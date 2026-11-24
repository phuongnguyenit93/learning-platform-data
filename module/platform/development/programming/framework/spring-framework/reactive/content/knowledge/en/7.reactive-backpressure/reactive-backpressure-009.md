# Throttling Limits Across HTTP, Network Buffers, and the Client

**Topic:** Spring Framework Reactive — **Backpressure**.

Reactive Streams allows a `Subscriber` to signal demand via `Subscription.request(n)`, ensuring a compliant `Publisher` does not send more elements than requested. However, an HTTP response must pass through **codecs, the HTTP server's write queue, OS socket buffers, the network, proxies, and client-side libraries**. At these boundaries, flow control can shift from **element counting** to **byte counting**, pass through separate buffers, be translated into different transport signals, or stop propagating directly back to the original producer.

Therefore, the design question in Spring WebFlux is not just "Does `Flux` have backpressure?", but: **when a client reads slowly, where is data sitting, which buffers are bounded, who can slow down the emitting source, and what happens when every limit hits its threshold?**

This article clearly distinguishes what Reactive Streams guarantees, what HTTP/TCP can throttle, what the client truly controls, and how to handle streaming applications safely when clients are slow or disconnect.

## 1. Key Boundary: `request(n)` Is Not an HTTP Message

In Reactive Streams, each `Subscription` connects **one Publisher with one Subscriber**. The Subscriber calls `request(n)` to announce it is allowed to receive up to `n` more `onNext` signals. The basic contract:

- `request(n)` is **element-count demand**, not bytes/second, HTTP frames, or TCP packets.
- The Publisher must not emit more `onNext` signals than total unused demand. It may emit fewer and complete.
- `cancel()` requests stopping the subscription; whether it reaches I/O, the producer, or external resources depends on the adapter/source.
- Operators such as `buffer`, `publishOn`, `flatMap`, and `limitRate` can **change the request volume sent upstream**; the final subscriber's request does not necessarily pass untouched through each operator.
- Backpressure is only guaranteed across **components that actually support/honor the protocol**. Hot callback APIs, external systems, or producers with internal queues are not automatically throttled merely because Java receives a `Flux`.

**Standard HTTP has no standard header or frame meaning "Reactive Streams requests the next 10 Java objects".** HTTP adapters may coordinate demand with read/write readiness and transport byte consumption, yet that process is an internal mechanism depending on the server, client, codec, and protocol.

For example, downstream calls `request(5)` on a `Flux<Order>`:

- Reactor can grant permission to emit five **`Order`** objects along one pipeline segment.
- The codec encodes five objects into JSON, NDJSON, or SSE events; each object has a different byte size.
- Netty may enqueue bytes into its outbound write queue; the kernel may accept bytes into the socket buffer even before the browser renders anything.
- TCP or HTTP/2 may prevent the sender from sending more **bytes** when the receiver's receive window is full.
- The browser may have already received all bytes while JavaScript is still processing slowly.

Thus, `request(5)` **is not equivalent** to "the client has finished processing five orders". Even a successful socket write does not mean the client application has parsed, rendered, persisted, or business-acknowledged the data.

## 2. Which Layers Does an HTTP Data Stream Cross?

```text
APPLICATION / REACTIVE STREAMS                   TRANSPORT / CLIENT
┌─────────────────┐
│ DB / message bus│  May be a source with/without its own slowdown mechanism
└────────┬────────┘
         │ event
         ▼
┌────────────────────────┐
│ Flux and operators     │  request(n), queues, prefetch, drop/error
└────────┬───────────────┘
         ▼
┌────────────────────────┐
│ HTTP codec / DataBuffer│  turns elements into bytes, may batch/buffer
└────────┬───────────────┘
         ▼
┌────────────────────────┐
│ Netty outbound queue   │  writable / non-writable; watermarks
└────────┬───────────────┘
         ▼
┌────────────────────────┐
│ Kernel TCP send buffer │  receives bytes before client app reads
└────────┬───────────────┘
         │ TCP flow control / congestion; HTTP/2/3 if used
         ▼
┌────────────────────────┐
│ Reverse proxy / CDN    │  may buffer, compress, open/close separate connections
└────────┬───────────────┘
         ▼
┌────────────────────────┐
│ Client receive buffers │  kernel, HTTP client, decoder, event queue
└────────┬───────────────┘
         ▼
┌────────────────────────┐
│ Consumer / browser UI  │  callbacks, rendering, persistence, business logic
└────────────────────────┘
```

The diagram is a **model of potential boundaries**, not a claim that every deployment has all these separate queues or the exact same data-copy sequence. With a reverse proxy, there are **two distinct network connections** and two separate transport flow controllers. Some codecs/transports use pooling or zero-copy, yet you still must answer **who owns and bounds memory and resources**.

At each layer, one of four actions can happen: **slow down**, **wait/bounded buffer**, **drop data per policy**, or **signal error/close connection**. No system is guaranteed safe if every layer chooses "unbounded buffering".

## 3. Four Backpressure Concepts Easily Confused

| Layer | Flow-Control Signal | Unit | Scope and Limits |
|---|---|---|---|
| **Reactive Streams** | `request(n)` / `cancel()` | `onNext` count | Only on the Publisher–Subscriber link; operators may transform requests |
| **Netty / application transport** | Writability, `Channel.isWritable()`, write queue | Bytes / buffers / writability | Depends on channel, codec, watermarks, and adapter; may still hold queued data |
| **TCP** | Receive window, ACK, and congestion control | Bytes sent/received on connection | Receiver throttles byte rate; has no notion of items, JSON, or render state |
| **HTTP/2** | `WINDOW_UPDATE` per stream and connection | DATA frame bytes | **Hop-by-hop** flow control, independent of `request(n)` logic; HTTP/3 uses QUIC flow control |

Another layer is **business-level throttling**, such as a client only being allowed 100 notifications/second or keeping only the latest snapshot. That is an application decision and cannot be deduced from TCP windows or `request(n)`.

### Item Units and Byte Units Cannot Convert 1:1

A single `onNext` can be:

- An `Order` object encoded into 200 bytes.
- An object with a long description field producing 2 MB of JSON.
- A `DataBuffer` carrying a chunk of bytes.
- A list of 10,000 items that itself is only **one `onNext`**.

Therefore, a limit of "at most 100 elements" does not automatically equal "at most 100 KB". If OOM is the main risk, bound **payload size, total bytes, connection count, and queues** in addition to element counts.

## 4. HTTP/1.1, HTTP/2, and HTTP/3 Throttle Differently

### 4.1. HTTP/1.1 over TCP

HTTP/1.1 does not define `Reactive Streams request(n)` on the wire. When the server streams a response:

1. Application emits data; HTTP encoder produces bytes.
2. Netty/kernel attempts to write bytes to the socket.
3. The receiver advertises a TCP window indicating how many more bytes it can accept; the network is also subject to congestion control.
4. If the client does not drain bytes fast enough, buffers can fill and eventually the writing side becomes constrained / unable to advance immediately.

However, **the server can write successfully into the kernel send buffer long before the client consumer processes the item**. Even when the server sees "write completed", that may only mean a lower layer accepted the data, not that the client application received and acknowledged it.

HTTP/1.1 can send a chunked response to deliver bytes incrementally, yet chunk boundaries **do not equate** to one reactive item or one JavaScript callback invocation. Proxies and codecs may split/coalesce bytes differently.

### 4.2. HTTP/2: Flow Control on Stream and Connection

HTTP/2 defines `WINDOW_UPDATE` so the receiver grants permission to send more **DATA frame bytes**. There are two windows:

- **Per-stream window**: limits DATA allowed to be sent for a specific HTTP/2 stream.
- **Per-connection window**: limits total DATA allowed across the connection carrying multiple streams.

The sender must respect **both**. RFC 9113 specifies **hop-by-hop** flow control; proxies do not forward a client's `WINDOW_UPDATE` untouched back to the origin like an end-to-end `request(n)`.

Model example (not an application default config value): a stream has 8 KiB of credit left, and the connection has 20 KiB of credit. If the server wants to send 12 KiB of DATA for that stream, it cannot exceed the stream's remaining 8 KiB credit; it must wait for a window update or send only what fits. Once sent, client JSON parsing is still a separate layer.

RFC 9113 sets an initial window of 65,535 bytes for both new streams and connections, though endpoints can adjust it via protocol mechanisms. **Do not use this number to infer actual WebFlux memory usage**: codecs, Netty buffers, socket buffers, and proxies also exist.

### 4.3. HTTP/3 / QUIC

HTTP/3 runs over QUIC. QUIC has its own flow control for **streams** and **connections**, also throttling bytes; it does not carry Reactive Streams `request(n)`. How limits work and map to application APIs depends on the transport and implementation. When debugging, identify the actual negotiated protocol; an `https://` URL does not by itself tell you HTTP/1.1, HTTP/2, or HTTP/3.

**Conclusion at this boundary:** the transport can propagate slowdown upward to the application, yet **there is no guarantee that the number of items processed at the client maps accurately to Publisher demand on the server**.

## 5. Netty Write Queues and Watermarks Are Not Unbounded Buffers

Reactor Netty is a non-blocking, backpressure-ready transport commonly used for Spring WebFlux. Underneath, Netty manages `Channel` writability. `WriteBufferWaterMark` has a **high** and **low** level:

- When bytes queued in the write buffer exceed the high watermark, `Channel.isWritable()` can flip to `false`.
- Once queued bytes drop below the low watermark, the channel can flip back to `true`.
- This is a **writability signal**, not a promise that every written byte reached the browser or an unbreakable **hard cap** on total memory.

Participating layers can include Netty's outbound queue, direct/pooled `ByteBuf` memory, TLS buffers, kernel send buffers, and proxies. Do not inspect Java heap alone and conclude the system is under no pressure: direct memory and network buffers can grow as well.

**Distinguish high/low watermarks from a memory limit:** Watermarks generally signal the producer/transport to pause pushing more data into the channel. A single large write, previously queued data, or buffers at other layers can still consume substantial memory. Application budgets must sum all places that can hold bytes, not just one watermark.

In implementation terms, the degree and manner in which Reactor Netty translates writable signals across Reactive Streams depend on the adapter/version and I/O type. Do not assume every `Flux<T>` response has a perfect, unit-identical throttling chain all the way from the browser back to the database.

## 6. Proxies, Load Balancers, and CDNs Can Break End-to-End Assumptions

A common architecture:

```text
WebFlux server
  └── TCP/HTTP connection #1
            ▼
      Reverse proxy
      [response buffer]
            ▼
  └── TCP/HTTP connection #2
Browser / mobile app
```

Suppose the proxy receives data from the server very quickly while sending to the browser very slowly. While space remains, the proxy can keep reading from the origin, leaving the origin server unaware of any pressure from the browser. Only when the proxy hits memory/disk/policy limits can it slow down the origin or close the connection. Depending on configuration, a proxy may also:

- **Buffer all or part of the response**, delaying per-event streaming.
- **Compress/batch**, changing when bytes actually reach the client.
- **Time out** idle connections, limit concurrent connections, or cap response size.
- **Retry** requests under certain conditions; with streaming or side effects, retries must obey idempotency contracts.
- Translate client-side HTTP/2 to origin-side HTTP/1.1, making flow control differ across the two hops.

Therefore, when testing a "slow browser", determine whether requests pass through an ingress, proxy, gateway, service mesh, or CDN. Testing directly against localhost alone does not evaluate the full production path.

### Impact on SSE and NDJSON

- **SSE (`text/event-stream`)** frames events for continuous client processing; misconfigured proxy buffering can hold multiple events before flushing.
- **NDJSON (`application/x-ndjson`)** separates JSON objects by newline, well-suited for streaming multiple items.
- **A large JSON array (`application/json`)** can be encoded incrementally on the server in some setups, yet some codecs/clients parse whole documents and may buffer large amounts of data before the application sees an item.
- Streaming encoding does not guarantee **every item is flushed and received independently and instantaneously**. Chunk boundaries, TLS records, HTTP frames, and client-side events can differ.

Choosing a media type is part of streaming design; it does not replace verifying buffering from server through proxy to client.

## 7. Slow Client Reading: Slow HTTP Client Differs from Slow Business Processing

A client can be slow at multiple places:

| Slow Location | What Can Be Observed | What Cannot Be Inferred |
|---|---|---|
| Network/client not reading socket | TCP/QUIC flow control may throttle further bytes | Cannot tell after how many exact items upstream publisher stopped |
| HTTP client/decoder reads socket but parses slowly | Library buffers and decoding pressure grow | Server may not immediately see client as "slow" |
| Browser received event but JS callback is busy | Event queue, UI lag, and page memory grow | Does not automatically make server receive `request(0)` |
| App parsed data but local DB write is slow | Client-side work queue grows | Cannot treat TCP window as business acknowledgment |
| Proxy reads origin fast but sends to browser slowly | Proxy-side buffer grows | Origin server may think downstream is still fast |

#### Browser `EventSource`

`EventSource` opens an SSE connection and dispatches events to JavaScript. This API does not expose `Subscription.request(n)` for the web page to ask for "three more events". A slow JavaScript callback **is not an end-to-end credit mechanism**. If event volume is too high, rate-limit events, send **latest snapshots** instead of every change, or implement application-level acknowledgment/resync when events are dropped.

#### Fetch / Streams API

With `fetch()` and `ReadableStream`, JavaScript can pull chunks via `getReader().read()`. This gives explicit control over consumption in the client and can indirectly exert pressure on underlying buffers. Still, one `read()` operates on the browser's byte/chunk stream, **not 1:1 with server-side `Flux.request(1)`**.

#### Java Reactive `WebClient`

A `WebClient` can expose a `Flux<T>` for the response body. A subscriber with finite demand can slow down how fast decoded objects are handed downstream. However, the network connector and codec can still buffer data and apply their own prefetching; `limitRate(8)` does not promise the server only sent eight objects or that only eight objects exist in total memory across both machines.

## 8. Inbound HTTP Requests: Client → Server Backpressure

It is not only responses that face this issue. For uploads or streaming request bodies:

```text
Client producer → client HTTP encoder/socket
→ network/proxy → server HTTP decoder → Flux<DataBuffer> / Flux<T>
→ handler/service
```

When the server processes a request body slowly, the transport can pause reading more bytes for a time if read-throttling is supported. Yet if the client/proxy has already sent substantial data ahead and each layer has its own buffer, memory can still rise. Set bounds on **request size, element size, concurrent requests, timeouts, codec aggregation, and downstream resources**.

Example WebFlux controller ingesting continuous NDJSON (snippet inside a Spring Boot WebFlux project):

```java
@PostMapping(path = "/events",
        consumes = MediaType.APPLICATION_NDJSON_VALUE)
public Mono<Void> ingest(@RequestBody Flux<EventDto> events) {
    return events
            .concatMap(event -> reactiveService.save(event), 8)
            .then();
}
```

This is **non-standalone illustrative code**: it requires `EventDto`, `reactiveService`, imports, and a WebFlux application. `reactiveService.save(event)` is assumed to return a genuinely reactive/non-blocking `Mono<?>`. `concatMap(..., 8)` preserves processing order and uses the specified prefetch; it is **not a cap on total uploaded bytes**. Request size/decoder limits, data validation, timeouts, and DB protections are needed separately.

If `save` calls blocking JDBC, `concatMap` does not turn it into non-blocking. If a client uploads infinite data and the server parses into `collectList()`, the entire request can accumulate in memory before saving. Do not collect the whole stream unless truly necessary and properly bounded.

## 9. Runnable Java 17+ Program: Demand Is Only Guaranteed Inside the Reactor Pipeline

The following example is a **pure Reactor Core simulation**, with no HTTP. It shows `request(n)` throttling items inside one subscription and `cancel()` stopping the producer. After grasping this boundary, remember **you cannot infer from this program's output that TCP/sockets/browsers are throttled by the same `n`**.

Structure:

```text
reactor-demand-demo/
├── pom.xml
└── src/main/java/demo/DemandBoundaryDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>reactor-demand-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.8.8</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/DemandBoundaryDemo.java`:

```java
package demo;

import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

public class DemandBoundaryDemo {
    public static void main(String[] args) {
        Flux<Integer> source = Flux.range(1, 5)
                .doOnRequest(n ->
                        System.out.println("source request=" + n));

        BaseSubscriber<Integer> subscriber = new BaseSubscriber<>() {
            @Override
            protected void hookOnSubscribe(Subscription s) {
                System.out.println("subscribed");
                // Intentionally do not request here yet.
            }

            @Override
            protected void hookOnNext(Integer item) {
                System.out.println("item=" + item);
            }

            @Override
            protected void hookOnComplete() {
                System.out.println("completed");
            }

            @Override
            protected void hookOnCancel() {
                System.out.println("cancelled");
            }
        };

        source.subscribe(subscriber);

        System.out.println("request(2)");
        subscriber.request(2);

        System.out.println("request(1)");
        subscriber.request(1);

        System.out.println("cancel");
        subscriber.cancel();
    }
}
```

Run with JDK 17+ and Maven from the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.DemandBoundaryDemo
```

**Program standard output**, excluding Maven messages:

```text
subscribed
request(2)
source request=2
item=1
item=2
request(1)
source request=1
item=3
cancel
cancelled
```

Explanation:

1. Subscribed, yet `hookOnSubscribe` did not request, so no `item` arrives yet.
2. `request(2)` allows `Flux.range` to emit 1 and 2. `doOnRequest` records the demand.
3. `request(1)` permits item 3.
4. `cancel()` terminates the subscription before items 4 and 5 are sent. Because there is no `onComplete`, `hookOnComplete` does not run.
5. All operations in the example are **synchronous on the requesting thread**, so output order is deterministic without depending on schedulers or network I/O.

**Scope of inference:** the program proves the Reactive Streams contract **within a single in-JVM pipeline**. If `Flux.range` is replaced with data from `WebClient`, Kafka, a browser, or a hot source, you must inspect **each adapter and queue**; never use this output to claim a real client received exactly 3 items over the wire.

## 10. Spring WebFlux Example: SSE Status Updates for Slow Clients

Suppose an endpoint streams readings for a dashboard. The UI **only needs the newest state**, without keeping every intermediate tick. You can place `onBackpressureLatest` near the update source so that when downstream cannot keep up, the latest value is prioritized over keeping every value.

This is a **structurally complete Java 17 controller class** in a project with `spring-boot-starter-webflux`; a Spring Boot main class/server is still required. Do not use this example as an audit event source.

```java
import java.time.Duration;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
public class DashboardController {

    public record Snapshot(long tick) { }

    @GetMapping(path = "/dashboard/stream",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<Snapshot>> stream() {
        return Flux.interval(Duration.ofMillis(250))
                .onBackpressureLatest()
                .map(tick -> ServerSentEvent.<Snapshot>builder()
                        .id(Long.toString(tick))
                        .data(new Snapshot(tick))
                        .build())
                .doOnCancel(() ->
                        System.out.println("client subscription cancelled"));
    }
}
```

Processing flow:

1. `Flux.interval` emits ticks on a scheduler; the source is not the browser. Each subscription has its own lifecycle.
2. `onBackpressureLatest()` can **discard intermediate ticks** to keep the newest value for a slow downstream, rather than buffering unboundedly at this operator. It does not guarantee the entire HTTP path is buffer-free, nor does it guarantee every tick reaches the client.
3. `map` builds an SSE object with an `id` and `Snapshot` body.
4. Spring WebFlux/HTTP adapter encodes and sends SSE over the transport. Each subsequent layer still throttles and buffers bytes independently.
5. `doOnCancel` runs when the upstream subscription is cancelled. This is a pipeline cancellation observation point, **not proof the client read every event**. When connections drop, detecting cancellation can be delayed.

**Very important regarding SSE `id`:** `id` in the example is just the tick number. It comes with no event store or replay mechanism for `Last-Event-ID`. If a browser reconnects and asks to replay missed events, a real application needs a durable history store, sequence numbers, and bounded replay. **Do not use `onBackpressureLatest` for payments, audit logs, or events requiring exact-once delivery.**

### Testing HTTP Streaming from Outside

After running an application with the controller above, you can observe SSE:

```bash
curl -N -H "Accept: text/event-stream" http://localhost:8080/dashboard/stream
```

`-N` (no-buffer) disables `curl`'s own output buffering, making SSE lines appear more immediately. It **does not disable Netty, kernel, or reverse-proxy buffering**, and does not guarantee each event arrives in a single TCP packet.

To simulate a receiver consuming few bytes/second in a test environment, you can try:

```bash
curl -N --limit-rate 1k http://localhost:8080/dashboard/stream
```

`--limit-rate 1k` caps `curl`'s receive rate at roughly 1 KiB/second. With very small events, this rate may still be faster than the source's emission rate; **this is not a guaranteed test for inducing server backpressure**. To see clear pressure, use sufficiently large payloads, an appropriate emission rate, and queue/socket measurement tools, while also checking any proxy path. Never rely on lines printed in the terminal to infer server-side memory usage.

### Do Not Equate SSE Output with HTTP Client Demand

A browser `EventSource` does not call `request(n)`. `onBackpressureLatest` activates **where the operator sees demand drop**; if the HTTP adapter still requests fast enough and buffers bytes at a later layer, the operator may not immediately see that client JavaScript is slow. Thus, adding this operator is only **one control point**, and cannot replace an overall buffer- and connection-bounding strategy.

## 11. `WebClient` Example: Upstream Request Limits Are Not Network Limits

This snippet illustrates a **Java client** receiving multiple NDJSON objects:

```java
Flux<EventDto> events = webClient.get()
        .uri("/events")
        .accept(MediaType.APPLICATION_NDJSON)
        .retrieve()
        .bodyToFlux(EventDto.class)
        .limitRate(16);
```

This is a snippet requiring `webClient`, `EventDto`, `MediaType`, `Flux`, and an HTTP server with an NDJSON endpoint.

- `bodyToFlux(EventDto.class)` returns a Publisher of items decoded from the response.
- `limitRate(16)` splits/shapes downstream requests sent upstream within the **Reactor pipeline**. Replenishment, prefetch, and batching depend on the operator.
- **It does not mean** `WebClient` only downloads 16 objects over the socket, nor **does it mean** the network has not received bytes for the 17th object yet.
- The client codec may already hold buffered bytes from the transport; a single large object can occupy many bytes, far outweighing the count of 16 items.
- If downstream calls `collectList()`, the collection can still grow to the entire response; `limitRate` does not cap total elements stored in a list.

If you want to stop downloading excessive data when only a few items are needed, make the requirement explicit:

```java
Flux<EventDto> firstTen = events.take(10);
```

`take(10)` caps items **received downstream** and can cancel upstream after the 10th item. However, bytes already sent/buffered earlier may not be recoverable, and the server may have already performed part of the work. For billed data or side-effecting calls, use a server-side API with explicit limits rather than relying on client cancellation to undo work.

### Codec `maxInMemorySize` Is Not a Total HTTP Memory Cap

Spring WebFlux/WebClient exposes codec settings such as:

```java
WebClient client = WebClient.builder()
        .codecs(configurer -> configurer
                .defaultCodecs()
                .maxInMemorySize(256 * 1024))
        .build();
```

This snippet configures the in-memory aggregation limit of **certain codec decode/encode operations**. When the applicable threshold is exceeded, Spring can throw `DataBufferLimitException`. It **does not set a hard cap on total Netty direct memory, TLS, kernel socket buffers, all pending responses across multiple connections, or lists collected by application code**. Do not raise the codec limit to "fix" an unbounded streaming source when the root cause is accumulating the entire payload.

## 12. Hot Producers and Sources That Cannot Slow Down

Not every source listens to `request(n)`. A producer can keep emitting regardless of subscriber demand:

- External listener/callback APIs or a device sending continuous data.
- Kafka/message brokers: adapters can pause/throttle polling within limits, yet the broker, topic, and other consumers still have their own pace.
- Price feeds, external WebSockets, fast timers, or system-wide event streams.
- Other clients that already pushed data to ingress, queued at a proxy/broker before the service subscribed.

When a source cannot slow down accordingly, you must define an **overflow policy**:

| Strategy | Effect | When Appropriate | Risk |
|---|---|---|---|
| **Bounded buffer** | Temporarily holds up to N items or a separate byte limit | Short bursts; important items with balanced average rate | Must define error/drop/reject when full |
| **Drop** | Discards items when unable to accept | Telemetry/state not needing every event | Event loss; must measure drop counts |
| **Latest** | Keeps newest snapshot, discards unused old snapshots | Dashboards / sensor readings | Does not preserve history |
| **Error / overload response** | Fails fast on overload | Data requiring strict accuracy | Client needs safe retries and idempotency |
| **Durable broker/queue** | Offloads backlog to a persistent system | Every event must be processed; absorbs long bursts | Higher latency; still needs quotas/retention/retries |
| **True producer slowdown** | Pauses reading/polling or propagates flow control to source | When the source supports it | Not every source supports adequate throttling |

Common operators:

```java
Flux<Metric> latestOnly = hotMetrics
        .onBackpressureLatest();

Flux<Metric> bounded = hotMetrics
        .onBackpressureBuffer(100);

Flux<Metric> dropped = hotMetrics
        .onBackpressureDrop();
```

This is a snippet; it requires `Flux<Metric> hotMetrics` and a `Metric` type. Interpret carefully:

- `onBackpressureLatest()` holds only **one waiting element at the operator itself**; intermediate items may be discarded.
- `onBackpressureBuffer(100)` bounds **the element count in the queue managed by that operator**; on overflow it can error per overload/usage policy. It does not bound every other queue.
- `onBackpressureDrop()` can drop items when demand is absent.
- These operators typically **do not slow down an external producer** if the hot source does not support it, and may alter upstream demand to proactively receive and apply overflow handling.
- If items are reference-counted `DataBuffer`/`ByteBuf` instances, pay special attention to discard/release on drop/cancel paths. Do not assume default operators automatically perform proper cleanup for every buffer type.

**A business principle:** If no event may ever be lost, `latest`/`drop` is the wrong strategy. You need durable queues/acknowledgments/persistent storage and explicit backlog limits.

## 13. Quantitative Problem: Why Buffers Grow Even When `Flux` Has `request(n)`

Suppose a source sends 500 events/second while the client app only processes 100 events/second. If each event occupies **2 KiB after encoding**, data inside a buffer receiving all events grows roughly as:

```text
Arrival rate:            500 events/s
Consumption rate:        100 events/s
Surplus:                 400 events/s
Average size:              2 KiB/event

Data growth: 400 × 2 KiB/s = 800 KiB/s
After 60 seconds: 800 × 60 KiB = 48,000 KiB ≈ 46.9 MiB
```

This is a **model of a queue with no drops and no upstream slowdown**. Actual memory also includes object overhead, metadata, batching, compression, allocator overhead, and other queues; this calculation is **not a benchmark** or a guarantee that RAM stays at exactly 46.9 MiB.

Quick check formula:

```text
If λ = emission rate (items/second), μ = consumption rate,
B = average bytes/item, and λ > μ:

backlog byte growth rate ≈ (λ − μ) × B

No slowdown, no drop, no error:
backlog can grow roughly linearly over time.
```

If a buffer is capped at 10,000 items, a 400 item/s surplus can fill it in roughly 25 seconds (ignoring pre-existing backlog), at which point a **subsequent policy must exist**. A size cap without an action on hitting the threshold only postpones the failure.

In multi-client systems: 1,000 clients × 1 MiB average pending data can require roughly 1,000 MiB for that pending data alone, before counting anything else. Therefore, you need **per-connection** and **system-wide** metrics, not just one buffer.

### Do Not Evaluate Using Throughput Alone

Two systems with the same 10,000 items/s throughput can differ hugely in:

- Item/payload size.
- Client latency and distribution of slow clients.
- Concurrent connection count.
- Buffer retention duration.
- Serialization/encoding cost.
- In-flight items ahead of prefetching operators.
- Paths through proxies/TLS/HTTP/2 multiplexing.

Test with mixed workloads (fast, slow, disconnecting clients) and measure memory/queues/latency to locate actual bottlenecks.

## 14. When Does Throttling Reach Upstream, and When Does It Stop Mid-Way?

### Case A — Same JVM, Demand-Compliant Pull Source

`Flux.range`/`Flux.generate` can generate items per `request(n)`. When downstream stops requesting, the source can stop computing further items. This is the relatively direct case.

### Case B — Real Reactive DB Driver

The driver can read/decode according to demand and its own protocol mechanics, yet saying "R2DBC returns `Flux`" **does not guarantee** the database server immediately halts query execution when the browser pauses. Queries, network buffers, and DB cursors/prefetch have their own behavior; measure and inspect the specific driver.

### Case C — Source Fed from an Already-Populated Queue

`Flux.fromIterable(hugeList)` may honor demand while emitting, yet the huge list **was already allocated beforehand**. Backpressure protects the `onNext` pace without **reclaiming** memory the application already accumulated before creating the `Flux`.

### Case D — Message Broker or Independent System

The consumer can slow down polling or local demand; the broker still holds backlog and other producers keep publishing. Slowing down has **shifted where backlog sits**, without proving end-to-end memory/cost decreased unless retention/quotas are bounded.

### Case E — HTTP Server + Proxy Buffer

WebFlux can send many bytes to a proxy, and the proxy buffers them because the browser is slow. The server only feels pressure once the proxy slows reading or hits limits; `request(n)` from a Java client does not cross proxies as a unified signal.

### Case F — Slow Browser Event Handler

A JavaScript callback takes a long time, yet the browser/network can still read ahead and queue events. The server has no signal saying "client business logic finished". If precision is required, add **application-level ACKs**, quotas, or a dedicated streaming protocol. **A business ACK is an application-designed protocol**, distinct from a TCP ACK.

## 15. Meaningful Backpressure Testing Across HTTP

To conclude a system withstands slow clients, run an observable experiment:

1. **Choose the real stream**: SSE, NDJSON, file download, or upload? Record the exact protocol (HTTP/1.1, HTTP/2, or HTTP/3), proxies, and codec settings.
2. **Fix production rates**: item rate, average/max size, concurrent clients, ratio of slow clients.
3. **Slow down deliberately**: rate-limit client reads, read in bursts, or pause reading briefly. For HTTP/2, test multiple concurrent streams over one connection.
4. **Measure every layer**: upstream requests/demand, pending items, queued bytes/Netty writability, direct memory/heap, socket send/receive queues, proxy buffered bytes if applicable, client event queue/lag.
5. **Measure outcomes**: time to first/received event at client, dropped events, errors, UI lag, cancellation callbacks, connection count, and CPU.
6. **Test thresholds**: full buffers, client disconnects, proxy resets, timeouts, flaky networks, restarts, reconnects, and heavy bursts.
7. **Verify recovery**: once the client resumes normal reading, does backlog drain? Is required data intact? Are resources released on cancel?

### Metrics Worth Tracking

In a Reactor Netty application with Micrometer/metrics properly enabled, you can inspect metric groups such as:

- `reactor.netty.http.server.connections.active`: connections actively handling requests.
- `reactor.netty.http.server.data.sent` / `reactor.netty.http.server.data.sent.time`: outbound data volume and send timing.
- `reactor.netty.http.server.response.time`: server-side response handling time.
- `reactor.netty.bytebuf.allocator.used.direct.memory`: direct memory bytes from the monitored allocator.
- Custom metrics: live subscription count, queue size/bytes, dropped item count, timeouts, and time since last successful read/write.

Metric names and availability depend on versions and configuration. **Do not treat `data.sent` as a client application ACK.** Bytes sent measures a point in the server/transport pipeline; it does not confirm UI processing.

### Typical Failure Modes to Watch For

- `DataBufferLimitException`: codec had to hold/aggregate more data than the configured limit.
- `OutOfMemoryError` (heap/direct) or reference-counted buffer leaks.
- Growing write queues, prolonged non-writable channels, rising send latency.
- Full, slow, or timing-out client socket/proxy buffers.
- `OverflowException`/missing-demand errors or `FAIL_OVERFLOW` signals from sinks.
- High CPU from encoding, compression, callback execution, or excessive connections.
- Subscriptions staying alive after clients leave, causing producers to keep generating unwanted data.

Do not jump to conclusions from a single error type. For example, raising `maxInMemorySize` might eliminate `DataBufferLimitException` in a decoder while causing memory to grow further; check whether the API should stream or bound payload sizes instead.

## 16. Choosing Policies by Data Category

| Data Type | Allowed to Drop Events? | Sensible Design |
|---|---|---|
| Dashboard metrics, cursor positions, live readings | Usually **yes**, if latest state suffices | Latest/coalesce/sample, frequency limits, show timestamp/staleness |
| Real-time video/audio | May need quality reduction or policy-driven drops | Rate adaptation, frame/buffer latency, specialized transport |
| Critical SSE notifications | Depends on contract; if none may be lost | Durable event IDs, resume/replay, quota-bounded history, backoff |
| Orders, payments, audit logs | **No** business data loss allowed | Durable queues, business ACKs, idempotency, bounded retries, backlog monitoring |
| File downloads | Missing bytes unacceptable | Streaming with throughput limits, checksum/range verification, timeouts |
| File uploads | Must not accept unboundedly beyond quota | Size/request limits, rate limits, quotas, validation, cancel and cleanup |
| As-you-type search suggestions | Old results can be cancelled | `switchMap`/latest result, debounce, cancellation; no need to retain every request |

**Decisions about data loss are business decisions**, not a generic performance option applicable to every `Flux`.

## 17. Common Misconceptions

1. **"Reactor backpressure guarantees the database automatically slows down if the browser reads slowly."** Not guaranteed. Multiple codec/network/proxy/broker layers have their own buffers and limits.
2. **"`request(10)` means HTTP sends exactly 10 JSON objects and stops on the wire."** False. Demand is an `onNext` count at the Publisher–Subscriber boundary; the transport sends bytes per buffers and protocol.
3. **"TCP ACK means the user read the event."** False. TCP ACK confirms network data reached the TCP layer, not parsing/rendering/business persistence.
4. **"A successful server write means the event was delivered to the JavaScript callback."** False. Bytes may still sit in kernel/proxy/client buffers.
5. **"HTTP/2 `WINDOW_UPDATE` is Reactor's `request(n)`."** False. `WINDOW_UPDATE` grants **DATA frame byte** credit per stream and connection, hop-by-hop.
6. **"If the proxy receives data fast, the browser is fast too."** False. The proxy can buffer and send slowly on the other connection.
7. **"`limitRate(16)` caps all memory to only 16 objects."** False. It shapes upstream demand at one point; large objects, other operators, and codec/socket buffers still exist.
8. **"Default `onBackpressureBuffer()` is safe."** Dangerous without an explicit limit. An unbounded buffer can cause OOM.
9. **"`onBackpressureLatest()` never loses data."** False. It intentionally drops intermediate values; you must accept those semantics.
10. **"SSE IDs automatically provide replay on reconnect."** False. Message IDs do not create a durable event store; the app must implement replay/resume if needed.
11. **"`maxInMemorySize` is the total RAM cap for `WebClient`."** False. It caps codec aggregation operations, not every buffer quota.
12. **"When a client cancels, server/DB work is definitely rolled back."** False. Cancellation is a lifecycle signal; side effects and transactions have separate mechanics.
13. **"Non-blocking means no queues."** False. Non-blocking is event-driven and still uses buffers to absorb bursts, scheduling, and network latency.
14. **"Every test over localhost represents production."** False. Reverse proxies, HTTP versions, TLS, real clients, and slow networks shift bottlenecks.
15. **"More buffering is always safer."** False. Buffers buy time before overload; if long-term production exceeds consumption, backlog still grows to the limit.

## 18. Pre-Production Review Checklist for WebFlux Streaming

- **Source:** can it pause/throttle? If not, drop, fail, or durable queue?
- **Reactive boundaries:** do you know which operators prefetch, buffer, retry, or break backpressure demand?
- **Codec/payload:** how many bytes is the largest item? Does anything aggregate the full body? Is the media type truly streaming?
- **Netty/socket:** can you observe write queues, writability, heap/direct memory, connection counts, and timeouts?
- **Protocol:** is traffic HTTP/1.1, HTTP/2, or HTTP/3? Are multiplexing and flow-control windows accounted for?
- **Proxy/CDN:** is there buffering, compression, rate limiting, timeouts, or protocol translation? Have you tested the real path?
- **Client:** how fast does the client app consume? Does it have its own queue, persistence, rendering, and real backpressure?
- **Data policy:** may intermediate states be dropped, or must every event be preserved? Are durable storage, ACKs, and resume in place if needed?
- **Overflow:** are item counts, byte sizes, durations, and client counts bounded; what happens when full?
- **Cancel/reconnect:** are subscriptions/resources released and reconnects handled without duplicating side effects?
- **Observability:** can you measure slow clients, buffered bytes, drops, lag, completion, errors, and timeouts across layers?
- **Load testing:** have you tested concurrent slow + fast clients, bursts, network/proxy delays, HTTP/2 streams, and post-disconnect cleanup?

**Key takeaway:** `request(n)` protects **one Reactive Streams boundary by element count**. HTTP, Netty, TCP/QUIC, proxies, and browsers throttle **bytes, buffers, and lifecycles through different mechanisms**. Backpressure can propagate into slowing down a producer, yet you should never assume **end-to-end guarantees** without checking every adapter, buffer limit, and data policy. A good system knows **where backlog appears, how it is bounded, and what happens when a client cannot keep up**.

## References

- Reactive Streams — [JVM Specification: Publisher, Subscriber, Subscription, and demand](https://www.reactive-streams.org/).
- Project Reactor — [Backpressure and Ways to Reshape Requests](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html).
- Project Reactor — [Sinks and Overflow Behavior](https://projectreactor.io/docs/core/release/reference/coreFeatures/sinks.html).
- Reactor Netty — [HTTP Server Reference: I/O, Metrics, Connection](https://projectreactor.io/docs/netty/release/reference/http-server.html).
- Netty — [WriteBufferWaterMark API](https://netty.io/4.2/api/io/netty/channel/WriteBufferWaterMark.html).
- IETF — [RFC 9113, HTTP/2 `5.2 Flow Control](https://www.rfc-editor.org/rfc/rfc9113.html#section-5.2).
- Spring Framework — [WebFlux Reactive Core](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html).
- Spring Framework — [WebClient Codec Configuration and maxInMemorySize](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html).
