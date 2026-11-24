# ContainerProperties.EOSMode and modern options

When a Kafka listener reads records, processes data, and sends results to another topic, the application must ensure that both the output and the input offset are recorded consistently. If the output is written but the offset is not committed, the input record can be re-read and produce duplicate output. If the offset is committed but the output is not written, results can be lost. Kafka transactions combined with the Spring Kafka listener container close this gap by placing both the output and input offsets into the same transaction.

`ContainerProperties.EOSMode` selects the Exactly Once Semantics (EOS) mechanism used by the listener container when running with transactions. In modern Spring Kafka versions, the supported option is `V2`. To use EOS, setting `EOSMode` alone is not enough: the producer factory must support transactions, the listener container must have a `KafkaAwareTransactionManager` attached, and the broker must meet compatibility requirements.

## 1. What problem does EOS solve in consumers?

Suppose an `order-projection` service reads events from topic `orders.in`, computes order state, and sends results to `orders.out`.

Without transactions, the following two operations are independent:

1. Sending the result to `orders.out`.
2. Committing the offset of the record read from `orders.in`.

Two failure windows can occur:

- The output is written, but the application stops before committing the offset. The input record is re-read and the output may be written a second time.
- The offset is committed, but the application stops before the output is written successfully. The consumer will not re-read that record per the committed offset and results can be missing.

With Kafka transactions, Spring Kafka can write outputs and input offsets within the same transaction. The broker exposes the transaction's writes only when the entire transaction commits successfully.

```text
orders.in
    |
    v
Consumer reads record
    |
    v
Listener performs business processing
    |
    +---- KafkaTemplate sends result ----> orders.out
    |
    +---- Input offset ------------------> Kafka transaction
                                              |
                                              v
                                        COMMIT or ABORT
```

If the listener finishes normally, the container sends the offset into the transaction via `sendOffsetsToTransaction()` and then commits the transaction. If the listener throws an exception, the transaction rolls back and the consumer is repositioned so the record can be re-read. Downstream consumers using `isolation.level=read_committed` only observe outputs from committed transactions.

## 2. What is `ContainerProperties.EOSMode`?

`ContainerProperties` contains settings controlling the listener container, among which `eosMode` selects the fencing mechanism used for Exactly Once Semantics. This enum was introduced in Spring Kafka 2.5.

Two implementations were historically used: V1 and V2:

| Mode | Mechanism | Requirements and status |
| --- | --- | --- |
| `V1` | Fencing based on `transactional.id`; older Spring Kafka used separate producers per group/topic/partition for record listeners to prevent stale consumers from continuing to write | Intended for older brokers from 0.11 up to pre-2.5; removed as an option in Spring Kafka 3.0+ |
| `V2` | Fetch-offset-request fencing; consumer metadata is sent along with offsets into the transaction so the broker determines whether the producer is still valid or fenced | Requires Kafka broker 2.5 or newer; the only mode supported in Spring Kafka 3.0+ |

V2 eliminates the need for separate producers for every consumer group/topic/partition combination. The broker uses consumer metadata included with the transaction's offsets to check fencing. This mechanism is described in KIP-447.

In some older Spring Kafka 2.x versions, the enum also had `ALPHA` and `BETA` as historical aliases for `V1` and `V2`; they were deprecated. When reading older code, verify the exact library version. For Spring Kafka 3.x and 4.x, never select `V1`, `ALPHA`, or `BETA`; use `V2` exclusively.

## 3. Default mode and modern configuration

`EOSMode.V2` is the default value in `ContainerProperties` across modern Spring Kafka releases. Consequently, with Spring Kafka 3.x/4.x, you normally do not need to set `eosMode` explicitly in code.

If you want to express it explicitly on a manually configured listener container:

```java
import org.springframework.kafka.listener.ContainerProperties;

factory.getContainerProperties()
        .setEosMode(ContainerProperties.EOSMode.V2);
```

This statement only selects the EOS V2 mechanism. It does not create transactions by itself, does not enable transactions on the producer, and does not attach a transaction manager to the container. Those components must be configured separately.

Do not attempt to set `spring.kafka.listener.eos-mode=V1` in modern application configuration. `EOSMode` is a `ContainerProperties` setting; Boot does not provide a V1 option to restore the legacy mechanism in Spring Kafka 3.0+.

## 4. Enabling transactions on the producer factory

Spring Kafka enables transactions when `DefaultKafkaProducerFactory` is configured with `transactionIdPrefix`. The factory manages a cache of transactional producers; each producer's `transactional.id` is formed from the prefix plus a suffix allocated by the factory.

With Spring Boot, the shortest configuration is declaring `spring.kafka.producer.transaction-id-prefix`:

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

When the transaction ID prefix property is set, Spring Boot auto-configures `KafkaTransactionManager` and attaches it to the auto-configured listener container. In multi-instance deployments, `INSTANCE_ID` must be unique per instance, such as a pod name or instance identifier assigned by the deployment platform. Never share the same prefix across concurrent instances because they can contend on `transactional.id` and fence each other's producers.

The `local` value is suitable only when running a single local instance. When running multiple replicas, assign a distinct prefix to each replica.

## 5. Attaching KafkaTransactionManager to the listener container

If not using Spring Boot auto-configuration or when creating a custom listener container factory, attach `KafkaAwareTransactionManager` to `ContainerProperties`.

Example using a producer factory already configured with a transaction ID prefix:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.transaction.KafkaTransactionManager;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.listener.ContainerProperties;

@Configuration
public class KafkaTransactionConfiguration {

    @Bean
    public KafkaTransactionManager<String, String> kafkaTransactionManager(
            ProducerFactory<String, String> producerFactory) {
        return new KafkaTransactionManager<>(producerFactory);
    }

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
        factory.getContainerProperties()
                .setEosMode(ContainerProperties.EOSMode.V2);
        return factory;
    }
}
```

This snippet assumes `ProducerFactory` is configured with `transactionIdPrefix` and `ConsumerFactory` has bootstrap servers, deserializers, and required security properties. The `KafkaTemplate` used to send outputs must share the same producer factory as the transaction manager so send operations participate in the right transaction.

In Spring Kafka 3.2 and newer, use `setKafkaAwareTransactionManager(...)`. The older `setTransactionManager(PlatformTransactionManager)` API was deprecated as of 3.2 and replaced by this dedicated API.

## 6. Read-process-write flow with EOS V2

Example listener that reads an order event, transforms the payload, and sends the result to another topic:

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
            groupId = "order-projection")
    public void process(ConsumerRecord<String, String> record) {
        String projection = transform(record.value());

        kafkaTemplate.send(
                "orders.out",
                record.key(),
                projection);
    }

    private String transform(String event) {
        return "projection:" + event;
    }
}
```

When the listener container has `KafkaTransactionManager` attached, the container starts a Kafka transaction before invoking `process`. The `KafkaTemplate.send` call joins the active transaction. When the listener completes, the container sends the input offset into the same transaction and commits it.

If `transform` or the send throws an exception and that exception escapes the listener, the container rolls back the transaction. The input record can be re-read and the listener may run again. Thus, EOS does not mean the Java method is invoked strictly once; it guarantees the Kafka outputs of the read-process-write sequence commit transactionally, preventing outputs from rolled-back attempts from being visible to `read_committed` consumers.

Do not catch and ignore exceptions when business logic requires rollback. If the listener catches the exception and exits normally, the container may treat processing as successful and commit the transaction.

## 7. Role of isolation.level=read_committed

Kafka consumers have two common isolation levels:

| Value | Behavior |
| --- | --- |
| `read_uncommitted` | Can read records belonging to open transactions or transactions that eventually abort |
| `read_committed` | Returns only records belonging to committed transactions; skips data from uncommitted or aborted transactions |

So downstream consumers do not observe outputs from rolled-back transactions, consumers reading the output topic must use `isolation.level=read_committed`. In Spring Boot:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[isolation.level]": read_committed
```

If a downstream consumer still uses `read_uncommitted`, it may see records from aborted transactions and the application will not observe the full benefit of transactions. Align the isolation level across consumers participating in transactional flows.

## 8. What does EOS guarantee and what does it not guarantee?

The scope of EOS in Spring Kafka is the `read → process → write` sequence when input offsets and output records participate in the same Kafka transaction.

| Scenario | How EOS V2 handles it |
| --- | --- |
| Listener sends output and finishes | Output and input offset commit in the same transaction |
| Listener throws exception before commit | Transaction aborts; uncommitted output is hidden from `read_committed` consumers; input can be re-read |
| Old consumer keeps writing after partition moved to a new consumer | Broker fencing blocks the stale producer from completing invalid transactions |
| Listener updates a database then sends to Kafka | Kafka transactions do not automatically encompass database transactions |
| Listener calls HTTP or sends email | Side effects outside Kafka are not rolled back by Kafka transactions |

Reads and processing can still re-execute after a rollback or failure. Therefore, distinguish between "the sequence whose Kafka outcome commits exactly once" and "business code executing only once".

Nor does EOS automatically create an atomic distributed transaction between Kafka and a relational database, HTTP service, email provider, or other storage system. If a listener updates a database and then sends to Kafka, a failure between the two steps can still leave inconsistent state. Use transactional outbox/inbox, idempotency keys, or compensating workflows to manage that boundary.

## 9. Producer idempotence vs. EOS

Kafka producer idempotence helps avoid duplicate writes caused by producer retries under supported conditions. It does not automatically tie consumer offsets to output records.

| Mechanism | Scope |
| --- | --- |
| Idempotent producer | Prevents duplicates from producer-side retries |
| Kafka transaction | Groups multiple Kafka writes and/or offsets into a single transaction |
| Listener container EOS V2 | Combines record processing, output writes, and input offset commits in a transaction |
| Idempotent business handler | Tolerates listener re-invocation or duplicates from other sources |
| Outbox/inbox | Solves consistency between databases and messaging at the application boundary |

Enabling producer idempotence alone is not enough to claim a read-process-write consumer has EOS. You need transactions managed by the listener container with offsets sent into the same transaction as the outputs.

## 10. Record listeners and batch listeners

With a record listener, the container can run one transaction per record. When the listener succeeds, the output and the record's offset commit together.

With a batch listener, the container processes a group of records received from one poll. If a batch listener throws an exception, by default the entire batch may be re-read after rollback because the framework cannot always tell which record in the batch failed. Account for this when sizing batches and designing business operations.

You can use `AfterRollbackProcessor` to handle post-rollback work, retry records, or recover failed records according to policy. For batch listeners, define batch scope, recovery strategy, and duplicate tolerance clearly before going to production.

## 11. Retries and dead-letter topics with container transactions

When a listener runs inside a container transaction, errors roll back the transaction. Spring Kafka can use `AfterRollbackProcessor` to seek, retry, and eventually recover failed records, such as sending them to a dead-letter topic.

One important point is that **non-blocking retry topics** (such as `@RetryableTopic`) cannot be combined with container transactions. With non-blocking retries, when the listener throws an exception, the container transaction commits and the record is sent to a retry topic via a separate mechanism; that is not equivalent to rolling back the entire read-process-write transaction.

If the requirement is preserving atomicity of outputs and offsets, design retries around transactions/rollbacks, typically blocking retries and `AfterRollbackProcessor`. If avoiding partition blocking during retries via separate retry topics is preferred, re-evaluate the EOS requirements for that stream.

## 12. Transaction ID prefix and fencing across multiple instances

Every transactional producer has a `transactional.id`. With EOS V2, fixed transactional IDs per group/topic/partition are no longer needed, but the prefix must still be unique across concurrently running application instances.

Example:

```text
Instance A: orders-projection-pod-a-orders-tx-0
Instance B: orders-projection-pod-b-orders-tx-0
```

If two instances use the same prefix, they can generate identical transactional IDs. When one producer initializes a transaction with an ID already used by another instance, the prior producer can be fenced and receive `ProducerFencedException`.

Operational notes:

- Build the prefix from the application name plus a unique instance ID.
- Never use the same static value across all pods/replicas.
- When scaling deployments, ensure each instance receives its own value.
- Monitor `ProducerFencedException`, transaction timeouts, and coordinator errors.
- If transactional producers may sit idle longer than the broker's `transactional.id.expiration.ms`, consider setting `maxAge` on the producer factory lower than the broker expiration so the factory refreshes producers before they get fenced by expiration.

## 13. Broker configuration and deployment requirements

EOS V2 requires Kafka broker version 2.5 or newer. Beyond version compatibility, the cluster must operate the transaction coordinator and internal `__transaction_state` topic with proper settings.

In production, inspect settings such as replication factor and min ISR for the transaction state log, transaction timeouts, broker capacity, and coordinator recovery. On a single-broker learning cluster, replication factors may have to be set to one; such a setup does not provide durability or fault tolerance comparable to a multi-broker cluster.

Transactional producers also require proper permissions to write destination topics and use transactional IDs. If the cluster enforces ACLs, verify `Write`, `Describe`, and transactional ID permissions under your platform's security model.

## 14. When to use EOS V2 and when to choose another approach?

EOS carries operational overhead and transaction latency. Not every listener needs transactional read-process-write.

| Need | Suitable choice |
| --- | --- |
| Read from Kafka, transform, and write to Kafka; require atomic outputs and offsets | Container transactions with EOS V2 |
| Only read and update a projection that can tolerate reprocessing | Standard listener, AckMode commits, and business idempotency |
| Emit events from a database after data commits | Transactional outbox and a dedicated publisher |
| Need non-blocking retries without stalling partitions via retry topics | Non-blocking retries; do not combine with container transactions on that stream |
| Only need to prevent duplicates from producer retries | Producer idempotence; container EOS unnecessary without consume-process-write |
| Call external APIs or send emails inside a listener | Idempotency keys, outbox, or compensating logic; Kafka EOS cannot roll back external effects |

Choose EOS when the value of committing outputs and offsets together outweighs transaction overhead. For consumers only updating state idempotently, a simpler at-least-once model may be easier to operate.

## 15. Distinguishing container transactions and producer transactions

Spring Kafka offers multiple ways to initiate Kafka transactions. Their purposes are related, not interchangeable:

| Way to start a transaction | Primary scope | Automatically includes input offset in transaction? |
| --- | --- | --- |
| Listener container using `KafkaAwareTransactionManager` | Read-process-write inside a listener | Yes; container sends offsets into transaction before committing |
| `@Transactional` with `KafkaTransactionManager` | Group of Kafka sends from a service | Not automatically; this is a producer-initiated transaction |
| `TransactionTemplate` with `KafkaTransactionManager` | Programmatic producer transaction control | Not automatically |
| `KafkaTemplate.executeInTransaction(...)` | Group of Kafka sends in a local transaction | No; callback only groups producer operations |
| Listener without a transaction manager | Processes records and commits offsets per AckMode | No; uses standard container commit semantics |

Example of `KafkaTemplate.executeInTransaction`:

```java
kafkaTemplate.executeInTransaction(operations -> {
    operations.send("orders.audit", orderId, auditEvent);
    operations.send("orders.projection", orderId, projectionEvent);
    return true;
});
```

If the callback completes normally, the transaction commits; if an exception escapes the callback, the transaction rolls back. This is a transaction for the send calls inside the callback. It does not place a running listener's offsets into that transaction.

If a Kafka transaction has already been started by `KafkaTransactionManager` or transaction synchronization, `executeInTransaction` creates a new nested transaction instead of joining the existing one. Therefore, inside a listener container running EOS, call `KafkaTemplate.send(...)` directly so the sends join the container's transaction; do not wrap those calls in `executeInTransaction` when the goal is sharing a transaction with input offsets.

## 16. EOS V2 verification checklist

Before deploying a transactional listener to production, check:

- [ ] Spring Kafka 3.0+ uses `EOSMode.V2` only.
- [ ] Kafka brokers are version 2.5 or newer.
- [ ] Producer factory has `transactionIdPrefix` and supports transactions.
- [ ] `transactionIdPrefix` is unique per application instance.
- [ ] Listener container has `KafkaAwareTransactionManager` attached.
- [ ] `KafkaTemplate` uses the same producer factory as the transaction manager.
- [ ] Downstream consumers read transactional outputs with `isolation.level=read_committed`.
- [ ] Listener throws exceptions when business logic requires rollback; errors are not swallowed unintentionally.
- [ ] Retries and DLT are designed compatibly with container transactions.
- [ ] Non-blocking `@RetryableTopic` is not combined with container transactions.
- [ ] Database and external side effects have separate outbox/inbox or idempotency mechanisms.
- [ ] Tests cover successful commits, rollbacks, redelivery, and fencing.

## 17. Testing commit and rollback behavior

Integration tests should verify what a `read_committed` consumer observes, rather than merely checking whether the listener was called. A test scenario should include:

1. Send a record to the input topic.
2. Listener reads the record, sends output inside the transaction, and completes normally.
3. Verify the `read_committed` consumer receives the output and the input offset advances.
4. Send another record causing the listener to throw an exception after calling `KafkaTemplate.send`.
5. Verify the output from the rolled-back transaction is not visible to `read_committed` consumers.
6. Verify the input record can be retried/redelivered per the after-rollback processor configuration.

In addition, test multiple instances with distinct prefixes, stop/restart consumers mid-processing, and inspect fencing logs. Tests should wait for transactions and consumer assignments to settle using explicit conditions/timeouts; avoid relying solely on fixed `Thread.sleep` calls.

## 18. Conclusion

`ContainerProperties.EOSMode` controls the listener container's Exactly Once Semantics mechanism. V1 was an older fencing approach based on transactional IDs; V2 uses fetch-offset-request fencing and requires Kafka broker 2.5 or newer. Spring Kafka 3.0 and modern releases support only V2 and make V2 the default.

For true EOS, configure a transactional producer factory, a unique transaction ID prefix per instance, and a `KafkaAwareTransactionManager` on the listener container. The container places outputs sent via `KafkaTemplate` together with input offsets into one Kafka transaction. The guarantee covers the Kafka outcomes of the read-process-write chain; listeners may still re-execute, and databases or external side effects require their own consistency mechanisms.

## References

- [Spring Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html)
- [Spring Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Spring Kafka — Listener Container Properties](https://docs.spring.io/spring-kafka/reference/kafka/container-props.html)
- [Apache Kafka KIP-447 — Producer scalability for exactly once semantics](https://cwiki.apache.org/confluence/display/KAFKA/KIP-447%3A+Producer+scalability+for+exactly+once+semantics)
