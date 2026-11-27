# Choosing the Source of Truth and Projection Model for Search

In an architecture with Elasticsearch, data typically exists in at least two forms: business records in the source system and documents prepared for search queries. These two forms serve different purposes. The source of truth holds the authoritative business state; the search projection (read model) is designed to serve querying, filtering, sorting, autocomplete, and fast display.

Elasticsearch should not be treated as a verbatim copy of the entire database. A search document is usually selective data, combined or transformed from multiple sources to match actual query needs. When designing synchronization, you need to clearly define which data is authoritative, which system owns each field, how to update the projection, how to handle late-arriving events, and how to rebuild the index when the mapping or search model changes.

In Spring Data Elasticsearch, a controllable organization is to keep the domain model and the search document separate when they serve different purposes. A service or projection handler reads authoritative data, builds the search document, and writes it to Elasticsearch using a repository or `ElasticsearchOperations`. This approach optimizes search without making the business model depend on index mappings and structures.

## 1. What Is the Source of Truth?

The source of truth is the final authority for a given type of business data. When two systems report different values, the system designated as the source of truth determines the correct value.

For example, in an e-commerce system:

| Data | Possible source of truth | Role of Elasticsearch |
|---|---|---|
| Product name, SKU, and status | Product service/database | Stores a projection for searching and filtering |
| Current selling price | Pricing service/database | Denormalizes price into the document for sorting/filtering |
| Sellable inventory | Inventory service/database | Can display a snapshot; order placement decisions still check the authoritative inventory source |
| Orders and payment status | Order/payment service | Order search and dashboards |
| User profiles | Identity/profile service | Search by indexable fields |

Elasticsearch can contain very fresh data and answer queries quickly, but that does not automatically make it the source of truth for transactions. A search result can lag behind the database by milliseconds or seconds, can be missing during synchronization, and can be rebuilt from other sources.

### Distinguishing Source of Truth and Projection

- The source of truth is responsible for enforcing business rules and the consistency required for transactions.
- The search projection is responsible for making data easy to query according to search needs.
- A projection can denormalize, rename fields, create derived fields, or omit fields not needed for search.
- A projection must be reproducible from the source of truth or from a sufficiently informative event log.

If an application updates business values directly in Elasticsearch without updating the source of truth, the two systems will diverge. The next sync cycle may overwrite that change, or the change will be completely lost when the index is rebuilt.

## 2. Why Not Use Domain Entities Directly as Search Documents?

Domain entities typically reflect business rules and write structures. Search documents reflect how data is queried and displayed. The two models may overlap partially, but they do not have to be identical.

For example, a domain model might separate products, categories, brands, and prices into separate tables or aggregates:

```text
Product
  id
  name
  brandId
  categoryId

Brand
  id
  name

Category
  id
  displayName

Price
  productId
  amount
  currency
```

A search page typically needs a document that already includes the brand name, category name, price, and filter fields:

```json
{
  "id": "p-100",
  "name": "Wireless Mouse",
  "brand": {
    "id": "b-10",
    "name": "Acme"
  },
  "category": {
    "id": "c-20",
    "name": "Accessories"
  },
  "price": {
    "amount": 29.99,
    "currency": "USD"
  },
  "searchText": "Wireless Mouse Acme Accessories"
}
```

This document is a projection. It combines data from multiple aggregates to avoid performing joins on every search request.

### Benefits of Separating the Two Models

- The domain model does not have to carry search-only fields.
- Search mappings can change based on query requirements without forcing changes to the business schema.
- Multiple projections can be created for different use cases.
- The index can be rebuilt from the source of truth when analyzers or mappings change.
- Data ownership and synchronization responsibilities are clearer.

## 3. Choosing the Source of Truth per Field

A search document may combine data from multiple services. Therefore, you should not only identify the source of truth for the whole document; you need to identify the owner of each group of fields.

For example:

| Field in projection | Owner | Update mechanism |
|---|---|---|
| `name`, `description`, `sku` | Product service | Product created/updated event |
| `brandName` | Brand service | Brand changed event or projection refresh |
| `price` | Pricing service | Price changed event |
| `availableQuantity` | Inventory service | Inventory snapshot/event if the use case requires it |
| `ratingAverage` | Review/rating service | Aggregate updated on review events |
| `searchKeywords` | Search projection logic | Recomputed from source fields |

An aggregated field like `ratingAverage` has no single corresponding record in the source; it is computed from many reviews. Define which service owns this calculation or aggregate and how the projection receives new values.

### Fields with Multiple Update Sources

If multiple services write to the same field in Elasticsearch, the rule for "who wins" becomes unclear. You should designate a single owner for each field or group of fields. A projection handler can receive events from multiple sources, but it must know which event is allowed to update which fields.

For example, a `ProductUpdated` event should not overwrite the current price if the price belongs to the Pricing service. It should only update the product portion of the projection, then combine it with the known price or request a projection refresh from the authoritative pricing source.

## 4. Search Projection as a Read Model

In a CQRS architecture, the write model and read model can be designed differently:

```text
                 WRITE SIDE
Client -> Product Service -> Authoritative Database
                 |
                 | Outbox / CDC / Domain Event
                 v
              Event Stream
                 |
                 v
              Projector
                 |
                 v
          Elasticsearch Index
                 |
                 v
                 READ SIDE
Client -> Search API -> Search Projection
```

The write side handles business commands and persists authoritative data. The projector receives changes, transforms them into documents optimized for querying, and writes them to Elasticsearch. The Search API reads the projection instead of performing multiple joins across source systems.

The read model may lag behind the write model. This is eventual consistency. The API must account for this characteristic and not use search results as the final authority for operations requiring the latest transactional state.

### Example Business Flow

1. A user renames a product.
2. The Product service validates business rules and saves the new name to the database.
3. The service writes a `ProductUpdated` event in the same transaction or publishes the event via a reliable mechanism.
4. The projector receives the event and reads or extracts the necessary payload.
5. The projector rebuilds the search document and writes it to the index.
6. A user searches; once the projection is updated, the new name appears in the results.

If step 4 or 5 fails, the event needs to be retried or replayed. You should not ask the user to update the product again just to fix a failed search write.

## 5. Ways to Sync from Source of Truth to Elasticsearch

No single synchronization mechanism fits every system. Common options include:

| Mechanism | How it works | Pros | Cons |
|---|---|---|---|
| Direct dual write | Service writes to database then Elasticsearch | Easy to start, few components | Two writes have no shared transaction; data can easily diverge |
| Transactional outbox | Writes data and event in the same DB transaction; worker publishes event | No lost events between DB commit and publish when implemented properly | Requires outbox publisher, retries, and event management |
| CDC | Reads the database transaction log | Captures changes from multiple writers, reduces reliance on event-publishing code | Requires CDC infrastructure and handling schema/event semantics |
| Watermark polling | Periodically reads records with a newer `updatedAt` | Simple, easy to implement for small systems | Has latency, must handle duplicate timestamps and deleted records |
| Scheduled full rebuild | Scans the entire source and rebuilds the index | Easy to reproduce, useful for small datasets or batch | Resource-intensive and unsuitable for near real-time requirements |

### Why Is Dual Write Error-Prone?

Suppose a service executes:

```java
productRepository.save(product);
searchRepository.save(toSearchDocument(product));
```

If the database commit succeeds but Elasticsearch times out, the two systems diverge. If you reverse the order and Elasticsearch succeeds while the database rolls back, the search index contains data that does not exist in the source of truth. Without a distributed transaction spanning both systems, the two operations are not atomic.

Dual write can be acceptable in small applications if a reconciliation/rebuild mechanism exists and temporary drift is acceptable. For critical data, transactional outbox or CDC is usually more reliable.

## 6. Transactional Outbox

Transactional outbox stores business changes and the event to be published in the same transaction of the source database.

Example table:

```sql
CREATE TABLE outbox_event (
    event_id       VARCHAR(64) PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id   VARCHAR(100) NOT NULL,
    event_type     VARCHAR(100) NOT NULL,
    aggregate_version BIGINT NOT NULL,
    payload        JSON NOT NULL,
    created_at     TIMESTAMP NOT NULL,
    published_at   TIMESTAMP NULL
);
```

Business transaction:

```text
BEGIN
  UPDATE product ...
  INSERT INTO outbox_event (... ProductUpdated ...)
COMMIT
```

If the transaction rolls back, both the product update and the outbox event roll back. If the commit succeeds, the event remains in the outbox so the publisher can resend it after the broker or Elasticsearch recovers.

### Publisher and Projector

The outbox publisher reads unpublished events, sends them to a broker or directly to a worker, and marks them as published. The projector receives the event and updates the projection in Elasticsearch.

Operational requirements:

- Events have a unique ID for deduplication.
- Retry/backoff is in place when publishing or projecting fails.
- Do not mark an event as complete before the required step succeeds.
- Have a mechanism for handling poison or invalid events.
- Have retention/cleanup for processed outbox entries.
- Monitor lag from commit time to when the projection becomes searchable.

Outbox typically provides at-least-once delivery. Therefore, the projector must be idempotent; never assume an event is delivered only once.

## 7. CDC and Polling

### Change Data Capture

CDC reads the database transaction log to detect inserts, updates, and deletes. It fits well when multiple applications write to the database or when you cannot modify every writer to emit domain events.

CDC provides data-level changes. A single row change does not always carry full business semantics. The projector may need to read related tables or combine multiple changes into a complete projection.

### Polling by `updatedAt`

For smaller systems, you can store a watermark and query periodically:

```sql
SELECT *
FROM product
WHERE updated_at >= :watermark
ORDER BY updated_at, id
LIMIT :batch_size;
```

Do not use only `updated_at > :watermark` if multiple records can share the same timestamp or if database timestamp precision is low. A stable cursor can be the pair `(updated_at, id)`, or you can use an overlap window and deduplicate by version/ID.

Polling must also handle deletes. A physically deleted row will no longer appear in an `updated_at` query; you need soft deletes, a deletion log, an outbox, or CDC to know which documents must be deleted from Elasticsearch.

## 8. Designing Search Documents Around Queries, Not Table Structures

A search projection should start from the questions the search API must answer:

- Do users search by name, SKU, or description?
- Do you need to filter by brand, category, status, tenant, or time?
- Do you need to sort by price, updated date, or popularity?
- Are autocomplete or synonyms required?
- Do you need to preserve relationships between attributes within the same item?
- Which fields must the results display without calling additional services?

From those query patterns, choose the fields, mappings, and document shape. Do not dump the entire database schema into Elasticsearch and figure out how to query it later.

### Example Projection for a Product Page

```json
{
  "id": "p-100",
  "sku": "WM-100",
  "name": "Wireless Mouse",
  "nameSuggest": ["Wireless Mouse", "Mouse Wireless"],
  "description": "Compact wireless mouse with USB receiver",
  "brand": {
    "id": "b-10",
    "name": "Acme"
  },
  "categories": [
    { "id": "c-20", "name": "Accessories" },
    { "id": "c-21", "name": "Computer" }
  ],
  "priceAmount": 29.99,
  "currency": "USD",
  "status": "ACTIVE",
  "updatedAt": "2026-11-13T10:30:00Z"
}
```

The document flattens some relational data so search and display require no joins. Its structure can differ from both the domain model and the database schema.

## 9. Denormalization: Copying Fields for Fast Queries

Elasticsearch is optimized for document-level queries. Copying related fields into the search document avoids read-time joins.

For example, each product document stores `brandName` instead of storing only `brandId`. When filtering or displaying results, the API can use `brandName` directly.

Advantages:

- Search queries are simpler and usually faster.
- You can filter, sort, and aggregate on denormalized fields.
- Search responses contain enough data for basic display.
- Fewer calls to other services during a search request.

Costs:

- A change in a related source may require updating many projections.
- Duplicated data can be temporarily inconsistent.
- Rebuilding requires combining data from multiple sources.
- Ownership and versioning must be clearly defined for each part of the projection.

Denormalization is a deliberate decision for read performance. It does not eliminate the need for synchronization; it shifts the cost from query time to projection/update time.

## 10. Choosing Flat Objects, Nested, or Join Fields

The projection model should match query semantics.

| Shape | When to use | Example |
|---|---|---|
| Flat field | Only need to filter/sort on independent attributes | `brandName`, `status`, `priceAmount` |
| Standard object | Sub-fields are queried independently without needing to match the same object | `brand.id`, `brand.name` |
| `nested` | Conditions must match on the same element of an object array | A variant with a specific size and color |
| Parent-child join | Children have independent lifecycles and require bidirectional relational queries | A product with millions of independent reviews, if proven suitable by workload |

### Common Pitfall with Object Arrays

Suppose a product has two variants:

```json
{
  "variants": [
    { "color": "red", "size": "S" },
    { "color": "blue", "size": "L" }
  ]
}
```

If `variants` is a standard object, Elasticsearch may flatten fields into value arrays. A query `color=red AND size=L` can match the document even though no variant is both red and size L. If conditions must match on the same variant, use `nested` mapping/queries.

Do not use `nested` just because the JSON has an array of objects. Use it when queries need to preserve relationships between fields within the same element.

## 11. Spring Data Elasticsearch: Separating Domain Entity and Projection Document

You can define a source model in the service/domain layer and a separate document for Elasticsearch.

Domain model (illustrative):

```java
public record Product(
    String id,
    String sku,
    String name,
    String brandId,
    String categoryId,
    ProductStatus status,
    long version) {
}
```

Search document:

```java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products-read")
public class ProductSearchDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String brandId;

    @Field(type = FieldType.Keyword)
    private String brandName;

    @Field(type = FieldType.Keyword)
    private String categoryId;

    @Field(type = FieldType.Keyword)
    private String categoryName;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Double)
    private Double priceAmount;

    @Field(type = FieldType.Date)
    private Instant updatedAt;

    @Field(type = FieldType.Long)
    private Long sourceVersion;

    // Constructors, getters and setters
}
```

`ProductSearchDocument` includes denormalized fields and `sourceVersion` to track the business version. `sourceVersion` is an application-managed field in the projection, distinct from Elasticsearch's `_version`, `_seq_no`, and `_primary_term`.

### Mapper Creating the Projection

```java
public ProductSearchDocument toSearchDocument(
        Product product,
        Brand brand,
        Category category,
        Price price) {

    ProductSearchDocument doc = new ProductSearchDocument();
    doc.setId(product.id());
    doc.setSku(product.sku());
    doc.setName(product.name());
    doc.setBrandId(brand.id());
    doc.setBrandName(brand.name());
    doc.setCategoryId(category.id());
    doc.setCategoryName(category.displayName());
    doc.setStatus(product.status().name());
    doc.setPriceAmount(price.amount());
    doc.setUpdatedAt(Instant.now());
    doc.setSourceVersion(product.version());
    return doc;
}
```

The mapper is where the authoritative model is converted into the search model. In production, inject a `Clock` instead of calling `Instant.now()` directly if time needs to be tested; `updatedAt` should also be clearly defined as either source time or projector update time.

## 12. Writing Projections via `ElasticsearchOperations`

After building the search document, write it to the index:

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

public class ProductProjectionWriter {

    private final ElasticsearchOperations operations;

    public ProductProjectionWriter(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void upsert(ProductSearchDocument document) {
        operations.save(
            document,
            IndexCoordinates.of("products-read")
        );
    }
}
```

Using `save` with a stable ID writes the projection for the same entity ID to the same document. If using an alias, pass `IndexCoordinates` configured for the application's alias. Keep the writer separate from the domain repository to make it clear that this is a read model.

For large datasets, you can use bulk indexing via `ElasticsearchOperations` to reduce round trips. When using bulk, check each item's response and retry failures appropriately; never treat a bulk request as an atomic transaction.

## 13. Projector Receiving Events and Rebuilding Documents

A projector can receive an event containing an ID and version, then read the latest state from the source of truth to build the projection:

```java
public class ProductProjectionHandler {

    private final ProductReadService productReadService;
    private final ProductProjectionMapper mapper;
    private final ProductProjectionWriter writer;

    public void onProductChanged(ProductChanged event) {
        Product product = productReadService.getById(event.productId());
        Brand brand = productReadService.getBrand(product.brandId());
        Category category = productReadService.getCategory(product.categoryId());
        Price price = productReadService.getCurrentPrice(product.id());

        ProductSearchDocument document =
            mapper.toSearchDocument(product, brand, category, price);

        writer.upsert(document);
    }
}
```

Reading the latest state from the source of truth keeps the projector from relying entirely on old event payloads. However, you must ensure related sources can be read with the required consistency and that events carry versions so stale processing does not overwrite a newer projection.

Another option is for the event to carry all data needed to build the projection. This reduces calls to the source systems, though it increases event payload size and requires managing event schemas/versions.

## 14. Idempotency: Handling the Same Event Multiple Times

Events can be redelivered when a worker crashes after processing but before acknowledging. Therefore, the projector must be idempotent: receiving the same event multiple times must not produce incorrect results or duplicates.

For a one-document-per-product projection, using the product ID as the Elasticsearch `_id` overwrites the same document instead of creating a new record with a random ID.

```java
document.setId(event.productId());
operations.save(document, indexCoordinates);
```

However, using a stable ID alone is not enough when events can arrive out of order. An old event can overwrite a newer projection. You need to combine it with a business version or sequence.

### Using Source Version to Block Stale Events

Example event:

```json
{
  "eventId": "evt-9001",
  "aggregateId": "p-100",
  "aggregateVersion": 12,
  "eventType": "ProductUpdated"
}
```

The projection stores `sourceVersion = 12`. If a version 11 event arrives later, the projector must not overwrite the version 12 document. You can check the current version and ignore stale events, or use conditional updates/optimistic concurrency to ensure the check-and-write is safe when multiple projectors run concurrently.

Do not confuse `aggregateVersion` issued by the source of truth with `_version` or `_seq_no` managed by Elasticsearch. They have different scopes and meanings.

## 15. Event Ordering and Concurrent Updates

Suppose `ProductUpdated` version 12 is processed before version 11 due to parallel workers:

```text
Event version 11 -----------+----> arrives late
                            |
Event version 12 ----> processed first ----> projection version 12
                            |
Event version 11 ----------------------> must not overwrite version 12
```

Ways to handle this:

- Partition events by aggregate ID to preserve ordering within the same aggregate.
- Use a monotonically increasing aggregate version.
- Ignore events with a version less than or equal to the current projection version.
- Use Elasticsearch optimistic concurrency or an update script to check the version atomically when there are multiple writers.
- Limit processing to one projector per key at a time if the architecture allows.

If you check the version with a GET followed by an unconditional save, two workers can still race. When guarantees are required, the version check and write must be performed in one conditional operation or serialized by key.

## 16. Projections from Multiple Data Sources

A document may depend on Product, Brand, Price, Inventory, and Rating. When one source changes, the projector must update the corresponding part of the projection.

```text
Product events ----+
Brand events ------+
Price events ------+----> Projection coordinator
Inventory events -+              |
Rating events -----+              v
                         ProductSearchDocument
```

There are two common strategies:

### Re-reading the Entire Projection

Each event triggers re-reading all required sources and creating a new document. This is simpler in logic and reduces the risk of mis-merging fields, though it can generate significant read traffic and requires source services to be available.

### Partial Projection Updates

Each event only updates the fields owned by that source. This reduces read calls, but requires clear management of field ownership, per-part versioning, and out-of-order event delivery.

For infrequently changing data or small projections, rebuilding the document from the sources of truth is usually easier to maintain. With high event volume and many sources, you may need separate projection state or an event model designed for safe merging.

### Preventing One Source's Event from Overwriting Another Source's Fields

If `ProductUpdated` rebuilds the document without re-reading `Price`, it may write a stale price. If `PriceChanged` writes a partial document carelessly, it may wipe out product fields. You need one of the following mechanisms:

- Full rebuild from the authoritative sources.
- Store projection state and update fields by owner.
- Emit events containing sufficiently complete snapshots.
- Split projections by use case/source if a single document becomes too hard to synchronize.

## 17. Deletions and Tombstones

Delete events must be treated as data changes, not ignored cases. If the projector does not recognize deletes, stale documents remain in Elasticsearch and keep appearing in search results.

Example event:

```json
{
  "eventId": "evt-9010",
  "aggregateId": "p-100",
  "aggregateVersion": 13,
  "eventType": "ProductDeleted",
  "occurredAt": "2026-11-13T11:00:00Z"
}
```

The projector can delete the document:

```java
operations.delete(
    event.productId(),
    ProductSearchDocument.class,
    IndexCoordinates.of("products-read")
);
```

If stale events might arrive after a delete, physical deletion can remove the version marker needed to prevent old events from recreating the document. In that case, you can use a tombstone:

```json
{
  "id": "p-100",
  "sourceVersion": 13,
  "deleted": true,
  "deletedAt": "2026-11-13T11:00:00Z"
}
```

Search queries filter `deleted=false`; the tombstone is kept long enough so old events cannot resurrect the document. After the retention period, and once you are certain no old events or replays remain, tombstones can be cleaned up.

## 18. Initial Backfill and Syncing Changes During Scanning

When creating a new index, you need to load all existing data (backfill) and continue applying new changes. A common mistake is scanning a snapshot first and only then starting to consume events; changes occurring between the two steps can be lost.

A safer sequence:

```text
1. Determine watermark/offset to start capturing changes
             |
             v
2. Start retaining events/CDC from that watermark
             |
             v
3. Scan the source-of-truth snapshot
             |
             v
4. Write projections in batches
             |
             v
5. Replay events after the watermark
             |
             v
6. Apply version/ordering so old events do not overwrite new ones
             |
             v
7. Monitor lag and transition to continuous processing
```

Snapshot/offset details depend on the database, CDC tool, or broker. The goal is to leave no gap between the snapshot data and the change stream.

### Do Not Rely Solely on `updatedAt` If Zero Missed Records Are Required

Timestamps can collide, have low precision, or suffer from clock skew across systems. Use stable cursors, overlap windows, event IDs, or database log positions supported by the source. The projector must be idempotent to reprocess overlap regions safely.

## 19. Reconciliation: Detecting Projection Drift

Even with outbox/CDC, projections can still drift due to bugs, mapping errors, poison events, manual edits, or prolonged outages. Reconciliation is the process of comparing and repairing projections against the source of truth.

Several approaches:

- Compare record counts by tenant/status/partition.
- Compare source versions between source and projection.
- Fetch the list of IDs changed within a time window and rebuild them.
- Scan partitions and upsert projections.
- Check for missing documents or invalid tombstones.
- Periodically rebuild the entire index when scale permits.

You do not necessarily need to compare full JSON if documents contain derived or analyzer-specific fields. You can compare source versions, hashes of projection fields, or key business invariants.

### Rebuilding an Index Should Not Disrupt the Serving Index

A common strategy is to create a new index version, load the backfill, apply incoming events, verify, and then switch the read alias to the new index. Keep the old index intact during the rollback window in case it is needed.

## 20. Versioned Indexes and Aliases for Projections

Do not couple applications directly to physical index names if you need to rebuild or change mappings. Using aliases lets you switch the read target without changing application APIs.

For example:

```text
products-v1  <--- products-read

Rebuild:
products-v2  <--- load data and sync events

After verification:
products-read -> products-v2
```

Aliases can be switched via an atomic `_aliases` request:

```http
POST /_aliases
Content-Type: application/json

{
  "actions": [
    { "remove": { "index": "products-v1", "alias": "products-read" } },
    { "add": { "index": "products-v2", "alias": "products-read" } }
  ]
}
```

If a separate write alias is needed, you can use `products-write` pointing to the current write index. Distinguish between read aliases, write aliases, and write indexes in rollover or multi-index setups.

## 21. Schema Evolution of Search Projections

Search documents can change as new search requirements emerge:

- Adding filter or sort fields.
- Changing analyzers or normalizers.
- Adding autocomplete fields.
- Replacing standard objects with `nested` fields.
- Changing field types or field names.
- Adding denormalized data from a new service.

Not every mapping change can be applied directly to existing fields. Changing an analyzer or field type usually requires creating a new index and reindexing. Therefore, search projections should have an explicit version/schema version.

For example, documents can store `projectionVersion` to assist verification:

```json
{
  "id": "p-100",
  "projectionVersion": 3,
  "sourceVersion": 42,
  "name": "Wireless Mouse"
}
```

`projectionVersion` indicates the projection structure/logic; `sourceVersion` indicates which source state has been applied. The two values answer two different questions.

## 22. Choosing Which Data to Exclude from Projections

Not every database field should be indexed into Elasticsearch.

Consider excluding:

- Secrets, password hashes, or authentication tokens.
- Fields not used for searching, filtering, sorting, aggregating, or display.
- Large blobs or content only loaded when viewing details.
- Personal data unnecessary for the search use case.
- High-frequency update fields that add little value to the search projection.
- Data governed by dynamic permissions if adequate protection mechanisms are not in place.

Smaller projections usually reduce index size, network payloads, and update costs. Source filtering can also limit returned data, but it does not replace deciding which fields actually need to be indexed.

## 23. Access Control and Multi-Tenancy

If a search projection holds data for multiple tenants, the tenant ID must be indexed and enforced as a filter in every relevant query. Do not rely on the UI to hide results from other tenants.

Example document:

```json
{
  "id": "p-100",
  "tenantId": "tenant-42",
  "name": "Wireless Mouse"
}
```

Query:

```json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "tenantId": "tenant-42" } },
        { "match": { "name": "wireless" } }
      ]
    }
  }
}
```

The tenant ID should come from the server-side authenticated security context rather than trusting a tenant value sent directly by the client. Even if using tenant-based routing, keep the tenant filter in the query to enforce data scope and support access control.

## 24. Monitoring Synchronization Health

A projection system needs its own metrics, not just Elasticsearch cluster health.

Useful metrics:

- Counts of events received, succeeded, retried, and dead-lettered.
- Consumer lag or event delay.
- Time from source commit to projection update.
- Number of upserted/deleted documents.
- Number of events skipped due to stale versions.
- Number of mapping/serialization errors.
- Bulk item failures and retry counts.
- Document count by `projectionVersion`.
- Document count by source version or partition.
- Reconciliation mismatch count.
- Backfill progress and completion time.

Logs should include event ID, aggregate ID, source version, projection index/version, and correlation ID. Avoid logging full sensitive payloads.

### Projection Lag

Measure the gap between source commit time and when the document is written/refreshed for search. You can distinguish:

- Event delivery lag: the event has not yet reached the projector.
- Processing lag: the projector received the event but has not finished processing it.
- Elasticsearch write latency: slow write requests or retries.
- Search visibility lag: the document has been written but not yet refreshed.

Separating lag types helps pinpoint bottlenecks in the broker, projector, Elasticsearch, or refresh policy.

## 25. Testing Projections

Testing should not only assert that `repository.save()` throws no exceptions. Verify projection contents and behavior during abnormal sync conditions.

Cases to cover:

1. Product events create the right document and stable ID.
2. Brand/Category/Price are properly denormalized into the projection.
3. Duplicate events do not create duplicates or corrupt data.
4. Stale event versions do not overwrite newer versions.
5. Update and delete events are applied properly.
6. Failed events are retried and moved to dead-letter when exceeding policy.
7. Backfill does not miss changes occurring during scanning.
8. Reconciliation fixes missing/drifted documents.
9. Mappings and analyzers satisfy query patterns.
10. Tenant filters do not leak cross-tenant data.
11. Rebuilding a new index can switch the alias after synchronization.

For Elasticsearch integration tests, verify search visibility using an appropriate refresh policy or refresh the index after loading fixtures. Do not use fixed sleeps to wait for documents to appear.

## 26. Common Design Pitfalls

### Treating Elasticsearch as the Source of Truth for Transactions

Search projections can lag and can be rebuilt. For decisions requiring the latest state, read or confirm from the authoritative business source.

### Writing Database and Elasticsearch as One Transaction

The two systems do not share an ACID transaction. Dual writes can diverge when one side fails. Use outbox/CDC or explicit reconciliation.

### Using Domain Entities Directly for Every Index

Domain models and search documents have different goals. Separate projections when denormalization, custom mappings, or distinct schemas are needed.

### Lacking Owners for Denormalized Fields

Multiple events can overwrite each other's fields. Define source owners and how projections are updated.

### Not Handling Duplicate or Out-of-Order Events

At-least-once delivery and parallel workers can cause duplicate/out-of-order updates. Use stable IDs, versions, and idempotency.

### Physical Deletes Without Retaining Version Markers

Old events can recreate deleted documents. Consider tombstones or versioned delete mechanisms.

### Running Backfill Before Enabling the Event Consumer

Changes occurring between the two steps can be lost. Lock in a watermark/offset and replay events after the snapshot.

### Having No Reconciliation

Rare bugs or manual interventions can cause long-term projection drift. Run reconciliation jobs by version/hash/partition.

### Rebuilding an Index Directly on the Serving Index

Changing mappings or deleting indexes can cause downtime. Use versioned indexes and alias switches.

## 27. Source and Projection Design Workflow

When starting a search use case, you can follow this sequence:

1. List the queries, filters, sorts, aggregations, and display fields of the search API.
2. Identify the source of truth for each field and the owner responsible for updates.
3. Choose a separate projection reflecting query patterns rather than mechanically copying the database schema.
4. Decide which fields to denormalize, which to make nested, and which to exclude from the index.
5. Choose the synchronization mechanism: outbox, CDC, polling, or batch based on reliability and latency requirements.
6. Design event IDs, aggregate IDs, source versions, and idempotency.
7. Handle event ordering, concurrent projectors, and deletions/tombstones.
8. Design backfill with watermarks/offsets so new changes are not missed.
9. Use dedicated mappers/projectors and write with stable IDs via Spring Data Elasticsearch.
10. Set up retries, dead-letter handling, reconciliation, and metrics.
11. Use versioned indexes and aliases for mapping changes/rebuilds.
12. Test consistency, replay, tenant isolation, and search visibility.

## 28. Conclusion

The source of truth holds authoritative business state; the search projection is a read model optimized for queries that can be rebuilt. Choosing the source of truth per field, defining owners for denormalized data, and designing projections around query patterns prevent Elasticsearch from becoming a hard-to-sync database mirror.

In Spring Data Elasticsearch, use a separate search document when the search structure differs from the domain model, create mappers/projectors to transform data from authoritative sources, and write projections using stable IDs. Synchronization can use outbox, CDC, polling, or batch; regardless of the mechanism, handle duplicate/out-of-order events, versioning, deletions, backfill, and reconciliation. When mappings change, build a new index version and switch the alias after verification. Elasticsearch serves fast reads; critical transactional decisions must still rely on the authoritative business source.

## References

- [Spring Data Elasticsearch – Object mapping](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)
- [Spring Data Elasticsearch – ElasticsearchOperations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch – Repositories](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories.html)
- [Elasticsearch – Index aliases](https://www.elastic.co/docs/manage-data/data-store/aliases)
- [Elasticsearch – Reindex API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-reindex)
- [Debezium – Outbox Event Router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html)
- [Debezium – Change data capture concepts](https://debezium.io/documentation/reference/stable/)
