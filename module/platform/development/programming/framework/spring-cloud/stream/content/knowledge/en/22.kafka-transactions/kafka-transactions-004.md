# Producer-Only Transactions and Defining Transaction Boundaries

A Spring Cloud Stream application may only produce messages: a `Supplier` generating scheduled events, a REST controller calling `StreamBridge` on incoming requests, or a business service sending multiple records to Kafka. When sending only a single record per invocation, a regular producer may already meet the requirement if the application waits for the send result and configures an appropriate acknowledgement level. Kafka transactions become useful when multiple sends are related and must be published as a single atomic unit.

The first thing to define before enabling transactions is the **transaction boundary**: which records must commit together or abort together? For producer-only flows, that boundary is usually a business method, an event batch, or an operation publishing to multiple topics. The Spring Cloud Stream Kafka Binder provides the transactional producer; Spring Kafka provides `KafkaTransactionManager` and `TransactionTemplate` to wrap the sends in an explicit transaction.

## 1. What is a producer-only transaction?

A producer-only transaction is a Kafka transaction initiated by the message-producing application itself, not started by a consumer listener. Inside the transaction, the producer can send one or more records to one or more topics within the same Kafka cluster. When the transaction commits, the records are published as a unit; when the transaction aborts, the records from that transaction are not visible to `read_committed` consumers.

For example, finalizing an order needs to emit concurrently:

- `OrderConfirmed` to topic `orders.events`.
- `InventoryReservationRequested` to topic `inventory.commands`.
- `InvoiceRequested` to topic `billing.commands`.

If these three records represent a single business decision, the application may want all of them to appear or none at all. A producer-only transaction allows grouping those Kafka sends into a single transaction.

~~~text
Producer application
       |
       v
beginTransaction
       |
       +---- send orders.events
       |
       +---- send inventory.commands
       |
       +---- send billing.commands
       |
       v
   commitTransaction
       |
       v
read_committed consumer sees the entire group of records
~~~

If a send step or business logic throws an exception before commit, the transaction can roll back:

~~~text
beginTransaction
       |
       +---- send orders.events
       |
       +---- send inventory.commands
       |
       +---- error in next step
       |
       v
   abortTransaction
       |
       v
read_committed consumer does not see aborted records
~~~

The transaction guarantees the atomicity of Kafka writes within the same transaction. It does not automatically include database updates, HTTP API calls, sending emails, or operations on another broker.

## 2. When do you need a transaction and when do you not?

Do not enable transactions just because the application uses Kafka. Choose based on the requirements of the publish operation:

| Scenario | Typically appropriate approach |
|---|---|
| A single call sends one independent record | Synchronous producer send if waiting for result is needed; configure `acks` for durability |
| A `Supplier` emits one record per cycle | Usually does not need a transaction; consider synchronous producer |
| A REST request emits one record | Usually does not need a multi-record transaction |
| One operation sends multiple records that must appear or abort together | Producer-only transaction |
| One operation sends to multiple Kafka topics in the same cluster | Producer-only transaction if bindings share the same transactional producer factory |
| One operation writes both Kafka and a database | Needs synchronized transaction design and commit failure handling; consider outbox |
| Consumer reads, processes, then emits output and commits offset together | Consumer-initiated transaction; a different boundary from producer-only |

For a single record, a transaction adds overhead for opening, committing, and managing the producer. The Spring Cloud Stream Kafka Binder supports `sync: true` to wait for the send result. Combined with an appropriate Kafka acknowledgement level, this is often sufficient when you only need to know a single send was acknowledged by the broker.

Example synchronous send configuration:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderEvent-out-0:
          destination: orders.events
      kafka:
        binder:
          required-acks: all
        bindings:
          orderEvent-out-0:
            producer:
              sync: true
~~~

`sync: true` makes the producer wait for the send result instead of returning immediately after handing the record off to the async send path. `required-acks: all` instructs Kafka to wait for all currently in-sync replicas (ISR) to acknowledge per Kafka semantics. This is not a multi-record transaction; it simply makes the outcome of the individual send explicit.

## 3. Enabling the transactional producer in the Kafka Binder

The Kafka Binder enables the transactional producer when a non-empty `transaction-id-prefix` is configured:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderEvents-out-0:
          destination: orders.events
          content-type: application/json
      kafka:
        binder:
          brokers: localhost:9092
          transaction:
            transaction-id-prefix: ${INSTANCE_ID}-order-producer-
~~~

In the example, `INSTANCE_ID` must be a unique value per running instance, such as a pod ID or process ID provided by the deployment platform. If multiple instances run with the same prefix, producers can end up with duplicate `transactional.id`s; Kafka can fence the older producer when another producer initializes with the same identifier. In a single-instance local environment, a fixed prefix can be used; production requires a unique value per instance.

`transaction-id-prefix` instructs the binder to create a transactional producer factory. The Kafka producer factory generates concrete `transactional.id` values from the prefix and an internally managed suffix. The prefix must be distinct across concurrent instances while staying within Kafka's configuration length limits.

Once the binder is in transactional mode, producer bindings share a single producer factory and producer properties must be configured under `spring.cloud.stream.kafka.binder.transaction.producer.*`. Binding-level Kafka producer properties may be ignored in this mode. Place shared configurations at the proper scope and check the documentation for your binder version.

## 4. A single send does not equal a multi-record business transaction

A common point of confusion: merely enabling `transaction-id-prefix` is not enough to group multiple `StreamBridge.send()` calls into one shared transaction.

When there is no active Spring transaction, the binder may open and commit a separate transaction for each send:

~~~java
for (int i = 0; i < 3; i++) {
    streamBridge.send("orderEvents-out-0", events.get(i));
}
~~~

With transactional binder configuration but without a transaction manager wrapping the loop, three sends can become three separate transactions. If the third send fails, the first two may have already committed and been seen by consumers.

To make all three records a single atomic unit, you need to:

1. Enable the transactional producer via `transaction-id-prefix`.
2. Create a `KafkaTransactionManager` from the Kafka Binder's own transactional producer factory.
3. Use `TransactionTemplate` or `@Transactional` to wrap all the sends.
4. Let exceptions escape the transaction callback or mark rollback-only when the transaction must be aborted.

## 5. Obtaining ProducerFactory from the Kafka Binder

For producer-only transactions in a source application or an arbitrary thread such as `@Scheduled`, the Kafka Binder requires the application to obtain the transactional producer factory and create a `KafkaTransactionManager` from that factory.

~~~java
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.cloud.stream.binder.BinderFactory;
import org.springframework.cloud.stream.binder.kafka.KafkaMessageChannelBinder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.transaction.KafkaTransactionManager;
import org.springframework.messaging.MessageChannel;
import org.springframework.transaction.support.TransactionTemplate;

@Configuration
class KafkaProducerTransactionConfiguration {

    @Bean
    KafkaTransactionManager<byte[], byte[]> kafkaTransactionManager(
            BinderFactory binders) {

        KafkaMessageChannelBinder kafkaBinder =
                (KafkaMessageChannelBinder) binders.getBinder(
                        null, MessageChannel.class);

        ProducerFactory<byte[], byte[]> producerFactory =
                kafkaBinder.getTransactionalProducerFactory();

        return new KafkaTransactionManager<>(producerFactory);
    }

    @Bean
    TransactionTemplate kafkaTransactionTemplate(
            KafkaTransactionManager<byte[], byte[]> kafkaTransactionManager) {
        return new TransactionTemplate(kafkaTransactionManager);
    }
}
~~~

The example passes `null` for the binder name assuming the application configures only one binder. If the application has multiple binders, pass the exact Kafka binder name to `getBinder("kafka", MessageChannel.class)` or your system's actual binder name.

The most important point is that `KafkaTransactionManager` must use **the same `ProducerFactory` that the Kafka Binder uses for output bindings**. If you create an independent producer factory, `StreamBridge` may continue sending through the binder's own factory, without joining the transaction managed by the manager.

When enabling transactions via Spring Boot's `spring.kafka.producer.transaction-id-prefix` property, Spring Boot may create its own producer factory and transaction manager. In a Spring Cloud Stream application using the Kafka Binder, do not assume Boot's auto-configured manager uses the same factory as the binder. Use `spring.cloud.stream.kafka.binder.transaction.transaction-id-prefix` and retrieve the factory directly from the binder as shown.

## 6. Defining boundaries with TransactionTemplate

`TransactionTemplate` makes the start and end scope of a transaction explicit in code. For example, an order confirmation command needs to emit three related events:

~~~java
import java.util.List;

import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

record OrderEvent(String eventId, String orderId, String eventType) {}

@Service
class OrderBatchPublisher {

    private final StreamBridge streamBridge;
    private final TransactionTemplate kafkaTransactionTemplate;

    OrderBatchPublisher(
            StreamBridge streamBridge,
            TransactionTemplate kafkaTransactionTemplate) {
        this.streamBridge = streamBridge;
        this.kafkaTransactionTemplate = kafkaTransactionTemplate;
    }

    void publishAll(List<OrderEvent> events) {
        kafkaTransactionTemplate.executeWithoutResult(status -> {
            for (OrderEvent event : events) {
                boolean accepted = streamBridge.send(
                        "orderEvents-out-0", event);

                if (!accepted) {
                    throw new IllegalStateException(
                            "Kafka binding did not accept event " + event.eventId());
                }
            }
        });
    }
}
~~~

When the callback finishes normally, the transaction manager commits the transaction. If `send` returns `false` or an operation inside the callback throws an exception, the transaction callback terminates abnormally and Spring rolls back the transaction.

A `true` return value from `StreamBridge.send` indicates the message was accepted at the binding/channel level. It is not independent proof that the broker has committed the transaction. The Kafka commit is performed by the transaction manager after the callback completes; if you need to inspect detailed send results, you can add a record metadata channel or observe producer results as supported by the binder.

Do not catch and swallow exceptions inside the callback if business logic requires a rollback. If you need to catch an exception for logging, re-throw it or call `status.setRollbackOnly()` to mark the transaction not to commit.

## 7. Using @Transactional to group multiple sends

You can use `@Transactional` instead of `TransactionTemplate`. The annotated method must be invoked through a Spring transaction proxy and the transaction manager must be the `KafkaTransactionManager` sharing the binder's producer factory.

~~~java
import java.util.List;

import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class TransactionalOrderPublisher {

    private final StreamBridge streamBridge;

    TransactionalOrderPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    @Transactional(transactionManager = "kafkaTransactionManager")
    public void publishBatch(List<OrderEvent> events) {
        for (OrderEvent event : events) {
            if (!streamBridge.send("orderEvents-out-0", event)) {
                throw new IllegalStateException(
                        "Could not enqueue event " + event.eventId());
            }
        }
    }
}
~~~

Name the transaction manager bean `kafkaTransactionManager` to match the `transactionManager` attribute in the annotation. If the application has multiple transaction managers, always specify the manager explicitly; do not rely on default selection.

Invoke the transactional method from another Spring bean:

~~~java
@Service
class OrderApplicationService {

    private final TransactionalOrderPublisher publisher;

    OrderApplicationService(TransactionalOrderPublisher publisher) {
        this.publisher = publisher;
    }

    void confirm(Order order) {
        List<OrderEvent> events = createEvents(order);
        publisher.publishBatch(events);
    }
}
~~~

Do not call a `@Transactional` method from another method in the same instance via `this.publishBatch(...)` expecting the proxy to activate. Self-invocation normally bypasses the Spring proxy, so the transaction interceptor is not invoked. Also, by default Spring rolls back on `RuntimeException` and `Error`; checked exceptions require configuring `rollbackFor` if rollback is desired.

## 8. A single transaction can span multiple topics

A Kafka transaction can send records to multiple topics within the same cluster using the same transactional producer. Example:

The command types below represent payloads for two additional output bindings:

~~~java
record InventoryCommand(String orderId, String sku, int quantity) {}

record InvoiceCommand(String orderId, long totalMinorUnits) {}
~~~

Declare all three output bindings:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderEvents-out-0:
          destination: orders.events
          content-type: application/json
        inventoryCommands-out-0:
          destination: inventory.commands
          content-type: application/json
        invoiceCommands-out-0:
          destination: billing.commands
          content-type: application/json
~~~

~~~java
@Service
class OrderDecisionPublisher {

    private final StreamBridge streamBridge;
    private final TransactionTemplate kafkaTransactionTemplate;

    OrderDecisionPublisher(
            StreamBridge streamBridge,
            TransactionTemplate kafkaTransactionTemplate) {
        this.streamBridge = streamBridge;
        this.kafkaTransactionTemplate = kafkaTransactionTemplate;
    }

    void publishDecision(OrderEvent orderEvent,
                         InventoryCommand inventoryCommand,
                         InvoiceCommand invoiceCommand) {

        kafkaTransactionTemplate.executeWithoutResult(status -> {
            requireAccepted(
                    streamBridge.send("orderEvents-out-0", orderEvent));
            requireAccepted(
                    streamBridge.send("inventoryCommands-out-0", inventoryCommand));
            requireAccepted(
                    streamBridge.send("invoiceCommands-out-0", invoiceCommand));
        });
    }

    private void requireAccepted(boolean accepted) {
        if (!accepted) {
            throw new IllegalStateException("An output binding rejected a message");
        }
    }
}
~~~

The output bindings must be declared and connected to Kafka topics in the same cluster, and must use the appropriate transactional producer factory. If the bindings belong to two different Kafka clusters or two binders with different producer factories, a single Kafka transaction cannot turn them into an atomic distributed transaction.

If a send fails after earlier sends were accepted, the exception must cause the transaction to roll back. `read_committed` consumers will not see the records belonging to the aborted transaction.

## 9. Transaction boundaries and the transaction manager

The boundary should encompass exactly the sends that together represent a single business decision:

| Boundary | Example | Notes |
|---|---|---|
| Single send | An independent event | Usually use sync send if confirmation is needed |
| A batch | Multiple events for the same order confirmation | Can commit/abort together |
| Multiple topics | A decision emitting commands for order, inventory, and billing | Must share the same Kafka cluster and producer factory |
| A scheduler cycle | A snapshot batch that must be published coherently | Can wrap the batch in `TransactionTemplate` |
| An entire long-lived request | Includes external API calls, waiting on users, or long tasks | Should not keep a Kafka transaction open across the whole duration |

The longer a transaction runs, the longer it holds the producer and transaction coordinator, increasing timeout risk and reducing throughput. Put only sends that have an atomic relationship inside the transaction. Perform validation, queries, or expensive computations before opening the transaction whenever possible; do not call external services inside the transaction unnecessarily.

## 10. transaction-id-prefix and fencing across instances

Kafka uses `transactional.id` to identify a transactional producer. When a new producer initializes with the same transactional ID, Kafka can fence the older producer to prevent two concurrent processes from continuing to write with the same identity.

For multi-replica applications:

- Each instance needs a unique prefix.
- Do not use a single fixed prefix shared by all pods.
- Inject an instance ID that is stable over the process lifetime into configuration.
- During restarts or rolling updates, ensure two active instances do not accidentally share the same prefix.
- Monitor `ProducerFencedException` and transaction initialization errors.

Example:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          transaction:
            transaction-id-prefix: ${POD_UID}-orders-
~~~

If the environment lacks `POD_UID`, use a platform-provided instance identifier variable. A default value like `local` is only suitable when a single instance is guaranteed.

## 11. Transaction timeout and overly long transactions

Kafka producers have the `transaction.timeout.ms` property, limiting how long the broker allows an incomplete transaction to remain open. The broker also enforces `transaction.max.timeout.ms`; the producer's requested value cannot arbitrarily exceed the cluster limit.

An overly long transaction can:

- Expire and be aborted.
- Hold the producer used by the transaction manager longer than expected.
- Slow down `read_committed` consumers on the affected partitions due to the open transaction.
- Increase timeout risk when the application calls external APIs or waits on I/O.

Set timeouts based on actual batch durations and broker latency, while keeping transactions short. Do not raise the timeout to mask a long-running workflow that should instead be broken into independent steps.

## 12. Producer-only transactions vs. consumer-initiated transactions

In a producer-only transaction, the application opens the transaction itself and sends records. No input offset is added to the transaction.

In Spring Cloud Stream's processor pattern, the consumer listener can initiate the Kafka transaction. Records sent on the consumer thread participate in that transaction; when the listener exits normally, the listener container adds the processed offset to the transaction and commits. Thus, output records and the input offset can commit together.

| Characteristic | Producer-only | Consumer-initiated |
|---|---|---|
| Who starts the transaction | `TransactionTemplate`, `@Transactional`, or producer transaction API | Kafka listener container |
| Is an input offset in the transaction | No | Yes, when the container commits the offset into the transaction |
| Purpose | Group multiple publishes into one unit | Ensure consume-process-produce within a Kafka transaction |
| Typical boundary | A publish operation or batch | One listener record/batch processing invocation |
| Spring components | `KafkaTransactionManager` / `TransactionTemplate` | Transaction-aware listener container and binder |

Do not call producer-only transactions "exactly-once processing for the whole system". They guarantee the atomicity of the group of Kafka records sent within the transaction. Exactly-once consume-process-produce requires combining the input offset and outputs in the same transaction, proper consumer setup, and `read_committed` on the reading side.

## 13. Consumer isolation.level and observing transactions

By default, a consumer can read records from uncommitted or aborted transactions if its isolation level is `read_uncommitted`. A consumer using `read_committed` returns only records from committed transactions and non-transactional records.

With the Kafka Binder, you can configure the consumer isolation level via binder configuration:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          configuration:
            isolation.level: read_committed
~~~

This configures the binder's consumer client. If you have multiple consumers with different requirements, consider per-binding configuration scope and verify the binder version documentation.

To verify the boundary:

1. Send two records within one transaction.
2. Commit and confirm the `read_committed` consumer receives both.
3. Send two more records and intentionally throw an exception before commit.
4. Confirm the `read_committed` consumer does not receive the aborted records.
5. Compare with a `read_uncommitted` consumer in a test environment to understand the observable difference.

Do not use `Thread.sleep` as sole proof of transaction behavior. Verify commit/abort state and read results using a consumer with the specified isolation level.

## 14. Transactions and databases: boundary limits

A producer-only transaction covers only Kafka. If a method both sends to Kafka and writes to a database, `KafkaTransactionManager` does not automatically roll back the database, and a database transaction does not automatically roll back Kafka if the two resources are not synchronized.

Spring can synchronize two transaction managers in commit order. However, this is not an atomic distributed two-phase commit between Kafka and the database. One transaction can commit first and the other fail afterward; the application must handle divergent state and provide compensation.

For critical business data, the transactional outbox is typically a durable choice:

1. Inside one database transaction, write business changes and an outbox record.
2. A publisher reads the outbox and sends events to Kafka.
3. After sending succeeds, the publisher marks the outbox entry as published.
4. Consumers are idempotent to handle the possibility that the publisher resends if it stops between publishing and updating state.

The outbox avoids the gap between committing the database and recording the intent to emit an event. Kafka transactions can still be used to group multiple Kafka records, but they do not replace database consistency.

## 15. Common mistakes with producer-only transactions

| Symptom | Possible cause | Resolution |
|---|---|---|
| Each send commits separately | Only `transaction-id-prefix` enabled, no transaction manager wrapping multiple sends | Use `KafkaTransactionManager` with the binder's producer factory |
| `@Transactional` does not roll back | Self-invocation, non-proxied bean, or wrong transaction manager | Invoke through Spring bean proxy and specify the manager |
| `StreamBridge` does not join the transaction | Manager uses a different producer factory than the binder | Obtain `getTransactionalProducerFactory()` from `KafkaMessageChannelBinder` |
| Producer gets fenced | Multiple instances share the same transaction ID prefix | Assign a unique prefix per instance |
| Transaction aborts due to timeout | Batch too long or external service calls inside the transaction | Narrow the boundary and set reasonable timeouts |
| Consumer still sees aborted records | Consumer uses `read_uncommitted` | Use `isolation.level=read_committed` when only committed data should be read |
| Only some topics receive records | Bindings do not share the same cluster/factory or the transaction boundary does not cover all sends | Verify binder, cluster, and transaction manager |
| DB write succeeds but Kafka fails | The two systems are not in the same atomic transaction | Use outbox or a compensating workflow |

## 16. Testing transaction boundaries

A useful test suite should cover both commit and rollback paths:

- **Commit:** publish multiple records, finish the callback normally, verify a `read_committed` consumer receives all records.
- **Rollback:** publish part of the records and throw an exception, verify a `read_committed` consumer receives none of that transaction's records.
- **Multiple topics:** send to two topics and confirm both commit or abort together.
- **Transaction manager:** verify the manager obtains the exact producer factory from the Kafka Binder.
- **Multiple instances:** confirm prefixes differ and no producer fencing occurs.
- **Consumer visibility:** verify consumer isolation level is configured properly.
- **Timeout:** simulate a long-running transaction and verify failures are surfaced rather than silently ignored.
- **Database interaction:** if a DB is involved, test outbox and recovery state when one commit step fails.

The Test Binder can test function logic and Spring Cloud Stream wiring, but it does not replace testing the Kafka transaction coordinator, transactional producers, aborts, and `read_committed`. Use a real Kafka broker or equivalent integration environment to verify these guarantees.

## 17. Observing transactions in runtime environments

During development or troubleshooting, you can selectively enable TRACE logging:

~~~yaml
logging:
  level:
    org.springframework.transaction: TRACE
    org.springframework.kafka.transaction: TRACE
    org.springframework.kafka.producer: TRACE
    org.springframework.kafka.core: TRACE
~~~

Logs can show the sequence of `beginTransaction`, `send`, `commitTransaction`, or `abortTransaction`. When wrapping multiple sends with `TransactionTemplate`, a successful batch of sends should correspond to a single transaction boundary, not a separate begin/commit sequence for each send.

In production, monitor:

- Transaction commit and abort counts.
- Producer fencing errors, transaction timeouts, and commit failures.
- Open transaction duration and record count per transaction.
- Send failure rate, producer error channels, and application-level retries.
- Consumer lag and `read_committed` consumer behavior.

Do not log sensitive payloads in transaction logs. Use event IDs, transaction correlation IDs, and topic names for tracing.

## 18. Boundary definition checklist

- Does a single send actually need a transaction, or is a synchronous send enough?
- Which records must appear together or abort together?
- Do the output bindings belong to the same Kafka cluster and share the same transactional producer factory?
- Is `transaction-id-prefix` enabled and unique per instance?
- Does `KafkaTransactionManager` obtain its producer factory from the Kafka Binder itself?
- Does `TransactionTemplate` or `@Transactional` wrap all related sends?
- Do exceptions escape the callback to trigger rollback, or has the transaction been marked rollback-only?
- Do consumers need `read_committed` to see only committed transactions?
- Is the transaction short and free of external API calls or long waits?
- If a database is involved, is an outbox or compensation design in place for cross-system commit failures?
- Have commit, abort, multi-topic, and producer fencing scenarios been tested against real Kafka?

Producer-only transactions fit well when multiple Kafka publishes belong to a single business decision and must be published atomically. `transaction-id-prefix` enables the Kafka Binder's transactional producer, while `KafkaTransactionManager` uses the binder's exact producer factory to establish real boundaries via `TransactionTemplate` or `@Transactional`. A single send rarely needs a multi-record transaction; when databases or external systems are involved, design explicitly for consistency because Kafka transactions do not automatically extend across those systems.

## References

- [Spring Cloud Stream — Transactional Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/transactional.html)
- [Spring Blog — Producer Initiated Transactions in Spring Cloud Stream Kafka Applications](https://spring.io/blog/2023/09/28/producer-initiated-transactions-in-spring-cloud-stream-kafka-applications/)
- [Spring for Apache Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
