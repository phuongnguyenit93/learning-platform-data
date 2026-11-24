# Callbacks, Webhooks, and Changes in Specification Structure

## 1. Why do APIs need to describe callbacks and webhooks?

Standard REST APIs describe a client sending a request to a server and receiving a response. However, many integrations need the server to proactively notify the client when an event occurs—for example, when an order ships, a payment completes, or a processing status changes.

There are two common ways to describe server-initiated calls:

- **Callback**: an HTTP call attached to a specific operation. The callback URL is typically supplied by the client in the request or derived from request/response data.
- **Webhook**: a type of request sent by the API provider to an API consumer's endpoint when an event occurs. In OpenAPI 3.1, webhooks are described at the top level of the document, independent of any initial triggering operation.

Springdoc OpenAPI primarily infers APIs from handlers exposed by the application. Outbound callback or webhook endpoints sent by the system may not correspond to any inbound controller in the application. Therefore, you must add metadata via Swagger annotations or the OpenAPI model so the document accurately reflects asynchronous communication.

This article explains the Callback Object, Webhooks Object, runtime expressions, differences between OpenAPI 3.0 and 3.1, how to describe them with Springdoc, and what to check when tools lack full support.

## 2. Distinguishing callbacks, webhooks, and regular endpoints

Both callbacks and webhooks result in an HTTP request sent from one system to another, yet they occupy different places and contexts in the API contract.

| Concept | Where it is described | When it is called |
|---|---|---|
| Regular operation | `paths` | Client calls an operation on the API provider |
| Callback | Inside `callbacks` of an operation | When a condition related to the operation occurs |
| Webhook | Inside `webhooks` at the document level in OpenAPI 3.1 | When the provider emits an event, not necessarily tied to a specific operation |

Examples:

- A client calls `POST /subscriptions` and submits an event-receiving URL. When a change occurs, the provider sends a `POST` to that URL. This fits describing a callback attached to the subscription creation operation.
- A payment platform sends a `payment.completed` event to an endpoint registered by the merchant. The event can occur independently of any in-flight request. This fits describing a webhook at the document level.
- If your application exposes `POST /webhook-events` to receive events from an external provider, that endpoint is still a regular inbound API operation under `paths` in your API. The provider's OpenAPI document is what describes the webhook they send to that endpoint.

The key point is determining who initiates the request and which operation context that request belongs to.

## 3. What is a callback in OpenAPI?

The Callback Object describes one or more requests that the API provider can send to a URL supplied by the client or computed from the operation's context.

Callbacks are declared in the `callbacks` property of an Operation Object. Each callback has:

- A callback name for referencing within the document.
- One or more runtime expressions used to determine the target URL.
- A Path Item describing the HTTP method, request body, parameters, and responses of the callback call.

For example, a client subscribes to notifications by sending:

~~~http
POST /api/subscriptions
Content-Type: application/json

{
  "eventType": "order.status.changed",
  "callbackUrl": "https://merchant.example.com/hooks/orders"
}
~~~

When the order status changes, the API provider can send:

~~~http
POST https://merchant.example.com/hooks/orders
Content-Type: application/json

{
  "eventId": "evt-901",
  "orderId": "ORD-1001",
  "status": "SHIPPED"
}
~~~

The callback describes the second request as part of the `POST /api/subscriptions` operation. The target URL is taken from `callbackUrl` in the request body.

A callback does not create an additional inbound endpoint in the provider application. It describes the outbound call that the provider will send to the client.

## 4. Callback Object structure

In OpenAPI, a callback is a map from a runtime expression to a Path Item Object. Concise example:

~~~yaml
paths:
  /api/subscriptions:
    post:
      summary: Subscribe to events
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/SubscriptionRequest'
      callbacks:
        orderStatusChanged:
          '{$request.body#/callbackUrl}':
            post:
              summary: Notify order status change
              requestBody:
                required: true
                content:
                  application/json:
                    schema:
                      $ref: '#/components/schemas/OrderStatusEvent'
              responses:
                '202':
                  description: Client accepted the event
      responses:
        '201':
          description: Subscription created successfully
~~~

In the structure above:

- `callbacks` belongs to the `POST /api/subscriptions` operation.
- `orderStatusChanged` is the callback name.
- `{$request.body#/callbackUrl}` is the runtime expression identifying the target URL.
- `post` describes the HTTP request the provider sends to the client.
- `requestBody` describes the event payload.
- `responses` describes the response returned by the client's callback endpoint.

A callback can contain multiple expressions and Path Items depending on the design. Each callback operation should clearly describe its method, media type, schema, responses, and required headers.

## 5. Runtime expressions for determining the callback URL

A runtime expression is an expression referencing request or response data at the time the operation executes. Callbacks use this expression to determine the target URL.

Common expressions:

| Expression | Referenced value |
|---|---|
| `{$request.body#/callbackUrl}` | `callbackUrl` property in the JSON request body |
| `{$request.query.queryUrl}` | `queryUrl` query parameter |
| `{$request.header.X-Callback-Url}` | `X-Callback-Url` request header |
| `{$response.header.Location}` | `Location` header in the response |
| `{$request.body#/notification/target}` | Nested property in the request body |

For example, if the request contains:

~~~json
{
  "notification": {
    "target": "https://client.example.com/events"
  }
}
~~~

then the expression `{$request.body#/notification/target}` references the URL in the `target` property.

An expression is not an arbitrary Spring or Java template string. It is OpenAPI-defined syntax for binding a callback to data from the current message. Property names and JSON Pointers must match the actual payload.

If an expression points to a value absent from the request/response, the document may still be syntactically valid, yet clients cannot determine the callback URL at runtime. Ensure the request schema requires that field and clearly describes the URL format.

## 6. Declaring callbacks with Swagger annotations

Swagger Core provides annotations to describe callbacks on an operation. Example:

~~~java
@RestController
@RequestMapping("/api/subscriptions")
public class SubscriptionController {

    @Operation(
        summary = "Subscribe to order events",
        callbacks = {
            @Callback(
                name = "orderStatusChanged",
                callbackUrlExpression = "{$request.body#/callbackUrl}",
                operations = {
                    @CallbackOperation(
                        method = "post",
                        operation = @Operation(
                            summary = "Order status notification",
                            requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
                                required = true,
                                content = @Content(
                                    schema = @Schema(
                                        implementation = OrderStatusEvent.class
                                    )
                                )
                            ),
                            responses = {
                                @ApiResponse(
                                    responseCode = "202",
                                    description = "Event accepted"
                                )
                            }
                        )
                    )
                }
            )
        }
    )
    @PostMapping
    public SubscriptionResponse subscribe(
            @Valid @RequestBody SubscriptionRequest request) {
        return subscriptionService.subscribe(request);
    }
}
~~~

Callback annotations reside in the package `io.swagger.v3.oas.annotations.callbacks`:

- `@Callback`
- `@CallbackOperation`

Operation metadata uses `@Operation`, `@ApiResponse`, `@Content`, and `@Schema`.

In the example, `callbackUrlExpression` must point to the `callbackUrl` field of `SubscriptionRequest`. The DTO should include this field with appropriate validation:

~~~java
public record SubscriptionRequest(
    @NotBlank
    @URL
    String callbackUrl,

    @NotBlank
    String eventType
) {
}
~~~

Exact annotation names and attributes depend on the Swagger Core version bundled with Springdoc. Confirm that the dependency in use supports callback annotations before applying them.

Callback URLs usually come from client-submitted data, so the provider must treat them as untrusted input. If the server sends HTTP requests to arbitrary URLs, the callback registration endpoint can become a vector for Server-Side Request Forgery (SSRF). Allow only HTTPS and hosts on an allowlist fitting the integration model; reject loopback, private, link-local, and internal metadata addresses after DNS resolution; re-validate targets after redirects or disable redirects; and restrict outbound networking at the infrastructure layer. Simple regex checks on URLs are insufficient to prevent DNS rebinding or redirects to internal addresses.

## 7. Separating callback DTOs from subscription requests

A subscription creation request and a callback payload are two distinct messages. Do not share a single DTO just because both relate to orders.

Example subscription request:

~~~java
public record SubscriptionRequest(
    @NotBlank
    @URL
    String callbackUrl,

    @NotBlank
    String eventType
) {
}
~~~

Example event sent back by the provider:

~~~java
public record OrderStatusEvent(
    String eventId,
    String orderId,
    String status,
    Instant occurredAt
) {
}
~~~

The subscription request contains callback receiver endpoint details and event types. The callback payload contains data about the event that occurred.

In OpenAPI, the two schemas should be referenced separately:

- `SubscriptionRequest` in the request body of the subscription creation operation.
- `OrderStatusEvent` in the request body of the callback operation.

This separation helps clients clearly distinguish what data they send to the provider from what data the provider will send back.

## 8. A callback does not guarantee delivery semantics

OpenAPI describes the shape and context of a callback; it does not define the entire operational delivery mechanism.

A real-world callback system must decide:

- Retries when the client endpoint times out or returns errors.
- Retry intervals and backoff.
- Conditions for marking delivery as failed.
- Event retention periods and replay capabilities.
- How duplicate callbacks are detected.
- Event ordering and the possibility of out-of-order arrival.
- How the client acknowledges message receipt.

These rules should be documented in the operation description, callback description, or linked operational documentation. Do not leave clients guessing that a callback is delivered exactly once or always in order.

An event should carry a stable identifier such as `eventId`, occurrence timestamp, and event type so clients can implement idempotency.

## 9. Webhooks in OpenAPI 3.1

OpenAPI 3.1 adds the top-level `webhooks` property. This property describes requests that the API provider can send to the API consumer, independent of any specific operation in `paths`.

Example:

~~~yaml
openapi: 3.1.0
info:
  title: Payment API
  version: '2.0.0'

webhooks:
  paymentCompleted:
    post:
      summary: Notify payment completion
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/PaymentCompletedEvent'
      responses:
        '202':
          description: Consumer accepted the webhook

paths:
  /api/payments:
    post:
      summary: Create payment request
      responses:
        '201':
          description: Payment request created
~~~

Here:

- `webhooks` is a sibling of `paths`, `components`, and other top-level elements.
- `paymentCompleted` is the webhook name.
- `post` describes the request sent by the provider to the consumer.
- `PaymentCompletedEvent` describes the payload.
- `202` is the response returned by the webhook-receiving endpoint.

Webhooks do not belong under `paths` of the provider API because the request is sent to an endpoint operated by the consumer. The OpenAPI document describes the request shape the consumer must be ready to receive.

## 10. Differences between Callback Object and Webhooks Object

| Criterion | Callback | Webhook |
|---|---|---|
| OpenAPI version | Available since OpenAPI 3.0 | Added in OpenAPI 3.1 |
| Location | `callbacks` inside an Operation Object | `webhooks` at the document level |
| Context | Tied to a specific operation | Independent of any initiating operation |
| Target URL | Usually determined via a runtime expression | Usually registered/configured out-of-band between parties |
| Typical use case | Sending processing results back to a URL from a task-creation request | Emitting payment, order, or account events |
| Relationship to operation | Directly linked | No parent operation required |

Do not turn every callback into a webhook just because both are asynchronous requests. If the target URL is sent in an operation's request and the callback is only meaningful within that transaction, a Callback Object usually describes it more accurately.

If events are emitted independently under a long-lived subscription and are not tied to a single operation, a Webhooks Object is usually a better fit.

## 11. Selecting OpenAPI 3.1 in Springdoc

Document-level webhooks require OpenAPI 3.1 or higher. If the application outputs OpenAPI 3.0, the `webhooks` field is not part of that version's standard structure.

Springdoc has a configuration property for the OpenAPI document version in supported versions:

~~~yaml
springdoc:
  api-docs:
    version: OPENAPI_3_1
~~~

Supported configuration values and capabilities depend on the Springdoc version. Check the documentation for the exact Springdoc line in use and verify that the `openapi` field in `/v3/api-docs` is genuinely `3.1.x`.

Do not simply add `webhooks` to the model and assume the document is valid if the `openapi` field is still `3.0.x`. Validators and client generators may reject or ignore fields that do not belong to the declared version.

If a project must stay on OpenAPI 3.0 due to legacy tooling, you can describe the webhook receiver as a regular operation in a separate document intended for the API consumer, or publish a separate 3.1 document once the tool ecosystem is ready.

## 12. Adding webhooks with `OpenApiCustomizer`

Springdoc cannot automatically infer outbound webhooks from controllers alone, because the webhook receiver endpoint typically lives on a partner's system. You can add the Webhooks Object using `OpenApiCustomizer` and Swagger Core models.

Example:

~~~java
@Bean
OpenApiCustomizer paymentWebhookCustomizer() {
    return openApi -> {
        Operation operation = new Operation()
            .summary("Notify payment completion")
            .description(
                "Payment provider sends event to consumer's registered endpoint."
            )
            .requestBody(new RequestBody()
                .required(true)
                .content(new Content()
                    .addMediaType(
                        "application/json",
                        new MediaType()
                            .schema(new Schema<>()
                                .$ref("#/components/schemas/PaymentCompletedEvent"))
                    )
                )
            )
            .responses(new ApiResponses()
                .addApiResponse(
                    "202",
                    new ApiResponse()
                        .description("Consumer accepted the webhook")
                )
            );

        PathItem pathItem = new PathItem().post(operation);

        Map<String, PathItem> webhooks = new LinkedHashMap<>();
        if (openApi.getWebhooks() != null) {
            webhooks.putAll(openApi.getWebhooks());
        }
        webhooks.put("paymentCompleted", pathItem);
        openApi.setWebhooks(webhooks);
    };
}
~~~

The models used belong to `io.swagger.v3.oas.models`:

- `Operation`
- `RequestBody`
- `Content`
- `MediaType`
- `Schema`
- `ApiResponses`
- `ApiResponse`
- `PathItem`

This snippet demonstrates adding a webhook. The `PaymentCompletedEvent` schema must exist in the document's `components.schemas`; if Springdoc has not generated that schema from any DTO/controller, register the schema explicitly.

If the document already has webhooks from another customizer, do not use `Map.of` to overwrite the entire existing map. Copy the existing map, add the new entry, and set it back to avoid overwriting other webhooks.

## 13. Ensuring the webhook schema exists in `components`

You can register the schema from a DTO used in the API or add it via the model. Example DTO:

~~~java
public record PaymentCompletedEvent(
    String eventId,
    String paymentId,
    BigDecimal amount,
    String currency,
    Instant occurredAt
) {
}
~~~

If the DTO is not referenced by any operation, Springdoc may not automatically add its schema to `components.schemas`. In that case, the customizer must register the schema or establish an operation/schema reference using the version-appropriate mechanism.

One way to explicitly generate a schema with Swagger Core models is via `ModelConverters`:

~~~java
if (openApi.getComponents() == null) {
    openApi.setComponents(new Components());
}

ResolvedSchema resolved = ModelConverters.getInstance()
    .resolveAsResolvedSchema(
        new AnnotatedType(PaymentCompletedEvent.class)
    );

openApi.getComponents().addSchemas(
    "PaymentCompletedEvent",
    resolved.schema
);

if (resolved.referencedSchemas != null) {
    resolved.referencedSchemas.forEach(
        (name, schema) -> openApi.getComponents()
            .addSchemas(name, schema)
    );
}
~~~

Check the schema converters and packages matching your Swagger Core version. If the schema was already generated by Springdoc, do not add a duplicate name or inadvertently overwrite an existing schema.

When a document has multiple webhooks sharing an event schema, reuse a single component schema instead of embedding separate copies inside each operation.

## 14. Describing webhook authentication headers

Webhooks usually require a request authentication mechanism so consumers can verify the request genuinely came from the provider and the payload was not tampered with. Common approaches include:

- HMAC signature over the raw request body.
- Managed and rotated Bearer tokens.
- Mutual TLS between provider and consumer.
- Asymmetric signatures or standard message-signing schemes.

Example signature headers:

~~~http
X-Webhook-Signature: sha256=SIGNATURE_VALUE
X-Webhook-Timestamp: 1732100000
X-Webhook-Event-Id: evt-901
~~~

You can describe these headers in the webhook operation using Parameter Objects:

~~~yaml
parameters:
  - name: X-Webhook-Signature
    in: header
    required: true
    description: HMAC signature of the payload per integration specification
    schema:
      type: string
  - name: X-Webhook-Timestamp
    in: header
    required: true
    description: Request signing timestamp
    schema:
      type: integer
      format: int64
~~~

If a header represents a credential modeled as a security scheme, it can be described using `components.securitySchemes` and `security`. For HMAC signatures that change per payload, explain the canonicalization algorithm, encoding, timestamp tolerance, and signature calculation in the description or linked security documentation.

Never include real HMAC secrets in the OpenAPI document. Secrets are shared via secure provisioning channels and must have rotation/revocation procedures.

## 15. Describing responses and the retry contract

Webhook senders need to know how consumers must respond to acknowledge event receipt.

A common convention:

| Response | Possible specified meaning |
|---|---|
| 2xx | Consumer received the request |
| 400 | Invalid payload; may not retry |
| 401/403 | Invalid or unauthorized credentials |
| 429 | Consumer is rate-limiting; retry per policy |
| 5xx | Consumer hit a temporary error; provider may retry |

This is an integration convention, not something OpenAPI enforces automatically. The provider must clearly publish which statuses trigger retries, backoff intervals, retry counts, and dead-letter handling.

In OpenAPI, describe specific responses:

~~~yaml
responses:
  '202':
    description: Event accepted for asynchronous processing
  '400':
    description: Invalid payload
  '401':
    description: Invalid webhook signature
  '429':
    description: Consumer is rate-limiting
  '500':
    description: Temporary error while accepting event
~~~

Do not write “2xx means business processing completed” if the consumer only enqueues the event for later processing. Response descriptions must distinguish accepted from processed.

## 16. Idempotency, replay, and event ordering

Webhooks can be re-delivered due to timeouts, lost responses, or retries. Consumers should handle them idempotently.

An event should have a unique identifier:

~~~json
{
  "eventId": "evt-901",
  "eventType": "payment.completed",
  "occurredAt": "2026-11-20T10:30:00Z",
  "data": {
    "paymentId": "pay-1001",
    "status": "COMPLETED"
  }
}
~~~

The documentation should state:

- Within what scope `eventId` is unique.
- How long the consumer needs to retain processed IDs.
- Whether the provider can send duplicate events.
- Whether delivery attempt or timestamp headers are included.
- Whether events can arrive out of order.
- Whether a status-query API exists to reconcile missed events.

OpenAPI describes schemas and headers, but cannot guarantee exactly-once delivery on its own. Distributed systems typically aim for at-least-once delivery and require consumers to deduplicate processing.

If the provider supports replay, document how to request redelivery and any related limits.

## 17. Callbacks and webhooks in OpenAPI 3.0

OpenAPI 3.0 supports the Callback Object, though it does not yet have the top-level `webhooks` property.

If OpenAPI 3.0 must be retained, callbacks attached to operations can still be described:

~~~yaml
openapi: 3.0.3
paths:
  /api/subscriptions:
    post:
      callbacks:
        orderStatusChanged:
          '{$request.body#/callbackUrl}':
            post:
              requestBody:
                required: true
                content:
                  application/json:
                    schema:
                      $ref: '#/components/schemas/OrderStatusEvent'
              responses:
                '202':
                  description: Accepted
      responses:
        '201':
          description: Subscription created
~~~

If a webhook is not tied to an operation, you can create a separate document for the consumer side and describe the webhook-receiving endpoint under `paths`, if the goal is documenting the consumer-operated API. This does not replace provider-level outbound webhook semantics, yet it still helps consumers build receivers.

When upgrading the document to OpenAPI 3.1, also check JSON Schema differences and compatibility across validators, code generators, API gateways, and developer portals.

## 18. Notable structural changes when moving to OpenAPI 3.1

OpenAPI 3.1 does more than add `webhooks`. This version aligns the Schema Object more closely with JSON Schema 2020-12 and introduces several important structural/interpretive changes.

| Component | OpenAPI 3.0 | OpenAPI 3.1 |
|---|---|---|
| Standalone webhooks | No top-level `webhooks` | Has document-level `webhooks` |
| Schema Object | Based on a subset and extensions of JSON Schema | Aligned with JSON Schema 2020-12 |
| Null values | Has `nullable: true` | Uses a JSON Schema type union containing `null` |
| JSON Schema dialect | No root `jsonSchemaDialect` per 3.1 structure | Can declare a default dialect |
| `$ref` siblings | Restricted by 3.0 Reference Object rules | Reference Object rules expanded; verify exact context |

Example of representing nullable values:

OpenAPI 3.0:

~~~yaml
type: string
nullable: true
~~~

OpenAPI 3.1:

~~~yaml
type:
  - string
  - 'null'
~~~

Do not mechanically convert `nullable: true` into a `null` union if the schema also involves composition, references, or other constraints. Verify the schema against the target JSON Schema dialect and validator.

OpenAPI 3.1 also supports `jsonSchemaDialect` at the root level to specify the default dialect for Schema Objects. Document-processing tools must understand that dialect to interpret schemas consistently.

## 19. `$ref` and Reference Object rule changes

In OpenAPI 3.0, `$ref` in a Reference Object has strict rules; sibling fields are not processed as an arbitrary schema object. In OpenAPI 3.1, Reference Objects allow certain supplemental fields such as `summary` and `description` per the standard structure, while Schema Objects use JSON Schema rules for `$ref`.

Example schema reference:

~~~yaml
schema:
  $ref: '#/components/schemas/PaymentCompletedEvent'
~~~

When adding metadata to a reference, use the exact structure of the document version and distinguish Reference Objects from Schema Objects. Do not assume every `$ref` sibling carries the same meaning in all positions.

If an API has multiple documents consumed by older code generators, check how the tool handles `$ref` siblings before moving to OpenAPI 3.1. A document valid under the new standard may still be incompatible with older parsers.

## 20. Verifying Springdoc outputs callbacks and webhooks properly

After configuring annotations or customizers, fetch the OpenAPI JSON:

~~~http
GET /v3/api-docs
~~~

Verify callbacks:

- The parent operation has a `callbacks` field.
- The callback name is correct.
- The runtime expression matches the request/response field.
- The callback operation has the right method and request body.
- Responses describe the statuses the receiver returns.
- Referenced schemas exist in `components.schemas`.

Verify webhooks:

- The `openapi` field is `3.1.x`.
- `webhooks` sits at the root level, alongside `paths`.
- Webhook names and Path Items are accurate.
- Request body, media types, schemas, and responses are complete.
- Authentication headers and event metadata are described.
- No secrets or internal URLs are exposed.

If using document groups, verify whether webhooks appear in the appropriate group's document. Global and group-specific customizers have different scopes; do not assume a customizer applies to every document.

## 21. Testing callbacks and webhooks with contract tests

You can verify OpenAPI structure using `MockMvc` or `WebTestClient` depending on your web stack.

Example verifying a callback:

~~~java
mockMvc.perform(get("/v3/api-docs"))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$.paths['/api/subscriptions'].post.callbacks.orderStatusChanged"
    ).exists());
~~~

Example verifying a root-level webhook:

~~~java
mockMvc.perform(get("/v3/api-docs"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.openapi").value(startsWith("3.1")))
    .andExpect(jsonPath("$.webhooks.paymentCompleted.post").exists());
~~~

The `startsWith` matcher must be imported from the appropriate test library; if using another JSONPath matcher, you can parse the response and verify the `openapi` string starts with `3.1`.

Beyond checking the document, test HTTP sender/receiver behavior:

- Sender builds requests with the right URL and payload.
- Signatures are computed accurately over the transmitted payload.
- Receiver rejects invalid signatures or stale timestamps.
- Receiver handles duplicate events without repeating side effects.
- Sender retries according to policy on timeouts or retryable statuses.
- Logs do not record secrets or sensitive data.

Contract tests verify the description; integration tests verify actual delivery mechanisms.

## 22. Common mistakes

| Symptom | Cause to check |
|---|---|
| `webhooks` does not appear in OpenAPI JSON | Document is still 3.0.x or customizer did not run |
| Validator reports `webhooks` is invalid | Webhook field placed at the wrong level or document version is not 3.1 |
| Callback does not appear | Annotation not resolved by Springdoc/Swagger Core |
| Callback URL cannot be resolved | Runtime expression points to wrong field or request omits field |
| Callback schema is missing | DTO not registered in `components` |
| Webhook placed under `paths` semantically wrong | Confused consumer's receiver endpoint with provider's outbound webhook |
| Swagger UI does not display webhooks | UI version or renderer lacks full support for this section |
| Code generator ignores webhooks | Generator does not yet support OpenAPI 3.1 webhooks |
| Unclear how to verify webhook signature | Missing description of algorithm, timestamp, encoding, or raw body |
| Consumer processes an event twice | Missing idempotency keyed by event ID |
| Events arrive out of order | Missing sequence/version or reconciliation rules |
| Upgrading 3.0 to 3.1 breaks schemas | JSON Schema dialect or `nullable`/`ref` semantics changed |
| Group document lacks callbacks/webhooks | Customizer applied to the wrong group scope |

When a tool lacks webhook support, do not delete that part of the contract just to make Swagger UI look pretty. You can publish the standard 3.1 OpenAPI JSON/YAML via a developer portal or another tool with fuller support, while documenting the current UI's limitations.

## 23. Migration path and model selection

When designing asynchronous integrations:

1. Use Callback if the reverse call is tied to an operation and the URL is determined from request/response data.
2. Use Webhooks Object if the provider emits independent events and the document must describe outbound requests at the top level.
3. Use operations under `paths` when describing inbound endpoints exposed by your own API.
4. Use OpenAPI 3.1 when top-level `webhooks` are required.
5. Check whether Swagger UI, validators, code generators, and API gateways support that version/feature.
6. Document payloads, headers, responses, retries, idempotency, and security.
7. Never include real secrets or credentials in the document.
8. Use customizers to add outbound webhooks that Springdoc cannot infer from controllers.
9. Verify callback expressions and webhook root structure in OpenAPI JSON.
10. Manage schema and event contract changes as part of API versioning.

Callbacks and webhooks allow OpenAPI to describe server-initiated communication instead of only synchronous request/response calls. Callbacks attach to operations and runtime context; webhooks are document-level elements in OpenAPI 3.1. By picking the right structure, enriching outbound metadata with Springdoc, and checking tooling compatibility, clients can implement receivers with a clear understanding of payloads, security, and delivery behavior.

