# Deterministic IDs, Create Operations, and Idempotent Repeatability

When ingesting data into Elasticsearch, an application may send the same document multiple times due to network retries, message redelivery, job reruns, or post-failure batch replays. If each write generates a new document ID, duplicate data appears. If writes overwrite improperly, an older event can clobber newer data.

Three concepts help control this problem:

- **Deterministic ID**: the same logical entity or event always maps to the exact same document ID.
- **Conditional create**: create a document only when the ID does not yet exist; if it already exists, Elasticsearch returns a conflict.
- **Idempotency**: executing the same operation multiple times yields the same final state as executing it once.

In Spring Data Elasticsearch, you can assign IDs on entities or construct `IndexQuery` with a precomputed ID. When create-only semantics are needed, select the `CREATE` operation instead of `INDEX`. For bulk ingestion, inspect per-item results because a single bulk request can partially succeed.

## 1. Why Are Deterministic IDs Important?

Suppose a system receives product events:

~~~json
{
  "eventId": "evt-2026-000184",
  "productId": "P-1001",
  "status": "PUBLISHED"
}
~~~

If the application lets Elasticsearch auto-generate IDs on every processing pass, resending the same event can create extra documents:

~~~text
Attempt 1: _id = generated-A
Retry:     _id = generated-B
Retry:     _id = generated-C
~~~

One logical event created three documents. This skews counts, aggregations, reports, and downstream consumers.

Using a deterministic ID derived from the event:

~~~text
eventId = evt-2026-000184
       -> _id = evt-2026-000184
~~~

Every attempt for the same event targets the same document. The application can use `create` to guarantee only a single creation succeeds.

Deterministic IDs are not merely a storage optimization. They are a core part of correctness in distributed systems, where a timeout leaves you unsure whether the server executed the request.

## 2. Choosing IDs by Entity vs. by Event

Before constructing IDs, decide what each document represents.

| Document Model | Suitable ID Source | Meaning |
|---|---|---|
| Current product record | Product ID / business key | One document represents the latest state of the product |
| Order event | Event ID | Each logical event has its own document |
| Message processing record | Message ID or idempotency key | Each message is recorded only once |
| Daily snapshot | Entity ID + snapshot date | Each entity has one snapshot per period |
| Tenant-scoped record | Tenant ID + business key | Business key is scoped within a tenant |

For instance, if `productId` is globally unique, it can directly serve as the Elasticsearch document ID. If it is only unique within a tenant, include the tenant in the identifier:

~~~text
tenant-42:P-1001
tenant-77:P-1001
~~~

Two products with the same code `P-1001` in two different tenants receive distinct IDs.

If documents represent events, do not use `productId` as the document ID, as multiple distinct events for the same product would overwrite one another. Use the event ID or a unique idempotency key for that event.

## 3. Properties of a Good Deterministic ID

A deterministic ID should satisfy these properties:

1. The same logical entity always produces the same ID.
2. Two distinct entities do not accidentally collide on the same ID.
3. The ID can be recomputed after a process restart.
4. It does not depend on retry timing or delivery count.
5. It avoids exposing sensitive data if IDs appear in logs or URLs.
6. Producers and consumers share a standardized canonical format.

Example combining tenant and business key:

~~~java
public final class DocumentIds {

    private DocumentIds() {
    }

    public static String product(String tenantId, String productId) {
        return tenantId + ":" + productId;
    }
}
~~~

Usage:

~~~java
String id = DocumentIds.product("tenant-42", "P-1001");
~~~

If business keys can contain the delimiter, use explicit escaping or encoding. Another option is hashing a canonical string:

~~~java
String canonicalKey = tenantId + "\u0000" + productId;
String id = sha256Hex(canonicalKey);
~~~

Hashing keeps IDs compact and avoids putting raw business keys directly into document IDs. Still, maintain consistent canonicalization rules: trimming, Unicode normalization, case sensitivity, and character encoding must match across all producers.

Never use the current timestamp or a fresh random UUID on retries if the goal is for the same entity to keep the same ID.

## 4. Entity IDs and `_id` Metadata

In Spring Data Elasticsearch, the `@Id` annotation maps a Java property to Elasticsearch's document ID metadata.

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String productId;

    @Field(type = FieldType.Keyword)
    private String tenantId;

    @Field(type = FieldType.Text)
    private String name;

    // Constructors, getters and setters
}
~~~

Here:

- `id` is Elasticsearch's document ID metadata.
- `productId` is a business field inside `_source`.
- `tenantId` is a field used for filtering, authorization, or querying.

`id` and `productId` may share the same value, though they do not have to. If the ID is composed from tenant and product ID, `_source` can still store the separate business keys for querying.

Example:

~~~java
ProductDocument product = new ProductDocument();
product.setId(DocumentIds.product(tenantId, productId));
product.setTenantId(tenantId);
product.setProductId(productId);
product.setName("Wireless Keyboard");
~~~

Because the ID is assigned upfront, every subsequent write for the same product targets the same document.

## 5. Distinguishing `INDEX` and `CREATE`

Elasticsearch provides two common write operations in the Index API:

| Operation | When ID Does Not Exist | When ID Already Exists |
|---|---|---|
| `index` | Creates the document | Replaces document source with the submitted content |
| `create` | Creates the document | Returns an HTTP 409 conflict error |

`INDEX` example:

~~~http
PUT /products/_doc/tenant-42:P-1001
{
  "tenantId": "tenant-42",
  "productId": "P-1001",
  "name": "Wireless Keyboard"
}
~~~

Resending the same request writes to the same ID. This is upsert/replace-by-ID behavior: the document is created if missing, or `_source` is replaced if present.

`CREATE` example:

~~~http
PUT /products/_create/tenant-42:P-1001
{
  "tenantId": "tenant-42",
  "productId": "P-1001",
  "name": "Wireless Keyboard"
}
~~~

If the ID does not exist yet, the document is created. If the ID already exists, Elasticsearch returns a conflict and does not overwrite the existing document.

Use `CREATE` when business rules specify "create once only." Use `INDEX` when business rules specify "bring the document to the full state described by the current request."

Do not treat these two operations as equivalent merely because both take a document ID.

## 6. How Does `CREATE` Help Prevent Duplicates?

Suppose two workers receive the same message due to consumer rebalancing or at-least-once delivery:

~~~mermaid
sequenceDiagram
    participant A as Worker A
    participant B as Worker B
    participant ES as Elasticsearch
    A->>ES: create _id=evt-184
    B->>ES: create _id=evt-184
    ES-->>A: 201 Created
    ES-->>B: 409 Conflict
~~~

Elasticsearch enforces the creation precondition on the server side. Only one request can create the document for that ID; the other request receives a conflict.

This prevents two concurrent workers from creating two documents for the same event, provided both use the same deterministic ID and target the same index.

However, HTTP 409 does not by itself prove the two payloads are identical. Two requests might share an ID while carrying different payloads. The application must determine whether a conflict represents:

- A valid duplicate: the same event and same logical content.
- An ID collision or producer bug: the same ID with a different payload.
- A business conflict: an entity was already created by another workflow.

Do not blindly catch every 409 and ignore it without checking what it means.

## 7. Creating Documents with Fixed IDs in Spring Data

You can assign the ID on the entity and use `IndexQuery`.

~~~java
import org.springframework.data.elasticsearch.core.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.IndexQuery;
import org.springframework.data.elasticsearch.core.query.IndexQueryBuilder;

ProductDocument product = new ProductDocument();
product.setId("tenant-42:P-1001");
product.setTenantId("tenant-42");
product.setProductId("P-1001");
product.setName("Wireless Keyboard");

IndexQuery indexQuery = new IndexQueryBuilder()
        .withId(product.getId())
        .withObject(product)
        .build();

String indexedId = operations.index(
        indexQuery,
        IndexCoordinates.of("products")
);
~~~

This example uses the default `index` operation semantics. If the document already exists, its content can be overwritten.

When the ID is set on the entity and mapping metadata recognizes `@Id`, Spring Data can also read the ID from the entity. Setting the ID explicitly before building the query makes deterministic ID usage explicit in the ingestion flow.

## 8. Using `CREATE` via `IndexQuery`

Spring Data Elasticsearch exposes the operation type on `IndexQuery`. You can specify `IndexQuery.OpType.CREATE` to instruct Elasticsearch to create only if the ID does not exist yet.

~~~java
import org.springframework.data.elasticsearch.core.query.IndexQuery;
import org.springframework.data.elasticsearch.core.query.IndexQueryBuilder;

IndexQuery createQuery = new IndexQueryBuilder()
        .withId(product.getId())
        .withObject(product)
        .withOpType(IndexQuery.OpType.CREATE)
        .build();

String createdId = operations.index(
        createQuery,
        IndexCoordinates.of("products")
);
~~~

With this operation:

- ID does not exist: document is created.
- ID already exists: Elasticsearch returns a conflict.
- Existing `_source` is not overwritten by a duplicate create request.

Handle conflicts at the application layer per business rules. If you need to verify duplicates, fetch the existing document and compare the event ID, payload hash, or source metadata.

Exact APIs can vary across Spring Data Elasticsearch versions. Check your project's dependency Javadoc if builder methods or enums differ.

## 9. Bulk Create with Deterministic IDs

When importing multiple documents, build a list of `IndexQuery` items and submit them with `bulkIndex(... )`.

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.core.BulkOptions;
import org.springframework.data.elasticsearch.core.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.IndexQuery;
import org.springframework.data.elasticsearch.core.query.IndexQueryBuilder;

List<IndexQuery> createQueries = products.stream()
        .map(product -> new IndexQueryBuilder()
                .withId(product.getId())
                .withObject(product)
                .withOpType(IndexQuery.OpType.CREATE)
                .build())
        .toList();

var results = operations.bulkIndex(
        createQueries,
        BulkOptions.defaultOptions(),
        IndexCoordinates.of("products")
);
~~~

Each item carries its own ID and `CREATE` operation. Elasticsearch processes each action within the bulk request.

A bulk request is not a transaction. Some items can succeed while other items conflict or fail due to mapping, validation, or transient errors.

Therefore, after calling bulk, inspect per-item outcomes and do not rely solely on the method returning normally.

## 10. The Bulk API Returns Per-Item Results

A bulk request can contain multiple actions. Example:

~~~http
POST /_bulk
Content-Type: application/x-ndjson

{"create":{"_index":"products","_id":"tenant-42:P-1001"}}
{"tenantId":"tenant-42","productId":"P-1001","name":"Wireless Keyboard"}
{"create":{"_index":"products","_id":"tenant-42:P-1002"}}
{"tenantId":"tenant-42","productId":"P-1002","name":"Wireless Mouse"}
{"create":{"_index":"products","_id":"tenant-42:P-1001"}}
{"tenantId":"tenant-42","productId":"P-1001","name":"Duplicate Keyboard"}
~~~

The response can look like:

~~~json
{
  "errors": true,
  "items": [
    {
      "create": {
        "_index": "products",
        "_id": "tenant-42:P-1001",
        "status": 201,
        "result": "created"
      }
    },
    {
      "create": {
        "_index": "products",
        "_id": "tenant-42:P-1002",
        "status": 201,
        "result": "created"
      }
    },
    {
      "create": {
        "_index": "products",
        "_id": "tenant-42:P-1001",
        "status": 409,
        "error": {
          "type": "version_conflict_engine_exception"
        }
      }
    }
  ]
}
~~~

The Bulk API continues processing remaining items even when one item fails. The `errors` field indicates whether at least one item failed; `items` reports each action's individual outcome.

With NDJSON Bulk API payloads:

- Each action and document source sits on separate lines depending on the operation type.
- Do not insert JSON commas between actions.
- The request must end with a trailing newline.
- Do not wrap all actions in a surrounding JSON array.
- Response item order matches request action order.

## 11. Classifying Errors to Retry Properly

Do not retry an entire bulk request when only a few items fail.

| Outcome | Common Meaning | Handling Approach |
|---|---|---|
| 200/201 | Item succeeded | Record completion |
| 409 on `CREATE` | ID already exists | Determine if legitimate duplicate or business conflict |
| 400 | Invalid mapping or data | Fix data/structure; do not retry blindly |
| 401/403 | Authentication or authorization | Fix credentials/roles |
| 429 | Node overloaded or temporarily rejected | Retry with backoff and limits |
| 502/503/504 | Possible temporary gateway/service error | Controlled retry after checking health |
| Timeout/connection loss | Unknown whether server executed | Use deterministic IDs and verify outcome before deciding |

When a timeout occurs, you cannot deduce the request went unexecuted. Elasticsearch may have created the document while the response was lost in transit. Resending `CREATE` with the same ID can return 409 on retry. This is where deterministic IDs and duplicate handling become essential.

A sound retry policy should:

1. Retry only items with transient failures.
2. Use exponential backoff and jitter.
3. Enforce a maximum retry count.
4. Keep the exact same ID and logical payload.
5. Route non-retryable errors to a dead-letter queue or report them clearly.
6. Record conflicts separately for reconciliation.

Never retry continuously without delay, as doing so can overload the cluster further.

## 12. `CREATE` and Idempotency

Idempotency means applying the same operation multiple times has the same state effect as applying it once.

`CREATE` with a deterministic ID has an important property:

- The first call creates the document.
- Subsequent calls with the same ID receive a conflict.
- No extra documents are created and `_source` is never overwritten.

In terms of stored state, only one document exists. In terms of response, however, the first call returns success while subsequent calls return 409. Thus, if a business API needs to return the same logical result for every call, the application must translate verified duplicate conflicts into an "already processed" outcome.

Logic example:

~~~java
try {
    createDocument(event);
    return CreateResult.CREATED;
} catch (DuplicateDocumentException ex) {
    if (isSameEventAlreadyStored(event)) {
        return CreateResult.ALREADY_PROCESSED;
    }
    throw ex;
}
~~~

This snippet illustrates the idea; exact exception detection depends on your client and Spring Data version.

Do not treat every conflict as a successful duplicate. The same ID with a different event or different tenant could indicate a data error needing investigation.

## 13. `INDEX` with a Deterministic ID Can Also Be Idempotent, with Different Semantics

Sending the exact same full payload multiple times to the same ID with `INDEX` typically converges to the same final `_source`:

~~~http
PUT /products/_doc/tenant-42:P-1001
{
  "tenantId": "tenant-42",
  "productId": "P-1001",
  "name": "Wireless Keyboard",
  "status": "PUBLISHED"
}
~~~

Resending the same request does not create a new document. However, `INDEX` replaces the existing `_source`. If another writer updated the document in the meantime, an older request can overwrite newer data.

Example:

1. Event version 5 updates status to `PUBLISHED`.
2. Event version 6 updates name to `Wireless Keyboard Pro`.
3. Old event version 5 arrives late and runs `INDEX` with the full old source.
4. The newer name gets overwritten back to the old one.

Deterministic IDs prevent duplicate documents, yet they do not solve event ordering by themselves.

Choose operations according to data semantics:

- `CREATE`: accept only the initial creation.
- `INDEX`: write the full source representing the request's state.
- `UPDATE`: modify part of `_source` or run a script.
- Versioning/OCC: prevent stale writes from overwriting newer data based on version.

## 14. Controlling Write Ordering with Versions

If data can arrive out of order, use a monotonically increasing business version or optimistic concurrency control.

For example, each event carries a version:

~~~json
{
  "productId": "P-1001",
  "version": 42,
  "name": "Wireless Keyboard Pro"
}
~~~

Elasticsearch supports external versioning in the Index API. With `version_type=external`, a write only succeeds when the submitted version is strictly greater than the stored version:

~~~http
PUT /products/_doc/tenant-42:P-1001?version=42&version_type=external
{
  "tenantId": "tenant-42",
  "productId": "P-1001",
  "version": 42,
  "name": "Wireless Keyboard Pro"
}
~~~

If an event with version 41 arrives after version 42, Elasticsearch rejects the stale write.

A variant is `external_gte`, which accepts versions greater than or equal to the current version. Use it only when rewriting the same version is safe; two distinct payloads carrying the same version can overwrite each other.

Beyond external versions, Elasticsearch supports optimistic concurrency using `if_seq_no` and `if_primary_term`. This fits read-modify-write flows where the application reads a document and updates only if nothing modified it since that read.

Do not generate versions by incrementing at the consumer in message arrival order if messages can arrive out of order. Versions must reflect business order issued by a reliable data source.

## 15. `CREATE` Does Not Equal Exactly-Once Delivery

Message brokers typically provide at-least-once delivery. A message can be redelivered when a consumer finishes processing without committing the offset or when an acknowledgment is lost.

`CREATE` with a deterministic ID guarantees no two documents are created for the same ID, yet it does not make the entire system exactly-once.

Example consumer flow:

1. Receive event.
2. Create document in Elasticsearch successfully.
3. Process crashes before committing the offset.
4. Broker redelivers the event.
5. Consumer calls `CREATE` again and receives 409.

Only one document exists, yet the consumer must still handle the duplicate response and commit the offset per policy.

If the consumer performs additional side effects—such as sending emails, charging accounts, or publishing downstream messages—`CREATE` in Elasticsearch does not guarantee those side effects run only once. You need an idempotency key, transactional outbox, or deduplication in whichever system owns each side effect.

## 16. Using Event IDs as Idempotency Keys

For event ingestion, producers should supply a unique ID:

~~~json
{
  "eventId": "evt-2026-000184",
  "eventType": "PRODUCT_PUBLISHED",
  "occurredAt": "2026-11-13T10:00:00Z",
  "tenantId": "tenant-42",
  "productId": "P-1001"
}
~~~

You can use `eventId` as the document ID:

~~~java
eventDocument.setId(event.getEventId());
~~~

If the producer lacks an event ID, derive an idempotency key from immutable identifying attributes of the event. Never use the consumer's receipt timestamp, as each retry would generate a different timestamp.

If two legitimate independent events happen to carry identical payloads, hashing the payload alone can wrongly merge them. The ID must reflect the event's business identity, not merely coincidental payload equality.

## 17. Bulk Create with Elasticsearch Java API Client

When direct control over each `create` action is required, the Elasticsearch Java API Client provides the Bulk API.

Example with the typed client:

~~~java
import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch.core.BulkResponse;
import co.elastic.clients.elasticsearch.core.bulk.BulkOperation;

List<BulkOperation> operations = products.stream()
        .map(product -> BulkOperation.of(op -> op
                .create(c -> c
                        .index("products")
                        .id(product.getId())
                        .document(product)
                )
        ))
        .toList();

BulkResponse response = client.bulk(b -> b
        .operations(operations)
);
~~~

After sending, inspect the results:

~~~java
if (response.errors()) {
    response.items().forEach(item -> {
        if (item.error() != null) {
            System.err.println(
                    item.id() + ": " + item.error().reason()
            );
        }
    });
}
~~~

This uses the Java Client API directly. When calling the client directly, mapping, deserialization, and exception handling are managed by the client and application. When calling Spring Data's `ElasticsearchOperations.bulkIndex(... )`, Spring Data uses its own mapping metadata and converters to construct the request.

Do not mix operation types or request builders between legacy client generations and the modern Java API Client.

## 18. Recording Bulk Results in the Application

A batch ingestion job should produce a clear summary outcome:

~~~java
public record BulkIngestionReport(
        int submitted,
        int created,
        int duplicates,
        int retryableFailures,
        int permanentFailures
) {
}
~~~

When processing results, classify every item:

- Created: new document created.
- Duplicate: `create` returned conflict and payload/event was verified as the same operation.
- Retryable failure: transient failure eligible for retry.
- Permanent failure: bad data, mapping error, or insufficient permissions.
- Unknown: timeout or connection loss needing reconciliation by deterministic ID.

With Spring Data, bulk return types may be lists of indexed document metadata or exceptions depending on operation and version. If detailed per-item classification is required, verify whether the API exposes bulk response item metadata or use the Java API Client directly to inspect `BulkResponse.items()`.

Do not assume a result list containing only successful items always explains why missing items were skipped.

## 19. Bulk Requests Are Not Transactions

A bulk request reduces network overhead and executes multiple actions in one submission. It does not guarantee the entire batch succeeds or rolls back all actions if one fails.

Example:

~~~text
Item 1: CREATE succeeded
Item 2: CREATE succeeded
Item 3: 409 conflict
Item 4: 400 mapping error
Item 5: CREATE succeeded
~~~

After the request:

- Three documents may have been created.
- One item already existed.
- One item failed due to bad data.
- No automatic rollback happens for the successful items.

The application must track per-item state, or at least the error list, to retry and reconcile. For large batches, chunk batches appropriately and limit concurrent requests.

## 20. Designing Retries After Timeouts

Timeouts are tricky because the client cannot tell whether Elasticsearch processed the request.

With `CREATE` and a deterministic ID:

1. Send `create`.
2. Client times out.
3. Unclear whether the item was created.
4. Retry with the exact same ID and payload.
5. If the document does not exist, the retry creates it successfully.
6. If the document already exists, the retry gets 409.
7. The application verifies the existing document and classifies it as a duplicate.

With `INDEX` and a deterministic ID, retrying the same payload usually brings the document to the same `_source`, though it risks overwriting newer changes if multiple writers exist—requiring versions or OCC.

With an increment script:

~~~painless
ctx._source.stock += params.quantity;
~~~

Retrying the same request can add the quantity a second time. This script is not idempotent. You need event deduplication, persisted applied event IDs, or a redesigned data model to avoid double application.

Not every operation becomes idempotent merely because the document ID is deterministic.

## 21. Refresh and Read-After-Create Visibility

A successfully written document is not guaranteed to appear immediately in normal search queries. Elasticsearch refreshes make changes visible to search.

Bulk/index requests can configure an appropriate refresh policy, such as:

- `false` or default: do not force an immediate refresh.
- `wait_for`: wait for the next refresh to make data searchable.
- `true`: request an immediate refresh, which can add overhead.

Avoid immediate refresh per item in high-throughput ingestion. If you need to read a document right after `create`, use a GET by ID for real-time lookup or use a refresh policy suited to your requirements.

Distinguish:
- Write acknowledged: Elasticsearch confirmed the write operation.
- Search visible: the document appears in search after a refresh.
- Durable: data meets cluster replication/flush configuration and durability guarantees.

## 22. ID Generation Rules with Tenants, Versions, and Events

Some design patterns:

### Current State Document

~~~text
_id = tenantId + ":" + productId
~~~

Use when there is a single current document per product within a tenant.

### Event Log

~~~text
_id = eventId
~~~

Use when each event is a separate document requiring event-level deduplication.

### Periodic Snapshot

~~~text
_id = tenantId + ":" + productId + ":" + snapshotDate
~~~

Use when there is one snapshot per day or per period.

### Multi-Source Data

~~~text
_id = tenantId + ":" + sourceSystem + ":" + sourceRecordId
~~~

Use when multiple source systems can issue overlapping business keys.

Define ID generation in a shared utility or contract rather than letting each producer concatenate strings using different rules.

## 23. Common Pitfalls

### Generating a New UUID on Each Retry

Each retry gets a new ID and produces duplicate documents. Derive IDs from immutable business keys or event IDs.

### Using Product ID for an Event Log

Multiple events for the same product overwrite each other. Event documents need unique event IDs.

### Using `INDEX` When Create-Only Is Required

`INDEX` overwrites `_source` if the ID already exists. Use `CREATE` when existing documents must be rejected.

### Ignoring All 409 Errors

409 may be a legitimate duplicate, yet it can also be an ID collision or data conflict. Verify the payload or event identity before treating it as success.

### Retrying the Whole Bulk Request After One Item Fails

Some items already succeeded. Retrying the whole batch can trigger conflicts or unwanted overwrites. Classify and retry only the necessary items.

### Treating Bulk as a Transaction

Bulk exhibits partial success. Read per-item outcomes and persist processing state.

### Assuming Deterministic IDs Solve Event Ordering

Stable IDs stop duplicate documents, yet old events can still overwrite newer events under `INDEX`. Use external versioning or OCC when ordering matters.

### Assuming `retry_on_conflict` Prevents Duplicate Events

`retry_on_conflict` resolves version conflicts inside an update, not consumer redelivery of the same event. You still need idempotency keys/deduplication.

### Confusing `_id` with Business Key Fields

`_id` is Elasticsearch metadata; a business key inside `_source` is a data field. They may hold the same value, yet serve different roles.

### Assuming Write Success Means Instant Search Visibility

Refresh controls when documents appear in search. Do not sleep for fixed durations; use GET by ID, a refresh policy, or controlled synchronization.

## 24. Workflow for Safe Ingestion

When designing a data ingestion pipeline:

1. Decide whether each document represents a current entity or an event.
2. Pick a stable business key or event ID.
3. Canonicalize and generate deterministic IDs via a shared rule.
4. Decide between `CREATE` and `INDEX` semantics.
5. If stale writes must not overwrite newer data, add external versioning or OCC.
6. Build `IndexQuery` with the appropriate ID and operation type.
7. Send items or batches via `ElasticsearchOperations`/Bulk API.
8. Inspect per-item outcomes, not only overall request status.
9. Classify duplicates, conflicts, permanent errors, and transient errors.
10. Retry only retryable items with backoff.
11. For timeouts, retry with the exact same ID and logical payload, then reconcile.
12. Ensure increment scripts or other side effects have deduplication.
13. Choose a refresh policy matching read-after-write needs.
14. Emit logs/metrics for created, duplicate, failed, and retried counts.
15. Test redelivered messages, two concurrent workers, timeouts after server writes, and out-of-order events.

## References

- [Elasticsearch — Index API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-index_.html)
- [Elasticsearch — Create operation type](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-index_.html#operation-type)
- [Elasticsearch — Bulk API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-bulk.html)
- [Elasticsearch — Optimistic concurrency control](https://www.elastic.co/guide/en/elasticsearch/reference/current/optimistic-concurrency-control.html)
- [Elasticsearch — Refresh parameter](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-refresh.html)
- [Spring Data Elasticsearch — IndexQuery API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/query/IndexQuery.html)
- [Spring Data Elasticsearch — IndexQueryBuilder API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/query/IndexQueryBuilder.html)
- [Spring Data Elasticsearch — ElasticsearchOperations API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/ElasticsearchOperations.html)

## Conclusion

Deterministic IDs ensure every processing pass for the same entity or event targets the exact same document. `CREATE` guarantees creation only when the ID does not exist yet; `INDEX` writes or replaces `_source` at that ID. In Spring Data Elasticsearch, you can assign IDs via `@Id`/entities or `IndexQuery`, select `IndexQuery.OpType.CREATE`, and send batches with `bulkIndex(... )`. Bulk requests can partially succeed, so you must inspect every item, classify 409s, and retry transient failures under control. Deterministic IDs form the foundation of idempotency, yet they do not automatically solve event ordering, duplicate side effects, or counter-increment update scripts; those cases require versioning, OCC, or business-level deduplication.
