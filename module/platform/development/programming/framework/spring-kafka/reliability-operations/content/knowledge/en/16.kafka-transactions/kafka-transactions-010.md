# AfterRollbackProcessor

In Spring Kafka, when a listener container is configured to run **Kafka transactions**, a listener failure can cause the transaction to roll back. However, rolling back the transaction only handles records and offsets belonging to **the current transaction**; it does not automatically decide which records the consumer should re-read, how long to wait, or where to route failing records once retries are exhausted. The **`AfterRollbackProcessor`** component handles that critical part of the post-rollback recovery flow.

The standard implementation is **`DefaultAfterRollbackProcessor`**. It can reposition the consumer to offsets that need to be re-read, apply backoff between failures, and, when properly configured, invoke a recoverer to send repeatedly failing records to a Dead Letter Topic (DLT). When atomicity is needed between publishing to the DLT and confirming the recovered offset, it can even coordinate a **new transaction**.

This lesson focuses on the role of `AfterRollbackProcessor`, how to configure it in Spring Kafka, exactly-once boundaries, and how to operate when transactions roll back repeatedly.

## 1. Position in a Kafka Transaction Lifecycle

A typical transactional consume-process-produce flow:

~~~text
Kafka input topic
      |
      v
Consumer poll()
      |
      v
Listener container starts Kafka transaction
      |
      v
@KafkaListener processes record and emits output via KafkaTemplate
      |
      +---- Success --------------------------------+
      |                                             |
      |                                Commit output + input offset
      |                                in the same Kafka transaction
      |
      +---- Throw exception
                   |
                   v
             Rollback transaction
                   |
                   v
             AfterRollbackProcessor
                   |
                   +---- Seek / arrange for re-poll
                   |
                   +---- Backoff and retry
                   |
                   +---- Retries exhausted: recovery / DLT
~~~

Core point: **rolling back a Kafka transaction does not mean the Kafka consumer automatically rewound to the old offset**. The consumer tracks a *current read position* in memory and a *committed offset* for the consumer group. After a `poll()`, the read position may have moved past the fetched records even if the transaction processing them fails. The container must coordinate seek/re-fetch so unconfirmed records still get a chance to be reprocessed.

For example, suppose an input partition has records at offsets 100, 101, and 102:

1. Consumer poll receives three records.
2. Listener processes offset 100, then fails on 101.
3. Kafka transaction rolls back: transaction outputs do not become committed data; the transaction's input offset is not committed either.
4. `AfterRollbackProcessor` helps reposition the consumer to reprocess the necessary records instead of skipping the remainder of the poll.
5. If offset 101 fails repeatedly and exhausts retries, a recovery policy can isolate that record so processing can move forward.

Exact details on which records are sought depend on record/batch listener type, polled records, processing order, and the recovery policy of your Spring Kafka version.

## 2. Distinguishing AfterRollbackProcessor from Error Handlers

Spring Kafka provides several error-handling components, and they are not wholly interchangeable:

| Component | Primary context | Responsibility |
|---|---|---|
| `CommonErrorHandler` / `DefaultErrorHandler` | Listener containers, especially non-transactional flows | Handles listener exceptions, retries/backoff, seeks, or recovery per configuration. |
| `AfterRollbackProcessor` | After a listener transaction rolls back | Coordinates re-reading records after rollback and transaction-compatible recovery. |
| `DefaultAfterRollbackProcessor` | Common default implementation for transactional listeners | Seeks/re-fetches, applies backoff, and invokes recoverer after failure limits. |
| `DeadLetterPublishingRecoverer` | Usable by error handlers or `AfterRollbackProcessor` | Publishes failed records to a DLT with diagnostic metadata. |
| `@RetryableTopic` | Non-blocking retries using auxiliary topics | Routes records to retry topics and DLT on delayed schedules. |

For listeners using Kafka transactions, **exceptions must lead to rollback**. Spring Kafka normally does not attach an exception-swallowing error handler in default transactional container setups so errors escape and transactions roll back. If you configure a custom common error handler that catches errors and returns as if successful, transactions may fail to roll back as intended.

Do not mechanically substitute `DefaultErrorHandler` for `AfterRollbackProcessor` in transactional containers. Nor should you assume `@RetryableTopic` is compatible with container transactions in every version; non-blocking retries and container transactions have separate constraints.

## 3. How Does DefaultAfterRollbackProcessor Work?

`DefaultAfterRollbackProcessor<K,V>` implements the `AfterRollbackProcessor<K,V>` contract. Common flow with a record listener:

- When a processing transaction fails, the container rolls back the open transaction.
- The processor determines which records need reprocessing and adjusts consumer positions, typically by seeking on the affected topic-partitions.
- A `BackOff` determines the wait interval before the next attempt.
- After the configured number of retries, the processor can invoke a **recoverer** for the persistently failing record.
- Once recovery succeeds, the processor can advance the consumer past the handled record according to policy.
- Other records must still respect partition offset boundaries; recovering one record must never silently drop unprocessed records.

Example:

~~~text
Input partition P0: [A@10] [B@11] [C@12]

A succeeds, B throws exception
         |
         v
Transaction rollback
         |
         v
After rollback: A/B/C may be redelivered depending on
transaction state and seek/re-fetch mechanism
         |
         v
B still fails after configured retries
         |
         v
Recover B -> DLT -> advance to subsequent records
~~~

Because A might be reprocessed after the transaction rolls back, never assume an external non-Kafka operation executed while processing A will be automatically reversed. Databases, emails, HTTP calls, and systems outside Kafka transactions require idempotency or a separate coordination strategy.

### 3.1. Backoff and attempt counts

`DefaultAfterRollbackProcessor` accepts a Spring `BackOff` to pace retries. For example, `FixedBackOff(1_000L, 2L)` specifies a 1-second wait and up to **two retries** under the `FixedBackOff` contract (in addition to the initial attempt).

For exponential backoff, use an appropriate `BackOff` implementation. Set finite limits, factoring in listener execution time and retry budgets. Retrying a permanent data error endlessly spikes partition lag and wastes resources unnecessarily.

### 3.2. Recovery after exhausting retries

A recoverer typically processes a `ConsumerRecord` together with its exception. A common choice is `DeadLetterPublishingRecoverer` to emit records to a DLT. It isolates "poison pill" records from the main flow once the retry policy completes.

Not every record belongs in a DLT. Certain business flows may need to pause/stop the container, alert operators, or wait for a dependency to recover. The chosen recovery approach must reflect correctness requirements, not solely the desire to lower consumer lag.

## 4. Configuring Container Transactions in Spring Kafka

The example below illustrates wiring the components together. Assume the application already has a Kafka-transaction-enabled `ProducerFactory` and a matching `ConsumerFactory`.

~~~java
@Configuration
@EnableKafka
public class OrderKafkaConfiguration {

    @Bean
    KafkaTransactionManager<String, OrderEvent> kafkaTransactionManager(
            ProducerFactory<String, OrderEvent> producerFactory) {
        return new KafkaTransactionManager<>(producerFactory);
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent> orderListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory,
            KafkaTransactionManager<String, OrderEvent> kafkaTransactionManager,
            DefaultAfterRollbackProcessor<String, OrderEvent> afterRollbackProcessor) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.getContainerProperties()
                .setKafkaAwareTransactionManager(kafkaTransactionManager);
        factory.setAfterRollbackProcessor(afterRollbackProcessor);

        return factory;
    }
}
~~~

In older Spring Kafka versions, the API for attaching a transaction manager to the container may have another name (such as `setTransactionManager`). The examples above use the API style of versions supporting `setKafkaAwareTransactionManager`; pick the exact API of your dependency.

Spring Boot example enabling producer-side transactions:

~~~yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: orders-worker-0-
      acks: all
    consumer:
      enable-auto-commit: false
      properties:
        isolation.level: read_committed
~~~

`transaction-id-prefix` must be designed to be unique across concurrently active producers, while also supporting fencing during restarts/failovers. Do not reuse the exact same prefix across active-active replicas if they could generate colliding transactional IDs.

`read_committed` is especially critical for **downstream consumers**: it ensures they see only records from committed transactions and skip records from aborted ones. It does not enable Kafka transactions on listeners and does not replace `AfterRollbackProcessor`.

### 4.1. Listener participating in container-managed transactions

~~~java
@Component
public class OrderListener {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;
    private final OrderService orderService;

    public OrderListener(
            KafkaTemplate<String, OrderEvent> kafkaTemplate,
            OrderService orderService) {
        this.kafkaTemplate = kafkaTemplate;
        this.orderService = orderService;
    }

    @KafkaListener(
            topics = "orders.in",
            groupId = "order-worker",
            containerFactory = "orderListenerFactory")
    public void onOrder(ConsumerRecord<String, OrderEvent> record) {
        OrderEvent transformed = orderService.transform(record.value());
        kafkaTemplate.send("orders.out", record.key(), transformed);
    }
}
~~~

In a properly configured transactional listener container, `KafkaTemplate` joins the active transaction. When the listener succeeds, input offsets and Kafka outputs commit atomically within Kafka. When the listener throws an exception, the transaction rolls back and `AfterRollbackProcessor` handles recovery.

Do not arbitrarily call `KafkaTemplate.executeInTransaction(...)` inside a listener already running in a container transaction expecting the two transactions to merge; keep transaction boundaries and producer factories explicit.

## 5. Configuring DefaultAfterRollbackProcessor with a Recoverer

A practical configuration using `DeadLetterPublishingRecoverer` as an escape hatch for failing records:

~~~java
@Bean
DefaultAfterRollbackProcessor<String, OrderEvent> afterRollbackProcessor(
        KafkaTemplate<String, OrderEvent> kafkaTemplate) {

    var recoverer = new DeadLetterPublishingRecoverer(
            kafkaTemplate,
            (record, exception) ->
                    new TopicPartition(
                            record.topic() + ".DLT",
                            record.partition()));

    var backOff = new FixedBackOff(1_000L, 2L);

    var processor =
            new DefaultAfterRollbackProcessor<String, OrderEvent>(
                    recoverer,
                    backOff);

    processor.setKafkaTemplate(kafkaTemplate);
    processor.setCommitRecovered(true);

    return processor;
}
~~~

Key imports:

~~~java
import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DefaultAfterRollbackProcessor;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.util.backoff.FixedBackOff;
~~~

In this example:

- The recoverer routes failed records from `orders.in` to `orders.in.DLT` while preserving the partition number. The DLT topic must already have the target partition; otherwise publishing can fail. A different destination resolver can be used depending on infrastructure strategy.
- `FixedBackOff` bounds retry count and wait time.
- `setKafkaTemplate` supplies the Kafka operations needed by the processor to handle recovered offsets in a new transaction.
- `setCommitRecovered(true)` works with matching transaction configuration to send the recovered record's offset into a new transaction.
- The recoverer needs a producer compatible with Kafka transactions if DLT publishing and recovered offset commits must commit atomically.

This example targets a **record listener**. It does not guarantee that APIs, defaults, and serializer types are identical across all versions. If the DLT needs to send raw `byte[]` from deserialization-failed records, configure compatible serializers rather than relying solely on `OrderEvent`'s serializer.

### 5.1. Why does commitRecovered matter?

Suppose a record at offset 51 repeatedly fails and has been published to the DLT. Afterward, the consumer needs to advance to offset 52. If the DLT publish succeeds yet the input offset is not durably confirmed, on restart the record at offset 51 may be read again and emitted to the DLT again.

A proper transactional recovery setup can group:

~~~text
Main processing transaction: rollback
            |
            v
Open new recovery transaction
            |
            +---- Publish failed record to DLT
            |
            +---- Send offset 52 for consumer group
            |
            v
Commit recovery transaction
~~~

If the recovery transaction commits, the DLT output and the recovered input offset are confirmed together within Kafka. If the transaction fails or aborts, neither action is treated as committed. This boundary prevents the "DLT written yet offset did not advance" failure mode during Kafka recovery.

This atomicity **does not cover side effects outside Kafka**. An earlier successful HTTP call or database commit still requires separate idempotency/compensation.

## 6. Distinguishing Main Transaction from Recovery Transaction

You cannot commit a transaction that has already rolled back. If DLT publishing and the recovered offset must commit together, the system must execute them in a **new transaction** after rollback.

| Step | Transaction | Outcome on failure |
|---|---|---|
| Process input record and send main output | Listener transaction | Rolls back Kafka output and transaction input offset. |
| `AfterRollbackProcessor` coordinates seek/retry | Post-rollback | Prepares redelivery or recovery. |
| Publish DLT and commit recovered offset | New recovery transaction when configured | If rolled back, recovery is not treated as complete. |
| Process next record | Next listener transaction | Follows a fresh transaction boundary. |

You can reuse the same transactional `KafkaTemplate`/`ProducerFactory` across applicable steps, while letting Spring Kafka manage the transaction context. Never manually commit offsets using another consumer outside the container mechanism and expect recovery transactions to remain atomic.

Furthermore, never equate **the recoverer returning without error** with **the DLT write actually succeeding durably** across all producer send modes. For reliable DLT paths, configure recoverers/producers to await or verify send outcomes per your version so publish failures propagate rather than being ignored.

## 7. Choosing BackOff for Transactional Listeners

Backoff should fit the failure type and how long a partition can remain paused while waiting. Common choices:

| Scenario | Strategy |
|---|---|
| Short-lived dependency timeout | A few retries with fixed or exponential backoff. |
| Overloaded downstream dependency | Bounded exponential backoff, avoiding synchronized retry storms. |
| Unprocessable schema-invalid payload | Low retry limit or classification for early recovery. |
| Permanent business error | Isolate / send to DLT per business policy. |
| Unstable broker or transaction coordinator | Monitor transaction/cluster errors; do not merely raise listener retries. |

For extended retries, factor in `max.poll.interval.ms`, heartbeats, rebalances, transaction timeouts, and how backoff is implemented. `DefaultAfterRollbackProcessor` can coordinate `BackOff` variants and pause/seek logic depending on version, but never assume long sleeps are always safe for consumer group membership.

When a listener fails on a difficult record, bounded retries prevent partitions from stalling indefinitely. However, never auto-skip records carrying critical operations merely to reduce consumer lag.

### 7.1. Exception classification

Some exceptions are clearly permanent, such as validation failures or un-deserializable data. You can configure exception classification / retry policies on the processor or recoverer per your Spring Kafka API.

One design pattern groups exceptions into:

- **Retryable**: transient timeouts, HTTP 503, dependency not yet ready.
- **Non-retryable**: permanent schema mismatch, missing mandatory fields, disallowed business state.
- **Operator intervention**: missing DLT permissions, recoverer serializer error, prolonged transaction coordinator unavailability.

Do not classify solely on broad exception names like `RuntimeException`. Inspect root causes; multiple failure types wrapped inside one exception need distinct policies.

### 7.2. Changing exceptions across attempts

In practice, a record may fail first from a timeout, and then fail validation once the dependency comes back. Some versions of `DefaultAfterRollbackProcessor` support resetting backoff state when the exception type changes or when recovery fails. Options such as `setResetStateOnExceptionChange` and `setResetStateOnRecoveryFailure` should be reviewed per version.

If retry state is not reset appropriately, a brand-new error may be treated as having exhausted retries due to inherited attempt counts. Conversely, resetting too aggressively can hold records back longer. Test policies against sequences of changing exceptions.

## 8. Recovery Failures and DLT Loop Risks

An easily overlooked scenario is **when the recoverer itself fails**:

~~~text
Listener error -> rollback -> retries exhausted
                              |
                              v
                      Send record to DLT
                              |
                         broker/ACL/serialization error
                              |
                              v
                    Recovery incomplete
                              |
                              v
                    Record may be retried
~~~

If the DLT does not exist, lacks write permissions, has a serializer incapable of handling the payload, or the broker rejects the request, never treat the record as recovered.

Ensure:

- The DLT has enough partitions for the destination resolver.
- The DLT producer has serializers capable of handling both normal records and deserialization-failed records if needed.
- ACLs allow publishing, and replication/`acks` meet durability requirements.
- Exceptions during DLT publishing are observed and trigger appropriate retries/recovery.
- No unbounded replay loop feeds a DLT record back into a DLT infinitely.

For diagnostics, log the original topic/partition/offset, listener error type, recoverer error, and transaction status. Never put sensitive raw payloads or full stack traces into metric labels.

## 9. Batch Listeners Have Different Boundaries from Record Listeners

With a **record listener**, the container knows the specific failing record, so the processor can recover per record within supported limits. With a **batch listener**, the listener receives an entire list of records and throws an exception; if the exception does not identify which element failed, the framework cannot easily tell which records in the batch succeeded.

Example:

~~~java
@KafkaListener(
        topics = "orders.in",
        containerFactory = "transactionalBatchFactory")
public void onBatch(List<ConsumerRecord<String, OrderEvent>> batch) {
    for (ConsumerRecord<String, OrderEvent> record : batch) {
        orderService.process(record.value());
    }
}
~~~

If the 8th record fails, the transaction for the entire batch may roll back; preceding records may re-execute when the batch is re-read. Depending on version, `AfterRollbackProcessor` handles batches differently; whole-batch recovery features were added in newer releases.

Never assume per-record recoverer configuration works identically on batch listeners. If exact isolation of individual poison records is required, consider a record listener, index-aware error signaling, or a batch workflow whose recovery is verified with integration tests.

## 10. Offsets, Seeking, and Partition Ordering

Kafka guarantees record ordering **only within a partition**. When transactions roll back, redelivery reprocesses uncommitted records; this can increase latency for subsequent records.

For example, suppose a partition holds `A -> B -> C`, where B is a poison pill:

~~~text
A succeeds -> B fails -> rollback
       |
       +---- retry B (and records needing replay)
                  |
                  +---- retry again
                  |
                  +---- recover B -> DLT
                                   |
                                   v
                                   Continue C
~~~

Once B recovers successfully and its offset commits via the recovery transaction, the consumer can advance past B. Thus, the DLT stores failing records so the main partition does not stay blocked forever.

However, a DLT alters **business completion order**: C may be processed while B has not succeeded. If B and C update the same entity with strict ordering requirements, do not adopt skip-to-DLT without safeguards against applying invalid state. You can pause the flow, use versioning, or enforce controlled repair/replay.

## 11. Fencing, Zombie Instances, and Rollbacks

Kafka transactional producers use `transactional.id` and producer epochs to fence an old producer session when a new session claims the same identity. If an old instance stalls, a replacement instance can bump the epoch, invalidating the old instance's transactions.

An error like `ProducerFencedException` is a **producer ownership** problem, not a business error solvable by infinitely retrying records on the same fenced producer session.

When transaction errors appear:

1. Distinguish listener exceptions from transaction commit/abort errors or producer fencing.
2. Identify which instance legitimately owns the transactional identity.
3. Check whether `transactionIdPrefix` collides across replicas.
4. Continue work only on a valid producer session, letting the container reinitialize transactions from a safe state.
5. Ensure processing outside Kafka remains idempotent on redelivery.

`AfterRollbackProcessor` handles records after rollback while the container remains valid, but it does not replace transactional producer ownership management and cannot fix a configuration causing continuous producer fencing.

## 12. Comparing Recovery With and Without Kafka Transactions

| Scenario | Non-transactional consumer | Transactional container + `AfterRollbackProcessor` |
|---|---|---|
| Listener fails | `CommonErrorHandler` can retry/seek/recover | Transaction rolls back; `AfterRollbackProcessor` coordinates retry/recovery. |
| Kafka output before listener fails | May already have been published independently | Outputs from aborted transactions never appear to `read_committed` consumers. |
| Input offset | Committed per `AckMode`/error handling | Offset sent in transaction is not committed on rollback. |
| DLT publish | May be independent of offset commit | Can coordinate DLT and recovered offset in a new recovery transaction. |
| External DB/HTTP | Not atomic with Kafka | Still not atomic merely because Kafka transactions are enabled. |
| Redelivery | Still possible | Still possible before commit; business logic must tolerate retries. |

Kafka transactions provide strong guarantees within **Kafka topics/offsets** when producers and consumers are properly configured. They do not guarantee end-to-end exactly-once for systems involving databases, REST APIs, or emails.

## 13. Observing and Diagnosing AfterRollbackProcessor

In production, monitor both rollback counts and recovery effectiveness. Key metrics/logs:

- Listener exception counts and transaction rollbacks by topic/partition/exception class.
- Time from first attempt until a record succeeds or is recovered.
- Retry counts and backoff durations per error category.
- Consumer lag per partition, especially on partitions with poison pills.
- Records published to DLT and DLT publish failure counts.
- `commitRecovered` errors or recovery transaction failures.
- Transaction coordinator errors, producer fencing, and rebalances during retries.
- Backlog of records sitting in DLT awaiting investigation and replay.

A dashboard showing only aggregate lag can hide a single partition rolling back continuously. Correlate topic, partition, offset, event ID, and exception to pinpoint the specific record causing congestion.

Debug messages like "seek to offset" may appear repeatedly because that is intentional behavior when retrying after rollback. What matters is whether the same record eventually succeeds, moves to DLT cleanly, or loops endlessly.

### Short investigation procedure

1. Identify the initial exception causing rollback and the record coordinates.
2. Check whether the Kafka transaction rolled back or failed during commit/abort.
3. Check processor backoff and recovery thresholds.
4. Verify whether the record is sought/re-fetched or the listener is blocked on a dependency.
5. If retries are exhausted, check the DLT topic, serializers, ACLs, and publish outcomes.
6. Verify the offset committed after recovery, not just recoverer logs.
7. Watch lag metrics and confirm the pipeline moves on to subsequent records.
8. If errors persist, separate poison records from infrastructure failures or producer fencing.

## 14. Testing Transactional Rollback and Recovery

Use a real Kafka broker, such as Embedded Kafka or Testcontainers, to test commit/abort behavior and consumer offsets. Tests calling Java listener methods directly cannot verify Kafka transaction semantics.

Recommended scenarios:

1. **Success:** listener emits output; verify input offset and Kafka output commit.
2. **Fail once then succeed:** listener throws on the first attempt; verify the first transaction rolls back, the record is re-read, and only the final committed output is read with `read_committed`.
3. **Poison record:** listener always fails; after configured retries, the record is published to DLT.
4. **`commitRecovered`:** verify DLT output and the failed record's input offset commit together when the recovery transaction commits.
5. **DLT publish failure:** misconfigure permissions or serializers; verify the record is never silently treated as recovered.
6. **Multiple records per poll:** a middle record throws; verify remaining unprocessed records are not dropped.
7. **Batch listener:** failure on one element; verify whole-batch rollback semantics per active configuration.
8. **Restart during retries:** stop the consumer before commit and restart; verify redelivery/idempotency.
9. **Fencing:** run two producer sessions with colliding transactional identities to verify handling when the older session loses ownership.
10. **External side effects:** simulate a DB/HTTP call succeeding before Kafka rollback; verify idempotency on redelivery.

Inspect topics using a consumer with `isolation.level=read_committed`. Do not merely count records using `read_uncommitted`, as that mode can expose records from aborted transactions depending on log state and timing.

Use finite test timeouts, latches, or offset/record assertions rather than long `Thread.sleep()` calls. Clean up consumer groups, topics, and executors after tests to prevent cross-test interference.

## 15. Common Pitfalls

- **Assuming rollback automatically rewinds the consumer to the old offset:** seek/redelivery coordination from the container/`AfterRollbackProcessor` is required.
- **Assuming `AfterRollbackProcessor` is a transaction manager:** the processor recovers after rollback; it does not establish the listener's main transaction boundary.
- **Configuring an exception-swallowing error handler:** can prevent transactions from rolling back as intended.
- **Using infinite retries for permanent data errors:** partitions stay wedged and lag grows.
- **Sending to DLT without committing recovered offsets properly:** records may reprocess and appear in DLT repeatedly.
- **Believing recoverer return means durable DLT write:** inspect producer responses and transaction/recoverer configuration.
- **Using a DLT with fewer partitions than the destination resolver expects:** publishes can fail when preserving partition numbers.
- **Applying per-record recovery assumptions to batch listeners without verification:** batches have different retry boundaries and failure identification.
- **Assuming Kafka transactions roll back databases or HTTP:** external side effects still require idempotency.
- **Ignoring `isolation.level` on test/downstream consumers:** leads to false conclusions about aborted outputs.
- **Retrying a fenced producer:** transactional producer ownership cannot be restored via normal record retries.
- **Ignoring Spring Kafka version API changes:** setters, defaults, and recovery behaviors can differ across releases.

## 16. Choosing Configuration for Production

A stable operational design should answer these questions:

- Are the listener container's transaction manager and producer factory configured accurately?
- Which exceptions must trigger rollback, and which can recover early?
- Do backoff and retry limits align with SLAs and consumer lag budgets?
- Once retries are exhausted, does the DLT/recoverer have sufficient permissions and matching serializers?
- Does DLT publishing need to commit **together with** the recovered offset in a new transaction?
- Is the listener record-based or batch-based, and which unit does recovery target?
- After skipping a record to DLT, does business ordering for subsequent records remain valid?
- Are databases/APIs protected against duplicate processing when Kafka transactions roll back?
- Does monitoring distinguish listener rollbacks, recovery failures, DLT publish failures, and producer fencing?
- When upgrading Spring Kafka versions, have corresponding semantics been re-tested?

**`AfterRollbackProcessor`** is the bridge between transaction rollback and record reprocessing. Used properly with `DefaultAfterRollbackProcessor`, backoff, recoverers, and recovery transactions, it prevents Spring Kafka systems from stalling on repeatedly failing records without losing observability or breaking Kafka commit boundaries. Ultimately, reliability stems from aligning offsets, Kafka outputs, DLTs, retry bounds, and idempotency across systems outside Kafka.
