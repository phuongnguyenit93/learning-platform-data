# Transactions in a Consume-Process-Produce Flow

In an event-processing application, a record typically goes through three steps: consuming an event from Kafka, executing business logic, and producing a result event to another topic. If the application simply commits the input offset after sending the output successfully, there is still a window between those two operations during which the process could crash. Kafka transactions close this gap by grouping the output records and the input offset into a single Kafka transaction.

When the transaction commits, Kafka publishes the output records and stores the input offset as an atomic unit. When the transaction aborts, the output records are not visible to consumers in `read_committed` mode and the input offset is not committed in that transaction. The broker can redeliver the input record so the application can reprocess it.

In Spring Cloud Stream, the Kafka binder supports this model using Spring for Apache Kafka's transaction support. When transactions are enabled on the binder, producer bindings send data within a transaction; for a consume-process-produce flow, the binder can bind sending results and committing offsets into the same transaction boundary.

## 1. Why are transactions needed in a processing pipeline?

Suppose an `order-processor` service receives records from the `orders.submitted` topic, validates the order, and emits the result to `orders.accepted`. If the application sends the result and commits the offset as two independent operations, there are two failure scenarios:

| When the process stops | Possible consequence |
|---|---|
| After sending `orders.accepted` but before committing the input offset | The input record is redelivered; the application may emit duplicate results |
| After committing the input offset but before sending `orders.accepted` | The input record has already been acknowledged; the output result may be lost |

Kafka transactions allow writing output records and the input offset into the same transaction:

~~~mermaid
flowchart TD
    A["Read record from orders.submitted"] --> B["Start Kafka transaction"]
    B --> C["Run processing logic"]
    C --> D["Send record to orders.accepted"]
    D --> E["Include input offset in transaction"]
    E --> F{"Commit transaction"}
    F -->|Success| G["Output and offset committed together"]
    F -->|Error| H["Abort transaction"]
    H --> I["Output hidden from read_committed; input can be redelivered"]
~~~

The key point is that the input offset and the output records must participate in the same Kafka transaction. Enabling an idempotent producer alone or setting a consumer isolation level alone does not provide atomicity for the entire pipeline.

## 2. What do Kafka transactions guarantee?

A Kafka transaction provides atomicity for write operations belonging to the same transaction within a single Kafka cluster. A transaction can write multiple records, even across multiple topics and partitions. With consume-transform-produce, the processed offset can be sent into that very same transaction.

| Scenario | Result |
|---|---|
| Transaction commits | Output records are published along with the input offset |
| Transaction aborts | Output records of the transaction are not read by `read_committed` consumers; the input offset is not committed in the transaction |
| Consumer reads with `read_committed` | Reads only records from committed transactions and non-transactional records |
| Consumer reads with `read_uncommitted` | May see records from uncommitted or aborted transactions |

Kafka uses a transaction coordinator to manage transaction state and commit/abort markers. `read_committed` consumers rely on that state to determine which records are allowed to be exposed.

### 2.1. Transactions vs. idempotent producers

An idempotent producer prevents a retried send at the producer layer from creating duplicate records due to network retries within a Kafka-managed producer session/sequence. It does not automatically group multiple sends and consumer offsets into an atomic unit.

Kafka transactions add:

- Grouping multiple sends into a single commit or abort boundary.
- Allowing consumer offsets to be sent into the same transaction as output records.
- Allowing downstream `read_committed` consumers to filter out data from aborted transactions.

Idempotence is an essential foundation for transactional producers, but idempotence alone does not equal consume-process-produce exactly-once.

### 2.2. Scope of exactly-once

In a Kafka-to-Kafka pipeline, transactions can ensure that output results and input offsets are committed together. This is commonly referred to as exactly-once processing within the scope of Kafka.

It does not mean:

- The business function is only invoked once. When a transaction aborts, the function may be executed again.
- All side effects outside Kafka are rolled back.
- Database writes, HTTP calls, sending emails, or payments automatically become part of the Kafka transaction.
- Two different Kafka clusters participate in a single atomic transaction.
- The application does not need idempotency or duplicate handling in external non-Kafka systems.

Therefore, you must clearly define the transactional guarantee boundary before calling a processing flow "exactly-once".

## 3. Enabling transactions for the Kafka binder

The Kafka binder enables transactions when a transaction ID prefix is configured. Example:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.submitted
          group: order-processor
        processOrder-out-0:
          destination: orders.accepted
      kafka:
        binder:
          brokers: kafka-1:9092
          transaction:
            transactionIdPrefix: order-processor-pod-01-
~~~

The key property is:

~~~text
spring.cloud.stream.kafka.binder.transaction.transactionIdPrefix
~~~

When a transaction ID prefix is configured, the Kafka binder uses a transactional producer for output bindings. In a consumer-initiated transaction flow, the listener container starts a transaction upon receiving a record; the results sent to Kafka and the input offset are processed within the same transaction via the binder mechanism.

The example above uses an illustrative prefix for a single instance. In production, every concurrently active instance needs a unique prefix. You can obtain the pod or instance identity from the deployment platform and inject it into the configuration. Do not share the same prefix across multiple concurrently running instances because Kafka may fence the older producer when it detects a duplicate transactional ID.

### 3.1. Transaction ID prefix and transactional.id

A Kafka producer requires a stable and unique `transactional.id` across active producers. The Kafka binder takes the prefix and generates specific transactional IDs for the producers it manages.

| Component | Role |
|---|---|
| transactionIdPrefix | Prefix configured on the binder to create transactional producers |
| transactional.id | The actual transaction identity of the Kafka producer |
| consumer group | Identity of the consumer group sharing partitions and storing offsets |
| topic/partition | Where input and output records are stored |

The prefix is neither the consumer group nor the topic name. Each replica needs a different prefix; producers within the same instance can be assigned distinct suffixes managed by the binder.

If two instances use the same transactional ID, the broker can bump the producer epoch and fence one of the producers. A `ProducerFencedException` usually indicates that another producer is using the same transactional ID or an older producer is still active.

## 4. Processing a message with an imperative Function

Example of a `Function` receiving an order and returning an accepted event:

~~~java
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderSubmitted(
    String orderId,
    String customerId,
    int quantity
) {}

record OrderAccepted(
    String orderId,
    String customerId,
    int quantity,
    String status
) {}

@Configuration
class OrderConfiguration {

    @Bean
    Function<OrderSubmitted, OrderAccepted> processOrder() {
        return order -> {
            if (order.quantity() <= 0) {
                throw new IllegalArgumentException("quantity must be positive");
            }

            return new OrderAccepted(
                order.orderId(),
                order.customerId(),
                order.quantity(),
                "ACCEPTED"
            );
        };
    }
}
~~~

When running with a transaction-enabled Kafka binder, the output of the `Function` is sent via the output binding belonging to the binder-managed transaction. The input record's offset is committed with the transaction only when processing and output sending complete.

An imperative `Function` fits the consumer-initiated transaction model because the binder can wrap the message handler invocation in a transaction boundary. For a reactive `Function`, do not assume the listener's thread-bound transaction automatically spans the entire asynchronous pipeline; verify support in your binder version and execution model.

## 5. Transactions spanning multiple output bindings

A single processing step can emit multiple events to different topics. When the output bindings use the same Kafka binder and the same active transaction, the records sent within that transaction can commit or abort together.

For example, an accepted order needs to emit two events:

- `orders.accepted` for the order service to continue processing.
- `inventory.reservations` for the inventory service to reserve stock.

The function can use explicit output bindings via `StreamBridge` or a function design returning multiple outputs depending on the application model. When using `StreamBridge`, the send must join the active transaction; do not create an independent producer/transaction and expect it to be merged into the input binding's transaction.

~~~java
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
class OrderEventPublisher {

    private final StreamBridge streamBridge;

    OrderEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    void publish(OrderAccepted accepted) {
        Message<OrderAccepted> message = MessageBuilder
            .withPayload(accepted)
            .setHeader("eventType", "OrderAccepted")
            .build();

        if (!streamBridge.send("accepted-out-0", message)) {
            throw new IllegalStateException("Could not send OrderAccepted");
        }
    }
}
~~~

Declaring the output binding for `StreamBridge`:

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: accepted-out-0
      bindings:
        accepted-out-0:
          destination: orders.accepted
~~~

If using `StreamBridge` instead of a `Function` return value, you can invoke the publisher synchronously from a `Consumer` handled by the binder:

~~~java
@Bean
Consumer<OrderSubmitted> processOrder(OrderEventPublisher publisher) {
    return order -> {
        if (order.quantity() <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        publisher.publish(new OrderAccepted(
            order.orderId(),
            order.customerId(),
            order.quantity(),
            "ACCEPTED"
        ));
    };
}
~~~

Binding names and invocation patterns must match the application configuration. When sending via `StreamBridge` inside a consumer-initiated transaction, verify that the producer binding uses the same binder and transaction context. If an output binding points to a different binder or cluster, the current Kafka transaction cannot make both clusters commit atomically.

If one of the sends fails and the exception propagates before commit, the transaction can abort previously sent records in the same transaction as well. Do not catch and ignore the exception if you want the transaction to roll back; silently catching and handling errors can cause the transaction to commit even though business processing did not complete.

## 6. Consumers reading transactional data with read_committed

Kafka consumers have an isolation level:

| Isolation level | Readable data |
|---|---|
| read_uncommitted | Uncommitted, committed, or aborted transactional records; does not wait for transactions to finish for filtering |
| read_committed | Non-transactional records and records from committed transactions; skips records from aborted or in-progress transactions |

Downstream consumers need `read_committed` if they must only process committed data. This can be configured per binding:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          auditOrders-in-0:
            consumer:
              configuration:
                isolation.level: read_committed
~~~

This is a Kafka consumer configuration specific to the `auditOrders-in-0` binding. Check the mapped binding name and actual binder configuration. Do not put `isolation.level` in producer configuration since it is a consumer property.

`read_committed` consumers may see data later if an earlier transaction on the partition is still open. Kafka only allows reading up to the Last Stable Offset (LSO), which is the safe position before any open transaction. Therefore, overly long transactions can increase downstream consumer latency even though records have already been appended to the log.

## 7. What happens when a transaction aborts?

Suppose the `Function` receives `order-501`, sends `OrderAccepted`, and then encounters an error before the transaction commits. Aborting the Kafka transaction marks the output records in the transaction as uncommitted. `read_committed` consumers do not see that `OrderAccepted` record.

The offset of `order-501` is also not committed in the aborted transaction. When the consumer continues, the input record can be redelivered and the processing logic executed again.

Steps to distinguish:

1. An exception occurs in processing logic or during output sending.
2. The current transaction is rolled back/aborted.
3. Output records sent within the transaction are not exposed to `read_committed`.
4. The input offset is not committed in the transaction.
5. The consumer may reprocess the input record.

This is why business logic needs to be safe to re-run. Kafka transactions protect the atomicity of Kafka data; they do not prevent code from being invoked again after a rollback.

### 7.1. Retry and poison messages

A message with a transient error can be retried after rollback. However, an invalid message can cause repeated transaction aborts. A policy is needed for:

- Bounded retries with backoff for transient errors.
- Classifying unrecoverable data errors to avoid infinite retries.
- A recovery or DLQ mechanism compatible with the binder's transaction mode.
- Monitoring rollback counts, retries, and backlogged messages.

When transactions are enabled, do not assume every retry/DLQ property from the non-transactional imperative binder behaves identically. Check the documentation and APIs of the Spring Cloud Stream/Spring Kafka version in use, especially how the binder configures `AfterRollbackProcessor`, error handlers, and DLQ publishing. If failed messages need to be routed to a DLQ, verify that DLQ publishing participates appropriately in transactions and offsets are only committed according to the desired policy.

## 8. Transaction boundaries with databases and external services

A Kafka transaction does not automatically participate in PostgreSQL, MySQL, Redis, or HTTP service transactions. For example:

1. The `Function` writes the order to the database.
2. The `Function` sends `OrderAccepted` to Kafka.
3. The Kafka transaction aborts.

The database does not automatically roll back just because the Kafka transaction aborted. Redelivering the message may write the order again or repeat a side effect outside Kafka.

### 8.1. Using idempotency for database operations

If processing a Kafka event mutates a database, you can use an inbox/deduplication table with a unique event ID. Inside a single database transaction:

1. Attempt to insert the event ID into the inbox table with a unique constraint.
2. If the ID already exists, recognize that the event was already processed and skip repeating side effects.
3. If the ID is new, apply the business changes in the same database transaction.
4. Commit the database transaction.
5. Let the binder commit the Kafka offset as part of message consumption.

If the application stops after committing the database but before committing the Kafka offset, Kafka may redeliver the message. The unique constraint in the inbox allows the subsequent attempt to detect the duplicate and avoid repeating business changes.

### 8.2. Using the transactional outbox when the database is the source of truth

If the business logic updates the database and then needs to emit a Kafka event, the transactional outbox is an option:

- In the same database transaction, update business data and insert a row into an outbox table.
- A separate publisher reads the outbox and sends events to Kafka.
- After sending succeeds, the publisher marks or deletes the outbox row per policy.
- The publisher needs idempotency since it may resend if it stops between sending and marking.

An outbox does not create a distributed transaction between the database and Kafka. It guarantees that business data and the intent to emit an event are persisted together in the database, and the publisher forwards it in a recoverable manner.

## 9. Transaction timeouts and configuration

A transaction must complete within the timeframe allowed by the broker and client. If a transaction stays open too long, the coordinator may expire it or the producer may time out.

| Component | Impact |
|---|---|
| `transaction.timeout.ms` | Maximum time the broker allows a transaction to remain open |
| `max.poll.interval.ms` | Maximum time between consumer polls before the group considers the consumer stalled |
| `max.poll.records` | Maximum records returned per poll; affects batch processing time |
| `request.timeout.ms` / `delivery.timeout.ms` | Time limits for producer requests and record delivery |
| Business processing time | Time the `Function`/`Consumer` takes to process a message and emit output |
| Transaction coordinator availability | Ability to begin, commit, or abort transactions |

Do not arbitrarily increase transaction timeouts. Long-open transactions stall `read_committed` consumers behind the LSO and can degrade throughput, latency, rebalances, or recoverability.

If each poll processes a batch with many records, the time to finish the entire batch must fit within poll and transaction limits. You can reduce `max.poll.records`, optimize logic, or split work if processing takes too long.

## 10. Prefix uniqueness when running multiple instances

In a multi-replica environment, each instance must have its own transaction ID prefix. Example:

| Instance | transactionIdPrefix |
|---|---|
| Pod A | order-processor-pod-a- |
| Pod B | order-processor-pod-b- |
| Pod C | order-processor-pod-c- |

Do not set a single fixed prefix for the entire deployment if instances run concurrently. If prefixes collide, producers can be fenced and active transactions can fail.

The deployment platform can provide an instance identity from the pod name or another unique identifier. Ensure that identity does not collide across running instances. When restarting with the same instance identity, Kafka can use fencing to invalidate the old producer; this is part of producer transaction recovery.

## 11. Configuration ensuring only committed data is read

A Kafka pipeline application may have an input binding reading events from another service and an output binding emitting transactional results. Combined configuration pattern:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.submitted
          group: order-processor
        processOrder-out-0:
          destination: orders.accepted
      kafka:
        binder:
          brokers: kafka-1:9092
          transaction:
            transactionIdPrefix: order-processor-pod-a-
~~~

Another consumer that must only read committed data can configure its own isolation level:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          auditOrders-in-0:
            consumer:
              configuration:
                isolation.level: read_committed
~~~

Only declare `auditOrders-in-0` if the application actually has that function/binding. Configuring consumer isolation for a binding does not create a new binding on its own.

## 12. Transactions with KafkaTemplate and StreamBridge

The Spring Cloud Stream Kafka binder manages transactions for bindings configured via the binder. If the application uses `KafkaTemplate` directly, you must understand which transaction manager owns the transaction and ensure the template participates in the right transaction.

A `KafkaTemplate` can join an ongoing transaction managed by `KafkaTransactionManager` when using the corresponding producer factory. Calling an API that starts an independent transaction such as `executeInTransaction` inside another consumer transaction may create a separate transaction or fail to achieve the intended atomicity.

With Spring Cloud Stream:

- Prefer output bindings/`StreamBridge` configured with the same Kafka binder and transaction context.
- Do not manually create a producer with an arbitrary `transactional.id` and send alongside the binder.
- Do not use a different binder or a different Kafka cluster if a single atomic transaction is needed.
- Test that outputs and offsets commit/abort together under failure conditions.

Generic `@Transactional` does not automatically imply a Kafka transaction. You must determine which transaction manager is selected, transaction manager ordering, and which resources the method participates in. If both a database transaction and a Kafka transaction are involved, do not assume a single annotation commits both systems atomically.

## 13. Testing transactions with a Kafka broker

Unit tests for a `Function` can verify business logic but do not verify broker transactions. To test commit/abort semantics, integration tests with a real Kafka broker or Kafka Testcontainers are required.

A test scenario should:

1. Create input and output topics.
2. Start the application with a unique transaction ID prefix.
3. Send a record to the input topic.
4. Verify the output record appears to a `read_committed` consumer.
5. Verify the consumer group's offset has advanced after the transaction commits.
6. Send a record that causes the `Function` to throw an exception after preparing/sending output.
7. Verify output from the aborted transaction does not appear to `read_committed`.
8. Verify the input offset was not committed and can be retried/redelivered per configuration.
9. Start multiple instances and verify prefixes do not trigger `ProducerFencedException`.

To distinguish `read_committed` from `read_uncommitted`, you can use two consumers configured with different isolation levels and inspect records from an aborted transaction. The `read_committed` consumer must not receive that record; the `read_uncommitted` consumer may see the appended record even though the transaction aborted.

Additionally, test:

- Producer fencing when intentionally creating two instances with duplicate transactional IDs.
- Transaction timeouts when processing logic takes too long.
- Consumer rebalances when an instance stops mid-transaction.
- Retries and DLQ after rollback.
- Multiple output records across multiple topics committing or aborting together.
- Connection failures during the commit phase and recovery behavior.

## 14. Monitoring transactions in production

Transactions introduce additional state to observe beyond normal consumer lag:

| Metric or log | What to look for |
|---|---|
| Transaction commit rate | Number of transactions completing successfully |
| Transaction abort rate | Frequency of rollbacks due to business errors, timeouts, or broker issues |
| Transaction duration | How long transactions stay open |
| Producer fencing errors | Duplicate prefix/transactional ID or old producer being fenced |
| Consumer lag | Read lag of the input binding |
| Last Stable Offset and `read_committed` lag | Whether long-open transactions are blocking downstream data |
| Retry/rollback count | Which messages repeatedly cause transactions to fail |
| Coordinator errors/timeouts | Whether the broker transaction coordinator has issues |

When aborts spike, find the root cause in processing exceptions, timeouts, rebalances, output send failures, or the transaction coordinator. Do not just increase timeouts or retries without reviewing processing time and broker health.

## 15. Common misconceptions

**Enabling idempotence gives consume-process-produce exactly-once.** Idempotence reduces duplicates from producer retries; Kafka transactions are required to tie output records with input offsets.

**Setting `transactionIdPrefix` makes all systems atomic.** The prefix enables transactional producers in the binder. Databases, HTTP services, and other clusters remain outside the Kafka transaction.

**Every consumer automatically hides aborted records.** Consumers must use `isolation.level=read_committed` if they need to see only committed data.

**The Function only runs once.** When a transaction aborts and the input offset is uncommitted, the `Function` can run again.

**A single shared prefix for all replicas is enough.** Concurrently active instances need separate transactional IDs to avoid producer fencing.

**Longer transactions are safer.** Long-open transactions block the LSO, increase downstream latency, and risk timeouts or rebalances.

**Catching an exception and continuing equals a rollback.** If an exception is swallowed and the handler returns normally, the transaction can commit. To abort, the error must propagate to the transaction boundary or the application must mark rollback via a supported mechanism.

**Kafka transactions replace the outbox pattern.** Kafka transactions do not cover databases. The outbox pattern solves writing business data and the intent to emit an event in the same database transaction.

## 16. Process for designing transactions in a Spring Cloud Stream flow

1. Identify the service's input topic, output topic, and consumer group.
2. Identify all output records that must commit together with the input offset.
3. Enable transactions on the Kafka binder using `transactionIdPrefix`.
4. Assign a unique prefix per running instance.
5. Use the same Kafka binder/cluster for outputs that need to join the transaction.
6. Configure downstream consumers to use `read_committed` if they must process only committed records.
7. Set processing time limits compatible with `transaction.timeout.ms` and `max.poll.interval.ms`.
8. Design rollback, retry, recovery, and DLQ handling for failed messages.
9. Handle database/API side effects using an appropriate idempotency or outbox pattern.
10. Test commits, aborts, redelivery, producer fencing, and multiple outputs.
11. Monitor transaction duration, abort rate, consumer lag, and coordinator errors.

## Official References

- [Spring Cloud Stream - Kafka Binder Transactions](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/transactional.html): enabling transactions with transaction ID prefix and how the binder manages transactions.
- [Spring Cloud Stream - Kafka Binder Reference](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/index.html): configuring the Kafka binder, producer, consumer, and bindings.
- [Spring for Apache Kafka - Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html): `KafkaTransactionManager`, transactional producers, transaction synchronization, and fencing.
- [Apache Kafka - Design: Message Delivery Semantics](https://kafka.apache.org/documentation/#semantics): at-most-once, at-least-once, and exactly-once in Kafka.
- [Apache Kafka - Consumer Configurations](https://kafka.apache.org/40/configuration/consumer-configs/): `isolation.level` and `read_committed`.
