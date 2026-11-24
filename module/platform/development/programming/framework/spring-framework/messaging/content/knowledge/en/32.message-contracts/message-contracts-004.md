# Naming Conventions for Destinations, Routes, and Schemas

In a messaging system, naming is part of the communication contract. Producers need to know where to send messages; consumers need to know where to subscribe; and both sides need to understand the structure and meaning of the payload. If destinations, routes, and schemas are named arbitrarily, the system becomes hard to trace, hard to upgrade, and error-prone as multiple services evolve together.

In Spring, these concepts are related but not identical:

- **Destination** is the target address of a message in a messaging mechanism or broker, such as a STOMP destination or a JMS queue/topic.
- **Route** is the routing name of an RSocket request. The route is carried in routing metadata and mapped by Spring to a handler.
- **Schema** describes the structure and meaning of the payload: fields, data types, nullability rules, units of measurement, timestamp formats, and evolution rules.

An important principle: a destination or route determines where a message goes; a schema determines what data the message contains. Renaming a route does not automatically change the schema, and changing a Java DTO does not automatically alter a broker destination.

## 1. Distinguishing Destinations, Routes, and Schemas in Spring

| Concept | Role | Example |
|---|---|---|
| STOMP destination | Address for clients to send or subscribe over WebSocket/STOMP | /app/orders/submit, /topic/orders/created |
| JMS destination | Queue or topic name managed by the broker/provider | orders.commands.submit.v1 |
| RSocket route | Routing key directing a request to a responder | orders.submit.v1 |
| Payload schema | Data contract serialized inside the message | OrderSubmitRequestV1, OrderSubmittedEventV1 |

### STOMP Destination

In Spring WebSocket support, destinations starting with an application prefix are routed to methods annotated with @MessageMapping. Destinations starting with a broker prefix are forwarded to the message broker to handle subscriptions and message distribution.

A common configuration:

~~~java
@Configuration
@EnableWebSocketMessageBroker
class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

With the configuration above, a client sending to /app/orders/submit is routed to the handler mapped to /orders/submit. Clients can subscribe to /topic/orders/created to receive events. The /app prefix is an application convention; /topic and /queue are conventions for distinguishing usage patterns.

Note: with the built-in simple broker, /topic and /queue do not inherently enforce special broker semantics. They are primarily conventions to distinguish pub-sub from point-to-point. When using an external broker, check the semantics and naming rules supported by that broker.

### JMS Destination

In JMS, a destination is typically a Queue or Topic configured in the broker. A Queue typically serves point-to-point messaging; a Topic typically serves publish-subscribe. Destination names must match the actual broker and listener container configuration.

Example:

~~~java
@Component
class OrderMessageConsumer {

    @JmsListener(destination = "orders.events.created.v1")
    void onOrderCreated(OrderCreatedEventV1 event) {
        orderProjection.update(event);
    }
}
~~~

Producers can send to a destination using JmsTemplate:

~~~java
jmsTemplate.convertAndSend(
    "orders.commands.submit.v1",
    command
);
~~~

A queue or topic name does not determine semantics on its own. Destination type, subscription mode, durability, acknowledgement, and listener container configuration determine how messages are delivered and acknowledged.

### RSocket Route

RSocket uses a route in metadata to select a handler. Spring lets you declare routes with @MessageMapping, and requesters specify routes with RSocketRequester.

~~~java
@Controller
class OrderRSocketController {

    @MessageMapping("orders.submit.v1")
    Mono<OrderReceipt> submit(OrderSubmitRequestV1 request) {
        return orderService.submit(request);
    }
}
~~~

The requester calls the corresponding route:

~~~java
Mono<OrderReceipt> response = requester
    .route("orders.submit.v1")
    .data(request)
    .retrieveMono(OrderReceipt.class);
~~~

RSocket routes can be hierarchical and use dots as separators by default. A route is not a URL path; do not add leading slashes or apply URL encoding rules to routes. If a custom route matcher is used, both requester and responder must follow the same routing contract.

## 2. General Naming Rules

Standardize conventions across a bounded context or system, then map them to the syntax of each transport.

### Use Names That Describe Domain and Purpose

A name should answer three questions: which domain does the message belong to, which entity/subject is it about, and what action or event does it serve?

Examples:

- orders.submit: request to create an order.
- orders.cancel: request to cancel an order.
- orders.events.created: event that an order has been created.
- orders.events.cancelled: event that an order has been cancelled.
- inventory.reserve: request to reserve inventory.
- inventory.events.reserved: event that inventory has been reserved.

Avoid overly generic names such as message, data, update, process, event, or topic1. These names do not convey clear business intent and tend to get reused for unrelated contracts.

### Distinguish Commands, Queries, and Events

Use imperative verbs for commands, query action names for queries, and past tense for events.

| Message Type | Naming Pattern | Examples |
|---|---|---|
| Command | Verb + object | SubmitOrder, CancelOrder |
| Query | Get/Find/List + object | GetOrder, FindOrders |
| Event | Object + past action | OrderSubmitted, OrderCancelled |
| Response | Result object | OrderReceipt, OrderView |

A command represents an intent to perform an action; an event represents something that has already happened. Do not name an event like a command, as consumers may mistake an event notification for an execution request.

### Standardize Casing and Separators

A practical convention:

- Use lowercase ASCII for destination and route names.
- Use dots for hierarchical messaging-style routes or destinations.
- For STOMP, use slashes for path-style destination namespaces if the application adopts that convention.
- Do not arbitrarily mix dots, underscores, hyphens, and slashes within the same namespace.
- Avoid spaces, diacritics, control characters, or cryptic abbreviations.
- Keep casing consistent between producers and consumers.

For example, the same intent can be expressed per transport:

| Purpose | STOMP | RSocket | JMS |
|---|---|---|---|
| Send create-order command | /app/orders/submit | orders.submit.v1 | orders.commands.submit.v1 |
| Receive order-created event | /topic/orders/created | orders.events.created.v1 | orders.events.created.v1 |
| Receive private notification | /user/queue/notifications | notifications.user | notifications.user |

These are application convention examples, not mandatory Spring names. Choose a consistent style and verify support with your broker or route matcher.

### Avoid Embedding Variable or Sensitive Data in Names

Do not use order IDs, email addresses, access tokens, phone numbers, or personal data as part of static destination names. For parameterized routes, include only necessary, non-sensitive identifiers in the route pattern; keep full business data in the payload or controlled metadata.

Example RSocket route pattern:

~~~java
@MessageMapping("orders.{orderId}.status")
Mono<OrderStatus> status(@DestinationVariable String orderId) {
    return orderService.findStatus(orderId);
}
~~~

A requester can invoke a specific route like orders.O-100.status. Authenticate and authorize based on the principal and access policy; knowing a route name does not mean the caller is allowed to invoke it.

Do not hardcode dev, test, or prod environments into contract names in code if infrastructure can isolate environments via broker configuration, namespaces, or accounts. If multi-tenant partitioning is needed, explicitly define authorization rules and access boundaries.

## 3. Naming According to Destination Semantics

Names should reflect how messages are used, though they do not replace transport-level semantic configuration.

### Queues for Work to Be Processed

A queue typically represents work to be handled by one consumer in a competing consumer group. You can use a commands suffix or namespace:

- orders.commands.submit.v1
- billing.commands.capture-payment.v1
- inventory.commands.reserve.v1

If there are retry or dead-letter destinations, name them under the same namespace:

- orders.commands.submit.v1.retry
- orders.commands.submit.v1.dlq

Retry and DLQ names must match the actual broker configuration. Naming alone does not create destination behavior; you must configure bindings, policies, TTL, dead-letter routing, and access permissions accordingly.

### Topics for Events to Be Distributed

Topics are typically used when multiple subscribers need to receive the same event type. You can use an events namespace:

- orders.events.created.v1
- orders.events.cancelled.v1
- payments.events.captured.v1

Event names should express what occurred. Consumers can subscribe per event or by pattern if the broker supports it.

### User-Targeted Destinations

Spring STOMP supports user destinations with the /user/ prefix. For example, a client subscribes to /user/queue/notifications to receive notifications specific to an authenticated session or user. Spring translates this logical destination into a session-specific internal destination.

Do not manually concatenate usernames into destinations and let clients subscribe arbitrarily. Use the user destination mechanism and ensure user identity is authenticated on the server.

## 4. RSocket Route Naming Conventions

An RSocket route is a logical name agreed upon by requester and responder as the entry point for a request. A route typically follows the structure:

**domain.action.version**

Examples:

- orders.submit.v1
- orders.cancel.v1
- orders.find-by-id.v1
- inventory.reserve.v1
- pricing.calculate.v1

Key guidelines:

1. Use stable, concise names that accurately describe the handler's capability.
2. Keep the same namespace ordering across routes within a domain.
3. Use a consistent convention for action names, such as submit, cancel, find-by-id.
4. Include a version in the route only when incompatible contracts must be distinguished.
5. Avoid overloading the same route name for handlers with different semantics.
6. Do not implicitly use Java class names as routes; a route is a wire-level contract and should be declared explicitly.

Spring supports route patterns and @DestinationVariable. Example:

~~~java
@Controller
class OrderStatusController {

    @MessageMapping("orders.{orderId}.status")
    Mono<OrderStatusV1> status(
            @DestinationVariable String orderId) {
        return orderService.findStatus(orderId);
    }
}
~~~

Do not change a route merely because a Java package, class, or method was renamed. You should be able to refactor internal implementations while keeping public routes stable.

## 5. Schema and DTO Naming Conventions

A schema is the contract of the payload. Schema names should remain stable across code refactorings and clearly describe the message type and contract version.

A readable convention:

- Command: OrderSubmitRequestV1 or SubmitOrderCommandV1.
- Event: OrderCreatedEventV1 or OrderSubmittedEventV1.
- Query: GetOrderQueryV1.
- Response: OrderReceiptV1 or OrderViewV1.

Use the same convention across the entire domain. Suffixes like Command, Event, Query, and Response immediately clarify the payload's purpose when reading code.

Example:

~~~java
public record SubmitOrderCommandV1(
    String orderId,
    String customerId,
    BigDecimal total,
    String currency
) {}

public record OrderCreatedEventV1(
    String eventId,
    String orderId,
    Instant occurredAt,
    BigDecimal total,
    String currency
) {}

public record OrderReceiptV1(
    String orderId,
    String status
) {}
~~~

Java class names can change during refactoring. If schemas are shared across multiple languages or services, define a stable schema ID independent of Java packages.

Example logical IDs:

- com.acme.orders.SubmitOrderCommand.v1
- com.acme.orders.OrderCreatedEvent.v1

Example JSON Schema filenames:

- orders.submit-order-command.v1.schema.json
- orders.order-created-event.v1.schema.json

With Protobuf, you can include the major version in the package:

~~~proto
syntax = "proto3";

package acme.orders.v1;

message OrderCreatedEvent {
  string event_id = 1;
  string order_id = 2;
  string occurred_at = 3;
  string currency = 4;
}
~~~

Never reuse deleted field numbers in Protobuf. Mark old field numbers and names as reserved to prevent new payloads from being misinterpreted under an old schema.

## 6. Naming and Documenting Schema Fields

Field names are also part of the contract. A good field should have a clear name and stable semantics.

Best practices:

- Use camelCase for JSON fields if that is the agreed convention.
- Use names that express business meaning, such as orderId, occurredAt, currency.
- Distinguish message IDs from aggregate IDs: eventId is distinct from orderId.
- Use timestamps with explicit timezone or UTC convention, e.g., ISO-8601.
- Document units of measurement or currency. Do not use `amount` without specifying currency and scale.
- Specify whether each field is required, nullable, has a default, and its valid value range.
- Avoid vague names such as value, type, or statusCode without clear context.

Payload example:

~~~json
{
  "eventId": "evt-1001",
  "orderId": "O-100",
  "occurredAt": "2026-11-07T10:30:00Z",
  "total": 125000,
  "currency": "VND"
}
~~~

In this contract, occurredAt is when the event occurred, and whether total is in minor or major currency units must be explicitly stated in the schema documentation. Currency uses ISO 4217 codes if the domain needs to represent currency. Do not rely on field names alone to infer undocumented rules.

Do not reuse a single field for different meanings across versions. For example, status should not mean order status in one place, error code in another, and payment status elsewhere.

## 7. Versioning Destinations, Routes, and Schemas

Versioning enables both sides to coexist during asynchronous deployments. However, versioning needs a clear policy to avoid proliferating near-identical names.

### When Is a New Version Needed?

A new major version is typically needed when:

- Removing or renaming a field that old consumers depend on.
- Changing data types or representation formats incompatibly.
- Changing the business meaning of a field.
- Changing required/nullability rules in a way that invalidates old payloads.
- Changing the interaction model or request semantics.
- Changing authentication or route semantics in a way that breaks existing clients.

You typically do not need a major version bump when merely adding an optional field if both producers and consumers are designed to tolerate it. Still, verify actual serializer/deserializer configuration and your system's schema compatibility policy.

### Choosing One Authoritative Version Source

Versions can live in the route, destination, schema ID, or header metadata. Avoid versioning in multiple places without defining how they relate.

Example:

- Route: orders.submit.v1
- Schema ID: com.acme.orders.SubmitOrderCommand.v1

If both route version and schema version appear, they must align according to the published contract. Avoid sending a v2 schema payload over a v1 route without explicit translation rules.

If routes stay stable and schemas are managed by a schema registry, you can keep routes unversioned and declare the schema ID/version in metadata or headers. This is an architectural decision; Spring Framework does not provide a built-in universal schema registry for all payload types.

### Upgrade Process

1. Publish the new schema and check compatibility with the old schema.
2. Deploy consumers capable of reading both old and new versions if a transition period is needed.
3. Introduce the new route or destination if it is a breaking change.
4. Upgrade producers in waves.
5. Monitor traffic on both old and new names.
6. Retire the old name after zero consumers remain and the support window has ended.

Do not delete old routes or destinations immediately after releasing a new producer. In distributed systems, clients may upgrade at different times.

## 8. Message Headers and Metadata

The payload schema describes business data. Operational and routing details are better suited to message headers or metadata:

- messageId: unique identifier of the message.
- correlationId: links messages within the same business flow.
- causationId: identifies the message that caused the current message.
- schemaId or schemaVersion: identifies the schema used for decoding.
- contentType: describes the payload format.
- occurredAt: business occurrence timestamp, if part of an event.
- trace context: distributed trace propagation information.

Example creating a Spring Message:

~~~java
Message<OrderCreatedEventV1> message = MessageBuilder
    .withPayload(event)
    .setHeader("schemaId", "com.acme.orders.OrderCreatedEvent.v1")
    .setHeader("correlationId", correlationId)
    .build();
~~~

A Spring Message has a payload and headers. Transport adapters may map a subset of headers to STOMP headers, JMS properties, or RSocket metadata. Do not assume every header is preserved intact across every transport; check adapter mappings and limits.

Do not place access tokens, passwords, or sensitive personal data arbitrarily into destinations, routes, or headers. Metadata must also be protected and scrubbed according to logging policies.

## 9. Testing Contracts and Naming Rules

Contract names are only useful if tested and maintained consistently. Maintain contract tests on both producers and consumers.

Checks should cover:

1. **Destination/route existence:** producers send to the published destination or route.
2. **Correct mapping:** STOMP application prefixes route to the right @MessageMapping; RSocket routes map to the right responder.
3. **Correct broker semantics:** queues/topics, subscriptions, durability, retries, and DLQs match broker configuration.
4. **Schema serialization:** payloads serialize and deserialize with the intended codec.
5. **Schema compatibility:** payloads from prior versions still deserialize with new consumers when backward compatibility is promised.
6. **Field semantics:** nulls, missing fields, new enums, timestamps, decimals, and units are handled properly.
7. **Security:** clients cannot subscribe to or call routes merely by guessing names; access rights are enforced on the server.
8. **Deprecation:** metrics confirm zero traffic on legacy destinations or routes before removal.

Store sample payloads for each schema version and run them in CI. If using JSON Schema, Avro, or Protobuf with a schema registry, enable compatibility checks according to your chosen policy. Schema registration and enforcement are the responsibility of the corresponding tooling/schema registry, not provided automatically just by using Spring Messaging.

## 10. Common Naming Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Using the same name for commands and events | Consumers struggle to distinguish intent from occurred facts | Use separate commands and events namespaces |
| Using one destination for unrelated payload types | Consumers have to guess schemas or check types ad hoc | Separate destinations by message type |
| Treating an RSocket route like a URL path | Confusion over separator rules and URL decoding | Follow RSocket route matcher rules |
| Changing casing arbitrarily | Producer and consumer names fail to match | Standardize on lowercase |
| Renaming a Java class changes the wire-level schema | Internal refactoring causes breaking changes | Use stable schema IDs |
| Versioning every minor change | Creates too many routes and schemas to manage | Bump major version only on breaking changes |
| Route and schema versions out of sync | Clients send to the right route with the wrong payload version | Define a single authoritative version source |
| Putting PII or tokens in routes | Data leaks into logs and metrics | Use non-sensitive IDs and secured metadata |
| Assuming /topic is always pub-sub | Actual semantics depend on the broker | Verify broker configuration |
| Deleting old destinations too early | Un-upgraded clients fail | Maintain a deprecation window and monitor traffic |

## 11. Pre-Publication Contract Checklist

- [ ] Destination or route names clearly describe domain and purpose.
- [ ] Commands, queries, and events are clearly distinguished.
- [ ] Lowercase, separator, and namespace conventions are standardized.
- [ ] STOMP destinations, JMS destinations, and RSocket routes are not confused with each other.
- [ ] Queue/topic semantics are verified against broker configuration.
- [ ] Schema IDs are stable and independent of Java class names.
- [ ] Fields have clear types, nullability, units, and meaning.
- [ ] Versions increment only when necessary and have a compatibility policy.
- [ ] Route versions and schema versions do not conflict.
- [ ] Headers/metadata are used appropriately for correlation, schema ID, and tracing.
- [ ] Contract tests and payload fixtures run in CI.
- [ ] A deprecation plan and traffic verification exist before deleting old names.
- [ ] Authentication and authorization checks are enforced on the server.

## 12. References

- [Spring Framework Reference: Enable STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html) — application destination prefixes, broker prefixes, and STOMP configuration.
- [Spring Framework Reference: Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html) — how destinations map to @MessageMapping and the broker.
- [Spring Framework Reference: RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html) — routing metadata, route matchers, RSocketRequester, and annotated responders.
- [Spring Framework Reference: JMS](https://docs.spring.io/spring-framework/reference/integration/jms.html) — JmsTemplate, listeners, and JMS integration.
- [JSON Schema](https://json-schema.org/learn/getting-started-step-by-step) — describing and validating JSON payload structures.
- [Protocol Buffers: Updating a Message Type](https://protobuf.dev/programming-guides/proto3/#updating) — schema evolution and field number rules.
