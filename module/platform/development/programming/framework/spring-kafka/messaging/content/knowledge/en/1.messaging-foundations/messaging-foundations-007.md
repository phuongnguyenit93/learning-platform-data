# Core Guarantees of Kafka

Kafka is designed to transmit and store event streams across a distributed cluster of brokers. When saying Kafka "guarantees" that a message is sent, stored, read, or processed, you must separate distinct properties: record ordering, durability when brokers fail, and delivery semantics when producers or consumers fail mid-flight.

In Spring Kafka applications, these properties are expressed through `KafkaTemplate`, `@KafkaListener`, producer/consumer configuration, offset commits, and transactions. Understanding the exact boundaries of each guarantee helps you design reliable messaging flows without assuming that a single setting eliminates all failures.

## Learning Objectives

After this lesson, you will be able to:

- Explain why Kafka guarantees ordering at the partition level and why a topic has no global order.
- Choose `acks`, replication factor, and `min.insync.replicas` to balance durability against write availability.
- Distinguish at-most-once, at-least-once, and exactly-once; describe how offset commit timing affects each semantic.
- Explain how producer idempotence differs from Kafka transactions and why transactions do not automatically cover databases or HTTP APIs.
- Apply these guarantees when building producers, consumers, and consume-transform-produce flows with Spring Kafka.

## 1. Mental Model to Remember

A Kafka record typically has a key, value, timestamp, and headers. The record is written to a topic partition. Each partition is an ordered log: the broker assigns the record an incrementing offset within that partition.

A topic can have multiple partitions replicated across multiple brokers:

- **Leader replica** handles read/write requests for the partition.
- **Follower replica** replicates data from the leader.
- **ISR (in-sync replicas)** is the set of replicas keeping up with the leader according to Kafka's synchronization criteria.
- **Consumer group** distributes partitions among consumer members. In steady state, a partition is assigned to at most one member within the same group.
- **Consumer offset** records the next position the group will read within a partition.

Three distinct questions must be answered separately:

| Question | Primary Mechanism | Scope |
|---|---|---|
| In what order are records observed? | Partition and offset | A single partition |
| Does a record survive broker failures? | Replication, ISR, and producer acknowledgement | A partition and the broker cluster |
| Can a record be lost or processed twice? | Producer retries, consumer offsets, and transactions | Producer/consumer or pipeline |

Kafka does not automatically create a global order across partitions. Nor does a consumer group automatically guarantee that side effects in external systems occur only once.

## 2. Ordering Guarantee: Only Within a Single Partition

Kafka stores records in each partition in append order. If a consumer reads a partition sequentially, the consumer receives records in ascending offset order. For example, events for a single order can be sent with the same key:

```text
topic: order-events
key: order-42

partition 2:
offset 100 -> OrderCreated
offset 101 -> PaymentAuthorized
offset 102 -> OrderPacked
offset 103 -> OrderShipped
```

To route events for the same entity into the same partition, producers commonly use the entity identifier as the key:

```java
kafkaTemplate.send("order-events", orderId, event);
```

With the default partitioner, the same key normally maps to the same partition as long as partition configuration stays unchanged. Thus, `orderId` is a sensible key when business requirements call for preserving event order per order.

There are several important limitations:

1. Two records in two different partitions have no overall ordering relationship. Identical timestamps do not establish processing order either.
2. If you increase the partition count, the key-to-partition mapping can change. Older records for a key may live in the old partition while newer records go to another partition; evaluate partition scaling carefully when key-based ordering is mandatory.
3. If the application hands off processing to asynchronous tasks or parallel workers after receiving records, side-effect completion order can diverge from the order Kafka delivered.
4. Multiple producers writing the same key are still ordered by the order in which the broker receives and appends records; Kafka does not know the business order the producers intended.

In Spring Kafka, the `concurrency` setting can spawn multiple consumer threads to handle different partitions. Avoid placing records from the same partition into an internal parallel worker queue if business logic requires ordering.

**Design rule:** choose keys based on the unit that needs ordering, such as `orderId`, `accountId`, or `customerId`. Do not choose random keys if related events must be processed sequentially.

## 3. Durability Guarantee: Replication and Acknowledgements

Replication keeps a partition available and intact when a broker fails. With a replication factor of 3, a partition has one leader and up to two followers. However, replication factor alone does not specify how many replicas the producer must wait for before considering a write successful.

Producers control how long to wait via `acks`:

| Value | What the Producer Waits For | Primary Consequence |
|---|---|---|
| `0` | Does not wait for broker acknowledgement | Low latency, producer does not know if the broker received the record; higher risk of data loss |
| `1` | Leader acknowledges after receiving the record | Record can be lost if the leader fails before followers replicate it |
| `all` or `-1` | Replicas currently in the ISR acknowledge | Higher durability; writes can fail if ISR falls below the minimum threshold |

Two settings must be evaluated together:

- `replication.factor` defines the target number of copies of a partition.
- `min.insync.replicas` defines the minimum number of replicas that must remain in the ISR for the broker to accept a write with `acks=all`.

For example, a topic has replication factor 3 and `min.insync.replicas=2`. When the leader and at least one follower remain in the ISR, the broker can accept `acks=all` writes once ISR replicas acknowledge. If only one replica remains in the ISR, the broker rejects writes instead of silently degrading durability guarantees.

This setup creates an intentional trade-off: when the cluster loses too many replicas, the application may temporarily be unable to write. That behavior protects data durability; systems need bounded retries, alerting, and appropriate recovery procedures.

Example producer configuration in Spring Kafka:

```java
Map<String, Object> producerProps = new HashMap<>();

producerProps.put(ProducerConfig.ACKS_CONFIG, "all");
producerProps.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
producerProps.put(ProducerConfig.RETRIES_CONFIG, Integer.MAX_VALUE);
producerProps.put(
    ProducerConfig.MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION,
    5
);

// Pass producerProps into ProducerFactory alongside bootstrap servers
// and serializers matching the application's key/value types.
```

The example above illustrates properties related to acknowledgements and retries. Topic/broker settings must still configure appropriate replication factor and `min.insync.replicas`. Setting `acks=all` on the producer alone cannot replace replication configuration.

Several limitations to remember:

- `acks=all` means waiting for all replicas currently in the ISR, not necessarily every replica declared by the replication factor.
- Acknowledgement confirms the broker accepted the write according to replication settings; it does not mean a consumer has read or processed the record.
- Retention still applies. Records can expire by `retention.ms`/`retention.bytes` or be replaced under log compaction. Replication does not mean data is stored forever.
- Allowing unclean leader election from out-of-sync replicas trades potential loss of unreplicated records for availability. Understand unclean leader election settings thoroughly before changing them.

## 4. Delivery Semantics: At-Most-Once and At-Least-Once

Consumers read records by offset, yet processing a record and committing its offset are two separate actions. Failures can happen between those two actions. Their execution order determines whether a record can be lost or processed repeatedly.

### At-Most-Once

The consumer commits the offset before finishing record processing.

```text
read record -> commit offset -> business processing
                         |
                         +-- process fails here: record may be skipped
```

This avoids reprocessing committed records, but risks losing processing if the process crashes after committing and before side effects complete. Suitable only when missing occasional records is acceptable.

### At-Least-Once

The consumer processes successfully first, and commits the offset afterward.

```text
read record -> business processing -> commit offset
                     |
                     +-- failure before commit: record will be re-read
```

This prioritizes not skipping records, though duplicate processing can occur. For instance, a service writes a payment to the database successfully and crashes before committing the offset. When the consumer restarts, the record is read again and the write may run a second time.

At-least-once is usually the practical choice for business consumers, provided handlers are idempotent.

### Why Must Offsets Be Committed at the Right Time?

A consumer group's committed offset is the next position to read in a partition. Suppose a consumer successfully processes the record at offset 25; the next position to commit is 26.

Committing too early risks losing processing. Committing too late or crashing before committing can cause redelivery. Disabling auto-commit and letting the listener container manage acknowledgements usually ties commits more clearly to processing outcomes.

Example listener processing first and acknowledging manually afterward:

```java
@KafkaListener(topics = "order-events", groupId = "billing")
public void handle(
        OrderCreated event,
        Acknowledgment acknowledgment) {

    // This method must be idempotent, e.g. using eventId with a unique constraint.
    billingService.applyIfNotProcessed(event.eventId(), event);

    // Acknowledge only after side effects have completed.
    acknowledgment.acknowledge();
}
```

The listener above requires a container configured with the corresponding acknowledgement mode, such as `MANUAL`, and the consumer must have auto-commit disabled. Acknowledging after writing to the database still leaves a failure window: the database may have committed while the process crashes before the Kafka offset is committed. A unique constraint or inbox table keyed by `eventId` prevents a redelivery from causing a second side effect.

### Idempotent Consumers

An idempotent operation can be executed multiple times with the same input while yielding the same final business outcome as executing it once.

Common implementation patterns:

- Give every event a unique `eventId`; the consumer stores processed `eventId` values with a unique constraint.
- Conditional state transitions, e.g. only transitioning an order from `PAID` to `PACKED` if its current status is `PAID`.
- Use upserts or business keys so redelivery does not create duplicate rows.
- Record the processed marker and update business data within the same database transaction.

Never check if an event exists and then write data in two separate transactions: two consumers or concurrent executions can both pass the check at the same time. A database unique constraint is the reliable final safeguard.

## 5. Producer Idempotence and Exactly-Once

These two features are related yet solve different problems.

### Producer Idempotence

When a producer sends a record and fails to receive an acknowledgement due to a timeout, the producer does not know whether the broker already wrote the record. If it retries normally, the broker might write two copies.

Producer idempotence uses a producer ID and sequence numbers so the broker recognizes retries from the same producer session, avoiding duplicate writes caused by producer-layer retries. In modern Kafka versions, producer idempotence is supported directly; it should still be explicitly configured when reliability is critical.

Producer idempotence **does not** eliminate duplicates caused by the application explicitly calling `send()` twice, by two independent producers emitting the same event, or by a consumer reprocessing a record.

### Kafka Transactions

Kafka transactions allow writing multiple records, even across multiple partitions/topics, as a single atomic unit. In a consume-transform-produce flow, a transaction can also include the input record's offset in the same transaction as the output records.

A successful flow can be understood as follows:

```text
consume input at offset N
        |
transform
        |
begin transaction
        |
produce output record(s)
        |
send next offset N+1 to transaction
        |
commit transaction
        |
output and offset are committed together
```

If the transaction aborts, output belonging to that transaction is invisible to consumers configured with `read_committed`, and the input offset is not committed in the transaction. The consumer can re-read the input to retry the entire unit of work.

Achieving exactly-once semantics for a Kafka-to-Kafka pipeline requires coordinating:

1. A transactional producer configured with an appropriate transactional ID.
2. Sending input offsets into the same transaction as the output.
3. Output consumers configured with `isolation.level=read_committed` to ignore records from aborted or uncommitted transactions.
4. Application handling of transaction errors and retries via an appropriate mechanism.

### Exactly-Once Does Not Mean Every Side Effect Runs Once

A Kafka transaction can atomically combine Kafka record writes and Kafka offset commits. It does not automatically bring an SQL statement, an email send, or an HTTP request into the same distributed transaction.

For example, suppose a listener calls an external payment service and then the Kafka transaction aborts. When the input is re-read, the payment service may receive the same request again. To protect business logic, external APIs need idempotency keys or the application needs an integration pattern such as inbox/outbox, CDC, or a saga.

Therefore, whenever speaking of exactly-once, always specify the exact scope: exactly-once within the Kafka pipeline, or end-to-end business effects across the whole system.

## 6. Applying Transactions in Spring Kafka

Spring Kafka supports transactions via a transactional producer factory, `KafkaTransactionManager`, and listener containers. The producer factory requires a transaction ID prefix; each concurrently running application instance must have a sufficiently unique prefix to prevent producers from fencing each other.

Example initializing a transaction manager when the producer factory is configured as transactional:

```java
@Bean
KafkaTransactionManager<String, OrderEvent> kafkaTransactionManager(
        ProducerFactory<String, OrderEvent> producerFactory) {

    return new KafkaTransactionManager<>(producerFactory);
}
```

For an operation that only emits multiple Kafka records, `KafkaTemplate.executeInTransaction(...)` groups the sends into a single transaction:

```java
kafkaTemplate.executeInTransaction(operations -> {
    operations.send("order-events", orderId, createdEvent);
    operations.send("audit-events", orderId, auditEvent);
    return null;
});
```

For consume-transform-produce flows, configure the listener container to participate in the Kafka transaction so input record offsets are sent into the transaction alongside output records. Simply opening a transaction around `send()` without including the input offset does not provide end-to-end pipeline exactly-once.

Consumers reading transactional output topics must use:

```java
consumerProps.put(
    ConsumerConfig.ISOLATION_LEVEL_CONFIG,
    "read_committed"
);
```

Operational notes for transactions:

- The transactional ID prefix must remain stable across a producer's lifecycle yet not collide between concurrently active instances.
- Transactions must finish within `transaction.timeout.ms`; slow external calls can cause transactions to time out.
- Transactions add coordination overhead and can affect throughput. Enable them only when atomicity between Kafka outputs and offsets is truly required.
- Databases or external services still require idempotency or a separate coordination pattern.

## 7. Retries, Dead-Lettering, and Impact on Guarantees

Retries help recover from transient failures such as timeouts or temporarily unavailable dependencies. However, retries increase the likelihood of an event executing multiple times; handlers should be idempotent even when the producer has idempotence enabled.

A dead-letter topic (DLT) routes records that remain unprocessable after configured attempts to a separate place for investigation or reprocessing. A DLT does not prove that a record was processed successfully in business terms. Monitor DLT record counts, oldest record age, failure causes, and replay procedures.

Retry strategy also affects ordering:

- Blocking retries on the same processing thread can preserve partition ordering while stalling subsequent records.
- Asynchronous retries or routing failed records to another topic can allow subsequent records to finish before the failing record.
- Replaying a DLT can introduce older events after newer events; validate business version/state before applying them.

If ordering is a business requirement, design retries and replays around the same key/partition unit and define how late-arriving events are handled.

## 8. Choosing Guarantees Based on Requirements

| Requirement | Common Design Approach | Trade-Off to Accept |
|---|---|---|
| Do not need every record, prioritize latency | Consider `acks=0` or `acks=1` | Higher risk of data loss |
| Need higher durability across broker failures | Proper replication factor, `acks=all`, `min.insync.replicas` | Writes may be rejected when ISR is too low |
| Cannot lose consumer processing | Process first, then commit offset; idempotent handler | Redelivery and duplicate processing can occur |
| Need ordering per entity | Use business key for partitioning; process sequentially per partition | No global order; partition scaling requires care |
| Consume-transform-produce must be atomic in Kafka | Kafka transaction, include offsets in transaction, `read_committed` consumer | Covers only Kafka data and offsets |
| Database side effects must not duplicate | Inbox/idempotency key and database transaction | Must be designed at the business layer |

No single "exactly once" flag simultaneously covers every queue, database, and API. Define what is allowed to be lost, what is allowed to duplicate, at what level ordering is needed, and where transaction boundaries lie.

## 9. Failure Scenarios to Anticipate

| Scenario | Possible Outcome | Risk Mitigation |
|---|---|---|
| Producer times out after broker already wrote the record | Retries can create duplicate records without idempotence | Enable producer idempotence; handle duplicate events in consumers |
| Leader fails before followers replicate an `acks=1` record | Record may be lost when a new leader is elected | Use `acks=all` and suitable `min.insync.replicas` |
| Consumer fails before finishing processing and before committing | Record is redelivered | Bounded retries; idempotent handler |
| Consumer wrote to database but failed before committing offset | Record is redelivered, side effects may duplicate | Inbox/unique constraint and database transaction |
| Consumer committed offset before writing to database | Record may be skipped after process crash | Commit only after processing succeeds |
| Kafka transaction aborts | Transaction outputs are hidden from `read_committed` consumers; input can be re-read | Retry the whole transaction unit; external side effects must be idempotent |
| ISR drops below `min.insync.replicas` | Broker rejects writes with `acks=all` | Restore replicas, inspect broker/network, and monitor ISR |

Turn these scenarios into test cases. For example: make a listener throw an exception to verify offsets do not advance; resend the same `eventId` to confirm the database does not create a second business row; verify a `read_committed` consumer does not see output from an aborted transaction.

## 10. Testing and Observability

Unit tests can verify idempotent logic and how handlers react to failures. Integration tests with real Kafka or Testcontainers are better suited for verifying partitions, offsets, retries, transactions, and consumer group behavior.

Valuable checks include:

- Sending multiple events with the same key and verifying they land in the same partition with ascending offsets.
- Sending an event with the same `eventId` multiple times and confirming side effects are recorded only once.
- Failing a handler before acknowledgement, recovering, and verifying the record is redelivered.
- Aborting a transaction with output and verifying a `read_committed` consumer does not read that output.
- Testing behavior during consumer group rebalances and abrupt instance shutdowns.

In production, monitor producer send failures/retries, request latency, ISR and under-replicated partitions, consumer lag, rebalance counts, retry/DLT rates, and age of unprocessed records. Low consumer lag does not prove business side effects succeeded; also observe outcomes in target systems.

## Design Checklist

Before shipping a Spring Kafka flow, be sure you can answer these questions:

- [ ] Which key defines the business ordering that must be preserved?
- [ ] Does the topic have a replication factor and `min.insync.replicas` matching durability needs?
- [ ] Does the producer use appropriate acknowledgements and idempotence?
- [ ] After which point in the processing lifecycle are offsets committed?
- [ ] Can the consumer tolerate receiving the same event multiple times?
- [ ] If exactly-once is required, are offsets and outputs inside the same Kafka transaction?
- [ ] Do non-Kafka side effects have idempotency keys, inbox/outbox, or an equivalent mechanism?
- [ ] How might retries, DLT, replay, and rebalances affect ordering?
- [ ] Have critical failure scenarios been tested and instrumented with metrics/alerts?

## Conclusion

Kafka provides per-partition ordering, replication for durability, and offset/transaction mechanisms to govern delivery. Spring Kafka applications achieve reliable behavior when keys are chosen carefully, producers and brokers are configured properly, offsets are committed at the right time, and business processing tolerates retries. Exactly-once has its clearest meaning when Kafka transaction boundaries are explicitly defined and idempotency is added for every side effect outside those boundaries.

