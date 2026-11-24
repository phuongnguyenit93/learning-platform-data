# EOS in Spring Kafka

**Exactly-once semantics (EOS)** in Spring Kafka is the ability to guarantee that a sequence of **reading a record from Kafka → processing → writing a new record to Kafka** can be observed as a single successful processing within the Kafka scope, even when the consumer or producer fails at sensitive moments. The core mechanism is a **Kafka transaction**, in which output records and consumer consumption offsets are committed **atomically**: either both are confirmed together, or neither is confirmed.

That does not mean the listener is invoked only once. In crash, rebalance, or transaction abort scenarios, an input record may be reprocessed by the listener. EOS protects **Kafka-to-Kafka** results from exposing duplicate outputs from aborted transactions; it does not automatically provide exactly-once guarantees for database updates, HTTP APIs, emails, or side effects outside the Kafka transaction.

This lesson explains the commitment scope of EOS, how to configure transactions in Spring Kafka, error handling, producer fencing, interaction with offsets and retries, limitations when integrating with databases, how to test, as well as operational considerations in production.

## 1. Exactly-once must be understood within the right scope

Kafka provides related but non-identical features:

| Feature | What problem does it solve? | What does it not guarantee on its own? |
|---|---|---|
| Producer idempotence | Reduces the risk of duplicate writes caused by the producer retrying requests within a producer session | Does not combine consumer offset commits with output writes |
| Kafka transaction | Commits or aborts a set of Kafka writes and offsets in the same transaction | Does not transact atomically with external databases |
| `read_committed` isolation | Consumer does not see data from aborted Kafka transactions | Does not fix side effects outside Kafka |
| Spring Kafka transactional listener container | Wraps receiving and processing a record in a Kafka transaction, adding offsets to the transaction on success | Does not make the listener run only once |
| Idempotent business handler | Does not create duplicate business impact when a record is reprocessed | Does not replace the transaction requirement for atomic output and offset |

An accurate statement is: **Kafka EOS for a read-process-write flow guarantees that Kafka writes and input consumption positions are committed together**, when using the proper transactional producer, transactional container, and output consumers configured in the appropriate mode.

### 1.1. Why is the name misleading?

Suppose a consumer reads `OrderCreated`, performs calculations, and writes `InvoiceRequested` to another topic. The listener may have run the first time and sent the output, but the process crashes before the Kafka transaction commits. After restart, the same `OrderCreated` is read again and the listener runs a second time. If the first transaction is aborted, a `read_committed` downstream consumer only sees the output of the second committed transaction. **The Kafka result is only confirmed once, but the code may have executed twice.**

If the listener in the example also calls an email-sending API before the transaction commits, the email may already have been sent twice. Kafka has no authority to roll back an email.

## 2. The problem when using only at-least-once

With a traditional consumer, reading input, sending output, and committing offsets can be independent operations.

~~~text
Input: orders.events, partition 0, offset 40
       |
       v
Consumer processes OrderCreated
       |
       v
Producer sends InvoiceRequested -> output is written
       |
       X Process crashes before committing input offset
       |
       v
Restart: consumer reads offset 40 again
       |
       v
Producer sends InvoiceRequested again
~~~

If the output is a normal Kafka side effect without transactions or deduplication, downstream consumers may receive two `InvoiceRequested` records.

An error in the opposite direction is equally dangerous: if the application commits offset 41 **before** the output is successfully written, a process crash can cause input offset 40 to be skipped without producing output.

Two operations must be bound atomically:

1. Writing the Kafka output.
2. Committing the Kafka input read position.

That is why Kafka transactions are needed instead of merely enabling retries or an idempotent producer.

## 3. The read-process-write mechanism with Kafka transactions

A listener container with a transaction manager starts a transaction before invoking the listener. The listener uses a `KafkaTemplate` backed by a transactional producer factory to send output. If the listener completes successfully, the container adds the input offset to the transaction and commits. If the listener throws an exception, the transaction is rolled back; the transaction's output is invisible to `read_committed` consumers, and the input can be read again after recovery.

~~~text
Consumer poll -> Input offset 40
                   |
                   v
           BEGIN Kafka transaction
                   |
                   v
          Listener processes event
                   |
                   v
         KafkaTemplate.send(output)
                   |
            +------+------+
            |             |
         Success       Exception
            |             |
            v             v
    Include input offset  Abort Kafka transaction
    in transaction        (output is aborted)
            |             |
            v             v
    Commit transaction    Record can be
    (output + offset)     redelivered after rollback
            |
            v
  Downstream read_committed
  sees committed output
~~~

### 3.1. What does atomicity actually include?

A Kafka transaction allows writes to **multiple Kafka topics or partitions** and the input consumer's offset commit to reside in the same transaction. On a successful commit, the output records and consumption offsets are confirmed together; on abort, the output does not become committed output and the offset from that transaction does not advance.

This does not turn the entire microservice into a distributed transaction. Database transactions, cache updates, HTTP requests, filesystem writes, or sending notifications do not automatically participate in the Kafka transaction.

### 3.2. The committed offset is the next position

For an input at offset 40, the consumer group commits offset 41 once that record is successfully processed. If there are multiple records in the same transaction, the committed offset for each partition is the next position after the last successfully processed record within that scope.

In a transactional container, Spring Kafka coordinates sending offsets to the transaction. Normal listeners do not call `KafkaConsumer.commitSync()` directly or use another Kafka producer to commit offsets.

## 4. Required Spring Kafka components

A read-process-write EOS configuration typically consists of:

1. **ConsumerFactory** to create the Kafka consumer for input.
2. **ProducerFactory** supporting Kafka transactions, with a transactional ID prefix.
3. **KafkaTransactionManager** or a compatible transaction manager.
4. **Transactional listener container** using that manager.
5. **KafkaTemplate** to send output through the corresponding transactional producer.
6. Downstream consumers using `isolation.level=read_committed` if they must observe only committed transactions.

~~~text
ConsumerFactory
      |
      v
Listener container ---> KafkaTransactionManager
      |                         |
      v                         v
@KafkaListener            Transactional ProducerFactory
      |                         |
      v                         v
KafkaTemplate -----------------> Kafka broker
                                 |
                                 +-- Output records
                                 +-- Consumer offsets
                                 +-- Commit/abort marker
~~~

It is not enough to create a `KafkaTemplate` with a transaction manager while the listener container still commits offsets separately. Conversely, if the container is transactional but the output producer does not participate in that transaction, the output is not atomically bound to the offset either.

## 5. Spring Boot configuration

An example configuration for an application that transforms events from an input topic to an output topic:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: billing-processor
      enable-auto-commit: false
      isolation-level: read_committed
      auto-offset-reset: earliest
    producer:
      transaction-id-prefix: billing-tx-
      acks: all
    listener:
      ack-mode: record
~~~

Meaning of the properties:

| Property | Meaning |
|---|---|
| `spring.kafka.producer.transaction-id-prefix` | Enables the transactional producer mechanism in compatible Spring Boot configurations, serving as the base for generating transactional IDs |
| `enable-auto-commit: false` | Lets the container control offsets instead of having the Kafka consumer auto-commit on a timer |
| `isolation-level: read_committed` | Consumer reads committed Kafka transactions and does not read outputs from aborted transactions |
| `acks: all` | Producer waits for broker acknowledgments according to the acks policy |
| `ack-mode: record` | Illustrates the container ack mode; with transactions, offsets are still sent to the transaction by the container |
| `group-id` | Identifies the consumer group, which must be stable across business logic and deployments |

Note: enabling `read_committed` on the **input consumer** protects it when the input topic has transactional producers. For downstream to see only committed outputs, the **downstream consumer must also use `read_committed`**. Configuring only the input consumer does not change the isolation level of other services.

### 5.1. The transaction ID prefix must be designed for the deployment

In production with multiple pods/instances running concurrently, you must ensure the transactional IDs they generate do not collide unintentionally. An application-level prefix alone may not be enough if instances share the same transactional ID space.

Example strategy:

~~~text
billing-tx-<deployment-instance-id>-
~~~

Each pod receives an instance identifier suited to the deployment lifecycle, and Spring Kafka then generates transactional IDs with suffixes for producers in the cache. Do not use the same transactional ID for two concurrently active producers because the broker may fence one producer.

Uniqueness must be guaranteed across all running instances, not just across threads within one pod. During scale-out, rolling updates, or blue/green deployments, check the ID space across both old and new versions.

### 5.2. Spring Boot auto-configuration and custom factories

In a standard Spring Boot configuration, a transaction ID prefix allows Boot to create transactional producer support and `KafkaTransactionManager` if auto-configuration conditions are met. However, when the application declares a custom `ConcurrentKafkaListenerContainerFactory` or replaces the manager/producer factory, you must **verify that the listener container is actually wired with the Kafka transaction manager**.

Do not assume EOS is active just because the YAML file has `transaction-id-prefix`. Verify the actual beans, the listener container factory, and the `KafkaTemplate` send path.

## 6. Example listener reading from Kafka and writing to Kafka in a single transaction

Suppose the input topic `orders.created` contains `OrderCreated`, and the output `billing.requests` contains `BillingRequested`. The logic only transforms the event and writes to Kafka, without calling a database or HTTP API.

~~~java
@Component
public class BillingRequestListener {

    private final KafkaTemplate<String, BillingRequested> kafkaTemplate;

    public BillingRequestListener(
            KafkaTemplate<String, BillingRequested> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(
            topics = "orders.created",
            groupId = "billing-processor",
            containerFactory = "ordersTransactionalFactory")
    public void onOrder(
            ConsumerRecord<String, OrderCreated> record)
            throws Exception {

        OrderCreated source = record.value();
        BillingRequested result = new BillingRequested(
                source.orderId(),
                source.customerId(),
                source.total());

        kafkaTemplate.send(
                "billing.requests",
                record.key(),
                result).get(10, TimeUnit.SECONDS);
    }
}
~~~

This is an illustrative Java example; record types and serializers must be declared in the actual application. `get(10, TimeUnit.SECONDS)` ensures Kafka send failures surface during the listener execution rather than being ignored in a future. Choose the timeout based on the system's SLA and transaction timeout.

In the container transaction mechanism:

1. The container starts a Kafka transaction.
2. The listener calls `kafkaTemplate.send(...)`.
3. `KafkaTemplate` uses a transactional producer participating in the active transaction when configured with the proper `ProducerFactory`.
4. The listener returns successfully.
5. The container sends the input offset to the transaction and commits the transaction.

If the send fails or the listener throws an exception, the container aborts the transaction according to the error-handling flow.

### 6.1. Do not catch an exception and return successfully

A common mistake:

~~~java
@KafkaListener(topics = "orders.created")
public void wrong(OrderCreated event) {
    try {
        sendOutput(event);
    }
    catch (Exception ex) {
        log.error("Failed to send output", ex);
        // Wrong: returns successfully even though the business operation to send output failed.
    }
}
~~~

If the listener finishes normally and the transaction commits without the intended output, the offset may be confirmed as processed. Let the exception propagate to the container, or perform explicit durable recovery before treating the record as successful.

### 6.2. Creating an explicit transactional listener factory

In an application with multiple factories, you can configure a dedicated factory with a transaction manager:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
ordersTransactionalFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        KafkaAwareTransactionManager<?, ?> kafkaTransactionManager) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<
                    String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);

    factory.getContainerProperties()
            .setKafkaAwareTransactionManager(kafkaTransactionManager);

    return factory;
}
~~~

The example uses the container configuration API of Spring Kafka versions that have `setKafkaAwareTransactionManager(...)`. Some older versions have a transaction manager setter with a different name. Check against the dependency version in use. The manager must manage a `ProducerFactory` compatible with the `KafkaTemplate` used by the listener.

In this snippet, the listener uses a transactional container factory, rather than merely sending to Kafka inside a manually opened transaction unlinked from the input offset.

## 7. Is @Transactional needed on @KafkaListener?

When the **listener container** is configured with a Kafka transaction manager, the container already starts a transaction before invoking the listener. Therefore, for a standard Kafka-to-Kafka flow, it is not necessary to add `@Transactional` to the listener just to open a Kafka transaction a second time.

`@Transactional` on a service may serve a database transaction or another transaction boundary, but you must clearly understand:

- Which transaction starts first?
- Does `KafkaTemplate` participate in the container's transaction?
- In which Kafka transaction is the consumer offset committed?
- Is the database transaction committed before or after the Kafka transaction?
- When either commit fails, how can the system recover?

Avoid combining multiple transaction managers or annotating `@Transactional` without specifying a manager and then assuming it yields an atomic transaction between Kafka and the database.

## 8. Producer idempotence is not enough for read-process-write EOS

A Kafka producer has idempotence to prevent a producer request retry from causing the broker to write the same batch twice within the guarantees of a producer session. However:

~~~text
Consume offset 40
      |
      v
Idempotent producer sends output
      |
      v
Crash before committing consumer offset
      |
      v
Re-consume offset 40
      |
      v
Application sends a new output
~~~

Producer idempotence does not recognize those two business invocations as the same event; they can be two distinct send actions. You need a Kafka transaction to combine output and offset, or an appropriate deduplication strategy at the downstream consumer.

Transactions build upon Kafka producer mechanisms, but cannot be replaced merely by enabling `enable.idempotence`.

## 9. Isolation level: read_committed vs. read_uncommitted

A Kafka consumer can configure `isolation.level`:

| Isolation | Data returned |
|---|---|
| `read_uncommitted` | May read records belonging to a transaction that is later aborted |
| `read_committed` | Does not return records from aborted transactions; returns only committed transactional outputs together with valid non-transactional records |

Example:

~~~text
Producer T1: begin
Producer T1: send output X
Producer T1: abort

Consumer read_uncommitted: may see X
Consumer read_committed: does not see X
~~~

If downstream still uses `read_uncommitted`, it can observe outputs from aborted transactions, defeating the purpose of EOS at the downstream result level. Consumers that require transactional results should use `read_committed`.

### 9.1. Last Stable Offset

A `read_committed` consumer does not read past the boundary determined by open transactions, commonly called the **Last Stable Offset (LSO)**. If a transaction runs too long or hangs, downstream may be delayed in receiving even other records located behind it in the partition.

Therefore, long transactions not only slow down the listener; they can also increase record visibility latency at downstream consumers. Monitor transaction duration, lag, and record age.

### 9.2. read_committed does not mean the entire topic is EOS

A topic can receive records from both transactional producers and non-transactional producers. `read_committed` only handles the visibility of Kafka transactions; it does not prove every record was produced by an EOS workflow or that every producer has correct logic.

## 10. The EOS V2 mechanism in Spring Kafka

Modern Spring Kafka versions use Kafka's EOS V2 mechanism for listener containers, relying on the broker managing transactional producers and consumer group metadata to ensure proper producer fencing and offset commits. Older documentation or versions may refer to the previous EOS model.

Operational points to understand:

- Kafka transactions use `transactional.id` to identify the transactional producer.
- The broker uses producer identity/epoch to fence an old producer when a producer with the same transactional ID replaces it.
- Associated consumer group metadata is used when offsets are sent into a transaction.
- The container must synchronize with the consumer group lifecycle and rebalances to prevent an old producer from continuing to commit invalid results.
- APIs, minimum broker requirements, and EOS mode options can differ across Spring Kafka versions.

Do not copy EOS mode configurations from old articles without checking the current version. In newer versions, old configurations may have been removed or replaced.

### 10.1. Transactional ID and fencing

If two producers concurrently use the same `transactional.id`, the broker can fence the older producer. Fencing is a safety feature preventing two instances from committing transactions under one identity.

Common failure example:

~~~text
Pod A -> transactional.id = billing-tx-0
Pod B -> transactional.id = billing-tx-0
                         |
                         v
               Old producer is fenced
                         |
                         v
             Pod A's transaction fails
~~~

The solution is not to disable fencing, but to design a proper ID space, manage the producer cache, and understand rolling deployment scenarios.

## 11. Managing transaction timeout and producer lifecycle

Kafka transactions have timeouts managed by the producer and broker. If a transaction exceeds the threshold, the broker may abort it, and the application's commit attempt fails.

Common causes:

- Listener performs slow downstream I/O.
- Waiting on a long HTTP timeout within the same Kafka transaction.
- Processing a batch with too many records.
- Blocked workers or threads.
- Unstable broker/network.
- A transactional producer stays unused for a long time and encounters transactional ID expiration or cache-related errors.

### 11.1. Do not stretch a transaction across uncontrolled asynchronous work

A dangerous pattern:

~~~java
@KafkaListener(topics = "orders.created")
public void listen(OrderCreated event) {
    executor.execute(() -> publishOutput(event));
    // Listener returns before the worker sends the output.
}
~~~

When the listener returns, the container may consider the work complete and commit the input offset. The worker running afterward is not necessarily still inside the consumer thread's Kafka transaction. The result may lose atomicity.

If parallelization is needed, design separate transaction boundaries, synchronize task results before committing, or choose another controlled model. Do not assume the Kafka transaction context automatically propagates across a thread pool.

### 11.2. Producer cache and maxAge

Spring Kafka can cache transactional producers. In environments where producers are rarely used, a long-cached producer may run into issues related to transactional ID state on the broker. Spring Kafka versions support the `maxAge` property on `DefaultKafkaProducerFactory` to refresh a transactional producer before it becomes too stale.

Do not increase or decrease it arbitrarily. Cross-check the Spring Kafka version, broker-side transactional ID expiration, processing frequency, transaction timeout, and producer cache metrics.

## 12. Consumer group rebalances when using EOS

During scale-out, scale-in, rolling deploys, or consumer heartbeat loss, group rebalances can occur. Partition ownership moves, and an in-flight transaction may be aborted or fail to commit as expected.

In that case:

1. Records not yet confirmed by a committed Kafka transaction may be redelivered.
2. Output from an aborted transaction is not visible to `read_committed` downstream.
3. The new listener reprocesses the record and can produce a valid committed output.
4. Any non-Kafka side effects from the old processing attempt must still be protected by idempotency.

EOS does not eliminate the need for graceful shutdown or tuning `max.poll.interval.ms`. A listener exceeding the consumer group's limits can trigger rebalances and cause unnecessary aborts and redeliveries.

### 12.1. Scaling out does not mean unlimited throughput gains

The number of consumers that can process in parallel is bounded by the number of partitions. With transactional listeners, there is also the overhead of starting/committing Kafka transactions, producer caching, and broker coordination. Increasing replicas beyond the partition count can leave idle members without increasing throughput.

## 13. When a listener throws an exception: rollback and recovery

In a transactional listener, an exception must trigger a **Kafka transaction rollback**. After rollback, the container and after-rollback components decide whether to seek, retry, or recover the record.

In many transactional Spring Kafka configurations, `DefaultAfterRollbackProcessor` plays a key role in controlling record redelivery after rollback. Do not blindly copy `DefaultErrorHandler` instructions meant for non-transactional containers onto transactional listeners without checking the error-handling path.

~~~text
Listener processes input
         |
         +-- Success
         |      |
         |      v
         |  Output + input offset commit together
         |
         +-- Exception
                |
                v
           Abort transaction
                |
                v
         AfterRollbackProcessor
                |
           Retry / Seek / Recover
~~~

### 13.1. Retryable and non-retryable errors

Transient timeouts may warrant finite retries with backoff. Malformed payloads or contract violations typically do not fix themselves through retries. Policies should classify them:

| Error group | Handling approach |
|---|---|
| Transient network timeout | Retry with backoff and a retry limit |
| Broker transaction error | Rollback/recover according to producer and container semantics |
| Permanent validation error | Recovery/DLT per policy, do not retry fruitlessly |
| Schema/serialization error before listener | `ErrorHandlingDeserializer` and appropriate recovery if needed |
| Database error outside Kafka | Requires idempotency/reconciliation; avoid assuming Kafka rollback rolls back DB |

## 14. DLT and recovery in transactional flows

When a record ultimately cannot be processed successfully, it can be written to a DLT so processing can continue for other records. In a transactional setup, **publishing to the DLT and confirming the source offset** must be designed carefully to avoid losing records or unintentionally duplicating recovery.

One approach is to configure after-rollback recovery using a transactional `KafkaTemplate` and committing the recovered record's offset in an appropriate **new Kafka transaction**. Options such as `commitRecovered` on `DefaultAfterRollbackProcessor` and the associated transaction manager have specific semantics and version requirements; check the specific configuration.

### 14.1. Do not ack the source when DLT publish fails

If sending to the DLT fails while the source offset is committed, the record can be lost from the processing stream with no saved copy for recovery. Therefore:

- Wait for or observe the DLT publish result in the recoverer.
- Do not swallow exceptions from the DLT producer.
- Ensure the record is retried/redelivered if recovery fails to persist it.
- Monitor DLT send failures and transaction aborts.
- Test scenarios where the DLT broker is unavailable or ACLs are invalid.

### 14.2. Non-blocking retry topics do not combine arbitrarily with container transactions

Spring Kafka has compatibility limitations between **non-blocking retry topics** and **container transactions**. Do not assume that adding `@RetryableTopic` to a transactional listener yields EOS across all topic hops. In common Spring Kafka releases, non-blocking retries are not supported with container transactions.

When Kafka-to-Kafka EOS is required, favor rollback/retry mechanisms compatible with transactional containers and a transactional DLT design. If delayed retries across multiple topics are needed, evaluate topology and atomicity separately instead of applying the EOS label based solely on an annotation.

## 15. EOS and databases: the most important limitation

Suppose a listener performs two actions:

1. Writes order state to PostgreSQL.
2. Writes an `OrderProcessed` event to Kafka and commits the input offset.

A Kafka transaction can cover step 2 and the offset, but cannot automatically include step 1:

~~~text
             Kafka input
                 |
                 v
              Listener
             /        \
            v          v
       Database      Kafka output
       transaction   + input offset
            |          |
         COMMIT      Kafka txn commit
            |
    A crash can occur in between
~~~

If the database commits and then the Kafka transaction aborts, the input record can be read again and the database update runs again. If the Kafka transaction commits but the database does not complete, downstream sees the output while the database lacks the corresponding state.

No simple Spring transaction manager turns these two resources into a true distributed XA transaction merely by putting `@Transactional` on the listener. Coordinating commits between Kafka and a database still leaves a failure window.

### 15.1. Outbox pattern

When the database is the source of truth and needs to reliably publish Kafka events, the **transactional outbox** is often a strong choice:

1. Within a single database transaction, update the business table.
2. In the same transaction, insert a row into the outbox table.
3. Commit the database transaction.
4. An outbox publisher or CDC emits the event from the outbox to Kafka.
5. Mark or clean up the outbox according to a safe policy.

~~~text
Business request
      |
      v
DB transaction:
   update orders
   insert outbox_event
      |
      v
DB COMMIT (atomic)
      |
      v
Outbox publisher / CDC
      |
      v
Kafka topic
~~~

The outbox keeps business state and publishing intent inside one database transaction. Publishing from the outbox to Kafka may happen at-least-once, so consumers still need idempotency.

### 15.2. Inbox / idempotent consumer

When a Kafka consumer updates a database, an **inbox table** with a unique event id can prevent duplicate processing:

~~~sql
CREATE TABLE consumed_events (
    event_id VARCHAR(120) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Within the same database transaction:

1. Insert the event id; if it already exists, recognize the record as already processed.
2. Execute the business update for the new event.
3. Commit the transaction.
4. Let the consumer complete and commit the Kafka offset according to configuration.

If Kafka redelivers the record after the database commit, the event id prevents a second update. `Exactly-once effect` in the database depends on database transactions and idempotency constraints, not solely on Kafka EOS.

## 16. HTTP APIs, payments, and external side effects

Calling payment APIs, sending emails, pushing notifications, or writing files lie outside the Kafka transaction. If a listener calls an API before the Kafka transaction commits and the Kafka transaction aborts, the record may be reprocessed.

Example:

~~~text
Consumer receives PaymentRequested
          |
          v
HTTP payment API -> charge succeeds
          |
          v
Kafka output send
          |
          X Kafka transaction abort
          |
          v
Record is reprocessed
          |
          v
HTTP payment API is called again
~~~

For APIs supporting an **idempotency key**, send a business-stable key (such as a request ID) so retries do not create a second charge. For APIs that do not support idempotency, you need request state tracking, reconciliation, and handling for ambiguous timeouts.

Do not use Kafka's transactional ID as a business idempotency key. A transactional ID identifies a producer, not a payment command.

## 17. Difference between EOS and processing order

Kafka still guarantees offset ordering of records within a single partition. However, a system with multiple partitions or asynchronous processing can produce side effects that complete out of business order.

EOS does not automatically solve:

- Two events for the same aggregate being routed to two partitions due to an unstable key.
- Worker executors processing in parallel and writing side effects out of order.
- Retry topics allowing newer records to overtake older records waiting for retry.
- Two different services concurrently updating an entity without a version check.

If `OrderCreated` is required before `OrderPaid`, partition by aggregate key, process sequentially per key, or verify versions/sequences in the state store. Kafka EOS protects atomic output + offset within a transaction; it does not replace a business state machine.

## 18. Transaction failure matrix

A good way to understand EOS is to examine specific crash points:

| Failure point | Kafka output | Input offset | Behavior after recovery |
|---|---|---|---|
| Before starting transaction | Not sent | Not committed | Record is read again |
| After opening transaction, before output | Not committed | Not committed | Transaction aborts/times out; read again |
| After sending output, before transaction commit | Uncommitted/aborted | Not committed | `read_committed` does not see aborted output; read again |
| When transaction commit fails | Cannot be assumed committed | Cannot be assumed committed | Must let client/container handle outcome and reinitialize as needed |
| After transaction commit succeeds | Output committed | Offset committed with transaction | Group advances from next offset |
| After database commit, before Kafka transaction commit | DB side effect exists | Kafka may not be committed | Kafka redelivery; DB must be idempotent |
| Producer fenced | Current transaction cannot continue committing | Offset not committed by failed transaction | Container must handle fatal fencing and restore ownership |

Do not try to "self-fix" a commit failure by issuing a send or commit outside the failing transaction without understanding producer state. Doing so can break atomicity.

## 19. Monitoring for transactional Spring Kafka

Useful metrics must show both **processing progress** and **transaction health**.

| Metric/log | Purpose |
|---|---|
| Kafka transaction begin/commit/abort rate | Measures success and failure rates of transactions |
| Transaction commit latency | Detects slow broker/network performance |
| Producer fencing errors | Detects transactional ID collisions or producer replacement |
| Producer send errors | Detects output records failing to send |
| Consumer lag/oldest record age | Detects backlog and SLA violations |
| Rebalance count/duration | Correlates aborts with group membership changes |
| Downstream read_committed lag | Detects long-running or stuck open transactions |
| After-rollback retry/recovery rate | Measures redelivered records |
| DLT publish failures | Detects unsafe recovery paths |
| Listener processing duration | Tracks how long a transaction may remain open |

Not every metric is automatically exported by Spring Kafka under the exact table names above. You may need Micrometer, Kafka client metrics, container events, structured logs, or custom instrumentation.

### 19.1. Recommended alerts

- Sustained increase in transaction aborts.
- Abnormal appearance of `ProducerFencedException` or transaction errors.
- Consumer lag rising alongside listener processing time.
- Sharp increase in commit latency.
- DLT/recovery publisher failures.
- A pod continuously restarting/rebalancing and causing aborts.
- Downstream `read_committed` consumers not receiving new records despite uncommitted data on the broker.

Set thresholds based on workload baselines; a small number of transaction aborts during rolling deployments may be acceptable, but continuous aborts causing backlog require investigation.

## 20. Runbook: ProducerFencedException

When encountering producer fencing:

1. Identify the `transactional.id` or prefix associated with the error.
2. Check whether two instances are using the same transactional ID.
3. Inspect rolling updates, blue/green deployments, and actual replica counts.
4. Inspect the producer cache and how suffixes are assigned in each process.
5. Determine whether a consumer group rebalance occurred around the time of the error.
6. Do not continue using a fenced producer to commit transactions.
7. Recover the container/producer via the lifecycle supported by Spring Kafka.
8. Verify there are no duplicate downstream outputs and that offsets advance once the application stabilizes.

Fencing protects correctness; do not attempt to disable fencing to ignore errors. Fixing the root cause of ID collisions or ownership coordination is the right approach.

## 21. Runbook: Input lag increases while output does not appear

1. Check the input consumer group and partition assignments.
2. Verify whether the listener is actually being invoked.
3. Check whether exceptions are causing Kafka transactions to abort continuously.
4. Check producer send timeouts, the broker transaction coordinator, and ACLs.
5. Check whether downstream uses `read_committed`, and whether any long-running/open transaction is blocking LSO.
6. Check actual committed offsets rather than only looking at listener invocation counts.
7. Check the after-rollback processor and DLT routing if a record is a poison pill.
8. Reconcile input event ids with output event ids if the contract supports it.

Do not switch `read_committed` to `read_uncommitted` just to "see output" in production: doing so can feed outputs from aborted transactions into downstream processing.

## 22. Runbook: Duplicate outputs despite transactions enabled

Questions to investigate:

1. Are the duplicate outputs from two different **committed** Kafka transactions?
2. Did the original input contain two events with the same business id?
3. Did the listener send output via a `KafkaTemplate` using the right transactional producer factory?
4. Is the listener container actually transactional, or did only the producer open a transaction on its own?
5. Is another service publishing the same output type outside the transactional flow?
6. Is downstream using `read_committed`?
7. Did a manual replay or DLT replay generate a new event?
8. Is the event id kept stable and does the downstream consumer implement idempotency?

EOS does not deduplicate two **distinct events with identical payloads** sent by a producer as two separate business commands. Business event ids and deduplication are needed if that is required.

## 23. Testing EOS in an integration environment

Unit tests that merely mock `KafkaTemplate` are insufficient to prove atomic offset + output. Use a real test broker or integration environment (for example, Testcontainers) with transaction support.

### 23.1. Happy path: output and offset commit together

1. Create input and output topics.
2. Configure the transactional listener container and transactional `KafkaTemplate`.
3. Send an input event with an event id.
4. Wait for the listener to process successfully.
5. Verify the output can be read by a `read_committed` consumer.
6. Verify the input consumer group offset advances past that record.
7. Restart the consumer and verify no additional output is produced from the already committed input.

### 23.2. Listener fails after sending output

1. The listener sends output inside a Kafka transaction.
2. Intentionally throw an exception before the listener returns successfully.
3. Observe the transaction abort.
4. Use a `read_committed` consumer to verify the aborted transaction's output is not visible.
5. Verify the input was not committed by the failed transaction.
6. Allow the listener to reprocess successfully and verify only the committed output is seen.

### 23.3. Process crash before commit

1. Use fault injection right after output is sent but before transaction commit.
2. Stop the process or force the transaction to abort per the test scenario.
3. Restart the consumer.
4. Verify the input is redelivered.
5. Verify `read_committed` downstream sees only valid committed output.
6. If the listener has database side effects, verify inbox/idempotency prevents duplicates.

### 23.4. Producer fencing during scale-out

1. Create two instances using the same transactional ID in a test environment.
2. Trigger a producer replacement/fencing scenario.
3. Verify that one producer cannot commit the old transaction.
4. Fix the ID strategy so the two instances have distinct IDs.
5. Test rolling deploys and rebalances.

### 23.5. DLT failure and recovery

1. Force the listener to throw a non-retryable exception.
2. Trigger after-rollback recovery according to policy.
3. Cause the DLT producer send to fail or lack ACLs.
4. Verify the input offset is not committed and the record is not lost.
5. Restore DLT access and verify the record is safely persisted.

### 23.6. What must be verified beyond logs?

When asserting outcomes, verify:

- Whether the transactional output actually committed or aborted.
- Actual consumer group offsets.
- Data visible via `read_committed`.
- Count of database side effects, if any.
- Event ids and business event ordering.
- Error handling/fencing/recovery after crashes.

Merely logging "Kafka transaction started" or "listener invoked once" is not enough to prove EOS.

## 24. Common mistakes

**Enabling only producer idempotence and calling it EOS.** Idempotence does not combine output and consumer offset into a single transaction.

**Setting only `transaction-id-prefix` without checking the listener container.** A custom factory might not receive the transaction manager, causing offsets to still commit separately.

**Assuming `@Transactional` on the method automatically guarantees DB + Kafka atomicity.** Two resources do not get a distributed commit from a single annotation.

**Calling `KafkaTemplate` from a worker thread after the listener returns.** The worker may not participate in the container transaction; the offset may already commit before the send.

**Swallowing send exceptions and letting the listener return successfully.** This can commit the offset without the intended output.

**Downstream using `read_uncommitted`.** It can see Kafka outputs from aborted transactions.

**Two pods using the same transactional ID.** This can cause fencing and continuous aborts.

**Long-running transactions.** They can time out, increase lag, and make `read_committed` consumers wait longer.

**Using non-blocking retry topics arbitrarily with transactional containers.** Check compatibility limits and redesign EOS/recovery with proper semantics.

**Forgetting idempotency for HTTP, databases, and email.** Kafka transactions do not roll back external side effects.

**Assuming a newly generated event id after replay is still the same event.** Business deduplication requires a stable ID.

## 25. EOS implementation checklist

### Scope and contract

- [ ] Confirmed whether the goal is Kafka-to-Kafka read-process-write or requires non-Kafka side effects.
- [ ] Clearly documented which topics/offsets are included in the transaction.
- [ ] Identified which flows must use `read_committed`.
- [ ] Designed event ids and idempotency when redelivery is possible.

### Spring Kafka configuration

- [ ] `ProducerFactory` has transaction support and a non-colliding transactional ID strategy across instances.
- [ ] `KafkaTransactionManager` is properly created and attached to the listener container.
- [ ] `KafkaTemplate` uses the producer factory participating in the corresponding transaction.
- [ ] Consumer auto-commit is disabled when the container manages offsets.
- [ ] Ack mode, concurrency, and partition assignment fit the workload.
- [ ] Transaction timeout and producer cache are managed according to version.

### Error handling

- [ ] Exceptions from the listener abort the transaction instead of being swallowed.
- [ ] After-rollback retry/recovery is properly configured.
- [ ] DLT publish/offset recovery has a safe handling path.
- [ ] Incompatible retry topologies are not used with container transactions.
- [ ] Fencing/rebalance scenarios are tested and have runbooks.

### External systems

- [ ] Database consumers have an inbox/idempotent handler or equivalent pattern.
- [ ] When the DB is the source of truth, the transactional outbox has been considered.
- [ ] HTTP/API side effects use idempotency keys or reconciliation.
- [ ] Full end-to-end EOS is not promised if resources reside outside the Kafka transaction.

### Testing and observability

- [ ] Happy path verifies offsets commit together with outputs.
- [ ] Crash before commit is fault-injected and redelivery is tested.
- [ ] Aborted transactions do not expose outputs to `read_committed`.
- [ ] Tested producer fencing, transaction timeout, rebalance, and DLT failure.
- [ ] Metrics/alerts for transaction aborts, commit latency, lag, and producer errors.
- [ ] A reconciliation approach exists for event ids, committed offsets, and business side effects.

## Conclusion

EOS in Spring Kafka is not a promise that a Java listener will only be invoked once. With a **transactional listener container**, **transactional `KafkaTemplate`/`ProducerFactory`**, **Kafka transaction manager**, and **downstream `read_committed`**, a read-from-Kafka then write-to-Kafka flow can commit outputs and consumer offsets atomically. When a transaction fails, aborted outputs do not become committed outputs and inputs can be reprocessed. Therefore, Kafka-to-Kafka EOS is a commitment about **committed results**, not the execution count of a function.

To operate reliably, you must manage transactional IDs, fencing, transaction timeouts, producer caches, rebalances, after-rollback recovery, and DLTs. If the listener also updates databases or calls HTTP APIs, Kafka transactions do not cover those side effects: use inbox/idempotency, outbox, or appropriate reconciliation workflows. Testing crashes right before commit and actually observing behavior with a `read_committed` consumer alongside committed offsets is how you distinguish a genuinely EOS configuration from one that is only "transactional" in name.
