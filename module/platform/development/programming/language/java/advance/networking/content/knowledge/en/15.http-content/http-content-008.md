# Flow.Publisher, Flow.Subscriber, and Demand (Backpressure) in Java HTTP Content

When an HTTP server sends a very large response, or a client needs to upload data in multiple parts, you should not default to **reading the entire body into RAM before processing it**. Java 17 provides a demand-driven flow-control mechanism via `java.util.concurrent.Flow`. In this model, **`Flow.Publisher<T>` emits items**, **`Flow.Subscriber<T>` consumes them**, and **`Flow.Subscription.request(n)` indicates how many more items the subscriber allows itself to receive**. This mechanism is called **backpressure**: the receiver proactively signals how much data it can accept, preventing the sender from pushing data indefinitely into a queue.

This topic is especially important in **HTTP content** with `java.net.http.HttpClient`:

- On the **request-sending** side: `HttpRequest.BodyPublisher` **extends `Flow.Publisher<ByteBuffer>`**. The HTTP client subscribes to this publisher to pull body bytes to send over the network.
- On the **response-receiving** side: `HttpResponse.BodySubscriber<T>` **extends `Flow.Subscriber<List<ByteBuffer>>`**. The HTTP client emits **lists of buffers** of the body to the subscriber.
- `HttpResponse.BodyHandlers.ofPublisher()` allows the application to receive a **`Flow.Publisher<List<ByteBuffer>>`** instead of waiting for the entire response body as a String/byte array, then register a subscriber and regulate the number of requested items.
- `HttpRequest.BodyPublishers.fromPublisher(...)` connects an application-provided `Flow.Publisher<ByteBuffer>` to the HTTP request body.

This lesson distinguishes demand by **item count** from actual capacity **in bytes**, explains the `onSubscribe/onNext/onError/onComplete` signal protocol, handling `request(n)` and `cancel()`, how to avoid stalls when publisher/subscriber run asynchronously, and how to use real streaming in HTTP. A complete Java 17+ program in section 8 runs on loopback, testing both plain Flow and HTTP request/response without needing Internet access.

## 1. The problem: fast producer, slow consumer

Suppose an HTTP response is 500 MB, but the application can only process 2 MB per second. If the HTTP client accumulates all 500 MB before returning a `String` or `byte[]`, it can hold a very large amount of memory; if the application does not have enough RAM, it may encounter GC pressure or `OutOfMemoryError`.

With streaming, the application wants to follow this flow:

~~~text
HTTP server/network  ->  HttpClient  ->  downstream application
      send bytes           read bytes       decode / save to file
          |                    |                    |
          |       Flow.Publisher<List<ByteBuffer>>  |
          |                    |                    |
          |                    +--- onSubscribe ---->|
          |                    |<-- request(1) ------+
          |                    +--- onNext(batch A) -> process A
          |                    |<-- request(1) ------+
          |                    +--- onNext(batch B) -> process B
          |                    |<-- request(1) ------+
          |                    ...
          |                    +--- onComplete() --->|
~~~

The consumer proactively limits **the remaining number of allowed `onNext` calls**, rather than asking for an exact number of bytes. A compliant Publisher must not emit `onNext` beyond the outstanding demand. Once downstream finishes an item, it can grant more demand.

**Important note:** Flow backpressure is an **application-level protocol between Publisher and Subscriber**. It does not guarantee that the socket has no bytes left in the kernel buffer, that the server stops sending immediately, or that memory drops to 0: the HTTP client, TCP/HTTP/2, proxies, the OS, and the publisher may still hold internal buffers. However, it helps prevent items from being pushed to the application faster than the application has approved.

## 2. The four core interfaces of java.util.concurrent.Flow

`Flow` has the following nested interfaces:

| Interface | Role | Key methods |
| --- | --- | --- |
| `Flow.Publisher<T>` | Source emitting items of type `T`; creates a subscription for a subscriber | `subscribe(Subscriber<? super T>)` |
| `Flow.Subscriber<T>` | Receiver that processes items and terminal signals | `onSubscribe`, `onNext`, `onError`, `onComplete` |
| `Flow.Subscription` | Control link for **one publisher–subscriber subscription** | `request(long n)`, `cancel()` |
| `Flow.Processor<T,R>` | Both receives `T` as a Subscriber and emits `R` as a Publisher | Combines both directions; must propagate demand properly |

These interfaces correspond to the Reactive Streams model. A Publisher instance may have one or more subscribers depending on the implementation; **each subscription has its own demand**, and the allowed item count must not be mixed across subscribers.

### 2.1. Subscriber role and lifecycle

A normal lifecycle:

~~~text
Publisher.subscribe(subscriber)
      |
      v
subscriber.onSubscribe(subscription)
      |
      +--> subscription.request(n), with n > 0
               |
               v
          subscriber.onNext(item)  (0 or more times,
               |                   not exceeding demand)
               +--> request(m) if more items are desired
               |
               +--> subscriber.onComplete() when source ends
               |
               +--> or subscriber.onError(cause) on failure
~~~

Once a terminal signal `onComplete` or `onError` has been received, that subscription must not emit any further items. These two terminal signals are **mutually exclusive** in a valid stream. `onSubscribe` must arrive before any item or terminal signal for the subscription.

**Do not call `onNext` before `onSubscribe`**, do not call `onNext(null)` if the protocol/implementation does not allow null, and do not emit after a terminal signal. The Publisher is responsible for proper serialization/signaling; the Subscriber must also maintain thread-safe coordination if sharing state outside callbacks.

### 2.2. Subscription.request(n) — item count, not bytes

`subscription.request(n)` **adds** `n` to the subscription's unsatisfied demand. If you call `request(2)` followed by `request(3)`, the total newly granted demand is 5 items minus any already received. Flow allows `Long.MAX_VALUE` as effectively unbounded demand.

Arithmetic example:

| Event | Effective remaining demand |
| --- | ---: |
| Just subscribed, no request yet | 0 |
| Subscriber calls `request(2)` | 2 |
| Publisher emits `onNext(A)` | 1 |
| Subscriber calls `request(3)` | 4 |
| Publisher emits `onNext(B)` | 3 |
| Publisher emits `onNext(C)` | 2 |

Calling `request(2)` **does not require** the Publisher to emit exactly two items immediately: if no data is available, if the stream has ended, or due to scheduling conditions, fewer items may arrive. The Publisher must not exceed the quota the subscriber has granted.

Calling `request(0)` or `request(-1)` is **invalid**: per the `Flow.Subscription` contract, the subscriber will be signaled with `onError(IllegalArgumentException)`. Do not use `request(0)` as a "pause"; to pause, simply **do not request more**.

### 2.3. Requesting one item at a time

An easy-to-learn approach is to start with `request(1)`, and only grant one more item after finishing `onNext(item)`:

~~~java
// Java 17+ fragment, subscriber processing String items one by one.
Flow.Subscriber<String> subscriber = new Flow.Subscriber<>() {
    private Flow.Subscription subscription;

    @Override
    public void onSubscribe(Flow.Subscription s) {
        subscription = s;
        s.request(1);
    }

    @Override
    public void onNext(String value) {
        process(value);         // Application helper.
        subscription.request(1); // Only request more after processing.
    }

    @Override
    public void onError(Throwable error) {
        recordFailure(error);   // Application helper.
    }

    @Override
    public void onComplete() {
        markFinished();         // Application helper.
    }
};
~~~

This is a **fragment**, not a standalone runnable class; `process/recordFailure/markFinished` must be defined. In production, you need to handle exceptions thrown by `process`, bound processing time, handle cancellation, and coordinate threads. If `process(value)` takes a long time, calling it directly inside `onNext` can also block the publisher's dispatch thread; you can offload processing to a bounded executor/queue and only call `request(1)` **after** the item has actually been consumed.

The advantage of `request(1)` is simplicity and ease of verifying that demand is not exceeded. The disadvantage is more demand-signaling round trips, resulting in higher overhead when items are small and throughput is high.

### 2.4. Batch requesting and refilling

With a batch size of 8, you can request 8 items initially, and after processing 4 items, request 4 more. That way, outstanding demand stays roughly between 4 and 8 items under continuous emission/consumption:

~~~java
// Fragment: same subscription, callbacks are invoked sequentially.
private static final int WINDOW = 8;
private Flow.Subscription subscription;
private int handledSinceRefill;

@Override
public void onSubscribe(Flow.Subscription s) {
    subscription = s;
    s.request(WINDOW);
}

@Override
public void onNext(Item item) {
    consume(item); // Helper must complete or have an internal ack mechanism.
    if (++handledSinceRefill == WINDOW / 2) {
        handledSinceRefill = 0;
        subscription.request(WINDOW / 2);
    }
}
~~~

This is an **algorithmic pattern**, not a separately compilable Java file (requires `Item` and `consume`). Choose the window based on item count, average/maximum item size, queue capacity, downstream CPU/I/O, and deadlines. Do not optimize solely for fewer `request` calls while ignoring the memory budget.

**A subscription does not automatically convert items into bytes:** if each item is 1 KB, a demand of 8 is about 8 KB of payload; if each item is 8 MB, a demand of 8 can push up to 64 MB plus overhead downstream. Therefore, item-based backpressure alone is not enough to enforce a strict **byte limit** if item sizes vary.

## 3. Cancel and terminal signals: not the same thing

`Subscription.cancel()` asks the Publisher to **eventually stop sending**. According to the Javadoc, this is **best-effort**; some already-scheduled signals may still arrive after `cancel()` is called. A cancelled subscription is **not required** to emit `onComplete` or `onError`.

Comparison:

| Action | Initiated by | Meaning |
| --- | --- | --- |
| `request(n>0)` | Subscriber | Allows receiving `n` more items |
| `cancel()` | Subscriber | No longer wants more items; Publisher attempts to stop |
| `onComplete()` | Publisher | Normal completion of the source |
| `onError(Throwable)` | Publisher | Termination due to an error |
| `close()` on `SubmissionPublisher` | Producer | Stops accepting new submissions; delivers completion to existing subscribers after already-submitted data |

A subscriber that wants to discard an HTTP response can call `cancel()`, but doing so may make the underlying HTTP connection **no longer reusable**. Therefore, you must define a policy: **read the entire body until `onComplete`/`onError`**, or proactively cancel and accept the cost of closing the connection.

Do not use `cancel()` as a guarantee that the server has definitely stopped sending, that a remote transaction has rolled back, or that all data in queues has been cleared. For business operations with side effects, use a separate protocol or mechanism to determine state.

## 4. SubmissionPublisher: a built-in backpressure-capable source in the JDK

`java.util.concurrent.SubmissionPublisher<T>` is a basic implementation of `Flow.Publisher<T>` available since Java 9. It typically uses an `Executor` to deliver signals asynchronously and maintains a per-subscriber buffer with a configurable capacity limit.

~~~java
// Java 17+ fragment, usable in an application with Executor lifecycle management.
ExecutorService executor = Executors.newSingleThreadExecutor();

try (SubmissionPublisher<String> publisher =
         new SubmissionPublisher<>(executor, 8)) {

    publisher.subscribe(subscriber); // Application-defined Subscriber<String>.

    publisher.submit("A");
    publisher.submit("B");
    publisher.close();
} finally {
    executor.shutdownNow();
}
~~~

This snippet only illustrates initialization and is **not** a standalone program: there is no `subscriber` or wait for asynchronous completion. With real workloads, shutting down the executor **immediately after `close()`** can prevent callbacks from finishing delivery. In the complete program in section 8, the code waits on a `CountDownLatch` signaling completion before shutting down.

### submit() vs. offer()

- `submit(item)` publishes to current subscribers according to `SubmissionPublisher`'s rules; when **a subscriber's buffer is full**, the call may **block** waiting for space. That is **backpressure on the producer**, not a non-blocking guarantee.
- `offer(item, ...)` supports handling full-buffer conditions (such as dropping or controlled retry), including a timeout variant. Dropping an item in an HTTP body stream can corrupt the request/response content; **do not use drop as a default strategy for body byte streams**.
- The value returned by `submit` is an **estimate of the lag** among subscribers, not the number of items delivered to the HTTP peer or bytes actually sent over the network.
- `SubmissionPublisher.close()` does not mean all subscribers have finished processing. Wait for `onComplete` or a downstream Future/latch if you need confirmation that the pipeline has finished.

Stall example: a producer sends 1,000 items very quickly, the subscriber only calls `request(1)` every few seconds, and the buffer limit is 8. Initially items can enter the queue, but once the queue fills up, `submit` can block. If the producer and consumer dispatch on **the same thread** and that thread blocks in `submit`, there is a risk of deadlock/starvation. Therefore, choose the right executor, queue, and throttling mechanism.

**Do not confuse buffer capacity with demand:** a publisher can have an internal queue even when the subscriber has not requested any items yet. Backpressure limits delivery to the subscriber rather than guaranteeing that upstream data is never buffered.

## 5. HTTP request: BodyPublisher is a Flow.Publisher<ByteBuffer>

In Java 17, `HttpRequest.BodyPublisher` has the following inheritance signature:

~~~java
// API concept from java.net.http; not a standalone runnable Java file.
interface BodyPublisher extends Flow.Publisher<ByteBuffer> {
    long contentLength();
}
~~~

This is an **abbreviated** signature to highlight the type relationship. A `BodyPublisher` has two responsibilities: providing body bytes via Flow and announcing the body length when known. `HttpClient` is the subscriber to the request `BodyPublisher`.

Common factories include:

~~~java
// Illustrative fragment, no network call in this snippet.
HttpRequest.BodyPublisher text =
        HttpRequest.BodyPublishers.ofString("Hello", StandardCharsets.UTF_8);

HttpRequest.BodyPublisher binary =
        HttpRequest.BodyPublishers.ofByteArray(new byte[] {1, 2, 3});

HttpRequest.BodyPublisher empty =
        HttpRequest.BodyPublishers.noBody();

HttpRequest.BodyPublisher streamed =
        HttpRequest.BodyPublishers.ofInputStream(() -> openInputStream());
~~~

`ofString` and `ofByteArray` are generally suitable for small payloads; `ofFile(Path)` or `ofInputStream(Supplier<InputStream>)` are appropriate when you do not want to hold the entire body in a `String` or `byte[]`. For an `InputStream` supplier, create a **new stream for each invocation** in case the client needs to retry the request; an already-exhausted `InputStream` usually cannot be replayed safely. `openInputStream()` in the fragment is an application-provided helper, not a JDK API.

### 5.1. The fromPublisher adapter

If you already have a `Flow.Publisher<ByteBuffer>`:

~~~java
// Fragment: application-provided publisher; actual bytes must match.
Flow.Publisher<ByteBuffer> source = makeByteBufferPublisher();

HttpRequest.BodyPublisher unknownLength =
        HttpRequest.BodyPublishers.fromPublisher(source);

HttpRequest.BodyPublisher knownLength =
        HttpRequest.BodyPublishers.fromPublisher(source, 1_024);
~~~

- `fromPublisher(source)` sets `contentLength() == -1` (unknown length). HTTP/1.1 can use a framing mechanism such as chunked transfer; HTTP/2 has its own framing. Do not manually insert a fake `Content-Length`.
- `fromPublisher(source, contentLength)` requires an **exact positive byte count**. Only use it when you can guarantee the source will emit that exact number of bytes—no more, no less.
- If the body is **empty**, use `BodyPublishers.noBody()` instead of passing length 0 to the length-taking overload, because the Javadoc specifies that the length passed to that overload must be **positive**.
- `BodyPublisher.contentLength()` may be queried multiple times and must return **a consistent value** across calls; do not make it depend on how many bytes remain to be read.

`HttpClient` may **re-subscribe** to the request `BodyPublisher` when it needs to resend a request (per redirect/authentication/retry policies). The publisher must be able to produce an **equivalent** new sequence for each subscription. A hot `SubmissionPublisher` that has already emitted data before `HttpClient` subscribes **does not automatically replay** those items; using it directly as an upload source can lose part of the body or fail to support resending. In real applications, you typically choose a **cold/replayable** publisher or a data source that can be reopened.

### 5.2. ByteBuffer ownership on the request side

The `HttpRequest.BodyPublisher` Javadoc requires that `ByteBuffer` instances be allocated by the publisher for each emission and **must not be accessed or modified by the publisher after being published to the HTTP Client**. Do not send a mutable `ByteBuffer` and then continue calling `put/clear/flip` on another thread:

~~~java
// Wrong ownership: a mutable buffer is modified after publishing.
ByteBuffer shared = ByteBuffer.allocate(1024);
// publisher.onNext(shared);    // Hypothetical method example.
shared.clear();                 // HTTP client may not have finished consuming it.
~~~

The snippet above is an **illustrative anti-pattern**, not a standalone runnable class. In a proper Publisher, each subscription has independent state; when emitting, create a valid buffer and hand over read ownership to `HttpClient`. If the shared data source can still change, copy the bytes or design clear ownership. Never let the publisher mutate a buffer after publication.

### 5.3. Streaming POST via Flow

~~~java
// Java 17+ fragment; uri and Flow.Publisher<ByteBuffer> source are already available.
HttpRequest upload = HttpRequest.newBuilder(uri)
        .header("Content-Type", "application/octet-stream")
        .POST(HttpRequest.BodyPublishers.fromPublisher(source))
        .build();

HttpResponse<Void> response = client.send(
        upload, HttpResponse.BodyHandlers.discarding());
~~~

This snippet is not standalone because `uri/source/client` are application components. Synchronous `send` **waits for the `HttpResponse` according to the `BodyHandler`**, while the publisher is subscribed to and driven by demand from the HTTP client. Using Flow does not automatically make the `send` call asynchronous for the calling thread. You can use `sendAsync` so the client thread does not block, with appropriate error/timeout/cancellation handling.

**`Content-Type` must still be accurate**: the publisher only emits bytes. If the bytes are JSON, use `Content-Type: application/json` per the API; if binary, use `application/octet-stream` or the agreed media type. Flow does not automatically serialize JSON or guarantee that the server accepts the method.

## 6. HTTP response: BodySubscriber receives List<ByteBuffer>, not a single ByteBuffer

The signature is crucial:

~~~java
// API concept from java.net.http, shown only to illustrate generics.
interface BodySubscriber<T>
        extends Flow.Subscriber<List<ByteBuffer>> {
    CompletionStage<T> getBody();
}
~~~

On the **response-receiving** side, `HttpClient` is the data source and `BodySubscriber` is the consumer. However, the item type is **`List<ByteBuffer>`**, not a single `ByteBuffer`. Each `onNext(batch)` may contain **one or more** buffers. Per the Java 17 Javadoc, the lists are **unmodifiable** and the `ByteBuffer` instances are **read-only**, and the order of the buffers corresponds to the byte order of the response.

Therefore:

~~~java
// Fragment for Flow.Subscriber<List<ByteBuffer>>.
@Override
public void onNext(List<ByteBuffer> batch) {
    for (ByteBuffer buffer : batch) {
        byte[] chunk = new byte[buffer.remaining()];
        buffer.get(chunk); // Reading is valid even though the buffer is read-only.
        processBytes(chunk); // Application helper.
    }
    subscription.request(1);
}
~~~

`buffer.get(chunk)` reads bytes and advances the buffer's local position. `buffer.put(...)` can throw `ReadOnlyBufferException`. If you need to pass buffers across another asynchronous pipeline, keep ownership and lifetime clear, or copy the needed bytes; the Javadoc guarantees `HttpClient` does not reuse delivered lists/buffers, but business code must still synchronize access to any shared state.

### 6.1. BodyHandlers.ofPublisher()

A streaming option:

~~~java
// Java 17+ fragment, client and request already initialized.
HttpResponse<Flow.Publisher<List<ByteBuffer>>> response =
        client.send(request, HttpResponse.BodyHandlers.ofPublisher());

Flow.Publisher<List<ByteBuffer>> bodyPublisher = response.body();
// MUST subscribe exactly once and either read completely or cancel.
bodyPublisher.subscribe(mySubscriber);
~~~

With `ofPublisher()`, `HttpResponse` can be returned **as soon as the response headers have been read**, while the response body **is still streaming**. This publisher **may only be subscribed to once**. A second subscription receives `onError(IllegalStateException)` per the JDK contract; do not treat it as a replayable source for multiple consumers.

To release the HTTP exchange's resources, you must **register exactly one subscriber** and then either:
- request data until `onComplete/onError`, or
- call `Subscription.cancel()` when you genuinely do not need the rest.

**Do not treat the return of `client.send(..., ofPublisher())` as proof that the body has been fully read.** Status and headers are available, but `onNext` callbacks continue afterward. If you forget to subscribe, or subscribe without requesting any items, the exchange may hold onto resources for a long time. With HTTP/1.1, cancelling mid-body can cause the connection to be closed and not reused; with HTTP/2, stream cancellation depends on the protocol and implementation.

### 6.2. What does request(1) count here?

For `BodyHandlers.ofPublisher()`:

~~~text
subscription.request(1)
    |
    +--> Allows at most 1 onNext(List<ByteBuffer>) call
            |
            +--> batch might contain buffer 1 (512 bytes)
            +--> batch might contain buffer 2 (2048 bytes)
            +--> ... total bytes are not fixed
~~~

Therefore, `request(1)` **does not mean receiving only one byte or exactly one network packet**. HTTP/1.1 chunks, HTTP/2 frames, socket reads, `ByteBuffer` instances, and Flow items have boundaries that **do not necessarily align**. Do not parse JSON, UTF-8, or individual messages by assuming one `onNext` equals one message.

If the body uses UTF-8, a multi-byte character can be split across buffers. When receiving buffers, use an incremental `CharsetDecoder` or accumulate enough bytes until a complete encoding unit is available; do not call `new String(chunk, UTF_8)` independently on every chunk and concatenate them if an encoding sequence can be split mid-character.

### 6.3. BodyHandlers.ofString/ofByteArray/ofFile/ofInputStream

| BodyHandler | Type of `response.body()` | Resource characteristics |
| --- | --- | --- |
| `ofString()` | `String` | Typically accumulates the entire body before returning; convenient for small responses |
| `ofByteArray()` | `byte[]` | Accumulates all bytes; can consume significant heap for large responses |
| `ofFile(path)` | `Path` | Writes the body to a file, avoiding holding the entire body in a `byte[]` |
| `ofInputStream()` | `InputStream` | Provides a stream for the caller to read later; must be fully read or closed |
| `ofPublisher()` | `Flow.Publisher<List<ByteBuffer>>` | Caller manages Flow subscriber, demand, and completion/cancel |
| `discarding()` | `Void` | Reads and discards the body per handler policy without storing content |

**Choose simplicity first:** when downloading a few KB of JSON, `ofString()` is reasonable. When downloading a multi-GB file, `ofFile(path)` can be used instead of writing a custom subscriber. `ofPublisher()` is useful when you need an online transform/parse pipeline, load regulation, or downstream Flow integration. Do not choose Flow just to make the code more complex.

### 6.4. BodySubscriber.getBody() and CompletionStage

`HttpResponse.BodySubscriber<T>` provides `CompletionStage<T> getBody()`. When this stage completes depends on **the type `T` and the subscriber**:

- If `T` is `String` or `byte[]` accumulating the whole body, the stage usually completes only after the body has been received and converted.
- If `T` is a streaming type such as `InputStream` or `Publisher<...>`, the stage may complete **before the entire body is read**, because the caller needs the stream/publisher to continue processing.

Do not confuse "the `CompletableFuture<HttpResponse<Publisher<...>>>` completed" with "the entire response body has been received." You must track the subscriber's completion separately if business logic needs to know whether all data has finished processing.

## 7. Good and bad HTTP Flow interaction examples

### 7.1. Subscriber does not request data: response stalls on the application side

~~~java
// Anti-pattern: nobody calls request() after onSubscribe.
public void onSubscribe(Flow.Subscription s) {
    this.subscription = s;
    // No request(1), so there is no demand for onNext.
}
~~~

A Flow-compliant Publisher does not emit `onNext` without demand. If you wait for data without ever requesting it, the application puts itself into a stalled state. Do not fix this with `Thread.sleep()`; grant demand or decide to cancel.

### 7.2. Requesting Long.MAX_VALUE: giving up demand control

~~~java
// May be fine for small sources, but removes Flow-level bounds.
public void onSubscribe(Flow.Subscription s) {
    this.subscription = s;
    s.request(Long.MAX_VALUE);
}
~~~

This is effectively unbounded demand. When a subscriber is slow but has been granted a huge number of items up front, downstream can be overloaded if the publisher/adapter keeps emitting quickly or intermediate stages buffer into queues. Choose a window based on your memory budget; even then, `request(1)` alone does not bound byte count if each item is large.

### 7.3. Storing everything in ByteArrayOutputStream: valid demo, not bounded memory

~~~java
// Fragment inside onNext; ONLY suitable for small bounded bodies.
for (ByteBuffer part : batch) {
    byte[] bytes = new byte[part.remaining()];
    part.get(bytes);
    collector.write(bytes, 0, bytes.length);
}
subscription.request(1);
~~~

Even when requesting one batch at a time, `ByteArrayOutputStream` **still grows unboundedly with the total response size**. This is **not** bounded-memory streaming at the application layer. The standalone program in section 8 intentionally accumulates a 10-byte response to demonstrate the API; when applying this to real large files, write to a bounded sink or process online and discard processed bytes.

### 7.4. Offloading heavy work to a worker queue must preserve backpressure

If `onNext` simply calls `queue.offer(batch)` and immediately calls `request(1)` with an unbounded queue, upstream still pushes faster than the consumer and memory grows. A better pattern:

~~~text
onNext(batch)
    |
    +--> validate size, copy/transfer data to a BOUNDED work queue
    |
    +--> worker finishes processing batch (ack)
              |
              +--> if not cancelled and capacity remains:
                         subscription.request(1)
              |
              +--> if processing fails:
                         cancel / fail pipeline / cleanup
~~~

A bounded queue may need to reject, wait, or apply additional backpressure; never block indefinitely inside a callback if that thread is also responsible for draining the queue, as that can deadlock. Serialize or synchronize `request`, `cancel`, and `close` calls to avoid races when multiple workers finish concurrently.

## 8. Standalone Java 17+ program: Flow + HTTP streaming

The program **`FlowHttpDemo.java`** has two clear test parts:

1. **Plain Flow:** `SubmissionPublisher<String>` with a subscriber using `request(1)`, receiving A then B and completing. Uses a `CountDownLatch` to wait for callbacks so stdout output is ordered.
2. **HTTP loopback:** a local server using `com.sun.net.httpserver.HttpServer` with a `/data` route returning `HELLO-FLOW` and an `/upload` route echoing POST bytes. The client uses `BodyHandlers.ofPublisher()` to read the GET response via `Flow.Subscriber<List<ByteBuffer>>`, and `BodyPublishers.fromPublisher(...)` to upload the four bytes `PING`.

The key learning point in the HTTP example is that the custom request publisher creates a **new subscription** for each subscribe call, returns a fresh `ByteBuffer`, and does not access the buffer after publication. This avoids using a hot source that could lose data before `HttpClient` subscribes.

**Save all of the code below into `FlowHttpDemo.java`:**

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
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicReference;

public class FlowHttpDemo {
    private static final java.nio.charset.Charset UTF8 =
            StandardCharsets.UTF_8;
    private static final long SECONDS = 5;

    private static void flowExample() throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch done = new CountDownLatch(1);
        AtomicReference<Throwable> error = new AtomicReference<>();

        try (SubmissionPublisher<String> publisher =
                     new SubmissionPublisher<>(executor, 8)) {

            publisher.subscribe(new Flow.Subscriber<String>() {
                private Flow.Subscription subscription;

                @Override
                public void onSubscribe(Flow.Subscription s) {
                    subscription = s;
                    System.out.println("flowSubscribed");
                    s.request(1);
                }

                @Override
                public void onNext(String item) {
                    System.out.println("flowNext=" + item);
                    subscription.request(1);
                }

                @Override
                public void onError(Throwable throwable) {
                    error.set(throwable);
                    done.countDown();
                }

                @Override
                public void onComplete() {
                    System.out.println("flowComplete");
                    done.countDown();
                }
            });

            publisher.submit("A");
            publisher.submit("B");
            publisher.close();

            if (!done.await(SECONDS, TimeUnit.SECONDS)) {
                throw new TimeoutException("Flow did not finish");
            }
            if (error.get() != null) {
                throw new IllegalStateException(
                        "Flow failed", error.get());
            }
        } finally {
            executor.shutdownNow();
        }
    }

    // Server-side HTTP response; for local demo only.
    private static void reply(HttpExchange exchange, String text)
            throws IOException {
        byte[] body = text.getBytes(UTF8);
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=UTF-8");
        exchange.sendResponseHeaders(200, body.length);

        try (OutputStream out = exchange.getResponseBody()) {
            out.write(body);
        }
    }

    // Cold/replayable Publisher: each subscription gets its own buffer.
    // Intended only for the 4-byte demo payload, not a production
    // multi-chunk/multi-consumer implementation.
    private static Flow.Publisher<ByteBuffer> singleChunk(
            byte[] source) {
        byte[] content = source.clone();

        return subscriber -> subscriber.onSubscribe(
                new Flow.Subscription() {
            private boolean terminated;

            @Override
            public synchronized void request(long n) {
                if (terminated) {
                    return;
                }
                terminated = true;

                if (n <= 0) {
                    subscriber.onError(new IllegalArgumentException(
                            "positive demand required"));
                    return;
                }

                // Each subscribe creates a new array/buffer.
                // After onNext, the Publisher must not modify it again.
                subscriber.onNext(
                        ByteBuffer.wrap(content.clone())
                                .asReadOnlyBuffer());
                subscriber.onComplete();
            }

            @Override
            public synchronized void cancel() {
                terminated = true;
            }
        });
    }

    private static void httpExample() throws Exception {
        InetAddress loopback = InetAddress.getByAddress(
                new byte[] {127, 0, 0, 1});

        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 0);

        server.createContext("/data", exchange -> {
            try (InputStream ignored = exchange.getRequestBody()) {
                reply(exchange, "HELLO-FLOW");
            }
        });

        server.createContext("/upload", exchange -> {
            byte[] body;
            try (InputStream in = exchange.getRequestBody()) {
                body = in.readAllBytes();
            }
            reply(exchange,
                    exchange.getRequestMethod() + ":"
                            + new String(body, UTF8));
        });

        server.start();
        try {
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .version(HttpClient.Version.HTTP_1_1)
                    .build();

            String base = "http://127.0.0.1:"
                    + server.getAddress().getPort();

            HttpRequest get = HttpRequest.newBuilder(
                    URI.create(base + "/data"))
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();

            // HttpResponse holds a body publisher, not a String.
            HttpResponse<Flow.Publisher<List<ByteBuffer>>> download =
                    client.send(
                            get,
                            HttpResponse.BodyHandlers.ofPublisher());

            CountDownLatch done = new CountDownLatch(1);
            AtomicReference<Throwable> failure =
                    new AtomicReference<>();
            ByteArrayOutputStream bytes =
                    new ByteArrayOutputStream();

            download.body().subscribe(
                    new Flow.Subscriber<List<ByteBuffer>>() {
                private Flow.Subscription subscription;

                @Override
                public void onSubscribe(Flow.Subscription s) {
                    subscription = s;
                    s.request(1); // One LIST per turn, not 1 byte.
                }

                @Override
                public void onNext(List<ByteBuffer> batch) {
                    for (ByteBuffer buffer : batch) {
                        byte[] chunk = new byte[buffer.remaining()];
                        buffer.get(chunk);
                        bytes.write(chunk, 0, chunk.length);
                    }
                    subscription.request(1);
                }

                @Override
                public void onError(Throwable error) {
                    failure.set(error);
                    done.countDown();
                }

                @Override
                public void onComplete() {
                    done.countDown();
                }
            });

            if (!done.await(SECONDS, TimeUnit.SECONDS)) {
                throw new TimeoutException(
                        "HTTP body did not finish");
            }
            if (failure.get() != null) {
                throw new IOException(
                        "HTTP response body failed", failure.get());
            }

            System.out.println(
                    "downloadStatus=" + download.statusCode());
            System.out.println(
                    "downloadText="
                            + new String(bytes.toByteArray(), UTF8));

            // Create a body publisher from a re-subscribable Flow source.
            byte[] payload = "PING".getBytes(UTF8);
            HttpRequest post = HttpRequest.newBuilder(
                    URI.create(base + "/upload"))
                    .timeout(Duration.ofSeconds(5))
                    .header(
                            "Content-Type",
                            "text/plain; charset=UTF-8")
                    .POST(HttpRequest.BodyPublishers.fromPublisher(
                            singleChunk(payload), payload.length))
                    .build();

            HttpResponse<String> upload = client.send(
                    post,
                    HttpResponse.BodyHandlers.ofString(UTF8));

            System.out.println(
                    "uploadStatus=" + upload.statusCode());
            System.out.println(
                    "uploadText=" + upload.body());

        } finally {
            server.stop(0);
        }
    }

    public static void main(String[] args) throws Exception {
        flowExample();
        httpExample();
    }
}
~~~

**Compile/run with JDK 17+** (no external libraries needed):

~~~bash
javac FlowHttpDemo.java
java FlowHttpDemo
~~~

The program uses the JDK module `jdk.httpserver`. In a self-managed module-path configuration, you may need `--add-modules jdk.httpserver` on the compile/run command; the standard JDK classpath/unnamed module usually resolves this module automatically.

**Verified output on loopback with JDK/JShell**:

~~~text
flowSubscribed
flowNext=A
flowNext=B
flowComplete
downloadStatus=200
downloadText=HELLO-FLOW
uploadStatus=200
uploadText=POST:PING
~~~

### Detailed walkthrough

- `flowSubscribed` arrives before any data. The subscriber calls `request(1)` and then receives A and B in turn. After each item, the subscriber grants one more receive allowance. `SubmissionPublisher.close()` triggers completion after the delivered items; `CountDownLatch` ensures `main` only proceeds once finished.
- The HTTP GET returns `statusCode()==200` and a body Publisher; the application's subscriber uses `request(1)` on **`List<ByteBuffer>`**. Regardless of how many lists/chunks the HTTP client splits `HELLO-FLOW` into, the code concatenates the **bytes in exact order** before decoding UTF-8, so it does not depend on network chunking.
- `singleChunk(payload)` creates a new Flow source for each subscription. Because the payload is 4 bytes long, `fromPublisher(..., payload.length)` has an exact content length of 4. The server echoes the method and body as `POST:PING`.
- Both endpoints run only on `127.0.0.1` and an ephemeral port so no Internet or API key is needed. `HttpServer` only echoes/returns fixed data; it is **not a production server**.
- The program intentionally uses `ByteArrayOutputStream` to easily print a 10-byte response; **do not infer that the download demo has bounded memory for arbitrary responses**. For large files, use `BodyHandlers.ofFile()` or design a bounded streaming sink that grants demand after the sink completes.

**About chunk counts:** the demo does not print the number of `onNext` calls, because the HTTP client may split `List<ByteBuffer>` differently depending on runtime/protocol/network. The output relies only on the assembled body and status, which are more reliable observations in a normal loopback test environment.

### Notes on the demo's request Publisher

`singleChunk` is a minimal example for **exactly one single item**: one `request(n>0)` allows sending that item and then completing. It does not represent all concerns of a general-purpose publisher such as emitting multiple batches, multi-threaded callback synchronization, streaming from disk, retries, cancel races, or time limits. Production code should use built-in `BodyPublishers` or a Reactive Streams–compliant library and verify replayability.

Although `request(n)` in the demo can emit immediately on the thread calling `request`, the program is still valid for the single-item subscription idea. This also illustrates why a custom publisher must **tolerate reentrancy**; never assume every signal always runs on a separate executor thread. Complex publishers must serialize signals and avoid holding locks while invoking user callbacks to reduce deadlock risk.

## 9. True streaming subscriber example with a bounded sink

To avoid accumulating the entire body on the heap, process each batch and discard processed bytes. One way to download a file is `BodyHandlers.ofFile(path)` without managing Flow yourself. If the problem requires a custom transform/parser, you must decide what happens when downstream is slow.

Suppose the application writes the body to a file output stream with a 20 MB total limit:

~~~java
// Fragment inside a Flow.Subscriber<List<ByteBuffer>>;
// requires an open OutputStream out, Flow.Subscription subscription,
// long totalBytes, boolean terminal, and cleanup helpers.
private static final long MAX_BYTES = 20L * 1024 * 1024;

@Override
public void onNext(List<ByteBuffer> batch) {
    try {
        for (ByteBuffer part : batch) {
            int n = part.remaining();
            if (totalBytes + n > MAX_BYTES) {
                subscription.cancel();
                closeOutputAndReportTooLarge();
                return;
            }
            byte[] chunk = new byte[n];
            part.get(chunk);
            out.write(chunk);
            totalBytes += n;
        }
        // After downstream write of the batch completes.
        subscription.request(1);
    } catch (IOException error) {
        subscription.cancel();
        closeOutputAndReportFailure(error);
    }
}
~~~

This is a **fragment**, not a standalone compilable class; `closeOutputAndReportTooLarge/Failure` are application helpers. `totalBytes + n` must guard against integer overflow if `n` is not reasonably bounded; checking `n > MAX_BYTES - totalBytes` is safer. Every terminal path (`onComplete`/`onError`/`cancel`) must close the output exactly once; handle exceptions in callbacks and do not request more after `cancel`.

**Important:** `out.write(chunk)` is a **blocking** operation. Calling it directly inside the HTTP client's `onNext` with a slow file/network sink can hold the dispatch thread and affect other exchanges. Depending on requirements, solutions include: using `BodyHandlers.ofFile(path)`, using a bounded worker queue with ack before the next request, or designing an asynchronous sink with proper ownership.

When handing data off to a worker queue, do not pass mutable `ByteBuffer` positions that are modified concurrently on two threads. In Java's `HttpClient`, received buffers are read-only so they cannot be written to, but each object's position is still mutable; avoid having multiple threads call `get` on the same instance without coordination. Use `asReadOnlyBuffer()` to create an independent position view or copy bytes within bounds if needed.

## 10. Item demand does not replace resource limits

Suppose the HTTP response publisher emits `List<ByteBuffer>`, where each batch can contain multiple buffers with varying total bytes:

| Demand | Assumed batch size | Maximum bytes from the demanded items themselves |
| --- | --- | --- |
| `request(1)` | 1 batch, 2 KB | Around 2 KB for that batch |
| `request(1)` | 1 batch, 512 KB | Around 512 KB for that batch |
| `request(8)` | 8 batches, 1 MB each | Could reach around 8 MB |
| `request(Long.MAX_VALUE)` | Unbounded item count | No byte budget from Flow demand |

These sizes are **illustrative assumptions**, not a promise that `HttpClient` will emit batches of those sizes. Each stage needs additional controls:

- **Bytes per item:** cap abnormally large payloads.
- **Total response bytes:** check `Content-Length` if present, but do not blindly trust the header; count actual bytes received.
- **Internal queues:** bounded queues, max in-flight items/bytes, reject or cancel on overload.
- **Processing time:** overall timeouts/deadlines; a slow consumer can hold an HTTP connection open for a long time.
- **Concurrent requests/connections:** per-response Flow does not automatically limit the number of HTTP requests or total resources across multiple flows.
- **Ownership and resource leaks:** normal completion must drain; on abort, must cancel/close.

Flow demand guarantees **no more `onNext` calls than allowed** in a valid subscription. It does **not** guarantee fixed RAM usage, because per-item size, upstream/downstream buffers, and application-retained data are separate factors.

## 11. What backpressure layers exist when processing HTTP content?

Consider a flow:

~~~text
Producer application
      |
      | (1) Flow demand: request(n) ByteBuffer items
      v
HttpRequest.BodyPublisher
      |
      | (2) Buffering/framing in HttpClient
      v
HTTP/1.1 or HTTP/2
      |
      | (3) TCP socket buffer and TCP receive window,
      |     HTTP/2 flow control if applicable
      v
Proxy / server / network
      |
      | (4) HTTP client response BodySubscriber<List<ByteBuffer>>
      v
Downstream Subscriber application
      |
      | (5) Queue, file, DB, parser, consumer
      v
Processing complete
~~~

Backpressure at the Flow layer can slow down the producer when downstream stops requesting more, but it must pass through **buffers and schedulers** at each layer. For example, the server may have already sent some data into the TCP send buffer before the client pauses requesting items. HTTP/2 uses protocol-level flow-control windows, yet the application still cannot assume one `request(1)` corresponds to one `WINDOW_UPDATE` or one single TCP read. With HTTP/1.1, slow reading can cause the TCP receive window to throttle the sender **over time**, not instantaneously and not with absolute precision.

The design goal is **end-to-end bounded work**, not "just add `request(1)` and call it done." If any stage receives items and stores them in an unbounded list, backpressure is broken at that stage.

## 12. Flow.Processor: transforming data while preserving demand

`Flow.Processor<T,R>` is simultaneously a `Subscriber<T>` (receiving upstream data) and a `Publisher<R>` (emitting downstream). Use it when you need to decode/transform or filter data, while properly propagating demand.

~~~text
Publisher<ByteBuffer> -> Processor<ByteBuffer, ParsedEvent>
                                   |
                                   v
                           Subscriber<ParsedEvent>
                                  request(n)
                                   |
                       Processor decides when to
                       request more from upstream
~~~

A broken processor might:
- Request `Long.MAX_VALUE` upstream and buffer everything while downstream only calls `request(1)`, causing memory growth.
- Send `onNext` downstream without sufficient demand.
- Arbitrarily drop bytes/items, corrupting the HTTP payload.
- Call upstream `request` inside a callback while holding a lock, causing reentrancy/deadlock.

Therefore, do not build a custom processor to parse large JSON bodies unless genuinely needed; use a reputable streaming parser and design bounded queues/acks. When parsing line-delimited JSON/NDJSON, remember that HTTP chunks do not align with line boundaries; the parser must retain incomplete bytes across batches and only emit an event once a complete frame is available.

## 13. Common mistakes and how to fix them

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| `onSubscribe` ran, but `onNext` never arrives | Subscriber has not called `request(n>0)`, or upstream has no data yet | Grant proper demand; measure readiness and upstream state |
| `request(0)` throws an error | Demand must be positive | Do not use 0 to pause; stop requesting more |
| Flow subscriber receives `List<ByteBuffer>` but code casts to `ByteBuffer` | Wrong generic type for response `BodySubscriber` | Iterate through each buffer in the batch |
| Request body publisher uses `Flow.Publisher<List<ByteBuffer>>` | Wrong on request side: `BodyPublisher` emits individual `ByteBuffer`s | Provide `Flow.Publisher<ByteBuffer>` |
| Uploaded body misses bytes on retry | Using a hot/non-replayable publisher or an exhausted stream | Create a fresh source per subscription/retry; verify `contentLength` |
| Wrong `Content-Length` | Counting characters instead of bytes, or source emits too few/many | Use a publisher with accurate byte length; do not set the header manually |
| Large response download still OOMs despite `request(1)` | Application stores all bytes in an unbounded `ByteArrayOutputStream`/`List` | Process per chunk, release, use `ofFile` or a bounded sink |
| `send(... ofPublisher)` returns but logic is not done | Response only needs headers first; body streaming is still running | Wait for downstream `onComplete`/`onError` with a deadline |
| Second subscriber to `ofPublisher()` fails | Response publisher only allows subscribing once | Use a single consumer or build controlled/bounded multicast |
| Callbacks still arrive in-flight after `cancel()` | Cancel is best-effort | Keep state idempotent, avoid double cleanup, ignore late items |
| `SubmissionPublisher.submit` "hangs" | Buffer for a slow subscriber is full | Use a bounded executor/queue; do not block on the consumer's own thread |
| `SubmissionPublisher.offer` corrupts file | Items are being dropped | Do not drop body stream data; use backpressure/timeout/error |
| Increasing `request(1000)` does not increase throughput | Bottleneck in network, disk, CPU, server, or overhead | Measure with metrics; tune window in a controlled manner |
| UTF-8 is corrupted when receiving chunks | Multi-byte character split across `ByteBuffer`s | Retain partial bytes or use a streaming decoder |
| Subscriber `onNext` throws an exception | Processing/IO error in callback | Catch, cancel/close per policy, report error once |
| HTTP connection is not reused | Body was not fully consumed or was cancelled mid-stream | Drain body when appropriate; accept connection close on cancel |

### 13.1. No data arrives after subscribing

First check whether `onSubscribe` was called, whether you stored the `Subscription` properly, whether you requested a positive number, and whether the publisher has data. Do not diagnose "slow network" before verifying that the application itself has **demand**. In HTTP, remember that a second `ofPublisher` subscriber is always rejected; log subscriber lifecycle events for the right exchange.

### 13.2. Publisher emits more than demand

A custom publisher must track total demand **per subscription** and serialize signals. Do not call `onNext` unconditionally in a file/network read loop, as that can violate Flow. Use standard `BodyPublishers` whenever possible; if writing your own, test `request(1)`, cumulative requests, `0`/negative requests, cancel races, multiple subscribers, reentrant requests, and error paths.

### 13.3. Why shouldn't you make a long-running DB request inside onNext?

`onNext` may run on the dispatch/callback thread of the Publisher or `HttpClient`. A long blocking operation can affect other subscriptions and slow down the entire pipeline. If DB work is needed, offload it to a separate **bounded** executor; only request the next batch when the corresponding work completes and the queue still has capacity.

### 13.4. Pitfalls of rolling your own fan-out

If one Publisher has three subscribers, each subscriber has different demand and buffers. One slow subscriber can cause `SubmissionPublisher.submit` to block because its own buffer is full; the entire source's throughput can be affected. Do not assume Flow automatically multicasts with fair/independent handling or drops slow subscribers without an explicit policy.

### 13.5. Does cancellation cancel the request on the server?

Not necessarily. The HTTP client may stop reading/sending data and close the stream/connection, but the server may have already received, validated, written data, or committed the operation beforehand. In particular, a payment/upload POST with business side effects may have already executed. To know the outcome, use a request ID, idempotency key, business status checks, and retry policies—do not rely on `cancel()`.

## 14. Production rules for safe HTTP streaming

A real-world pipeline should explicitly define:

1. **Max body bytes:** cap total download/upload bytes; do not rely solely on the peer-announced `Content-Length`.
2. **Max in-flight bytes/items:** each subscriber keeps outstanding items small and caps each item's size; bounded queues throughout the pipeline.
3. **Deadlines:** connect timeout, request timeout, processing/sink wait timeout; prolonged slowness must not hold sockets/workers indefinitely.
4. **Error propagation:** upstream error → notify downstream/cancel and close resources; downstream error → stop requesting, cancel upstream, fail the corresponding task.
5. **Idempotent termination:** complete the future/latch/request only once; `onError` and `onComplete` never occur together; late signals may still arrive after cancel.
6. **Demand policy:** batch requests based on throughput and byte budget, not hardcoded `Long.MAX_VALUE` at every stage.
7. **ByteBuffer ownership:** for requests, the publisher does not modify buffers after handing them to `HttpClient`; for responses, lists and buffers are read-only; if passing to workers, manage position/threading properly.
8. **Replayable uploads:** prepare `BodyPublisher` for resends and verify accurate `contentLength()`; if not replayable, configure retry/redirect accordingly and handle failures explicitly.
9. **Charset/framing:** assemble/decode data by bytes; do not assume one `onNext` equals one JSON line or one UTF-8 code point.
10. **Resource cleanup:** with `ofPublisher()`, subscribe once and consume to a terminal signal or cancel; with `InputStream`/Stream/File, close per the API.
11. **Security:** TLS/hostname verification, proper auth, no token logging, body limits to prevent zip bombs/decompression bombs if decompressing, and avoid parsing unvalidated input.
12. **Observability:** record bytes received/sent, outstanding demand, queue depth, buffer usage, wait time, cancellations/errors, HTTP status/latency, and concurrency; do not log sensitive payloads.

Merely calling `request(1)` without bounding **payload size and total response length** is not enough. Application resources are consumed according to **bytes × number of flows × hold duration**, not just by the number of `onNext` calls.

## 15. Self-check questions

**Q1.** Does `Flow.Subscription.request(3)` mean requesting three more bytes?  
**A:** No. It grants demand for at most three more **items/`onNext` calls**. An item may be a `ByteBuffer` or `List<ByteBuffer>` with a non-fixed byte size.

**Q2.** You call `request(2)`, receive one item, and then call `request(4)`. What is the remaining demand?  
**A:** Initially 2, consuming 1 leaves 1, plus 4 makes **5 items**, assuming no other items or signals intervened.

**Q3.** If a Subscriber does not call `request` after `onSubscribe`, may the Publisher validly emit `onNext`?  
**A:** It must not exceed the demand of 0. The Subscriber must request a positive number if it wants data; do not use `request(0)` to pause.

**Q4.** Is `request(0)` a "pause"?  
**A:** No. Per the Flow contract, it must result in `onError(IllegalArgumentException)`; pause by simply not requesting more yet.

**Q5.** Why is `HttpRequest.BodyPublisher` a `Publisher<ByteBuffer>` while `HttpResponse.BodySubscriber<T>` is a `Subscriber<List<ByteBuffer>>`?  
**A:** Those are two different JDK generic contracts: the request side emits individual `ByteBuffer`s; on the response side, `HttpClient` emits **lists of `ByteBuffer`s** (batches). Do not force one form into the other.

**Q6.** When `BodyHandlers.ofPublisher()` returns an `HttpResponse`, can you assume the entire body has finished downloading?  
**A:** No. Headers may be complete while the body is still streaming. The Subscriber must receive until `onComplete`/`onError` or `cancel`.

**Q7.** Can a single `ofPublisher()` response be subscribed to by two independent consumers?  
**A:** No. The returned Publisher allows only one subscription; a second subscription receives an error. If you need two consumers, build your own throttled/bounded fan-out.

**Q8.** Does `HttpRequest.BodyPublishers.fromPublisher(source, 1024)` mean the body is 1,024 characters long?  
**A:** No. It means exactly **1,024 bytes**, and the publisher must emit that exact amount. Do not use `String.length()` in place of UTF-8 byte count.

**Q9.** Why can a hot `SubmissionPublisher` be a poor choice for HTTP upload retries?  
**A:** Data sent before the HTTP client subscribes is not replayed to a new subscriber; a resent request may not receive the same body. You need a fresh/replayable source per subscription.

**Q10.** Does `cancel()` guarantee that `onComplete()` will be called?  
**A:** No. Cancellation is best-effort; after cancel, no terminal signal is required and already-scheduled signals may still arrive.

**Q11.** With `request(1)`, is the application guaranteed not to use much RAM?  
**A:** No. A single item can be very large; queues in other stages or a collector accumulating the entire response may be unbounded.

**Q12.** When should you use `BodyHandlers.ofFile()` instead of `ofPublisher()`?  
**A:** When you only need to download a large response to a file using a built-in API, without needing custom transforms or Flow processing. It is usually simpler and less error-prone.

**Q13.** If a Vietnamese character is split across two `ByteBuffer`s received from HTTP, what should you do?  
**A:** Assemble the bytes properly or use an incremental `CharsetDecoder`; do not decode each fragment as an independent string and concatenate them.

**Q14.** Can `SubmissionPublisher.submit(item)` block?  
**A:** Yes. When a subscriber's buffer is full and downstream is slow, `submit` can block waiting for space. `offer` can drop according to policy, which is unsuitable for automatically discarding body bytes.

**Q15.** Once `onNext` has placed a batch onto a worker queue, should it immediately request the next one?  
**A:** Only if the queue is bounded/has capacity and end-to-end backpressure remains intact. If you keep requesting unboundedly before processing finishes, downstream can OOM.

**Q16.** When is `Flow.Processor<T,R>` used?  
**A:** When you need a stage that both consumes upstream and emits downstream, such as parsing bytes into events; it must propagate demand, preserve ordering, and manage buffers/timeouts.

## 16. Official documentation

- Java SE 17 — `Flow` and examples of demand and batch requesting: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.html
- Java SE 17 — `Flow.Publisher`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.Publisher.html
- Java SE 17 — `Flow.Subscriber`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.Subscriber.html
- Java SE 17 — `Flow.Subscription.request/cancel`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.Subscription.html
- Java SE 17 — `SubmissionPublisher`, `submit/offer/close`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/SubmissionPublisher.html
- Java SE 17 — `HttpRequest.BodyPublisher` (Flow.Publisher<ByteBuffer>): https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublisher.html
- Java SE 17 — `HttpRequest.BodyPublishers.fromPublisher` and replayable sources: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html
- Java SE 17 — `HttpResponse.BodySubscriber<T>` (Flow.Subscriber<List<ByteBuffer>>): https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscriber.html
- Java SE 17 — `HttpResponse.BodyHandlers.ofPublisher/ofFile/ofInputStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html
- Java SE 17 — `HttpResponse.BodySubscribers.ofPublisher/fromSubscriber`: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html
- Java SE 17 — `HttpClient`, `send/sendAsync`: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
