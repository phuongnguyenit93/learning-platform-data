# Bulk Index, Create, Update, and Delete

The Elasticsearch Bulk API lets you send multiple document operations in a single request. A single bulk request can contain index, create, update, and delete operations, reducing round trips between the application and the cluster when importing data or processing a large set of documents.

Spring Data Elasticsearch provides bulk APIs at the abstraction level such as `bulkIndex` and `bulkUpdate` through `ElasticsearchOperations`/`DocumentOperations`. For conditional deletes, you can use `DeleteQuery`. When you need to bulk delete by a list of IDs or mix create, index, update, and delete in the same request, the application can use the Elasticsearch Java API Client directly.

The key point to remember is that bulk only groups operations into one request. It does not create an ACID transaction across all documents: each item can succeed or fail independently. Therefore, ingestion code must check per-item errors, split batches to a reasonable size, retry selectively, and ensure operations can be safely re-executed.

## 1. What Problem Does the Bulk API Solve?

Suppose an application needs to write 10,000 products. If it issues one request per document, the application must perform thousands of network exchanges:

~~~text
Writing one document at a time:

Application -- index product 1 --> Elasticsearch
Application -- index product 2 --> Elasticsearch
Application -- index product 3 --> Elasticsearch
...
Application -- index product 10000 --> Elasticsearch
~~~

Bulk groups multiple operations together:

~~~text
Application
    |
    | one bulk request containing multiple actions
    v
Elasticsearch
    |
    +-- index product 1
    +-- index product 2
    +-- create product 3
    +-- update product 4
    +-- delete product 5
    +-- ...
~~~

Key benefits:

- Reduces network cost and HTTP overhead.
- Increases throughput when importing many documents.
- Allows combining multiple operation types in the same request.
- Enables controlling pipeline, refresh policy, routing, and timeout at the request level.
- Returns per-item results to identify which documents succeeded or failed.

Bulk is especially useful for data imports, projection synchronization, batch status updates, event processing, and scheduled jobs.

## 2. Four Operation Types in the Bulk API

The Bulk API supports four primary actions:

| Action | Meaning | Existing Document |
|---|---|---|
| index | Write a document; create new if absent | Replaces the document content for that ID |
| create | Create a new document only | Fails with a version conflict if the ID already exists |
| update | Partially update a document or run a script | Updates the existing document; upsert can be configured |
| delete | Delete a document by ID | Returns a not found result if the document does not exist per API semantics |

Two operations commonly confused are `index` and `create`:

- `index` is suitable when you want to write the current document state and allow replacing a document with the same ID.
- `create` is suitable when only non-existent IDs are allowed to be created; if the ID already exists, Elasticsearch returns a conflict error instead of overwriting.

`update` typically uses a partial document or script. `delete` only needs the action metadata line, with no source line following it in NDJSON.

## 3. NDJSON Structure of a Bulk Request

The Bulk API uses NDJSON (Newline Delimited JSON). Each action has a metadata line; `index`/`create`/`update` also have a payload line following it.

Example request containing all four action types:

~~~http
POST _bulk
{"index":{"_index":"products","_id":"p-100"}}
{"name":"Wireless Keyboard","price":1299000,"active":true}
{"create":{"_index":"products","_id":"p-101"}}
{"name":"Ergonomic Mouse","price":599000,"active":true}
{"update":{"_index":"products","_id":"p-102","retry_on_conflict":3}}
{"doc":{"price":1499000,"active":true}}
{"delete":{"_index":"products","_id":"p-103"}}
~~~

Rules:

- Each action starts with a JSON metadata line.
- `index` and `create` require a JSON document line immediately after the action.
- `update` requires a JSON line describing the partial document, script, or upsert.
- `delete` has no following payload line.
- Lines must be separated by newlines.
- The request must end with a final trailing newline.
- The request `Content-Type` is `application/x-ndjson`.

When sending via curl, you can use an NDJSON file:

~~~bash
curl -X POST "http://localhost:9200/_bulk" \
  -H "Content-Type: application/x-ndjson" \
  --data-binary "@products-bulk.ndjson"
~~~

Do not use `application/json` for an NDJSON body and do not serialize all actions into a JSON array. The Bulk API requires the exact line-by-line format.

## 4. Distinguishing `index`, `create`, `update`, and `delete`

### 4.1. Index: create new or replace

Example:

~~~http
POST products/_bulk
{"index":{"_id":"p-100"}}
{"name":"Wireless Keyboard","price":1299000,"active":true}
~~~

If `p-100` does not exist yet, the document is created. If it already exists, the `_source` content is replaced by the submitted document. Fields omitted from the new payload may disappear from the document.

Therefore, `index` is suitable when the application holds the complete state of the document.

### 4.2. Create: only create if the ID does not exist

~~~http
POST products/_bulk
{"create":{"_id":"p-101"}}
{"name":"Ergonomic Mouse","price":599000,"active":true}
~~~

If `p-101` already exists, the `create` action fails with HTTP status 409 for that item. Other actions in the bulk request can still proceed.

`create` is useful when importing new data and wanting to detect duplicate IDs rather than silently overwriting. It is also the appropriate choice for append-only streams, such as certain cases of writing to a data stream.

### 4.3. Update: change part of a document

~~~http
POST products/_bulk
{"update":{"_id":"p-100"}}
{"doc":{"price":1399000}}
~~~

Only the `price` field is changed; other fields are preserved. If the document does not exist, `update` normally fails unless upsert is configured.

`update` can use a script:

~~~http
POST products/_bulk
{"update":{"_id":"p-100","retry_on_conflict":3}}
{"script":{"source":"ctx._source.stock -= params.quantity","params":{"quantity":2}}}
~~~

Scripts are appropriate when the change depends on the document's current state. Idempotency must be controlled: re-running a script that decrements stock could decrement it an extra time.

### 4.4. Delete: remove a document by ID

~~~http
POST products/_bulk
{"delete":{"_id":"p-103"}}
~~~

`delete` only needs the metadata line. When the request specifies the index in the URL, the action can omit `_index` in metadata. When using the general `_bulk` endpoint or mixing multiple indices, specify `_index` explicitly for each action.

## 5. Bulk APIs in Spring Data Elasticsearch

In current Spring Data Elasticsearch, the bulk operations on `DocumentOperations` include the main methods:

| Method | Input | Result |
|---|---|---|
| `bulkIndex(List<IndexQuery>, Class or IndexCoordinates)` | List of `IndexQuery` | List of `IndexedObjectInformation` |
| `bulkIndex(List<IndexQuery>, BulkOptions, Class or IndexCoordinates)` | List of queries and options | List of `IndexedObjectInformation` |
| `bulkUpdate(List<UpdateQuery>, Class or IndexCoordinates)` | List of `UpdateQuery` | `void` |
| `bulkUpdate(List<UpdateQuery>, BulkOptions, IndexCoordinates)` | List of queries and options | `void` |
| `delete(String id, IndexCoordinates)` | Single document ID | Deleted ID |
| `delete(DeleteQuery, Class, IndexCoordinates)` | Query identifying the document set | `ByQueryResponse` |

Note on delete: `DocumentOperations` does not provide a public method named `bulkDelete(List<...>)` analogous to `bulkIndex`/`bulkUpdate`. For multiple known IDs, use the Elasticsearch Java API Client `BulkRequest` or the REST Bulk API to send delete actions. For query criteria, use `DeleteQuery`; Elasticsearch executes this via the delete-by-query mechanism.

If you need to mix `index`, `create`, `update`, and `delete` in the same bulk request, the Elasticsearch Java API Client is the more direct abstraction. Do not invent a class named `BulkOperations` and assume Spring Data Elasticsearch provides that exact API out of the box.

## 6. Preparing the Entity and Mapping

Example using the `products` index:

~~~java
package com.example.catalog.domain;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Long)
    private Long price;

    @Field(type = FieldType.Boolean)
    private Boolean active;

    public Product() {
    }

    public Product(String id, String name, String category, Long price, Boolean active) {
        this.id = id;
        this.name = name;
        this.category = category;
        this.price = price;
        this.active = active;
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getCategory() {
        return category;
    }

    public Long getPrice() {
        return price;
    }

    public Boolean getActive() {
        return active;
    }
}
~~~

Bulk does not bypass mapping. If one item sends a string to a `long` field or has a malformed object structure, only that item may fail with a parsing/mapping error while other valid items are still written.

Before importing large data, create the index and proper mapping:

~~~http
PUT products
{
  "mappings": {
    "properties": {
      "name": {"type": "text"},
      "category": {"type": "keyword"},
      "price": {"type": "long"},
      "active": {"type": "boolean"}
    }
  }
}
~~~

Verify the mapping with `GET products/_mapping`. If new data contains fields or types incompatible with the mapping, fix the schema or transform the data before sending the bulk request.

## 7. Bulk Index with `ElasticsearchOperations`

Spring Data represents an index action using `IndexQuery`. Each query can carry an ID, an object or JSON source, routing, version, sequence number/primary term, and operation type.

Example creating a list of `IndexQuery`:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.IndexQuery;
import org.springframework.data.elasticsearch.core.query.IndexedObjectInformation;
import org.springframework.data.elasticsearch.core.query.BulkOptions;

public List<IndexedObjectInformation> indexProducts(
        ElasticsearchOperations operations,
        List<Product> products) {

    List<IndexQuery> queries = products.stream()
            .map(product -> IndexQuery.builder()
                    .withId(product.getId())
                    .withObject(product)
                    .build())
            .toList();

    return operations.bulkIndex(
            queries,
            BulkOptions.defaultOptions(),
            IndexCoordinates.of("products"));
}
~~~

`IndexQueryBuilder.withObject` accepts a Java object. Spring Data uses `ElasticsearchConverter` to convert the object to JSON according to mapping metadata. If you need to send pre-built JSON source, you can use `withSource` instead of `withObject`.

### 7.1. Choosing `index` or `create` with `OpType`

`IndexQuery.OpType` has two values:

- `INDEX`: create a new document or replace the document by ID.
- `CREATE`: only create if the ID does not exist yet.

Example import allowing creation only:

~~~java
List<IndexQuery> createQueries = products.stream()
        .map(product -> IndexQuery.builder()
                .withId(product.getId())
                .withObject(product)
                .withOpType(IndexQuery.OpType.CREATE)
                .build())
        .toList();

List<IndexedObjectInformation> created = operations.bulkIndex(
        createQueries,
        BulkOptions.defaultOptions(),
        IndexCoordinates.of("products"));
~~~

If the ID already exists, the corresponding create item fails. Spring Data reports bulk errors via `BulkFailureException` and provides information on the failed documents. Do not automatically switch `CREATE` to `INDEX` upon encountering a conflict if business rules forbid overwriting.

### 7.2. When to Use `bulkIndex` vs. `saveAll`?

Repository `saveAll` is suitable for saving an iterable of entities through the repository abstraction. `bulkIndex` is suitable when you need control over `IndexQuery`, operation type, routing, version, or `BulkOptions`.

Choose based on your needs:

| Need | Approach |
|---|---|
| Save a single entity | `repository.save` or `operations.save` |
| Save a simple group of entities | `repository.saveAll` or `operations.save(Iterable)` |
| Bulk with explicit `CREATE`/`INDEX` | `bulkIndex` with `IndexQuery.OpType` |
| Per-item routing/version | `IndexQuery` with the corresponding metadata |
| Need `BulkOptions` such as pipeline or refresh policy | `bulkIndex` with `BulkOptions` |
| Mix index/create/update/delete in one request | Elasticsearch Java API Client `BulkRequest` |

Do not assume every `saveAll` overload chunks batches the same way or shares the same options as `bulkIndex`. When specific bulk behavior is required, use the explicit bulk API.

## 8. Bulk Update with `UpdateQuery`

`UpdateQuery` represents an update request. It can contain:

- A document ID or a `Query` for update-by-query.
- A partial document.
- A Painless script and params.
- An upsert document.
- Routing.
- `if_seq_no` and `if_primary_term`.
- `retry_on_conflict`.
- Refresh policy and related options.

Example updating prices for multiple products:

~~~java
import java.util.List;
import java.util.Map;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.document.Document;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.BulkOptions;
import org.springframework.data.elasticsearch.core.query.UpdateQuery;

public void updatePrices(
        ElasticsearchOperations operations,
        Map<String, Long> priceByProductId) {

    List<UpdateQuery> updates = priceByProductId.entrySet().stream()
            .map(entry -> UpdateQuery.builder(entry.getKey())
                    .withDocument(Document.from(Map.of(
                            "price", entry.getValue())))
                    .build())
            .toList();

    operations.bulkUpdate(
            updates,
            BulkOptions.defaultOptions(),
            IndexCoordinates.of("products"));
}
~~~

Each `UpdateQuery` has its own ID and partial document. Fields omitted from the partial document are preserved. If a document does not exist, that update item normally fails unless upsert is configured.

### 8.1. Partial Document and Script Update

A partial document is appropriate when the application already knows the new values:

~~~java
UpdateQuery update = UpdateQuery.builder("p-100")
        .withDocument(Document.from(Map.of(
                "price", 1399000L,
                "active", true)))
        .build();
~~~

A script is appropriate when the change depends on the current values in the document:

~~~java
UpdateQuery update = UpdateQuery.builder("p-100")
        .withScript("ctx._source.stock += params.amount")
        .withParams(Map.of("amount", 10))
        .build();
~~~

Scripts execute on Elasticsearch. Pass data through `params` instead of concatenating strings into the script. This separates script code from data and avoids generating a distinct script source for every value.

### 8.2. Upsert

If the document might not exist yet, you can configure the partial document as an upsert:

~~~java
UpdateQuery update = UpdateQuery.builder("p-200")
        .withDocument(Document.from(Map.of(
                "name", "Vertical Mouse",
                "price", 799000L)))
        .withDocAsUpsert(true)
        .build();
~~~

`doc_as_upsert` means that if the document does not exist yet, the partial document is used to create a new document. Ensure the partial document contains all required fields per mapping and business rules. If a new document needs additional fields, use `withUpsert(Document)` to supply a full source.

### 8.3. Retrying on Version Conflict

`UpdateQuery` supports `withRetryOnConflict`:

~~~java
UpdateQuery update = UpdateQuery.builder("p-100")
        .withDocument(Document.from(Map.of("stock", 25)))
        .withRetryOnConflict(3)
        .build();
~~~

Elasticsearch can retry the update on a version conflict. Retrying is appropriate for state-assignment operations or scripts designed to run safely multiple times. For addition/subtraction, understand the semantics of the script and retries to avoid incorrect updates caused by duplicated events.

If you need optimistic concurrency against a previously read version, use `if_seq_no` and `if_primary_term`. When the document has changed, the update conflicts so the application can re-read and decide the next step.

### 8.4. Bulk Update Is Not Update-by-Query

`bulkUpdate` takes a list of `UpdateQuery`, typically each bound to an individual ID and update body.

Update-by-query takes a query identifying a set of documents and a shared script or partial update applied to matching documents. In Spring Data, you can use `UpdateQuery.builder(query)` and call `operations.updateByQuery(...)`.

Example update-by-query:

~~~java
CriteriaQuery selection = new CriteriaQuery(
        Criteria.where("category").is("accessories"));

UpdateQuery updateByQuery = UpdateQuery.builder(selection)
        .withScript("ctx._source.active = params.active")
        .withParams(Map.of("active", false))
        .withBatchSize(500)
        .build();

ByQueryResponse response = operations.updateByQuery(
        updateByQuery,
        IndexCoordinates.of("products"));
~~~

Choose `bulkUpdate` when you already know each ID and its update value. Choose `updateByQuery` when Elasticsearch can locate documents by criteria and apply the same change.

## 9. Deleting a Single Document

Spring Data Elasticsearch provides delete by ID:

~~~java
String deletedId = operations.delete(
        "p-100",
        IndexCoordinates.of("products"));
~~~

Or delete through a repository:

~~~java
productRepository.deleteById("p-100");
~~~

This is a single-document operation. If you have many IDs and want to group them into a single bulk request, use the Bulk API through the Elasticsearch Java API Client.

## 10. Conditional Delete with `DeleteQuery`

`DeleteQuery` represents a deletion condition. Spring Data translates this operation to the Elasticsearch Delete By Query API:

~~~java
import org.springframework.data.elasticsearch.core.query.ByQueryResponse;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.DeleteQuery;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

CriteriaQuery criteriaQuery = new CriteriaQuery(
        Criteria.where("active").is(false));

DeleteQuery deleteQuery = DeleteQuery.builder(criteriaQuery).build();

ByQueryResponse response = operations.delete(
        deleteQuery,
        Product.class,
        IndexCoordinates.of("products"));

long deletedCount = response.getDeleted();
~~~

Delete By Query is suitable when you need to delete all documents matching a condition, such as removing expired temporary data or projections belonging to a tenant removed under retention policy.

The `ByQueryResponse` provides:

- `getTotal()`: number of documents processed.
- `getDeleted()`: number of documents successfully deleted.
- `getBatches()`: number of scroll batches processed.
- `getVersionConflicts()`: number of version conflicts.
- `getFailures()`: failures in internal bulk operations.
- `getSearchFailures()`: failures during the document search phase.
- `getTimedOut()`: whether any sub-request timed out.
- `getTook()`: total execution time in milliseconds.

Delete By Query is not an atomic operation across the entire set of documents. While it runs, documents may be updated or deleted by another writer; inspect the response and handle conflicts/failures according to business rules.

## 11. Bulk Delete by a List of IDs

In the current API, `DocumentOperations` does not have a public `bulkDelete(List<String>)`. If you need to delete many IDs in a single request, use the Elasticsearch Java API Client.

Example:

~~~java
import java.util.List;

import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch.core.BulkRequest;
import co.elastic.clients.elasticsearch.core.BulkResponse;
import co.elastic.clients.elasticsearch.core.bulk.BulkResponseItem;

public void deleteProducts(
        ElasticsearchClient client,
        List<String> productIds) throws IOException {

    BulkRequest.Builder request = new BulkRequest.Builder();

    for (String id : productIds) {
        request.operations(operation -> operation
                .delete(delete -> delete
                        .index("products")
                        .id(id)));
    }

    BulkResponse response = client.bulk(request.build());

    if (response.errors()) {
        for (BulkResponseItem item : response.items()) {
            if (item.error() != null) {
                log.warn(
                        "Delete failed: index={}, id={}, status={}, reason={}",
                        item.index(),
                        item.id(),
                        item.status(),
                        item.error().reason());
            }
        }
    }
}
~~~

This example uses the Elasticsearch Java API Client configured in the application. With Spring Boot, the client may be auto-configured depending on dependencies and settings; reuse the shared client bean used by Spring Data rather than creating a separate connection.

`BulkRequest` can contain different types of `BulkOperation`. That allows combining `create`, `index`, `update`, and `delete` in the same request when the use case requires it. If sticking to Spring Data abstractions, use `bulkIndex`/`bulkUpdate` for the two directly supported groups and the native client for bulk delete by ID.

## 12. Combining Multiple Actions in One Bulk Request

NDJSON can mix actions in order:

~~~http
POST _bulk
{"create":{"_index":"products","_id":"p-201"}}
{"name":"USB Hub","price":299000,"active":true}
{"index":{"_index":"products","_id":"p-202"}}
{"name":"Laptop Stand","price":499000,"active":true}
{"update":{"_index":"products","_id":"p-203","retry_on_conflict":3}}
{"doc":{"price":549000}}
{"delete":{"_index":"products","_id":"p-204"}}
~~~

The Bulk Java Client represents each action with a variant of `BulkOperation`:

- `operation.create(...)`
- `operation.index(...)`
- `operation.update(...)`
- `operation.delete(...)`

Each item can target a specific index. This is suitable when an ingestion flow needs to write to multiple indices or perform different action types within the same batch.

However, mixing multiple action types makes inspection and retrying more complex. Maintain correlation between each action and its source data, such as storing index, ID, operation type, and event ID for each item.

## 13. `BulkOptions`

`BulkOptions` provides shared options for `bulkIndex` and `bulkUpdate`:

| Option | Meaning |
|---|---|
| `withRefreshPolicy` | Refresh policy after the bulk request |
| `withTimeout` | Wait timeout for request conditions |
| `withWaitForActiveShards` | Number of shard copies that must be active before proceeding |
| `withPipeline` | Ingest pipeline applied to the request |
| `withRoutingId` | Shared routing ID for the request |

Example:

~~~java
import java.time.Duration;

import org.springframework.data.elasticsearch.core.RefreshPolicy;
import org.springframework.data.elasticsearch.core.query.BulkOptions;

BulkOptions options = BulkOptions.builder()
        .withRefreshPolicy(RefreshPolicy.NONE)
        .withTimeout(Duration.ofSeconds(60))
        .withWaitForActiveShards(ActiveShardCount.ONE)
        .withPipeline("normalize-product")
        .build();
~~~

Then pass `options` to `bulkIndex` or `bulkUpdate`:

~~~java
operations.bulkIndex(
        indexQueries,
        options,
        IndexCoordinates.of("products"));
~~~

`BulkOptions` is not where per-document content is configured. Information such as ID, object, per-item routing, or version belongs on the respective `IndexQuery`/`UpdateQuery`.

### 13.1. Refresh Policy

Refresh determines when newly written data becomes visible to search:

| Policy | Behavior |
|---|---|
| `NONE` | Do not request a separate refresh after the request |
| `IMMEDIATE` | Immediately refresh affected shards after the request |
| `WAIT_UNTIL` | Wait for the next refresh to make data visible |

For large imports, `IMMEDIATE` is usually avoided per batch because overly frequent refreshes lower indexing throughput. If the application needs search to see the data after the import finishes, you can choose `WAIT_UNTIL` or explicitly refresh once after the write phase.

Refresh only affects search visibility. It does not turn bulk into a transaction and does not guarantee that other indices have been updated.

### 13.2. Ingest Pipeline

`BulkOptions` can select an ingest pipeline:

~~~java
BulkOptions options = BulkOptions.builder()
        .withPipeline("normalize-product")
        .build();
~~~

A pipeline can normalize data, add derived fields, or process timestamps before the document is indexed. If the pipeline modifies `_source`, verify the post-ingest output and ensure the pipeline is applied consistently across import, update, and other write paths.

### 13.3. Routing

If an index uses custom routing, the operation must supply the right routing value so the document lands on the right shard. Routing can be set on each `IndexQuery` or `UpdateQuery`. `BulkOptions.withRoutingId` uses a shared routing ID when all operations in the request share the same value.

If a batch contains multiple tenants or multiple routing keys, attach routing individually per item instead of using a single request-wide routing ID. When reading, updating, or deleting, the matching routing must also be passed.

## 14. Inspecting Results and `BulkFailureException`

A bulk request can return a successful request-level HTTP status while still having failed items. Therefore, you must not only check whether the request threw an exception or whether the HTTP status is 200.

In an Elasticsearch Bulk API response:

- `errors = false` means every item completed successfully.
- `errors = true` means at least one item failed.
- `items` contains results in the exact order of the submitted actions.
- Each item has `status`, `result`, or `error` depending on the outcome.

Abbreviated response example:

~~~json
{
  "errors": true,
  "items": [
    {
      "index": {
        "_index": "products",
        "_id": "p-201",
        "status": 201,
        "result": "created"
      }
    },
    {
      "create": {
        "_index": "products",
        "_id": "p-202",
        "status": 409,
        "error": {
          "type": "version_conflict_engine_exception",
          "reason": "document already exists"
        }
      }
    }
  ]
}
~~~

Spring Data `bulkIndex` and `bulkUpdate` can throw `BulkFailureException` when operations fail. The exception provides `getFailedDocuments()`, a map from document ID to `FailureDetails` containing `status` and `errorMessage`.

Example:

~~~java
import org.springframework.data.elasticsearch.BulkFailureException;

try {
    operations.bulkIndex(
            indexQueries,
            BulkOptions.defaultOptions(),
            IndexCoordinates.of("products"));
} catch (BulkFailureException exception) {
    exception.getFailedDocuments().forEach((id, failure) -> {
        log.warn(
                "Bulk item failed: id={}, status={}, error={}",
                id,
                failure.status(),
                failure.errorMessage());
    });

    throw exception;
}
~~~

Successful items are not automatically rolled back when another item fails. The exception is a signal for the application to record failures and recover, not proof that the entire batch failed to write.

## 15. Error Classification and Retry

Not every error should be retried:

| Error | Example Status | Handling Approach |
|---|---:|---|
| `create` ID already exists | 409 | Check for duplicate; do not retry blindly |
| Version conflict | 409 | Read newer version or retry according to concurrency policy |
| Mapping/parsing error | 400 | Fix data or mapping; retrying the same payload will not resolve it |
| Rejected execution / overload | 429 | Retry with backoff and reduce send rate |
| Service unavailable / transient error | 5xx | Retry with limits after checking cluster health |
| Authentication/authorization | 401/403 | Fix credentials or permissions |
| Document missing on update | 404 | Check document lifecycle; use upsert if business logic allows |

### 15.1. Selective Retry

With a bulk response from the Java client, put only transiently failed items into the retry batch. Do not resend all actions because some items may have already succeeded.

With Spring Data's `BulkFailureException`, use the `failedDocuments` map to identify failed IDs and errors. If you need the full operation type or original payload, the application should maintain a correlation map from ID to the input command/event.

### 15.2. Exponential Backoff

When the cluster returns 429 or transient errors, immediate continuous retries can worsen the overload. Use exponential backoff with jitter:

~~~text
delay = min(maxDelay, baseDelay * 2^attempt) + randomJitter
~~~

Illustrative configuration example:

| Attempt | Base Delay |
|---:|---:|
| 1 | 200 ms |
| 2 | 400 ms |
| 3 | 800 ms |
| 4 | 1,600 ms |
| 5 | 3,200 ms |

Set limits on retry count and total retry duration. Once thresholds are exceeded, write the item to a dead-letter queue or error table so it can be reprocessed later.

### 15.3. Idempotency

Retries are safest when actions can be re-executed without corrupting state:

- `index` with the same ID and same source generally converges to the same final state.
- `create` with the same ID a second time will conflict; distinguish legitimate duplicates from errors.
- Partial `update` assigning a fixed value is usually easier to retry than an increment/decrement script.
- `delete` with the same ID may encounter `not_found` on a subsequent run; decide whether that counts as success by final state or an error to record.
- Counter-increment scripts are not idempotent if an event is replayed.

For event-driven ingestion, include an event ID/version and record which items have completed. Never mark an entire batch successful when a subset of items failed.

## 16. Splitting Batches by Size

Do not load millions of documents into a single `List` and send them in one bulk request. Oversized batches can cause:

- Increased heap usage in the application.
- Large request bodies, increasing network pressure.
- The receiving node having to buffer large payloads and process many actions.
- Long processing times, increasing timeout probability.
- Harder identification and selective retry of subsets when errors occur.

Batches that are too small increase overhead and lower throughput. Benchmark with production-like data.

### 16.1. Splitting by Item Count

Example batch processing:

~~~java
int batchSize = 500;

for (int start = 0; start < products.size(); start += batchSize) {
    int end = Math.min(start + batchSize, products.size());
    List<Product> batch = products.subList(start, end);

    indexBatch(operations, batch);
}
~~~

500 is only an illustrative value. Depending on JSON size, field count, pipeline, shard count, and cluster load, the appropriate batch size can differ significantly.

### 16.2. Monitoring Byte Size

Item count does not fully reflect request size. 500 small documents can be lighter than 20 documents with large content.

Monitor:

- Number of items per batch.
- NDJSON size in bytes.
- Request duration.
- Failed item count and error types.
- Cluster CPU, heap, indexing pressure, and thread pools.

Increase batch size gradually, measure throughput and latency, and stop when throughput plateaus or the cluster shows signs of overload.

### 16.3. Limiting Concurrency

Sending multiple bulk requests in parallel can increase throughput up to a point. Too many concurrent requests can drive up indexing pressure and queues.

Limit the number of in-flight requests. With producer/consumer pipelines, apply backpressure so the producer does not push data faster than Elasticsearch can process it.

## 17. `BulkIngester` for Continuous Ingestion Streams

If the application continuously generates actions rather than having a pre-built batch list, the Elasticsearch Java API Client provides `BulkIngester`. This component automatically accumulates operations, sends a bulk request when reaching an operation count/size threshold or flush interval, and can limit concurrent requests.

Skeleton example:

~~~java
import java.util.concurrent.TimeUnit;

import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch._helpers.bulk.BulkIngester;

BulkIngester<Void> ingester = BulkIngester.of(builder -> builder
        .client(client)
        .maxOperations(500)
        .flushInterval(1, TimeUnit.SECONDS));

for (Product product : productStream) {
    ingester.add(operation -> operation
            .index(index -> index
                    .index("products")
                    .id(product.getId())
                    .document(product)));
}

ingester.close();
~~~

`close()` must be called to flush remaining pending operations and release resources. In long-running applications, manage `BulkIngester`'s lifecycle along with the worker/service lifecycle.

`BulkIngester` can accept a listener to observe the results of each bulk execution and contexts attached to operations. Use the listener to record errors by ID/event and feed a retry queue. Do not just log total request counts and ignore item failures.

`BulkIngester` is a utility of the Elasticsearch Java API Client, not a method on `ElasticsearchOperations`. If a project only processes finite batches, Spring Data's `bulkIndex`/`bulkUpdate` is often simpler.

## 18. Refresh, Shards, and Indexing Performance

### 18.1. Avoid Refreshing After Every Document

Frequent refreshes create many small segments and increase merge cost. For large imports:

1. Send multiple batches with `RefreshPolicy.NONE`.
2. Monitor results and errors.
3. Upon completion, refresh the index once if search needs to see the data immediately.

If the index has a suitable refresh interval, automatic refresh can handle visibility.

### 18.2. `wait_for_active_shards`

`BulkOptions` lets you configure how many shard copies must be active before a request proceeds. This setting governs write availability preconditions, not how many replicas the application itself writes to.

Choose a policy aligned with durability/availability requirements. Waiting for all shard copies can stall requests if a replica is temporarily unavailable.

### 18.3. Pipeline and Mapping

Ingest pipelines can normalize data before indexing. The mapping must align with pipeline output. If a pipeline adds new fields or changes types, verify the index mapping and test with representative payloads.

### 18.4. Routing and Shard Distribution

Custom routing can reduce fan-out when queries always include a routing key, but uneven routing can create a hot shard. A bulk batch whose routing keys concentrate on one shard can overload that shard.

When using routing, ensure the same document is always written, updated, retrieved, and deleted with the matching routing value.

## 19. Bulk on Aliases and Data Streams

Bulk actions can target an index, alias, or data stream. When using an alias as the write target, verify that the alias has an explicit write index if it points to multiple indices.

Data streams have append-oriented semantics, and the Bulk API only supports the `create` action for data streams. Do not send `update` or `delete` actions directly to a data stream as you would for a regular index. If old documents must be modified or deleted, target the backing index with an appropriate process while accounting for the data stream lifecycle.

In production imports, `require_alias` can force requests to write through an alias instead of accidentally creating a new index due to a typo. This is useful when the application uses aliases for index versioning.

## 20. Concurrency Control and Stale Data

Bulk requests can run concurrently with other requests. If two writers update the same document, the outcome depends on write order and concurrency control.

Common mechanisms:

- `if_seq_no` and `if_primary_term` to update only if the document has not changed since it was read.
- `retry_on_conflict` on the Update API when Elasticsearch should retry the update after a conflict.
- Business version in the document/event to ignore stale events.
- Idempotent commands so retries do not produce incorrect state.

Do not use a bulk batch to overwrite the entire document if each producer only owns a subset of fields. Use partial updates or a single projection writer with clear ownership.

If a bulk request contains the same ID multiple times, the order of actions in the request can affect the final state. Deduplicate IDs within a batch or establish the intended order before sending.

## 21. `BulkFailureException` and Java Client Responses

There are two ways to read errors depending on the API:

| API | How Errors Are Reported |
|---|---|
| Spring Data `bulkIndex`/`bulkUpdate` | `BulkFailureException.getFailedDocuments()` |
| Elasticsearch Java API Client `BulkRequest` | `BulkResponse.errors()` and `BulkResponse.items()` |
| `DeleteQuery` / `updateByQuery` | `ByQueryResponse.getFailures()`, `getSearchFailures()`, `getVersionConflicts()`, `getTimedOut()` |

When using the Java client, `response.errors()` must be checked even when `client.bulk(...)` does not throw an exception. For each item, inspect `error()` and `status()`.

When using Spring Data, `BulkFailureException` is a runtime exception. Catch it at a layer with enough context to persist failed items or enqueue them for retry. Do not swallow the exception and continue as if the batch fully succeeded.

## 22. Handling Errors Per Item

A practical strategy:

1. Create a command per item and retain its ID, index, action type, and payload.
2. Send the batch.
3. Read the response or `BulkFailureException`.
4. Match errors back to original commands by ID/correlation.
5. Retry transient errors such as 429 or certain 5xx statuses.
6. Route data/mapping errors to a DLQ for payload fixes.
7. Resolve conflicts according to business rules.
8. Mark the batch complete once every item has succeeded or been moved to a tracked error flow.

Example error record structure:

~~~json
{
  "batchId": "import-2026-11-13-01",
  "itemId": "p-202",
  "index": "products",
  "operation": "create",
  "attempt": 2,
  "status": 400,
  "error": "mapper_parsing_exception",
  "payloadRef": "object-storage://imports/p-202.json"
}
~~~

For large payloads, the DLQ can store a reference to object storage rather than duplicating the entire JSON in the message.

## 23. Bulk Is Not a Transaction

A bulk request can produce mixed results:

~~~text
Action 1: INDEX  -> SUCCESS
Action 2: CREATE -> CONFLICT
Action 3: UPDATE -> SUCCESS
Action 4: DELETE -> NOT FOUND
Action 5: INDEX  -> MAPPING ERROR
~~~

Elasticsearch does not roll back actions 1 and 3 because actions 2 and 5 failed. If business logic requires a group of changes to all succeed or all fail together, bulk does not satisfy that transaction requirement.

For projections or search indices, systems typically rely on eventual consistency, idempotency, retries, and reconciliation. If source data lives in a relational database, keep business transactions in the database and use outbox/CDC to synchronize Elasticsearch.

## 24. When to Use `bulkIndex`, `bulkUpdate`, `DeleteQuery`, or Native Bulk?

| Scenario | Recommended API |
|---|---|
| Import many complete documents | `bulkIndex` |
| Create new only and reject duplicate IDs | `bulkIndex` + `OpType.CREATE` |
| Write full state, allowing replacement for the same ID | `bulkIndex` + `OpType.INDEX` |
| Each document has different partial fields | `bulkUpdate` |
| Many documents receive the same script by query | `updateByQuery` |
| Delete a single document | `delete(id, index)` or `repository.deleteById` |
| Delete all documents matching a condition | `delete(DeleteQuery, ...)` |
| Delete many known IDs in one request | Java API Client `BulkRequest` with delete actions |
| Mix create/index/update/delete in one request | Java API Client `BulkRequest` |
| Continuous streaming ingest with auto-batching | `BulkIngester` |

Do not choose `updateByQuery` just because there are many documents. If each document has its own update value, `bulkUpdate` with a list of IDs is usually better suited. Conversely, if all matching documents receive the same change, `updateByQuery` or `DeleteQuery` avoids pulling the list of IDs into the application.

## 25. Testing Bulk Operations

An integration test against a real Elasticsearch instance or Testcontainers should verify:

- `index` creates a new document.
- `index` with the same ID replaces the existing document.
- `create` with the same ID a second time returns a conflict.
- `update` changes only the submitted fields.
- `update` on a non-existent document fails when upsert is disabled.
- `update` with `doc_as_upsert` creates the document when missing.
- `delete` by ID removes the right document.
- `DeleteQuery` deletes only documents matching the condition.
- One item with a mapping error does not prevent other valid items from being written.
- Bulk response has `errors=true` when one item fails.
- `BulkFailureException` contains failed IDs and error details.
- Routing is applied correctly when the index uses custom routing.
- Refresh policy matches how the test reads back data.

### 25.1. Testing `create` and `index` Semantics

Logic test example:

~~~java
@Test
void createDoesNotOverwriteExistingDocument() {
    operations.save(new Product(
            "p-100", "Original Keyboard", "accessories", 1000L, true),
            IndexCoordinates.of("products"));

    IndexQuery create = IndexQuery.builder()
            .withId("p-100")
            .withObject(new Product(
                    "p-100", "New Keyboard", "accessories", 2000L, true))
            .withOpType(IndexQuery.OpType.CREATE)
            .build();

    assertThatThrownBy(() -> operations.bulkIndex(
            List.of(create),
            BulkOptions.defaultOptions(),
            IndexCoordinates.of("products")))
            .isInstanceOf(BulkFailureException.class);
}
~~~

This is an integration test example; index setup, refresh, and cleanup must be added according to your project's Testcontainers configuration.

### 25.2. Testing Partial Update

Create a document with multiple fields, run an `UpdateQuery` that only changes `price`, then read it back by ID and verify `name`/`category` remain intact. This test catches accidental use of `index`/`save` when partial update was intended.

### 25.3. Testing Partial Failure

Send a batch containing:

- One valid document.
- One document with a wrong field type.
- One `create` with an already-existing ID.

Verify that the valid document was written and that the failed items are reported in `BulkFailureException` or `BulkResponse`. Do not assert only overall request success or failure.

## 26. Common Pitfalls

### Thinking HTTP 200 Means Every Item Succeeded

A bulk response can return HTTP 200 with `errors=true`. Inspect `errors` and each item.

### Using `index` When Only `create` Is Intended

`index` replaces a document with the same ID. Use `OpType.CREATE` when existing IDs must be rejected.

### Using `create` When Upsert Is Needed

`create` does not update existing documents. If you need create-or-replace, use `index`; if you need partial update/upsert, use `update` with upsert configured.

### Sending a Partial Entity Missing Fields

Bulk `index` replaces the document by ID. If the entity lacks the full source, old fields can be lost. Use `bulkUpdate` for partial changes.

### Sending an Oversized Batch

Large requests increase heap usage, indexing pressure, and timeout risk. Split batches by both item count and bytes.

### Retrying the Entire Bulk Request When One Item Fails

Successful items may be re-executed. With `create` this can conflict; with incrementing scripts this can update twice. Retry only the failed items and design idempotent actions.

### Not Preserving Correlation Between Items and Payloads

When errors occur, the application cannot tell which document needs fixing. Keep ID, action type, and event/batch ID for correlation.

### Using `IMMEDIATE` Refresh for Every Batch

Frequent refreshes degrade indexing throughput. Only refresh when search visibility requires it.

### Inconsistent Routing

Documents written with routing may not be found by update/delete calls lacking matching routing. Store routing in the command and pass it consistently.

### Assuming Spring Data Has `bulkDelete`

Current `DocumentOperations` provides `bulkIndex` and `bulkUpdate`, not `bulkDelete` by a list of IDs. Use `DeleteQuery` for query-based deletes or native `BulkRequest` for delete actions by ID.

### Treating `DeleteQuery` as Atomic

Delete-by-query processes in batches and can encounter version conflicts and failures. Read `ByQueryResponse` and design recovery.

### Forgetting Data Stream Restrictions

Data streams only support the `create` action in bulk. Do not send `update`/`delete` as with a normal index.

## 27. Workflow for Implementing a Bulk Job

When building an import or sync job:

1. Identify the target index/alias/data stream and verify its mapping is created.
2. Determine the action type: `create`, `index`, `update`, or `delete`.
3. Determine ID and routing for each item.
4. Normalize and validate data before sending.
5. Build `IndexQuery`/`UpdateQuery` or `BulkOperation` items.
6. Split batches by item count and byte size.
7. Configure `BulkOptions` such as refresh policy, pipeline, timeout, and active shards if using Spring Data.
8. Limit concurrent bulk requests.
9. Send batches and check per-item errors.
10. Retry selectively with backoff; route permanent errors to a DLQ.
11. Record counts of succeeded, failed, retried items, and processing duration.
12. Refresh after the batch if search needs immediate visibility.
13. Reconcile document counts and states after import.
14. Save checkpoints so the job can resume after a process restart.

## 28. Summary

The Bulk API groups multiple document operations into one request and supports four actions: `index`, `create`, `update`, and `delete`. `index` creates or replaces a document; `create` creates only when the ID does not exist; `update` modifies part of `_source` or runs a script; `delete` removes a document by ID. NDJSON requires one metadata line per action and a payload line for `index`/`create`/`update`, while `delete` has no payload line.

Spring Data Elasticsearch provides `bulkIndex` with `IndexQuery` and `bulkUpdate` with `UpdateQuery`. `IndexQuery.OpType` distinguishes `CREATE` from `INDEX`. `BulkOptions` controls refresh policy, timeout, active shards, pipeline, and shared routing. For deletions, Spring Data supports single-ID delete and `DeleteQuery` for conditional deletes; current `DocumentOperations` does not expose a public `bulkDelete(List<ID>)`. When you need bulk delete by ID or mixed action types, use Elasticsearch Java API Client `BulkRequest` or the REST Bulk API.

Bulk is not a multi-document transaction. A single request can partially succeed; you must inspect `errors` and item failures and avoid blindly retrying the entire batch. Split batches by item count and bytes, limit concurrency, choose appropriate refresh behavior, maintain payload correlation, retry transient errors with backoff, and design idempotent operations. Following these principles keeps bulk jobs high-throughput while remaining resilient to mapping errors, version conflicts, timeouts, and cluster overload.

## References

- [Spring Data Elasticsearch – DocumentOperations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/DocumentOperations.html)
- [Spring Data Elasticsearch – IndexQuery API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/query/IndexQuery.html)
- [Spring Data Elasticsearch – IndexQueryBuilder API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/query/IndexQueryBuilder.html)
- [Spring Data Elasticsearch – UpdateQuery API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/query/UpdateQuery.html)
- [Spring Data Elasticsearch – UpdateQuery.Builder API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/query/UpdateQuery.Builder.html)
- [Spring Data Elasticsearch – DeleteQuery API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/query/DeleteQuery.html)
- [Spring Data Elasticsearch – BulkOptions API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/query/BulkOptions.html)
- [Spring Data Elasticsearch – BulkFailureException API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/BulkFailureException.html)
- [Elasticsearch – Bulk API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-bulk)
- [Elasticsearch Java API Client – Bulk indexing](https://www.elastic.co/docs/reference/elasticsearch/clients/java/usage/indexing-bulk)
- [Elasticsearch – Update By Query API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-update-by-query)
- [Elasticsearch – Delete By Query API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-delete-by-query)
