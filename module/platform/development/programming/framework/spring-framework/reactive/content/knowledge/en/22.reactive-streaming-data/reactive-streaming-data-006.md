# Server, Proxy, and Client Buffering in Spring WebFlux

## 1. Why has the server flushed yet the client still sees no data?

A WebFlux endpoint can emit data steadily using `Flux<T>`, the encoder can produce byte chunks, and the server can call flush after each event. Even so, the user may still only see the entire content once the stream ends.

The reason is that **streaming is a property of the entire transmission path**, not just the controller. Data can be held at many layers:

1. Publishers and operators inside the application.
2. `HttpMessageWriter`, encoders, and Spring's response abstraction.
3. Reactor Netty, outbound channel buffers, and TLS.
4. OS socket send buffers and the TCP stack.
5. Reverse proxies, ingress, API gateways, service meshes, or CDNs.
6. Client-side HTTP libraries, runtimes, and UI.

Each layer can accumulate bytes before forwarding them. Therefore, distinguish three moments in time:

- **Application emitted:** the Publisher emits an item.
- **Server flushed:** the framework/server requests pending data to be pushed down to the transport.
- **Client consumed:** the receiving application has read and processed the data.

These three moments are not synonymous. Flush is a signal to the transport layer to keep sending data; it is not confirmation that the browser has received, decoded, or rendered the event.

~~~text
Flux / Publisher
      |
      v
Spring encoder + HttpMessageWriter
      |
      v
ServerHttpResponse / writeAndFlushWith
      |
      v
Reactor Netty outbound buffer
      |
      v
TLS + OS socket send buffer
      |
      v
TCP / HTTP framing
      |
      v
Reverse proxy / ingress / CDN
      |
      v
Client HTTP library / browser
      |
      v
ReadableStream / EventSource / UI
~~~

This lesson focuses on identifying and controlling buffering at each layer, designing SSE/NDJSON, configuring proxies, and testing event arrival times from a real client.

## 2. Four concepts to separate

### 2.1. Buffering

Buffering is holding bytes or items temporarily before forwarding them. Its goals may include:

- Reducing the number of I/O calls.
- Increasing throughput when writing data in batches.
- Supporting compression or encryption.
- Satisfying formats that require a complete document.
- Smoothing rate differences between producer and consumer.
- Reducing network round trips.

Buffering is not inherently a bug. For large files, database batches, or ordinary JSON documents, buffering can be reasonable. A problem arises when the application needs events to arrive early, yet an intermediate layer waits for more data or waits for the stream to end.

### 2.2. Flushing

Flushing instructs a writing layer to push pending data down to the layer below. In WebFlux, `ServerHttpResponse.writeAndFlushWith` allows splitting the response into Publisher groups and flushing after each group.

Flushing does not:

- Create message boundaries at TCP.
- Force a separate TCP packet per event.
- Bypass every proxy or CDN buffer.
- Guarantee the client application has read the data.
- Guarantee the UI renders at that exact moment.

### 2.3. Backpressure

Backpressure regulates demand from downstream to upstream per Reactive Streams. If the client/server does not consume quickly, demand can drop and the reactive source is throttled when components support that mechanism.

Backpressure differs from buffering. A pipeline with backpressure can still have bounded buffers in operators, Netty, sockets, or proxies. A proxy with response buffering enabled can even read rapidly from upstream and hold data locally before sending it to the client.

### 2.4. Framing

Framing defines how the receiver knows where a message or record ends. Examples:

- SSE terminates an event with a blank line.
- NDJSON uses newlines to separate JSON objects.
- A JSON array is a document with opening/closing brackets.
- HTTP/1.1 can use chunked transfer framing.
- HTTP/2 uses DATA frames.

Transport chunk boundaries do not necessarily match application event boundaries. One event can arrive across multiple reads; multiple events can also arrive in a single read.

## 3. Buffering inside a WebFlux application

### 3.1. `Flux<T>` does not guarantee per-item flushing on its own

A controller returning `Flux<T>` means the source can emit multiple values over time. How it is encoded and flushed depends on the media type, `HttpMessageWriter`, and codec configuration.

Example of an SSE stream:

~~~java
@GetMapping(
    value = "/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
public Flux<ServerSentEvent<String>> events() {
    return Flux.interval(Duration.ofSeconds(1))
        .map(index -> ServerSentEvent.<String>builder()
            .id(Long.toString(index))
            .event("tick")
            .data("message-" + index)
            .build());
}
~~~

`text/event-stream` is the media type dedicated to event streaming. Spring has a specialized writer for SSE and flushes events per element. Reactor Netty also describes its SSE strategy as flushing after each emitted Publisher element.

With standard `application/json`, clients usually expect a complete JSON document. Even if the server writes document bytes across multiple writes, a client calling `response.json()` or `bodyToMono(String.class)` still waits for the entire body before parsing. Do not use a JSON document as an event protocol just because the controller returns a Flux.

### 3.2. Buffers created by operators

Operators such as `buffer`, `bufferTimeout`, `collectList`, `reduce`, or certain prefetch strategies can hold multiple items before emitting downstream.

Example intentionally collecting five events:

~~~java
Mono<List<Event>> buffered =
    Flux.interval(Duration.ofSeconds(1))
        .take(5)
        .map(index -> new Event(index + 1, "event-" + index))
        .collectList();
~~~

The Publisher only emits the List when the source completes. If the source is infinite, `collectList` produces no result until terminated or cancelled; this is a design bug if the endpoint needs continuous streaming.

These operators are not bad. Use them when business logic truly requires batching or aggregation, and avoid placing them on the path of events that must be emitted immediately.

### 3.3. Encoder and message writer buffers

Codecs may need to accumulate data to:

- Produce a valid JSON document.
- Complete an object before encoding.
- Handle charsets or framing.
- Perform compression.
- Allocate an appropriately sized DataBuffer.

For streaming responses, choose a media type for which the writer supports streaming. Spring WebFlux supports streaming media types such as `text/event-stream` and can configure streaming media types for the Jackson encoder. Do not infer flush policy solely from the Java type `Flux`.

### 3.4. Group flushing with `writeAndFlushWith`

`ServerHttpResponse.writeWith` writes a single Publisher of DataBuffers. `writeAndFlushWith` accepts a Publisher containing multiple inner Publishers; each inner Publisher is a group of data flushed after it is written.

~~~java
Mono<Void> writeEvents(ServerHttpResponse response) {
    Flux<Publisher<? extends DataBuffer>> flushGroups =
        Flux.interval(Duration.ofSeconds(1))
            .take(3)
            .map(index -> {
                String frame = "data: event-" + (index + 1) + "\n\n";
                DataBuffer buffer = response.bufferFactory().wrap(
                    frame.getBytes(StandardCharsets.UTF_8));
                return Mono.just(buffer);
            });

    response.getHeaders().setContentType(MediaType.TEXT_EVENT_STREAM);
    return response.writeAndFlushWith(flushGroups);
}
~~~

Here each inner Publisher creates one SSE frame; the response is flushed after each group. When passing a DataBuffer to the response writer, ownership transfers to the writing component per the API contract. Do not release the buffer before the writer consumes it.

Use `writeAndFlushWith` when you genuinely need to control flush groups at the response layer. For normal SSE controllers, returning `Flux<ServerSentEvent<T>>` is usually simpler and lets the SSE writer manage framing.

## 4. Buffering at server runtime, TLS, and OS

### 4.1. Reactor Netty has outbound buffers

Spring WebFlux typically runs on Reactor Netty under Spring Boot's default WebFlux configuration. Data is turned into DataBuffer/ByteBuf and flows through the Netty channel pipeline before being written to the socket.

Netty can hold data in outbound buffers until the channel is writable. When the channel is congested, writes may wait or be regulated according to transport capacity. The event loop handles I/O asynchronously; do not use `Thread.sleep`, `block()`, or long synchronous operations inside handlers to try to pace a stream.

### 4.2. TLS and compression can batch data

HTTPS adds a TLS record layer before bytes hit the socket. Compression can also hold an amount of data to build efficient compressed blocks. These layers can alter the size and timing of forwarded data.

If a stream has small events and needs low latency:

- Check whether compression is enabled at the server, proxy, or CDN.
- Measure both HTTP and HTTPS paths if the environment allows.
- Only disable compression for streaming endpoints when measurements show it causes delays and the trade-off is acceptable.
- Do not assume an extra flush in the controller will force every TLS/compression layer to immediately emit a record.

### 4.3. Socket send buffers and TCP

The operating system maintains socket send buffers. TCP transmits an ordered byte stream, preserving no Publisher message boundaries. Small chunks may be coalesced or split into segments depending on network conditions, congestion windows, and transport algorithms.

Therefore, never write a client assuming one read equals one event. The client must parse the application protocol framing.

### 4.4. Flush is not TCP acknowledgement

Flushing only pushes data closer to the transport layer. A TCP acknowledgement indicates data was acknowledged at the peer's TCP layer, not that the peer's application parsed the event or updated the UI.

If business confirmation is needed that the recipient processed an event, design application-level acknowledgements, such as event IDs and a dedicated acknowledgement API.

## 5. Buffering at reverse proxies and ingress

### 5.1. Nginx enables response proxy buffering by default

When `proxy_buffering on`, Nginx reads the response from upstream as fast as possible, holds data in configured buffers, and may spill excess to temporary files if the response is large. The client may only receive data after the proxy accumulates enough bytes or completes the response.

When `proxy_buffering off`, Nginx forwards data to the client synchronously as it arrives from upstream without trying to read the entire response first. Nginx documentation explicitly states the default for this directive is `on`.

### 5.2. Nginx configuration for streaming endpoints

Example configuration inside a server block:

~~~nginx
location /api/stream/ {
    proxy_pass http://webflux_app;
    proxy_http_version 1.1;

    proxy_buffering off;
    proxy_cache off;

    proxy_read_timeout 1h;
    gzip off;
}
~~~

Meaning:

- `proxy_buffering off` disables response buffering for this location.
- `proxy_cache off` prevents caching streaming responses at this location.
- `proxy_read_timeout` must be long enough for sparse streaming connections.
- `gzip off` is an option when compression delays small events; only disable if needed after testing.

This is a configuration example, not optimal timeout values for every system. Align timeouts with gateways, load balancers, ingress, and the connection duration required by the product.

### 5.3. The `X-Accel-Buffering` header

Nginx can toggle response buffering per response via header:

~~~http
X-Accel-Buffering: no
~~~

Spring can set this header before the response commits:

~~~java
response.getHeaders().set("X-Accel-Buffering", "no");
~~~

This header is useful when only specific endpoints need streaming. Nginx can be configured to ignore control headers via `proxy_ignore_headers`, so verify the actual configuration.

### 5.4. Do not confuse response buffering with request buffering

- `proxy_buffering` controls whether Nginx buffers the response from upstream before sending to the client.
- `proxy_request_buffering` controls whether Nginx buffers the client's request body before forwarding to upstream.

When debugging server-sent events or response streams, check `proxy_buffering`. When debugging streaming uploads from client to server, check `proxy_request_buffering`.

### 5.5. Other proxies can also buffer

Nginx is not the only layer. The following components may have their own buffering, compression, caching, or timeout policies:

- Kubernetes ingress controllers.
- Envoy or service mesh sidecars.
- API gateways.
- CDNs and edge caches.
- Cloud load balancers.
- WAFs or corporate reverse proxies.

Configuration names vary by product and version. Check the documentation for the exact gateway deployed; do not apply Nginx directives to Envoy or vice versa.

## 6. Buffering at the client and UI

### 6.1. Clients can actively read the whole response

In Java WebClient:

~~~java
Mono<String> wholeBody = webClient.get()
    .uri("/api/stream/json")
    .retrieve()
    .bodyToMono(String.class);
~~~

`bodyToMono(String.class)` waits for the body to complete to construct one String. This is reasonable for small documents, but unsuitable if you want to process events as they arrive.

To consume element by element, use the reactive API matching the media type:

~~~java
Flux<ServerSentEvent<String>> events = webClient.get()
    .uri("/api/stream/sse")
    .accept(MediaType.TEXT_EVENT_STREAM)
    .retrieve()
    .bodyToFlux(new ParameterizedTypeReference<ServerSentEvent<String>>() {});
~~~

The client can still have internal buffers. Subscribe and process items as a stream; avoid converting to `collectList`, `blockLast`, or concatenating into a single String if early reading is the goal.

### 6.2. Browser Fetch has ReadableStream

`Response.body` in the Fetch API is a `ReadableStream`. You can read chunk by chunk instead of calling `response.text()` or `response.json()` which wait for the entire body.

~~~javascript
const response = await fetch("/api/stream/flush");

if (!response.ok || !response.body) {
  throw new Error("HTTP " + response.status);
}

const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
  const result = await reader.read();
  if (result.done) break;

  output.textContent += decoder.decode(result.value, { stream: true });
}

output.textContent += decoder.decode();
~~~

`TextDecoder` uses `stream: true` to preserve state when a UTF-8 character is split across chunks. A chunk yielded by the browser does not necessarily correspond to one SSE event or one NDJSON line.

### 6.3. Using EventSource for SSE

If the endpoint follows the SSE protocol, the browser can use `EventSource`:

~~~javascript
const source = new EventSource("/api/stream/sse");

source.addEventListener("update", (event) => {
  const payload = JSON.parse(event.data);
  console.log("received event", payload);
});

source.onerror = () => {
  console.log("SSE connection interrupted; browser may reconnect");
};
~~~

EventSource automatically parses event framing and supports SSE reconnection. If you need to send a method other than GET or a custom authorization header, consider Fetch streaming or an appropriate authentication design; the standard EventSource API has restrictions on request configuration.

### 6.4. The UI can batch updates even after the network receives them

Even when JavaScript reads chunks immediately, a UI framework may batch state updates or wait for the next animation frame. Developer tools may also display response previews in ways that do not accurately reflect when individual bytes arrived.

Distinguish:

- When the browser receives bytes.
- When JavaScript reads a chunk.
- When the parser completes an event.
- When state is updated.
- When the browser paints pixels.

If the goal is user experience, measure until the UI displays the event, not only server-side logs.

## 7. Media types and framing determine how clients process data

### 7.1. JSON documents

`application/json` suits a complete JSON object or array. Clients typically parse after the body completes. Do not use a JSON array as an event protocol if the client is required to process each record immediately.

### 7.2. NDJSON

NDJSON uses one JSON object per line:

~~~text
{"id":1,"type":"created"}
{"id":2,"type":"updated"}
{"id":3,"type":"closed"}
~~~

Clients can parse each line as soon as its newline arrives. However, newline framing does not automatically guarantee the server/proxy flushes after each line. Check the writer, streaming media type, proxy, and client; if explicit flushing is required, use a response API with flush groups.

### 7.3. Server-Sent Events

SSE uses `text/event-stream`. An event can contain `id`, `event`, `data`, `retry` lines and end with a blank line:

~~~text
id: 1
event: update
data: {"status":"ready"}

id: 2
event: update
data: {"status":"running"}

~~~

Spring provides `ServerSentEvent<T>` and a dedicated writer. SSE suits unidirectional server-to-browser flows with event framing and reconnection. Use heartbeat comments such as `: keepalive` when connections must stay alive through infrastructure with idle timeouts; comments do not produce business events.

### 7.4. HTTP/1.1 and HTTP/2

With HTTP/1.1, responses without Content-Length can use chunked transfer encoding. Chunked encoding is only transport framing; chunks are not application events.

HTTP/2 uses DATA frames and stream multiplexing, not HTTP/1.1 chunked transfer encoding. Do not manually set `Transfer-Encoding: chunked` on HTTP/2 responses. Let the server and proxy manage protocol framing.

## 8. Backpressure across multiple buffer layers

### 8.1. Backpressure inside the application

If the client reads slowly, demand can decrease and the downstream publisher throttles upstream rate. Some operators still maintain prefetch or bounded buffers; inspect the entire pipeline rather than just one operator.

### 8.2. Proxy buffering can decouple upstream/downstream pacing

When a proxy reads fast from WebFlux but sends slowly to the browser, the proxy may hold data in memory or temporary files. The upstream server sees the proxy as its consumer, not the browser directly.

This can cause the server to write successfully while the browser has not yet received events. Disabling buffering for streaming endpoints brings backpressure closer through the proxy, though buffers in transport and client still remain.

### 8.3. Do not use flush as a substitute for load bounding

Frequent flushing has I/O overhead and can hurt throughput if every tiny byte is pushed separately. Choose flush boundaries according to the protocol:

- Each SSE event is a sensible boundary.
- Each NDJSON record can be a boundary when latency requires.
- File downloads typically optimize for larger chunks.
- Batch responses may prioritize throughput over per-item latency.

Balance latency, CPU, syscalls, bandwidth, and concurrent connections.

## 9. Timeouts, heartbeats, and long-lived connection lifecycles

Streaming responses can live much longer than typical request/response calls. Proxy/load balancer layers have idle timeouts; if no bytes are sent during that window, the connection may be closed.

Measures:

- Set gateway/proxy timeouts long enough for expected connections.
- Send protocol-appropriate heartbeats when streams may be silent for long periods.
- Close streams when the user navigates away or subscriptions are no longer needed.
- Use `doFinally` to clean up resources on complete/error/cancel.
- Limit concurrent connections and streams.
- Have reconnect, replay, or resume policies if events can be lost during client disconnects.

Heartbeats only keep connections active when infrastructure treats that traffic as activity. They do not replace reconnection, event IDs, or duplicate handling. With SSE, comment heartbeats can be used:

~~~text
: keepalive

~~~

Do not emit heartbeats too frequently; base the interval on path idle timeouts and connection overhead.

## 10. Complete Spring Boot 3.5.7 + Java 17 example

The project below exposes three endpoints for comparison:

- `GET /api/stream/sse`: emits SSE every second; Spring's writer handles event streaming.
- `GET /api/stream/flush`: builds individual SSE frames and uses `writeAndFlushWith` to flush after each group.
- `GET /api/stream/buffered`: collects five events into a List before returning JSON.

### 10.1. Project structure

~~~text
webflux-stream-buffering/
├── pom.xml
└── src/main/java/example/streaming/
    ├── StreamingApplication.java
    └── StreamController.java
└── src/test/java/example/streaming/
    └── StreamControllerTest.java
~~~

### 10.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>webflux-stream-buffering</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 10.3. `StreamingApplication.java`

~~~java
package example.streaming;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StreamingApplication {

    public static void main(String[] args) {
        SpringApplication.run(StreamingApplication.class, args);
    }
}
~~~

### 10.4. `StreamController.java`

~~~java
package example.streaming;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.List;

import org.reactivestreams.Publisher;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/stream")
public class StreamController {

    public record Event(
        long sequence,
        String message,
        Instant createdAt
    ) {}

    @GetMapping(
        path = "/sse",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public Flux<ServerSentEvent<Event>> sse(
        ServerHttpResponse response
    ) {
        prepareStreamingHeaders(response);

        return Flux.interval(Duration.ofSeconds(1))
            .take(5)
            .map(index -> {
                long sequence = index + 1;
                Event event = new Event(
                    sequence,
                    "event-" + sequence,
                    Instant.now()
                );

                return ServerSentEvent.<Event>builder(event)
                    .id(Long.toString(sequence))
                    .event("update")
                    .build();
            });
    }

    @GetMapping(
        path = "/flush",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public Mono<Void> explicitFlush(ServerHttpResponse response) {
        prepareStreamingHeaders(response);

        Flux<Publisher<? extends DataBuffer>> flushGroups =
            Flux.interval(Duration.ofSeconds(1))
                .take(5)
                .map(index -> {
                    String frame =
                        "id: " + (index + 1) + "\n"
                        + "event: update\n"
                        + "data: manual-" + (index + 1) + "\n\n";

                    DataBuffer buffer = response.bufferFactory().wrap(
                        frame.getBytes(StandardCharsets.UTF_8)
                    );

                    return Mono.just(buffer);
                });

        return response.writeAndFlushWith(flushGroups);
    }

    @GetMapping(
        path = "/buffered",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<List<Event>> buffered() {
        return Flux.interval(Duration.ofSeconds(1))
            .take(5)
            .map(index -> new Event(
                index + 1,
                "event-" + (index + 1),
                Instant.now()
            ))
            .collectList();
    }

    private static void prepareStreamingHeaders(
        ServerHttpResponse response
    ) {
        response.getHeaders().set(
            "Cache-Control", "no-cache, no-transform");
        response.getHeaders().set(
            "X-Accel-Buffering", "no");
    }
}
~~~

Explanation:

- `/sse` emits one `ServerSentEvent` per second. Spring's SSE writer formats the event and flushes per event.
- `/flush` builds SSE frames manually. Each inner Publisher in `flushGroups` holds a DataBuffer; `writeAndFlushWith` flushes after each group.
- `/buffered` uses `collectList()`. The client only receives a JSON array after all five events have been collected.
- `Cache-Control` and `X-Accel-Buffering` are hints for intermediate layers; they cannot force every proxy/CDN to comply if that layer's configuration ignores headers.

This is a finite five-event demo application. For infinite streams, remove `take(5)` only after establishing cancellation, heartbeat, timeout, and connection limit policies.

### 10.5. Running the application

Requires JDK 17+ and Maven. In the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

### 10.6. Testing SSE directly with curl

~~~bash
curl -N -i \
  -H "Accept: text/event-stream" \
  http://localhost:8080/api/stream/sse
~~~

`-N` or `--no-buffer` disables curl's output buffering so the terminal displays data sooner. Expected body has five events, about one second apart:

~~~text
id: 1
event: update
data: {"sequence":1,"message":"event-1","createdAt":"..."}

id: 2
event: update
data: {"sequence":2,"message":"event-2","createdAt":"..."}

...
~~~

The `createdAt` value is a runtime timestamp and varies across runs.

### 10.7. Comparing the aggregated endpoint

~~~bash
curl -N -i \
  -H "Accept: application/json" \
  http://localhost:8080/api/stream/buffered
~~~

This endpoint waits for the source to complete after roughly five seconds before returning a JSON array. `curl -N` cannot make the application emit data earlier than the Publisher emits it.

### 10.8. Testing through a proxy

When the application runs behind Nginx, call the public URL through the proxy using the same `curl -N` command. Compare against the application's direct port:

- If localhost emits every second while the proxy URL only appears after five seconds, inspect proxy buffering, compression, caching, and ingress.
- If both are slow, inspect the Publisher, operators, codec, server, and client.
- If curl prints steadily while the UI updates late, inspect client-side parsing and UI scheduling.

## 11. Testing streaming with WebTestClient

A test calling only `expectBody(String.class)` typically collects the complete body, so it does not prove events are received early. To test streaming, obtain the response body as a Flux and read the first element before the stream ends.

~~~java
package example.streaming;

import static org.springframework.http.MediaType.TEXT_EVENT_STREAM;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class StreamControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void firstSseDataArrivesBeforeStreamCompletes() {
        FluxExchangeResult<String> result = client.get()
            .uri("/api/stream/sse")
            .accept(TEXT_EVENT_STREAM)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(TEXT_EVENT_STREAM)
            .returnResult(String.class);

        String firstChunk = result.getResponseBody()
            .next()
            .block(Duration.ofSeconds(3));

        assertNotNull(firstChunk);
    }
}
~~~

This test hits the server directly and verifies first data arrives within three seconds. It does not test Nginx, CDNs, or browsers; run the same measurement through the public URL to verify the entire path.

Do not set a tight one-second threshold because CI can experience load. For real systems, use reasonable tolerances and check first-event arrival time rather than demanding exact wall-clock instants.

## 12. End-to-end diagnostic workflow

When a stream only appears after completion, follow these steps in order to pinpoint the layer:

1. **Confirm the source:** add logs or metrics where the Publisher emits items; check for `collectList`, `buffer`, `reduce`, `delayUntil`, or any operator waiting for enough data.
2. **Check writer/media type:** inspect whether the response has the right `Content-Type`; use `text/event-stream` for SSE and verify the writer flushes events.
3. **Test the server directly:** run `curl -N` against the application port, bypassing proxies.
4. **Inspect response headers:** check `Cache-Control`, `Content-Encoding`, `X-Accel-Buffering`, `Content-Length`, and status.
5. **Add layers back one by one:** call through ingress, gateway, and CDN in order to find where delay starts.
6. **Disable response buffering on the right route:** configure the specific proxy and verify no other policy overrides it.
7. **Check compression/caching:** temporarily disable on a test endpoint to measure impact.
8. **Check the client:** use `ReadableStream`/`EventSource` or WebClient `bodyToFlux`; avoid `text()`, `json()`, or `bodyToMono(String.class)` when early reading is needed.
9. **Measure timestamps:** record when the server emits, when the client receives the first byte, when the parser completes an event, and when the UI renders.
10. **Check timeouts/cancellation:** verify whether the proxy closes idle connections or the client cancels the subscription.

Do not use `doOnNext` logs in a controller as proof the client received bytes. That callback only indicates an item passed a point in the application pipeline.

## 13. Useful measurements and metrics

Distinguish the latencies:

| Metric | Measured from → to | Meaning |
| --- | --- | --- |
| Time to first server item | Handler subscribe to first item | Does the reactive source emit early? |
| Time to first response byte | Request start to first byte at client | Are server/transport/proxy delaying? |
| Time to first event | Request start to fully parsed event | Are framing and client parser working? |
| Inter-event delay | Gap between two events received by client | Is the stream steady? |
| Time to first render | Request start to UI displaying event | Actual user experience |

You can track Reactor Netty metrics such as `reactor.netty.http.server.response.time`, `reactor.netty.http.server.data.sent.time`, active connections/streams, and bytes sent. Server metrics do not replace client measurements because proxies and networks sit outside the process.

When testing, record client-side timestamps for each event. Do not measure only total completion time: a five-second stream might emit the first event after 100 ms or emit everything at the fifth second.

## 14. Common mistakes and fixes

**Mistake 1 — Thinking `Flux` means flushing per item.** Flux describes multiple values; the writer and media type decide encode/flush strategy. Use SSE or flush groups when needed.

**Mistake 2 — Using `collectList()` on an infinite stream.** The Publisher never completes, so the client never gets a result. Process item by item and manage stream lifecycle.

**Mistake 3 — Returning `application/json` while the client expects immediate events.** JSON documents are usually parsed by clients after the body completes. Use SSE or NDJSON per the contract.

**Mistake 4 — Server flushes but Nginx still buffers.** Turn off `proxy_buffering` on the streaming location or use `X-Accel-Buffering: no` if the proxy permits.

**Mistake 5 — Only disabling `proxy_request_buffering`.** That directive governs the request body. Response streams require checking `proxy_buffering`.

**Mistake 6 — Forgetting CDN/ingress/service mesh.** Another intermediate proxy can still buffer. Check every hop.

**Mistake 7 — Using `bodyToMono(String.class)` or `response.text()`.** These APIs collect the entire body. Use Flux or ReadableStream to read incrementally.

**Mistake 8 — Assuming one read equals one event.** TCP and HTTP framing do not preserve Publisher item boundaries. Parse newlines or SSE blank-line framing.

**Mistake 9 — Compression coalescing multiple small events.** Measure with compression on/off; only disable on streaming routes if there is clear benefit and the bandwidth cost is acceptable.

**Mistake 10 — Caching streaming responses.** Caches may hold or replay responses unexpectedly. Use proper cache policies and avoid ordinary caching for SSE.

**Mistake 11 — Not sending heartbeats on long-silent connections.** Proxies have idle timeouts and may close connections. Send sensible heartbeats or tune timeouts.

**Mistake 12 — Flushing too frequently.** Flushing every byte increases overhead. Flush on meaningful event/record boundaries instead of every tiny write.

**Mistake 13 — Setting a fixed Content-Length on an unknown-size stream.** Let the server manage framing; do not manually set length without knowing the exact full body.

**Mistake 14 — Manually adding `Transfer-Encoding: chunked` on HTTP/2.** Chunked is HTTP/1.1 framing. Let the server handle protocol framing.

**Mistake 15 — Blocking the event loop with `block()` or `Thread.sleep`.** The handler cannot emit events on schedule and other connections are affected too. Use non-blocking Publishers and appropriate schedulers for blocking work.

**Mistake 16 — Not handling cancellation.** Closing a tab or proxy disconnects can cancel the subscription. Attach cleanup with `doFinally` and release resources.

**Mistake 17 — Trying to change status after the response is committed.** Once the first event has been sent, you cannot replace status/body with a new JSON error response. Use protocol-level error events or terminate the stream.

**Mistake 18 — Using server logs as the final conclusion.** The server emitting events does not prove the browser receives and renders them. Always verify from the client across the whole path.

## 15. Self-check exercises

1. Why might the server flush yet the browser still not see events? **Buffers may still exist in Netty, TLS/sockets, proxies, client libraries, or UI.**
2. How does `writeAndFlushWith` differ from `writeWith`? **It accepts Publisher groups and flushes after each group.**
3. Does `Flux<T>` automatically guarantee per-item flushing? **No; writer, media type, and configuration decide.**
4. Which media type suits one-way server-to-browser events? **`text/event-stream` (SSE).**
5. Why is `collectList()` unsuitable for infinite streams? **It waits for the source to complete before emitting the List.**
6. What is Nginx `proxy_buffering` default? **`on`.**
7. Which directive disables response buffering in Nginx? **`proxy_buffering off`.**
8. Which header can control per-response buffering in Nginx? **`X-Accel-Buffering: no`.**
9. Which direction does `proxy_request_buffering` control? **Request body from client to upstream.**
10. What does `curl -N` do? **Disables curl's own output buffering; it does not change server/proxy buffering.**
11. Does `Response.text()` process chunked events immediately? **No; it waits for the full body as text.**
12. Which browser API reads responses incrementally? **`Response.body` as a ReadableStream.**
13. Does one TCP segment correspond to one SSE event? **No; clients must parse SSE framing.**
14. Does `Cache-Control: no-transform` solve all proxy buffering? **No; proxies must be configured and each layer tested.**
15. When a stream stays silent for long periods, what helps avoid idle timeouts? **Heartbeats and appropriate timeouts.**
16. Why measure time-to-first-event on the client? **To verify data truly arrives at the consumer, across both proxies and clients.**

## 16. Key takeaways and official references

- **Streaming is an end-to-end property.** A Publisher emitting items early does not guarantee the client sees them early.
- **Buffering** holds data; **flush** asks to push data down; **backpressure** regulates demand; **framing** defines record boundaries.
- Flux does not guarantee per-item flushing. SSE and `writeAndFlushWith` let you express explicit flush boundaries.
- Reactor Netty, TLS, sockets, TCP, proxies, CDNs, and clients can all affect latency.
- Nginx enables `proxy_buffering` by default; disable it on streaming endpoints or use `X-Accel-Buffering: no` when permitted.
- `proxy_request_buffering` is the request direction; `proxy_buffering` is the response direction.
- Browser Fetch uses ReadableStream to read incrementally; `text()`/`json()` wait for the whole body.
- `curl -N` helps inspect client output, but compare directly against the application port and through proxies.
- Measure time-to-first-byte, time-to-first-event, and time-to-first-render at the right layers.
- Handle heartbeats, cancellation, timeouts, and errors after the response commits.

Official documentation:

1. [Spring Framework Reference — Return Values in WebFlux](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/return-types.html): reactive return types, streaming media types, and flush behavior.
2. [Spring Framework Javadoc — ServerHttpResponse](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/http/server/reactive/ServerHttpResponse.html): writeWith and writeAndFlushWith.
3. [Reactor Netty Reference — HTTP Server and SSE](https://projectreactor.io/docs/netty/release/reference/http-server.html): HTTP server, SSE flush strategy, compression, transport, and metrics.
4. [Nginx Documentation — ngx_http_proxy_module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html): proxy_buffering, buffer size, and X-Accel-Buffering.
5. [MDN — Using the Fetch API](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch): response body, ReadableStream, and reading responses incrementally.
6. [MDN — Streams API](https://developer.mozilla.org/en-US/docs/Web/API/Streams_API): chunk processing, cancellation, and browser-side backpressure.
