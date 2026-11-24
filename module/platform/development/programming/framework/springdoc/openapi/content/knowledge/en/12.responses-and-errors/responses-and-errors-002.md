# Inferring Schemas from Handler Return Types

When generating an OpenAPI specification from Spring Boot controllers, springdoc-openapi typically relies on handler return types to infer response content. A method returning a DTO can produce an object schema; a method returning a list of DTOs can produce an array schema; a method returning ResponseEntity<OrderResponse> indicates that the body has type OrderResponse. As a result, many endpoints can be documented without rewriting every schema with annotations.

Inference is accurate only when the Java signature reflects the data the API actually sends to clients. Return types alone do not describe every status code, every error branch, or all response headers. For cases with multiple outcomes, erased generics, empty bodies, or special data types, additional metadata must be supplied via @ApiResponse, @Content, and @Schema.

## 1. Response Schema Inference Mechanism

springdoc-openapi reads Spring mappings, handler signatures, Java types, OpenAPI annotations, and related configuration to build Operations in the documentation. For REST endpoints, the return type is normally used to determine the schema of the success response.

The processing flow can be visualized as follows:

~~~mermaid
flowchart TD
    A[Handler method in controller] --> B[Read Java return type]
    B --> C{Has wrapper or generic type?}
    C -->|Yes| D[Analyze inner body type]
    C -->|No| E[Analyze return type directly]
    D --> F[Generate OpenAPI schema]
    E --> F
    F --> G[Place schema into response content]
    G --> H[Inspect /v3/api-docs]
    H --> I[Compare against runtime JSON]
~~~

What must be distinguished is that Spring decides how to handle the return value when a request runs, whereas springdoc describes that behavior in the OpenAPI contract. For REST controllers, return values are typically converted into the response body through Spring MVC's HttpMessageConverter or WebFlux's HttpMessageWriter. springdoc uses type information and annotations to describe the shape of that data.

The returned schema is usually placed inside the operation's response content, for example:

~~~yaml
responses:
  '200':
    description: Order found
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/OrderResponse'
~~~

If an object schema is reused, it may reside in components.schemas and be referenced by the operation via $ref. For simple types, the schema may be inlined directly inside response content.

## 2. Returning a DTO Directly

This is the easiest case to infer. The controller returns a concrete DTO, and springdoc reads its properties to generate the corresponding schema.

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping("/{id}")
    public OrderResponse getById(@PathVariable long id) {
        return orderService.getById(id);
    }
}
~~~

DTO:

~~~java
public class OrderResponse {

    private Long id;
    private String orderNumber;
    private BigDecimal total;
    private String status;

    // Getters and setters omitted.
}
~~~

Because the controller uses @RestController, the OrderResponse object is written to the response body. springdoc can infer an object schema with properties id, orderNumber, total, and status. If the DTO contains nested objects, enums, or collections, the schema can reference the corresponding component schemas.

If using @Controller instead of @RestController, mark the method with @ResponseBody when you want to return data in the HTTP response. In a standard MVC controller, a String return value can be interpreted as a view name rather than a response body. Therefore, consider both controller-level and method-level annotations when reading return signatures.

## 3. Returning Simple Types, Strings, and Collections

The Java return type directly shapes the resulting schema:

| Return type | Common schema shape | JSON example |
| --- | --- | --- |
| String | string | "Order created" |
| Integer, Long | integer | 42 |
| BigDecimal, Double | number | 125000.50 |
| Boolean | boolean | true |
| DTO | object | {"id":42,"status":"NEW"} |
| List<OrderResponse> | array with OrderResponse items | [{"id":42,"status":"NEW"}] |
| OrderResponse[] | array with OrderResponse items | [{"id":42,"status":"NEW"}] |
| Map<String, String> | object with dynamic properties | {"region":"north"} |

Example of an endpoint returning a list:

~~~java
@GetMapping
public List<OrderResponse> findAll() {
    return orderService.findAll();
}
~~~

The inferred schema is an array whose items describe OrderResponse. Do not declare the response as an object just because an internal service returns a collection; check the actual JSON to verify whether the API returns a raw array directly or a wrapper object containing a list.

Example of a Map with dynamic keys:

~~~java
@GetMapping("/statistics")
public Map<String, Long> statistics() {
    return orderService.countByStatus();
}
~~~

The result can be an object with keys such as NEW, CONFIRMED, or CANCELLED. If the key set is fixed and carries business meaning, a DTO with explicit properties usually produces clearer documentation than a generic Map.

A String return type in a @RestController is a string-typed response body. It is not automatically a JSON object or a structured JSON string. Check the Content-Type and how the converter serializes data; if the endpoint returns text/plain, document the corresponding media type.

## 4. Inferring the Body from ResponseEntity<T>

ResponseEntity<T> represents an entire HTTP response, including status, headers, and body. The type parameter T indicates the body type. Consequently, springdoc can infer the schema from T rather than generating a schema for the ResponseEntity class itself.

~~~java
@GetMapping("/{id}")
public ResponseEntity<OrderResponse> getById(@PathVariable long id) {
    OrderResponse order = orderService.getById(id);
    return ResponseEntity.ok()
        .header("X-Order-Source", "primary")
        .body(order);
}
~~~

In this example, the body has the OrderResponse schema. The X-Order-Source header and HTTP status are separate parts of the response; they do not become properties of OrderResponse.

ResponseEntity lets the handler choose the status based on the processing outcome:

~~~java
@GetMapping("/{id}")
public ResponseEntity<OrderResponse> getById(@PathVariable long id) {
    return orderService.findById(id)
        .map(ResponseEntity::ok)
        .orElseGet(() -> ResponseEntity.notFound().build());
}
~~~

The return type still indicates that the success body is OrderResponse, but it does not fully describe every status branch. The not-found branch returns 404 with no body; the found branch returns 200 with a body. Declare separate responses using @ApiResponses so the contract expresses both outcomes.

## 5. Generic Wrappers and Nested Types

Many systems use a common wrapper to standardize responses:

~~~java
public class ApiEnvelope<T> {

    private boolean success;
    private T data;
    private String traceId;

    // Getters and setters omitted.
}
~~~

If the controller declares the full type argument:

~~~java
@GetMapping("/{id}")
public ApiEnvelope<OrderResponse> getById(@PathVariable long id) {
    return ApiEnvelope.success(orderService.getById(id));
}
~~~

springdoc can infer the wrapper structure and the type of data from ApiEnvelope<OrderResponse>. The expected schema has fields success, data, and traceId; the data property references or describes OrderResponse.

Nested generics can also be represented when the signature preserves full type arguments:

~~~java
@GetMapping
public ResponseEntity<ApiEnvelope<List<OrderResponse>>> findAll() {
    List<OrderResponse> orders = orderService.findAll();
    return ResponseEntity.ok(ApiEnvelope.success(orders));
}
~~~

The body type in the example is ApiEnvelope containing a list of OrderResponse. This is why concrete generic types should be preserved in public controller signatures.

If you declare a raw type or wildcard:

~~~java
public ResponseEntity<?> getById(@PathVariable long id) {
    return ResponseEntity.ok(orderService.findById(id));
}
~~~

springdoc lacks sufficient static information to know which DTO the actual body belongs to. An Object type or overly broad schema may appear. If the API actually returns one stable type, declare that type in the signature or specify it explicitly with @ApiResponse and @Schema(implementation = OrderResponse.class).

If the body can belong to multiple distinct types, describe the union with oneOf or anyOf when appropriate. Do not arbitrarily pick a single implementation if runtime can return multiple incompatible JSON structures.

## 6. Optional and Asynchronous Return Types

Some handlers return results that may be absent or produced asynchronously. Distinguish wrappers representing computation state from the final data type sent to clients.

With Optional, clearly define the HTTP behavior when data is absent. Example:

~~~java
@GetMapping("/{id}")
public ResponseEntity<OrderResponse> getById(@PathVariable long id) {
    return orderService.findById(id)
        .map(ResponseEntity::ok)
        .orElseGet(() -> ResponseEntity.notFound().build());
}
~~~

Optional in the service layer does not need to appear in the response schema if the controller converts it into ResponseEntity<OrderResponse>. The client receives 200 with OrderResponse or 404 with no body.

Spring MVC supports asynchronous return types such as CompletableFuture<T>, CompletionStage<T>, Callable<T>, and DeferredResult<T>. Spring handles the result once the task completes; springdoc typically documents the final value type rather than a CompletableFuture object. Example:

~~~java
@GetMapping("/{id}")
public CompletableFuture<OrderResponse> getById(@PathVariable long id) {
    return orderService.findByIdAsync(id);
}
~~~

The API contract remains a response containing OrderResponse. The asynchronous wrapper is an implementation detail.

Exact output depends on the wrapper type, the Spring MVC/WebFlux stack, and the springdoc version. When using custom wrappers or nested reactive types, inspect the generated OpenAPI JSON instead of assuming every wrapper is automatically unwrapped the same way.

## 7. Mono, Flux, and Streaming Responses

In Spring WebFlux, handlers can return Mono<T> or Flux<T>. Mono typically represents zero or one value; Flux represents multiple values. Spring supports both responses written as a single JSON value and streaming responses depending on media type.

Example returning a single object:

~~~java
@GetMapping("/{id}")
public Mono<OrderResponse> getById(@PathVariable long id) {
    return orderService.findById(id);
}
~~~

Example returning a list collected into a single response:

~~~java
@GetMapping
public Flux<OrderResponse> findAll() {
    return orderService.findAll();
}
~~~

With Flux, delivery depends on media type and how Spring writes the response. If a client requests application/json, multiple values may be collected and written as a JSON array. If the endpoint uses text/event-stream or a streaming media type, data is emitted event by event or item by item. These two styles have different contracts.

Therefore, when using Flux, declare produces explicitly and check the actual response. For Server-Sent Events, you can use Flux<ServerSentEvent<OrderEvent>> with media type text/event-stream. The schema of event data, stream frame structure, and how clients consume it must be documented clearly; an unbounded stream should not be documented as an ordinary JSON array.

Spring MVC also supports ResponseBodyEmitter, SseEmitter, and StreamingResponseBody. These types emit data as a stream or write directly to an OutputStream. They require explicit media type and content descriptions via response annotations if automatic inference does not accurately reflect how data is delivered.

## 8. void, ResponseEntity<Void>, and Bodyless Responses

Handlers with return type void or ResponseEntity<Void> normally do not return a JSON body:

~~~java
@DeleteMapping("/{id}")
@ResponseStatus(HttpStatus.NO_CONTENT)
public void delete(@PathVariable long id) {
    orderService.delete(id);
}
~~~

Or using ResponseEntity:

~~~java
@DeleteMapping("/{id}")
@ApiResponse(
    responseCode = "204",
    description = "Order deleted",
    content = @Content
)
public ResponseEntity<Void> delete(@PathVariable long id) {
    orderService.delete(id);
    return ResponseEntity.noContent().build();
}
~~~

In the contract, a 204 response normally has no content. The springdoc FAQ guides declaring an empty response with content = @Content or content = @Content(schema = @Schema(hidden = true)).

Do not assign an object schema to a 204 response if the server sends no body. Also distinguish status 200 with an empty body from status 204 with no content: these are different HTTP commitments.

A void method alone does not dictate every status case. In Spring MVC, void can mean the response was handled directly if ServletResponse, OutputStream, @ResponseStatus, or an equivalent mechanism is present; otherwise, it may produce an empty response body in a REST controller or view resolution behavior in an MVC controller. Inspect annotations and runtime behavior.

## 9. Media Types and Response Shapes

The return type indicates data structure; the media type indicates how content is represented. These two parts must match.

Example returning JSON:

~~~java
@GetMapping(value = "/{id}", produces = MediaType.APPLICATION_JSON_VALUE)
public OrderResponse getById(@PathVariable long id) {
    return orderService.getById(id);
}
~~~

Example returning plain text:

~~~java
@GetMapping(value = "/health/text", produces = MediaType.TEXT_PLAIN_VALUE)
public String healthText() {
    return "UP";
}
~~~

For file downloads, a handler can return Resource or ResponseEntity<Resource>. Many OpenAPI 3.0 toolchains describe file content using type string with format binary, paired with an appropriate media type such as application/octet-stream or a specific file type. When exporting OpenAPI 3.1, verify the file schema conventions supported by your springdoc version and validator tools. For file uploads/downloads, declare content explicitly rather than relying solely on Java types.

If the same endpoint supports multiple media types, OpenAPI can describe multiple entries in content of the same response. This remains a single operation with multiple representations, not necessarily multiple distinct schemas. Ensure Spring converters actually support the declared media types.

## 10. Inference Does Not Replace Documenting Statuses and Errors

The return type primarily helps infer the schema of the response body. A handler may return 200, 201, 202, 204, 400, 404, or 409 depending on processing conditions. All of these branches cannot be known from a single DTO type.

Example documenting multiple outcomes:

~~~java
@PostMapping
@Operation(summary = "Create order")
@ApiResponses({
    @ApiResponse(
        responseCode = "201",
        description = "Order created",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = OrderResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "400",
        description = "Invalid input data",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ApiError.class)
        )
    ),
    @ApiResponse(
        responseCode = "409",
        description = "Duplicate order",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ApiError.class)
        )
    )
})
public ResponseEntity<OrderResponse> create(
        @Valid @RequestBody CreateOrderRequest request) {
    OrderResponse created = orderService.create(request);
    return ResponseEntity.status(HttpStatus.CREATED).body(created);
}
~~~

In the example, the return type indicates that the success body is OrderResponse. Error responses use ApiError and are declared separately.

With @ControllerAdvice, springdoc can add shared error responses. springdoc documentation recommends declaring the HTTP code with @ResponseStatus on exception-handler methods for automatic documentation generation. The springdoc.override-with-generic-response property is enabled by default to add responses from ControllerAdvice to generated operations; inspect the output to avoid inappropriate generic responses on specific endpoints.

## 11. When Should You Override the Response Schema?

If the return type is not specific enough or does not reflect the public JSON, you can declare the response explicitly:

~~~java
@GetMapping("/{id}")
@ApiResponse(
    responseCode = "200",
    description = "Order information",
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = OrderResponse.class)
    )
)
public ResponseEntity<?> getById(@PathVariable long id) {
    return ResponseEntity.ok(orderService.findResponse(id));
}
~~~

If the response is a list whose signature does not retain the element type, you can use @ArraySchema:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Order list",
    content = @Content(
        mediaType = "application/json",
        array = @ArraySchema(
            schema = @Schema(implementation = OrderResponse.class)
        )
    )
)
~~~

When a concrete return type is already available, prefer letting springdoc infer it. Override only when the contract genuinely differs from the declared Java type or when generic type information is insufficient.

If you need to hide the response schema or describe a response without content, you can use:

~~~java
@ApiResponse(
    responseCode = "204",
    description = "No content returned",
    content = @Content
)
~~~

or:

~~~java
@ApiResponse(
    responseCode = "204",
    description = "No content returned",
    content = @Content(schema = @Schema(hidden = true))
)
~~~

## 12. Inspecting the Inferred Schema

After starting the application, open the default /v3/api-docs endpoint or your configured endpoint. Find the relevant operation and verify:

1. Whether the published response code matches @ResponseStatus and @ApiResponse annotations; for ResponseEntity with multiple status branches, declare each possible code explicitly.
2. Whether the schema reflects the actual body: object, array, primitive, map, or wrapper.
3. Whether generic types are preserved properly across nested layers.
4. Whether bodyless responses have empty content without an assumed schema.
5. Whether the media type in content matches produces and the actual converter.
6. Whether important error responses are declared with accurate schemas.
7. That no invalid components or $ref entries appear due to wrappers or override configuration.

You can download the document using curl:

~~~bash
curl -s http://localhost:8080/v3/api-docs
~~~

Then call the real endpoint to inspect the JSON, status, and headers. The OpenAPI specification is a published contract; it cannot prove that runtime responses always comply with the contract. Integration tests should cover success, error, empty-body, and different media type branches.

## 13. Common Errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Response schema is Object | Handler uses raw type, Object, or wildcard | Preserve concrete generic types or declare implementation |
| Wrapper has data but data schema is unclear | Generic type T is not preserved on the public signature | Declare ApiEnvelope<OrderResponse> instead of raw ApiEnvelope |
| ResponseEntity is documented as an object | HTTP wrapper confused with body payload | Check springdoc version and response content; expected schema is type T |
| List is documented as an object | Return signature uses a wrapper object or unclear collection type | Inspect runtime JSON and declare an array schema when needed |
| Error status does not appear in docs | Relying solely on the success return type | Declare @ApiResponse for each important error code |
| 204 response has a body schema | Response annotation describes content even though runtime sends no body | Use content = @Content and verify the actual status |
| String is interpreted as a view | Using @Controller without @ResponseBody | Use @RestController or add @ResponseBody to return a body |
| Flux displays as a list while the API emits SSE | Streaming media type is not documented accurately | Declare produces = text/event-stream and verify event structure |
| File response is documented as an object | Media type and binary schema not declared | Document content with application/octet-stream and string/binary schema |
| ControllerAdvice error response added to every operation | Generic response applied globally | Check springdoc.override-with-generic-response and error scope configuration |

## 14. Design Principles

Declare concrete return types on controllers so springdoc has enough information to build schemas. Use public DTOs instead of entities or Object when returned data needs a stable structure. Preserve generic types inside wrappers and ResponseEntity to describe the body type accurately. For empty bodies, use void or ResponseEntity<Void> and declare the appropriate status/content. For multiple statuses, errors, media types, or streams, add metadata so the contract reflects every outcome clients can receive.

Finally, compare the generated specification with runtime responses. Java signatures help springdoc infer schemas, but the actual JSON, status, headers, and media types sent by the application are what clients consume.

## 15. Official References

- [springdoc-openapi — Features v2](https://springdoc.org/v2/features.html) — REST integration, error handling via @ControllerAdvice and @ResponseStatus, functional endpoints.
- [springdoc-openapi — FAQ v2](https://springdoc.org/v2/faq.html) — declaring responses without content and hiding response schemas.
- [Spring Framework — Return Values](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/return-types.html) — handler return types, void, ResponseEntity, async, and reactive.
- [Spring Framework — ResponseEntity](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html) — status, headers, body, and asynchronous response forms.
- [Spring Framework — WebFlux Return Values](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html) — handling reactive and streaming types.
- [springdoc-openapi Core Properties](https://springdoc.org/core-properties.html) — configuring shared responses from ControllerAdvice.

Inferring schemas from return types speeds up documentation and keeps docs close to source code. When Java signatures are concrete, wrappers are clear, and responses are tested, springdoc-openapi can produce a useful OpenAPI contract for frontend, mobile, partners, and client generation tools.
