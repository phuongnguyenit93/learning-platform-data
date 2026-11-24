# Replaying from DLT Back to the Source Topic

In Spring Kafka, a Dead Letter Topic (DLT) stores records that the main processing flow could not complete after retries or that were classified as non-retryable. Moving a record to the DLT lets the main consumer keep running, but **does not mean the business issue has been resolved**. After finding and fixing the root cause, operations may need to **replay from the DLT back to the source topic** to reprocess the quarantined records.

Replay is a controlled workflow: pick the right records, verify eligibility, publish them back to the source topic, track processing outcomes, and ensure traceability. It differs from simply altering a consumer group's offsets or restarting a listener. Specifically, publishing back to the source topic successfully **does not prove** the business listener processed the record successfully.

## 1. Where does the DLT fit in the processing lifecycle?

A common topology uses `DefaultErrorHandler` and `DeadLetterPublishingRecoverer` to move failed records from the source topic to a DLT. With `@RetryableTopic`, a record may pass through one or more retry topics before reaching the DLT. The DLT topic name depends on configuration: for instance, `orders.DLT` when using a resolver like `record.topic() + ".DLT"`, or a differently suffixed name in retry-topic infrastructure. Do not assume every application follows the same naming convention.

```text
Producer
   |
   v
orders (source topic)
   |
   v
Spring Kafka listener
   |
   +---- processing succeeded --------------> end
   |
   +---- error ----> retry / error handler
                           |
                      retries exhausted / fatal
                           |
                           v
                     orders.DLT
                           |
                     fix root cause
                           |
                     approve replay
                           |
                           v
                    replay publisher
                           |
                           v
                     orders (source topic)
                           |
                           v
                    listener reprocesses
```

In the standard branch, a DLT is an independent Kafka topic with its own partitions and offsets. When a record is published to the DLT, it receives a new offset **inside the DLT**, rather than keeping its physical offset from the source topic. After replaying back to `orders`, the broker assigns yet another new offset in `orders`. These two appearances are linked by business metadata and provenance headers, not by reusing old offsets.

## 2. How replay differs from retry, reprocessing, and offset reset

| Mechanism | Record source | Purpose | Notes |
|---|---|---|---|
| Blocking retry | Record currently handled by error handler | Retry recoverable errors | Can stall partition and raise lag |
| Non-blocking retry | Spring Kafka retry topics | Defer processing without blocking main topic | Can alter processing order |
| DLT replay | A record already sitting in the DLT | Return a quarantined record to the business flow | Requires approval, limits, and idempotency |
| Consumer offset reset | Topic log read by a consumer group | Make the group re-read from an earlier offset | Affects the entire range of records, not just DLT records |
| Compensating event | New event per business contract | Correct state via an intentional action | Does not necessarily match original payload |

For example, `orders` has progressed from offset 500 to 2,000, while one failed record at offset 530 was sent to `orders.DLT`. Resetting the group offset back to 530 would make the listener re-read **thousands of other records**, risking duplicate side effects. Replaying only the corresponding record from the DLT limits the blast radius, though you must still control duplicates and business ordering.

Do not use offset resets as a default substitute for DLT replay. If an entire range of data must be re-emitted, that is a backfill/reprocessing task requiring its own plan.

## 3. Mandatory prerequisites before replaying

Replay must start with the **root cause**. If the payload is malformed or the event version is unsupported by the consumer, republishing the same raw bytes back to the source topic usually just creates another failed record that returns to the DLT.

Before authorizing a record for replay, confirm:

1. **The root cause is understood:** schema error, data issue, dependency failure, application bug, or security config.
2. **The fix is ready:** consumer is patched, dependency has recovered, or payload is transformed via an approved procedure.
3. **Business impact is assessed:** the record may have already produced partial side effects; replay must not generate duplicate transactions/invoices/notifications.
4. **Correct topic and owner:** verify DLT, source topic, environment, cluster, group, and owning service.
5. **Explicit scope:** list of event IDs or `DLT topic + partition + offset` coordinates, time window, count, filter criteria.
6. **Rollback or re-handling plan:** if replay fails again, know where the record will go and who handles it.
7. **Rate limiting:** avoid flooding hundreds of thousands of old records into the main topic while the service is under heavy live load.

A record that failed due to a newer schema version may succeed once the consumer is upgraded. Conversely, a record rejected by an immutable business rule may need to be closed as a business outcome rather than replayed.

## 4. Finding the original record from DLT metadata

`DeadLetterPublishingRecoverer` normally attaches headers containing source and exception info, such as original topic, partition, offset, timestamp, and error attributes. In Spring Kafka, the `KafkaHeaders.DLT_*` constant group supplies the corresponding header names, such as `KafkaHeaders.DLT_ORIGINAL_TOPIC`, `KafkaHeaders.DLT_ORIGINAL_PARTITION`, and `KafkaHeaders.DLT_ORIGINAL_OFFSET`. Specific headers and metadata retention counts can vary across versions and recoverer configurations.

A DLT record can be described as:

```text
DLT record:
  topic:     orders.DLT
  partition: 2
  offset:    730
  key:       order-12345

Original metadata (headers):
  original topic:     orders
  original partition: 2
  original offset:    530
  exception class:    ...InvalidOrderPayloadException

Business metadata:
  event-id:           evt-9b62
  correlation-id:     request-2187
```

In the example, `orders.DLT` partition 2 offset 730 is the **record's position in the DLT**, whereas `orders` partition 2 offset 530 is where the failure originated. To pick the right record to replay, use the DLT coordinates or a verified business event ID. Never treat the source offset as if it were the offset inside the DLT.

If a custom recoverer does not produce source headers, the application needs its own provenance mechanism. Do not guess the source topic from an arbitrary DLT name and publish without checking a whitelist; a replay job must protect against writing to the wrong topic, cluster, or environment.

## 5. Choosing a replay strategy

Three common approaches:

| Strategy | How it works | When suitable |
|---|---|---|
| Replay one record / approved list | Job reads specific DLT coordinates, validates, and republishes | Small incidents needing tight per-event control |
| Replay a DLT range | Job reads an offset range, applying filters and rate limits | Large backlogs once safe conditions are established |
| Dedicated replay consumer | Listener on DLT started on demand with an approval policy | Frequent recurring operations with a dedicated owner |

Do not create an always-on `@KafkaListener(topics = "orders.DLT")` that automatically republishes **every record** back to `orders`. When the root cause is not yet fixed, records bounce from the main topic to the DLT and back again, forming a **poison message loop**.

For workflows requiring tight control and auditing, a job executing against an approved list of DLT partitions/offsets is usually easier to verify than a consumer that automatically replays everything.

## 6. Spring Kafka example: replaying a single selected record

The example below shows a `DltReplayService` reading a DLT coordinate supplied by an operational workflow, confirming the original topic is `orders`, capping replay attempts, and republishing the **raw payload bytes**. Reading raw bytes avoids deserializing a payload that previously failed; however, it is only safe if the DLT contains bytes matching the format expected by the source topic's consumer.

First, create a `ConsumerFactory<String, byte[]>` dedicated to the DLT reading job. This consumer disables auto-commit; in practice, the example uses bootstrap and connection settings provided by Spring Boot:

```java
@Bean("dltReplayConsumerFactory")
ConsumerFactory<String, byte[]> dltReplayConsumerFactory(
        KafkaProperties kafkaProperties) {

    Map<String, Object> props =
            new HashMap<>(kafkaProperties.buildConsumerProperties());

    props.put(ConsumerConfig.GROUP_ID_CONFIG, "orders-dlt-replay-admin");
    props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
    props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class);
    props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
            ByteArrayDeserializer.class);

    return new DefaultKafkaConsumerFactory<>(props);
}
```

Across Spring Boot versions, the API for building consumer properties from `KafkaProperties` may also accept SSL bundles; use the overload appropriate for your version. The `KafkaTemplate<String, byte[]>` used for replay must have `StringSerializer` for keys, `ByteArraySerializer` for values, the right cluster bootstrap/ACLs, and appropriate producer durability.

A service using `assign()` and `seek()` to target coordinates **inside the DLT**, rather than standard consumer group assignment. The code below assumes DLT coordinates were approved by an operator through an external approval workflow:

```java
@Service
public class DltReplayService {

    private static final String DLT = "orders.DLT";
    private static final String ORIGINAL = "orders";
    private static final int MAX_REPLAY_COUNT = 2;

    private final ConsumerFactory<String, byte[]> consumerFactory;
    private final KafkaTemplate<String, byte[]> kafkaTemplate;

    public DltReplayService(
            @Qualifier("dltReplayConsumerFactory")
            ConsumerFactory<String, byte[]> consumerFactory,
            KafkaTemplate<String, byte[]> kafkaTemplate) {
        this.consumerFactory = consumerFactory;
        this.kafkaTemplate = kafkaTemplate;
    }

    public void replayApproved(int dltPartition, long dltOffset)
            throws Exception {

        // Caller must verify permissions, change ticket, and approved coordinates.
        if (dltPartition < 0 || dltOffset < 0) {
            throw new IllegalArgumentException("Invalid DLT position");
        }

        TopicPartition source = new TopicPartition(DLT, dltPartition);

        try (Consumer<String, byte[]> consumer =
                     consumerFactory.createConsumer()) {

            consumer.assign(List.of(source));
            consumer.seek(source, dltOffset);

            ConsumerRecord<String, byte[]> selected = null;

            // Bounded poll; if record was removed by retention/compaction,
            // never silently pick another offset instead.
            for (int pollIndex = 0;
                    pollIndex < 5 && selected == null;
                    pollIndex++) {

                ConsumerRecords<String, byte[]> records =
                        consumer.poll(Duration.ofSeconds(2));

                for (ConsumerRecord<String, byte[]> record :
                        records.records(source)) {
                    if (record.offset() == dltOffset) {
                        selected = record;
                        break;
                    }
                }
            }

            if (selected == null) {
                throw new IllegalStateException("DLT record unavailable");
            }

            Header originalTopicHeader = selected.headers().lastHeader(
                    KafkaHeaders.DLT_ORIGINAL_TOPIC);

            if (originalTopicHeader == null) {
                throw new IllegalStateException("Missing origin header");
            }

            String originalTopic = new String(
                    originalTopicHeader.value(), StandardCharsets.UTF_8);

            if (!ORIGINAL.equals(originalTopic)) {
                throw new IllegalStateException("Unexpected original topic");
            }

            int previousReplayCount = replayCount(selected.headers());
            if (previousReplayCount >= MAX_REPLAY_COUNT) {
                throw new IllegalStateException("Replay limit reached");
            }

            Headers replayHeaders = new RecordHeaders();
            // Copy only business headers on the allowlist.
            for (Header header : selected.headers()) {
                if (header.key().equals("event-id")
                        || header.key().equals("x-correlation-id")
                        || header.key().equals("content-type")) {
                    replayHeaders.add(header.key(), header.value());
                }
            }

            replayHeaders.add("x-replay-count", Integer.toString(
                    previousReplayCount + 1).getBytes(StandardCharsets.UTF_8));
            replayHeaders.add("x-replay-source", (
                    DLT + ":" + dltPartition + ":" + dltOffset)
                    .getBytes(StandardCharsets.UTF_8));

            ProducerRecord<String, byte[]> outgoing = new ProducerRecord<>(
                    ORIGINAL, null, selected.key(), selected.value(),
                    replayHeaders);

            // Consider republish successful only after broker acknowledgement.
            kafkaTemplate.send(outgoing).get(30, TimeUnit.SECONDS);

            // Write audit result to an operations system outside this example.
            // No DLT offset commit: job reads by selected coordinates.
        }
    }

    private int replayCount(Headers headers) {
        Header value = headers.lastHeader("x-replay-count");
        if (value == null) {
            return 0;
        }
        try {
            int count = Integer.parseInt(
                    new String(value.value(), StandardCharsets.UTF_8));
            if (count < 0) {
                throw new IllegalArgumentException("Negative replay count");
            }
            return count;
        }
        catch (NumberFormatException ex) {
            throw new IllegalArgumentException("Invalid replay count", ex);
        }
    }
}
```

This is an example of the **read and publish step**, not a complete approval system. An endpoint or job invoking `replayApproved()` must enforce authentication, authorization, an approval record, total record caps, and an audit trail. Never expose this method directly via an unprotected public API. Do not share a single `KafkaConsumer` across multiple threads; each job or worker must own its own consumer.

The example does not specify a destination partition when constructing `ProducerRecord`. The Kafka producer may pick the partition according to the key and configured partitioner. This **does not guarantee** the record is replayed into the same initial partition. If preserving the original partition is required, read the source partition header, confirm the destination partition is still valid, and explicitly evaluate ordering effects. Regardless of partition, the offset assigned on the source topic during replay is still a **new offset**.

Required class imports include Kafka client (`Consumer`, `ConsumerRecord`, `ConsumerRecords`, `ProducerRecord`, `TopicPartition`, `Header`, `Headers`, `RecordHeaders`, `ConsumerConfig`, deserializers), Spring Kafka (`ConsumerFactory`, `DefaultKafkaConsumerFactory`, `KafkaTemplate`, `KafkaHeaders`), Java (`Duration`, `TimeUnit`, `StandardCharsets`, collections), and Spring annotations. If the application uses a schema registry or special serializers, adapt the read/write configuration accordingly rather than assuming payloads are always plain JSON.

## 7. Replaying a whole batch or large backlog

Replaying a single record is the building block for replaying an approved list. For large backlogs, do not open a new consumer for every record; use a dedicated consumer that reads approved ranges sequentially, with checkpointing and resume capability.

Batch replay design must handle:

- **Scope:** DLT topic, partitions, offset ranges, or event ID set; exception class/schema criteria.
- **Checkpoint:** job's own progress, never conflated with the business consumer group's committed offsets.
- **Pacing:** records/sec rate, in-flight request count, limits per partition and downstream capacity.
- **Selection:** ineligible records must be recorded as skipped with a reason, not silently ignored.
- **Failure:** if publish fails, stop or retry with backoff; never mark succeeded before broker ack.
- **Resume:** recover after crashes from a safe checkpoint; accept potential duplicates and rely on idempotency.
- **Audit:** approver, change ID, approved count, succeeded/failed/skipped counts, timestamps, and new offset mappings.

A reliable checkpoint should correspond to DLT coordinates actually published successfully. If the checkpoint is saved after broker ack, a crash between those two steps can republish the record upon resume. If the checkpoint is saved before broker ack, there is a risk of marking it done when the broker never received it. With two separate storage systems, there is no default atomicity; design for at-least-once and deduplication.

## 8. Controlled replay listener pattern

If an organization frequently sees large backlogs, you can create a dedicated listener reading the DLT that **does not start automatically**. Implement approval/filtering/checkpointing before enabling it, because the listener sees records according to its own consumer group's progress and does not automatically know which records were approved.

```java
@KafkaListener(
        id = "ordersDltReplayListener",
        topics = "orders.DLT",
        groupId = "orders-dlt-replay-operator",
        containerFactory = "dltReplayListenerContainerFactory",
        autoStartup = "false")
public void replayDltRecord(
        ConsumerRecord<String, byte[]> record,
        Acknowledgment acknowledgment) throws Exception {

    // Verify approval/eligibility and replay count before publishing.
    // After republishing, wait for broker ack before acknowledging the DLT.
    // When not approved: do not ack to silently skip.
}
```

This is a **listener skeleton, not an implementation ready to switch on**. The factory needs a suitable ack mode, such as `MANUAL_IMMEDIATE`, and publishing must check results. When starting the listener, bound partitions or offset ranges if selective replay is needed. `autoStartup=false` only stops the container from starting on application boot; it does not provide an approval workflow, pause/resume, offset boundaries, or replay caps.

With `KafkaListenerEndpointRegistry`, the application can fetch the container by listener ID to `start()` or `stop()` via an authenticated admin action. Stopping the container does not roll back already-published records. When using a dedicated replay consumer group, that group's committed DLT offset only reflects DLT reading progress—it does not prove the business consumer processed the replayed record successfully.

## 9. Avoiding infinite replay loops

A record can move from the DLT back to the source topic and fail again. If DLT replay runs automatically without bounds, records can cycle endlessly:

```text
orders -> orders.DLT -> orders -> orders.DLT -> ...
```

This loop inflates broker record counts, consumer lag, storage costs, logs, and DLT backlogs. Even with an idempotent producer, publishing a new record can still be accepted by Kafka as a **new valid record**; an idempotent producer does not stop business replay loops.

Apply defense in depth:

1. **Replay only once the root cause is fixed**, with evidence from testing a small sample.
2. **Cap replay attempts:** use a header or durable metadata like `x-replay-count`; avoid resetting the count when a record returns to the DLT.
3. **Use business idempotency keys:** stable event IDs, unique constraints, or inbox tables to avoid duplicate side effects.
4. **Have a final quarantine:** records exceeding the replay cap must stop in a manual-handling area rather than being sent back to the source topic.
5. **Add rate limits and circuit breakers:** pause the job if error rates on the source topic/DLT climb again.
6. **Track provenance:** record DLT coordinates and replay attempts to distinguish original records from replayed ones.

The `x-replay-count` header in the example only helps if the pipeline preserves that header when the record re-enters the DLT. If a serializer, mapper, or recoverer strips headers, the replay count could reset to 0. For critical workflows, store replay history in a governance datastore keyed by stable event ID for durable bounds across publishes.

## 10. Idempotency: replay does not mean exactly-once processing

For instance, a `PaymentCaptured` record wrote to the database, then the listener crashed before committing the offset. Later the record was retried and routed to the DLT due to a downstream step failing. If replayed unconditionally, updating balances or generating invoices could run a second time.

Consumer design must handle duplicates based on business IDs:

```text
event-id: evt-9b62
       |
       v
BEGIN DB TRANSACTION
       |
       v
INSERT INTO inbox(event_id)
       |
       +-- unique constraint conflict --> already processed, exit safely
       |
       v
Perform business update
       |
       v
COMMIT DB TRANSACTION
```

Inserting the event ID into the inbox must happen in the **same database transaction** as the protected side effect. Recording only in an ephemeral cache is insufficient. If one event triggers multiple side effects across external systems outside the database, design separate idempotency per system or appropriate orchestration.

Even the replay job itself must avoid unintended re-emissions. Use a replay job ID and `(DLT topic, partition, offset)` key in audits/checkpoints to track which records were requested for replay. Still, if Kafka publishing and audit writing sit in separate transactions, a crash window exists. Operators should assume **at-least-once republish** unless specific transactional/outbox mechanisms are built.

## 11. Do Kafka transactions solve everything?

Kafka transactions can make writing multiple records and committing a consumer group's offsets atomic **within Kafka's scope**, when producers, consumers, and the transaction manager are configured properly. A transactional replay consumer can publish a record back to the source topic and commit the replay group's DLT offset in the same Kafka transaction.

However, this transaction does not automatically encompass the outcome of the business listener on the source topic, databases, HTTP APIs, or an external audit store. Downstream consumers still need idempotency and failure-handling policies.

With a job reading DLT coordinates manually via `assign()` as in the example above, no group offset commit is tied to the job; to use Kafka transactions, design a consume-transform-produce flow with group assignment, offsets sent into the transaction, and a transactional producer. Do not merely add `@Transactional` and assume all Kafka and database operations become atomic automatically.

## 12. Headers, schemas, keys, and partitions during replay

When returning data from the DLT to the source topic, decide **what to keep** and **what to drop**:

| Element | Usually suitable handling |
|---|---|
| Business event ID | Keep intact for consumer deduplication |
| Kafka record key | Keep if key-based partition routing is needed |
| Payload | Keep raw bytes if valid after consumer fix; if transformed, version/audit explicitly |
| Correlation ID | Keep to link original trace and replay |
| Exception stack trace in DLT headers | Do not copy back to the main topic automatically if unnecessary |
| Original topic/partition/offset | Keep in audit or controlled provenance headers |
| Replay attempt/count | Increment per policy and preserve across recoveries |
| Kafka timestamp | Replay gets a new write timestamp; do not assume original timestamp is preserved |
| Original partition | Reuse only when compatible with partition count, key distribution, and ordering needs |

The example code uses a business-header allowlist instead of copying every DLT header. Retaining error headers from multiple retry/replay cycles can bloat headers and leak stack traces or sensitive details into the main topic.

**Be careful with deserialization failures:** a DLT record produced by `ErrorHandlingDeserializer` may contain raw bytes that never deserialized, whereas a DLT record from a listener exception may hold a value re-encoded by `KafkaTemplate`'s serializer. Before replaying, verify the stored payload is genuinely compatible with the source topic's consumer. Do not look solely at the DLT object's Java type and assume its bytes are safe to publish.

If a payload requires modification, prefer creating a new event conforming to a valid contract/schema and storing a mapping from the new event back to the old DLT record. Never silently edit emitted content without an audit trail, especially for financial or audited events.

## 13. Ordering and impact on business flows

Replaying from a DLT back to the source topic always appends **a new record at the end of the destination partition's log**. It does not insert the record back into its historical slot ahead of records already processed.

Example:

```text
orders partition 2:
  offset 530: OrderCreated  ---> failed, moved to DLT
  offset 531: OrderPaid     ---> processed on main topic
  offset 532: OrderShipped  ---> processed on main topic
  ...
  offset 940: replay OrderCreated
```

If `OrderPaid` or `OrderShipped` requires `OrderCreated` to be applied first, appending at the end of the log cannot restore the original business sequence. The system must pick an explicit strategy: process events with a version-checked state machine, hold records awaiting dependencies, execute compensation, or use a dedicated reprocessing flow preserving required ordering.

Keeping the Kafka record key lets the partitioner route records with the same key to the same partition, yet **does not restore the old offset** and does not eliminate the problem of an older event arriving after newer events. With different producer configurations or changed partition counts, the same key could even land on a different partition. Verify in the actual environment.

## 14. Controlled replay with canary and rate limiting

With a large DLT backlog, a sudden mass replay can overload the main consumer and downstream dependencies, causing more exceptions and pushing many records back to the DLT. Execute in stages:

1. Select a few representative records by exception class, schema version, and failure timestamp.
2. Replay in a staging environment or compatible canary stream if possible.
3. Replay a small batch in production, monitoring side effects and DLT re-entry.
4. Ramp up gradually within the throughput capacity of consumers, databases, and downstream APIs.
5. Automatically pause if error rate, lag, latency, or DLT re-entry exceeds thresholds.
6. After completing the batch, reconcile the approved list against successful publishes and business outcomes.

Crucially, do not use producer send success rate as the sole gauge. A producer can emit 10,000 records/sec while the business consumer only handles 1,000 records/sec and the DLT keeps growing. Coordinate rate limits with lag and real downstream capacity.

## 15. Replay observability and auditing

An operational dashboard should separate three outcome layers:

- **Replay requested/approved:** count of records approved or scheduled.
- **Replay published:** count of records confirmed by brokers as written back to the source topic.
- **Business reprocessed:** count of records actually completed by the business listener after replay.

Additional metrics include publish errors, replay throughput, latency from DLT to source topic, records returning to the DLT after replay, records exceeding the replay cap, source topic consumer lag, and downstream health. Log/audit each record with DLT topic/partition/offset, original topic/partition/offset, event ID, replay job ID, operator/change ID, publish timestamp, new result topic/partition/offset, and reconciliation status when available.

Do not use individual event IDs or offsets as metric labels due to high cardinality. Keep them in controlled audit logs or traces. Avoid exposing sensitive payloads or stack traces on dashboards.

An audit table might look like:

| Field | Meaning |
|---|---|
| `job_id` | Replay batch and approver |
| `dlt_topic`, `dlt_partition`, `dlt_offset` | Selected DLT coordinates |
| `event_id` | Stable business key |
| `target_topic` | Topic republished to |
| `replayed_partition`, `replayed_offset` | Coordinates returned by broker after republish |
| `status` | Approved, published, failed, skipped, verified |
| `reason` | Reason for replay or rejection |

To conclude a record was processed in business terms, reconcile against the transaction/inbox database, outcome events, or meaningful business metrics—not solely against producer acknowledgements.

## 16. Common operational failures

| Symptom | Common cause | Action |
|---|---|---|
| Record returns to DLT after replay | Root cause not fixed or payload still incompatible | Stop replay, inspect the new exception, and test one record |
| One event causes side effects twice | Consumer not idempotent or job republished after crash | Preserve event ID, use inbox/unique constraint, audit replay requests |
| Replay job targets wrong topic | Trusting unverified headers or wrong environment | Whitelist target topics, check cluster, ACLs, and approvals |
| Record not found at DLT offset | Retention/compaction removed it or wrong partition/offset | Verify coordinates; never substitute the next record |
| Replay emits wrong format | DLT value was encoded by a different serializer; schema unpatched | Inspect raw bytes/schema and serializer/deserializer config |
| Replay disrupts processing order | Old record appended at end of topic | Use state versions, compensation, or an ordering-aware workflow |
| DLT grows during replay | Replay loop, excessive throughput, or consumer still failing | Apply rate limits, circuit breaker, replay cap, stop batch |
| Published successfully yet no business outcome | Main consumer lagging, failing again, or workflow incomplete | Check consumer group, business outcomes, and DLT re-entry |
| DLT replay listener skips unapproved records | Listener auto-acks/commits before durable filter state | Use coordinate-based jobs or audited checkpoint/skip policies |
| Job restart causes duplicate replays | Checkpoint and Kafka publish are non-atomic | Design for at-least-once, deduplication, and controlled resume |

When investigating, start with DLT coordinates and event ID to reconstruct the record's path across source topic, retry topics, DLT, and replay. Verify exactly which records were published after each batch rather than relying solely on aggregate counts.

## 17. Testing the replay flow

Before taking replay tooling to production, test at least these scenarios:

1. **Valid record after fix:** route to DLT, fix consumer, replay, and verify business processing succeeds.
2. **Error still persists:** replay a poison record, verify replay cap/quarantine or circuit breaker stops the loop.
3. **Duplicate request:** same DLT partition/offset requested twice; verify audit and business prevent duplicate side effects.
4. **Publish failure:** missing write ACL or broker timeout; job does not record published success before broker ack.
5. **Crash after publish:** stop process right after broker receives record but before checkpoint save; verify resume does not corrupt business state.
6. **Missing original topic header:** job rejects or routes to manual handling; never guesses a destination topic.
7. **Deserialization-failed payload:** verify raw bytes/schema are handled properly or blocked safely.
8. **Ordering conflict:** replay an older event after a newer event and verify state versions/business rules protect correctness.
9. **DLT retention:** expired offset is never silently substituted with the next record.
10. **Large backlog:** rate limiting, lag/DLT re-entry monitoring, and pause/resume work properly.

Tests should assert both Kafka details (key, headers, partition, offset) and business state. For transactional or outbox replays, add transaction-abort and job-retry scenarios.

## 18. Safe replay runbook

An on-call operational procedure can follow this sequence:

1. **Detect:** DLT growth alert fires or downstream reports an incident.
2. **Triage:** group records by exception, producer version, schema, and impacted system.
3. **Remediate:** fix code, data, dependency, ACL, or schema; validate with one representative record.
4. **Approve:** lock scope of DLT topic/partition/offset or event IDs, owner, and replay batch limits.
5. **Prepare:** verify target topic, ACLs, serializers, retention, idempotency, ordering, and downstream capacity.
6. **Canary:** replay a handful of records, watch DLT re-entry and business outcomes.
7. **Execute:** run the batch with rate limits and checkpoints, never expanding beyond the approved list.
8. **Monitor:** track published count, business processed count, lag, exception rate, and replay loops.
9. **Reconcile:** determine how many records succeeded, still failed, or need manual intervention.
10. **Close incident:** archive job ID, new offset mappings, root cause, timeline, and preventive actions.

If you need to stop midway, preserve job state and the list of published records. Never reset the main consumer's offset to "redo everything" unless you have an independent, approved backfill plan.

## 19. Core principles when replaying DLT to the source topic

Replay should only occur when there is a **clear business reason** and evidence that the record will fare better than in the previous failure. Use DLT metadata to pick the right records, whitelist destination topics, preserve stable event IDs and provenance metadata, cap replay attempts, and monitor outcomes all the way to business side effects.

For consistency, assume a record can be published or processed more than once across crashes, retries, and rebalances; idempotency is a foundational requirement. Operationally, treat DLT replay as a **controlled data recovery process**, not an automated listener pushing every failed record back to the main topic. Combining approvals, rate limits, auditing, testing, and reconciliation allows Spring Kafka to recover quarantined events while curbing duplicates, replay loops, and disruption to live consumers.
