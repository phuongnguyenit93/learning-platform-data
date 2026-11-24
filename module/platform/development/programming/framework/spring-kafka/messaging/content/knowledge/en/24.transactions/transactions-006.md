# Transactional Listener Container

In Spring Kafka, a listener container can manage a Kafka transaction for each record or batch processed. The container begins a transaction before invoking `@KafkaListener`; send operations using `KafkaTemplate` inside the listener participate in that transaction. When the listener completes successfully, the container adds the input offset into the same transaction and commits. If the listener throws an exception, the transaction rolls back and the record can be read again.

This mechanism enables an atomic **read → process → write** flow in Kafka: output records and input offsets commit together or abort together. It is the foundation of Exactly Once Semantics (EOS) in Spring Kafka. For it to work properly, the producer factory must support transactions, the listener container must be configured with a `KafkaAwareTransactionManager`, and `KafkaTemplate` must use the same producer factory.

## 1. What is a transactional listener container?

A regular listener container invokes the listener and commits offsets according to `AckMode`. With a transactional listener container, the container opens a Kafka transaction to wrap processing. When the listener sends output to another topic, the output is written inside the current transaction; the offset of the consumed record is also sent into the transaction before commit.

```text
Input topic
    |
    v
Kafka consumer poll
    |
    v
Listener container starts Kafka transaction
    |
    v
@KafkaListener processes record
    |
    +---- KafkaTemplate.send(output) ----> Output record in transaction
    |
    v
Container sends input offset to transaction
    |
    v
COMMIT TRANSACTION
    |
    +---- Output is published
    +---- Input offset is committed
```

If the listener throws an exception before the transaction commits:

```text
Listener throws exception
        |
        v
Kafka transaction ABORT
        |
        +---- Transaction output is not exposed to read_committed
        |
        v
AfterRollbackProcessor handles consumer position
        |
        v
Record is retried or recovered
```

The container is responsible for the transaction lifecycle. The listener does not need to call `beginTransaction()`, `commitTransaction()`, or `sendOffsetsToTransaction()` manually.

## 2. Required components

A transactional listener container requires the following components:

| Component | Responsibility |
| --- | --- |
| `DefaultKafkaProducerFactory` with `transactionIdPrefix` | Creates and caches transactional producers |
| `KafkaTransactionManager` | Starts, commits, and rolls back Kafka transactions |
| `ConcurrentKafkaListenerContainerFactory` | Attaches the transaction manager to the listener container |
| `KafkaTemplate` using the same producer factory | Sends outputs participating in the current transaction |
| Transaction-capable Kafka broker | Stores transaction state and coordinates commit/abort |
| Downstream `read_committed` consumers | Reads only outputs from committed transactions |

Setting `EOSMode.V2` alone is not enough to make a listener transactional. You must configure a transaction ID prefix on the producer factory and attach the transaction manager to the container.

## 3. Enabling transactions with Spring Boot

With Spring Boot, the concise configuration is setting `spring.kafka.producer.transaction-id-prefix`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: ${INSTANCE_ID:local}-orders-tx-
    consumer:
      group-id: order-projection
      properties:
        "[isolation.level]": read_committed
```

When `transaction-id-prefix` is set, Spring Boot configures a transaction-capable producer factory, creates a `KafkaTransactionManager`, and attaches the manager to the auto-configured listener container factory. The auto-configured `KafkaTemplate` also uses that producer factory, so sends inside the listener can participate in the container's transaction.

`INSTANCE_ID` must be unique for each concurrently running application instance, such as a Kubernetes pod name or a platform-assigned instance ID. The value `local` is only appropriate when running a single local instance. If multiple instances share the same prefix, transactional producers can fence one another.

If the application declares its own producer factory or listener container factory, do not assume auto-configuration will attach the manager to custom factories. Configure it explicitly as shown in the next section.

## 4. Java configuration without auto-configuration

The producer factory must have a transaction ID prefix. The example below illustrates the core beans:

```java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.transaction.KafkaTransactionManager;

@Configuration
public class KafkaTransactionConfiguration {

    @Bean
    public ProducerFactory<String, String> producerFactory() {
        Map<String, Object> properties = new HashMap<>();
        properties.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
                "localhost:9092");
        properties.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);
        properties.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);

        var factory = new DefaultKafkaProducerFactory<String, String>(properties);
        factory.setTransactionIdPrefix("orders-instance-a-tx-");
        return factory;
    }

    @Bean
    public KafkaTransactionManager<String, String> kafkaTransactionManager(
            ProducerFactory<String, String> producerFactory) {
        return new KafkaTransactionManager<>(producerFactory);
    }
}
```

In production, the prefix must be supplied separately per instance instead of hardcoding the same value. The configuration above only illustrates the producer factory and transaction manager; the application still needs a `ConsumerFactory`, deserializers, bootstrap/security properties, and a listener container factory.

Attach the manager to the listener container factory:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.transaction.KafkaTransactionManager;

@Bean
public ConcurrentKafkaListenerContainerFactory<String, String>
        kafkaListenerContainerFactory(
                ConsumerFactory<String, String> consumerFactory,
                KafkaTransactionManager<String, String> transactionManager) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, String>();
    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
            .setKafkaAwareTransactionManager(transactionManager);
    return factory;
}
```

From Spring Kafka 3.2 onward, use `setKafkaAwareTransactionManager(...)`. The older `setTransactionManager(...)` API is deprecated. `KafkaAwareTransactionManager` is the abstraction the listener container requires to manage Kafka transactions.

## 5. `KafkaTemplate` must use the same `ProducerFactory`

Send operations join the active transaction only when `KafkaTemplate` uses the same `ProducerFactory` as the container's `KafkaTransactionManager`. Spring Kafka uses the producer resource bound to the listener processing thread.

Example:

```java
@Bean
public KafkaTemplate<String, String> kafkaTemplate(
        ProducerFactory<String, String> producerFactory) {
    return new KafkaTemplate<>(producerFactory);
}
```

When the container starts a transaction, a `KafkaTemplate` created from this producer factory retrieves the producer bound to the current transaction. Its `send()` calls are enlisted in that transaction.

If the template uses a different producer factory, sends may execute in a separate transaction or outside the listener's transaction. Outputs and input offsets will then no longer commit atomically as intended.

In a transactional listener, call `KafkaTemplate.send(...)` directly on the listener's processing thread. If sending is offloaded to another executor/thread, the thread-bound transaction context does not automatically propagate to the background thread; that send will not automatically join the container's transaction.

## 6. Read-process-write example with a transactional listener

Suppose a service reads `orders.in`, produces a projection, and sends the result to `orders.out`:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
public class OrderProjectionListener {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderProjectionListener(
            KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(
            topics = "orders.in",
            groupId = "order-projection",
            containerFactory = "kafkaListenerContainerFactory")
    public void process(ConsumerRecord<String, String> record) {
        String result = transform(record.value());

        kafkaTemplate.send(
                "orders.out",
                record.key(),
                result);
    }

    private String transform(String input) {
        return "projection:" + input;
    }
}
```

When `process` is invoked, the container has already started a Kafka transaction. `KafkaTemplate.send` joins the active transaction. Once the listener finishes normally, the container sends the input record's offset into the transaction and commits.

If `transform` or the listener logic throws an exception, the transaction rolls back. Outputs sent in that transaction are not visible to `read_committed` consumers; the input record is reprocessed according to the rollback/retry policy.

Do not call `KafkaTemplate.executeInTransaction(...)` inside a transactional listener container. Direct sends already participate in the container's transaction. `executeInTransaction` starts a new local transaction rather than joining the existing one, which can break the goal of committing outputs and offsets in one transaction.

## 7. Transaction boundaries with record listeners and batch listeners

The transaction boundary depends on the listener type:

| Listener type | Transaction boundary |
| --- | --- |
| Record listener | One transaction per processed record |
| Batch listener | One transaction for the entire batch received from a single poll |

With a record listener, if one record fails, that record's transaction rolls back. Other records can be processed in separate transactions according to container progress.

With a batch listener, the listener receives a list of records. If the listener throws an exception, the batch's transaction rolls back; the batch can be redelivered according to the after-rollback policy. Because part of the batch may have executed external side effects before the error, batch logic must be idempotent or use an appropriate transaction mechanism for external storage systems.

## 8. Input offsets are committed in the Kafka transaction

The container automatically enlists processed offsets in the transaction using Kafka consumer group metadata and `sendOffsetsToTransaction()`. The application does not need to call `consumer.commitSync()` or manually send offsets.

When the transaction commits successfully:

- Output records are committed and readable by `read_committed` consumers.
- The input offset is committed in the same transaction.
- The consumer group continues from the next position.

When the transaction aborts:

- The transaction's output records are not exposed to `read_committed` consumers.
- The input offset is not committed in the aborted transaction.
- The consumer can re-read the record from its recovered position.

This is the core of EOS: there is no state where outputs are committed while the input offset of the same transaction is uncommitted, or vice versa.

## 9. Downstream consumers need `read_committed`

Kafka consumers have two main isolation levels:

| `isolation.level` | Behavior |
| --- | --- |
| `read_uncommitted` | May read records belonging to incomplete or aborted transactions |
| `read_committed` | Returns only records belonging to committed transactions |

So downstream does not observe outputs from rolled-back transactions, configure the consumer:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[isolation.level]": read_committed
```

`read_committed` can make consumers wait at log regions with unfinished transactions (the last stable offset), so observed latency may rise when transactions stay open for a long time. Keep transactions short and monitor transaction timeouts.

## 10. EOS V2 and fencing

Modern Spring Kafka uses `EOSMode.V2` as its Exactly Once Semantics mechanism. V2 requires Kafka brokers 2.5 or newer and uses consumer group metadata when sending offsets to transactions so the broker can verify whether the producer is still valid or has been fenced.

From Spring Kafka 3.0 onward, V2 is the only supported mode. In older Spring Kafka lines, `V1` used producer/fencing mechanics tied to group/topic/partition; do not reuse the legacy mode in modern applications.

Fencing protects the group when a partition moves from an old consumer to a new consumer. The old producer cannot finish an invalid transaction after the broker has fenced that producer.

Do not confuse fencing with business idempotency. Listeners can still be invoked again after a rollback; EOS guarantees Kafka outputs and input offsets commit atomically, not that a Java method runs only once.

## 11. Producer transactional IDs and multi-instance execution

`transactionIdPrefix` is used to generate `transactional.id` for each producer in the factory's cache. The prefix must be unique across concurrently running application instances.

Example:

```text
orders-projection-pod-a-tx-0
orders-projection-pod-b-tx-0
orders-projection-pod-c-tx-0
```

If two instances use the same prefix, they can generate the same transactional ID. When a new producer initializes with an ID already used by another producer, the old producer may be fenced and receive `ProducerFencedException`.

Operational notes:

- Build the prefix from the application name plus a unique instance ID.
- Do not use the same static prefix for all pods/replicas.
- When scaling deployments, ensure each instance receives a distinct prefix.
- Monitor `ProducerFencedException`, transaction timeouts, and coordinator errors.
- If a producer may sit idle longer than the broker's `transactional.id.expiration.ms`, consider setting `maxAge` on the producer factory lower than the broker expiration to refresh producers before they are fenced due to expiration.

## 12. Retry and rollback: `AfterRollbackProcessor`

With a transactional listener, an exception escaping the listener causes the Kafka transaction to roll back. Post-rollback handling is managed by `AfterRollbackProcessor`, typically via `DefaultAfterRollbackProcessor`.

Processing flow:

```text
Listener starts in transaction
          |
          v
Processing fails, throws exception
          |
          v
Transaction rollback
          |
          v
DefaultAfterRollbackProcessor
          |
     +----+----------------+
     |                     |
     v                     v
  Seek/retry          Retries exhausted
     |                     |
     v                     v
Listener runs again    Recover/DLT
```

Do not swallow exceptions inside the listener if you want the transaction to roll back. If the listener catches the exception and returns normally, the container can treat processing as successful and commit the transaction.

`DefaultErrorHandler` is normally used for non-transactional listeners. With container transactions, design retry/recovery around `AfterRollbackProcessor`; do not blindly apply blocking retry configurations meant for non-transactional listeners.

Once retries are exhausted, you can configure a recoverer to publish the record to a DLT. If you want the DLT publish and original offset to commit atomically, configure the after-rollback processor with in-transaction recovery, such as `commitRecovered=true` with a transactional `KafkaTemplate` according to your Spring Kafka version's API.

## 13. Non-blocking retry is not used with container transactions

`@RetryableTopic` implements non-blocking retry by publishing records to retry topics for later consumption. This mechanism is incompatible with container transactions.

If the listener requires read-process-write EOS, use transaction rollback and blocking retry via `AfterRollbackProcessor`. If isolating failing records off the main partition and accepting altered ordering is preferred, use retryable topics with a non-transactional listener container.

Do not combine `@RetryableTopic` and a transactional listener expecting outputs, retry topics, and input offsets to reside in a single Kafka transaction.

## 14. Transactional listeners do not automatically cover databases

Kafka transactions manage only Kafka operations. If a listener both updates a database and sends Kafka output, the two systems do not automatically become an atomic distributed transaction.

For example, the following can happen:

1. The database transaction commits successfully.
2. The Kafka transaction commit fails.
3. The input record is redelivered.
4. The database update may run a second time.

Or in the reverse order, Kafka commits successfully while the database transaction fails. Therefore, do not describe Kafka EOS as exactly-once for databases, HTTP services, or email.

Common solutions:

- Use a transactional outbox to store business changes and events in the same database transaction; a separate publisher sends events to Kafka.
- Use inbox/event IDs and unique constraints so consumers handle redeliveries safely.
- Design business operations to be idempotent.
- Use sagas/compensation when workflows span multiple systems without a shared distributed transaction.

Spring can synchronize commit ordering between a Kafka transaction manager and another transaction manager in certain patterns, yet that is not an XA/distributed atomic commit. Clearly establish which transaction commits first and handle the failure window between systems.

## 15. Transaction timeouts and listener processing time

Producer transactions have time limits. `transaction.timeout.ms` sets the producer-side transaction timeout; the broker enforces a maximum `transaction.max.timeout.ms`.

A listener that runs too long can hit transaction timeouts, exceed consumer `max.poll.interval.ms`, trigger rebalances, or suffer producer fencing. Control and monitor:

- High-percentile record/batch processing time.
- Timeouts for database/HTTP calls invoked inside the listener.
- `transaction.timeout.ms` and broker limits.
- `max.poll.interval.ms` and `max.poll.records`.
- Backoff/retry durations and open transaction time.
- Transaction coordinator and broker health.

Do not increase the transaction timeout indefinitely to mask a slow listener. Optimize synchronous work, reduce batch size, or offload long-running tasks to another workflow when needed.

## 16. Broker configuration and access permissions

Kafka transactions rely on the transaction coordinator and the internal `__transaction_state` topic. Production clusters need an appropriate replication factor and min ISR to store transaction state durably.

Relevant broker configurations:

| Configuration | Meaning |
| --- | --- |
| `transaction.state.log.replication.factor` | Replication factor of the transaction state topic |
| `transaction.state.log.min.isr` | Minimum in-sync replicas required to accept transaction state writes |
| `transaction.max.timeout.ms` | Maximum transaction timeout accepted by the broker |

On a single-broker cluster used for learning, replication factor/min ISR may need to be set to 1. That configuration does not provide the durability and fault tolerance of a multi-broker production cluster.

When ACLs are enabled, the producer principal needs permission to use the transactional ID and write to target topics; the consumer needs permission to read the input topic and join the group. Exact permissions depend on the cluster's authorization mechanism. Check both transaction coordinator permissions and topic permissions when encountering `TransactionalIdAuthorizationException` or authorization errors.

## 17. Observing transactional listeners

To verify transactions are working properly, monitor:

- Committed/aborted transaction counts and abort rate.
- Transaction duration and timeouts.
- `ProducerFencedException`.
- Consumer lag and rebalances.
- `AfterRollbackProcessor` errors and retry counts.
- DLT publish/recovery failures.
- Listener processing time and downstream latency.

When investigating a record, log topic, partition, offset, key, event ID/correlation ID, and transaction outcome. Avoid logging sensitive payloads.

## 18. Testing transactional listener containers

Integration tests must verify both the output topic and the input offset. Checking only that the listener method was invoked is insufficient to prove transaction atomicity.

Successful commit scenario:

1. Create input and output topics on the test broker.
2. Configure a producer factory with a unique transaction ID prefix.
3. Attach `KafkaTransactionManager` to the listener container factory.
4. Send a record to the input topic.
5. Listener sends output using `KafkaTemplate` with the same producer factory.
6. Confirm a `read_committed` consumer receives the output and the input group offset advances.

Rollback scenario:

1. Send another record to the input topic.
2. Listener sends output and then throws an exception before returning.
3. Confirm output from the aborted transaction does not appear to `read_committed` consumers.
4. Confirm the input record is retried according to `AfterRollbackProcessor`.
5. Allow the retry to succeed and confirm output appears only from the committed transaction.

Also test multiple application instances with distinct prefixes, producer fencing, transaction timeouts, DLT recovery, and consumer restarts mid-processing. Use latches/conditions with timeouts to await assignment, commit, and redelivery; avoid short fixed sleeps.

## 19. Common errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Listener does not run in a transaction | Producer factory lacks transaction ID prefix or container has no manager attached | Check `transactionIdPrefix` and `setKafkaAwareTransactionManager` |
| Output commits despite listener error | Exception was caught and not propagated out | Let the exception propagate so the container rolls back |
| Output and input offset are not atomic | `KafkaTemplate` uses a different producer factory | Use the same producer factory as the transaction manager |
| Downstream sees aborted outputs | Consumer uses `read_uncommitted` | Set `isolation.level=read_committed` |
| `ProducerFencedException` | Duplicate transactional ID/prefix across instances or expired producer fenced | Provide unique prefixes and consider producer `maxAge` |
| Transaction timeout | Listener takes too long or timeout is set too low | Measure processing time, optimize I/O, and tune timeout within limits |
| Record retries do not behave as expected | Wrong error handler mechanism used for transactional listener | Configure `AfterRollbackProcessor` and let exceptions escape the listener |
| Non-blocking retry does not work with transactions | `@RetryableTopic` does not support container transactions | Choose blocking rollback retry or non-transactional non-blocking retry |
| DB and Kafka drift out of sync | Kafka transactions do not cover databases | Use outbox/inbox and idempotency |

## 20. Pre-deployment checklist

- [ ] Producer factory has `transactionIdPrefix`.
- [ ] Prefix is unique across concurrently running instances.
- [ ] `KafkaTransactionManager` uses the exact same producer factory.
- [ ] Listener container factory has `KafkaAwareTransactionManager` attached.
- [ ] `KafkaTemplate` uses the same producer factory.
- [ ] Listener does not swallow exceptions meant to trigger rollback.
- [ ] Downstream consumers use `read_committed`.
- [ ] Retry/recovery is configured with an appropriate `AfterRollbackProcessor`.
- [ ] Non-blocking retry topics are not combined with container transactions.
- [ ] Databases and external side effects have outbox/inbox or idempotency.
- [ ] Transaction timeouts, poll intervals, and downstream timeouts are verified.
- [ ] Broker transaction state topic, replication, and ACLs are ready.
- [ ] Integration tests verify both commit and rollback.

## 21. Conclusion

Spring Kafka's transactional listener container opens a Kafka transaction before invoking the listener. `KafkaTemplate` operations using the same producer factory join the transaction; when the listener finishes, the container sends the input offset into the transaction and commits. If the listener throws an exception, the transaction rolls back and `AfterRollbackProcessor` coordinates retry/recovery.

To implement this, configure a producer factory with a unique transaction ID prefix, create a `KafkaTransactionManager`, attach the manager to the container via `setKafkaAwareTransactionManager(...)`, and ensure the template uses the same producer factory. Downstream consumers need `read_committed` to see only committed outputs. This mechanism provides EOS for read-process-write across Kafka topics; databases and external side effects still require dedicated outbox/inbox or idempotency.

## References

- [Spring for Apache Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Spring for Apache Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html)
- [Spring for Apache Kafka — Listener Container Properties](https://docs.spring.io/spring-kafka/reference/kafka/container-props.html)
- [Apache Kafka — Transactions](https://kafka.apache.org/documentation/#transactions)
