# Designing Change Messages and Stable Document IDs

When synchronizing data from a database or message broker to Elasticsearch, message and document ID design determines whether consumers can safely reprocess messages, recover from failures, and update the right documents. If every message creates a document with a random ID, a redelivered event can create duplicate records. If a stable ID is used but messages arrive out of order, an older event can still overwrite newer state.

A sound design clearly separates three identifiers: the event ID identifies a specific message; the aggregate ID identifies the source business entity; the Elasticsearch document ID identifies the target document. Messages should have a clear schema, source version, change type, and sufficient payload for consumers to apply. Consumers must handle at-least-once delivery, retries, replays, deletes, and schema evolution.

This lesson covers designing the event envelope, deriving deterministic document IDs from source keys, distinguishing snapshot events from delta events, using outbox/CDC, handling duplicate and out-of-order delivery, syncing deletes, tenant/routing concerns, bulk failures, schema evolution, and testing idempotency.

## 1. The Data Synchronization Problem

Suppose a retail system stores `Product` in a relational database and uses Elasticsearch as a read model for search. When a `Product` changes, a message is sent to a consumer to update the `products` index.

Simple flow:

~~~text
Source database
      |
      | Product changed
      v
Change event / Outbox / CDC
      |
      v
Message broker
      |
      v
Elasticsearch consumer
      |
      | index / update / delete
      v
Elasticsearch document
~~~

In distributed systems, messages can be redelivered due to consumer crashes, timeouts, broker redeliveries, or retries. Events can arrive duplicated, late, or out of order. If IDs and messages are poorly designed, these scenarios cause:

- One source entity creating multiple duplicate documents.
- Stale events overwriting newer data.
- A delete being undone when a stale event resurrects the document.
- A delta event being applied twice.
- Consumers unable to replay after a bug fix.
- Inability to trace which message produced the current state.

Elasticsearch typically serves as a projection/read model. The database or domain service is the source of truth; messages carry the information needed to rebuild the projection. The design must allow the projection to converge toward the source state.

## 2. Distinguishing Event ID, Aggregate ID, and Document ID

These three IDs serve different purposes:

| Identifier | Answers the question | Example |
|---|---|---|
| eventId | Which specific message is this? | evt-8d31... |
| aggregateId | Which business entity changed? | product-100 |
| Elasticsearch _id | Which target document represents this entity/projection? | tenant-7:product-100 |

One `Product` can emit many events:

~~~text
Product product-100
    |
    +-- ProductCreated       eventId = evt-001
    +-- ProductPriceChanged  eventId = evt-002
    +-- ProductRenamed       eventId = evt-003
    +-- ProductDeleted       eventId = evt-004
~~~

These events have different `eventId` values but the same `aggregateId`. If each event represents the latest state of the same Product document, they must update the same Elasticsearch `_id`.

Do not use `eventId` as the document ID for a one-document-per-product materialized view. Doing so creates a new document for every change instead of updating the existing projection.

Conversely, if the index is designed as an event history where each event is its own document, `eventId` can be an appropriate `_id`. Choose the ID based on the target data model, not the message name.

## 3. Designing the Event Envelope

An event should have a consistent envelope containing metadata independent of the business payload:

~~~json
{
  "eventId": "evt-01J8Z7K4Y3",
  "eventType": "ProductSnapshotUpdated",
  "schemaVersion": 2,
  "aggregateType": "Product",
  "aggregateId": "product-100",
  "aggregateVersion": 18,
  "tenantId": "tenant-7",
  "occurredAt": "2026-11-13T09:15:30Z",
  "producer": "catalog-service",
  "correlationId": "req-42",
  "payload": {
    "sku": "KB-100",
    "name": "Wireless Keyboard",
    "category": "accessories",
    "price": 1299000,
    "active": true
  }
}
~~~

Field meanings:

| Field | Purpose |
|---|---|
| eventId | Unique ID of this event emission; used for tracing or deduplication |
| eventType | Type of change so consumers can choose how to handle it |
| schemaVersion | Schema version of the payload |
| aggregateType | Type of the source entity |
| aggregateId | Stable key of the source entity |
| aggregateVersion | Monotonically increasing version of the aggregate at the source |
| tenantId | Tenant scope if data is multi-tenant |
| occurredAt | Time when the change occurred at the source |
| producer | Service emitting the event |
| correlationId | Links the event to a request/workflow |
| payload | Business data to synchronize |

Not every system needs every field. However, `eventId`, event type, aggregate identity, version, and schema version are usually very helpful for handling duplicates, ordering, and replays.

### 3.1. `occurredAt` Does Not Replace `aggregateVersion`

Timestamps are not a safe way to decide which event is newer:

- Clocks across services can skew.
- Two events can share the same timestamp.
- Timestamp precision may be lower than the rate of changes.
- An event can be published late even though it occurred earlier.

If the source maintains a monotonically increasing version or sequence per aggregate, use that value to compare order. `occurredAt` serves auditing and observability; `aggregateVersion` serves order control.

### 3.2. `eventId` Must Stay Stable Across Retries

When a publisher retries the same event, keep the same `eventId`. Do not generate a new UUID on each resend, because consumers will treat each retry as a different event.

If events are written to an outbox, generate `eventId` inside the source transaction and store it with the outbox record. The dispatcher can resend that record multiple times without changing its ID.

### 3.3. Message Key and `eventId` Are Not the Same

For brokers supporting partition keys such as Kafka:

- The message key is usually `aggregateId` so events for the same aggregate land in the same partition and stay ordered within that partition.
- `eventId` is the unique identifier of each individual message.

Example:

~~~text
Kafka key: product-100
eventId:   evt-001
eventType: ProductPriceChanged
~~~

Using `aggregateId` as the key helps preserve per-key ordering within a partition, yet consumers should still check `aggregateVersion`. Retries, multiple processing threads, or different producers can complicate business ordering.

## 4. Choosing Snapshot Events vs. Delta Events

Event payloads can describe the full state after a change (snapshot) or only the changed portion (delta).

### 4.1. Snapshot Event

A snapshot contains the entire state needed to build the document:

~~~json
{
  "eventType": "ProductSnapshotUpdated",
  "aggregateId": "product-100",
  "aggregateVersion": 18,
  "payload": {
    "sku": "KB-100",
    "name": "Wireless Keyboard",
    "price": 1299000,
    "active": true
  }
}
~~~

The consumer can index the entire payload into the document using a stable ID. If the same snapshot is reprocessed, the document ends up in the exact same state.

Snapshots are usually easier to make idempotent because the operation has "set the document to this state" semantics.

### 4.2. Delta Event

A delta contains only the change:

~~~json
{
  "eventType": "ProductPriceIncreased",
  "aggregateId": "product-100",
  "aggregateVersion": 18,
  "payload": {
    "priceDelta": 50000
  }
}
~~~

A consumer could add the delta to the current price. However, if the message is delivered twice, the addition can execute twice:

~~~text
Initial price:     1,000,000
Delta event:       +50,000
After first run:   1,050,000
After retry:       1,100,000  <- wrong
~~~

Delta events require durable deduplication, version checks, or a mechanism to apply each event effectively once in business terms. A stable document ID alone is not enough to prevent an addition from repeating.

### 4.3. Choosing Event Type Based on Projection Needs

| Scenario | Typically suitable design |
|---|---|
| Syncing a document representing current state | Snapshot |
| Event stream needing to record every business change | Delta/domain event |
| Consumers needing independent replay and index rebuilds | Snapshot or events carrying enough data to reconstruct |
| Only deltas exist, yet current projection is needed | Delta + version/deduplication and explicit fold rules |
| Large data, small events | Deltas save bandwidth but increase consumer complexity |

No single choice fits every system. When simple consumers and safe replays are the priority, snapshot events are usually easier to operate.

## 5. Designing Stable Elasticsearch Document IDs

For a document representing a source entity, its ID should be deterministically derived from the source key:

~~~text
Elasticsearch _id = source aggregate ID
~~~

Example for a Product with ID `product-100`:

~~~java
@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    private String sku;
    private String name;
    private Long price;
}
~~~

When mapping the event:

~~~java
ProductDocument document = new ProductDocument();
document.setId(event.aggregateId());
document.setSku(event.payload().sku());
document.setName(event.payload().name());
document.setPrice(event.payload().price());

operations.save(document);
~~~

On the first write, Elasticsearch creates the document with ID `product-100`. On subsequent writes with the same `aggregateId`, `save` re-indexes the same document rather than creating another one.

### 5.1. Why Not Use Random IDs?

Unsuitable example for a one-document-per-product projection:

~~~java
document.setId(UUID.randomUUID().toString());
operations.save(document);
~~~

If the broker redelivers the event, a new UUID creates a new document. After multiple retries, the index holds multiple copies of the same Product.

Random IDs are only appropriate when each write is genuinely an independent record, such as an event history or audit log. For current-state projections, use deterministic source keys.

### 5.2. Using Repository `save`

Repositories also use the entity's ID:

~~~java
ProductDocument document = mapper.toDocument(event);
repository.save(document);
~~~

If the document's `@Id` is assigned the exact same value on every processing pass of the same aggregate, `save` indexes to the same `_id`.

Never leave the ID null when idempotent upsert is the goal. When ID is null, Elasticsearch can auto-generate an ID and every retry becomes a distinct document.

### 5.3. Using `IndexQuery` in Bulk Operations

With bulk indexing, set the ID explicitly for each operation:

~~~java
IndexQuery query = new IndexQueryBuilder()
        .withId(document.getId())
        .withObject(document)
        .build();

operations.bulkIndex(
        List.of(query),
        BulkOptions.defaultOptions(),
        IndexCoordinates.of("products"));
~~~

Application-assigned IDs ensure the same source entity always targets the same destination document. Inspect the bulk response item by item; do not assume the entire batch succeeded just because the HTTP request succeeded.

## 6. Generating IDs for Multi-Tenant Data

If two tenants can share a local key like `product-100`, an ID based solely on `productId` will cause cross-tenant collisions.

Use a composite identity:

~~~text
_id = tenantId + ":" + productId
~~~

Examples:

~~~text
tenant-7:product-100
tenant-9:product-100
~~~

The two documents have distinct IDs even though `productId` is identical across tenants.

### 6.1. Avoiding Ambiguous Composite Keys

Concatenating strings with a delimiter is only safe if components cannot contain the delimiter or if escaping rules are applied:

~~~text
tenant:a + ":" + product:b
tenant:a:product:b
~~~

Without encoding rules, two different component pairs can produce the same string. You can use length-prefixing, canonical JSON, or encode each component before joining.

Length-prefix example:

~~~text
7:tenant-7|11:product-100
~~~

In many systems, source UUIDs are already globally unique. In that case, you can use the UUID as the document ID and store `tenantId` as a field for filtering/authorization.

### 6.2. Hashing Composite Keys

If a composite key is long or contains data that should not appear in URLs/logs, you can hash a canonical key:

~~~java
String canonicalKey = tenantId + "\u0000" + productId;
String documentId = sha256Hex(canonicalKey);
~~~

Hashing produces a fixed-length, uniform ID that does not directly expose the raw components. However:

- The same canonical input must always produce the same hash.
- Canonicalization rules must remain stable.
- Choose a hash strong enough that collision probability is negligible.
- If you need to prevent guessing IDs from low-entropy inputs, plain hashes can be probed; consider keyed HMAC with key management.
- Never change the hash algorithm or HMAC secret without an ID migration plan.

If the source key is already an opaque UUID, hashing rarely adds meaningful value.

## 7. One Aggregate Can Produce Multiple Documents

One source entity can be projected into multiple document types:

- Product detail document.
- Product suggestion document.
- Product inventory projection.
- Product per-locale document.

Do not use the same `_id` if these projections live in the same index and must exist independently. Include the projection type or locale in the identity:

~~~text
tenant-7:product-100:detail
tenant-7:product-100:suggestion
tenant-7:product-100:inventory
tenant-7:product-100:locale-en
tenant-7:product-100:locale-vi
~~~

If each projection resides in its own index, the source ID can be reused within each index. Document identity is unique within an index/shard scope, not a global identifier across all projection types.

## 8. How Stable IDs Support Idempotency

An idempotent operation can be executed multiple times while leaving the final state identical to executing it once.

With snapshot events and stable IDs:

~~~text
Event evt-001:
  aggregateId = product-100
  payload = { name: "Keyboard", price: 1000 }

Attempt 1 -> index _id=product-100
Attempt 2 -> index _id=product-100
Attempt 3 -> index _id=product-100

Result: still one document product-100 with the same source state
~~~

The Index API with the same `_id` replaces the previous source document. This is the foundation of idempotent projections for snapshots.

### 8.1. Stable IDs Do Not Guarantee Every Update Is Idempotent

Assignment-style update:

~~~json
{
  "doc": {
    "price": 1299000
  }
}
~~~

Resending this usually preserves the same final value.

Increment-style update:

~~~json
{
  "script": {
    "source": "ctx._source.stock += params.delta",
    "params": {
      "delta": 2
    }
  }
}
~~~

Resending this increments the value again. A stable ID only ensures writes target the same document; it does not prevent repeated transformations.

For deltas, you need event deduplication, version guards, or conversion to a snapshot before writing.

## 9. Consumers Handling At-Least-Once Delivery

Many message brokers and consumer frameworks use at-least-once delivery semantics. That means a message can be redelivered if the consumer does not ack, the process dies, or the outcome is unconfirmed.

A typical scenario:

~~~text
1. Consumer receives event evt-001
2. Consumer indexes document successfully
3. Process crashes before acking the broker
4. Broker redelivers evt-001
5. Consumer reprocesses
~~~

If the consumer uses snapshots and stable `_id`s, indexing the same document a second time will not create duplicates. If the consumer uses random IDs or unguarded deltas, data can become corrupted.

### 9.1. Ack After Successful Writes

With a message broker, only ack/commit offsets after Elasticsearch confirms the corresponding operation succeeded per processing policy.

Never ack first and write to Elasticsearch afterward:

~~~text
ACK broker -> crash -> document not written -> lost projection update
~~~

With bulk operations, handle items individually. If some items succeed and others fail, do not blindly retry the entire batch if operations are not idempotent. Ack/commit and retries must respect broker, partition, and batch semantics.

### 9.2. Exactly-Once Does Not Appear Automatically When Using a Broker

End-to-end exactly-once across a database, broker, and Elasticsearch is a different problem. Broker transactions do not automatically create a distributed transaction with Elasticsearch.

Practical designs typically combine:

- At-least-once delivery.
- Stable document IDs.
- Snapshots or deltas with versioning/deduplication.
- Controlled retries.
- Outbox/CDC.
- Reconciliation and replay.

The goal is an effectively-once projection update in terms of final state, even though messages may be delivered multiple times.

## 10. Deduplication Using `eventId`

If you need to know whether an event has already been processed, `eventId` can serve as an idempotency key. Consumers must store a durable trace in an appropriate store:

~~~text
processed_event
----------------
event_id       primary key
processed_at
consumer_name
result
~~~

General workflow:

1. Receive event.
2. Check if `eventId` has already been processed.
3. If already present, skip side effects and acknowledge the event per retry semantics.
4. If not present, apply the projection.
5. Record `eventId` as processed.
6. Ack the message.

### 10.1. Beware of Dual Writes

If the deduplication ledger lives in a separate database and the document lives in Elasticsearch, the two operations are not in the same transaction:

~~~text
Write Elasticsearch succeeds
       |
       | process crashes
       v
Dedup ledger not written
       |
       v
Event redelivered and applied again
~~~

If you write the ledger first:

~~~text
Write dedup ledger succeeds
       |
       | process crashes
       v
Elasticsearch not updated
       |
       v
Redelivery is skipped incorrectly
~~~

Therefore, merely storing `eventId` in another database does not create exactly-once processing. With snapshot events and stable IDs, you can leverage the idempotency of index operations for simplicity. With delta events, design consistent version/dedup storage and recovery, or switch to snapshots.

### 10.2. Storing Event Markers Inside the Document?

You can store `lastAppliedEventId` or `lastAppliedVersion` inside the Elasticsearch document to guard processing. However, updating the marker and the data must happen in the same conditional update/script; making two separate requests still leaves a crash window.

For an aggregate, a monotonically increasing version is usually more useful than keeping only the last `eventId`, because versions also catch older events arriving out of order.

## 11. Handling Out-of-Order Events

Suppose a Product has increasing versions:

~~~text
Version 16: price = 1000
Version 17: price = 1200
Version 18: price = 1500
~~~

Due to retries or partitioning, the consumer receives them in order:

~~~text
18 -> 16 -> 17
~~~

If each event simply indexes by stable ID without checking versions, the final state can revert to `price = 1200` even though the source is at version 18.

Stable IDs prevent duplicate documents; they do not automatically stop stale events from overwriting newer data.

### 11.1. Using `aggregateVersion`

Each aggregate has a monotonically increasing version at the source:

~~~json
{
  "aggregateId": "product-100",
  "aggregateVersion": 18,
  "payload": {
    "price": 1500
  }
}
~~~

The consumer applies an event only if its version is newer than the stored version. If event version 16 arrives after document version 18, ignore the stale event.

### 11.2. External Versioning

For snapshot events, Elasticsearch supports external versioning on index operations. The application sends the version provided by the source:

~~~http
PUT products/_doc/product-100?version=18&version_type=external
{
  "id": "product-100",
  "sourceVersion": 18,
  "name": "Keyboard",
  "price": 1500
}
~~~

With `version_type=external`, Elasticsearch only accepts an incoming version strictly greater than the stored version. Older events are rejected with a version conflict.

If the versions are equal and you want to allow replaying the same version, Elasticsearch offers `version_type=external_gte`. Use this only when a given `aggregateVersion` always represents one exact state payload. If two different payloads share the same version, `external_gte` lets the later payload overwrite the earlier one.

### 11.3. Source Version Differs from Elasticsearch `_version`

Elasticsearch has its own internal `_version` and sequence numbers. They do not automatically synchronize with `aggregateVersion` in the database.

If using external versioning, the submitted version must come from an ordered source. Never substitute timestamps or Elasticsearch's previous `_version` for a business version without explicit rules.

### 11.4. Using Update Scripts to Compare `sourceVersion`

If partial updates are needed instead of indexing a full snapshot, you can store `sourceVersion` in the document and compare it inside an update script:

~~~json
{
  "script": {
    "source": "if (ctx._source.sourceVersion == null || params.version > ctx._source.sourceVersion) { ctx._source.price = params.price; ctx._source.sourceVersion = params.version; } else { ctx.op = 'noop'; }",
    "params": {
      "version": 18,
      "price": 1500
    }
  },
  "upsert": {
    "price": 1500,
    "sourceVersion": 18
  }
}
~~~

The script is an atomic operation on the document. Define behavior for equal versions, missing versions, and non-existent documents. For full snapshots, external versioning on the index action is usually simpler.

## 12. Designing Delete Events

Delete events must carry the same identity as the created document:

~~~json
{
  "eventId": "evt-099",
  "eventType": "ProductDeleted",
  "aggregateType": "Product",
  "aggregateId": "product-100",
  "aggregateVersion": 19,
  "tenantId": "tenant-7",
  "occurredAt": "2026-11-13T10:00:00Z"
}
~~~

The consumer computes the exact document ID and deletes it:

~~~java
operations.delete(
        event.aggregateId(),
        IndexCoordinates.of("products"));
~~~

If the document ID is derived from `tenantId` and `aggregateId`, deletes must use the exact same ID factory:

~~~java
String documentId = documentIdFactory.productId(
        event.tenantId(),
        event.aggregateId());

operations.delete(
        documentId,
        IndexCoordinates.of("products"));
~~~

Never construct delete IDs using a different rule from index IDs. A single-character mismatch leaves the old document behind.

### 12.1. Stale Events Can Resurrect Deleted Documents

A scenario:

1. Version 19 deletes the Product.
2. Consumer deletes the document in Elasticsearch.
3. Event version 18 is redelivered afterward.
4. Consumer indexes snapshot version 18 under the same `_id`.

The deleted document reappears. A stable ID does not prevent this resurrection.

### 12.2. Tombstones or Versioned Deletes

You can keep a tombstone document:

~~~json
{
  "_id": "tenant-7:product-100",
  "sourceVersion": 19,
  "deleted": true,
  "deletedAt": "2026-11-13T10:00:00Z"
}
~~~

Consumers modify the document only if an event has a newer version than the tombstone. Search queries filter `deleted = false`. A cleanup job can remove tombstones after a defined retention window, once the system guarantees old events can no longer be replayed.

Another option is using versioned/conditional deletes via the appropriate Elasticsearch mechanism. However, Elasticsearch's internal delete tombstones have finite retention; do not rely on them as a long-term business ledger for unbounded event replays.

### 12.3. Hard Delete or Soft Delete?

| Approach | Pros | Cons |
|---|---|---|
| Immediate hard delete | Index holds only active documents | Must guard against old events resurrecting documents |
| Soft delete/tombstone | Retains version to reject stale events and replays | Queries must filter `deleted`; requires cleanup |
| Versioned conditional delete | Blocks certain stale operations by concurrency token | Requires passing the right version and understanding retention semantics |

Choose based on maximum replay horizon, audit requirements, and how events are emitted. For sync pipelines with long-lived broker/outbox replays, tombstones or a durable version ledger are usually easier to control.

## 13. Transactional Outbox

A common issue is dual writing between a database and a broker:

~~~text
1. Update Product in database
2. Publish event to broker
~~~

If the database commit succeeds but publishing fails, Elasticsearch is never updated. If publishing succeeds but the database rolls back, consumers receive an event inconsistent with source state.

Transactional Outbox writes business changes and an outbox record within the same database transaction:

~~~text
Database transaction
   |
   +-- UPDATE product
   |
   +-- INSERT outbox_event
   |
   +-- COMMIT
          |
          v
Outbox relay / CDC
          |
          v
Message broker
          |
          v
Elasticsearch consumer
~~~

Example outbox table:

~~~sql
CREATE TABLE outbox_event (
    event_id VARCHAR(64) PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(200) NOT NULL,
    aggregate_version BIGINT NOT NULL,
    event_type VARCHAR(150) NOT NULL,
    schema_version INTEGER NOT NULL,
    payload JSON NOT NULL,
    occurred_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP NULL
);
~~~

Within the same transaction:

~~~sql
BEGIN;

UPDATE product
SET price = 1500,
    version = 18
WHERE id = 'product-100';

INSERT INTO outbox_event (
    event_id,
    aggregate_type,
    aggregate_id,
    aggregate_version,
    event_type,
    schema_version,
    payload,
    occurred_at
) VALUES (
    'evt-018',
    'Product',
    'product-100',
    18,
    'ProductSnapshotUpdated',
    2,
    '{"name":"Keyboard","price":1500}',
    CURRENT_TIMESTAMP
);

COMMIT;
~~~

A relay reads the outbox and publishes. If the relay crashes after publishing but before marking published, the event may be resent. Consumers still need idempotency and stable document IDs.

## 14. CDC and Message Normalization

Change Data Capture (CDC) reads database transaction logs or changes to emit events. A CDC record may contain:

- operation type (insert/update/delete).
- before and after images.
- source metadata such as database, table, log position.
- timestamp and transaction metadata.

Avoid coupling every Elasticsearch consumer directly to database-specific CDC structures whenever possible. Create an adapter step that transforms CDC records into stable domain/projection events:

~~~text
Database CDC format
       |
       v
CDC adapter
       |
       | normalize fields, IDs and versions
       v
ProductSnapshotUpdated v2
       |
       v
Elasticsearch projection consumer
~~~

This lets you change database connectors or CDC schemas without forcing all consumers to change simultaneously.

### 14.1. Deletes in CDC

Some CDC connectors emit a tombstone record after a delete, especially in log-compacted topics. Distinguish:

- Business delete events carrying an aggregate ID and version.
- Broker tombstone messages used to mark key removal during log compaction.
- CDC before/after images.

The adapter must translate these into a contract consumers understand. Do not assume every record with a null payload carries the same meaning across all connectors.

## 15. Message Schema Evolution

Messages outlive individual deployments. Producers and consumers can be upgraded at different times; older events may be replayed months later.

Include `schemaVersion` in the envelope:

~~~json
{
  "eventType": "ProductSnapshotUpdated",
  "schemaVersion": 2,
  "aggregateId": "product-100",
  "aggregateVersion": 18,
  "payload": {
    "name": "Keyboard",
    "price": 1500,
    "active": true
  }
}
~~~

When adding fields:

- Prefer additive changes.
- Older consumers should ignore unknown fields if the format allows.
- New fields can be optional or have safe defaults.
- Never change the meaning of an old field while keeping the old `schemaVersion`.

When changing data types or semantics:

- Increment `schemaVersion`.
- Write a mapper/upcaster from older versions.
- Test replaying old messages.
- Consider publishing a new event type or rebuilding the projection if conversion cannot be done on the consumer side.

### 15.1. Event Type and Schema Version Are Two Concepts

`eventType` describes business meaning, e.g., `ProductDeleted`. `schemaVersion` describes the payload structure of that event type. Do not use `schemaVersion` in place of `eventType` or vice versa.

### 15.2. Do Not Use Java Class Names as Contracts

Avoid sending Java package/class names as event types if producers and consumers need language independence or packages may be refactored. Use stable schema event names like `ProductSnapshotUpdated`.

### 15.3. Retain Enough Data for Replay

If an event contains only `productId` and the consumer has to call back to the source database for state, a replay may receive the current state rather than the state at the time of the event. That may be fine if the goal is an eventual latest-state projection, but unsuitable when reconstructing historical steps.

Choose payloads based on semantics:

- Snapshot events store state at that version.
- Reference events store only IDs and require controlled source reads.
- Delta events store changes with versions and application rules.

Do not let consumers accidentally mix the semantics of these three types.

## 16. Mapping Messages to Documents

Create a dedicated mapper to convert events into documents:

~~~java
public class ProductDocumentMapper {

    public ProductDocument toDocument(ProductSnapshotUpdated event) {
        ProductDocument document = new ProductDocument();
        document.setId(documentId(event.tenantId(), event.aggregateId()));
        document.setTenantId(event.tenantId());
        document.setSourceVersion(event.aggregateVersion());
        document.setSku(event.payload().sku());
        document.setName(event.payload().name());
        document.setPrice(event.payload().price());
        document.setActive(event.payload().active());
        document.setUpdatedAt(event.occurredAt());
        document.setDeleted(false);
        return document;
    }

    private String documentId(String tenantId, String aggregateId) {
        return tenantId + ":" + aggregateId;
    }
}
~~~

The mapper is responsible for:

- Constructing IDs according to one single rule.
- Mapping fields from the event schema to the Elasticsearch document.
- Storing `sourceVersion` for observability/reconciliation.
- Applying intentional defaults and normalization.
- Avoiding coupling to irrelevant transport metadata.

Do not scatter document ID generation across multiple consumers/services. Use a shared `DocumentIdFactory` or shared mapper so index, update, get, and delete stay consistent.

### 16.1. Storing Necessary Source Metadata

The document can store:

~~~json
{
  "tenantId": "tenant-7",
  "sourceId": "product-100",
  "sourceVersion": 18,
  "sourceUpdatedAt": "2026-11-13T09:15:30Z",
  "projectionVersion": 2,
  "name": "Wireless Keyboard",
  "price": 1299000
}
~~~

Metadata helps:

- Compare projections against the source.
- Detect stale documents.
- Locate mapping bugs or missed events.
- Rebuild indexes with versioning.
- Identify which mapper version produced the projection schema.

You do not need to expose all this metadata in user-facing APIs; it can remain in the document for operations.

## 17. Consumers Handling Snapshot Events

A simple consumer can do:

~~~java
public void onProductSnapshot(ProductSnapshotUpdated event) {
    ProductDocument document = mapper.toDocument(event);
    repository.save(document);
}
~~~

Because the ID is stable and the payload is a snapshot, reprocessing the same event writes to the same document. However, add version checks if events can arrive out of order.

When using external versioning, the consumer sends `aggregateVersion` on the index request. When a version conflict occurs due to a stale event, you can treat it as a rejected stale event after verifying the error type. Do not ignore all conflict errors identically; create conflicts, external version conflicts, and OCC conflicts have different semantics.

### 17.1. When a Consumer Receives the Same Version Twice

With strict external versioning, a second request with the same version is rejected because the version is not strictly greater than the stored version. The consumer can treat this as a duplicate/stale event after confirming the current document holds that matching version.

With `external_gte`, equal versions are accepted. Use it only when payloads for the same version are guaranteed identical; otherwise, a retry could overwrite with a different payload bearing the same version.

### 17.2. Do Not Overwrite `sourceVersion` with Unversioned Events

If an event lacks `aggregateVersion`, do not assign `0` or a timestamp to fake ordering. Define source semantics properly:

- Add versioning at the producer.
- Use well-defined log sequences/CDC positions.
- Serialize by aggregate key.
- Or accept eventual overwrites backed by appropriate reconciliation.

## 18. Consumers Handling Delta Events

With delta events, the consumer needs awareness of the current document to apply the change:

~~~java
public void onStockChanged(StockChanged event) {
    UpdateQuery update = UpdateQuery.builder(
                    documentIdFactory.productId(
                            event.tenantId(),
                            event.aggregateId()))
            .withScript("""
                ctx._source.stock = params.stock;
                ctx._source.sourceVersion = params.version;
                """)
            .withParams(Map.of(
                    "stock", event.payload().newStock(),
                    "version", event.aggregateVersion()))
            .build();

    operations.update(
            update,
            IndexCoordinates.of("products"));
}
~~~

This example assigns the new stock value (a field-level snapshot) rather than adding a delta. Setting absolute state is usually easier to retry than adding/subtracting.

If incrementing a delta is truly necessary, the script must check whether the event/version has already been applied and update the version in the same atomic operation. Define behavior when the document does not yet exist and when an event is skipped due to a stale version.

### 18.1. Partial Updates Can Lose Data If Events Are Incomplete

If a snapshot event carries only a few fields yet the consumer indexes a full document, other fields can be wiped from `_source`. If using partial updates, missing fields are preserved, which can leave the projection mixing fields from different versions.

Clarify whether an event is:

- Full snapshot: can replace the entire document.
- Partial patch: updates only present fields.
- Delta: applies a transformation.

Do not treat these three payload types as equivalent.

## 19. Bulk Processing and Partial Failures

Consumers can batch multiple events into a bulk request for higher throughput:

~~~java
List<IndexQuery> queries = events.stream()
        .map(event -> {
            ProductDocument document = mapper.toDocument(event);
            return new IndexQueryBuilder()
                    .withId(document.getId())
                    .withObject(document)
                    .build();
        })
        .toList();

operations.bulkIndex(
        queries,
        BulkOptions.defaultOptions(),
        IndexCoordinates.of("products"));
~~~

The Bulk API processes each item independently. Some items can succeed while others fail. Consumers must:

- Check individual items/failed documents.
- Retry transient errors like 429 or certain 5xx responses per policy.
- Handle version conflicts as stale/duplicate according to semantics.
- Send permanent mapping/schema errors to a DLQ.
- Never ack messages that have not been handled successfully per policy.
- Maintain correlation between bulk items and original events.

If retrying an entire batch, snapshot indexing with stable IDs is generally idempotent; delta events without deduplication can be applied repeatedly.

### 19.1. Bulk Is Not a Transaction

A bulk request does not roll back succeeded items when another item fails. Never mark an entire batch successful based solely on the HTTP response. Likewise, do not delete all succeeded documents to simulate a rollback.

### 19.2. A Batch May Contain Multiple Versions of the Same Aggregate

If a batch includes versions 17 and 18 for the same product:

- Preserve per-aggregate order if processing deltas.
- Or keep only the latest snapshot if semantics and audit rules allow.
- Use external versioning/version guards so older events do not overwrite newer ones.

Do not rely on array ordering inside a bulk request as an ordering guarantee across multiple requests or consumers.

## 20. Routing and Stable Document Identity

Elasticsearch supports custom routing to select shards. If a document is indexed with custom routing, get/update/delete/search operations by ID must supply the matching routing.

Example using `tenantId` as routing:

~~~text
_id     = tenant-7:product-100
routing = tenant-7
~~~

When indexing:

~~~http
PUT products/_doc/tenant-7:product-100?routing=tenant-7
{
  "tenantId": "tenant-7",
  "sourceId": "product-100",
  "name": "Keyboard"
}
~~~

Deletes must use the same routing:

~~~http
DELETE products/_doc/tenant-7:product-100?routing=tenant-7
~~~

If indexing uses routing while delete/get omits routing, operations may look at the wrong shard or fail to find the document.

### 20.1. `_id` Does Not Replace Routing

A stable ID identifies a document within a shard. Custom routing decides the target shard. With custom routing, the same `_id` with different routing can be routed to different shards; do not change routing arbitrarily between events.

### 20.2. Choosing a Routing Key

Routing by tenant co-locates tenant data on the same shard and makes tenant-filtered searches more efficient. However, very large tenants can create hot shards. Evaluate load distribution, tenant sizes, and query patterns before choosing custom routing.

If custom routing is unnecessary, letting Elasticsearch route by `_id` by default is simpler and avoids forgetting routing on updates/deletes.

## 21. Multi-Index, Aliases, and Projection Changes

Document IDs should stay stable per aggregate across updates to the same projection. When reindexing into a new index version, preserve the IDs:

~~~text
products-v1/_doc/tenant-7:product-100
products-v2/_doc/tenant-7:product-100
~~~

The `products` alias can switch from v1 to v2 after the new index is built and verified. If the ID algorithm changes between versions, plan the migration/rebuild carefully; otherwise, one aggregate may receive different IDs and create duplicate documents in the new index.

### 21.1. Projection Version Differs from `aggregateVersion`

- `aggregateVersion` indicates change ordering at the source.
- `projectionVersion` indicates the schema/mapping logic of the target document.

For example, mapper v2 adds `normalizedName`. The same `aggregateVersion` can be re-projected by a newer `projectionVersion` during an index rebuild. Never use `projectionVersion` instead of source version to skip stale events.

### 21.2. Rebuilding from the Source of Truth

An index can be rebuilt from a database snapshot or event history. Use the same document ID factory and mapper contract so rebuilt data shares the exact same identity as incremental sync data.

When rebuilding from a snapshot while new events continue arriving, implement a catch-up strategy:

1. Take a snapshot at a well-defined source position/version.
2. Rebuild the new index from the snapshot.
3. Replay events occurring after the snapshot position.
4. Check projection versions/lag.
5. Switch the alias once the new index has converged.

Never simply copy documents to a new index and switch the alias while unapplied events remain.

## 22. Handling Poison Events and Dead Letter Queues

A message may fail processing due to:

- Invalid payload schema.
- Missing `aggregateId` or `eventId`.
- Incompatible field mappings.
- Document ID factory failure.
- Insufficient Elasticsearch permissions.
- Missing index or alias.

Error classification:

| Error | Handling |
|---|---|
| Network timeout/429/temporary 5xx | Retry with backoff |
| Version conflict from stale event | Verify version and ignore |
| Mapping/parsing error | DLQ and fix schema/mapper |
| Missing required identity | DLQ or reject producer contract |
| Authentication/authorization | Stop/bounded retry and alert on configuration |
| Unknown index | Retry after verifying deployment order or send to DLQ |

The DLQ should retain the original event, `eventId`, `aggregateId`, version, error, attempt count, and last timestamp. Do not log unnecessary sensitive payloads.

When replaying from the DLQ, apply the same `eventId` and document ID rules. If an event has become stale compared to the current `sourceVersion`, the consumer should skip it via the version guard rather than regressing the projection.

## 23. Observability and Reconciliation

A data sync consumer should measure:

- Events received.
- Events succeeded, duplicated, and stale.
- Version conflicts.
- Bulk item failures by status/error type.
- Retry counts and DLQ counts.
- Consumer lag and event age.
- Gap between source version and document `sourceVersion`.
- Time from `occurredAt` until the projection is updated.

Logs can record metadata:

~~~text
eventId=evt-018
aggregateType=Product
aggregateId=product-100
aggregateVersion=18
documentId=tenant-7:product-100
result=INDEXED
~~~

Avoid logging full payloads if they contain sensitive data.

### 23.1. Reconciliation

Retries alone do not guarantee projections are always accurate. You may need a reconciliation job:

1. Read source IDs and source versions in batches.
2. Read corresponding document IDs/`sourceVersion` from Elasticsearch.
3. Detect missing, stale, or abnormally high-version documents.
4. Rebuild snapshots for drifted aggregates.
5. Record reconciliation metrics and outcomes.

Reconciliation detects and repairs long-term drift, especially useful after DLQ incidents or mapping bugs.

## 24. Testing Message and Document ID Design

Tests should prove the core invariants:

### 24.1. Same Aggregate Always Produces the Same Document ID

~~~java
@Test
void documentIdIsStableForSameAggregate() {
    String first = documentIdFactory.productId("tenant-7", "product-100");
    String second = documentIdFactory.productId("tenant-7", "product-100");

    assertThat(first).isEqualTo(second);
}
~~~

### 24.2. Two Tenants Do Not Collide

~~~java
@Test
void documentIdIncludesTenantIdentity() {
    String tenantA = documentIdFactory.productId("tenant-a", "product-100");
    String tenantB = documentIdFactory.productId("tenant-b", "product-100");

    assertThat(tenantA).isNotEqualTo(tenantB);
}
~~~

### 24.3. Replaying the Same Snapshot Creates No Duplicates

Integration test:

1. Process the same snapshot event twice.
2. Refresh the index if the test requires search visibility.
3. Search by `aggregateId`/`tenantId`.
4. Assert only one document exists with identical source content.

### 24.4. Stale Events Do Not Overwrite Newer Events

1. Process version 18.
2. Reprocess version 16.
3. Read the document.
4. Assert `sourceVersion` remains 18 and fields retain version 18 values.

### 24.5. Deletes Are Not Resurrected by Stale Events

1. Process snapshot version 18.
2. Process delete/tombstone version 19.
3. Resend snapshot version 18.
4. Assert the document remains deleted or non-searchable per chosen semantics.

### 24.6. Deltas Are Not Applied Twice

Send the same delta event twice and verify counters/stock change only once. If the test fails, add event deduplication or a version guard.

### 24.7. Schema Compatibility

Test old messages and new schema-version messages through the mapper/upcaster. Verify defaults, optional fields, and unknown fields behave deterministically.

### 24.8. Bulk Partial Failure

Build a batch containing valid items, stale events, and mapping-error items. Verify the consumer classifies each item, retries only retryable failures, and sends permanent failures to the DLQ.

## 25. Common Design Pitfalls

### Generating a New UUID on Every Event Processing Pass

Each retry creates a different document. Derive document IDs deterministically from aggregate identity.

### Using `eventId` as the Document ID for State Projections

Every change creates a new document. Use `aggregateId` or a composite projection key; reserve `eventId` for message identity.

### Assuming Stable IDs Prevent Duplicate Deltas

Stable IDs only target the same document. Additions/subtractions can still execute twice. Use snapshots, deduplication, or version guards.

### Lacking `aggregateVersion`

Stale events can overwrite newer events. Add monotonically increasing versions from the source or define a clear ordering strategy.

### Using Timestamps to Determine the Latest Event

Clock skew and timestamp precision make ordering unreliable. Use source versions/sequences.

### Hard Deleting While Replaying Old Events

Old events can recreate deleted documents. Use versioned deletes, tombstones, or a durable version ledger.

### Storing `tenantId` in a Field Without Including It in Identity

Two tenants with identical local IDs can overwrite each other. Use globally unique UUIDs or composite tenant identities.

### Concatenating Composite Keys Without Escaping

Delimiters can cause collisions. Use canonical encoding or length-prefixing.

### Changing the ID Algorithm During Reindexing

The new projection may assign different document identities. Keep the same ID factory or execute an explicit migration.

### Forgetting Routing on Updates/Deletes

Documents are indexed to a shard via routing, yet later operations look in a different shard. Use stable routing keys and pass them consistently.

### Acking Messages Before Elasticsearch Writes Succeed

Crashing after ack loses projection updates. Ack only after operations are confirmed per delivery policy.

### Treating Bulk as a Transaction

Some items may succeed while others fail. Inspect every item and perform selective retries.

### Assuming Outbox/CDC Eliminates the Need for Idempotency

Relays can publish duplicates. Consumers must still handle redelivery safely.

### Writing the Dedup Ledger and Elasticsearch as Two Independent Steps

Crashing between the two steps causes missed or repeated operations. Design idempotent snapshots or a consistent recovery workflow.

### Not Versioning Event Schemas

Older consumers can misparse replayed payloads. Add `schemaVersion` and test compatibility.

## 26. Data Synchronization Design Workflow

When building an Elasticsearch consumer:

1. Identify the source of truth and the target projection/document.
2. Determine whether one aggregate maps to one or multiple documents.
3. Separate `eventId`, `aggregateId`, `aggregateVersion`, and document ID.
4. Design an event envelope with `eventType`, `schemaVersion`, tenant, `occurredAt`, and needed correlation metadata.
5. Choose snapshot vs. delta and document payload semantics clearly.
6. Derive deterministic document IDs from source identity; use composite keys for tenant/projection scoping.
7. Use one unified ID factory across index, get, update, and delete.
8. Use outbox/CDC so changes are not lost between database commit and publish.
9. Design consumers for at-least-once delivery and idempotent behavior.
10. Use `aggregateVersion`/external versioning or version guards to block stale events.
11. Design deletes/tombstones so stale events cannot resurrect documents.
12. Choose stable routing if using custom routing.
13. Inspect every bulk item, retry transient errors, and route poison events to a DLQ.
14. Version message schemas and support replay/upcasting.
15. Monitor consumer lag, stale events, conflicts, DLQ, and projection version lag.
16. Maintain a reconciliation/rebuild plan to recover projections.
17. Test duplicates, out-of-order events, deletes, tenant collisions, replays, and partial bulk failures.

## 27. Summary

Data sync message design requires separating `eventId`, `aggregateId`, `aggregateVersion`, and Elasticsearch document ID. `eventId` identifies a single change emission; `aggregateId` identifies the source entity; document ID identifies the target projection. For a one-document-per-aggregate model, derive `_id` deterministically from source keys rather than generating a new UUID on each processing pass. For multi-tenant or multi-projection data, use composite identities with unambiguous encoding.

Snapshot events carry full state and are generally easy to make idempotent: reprocessing the same snapshot indexes the same document with the same content. Delta events describe only changes and can be applied twice; they require deduplication or version guards. Stable IDs also do not solve out-of-order events by themselves. Use `aggregateVersion` or a source sequence to prevent stale events from overwriting newer data.

Outbox/CDC transmits changes from the source more reliably, yet relays can still publish duplicates. Consumers need at-least-once handling, selective retries, bulk item inspection, and DLQs. Deletes must share the same document ID/routing as indexing and guard against stale events resurrecting documents via versioned deletes, tombstones, or a version ledger. Schema versions, reconciliation, and replay plans allow projections to evolve and recover when failures occur.

## References

- [Spring Data Elasticsearch – Object Mapping](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)
- [Spring Data Elasticsearch – Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch – IndexQuery API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/query/IndexQuery.html)
- [Elasticsearch – Index API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-index_.html)
- [Elasticsearch – Bulk API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-bulk.html)
- [Elasticsearch – Optimistic concurrency control](https://www.elastic.co/guide/en/elasticsearch/reference/current/optimistic-concurrency-control.html)
- [Elasticsearch – Document APIs and routing](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-get.html)
- [Debezium – Outbox Event Router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html)
- [Debezium – Change Data Capture](https://debezium.io/documentation/reference/stable/)
