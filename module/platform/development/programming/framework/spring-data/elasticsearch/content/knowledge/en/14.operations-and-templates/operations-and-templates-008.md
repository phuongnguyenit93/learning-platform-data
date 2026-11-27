# Update, Bulk, and Reindex Operations via Appropriate APIs

Spring Data Elasticsearch provides several ways to write and modify documents: saving entities, partial updates, conditional updates, sending multiple operations in one bulk request, and copying data to another index via reindex. These operations have different goals. Choosing the wrong API can unintentionally overwrite fields, generate unnecessary requests, or lose data during an index transition.

This lesson explains how to choose an API by task scope, use `ElasticsearchOperations`/`DocumentOperations` to update documents, run bulk indexing and bulk updates, use Update By Query and the Reindex API, and manage errors, version conflicts, refreshes, and alias migrations.

## 1. Choosing the Right Operation

Before writing code, identify the goal:

| Need | Appropriate API | Scope |
|---|---|---|
| Write new or replace an entire document by ID | `save(entity)` or `index(...)` | One document |
| Change only a few fields of a document | `update(entity)` or `update(UpdateQuery, index)` | One document |
| Update multiple documents matching the same condition | `updateByQuery(...)` | Documents matching a query in an index |
| Send multiple index/update operations in one call | `bulkIndex(...)`, `bulkUpdate(...)`, or Bulk API | Multiple specified documents |
| Copy data to another index, usually to change mappings/settings | `reindex(...)` or `_reindex` | A set of documents from source to destination |

These APIs may look similar because all of them alter data, yet their semantics differ:

- `save` writes a document using index semantics, typically replacing existing `_source` content with the submitted entity content.
- `update` uses Elasticsearch's Update API to apply a partial document or script to an existing document.
- `updateByQuery` finds a set of documents and applies the same update/script to each one.
- `bulk` packs multiple independent actions into one request to reduce round trips.
- `reindex` reads documents from a source and writes them to another destination index; it does not modify the source index.

## 2. Spring Data Elasticsearch Abstractions

Spring Data organizes Elasticsearch operation APIs into functional interfaces:

| Interface | Primary Responsibility |
|---|---|
| `DocumentOperations` | Save, read, update, delete documents by ID; bulk and reindex |
| `SearchOperations` | Search multiple documents using queries |
| `IndexOperations` | Create/delete indices, read and update mappings/settings, aliases |
| `ElasticsearchOperations` | Combines document and search operation abstractions along with common utilities |

In a Spring Boot application, you can inject `ElasticsearchOperations`:

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.stereotype.Service;

@Service
public class ProductDataService {

    private final ElasticsearchOperations operations;

    public ProductDataService(ElasticsearchOperations operations) {
        this.operations = operations;
    }
}
```

`ElasticsearchOperations` provides a way to operate independently of repositories. Repositories remain suitable for standard CRUD and query methods; operations is suitable when you need explicit control over `UpdateQuery`, bulk options, reindex, or complex queries.

Since Spring Data Elasticsearch 4.0, `DocumentOperations` and `SearchOperations` have been split into dedicated interfaces; `ElasticsearchOperations` combines them. Methods have been added across multiple release trains, so verify against the Javadoc of the dependency version managed by Spring Boot.

## 3. Distinguishing `save` and `update`

### 3.1. `save` Writes the Entire Document

Example entity:

```java
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
    private Long priceInCents;

    // Constructors, getters and setters
}
```

Saving the entity:

```java
Product product = new Product("p-100", "Mechanical Keyboard", "accessories", 1299000L);
Product saved = operations.save(product);
```

`save` uses Elasticsearch's index operation. If a document with that ID already exists, the newly written document content replaces the current `_source` for that ID. If it does not exist yet, the document is created. This is the right choice when the entity represents the complete state the application intends to store.

Keep in mind: if the current `_source` has fields added by another system, re-indexing an entity that lacks those fields can cause them to disappear from the new document. When you only want to change a few fields, use a partial update.

### 3.2. `update(entity)` Performs a Partial Update

`DocumentOperations` provides `update(entity)` to partially update a document based on an entity. For example:

```java
Product patch = new Product();
patch.setId("p-100");
patch.setPriceInCents(1399000L);

operations.update(patch);
```

This API was added in Spring Data Elasticsearch 5.0. How the entity is converted into a partial document depends on the mapping converter and library version. When you need exact control over which fields are sent, `UpdateQuery` with an explicit `Document` is usually clearer.

Do not assume an entity with missing values will always be handled the way you expect. Verify how the converter handles `null` fields, unset fields, and nested objects. If you need to guarantee that only one field is updated, construct a partial document containing only that field.

### 3.3. What Does Elasticsearch's Update API Do?

The Update API allows sending a partial document (`doc`) or a script. On the Elasticsearch side, the update is executed by reading the current document, applying the change, and writing a new document. It does not mutate a few bytes directly inside a Lucene segment.

Example REST API:

```http
POST products/_update/p-100
{
  "doc": {
    "priceInCents": 1399000
  }
}
```

Fields not present in `doc` are preserved. If the document does not exist, the Update API typically returns a document missing error unless the request configures upsert.

## 4. Using `UpdateQuery` to Update One Document

`UpdateQuery` represents an update request. You can create a query by ID and pass a partial document using `Document`.

```java
import java.util.Map;

import org.springframework.data.elasticsearch.core.document.Document;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.UpdateQuery;
import org.springframework.data.elasticsearch.core.query.UpdateResponse;

UpdateQuery updateQuery = UpdateQuery.builder("p-100")
        .withDocument(Document.from(Map.of(
                "priceInCents", 1399000L,
                "category", "mechanical-keyboards")))
        .build();

UpdateResponse response = operations.update(
        updateQuery,
        IndexCoordinates.of("products"));
```

`Document.from(Map)` creates a partial document from key-value pairs. In this example, only `priceInCents` and `category` are sent in the update document payload. Other fields of the product are not overwritten with `null` just because a Java object lacks values.

`UpdateQuery.builder(String id)` is used when updating a single document by ID. `operations.update(updateQuery, index)` executes the partial update and returns an `UpdateResponse`.

### 4.1. Upsert When the Document Does Not Exist Yet

If you want to create the document when it does not yet exist, use `doc_as_upsert`:

```java
UpdateQuery updateOrInsert = UpdateQuery.builder("p-200")
        .withDocument(Document.from(Map.of(
                "name", "Wireless Mouse",
                "category", "accessories",
                "priceInCents", 499000L)))
        .withDocAsUpsert(true)
        .build();

operations.update(updateOrInsert, IndexCoordinates.of("products"));
```

When the document does not exist, `doc` is used to create a new document. When it already exists, the fields in `doc` are applied as a partial update.

Another option is passing a separate `upsert` via `withUpsert(Document)`. This is useful when the content for initial creation differs from the partial document used for updates.

```java
UpdateQuery updateQuery = UpdateQuery.builder("p-201")
        .withDocument(Document.from(Map.of("lastSeenAt", "2026-11-13T10:00:00Z")))
        .withUpsert(Document.from(Map.of(
                "name", "New Device",
                "status", "NEW",
                "lastSeenAt", "2026-11-13T10:00:00Z")))
        .build();
```

Ensure the upsert content contains all fields required by the mapping and business rules. Do not enable upsert merely to avoid handling an invalid ID error; it can create unintended documents.

### 4.2. Updating with a Painless Script

When you want to perform a calculation based on the document's current value, a script is more suitable than reading the document into Java, modifying it, and writing it back.

Example incrementing view count:

```java
import java.util.Map;

UpdateQuery incrementViews = UpdateQuery.builder("p-100")
        .withScript("ctx._source.viewCount += params.delta")
        .withParams(Map.of("delta", 1))
        .build();

operations.update(incrementViews, IndexCoordinates.of("products"));
```

The script executes inside Elasticsearch, using `params` to pass data. Do not concatenate user input strings directly into a script. Using parameters separates code from data and reduces the risk of errors or injection.

Scripts can be used to add/remove fields, compute new values, or skip modifying the document if no change is needed. The script must be compatible with Painless and the actual `_source` structure.

### 4.3. Optimistic Concurrency Control

If multiple processes can update the same document, avoid overwriting each other's changes. Elasticsearch provides `seq_no` and `primary_term` for document version control.

An update request can require updating only if the document is still at the sequence number and primary term previously read:

```java
UpdateQuery guardedUpdate = UpdateQuery.builder("p-100")
        .withDocument(Document.from(Map.of("priceInCents", 1499000L)))
        .withIfSeqNo(42L)
        .withIfPrimaryTerm(3L)
        .build();
```

If the document changed after the read, Elasticsearch returns a version conflict instead of silently overwriting. The application can re-read, recompute, and retry according to business rules.

`withRetryOnConflict(n)` is another mechanism: it instructs Elasticsearch to retry the update when a conflict occurs. It suits update scripts that can be re-executed safely. Do not blindly retry non-idempotent scripts or business operations with side effects outside Elasticsearch.

## 5. Updating Multiple Documents by Criteria: Update By Query

If many documents matching a condition need to receive the same change, there is no need to read each document into the application. Use Elasticsearch's Update By Query API.

Example migrating all products in an old category to a new category:

```http
POST products/_update_by_query
{
  "query": {
    "term": {
      "category": "old-accessories"
    }
  },
  "script": {
    "lang": "painless",
    "source": "ctx._source.category = params.newCategory",
    "params": {
      "newCategory": "accessories"
    }
  }
}
```

Elasticsearch finds documents matching the query and applies the script to each document. Update By Query is suitable when a transformation rule can be executed directly on the cluster.

### 5.1. Using `updateByQuery` from Spring Data

`DocumentOperations` has `updateByQuery(UpdateQuery, IndexCoordinates)`. You can combine a `CriteriaQuery` as the document selection query with a script for the change:

```java
import java.util.Map;

import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.ByQueryResponse;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.UpdateQuery;

CriteriaQuery selection = new CriteriaQuery(
        Criteria.where("category").is("old-accessories"));

UpdateQuery updateByQuery = UpdateQuery.builder(selection)
        .withScript("ctx._source.category = params.newCategory")
        .withParams(Map.of("newCategory", "accessories"))
        .withBatchSize(500)
        .withAbortOnVersionConflict(false)
        .build();

ByQueryResponse response = operations.updateByQuery(
        updateByQuery,
        IndexCoordinates.of("products"));
```

`UpdateQuery.builder(Query)` is used when operating by query instead of ID. `withBatchSize` adjusts the number of documents per batch. `withAbortOnVersionConflict(false)` tells it to continue upon encountering version conflicts; inspect the conflict count in the response and plan how to handle un-updated documents.

Update By Query was added to `DocumentOperations` in Spring Data Elasticsearch 4.2. Specific options on `UpdateQuery` may differ across versions; check the Javadoc for your release train.

### 5.2. Version Conflicts and Error Handling

Update By Query may stop on version conflicts by default. You can choose `abort` or `proceed`:

- `abort`: stops when encountering a conflict; suitable when you want to detect all concurrent changes and handle them explicitly.
- `proceed`: continues with the remaining documents; the response still reports the conflict count.

`proceed` does not resolve conflicts automatically. Conflicting documents may remain un-updated; the application must record and reprocess them if business rules require all documents to reach the new state.

Update By Query uses batch/scroll searching on Elasticsearch's side. For large datasets, pay attention to batch size, scroll duration, timeout, and cluster load.

### 5.3. Rate Limiting and Slicing

Update By Query can throttle processing rate with `requests_per_second` and split work into slices. In `UpdateQuery.Builder`, corresponding options can be expressed via `withRequestsPerSecond(...)`, `withSlices(...)`, `withMaxDocs(...)`, and `withTimeout(...)` depending on version.

Throttling is useful when updating an index serving live traffic. Slicing can increase parallelism but also increases cluster load; do not set a high slice count without monitoring CPU, I/O, and thread pools.

### 5.4. Running Asynchronously and Monitoring Tasks

For a long-running Update By Query job, the Elasticsearch REST API supports `wait_for_completion=false` to return a task ID instead of holding the connection until completion. Applications can use the Tasks API to check status or cancel a task.

REST example:

```http
POST products/_update_by_query?wait_for_completion=false&requests_per_second=500
{
  "query": {
    "term": {
      "status": "LEGACY"
    }
  },
  "script": {
    "source": "ctx._source.status = 'ARCHIVED'"
  }
}
```

The response returns a task ID. Use `GET _tasks/{task_id}` to inspect progress and `POST _tasks/{task_id}/_cancel` if cancellation is needed. Canceling a task does not roll back documents already updated prior to cancellation.

## 6. Bulk API: Multiple Operations in One Request

The Bulk API accepts an NDJSON string containing actions. Each action has metadata and, depending on operation type, an additional document or update source line.

Main actions:

| Action | Behavior |
|---|---|
| `index` | Create or replace a document by ID |
| `create` | Create only; fails if ID already exists |
| `update` | Partially update or run a script on a document |
| `delete` | Delete a document by ID |

Example bulk request containing three action types:

```http
POST _bulk
{"index":{"_index":"products","_id":"p-101"}}
{"name":"Keyboard","category":"accessories","priceInCents":1299000}
{"update":{"_index":"products","_id":"p-102","retry_on_conflict":3}}
{"doc":{"priceInCents":1399000}}
{"delete":{"_index":"products","_id":"p-103"}}
```

The Bulk API body must use NDJSON, with each line being a separate JSON object and the request ending with a newline. For HTTP clients, the appropriate content type is `application/x-ndjson`.

Bulk reduces connections/round trips, but does not turn the whole request into a transaction. Each action is processed independently; one failed item does not necessarily cause other items to fail.

### 6.1. Reading the Bulk API Response

The response typically contains fields:

- `took`: time taken to process the request.
- `errors`: `true` if at least one action failed.
- `items`: individual results for each action, in the order sent.

HTTP status 200 does not mean every item succeeded. Applications must inspect `errors` and each element in `items`, then retry or record failed items according to policy.

Example response with an error:

```json
{
  "took": 18,
  "errors": true,
  "items": [
    {
      "index": {
        "_id": "p-101",
        "status": 201,
        "result": "created"
      }
    },
    {
      "update": {
        "_id": "p-102",
        "status": 404,
        "error": {
          "type": "document_missing_exception",
          "reason": "document missing"
        }
      }
    }
  ]
}
```

The first item succeeded; the second failed because the document did not exist. Do not blindly retry the whole batch; classify errors and only retry actions that are safe to retry.

## 7. Bulk Indexing with Spring Data Elasticsearch

Spring Data provides `bulkIndex(List<IndexQuery>, ...)` in `DocumentOperations`. This method performs bulk indexing with save/update semantics for each document.

Example building `IndexQuery` instances from a list of entities:

```java
import java.util.List;

import org.springframework.data.elasticsearch.core.IndexedObjectInformation;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.IndexQuery;
import org.springframework.data.elasticsearch.core.query.IndexQueryBuilder;

List<IndexQuery> queries = products.stream()
        .map(product -> new IndexQueryBuilder()
                .withId(product.getId())
                .withObject(product)
                .build())
        .toList();

List<IndexedObjectInformation> indexed = operations.bulkIndex(
        queries,
        IndexCoordinates.of("products"));
```

`IndexQueryBuilder` lets you specify ID, object, routing, version, and operation type. If you need to guarantee creation only, set `IndexQuery.OpType.CREATE` instead of the default index behavior:

```java
IndexQuery createOnly = new IndexQueryBuilder()
        .withId(product.getId())
        .withObject(product)
        .withOpType(IndexQuery.OpType.CREATE)
        .build();
```

When the ID already exists, the create action reports a conflict instead of replacing the document. Choose `CREATE` when input data must represent new records and overwriting is a business error.

### 7.1. Configuring `BulkOptions`

You can pass `BulkOptions` to configure pipeline, refresh policy, timeout, routing, or active shard count:

```java
import java.time.Duration;

import org.springframework.data.elasticsearch.core.RefreshPolicy;
import org.springframework.data.elasticsearch.core.query.BulkOptions;

BulkOptions options = BulkOptions.builder()
        .withRefreshPolicy(RefreshPolicy.NONE)
        .withTimeout(Duration.ofSeconds(30))
        .build();

List<IndexedObjectInformation> result = operations.bulkIndex(
        queries,
        options,
        IndexCoordinates.of("products"));
```

`RefreshPolicy.NONE` avoids requesting an immediate refresh after bulk execution. If the application needs to find documents right after writing, consider `WAIT_UNTIL` or `IMMEDIATE`, keeping in mind that frequent refreshes reduce indexing performance.

`BulkOptions` does not replace batch splitting. Applications must still decide an appropriate batch size for document sizes, bandwidth, and cluster resources.

### 7.2. Bulk Update with `UpdateQuery`

When you know each document's ID and only want to update specific fields, build a list of `UpdateQuery`:

```java
import java.util.List;
import java.util.Map;

import org.springframework.data.elasticsearch.core.document.Document;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.UpdateQuery;

List<UpdateQuery> updates = List.of(
        UpdateQuery.builder("p-101")
                .withDocument(Document.from(Map.of("priceInCents", 1299000L)))
                .build(),
        UpdateQuery.builder("p-102")
                .withDocument(Document.from(Map.of("priceInCents", 1399000L)))
                .build(),
        UpdateQuery.builder("p-103")
                .withDocument(Document.from(Map.of("priceInCents", 1499000L)))
                .build()
);

operations.bulkUpdate(
        updates,
        BulkOptions.defaultOptions(),
        IndexCoordinates.of("products"));
```

`bulkUpdate` performs an update for each `UpdateQuery`. Unlike `bulkIndex`, this method does not replace entire documents. You can use `withDocument`, `withScript`, `withUpsert`, `withDocAsUpsert`, `withRetryOnConflict`, or concurrency conditions as needed.

Spring Data's bulk methods can throw `BulkFailureException` when actions fail. Do not ignore the exception and assume the entire batch succeeded.

## 8. Handling Bulk Errors in Spring Data

Spring Data provides `BulkFailureException`, a `DataAccessException` containing details about failed documents. You can inspect `getFailedDocuments()` to log or enqueue failed items for retry:

```java
import org.springframework.data.elasticsearch.BulkFailureException;

try {
    operations.bulkUpdate(
            updates,
            BulkOptions.defaultOptions(),
            IndexCoordinates.of("products"));
} catch (BulkFailureException ex) {
    ex.getFailedDocuments().forEach((id, failure) -> {
        // Record the document ID, HTTP status and error message.
        System.err.println(id + " -> " + failure.status()
                + ": " + failure.errorMessage());
    });
    throw ex;
}
```

Since Spring Data Elasticsearch 5.2, `getFailedDocuments()` returns a map whose values are `BulkFailureException.FailureDetails` with status and error message. Previous versions used a different value type; when upgrading, check the migration guide and actual API signatures.

Classify errors:

- Mapping/parsing errors: fix data or mapping before retrying.
- Version conflicts: re-read state or apply a controlled retry strategy.
- Document missing on update: verify ID, or switch to upsert if appropriate for the business rule.
- Authentication/authorization: fix credentials or permissions; do not retry repeatedly.
- Timeouts or network errors: determine whether the server partially processed the request before resending.

Retries must be idempotent. For an index action with the same ID and content, resending usually yields the same final state; for counter-incrementing scripts or additive operations, retries can apply changes twice without deduplication mechanisms.

## 9. Choosing Batch Size and Operating Bulk Writes

There is no single optimal bulk size for every cluster. Document count is only part of the equation; payload byte size, field count, analyzers, ingest pipelines, and write rate all affect performance.

Practical principles:

- Start with a moderate batch size, measure throughput and latency, then tune.
- Split data by document count or total bytes; avoid creating one massive request holding the entire payload in heap.
- Monitor `took`, failed item counts, bulk thread pool, indexing pressure, and disk space.
- Avoid refreshing right after every batch unless immediate searchability is required.
- When multiple producers exist, avoid letting every producer send the maximum possible batch simultaneously.
- Apply backpressure or rate limiting when the cluster is overloaded.
- Preserve operation order if business rules require it, especially when multiple actions update the same ID.

The Bulk API is not a transaction. If a group of operations must succeed or fail together, design orchestration/compensation at the application layer; you cannot rely on a single bulk request to roll back all items.

## 10. Direct Bulk API and Elasticsearch Java API Client

When Spring Data abstractions satisfy your needs, `bulkIndex` and `bulkUpdate` leverage the mapping converter and `IndexCoordinates`. When lower-level action control or new Elasticsearch options are needed, you can use the Elasticsearch Java API Client or the REST Bulk API.

The Elasticsearch Java API Client is the official client in modern Spring Data Elasticsearch release trains. You can inject `co.elastic.clients.elasticsearch.ElasticsearchClient` if the application configuration provides that bean. When using the client directly, the application is responsible for building requests/responses matching the client API and server version.

Do not independently upgrade the `elasticsearch-java` dependency to a different major version than the one managed by Spring Data/Spring Boot without verifying compatibility. Request types are generated per client version.

## 11. When to Use Reindex?

Reindex copies documents from a source index, alias, or data stream to a destination index. This is the right API when you need to:

- Move data to a new index with a different mapping.
- Change analyzers or field types requiring re-indexing.
- Change shard count or index settings.
- Normalize data with a script during migration.
- Merge multiple source indices into one destination index.
- Move data to an index with a new structure or lifecycle.

Reindex is not the same as `updateByQuery`:

| Operation | Source | Destination | Purpose |
|---|---|---|---|
| Update By Query | One index updated in place | The same index | Modify existing documents by query/script |
| Reindex | One or more sources | Another index/stream | Copy documents to a destination, optionally transforming data |

Reindex does not delete source documents. After a successful reindex, both source and destination remain until the application or operations workflow switches aliases and cleans up the source.

## 12. Preparing the Destination Before Reindexing

The Elasticsearch Reindex API only copies documents. It **does not copy settings, mappings, shard counts, replicas, or index templates** from source to destination.

Therefore, create the destination with the desired configuration before calling reindex:

```http
PUT products-v2
{
  "settings": {
    "number_of_shards": 2,
    "number_of_replicas": 1
  },
  "mappings": {
    "properties": {
      "name": {
        "type": "text"
      },
      "category": {
        "type": "keyword"
      },
      "priceInCents": {
        "type": "long"
      },
      "createdAt": {
        "type": "date"
      }
    }
  }
}
```

Only then run reindex. The source must have `_source` enabled because the Reindex API reads document content from `_source` to send to the destination.

Source and destination must differ. You cannot reindex an index or data stream into itself. If the destination is a data stream, the reindex operation must use `op_type: create` because data streams are append-only and do not allow updating existing documents in the usual way.

## 13. Calling the Reindex API via REST

Example copying all documents from `products-v1` to `products-v2`:

```http
POST _reindex
{
  "source": {
    "index": "products-v1"
  },
  "dest": {
    "index": "products-v2"
  }
}
```

You can filter the source using Query DSL:

```http
POST _reindex
{
  "source": {
    "index": "products-v1",
    "query": {
      "term": {
        "status": "ACTIVE"
      }
    }
  },
  "dest": {
    "index": "products-v2",
    "op_type": "create"
  }
}
```

`op_type: create` only creates new documents at the destination. If an ID already exists, the create action fails with a conflict instead of overwriting the destination document.

### 13.1. Transforming Data with a Script During Reindex

You can use a Painless script to transform data before writing to the destination:

```http
POST _reindex
{
  "source": {
    "index": "products-v1"
  },
  "dest": {
    "index": "products-v2"
  },
  "script": {
    "lang": "painless",
    "source": "ctx._source.category = ctx._source.remove('legacyCategory')"
  }
}
```

The script above moves the value from `legacyCategory` to `category` and removes the old field from the new `_source`. Test scripts on a small set of documents before running across the full dataset.

### 13.2. Version Conflicts

Reindex stops on version conflicts by default. You can set `conflicts: proceed` to continue and count conflicts:

```http
POST _reindex?wait_for_completion=true
{
  "conflicts": "proceed",
  "source": {
    "index": "products-v1"
  },
  "dest": {
    "index": "products-v2",
    "op_type": "create"
  }
}
```

`proceed` does not mean every document was copied. Inspect `version_conflicts`, `failures`, `created`, `updated`, and other counters in the response. Decide how to handle conflicts based on migration goals.

### 13.3. Running Reindex Asynchronously

For large datasets, use `wait_for_completion=false` to obtain a task ID:

```http
POST _reindex?wait_for_completion=false&requests_per_second=500
{
  "source": {
    "index": "products-v1",
    "size": 500
  },
  "dest": {
    "index": "products-v2"
  }
}
```

Check the task:

```http
GET _tasks/<task_id>
```

Cancel the task if needed:

```http
POST _tasks/<task_id>/_cancel
```

A canceled task does not roll back documents already written to the destination. When rerunning, define a policy for handling partially copied documents, such as deleting the test destination and rerunning, or using `op_type: create` and handling conflicts.

## 14. Reindexing with Spring Data Elasticsearch

Spring Data Elasticsearch provides `ReindexRequest` along with two methods on `DocumentOperations`:

- `reindex(ReindexRequest)`: executes reindex and returns `ReindexResponse`.
- `submitReindex(ReindexRequest)`: submits the job and returns a task ID.

These two methods have been available since Spring Data Elasticsearch 4.4. Example building a request:

```java
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.reindex.ReindexRequest;
import org.springframework.data.elasticsearch.core.reindex.ReindexResponse;

ReindexRequest request = ReindexRequest.builder(
                IndexCoordinates.of("products-v1"),
                IndexCoordinates.of("products-v2"))
        .withSourceSize(500)
        .withMaxDocs(100_000L)
        .withConflicts(ReindexRequest.Conflicts.PROCEED)
        .withRefresh(true)
        .build();

ReindexResponse response = operations.reindex(request);
```

`IndexCoordinates` specifies the source and destination. `withSourceSize` adjusts the batch size read from the source; `withMaxDocs` limits the number of documents processed; `withConflicts` chooses how version conflicts are handled; `withRefresh(true)` requests refreshing the destination after the operation.

You can add a query to copy only required documents:

```java
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;

ReindexRequest activeProducts = ReindexRequest.builder(
                IndexCoordinates.of("products-v1"),
                IndexCoordinates.of("products-v2"))
        .withSourceQuery(new CriteriaQuery(
                Criteria.where("status").is("ACTIVE")))
        .withSourceSize(500)
        .build();
```

The reindex request builder also offers options such as script, destination pipeline, destination routing, operation type, version type, slicing, throttling, scroll duration, and timeout. Check the Javadoc for your exact version to see available methods.

### 14.1. Monitoring the Response

`ReindexResponse` provides information such as:

- `getTotal()`: number of documents processed successfully.
- `getCreated()`: number of documents created at the destination.
- `getUpdated()`: number of documents updated at the destination.
- `getVersionConflicts()`: number of version conflicts.
- `getFailures()`: list of failures.
- `isTimedOut()`: whether any sub-request timed out.
- `getTook()`: execution duration.

Do not check only `getTotal()`. Inspect conflicts, failures, and timeouts as well before concluding the migration is complete.

### 14.2. Submitting a Reindex Task

If you want to run the job asynchronously:

```java
String taskId = operations.submitReindex(request);
```

This method returns a task ID. Use Elasticsearch's Tasks API via the Elasticsearch Java API Client or REST API to monitor, cancel, or fetch task results. `submitReindex` does not mean the job is finished when the method returns.

## 15. Safe Index Migration Workflow

A typical scenario is changing the mapping of `products-v1` and creating `products-v2`. Because you cannot always directly modify the type of an already-indexed field, creating a new index and reindexing is a common approach.

```text
             1. Create products-v2
                       |
                       v
             2. Reindex from v1 to v2
                       |
                       v
             3. Verify v2 data
                       |
                       v
             4. Sync new writes
                       |
                       v
             5. Switch read/write alias
                       |
                       v
             6. Keep v1 during rollback window
                       |
                       v
             7. Delete v1 once verified
```

Deployment sequence:

1. Create `products-v2` with the desired settings, mappings, analyzers, and aliases.
2. Inspect the destination index mapping before copying.
3. Run reindex from `products-v1` to `products-v2`.
4. Verify document count, sample data, mappings, queries, and aggregations on the new index.
5. Handle documents written to the source during reindexing. You can pause writes, dual-write, replay events, or run a catch-up pass depending on the architecture.
6. Switch read/write aliases to the new index in a single Aliases API operation.
7. Monitor errors after switching and keep the old index during the rollback window.
8. Only delete the old index after data and operational stability have been verified.

Reindex does not automatically synchronize changes occurring after the moment it reads a document. If the application keeps writing to the old index during migration, those changes may not appear in the new index. Have a final sync strategy before switching aliases.

### 15.1. Switching Aliases

Example switching the `products-read` alias from the old index to the new index:

```http
POST _aliases
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
    }
  ]
}
```

The Aliases API performs the batch of changes in one request atomically at the cluster metadata level. For write aliases, configure `is_write_index` properly if the alias points to multiple indices. Applications should use stable aliases rather than hardcoding versioned index names if the architecture requires frequent migrations.

### 15.2. Reindex and Data Streams

Reindex can read from a data stream. When the destination is a data stream, you must use `op_type: create`; data streams do not support updating existing documents via reindex. Create the destination data stream and appropriate template before copying data.

## 16. Refresh and Data Visibility

Elasticsearch is a near-real-time system. After `save`, `update`, bulk, or reindex, data may not appear immediately in search until the next refresh.

Spring Data provides `RefreshPolicy` and methods like `operations.withRefreshPolicy(...)`. Common options:

| Policy | Meaning |
|---|---|
| `NONE` | No explicit refresh requested; changes appear after the next scheduled refresh |
| `IMMEDIATE` | Refresh immediately after the operation so changes become searchable promptly |
| `WAIT_UNTIL` | Wait for the next refresh rather than forcing an immediate refresh |

Do not set `IMMEDIATE` on every production request just so search sees data immediately. Frequent refreshes degrade write performance. Choose a policy based on business and testing requirements.

## 17. Routing, Pipelines, and Consistency Conditions

When writing documents with custom routing, updates and bulk actions must also use the corresponding routing. Otherwise, Elasticsearch may target the wrong shard or fail to find the document.

`BulkOptions` can pass a shared routing ID for a bulk request. `UpdateQuery` also provides `withRouting(...)`. When documents have different routing keys, configure individual actions/queries rather than using one incorrect shared routing value.

Ingest pipelines can run during index/bulk index or when a reindex destination is configured to use a pipeline. When reindexing, you can specify a destination pipeline. Check whether the pipeline reapplies expected normalization logic and avoid duplicate processing that modifies data unexpectedly.

For concurrent update flows:

- Use `if_seq_no` and `if_primary_term` when optimistic concurrency is needed.
- Use `retry_on_conflict` when updates can be retried safely.
- Design idempotent scripts if requests may be retried.
- Do not treat bulk or reindex as transactions.
- Record ID, index, action, and error cause so selective replay is possible.

## 18. Common Pitfalls

### Using `save` When You Only Want to Edit One Field

`save` overwrites the document from the entity, which can lose fields missing from the object. Use `UpdateQuery` or `update(entity)` for partial updates.

### Using Update on a Non-Existent Document Without Configuring Upsert

The Update API may return document missing. If business rules want to create the document when missing, explicitly configure `doc_as_upsert` or `upsert`.

### Bulk Returns HTTP 200 Even with Failed Items

Check `errors` and each item in the response; in Spring Data, handle `BulkFailureException.getFailedDocuments()`.

### Retrying Additive Scripts Multiple Times

A non-idempotent counter-increment script can increment multiple times if the application resends the action after a timeout. Use idempotency keys, version checks, or appropriate script/flow design.

### Reindexing Without Creating the Destination Mapping

Reindex does not copy mappings/settings. If the destination relies on dynamic mapping, data types may differ from the source or data may be parsed incorrectly. Create the destination beforehand with a defined configuration.

### Reindexing While the Source Still Receives Writes

New changes may not be copied to the destination. Use dual-write, write pauses, a catch-up pass, or event replay before switching aliases.

### Using `conflicts: proceed` and Assuming Migration Is Complete

Conflicts are still documents not processed by that request. Inspect conflict counts and failures, then decide whether to rerun or handle separately.

### Not Tracking Asynchronous Tasks

`submitReindex` or `wait_for_completion=false` only returns a task ID. Monitor status, results, timeouts, and failures before switching aliases.

### Oversized Bulk Batches

Oversized requests can pressure heap, network, and thread pools. Split batches, measure throughput, and apply backpressure.

## 19. Choosing an API by Scenario

| Scenario | Recommended Choice | Why |
|---|---|---|
| Write a complete entity | Repository `save` or `operations.save` | Simple API; mapping converter handles entity |
| Edit a few fields of one document | `operations.update(UpdateQuery, index)` | Sends explicit partial document |
| Increment a counter or compute from current values | `UpdateQuery` with Painless script | Avoids reading document into application |
| Many documents matching a condition need the same change | `updateByQuery` | Elasticsearch searches and updates in batches |
| Many documents with individual IDs and contents | `bulkIndex`/`bulkUpdate` | Bundles multiple actions into a bulk request |
| Need mixed `create`, `delete`, and `update` actions | Bulk API / Java API Client | Control each action within the same request |
| Change mapping or switch index version | `reindex` | Copies documents to a prepared destination index |
| Run a long reindex and need a task ID | `submitReindex` or REST with `wait_for_completion=false` | Track and control the task independently |

## 20. Testing and Verifying Results

Verify data, responses, and searchability after operations. Example with partial update:

```java
@Test
void partialUpdateChangesOnlyTheRequestedField() {
    Product original = new Product(
            "p-100", "Keyboard", "accessories", 1299000L);
    operations.save(original);

    UpdateQuery update = UpdateQuery.builder("p-100")
            .withDocument(Document.from(Map.of("priceInCents", 1399000L)))
            .build();

    operations.update(update, IndexCoordinates.of("products"));

    Product loaded = operations.get("p-100", Product.class);
    assertThat(loaded).isNotNull();
    assertThat(loaded.getName()).isEqualTo("Keyboard");
    assertThat(loaded.getPriceInCents()).isEqualTo(1399000L);
}
```

In integration tests, wait for or request an appropriate refresh before verifying via search. `get(id, ...)` uses document retrieval by ID and does not depend on search visibility in the same way `_search` does.

For bulk operations, verify the count of successful actions and the error list. For reindex, verify destination mapping, document count, transformed fields, version conflicts, and representative queries. Do not compare counts alone because two different document sets can have the same count.

Testcontainers or a real Elasticsearch instance helps validate Update API, Bulk API, ingest pipeline, and Reindex API semantics. Mocking `ElasticsearchOperations` only tests Java-layer interactions and does not confirm that Elasticsearch executes requests as expected.

## 21. API Differences Across Release Trains

Spring Data Elasticsearch and the Elasticsearch Java API Client change across versions. Some API milestones in current documentation:

- `DocumentOperations` was extracted as a dedicated interface starting in Spring Data Elasticsearch 4.0.
- `bulkUpdate` has been available since 4.1.
- `updateByQuery` has been available since 4.2.
- `reindex` and `submitReindex` have been available since 4.4.
- `update(entity)` has been available since 5.0.
- Since Spring Data Elasticsearch 5.2, the value type in `BulkFailureException.getFailedDocuments()` is `FailureDetails` instead of a plain error string in earlier versions.

Spring Boot manages compatible Spring Data and Elasticsearch Java API Client versions via dependency management. Before copying examples, verify your actual `spring-data-elasticsearch` version and its Javadoc. Do not independently upgrade Elasticsearch Java API Client to another major version without confirming compatibility.

## 22. Recommended Workflow

When implementing a major data change, you can follow this sequence:

1. Determine whether the change is a full document write, partial update, update by query, bulk, or reindex.
2. Choose `ElasticsearchRepository` for simple operations or `ElasticsearchOperations` for fine-grained API control.
3. Identify index, ID, routing, and concurrency conditions.
4. Test on a few sample documents in a development environment.
5. Split batches and configure appropriate timeouts, refreshes, and retry/throttling.
6. Record responses and handle per-item errors; do not assume bulk is atomic.
7. For large update-by-query or reindex jobs, consider asynchronous tasks and monitor the Tasks API.
8. For reindex, create destination mappings/settings first, check `_source`, and prepare a sync strategy for new writes.
9. Compare data, test queries, then switch aliases.
10. Delete the old index only after verification and once the rollback window has passed.

## 23. Summary

`save` is suitable when writing complete entity state; `update` is suitable when modifying only part of a document. `UpdateQuery` allows sending partial documents, upserts, or Painless scripts. `updateByQuery` applies a change to documents matching criteria. The Bulk API bundles multiple independent actions in one request; you must inspect per-item results and handle partial failures. Reindex copies documents to a preconfigured destination index, commonly used when changing mappings or migrating index versions.

In Spring Data Elasticsearch, `DocumentOperations`/`ElasticsearchOperations` provides `update`, `updateByQuery`, `bulkIndex`, `bulkUpdate`, `reindex`, and `submitReindex`. When an abstraction does not support a new Elasticsearch option, you can use the Elasticsearch Java API Client or REST API. Selecting the right API for the goal, controlling concurrency and refreshes, tracking per-item errors, and preparing an alias migration workflow make data changes predictable and operationally safe.

## References

- [Spring Data Elasticsearch – Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch – DocumentOperations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/DocumentOperations.html)
- [Spring Data Elasticsearch – UpdateQuery API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/query/UpdateQuery.html)
- [Spring Data Elasticsearch – ReindexRequest API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/reindex/ReindexRequest.html)
- [Elasticsearch – Bulk API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-bulk)
- [Elasticsearch – Update By Query API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-update-by-query)
- [Elasticsearch – Reindex API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-reindex)
