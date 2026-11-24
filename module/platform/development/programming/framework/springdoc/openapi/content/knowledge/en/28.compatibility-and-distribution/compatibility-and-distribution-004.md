# Differences Between Input and Output Compatibility

When modifying an API, a change can be safe on the request side yet cause errors on the response side, or vice versa. Therefore, compatibility cannot be evaluated with a single generic question like "Is the API still compatible?". Two directions must be separated:

- **Input compatibility:** does the new server continue accepting requests sent by old clients?
- **Output compatibility:** do old clients continue reading and processing responses returned by the new server?

In Spring Boot, requests are typically bound into DTOs, validated with Bean Validation, and passed to services. Responses are serialized from DTOs or controller return types. `springdoc-openapi` generates documentation describing both sides via `requestBody`, `parameters`, `responses`, and the Schema Object.

This lesson helps you evaluate changes from both provider and consumer perspectives, read request/response schemas accurately, test actual runtime behavior, and decide when a compatible release is possible versus when a new API version is required.

## 1. Two compatibility directions answer two different questions

An API has at least two data flows:

~~~text
Client  ---- Request ---->  Server
Client  <--- Response ----  Server
~~~

In the request flow, the client sends data and the server must parse, validate, accept, or reject that data. In the response flow, the server sends data and the client must deserialize, validate, and use it.

| Direction | Question | What must be protected |
|---|---|---|
| Input compatibility | Does the new server still accept old requests? | Clients calling the API |
| Output compatibility | Do old clients still read new responses? | Applications consuming the API |
| Contract compatibility | Does the new OpenAPI still accurately describe behavior and consumer expectations? | Both provider and consumer |

For example, adding an optional property to a request usually does not break old clients because old clients can simply omit that property. However, adding a new property to a response can cause a client using strict deserialization to reject the payload if the client disallows unknown fields.

Conversely, adding an enum value accepted by the server in a request can be safe for old clients, whereas adding an enum value returned by the server in a response can cause old clients to fail to handle it.

## 2. Distinguishing backward and forward compatibility by deployment direction

The terms backward and forward are often used inconsistently. To avoid confusion, state the client and server versions explicitly:

| Client | Server | Compatibility Question |
|---|---|---|
| Old client | New server | Is the new server backward-compatible with old clients? |
| New client | Old server | Is the new client forward-compatible with old servers? |
| New client | New server | Do both sides share the new contract? |

In this lesson:

- **Provider backward compatibility** means the new server still supports the requests and response expectations of old clients.
- **Consumer forward compatibility** means new clients still work when encountering an old server that lacks the new changes.

No single general rule guarantees both directions. For instance, adding a response property can be safe for old clients if they ignore unknown fields, yet new clients may fail when calling an old server because the old server does not send the property the new client expects.

When reviewing an API change, specify which direction must be guaranteed. For public APIs, the new server must typically remain compatible with already-released clients.

## 3. Input compatibility: the server accepts requests

Input compatibility focuses on the requests the provider receives:

- Path parameters.
- Query parameters.
- Headers and cookies.
- Request bodies.
- Media types and encodings.
- Data types, formats, and constraints.
- Required/optional status.
- Enums and allowed values.
- Authentication and authorization mechanisms.

A safe change usually expands the set of valid requests the server accepts. A risky change usually narrows that set or alters how the server interprets legacy data.

Example:

~~~http
POST /api/orders
Content-Type: application/json

{
  "customerId": "CUS-1001",
  "items": [
    {
      "productId": "SKU-01",
      "quantity": 2
    }
  ]
}
~~~

Old clients send `customerId` and `items`. If the new server adds an optional `note` property, old requests can remain valid. If the new server requires `note`, old clients omit that field and requests may be rejected.

## 4. Output compatibility: the client reads responses

Output compatibility focuses on the responses the consumer receives:

- Status codes.
- Response bodies and schemas.
- Property names and types.
- Required/optional status.
- Nullability.
- Enums.
- Date/time, numeric, and identifier formats.
- `Content-Type` and media types.
- Response headers.
- Error representations.
- Pagination or streaming structures.

A safe change usually preserves the data old clients need, or only adds data that clients can ignore. A risky change usually removes, retypes, or changes the meaning of existing data.

Example:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "ORD-1001",
  "status": "PAID",
  "createdAt": "2026-11-20T10:00:00Z"
}
~~~

If the new server adds an optional `source` property, old clients can continue reading `id`, `status`, and `createdAt`. If the server changes `status` from a string to an object, old clients may fail to deserialize it.

## 5. Request and response change matrix

The following table serves as an initial assessment guide. Final outcomes also depend on server strictness, serializers, client runtimes, and organizational contract conventions.

| Change | Input compatibility: server receives request | Output compatibility: client reads response |
|---|---|---|
| Add optional property | Usually backward-compatible | Usually compatible if clients ignore unknown fields |
| Add required property | May break old clients | New clients may fail with old servers if old servers omit the field |
| Remove property | May break old clients still sending or relying on the field | Usually breaks clients reading the field |
| Rename property | Breaks if server no longer accepts old name | Breaks if clients still read old name |
| Change data type | Usually breaks | Usually breaks |
| Tighten constraint | May break previously valid requests | May break if responses no longer satisfy old contract |
| Relax constraint | Usually safe for old requests | May change the set of valid responses; check clients |
| Add enum value | Server accepting more values is usually safe for old clients | Old clients may fail to handle new value |
| Remove enum value | May break clients still sending removed value | Server no longer emits old value; old clients usually understand remaining values |
| Change media type | May break request submission | May break client decoders |
| Change status code | May affect call or retry behavior | May break client response-handling branches |

Do not judge a change merely by the label "additive." Adding a field to a request and adding a field to a response are different cases because one is data the server receives and the other is data the client receives.

## 6. Adding an optional property to a request

Suppose the initial request is:

~~~java
public record CreateOrderRequest(
    @NotBlank String customerId,
    @NotEmpty List<CreateOrderLineRequest> items
) {}
~~~

The new version adds an optional `note`:

~~~java
public record CreateOrderRequest(
    @NotBlank String customerId,
    @NotEmpty List<CreateOrderLineRequest> items,
    String note
) {}
~~~

Old clients still send `customerId` and `items`. If the new server does not require `note` and does not change how the existing fields are processed, old requests remain accepted.

The OpenAPI request schema can express:

~~~yaml
CreateOrderRequest:
  type: object
  required:
    - customerId
    - items
  properties:
    customerId:
      type: string
    items:
      type: array
      items:
        $ref: '#/components/schemas/CreateOrderLineRequest'
    note:
      type: string
~~~

`note` is not in the `required` list, so clients can omit it.

However, verify actual DTO binding and validation. If a custom deserializer or business validation requires `note` at runtime, the documented schema alone is insufficient to guarantee input compatibility.

## 7. Adding a required property to a request

Suppose the new version adds a field:

~~~java
public record CreateOrderRequest(
    @NotBlank String customerId,
    @NotEmpty List<CreateOrderLineRequest> items,
    @NotBlank String channel
) {}
~~~

If `channel` is required, old clients do not send this field. The new server may return 400 due to validation or reject the request in business logic.

OpenAPI will represent `channel` in `required`:

~~~yaml
required:
  - customerId
  - items
  - channel
~~~

This is usually a breaking change for input compatibility.

A safer rollout approach can be:

1. Add `channel` as optional.
2. Set a default for old clients or determine how to infer `channel`.
3. Publish the new field in OpenAPI.
4. Give clients time to start sending the field.
5. Monitor requests missing `channel`.
6. Upgrade it to `required` only in a breaking-change release if genuinely needed.

Do not mark a property `required` merely to make documentation look complete if the server can still process requests without the field.

## 8. Removing or renaming a request property

Removing a property from a DTO can cause Jackson to ignore the old field or reject the request depending on configuration. Even when the server does not error, business logic may stop receiving the value sent by clients.

Renaming a property carries a similar risk:

~~~json
{
  "customerId": "CUS-1001"
}
~~~

changed to:

~~~json
{
  "customer": "CUS-1001"
}
~~~

Old clients still send `customerId`. If the new server only reads `customer`, the data may be missing or validation may fail.

If renaming is necessary, you can keep an alias during the transition period with Jackson:

~~~java
public record CreateOrderRequest(
    @JsonAlias("customerId")
    @JsonProperty("customer")
    String customer
) {}
~~~

This example must be tested with the project's Jackson version and record binding. In particular, OpenAPI must document the property name clients are expected to send. If the server accepts both old and new names, clearly publish the end-of-support deadline for the old name.

## 9. Changing request constraints

Constraints are part of the input contract. Bean Validation annotations can be reflected into the schema by `springdoc`:

~~~java
public record SearchRequest(
    @Size(min = 2, max = 50)
    String keyword,

    @Positive
    Integer pageSize
) {}
~~~

OpenAPI can describe `minLength`, `maxLength`, `minimum`, or `exclusiveMinimum` depending on the constraint.

If the new server reduces `maxLength` from 50 to 20, an old request with a 30-character `keyword` that was previously valid is now rejected. This narrows the input domain and is usually a breaking change.

If the server increases `maxLength` from 50 to 100, the server accepts more requests. For old clients, this change is usually backward-compatible.

Verify both layers:

- The OpenAPI schema reflects the new constraint.
- Runtime validation actually accepts or rejects data accurately.

Do not assume every custom annotation is automatically translated into schema keywords by `springdoc`. If a constraint comes from a custom validator, document it with schema annotations and write corresponding contract tests.

## 10. Adding and removing enum values in a request

Suppose a request has an enum:

~~~java
public enum OrderChannel {
    WEB,
    MOBILE
}
~~~

The new server adds `PARTNER`:

~~~java
public enum OrderChannel {
    WEB,
    MOBILE,
    PARTNER
}
~~~

The new server can accept one more value. Old clients still send `WEB` or `MOBILE` and are typically unaffected.

However, new clients generated from the new spec can send `PARTNER`. If those clients call an old server that only knows `WEB` and `MOBILE`, requests may be rejected. This is the difference between a new server accepting old requests and an old server accepting new requests.

If the server removes `MOBILE`, old clients still sending `MOBILE` will fail. Therefore, removing an enum value in a request is usually a breaking change.

In OpenAPI:

~~~yaml
OrderChannel:
  type: string
  enum:
    - WEB
    - MOBILE
    - PARTNER
~~~

Do not just update the enum in documentation. Test the parser, Jackson enum deserializer, validation, and business logic.

## 11. Adding a property to a response

Suppose the initial response is:

~~~java
public record OrderResponse(
    String id,
    String status
) {}
~~~

The new version adds `createdAt`:

~~~java
public record OrderResponse(
    String id,
    String status,
    Instant createdAt
) {}
~~~

New OpenAPI response schema:

~~~yaml
OrderResponse:
  type: object
  required:
    - id
    - status
  properties:
    id:
      type: string
    status:
      type: string
    createdAt:
      type: string
      format: date-time
~~~

`createdAt` is not required, so the documentation allows the property to be absent. If the server always sends the field, you can consider marking it `required` per schema policy. However, when adding a property to a response, verify whether clients accept unknown fields.

Many JSON deserializers ignore unknown properties by default, yet some configurations enable strict unknown-property handling. Clients generated from closed schemas or using strict validation may also reject new fields.

Therefore, adding a response property is generally considered compatible with flexible consumers, though not an absolute guarantee for every client.

## 12. Adding a required property to a response

When the new server always returns an additional field, OpenAPI can mark that field `required`:

~~~yaml
OrderResponse:
  type: object
  required:
    - id
    - status
    - fulfillmentMode
  properties:
    id:
      type: string
    status:
      type: string
    fulfillmentMode:
      type: string
~~~

Old clients can usually ignore `fulfillmentMode` if their deserializer permits unknown fields. However, new clients generated from this schema may assume `fulfillmentMode` always exists.

If a new client calls an old server, the old server does not yet send `fulfillmentMode`. The new client may receive null, a default value, or an error depending on the generated model and runtime.

This illustrates how a single change can be:

- Compatible with old clients when the new server sends the extra field.
- Incompatible with new clients when those clients call an old server.

If clients and servers are deployed independently, consider ordered rollouts: deploy servers supporting the new field first, then deploy clients that require using the field.

## 13. Removing or retyping a response property

Removing a response property usually breaks clients that use that field:

~~~json
{
  "id": "ORD-1001",
  "status": "PAID"
}
~~~

If the new server only returns:

~~~json
{
  "id": "ORD-1001"
}
~~~

Clients reading `status` may receive null, validation errors, or logic errors.

Changing types also carries risk:

| Old | New | Risk |
|---|---|---|
| string | integer | Deserializer or consumer code is incompatible |
| integer | string | Model type and operations change |
| string | object | Response structure changes |
| date-time string | epoch number | Clients must change parsers |
| array | object | Payload shape changes |
| object | array | Payload shape changes |

Even if values are convertible from a business standpoint, the contract has changed. Do not rely on one specific client's coercion behavior to declare compatibility for all consumers.

If a type change is needed, create a new field or a new API version, keep the old field during a transition period, and plan deprecation.

## 14. Adding enum values in a response

The server may begin returning a new enum value:

~~~java
public enum OrderStatus {
    PENDING,
    PAID,
    SHIPPED,
    CANCELLED
}
~~~

If old clients only know `PENDING`, `PAID`, and `CANCELLED`, the value `SHIPPED` can cause:

- Enum deserialization failure.
- Fallback to `null` or unknown.
- Errors in `switch` expressions.
- Skipped business branches.
- Incorrect status display.

Therefore, extending an enum in a response can break output compatibility for old consumers, even if the schema only adds one value.

A resilient client should have a branch handling unknown values where the domain permits. However, you cannot assume every client was written that way.

If response enums can expand, state clearly in API guidelines that consumers must handle unknown values. For client generators, check enum extensibility settings and target language runtime behavior.

## 15. Changing status codes and response headers

The response contract is not just the body. Status codes and headers are outputs too.

For example, an endpoint initially returns `200`:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
~~~

The new server switches to `204 No Content`. Clients deserializing the body into `OrderResponse` may fail because the body is gone.

Other status changes:

- `200` to `201` can affect clients that only handle `200`.
- Adding `202` can shift semantics from completion to asynchronous processing.
- Adding `409` may require clients to handle conflicts.
- `404` to `204` can lose "not found" information.
- Adding redirects can change client behavior if redirects are not followed.

Headers can also be part of the contract:

- `Location`.
- `ETag`.
- `Retry-After`.
- `Link`.
- `RateLimit` or `X-RateLimit-*`.
- `Content-Disposition`.

If clients depend on headers, document them in OpenAPI and test at runtime. Do not evaluate compatibility using the response schema alone.

## 16. Changing media types and content negotiation

Request media types define how clients send bodies. Response media types define how clients decode bodies.

JSON request example:

~~~java
@PostMapping(
    value = "/api/orders",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public Mono<OrderResponse> create(
    @Valid @RequestBody CreateOrderRequest request
) {
    return orderService.create(request);
}
~~~

If the new server only accepts `application/vnd.example.order+json`, old clients sending `application/json` may receive `415 Unsupported Media Type`.

Similarly for responses: if old clients expect `application/json` while the server returns `application/xml` or `application/x-ndjson`, the decoder may fail to process it.

In OpenAPI, media types appear under `content` of `requestBody` or `responses`:

~~~yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        $ref: '#/components/schemas/CreateOrderRequest'
~~~

If the API supports multiple media types, test each `Accept` and `Content-Type` branch. Do not alter `produces` or `consumes` merely to standardize code without evaluating consumers.

## 17. `required`, optional, and `nullable` are three things to distinguish

A property can be:

- Required and non-null.
- Required yet nullable.
- Optional and non-null if present.
- Optional and nullable.

Example in OpenAPI 3.1:

~~~yaml
type: object
required:
  - id
  - note
properties:
  id:
    type: string
  note:
    type:
      - string
      - "null"
  comment:
    type: string
  nickname:
    type:
      - string
      - "null"
~~~

In this example:

- `id` is required and non-null.
- `note` is required yet may be null.
- `comment` is optional; if present, it must be a string.
- `nickname` is optional and may be null.

Client generators may map these fields to different types depending on the language. When migrating schemas from 3.0 to 3.1, verify generator and runtime nullable mappings.

Do not use `required` as a synonym for non-null. The two concepts are independent.

## 18. `readOnly` and `writeOnly` in the Schema Object

OpenAPI supports `readOnly` and `writeOnly` to distinguish properties read only in responses or written only in requests.

Example:

~~~yaml
Order:
  type: object
  properties:
    id:
      type: string
      readOnly: true
    accessToken:
      type: string
      writeOnly: true
    name:
      type: string
~~~

`id` is returned only by the server; `accessToken` is sent only in requests. Tools can use this metadata to generate appropriate request/response models or validation.

In Java:

~~~java
public record OrderView(
    @Schema(accessMode = Schema.AccessMode.READ_ONLY)
    String id,
    String name
) {}
~~~

~~~java
public record CreateOrderRequest(
    String name,
    @Schema(accessMode = Schema.AccessMode.WRITE_ONLY)
    String accessToken
) {}
~~~

Using separate DTOs for requests and responses is usually clearer when the two data shapes differ significantly. `readOnly`/`writeOnly` are schema metadata; verify actual Jackson serialization and deserialization to ensure the runtime does not send or accept properties contrary to intent.

Per OpenAPI rules, a `required` property with `readOnly` is interpreted as required in responses; a `required` property with `writeOnly` is interpreted as required in requests. Check how your parser and generator handle this rule.

## 19. Using separate DTOs to protect both contract directions

A controllable design is to separate request DTOs and response DTOs:

~~~java
public record CreateOrderRequest(
    @NotBlank String customerId,
    @NotEmpty List<@Valid CreateOrderLineRequest> items
) {}
~~~

~~~java
public record OrderResponse(
    String id,
    String customerId,
    String status,
    Instant createdAt
) {}
~~~

Controller:

~~~java
@PostMapping("/api/orders")
public Mono<ResponseEntity<OrderResponse>> create(
    @Valid @RequestBody CreateOrderRequest request
) {
    return orderService.create(request)
        .map(order -> ResponseEntity
            .created(URI.create("/api/orders/" + order.id()))
            .body(order));
}
~~~

Separate DTOs help you:

- Add response fields without accidentally requiring clients to send them.
- Restrict which data clients are permitted to write.
- Avoid returning tokens or secrets in responses.
- Define `required`/optional independently.
- Review request and response versioning separately.

Sharing one entity or DTO for both requests and responses can cause properties like `id`, `status`, or internal flags to leak onto the wrong side. If you still use a shared model, declare `readOnly`/`writeOnly` explicitly and test the schema in both directions.

## 20. Runtime validation and documented schema must stay in sync

`springdoc` can infer several constraints from Bean Validation:

~~~java
public record UpdateProfileRequest(
    @NotBlank
    @Size(max = 80)
    String displayName,

    @Email
    String email
) {}
~~~

Documentation can describe `required`, `maxLength`, or `format` accordingly. However, not every custom validator can be automatically translated into an OpenAPI schema.

There are two opposite bugs:

- OpenAPI says a field is optional, yet runtime returns 400 when omitted.
- OpenAPI says `maxLength` is 80, yet runtime allows or rejects under a different limit.

Test both:

1. Fetch the request schema from `/v3/api-docs`.
2. Send a payload valid per the schema.
3. Send a payload missing a required field.
4. Send a payload with `null`.
5. Send a payload exceeding min/max bounds.
6. Compare the status and error body against documentation.

An accurate specification must describe actual server behavior, not merely reflect annotations superficially.

## 21. How does `springdoc` describe requests and responses?

`springdoc` inspects mappings, parameter types, request bodies, return types, and annotations to generate OpenAPI.

Example:

~~~java
@PostMapping("/api/orders")
@Operation(summary = "Create order")
@ApiResponses({
    @ApiResponse(
        responseCode = "201",
        description = "Order has been created",
        content = @Content(
            schema = @Schema(implementation = OrderResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "400",
        description = "Invalid request data"
    )
})
public Mono<ResponseEntity<OrderResponse>> createOrder(
    @Valid @RequestBody CreateOrderRequest request
) {
    return orderService.create(request)
        .map(order -> ResponseEntity
            .created(URI.create("/api/orders/" + order.id()))
            .body(order));
}
~~~

`springdoc` can infer the request schema from `CreateOrderRequest` and the response schema from `OrderResponse` or response annotations.

When precise control is needed, use `@RequestBody`, `@Parameter`, `@Schema`, `@ApiResponse`, and `@Content`. Yet annotations only describe documentation; they do not automatically alter validation, serialization, or business logic.

After changing annotations, always inspect the final OpenAPI JSON. Never assume annotations produced the right schema just because the application compiles cleanly.

## 22. Evaluating compatibility when adding a query parameter

Suppose the initial endpoint is:

~~~java
@GetMapping("/api/orders")
public Flux<OrderResponse> listOrders() {
    return orderService.findAll();
}
~~~

The new version adds an optional query parameter:

~~~java
@GetMapping("/api/orders")
public Flux<OrderResponse> listOrders(
    @RequestParam(required = false) OrderStatus status
) {
    return orderService.findByStatus(status);
}
~~~

Old clients do not send `status`. If the new server still handles the missing parameter case, input compatibility is generally preserved.

If `required = true` is declared or binding without a default causes missing parameters to be rejected, old clients may receive 400.

OpenAPI should express:

~~~yaml
parameters:
  - name: status
    in: query
    required: false
    schema:
      $ref: '#/components/schemas/OrderStatus'
~~~

Adding an optional parameter is usually safe for old requests. Removing a parameter or renaming a parameter usually breaks clients using it.

## 23. Evaluating compatibility when adding a response field

A new response field can be added to the schema:

~~~yaml
properties:
  id:
    type: string
  status:
    type: string
  estimatedDelivery:
    type: string
    format: date
~~~

If `estimatedDelivery` is optional, new clients need to handle the field being absent when calling old servers. Old clients need to handle the unknown field if the new server sends it.

These are two distinct conditions:

- New server with old client: does the client ignore `estimatedDelivery`?
- Old server with new client: does the client accept a response without `estimatedDelivery`?

If both directions must work during independent rollouts, do not immediately make new clients depend on a field that only exists on the new server. Deploy the server first, then enable client logic relying on the field.

## 24. Changing error responses is also an output contract change

Error responses are often overlooked when evaluating compatibility, yet clients may rely on `code` and `message` for handling.

Error schema example:

~~~yaml
ApiError:
  type: object
  required:
    - code
    - message
  properties:
    code:
      type: string
    message:
      type: string
    traceId:
      type: string
~~~

If the server changes a code from `ORDER_NOT_FOUND` to `RESOURCE_MISSING`, clients branching on the old code may stop working.

If the server changes the response body from `ApiError` to Problem Details, clients need to support the new schema.

When standardizing error formats, you can retain legacy fields during a transition period or release a new version. Document error status codes and bodies using `@ApiResponse` and test with `WebTestClient`.

Do not include stack traces, SQL details, or secrets in error responses just to help clients debug. Error schemas should contain safe, stable information.

## 25. Compatibility of pagination and collection responses

Switching from an array to an envelope is a major change:

Old version:

~~~json
[
  {"id": "ORD-1"},
  {"id": "ORD-2"}
]
~~~

New version:

~~~json
{
  "items": [
    {"id": "ORD-1"},
    {"id": "ORD-2"}
  ],
  "page": 0,
  "size": 20,
  "totalElements": 2
}
~~~

Old clients expecting an array cannot read an object envelope. Even though the new envelope provides useful metadata, this is a breaking change to the output contract.

If pagination metadata must be added, create a new endpoint, a new version, or a clearly agreed transition phase. Do not change the response shape of a widely used endpoint without checking consumers.

## 26. Compatibility of streaming responses

Streaming is also an output contract. Switching from a JSON array to SSE or NDJSON can break clients:

| Representation | What clients must handle |
|---|---|
| `application/json` | A single JSON document, typically an object or array |
| `text/event-stream` | SSE event framing and long-lived connections |
| `application/x-ndjson` | Multiple newline-delimited JSON records |
| `application/stream+json` | JSON values framed as supported by the codec/client |

Returning `Flux<T>` does not by itself determine the representation. Media types, codecs, and mappings determine how clients receive data.

If you change the media type, treat it as a contract change. Document response content accurately in OpenAPI and test real clients, not just the server emitting a publisher.

## 27. Distinguishing schema compatibility from semantic compatibility

A schema can stay unchanged while the meaning of data still shifts.

For instance, `status` remains a string, yet previously `PAID` meant funds were captured, and later it is used for orders confirmed as partially paid. The type is unchanged, but business semantics changed.

Semantic changes to review:

- Currency or measurement units.
- Timezone and timestamp meaning.
- Rounding rules.
- Business states.
- Ordering of list elements.
- Stability of identifiers.
- Pagination rules.
- Idempotency and retry behavior.
- Meaning of null or omitted fields.

OpenAPI can describe formats, descriptions, and enums, but cannot by itself prove all business semantics. Contract documentation, examples, and business-level tests are required.

## 28. Checking compatibility with OpenAPI diff

After `springdoc` generates the new document:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o target/openapi-new.json
~~~

Compare against the released version using an OpenAPI diff tool or parser-aware tool. Specifically review:

- Request parameters and `required` flags.
- Request body schemas.
- Request enums and constraints.
- Response status codes.
- Response content types.
- Response schemas and required fields.
- Response enums.
- Security requirements.
- Server URLs and paths.
- Error responses.

Text diffs can report noisy changes due to key ordering. Use semantic diffs to classify contract changes. However, do not automatically ignore server URL or security changes because they can directly impact clients.

## 29. Testing request compatibility with `WebTestClient`

Example of an old client omitting a new optional property:

~~~java
@Test
void acceptsLegacyCreateOrderRequest() {
    webTestClient.post()
        .uri("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue("""
            {
              "customerId": "CUS-1001",
              "items": [
                {
                  "productId": "SKU-01",
                  "quantity": 2
                }
              ]
            }
            """)
        .exchange()
        .expectStatus().isCreated();
}
~~~

This test proves the new server still accepts the old payload in this concrete case. Mock services or prepare fixtures appropriate for the test context.

Add tests for:

- New field omitted.
- New field set to `null`.
- Legacy enum values.
- Legacy parameters.
- Legacy headers.
- Payloads without optional fields.
- Legacy constraints still valid.

If the new server intentionally stops accepting an old request, the test should explicitly demonstrate the response and corresponding API version.

## 30. Testing output compatibility with response fixtures

You can keep response fixtures from the old version and verify that new clients can read them.

JSON fixture example:

~~~json
{
  "id": "ORD-1001",
  "status": "PAID"
}
~~~

Deserialization test:

~~~java
@Test
void newClientModelReadsLegacyResponse() throws Exception {
    OrderResponse response = objectMapper.readValue(
        legacyResponseFixture,
        OrderResponse.class
    );

    assertThat(response.id()).isEqualTo("ORD-1001");
    assertThat(response.status()).isEqualTo("PAID");
}
~~~

If the new DTO has a required field or constructor rejecting missing values, this test can catch that the new client is incompatible with old servers.

For clients generated from OpenAPI, run fixtures through the exact generated models and deserializers. Do not substitute hand-written DTOs because behavior may differ.

## 31. Contract tests must check both sides

A practical verification workflow:

1. Export OpenAPI from the application.
2. Validate the document and references.
3. Compare against the released contract.
4. Test old requests against the new server.
5. Test new responses against old clients or old client fixtures.
6. Test new clients against old server responses if rollouts require it.
7. Test generated SDKs.
8. Run `WebTestClient` for statuses, headers, bodies, and validation.
9. Review semantic changes.
10. Store results alongside artifacts.

Do not rely solely on an OpenAPI validator. Validators check spec structure, not how old clients actually handle unknown enums or unknown fields.

Do not rely solely on runtime tests. Runtime tests on one server version do not prove every released client remains compatible.

## 32. Deployment strategies when contracts change

When adding a new field:

1. Update the server to accept the new field while continuing to support old requests.
2. Publish the optional field in OpenAPI.
3. Deploy the server.
4. Update clients to send the field when needed.
5. Monitor usage of legacy fields.
6. If legacy fields must be removed, announce deprecation and end-of-support timing.
7. Remove only in a major/breaking release per policy.

When adding a response field needed by new clients:

1. Deploy the server emitting the new field while keeping old response fields.
2. Update OpenAPI.
3. Wait until the new server is available across the entire fleet.
4. Deploy clients reading the new field with a fallback.
5. Only after all consumers have migrated, consider requiring the field on the client.
6. Retain the ability to read old responses during rollout if needed.

Deployment ordering depends on whether the system performs rolling deployments or runs multiple server versions in parallel. The contract must support the window when client and server are not on the same release.

## 33. Deprecation and transition periods

OpenAPI can mark operations or parameters `deprecated`:

~~~yaml
parameters:
  - name: customerId
    in: query
    required: false
    deprecated: true
    schema:
      type: string
    description: Use customerRef instead.
~~~

Marking `deprecated` tells consumers that the field still exists but should not be used for new integrations.

A deprecation plan should state:

- Which component is scheduled for removal.
- The replacement component.
- Expected version or end-of-support date.
- Migration instructions.
- Overlap duration where both work concurrently.
- How consumers can reach support.

Do not delete a property immediately after marking it `deprecated`. Deprecation is a transition notice; removal is a contract change that must be managed separately.

## 34. API versioning vs. OpenAPI document versioning

Distinguish:

- API version: version of the business contract.
- OpenAPI version: version of the specification format.
- `springdoc` version: version of the documentation generation library.
- Application version: version of the server artifact.

Example:

~~~yaml
openapi: 3.1.0
info:
  title: Order API
  version: 2.4.0
~~~

Here `3.1.0` is the specification version, while `2.4.0` is the published API version.

You can version APIs via URL:

~~~text
/api/v1/orders
/api/v2/orders
~~~

Or use header/media-type versioning according to system policy. Whichever approach is chosen, OpenAPI must clearly describe how consumers select versions, and documentation must be distributed per version.

Do not bump the OpenAPI version just because the API contract changed. Nor should you bump the API version just because `springdoc` was upgraded.

## 35. When should a new major API version be created?

Consider a new major version when changes cannot be rolled out compatibly for current consumers, such as:

- Removing or renaming a request field currently in use.
- Turning an optional request field into `required`.
- Tightening constraints so old requests become invalid.
- Removing a response field.
- Changing response types or structure.
- Changing media types or streaming protocols.
- Removing status codes or error formats used by clients.
- Changing security schemes or requiring new scopes that lock out old clients.
- Semantic changes that cause old clients to process data incorrectly.

You do not need a new major version merely for adding a new operation or adding an optional request property, provided those changes are genuinely compatible with supported consumers.

Versioning decisions should be based on the published compatibility policy and API usage data, not solely on the endpoint author's intuition.

## 36. Distributing contracts and generated SDKs

After compatibility checks pass, distribute OpenAPI artifacts under immutable versions:

~~~text
contracts/
  orders/
    1.0.0/
      openapi.json
      openapi.yaml
      checksum.txt
    1.1.0/
      openapi.json
      openapi.yaml
      checksum.txt
~~~

Each artifact should be associated with:

- API version.
- Commit or release revision.
- OpenAPI specification version.
- `springdoc` and toolchain versions used to generate the file.
- Validation results.
- Compatibility report.
- Release date or release metadata outside the contract if needed.

Do not overwrite published artifacts without a policy. Client SDKs need to know which contract version they were generated from. When the contract changes, generate a new SDK and release it under the package versioning policy.

## 37. Pre-release verification matrix

You can use the following matrix in pull requests:

| Check | Input | Output |
|---|---|---|
| Required/optional | Does server still accept old requests? | Can clients tolerate missing new fields? |
| Type/format | Does server parse old payloads? | Do clients deserialize new payloads? |
| Enum | Does server still accept old values? | Do clients handle unknown new values? |
| Constraint | Are old requests still valid? | Do responses always satisfy schema? |
| Media type | Does server still accept old `Content-Type`? | Do clients read new `Content-Type`? |
| Status code | Requests and auth flows unchanged unexpectedly? | Do clients handle new statuses? |
| Security | Are old credentials/scopes still accepted? | Can clients handle new challenges/errors? |
| Generated SDK | Does request serializer build valid payloads? | Does response deserializer handle fields/enums properly? |

Mark PASS only with evidence from the spec, runtime tests, or appropriate generated client tests.

## 38. Common mistakes

| Symptom | Root cause to check |
|---|---|
| Added request field causes 400 for old clients | New field was marked `required` or enforced by validator |
| Added response field breaks old clients | Client uses strict deserialization or closed schema |
| New client fails when calling old server | Client depends on new response field not yet present |
| Added request enum breaks on old server | New client sends value unknown to old server |
| Added response enum breaks old clients | Enum deserializer or `switch` lacks unknown case |
| Type changed yet docs still compile | OpenAPI is metadata only and does not verify runtime payloads |
| Request schema matches yet runtime rejects | Bean Validation or custom validator differs from documentation |
| Response schema matches yet body differs | Actual serializer or mapping differs from DTO/annotations |
| Replaced JSON array with envelope | Old clients can no longer read the response shape |
| Changed `200` to `204` | Clients still attempt to deserialize a body |
| Changed media type | Client decoder does not support the new representation |
| Marked `deprecated` and removed immediately | Consumers had no time for migration |
| Ran validator only without SDK tests | Tool parses spec fine, yet generated clients can break |
| Bumped OpenAPI version when API changed | Confused format version with API contract version |

## 39. API change review workflow

When reviewing a pull request that modifies controllers, DTOs, or annotations:

1. Determine whether the change affects requests, responses, or both.
2. Compare OpenAPI before and after.
3. For requests, verify the new server still accepts old payloads.
4. For responses, verify old clients still read new payloads.
5. Check `required`, optional, `nullable`, enums, and constraints.
6. Check statuses, headers, and media types.
7. Check security and authorization.
8. Run `WebTestClient` or integration tests.
9. Generate and compile client SDKs if the project distributes SDKs.
10. Decide on compatible change, deprecation, or major version.
11. Store the OpenAPI artifact and compatibility report.

If no consumer fixtures exist, create fixtures from published contracts or SDK tests. Do not rely on the current DTO to represent every legacy client.

## 40. Checklist

- [ ] Clearly identified input compatibility and output compatibility.
- [ ] Explicitly stated direction: old client/new server or new client/old server.
- [ ] New request properties are optional if old clients must keep working.
- [ ] `required` flags match runtime validation.
- [ ] Legacy request enums remain accepted.
- [ ] Constraints do not accidentally narrow the input domain.
- [ ] Legacy response fields were not unexpectedly removed or retyped.
- [ ] Old clients can handle new response properties.
- [ ] New clients have fallbacks when old servers omit new fields.
- [ ] Response enums have an unknown-value policy.
- [ ] Status codes and error bodies were checked.
- [ ] `Content-Type` and media types did not change unintentionally.
- [ ] `readOnly`/`writeOnly` are documented and tested accurately.
- [ ] Request/response DTOs are separated when appropriate.
- [ ] OpenAPI schema matches Bean Validation and serialization.
- [ ] Contract tests cover both old and new payloads.
- [ ] Generated SDKs were compiled and tested.
- [ ] Deprecations include a migration window.
- [ ] API version is not confused with OpenAPI version.
- [ ] Artifacts and compatibility reports are stored per release.

## 41. References

- [springdoc-openapi – Official Documentation](https://springdoc.org/)
- [OpenAPI Specification – Schema Object](https://spec.openapis.org/oas/latest.html#schema-object)
- [OpenAPI Specification – Request Body Object](https://spec.openapis.org/oas/latest.html#request-body-object)
- [OpenAPI Specification – Responses Object](https://spec.openapis.org/oas/latest.html#responses-object)
- [OpenAPI Specification – Parameter Object](https://spec.openapis.org/oas/latest.html#parameter-object)
- [Spring Framework – Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Jackson – Annotations](https://github.com/FasterXML/jackson-annotations)
- [OpenAPI Generator – Documentation](https://openapi-generator.tech/docs/)

Input compatibility is the ability of a new server to continue accepting old requests; output compatibility is the ability of old clients to continue reading new responses. Adding an optional request property is usually safe for old clients, whereas adding a response enum value can break old clients. Evaluate `required`, types, constraints, enums, statuses, media types, and semantics separately, then verify with OpenAPI diff, `WebTestClient`, and generated clients before distributing the contract.
