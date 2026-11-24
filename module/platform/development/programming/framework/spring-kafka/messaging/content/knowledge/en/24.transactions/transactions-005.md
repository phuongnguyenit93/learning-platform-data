# `executeInTransaction`

When a business operation needs to send multiple Kafka records as an atomic unit, the application should not allow the first record to be written successfully while the second fails and only partial data appears on the topic. Kafka transactions allow a producer to write multiple records to one or more topics/partitions and commit them all together, or abort so the transaction's records are not read by consumers in `read_committed` mode.

Spring Kafka provides `KafkaTemplate.executeInTransaction()` to run a callback inside a template-managed transaction. This approach fits when a business method needs to send a group of Kafka records within a single commit/rollback boundary without manually calling `beginTransaction()`, `commitTransaction()`, and `abortTransaction()` on the Kafka producer.

## 1. What does `executeInTransaction` do?

`executeInTransaction()` accepts an `OperationsCallback` and runs the callback inside a Kafka transaction. The callback receives a `KafkaOperations` instance to send records. If the callback finishes normally, the template commits the transaction; if the callback throws an exception, the transaction is aborted and the exception is propagated to the caller.

```text
Call KafkaTemplate.executeInTransaction(callback)
                    |
                    v
             Begin transaction
                    |
                    v
          Run OperationsCallback
                    |
          +---------+---------+
          |                   |
       Success            Exception
          |                   |
          v                   v
    commitTransaction()  abortTransaction()
          |                   |
          v                   v
    Records committed    Records aborted
```

The key point is that the transaction boundary wraps the callback. Send operations that belong to the same transaction must be performed via the `KafkaOperations` received from the callback or via a `KafkaTemplate` participating in the active transaction. Do not manually create another Kafka producer and send outside the transaction if those records need to be atomic together.

## 2. Prerequisites for using `executeInTransaction`

`KafkaTemplate` must use a transaction-capable `ProducerFactory`. In Spring Boot, the common way is configuring `spring.kafka.producer.transaction-id-prefix`. Spring Boot uses this prefix to configure a transactional producer factory and auto-configure the related Kafka transaction components per the Boot version.

`KafkaTemplate.executeInTransaction()` has been available since Spring Kafka 2.3. If the project uses an older version, upgrade or use the corresponding transaction API for that version.

Example `application.yml`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: ${HOSTNAME:orders-local}-orders-tx-
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
```

`transaction-id-prefix` is used to build `transactional.id` for producers. The producer factory can append a suffix to create a distinct ID for each managed producer. The prefix must be unique across active application instances in the same cluster. If two instances share the same transactional ID, the broker can fence the old producer when the other instance initializes a producer with the same ID.

In multi-pod environments, derive the prefix from a stable, unique instance identifier, such as the pod name injected into `HOSTNAME` or `POD_NAME`. Do not use the same fixed prefix for all replicas.

If configuring the producer factory manually, set the transaction ID prefix on `DefaultKafkaProducerFactory`:

```java
import java.util.HashMap;
import java.util.Map;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;

@Configuration
class KafkaProducerConfiguration {

    @Bean
    ProducerFactory<String, String> producerFactory() {
        Map<String, Object> properties = new HashMap<>();
        properties.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
        properties.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
        properties.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, StringSerializer.class);

        var factory = new DefaultKafkaProducerFactory<String, String>(properties);
        factory.setTransactionIdPrefix("orders-local-tx-");
        return factory;
    }

    @Bean
    KafkaTemplate<String, String> kafkaTemplate(
            ProducerFactory<String, String> producerFactory) {
        return new KafkaTemplate<>(producerFactory);
    }
}
```

The Java example above is for a local environment. Production must provide a separate prefix for each instance. If `ProducerFactory` is not configured for transactions, calling `executeInTransaction()` will fail because the template lacks a transactional producer to open a transaction.

## 3. Sending multiple records in one transaction

Consider a payment workflow that must emit a payment-succeeded event and an audit event. Both records must commit together or abort together:

```java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
class PaymentEventPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    PaymentEventPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public String publishPayment(String paymentId, String paymentJson, String auditJson) {
        return kafkaTemplate.executeInTransaction(operations -> {
            operations.send("payments.events", paymentId, paymentJson);
            operations.send("payments.audit", paymentId, auditJson);
            return "published:" + paymentId;
        });
    }
}
```

Inside the callback:

- `operations.send()` sends records using the transactional producer bound to the current transaction.
- Records can be sent to multiple topics and partitions in the same Kafka cluster.
- The callback's return value is returned to the caller after the transaction completes.
- When the callback returns normally, the template commits the transaction before returning the result.

If one of the business checks detects invalid data, throw an exception to roll back the transaction:

```java
public String publishPayment(String paymentId, String paymentJson, String auditJson) {
    return kafkaTemplate.executeInTransaction(operations -> {
        operations.send("payments.events", paymentId, paymentJson);

        if (auditJson == null || auditJson.isBlank()) {
            throw new IllegalArgumentException("auditJson is required");
        }

        operations.send("payments.audit", paymentId, auditJson);
        return paymentId;
    });
}
```

When the exception escapes the callback, the transaction is aborted. The `payments.events` record sent earlier also belongs to this transaction, so it is not exposed to `read_committed` consumers as a committed record.

## 4. Using the `KafkaOperations` passed to the callback

The `operations` parameter in the callback has type `KafkaOperations<K, V>`. Use this object for all send calls belonging to the transaction:

```java
kafkaTemplate.executeInTransaction(operations -> {
    operations.send("orders.events", orderId, orderJson);
    operations.send("orders.audit", orderId, auditJson);
    return null;
});
```

This style makes clear which send calls belong to the callback boundary. Do not directly invoke a manually created `Producer` outside the transaction-managing producer factory; that producer does not automatically join the template's transaction.

If you need to reuse a message-sending service, design it to accept `KafkaOperations` or ensure the `KafkaTemplate` used participates in the active transaction context. Avoid silently sending some records with a different template or producer factory that is not part of the same transaction.

## 5. What happens when the callback throws an exception?

If the callback throws an exception and it escapes, `executeInTransaction()` aborts the transaction and propagates the exception to the caller. The caller can catch the exception outside to return a business error or perform other handling.

```java
try {
    kafkaTemplate.executeInTransaction(operations -> {
        operations.send("orders.events", orderId, orderJson);
        validateAudit(auditJson); // May throw an exception.
        operations.send("orders.audit", orderId, auditJson);
        return null;
    });
} catch (RuntimeException ex) {
    log.error("Failed to publish transaction for orderId={}", orderId, ex);
    throw ex;
}
```

Do not catch and ignore an exception inside the callback if a rollback is desired:

```java
// Inappropriate if errors must roll back the transaction.
kafkaTemplate.executeInTransaction(operations -> {
    operations.send("orders.events", orderId, orderJson);
    try {
        validateAudit(auditJson);
    } catch (IllegalArgumentException ex) {
        log.warn("Invalid audit", ex);
        // Callback still returns normally: the transaction may be committed.
    }
    return null;
});
```

If the application handles the exception and the callback still returns normally, the template does not know the business operation failed; the transaction can commit the records already sent. Rethrow the exception, or consciously decide that the already-sent data is still allowed to commit.

## 6. Send futures and when the transaction commits

`KafkaTemplate.send()` returns a future because sending records is asynchronous. Inside a transaction callback, you can send multiple records without awaiting each future. When committing the transaction, the Kafka producer must complete all pending send requests before commit succeeds; a send failure can cause commit to fail and abort the transaction.

If you need to inspect send results immediately at the call site, you can await the futures, though waiting sequentially per record increases latency and reduces parallel sending:

```java
import java.util.concurrent.CompletableFuture;
import org.springframework.kafka.support.SendResult;

String result = kafkaTemplate.executeInTransaction(operations -> {
    CompletableFuture<SendResult<String, String>> first =
            operations.send("orders.events", orderId, orderJson);
    CompletableFuture<SendResult<String, String>> second =
            operations.send("orders.audit", orderId, auditJson);

    // Wait for both send acknowledgements; the transaction still commits after the callback returns.
    CompletableFuture.allOf(first, second).join();
    return "sent";
});
```

Inside the callback, let send errors propagate to the transaction boundary. Do not swallow errors in the callback or future callbacks and return normally if business logic requires every record to be written successfully. `CompletableFuture.allOf(...).join()` waits for send acknowledgements and slows down the callback; in return, a future failure is thrown before the callback returns. Transaction commit remains the final confirmation step for the entire group of records.

With Spring Kafka 3.x, the send API returns `CompletableFuture`; older versions may return `ListenableFuture`. Observe asynchronous results in the manner matching your application's library version.

## 7. Transactions and `read_committed` consumers

Kafka transactions guarantee atomicity for records sent within the transaction, yet consumers must choose the appropriate isolation level to read only committed data.

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[isolation.level]": read_committed
```

With `read_committed`, consumers read only records belonging to committed transactions and do not return records from aborted transactions. Consumers using `read_uncommitted` can see transactional records before the transaction is decided, including records later aborted.

`read_committed` can cause consumers to wait when an incomplete transaction sits at the head of a partition's log. This relates to the Last Stable Offset (LSO), so abnormally long transactions can affect consumer readability and latency.

If an application publishes data to multiple downstream consumers, align isolation levels with consistency requirements. A `read_uncommitted` consumer can observe data that a `read_committed` consumer will never receive.

## 8. How does `executeInTransaction` differ from `@Transactional` and `KafkaTransactionManager`?

Spring Kafka provides multiple ways to manage transactions. Choose based on the business boundary:

| Usage | Transaction boundary | Best fit |
|---|---|---|
| `KafkaTemplate.executeInTransaction()` | Callback passed to the template | A method that needs to group a set of Kafka send calls in a local transaction |
| `KafkaTransactionManager` + `@Transactional` | Method/service or listener container via Spring transactions | Coordinating transactions through Spring's transaction infrastructure |
| Transactional listener container | Record processing and Kafka output sending, optionally coordinating offsets | Consume-transform-produce with Kafka transactions |

`executeInTransaction()` is a convenient API for callback-scoped transactions. `KafkaTransactionManager` fits when you want Spring to manage transactions per thread and annotation. Do not nest multiple transaction mechanisms without clearly understanding which transaction owns the producer and which governs commit.

When a method is already managed by `KafkaTransactionManager`, normally you just call `KafkaTemplate.send()` inside the method so the template joins the thread-bound transaction. Using `executeInTransaction()` for a separate callback boundary is an alternative; do not mix both in the same flow without verifying your Spring Kafka version's semantics and the desired commit boundary.

Example using `@Transactional` with the Kafka transaction manager:

```java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.stereotype.Service;

@Service
class TransactionalOrderPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    TransactionalOrderPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional("kafkaTransactionManager")
    public void publish(String orderId, String payload) {
        kafkaTemplate.send("orders.events", orderId, payload);
        kafkaTemplate.send("orders.audit", orderId, "published:" + orderId);
    }
}
```

The example assumes the application defines a `KafkaTransactionManager` bean named `kafkaTransactionManager`. With Spring Boot, the transaction manager can be auto-configured when a producer transaction prefix is set; verify the actual bean if the application has multiple transaction managers.

## 9. Does `executeInTransaction` automatically commit consumer offsets?

Do not equate a record-sending transaction with a consumer-offset transaction. `executeInTransaction()` groups Kafka send calls inside the callback. Unless consumer offsets are explicitly sent into the transaction, that transaction does not automatically acknowledge offsets read by a listener.

In a consume-transform-produce model where output records and input offsets must commit together in Kafka, a transactional listener container with `KafkaTransactionManager` is typically used. The container coordinates sending processed record offsets into the same transaction as the outputs.

```text
Input topic
    |
    v
Transactional listener container
    |
    +---- process record
    |
    +---- send output record
    |
    +---- send consumer offset to transaction
    |
    v
Commit Kafka transaction
    |
    +---- output record visible to read_committed
    +---- input offset committed
```

If you only call `executeInTransaction()` to send output and then commit the input offset via an independent mechanism, a gap can exist between the two operations. Choose a transactional listener container or an API that sends offsets into the transaction according to the Kafka consume-process-produce model.

## 10. Transactions do not cover databases or HTTP services

Kafka transactions coordinate only the Kafka operations included in that transaction. They do not automatically roll back databases, REST APIs, emails, or the filesystem.

For example:

```text
Kafka transaction
    |
    +---- send orders.events
    +---- send orders.audit
    |
    +---- commit / abort

Database updates and HTTP calls do not automatically belong to this transaction.
```

If a callback updates a database and the Kafka transaction later aborts, the database does not automatically roll back unless the database transaction is coordinated via a separate mechanism. Conversely, if Kafka commits successfully while the database update fails, the two systems can drift out of sync.

For business flows that must coordinate a database and Kafka, consider transactional outbox, inbox/idempotency, or distributed transactions if the entire stack supports them and accepts the operational cost. Do not use `executeInTransaction()` as a distributed transaction manager.

## 11. Timeouts, fencing, and transaction errors

Kafka transactions carry additional operational constraints:

- `transaction.timeout.ms` limits how long the broker allows a transaction to remain open. This value must not exceed `transaction.max.timeout.ms` on the broker.
- `transactional.id` helps the broker identify a producer across restarts and fence an old producer when a new producer uses the same ID.
- `transactionIdPrefix` must be unique across concurrent application instances.
- Overly long transactions can hold back the LSO, causing `read_committed` consumers to wait and increasing latency.
- Network errors or timeouts during commit can leave the commit outcome ambiguous to the caller; design appropriate business retries and idempotency.

Do not hold a transaction open while making slow HTTP calls, waiting for user input, or performing unrelated work. Prepare data before opening the transaction, then execute the Kafka operations needing atomicity inside a short callback.

## 12. Testing `executeInTransaction`

Transaction tests must verify both commit and rollback cases, not just the method return value:

1. **Successful commit:** send two records to two topics in the callback; a `read_committed` consumer receives both.
2. **Rollback:** send the first record, then throw an exception before the second record; a `read_committed` consumer receives no records from the aborted transaction.
3. **Send failure:** make the producer unable to send or use an invalid topic/ACL; verify the callback/commit reports an error and the transaction is not treated as successful.
4. **Transaction ID:** run multiple instances with distinct prefixes; verify they do not fence one another.
5. **Isolation level:** compare `read_committed` and `read_uncommitted` consumers when an aborted transaction occurs.
6. **Transaction timeout:** verify callbacks do not exceed the timeout and observe behavior when the broker is slow.
7. **Offset coordination:** if the use case is consume-transform-produce, verify outputs and input offsets commit together in a transactional listener container.

Tests should use a real Kafka broker or an embedded broker matching the library version. Mocking `KafkaTemplate` alone cannot verify broker commit markers, aborts, or isolation behavior.

## 13. Common misconceptions

1. **Assuming merely calling `executeInTransaction()` makes a producer transactional.** `ProducerFactory` must be configured for transactions via `transactionIdPrefix` or an equivalent configuration.
2. **Sending some records via another producer.** A producer outside the transaction is not committed/aborted with the callback.
3. **Catching an exception in the callback and returning normally.** The transaction can commit even though business logic failed.
4. **Assuming a completed send future means the transaction committed.** Sending records and committing the transaction are two separate phases.
5. **Assuming consumers read only committed records by default.** You must configure `isolation.level=read_committed` to hide aborted transactional records.
6. **Using the same transaction ID prefix across all pods.** This can cause producer fencing when multiple instances run.
7. **Assuming `executeInTransaction` automatically commits consumer offsets.** Coordinating input offsets and output records requires an appropriate transactional consume-process-produce model.
8. **Assuming Kafka transactions cover databases or HTTP.** Resources outside Kafka require separate coordination mechanisms.
9. **Keeping transactions open too long.** This can exceed the transaction timeout, hold back the LSO, and increase downstream latency.

`executeInTransaction()` provides a clear way to group multiple Kafka send operations into one commit/rollback unit. Configure the producer factory with a unique transaction ID prefix per instance, use `KafkaOperations` inside the callback, let exceptions escape when rollback is needed, and set downstream consumers to `read_committed`. For flows involving consumer offsets or databases, choose the corresponding transaction mechanism rather than assuming a Kafka callback can cover every resource.
