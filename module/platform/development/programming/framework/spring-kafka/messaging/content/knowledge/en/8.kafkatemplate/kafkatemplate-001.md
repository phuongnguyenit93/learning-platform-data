# The Role of KafkaTemplate

In a Spring Kafka application, `KafkaTemplate` is the producer-side component that helps business code send records to Kafka consistently with the Spring ecosystem. A service simply injects the template and calls the `send` method; Spring Kafka coordinates with `ProducerFactory`, the Kafka producer, serializers, the partitioner, and the declared configuration to perform the send.

`KafkaTemplate` acts as a bridge between Spring application code and the Kafka producer API. It reduces boilerplate producer management code, provides overloads for sending records, supports asynchronous callbacks, integrates with transactions, and exposes access to several advanced operations when needed. However, calling `send` does not mean the consumer has successfully processed the business logic; producer and consumer are two separate stages in the messaging flow.

## 1. Where does KafkaTemplate sit in the architecture?

A typical event-publishing flow can be visualized as follows:

```text
Controller / Application Service
             |
             v
      KafkaTemplate<K, V>
             |
             v
       ProducerFactory
             |
             v
       KafkaProducer
             |
             v
 Serializer -> Partitioner -> Kafka broker
```

Role of each component:

| Component | Responsibility |
| --- | --- |
| Application service | Decides when to emit an event and what business data needs to be sent |
| `KafkaTemplate<K, V>` | Provides the Spring API to create and send records, receive results, handle callbacks, and coordinate transactions |
| `ProducerFactory<K, V>` | Creates and manages the lifecycle of Kafka producers according to the provided configuration |
| `KafkaProducer<K, V>` | Handles the producer protocol communication with brokers, buffering, retries, and sending according to client configuration |
| Serializer | Converts keys/values from Java types into byte arrays |
| Partitioner | Selects a partition if the record does not specify a concrete partition |
| Kafka broker | Receives, stores, and replicates records according to the topic/cluster configuration |

In Spring Boot, when the Spring Kafka dependency and appropriate configuration are present, auto-configuration can create `ProducerFactory` and `KafkaTemplate` for the application to inject directly. When multiple producers with different serializers, credentials, or clusters are needed, the application can declare multiple separate factories/templates and inject the right bean using `@Qualifier`.

## 2. What problems does KafkaTemplate solve?

If you call `KafkaProducer` directly, every component that sends data must deal with creating the producer, configuring serializers, managing resources, closing the producer, and handling callbacks. This approach may fit a plain Java application, but it introduces substantial infrastructure boilerplate when integrated into a Spring application.

`KafkaTemplate` centralizes those operations into a shared abstraction:

- Can be injected as a Spring bean instead of creating a producer manually in every service.
- Shares configuration provided by `ProducerFactory`.
- Provides `send` overloads for topic, key, partition, `ProducerRecord`, and Spring `Message`.
- Returns asynchronous results so the application can handle metadata or errors.
- Supports sending records inside a Kafka transaction when configured.
- Offers additional operations such as `flush`, `execute`, and `metrics` for advanced scenarios.

With this organization, business code focuses on publishing events. Connection configuration, serializers, partitioner, Kafka client retries, and producer management are placed in the messaging configuration layer.

## 3. Declaring and injecting KafkaTemplate

With Spring Boot, first add the Spring Kafka dependency matching the Boot line in use. Newer Boot lines may provide a Kafka starter; others use `spring-kafka` with Boot's dependency management. Then configure the broker address and serializers.

Example `application.yml` for string keys and string values:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
```

Inject `KafkaTemplate` using constructor injection:

```java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
public class NotificationPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public NotificationPublisher(
            KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }
}
```

The two generic types `<String, String>` represent the key and value types that application code sends. They must match the serializers configured in the producer factory. If you use `KafkaTemplate<String, OrderCreatedEvent>`, the value serializer must know how to convert `OrderCreatedEvent` to bytes, such as a JSON serializer or a schema-based serializer.

Typically, use a configured `KafkaTemplate` bean and share it across services. Do not create a new `KafkaTemplate` or `KafkaProducer` for every HTTP request or every message; doing so increases initialization overhead, connection count, and resource management complexity.

## 4. Common ways to send records

`KafkaTemplate` provides multiple overloads to fit routing and metadata requirements.

### Send a value to a topic

```java
kafkaTemplate.send("notifications", "A new notification");
```

Not passing a key means the record has no key. With the default partitioner, Kafka uses sticky partitioning for keyless records. Do not use this approach if events belonging to the same entity need to be grouped onto the same partition.

### Send to a topic with key and value

```java
kafkaTemplate.send("orders.events", orderId, event);
```

This is the form commonly used in event-driven applications. `orderId` helps ensure events for the same order are generally routed to the same partition, provided the partition count, serializer, and partitioner do not change.

### Specify a concrete partition

```java
kafkaTemplate.send("orders.events", 1, orderId, event);
```

The record is sent directly to partition `1`. That partition must exist in the topic. When specifying a partition, the application takes responsibility for routing and ensuring that records requiring mutual ordering are sent to the same partition.

### Send a ProducerRecord

When fuller control over record attributes is needed, create a `ProducerRecord`:

```java
import org.apache.kafka.clients.producer.ProducerRecord;

ProducerRecord<String, String> record = new ProducerRecord<>(
        "orders.events",
        1,
        orderId,
        eventJson);

record.headers().add(
        "event-source",
        "order-service".getBytes(java.nio.charset.StandardCharsets.UTF_8));

kafkaTemplate.send(record);
```

`ProducerRecord` allows specifying the topic, partition, timestamp, key, value, and headers. Headers are commonly used to pass metadata such as event type, correlation ID, or source service. Do not put passwords, tokens, or sensitive data in headers.

### Send a Spring Message

In applications already using Spring's `Message<?>` abstraction, you can send a message with headers:

```java
import org.springframework.messaging.support.MessageBuilder;

var message = MessageBuilder
        .withPayload(eventJson)
        .setHeader("kafka_topic", "orders.events")
        .setHeader("kafka_messageKey", orderId)
        .build();

kafkaTemplate.send(message);
```

Spring Kafka maps supported headers to Kafka record metadata. Special header names and mapping behavior depend on the Spring Kafka API/version; for code that needs exact control over partition, timestamp, or headers, `ProducerRecord` is usually clearer.

### Send to the default topic

`sendDefault(...)` sends to the default topic configured on the template. This is useful when a template is dedicated to a single topic. In applications with many business topics, passing the topic explicitly to `send` usually makes code easier to read and search.

## 5. Send results are asynchronous

The `send` methods return `CompletableFuture<SendResult<K, V>>` in modern Spring Kafka releases (Spring Kafka 3.x and later). The application can continue doing other work while the Kafka producer sends the record.

Example publisher returning the future to the caller:

```java
import java.util.concurrent.CompletableFuture;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderEventPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, String>> publish(
            String orderId,
            String eventJson) {
        return kafkaTemplate.send("orders.events", orderId, eventJson);
    }
}
```

The caller can handle the result:

```java
publisher.publish(orderId, eventJson)
        .whenComplete((result, exception) -> {
            if (exception != null) {
                log.error("Publish order event failed: orderId={}",
                        orderId, exception);
                return;
            }

            var metadata = result.getRecordMetadata();
            log.info("Published order event: topic={}, partition={}, offset={}",
                    metadata.topic(), metadata.partition(), metadata.offset());
        });
```

The example assumes the class already has a `log` logger. `SendResult` provides the sent record and the `RecordMetadata` received by the producer, including topic, partition, offset, and timestamp. Metadata confirms the record location acknowledged by the broker according to the producer's acknowledgement mechanism.

Do not call `.get()` or `.join()` by default for every message on a request thread. Waiting synchronously blocks the request until the future completes, reducing the benefits of asynchronous sending and potentially increasing latency. Only wait when the business flow genuinely needs the send result before proceeding.

Note: with `acks=0`, the producer does not wait for broker acknowledgement; a completed future does not mean the broker confirmed storing the record. With `acks=1` or `acks=all`, the acknowledgement level depends on broker configuration, replication, and `min.insync.replicas`. Choose `acks` according to data durability requirements.

## 6. Handling send errors

Errors can occur immediately when calling `send` or surface later while the producer performs the asynchronous send. For example, configuration or serialization errors may arise while preparing the record; timeout, broker unavailable, or authorization errors may appear when sending to the cluster.

Therefore, code needs to handle both forms:

```java
public CompletableFuture<SendResult<String, String>> publish(
        String orderId,
        String eventJson) {
    try {
        return kafkaTemplate.send("orders.events", orderId, eventJson)
                .whenComplete((result, exception) -> {
                    if (exception != null) {
                        log.error("Kafka send failed for orderId={}",
                                orderId, exception);
                    }
                });
    }
    catch (RuntimeException exception) {
        log.error("Cannot prepare Kafka record for orderId={}",
                orderId, exception);
        throw exception;
    }
}
```

The example above logs asynchronous errors in the callback and rethrows synchronous errors so the caller can decide how to respond. In production code, clearly define who is responsible for retrying, recording the failed state, or routing the event to a recovery flow. Do not blindly retry every error; serialization or authorization errors usually do not resolve on immediate retry.

Do not swallow exceptions and return success. If a publisher does not notify the caller of failures, the application may record that a business operation emitted an event even though the record was not sent with the desired acknowledgement level.

## 7. KafkaTemplate and key, partition, headers

`KafkaTemplate` does not decide the business meaning of the key on its own. The application must choose a key aligned with the entity requiring ordering, such as `orderId` for order lifecycle events. When no partition is specified, the producer partitioner uses the serialized key to select the partition.

Some principles when sending:

- Use consistent key types and serializers across producers writing to the same topic.
- Choose keys according to business ordering boundaries; do not use a different UUID for each event if events need to be grouped by aggregate.
- Use `ProducerRecord` or Spring `Message` when extra metadata is needed.
- Do not treat headers as a place to store the main payload or authentication secrets.
- Inspect partition/offset from `SendResult` in logs or tests to verify routing.

Increasing the partition count can cause keys to map to different partitions because the number of partitions participating in the routing calculation has changed. If business logic relies on per-key ordering across the entire history, evaluate the impact before expanding a topic.

## 8. KafkaTemplate and transactions

`KafkaTemplate` supports sending records within a Kafka transaction when the producer factory is configured for transactions appropriately. Applications can use `executeInTransaction(...)` to group multiple send operations into a single Kafka transaction:

```java
kafkaTemplate.executeInTransaction(operations -> {
    operations.send("orders.events", orderId, orderCreatedJson);
    operations.send("orders.audit", orderId, auditJson);
    return true;
});
```

If an operation inside the callback fails and an exception propagates out, the transaction can be aborted by the template's transaction mechanism. Configure the transaction ID prefix and producer factory according to the Spring Kafka documentation for the version in use.

A Kafka transaction coordinates Kafka write operations within the same transaction. It does not automatically create an atomic transaction between Kafka and a relational database. If a service both updates a database and emits events, consider transactional outbox, inbox, or idempotency to handle the gap between database commit and Kafka commit.

## 9. `flush`, `execute`, and advanced operations

### `flush()`

A Kafka producer normally sends asynchronously and may batch records together. `KafkaTemplate.flush()` asks the producer to flush pending records and wait for sending to complete according to Kafka client semantics.

```java
kafkaTemplate.send("notifications", "service-started");
kafkaTemplate.flush();
```

Do not call `flush()` after every record in high-throughput flows without a specific reason. Flushing continuously can reduce batching and throughput. In most application code, observing `CompletableFuture` is a better way to learn the send result.

### `execute(...)`

`execute(...)` lets you run a callback with the Kafka `Producer` managed by the template. This is a low-level API for situations requiring producer operations that the `send` overloads do not cover. Prefer the template's high-level APIs; when using `execute`, do not manually close the factory-managed producer and understand the callback lifecycle carefully.

### Metrics

`metrics()` gives access to the metrics of the managed producer. Kafka client metrics help observe send rates, batching, request latency, and buffering. When exporting metrics to a monitoring system, choose relevant metrics and avoid creating excessive cardinality from dynamic topics, keys, or client IDs.

## 10. Is KafkaTemplate thread-safe?

In a standard Spring Kafka configuration, `KafkaTemplate` is designed to be shared and used concurrently from multiple services or threads when configured properly. Applications typically inject a singleton bean instead of creating a new template for each task.

Concurrency safety also depends on the producer factory and any application customizations. If you create multiple `ProducerFactory` beans, separate templates, or custom callbacks with mutable state, ensure those components are safe for concurrent access. Do not store request-specific data in mutable fields of a singleton publisher.

## 11. When to use KafkaTemplate and when another API is needed?

| Need | Appropriate approach |
| --- | --- |
| Send a business event to a topic | `KafkaTemplate.send(topic, key, value)` |
| Specify partition, timestamp, or headers | Build a `ProducerRecord` and send it |
| Send a message structured with Spring's abstraction | `KafkaTemplate.send(Message<?>)` |
| Send multiple records in a Kafka transaction | Transaction support of `KafkaTemplate` |
| Access the producer for specialized operations | `execute(...)`, only when high-level APIs are insufficient |
| Read events from a topic | `@KafkaListener` and listener containers, not `KafkaTemplate` |
| Inspect or modify topic/cluster metadata | `KafkaAdmin` or Kafka `AdminClient` |

`KafkaTemplate` is the data-sending API. Receiving data is the consumer's responsibility and is typically organized with `@KafkaListener`. Separating these two roles allows producer and consumer services to evolve, scale, and operate independently.

## 12. Common mistakes

| Mistake | Consequence | How to handle |
| --- | --- | --- |
| Calling `send` and assuming success by default | Asynchronous errors go undetected | Track the future and handle exceptions |
| Using generic types that do not match the serializer | Serialization or deserialization errors | Align key/value types with serializers and deserializers |
| Creating a new template/producer per request | Increases connections and resource overhead | Inject a shared template bean |
| Not passing a key when per-entity ordering is needed | Events for the same entity may land in multiple partitions | Use a stable business key |
| Blocking on `.get()` for every send | Increases latency and reduces throughput | Use callbacks/futures unless synchronous results are required |
| Calling `flush()` after every record | Reduces batching and throughput | Let the producer batch under normal configuration |
| Swallowing Kafka send exceptions | Loses visibility into failures | Record and propagate errors to the responsible layer |
| Assuming a Kafka transaction includes the database | State divergence between DB and Kafka can occur | Use outbox/inbox or an appropriate consistency mechanism |

## 13. Conclusion

`KafkaTemplate` is the central producer-side abstraction in Spring Kafka. It connects business code with the Kafka producer through `ProducerFactory`, providing ways to send records with or without keys, specify partitions, attach headers, track asynchronous results, and coordinate Kafka transactions.

In a Spring application, inject a shared template, choose matching key/value types and serializers, pass keys aligned with business ordering boundaries, and observe `CompletableFuture` for send outcomes. Understanding the boundaries between producer acknowledgements, consumer processing, and database transactions helps design more reliable messaging flows.

## References

- [Spring for Apache Kafka — KafkaTemplate](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html)
- [Spring for Apache Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Apache Kafka — Producer Configuration](https://kafka.apache.org/documentation/#producerconfigs)
