# Per-Key Ordering and Limits Under Asynchronous Processing

In an event-processing system, message ordering can carry business meaning. For example, an account must be created before its balance is updated; an order must be confirmed before emitting a shipping event. If related messages are processed out of order, the final state may be incorrect even though every individual message is valid.

Spring Cloud Stream supports partitioning to distribute messages by key. Messages with the same partition key are routed to the same partition according to the binder's strategy, helping preserve ordering within the partition scope supported by the broker. However, partitioning does not create global ordering across an entire destination, nor does it automatically guarantee completion order when an application processes asynchronously. To design correctly, you must understand key selection, how the broker distributes partitions, and how consumers execute work.

## 1. Partitions and Message Ordering

A partition is an ordered segment of a destination. With Kafka, a topic can consist of multiple partitions; each partition stores records in append order. Consumers read records in a partition by offset. Multiple partitions allow parallel processing, yet there is no overall ordering across partitions.

For example, the `orders.events` stream has three partitions:

~~~text
orders.events
  partition 0: A1 -> A2 -> A3
  partition 1: B1 -> B2 -> B3
  partition 2: C1 -> C2 -> C3
~~~

Consumers can read all three partitions simultaneously. The order A1 before A2 before A3 is maintained in partition 0; the system makes no guarantee that A1 finishes before B1 in partition 1. If business logic only requires ordering per customer or per order, we can choose a key so all events for the same entity go to the same partition.

Partitioning addresses two related goals:

- **Per-key ordering:** messages with the same key are routed to the same partition, allowing sequential processing within that partition's scope.
- **Scalability:** different partitions can be processed in parallel by multiple consumers.

The partition count sets the useful parallelism limit of a consumer group. If a topic has three partitions, scaling consumers in the same group to ten does not create ten independent processing streams for that topic; some consumers will receive no partition assignment.

## 2. Choosing a Partition Key by Business Entity

A partition key is the value used to decide which partition a message belongs to. The key should represent the entity for which business logic requires ordering:

| Business Flow | Usually Suitable Key | Reason |
|---|---|---|
| Order status updates | `orderId` | Changes for the same order must be processed in sequence |
| Account transaction ledger | `accountId` | Transactions for one account must be serialized |
| Customer profile updates | `customerId` | Changes for the same customer should not race |
| Inventory handling by SKU | `sku` | Updates to the same product need coordination |

Do not choose a random key per message when the goal is per-entity ordering. A random key scatters events of the same entity across multiple partitions. Timestamps are also not an automatic substitute: two producers can generate skewed timestamps, clocks can drift, and timestamps do not guarantee the order in which the broker receives messages.

Keys must be stable, present on every message in the same business stream, and consistently represented. If `customerId` is sometimes null or normalized differently across producers, the same customer can be split across multiple key groups. Validate keys before publishing and standardize normalization rules.

## 3. Configuring Partitioning on the Producer

Spring Cloud Stream provides shared partitioning properties at the producer level. For example, all events for the same customer use `customerId` as the partition key:

~~~yaml
spring:
  cloud:
    function:
      definition: publishOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.events
          producer:
            partition-key-expression: payload.customerId
            partition-count: 12
~~~

In this configuration:

- **partition-key-expression** is the SpEL expression used to extract the key from the message. `payload.customerId` reads the `customerId` field of the payload.
- **partition-count** is the number of partitions the producer uses in partition selection.
- **destination** identifies the logical stream to which messages are published.

For a message with an `OrderEvent` payload, the expression can be `payload.orderId` or `payload.accountId` depending on ordering requirements. If using a header as the key, the expression can reference the header, such as `headers['partitionKey']`; the producer must ensure that header exists and has an appropriate value type.

Spring Cloud Stream can use custom partition key extractors and partition selectors when default expressions do not meet requirements. You can declare extractor/selector beans and reference them by name in producer configuration. Only customize when there is a clear partitioning rule; all producers must use the same algorithm and key normalization so an entity does not shift to another partition.

`partition-count` must be compatible with the actual partition count supported by the binder/broker. With Kafka, the topic needs enough partitions; producer configuration does not automatically expand an existing topic's partitions in every deployment mode. Verify the topic before releasing.

## 4. How a Key Maps to a Partition

Conceptually, the producer performs two steps:

1. Extract the partition key from the payload or header.
2. Pass the key through the partition selector to pick a partition within the partition count range.

With a hash-based selector, repeated sends with the same key select the same partition as long as the algorithm and partition count do not change:

~~~text
partitionKey = customerId
partition = selector(partitionKey, partitionCount)

customer-10 -> partition 2
customer-20 -> partition 0
customer-10 -> partition 2
customer-30 -> partition 1
~~~

The numbers in the diagram are illustrative only. Do not assume the partition ID always equals `hashCode` modulo `partitionCount`; the exact algorithm depends on the selector, binder, and version. What must be preserved is that every producer participating in the same stream applies the same rule so events for one key are routed consistently.

If using a custom partition selector, test cases with null keys, empty keys, Unicode, negative values, and skewed key distributions. Avoid algorithms that return out-of-range partitions or concentrate most traffic onto one partition.

A partition key only determines where a message is written. If two producers simultaneously emit events for an `orderId`, the order in which the broker receives them may differ from the business order the two producers intended. To achieve deterministic business ordering, you need a single coordinator or a consistently assigned sequence/version for the aggregate; partitioning does not automatically sort messages by timestamp or sequence.

## 5. Consumer Groups and Partition Distribution

Consumers in the same group typically split processing of a destination's partitions. With Kafka, the broker and Kafka consumer group coordinator assign partitions to member consumers. At any given time, a partition is assigned to only one consumer within the same group, while other groups can read the same topic independently.

~~~text
Topic orders.events: 6 partitions

Consumer group: order-projection
  consumer A <- partitions 0, 1
  consumer B <- partitions 2, 3
  consumer C <- partitions 4, 5

Consumer group: billing
  consumer D <- partitions 0, 1, 2
  consumer E <- partitions 3, 4, 5
~~~

This example shows two services reading the same topic using different groups. Within each group, partitions are split across instances; each group tracks its own consumption progress. If instances of the same service accidentally use different groups, they can each receive the entire stream independently instead of sharing load.

With the Kafka binder, consumer group assignment is Kafka's native mechanism. When the instance count changes, Kafka can rebalance and reassign partitions. With Spring Cloud Stream's generic partitioned consumer model, `instance-count`, `instance-index`, and `consumer.partitioned` can be used to describe the total instance count and instance index; exact applicability depends on the binder. Do not mix native binder assignment with instance-level configuration without checking the documentation for the version in use.

## 6. Partition Order Is Not Completion Order

The broker may deliver messages in order within a partition, yet the application can still complete processing out of order if it runs multiple asynchronous tasks.

For example, a consumer receives sequentially:

~~~text
Message:  A1 -> A2 -> A3
Start:    A1    A2    A3
Finish:   A2    A3    A1
~~~

If A1 updates an order status to PAID and A2 updates it to SHIPPED, A2 finishing before A1 can overwrite the final state incorrectly. This is a bug in the application's execution layer, even though the broker delivered the messages in order.

Some common causes:

- Using `flatMap` with asynchronous I/O tasks that have varying completion times.
- Using a shared thread pool or executor to process multiple messages concurrently.
- Calling external APIs or databases with variable latency.
- Committing offsets or acknowledging messages before side effects complete.
- Having multiple consumers or subscriptions update the same entity without synchronization locking.

To preserve ordering, you must control receive order, execution start order, completion order, and commit/acknowledgment timing.

## 7. Serializing Processing with Reactor

In a reactive pipeline, `concatMap` processes elements one by one: the publisher for the current element completes before the next element is processed. For example:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

record OrderEvent(String orderId, String status, long sequence) {}

record OrderResult(String orderId, String status, long sequence) {}

@Configuration
class OrderedOrderFunctions {

    private Mono<OrderResult> applyOrderEvent(OrderEvent event) {
        // Replace with actual asynchronous business operation.
        return Mono.just(new OrderResult(
                event.orderId(), event.status(), event.sequence()));
    }

    @Bean
    Function<Flux<OrderEvent>, Flux<OrderResult>> processInOrder() {
        return events -> events.concatMap(this::applyOrderEvent);
    }
}
~~~

`concatMap` preserves the input stream's emission order in the output stream, while running only one task at a time in that pipeline. This is simple and safe when stream-wide ordering matters, at the cost of throughput being bounded by the slowest task.

`flatMap` allows multiple tasks to run concurrently and can emit results in completion order. It is suitable when messages are independent or business logic does not require ordering. Do not replace `concatMap` with `flatMap` just to boost throughput if messages for the same entity have state dependencies.

Reactor also provides `flatMapSequential`: it can subscribe to and run multiple tasks concurrently while preserving output emission order matching input element order. This only reorders output signals; side effects inside tasks can still occur out of order. If tasks update the same aggregate and the writes themselves must be sequential, `flatMapSequential` does not replace `concatMap` or per-key synchronization.

If you want parallelism across keys while preserving order within each key, partition by key at the broker layer and process each partition sequentially, or design a per-key coordinator. Using `groupBy` followed by `concatMap` in Reactor requires bounding concurrency, managing group counts, and controlling buffers; it should not be applied blindly to an unbounded key space.

## 8. Asynchronous Example That Reorders Execution

Suppose a service updates order status using an I/O call:

~~~java
Flux<OrderResult> unsafe =
        events.flatMap(event ->
                orderService.updateAsync(event));
~~~

`flatMap` can start processing A1, A2, and A3 almost simultaneously. If A2 completes before A1, its result is emitted before A1. If each task writes to the same order record, the final state can depend on completion order rather than event order.

When the entire pipeline must be serialized:

~~~java
Flux<OrderResult> ordered =
        events.concatMap(event ->
                orderService.updateAsync(event));
~~~

When ordering is only needed per `orderId`, distribute load so all events with the same `orderId` enter the same partition and ensure sequential processing within that partition. Other partitions can still run in parallel. If a single partition uses multiple threads for async processing, completion order can still invert; maintain a sequential processing chain per partition or lock by entity.

## 9. Ordering and Limits by Broker

Partitioning is a shared concept, but the physical semantics of each broker differ:

| Broker | Ordered Unit | How to Preserve Per-Key Order | Limits to Remember |
|---|---|---|---|
| Kafka | Records within one partition | Use a stable record key/partition key so the same key goes to the same partition | No ordering across partitions; concurrent consumer processing can finish out of order |
| RabbitMQ | Messages in one queue in broker enqueue order | Use exchange/routing key and queues partitioned by key or shard | Multiple consumers, large prefetch, requeues, and async processing can make completion order differ from receive order |
| Pulsar | Messages in a topic partition; semantics depend on subscription | Use message key and a subscription type supporting key-based distribution | `Key_Shared` routes the same key to the same consumer per Pulsar's mechanism; ordering and redelivery still depend on configuration |

### Kafka

Kafka guarantees record order within a single partition by offset. If all events for an `orderId` use the same record key, they can be read in order within that partition. A consumer group divides partitions among consumers, without creating global ordering across partitions. When producers use retries or async sends, check producer settings to preserve required send order; do not deduce guarantees solely from the partition key.

Increasing a topic's partition count can alter key-to-partition mapping for producers using modulo hashing on the partition count. Older messages for a key remain in the old partition while newer messages may go to another partition. If continuous ordering is needed across partition expansion, plan a migration, drain the old stream, or use a controlled versioning/sharding strategy.

### RabbitMQ

RabbitMQ routes messages from exchanges to queues. A single queue provides enqueue order, yet with multiple consumers, high prefetch counts, async acknowledgments, or requeued messages, processing completion order can diverge from queue order. To keep per-key ordering, design routing and queue sharding so the same key lands in the same queue while controlling consumer count and acknowledgment behavior.

Do not assume simply declaring a partition key in the application automatically creates the desired queue topology for every Rabbit binder configuration. Inspect how the binder creates exchanges, queues, routing keys, and dead-letter resources.

### Pulsar

Pulsar supports partitioned topics and message keys. Subscription type affects how consumers receive messages. With `Key_Shared`, messages with the same key are delivered to the same consumer per Pulsar's mechanism, enabling parallel processing across keys. Check batching, redelivery, and acknowledgment settings because they can affect ordering observed at the application layer.

Do not treat `Shared` and `Key_Shared` as equivalent. `Shared` distributes messages across consumers for load sharing without committing that the same key always reaches the same consumer. Choose the subscription type based on ordering and throughput requirements.

## 10. Changing Partition Count and Load Distribution

The partition count affects parallelism, storage footprint, key distribution, and how work is assigned to consumers. Increasing partitions can raise throughput, though it is not a free change:

- Keys can map to different partitions if the algorithm depends on partition count.
- Older and newer messages for the same key may land in two different partitions.
- Consumer groups may rebalance and temporarily alter processing capacity.
- The broker needs additional resources and metadata for new partitions.
- High-frequency keys still concentrate on a single partition, creating hot partitions.

If one customer generates far more events than all others, picking `customerId` as the key can make one partition hot. Increasing the partition count will not solve a single key funneling into one partition. Revisit the unit of serialization, shard by sub-entity, or split event types—but never split a key if doing so violates business ordering requirements.

Do not change the partition count based solely on the desired number of consumers. Measure throughput, lag, key distribution, processing latency, and broker capacity before deciding.

## 11. Error Handling, Retries, and Ordering

Retries can alter observed order. For example, A1 fails and retries while A2 has already been processed. If A2 updates state first and then A1 succeeds on retry, state can regress to an older value.

Ways to mitigate this:

- Process sequentially within a partition or key scope when business rules require it.
- Use a sequence number or version on the aggregate to detect stale events.
- When updating data, accept only a version newer than the stored version.
- Distinguish transient errors from non-recoverable errors; never infinitely retry a message with bad data.
- Use a DLQ and controlled replay procedures; replay must account for the ordering of subsequent messages.
- Design idempotent consumers so redelivery does not create duplicate side effects.

Example sequence check:

~~~java
if (event.sequence() <= currentState.lastSequence()) {
    // Skip stale or already processed message.
    return;
}

apply(event);
saveLastSequence(event.sequence());
~~~

This is pseudocode; checking and updating the version must be atomic in the data store if multiple processes can update the same aggregate. Sequence numbers detect stale messages, yet do not automatically recover a missing message. If a sequence gap is detected, the application must wait, re-query, or mark the aggregate for reconciliation.

## 12. Testing Per-Key Ordering

Testing should verify both partition keys and processing order:

1. Send multiple events with the same key and ascending sequence numbers.
2. Send events for multiple different keys to confirm they can be processed in parallel.
3. Inspect the actual partition or queue where the broker receives the messages.
4. Simulate slow consumer processing to observe completion order.
5. Simulate errors and retries to check whether later messages overtake a failing message.
6. Test rebalancing or consumer restarts mid-processing.
7. Try changing the partition count in a test environment and validate the migration plan.

Spring Cloud Stream's Test Binder is suitable for testing partition key expressions, headers, and function logic at the application level when configured appropriately. However, the Test Binder does not prove Kafka partition assignment, RabbitMQ routing, or Pulsar `Key_Shared`. Those guarantees require integration tests with the real binder and broker.

## 13. Observing Ordering and Partition Health

In production, monitor:

- Consumer lag or backlog per partition/queue/subscription.
- Message rate per partition and signs of hot partitions.
- End-to-end duration from receive to processing completion.
- Retry counts, messages entering the DLQ, and time spent in the DLQ.
- Rebalance counts, unassigned consumers, and concurrency changes.
- Sequence gaps, skipped stale events, and version update failures.

Logs should contain the aggregate key, `eventId`, sequence, partition (if available), consumer instance, and processing start/end timestamps. Avoid logging only timestamps without a sequence or event ID; timestamps are insufficient to prove business ordering.

## 14. Design Checklist

- Choose a partition key around the entity requiring ordering, such as `orderId` or `accountId`.
- Ensure the key is always populated and normalized identically across all producers.
- Configure a partition count suited to the broker and scaling plan.
- Use the same partition selection rule across producers sharing a destination.
- Understand groups and how the binder assigns partitions to consumer instances.
- Distinguish broker message delivery order from application processing completion order.
- Use `concatMap` or per-partition/per-key serialization when needed.
- Control retries, redeliveries, acknowledgments, and DLQs to avoid applying an older event after a newer one.
- Maintain an event sequence/version and perform atomic state updates when required by business logic.
- Test against a real broker, covering errors, restarts, rebalances, and partition count changes.

A partition key funnels messages for the same entity into the same ordered scope while allowing other partitions to run in parallel. That guarantee is only useful when producers select keys consistently and consumers do not invert order during asynchronous processing. The design must combine partitioning, consumer concurrency, retries, business versioning, and broker testing to uphold the ordering your system truly requires.
