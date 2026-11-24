# Distinguishing JSON Lists from Continuous Data Streams

In Spring WebFlux, `Flux<T>` represents an asynchronous sequence of zero to many elements. However, a controller returning `Flux<T>` does not mean the HTTP response is necessarily sent as multiple independent messages as soon as each element is emitted. How data is encoded and transmitted depends on `Content-Type`, HTTP message codecs, and client behavior.

With standard JSON (`application/json`), multiple elements are usually represented as a single JSON array. With NDJSON, each element is a JSON object on its own line. With Server-Sent Events (SSE), each event has its own `event`, `id`, and `data` framing. Choosing the right format helps clients read data incrementally, reduce buffering, and handle long-lived connections properly.

## 1. Flux Does Not Equal HTTP Streaming

`Flux<T>` is a reactive type on the application side. It describes a publisher that can emit multiple elements over time, complete, or terminate with an error. An HTTP response is a representation on the wire; `Content-Type` and codecs decide how elements are turned into bytes.

There are three concepts to separate:

1. **Reactive sequence:** `Flux<T>` emits elements inside the application according to Reactive Streams signals.
2. **HTTP representation:** JSON array, NDJSON, SSE, or another format determined by the media type.
3. **Network transmission:** the server writes bytes per flush, in chunks, or via the corresponding transport mechanism.

A `Flux<Product>` may be encoded as a complete JSON array. Conversely, a `Flux<ProductEvent>` may be written as multiple NDJSON records or multiple SSE events. Looking at the Java return type alone cannot determine which representation the client will receive.

HTTP chunked transfer encoding is also not synonymous with NDJSON or SSE. Chunking is a byte-transfer mechanism at the HTTP/1.1 layer; it does not define boundaries between JSON records or events. Clients must rely on `Content-Type` and representation framing rather than assuming one network chunk corresponds to one object. HTTP/2 also has its own framing mechanism and does not use `Transfer-Encoding: chunked` the way HTTP/1.1 does.

| Return Type and Media Type | HTTP Representation | How Clients Consume It |
|---|---|---|
| `Mono<Product>` + `application/json` | A single JSON object | Read a single JSON document |
| `Flux<Product>` + `application/json` | A JSON array of multiple objects | Read a single JSON array document |
| `Flux<ProductEvent>` + `application/x-ndjson` | Multiple JSON objects, one per line | Read and parse line by line |
| `Flux<ServerSentEvent<T>>` + `text/event-stream` | Multiple SSE events with explicit framing | Read events via the EventSource protocol |

## 2. JSON List: A Single Document with Array Structure

When an API returns a finite result set, a JSON array is the most common and easiest representation to integrate.

Example response:

```json
[
  {"id": "p-101", "name": "Ballpoint pen"},
  {"id": "p-102", "name": "Notebook"},
  {"id": "p-103", "name": "Ruler"}
]
```

Controller:

```java
@GetMapping(
    value = "/api/products",
    produces = MediaType.APPLICATION_JSON_VALUE
)
Flux<ProductResponse> findAll() {
    return productService.findAll();
}
```

With the default Jackson JSON encoder in current Spring Framework, a multi-value publisher written under `application/json` is collected into a list and serialized as a JSON collection. Thus the client receives a single JSON array document, not independent objects that can be parsed immediately as they arrive.

If the API needs to bound the number of elements, you can express it explicitly with `Mono<List<ProductResponse>>`:

```java
@GetMapping(value = "/api/products", produces = MediaType.APPLICATION_JSON_VALUE)
Mono<List<ProductResponse>> findAll() {
    return productService.findAll().collectList();
}
```

`collectList()` makes clear that the application gathers elements before returning the list. This works well for bounded result sets with controlled sizes. Do not collect an unbounded stream or a very large dataset into memory just to build a JSON array.

### When Should You Use a JSON Array?

- Finite search results or bounded lists.
- Clients need to parse a complete document.
- Clients need to process the entire collection before rendering or updating state.
- APIs with clear pagination, page size, and size limits.

A JSON array is straightforward to describe in OpenAPI: the response schema has `type: array`, and `items` points to the element schema.

## 3. NDJSON: Each Line Is an Independent JSON Object

NDJSON (Newline Delimited JSON), also known as JSON Lines, frames data using newline characters. Each line contains one independent JSON value; APIs typically use an object per record.

Example body:

```text
{"id":"p-101","name":"Ballpoint pen"}
{"id":"p-102","name":"Notebook"}
{"id":"p-103","name":"Ruler"}
```

There are no square brackets wrapping all records. Clients can read line by line, parse each line's JSON, and begin processing before the server finishes sending the entire response.

Spring WebFlux supports JSON streaming media types such as `application/x-ndjson` and `application/jsonl`. With a codec-supported streaming media type, the Jackson encoder writes and flushes each value individually.

Controller:

```java
@GetMapping(
    value = "/api/products/export",
    produces = "application/x-ndjson"
)
Flux<ProductExportRow> exportProducts() {
    return productService.exportRows();
}
```

A WebClient consumer can read NDJSON into individual objects:

```java
Flux<ProductExportRow> rows = WebClient.create("http://localhost:8080")
    .get()
    .uri("/api/products/export")
    .accept(MediaType.parseMediaType("application/x-ndjson"))
    .retrieve()
    .bodyToFlux(ProductExportRow.class);
```

### When Should You Use NDJSON?

- Exporting large datasets record by record.
- Pipelines processing logs, events, or batch data.
- Clients that need incremental processing without waiting for a full JSON array.
- Producers that may emit records over a long period while keeping each record as standalone JSON.

NDJSON has no standard stream-wide metadata such as total item count, page count, or business completion status. If metadata is needed, use headers, a separate endpoint, a typed message envelope, or another clearly defined protocol.

## 4. Server-Sent Events: Unidirectional Event Stream from Server to Client

SSE is a protocol for pushing events from server to browser over a long-lived HTTP connection. Its media type is `text/event-stream`. Each event may include `id`, `event`, `data`, and `retry` fields; fields are separated by newlines, and each event ends with a blank line.

Example response:

```text
id: 101
event: product-updated
data: {"id":"p-101","name":"New ballpoint pen"}

id: 102
event: product-created
data: {"id":"p-102","name":"Notebook"}

```

WebFlux controller:

```java
@GetMapping(
    value = "/api/products/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
Flux<ServerSentEvent<ProductEvent>> watchProductEvents() {
    return productEventService.events()
        .map(event -> ServerSentEvent.builder(event)
            .id(event.id().toString())
            .event(event.type())
            .build());
}
```

If only the `data` field is needed, the controller can return `Flux<ProductEvent>` with `produces = MediaType.TEXT_EVENT_STREAM_VALUE`; the `ServerSentEvent` wrapper is needed when setting id, event name, retry, or comments.

Browser clients can use `EventSource`:

```javascript
const source = new EventSource("/api/products/events");

source.addEventListener("product-updated", event => {
  const product = JSON.parse(event.data);
  console.log("Updated product", product);
});

source.onerror = () => {
  console.log("SSE connection interrupted; browser may reconnect");
};
```

SSE fits notifications, task progress, order status updates, or dashboard data requiring one-way updates. If clients also need to send messages continuously to the server over the same bidirectional protocol, consider WebSocket or another suitable protocol.

## 5. Comparing JSON Array, NDJSON, and SSE

| Criterion | JSON Array | NDJSON | SSE |
|---|---|---|---|
| Media type | `application/json` | `application/x-ndjson` or `application/jsonl` | `text/event-stream` |
| Framing | Single JSON document, usually an array | One JSON value per line | Event frames terminated by a blank line |
| Event metadata | No dedicated standard structure | No dedicated standard structure | Supports `id`, `event`, `retry`, `data` |
| Incremental delivery | Do not assume; default encoder may collect into a list | Yes, each record is written individually | Yes, each event is flushed |
| Termination | End of JSON document | EOF ends the record stream | Connection may stay open long-term; an event does not imply business completion |
| Common clients | `fetch`, `WebClient`, JSON parsers | Line readers, `WebClient.bodyToFlux` | Browser `EventSource`, SSE clients |
| Best suited for | Bounded lists | Exports or record feeds | Real-time unidirectional events |

Choose the format based on how consumers need to receive data, not on whether the service returns `Flux` or `Mono`.

## 6. Content Negotiation and Declaring produces

Spring WebFlux uses `produces` to restrict the representations an endpoint can generate. Clients can send an `Accept` header to request a suitable format.

Example of an endpoint supporting only NDJSON:

```java
@GetMapping(value = "/api/events", produces = "application/x-ndjson")
Flux<ProductEvent> events() {
    return eventService.stream();
}
```

Client:

```http
GET /api/events HTTP/1.1
Accept: application/x-ndjson
```

If a client sends `Accept: application/json` while the endpoint only declares `application/x-ndjson`, Spring may return `406 Not Acceptable`. This is correct content-negotiation behavior; do not silently return a different framing than what the client requested.

If an API needs to support multiple representations, you can declare multiple media types in `produces` and verify that codecs/handlers can produce each representation:

```java
@GetMapping(
    value = "/api/products/feed",
    produces = {
        MediaType.APPLICATION_JSON_VALUE,
        "application/x-ndjson"
    }
)
Flux<ProductResponse> feed() {
    return productService.feed();
}
```

However, an endpoint with multiple representations needs explicit testing with each `Accept` header; do not assume the same client parser can read both a JSON array and NDJSON.

## 7. Codec Configuration Determines How Data Is Written

WebFlux uses `HttpMessageWriter` and codecs to serialize responses. With Jackson, the encoder inspects the media type to decide whether to collect elements or write them one by one.

According to current Spring Framework documentation:

- `Mono<T>` with JSON is serialized as a single value.
- A multi-value publisher with `application/json` is collected into a list by default and serialized as a collection.
- Streaming media types such as `application/jsonl` and `application/x-ndjson` write each element individually and flush.
- With SSE, the Jackson encoder is invoked per event and flushed so data is delivered without waiting for the next event.

Exact behavior depends on the Spring Framework version and configured codecs. If the application registers a custom `Encoder`, `HttpMessageWriter`, or Gson instead of Jackson, check that codec's documentation and tests. Do not infer behavior solely from the name `Flux`.

Example configuring codec memory limits:

```java
@Configuration
class WebFluxCodecConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(ServerCodecConfigurer configurer) {
        configurer.defaultCodecs().maxInMemorySize(2 * 1024 * 1024);
    }
}
```

Codec memory limits affect operations that require aggregation or buffering. Do not raise this limit arbitrarily to mask an endpoint buffering a huge stream in RAM. Choose an appropriate media type and data-processing pattern first.

## 8. Documenting JSON Arrays in OpenAPI

For a finite JSON list, the response schema should be an array whose `items` points to each element's schema.

Example annotation:

```java
@Operation(summary = "List products")
@ApiResponse(
    responseCode = "200",
    description = "Product list as a JSON array",
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        array = @ArraySchema(
            schema = @Schema(implementation = ProductResponse.class)
        )
    )
)
@GetMapping(value = "/api/products", produces = MediaType.APPLICATION_JSON_VALUE)
Flux<ProductResponse> findAll() {
    return productService.findAll();
}
```

Corresponding OpenAPI schema:

```yaml
responses:
  '200':
    description: Product list as a JSON array
    content:
      application/json:
        schema:
          type: array
          items:
            $ref: '#/components/schemas/ProductResponse'
```

springdoc can infer the schema from `Flux<ProductResponse>` in a controller. `@ApiResponse`/`@ArraySchema` makes the representation explicit when inference does not match or when you want control over descriptions.

## 9. Documenting NDJSON in OpenAPI

NDJSON is not a JSON array. Each line is an independent JSON value. OpenAPI can describe the media type and the schema of a single record, while the description explains the line-delimiting rules.

Example:

```java
@Operation(
    summary = "Export product events",
    description = "Response is NDJSON: each line contains an independent ProductEvent JSON object."
)
@ApiResponse(
    responseCode = "200",
    description = "NDJSON record stream",
    content = @Content(
        mediaType = "application/x-ndjson",
        schema = @Schema(implementation = ProductEvent.class)
    )
)
@GetMapping(value = "/api/products/export", produces = "application/x-ndjson")
Flux<ProductEvent> export() {
    return productEventService.export();
}
```

In this example, the schema describes one record per line. The description must clearly state NDJSON framing and how clients read multiple records until EOF. Do not document an NDJSON response as a JSON array if the actual wire format has no `[` and `]` brackets.

OpenAPI describes the media type and data schema, but has no single dedicated field for describing the full semantics of an unbounded NDJSON stream. Use `description`, `example`, and operation documentation to explain newline framing, record ordering, termination conditions, and error handling.

## 10. Documenting SSE in OpenAPI

SSE is a text protocol with framing fields. If a controller returns `Flux<ServerSentEvent<ProductEvent>>`, the `data` part may contain JSON while the overall response remains `text/event-stream`.

Example annotation:

```java
@Operation(
    summary = "Watch product changes",
    description = "Opens an SSE connection; each event has an event name and data containing ProductEvent JSON."
)
@ApiResponse(
    responseCode = "200",
    description = "SSE event stream",
    content = @Content(
        mediaType = MediaType.TEXT_EVENT_STREAM_VALUE,
        schema = @Schema(
            type = "string",
            description = "SSE frames containing id, event, and data; data contains ProductEvent JSON."
        )
    )
)
@GetMapping(value = "/api/products/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<ServerSentEvent<ProductEvent>> events() {
    return productEventService.events()
        .map(event -> ServerSentEvent.builder(event)
            .id(event.id().toString())
            .event(event.type())
            .build());
}
```

The `string` schema here describes the text/event-stream body. `ProductEvent` is the payload of the `data` field, not the entire SSE frame. Clearly explain the `id`, `event`, `data`, and `retry` structure if clients need to consume them.

Example of one event in the description:

```text
id: 101
event: product-updated
data: {"id":"p-101","name":"New ballpoint pen"}

```

Do not declare an SSE response as `application/json` just because the `data` portion is JSON. The media type of the entire stream remains `text/event-stream`.

## 11. Error Handling After a Streaming Response Has Started

With a JSON array collected before serialization, the server can detect certain errors before the body is completely written. With NDJSON or SSE, once the first record or event is sent, the HTTP response may already be committed.

Once a response is committed:

- The server cannot change the status to 500 and replace the body with a Problem Details document as it can before the response starts.
- A mid-stream error may terminate the connection abnormally or omit the final record.
- Clients must distinguish a normal stream completion from a dropped connection.
- If business logic requires protocol-level error notifications, you must define how errors are represented inside the stream.

For SSE, you can define an `error` event with a dedicated payload schema, then end the stream or keep the connection open per policy. For NDJSON, you can define an envelope with a `type` field such as `data`, `error`, `complete`; clients must know how to distinguish those records. Do not add error records to a stream unless consumers are informed of this convention.

Example NDJSON envelope:

```json
{"type":"data","payload":{"id":"p-101","name":"Ballpoint pen"}}
{"type":"data","payload":{"id":"p-102","name":"Notebook"}}
{"type":"error","code":"SOURCE_UNAVAILABLE","message":"Data source temporarily unavailable"}
```

This envelope is an application-defined contract, not a default rule of NDJSON or Spring WebFlux. If used, document the corresponding discriminated union schema in OpenAPI.

## 12. Backpressure, Buffering, and Resource Limits

Reactive Streams provides backpressure so subscribers can signal how many elements they are ready to receive. This coordinates rates between publisher and subscriber inside the reactive pipeline. However, backpressure does not mean every HTTP client or reverse proxy automatically throttles the producer in the same way.

Key principles:

- Do not use `collectList()` on large or unbounded data sources.
- Do not use unbounded `onBackpressureBuffer()` for streams where the producer is faster than the consumer.
- Set limits on record counts, buffers, duration, and concurrency as appropriate.
- Handle cancellation when clients close the connection so unnecessary upstream work stops.
- Monitor metrics for open connections, record emission rates, connection lifetimes, and error counts.
- For long-lived SSE connections, send periodic heartbeats if proxies or load balancers require traffic to keep connections alive.

Example limiting record count:

```java
Flux<ProductEvent> export() {
    return productEventService.events()
        .take(10_000);
}
```

Example limiting stream duration:

```java
Flux<ProductEvent> watch() {
    return productEventService.events()
        .take(Duration.ofMinutes(5));
}
```

Specific limits must match business requirements. Do not apply `take` arbitrarily if the API promises an unbounded stream; publish termination conditions and how clients should reconnect.

## 13. How Do Clients Read Each Format?

### JSON Array

Clients typically wait for a valid JSON document and parse it into a list:

```javascript
const response = await fetch("/api/products", {
  headers: { Accept: "application/json" }
});
const products = await response.json();
```

### NDJSON

Clients must read the response body in chunks, buffer partial lines, and parse each complete line. Do not assume each network chunk always corresponds to exactly one line or one record.

Java WebClient example:

```java
Flux<ProductEvent> events = webClient.get()
    .uri("/api/products/export")
    .accept(MediaType.parseMediaType("application/x-ndjson"))
    .retrieve()
    .bodyToFlux(ProductEvent.class);
```

### SSE

Browsers can use `EventSource` for unidirectional GET connections. Java WebClient can read `ServerSentEvent`:

```java
ParameterizedTypeReference<ServerSentEvent<ProductEvent>> eventType =
    new ParameterizedTypeReference<>() {};

Flux<ServerSentEvent<ProductEvent>> events = webClient.get()
    .uri("/api/products/events")
    .accept(MediaType.TEXT_EVENT_STREAM)
    .retrieve()
    .bodyToFlux(eventType);
```

With SSE, clients must handle reconnects, `Last-Event-ID` if event IDs are used, and the possibility of duplicate events after reconnecting. Design consumers to be idempotent if events can be replayed.

## 14. Testing Representations with WebTestClient

Tests should verify `Content-Type` and body shape, not just HTTP 200 status.

### Testing a JSON Array

```java
webTestClient.get()
    .uri("/api/products")
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectBodyList(ProductResponse.class)
    .hasSize(2);
```

### Testing NDJSON

```java
FluxExchangeResult<ProductEvent> result = webTestClient.get()
    .uri("/api/products/export")
    .accept(MediaType.parseMediaType("application/x-ndjson"))
    .exchange()
    .expectStatus().isOk()
    .expectHeader().contentTypeCompatibleWith(
        MediaType.parseMediaType("application/x-ndjson")
    )
    .returnResult(ProductEvent.class);

StepVerifier.create(result.getResponseBody())
    .expectNextCount(2)
    .verifyComplete();
```

### Testing SSE

```java
ParameterizedTypeReference<ServerSentEvent<ProductEvent>> eventType =
    new ParameterizedTypeReference<>() {};

FluxExchangeResult<ServerSentEvent<ProductEvent>> result = webTestClient.get()
    .uri("/api/products/events")
    .accept(MediaType.TEXT_EVENT_STREAM)
    .exchange()
    .expectStatus().isOk()
    .expectHeader().contentTypeCompatibleWith(MediaType.TEXT_EVENT_STREAM)
    .returnResult(eventType);

StepVerifier.create(result.getResponseBody())
    .assertNext(event -> {
        assertThat(event.event()).isEqualTo("product-updated");
        assertThat(event.data()).isNotNull();
    })
    .thenCancel()
    .verify(Duration.ofSeconds(5));
```

For infinite streams, use `thenCancel()` after verifying the expected events so the test does not wait for the stream to complete. Ensure tests have reasonable timeouts and publishers clean up when subscriptions are canceled. The examples require importing `java.time.Duration` and Reactor Test `StepVerifier`.

## 15. Inspecting the Generated OpenAPI Document

After declaring annotations, fetch `/v3/api-docs` and check response content by media type:

- JSON list endpoints have `application/json` and an array schema.
- NDJSON endpoints have `application/x-ndjson`, a single-record schema, and a description stating newline framing.
- SSE endpoints have `text/event-stream` and descriptions of event frames and `data` payloads.
- Response statuses and examples must match runtime behavior.

Condensed OpenAPI YAML example:

```yaml
paths:
  /api/products:
    get:
      responses:
        '200':
          description: Product list as a JSON array
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/ProductResponse'
  /api/products/export:
    get:
      responses:
        '200':
          description: Each line is an independent ProductEvent JSON object (NDJSON)
          content:
            application/x-ndjson:
              schema:
                $ref: '#/components/schemas/ProductEvent'
  /api/products/events:
    get:
      responses:
        '200':
          description: SSE stream; each event's data contains ProductEvent JSON
          content:
            text/event-stream:
              schema:
                type: string
```

OpenAPI describes media types and schemas, but semantics regarding stream lifetime, heartbeats, reconnects, cancellation, and terminal errors must be documented in descriptions or accompanying protocol docs.

## 16. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Client receives a JSON array even though controller returns `Flux` | Endpoint uses `application/json`; encoder collects items into a collection | Use NDJSON or SSE if independent records/events are needed |
| Client fails to parse expecting an array but receives multiple lines | Server publishes NDJSON, client uses a JSON document parser | Use a line reader or WebClient `bodyToFlux` |
| Data does not reach client as items are generated | Codec is aggregating or proxy is buffering | Choose a streaming media type and check proxy buffering/flushing |
| SSE client does not receive event names | Controller returns objects directly instead of `ServerSentEvent` | Use the wrapper to set `event`, `id`, `retry` |
| Response returns 406 | `Accept` incompatible with `produces` | Synchronize media types between client and endpoint |
| OpenAPI documents NDJSON as an array | Springdoc inferred from generic publisher or unclear annotation | Override `@ApiResponse` and state one record per line |
| OpenAPI documents SSE as a JSON object | Confused `data` payload with the entire SSE frame | Use `text/event-stream` and document frame and payload separately |
| Error occurs after a few records without Problem Details | Response already committed and partial stream sent | Define an error record/event or close stream per contract |
| Memory grows over time | Collecting into a list or unbounded buffering | Use a streaming media type, bound data, and bound buffers |
| Stream keeps running after client disconnects | Source ignores cancellation or upstream work is not disposed | Check lifecycle, `doFinally`, and publisher cancellation |
| SSE disconnects after a fixed interval | Proxy/load balancer timeout or missing heartbeats | Configure idle timeouts and send periodic heartbeats |

## 17. Workflow for Choosing Endpoint Representations

When designing an endpoint returning multiple elements, determine:

1. Is the result a finite set or a long-lived stream?
2. Does the client need a complete JSON document or to process each record as it arrives?
3. Is event metadata like `id`, `event`, `retry`, and reconnect needed?
4. Which media type reflects the framing: `application/json`, `application/x-ndjson`, or `text/event-stream`?
5. Are there limits on size, duration, record count, and buffers?
6. How do clients handle cancellation, reconnects, and error records?
7. Does OpenAPI accurately document the media type, schema, and semantics?
8. Have tests verified the actual body, headers, and streaming behavior?

For finite lists with bounded sizes, a JSON array is the simplest choice. For large record sets requiring incremental reading, NDJSON fits better. For real-time one-way browser notifications, SSE provides clear event framing. Spring WebFlux supports all three; the HTTP contract must accurately reflect the format clients will receive.

## 18. References

- [Spring Framework – WebFlux Return Values](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html): how Spring handles `Flux`, `Mono`, and SSE return types.
- [Spring Framework – Reactive Core and JSON Codecs](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): Jackson encoder, JSON array, NDJSON, SSE, and streaming codecs.
- [Spring Framework – @ResponseBody in WebFlux](https://docs.spring.io/spring/reference/web/webflux/controller/ann-methods/responsebody.html): reactive return types and HTTP message writers.
- [Project Reactor – Flux](https://projectreactor.io/docs/core/release/reference/coreFeatures/flux.html): semantics of 0..N sequences in `Flux`.
- [Project Reactor – Backpressure](https://projectreactor.io/docs/core/release/reference/advancedFeatures/reactiveProgramming.html): demand and backpressure in Reactive Streams.
- [Project Reactor – Hot vs Cold](https://projectreactor.io/docs/core/release/reference/advancedFeatures/reactor-hotCold.html): differences between hot and cold publishers.
- [OpenAPI Specification – Media Type Object](https://spec.openapis.org/oas/latest.html#media-type-object): documenting media types, schemas, and examples in response content.
- [Springdoc OpenAPI](https://springdoc.org/): generating OpenAPI documents from controllers and configuring response schemas.
