# The Publish-Subscribe Model in Kafka

## 1. What Is Publish-Subscribe?

Publish-subscribe (pub/sub) is a communication model in which the event sender (*publisher* or *producer*) sends messages to a shared channel, while recipients (*subscribers* or *consumers*) register to receive messages from that channel. Neither side needs to call the other directly, and usually neither needs to know the identity or network address of the other.

For example, when an order is created, the Order service emits an `OrderCreated` event. The Inventory service can receive the event to reserve stock, the Notification service sends an email, and the Analytics service updates metrics. Order is only responsible for publishing the event; it does not need to call those three services one by one.

This model reduces coupling between services, allows adding or changing consumers with minimal impact on the publisher, and supports asynchronous processing. In return, the system must account for message delivery guarantees, processing order, duplicate failures, latency, and observability.

## 2. How Does Kafka Implement Pub/Sub?

Kafka is a distributed event streaming platform. Producers write records to a **topic**; Kafka stores records in logs split into **partitions**; consumers read records from partitions by offset. A broker is a Kafka process that stores data and serves read/write requests. A Kafka cluster typically has multiple brokers to distribute load and improve fault tolerance.

<escape>
Producer Order ── OrderCreated ──▶ Topic: orders
                                      │
                         ┌────────────┼────────────┐
                         ▼            ▼            ▼
                   Consumer       Consumer     Consumer
                   group: stock   group: mail  group: analytics
                   (Inventory)    (Notify)     (Analytics)
</escape>

In Kafka, a topic acts as the event channel. Producers can send records without knowing which consumers are active. Consumers actively poll data from Kafka; the broker does not need to open a separate push connection to deliver each event to every subscriber.

An important point: Kafka does not delete a record right after one consumer finishes reading it. Records are retained according to a retention policy (by time or size) and can be read independently by multiple consumer groups. Therefore, a new consumer can read historical data if offset configuration and retention allow.

## 3. Topic, Partition, and Offset

### Topic

A topic is the logical name of a record stream, typically named after an event category or business domain such as `orders`, `payments`, or `inventory-events`. Producers write to topics; consumers subscribe to one or more topics to read.

Topic names should clearly express content and business scope. For large systems, establish consistent naming conventions, schemas, access permissions, and retention policies so service teams can integrate safely.

### Partition

Each topic is divided into one or more partitions. A partition is an ordered log: new records are appended to the end of the log and numbered with an incrementing offset. Partitions can reside on different brokers, enabling Kafka to distribute storage and processing.

Kafka guarantees ordering only within a single partition, not global ordering across multiple partitions. If events for the same order must be processed in sequence, the producer should use `orderId` as the message key. Kafka maps the same key to the same partition under the default partitioner (provided the partition count and related configuration do not change in a way that alters the mapping).

Increasing the number of partitions can increase parallel processing capacity, but it can also alter key-to-partition mapping and complicate ordering requirements. Therefore, choose partition counts based on throughput, expected consumer count, and business characteristics.

### Offset

An offset is the position of a record within a partition. Offsets help consumers track their read position and resume from the saved position after a restart. An offset has meaning within each partition, not as a global sequence number for the entire topic.

A consumer group stores reading progress (committed offsets) for each partition. When a consumer reads a record, that does not automatically mean the offset has been committed. Committing too early can lose the ability to reprocess if the application crashes; committing too late can cause records to be reprocessed after a restart. Hence, commit timing must align with business processing outcomes.

## 4. Consumer Groups Create Pub/Sub Distribution

A consumer group is a collection of consumers sharing the same `group.id`. Within a group, each partition at any given time is assigned to at most one consumer in the group. Consumers in the same group therefore split the topic's workload instead of each consumer receiving every record.

Different groups read independently. On topic `orders`, the `inventory-service` group can handle stock reservation, while the `notification-service` group handles sending notifications. Both groups can read the exact same `OrderCreated` record, each maintaining its own offsets.

| Configuration | Outcome |
|---|---|
| Multiple consumers in the same group | Share partitions and processing load; a record in a partition is processed by one consumer in the group at a time |
| One consumer in each different group | Each group has independent reading progress and can read the same data |
| More consumers in a group than partitions | Some consumers receive no partition assignment and remain idle |
| Fewer or equal consumers compared to partitions | Can process in parallel across partitions, depending on assigned partitions and application capacity |

For example, if a topic has 4 partitions and a group has 2 consumers, each consumer typically receives 2 partitions. If the group has 5 consumers, at most 4 consumers are assigned partitions; the extra consumer does not increase the group's read throughput. When group membership changes, Kafka performs a rebalance to reassign partitions.

## 5. Sending and Receiving Events with Spring Kafka

Spring Kafka provides `KafkaTemplate` to send records and `@KafkaListener` to declare record-receiving methods. Connection settings are typically placed in `application.yml`.

### Basic Configuration

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
    consumer:
      group-id: notification-service
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.example.messaging
```

`bootstrap-servers` is the list of broker addresses for initializing client connections. Serializers convert keys/values into bytes before sending; deserializers convert bytes into application types when receiving. JSON settings must be consistent between producer and consumer, especially data types, type headers, and trusted packages. In production environments, configure authentication, encrypted connections, and schema compatibility per deployment requirements.

### Producer Using KafkaTemplate

```java
public record OrderCreated(String orderId, BigDecimal total) {}

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

The `send` call sends a record to topic `orders`, using `orderId` as the key and the event as the value. The return value is a `CompletableFuture`, so the application can handle the send result asynchronously, log failures, or add an appropriate retry mechanism. Calling `send` should not be regarded as proof that the broker acknowledged the record; observe the future's completion result and configure suitable producer acknowledgements.

### Consumer Using @KafkaListener

```java
@Component
public class OrderCreatedListener {

    @KafkaListener(topics = "orders", groupId = "notification-service")
    public void onOrderCreated(OrderCreated event) {
        // Business logic: create a notification request.
        System.out.printf("Order %s, total %s%n",
                event.orderId(), event.total());
    }
}
```

Spring Kafka manages the listener container lifecycle and record polling. `groupId` identifies the consumer group; multiple instances of the same service can join the same group to share partitions. In a real application, delegate business processing to a dedicated service, control error handling, and ensure operations tolerate redelivery of an event.

## 6. Example Processing Flow Between Services

Suppose Order Service creates an order. Once the order is confirmed, it publishes `OrderCreated` to topic `orders`. Inventory Service reads the event in group `inventory-service` to reserve stock. Notification Service reads the same topic in group `notification-service` to send emails. Analytics Service can read in its own group to update reports.

Services can be deployed and scaled independently. When Fraud Detection needs to be added, the development team simply deploys a new consumer group reading topic `orders`; Order Service does not need to know the new consumer exists. However, the event contract must remain stable: define field names and meanings, schema versions, emission timing, and how incompatible data is handled.

Events should describe something that happened, such as `OrderCreated` or `PaymentCaptured`, rather than commanding consumers to perform an arbitrary instruction. The producer must emit the event at the appropriate business moment. If database updates and Kafka publishing must be consistent, consider the Transactional Outbox pattern to avoid situations where data is committed but the event is never sent (or vice versa).

## 7. Operational Characteristics to Understand

### Delivery and Duplicate Processing

In practice, a consumer may finish processing a record yet stop before committing its offset. Upon restart, that record can be read and processed again. Therefore, applications often need idempotent handlers: processing the same `eventId` multiple times produces no duplicate side effects. Processed event IDs can be stored with a unique constraint in the database or guarded by an appropriate business key.

### Retry and Dead-Letter Topics

Transient errors such as timeouts or unavailable dependencies can be retried with bounded attempts and wait intervals. Invalid data or unrecoverable errors should be routed to a dead-letter topic for investigation and controlled reprocessing. Infinite retries can stall a partition and increase latency for subsequent records.

### Ordering and Parallelism

Ordering is guaranteed only within a single partition. Parallel processing inside the consumer application itself can also alter completion order, even if records are polled in order. If business logic depends on order, use a stable key, control concurrency, and avoid processing records with the same key concurrently.

### Retention and Replay

Kafka retains records according to retention settings independently of whether consumers have read them. When rebuilding projections or fixing processing bugs, a consumer group can re-read retained data. Replay must be prepared so it does not trigger duplicate side effects in external systems.

## 8. When Should You Use This Model?

Pub/sub with Kafka fits when multiple systems care about an event, teams need to deploy independently, traffic volume is high, or data replay is required. It is also useful for decoupling the primary request path from secondary tasks such as sending notifications, updating search indexes, and running analytics.

Kafka does not solve every integration problem on its own. For calls needing immediate responses, synchronous data queries, or simple CRUD operations, HTTP/gRPC may be more suitable. With Kafka, teams must operate brokers, monitor consumer lag, manage schemas, configure topic permissions, and handle retention, retries, and dead letters.

## 9. Summary

- Producers publish records to topics; consumers actively read records from Kafka.
- Topics are divided into partitions; each partition is an ordered log with its own offsets.
- Ordering is guaranteed within a single partition, so keys help group related events into the same partition.
- Consumers in the same group share partitions; different groups can read the same data with independent offsets.
- `KafkaTemplate` supports publishing events and `@KafkaListener` supports receiving events in Spring Kafka.
- Consumer design must account for offset commits, duplicate processing, idempotency, retries, dead letters, and replay.

By mastering these components, you can design event flows between services where publishers and subscribers are loosely coupled while keeping scalability and operational reliability under control.
