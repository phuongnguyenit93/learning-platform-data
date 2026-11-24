# Mono, Flux, and How Return Data Types Are Represented

Spring WebFlux uses Reactor to represent asynchronous results with two common types: **Mono<T>** for at most one element and **Flux<T>** for zero, one, or many elements. When writing controllers, these two types describe how data is emitted during processing. OpenAPI, on the other hand, describes the HTTP response seen by the client: status codes, media types, schemas, and headers.

Therefore, you cannot simply look at the name Mono or Flux and conclude whether a response will be an object, an array, or an event stream. You must consider the element type T, wrapper types, media types, and how WebFlux writes data over HTTP. springdoc-openapi analyzes method signatures and metadata to generate schemas, yet the final document still needs to be verified against actual responses.

## 1. Mono and Flux in WebFlux

Reactor provides two commonly used publishers:

| Type | Number of Emitted Elements | Use Cases |
|---|---:|---|
| Mono<T> | 0 or 1 | Single resource details, single lookup result, asynchronous operation |
| Flux<T> | 0 to many | Lists, event streams, continuously emitted data |

Mono<OrderResponse> represents a single result or no result. Flux<OrderResponse> represents a sequence of results that may be emitted gradually over time.

~~~java
@GetMapping("/api/orders/{id}")
public Mono<OrderResponse> getOrder(@PathVariable String id) {
    return orderService.findById(id);
}

@GetMapping("/api/orders")
public Flux<OrderSummary> listOrders() {
    return orderService.findAll();
}
~~~

In these two methods, the first returns a publisher with at most one OrderResponse; the second can emit multiple OrderSummary items. Neither blocks the thread while waiting for data to complete.

A Mono can complete without emitting an element. A Flux can complete immediately without emitting any elements. This is a property of the publisher, not synonymous with a specific HTTP status code.

## 2. Java Types and HTTP Representations Are Two Separate Layers

OpenAPI has no Mono or Flux types. The specification describes data transmitted over HTTP, not Reactor's internal emission mechanism.

| Controller Signature | Publisher Semantics | Common HTTP Representation |
|---|---|---|
| Mono<OrderResponse> | At most one object | A JSON object |
| Flux<OrderResponse> with application/json | Multiple objects | A JSON array |
| Mono<Void> | Signals completion only | No response body |
| Flux<OrderEvent> with text/event-stream | Sequence of events | SSE stream |
| Flux<OrderEvent> with application/x-ndjson | Multiple JSON records | One JSON object per line |

These are common representations, not rules inferred solely from Java types. Media types, codecs, controller configuration, and annotations can change the representation.

When reading OpenAPI, look at the operation response and content first, then inspect the schema. When reading code, check the publisher type and the media type declared on the mapping.

## 3. Mono<T> Is Typically Documented with the Schema of T

For an endpoint returning a JSON object:

~~~java
@GetMapping(
    value = "/api/orders/{id}",
    produces = MediaType.APPLICATION_JSON_VALUE
)
public Mono<OrderResponse> getOrder(@PathVariable String id) {
    return orderService.findById(id);
}
~~~

If springdoc can resolve the generic type, the response schema normally references OrderResponse instead of a Mono type.

~~~yaml
paths:
  /api/orders/{id}:
    get:
      responses:
        '200':
          description: Order details
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
~~~

In components.schemas, OrderResponse describes the JSON fields received by the client. The client does not need to know whether the server uses Mono, CompletableFuture, or another asynchronous mechanism internally.

If the return type is Mono<OrderResponse>, do not document the schema as an object with a property named value or publisher. The publisher is an implementation detail; the schema must reflect the actual response body.

## 4. Flux<T> with application/json Is Typically a JSON Array

An endpoint returning multiple records in a single JSON response:

~~~java
@GetMapping(
    value = "/api/orders",
    produces = MediaType.APPLICATION_JSON_VALUE
)
public Flux<OrderSummary> listOrders() {
    return orderService.findAll();
}
~~~

With the application/json media type, WebFlux typically writes the sequence of elements as a JSON array. Example body:

~~~json
[
  {
    "id": "ORD-1001",
    "status": "PAID"
  },
  {
    "id": "ORD-1002",
    "status": "PENDING"
  }
]
~~~

The OpenAPI schema should represent an array whose items are OrderSummary:

~~~yaml
paths:
  /api/orders:
    get:
      responses:
        '200':
          description: Order list
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/OrderSummary'
~~~

springdoc can usually infer the array schema from Flux<T>. If you need to declare it explicitly via annotations, you can use ArraySchema:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Order list",
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        array = @ArraySchema(
            schema = @Schema(implementation = OrderSummary.class)
        )
    )
)
~~~

Only add explicit annotations when type inference is incorrect or when you need finer control over metadata. Then inspect the OpenAPI JSON to ensure the schema is an array rather than a single object.

## 5. Flux Does Not Automatically Mean HTTP Streaming

Flux allows emitting data incrementally inside the application, but the HTTP representation also depends on the media type and encoder.

- application/json normally collects elements into a JSON array.
- text/event-stream represents Server-Sent Events.
- application/x-ndjson normally uses one JSON record per line.
- application/stream+json may be used to stream JSON values depending on codecs and clients.

When using application/json, the client typically receives a JSON body structured as an array. Although the server can start writing data as the publisher emits elements, the client and codecs still process the JSON representation according to that media type.

If you need the client to process each event immediately upon arrival, choose an appropriate streaming media type and verify codec, proxy, and client behavior. Do not simply change the return type from List<T> to Flux<T> and conclude that the API has become an event stream.

## 6. Server-Sent Events with Flux<ServerSentEvent<T>>

Server-Sent Events (SSE) is a mechanism where the server pushes events to the client over a long-lived HTTP connection. WebFlux can return Flux<ServerSentEvent<T>>.

~~~java
@GetMapping(
    value = "/api/orders/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
public Flux<ServerSentEvent<OrderEvent>> streamOrderEvents() {
    return orderEventService.events()
        .map(event -> ServerSentEvent.builder(event)
            .id(event.id())
            .event("order-update")
            .build());
}
~~~

An SSE event can contain id, event name, data, and retry. The SSE wire format is text per event, not a single JSON array. If data is an object, WebFlux can serialize the payload according to codec configuration; event framing still follows SSE rules.

In OpenAPI, the response should declare the text/event-stream media type. For example:

~~~yaml
paths:
  /api/orders/events:
    get:
      responses:
        '200':
          description: Order event stream in SSE format
          content:
            text/event-stream:
              schema:
                type: string
                description: >
                  SSE event stream. The data field carries an OrderEvent payload;
                  each event may include an id and event name.
~~~

You can also define an OrderEvent component to describe the data payload structure. OpenAPI and client generators do not uniformly represent SSE framing, reconnects, and event metadata; check the specific consuming tools you use.

Do not document SSE as an application/json array if clients must read individual events over the EventSource protocol.

## 7. NDJSON and Other JSON Streaming Formats

NDJSON (Newline Delimited JSON) represents each JSON record on its own line. This format is useful when the server emits multiple records and the client wants to process each line individually.

~~~java
@GetMapping(
    value = "/api/orders/stream",
    produces = "application/x-ndjson"
)
public Flux<OrderEvent> streamOrders() {
    return orderEventService.stream();
}
~~~

Illustrative body:

~~~text
{"id":"ORD-1001","status":"PAID"}
{"id":"ORD-1002","status":"SHIPPED"}
{"id":"ORD-1003","status":"DELIVERED"}
~~~

The media type and per-record writing must be supported by codecs in the Spring Framework version in use. You can use application/stream+json if the system and clients agree on that format.

OpenAPI should specify the exact media type. The schema can describe the record payload, such as OrderEvent, while the description explains that the body consists of multiple newline-separated JSON records. Do not automatically turn the schema into an array if the actual wire format is consecutive JSON records without array brackets.

Client generation support for NDJSON varies by generator. Some tools only generate models for the payload without generating a stream reader API. Check the generated client and write tests that read multiple lines.

## 8. Mono<Void> Represents an Operation Without a Body

Mono<Void> is commonly used for operations that only signal completion, such as deleting data or triggering an action:

~~~java
@DeleteMapping("/api/orders/{id}")
public Mono<Void> deleteOrder(@PathVariable String id) {
    return orderService.deleteById(id);
}
~~~

Mono<Void> does not contain a response object to serialize. However, it does not automatically make the status code 204.

If you want to return 204 No Content, you can declare:

~~~java
@DeleteMapping("/api/orders/{id}")
@ResponseStatus(HttpStatus.NO_CONTENT)
public Mono<Void> deleteOrder(@PathVariable String id) {
    return orderService.deleteById(id);
}
~~~

Or:

~~~java
@DeleteMapping("/api/orders/{id}")
public Mono<ResponseEntity<Void>> deleteOrder(
    @PathVariable String id
) {
    return orderService.deleteById(id)
        .thenReturn(ResponseEntity.noContent().build());
}
~~~

The corresponding OpenAPI should document 204 without declaring a content body:

~~~yaml
responses:
  '204':
    description: Order deleted
~~~

If the controller does not set a status, the response may use the framework's default status. Declare and test the status explicitly rather than inferring 204 solely from Mono<Void>.

## 9. Mono.empty() Does Not Automatically Mean 404

Mono<T> can complete without emitting a value. This commonly happens when no data or result is found.

~~~java
public Mono<OrderResponse> findById(String id) {
    return repository.findById(id)
        .map(orderMapper::toResponse);
}
~~~

If the repository does not find a record, the publisher may be Mono.empty(). That does not automatically become HTTP 404. The status and body depend on how the controller, framework, or exception handler handles an empty publisher.

If the contract requires 404, convert the empty state into an explicit response:

~~~java
@GetMapping("/api/orders/{id}")
public Mono<ResponseEntity<OrderResponse>> getOrder(
    @PathVariable String id
) {
    return orderService.findById(id)
        .map(ResponseEntity::ok)
        .defaultIfEmpty(ResponseEntity.notFound().build());
}
~~~

If the API uses a unified error body, you can return ResponseEntity.status(HttpStatus.NOT_FOUND).body(apiError) in the empty branch.

OpenAPI should accurately document the 200 and 404 branches. Do not document 404 merely because the service returns Mono.empty(); verify that the controller actually produces status 404.

## 10. ResponseEntity and Reactive Wrapper Ordering

Spring WebFlux supports several ways of combining ResponseEntity with publishers. Wrapper order affects when status and headers are determined.

| Return Type | Meaning |
|---|---|
| ResponseEntity<Mono<T>> | Status and headers are ready immediately; body is emitted asynchronously |
| ResponseEntity<Flux<T>> | Status and headers are ready immediately; body is emitted as multiple elements |
| Mono<ResponseEntity<T>> | Entire response entity is constructed asynchronously |
| Mono<ResponseEntity<Flux<T>>> | Response entity is constructed asynchronously, body continues streaming |

Example of ResponseEntity<Mono<T>>:

~~~java
@GetMapping("/api/orders/{id}")
public ResponseEntity<Mono<OrderResponse>> getOrder(
    @PathVariable String id
) {
    Mono<OrderResponse> body = orderService.findById(id);
    return ResponseEntity.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .body(body);
}
~~~

Status 200 and Content-Type are set immediately, while the body is emitted later.

Example of Mono<ResponseEntity<T>>:

~~~java
@GetMapping("/api/orders/{id}")
public Mono<ResponseEntity<OrderResponse>> getOrder(
    @PathVariable String id
) {
    return orderService.findById(id)
        .map(ResponseEntity::ok)
        .defaultIfEmpty(ResponseEntity.notFound().build());
}
~~~

In this case, the controller can choose 200 or 404 after the publisher emits a result or completes empty.

springdoc can resolve common wrappers to generate schemas, but when nesting is complex or generics are erased, you need to add annotations and inspect the OpenAPI JSON. Avoid using raw types like Mono or Flux without generics because the schema can become overly generic.

## 11. Generic Response Wrappers Combined with Mono

Many APIs use a shared envelope:

~~~java
public record ApiResponse<T>(
    String code,
    String message,
    T data
) {}
~~~

A controller can return:

~~~java
@GetMapping("/api/orders/{id}")
public Mono<ApiResponse<OrderResponse>> getOrder(
    @PathVariable String id
) {
    return orderService.findById(id)
        .map(order -> new ApiResponse<>(
            "SUCCESS",
            "Order retrieved successfully",
            order
        ));
}
~~~

OpenAPI needs to preserve the concrete generic type so the data property references OrderResponse. If the documentation only displays data as an untyped object or generics are lost, client generators may produce inaccurate models.

You can use @Schema(implementation = ...) or a customizer if you need control over components, while ensuring the response schema still accurately reflects ApiResponse<OrderResponse>. Generated component names depend on the swagger-core/springdoc version and generic resolution; inspect components.schemas rather than guessing names.

If multiple operations use the envelope with different data types, inspect each operation individually. Do not assume every response wrapper is documented identically just because it uses the same ApiResponse class.

## 12. Declaring Response Schemas with Annotations

When springdoc infers the wrong schema or you need to explicitly specify media types, you can declare @ApiResponse, @Content, and @Schema.

Example with Mono<OrderResponse>:

~~~java
@GetMapping("/api/orders/{id}")
@ApiResponse(
    responseCode = "200",
    description = "Order details",
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = OrderResponse.class)
    )
)
public Mono<OrderResponse> getOrder(@PathVariable String id) {
    return orderService.findById(id);
}
~~~

Example with Flux<OrderSummary> as a JSON array:

~~~java
@GetMapping("/api/orders")
@ApiResponse(
    responseCode = "200",
    description = "Order list",
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        array = @ArraySchema(
            schema = @Schema(implementation = OrderSummary.class)
        )
    )
)
public Flux<OrderSummary> listOrders() {
    return orderService.findAll();
}
~~~

Annotations are documentation metadata; they do not change how WebFlux serializes responses. If a controller returns a Flux while the annotation describes a single object, the documentation will be wrong even though the application still runs.

Do not declare a schema implementation for Mono<Void> or a bodyless 204 response. If you need to document headers, declare headers separately without adding content.

## 13. Media Types Must Match produces

The produces attribute on mappings determines the media type an endpoint advertises and can influence codec selection:

~~~java
@GetMapping(
    value = "/api/orders",
    produces = MediaType.APPLICATION_JSON_VALUE
)
public Flux<OrderSummary> listOrders() {
    return orderService.findAll();
}
~~~

For SSE:

~~~java
@GetMapping(
    value = "/api/orders/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
public Flux<ServerSentEvent<OrderEvent>> events() {
    return eventService.events();
}
~~~

For NDJSON:

~~~java
@GetMapping(
    value = "/api/orders/stream",
    produces = "application/x-ndjson"
)
public Flux<OrderEvent> stream() {
    return eventService.stream();
}
~~~

Cross-check mapping produces, content in the OpenAPI response, actual Content-Type headers, codecs supporting the media type, and how the client reads the body.

If OpenAPI documents application/json while runtime returns text/event-stream, client generators may produce broken body-reading code. Conversely, documentation describing SSE while the controller actually returns a JSON array also violates the contract.

## 14. Documenting Reactive Request Bodies

Request bodies in WebFlux can also be received as publishers:

~~~java
@PostMapping(
    value = "/api/orders",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public Mono<OrderResponse> createOrder(
    @Valid @RequestBody Mono<CreateOrderRequest> request
) {
    return request.flatMap(orderService::create);
}
~~~

For a normal JSON object, the OpenAPI requestBody still describes the CreateOrderRequest schema. Mono merely represents receiving the body asynchronously.

If an endpoint accepts multiple records or a request stream, the representation depends on the media type and codecs. For example, an NDJSON request might use Flux<CreateOrderLine> and consumes application/x-ndjson. In that case, document the framing clearly and verify whether clients can send multiple lines.

Do not document a request body as a Mono or Flux schema. Document the payload that the server receives after decoding.

## 15. Error Handling in Reactive Pipelines

Errors in Reactor are emitted as onError signals. WebFlux can translate errors into HTTP responses via exception handlers or the application's error-handling mechanism.

~~~java
public Mono<OrderResponse> findById(String id) {
    return repository.findById(id)
        .switchIfEmpty(Mono.error(
            new OrderNotFoundException(id)
        ))
        .map(orderMapper::toResponse);
}
~~~

They can be handled centrally:

~~~java
@RestControllerAdvice
class ReactiveExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    Mono<ResponseEntity<ApiError>> handleNotFound(
        OrderNotFoundException exception
    ) {
        ApiError error = new ApiError(
            "ORDER_NOT_FOUND",
            "Order not found"
        );

        return Mono.just(
            ResponseEntity.status(HttpStatus.NOT_FOUND).body(error)
        );
    }
}
~~~

The OpenAPI operation should document the 404 response with the ApiError schema if this is the actual behavior. The @ApiResponse annotation does not handle onError or turn exceptions into status codes by itself.

When an error occurs after a stream has already started writing its body, the server may no longer be able to change the HTTP status or headers. In that case, the stream protocol needs its own convention to signal in-stream errors or close the connection. This is an important consideration for SSE and NDJSON.

## 16. Backpressure Is Not Described by OpenAPI Schemas

Reactor supports backpressure so subscribers can regulate the rate at which a publisher emits data. This is an internal flow-control mechanism between publisher and subscriber.

OpenAPI schemas do not describe event emission rates, request demand, buffering strategies, cancellation, retry/reconnect behavior, when a stream ends, or connection keep-alive policies.

If clients need to know how long a stream can stay open, whether events can be duplicated, or how to reconnect, add clear descriptions, operational documentation, or an application-level protocol spec. These rules cannot be inferred from the Flux<T> type.

For SSE, document the event name, id, and payload. For NDJSON, document record delimiting and stream termination conditions. For potentially infinite streams, specify how clients should cancel the subscription or close the connection.

## 17. Distinguishing List Flux from Page and Slice

Flux<T> can emit many elements, but it does not inherently provide pagination metadata like Page<T>.

| Type | Data | Metadata |
|---|---|---|
| Flux<T> | Sequence of elements | No default totalElements/page number |
| Mono<List<T>> | Complete list | No default pagination metadata |
| Mono<Page<T>> | One page of data | Includes totalElements, totalPages, page number |
| Mono<Slice<T>> | One slice of data | Includes hasNext/hasPrevious |

If the API needs page, size, totalElements, and totalPages, use an appropriate paginated result type instead of assuming Flux is a Page.

With reactive repositories, Spring Data supports different return types depending on the module and store. Check the capabilities of the repository in use. Not all reactive repositories support Page in the same way blocking repositories do.

If an endpoint returns Flux when it actually fetches a single page and emits each item, OpenAPI may only see an array or stream without page metadata. If clients need metadata, design an appropriate response envelope.

## 18. WebFlux and springdoc Dependencies

A Spring Boot WebFlux application needs the WebFlux starter. With springdoc 2.x and Spring Boot 3, the commonly used starter for WebFlux UI is:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>

<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-ui</artifactId>
    <version>YOUR_COMPATIBLE_SPRINGDOC_VERSION</version>
</dependency>
~~~

Use a springdoc version compatible with the Spring Boot line in use and manage versions through dependency management or a project property. Do not arbitrarily mix WebMVC and WebFlux starters in the same application; the chosen runtime stack should be explicit.

Once the application starts, docs are normally available at /v3/api-docs and the UI at /swagger-ui.html. If the project customizes paths, groups, or UI settings, use the configured URLs instead of assuming defaults.

## 19. Inspecting OpenAPI JSON

Download the document from the application:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Inspect the response schema of a Mono endpoint:

~~~bash
jq '.paths["/api/orders/{id}"].get.responses["200"].content["application/json"].schema' openapi.json
~~~

Inspect the response schema of a Flux endpoint:

~~~bash
jq '.paths["/api/orders"].get.responses["200"].content["application/json"].schema' openapi.json
~~~

For Flux JSON, confirm the schema has type array and items pointing to the element component. For Mono JSON, confirm the schema points to a single object.

Inspect the media type of SSE:

~~~bash
jq '.paths["/api/orders/events"].get.responses["200"].content | keys' openapi.json
~~~

The result should include text/event-stream if the endpoint publishes SSE. Similarly, an NDJSON endpoint should list the media type that the controller actually uses.

Also cross-check components.schemas, generic wrappers, 204 responses, 404 responses, status codes, and produces/media types. OpenAPI JSON is the final output consumed by Swagger UI and client generators; do not check only annotations in source code.

## 20. Runtime Testing with WebTestClient

WebTestClient is well suited for testing WebFlux. Example testing a Mono response:

~~~java
@WebFluxTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    WebTestClient webTestClient;

    @MockitoBean
    OrderService orderService;

    @Test
    void returnsSingleOrder() {
        given(orderService.findById("ORD-1001"))
            .willReturn(Mono.just(new OrderResponse(
                "ORD-1001",
                "PAID"
            )));

        webTestClient.get()
            .uri("/api/orders/{id}", "ORD-1001")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.id").isEqualTo("ORD-1001")
            .jsonPath("$.status").isEqualTo("PAID");
    }
}
~~~

Testing a Flux JSON array:

~~~java
webTestClient.get()
    .uri("/api/orders")
    .exchange()
    .expectStatus().isOk()
    .expectHeader()
    .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectBody()
    .jsonPath("$[0].id").isEqualTo("ORD-1001");
~~~

Testing SSE requires verifying the media type and event stream:

~~~java
webTestClient.get()
    .uri("/api/orders/events")
    .accept(MediaType.TEXT_EVENT_STREAM)
    .exchange()
    .expectStatus().isOk()
    .expectHeader()
    .contentTypeCompatibleWith(MediaType.TEXT_EVENT_STREAM);
~~~

For streams that never complete, avoid assertions that wait for the entire body. Consume a bounded portion of the stream with timeouts and cancel the subscription in tests so pipelines do not hang.

Tests need mocks, DTOs, and imports prepared according to the application. @MockitoBean is available in newer Spring Framework/Spring Boot versions; older projects can use the supported mock annotation for their version.

## 21. Common Pitfalls

| Symptom | Cause to Investigate |
|---|---|
| OpenAPI shows Mono as a wrapper object | Generic type not resolved or faulty custom converter |
| Flux JSON is documented as a single object | Schema annotation overriding array inference |
| Flux is mistaken for SSE | Only changed return type without declaring text/event-stream |
| Swagger UI shows JSON while runtime returns SSE | produces and response content out of sync |
| Mono.empty() returns 200 instead of 404 | Empty branch not mapped to status 404 |
| Mono<Void> still returns 200 | Missing ResponseEntity or appropriate @ResponseStatus |
| ResponseEntity wrapper loses schema | Nested generics not resolved as expected |
| NDJSON client reads only one object | Generator lacks framing support or schema description is unclear |
| Stream fails after sending partial body | HTTP status/headers can no longer be changed |
| Swagger UI hangs forever calling an infinite Flux | Endpoint is a long-lived stream; needs an event-reading client and test |
| Page schema lacks metadata | Controller returns Flux<T> instead of a paginated type |
| Generic ApiResponse<T> becomes a generic object | Type parameter lost or raw type used |

## 22. Reactive Response Design Conventions

To keep contracts easy to understand:

- Use Mono<T> for single responses.
- Use Flux<T> with application/json when returning a JSON array.
- Use text/event-stream for SSE and clearly document the event payload.
- Use NDJSON or an agreed streaming media type when line-delimited records are needed.
- Use Mono<Void> for bodyless responses and set the status explicitly.
- Convert Mono.empty() to 404/204 if required by business logic; do not rely on guesswork.
- Keep generic types concrete; avoid raw Mono and raw Flux.
- Use ResponseEntity when you need conditional control over status and headers.
- Keep response schemas, content, and produces synchronized.
- Verify OpenAPI JSON alongside WebTestClient.

A good reactive API does not just use the right publisher—it also exposes a clear HTTP representation for clients. Choose return types based on how clients need to consume data, not solely on how internal services process work asynchronously.

## 23. Checklist

- [ ] Distinguished between Mono<T> and Flux<T>.
- [ ] Determined HTTP representation instead of inferring from publisher alone.
- [ ] Mono JSON is documented with the object schema of T.
- [ ] Flux application/json is documented with an array schema.
- [ ] SSE uses text/event-stream and documents the event payload.
- [ ] NDJSON/streaming media types are specified properly with framing documented.
- [ ] Mono<Void> does not declare a response body.
- [ ] Status for Mono.empty() is handled explicitly.
- [ ] ResponseEntity wrappers preserve accurate status, headers, and body schema.
- [ ] Generic response wrappers preserve the element type.
- [ ] Reactive exceptions have appropriate response documentation.
- [ ] Distinguished Flux from Page/Slice.
- [ ] springdoc WebFlux dependency is compatible with the Spring Boot version.
- [ ] Verified /v3/api-docs.
- [ ] Tested JSON, SSE, or NDJSON with WebTestClient.

## 24. References

- [springdoc-openapi – Official Documentation](https://springdoc.org/)
- [Spring Framework – WebFlux annotated controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html)
- [Spring Framework – Reactive libraries](https://docs.spring.io/spring-framework/reference/web/webflux-reactive-libraries.html)
- [Project Reactor – Reference Guide](https://projectreactor.io/docs/core/release/reference/)
- [OpenAPI Specification – Responses Object](https://spec.openapis.org/oas/latest.html#responses-object)
- [OpenAPI Specification – Media Type Object](https://spec.openapis.org/oas/latest.html#media-type-object)

Mono and Flux describe reactive publishers on the server; OpenAPI describes the HTTP representation received by the client. Mono usually maps to a single payload, Flux can be a JSON array or a stream depending on media type, and Mono<Void> usually has no body. Verify schemas, content types, statuses, and bodies using both /v3/api-docs and WebTestClient so the documentation accurately reflects WebFlux behavior.
