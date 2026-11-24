# Offsets and outputs in the same transaction

In Spring Kafka, a common processing flow reads data from an input topic, transforms or validates business logic, and publishes the result to an output topic. To let the consumer resume from the right position upon restart, the application must also **commit the offset** of processed records. If outputs and offsets are committed as two independent operations, a process crash in between can duplicate outputs or skip input records.

**Kafka transactions** allow placing output records and consumer group offsets into **the same Kafka transaction**. When the transaction commits, outputs and consumption progress are confirmed together; on abort, offsets are not committed and outputs from aborted transactions are not returned to consumers with `isolation.level=read_committed`. Spring Kafka can coordinate this using `KafkaTransactionManager`, `KafkaTemplate`, and a transactional listener container.

This is the foundation of **exactly-once semantics (EOS) for Kafka → processing → Kafka flows**. It does not mean the listener method runs only once. After a crash or abort, the same input can be reprocessed; what matters is that Kafka results from aborted transactions are not treated as committed outputs. Side effects outside Kafka, such as databases and HTTP calls, still require idempotency or a dedicated architecture.

## 1. Two outcomes of a record must be confirmed together

Suppose consumer group `order-processor` reads a record from `orders`, partition 0, offset 41. The listener builds `OrderValidated` and sends it to `validated-orders`.

Once offset 41 is processed, the next committed offset is normally **42**—the *next position to read*, not the last processed position. Two actions must complete:

1. Publish output `OrderValidated` to topic `validated-orders`.
2. Commit offset `orders-0 → 42` for group `order-processor`.

```text
Kafka input: orders-0, offset=41
                |
                v
         Spring @KafkaListener
                |
                v
      Process / create output record
                |
        +-------+-------+
        |               |
        v               v
 validated-orders   Group offset: 42
        |               |
        +-------+-------+
                |
                v
         Kafka transaction
        COMMIT or ABORT
```

The goal is to prevent states where *output committed while offset did not*, or *offset committed while the corresponding output did not*, caused by executing two actions as separate commits.

## 2. The problem with sending outputs and committing offsets independently

Without transactions, a `send()` first then `commitSync()` flow can suffer:

```text
poll() input offset 41
        |
        v
publish output succeeds
        |
        X process crashes
        |
offset 42 not committed yet
```

After restart, the consumer group can still re-read offset 41, and the listener creates the output again. **Output is duplicated.** Producer idempotence prevents certain duplicates from producer retries, yet does not stop the application from publishing the same business event a second time after the consumer re-reads the input.

Reversing the order to commit the offset first:

```text
poll() input offset 41
        |
        v
commit offset 42
        |
        X process crashes
        |
output not published yet
```

The group has advanced past the input record while no output exists: risking **lost processing results**. Therefore, the implementation needs a shared atomicity boundary rather than trying to pick a "less risky" commit order.

## 3. How does sendOffsetsToTransaction work?

Kafka's producer exposes `sendOffsetsToTransaction(...)` to add a consumer group's committed offsets into the producer's transaction. At the Kafka client level, the flow can be described as:

```text
producer.initTransactions()  // initialize transactional producer

producer.beginTransaction()

producer.send(outputRecordA)
producer.send(outputRecordB)

producer.sendOffsetsToTransaction(
    offsetsToCommit,
    consumer.groupMetadata()
)

producer.commitTransaction()
```

`offsetsToCommit` is a map from `TopicPartition` to `OffsetAndMetadata`. For example, `orders-0 → 42` and `orders-1 → 16`. The group metadata parameter lets Kafka associate the offset commit request with the proper consumer group membership.

In **EOS V2**, Kafka uses group metadata to increase safety during membership or partition assignment changes. Modern Spring Kafka uses this mechanism in transactional listener containers. For normal applications, **do not call `sendOffsetsToTransaction` manually inside `@KafkaListener`**: the container adds offsets into the transaction when the Kafka transaction manager is properly configured.

If the transaction aborts, output records in that transaction are hidden from `read_committed` consumers and offsets sent in the transaction do not become committed offsets of the group.

## 4. What steps does the container perform?

With a Kafka transaction manager attached to the listener container, the logical execution flow is:

```text
Consumer poll()
     |
     v
Listener container begins Kafka transaction
     |
     v
@KafkaListener processes input
     |
     v
KafkaTemplate.send(output) joins transaction
     |
     v
Listener finishes successfully
     |
     v
Container sends processed offsets into transaction
     |
     v
Producer commitTransaction()
     |
     v
Outputs and committed offsets take effect together
```

If the listener throws an exception, the transaction must be aborted according to the container's error-handling mechanism. If the transaction commit fails, the container must also handle the corresponding exception; never assume offsets advanced just because `send()` returned.

Transaction boundaries can differ between record listeners and batch listeners. **Do not assume one `poll()` always equals one transaction** across all modes; understand listener types, acknowledgment semantics, and the Spring Kafka version in use.

## 5. Spring Boot configuration

Example using String keys/values to focus on Kafka transactions:

```yaml
spring:
  kafka:
    bootstrap-servers: kafka:9092
    producer:
      transaction-id-prefix: "order-tx-instance-a-"
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all
      properties:
        "[enable.idempotence]": true
    consumer:
      group-id: order-processor
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      properties:
        "[isolation.level]": read_committed
```

| Configuration | Meaning |
|---|---|
| `transaction-id-prefix` | Lets the producer factory create transactional producers with `transactional.id` built from prefix and suffix. |
| `acks=all` | Requires acknowledgments per replication settings; does not replace transaction atomicity. |
| `enable.idempotence=true` | Enables an idempotent producer, useful for transactional producers; does not commit offsets with outputs by itself. |
| `enable-auto-commit=false` | Prevents the Kafka consumer from auto-committing offsets outside the Spring container's transaction. |
| `isolation.level=read_committed` | Returns only committed transactional records to the consumer. |

In the example, `order-tx-instance-a-` represents **one instance**. When running multiple pods, prefixes must differ across concurrently active instances. You can obtain the pod name via the Kubernetes Downward API and pass it through configuration environment variables.

Spring Boot can auto-configure `KafkaTransactionManager` when producer transaction ID prefix is set. When an application manually creates `ProducerFactory`, `KafkaTemplate`, or listener factories, verify they participate in the right transaction manager; the mere presence of a transaction manager bean does not guarantee every listener uses it.

## 6. Attaching KafkaTransactionManager to the listener container

Java example configuring a listener container. `setKafkaAwareTransactionManager(...)` fits Spring Kafka 3.2+; in earlier versions, check the corresponding `setTransactionManager(...)` API.

```java
@Configuration
public class KafkaOrderConfiguration {

    @Bean
    KafkaTransactionManager<String, String> kafkaTransactionManager(
            ProducerFactory<String, String> producerFactory) {
        return new KafkaTransactionManager<>(producerFactory);
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, String>
            orderListenerFactory(
                    ConsumerFactory<String, String> consumerFactory,
                    KafkaTransactionManager<String, String> kafkaTransactionManager) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, String>();
        factory.setConsumerFactory(consumerFactory);

        factory.getContainerProperties()
                .setKafkaAwareTransactionManager(kafkaTransactionManager);

        return factory;
    }
}
```

Key imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.transaction.KafkaTransactionManager;
```

The snippet assumes `ProducerFactory<String, String>` has a valid transaction ID prefix configured. If Boot already created a transaction manager, do not create a duplicate bean with the same role; inject the existing manager instead. In projects with multiple `KafkaTransactionManager` or `ProducerFactory` beans, select explicitly by bean name/`@Qualifier`.

**Critical requirement:** the `KafkaTemplate` used in the listener must use the exact transactional producer factory compatible with the transaction manager used by the container. Two separate factories do not automatically share the same Kafka transaction.

## 7. Listener only processes input and sends output

Once the container is configured, the listener can focus on business logic:

```java
@Component
public class OrderProcessor {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderProcessor(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(
        topics = "orders",
        groupId = "order-processor",
        containerFactory = "orderListenerFactory"
    )
    public void handle(ConsumerRecord<String, String> record) {
        String normalizedOrder = record.value().trim();

        kafkaTemplate.send(
                "validated-orders",
                record.key(),
                normalizedOrder);
    }
}
```

Relevant imports:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;
```

The listener **does not manually call** `consumer.commitSync()`, `Acknowledgment.acknowledge()`, or `sendOffsetsToTransaction()` in this example. The container places the proper offsets into the Kafka transaction and commits after the listener succeeds. If business processing fails, the listener must throw an exception so the container triggers rollback/retry.

Do not arbitrarily call `KafkaTemplate.executeInTransaction(...)` inside a listener that already has a transactional container: this API can open a new Kafka transaction independent of the transaction coordinating offsets. For read-process-write EOS, letting outputs participate in the active transaction is the clearest model.

## 8. Calculating offsets to commit per partition

A committed offset is not a "this record is done" flag. It marks the next position the consumer group will read on each topic-partition.

Suppose the listener finishes:

```text
orders-0: offset 40, 41, 42
orders-1: offset 15
```

If all records are covered by one transaction and eligible to commit, the offset map looks like:

```text
TopicPartition("orders", 0) -> OffsetAndMetadata(43)
TopicPartition("orders", 1) -> OffsetAndMetadata(16)
```

Never commit past an unfinished record simply because a later record finished first. Spring Kafka tracks progress by listener mode, acknowledgment mode, and transaction scope. With batch listeners, an error mid-batch can widen the rollback and replay scope compared to single-record processing.

## 9. Crash points and expected outcomes

Consider input `orders-0@41` and expected output to `validated-orders`:

| Failure timing | Output | Group offset | On restart |
|---|---|---|---|
| Before sending output | No committed output yet. | 42 not committed yet. | Input can be reprocessed. |
| After `send()` but before transaction commit | Pending or aborted; not treated as committed output. | 42 not committed yet. | Input can be reprocessed; `read_committed` skips aborted output. |
| During commit, client gets no clear response | Kafka transaction state is determined by the coordinator; client may not know immediately. | Offset and output are not two separate commits. | Consumer recovers from actual committed offset. |
| Broker committed transaction successfully | Output is valid for `read_committed`. | Offset 42 committed. | Group normally resumes at offset 42. |

A `commitTransaction()` request may fail or disconnect while waiting for the broker's reply; **never assume the transaction aborted just because the client did not receive an acknowledgment**. What matters is that Kafka manages output and offset in the same transaction, so they never enter a "one side committed, the other side uncommitted" state under a proper transactional model.

If the application re-sends the output using another producer outside the transaction "just to be sure" after a timeout, it can inject duplicates into the topic and break the guarantee.

## 10. read_committed is the visibility condition for outputs

Kafka can write records to the log before a transaction is committed or aborted. A `read_uncommitted` consumer can read records from uncommitted transactions as well as transactions that later abort.

Downstream consumers wanting to see only outputs from successful transactions need:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[isolation.level]": read_committed
```

With `read_committed`, the Kafka consumer does not return records from aborted transactions. The consumer may also pause reading progress at the **Last Stable Offset (LSO)** while a transaction remains open; hence a long transaction can affect downstream output visibility latency.

Two states to distinguish:

- Producer future indicates `send()` was processed by the broker in the request context; **it does not mean the whole transaction committed**.
- A `read_committed` consumer sees outputs after the transaction commits and reads satisfy the isolation level.

If downstream uses `read_uncommitted`, part of the EOS guarantee based on transactional output is no longer honored in how downstream consumes.

## 11. EOS V2 and consumer group changes

Modern Spring Kafka uses **EOS V2**: offsets are sent into the transaction together with consumer group metadata. When a consumer rebalances and loses partition ownership, the broker can reject transaction/offset operations that no longer match the current group generation.

`transactional.id` solves a different problem: producer epochs **fence** old producers when a new producer with the same ID takes over. Understand the difference:

| Concept | Role |
|---|---|
| Consumer `group.id` | Identifies the group sharing partitions and committed offsets. |
| `Consumer.groupMetadata()` | Ties offset transactions to consumer group membership state. |
| Producer `transactional.id` | Identifies a transactional producer session sequence; used for fencing. |
| Producer epoch | Lets the broker invalidate an old producer session when a new producer claims the same ID. |
| Consumer `read_committed` | Filters uncommitted/aborted outputs per Kafka transactions. |

Do not use the same transactional ID for all replicas in a consumer group. During rolling updates when old and new pods run together, matching prefixes can cause `ProducerFencedException`. Assign distinct prefixes per active instance and monitor fencing after deployments.

## 12. Producer transaction cache and concurrency

`DefaultKafkaProducerFactory` reuses transactional producers once the prior transaction finishes. If multiple listener threads process concurrently, each active transaction needs its own producer; a single producer cannot run two independent transactions simultaneously.

```text
Pod order-service-1
  listener-0 -> transaction A -> producer P0
  listener-1 -> transaction B -> producer P1
  listener-2 -> transaction C -> producer P2

Three concurrent transactions require three producers.
```

With Spring Kafka 3.2+, `DefaultTransactionIdSuffixStrategy(maxCache)` can bound the number of suffixes allocated for producers. When no suffix is available, `NoProducerAvailableException` can occur. Size the cache for concurrency and other transactions running in **one JVM**, not multiplied by cluster-wide replica counts per pod.

If a producer stays cached longer than is healthy relative to the broker's `transactional.id.expiration.ms`, errors can occur upon reuse. `DefaultKafkaProducerFactory.setMaxAge(...)` lets the factory replace aged producers. Caching helps performance and producer lifecycle; **it does not enable EOS by itself** if the listener container lacks a Kafka transaction manager.

## 13. Timeouts, poll intervals, and long transactions

Transactions must be short enough to avoid timeouts and consumer group disruption:

| Property | Meaning |
|---|---|
| Producer `transaction.timeout.ms` | Broker-side transaction lifetime limit. |
| Broker `transaction.max.timeout.ms` | Maximum transaction timeout accepted by the broker. |
| Consumer `max.poll.interval.ms` | Maximum interval between `poll()` calls per consumer group policy. |
| Producer `request.timeout.ms` | Timeout for a single request, not the maximum duration of the entire transaction. |

If a listener performs slow database or HTTP calls, waits too long on synchronous retries, or processes huge batches, the transaction can time out and the consumer can trigger a rebalance. When that happens, the Kafka transaction aborts and inputs are redelivered via recovery.

Do not simply raise timeouts to very large values. Long-open transactions hold uncommitted output and stall `read_committed` downstream consumers. Measure per-record/batch processing time, reduce blocking work inside transactions, and choose timeouts with reasonable headroom.

## 14. Exceptions, aborts, and AfterRollbackProcessor

In transactional listeners, exceptions should lead to rollback/abort rather than wrong commits:

```text
poll input
    |
    v
Container beginTransaction()
    |
    v
Listener sends(output) then throws exception
    |
    v
Kafka transaction aborts
    |
    +--> aborted output invisible to read_committed
    |
    +--> transaction's offset does not commit
    |
    v
AfterRollbackProcessor / container reprocesses record
```

Spring Kafka provides `AfterRollbackProcessor` for post-rollback handling. With transactional listeners, retry/recovery behavior must align with transaction semantics; never copy a `DefaultErrorHandler` from a non-transactional listener and assume equivalent results.

**Do not swallow exceptions and return normally** when business processing actually failed. The container may consider the listener successful and commit outputs/offsets. If you recover from an error inside the listener, clearly define the contract under which the record is considered complete.

### Exhausting retries and routing to DLT

A poison record can repeatedly cause aborts. You can use after-rollback handling and a recoverer to send failing records to a DLT; if both the DLT publish and the source offset must be confirmed transactionally, configure an appropriate recovery transaction.

Spring Kafka versions support `DefaultAfterRollbackProcessor` executing recovery in a new transaction and committing the recovered offset under specific configuration conditions. Verify the exact API and listener type in use.

**Non-blocking retries via `@RetryableTopic` do not support direct combination with container transactions in Spring Kafka versions carrying this limitation.** If Kafka-to-Kafka EOS is required, choose compatible retry/recovery mechanisms instead of enabling all retry annotations together.

## 15. Exactly-once does not automatically include databases or HTTP

Kafka transactions are atomic only for changes covered by the Kafka transaction:

```text
orders -> listener
            |
            +--> UPDATE PostgreSQL    (separate DB transaction)
            |
            +--> KafkaTemplate.send   (Kafka transaction)
            |
            +--> offset commit        (Kafka transaction)
```

If the database commits successfully and then the Kafka transaction aborts, the input may be redelivered and the DB update applied a second time. If the Kafka transaction commits before a failing database operation, outputs/offsets are confirmed in Kafka while the DB remains unchanged.

To protect non-Kafka side effects, add:

- **Idempotency** by event ID, unique constraints, or controlled upserts.
- **Transactional outbox** to coordinate database changes with Kafka publishing intent.
- **Inbox/deduplication** so consumers receiving the same event multiple times avoid duplicate effects.
- **Idempotency keys** when calling external APIs, if supported by the partner system.
- Reconciliation procedures when two systems lack atomic distributed transactions.

Never interpret "exactly once" as "the listener runs once." A record may be re-executed by the listener multiple times across aborts; only Kafka outputs from committed transactions are recognized.

## 16. Observing transactions in production

Signals to view together:

| Signal | How to interpret |
|---|---|
| Transaction commit/abort rate | Rising aborts suggest listener failures, timeouts, or unstable transaction infrastructure. |
| Transaction duration | Long transactions increase latency and timeout risk. |
| `ProducerFencedException` / epoch errors | Check duplicate prefixes, producer lifecycle, and rebalances. |
| `NoProducerAvailableException` | Check bounded producer cache size and concurrent transactions. |
| Producer send failures | Distinguish broker/network/serialization errors from business errors. |
| Group committed offset | Confirms input progress has actually committed. |
| Consumer lag and LSO | Evaluates input backlog and output visibility via `read_committed`. |
| `AfterRollbackProcessor` / DLT recovery | Shows records routed to error handling instead of normal output. |

Exact metric names depend on the Kafka client, Micrometer, Spring Kafka, and application instrumentation; the table lists signals, not guaranteed metric names.

Structured logs should contain `inputTopic`, `partition`, `offset`, group ID, instance ID, output topic, transaction result, and exception type; avoid logging full sensitive payloads.

```text
event=kafka_read_process_write
input_topic=orders
input_partition=0
input_offset=41
output_topic=validated-orders
consumer_group=order-processor
transaction_result=ABORTED
exception_type=ValidationServiceUnavailableException
```

## 17. Testing crashes and transaction aborts

To prove EOS, you need integration tests with a transaction-capable Kafka broker; mocking `KafkaTemplate` cannot prove broker atomicity.

**Success scenario:** Publish an input, await output via a `read_committed` consumer, verify the group offset advances past the input. Output and committed offset must correspond to the same successful transaction.

**Listener error scenario:** Listener calls `send()` and throws an exception. Verify the transaction aborts, that output does not appear to a `read_committed` consumer, the offset does not advance because the transaction aborted, and the input can be retried.

**Pre-commit crash scenario:** Stop the instance after sending output but before `commitTransaction()`. After restart, the record is reprocessed; a `read_committed` consumer sees only the committed transaction's output.

**Rebalance/fencing scenario:** Trigger partition ownership transfer or duplicate transaction IDs in a test environment; verify errors are surfaced, offsets are not committed outside the transaction, and records still reprocess safely.

**Non-Kafka database scenario:** Let the DB commit and intentionally abort the Kafka transaction; observe that the DB side effect persists. Use that result to drive idempotency/outbox design.

Never run destructive tests or manually reset offsets in production; use isolated test topics and consumer groups.

## 18. Runbook: logs show output sent, but offsets do not advance

Suppose after a rollout, the service logs "send successful", yet consumer group `order-processor` is not advancing offsets.

1. **Check configuration:** Does the listener use the right factory wired with `KafkaAwareTransactionManager`? Does `KafkaTemplate` use the same transactional producer factory?
2. **Check transaction outcome:** `send()` can succeed before commit. Look for `commitTransaction()` errors, aborts, timeouts, and coordinator issues.
3. **Check `transactional.id`:** Are prefixes colliding across active pods? Are there `ProducerFencedException` or epoch errors after the rolling update?
4. **Check producer cache:** Are there enough producers for concurrency? Is `NoProducerAvailableException` occurring?
5. **Check consumer group:** Are assignment, rebalances, committed offsets, lag, and `max.poll.interval.ms` showing anomalies?
6. **Check downstream:** Do output consumers use `read_committed`? Are open transactions holding back LSO and delaying outputs?
7. **Check rollback/recovery:** Is the listener throwing exceptions? Are records retrying, routing to DLT, or recovering via after-rollback logic?
8. **Verify after fix:** Inputs are processed, outputs appear per committed transactions, offsets advance accordingly, and non-Kafka duplicate side effects do not increase.

Never manually reset offsets or call `seek` just to shrink lag before determining which transactions actually committed and which records went to the DLT.

## 19. Operational principles

- Combine Kafka outputs and input offsets in **one Kafka transaction** to achieve atomicity for Kafka-to-Kafka flows.
- Use `KafkaTransactionManager` on the listener container and a `KafkaTemplate` sharing the same transactional producer factory.
- Set `enable.auto.commit=false`; never use separate `commitSync()` calls for offsets sent in the container's transaction.
- Do not call `sendOffsetsToTransaction` manually in a transactional listener already coordinated by the container.
- Assign non-overlapping `transactional.id` prefixes across concurrently running instances to avoid fencing.
- Downstream consumers must read with `read_committed` if they must skip aborted messages.
- Never swallow business errors and return normally, as doing so can cause wrong transaction commits.
- Design retry/`AfterRollbackProcessor`/DLT to be transaction-compatible and avoid unsupported retry combinations.
- Bound transaction duration; monitor timeouts, producer caches, group rebalances, and offsets alongside outputs.
- Use idempotency/outbox/inbox for database and external API side effects outside Kafka.
- Test restarts, crashes before commit, aborts, and rebalances in isolated environments.

**Offsets and outputs in the same transaction** turn two potentially decoupled operations—publishing results and saving read progress—into one atomic change in Kafka. Committing the transaction makes outputs and offsets take effect together; aborting lets inputs be reprocessed while aborted outputs are never seen by `read_committed` consumers as valid results. End-to-end reliability still requires proper transaction manager configuration, explicit rollback/recovery handling, and safe design for side effects outside Kafka.
