# Distinguishing Application-Created Headers from Broker-Provided Metadata

## Objectives

A message in Spring Cloud Stream can carry a payload along with many headers. Some headers are intentionally created by the application to describe the event or link processing steps; others are provided by the broker or binder when the message is sent, stored, or delivered to a consumer. Additionally, Spring Messaging includes framework-generated metadata, such as the `Message` object's ID and timestamp.

These three groups have different origins and purposes. Treating every header as application data can inadvertently couple code to Kafka, RabbitMQ, or Pulsar; copying delivery metadata onto a new message can cause the application to re-emit values that are no longer accurate. This lesson helps identify each group and place them at the proper boundary.

After this lesson, you will be able to:

- Distinguish application headers, broker-provided metadata, and framework metadata.
- Create custom headers for outbound messages using Spring Messaging.
- Read delivery metadata in an inbound adapter according to the active binder.
- Distinguish producer-supplied routing keys/record keys from broker-assigned partition or delivery metadata.
- Select which headers to forward and avoid copying stale metadata.
- Test header mapping on Spring Cloud Stream and the target broker.

## 1. A Message Has a Payload and Headers

Spring Messaging defines `Message<T>` as consisting of a payload of type `T` and a set of headers:

```java
public record OrderCreated(
        String eventId,
        String orderId,
        BigDecimal total
) {}

Message<OrderCreated> message = MessageBuilder
        .withPayload(new OrderCreated(
                "evt-100", "order-42", new BigDecimal("125.50")
        ))
        .setHeader("correlationId", "corr-900")
        .setHeader("tenantId", "tenant-a")
        .build();
```

In this example:

- The payload is `OrderCreated`, containing the business data of the event.
- `correlationId` and `tenantId` are custom headers created by the application.
- Spring Messaging creates and manages certain metadata on the `Message` object, such as its ID and timestamp.

When a message passes through Spring Cloud Stream, the binder converts between Spring's abstraction and the broker protocol. A message on the consumer side can therefore contain the deserialized payload, mapped custom headers, and delivery metadata injected by the binder. The exact set of headers depends on the broker, binder, version, and configuration.

Header origins can be divided into three groups:

| Group | Who creates or assigns it? | Examples | Usage |
|---|---|---|---|
| Application headers | Application code or producer per the event contract | `eventId`, `correlationId`, `tenantId`, `eventType` | Carry application context across processing steps |
| Broker-provided metadata | Broker or binder upon send/receive | Topic, partition, offset, queue, received routing key, delivery tag, broker message ID | Observe delivery, routing, diagnostics, and edge integration tasks |
| Framework metadata | Spring Messaging when constructing the Message object | Spring Message ID, timestamp | Track the Message object's lifecycle within framework scope |

Not every header appearing in `MessageHeaders` is part of the business contract. Identify its origin before deciding to persist, forward, or make decisions from a header.

## 2. Application Headers: Application-Defined Metadata

Application headers carry information meaningful to collaborating application components. For example:

- `eventId`: stable identifier of an event for deduplication and reconciliation.
- `correlationId`: links messages or operations within the same business flow.
- `causationId`: identifier of the event or command that directly caused the current event.
- `tenantId`: tenant scope if the application uses a multi-tenant model.
- `eventType` or `schemaVersion`: describes the event type and contract version when the architecture chooses to place them in headers.

These names are system-defined conventions, not headers automatically provided by every broker. The development team must agree on names, data types, meanings, mandatory vs. optional rules, and compatibility policies.

### Creating Application Headers on Outbound Messages

Use `MessageBuilder` to create a message and add headers belonging to the application contract:

```java
@Bean
Supplier<Message<OrderCreated>> orderEvents(OrderEventSource source) {
    return () -> {
        OrderCreated event = source.nextEvent();

        return MessageBuilder
                .withPayload(event)
                .setHeader("eventId", event.eventId())
                .setHeader("correlationId", source.correlationId())
                .setHeader("eventType", "order.created")
                .build();
    };
}
```

The `Supplier` builds the message on the application side. The binder takes the message and sends the payload along with supported headers to the broker. The broker may add its own metadata upon acceptance or when delivering the message to a consumer.

Never pre-populate values that the broker is responsible for assigning, such as a Kafka offset, actual chosen partition, RabbitMQ delivery tag, or Pulsar broker-generated message ID. Those values only have meaning after the broker processes the message.

### Setting Headers in a Function

A `Function` can accept a payload and construct an output message with new application headers:

```java
@Bean
Function<OrderCreated, Message<OrderAccepted>> acceptOrder(
        OrderService service) {
    return event -> {
        OrderAccepted accepted = service.accept(event);

        return MessageBuilder
                .withPayload(accepted)
                .setHeader("eventId", accepted.eventId())
                .setHeader("correlationId", event.eventId())
                .setHeader("eventType", "order.accepted")
                .build();
    };
}
```

In a real system, `correlationId` is typically taken from the validated input context or created at the start of the flow. The example above illustrates creating headers; do not assume the input event's event ID is always the correlation ID.

### Header or Payload?

Not all metadata belongs in headers. Place information in the payload if it is an essential part of the business event, needs long-term storage, replay, or must remain independent of transport. Headers are suited for coordination metadata and agreed transport context.

For example, if `eventId` is the canonical event identifier, the team may place it in the payload, header, or both under a clear contract. If it appears in both places, designate one as authoritative and verify consistency. Do not let producers and consumers pick different places to read from arbitrarily.

## 3. Broker-Provided Metadata: Information Assigned by the Messaging System

Brokers store and deliver messages using their own mechanisms. During that process, the broker or binder can provide metadata so consumers know where a message came from and its delivery state.

Such metadata typically has these characteristics:

- Assigned or determined by the broker/binder, not chosen arbitrarily by the application.
- May exist only when the message is received or within one specific delivery attempt.
- Carries protocol- and binder-specific semantics.
- Not guaranteed to stay intact when a message is forwarded to another destination.
- Usually belongs only in adapters, logs, metrics, or operational layers.

### Kafka

Kafka stores records in topics and partitions. When a consumer reads a record, the binder can provide metadata such as:

| Metadata | Meaning |
|---|---|
| Received topic | Topic containing the record |
| Received partition | Partition where the broker stored the record |
| Offset | Position of the record within the partition |
| Receive/record timestamp | Timestamp associated with the record per timestamp policy |
| Record key | Key sent by the producer and stored by the broker with the record |

Partition and offset are positional details determined by Kafka. The record key is typically provided by the producer; it may be used to choose a partition, though it is not the partition number itself. Consumer group offset represents committed consumption progress, distinct from the current record's offset.

In the Kafka binder, an adapter can read inbound metadata using Kafka-specific constants, for example:

```java
import org.springframework.kafka.support.KafkaHeaders;

@Bean
Consumer<Message<OrderCreated>> inspectKafkaRecord(
        OrderService service) {
    return message -> {
        OrderCreated event = message.getPayload();

        String topic = message.getHeaders()
                .get(KafkaHeaders.RECEIVED_TOPIC, String.class);
        Integer partition = message.getHeaders()
                .get(KafkaHeaders.RECEIVED_PARTITION, Integer.class);
        Long offset = message.getHeaders()
                .get(KafkaHeaders.OFFSET, Long.class);

        service.handle(event);

        // topic, partition, and offset are appropriate for logs/metrics in the adapter.
    };
}
```

Mapped header names and types can depend on the Kafka binder and Spring Kafka versions. Use only constants available in your application's dependency version; verify actual headers via integration tests. Never inject topic, partition, or offset into business entities just to record technical details of one delivery.

### RabbitMQ

RabbitMQ routes messages via exchanges and queues. Consumers can receive metadata such as:

| Metadata | Meaning |
|---|---|
| Received queue | Queue from which the consumer received the message |
| Received routing key | Routing key used during routing |
| Delivery tag | Delivery identifier on the channel, used for acknowledgment operations |
| Redelivered | Indicator that the message was previously delivered |
| Exchange | Exchange associated with the message |

The routing key is normally specified by the producer when publishing and used by the broker for routing; the received queue and delivery tag belong to delivery. A delivery tag is channel-scoped and is not a business event ID. Never copy it onto a new message or reuse it when publishing to another queue.

In the Rabbit binder, specific headers can be mapped from Spring AMQP. Adapters may read corresponding constants, such as `AmqpHeaders.CONSUMER_QUEUE`, `AmqpHeaders.RECEIVED_ROUTING_KEY`, or `AmqpHeaders.DELIVERY_TAG`, if exposed by the binder/version in use. Check documentation and actual data types before relying on them.

### Pulsar

A Pulsar message can carry a key, properties, event time, and broker-managed metadata. Consumers also operate within a subscription; acknowledgment and redelivery behavior depend on the subscription type and configuration.

Observable details include:

- Topic and partition associated with the message.
- Pulsar-generated Message ID.
- Publish time and event time.
- Producer-set key or properties.
- Subscription-scoped redelivery/acknowledgment context.

Not every Pulsar client field is exposed as a Spring Message header in every binder version. Check the binder documentation and inspect actual messages. If Pulsar-specific metadata is required, keep reading it inside the adapter so use cases do not depend on Pulsar APIs.

## 4. Distinguishing Producer-Set Values from Broker-Assigned Values

Some fields look similar but originate differently. Distinguishing them accurately prevents bugs during partitioning or replay.

| Field | Common origin | Role |
|---|---|---|
| Kafka record key | Producer | Input to the partitioner and record key |
| Kafka partition | Broker/partitioner when record is written | Storage location |
| Kafka offset | Broker | Position of the record within the partition |
| Rabbit routing key | Producer | Routing instruction to the exchange |
| Rabbit received queue | Broker/topology | Actual queue delivering the message to the consumer |
| Rabbit delivery tag | Broker/channel | Identifies delivery for ack/nack |
| Pulsar message key | Producer | Message key, which can influence routing/partitioning |
| Pulsar message ID | Broker | Identifies message position in Pulsar |
| Application event ID | Application/producer per contract | Stable business identifier across retries and replays |

For example: an application sends a Kafka record with key `order-42`. The Kafka partitioner picks partition 3 and the broker assigns offset 128. The key is data sent by the producer; partition and offset are metadata of the persisted record. When a consumer reads the record, the binder may expose all three in the message context, yet they are not interchangeable.

Similarly, a RabbitMQ producer chooses routing key `orders.created`; the exchange routes to the matching queue. The delivery tag is assigned only when the message is delivered over a channel to the consumer. When publishing a new message, the old delivery tag no longer applies.

## 5. Reading Metadata in the Adapter, Keeping Business Core Independent

The inbound adapter is the right place to read broker metadata. The adapter can use metadata for logs, metrics, tracing, or pass an application-meaningful value into a command after validation.

Example separating business logic from metadata observation:

```java
@Bean
Consumer<Message<OrderCreated>> orderCreated(
        OrderCreatedUseCase useCase,
        MessageObservation observation) {
    return message -> {
        OrderCreated event = message.getPayload();

        String correlationId = message.getHeaders()
                .get("correlationId", String.class);

        observation.recordReceived(
                event.eventId(),
                correlationId,
                message.getHeaders()
        );

        useCase.handle(new CreateOrderCommand(
                event.eventId(),
                event.orderId(),
                event.total()
        ));
    };
}
```

In this example, `MessageObservation` is an adapter supporting logging/metrics; it can extract binder-specific broker metadata. The use case receives a business command and needs no knowledge of topics, offsets, queues, or delivery tags.

If business logic needs a value such as tenant ID or correlation ID, the adapter must validate that value and pass it as an explicit field in the command or execution context. Never pass raw `MessageHeaders` into an application service, as doing so couples the application to transport abstractions and risks relying on unstable metadata.

A simple rule of thumb:

- Metadata for observation or diagnostics: keep in the adapter/telemetry.
- Validated metadata with business meaning: convert into explicit command fields.
- Metadata meaningful only for ack, offset, partition, or delivery: keep in the adapter and binder.
- Data needed for replay or long-term storage: place in the payload or a data store with a clear contract.

## 6. Selecting Headers When Emitting Downstream Messages

When a consumer receives a message and emits a new message, do not unconditionally copy all input headers. The input message may contain metadata from the broker, framework, or prior delivery attempt.

Example creating an output message with only the application headers to forward:

```java
@Bean
Function<Message<OrderCreated>, Message<OrderAccepted>> acceptOrder(
        OrderService service) {
    return input -> {
        OrderCreated event = input.getPayload();
        OrderAccepted accepted = service.accept(event);

        String correlationId = input.getHeaders()
                .get("correlationId", String.class);

        MessageBuilder<OrderAccepted> builder =
                MessageBuilder.withPayload(accepted)
                        .setHeader("eventId", accepted.eventId())
                        .setHeader("eventType", "order.accepted");

        if (correlationId != null) {
            builder.setHeader("correlationId", correlationId);
        }

        return builder.build();
    };
}
```

This example creates a new message using a header allowlist. It does not carry over partition, offset, delivery tag, received queue, or framework-generated message ID from the input.

You can use `MessageBuilder.fromMessage(input)` to start from the current message, provided you actively remove stale metadata and inspect every retained header. For flows crossing multiple brokers, creating a new message with an explicit list of allowed headers is usually easier to control.

Never define custom headers whose names collide with headers reserved by the binder or framework. If you need to pass custom metadata, use application-managed names and document the contract clearly. Avoid generic names like `id`, `timestamp`, or `partition` if they might conflict with framework or broker metadata.

## 7. Headers and Security

Headers can come from external producers or be forwarded by brokers. Therefore, never treat custom headers as trustworthy proof.

For example, a producer might send `tenantId=tenant-a`. A consumer must not rely solely on that value to grant access to `tenant-a`'s data. The adapter must verify the sender, signature, or identity claims according to the system's security mechanisms. Only after verification should the application receive the corresponding tenant context.

Principles to follow:

- Validate format, length, and allowed value sets for custom headers.
- Authenticate tenant, actor, or scope before using them for data access.
- Never place access tokens, passwords, session IDs, or secrets into headers.
- Do not dump all headers into logs if sensitive data could be present.
- Never use broker metadata such as partition, delivery tag, or message ID to authenticate senders.
- Restrict the list of headers forwarded across service boundaries.

Broker metadata is not always reliable outside its own context either. For instance, a delivery tag is meaningful only within a specific channel; an offset only identifies a position within a partition; a broker message ID does not replace a business ID.

## 8. Header Mapping Across Spring Cloud Stream and Binders

Spring Cloud Stream provides a common abstraction, while brokers differ in how they store and transmit metadata. Binders handle mapping headers between Spring Messages and broker-native messages.

When designing a contract, verify:

1. Which custom headers does the binder transmit to the broker?
2. Which headers are mapped back upon receipt?
3. Do values retain their data types or get converted to strings/bytes?
4. Which headers are native metadata assigned by the broker?
5. Are there limits on header names, sizes, or types?
6. Which headers are dropped, renamed, or reserved by the binder?
7. Are native headers or embedded headers used in that configuration?

Some binders support native broker headers; certain scenarios or binders may use embedded headers. Configuration and defaults depend on the binder and version. Never assume a custom header travels intact simply because it exists in the `Message` object on the producer side.

In Kafka, native record headers are the common mechanism for carrying metadata. In RabbitMQ, message properties and headers follow AMQP/client type capabilities. In Pulsar, properties and keys have their own rules. Binders may normalize part of that metadata into Spring headers, but not every native field maps identically.

If a header is mandatory for the application contract, write a contract test against the target binder to prove it is sent and received accurately. If a header is only for internal logging, do not require every broker to support it as part of the business contract.

## 9. Testing Header Origins and Behavior

Test the three groups separately:

### Unit Tests for Application Headers

Create a message with `MessageBuilder` and verify custom headers are set properly:

```java
@Test
void shouldCreateApplicationHeaders() {
    OrderCreated event = new OrderCreated(
            "evt-100", "order-42", new BigDecimal("125.50")
    );

    Message<OrderCreated> message = MessageBuilder
            .withPayload(event)
            .setHeader("eventId", event.eventId())
            .setHeader("correlationId", "corr-900")
            .build();

    assertEquals("evt-100", message.getHeaders().get("eventId"));
    assertEquals("corr-900", message.getHeaders().get("correlationId"));
}
```

This test verifies application message-building logic; it does not prove the broker stored or transmitted those headers.

### Integration Tests for Broker Metadata

Use the Test Binder to check mapping at the Spring Cloud Stream level, then use Testcontainers or an appropriate test broker to verify real metadata. For each binder, verify the values your application expects to read, for example:

- Kafka: topic, partition, offset, and record key.
- RabbitMQ: received queue, received routing key, and delivery context if exposed.
- Pulsar: topic, message ID, key, or binder-supported properties.

Do not hardcode assumptions that headers share identical names and types across all binders. Test adapters separately per binder if code reads native metadata.

### Tests When Forwarding Messages

Create an input message containing both application headers and simulated metadata, then invoke the adapter to build an output message. Verify:

- Application headers slated for retention are forwarded.
- Delivery metadata from the input message does not appear on the new message.
- Invalid headers are rejected or stripped per policy.
- Payload and event ID remain consistent.
- The target binder receives the exact custom headers allowed by the contract.

## 10. Common Mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| Using broker message ID as business event ID | ID changes upon republish or across different brokers | Generate a stable event ID within the application |
| Copying offset/partition/delivery tag onto a new message | Stale metadata is inaccurate for the new emission | Build a new message and retain only needed application headers |
| Treating routing key as partition | Confuses routing instruction with storage location | Distinguish producer-set keys from broker-selected partitions |
| Assuming all custom headers cross binders intact | Consumer fails to receive expected metadata | Test header mapping on the target binder |
| Using unverified tenant header for database access | Risk of accessing the wrong tenant's data | Verify origin and value at the adapter/security boundary |
| Passing raw MessageHeaders into the domain | Domain couples to framework and transport metadata | Convert needed values into explicit command/context fields |
| Dumping all headers into logs | May expose tokens or sensitive data | Select a safe allowlist of log fields |

## Conclusion

Application headers are defined by the application to carry context such as event ID, correlation ID, or tenant ID. Broker-provided metadata describes where messages are stored and how they are delivered, such as topic, partition, offset, queue, or delivery tag. Spring Messaging also maintains its own `Message` object metadata such as ID and timestamp.

In Spring Cloud Stream, read broker metadata in the adapter, validate custom headers arriving from external sources, and forward only required application headers. Never reuse metadata from a previous delivery when constructing a new message. Because Kafka, RabbitMQ, and Pulsar represent metadata differently, test header mapping on the exact binder and broker you deploy.
