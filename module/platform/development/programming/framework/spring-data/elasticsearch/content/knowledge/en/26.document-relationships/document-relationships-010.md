# Updating Duplicated Data and Managing Consistency Across Documents

In Elasticsearch, a piece of business information can be copied into multiple documents to enable fast queries without joins like in a relational database. For instance, a product name might appear in product documents, orders, order lines, and transaction histories; a store name might appear across many listings; a category name might be stored with each product. This organization is called denormalization.

Denormalization speeds up reads and simplifies search queries, but introduces a challenge: when source data changes, copies in other documents may also need to change. Elasticsearch does not provide ACID transactions spanning multiple documents. Even a Bulk request is not a transaction; each item succeeds or fails independently. Therefore, the application must design a canonical data source, propagation flows, duplicate/out-of-order event handling, retries, error detection, and data reconciliation.

This lesson explains how to choose a data model, update multiple documents with Spring Data Elasticsearch, manage concurrency, and build consistency pipelines that can recover when part of the work fails.

## 1. Why is data duplicated across documents?

Suppose a sales system stores a product and placed orders:

~~~json
{
  "_id": "product-100",
  "name": "Wireless Keyboard",
  "brandName": "KeyWorks",
  "categoryName": "Accessories"
}
~~~

An order document can store the details needed to display purchase history:

~~~json
{
  "_id": "order-900",
  "customerId": "customer-20",
  "items": [
    {
      "productId": "product-100",
      "productName": "Wireless Keyboard",
      "brandName": "KeyWorks",
      "quantity": 2,
      "unitPrice": 1299000
    }
  ]
}
~~~

The order document keeps copies of `productName` and `brandName`. When searching orders, the application can display product names directly without looking up the product document for each order line.

Another example is a search catalog:

~~~json
{
  "_id": "listing-501",
  "title": "Wireless Keyboard",
  "sellerId": "seller-7",
  "sellerName": "North Star Store",
  "sellerRating": 4.8,
  "categoryName": "Accessories"
}
~~~

`sellerName` and `sellerRating` can be copied into many listings for fast filtering, sorting, and result display.

Common reasons to duplicate data:

- Reduce related-document lookups per request.
- Avoid joins when querying Elasticsearch.
- Optimize for a specific screen or search pattern.
- Store historical snapshots, such as name and price at order time.
- Build a projection/read model tailored to a use case.

Not every copy needs to be synchronized after every change. A product name on a completed order is usually a historical snapshot; if the product is renamed later, past invoices may still need to show the name at purchase time. Conversely, `sellerName` on active listings usually needs updating so current information is shown.

## 2. Identifying the canonical source and the meaning of each copy

Before writing update code, classify every duplicated field:

| Duplicated data type | Example | When source data changes |
|---|---|---|
| Historical snapshot | Product name and unit price in a confirmed order | Usually kept as-is from transaction time |
| Current projection | Seller name in active listings | Must propagate changes |
| Cache/search projection | Category name copied into products | Can be rebuilt from canonical source |
| Aggregate counter | Active product count for a store | Must be updated by events or recalculated |
| Derived data | Search keywords, slug, normalized name | Can be regenerated from source fields |

Each field needs a clear rule: who owns the value, when copies are updated, which copies are snapshots, and which systems are allowed to write.

### 2.1. Choosing a canonical data source

In many systems, the operational database is the source of truth; Elasticsearch is a read model serving search and filtering. For example:

~~~text
Operational database
       |
       | product/seller changes
       v
Outbox event or CDC
       |
       v
Consumer updates projections
       |
       +------> product index
       |
       +------> listing index
       |
       +------> recommendation index
~~~

In this setup, Elasticsearch is not the sole repository of canonical data. If a projection becomes corrupted, the system can replay events or rebuild the index from the source of truth.

If Elasticsearch itself is the application's primary store, you still must identify which document owns each field and how copies are synced. Avoid letting multiple independent services write the same field without clear ownership rules.

### 2.2. Do not blindly sync historical snapshots

For example, an order stores `unitPrice` at purchase time. If catalog prices change, do not update `unitPrice` on past orders. Similarly, product names on invoices or delivery notes can be legal/business snapshots.

Conversely, if a listing must display the seller's current name, that is a projection that must be updated when `sellerName` changes.

Distinguishing these two cases prevents a serious bug: syncing every field with the same name and inadvertently altering transaction history.

## 3. Ways to model relationships in Elasticsearch

Not every relationship needs multiple separate documents. Choose the structure based on read patterns, update patterns, and data size.

| Model | Characteristics | Updates and consistency |
|---|---|---|
| Embedded standard object | Child data sits inside `_source`, without `nested` | Rewrites parent document; no independent document for child objects |
| Nested | Child objects indexed as hidden Lucene documents attached to parent | Updating a nested object still updates the parent document |
| Parent-child join | Parent and child are separate documents in same index, same shard | Updates each document independently; join queries are costly and not transactional |
| Denormalized documents | Copy queryable fields across documents/indexes | Must fan-out updates or accept eventual consistency |

### 3.1. Embedding objects or using nested

If child data is always read with the parent document and has a reasonable size, embedding objects can be simpler:

~~~json
{
  "orderId": "order-900",
  "items": [
    {
      "productId": "product-100",
      "productName": "Wireless Keyboard",
      "quantity": 2
    }
  ]
}
~~~

With `nested` mapping, Elasticsearch preserves per-object semantics when querying conditions on the same element. Yet nested objects still belong to the parent document. Updating a nested item means rewriting the parent document under Elasticsearch's storage model.

Choose `nested` when:

- The child list is moderately sized.
- Queries frequently search or filter child object fields together.
- You must ensure attributes within the same child object match on the same element.
- Rewriting the parent document on nested item updates is acceptable.

### 3.2. Parent-child join

Parent-child lets parent and child documents exist separately in the same index, using a `join` field to represent the relationship. Parent and child must live on the same shard, so proper routing is required.

This model can be useful when:

- One parent has very many children.
- Children change frequently while the parent changes rarely.
- You need to update children independently without rewriting the entire parent.

In return, join queries are more complex and resource-heavy than queries on denormalized fields. Parent-child also does not provide transactions to update parent and child atomically. If the primary goal is fast reads and copy updates are acceptable, denormalization is usually easier to operate.

### 3.3. Splitting into separate documents and copying fields

For example, a `seller` document and multiple `listing` documents:

~~~json
{
  "_id": "seller-7",
  "name": "North Star Store",
  "rating": 4.8
}
~~~

~~~json
{
  "_id": "listing-501",
  "sellerId": "seller-7",
  "sellerName": "North Star Store",
  "sellerRating": 4.8,
  "title": "Wireless Keyboard"
}
~~~

When the seller renames, active listings must be updated if `sellerName` is a current projection. This is the core problem of updating duplicated data across documents.

## 4. Elasticsearch has no multi-document transactions

An index/update/delete operation acts on a single document. The Bulk API lets you send multiple actions in one request, yet each action is processed independently:

- One item can succeed while another item fails.
- A bulk response can have a successful HTTP status while its `errors` field is `true`.
- Elasticsearch does not roll back succeeded items just because another item failed.
- There is no ACID commit/rollback spanning documents in a bulk request.

Example bulk request:

~~~http
POST _bulk
{"update":{"_index":"listings","_id":"listing-501"}}
{"doc":{"sellerName":"North Star Retail"}}
{"update":{"_index":"listings","_id":"listing-502"}}
{"doc":{"sellerName":"North Star Retail"}}
{"update":{"_index":"listings","_id":"listing-503"}}
{"doc":{"sellerName":"North Star Retail"}}
~~~

If the action for `listing-502` fails, `listing-501` and `listing-503` can still be updated. The application must inspect every item and have a retry/reconciliation strategy.

### 4.1. Distinguishing atomicity, visibility, and durability

Three commonly confused concepts:

- **Atomicity:** whether a group of changes all succeed or all fail together. Bulk does not provide multi-document atomicity.
- **Visibility:** whether new documents appear in search results immediately. Elasticsearch is near-real-time; refresh controls when changes become visible to search.
- **Durability:** whether changes are durably persisted according to cluster mechanisms. This is separate from refresh.

Setting the refresh policy to `IMMEDIATE` does not turn multiple updates into a transaction. It only affects when changes become searchable.

### 4.2. Eventual consistency

For denormalized projections, many systems choose eventual consistency: after source data changes, copies are updated asynchronously and converge to the same state once events are processed successfully.

During propagation lag, a query may observe new data in the source document alongside old data in some projections. The application must decide what lag is acceptable and have a way to detect when a projection fails to converge.

If business logic demands immediate read consistency, read the canonical field from the operational source or design an appropriately confirmed synchronous flow. You cannot assume a bulk update mutates an entire index atomically.

## 5. Choosing Spring Data Elasticsearch APIs for updating duplicated data

Spring Data Elasticsearch offers multiple abstractions for updating documents:

| API | Purpose | When to use |
|---|---|---|
| Repository `save` / `operations.save` | Index the full entity | You have the complete document state |
| `operations.update(UpdateQuery, index)` | Partial update of one document | You know the ID and change only a few fields |
| `operations.bulkUpdate(...)` | Multiple partial updates in one bulk request | You have a list of IDs to update |
| `operations.updateByQuery(...)` | Update documents matching a query | Many documents receive the same change |
| `operations.deleteByQuery(...)` | Delete documents matching a query | Delete projections by relation or condition |
| `operations.bulkIndex(...)` | Bulk index full documents | Create or replace many documents |

Do not use `save(entity)` just to change one field if the entity lacks other fields. An index operation can replace the document's `_source`. Partial updates are safer when you only want to change `sellerName` or `categoryName` while keeping all other fields intact.

## 6. Updating a single document with UpdateQuery

Suppose a seller renames and listing `listing-501` must be updated:

~~~java
import java.util.Map;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.document.Document;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.UpdateQuery;
import org.springframework.data.elasticsearch.core.query.UpdateResponse;

public class ListingProjectionWriter {

    private final ElasticsearchOperations operations;

    public ListingProjectionWriter(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public UpdateResponse updateSellerName(String listingId, String sellerName) {
        UpdateQuery update = UpdateQuery.builder(listingId)
                .withDocument(Document.from(Map.of(
                        "sellerName", sellerName)))
                .build();

        return operations.update(
                update,
                IndexCoordinates.of("listings"));
    }
}
~~~

The document contains only the `sellerName` field, so Elasticsearch applies a partial update to that document. Fields `title`, `sellerId`, and `sellerRating` remain untouched.

If a value can be `null`, explicitly decide what that means:

- Omit the field from the partial document: leave the existing field unchanged.
- Send `null`: may set the field to `null` in `_source` per Update API semantics.
- Remove the field: use a script removing the field from `ctx._source` or an appropriate API.

Do not use `Map.of` if values can be `null`, as `Map.of` rejects `null`. In that case, build a map that allows `null` or model field removal separately.

### 6.1. When to use save?

If the service holds the full new listing state and wants to replace the document:

~~~java
Listing listing = loadCompleteListing(listingId);
listing.setSellerName(newSellerName);

operations.save(listing);
~~~

Only do this when `listing` represents complete state and the application owns the entire `_source`. If the document contains fields managed by other pipelines or services, saving an entity missing those fields will wipe out that data.

### 6.2. Upsert does not replace consistency rules

`UpdateQuery` can configure upsert to create the document if it does not exist yet:

~~~java
UpdateQuery update = UpdateQuery.builder("listing-501")
        .withDocument(Document.from(Map.of(
                "sellerName", "North Star Retail")))
        .withDocAsUpsert(true)
        .build();
~~~

Upsert only defines behavior when the document is absent. It does not guarantee that other fields on the newly created document are complete. Only use it when the partial document forms a valid document per mapping and business rules; otherwise, index a complete projection.

## 7. Updating multiple known IDs with bulkUpdate

If the consumer knows the list of listings belonging to `seller-7`, it can build multiple `UpdateQuery` instances and send them in bulk:

~~~java
import java.util.List;
import java.util.Map;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.document.Document;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.BulkOptions;
import org.springframework.data.elasticsearch.core.query.UpdateQuery;

public void updateListings(
        ElasticsearchOperations operations,
        List<String> listingIds,
        String sellerName) {

    List<UpdateQuery> updates = listingIds.stream()
            .map(id -> UpdateQuery.builder(id)
                    .withDocument(Document.from(Map.of(
                            "sellerName", sellerName)))
                    .build())
            .toList();

    operations.bulkUpdate(
            updates,
            BulkOptions.defaultOptions(),
            IndexCoordinates.of("listings"));
}
~~~

Bulk reduces network round trips compared to updating each document individually. Still, you must handle per-item errors and chunk into suitable batches. Do not build a list of millions of `UpdateQuery` objects in memory and send a single giant request.

### 7.1. Batching

Example processing an ID list in batches:

~~~java
int batchSize = 500;

for (int start = 0; start < listingIds.size(); start += batchSize) {
    int end = Math.min(start + batchSize, listingIds.size());
    List<String> batch = listingIds.subList(start, end);

    updateListings(operations, batch, newSellerName);
}
~~~

Batch size should be tuned through benchmarking, not chosen as a fixed magic number for every system. Document size, number of updated fields, cluster load, network, and concurrency all affect performance.

### 7.2. Bulk failure is partial failure

Spring Data provides `BulkFailureException` to report failed documents in a bulk operation. In versions exposing `FailureDetails`, you can read the ID, status, and error message:

~~~java
import org.springframework.data.elasticsearch.BulkFailureException;

try {
    operations.bulkUpdate(
            updates,
            BulkOptions.defaultOptions(),
            IndexCoordinates.of("listings"));
} catch (BulkFailureException exception) {
    exception.getFailedDocuments().forEach((id, failure) -> {
        log.warn(
                "Failed to update listing {}: status={}, message={}",
                id,
                failure.status(),
                failure.errorMessage());
    });

    throw exception;
}
~~~

The signature and value type of `getFailedDocuments()` vary across release trains. The example above matches current APIs with `FailureDetails`; check the Javadoc for the exact Spring Data Elasticsearch version your project uses.

Do not merely log and ignore failures. Persist failed items for retry or route them to a dead-letter queue (DLQ). If the consumer marks an event as processed despite partial item failures, copies can drift permanently.

## 8. Conditional updates with Update By Query

If all documents with `sellerId = seller-7` need the exact same `sellerName` change, you do not necessarily have to fetch all IDs back to the application. Elasticsearch Update By Query can locate and update them directly inside the cluster.

REST API:

~~~http
POST listings/_update_by_query
{
  "query": {
    "term": {
      "sellerId": "seller-7"
    }
  },
  "script": {
    "lang": "painless",
    "source": "ctx._source.sellerName = params.name",
    "params": {
      "name": "North Star Retail"
    }
  }
}
~~~

Spring Data Elasticsearch can express this using `UpdateQuery` builder with a query and script:

~~~java
import java.util.Map;

import org.springframework.data.elasticsearch.core.query.ByQueryResponse;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.UpdateQuery;

CriteriaQuery selection = new CriteriaQuery(
        Criteria.where("sellerId").is("seller-7"));

UpdateQuery updateByQuery = UpdateQuery.builder(selection)
        .withScript("ctx._source.sellerName = params.name")
        .withParams(Map.of("name", "North Star Retail"))
        .withBatchSize(500)
        .withAbortOnVersionConflict(false)
        .build();

ByQueryResponse response = operations.updateByQuery(
        updateByQuery,
        IndexCoordinates.of("listings"));
~~~

Update By Query fits when:

- The target document set can be identified via a query.
- Every document receives the same change or the same script.
- The application does not need to read each document individually before sending updates.

Avoid Update By Query when each document requires a distinct value that a script cannot compute from `_source` or `params`. In that case, `bulkUpdate` with IDs and partial documents is usually a better fit.

### 8.1. Handling version conflicts

While Update By Query is running, another writer may modify a document. Elasticsearch detects a version conflict. You can choose to abort or proceed:

- Abort: stop on conflict; fits when all documents must be updated in one controlled pass.
- Proceed: continue updating other documents and record conflict counts; conflicted documents must still be handled separately.

`withAbortOnVersionConflict(false)` corresponds to proceeding in the current Spring Data API. It does not resolve conflicts and does not guarantee every matching document was updated.

### 8.2. Asynchronous Update By Query

For large document sets, the Elasticsearch REST API supports `wait_for_completion=false` to return a task ID:

~~~http
POST listings/_update_by_query?wait_for_completion=false&requests_per_second=500
{
  "query": {
    "term": {
      "sellerId": "seller-7"
    }
  },
  "script": {
    "source": "ctx._source.sellerName = params.name",
    "params": {
      "name": "North Star Retail"
    }
  }
}
~~~

Tracking the task:

~~~http
GET _tasks/TASK_ID
~~~

You can cancel the task:

~~~http
POST _tasks/TASK_ID/_cancel
~~~

Canceling a task does not roll back documents already updated prior to cancellation. Record progress and design subsequent runs to resume safely.

## 9. Why are events needed to propagate changes?

Suppose a seller renames from `North Star Store` to `North Star Retail`. The system must find every listing with the matching `sellerId` and update `sellerName`.

A simple sync flow:

1. Service updates the seller in the operational database.
2. Service emits a `SellerRenamed` event.
3. Consumer receives the event.
4. Consumer finds listings depending on `sellerId`.
5. Consumer updates listings in batches.
6. Consumer acknowledges the event once all required batches succeed.

An event can contain:

~~~json
{
  "eventId": "evt-2026-000091",
  "eventType": "SellerRenamed",
  "aggregateType": "Seller",
  "aggregateId": "seller-7",
  "aggregateVersion": 18,
  "occurredAt": "2026-11-13T10:30:00Z",
  "payload": {
    "sellerName": "North Star Retail"
  }
}
~~~

Field meanings:

- `eventId`: unique identifier for duplicate detection.
- `aggregateId`: which seller changed.
- `aggregateVersion`: monotonically increasing version of the seller.
- `occurredAt`: when the event occurred, useful for logging and investigation.
- `payload`: data required to update projections.

Do not rely solely on `occurredAt` to determine order because clocks across machines can skew. A monotonically increasing version per aggregate is generally much better for rejecting stale events.

## 10. Transactional Outbox to avoid losing events

A classic failure is updating the database successfully and then failing to publish the message:

~~~text
UPDATE seller in database: succeeded
Publish SellerRenamed: failed
=> Database changed, but Elasticsearch did not receive the event
~~~

The reverse failure can also occur: a message is published, but the database transaction rolls back. Consumers then receive an event describing a change that was never committed.

Transactional Outbox closes this gap by writing business data and the event within the same database transaction:

~~~text
BEGIN TRANSACTION
    UPDATE sellers SET name = ...
    INSERT INTO outbox(event_id, aggregate_id, version, payload, ...)
COMMIT
          |
          v
Outbox relay reads unsent events
          |
          v
Publish message
          |
          v
Consumer updates Elasticsearch
~~~

If the transaction commits, both the seller change and the outbox record exist together. The relay can retry publishing until it succeeds. Consumers still need idempotency because message brokers typically provide at-least-once delivery or can replay messages.

Outbox does not create a distributed transaction between the database and Elasticsearch. It guarantees that events for committed changes are durably persisted alongside the source transaction, and projections are updated asynchronously afterward.

### 10.1. Minimal outbox schema

An outbox table might include:

| Column | Meaning |
|---|---|
| `event_id` | Unique key of the event |
| `aggregate_type` | Aggregate type, e.g., `Seller` |
| `aggregate_id` | ID of the aggregate |
| `aggregate_version` | Version at the time of change |
| `event_type` | Event name |
| `payload` | Event payload |
| `created_at` | Creation timestamp |
| `published_at` | Timestamp when the relay successfully published |

The relay should mark publish state in a retry-safe way. If the relay crashes after publishing but before marking `published_at`, the event may be sent again; therefore consumers must tolerate duplicates.

## 11. Idempotency: handling duplicate events safely

Messages can be redelivered due to timeouts, retries, or consumer crashes. An idempotent consumer can process the same event multiple times without corrupting final state.

With a `SellerRenamed` event carrying final state:

~~~json
{
  "sellerId": "seller-7",
  "sellerName": "North Star Retail",
  "version": 18
}
~~~

Setting `sellerName` to `"North Star Retail"` is idempotent: running it multiple times yields the exact same value.

In contrast, an incrementing script:

~~~text
ctx._source.orderCount += params.delta
~~~

is not idempotent if the same event executes twice. The counter would be incremented twice.

### 11.1. Using event IDs to detect duplicates

A consumer can store processed `eventId`s in an inbox or deduplication table. However, writing to the inbox table and updating Elasticsearch are still not in the same transaction. If you mark the event processed before updating Elasticsearch, a crash can lose the update. If you mark it after updating, a crash in between causes re-execution.

Therefore, consumer deduplication must be paired with idempotent projection operations and retries. Never assume a simple `processed_events` table turns broker + Elasticsearch into a single transaction.

### 11.2. Prefer final-state events over deltas whenever possible

Delta-style event:

~~~json
{
  "sellerId": "seller-7",
  "ratingDelta": 0.1
}
~~~

Final-state event:

~~~json
{
  "sellerId": "seller-7",
  "rating": 4.8,
  "version": 18
}
~~~

Final-state events are much easier to retry because consumers assign precomputed values rather than adding/subtracting repeatedly. For counters or data requiring deltas, you must pair them with event IDs, versions, or exact deduplication mechanisms.

## 12. Handling out-of-order events

Suppose a seller renames twice in succession:

~~~text
Version 18: North Star Retail
Version 19: North Star Marketplace
~~~

Due to retries or partitioning, the consumer might receive version 19 first and version 18 afterward. Applying both in arrival order would regress the final value back to `North Star Retail`.

The solution is storing `aggregateVersion` inside the projection and accepting only events newer than the current version.

### 12.1. Storing the version inside projection documents

~~~json
{
  "_id": "listing-501",
  "sellerId": "seller-7",
  "sellerName": "North Star Marketplace",
  "sellerVersion": 19
}
~~~

The consumer must ensure older versions cannot overwrite newer versions. This can be achieved with optimistic concurrency, conditional scripts, or external versioning.

### 12.2. External versioning

Elasticsearch's Index API supports `version` and `version_type=external`. For example:

~~~http
PUT listings/_doc/listing-501?version=19&version_type=external
{
  "sellerId": "seller-7",
  "sellerName": "North Star Marketplace",
  "sellerVersion": 19
}
~~~

Elasticsearch accepts the write only when the incoming version is strictly greater than the current version. A late-arriving version 18 event is rejected with a version conflict.

`external_gte` accepts versions greater than or equal to the current version. This can help when replaying the same snapshot version, provided a single version always maps to the exact same payload. Two different payloads sharing the same version could cause non-deterministic overwrites.

External versioning applies to index operations per Elasticsearch's contract. For partial updates, use suitable controls like `if_seq_no`/`if_primary_term` or scripts checking `_source` version; do not assume external version parameters work identically on every endpoint.

### 12.3. Checking version with a Painless script

With the Update API, you can compare the event version with the version stored in the document:

~~~java
UpdateQuery update = UpdateQuery.builder("listing-501")
        .withScript("""
            if (ctx._source.sellerVersion == null ||
                params.version > ctx._source.sellerVersion) {
                ctx._source.sellerName = params.name;
                ctx._source.sellerVersion = params.version;
            } else {
                ctx.op = 'noop';
            }
            """)
        .withParams(Map.of(
                "name", "North Star Marketplace",
                "version", 19))
        .build();
~~~

The script applies the event only if its version is newer. If the version is equal or lower, the operation becomes a `noop`. Adjust numeric types in `params` and `_source` to match your actual schema.

If multiple consumers concurrently update the same document, you must still handle version conflicts and retries. Version-checking scripts prevent old events from overwriting newer ones, but do not turn multi-document updates into a transaction.

## 13. Optimistic concurrency for concurrent updates

Elasticsearch provides sequence numbers and primary terms to control concurrent writes. When reading a document, the response includes `_seq_no` and `_primary_term`. You can require an update to succeed only if the document is still at the exact version you read.

REST example:

~~~http
POST listings/_update/listing-501?if_seq_no=42&if_primary_term=3
{
  "doc": {
    "sellerName": "North Star Retail"
  }
}
~~~

If another writer modified the document in the meantime, Elasticsearch returns a version conflict. The application should re-read the latest state, inspect the business version, and decide whether to re-apply or skip.

Spring Data Elasticsearch can express this condition on `UpdateQuery`:

~~~java
UpdateQuery update = UpdateQuery.builder("listing-501")
        .withDocument(Document.from(Map.of(
                "sellerName", "North Star Retail")))
        .withIfSeqNo(42L)
        .withIfPrimaryTerm(3L)
        .build();
~~~

### 13.1. Distinguishing `retry_on_conflict` from optimistic concurrency

- `if_seq_no` + `if_primary_term`: writes only if the document has not changed since that specific read. On conflict, the application decides whether to re-read and retry.
- `retry_on_conflict`: instructs Elasticsearch to retry the Update API internally on version conflicts by re-reading the latest version and re-running the update/script.

Retrying is only safe when the update operation is repeatable. Assigning `sellerName` to a final value can generally be retried; incrementing a counter or adding funds requires dedicated idempotency design.

## 14. Handling partial bulk failures

A batch can yield mixed outcomes:

| Error type | Handling approach |
|---|---|
| HTTP 429 / rejected execution | Retry with backoff and rate limiting |
| Timeout or network error | Outcome unknown; replay idempotent actions or inspect the document |
| Version conflict | Read current version, discard stale event or retry per policy |
| Mapping/parsing error | Send to DLQ, fix schema/data, then replay |
| Authentication/authorization | Fix permissions/credentials; avoid tight retry loops |
| Document missing on update | Check document lifecycle; use upsert only if business logic allows |

Never unconditionally retry an entire bulk batch. Some actions already succeeded; re-sending non-idempotent actions can apply changes a second time.

### 14.1. Retry with backoff

For transient failures, retry using exponential backoff with jitter:

~~~text
delay = min(maxDelay, baseDelay * 2^attempt) + randomJitter
~~~

Example:

| Attempt | Illustrative base delay |
|---:|---:|
| 1 | 200 ms |
| 2 | 400 ms |
| 3 | 800 ms |
| 4 | 1,600 ms |
| 5 | 3,200 ms |

These are example settings, not universal optimal values. Cap maximum retry attempts, bound total retry duration, and route items exceeding thresholds to a DLQ.

### 14.2. Dead-letter queue

A DLQ stores events or items that failed after retries. Each record should capture:

- Event ID and aggregate ID.
- Target document ID/index.
- Payload or reference to the original payload.
- Retry count and timestamp of the latest attempt.
- Error type, status, and message.
- Desired projection version.

A DLQ needs monitoring and a replay workflow. Simply writing errors to log files makes recovering millions of failed items after an outage extremely difficult.

## 15. Handling relationship changes and deletions

Synchronization is not limited to updating names or statuses. Relationships can be added, reassigned, or deleted.

### 15.1. When a listing transfers to another seller

If `listing-501` changes `sellerId` from `seller-7` to `seller-9`, update both `sellerId` and copied fields `sellerName`/`sellerRating` in the same listing document. Never update `sellerName` first and `sellerId` afterward in two separate requests if that could expose a hybrid state.

Since both fields live in the same document, use one partial update:

~~~java
UpdateQuery update = UpdateQuery.builder("listing-501")
        .withDocument(Document.from(Map.of(
                "sellerId", "seller-9",
                "sellerName", "East Point Store",
                "sellerRating", 4.6)))
        .build();

operations.update(update, IndexCoordinates.of("listings"));
~~~

A single update on the same document updates all fields in that document as one unit. However, if the listing is also copied into other indexes, updating those other indexes remains separate independent operations.

### 15.2. When a seller is deleted or deactivated

The system must decide whether to:

- Delete related listings.
- Mark listings inactive.
- Keep listings while removing seller details.
- Retain a `sellerName` snapshot for history.

Do not automatically delete every document referencing `sellerId` just because the seller was deleted at the source. Rules depend on business logic, history, and audit requirements.

### 15.3. Delete By Query

If policy requires deleting all listings of a seller:

~~~http
POST listings/_delete_by_query
{
  "query": {
    "term": {
      "sellerId": "seller-7"
    }
  }
}
~~~

Delete By Query also processes in batches and can encounter version conflicts. It is not a transactional operation across the entire document set. For critical operations, record expected counts, actual results, failures, and resume capability.

## 16. Syncing multiple indexes with projection writers

One event may need to update multiple projections:

~~~text
SellerRenamed(seller-7, version=18)
        |
        +----> sellers index
        |
        +----> listings index
        |
        +----> recommendations index
        |
        +----> analytics projection
~~~

Encapsulate update logic for each projection inside its own writer. Each writer can use `bulkUpdate` or `updateByQuery` depending on data structure and document count.

Example interface:

~~~java
public interface ProjectionUpdater<E> {
    void apply(E event);
}
~~~

Coordinating consumer:

~~~java
public class SellerRenamedHandler {

    private final SellerIndexUpdater sellerUpdater;
    private final ListingIndexUpdater listingUpdater;
    private final RecommendationIndexUpdater recommendationUpdater;

    public void handle(SellerRenamed event) {
        sellerUpdater.apply(event);
        listingUpdater.apply(event);
        recommendationUpdater.apply(event);
    }
}
~~~

This example demonstrates separation of responsibilities. In a real deployment, track progress per projection or use independent retries. If `listingUpdater` succeeds while `recommendationUpdater` fails, do not assume the entire handler succeeded or that the `listings` index can be rolled back.

### 16.1. Tracking progress per projection

You can persist event status per consumer/projection:

| Event | Projection | Status |
|---|---|---|
| evt-91 | sellers | DONE |
| evt-91 | listings | RETRY |
| evt-91 | recommendations | DONE |

On retry, re-run only the missing projections or re-run all of them idempotently. The choice depends on the cost and idempotency level of each updater.

## 17. CDC and rebuilding projections

Besides application-written outboxes, systems can use Change Data Capture (CDC) to read changes from the database transaction log and emit events. CDC reduces the need to add publishing logic across services, though you still must handle:

- Mapping database changes into business events or projection updates.
- Preserving ordering by key/aggregate where required.
- Saving offsets and supporting replay.
- Schema evolution.
- Guarding against duplicate and stale events.

If an Elasticsearch projection is corrupted or needs a schema change, a robust strategy is rebuilding from the canonical source:

1. Create a new index/projection with the desired mapping.
2. Read canonical data or a consistent snapshot.
3. Reindex data in batches.
4. Replay events emitted during the rebuild.
5. Verify counts and business invariants.
6. Switch the alias to the new projection.
7. Retain the old index for a rollback window.

Rebuilding is usually far more reliable than trying to manually patch every drifted document if the canonical source is complete.

## 18. Reconciling duplicated data

Event-driven updates can fail due to mapping errors, neglected DLQs, consumer bugs, or operational incidents. Critical systems should therefore run reconciliation jobs.

A reconciliation process might:

1. Fetch sellers whose version is newer than the projection.
2. Find listings with matching `sellerId`.
3. Compare `sellerVersion` and `sellerName`.
4. Record drifted documents.
5. Repair them with bulk updates or re-emitting final-state events.
6. Record metrics on checked, drifted, and repaired documents.

Example projection check:

~~~json
{
  "_id": "listing-501",
  "sellerId": "seller-7",
  "sellerName": "North Star Store",
  "sellerVersion": 17
}
~~~

while the canonical source is at version 18. This signals the projection has not converged.

### 18.1. Choosing invariants to reconcile

Do not compare document counts alone. You can also verify:

- Every active listing references an existing seller.
- `sellerVersion` in listings is not below the minimum expected version.
- `sellerName` in the projection equals the canonical name at that version.
- No documents still reference deleted sellers where policy forbids it.
- Aggregate counters match recomputation from source data.

For large datasets, use sampling, time partitioning, or aggregate-ID sharding to throttle load. Reconciliation jobs must not cause load spikes on clusters actively serving search traffic.

## 19. Refresh and read-after-write

After updating a document, the application may read directly by ID or search via a query. The two have different visibility behaviors:

- Get by ID can read written document state without waiting for search refresh in the same way.
- Search only sees changes after the shard refreshes.

Spring Data exposes `RefreshPolicy` with options such as `NONE`, `IMMEDIATE`, and `WAIT_UNTIL`. For bulk or large fan-out updates, avoid refreshing immediately after every document because frequent refreshes degrade indexing throughput.

If the UI needs confirmation that an update appears in search, use `WAIT_UNTIL` for suitable operations or explicitly refresh after a batch. Remember this only guarantees visibility of that operation after refresh; it does not ensure projections across other indexes are updated.

## 20. Designing event versions and projection documents

A projection document should store enough metadata to track sync status:

~~~json
{
  "_id": "listing-501",
  "sellerId": "seller-7",
  "sellerName": "North Star Marketplace",
  "sellerVersion": 19,
  "projectionUpdatedAt": "2026-11-13T10:31:00Z"
}
~~~

Where:

- `sellerVersion` rejects stale events.
- `projectionUpdatedAt` aids lag monitoring and debugging.
- `sellerId` allows reverse lookups of dependent documents.

Do not rely solely on timestamps to adjudicate ordering if monotonically increasing versions are available. Timestamps can collide or arrive out of order due to clock skew.

An event version should be incremented at the source of truth inside the aggregate's transaction. If multiple services can emit versions for the same aggregate, enforce a single version issuer or partition processing by aggregate.

## 21. Choosing between bulkUpdate and updateByQuery

Both APIs update multiple documents, yet their usage patterns differ:

| Criterion | `bulkUpdate` | `updateByQuery` |
|---|---|---|
| Document identification | Application supplies IDs for each update | Elasticsearch finds documents via query |
| Update values | Can differ per document | Usually the same script/params, or derived from `_source` |
| Payload | List of `UpdateQuery` | Query + script/partial document |
| Best suited for | Events with explicit ID lists and distinct data | All matching documents receiving the same change |
| Failures | Per-bulk-item errors | Version conflicts/failures per batch |
| Batch control | Application chunks the list | Elasticsearch processes via batches/scroll |

Examples:

- Changing `sellerName` across all listings of `seller-7`: `updateByQuery` fits well.
- Updating each listing with a different price from separate events: `bulkUpdate` fits well.
- Changing just one listing: `update`.

When a relationship spans millions of documents, `updateByQuery` avoids pulling huge ID lists into application memory. Still, monitor task progress, throttling, conflicts, and execution duration.

## 22. Common mistakes

### Using save to update a single field

An entity missing other fields can erase data when reindexing the full `_source`. Use partial updates when changing only a subset of fields.

### Treating bulk as a transaction

A bulk request can partially succeed. Inspect each item, persist failures, and retry selectively.

### Marking an event complete while projections have errors

If a consumer acks an event after partial item failures, data drifts without automatic retry. Only ack once required projections succeed or errors move to a tracked recovery flow.

### Retrying a non-idempotent script

Accumulating scripts can execute twice on timeouts or redeliveries. Use event IDs/versions or design final-state assignment updates.

### Stale events overwriting newer events

Relying solely on message arrival order is insufficient. Store aggregate versions and discard older events.

### Saving processed events only before updating Elasticsearch

If the consumer crashes after recording processed status and before updating the index, the projection update is lost. Combine deduplication with idempotent updates, retries, and reconciliation.

### Treating refresh as consistency sync

Refresh only makes written data visible to search. It does not sync other indexes or create transactions.

### Updating historical snapshots

Do not propagate catalog changes into orders/invoices if those fields must reflect state at transaction time.

### Deleting related documents without business rules

Deleting a seller does not always mean deleting all orders or listings. Define lifecycle, soft deletes, snapshots, and retention beforehand.

### Having no rebuild mechanism

If you only have incremental events and cannot re-read the canonical source, recovering a corrupted projection is very difficult. Design rebuild capability from day one.

## 23. Workflow for implementing duplicated data updates

When a canonical field changes and must propagate to other documents:

1. Identify the canonical source and the field's owner.
2. Classify copies as historical snapshots or current projections.
3. Identify all dependent indexes/documents and how to reverse-lookup by ID.
4. Design events containing `eventId`, `aggregateId`, `aggregateVersion`, and the target state.
5. Persist events via transactional outbox or CDC to prevent lost changes.
6. Choose `update`, `bulkUpdate`, or `updateByQuery` based on document volume and how values are determined.
7. Use partial updates to preserve unrelated fields.
8. Design idempotency and out-of-order event handling.
9. Handle version conflicts, bulk failures, backoff retries, and DLQs.
10. Track progress separately per projection/index.
11. Run reconciliation to catch missed or stale documents.
12. Support rebuilding projections from the canonical source.
13. Request refresh only when search visibility is required; never treat refresh as a transaction.
14. Test duplicates, out-of-order delivery, timeouts, partial failures, and consumer restarts.

## 24. Testing consistency scenarios

An integration test suite for a projection updater should cover:

| Scenario | Expected outcome |
|---|---|
| Event version 18 arrives first time | Projection moves to version 18 |
| Event version 18 is redelivered | No invalid changes or double counter increments |
| Version 19 arrives before version 18 | Projection stays at version 19 |
| Bulk batch has one mapping error item | Successful items are applied; failed item can be retried/DLQ'd |
| Consumer crashes after updating one batch | Replay does not corrupt state |
| Seller renames twice rapidly | Listing never reverts to the older name |
| Listing changes seller | `sellerId` and copied fields update together in one document update |
| Order snapshot | Historical price/name are not accidentally overwritten |
| Projection rebuild | Rebuilt data matches source of truth plus catch-up events |

### 24.1. Testing idempotent updates

For a final-state event, run the same event twice and verify the document does not change on the second run:

~~~java
@Test
void applyingSameSellerRenameTwiceKeepsSameProjection() {
    handler.handle(event);
    Listing first = operations.get(
            "listing-501",
            Listing.class,
            IndexCoordinates.of("listings"));

    handler.handle(event);
    Listing second = operations.get(
            "listing-501",
            Listing.class,
            IndexCoordinates.of("listings"));

    assertThat(second.getSellerName()).isEqualTo(first.getSellerName());
    assertThat(second.getSellerVersion()).isEqualTo(first.getSellerVersion());
}
~~~

This test requires configuring mappings, events, and documents matching your application. For delta events, also test event IDs/versions to prove replays never add/subtract twice.

## 25. Summary

Denormalization enables fast Elasticsearch queries by copying queryable fields across documents. When canonical data changes, current copies must be updated via fan-out updates, while historical snapshots must generally be preserved as of transaction time. Distinguish between `nested` objects, parent-child, and denormalized documents because update mechanics and query costs differ.

Spring Data Elasticsearch provides `update` for single documents, `bulkUpdate` for lists of known IDs, and `updateByQuery` for query-selected document sets. Bulk and update-by-query are not multi-document transactions; partial failures can occur. Systems should combine a source of truth, transactional outbox or CDC, event IDs/versions, idempotent operations, concurrency control, backoff retries, DLQs, and reconciliation.

A consistent design never assumes all copies change instantaneously together. It defines acceptable lag, tracks which projections are up to date, supports event replay, and can rebuild from the canonical source. That way, duplicated data delivers fast reads while keeping the system resilient to failed updates, duplicate events, and out-of-order delivery.

## References

- [Spring Data Elasticsearch – Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch – DocumentOperations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/DocumentOperations.html)
- [Spring Data Elasticsearch – UpdateQuery API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/query/UpdateQuery.html)
- [Elasticsearch – Update API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-update)
- [Elasticsearch – Bulk API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-bulk)
- [Elasticsearch – Update By Query API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-update-by-query)
- [Elasticsearch – Optimistic concurrency control](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/optimistic-concurrency-control)
- [Elasticsearch – Parent-join field](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/parent-join)
- [Martin Fowler – Transactional Outbox](https://microservices.io/patterns/data/transactional-outbox.html)
