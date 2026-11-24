# Distinguishing Flux from Actual Incremental Streaming Responses in Spring WebFlux

## 1. Flux is a publisher, HTTP streaming is data transmission behavior

In Reactor, \`Flux<T>\` is a publisher that can emit **0 to many elements** over time, then complete or emit an error. It describes how the application produces and consumes data according to Reactive Streams.

An HTTP streaming response is behavior at the communication layer: the server sends the response body in multiple parts as data becomes ready, so the client can receive and process each part **before the entire response finishes**.

The two concepts are related but not synonymous:

- \`Flux\` indicates that the handler can produce multiple values asynchronously.
- The HTTP message writer/codec decides how to turn those values into response bytes.
- The media type helps the writer choose the appropriate format and writing strategy.
- The server transport, reverse proxy, gateway, and HTTP client may continue to buffer or batch bytes.
- Only when data actually reaches the client incrementally can the client observe end-to-end streaming.

Therefore, a method returning \`Flux<T>\` **is not enough to conclude** that the browser or client receives each part immediately when the publisher emits \`onNext\`. A \`Flux\` can be collected into a collection, serialized into a single JSON document, and only then sent.

The core point of this lesson is to distinguish three moments in time:

1. The publisher emits an element.
2. Spring encodes and writes bytes to the response.
3. The client actually receives the bytes and can process that piece of data.

If these three moments are separated by buffering, the application still has a reactive pipeline, but the user does not observe a streaming response.

## 2. The path from Flux to HTTP response

In an annotated controller, \`@ResponseBody\` (implied by \`@RestController\`) instructs Spring to serialize the return value through an \`HttpMessageWriter\`. WebFlux uses the codec matching the Java type and media type to write the response.

Model:

~~~text
Controller returns Flux<T>
        |
        v
Reactive Streams subscription
        |
        v
HttpMessageWriter / Encoder
        |
        +-- Chooses format based on Content-Type
        +-- May buffer or encode each element
        +-- May flush after each element
        |
        v
ServerHttpResponse / server transport
        |
        v
Proxy / gateway / load balancer (if any)
        |
        v
HTTP client / browser
        |
        v
Client application reads bytes and processes records
~~~

Each layer can affect when data appears. Spring may write and flush each record, but a proxy may still hold the data for a while before forwarding it. The client may also buffer before displaying or parsing.

Therefore, you need to examine **the publisher, codec, media type, transport, and client**, rather than looking only at the method signature.

## 3. The important difference of application/json

With the default Jackson codec in Spring Framework 6.2, when writing a multi-value publisher such as \`Flux<T>\` with the \`application/json\` media type, \`Jackson2Encoder\` calls \`collectToList()\` by default and serializes that collection into a JSON array.

Example:

~~~java
@GetMapping(value = "/numbers", produces = MediaType.APPLICATION_JSON_VALUE)
public Flux<NumberEvent> numbers() {
    return Flux.interval(Duration.ofSeconds(1))
        .take(5)
        .map(NumberEvent::new);
}
~~~

The publisher emits one value per second, but a typical JSON response looks like:

~~~json
[
  {"value":0},
  {"value":1},
  {"value":2},
  {"value":3},
  {"value":4}
]
~~~

With the default codec, values are collected into a list before being serialized into a JSON array. The client typically receives the body after the publisher completes and the JSON document has been built.

This has an important consequence: if you return a \`Flux\` that **never completes** with \`application/json\`, the encoder waits for the complete collection and cannot close the JSON array. This is not an appropriate format for an infinite stream.

A JSON array is a structured document. The \`[\` character opens it, elements are separated by commas, and \`]\` only appears when the list ends. A client using a standard JSON parser usually needs to receive the full document before it can process the entire array.

You can choose a streaming parser on the client side to process a JSON array token by token, but that does not change the default behavior of the Jackson encoder described above in Spring WebFlux.

**Conclusion:** \`Flux<T>\` combined with \`application/json\` can produce a finite JSON array response, but it is not element-by-element streaming by default.

## 4. application/x-ndjson: each JSON object is a record

NDJSON (Newline Delimited JSON, also known as JSON Lines) represents each record as an independent JSON document on a single line:

~~~text
{"value":0}
{"value":1}
{"value":2}
{"value":3}
{"value":4}
~~~

The common media type is:

~~~http
Content-Type: application/x-ndjson
~~~

With a streaming media type such as \`application/x-ndjson\`, WebFlux's default Jackson encoder encodes, writes, and **flushes each value individually** in line-delimited JSON format. The client can read each line as data arrives without waiting for the entire publisher to complete.

Example:

~~~java
@GetMapping(
    value = "/numbers",
    produces = MediaType.APPLICATION_NDJSON_VALUE
)
public Flux<NumberEvent> numbers() {
    return Flux.interval(Duration.ofSeconds(1))
        .take(5)
        .map(NumberEvent::new);
}
~~~

Each time the publisher emits a \`NumberEvent\`, the encoder converts it to a JSON object, writes the record, and flushes. This is a suitable choice for:

- Exporting large datasets record by record.
- Simple service-to-service event feeds.
- Line-by-line import/export.
- Clients that need to parse each JSON object independently.
- Pipelines that do not require a complete JSON array.

NDJSON is not a JSON array. The client needs to read line by line and parse each line into an object. Do not parse the entire body with a JSON parser expecting a single document.

An NDJSON record must be clearly framed by a newline. If JSON data contains a string with a newline character, the JSON encoder escapes that character inside the string; the newline ending the record remains distinguishable.

## 5. text/event-stream: Server-Sent Events

**Server-Sent Events (SSE)** is a unidirectional streaming format from server to client. Browsers have the \`EventSource\` API to open a connection and receive events over time.

Media type:

~~~http
Content-Type: text/event-stream
~~~

An SSE event can contain the following fields:

- \`data:\` the event payload.
- \`id:\` the event identifier, useful for reconnecting.
- \`event:\` the event type name.
- \`retry:\` the time the client waits before reconnecting.
- Lines starting with \`:\` are comments, commonly used as heartbeats.

Each event ends with a blank line. Example response shape:

~~~text
id:0
event:number
data:{"value":0}

id:1
event:number
data:{"value":1}

id:2
event:number
data:{"value":2}

~~~

Spring WebFlux supports \`Flux<ServerSentEvent<T>>\`. With SSE, the encoder is invoked for each event and the output is flushed so data is delivered without waiting for the stream to complete.

Example:

~~~java
@GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<NumberEvent>> events() {
    return Flux.interval(Duration.ofSeconds(1))
        .take(5)
        .map(index -> {
            NumberEvent data = new NumberEvent(index);
            return ServerSentEvent.<NumberEvent>builder(data)
                .id(Long.toString(index))
                .event("number")
                .build();
        });
}
~~~

If you only need to send data without event id/name/retry/comment, you can return \`Flux<T>\` with \`produces = text/event-stream\`; the \`ServerSentEvent<T>\` wrapper is optional.

### NDJSON or SSE?

| Criteria | NDJSON | SSE |
| --- | --- | --- |
| Media type | \`application/x-ndjson\` | \`text/event-stream\` |
| Record framing | One JSON document per line | Event fields, terminated by a blank line |
| Data | Independent JSON record | Event can have data, id, event, retry, comment |
| Typical client | Service, CLI, stream parser | Browser \`EventSource\`, SSE-capable client |
| Reconnect/event ID | Application-designed | Built-in support for id and \`Last-Event-ID\` per SSE protocol |
| Communication direction | Server response stream | Unidirectional server-to-client |
| Use case | Data export/feed | Notifications, live dashboards, job status |

SSE does not replace WebSocket if the application requires continuous two-way exchange. For bidirectional communication, consider WebSocket or another suitable protocol.

## 6. Comparing three endpoints all returning Flux

The same \`Flux<NumberEvent>\` source can produce three different HTTP response styles depending on the media type:

| Return type | Media type | Default encoder behavior | Client observation |
| --- | --- | --- | --- |
| \`Flux<NumberEvent>\` | \`application/json\` | Collects into a List then serializes a JSON array | Typically receives the array when the publisher completes |
| \`Flux<NumberEvent>\` | \`application/x-ndjson\` | Encodes, writes, and flushes each JSON record | Can read each line as it arrives |
| \`Flux<ServerSentEvent<NumberEvent>>\` | \`text/event-stream\` | Encodes and flushes each SSE event | Receives events over time |

This is the default codec behavior documented in Spring Framework 6.2. If the application registers a custom encoder/writer or changes codec configuration, behavior may differ; check the actual configuration.

It is also important to distinguish \`Flux<T>\` from \`Mono<List<T>>\`:

- \`Flux<T>\` emits each element according to Reactive Streams.
- \`Mono<List<T>>\` emits a single collection after the data has been gathered.
- When using a JSON array, the default encoder may collect a multi-value Flux into a collection before serializing, so the result on the wire is close to a complete array.

## 7. Flush, HTTP chunking, and record boundaries

Several terms are easily confused:

**Write:** the server transfers bytes into the response output pipeline.

**Flush:** asks the output layer to push pending data down to the next layer. With NDJSON/SSE, the default encoder flushes after each record/event.

**HTTP framing:** how HTTP determines how long the response body is and when it ends.

**Record framing:** how the application distinguishes one record from the next, such as newlines in NDJSON or blank lines in SSE.

In HTTP/1.1, a response of unknown size can use \`Transfer-Encoding: chunked\` to frame the message body. Chunked transfer coding is a mechanism for transmitting and determining the length of byte chunks; it **does not define JSON record boundaries** and does not guarantee that each \`onNext\` corresponds to exactly one HTTP chunk.

In HTTP/2, the body is transmitted using DATA frames; \`Transfer-Encoding: chunked\` is not used as in HTTP/1.1. A DATA frame is also framing at the HTTP transport layer, not an application record boundary.

Therefore:

- Seeing the \`Transfer-Encoding: chunked\` header does not prove each Flux item was received individually by the client.
- Not seeing that header does not prove the response is not streaming, especially when using HTTP/2.
- A TCP packet, HTTP chunk, or HTTP/2 DATA frame is not a record boundary that the client should rely on.
- The client must parse according to the application format: newlines for NDJSON, event delimiters for SSE.

## 8. Why can data still be buffered?

Even when the Spring encoder flushes each element, other layers can delay visibility:

1. **Publisher or operator:** \`collectList()\`, \`buffer()\`, \`window()\` combine and aggregate data, or an operator waits for completion before emitting.
2. **Codec:** the media type or a custom writer chooses an aggregation strategy.
3. **Server transport:** data may be batched depending on the I/O implementation and write timing.
4. **Compression:** compression middleware may hold data to build efficient compressed blocks.
5. **Reverse proxy/gateway:** proxy buffering may collect the response before forwarding it.
6. **Load balancer/service mesh:** intermediate layers may apply buffering or timeouts.
7. **Client library:** the client may read the body into a byte array/string before parsing.
8. **Browser UI:** JavaScript may wait for enough data or batch renders.

Therefore, you need to test on the application's actual transmission path, including production proxies and clients. A unit test for the publisher only proves the publisher emits elements over time; it does not prove the browser receives each part immediately.

If using a reverse proxy, check the proxy's buffering configuration. For example with Nginx, response buffering may need to be disabled for streaming endpoints depending on deployment configuration. Do not disable buffering globally without thinking; adjust only the routes that need streaming and run load tests.

## 9. Backpressure: regulating demand, not guaranteeing flush

Reactive Streams backpressure lets the subscriber control how many elements it wants to receive via \`request(n)\`. Reactor propagates demand upstream through operators.

Example:

~~~java
Flux<Long> ticks = Flux.interval(Duration.ofMillis(100))
    .onBackpressureBuffer(100);
~~~

This snippet only illustrates the operator; it creates a buffer of up to 100 elements under the default policy of this overload before overflow is handled. You should not add large buffers to mask a slow consumer.

Backpressure helps the reactive pipeline regulate emission/consumption, but **does not mean** each \`onNext\` immediately becomes a network send or an instant client render. The transport, proxy, and client still have their own buffers.

Principles:

- Avoid \`collectList()\` or \`collectMap()\` on unbounded streams.
- Do not use an unbounded \`onBackpressureBuffer()\` for a source that can emit faster than the consumer.
- Limit concurrency when each event calls a service or database.
- Choose an appropriate overflow policy: bounded buffer, drop, latest, or error, depending on business requirements.
- Measure queue size, latency, dropped events, and consumer throughput.
- Check cancellation when the client closes the connection.

A streaming endpoint must be designed for both source rate and client consumption capacity; simply returning \`Flux\` does not solve overload on its own.

## 10. Cancellation and detecting client disconnects

When a client closes the connection, the server can detect that the response is no longer being consumed and cancel the upstream subscription. However, detection may be delayed if the server has not attempted to write more data or an intermediate connection remains open.

For long or near-infinite streams, Spring recommends sending data periodically to detect client disconnects earlier. With SSE, you can send a comment-only event or empty event as a heartbeat; NDJSON can have a heartbeat record according to the application schema if the client understands that record.

Lifecycle tracking example:

~~~java
Flux<NumberEvent> stream = source()
    .doFinally(signal -> {
        if (signal == SignalType.CANCEL) {
            metrics.incrementClientDisconnects();
        }
    });
~~~

This is an illustrative snippet requiring application \`source()\` and \`metrics\`. \`doFinally\` observes \`ON_COMPLETE\`, \`ON_ERROR\`, or \`CANCEL\`; it does not replace scoped resource cleanup. If the source holds a listener, socket, or handle, attach cleanup to the proper lifecycle.

Do not assume a client disconnect always appears the moment a tab closes. Periodic heartbeats give the server a chance to write data and recognize a broken connection.

## 11. Errors occurring after the response has started

In a streaming response, the status and headers are usually committed before or as the first bytes are sent. If the publisher emits several events and then emits \`onError\`, the server cannot go back to replace status 200 with 500 and write a new JSON error document.

Example:

~~~java
Flux<NumberEvent> stream = Flux.concat(
    Flux.just(new NumberEvent(0), new NumberEvent(1)),
    Flux.error(new IllegalStateException("source failed"))
);
~~~

Once the first two records have been sent, a subsequent error can only terminate the stream abnormally or be represented according to the application protocol. You cannot replace the already-sent body with a complete error response.

Design options:

- Validate predictable errors **before committing the response**.
- Use an error event in SSE if the client protocol understands that event.
- With NDJSON, only send a final error record if the API schema explicitly defines that record type; do not arbitrarily mix error records into the data stream.
- Log and record metrics server-side, attach a request ID, and distinguish upstream errors from client cancellation.
- If the client needs to know whether the entire batch succeeded or failed as a single unit, consider finite buffering/batching and returning a single JSON document after processing completes.

Streaming optimizes latency and incremental processing, but changes how an API surfaces errors. The client must understand that the stream may end before receiving all expected records.

## 12. Complete Java 17+ example with Spring Boot WebFlux

This example creates three endpoints using the same source that emits five elements, one per second:

- \`GET /api/numbers/json\`: returns a JSON array; by default Jackson collects elements and serializes when the Flux completes.
- \`GET /api/numbers/ndjson\`: returns individual JSON records and flushes line by line.
- \`GET /api/numbers/events\`: returns SSE events, each with an ID and event name.

Project structure:

~~~text
flux-http-streaming/
├── pom.xml
└── src/
    ├── main/java/com/example/streaming/
    │   ├── StreamingApplication.java
    │   └── StreamController.java
    └── test/java/com/example/streaming/
        └── StreamControllerTest.java
~~~

File \`pom.xml\` (Spring Boot 3.5.0, Java 17+):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>flux-http-streaming</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

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
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
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

File \`src/main/java/com/example/streaming/StreamingApplication.java\`:

~~~java
package com.example.streaming;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StreamingApplication {

    public static void main(String[] args) {
        SpringApplication.run(StreamingApplication.class, args);
    }
}
~~~

File \`src/main/java/com/example/streaming/StreamController.java\`:

~~~java
package com.example.streaming;

import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/api")
public class StreamController {

    public record NumberEvent(long value) {}

    private Flux<NumberEvent> numbers() {
        return Flux.interval(Duration.ofSeconds(1))
            .take(5)
            .map(NumberEvent::new);
    }

    // A Flux, but application/json is collected into an array by default.
    @GetMapping(
        path = "/numbers/json",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Flux<NumberEvent> jsonArray() {
        return numbers();
    }

    // Each NumberEvent is encoded and flushed as an NDJSON line.
    @GetMapping(
        path = "/numbers/ndjson",
        produces = MediaType.APPLICATION_NDJSON_VALUE
    )
    public Flux<NumberEvent> ndjson() {
        return numbers();
    }

    // Each NumberEvent is sent as an SSE event.
    @GetMapping(
        path = "/numbers/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public Flux<ServerSentEvent<NumberEvent>> events() {
        return numbers().map(value ->
            ServerSentEvent.<NumberEvent>builder(value)
                .id(Long.toString(value.value()))
                .event("number")
                .build()
        );
    }
}
~~~

Run from the \`flux-http-streaming\` directory with JDK 17+ and Maven:

~~~bash
mvn spring-boot:run
~~~

### Testing JSON array

~~~bash
curl -i -H "Accept: application/json" \
  http://localhost:8080/api/numbers/json
~~~

Expected JSON body:

~~~json
[
  {"value":0},
  {"value":1},
  {"value":2},
  {"value":3},
  {"value":4}
]
~~~

The source emits over five seconds, but with the default Jackson encoder, the JSON array is serialized after the publisher completes. This example shows that a \`Flux\` return signature does not by itself guarantee record-by-record streaming.

### Testing NDJSON

~~~bash
curl -N -i -H "Accept: application/x-ndjson" \
  http://localhost:8080/api/numbers/ndjson
~~~

Expected body appears line by line, about one second apart:

~~~text
{"value":0}
{"value":1}
{"value":2}
{"value":3}
{"value":4}
~~~

cURL's \`-N\` option disables client-side output buffering so incremental arrival is easy to observe.

### Testing SSE

~~~bash
curl -N -i -H "Accept: text/event-stream" \
  http://localhost:8080/api/numbers/events
~~~

The body has a structure similar to:

~~~text
id:0
event:number
data:{"value":0}

id:1
event:number
data:{"value":1}

id:2
event:number
data:{"value":2}

~~~

An SSE event ends with a blank line. A browser can use \`EventSource\` to receive events and run callbacks by event type.

On Windows PowerShell, if \`curl\` is mapped to a PowerShell alias, use \`curl.exe\`. If running through a proxy, check whether the proxy buffers before concluding that the encoder is not flushing.

## 13. Testing streaming with WebTestClient and StepVerifier

WebTestClient can return a \`FluxExchangeResult\` for a stream response. Then use \`StepVerifier\` to verify that elements arrive over time.

File \`src/test/java/com/example/streaming/StreamControllerTest.java\`:

~~~java
package com.example.streaming;

import java.time.Duration;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class StreamControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void ndjsonValuesArriveAsSeparateSignals() {
        FluxExchangeResult<StreamController.NumberEvent> result =
            client.get()
                .uri("/api/numbers/ndjson")
                .accept(MediaType.APPLICATION_NDJSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_NDJSON)
                .returnResult(StreamController.NumberEvent.class);

        StepVerifier.create(result.getResponseBody())
            .expectNext(new StreamController.NumberEvent(0))
            .expectNoEvent(Duration.ofMillis(200))
            .expectNext(new StreamController.NumberEvent(1))
            .expectNext(new StreamController.NumberEvent(2))
            .expectNext(new StreamController.NumberEvent(3))
            .expectNext(new StreamController.NumberEvent(4))
            .verify(Duration.ofSeconds(8));
    }

    @Test
    void jsonEndpointReturnsACompleteArray() {
        client.get()
            .uri("/api/numbers/json")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectBodyList(StreamController.NumberEvent.class)
            .hasSize(5);
    }
}
~~~

Run the tests:

~~~bash
mvn test
~~~

The NDJSON test confirms records are decoded into separate signals with a pause between the first two records. The JSON test confirms the endpoint returns a collection of five elements. When running tests on a heavily loaded machine, you can widen the duration and timeout to avoid overly tight scheduler/CI dependencies.

WebTestClient tests verify status, headers, and response body streams in integration tests. To prove behavior through a production proxy/browser, you still need to test end-to-end across the actual deployment path.

## 14. Reading streams on the client side

### WebClient consuming NDJSON

A reactive service can consume each record using \`bodyToFlux\`:

~~~java
Flux<NumberEvent> events = webClient.get()
    .uri("/api/numbers/ndjson")
    .accept(MediaType.APPLICATION_NDJSON)
    .retrieve()
    .bodyToFlux(NumberEvent.class);
~~~

The client can compose:

~~~java
return events
    .doOnNext(this::processEvent)
    .then();
~~~

Do not call \`collectList()\` if the goal is to process each record with bounded memory. If aggregation is needed, use bounded batches or an appropriate aggregation strategy.

### Browser consuming SSE

Browser-side JavaScript example:

~~~javascript
const source = new EventSource("/api/numbers/events");

source.addEventListener("number", event => {
  const value = JSON.parse(event.data);
  console.log("received", value.value);
});

source.onerror = () => {
  console.log("SSE connection interrupted; browser may reconnect");
};
~~~

\`EventSource\` automatically handles some aspects of SSE reconnection. If the server sets \`id\`, the browser can send \`Last-Event-ID\` when reconnecting; the server needs to design resume logic if it wants to continue from the previous event.

NDJSON is usually read with Fetch Streams or an HTTP client supporting incremental body reading; calling an API that reads the entire body into \`text()\` or \`json()\` waits until the response ends and defeats record-by-record processing.

## 15. Choosing a media type by client contract

| Need | Format to consider | Reason |
| --- | --- | --- |
| Return a finite list, client needs one JSON document | \`application/json\` | JSON arrays are easy to use with standard parsers and APIs |
| Send many independent records as data arrives | \`application/x-ndjson\` | Each line is a JSON object, parsed record by record |
| Dashboard/browser receives one-way notifications | \`text/event-stream\` | SSE provides event types, IDs, and reconnection |
| Continuous two-way exchange | WebSocket or another suitable protocol | SSE is server-to-client only |
| Large file download | Byte/Resource response body streaming | Choose a byte-streaming API and manage range/content disposition |
| Client needs to know batch succeeded as a unit | Finite JSON response or bounded batch | Can validate/serialize before committing |

Do not choose a media type just because the controller returns \`Flux\`. Start from how the client needs to parse, handle errors, reconnect, and confirm completion.

## 16. Heartbeats and timeouts for long streams

A stream may emit no business data for several minutes. During that time, a proxy, load balancer, or client may consider the connection idle and close it. The server also has trouble noticing a client disconnect if there is no data to write.

Spring recommends sending periodic data for streaming responses to detect client disconnects earlier. With SSE, a comment-only event can serve as a heartbeat without producing a business event:

~~~text
: keep-alive

~~~

You can choose a heartbeat interval shorter than the idle timeout of the network layers. Do not send heartbeats too frequently, as that increases traffic and parsing work.

With NDJSON, if sending a heartbeat, clearly specify the record schema, for example \`{"type":"heartbeat"}\`; the client must recognize and ignore this record. Do not send an arbitrary line that causes the client to fail parsing into a domain object.

In addition to heartbeats, configure:

- Timeouts on the server, reverse proxy, load balancer, and client.
- Limits on concurrent streaming connections.
- Reconnect and backoff policies.
- Event ID/offset if resuming is required.
- Cleanup on cancel and on server shutdown.

## 17. DataBuffer and streaming raw bytes

In most endpoints, let the codec convert DTOs into bytes. There is no need to manipulate \`DataBuffer\` directly when simply returning \`Flux<DTO>\`.

Only use \`Flux<DataBuffer>\` when the application genuinely needs control over a raw byte stream, such as proxying files or forwarding binary content. In that case, note:

- Some servers such as Reactor Netty use pooled, reference-counted buffers.
- Buffers must be released promptly if the application consumes or retains them itself.
- When discarding buffers in a pipeline, appropriate discard handling must be present.
- Do not hold a DataBuffer longer than its required lifecycle.
- Do not pass a buffer to another thread while ignoring ownership/reference counts.

Structural example when handling buffers manually:

~~~java
Flux<DataBuffer> body = source()
    .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
~~~

This is only an illustrative snippet; \`source()\` and imports must be provided. With standard codecs and DTOs, the framework manages buffers for the application. Do not arbitrarily add manual releases to a DTO pipeline.

## 18. Common mistakes

1. **Seeing a Flux return type and concluding HTTP streaming:** wrong; check the writer, media type, and flush behavior.
2. **Returning an infinite Flux with application/json:** the default Jackson encoder collects into a List and waits for completion, so the JSON array can never finish.
3. **Using a JSON array for an infinite feed:** the client has no complete document to parse in the standard way. Use NDJSON or SSE.
4. **Confusing chunked transfer coding with record framing:** chunked is an HTTP/1.1 body framing mechanism, not a boundary for each Flux element.
5. **Assuming each onNext corresponds to one TCP packet/HTTP chunk:** the transport may coalesce or split bytes. The client parses according to the media type.
6. **Not declaring a streaming media type:** the encoder may choose an aggregation mode suited to the default media type.
7. **Using NDJSON but having the client parse the whole body as one JSON document:** each line is a separate document; parse line by line.
8. **Using SSE but having the client call response.json():** SSE is text/event-stream, requiring EventSource or an SSE parser.
9. **Assuming flush guarantees immediate browser rendering:** proxies, compression, networks, and clients can still buffer.
10. **Not disabling proxy buffering for endpoints needing real-time delivery:** data may be held at the proxy. Check per-route configuration.
11. **Using collectList/buffer on large streams:** increases memory usage and delays the first record. Process element by element or in bounded batches.
12. **Not handling client cancellation:** upstream may continue working if the source does not support cancel or cleanup.
13. **Not sending heartbeats on long-idle streams:** the server may detect disconnects late or intermediate layers may close the connection.
14. **Assuming you can change the HTTP status after the stream starts:** the response is already committed; late errors must be handled according to the stream protocol.
15. **Not distinguishing errors from cancellations:** a client disconnect typically produces a cancellation, not necessarily an application error.
16. **Subscribing manually inside a controller:** detaches work from the response lifecycle and makes cancellation/backpressure hard to control. Return the publisher to WebFlux.
17. **Not bounding concurrency/queues:** a source faster than the consumer can build backlog and increase memory usage.
18. **Manipulating DataBuffer without releasing:** can cause memory leaks with pooled buffers.
19. **Testing only the publisher without testing HTTP:** a publisher emitting elements individually does not prove the codec and proxy deliver them incrementally.
20. **Using WebTestClient and concluding the production proxy does not buffer:** integration tests only check the path in the test environment; end-to-end tests are needed in the deployment environment.

## 19. Checklist for verifying true streaming

When you need to confirm an endpoint delivers incrementally, check in order:

- Does the publisher emit elements spaced over time or were they collected beforehand?
- Has the controller declared an appropriate media type?
- Does the default codec or custom writer encode/flush each element?
- Does the response start writing before the publisher completes?
- Does the client read the body incrementally or wait for \`bodyToMono\`, \`json()\`, \`text()\` to complete?
- Does cURL use \`-N\` to disable output buffering when observing?
- Does the proxy/gateway have response buffering enabled?
- Does compression delay flushing?
- Is the HTTP version in use 1.1 or 2? Do not rely on \`Transfer-Encoding\` to conclude.
- When the client cancels, does upstream stop and are resources cleaned up?
- Does the stream have heartbeats, timeouts, and a reconnect policy?
- If an error occurs after the first record, does the client know how the stream ends?
- Are there WebTestClient/StepVerifier tests and a test over a near-production path?

An endpoint is considered end-to-end streaming only when data genuinely reaches the client incrementally and the client can process it before the publisher completes.

## 20. Self-check questions

**1.** What does \`Flux<T>\` describe? A publisher that can emit 0 to many elements, then complete or error.

**2.** Does returning \`Flux<T>\` guarantee the HTTP response is sent incrementally? No. It also depends on the codec, media type, flush, transport, proxy, and client.

**3.** With the default Jackson encoder, what behavior does \`Flux<T>\` + \`application/json\` have? Collects elements into a List and serializes into a JSON array.

**4.** Which media type is suitable for individual JSON records? \`application/x-ndjson\`.

**5.** Which media type does SSE use? \`text/event-stream\`.

**6.** How are SSE events separated? Fields are written as lines; a blank line terminates the event.

**7.** What does \`ServerSentEvent<T>\` add? Fields such as data, id, event, retry, and comment.

**8.** Why is an infinite Flux with application/json unsuitable? The default encoder waits for the publisher to complete in order to build the JSON array.

**9.** Does flush guarantee the browser receives immediately? No; proxies, networks, and clients can buffer.

**10.** Is HTTP/1.1 chunked the NDJSON record boundary? No. Newlines are the NDJSON record boundary.

**11.** Does HTTP/2 use Transfer-Encoding: chunked? No; HTTP/2 uses DATA frames to carry message content.

**12.** What is used to test a stream with WebTestClient? \`FluxExchangeResult\` combined with \`StepVerifier\`.

**13.** Why are heartbeats needed? To send data periodically and detect client disconnects earlier on long-idle streams.

**14.** Can the status be changed to 500 after the first event has been sent? No; the response is already committed.

**15.** Does backpressure mean each record is flushed immediately? No. Backpressure regulates demand, whereas flush is response-writing behavior.

**Key takeaway:** \`Flux\` only describes a multi-element reactive sequence. With the default Jackson codec, \`application/json\` collects a \`Flux\` into a JSON array; \`application/x-ndjson\` writes and flushes each record; \`text/event-stream\` sends and flushes each SSE event. True streaming also depends on the response writer, server, proxy, and client. Choose the media type by data contract, verify incremental delivery end-to-end, and manage backpressure/cancellation, heartbeats, and errors after the response is committed.

**Official documentation:**
- [Spring Framework 6.2 — Reactive Core, Jackson Encoder and Streaming](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html)
- [Spring Framework 6.2 — @ResponseBody and HTTP Message Writers](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/responsebody.html)
- [Spring Framework 6.2 — ServerSentEvent Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/codec/ServerSentEvent.html)
- [Spring Framework 6.2 — WebTestClient Streaming Responses](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html)
- [Reactor 3.8 — Backpressure](https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html)
- [RFC 9112 — HTTP/1.1 Transfer Coding](https://www.rfc-editor.org/rfc/rfc9112.html)
- [RFC 9113 — HTTP/2 DATA Frames](https://www.rfc-editor.org/rfc/rfc9113.html).