# Safe replay verification

Replaying in Kafka means re-reading one or more records previously processed by a consumer, typically to recover data, rebuild projections, re-run logic after a bug fix, or return records from a dead-letter topic (DLT) into processing. Replays are powerful, yet every re-read can re-trigger data mutations and external side effects. Consequently, a replay is safe only when you identify the exact data to be read, understand the logic that will run, and prove that repeated processing will not corrupt business state.

In Spring Kafka, distinguish three scenarios:

- **Retry** is re-attempting a failing delivery, usually due to transient errors like timeouts or unavailable dependencies.
- **Offset-based replay** resets a consumer group's read position to an earlier offset so the consumer re-reads records in a topic.
- **DLT replay** takes records routed to a dead-letter topic, fixes the root cause or processing condition, and re-emits them into the appropriate stream.

All three may share the same idempotency mechanisms, yet differ in data scope, ordering controls, and progress tracking.

## 1. Prerequisites to verify before replaying

A replay plan must answer these questions before consumers start reading:

| Item | What to verify |
|---|---|
| Data source | Topic, partitions, starting offset, and ending offset range are defined. |
| Consumer | Which consumer group will read; whether active consumers are running in that group; which configuration and application version will run. |
| Processing target | Whether records update business tables, projections, caches, another topic, or external services. |
| Event identity | Every event has a stable ID preserved across retries, DLT, and replays. |
| Idempotency | Receiving the same event multiple times does not produce unintended repeated business changes. |
| Ordering | Whether in-partition or per-aggregate ordering is required during processing. |
| Capacity | Replay rate fits database, downstream, and system throughput limits. |
| Stop and recovery | Stop conditions, responsible owner, and steps to return to normal operations exist. |

Never start a replay without identifying the source, scope, consumer group, or side effects. A single offset-reset command can cause an entire group to re-read massive volumes of data; picking the wrong group or topic can mutate unintended targets.

## 2. Choosing the right replay approach

Not every replay requires resetting offsets on the live production consumer group.

| Approach | When to use | Control points |
|---|---|---|
| Separate consumer group | Rebuilding projections, backfilling, or testing a dataset. | New group has independent offsets. If targeting production data, still control idempotency and side effects. |
| Resetting current group offsets | Need the production consumer to re-read a slice of data in the existing stream. | Stop all consumers in the group, preview reset output, scope strictly to intended topic and partitions. |
| DLT replay | Failed records reprocessed after fixing data or resolving a dependency. | Preserve original event ID and source metadata; prevent infinite DLT loops; track each replayed record. |
| Separate replay topic | Testing new logic or re-running data in a controlled environment. | Isolate replay target, configure permissions and rate; ensure production consumers do not accidentally pick up test records. |

A separate consumer group often fits backfills because it leaves the production group's active offsets untouched. However, a separate group does not automatically make a replay safe: if the listener writes to the same production tables or calls the same production APIs, side effects still occur. Whenever possible, test against an isolated target database or topic before promoting results to production.

## 3. Idempotency is the primary guard against duplicate processing

Kafka consumers typically operate under **at-least-once** semantics: a record can be redelivered if the application finished mutating data yet stopped before committing the offset. Intentional replays create the same repetition scenario. Never assume an event is processed only once.

Every business event should have an immutable `eventId`. The Kafka record key usually represents the aggregate or entity for partitioning and ordering; it is not necessarily the event ID. Two different events for the same order can share a Kafka key while carrying two distinct event IDs.

For database writes, a common pattern records processed markers in an inbox or deduplication table. The unique key typically combines the logical consumer name and event ID. Writing the processed marker and updating business data must share the same database transaction.

The following example uses PostgreSQL syntax to illustrate an insert with duplicate checking:

```java
@Service
public class OrderEventProcessor {

    private final JdbcTemplate jdbcTemplate;
    private final OrderProjectionRepository projectionRepository;

    public OrderEventProcessor(
            JdbcTemplate jdbcTemplate,
            OrderProjectionRepository projectionRepository) {
        this.jdbcTemplate = jdbcTemplate;
        this.projectionRepository = projectionRepository;
    }

    @Transactional
    public void applyOnce(OrderCreated event) {
        int inserted = jdbcTemplate.update(
            """
            INSERT INTO consumed_event (consumer_name, event_id, processed_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT (consumer_name, event_id) DO NOTHING
            """,
            "order-projection-v1",
            event.eventId()
        );

        if (inserted == 0) {
            // Event was already processed successfully previously.
            return;
        }

        projectionRepository.apply(event);
    }
}
```

In this example, the database needs a unique constraint on `(consumer_name, event_id)`. If updating the projection fails, transaction rollback undoes the inbox row too; the next delivery can retry. If the transaction committed yet the Kafka offset did not, the record redelivers and the insert returns `0`, so the projection is not updated a second time.

This snippet illustrates PostgreSQL; for other databases, use equivalent insert-if-absent syntax and unique constraint mechanisms. Do not implement a `SELECT` check followed by `INSERT` without a unique constraint, as two concurrent consumers can both pass the check.

### Watch out when changing logic versions

The deduplication key must reflect the exact processing scope. If `order-projection-v1` already processed all events and you want to rebuild the projection with new logic, reusing the same namespace could skip every event. Create a separate namespace like `order-projection-v2`, write to a new projection, verify it, and then switch over.

Do not bulk-delete deduplication data just to make a replay run again. Doing so can re-trigger side effects of already-processed events, such as sending emails, charging payments, or creating shipments. For payment commands or external APIs, use provider-supported stable idempotency keys or design reconciliation before resending requests.

## 4. Controlling offsets and consumer groups

An offset is a consumer group's read position per partition. Resetting offsets changes the next position the group will read; it does not delete records from the topic and does not undo side effects already applied to databases or external systems.

### Re-reading with a separate group

For a brand-new group, `auto.offset.reset=earliest` lets the consumer start from the earliest retained record when the group has no valid committed offset yet. This property does **not** automatically rewind a group that already has committed offsets. If the group already has offsets, the consumer resumes from the committed offset.

Assigning a dedicated group ID per controlled backfill helps track offsets and lag independently. Record the group ID, topic, start time, `auto.offset.reset` setting, application version, and data target so outcomes can be explained afterward.

### Resetting offsets of an existing group

Before using the Kafka consumer group tool to reset offsets:

1. Stop all instances participating in the group and verify no active consumers remain.
2. Record current committed offsets for every partition as a baseline.
3. Select the exact group, topic, and partitions; determine the starting offset to re-read from.
4. Run `--dry-run` and inspect every offset the command intends to change.
5. Only after verifying the scope, re-run with `--execute`.
6. Start consumers and monitor lag, processing rate, errors, and downstream impact.

Example previewing rewinding a topic to the beginning for a group:

```bash
kafka-consumer-groups.sh \
  --bootstrap-server <bootstrap-servers> \
  --group <consumer-group> \
  --topic <topic-name> \
  --reset-offsets \
  --to-earliest \
  --dry-run
```

After reviewing the output and confirming the right group/topic, apply the change by replacing `--dry-run` with `--execute`. To reset only one partition, specify topic-partition, e.g., `--topic orders:0`. For a specific offset, use `--to-offset <offset>` after verifying that offset belongs to the target partition.

The reset command sets only the starting position. If you must replay a bounded range with an ending point, implement a mechanism to stop the consumer at the target end offset, or stop the group upon reaching the monitored mark. Never assume resetting to a starting offset automatically bounds how much data is read.

### Retention and compacted topics

Replays can only read data that still exists. Check `retention.ms`, `retention.bytes`, storage status, and the earliest available offset per partition. For topics using `cleanup.policy=compact`, Kafka may have discarded older versions of the same key; compacted topics do not guarantee full state-transition history to reconstruct every business change.

If the target offset already fell outside retained data, resetting offsets cannot recover deleted records. Locate an appropriate archive or backup source before proceeding.

## 5. Preserving order and rate limiting

Kafka guarantees ordering only within a partition. If events for the same aggregate must be processed in order, producers must use stable keys to route them to the same partition and consumers must uphold corresponding processing rules.

Replays can break business-level observed order in several cases:

- Increasing partition counts can change how keys map to partitions for newer records; never assume historical and newer records for the same key share the same partition after a partition count change.
- Multiple consumers processing in parallel or listeners offloading work to thread pools can finish later events before earlier ones.
- Non-blocking retries via retry topics or `@RetryableTopic` can return failed events after later events. This fits when the system tolerates delayed processing or validates sequences; it does not fit when strict order is mandatory.
- DLT replays can re-emit multiple events for the same aggregate out of original order if selection and re-emission are unsorted.

When business rules require ordering, validate aggregate sequence/version in the database. Apply only the next valid version; buffer early arrivals or route late arrivals to reconciliation. For DLT replays, group records by key and sort by sequence or original offset metadata before re-emitting.

Replay rate must be throttled to match database and downstream dependency capacity. Monitor consumer lag, per-record processing time, connection pools, lock waits, CPU, timeouts, and rate limits. Lower concurrency, shrink batch sizes, or pause the replay if downstream crosses thresholds. Increase speed only when metrics confirm the system handles the load.

## 6. Configuring error handling in Spring Kafka

Spring Kafka offers retry and recoverer mechanisms to control listener failures. With `DefaultErrorHandler`, you can configure bounded retries and `DeadLetterPublishingRecoverer` to route unrecoverable records to a DLT. Classify errors before choosing retries:

- Transient errors like timeouts, network glitches, or overloaded dependencies can usually retry with backoff and attempt caps.
- Data errors like invalid schemas, missing required fields, or business rule violations rarely heal on retry. Route them to a DLT or bad-data workflow.
- Code bugs or misconfigurations must be fixed before bulk replay; blind retries only add load and prolong recovery.

When using a DLT, ensure the target topic exists with a partition count compatible with `DeadLetterPublishingRecoverer` routing. Verify recoverer config, DLT naming conventions, serializers, and topic write ACLs in the target environment.

With `@RetryableTopic`, Spring Kafka creates retry topics and a DLT for non-blocking retries. This lets the main partition keep processing other records while a failed record awaits retry, though it can alter observed order. If per-key ordering is mandatory, choose a compatible retry strategy and enforce sequence checks.

### Committing offsets after processing

With listener containers, Spring Kafka manages commits according to `AckMode`. Pick the mode fitting how the listener processes records; `AckMode.RECORD` is usually straightforward when committing after each successfully processed record. If using manual acknowledgment, acknowledge only after required work completes successfully.

For raw Kafka consumers, `enable.auto.commit=false` is typically needed so the application controls commits explicitly. With Spring Kafka listener containers, let the container manage commits per its configuration and avoid enabling auto-commit in ways that surrender processing-order control.

When a listener updates a database, let the database transaction finish before the listener returns normally for the container to commit the offset. A gap remains between database commit and Kafka offset commit; if the app stops in that gap, the record can be redelivered. Inbox/idempotency handles this exact scenario.

### Kafka transactions do not cover all side effects

Spring Kafka supports transactions for consume-process-produce flows across Kafka topics. Producer transactions and consumer `isolation.level=read_committed` ensure consumers read only committed transactional records. Kafka's exactly-once semantics apply to the Kafka operations enlisted in that transaction.

Kafka transactions do not automatically make database updates, emails, payment API calls, or external system actions exactly-once. For database-to-Kafka flows, consider transactional outbox; for Kafka-to-database flows, consider inbox and idempotency inside the database transaction. Design must define each system's transaction boundary explicitly.

## 7. Controlled DLT replay

A DLT isolates records that cannot be processed under current policy. Before replaying a DLT, classify root causes: bad data, incompatible schema, code bug, transient dependency outage, or misconfiguration. Replay only after the root cause is fixed or an explicit business decision governs how to skip/correct the data.

Recommended workflow:

1. Extract record counts by topic, partition, exception, and timestamp; select the exact cohort of records to process.
2. Inspect payload, event ID, Kafka key, correlation ID, and original record metadata. Verify schemas and that the new consumer can read the records.
3. Preserve original event ID and business data. Attach separate replay metadata such as `replay-id`, replay timestamp, and operational ticket ID for traceability.
4. If payloads must be patched, retain the original copy, modified content, reason, and approver per operational procedure. Never silently mutate data during replay.
5. Send a small canary batch to the target topic, verify outcomes and side effects, then expand scope.
6. Monitor succeeded records, still-failing records, and records routed back to the DLT. Cap replay attempts to avoid infinite loops.

When re-emitting, preserve original metadata like source topic, partition, and original offset if libraries and record formats allow. Never overwrite event ID with replay ID: replay ID tracks an operational run, whereas event ID tracks the business event across all deliveries.

Do not immediately delete original records from the DLT after resending. Retain data and audit trails per retention policy for outcome reconciliation. DLT purging should be a separate operation with explicit retention and expiration policies.

## 8. Observing during and after replay

During a replay, monitor at minimum:

- **Kafka progress:** committed offsets, end offsets, per-partition lag, records read, and consumption rate.
- **Listener outcomes:** succeeded records, retry counts, DLT-routed records, exceptions by type, and processing latency.
- **Idempotency:** duplicate events detected, unexpected unique-constraint errors, and skipped events by consumer namespace.
- **Database:** write throughput, connection pool usage, transaction rollbacks, lock waits, deadlocks, and query latency.
- **Downstream:** API errors, timeouts, rate limits, idempotency-keyed requests, and side-effect statuses.
- **Business correctness:** before/after record counts, monetary/quantity totals per aggregate, missing sequences, and reconciliation results.

Define stop thresholds before starting—such as error spikes above threshold, sustained downstream rate limiting, unexpected lag growth, or reconciliation mismatches. When stopping, pause consumers or halt the replay per runbook, record the last offset and replay ID, and investigate before resuming.

After completion, reconcile total records in scope against succeeded, duplicate-skipped, still-failing, and business-excluded counts. Inspect final states of critical aggregates and confirm zero duplicate side effects occurred.

## 9. Pre-production replay testing

Every replay procedure should be rehearsed on representative data before running in production. Test scenarios should include:

| Scenario | Expected outcome |
|---|---|
| Same event delivered twice | Only one business change commits. |
| App stops after database commit before offset commit | Record redelivers and is caught as processed by inbox/dedup. |
| Database transaction rollback | Inbox marker and business changes roll back together; record can reprocess. |
| Two consumers receive same event under contention | Unique constraint prevents double application; contention error is handled deliberately. |
| Event arrives out of sequence | Newer state is not overwritten by older state; event is buffered or routed to reconciliation. |
| Dependency keeps failing | Retries stop at cap and record routes to DLT per policy. |
| Successful DLT replay | Original event ID is preserved, replay metadata is traceable, and no duplicate side effects occur. |
| Incompatible schema or payload | Record is quarantined with enough error context to investigate. |

Beyond per-record checks, verify end-to-end properties: can the replay run multiple times without unexpectedly altering final state; can rate be throttled up or down without breaking business order; and can the process pause and resume cleanly from recorded offsets?

## 10. Operational checklist

Before starting:

- [ ] Identified topic, partitions, starting offset, and ending limit.
- [ ] Identified consumer group, application version, configuration, and processing target.
- [ ] Checked retention, earliest offset, and schema readability.
- [ ] Confirmed stable event IDs and working idempotency where side effects occur.
- [ ] Verified ordering requirements, concurrency, and rate limits.
- [ ] Recorded baseline offsets, replay ID, replay reason, and stop conditions.
- [ ] Tested on a small scope or isolated target environment.

While running:

- [ ] Monitor lag, listener errors, retries, DLT, and downstream health.
- [ ] Check duplicate event counts and idempotency outcomes.
- [ ] Stop if defined thresholds trip or business numbers diverge.
- [ ] Record final offset, timestamp, and replay ID when pausing or finishing.

After running:

- [ ] Reconciled total records in scope against succeeded, duplicate, failed, and excluded counts.
- [ ] Verified aggregate states and critical side effects.
- [ ] Handled remaining DLT records separately.
- [ ] Restored normal operational configuration/concurrency and archived the audit trail.

A replay is complete when the processed data range is reconciled, business state is accurate, remaining failed records have assigned owners, and the consumer group has returned to expected operational health. Zero consumer lag only proves the consumer read to the end of available data; it is not enough to prove the replay was business-correct.
