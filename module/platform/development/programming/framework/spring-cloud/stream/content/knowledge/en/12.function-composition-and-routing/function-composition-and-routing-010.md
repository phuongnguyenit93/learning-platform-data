# Controlling Permitted Destinations and Routing Expressions from External Data

In an event-driven system, a message may need to be routed to different handler functions or destinations depending on the event type, tenant, or business domain. Spring Cloud Stream supports routing through its functional model and dynamic destination sending mechanisms. However, data arriving from requests, files, or external systems must be treated as untrusted data. Using such values directly as function names, SpEL expressions, or destination names can cause the application to invoke unintended capabilities, send messages to unexpected resources, or create excessive broker resources.

Safe routing design separates three decisions: **selecting the handler function**, **selecting the destination**, and **verifying whether the sender is authorized to select that target**. Routing expressions should be configured and controlled by the application; external data only supplies validated business attributes to select within an allowed set of options.

This lesson belongs to the **Function Composition and Routing** chapter of the `SPRING_CLOUD_STREAM` module. It focuses on function routing, destination routing, allowlists, routing expressions, permission checks, handling invalid inputs, and testing on Kafka, RabbitMQ, or Pulsar binders.

## 1. Distinguishing function routing from destination routing

The two types of routing are often mentioned together but answer different questions:

- **Function routing:** selecting which `Function` or `Consumer` bean will process the message.
- **Destination routing:** selecting which topic, exchange, or destination will receive the output message.

For example, a message with `eventType = OrderPlaced` can be dispatched to the `orderHandler` function. After processing, the result can be sent to the `orders.accepted` destination. If the message is `PaymentAuthorized`, the application can select `paymentHandler` and send the result to `payments.confirmed`.

```text
Message from external source
          |
          v
Validate structure and permissions
          |
          v
Select function from allowlist
          |
          v
Function / Consumer
          |
          v
Select permitted destination
          |
          v
Binder -> Kafka / RabbitMQ / Pulsar
```

| Decision | Example value | Common mechanism |
|---|---|---|
| Select function | `orderHandler` | Function routing and `spring.cloud.function.routing-expression` |
| Select destination | `orders.accepted` | Configured output binding, `StreamBridge`, or supported output routing header |
| Authorize selection | `OrderPlaced` can only go to its matching handler | Allowlist, enum, fixed map, and business authorization check |

Do not use destination names in place of function names, nor use function names as an authorization mechanism. The fact that a function exists in the application context does not mean every client is permitted to invoke it.

## 2. Why routing data from external sources must be controlled

Suppose an API receives JSON:

```json
{
  "tenantId": "tenant-a",
  "eventType": "OrderPlaced",
  "target": "orders.tenant-a",
  "orderId": "ORD-42"
}
```

The fields `tenantId`, `eventType`, and `target` all come from an external source. If the application directly calls:

```java
streamBridge.send(request.target(), event);
```

then a client can replace `target` with another destination name. If `eventType` is used directly as a function name, a client could request invoking an unintended bean. If a client is allowed to send an entire SpEL string that gets evaluated, the risk is even greater because data becomes an executable expression.

Key risks:

- **Misrouted streams:** a message containing tenant A's data is sent to tenant B's destination.
- **Unintended privilege escalation:** a client selects a handler with access to sensitive data or operations.
- **Unbounded resource creation:** every arbitrary value creates a new topic, exchange, queue, or binding.
- **Data leakage:** a message is sent to a destination whose recipients are not authorized to view that data.
- **Operational burden:** the number of dynamic bindings, destinations, and metrics grows without bound.
- **Expression risk:** externally supplied routing expressions can access properties or beans beyond the intended scope.

The design principle is to let external data influence only a predefined choice. The application itself must determine which choices are valid and check permissions before sending.

## 3. Function routing with `RoutingFunction`

Spring Cloud Function provides a routing mechanism to select functions per message. In a Spring Cloud Stream application, you can activate the router function via the `functionRouter` definition and configure a routing expression. The expression typically reads the payload or message headers and returns the name of a registered function bean.

Example configuration selecting a handler by `eventType`:

```yaml
spring:
  cloud:
    function:
      definition: functionRouter
      routing-expression: "payload.eventType == 'OrderPlaced' ? 'orderHandler' : payload.eventType == 'PaymentAuthorized' ? 'paymentHandler' : 'unsupportedEventHandler'"
    stream:
      bindings:
        functionRouter-in-0:
          destination: integration.events
          group: event-router
          content-type: application/json
```

The expression above selects only one of three function names hardcoded in configuration. The `eventType` value is input data; it is not evaluated as an expression string. Thus, clients cannot inject SpEL syntax to alter routing logic.

Handlers must be declared as beans with signatures compatible with the messages dispatched by the router:

```java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderPlaced(String orderId, String tenantId) {}

record PaymentAuthorized(String paymentId, String orderId) {}

@Configuration
class EventHandlers {

    @Bean
    Consumer<OrderPlaced> orderHandler() {
        return event -> {
            // Process order-created event.
        };
    }

    @Bean
    Consumer<PaymentAuthorized> paymentHandler() {
        return event -> {
            // Process payment-authorized event.
        };
    }

    @Bean
    Consumer<Object> unsupportedEventHandler() {
        return event -> {
            // Record or quarantine unsupported event type.
        };
    }
}
```

This illustrates handler structure; during implementation, verify how your binder and framework version convert payloads to the selected function's target type. If handlers have different payload types, content types, schemas, and conversion must be tested together with the router. Never assume every payload can deserialize into any Java type.

### Routing expressions must be trusted configuration

`spring.cloud.function.routing-expression` is an application-configured expression. Never take a raw expression string from an HTTP request, message payload, or external header field and pass it to the SpEL evaluator. Let external data provide values like `eventType`, then use a static expression to map those values to a function in the allowlist.

If routing logic is complex, requires per-tenant permission checks, or looks up dynamic configuration from a database, a router written in Java is usually easier to test and control than a long SpEL expression.

## 4. Do not use arbitrary function names from payloads

A dangerous implementation takes a `handler` field from JSON and uses that raw value as a function name. Instead, map approved business values to internal bean names:

```java
import java.util.Map;

final class HandlerRegistry {

    private static final Map<String, String> ALLOWED_HANDLERS = Map.of(
        "ORDER_PLACED", "orderHandler",
        "PAYMENT_AUTHORIZED", "paymentHandler"
    );

    String resolve(String eventType) {
        String handler = ALLOWED_HANDLERS.get(eventType);
        if (handler == null) {
            throw new IllegalArgumentException("Unsupported event type");
        }
        return handler;
    }
}
```

`eventType` is a business code, not an arbitrary bean name. The registry restricts which handlers can be selected. In real applications, the registry can be built from managed configuration and validated at startup; never allow unauthenticated clients to add new handlers dynamically.

If the system must restrict a tenant to emitting only certain event types, check permissions before returning the handler:

```java
String resolveHandler(AuthenticatedTenant tenant, String eventType) {
    if (!tenant.allowedEventTypes().contains(eventType)) {
        throw new AccessDeniedException("Event type is not permitted");
    }
    return handlerRegistry.resolve(eventType);
}
```

Permission checks must rely on authenticated identity and server-side policy. Never trust a `tenantId` inside a payload as proof that the sender belongs to that tenant.

## 5. Destination routing with an allowlist

After selecting a handler, the application may need to send results to different destinations. For stable destinations, the clearest approach is pre-configuring output bindings and selecting one binding in code.

Example:

```yaml
spring:
  cloud:
    stream:
      output-bindings: orderOutput;paymentOutput
      bindings:
        orderOutput:
          destination: orders.accepted
          content-type: application/json
        paymentOutput:
          destination: payments.confirmed
          content-type: application/json
```

The service selects a configured binding:

```java
import java.util.Map;

import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Service;

@Service
class EventPublisher {

    private static final Map<String, String> OUTPUT_BINDINGS = Map.of(
        "ORDER_ACCEPTED", "orderOutput",
        "PAYMENT_CONFIRMED", "paymentOutput"
    );

    private final StreamBridge streamBridge;

    EventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public void publish(String resultType, Object event) {
        String binding = OUTPUT_BINDINGS.get(resultType);
        if (binding == null) {
            throw new IllegalArgumentException("Unsupported result type");
        }
        if (!streamBridge.send(binding, event)) {
            throw new IllegalStateException("Output binding did not accept message");
        }
    }
}
```

Code selects only from declared bindings. Each binding has its own destination and content type. This fits critical flows requiring explicit provisioning, permissions, and producer configuration.

## 6. Dynamic destinations that remain bounded

When destinations are chosen at runtime, `StreamBridge` can create dynamic output bindings. Configuring `spring.cloud.stream.dynamicDestinations` restricts the list of destinations that the dynamic destination mechanism is allowed to use.

```yaml
spring:
  cloud:
    stream:
      dynamic-destinations:
        - tenant-a.events
        - tenant-b.events
        - tenant-c.events
```

Never pass a user-entered target name directly to `send`. Map an authenticated tenant or business domain to a managed destination:

```java
import java.util.Map;

import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Service;

record TenantEvent(String tenantId, String eventType, String body) {}

@Service
class TenantRouter {

    private static final Map<String, String> DESTINATIONS = Map.of(
        "tenant-a", "tenant-a.events",
        "tenant-b", "tenant-b.events",
        "tenant-c", "tenant-c.events"
    );

    private final StreamBridge streamBridge;
    private final TenantAuthorization authorization;

    TenantRouter(StreamBridge streamBridge, TenantAuthorization authorization) {
        this.streamBridge = streamBridge;
        this.authorization = authorization;
    }

    public void publish(
            AuthenticatedTenant caller,
            String requestedTenant,
            TenantEvent event) {

        authorization.requireCanPublishTo(caller, requestedTenant);

        String destination = DESTINATIONS.get(requestedTenant);
        if (destination == null) {
            throw new IllegalArgumentException("Unknown tenant");
        }

        if (!streamBridge.send(destination, event)) {
            throw new IllegalStateException("Could not send tenant event");
        }
    }
}
```

`AuthenticatedTenant` and `TenantAuthorization` represent the application's authentication/authorization components. The example shows the required order: authenticate the caller, check permission for the target tenant, map to the internal destination name, and only then send. `dynamic-destinations` is an additional configuration guardrail; it does not replace business authorization.

If destinations can be enumerated upfront, prefer static output bindings. Dynamic destinations fit when the target count genuinely varies at runtime while still bounded by policy and provisioning processes.

## 7. Output routing via message headers

A function can return `Message<?>` with metadata specifying the output destination. Spring Cloud Stream supports the `spring.cloud.stream.sendto.destination` output routing header in applicable functional streams. This header allows selecting a target while processing a message, yet its value must still be controlled like any other dynamic destination.

Example of a function selecting a destination from an allowed set:

```java
import java.util.Map;
import java.util.function.Function;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;

record IncomingEvent(String eventType, String tenantId, String body) {}

@Component
class EventDestinationRouter
        implements Function<Message<IncomingEvent>, Message<IncomingEvent>> {

    private static final Map<String, String> ALLOWED = Map.of(
        "ORDER_PLACED", "orders.events",
        "PAYMENT_AUTHORIZED", "payments.events"
    );

    @Override
    public Message<IncomingEvent> apply(Message<IncomingEvent> message) {
        String eventType = message.getPayload().eventType();
        String destination = ALLOWED.get(eventType);

        if (destination == null) {
            throw new IllegalArgumentException("Unsupported event type");
        }

        return MessageBuilder.fromMessage(message)
            .setHeader("spring.cloud.stream.sendto.destination", destination)
            .build();
    }
}
```

The routing header is set by trusted code after checking an allowlist. Never copy a header of the same name directly from an external message, because the sender could set the destination value itself. Strip or overwrite routing headers arriving from untrusted sources before the function sets the internal header.

Configuring the input binding and restricting usable output destinations:

```yaml
spring:
  cloud:
    function:
      definition: eventDestinationRouter
    stream:
      dynamic-destinations:
        - orders.events
        - payments.events
      bindings:
        eventDestinationRouter-in-0:
          destination: integration.events
          group: destination-router
          content-type: application/json
```

Output routing headers and dynamic destinations still depend on the capabilities of your Spring Cloud Stream version, binder, and binding configuration. Test with the actual binder, especially when using multiple binders or destinations with specific partition/routing key requirements.

## 8. SpEL expressions: reading data, not executing data

Routing expressions can read payload fields or headers to make decisions. Example:

```yaml
spring:
  cloud:
    function:
      definition: functionRouter
      routing-expression: "payload.eventType == 'OrderPlaced' ? 'orderHandler' : 'unsupportedEventHandler'"
```

The expression is static configuration. The message only supplies the `eventType` value. When a message carries `OrderPlaced`, the router chooses `orderHandler`; other values go to the default handler. This is how external data selects a pre-programmed branch.

Do not configure it like this:

```yaml
# Do not do this: expression injected from an untrusted source.
spring:
  cloud:
    function:
      routing-expression: "#{${request.expression}}"
```

Never accept an expression from a request, header, or payload for dynamic evaluation. SpEL is an expression language capable of accessing properties and objects in context; passing client-controlled content into the evaluator can create unintended execution paths.

If rules change frequently, store a configuration table with a strict schema such as `eventType -> handlerCode` or `tenantId -> destinationCode`. Validate and audit the configuration table before applying it. Do not store arbitrary user-managed SpEL strings unless you have a purpose-built, sandboxed, and audited expression management system.

## 9. Controlling message headers from external sources

Headers are part of a message and can be supplied by external producers. Certain headers carry control meaning, such as function definition, routing expression, content type, or target destination. If an application trusts these headers without verifying provenance, a sender can influence how messages are processed.

When receiving messages from untrusted sources:

1. Explicitly define which headers are allowed across the system boundary.
2. Strip or overwrite internal control headers before passing messages into a router.
3. Set routing headers only after validating the payload and sender permissions.
4. Use a header allowlist and explicit forwarding rules.
5. Never use headers as authentication or authorization proof.

Example sanitizing a message before processing:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<IncomingEvent> sanitized = MessageBuilder
    .withPayload(original.getPayload())
    .setHeader("correlationId", trustedCorrelationId)
    .setHeader("eventType", validatedEventType)
    .build();
```

This example constructs a new message retaining only metadata verified by the application. In production code, also retain transport headers required by the binder and tracing instrumentation, while stripping control headers that external sources are not permitted to set.

## 10. Handling unsupported event types or targets

A router must define clear behavior when data does not match the allowlist. Avoid silently sending to an ambiguous default destination or dropping messages without a trace.

Common options:

| Situation | Handling approach |
|---|---|
| Unsupported `eventType` | Reject, record the reason, and route to a quarantine flow if investigation is needed |
| Nonexistent tenant | Return a business error or quarantine the message per policy |
| Sender lacks permission | Reject before sending; write a safe audit log |
| Destination not in allowlist | Do not create a binding; record metrics and handle the error explicitly |
| Incompatible schema | Route to appropriate error handling/DLQ without guessing a function type |
| Broker unavailable | Apply appropriate producer/outbox retries; do not switch destinations to bypass errors |

Quarantine destinations must also be properly configured and secured. Never send sensitive data to a broadly accessible debug queue. When replaying quarantined messages, retain event IDs and source metadata for reconciliation.

## 11. Multi-layer permission checks

A destination name allowlist does not by itself guarantee that a sender is authorized to send data to that destination. Separate at least three layers:

- **Authentication:** identify who the sender or sending service is.
- **Business authorization:** determine which event types, tenants, or data domains that identity may publish for.
- **Broker permissions:** restrict which topics, exchanges, or namespaces the application's broker account may publish to.

For example, tenant A may only publish events for tenant A. Even if `tenant-b.events` is in the application-wide allowlist, tenant A must still be denied when requesting to send there. Conversely, business code permitting tenant A still cannot publish if the binder account lacks write permissions on the corresponding destination.

Do not grant cluster-wide admin permissions to a router's broker account just because it sends to several destinations. Apply least-privilege permissions per topic, exchange, namespace, or tenant where supported by the broker. If the application uses a shared credential, enforce stricter controls at the application layer and monitor all routing decisions.

## 12. Differences across Kafka, RabbitMQ, and Pulsar

Spring Cloud Stream provides a common abstraction, but physical destinations and routing mechanics differ:

| Broker | Output destination | Aspects to control |
|---|---|---|
| Kafka | Topic and partition | Allowed topics, produce permissions, key/partitioner, partition count, and retention |
| RabbitMQ | Exchange, routing key, and queue binding | Allowed exchanges, routing keys, queue bindings, publish permissions, and unroutable message handling |
| Pulsar | Topic and namespace | Allowed namespaces/topics, produce permissions, partitioned topics, and key ordering |

With Kafka, sending to a topic does not automatically choose a partition per tenant unless the producer sets an appropriate key or partition. With RabbitMQ, an exchange can route messages to multiple queues based on routing keys; choosing an exchange does not imply only one queue receives the message. With Pulsar, topics and subscriptions are distinct concepts; the producer selects the topic, while the subscription determines how consumers receive messages.

When using dynamic destinations, confirm the binder can resolve the right broker and destination. In multi-binder applications, explicitly configure the default binder or specify the binder per binding. Never let external data dictate binder names, broker addresses, or credentials.

## 13. Avoiding routing that breaks ordering or contracts

Routing by tenant or event type can split messages across multiple destinations. This affects ordering and consumer processing:

- If events for the same order must stay ordered, keep the same key/partition or processing stream within broker capabilities.
- If event types have different schemas, destinations should have clear contracts or messages must carry a discriminator and schema version.
- If an event is sent to multiple destinations, make fan-out intentional and handle cases where only one branch succeeds.
- When routing rules change, account for in-flight messages routed under old rules alongside new messages under new rules.

Do not change destinations merely because a consumer is failing or slow. That can create two divergent state streams and break reconciliation. Consumer failures should be handled via retries, DLQ, and observability on the corresponding stream.

## 14. Testing expressions and allowlists

Router tests must verify both permitted cases and rejected cases:

| Scenario | Input | Result to verify |
|---|---|---|
| Valid event type | `OrderPlaced` | Selects `orderHandler` |
| Another valid event type | `PaymentAuthorized` | Selects `paymentHandler` |
| Unknown event type | `UnknownEvent` | Enters quarantine handler or is rejected per policy |
| Authorized tenant | Tenant A sends to destination A | Message is sent to destination A |
| Unauthorized tenant | Tenant A requests destination B | Rejected before calling `StreamBridge.send` |
| Destination outside allowlist | `admin.commands` | No binding created or published to that target |
| Spoofed control header | Message sets target/function header itself | Header is stripped or overwritten with trusted value |
| Expression injection | Payload contains SpEL syntax string | String is treated purely as data and never evaluated |
| Broker error | Valid destination but broker rejects publish | Error is observed and handled per send policy |
| Multiple concurrent tenants | Messages from multiple tenants | No data leakage or cross-tenant destination mix-ups |

Unit tests should verify the `eventType -> handler` and `tenant -> destination` mappings independently. Integration tests should confirm the function router, message conversion, header mapping, and binder work together properly. The Test Binder is useful for checking Spring flows, but does not replace testing broker permissions, RabbitMQ exchange routing, Kafka partitioning, or Pulsar namespaces in a compatible environment.

## 15. Observing routing in production

A router needs logs and metrics that answer:

- Which event type was the message classified as?
- Which handler was selected and under which rule version?
- Which destination was chosen after checking the allowlist?
- How many routing attempts were rejected due to invalid tenant, event type, or destination?
- How many send failures occurred per binder and destination?
- Is any destination experiencing unusual growth in binding count or backlog?

Log `eventId`, `correlationId`, normalized event type, rule version, and permitted destination. Do not log tokens, credentials, or full sensitive payloads. Metric labels must have bounded cardinality; avoid using arbitrary tenant IDs, UUIDs, or client-supplied destination names as labels.

When updating allowlists or routing rules, version the configuration and keep an audit trail of who changed it, when, and why. This helps explain why the same event type may be routed differently at two different points in time.

## 16. Safe implementation workflow

When designing routing from external data, follow this sequence:

1. Clarify whether you are selecting a function, a destination, or both.
2. Define event types and routing fields in the schema; never use expression strings as business data.
3. Authenticate the sender and check tenant/domain permissions.
4. Normalize input data and reject missing or invalid values.
5. Map event type to a function in the allowlist using a static expression or Java router.
6. Map tenant or processing result to an allowed binding/destination.
7. If using dynamic destinations, restrict with `dynamicDestinations` and controlled provisioning.
8. Strip or overwrite control headers coming from untrusted sources.
9. Enforce least-privilege publish permissions on the broker.
10. Test valid cases, unauthorized attempts, expression injection, broker errors, and concurrent multi-tenant traffic.
11. Monitor rule versions, dynamic binding counts, routing errors, and backlogs.
12. Roll out routing rule changes via a controlled process with rollback capability.

## 17. Self-check

- [ ] Can distinguish function routing from destination routing.
- [ ] Can explain the role of `functionRouter` and `spring.cloud.function.routing-expression`.
- [ ] Know why routing expressions must be trusted configuration rather than taken raw from external payloads.
- [ ] Map event types to functions in an allowlist.
- [ ] Map tenants or business domains to permitted destinations.
- [ ] Know when to use pre-configured output bindings for stable destinations and dynamic destinations when genuinely needed.
- [ ] Understand that `dynamicDestinations` only restricts dynamic targets and does not replace authorization.
- [ ] Recognize and handle spoofed control headers.
- [ ] Verify broker permissions, message ordering, and schemas when routing.
- [ ] Design tests for unknown event types, unauthorized tenants, and invalid destinations.

## Conclusion

Safe routing separates selecting a handler function from selecting an output destination. Spring Cloud Function can use `functionRouter` and `spring.cloud.function.routing-expression` to pick functions; Spring Cloud Stream can send to static bindings or dynamic destinations. External data should supply only validated business codes to select from an application-managed allowlist. Never evaluate client-supplied expressions, never trust unverified control headers, and never use destination names as an authorization mechanism. Combining allowlists, authorization, least-privilege broker permissions, testing, and observability keeps routing flows scalable and under control.
