# UpdateQuery, doc Content, and Fields to Update

In Spring Data Elasticsearch, `UpdateQuery` describes an operation to update an existing document in an index. Instead of resending the entire entity like an index/save operation, the application can send a partial `doc` containing only the fields that need to change, or send a script to update values based on the document's current state.

The key is distinguishing **the document content sent for updating** from **the fields actually present in the update payload**. With a partial document update, fields omitted from `doc` are typically preserved; fields present in `doc` are added or have their values replaced. If sending an entire object or array, you must understand how Elasticsearch merges that structure. In particular, arrays are usually replaced as a single complete value rather than merged element-by-element by ID.

`UpdateQuery` is the class describing the request; `ElasticsearchOperations.update(...)` executes the operation against the index. This approach is useful when you only need to modify a few attributes, want to use a script for atomic calculations, or need control over upsert and update conflict handling.

## 1. How Does Document Update Differ from Save/Index Document?

Suppose a product is stored in the index:

```json
{
  "sku": "KB-1001",
  "name": "Mechanical Keyboard",
  "price": 120,
  "stock": 35,
  "description": "Wireless mechanical keyboard",
  "active": true
}
```

A price change request only needs to update `price`:

```json
POST /products/_update/KB-1001
{
  "doc": {
    "price": 135
  }
}
```

After the update, the document retains `sku`, `name`, `stock`, `description`, and `active`; only `price` changes to `135`.

If the application creates an entity with only `sku` and `price`, and then calls `save(entity)` to reindex under the same ID, fields absent from the entity may be lost from `_source` because the index operation rewrites the document content. Therefore:

| Operation | Meaning |
|---|---|
| `save(entity)` / index document | Writes the document from the entity's content; typically replaces the current source for that ID |
| `UpdateQuery` with `doc` | Sends a partial document to update the provided fields |
| `UpdateQuery` with script | Executes update logic on the current source in Elasticsearch |
| Update by query | Applies an update/script to multiple documents matching a query |

Choose update when you want to modify part of a document without reading and rewriting the entire entity. Choose save/index when the application has the full, authoritative version of the document and intentionally wants to replace its content.

## 2. UpdateQuery and ElasticsearchOperations

`UpdateQuery` belongs to the package `org.springframework.data.elasticsearch.core.query`. It encapsulates the details needed for the Update API, such as partial document, script, upsert, routing, retry on conflict, and other version-dependent options.

`ElasticsearchOperations` provides the execution API:

```java
UpdateResponse response = operations.update(updateQuery, indexCoordinates);
```

Where:

- `updateQuery` describes the ID and the content/script to update.
- `indexCoordinates` specifies the target index or alias.
- `UpdateResponse` holds the result of the update operation according to the Elasticsearch response and Spring Data version.

Unlike repository `save`, `UpdateQuery` allows the application to explicitly define the portion of data to write.

## 3. Creating a Partial Doc Using Document

Spring Data Elasticsearch uses `Document` to represent JSON content as a map. You can create a `Document` containing only the fields to change:

```java
import org.springframework.data.elasticsearch.core.document.Document;

Document partial = Document.create()
    .append("price", 135)
    .append("stock", 30);
```

`partial` does not need to include `sku`, `name`, `description`, or `active`. When sent as the `doc` portion of the Update API, omitted fields are not overwritten simply because they are absent.

### 3.1 Creating an UpdateQuery

```java
import org.springframework.data.elasticsearch.core.query.UpdateQuery;

UpdateQuery updateQuery = UpdateQuery.builder("KB-1001")
    .withDocument(partial)
    .build();
```

The builder takes the document ID. `withDocument(partial)` sets the partial `doc` content to merge into the existing document.

### 3.2 Executing the Update

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.UpdateResponse;

public class ProductUpdateService {

    private final ElasticsearchOperations operations;

    public ProductUpdateService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public UpdateResponse updatePrice(String id, double newPrice) {
        Document partial = Document.create()
            .append("price", newPrice);

        UpdateQuery updateQuery = UpdateQuery.builder(id)
            .withDocument(partial)
            .build();

        return operations.update(
            updateQuery,
            IndexCoordinates.of("products")
        );
    }
}
```

This example updates only `price` for the document with the passed-in ID. If the document does not exist, the default behavior is for the update to fail per Elasticsearch Update API semantics; to create it when missing, you must configure upsert.

### 3.3 Using Document When Multiple Fields Are Needed

```java
Document partial = Document.create()
    .append("price", 135.0)
    .append("stock", 30)
    .append("active", true);

UpdateQuery updateQuery = UpdateQuery.builder("KB-1001")
    .withDocument(partial)
    .build();

operations.update(updateQuery, IndexCoordinates.of("products"));
```

Only the three fields present in the partial doc are updated. Other fields continue to keep their current values in the document.

## 4. Selecting the Exact Fields to Update

A partial doc should contain only the fields belonging to the business request. Do not serialize the entire request DTO or entity into `Document` if the request is only permitted to change a few attributes.

Example API request:

```java
public record UpdateProductRequest(
    Double price,
    Integer stock,
    Boolean active
) {
}
```

The service can add fields only when the request actually provides a value:

```java
Document partial = Document.create();

if (request.price() != null) {
    partial.append("price", request.price());
}

if (request.stock() != null) {
    partial.append("stock", request.stock());
}

if (request.active() != null) {
    partial.append("active", request.active());
}

if (partial.isEmpty()) {
    throw new IllegalArgumentException("No fields to update");
}
```

Then use `partial` as `doc`. This approach clearly distinguishes "the client did not send the field" from "the client sent a value to update".

### 4.1 Do Not Conflate Null with Omitted

In a JSON request, a field can be:

- Absent: the client does not request changing that field.
- Present with value `null`: the client wants to set the field to null, if business rules allow.
- Present with a concrete value: the client wants to update to that value.

If using a DTO with standard nullable fields, both "omitted" and "sent as null" can map to Java `null`. When you need to distinguish them, use JSON Merge Patch, `JsonNode`, a wrapper with presence state, or a DTO that explicitly represents all three states.

For example, if `description` is allowed to be cleared with null, append `description: null` only when the client actually sends the field. If you only append when the value is non-null, the API cannot request setting the field to null.

### 4.2 Field Names in Document

`Document` represents the fields in the JSON sent to Elasticsearch. Use the field names according to the Elasticsearch mapping, especially when a Java property has `@Field(name = "...")` or when names are transformed by a naming strategy.

Example:

```java
@Field(name = "product_status", type = FieldType.Keyword)
private String status;
```

A partial doc sent directly may need the key `product_status` per the mapping, rather than assuming the key is `status`. Check the mapping and how your version's converter/query API handles field names.

## 5. Updating Nested Fields

Elasticsearch partial updates merge JSON objects according to Update API semantics. If you send a child object, the provided sub-fields may be merged into the existing object; sub-fields absent from the partial object are typically preserved.

Current document:

```json
{
  "name": "Mechanical Keyboard",
  "manufacturer": {
    "name": "Northwind",
    "country": "VN",
    "supportEmail": "help@example.test"
  }
}
```

Partial update:

```json
{
  "doc": {
    "manufacturer": {
      "supportEmail": "support@example.test"
    }
  }
}
```

Under object merge semantics, `manufacturer.supportEmail` is replaced; `manufacturer.name` and `manufacturer.country` are preserved.

### 5.1 Arrays Are Not Merged Element-by-Element by Key

With arrays, do not assume a partial doc automatically finds the element with the same `sku` and updates only one attribute.

Current document:

```json
{
  "variants": [
    { "sku": "RED-M", "color": "red", "price": 120 },
    { "sku": "BLUE-L", "color": "blue", "price": 140 }
  ]
}
```

If you send:

```json
{
  "doc": {
    "variants": [
      { "sku": "RED-M", "price": 125 }
    ]
  }
}
```

the `variants` array may be replaced with an array containing only the sent element, losing `BLUE-L`. Elasticsearch does not automatically treat `sku` as a key for merging array elements.

If you need to update a single element in an array, there are two approaches:

1. Read the current array, modify the element in the application, and send back the entire array; concurrency handling is required to avoid overwriting concurrent changes.
2. Use a Painless script to find the element by key and replace the corresponding field in `_source` on the Elasticsearch side.

If child elements have independent lifecycles and frequent independent updates, consider modeling them as separate documents or using nested/object types according to your query needs.

## 6. Upsert: Update or Create New

By default, the Update API requires the document to already exist. If you want to create the document when the ID is missing, you can use upsert.

### 6.1 `doc_as_upsert`

`doc_as_upsert` instructs Elasticsearch to use the partial doc itself as the content for creation if the document does not yet exist:

```java
Document partial = Document.create()
    .append("sku", "KB-1001")
    .append("name", "Mechanical Keyboard")
    .append("price", 135.0)
    .append("stock", 30);

UpdateQuery updateQuery = UpdateQuery.builder("KB-1001")
    .withDocument(partial)
    .withDocAsUpsert(true)
    .build();

operations.update(updateQuery, IndexCoordinates.of("products"));
```

If the ID does not exist yet, Elasticsearch creates the document from the `doc` content. Therefore, the partial doc must have at least the minimum fields needed for the new document to be valid according to the mapping and business rules. Do not enable doc-as-upsert for a payload containing only one field like `stock` if new documents require `sku`, `name`, and other fields.

### 6.2 Separate `upsert`

You can specify dedicated content to use when the document does not yet exist:

```java
Document partial = Document.create()
    .append("price", 135.0);

Document initialDocument = Document.create()
    .append("sku", "KB-1001")
    .append("name", "Mechanical Keyboard")
    .append("price", 135.0)
    .append("stock", 0)
    .append("active", true);

UpdateQuery updateQuery = UpdateQuery.builder("KB-1001")
    .withDocument(partial)
    .withUpsert(initialDocument)
    .build();
```

When the document already exists, Elasticsearch applies `partial`; when it does not yet exist, it uses `initialDocument` to create it. This approach allows the creation payload to be more complete than the update payload.

### 6.3 Choosing `doc_as_upsert` vs. Separate `upsert`

| Case | Approach |
|---|---|
| Partial doc is sufficient as a new document | `doc_as_upsert` |
| Creation content differs from update content | Separate `upsert` |
| Update only existing documents | Do not configure upsert |
| Using a script and want to create when absent | Scripted upsert per appropriate API |

Upsert does not mean every update error automatically creates a document. It only handles the case where the document ID does not yet exist as configured in the request; mapping, validation, or cluster errors can still fail.

## 7. Using Scripts to Update Based on Current State

Partial `doc` is suitable when the new values are already computed by the application. A script is suitable when you need to read current values and perform atomic transformations in Elasticsearch.

Example incrementing stock by an amount:

```json
POST /products/_update/KB-1001
{
  "script": {
    "lang": "painless",
    "source": "ctx._source.stock += params.amount",
    "params": {
      "amount": 5
    }
  }
}
```

Instead of the application reading the current stock, adding 5, and writing the new value (risking lost updates), the script performs the addition inside the update operation in Elasticsearch.

### 7.1 Conditional Scripts

You can check state before updating:

```json
POST /products/_update/KB-1001
{
  "script": {
    "lang": "painless",
    "source": "if (ctx._source.stock >= params.amount) { ctx._source.stock -= params.amount; } else { ctx.op = 'none'; }",
    "params": {
      "amount": 2
    }
  }
}
```

If stock is sufficient, the script subtracts the quantity. If insufficient, `ctx.op = 'none'` leaves the document unchanged. In real business logic, define what a `noop` response means and return the appropriate result to the caller.

### 7.2 Scripts Should Not Concatenate Input Directly into Source

Do not construct scripts by concatenating user-supplied strings:

```java
// Avoid: input is concatenated directly into script source.
String source = "ctx._source.stock += " + userInput;
```

Keep the source fixed and pass values via `params`. This reduces script injection risk, avoids escaping errors, and allows Elasticsearch to cache compiled scripts more effectively.

### 7.3 Scripts in UpdateQuery

Spring Data Elasticsearch provides builder properties for scripts such as source, language, parameters, and script type depending on the version. Illustrative example using common builder APIs:

```java
Map<String, Object> params = Map.of("amount", 5);

UpdateQuery updateQuery = UpdateQuery.builder("KB-1001")
    .withScript("ctx._source.stock += params.amount")
    .withLang("painless")
    .withParams(params)
    .build();

UpdateResponse response = operations.update(
    updateQuery,
    IndexCoordinates.of("products")
);
```

Script method names and overloads can vary across Spring Data Elasticsearch versions; check the Javadoc for your exact dependency. On the Elasticsearch side, the corresponding request is an Update API call with `script` and `params`.

### 7.4 Scripts Modifying Multiple Fields

```json
POST /products/_update/KB-1001
{
  "script": {
    "lang": "painless",
    "source": "ctx._source.stock -= params.quantity; ctx._source.updatedAt = params.updatedAt; ctx._source.lastOrderId = params.orderId",
    "params": {
      "quantity": 2,
      "updatedAt": "2025-03-12T10:30:00Z",
      "orderId": "ORDER-9001"
    }
  }
}
```

A single script can update multiple fields based on the same current state. Validate parameters in the application and ensure the script handles missing/null fields according to business rules.

## 8. Removing a Field or Setting It to Null

The two operations have different semantics:

- Setting a field to `null`: the field may still exist in `_source` with a `null` value.
- Removing a field from `_source`: the key is removed from the object.

Partial doc:

```json
{
  "doc": {
    "description": null
  }
}
```

Script removing the key:

```json
{
  "script": {
    "lang": "painless",
    "source": "ctx._source.remove('description')"
  }
}
```

If an API has a "clear field" operation, decide whether to use `null` or remove. Mappings, query semantics, and how the application serializes documents can make these two states behave differently.

## 9. Updating Nested/Object Arrays

For arrays of objects, updating one attribute of an element by key usually requires a script or a read-modify-write of the entire array.

Painless example finding a variant by SKU:

```json
POST /products/_update/product-1001
{
  "script": {
    "lang": "painless",
    "source": "for (def variant : ctx._source.variants) { if (variant.sku == params.sku) { variant.price = params.price; } }",
    "params": {
      "sku": "RED-M",
      "price": 125
    }
  }
}
```

The script iterates over the current array and replaces the price of the element with the matching SKU. You must decide what happens if the SKU is not found: do nothing, add a new variant, or report an error. You can use a boolean flag in the script and set `ctx.op = 'none'` or throw an error according to the chosen semantics.

If using read-modify-write in the application, combine it with optimistic concurrency or version control to prevent two concurrent requests from overwriting each other's changes.

## 10. Update Conflicts and `retry_on_conflict`

The Elasticsearch Update API reads the current document, applies the partial doc/script, and reindexes the modified document. If another update happens concurrently, the operation may encounter a version conflict.

`retry_on_conflict` allows Elasticsearch to retry the update when a conflict occurs:

```java
UpdateQuery updateQuery = UpdateQuery.builder("KB-1001")
    .withDocument(Document.create().append("stock", 30))
    .withRetryOnConflict(3)
    .build();
```

A value of `3` allows retrying up to three times per the API configuration. Retrying is helpful when many concurrent updates occur, but it is not a solution for all conflicts. If the update depends on stale business state or the caller needs to know the data changed, use optimistic concurrency.

### 10.1 Optimistic Concurrency with Sequence Number and Primary Term

Elasticsearch can guard updates using `if_seq_no` and `if_primary_term`:

```http
POST /products/_update/KB-1001?if_seq_no=12&if_primary_term=3
{
  "doc": {
    "price": 135
  }
}
```

The update succeeds only if the document is still at the sequence number and primary term the application read. If the document changed, Elasticsearch returns a version conflict; the application must re-read and decide whether to recompute the update or report a conflict.

In Spring Data, `UpdateQuery` may expose `ifSeqNo`/`ifPrimaryTerm` options depending on the version. Use them when you need to guarantee an update is based on the version read, rather than retrying blindly.

### 10.2 Choosing Retry vs. Optimistic Concurrency

| Need | Mechanism |
|---|---|
| Simple update that can be reapplied on conflict | `retry_on_conflict` |
| Caller needs to detect that the document changed since reading | `if_seq_no` + `if_primary_term` |
| Atomic increment/decrement updates | Script with params; consider retry policy |
| Business rules depend on old state and require re-evaluation | Optimistic concurrency + re-read |

## 11. Routing, Refresh, and Other Options

Besides ID and update content, `UpdateQuery` can carry several request options:

- **Routing:** use the same routing value used when indexing the document if the index uses custom routing.
- **Retry on conflict:** number of retries when an update conflict occurs.
- **Refresh policy:** controls when changes become visible in search.
- **Upsert:** creates the document if the ID does not yet exist.
- **Fetch source:** requests returning the source after the update if needed by the use case.
- **Sequence number/primary term:** optimistic concurrency if supported by the API version.

Example configuring routing and retry:

```java
UpdateQuery updateQuery = UpdateQuery.builder("KB-1001")
    .withDocument(Document.create().append("price", 135))
    .withRouting("tenant-42")
    .withRetryOnConflict(3)
    .build();
```

Routing must match the routing used when the document was indexed. If routing is omitted or incorrect, Elasticsearch may not find the document on the expected shard.

Do not set refresh to `IMMEDIATE` for every update just to read the data immediately. Frequent refreshes can degrade indexing performance. Use a refresh policy matching the API's consistency requirements; waiting for the default periodic refresh is usually appropriate for write-heavy workloads.

## 12. Bulk Updating Multiple Documents

If you need to update multiple documents from a list of IDs, avoid sending sequential individual requests when they can be batched into a bulk request. Spring Data Elasticsearch provides a `bulkUpdate(...)` API accepting a collection of `UpdateQuery` depending on the version.

Example constructing a list of updates:

```java
List<UpdateQuery> updates = List.of(
    UpdateQuery.builder("KB-1001")
        .withDocument(Document.create().append("price", 135))
        .build(),
    UpdateQuery.builder("KB-1002")
        .withDocument(Document.create().append("price", 145))
        .build(),
    UpdateQuery.builder("MS-2001")
        .withDocument(Document.create().append("stock", 50))
        .build()
);

operations.bulkUpdate(updates, IndexCoordinates.of("products"));
```

Bulk reduces network overhead and lets Elasticsearch process multiple operations in one request. However, a bulk request is not an atomic transaction: some items may succeed while others fail. Check each item's result according to your version's return API, record failed IDs, and retry selectively.

### 12.1 Splitting Bulk Requests into Moderate Batches

Do not cram hundreds of thousands of updates into a single request. Choose a batch size based on payload, latency, throughput, and cluster limits. Monitor for 429/rejected execution errors, retry with backoff, and avoid spawning excessive concurrent requests.

### 12.2 Bulk Update vs. `update_by_query`

- `bulkUpdate`: the application specifies each ID and partial update/script per document.
- `update_by_query`: Elasticsearch finds documents matching a query and applies the script/update to all matching documents.

If the list of IDs is known, bulk update is usually appropriate. If you need to modify all documents matching a condition, update by query may be more suitable, though you must understand conflicts, slicing, throttling, and cluster impact.

## 13. Update by Query and UpdateQuery Are Not the Same

`UpdateQuery` describes an update for a specific document ID. Update by query operates on a set of documents matching a query:

```http
POST /products/_update_by_query
{
  "query": {
    "term": {
      "status": "LEGACY"
    }
  },
  "script": {
    "lang": "painless",
    "source": "ctx._source.status = 'ARCHIVED'"
  }
}
```

Update by query can process large numbers of documents and has its own options such as `conflicts`, `slices`, `requests_per_second`, `refresh`, and `wait_for_completion`. Do not use it to replace a single `UpdateQuery` when the document ID is already known.

## 14. Mapping and Data Conversion

A partial doc must still be compatible with the index mapping. If `price` is `double`, sending an unparseable string can cause a mapping error. If a field is `keyword`, send an appropriate value. If a field uses a custom date format, date values must match that format.

Example entity:

```java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Double)
    private Double price;

    @Field(type = FieldType.Integer)
    private Integer stock;
}
```

A partial `Document` should send numbers of the right type:

```java
Document partial = Document.create()
    .append("price", 135.0)
    .append("stock", 30);
```

When using `Document` directly, do not assume all entity converter metadata automatically applies to keys and values. If you need custom conversion, date/time serialization, or field name mapping, consider using the converter to create the `Document` or inspect the actual JSON request.

## 15. `UpdateResponse` Results

The Update API can return statuses such as:

- `updated`: the document was updated.
- `created`: the document was created via upsert.
- `noop`: the script or request made no change to the document.
- `not_found`: the document did not exist in certain response/API flows.
- Version conflict or mapping/request error: the operation failed.

The response may contain version, sequence number, and primary term depending on the API. Handle these statuses per business logic; do not treat every non-throwing response as "data was modified". If using a script with `ctx.op = 'none'`, `noop` is an intentional outcome.

## 16. Common Mistakes

### 16.1 Sending the Whole Entity When Only Updating One Field

If you serialize the whole entity, null fields or default values may overwrite existing data. Build a partial `Document` containing only fields allowed to change.

### 16.2 Assuming Absent Fields and Null Fields Are the Same

Absent fields are normally preserved; fields sent as `null` may be set to `null`. The API needs to clearly distinguish omitting a field from clearing it.

### 16.3 Updating an Array Element with a Partial Array

Elasticsearch does not automatically merge arrays by `sku` or child ID. Sending a new array can replace the entire array. Use a script or read-modify-write with concurrency control.

### 16.4 Forgetting Upsert

Updating a non-existent document will not create it automatically unless upsert is configured. Use `doc_as_upsert` or a separate upsert when business rules allow.

### 16.5 Using `doc_as_upsert` with a Payload Missing Required Fields

If the document does not yet exist, the partial doc becomes the new document. Ensure it contains sufficient minimum data or provide a complete upsert document.

### 16.6 Computing the New Value in the Application and Overwriting

Reading stock, adding/subtracting in Java, and then updating can lose concurrent requests' changes. Use an atomic script or appropriate optimistic concurrency.

### 16.7 Using the Wrong Routing

Documents indexed with custom routing must be updated with the same routing. Otherwise, Elasticsearch may fail to locate the document.

### 16.8 Not Handling Version Conflicts

Multiple writers can update the same ID. Choose `retry_on_conflict` or optimistic concurrency according to business semantics and record conflicts.

### 16.9 Treating a Bulk Request as a Transaction

Bulk requests can partially succeed. Inspect item-level results, retry selectively, and design idempotent operations.

### 16.10 Refreshing Immediately After Every Update

Immediate refresh increases overhead. Use it only when immediate read-after-write is required; otherwise, use the default refresh policy or batch accordingly.

## 17. Workflow for Building a Safe Update Service

An update service can be structured into the following steps:

1. Validate the ID and authorization to update the document.
2. Permit only fields on the business allowlist.
3. Distinguish omitted fields from fields explicitly requested to be set to `null`.
4. Validate data types and value bounds.
5. Build a partial `Document` containing only the fields to change.
6. Choose partial update, script, or upsert as required.
7. Add routing/concurrency options if required by the index.
8. Execute using `ElasticsearchOperations.update(...)`.
9. Inspect `UpdateResponse` and handle not-found/noop/conflict.
10. Refresh immediately only if the API must read changes right away.

For multi-document updates, use bulk in moderate batches and check each item's result. For complex array updates or atomic calculations, consider Painless scripts with `params`.

## 18. Comprehensive Service Example

```java
import java.util.Map;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.document.Document;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.UpdateQuery;
import org.springframework.data.elasticsearch.core.query.UpdateResponse;
import org.springframework.stereotype.Service;

@Service
public class ProductUpdateService {

    private static final IndexCoordinates PRODUCTS =
        IndexCoordinates.of("products");

    private final ElasticsearchOperations operations;

    public ProductUpdateService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public UpdateResponse changePrice(String id, double price) {
        if (price < 0) {
            throw new IllegalArgumentException("price must be non-negative");
        }

        Document partial = Document.create()
            .append("price", price);

        UpdateQuery update = UpdateQuery.builder(id)
            .withDocument(partial)
            .withRetryOnConflict(3)
            .build();

        return operations.update(update, PRODUCTS);
    }

    public UpdateResponse increaseStock(String id, int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }

        UpdateQuery update = UpdateQuery.builder(id)
            .withScript("ctx._source.stock += params.amount")
            .withLang("painless")
            .withParams(Map.of("amount", amount))
            .withRetryOnConflict(3)
            .build();

        return operations.update(update, PRODUCTS);
    }

    public UpdateResponse createOrUpdate(
            String id,
            String sku,
            String name,
            double price) {

        Document partial = Document.create()
            .append("price", price);

        Document initial = Document.create()
            .append("sku", sku)
            .append("name", name)
            .append("price", price)
            .append("stock", 0)
            .append("active", true);

        UpdateQuery update = UpdateQuery.builder(id)
            .withDocument(partial)
            .withUpsert(initial)
            .build();

        return operations.update(update, PRODUCTS);
    }
}
```

The example illustrates three different needs: updating a field via partial doc, modifying stock via script addition, and upserting with separate creation content. Specific script/builder methods should be verified against the Spring Data Elasticsearch version in use.

## 19. Usage Principles

- Use `UpdateQuery` when updating a document by ID without rewriting the entire source.
- Use a partial `Document` containing only fields allowed to change.
- Understand that omitted fields, `null` fields, and remove operations have different semantics.
- Verify field names against the Elasticsearch mapping, especially when Java properties have different names.
- Do not assume object arrays merge element-by-element; use scripts or read-modify-write with concurrency control.
- Use `doc_as_upsert` when the partial doc suffices as a new document; use a separate `upsert` when creation content differs from update content.
- Use scripts with `params` for calculations based on current state and avoid concatenating inputs into script source.
- Use `retry_on_conflict` for retryable conflicts; use sequence number/primary term when optimistic concurrency is required.
- Pass the same routing used when the document was indexed.
- Use bulk updates for multiple IDs, but process item-level results because bulk is not atomic.
- Distinguish ID-based updates from update by query.
- Do not force immediate refresh unless immediate read-after-write is required.
- Inspect `UpdateResponse` and handle `updated`/`created`/`noop`/`not-found`/`conflict` according to business logic.

## 20. Summary

`UpdateQuery` is how Spring Data Elasticsearch models Update API operations for a single document. With `withDocument(Document)`, the application sends a partial doc containing only fields to change; omitted fields are normally preserved. This differs from `save(entity)`/document indexing, which typically rewrites the source from the entity's content. Distinguish absent fields from `null`, and especially remember that arrays do not automatically merge element-by-element by key.

When a document does not exist yet, you can use `doc_as_upsert` if the partial doc suffices as a new document, or provide a separate `upsert`. When updates depend on current state, Painless scripts with `params` allow atomic calculations inside Elasticsearch. With concurrent writers, choose `retry_on_conflict` or optimistic concurrency via sequence number/primary term. For multiple IDs, use bulk updates in batches and inspect item-level results.

In Spring Data Elasticsearch, build `UpdateQuery`, choose the right ID/document/script/options, and call `ElasticsearchOperations.update(...)` with `IndexCoordinates`. Restrict updatable fields at the business layer, verify mappings/routing, handle responses explicitly, and use immediate refresh only when necessary. Designing partial docs and concurrency properly prevents lost fields, lost updates, and data corruption when updating documents.

## References

- [Elasticsearch — Update API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-update.html)
- [Elasticsearch — Update by query API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-update-by-query.html)
- [Elasticsearch — Painless scripting](https://www.elastic.co/guide/en/elasticsearch/painless/current/painless-guide.html)
- [Spring Data Elasticsearch Reference — Template API](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch API — UpdateQuery](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/query/UpdateQuery.html)
