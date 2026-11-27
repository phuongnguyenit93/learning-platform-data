# Why save Is Not Equivalent to a Partial Update

In Spring Data Elasticsearch, `repository.save(entity)` writes a document by ID. When the document already exists, this operation uses Elasticsearch's index semantics: the document content is re-written according to the entity's representation. It does not mean Spring Data sends only the Java properties you just modified.

This differs from a **partial update** via the Elasticsearch Update API. With a partial update, the application sends a partial document containing only the fields to change; fields omitted from the update payload are preserved. The Update API also supports scripts to compute new values based on the current document content.

If an application loads a full entity, modifies one property, and calls `save`, the outcome usually matches expectations because the other fields are still present on the entity. However, if the application constructs a new entity containing only an ID and a few fields and then calls `save`, fields absent from the serialized representation can vanish from the document's `_source`. This is a common cause of unintended data loss.

## 1. Two Operations Serve Different Purposes

Suppose the current product document in the `products` index is:

```json
{
  "sku": "SKU-1001",
  "name": "Mechanical Keyboard",
  "price": 185000,
  "stock": 25,
  "description": "Mechanical keyboard with brown switches",
  "active": true
}
```

The application only wants to change `stock` to `20`.

**Writing the full document with `save`:** the entity is serialized into a new document. If the submitted entity only contains `id`, `stock`, and a few fields, other fields missing from the new document will no longer exist in `_source` after the write.

**Partial update:** sends a partial document containing only `stock`. Elasticsearch applies that change to the existing document and keeps the other fields.

| Operation | Meaning | Omitted fields |
|---|---|---|
| `save(entity)` | Indexes document content from entity and ID | Can be dropped from the new document |
| Update API with `doc` | Merges the sent partial document into the current document | Preserved as-is |
| Update API with `script` | Runs modification logic against current `_source` | Preserved unless modified/removed by script |

This is a semantic difference, not merely a difference in Java syntax.

## 2. `save` Writes a Document by ID

A Spring Data Elasticsearch repository is typically declared as:

```java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
```

Entity:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Double)
    private Double price;

    @Field(type = FieldType.Integer)
    private Integer stock;

    @Field(type = FieldType.Text)
    private String description;

    @Field(type = FieldType.Boolean)
    private Boolean active;

    protected Product() {
    }

    // Constructors and accessors omitted for brevity.
}
```

When calling:

```java
productRepository.save(product);
```

Spring Data converts the entity into a document using mapping metadata and sends the write operation to the index configured by `@Document`. For an existing ID, the index operation writes the new document content under that same ID. Properties unrepresented in the new document are not automatically copied over from the old document.

At the REST layer, the semantics closely match the Index API:

```http
PUT /products/_doc/product-1001
{
  "sku": "SKU-1001",
  "name": "Mechanical Keyboard",
  "price": 185000,
  "stock": 20,
  "description": "Mechanical keyboard with brown switches",
  "active": true
}
```

The request sends the complete desired document content. If a subsequent write sends only `stock` and `name`, the remaining fields absent from the new document can disappear from `_source`.

### 2.1 Example of Losing Fields When Saving a Partial Entity

Suppose code creates an object with only ID and stock:

```java
Product patch = new Product();
patch.setId("product-1001");
patch.setStock(20);

productRepository.save(patch);
```

If the entity serializes to:

```json
{
  "stock": 20
}
```

then the document after the write may contain only that content (aside from `_id` metadata). Fields like `sku`, `name`, `price`, `description`, and `active` are not automatically retained.

This is why `save` must not be used to submit partial update DTOs. `save` takes an entity representing the full document to write; it cannot guess which fields the caller meant to keep, which were omitted, and which should be deleted.

### 2.2 When Is `save` the Right Choice?

Use `save` when the application holds the complete document state to persist and intends to write that entire document:

- Creating a new document.
- Replacing document content with a complete entity.
- Re-syncing the entire document from an authoritative data source.
- Re-saving a document after reading the full entity, modifying it, and enforcing suitable concurrency control.

If an object is a projection, a PATCH request DTO, or an object holding only changed fields, do not treat it as a full representation for `save`.

## 3. Partial Update via the Elasticsearch Update API

Elasticsearch provides the `_update` endpoint to modify an existing document. The request can contain `doc` with just the portion of the document to change:

```http
POST /products/_update/product-1001
{
  "doc": {
    "stock": 20
  }
}
```

Elasticsearch fetches the current document, applies the `doc` section, and re-indexes the updated document. Fields not mentioned in `doc` remain untouched.

After the request, the document becomes:

```json
{
  "sku": "SKU-1001",
  "name": "Mechanical Keyboard",
  "price": 185000,
  "stock": 20,
  "description": "Mechanical keyboard with brown switches",
  "active": true
}
```

Only `stock` changed. The remaining fields are preserved.

### 3.1 Updating Multiple Fields at Once

```http
POST /products/_update/product-1001
{
  "doc": {
    "stock": 20,
    "active": false
  }
}
```

The request updates `stock` and `active` while leaving all unmentioned fields intact.

### 3.2 Omitted Fields vs. Null Fields

In a partial document, distinguish carefully:

- A field **omitted** from `doc`: no change requested for that field.
- A field present with a value: updates that field.
- A field present with `null`: this is a value sent to the update; do not assume it automatically equals deleting the field from `_source`.

If you need to remove a field from `_source`, use an explicit removal script:

```http
POST /products/_update/product-1001
{
  "script": {
    "source": "ctx._source.remove('description')"
  }
}
```

This keeps "leave unchanged," "set to null," and "remove property" distinct in your API. If your application uses null in PATCH requests to mean "not provided," design dedicated DTO/patch semantics instead of blindly forwarding every null to an update.

### 3.3 Updating Nested Sub-Objects

Suppose a document contains an address object:

```json
{
  "address": {
    "city": "Ho Chi Minh City",
    "district": "District 1",
    "street": "Le Loi"
  }
}
```

A partial doc can update a sub-property:

```http
POST /customers/_update/customer-1001
{
  "doc": {
    "address": {
      "district": "District 3"
    }
  }
}
```

The Update API applies merge semantics to the submitted partial document. However, with complex objects or arrays, verify the exact payload sent and resulting `_source`; in particular, never assume an array will be merged element-by-element by a business key.

### 3.4 Arrays and Nested Objects

For an array field like `variants`, partial update does not automatically locate an element by `sku` and edit only that element. When sending a new value for an array field, expect it to replace the array field's value unless you use a script to modify specific elements.

Example replacing an entire array:

```http
POST /products/_update/product-1001
{
  "doc": {
    "tags": ["keyboard", "wireless"]
  }
}
```

If you need to change `stock` for one variant inside a nested array, use a script that loops over the array and updates the matching element:

```http
POST /products/_update/product-1001
{
  "script": {
    "source": "for (def variant : ctx._source.variants) { if (variant.sku == params.sku) { variant.stock = params.stock; } }",
    "params": {
      "sku": "SKU-RED-M",
      "stock": 12
    }
  }
}
```

The script modifies only the element with the matching SKU. In real applications, explicitly define behavior when no element matches, when duplicate SKUs exist, or when adding a new variant is needed. `nested` mapping preserves relationships between elements at query time; it does not turn document updates into per-element patches automatically.

## 4. Using Partial Update via Spring Data Elasticsearch

`ElasticsearchRepository` provides `save` for entity writes, so do not assume it has a `savePartial` method that automatically merges fields. When partial updates are needed, use `ElasticsearchOperations` with `UpdateQuery`.

Example updating stock:

```java
import java.util.Map;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.document.Document;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.UpdateQuery;
import org.springframework.stereotype.Service;

@Service
public class ProductUpdateService {

    private final ElasticsearchOperations operations;

    public ProductUpdateService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void updateStock(String productId, int newStock) {
        Document partialDocument = Document.from(
            Map.of("stock", newStock)
        );

        UpdateQuery updateQuery = UpdateQuery.builder(productId)
            .withDocument(partialDocument)
            .build();

        operations.update(updateQuery, IndexCoordinates.of("products"));
    }
}
```

Here, `Document` contains only the field to modify. `UpdateQuery` pairs the partial document with the target ID. `ElasticsearchOperations.update(...)` sends the update operation to the specified index.

Builder APIs may offer additional options such as routing, retry on conflict, upsert, or scripts. Check exact package names and overloads against your project's Spring Data Elasticsearch version, but the core rule stays the same: pass a partial document to the Update API instead of serializing a sparse entity through `save`.

### 4.1 Separating PATCH DTOs from Storage Entities

REST APIs frequently accept requests containing only fields the client wants to change. Example:

```java
public record UpdateStockRequest(Integer stock) {
}
```

The service converts the request into a partial document:

```java
public void updateStock(String productId, UpdateStockRequest request) {
    if (request.stock() == null || request.stock() < 0) {
        throw new IllegalArgumentException("stock must be non-negative");
    }

    Document partialDocument = Document.from(
        Map.of("stock", request.stock())
    );

    UpdateQuery query = UpdateQuery.builder(productId)
        .withDocument(partialDocument)
        .build();

    operations.update(query, IndexCoordinates.of("products"));
}
```

The PATCH DTO expresses what the client sent. The `Product` entity remains the full document model. Never construct a dummy entity holding only a few fields and pass it to `save`.

### 4.2 Upsert: Create If Absent

By default, the Update API requires the document to already exist. If no matching document exists, the update can return a not-found error. When you want to create the document if absent, Elasticsearch supports `doc_as_upsert` or `upsert`:

```http
POST /products/_update/product-1001
{
  "doc": {
    "stock": 20
  },
  "doc_as_upsert": true
}
```

If the document already exists, `stock` is updated and other fields are preserved. If it does not exist, `doc` is used to create a new document. In this example, the newly created document will have only `stock`; it will not magically obtain `sku`, `name`, or `price`.

Thus, `doc_as_upsert` is suitable only when the partial document is also valid as a standalone new document if the ID is missing. If new documents require many mandatory fields, supply a complete `upsert` document or check existence and create via a dedicated flow.

## 5. Updating with Scripts

Partial `doc` works well when new field values are already known. Scripts fit when updates depend on current values, calculations, or conditional logic.

### 5.1 Incrementing Stock

If you want to increase stock by a delta rather than writing an absolute value:

```http
POST /products/_update/product-1001
{
  "script": {
    "source": "ctx._source.stock += params.delta",
    "params": {
      "delta": 5
    }
  }
}
```

The script reads the current value in `_source` and adds `delta`. This is safer than reading the old stock into Java, adding 5, and saving back, because another request could modify stock between the read and write.

If `stock` might be null or missing, handle that case explicitly in the script:

```json
{
  "script": {
    "source": "if (ctx._source.stock == null) { ctx._source.stock = params.delta; } else { ctx._source.stock += params.delta; }",
    "params": {
      "delta": 5
    }
  }
}
```

### 5.2 Conditional Updates

For example, updating the price only if the current price is below a threshold:

```http
POST /products/_update/product-1001
{
  "script": {
    "source": "if (ctx._source.price < params.limit) { ctx._source.price = params.newPrice; } else { ctx.op = 'noop'; }",
    "params": {
      "limit": 200000,
      "newPrice": 199000
    }
  }
}
```

`ctx.op = 'noop'` tells Elasticsearch not to re-write the document if the condition is not met. Scripts must be tightly controlled; never concatenate user input directly into script source. Pass data via `params`.

### 5.3 Scripts and Performance

Script updates enable flexible logic but must execute on the shard holding the document. Over large numbers of documents, update-by-query or bulk updates can impose significant load. Limit scope, monitor execution time, handle version conflicts, and throttle appropriately. Do not use a script merely to assign a static value when a partial `doc` suffices.

## 6. Save, Partial Update, and Update-by-Query

Elasticsearch offers multiple ways to modify documents. Choose based on scope and data semantics:

| Approach | Scope | Best suited for |
|---|---|---|
| `repository.save(entity)` | One document, writes entity content | Creating or re-writing a complete document |
| `POST /index/_update/id` with `doc` | One document, partial update | Changing a few known fields |
| `_update` with script | One document, logic based on current state | Increment/decrement, conditions, editing an array item |
| `_update_by_query` | Multiple documents matching a query | Bulk updating by criteria |
| Bulk API | Many write/update/delete operations | High-volume batch ingestion or updates |

`_update_by_query` is not a universal replacement for `save`. It reads matching documents and applies a script or partial update to each document. You must manage version conflicts, document counts, and cluster load.

## 7. Partial Updates and Concurrency Issues

Partial updates avoid overwriting unrelated fields, yet they do not automatically solve every concurrency problem.

### 7.1 Lost Updates in Read-Modify-Save

Suppose two requests concurrently read a document with `stock = 10`:

1. Request A reads `10` and wants to subtract 2.
2. Request B reads `10` and wants to subtract 3.
3. A computes `8` and calls save.
4. B computes `7` and calls save.

The final result can end up as `7`, even though both reductions combined should yield `5`. This is a lost update caused by both requests computing from the same stale value.

When business logic performs relative increments/decrements, server-side script updates can apply arithmetic to the current state. Even then, define idempotency and retry semantics carefully because requests may be re-sent after timeouts.

### 7.2 Optimistic Concurrency Control

Elasticsearch supports optimistic concurrency control using `_seq_no` and `_primary_term`. A client can require an update to succeed only if the document is still at the version it read. If the document changed, Elasticsearch returns a version conflict so the application can re-read and retry or report the conflict.

Spring Data Elasticsearch also supports a version property via `@Version` in compatible APIs. When using it, understand your Spring Data version's contract and how version metadata is propagated during writes/updates.

Optimistic locking fits when you must guarantee you never blindly overwrite someone else's change. It does not replace atomic update designs for increments/decrements or server-side calculations against current state.

### 7.3 Retry on Conflict

The Update API supports `retry_on_conflict` to retry when a version conflict occurs during the update. This lets certain updates re-run against the newer document version.

Never enable infinite retries. Scripts must be safe to re-execute, and retry limits must match expected contention. A script adding 1 has different semantics from setting stock to an absolute value; understand which operations are safe to repeat.

## 8. Read-After-Write and Refresh

Elasticsearch is near real-time for search. `save` or update can return successfully before the change appears in `_search` results, because search requires a refresh. Reading a document by ID via GET has real-time semantics by default, unlike search queries.

If business logic needs search to reflect an update immediately, use an appropriate refresh policy or refresh the index after a batch of operations. Avoid forcing a refresh on every write request unless truly necessary, as frequent refreshes degrade indexing efficiency.

In Spring Data Elasticsearch, you can configure refresh policies on operations/entities as supported by your version, or use an update API that accepts a refresh option. Distinguish search-visibility requirements from durability requirements; refresh is neither a commit nor a transaction.

## 9. Designing PATCH APIs at the Application Layer

HTTP `PUT` typically represents replacing a resource's representation, whereas `PATCH` represents a partial modification. Exact mappings depend on your API contract, though this distinction aligns closely with `save` vs. the Update API.

Example DTO:

```java
public record UpdateProductRequest(
    String name,
    Double price,
    Integer stock
) {
}
```

If every null property means "not sent," you can construct a partial document containing only non-null values. However, that prevents clients from intentionally clearing a field with null. If your API needs three states—"omitted," "set to null," and "remove"—use a dedicated patch representation or follow JSON Merge Patch/JSON Patch with an explicit contract.

Simple example updating only sent fields without supporting field removal:

```java
Map<String, Object> changes = new HashMap<>();

if (request.name() != null) {
    changes.put("name", request.name());
}
if (request.price() != null) {
    changes.put("price", request.price());
}
if (request.stock() != null) {
    changes.put("stock", request.stock());
}

if (!changes.isEmpty()) {
    UpdateQuery query = UpdateQuery.builder(productId)
        .withDocument(Document.from(changes))
        .build();
    operations.update(query, IndexCoordinates.of("products"));
}
```

This snippet demonstrates building a partial document. Production applications must validate each field, restrict which fields are editable, and handle no-op requests cleanly. Never accept an arbitrary map from a client and forward it directly to `_update`, as clients could alter system fields or restricted properties.

## 10. When Should You Read an Entity and Save It Back?

Reading the full entity, modifying a property, and calling save can be appropriate when:

- The entity genuinely represents the entire document to preserve.
- No projection or mapping drops fields that must be kept.
- The application accepts re-writing the entire document.
- Concurrency control is in place if concurrent requests may update the document simultaneously.

Example:

```java
Product product = productRepository.findById(id)
    .orElseThrow(() -> new ProductNotFoundException(id));

product.setStock(20);
productRepository.save(product);
```

This is completely different from instantiating a new `Product` with only ID and stock. Because the entity was loaded in full, all other properties remain present during serialization, assuming mappings/converters read them properly.

However, read-modify-save still leaves a gap between read and write. Another request can update the document during that window. To avoid overwriting concurrent updates, use optimistic concurrency control or design an appropriate atomic update.

## 11. Common Mistakes

### 11.1 Using save with a PATCH DTO

PATCH DTOs usually contain only the fields a client wants to change. Mapping that DTO into a sparse entity and calling `save` can wipe out omitted fields. Build a partial `Document` and use the Update API.

### 11.2 Assuming Null Fields Mean Unchanged

During entity serialization, null fields may be skipped or written depending on mappings, converters, and configuration. Either way, `save` does not infer a client's PATCH intent. Define field states explicitly and build intentional partial updates.

### 11.3 Assuming Omitting a Field from Update JSON Deletes It

With partial `doc`, omitted fields are preserved. To delete a field, use a script like `ctx._source.remove(...)` or an equivalent mechanism.

### 11.4 Updating One Array Element with Partial JSON

Sending a new array for an array field replaces that entire field's value. When updating a single element by key, use a script or model sub-items as separate documents.

### 11.5 Using Scripts for Every Update

Scripts are powerful for dynamic logic, but add complexity and overhead. If you only need to set a few fields to known values, partial `doc` is simpler.

### 11.6 Ignoring Version Conflicts

Under concurrent updates, requests can hit conflicts or overwrite each other in completion order. Define clear business semantics and use optimistic locking, script updates, or bounded retries appropriately.

### 11.7 Confusing Timeout Errors with Unapplied Updates

A client can time out after Elasticsearch already applied the update if the response is lost. Retrying an increment/decrement operation can apply it a second time. Design idempotency keys, version checks, or safe update logic accordingly.

## 12. How to Investigate When Other Fields Disappear After save

If a field vanishes after calling `save`, check:

1. `_source` before the write to confirm the field existed.
2. Whether the actual entity passed to `save` contained that field.
3. Whether mapping converters or custom conversions ignored or renamed the field.
4. Whether the entity was a projection/DTO holding only a subset of data.
5. Whether multiple requests wrote to the same ID and which one finished last.
6. Whether an alias pointed to multiple indices or writes hit the wrong index.

Inspect the document directly:

```http
GET /products/_doc/product-1001
```

Test update behavior with `_update` on a sample document and compare `_source` before and after. If you need to inspect emitted requests, enable HTTP client logging in development using synthetic data; avoid logging sensitive payloads in production.

## 13. Selection Principles

- Use `save` when the entity represents the complete document to write.
- Use the Update API with `doc` when only a few known fields need changing.
- Use scripts when calculations or modifications depend on current `_source` state.
- Use `doc_as_upsert` or `upsert` only when the payload for creating a missing document is also valid.
- Do not treat null, omitted fields, and field removal as identical.
- For arrays/nested structures, never assume JSON updates merge element-by-element; use scripts or model separately when needed.
- Design concurrency and retries to prevent lost updates or duplicate applications.
- Distinguish write acknowledgement from search visibility after refresh.
- Keep PATCH DTOs separate, validate editable fields, and convert them into explicit partial updates.

## 14. Summary

`save(entity)` in Spring Data Elasticsearch writes a document by ID using the content produced from the entity. When the document already exists, it does not automatically fetch the old document and merge missing fields from the entity; consequently, an incomplete entity can lose fields omitted from the newly serialized document.

Partial updates via the Elasticsearch Update API send either a `doc` containing only the fields to modify or a script operating on the current `_source`. Omitted fields remain intact; null fields, removed fields, and unmentioned fields each require clear semantics. For arrays and nested objects, explicitly update elements via scripts or intentionally replace the array field.

In Spring Data Elasticsearch, use `ElasticsearchOperations.update(UpdateQuery, IndexCoordinates)` when partial updates are needed. Reserve `save` for complete documents, implement appropriate concurrency and retry controls, and inspect the actual `_source` when investigating data loss. Understanding this distinction prevents unintended overwrites, missing fields, and data drift in update APIs.
