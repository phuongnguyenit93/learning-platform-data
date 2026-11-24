# Sending with a Custom Timestamp

Every Kafka record can carry a timestamp alongside its key, value, and headers. The timestamp helps describe the point in time associated with the event, supporting latency monitoring and time-based data processing. With Spring Kafka, the producer can specify a timestamp when creating a `ProducerRecord` or calling the corresponding `KafkaTemplate.send()` overload.

When building messaging flows with `KafkaTemplate` and `@KafkaListener`, you must clearly define what point in time the timestamp represents. An event might have occurred in the source system several minutes before being sent to Kafka; the broker can also assign the time when the record is appended to the log. Kafka supports two timestamp types, `CreateTime` and `LogAppendTime`, and the choice at the topic level determines which timestamp consumers observe.

## 1. Timestamp of a Kafka record

A Kafka record timestamp is a time value measured in **milliseconds since the Unix epoch** (1970-01-01T00:00:00Z). In Java, `Instant` is a suitable type to represent an absolute point in time and convert to a Kafka value via `toEpochMilli()`.

For example, a service receives an order event with the following details:

```text
orderId: order-1001
event: OrderPaid
occurredAt: 2026-11-17T02:15:30Z
```

The producer can use `occurredAt` as the record's timestamp. Consumers later read this timestamp to determine when the event was recorded according to the source system's clock.

The timestamp is record metadata, not a key and not an offset:

- **Key** is typically used to route the record to a partition, e.g., `orderId`.
- **Offset** is the record's position within a partition and determines log order in that partition.
- **Timestamp** represents the point in time attached to the record according to the topic's timestamp type.

Changing the timestamp does not change the partition selected by the key, does not change the offset, and does not reorder already written records. Kafka still stores records in append order within the partition. Timestamps can increase or decrease between two consecutive records if a producer sends late events or data arrives out of chronological order.

## 2. Distinguishing CreateTime and LogAppendTime

Kafka supports two primary timestamp types, configured via the topic property `message.timestamp.type`.

| Timestamp type | Value stored on the record | Meaning |
|---|---|---|
| `CreateTime` | Timestamp provided by the producer; if the producer does not provide one, the Kafka producer usually assigns the current time | Suitable when preserving the time the event occurred or was created at the source |
| `LogAppendTime` | Timestamp assigned by the broker when appending the record to the log | Suitable when needing the time Kafka ingested the record at the broker |

### CreateTime

With `CreateTime`, the broker keeps the timestamp sent by the producer. The producer may send the current time or an older time taken from business data. This is usually the right choice for event time, such as when an order was paid in the payment system.

For example, the payment service might lose connectivity to Kafka for two minutes. When connectivity returns, it sends the `PaymentReceived` event with the timestamp set to the actual payment time. The timestamp still reflects when the payment happened, even though Kafka only received the record later.

Because the producer decides the value, the system must control clocks and input time data. Incorrect timestamps, values too far in the future, or inconsistent time zones can skew latency measurements and event-time processing. Depending on the broker version and configuration, Kafka may enforce timestamp difference limits to reject invalid values.

### LogAppendTime

With `LogAppendTime`, the broker overwrites the producer-sent timestamp with the time the broker appends the record to the log. This value reflects when Kafka ingested the data at the leader broker, which is useful when measuring ingest time or investigating send latency to Kafka.

If a producer sends an event with an old timestamp, that value is no longer the record's timestamp after the broker applies `LogAppendTime`. If business logic still needs to know when the event actually occurred, keep `occurredAt` inside the record's payload or headers.

Broker clocks must be synchronized when using `LogAppendTime`, especially when a partition can transfer leadership between brokers. Clock skew can make ingest time measurements inconsistent.

## 3. Sending a custom timestamp with ProducerRecord

`ProducerRecord` has a constructor that lets you specify topic, partition, timestamp, key, and value. The timestamp passed to the constructor is a `Long` in milliseconds. If you pass `null` for the partition position, the producer still uses the partitioner to choose the partition based on the key.

Example with Spring Kafka:

```java
import java.time.Instant;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
class OrderEventProducer {

    private final KafkaTemplate<String, String> kafkaTemplate;

    OrderEventProducer(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(
            String orderId,
            String payload,
            Instant occurredAt
    ) {
        long timestamp = occurredAt.toEpochMilli();

        ProducerRecord<String, String> record = new ProducerRecord<>(
                "orders.events",
                null,           // Let the partitioner select the partition from the key.
                timestamp,      // Milliseconds since the Unix epoch.
                orderId,
                payload
        );

        kafkaTemplate.send(record);
    }
}
```

In this example, `orderId` is the key and `occurredAt` is the timestamp. If the topic uses `CreateTime`, Kafka preserves the custom timestamp. If the topic uses `LogAppendTime`, the broker replaces this timestamp with the append time.

Use `Instant` instead of manually computing millisecond numbers or using a timezone-less `LocalDateTime`. If the timestamp comes from an ISO-8601 string with an offset or `Z` marker, parse it into an `Instant` before sending:

```java
Instant occurredAt = Instant.parse("2026-11-17T02:15:30Z");
long timestamp = occurredAt.toEpochMilli();
```

If the input data is in local time, convert it with a known `ZoneId` to identify an exact point in time. Do not blindly assume `LocalDateTime` is UTC.

## 4. Sending a timestamp via KafkaTemplate overloads

Spring Kafka also provides a `KafkaTemplate.send()` overload that directly accepts a timestamp:

```java
public void publish(
        String orderId,
        String payload,
        Instant occurredAt
) {
    kafkaTemplate.send(
            "orders.events",
            null,                       // Partition: let the partitioner choose.
            occurredAt.toEpochMilli(), // Timestamp in epoch milliseconds.
            orderId,                    // Key.
            payload                     // Value.
    );
}
```

This overload is equivalent to creating a `ProducerRecord` and calling `send(record)`. Using `ProducerRecord` is useful when you need to set additional headers or keep the record as an object before sending. Using the direct overload is more concise when only passing the basic fields.

`KafkaTemplate.send()` sends asynchronously and returns a future containing the send result. In real applications, observe send errors and returned metadata rather than assuming the record has been written by the broker just because `send()` was called. The exact future signature depends on the Spring Kafka version; starting with Spring Kafka 3.x, send methods return `CompletableFuture`.

## 5. Configuring the timestamp type for a topic

The timestamp type is a topic configuration. You can declare a topic using `NewTopic` and `TopicBuilder` in Spring Kafka. The following example selects `CreateTime` for `orders.events`:

```java
import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.TopicBuilder;

@Configuration
class OrderTopicConfiguration {

    @Bean
    NewTopic ordersEventsTopic() {
        return TopicBuilder.name("orders.events")
                .partitions(3)
                .replicas(1)
                .config("message.timestamp.type", "CreateTime")
                .build();
    }
}
```

A replication factor of one is appropriate for a single-broker development cluster. In production, choose the replication factor based on broker count and the system's fault-tolerance requirements. The `message.timestamp.type` setting can be configured at the broker level as a default and overridden at the topic level.

To use broker append time, change the setting to:

```java
.config("message.timestamp.type", "LogAppendTime")
```

The two options serve different purposes. Do not choose `LogAppendTime` if downstream consumers need the Kafka timestamp to reflect when the event occurred at the source; in that case, use `CreateTime` or store event time separately in the payload when append time is mandatory.

The `NewTopic` bean enables Spring Kafka to ask Kafka Admin to create the topic with the declared configuration when the topic does not yet exist. When a topic has already been created beforehand, check the actual configuration on the cluster; do not assume that merely editing the bean will definitely change an existing topic's configuration.

## 6. Reading the timestamp on the consumer

Consumers can read both the timestamp and timestamp type from `ConsumerRecord`. With Spring Kafka, `@KafkaListener` can accept `ConsumerRecord` directly to retrieve both payload and metadata:

```java
import java.time.Instant;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderEventListener {

    @KafkaListener(topics = "orders.events", groupId = "order-projection")
    public void consume(ConsumerRecord<String, String> record) {
        long timestampMillis = record.timestamp();

        if (timestampMillis >= 0) {
            Instant recordTime = Instant.ofEpochMilli(timestampMillis);
            System.out.printf(
                    "key=%s, timestamp=%s, timestampType=%s, partition=%d, offset=%d%n",
                    record.key(),
                    recordTime,
                    record.timestampType(),
                    record.partition(),
                    record.offset()
            );
        }

        process(record.value());
    }

    private void process(String payload) {
        // Process the order event.
    }
}
```

`record.timestamp()` returns the timestamp in milliseconds; `record.timestampType()` indicates whether the timestamp is `CREATE_TIME` or `LOG_APPEND_TIME`. Checking both fields helps the consumer correctly interpret the received time. In some formats or cases where a record has no valid timestamp, the value may be a negative sentinel; therefore, check before converting to `Instant`.

If you need to measure ingest latency for a topic using `CreateTime`, you can compare the time observed by the broker/consumer with the event timestamp. This measurement is only meaningful when producer, broker, and consumer clocks are sufficiently synchronized. With a topic using `LogAppendTime`, the record timestamp reflects broker append time; to measure consumer processing time, record the processing time in the application as well.

## 7. How do timestamps affect time-based processing?

Timestamps matter in time-based event-processing systems, but they do not replace offsets and do not guarantee global ordering.

### Event time, ingest time, and processing time

| Concept | Point in time represented | Common source |
|---|---|---|
| Event time | When the business event actually occurred | Source data, e.g., `occurredAt` |
| Ingest/append time | When the Kafka broker wrote the record to the log | `LogAppendTime` timestamp |
| Processing time | When the consumer application processes the record | Consumer process clock |

The three points in time can differ significantly. For example, a payment event occurs at 10:00, the producer resends at 10:03 after a connection drop, and the consumer processes it at 10:03:02. Then event time is 10:00, append time is near 10:03, and processing time is near 10:03:02.

If using `CreateTime`, the record can retain event time to aggregate revenue by transaction hour. If using `LogAppendTime`, the record timestamp is better suited for tracking when Kafka ingested the data. If you need both, keep event time in the payload and use the record timestamp for append time.

### Timestamps do not reorder the log

Suppose a producer sends three events to the same partition in the following order:

| Offset | Event | Timestamp |
|---:|---|---|
| 40 | `OrderCreated` | 10:00:00 |
| 41 | `OrderPaid` | 10:02:00 |
| 42 | `OrderItemAdded` (arrived late) | 09:59:30 |

The consumer still reads offset 40, 41, and then 42. The timestamp of the last record is older than the previous two, yet Kafka does not move it earlier in the log. An application performing event-time processing must have a policy for late data, such as watermarks, grace periods, or updating already computed results.

Kafka Streams uses record timestamps for time-based processing according to its timestamp extractor configuration. Consequently, choosing `CreateTime` or `LogAppendTime` can alter time window results, how late events are detected, and when windows close. Align timestamp semantics between producers and downstream applications.

### Timestamps and retention

With time-based retention, log segment timestamps can participate in determining when a segment becomes eligible for deletion. When a topic uses `CreateTime`, the timestamp provided by the producer therefore needs to be sensible. A timestamp too far in the future can skew when time-based cleanup triggers; a timestamp too far in the past can make data eligible for deletion sooner than expected. With `LogAppendTime`, the broker uses append time, so retention policies reflect when data entered the log.

Do not use custom timestamps as a way to schedule record deletion or replace retention policies. Retention is applied per segment and topic/broker configuration, not as an independent timer per record.

## 8. Checks and usage choices

Before putting custom timestamps into production, check the following points:

1. **Unit:** the value sent to Kafka is epoch milliseconds. Do not pass epoch seconds or nanoseconds directly.
2. **Time zone:** convert source timestamps to `Instant`; do not interpret `LocalDateTime` without determining `ZoneId`.
3. **Meaning:** decide whether the timestamp is event time or broker append time and configure `message.timestamp.type` accordingly.
4. **Clock skew:** synchronize clocks across producer, broker, and consumer; check broker policies if sending timestamps too far from current time.
5. **Partition and ordering:** continue using keys to route records. Timestamps do not guarantee event order.
6. **Downstream:** verify whether consumers and Kafka Streams are using record timestamps as event time.
7. **Retention:** examine the impact of custom timestamps on time-based deletion policies.
8. **Send result:** observe the returned future and metadata to confirm the record was sent successfully and the actual broker timestamp matches expectations.

| Need | Suitable choice |
|---|---|
| Aggregating by when the business event occurred | `CreateTime` and pass `occurredAt` |
| Measuring when Kafka ingested data | `LogAppendTime` |
| Needing event time while the topic uses append time | Store `occurredAt` in payload/headers and use the record timestamp for append time |
| Only needing the producer's current send time | Let the producer attach the default timestamp or pass `Instant.now()` |

Sending custom timestamps helps an event stream preserve time semantics aligned with business logic. When using Spring Kafka, pass epoch milliseconds via `ProducerRecord` or `KafkaTemplate.send()`, clearly define `CreateTime` or `LogAppendTime` on the topic, and inspect both timestamp and `timestampType` on the consumer. Offsets remain the basis for log ordering; timestamps add time information so applications can measure and process events in the right context.
