# `KafkaTemplate` local transaction

## 1. What is a `KafkaTemplate` local transaction?

In some business flows, a single operation must emit multiple Kafka records and those records must be recorded together. For example, when an order is created, the service may emit `OrderCreatedEvent` to the `orders` topic and simultaneously emit `OrderAuditEvent` to the `order-audit` topic.

If each record is sent with independent `KafkaTemplate.send()` calls, the first record might be written successfully while the second fails. Consumers would then observe a partial outcome, even though the business logic expects both records to appear together or neither to appear.

Kafka supports producer transactions to group multiple sends into an atomic unit within the Kafka cluster. Spring Kafka provides `KafkaTemplate.executeInTransaction()` to open a local transaction, perform sends inside a callback, and commit when the callback finishes normally.

If the callback throws an exception, the transaction is aborted. Consumers configured with `isolation.level=read_committed` see only records belonging to committed transactions.

A `KafkaTemplate` local transaction fits cases where a block of code needs to manage its own Kafka send transaction boundary without placing the entire method inside a Spring transaction coordinated by a transaction manager.

## 2. Transaction execution flow

`executeInTransaction()` accepts a callback working with `KafkaOperations`. Inside the callback, the application can send multiple records, even to different topics or partitions within the same Kafka cluster.

~~~mermaid
flowchart TD
    A["Call executeInTransaction()"] --> B["Create / acquire transactional producer"]
    B --> C["beginTransaction()"]
    C --> D["Run callback"]
    D --> E{"Callback completes normally?"}
    E -->|Yes| F["commitTransaction()"]
    E -->|Exception thrown| G["abortTransaction()"]
    F --> H["Records become visible to read_committed consumers"]
    G --> I["Transaction records are excluded from read_committed view"]
~~~

A producer transaction typically consists of these steps:

1. Spring acquires a transactional producer from `ProducerFactory`.
2. The producer begins a transaction.
3. `send()` calls inside the callback are dispatched using the producer bound to the current transaction.
4. When the callback returns normally, Spring commits the transaction.
5. If the callback fails, Spring aborts the transaction and propagates the error to the caller.

`executeInTransaction()` returns the callback result only after the commit completes. If commit fails, the caller receives an exception instead of a successful result.

Kafka transactions provide atomicity for records sent within the same transaction. They do not automatically include database operations, HTTP requests, file writes, or side effects in other systems.

## 3. Enabling a transactional producer in Spring Boot

`KafkaTemplate.executeInTransaction()` requires a transaction-capable `ProducerFactory`. In Spring Boot, the common approach is configuring `spring.kafka.producer.transaction-id-prefix`.

Example:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: order-service-${INSTANCE_ID:local}-tx-
      acks: all
      properties:
        transaction.timeout.ms: 60000
~~~

Spring Boot uses this prefix to configure a transactional producer factory and generate distinct transactional IDs for producers created from that factory.

**The prefix must be unique across concurrently running instances.** In multi-replica environments, supply a different `INSTANCE_ID` for each instance, such as a pod UID or a stable instance identifier. If two active instances share the same prefix, transactional IDs can collide and one producer will fence the other.

The `local` value in the example is only appropriate when running a single instance on a development machine. Do not use the same default value across multiple production replicas.

Points to remember:

- Do not hardcode a single static `transactional.id` shared by all producer instances.
- Let Spring Kafka manage the transactional ID suffix via `transaction-id-prefix`.
- Do not disable idempotence on a transactional producer.
- Choose `transaction.timeout.ms` to fit the maximum transaction duration; the broker enforces `transaction.max.timeout.ms`.
- Keep transactions short. Do not make slow API calls or wait for user input while a transaction is open.

With the configuration above, Spring Boot can auto-configure a transactional `ProducerFactory` and `KafkaTemplate`. The application can inject the template and call `executeInTransaction()`.

## 4. Configuring `ProducerFactory` manually

If not using Spring Boot auto-configuration, configure the transactional ID prefix on `DefaultKafkaProducerFactory`.

~~~java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.support.serializer.JsonSerializer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class KafkaProducerConfiguration {

    @Bean
    ProducerFactory<String, Object> producerFactory(
            @Value("${app.kafka.transaction-id-prefix}")
            String transactionIdPrefix) {

        Map<String, Object> producerProperties = new HashMap<>();
        producerProperties.put(
            ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092"
        );
        producerProperties.put(
            ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class
        );
        producerProperties.put(
            ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
            JsonSerializer.class
        );
        producerProperties.put(ProducerConfig.ACKS_CONFIG, "all");

        var factory =
            new DefaultKafkaProducerFactory<String, Object>(
                producerProperties
            );

        factory.setTransactionIdPrefix(transactionIdPrefix);
        return factory;
    }

    @Bean
    KafkaTemplate<String, Object> kafkaTemplate(
            ProducerFactory<String, Object> producerFactory) {
        return new KafkaTemplate<>(producerFactory);
    }
}
~~~

Example property declaration consumed by the bean:

~~~yaml
app:
  kafka:
    transaction-id-prefix: order-service-${INSTANCE_ID:local}-tx-
~~~

`producerProperties` in the example is built with illustrative bootstrap server and serializers; replace `localhost:9092` with your environment's cluster configuration. `transactionIdPrefix` must come from per-instance configuration rather than hardcoding the same value for all replicas.

The example above focuses on enabling transactions. In a real application, use typed configuration properties and declare serializers compatible with your key/value types. Do not create two different `ProducerFactory` instances and expect records sent from both factories to automatically belong to the same transaction.

## 5. Sending multiple records in a local transaction

Example of a service emitting two events when an order is created:

~~~java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
public class OrderEventPublisher {

    private final KafkaTemplate<String, Object> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, Object> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public String publish(OrderCreatedEvent orderEvent,
                          OrderAuditEvent auditEvent) {

        return kafkaTemplate.executeInTransaction(operations -> {
            operations.send(
                "orders",
                orderEvent.orderId(),
                orderEvent
            ).join();

            operations.send(
                "order-audit",
                auditEvent.orderId(),
                auditEvent
            ).join();

            return "published";
        });
    }
}
~~~

Inside the callback:

- `operations` is the `KafkaOperations` bound to the current transaction.
- Both `send()` calls use the same transactional producer.
- `join()` waits for the send result so send failures are detected immediately inside the callback.
- The callback returns `"published"` only after both sends complete; `executeInTransaction()` then commits the transaction before returning the result to the caller.

`join()` blocks the calling thread until the send completes. For high-throughput paths, consider how futures and transactions interact; even without `join()`, committing the transaction still must complete pending sends before the transaction commits. Do not treat `send()` returning a future as proof that the record is already committed.

If a send fails or the callback throws an exception, the transaction is aborted. Do not catch and swallow exceptions inside the callback, because normal callback completion causes Spring to commit previously sent records.

## 6. What happens when the callback throws an exception?

You can intentionally throw an exception when a business condition is not met:

~~~java
public void publishIfValid(
        OrderCreatedEvent orderEvent,
        OrderAuditEvent auditEvent) {

    kafkaTemplate.executeInTransaction(operations -> {
        operations.send(
            "orders",
            orderEvent.orderId(),
            orderEvent
        ).join();

        if (!auditEvent.isAllowed()) {
            throw new IllegalStateException(
                "Not allowed to emit audit event"
            );
        }

        operations.send(
            "order-audit",
            auditEvent.orderId(),
            auditEvent
        ).join();

        return null;
    });
}
~~~

In this example, the record already sent to `orders` still belongs to the open transaction. When the callback throws `IllegalStateException`, Spring aborts the transaction. A consumer in `read_committed` mode will not receive that record as a committed record.

A consumer using `read_uncommitted` can read records belonging to uncommitted or aborted transactions. Therefore, if business logic requires reading only committed data, configuring the consumer isolation level is mandatory.

Do not write code like this:

~~~java
kafkaTemplate.executeInTransaction(operations -> {
    try {
        operations.send("orders", orderId, event).join();
        operations.send("order-audit", orderId, audit).join();
    } catch (RuntimeException ex) {
        log.error("Failed to send event", ex);
        // Callback completes normally: the transaction may be committed.
    }
    return null;
});
~~~

Once you decide the transaction has failed, let the exception propagate out of the callback or rethrow a runtime exception. Merely logging and continuing can turn a send failure into an unintended transaction commit.

## 7. Consumers must use `read_committed`

A Kafka consumer has the `isolation.level` property:

| Value | Behavior |
|---|---|
| `read_uncommitted` | May read records from uncommitted or aborted transactions; this is the common Kafka consumer default |
| `read_committed` | Returns only records from committed transactions and skips records from aborted transactions |

Spring Boot configuration:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        isolation.level: read_committed
~~~

With `read_committed`, the consumer reads only up to the partition's last stable offset. If an open transaction exists on a partition, records behind that transaction may not be returned until the transaction finishes. This behavior is important to understand when observing consumer lag or read latency.

Configuring `read_committed` does not make the consumer manage transactions itself. It only controls which records the consumer is allowed to see.

If a topic has both transactional and non-transactional producers, a `read_committed` consumer still reads non-transactional records written normally; it filters by record transaction state.

## 8. How does a local transaction differ from `KafkaTransactionManager`?

Spring Kafka offers multiple ways to manage transactions. Choose based on where you want to place the transaction boundary:

| Mechanism | Usage | Best fit |
|---|---|---|
| `KafkaTemplate.executeInTransaction()` | Opens and closes a local transaction directly around the callback | A code block that needs to send multiple Kafka records all-or-nothing |
| `KafkaTransactionManager` | Integrates Kafka transactions with Spring's transaction infrastructure | Letting Spring manage Kafka transactions through a transaction manager |
| Transactional listener container | Container starts a transaction for record processing; Kafka sends join the transaction and offsets are coordinated as configured | Consume-transform-produce in Kafka |
| Database transaction + Outbox | Writes business data and an outbox row in the same database transaction; a publisher emits outbox records later | Reliably coordinating database changes with Kafka publishing |

`executeInTransaction()` is a local, explicit API: the calling code decides where the transaction begins and ends. It does not automatically turn an existing database transaction into a distributed transaction with Kafka.

If the goal is processing an input record, emitting output records, and committing offsets within the same Kafka transaction, explore transactional listener containers and configure `KafkaTransactionManager` appropriately. If the goal is updating a database and emitting events, Transactional Outbox is generally easier to operate.

## 9. Local transactions do not include databases or HTTP

Suppose a callback sends a Kafka event and updates a database:

~~~java
kafkaTemplate.executeInTransaction(operations -> {
    operations.send("orders", orderId, event).join();

    orderRepository.markPublished(orderId);

    return null;
});
~~~

This code does not create an atomic transaction between Kafka and the database. If the database commits successfully while the Kafka transaction aborts, or the Kafka transaction commits while the database rolls back, the two systems can be left in an inconsistent state.

Do not place database writes inside the callback assuming `executeInTransaction()` will roll back the database. Similarly, HTTP requests, sending emails, or writing files are not automatically undone by Kafka transactions.

If you need to write to a database and publish to Kafka as a durable business operation:

1. Within a single database transaction, update business data and insert an outbox record.
2. A publisher reads the outbox and sends events to Kafka.
3. The publisher marks the outbox entry as sent with retry/reconciliation handling.
4. Consumers process idempotently to tolerate replayed events.

Outbox bridges the gap between database commit and Kafka publish with a durable record inside the same database transaction. It does not turn the database and Kafka into a single distributed transaction.

## 10. Transactional ID, fencing, and transaction timeout

Kafka uses `transactional.id` to identify a transactional producer across producer creations. Spring Kafka constructs IDs from `transaction-id-prefix` plus a suffix managed by the producer factory.

If two active producer instances use the same transactional ID, the broker can fence the older producer. Fencing prevents an old producer from continuing to write transactions after ownership of the ID has transferred to another producer.

Keep in mind:

- Each concurrent application instance must have its own prefix.
- Within an instance, the producer factory manages suffixes for created producers.
- The prefix should be tied intentionally to an instance identity, not shared arbitrarily across replicas.
- When an instance is replaced, use an appropriate identifier so the new producer can fence the old producer when needed.
- Transactions must finish within `transaction.timeout.ms`.
- Brokers enforce a ceiling via `transaction.max.timeout.ms`.

Do not set an overly large timeout merely to mask a slow callback. Long-lived open transactions can hold back the last stable offset on the consumer side and increase read latency. Reduce processing time inside the transaction, avoid waiting on external services, and split work where appropriate.

## 11. Common errors

| Symptom | Common cause | Resolution |
|---|---|---|
| `executeInTransaction()` reports factory is not transactional | Transaction ID prefix is not configured | Configure `transaction-id-prefix` in Boot or call `setTransactionIdPrefix()` |
| Producer is fenced | Two instances share the same transactional ID/prefix | Assign a distinct prefix per running instance |
| Consumer sees aborted records | Consumer uses `read_uncommitted` | Switch to `read_committed` if reading only committed transactions is required |
| Transaction timeout | Callback runs too long or waits on external APIs | Shorten the transaction and align timeouts with broker limits |
| Some records appear while others do not | Sends are not in the same transaction or use a different producer factory | Use the same template/transaction context inside the callback |
| Callback throws/logs an error yet transaction commits | Exception was caught and swallowed inside the callback | Rethrow the exception so the transaction aborts |
| Expecting database to roll back with Kafka | Confusing a local Kafka transaction with a distributed transaction | Use Outbox or an appropriate coordination mechanism |
| Producer send future has not completed | Result not awaited or commit has not finished | Observe futures and the outcome of `executeInTransaction()` |

When troubleshooting, inspect the transaction ID prefix, actual producer factory, transaction timeout, broker logs, send futures, and consumer isolation level. Do not conclude a transaction succeeded just because the callback finished running; wait for `executeInTransaction()` to return successfully.

## 12. Testing local transactions

Test both branches: successful commit and abort when the callback fails.

**Testing commit:** call `executeInTransaction()` to send two records to two topics. Use a consumer with `isolation.level=read_committed` to read both topics and verify each record appears once.

~~~java
kafkaTemplate.executeInTransaction(operations -> {
    operations.send("orders", "ORD-1", orderEvent).join();
    operations.send("order-audit", "ORD-1", auditEvent).join();
    return null;
});
~~~

**Testing abort:** send the first record and then throw an exception before the callback completes:

~~~java
assertThatThrownBy(() ->
    kafkaTemplate.executeInTransaction(operations -> {
        operations.send("orders", "ORD-2", orderEvent).join();
        throw new IllegalStateException("force rollback");
    })
).isInstanceOf(RuntimeException.class);
~~~

Afterward, the `read_committed` consumer must not receive records from the aborted transaction. To keep tests isolated from old data, use dedicated test topics or group IDs, and poll with a finite timeout.

Points to verify:

- The producer factory genuinely has a transactional ID prefix.
- Both sends inside the callback belong to the same transaction.
- When the callback ends normally, a `read_committed` consumer sees all records.
- When the callback throws an exception, a `read_committed` consumer sees no records from the aborted transaction.
- Commit or publish errors are propagated to the caller.
- Two instances do not share the same prefix.
- A `read_uncommitted` consumer exhibits different observable behavior, if tests need to demonstrate isolation.

You can use Embedded Kafka or Testcontainers to test against a real broker. Do not mock `KafkaTemplate` alone, because mocks cannot prove broker transaction markers, commit/abort, or isolation levels work properly.

## 13. Checklist for implementing `KafkaTemplate` local transactions

- [ ] Configure a transactional producer via `transaction-id-prefix`.
- [ ] Assign a unique prefix to each concurrently running application instance.
- [ ] Use the same transactional `KafkaTemplate` for records inside the callback.
- [ ] Send all records requiring atomicity inside `executeInTransaction()`.
- [ ] Allow exceptions to propagate out of the callback when the transaction must abort.
- [ ] Wait for `executeInTransaction()` to complete before reporting business success.
- [ ] Configure consumer `isolation.level=read_committed` when only committed records should be read.
- [ ] Pick an appropriate `transaction.timeout.ms` and keep callbacks short.
- [ ] Do not assume Kafka transactions cover databases, HTTP, or files.
- [ ] Use Outbox when database commits must be coordinated with Kafka publishing.
- [ ] Test both commit and abort against a real broker.
- [ ] Monitor fencing, transaction timeouts, producer errors, and consumer lag.

`KafkaTemplate.executeInTransaction()` provides a clear way to send multiple Kafka records within a local transaction. When each instance has its own transactional ID prefix, consumers read with `read_committed`, and callbacks handle errors properly, applications can ensure records in a transaction become visible together or not at all. That boundary applies strictly to Kafka; side effects in databases and external systems require separate coordination mechanisms.
