# Core Components of Spring for Apache Kafka

## 1. What is Spring for Apache Kafka?

Spring for Apache Kafka (often shortened to Spring Kafka) is a library for integrating Kafka into Spring applications. The library provides abstractions for sending records, receiving records, managing listeners, converting messages, handling errors, and managing transactions. The application still uses the Kafka client underneath; Spring Kafka organizes those components into beans that can be configured, dependency-injected, and tested in the familiar Spring way.

In the `SPRING_KAFKA_MESSAGING` module, the two most common entry points are `KafkaTemplate` for publishing events and `@KafkaListener` for consuming events. To understand how they work, it is necessary to understand the factories, listener containers, serializers/deserializers, and accompanying administrative components.

Spring Boot can auto-configure many beans based on dependencies and `spring.kafka.*`. When customization is needed, the application declares its own beans and wires them together through dependency injection.

## 2. Overall Architecture Picture

The components are divided into two main flows: the sending flow on the producer side and the receiving flow on the consumer side.

```text
Spring Application
│
├── Sending flow
│   Business service
│       │
│       ▼
│   KafkaTemplate
│       │
│       ▼
│   ProducerFactory ── creates/manages KafkaProducer
│       │
│       ▼
│   Serializer ── byte[] ──▶ Kafka broker / topic / partition
│
└── Receiving flow
    Kafka broker / topic / partition
        │
        ▼
    ConsumerFactory ── creates KafkaConsumer with Deserializer
        │
        ▼
    Listener container ── manages consumer and calls poll()
        │
        ▼
    KafkaConsumer returns record with deserialized key/value
        │
        ▼
    @KafkaListener ── business processing method

Supporting components: KafkaAdmin, NewTopic, MessageConverter,
CommonErrorHandler, KafkaTransactionManager, and observability.
```

Spring Kafka does not replace the broker. The broker remains responsible for storing records, partitions, replication, and consumer groups. Spring beans orchestrate creating Kafka clients, transferring data between the application model and Kafka, as well as managing the processing lifecycle.

## 3. Baseline Configuration and Spring Boot Auto-Configuration

When adding the Spring Kafka dependency or the corresponding Spring Boot starter, the application can configure connection properties in `application.yml`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      acks: all
      properties:
        enable.idempotence: true
    consumer:
      group-id: order-notification
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.example.orders.events
    listener:
      ack-mode: record
```

`bootstrap-servers` provides the broker addresses for clients to fetch metadata and connect to the appropriate brokers. Producer and consumer configurations are translated by Spring Boot into Kafka client configurations. `auto-offset-reset` only takes effect when the group does not yet have a valid committed offset (or the current offset is no longer valid); it does not automatically rewind a group that already has an offset.

Auto-configuration helps create default beans such as `ProducerFactory`, `KafkaTemplate`, `ConsumerFactory`, the listener container factory, and `KafkaAdmin` when the appropriate conditions are met. If declaring custom beans, you need to understand which default beans are still created and which ones are replaced by auto-configuration conditions. Avoid declaring multiple beans of the same type without specifying which bean is used.

## 4. Producer-Side Components

### ProducerFactory

`ProducerFactory<K, V>` is the abstraction for creating Kafka producers. The commonly used implementation is `DefaultKafkaProducerFactory`, which takes configurations such as brokers, serializers, acknowledgements, retries, and idempotence and creates `KafkaProducer` instances.

Applications typically do not create or close `KafkaProducer` themselves in each business method. `ProducerFactory` manages creating and reusing producers according to its mechanism, allowing services to share configuration and lifecycle managed by Spring.

### KafkaTemplate

`KafkaTemplate<K, V>` is the application-level API for sending messages. It accepts a topic, key, and value, and can additionally accept a partition, timestamp, or headers through overloads or a `ProducerRecord`.

```java
public record OrderCreated(
        String eventId,
        String orderId,
        BigDecimal total) {}

@Service
public class OrderEventPublisher {
    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {
        return kafkaTemplate.send("orders", event.orderId(), event);
    }
}
```

In the example, `orderId` is the key so that events for the same order are generally routed to the same partition according to the partitioner in use. `OrderCreated` is the value serialized into bytes before sending. `send` returns a `CompletableFuture` in modern Spring Kafka versions; the application should observe completion to know whether the record was acknowledged by the broker or failed to send.

`KafkaTemplate` also supports sending Spring Messaging `Message<?>`, sending via `ProducerRecord`, accessing send result metadata, and executing operations within a transaction. It is a convenient API, while producer creation and connection configuration are still handled by `ProducerFactory`.

### ProducerRecord and SendResult

`ProducerRecord<K, V>` represents a record to be sent, which can contain a topic, optional partition, timestamp, key, value, and headers. If no partition is specified, the partitioner chooses a partition based on the key or the configured partitioning policy.

`SendResult<K, V>` contains the sent record along with `RecordMetadata` returned by the broker, which includes the topic, partition, and offset. This metadata is useful for logging, tracing, or diagnostics. Do not use the offset as a global business ID because an offset only has meaning within a single partition.

## 5. Consumer-Side Components

### ConsumerFactory

`ConsumerFactory<K, V>` creates Kafka consumers configured with group ID, deserializers, commit, poll, and related properties. A common implementation is `DefaultKafkaConsumerFactory`.

Kafka consumer is not thread-safe. Spring Kafka therefore lets the listener container manage the consumer and execute polls on the appropriate thread, rather than having multiple business threads call a shared consumer object.

### @KafkaListener

`@KafkaListener` marks a method as a record-receiving endpoint. The annotation can declare topics, topic patterns, group ID, container factory, endpoint-level concurrency, batch listener, and other options.

```java
@Component
public class OrderCreatedListener {

    @KafkaListener(
            id = "order-created-listener",
            topics = "orders",
            groupId = "order-notification")
    public void onOrderCreated(OrderCreated event) {
        // Call business service to process the event.
        System.out.println("Received order: " + event.orderId());
    }
}
```

`KafkaListenerAnnotationBeanPostProcessor` detects the annotation at startup, creates the endpoint, and registers the corresponding listener container through `KafkaListenerEndpointRegistry`. When a record arrives, the container passes the data to the listener method after the Kafka client deserializes it and Spring performs the necessary payload conversion.

The listener method can also receive metadata such as key, topic, partition, offset, or headers via `@Header`, `@Headers`, and constants in `KafkaHeaders`. This is how to retrieve transport information without directly interacting with the Kafka consumer.

### Listener container

The listener container is the component that runs the poll loop, invokes the listener, handles errors, and manages offsets. Two common types are:

- `KafkaMessageListenerContainer`: manages a single Kafka consumer and one main processing thread for that consumer.
- `ConcurrentMessageListenerContainer`: creates and manages multiple child `KafkaMessageListenerContainer` instances to increase concurrency.

For example, a listener container factory can configure concurrency:

```java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    ordersKafkaListenerContainerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);
        return factory;
    }
}
```

To make a listener use this factory, specify the name in the annotation:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-notification",
        containerFactory = "ordersKafkaListenerContainerFactory")
public void onOrderCreated(OrderCreated event) {
    // Process event.
}
```

Concurrency is the number of consumers the container can create for an endpoint. Within the same consumer group, each partition at a given time is assigned to at most one consumer. Therefore, increasing concurrency beyond the number of assigned partitions does not increase the number of consumers doing useful reading; some consumers may receive no partitions. If parallel processing is needed, consider the number of partitions, the number of application instances, and the processing time per record.

### KafkaListenerEndpointRegistry

`KafkaListenerEndpointRegistry` manages the listener containers created from `@KafkaListener`. You can use the registry to look up containers by `id`, check status, or stop or start listeners for operational needs. These containers are normally managed through the registry rather than being declared as standalone container beans in the context.

Do not arbitrarily stop/start listeners from many places in the application. If dynamic control is needed, centralize the operations into a clear management component and handle cases where the container is not yet registered or is in the middle of starting up.

## 6. Serialization, Deserialization, and Message Conversion

Kafka stores bytes. The producer must turn keys/values into bytes using a serializer; the consumer uses a deserializer to convert bytes into data types the application can use.

Spring Kafka provides serializers/deserializers for common types and supports JSON through `JsonSerializer` and `JsonDeserializer`. Both sides need to agree on the schema, data types, and how types are identified. The trusted packages configuration of the JSON deserializer should be restricted to the necessary packages, avoiding trusting all packages in untrusted environments.

It is important to distinguish two conversion layers:

| Component | Role | Example |
|---|---|---|
| Serializer / Deserializer | Converts keys/values between objects and bytes for exchanging with Kafka | `StringSerializer`, `JsonSerializer`, `JsonDeserializer` |
| MessageConverter | Converts between Spring `Message<?>` / `ConsumerRecord` and application payload, headers | `MessagingMessageConverter`, `StringJsonMessageConverter` |

The deserializer operates at the Kafka client layer. The message converter operates at the Spring Messaging and listener adapter layer. The converter can map Kafka headers to Spring message headers, allowing the listener method to accept payload and metadata using convenient parameter types.

If producer and consumer use JSON, schema compatibility rules are needed when adding, renaming, or removing fields. Incompatible changes to event structure can cause older consumers to fail when reading new data, or vice versa. For multi-service systems, manage schema versions and establish compatibility policies before deployment.

## 7. KafkaAdmin and Topic Declaration

`KafkaAdmin` uses the Kafka Admin API to perform cluster administrative operations from a Spring application. An application can declare `NewTopic` beans; at startup, KafkaAdmin can create topics that do not yet exist with the requested configuration.

```java
@Configuration
public class KafkaTopicConfiguration {

    @Bean
    NewTopic ordersTopic() {
        return TopicBuilder.name("orders")
                .partitions(6)
                .replicas(3)
                .config(TopicConfig.MIN_IN_SYNC_REPLICAS_CONFIG, "2")
                .build();
    }
}
```

The example creates topic `orders` with 6 partitions, replication factor 3, and requires at least 2 replicas in the ISR when a producer writes with `acks=all`. The cluster must have enough brokers to satisfy the replication factor. If the topic already exists, the behavior for configuration changes depends on the operation and version; a `NewTopic` bean should not be treated as a way to automatically modify all configurations of a running topic.

In production environments, topics may be managed via a separate infrastructure process rather than having every application startup auto-create resources. Regardless of the approach used, verify the topic name, partitions, replication factor, retention, and ACLs.

## 8. Error Handling, Retry, and Dead-Letter

A listener can encounter business errors, data errors, timeouts, or dependent system failures. Spring Kafka provides error handler mechanisms to decide whether to retry, skip, recover, or route failed records to a dead-letter topic.

`CommonErrorHandler` is the error-handling abstraction of the listener container. `DefaultErrorHandler` supports retries with backoff and can be combined with `DeadLetterPublishingRecoverer` to publish unprocessable records to a dead-letter topic.

Example of configuring bounded retries and sending failed records to a DLT:

```java
@Configuration
public class KafkaErrorConfiguration {

    @Bean
    DefaultErrorHandler kafkaErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        var recoverer = new DeadLetterPublishingRecoverer(kafkaTemplate);
        var backOff = new FixedBackOff(1_000L, 2L);
        return new DefaultErrorHandler(recoverer, backOff);
    }
}
```

The configuration snippet illustrates two retry attempts after the initial processing attempt, spaced one second apart; after retries are exhausted, the recoverer sends the record to the DLT topic following the default routing rules or additionally configured rules. You must configure a serializer for the DLT compatible with both normal records and records with malformed payloads; otherwise, publishing to the DLT itself can fail.

Retry is suitable for transient errors. For invalid data errors, repeated retries usually do not help and can slow down the partition. Classify exceptions, configure backoff and retry limits, monitor the DLT, and build a process to inspect and replay records after resolving the root cause.

## 9. Offsets, Acknowledgements, and Transactions

The listener container manages offset commits according to `AckMode`. Common modes include:

- `RECORD`: commits the offset after the listener finishes processing each record.
- `BATCH`: commits the offset after processing a batch of polled records.
- `MANUAL` and `MANUAL_IMMEDIATE`: the application calls `Acknowledgment.acknowledge()` to explicitly acknowledge according to the rules of the mode.

Choosing an ack mode should be based on tolerance for duplicate processing, throughput, and how the listener handles errors. Committing the offset before completing business side effects can prevent a record from being re-read even though the business operation did not succeed. Committing after processing finishes can lead to record redelivery if the application stops abruptly before the commit; therefore, handlers should still be idempotent.

Spring Kafka supports Kafka transactions via `KafkaTransactionManager` and a producer factory configured with a transaction ID prefix. `KafkaTemplate` can send records within a transaction, and the listener container can participate in the transactional processing flow according to the corresponding configuration. This is useful when coordinating consume-transform-produce in Kafka with appropriate transactional guarantees.

Exactly-once in Kafka has a specific scope: it generally guarantees the read and write outcome across Kafka topics in a flow configured as transactional with consumers reading at the appropriate isolation level. If a listener updates a relational database or calls an external API, a Kafka transaction does not automatically create a shared ACID transaction with that system. When consistency between a database and events is required, consider Transactional Outbox, inbox, or idempotency mechanisms.

## 10. Supporting Components and Observability

Beyond the core components, Spring Kafka includes tools to help build a complete messaging flow:

| Component | Purpose |
|---|---|
| `KafkaOperations` | Abstract interface for Kafka send operations; `KafkaTemplate` is the common implementation |
| `Message<?>` and `KafkaHeaders` | Carries payload along with metadata such as topic, key, partition, offset, and reply topic |
| `ReplyingKafkaTemplate` | Supports the request-reply pattern over Kafka when the application genuinely needs to wait for a correlated response |
| `KafkaTransactionManager` | Manages transactions using a Kafka producer |
| `KafkaAdmin` | Performs administrative operations on Kafka topics and resources |
| Listener container events | Notifies about lifecycle and state events of the listener container |

In operations, monitor producer send failure/latency, consumer lag, number of processed records, retries, DLT, rebalances, and listener container state. Spring Kafka integrates with Spring's metrics/observation ecosystem; metric names and export formats depend on the Spring Boot version, Micrometer, and application configuration.

Logs should include event ID, topic, partition, and offset where appropriate to aid tracing. Avoid logging the full payload if it contains sensitive data. Across multiple services, a correlation ID or trace context in message headers helps connect processing steps into an observable flow.

## 11. A Complete Processing Flow

Suppose the Order Service emits `OrderCreated` and the Notification Service receives the event:

1. The business service creates an `OrderCreated` object and calls `KafkaTemplate`.
2. `KafkaTemplate` delegates the request to `ProducerFactory`; the producer serializes the key/value into bytes and sends them to the broker.
3. The broker writes the record to a partition; the send result returns metadata for the application to log or handle errors.
4. The consumer is created by `ConsumerFactory` and managed by the listener container.
5. The container polls records; the deserializer and message converter prepare the payload.
6. The listener adapter invokes the `@KafkaListener` method.
7. The method calls the business service, then the container handles any errors and commits the offset according to the ack mode.
8. If processing fails, the error handler decides whether to retry or route the record to the DLT.

Each component has a distinct responsibility. Separating responsibilities makes testing and configuration changes easier: you can swap the serializer without rewriting sending business logic, change the error handler without changing the listener, or increase concurrency without manually managing Kafka consumer threads.

## 12. Summary

- `ProducerFactory` creates Kafka producers; `KafkaTemplate` is the application API for sending records.
- `ConsumerFactory` creates Kafka consumers; the listener container manages polling, invoking listeners, and offsets.
- `@KafkaListener` declares record-receiving endpoints; `KafkaListenerEndpointRegistry` manages containers created from annotations.
- Serializers/deserializers convert bytes at the Kafka client layer; MessageConverter converts payloads and headers at the Spring Messaging layer.
- `KafkaAdmin` and `NewTopic` support declaring and administering topics.
- `CommonErrorHandler`, `DefaultErrorHandler`, and `DeadLetterPublishingRecoverer` support retries and dead-letter handling.
- `KafkaTransactionManager` supports Kafka transactions; consistency with databases/APIs outside Kafka requires additional design.

By understanding the relationships among these beans, you can read Spring Kafka configurations, trace the send/receive flow, and choose the right component to customize serialization, concurrency, retries, offsets, or transactions for a reliable messaging application.
