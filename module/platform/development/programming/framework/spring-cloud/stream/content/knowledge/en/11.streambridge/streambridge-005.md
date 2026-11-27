# Distinguishing Pre-declared Bindings from Dynamic Destinations

In Spring Cloud Stream, applications commonly send messages through an output binding declared in configuration. However, there are times when the target destination is only known at runtime—for example, sending notifications to a tenant's stream, a customer group, or a business domain chosen from input data. `StreamBridge` supports both approaches: sending via a pre-configured binding and sending to a destination whose binding is created on demand.

These two approaches are related but not identical. With a pre-declared binding, the application knows the binding name and the configuration maps it to a destination, binder, and producer properties. With a dynamic destination, the application supplies the target name when calling `StreamBridge`; Spring Cloud Stream can create an output binding when the first send occurs. Whether topics, exchanges, or corresponding resources can be created still depends on the binder, broker, permissions, and provisioning policies.

This lesson belongs to the **StreamBridge** chapter of the `SPRING_CLOUD_STREAM` module, focusing on how to choose between static configuration and dynamic targets, naming, resource control, error handling, and testing.

## 1. What need does StreamBridge address?

The `Supplier`/`Function`/`Consumer` functional model fits when message flows tie directly to a function. Yet a Spring application may also need to send messages from an imperative component, such as a REST controller, business service, listener from another system, or synchronous workflow. `StreamBridge` provides an API to send a payload or Spring `Message<?>` to an output binding without writing a function solely to forward messages.

For example, after a user updates a shipping address, a service publishes an `AddressChanged` event:

```text
REST request
    |
    v
AddressService
    |
    | StreamBridge.send(...)
    v
Output binding
    |
    v
Binder
    |
    v
Kafka / RabbitMQ / Pulsar
```

`StreamBridge` does not replace the binder. It sends the message into a binding; the binder remains responsible for connecting to the broker and delivering the message according to that binding's configuration.

## 2. Distinguishing binding name and destination

This is the foundation for understanding pre-declared bindings and dynamic destinations:

| Concept | Meaning | Example |
|---|---|---|
| Binding name | Logical connection point name in Spring Cloud Stream configuration | `auditOutput` |
| Destination | Target name that the binder maps to a broker resource | `audit.events` |
| Binder | Component integrating with a type of broker | Kafka binder, Rabbit binder, Pulsar binder |
| Physical resource | Actual broker object receiving or storing messages | Kafka topic, RabbitMQ exchange/queue, Pulsar topic |

With a pre-declared binding, the binding name can differ from the destination name. For example, `auditOutput` maps to destination `audit.events`. When calling `StreamBridge.send`, the application uses the binding name `auditOutput`.

With a dynamic destination, the name passed to `StreamBridge` is typically both the binding name created at runtime and the destination name used by the binder. For example, calling `send("tenant-42.events", event)` requests sending to target `tenant-42.events`; there is no need to pre-declare a function binding for every tenant.

Do not mix the two types of names. If you already declared a binding `auditOutput` pointing to `audit.events`, calling `send("audit.events", event)` is a different request from `send("auditOutput", event)`; the passed name is interpreted as a binding/destination name according to StreamBridge's resolution mechanism.

## 3. Pre-declared output bindings

A pre-declared binding is one explicitly declared in application configuration. When an application needs to create an output binding not tied to a `Function` output, it can list the binding name in `spring.cloud.stream.output-bindings`.

Example declaring a binding named `auditOutput` and mapping it to destination `audit.events`:

```yaml
spring:
  cloud:
    stream:
      output-bindings: auditOutput
      bindings:
        auditOutput:
          destination: audit.events
          content-type: application/json
```

`output-bindings` tells the framework to create an output binding named `auditOutput`. The `bindings.auditOutput` section describes the destination and content type. The binding name does not have to match the topic or exchange name.

A service can publish events through that binding:

```java
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Service;

record AuditEvent(String actorId, String action, String resourceId) {}

@Service
class AuditPublisher {

    private final StreamBridge streamBridge;

    AuditPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public void publish(AuditEvent event) {
        boolean accepted = streamBridge.send("auditOutput", event);
        if (!accepted) {
            throw new IllegalStateException("Could not send audit event");
        }
    }
}
```

In this example, Java code only knows the binding name `auditOutput`. The actual destination, content type, and producer configuration are managed in Spring Cloud Stream configuration. When changing destinations per environment, configuration can be changed without modifying the call in the service.

### When should you pre-declare?

Pre-declared bindings fit when:

- Destinations are known in advance and their count is stable.
- Each stream needs specific content type, partitioning, retry, header mapping, or producer properties.
- Infrastructure must be provisioned and reviewed before deploying the application.
- You want clear control over access permissions, resource names, and per-environment configuration.
- Multiple components in the application need to send to the same standardized stream.

For core domain events such as `orders.created`, `payments.authorized`, or `inventory.reserved`, pre-declared bindings usually make contracts and topology easier to manage.

## 4. Dynamic destinations

Dynamic destinations are determined while the program is running. When `StreamBridge` receives an undeclared binding name, the framework can create an output binding on demand and use that name as the default destination.

Example of an application sending events to a per-tenant destination:

```java
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Service;

record TenantEvent(String tenantId, String eventType, String data) {}

@Service
class TenantEventPublisher {

    private final StreamBridge streamBridge;

    TenantEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(String destination, TenantEvent event) {
        return streamBridge.send(destination, event);
    }
}
```

If calling `publish("tenant-42.events", event)`, the application asks StreamBridge to send the message to destination `tenant-42.events`. The binding can be created on the first send. Subsequent sends can use the binding already created and managed at runtime.

```text
First send
StreamBridge.send("tenant-42.events", event)
             |
             v
      Resolve binding name
             |
             v
      No binding yet?
             |
             v
      Create dynamic output binding
             |
             v
      Binder connects destination
             |
             v
      Send message

Subsequent sends
             |
             v
      Use resolved binding
```

Dynamic destinations are useful when the number of targets cannot be fully enumerated at deployment time or when an application must route based on runtime data. However, automatic resource creation depends on the binder and broker. For instance, Kafka may require topics to exist beforehand if auto topic creation is disabled; RabbitMQ may require exchanges or topology to be provisioned; Pulsar may require appropriate namespaces and topic creation permissions.

## 5. Restricting dynamic destinations with an allowlist

If a destination name is taken directly from a request or user input, do not pass that string straight into `StreamBridge.send`. An arbitrary value can cause the application to create or access unintended resources, inflating destination counts, complicating access control, and increasing operational costs.

Spring Cloud Stream provides the `spring.cloud.stream.dynamicDestinations` property to restrict destinations allowed for dynamic creation. Example:

```yaml
spring:
  cloud:
    stream:
      dynamic-destinations:
        - tenant-a.events
        - tenant-b.events
        - tenant-c.events
```

When an allowlist is configured, only permitted destinations can be resolved via the framework's dynamic destination mechanism. Verify the exact behavior and syntax with the Spring Cloud Stream version in use, especially if the application combines multiple binders or has custom authorization rules.

At the business layer, map a validated identifier to an application-managed destination:

```java
import java.util.Map;

import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Service;

@Service
class TenantEventRouter {

    private static final Map<String, String> DESTINATIONS = Map.of(
        "tenant-a", "tenant-a.events",
        "tenant-b", "tenant-b.events",
        "tenant-c", "tenant-c.events"
    );

    private final StreamBridge streamBridge;

    TenantEventRouter(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public void publish(String tenantId, TenantEvent event) {
        String destination = DESTINATIONS.get(tenantId);
        if (destination == null) {
            throw new IllegalArgumentException("Unknown tenant");
        }

        if (!streamBridge.send(destination, event)) {
            throw new IllegalStateException("Message was not accepted");
        }
    }
}
```

The allowlist in configuration and the tenant check in business logic protect two different boundaries: configuration limits which targets the framework is allowed to resolve; business code determines which targets the caller is authorized to send to.

## 6. Comparing the two approaches

| Criterion | Pre-declared binding | Dynamic destination |
|---|---|---|
| Target resolution time | When configuring the application | When the application runs |
| Name passed to `send` | Declared binding name | Dynamic destination/binding name |
| Name mapping | Binding name can differ from destination | Usually uses the dynamic name as default destination |
| Producer properties | Can be explicitly configured per binding | Usually relies on defaults or pre-configured properties for the corresponding binding |
| Provisioning | Easy to manage before deployment | May occur at runtime, depending on binder and broker permissions |
| Number of targets | Typically finite, stable | Can vary according to runtime data |
| Access control | Easy to attach permissions per fixed destination | Requires allowlist and business-layer authentication/authorization |
| Operations | Easy to monitor metrics, configuration, and topology | Must manage lifecycle, cardinality, and cleanup of many targets |
| Suitable cases | Core business flows, stable destinations | Routing to a target set selected at runtime |

Neither approach is better in every situation. Choose based on topology stability, operational requirements, and authorization model.

## 7. Content type and message headers

`StreamBridge.send` can send a Java object as payload or a Spring `Message<?>` when header control is needed. With a pre-declared binding, content type can be declared in configuration:

```yaml
spring:
  cloud:
    stream:
      output-bindings: orderEvents
      bindings:
        orderEvents:
          destination: orders.events
          content-type: application/json
```

Sending a simple payload:

```java
streamBridge.send("orderEvents", orderEvent);
```

Sending a message with metadata:

```java
import java.time.Instant;
import java.util.UUID;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

record OrderEvent(String orderId, Instant occurredAt) {}

String correlationId = UUID.randomUUID().toString();
OrderEvent orderEvent = new OrderEvent("ORD-42", Instant.now());

Message<OrderEvent> message = MessageBuilder
    .withPayload(orderEvent)
    .setHeader("eventId", UUID.randomUUID().toString())
    .setHeader("eventType", "OrderPlaced")
    .setHeader("correlationId", correlationId)
    .build();

streamBridge.send("orderEvents", message);
```

The payload carries business data; headers carry metadata such as event ID, correlation ID, or tracing info. The binder can map headers to broker-specific metadata, though not every header is supported or preserved across all binders. Test critical headers with the real broker.

With dynamic destinations, if each target has a different payload contract, ensure content type and message type are clearly defined. Do not send unrelated schemas to the same destination without a discriminator or versioning rules.

## 8. What does the return value of `send` mean?

`StreamBridge.send(...)` returns a boolean indicating whether the message was sent/accepted through the output channel per StreamBridge's mechanism. A `true` value does not mean downstream consumers have processed the business logic successfully, nor does it prove by itself that the message was durably acknowledged by all replicas or target systems.

Distinguish the milestones:

1. Application calls `send` and the message is accepted by the output channel.
2. Binder/producer sends the message to the broker.
3. Broker acknowledges according to the configured guarantee level.
4. Consumer receives the message.
5. Consumer commits the business result.

Each milestone has its own failure modes and guarantees. If business rules require confirmation that the broker wrote the message, configure and use the appropriate binder/producer acknowledgment mechanism. If you need to know the consumer finished, a business reply or separately persisted state is required.

Do not treat a boolean `true` as a distributed transaction spanning the application's database and the broker. If a service updates the database and then sends an event, consider transactional outbox to avoid states where the database commits but the message is not published, or the message is published while the send status is not saved.

## 9. Dynamic destinations and multiple binders

An application can use multiple binders, such as Kafka for event streams and RabbitMQ for task queues. A pre-declared binding can specify a concrete binder in binding configuration. With dynamic destinations, there must be a strategy for determining which binder handles the target; do not assume a destination name alone is enough to pick the right broker in every multi-binder setup.

When multiple brokers are needed, consider:

- Declaring pre-configured bindings for flows with fixed broker requirements.
- Using clear default binder settings or framework-supported mapping configuration for dynamic targets.
- Never letting request data decide the binder name or broker endpoint.
- Testing each sending path on the right binder, because destination types and metadata map differently.

If an application has multiple binders and dynamic destinations can belong to multiple brokers, define explicit routing rules in the application layer or create dedicated publishers with clear configuration. Avoid letting an arbitrary input string decide where data goes.

## 10. Provisioning and destination lifecycle

Pre-declared bindings allow infrastructure to create resources before the application starts. With dynamic destinations, a binding can be created on the first send, but that does not mean every broker will always auto-create resources successfully.

| Broker | Output destination | Things to verify when using dynamic targets |
|---|---|---|
| Kafka | Topic | Whether topic auto-create is enabled; producer account has write permissions; partitions and retention follow policy |
| RabbitMQ | Exchange, then routed via queue bindings | Whether exchange is created; routing key and queue bindings already exist; how unrouted messages are handled |
| Pulsar | Topic | Whether namespace exists; produce permissions and auto topic creation policy allow it |

In production, critical resources should generally be provisioned through controlled infrastructure processes. With dynamic destinations, define who is responsible for creating, monitoring, changing retention, and cleaning up unused resources.

If each tenant creates a separate topic, growing tenant counts can lead to thousands of topics, exchanges, or queues. This increases metadata, monitoring, access-control, backup, and operational overhead. A shared topic with `tenantId` in payload/header and an appropriate key may be simpler if data isolation requirements allow. Base the decision on security, retention, load, and per-tenant access requirements.

## 11. Common errors

| Symptom | Possible cause | What to check |
|---|---|---|
| `send` fails to send | Binding cannot be resolved, channel creation error, or invalid binder configuration | Check binding name, StreamBridge logs, and binder |
| Sent to wrong destination | Used destination instead of configured binding name | Check `bindings.<name>.destination` mapping |
| Dynamic destination rejected | Target is not in `dynamicDestinations` allowlist | Check normalized name and allowlist |
| Binding created but broker lacks resource | Broker disabled auto-provisioning or lacks permissions | Check topic/exchange/namespace, permissions, and provisioning |
| RabbitMQ has no queue receiving messages | Exchange exists but has no matching queue/routing binding | Check exchange type, routing key, and queue bindings |
| Consumer receives wrong payload type | Inconsistent content type or schema | Check content type, converter, and actual payload |
| Abnormal growth in destination count | Target name taken from uncontrolled data or excessive cardinality | Add allowlist, normalize names, and monitor binding count |
| `send` returns true but consumer does not process | Only the channel send step was confirmed; consumer may be failing, not subscribed, or lagging | Check broker, group/subscription, retries, and DLQ |

When debugging, trace the flow in order: name passed to `StreamBridge.send`, resolved binding, actual destination, selected binder, broker resource, and consumer. Checking only producer logs is not enough to prove a message reached the consumer.

## 12. Testing pre-declared bindings and dynamic destinations

The two approaches require different test scenarios:

| Scenario | Pre-declared binding | Dynamic destination |
|---|---|---|
| Valid name | Call with configured binding name | Call with permitted destination name |
| Destination mapping | Verify binding points to right physical destination | Verify dynamic name is used properly as destination |
| Content type | Check binding configuration | Check default configuration or message metadata |
| Resources | Verify provisioning before or at startup per config | Verify binding/resource creation behavior on first send |
| Invalid name | Check non-existent binding name | Verify destinations outside allowlist are rejected |
| Broker errors | Verify publish errors are observed | Verify resolve/provision/publish errors are distinguished |

Test examples should verify both the boolean return value and the content sent to the output destination. With Spring Cloud Stream Test Binder, you can verify messages are routed to the corresponding test destination without a real broker. However, the test binder does not prove permissions to create topics, exchanges, or subscriptions, nor does it fully validate broker semantics.

For integration tests, run at least one scenario on the exact broker type used in deployment. Verify payload, headers, content type, routing, and consumer message reception. For dynamic destinations, also test the allowlist, number of created bindings, and behavior when a destination does not exist.

## 13. Observability and security

When using dynamic destinations, metrics tracking only total message counts may be insufficient. Observe:

- Number of active dynamic bindings and rate of new binding creation.
- Send success/failure counts by binder and normalized destination.
- Number of destinations rejected because they are not in the allowlist.
- Provisioning errors, authentication errors, publish errors, and consumer backlog.
- Broker resource counts, storage usage, and retention by business domain.

Do not use arbitrary tenant IDs or destinations as metric labels if cardinality is unbounded. Logs can record validated destinations, correlation ID, and event ID, but must not log sensitive data in payloads.

Grant publish permissions only to destinations the application genuinely needs. If the binder uses an account with broad write permissions, the application-level allowlist becomes even more critical. In multi-tenant systems, verify tenant access rights before selecting a destination; do not rely on destination naming as the sole authorization mechanism.

## 14. Selection and implementation workflow

When designing a sending path with `StreamBridge`:

1. Determine whether destinations are known before deployment or only when processing requests.
2. If destinations are stable, declare output bindings and map binding names to destinations.
3. If destinations are dynamic, define naming rules, an allowlist, and business-layer authorization checks.
4. Configure binder, content type, producer properties, and provisioning according to the broker.
5. Send using binding names for pre-declared bindings; use controlled dynamic target names for dynamic destinations.
6. Distinguish `send` results from broker acknowledgments and consumer processing outcomes.
7. Design retries, outbox, or acknowledgment mechanisms suited to delivery requirements.
8. Test correct destinations, payloads, headers, broker errors, and invalid names.
9. Monitor binding counts, resource counts, publish errors, and backlog.
10. Establish a process to clean up dynamic destinations and revoke permissions when tenants or flows become inactive.

## 15. Self-check

- [ ] Can distinguish binding name, destination, binder, and physical resource.
- [ ] Can explain how to declare pre-configured output bindings with `output-bindings`.
- [ ] Know why calling `StreamBridge.send` with a configured binding name differs from a dynamic destination name.
- [ ] Can describe how dynamic destinations are resolved and bound on the first send.
- [ ] Know how to restrict dynamic destinations with an allowlist and tenant authorization checks.
- [ ] Understand that resource provisioning depends on the broker, binder, and granted permissions.
- [ ] Distinguish the return value of `send` from broker acknowledgment and business processing completion.
- [ ] Can choose when to use pre-declared bindings and when dynamic destinations fit.
- [ ] Can design tests, metrics, and lifecycles for dynamic destinations.

## Conclusion

Pre-declared bindings define binding names, destinations, and producer properties in advance; `StreamBridge.send` is called using that binding name. Dynamic destinations let the application select targets at runtime and allow the framework to create an output binding on the first send. The dynamic approach is useful when topology changes with runtime data, but requires an allowlist, permission checks, resource count limits, and clear provisioning processes. Regardless of which approach is used, distinguish a message being accepted at the output channel from broker acknowledgment and consumer business completion.
