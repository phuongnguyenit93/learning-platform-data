# What Problems Does Spring Kafka Solve in a Spring Application?

In a Spring application, components often need to exchange data with each other or coordinate with external systems. A familiar approach is calling a REST API directly: service A sends a request to service B and waits for a response. This approach works well when an immediate result is needed, but it can create a tightly coupled chain of dependencies. For example, after creating an order, the system may also need to update inventory, send a notification, record analytics data, and initiate shipping. If everything is called synchronously, the processing time of the order creation request depends on all downstream services. One slow or temporarily unavailable service can slow down or fail the entire flow.

Kafka provides another way to communicate: an application publishes events to a data stream, while interested applications independently read and process those events. Spring Kafka helps a Spring application use this mechanism through familiar Spring building blocks such as dependency injection, externalized configuration, lifecycle management, and error handling. To understand what problems Spring Kafka solves, it is first necessary to distinguish Kafka's role from Spring Kafka's role.

## 1. The Problem of Asynchronous Communication Between Components

Suppose the order service needs to announce that an order has been created. Instead of calling the inventory, notification, and analytics services one by one, the order service can publish an `OrderCreated` event to the `orders.created` topic.

Other services subscribe to read that topic as needed:

- The inventory service receives the event to reserve or deduct stock.
- The notification service sends an email or notification to the buyer.
- The analytics service updates business metrics.

The order service only needs to complete publishing the event according to the chosen acknowledgement policy. Receiving services can process independently, at their own pace and timing. Adding a new consumer, such as a customer support service, usually does not require modifying the internal processing flow of the order service.

This model brings several benefits:

1. **Reduced direct coupling:** the event publisher does not need to know all recipients or call each one's API.
2. **Off-request-path processing:** work that does not need to complete before returning a response can be performed asynchronously.
3. **Absorbing load at the consumer's pace:** Kafka retains records for a configured retention period; a consumer can resume reading when it comes back online, as long as the data is still within the retention window.
4. **One event, multiple use cases:** multiple independent consumer groups can read the same topic—for example, both the inventory group and the analytics group receive the order creation event.
5. **Ability to replay data:** a consumer group can adjust its read position or use a new group to reprocess data that is still retained.

Asynchronous communication also has costs. Processing results usually do not appear immediately in the order creation response; the system must accept latency and eventual consistency. Consumers need to handle duplicate delivery, transient failures, and partially completed processing states. Kafka also needs to be deployed, monitored, and operated as separate infrastructure.

## 2. Kafka Concepts You Need to Know

Kafka stores records in a **topic**. A record typically has a key, value, timestamp, and headers. In the example above, the topic might be `orders.created`, the key is the order ID, and the value contains the event content.

A topic is divided into **partitions** for storage and parallel processing. Each record within a partition has an incrementing **offset** used to identify the record's position in that partition. An offset is not a global identifier across all topics; it only has meaning within a single partition.

The key affects partition selection. With the default partitioner, records with the same key are normally routed to the same partition. Therefore, if `orderId` is used as the key, events for the same order are normally read in order within the same partition. Kafka guarantees ordering within a single partition, not a global order across all partitions of a topic.

Consumers read records from a topic. Consumers in the same **consumer group** coordinate to share the partitions assigned to that group. At any point in time, a partition is assigned to at most one consumer within the same group. If there are multiple different consumer groups, each group has its own reading progress and can receive the same data.

For example:

| Component | Role |
| --- | --- |
| Topic `orders.created` | Stores order creation events |
| Partitions 0, 1, 2 | Splits data to increase storage capacity and parallel processing |
| Key `orderId` | Helps route events of the same order to the same partition |
| Consumer group `inventory-service` | Reads events to process inventory |
| Consumer group `analytics-service` | Reads the same events to update analytics |
| Offset | Tracks the reading position of each partition in each group |

Kafka does not work like a simple queue where a message disappears from the system once taken. Records are kept according to the topic's retention policy. Consumer groups store their reading progress using offsets; the fact that one group has read a record does not prevent another group from reading that record.

## 3. What Does Spring Kafka Add to a Spring Application?

Kafka provides a Java client for sending and receiving records. However, when integrating the client directly into a Spring application, the development team has to organize many parts themselves, such as initializing producers and consumers, managing lifecycles, running the poll loop, configuring serializers, handling errors, coordinating threads, and integrating with transactions.

Spring Kafka provides abstractions to bring those tasks into the Spring programming model. The main components include:

| Component | Problem Supported |
| --- | --- |
| `KafkaTemplate` | Sends records to a topic through an API that can be injected into services |
| `@KafkaListener` | Declares a method for receiving and processing records |
| Listener container | Manages consumers, polls data, invokes listeners, and coordinates lifecycle |
| Serializers and deserializers | Converts data between Java objects or types and byte arrays on Kafka |
| Error handler and retry | Defines how to handle exceptions thrown by a listener |
| Dead-letter topic (DLT) | Routes unprocessable records to a separate location for inspection or reprocessing |
| Transaction support | Coordinates reading, processing, and writing Kafka data within a configured Kafka transaction scope |

When using Spring Boot, Spring Kafka integrates with Boot's configuration mechanism and auto-configuration. Broker connection, producer, and consumer properties are typically declared in `application.yml` or `application.properties`. Services can inject `KafkaTemplate`; methods annotated with `@KafkaListener` are managed by the listener container.

Spring Kafka does not replace the Kafka broker. The broker remains responsible for storage, partition replication, metadata management, and record distribution. Spring Kafka is the application-side integration layer that makes using Kafka convenient and consistent with the Spring ecosystem.

## 4. Basic Send and Receive Flow

To illustrate, the following example uses strings as the key and value. In real systems, the value is usually JSON or a schema-based format such as Avro or Protobuf.

### Connection Configuration

With a Kafka broker running locally, a minimal configuration might look like this:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
    consumer:
      group-id: order-projection
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
```

`bootstrap-servers` specifies the broker address used to initiate the connection. The producer uses serializers to convert keys and values into bytes before sending. The consumer uses corresponding deserializers to convert received bytes back into Java types.

`auto-offset-reset: earliest` applies when the consumer group does not yet have a valid committed offset for a partition, such as when a new group starts reading. This property does not automatically rewind a group that already has offsets back to the beginning of the topic. To re-read data, you must explicitly change the read position or use a new consumer group, while ensuring the data is still within retention.

The application needs the `spring-kafka` dependency. If using Spring Boot dependency management, let Boot manage the compatible version instead of manually choosing an out-of-sync Spring Kafka version.

### Sending Events with `KafkaTemplate`

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
        return kafkaTemplate.send("orders.created", orderId, eventJson);
    }
}
```

`KafkaTemplate` is injected as a Spring dependency. The `send` call specifies the topic, key, and value. The key is `orderId`, so events for the same order are normally routed to the same partition by the default partitioner.

In modern versions of Spring Kafka, `send` returns a `CompletableFuture`. Calling code should observe the completion result to know whether the send succeeded or failed and handle/log errors appropriately. Calling `send` should not be treated as proof that the broker has successfully persisted the record.

### Receiving Events with `@KafkaListener`

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Service;

@Service
public class OrderProjectionListener {

    @KafkaListener(
            topics = "orders.created",
            groupId = "order-projection")
    public void consume(ConsumerRecord<String, String> record) {
        String orderId = record.key();
        String eventJson = record.value();

        // Convert the event and update the corresponding read model.
    }
}
```

`@KafkaListener` marks the method that receives records. The listener container creates and manages the Kafka consumer, invokes the method when data arrives, and coordinates offset commits and error handling according to configuration. As a result, business code can focus on interpreting the event and performing the required task.

In a real application, the producer and consumer may belong to two separate services. The example above places them side by side to clarify both ends of the data flow; splitting into services depends on business boundaries and deployment strategy.

## 5. Operational Concerns Spring Kafka Helps Organize

Simply sending and receiving a record is only the first step. A reliable messaging flow requires clearly defining the data, reading progress, and behavior when errors occur.

### Serialization and Data Contracts

Kafka stores bytes, so producer and consumer must agree on how to interpret the value. With JSON strings, both sides need to agree on field names, data types, and how timestamps or monetary amounts are represented. When multiple services share an event, schema changes need a backward- or forward-compatibility strategy. For larger systems, a schema registry with Avro or Protobuf can help manage data contracts more clearly.

You should not send an entire database entity just because it is already available in the application. An event should represent a business occurrence and carry only the data consumers need. This reduces coupling between internal storage structure and the integration contract.

### Offsets, Acknowledgments, and Duplicate Processing

Offsets represent a consumer group's reading progress. If an application finishes processing a record but stops before the offset is committed, the record may be read again after a restart or rebalance. Therefore, in many practical configurations, consumers need to be designed for **at-least-once** delivery: a record may be redelivered and business logic must tolerate duplicate processing.

A common approach is to make the consumer **idempotent**. For example, when updating an order status, the application checks the event ID or processed state before applying the change. For cumulative operations like deducting stock or crediting money, duplicate delivery can cause discrepancies without an appropriate deduplication mechanism.

### Retry and Dead-Letter Topics

Not all errors should be handled the same way. Transient connection errors can be retried with increasing wait intervals. Malformed data or business rule violations may never succeed regardless of how many times they are retried.

Spring Kafka supports configuring error handlers and retries. Once the maximum number of attempts is exhausted or an error classified as non-recoverable occurs, the application can route the record to a dead-letter topic (DLT). The DLT should retain enough information for tracing, such as the original topic and partition, offset, key, failure reason, and processing timestamp. Operations teams also need to monitor the DLT and have a process for fixing data or replaying records; merely moving failures to a DLT does not mean the incident is resolved.

### Partitions and Concurrent Processing

Spring Kafka allows increasing listener container concurrency so multiple consumers process a consumer group simultaneously. Useful parallelism is bounded by the number of partitions assigned to the group. If a topic has three partitions, increasing the number of consumers in the same group to ten will not make a single partition be processed in parallel by ten consumers.

Increasing concurrency can boost throughput, but it also increases the number of processing threads and potential resource contention on downstream databases or services. If business logic requires preserving order per order ID, choose a consistent key and avoid introducing additional parallel processing that reorders records sharing the same key.

### Transactions and Exactly-Once

Spring Kafka supports Kafka transactions to coordinate consuming a record, producing results, and writing results back to Kafka within the same transaction scope. When producer transactions and consumers reading with the appropriate isolation level are properly configured, a consume-process-produce flow can be built with exactly-once semantics within the Kafka scope.

That does not automatically create an atomic transaction between Kafka and a relational database. If a consumer both updates a database and commits a Kafka offset, the process can still crash between the two operations. Patterns such as transactional outbox, inbox, or idempotency are commonly used to handle this boundary. Always define the exact scope of guarantees before calling a processing flow exactly-once.

### Testing

Producer and consumer tests should verify both data content and flow behavior: keys/values are serialized properly, consumers read from the right topic and group, errors are retried according to policy, failed records are routed to the DLT, and duplicate processing does not corrupt state. Embedded Kafka or Kafka Testcontainers can be used for integration testing. Isolated unit tests for business logic remain useful, but they do not replace testing against a real broker when verifying serialization, partitions, and offsets.

## 6. When Should You Use Spring Kafka?

Spring Kafka is suitable when an application needs one or more of the following characteristics:

- Publishing events that multiple independent systems are interested in.
- Processing work asynchronously without keeping the user waiting for the entire chain of tasks.
- Ingesting high event volumes and scaling consumers by partition.
- Retaining events for a period of time so consumers can catch up or reprocess.
- Building data pipelines, service integrations, or event-driven architectures.

Synchronous REST calls are usually more suitable when the caller needs an immediate result, needs to query current data, or needs direct error feedback within the same request. For small background tasks confined to a single application, an executor or in-memory queue may be simpler. Kafka proves its value when you need durable event streams, multiple independent consumers, or high throughput sufficient to justify operational overhead.

## 7. Conclusion

Kafka provides the foundation for storing and distributing event streams across applications. Spring Kafka brings that foundation into Spring applications with abstractions such as `KafkaTemplate`, `@KafkaListener`, listener containers, serializers, error handlers, and transaction support.

As a result, applications can decouple event publishers from processors, organize asynchronous work, and scale independent consumers. For a reliable messaging flow, development teams still must design data contracts, keys and partitions, offset policies, duplicate handling, retries, DLTs, transactions, and testing. Spring Kafka provides the tools to implement those decisions; ultimate reliability depends on how the application configures and implements business logic.
