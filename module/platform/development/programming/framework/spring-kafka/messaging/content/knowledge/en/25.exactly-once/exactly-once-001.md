# Exactly-once semantics in Kafka

Exactly-once semantics (EOS) in Kafka is the ability to guarantee that the result of a Kafka processing flow is published exactly once in terms of committed state, even though the producer or consumer may retry, crash, or restart. To achieve this in a consume-process-produce flow, Kafka needs to combine an **idempotent producer**, **transactions**, and **input offsets committed in the same transaction as the output**.

EOS does not mean that a Java method is invoked only once. A listener can execute again after a rollback or crash. What Kafka guarantees is that output from an uncommitted processing attempt is not visible to `read_committed` consumers, while the output and offset of a successful processing attempt are committed atomically. Side effects outside Kafka such as databases, HTTP, email, or file storage still require idempotency, inbox/outbox, or separate coordination mechanisms.

## 1. Why is Exactly-once needed?

Suppose a service reads events from `orders.in`, computes a projection, and sends the result to `orders.out`. The two main operations are:

1. Write the result to the output topic.
2. Commit the input record's offset so the consumer group knows how far it has processed.

If the two operations are independent, a crash can create two inconsistent states:

| Crash timing | Consequence |
| --- | --- |
| Output written, offset not committed | Input record is read again; output may be written twice |
| Offset committed, output not written | Consumer skips the input record; output is missing |

Kafka transactions allow putting both the output record and the input offset into the same transaction. The broker publishes the transaction only when the commit succeeds. If the transaction aborts, neither the output nor the offset is committed.

```text
orders.in
    |
    v
Consumer reads record
    |
    v
Business processing
    |
    +---- Send output to orders.out
    |
    +---- Add input offset to transaction
                    |
                    v
             Kafka transaction
                    |
              +-----+-----+
              |           |
           COMMIT        ABORT
              |           |
              v           v
       Output + offset   No output/offset
       take effect       is committed
```

## 2. Distinguishing at-most-once, at-least-once, and exactly-once

| Semantics | Processing approach | Main risk |
| --- | --- | --- |
| At-most-once | Commit offset before processing | Tasks may be lost if a crash occurs after commit |
| At-least-once | Process first, then commit offset | Duplicate processing may occur if a crash happens before commit |
| Exactly-once in Kafka | Output and input offset committed together in a transaction | Listener may still run again; only Kafka state is guaranteed atomic |

At-least-once combined with idempotency is often the right choice for consumers updating a database. EOS is suitable when read-process-write between Kafka topics is needed and output/offset must be consistent within the same transaction.

Do not use the phrase "exactly-once delivery" to mean that a record is transmitted over the network only once. Kafka may retransmit requests or re-execute listeners; EOS guarantees the final committed state according to transaction semantics.

## 3. Idempotent producer

A producer may retry sending a record due to network errors, temporary broker unavailability, or request timeouts. If the broker already wrote the record but the response was lost, the producer may resend the request. Without a retry-detection mechanism, the same record could be written twice.

Kafka supports an idempotent producer with the property:

```properties
enable.idempotence=true
```

The broker assigns a producer ID (PID), and the producer uses a sequence number per partition. The broker tracks the sequence to recognize resent requests and deduplicate retries from the same producer session.

```text
Producer (PID 42)
  Partition 0, sequence 10 ---> Broker writes record
  Partition 0, sequence 10 ---> Broker receives retry, detects duplicate
                                Does not write another copy
```

An idempotent producer protects against resends caused by retries at the Kafka producer layer. It does not automatically prevent duplicates caused by the application actively calling `send()` again with a new event, for example when a service encounters a timeout and creates a new publish using another producer.

Idempotence also does not replace transactions. It does not automatically link consumer offsets with output records. If a consumer reads an event and publishes output, an idempotent producer alone still does not resolve the crash window between output and offset commit.

### Configuring idempotence

It can be enabled explicitly in producer properties:

```yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        "[enable.idempotence]": true
```

Modern Kafka producers usually enable idempotence by default if there are no conflicting configurations; declaring it explicitly helps express intent. When idempotence is enabled, compatible conditions include `acks=all`, `retries` greater than 0, and `max.in.flight.requests.per.connection` not exceeding 5. The Kafka client validates these conditions when initializing the producer.

## 4. Kafka transactions

An idempotent producer prevents duplicates from retries within a producer's scope. Kafka transactions extend this capability by grouping multiple write operations into an atomic unit.

A transaction can:

- Write multiple records to one or more topics.
- Write records to multiple partitions.
- Include processed offsets of a consumer group in the same transaction.
- Commit all operations or abort all operations.

A transactional producer requires a stable `transactional.id`. The broker uses a transaction coordinator to manage transaction state and producer epoch. The producer must initialize transactions before sending:

```java
producer.initTransactions();

producer.beginTransaction();
try {
    producer.send(new ProducerRecord<>("orders.out", key, output));
    producer.sendOffsetsToTransaction(offsets, consumer.groupMetadata());
    producer.commitTransaction();
}
catch (Exception exception) {
    producer.abortTransaction();
    throw exception;
}
```

This is pseudocode illustrating the sequence of operations, not a complete consumer poll loop. In real applications, assignment/rebalance, exception types, transaction retries, and proper closing of producer/consumer must be handled. When using a Spring Kafka listener container, the container manages transactions and offsets automatically; the listener does not need to call these transaction APIs.

## 5. Atomic consume-process-produce

The most common EOS flow is a consumer reading a record, the application processing it, and the producer writing the result to another topic. The input offset is included in the same transaction as the output.

Example:

```text
Consumer group: order-projection
Input: orders.in, partition 2, offset 104
             |
             v
       Process order event
             |
             v
       Produce orders.out
             |
             v
       Add offset 105 for partition 2
             |
             v
       Commit transaction
```

If the transaction commits, the output record takes effect and the group offset advances to 105. If the transaction aborts, the output is not published to `read_committed` consumers, and the input offset does not advance for that transaction. The input record can be read again.

This is the atomic boundary of Kafka EOS. It does not mean CPU processing, Java method calls, or logging in the listener are executed only once. Those operations may run again when a transaction rolls back.

## 6. Producer ID, sequence number, and producer epoch

Kafka uses identifiers to recognize producers and control transactions:

| Component | Role |
| --- | --- |
| Producer ID (PID) | Identifies the producer on the broker side |
| Sequence number | Identifies record batch ordering per producer and partition, supporting retry duplicate detection |
| `transactional.id` | Logical identifier of a transactional producer across initializations |
| Producer epoch | Fencing version of a transactional producer; a new epoch invalidates an older producer using the same transactional ID |
| Transaction coordinator | Manages transaction state and coordinates commit/abort |

When a new producer initializes with a `transactional.id` that was previously used, the broker increments the epoch. The older producer with a lower epoch is fenced and cannot continue completing transactions. This mechanism prevents two producers from writing as the same logical producer simultaneously.

For a transactional producer, `transactional.id` must be stable for the same logical producer and unique across concurrently running logical producers. Do not generate the same ID for independent instances.

## 7. Consumer isolation.level

A consumer can read records belonging to open or aborted transactions if using `read_uncommitted`. To see only committed transaction output, set:

```properties
isolation.level=read_committed
```

In Spring Boot:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[isolation.level]": read_committed
```

| Isolation level | Behavior |
| --- | --- |
| `read_uncommitted` | Reads even incomplete or aborted transactional records |
| `read_committed` | Returns only records belonging to committed transactions |

A `read_committed` consumer reads only up to the last stable offset (LSO), which is the boundary before the earliest open transaction in the partition. If there is a long-running open transaction, the consumer may wait even though other records already exist behind it. Therefore, transactions must be short and have appropriate timeouts.

If the input topic is also written by a transactional producer and the application does not want to process data from aborted transactions, the consumer reading input should also use `read_committed`.

## 8. Exactly-once in Spring Kafka

Spring Kafka supports EOS for transactional listener containers. You need to configure the producer factory with a transaction ID prefix, create a `KafkaTransactionManager`, and attach the manager to the listener container. `KafkaTemplate` must use the same producer factory so send operations participate in the active transaction.

### Configuring with Spring Boot

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: ${INSTANCE_ID}-orders-tx-
    consumer:
      group-id: order-projection
      enable-auto-commit: false
      properties:
        "[isolation.level]": read_committed
```

When `spring.kafka.producer.transaction-id-prefix` is set, Spring Boot configures a transactional producer factory and a `KafkaTransactionManager` for the auto-configured setup. The auto-configured listener container uses the transaction manager; the auto-configured `KafkaTemplate` also uses the corresponding producer factory.

With multiple replicas, `INSTANCE_ID` must be provided and distinct across instances; if the environment variable is not set, the application should fail on configuration binding rather than silently sharing a default prefix. Do not use the same fixed prefix for every pod. The Spring Kafka listener container manages offsets; `enable.auto.commit` must be `false`, and the framework sets it to `false` if not declared.

### Configuring the listener container in Java

If creating factories manually, attach `KafkaAwareTransactionManager`:

```java
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

The producer factory must already be configured with a transaction ID prefix. Since Spring Kafka 3.2, use `setKafkaAwareTransactionManager(...)`; the legacy `setTransactionManager(...)` API is deprecated.

### Listener sending output

```java
@Component
public class OrderProjectionListener {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderProjectionListener(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(
            topics = "orders.in",
            groupId = "order-projection",
            containerFactory = "kafkaListenerContainerFactory")
    public void onMessage(ConsumerRecord<String, String> record) {
        String output = "projection:" + record.value();
        kafkaTemplate.send("orders.out", record.key(), output);
    }
}
```

The container starts a transaction before invoking the listener. `KafkaTemplate.send()` participates in the transaction; when the listener finishes, the container sends the input offset into the transaction and commits. If the listener throws an exception, the transaction rolls back and `AfterRollbackProcessor` coordinates retry/recovery.

## 9. EOS V2 and fencing in Spring Kafka

Modern Spring Kafka uses `EOSMode.V2`. V2 uses consumer group metadata in the send-offsets-to-transaction operation, allowing the broker to fence an older producer when a partition is reassigned to another consumer.

EOS V2 requires Kafka broker 2.5 or higher. Since Spring Kafka 3.0, V2 is the only supported mode; older V1/ALPHA/BETA modes are no longer options in modern applications.

In V2, there is no need to create a separate transactional producer per group/topic/partition combination as in the older approach. The producer factory can cache producers, while the transactional ID is constructed from the prefix and a suffix managed by the factory. The prefix still must be unique across concurrently running application instances.

If a producer stays idle longer than the broker's `transactional.id.expiration.ms`, consider setting `maxAge` on `DefaultKafkaProducerFactory` lower than the broker expiration so the factory refreshes the producer before it gets fenced due to expiration.

## 10. Failure scenarios and EOS outcomes

| Scenario | Expected outcome with Kafka transactions |
| --- | --- |
| Producer sends output, then listener throws an exception | Transaction aborts; output is not visible to `read_committed` consumers; input offset is not committed |
| Listener succeeds, transaction commits | Output and input offset take effect together |
| Consumer crashes while transaction is open | Coordinator resolves the incomplete transaction via timeout/recovery; uncommitted output is not exposed to `read_committed` |
| Producer resends batch due to network error within the same producer session | Idempotent producer detects sequence and avoids writing retry duplicates |
| New producer initializes with the same transactional ID | New producer epoch fences the old producer |
| Application resends the same event as a new publish | May create a new record; event ID/idempotency is needed to eliminate business duplicates |
| Database commits, but Kafka transaction aborts | Database does not roll back automatically; inbox/outbox or idempotency is required |

EOS handles the atomicity of Kafka state, not hiding all errors at the application layer. Retries and side effects must be designed around the exact transaction boundaries.

## 11. Exactly-once does not cover databases or external services

Kafka transactions do not automatically create a distributed transaction across Kafka and a relational database, REST API, email provider, or file system.

For example, a listener updates a database and then sends to Kafka:

1. Database commit succeeds.
2. Kafka transaction fails.
3. Kafka input record is read again.
4. Database update may run again.

If the listener sends to Kafka first and then calls the database, the reverse situation can also happen. A Kafka transaction cannot roll back an HTTP request already processed by another service or an email already sent.

Common strategies:

- **Transactional outbox:** store the business update and event in the same database transaction; a separate publisher sends outbox events to Kafka.
- **Inbox/deduplication:** store `eventId` with a unique constraint in the same database transaction so redelivered events do not cause repeated side effects.
- **Idempotent API:** send an idempotency key downstream so the same request does not create multiple results.
- **Saga/compensation:** design compensating actions when a workflow spans multiple independent systems.

For many applications, at-least-once + idempotent business operations are simpler than trying to extend the EOS concept outside Kafka.

## 12. Exactly-once and business-layer idempotency

Idempotency means executing the same event multiple times still produces a business result equivalent to executing it once. Example using an event ID:

```sql
CREATE TABLE processed_event (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
```

Within a database transaction:

```java
@Transactional
public void processOnce(OrderCreatedEvent event) {
    boolean firstDelivery = processedEventRepository
            .insertIfAbsent(event.eventId());

    if (!firstDelivery) {
        return;
    }

    orderRepository.createProjection(event);
}
```

`insertIfAbsent` must be implemented using a unique constraint or an atomic insert/upsert statement. Do not simply do `SELECT` followed by `INSERT`, because two consumers could run concurrently and both see the event as non-existent.

Recording the event marker and applying the business update must be inside the same database transaction. Only afterward should the listener commit the Kafka offset. If a crash occurs after the database commit but before the offset commit, the record is redelivered, but the event ID already exists so the business update is not repeated.

## 13. Transactional ID and broker configuration

Kafka transactions use a transaction coordinator and the internal topic `__transaction_state`. The cluster must configure appropriate replication and min ISR so transaction state is durable.

Some related broker configurations:

| Property | Meaning |
| --- | --- |
| `transaction.state.log.replication.factor` | Replication factor of the transaction state topic |
| `transaction.state.log.min.isr` | Minimum replicas that must be in-sync to accept transaction state writes |
| `transaction.max.timeout.ms` | Maximum transaction timeout limit accepted by the broker |

The producer has `transaction.timeout.ms`; its value must not exceed the broker limit. For a single-broker cluster used for learning, replication factor and min ISR may need to be set to 1, but that configuration does not provide durability equivalent to a production cluster.

When ACLs are enabled, the producer needs permission to use the transactional ID and write to target topics. The consumer needs permission to read the input topic and join the consumer group. `TransactionalIdAuthorizationException` usually requires checking transactional ID permissions; topic/group errors require checking the corresponding permissions.

## 14. Transaction limits and throughput

Transactions add extra round trips with the coordinator and require commit/abort. Overly long transactions can increase latency, hold the last stable offset back, and cause `read_committed` consumers to wait.

Points to control:

- Keep transactions short, including only work that requires atomicity.
- Do not perform slow HTTP/database calls inside a transaction if they can be separated.
- Choose `transaction.timeout.ms` suitable for the highest predictable processing time.
- Monitor transaction commit/abort rate and transaction duration.
- Avoid opening many unnecessary small transactions in a producer-only flow.
- Evaluate throughput/latency before and after enabling transactions.

Do not increase timeouts indefinitely to hide a hanging listener. If business processing takes a long time, consider splitting the work or using an appropriate workflow/outbox.

## 15. When is EOS needed and when is at-least-once enough?

| Use case | Recommended option | Reason |
| --- | --- | --- |
| Consume Kafka, transform, and publish to Kafka; output and offset must be atomic | Kafka transaction + EOS | Both operations commit/abort together |
| Producer retries could write duplicates due to network errors | Idempotent producer | Deduplicates retries from the same producer |
| Consumer only updates a database | At-least-once + inbox/idempotency | Database is not part of the Kafka transaction |
| Send events from a database after updating data | Transactional outbox | Synchronizes business data and events in the database |
| Send emails or call REST APIs | Idempotency key/outbox/compensation | Kafka cannot roll back external side effects |
| Only send multiple Kafka records requiring atomic visibility | Producer transaction | Commits/aborts a group of outputs without necessarily having input offsets |
| Flow does not require atomicity and prioritizes simple latency | At-least-once or at-most-once as required | Reduces transaction overhead and complexity |

Enable EOS only when business requirements demand atomic read-process-write inside Kafka. If a consumer only writes to a database, EOS does not automatically solve the most important problem: synchronizing the database with the offset.

## 16. Testing Exactly-once

Testing EOS needs to verify what downstream consumers see and the input offset state, not just check that the listener was called.

### Successful commit scenario

1. Create input and output topics in the test broker.
2. Configure the producer factory with a unique transaction ID prefix.
3. Attach `KafkaTransactionManager` to the listener container.
4. Send a record to the input topic.
5. Listener sends output using `KafkaTemplate` backed by the same producer factory.
6. A `read_committed` consumer receives exactly one committed output.
7. Verify the input group offset has advanced.

### Rollback scenario

1. Send another record to the input topic.
2. Listener sends output and then throws an exception before the transaction completes.
3. Confirm the `read_committed` consumer does not see the output belonging to the aborted transaction.
4. Confirm the input record is retried according to `AfterRollbackProcessor`.
5. Let the subsequent attempt succeed and confirm output appears only from the committed transaction.

### Producer retry and fencing scenario

- Simulate a record send retry and confirm the idempotent producer does not create duplicates from retries in the same producer session.
- Initialize a new producer with the same transactional ID to verify the old producer is fenced.
- Run multiple application instances with different prefixes to verify there is no transactional ID contention.

### External side effect scenario

- Let the database commit succeed, then simulate an uncommitted Kafka offset.
- Confirm the record is redelivered.
- Confirm the inbox/event ID prevents repeated database updates.

Use Embedded Kafka or a test broker, `CountDownLatch`, `BlockingQueue`, or Awaitility to wait for transactions and offsets with a timeout. Avoid relying solely on short `Thread.sleep` calls to conclude whether a transaction has committed or aborted.

## 17. Common errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Producer retry still creates duplicates | Idempotence disabled or application resends as a new publish | Enable idempotence; use event ID to deduplicate in business logic |
| Output commits, but input offset is not committed | Output and offset are not in the same transaction | Use transactional listener/container or `sendOffsetsToTransaction` |
| Offset commits, but output is missing | Committing two operations independently or wrong transaction boundary | Put output and offset into the same transaction |
| Consumer sees records from aborted transactions | Consumer uses `read_uncommitted` | Set `isolation.level=read_committed` |
| `ProducerFencedException` | Duplicate transactional ID or old producer fenced by a new epoch | Use a unique transactional ID/prefix per logical instance |
| Transaction timeout | Listener takes too long or timeout is inappropriate | Reduce transaction duration and adjust timeout within bounds |
| EOS does not protect the database | Database is outside the Kafka transaction | Use outbox/inbox and idempotency |
| Listener still runs multiple times | Rollback, redelivery, or crash before offset commit | Design an idempotent listener; EOS guarantees Kafka state, not single code invocation |
| `read_committed` is slow | Long-running open transaction prevents LSO from advancing | Find stuck transactions, shorten processing time, and monitor the coordinator |

## 18. Deployment checklist

- [ ] Producer uses idempotence; producer properties are compatible.
- [ ] Read-process-write flows use Kafka transactions.
- [ ] Input offset is included in the same transaction as the output.
- [ ] Transactional ID is stable per logical producer and unique across concurrently running instances.
- [ ] `KafkaTemplate` uses the same `ProducerFactory` as the transaction manager.
- [ ] Listener container is attached to `KafkaAwareTransactionManager`.
- [ ] Consumers needing transactional data use `read_committed`.
- [ ] Listener propagates exceptions to roll back when processing fails.
- [ ] Retry/recovery of transactional listeners uses an appropriate `AfterRollbackProcessor`.
- [ ] Databases and external side effects have outbox/inbox or idempotency.
- [ ] Transaction timeout, broker transaction state log, and ACLs have been verified.
- [ ] Integration tests exist for commit, abort, retry, fencing, and redelivery.

## 19. Conclusion

Exactly-once semantics in Kafka relies on two coordinated mechanisms: an idempotent producer eliminates duplicates from retries by the same producer, while Kafka transactions group output and input offsets into an atomic commit/abort unit. `read_committed` consumers see only committed output. In Spring Kafka, a transactional listener container manages the transaction, sends input offsets into the transaction, and uses `KafkaTemplate` with the same producer factory to send output.

EOS guarantees the Kafka state of a read-process-write flow, does not guarantee the listener runs only once, and does not automatically cover databases or external services. Use transactional IDs/prefixes properly, keep transactions short, configure `read_committed`, design idempotent side effects, and test crash/rollback scenarios. For many business cases, at-least-once combined with inbox/outbox can be simpler and more suitable than trying to extend EOS beyond Kafka.

## References

- [Apache Kafka — Message Delivery Semantics](https://kafka.apache.org/documentation/#semantics)
- [Apache Kafka — Producer Configurations](https://kafka.apache.org/documentation/#producerconfigs)
- [Apache Kafka — Transactions](https://kafka.apache.org/documentation/#transactions)
- [Spring for Apache Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html)
- [Spring for Apache Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
