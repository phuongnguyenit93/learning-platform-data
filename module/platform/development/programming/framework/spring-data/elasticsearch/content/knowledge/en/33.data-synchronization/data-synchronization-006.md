# Propagating Delete Changes, Tombstones, and Preventing Resurrection of Old Documents

## 1. The Problem When Syncing Delete Operations

A system typically has a source database with Elasticsearch serving as a read model for search. The application writes data to the database, and a synchronization pipeline forwards changes to Elasticsearch via a message broker, CDC, or a transactional outbox.

For creates and updates, the sync pipeline typically sends a new document or an update. For deletes, the database may physically remove the row. If the sync pipeline only reads existing rows, it no longer has data indicating that a document must be removed from Elasticsearch.

For example:

1. Order `order-42` exists in both the database and Elasticsearch.
2. A user deletes the order in the database.
3. A delete event is emitted, though the consumer is temporarily paused.
4. Another worker or an old retry still sends a prior update event.
5. Elasticsearch receives the older payload and recreates document `order-42`.

A deleted document can reappear. This phenomenon is commonly called **resurrection** (or stale document resurrection).

The root cause is usually not the Delete API itself. The problem is that the system does not retain enough information to distinguish a newer change from a late-arriving older event.

To propagate deletes safely, you must transmit a trace of the delete operation, establish version ordering per entity, and reject any record older than the applied state.

## 2. What Is a Tombstone?

A **tombstone** is a marker indicating that an entity was deleted at a specific version or point in time. A tombstone can be an event in an event stream, a document marked deleted in Elasticsearch, or a separate metadata record.

Example tombstone for an order:

~~~json
{
  "id": "order-42",
  "operation": "DELETE",
  "sourceRevision": 18,
  "deletedAt": "2026-11-13T10:15:30Z",
  "eventId": "evt-9f8a"
}
~~~

A tombstone carries critical information:

- Which entity was deleted.
- The source revision at the time of deletion.
- The timestamp or position of the change.
- Event ID for deduplication and tracing.
- Routing or partition key if needed to target the right shard.

A tombstone indicates that the entity's latest state is deleted. When an older event arrives, the consumer compares the event's revision against the tombstone's revision and rejects the stale event.

### How Does a Tombstone Differ from a Soft Delete?

A soft delete is typically how deletion state is represented in business data, for example:

~~~json
{
  "id": "order-42",
  "deleted": true,
  "deletedAt": "2026-11-13T10:15:30Z"
}
~~~

A soft delete can act as a tombstone if it preserves sufficient revision metadata and serves as a guard against older events.

However, a `deleted=true` flag does not automatically prevent resurrection. If the application removes this document later and then receives an old upsert, Elasticsearch no longer has a marker to reject that upsert.

### Tombstones Do Not Need to Keep the Full Document

In many systems, a tombstone only needs the ID, source revision, deletion timestamp, and essential metadata. When personal data or sensitive payloads must be purged, you can replace the document content with a minimal tombstone.

Tombstones should retain enough information to block resurrection without retaining business data that needed to be deleted.

## 3. Three Delete Concepts to Distinguish in Elasticsearch

In Elasticsearch, several mechanisms relate to "deletion," but they serve different purposes.

| Mechanism | Meaning | Durable business tombstone? |
|---|---|---|
| Delete API | Removes a document from queryability | No |
| Elasticsearch internal soft deletes | Retains operation history for replication/recovery | No |
| Application tombstone | Document or event marking an entity deleted alongside its source revision | Yes, if retained and checked properly |

### Delete API

Example:

~~~http
DELETE /orders/_doc/order-42
~~~

The document no longer appears in search results once the change becomes searchable. Elasticsearch retains version metadata of the deleted document for a short period to handle concurrent operations.

That window is governed by `index.gc_deletes`, whose current default is 60 seconds. After delete metadata is garbage collected, Elasticsearch no longer retains that deletion version marker for subsequent versioned operations.

Therefore, the Delete API does not provide an application tombstone that persists indefinitely.

### Internal Soft Deletes

Elasticsearch uses soft deletes at the storage layer to preserve operation history needed for mechanisms like peer recovery and cross-cluster replication. This is an internal engine detail.

Internal soft deletes are not a `deleted=true` document that applications can rely on to decide whether a CDC event is stale. Shard history retention and retention leases are also not business tombstone retention policies.

### Application Tombstones

An application tombstone is data actively created and maintained by the application. For example, instead of calling the Delete API, the consumer indexes a minimal document with the same ID and a newer revision:

~~~json
{
  "id": "order-42",
  "sourceRevision": 18,
  "deleted": true,
  "deletedAt": "2026-11-13T10:15:30Z",
  "lastEventId": "evt-9f8a"
}
~~~

This document remains in the index and preserves revision 18. A stale upsert with revision 17 is rejected when using external versioning.

## 4. Why Can Old Documents Resurrect?

Suppose the database emits two events for the same order:

| Revision | Event | Content |
|---:|---|---|
| 17 | UPDATE | Order in `PAID` status |
| 18 | DELETE | Order deleted |

With parallel consumers, the DELETE event at revision 18 can reach Elasticsearch first. The consumer calls the Delete API and the document vanishes.

Later, a worker retries the UPDATE event at revision 17. If the worker calls the Index API with a standard write, Elasticsearch can recreate the document because that ID no longer exists.

Timeline:

~~~text
Database source
   |
   +-- revision 17: UPDATE order-42
   |
   +-- revision 18: DELETE order-42
             |
             v
        Event broker
             |
       +-----+------+
       |            |
       v            v
   Consumer B   Consumer A
       |            |
       |            +-- DELETE order-42
       |                     |
       |                     v
       |              Document deleted
       |
       +-- late UPDATE revision 17
                    |
                    v
              Index order-42
                    |
                    v
             Document resurrected
~~~

If a system relies solely on message arrival order, it is highly vulnerable to retries, parallel partitions, consumer restarts, or reprocessing.

You need a comparable revision across every event for the same entity. Consumers use that revision to protect the latest state.

## 5. Fundamental Rule: Source Revisions Must Increase Monotonically

Every change to an entity needs a monotonically increasing revision. This revision is generated at the data source and carried in events.

Example:

| Change | Source revision |
|---|---:|
| Create order | 1 |
| Change shipping address | 2 |
| Confirm payment | 3 |
| Update delivery status | 4 |
| Delete order | 5 |

The revision of a delete operation must be strictly greater than all previous change revisions.

If an entity is recreated according to business rules, the new revision must also be greater than the preceding tombstone. For instance, if the tombstone is revision 5, a valid recreation takes revision 6.

Avoid relying solely on an `updated_at` timestamp as a version whenever possible:

- Two changes can share the same timestamp due to clock resolution.
- Multiple services can have skewed clocks.
- A retried message may carry an older timestamp.
- Time does not necessarily reflect the commit order of the data source.

You can use an incrementing revision column in the database, a per-entity sequence, or a source change position with clear semantics. If using CDC LSN/offsets, ensure the values are comparable within the entity scope and remain meaningful across partition or source changes.

An event should carry an explicit source revision:

~~~json
{
  "eventId": "evt-9f8a",
  "aggregateId": "order-42",
  "revision": 18,
  "type": "ORDER_DELETED",
  "occurredAt": "2026-11-13T10:15:30Z",
  "routing": "customer-7"
}
~~~

The consumer must never invent a new revision based on message receipt time. It must use the revision assigned by the source.

## 6. Sync Event Format

A sync event should carry enough data for the consumer to apply the change without guessing from current state.

Java record example:

~~~java
import java.time.Instant;

public record OrderSyncEvent(
    String eventId,
    String orderId,
    long revision,
    Operation operation,
    OrderPayload payload,
    String routing,
    Instant occurredAt
) {
    public enum Operation {
        UPSERT,
        DELETE
    }
}
~~~

Key principles:

- Unique `eventId` for tracing and deduplication.
- `orderId` remains stable across the entity lifecycle.
- `revision` increases monotonically per entity.
- `operation` distinguishes upsert from delete.
- `payload` can be null for delete events.
- `routing` preserves the exact value used when indexing the document.
- `occurredAt` serves observability and investigation, never replacing revision.

If the consumer must re-fetch data from the database upon receiving an event, be careful: an old UPDATE event could read the latest database state and inadvertently write newer content with an older revision. Payload and source revision must remain consistent with each other.

With CDC, delete events often only contain the pre-delete state (before image) or operation metadata. Ensure the CDC connector and configuration do not strip delete events, IDs, revisions, or required routing.

## 7. Propagating Delete Events When the Database Physically Deletes Rows

When a database physically deletes rows, a simple polling job like:

~~~sql
SELECT * FROM orders WHERE updated_at > :last_seen;
~~~

cannot detect vanished rows. Once deleted, the row no longer appears in query results.

There are two common ways to preserve deletion information.

### CDC Reading the Change Log

CDC reads the database transaction log. A DELETE operation can be emitted as an event containing the primary key and change metadata.

The consumer receives the delete event and writes a tombstone to Elasticsearch.

Check your connector configuration:

- Are delete events emitted?
- Is the primary key preserved in the payload?
- Which revision or source position can be used for comparison?
- Is the before image enabled if older data is needed?
- Are Kafka tombstones dropped by the connector or an SMT?
- Is log retention long enough for consumers to recover?

Some connectors emit a Kafka tombstone record with a null value after a delete event to support log compaction. This Kafka tombstone has different semantics from an application tombstone in Elasticsearch. It signals to the broker that a key was deleted during log compaction; consumers still need to process the delete event and record a deletion/version marker in the search index.

### Transactional Outbox

The application can write an event to an outbox in the same transaction as the delete operation.

General flow:

~~~text
BEGIN TRANSACTION
    |
    +-- Increment entity revision
    |
    +-- Write ORDER_DELETED to outbox
    |
    +-- Delete business row
    |
COMMIT
    |
    v
Outbox relay reads event
    |
    v
Message broker
    |
    v
Elasticsearch consumer
~~~

Illustrative SQL example:

~~~sql
BEGIN;

UPDATE orders
SET revision = revision + 1
WHERE id = :order_id
RETURNING revision;

-- The application captures the returned revision to write the outbox row.
INSERT INTO outbox_events (
    event_id,
    aggregate_id,
    aggregate_revision,
    event_type,
    created_at
)
VALUES (
    :event_id,
    :order_id,
    :new_revision,
    'ORDER_DELETED',
    CURRENT_TIMESTAMP
);

DELETE FROM orders
WHERE id = :order_id;

COMMIT;
~~~

The statements above illustrate the steps inside a transaction; capturing the revision from the UPDATE result must be implemented via a CTE or syntax supported by your specific database.

The crucial point is that the delete event and row deletion commit together. If the transaction rolls back, both roll back. If it commits, the relay can still emit the event after the application or broker recovers.

Never emit a message after deleting from the database via an independent call without an outbox or CDC. If the application dies between commit and publish, deletion information can be lost.

## 8. Approach 1: Hard Delete in Elasticsearch

The simplest approach is receiving a delete event and calling the Delete API:

~~~http
DELETE /orders/_doc/order-42
~~~

If source revision control is needed:

~~~http
DELETE /orders/_doc/order-42?version=18&version_type=external
~~~

`version_type=external` requires the submitted version to be higher than the stored version. If the document is at revision 17, delete revision 18 succeeds. If the document was already updated to revision 19, delete revision 18 is rejected as stale.

### Limitations of Hard Deletes

After deletion, Elasticsearch only retains the version of the deleted document for the duration controlled by `index.gc_deletes`. The current default is 60 seconds.

For example:

1. Document has external version 17.
2. Delete event revision 18 arrives and deletes the document.
3. While the internal tombstone is kept, an upsert at revision 17 is rejected.
4. Once delete metadata is garbage collected, an upsert at revision 17 may no longer find a version marker to compare against.
5. Since the ID no longer exists, the stale index operation can recreate the document.

Therefore, `index.gc_deletes` is not a long-term anti-resurrection mechanism for CDC. Increasing this value extends protection slightly, but does not solve replays after hours, days, or backup restores.

Hard deletes fit when event sources and consumers have strict replay bounds, or when the system maintains another durable version/tombstone store checked prior to writes.

## 9. Approach 2: Keeping Application Tombstones in the Same Index

A common pattern is replacing the business document with a tombstone document under the same `_id`.

Suppose an active document is:

~~~json
{
  "id": "order-42",
  "customerId": "customer-7",
  "status": "PAID",
  "sourceRevision": 17,
  "deleted": false
}
~~~

Upon receiving delete event revision 18, the consumer indexes a new document:

~~~json
{
  "id": "order-42",
  "sourceRevision": 18,
  "deleted": true,
  "deletedAt": "2026-11-13T10:15:30Z",
  "lastEventId": "evt-9f8a"
}
~~~

The tombstone replaces the old payload and preserves version 18. The consumer can use external versioning to reject any event with a lower revision.

Advantages:

- Tombstones persist as regular documents.
- Delete revisions survive past `index.gc_deletes` expiration.
- No need to query a separate tombstone store before every upsert.
- A valid recreation with a higher revision can overwrite the tombstone.
- Old business payloads are stripped from `_source` when the tombstone is indexed.

This is usually an easy-to-reason-about design for read models needing protection against out-of-order events.

### Mapping for Documents with Tombstones

Example mapping:

~~~http
PUT /orders-v1
{
  "mappings": {
    "properties": {
      "id": {
        "type": "keyword"
      },
      "customerId": {
        "type": "keyword"
      },
      "status": {
        "type": "keyword"
      },
      "sourceRevision": {
        "type": "long"
      },
      "deleted": {
        "type": "boolean"
      },
      "deletedAt": {
        "type": "date"
      },
      "lastEventId": {
        "type": "keyword"
      }
    }
  }
}
~~~

Active documents should have `deleted: false`. Tombstones have `deleted: true`.

You can create an alias that reads only active documents:

~~~http
POST /_aliases
{
  "actions": [
    {
      "add": {
        "index": "orders-v1",
        "alias": "orders-active",
        "filter": {
          "bool": {
            "must_not": [
              {
                "term": {
                  "deleted": true
                }
              }
            ]
          }
        }
      }
    }
  ]
}
~~~

The application searches via the alias:

~~~http
GET /orders-active/_search
{
  "query": {
    "term": {
      "customerId": "customer-7"
    }
  }
}
~~~

The alias filter excludes tombstones from search results. Tombstones stay in the index to preserve revisions.

If legacy data contains documents without the `deleted` field, `must_not deleted=true` still allows those documents to appear. When standardizing, you can backfill `deleted=false` during migration.

## 10. External Versioning Prevents Old Events from Overwriting Tombstones

External versioning lets the application pass source-managed versions. Elasticsearch accepts the operation only if the submitted version is strictly greater than the current version.

Suppose a document currently has revision 17:

~~~http
PUT /orders-v1/_doc/order-42?version=17&version_type=external
{
  "id": "order-42",
  "customerId": "customer-7",
  "status": "PAID",
  "sourceRevision": 17,
  "deleted": false
}
~~~

Delete event revision 18 is represented as a tombstone document:

~~~http
PUT /orders-v1/_doc/order-42?version=18&version_type=external
{
  "id": "order-42",
  "sourceRevision": 18,
  "deleted": true,
  "deletedAt": "2026-11-13T10:15:30Z",
  "lastEventId": "evt-9f8a"
}
~~~

An older revision 17 event arrives afterward:

~~~http
PUT /orders-v1/_doc/order-42?version=17&version_type=external
{
  "id": "order-42",
  "customerId": "customer-7",
  "status": "PAID",
  "sourceRevision": 17,
  "deleted": false
}
~~~

Elasticsearch returns a version conflict because 17 is not greater than 18. The tombstone keeps the latest state.

If a valid order recreation occurs with revision 19, that operation is accepted:

~~~http
PUT /orders-v1/_doc/order-42?version=19&version_type=external
{
  "id": "order-42",
  "customerId": "customer-7",
  "status": "NEW",
  "sourceRevision": 19,
  "deleted": false
}
~~~

The essential property is that revisions must be assigned by the source and increase across both deletes and recreations.

### `EXTERNAL` vs. `EXTERNAL_GTE`

| Version type | Acceptance condition |
|---|---|
| `internal` | Elasticsearch manages versions internally |
| `external` | Submitted version must be strictly greater than stored version |
| `external_gte` | Submitted version can be equal to or greater than stored version |

For replayable event streams, `external` is usually safer because an event with a duplicate revision cannot overwrite a different payload sharing that revision.

`external_gte` can be useful in certain specialized idempotent designs, but if two different payloads share a revision, the later payload can overwrite the earlier one. Elasticsearch documentation warns that misusing `external_gte` can cause data loss.

Never use timestamps or randomly generated values as external versions. You need a meaningful, stable ordering from the source.

## 11. Spring Data Elasticsearch and Version Metadata

Spring Data Elasticsearch supports versioning via `@Version` and `@Document.versionType`.

Entity example:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.elasticsearch.annotations.Document;

@Document(
    indexName = "orders",
    versionType = Document.VersionType.EXTERNAL
)
public class OrderDocument {

    @Id
    private String id;

    @Version
    private Long version;

    private String status;

    // Getters and setters
}
~~~

`@Version` marks the property used as the document's version metadata. Spring Data uses the version to guard concurrent writes. When versions mismatch, the operation can fail with an optimistic locking exception.

`@Document.versionType` configures how Elasticsearch manages versions. Spring Data Elasticsearch 6.1.2 defaults to `EXTERNAL`; supported values include `INTERNAL`, `EXTERNAL`, and `EXTERNAL_GTE`.

Distinguish version metadata from the business field `sourceRevision`:

- `@Version` is Elasticsearch's version metadata managed by Spring Data.
- `sourceRevision` is the revision assigned by the database or event source.
- When using external versioning for CDC, the actual index request must receive `sourceRevision` as the version metadata.
- Do not assume simply adding a `sourceRevision` property to an entity causes Elasticsearch to use it as the version.

If the application uses repository `save()` for standard entities, use `@Version` to protect read-modify-write cycles per the Spring Data model. For CDC consumers needing exact source revisions applied, verify the version sent in the Elasticsearch request and test out-of-order event handling.

### `SeqNoPrimaryTerm` in Spring Data

Spring Data Elasticsearch also provides `SeqNoPrimaryTerm` to support optimistic concurrency control via `_seq_no` and `_primary_term`.

Example:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.core.query.SeqNoPrimaryTerm;

@Document(indexName = "orders")
public class OrderDocument {

    @Id
    private String id;

    private String status;

    private SeqNoPrimaryTerm seqNoPrimaryTerm;

    // Getters and setters
}
~~~

When an entity is read from Elasticsearch, Spring Data automatically populates the sequence number and primary term pair if this property exists. When the entity is re-indexed with a valid metadata pair, Spring Data sends the corresponding condition so Elasticsearch rejects the update if the document changed after the read.

This mechanism suits the flow:

1. Read document.
2. Modify entity in application.
3. Write entity back.
4. Detect if another writer updated the document in the meantime.

`SeqNoPrimaryTerm` is neither a database source revision nor a tombstone. It protects an operation based on previously read Elasticsearch state.

## 12. Spring Data Java API Client for Events with Source Revisions

With Spring Data Elasticsearch 5+ using the Elasticsearch Java API Client, applications can inject the configured client and send external versions directly.

Document index example:

~~~java
import co.elastic.clients.elasticsearch._types.VersionType;
import co.elastic.clients.elasticsearch.core.IndexResponse;

OrderIndexDocument document = new OrderIndexDocument(
    event.orderId(),
    event.revision(),
    false,
    null,
    event.eventId()
);

IndexResponse response = elasticsearchClient.index(i -> i
    .index("orders-v1")
    .id(event.orderId())
    .version(event.revision())
    .versionType(VersionType.External)
    .document(document)
);
~~~

Tombstone example:

~~~java
OrderIndexDocument tombstone = new OrderIndexDocument(
    event.orderId(),
    event.revision(),
    true,
    event.occurredAt(),
    event.eventId()
);

IndexResponse response = elasticsearchClient.index(i -> i
    .index("orders-v1")
    .id(event.orderId())
    .version(event.revision())
    .versionType(VersionType.External)
    .document(tombstone)
);
~~~

This indexes a tombstone document with the same ID. It stores the version in Elasticsearch metadata and records `sourceRevision` in `_source` so the application can observe, debug, and reconcile.

Document record example:

~~~java
import java.time.Instant;

public record OrderIndexDocument(
    String id,
    long sourceRevision,
    boolean deleted,
    Instant deletedAt,
    String lastEventId
) {
}
~~~

In real applications, active documents can include additional search fields such as customer, status, and order items. Tombstones only need the minimal required fields.

### Calling via `ElasticsearchOperations`

If the application uses the template, you can use `ElasticsearchOperations.execute(...)` to access the low-level client:

~~~java
IndexResponse response = operations.execute(client ->
    client.index(i -> i
        .index("orders-v1")
        .id(event.orderId())
        .version(event.revision())
        .versionType(VersionType.External)
        .document(tombstone)
    )
);
~~~

This path calls the Elasticsearch Java API Client directly. It provides explicit control over version type and source revision. Spring Data entity callbacks do not automatically run just because a request executes inside `operations.execute`; the application must prepare the payload itself.

## 13. Handling Version Conflicts Properly

When using external versioning, duplicate or older events can return an HTTP 409 version conflict.

Never treat every HTTP 409 as a success. There can be other conflict types or errors that require handling.

A sound workflow:

1. Receive event with ID and revision.
2. Send index or tombstone using external version.
3. On success, record event as applied.
4. On version conflict, read the current document by ID.
5. Compare current `sourceRevision` against the event's revision.
6. If current revision is higher, the event arrived late and can be skipped.
7. If revisions are equal and `eventId`/state match, this is likely a replay of the same event.
8. If revisions match yet payload or event type differs, treat it as a version contract violation and route to investigation.

Pseudocode:

~~~java
try {
    applyWithExternalVersion(event);
    acknowledge(event);
} catch (VersionConflictException conflict) {

    OrderIndexDocument current = loadCurrentDocument(event.orderId());

    if (current.sourceRevision() > event.revision()) {
        // Event is older than already applied state.
        acknowledgeAsStale(event);
        return;
    }

    if (current.sourceRevision() == event.revision()
            && current.lastEventId().equals(event.eventId())) {
        // The exact same event was already applied.
        acknowledgeAsDuplicate(event);
        return;
    }

    // Same revision but different event or state.
    sendToDeadLetterQueue(event, conflict);
}
~~~

This pseudocode illustrates the handling rules; exact exception names depend on how the client or Spring Data wraps Elasticsearch errors.

When reading the current document, handle missing documents and network errors. Never turn a read failure into a conclusion that the event was already applied.

### Why Not Use `external_gte` to Avoid 409s?

With `external_gte`, an event with the same revision could be accepted and overwrite a tombstone with an older payload if the producer emitted two different payloads under the same version.

Using strict `external` and handling duplicates in the consumer generally detects version violations more clearly.

## 14. Hard Deletes Can Use Versioning and `seq_no`/`primary_term`

If business rules require physical deletion from Elasticsearch, the Delete API supports two control modes.

### External Versioning

~~~http
DELETE /orders/_doc/order-42?version=18&version_type=external
~~~

The source version is compared against the document version. This is useful when source revision serves as the document's version.

However, the delete tombstone version of a hard delete is retained only per `index.gc_deletes`. It does not replace a durable application tombstone.

### Optimistic Concurrency via `seq_no` and `primary_term`

When an application reads a document, Elasticsearch returns `_seq_no` and `_primary_term`. These can ensure deletion happens only if the document has not changed since the read:

~~~http
DELETE /orders/_doc/order-42?if_seq_no=362&if_primary_term=2
~~~

If the document changed, Elasticsearch returns a version conflict and does not delete the newer document.

This mechanism suits user read-then-delete flows based on a snapshot. It does not replace `sourceRevision` in an event stream: database revisions and Elasticsearch sequence numbers belong to two distinct domains.

## 15. Routing Must Stay Consistent When Deleting and Writing Tombstones

If a document is indexed using custom routing, Delete API calls must supply the matching routing to reach the same shard.

Index example:

~~~http
PUT /orders/_doc/order-42?routing=customer-7
{
  "customerId": "customer-7",
  "status": "PAID"
}
~~~

Delete must also use routing:

~~~http
DELETE /orders/_doc/order-42?routing=customer-7
~~~

If the mapping requires routing and the request omits it, Elasticsearch rejects the operation. If the request supplies the wrong routing, it may check a different shard and fail to delete the target document.

For application tombstones, use the exact same ID and routing used when indexing the active document. If the routing key can change over time, you need the old routing to delete or replace the old document on the correct shard.

Routing should be part of the event contract or deterministically derived from the ID.

## 16. Delete by Query Does Not Replace Per-Entity Delete Events

Elasticsearch provides the Delete by Query API:

~~~http
POST /orders/_delete_by_query
{
  "query": {
    "term": {
      "status": "CANCELLED"
    }
  }
}
~~~

This API suits maintenance tasks or deleting a set of documents matching criteria.

However, it is not the default choice for propagating individual delete events from a database:

- Elasticsearch takes a data snapshot when the request starts.
- Matching documents are deleted using internal versioning.
- If a document changes after the snapshot is taken and before deletion runs, a version conflict can occur.
- Large tasks can run long or asynchronously.
- The request does not carry per-entity source revisions.

For CDC synchronization, consumers should process events by ID and source revision. Delete by query should be reserved for well-scoped administrative tasks.

## 17. Recreating an Entity After Deletion

There are two different requirement types:

1. Entities are permanently deleted and never allowed to reappear.
2. Entities can be recreated under business rules.

If an entity is recreated, the new revision must exceed the tombstone revision.

Example:

| Revision | Operation | Result |
|---:|---|---|
| 20 | UPSERT | Active document |
| 21 | DELETE | Tombstone |
| 22 | UPSERT | Document active again |
| 20 | Late UPSERT | Rejected |
| 21 | Duplicate DELETE | Recognized as duplicate/stale |

If business rules forbid recreation after deletion, the consumer needs a status or registry indicating that the ID is retired. Even an upsert event with a higher revision should not automatically reactivate the entity if source policy forbids it.

Tombstones only solve ordering and versioning. Whether an entity can be recreated remains a business rule of the data source.

## 18. When Can Tombstones Be Garbage Collected?

Keeping tombstones forever can gradually bloat the index. However, deleting tombstones too early reopens the door to resurrection.

Only purge tombstones when the system can prove no stale events can still arrive.

Factors to consider:

- Event retention in the broker.
- Maximum duration consumers can stay offline.
- Retry and dead-letter replay windows.
- Restore windows from older backups or snapshots.
- Read model reindex/rebuild procedures.
- CDC log retention at the database.
- Other writers capable of re-emitting old data.

Without a reliable replay bound, keep the tombstone or maintain a durable high-watermark version for that ID.

A possible strategy:

1. Keep tombstones in the index for a defined period.
2. Once all consumers have passed the relevant checkpoint, move the ID and revision to a smaller registry.
3. Upon receiving an upsert, check the high-watermark before writing.
4. Remove from the registry only once the source and all replay paths guarantee older revisions cannot be re-emitted.

If the registry resides in another index, handle races between checking the registry and writing the document. Two operations across two indexes lack an atomic transaction. Use a single writer service, partition by entity, or co-locate the tombstone with the document to avoid this race window.

## 19. Building a Transactional Outbox for Deletes

Example service deleting an order in the database:

~~~java
@Transactional
public void deleteOrder(String orderId) {

    Order order = orderRepository.findById(orderId)
        .orElseThrow();

    long nextRevision = order.getRevision() + 1;

    outboxRepository.save(
        new OutboxEvent(
            UUID.randomUUID().toString(),
            orderId,
            nextRevision,
            "ORDER_DELETED",
            Instant.now()
        )
    );

    orderRepository.delete(order);
}
~~~

This example illustrates the concept; updating the revision and deleting the row must ensure the final revision is stored in the outbox within the same transaction.

The relay reads the outbox and publishes the event. The consumer applies the tombstone in Elasticsearch.

The outbox needs:

- Unique `event_id`.
- `aggregate_id`.
- `aggregate_revision`.
- `event_type`.
- Required payload or metadata.
- Publish/checkpoint status.
- Creation timestamp.

Never delete outbox events immediately upon sending if the relay requires retries or auditing. Cleanup policies must respect broker checkpoints and retention.

With CDC, a separate relay may be unnecessary, though you still must ensure log retention and complete delete event emission.

## 20. Bulk Synchronization and Delete Tombstones

When many events arrive, operations can be batched using the Bulk API. Each action must carry that entity's own version.

Example bulk indexing two tombstones:

~~~http
POST /orders-v1/_bulk
{"index":{"_id":"order-42","version":18,"version_type":"external"}}
{"id":"order-42","sourceRevision":18,"deleted":true,"deletedAt":"2026-11-13T10:15:30Z","lastEventId":"evt-9f8a"}
{"index":{"_id":"order-43","version":31,"version_type":"external"}}
{"id":"order-43","sourceRevision":31,"deleted":true,"deletedAt":"2026-11-13T10:16:00Z","lastEventId":"evt-9f8b"}
~~~

The Bulk API returns results per item. A single request can have some items succeed and others fail.

Consumers must:

- Read each item's status.
- Retry transient errors such as timeouts or unavailable responses.
- Recognize version conflicts caused by stale events.
- Route mapping errors or invalid data to a dead-letter queue.
- Commit/ack checkpoints appropriately only after handling each item.
- Never treat the whole bulk request as successful solely because the HTTP response returned 200.

With partitioned message brokers, ensure checkpoints do not skip past an event that has not been successfully handled if the consumer requires per-partition ordering.

## 21. Aliases and Rollover When Syncing Deletes

If an application writes through an alias pointing to multiple indexes or uses rollover, determine which indexes may hold the document.

For example:

- `orders-000001` holds documents before rollover.
- Alias `orders-write` switches to `orders-000002`.
- A delete event arrives after rollover.

If the consumer writes the tombstone only to the new write index, the old document in `orders-000001` may still appear when querying via a read alias covering both indexes.

Principles:

- Use a stable index strategy per entity if updates/deletes by ID are needed.
- If rollover allows the same ID to appear in multiple backing indexes, deletes must identify which indexes may hold the document.
- With data streams, you cannot send deletes directly to the data stream name; you must target the specific backing index.
- Use the same routing key for upserts and deletes.
- Ensure read aliases do not return stale documents from prior indexes.

When entities are mutable by ID, a regular index or write alias with clear routing rules is usually easier to manage than an append-only data stream.

## 22. Rebuilding Indexes Without Resurrecting Deleted Documents

A reindex or read model rebuild may read an older snapshot while CDC continues emitting new events.

Example:

1. Start database snapshot at checkpoint C100.
2. While the snapshot runs, an order is deleted at checkpoint C120.
3. The snapshot still contains the order because it was captured before the deletion.
4. Consumer loads the snapshot into the new index.
5. CDC event DELETE C120 is replayed.

If delete events are dropped or the checkpoint is wrong, documents from the snapshot can persist in the new index despite being deleted at the source.

A safe rebuild workflow:

1. Choose source checkpoint C100.
2. Create the new target index.
3. Load a consistent snapshot as of C100.
4. Capture all changes after C100, including delete events.
5. Apply changes according to source revision or change position.
6. Wait until the consumer reaches the target checkpoint.
7. Reconcile state against the source.
8. Switch the read alias to the new index.
9. Retain the old index long enough for rollback per procedure.

If snapshot and CDC lack a consistent boundary, updates or deletes between the two steps can be missed. Tombstones cannot fix a broken checkpoint or a lost delete event.

## 23. Distinguishing Source Revision, Elasticsearch Version, and Sequence Number

Three numbers are frequently conflated:

| Value | Who creates it? | What is it used for? |
|---|---|---|
| Source revision | Database or event source | Ordering business changes of an entity |
| Elasticsearch `_version` | Elasticsearch or external version sent by request | Document version control in the index |
| `_seq_no` + `_primary_term` | Elasticsearch primary shard | Optimistic concurrency for operations based on read state |

Example:

- Database order revision 18 is deleted.
- Elasticsearch document currently has `_version` 17.
- Tombstone operation sends external version 18.
- Elasticsearch accepts the tombstone and stores version 18.
- `_seq_no` might be 900 and `_primary_term` 3.

These numbers do not have to match. Source revision 18 is not `_seq_no` 18.

If an application takes `_seq_no` from a `SearchHit` and uses it as a source revision in a message broker, the system mixes two version domains and easily breaks during index rebuilds or migrations.

## 24. Reconciling and Observing the Delete Pipeline

Do not merely check that consumers report no errors. A sync system needs metrics that reveal lost delete events or accepted stale events.

Metrics to monitor:

- Delete events received.
- Tombstones written successfully.
- External version conflicts.
- Stale events ignored.
- Duplicate events.
- Mapping or serialization errors.
- Age of the oldest unprocessed event.
- Consumer lag and checkpoints.
- Tombstone count by index and over time.
- Active document count in Elasticsearch compared to the source.
- IDs still present in Elasticsearch that have been deleted in the database.

When discrepancies are detected, follow a reconciliation workflow:

1. Determine the ID and latest source revision.
2. Read document or tombstone state in Elasticsearch.
3. Compare source revisions.
4. If Elasticsearch is behind, replay the latest event or write source state using external versioning.
5. If Elasticsearch is ahead, investigate out-of-order events or source revision resets.
6. Record reconciliation outcomes to avoid infinite loops.

Reconciliation should run periodically and can be scoped by partition or ID range to control load.

## 25. Common Pitfalls

**Calling the Delete API and assuming resurrection is prevented.** Delete metadata is retained only per `index.gc_deletes`, defaulting to 60 seconds. It is not a durable application tombstone.

**Emitting delete events after database deletion without an outbox or CDC.** If the process dies after commit and before publishing, events can be lost.

**Omitting revisions from delete events.** Consumers cannot tell whether a delete arrived before or after another update for the same entity.

**Using timestamps as versions.** Timestamps can collide or suffer clock skew. Use revisions with source-guaranteed ordering.

**Using external versioning but forgetting tombstone versions.** If a tombstone is indexed without a source version, an older upsert can still overwrite it under active versioning rules.

**Using `external_gte` indiscriminately.** Different payloads sharing the same revision can overwrite each other. Use strict `external` and handle duplicates explicitly.

**Treating every 409 as a valid duplicate.** Determine whether it is a stale-event version conflict or another error. Same revision with different event content warrants investigation.

**Deleting tombstones immediately after broker ack.** Broker ack does not prove every consumer, backup, replay, or rebuild has moved past that event.

**Using a separate tombstone store without controlling races.** Checking a tombstone store and indexing in another index leaves a window where delete and upsert run concurrently.

**Omitting routing on deletes.** Deletes or tombstones can land on a different shard from the old document.

**Using `delete_by_query` for per-entity CDC.** This API uses snapshots and internal versioning rather than carrying per-entity source revisions.

**Using `@Version` alone and assuming tombstones exist.** `@Version` guards document versions on writes. It does not retain a deleted document after the Delete API completes.

**Confusing `SeqNoPrimaryTerm` with source revisions.** This is Elasticsearch optimistic concurrency metadata, not a database sequence.

**Letting snapshot rebuilds run after CDC without a shared checkpoint.** Stale snapshots can reload deleted data if delete events are skipped.

**Allowing a multi-index read alias to retain old versions.** A tombstone in the new write index does not automatically delete a duplicate-ID document in an older backing index.

**Keeping full sensitive payloads in tombstones.** Tombstones should be minimal and comply with business data deletion requirements.

## 26. Workflow for Safe Delete Propagation Design

You can implement this in steps:

1. Determine whether the data source can emit delete events via CDC or transactional outbox.
2. Design an event contract with ID, operation, source revision, event ID, and routing.
3. Ensure revisions increase monotonically across all changes, including deletes and recreations.
4. Choose hard deletes or application tombstones based on replay and retention needs.
5. If long-term anti-resurrection protection is needed, keep tombstone documents or a durable high-watermark.
6. Use external versioning to reject stale events.
7. Use strict `external` to catch duplicate-revision conflicts; use `external_gte` only when semantics are explicitly designed.
8. With Spring Data, distinguish `@Version`, `@Document.versionType`, and `SeqNoPrimaryTerm`.
9. For CDC events, pass the exact source revision in the request's version metadata.
10. Handle 409 responses against current state rather than ignoring all conflicts.
11. Keep routing and target indexes consistent.
12. Handle Bulk API responses per item and manage checkpoints.
13. Design tombstone retention around replay, backup, and rebuild horizons.
14. Build a snapshot + CDC catch-up workflow for index rebuilds.
15. Monitor stale events, duplicates, consumer lag, and reconciliation.
16. Test stale updates arriving after deletes, deletes arriving after newer updates, duplicate deletes, recreations, and replays after many days.

## 27. Essential Test Scenarios

A delete-sync test suite should cover these scenarios:

| Scenario | Event arriving at Elasticsearch | Expected outcome |
|---|---|---|
| Creation | UPSERT revision 1 | Active document |
| Update | UPSERT revision 2 | Document updated |
| Delete | DELETE revision 3 | Tombstone revision 3 |
| Late stale update | UPSERT revision 2 | Rejected |
| Duplicate delete | DELETE revision 3 | Identified as duplicate |
| Valid newer update | UPSERT revision 4 | Applied only if business rules allow recreation |
| Same revision, different payload | UPSERT revision 3 different event | Flagged as version contract error |
| Long-delayed replay | UPSERT revision 2 days later | Still rejected by tombstone revision 3 |
| Wrong routing | DELETE with different routing | Test must catch that the old document persists |
| Rebuild from old snapshot | Snapshot has revision 2, then replay DELETE revision 3 | New index retains tombstone revision 3 |

In particular, run stale upsert replay tests after `index.gc_deletes` has expired. If tests run within a few seconds only, they can miss the hard-delete vulnerability.

## Conclusion

Propagating delete changes in synchronization systems requires retaining traces of delete operations and entity revisions. Elasticsearch's Delete API preserves deleted document versions only for the window governed by `index.gc_deletes`, defaulting to 60 seconds. That interval helps short-term concurrency control, but is insufficient to guard against replays or late events arriving hours or days later.

Application tombstones solve this by maintaining a minimal document with the same ID, source revision, and deleted state. Combined with external versioning, Elasticsearch accepts only changes with newer revisions. A stale upsert cannot overwrite an existing tombstone; a valid recreation must carry a higher revision and be permitted by business rules.

In Spring Data Elasticsearch, `@Version` and `@Document.versionType` support version metadata for entity operations; `SeqNoPrimaryTerm` supports optimistic concurrency based on read Elasticsearch state. These mechanisms differ from source revisions and application tombstones. For CDC events carrying exact source revisions, ensure that version is sent in Elasticsearch requests, handle version conflicts with verification, and retain tombstones across all possible replay or rebuild horizons.

A reliable sync pipeline combines durable delete events from CDC or transactional outbox, monotonically increasing revisions, long-lived tombstones, idempotent consumers, consistent routing, and reconciliation processes. When these components are designed together, delete operations can propagate across asynchronous consumers without resurrecting stale data.

## References

- [Elasticsearch — Delete a document](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-delete)
- [Elasticsearch — Optimistic concurrency control](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/optimistic-concurrency-control)
- [Elasticsearch — General index settings (index.gc_deletes)](https://www.elastic.co/docs/reference/elasticsearch/index-settings/index-modules)
- [Elasticsearch — Bulk API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-bulk)
- [Elasticsearch — Delete by query API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-delete-by-query)
- [Elasticsearch — Soft deletes and retention leases](https://www.elastic.co/docs/deploy-manage/tools/cross-cluster-replication)
- [Spring Data Elasticsearch — Core concepts and entity state detection](https://docs.spring.io/spring-data/elasticsearch/reference/repositories/core-concepts.html)
- [Spring Data Elasticsearch — @Document API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/annotations/Document.html)
- [Spring Data Elasticsearch — Document.VersionType API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/annotations/Document.VersionType.html)
- [Spring Data Elasticsearch — SeqNoPrimaryTerm API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/query/SeqNoPrimaryTerm.html)
- [Spring Data Elasticsearch — IndexQueryBuilder API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/query/IndexQueryBuilder.html)
