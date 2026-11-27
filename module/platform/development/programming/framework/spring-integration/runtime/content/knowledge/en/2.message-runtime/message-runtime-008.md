# Header Propagation and Header Mapping

In Spring Integration, headers are the metadata layer traveling alongside the payload so endpoints can coordinate message processing. Headers can hold a correlation ID, reply channel, error channel, content type, tenant information, trace ID, or attributes extracted by an adapter from an external protocol.

Two mechanisms that are often confused are **header propagation** and **header mapping**:

- **Header propagation** is how message-producing endpoints retain and forward headers as a message moves through steps inside a Spring Integration application.
- **Header mapping** is how adapters convert between Spring `MessageHeaders` and headers/properties of an external protocol such as HTTP, AMQP, JMS, or Kafka.

Understanding both mechanisms prevents losing metadata during payload transformation, prevents accidentally sending internal headers outside, and preserves the information needed for correlation, request-reply, tracing, and error handling to work properly.

## 1. Where do headers live in a Message?

A Spring message has two parts:

- `payload`: business data processed by consumers, such as `Order`, JSON, or a byte array.
- `headers`: name/value pair metadata describing the message and how the runtime or adapter handles it.

`MessageHeaders` implements `Map<String, Object>`, yet the map itself is read-only. You cannot call `put`, `remove`, or `clear` to alter header structure after the message has been created. The payload also cannot be replaced directly on an existing message. To change the payload or headers, create a new message using `MessageBuilder` or the corresponding API.

Some common headers:

| Header | Meaning |
|---|---|
| `id` | UUID identifying a message instance; managed by the framework |
| `timestamp` | Message creation time; managed by the framework |
| `correlationId` | Key linking messages belonging to the same task or group |
| `sequenceNumber` | Position of the message in a sequence |
| `sequenceSize` | Expected number of messages in the sequence |
| `replyChannel` | Destination for replies when the flow uses request-reply |
| `errorChannel` | Destination for errors associated with the message |
| `contentType` | Content type of the payload, useful during data conversion |
| `priority` | Priority level, used by certain channels such as `PriorityChannel` |

Spring Integration defines header constants in `MessageHeaders`, `IntegrationMessageHeaderAccessor`, and adapter-specific classes such as `AmqpHeaders`, `JmsHeaders`, or `KafkaHeaders`. Using constants instead of hand-typed strings prevents typos and clarifies whether a header belongs to the framework or a protocol.

`id` and `timestamp` are read-only. When a message is created or transformed, the framework usually assigns a new ID and timestamp. Do not use `id` as an order ID or business identifier that must remain stable across multiple deliveries. If you need a cross-system identifier, create a separate header such as `app.messageKey` or `app.orderId`.

### A read-only header map does not mean every value is immutable

The header map disallows structural changes, yet a value stored in a header can still be a mutable object. If the same message is read by multiple subscribers, a shared mutable object can be modified by one consumer and affect another.

Prefer immutable, lightweight metadata values such as `String`, `UUID`, `Long`, `Integer`, `Boolean`, `Instant`, or enums. Avoid placing objects holding sessions, connections, ORM-managed entities, or large mutable structures into headers without a clear reason.

## 2. Header propagation inside a message flow

When a message passes through a `MessageChannel`, the channel forwards the message to a consumer. If no endpoint creates a new message or modifies metadata, headers remain on that message.

When an endpoint processes a message and emits an output message, Spring Integration generally propagates input headers to the output message. This propagation follows several important rules:

1. Input headers are copied to the output message if that header is not already present on the output message.
2. Headers explicitly set by the handler on the output message are preserved; input values do not overwrite existing values.
3. If a transformer returns only a new payload, the framework forwards input headers.
4. If a transformer returns a complete `Message`, the transformer's code is responsible for producing both the payload and the desired set of headers.
5. Some endpoints can be configured to omit specific headers when creating an output message.

These rules allow a processing step to update metadata without losing the rest of the request's context. For example, a service activator can add `app.processedBy`, while `correlationId` and `replyChannel` continue to be preserved unless replaced or filtered out.

### Transformers returning a payload vs. transformers returning a Message

The following two return styles have different semantics.

~~~java
// Returns a new payload: the framework propagates input headers.
Order normalize(Order order) {
    return order.normalized();
}
~~~

~~~java
// Returns a complete Message: code must explicitly decide which headers to keep.
Message<Order> normalize(Message<Order> input) {
    return MessageBuilder.withPayload(input.getPayload().normalized())
            .copyHeaders(input.getHeaders())
            .build();
}
~~~

In the second example, `copyHeaders()` copies headers from the input message to the new message. `id` and `timestamp` are read-only headers and are not overwritten in the usual manner; the new message gets its own identifying metadata. If not all headers need to be kept, selectively copy only what is required instead of copying everything.

Remember that returning a complete `Message` means application code explicitly controls the output message's context. If you forget to copy `correlationId`, `replyChannel`, or required routing headers, the flow may still run yet lose the ability to correlate or return results to the right place.

## 3. Creating and copying headers with MessageBuilder

`MessageBuilder` is the standard API for creating a new message from a payload or an existing message. Key operations:

| API | Behavior |
|---|---|
| `MessageBuilder.fromMessage(message)` | Creates a builder from an existing message, preserving payload and copyable headers |
| `MessageBuilder.withPayload(payload)` | Creates a builder with a new payload |
| `setHeader(name, value)` | Sets or replaces a header value |
| `setHeaderIfAbsent(name, value)` | Sets the header only if not already present |
| `copyHeaders(map)` | Copies headers; colliding names may overwrite |
| `copyHeadersIfAbsent(map)` | Copies only headers not yet present in the builder |
| `removeHeader(name)` | Removes a header from the new message |
| `build()` | Builds the message from the builder |

Example replacing the payload while retaining metadata and setting a source header owned by the current step:

~~~java
Message<Order> toNextStep(Message<Order> input) {
    return MessageBuilder.withPayload(input.getPayload().normalized())
            .setHeader("app.source", "orders-flow")
            .copyHeadersIfAbsent(input.getHeaders())
            .build();
}
~~~

Here `app.source` is set first. `copyHeadersIfAbsent()` only fills in missing headers, so it does not overwrite the `app.source` value set by the current step. Other headers such as `correlationId` are preserved if present on the input message.

If you want to prioritize values from the original message, copy first and then call `setHeader()`:

~~~java
Message<Order> toNextStep(Message<Order> input) {
    return MessageBuilder.withPayload(input.getPayload().normalized())
            .copyHeaders(input.getHeaders())
            .setHeader("app.source", "normalizer")
            .build();
}
~~~

Do not directly mutate the map returned by `message.getHeaders()`. Doing so violates the read-only contract and can throw `UnsupportedOperationException`.

## 4. Adding metadata with a Header Enricher

When the goal is simply to add or update metadata, there is no need to write a transformer just to build a new message. Spring Integration provides a **Header Enricher**.

A Header Enricher can set static values, reference beans, or compute values from payload/headers via expressions. Java DSL supports `.enrichHeaders(...)`.

~~~java
@Bean
IntegrationFlow enrichOrderHeaders() {
    return IntegrationFlow.from("orders.input")
            .enrichHeaders(headers -> headers
                    .header("app.source", "orders-api")
                    .headerExpression("app.region", "payload.region")
                    .headerExpression("app.receivedAt", "T(java.time.Instant).now()"))
            .channel("orders.normalized")
            .get();
}
~~~

In this example:

- `app.source` marks the ingestion source.
- `app.region` extracts region information from the payload.
- `app.receivedAt` records when the flow received the message.

Header Enricher can also set special framework headers such as `replyChannel`, `errorChannel`, `correlationId`, or `priority`. These headers directly affect how messages are routed or managed, so set them with the right data type and at the right time.

Do not arbitrarily overwrite `correlationId` mid-flow. If a splitter has created multiple messages belonging to the same group, changing the correlation ID can prevent an aggregator from gathering those messages.

## 5. Removing headers with a Header Filter

Some headers are only needed within a portion of a flow. Before sending a message out through an adapter or across another trust boundary, remove them with a **Header Filter**.

Java DSL:

~~~java
@Bean
IntegrationFlow publishOrder() {
    return IntegrationFlow.from("orders.ready")
            .headerFilter("app.internalToken", "app.debugContext", "replyChannel")
            .channel("orders.external")
            .get();
}
~~~

Header Filter produces an output message without the specified headers. It is useful when:

- A header only serves an internal endpoint.
- A header contains sensitive data that must not be sent to another system.
- A header from an inbound request could conflict with an outbound adapter's metadata.
- You do not want temporary headers appearing in persisted or transmitted messages.

Evaluate the impact before filtering `replyChannel`, `errorChannel`, `correlationId`, or sequence headers. If a gateway or downstream endpoint still needs them to send replies, route errors, or aggregate groups, removing them can break flow semantics.

## 6. Controlling propagated headers

When an endpoint produces an output message and should not carry over certain input headers, Spring Integration supports configuring a list of non-propagated headers.

`MessageProducingMessageHandler` provides `setNotPropagatedHeaders()` and `addNotPropagatedHeaders()`. Java DSL also provides the `notPropagatedHeaders()` option on endpoint configuration; XML has the `not-propagated-headers` attribute for service activators.

XML example:

~~~xml
<int:service-activator
        input-channel="orders.input"
        ref="orderService"
        method="process"
        output-channel="orders.output"
        not-propagated-headers="app.secret*, app.internalContext"/>
~~~

Simple patterns can filter by header name, such as prefixes or suffixes. Using `*` to block all propagation forces the handler to create every needed header on the output message itself.

A global list of read-only headers can be configured via the `readOnlyHeaders` property in `META-INF/spring.integration.properties` to control the default message builder's copying behavior. This is a broad setting; only use it when the policy genuinely applies uniformly across the entire application.

Note: the suppression mechanism applies to endpoints that create new messages. It does not have the same effect on endpoints that do not modify messages, such as bridges or routers, because those endpoints do not construct output messages via the same mechanism.

## 7. Header mapping at the adapter boundary

Header propagation operates within the internal message model. When a message crosses HTTP, AMQP, JMS, or Kafka, the adapter must translate between two metadata models.

That is the job of **HeaderMapper**.

The two directions can be illustrated as follows:

~~~mermaid
flowchart LR
    A["HTTP / AMQP / JMS / Kafka headers"] -->|"Inbound mapper"| B["Spring MessageHeaders"]
    B --> C["Internal message flow"]
    C --> D["Spring MessageHeaders"]
    D -->|"Outbound mapper"| E["HTTP / AMQP / JMS / Kafka headers"]
~~~

On the inbound side, the mapper reads protocol headers/properties and creates corresponding entries in `MessageHeaders`. On the outbound side, the mapper selects headers from the Spring message and writes them onto the protocol's request/message object.

For request-reply, some mappers distinguish request header sets from reply header sets. The `RequestReplyHeaderMapper` API expresses this through operations:

- `toHeadersFromRequest(...)`: reads headers from an external request into a Spring header map.
- `fromHeadersToRequest(...)`: writes Spring headers onto an external request.
- `toHeadersFromReply(...)`: reads headers from an external reply.
- `fromHeadersToReply(...)`: writes Spring headers onto an external reply.

Not every mapper implements `RequestReplyHeaderMapper`. Kafka has its own `KafkaHeaderMapper` strategy with `fromHeaders(...)` and `toHeaders(...)` operations; therefore check the interface used by the specific adapter rather than assuming all protocols share the same API.

Adapters usually come configured with a protocol-specific default mapper. When you need explicit control over which headers are transmitted, configure a custom mapper or use the adapter's mapped-header attributes.

Header mapping is not the same as payload conversion. Message converters or transformers convert the body/payload; header mappers convert metadata. Both mechanisms may run inside the same adapter, yet handle two different parts of the message.

## 8. Mapping HTTP headers

HTTP adapters and gateways use `DefaultHttpHeaderMapper` to map HTTP request/response headers with Spring `MessageHeaders`.

By default, standard HTTP headers are mapped. When customization is needed, you can declare a list of headers or wildcards. Providing a custom list replaces the default behavior; if you still need all standard headers, include the `HTTP_REQUEST_HEADERS` or `HTTP_RESPONSE_HEADERS` patterns.

Outbound HTTP gateway example:

~~~xml
<int-http:outbound-gateway
        id="partnerGateway"
        url="https://partner.example/orders"
        mapped-request-headers="HTTP_REQUEST_HEADERS, X-Trace-Id, X-Tenant-Id"
        mapped-response-headers="HTTP_RESPONSE_HEADERS, X-Partner-Request-Id"
        channel="partner.requests"/>
~~~

In this example, the gateway sends standard HTTP request headers plus two selected metadata headers; response mapping receives standard response headers and the partner's custom request ID.

You can configure `DefaultHttpHeaderMapper` independently and attach it to the adapter via the `header-mapper` attribute. Choosing patterns should match the mapping direction: outbound requests and inbound responses may need two different sets of headers.

Do not assume every `MessageHeaders` entry is a valid HTTP header. HTTP headers have rules for names and value representations; arbitrary objects in a Spring message may not convert into HTTP headers. Convert complex metadata to strings or a suitable format before mapping.

## 9. Mapping AMQP, JMS, and Kafka

Protocols have different header models. The same Spring header may be represented as a standard property, user-defined property, byte array, or serialized type depending on the protocol.

| Protocol | Common mapper | Points to watch |
|---|---|---|
| AMQP/RabbitMQ | `DefaultAmqpHeaderMapper` | Maps AMQP properties and user-defined headers per version rules; certain `x-*` headers are handled specially to avoid bouncing received metadata back |
| JMS | `DefaultJmsHeaderMapper` | Maps JMS standard properties and user properties; names and value types must obey JMS restrictions |
| Kafka | `DefaultKafkaHeaderMapper` or `JsonKafkaHeaderMapper` depending on Spring Kafka version; `SimpleKafkaHeaderMapper` for raw mapping | Kafka native headers have byte array keys and values; JSON mapper converts header objects and type metadata |

### AMQP

Standard headers are typically represented by dedicated names such as `amqp_correlationId`, `amqp_messageId`, `amqp_replyTo`, and `contentType`. Use `AmqpHeaders` constants to reference adapter-provided headers.

For user-defined headers, `DefaultAmqpHeaderMapper` supports name lists and patterns. Broad patterns can cause metadata received from the broker to be sent back to the broker or into replies. Some `x-*` headers are excluded from default mapping in certain directions; exact behavior depends on the Spring Integration version and mapper configuration.

If you only need to send a specific set of metadata, declare an allow-list. When using wildcards, carefully inspect which headers arrive from the broker and which are allowed on outgoing messages.

### JMS

JMS distinguishes standard message properties from user properties. The mapper converts JMS properties to corresponding Spring header names. JMS user properties have restrictions on valid data types and names; you cannot assume an arbitrary Java object in `MessageHeaders` will be sent as a JMS property.

When integrating request-reply, understand how `JMSCorrelationID`, `JMSReplyTo`, and corresponding Spring headers are mapped. If two systems use different correlation conventions, map them explicitly rather than relying on coincidental header name matches.

### Kafka

Kafka native headers store values as `byte[]`. The JSON mapper named `DefaultKafkaHeaderMapper` in many Spring Kafka versions is used by Spring Integration; newer Spring Kafka documentation uses the name `JsonKafkaHeaderMapper`. This mapper can use Jackson to convert rich header types to JSON. Type metadata is recorded in the special `spring_json_header_types` header so the receiver can restore appropriate types. `SimpleKafkaHeaderMapper` keeps headers as raw `byte[]` and can be configured to convert selected headers to strings.

Not every application or language understands Spring Kafka type metadata. If producer and consumer use different technologies, prefer headers with a simple contract, such as UTF-8 strings or numbers represented by a shared convention.

Mappers support patterns to restrict outbound headers. `id` and `timestamp` should generally not be sent as application headers; they are Spring's message-identifying metadata and are managed by the framework. When configuring custom patterns, verify include/exclude ordering and the mapper's trusted-type rules before deserializing objects from untrusted sources. In current JSON mappers, only a few common packages are trusted by default; if application types are needed, register the required packages explicitly via `addTrustedPackages()`. Avoid trusting all packages (`*`) when receiving messages from untrusted sources, because the mapper can instantiate objects from types described in header metadata.

## 10. replyChannel and errorChannel across serialization boundaries

`replyChannel` and `errorChannel` can contain a `MessageChannel` object or a `String` channel name.

When a message only travels through endpoints within the same application context, holding a channel reference works normally. However, if the message is serialized into a message store or sent over a broker, an object referencing a channel cannot be transferred intact to another process.

Spring Integration provides `HeaderChannelRegistry` and `DefaultHeaderChannelRegistry` to handle this scenario. The registry converts a channel reference into an identifier string and retains the mapping so the channel can be looked up when a reply or error returns. Header enricher supports `header-channels-to-string` in XML; an equivalent mechanism can be implemented via an expression calling the registry.

The registry retains mappings for a limited duration. The default value described in Spring Integration documentation is 60 seconds; configure a TTL/reaper matching the maximum time a reply may take to return. If the mapping expires before the reply arrives, the runtime can no longer resolve the original channel.

For communication across multiple independent applications, do not send an internal `MessageChannel` object over the network expecting another process to use it. Use a reply address or routing key understood by the external system, then let the receiving application's adapter/gateway map back to an internal channel.

## 11. Header propagation does not propagate ThreadLocal

Headers live inside the message, so they travel with the message when sent through an `ExecutorChannel`, queue, or other endpoint. However, values bound to the current thread do not automatically become message headers.

For example:

- Logging framework MDC may disappear when a handler runs on a different executor thread.
- Application-managed `ThreadLocal` values do not automatically travel with the message.
- Security context or transaction context is not automatically transferred merely because the message has a `correlationId`.
- Trace context requires an appropriate instrumentation/context propagation mechanism, or must be represented and extracted via standard trace headers.

If you need tracing across asynchronous boundaries, use Micrometer Observation/Tracing or the context propagation mechanism appropriate to your application stack. Trace headers can carry the required information, yet merely setting a header does not guarantee MDC, security, or transaction context is restored on another thread.

## 12. Serialization, persistence, and compatibility

When a message is saved to a `MessageStore`, a `QueueChannel` backed by a persistent store, or sent through a broker, headers must be compatible with the destination's serialization mechanism and schema.

A header object may work fine inside the JVM yet fail to serialize. A custom header class may not exist or may be version-incompatible in another consumer. Therefore:

- Prefer metadata as primitives, strings, UUIDs, standard timestamps, or structures with stable schemas.
- Avoid placing runtime objects such as `MessageChannel`, `ApplicationContext`, `Connection`, `Session`, or beans into message headers that require persistence.
- For complex objects, define serialization/deserialization rules and manage schema versions.
- Bound header sizes; large metadata inflates message size, broker cost, and serialization time.
- Do not rely on Java class names to exchange metadata contracts across independent languages or services.

A message can serialize successfully yet still be semantically incompatible. For example, a producer sends `app.priority` as the string `"5"` while the consumer expects `Integer`; the consumer may fail to parse it or behave unexpectedly. Header contracts must define name, type, units, valid values, and semantics.

## 13. Security and trust boundaries

Headers are frequently used to control routing, tenancy, retries, correlation, or access permissions. Therefore, headers received from outside must be treated as untrusted input data.

Some practical rules:

1. Map only required headers using an allow-list; avoid admitting all external headers into the flow without a clear purpose.
2. Do not forward `Authorization`, cookies, tokens, or personal data to other systems unless the integration contract requires it.
3. Do not trust caller-supplied `tenantId`, `role`, `userId`, or `securityContext`. Authenticate and attach trusted metadata at the application boundary.
4. Namespace internal headers such as `app.*` to avoid name collisions with framework or adapter headers.
5. Strip internal headers before sending through an adapter using a Header Filter or mapper rules.
6. Do not dump all headers into production logs. Redact tokens, cookies, identifying data, and sensitive information.

The `correlationId` header links messages; it is not proof of authentication. Similarly, `replyChannel` and `errorChannel` can influence message routing; do not let untrusted data control internal channels without validation.

## 14. Diagnosing missing or incorrect headers

When a downstream endpoint fails to receive expected metadata, identify at which boundary the header disappeared.

| Symptom | Possible cause | How to check |
|---|---|---|
| Header lost after transformer | Transformer returned a complete `Message` without copying headers | Check return style; use payload return or selective header copying |
| Old header overwrites new value | Improper order of `copyHeaders()` and `setHeader()` | Use `copyHeadersIfAbsent()` or set new values after copying |
| Internal header missing at broker | Outbound mapper disallows that name or value type is invalid | Check allow-list, patterns, and mapping logs |
| Header from broker missing in message | Inbound mapper excludes that name or converter cannot convert it | Check mapper, protocol properties, and native data types |
| Reply fails to return to gateway | `replyChannel` filtered out, non-serializable, or registry mapping expired | Check headers, HeaderChannelRegistry, and TTL |
| Aggregator fails to group messages | `correlationId` altered or dropped in flow | Compare correlation keys on each message and sequence headers |
| HTTP request missing metadata | Header pattern mismatch or custom list replaced defaults | Check `mapped-request-headers` and `HTTP_REQUEST_HEADERS` |
| Trace ID lost across executor | Relied solely on MDC/ThreadLocal | Check tracing instrumentation/context propagation and message headers |

An effective debugging approach is logging header names and data types at key boundaries: after the inbound adapter, after enrichers/transformers, before the outbound adapter, and after inbound replies. Do not log sensitive values. Use the same `correlationId` to link records together.

### Testing mappings

Test at least four things:

- Required headers are present after passing through internal endpoints.
- Replaced headers have the expected new values.
- Forbidden headers do not appear on outbound native messages.
- Inbound headers are converted to the expected names and types in `MessageHeaders`.

With real adapters, integration tests should verify both inbound and outbound directions on the target protocol. Unit tests checking only `MessageBuilder` are insufficient to prove that adapter mappers and converters work correctly.

## 15. Example of metadata design across a flow

Suppose an API receives an order, attaches trace and tenant metadata, normalizes the payload, and sends it to an HTTP partner. Design should partition metadata by ownership:

- API gateway authenticates the caller and creates a trusted `app.tenantId`.
- Inbound adapter or tracing instrumentation establishes trace context.
- Header Enricher adds `app.source` and reception timestamp.
- Transformer replaces the payload while preserving required headers.
- Outbound HTTP mapper forwards only allowed headers such as `X-Trace-Id` and `X-Tenant-Id`.
- Header Filter strips internal tokens or JVM-only info before sending externally.

~~~java
@Bean
IntegrationFlow partnerOrderFlow(OrderService orderService) {
    return IntegrationFlow.from("orders.in")
            .enrichHeaders(h -> h
                    .header("app.source", "order-api")
                    .headerExpression("app.receivedAt", "T(java.time.Instant).now()"))
            .transform(Order.class, orderService::normalize)
            .headerFilter("app.internalToken", "app.debugContext")
            .channel("partner.http.requests")
            .get();
}
~~~

In this flow, the transformer returns the normalized `Order` payload. By propagation rules, input headers are forwarded to the output message unless a corresponding value is already set. Before the message reaches the HTTP adapter, Header Filter removes internal metadata not permitted to leave the application. The HTTP adapter's mapper then transfers only configured headers onto the HTTP request.

In real deployments, ensure the HTTP adapter is configured with matching mapped request headers. Having `app.tenantId` in `MessageHeaders` does not automatically mean the HTTP request will carry `X-Tenant-Id`; an explicit mapping rule or custom mapper is needed to translate names and values.

## 16. Header design checklist

Before putting a flow into production, verify:

- Does every header have a clear purpose and a single component responsible for producing its value?
- Which headers are framework metadata, and which are business metadata?
- Which transformers return payloads, and which return complete messages?
- When building new messages, does code properly preserve correlation, reply/error, and routing headers?
- Which headers are allowed to propagate across service activators or handlers?
- Which headers must be filtered before leaving the trust boundary?
- Are inbound/outbound mappers configured with the right direction and allow-list?
- Are header data types compatible with HTTP, AMQP, JMS, Kafka, or message stores?
- Do `replyChannel`/`errorChannel` require HeaderChannelRegistry, and is the TTL long enough?
- Is trace context propagated across executors/brokers by an appropriate mechanism?
- Do logs and metrics support diagnostics without exposing sensitive information?

Good header design ensures messages carry enough context for accurate flow orchestration, while each adapter boundary receives only the metadata required by the target protocol and system.

## References

The official documentation below describes APIs and behavior for their respective Spring Integration/Spring Kafka versions. Check your application's actual version before applying specific configurations.

- [Spring Integration — Message and Header Propagation](https://docs.spring.io/spring-integration/reference/message.html)
- [Spring Integration — Content Enricher and Header Channel Registry](https://docs.spring.io/spring-integration/reference/content-enrichment.html)
- [Spring Integration — Message Transformation and Header Filter](https://docs.spring.io/spring-integration/reference/message-transformation.html)
- [Spring Integration — HTTP Header Mappings](https://docs.spring.io/spring-integration/reference/http/header-mapping.html)
- [Spring Integration — AMQP Message Headers](https://docs.spring.io/spring-integration/reference/amqp/message-headers.html)
- [Spring Integration — Apache Kafka Support](https://docs.spring.io/spring-integration/reference/kafka.html)
- [Spring for Apache Kafka — Message Headers](https://docs.spring.io/spring-kafka/reference/kafka/headers.html)
