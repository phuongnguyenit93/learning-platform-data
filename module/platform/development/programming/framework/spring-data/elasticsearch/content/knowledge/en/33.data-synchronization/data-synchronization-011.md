# Monitoring Synchronization Lag and Recoverability

In many systems, Elasticsearch serves search while the authoritative data lives in another system such as PostgreSQL, MySQL, or a business service. After source data changes, documents in Elasticsearch must be updated accordingly. The elapsed time from a source change until users can find the new version is **synchronization lag**.

Data synchronization can fall behind due to growing queues, stopped consumers, overloaded Elasticsearch clusters, bulk requests with failed items, incompatible mappings, or deployments interrupting pipelines. A well-operated system must answer three questions: how far behind is the data, at which stage is data lost or stuck, and where can processing resume without missing records or writing out of order?

This lesson is framed around Spring Data Elasticsearch, with an authoritative source of truth and Elasticsearch acting as a read model/projection for search. Topics span sync architecture, measuring lag, checkpoints, Bulk API handling, retries and Dead Letter Queues (DLQs), replays, backfills, reconciliation, and recovery drills.

## 1. Identifying the Source of Truth and Sync Objectives

Before measuring lag, establish which system holds final authority over the data.

A common architecture:

~~~text
Client
  |
  v
Application service
  |
  +----> Primary database (source of truth)
  |          |
  |          +----> Outbox / CDC log
  |                     |
  |                     v
  |                Sync worker
  |                     |
  |                     v
  +----------------> Elasticsearch
                         |
                         v
                    Search API
~~~

In this model:

- The database stores authoritative business state.
- Outbox or CDC records changes needing synchronization.
- Workers read events in order or per partition.
- Spring Data Elasticsearch or the Elasticsearch Java API Client writes documents.
- The Search API reads projections from Elasticsearch.

If Elasticsearch loses data or an index must be rebuilt, the application can regenerate projections from the source of truth and retained change history.

Never treat a successful Elasticsearch write as proof that business data committed at the source. If both the database and Elasticsearch act as primary write stores without coordination, the system can end up with one succeeding and the other failing.

## 2. Common Synchronization Patterns

### Synchronous Dual Write

The application writes to the database and then writes to Elasticsearch within the same request:

~~~text
Request
  |
  +--> Database commit
  |
  +--> Elasticsearch index
  |
  +--> Response
~~~

This is easy to implement, yet introduces the dual-write problem. The database can commit and Elasticsearch can time out; or Elasticsearch can succeed while the database rolls back. A regular transaction does not automatically span both systems.

If this approach is still used, build explicit repair mechanisms and never report success when the two stores fail to satisfy the business contract.

### Transactional Outbox

The application writes business data and an outbox event within the same database transaction:

~~~text
Database transaction
  |
  +--> Update business row
  |
  +--> Insert outbox event
  |
  +--> Commit
          |
          v
      Outbox relay
          |
          v
      Elasticsearch
~~~

When the transaction commits, the business change and sync event coexist. Workers can retry events if Elasticsearch is temporarily unavailable.

Outbox is usually an easy-to-control choice for applications needing reliable sync without coupling directly to database replication logs.

### Change Data Capture (CDC)

CDC reads the database transaction log, such as WAL or binlog, and forwards changes to the sync pipeline. CDC fits when capturing changes across many tables or avoiding adding event-publishing code to every service.

You must understand how the connector represents inserts, updates, deletes, schema changes, transaction boundaries, and offsets. Not every CDC event equates to a complete domain event.

### Batch Polling

A worker periodically queries records changed after a watermark or by `updatedAt` and updates Elasticsearch. This is simple, yet requires careful handling of identical timestamps, concurrent changes during batches, and pagination gaps.

Never use a standalone timestamp as a checkpoint if resolution is coarse or multiple records share timestamps. Include a tie-breaker key or monotonically increasing sequence.

## 3. Distinguishing Write Latency from Searchable Latency

A document may already be accepted by Elasticsearch yet not immediately appear in search due to refresh.

Distinguish clearly:

- **Source-to-consumer lag:** time from source commit until the worker receives the event.
- **Processing lag:** time the worker spends processing, transforming, and sending requests.
- **Index acknowledgement latency:** time for Elasticsearch to acknowledge the write.
- **Search visibility lag:** time from source commit until the document is actually visible in search.
- **End-to-end synchronization lag:** total time from source change until the projection is readable per product contract.

Timeline:

~~~text
t0: Database commit
 |
 |  Queue / CDC delay
 v
t1: Worker receives event
 |
 |  Transform + bulk request
 v
t2: Elasticsearch acknowledges write
 |
 |  Wait for refresh
 v
t3: Document becomes searchable

End-to-end lag = t3 - t0
~~~

Measuring only Bulk API response times can make dashboards look healthy while users still cannot find new documents.

For some use cases, write acknowledgement suffices—for example, when an application needs confirmation data reached the index without immediate searchability. For read-after-write use cases, measure searchable latency or use an appropriate refresh strategy.

## 4. Defining Lag with Meaningful Timestamps

Each event should carry source timestamps, such as:

- `sourceCreatedAt`: when the event was created.
- `sourceCommittedAt`: when the source transaction committed, if accurately obtainable.
- `consumedAt`: when the worker received the event.
- `processingStartedAt`: when processing began.
- `indexedAt`: when Elasticsearch confirmed the operation.
- `searchableAt`: when the document was observed in search, if the use case measures it.

Timestamps must have explicit timezones; store `Instant`/UTC. Synchronize clocks across hosts so timestamp subtraction stays meaningful. Large clock skew can produce negative or inflated lag.

Never substitute worker processing time for the original change time. If an event sat in a queue for 20 minutes before processing, worker timestamps hide those 20 minutes of delay.

An event envelope might look like:

~~~json
{
  "eventId": "evt-01JABC",
  "aggregateType": "Product",
  "aggregateId": "p-1001",
  "tenantId": "tenant-a",
  "eventType": "ProductUpdated",
  "sourceVersion": 42,
  "sourceOccurredAt": "2026-11-13T09:20:00Z",
  "partition": "product-07",
  "sequence": 918273,
  "payload": {
    "name": "Mechanical Keyboard",
    "status": "ACTIVE"
  }
}
~~~

The envelope should preserve a stable event ID across retries. Never mint a new `eventId` every time a worker resends the same change, or deduplication becomes much harder.

## 5. Measuring End-to-End Synchronization Lag

For indexed events, basic lag is:

\[
lag = indexedAt - sourceOccurredAt
\]

When the requirement is searchable data:

\[
searchableLag = searchableAt - sourceOccurredAt
\]

Track percentiles rather than looking at averages alone:

- p50: typical lag.
- p95: lag for the vast majority of events.
- p99: slow tail.
- max: slowest event in the window.
- oldest pending age: age of the oldest unprocessed event.

Averages can hide a small group of events stuck for hours. p95/p99 and oldest pending age are far better at exposing backlogs or poison messages.

Measure lag per event or per partition. Sampling only the newest processed event's timestamp lets a healthy partition mask a stalled partition.

## 6. Watermarks and Checkpoints

A **watermark** describes sync progress up to a given point. A **checkpoint** is a position usable to resume processing after a worker restart.

Depending on the source, a checkpoint can be:

- Kafka partition offset.
- CDC log sequence number (LSN), binlog position, or connector offset.
- Outbox event ID/sequence.
- Database cursor on `(updatedAt, primary key)`.
- A monotonically increasing sequence per aggregate or partition.

A checkpoint should never be just the latest timestamp if multiple events can share timestamps. For time-based polling, use a composite key:

~~~sql
WHERE
    updated_at > :lastUpdatedAt
    OR (
        updated_at = :lastUpdatedAt
        AND id > :lastId
    )
ORDER BY updated_at, id
LIMIT :batchSize
~~~

After each batch, persist the final successfully processed pair. On restart, the worker resumes past this checkpoint.

### Checkpoints Must Reflect Completed Work

Never advance the checkpoint to the newest event merely because the worker read it. If event 100 failed while the checkpoint jumped to 120, a restart can skip event 100.

With parallel processing, events can finish out of arrival order. A safe checkpoint is usually the **contiguous completed offset**: the highest position where every preceding event in the partition has completed or entered durable error handling per policy.

If the system skips an event after moving it to a DLQ, persist the DLQ status and position durably for later replay. Never treat an unrecorded failure as completed.

## 7. Distinguishing Received, Processed, Indexed, and Searchable

A sync dashboard should expose distinct progress states:

| State | Meaning |
|---|---|
| Received | Worker received the event |
| Validated | Payload and schema passed validation |
| Transformed | Document/query constructed |
| Submitted | Request dispatched |
| Indexed | Item acknowledged as successful by Elasticsearch |
| Searchable | Document appeared in search as required |
| Dead-lettered | Event persisted to DLQ for investigation/replay |
| Reconciled | Confirmed projection matches source |

An event can be received yet unprocessed due to queuing; submitted yet hitting item-level errors; indexed yet not searchable; or dead-lettered and awaiting remediation.

Separating states pinpoints bottlenecks accurately. Low queue lag with high searchable lag points to refresh behavior, whereas high consumer lag points to worker throughput or downstream capacity.

## 8. Counting Bulk API Results Accurately

The Bulk API executes multiple index/create/update/delete actions in one request. The overall HTTP request can succeed while individual items fail.

Therefore, never assume a bulk call that threw no exception wrote every item successfully.

A response can contain:

- `errors`: indicates whether any item failed.
- `items`: individual outcome per action.
- `status`: HTTP status per item.
- `error`: error type and reason.
- `_id`, `_index`, and version metadata.

Abbreviated response example:

~~~json
{
  "errors": true,
  "items": [
    {
      "index": {
        "_id": "p-1001",
        "status": 201
      }
    },
    {
      "index": {
        "_id": "p-1002",
        "status": 429,
        "error": {
          "type": "es_rejected_execution_exception",
          "reason": "rejected execution"
        }
      }
    },
    {
      "index": {
        "_id": "p-1003",
        "status": 400,
        "error": {
          "type": "mapper_parsing_exception",
          "reason": "failed to parse field"
        }
      }
    }
  ]
}
~~~

In this example, `p-1001` succeeded, `p-1002` can retry after backoff, and `p-1003` needs a payload or mapping fix. Marking the entire batch successful loses both failed events from recovery.

## 9. Handling Per-Item Outcomes

Workers must map each bulk item back to its corresponding source event. You can maintain a list aligned with request order:

~~~text
events[0] <-> bulkItems[0]
events[1] <-> bulkItems[1]
events[2] <-> bulkItems[2]
~~~

After receiving the response:

1. Verify response item count matches sent action count.
2. Correlate each item with its event ID/aggregate ID.
3. Classify success, retryable failure, or permanent failure.
4. Persist durable per-item status.
5. Advance checkpoints only per safety rules.
6. Emit metrics per outcome type.

Never check only the top-level `errors` flag. It tells you a batch had failures, not which items need retries. Also do not rely blindly on positional alignment if transformations or grouping occur; retain explicit correlation IDs to avoid misattributing items.

## 10. Classifying Recoverable Errors vs. Data Errors

A useful retry policy separates transient errors from errors that will not resolve on their own.

| Error category | Common handling |
|---|---|
| 429 / rejected execution | Back off, shrink batch/concurrency |
| 502, 503, 504 | Bounded retries |
| Network timeout/reset | Idempotent retry, inspect state if needed |
| Cluster unavailable | Retain backlog, retry with backoff |
| 400 mapping/parsing | DLQ, fix schema/payload |
| 401/403 | Pause or alert on credential configuration |
| Index not found | Check provisioning/aliases; do not retry infinitely |
| 409 version conflict | Apply explicit ordering/version policy |
| Document validation failure | DLQ or reject per business rules |
| Payload too large | Split or handle separately |

Some status codes have multiple causes. For example, 409 can stem from concurrency conflicts, duplicate creates, or optimistic concurrency. Never retry all 409s identically.

## 11. Exponential Backoff and Jitter

Immediate continuous retries make an overloaded cluster harder to recover. Use exponential backoff:

\[
delay_n = min(maxDelay,\ baseDelay \times 2^n)
\]

Add jitter so workers do not all retry simultaneously:

\[
actualDelay = random(0,\ delay_n)
\]

Conceptual configuration example:

- Attempt 1: up to 200 ms.
- Attempt 2: up to 400 ms.
- Attempt 3: up to 800 ms.
- Attempt 4: up to 1.6 s.
- Maximum cap: 30 s.
- Beyond retry cap: DLQ or route to investigation status.

Specific values depend on throughput, SLAs, and cluster capacity. Never run infinite retries without caps, metrics, and alerts.

If Elasticsearch returns `Retry-After` or downstream signals throttling, consider honoring those hints instead of relying solely on fixed schedules.

## 12. Shrinking Batch Size When Elasticsearch Is Overloaded

When bulk calls frequently hit 429s or rising latency, reduce:

- Document count per bulk request.
- Total bytes per bulk request.
- Concurrent bulk requests in flight.
- Parallel worker/consumer count.
- Event read rate from queues.

Batches should be bounded by both item count and byte size. A batch of 500 small documents differs substantially from 500 multi-megabyte payloads.

A simple adaptive strategy:

~~~text
If bulk succeeds and latency is stable:
    increase batch slightly up to configured cap
If frequent 429s or timeouts occur:
    shrink batch and concurrency
If mapping errors occur:
    do not shrink batch; route failed items to DLQ
~~~

Never grow batches indefinitely just to reduce request counts. Oversized batches inflate memory footprint, processing duration, and blast radius on timeouts.

## 13. Idempotency: The Foundation of Safe Retries

An event may be sent multiple times if a worker crashes after Elasticsearch writes yet before the checkpoint saves. Thus, pipelines should assume at-least-once delivery.

**Idempotency** means reprocessing the same event creates no incorrect state or unintended duplicate side effects.

A common pattern uses stable document IDs:

~~~java
IndexQuery query = new IndexQueryBuilder()
        .withId(product.getId())
        .withObject(product)
        .build();
~~~

If the same product is re-indexed with the same ID, the index request replaces the document per index semantics rather than generating a new random-ID record.

This does not solve ordering on its own. An older event retried after a newer event can still overwrite newer data without version checks.

## 14. Protecting Ordering with Source Versions

Each aggregate can have a monotonically increasing version:

~~~json
{
  "aggregateId": "p-1001",
  "sourceVersion": 42,
  "eventType": "ProductUpdated"
}
~~~

Once event version 42 is indexed, a late-arriving version 41 event must not overwrite the projection.

Options:

- External versioning in Elasticsearch.
- Storing `sourceVersion` in the document and checking before updating.
- Serializing events by aggregate key.
- Using optimistic concurrency with sequence number/primary term when appropriate.
- Using version-conditional update scripts.

External versioning lets Elasticsearch reject a version older than the existing version. Choose the right `version_type` for your pipeline semantics and understand behavior when identical versions are resent.

Never use timestamps as versions if timestamps can collide or clocks drift. An integer version from the source is usually much clearer.

## 15. Handling Version Conflicts Intentionally

With external versioning, an older request can receive a conflict because the document already holds a newer version. This can be the desired outcome: the stale event is outdated and should not be retried like a transient error.

Workers must distinguish:

- Event older than document: mark stale/superseded per policy.
- Same version and same payload: likely an already-processed duplicate.
- Same version yet different payload: sign of a source data or event producer bug.
- Newer version: must be indexed unless another conflict occurs.

With optimistic concurrency (`if_seq_no` and `if_primary_term`), conflicts usually mean the document mutated since the read. You may need to re-read and recompute the update; never blindly retry the stale request.

## 16. Deletes Also Need Versions and Tombstones

Delete synchronization is easily overlooked. A document deleted at the source yet lingering in Elasticsearch keeps showing up in searches.

A delete event can carry:

~~~json
{
  "eventId": "evt-delete-1001",
  "aggregateId": "p-1001",
  "sourceVersion": 43,
  "eventType": "ProductDeleted",
  "sourceOccurredAt": "2026-11-13T10:00:00Z"
}
~~~

If a delete event executes before a late stale update event, the document can be recreated. Versioning or tombstones prevent this.

Some systems store tombstones (deleted markers) inside projections or a separate store long enough to block old events. If deleting documents outright, verify how the pipeline ensures old events will not resurrect them.

Tests must include delayed updates arriving after deletes and confirm the final state remains deleted.

## 17. Outbox Pattern and Event States

An outbox table can store:

~~~sql
CREATE TABLE outbox_event (
    event_id        VARCHAR(64) PRIMARY KEY,
    aggregate_type  VARCHAR(80) NOT NULL,
    aggregate_id    VARCHAR(128) NOT NULL,
    aggregate_version BIGINT NOT NULL,
    event_type      VARCHAR(120) NOT NULL,
    payload         JSON NOT NULL,
    occurred_at     TIMESTAMP NOT NULL,
    published_at    TIMESTAMP NULL,
    attempts        INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMP NULL,
    last_error      TEXT NULL
);
~~~

Actual schemas depend on the database. For PostgreSQL, `JSONB` and `timestamp with time zone` may fit better; workers also need claim/lock mechanisms or CDC so multiple instances do not process duplicates unintentionally.

Operational states can live in a separate table or be inferred from published/attempt fields. Avoid updating outbox rows and Elasticsearch inside a transaction assuming both can roll back together.

Outbox records should be retained long enough for replay and investigation. Deleting events right after publishing forfeits recovery when a mapping bug surfaces hours later.

## 18. Dead Letter Queue (DLQ)

A DLQ stores events that cannot be processed automatically after retries or encounter permanent errors.

A DLQ record should retain:

- `eventId` and `aggregateId`.
- `sourceVersion`/sequence.
- Original payload or a safe reference to it.
- Creation timestamp.
- Error type and sanitized error message.
- Attempt count.
- Worker/build version.
- Target index/alias.
- Replay status and operator/approval if needed.

Example record:

~~~json
{
  "eventId": "evt-1003",
  "aggregateId": "p-1003",
  "sourceVersion": 8,
  "attempts": 5,
  "failureType": "mapper_parsing_exception",
  "target": "products-write",
  "status": "PENDING_REPAIR"
}
~~~

A DLQ is not a trash bin to forget. Maintain dashboards, alerts, owners, SLAs, and replay workflows. If the DLQ grows unowned, the system silently accumulates drifted data.

Never store secrets, access tokens, or unnecessary personal info in error payloads. Protect DLQ data like business data.

## 19. Replaying Events from the DLQ

Once mappings or payloads are fixed, events can be replayed:

1. Select a batch of DLQ events by error type or time range.
2. Verify schema and `sourceVersion`.
3. Check whether each event is still needed or superseded by a newer event.
4. Rebuild the document/query from source payload or re-read latest state.
5. Send to the target index.
6. Inspect per-item outcomes.
7. Mark DLQ records resolved only after outcomes are confirmed.
8. Record an audit trail for the replay.

There are two strategies:

- **Replay original event:** useful when reconstructing history and events hold complete data.
- **Rebuild from latest state:** suits cases where old events are stale or projections can regenerate from the source of truth.

Never bulk-replay the entire DLQ immediately after a cluster recovers. Start with small batches, watch latency and errors, and scale up gradually.

## 20. Retry Queues vs. DLQs

Retry queues hold events likely to succeed after waiting. DLQs hold events requiring investigation or fixes before retrying.

| Retry queue | DLQ |
|---|---|
| Transient errors | Permanent errors or exhausted retries |
| Has `nextAttemptAt` | Has failure classification |
| Retries automatically on schedule | Usually requires explicit replay decision |
| Backoff and jitter | Tracks owners and remediation |
| Typically short retention | Needs sufficient retention for investigation |

Do not send every error to the retry queue. Mapping errors do not vanish after 30 seconds. Conversely, do not dump every timeout straight into the DLQ when requests can safely retry.

## 21. Recovering After an Elasticsearch Outage

When Elasticsearch is unavailable:

- Do not delete or drop source events.
- Retain events in the outbox/broker.
- Throttle or pause consumers via backpressure.
- Retry with backoff, avoiding retry storms.
- Monitor oldest pending age and queue depth.
- Ensure event sources retain events longer than the outage duration.
- When the cluster recovers, ramp throughput gradually.
- Check item-level bulk failures.
- Confirm lag drops and searchable latency returns to normal.

If consumers keep reading faster than they can write, queues can overflow or exhaust memory. Enforce queue bounds and pause/resume policies.

When outages exceed broker or CDC log retention, you may need a backfill from the database or a snapshot. Therefore, recovery plans must account for event retention limits, not merely restarting workers.

## 22. Recovering After Mapping or Schema Errors

Mapping errors rarely self-resolve on retry. For example, the source begins sending strings into a field mapped as numeric.

Workflow:

1. Pause or isolate the failing event type if it floods the DLQ.
2. Identify the changed field and schema version.
3. Inspect the current mapping.
4. Choose a fix: fix payload, add a new field, create a new index version, or apply an ingest transform.
5. Replay affected events.
6. Verify documents and queries after replay.
7. Resume consumers once the error is resolved.

Elasticsearch does not allow arbitrarily changing existing field mappings. Changing data types usually requires creating a new index with the right mapping, reindexing data, and switching aliases after verification.

Never alter production mappings directly just to silence errors without evaluating query, sort, aggregation, and existing-data impacts.

## 23. Snapshot + Change Stream to Rebuild an Index

When creating a new index or recovering projections from scratch, combine a source data snapshot with a change stream.

General flow:

~~~text
1. Capture database log position L0
             |
             v
2. Read consistent source snapshot
             |
             v
3. Bulk index snapshot into new index
             |
             v
4. Replay changes after L0
             |
             v
5. Catch up to current position
             |
             v
6. Validate counts / samples / hashes
             |
             v
7. Switch read alias to new index
~~~

Crucially, the snapshot and log position must be consistent. Taking a snapshot first and starting CDC afterward without an exact join point can drop changes occurring between the two steps.

With databases supporting consistent snapshots tied to a log position, save that position as the replay boundary. Follow your CDC connector's workflow to prevent gaps or duplicates; duplicates can be absorbed via idempotency, whereas gaps cannot self-heal without reconciliation.

## 24. Rebuilding Indexes Using Aliases

A safe way to build a new index uses versioned indexes and aliases:

~~~text
products-v1  <- alias products-read
products-v2  <- build + validate
                  |
                  v
            atomic alias switch
                  |
                  v
products-read -> products-v2
~~~

Workflow:

1. Create `products-v2` with new mappings/settings.
2. Read source snapshot and bulk index into v2.
3. Replay events emitted during the snapshot.
4. Catch up to a fresh watermark.
5. Run reconciliation.
6. Switch read/write aliases per plan.
7. Keep the old index during the defined rollback window.
8. Delete the old index once stability is confirmed and retention expires.

Alias switching executes as an atomic update-aliases request in Elasticsearch. Define write and read aliases clearly; never let producers keep writing accidentally to the old index post-switch.

When using external versioning, snapshots and events can replay with versions so older events never overwrite newer snapshots. Confirm version semantics align with bulk operations and mappings.

## 25. Reconciliation: Comparing Source Against Projection

Replays do not replace reconciliation. A pipeline can report every event succeeded yet still hold corrupted data due to transform bugs, missed events prior to monitoring, or writes bypassing the outbox.

Reconciliation compares source data against Elasticsearch across a controlled scope.

Verification levels:

- **Count:** document counts per tenant, status, or partition.
- **Existence:** whether IDs exist in both source and projection.
- **Version:** whether `sourceVersion` matches source versions.
- **Field samples:** comparing critical fields.
- **Hash/checksum:** computing stable fingerprints from business fields.
- **Delete consistency:** ensuring deleted records no longer appear.
- **Aggregate comparison:** comparing totals or group distributions.

Never compare total document counts across the whole index alone. Tenant A missing 100 documents and Tenant B having 100 extra documents leaves the grand total unchanged.

## 26. Partitioned or Time-Window Reconciliation

For large datasets, never pull the entire source and Elasticsearch into the application for a single comparison pass. Split scopes by:

- Tenant.
- ID range.
- Created/updated date.
- Partition key.
- Entity type.
- Source version window.

Example reconciliation by date and tenant:

~~~text
tenant-a / 2026-11-12
tenant-a / 2026-11-13
tenant-b / 2026-11-12
tenant-b / 2026-11-13
~~~

Each partition can record:

- Source count.
- Elasticsearch count.
- Mismatch count.
- Oldest mismatch age.
- Last checked timestamp.
- Status: `MATCH`, `MISMATCH`, `FAILED`, or `IN_PROGRESS`.

When mismatches appear, emit scoped repair tasks instead of immediately rebuilding the entire index.

## 27. Repairing Drifted Data Without Introducing New Errors

When reconciliation finds missing or stale documents:

1. Read the latest state from the source of truth.
2. Determine the source version.
3. Build the projection document using the exact same transformation code as the normal pipeline.
4. Index with a stable ID and version guard.
5. Verify the document in Elasticsearch.
6. Record the repair result and applied source version.

Using an older event to repair a document after the source mutated further can regress the projection. For repairs, rebuilding from the source's latest state is usually safer than replaying an old payload without version checks.

For deleted source records, apply tombstone/delete semantics so old events cannot recreate them after repair.

## 28. Monitoring Throughput and Backlog

Lag is one indicator, but you need supporting metrics to explain why:

- `events produced per second`.
- `events consumed per second`.
- `events indexed per second`.
- `queue depth` or `consumer lag`.
- `oldest pending event age`.
- `bulk requests per second`.
- `bulk items per request`.
- `bulk byte size`.
- `item success/failure count`.
- `retry count` and `retry delay`.
- `DLQ size` and `oldest DLQ age`.
- `Elasticsearch request latency`.
- `429`, `5xx`, `timeout`, and connection error rates.
- `worker concurrency` and `processing duration`.
- `refresh/search visibility delay`.

If producers emit 1,000 events/sec while workers handle only 700 events/sec, the backlog grows by ~300 events/sec. A lag dashboard lacking throughput makes it hard to predict when a backlog will drain.

Backlog drain time can be estimated as:

\[
drainTime \approx \frac{pendingEvents}{processingRate - incomingRate}
\]

This formula holds only when `processingRate` exceeds `incomingRate` and rates remain relatively steady. Without spare worker capacity, backlogs never clear on their own.

## 29. Metrics and Dashboards with Spring Boot

Spring Boot Actuator and Micrometer can expose worker metrics. Example:

~~~java
@Component
public class SyncMetrics {

    private final MeterRegistry registry;

    public SyncMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordIndexed(String eventType) {
        registry.counter(
                "search.sync.items",
                "result", "success",
                "event_type", eventType
        ).increment();
    }

    public void recordFailure(String category) {
        registry.counter(
                "search.sync.items",
                "result", "failure",
                "failure_type", category
        ).increment();
    }

    public void recordLag(Duration lag) {
        registry.timer("search.sync.lag")
                .record(lag);
    }

    public void recordProcessingTime(Duration duration) {
        registry.timer("search.sync.processing")
                .record(duration);
    }
}
~~~

This is a simple example of recording counters and timers. In production, never add high-cardinality values like `eventId`, `documentId`, or `tenantId` as default metric tags. Those belong in controlled logs or traces.

Gauges can track queue depth or oldest pending age. With gauges, update backing sources safely and avoid running heavy database queries on every scrape.

## 30. Monitoring Searchable Lag

When the requirement is "users find data right after updating," measuring when Elasticsearch receives the write is insufficient.

You can measure searchable lag via:

- Sampling indexed events and querying back by ID after a brief delay.
- Using a periodically updated canary document and measuring time until search visibility.
- Using appropriate refresh policies on operations needing read-after-write.
- Measuring elapsed time between write acknowledgement and the first search returning the document.

Never fire a separate search request for every production event just to measure lag; that generates more load than the sync pipeline itself. Sampling or canaries are usually better.

Refresh is what makes indexed changes searchable. Setting `refresh=wait_for` helps specific requests awaiting refresh, yet using it on every bulk call degrades throughput. Balance read-after-write needs against performance.

## 31. Defining SLIs, SLOs, and Alerts

Useful SLIs include:

- p95 end-to-end sync lag.
- p99 end-to-end sync lag.
- oldest pending event age.
- event success rate over a time window.
- DLQ growth rate.
- bulk item failure rate.
- document version mismatch rate.
- canary searchable lag.

Illustrative SLO table:

| Indicator | Example target |
|---|---|
| p95 source-to-searchable lag | under 30 seconds |
| p99 source-to-searchable lag | under 2 minutes |
| oldest pending event age | under 5 minutes |
| successful event indexing rate | 99.9% over a daily window |
| unprocessed DLQ items | not growing continuously |

These numbers are not universal defaults. Choose targets matching product expectations, load, refresh intervals, and operational cost.

Alerts should reflect user/system impact:

- Warning when p95 lag breaches the SLO for a sustained interval.
- Critical when oldest pending age climbs rapidly or consumer offsets stall.
- Critical when mass mapping errors hit the DLQ.
- Warning when retry rates spike or 429s increase.
- Critical when event sources approach retention limits before backlogs clear.

Avoid alerting on brief spikes with no real impact. Use appropriate evaluation windows and sustained-breach conditions.

## 32. Distinguishing Lag from Data Loss

Lag means data has not yet reached the target or become searchable within the desired time. Data loss means events or changes can no longer be reproduced through the current pipeline.

Examples:

- Queue has 100,000 pending events: backlog/lag, not necessarily data loss.
- Consumer offset skipped past a failing event without saving to DLQ: risk of data loss.
- Outbox row deleted prior to publishing: possible event loss.
- CDC log retention expired before consumer caught up: cannot replay from log.
- Document written incorrectly yet source event still exists: drifted projection, repairable.

Dashboards should expose checkpoints, retention head/tail, DLQ counts, and reconciliation status to distinguish these two states.

## 33. RPO and RTO for Elasticsearch Projections

**RPO (Recovery Point Objective)** is the maximum acceptable data loss during an incident. **RTO (Recovery Time Objective)** is the maximum time to restore service.

With Elasticsearch as a rebuildable projection:

- RPO depends on retention of source data, outbox/CDC logs, and checkpoints.
- RTO depends on snapshot speed, bulk indexing rate, backlog replay time, and alias switching.
- If source events are kept for only 24 hours yet an outage lasts 48 hours, log replay alone cannot recover.
- If rebuilding an index takes 6 hours while the SLO permits only 30 minutes of disruption, plan parallel indexing or recent snapshots.

Calculate RTO using real measurements: document count, average size, sustained bulk throughput, replay time, and reconciliation time. Never estimate solely from local machine benchmarks.

## 34. Runbook When Lag Exceeds Thresholds

A runbook can follow this sequence:

1. Determine whether lag sits in source-to-consumer or write-to-searchable.
2. Inspect queue depth, oldest pending age, and consumer offsets.
3. Check worker health, restart counts, and recent deployments.
4. Inspect Elasticsearch cluster health, thread pools, 429s, 5xxs, and latency.
5. Check bulk item failures, retry queues, and DLQs.
6. Classify errors as transient, mapping/schema, or credential/config.
7. If downstream is overloaded, reduce concurrency/batch size or pause consumers.
8. If mapping errors occur, isolate the event type and fix schema/payloads.
9. Once the cluster stabilizes, resume in small batches and monitor backlog drain rate.
10. Run reconciliation across affected partitions.
11. Confirm searchable lag returns within SLO.
12. Document root cause, impact window, and preventive measures.

Never blindly restart workers before understanding the root cause. Restarts can wipe in-memory state, create duplicates, or cause multiple instances to retry at once.

## 35. Recovery Drills

Recovery plans must be tested periodically. Drill scenarios:

- Stop Elasticsearch for several minutes, then bring it back online.
- Trigger bulk 429s by ramping load in a test environment.
- Send payloads violating mappings to exercise the DLQ.
- Kill a worker after Elasticsearch writes yet before committing checkpoints.
- Send older-version events after newer-version events.
- Emit a delete event and replay an older update afterward.
- Pause consumers nearly up to retention limits.
- Rebuild a new index and switch aliases.
- Inject deliberate mismatches and run reconciliation/repair.

For each drill, record: time to detect, time to recover, retried event counts, DLQ counts, pre/post drift, and whether SLO/RPO/RTO targets were met.

Do not verify merely that workers restart cleanly. Verify zero lost events, zero version regressions, and accurate final search state.

## 36. Testing Checkpoints and Crash Recovery

A critical integration test simulates crashes mid-flight:

~~~text
1. Worker reads event E42
2. Elasticsearch writes E42 successfully
3. Worker crashes before committing checkpoint
4. Worker restarts
5. E42 is read again
6. Re-indexed with the same document ID/version
7. Worker commits checkpoint
~~~

The result must be one accurate document, with no duplicates and no overwritten newer versions.

Another scenario:

~~~text
1. Worker reads E42, E43, E44
2. E42 and E44 succeed
3. E43 fails
4. Worker restarts
5. Checkpoint must not skip E43
~~~

When processing in parallel, test contiguous checkpoints or broker per-partition acks. Never commit the highest completed offset while an earlier gap remains unresolved.

## 37. Testing Bulk API Partial Failures

Construct a batch containing:

- A valid document.
- A document with a mapping error.
- An item triggering a conflict.
- An item experiencing controlled throttling in test.

Verify:

- The worker reads individual item responses.
- Succeeded items are not unnecessarily resent once state is recorded.
- Retryable items are scheduled for retry.
- Permanent failures go to the DLQ.
- Checkpoints respect no-gap policies.
- Metrics accurately reflect success/failure counts.
- Replaying after fixing errors does not corrupt newer documents.

Never rely solely on mocked responses to validate Bulk API behavior. Include integration tests against real Elasticsearch alongside unit tests for classifiers and worker state machines.

## 38. Testing Lag with Controllable Clocks

Never use `Thread.sleep` in unit tests to simulate lag. Inject a `Clock` for deterministic time:

~~~java
public class SyncLagCalculator {

    private final Clock clock;

    public SyncLagCalculator(Clock clock) {
        this.clock = clock;
    }

    public Duration lag(Instant sourceOccurredAt) {
        return Duration.between(
                sourceOccurredAt,
                clock.instant()
        );
    }
}
~~~

Test:

~~~java
@Test
void calculatesLagFromSourceTimestamp() {
    Clock clock = Clock.fixed(
            Instant.parse("2026-11-13T10:00:30Z"),
            ZoneOffset.UTC
    );

    SyncLagCalculator calculator =
            new SyncLagCalculator(clock);

    Duration lag = calculator.lag(
            Instant.parse("2026-11-13T10:00:00Z")
    );

    assertEquals(Duration.ofSeconds(30), lag);
}
~~~

This tests the calculation independently of wall-clock test runtime. In integration tests, use fixed fixture event timestamps and assert corresponding metrics/records.

## 39. Common Pitfalls in Sync Monitoring and Recovery

| Symptom | Possible cause | Remediation |
|---|---|---|
| Dashboard reports low lag yet users miss documents | Measured write ack only, ignored refresh | Measure searchable lag or use a canary |
| Bulk request succeeds yet documents are missing | Ignored item-level errors | Inspect every item response |
| Checkpoints skip failed events | Committed offsets before durable handling | Ack after success/DLQ and keep contiguous progress |
| Retries overwrite newer documents with older ones | Missing source version guard | External versioning or explicit version checks |
| Deleted documents reappear | Late stale update events | Tombstones/version ordering |
| DLQ grows unattended | Missing owners, alerts, and replay workflow | Establish runbooks, dashboards, and DLQ SLAs |
| Backlog fails to shrink post-recovery | Throughput at or below incoming rate | Scale capacity carefully, throttle producer load |
| Replays create duplicate data | Unstable IDs or non-idempotent side effects | Deterministic IDs and idempotency keys |
| Index rebuild misses concurrent changes | Snapshot not aligned with CDC position | Pair consistent snapshot + log position |
| Counts match across systems yet data mismatches | No per-partition/ID verification | Version/hash reconciliation |
| Post-outage retry storm | Many workers retrying simultaneously | Exponential backoff and jitter |
| Mapping errors retry forever | Permanent failures not classified | Route to DLQ and fix schema |
| Negative or erratic lag | Clock skew or bad source timestamps | Standardize on UTC, sync clocks, validate event times |

## 40. Resilient Synchronization Design Checklist

**Source and events**

- Source of truth identified.
- Durable outbox or CDC in place.
- Events carry stable IDs.
- Aggregate versions/sequences present where ordering matters.
- Payloads include source timestamps and schema versions.
- Retention long enough for outages and replays.

**Processing and checkpoints**

- Separate received, processed, indexed, and searchable states.
- Inspect every bulk item.
- Advance checkpoints only once state is durable.
- Handle gaps under parallelism.
- Idempotent handling on redelivery.
- Version guards against regressions.
- Clear ordering for deletes/tombstones.

**Retries and DLQs**

- Classify transient vs. permanent failures.
- Exponential backoff with jitter.
- Bounded attempts and total retry duration.
- Adjust batch size/concurrency on 429s.
- DLQs carry payloads/references, errors, owners, and retention.
- Replay workflows and audit trails in place.

**Observability and recovery**

- Measure source-to-consumer and source-to-searchable lag.
- Track p95/p99 and oldest pending age.
- Track throughput, queue depth, retries, DLQs, and bulk errors.
- SLOs, alerts, and runbooks defined.
- Snapshot + CDC catch-up ready for rebuilds.
- Reconciliation by tenant/partition/version.
- RPO/RTO measured realistically.
- Regular drills for crashes, outages, mapping errors, and replays.

Monitoring synchronization lag means more than timing Bulk API responses. You must trace changes from the source of truth through queues, workers, and Elasticsearch until search visibility, while keeping checkpoints, versions, and event histories durable enough for failure recovery. Bulk item failures must be handled individually, retries require idempotency and backoff, non-self-healing errors belong in a DLQ, and replays/backfills need version guards and reconciliation. With per-stage metrics, runbooks, and recovery drills, Elasticsearch can rebuild or catch up backlogs without silently losing updates or regressing data state.
