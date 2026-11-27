# Building a Search Indexer from Data Change Events

An application often stores transactional data in a relational database while requiring full-text search, multi-attribute filtering, relevance ranking, or autocomplete. A search engine handles those queries far better than a transactional database, but the search index must stay updated whenever the source changes.

A serverless-friendly approach is building a **search index projection** from data change events. Whenever a record is created, updated, or deleted, the system emits an event to a broker. A Java function consumes the event, transforms the source data into a search document, and updates the index.

This pattern decouples search workloads from transactional workloads. The source database remains the authoritative system of record; the search index is a rebuildable projection. Because event processing involves retries, duplicates, and propagation lag, consumers must be idempotent, enforce update ordering, and have safe rebuild and reconciliation workflows.

This lesson covers the architecture from transactional outbox or CDC to a Java indexer, initial index bootstrapping, handling upserts/deletes, controlling bulk indexing/retries/backpressure, and safely rebuilding indexes.

## 1. Why Build a Search Index from Events?

Transactional databases are optimized for ACID transactions and key/relationship lookups. Search engines are optimized for operations such as:

- Full-text search and relevance scoring.
- Fuzzy matching, stemming, and autocomplete.
- Faceted search and aggregations.
- Filtering across many fields and arbitrary combinations of predicates.
- Querying over denormalized data.
- Serving heavy read queries without adding load to the transactional database.

Do not move all business queries into the search engine by default. Operations requiring strict transactions, final inventory checks, or access control decisions should verify against the authoritative source of truth when needed.

### 1.1. The Search Index Is Derived Data

The source database may span multiple normalized tables:

~~~text
products
  id, name, description, brand_id, category_id, status

brands
  id, name

categories
  id, name

search document
  product_id
  product_name
  description
  brand_name
  category_name
  searchable_attributes
  source_version
~~~

The search index stores a query-optimized projection. If the index is deleted or its mapping changes, the system can rebuild it from the database or event history.

Therefore:

- The database/domain service is the authoritative source of truth.
- Events signal that a change occurred or carry the change payload.
- The indexer transforms events into search documents.
- The search engine stores the projection to serve queries.
- Reconciliation detects and repairs drift.

Never keep critical business state exclusively inside the search index. If the index loses data, you must be able to regenerate it.

## 2. Overall Architecture

A common architecture consists of producers, an event source, a broker, and consumers:

~~~mermaid
flowchart LR
    A["HTTP command / domain service"] --> B["Source database"]
    B --> O["Outbox row / CDC log"]
    O --> Q["Event broker"]
    Q --> F["Java serverless indexer"]
    F --> T["Transform / enrich"]
    T --> S["Search engine index"]
    C["Search API"] --> S
    C --> A
    R["Reconciliation / reindex job"] --> B
    R --> S
~~~

| Component | Responsibility |
|---|---|
| Command/domain service | Validates business rules and updates source data |
| Source database | Stores authoritative state and executes transactions |
| Outbox or CDC connector | Turns data changes into durable events |
| Broker | Buffering, delivery, retries, and distribution |
| Java indexer | Validates, transforms, enriches, and writes search documents |
| Search engine | Serves search queries |
| Reconciliation job | Detects discrepancies and repairs drift |
| Search API | Enforces access control and formats results |

The indexer can run as AWS Lambda, Cloud Functions, Azure Functions, or another serverless/container consumer. The core design remains identical: durable events, safe repeated processing, and rebuildable indexes.

## 3. Choosing Domain Events vs. CDC

There are two common event sources.

**Domain events** describe meaningful business occurrences, such as `ProductPublished`, `ProductPriceChanged`, or `ProductDeleted`. Events are emitted by the domain/application service after business rules execute.

**Change Data Capture (CDC)** captures database-level mutations—for example, a row in `products` being inserted, updated, or deleted. CDC typically reads the database transaction log or native change stream.

| Criterion | Domain Event | CDC |
|---|---|---|
| Semantics | Carries business meaning | Describes storage-level row changes |
| Coupling | Coupled to domain contract | Coupled to database schema/tables |
| Data source | Application/domain service | Database log/connector |
| Payload | Can carry only fields needed by consumers | Often contains before/after row snapshots |
| Multi-table changes | Can emit one consolidated business event | Consumer must join/enrich or correlate multiple records |
| Use cases | Multiple domain consumers | Syncing read models, search indexes, data warehouses |

Domain events reduce consumer coupling to database schemas. CDC shines when capturing all changes from legacy systems or when producers cannot be modified. You can also combine CDC with an outbox table to emit standardized domain events.

Never emit an event directly after updating the database without guaranteeing consistency between the data transaction and event persistence. If the process crashes in between, the database commits while the event is lost.

## 4. Transactional Outbox Prevents Lost Events

A transactional outbox persists the business mutation and the event to publish inside the same database transaction.

Example when publishing a product:

~~~sql
BEGIN;

WITH updated_product AS (
    UPDATE products
    SET status = 'PUBLISHED',
        version = version + 1,
        updated_at = NOW()
    WHERE id = :product_id
    RETURNING id, version, name, description, brand_id, category_id, status
)
INSERT INTO outbox_event (
    event_id,
    aggregate_type,
    aggregate_id,
    aggregate_version,
    event_type,
    schema_version,
    payload,
    created_at
) SELECT
    :event_id,
    'Product',
    updated_product.id,
    updated_product.version,
    'ProductPublished',
    1,
    jsonb_build_object(
        'productId', updated_product.id,
        'aggregateVersion', updated_product.version,
        'name', updated_product.name,
        'description', updated_product.description,
        'brandId', updated_product.brand_id,
        'categoryId', updated_product.category_id,
        'status', updated_product.status
    ),
    NOW()
FROM updated_product;

COMMIT;
~~~

If the transaction rolls back, both the business update and the outbox row roll back. If it commits, a publisher reads the outbox and dispatches the event afterward.

Illustrative schema:

~~~sql
CREATE TABLE outbox_event (
    event_id UUID PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(200) NOT NULL,
    aggregate_version BIGINT NOT NULL,
    event_type VARCHAR(150) NOT NULL,
    schema_version INTEGER NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    published_at TIMESTAMPTZ
);

CREATE INDEX outbox_unpublished_idx
    ON outbox_event (created_at)
    WHERE published_at IS NULL;
~~~

The publisher reads unpublished rows, sends events to the broker, and marks them published only after broker confirmation per client semantics.

One gap remains: the broker receives the event, but the publisher crashes before writing `published_at`. On restart, the publisher resends the event. This is at-least-once behavior, meaning consumers must be idempotent. An outbox prevents lost events, but does not make broker delivery exactly-once.

### 4.1. Preventing Multiple Publishers from Claiming the Same Row

When running multiple publishers, use a safe claim mechanism to avoid concurrent duplicate sends. Options include row locking/claim leases, database `SKIP LOCKED` support, or a CDC connector managing offsets.

Do not hold database transactions open across slow broker network calls. Claim a small batch, commit lease/ownership, publish, and conditionally update status afterward. Leases need timeouts and recovery if a publisher crashes.

With CDC, a connector reads the transaction log and checkpoints offsets. Monitor connector lag, log retention, and resume behavior after outages so no change window is lost.

## 5. Event Contract for the Search Indexer

Events must carry identity, version, and sufficient details for consumers. Illustrative envelope:

~~~json
{
  "id": "evt-7c91",
  "source": "catalog-service",
  "type": "com.example.catalog.product-updated",
  "subject": "products/sku-1042",
  "time": "2026-11-17T10:15:30Z",
  "schemaVersion": 2,
  "aggregateId": "sku-1042",
  "aggregateVersion": 18,
  "operation": "UPSERT",
  "data": {
    "productId": "sku-1042",
    "name": "Java Serverless Handbook",
    "description": "A practical guide",
    "brandId": "publisher-7",
    "categoryId": "books",
    "status": "PUBLISHED"
  }
}
~~~

Key fields:

- **id:** stable event identity across all redeliveries.
- **source:** originating system emitting the event.
- **type:** change classification.
- **subject/aggregateId:** entity being modified.
- **time:** timestamp when the event was created.
- **schemaVersion:** payload contract version.
- **aggregateVersion:** monotonically increasing entity version.
- **operation:** `UPSERT` or `DELETE`.
- **data:** fields required for projection.

You can adopt CloudEvents or an internal envelope. With CloudEvents, `source + id` uniquely identifies an event. A separate business version is still needed to detect stale or out-of-order events.

### 5.1. Choosing Full-State vs. Thin Payloads

**Full-state events** carry the full entity state required by the index at the new version. Consumers can write documents without querying the source database.

Pros:

- Reduces read load on the source database.
- Loosens consumer coupling to the source schema.
- Simplifies event replay when events are durably archived.

Cons:

- Larger payloads.
- May carry sensitive data.
- Producers must update events whenever the projection adds fields.
- Older events may lack newly introduced fields.

**Thin events** carry only the entity ID, version, and change type. Consumers query the source database to assemble the document.

Pros:

- Small payloads.
- Indexer reads authoritative state at read time.
- Less data passes through the broker.

Cons:

- Increases query load on the source database.
- Reading "latest" state instead of state at the event's version can cause older events to index newer state, muddying ordering guarantees.
- Requires careful handling of deleted records and race conditions.

A hybrid option: events carry ID and version; consumers run a purpose-built projection query, checking versions and writing only if the fetched state matches the expected version.

## 6. Bootstrapping: Building the Initial Index

Events only capture mutations occurring after a subscription begins. An empty index must be seeded with existing data before serving full traffic.

Bootstrapping typically has two phases:

1. Taking a consistent snapshot of the source data.
2. Replaying/catching up on changes produced after the snapshot point.

~~~mermaid
sequenceDiagram
    participant DB as Source database
    participant CDC as Outbox / CDC
    participant Q as Broker
    participant I as Indexer
    participant S as Search index

    Note over DB,CDC: Establish consistent snapshot and change-stream checkpoint
    DB->>S: Bulk index snapshot
    CDC->>Q: Publish changes after checkpoint
    Q->>I: Deliver change events
    I->>S: Apply version-aware upsert/delete
    Note over I,S: Enable read traffic only after index catches up to source
~~~

How checkpoints are obtained depends on the database and CDC connector. Prefer connector-supported consistent snapshots and snapshot offsets. Never pair an application-server timestamp with a database scan and assume there is no gap.

### 6.1. Why Scanning the Database Before Subscribing Risks Data Loss

Failure scenario:

1. A job begins scanning the `products` table.
2. A product is updated mid-scan.
3. The event is emitted before the consumer starts reading.
4. Depending on timing, the scan may read the old or new row.
5. The consumer never receives the event needed to fix the document.

As a result, the index can permanently miss updates.

The solution is establishing a change-stream checkpoint aligned consistently with the snapshot. The snapshot loads state as of the checkpoint; then all events after that checkpoint are replayed. Use connectors supporting consistent snapshots or verified database-specific procedures.

### 6.2. Running Snapshot and Consumer Concurrently

A practical approach writes the snapshot to a new index while buffering or consuming post-checkpoint change events. Once the snapshot completes, apply accumulated events with version guards so stale events cannot overwrite newer state.

If event consumers write concurrently with the snapshot, every write must carry the source version and execute conditionally. Never let an older snapshot row overwrite a newer event already applied.

## 7. Designing the Search Document

Optimize search documents for the queries they serve. Example:

~~~json
{
  "productId": "sku-1042",
  "name": "Java Serverless Handbook",
  "description": "A practical guide",
  "brand": {
    "id": "publisher-7",
    "name": "Tech Press"
  },
  "category": {
    "id": "books",
    "name": "Books"
  },
  "status": "PUBLISHED",
  "searchableText": "Java Serverless Handbook A practical guide Tech Press Books",
  "sourceVersion": 18,
  "sourceUpdatedAt": "2026-11-17T10:15:30Z"
}
~~~

Principles:

- Use a stable document ID, typically the entity ID.
- Denormalize fields needed for filtering, sorting, and faceting.
- Retain `sourceVersion` to enforce update ordering.
- Do not index fields unused by queries.
- Distinguish exact-match, full-text, numeric, date, and nested fields.
- Configure language-appropriate analyzers and tokenizers.
- Include tenant/resource ownership metadata if the search API enforces authorization.
- Keep secrets and unnecessary sensitive data out of the index.

Search mappings form a contract between the indexer and the search API. Changing mappings often requires creating a new index and reindexing; not all field types can be altered in place.

## 8. Handling UPSERT and DELETE

Indexers primarily perform two operations:

- `UPSERT`: create or replace an entity's projection.
- `DELETE`: remove an entity from the search index.

`UPSERT` should write the complete document per the projection contract or perform partial updates under strict rules. With partial updates, explicitly handle removed or nullified fields so stale values do not linger.

`DELETE` must be treated as a versioned mutation, not an unconditional delete command.

### 8.1. Tombstones Prevent Deleted Documents from Resurrecting

Suppose version 20 is a `DELETE` event arriving before a version 19 `UPSERT` event. If the indexer deletes the document and then applies the stale `UPSERT`, the document reappears even though it was deleted at the source.

Persist delete versions/tombstones or use search engine external versioning/conditional writes:

- Apply events only when their version exceeds the recorded version.
- Store a tombstone recording entity ID and delete version.
- Ignore events older than the tombstone.
- Retain tombstones long enough to cover retries, replays, and snapshot overlaps.
- During index rebuilds, ensure snapshots/checkpoints never resurrect deleted records.

Some search engines support external versioning or optimistic concurrency control. If relying on those features, verify the engine's exact semantics. Otherwise, maintain version/tombstone state in document metadata or a durable state store.

Never purge version metadata immediately upon deleting a document if older events could still be replayed.

## 9. Ordering and Entity Versioning

Brokers typically guarantee ordering only within a single partition or message group—not across an entire topic. Multiple events for the same entity can arrive via different partitions or workers.

Example:

~~~text
Product sku-1042:
  version 17 -> name = "Old title"
  version 18 -> name = "New title"
~~~

If version 18 is indexed before version 17, a consumer lacking version guards can overwrite the newer title with the older one.

Safeguards:

- Partition by aggregate/entity ID so events for the same entity land in the same partition when supported by the broker.
- Assign monotonically increasing `aggregateVersion` values inside the source transaction.
- Use conditional updates so only newer versions are written.
- Never use event timestamps as the sole version, since clocks skew and timestamps collide.
- Handle duplicates and out-of-order events separately.

Versions must originate at the authoritative data source—never invented in the consumer.

The contract must ensure one `aggregateVersion` corresponds to one applicable projection state. If a single transaction emits multiple partial events for the same entity with the same version, include a sub-version/sequence to establish total ordering, or emit one full-state projection event. Using `aggregateVersion` alone cannot distinguish two distinct events sharing the same version.

### 9.1. Not Every Sequence Is an Aggregate Version

Database log sequences or offsets establish global or log-level ordering, not necessarily an entity's business version. With CDC, connector offsets help resume streams, but entity versions or source transaction metadata still must be interpreted per database semantics.

If one transaction mutates multiple related tables, consumers must know which projections are affected and ensure joined reads never mix state across two different transactions.

## 10. Idempotency for Event Consumers

Event brokers may redeliver messages if a consumer finishes processing before acknowledging, or a publisher may resend when unsure whether a prior send succeeded.

The indexer must tolerate the same event executing multiple times.

An event deduplication store can key on:

~~~text
source + event_id
~~~

An idempotency record stores:

- Event identity.
- Entity ID and aggregate version.
- Processing status.
- Receipt and completion timestamps.
- Relevant error metadata.

However, deduplicating by event ID alone is insufficient. Two different event IDs can describe states of the same entity; version guards prevent older state from overwriting newer state.

If using a dedup store to prevent concurrent duplicates, claiming must be an atomic operation with a lease/owner token. Separate `isCompleted` reads followed by `markCompleted` writes cannot prevent two workers from racing. In the design below, the atomic version guard in the search writer is the true correctness boundary; the dedup store reduces redundant work and aids status tracking.

### 10.1. Ordering Index Writes and Marking Events Completed

If you mark an event completed before the search engine confirms the write, a crash immediately afterward causes redeliveries to skip the event, leaving the document stale.

A safer order:

1. Validate the event and check identity/version.
2. Perform a conditional upsert/delete in the search engine.
3. Wait for write confirmation.
4. Mark the event completed in the dedup store if used.
5. Acknowledge the broker message.

If the search write succeeded but the process crashed before step 4 or acknowledgement, the event will run again. Version-aware upserts/deletes make re-execution harmless. This yields effectively-once projection semantics rather than cross-system exactly-once delivery.

## 11. Java Event Model

Example Java record for events:

~~~java
import java.time.Instant;
import java.util.Map;

public record ProductChangeEvent(
        String id,
        String source,
        String type,
        int schemaVersion,
        String aggregateId,
        long aggregateVersion,
        Operation operation,
        Instant occurredAt,
        Map<String, Object> data) {

    public enum Operation {
        UPSERT,
        DELETE
    }
}
~~~

In production, prefer strongly typed DTOs for core domain fields instead of an untyped `Map`. Validate `schemaVersion` and required fields before processing.

The record examples below require a Java version supporting records (Java 16+); on Java 17/21 serverless runtimes, this structure works out of the box.

Example document:

~~~java
import java.time.Instant;

public record ProductSearchDocument(
        String productId,
        String name,
        String description,
        String brandName,
        String categoryName,
        String status,
        long sourceVersion,
        Instant sourceUpdatedAt) {
}
~~~

Separate the mapper from the consumer for independent unit testing:

~~~java
public interface ProductDocumentMapper {
    ProductSearchDocument map(ProductChangeEvent event);
}
~~~

The mapper may enrich fields from a source read model if events omit certain attributes. Enrichment requires clear policies for version consistency, timeouts, and fallbacks.

## 12. Java Index Writer with Version Guards

The search engine adapter should expose conditional write operations:

~~~java
public interface SearchIndexWriter {

    WriteResult upsertIfNewer(
            String documentId,
            long sourceVersion,
            ProductSearchDocument document);

    WriteResult deleteIfNewer(
            String documentId,
            long sourceVersion);
}
~~~

`upsertIfNewer` and `deleteIfNewer` are application abstractions. Concrete adapters must use atomic conditional updates, external versioning, or optimistic concurrency supported by the search engine. Never implement this as a separate read-version-then-write sequence if races can occur between steps.

Example result enum:

~~~java
public enum WriteResult {
    APPLIED,
    ALREADY_CURRENT,
    STALE_EVENT
}
~~~

If an event carries a lower version than the indexed document, the writer returns `STALE_EVENT` and the consumer treats it as superseded. If versions match, retries of the same event/state return `ALREADY_CURRENT`.

Never treat every conflict as a retryable error. Distinguish version conflicts caused by stale events from transient search cluster failures.

## 13. Java Consumer Orchestration

A handler can coordinate validation, deduplication, mapping, and writing:

~~~java
public final class ProductIndexer {

    private final EventDedupStore dedupStore;
    private final ProductDocumentMapper mapper;
    private final SearchIndexWriter indexWriter;

    public ProductIndexer(
            EventDedupStore dedupStore,
            ProductDocumentMapper mapper,
            SearchIndexWriter indexWriter) {
        this.dedupStore = dedupStore;
        this.mapper = mapper;
        this.indexWriter = indexWriter;
    }

    public void handle(ProductChangeEvent event) {
        validate(event);

        String eventKey = event.source() + ":" + event.id();

        if (dedupStore.isCompleted(eventKey)) {
            return;
        }

        if (event.operation() == ProductChangeEvent.Operation.DELETE) {
            indexWriter.deleteIfNewer(
                    event.aggregateId(),
                    event.aggregateVersion());
        } else {
            ProductSearchDocument document = mapper.map(event);

            indexWriter.upsertIfNewer(
                    event.aggregateId(),
                    event.aggregateVersion(),
                    document);
        }

        dedupStore.markCompleted(eventKey);
    }

    private void validate(ProductChangeEvent event) {
        if (event == null) {
            throw new InvalidEventException("Missing event");
        }
        if (event.id() == null || event.id().isBlank()) {
            throw new InvalidEventException("Missing event id");
        }
        if (event.source() == null || event.source().isBlank()) {
            throw new InvalidEventException("Missing event source");
        }
        if (event.schemaVersion() < 1 || event.schemaVersion() > 2) {
            throw new UnsupportedEventSchemaException(event.schemaVersion());
        }
        if (event.aggregateId() == null || event.aggregateId().isBlank()) {
            throw new InvalidEventException("Missing aggregate id");
        }
        if (event.aggregateVersion() < 1) {
            throw new InvalidEventException("Invalid aggregate version");
        }
        if (event.operation() == null) {
            throw new InvalidEventException("Missing operation");
        }
    }
}
~~~

This is an illustrative skeleton. `isCompleted` and `markCompleted` must be backed by a durable store—never a static map. You can replace them with an atomic claim/complete record. If `markCompleted` fails after a successful index write, retries re-invoke the writer safely thanks to the version guard.

Route permanently invalid events to quarantine/DLQ along with diagnostic metadata. Never infinitely retry a payload missing an entity ID or carrying an unsupported schema version.

## 14. Batch Indexing for Higher Throughput

Calling the search engine once per event creates excessive network round trips. Bulk indexing combines multiple operations into a single request.

Benefits:

- Lower per-request overhead.
- Higher throughput.
- Better network utilization.
- Tunable document counts per batch.

Risks:

- Overly large batches cause memory pressure or request timeouts.
- Some items in a batch may succeed while others fail.
- Retrying an entire batch re-sends already-succeeded documents.
- Payloads may exceed search engine request size limits.

Inspect per-item outcomes rather than relying solely on the overall HTTP status. Retry only transient item failures; route permanently failed items to a DLQ/quarantine.

### 14.1. Choosing Batch Sizes

Start with moderate document counts and byte limits, then benchmark:

- Documents per batch.
- Total bytes per batch.
- Document construction time.
- Bulk request latency.
- Per-item success/failure rates.
- Peak memory consumption.
- Search cluster indexing pressure.
- Queue age and consumer throughput.

Do not size batches strictly by document count. A single document with a huge description or deeply nested fields can outweigh dozens of small documents.

### 14.2. Partial Batch Failures

If the event trigger supports partial batch responses, report only the failed messages so the platform retries just that subset. Otherwise, one failing record forces redelivery of the entire batch.

Consumers must remain idempotent because succeeded messages may still be redelivered alongside failed ones. With bulk APIs, inspect every item result so a batch is never marked completely succeeded while individual items failed.

## 15. Retries, DLQs, and Poison Events

Indexing failures fall into clear categories:

| Error Category | Examples | Handling |
|---|---|---|
| Transient | Timeouts, connection resets, search cluster temporarily unavailable, throttling | Retry with backoff and jitter |
| Permanent | Malformed event schema, missing entity ID, unsupported operation | Quarantine/DLQ and investigate |
| Ignorable conflict | Event version older than indexed document | Mark superseded/completed |
| Dependency/configuration | Invalid credentials, wrong endpoint, incompatible mapping | Alert and halt/throttle consumers per policy |

Retries need bounded limits and a DLQ. Poison events must never block a partition or batch indefinitely.

When replaying from a DLQ:

- Preserve the original event ID and aggregate version.
- Verify the event remains valid under current schemas and mappings.
- Check whether the index already holds a newer version.
- Do not replay unrelated side effects if the event is shared across consumers.
- Monitor replay rates and recurring errors.

A DLQ is an isolation area for actionable remediation—not permanent storage without an owner.

## 16. Backpressure and Protecting the Search Cluster

If producers emit 5,000 events/sec while the search cluster sustains 1,000 documents/sec, backlogs will grow. Scaling Lambda concurrency indefinitely can overload the search cluster, triggering rejections and cascading retries.

Throttling layers:

- Maximum consumer concurrency.
- Batch document counts and byte sizes.
- Per-index and per-tenant rate limits.
- Bounded worker pools.
- Search cluster write capacity.
- Pausing/slowing polling when downstream saturates.
- Retry backoff on `429` or cluster overload responses.
- Bulkheads isolating critical indexes or tenants.

Monitor queue age alongside search indexing pressure. When a cluster is saturated, increasing consumer concurrency usually makes things worse.

### 16.1. Per-Index and Per-Tenant Limits

One tenant can emit a massive burst and monopolize indexing capacity. For multi-tenant workloads, consider:

- Separate partition keys and queues per workload class.
- Per-tenant rate limits.
- Fair scheduling.
- Maximum document size caps.
- Quotas for bulk operations.
- Separate indexes or clusters where isolation demands it.

Never trust an unverified `tenantId` from a payload to enforce security boundaries. Tenant identities must be verified from trusted sources.

## 17. Mapping and Schema Evolution

Search mappings evolve alongside query requirements—for instance, changing a `name` field from `text` to `keyword`, updating analyzers, or adding nested objects.

Manage versions for both event schemas and index mappings:

- Consumers know which `schemaVersion` values they support.
- Mappers can translate older events into current document shapes.
- New fields define sensible defaults or nullable semantics.
- Changing field types typically requires a new index.
- Do not remove old fields until all producers and consumers have migrated.
- Reindex whenever analyzers or mappings change incompatibly.

Never assume event schemas and search index mappings are identical. Producers can emit stable domain events while indexers project them into evolving index versions.

### 17.1. Schema Registries or Contract Validation

In multi-producer/multi-consumer systems, use a schema registry or contract tests to enforce compatibility—backward, forward, or full compatibility depending on deployment strategy.

Event consumers must respond deterministically to unsupported schema versions: route to quarantine/DLQ and alert, never silently drop critical fields and write corrupted documents.

## 18. Zero-Downtime Rebuilds with Blue-Green Indexes and Aliases

Occasionally an entire index must be rebuilt:

- Mappings or analyzers change.
- Document projection logic changes.
- An index becomes corrupted or misses data.
- Computed fields or `searchableText` rules change.
- Migrating to a new search cluster.

Never delete a live production index before rebuilding it. Create a new index, load a snapshot, replay catch-up events, and atomically swap the alias once caught up.

~~~mermaid
flowchart TD
    A["Current index: products-v1"] --> U["Alias: products"]
    S["Source snapshot + CDC checkpoint"] --> B["Build products-v2"]
    Q["Events after checkpoint"] --> C["Catch-up consumer"]
    C --> B
    B --> D["Validate count, versions, sample queries"]
    D --> E{"Lag low enough and data accurate?"}
    E -->|Yes| F["Atomically switch alias products -> v2"]
    F --> G["Search API reads v2"]
    E -->|No| C
    F --> H["Keep v1 during rollback window"]
~~~

Steps:

1. Create the new index with updated mappings/version.
2. Capture a consistent snapshot and checkpoint.
3. Bulk-index the snapshot into the new index.
4. Replay events occurring after the checkpoint.
5. Monitor consumer lag and source versions.
6. Validate document counts, version distributions, and sample queries.
7. Atomically switch the alias if supported by the search engine.
8. Monitor error rates and latency post-cutover.
9. Retain the old index for a rollback window.
10. Delete the old index once the rollback window expires.

If the search engine lacks aliases, use an equivalent routing or configuration switch and verify atomicity.

### 18.1. Avoiding Uncontrolled Dual Writes

During rebuilds, events may need to flow to both old and new indexes. Use a single consumer/router performing version-aware writes to both, or run two independent consumers with managed checkpoints.

Never have application commands write directly to both the database and the search engine as if they formed an atomic transaction. If one write succeeds and the other fails, data drifts out of sync.

## 19. Search Consistency and User Experience

Event-driven indexing introduces eventual consistency: the database commits first, and the search index updates shortly after.

A user who just created a product might not immediately see it in search results. Define clear API contracts:

- Return the created/updated resource directly from the write API upon database commit.
- Expose operation or indexing status when index readiness matters.
- Allow clients to retry search briefly.
- Support direct lookups by ID when search hasn't caught up yet.
- Never use search results as final confirmation of a write transaction.

Some workflows require read-your-writes semantics. You can wait briefly for index acknowledgement within tight bounds, or expose indexing status for polling—avoid holding HTTP requests open across large backlogs.

Search APIs should tolerate bounded staleness and surface appropriate UI states rather than assuming synchronous database-to-index updates.

## 20. Reconciliation: Detecting Index Drift from Source

Even with healthy event pipelines, operational errors, mapper bugs, DLQs, or retention gaps can cause an index to drift from its source.

A periodic reconciliation job can:

- Compare entity counts grouped by status or tenant.
- Compare source versions against indexed versions.
- Sample documents and compare normalized fields or hashes.
- Find active source entities missing from the index.
- Find indexed documents no longer present at the source.
- Verify tombstone and delete propagation.
- Emit repair events or reindex affected entity groups.

You do not need full-table scans continuously. Partition by time or ID ranges, use `updated_at`/version watermarks, or schedule full reconciliations less frequently.

When repairing drift, route updates through the same version-aware writer. Never overwrite newer versions currently being processed by live consumers with stale reconciliation snapshots.

## 21. Security and Sensitive Data in Search Indexes

Search indexes are often easier to query broadly than normalized databases, meaning denormalization can expand data exposure.

Enforce:

- Indexing only fields needed for search.
- Excluding secrets, tokens, and payment credentials.
- Classifying PII and applying masking or minimization.
- Enforcing tenant and resource filters server-side.
- Never trusting client-supplied filters for tenant isolation.
- Encrypting data in transit and at rest.
- Restricting index write permissions exclusively to the indexer.
- Restricting index read/query permissions to the Search API.
- Auditing access and administrative operations.
- Deleting or updating sensitive records per retention and deletion policies.

If a user's permission to view a resource is revoked, the Search API must enforce current permissions. Presence of a document in the index never grants implicit read access.

### 21.1. Data Deletion and Privacy

When handling a deletion request, verify:

- Has the source record been deleted or anonymized?
- Was the delete event published?
- Has the search index applied the tombstone?
- Do caches or replicas still hold the data?
- How long do snapshots and backups retain the data?
- Could an index rebuild accidentally re-ingest deleted data?

Tombstones and deletion ledgers may need retention long enough to prevent old events or snapshots from resurrecting deleted records. Deleting from the search index does not automatically purge backups or event archives.

## 22. Observability for the Indexing Pipeline

Monitor the entire path from source to search index, not merely function invocation durations.

| Metric | Meaning |
|---|---|
| Outbox pending count | Events awaiting publication |
| CDC connector lag | Delay reading the database transaction log |
| Broker backlog | Events queued for consumers |
| Oldest event age | Age of the oldest unprocessed event |
| Consumer throughput | Events processed per second |
| Indexing latency | Time from source commit to document becoming searchable |
| Bulk request latency | Time to execute batch writes |
| Item failure rate | Ratio of failed items inside bulk requests |
| Version conflict/stale count | Stale events skipped by version guards |
| Duplicate event count | Event identities redelivered |
| DLQ depth | Failed events awaiting investigation |
| Reconciliation mismatch | Discrepancies between source and index |
| Search cluster rejections | Cluster pressure or capacity exhaustion |

Include trace/correlation IDs and event IDs in logs to trace individual mutations. Avoid using high-cardinality entity IDs, tenant IDs, or event IDs as metric labels; keep granular identifiers in logs and traces.

A useful SLO measures the percentage of changes indexed within a target window—for instance, the percentage of events searchable within a defined latency budget. Set thresholds based on product needs and system capacity.

## 23. Testing the Indexing Pipeline

Scenarios to verify:

1. A product is created and appears in search results.
2. A product's name/description changes and the document updates.
3. A product is deleted and disappears from search results.
4. Identical events are redelivered multiple times.
5. An older event version arrives after a newer version.
6. A `DELETE` arrives before an older `UPSERT`.
7. The consumer crashes after writing to the index but before acknowledging.
8. The search cluster times out or throttles requests.
9. One item inside a bulk request fails.
10. An event arrives with an unsupported new schema version.
11. A snapshot runs concurrently with a live event stream.
12. An index rebuild runs while production continues receiving mutations.
13. Alias cutover and rollback.
14. DLQ replay after the index already holds a newer version.
15. One tenant's burst does not starve other tenants.
16. Delete/PII erasure requests propagate through the index and caches.
17. Reconciliation detects and repairs a missing document.

Test concurrency and crashes against realistic broker, database, and search engine test environments whenever possible. Mocks verify mapper logic only; they cannot prove atomic version guards or real broker delivery semantics.

## 24. Common Design Pitfalls

| Pitfall | Consequence | Mitigation |
|---|---|---|
| Updating DB and publishing events separately | Lost events after DB commit | Transactional outbox or CDC |
| Subscribing after scanning a snapshot | Changes missed in the gap | Consistent snapshot + checkpoint/catch-up |
| Missing aggregate versions | Stale events overwrite newer state | Version-aware conditional writes |
| Deduplicating only in memory | Duplicates after restarts/scale-out | Durable dedup and version guards |
| Deleting without tombstones/versions | Stale events resurrect documents | Versioned tombstones |
| Retrying entire bulk batches | Extra load and re-writing succeeded items | Per-item retry handling |
| Missing DLQ/quarantine | Poison events stall the pipeline | Error classification and DLQs |
| Raising concurrency on cluster overload | Higher rejection and retry rates | Backpressure and rate limits |
| Treating search index as source of truth | Hard to recover from index loss/corruption | Rebuild from authoritative source |
| Rebuilding directly over the live index | Search downtime or missing results | New index + catch-up + alias switch |
| Skipping reconciliation | Drift persists silently | Periodic version/count/hash checks |
| Indexing excessive PII | Expanded data exposure | Data minimization and access controls |

## 25. Step-by-Step Guide to Building an Event-Driven Indexer

1. **Choose the event source.** Domain events, transactional outbox, or CDC based on producer and database ownership.
2. **Design the event contract.** Include event ID, source, schema version, entity ID, operation, and aggregate version.
3. **Ensure durable event emission.** Use an outbox or CDC checkpoints so mutations are never lost.
4. **Bootstrap the index.** Use consistent snapshots paired with change-stream checkpoints.
5. **Design documents and mappings.** Index only query-needed fields while retaining source versions and ownership metadata.
6. **Implement the Java consumer.** Validate, transform, enrich, and perform conditional writes.
7. **Handle idempotency and ordering.** Combine durable deduplication, version guards, and delete tombstones.
8. **Use bounded batching.** Monitor byte sizes, durations, partial item failures, and memory.
9. **Configure retries and DLQs.** Retry transient errors, quarantine permanent errors, and support controlled replays.
10. **Apply backpressure.** Cap concurrency and rates to protect the search cluster.
11. **Protect sensitive data.** Enforce tenant authorization, data minimization, and deletion policies.
12. **Instrument end-to-end observability.** Track outbox/CDC lag, queue age, indexing latency, and mismatches.
13. **Support safe rebuilds.** Build new indexes from snapshots, catch up, validate, and switch aliases.
14. **Run periodic reconciliation.** Repair missing, stale, or orphaned documents.
15. **Test failure modes.** Simulate duplicates, out-of-order arrivals, crashes, timeouts, DLQ replays, and rollbacks.

## 26. Self-Check Questions

- Why should a search index be treated as a rebuildable projection?
- How do domain events differ from CDC?
- How does a transactional outbox prevent lost events?
- Why can an outbox publisher still emit duplicates?
- Which fields does an event envelope need to support idempotency and ordering?
- When should you use full-state events vs. thin events?
- How must snapshot bootstrapping coordinate with checkpoints to avoid missing updates?
- How do aggregate versions stop stale events from overwriting newer documents?
- Why do deletes require tombstones?
- How does event-ID deduplication differ from version guards?
- Why must bulk responses be handled item by item?
- When should an event be routed to a DLQ?
- How does backpressure protect a search cluster?
- What are the benefits of rebuilding via a new index and alias switch?
- What data should reconciliation compare?
- How do you enforce tenant isolation and handle PII erasure requests?
- Which metrics capture end-to-end latency from source commit to searchable document?
