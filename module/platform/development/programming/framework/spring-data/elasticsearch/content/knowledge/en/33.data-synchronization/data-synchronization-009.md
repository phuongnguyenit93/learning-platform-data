# Bootstrapping an Index from Existing Data Without Losing New Changes

When creating a new Elasticsearch index for a live system, the application often needs to load previously existing data. While that loading runs, users continue creating, updating, or deleting records. Simply scanning existing data and writing it into the new index risks dropping changes made during bootstrap or overwriting them with older data.

For example, a bootstrap job reads product `P-100` at price 100. While the job runs, a user changes the price to 120. If the price-120 update event writes to the new index first and the bootstrap job writes its price-100 snapshot later, the new index reverts to stale state. Another case is a product deleted during bootstrap; if the old snapshot writes after the delete event, the product can reappear.

To bootstrap safely, you must coordinate two data streams:

1. **Snapshot:** existing data at a consistent point in time.
2. **Change stream:** every change occurring after that snapshot boundary.

After loading the snapshot into the new index, the application replays captured changes, catches up to the live update stream, and only then switches queries to the new index. This mechanism is commonly built using database change data capture (CDC), a transactional outbox, or an ordered change log.

## 1. The Bootstrap Problem While Writes Continue

Suppose a system uses a database as its source of truth and Elasticsearch serves search. A new index is needed to change mappings, analyzers, document structure, or text analysis rules.

During bootstrap:

- Users continue creating new documents.
- Existing documents continue being updated.
- Some documents are deleted.
- The bootstrap job reads data page by page and writes in batches.
- Change events can arrive before or after their corresponding snapshot records.

The goal is for the new index to fully reflect source state at cutover time, without missing changes or letting older data overwrite newer data.

### 1.1. Why Scanning Old Data Alone Is Insufficient?

A naive approach is:

1. Read the entire product table.
2. Write each page into the new index.
3. Once finished, switch the alias to the new index.

This approach has a gap: changes occurring after the job reads a record and before cutover may be absent from the snapshot. While the application still writes to the old index, the new index never receives those updates.

Even if the application simultaneously writes to both the old and new indexes, write ordering can cause race conditions. The snapshot job can overwrite a newer update with stale data.

### 1.2. Two Data Streams Must Be Coordinated

~~~text
                   Source of truth
                          |
               +----------+----------+
               |                     |
               v                     v
      Consistent snapshot       Change stream
               |                (CDC / Outbox)
               v                     |
        Bulk bootstrap               |
               |                     |
               v                     v
           New index <--- Replay and catch-up
                          |
                          v
                    Validate data
                          |
                          v
                  Switch read alias
~~~

The snapshot loads pre-existing state. The change stream brings the new index up to current state. Both streams must share an accurate join point or a strong versioning mechanism to handle the overlap.

## 2. Essential Concepts

| Concept | Meaning |
| --- | --- |
| Source of truth | Authoritative data source where business writes occur |
| Target index | New index being bootstrapped |
| Snapshot | Point-in-time capture of source data at a consistent boundary |
| Watermark | Position in the change log marking the snapshot boundary |
| CDC | Change Data Capture, recording database changes |
| Transactional outbox | Event table written within the same business transaction |
| Replay | Reprocessing recorded events into the target index |
| Catch-up | Processing the change stream until near or at the current position |
| Cutover | Switching the read alias to the new index |
| Tombstone | Record marking a document deleted, preserving the delete operation's version |

A watermark can be a database log sequence number (LSN), binlog position, transaction ID with proper semantics, Kafka offset, or outbox event position. Do not assume an application timestamp can substitute for a database watermark.

## 3. Bootstrap Strategies

No single procedure fits every system. The choice depends on the data source, ability to pause writes, load level, and consistency requirements.

| Strategy | Approach | When suitable | Main risk |
| --- | --- | --- | --- |
| Maintenance window | Stop writes, load snapshot, switch alias, resume writes | Small datasets, downtime acceptable | Long downtime if import is slow |
| Snapshot + CDC | Take consistent snapshot, replay log after watermark | Live systems needing minimal downtime | Requires CDC and offset management |
| Snapshot + transactional outbox | Snapshot source, replay outbox past corresponding boundary | Applications controlling transactions and events | Requires outbox, ordering, and retention design |
| Overlap + source version | Run snapshot and events concurrently, reject older versions | Lacking a clean snapshot/log boundary | Needs monotonic versions and proper delete handling |
| Dual-write | Application writes to both old and new indexes | Only when backed by explicit retries/reconciliation | Two writes are non-atomic, prone to drift |

For systems receiving continuous writes, a snapshot combined with CDC or outbox is usually the easiest approach to prove zero lost changes.

### 3.1. Maintenance Window

If all writes can be paused temporarily:

1. Block create/update/delete requests.
2. Wait for in-flight transactions to finish.
3. Take a source snapshot.
4. Load the snapshot into the new index.
5. Refresh and verify the index.
6. Switch the alias.
7. Re-enable writes.

Since no changes occur while the snapshot and new index are built, no event replay is needed. This is simple, though downtime can be lengthy.

### 3.2. Snapshot + CDC

CDC reads the database transaction log and records inserts, updates, and deletes in commit order. A CDC connector can usually provide a log position matching a snapshot.

Workflow:

1. Start CDC and establish the starting position.
2. Create a consistent snapshot tied to that log position.
3. Load the snapshot into the new index.
4. Replay CDC events starting after the snapshot position.
5. Keep consuming new events during verification.
6. Cut over once the target catches up to a verified watermark.

Crucially, snapshot and log position must be coordinated via the database/CDC connector's mechanism. Never grab system clock time before querying and assume it forms an exact transaction boundary.

### 3.3. Snapshot + Transactional Outbox

If the application manages business changes itself, a transactional outbox is a strong option:

- Business transactions update data tables and insert outbox events within the same transaction.
- A publisher reads the outbox and forwards events to a message broker.
- A projector reads events and updates Elasticsearch.

Because events commit in the same source transaction, the application avoids scenarios where the database commits yet event publishing fails.

To bootstrap, identify the outbox boundary corresponding to the snapshot. You can use a database consistent snapshot paired with an outbox watermark/ID captured inside the appropriate transaction scope. If synchronized snapshot-offset tooling is unavailable, use overlap with versioning and reconciliation instead of estimated timestamps.

### 3.4. Dual-Write Does Not Guarantee Consistency by Itself

A common idea is having the application call Elasticsearch twice after every database write: once to the old index and once to the new index.

If the database commits yet the second Elasticsearch write fails, the two indexes diverge. If a request times out after Elasticsearch wrote yet before the client received a response, retries can repeat side effects. Two writes do not form a distributed transaction.

If dual-write is still used, you need an outbox or durable retries, stable IDs, versioning, per-target error monitoring, and reconciliation. Plain dual-write is not a zero-data-loss guarantee.

## 4. Choosing the Right Watermark for the Snapshot

The watermark is the most critical piece of the workflow. It defines which events are already reflected in the snapshot and which must be replayed.

Example:

~~~text
Database transaction log
       |
       +-- LSN 100: update P-1
       |
       +-- LSN 101: create P-2
       |
       +-- LSN 102: snapshot boundary
       |
       +-- LSN 103: change price P-1
       |
       +-- LSN 104: delete P-2
       |
       +-- LSN 105: create P-3

Snapshot reflects state as of LSN 102.
Replay changes after LSN 102.
~~~

When replaying, define inclusive/exclusive semantics clearly. If the snapshot already includes the transaction at watermark W, replay only transactions after W. If the snapshot excludes W, replay starting from W. Skipping an event or replaying one twice must be handled intentionally.

### 4.1. Timestamps Are Not Safe Watermarks

Never rely solely on `updatedAt > bootstrapStartTime` as the only change capture mechanism.

Problems:

- Clocks across application instances can skew.
- A transaction can start earlier yet commit later.
- Multiple changes can share the same timestamp precision.
- A record might be updated without properly updating its timestamp.
- Deletes leave no row behind to query by `updatedAt`.
- A snapshot job might read a row just before an updating transaction commits.

Timestamps are useful for reconciliation or coarse filtering, but you need a log position, outbox sequence, or source version with clear semantics as the boundary.

### 4.2. CDC Position

Depending on the database, a watermark can be:

- MySQL binlog file/position or GTID.
- PostgreSQL WAL LSN or replication slot position.
- SQL Server LSN in CDC/change tracking.
- Kafka offset of the change event topic.
- A sequence stored in the outbox synchronized with the snapshot transaction.

Exact names and acquisition steps depend on the database/connector. Use the snapshot mode supported by your connector instead of stitching a log position and snapshot query together as two unrelated operations.

## 5. Creating a Consistent Snapshot

The snapshot must represent source state at a single logical point in time. If a job reads page by page while data mutates without snapshot isolation, pages can reflect different points in time.

Example:

1. Job reads page 1 at 10:00.
2. A transaction modifies a product on page 2 at 10:01.
3. Job reads page 2 at 10:02.
4. Job reads page 3 at 10:03.

The result can mix pre- and post-change state. CDC can heal discrepancies if the snapshot boundary is clean; otherwise, updates can be missed or applied out of order.

### 5.1. Using a Consistent Database Snapshot

Databases can provide transaction snapshots or snapshot export facilities. The bootstrap job reads all data under that snapshot while CDC retains transactions occurring past the corresponding position.

Avoid holding a transaction snapshot open too long if the database cannot tolerate it. Large datasets can create MVCC pressure, retain dead row versions, or bloat transaction logs. Measure snapshot duration and configure retention accordingly.

### 5.2. Paginating by Stable Keys

For large datasets, avoid deep offset pagination where the database must skip many rows per page. Keyset pagination is usually far more efficient:

~~~sql
SELECT id, name, brand_id, price, source_version
FROM product
WHERE id > :last_seen_id
ORDER BY id
LIMIT :batch_size;
~~~

This condition is safe only if:

- IDs have a stable, unique order.
- The snapshot remains consistent.
- The job saves the `last_seen_id` checkpoint only after the batch succeeds.
- No rule moves unread records across the cursor outside snapshot semantics.

When using composite keys, `ORDER BY` and cursor predicates must include all components to establish a total order.

### 5.3. Never Advance Checkpoints Before Batch Writes Finish

Suppose the job reads up to ID `P-500` and writes the batch to Elasticsearch. If it updates the checkpoint to `P-500` before bulk finishes, the process can crash after checkpointing yet before indexing completes. The next run will skip unwritten data.

Safe ordering:

1. Read batch from snapshot.
2. Transform documents.
3. Send bulk request.
4. Inspect item-level results.
5. Handle or isolate failed items.
6. Update checkpoint only once the batch reaches completion per policy.

If a batch has item failures, the checkpoint must accurately reflect handled items. You can record failed IDs for separate retry, or hold the checkpoint back from advancing past the batch until those items are resolved.

## 6. Bulk-Loading the Snapshot

Never issue one HTTP request per document when bootstrapping millions of records. Split data into batches and use the Bulk API.

General flow:

~~~text
Snapshot reader
      |
      v
Batch transformer
      |
      v
Bulk writer
      |
      v
New versioned index
      |
      v
Checkpoint store
~~~

### 6.1. Preparing the Target Index

Create the new index with a versioned name, for example:

~~~text
products-v2
~~~

Before loading data, configure:

- Exact mappings for the new document model.
- Analyzers, normalizers, and multi-fields.
- Appropriate settings and shard/replica counts.
- Ingest pipelines if any.
- Post-cutover read/write aliases.
- Version or `sourceVersion` rules.

Do not rely on dynamic mapping during large imports if data can hold heterogeneous types. A single document with a mapping error will fail at the item level in the bulk response.

### 6.2. Bulk Operations in Spring Data Elasticsearch

Spring Data Elasticsearch provides `BulkOperations` to write multiple entities:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.core.BulkMode;
import org.springframework.data.elasticsearch.core.BulkOperations;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

public class ProductBootstrapWriter {

    private final ElasticsearchOperations operations;
    private final String targetIndex;

    public ProductBootstrapWriter(
            ElasticsearchOperations operations,
            String targetIndex) {
        this.operations = operations;
        this.targetIndex = targetIndex;
    }

    public void writeBatch(List<ProductIndexDocument> batch) {
        BulkOperations bulk = operations.bulkOps(
            BulkMode.BULK,
            ProductIndexDocument.class,
            IndexCoordinates.of(targetIndex)
        );

        bulk.insert(batch);
        bulk.execute();
    }
}
~~~

This example illustrates writing a batch to a specific target index. The exact `BulkOperations` API and access to failed item details depend on your Spring Data Elasticsearch version. For pipelines needing exact per-item status/error checks, use a bulk API exposing `BulkResponse` or the appropriate Java client API.

Never mark a batch complete merely because `execute` threw no exception if the abstraction in use does not expose the level of detail required by your ingestion contract. Verify the error contract of your exact version.

### 6.3. Batch Size

No single document count fits every cluster. Bound batches by both item count and byte size:

- Small documents can pack more items per batch.
- Large documents or documents with nested fields need smaller batches.
- Complex ingest pipelines can lower throughput.
- Bulk responses also consume client-side heap.
- Oversized batches raise latency and complicate partial retries.

Benchmark on representative data while monitoring bulk `took`, client latency, 429s, and heap. Tune batch size and concurrency against real load.

## 7. Capturing Changes During Bootstrap

Once the snapshot boundary is established, retain all changes past that boundary until the target index catches up.

A minimal event should include:

~~~json
{
  "eventId": "evt-90001",
  "aggregateType": "Product",
  "aggregateId": "P-100",
  "aggregateVersion": 42,
  "operation": "UPSERT",
  "occurredAt": "2026-11-13T10:15:00Z",
  "payload": {
    "id": "P-100",
    "name": "Mechanical Keyboard",
    "price": 120
  }
}
~~~

Delete event:

~~~json
{
  "eventId": "evt-90002",
  "aggregateType": "Product",
  "aggregateId": "P-101",
  "aggregateVersion": 19,
  "operation": "DELETE",
  "occurredAt": "2026-11-13T10:16:00Z"
}
~~~

Key fields:

- `eventId` to deduplicate when the broker redelivers events.
- `aggregateId` to identify the document.
- `aggregateVersion` to reject stale events.
- `operation` to distinguish upserts from deletes.
- `payload` sufficient to build the document or apply changes.
- Log position/partition offset to track progress.

### 7.1. Full-State Events vs. Delta Events

Full-state events carry the aggregate's complete state after a change. The projector can re-index the document by stable ID. This is usually easier to retry and recover.

Delta events carry only the changed portion, such as only the new price. The projector must apply deltas in exact order and ensure no prior event is missed.

If events arrive duplicated or out of order, deltas risk producing wrong final state. Whenever possible, use full-state projections or carry source versions with strict order control.

### 7.2. Partitioning by Aggregate ID

When using Kafka or a partitioned message broker, choose `aggregateId` as the partition key. Events for the same aggregate stay ordered within that partition per broker semantics.

This lets projectors apply changes for the same document in order while processing different aggregates in parallel.

If multiple event sources can update the same document, establish a shared ordering rule or source version to decide which event is newer.

## 8. Replay and Catch-Up

Once the snapshot is loaded, start replaying changes from the watermark.

~~~text
Snapshot at W
     |
     v
Bulk load snapshot
     |
     v
Replay events after W
     |
     v
Apply updates/deletes
     |
     v
Continue consuming new events
     |
     v
Lag approaches zero
~~~

### 8.1. Replays Must Be Durable

Never buffer events solely in the memory of a single bootstrap process. If that process crashes, events must remain in the CDC log, outbox, or message broker for replay.

Consumer offsets/checkpoints must only be committed after corresponding operations succeed or are handled per error policy. Committing offsets before writing to Elasticsearch risks permanently skipping events on crash.

If Elasticsearch writes succeed yet offset commits fail, events can be redelivered. Thus, projectors must be idempotent.

### 8.2. Measuring Consumer Lag

Lag is the distance between the latest position in the change stream and the position processed by the projector.

Monitor:

- Current CDC log position.
- Committed consumer offset.
- Pending event count.
- Age of the oldest unprocessed event.
- Event production rate.
- Event processing rate.
- Failed item count and retry queue.

If source change rate exceeds replay rate, lag will never shrink. Scale projector capacity, optimize bulk writes, cut transformation cost, or throttle source concurrency if possible.

### 8.3. Catching Up to a Barrier

Do not cut over simply because consumer lag happens to look near zero at an arbitrary instant.

Define a barrier:

1. Capture high watermark H of the change stream.
2. Confirm the target has processed all events up to H.
3. Confirm zero unresolved failed batches exist prior to H.
4. Confirm all partitions have reached their corresponding offsets.
5. Execute cutover while consumers keep processing new events.

With multiple partitions, the barrier is a per-partition offset map rather than a single scalar number.

## 9. Handling Race Conditions Between Snapshots and Events

This is the trickiest part of bootstrapping. Snapshots and events can arrive at the target out of source change order.

### 9.1. Stale Snapshot Writing After a Newer Event

Timeline:

~~~text
Source:
  v10: price = 100
  v11: price = 120

Target:
  1. Event v11 replayed -> price = 120
  2. Snapshot v10 bulk-written later -> price = 100

Wrong result: target regresses to v10
~~~

There are two main ways to prevent this:

- Ensure the snapshot finishes writing before event replay begins.
- Or use source versions so the target rejects older versions.

In large systems, enforce both: an explicit pipeline sequence plus version guards protecting against retries, resumes, or unexpected races.

### 9.2. Storing Source Version in the Document

Each aggregate should have a monotonically increasing version on state changes:

~~~json
{
  "id": "P-100",
  "name": "Mechanical Keyboard",
  "price": 120,
  "sourceVersion": 11
}
~~~

Both snapshots and events carry `sourceVersion`. The projector applies only records newer than the already-written state.

Do not confuse business `sourceVersion` with Elasticsearch's internal `_version`. Elasticsearch `_version` is index-local document metadata; `sourceVersion` belongs to the authoritative data source.

### 9.3. External Versioning

Elasticsearch supports external versioning for the Index API and bulk index operations. The application passes versions obtained from the source:

- `external`: accepts only versions strictly greater than the stored version.
- `external_gte`: accepts versions greater than or equal to the stored version.

Conceptual example with the Java API Client:

~~~java
import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch._types.VersionType;
import co.elastic.clients.elasticsearch.core.BulkRequest;
import co.elastic.clients.elasticsearch.core.BulkResponse;

BulkRequest.Builder request = new BulkRequest.Builder();

for (ProductIndexDocument document : batch) {
    request.operations(operation -> operation
        .index(index -> index
            .index(targetIndex)
            .id(document.id())
            .version(document.sourceVersion())
            .versionType(VersionType.ExternalGte)
            .document(document)
        )
    );
}

BulkResponse response = elasticsearchClient.bulk(request.build());
~~~

This snippet illustrates the Java client API. Verify exact packages, enum constants, and builder methods against your project's Elasticsearch Java API Client version.

With external versioning:

- Snapshot version 10 arriving after event version 11 is rejected.
- Event version 12 is accepted after version 11.
- Resending event version 12 with `external_gte` can be accepted again.

`external_gte` is safe only when a given source version always maps to the exact same document state. If two different payloads share the same version, the later payload can overwrite the earlier one. Ensure versions are unique per state, or use strict `external` versioning with appropriate deduplication.

### 9.4. Versions Must Be Monotonic per Document

Do not use millisecond timestamps as versions if concurrent updates or clock skew can occur. Better choices:

- Aggregate versions incremented inside source transactions.
- Database-assigned sequence numbers.
- Durably managed per-aggregate event sequences.

Versions must increase in business order for the same document. Different documents do not need a shared global sequence unless the source provides one.

## 10. Handling Deletes to Prevent Document Resurrection

Deletes are frequently overlooked during bootstrapping.

Timeline:

1. Snapshot reads `P-100` while it still exists.
2. User deletes `P-100`.
3. Delete event is applied to the new index.
4. Slow snapshot job writes `P-100` to the new index after the delete.

The deleted document reappears.

### 10.1. Tombstones

One solution is representing deletes with tombstones:

~~~json
{
  "id": "P-100",
  "sourceVersion": 15,
  "deleted": true,
  "deletedAt": "2026-11-13T10:16:00Z"
}
~~~

The tombstone retains the delete operation's version. Product read queries must filter `deleted=false`. When stale snapshot version 14 arrives late, the version guard rejects it because the tombstone already holds version 15.

Tombstones must be kept long enough that no stale snapshots, event retries, consumer replays, or recovery jobs can rewrite pre-delete data.

Once past the retention window and confirmed free of old events, a cleanup job can purge tombstones.

### 10.2. Why Not Always Use Physical Deletes?

Elasticsearch retains deleted document version info for a bounded period via `gc_deletes`. Never rely on that delete metadata to block stale events across long replay windows or backup restores.

If an older upsert arrives after delete metadata has been garbage collected, the document can be recreated. A tombstone document with a durable `sourceVersion` gives the projector the information needed to reject stale records.

### 10.3. Delete Events Must Also Be Versioned

Delete events must carry a version newer than prior states. Never process deletes as unconditional removals if stale events can arrive late.

If the source lacks aggregate versions, you need a durable sequence or tombstone ledger capable of distinguishing newer deletes from stale upserts.

## 11. Idempotency and Handling Redelivered Events

CDC connectors, message brokers, or consumers can redeliver events during retries. A safe projector must tolerate processing the same event multiple times without corrupting final state.

Principles:

- Derive stable document IDs from business keys.
- Give each event a unique `eventId`.
- Give each aggregate a monotonically increasing `sourceVersion`.
- Write documents using deterministic state assignment whenever possible.
- Deduplicate events or enforce version guards.
- Never increment counters via addition without duplicate protection.

### 11.1. At-Least-Once and Exactly-Once

Many CDC/message broker pipelines provide at-least-once delivery: events can be redelivered, yet should not be dropped when consumers retry properly.

Never assume the end-to-end path from database through broker to Elasticsearch shares an exactly-once transaction. Instead, build idempotent projectors so redeliveries never corrupt data.

### 11.2. Full-State Upserts Recover More Easily Than Deltas

If events carry full post-change product state, the projector can re-index the same document ID and `sourceVersion`. Duplicate events can be skipped or safely reapplied per version policy.

If events carry only deltas like incrementing stock by 1, redeliveries can increment stock twice. You need durable event deduplication or recomputing state from the source of truth.

## 12. Designing the Bootstrap Projector

The projector transforms snapshot rows or change events into Elasticsearch documents.

Use the exact same transformation rules for both snapshots and events:

~~~text
Snapshot row ------+
                   |
                   v
              Document mapper
                   |
                   v
              Index document
                   ^
                   |
Change event ------+
~~~

If snapshots and events use two different mappers, the same source record can yield two different document shapes, leading to mismatched fields, mappings, or search behavior.

### 12.1. Shared Mapper

~~~java
public class ProductDocumentMapper {

    public ProductIndexDocument fromSnapshot(ProductRow row) {
        return new ProductIndexDocument(
            row.id(),
            row.name(),
            row.price(),
            row.version(),
            false
        );
    }

    public ProductIndexDocument fromEvent(ProductChanged event) {
        return new ProductIndexDocument(
            event.productId(),
            event.name(),
            event.price(),
            event.aggregateVersion(),
            false
        );
    }
}
~~~

This is an illustrative example. If events carry only deltas, the mapper must fetch full state or the projector must apply deltas sequentially by version.

### 12.2. Persisting Progress State

A bootstrap job typically persists:

~~~json
{
  "jobId": "products-v2-bootstrap",
  "targetIndex": "products-v2",
  "snapshotBoundary": "LSN-102",
  "snapshotCursor": "P-50000",
  "snapshotCompleted": true,
  "replayPosition": "LSN-150",
  "cutoverBarrier": null,
  "status": "CATCHING_UP"
}
~~~

Checkpoints must be stored durably, not solely in worker memory. When the process restarts, it resumes from the confirmed cursor/offset.

## 13. Separating Snapshot Writers and Change Projectors

Snapshot loaders and event projectors can run concurrently, provided they share the same version policy and target index.

One model:

~~~text
Snapshot worker
    |
    +----> Read consistent snapshot
    |
    +----> Transform batches
    |
    +----> Bulk write with sourceVersion
                    |
                    v
                products-v2
                    ^
                    |
Change projector     |
    |                |
    +----> Read CDC/outbox
    |
    +----> Apply upsert/delete with sourceVersion
~~~

If both writers can touch the same document, external versioning or per-aggregate serialization is mandatory. Without a version guard, enforce snapshot completion before starting replay.

### 13.1. Only One Component Owns the Version Policy

Never let the snapshot worker use one ID/version rule and the event projector use another. Both must agree on:

- Identical document IDs.
- Identical `sourceVersion` semantics.
- Identical transformation logic.
- Identical delete/tombstone behavior.
- Identical stale-version handling rules.

If events carry version 20 yet snapshot rows lack corresponding versions, external versioning cannot reliably resolve races. Add source versioning or adjust the bootstrap sequence.

## 14. Cutover via Aliases

Once the new index is loaded and caught up to the change stream, switch the application to the new index.

Never edit index names across every service or configuration in scattered steps. Use aliases to keep logical names stable.

Example:

~~~text
products-read  -> products-v1
products-write -> products-v1
~~~

After bootstrapping:

~~~text
products-read  -> products-v2
products-write -> products-v2
~~~

### 14.1. Separating Read and Write Aliases

The read alias serves queries. The write alias serves writes. Both aliases can switch in one alias update call.

This ensures:

- Applications never hardcode active physical indexes.
- New index versions can be built in parallel.
- Cutover occurs via a cluster state update.
- The old index can remain intact for rollback.

When an alias points to multiple indexes, define the write index explicitly. For read aliases, avoid exposing the same document in both old and new indexes simultaneously, which returns duplicate results.

### 14.2. Atomic Alias Switch

Elasticsearch supports multiple alias actions in a single request:

~~~http
POST /_aliases
{
  "actions": [
    {
      "remove": {
        "index": "products-v1",
        "alias": "products-read"
      }
    },
    {
      "add": {
        "index": "products-v2",
        "alias": "products-read"
      }
    },
    {
      "remove": {
        "index": "products-v1",
        "alias": "products-write"
      }
    },
    {
      "add": {
        "index": "products-v2",
        "alias": "products-write",
        "is_write_index": true
      }
    }
  ]
}
~~~

Alias actions inside one request apply as a single unified cluster state change. This avoids any window where applications see the alias removed before being attached to the new index.

### 14.3. Pre-Cutover Barrier

A safe cutover sequence:

1. Record high watermark H from CDC/outbox.
2. Wait for the projector to process up to H on the new index.
3. Confirm zero unresolved item errors exist before H.
4. Keep consuming new events past H.
5. Switch read and write aliases in one alias request.
6. Verify aliases point to the new index.
7. Continue monitoring lag and errors.

If the application writes directly to Elasticsearch instead of going through a source event stream, use another barrier: briefly pause writers, drain in-flight requests, apply remaining changes, and then switch. Never cut over while writers are still hitting the old index without mirroring to the new index.

### 14.4. Spring Data and Aliases

You can point `@Document` `indexName` to a logical alias instead of a physical index name:

~~~java
@Document(indexName = "products-write")
public class ProductIndexDocument {
    // ...
}
~~~

Read operations can use `products-read` via `IndexCoordinates` or corresponding configuration. When aliases switch targets, application code keeps using stable alias names.

During bootstrap, the writer should target the new physical index explicitly so it does not accidentally write to the live production alias. After cutover, normal operations use the write alias.

## 15. Validating the New Index Before Switching Aliases

Do not check only total document count. Two indexes can have identical counts while holding different data.

### 15.1. Count Checks

Compare:

- Source row count in the snapshot.
- Bulk-indexed document count.
- Tombstone count.
- Replayed event count.
- Pending failed item count.
- Counts by partition, tenant, or category.

If the source applies a filter excluding records, compute expected counts using that exact same predicate.

### 15.2. Sample Content Checks

Sample IDs from both the source and the new index, comparing:

- IDs.
- Required fields.
- Transformed fields.
- `sourceVersion`.
- `deleted` state.
- Relations/nested objects.
- Fields used for filtering, sorting, and aggregations.

Deliberately sample across data segments: newly created records, recently updated records, records with missing fields, records with many nested entries, and deleted records.

### 15.3. Real Query Checks

Run representative query suites against the new index:

- Full-text search.
- Keyword filters.
- Range queries.
- Sorting.
- Aggregations.
- Nested queries if present.
- Pagination.
- Tombstone-excluding queries.

New mappings and analyzers can alter relevance or filter results even when document counts match.

### 15.4. Freshness Checks

Confirm the target has processed up to the barrier offset. Measure event lag by both count and event age. Do not cut over while unresolved poison events remain if they can affect business results.

## 16. Error Handling and Resuming After Crashes

Bootstrapping can run for hours or days. Jobs must be able to stop and resume without missing or corrupting data.

### 16.1. Snapshot Checkpoints

Persist the cursor after a batch is completely handled. If the job crashes:

1. Read the last checkpoint.
2. Reopen the consistent snapshot if still valid.
3. Resume from the saved cursor.
4. If the snapshot is no longer valid, take a fresh snapshot and re-establish the watermark/replay window.

Never resume an old cursor against a brand-new snapshot without proving compatible semantics.

### 16.2. Bulk Item Failures

The Bulk API can return HTTP 200 while individual items fail. You must:

- Read `errors` and each item response.
- Retry transient failures like 429 with backoff.
- Fix mappings or data for permanent errors.
- Write failures to a dead-letter queue when they cannot be handled immediately.
- Never mark a batch complete if items still lack a terminal policy state.

Never blindly retry the entire batch. Already-succeeded items could be rewritten or trigger duplicate side effects if operations are non-idempotent.

### 16.3. Redelivered Replay Events

If an event was written to Elasticsearch yet the consumer crashed before committing its offset, the event will be redelivered. Use `eventId`, `sourceVersion`, and idempotent operations so the final state remains unchanged.

### 16.4. Poison Events

An event with bad mappings or invalid data can make a consumer fail repeatedly. Never let one poison event block all subsequent events indefinitely if the architecture allows isolation.

Send the event to a dead-letter queue with:

- Event ID.
- Aggregate ID/version.
- Log position or offset.
- Error type/reason.
- Sanitized payload.
- Attempt count.

After fixing the bug, replay the event in order or rebuild the affected aggregate. Skip an event only with an explicit business decision and reconciliation confirming target state.

## 17. Post-Cutover Rollback

Keep the old index during a rollback window. However, rollback is safe only when you know which changes the old index received after cutover.

### 17.1. Keeping Both Indexes Updated During the Observation Window

For a brief window after cutover, the projector can keep writing to both the new and old indexes. If the new index exhibits severe issues, switch the read alias back to the old index.

This increases write load and requires version/offset control on both targets. Maintain dual projection only for an intentional, bounded period.

### 17.2. If the Old Index Stopped Receiving Updates

If only the new index receives events after cutover, the old index grows progressively stale. Rolling back then forces the application back onto stale data.

Options:

- Continue dual-projecting during the rollback window.
- Before rolling back, replay the change stream into the old index up to a fresh barrier.
- Build another rollback index from the source of truth.

Never delete the old index right after cutover before finishing the observation period and having a valid recovery copy.

## 18. Approach When the Legacy Source Is an Elasticsearch Index

If legacy data lives in an Elasticsearch index instead of a database, you still need a snapshot and change capture. Use Point in Time (PIT) with `search_after` to read a stable view of the old index.

### 18.1. PIT and `search_after`

PIT maintains a consistent view of the index while reading. `search_after` paginates by sort values rather than deep offsets.

Example query:

~~~http
POST /products-v1/_pit?keep_alive=2m
~~~

Then search on the PIT:

~~~http
POST /_search
{
  "pit": {
    "id": "PIT_ID",
    "keep_alive": "2m"
  },
  "size": 500,
  "sort": [
    { "_shard_doc": "asc" }
  ],
  "query": {
    "match_all": {}
  }
}
~~~

Subsequent pages pass `search_after` with the sort values of the last hit. Keep the PIT alive and persist cursors durably as you scan.

### 18.2. PIT Does Not Capture Post-Snapshot Changes

PIT gives a stable view of the index at the moment the PIT was created. It does not automatically provide a change log to update the target with subsequent writes.

If the application continues writing to the old index, you must:

- Mirror new changes to the target via application-level outbox/events.
- Or pause writes during the snapshot and cutover phases.
- Or maintain an independent change log for replay.

Never open a PIT, read all documents, and assume the target has caught up to writes made after PIT creation.

### 18.3. Reindex API

Elasticsearch's Reindex API copies documents from a source index to a destination index. However, a single reindex call does not automatically resolve concurrent changes if the source continues mutating.

When using the Reindex API:

- Create target mappings/settings first.
- Specify source and target clearly.
- Handle version/conflicts if applicable.
- Use change capture or a maintenance window for new changes.
- Verify task completion and failures.

The Reindex API also does not create a cross-index transaction between the old and new indexes.

## 19. Common Pitfalls

**Scanning data and immediately cutting over.** Changes occurring during the scan may be missing from the new index. Use CDC/outbox or a maintenance window.

**Starting CDC long after the snapshot began.** Changes occurring before capture started can be lost. Start capture first or coordinate the snapshot with a log position.

**Using timestamps as the sole watermark.** Transaction commit order, clock skew, and timestamp precision create gaps. Use log sequences or outbox positions with clear semantics.

**Not using a consistent snapshot.** Pages can reflect different points in time. Use appropriate transaction snapshots or CDC connectors with snapshot mode.

**Letting snapshots overwrite newer events.** Stale data can beat newer data in a race. Enforce snapshot-before-replay sequencing or source version guards.

**Ignoring delete events.** Documents deleted during bootstrap can resurrect when snapshots write late. Use tombstones/versioning or enforce replay and snapshot order.

**Physical deletes assuming versions stay forever.** Delete metadata has finite retention. Durable tombstones fit long replay windows better.

**Using delta events without order control.** Redelivered or out-of-order events corrupt state. Use aggregate versions, partition keys, or full-state events.

**Committing consumer offsets before writing the target.** Crashes can drop events from replay. Commit after writes or durably persisting processing state.

**Not checking bulk item failures.** HTTP 200 can still hide failed documents. Inspect every item and retry the failed subset.

**Advancing checkpoints before bulk finishes.** Crashes can cause jobs to skip unwritten data. Advance checkpoints only after batches reach terminal state.

**Treating direct dual-write as a transaction.** One target can succeed while the other fails. Use outbox, retries, and reconciliation.

**Cutting over while consumer lag remains high.** The new index does not yet reflect recent changes. Wait for a barrier offset and resolve pre-barrier failures.

**Comparing document counts only.** Equal counts do not prove equal contents. Compare versions, samples, aggregates, and real queries.

**Deleting the old index right after cutover.** Loses fast rollback and comparison baselines. Keep the old index for the retention window.

**Rolling back to a stale old index.** After cutover, the old index may stop receiving new changes. Continue dual-projecting or replay before rolling back.

## 20. Safe Bootstrap Workflow

A practical workflow can follow these steps:

1. Identify the source of truth and the new versioned target index.
2. Create required mappings, settings, analyzers, and aliases for the target.
3. Ensure all source changes write durably to CDC/outbox.
4. Start capture before taking the snapshot and establish a consistent watermark.
5. Open a consistent snapshot at the chosen boundary.
6. Read the snapshot via stable keyset/cursor pagination.
7. Transform data using the exact same mapper used for event projections.
8. Bulk write to target, inspect item results, and save checkpoints.
9. Once the snapshot completes, replay the change stream past the watermark.
10. Use `sourceVersion`, idempotency, and tombstones to block stale writes, duplicates, and resurrections.
11. Keep catching up while validating data and queries.
12. Record a barrier offset and wait for the target to catch up to it.
13. Confirm zero unresolved item failures exist before the barrier.
14. Verify counts, versions, samples, delete states, and business queries.
15. Switch read/write aliases in a single alias request.
16. Continue running consumers on the new index and monitor lag/errors.
17. Retain the old index during the rollback window or keep dual-projecting.
18. After stability is confirmed, clean up the old index and tombstones per retention policy.

## 21. Example Architecture with Spring Data Elasticsearch

A clean design separates three components:

- Snapshot reader reading source data via a consistent snapshot.
- Document mapper producing the same `ProductIndexDocument` shape for snapshots and events.
- Elasticsearch writer bulk-indexing documents into the target index.
- Event projector processing CDC/outbox events and enforcing version guards.

### 21.1. Document Model

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products-write")
public class ProductIndexDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Double)
    private double price;

    @Field(type = FieldType.Long)
    private long sourceVersion;

    @Field(type = FieldType.Boolean)
    private boolean deleted;

    // Constructors, getters and setters
}
~~~

`sourceVersion` is the business version from the source. `deleted` represents a tombstone if the system stores delete markers in the index.

### 21.2. Shared Mapper

~~~java
public class ProductIndexMapper {

    public ProductIndexDocument fromSnapshot(ProductRow row) {
        ProductIndexDocument document = new ProductIndexDocument();
        document.setId(row.id());
        document.setName(row.name());
        document.setPrice(row.price());
        document.setSourceVersion(row.version());
        document.setDeleted(false);
        return document;
    }

    public ProductIndexDocument fromEvent(ProductChanged event) {
        ProductIndexDocument document = new ProductIndexDocument();
        document.setId(event.productId());
        document.setName(event.name());
        document.setPrice(event.price());
        document.setSourceVersion(event.aggregateVersion());
        document.setDeleted(false);
        return document;
    }

    public ProductIndexDocument tombstone(ProductDeleted event) {
        ProductIndexDocument document = new ProductIndexDocument();
        document.setId(event.productId());
        document.setSourceVersion(event.aggregateVersion());
        document.setDeleted(true);
        return document;
    }
}
~~~

This is a condensed example. A production mapper must handle all fields, null semantics, nested objects, analyzer inputs, and schema versions.

### 21.3. Snapshot Reader and Bulk Writer

~~~java
public class ProductBootstrapService {

    private final ProductSnapshotRepository source;
    private final ProductIndexMapper mapper;
    private final ProductBootstrapWriter writer;
    private final BootstrapCheckpointStore checkpoints;

    public void bootstrap(SnapshotHandle snapshot) {
        String cursor = checkpoints.lastProductId();

        while (true) {
            List<ProductRow> rows =
                source.readNextPage(snapshot, cursor, 500);

            if (rows.isEmpty()) {
                break;
            }

            List<ProductIndexDocument> documents = rows.stream()
                .map(mapper::fromSnapshot)
                .toList();

            writer.writeBatch(documents);

            cursor = rows.get(rows.size() - 1).id();
            checkpoints.saveLastProductId(cursor);
        }

        checkpoints.markSnapshotCompleted();
    }
}
~~~

This illustrates keyset cursors and checkpoints. In production, the writer must return per-item results; save the checkpoint only when every document in the batch succeeded or entered durable retry/DLQ storage per policy. `SnapshotHandle` must maintain the same consistent snapshot or represent an already materialized snapshot.

### 21.4. Event Projector

~~~java
public class ProductChangeProjector {

    private final ProductIndexMapper mapper;
    private final VersionAwareProductWriter writer;
    private final EventCheckpointStore checkpoints;

    public void handle(ProductEvent event) {
        switch (event.type()) {
            case PRODUCT_CHANGED ->
                writer.upsert(mapper.fromEvent(event.asChanged()));
            case PRODUCT_DELETED ->
                writer.upsert(mapper.tombstone(event.asDeleted()));
        }

        checkpoints.markProcessed(event.position());
    }
}
~~~

`VersionAwareProductWriter` must apply `sourceVersion` atomically on write. If the event is older than the current document, it must not overwrite. If the write succeeds and the process crashes before committing offsets, the event is redelivered and the subsequent write must be idempotent.

### 21.5. Why Not Just Use `ElasticsearchOperations.save`?

`ElasticsearchOperations.save` works well for standard writes using Spring Data mappings. However, if bootstrapping lets snapshots and events run concurrently, source version protection is essential.

Do not assume `save` automatically uses a `sourceVersion` field in the entity to reject stale writes. `sourceVersion` is merely a field in `_source` unless the application maps it to external versioning or executes conditional checks/writes itself.

When external versioning or per-item versioned bulk writes are required, use the Elasticsearch Java API Client or a Spring Data API exposing version semantics in your project version.

## 22. Pre-Cutover Checklist

Before switching aliases, verify:

- [ ] Target index has accurate mappings/settings.
- [ ] Snapshot was read from a consistent view.
- [ ] Snapshot boundary and change stream position were established.
- [ ] Change capture started prior to or cleanly aligned with the snapshot.
- [ ] All snapshot pages were written and checkpointed accurately.
- [ ] Bulk item failures have been handled.
- [ ] Post-watermark events have been replayed.
- [ ] Consumers caught up to the cutover barrier.
- [ ] Duplicate events do not corrupt data.
- [ ] Stale events do not overwrite newer versions.
- [ ] Deletes do not resurrect documents.
- [ ] Counts, samples, `sourceVersion`, and business queries are verified.
- [ ] Read alias and write alias have explicit targets.
- [ ] Rollback plan and old index retention are ready.

## 23. References

- [Elasticsearch - Bulk API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-bulk): bulk indexing, per-item responses, and error handling.
- [Elasticsearch - Index API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-index): document IDs, versioning, and index operations.
- [Elasticsearch - Optimistic concurrency control](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/optimistic-concurrency-control): sequence numbers, primary terms, and conditional writes.
- [Elasticsearch - Aliases](https://www.elastic.co/guide/en/elasticsearch/reference/current/aliases.html): alias actions and switching target indexes.
- [Elasticsearch - Point in Time API](https://www.elastic.co/guide/en/elasticsearch/reference/current/point-in-time-api.html): maintaining a stable view while reading and paginating.
- [Elasticsearch - Reindex API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-reindex.html): copying documents between indexes and tracking tasks.
- [Spring Data Elasticsearch - Bulk operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html): `BulkOperations` and `ElasticsearchOperations`.
- [Debezium - Snapshotting](https://debezium.io/documentation/reference/stable/connectors/index.html): snapshot and change capture mechanisms of CDC connectors.
- [Debezium - Outbox Event Router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html): emitting events from a transactional outbox.

Specific API names, builder methods, and snapshot/CDC mechanisms depend on your Spring Data Elasticsearch, Elasticsearch Java API Client, database, and connector versions. Consult the documentation matching your running dependencies and infrastructure. The core rules remain: snapshots need a consistent boundary, every post-boundary change must be retained and replayed, and versioning/idempotency/tombstones protect the target against duplicate or out-of-order events.
