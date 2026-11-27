# Handling Version Conflicts on Write and Update

When multiple requests or multiple services concurrently write to an Elasticsearch document, one writer may read stale data and overwrite a newer change from another writer. This is the lost update problem. Elasticsearch uses optimistic concurrency control to detect when a document has changed since the writer read it. When the version condition no longer holds, the write operation is rejected with a version conflict instead of silently overwriting newer data.

Spring Data Elasticsearch supports entity-level optimistic locking through the `@Version` annotation. For direct update requests, Elasticsearch provides the `if_seq_no` and `if_primary_term` pair. The Update API also offers `retry_on_conflict` to retry an update on conflict. If data comes from another source system with its own business version, external versioning can be used for appropriate index operations.

This lesson distinguishes the version types, explains how to detect and handle conflicts during index/update/delete, shows how to use `@Version` and `UpdateQuery` in Spring Data, demonstrates handling bulk errors, and covers testing concurrent write scenarios.

## 1. What is a version conflict?

Suppose a product has `stock = 10`. Two requests read the document in that state:

~~~text
Time          Writer A                  Writer B
----------------------------------------------------------
t1            Read stock = 10
t2                                      Read stock = 10
t3            Write stock = 8
t4                                      Write stock = 7
~~~

If Writer B writes a full document based on its stale read, it can overwrite the state Writer A just saved. A change that succeeded is lost from the final state.

Optimistic concurrency control (OCC) requires the writer to include the version information it read. Elasticsearch accepts the write only if the document is still at that version. If the document has changed, Elasticsearch returns a conflict so the application can reload and decide how to merge.

~~~text
Writer A reads document + concurrency token
                |
                v
Writer B updates document
                |
                v
Writer A sends update with stale token
                |
                v
Elasticsearch checks token
        /               \
       /                 \
  Still valid           Changed
     |                      |
     v                      v
  Write succeeds       409 Version Conflict
                            |
                            v
                    Application reloads and handles
~~~

Elasticsearch uses optimistic locking because many systems experience relatively low write contention. Instead of locking the document for the entire duration of application processing, the system lets multiple writers proceed and checks the condition at write time.

## 2. Distinguishing version types and concurrency tokens

Elasticsearch has several related concepts that are not interchangeable:

| Concept | Purpose | Source of value |
|---|---|---|
| Internal document version (`_version`) | Tracks the document's internal version | Elasticsearch |
| Sequence number (`_seq_no`) | Identifies operation order on the primary shard | Elasticsearch |
| Primary term (`_primary_term`) | Distinguishes the tenure/generation of the primary shard | Elasticsearch |
| External version | Compares versions supplied by an external system | Database/event/source system |
| Spring Data `@Version` | Enables version-based optimistic locking for an entity | Spring Data and Elasticsearch |

Two common OCC mechanisms are:

1. Version-based concurrency using the document's version, typically exposed by Spring Data via `@Version`.
2. Sequence-number-based concurrency using both `_seq_no` and `_primary_term` in `if_seq_no`/`if_primary_term` requests.

Do not send `_seq_no` without `_primary_term`. This pair must be preserved together as a single token.

### 2.1. Internal `_version`

Elasticsearch assigns `_version` to documents. Under default internal versioning, each successful write increments the version. You can see the version in the response:

~~~http
GET products/_doc/p-100
~~~

Abbreviated response:

~~~json
{
  "_index": "products",
  "_id": "p-100",
  "_version": 7,
  "found": true,
  "_source": {
    "name": "Wireless Keyboard",
    "price": 1299000
  }
}
~~~

`_version` is managed by Elasticsearch. Do not use it as a business version for a seller, product, or event unless your application intentionally uses external versioning.

### 2.2. Sequence number and primary term

Elasticsearch assigns a sequence number to every operation executed on the primary shard. The primary term changes when a primary shard is replaced/elected in a new term.

GET document returns this metadata:

~~~http
GET products/_doc/p-100
~~~

Illustrative response:

~~~json
{
  "_index": "products",
  "_id": "p-100",
  "_seq_no": 42,
  "_primary_term": 3,
  "_source": {
    "name": "Wireless Keyboard",
    "price": 1299000
  }
}
~~~

The application retains the pair `(42, 3)` to state: update only if the document is still in the exact state read. If another operation changed the document or the primary term changed, the condition no longer holds.

## 3. Conditional update with if_seq_no and if_primary_term

Suppose the application just read a document and received `_seq_no = 42`, `_primary_term = 3`. It can send a partial update with these two values:

~~~http
POST products/_update/p-100?if_seq_no=42&if_primary_term=3
{
  "doc": {
    "price": 1399000
  }
}
~~~

If the document has not changed since the read, the update succeeds. If another writer wrote first, Elasticsearch returns HTTP 409 with error `version_conflict_engine_exception`.

Key points:

- Obtain both `_seq_no` and `_primary_term` from the same read.
- Do not reuse an old token after an update succeeds.
- After a conflict, reload the fresh document and recompute the change against the new data.
- Do not blindly retry with the same token because the condition will remain invalid.

### 3.1. Conditional index

OCC also applies to index operations:

~~~http
PUT products/_doc/p-100?if_seq_no=42&if_primary_term=3
{
  "name": "Wireless Keyboard",
  "price": 1399000,
  "active": true
}
~~~

If the condition holds, the document is written. If the document has changed, the request hits a conflict. Index writes the entire document source, so only use it when the application has the complete state to save; if only changing `price`, a partial update is usually more suitable.

### 3.2. Conditional delete

You can prevent deleting a document that was modified since it was read:

~~~http
DELETE products/_doc/p-100?if_seq_no=42&if_primary_term=3
~~~

If the token is stale, Elasticsearch rejects the deletion. This is useful when deletion depends on state a user or service inspected earlier.

## 4. Retrieving concurrency tokens in the Search API

If an application reads a document via GET by ID, the response includes `_seq_no` and `_primary_term`. When reading via the Search API, ask Elasticsearch to return these two metadata values for each hit using `seq_no_primary_term`:

~~~http
GET products/_search
{
  "seq_no_primary_term": true,
  "query": {
    "term": {
      "category": "accessories"
    }
  }
}
~~~

Each hit can contain:

~~~json
{
  "_id": "p-100",
  "_seq_no": 42,
  "_primary_term": 3,
  "_source": {
    "name": "Wireless Keyboard"
  }
}
~~~

If the UI or a service needs to send the token back for an update, pass it through a clearly named DTO, such as `seqNo` and `primaryTerm`. Do not grab `_version` and mistakenly pass it to `if_seq_no`.

## 5. Using @Version in Spring Data Elasticsearch

Spring Data Elasticsearch supports entity optimistic locking via `org.springframework.data.annotation.Version`.

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Version
    private Long version;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Long)
    private Long price;

    public Product() {
    }

    public String getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public String getName() {
        return name;
    }

    public Long getPrice() {
        return price;
    }

    public void setPrice(Long price) {
        this.price = price;
    }
}
~~~

When the entity is saved for the first time, Spring Data/Elasticsearch manages the version. After a successful save, keep the entity returned by `save` to retain the fresh metadata:

~~~java
Product saved = repository.save(product);
Long currentVersion = saved.getVersion();
~~~

On the next save, the entity's version is used to detect concurrent modifications. If another writer saved the document after the entity was read, saving with the stale version will fail instead of overwriting the newer change.

### 5.1. Why use Long instead of long?

Using the wrapper type `Long` represents an unversioned state as `null`. A primitive `long` always defaults to `0`, which can blur the distinction between a new entity and a versioned entity if code initializes or assigns values manually.

Do not increment the version in setters or assign time-based versions manually. Version is managed by the persistence mechanism.

### 5.2. Repository save and optimistic locking

Example:

~~~java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
~~~

A service can save the entity:

~~~java
Product product = repository.findById("p-100").orElseThrow();
product.setPrice(1399000L);

Product saved = repository.save(product);
~~~

If no other writer modified the document since it was read, `save` succeeds. If the version is stale, Spring Data translates Elasticsearch's concurrency error into a Spring exception hierarchy exception, typically `OptimisticLockingFailureException`.

### 5.3. @Version does not automatically cover every operation

`@Version` is metadata for entity persistence. Do not assume every custom query, Painless script, `UpdateQuery`, or bulk request automatically uses the entity's version property.

When using lower-level update APIs, inspect the actual outgoing request and pass appropriate concurrency conditions, such as `if_seq_no`/`if_primary_term` or an in-script version guard. Having `@Version` on an entity does not make a multi-document bulk request transactional.

## 6. Handling OptimisticLockingFailureException

When Spring Data detects a stale version, the application can catch `OptimisticLockingFailureException`:

~~~java
import org.springframework.dao.OptimisticLockingFailureException;

public Product changePrice(String productId, long newPrice) {
    Product product = repository.findById(productId).orElseThrow();
    product.setPrice(newPrice);

    try {
        return repository.save(product);
    } catch (OptimisticLockingFailureException exception) {
        throw new ProductChangedConcurrentlyException(
                "Product was changed by another request: " + productId,
                exception);
    }
}
~~~

There are two ways to respond depending on business rules:

- Report the conflict to the caller and ask them to reload the data.
- Reload the fresh state, merge the change, and retry if the operation can be safely recomputed.

Do not catch the exception and return the stale entity as if the update succeeded.

### 6.1. Retries must reload the data

One retry pattern:

~~~java
public Product changePriceWithRetry(String productId, long newPrice) {
    int maxAttempts = 3;

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        Product product = repository.findById(productId).orElseThrow();
        product.setPrice(newPrice);

        try {
            return repository.save(product);
        } catch (OptimisticLockingFailureException exception) {
            if (attempt == maxAttempts) {
                throw exception;
            }
        }
    }

    throw new IllegalStateException("Unreachable");
}
~~~

This example illustrates reloading a fresh entity on every attempt. In real systems, add backoff/jitter and a retry time budget. More importantly, verify whether reapplying the change makes business sense.

If the operation is "set price to 1,399,000," reloading and reassigning the same new price can usually be recomputed safely. If the operation is "decrement stock by 2," you must ensure the same request is not applied twice when a client retries after a timeout.

### 6.2. When should you not auto-retry?

Do not auto-retry if:

- User confirmation is needed because the newer change alters the business decision.
- Two writers modify the same field under rules that cannot be merged automatically.
- The update depends on an old state, such as transitioning an order from PAID to CANCELLED while another writer already marked it SHIPPED.
- The actual error is mapping/parsing/authentication rather than a transient conflict.

In such cases, return the conflict to the business layer for explicit handling.

## 7. Updating with UpdateQuery and if_seq_no/if_primary_term

When using `ElasticsearchOperations` instead of repository `save`, you can attach concurrency tokens to `UpdateQuery`:

~~~java
import java.util.Map;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.document.Document;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.UpdateQuery;

public void updatePrice(
        ElasticsearchOperations operations,
        String productId,
        long expectedSeqNo,
        long expectedPrimaryTerm,
        long newPrice) {

    UpdateQuery update = UpdateQuery.builder(productId)
            .withDocument(Document.from(Map.of(
                    "price", newPrice)))
            .withIfSeqNo(expectedSeqNo)
            .withIfPrimaryTerm(expectedPrimaryTerm)
            .build();

    operations.update(
            update,
            IndexCoordinates.of("products"));
}
~~~

`expectedSeqNo` and `expectedPrimaryTerm` must come from the same document read. If another writer modifies the document before the update runs, Elasticsearch rejects the operation.

### 7.1. Updating one field while keeping others intact

`Document.from(Map.of("price", newPrice))` builds a partial document. Other fields not included in the payload are preserved. This is appropriate when modifying just a few fields without rewriting the entire entity.

### 7.2. Controlling conflicts in scripts

If a change depends on current state, you can use a Painless script:

~~~java
UpdateQuery update = UpdateQuery.builder(productId)
        .withScript("""
            if (ctx._source.stock >= params.quantity) {
                ctx._source.stock -= params.quantity;
            } else {
                ctx.op = 'noop';
            }
            """)
        .withParams(Map.of("quantity", 2))
        .withIfSeqNo(expectedSeqNo)
        .withIfPrimaryTerm(expectedPrimaryTerm)
        .build();
~~~

If the token is stale, the update conflicts before applying the change. If the token is still valid, the script checks stock and either decrements it or returns `noop`. Define clearly what `noop` means in business logic and API responses.

Do not treat a script as a transaction spanning other documents. It only governs a single document within a single update operation.

## 8. Update API's retry_on_conflict

The Update API has a `retry_on_conflict` parameter. When an update hits a conflict because another writer updated the same document, Elasticsearch can reload the new source and retry applying the update a specified number of times.

REST API:

~~~http
POST products/_update/p-100?retry_on_conflict=3
{
  "doc": {
    "price": 1399000
  }
}
~~~

The Bulk API expresses this option in the action metadata:

~~~http
POST products/_bulk
{"update":{"_index":"products","_id":"p-100","retry_on_conflict":3}}
{"doc":{"price":1399000}}
~~~

With Spring Data `UpdateQuery`:

~~~java
UpdateQuery update = UpdateQuery.builder("p-100")
        .withDocument(Document.from(Map.of(
                "price", 1399000L)))
        .withRetryOnConflict(3)
        .build();
~~~

`retry_on_conflict` is useful when an update can be reapplied onto the new source and the application does not need to reload/merge every conflict itself. It does not guarantee success; if conflicts persist past the retry limit, the operation still fails.

### 8.1. How does retry_on_conflict differ from if_seq_no/if_primary_term?

| Mechanism | Behavior | When suitable |
|---|---|---|
| `if_seq_no` + `if_primary_term` | Writes only if the document still matches the read version | Must protect a decision based on a specific snapshot |
| `retry_on_conflict` | Elasticsearch automatically retries the update on conflict | Update can be safely recomputed on the fresh source |
| Spring Data `@Version` | Checks entity version on save | Entity persistence via repository/operations |
| External versioning | Compares version sent by an external source | Syncing projections from databases/events with increasing versions |

Do not use `retry_on_conflict` to mask business conflicts. If newer changes invalidate the old request, return a conflict and let the caller decide.

### 8.2. Notes when combining retries and scripts

Scripts re-run against the fresh source when Elasticsearch retries due to a version conflict. Therefore, scripts must be designed with the intended semantics.

An additive script:

~~~text
ctx._source.stock += params.delta
~~~

can be accurate if each update request is processed once successfully and internal retries only replace uncommitted conflicted attempts. However, if the application resends the entire request after a timeout or a message broker redelivers an event, `delta` may be added a second time. These two kinds of retries are different.

For event-driven counters, use event IDs/deduplication or store the last applied version. For final-state data, setting an absolute value is usually easier to retry safely.

## 9. External versioning for syncing from a source system

A system may have its own business version. For example, a database increments `sellerVersion` whenever a seller changes:

~~~json
{
  "sellerId": "seller-7",
  "name": "North Star Retail",
  "version": 18
}
~~~

When indexing the projection into Elasticsearch, external versioning can reject older events:

~~~http
PUT sellers/_doc/seller-7?version=18&version_type=external
{
  "sellerId": "seller-7",
  "name": "North Star Retail"
}
~~~

With `version_type=external`, Elasticsearch accepts the write only when the external version is strictly greater than the stored version. If a version 17 event arrives after version 18, the request conflicts and does not overwrite the newer state.

### 9.1. external_gte

`version_type=external_gte` allows a submitted version equal to or greater than the current version:

~~~http
PUT sellers/_doc/seller-7?version=18&version_type=external_gte
{
  "sellerId": "seller-7",
  "name": "North Star Retail"
}
~~~

This supports replaying the same version. However, use it only when every payload with the same version represents the exact same state. If two different payloads share the same version, the later request can overwrite the earlier one even though the version did not increase.

### 9.2. External version and _version are not from the same source

When using external versioning, the version value comes from the database or event producer. It is not Elasticsearch's default auto-incrementing internal version. Do not take an internal `_version` value and assume it equals the database's `aggregateVersion`.

### 9.3. Bulk index with external version

A bulk index action can pass `version` and `version_type` in its metadata:

~~~http
POST _bulk
{"index":{"_index":"sellers","_id":"seller-7","version":18,"version_type":"external"}}
{"sellerId":"seller-7","name":"North Star Retail"}
~~~

When an older event arrives later, that item fails with a conflict. Other items in the bulk response can still succeed; inspect each item.

For partial updates, external versioning is not always directly equivalent to an index action. Use `if_seq_no`/`if_primary_term` or a script comparing a business version inside `_source` when partial update control is needed.

### 9.4. When should external versioning be used?

Suitable when:

- The source database issues a monotonically increasing version per aggregate.
- Events can arrive duplicated or out of order.
- The Elasticsearch projection can be reindexed with the latest state.
- Each version uniquely identifies a complete document state.

Not suitable if the source lacks stable versions or multiple producers generate unordered versions.

## 10. Bulk writes and version conflicts

The Bulk API lets you send concurrency metadata per action. Example index action with `if_seq_no`/`if_primary_term`:

~~~http
POST _bulk
{"index":{"_index":"products","_id":"p-100","if_seq_no":42,"if_primary_term":3}}
{"name":"Wireless Keyboard","price":1399000}
{"delete":{"_index":"products","_id":"p-101","if_seq_no":17,"if_primary_term":2}}
~~~

If one item's token is stale, that item fails with 409. Other items can still succeed.

### 10.1. Checking per-item errors

A bulk response may look like:

~~~json
{
  "errors": true,
  "items": [
    {
      "index": {
        "_id": "p-100",
        "status": 200,
        "result": "updated"
      }
    },
    {
      "delete": {
        "_id": "p-101",
        "status": 409,
        "error": {
          "type": "version_conflict_engine_exception",
          "reason": "if_seq_no and if_primary_term do not match"
        }
      }
    }
  ]
}
~~~

The HTTP status of the bulk request is not enough to conclude all items succeeded. Inspect `errors` and every element in `items`.

### 10.2. Spring Data BulkFailureException

`bulkIndex` and `bulkUpdate` in Spring Data can throw `BulkFailureException` when one or more items fail. The exception provides failed document details via `getFailedDocuments()`, including ID, status, and error message in current API versions.

~~~java
try {
    operations.bulkUpdate(
            updates,
            BulkOptions.defaultOptions(),
            IndexCoordinates.of("products"));
} catch (BulkFailureException exception) {
    exception.getFailedDocuments().forEach((id, failure) -> {
        if (failure.status() == 409) {
            log.info("Concurrent update for product {}", id);
        } else {
            log.error(
                    "Update failed for {}: {}",
                    id,
                    failure.errorMessage());
        }
    });

    throw exception;
}
~~~

Do not retry the entire batch just because one item hit a version conflict. Items that succeeded do not need to run again. For conflicted items, reload the document and handle according to business rules.

### 10.3. Retaining correlation with input

A batch can experience multiple types of errors. Maintain a map from document ID or operation ID back to the original event/command so you can:

- Know which fields were requested to change.
- Know the expected version.
- Distinguish conflict errors from mapping errors.
- Retry only the right items.
- Route unprocessable items to a DLQ.

Do not simply log a generic exception and drop the batch.

## 11. Version conflicts in Update By Query

Update By Query finds documents matching a query and updates each document according to the version it read. If a document is modified by another writer before the update applies, the operation can encounter a version conflict.

By default, update-by-query stops on conflict. You can instruct it to proceed with other documents:

~~~http
POST products/_update_by_query?conflicts=proceed
{
  "query": {
    "term": {
      "category": "accessories"
    }
  },
  "script": {
    "source": "ctx._source.active = params.active",
    "params": {
      "active": false
    }
  }
}
~~~

`conflicts=proceed` only lets the job continue; it does not resolve the conflicting documents. The response includes `version_conflicts` so the application knows how many were skipped. If all documents must be updated, re-run for the conflicted ones or reconcile.

With Spring Data `UpdateQuery` using query selection, you can configure `withAbortOnVersionConflict(false)`. Inspect `ByQueryResponse.getVersionConflicts()` and `getFailures()` to see the results.

## 12. Distinguishing version conflicts from other errors

HTTP 409 appears in several conflict situations, not all of which mean the same thing:

| Situation | Cause | How to handle |
|---|---|---|
| OCC conflict | `seq_no`/`primary_term` or version no longer matches | Reload, merge, or discard stale operation |
| Create conflict | ID already exists | Check for duplicate; do not blindly overwrite |
| External version conflict | Submitted version is older or fails condition | Discard older event or take latest state |
| Mapping/parsing error | Data does not match mapping | Fix payload/schema; do not retry raw data |
| 429 rejected execution | Cluster overloaded | Backoff, reduce concurrency |
| 5xx/service unavailable | Transient or infrastructure error | Bounded retry and verify write state |

Do not retry all 409 errors the same way. For instance, a create conflict might mean the document was already created by a previous run; in an idempotent import, you can verify the payload and treat it as done. Yet if the requirement is strictly creating a unique new record, report a duplicate.

## 13. Designing retries properly

A retry strategy must define:

1. Which error types are retried.
2. Whether the document must be reloaded.
3. Whether business logic must be recomputed.
4. Maximum retry attempts.
5. Backoff and jitter.
6. Handling when retries are exhausted.
7. How to ensure the same command is not applied twice.

### 13.1. Retrying OCC conflicts

With `if_seq_no`/`if_primary_term`, the old token cannot be reused. A retry must:

- Reload the new document.
- Re-check business rules on the new state.
- Recompute changes.
- Send the update with the new token.

If business rules prohibit automatic merging, return the conflict to the caller.

### 13.2. Exponential backoff

When multiple writers contend on the same document, immediate retries can spark another round of conflicts. Use backoff with jitter:

~~~text
delay = min(maxDelay, baseDelay * 2^attempt) + randomJitter
~~~

Example base delays:

| Attempt | Delay |
|---:|---:|
| 1 | 100 ms |
| 2 | 200 ms |
| 3 | 400 ms |
| 4 | 800 ms |
| 5 | 1,600 ms |

These are illustrative values. Cap total retry duration and monitor conflict rates to detect hotspots.

### 13.3. Idempotency on client timeout

A tricky case is when a client sends an update, Elasticsearch writes it successfully, and the response is lost to a timeout. The client does not know whether the request committed.

If the client resends an increment/decrement operation, data can be modified twice. For non-idempotent commands, you need event IDs/deduplication, business sequences/versions, or operations that specify final state.

Setting a field to a deterministic value is generally easier to retry:

~~~json
{
  "doc": {
    "status": "ACTIVE"
  }
}
~~~

Compared to a counter-increment script:

~~~text
ctx._source.orderCount += 1
~~~

Delta scripts require a separate deduplication mechanism.

## 14. Version conflicts do not solve multi-document consistency

OCC protects a single document at write time. It does not create transactions across multiple documents or indices.

For example, changing `sellerName` might require updating:

- The seller document.
- 500 listing documents.
- Recommendation documents.

Each document has its own version. Some updates may succeed while others conflict. There is no automatic rollback for documents that succeeded.

For distributed projections, combine:

- Events carrying aggregate versions.
- Idempotent updates.
- Per-item conflict retries.
- Dead-letter queues for persistent failures.
- Reconciliation to catch stale projections.
- Rebuilding indices from the source of truth when needed.

If the authoritative source is a relational database, transactional outbox or CDC prevents losing events between committing source data and publishing messages. Elasticsearch is still updated under eventual consistency.

## 15. Combining @Version with multiple writers

Suppose two services concurrently read a `Product` with version 7:

~~~text
Service A reads Product version 7
Service B reads Product version 7

Service A changes price and saves -> succeeds, version 8
Service B changes name and saves -> conflict because version 7 is stale
~~~

Even though A and B modified different fields, `@Version` can still reject B's entire save because the entity is persisted as a versioned unit. This behavior prevents lost updates.

After the conflict, service B can reload version 8, apply its name change onto the fresh entity, and save the next version. Thus, A's price change is preserved.

If services truly own independent fields and need parallel updates, consider field-level partial updates or cleanly separating projections/ownership. However, ensure operations cannot overwrite one another or violate business invariants.

## 16. Deleting documents with version control

Deletes can also race with updates:

1. Service A reads a document and decides to delete it.
2. Service B updates the document.
3. Service A sends delete with the stale token.

Using `if_seq_no`/`if_primary_term`, the delete succeeds only if the document is still at the version that was read. If the document changed, the delete conflicts and the application can re-evaluate its decision.

~~~http
DELETE products/_doc/p-100?if_seq_no=42&if_primary_term=3
~~~

With bulk delete, each action's metadata can carry `if_seq_no` and `if_primary_term`:

~~~http
POST _bulk
{"delete":{"_index":"products","_id":"p-100","if_seq_no":42,"if_primary_term":3}}
~~~

Do not confuse version conflict with document missing. If the document was already deleted by another writer, the response may indicate not found rather than conflict depending on state and API.

## 17. Observing and diagnosing version conflicts

When conflicts occur frequently, determine:

- Which document IDs have high conflict rates.
- Which index and shard hold those documents.
- Which services or workers write concurrently.
- Whether conflicts come from `@Version`, `seq_no`/`primary_term`, external version, or create duplicates.
- Whether retries succeed.
- Average retry count and retry exhaustion rate.
- Whether a single aggregate or tenant is creating a hotspot.

Suggested metrics:

| Metric | Meaning |
|---|---|
| `optimistic_lock_conflicts_total` | Total conflicts on save/update |
| `bulk_items_failed_total{status="409"}` | Number of conflicted bulk items |
| `update_retry_attempts` | Internal/application retry count |
| `update_retry_exhausted_total` | Operations exhausting retries |
| `projection_version_lag` | Version gap between source and projection |
| `conflict_rate_by_index` | Conflict rate per index |

Do not log entire sources or sensitive information just to debug conflicts. ID, index, version token, event ID, and operation type are usually enough for tracing.

## 18. Testing version conflicts

Unit tests for merge logic are not enough to verify Elasticsearch enforces OCC. You need integration tests with a real Elasticsearch instance or Testcontainers.

### 18.1. Testing @Version

Scenario:

1. Save a new Product.
2. Read the same document into two objects A and B.
3. Update A and save successfully.
4. Update B and try to save.
5. Assert B's save throws `OptimisticLockingFailureException`.

Example:

~~~java
@Test
void staleEntityCannotOverwriteNewerVersion() {
    Product initial = repository.save(
            new Product("p-100", "Keyboard", 1000L));

    Product writerA = repository.findById(initial.getId()).orElseThrow();
    Product writerB = repository.findById(initial.getId()).orElseThrow();

    writerA.setPrice(1200L);
    repository.save(writerA);

    writerB.setName("Old Keyboard");

    assertThatThrownBy(() -> repository.save(writerB))
            .isInstanceOf(OptimisticLockingFailureException.class);
}
~~~

This is an illustrative test example; constructors, getters/setters, and index setup should match your actual entity.

### 18.2. Testing if_seq_no/if_primary_term

Scenario:

1. GET document and capture `seq_no` and `primary_term`.
2. Write another change so the token changes.
3. Send an update with the stale token.
4. Verify the request receives 409.
5. GET the document again and verify the newer change remains intact.

This test proves conditional writes prevent stale writers from overwriting data.

### 18.3. Testing retry_on_conflict

Issue multiple concurrent requests updating the same document. Verify updates with `retry_on_conflict` complete within the allowed retries, while still asserting the final state matches business invariants.

Do not assert only that requests returned success. For a counter-increment script, assert the counter matches the number of unique commands sent, not the number of client retries.

### 18.4. Testing external versioning

Send version 18 first, then send version 17. Assert the version 17 event conflicts and the source retains version 18 state. If using `external_gte`, add a test replaying version 18 with the same payload and a test verifying producers never emit two different payloads for the same version.

### 18.5. Testing bulk partial failure

Send a bulk request containing:

- One item with a current token.
- One item with a stale token.
- One item with a mapping error.

Assert the valid item succeeds, the conflicted item is identified individually, the mapping error is not blindly retried, and the batch can recover without re-running non-idempotent actions.

## 19. Conflict-handling workflow in a service

When a write operation hits a conflict, a service can proceed as follows:

1. Identify the mechanism causing the conflict: `@Version`, `seq_no`/`primary_term`, external version, or create duplicate.
2. Determine whether the business change can be merged automatically or needs the caller's decision.
3. If auto-mergeable, read the latest state.
4. Re-verify business invariants on the latest state.
5. Recompute the change.
6. Send the update with the new version/token.
7. Bound retry attempts and use backoff.
8. If still conflicting, return a clear error or route the command to a reprocessing flow.
9. For bulk, retry only failed items.
10. Record metrics and correlation IDs for monitoring.

## 20. Common mistakes

### Using _version instead of _seq_no

`_version` and `_seq_no` are two different metadata values. `if_seq_no` must receive the sequence number, along with `if_primary_term` obtained from the same response.

### Saving seq_no while forgetting primary_term

The two values form a single concurrency token. Do not fabricate them or mix `seq_no` from one read with `primary_term` from another read.

### Retrying with the same token after 409

A stale token stays stale. Reload the document and obtain a new token if retrying.

### Catching conflict and re-saving the old entity

The old entity still carries the old version. Reload the fresh entity, merge changes, and save the new version.

### Using @Version and thinking all custom updates are protected

`UpdateQuery`, scripts, and native bulk calls may need their own concurrency conditions. Inspect requests and use `if_seq_no`/`if_primary_term` or an appropriate version guard.

### Using retry_on_conflict for business conflicts

Elasticsearch can only retry technical updates. If the new state invalidates the request, the application must decide.

### Retrying every 409 error

Create duplicates, external version conflicts, and OCC conflicts have different meanings. Classify the error type before retrying.

### Using external_gte with non-deterministic payloads

Two different payloads with the same version can overwrite each other. Only use `external_gte` when a single version uniquely defines one state.

### Treating bulk as a transaction

A conflicted item does not roll back succeeded items. Inspect per-item results and retry selectively.

### Ignoring version conflicts in update-by-query

`conflicts=proceed` merely continues the job. Conflicted documents remain un-updated and require reconciliation.

### Expecting OCC to provide multi-document transactions

OCC protects individual documents. Making multi-document projections converge requires events, retries, idempotency, and reconciliation.

## 21. Which mechanism to choose?

| Situation | Appropriate mechanism |
|---|---|
| Saving entities via Repository/`ElasticsearchOperations` and wanting stale-entity detection | `@Version` |
| Reading a document, editing, and writing only if unmodified | `if_seq_no` + `if_primary_term` |
| Update script that can safely reapply on fresh source | `retry_on_conflict` |
| Syncing snapshots with a database business version | External versioning |
| Multiple bulk items each with their own concurrency token | `if_seq_no`/`if_primary_term` per action |
| Update-by-query hits conflicts and must continue other items | `conflicts=proceed`, then reconcile |
| Multi-document/index changes needing eventual consistency | Events/outbox, idempotency, retries, and reconciliation |

No single mechanism fits every situation. Choose based on version source, update style, auto-mergeability, and business requirements.

## 22. Summary

Version conflicts happen when a writer attempts to write based on stale state after another writer modified the document. Elasticsearch provides internal `_version` and the optimistic concurrency token `_seq_no`/`_primary_term`. Conditional writes with `if_seq_no` and `if_primary_term` succeed only if the document remains in the exact read state. Spring Data Elasticsearch supports version-based optimistic locking for entities via `@Version` and can raise `OptimisticLockingFailureException` when an entity is stale.

The Update API provides `retry_on_conflict` to retry updates after technical conflicts. This suits updates that can be reapplied to fresh source; it does not replace business decisions or protect against duplicate client requests. External versioning fits when the data source supplies monotonically increasing versions, rejecting stale events. Bulk and update-by-query can still partially fail, so inspect individual items or `ByQueryResponse`.

When encountering a conflict, do not re-save the stale entity or retry with the old token. Read the latest state, check invariants, merge changes if allowed, and bound retries. For replicated data across multiple documents, OCC protects only individual documents; outbox/CDC, event versions, idempotency, retries, and reconciliation are needed for projections to converge.

## References

- [Spring Data Elasticsearch – Object Mapping and Versioning](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)
- [Spring Data Elasticsearch – Elasticsearch Operations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/ElasticsearchOperations.html)
- [Spring Data Elasticsearch – UpdateQuery API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/query/UpdateQuery.html)
- [Spring Data Elasticsearch – BulkFailureException API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/BulkFailureException.html)
- [Elasticsearch – Optimistic concurrency control](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/optimistic-concurrency-control)
- [Elasticsearch – Index API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-index)
- [Elasticsearch – Update API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-update)
- [Elasticsearch – Bulk API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-bulk)
- [Elasticsearch – Update By Query API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-update-by-query)
