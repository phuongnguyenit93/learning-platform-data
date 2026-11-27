# Bridging Kafka and RabbitMQ with a Unified Data Contract

A system may use Kafka to ingest events from domain services while using RabbitMQ to distribute tasks to processing groups. When building a bridge between two brokers with Spring Cloud Stream, the hardest challenge is not reading a record and publishing a message. The challenge is ensuring both sides understand **the exact same data contract**, preserving event identity and context, controlling duplicates under failure, and staying operable when either broker goes down.

This exercise builds the following flow:

~~~text
Order Service
    |
    | Kafka topic: orders.created
    v
Kafka Binder
    |
    | Spring Cloud Stream Function
    v
Bridge: validate + map + preserve event identity
    |
    | RabbitMQ topic exchange: orders.fulfillment
    v
Queue: orders.fulfillment.fulfillment-service
    |
    v
Fulfillment Service
~~~

The bridge application consumes `OrderCreated` events from Kafka, validates the contract, maps them to `FulfillmentRequested`, and publishes to RabbitMQ. Both brokers share a unified event envelope carrying `eventId`, `eventType`, `schemaVersion`, timestamp, producer, `correlationId`, and a strongly typed payload.

The examples use the Spring Cloud Stream functional model and two official binders. Broker names, queues, topics, routing keys, and Java code are adaptable to your system. The lesson also examines delivery guarantees: Kafka and RabbitMQ do not participate in a shared transaction by default, so you must never claim the bridge achieves exactly-once semantics just because a function returned normally.

## 1. Objectives and Completion Criteria

After completing this exercise, you should be able to:

1. Define a unified event envelope shared across multiple brokers.
2. Distinguish the event contract from Kafka record keys, Kafka headers, RabbitMQ routing keys, and AMQP headers.
3. Configure a Spring Cloud Stream application with a Kafka input binder and a RabbitMQ output binder.
4. Implement a `Function` that consumes `OrderCreated` and produces `FulfillmentRequested`.
5. Preserve `eventId`, `causationId`, `correlationId`, and trace context across the bridge.
6. Explicitly map destinations, consumer groups, exchanges, queues, and routing keys.
7. Verify schema evolution and validation before publishing.
8. Explain the duplicate window between output publishing and Kafka offset commits.
9. Design inbox/outbox and idempotent consumers when higher reliability is required.
10. Test end-to-end with real Kafka and RabbitMQ instances via Testcontainers.
11. Monitor lag, retries, publish failures, DLQs, and backlogs.
12. Handle broker outages, restarts, replays, and rolling deployments following a runbook.

Minimum completion criteria:

- Valid `OrderCreated` events are read from the expected Kafka topic.
- Under normal operation, the bridge emits `FulfillmentRequested` matching the agreed contract.
- Event identity and correlation context are preserved or mapped according to documented rules.
- RabbitMQ routes messages to the fulfillment group's queue.
- Invalid payloads route to an observable and manageable error path.
- Tests prove duplicates can happen at the two-broker boundary and downstream handles them idempotently.

## 2. Designing a Unified Event Contract

Never let each broker dictate its own separate business payload structure. Kafka and RabbitMQ are merely transports; the event contract defines the data semantics shared between producers and consumers.

Recommended envelope:

| Field | Type | Meaning |
|---|---|---|
| `eventId` | string | Unique, stable identifier of the event |
| `eventType` | string | Event type name, e.g., `OrderCreated` |
| `schemaVersion` | integer | Payload schema version |
| `occurredAt` | UTC timestamp | Timestamp when the business event occurred |
| `producer` | string | Service that emitted the event |
| `correlationId` | string | Correlates steps within the same business flow |
| `causationId` | string/null | Event that caused the current event |
| `traceparent` | string/null | W3C trace context if available |
| `payload` | object | Domain data with its own schema |

Example JSON:

~~~json
{
  "eventId": "9d7a1a3e-6c88-4f8e-ae6c-7b80d8c8d100",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "occurredAt": "2026-11-24T08:15:30Z",
  "producer": "order-service",
  "correlationId": "checkout-7f13",
  "causationId": null,
  "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
  "payload": {
    "orderId": "ORD-1042",
    "customerId": "CUS-882",
    "currency": "VND",
    "totalMinor": 259900,
    "items": [
      {
        "sku": "SKU-CHAIR-01",
        "quantity": 1,
        "unitPriceMinor": 259900
      }
    ]
  }
}
~~~

Using integer minor units for money (such as VND or cents) avoids floating-point rounding errors. In multi-currency systems, always include `currency`. Timestamps should carry timezone info and be normalized to UTC. Business IDs should not embed sensitive data.

### Why Must the Envelope Stay Stable?

If a Kafka producer sends a record with a `correlationId` header and the bridge forwards the payload to RabbitMQ while dropping headers, downstream loses tracing context. If the event ID only exists as a Kafka offset, it cannot be used for deduplication in a RabbitMQ consumer.

Putting cross-system metadata inside the envelope keeps the contract broker-independent. You can copy selected fields to transport headers for routing or faster observability, while the payload itself still retains everything needed for independent replay or storage.

## 3. Defining Input and Output Schemas

`OrderCreated` describes an order creation event. `FulfillmentRequested` is a request sent to the fulfillment system.

~~~json
{
  "eventId": "source-event-id",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "occurredAt": "2026-11-24T08:15:30Z",
  "producer": "order-service",
  "correlationId": "checkout-7f13",
  "causationId": null,
  "traceparent": null,
  "payload": {
    "orderId": "ORD-1042",
    "customerId": "CUS-882",
    "currency": "VND",
    "totalMinor": 259900,
    "items": [
      {
        "sku": "SKU-CHAIR-01",
        "quantity": 1,
        "unitPriceMinor": 259900
      }
    ]
  }
}
~~~

The bridge produces the output envelope:

~~~json
{
  "eventId": "deterministic-fulfillment-event-id",
  "eventType": "FulfillmentRequested",
  "schemaVersion": 1,
  "occurredAt": "2026-11-24T08:15:31Z",
  "producer": "order-fulfillment-bridge",
  "correlationId": "checkout-7f13",
  "causationId": "source-event-id",
  "traceparent": null,
  "payload": {
    "fulfillmentId": "deterministic-id-derived-from-source-event",
    "orderId": "ORD-1042",
    "customerId": "CUS-882",
    "currency": "VND",
    "totalMinor": 259900,
    "items": [
      {
        "sku": "SKU-CHAIR-01",
        "quantity": 1
      }
    ]
  }
}
~~~

The output event has its own `eventType` and `schemaVersion`. `causationId` points to the input event. Output `eventId` must remain deterministic across repeated processing of the same input event if downstream relies on it for deduplication.

A simple rule is deriving a deterministic ID from the source event ID and output event type name. Never generate a fresh random UUID on every retry, as two executions of the same input would produce two different identities.

## 4. Schema Compatibility Rules

Data contracts must be managed like public APIs across services.

Practical rules:

- Add new fields as optional or with safe defaults.
- Never change the meaning of an existing field within the same schema version.
- Never rename a required field without a transition phase.
- Never arbitrarily change a field type from number to string or vice versa.
- Never reuse an `eventType` for a different business meaning.
- Consumers should ignore unknown fields when serializer and contract allow it.
- Producers must emit only schema versions supported by consumers.
- For breaking changes, introduce a new version or new event type with a migration plan.

Example adding a note field:

~~~json
{
  "orderId": "ORD-1042",
  "customerId": "CUS-882",
  "currency": "VND",
  "totalMinor": 259900,
  "customerNote": null
}
~~~

Older consumers can ignore `customerNote`. However, changing `totalMinor` to a decimal `totalAmount` requires agreeing on conversion, rounding, and currency handling before publishing the new schema.

You can manage JSON Schema, Avro, or Protobuf in a schema registry. When using plain JSON, maintain contract tests and version control in the repository. Writing `schemaVersion` into the envelope without validating schema contents is insufficient.

## 5. Distinguishing Payload, Kafka Key, and Transport Headers

These elements solve different problems:

| Element | Used for | Part of event contract? |
|---|---|---|
| Envelope payload | Business meaning and identity | Yes |
| Kafka record key | Partitioning and per-key ordering | No |
| Kafka headers | Additional transport metadata | No |
| Rabbit routing key | Routing to queues | No |
| AMQP headers | Transport metadata and header exchanges | No |
| Pulsar message key | Key-based distribution | No |

For example, the Kafka key can be `orderId` so events for the same order hit the same partition. The RabbitMQ routing key can be `fulfillment.requested` to route to the fulfillment group's queue. Neither value should be treated as `eventType` or `eventId`.

If the bridge transforms a Kafka key into a RabbitMQ routing key, document the mapping rule explicitly. Never blindly copy all transport headers because they may contain broker-specific attributes like delivery tags, offsets, partitions, or internal headers.

## 6. Bridge Application Structure

A maintainable package structure:

~~~text
order-fulfillment-bridge/
  src/main/java/com/example/bridge/
    BridgeApplication.java
    config/
      BridgeFunctionConfiguration.java
    contract/
      EventEnvelope.java
      OrderCreated.java
      FulfillmentRequested.java
      OrderItem.java
    mapping/
      FulfillmentMapper.java
    validation/
      OrderCreatedValidator.java
    messaging/
      BridgeHeaders.java
      BridgeFailureHandler.java
    reliability/
      InboxService.java
      OutboxService.java
      OutboxPublisher.java
  src/main/resources/
    application.yml
  src/test/java/com/example/bridge/
    FulfillmentMapperTest.java
    BridgeContractTest.java
    KafkaRabbitBridgeIT.java
~~~

Separate contracts from binder configuration so mapping can be tested without a broker. Separate validation from mapping so schema errors and business errors can be classified independently. Reliability components are only needed when delivery guarantees exceed what a direct bridge provides.

## 7. Dependencies for Kafka and RabbitMQ Binders

With Maven, add Spring Cloud Stream and both binders. Manage versions using a Spring Cloud BOM compatible with your project's Spring Boot version.

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>2025.1.3</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-stream-kafka</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-stream-rabbit</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

This example uses Spring Cloud 2025.1.3, compatible with Spring Boot 4.0.x and 4.1.x. If your project uses Spring Boot 3.5.x, pick the corresponding 2025.0.x release train; always check the compatibility matrix before upgrading. Do not override Kafka client or Spring AMQP versions outside dependency management without a clear reason.

Both binders sit on the same classpath. Therefore, every binding configuration must specify its `binder` explicitly to prevent output from accidentally going to Kafka or input accidentally using RabbitMQ.

## 8. Configuring Both Binders in `application.yml`

Local configuration example:

~~~yaml
spring:
  application:
    name: order-fulfillment-bridge
  cloud:
    function:
      definition: bridgeOrder
    stream:
      default-binder: kafka
      bindings:
        bridgeOrder-in-0:
          destination: orders.created
          group: order-fulfillment-bridge
          binder: kafka
          content-type: application/json
          consumer:
            max-attempts: 3
            back-off-initial-interval: 1000
            back-off-max-interval: 5000
            back-off-multiplier: 2.0
        bridgeOrder-out-0:
          destination: orders.fulfillment
          binder: rabbit
          content-type: application/json
          producer:
            required-groups:
              - fulfillment-service
      kafka:
        binder:
          brokers: localhost:9092
      rabbit:
        bindings:
          bridgeOrder-out-0:
            producer:
              routing-key: fulfillment.requested
              binding-routing-key: fulfillment.requested
              exchange-type: topic

  rabbitmq:
    host: localhost
    port: 5672
    username: guest
    password: guest

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
~~~

Key meanings:

- `bridgeOrder` is the Function bean name.
- `bridgeOrder-in-0` is the Kafka input.
- `bridgeOrder-out-0` is the RabbitMQ output.
- `order-fulfillment-bridge` is the stable Kafka consumer group.
- `orders.created` is the Kafka topic.
- `orders.fulfillment` is the RabbitMQ exchange destination.
- `fulfillment.requested` is the routing key.
- `required-groups` instructs the binder to provision queues and bindings for downstream groups per RabbitMQ binder semantics.

In production, replace endpoints and credentials with external secrets/configuration. Never use `guest`/`guest` or `localhost`. When using TLS/SASL, configure them separately for the Kafka binder and RabbitMQ connection factory.

## 9. Java Data Models

Create records representing the contract:

~~~java
import java.time.Instant;
import java.util.List;

public record EventEnvelope<T>(
    String eventId,
    String eventType,
    int schemaVersion,
    Instant occurredAt,
    String producer,
    String correlationId,
    String causationId,
    String traceparent,
    T payload
) {
}

public record OrderItem(
    String sku,
    int quantity,
    long unitPriceMinor
) {
}

public record OrderCreated(
    String orderId,
    String customerId,
    String currency,
    long totalMinor,
    List<OrderItem> items
) {
}

public record FulfillmentItem(
    String sku,
    int quantity
) {
}

public record FulfillmentRequested(
    String fulfillmentId,
    String orderId,
    String customerId,
    String currency,
    long totalMinor,
    List<FulfillmentItem> items
) {
}
~~~

These records describe payloads only. Validation checks for nulls, blanks, negative numbers, currencies, and quantities before the bridge publishes.

Use `Instant` to represent UTC timestamps. If the contract needs to retain the original business timezone, add a dedicated field rather than letting each service interpret timestamps in its host timezone.

## 10. Validation Before Mapping

Never publish downstream if the input fails validation. Example validator:

~~~java
import java.util.Objects;

public final class OrderCreatedValidator {

    public void validate(EventEnvelope<OrderCreated> envelope) {
        if (envelope == null) {
            throw new InvalidOrderEventException("Envelope is required");
        }
        if (isBlank(envelope.eventId())) {
            throw new InvalidOrderEventException("eventId is required");
        }
        if (!"OrderCreated".equals(envelope.eventType())) {
            throw new InvalidOrderEventException("Unexpected eventType");
        }
        if (envelope.schemaVersion() != 1) {
            throw new UnsupportedSchemaVersionException(
                "Unsupported OrderCreated schemaVersion"
            );
        }

        OrderCreated payload = envelope.payload();
        if (payload == null || isBlank(payload.orderId())) {
            throw new InvalidOrderEventException("orderId is required");
        }
        if (isBlank(payload.customerId()) || isBlank(payload.currency())) {
            throw new InvalidOrderEventException(
                "customerId and currency are required"
            );
        }
        if (payload.totalMinor() < 0) {
            throw new InvalidOrderEventException("totalMinor cannot be negative");
        }
        if (payload.items() == null || payload.items().isEmpty()) {
            throw new InvalidOrderEventException("At least one item is required");
        }

        for (OrderItem item : payload.items()) {
            if (item == null || isBlank(item.sku())
                    || item.quantity() <= 0
                    || item.unitPriceMinor() < 0) {
                throw new InvalidOrderEventException("Invalid order item");
            }
        }
    }

    private boolean isBlank(String value) {
        return value == null || value.isBlank();
    }
}
~~~

Exception types are custom application classes. Distinguish permanent data errors (bad schema, missing IDs) from transient errors (database unavailable, broker timeout). Retrying an invalid payload repeatedly will not make it valid; such errors need an error channel/DLQ and a data-correction process.

## 11. Mapping and Deterministic Event Identity

The mapper converts the source payload into the target payload. Output IDs are derived deterministically from the source event ID:

~~~java
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.util.UUID;

public final class FulfillmentMapper {

    private final Clock clock;

    public FulfillmentMapper(Clock clock) {
        this.clock = clock;
    }

    public EventEnvelope<FulfillmentRequested> map(
            EventEnvelope<OrderCreated> source) {

        OrderCreated order = source.payload();

        String outputId = UUID.nameUUIDFromBytes(
            ("FulfillmentRequested:v1:" + source.eventId())
                .getBytes(StandardCharsets.UTF_8)
        ).toString();

        var items = order.items().stream()
            .map(item -> new FulfillmentItem(item.sku(), item.quantity()))
            .toList();

        var payload = new FulfillmentRequested(
            outputId,
            order.orderId(),
            order.customerId(),
            order.currency(),
            order.totalMinor(),
            items
        );

        return new EventEnvelope<>(
            outputId,
            "FulfillmentRequested",
            1,
            clock.instant(),
            "order-fulfillment-bridge",
            source.correlationId(),
            source.eventId(),
            source.traceparent(),
            payload
        );
    }
}
~~~

`UUID.nameUUIDFromBytes` generates deterministic IDs from the same input string. This produces a name-based UUID (v3); if your system requires UUIDv5 with a specific namespace, use a standard UUIDv5 implementation rather than assuming the default UUID is v5.

The output identifier incorporates both the event type and mapping version. If mapping logic changes in a way that creates a distinct business event, consider bumping the version or changing the idempotency key. Never randomize IDs every time Kafka redelivers an input.

## 12. Function Receiving Kafka Messages and Producing RabbitMQ Messages

The function uses Spring `Message` to read payloads and preserve required metadata:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Configuration
public class BridgeFunctionConfiguration {

    @Bean
    OrderCreatedValidator orderCreatedValidator() {
        return new OrderCreatedValidator();
    }

    @Bean
    FulfillmentMapper fulfillmentMapper() {
        return new FulfillmentMapper(java.time.Clock.systemUTC());
    }

    @Bean
    Function<Message<EventEnvelope<OrderCreated>>,
             Message<EventEnvelope<FulfillmentRequested>>> bridgeOrder(
            OrderCreatedValidator validator,
            FulfillmentMapper mapper) {

        return input -> {
            EventEnvelope<OrderCreated> source = input.getPayload();
            validator.validate(source);

            EventEnvelope<FulfillmentRequested> output = mapper.map(source);

            return MessageBuilder.fromMessage(input)
                .setPayload(output)
                .setHeader("event_id", output.eventId())
                .setHeader("event_type", output.eventType())
                .setHeader("correlation_id", output.correlationId())
                .setHeader("causation_id", output.causationId())
                .build();
        };
    }
}
~~~

`MessageBuilder.fromMessage` retains allowed forwarded headers. Control which headers are transport-specific versus contract-level. Never copy delivery tags, Kafka offsets, partition metadata, or RabbitMQ delivery metadata to the target broker as if they carried the same meaning.

The event envelope is the primary source of truth for `eventId`, `eventType`, and `correlationId`. Headers are copied for observability or routing; downstream must still be able to process the payload standalone.

When using tracing instrumentation, let Micrometer Tracing/OpenTelemetry manage trace context according to your Spring Boot version. Never fabricate a fake `traceparent` or overwrite an existing trace ID.

## 13. Verifying Binding Names and Destinations

For function `bridgeOrder`:

| Direction | Binding name | Binder | Destination |
|---|---|---|---|
| Input | `bridgeOrder-in-0` | Kafka | `orders.created` |
| Output | `bridgeOrder-out-0` | RabbitMQ | `orders.fulfillment` |

A common mistake is configuring output under `bridgeOrder-out` when the function actually creates `bridgeOrder-out-0`. In that case, the intended output binding configuration is ignored.

If the function is renamed, its default binding names change too. When aliasing via `spring.cloud.stream.function.bindings`, update extended binder properties to match the mapped binding name.

Do not inspect YAML alone. Check startup logs and Actuator `/actuator/bindings` to confirm which bindings were created, which binder was selected, and that their state is `STARTED`.

## 14. Kafka Topic and Key for Order Events

The source Kafka producer should key records by `orderId` so events for the same order land in the same partition:

~~~text
Kafka topic: orders.created
Record key:  ORD-1042
Value:       EventEnvelope<OrderCreated>
Headers:     event_id, event_type, correlation_id
~~~

If the upstream producer uses Spring Cloud Stream, configure a payload-based partition key expression or use `KafkaTemplate`/`ProducerRecord`. Implementation depends on the producer; what matters is choosing a stable key and having all producers follow the same rule.

The bridge does not automatically convert a Kafka partition key into a RabbitMQ routing key. Kafka partitions preserve order within a partition; RabbitMQ queues have different semantics. If downstream needs per-`orderId` ordering, design queue sharding or serialization by `orderId`.

Verify the topic has appropriate partitions, retention, ACLs, and replication. The bridge consumer group needs permissions to read the topic and commit offsets.

## 15. RabbitMQ Exchange, Queue, and Routing Key

The RabbitMQ Binder uses the destination as the exchange name. For a named group, the binder typically creates a queue named `destination.group` and binds it to the exchange.

Example:

~~~text
Exchange: orders.fulfillment
Type:     topic
Queue:    orders.fulfillment.fulfillment-service
Key:      fulfillment.requested
~~~

Downstream consumer:

~~~yaml
spring:
  cloud:
    function:
      definition: receiveFulfillment
    stream:
      bindings:
        receiveFulfillment-in-0:
          destination: orders.fulfillment
          group: fulfillment-service
          binder: rabbit
          content-type: application/json
      rabbit:
        bindings:
          receiveFulfillment-in-0:
            consumer:
              binding-routing-key: fulfillment.requested
~~~

Producer output uses the same exchange and routing key. When the output binding declares `required-groups`, the RabbitMQ Binder can pre-provision queues and bindings for each group before consumers start. The producer `binding-routing-key` property specifies the key used to bind queues created via `required-groups`; if omitted, it defaults to `#`. Therefore, this example sets producer `binding-routing-key` to `fulfillment.requested` matching `routing-key`. The consumer `binding-routing-key` must also align with that topology. If queues are externally pre-provisioned, binder settings must match queue names, exchange declarations, and binding policies. Never assume a queue named after the group is automatically selected unless `queueNameGroupOnly` is enabled.

A named group creates a durable queue per binder semantics; anonymous queues can auto-delete and are unsuitable for retaining backlogs while consumers are down.

## 16. Producer Routing Key vs. Consumer Binding Key

A RabbitMQ topic exchange matches a message's routing key against a queue's binding key:

- Producer routing key: `fulfillment.requested`
- Consumer binding key: `fulfillment.requested` or an appropriate pattern
- Exchange: `orders.fulfillment`

With an exact key, the queue receives that exact message type. If a queue should receive all fulfillment events, you can use a pattern like `fulfillment.#`, provided you evaluate the scope of routed data.

Never use broad wildcards like `#` if a queue should receive only one event type. An overly broad binding key lets unexpected messages enter the consumer, causing deserialization errors or unintended business execution.

When a queue is provisioned by the producer binding via `required-groups`, the producer-side `binding-routing-key` is a separate property used only to bind that queue—it is not the message's `routingKey`. A broad queue binding key can route more messages than intended even when the producer sets a specific routing key; verify both sides.

Publisher confirms and message routing are two distinct things. The broker can confirm a publish even when no queue matches the routing key. Configure and monitor publisher returns or an alternate exchange as needed, and verify actual queue bindings.

## 17. Content Type and JSON Conversion

Both input and output bindings declare:

~~~yaml
content-type: application/json
~~~

Spring Cloud Stream uses message conversion to turn JSON bytes into Java types and back. However, `content-type` is only part of the contract:

- Producer must serialize matching JSON schemas.
- Consumer must declare compatible payload types.
- `contentType` headers must be accurate.
- Native encoding/decoding must not be enabled unexpectedly.
- Schema versions must be checked in application code or a schema registry.
- Unknown fields and null fields need explicit policies.

If upstream emits Avro while the bridge expects JSON, the binder receives bytes yet fails to instantiate Java records. Never swap destinations to work around serialization mismatches.

With generic `EventEnvelope<T>`, verify that Spring Cloud Stream converters and Jackson retain payload type information in your version. If type erasure prevents converters from resolving the generic payload, use a concrete DTO or a tested custom converter.

## 18. Headers and Trace Context Across Both Brokers

Certain metadata should appear in both the envelope and transport headers:

| Metadata | In envelope | Transport header |
|---|---|---|
| `eventId` | Mandatory | Recommended |
| `eventType` | Mandatory | Recommended |
| `schemaVersion` | Mandatory | Optional as needed |
| `correlationId` | Mandatory for workflows | Recommended |
| `causationId` | Mandatory for derived events | Recommended |
| `traceparent` | Depends on tracing policy | Should propagate |
| Kafka offset/partition | No | Source logs/telemetry only |
| Rabbit `deliveryTag` | No | Rabbit processing metadata only |

Do not embed transport metadata into the payload if it lacks cross-broker business meaning. For instance, Kafka partition 2 does not correspond to any RabbitMQ queue partition 2.

When the bridge emits a new event, `causationId` should point to the source event, while `correlationId` preserves the original workflow. Trace context should continue via tracing instrumentation or follow W3C propagation standards.

## 19. Direct Bridge Reliability: At-Least-Once and the Duplicate Window

The simple path:

1. Kafka delivers `OrderCreated` to the bridge.
2. The function validates and maps.
3. The RabbitMQ Binder publishes `FulfillmentRequested`.
4. The Kafka consumer completes processing and commits offsets per ack/transaction policy.

There is a failure window:

~~~mermaid
sequenceDiagram
    participant K as Kafka
    participant B as Bridge
    participant R as RabbitMQ

    K->>B: Deliver event E
    B->>R: Publish output E2
    R-->>B: Broker accepts publish
    Note over B: Process crashes before Kafka offset commit
    K->>B: Redeliver event E
    B->>R: Publish E2 again
    R-->>B: Broker accepts duplicate
~~~

If output was published while input offsets were not yet committed, Kafka can redeliver the input. The bridge publishes the output a second time. This is valid duplicate behavior under at-least-once processing.

Conversely, if input offsets are committed before output is durably persisted, a crash loses the output. Understanding ack modes, transactions, and publisher confirms for your binder version is therefore essential.

**There is no default transaction spanning Kafka offsets and RabbitMQ publishing.** Kafka transactions do not automatically enlist RabbitMQ, and RabbitMQ publisher confirms do not commit Kafka offsets.

## 20. Downstream Idempotency

Because duplicates can occur, Fulfillment Service must deduplicate by `eventId` or an idempotency key.

Example inbox table:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(80) PRIMARY KEY,
    event_type VARCHAR(120) NOT NULL,
    processed_at TIMESTAMP NOT NULL
);
~~~

Processing inside a transaction:

~~~java
@Transactional
public void handle(FulfillmentRequestedEvent event) {
    boolean firstDelivery = inboxRepository.insertIfAbsent(
        event.eventId(),
        event.eventType()
    );

    if (!firstDelivery) {
        return;
    }

    fulfillmentRepository.createIfAbsent(
        event.payload().fulfillmentId(),
        event.payload()
    );
}
~~~

`insertIfAbsent` must use a database unique constraint or upsert. Never implement `SELECT` followed by `INSERT` without a unique constraint, because two concurrent consumers can pass the `SELECT` simultaneously.

If triggering side effects outside the database (calling shipping carriers, sending emails), pass an idempotency key to the external system or persist send state with controlled retries.

## 21. When Does the Bridge Itself Need Inbox/Outbox?

For critical flows, a direct bridge may not offer enough resilience. A more durable architecture:

~~~mermaid
flowchart TD
    K[Kafka orders.created] --> C[Bridge consumer]
    C --> T[DB transaction]
    T --> I[Inbox: unique source event ID]
    T --> O[Outbox: mapped output event]
    O --> P[Outbox publisher]
    P --> R[RabbitMQ exchange]
    R --> Q[Fulfillment queue]
    Q --> D[Downstream inbox/idempotency]
~~~

Inside one database transaction:

1. Insert the source event into the inbox with its unique `eventId`.
2. If it already exists, do not create another output row.
3. Map to `FulfillmentRequested` with a deterministic ID.
4. Write the output event to the outbox.
5. Commit the database transaction.
6. Only after the function returns normally is the Kafka binder allowed to ack/commit the input per configuration.

If the process crashes after DB commit but before Kafka offset commit, Kafka redelivers the event. The unique inbox detects the duplicate and skips creating a second outbox row. This is why the DB transaction must commit before the handler returns and offsets are acknowledged.

The outbox publisher sends to RabbitMQ and marks `sent` after confirmation per publisher-confirm policy. If it crashes after publishing but before marking `sent`, the relay may republish. Downstream still needs idempotency.

An outbox does not magically create exactly-once semantics across database and RabbitMQ; it establishes a durable, retryable, deduplicated delivery chain.

## 22. Reference Inbox/Outbox Schema

~~~sql
CREATE TABLE bridge_inbox (
    source_event_id VARCHAR(80) PRIMARY KEY,
    source_event_type VARCHAR(120) NOT NULL,
    received_at TIMESTAMP NOT NULL
);

CREATE TABLE bridge_outbox (
    event_id VARCHAR(80) PRIMARY KEY,
    event_type VARCHAR(120) NOT NULL,
    schema_version INTEGER NOT NULL,
    destination VARCHAR(200) NOT NULL,
    routing_key VARCHAR(200) NOT NULL,
    payload JSON NOT NULL,
    created_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error VARCHAR(1000) NULL
);
~~~

Exact JSON column types depend on the database (PostgreSQL `JSONB`, MySQL `JSON`, or validated text). Add statuses such as `PENDING`, `IN_FLIGHT`, `SENT`, `FAILED`, plus `next_attempt_at` and lock ownership so multiple relay workers never publish the same row uncontrollably.

Index unpublished rows, bound batch sizes, and use time-bounded leases/locks. If a worker dies while holding a lock, rows must be reclaimable once the lease times out.

## 23. Retries and Error Classification

Not every error warrants the same retry strategy.

| Error | Classification | Action |
|---|---|---|
| Kafka broker timeout | Transient | Retry with backoff |
| RabbitMQ connection reset | Transient | Reconnect and retry publish |
| RabbitMQ unroutable message | Config/topology | Return/alert; do not retry infinitely |
| Malformed JSON | Permanent data error | Error/DLQ and investigate producer |
| Unsupported `schemaVersion` | Contract mismatch | Quarantine, coordinate version |
| Missing `orderId` | Validation | DLQ or error store |
| DB deadlock | Transient | Bounded transaction retry |
| ACL/authentication denied | Config/security | Fail fast, alert |
| Quota/resource limit | Infrastructure | Bounded backoff and alert |

Retries must not block consumer threads indefinitely. Set attempt caps, backoff, timeouts, and total time budgets. Once retries exhaust, route the payload and metadata into a controlled error path/DLQ.

Never re-emit failed messages with a brand-new `eventId` to bypass deduplication. Event identity must stay stable across retries.

## 24. Kafka Input: Group, Partitions, and Offsets

The bridge needs a stable group such as `order-fulfillment-bridge`. Replicas of the same service share this group to divide partitions. Never share a group with another service if each service needs every event.

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        bridgeOrder-in-0:
          destination: orders.created
          group: order-fulfillment-bridge
          consumer:
            concurrency: 3
~~~

Concurrency must align with partition counts and downstream capacity. If a topic has 2 partitions, raising concurrency to 10 adds no useful parallelism within the same group.

Using `orderId` as the Kafka key keeps events for the same order in the same partition, preserving per-partition order. However, downstream RabbitMQ does not automatically preserve that order when multiple consumers or queues run concurrently. If business rules depend on ordering, design sharding or serial processing on the RabbitMQ consumer side.

Inspect offset commit policies alongside retries and transactions. Replays can introduce duplicates; never treat resetting offsets as a routine bridge troubleshooting fix.

## 25. RabbitMQ Output: Durability, Confirms, and Unroutable Messages

For RabbitMQ outputs to survive broker restarts, configure durable topology and appropriate message delivery modes. The RabbitMQ Binder has dedicated producer/consumer properties; check version docs before configuring durability, queue types, TTLs, DLXs, or delivery modes.

Foundational Spring Boot settings:

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
~~~

These properties enable Spring AMQP connection factory confirms and returns according to your Spring Boot version. With the RabbitMQ Binder, configure producer `confirmAckChannel` or `useConfirmHeader` (mutually exclusive) to receive publisher confirmations; the connection factory must enable confirms and the application must handle results. When `errorChannelEnabled` is active, `confirmAckChannel` can route positive acknowledgments to the registered channel. **Publisher confirms verify broker receipt of the publish—they do not guarantee the message routed to an intended queue.** Monitor returned messages or an alternate exchange for unroutable messages.

If no queue matches the routing key, mandatory returns or an alternate exchange must be configured and monitored. Never mark an outbox row `SENT` merely because the send call did not throw an exception when the contract requires broker confirmation.

## 26. DLQs and Error Paths on Both Sides

There are two independent failure classes:

- Kafka input cannot deserialize or the bridge handler fails.
- RabbitMQ output publish fails or is unroutable.

Do not lump them into a single DLQ without classifying source and stage. Error metadata should include:

~~~json
{
  "sourceEventId": "source-event-id",
  "stage": "RABBIT_PUBLISH",
  "errorCode": "UNROUTABLE",
  "attempt": 3,
  "failedAt": "2026-11-24T08:20:00Z",
  "destination": "orders.fulfillment",
  "routingKey": "fulfillment.requested"
}
~~~

Never store passwords, tokens, private keys, or unnecessary personal data in error records. Payloads may contain PII; enforce retention and access policies on DLQs.

Replays must preserve deterministic output `eventId`s. If mapping logic changes, record which mapping version the replay uses so older events do not silently morph into different content without audit trails.

## 27. Downstream RabbitMQ Consumer

Fulfillment Service consumes the event:

~~~java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class FulfillmentConsumerConfiguration {

    @Bean
    Consumer<EventEnvelope<FulfillmentRequested>> receiveFulfillment(
            FulfillmentService service) {
        return service::handle;
    }
}
~~~

~~~yaml
spring:
  cloud:
    function:
      definition: receiveFulfillment
    stream:
      bindings:
        receiveFulfillment-in-0:
          destination: orders.fulfillment
          group: fulfillment-service
          binder: rabbit
          content-type: application/json
      rabbit:
        bindings:
          receiveFulfillment-in-0:
            consumer:
              binding-routing-key: fulfillment.requested
~~~

The RabbitMQ Binder typically derives queue names from destination and group. If IaC pre-provisions queues, align `queueNameGroupOnly`/`bindQueue`/`declareExchange` accordingly. Never assume the queue name equals just the group name.

Downstream must record the inbox/idempotency key before executing side effects. On duplicates, return normally once prior completion is confirmed so the broker can ACK the message.

## 28. Ordering and Parallelism Across Both Brokers

Kafka guarantees ordering within a partition. RabbitMQ queues maintain enqueue order, yet with multiple consumers, prefetch, and concurrent execution, business completion order can diverge from arrival order.

Example:

~~~text
Kafka partition 0:
  OrderCreated A
  OrderUpdated A
  OrderCancelled A

Bridge publish:
  Rabbit queue:
    A-created
    A-updated
    A-cancelled
~~~

If the RabbitMQ consumer runs with concurrency 3, `A-cancelled` can finish before `A-created`. If business logic requires per-`orderId` ordering:

- Use stable keys/shards.
- Route events for the same `orderId` to the same queue/partition.
- Ensure a single consumer processes sequentially per shard or enforce sequence/version checks.
- Use optimistic locking or aggregate versions in the database.
- Reject or defer out-of-order events with a replay mechanism.

Never assume a routing key alone guarantees ordering when an exchange routes the same key to a queue whose consumer concurrency exceeds one.

## 29. Security and Access Control

The bridge requires distinct permissions on each broker:

| Component | Recommended least privilege |
|---|---|
| Kafka bridge principal | Read `orders.created`, join `order-fulfillment-bridge`, commit offsets |
| Rabbit bridge principal | Write exchange `orders.fulfillment` and confirm/return permissions |
| Rabbit fulfillment principal | Read fulfillment group queue, ack/reject |
| Platform provisioner | Create topics/exchanges/queues/bindings within scope |

Use TLS on both brokers. Kafka can use SASL/SCRAM or mTLS; RabbitMQ uses TLS and per-vhost users. Never commit production credentials in `application.yml` in Git.

If the binder auto-provisions, it needs create/describe permissions. If infrastructure pre-provisions resources, switch to verify-only and minimize runtime privileges. Never grant cluster-admin rights to the bridge merely to bypass provisioning errors.

## 30. End-to-End Observability

Logs and traces should answer:

- What is the source event ID?
- What is the output event ID?
- What is the correlation ID?
- Which stage is the bridge in?
- Which source Kafka topic/partition/offset?
- Which target RabbitMQ exchange/routing key?
- Was the publish confirmed or returned?
- What is the retry attempt count and last error?

Recommended metrics:

| Metric | Meaning |
|---|---|
| `bridge_events_received_total` | Events read from Kafka |
| `bridge_events_validated_total` | Validated events |
| `bridge_events_rejected_total` | Contract-violating events |
| `bridge_publish_success_total` | RabbitMQ publishes confirmed per criteria |
| `bridge_publish_failure_total` | Failed publishes |
| `bridge_unroutable_total` | Unroutable RabbitMQ messages |
| `bridge_processing_duration` | Bridge processing latency |
| `kafka_consumer_lag` | Ability to keep up with Kafka |
| `bridge_outbox_pending` | Unpublished outbox rows |
| `bridge_outbox_oldest_age` | Age of oldest pending row |
| `fulfillment_duplicate_total` | Duplicates blocked by idempotency |

Never use `eventId`, `orderId`, or `customerId` as unbounded metric labels because cardinality explodes. Put IDs in structured logs and traces; use `binder`, `destination`, `errorCode`, and `environment` on metrics.

## 31. Unit Testing the Mapper and Contract

Test mapping without a broker:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;

import org.junit.jupiter.api.Test;

class FulfillmentMapperTest {

    @Test
    void mapsOrderAndKeepsCausationAndCorrelation() {
        Clock clock = Clock.fixed(
            Instant.parse("2026-11-24T08:15:31Z"),
            ZoneOffset.UTC
        );

        FulfillmentMapper mapper = new FulfillmentMapper(clock);

        var order = new OrderCreated(
            "ORD-1042",
            "CUS-882",
            "VND",
            259900,
            List.of(new OrderItem("SKU-CHAIR-01", 1, 259900))
        );

        var source = new EventEnvelope<>(
            "source-event-1042",
            "OrderCreated",
            1,
            Instant.parse("2026-11-24T08:15:30Z"),
            "order-service",
            "checkout-7f13",
            null,
            null,
            order
        );

        var output = mapper.map(source);

        assertThat(output.eventType()).isEqualTo("FulfillmentRequested");
        assertThat(output.schemaVersion()).isEqualTo(1);
        assertThat(output.causationId()).isEqualTo(source.eventId());
        assertThat(output.correlationId()).isEqualTo(source.correlationId());
        assertThat(output.eventId()).isEqualTo(
            mapper.map(source).eventId()
        );
        assertThat(output.payload().orderId()).isEqualTo("ORD-1042");
    }
}
~~~

Beyond happy paths, test null payloads, missing `eventId`, unsupported schema versions, negative totals, zero item quantities, and empty item lists.

## 32. JSON Contract Testing

Serialize the envelope and assert required fields:

~~~java
@Test
void serializesStableEventContract() throws Exception {
    String json = objectMapper.writeValueAsString(envelope);

    JsonNode root = objectMapper.readTree(json);

    assertThat(root.path("eventId").asText()).isNotBlank();
    assertThat(root.path("eventType").asText())
        .isEqualTo("OrderCreated");
    assertThat(root.path("schemaVersion").asInt()).isEqualTo(1);
    assertThat(root.path("payload").path("orderId").asText())
        .isEqualTo("ORD-1042");
}
~~~

Retain representative JSON fixtures for each schema version to verify newer consumers read older events. When producers add optional fields, test backward compatibility. When breaking changes occur, verify version routing or migration logic.

## 33. Integration Testing with Real Kafka and RabbitMQ

Use Testcontainers to launch both brokers in the same test. With Testcontainers 2.x, the modules are `kafka` and `rabbitmq`; imports/packages may differ in Testcontainers 1.x. Keep BOM/versions consistent with your project's dependency management.

~~~xml
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>testcontainers-junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>testcontainers-kafka</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>testcontainers-rabbitmq</artifactId>
    <scope>test</scope>
</dependency>
~~~

Example test setup:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.kafka.KafkaContainer;
import org.testcontainers.rabbitmq.RabbitMQContainer;
import org.testcontainers.utility.DockerImageName;

import java.nio.charset.StandardCharsets;
import java.util.Properties;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.Producer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.serialization.StringSerializer;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@SpringBootTest
class KafkaRabbitBridgeIT {

    @Container
    static final KafkaContainer kafka =
        new KafkaContainer(DockerImageName.parse("apache/kafka-native:3.8.0"));

    @Container
    static final RabbitMQContainer rabbit =
        new RabbitMQContainer(DockerImageName.parse("rabbitmq:4.0-management"));

    @Autowired
    RabbitTemplate rabbitTemplate;

    @DynamicPropertySource
    static void brokerProperties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.cloud.stream.kafka.binder.brokers",
            kafka::getBootstrapServers
        );
        registry.add("spring.rabbitmq.host", rabbit::getHost);
        registry.add("spring.rabbitmq.port", rabbit::getAmqpPort);
        registry.add("spring.rabbitmq.username", rabbit::getAdminUsername);
        registry.add("spring.rabbitmq.password", rabbit::getAdminPassword);
    }

    @Test
    void forwardsOrderCreatedToRabbitFulfillmentQueue() throws Exception {
        String json = """
            {
              "eventId": "source-event-1042",
              "eventType": "OrderCreated",
              "schemaVersion": 1,
              "occurredAt": "2026-11-24T08:15:30Z",
              "producer": "order-service",
              "correlationId": "checkout-7f13",
              "causationId": null,
              "traceparent": null,
              "payload": {
                "orderId": "ORD-1042",
                "customerId": "CUS-882",
                "currency": "VND",
                "totalMinor": 259900,
                "items": [
                  {"sku": "SKU-CHAIR-01", "quantity": 1, "unitPriceMinor": 259900}
                ]
              }
            }
            """;

        Properties properties = new Properties();
        properties.put(
            ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
            kafka.getBootstrapServers()
        );
        properties.put(
            ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class.getName()
        );
        properties.put(
            ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class.getName()
        );

        try (Producer<String, String> producer = new KafkaProducer<>(properties)) {
            producer.send(
                new ProducerRecord<>("orders.created", "ORD-1042", json)
            ).get(10, TimeUnit.SECONDS);
        }

        Message message = rabbitTemplate.receive(
            "orders.fulfillment.fulfillment-service",
            10_000
        );
        assertThat(message).isNotNull();

        String output = new String(message.getBody(), StandardCharsets.UTF_8);
        assertThat(output).contains("FulfillmentRequested");
        assertThat(output).contains("source-event-1042");
        assertThat(output).contains("checkout-7f13");
        assertThat(output).contains("ORD-1042");
    }
}
~~~

This example uses a Kafka Producer to send a JSON string keyed by `orderId`, then `RabbitTemplate` reads from the queue provisioned by `required-groups`. In larger suites, use Awaitility and deserialize output into DTOs to assert individual fields. Timeouts on producer sends and queue receives ensure bounded failure if the bridge drops messages.

Test configuration must select real binders for each binding. If the Spring Integration Test Binder sits on the test classpath and overrides the middleware binders, tests can pass without ever exercising Kafka or RabbitMQ. Separate test source sets or modules if needed.

## 34. Key End-to-End Assertions

For a single source event, tests should verify:

1. Kafka producer sends the record to `orders.created`.
2. Bridge consumer group receives the record.
3. Function executes and maps accurately.
4. RabbitMQ exchange `orders.fulfillment` receives the output.
5. Routing key `fulfillment.requested` routes to the fulfillment queue.
6. Output envelope has `eventType` `FulfillmentRequested` and `schemaVersion` 1.
7. `causationId` equals input `eventId`.
8. `correlationId` is preserved.
9. Output `eventId` stays deterministic when the same input is reprocessed.
10. Fulfillment consumer persists the idempotency key.
11. Duplicate inputs do not create a second fulfillment.
12. Failing messages enter an observable error path.

Never assert solely that a queue contains one message. Inspect payload and headers. Queues may contain leftover messages from earlier tests if topology is not isolated.

## 35. Testing the Duplicate Window

A reliability test should simulate:

~~~text
1. Bridge receives Kafka event E.
2. RabbitMQ receives output E2.
3. Bridge stops before Kafka offsets are committed.
4. Bridge restarts.
5. Kafka redelivers E.
6. Bridge re-emits E2 with the same eventId.
7. Fulfillment inbox detects the duplicate.
8. Only one business fulfillment is created.
~~~

In tests, inject a failure right after output publish succeeds or before the handler finishes. Use dedicated test hooks for fault injection; never simulate crashes by killing production environments.

When using an outbox, simulate a crash after publishing but before marking `SENT`. The relay retries, and downstream idempotency ensures side effects run only once.

## 36. Failure Matrix for the Bridge

| Failure | Expected result | What to check |
|---|---|---|
| Kafka temporarily down | Consumer reconnects; lag climbs | Reconnects, lag, retries |
| RabbitMQ temporarily down | Output is not marked complete; retry/outbox holds it | Publish failures, outbox pending |
| RabbitMQ exchange exists with no matching queue | Unroutable message detected | Returns/alternate exchange |
| Invalid input JSON | Bad output is never published | Validation errors, DLQ |
| Unsupported new schema version | Quarantined or routed to DLQ | Version metrics |
| Crash after RabbitMQ publish | Possible duplicate on Kafka redelivery | Deterministic ID, inbox |
| Crash before RabbitMQ publish | Input retried if unacknowledged | Offset/ack policy |
| Fulfillment consumer crashes after side effect | Message may redeliver | Downstream idempotency |
| Kafka rebalance | In-flight messages may redeliver | Graceful shutdown, idempotency |
| RabbitMQ queue deleted | Publishes become unroutable | Provisioning/`required-groups` |

## 37. Runbook When the Bridge Stops Forwarding Messages

Follow in order:

1. Check that the Kafka input binding is `STARTED`.
2. Verify cluster/topic `orders.created`.
3. Check group `order-fulfillment-bridge`, member assignments, and lag.
4. Verify incoming records have `eventId` and key.
5. Inspect function validation and mapping logs.
6. Check RabbitMQ endpoint, vhost, and exchange `orders.fulfillment`.
7. Check fulfillment group queue and binding key.
8. Inspect publisher confirms/returns and error paths.
9. Check retry/DLQ or outbox pending rows.
10. Inspect downstream consumer and idempotency tables.

Never reset Kafka offsets or purge RabbitMQ queues just to "see if it starts working." Before replaying, record source offsets, output event IDs, and already-completed side effects.

## 38. Deployment and Operations

Deployment steps:

- Provision Kafka topics, partitions, retention, and ACLs.
- Provision RabbitMQ exchanges, durable queues, bindings, and DLQs per policy.
- Issue dedicated credentials for the bridge.
- Configure TLS/SASL and secrets via external configuration.
- Set a stable group and concurrency matched to partitions.
- Configure bounded timeouts and retries.
- Decouple readiness/liveness probes from temporary broker outages.
- Enable metrics, tracing, and structured logging.
- Run contract tests and broker integration tests before rollout.
- Deploy via canary or rolling updates.
- Monitor Kafka lag, RabbitMQ queue depth, publish failures, outbox age, and DLQs.
- Revoke old credentials only after confirming all instances run on new credentials.

The bridge should alert on sustained Kafka lag growth, RabbitMQ publish failures, unroutable counts, rising DLQs, and aging pending outbox rows. A Ready Pod alone does not prove the end-to-end pipeline is healthy.

## 39. Architectural Decisions to Record in ADRs

Before production, document:

| Decision | Question to answer |
|---|---|
| Event identity | How are output IDs generated deterministically? |
| Schema ownership | Who owns and reviews event contracts? |
| Compatibility | How long are older schema versions supported? |
| Kafka group | Which group belongs exclusively to the bridge? |
| Partition key | Which key preserves per-order ordering? |
| RabbitMQ topology | Exchange, queue, routing key, and group naming? |
| Delivery guarantee | At-most-once, at-least-once, or outbox-backed? |
| Duplicate handling | Where do inbox/idempotency keys live? |
| Error policy | How many retries, and which errors go to DLQ? |
| Replay | Who is authorized to replay, with what tooling and audit trail? |
| Ownership | Who provisions and deletes topics/queues? |
| Security | What are the least-privilege principals and ACLs? |
| Observability | How are event IDs and correlation traced? |

Never use the phrase "exactly-once" without scoping it. Kafka transactions can support exactly-once within Kafka read-process-write pipelines when properly configured; they do not automatically form an atomic transaction with RabbitMQ and a database.

## 40. Acceptance Checklist

- [ ] Envelope includes `eventId`, `eventType`, `schemaVersion`, `occurredAt`, `producer`, `correlationId`, and `payload`.
- [ ] `OrderCreated` and `FulfillmentRequested` have explicit schemas and versions.
- [ ] Mapping preserves causation/correlation and generates deterministic output event IDs.
- [ ] Function definitions and input/output binding names are accurate.
- [ ] Input binder is Kafka; output binder is RabbitMQ.
- [ ] Kafka topic, group, partitions, and ACLs are verified.
- [ ] RabbitMQ exchange, queue, group, routing key, and ACLs are verified.
- [ ] Content type/JSON conversion and schema validation are tested.
- [ ] Producer confirms/returns are understood and monitored.
- [ ] Retries/DLQs are bounded and backed by a replay procedure.
- [ ] The duplicate window has been tested.
- [ ] Downstream idempotency uses a unique constraint.
- [ ] Outbox/inbox is implemented where higher durability is required.
- [ ] Testcontainers tests exercise real Kafka and RabbitMQ brokers.
- [ ] Metrics, traces, and logs do not leak sensitive data.
- [ ] Runbooks include safe investigation and rollback steps.

## 41. References

- [Spring Cloud Stream — Functional Binding Names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html): input/output binding conventions for `Supplier`, `Function`, and `Consumer`.
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html): destination, group, binder, content type, consumer, and producer properties.
- [Spring Cloud Stream — Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/index.html): Kafka topics, consumer groups, producers, offsets, and binder configuration.
- [Spring Cloud Stream — RabbitMQ Binder](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview.html): exchanges, queues, groups, routing, and producer/consumer properties.
- [Spring Cloud Stream — RabbitMQ Producer Properties](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/prod-props.html): `requiredGroups`, `bindingRoutingKey`, confirms, and `routingKey`.
- [Spring Cloud — Supported Versions](https://spring.io/projects/spring-cloud/): selecting release trains compatible with Spring Boot.
- [Spring Cloud Stream — Error Handling](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html): retries, error channels, and error handling.
- [Spring AMQP — Publisher Confirms and Returns](https://docs.spring.io/spring-amqp/reference/amqp/template.html): publish confirmations and returned messages.
- [Apache Kafka — Design](https://kafka.apache.org/documentation/#design): partitions, ordering, replication, and consumer semantics.
- [RabbitMQ — Exchanges](https://www.rabbitmq.com/docs/exchanges): direct, topic, fanout, and routing keys.
- [RabbitMQ — Publisher Confirms](https://www.rabbitmq.com/docs/confirms): broker confirms, consumer acknowledgments, and delivery semantics.
- [Testcontainers — Kafka](https://java.testcontainers.org/modules/kafka/): `KafkaContainer` for integration testing.
- [Testcontainers — RabbitMQ](https://java.testcontainers.org/modules/rabbitmq/): `RabbitMQContainer` for integration testing.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/): `traceparent` standard and propagation.

**Expected outcome:** Kafka and RabbitMQ can share a single event contract without forcing both brokers into identical routing models. Kafka groups and partitions manage source consumption, while RabbitMQ exchanges, queues, and routing keys manage downstream distribution. The bridge must preserve event identity and schemas, handle duplicates under at-least-once delivery, and employ inbox/outbox when zero-event-loss guarantees exceed what a direct function can provide.
