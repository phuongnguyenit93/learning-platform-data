# Ordering within a single producer

Kafka writes records into each partition's log in a deterministic order. When a single producer sends multiple records to the same partition, the producer can preserve its send order within that partition. This is the foundation for emitting events in sequence such as order creation, payment confirmation, and status updates.

However, this guarantee has a specific scope. It does not establish a total order across multiple partitions, does not automatically sort concurrent calls from multiple threads into business order, and does not establish a causal order across multiple independent producers. To keep the system in the right order, you must coordinate keys, partitioning, producer configuration, asynchronous sending, and business flow design.

## 1. What is the scope of ordering in Kafka?

Each partition is an ordered log. Kafka assigns monotonically increasing offsets to records appended to that partition. Consumers read a partition in offset order.

For example, topic `orders` has two partitions:

```text
orders-0:
offset 0 -> OrderCreated(order-101)
offset 1 -> PaymentRequested(order-101)
offset 2 -> OrderConfirmed(order-101)

orders-1:
offset 0 -> OrderCreated(order-202)
offset 1 -> PaymentRequested(order-202)
```

In partition `orders-0`, the record at offset 0 precedes offset 1 and offset 2. Similarly, `orders-1` has its own order. There is no shared offset to conclude whether a record at `orders-0` offset 2 occurred before or after a record at `orders-1` offset 1.

Principles to remember:

- Kafka guarantees order within a single partition; it does not guarantee total order across partitions.
- Offsets only have meaning within the scope of a topic and partition.
- Producers can route records to a partition via key, partitioner, or explicit partition assignment.
- A single producer can preserve its own send order to the same partition when retry configuration preserves ordering guarantees.
- Multiple producers sending to the same partition are appended by Kafka in the order the broker receives and processes requests; Kafka does not know the business order the application intends.

## 2. A single producer sending multiple records to the same partition

`KafkaProducer` sends asynchronously. When the application calls `send()`, the record is serialized and placed into a buffer; the producer batches records per partition and sends requests to the broker. The application does not have to wait for each record to finish before sending the next one.

If `send()` calls happen sequentially on the same producer and target the same partition, the producer preserves the order of those records when writing to the partition, provided retry settings do not break ordering guarantees.

Example of a service emitting three events for the same order:

```java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
class OrderEventPublisher {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    OrderEventPublisher(
            KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    void publishOrderLifecycle(String orderId) {
        kafkaTemplate.send(
                "orders",
                orderId,
                new OrderCreated(orderId)
        );

        kafkaTemplate.send(
                "orders",
                orderId,
                new PaymentRequested(orderId)
        );

        kafkaTemplate.send(
                "orders",
                orderId,
                new OrderConfirmed(orderId)
        );
    }
}
```

With the default partitioner and the same `orderId` key, the three records are typically routed to the same partition. The same producer sends them in call order. When idempotence is enabled and configuration constraints are valid, the producer preserves order even if requests must be retried.

There is no need to call `get()` after every `send()` just to preserve order in a sequential send flow. Waiting on every future reduces batching efficiency and throughput. Observe results asynchronously while configuring the producer to preserve order across retries.

## 3. Keys group events of the same entity

With the default partitioner, the key is hashed to select a partition. Records with the same key are typically routed to the same partition under the same topic state and partitioning strategy.

Example:

```java
kafkaTemplate.send("orders", "order-101", createdEvent);
kafkaTemplate.send("orders", "order-101", paymentRequestedEvent);
kafkaTemplate.send("orders", "order-101", confirmedEvent);

kafkaTemplate.send("orders", "order-202", createdAnotherOrder);
```

Events for `order-101` can all go into one partition, while `order-202` can go into another partition. This allows multiple orders to be processed in parallel across partitions, while each order's events stay in a single ordered stream.

The key is not a partition number. It is an input to the partitioner. Keep in mind:

- The key must be stable for the entity that needs ordering, such as `orderId` or `accountId`.
- If the key is `null`, the partitioner may use sticky partitioning to distribute batches; do not rely on null keys to preserve per-entity order.
- You can specify the partition directly in `ProducerRecord`, in which case the application is responsible for choosing the right partition.
- Changing the partition count can cause a key to hash to a different partition. Old records stay in the old partition, while new records may go to the new partition, breaking continuous key-based ordering across the two partitions.

Example of sending to an explicit partition:

```java
import org.apache.kafka.clients.producer.ProducerRecord;

ProducerRecord<String, OrderEvent> record =
        new ProducerRecord<>(
                "orders",
                2,
                "order-101",
                new PaymentRequested("order-101")
        );

kafkaTemplate.send(record);
```

Only use an explicit partition when there is a clear partitioning rule. Hard-coding partition numbers across many services makes scaling partitions or changing topology difficult.

## 4. Idempotent producer protects order during retries

When a producer sends requests to a broker, network errors or timeouts can occur. In some cases, the broker has already written the batch, but the response fails to reach the producer. The producer cannot be sure whether the batch was written, so it may retry.

With multiple in-flight requests, if an earlier batch hits a transient error while a later batch succeeds, uncontrolled retries can cause the later batch to appear before the earlier batch. This is the reordering risk when idempotence is disabled.

Kafka supports an idempotent producer. The broker assigns a Producer ID and producer sequences to batches; on retry, the broker recognizes the sequence to deduplicate resent records and preserve the producer's exact order in the partition.

Related properties:

| Property | Recommended value when ordering across retries is needed | Role |
|---|---:|---|
| `enable.idempotence` | `true` | Enables producer sequence tracking and deduplicates internal retries |
| `acks` | `all` | Waits for acknowledgment according to the current ISR |
| `retries` | Greater than `0` | Allows the producer to retry recoverable errors |
| `max.in.flight.requests.per.connection` | No greater than `5` | Stays compatible with idempotent producer limits |

When enabling idempotence, Kafka requires compatible related settings. In modern client versions, the producer may automatically apply suitable defaults; declaring them explicitly makes the configuration easier to audit and prevents unintended changes.

Idempotence protects internal retries within the same producer session. It does not automatically deduplicate cases where the application explicitly calls `send()` again after a failed future, nor does it coordinate ordering between multiple independent producers.

## 5. Producer configuration in Spring Boot

You can configure the producer in `application.yml`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      acks: all
      properties:
        "[enable.idempotence]": true
        "[retries]": 2147483647
        "[max.in.flight.requests.per.connection]": 5
        "[delivery.timeout.ms]": 120000
        "[request.timeout.ms]": 30000
```

Native Kafka keys containing dots are preserved using bracket syntax in Spring Boot property maps. Verify how properties actually bind in your application's Spring Boot version.

You can also configure them directly when constructing a `ProducerFactory`:

```java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.support.serializer.JsonSerializer;

Map<String, Object> properties = new HashMap<>();

properties.put(
        ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
        "localhost:9092"
);
properties.put(
        ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class
);
properties.put(
        ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
        JsonSerializer.class
);
properties.put(ProducerConfig.ACKS_CONFIG, "all");
properties.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
properties.put(ProducerConfig.RETRIES_CONFIG, Integer.MAX_VALUE);
properties.put(
        ProducerConfig.MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION,
        5
);
properties.put(ProducerConfig.DELIVERY_TIMEOUT_MS_CONFIG, 120_000);
properties.put(ProducerConfig.REQUEST_TIMEOUT_MS_CONFIG, 30_000);

ProducerFactory<String, OrderEvent> producerFactory =
        new DefaultKafkaProducerFactory<>(properties);
```

`delivery.timeout.ms` is the upper bound on total time to report success or failure after a producer starts sending, including waiting and retries. `request.timeout.ms` limits how long to wait for a response to a single request. Both values must be compatible with each other and with `linger.ms`; do not set delivery timeout smaller than the sum of request timeout and linger time as required by the Kafka client.

`acks=all` does not mean every assigned replica always acknowledges. The broker waits for replicas currently in the ISR according to Kafka's protocol. You can combine this with topic-level `min.insync.replicas` to enforce a minimum durability threshold on writes.

## 6. What happens if idempotence is disabled?

Suppose the same producer sends two batches to the same partition:

```text
Send order:
  Batch A: OrderCreated
  Batch B: PaymentRequested

Failure scenario with idempotence disabled:
  1. The broker has not acknowledged Batch A due to a request error.
  2. Batch B is sent and written successfully.
  3. The producer retries Batch A.
  4. The broker writes Batch A after Batch B.

The order in the log can become:
  PaymentRequested
  OrderCreated
```

This scenario can happen when multiple in-flight requests and retries are allowed without idempotence enabled. If idempotence cannot be used, one way to preserve order is setting `max.in.flight.requests.per.connection=1`, restricting the producer to a single uncompleted request per connection. In exchange, throughput may drop due to losing request pipelining.

With modern producers, the usually appropriate choice is enabling idempotence and keeping `max.in.flight.requests.per.connection` within the supported limit, rather than lowering it to 1 without measurement-backed justification.

## 7. Asynchronous sending and tracking results

`KafkaTemplate.send()` returns a future. The application can register a callback to handle the result without blocking the sending thread:

```java
import org.springframework.kafka.support.SendResult;

import java.util.concurrent.CompletableFuture;

CompletableFuture<SendResult<String, OrderEvent>> future =
        kafkaTemplate.send("orders", orderId, event);

future.whenComplete((result, exception) -> {
    if (exception != null) {
        log.error(
                "Publish failed: orderId={}",
                orderId,
                exception
        );
        return;
    }

    var metadata = result.getRecordMetadata();

    log.info(
            "Published order event: key={}, topic={}, partition={}, offset={}",
            orderId,
            metadata.topic(),
            metadata.partition(),
            metadata.offset()
    );
});
```

The example uses the `CompletableFuture` API from Spring Kafka 3.x. Some older Spring Kafka versions return `ListenableFuture`; use the API type matching your application's dependency.

The send result confirms that the record was acknowledged by the broker and provides the topic, partition, and offset. Do not treat simply calling `send()` as proof that the record was written successfully.

Callbacks help observe results, but you should not use callback completion to reorder records that have already been sent. If event B must only be emitted after event A has been acknowledged or after business step A finishes, model that dependency at the application layer.

## 8. A single producer called from multiple threads

Kafka producers are thread-safe: multiple threads can call `send()` on the same producer. The producer manages internal buffers and requests to send data.

However, thread safety does not equate to automatic business ordering. If two threads simultaneously emit events for the same order, the order in which the producer receives those calls may differ from the intended business order.

Example:

```text
Thread A: sends OrderCreated(order-101)
Thread B: sends PaymentRequested(order-101)
Thread B can call send before Thread A if scheduling changes.
```

Even with the same key and same partition, both records can still be appended in the actual call arrival order at the producer. Kafka does not know that `OrderCreated` must precede `PaymentRequested`.

If per-aggregate or per-key ordering must be preserved:

- Serialize event emission for the same aggregate before calling the producer.
- Use a keyed executor or queue partitioned by key so each key only has one publishing flow at a time.
- Attach a sequence number or aggregate version to the event so consumers can detect out-of-order arrivals.
- Parallelize only across different keys when business rules allow.

A simple illustration of the idea: all events for `order-101` pass through one sequential processing queue; events for `order-202` can pass through another queue. This preserves order per order while utilizing parallelism across orders.

## 9. Multiple producers sending the same key

Suppose two instances of the same service both send records with key `order-101` to topic `orders`. The partitioner may route both records to the same partition, yet each instance is an independent producer with its own Producer ID and sequence.

Kafka writes records in the order the broker processes the requests. It does not know which event comes first in business order. Idempotence on each producer does not coordinate sequences across two producers.

Common solutions:

- Assign a single publisher to own a key or shard at any given time.
- Route event emission commands through a sequential queue/actor per aggregate ID.
- Use a transactional outbox and a relay mechanism with stable partitioning that guarantees event retrieval order per aggregate.
- Include an aggregate version or sequence number in the payload so the consumer can validate, reject, or wait for missing events.
- Use optimistic locking or fencing tokens to stop an old publisher from continuing to emit after ownership has transferred.

Do not assume that sharing the same key is enough to coordinate multiple producers. Keys help select partitions; they are not distributed locks and do not lock application instances.

## 10. Changing partition count can affect key-based ordering

With the default hash partitioner, the partition is chosen based on the key's hash and the current partition count. When increasing partitions, the same key can be mapped to a different partition.

Example before increasing partitions:

```text
order-101 -> orders-1
```

After the topic increases partitions:

```text
order-101 -> orders-4
```

Old records for `order-101` remain in `orders-1`, while new records may reside in `orders-4`. The two partitions have independent orders, so consumers cannot infer a continuous order solely from offsets.

If key-based ordering is critical, plan partition scaling carefully. You can use a fixed partition count aligned with a long-term strategy, or a stable partitioning strategy with version management and migration procedures. Another option is carrying a per-aggregate sequence number so consumers verify business order independently of partition offsets.

## 11. Ordering and parallel consumer processing

A producer may write records in the right order within a partition, yet a consumer can still produce out-of-order side effects if the application hands records off to a thread pool or processes asynchronously without control.

For example, the consumer reads:

```text
offset 10 -> OrderCreated
offset 11 -> PaymentRequested
offset 12 -> OrderConfirmed
```

If the listener submits the three records to three tasks running in parallel, the task for offset 12 may finish before offset 10. Kafka still preserves log order, but database state can be updated out of sequence.

When end-to-end ordering is needed:

- Let records within the same partition be processed sequentially.
- If parallelism is needed, shard work by key while ensuring the same key always goes to the same worker/queue.
- Only commit offsets after prior records have been processed successfully under the chosen semantics.
- Use an aggregate version or sequence number to detect out-of-order records.
- Design idempotent consumers to tolerate redelivery after failures or rebalances.

Ordering inside the producer is only one piece of end-to-end ordering. You must also inspect partition assignment, consumer concurrency, asynchronous dispatch, and target data update order.

## 12. Do transactions replace idempotence?

Kafka transactions allow a producer to write multiple records to multiple partitions atomically: consumers using `read_committed` only see committed transactions. Transactions are useful when writing to multiple output topics together or combining consume-transform-produce processing under transaction configuration.

Transactions do not establish a total order across partitions. Each partition still has its own order. A transactional producer also uses the idempotence mechanism, but the goal of transactions is atomicity and producer fencing via `transactional.id`, whereas idempotence handles producer retries.

Do not treat transactions as a replacement for keys or per-aggregate event serialization strategies. If two independent producers emit events for the same aggregate concurrently, each producer's transaction does not determine which event must come first.

## 13. How to verify ordering in practice

You can create an event containing an aggregate ID and sequence number:

```java
public record OrderEvent(
        String orderId,
        long sequence,
        String eventType
) {
}
```

The producer sends in order:

```java
kafkaTemplate.send(
        "orders",
        orderId,
        new OrderEvent(orderId, 1, "OrderCreated")
);

kafkaTemplate.send(
        "orders",
        orderId,
        new OrderEvent(orderId, 2, "PaymentRequested")
);

kafkaTemplate.send(
        "orders",
        orderId,
        new OrderEvent(orderId, 3, "OrderConfirmed")
);
```

The consumer logs the sequence along with its Kafka position:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;

@KafkaListener(topics = "orders", groupId = "orders-audit")
public void audit(ConsumerRecord<String, OrderEvent> record) {
    OrderEvent event = record.value();

    log.info(
            "orderId={}, sequence={}, partition={}, offset={}, type={}",
            event.orderId(),
            event.sequence(),
            record.partition(),
            record.offset(),
            event.eventType()
    );
}
```

When testing, verify that events with the same key land in the same partition and offsets increase alongside the sequence. Also test producer retry scenarios and multiple threads sending the same key. If running multiple producer instances, test contention scenarios to verify ownership or sequence validation mechanisms.

The sequence number inside the event is business metadata managed by the application. The Kafka offset is a storage position assigned by the broker. The two values serve different purposes and must not substitute for one another.

## 14. Common errors

| Symptom | Cause | Resolution |
|---|---|---|
| Events with the same key land in different partitions | Partition count changed, different partitioner, or keys differ after serialization | Check keys, partitioner, and partition change history |
| Records are reordered during retries | Idempotence disabled with multiple in-flight requests | Enable idempotence, keep `max.in.flight` at most 5 |
| Events with the same key processed out of order | Multiple threads or consumer workers processing in parallel | Serialize processing per key or use sequence validation |
| Two producers with the same key produce unexpected order | Idempotence is scoped per individual producer | Use single-owner/shard, outbox ordering, or aggregate version |
| Futures complete in an unexpected order | Sending to multiple partitions or relying on callbacks for coordination | Use partition/offset metadata and manage dependencies at the business layer |
| Manual retries create duplicate records | Application calls `send()` again as a brand-new send | Use event ID/idempotency key and handle duplicates in the consumer |
| Increasing partitions breaks continuous key order | Keys may be remapped to a new partition | Plan migration and use sequence numbers |
| Logs show non-contiguous offsets | Compaction, aborted transactions, or records hidden by isolation level | Do not assume contiguous offsets; inspect records and isolation level |

## 15. Checklist for preserving ordering within a single producer

1. Choose a stable key representing the entity whose order must be preserved.
2. Ensure events for the same entity use the same topic and partitioning strategy.
3. Enable `enable.idempotence=true` to preserve order across producer retries.
4. Use `acks=all`, retries greater than 0, and `max.in.flight.requests.per.connection` no greater than 5 when idempotence is enabled.
5. Do not treat callback completion as a business ordering mechanism.
6. Serialize send calls for the same key if multiple threads can emit events concurrently.
7. Do not assume multiple independent producers share an order merely by using the same key.
8. Plan ahead when increasing partitions because keys may shift partitions.
9. Verify that the consumer processes sequentially per partition/key.
10. Use event IDs and sequence numbers when business-level duplicate or out-of-order detection is needed.

Kafka guarantees log order within each partition. An idempotent producer can preserve its own record order during retries to the same partition. To preserve business sequence, the application must also control send call ordering, key/partition mapping, competing producers, and how consumers execute side effects.
