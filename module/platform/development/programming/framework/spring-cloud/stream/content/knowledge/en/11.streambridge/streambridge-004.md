# Pre-creating Output Bindings and Creating Bindings on First Send

## Objectives

Spring Cloud Stream typically connects functions to a broker through bindings inferred from `Supplier`, `Function`, or `Consumer` signatures. In some cases, an application needs to publish messages from an imperative component such as a service, controller, scheduler, or outbox relay. `StreamBridge` provides a way to send messages to an output binding without turning that component into a function bean.

With `StreamBridge`, an output binding can be **pre-created when the application starts** or **created dynamically when the first send occurs**. Both approaches are useful, but they differ in initialization timing, configurability, destination control, and error handling.

After this lesson, you can:

- Distinguish a binding name from a destination name.
- Use `spring.cloud.stream.output-bindings` to pre-create output bindings before sending.
- Send to a pre-created binding using `StreamBridge.send`.
- Create bindings dynamically on the first send to an unbound name.
- Restrict dynamic destinations and configure appropriate binder/content type settings.
- Choose a binding creation approach based on topology and operational requirements.
- Test binding creation, message sending, and provisioning with the target binder.

## 1. What is StreamBridge used for?

`StreamBridge` is an imperative API for sending data to a Spring Cloud Stream output binding. It is useful when the publishing source is not a function output, such as:

- A REST controller receiving a request and publishing an event.
- An application service publishing a notification after completing an operation.
- A scheduler generating periodic messages.
- An outbox relay reading events stored in a database and sending them to the broker.
- An adapter that needs to select an output binding based on event type or allowed destinations.

Example of a service sending notifications:

```java
@Service
public class NotificationPublisher {

    private final StreamBridge streamBridge;

    public NotificationPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(OrderNotification notification) {
        return streamBridge.send("notifications-out-0", notification);
    }
}
```

The name passed to `send` is the **binding name** that StreamBridge uses to look up or create an output binding. The binding name maps to the **destination** where the binder will send the message.

These two concepts can be identical, but they do not have to be:

| Concept | Meaning | Example |
|---|---|---|
| Binding name | Identifier of the output binding in Spring Cloud Stream configuration and when calling StreamBridge | `notifications-out-0` |
| Destination | Target on the broker that the binding connects to | Kafka topic `notifications`, configured Rabbit exchange/queue, or Pulsar topic |
| Binder | Component connecting a binding to a specific broker | Kafka binder, Rabbit binder, Pulsar binder |

In the example above, `notifications-out-0` is the binding name; the actual destination will be configured. Do not assume that renaming a binding changes the topic or queue name.

## 2. Pre-creating output bindings on application startup

When the output bindings an application needs are known in advance, they can be declared in `spring.cloud.stream.output-bindings`. Spring Cloud Stream creates those output bindings during startup.

Example:

```yaml
spring:
  cloud:
    stream:
      output-bindings: notifications-out-0;audit-events-out-0
      bindings:
        notifications-out-0:
          destination: app.notifications
          content-type: application/json
        audit-events-out-0:
          destination: app.audit-events
          content-type: application/json
```

The `output-bindings` list uses semicolons to separate binding names. Each binding can have its own settings under `spring.cloud.stream.bindings.<bindingName>`, such as destination, content type, binder, and producer properties.

Once the binding is created, code sends messages using the exact binding name:

```java
@Service
public class EventPublisher {

    private final StreamBridge streamBridge;

    public EventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publishNotification(Notification event) {
        return streamBridge.send("notifications-out-0", event);
    }

    public boolean publishAudit(AuditEvent event) {
        return streamBridge.send("audit-events-out-0", event);
    }
}
```

### When should you pre-create?

Pre-creating bindings fits when:

- The set of destinations is relatively stable and known before deployment.
- Each output needs explicit content type, partitioning, or producer behavior settings.
- A specific binder must be selected in a multi-binder application.
- You want configuration or provisioning errors to surface at startup rather than on the first request.
- You want to observe the output topology as soon as the application starts.

Pre-creation does not mean the broker destination necessarily already exists. The binder may auto-provision the destination if supported and granted the appropriate permissions; if auto-creation is disabled, the destination must be created beforehand through infrastructure processes. Permission to create topics, exchanges, queues, or Pulsar topics still depends on the broker and binder configuration.

## 3. Creating bindings dynamically on first send

If `StreamBridge.send` receives a binding name that has not been declared or does not exist yet, Spring Cloud Stream can dynamically create an output binding when the first send to that name occurs.

Example:

```java
@Service
public class AlertPublisher {

    private final StreamBridge streamBridge;

    public AlertPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(Alert alert) {
        return streamBridge.send("inventory-alerts", alert);
    }
}
```

If no binding named `inventory-alerts` exists yet, StreamBridge asks the framework to create a dynamic output binding. Without separate mapping configuration, the name is used as the default destination. The corresponding binder performs connection and provisioning according to its configuration, permissions, and capabilities.

A dynamic binding can be configured by its known name in configuration:

```yaml
spring:
  cloud:
    stream:
      bindings:
        inventory-alerts:
          destination: inventory.alerts
          content-type: application/json
```

Then code still calls:

```java
streamBridge.send("inventory-alerts", alert);
```

Here, `inventory-alerts` is the binding name; `inventory.alerts` is the destination. Pre-declaring properties under the binding name allows defining the destination and content type even when the binding is only created on first send.

### Restricting dynamic destinations

You can restrict the destinations allowed for dynamic creation using `spring.cloud.stream.dynamic-destinations` if the application needs an allowlist:

```yaml
spring:
  cloud:
    stream:
      dynamic-destinations:
        - inventory-alerts
        - audit-events
```

This list must match the dynamic destination/binding names the application is allowed to use according to the Spring Cloud Stream version being run. Verify the allowlist behavior of your specific version in integration tests. If the application does not need to send to a changing set of targets, pre-creating output bindings is usually easier to control.

Never take a destination name directly from an HTTP parameter or user input and pass it into `StreamBridge.send`. Doing so can let a request cause the application to attempt creating unintended destinations, introducing operational risk, resource costs, or cross-access issues. Map event types to an already allowed list of bindings/destinations.

## 4. Configuring content type and outbound messages

Whether a binding is pre-created or created dynamically, messages still must be converted to the format consumers expect. Content type can be configured on the binding:

```yaml
spring:
  cloud:
    stream:
      output-bindings: notifications-out-0
      bindings:
        notifications-out-0:
          destination: app.notifications
          content-type: application/json
```

The publisher can send a POJO:

```java
public record OrderNotification(
        String eventId,
        String orderId,
        String message
) {}

boolean accepted = streamBridge.send(
        "notifications-out-0",
        new OrderNotification(
                "evt-100",
                "order-42",
                "Order has been confirmed"
        )
);
```

Spring Cloud Stream uses the content type and corresponding conversion mechanism to transform the payload. If sending a `Message<?>`, application headers can be attached using `MessageBuilder`:

```java
Message<OrderNotification> message = MessageBuilder
        .withPayload(notification)
        .setHeader("eventId", notification.eventId())
        .setHeader("eventType", "order.notification")
        .build();

boolean accepted = streamBridge.send("notifications-out-0", message);
```

Add only meaningful application headers expected by consumers. Do not manually fabricate broker-managed metadata such as offset, assigned partition, or delivery tag. Details regarding native serialization and header mapping also depend on the binder; content type does not replace broker-specific serializers when a binding is configured for native encoding.

## 5. Selecting a binder and producer properties

In a multi-binder application, an output binding must connect to the right binder. For pre-created bindings, the binder can be declared explicitly:

```yaml
spring:
  cloud:
    stream:
      output-bindings: notifications-out-0
      bindings:
        notifications-out-0:
          destination: app.notifications
          binder: kafka
          content-type: application/json
```

The name `kafka` must match a binder registered in the application. If no binder is declared for the binding, the framework uses the default binder or selects appropriately based on multi-binder configuration.

Common producer properties and binder-specific properties should be placed in their proper namespaces. For example, Kafka producer properties should not be placed in general configuration expecting RabbitMQ or Pulsar to apply the same meaning. When using dynamic bindings, if specific binder, partition, native encoding, or producer properties are needed, declare properties under the binding name before the first send and verify they are actually applied.

For a known set of outputs, pre-creating bindings makes reviewing binder setup and configuration clearer. Dynamic binding fits when the target set genuinely needs flexibility, but should not be used to avoid designing topology or managing producer configuration.

## 6. Comparing the two binding creation approaches

| Criterion | Pre-create with `output-bindings` | Dynamic creation on first send |
|---|---|---|
| Creation time | On application startup | When StreamBridge first sends to a non-existent binding |
| Binding list | Known in advance and declared in config | Can vary per runtime needs within allowed limits |
| Configuration | Easy to declare completely before startup | Should declare properties under binding name if customization is needed |
| Error detection | Many connection/provisioning errors surface at startup | Errors may surface on the first request or send task |
| Topology | Stable, easy to observe | Flexible, but target list needs management |
| Use case | Notifications, audit, domain events with fixed destinations | Controlled dynamic destinations, e.g., target groups from runtime config |
| Main risk | Startup depends on creating/connecting declared outputs | Unintended target creation, missing config, and latency on first send |

### Choosing by scenario

- If the application always publishes to `app.notifications` and `app.audit-events`, pre-create the two output bindings.
- If an adapter needs to send to one of several destinations chosen from runtime configuration, dynamic binding with an allowlist can be used.
- If each tenant has its own topic, carefully weigh destination counts and provisioning lifecycles. Often, a partition key or tenant ID in the payload/header satisfies isolation needs without creating unbounded topics.
- If binder-specific producer configuration or an SLA-critical topology is required, prefer declaring bindings and explicit configuration.

## 7. Handling send results and provisioning errors

`StreamBridge.send` returns a boolean indicating whether sending through the output binding/channel was accepted according to the framework's send mechanism. A `true` value **does not prove** that the broker durably stored the message, that the consumer received it, or that downstream consumer business logic completed.

Publishers need to handle both returning `false` and exceptions caused by binding creation, payload conversion, or sending failures. Do not ignore the result:

```java
public void publish(OrderNotification event) {
    boolean accepted = streamBridge.send("notifications-out-0", event);

    if (!accepted) {
        throw new IllegalStateException(
                "Spring Cloud Stream did not accept the notification"
        );
    }
}
```

If this message originates from a business transaction, do not simply send via StreamBridge and assume the database and broker committed atomically. You can use a transactional outbox: write business state and an outbox record in the same database transaction, then have a relay send the message. The relay must persist send state and tolerate resends; consumers should be idempotent by event ID.

Errors to monitor:

- Incorrect binding name or not configured as expected.
- Binder missing from the classpath or cannot be selected.
- Broker unavailable or credentials lack publish/provision permissions.
- Destination does not exist while auto-provisioning is disabled.
- Payload cannot be converted or serializer is incompatible.
- Dynamic destination rejected by allowlist.
- Producer/binder rejects sending or an asynchronous error occurs after the send call returns.

Logs should include event ID, binding name, and error type. Avoid logging full payloads or headers if sensitive data is present. Monitor publish failures and outbox status to detect stuck messages.

## 8. Testing pre-created output bindings

Testing pre-created bindings should verify that bindings are initialized and StreamBridge sends messages to the right output. With the Spring Cloud Stream Test Binder, you can test at the framework level without needing a real broker.

Example test configuration:

```yaml
spring:
  cloud:
    stream:
      output-bindings: notifications-out-0
      bindings:
        notifications-out-0:
          destination: app.notifications
          content-type: application/json
```

Tests should verify:

1. Application context starts with the declared output binding.
2. Calling the publisher uses the right binding name.
3. Message appears at the target destination/binding in the Test Binder.
4. Payload is converted properly and required custom headers are present.
5. Binding uses the right binder when the application has multiple binders.

The Test Binder verifies framework behavior; it does not prove a real broker has provisioned a topic or exchange. With Kafka, RabbitMQ, or Pulsar, integration tests are required when verifying publish permissions, provisioning, native serialization, and broker-specific producer behavior.

## 9. Testing dynamic bindings

For dynamic bindings, verify binding creation behavior on the first send and destination policy:

- Perform a first send to an unbound name and verify the framework creates the output binding.
- Perform subsequent sends to the same name and verify the binding is reused per framework lifecycle.
- If an allowlist exists, test that valid destinations are accepted and unlisted destinations are rejected.
- Verify content type, destination mapping, binder, and producer properties declared under the binding name.
- Test error handling when the broker disallows provisioning or publishing.
- Verify the system does not create arbitrary destinations from untrusted input.

For example, unit-testing publisher logic can use the Test Binder or mocks to verify the selected binding name. However, dynamic provisioning behavior must be tested with an application context and real binder; mocking `StreamBridge.send` does not prove the framework created the binding.

## 10. Selection and implementation workflow

When sending messages from imperative code is needed:

1. List the destinations the application needs to send to.
2. If the target set is stable, declare names in `spring.cloud.stream.output-bindings`.
3. If dynamic binding is needed, define name mapping rules, an allowlist, and target count limits.
4. Distinguish binding name from destination; declare `bindings.<bindingName>.destination` when the two names differ.
5. Declare content type, binder, and producer properties before the first send if specific behavior is needed.
6. Send using `StreamBridge.send(bindingName, data)` and check the result.
7. Design retries, outbox, and idempotency according to delivery requirements.
8. Test with the Test Binder, then verify provisioning and publishing on the target broker.

Document binding names and destinations clearly in operational docs. When changing destinations or binders, update configuration and tests to prevent an infrastructure change from sending messages to the wrong target.

## Conclusion

`spring.cloud.stream.output-bindings` enables creating output bindings right when the application starts, fitting stable topologies that require explicit configuration. If `StreamBridge.send` is called with a name that has no binding yet, Spring Cloud Stream can dynamically create a binding on the first send, fitting controlled dynamic target sets.

In both approaches, distinguish binding names from destinations, scope content type and binder configuration properly, restrict dynamic destinations, and handle send results intentionally. A `true` return value from `send` is not confirmation that a consumer has processed the message. When reliability between database and broker is needed, combine outbox, retries, and idempotent consumers.
