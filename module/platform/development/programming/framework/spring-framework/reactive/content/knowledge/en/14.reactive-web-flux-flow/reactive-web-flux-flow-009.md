# Boundaries Between Network Events, Codecs, and Business Processing

**Context:** Spring Framework Reactive → **WebFlux processing flow**.

A WebFlux request passes through many layers before the data becomes Java objects that a service can process. On the way in, the server receives bytes from the HTTP connection, the adapter turns I/O into reactive signals, codecs read bytes and decode content, and only then do controllers/services work with DTOs or domain objects. On the way out, the business result passes through encoders/HTTP message writers, is converted into bytes, and is sent over the transport to the client.

The key point is that **network events, byte buffers, decoded items, and business events are four different concepts**. One TCP packet does not correspond to one JSON object; one `DataBuffer` does not necessarily contain one complete event; one `onNext(Dto)` does not prove the client has finished rendering or business processing. Understanding these boundaries correctly helps you design streaming, backpressure, validation, error handling, cancellation, and memory management accurately.

## 1. Map of request and response processing

```text
CLIENT
  │ HTTP bytes (TCP or QUIC; possibly through TLS/proxy)
  ▼
SERVER ADAPTER (Reactor Netty or another non-blocking adapter)
  │ converts I/O into request/response abstractions
  ▼
HttpHandler → WebHandler chain → WebFilter
  │
  ▼
DispatcherHandler / RouterFunction
  │ finds handler and prepares arguments
  ▼
HttpMessageReader + Decoder
  │ DataBuffer → content → DTO
  ▼
CONTROLLER / HANDLER
  │ Publisher<DTO>
  ▼
APPLICATION SERVICE
  │ validation, authorization, domain rules, persistence
  ▼
Publisher<DomainResult>
  │
  ▼
Encoder + HttpMessageWriter
  │ DTO/domain result → DataBuffer / HTTP content
  ▼
SERVER ADAPTER → NETWORK → PROXY → CLIENT
```

This is an architectural model, not a list of threads or a fixed call sequence for every server. WebFlux has two main programming models:

- **Annotated controllers:** declared with `@RestController`, `@GetMapping`, `@PostMapping`; the framework finds the handler, decodes arguments, and writes the response.
- **Functional endpoints:** use `RouterFunction` and `HandlerFunction`; the application describes routes and handlers with functions.

Both rely on the same reactive web foundation and Spring's HTTP/codec abstractions.

| Layer | Responsibility | Typical data |
|---|---|---|
| Server adapter | Receives/sends I/O from the server runtime | ByteBuffer, ByteBuf, socket events |
| `HttpHandler` / `WebHandler` | Request/response bridge and web filter chain | `ServerHttpRequest`, `ServerHttpResponse` |
| Dispatcher / Router | Selects controller or handler | Path, method, headers |
| `HttpMessageReader` / Decoder | Reads HTTP body and decodes | `DataBuffer` → DTO |
| Controller / Handler | Coordinates request, produces response publisher | `Mono<Dto>`, `Flux<Dto>` |
| Service/domain | Executes business rules | Command, event, entity, result |
| Encoder / `HttpMessageWriter` | Encodes response body | DTO → `DataBuffer` |
| Transport/proxy/client | Transfers bytes and consumes response | HTTP frames, network buffers |

Spring provides `HttpHandler` as the request-handling contract with non-blocking I/O and Reactive Streams backpressure; adapters connect that contract to the server runtime. Codecs read/write content via `DataBuffer`. See [Spring WebFlux Reactive Core](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html).

## 2. Distinguishing four kinds of events

When debugging a WebFlux flow, identify which kind of data you are talking about:

1. **Network event / transport bytes:** bytes received or sent by TCP/QUIC and the HTTP implementation. They carry no domain meaning.
2. **Buffer event:** a `DataBuffer` or `ByteBuf` holding a slice of bytes. A buffer may contain part of a message, multiple partial messages, or an arbitrary boundary depending on the layer.
3. **Codec output:** the Java object produced by the decoder, for example `EventDto`. This is the application's unit of data after decoding.
4. **Business event:** an event or command with business meaning after the application validates, checks, and applies domain rules, for example `OrderAccepted`.

Example where the client sends NDJSON:

```text
{"id":"e-1","amount":10}\n
{"id":"e-2","amount":20}\n
```

The application may receive bytes across multiple socket reads. One buffer might end in the middle of the string `"amount"`; the next buffer continues the remainder. The decoder recognizes NDJSON record boundaries, creates two DTOs, and then the service may produce two business results. You must not assume each socket read is one JSON line.

### Boundaries do not map 1:1

| Observation | May be true | Must not be inferred |
|---|---|---|
| One TCP packet arrived | Some bytes reached the TCP layer | One JSON object is complete |
| One HTTP/2 DATA frame arrived | One content chunk of the stream arrived | One DTO has finished decoding |
| One `DataBuffer` is emitted | A byte slice is ready for the codec | A whole message/event |
| One `onNext(EventDto)` | The decoder produced one DTO | The service saved the event or the client processed it |
| A response write completed at the adapter | One write layer received the data | The browser rendered it or the user saw it |
| The client sent a TCP ACK | Bytes were acknowledged by the peer's TCP per protocol | The business operation committed or was confirmed |

TLS, HTTP framing, compression, buffering, proxies, and network segmentation can all split or coalesce data. Message boundaries must be defined by the protocol and codec, not packet boundaries.

## 3. Server adapters, HttpHandler, and the filter chain

WebFlux is not restricted to running on only one server type. Depending on dependencies and configuration, the reactive web stack can be wired to Reactor Netty or the non-blocking adapters of several servers/Servlet containers.

`HttpHandler` provides the low-level contract for requests and responses. `WebHandler` builds a higher-level web processing chain; `WebFilter` can run shared logic such as security, tracing, CORS, or correlation IDs. With annotated controllers, `DispatcherHandler` coordinates finding the handler and invoking the handler adapter. With functional endpoints, the router selects the `HandlerFunction`.

A `WebFilter` illustrating attaching a correlation ID:

```java
@Component
public class CorrelationFilter implements WebFilter {
    @Override
    public Mono<Void> filter(ServerWebExchange exchange,
                             WebFilterChain chain) {
        String id = exchange.getRequest().getHeaders()
                .getFirst("X-Request-Id");

        if (id == null || id.isBlank()) {
            id = UUID.randomUUID().toString();
        }

        exchange.getResponse().getHeaders().set("X-Request-Id", id);
        String requestId = id;

        return chain.filter(exchange)
                .contextWrite(context ->
                        context.put("requestId", requestId));
    }
}
```

This is a snippet that needs imports and Spring component configuration. `contextWrite` puts data into the Reactor Context for downstream operators to read with `deferContextual`. Do not rely on ordinary `ThreadLocal` to carry context across every scheduler boundary.

Filters run at the request boundary, suited to cross-cutting logic. They should not read the body themselves and create a separate subscription to log it, because the request body is a publisher with a specific lifecycle and ownership; improper consumption can leave the controller with no body to read.

## 4. Codecs: from DataBuffer to DTO and back

Spring separates encoding/decoding into abstractions:

- `Encoder<T>` and `Decoder<T>` handle content conversion independently of HTTP.
- `HttpMessageReader<T>` reads HTTP message content and produces objects.
- `HttpMessageWriter<T>` writes objects into HTTP response content.
- `DataBuffer` is the abstraction for a byte region; implementations may be backed by Netty `ByteBuf` or `ByteBuffer`.

Request flow:

```text
Flux<DataBuffer>
       │
       ▼
Decoder / HttpMessageReader
       │
       ├── parse framing / character encoding
       ├── deserialize JSON / NDJSON / form / SSE ...
       ▼
Flux<EventDto>
```

Response flow:

```text
Mono<Dto> or Flux<Dto>
       │
       ▼
Encoder / HttpMessageWriter
       │
       ├── serialize object
       ├── select content type / format
       ▼
Publisher<DataBuffer>
       │
       ▼
HTTP adapter
```

Controllers usually do not need to call encoders themselves or manipulate bytes. The framework chooses the reader/writer based on the argument/return value type, content type, Accept header, and configured codecs.

Foundational docs: [Spring Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html) and [WebFlux codec configuration](https://docs.spring.io/spring-framework/reference/web/webflux/config.html).

## 5. Request body: Mono, Flux, and how the Java type affects reading

Example controller receiving a JSON object:

```java
@PostMapping("/profile")
public Mono<ProfileDto> save(@RequestBody Mono<ProfileDto> body) {
    return body.flatMap(profileService::save);
}
```

`Mono<ProfileDto>` represents one decoded object or error/empty per the publisher's contract. The framework manages reading the request body and the necessary subscription.

With a stream of records:

```java
@PostMapping(
        path = "/events",
        consumes = MediaType.APPLICATION_NDJSON_VALUE)
public Mono<Void> ingest(@RequestBody Flux<EventDto> events) {
    return events.concatMap(eventService::process).then();
}
```

`Flux<EventDto>` allows processing elements as a stream. `concatMap` subscribes to each processing operation and waits for the inner publisher to complete before moving to the next item; `then()` returns a `Mono<Void>` that completes only when the chain succeeds.

| Argument type | Meaning at the application layer | Considerations |
|---|---|---|
| `@RequestBody Mono<Dto>` | One body object | Fits a single command/resource |
| `@RequestBody Flux<Dto>` | Multiple items processable as a stream | Must define framing, validation, and per-item limits |
| `@RequestBody Mono<List<Dto>>` | A collection already gathered into a list | Memory grows with the whole collection; needs limits |
| `@RequestBody String` | Text content already read/decoded | Unsuitable for large bodies if it must be aggregated |
| `@RequestBody Flux<DataBuffer>` | Raw byte buffers | Application is responsible for parsing and managing buffers properly |

**Do not choose `Mono<List<T>>` just because JSON has square brackets.** If the request is large or the stream is long, the collection type means the application needs the entire list before processing in that style. `Flux<T>` is appropriate when items can be processed individually and the codec supports the chosen streaming format.

### JSON array, NDJSON, and SSE

- **JSON array** has the structure of a single JSON document containing multiple elements. A decoder may decode elements into a `Flux<T>`, but you must not assume the client/server flushes each element like NDJSON.
- **NDJSON** separates records by newlines, suited for many consecutive JSON objects in one body.
- **SSE** uses a text event format with fields such as `data:`, `id:`, and a blank line terminating each event. WebFlux has codec support for Server-Sent Events.
- **Multipart/form-data** has its own framing and storage; large files need streaming and size limits considered.

Media type is part of the API contract. Sending a JSON object while declaring NDJSON, or sending SSE without valid SSE framing, will keep the decoder/client from interpreting the content correctly.

## 6. Response body: how DTOs are written into bytes

A controller can return `Mono<Dto>` or `Flux<Dto>`:

```java
@GetMapping("/profile/{id}")
public Mono<ProfileDto> getProfile(@PathVariable String id) {
    return profileService.findById(id);
}

@GetMapping(path = "/events", produces = MediaType.APPLICATION_NDJSON_VALUE)
public Flux<EventDto> events() {
    return eventService.streamEvents();
}
```

`Mono<ProfileDto>` usually represents a single response object. `Flux<EventDto>` can represent a sequence of elements encoded according to the chosen media type. The writer handles serialization and sends the content through the server adapter.

**One `onNext` does not mean one socket write or one packet.** The encoder can produce one or more DataBuffers; the adapter, TLS, and network can coalesce or split bytes. Even with streaming formats, when the client sees each item depends on flush policies, buffering, and transport.

When returning `Flux<T>` with `application/json`, the response usually takes the form of a JSON array. Depending on the writer and configuration, data may be written incrementally; however, the client parser may still wait for the complete document before surfacing individual objects to the application layer.

NDJSON or SSE expresses record/event boundaries more clearly for streaming consumers. With SSE, Reactor Netty has a strategy for flushing each element of the publisher when using the SSE response API; proxies/clients can still buffer at other layers.

### Do not subscribe yourself in the controller

The controller should return the publisher to the framework:

```java
@GetMapping("/feed")
public Flux<EventDto> feed() {
    return eventService.streamEvents();
}
```

Do not do this:

```java
@GetMapping("/feed")
public Mono<Void> wrong() {
    eventService.streamEvents().subscribe();
    return Mono.empty();
}
```

The wrong snippet creates a detached subscription; the HTTP response may complete before the feed finishes processing, and errors and cancellation no longer belong to the response. If the work is part of the response, compose and return the publisher.

## 7. The boundary between codecs and business logic

Codecs are responsible for transforming **representation**; services are responsible for checking and enforcing **business meaning**.

Example JSON request:

```json
{
  "eventId": "evt-100",
  "accountId": "acct-7",
  "amount": 250
}
```

After the decoder creates `TransferRequest`, the service still needs to check:

1. Are the structure and required fields valid?
2. Are the types and value ranges right?
3. Does the caller have permission to perform the action?
4. Does the account exist and is it in an allowed state?
5. Are the balance, limits, and business rules satisfied?
6. Does the request have an idempotency key or event ID to prevent duplicate processing?
7. Are data writes and event publishing inside an appropriate transaction/outbox?

Successful JSON parsing **does not mean valid business logic**. A request can be syntactically valid yet rejected for a business rule. Distinguish representation errors, validation errors, and domain failures to map appropriate HTTP statuses.

### A DTO is not necessarily a domain entity

Treat DTOs as transport structures. Converting to commands/value objects/domain models at the application boundary keeps the domain independent of field names, Jackson annotations, or HTTP formats. For small APIs, DTOs may be used directly in services; for complex domains, separating layers helps control change and security.

Do not bind requests directly into persistence entities with permission to update every field. That can let clients modify internal fields, status, or ownership that the API never intended to expose.

## 8. Processing multiple events: ordering, concurrency, and backpressure

After the codec emits `Flux<EventDto>`, how you compose the service determines speed and business ordering.

### concatMap: sequential

```java
Flux<ProcessedEvent> result = incoming
        .concatMap(event -> service.process(event), 1);
```

Inner publishers are processed sequentially; the next item waits for the previous item to finish. Appropriate when update ordering on the same aggregate matters or when limiting concurrent work per subscription.

### flatMap: allows concurrency

```java
Flux<ProcessedEvent> result = incoming
        .flatMap(event -> service.process(event), 8);
```

Up to eight inner publishers are managed concurrently under this overload. Results may interleave by completion time; input order is not guaranteed. The number 8 is not a limit on total connections, bytes, DB pool, or the whole system.

### flatMapSequential: runs concurrently while preserving output order

```java
Flux<ProcessedEvent> result = incoming
        .flatMapSequential(event -> service.process(event), 8);
```

The operator can subscribe to multiple inner publishers concurrently while preserving output emission order matching the source order; earlier-completing results may have to wait in a buffer. Bound concurrency and understand the buffering cost.

### Buffering does not turn into durable processing

- `buffer(n)` groups multiple items into a collection; reduces downstream call count but increases memory per batch.
- `collectList()` collects the entire stream before emitting one list; unsuitable for infinite sources or unbounded large bodies.
- `publishOn` creates a scheduler boundary and has its own prefetch/buffer.
- `limitRate` adjusts upstream requests at the operator's position; it does not cap total network bytes or all queues.
- `onBackpressureBuffer` needs clear bounds and overflow policies; an unbounded buffer can lead to OOM.

Backpressure regulates demand between supporting publishers/subscribers; it does not replace request quotas, payload limits, concurrency limits, database pools, or durable queues.

## 9. DataBuffer and memory ownership

`DataBuffer` is an important abstraction because codecs and the HTTP layer operate on bytes. With Reactor Netty, buffers may be backed by pooled, reference-counted Netty `ByteBuf`s. Therefore, **buffers have lifecycles and ownership**, and are not always freely garbage-collected byte arrays.

Practical rules:

- In ordinary controllers receiving DTOs via `@RequestBody`, let the framework/codec manage buffers.
- When handling `Flux<DataBuffer>` yourself, identify clearly who owns the buffer and when it is released.
- If retaining a buffer for later processing, ensure release on complete, error, and cancel paths.
- When operators drop items, check discard support and release pooled buffers properly.
- Avoid calling `retain()` unless you need to hold a reference across an ownership boundary; if retained, there must be a matching release.
- Do not release a buffer twice and do not read a buffer after it has been released.

### When you need to join the body into one buffer

`DataBufferUtils.join(...)` can join multiple buffers into a composite buffer. When limits are needed, use the overload with `maxByteCount` to avoid unbounded body aggregation.

```java
Mono<String> bodyText = DataBufferUtils
        .join(request.getBody(), 1024 * 1024)
        .map(buffer -> {
            try {
                byte[] bytes = new byte[buffer.readableByteCount()];
                buffer.read(bytes);
                return new String(bytes, StandardCharsets.UTF_8);
            }
            finally {
                DataBufferUtils.release(buffer);
            }
        });
```

This is a snippet for **intentionally aggregating a body up to 1 MiB**; it requires `ServerHttpRequest`, `DataBufferUtils`, `StandardCharsets`, and Reactor imports. The joined buffer is released after reading. In real applications, if you can process item by item, stream instead of aggregating the entire body.

### doOnDiscard when operators may drop DataBuffers

```java
Flux<DataBuffer> filtered = body
        .filter(this::isRelevant)
        .doOnDiscard(DataBuffer.class, DataBufferUtils::release);
```

This is a snippet requiring checks of ownership and operator discard support. `doOnDiscard` is a hook for elements dropped in operators that support discard; it is not a way to release every buffer on every path. Do not mechanically add release hooks to ordinary DTO pipelines.

Detailed documentation: [Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html).

## 10. Codec limits and request protection

Codecs may need to buffer in order to decode an object, aggregate form/multipart, or handle non-streaming content. Configuring `maxInMemorySize` helps bound certain codec aggregation operations:

```java
@Configuration
public class CodecConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs()
                .maxInMemorySize(256 * 1024);
    }
}
```

This is an example configuring a 256 KiB limit for the cases where the codec applies it; the number is only illustrative and must be chosen based on real payloads and codecs. With Spring Boot, when only partial customization is needed, use `WebFluxConfigurer` without adding `@EnableWebFlux` to preserve Boot's customizations.

**maxInMemorySize is not the application's total RAM quota.** It does not automatically bound every DataBuffer, Netty direct memory, operator queues, service-created objects, `collectList()`, or proxy buffers.

Beyond codec limits, production typically needs:

- Request body byte limits and multipart/file size limits.
- Per-event/record size limits and an appropriate JSON depth limit.
- Concurrent request/stream limits, rate limits, and timeouts.
- Service concurrency and connection pool limits.
- Queue/buffer limits by both item count **and** bytes when payloads have variable sizes.
- Explicit overload policies: reject, error, drop/latest, or persist into a durable queue.
- Authentication/authorization before processing business commands.
- Monitoring direct memory, heap, queues, latency, and connection counts.

## 11. Error boundaries: network, codec, validation, and business

Not every error is of the same kind. Distinguish where an error arises to return the right HTTP status and logs.

| Layer | Example | Common handling approach |
|---|---|---|
| Network / server adapter | Client reset, timeout, TLS handshake failure | Observe transport, timeouts, connection lifecycle |
| HTTP protocol | Invalid method/path/header/framing | HTTP server/protocol handling |
| Codec / deserialization | Malformed JSON, wrong field type, decode limit exceeded | 400 or appropriate representation error |
| Validation | Missing field, negative amount, business format failure | 400/422 per API contract |
| Authorization | User lacks permission on the resource | 401/403 |
| Domain | Account closed, limit exceeded, disallowed state | 409/422 or status per contract |
| Persistence / dependency | DB unavailable, downstream timeout | 5xx, bounded retry if safe |
| Response encoding | Object cannot be serialized or buffer error | Response stream may fail mid-way |
| Client disconnect | Consumer closes connection while stream is running | Cancellation/transport signal, not treated as a business error by default |

### Before and after the response commits

If an error occurs **before response headers/body are committed**, the framework usually still has the ability to create an error response with an appropriate status/body.

If an error occurs **after a streaming response has begun**, the status and headers may already have been sent. The server cannot go back and change HTTP 200 to 500 or replace the entire response with a JSON error document. The stream may end abnormally; the client must recognize the error via the application protocol (if needed) or reconnect/resume.

With SSE, if you want to report a business error in an event, define an event type/error payload in the SSE contract. A reactive `onError` does not automatically become a valid SSE event.

Do not mindlessly use `onErrorComplete()` to mask malformed JSON errors as an "empty body". Also do not convert database errors into `Mono.empty()` if empty means "not found". Keep the distinction between missing data, invalid data, and dependency failure.

## 12. Cancellation and the request lifecycle

When the client disconnects or stops receiving the response, the adapter can cancel the response body subscription. Cancellation can propagate up through the publisher chain to active inner publishers, if the operators and sources support it.

```java
@GetMapping(path = "/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<Update>> stream() {
    return updateService.stream()
            .map(update -> ServerSentEvent.builder(update).build())
            .doOnCancel(() -> log.info("stream cancelled"))
            .doFinally(signal -> log.debug("stream finished: {}", signal));
}
```

This is a snippet; service, DTO, and logger are required. `doOnCancel` observes cancellation; `doFinally` observes complete, error, or cancel. These hooks serve observability; real resources should be managed with publisher-scoped lifecycles such as `using`/`usingWhen` or appropriate transaction/resource operators.

**Cancellation is not rollback.** If the service has already sent a command to a database or payment provider, cancelling the request does not guarantee external side effects are undone. For important write operations, you need idempotency, transactions, outbox, job state, and reconciliation.

If a task must continue even if the client closes the connection, extract it into a job with its own owner (a durable queue/background worker) and return a job ID. Do not call `subscribe()` yourself in a controller to turn part of a response into an ownerless fire-and-forget.

## 13. Functional endpoints: same boundaries, different declaration

A functional endpoint can read the body as a publisher using `bodyToFlux`:

```java
@Bean
RouterFunction<ServerResponse> eventRoutes(EventService service) {
    return RouterFunctions.route()
            .POST("/events",
                    request -> request.bodyToFlux(EventDto.class)
                            .concatMap(service::process, 1)
                            .as(results -> ServerResponse.ok()
                                    .contentType(MediaType.APPLICATION_NDJSON)
                                    .body(results, ProcessedEvent.class)))
            .build();
}
```

This is a snippet needing the `EventDto`/`ProcessedEvent` types, service, and imports. `bodyToFlux` still relies on codecs to convert request content into objects; `ServerResponse.body` uses writers/encoders to convert the result publisher into response content. Changing the programming model does not change the bytes → codec → business → writer boundaries.

## 14. Standalone runnable Java 17+ example: codec output → business → response representation

This example uses Reactor Core without starting an HTTP server. It simulates the **middle part of the WebFlux pipeline after codecs have produced DTOs and before the HTTP writer sends bytes**. That way, the output is deterministic and focuses on the processing boundaries.

Structure:

```text
webflux-boundary-demo/
├── pom.xml
└── src/main/java/demo/WebFluxBoundaryDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>webflux-boundary-demo</artifactId>
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

File `src/main/java/demo/WebFluxBoundaryDemo.java`:

```java
package demo;

import java.util.List;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class WebFluxBoundaryDemo {

    record EventDto(String id, int amount) { }
    record ProcessedEvent(String id, int acceptedAmount) { }

    private static Mono<ProcessedEvent> process(EventDto event) {
        return Mono.fromSupplier(() -> {
            System.out.println("business: " + event.id());

            if (event.amount() <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }

            return new ProcessedEvent(event.id(), event.amount());
        });
    }

    private static String encode(ProcessedEvent event) {
        return "{\"id\":\"" + event.id()
                + "\",\"acceptedAmount\":" + event.acceptedAmount() + "}";
    }

    public static void main(String[] args) {
        // Represents the Flux<EventDto> produced by HttpMessageReader/Decoder.
        Flux<EventDto> decodedByCodec = Flux.fromIterable(List.of(
                new EventDto("e-1", 10),
                new EventDto("e-2", 20)
        ));

        decodedByCodec
                .doOnNext(event ->
                        System.out.println("codec->dto: " + event.id()))
                .concatMap(WebFluxBoundaryDemo::process, 1)
                .map(WebFluxBoundaryDemo::encode)
                .subscribe(
                        line -> System.out.println("response representation: " + line),
                        error -> System.out.println("processing error: "
                                + error.getMessage()),
                        () -> System.out.println("publisher complete")
                );
    }
}
```

Run from the directory containing `pom.xml` with JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.WebFluxBoundaryDemo
```

**Expected standard output** (excluding Maven messages):

```text
codec->dto: e-1
business: e-1
response representation: {"id":"e-1","acceptedAmount":10}
codec->dto: e-2
business: e-2
response representation: {"id":"e-2","acceptedAmount":20}
publisher complete
```

Explanation:

1. `decodedByCodec` represents the output of the HTTP message reader. In the demo program, DTOs are created upfront with `Flux.fromIterable`; there is no real socket or JSON decoder.
2. `doOnNext` observes each DTO at the codec → application boundary.
3. `concatMap` invokes the business function and waits for each inner `Mono` to complete before the next item.
4. `map(encode)` produces a JSON string representation to illustrate the application result → encoder step.
5. `subscribe` in `main` is the execution boundary of the demo program. In a WebFlux controller, return the publisher so the framework manages the subscription and HTTP response.

The example deliberately does not write HTTP framing, DataBuffer, or TCP itself. Those layers belong to Spring's codecs and server adapters in a real application.

## 15. Testing at the right boundaries

Do not only test the service while ignoring decoders/writers when the problem lies at the HTTP boundary.

- **Service unit tests:** check domain validation, transaction semantics, and per-event processing.
- **StepVerifier:** check item count, terminal signals, ordering, errors, and cancellation in publishers.
- **WebTestClient:** check routes/controllers, content types, request decoding, response encoding, and status.
- **Integration tests through a real server:** check streaming, disconnect, timeouts, TLS, proxies, and transport behavior.
- **Load tests:** check large payloads, bursts, slow clients, many concurrent streams, and memory limits.

Example testing a publisher with StepVerifier:

```java
StepVerifier.create(service.process(new EventDto("e-1", 10)))
        .expectNextMatches(result ->
                result.id().equals("e-1")
                && result.acceptedAmount() == 10)
        .verifyComplete();
```

Example testing a WebFlux endpoint with WebTestClient (snippet inside a test with controller configuration):

```java
webTestClient.post()
        .uri("/events")
        .contentType(MediaType.APPLICATION_NDJSON)
        .accept(MediaType.APPLICATION_NDJSON)
        .bodyValue("{\"id\":\"e-1\",\"amount\":10}\n")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_NDJSON)
        .expectBody()
        .jsonPath("$.id").isEqualTo("e-1");
```

This snippet needs `WebTestClient` and an actual controller; body/response assertions must match the test configuration and NDJSON decoder. For multi-record streams, verify responses line by line or use appropriate exchange/flux assertions rather than assuming a single JSON document.

### Testing client disconnect

To test cancellation, you need a publisher where `doOnCancel` can be observed and a client that closes the response before completion. Use `StepVerifier.thenCancel()` for unit-level lifecycle; use WebTestClient or a real HTTP client for integration. Do not rely on `Thread.sleep` to guess whether the server has received the disconnect.

## 16. Observability: measuring at the right layer

A log line in a controller does not tell you the full state of the network or codecs. Split metrics by boundary:

| Layer | What to observe |
|---|---|
| Server/transport | Active connections, HTTP/2 streams, bytes received/sent, response time, transport errors |
| Codec | Decode/encode failures, body size, aggregate limit errors, serialization latency |
| Application | Items decoded, validation failures, business processing latency, success/failure |
| Queue/concurrency | Pending items/bytes, active inner operations, pool saturation, overflow/drop |
| Lifecycle | Cancellation, timeouts, completion, client disconnect, resource cleanup |
| Client/proxy | Read latency, retries/reconnects, buffered bytes if any, stream lag |

Reactor Netty provides Micrometer metrics. Examples of full names include `reactor.netty.http.server.connections.active`, `reactor.netty.http.server.data.received`, `reactor.netty.http.server.data.sent`, `reactor.netty.http.server.response.time`, and `reactor.netty.bytebuf.allocator.used.direct.memory` metrics. Exact names/availability depend on version and configuration.

**Bytes sent is not a business acknowledgment.** It measures data at the server/transport observation point, and does not prove the client parsed, rendered, saved, or committed the business operation. If business confirmation is required, design an acknowledgment/event ID at the application layer.

## 17. Common mistakes when confusing boundaries

1. **Treating one TCP packet as one JSON object.** Packet segmentation is not message framing; let codecs parse the content.
2. **Treating one DataBuffer as one record.** A buffer may contain half a record or multiple records.
3. **Putting domain logic into a decoder.** Codecs should decode representation; validation and business rules belong to the application/domain layer.
4. **Using `collectList()` on a large body stream.** It gathers every item, potentially growing memory with the request size.
5. **Using `Mono<List<T>>` when streaming is needed.** The collection type forces gathering all data before processing in that style.
6. **Assuming every `onNext` creates a flush or a packet.** Writers/adapters/transports have their own buffering and framing.
7. **Assuming HTTP 200 guarantees every stream event succeeded.** With streaming, the response may have committed before an error occurred on a later item.
8. **Ignoring deserialization errors.** Malformed JSON occurs before or at the codec boundary; it is not a domain validation error.
9. **Collapsing DB errors into empty.** Empty, invalid representation, and dependency failure have different meanings.
10. **Calling `block()` or nested `subscribe()` in a controller.** This breaks request ownership, backpressure, error handling, and cancellation.
11. **Limiting item count while forgetting byte size.** One item can be very large; cap payload and aggregate bytes separately.
12. **Managing DataBuffers manually without releasing.** Pooled buffers can leak direct memory if ownership is unclear.
13. **Releasing buffers owned by the framework.** Can cause double release/use-after-release; only release when your code owns the responsibility.
14. **Retrying errors after the response has committed without considering semantics.** The client may have received part of the stream; retries need event IDs/idempotency and a resume protocol.
15. **Treating cancellation as rollback.** Cancelling a publisher does not automatically reverse transactions or side effects already sent to external systems.
16. **Logging the entire request body in a WebFilter with a separate subscription.** Can consume the body before the controller, create large buffer copies, and expose sensitive data.
17. **Using one codec limit as a total memory cap.** Netty direct memory, operator queues, service objects, and proxy buffers remain outside that limit.
18. **Using unbounded flatMap for every event.** Can spawn too many inner calls, connections, and memory usage; choose concurrency according to downstream capacity.

## 18. Design and review checklist

Before taking a WebFlux endpoint to production, check:

- **Transport:** which server adapter and protocol are running? Is there a proxy/load balancer in between?
- **Framing:** does the body use JSON, NDJSON, SSE, multipart, or a binary protocol? Where are record boundaries defined?
- **Codec:** which reader/writer is selected? Are there custom codecs? Are there limits on aggregate body and record sizes?
- **Memory ownership:** are you manipulating `DataBuffer`/`ByteBuf` directly? Who retains/releases and handles cancel/discard?
- **Request model:** is the body a Mono, Flux, list, or raw buffer? Is anything accidentally aggregating the whole body?
- **Business semantics:** where does validation happen? Transaction per request or per event? Which idempotency key?
- **Ordering/concurrency:** using concatMap, flatMap, or flatMapSequential? What concurrency and prefetch values?
- **Backpressure:** does the source support demand? Which queues are bounded? How is overflow handled?
- **Response format:** does the content type support streaming consumers? Can clients parse each event?
- **Error policy:** how are codec, validation, domain, persistence, and transport errors distinguished?
- **Commit boundary:** do errors occur before or after the response begins sending? Does the client have a resume mechanism?
- **Cancellation:** does disconnect cancel upstream and clean up resources? Are there side effects that must live independently?
- **Security:** are body limits, rate limits, authorization, sensitive logging, and tenant isolation handled?
- **Observability:** do metrics distinguish bytes, DTOs, business events, and acknowledgments?
- **Testing:** have you tested malformed bodies, large payloads, slow clients, disconnects, multiple events, mid-stream errors, and a real proxy?

**Key takeaway:** WebFlux turns HTTP I/O into publishers, but it does not erase the boundaries between transport, codecs, and business logic. **Bytes received are not DTOs; decoded DTOs are not committed business events; a written response is not a client that has finished processing.** Let server adapters and codecs manage framing/serialization, keep business logic in composable publishers/services, and separately control payloads, buffers, concurrency, errors, cancellation, and resource ownership.

## References

- Spring Framework — [Reactive Core: HttpHandler, WebHandler, codecs, and DataBuffer](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html).
- Spring Framework — [Data Buffers and Codecs: ownership, release, and join](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html).
- Spring Framework — [WebFlux annotated controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller.html).
- Spring Framework — [WebFlux configuration and HTTP message codecs](https://docs.spring.io/spring-framework/reference/web/webflux/config.html).
- Spring Framework — [WebClient and codec configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html).
- Project Reactor — [Reactive Streams backpressure and request reshaping](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html).
- Reactor Netty — [HTTP Server: request receive, response send, and metrics](https://projectreactor.io/docs/netty/release/reference/http-server.html).
