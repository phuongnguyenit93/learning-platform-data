# EOSMode and client versions

Exactly-once semantics (EOS) in Spring Kafka enables a consume-process-produce flow to write Kafka results and acknowledge input offsets as a single transactional unit. When the transaction commits, output records and offsets are committed together; when the transaction aborts, neither the output nor the offset is considered committed. Consumers using `read_committed` read only records belonging to committed transactions.

This capability depends on the Kafka broker version, the `kafka-clients` library, and Spring Kafka. Spring Kafka provides two historical models: `EOSMode.V1` and `EOSMode.V2`. Choosing the right mode and client version avoids incompatible configurations, while determining how producers are allocated and how the broker fences an old consumer after a rebalance.

## 1. What does EOS guarantee?

In a consume-transform-produce listener, the application reads an input record, processes it, and sends one or more output records. If it simply sends output and commits offsets as two independent operations, the following can happen:

- Output has been written, but the input offset is not committed; when the consumer re-reads, output may be written again.
- Input offset is committed, but output is not written; the input event is skipped even though no result exists.

Kafka transactions combine publishing output and writing consumer offsets into the same Kafka transaction. When the transaction commits, both take effect together. When the transaction aborts, the consumer re-reads the input record and output from the aborted transaction is not visible to `read_committed` consumers.

```text
Consumer poll input record
          |
          v
Begin Kafka transaction
          |
          v
Process record -> KafkaTemplate.send(output)
          |
          v
Send input offset to transaction
          |
          v
Commit transaction
     /          \
  success       abort
    |              |
output + offset   output and offset do not commit
both commit       input can be read again
```

EOS protects data flows inside Kafka. It does not automatically make REST calls, email sending, or relational database updates exactly-once. Side effects outside Kafka still need idempotency, outbox, or a separate coordination mechanism.

## 2. How do EOSMode V1 and V2 differ?

`EOSMode` describes how Spring Kafka creates and fences transactional producers in the listener container.

| Characteristic | EOSMode.V1 | EOSMode.V2 |
| --- | --- | --- |
| Fencing model | Uses transactional producers tied to each partition being processed | Uses consumer group metadata so the broker fences old producers when the group changes |
| Producer scope | May require one producer per partition | Can reuse producers per listener thread |
| Scalability | More producers when there are many partitions | Fewer producers and better suited for high concurrency |
| Broker requirement | Kafka supporting transactions, from 0.11.0.0 | Kafka 2.5.0 or higher, supporting KIP-447 |
| Status in Spring Kafka | Legacy compatibility model; deprecated in newer lines | Modern model; the only mode in Spring Kafka 3.0 and later |

V1 uses a distinct transactional ID per group/topic/partition to ensure only the producer currently owning a partition can complete transactions for that partition. This approach can create many producers when the application has many partitions.

V2 leverages a change in Kafka 2.5 (KIP-447): the producer sends consumer group metadata when adding offsets to a transaction. The broker can detect a producer belonging to an older consumer generation and fence it. As a result, Spring Kafka can use producers per listener thread instead of needing a separate producer for every partition.

For new projects, use EOS V2 on a compatible broker. Do not choose V1 just because an old example uses that mode; determine the actual Spring Kafka and broker versions running.

## 3. Relationship between Spring Kafka, kafka-clients, and broker

Three versions must be considered separately:

- **Spring Kafka:** provides the listener container, transaction manager, producer factory, and EOS integration.
- **Kafka client (`kafka-clients`):** the Java library Spring Kafka uses to communicate with the broker; client APIs and protocols must support the chosen EOS mechanism.
- **Kafka broker:** the Kafka cluster must support transactions and the corresponding fencing/consumer group metadata protocols.

Key milestones:

| Milestone | Significance |
| --- | --- |
| Kafka 0.11.0.0 | Introduced transactional and idempotent producers; foundation for EOS V1 |
| Kafka 2.5.0 | Added protocol changes required for EOS V2 (KIP-447) |
| Kafka Java client 2.5.0 | Includes consumer group metadata API needed to send offsets into transactions under EOS V2 |
| Spring Kafka 2.5 | Added EOS V2 support to leverage Kafka 2.5+ brokers |
| Spring Kafka 2.8 | EOS V1 marked deprecated; V2 is the recommended path |
| Spring Kafka 3.0+ | Only EOS V2 remains; requires Kafka 2.5+ broker |

The minimum broker milestone for V2 does not mean any `kafka-clients` version can be used with any Spring Kafka version. Use the `kafka-clients` version managed by Spring Kafka or Spring Boot dependency management. If overriding manually, verify the compatibility matrix of the exact Spring Kafka, client, and broker releases. Avoid upgrading `kafka-clients` alone to a major version unsupported by the current Spring Kafka release.

For EOS V1, the broker must support transactions (Kafka 0.11.0.0 or higher). For EOS V2, both the broker and Kafka Java client must be 2.5.0 or higher to support consumer group metadata in transactions. This is the minimum feature level; the actual client version must still fall within the range supported by the Spring Kafka release in use. Using the client version managed by the framework's BOM is safer than choosing a client solely by broker version.

## 4. Configuring transactional producers in Spring Boot

To use Kafka transactions, the producer needs `transactional.id`. When using Spring Boot, you can configure a transaction ID prefix:

```yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: ${HOSTNAME:local}-orders-
      acks: all
      properties:
        enable.idempotence: true
    consumer:
      properties:
        isolation.level: read_committed
```

`transaction-id-prefix` allows Spring Kafka to generate distinct transactional IDs for each producer allocated from the factory. The prefix must be unique across concurrently running application instances. If two instances use the same prefix and create producers with the same suffix, they can fence each other and cause transaction errors.

When the prefix is configured, Spring Boot can auto-configure `DefaultKafkaProducerFactory` in transaction mode and provide a `KafkaTransactionManager` for that producer factory. Inspect the actual configuration if the application declares its own producer factory or transaction manager.

`acks=all` and idempotence help the producer ensure send reliability; a transactional producer also requires transaction ID configuration. When `transactional.id` is set, the Kafka producer requires idempotence and compatible settings. Let the client apply compatible defaults or configure according to the client version documentation rather than overriding conflicting values.

A `read_committed` consumer reads only committed records. If a consumer uses `read_uncommitted`, it may see records from aborted transactions, defeating the purpose of EOS on the read side.

## 5. Selecting EOSMode on the listener container

In Spring Kafka versions that still allow configuring both modes, EOS mode belongs to `ContainerProperties` of the listener container. Example configuring V2:

```java
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.listener.ContainerProperties;

factory.getContainerProperties()
        .setEosMode(ContainerProperties.EOSMode.V2);
```

In Spring Kafka 3.0 and later, V2 is the only mode, so there is no V1/V2 selection to switch between. Mode configuration APIs can change across major versions; when upgrading, check the `ContainerProperties` Javadoc in the exact dependency rather than copying code snippets from documentation of another release.

In many Spring Boot applications, configuring the transaction ID prefix is enough to activate Kafka transactions for the listener container. If the application has a custom factory, ensure the factory uses a transaction-configured producer factory/transaction manager and that the container has an appropriate transaction manager.

## 6. Producer and listener participating in the same Kafka transaction

When a listener container is configured for transactions, the container begins a Kafka transaction before invoking the listener. `KafkaTemplate.send()` calls inside the listener participate in the open transaction. After the listener finishes successfully, the container sends the input offset into the transaction and commits. If the listener throws an exception, the transaction is aborted and the input record may be redelivered.

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
class PaymentEventListener {

    private final KafkaTemplate<String, PaymentAccepted> kafkaTemplate;

    PaymentEventListener(
            KafkaTemplate<String, PaymentAccepted> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(topics = "payment-requests")
    public void onPayment(PaymentRequest request) {
        PaymentAccepted result = process(request);
        kafkaTemplate.send(
                "payment-events",
                request.paymentId(),
                result);
    }
}
```

The example assumes the listener container is configured with transactions and `KafkaTemplate` uses the same producer factory. Do not manually call `executeInTransaction()` inside a listener that already has an active transaction unless an independent transaction is needed and the semantics are clearly understood; nested transactions do not automatically form a distributed transaction.

In a record listener, the transaction is typically tied to the listener invocation for that record. With a batch listener, the transaction boundary is tied to the listener invocation for the batch. Choose the listener mode and acknowledgment compatible with processing requirements.

## 7. EOS V2, concurrency, and fencing

In a multi-consumer-instance environment, a rebalance can move partitions from an old consumer to a new consumer. An old consumer might still be running a task after losing partition ownership. If it continues committing transactions, data could conflict with the new consumer.

V2 uses consumer group metadata when sending offsets into a transaction. The broker checks generation and member metadata; the old producer is fenced if it no longer represents a valid consumer of the group. This supports concurrency and rebalances without needing a separate transactional producer for each partition.

The transaction ID prefix must be unique per application instance. Within an instance, Spring Kafka manages suffixes for producers per thread. When deploying multiple replicas, generate distinct prefixes per replica, for example based on hostname or pod identity. The prefix must remain stable over an instance's lifecycle while never colliding across active instances.

Fencing exceptions can occur when an old producer is replaced, prefixes collide, or transaction IDs are misused. Inspect transaction coordinator logs, consumer group rebalances, and transaction ID configuration to distinguish expected fencing from misconfiguration.

## 8. What EOS does not cover

EOS in Kafka does not automatically guarantee exactly-once for all side effects in a listener. For instance, a listener updates a database and then sends to Kafka within the same Kafka transaction: if the Kafka transaction aborts, the database transaction does not automatically roll back unless there is a separate transaction coordination mechanism. The listener may be invoked again and update the database a second time.

| Operation | Protected by Kafka EOS? | Additional handling |
| --- | --- | --- |
| Sending output records to Kafka | Yes, if sent inside the listener's transaction | Use `KafkaTemplate` with the same producer factory/transaction |
| Committing input offsets | Yes, when the container sends offsets into the same Kafka transaction | Configure transactional listener container |
| Reading only committed records | Yes, with `isolation.level=read_committed` | Configure consumer isolation |
| Updating a relational database | Not automatically | Outbox, idempotency, or an explicitly designed distributed transaction |
| Calling REST, sending email, or filesystem operations | No | Idempotency keys, outbox, or compensating workflows |

If a listener needs to update a database and emit Kafka events, Transactional Outbox is often a practical choice. If a consumer needs to update a database from a Kafka event, record the processed event ID and business change in the same database transaction to prevent duplicate deliveries.

## 9. Version upgrade notes

When upgrading Spring Kafka or the Kafka client, check the following points:

1. Determine the actual Spring Boot and Spring Kafka versions; do not infer them solely from the broker version.
2. Check the `kafka-clients` version managed by the BOM and avoid overriding it without good reason.
3. Verify minimum broker versions: EOS V1 requires a transaction-supporting broker from 0.11; EOS V2 requires broker 2.5+.
4. If upgrading to Spring Kafka 3.0+, remove V1 configurations and verify all brokers support V2.
5. Check that transaction ID prefixes are unique across all replicas.
6. Verify consumers use `read_committed` when records from aborted transactions must be hidden.
7. Check ACL permissions for transactional IDs and topics; the broker must allow producers to use transactions.
8. Test rebalances, producer fencing, and transaction aborts in a production-like environment.

Do not upgrade the client jar alone to solve an EOS issue before checking Spring Kafka, broker, and dependency management versions. Version mismatches can cause API or protocol errors harder to diagnose than the original problem.

## 10. Testing EOSMode and client compatibility

An integration test should prove that output and offset share the same commit outcome:

- Send an input record and verify the listener publishes the expected output record.
- Make the listener throw an exception after calling `KafkaTemplate.send()`; verify the output transaction is aborted and a `read_committed` consumer does not see that output.
- Verify the input offset was not committed in the aborted transaction and the record is redelivered.
- Let the listener run successfully; verify output appears and the input offset is committed in the same transaction.
- Trigger a rebalance while the listener is processing; verify the old producer is fenced and cannot commit transactions after losing ownership.
- Run a consumer with `read_uncommitted` in a test environment to observe the difference, then ensure production is configured with `read_committed`.
- Verify transaction ID prefixes across multiple instances do not collide.

Beyond functional results, monitor transaction commit/abort counts, producer fencing, transaction timeouts, coordinator errors, and transaction processing duration. A transaction timeout that is too short can abort transactions when listeners take long; too long can hold resources and slow recovery.

## 11. Deployment checklist

- [ ] Spring Kafka, `kafka-clients`, and broker versions are clearly identified.
- [ ] EOS V2 is used only when brokers are Kafka 2.5 or higher.
- [ ] Spring Kafka 3.0+ is configured for EOS V2; no remaining V1 dependencies.
- [ ] `transaction-id-prefix` is configured and unique across instances.
- [ ] Producer factory and listener container actively participate in Kafka transactions.
- [ ] `KafkaTemplate` inside the listener uses the proper producer factory to join the open transaction.
- [ ] Consumers use `isolation.level=read_committed` when only committed records should be read.
- [ ] Transactional ID and topic ACLs allow producers to commit transactions.
- [ ] Side effects outside Kafka have idempotency or Outbox/separate coordination mechanisms.
- [ ] Commit, abort, redelivery, rebalance, and fencing have been tested.

`EOSMode` determines how Spring Kafka manages producers and fencing in the listener container; broker and `kafka-clients` versions determine whether required protocols are supported. Using EOS V2 on Kafka 2.5+ brokers, keeping client versions aligned with Spring Kafka dependency management, and configuring `read_committed` consumers form the foundation for consume-process-produce exactly-once flows in Kafka. Changes outside Kafka still require their own consistent design.
