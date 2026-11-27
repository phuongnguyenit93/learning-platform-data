# isolation.level and Reading Committed Data

A Kafka producer can send multiple records within a single transaction. A consumer needs to decide whether it may see records from incomplete transactions or only committed data. The Kafka consumer `isolation.level` property controls this behavior.

The two key values are `read_uncommitted` and `read_committed`. `read_uncommitted` allows the consumer to read transactional records before the transaction ends, including records belonging to transactions that are later aborted. `read_committed` returns only non-transactional records and records from committed transactions; records from open or aborted transactions are not returned to the application.

In the Spring Cloud Stream Kafka binder, `isolation.level` can be set per consumer binding. If a service must only process events confirmed as committed by the producer, configure `read_committed` and understand the impact of Last Stable Offset (LSO), long-running transactions, consumer lag, and data wait times.

## 1. Transactional records and transaction states

Kafka supports producer transactions to write multiple records atomically within Kafka. A producer starts a transaction, sends records to one or more partitions, and then commits or aborts the transaction.

A transaction generally passes through these states:

1. **Begin:** the producer opens a transaction and sends records.
2. **In progress:** records are written to the partition log, but the transaction has no final outcome yet.
3. **Commit:** the transaction coordinator records the transaction as successful; its records become committed data.
4. **Abort:** the transaction coordinator records the transaction as failed; its records are marked aborted and are not returned to `read_committed` consumers.

Transactional records may already reside in the log before the transaction commits. The fact that a record is written to the log does not mean every consumer is permitted to see it. `isolation.level` determines whether a consumer reads across transaction boundaries.

Kafka also writes internal control markers to represent transaction outcomes. These markers serve the broker and consumer protocol; applications do not receive them as normal business payloads.

## 2. The two values of isolation.level

Kafka consumers support two values:

| Value | Behavior | When to use |
| --- | --- | --- |
| `read_uncommitted` | Reads non-transactional records as well as uncommitted or eventually aborted transactional records | Need maximum data availability and the application can tolerate processing records that might abort |
| `read_committed` | Returns only non-transactional records and records from committed transactions | Must avoid processing data from incomplete or aborted transactions |

The Kafka consumer default is `read_uncommitted`. If an application must read transactional data consistently, `read_committed` must be configured explicitly; do not assume a consumer switches to this mode automatically just because the producer enables transactions.

`isolation.level` is a consumer property. It does not enable transactions on a producer, does not turn a standard producer into a transactional one, and does not turn a database transaction into a Kafka transaction.

## 3. read_uncommitted: seeing records before the transaction finishes

With `read_uncommitted`, the consumer reads records as soon as they can be fetched from the log, without waiting for the containing transaction to commit.

Example where a producer sends two events in the same transaction:

```text
beginTransaction()
  send(OrderCreated)
  send(InventoryReserved)
commitTransaction()
```

A `read_uncommitted` consumer can receive `OrderCreated` and `InventoryReserved` before the producer calls `commitTransaction()`. If the producer later aborts, the consumer may already have processed both records. Kafka cannot undo side effects the application has already performed.

This means `read_uncommitted` can observe an intermediate transactional state. If a producer writes multiple records to represent a single logical change, the consumer may see a partial set of records before the transaction ends.

### Example of an aborted transaction

```text
Producer                         Consumer read_uncommitted
--------                         -------------------------
beginTransaction()
send(OrderCreated)       ----->  receives OrderCreated
send(InventoryReserved)  ----->  receives InventoryReserved
abortTransaction()
```

The consumer received the records even though the transaction ended in an abort. For business consumers unable to roll back side effects, this is usually undesirable behavior.

## 4. read_committed: reading only committed data

With `read_committed`, a Kafka consumer returns only:

- Non-transactional records.
- Records belonging to committed transactions.

The consumer does not return records from open transactions or records from aborted transactions. If the producer commits the transaction, its records become readable in log order. If the producer aborts, they are hidden from `read_committed` consumers.

```text
Producer                         Consumer read_committed
--------                         -----------------------
beginTransaction()
send(OrderCreated)       ----->  does not receive record yet
send(InventoryReserved)  ----->  does not receive record yet
commitTransaction()
                               receives OrderCreated
                               receives InventoryReserved
```

If the transaction aborts, those two records will not be returned to the `read_committed` consumer.

`read_committed` helps consumers avoid executing side effects based on uncommitted transactional records. This is an essential requirement when building transactional consume-process-produce Kafka pipelines.

## 5. Last Stable Offset (LSO) and the readable data boundary

The core difference between the two isolation levels lies in the offset boundary up to which a consumer can read.

- The High Watermark (HW) marks the boundary of data sufficiently replicated according to partition conditions and readable under standard semantics.
- The Last Stable Offset (LSO) is the stability boundary for transactions and is treated as an exclusive bound. With `read_committed`, a consumer only receives records with offsets less than the partition's LSO.

The LSO is determined by the earliest unfinished transaction in the partition. If the first open transaction has a record at offset 101, the LSO stops at 101; a `read_committed` consumer reads records with offsets less than 101. Records at offset 101 and beyond may already be written and replicated, yet still withheld from the consumer.

Example partition log:

```text
Offset:  100   101   102   103   104   105   106
Record:   A    Tx-1  Tx-1    B     C    Tx-2   D
State:  plain  open  open   plain plain  open plain
```

While `Tx-1` has not finished, the LSO stops before that transaction. A `read_committed` consumer can read records prior to the boundary, but must wait for the transaction to finish before advancing to subsequent records. When `Tx-1` commits or aborts, the LSO can advance unless another open transaction continues blocking it.

This is why a `read_committed` consumer can sometimes appear slow even though the broker has already received new records. Those records may already exist in the log, but are not yet inside the stable region the consumer is allowed to read.

## 6. Long-running transactions can stall consumers

A transaction kept open too long can block the LSO and increase latency for `read_committed` consumers on the affected partition.

Common causes:

- The producer starts a transaction and then waits too long on an external API or database before committing.
- A processing branch hangs and neither commits nor aborts the transaction.
- The producer crashes before closing the transaction while the broker has not yet completed timeout or fencing handling.
- The transaction encompasses too much work or too many records.

Example:

```text
Partition 2:
  offset 40: CustomerUpdated (non-transactional)
  offset 41: Tx-77 / OrderCreated (transaction open)
  offset 42: CustomerBalanceChanged (non-transactional)
  offset 43: NotificationRequested (non-transactional)
```

A `read_committed` consumer can read the record at offset 40, but must wait for the outcome of `Tx-77` before receiving subsequent records. The non-transactional records behind it are also blocked by the LSO boundary, even though they do not belong to the transaction themselves.

Therefore, transactions should be short and limited to Kafka operations requiring atomicity. Avoid keeping a Kafka transaction open while calling external systems or waiting on user input.

## 7. Offsets can have gaps

`read_committed` consumers do not necessarily observe consecutive offsets. Records from aborted transactions still occupy offsets in the log while being hidden from the application. Control records also occupy positions in the log that the application does not receive as regular payloads.

Example:

```text
Offset 20: OrderCreated             (committed, visible)
Offset 21: PaymentAttempted         (aborted, hidden)
Offset 22: PaymentReservation       (aborted, hidden)
Offset 23: InventoryReserved        (committed, visible)
```

A `read_committed` consumer may receive offset 20 followed by offset 23. This is not message loss or a delivery bug; offsets 21 and 22 are hidden because the transaction aborted.

Do not write logic assuming the next offset always equals the current offset plus one. An offset is a position in the log, not a contiguous sequence number of records seen by a consumer.

## 8. Configuring isolation.level in the Spring Cloud Stream Kafka binder

With the Spring Cloud Stream Kafka binder, you can set Kafka consumer properties at the binding level. For example, if input binding `processOrders-in-0` must only read committed data:

```yaml
spring:
  cloud:
    function:
      definition: processOrders
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.events
          group: order-service
          content-type: application/json
      kafka:
        bindings:
          processOrders-in-0:
            consumer:
              configuration:
                "isolation.level": read_committed
```

In the example, `configuration` passes Kafka consumer properties to the consumer created by the binder. The Kafka property name is `isolation.level`, using a dot. Placing it in the binding-specific consumer configuration limits its scope to this input binding.

If you want to apply it to all consumers managed by the Kafka binder, you can configure it at the binder scope appropriate for your version. However, binding-specific configuration makes it easy to see which flows require reading committed data.

Do not confuse this property with Spring Boot Kafka auto-configuration's `spring.kafka.consumer.properties.isolation.level`. When an application uses the Spring Cloud Stream binder, the binder creates and configures its own consumers; use the Kafka binder namespace supported by your version's documentation rather than assuming `KafkaProperties` from another `KafkaListenerContainerFactory` will automatically apply.

## 9. Producer transaction configuration does not replace isolation.level

Producer transactions and consumer isolation are two separate configuration concerns:

| Component | Responsibility | Example config/concept |
| --- | --- | --- |
| Producer transaction | Write a group of records and commit or abort them together | Transactional producer, `transactional.id`, transaction manager, or Kafka binder transaction support |
| Consumer isolation | Decide whether the consumer reads uncommitted/aborted transactional records | `isolation.level=read_committed` |
| Consumer group offset | Store the group's read position | Offset commit, or sending offsets into the same Kafka transaction in consume-process-produce |

Enabling producer transactions alone does not make consumers automatically use `read_committed`. A consumer keeping the default `read_uncommitted` can still read records before a transaction finishes. Conversely, setting `read_committed` on a consumer does not create transactions for producers; it only filters data according to transaction state recorded by the broker.

In a pipeline with a transactional producer where downstream consumers must only process committed results, configure consumer isolation explicitly. If the pipeline also needs to guarantee atomic commits of input offsets and output records, use the appropriate consume-transform-produce transaction mechanism of Kafka/Spring Kafka or the binder; `read_committed` alone does not guarantee that.

## 10. Producer commit and abort example

A Kafka producer configured as transactional can send multiple records in the same transaction. The example below illustrates Spring Kafka's `KafkaTemplate` API; it requires a transaction-capable `ProducerFactory` and a configured transactional ID prefix in the application:

```java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventProducer {

    private final KafkaTemplate<String, Object> kafkaTemplate;

    public OrderEventProducer(KafkaTemplate<String, Object> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publishOrder(OrderCreated order, InventoryReserved inventory) {
        kafkaTemplate.executeInTransaction(operations -> {
            operations.send("orders.created", order.orderId(), order);
            operations.send("inventory.reserved", order.orderId(), inventory);
            return null;
        });
    }
}
```

When the callback finishes normally, the transaction commits. If the callback throws an exception, the transaction aborts according to `executeInTransaction` semantics. The snippet only illustrates transactions within Kafka; it does not cover a JPA transaction on a relational database.

Downstream consumers need `read_committed` to avoid processing `OrderCreated` or `InventoryReserved` when the transaction is uncommitted or aborted.

## 11. Example verifying the two isolation levels

You can verify the behavior via an integration test with real Kafka or Testcontainers:

1. Create a test topic.
2. Create a transactional producer.
3. Open a transaction and send a record.
4. Before committing, use a `read_uncommitted` consumer to verify the record can be read.
5. Use a `read_committed` consumer to verify the record is not returned yet.
6. Commit the transaction and verify the `read_committed` consumer receives the record.
7. Repeat with an aborted transaction; the `read_committed` consumer does not receive the aborted record.

In the abort test, `read_uncommitted` may have already read the record before the abort. Even if the test starts the consumer only after the abort completes, the record can still be read under `read_uncommitted` isolation because the log retains aborted records and the consumer does not filter them out.

Pseudo-code inspecting consumer config:

```java
Map<String, Object> consumerProps = new HashMap<>();
consumerProps.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
consumerProps.put(ConsumerConfig.GROUP_ID_CONFIG, "isolation-test");
consumerProps.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class);
consumerProps.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class);
consumerProps.put(ConsumerConfig.ISOLATION_LEVEL_CONFIG, "read_committed");
```

This is direct Kafka client configuration to illustrate the property. When testing the Spring Cloud Stream binder, set the same property under binding-specific `consumer.configuration` as in the earlier example and run the actual binder.

## 12. Impact on consumer lag and system observability

A `read_committed` consumer can exhibit higher observed latency than a `read_uncommitted` consumer because it must wait for transactions to finish. When measuring lag, distinguish between:

- The position the consumer has processed/committed.
- The partition's High Watermark.
- The Last Stable Offset that `read_committed` consumers can read up to.

Some dashboards compute lag based on the high watermark or end offset, whereas `read_committed` consumers only read up to the LSO. As a result, displayed lag may include records currently blocked by an open transaction. Understand how your exporter and monitoring tools compute lag before concluding that a consumer is processing slowly.

Metrics to observe:

- Consumer lag per group and partition.
- LSO compared to high watermark, if exposed by broker/exporter tooling.
- Producer transaction duration.
- Number of open or aborted transactions.
- Time from producer send to `read_committed` consumer receipt.
- Producer timeouts, fencing events, or transaction aborts.
- Consumer rebalances and processing latency.

If consumer lag grows while CPU and processing time remain low, investigate long-running transactions or the transaction coordinator before scaling consumer concurrency.

## 13. Isolation level is not a system-wide exactly-once guarantee

`read_committed` keeps consumers from seeing records belonging to uncommitted or aborted Kafka transactions. It does not guarantee:

- Atomic commit or rollback across a database and Kafka.
- Exactly-once processing by a consumer if it crashes after a side effect but before committing its offset.
- Exactly-once invocation of HTTP APIs or external systems.
- A shared transaction across two topics or two independent brokers without an appropriate coordination mechanism.

To build a reliable pipeline, combine Kafka transactions with idempotent consumers, event IDs, retry/DLQ, outbox, or appropriate state persistence. If the consumer writes to a database, consider an inbox/deduplication table or a transactional outbox for downstream publishing.

## 14. When should you use read_committed?

Choose `read_committed` when:

- The upstream producer uses Kafka transactions to publish a group of records atomically.
- The consumer must not perform side effects based on records that might be aborted.
- A consume-process-produce pipeline must read committed transactional inputs.
- Downstream reports or processing must reflect final transaction outcomes.

`read_uncommitted` may be suitable when:

- The topic is non-transactional and latency/throughput takes priority over transaction-state filtering.
- The consumer uses only transient data or can compensate when an upstream transaction aborts.
- The application intentionally observes log data under semantics that do not wait for transaction commits.

For critical business data, `read_committed` is generally the safer choice when upstream uses transactions. However, evaluate latency from open transactions and do not enable it blindly if producers do not use transactions and the application has no such requirement.

## 15. Common issues

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Consumer sees records before producer commits | Consumer is using `read_uncommitted` | Set `isolation.level=read_committed` on the appropriate input binding. |
| Consumer does not see records even though broker wrote them | Transaction not yet committed or LSO has not passed the offset | Check transaction state, producer timeouts, and LSO. |
| Consumer does not see records from an aborted transaction | Expected `read_committed` behavior | For investigation, use producer logs/metrics or a test `read_uncommitted` consumer; do not feed aborted data into business logic. |
| Consumer offsets have gaps | Aborted records/control markers are hidden from the application | Do not assume contiguous offsets; use event IDs and treat offsets as log positions. |
| Lag rises even though consumer processes quickly | LSO is blocked by an open transaction or metric measures against HW | Check transaction duration and how the exporter calculates lag. |
| Producer transactions enabled but consumer still sees uncommitted data | Consumer kept default `read_uncommitted` | Configure consumer isolation explicitly; producer transactions do not change consumers automatically. |
| `spring.kafka.consumer.properties.isolation.level` has no effect | Binder creates its own consumer instead of using expected auto-config consumer | Use the Kafka binder namespace `bindings.<binding>.consumer.configuration`. |
| Increasing concurrency does not reduce lag | Partition is blocked by LSO or downstream is not the bottleneck | Check transaction state, partition assignment, and lag source before scaling. |

## 16. Deployment checklist

Before deploying a consumer reading transactional data to production:

1. Determine whether upstream producers use Kafka transactions.
2. Determine whether the consumer must exclude uncommitted/aborted records.
3. Configure `isolation.level=read_committed` on the exact binding.
4. Verify the property is actually passed to the binder's Kafka consumer.
5. Test both transaction commit and abort cases.
6. Verify the consumer does not assume contiguous offsets.
7. Monitor LSO, high watermark, transaction duration, and consumer lag.
8. Set reasonable producer timeouts and transaction duration limits.
9. Design idempotency for consumer side effects.
10. Test crashes, rebalances, and retries in the consume-process-produce pipeline.

## References

- [Apache Kafka — Consumer Configs: `isolation.level`](https://kafka.apache.org/documentation/#consumerconfigs_isolation.level)
- [Apache Kafka — Design: Message Delivery Semantics and Transactions](https://kafka.apache.org/documentation/#semantics)
- [Spring Cloud Stream — Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/index.html)
- [Spring for Apache Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)

Cross-check the documentation for your specific Kafka broker, Kafka client, and Spring Cloud Stream Kafka binder versions. Binder property names, transaction configurations, and LSO metrics may vary by version and operational tooling.

## Conclusion

`isolation.level` determines whether a Kafka consumer sees uncommitted or aborted transactional records. `read_uncommitted` may return records that are ultimately aborted; `read_committed` returns only non-transactional records and records from committed transactions. `read_committed` consumers read up to the Last Stable Offset, so long-open transactions can block subsequent records and increase observed latency. In the Spring Cloud Stream Kafka binder, configure this property on consumer bindings, test both commit and abort scenarios, and combine it with idempotency and retry strategies to build reliable pipelines.
