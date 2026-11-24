# Callbacks and Webhooks by Specification Version Capabilities

Many APIs need to notify another system when an event occurs. For example, when an order is created, an e-commerce service might send an event to a URL registered by a partner. Another workflow might allow a client to register a URL for status updates, and the server then calls that URL once processing finishes. This is asynchronous communication: the sender does not hold an open API request waiting to return the final result.

**springdoc-openapi** can describe these flows in the OpenAPI document. You must choose the right structure according to semantics and specification version:

- **Callback Object** describes out-of-band requests initiated by the API provider and tied to a specific operation. Callbacks have existed since OpenAPI 3.0.
- **Top-level webhooks** describe requests proactively sent by the API provider to consumers, independent of any active operation. The `webhooks` field was added in OpenAPI 3.1.

These two structures describe the contract. They do not automatically create endpoints, send callbacks, manage queues, perform retries, or verify signatures. The runtime implementation still must be built in the application.

## 1. Distinguishing callbacks and webhooks

In everyday conversation, callback and webhook are sometimes used interchangeably. When authoring OpenAPI, distinguish them by the relationship between the event and an operation:

| Criterion | Callback | Webhook |
| --- | --- | --- |
| Relationship to operation | Attached to a specific operation | Independent of any active operation |
| When sent | After the client invokes the parent operation and the related event occurs | Whenever an event is emitted, potentially at any time |
| Target address | Typically pulled from request/response data via a runtime expression | Address configured by the consumer in a registration flow or outside the document |
| Location in OpenAPI | `callbacks` property of the Operation Object | Top-level `webhooks` field of the OpenAPI Object |
| Version | OpenAPI 3.0 and later | OpenAPI 3.1 and later |
| Example | Client sends `callbackUrl` when creating a subscription; server calls that URL when status changes | Service sends an `orderCreated` event to registered subscribers |

A typical callback flow:

1. The client calls `POST /api/subscriptions` and sends `callbackUrl`.
2. The server stores the subscription and returns `subscriptionId`.
3. When the order changes, the server sends `POST` to the registered `callbackUrl`.
4. The callback-receiving system returns a `2xx` status code to acknowledge receipt.

A typical webhook flow:

1. The consumer subscribes to one or more event types.
2. The provider stores the event-receiving endpoint configuration.
3. When an event occurs, the provider sends an HTTP request to that endpoint.
4. The consumer verifies the request, processes the event, and returns an acknowledgement response.

In OpenAPI, webhooks in the `webhooks` field are requests sent outward from the API provider to the consumer. If your Spring Boot application receives webhooks from an external service, that receiving endpoint is still a normal HTTP operation under `paths`. The direction of the request determines how it is modeled; naming in code does not dictate the specification structure.

## 2. Callbacks in OpenAPI 3.0 and 3.1

OpenAPI 3.0 already includes the Callback Object. A callback is declared inside the operation it belongs to. A callback consists of one or more runtime expressions; each expression maps to a Path Item Object describing the HTTP request the API provider will send.

OpenAPI 3.1 continues supporting callbacks and adds the document-level `webhooks` field. Therefore, when a project uses OpenAPI 3.0, you can still document operation-bound callbacks. If you need to document standalone webhooks using the standard structure, you must emit OpenAPI 3.1 or later.

| Specification version | Callback Object | Top-level webhooks |
| --- | --- | --- |
| OpenAPI 3.0.x | Yes | Not in the standard |
| OpenAPI 3.1.x | Yes | Yes |

Do not change the version label in JSON by manually editing the `openapi` field. The document's structure and schemas must match the declared version. If using OAS 3.1 features, configure springdoc and a `swagger-core` version that supports OAS 3.1.

## 3. Runtime expressions identifying the callback URL

The Callback Object uses a runtime expression as its key. The expression is evaluated from the parent operation's HTTP request or response at runtime.

Commonly used data sources:

| Expression | Value read |
| --- | --- |
| `$request.body#/callbackUrl` | `callbackUrl` property in the request body |
| `$request.query.callbackUrl` | Query parameter `callbackUrl` |
| `$request.header.X-Callback-Url` | Request header `X-Callback-Url` |
| `$request.path.subscriptionId` | Path parameter `subscriptionId` |
| `$response.header.Location` | Response header `Location` |
| `$url` | Current request URL |
| `$method` | Current request HTTP method |
| `$statusCode` | Response status code |

In YAML, the callback key is typically wrapped in single quotes with the expression inside curly braces:

~~~yaml
callbacks:
  orderStatusChanged:
    '{$request.body#/callbackUrl}':
      post:
        summary: Send order status update
        responses:
          '200':
            description: Consumer received the callback
~~~

The expression must match the actual payload structure. If the request body has the shape:

~~~json
{
  "notification": {
    "callbackUrl": "https://consumer.example.com/events"
  }
}
~~~

then the expression must reference `/notification/callbackUrl`. JSON Pointer is case-sensitive on property names and supports character escaping per JSON Pointer rules.

A runtime expression only tells OpenAPI-reading tools how to determine the callback target from the message. It does not validate the URL, verify domain ownership, or send HTTP requests itself.

## 4. Describing a callback in YAML

Example of an API allowing clients to register a URL for order events:

~~~yaml
openapi: 3.0.3
paths:
  /api/subscriptions:
    post:
      operationId: createOrderSubscription
      summary: Subscribe to order events
      description: Save the URL that the server will call when an order changes.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateSubscriptionRequest'
      responses:
        '201':
          description: Subscription created
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/SubscriptionView'
      callbacks:
        orderStatusChanged:
          '{$request.body#/callbackUrl}':
            post:
              operationId: receiveOrderStatusChanged
              summary: Receive status change notification
              parameters:
                - name: X-Webhook-Signature
                  in: header
                  required: true
                  schema:
                    type: string
              requestBody:
                required: true
                content:
                  application/json:
                    schema:
                      $ref: '#/components/schemas/OrderStatusEvent'
              responses:
                '200':
                  description: Callback accepted
components:
  schemas:
    CreateSubscriptionRequest:
      type: object
      required:
        - callbackUrl
      properties:
        callbackUrl:
          type: string
          format: uri
          description: HTTPS URL managed by the consumer to receive events
          example: https://consumer.example.com/order-events
    SubscriptionView:
      type: object
      properties:
        subscriptionId:
          type: string
          example: sub-1001
        status:
          type: string
          example: ACTIVE
    OrderStatusEvent:
      type: object
      required:
        - eventId
        - orderId
        - status
      properties:
        eventId:
          type: string
          example: evt-9001
        orderId:
          type: string
          example: ord-1001
        status:
          type: string
          example: SHIPPED
~~~

In this document:

- Operation `createOrderSubscription` is the parent operation invoked by the client.
- `callbacks.orderStatusChanged` describes the `POST` request sent later by the provider.
- The key `{$request.body#/callbackUrl}` indicates the callback URL comes from the parent operation's request body.
- The callback request body is `OrderStatusEvent`, distinct from `CreateSubscriptionRequest`.
- The signature header is described as part of the callback request so the consumer knows how to verify it.

A callback operation is not a controller endpoint served by the provider application itself. It describes a request sent to the consumer system. If the consumer wants to document its own API in a separate spec, it can publish its `POST /order-events` endpoint there.

## 5. Declaring callbacks with Swagger annotations

Swagger Core provides the **@Callback** annotation to attach callbacks at the method level. Springdoc reads OpenAPI annotations from controllers and converts them into Callback Objects when the dependency version supports it.

Example subscription DTO:

~~~java
import jakarta.validation.constraints.NotBlank;

public record CreateSubscriptionRequest(
    @NotBlank
    String callbackUrl
) {}
~~~

Event DTO:

~~~java
public record OrderStatusEvent(
    String eventId,
    String orderId,
    String status
) {}
~~~

Controller declaring the callback:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.callbacks.Callback;
import io.swagger.v3.oas.annotations.enums.ParameterIn;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.parameters.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
class SubscriptionController {

    @Operation(
        operationId = "createOrderSubscription",
        summary = "Subscribe to order events"
    )
    @Callback(
        name = "orderStatusChanged",
        callbackUrlExpression = "{$request.body#/callbackUrl}",
        operation = @Operation(
            method = "post",
            summary = "Send order status change event",
            parameters = @Parameter(
                name = "X-Webhook-Signature",
                in = ParameterIn.HEADER,
                required = true,
                description = "Signature for consumer to verify payload",
                schema = @Schema(type = "string")
            ),
            requestBody = @io.swagger.v3.oas.annotations.parameters.RequestBody(
                required = true,
                content = @Content(
                    mediaType = "application/json",
                    schema = @Schema(implementation = OrderStatusEvent.class)
                )
            ),
            responses = @ApiResponse(
                responseCode = "200",
                description = "Consumer received the callback"
            )
        )
    )
    @PostMapping("/api/subscriptions")
    SubscriptionView create(
        @Valid @RequestBody CreateSubscriptionRequest request
    ) {
        return subscriptionService.create(request);
    }
}
~~~

In this example, **@Callback** sits on the controller method and the nested operation describes the callback's HTTP method, request body, header, and response. The annotation documents the contract; the service still has to store the subscription, emit the event, and send the request to the target URL.

Annotation attribute names can vary across `swagger-annotations` generations. The example above uses the Swagger Core 2.x API; check the Javadoc of the exact version managed by springdoc before copying into a project. If the annotation does not produce a callback in the document, you can use `OpenApiCustomizer` to add the Callback Object to the operation.

## 6. Standalone webhooks in OpenAPI 3.1

For webhooks not tied to a specific operation, OpenAPI 3.1 provides the top-level **webhooks** field. Each key is the logical name of the event type; the value is a Path Item Object describing the request the API provider will send to the consumer.

Example:

~~~yaml
openapi: 3.1.0
info:
  title: Order Event API
  version: 1.0.0
webhooks:
  orderCreated:
    post:
      operationId: receiveOrderCreated
      summary: Receive order created event
      description: Provider sends this request when a new order is created.
      parameters:
        - name: X-Webhook-Signature
          in: header
          required: true
          description: HMAC signature of the payload and timestamp
          schema:
            type: string
        - name: X-Webhook-Event-Id
          in: header
          required: true
          schema:
            type: string
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/OrderCreatedEvent'
      responses:
        '200':
          description: Consumer received the event
        '202':
          description: Consumer accepted and queued the event for processing
components:
  schemas:
    OrderCreatedEvent:
      type: object
      required:
        - eventId
        - eventType
        - occurredAt
        - data
      properties:
        eventId:
          type: string
          example: evt-2026-0001
        eventType:
          type: string
          const: order.created
        occurredAt:
          type: string
          format: date-time
        data:
          type: object
          required:
            - orderId
          properties:
            orderId:
              type: string
              example: ord-1001
            total:
              type: number
              example: 1250000
~~~

The `webhooks` field does not need a URL expression like callbacks. It describes the type of request the provider will send; the consumer's destination address is typically configured in a registration flow or subscription management system. The documentation should clearly explain how consumers register URLs and event types.

In OAS 3.1, schemas use modern JSON Schema, such as **const** to restrict `eventType` to a single value. If the document must remain OAS 3.0 compatible, do not use the standard `webhooks` field and do not assume `const` has the same support; use a single-element enum or an appropriate compatible mechanism.

## 7. Selecting OpenAPI 3.1 in springdoc

To have springdoc emit the top-level `webhooks` field, the application must generate an OpenAPI 3.1 specification and use a `swagger-core`/`swagger-models` version that supports this field. In springdoc versions supporting the corresponding configuration property, set in `application.properties`:

~~~properties
springdoc.api-docs.version=OPENAPI_3_1
~~~

Or `application.yml`:

~~~yaml
springdoc:
  api-docs:
    version: OPENAPI_3_1
~~~

Property names and enum values should be checked against the documentation of the springdoc version in use. After startup, check the **openapi** field in JSON at `/v3/api-docs`. The value must be a `3.1.x` version before adding `webhooks`.

If the project is emitting `3.0.x`, the `webhooks` structure may be ignored, omitted during serialization, or rejected by validators depending on the model version and configuration. Do not work around this by manually patching the final JSON string; upgrade to a compatible dependency set and configure the spec version directly in springdoc.

## 8. Adding webhooks with OpenApiCustomizer

Springdoc supports customizing the OpenAPI model via **OpenApiCustomizer**. This is useful when a webhook does not correspond to a controller method in the application or annotations are insufficient to describe it.

The following example adds an `orderCreated` webhook to an OpenAPI 3.1 document:

~~~java
import io.swagger.v3.oas.models.Operation;
import io.swagger.v3.oas.models.PathItem;
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.media.Content;
import io.swagger.v3.oas.models.media.MediaType;
import io.swagger.v3.oas.models.media.Schema;
import io.swagger.v3.oas.models.parameters.RequestBody;
import io.swagger.v3.oas.models.responses.ApiResponse;
import io.swagger.v3.oas.models.responses.ApiResponses;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springdoc.core.utils.SpringDocAnnotationsUtils;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class WebhookOpenApiConfiguration {

    @Bean
    OpenApiCustomizer orderWebhookCustomizer() {
        return openApi -> {
            if (openApi.getComponents() == null) {
                openApi.setComponents(new Components());
            }

            Schema<?> eventSchema =
                SpringDocAnnotationsUtils.extractSchema(
                    openApi.getComponents(),
                    OrderCreatedEvent.class,
                    null,
                    null,
                    openApi.getSpecVersion()
                );

            PathItem webhook = new PathItem().post(
                new Operation()
                    .operationId("receiveOrderCreated")
                    .summary("Receive order created event")
                    .requestBody(
                        new RequestBody()
                            .required(true)
                            .content(
                                new Content().addMediaType(
                                    "application/json",
                                    new MediaType().schema(eventSchema)
                                )
                            )
                    )
                    .responses(
                        new ApiResponses().addApiResponse(
                            "200",
                            new ApiResponse()
                                .description("Consumer received the event")
                        )
                    )
            );

            openApi.addWebhooks("orderCreated", webhook);
        };
    }
}
~~~

**SpringDocAnnotationsUtils.extractSchema** helps springdoc inspect the DTO type and register the referenced schema in `components`. Then **addWebhooks** attaches the Path Item to the `webhooks` field of the OpenAPI model. These model APIs depend on the `swagger-core` version; `addWebhooks` belongs to OpenAPI 3.1 support in `swagger-models` 2.2.0 and later. Check the actual dependencies and OAS 3.1 configuration of the application.

A default **OpenApiCustomizer** bean applies to the default document. If the project uses **GroupedOpenApi**, attach the customizer to the appropriate group or use **GlobalOpenApiCustomizer** when the webhook must appear in all groups. Avoid adding the same webhook multiple times if customizers are registered at both group and global scopes.

The code example assumes **OrderCreatedEvent** is a valid DTO in the project. If the model carries annotations such as **@Schema**, springdoc can use them when extracting the schema. When a customizer attaches security, headers, or complex responses, add the corresponding components to the Path Item and verify the output JSON.

## 9. Securing callbacks and webhooks

Callback URLs and webhooks sit on the boundary between two systems. Documentation should describe how to verify requests, and the runtime must perform checks before processing payloads.

### Payload signatures

A common pattern is for the provider to send:

- A signature header, such as `X-Webhook-Signature`.
- A timestamp to limit request age.
- An event ID to identify the event delivery.
- A JSON payload containing the event data.

The consumer uses a pre-shared secret to recompute the HMAC signature over the agreed content, compares it in constant time, and validates the timestamp. Never embed secrets directly in the callback URL or query string because URLs frequently appear in logs, histories, and monitoring systems.

If using HTTP Bearer authentication instead of a custom signature, declare the security scheme under `components.securitySchemes` and attach the security requirement to the callback/webhook operation. For custom signatures such as `X-Webhook-Signature`, describe the header with a Parameter Object because it is a business-protocol header of the webhook.

### Validating callback URLs

When a server accepts a URL supplied by a client and actively sends requests to that URL, protect against SSRF:

- Only allow HTTPS unless another business reason requires otherwise.
- Use a domain allow-list or verify endpoint ownership.
- Block loopback, private network, link-local, and metadata endpoints.
- Check DNS resolution and handle redirects carefully so the allow-list is not bypassed.
- Limit ports, timeouts, response sizes, and redirect counts.
- Never send internal credentials or sensitive headers to client-controlled URLs.
- Let consumers verify URL ownership via a challenge before activating a subscription when appropriate.

The `uri` format in OpenAPI only documents that the value is a URI; it does not enforce any of the safety checks above.

## 10. Retries, idempotency, and event ordering

OpenAPI describes request/response shapes, yet does not standardize retry policies, timeouts, or event ordering guarantees. Provider and consumer must agree on operational rules.

| Topic | What to publish |
| --- | --- |
| Delivery acknowledgement | Which `2xx` codes are treated as acknowledged |
| Retry | Wait intervals, backoff, retry count, and delivery window |
| Idempotency | Using `eventId` or `deliveryId` to detect duplicate events |
| Ordering | Whether ordering per aggregate/`orderId` is guaranteed |
| Timeout | Response wait time before retrying |
| Payload size | Body size limits and handling of large payloads |
| Event versioning | Schema evolution rules and deprecation window for older versions |
| Unsubscribing | How to cancel a subscription or disable an endpoint |

Webhooks are commonly delivered with at-least-once semantics: a consumer may receive the same event multiple times if the provider does not receive an acknowledgement. Consumers should process idempotently, store processed `eventId`s, and return an acknowledgement response only after persistently recording the event. Returning `2xx` before persistence succeeds risks losing events if the process terminates unexpectedly.

Do not assume a `500` response always triggers a retry or a `200` response means business processing is complete. Explicitly document status code semantics in `description` and integration guides.

## 11. Testing and verifying the generated documentation

After starting the application, fetch the OpenAPI JSON:

~~~bash
curl -sS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Check the specification version:

~~~bash
jq -r '.openapi' openapi.json
~~~

Check operation-bound callbacks:

~~~bash
jq '.paths["/api/subscriptions"].post.callbacks' openapi.json
~~~

Check top-level webhooks:

~~~bash
jq '.webhooks' openapi.json
~~~

Verify these points:

1. Callbacks sit under the right parent operation.
2. Runtime expressions point to the right fields in the request or response.
3. Callback operations have the right HTTP method, request body, headers, and responses.
4. Webhooks appear under top-level `webhooks` only when the document uses OAS 3.1.
5. Each webhook has a unique `operationId` within the document.
6. All `$ref` references to `components.schemas` exist.
7. Security schemes and signature headers match how the provider actually sends requests.
8. Swagger UI or OpenAPI-reading tools can render the callback/webhook.

Swagger UI can display callback or webhook structures, yet it does not register URLs, emit events, or simulate the entire asynchronous flow itself. Test the runtime using a test consumer or mock HTTP server to verify destination URLs, signatures, payloads, retries, and acknowledgements.

## 12. Common errors

**Callback does not appear in documentation.** Check that **@Callback** is placed on the right method, `callbackUrlExpression` has a value, and the `swagger-annotations`/`springdoc` version supports that annotation. If needed, add the callback via `OpenApiCustomizer` and inspect the `callbacks` property of the operation in JSON.

**Webhook does not appear at top-level.** Check whether the document truly emits OAS 3.1, whether `swagger-models` supports the `webhooks` field, and whether the customizer runs on the right document/group.

**Changed `openapi` to 3.1 but webhooks are still missing.** Do not patch the version string after generating the document. Configure springdoc to use OAS 3.1 and upgrade compatible dependencies so the model includes the `webhooks` field.

**Using `paths` to document outbound webhooks.** Re-examine the request direction. If the provider proactively calls the consumer's endpoint, it is a callback or top-level webhook; `paths` describes endpoints exposed by the API provider. If your application receives webhooks from an external service, the receiving endpoint belongs in your application's `paths`.

**Callback URL expression is not substituted.** Check field names, JSON structure, JSON Pointer, and curly braces. Expressions in the specification are not Spring MVC placeholders.

**Webhook schema is missing.** When creating Path Items manually, ensure schemas are registered in `components`. Use `SpringDocAnnotationsUtils.extractSchema` or add explicit schemas.

**Webhook delivered twice and consumer processes duplicates.** Use `eventId`/`deliveryId` for idempotency; do not rely on the provider delivering only once.

**Callback URL points to internal resources.** Validate the URL and resolved IP addresses after DNS resolution, restrict redirects, and apply allow-lists before the server sends requests.

## 13. Selection and implementation checklist

- [ ] Determined whether the API provider sends operation-bound requests or independent events.
- [ ] Used Callback Object for operation-bound callbacks.
- [ ] Used top-level `webhooks` for standalone webhooks in OpenAPI 3.1 or later.
- [ ] Avoided declaring standard `webhooks` field in OAS 3.0.
- [ ] Configured the right OpenAPI version and compatible `swagger-core`/`swagger-models` dependencies.
- [ ] Used runtime expressions matching the actual message structure.
- [ ] Documented method, headers, request body, responses, and security of callbacks/webhooks.
- [ ] Registered all component schemas when using customizers.
- [ ] Validated callback URLs, signatures, timestamps, and replay protection.
- [ ] Defined retries, timeouts, idempotency, ordering, and versioning.
- [ ] Verified `/v3/api-docs`, Swagger UI, and runtime HTTP send/receive flows.

## 14. Conclusion

Callbacks and webhooks allow APIs to notify events without forcing clients to poll continuously. OpenAPI 3.0 supports operation-bound callbacks; OpenAPI 3.1 adds top-level `webhooks` for standalone events. Springdoc can generate callbacks from annotations and lets you add webhooks via `OpenApiCustomizer` when supported by the model/version. Identify request direction accurately, pick the structure matching the specification version, document payloads and security mechanisms, and test both the documentation and actual send/receive behavior.

## 15. References

- [OpenAPI Specification 3.0.3 — Callback Object](https://spec.openapis.org/oas/v3.0.3.html#callback-object): operation-bound callbacks and runtime expressions.
- [OpenAPI Specification 3.1.1 — Callback Object and Webhooks Object](https://spec.openapis.org/oas/v3.1.1.html#callback-object): callbacks and the top-level `webhooks` field.
- [Swagger Core 2.2 — @Callback annotation](https://docs.swagger.io/swagger-core/v2.2.30/apidocs/io/swagger/v3/oas/annotations/callbacks/Callback.html): placement and attributes of the callback annotation.
- [Springdoc — Configuration Properties](https://springdoc.org/properties.html): configuring the generated OpenAPI version.
- [Springdoc — FAQ: Programmatic OpenAPI customization](https://springdoc.org/faq.html): using OpenAPI Bean, `OpenApiCustomizer`, and `GlobalOpenApiCustomizer`.
