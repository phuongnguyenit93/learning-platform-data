# Message Loss, Duplicates, and Retries

In a Spring Kafka system, the three phenomena of **message loss**, **duplicate message processing**, and **retries** are closely related yet occur at different points in the event lifecycle. To operate reliably, you must clearly establish how far the producer sent the message, what the broker acknowledged, which work the consumer completed, and whether the offset was committed.

Kafka stores messages by partition and offset. The producer sends records to the partition leader; the broker replicates data to replicas in the ISR (in-sync replicas); the consumer reads and processes records; finally, the consumer group stores offsets to record how far it has processed. Each step can fail independently. Therefore, configuring retries at one step does not automatically solve failures at the remaining steps.

## 1. Distinguishing Message Loss, Duplicates, and Retries

- **Message loss:** an event the system needs to process can no longer be processed. Either the message was not durably stored by the broker, or the consumer advanced the offset past the message before business work completed.
- **Duplicate:** the same event is sent or processed multiple times. Duplicates can occur even though Kafka stores each record at a unique offset and has no data corruption in the broker.
- **Retry:** another attempt to process after a previous attempt failed. Retries are a recovery mechanism; if uncontrolled, they can create duplicates, invert event ordering, or trigger load spikes.

Basic processing flow:

    Producer
       |
       v
    Partition leader ----> ISR replicas
       |
       v
    Consumer poll
       |
       v
    Business processing
       |
       v
    Commit consumer offset

A message is considered completely processed only when the business work has reached a durable state and the offset has been recorded according to the proper policy. "Producer sent successfully", "broker returned ACK", and "consumer finished processing" are three distinct milestones.

| When failure occurs | Main risk | Control direction |
|---|---|---|
| Producer sends without waiting for acknowledgement | Broker may not have stored the message | acks, retries, and idempotent producer |
| Leader fails before copies are sufficiently safe | An ACKed message may be missing on the newly elected replica | Replication factor, ISR, and leader election |
| Consumer commits offset before finishing processing | Message may be skipped after restart | Disable auto commit; commit after processing |
| Consumer finishes processing but has not committed offset | Message may be redelivered | Idempotent business handler |
| Processing fails transiently | Message needs to be retried | Backoff, error handler, or retry topic |
| Message remains unprocessable after multiple attempts | One bad record can block the stream | Dead-letter topic (DLT) and recovery workflow |

## 2. Preventing Message Loss on the Producer and Broker Side

### 2.1. Choosing the Appropriate Acknowledgement Level

The producer uses the acks property to decide what acknowledgement level to wait for:

- acks=0: the producer does not wait for broker acknowledgement. The application may fail to notice that a message never reached the broker.
- acks=1: the leader acknowledges after writing the record to its local log. If the leader fails before other replicas receive the record, the message can be lost when an older replica is elected leader.
- acks=all (equivalent to -1): the leader acknowledges only after replicas currently in the ISR have recorded the record. This is the right choice for flows requiring high durability.

acks=all must be paired with proper replication settings. For example, a topic has replication factor 3 and min.insync.replicas=2. Then a producer using acks=all requires at least two replicas in the ISR to accept a write. If the ISR drops below the minimum, the broker rejects writes instead of acknowledging a record that does not meet the required safety threshold. The application must handle send failures and can retry when the cluster recovers.

Example broker/topic configuration commonly used for critical data:

    # Corresponding broker configuration or topic configuration
    default.replication.factor=3
    min.insync.replicas=2
    unclean.leader.election.enable=false

Create production topics with an explicit replication factor; default.replication.factor mainly applies when brokers auto-create topics. Disabling unclean leader election prevents electing an out-of-ISR replica that may lack data, at the cost that writes/reads on the partition may pause when no eligible replica remains. This is a trade-off between availability and the risk of data loss.

Replication does not replace backups. It protects against certain broker and disk failures, but does not fully protect against accidental deletions, application bugs writing bad data, expired retention, or outages affecting all replicas simultaneously.

### 2.2. Enabling the Idempotent Producer and Handling Send Errors

When a producer sends a batch but the ACK is lost in transit, the producer may resend. Without protocol-level deduplication on the producer, the broker could write the same send as multiple records.

Enable the idempotent producer so Kafka detects resends within the same producer session and avoids duplicate writes from protocol-layer retries:

    spring:
      kafka:
        producer:
          acks: all
          properties:
            enable.idempotence: true
            delivery.timeout.ms: 120000
            request.timeout.ms: 30000

The timeout values above are illustrative examples only; tune them according to network latency, SLAs, and expected recovery times. delivery.timeout.ms bounds the total time the producer waits to succeed or report failure. When the deadline expires, the application must record the error and decide the next steps.

An idempotent producer protects record send retries within a producer session via Kafka's mechanism. It does not prevent the application from explicitly calling send() twice for the same business event, does not automatically deduplicate across two independent producers, and does not replace consumer-side idempotency. If the application restarts and re-emits the same event, the system still needs a stable eventId to identify that event.

Do not configure acks, retries, or max.in.flight.requests.per.connection in conflict with idempotence requirements. The Kafka client enforces compatibility constraints and may reject invalid configurations. Verify the effective producer configuration after application startup.

### 2.3. Distinguishing Send Errors from Processing Errors

The producer must observe the outcome of send operations. With asynchronous APIs, calling send() does not mean the message was acknowledged by the broker. The application should track the send callback or future, log terminal failures, and never silently ignore exceptions.

If an application writes data to a database and then emits a Kafka event, there is a failure gap between the two operations: the database commit succeeds, but the application stops before sending the event. Producer retries alone do not close this gap. You can use **Transactional Outbox**: write the business change and an outbox record in the same database transaction, then have a relay process send outbox records to Kafka. The relay may send duplicates, so consumers still need idempotency.

## 3. Preventing Message Loss on the Consumer Side

### 3.1. Committing Offsets After Successful Processing

A consumer group stores offsets to know the next position to read. If the offset is committed before business work finishes, the consumer can skip records if the process fails.

Example dangerous scenario:

1. Consumer receives record at offset 120.
2. Consumer commits the next offset as 121.
3. Application calls the database, but the process stops before the transaction completes.
4. Consumer restarts and resumes from offset 121.
5. Record 120 is not redelivered to that consumer group.

For processing where message loss must be avoided, disable auto commit and let the Spring Kafka container manage commits after the listener finishes successfully:

    spring:
      kafka:
        consumer:
          enable-auto-commit: false
        listener:
          ack-mode: record

With AckMode.RECORD, the container commits the record's offset after the listener processes it successfully. With AckMode.BATCH, the offset is committed after all records in the poll batch succeed. Choose the mode matching your listener and replay tolerance.

If a listener uses manual acknowledgment, call acknowledge() only after durable work has completed. Do not ACK immediately upon receiving the record or before the database transaction commits. Offset commits can still fail or the consumer can rebalance; thus, completed processing without a committed offset can still lead to redelivery. This is a common source of duplicates and must be resolved with idempotency.

### 3.2. Understanding Transaction Boundaries

When a listener writes to a database, the typical operation order is:

    Receive record
        |
        v
    Begin database transaction
        |
        v
    Apply business changes
        |
        v
    Database commit
        |
        v
    Commit Kafka offset

If the process stops after database commit but before offset commit, Kafka redelivers the record. If you reverse the order and commit the offset before the database, a database error can lose the work. With an independent database and Kafka, you cannot create a single atomic transaction spanning both simply by reordering those two operations.

Therefore, consumers writing to databases should design operations that can run safely multiple times, such as using a unique constraint on eventId, conditional upserts, or an inbox table. If multiple systems must be coordinated, define transaction boundaries clearly and use outbox/inbox or an appropriate coordination mechanism.

### 3.3. Watching Retention and Invalid Offsets

Kafka retains records only according to the topic's retention policy. A consumer stopped longer than the retention period may no longer be able to read older data. With compacted topics, Kafka can remove older versions of the same key according to compaction policy; a compacted topic is not an archive of every historical change.

Monitor consumer lag, consumer downtime, and the age of unprocessed records. Set retention based on maximum recoverable outage duration, storage capacity, and business requirements. Configure auto.offset.reset intentionally as well: earliest can reread available data when a group has no valid offset; latest may skip data older than the new starting position. Neither can recover records past retention.

## 4. Understanding and Controlling Duplicates

### 4.1. Where Do Duplicates Come From?

An event can appear multiple times in the following cases:

- The producer did not receive an ACK and resent; the idempotent producer handles this protocol-layer duplicate.
- Application logic emits the same event multiple times, such as a user resubmitting a request or an outbox relay restarting.
- The consumer wrote to the database successfully but stopped or rebalanced before committing the offset.
- An error handler, retry topic, or DLT re-drive procedure redelivers the same event.
- Two independent flows both emit representations of the same business change.

Therefore, "Kafka has unique offsets" does not mean "a business event is processed only once". An offset identifies a record within a partition; it does not automatically identify logical duplicates sent at another offset or to another topic.

### 4.2. Using a Stable Event ID

Every business event should have a stable identifier, such as eventId, generated when the event is created and preserved across resends, retry topics, and DLTs. Do not generate a new event ID on each retry, as doing so prevents the system from recognizing attempts belonging to the same event.

Example payload:

    {
      "eventId": "evt-8f21a6",
      "eventType": "OrderPaid",
      "aggregateId": "order-1042",
      "occurredAt": "2026-11-15T10:30:00Z",
      "payload": {
        "orderId": "order-1042",
        "amount": 125000
      }
    }

In a consumer writing to a database, you can create an inbox or processed_event table with event_id as a unique key. Recording the processed marker and updating business data must be in the same database transaction:

    BEGIN;

    INSERT INTO processed_event (event_id, processed_at)
    VALUES (:event_id, CURRENT_TIMESTAMP)
    ON CONFLICT (event_id) DO NOTHING;

    -- Execute business changes only if INSERT actually added a row.
    -- If event_id already exists, skip the previously completed work.

    COMMIT;

The application must check how many rows were inserted to decide whether to apply the business change. If the business operation fails, the transaction must roll back the inbox marker too so redelivery can retry. Never commit the processed marker in a separate transaction before updating business data, as that could cause records to be skipped even though the work failed to complete.

For a consumer reading only one topic, the tuple topic + partition + offset can identify one specific occurrence. However, eventId is usually better suited for business idempotency because it can be preserved when the same event is re-published to another topic or re-emitted from an outbox.

### 4.3. Designing Idempotent Business Operations

An idempotent operation produces an equivalent business outcome when executed multiple times with the same identifier or target state. Examples:

- Conditionally set order status to PAID instead of incrementing a payment counter.
- Use a unique transaction reference to avoid recording a payment twice.
- Insert records with a unique key and handle conflicts intentionally.
- Use an aggregate version to reject stale or repeated updates.

Not every operation can be turned into a state assignment. For balance debits/credits, sending notifications, or calling billing APIs, you need an idempotency key that the target system understands and persists durably. If an external API supports an idempotency key, pass the same key across all attempts.

## 5. Choosing Delivery Semantics

Three common terms describe the trade-off between message loss and duplicates:

| Semantics | Offset recording timing | Characteristics |
|---|---|---|
| At-most-once | Before processing | Avoids redelivery in some scenarios but can lose work |
| At-least-once | After successful processing | Avoids skipping unprocessed records but can reprocess |
| Exactly-once | Combines data and offset in a supported transaction | Achievable within Kafka transaction scope; does not automatically cover side effects in external systems |

For many business systems, **at-least-once combined with an idempotent consumer** is the practical choice: records may be redelivered, yet the business effect is applied only once per eventId.

Kafka transactions support consume-process-produce flows within Kafka: input records, output records, and consumer offsets can be committed atomically in the same transaction. Consumers reading transaction outputs should use isolation.level=read_committed so they do not see records from uncommitted or aborted transactions.

Example consumer configuration when reading transactional data:

    spring:
      kafka:
        consumer:
          properties:
            isolation.level: read_committed

In Spring Boot, you can enable producer transactions with spring.kafka.producer.transaction-id-prefix using a unique prefix per application instance. Transaction and listener container configuration must match your Spring Kafka version. Kafka EOS protects the chain of operations within Kafka; if the listener also writes to a database, makes HTTP calls, or sends emails, those side effects still require separate transactions or idempotency.

## 6. Retrying When Processing Fails

### 6.1. Classifying Errors Before Retrying

Not every error can be resolved by retrying.

| Error group | Example | Appropriate action |
|---|---|---|
| Transient | Database timeout, dependent service briefly unreachable, network glitch | Retry with backoff and a limit |
| Invalid data | Missing required field, malformed format, invariant violation | Do not retry indefinitely; route to DLT or error-handling flow |
| Configuration/permission error | Wrong credentials, missing access rights, topic does not exist | Alert and fix configuration; continuous retries rarely help |
| Contention/state error | Version conflict, resource not yet ready | Assess retriability, idempotency, and attempt limits |

Retries are useful only when the root cause is likely to clear over time. A record with an invalid schema will keep failing even after thousands of attempts. For transient errors, use bounded attempt counts, increasing wait intervals, and jitter so multiple consumers do not hammer an overloaded service simultaneously.

Example exponential backoff:

    Attempt 1: failed
       |
       +-- wait 1 second
    Attempt 2: failed
       |
       +-- wait 2 seconds
    Attempt 3: failed
       |
       +-- wait 4 seconds
    Limit reached -> DLT / recovery workflow

Avoid infinite retries and avoid stacking multiple retry layers without calculating total duration. For instance, an HTTP client retrying 3 times inside a listener while the Kafka listener also retries 5 times can produce far more service calls than intended. Define total retry budgets, timeouts, and event processing deadlines.

### 6.2. Blocking Retry with DefaultErrorHandler

Spring Kafka provides DefaultErrorHandler so the container retries records on the current processing thread. This fits when partition ordering must be preserved and retry durations are short. While waiting, the partition/consumer can be affected by handling the failing record; do not use very long backoffs without evaluating the impact on poll intervals, throughput, and rebalances.

Example configuration with three retries after the initial attempt, spaced one second apart, before moving the record to a DLT:

    @Bean
    DefaultErrorHandler kafkaErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(kafkaTemplate);

        DefaultErrorHandler handler =
                new DefaultErrorHandler(recoverer, new FixedBackOff(1_000L, 3L));

        // Data errors that cannot be fixed by retries go straight to the recoverer.
        handler.addNotRetryableExceptions(IllegalArgumentException.class);

        return handler;
    }

This example assumes the application configured compatible serializers/deserializers and that the DLT topic can accept records. The default recoverer typically routes to a topic suffixed with .DLT while preserving the corresponding partition; ensure the DLT exists and has enough partitions for the routing used. You can customize the destination resolver to route by error type or topic type.

When a record is sent to the DLT, ensure publishing to the DLT succeeds before treating the original record as recovered. If sending to the DLT fails, the system must preserve the ability to retry and raise an alert; never silently discard the original record.

### 6.3. Non-blocking Retry with @RetryableTopic

For errors needing longer waits or when you do not want to block the main partition during backoff, Spring Kafka supports retry topics via @RetryableTopic. Failed records move through retry topics on a backoff schedule; once attempts are exhausted, the record goes to the DLT.

    @RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 1_000, multiplier = 2.0),
        dltTopicSuffix = ".DLT"
    )
    @KafkaListener(topics = "orders", groupId = "order-processor")
    public void consume(OrderCreated event) {
        orderService.process(event);
    }

This is an illustrative example; configure retry/DLT topics, serializers, and listeners to match your project's Spring Kafka version. attempts represents the number of deliveries/attempts per annotation semantics; verify how attempts are counted and how topics are created in the library version you run.

Retry topics free the main stream while waiting, but can alter processing order. For example, record A for an order fails and moves to a retry topic while record B for the same order is processed immediately on the main topic. When A returns later, B may already have been applied before A. If business logic requires strict ordering per key, consider short blocking retries, aggregate versioning/sequencing, or a key-based coordination mechanism.

Do not configure multiple retry mechanisms simultaneously for the same error unintentionally. Pick one primary strategy, define the total attempt count, and specify where records land after retries are exhausted.

### 6.4. Dead-letter Topic and Recovery

A DLT holds records that could not be processed after the retry policy. A DLT isolates bad records from the main stream, but does not automatically fix data or guarantee the record will be reprocessed.

A DLT workflow should retain enough context for investigation:

- Original payload and key, along with source topic, partition, and offset.
- eventId, timestamp, and correlation ID if present.
- Last exception, root cause, and attempt count.
- Retry/DLT headers added by Spring Kafka.
- Time when the record moved to the DLT.

Operational procedures typically include: alerting on DLT growth, triaging errors, identifying root cause, fixing data or code, and performing controlled re-drive. When replaying, keep the original eventId so idempotent consumers recognize duplicates. Avoid replaying the entire DLT at once if downstream dependencies are still overloaded.

## 7. Reference Spring Kafka Configuration

A baseline configuration for a flow prioritizing durability and at-least-once processing can start as follows:

    spring:
      kafka:
        producer:
          acks: all
          properties:
            enable.idempotence: true
        consumer:
          enable-auto-commit: false
        listener:
          ack-mode: record

Meaning of these choices:

- Producer waits for ISR acknowledgements and uses idempotence to avoid duplicates from protocol retries.
- Consumer does not auto-commit offsets on a schedule independent of the listener.
- Container commits offsets after the listener processes a record successfully.
- If the listener fails, the error handler decides whether to retry, recover, or route to DLT.
- The consumer handler still must be idempotent because failure can occur after side effects complete but before the offset commits.

This is a starting point, not a complete configuration for every system. Adjust replication factor, min.insync.replicas, retention, timeouts, concurrency, poll settings, and retry policies according to load, record size, SLAs, and Kafka/Spring Kafka versions. Broker and topic settings must be applied at the proper layer; setting a Spring Boot property does not automatically alter cluster configuration.

## 8. Monitoring Reliability in Operations

To detect message loss, duplicates, and abnormal retries early, monitor producers, brokers, consumers, and DLTs together.

**Producer**

- Send error rate and retry counts.
- Send latency, request timeouts, and buffer exhaustion.
- Successfully sent records compared against expected events emitted by the application.

**Broker**

- Under-replicated partitions and offline partitions.
- ISR shrinks/expands, request errors, and disk health.
- Replication lag and controller/leader election state.

**Consumer**

- Consumer lag by group, topic, and partition.
- Processing rate, per-record processing time, and rebalance counts.
- Exception rate, retries, commit failures, and records awaiting processing.

**Retries and DLT**

- Records entering each retry topic and DLT.
- Age of the oldest record in the DLT.
- Retry success rate, exhausted retries, and re-drive counts.
- Events rejected due to non-retriable data errors.

Logs should contain eventId, topic, partition, offset, key, consumer group, attempt, and correlation ID to link attempts. Avoid writing sensitive payloads to logs. A metric showing "consumer lag equals 0" does not prove zero message loss: records may have been committed too early or expired past retention. Reconcile input event counts, business outcomes, send failures, and DLT counts.

## 9. Scenarios to Simulate in Test Environments

When building operational procedures, simulate critical failure windows and verify business outcomes:

1. Producer sends a record and loses connection before receiving ACK: verify retries and idempotent producer.
2. A partition leader broker stops right after a write: verify ISR, replication factor, and acknowledgement level.
3. Consumer stops before database commit: the record must be redeliverable.
4. Consumer stops after database commit but before offset commit: the record may be redelivered, yet the business change must not be duplicated.
5. Dependent service times out briefly: retries must recover without creating load spikes.
6. Record with invalid schema: no infinite retries; record must reach DLT or designated error-handling flow.
7. DLT unavailable: original record must not be marked successfully recovered while the failed record cannot be stored.
8. Consumer down longer than retention: verify detection and recovery workflow from another durable source if required by the business.

These scenarios help operations teams validate assumptions about offsets, transactions, and retries before deploying to production.

## 10. Decision Guidelines by Business Requirement

| Requirement | Design to consider |
|---|---|
| Do not lose records on single-broker failures | acks=all, proper replication factor, min.insync.replicas, and safe leader election |
| Do not lose work on consumer restarts | Disable auto commit; commit after successful processing |
| Tolerate redelivery without applying business effects twice | At-least-once and idempotent consumer keyed by eventId |
| Consume and produce back to Kafka atomically | Kafka transactions and read_committed consumers |
| Write to database and emit events | Transactional Outbox |
| Consumer receives events and updates a database | Inbox/dedup in the same database transaction as business changes |
| Short-lived dependency errors | Blocking retries with bounded backoff |
| Long retry waits without holding the main stream | Retry topics, while assessing ordering impact |
| Unprocessable records | DLT, alerting, investigation, and controlled re-drive |

Spring Kafka reliability comes from properly aligning acknowledgement milestones, replication, offset commits, idempotency, and retries. Choose semantics based on the business consequences of losing or duplicating events, then design consumers and operational procedures to handle the remaining failure windows.