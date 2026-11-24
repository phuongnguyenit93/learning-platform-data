# Dead Letter and Replay Checklist

A dead-letter topic (DLT) stores records that could not be processed under the consumer's retry policy. A DLT isolates failing records from the main stream for investigation and recovery, but sending a record to a DLT does not mean the business process is finished. Every record must be traced, classified, resolved, and replayed in a controlled way if appropriate.

In Spring Kafka, a DLT can be populated by `DeadLetterPublishingRecoverer` via an error handler or by non-blocking retries with `@RetryableTopic`. Operational procedures must cover when records enter the DLT, retention duration, ownership, replay mechanics, and safeguards against duplicate side effects.

## 1. Identify the DLT creation flow

First, document whether the listener uses blocking retries or non-blocking retries. The two mechanisms have different topologies and controls.

| Mechanism | Path | Checkpoints |
|---|---|---|
| Blocking retry with `DefaultErrorHandler` | Source topic → listener → in-container retry → recoverer → DLT | BackOff, exception classification, recoverer, and offsets |
| Non-blocking retry with `@RetryableTopic` | Source topic → backoff-level retry topics → DLT | attempts, retry topics, DLT handler, partitions, and retention |
| Dedicated recovery flow | DLT → replay worker → target topic | Access control, audit, rate limits, and idempotency |

~~~mermaid
flowchart TD
    A[Source topic] --> B[Listener]
    B -->|Success| C[Complete offset]
    B -->|Error| D[Retry policy]
    D --> E[Retry / retry topic]
    E --> B
    D -->|Retries exhausted| F[Recoverer]
    F --> G[(DLT)]
    G --> H[Investigate and classify]
    H --> I{Recoverable?}
    I -->|Yes| J[Controlled replay]
    J --> A
    I -->|No| K[Compensation / archive]
~~~

A DLT record can stem from data errors, business rule failures, prolonged dependency outages, configuration mistakes, or programming bugs. Never treat all records in a DLT as the same failure class and replay all of them with a single blanket command.

## 2. Retry and recoverer configuration checklist

For blocking retries, verify that the error handler has a recoverer publishing records to the DLT and handles publish failures properly.

~~~java
@Bean
DefaultErrorHandler ordersErrorHandler(
        KafkaTemplate<Object, Object> template) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(template);

    recoverer.setFailIfSendResultIsError(true);

    FixedBackOff backOff = new FixedBackOff(1_000L, 3L);

    DefaultErrorHandler handler =
            new DefaultErrorHandler(recoverer, backOff);

    handler.addNotRetryableExceptions(
            InvalidOrderException.class,
            UnsupportedCurrencyException.class
    );

    return handler;
}
~~~

Attach the handler to the listener container factory:

~~~java
factory.setCommonErrorHandler(ordersErrorHandler);
~~~

- [ ] Listener lets exceptions propagate to the container when retries are desired.
- [ ] Transient errors and non-retryable errors are clearly classified.
- [ ] BackOff bounds attempt counts or total duration.
- [ ] Recoverer publishes to the right target topic.
- [ ] DLT publish results are checked.
- [ ] DLT serializer supports the right key/value types and payloads.
- [ ] DLT topic is provisioned or topic creation is controlled.
- [ ] Offsets advance per policy only after the recoverer finishes.

`setFailIfSendResultIsError(true)` instructs the recoverer to fail if sending to the DLT fails rather than silently treating the record as recovered. Check the API for your Spring Kafka version. If DLT publishing fails, never let offsets advance past a record that has not been safely stored.

With `@RetryableTopic`, verify that `attempts` includes the initial attempt, backoff fits SLA, include/exclude exceptions are accurate, and the DLT handler is registered. Non-blocking retries have specific constraints on ordering, batch listeners, and container transactions; check stream requirements before choosing them.

## 3. DLT topic design checklist

A DLT is a normal Kafka topic and must be configured and operated like any other topic.

- [ ] DLT name is clear, consistent, and collision-free.
- [ ] Mapping rule from source topic to DLT is documented.
- [ ] Partition count is compatible with how the recoverer routes records.
- [ ] Replication factor meets fault-tolerance requirements.
- [ ] Retention is long enough for investigation and replay approval.
- [ ] Disk capacity is sized for payload sizes and failure rates.
- [ ] ACLs separate DLT write, DLT read, and replay administration permissions.
- [ ] A dedicated consumer group or operational tool exists for the DLT.
- [ ] Alerts trigger when the DLT receives new records or backlog grows.
- [ ] Procedures exist for archiving/deleting records after retention expires.

With the common default configuration of `DeadLetterPublishingRecoverer`, the DLT is named by appending `.DLT` to the source topic and routed to the matching partition. If using a custom destination resolver or naming strategy, verify the actual rules. If the resolver preserves partition numbers, the DLT must have matching partitions; otherwise publishing can fail because the target partition does not exist.

`@RetryableTopic` uses its own naming conventions for retry topics and DLTs. Do not assume non-blocking retry topic names match the DLT produced by the default recoverer.

## 4. Checklist of metadata to preserve

A record in the DLT needs enough information to identify its origin and decide how to recover it.

| Metadata | Purpose |
|---|---|
| Event ID | Stable business identifier for deduplication |
| Original topic | Identifies which stream the record came from |
| Original partition/offset | Traces the record's position in the original log |
| Record key | Preserves aggregate/key routing rules |
| Original timestamp | Records when the event was created |
| Consumer group/listener | Identifies the failing processing flow |
| Exception class | Classifies the failure type |
| Exception message/stacktrace | Aids investigation within security limits |
| Retry/attempt metadata | Shows which attempts the record went through |
| Correlation/trace ID | Links logs and traces across services |
| Schema/version | Deserializes payloads with the right contract version |

Spring Kafka adds DLT headers containing origin metadata and exception info depending on version and configuration. Verify that required headers survive across retry topics and recoverers.

- [ ] Event ID is not regenerated when moving a record to the DLT.
- [ ] Key is preserved if per-aggregate partitioning must be maintained.
- [ ] Original topic, partition, offset, and timestamp are queryable.
- [ ] Exception metadata does not leak secrets or sensitive data.
- [ ] Trace/correlation context is sufficient to locate logs.
- [ ] Duplicate or stale headers are handled clearly during replay.
- [ ] Payload and schema version are stored sufficiently for later deserialization.

Do not use event ID, order ID, or correlation ID as high-cardinality metric tags. These identifiers belong in logs, traces, and DLT lookup stores.

## 5. DLT consumer checklist

A dedicated listener can persist DLT records as tracked cases with state:

~~~java
@Component
public class OrdersDltListener {

    private final DltCaseService dltCaseService;

    public OrdersDltListener(DltCaseService dltCaseService) {
        this.dltCaseService = dltCaseService;
    }

    @KafkaListener(
            topics = "orders.DLT",
            groupId = "orders-dlt-operations"
    )
    public void handle(ConsumerRecord<String, OrderEvent> record) {
        dltCaseService.register(
                record.key(),
                record.value(),
                record.topic(),
                record.partition(),
                record.offset(),
                record.headers()
        );
    }
}
~~~

- [ ] DLT consumer group has a dedicated, stable ID.
- [ ] Listener stores origin metadata and event ID.
- [ ] DLT handler has appropriate timeouts and retries.
- [ ] Failures while saving cases are observed and recoverable.
- [ ] Errors in the DLT handler do not loop back into the same DLT indefinitely.
- [ ] DLT consumer can be paused if the case-management system has an outage.
- [ ] Access control and audit exist for investigators.
- [ ] DLT backlog and oldest record age are monitored.

If the DLT handler only reads and logs, logs must be durable enough and someone must be responsible for monitoring them. For critical flows, persist stateful cases instead of relying on plain text logs.

## 6. Classify records before replay

| Error category | Examples | Appropriate action |
|---|---|---|
| Transient dependency recovered | DB timeout, API 503 | Replay after verifying dependency health |
| Invalid data | Missing required field, bad format | Repair data with audit or handle via business workflow |
| Incompatible schema | Consumer cannot read payload | Deploy compatible reader before replaying |
| Business error | Order state disallows action | Verify state and decide on compensation |
| Config/permission error | ACL, credentials, topic mapping | Fix config/permissions before replaying |
| Code bug | Handler bug | Deploy fix, test, and canary replay |
| Unknown side effect | API may have executed before client timed out | Reconcile with target system before replaying |

- [ ] Root cause has been identified.
- [ ] Confirmed the error is fixed or a data remediation exists.
- [ ] Checked whether the event was partially processed before entering the DLT.
- [ ] Verified external database/API state if side effects exist.
- [ ] Assessed whether replay could create duplicates.
- [ ] Obtained approval for critical business flows.
- [ ] Recorded the rationale for choosing replay, data repair, compensation, or keeping in DLT.

Do not replay simply because a dependency came back up. A request timeout can occur after the target API already performed the business action; look up by idempotency key or transaction ID before resending.

## 7. Idempotency checklist before replay

Replaying can cause the same event to be processed again. Consumers must protect side effects with stable event IDs and idempotent operations.

- [ ] Original event ID is preserved on replay.
- [ ] Consumer has a unique constraint/inbox key for processed events.
- [ ] Deduplication marker and business update occur in the same database transaction.
- [ ] External APIs use stable idempotency keys where supported.
- [ ] Do not generate a new idempotency key for each technical replay.
- [ ] Non-idempotent actions have been checked/reconciled.
- [ ] If an intentional business re-execution is needed, issue a new audited command rather than disguising it as a technical replay.

Example inbox table:

~~~sql
CREATE TABLE processed_event (
    consumer_name VARCHAR(150) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

The key includes both consumer name and event ID so Billing, Notification, or other logical consumers can process the same event independently. Do not use a single global deduplication marker that lets one consumer accidentally block another consumer's processing.

## 8. Replay procedure checklist

Replay should be a controlled, audited, and stoppable workflow.

1. Select records by event ID, time range, partition, offset, or case ID.
2. Check the failure root cause and side-effect status.
3. Choose the target topic: original topic, retry topic, or dedicated recovery topic.
4. Verify schema, serializer, key, and headers.
5. Run a dry-run to count records and inspect sample payloads.
6. Test-replay a single record or tiny batch.
7. Verify the consumer processes successfully without duplicate side effects.
8. Scale batches up within rate limits.
9. Monitor lag, retry rate, DLT ingress, and dependency latency.
10. Halt replay if errors spike, backlog grows rapidly, or downstream saturates.
11. Record counts of succeeded, failed, skipped, and pending records.
12. Close cases and store audit trails.

- [ ] Selection criteria for records are explicit.
- [ ] Dry-run and per-batch limits exist.
- [ ] Rate limiting/throttling is enforced.
- [ ] Replay can be paused or canceled.
- [ ] Checkpointing exists to resume after a replay job stops.
- [ ] Logs capture replay ID, operator, timestamp, source/target topics, and outcome.
- [ ] Alerts trigger if replay spikes retries or new DLT entries.
- [ ] Safeguards prevent two operators from replaying the same set concurrently.

## 9. Replay with KafkaTemplate: publish and ack

A replay worker can read DLT records, republish to the target topic, and confirm the source record only after the broker acknowledges the publish.

~~~java
ProducerRecord<String, OrderEvent> replayRecord =
        new ProducerRecord<>(
                targetTopic,
                dltRecord.key(),
                dltRecord.value()
        );

replayRecord.headers().add(
        "x-replay-id",
        replayId.getBytes(StandardCharsets.UTF_8)
);

replayRecord.headers().add(
        "x-replayed-from",
        dltRecord.topic().getBytes(StandardCharsets.UTF_8)
);

kafkaTemplate.send(replayRecord)
        .get(10, TimeUnit.SECONDS);
~~~

This snippet illustrates only the publish step. A replay worker must also manage DLT offsets, send failures, header filtering, and auditing.

With a DLT listener using manual acknowledgment, do not ack the source record before the target publish is confirmed. However, if the publish succeeds and the process crashes before committing the DLT offset, the record can be replayed again. This is the duplicate window of an at-least-once workflow.

If Kafka-to-Kafka atomicity is needed, configure a transactional listener container and use the same transactional producer factory to publish the target record and commit the DLT offset within one Kafka transaction. When the transaction commits, both the replayed output and source offset take effect; when rolled back, neither commits. Test the actual configuration and configure downstream consumers with `read_committed` when aborted records must be excluded.

- [ ] Decide whether replay is at-least-once or transactional.
- [ ] Do not assume a successful send future and an offset commit form a single transaction unless configured.
- [ ] Preserve original event ID and key.
- [ ] Forward only necessary headers; strip stale error headers or unsuitable metadata.
- [ ] Add replay ID and dedicated audit metadata.
- [ ] Handle timeouts and publish failures.
- [ ] Test crashes between publish and offset commit.

## 10. Do not blindly forward all DLT headers

DLT records usually carry exception headers and origin metadata. If you replay all headers verbatim and the record fails again, old error headers may be mistaken for the new attempt or duplicated.

When replaying:

- Keep correlation ID, trace context, and event ID if still valid.
- Keep business metadata needed by the consumer.
- Move DLT origin details into clearly named audit/replay headers.
- Do not carry over old stacktraces or exception messages as if from the new attempt.
- Handle duplicate headers according to policy.
- Strip headers containing credentials, secrets, or unnecessary internal data.

Do not discard origin details before saving them to an audit record. Operators must be able to trace which DLT topic, partition/offset, and case a replayed record originated from.

## 11. Batch and rate-limit replays

A large DLT backlog can hold thousands or millions of records. Replaying everything at once can create a massive load spike on the original topic and downstream systems.

- [ ] Pick a batch size suited to payload sizes and downstream capacity.
- [ ] Cap records/second.
- [ ] Monitor consumer lag on the target topic.
- [ ] Monitor CPU, heap, database pools, and API rate limits.
- [ ] Pause replay if dependencies degrade.
- [ ] Prioritize records by SLA or business criticality.
- [ ] Do not break per-aggregate ordering if business rules require it.
- [ ] Support resuming from a checkpoint without uncontrolled redelivery.

When replaying records for the same aggregate, preserve keys and consider ordering by original timestamp/version. Kafka orders records per partition as of the new publish time; it does not re-sort historical events by old topic offsets after replay.

## 12. Monitor DLT and replay

| Metric | Meaning |
|---|---|
| DLT ingress rate | New records entering DLT over time |
| DLT backlog | Records not yet investigated/resolved |
| DLT oldest age | Age of the oldest record |
| DLT handler failures | Errors in the DLT intake pipeline |
| Replay requested | Records selected for replay |
| Replay published | Records successfully republished |
| Replay failed | Failed publish/replay attempts |
| Replay duplicate | Records replayed or deduplicated |
| Post-replay retry rate | Indicates whether the fix resolved the error |

- [ ] Dedicated dashboards exist for source topics, retry topics, and DLTs.
- [ ] Alerts exist on DLT ingress rate, backlog, and oldest age.
- [ ] Alerts trigger if the DLT handler or replay worker fails.
- [ ] Replay metrics track outcomes.
- [ ] Metric tags have bounded cardinality; do not use event IDs as tags.
- [ ] Logs include event ID, original topic/partition/offset, replay ID, and exception class.
- [ ] Trace/correlation IDs can look up related flows.
- [ ] Sensitive payloads are never written to logs or dashboards.

## 13. Retention, security, and access control

DLTs may store failing data longer than main topics. Treat them as operational data that may contain sensitive information.

- [ ] Retention aligns with investigation SLAs and replay approval windows.
- [ ] Disk limits and storage alerts are in place.
- [ ] ACLs restrict DLT reads to required services/operators.
- [ ] Replay permissions are separated from read-only inspection permissions.
- [ ] Sensitive payloads are protected by appropriate encryption/access policies.
- [ ] Logs/traces do not expose tokens, passwords, payment data, or secrets.
- [ ] Retention/deletion policies exist for DLT cases and audits.
- [ ] Each critical DLT topic has an assigned owner.

Do not delete a DLT topic or reset DLT offsets to "clear backlog" without archiving and classifying records first. If unrecoverable records must be discarded, require a business decision, audit record, and clear retention policy.

## 14. Runbook for handling a DLT record

When handling a DLT case, follow this sequence:

1. Open the case by event ID and replay ID if previously replayed.
2. Identify original topic, partition, offset, consumer group, and listener.
3. Inspect exception class, error code, and retry metadata.
4. Search logs/traces by correlation ID.
5. Check business state in the database and external systems.
6. Determine whether the issue is data, code, dependency, permissions, or config.
7. Decide to repair data, deploy a fix, wait for dependency, compensate, or replay.
8. Verify idempotency and event ordering before replaying.
9. Test-replay one record and verify final state.
10. Record the outcome and close or escalate the case.

Cases should carry states such as NEW, INVESTIGATING, READY_TO_REPLAY, REPLAYING, RESOLVED, COMPENSATED, or REJECTED. Exact state names depend on your tooling, but they must distinguish pending, under-investigation, replayed, and unrecoverable records.

## 15. Common operational mistakes

| Symptom | Possible cause | Resolution |
|---|---|---|
| Records vanish after failure | Offset committed even though DLT publish failed | Check recoverer send result and offset policy |
| DLT lacks matching partition | Resolver keeps source partition while DLT has fewer partitions | Provision matching partitions or change resolver |
| DLT backlog grows forever | No DLT consumer/owner or slow case triage | Assign owner, alerts, and runbook |
| Replay creates duplicates | Publish succeeded before DLT offset committed | Idempotency or Kafka transactions |
| Replayed records re-enter DLT | Root cause unfixed or payload still broken | Reclassify and halt automated replay |
| Out-of-order events | Batch replay did not preserve key/version/ordering | Replay per aggregate and check versions |
| DLT handler loops infinitely | Handler errors get routed back to the same DLT unbounded | Separate error handling and cap recovery |
| Duplicate error headers | Blindly forwarding all DLT headers across replays | Filter headers and store origin metadata in audit |
| Replay overloads downstream | Unthrottled or oversized batches | Rate-limit and canary replay |
| Unknown who replayed a record | Missing audit and replay ID | Log operator, reason, timestamp, and outcome |

## 16. Pre-production checklist

### Retry and DLT configuration

- [ ] Blocking vs. non-blocking retry chosen according to ordering/transaction needs.
- [ ] Retryable/non-retryable exceptions clearly classified.
- [ ] BackOff and attempts are bounded.
- [ ] Recoverer publishes to DLT and publish failures are handled.
- [ ] DLT topic has proper partitions, replication, retention, and ACLs.
- [ ] Serializers/deserializers support DLT payloads.
- [ ] Origin metadata and event IDs are preserved.

### DLT operations

- [ ] Dedicated consumer/tooling handles DLT intake.
- [ ] Owner, dashboards, alerts, and runbooks exist.
- [ ] DLT cases are classified before replay.
- [ ] Auditing exists for data repairs, replays, and compensations.
- [ ] Retention and safe archival/deletion procedures exist.

### Replay safety

- [ ] Consumers are idempotent by event ID.
- [ ] External APIs use idempotency keys where possible.
- [ ] Replay preserves keys/event IDs and forwards only needed headers.
- [ ] At-least-once vs. transactional replay semantics are defined.
- [ ] Dry-run, canary, batch sizing, and rate limits exist.
- [ ] Checkpointing, pause/stop, and resume capabilities exist.
- [ ] Duplicates, crash windows, and ordering have been tested.
- [ ] Reconciliation procedures exist for ambiguous side-effect outcomes.

## 17. DLT and replay testing checklist

Before release, test these scenarios:

1. Listener hits a retryable error and eventually succeeds.
2. Listener exhausts retries and record lands in the DLT.
3. Non-retryable exception follows the expected DLT policy.
4. DLT publish failure does not falsely mark the source record confirmed.
5. DLT handler persists the right payload, key, headers, and origin metadata.
6. Replaying a record succeeds after fixing the root cause.
7. Replaying the same event ID twice produces no duplicate side effects.
8. Process crashes after publishing replay but before committing offset.
9. Replaying many records with throttling and checkpointing.
10. A replayed record that fails again is investigated as a new case.
11. Replay preserves per-aggregate ordering when business logic requires it.
12. DLT retention, ACLs, and dashboards work properly.

For integration tests, use Embedded Kafka or Testcontainers to confirm records are actually published and consumed. Mocking the recoverer tests invocation logic, not whether topics, partitions, serializers, ACLs, or transactions work on a broker.

## 18. DLT case record template

When creating a case, capture at least:

| Field | Value to record |
|---|---|
| Case ID | Incident tracking ID |
| Event ID | Original event identifier |
| Original topic/partition/offset | Initial record position |
| DLT topic/partition/offset | Record position in the DLT |
| Consumer group/listener | Failing processing flow |
| Exception/error code | Observed failure cause |
| First failure time | Timestamp of first error |
| Last attempt time | Timestamp of final attempt |
| Retry count | Attempt count per defined semantics |
| Business impact | Impact on business operations |
| Root cause | Verified cause |
| Decision | Replay, repair, compensate, or reject |
| Replay ID/operator | Identifier and person executing |
| Result | Success, failed, duplicate, or pending |

This template keeps operators from guessing from a single log line and establishes an auditable history.

A DLT is only useful when paired with investigation and recovery workflows. Ensure records are published safely, preserve origin metadata, classify root causes before replay, verify idempotency, and throttle replay rates. With Spring Kafka, combining well-configured retries/recoverers, a dedicated DLT consumer, audits, metrics, and runbooks handles failing records responsibly without data loss or unintended duplicate business side effects.

