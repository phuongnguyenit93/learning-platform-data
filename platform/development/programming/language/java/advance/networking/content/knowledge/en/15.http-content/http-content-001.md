# Where BodyPublisher, BodyHandler, and BodySubscriber Fit in an Exchange

## 1. Viewing the Entire HTTP Lifecycle from the Java HttpClient Perspective

When using `java.net.http.HttpClient` (available since Java 11), an HTTP exchange has **two separate body directions**:

- **Request body** goes **from client to server**.
- **Response body** goes **from server back to client**.

The three easily confused interfaces sit at **different points**:

1. **`HttpRequest.BodyPublisher`**: **request output**. Supplies the sequence of bytes that `HttpClient` sends in the request.
2. **`HttpResponse.BodyHandler<T>`**: **response handling selector**. Invoked when the HTTP **status and headers** of the response are available, but **before the response body is received**. It **returns** an appropriate `BodySubscriber<T>`.
3. **`HttpResponse.BodySubscriber<T>`**: **response input**. Receives the actual response bytes, consumes them via the `Flow` mechanism, and produces a body value of type `T` (for example `String`, `byte[]`, `Path`, or a streaming type).

~~~text
                       REQUEST DIRECTION
Client application
    |
    | Create HttpRequest + POST(BodyPublisher)
    v
HttpRequest.BodyPublisher -- Flow.Publisher<ByteBuffer> --> HttpClient
                                                           |
                                                           v
                                                    HTTP request bytes
                                                           |
                                                           v
                                                       HTTP server
                                                           |
                              server processes request, produces status/headers/body
                                                           |
                                                           v
                                                    HTTP response bytes
                                                           |
     RESPONSE DIRECTION                                    |
                                                           v
HttpClient has status + headers ----> BodyHandler<T>.apply(ResponseInfo)
                                               |
                                               | selects/returns BodySubscriber<T>
                                               v
                                     BodySubscriber<T>
                              Flow.Subscriber<List<ByteBuffer>>
                                               |
                              receives response body bytes
                                               |
                                               v
                                  CompletionStage<T> getBody()
                                               |
                                               v
                                 HttpResponse<T>.body()
~~~

**Do not reverse the directions:** `BodyPublisher` is about the **outgoing request**, whereas `BodyHandler` and `BodySubscriber` are about the **incoming response**. `BodyHandler` does not perform request uploads, and `BodySubscriber` is not where request headers or status are chosen.

This is a **client-side pipeline**. On the server, the `com.sun.net.httpserver.HttpHandler`/`HttpExchange` API is a **different** mechanism; it is not an `HttpResponse.BodyHandler`. The two runnable programs below create a loopback server only as a test environment for the client.

## 2. Distinguishing Similar Names: Three Interfaces and Three Factory Classes

| API Name | Role | Typical Input/Output |
| --- | --- | --- |
| `HttpRequest.BodyPublisher` | Supplies bytes to **send a request** | Implements `Flow.Publisher<ByteBuffer>`; has `contentLength()` |
| `HttpRequest.BodyPublishers` | **Factory** for creating BodyPublisher | `ofString`, `ofByteArray`, `ofFile`, `ofInputStream`, `noBody`, `fromPublisher` |
| `HttpResponse.BodyHandler<T>` | Selects response handling strategy based on **metadata** | `ResponseInfo -> BodySubscriber<T>` |
| `HttpResponse.BodyHandlers` | **Factory** for creating BodyHandler | `ofString`, `ofByteArray`, `ofFile`, `discarding`, `ofInputStream`, `ofPublisher` |
| `HttpResponse.BodySubscriber<T>` | Consumes response bytes and completes `T` | Implements `Flow.Subscriber<List<ByteBuffer>>`, has `getBody()` |
| `HttpResponse.BodySubscribers` | **Factory** for creating BodySubscriber for BodyHandler | `ofString`, `ofByteArray`, `ofFile`, `discarding`, `mapping`, `fromSubscriber` |

Because Java has factories with very similar names, look at the **prefix**:

- `HttpRequest.BodyPublishers.ofString("...")`: **encodes a String into an outgoing request body**.
- `HttpResponse.BodyHandlers.ofString(UTF_8)`: **returns a BodyHandler that chooses to receive the response as a String**.
- `HttpResponse.BodySubscribers.ofString(UTF_8)`: **the BodySubscriber that actually collects and decodes response bytes**. Usually `BodyHandlers.ofString(...)` creates this subscriber for us.

The two terms **Publisher** and **Subscriber** here both use Reactive Streams (`java.util.concurrent.Flow`) terminology, but data flows in **opposite directions**. `BodyHandler` is the coordinator sitting **between receiving headers and consuming the response body**, not a publisher.

## 3. BodyPublisher: Byte Source for an HTTP Request

A POST request is typically built as follows:

~~~java
HttpRequest.BodyPublisher publisher =
        HttpRequest.BodyPublishers.ofString(
                "Xin chào", StandardCharsets.UTF_8);

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://example.org/api"))
        .header("Content-Type", "text/plain; charset=utf-8")
        .POST(publisher)
        .build();
~~~

*This snippet requires imports and a real endpoint to run; the standalone version in Section 7 does not use the Internet.*

`BodyPublisher` extends `Flow.Publisher<ByteBuffer>`. When sending a request with a body, **`HttpClient` subscribes an internal `Flow.Subscriber<ByteBuffer>`** to that publisher; the publisher supplies `ByteBuffer`s on demand for the client to package and send over HTTP. Applications usually **do not call `subscribe` themselves** with built-in publishers.

The request body size is described via `publisher.contentLength()`:

- **`> 0`**: known byte count.
- **`== 0`**: empty body; the client may not need to subscribe.
- **`< 0`**: unknown length upfront; the client chooses transfer framing appropriate for the HTTP version/transport. Do not assume a `Content-Length` header is always present.

`contentLength()` is the **number of bytes**, not `String.length()`. For example, `"Xin chào"` in UTF-8 has multi-byte characters; if you want to limit upload size, check the **encoded byte count**, not just the character count.

A custom `BodyPublisher` needs to pay attention to:

- `contentLength()` must be **consistent** across calls.
- It may be subscribed **again** by `HttpClient` when a request needs to be resent due to redirect/authentication or internal conditions. A publisher whose data can only be read once will have issues without a retry/replay policy.
- After emitting a `ByteBuffer` to HttpClient, the publisher **must not continue accessing/modifying that buffer**; it must respect ownership and the `Flow` protocol.
- Use `Flow.Subscription.request(n)` to pace emission demand. A custom publisher must handle cancellation, errors, and completion properly, without emitting unbounded data.

### Common Request Source Choices

| Factory | Outgoing Data | When to Use |
| --- | --- | --- |
| `BodyPublishers.noBody()` | No body | GET or requests without a payload |
| `BodyPublishers.ofString(text, UTF_8)` | UTF-8 bytes of text | Small JSON/text POST already in memory |
| `BodyPublishers.ofByteArray(bytes)` | Binary data in an array | Small/medium binary payload |
| `BodyPublishers.ofFile(path)` | Reads a file to send | File upload, avoiding loading the whole file into a String yourself |
| `BodyPublishers.ofInputStream(supplier)` | Gets an `InputStream` from a `Supplier` when needed | Streaming data; the supplier should create a suitable stream per send attempt |
| `BodyPublishers.fromPublisher(flowPublisher)` | Gets `ByteBuffer` from a Flow publisher | Integrating with a custom streaming pipeline |

**Important distinction:** `BodyPublishers.ofFile(path)` **reads a source file to send**, whereas `BodyHandlers.ofFile(path)` **writes the received response to a destination file**. The `ofFile` name is the same, but the data direction is opposite.

The `Content-Type` header is not automatically generated just by using `ofString`; set the content type, charset, and protocol according to the server's requirements. `BodyPublisher` is **not responsible** for deciding the response status or turning the response into a String.

## 4. BodyHandler: Status and Headers Are Available, Body Is Not Yet

On the response path, after the HTTP client receives status/headers information, it calls:

~~~java
HttpResponse.BodyHandler<String> handler = info -> {
    int status = info.statusCode();
    HttpHeaders headers = info.headers();
    // Choose subscriber based on metadata; cannot read response body here yet.
    return HttpResponse.BodySubscribers.ofString(StandardCharsets.UTF_8);
};
~~~

*Illustrative example with `HttpHeaders`, `HttpResponse`, and `StandardCharsets` already imported; not a standalone program.*

The method `BodyHandler<T>.apply(HttpResponse.ResponseInfo info)` is called **after status and headers are available**, **before the response body is received**. At this point, the handler can inspect:

- `info.statusCode()`, for example 200, 204, 404.
- `info.headers()`, for example `Content-Type`, `Content-Length` (if present).
- `info.version()`, the HTTP protocol version used.

It chooses **a `BodySubscriber<T>`** for the HTTP client to interact with the body stream afterward. `BodyHandler` does not receive the payload's `byte[]` and should not attempt to parse the body inside `apply`.

Example of dispatching by status:

~~~java
HttpResponse.BodyHandler<String> handler = info ->
        info.statusCode() == 204
                ? HttpResponse.BodySubscribers.replacing("")
                : HttpResponse.BodySubscribers.ofString(StandardCharsets.UTF_8);
~~~

*Illustrative snippet: the 204 case returns an empty String and a `String`-typed body subscriber; in a real system, status/Content-Type must be handled according to contract.*

`BodySubscribers.replacing("")` discards the response body data and returns a fixed String value. Both branches must match the generic type `T == String`. If you want to return `byte[]`/`Path` instead of String, you must change both `BodyHandler<T>` and `HttpResponse<T>` consistently.

The factory `BodyHandlers.ofString(UTF_8)` is a built-in handler that usually does not inspect status. **HTTP 404/500 does not automatically throw an exception just because the status is non-2xx.** `send` can return an `HttpResponse<T>` with `statusCode()==404` and an error body, leaving it to the application to handle. If the body handler/IO encounters an error, that is a separate kind of failure.

## 5. BodySubscriber: Actually Receiving Response Bytes via Flow

`HttpResponse.BodySubscriber<T>` extends **`Flow.Subscriber<List<ByteBuffer>>`** and adds:

~~~java
CompletionStage<T> bodyStage = subscriber.getBody();
~~~

*Illustrative snippet with an existing `subscriber`; `getBody()` is not an operation where the application reads directly from the socket.*

The HTTP client delivers **lists of `ByteBuffer`s** containing response bytes. Standard `Flow` events:

1. `onSubscribe(Flow.Subscription subscription)`: receives the subscription, calls `subscription.request(n)` to request **n more items**.
2. `onNext(List<ByteBuffer> buffers)`: receives **one item, which is a list** of ByteBuffers; process every buffer in the list in order.
3. `onComplete()`: the body stream has finished normally.
4. `onError(Throwable error)`: the body stream failed; do not treat an incomplete body as success.

**Common pitfall:** on the response side, the item requested by `request(n)` is a **`List<ByteBuffer>`**, not `n` bytes. The sizes of the lists/ByteBuffers and the number of `onNext` calls are **not guaranteed** to match individual server `write` calls, TCP packets, or text lines.

`BodySubscriber.getBody()` returns a **`CompletionStage<T>`**. For full-body buffering subscribers like `ofString` or `ofByteArray`, the stage typically completes only after the entire body has been received/converted. For **streaming** subscribers, such as `ofInputStream` or `ofPublisher`, the stage can complete **early**, as soon as the stream/publisher object is ready, while the actual response bytes are consumed later by the application.

This is why **"`HttpResponse<T>` is available" does not always mean "all response bytes have been consumed"**. It depends on `T` and the type of subscriber/handler chosen.

## 6. Timeline: Who Runs When, and How send Differs from sendAsync

For a POST request and String response:

~~~text
T0  newBuilder().POST(BodyPublishers.ofString(...)).build()
    -> only creates request configuration, NOT sent over the network yet.

T1  HttpClient.send(request, BodyHandlers.ofString(UTF_8))
    -> starts the HTTP exchange.

T2  HttpClient subscribes to the request's BodyPublisher
    -> request ByteBuffers are emitted/written according to Flow and transport.

T3  Server receives request, processes it, and returns status + headers.

T4  BodyHandler is invoked with ResponseInfo
    -> selects BodySubscriber<String> based on metadata.

T5  HttpClient delivers response body via onSubscribe/onNext/... to subscriber
    -> subscriber processes bytes, manages backpressure.

T6  BodySubscriber.getBody() completes with String (with ofString, after full body)
    -> HttpResponse<String>.body() is the resulting String.
~~~

These milestones can **overlap** and are not strictly sequential between sending the request and receiving the response: a server can reject a request early and return a response before the entire request body is uploaded, depending on HTTP protocol and policy. The timeline only illustrates API relationships.

**`send` vs. `sendAsync`:**

- `client.send(request, handler)`: **blocks the caller thread** until an `HttpResponse<T>` is available according to the body handler's semantics, or an error/interruption occurs.
- `client.sendAsync(request, handler)`: returns a **`CompletableFuture<HttpResponse<T>>`** so the caller can continue other work. `thenApply`/`thenAccept`/`exceptionally` run when the future completes.
- `future.join()` or `future.get()` can **block** if the result is not ready yet, even though the request was sent via the async API.
- `HttpResponse<String>` from `BodyHandlers.ofString` usually means **the String body has been fully collected**, whereas `BodyHandlers.ofInputStream` can return a response as soon as the stream is available and the application must still read/close the stream.
- `CompletableFuture` completion from the HTTP client represents **the exchange processing state according to the body handler**, not confirmation that a business operation was successfully committed by the server.

## 7. Complete Java 17+ Example: BodyPublisher Sends Request, BodyHandler Selects Subscriber

The first program does not need the Internet: it runs an `HttpServer` on **127.0.0.1** in the same JVM, then sends a POST `PING` from Java `HttpClient`. The server reads the request body and replies with `ACK:PING`. On the client side:

- `HttpRequest.BodyPublishers.ofString("PING", UTF_8)` creates the source body with `contentLength() == 4` bytes.
- `BodyHandler<String>` reads `ResponseInfo.statusCode()` before the response body is received; returns `BodySubscribers.ofString(UTF_8)`.
- `client.send(...)` returns `HttpResponse<String>`; `response.body()` is the subscriber's result.

Create `HttpBodyPipelineDemo.java`:

~~~java
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class HttpBodyPipelineDemo {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        AtomicReference<String> requestAtServer = new AtomicReference<>();
        server.createContext("/echo", exchange -> {
            try {
                String received = new String(
                        exchange.getRequestBody().readAllBytes(),
                        StandardCharsets.UTF_8);
                requestAtServer.set(exchange.getRequestMethod() + " " + received);
                byte[] reply = ("ACK:" + received).getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set(
                        "Content-Type", "text/plain; charset=utf-8");
                exchange.sendResponseHeaders(200, reply.length);
                exchange.getResponseBody().write(reply);
            } finally {
                exchange.close();
            }
        });
        server.start();
        try {
            HttpRequest.BodyPublisher publisher =
                    HttpRequest.BodyPublishers.ofString(
                            "PING", StandardCharsets.UTF_8);
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create("http://127.0.0.1:"
                            + server.getAddress().getPort() + "/echo"))
                    .header("Content-Type", "text/plain; charset=utf-8")
                    .POST(publisher)
                    .build();

            AtomicInteger statusAtHeaders = new AtomicInteger(-1);
            HttpResponse.BodyHandler<String> handler = info -> {
                statusAtHeaders.set(info.statusCode());
                return HttpResponse.BodySubscribers.ofString(
                        StandardCharsets.UTF_8);
            };
            HttpResponse<String> response = HttpClient.newHttpClient()
                    .send(request, handler);
            System.out.println("publisher bytes: " + publisher.contentLength());
            System.out.println("server received: " + requestAtServer.get());
            System.out.println("handler saw status: " + statusAtHeaders.get());
            System.out.println("response status: " + response.statusCode());
            System.out.println("response body: " + response.body());
        } finally {
            server.stop(0);
        }
    }
}
~~~

Run (JDK 17 or newer):

~~~bash
javac HttpBodyPipelineDemo.java
java HttpBodyPipelineDemo
~~~

Output when loopback works normally:

~~~text
publisher bytes: 4
server received: POST PING
handler saw status: 200
response status: 200
response body: ACK:PING
~~~

### Where Does Each Part of the Output Come From?

- `publisher bytes: 4` comes from `BodyPublisher.contentLength()`: the length of the encoded **request body**, not the response length.
- `server received: POST PING` is the **server fixture** reading `HttpExchange.getRequestBody()`, proving the request was actually sent.
- `handler saw status: 200` is the `ResponseInfo.statusCode()` value that **`BodyHandler.apply`** sees at the headers stage. The handler does not receive the body itself; it returns a subscriber.
- `response status: 200` is metadata on `HttpResponse<String>` after `send`.
- `response body: ACK:PING` is the result of **`BodySubscriber<String>`** processing the response body. `HttpClient` invokes the Flow callbacks internally, so the example does not need to implement `Flow.Subscriber` itself.

Do not confuse `server.createContext("/echo", exchange -> ...)` with `HttpResponse.BodyHandler`: the server fixture function handles **incoming HTTP requests to the server**, whereas the client-side `BodyHandler` handles **how to receive the response**.

## 8. Complete Java 17+ Example: Custom BodySubscriber, Demand, and sendAsync

The second example intentionally creates a `Flow.Subscriber<List<ByteBuffer>>` to show how `BodySubscriber` works. `HttpResponse.BodySubscribers.fromSubscriber(...)` adapts the application-written subscriber into a `BodySubscriber<String>` using a `finisher` function.

The server sends the string `STREAM:ONE-TWO` in two `write` calls. On the client, **do not assume** there will be exactly two `onNext` calls: the HTTP/TCP layer may coalesce or split data depending on the implementation.

Create `HttpBodyFlowDemo.java`:

~~~java
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayOutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Flow;
import java.util.concurrent.atomic.AtomicReference;

public class HttpBodyFlowDemo {
    static final class CopyingSubscriber
            implements Flow.Subscriber<List<ByteBuffer>> {
        private final ByteArrayOutputStream collected = new ByteArrayOutputStream();
        private Flow.Subscription subscription;
        private int onNextCalls;
        private boolean finished;

        @Override
        public void onSubscribe(Flow.Subscription s) {
            subscription = s;
            s.request(1);
        }

        @Override
        public void onNext(List<ByteBuffer> buffers) {
            for (ByteBuffer buffer : buffers) {
                byte[] chunk = new byte[buffer.remaining()];
                buffer.get(chunk);
                collected.write(chunk, 0, chunk.length);
            }
            onNextCalls++;
            subscription.request(1);
        }

        @Override
        public void onError(Throwable error) {
            System.err.println("response body failed: " + error.getClass().getName());
        }

        @Override
        public void onComplete() {
            finished = true;
        }

        String result() {
            return new String(collected.toByteArray(), StandardCharsets.UTF_8);
        }

        boolean receivedData() {
            return onNextCalls > 0;
        }

        boolean completed() {
            return finished;
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/stream", exchange -> {
            try {
                byte[] message = "STREAM:ONE-TWO".getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set(
                        "Content-Type", "text/plain; charset=utf-8");
                exchange.sendResponseHeaders(200, 0);
                exchange.getResponseBody().write(message, 0, 7);
                exchange.getResponseBody().write(message, 7, message.length - 7);
            } finally {
                exchange.close();
            }
        });
        server.start();
        try {
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create("http://127.0.0.1:"
                            + server.getAddress().getPort() + "/stream"))
                    .GET().build();
            AtomicReference<CopyingSubscriber> observed = new AtomicReference<>();
            HttpResponse.BodyHandler<String> handler = info -> {
                CopyingSubscriber collector = new CopyingSubscriber();
                observed.set(collector);
                return HttpResponse.BodySubscribers.fromSubscriber(
                        collector, CopyingSubscriber::result);
            };

            CompletableFuture<HttpResponse<String>> future =
                    HttpClient.newHttpClient().sendAsync(request, handler);
            HttpResponse<String> response = future.join();
            System.out.println("status: " + response.statusCode());
            System.out.println("onNext called: " + observed.get().receivedData());
            System.out.println("onComplete called: " + observed.get().completed());
            System.out.println("subscriber body: " + response.body());
        } finally {
            server.stop(0);
        }
    }
}
~~~

Run:

~~~bash
javac HttpBodyFlowDemo.java
java HttpBodyFlowDemo
~~~

Output:

~~~text
status: 200
onNext called: true
onComplete called: true
subscriber body: STREAM:ONE-TWO
~~~

### Explaining Flow in the Example

1. `HttpResponse.BodyHandler<String>` is called when headers are ready. It creates a new `CopyingSubscriber` **for this response**, then uses `BodySubscribers.fromSubscriber(collector, CopyingSubscriber::result)`.
2. `onSubscribe` is called with `Flow.Subscription`; `request(1)` allows the HTTP client to emit **one List<ByteBuffer> item**.
3. `onNext` iterates over **every ByteBuffer in the List**, copies the exact `remaining()` bytes into a buffer; calls `request(1)` to allow the next item. Do not treat each item as exactly one HTTP frame, one server write, or one character.
4. `onComplete` marks the response body stream as finished. The `fromSubscriber` adapter applies `finisher` after onComplete, converting the collected bytes into a UTF-8 `String`.
5. `CompletableFuture<HttpResponse<String>>` is returned immediately by `sendAsync`; `join()` in the **demo** waits to print stable output. In a real asynchronous application, you can attach `thenApply`/`thenAccept` and handle exceptions without blocking the calling thread.
6. Because the body type is `String` accumulating the entire body, this example is only suitable for small/controlled responses. For large bodies, use a streaming/file-writing subscriber and data limits.

**Note:** `onNextCalls` may be 1, 2, or another number. The output only prints `onNext called: true`, **not a fixed chunk count**. `request(1)` paces by **the number of List<ByteBuffer> emissions**, not by bytes or the number of elements in the List.

## 9. Type Boundaries to Remember

~~~text
Request:
  String/byte[]/Path
      -> BodyPublisher extends Flow.Publisher<ByteBuffer>
      -> HttpClient receives each ByteBuffer to send the request.

Response:
  HTTP status + headers
      -> BodyHandler<T>.apply(ResponseInfo)
      -> BodySubscriber<T> extends Flow.Subscriber<List<ByteBuffer>>
      -> getBody(): CompletionStage<T>
      -> HttpResponse<T>.body() has type T.
~~~

Comparing the two `Flow` branches:

| Side | `Flow` type | Who holds the subscriber role? | What does it transfer? |
| --- | --- | --- | --- |
| **Sending request** | `Flow.Publisher<ByteBuffer>` | `HttpClient` is the internal subscriber | Outbound body buffers |
| **Receiving response** | `Flow.Subscriber<List<ByteBuffer>>` | `BodySubscriber<T>` chosen by `BodyHandler` | Inbound body buffer lists |
| **Streaming response via ofPublisher** | `Flow.Publisher<List<ByteBuffer>>` is the **returned body type** | Application subscribes a subscriber to the publisher after receiving response | Forwarded inbound buffer lists |

Because `BodySubscriber` receives **List<ByteBuffer>**, custom code must iterate through two layers: each `onNext` can contain one or more buffers. When decoding UTF-8, a multi-byte character can span across multiple buffers; **do not decode each chunk individually** with `new String(chunk)` and concatenate, because that can split mid-character. Use a stateful streaming decoder or collect/copy bytes in order and decode once complete, as in the small-response example.

In Java Flow, terminal signals `onComplete` and `onError` end the subscription; do not call `request` after canceling a subscription to "re-read" lost body parts. If the application does not want to receive more, `subscription.cancel()` is the cancellation operation; it has consequences for reusable HTTP connections.

## 10. BodyHandler Can Choose Different Receiving Strategies

Not every response should be collected into a String:

| BodyHandler factory | Body type `T` | Characteristics |
| --- | --- | --- |
| `BodyHandlers.ofString(UTF_8)` | `String` | Collects body then decodes; convenient for small JSON/text, needs size control |
| `BodyHandlers.ofByteArray()` | `byte[]` | Collects binary data; can consume a lot of RAM |
| `BodyHandlers.ofFile(path)` | `Path` | Writes response bytes to a file; used for downloads and path/permission management |
| `BodyHandlers.discarding()` | `Void` | Reads/discards data, produces no body content |
| `BodyHandlers.ofInputStream()` | `InputStream` | Returns a stream for the application to read incrementally; **must read fully/close** |
| `BodyHandlers.ofLines()` | `Stream<String>` | Reads text line by line; manage/close stream properly |
| `BodyHandlers.ofPublisher()` | `Flow.Publisher<List<ByteBuffer>>` | Exposes body as a Flow publisher for the application to subscribe/pace |
| Custom `BodyHandler<T>` | By design | Selects `BodySubscriber` by `statusCode/headers`, e.g., ignore body on 204 |

Built-in `BodyHandlers` **do not automatically reject HTTP 4xx/5xx**. If an API treats non-2xx statuses as business errors, check `response.statusCode()` after receiving the response or choose an appropriate subscriber from `BodyHandler.apply`. Choosing `discarding()` drops error bodies, losing server message details; sometimes a bounded small error body should be kept for diagnostics.

**`ofInputStream`/`ofLines`/`ofPublisher` have a different lifecycle from `ofString`.** `HttpResponse<T>` may be returned before the application has consumed the entire body; if the application holds the stream without reading/closing it, HTTP connection resources can be held up. With a streaming publisher, if not subscribed or if the subscriber does not request more items, the response body cannot complete as the application expects.

For downloading large responses, consider `ofFile`, `ofInputStream`, or streaming, checking size as data arrives and handling cancellation/cleanup. `BodyHandlers.ofString` is very convenient, but should not be used unconditionally with payloads that might be too large or from untrusted sources.

## 11. Backpressure, Cancellation, and Network Resources

`Flow.Subscription.request(n)` is a signal of **demand for more items**, not an application command to "read n bytes from the socket". `HttpClient` coordinates demand so it does not deliver data to the subscriber beyond its demand, in accordance with the Flow protocol.

**On the request side:**

- The publisher receives demand from `HttpClient`'s internal subscriber and emits `ByteBuffer`s accordingly.
- The publisher must honor `cancel` and emit `onComplete`/`onError` according to the lifecycle.
- Publishers from files/streams must manage the data source when sending finishes/cancels/fails. `BodyPublishers.ofInputStream(supplier)` must be able to create **an appropriate InputStream per subscription** if the request is resent.
- If `contentLength()` declares the wrong byte count emitted, the exchange may fail; do not assume the HTTP client will automatically fix a broken custom publisher.

**On the response side:**

- The subscriber calls `request(n)` to receive subsequent **List<ByteBuffer>** items, properly processing `remaining()` bytes.
- If you do not want to consume the rest, call `cancel()`; Java documentation warns that early cancellation may **close the connection and prevent reuse**. To leverage keep-alive, choose a strategy that reads/discards to the end when appropriate for resources, timeouts, and security.
- If a custom subscriber gets stuck because it never calls `request`, the response body can stall indefinitely. Keeping an unbounded buffer is not backpressure either: you must bound RAM, bytes, time, and concurrent exchanges.
- `BodySubscriber.getBody()` must be able to return a `CompletionStage` at any time; do not write a blocking implementation inside `getBody()` that stalls the HTTP client.
- After `onComplete` or `onError`, complete or fail the body stage properly. Using the `BodySubscribers.fromSubscriber(...)` factory is usually safer and cleaner than implementing the entire protocol yourself.

**Do not use HTTP client BodySubscriber to replace all application-layer framing.** `BodySubscriber` handles receiving response bytes over HTTP, while JSON/NDJSON parsers, limits, and schema validation belong to the layer above.

## 12. Content-Type, Content-Length, and Streaming Reality

`Content-Type` and `Content-Length` are **HTTP headers**, not the body itself:

- `Content-Type: application/json; charset=utf-8` describes the data type; `BodyPublishers.ofString`/`BodyHandlers.ofString` do not guarantee automatic JSON schema validation. The application must choose charset/parse/validate itself.
- `BodyPublisher.contentLength()` is **request body** information from the publisher, which may be known or unknown. If unknown (`-1`), the HTTP client can use appropriate transfer framing; manually setting a `Content-Length` that conflicts with the publisher is unsafe.
- `Content-Length` on a response may not be present (HTTP/2 framing, HTTP/1.1 chunked transfer, or other cases). Do not treat the header value as the sole boundary of data read by the application.
- A response may use `Content-Encoding` such as gzip per protocol configuration; **do not assume `BodyHandler` automatically decompresses all content**. Handle encoding according to the actual API/service contract, and check size **after decompression** to avoid abnormal payload expansion.
- A response may contain a header reporting a small length while the actual body or decoded data is large; check **actual bytes received and resource limits** in the pipeline, not just the header.
- `HEAD`/`204 No Content`/`304 Not Modified` normally have no response body per HTTP semantics; the handler can use a subscriber that discards the body/returns an appropriate empty value, while still handling status/headers.

If the application requires limiting response size, choose a subscriber/streaming consumer that tracks actual byte count and cancels or stops when exceeding the limit; simply using `BodyHandlers.ofString` after looking at `Content-Length` is not enough to reliably protect against untrusted peers.

## 13. HTTP Errors, Body Errors, and CompletableFuture: Do Not Mix Them Up

| Event Type | Where Does It Usually Appear? | Proper Handling |
| --- | --- | --- |
| Server returns `404`/`500` | `HttpResponse.statusCode()`, BodyHandler may still be called | It is an **HTTP status**, not automatically equivalent to a Java exception |
| Connection failure/DNS/TLS fail | `send` throws `IOException` or `sendAsync` completes exceptionally | BodyHandler may not have been called yet, as response headers may not exist |
| Request timeout | `HttpTimeoutException` or related I/O error | Manage deadline/retry according to idempotency |
| `BodyPublisher` fails while emitting request | Exchange fails, error surfaces via `send`/future | Check file/stream/publisher, not just the response |
| `BodyHandler.apply` throws an error | Failed to create an appropriate subscriber | Fix subscriber selection logic; do not parse response body here |
| `BodySubscriber.onError` | Flow receiving body encountered an error | Do not pass an incomplete body to the parser as success |
| `send` is interrupted | `InterruptedException` | Restore interrupt state or handle per policy; do not swallow the error |
| `sendAsync` fails | Future completes exceptionally, `join()` may throw `CompletionException` | Check `getCause()`, timeout/cancellation, and cleanup |
| Streaming body not fully consumed | `HttpResponse<InputStream>` may have been returned while stream is still open | Read/close/cancel appropriately to release resources |

A `sendAsync` handling chain can typically attach:

~~~java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());

future.thenApply(response -> {
    if (response.statusCode() / 100 != 2) {
        throw new IllegalStateException(
                "HTTP status " + response.statusCode());
    }
    return response.body();
}).thenAccept(body -> {
    // Parse/validate and process the received body.
}).exceptionally(error -> {
    // Log phase/cause, apply retry and cleanup according to policy.
    return null;
});
~~~

*This is an **illustrative snippet** inside a class with `client`/`request` and imports; not a standalone program.*

`thenApply`/`thenAccept` may run on the thread performing completion or the caller thread depending on Future state; do not block for long inside callbacks. Handling HTTP status errors **after** receiving the response does not change the fact that `BodyHandler` was already used to choose how to consume the response body.

For non-idempotent requests (for example creating an order), do not retry blindly just because the Future failed: the server may have already received or processed the request even if the response failed. Use an idempotency token/key and clear business contracts.

## 14. Most Common Misconceptions

| Misconception | Why Is It Wrong? | How to Remember |
| --- | --- | --- |
| "BodyPublisher receives the response." | This publisher belongs to `HttpRequest` | Publisher **sends the request** |
| "BodyHandler receives each body byte." | Handler only sees `ResponseInfo` before the body | Handler **selects the subscriber** |
| "BodySubscriber decides the response status itself." | Status is already available before the subscriber is chosen | Subscriber **consumes response bytes** |
| "BodyHandlers.ofString and BodyPublishers.ofString are equivalent." | One handles inbound, the other creates outbound | Check the `HttpRequest`/`HttpResponse` prefix |
| "onNext receives a single ByteBuffer." | `BodySubscriber` receives `List<ByteBuffer>` | Iterate over all buffers in each list |
| "request(1) means one byte." | Flow demand counts items | One item is one buffer list |
| "Two writes on the server = two onNext calls on the client." | HTTP/TCP does not preserve write boundaries | Do not rely on chunk count |
| "sendAsync returning a Future means the body is done." | The Future may not be complete yet; streaming completes at a different stage | Understand `CompletionStage<T>` and body type |
| "BodyHandler is only called on HTTP 200." | Handler is used to receive responses with non-2xx statuses too | Always check `statusCode()` |
| "ofInputStream does not need closing." | Connections/resources can be held open | Read and close the stream |
| "ofString is suitable for downloading gigabytes." | Buffers the body in RAM | Use streaming/ofFile and byte limits |
| "contentLength is the character count." | It represents bytes | Count bytes after encoding |
| "A custom publisher can modify a buffer right after onNext." | Violates ownership | Respect Flow and buffer lifecycle |
| "Canceling a subscriber does not affect the connection." | Can close the HTTP connection, reducing reuse | Decide to consume/discard/cancel intentionally |
| "HTTP 500 always makes send throw IOException." | 500 is a valid HTTP status | Distinguish transport vs HTTP status |
| "Using BodyHandler means writing a server handler." | It is a client response handler | Server `HttpHandler` is a different API |

## 15. Self-Check Questions

**Question 1.** In `client.send(request, BodyHandlers.ofString())`, where is the BodyPublisher?

*Answer:* It is attached **inside `request`**, for example `POST(BodyPublishers.ofString("PING"))`. The parameter to `send` is the **BodyHandler** for the **response**, not the request publisher.

**Question 2.** When is `BodyHandler.apply(ResponseInfo)` called?

*Answer:* When the response status and headers are available, **before body bytes are received**. The handler returns a `BodySubscriber<T>` to continue processing the body.

**Question 3.** What data type does `BodySubscriber<T>` receive in `onNext`? What does `request(1)` mean?

*Answer:* It receives `List<ByteBuffer>` via Flow; `request(1)` requests **one item, which is a list of buffers**, not one byte or a single buffer.

**Question 4.** `BodyHandlers.ofInputStream()` has returned `HttpResponse<InputStream>`. Has the large body been fully read yet?

*Answer:* **Not necessarily**. The stage returning the InputStream body object can complete early, and the application must still read/close the stream to finish consumption and release resources.

**Question 5.** The server returns 404 with a JSON error body. Does `BodyHandlers.ofString(UTF_8)` automatically throw `IOException`?

*Answer:* Not just because of the 404 status. The client can still receive `HttpResponse<String>`, and must check `statusCode()` then handle the error body. A Java exception occurs if there is a connection/HTTP processing/other body-handling error.

**Question 6.** Why can a custom BodyPublisher that can only be read once fail when a request is resent?

*Answer:* `HttpClient` may subscribe again when it needs to resend. The publisher must be able to replay data consistently, or the application must choose a policy not to retry non-replayable requests.

**Question 7.** Why can't you do `new String(chunk)` for each ByteBuffer and concatenate when a UTF-8 response contains Vietnamese text?

*Answer:* A UTF-8 character has multiple bytes and can be split across buffer boundaries; decoding each piece separately can corrupt characters. You need a stateful streaming decoder or to collect bytes and decode once complete.

## 16. Practice Exercises

1. **Trace the pipeline:** in `HttpBodyPipelineDemo`, mark the line creating `BodyPublisher`, the line attaching it to `POST(...)`, the line where `BodyHandler` selects `BodySubscriber`, and the line retrieving `HttpResponse<String>.body()`. Explain why `server.createContext` is not a client BodyHandler.
2. **Change body type:** replace `BodySubscribers.ofString(UTF_8)` with `BodySubscribers.ofByteArray()`, change the generic to `HttpResponse<byte[]>`, and decode `new String(response.body(), UTF_8)` after receiving. State the trade-offs.
3. **By status:** modify the server to return `404` and a small error JSON; try `BodyHandlers.ofString` and print status + body. Write a custom handler using `BodySubscribers.replacing("")` for `204` without losing metadata.
4. **Backpressure:** in `HttpBodyFlowDemo`, try `request(1)` on each `onNext` and compare with omitting the next request call. Observe why the Future may not complete if the flow still needs demand.
5. **Chunk boundaries:** change the response to a long Vietnamese string; observe how the number of `onNext` calls can vary across runs and verify the final body is still correct if all bytes are copied and decoded once.
6. **Large streaming:** sketch `BodyHandlers.ofFile(path)` versus `ofString`, accounting for download limits, error/cancellation handling, and cleaning up partially downloaded files.
7. **Client architecture:** draw the pipeline for an authenticated JSON POST with 201 and 422 responses; identify precisely which layer checks TLS, HTTP status, body type, JSON schema, and business ACK.
8. **Retry capability:** design a `BodyPublisher` from an InputStream with a supplier that creates a new stream per subscription, and explain how to ensure identical content when the HTTP client needs to resend while avoiding retrying non-idempotent business operations.

## Standard Java Documentation

- [`HttpRequest.BodyPublisher` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublisher.html): `Flow.Publisher<ByteBuffer>` and `contentLength()`.
- [`HttpRequest.BodyPublishers` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html): factory for request data sources.
- [`HttpResponse.BodyHandler<T>` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandler.html): invoked after headers, before response body, selects `BodySubscriber<T>`.
- [`HttpResponse.BodySubscriber<T>` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscriber.html): `Flow.Subscriber<List<ByteBuffer>>` and `getBody()`.
- [`HttpResponse.BodyHandlers` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): factory for receiving responses.
- [`HttpResponse.BodySubscribers` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html): subscribers, mapping, `fromSubscriber`, and streaming.
- [`HttpClient` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html): `send`, `sendAsync`, and HTTP exchange.
- [`Flow` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.html): reactive streams, demand, subscription, and terminal signals.
