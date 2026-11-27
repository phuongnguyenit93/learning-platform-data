# Distinguishing Full-Document Indexing and Partial Updates

In Elasticsearch, updating a document can be performed in two main ways:

- **Full-document indexing**: sending a new representation of the document with the same ID. The current `_source` content is replaced by the new content.
- **Partial update**: sending only the fields that need to change or a script. Elasticsearch applies the changes to the existing document and preserves the untouched fields.

Both operations may use the same document ID, but they have different semantics. Choosing the wrong one can cause data loss: a DTO containing only a few fields sent through `save()` can replace the entire source and cause the remaining fields to disappear. Conversely, a partial update is suitable when only a few attributes change, but you must explicitly handle null fields, arrays, nested objects, missing documents, and concurrent write conflicts.

In Spring Data Elasticsearch, `save()` typically represents a document indexing operation; partial updates are performed via `ElasticsearchOperations` and `UpdateQuery`, bulk updates, or the Elasticsearch Java API Client. This lesson distinguishes their semantics, illustrates the REST DSL and Java APIs, and shows how to choose the safe operation based on business requirements.

## 1. Two Ways to Update and Their Core Differences

Suppose a document in the `products` index currently has the following source:

~~~json
{
  "sku": "SKU-1001",
  "name": "Wireless Mouse",
  "priceInCents": 259900,
  "active": true,
  "description": "Bluetooth mouse with rechargeable battery",
  "stock": 42
}
~~~

The application only wants to change the price to `279900`.

If sending the full document via the Index API:

~~~http
PUT /products/_doc/P-1001
{
  "sku": "SKU-1001",
  "name": "Wireless Mouse",
  "priceInCents": 279900,
  "active": true,
  "description": "Bluetooth mouse with rechargeable battery",
  "stock": 42
}
~~~

Elasticsearch replaces the document's source with the JSON that was just sent. All fields that need to be retained must be present in the new representation.

If using the Update API with a partial document:

~~~http
POST /products/_update/P-1001
{
  "doc": {
    "priceInCents": 279900
  }
}
~~~

Only `priceInCents` is updated. Fields such as `sku`, `name`, `description`, and `stock` continue to keep their existing values.

| Criterion | Full-document indexing | Partial update |
|---|---|---|
| Elasticsearch API | Index API | Update API |
| Payload sent | Entire new document | Only changed fields or a script |
| Omitted fields | No longer in the new source | Preserved |
| Fields sent as `null` | Depends on JSON/converter; the new source may contain `null` or omit them based on configuration | Set to `null` if the `null` field is sent |
| Non-existent document | Created according to Index API semantics | Fails with not found by default, unless upsert is configured |
| Usage in Spring Data | `save()` / `saveAll()` | `UpdateQuery`, bulk update, or client API |
| Best suited for | Writing new documents or replacing a full snapshot | Modifying part of an existing document |

Both approaches ultimately cause Elasticsearch to update the indexed structure for the document. A partial update is not a physical column-level modification like in a relational database; Elasticsearch retrieves the current source, applies the patch/script, and then reindexes the modified document.

## 2. Index API: Replacing the Entire Document

The Index API writes a document by ID. If the ID does not exist yet, the document is created. If the ID already exists, the old source is replaced by the new source.

~~~http
PUT /products/_doc/P-1001
{
  "sku": "SKU-1001",
  "name": "Wireless Mouse",
  "priceInCents": 279900,
  "active": true,
  "stock": 42
}
~~~

If the old source had `description` but the new JSON does not include that field, the new source will no longer have `description`.

This can be valid if the application is writing a full snapshot and intentionally wants to replace the document state. It can cause data loss if the application only has partial information.

### 2.1. `save()` in Spring Data Elasticsearch

With a repository:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
~~~

You can save:

~~~java
Product product = loadCompleteProduct();
product.setPriceInCents(279900L);

productRepository.save(product);
~~~

Or using Operations:

~~~java
Product saved = operations.save(product);
~~~

`save()` is a document write operation by ID and typically uses the Index API. If the ID already exists, the document is reindexed with the content from the serialized object. Therefore, the object passed in must represent the complete state that the application wants to store.

Dangerous example:

~~~java
Product patch = new Product();
patch.setId("P-1001");
patch.setPriceInCents(279900L);

productRepository.save(patch);
~~~

If this object only has an ID and a price, other fields may be lost from the source after `save`, because the object is converted into a new document. The exact outcome also depends on converter configuration for null fields, but `save()` should not be used as a patch command.

### 2.2. `saveAll()` Is Also Not a Partial Update

`saveAll()` typically writes multiple documents using a bulk index operation. Each object is still treated as a document to be indexed in full.

~~~java
productRepository.saveAll(products);
~~~

If the list contains objects with only a few fields, you should not assume the old fields will be preserved. Bulk is merely a more efficient way to send multiple operations; it does not change the semantics of each individual index operation.

### 2.3. Index API and Create-Only

The Index API can create a new document or replace one by ID. If you need to guarantee creation only when the ID does not yet exist, Elasticsearch provides the create operation:

~~~http
PUT /products/_create/P-1001
{
  "sku": "SKU-1001",
  "name": "Wireless Mouse",
  "priceInCents": 259900
}
~~~

If the ID already exists, create-only returns a conflict instead of overwriting. This is useful when IDs must be unique and the application wants to detect duplicate creation.

Do not confuse create-only with partial update: create-only only controls the creation condition, not field update semantics.

## 3. Update API: Modifying Part of a Document

The Update API accepts one of the following main forms:

- `doc`: a partial document containing the fields to change.
- `script`: a Painless script operating on `_source`.
- `upsert`: a document used when the ID does not yet exist.
- `doc_as_upsert`: uses `doc` itself as the newly created document if it does not yet exist.

Example changing only the price:

~~~http
POST /products/_update/P-1001
{
  "doc": {
    "priceInCents": 279900
  }
}
~~~

After the update, the document still preserves the other fields.

### 3.1. Fields Omitted from a Partial Document Are Preserved

Suppose the current source is:

~~~json
{
  "name": "Wireless Mouse",
  "priceInCents": 259900,
  "active": true,
  "stock": 42
}
~~~

Sending:

~~~json
{
  "doc": {
    "stock": 35
  }
}
~~~

The resulting source after the update is:

~~~json
{
  "name": "Wireless Mouse",
  "priceInCents": 259900,
  "active": true,
  "stock": 35
}
~~~

Fields not listed in `doc` are retained. This is the most important difference compared to full-document indexing.

### 3.2. A Partial Update Is Not a Byte-Level Patch

The Update API processes the document on the Elasticsearch side: it reads the current source, applies the partial document or script, and then reindexes the modified document. Therefore:

- The application does not need to fetch the entire object and send it back.
- It does not mean Elasticsearch only writes a few bytes or a single column.
- Large documents and frequent updates still incur the cost of reading the source, processing, and indexing.
- `_source` must be enabled for the Update API to function under its normal mechanism.

If multiple fields need to be changed at once, a single partial document can contain multiple fields:

~~~http
POST /products/_update/P-1001
{
  "doc": {
    "priceInCents": 279900,
    "stock": 35,
    "active": false
  }
}
~~~

This operation updates all sent fields within the same update request.

## 4. Distinguishing Omitted Fields, Null Fields, and Removing Fields

This is a common source of bugs when building patch APIs.

### 4.1. Not Sending a Field

If the partial document does not contain the `description` field, the old value is preserved:

~~~json
{
  "doc": {
    "priceInCents": 279900
  }
}
~~~

`description` is left unchanged.

### 4.2. Sending a Field with `null`

If you send:

~~~json
{
  "doc": {
    "description": null
  }
}
~~~

Elasticsearch updates the `description` field to `null` in `_source` according to update semantics. The field may not have an indexed value for querying unless the mapping uses `null_value` for indexing purposes. `null_value` does not replace the `null` value in `_source`.

`null` is different from omitting a field. With a partial update, `null` is a passed-in value and may mean clearing the business value, though the field can still appear in the source as `null`.

### 4.3. Completely Removing a Field from `_source`

If you want to remove the field key from the JSON source, use a script:

~~~http
POST /products/_update/P-1001
{
  "script": {
    "source": "ctx._source.remove('description')"
  }
}
~~~

The script removes the `description` key from `_source`. After the update, the field no longer exists in the source.

Do not use `null` if the business requirement demands that the field disappear completely. Choose clear API semantics:

| Intent | Representation |
|---|---|
| Leave field unchanged | Omit the field from the partial document |
| Set field to `null` | Send the field with `null` |
| Remove key from source | Script `ctx._source.remove('field')` |
| Set default value | Send the specific value or use a script |

### 4.4. Java `null` and JSON Serialization

When constructing a `Document` or serializing a DTO, converter configuration may determine whether Java `null` fields are written to JSON or omitted. Therefore, do not rely on a DTO with nullable fields to represent all three states ("unchanged", "delete", and "set to null") at the same time.

For HTTP PATCH, use a representation that can distinguish a field that was not provided from a field explicitly provided as `null`. You can use `JsonNode`, an `Optional`-style wrapper with appropriate semantics, or a command object with separate presence flags.

## 5. Partial Updates with Nested Objects and Arrays

For nested objects, partial documents are typically merged according to the object structure. However, you should verify behavior against your actual data and Elasticsearch version, especially when objects contain arrays or when the application depends on preserving individual sub-fields.

Example source:

~~~json
{
  "name": "Wireless Mouse",
  "shipping": {
    "city": "Ho Chi Minh City",
    "district": "District 1",
    "postalCode": "700000"
  }
}
~~~

Partial update:

~~~http
POST /products/_update/P-1001
{
  "doc": {
    "shipping": {
      "district": "District 3"
    }
  }
}
~~~

With object merging, the goal is to change only `shipping.district` and preserve the other sub-fields. If the application needs an absolute guarantee against overwriting a nested object in a complex structure, use a script that assigns the exact path:

~~~http
POST /products/_update/P-1001
{
  "script": {
    "source": "ctx._source.shipping.district = params.district",
    "params": {
      "district": "District 3"
    }
  }
}
~~~

If `shipping` might not exist yet, the script must check and initialize the object before assigning.

### 5.1. Arrays Are Typically Replaced, Not Automatically Appended

Suppose the source has:

~~~json
{
  "tags": ["wireless", "bluetooth"]
}
~~~

Sending a partial update:

~~~json
{
  "doc": {
    "tags": ["ergonomic"]
  }
}
~~~

The `tags` field is updated with the new array; you should not expect Elasticsearch to automatically append the new element to the old array.

To append an element, use a script:

~~~http
POST /products/_update/P-1001
{
  "script": {
    "source": "if (ctx._source.tags == null) { ctx._source.tags = []; } ctx._source.tags.add(params.tag)",
    "params": {
      "tag": "ergonomic"
    }
  }
}
~~~

To remove an element:

~~~http
POST /products/_update/P-1001
{
  "script": {
    "source": "if (ctx._source.tags != null) { ctx._source.tags.removeIf(tag -> tag == params.tag); }",
    "params": {
      "tag": "bluetooth"
    }
  }
}
~~~

Painless supports a specific set of syntax and collection APIs depending on context and version. Test scripts on your project's Elasticsearch version, especially when using lambdas or collection methods.

## 6. Partial Updates with `ElasticsearchOperations`

In Spring Data Elasticsearch, `ElasticsearchOperations` provides an abstraction for operations beyond basic repository CRUD. In modern versions, `UpdateQuery` describes an update request.

Conceptual example using the Spring Data Elasticsearch 5.x API:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.document.Document;
import org.springframework.data.elasticsearch.core.query.UpdateQuery;
import org.springframework.data.elasticsearch.core.query.UpdateResponse;

Document partialDocument = Document.create();
partialDocument.put("priceInCents", 279900L);
partialDocument.put("stock", 35);

UpdateQuery updateQuery = UpdateQuery.builder("P-1001")
    .withDocument(partialDocument)
    .build();

UpdateResponse response =
    operations.update(updateQuery, Product.class);
~~~

`Document` in the example is `org.springframework.data.elasticsearch.core.document.Document`, not the `Product` entity. It holds the fields to patch.

Some versions provide overloads accepting `IndexCoordinates` to specify the index explicitly:

~~~java
UpdateResponse response = operations.update(
    updateQuery,
    Product.class,
    IndexCoordinates.of("products")
);
~~~

Overload signatures, response types, and builder methods can vary across minor versions. Check `ElasticsearchOperations`, `UpdateQuery.Builder`, and `UpdateResponse` in your project's dependencies. If the project lacks a particular overload, use the available API or the Elasticsearch Java API Client directly; do not assume a framework method exists.

### 6.1. Creating a Partial Document

You can create a `Document` from a map:

~~~java
Map<String, Object> fields = Map.of(
    "priceInCents", 279900L,
    "stock", 35
);

Document partialDocument = Document.from(fields);
~~~

How `Document` is instantiated and its factory methods depend on the version. If using `Map.of(...)`, you cannot pass `null` because Java's `Map.of` does not allow null keys or values. Use a structure capable of representing `null` explicitly if that is your intent.

### 6.2. Updating by ID and Target Index

An update needs to identify the document ID and target index or alias. For repositories with a default index name, you can pass the entity class so Spring Data resolves the index from the mapping. If the application writes to a dynamic index or alias, pass the corresponding `IndexCoordinates`.

Do not assume `UpdateQuery` automatically infers the right index if the domain type has no mapping or if the target index differs from `@Document(indexName=...)`.

## 7. Upsert: Update or Create New

By default, the Update API requires the document to already exist. If the ID does not exist yet, the request may return a document-missing error.

There are two common ways to define data when the document does not yet exist:

- `doc_as_upsert`: uses `doc` itself as the source when creating a new document.
- `upsert`: provides a separate document to use when the ID does not yet exist.

### 7.1. `doc_as_upsert`

~~~http
POST /products/_update/P-1001
{
  "doc": {
    "sku": "SKU-1001",
    "name": "Wireless Mouse",
    "stock": 35
  },
  "doc_as_upsert": true
}
~~~

If `P-1001` already exists, the fields in `doc` are updated. If it does not yet exist, `doc` is used to create a new document.

This is useful when the update payload is also sufficient to create the initial document. If the payload only contains `stock`, the new document might only contain `stock` and lack required business fields.

### 7.2. Separate `upsert`

~~~http
POST /products/_update/P-1001
{
  "doc": {
    "stock": 35
  },
  "upsert": {
    "sku": "SKU-1001",
    "name": "Wireless Mouse",
    "priceInCents": 259900,
    "stock": 35,
    "active": true
  }
}
~~~

If the document exists, only `stock` is updated. If it does not exist, Elasticsearch indexes the source specified in `upsert`.

Use a separate `upsert` when the creation structure needs to be more complete than the patch payload.

### 7.3. `scripted_upsert`

If you use a script and want it to run even when the document does not yet exist, you can use `scripted_upsert` along with `upsert`:

~~~http
POST /products/_update/P-1001
{
  "scripted_upsert": true,
  "script": {
    "source": "ctx._source.stock = (ctx._source.stock == null ? 0 : ctx._source.stock) + params.amount",
    "params": {
      "amount": 5
    }
  },
  "upsert": {}
}
~~~

The script is executed for the non-existent document case according to the `scripted_upsert` configuration. Ensure the script initializes required fields and the upsert source is valid for the mapping and business rules.

`doc_as_upsert`, `upsert`, and `scripted_upsert` have different semantics. Choose the one appropriate for the write flow; do not enable one merely to avoid document-missing errors without defining the initial state.

## 8. Script Update: Modifying Data with Logic

A partial document works well when the exact new values are known. A script is suitable when the change depends on the current value or requires collection manipulation.

Example incrementing `stock` by an amount:

~~~http
POST /products/_update/P-1001
{
  "script": {
    "lang": "painless",
    "source": "ctx._source.stock += params.amount",
    "params": {
      "amount": 5
    }
  }
}
~~~

If `stock` might not exist yet, the script should handle it:

~~~http
POST /products/_update/P-1001
{
  "script": {
    "lang": "painless",
    "source": "if (ctx._source.stock == null) { ctx._source.stock = params.amount; } else { ctx._source.stock += params.amount; }",
    "params": {
      "amount": 5
    }
  }
}
~~~

### 8.1. Setting Values Conditionally

For example, only update the status when the order has not been cancelled:

~~~http
POST /orders/_update/O-1001
{
  "script": {
    "source": "if (ctx._source.status != 'CANCELLED') { ctx._source.status = params.status; } else { ctx.op = 'none'; }",
    "params": {
      "status": "SHIPPED"
    }
  }
}
~~~

`ctx.op = 'none'` instructs Elasticsearch not to write changes if the condition is not met. Update scripts can use `ctx.op` to control the operation according to the supported context.

Do not interpolate user strings directly into `source`. Keep the script stable and pass dynamic data via `params` to reduce injection risks and improve compiled script reuse.

### 8.2. Deleting a Document via Script Is Not Deleting a Field

An update script can control the operation, for example `ctx.op = 'delete'` to delete the document within the update context. By contrast, `ctx._source.remove('field')` only removes a single field from the document's source.

Clearly distinguish these two intents to avoid deleting the entire document when you only want to remove an attribute.

## 9. Conditional Updates: Update By Query

If you need to update multiple documents selected by a query, you can use the Update By Query API:

~~~http
POST /products/_update_by_query
{
  "query": {
    "term": {
      "category": "clearance"
    }
  },
  "script": {
    "source": "ctx._source.active = false"
  }
}
~~~

Elasticsearch finds the documents matching the query and runs the script for each document. This is a multi-document operation, suitable for data migrations or bulk conditional updates.

### 9.1. Update By Query Is Not a Whole-Set Transaction

Update By Query does not guarantee that the entire set of documents is updated in an atomic transaction. The following can occur:

- Some documents update successfully while others fail.
- Version conflicts.
- Timeouts or task cancellation.
- Need to retry or resume based on task results.
- Heavy cluster load when processing many documents.

Inspect the response and failures, keep the query sufficiently narrow, and consider `conflicts=proceed`, throttling, and slices where appropriate. `conflicts=proceed` allows the operation to continue when conflicts occur but does not resolve conflict logic automatically; conflicted documents may still remain un-updated.

### 9.2. Update By Query and Spring Data Elasticsearch

Support for Update By Query in Spring Data abstractions varies by version. If `ElasticsearchOperations` in your dependency does not expose a suitable API, you can use the Elasticsearch Java API Client directly to build an `UpdateByQueryRequest`.

Do not confuse `UpdateQuery` for a single document with Update By Query. One targets a document by ID; the other selects multiple documents by query.

## 10. Bulk Updates and Multiple Documents

If you have a list of IDs and each document needs a partial update, you can use a bulk update to reduce network requests.

Conceptual example:

~~~java
List<UpdateQuery> updates = new ArrayList<>();

updates.add(
    UpdateQuery.builder("P-1001")
        .withDocument(documentForFirstProduct)
        .build()
);

updates.add(
    UpdateQuery.builder("P-1002")
        .withDocument(documentForSecondProduct)
        .build()
);

operations.bulkUpdate(
    updates,
    Product.class,
    IndexCoordinates.of("products")
);
~~~

The exact `bulkUpdate` overload names and response types depend on the Spring Data Elasticsearch version. Verify them against your project's `ElasticsearchOperations`.

A bulk request groups multiple independent operations into a single request. One failing item does not necessarily cause all other items to fail. Always check item-level results and handle per-document retries appropriately.

If each document requires different logic, create a separate `UpdateQuery` for each ID. If the same script or condition applies to a large set of documents, Update By Query may be more suitable.

## 11. Concurrent Write Conflicts and Optimistic Concurrency

Two requests may read the same document and then write changes. If both use a full index with the old source, the later request can overwrite the earlier request's changes. This is a lost update.

Example:

1. Request A reads `stock = 10`.
2. Request B reads `stock = 10`.
3. A writes `stock = 8`.
4. B writes `stock = 7` based on the stale read.
5. The final result is `7`, instead of `5` if both orders were subtracting `2` and `3`.

An update script that increments/decrements based on the current source can mitigate application-tier read-modify-write lost updates because the script executes on Elasticsearch. However, the business logic must still define rules for conflicts and retries.

### 11.1. Optimistic Concurrency with Sequence Number and Primary Term

Elasticsearch supports optimistic concurrency control using `if_seq_no` and `if_primary_term`. The client sends the version values it previously read; Elasticsearch only updates if the document is still at that exact version.

REST example:

~~~http
POST /products/_update/P-1001?if_seq_no=12&if_primary_term=3
{
  "doc": {
    "priceInCents": 279900
  }
}
~~~

If the document has changed since it was read, Elasticsearch returns a version conflict. The application can re-read, re-evaluate business rules, and decide whether to retry or return a conflict to the caller.

Spring Data Elasticsearch has version/concurrency mechanisms depending on API generation and mapping. `@Version` is the annotation to explore when using optimistic locking on entities:

~~~java
@Version
private Long version;
~~~

The signature and integration semantics of `@Version` depend on the Spring Data Elasticsearch version and how the client executes operations. With `UpdateQuery` or custom client requests, verify how concurrency tokens are passed; do not assume every update overload automatically uses the same token as repository `save`.

### 11.2. `retry_on_conflict`

The Update API provides the `retry_on_conflict` option so Elasticsearch retries the update when a version conflict occurs:

~~~http
POST /products/_update/P-1001?retry_on_conflict=3
{
  "script": {
    "source": "ctx._source.stock += params.amount",
    "params": {
      "amount": 1
    }
  }
}
~~~

This option is useful for updates based on the current state, such as incrementing a counter. Elasticsearch reads the newer version and retries the script up to the configured number of times.

Do not enable retries blindly for every business operation. The script must be safe to re-run against a newer source; if the operation is not idempotent or has external side effects outside Elasticsearch, design a separate mechanism.

## 12. No-op Detection and Refresh

The Update API can detect requests that produce no actual change and return a `noop` result instead of rewriting the document. This can be controlled via `detect_noop`:

~~~http
POST /products/_update/P-1001
{
  "doc": {
    "active": true
  },
  "detect_noop": true
}
~~~

If `active` is already `true`, Elasticsearch can determine that reindexing the document is unnecessary.

Refresh is a separate concept. A successful update does not mean the Search API sees the new data immediately; Elasticsearch is a near-real-time system. You can use an appropriate refresh policy on the write operation or wait for the natural refresh cycle.

Do not enable `refresh=wait_for` after every update in high-throughput write flows unless immediate visibility is required. Frequent refreshes can hurt indexing performance.

## 13. Mapping and Data Types During Updates

Partial updates do not allow changing the mapping type of an existing field.

For example, `priceInCents` is mapped as `long`. Sending a string:

~~~json
{
  "doc": {
    "priceInCents": "two hundred"
  }
}
~~~

can cause a parsing or mapping error. If a field's type needs to change, you typically must create a new index with the appropriate mapping and reindex the data.

Adding a new field can trigger dynamic mapping if the index permits it. However, relying on dynamic mapping for production data can lead to unintended field types. Define explicit mappings for important fields.

Partial updates do not automatically update Java annotations or mapping metadata. The index mapping and entity serialization must stay synchronized.

## 14. Choosing Full Index or Partial Update?

You can use the following scenarios to decide:

| Scenario | Typically suitable option |
|---|---|
| Creating a new document from a full object | `save()` / Index API |
| Syncing a full snapshot from an authoritative source | Index API |
| Replacing the entire source with a new version | Index API |
| Changing only a few known fields | Update API with `doc` |
| Incrementing/decrementing a counter based on current value | Script update |
| Adding/removing elements in an array | Script update |
| Removing a field from source | Script `ctx._source.remove(...)` |
| Creating if absent, updating if present | Update API with appropriate upsert |
| Updating multiple IDs with different patches | Bulk update |
| Updating all documents matching a condition | Update By Query |
| Needing to detect concurrent writes | Optimistic concurrency |
| Updating all data after a mapping change | Create a new index and reindex |

An easy rule of thumb: `save()` is for objects representing the full document; partial updates are for commands describing only the changes.

## 15. Service Example: Safely Updating a Single Field

Suppose an API allows changing a product's price. The service does not need to read the entire entity and save it back.

~~~java
@Service
public class ProductService {

    private final ElasticsearchOperations operations;

    public ProductService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void changePrice(String productId, long newPriceInCents) {
        if (newPriceInCents < 0) {
            throw new IllegalArgumentException("Price must be non-negative");
        }

        Document patch = Document.create();
        patch.put("priceInCents", newPriceInCents);

        UpdateQuery updateQuery = UpdateQuery.builder(productId)
            .withDocument(patch)
            .build();

        operations.update(
            updateQuery,
            Product.class,
            IndexCoordinates.of("products")
        );
    }
}
~~~

The example uses common Spring Data Elasticsearch 5.x API patterns. Verify imports, overloads, and response types in your project's version. If the document does not exist, the operation may throw an error by default; the service must decide whether to return 404, use upsert, or create a separate document.

The advantage of this approach is that the command carries only the field that needs to change, reducing the risk of overwriting other fields the service does not own.

## 16. Service Example: Incrementing Stock with a Script

If the requirement is to increase `stock` by an amount, there is no need to read `stock` into Java and add to it:

~~~java
public void increaseStock(String productId, long amount) {
    if (amount <= 0) {
        throw new IllegalArgumentException("Amount must be positive");
    }

    UpdateQuery updateQuery = UpdateQuery.builder(productId)
        .withScript(
            "if (ctx._source.stock == null) { " +
            "ctx._source.stock = params.amount; " +
            "} else { ctx._source.stock += params.amount; }"
        )
        .withParams(Map.of("amount", amount))
        .build();

    operations.update(
        updateQuery,
        Product.class,
        IndexCoordinates.of("products")
    );
}
~~~

Builder method names and script parameter types can differ across minor versions. Some APIs require a dedicated `Script` object or separate script type configuration. Check `UpdateQuery.Builder` in your dependency.

If the requirement is to prevent `stock` from becoming negative or exceeding available inventory, the script must check the condition and report an appropriate result. Do not simply add/subtract and hope the Java layer has controlled all concurrent requests.

## 17. PATCH API and Command Object Design

An HTTP PATCH endpoint typically represents a partial change:

~~~http
PATCH /products/P-1001
Content-Type: application/json

{
  "priceInCents": 279900
}
~~~

Do not deserialize the payload into a full `Product` entity and call `repository.save()` if fields absent from the request become `null` or default values.

Instead, use a patch DTO:

~~~java
public record ProductPatchRequest(
    Long priceInCents,
    Boolean active,
    Integer stock
) {
}
~~~

However, the DTO above still needs clear semantics for `null`:

- An omitted field means no change.
- A field sent as `null` may mean setting `null` or removing.
- Primitives like `boolean` or `int` cannot distinguish missing from `false`/`0` after deserialization in many configurations.

You can use `JsonNode`, a wrapper like `PatchField<T>`, or a custom deserializer to preserve whether a field appeared in the request.

After validation, the service constructs a `Document` containing only the fields actually requested for update. This is a critical boundary between the API contract and the Elasticsearch Update API.

## 18. Common Mistakes

| Symptom | Possible cause | Resolution |
|---|---|---|
| Old fields disappear after `save` | Input object only contained partial data and Index API replaced the source | Use a full object or `UpdateQuery` |
| Partial update does not change the field | Wrong field name or `Document` lacks the expected key | Inspect the actual JSON request |
| Field unexpectedly becomes `null` | DTO `null` was serialized as a `null` field | Distinguish missing fields from `null` in the patch DTO |
| Wanted to remove field, but still see `null` | Sending `null` only sets a `null` value | Use a script to remove from `_source` |
| Array is completely replaced | Partial `doc` assigns a new array | Use an append/remove script if manipulating individual elements |
| Updating non-existent document fails | Upsert is not configured | Use upsert or handle not found |
| Update script errors on missing field | Script accesses an uninitialized field | Check and initialize the field in Painless |
| Mapping exception | Sent value is incompatible with field type | Check the mapping and data types |
| Concurrent writes lose changes | Full index from stale source or lack of concurrency control | Use script updates, optimistic concurrency, and handle conflicts |
| Some items fail in bulk update | Bulk items are independent and can fail individually | Inspect each item result |
| Update By Query updates only partially | Conflicts, timeouts, or task failures | Check failures/task status and retry in a controlled manner |
| Search does not see updated data yet | Not refreshed yet | Use an appropriate refresh policy |
| `UpdateQuery` fails to compile | Builder/API differs across versions | Check dependency Javadoc |
| `@Version` does not prevent conflicts as expected | Update path does not pass the token as assumed | Verify the concurrency API for your exact version |

## 19. Testing Semantics Instead of Just Request Success

Integration tests should verify the data after the operation.

### 19.1. Testing That Indexing Replaces the Entire Source

1. Save a `Product` with `name`, `price`, `stock`, and `description`.
2. Create an object with the same ID containing only `name` and `price`.
3. Call `save`.
4. Read the document back and verify the replacement semantics under the current mapping/converter.

This test catches accidental use of `save` for patch objects.

### 19.2. Testing That Partial Updates Preserve Other Fields

1. Save a complete `Product`.
2. Send an `UpdateQuery` containing only `priceInCents`.
3. Refresh the index if the test reads via the Search API.
4. Read the document back.
5. Verify that `price` changed while `name`, `stock`, and `description` remain intact.

### 19.3. Testing `null`, Remove, and Arrays

Write dedicated tests for:

- Omitted field: old value is preserved.
- Sent `null`: source has `null` per intended semantics.
- Remove script: key disappears from source.
- Array patch: confirm the array is replaced.
- Append/remove script: confirm elements are added or removed properly.

### 19.4. Testing Upsert and Concurrency

- Updating a non-existent ID without upsert produces the expected outcome.
- `doc_as_upsert` creates the document from the payload.
- `upsert` creates the full source as configured.
- Version conflicts are handled per application policy.
- `retry_on_conflict` is only used with scripts safe to re-execute.

For tests reading immediately after writes, remember that the Elasticsearch Search API is near-real-time. You may need a refresh in tests; do not force a refresh after every operation in production.

## 20. Workflow for Choosing an Update Operation

When building a data-writing service, determine:

1. Does the input object represent the entire document or only a portion?
2. Should fields absent from the request remain unchanged, be deleted, or receive default values?
3. If the document does not exist, should it return not found, create a new one, or use upsert?
4. Does the change depend on current values?
5. Are there operations on arrays or nested objects?
6. Can multiple requests update the same document concurrently?
7. Is optimistic concurrency or retry needed?
8. Are you updating one ID, multiple IDs, or all documents matching a query?
9. Does the Search API need an immediate refresh to see the new data?
10. Is the current mapping compatible with the new values?

Choose the API:

- Full snapshot → `save()` / Index API.
- Field patch → Update API with `doc`.
- Logic depending on current source → script update.
- Create if missing → `upsert` or `doc_as_upsert`.
- Multiple IDs → bulk update.
- Multiple documents matching a condition → Update By Query.

## 21. Quick Reference Table

| Need | Approach |
|---|---|
| Create or replace an entire document | `save()` / Index API |
| Write multiple complete documents | `saveAll()` / bulk index |
| Update a few fields | `UpdateQuery` with `Document` |
| Update via calculation on current source | Painless script update |
| Remove a field | `ctx._source.remove('field')` |
| Add/remove array elements | Script update |
| Update or create | `upsert` / `doc_as_upsert` |
| Run script even when document is missing | `scripted_upsert` |
| Update multiple IDs | Bulk update |
| Update documents selected by query | Update By Query |
| Detect concurrent writes | `if_seq_no`, `if_primary_term`, version control |
| Retry on conflict | `retry_on_conflict` if the operation is safe to re-run |
| Avoid writes when values do not change | `detect_noop` |
| Read updated results via Search API | Appropriate refresh policy |

Full-document indexing and partial updates have different semantics even when using the same ID. `save()`/Index API replaces the source with the new representation, so use it only when the input object represents the complete state. The Update API with `doc` preserves omitted fields; scripts are suitable for calculations on the current source, array operations, or field deletion. Define the meaning of missing and `null` fields clearly, choose upsert when creation is needed, and design optimistic concurrency for data with multiple write streams. In Spring Data Elasticsearch, use `ElasticsearchOperations`/`UpdateQuery` or the version-appropriate client API, and test the resulting data after operations to verify that fields outside the patch scope remain intact.
