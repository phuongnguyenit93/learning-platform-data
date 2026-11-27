# Output Routing with StreamBridge and Dynamic Destinations

## Objectives

In an event-driven application, a service may need to emit different types of messages to different destinations. For example, regional order events are sent to their corresponding topics; audit notifications are sent to a dedicated destination; or an adapter sends events to one of several configured integration systems.

Spring Cloud Stream provides `StreamBridge` to send messages from imperative code to an output binding. When the topology is known in advance, the application can declare static output bindings. When the target set must be flexible, StreamBridge can create bindings dynamically on the first send to an unbound destination.

This lesson explains how to choose output targets, distinguish destinations from binding names and broker-internal routing keys, control dynamic destinations, configure binders, and test sending flows.

After this lesson, you will be able to:

- Send messages to static output bindings using `StreamBridge.send`.
- Create dynamic output bindings on the first send to an allowed destination.
- Route by event type or authenticated context using an explicit lookup map.
- Distinguish destinations from Kafka keys/partitions and RabbitMQ routing keys.
- Manage allowlists, provisioning, and binders for output targets.
- Handle send results and test routing with the Test Binder as well as target brokers.

## 1. StreamBridge and output routing

`StreamBridge` is Spring Cloud Stream's imperative API. It allows sending an object or a Spring `Message` to an output binding from a service, controller, scheduler, or outbox relay without declaring a `Supplier` or `Function` solely to emit messages.

Publisher example:

```java
@Service
public class OrderEventPublisher {

    private final StreamBridge streamBridge;

    public OrderEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(OrderCreated event) {
        return streamBridge.send("orders-out-0", event);
    }
}
```

The string `orders-out-0` is the binding name StreamBridge uses to locate the output channel. That binding is configured with a specific destination, such as a Kafka topic or a destination managed by the Rabbit or Pulsar binder.

| Concept | Meaning | Example |
|---|---|---|
| Binding name | Output binding name inside the Spring Cloud Stream app | `orders-out-0` |
| Destination | Logical target on the broker that the binding sends to | `orders.created` |
| Binder | Adapter connecting the binding to a broker | Kafka, RabbitMQ, or Pulsar binder |
| Partition/key/routing key | How the broker partitions or routes within a destination | Kafka partition key, Rabbit routing key, Pulsar message key |

Output routing can occur at two levels:

1. **Selecting a destination:** deciding which topic, queue/exchange, or Pulsar topic a message goes to.
2. **Routing within a destination:** choosing a partition, key, or target queue using broker mechanics.

These two levels solve different problems. Choosing a partition does not move a message to another topic; changing a routing key is not the same as changing an output binding.

## 2. Using static output bindings when the topology is known

If an application sends only to a stable set of destinations, declare output bindings in configuration. Bindings can be initialized at startup using `spring.cloud.stream.output-bindings`:

```yaml
spring:
  cloud:
    stream:
      output-bindings: orders-out-0;audit-out-0
      bindings:
        orders-out-0:
          destination: orders.created
          content-type: application/json
        audit-out-0:
          destination: audit.events
          content-type: application/json
```

The publisher sends to the exact binding name:

```java
@Service
public class EventPublisher {

    private final StreamBridge streamBridge;

    public EventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publishOrder(OrderCreated event) {
        return streamBridge.send("orders-out-0", event);
    }

    public boolean publishAudit(AuditEvent event) {
        return streamBridge.send("audit-out-0", event);
    }
}
```

In this example, the code selects one of the two declared bindings. A binding name can differ from the destination name; configuration performs the mapping between them.

Bindings can be declared without listing them in `output-bindings` if they are created through other means in the application. `output-bindings` is useful when you want output bindings created proactively during startup so certain configuration or connectivity errors surface early.

**Prefer static bindings when:**

- Destinations are known before deployment.
- Each target needs specific configuration for content type, binder, partitioning, or producer properties.
- You want the topology to be easy to inventory, monitor, and authorize.
- You want provisioning or connectivity errors to appear at startup rather than on the first request.

Creating bindings at startup does not guarantee the topic, queue, exchange, or Pulsar topic already exists on the broker. Resource creation depends on auto-provisioning support, account permissions, and binder configuration. If auto-provisioning is disabled, infrastructure must create destinations as part of deployment.

## 3. Creating dynamic bindings on first send

When calling `StreamBridge.send` with a name that does not yet have an output binding, Spring Cloud Stream can dynamically create a binding for that name on the first send. Without an explicit mapping configuration, the passed name is used as the default destination.

Example:

```java
@Service
public class RegionalEventPublisher {

    private final StreamBridge streamBridge;

    public RegionalEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(String destination, OrderCreated event) {
        return streamBridge.send(destination, event);
    }
}
```

If the first call is:

```java
streamBridge.send("orders.eu", event);
```

and no binding named `orders.eu` exists yet, the framework can dynamically create an output binding targeting the `orders.eu` destination. Subsequent sends reuse the created binding according to the framework's binding management mechanism.

You can restrict the set of dynamic destinations:

```yaml
spring:
  cloud:
    stream:
      dynamic-destinations:
        - orders.eu
        - orders.apac
        - orders.us
```

When the allowlist is enabled, only listed destinations are permitted for dynamic binding creation according to the framework's policy. Verify exactly how allowlist checks and name matching work in your Spring Cloud Stream version.

Dynamic destinations are useful when targets are genuinely chosen at runtime, yet still remain within an anticipated set. Never take a destination string directly from an HTTP request, external message, or user input and pass it straight into `StreamBridge.send`. Doing so could cause the application to attempt creating unexpected topics/queues or send data to unauthorized targets.

## 4. Routing by event type using a lookup map

A safe implementation maps validated business values to a fixed set of destinations. Never let arbitrary input data dictate broker destination names.

Example:

```java
public enum Region {
    EU,
    APAC,
    US
}
```

Publisher using a lookup map:

```java
@Service
public class RegionalOrderPublisher {

    private static final Map<Region, String> DESTINATIONS = Map.of(
            Region.EU, "orders.eu",
            Region.APAC, "orders.apac",
            Region.US, "orders.us"
    );

    private final StreamBridge streamBridge;

    public RegionalOrderPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(Region region, OrderCreated event) {
        String destination = DESTINATIONS.get(region);
        if (destination == null) {
            throw new IllegalArgumentException("Unsupported region");
        }

        Message<OrderCreated> message = MessageBuilder
                .withPayload(event)
                .setHeader("eventId", event.eventId())
                .setHeader("eventType", "order.created")
                .build();

        return streamBridge.send(destination, message);
    }
}
```

Destinations in the lookup map should also be included in the allowlist:

```yaml
spring:
  cloud:
    stream:
      dynamic-destinations:
        - orders.eu
        - orders.apac
        - orders.us
```

The `region` value should be validated according to application policy before calling the publisher. If region comes from tenant or user context, verify authorization to access that tenant. Never treat an arbitrary header sent by an external producer as authorization proof.

You can route by event type similarly:

```java
String destination = switch (event.type()) {
    case ORDER_CREATED -> "orders.created";
    case ORDER_CANCELLED -> "orders.cancelled";
    case ORDER_REFUNDED -> "orders.refunded";
};
streamBridge.send(destination, event);
```

In production code, use an enum or sealed type and handle unsupported values explicitly. A lookup map helps reviewers inspect every possible destination and supports testing each branch.

## 5. Specific configuration for dynamic destinations

If a dynamic destination needs its own content type or binding properties, you can declare configuration under its binding name before the first send occurs:

```yaml
spring:
  cloud:
    stream:
      dynamic-destinations:
        - orders.eu
        - orders.apac
      bindings:
        orders.eu:
          destination: company.orders.eu
          content-type: application/json
        orders.apac:
          destination: company.orders.apac
          content-type: application/json
```

Code calls `send` with the corresponding binding name:

```java
streamBridge.send("orders.eu", event);
streamBridge.send("orders.apac", event);
```

Here `orders.eu` and `orders.apac` are binding names invoked from code; the physical/logical destinations on the broker are configured separately. Pre-declaring properties lets the framework create the dynamic binding with the desired settings when needed.

If an application uses multiple binders, be especially careful. A dynamic binding must be associated with the right binder according to the framework version's configuration mechanism; never assume a destination name automatically selects the right binder. For targets requiring different binders or specialized producer properties, explicitly configured static output bindings are usually easier to control. Do not let business logic choose binders by inspecting broker names.

## 6. Destinations versus partition keys and routing keys

A common design mistake is using a broker-internal routing mechanism to solve a destination-selection requirement.

### Kafka

Kafka stores records in topics and partitions. The output binding specifies the topic; a record's key can be used to choose the partition. Records with the same key are typically assigned to the same partition by the configured partitioner, supporting key-based ordering within that partition.

Example:

- Destination/topic: `orders.created`.
- Record key: `order-42`.
- Partition: determined by the partitioner from the key and topic topology.

Changing the key does not send the record to a different topic. If you need to separate data into `orders.eu` and `orders.apac` topics, select the corresponding binding/destination first; then use keys to determine partitioning within that topic.

### RabbitMQ

RabbitMQ publishes messages to an exchange with a routing key. The exchange and binding rules decide which queues receive the message. A routing key is neither an output binding name nor necessarily a queue name. If you need to target a different exchange/destination, choose the appropriate output binding or binder configuration. If you only need to select queues via a topic/direct exchange, routing keys and exchange topology handle routing inside the broker.

### Pulsar

A Pulsar destination identifies a topic. A message key can assist partitioning or key-based processing depending on schema and subscription mode. A key does not replace topic selection. Distinguish the topic chosen by the binding from the key sent with the message.

| Broker | Selecting destination | Routing within destination |
|---|---|---|
| Kafka | Output binding → topic | Record key/partitioner → partition |
| RabbitMQ | Output binding and configured exchange | Routing key + exchange bindings → queue |
| Pulsar | Output binding → topic | Message key and partitioning mechanism |

## 7. Content type, headers, and serialization

Whether sending to a static or dynamic binding, the payload must still be in a format compatible with consumers. You can declare `content-type` per binding:

```yaml
spring:
  cloud:
    stream:
      bindings:
        orders.eu:
          destination: company.orders.eu
          content-type: application/json
```

Sending a POJO:

```java
boolean accepted = streamBridge.send("orders.eu", event);
```

Or sending a Spring Message with application headers:

```java
Message<OrderCreated> message = MessageBuilder
        .withPayload(event)
        .setHeader("eventId", event.eventId())
        .setHeader("correlationId", correlationId)
        .build();

boolean accepted = streamBridge.send("orders.eu", message);
```

Headers such as `eventId` and `correlationId` are application-defined metadata. Do not fabricate broker-managed metadata such as Kafka offsets, Rabbit delivery tags, or Pulsar message IDs. Propagation of custom headers and payload conversion depend on the binder, content type, and native encoding/decoding settings. Producer and consumer must agree on schema and wire format.

## 8. Send results, errors, and delivery guarantees

`StreamBridge.send` returns a boolean indicating whether the message was accepted by the output binding/channel under the framework's mechanics. Returning `true` does not prove that a consumer received, processed, or committed the business action. Nor does it replace broker acknowledgments or transactions across a database and a broker.

Publishers should check the return value and handle exceptions:

```java
public void publish(OrderCreated event) {
    boolean accepted = streamBridge.send("orders.eu", event);

    if (!accepted) {
        throw new IllegalStateException(
                "Output binding did not accept the event"
        );
    }
}
```

In production, observe errors occurring during binding creation, destination provisioning, payload serialization, or broker sends. Some errors surface as synchronous exceptions; asynchronous send failures may be reported via binder callback/error mechanisms. Check the documentation and behavior of your specific binder.

If events originate alongside a database change, sending directly from a transactional service can leave a gap: the database commits while the message fails to send, or the message is sent while the database rolls back. You can use a transactional outbox:

1. Write the business change and the outbox record in the same database transaction.
2. A relay reads unsent records and chooses the output binding via a controlled lookup map.
3. The relay sends the message through StreamBridge.
4. Once the send status is confirmed per the relay's policy, mark the outbox record as sent.
5. If the relay stops after sending but before marking, the message may be sent again; consumers must be idempotent by event ID.

Do not mark an outbox record complete merely because a send call returned true if durability requires explicit broker confirmation. Design relay states around binder confirmation semantics and accept the possibility of duplicate sends.

## 9. Provisioning and destination access permissions

Dynamic bindings do not mean the broker automatically creates every resource. The outcome depends on the binder and infrastructure configuration:

- Kafka may require topics to be pre-created or allow auto topic creation per broker policy.
- RabbitMQ may require exchanges, queues, and bindings to be provisioned by the binder or infrastructure.
- Pulsar may require topics/namespaces to be pre-created or rely on cluster auto-creation policy.

The application account needs publish permissions to permitted destinations. Permissions to create topics, exchanges, or queues should be granted separately following the principle of least privilege. If an application does not need to create resources at runtime, disable or restrict dynamic provisioning and manage topology via IaC/deployment pipelines.

For dynamic destinations, establish policies for:

- List of permitted destinations.
- Publish permissions per binder and namespace.
- Naming conventions and cardinality limits.
- How to handle nonexistent destinations.
- Monitoring the count of created bindings/destinations and provisioning errors.
- Destination lifecycle when a tenant or integration is decommissioned.

Do not create a separate topic per request or per user if partitioning, keys, or tenant metadata already satisfies the requirement. Too many destinations increase metadata load, administrative overhead, and operational complexity.

## 10. Testing output routing

Test both the target selection decision and binding behavior.

### Unit testing the lookup map

Verify that each event type or region maps to the expected binding name. Verify that unsupported values are rejected and arbitrary destinations cannot be constructed.

You can mock StreamBridge to verify the publisher invokes the right binding name with the expected payload. This test verifies selection logic, though it does not prove the binding was created or the broker received the message.

### Test Binder

Use the Spring Cloud Stream Test Binder to verify:

- Static bindings are initialized per configuration.
- StreamBridge sends messages to the expected output channel.
- Dynamic bindings are created on first send to a valid destination.
- The allowlist rejects disallowed destinations per configuration.
- Payloads and application headers are converted as expected.

The Test Binder exercises the framework at the test level and does not fully simulate provisioning, permissions, or native metadata of individual brokers.

### Broker integration tests

Use Kafka, RabbitMQ, or Pulsar running in a test environment to verify:

- Actual destination/topic/exchange/queue matches expectations.
- The right binder is selected.
- The broker account has required publish and provisioning permissions.
- Kafka key/partition, Rabbit routing key/queue, or Pulsar key/partition behave properly.
- Consumers receive payloads and headers according to contract.
- Broker errors or missing destinations are observed and handled properly.

In systems using multiple binders, test every binder type used in production. Do not infer RabbitMQ or Pulsar behavior solely from a test run against Kafka.

## 11. Implementation workflow

When designing output routing with StreamBridge, follow this sequence:

1. Identify the event types and destinations the application needs to send to.
2. If the target set is stable, declare static output bindings and map binding names to destinations.
3. If dynamic bindings are needed, define an allowlist and naming rules; never accept arbitrary destination names from outside.
4. Write a lookup map from validated event type/region to binding name.
5. Configure content type, binder, and producer properties for each target.
6. Distinguish selecting a destination from keys, partitions, or routing keys inside the broker.
7. Verify send results, exceptions, provisioning, and publish permissions.
8. If coordinating with a database, use an outbox and idempotent consumers.
9. Write unit tests, Test Binder tests, and broker integration tests for every routing branch.

Document the list of binding names, destinations, binders, owners, and access permissions in operational documentation. When adding a new destination, update the allowlist, broker configuration, and contract tests before deploying code that sends to that target.

## Conclusion

`StreamBridge` allows sending messages from imperative code to output bindings. Static bindings suit known topologies and provide explicit configuration; dynamic bindings allow creating output bindings on the first send to a controlled destination. A lookup map from validated event types or contexts lets the application route without relying on arbitrary destination strings.

Distinguish destinations from Kafka partition keys, RabbitMQ routing keys, and Pulsar message keys. Enforce allowlists, provisioning controls, binders, and publish permissions; inspect send results and test against target brokers. A `true` return value from StreamBridge does not confirm consumer processing, so reliable business flows still require appropriate retries, outbox patterns, and idempotency.
