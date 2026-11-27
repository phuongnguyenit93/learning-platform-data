# Upsert, doc_as_upsert, and Missing Document Conditions

When updating data in Elasticsearch, applications often need to handle two cases: if the document already exists, modify certain fields; if the document does not yet exist, create a new one. **Upsert** combines these two behaviors into a single update operation. Elasticsearch provides the **upsert** and **doc_as_upsert** properties in the Update API to accomplish this.

However, upsert does not mean "create only if it does not exist". If the document is already present, the Update API still applies the update portion. When business rules require creating a new document and failing if the ID already exists, you must use the **Create API** or **op_type=create**. Clearly distinguishing these two meanings helps prevent data overwrites, handle conflicts properly, and reduce errors caused by concurrent requests.

This lesson uses the **products** index with SKU, name, price, stock quantity, and status fields. The content focuses on the Update API, upsert, `doc_as_upsert`, scripted upsert, conditional create operations, conflict handling, and calling them from Spring Data Elasticsearch.

## 1. The Update API and Partial Document Updates

Elasticsearch stores each document as a JSON source. When only a few fields need to change, the Update API lets you send a **partial document** instead of resending the entire source.

Example current document:

~~~json
{
  "sku": "KB-1001",
  "name": "Mechanical Keyboard",
  "price": 89.5,
  "stock": 20,
  "status": "ACTIVE"
}
~~~

The application only wants to change the price:

~~~http
POST /products/_update/p-1001
{
  "doc": {
    "price": 94.5
  }
}
~~~

Elasticsearch updates the `price` field and preserves the other fields. This is a partial update. If the document does not yet exist, the request above does not automatically create it by default; Elasticsearch returns a document-not-found error.

The Update API performs the read, applies changes, and reindexes the source on the Elasticsearch side. The application does not need to `GET` the document, modify the object, and send the whole thing back just to change one field.

### Partial Document Is Not Full-Source Replacement

With the request:

~~~json
{
  "doc": {
    "price": 94.5
  }
}
~~~

the fields `sku`, `name`, `stock`, and `status` remain preserved. If you send a nested object, Elasticsearch applies object merge rules; with arrays, you should not assume elements will be appended. An array value sent in a partial document typically replaces the current array value.

Example document having:

~~~json
{
  "address": {
    "city": "Ho Chi Minh City",
    "district": "District 1"
  },
  "tags": [
    "keyboard",
    "wireless"
  ]
}
~~~

Sending a partial doc:

~~~json
{
  "doc": {
    "address": {
      "district": "District 3"
    },
    "tags": [
      "mechanical"
    ]
  }
}
~~~

The `address` object is merged by sub-fields, while `tags` is replaced by the new array. If you want to add an element to an array or increment `stock` based on its current value, consider a script update.

## 2. What Is Upsert?

**Upsert** combines update and insert:

- If the document already exists: apply the changes.
- If the document does not yet exist: create the document from the provided upsert data.

The Update API accepts both a partial document and an initialization document:

~~~http
POST /products/_update/p-1001
{
  "doc": {
    "price": 94.5
  },
  "upsert": {
    "sku": "KB-1001",
    "name": "Mechanical Keyboard",
    "price": 89.5,
    "stock": 20,
    "status": "ACTIVE"
  }
}
~~~

If ID `p-1001` already exists, Elasticsearch applies the `doc` part and updates `price` to `94.5`. If the ID does not yet exist, Elasticsearch indexes a document from the `upsert` object.

The key point is that **upsert is not create-only**. It is designed for create-or-update behavior. If two requests use the same ID, the operation is processed on the shard holding the document; the application does not need to perform a `GET` followed by a client-side insert-or-update decision.

### Why Is Upsert Useful?

A GET-then-write flow typically looks like:

~~~text
Application               Elasticsearch
   |                            |
   |---- GET document --------->|
   |<--- does not exist --------|
   |                            |
   |---- INDEX document ------->|
   |<--- created ---------------|
~~~

Between `GET` and `INDEX`, another request could create the same ID. Both applications observe that the document does not exist yet and both write it. This is a race condition.

Upsert moves the existence check and the create/update operation into a single Update API request. Elasticsearch processes this on the shard containing the document, avoiding the gap caused by the application checking and then writing.

## 3. Distinguishing `doc` and `upsert`

The two properties serve separate roles:

| Property | When document exists | When document does not exist |
|---|---|---|
| **doc** | Partial document merged into current source | Does not create a document automatically without upsert |
| **upsert** | Not used as regular update content | Used as initial source to create the document |
| **doc_as_upsert** | `doc` is still used to update | `doc` content is used as the newly created document |

Example:

~~~json
{
  "doc": {
    "price": 94.5
  },
  "upsert": {
    "sku": "KB-1001",
    "name": "Mechanical Keyboard",
    "price": 89.5,
    "stock": 20
  }
}
~~~

When it exists, the price is updated to `94.5`. When it does not yet exist, the document is created from `upsert` with an initial price of `89.5`.

This allows two different structures:

- A small partial update for an existing document.
- A fuller source for the case where creation is required.

Ensure the `upsert` object has all required fields according to the mapping and business rules. If `upsert` lacks an important field, the new document may be created yet fail to satisfy the application's data contract.

## 4. What Is `doc_as_upsert`?

**`doc_as_upsert: true`** instructs Elasticsearch to use the content in `doc` itself as the upsert document if the ID does not yet exist.

Example:

~~~http
POST /products/_update/p-1001
{
  "doc": {
    "sku": "KB-1001",
    "name": "Mechanical Keyboard",
    "price": 94.5,
    "stock": 20,
    "status": "ACTIVE"
  },
  "doc_as_upsert": true
}
~~~

Result:

- If `p-1001` already exists, the fields in `doc` are applied to the current source.
- If `p-1001` does not yet exist, the entire `doc` object is used to create the new document.

`doc_as_upsert` is suitable when the content used for updating is also sufficient to initialize the document. It avoids duplicating the same JSON in both `doc` and `upsert`.

### `doc_as_upsert` Does Not Mean Create Only When Missing

This is an essential point to remember. A request with `doc_as_upsert` still updates an existing document. If the document exists, Elasticsearch does not return a duplicate error just because the ID is already present.

Example request:

~~~json
{
  "doc": {
    "status": "ACTIVE"
  },
  "doc_as_upsert": true
}
~~~

If the document already exists, `status` is updated. If it does not exist, Elasticsearch creates a source with only `status`. If `Product` requires `sku` and `name`, the new document may be incomplete from a business standpoint even though the request technically succeeded.

Therefore, only use `doc_as_upsert` when `doc` is genuinely sufficient to create a valid document. If you need an initial source different from the update payload, use a separate `upsert`.

### Choosing `doc_as_upsert` vs. Explicit `upsert`

| Need | Choice |
|---|---|
| Update content also suffices as a new source | `doc_as_upsert: true` |
| New source needs more fields than partial update | `doc` combined with `upsert` |
| Need initialization logic when document does not yet exist | `scripted_upsert` |
| Must only create new; existing document must cause conflict | Create API or `op_type=create` |

There is no need to specify both `upsert` and `doc_as_upsert` in the same request. Pick one approach that expresses your intent clearly to avoid confusing configurations.

## 5. Upsert and Missing Document Conditions Are Two Different Requirements

In business requirements, the phrase "if the document does not exist, create it" can carry two meanings:

1. **Create-or-update:** if missing, create; if present, update.
2. **Create-only:** if missing, create; if present, reject and report a conflict.

Upsert satisfies the first requirement. The Create API satisfies the second.

| ID State | Update API with upsert | Create API |
|---|---|---|
| ID does not exist | Creates document | Creates document |
| ID already exists | Updates document | Rejects, typically returns HTTP 409 |
| Goal | Sync or write state with create-or-update semantics | Guarantee not overwriting an existing document |

If the requirement is "create an order with this ID only once; if it already exists, report a duplicate order", use a create-only operation. Do not use `doc_as_upsert` because the request could update the existing source.

If the requirement is "receive the latest product record from the sync source; create if missing, update certain fields if present", upsert is more appropriate.

## 6. Create API: Creating New and Failing If ID Already Exists

Elasticsearch provides the **_create** endpoint to create a document only when the ID does not yet exist.

Example:

~~~http
PUT /products/_create/p-1001
{
  "sku": "KB-1001",
  "name": "Mechanical Keyboard",
  "price": 89.5,
  "stock": 20,
  "status": "ACTIVE"
}
~~~

If `p-1001` does not yet exist, the document is created. If the ID already exists, Elasticsearch returns a conflict error, typically HTTP 409 with error type `resource_already_exists_exception`.

An equivalent approach is using the Index API with **op_type=create**:

~~~http
PUT /products/_doc/p-1001?op_type=create
{
  "sku": "KB-1001",
  "name": "Mechanical Keyboard",
  "price": 89.5,
  "stock": 20,
  "status": "ACTIVE"
}
~~~

Differences from a regular index operation:

- The default Index API can create a new document or replace the source of an existing ID.
- `op_type=create` requires the ID not to exist yet.
- `_create` directly expresses create-only intent.

This is a safe way to protect documents from being overwritten by duplicate requests or multiple clients creating the same ID simultaneously.

## 7. Why Not Use GET and Then CREATE?

An easy-to-imagine implementation:

~~~text
GET /products/_doc/p-1001
If it does not exist:
    PUT /products/_doc/p-1001
If it exists:
    Report duplicate
~~~

This approach has a race condition:

1. Request A checks and sees the ID does not exist.
2. Request B also checks and sees the ID does not exist.
3. Request A writes the document.
4. Request B writes the same ID and may replace A's document if using the standard Index API.

Using `_create` resolves this condition on the Elasticsearch side:

~~~text
Request A ---- _create/p-1001 ----> succeeds
Request B ---- _create/p-1001 ----> 409 conflict
~~~

Only one request can create the document with that ID. The other request receives a conflict and can translate it into a business response such as "code already exists".

Do not turn every HTTP 409 into a success. Determine whether this is an expected duplicate or a version conflict during an update. The two cases have different meanings.

## 8. Bulk API: Distinguishing index, create, and update

When writing multiple documents, the Bulk API provides distinct actions:

| Action | Meaning |
|---|---|
| **index** | Creates a new document or replaces the source of an ID |
| **create** | Creates only if the ID does not yet exist |
| **update** | Partially updates or performs an upsert |
| **delete** | Deletes a document |

Example bulk create:

~~~http
POST /_bulk
{ "create": { "_index": "products", "_id": "p-1001" } }
{ "sku": "KB-1001", "name": "Mechanical Keyboard", "price": 89.5 }
{ "create": { "_index": "products", "_id": "p-1002" } }
{ "sku": "MS-1002", "name": "Wireless Mouse", "price": 25.0 }
~~~

If an ID already exists, the corresponding `create` action can fail with 409; other actions in the bulk request can still succeed. Bulk responses must be checked item by item, not solely by overall HTTP status.

Example bulk update with upsert:

~~~http
POST /_bulk
{ "update": { "_index": "products", "_id": "p-1001" } }
{ "doc": { "stock": 15 }, "upsert": { "sku": "KB-1001", "name": "Mechanical Keyboard", "stock": 15 } }
~~~

Example bulk update using `doc_as_upsert`:

~~~http
POST /_bulk
{ "update": { "_index": "products", "_id": "p-1002" } }
{ "doc": { "sku": "MS-1002", "name": "Wireless Mouse", "price": 25.0, "stock": 30 }, "doc_as_upsert": true }
~~~

Each `update` action can use `doc`, `upsert`, `doc_as_upsert`, or `script` as needed. Remember that the Bulk API uses NDJSON format: each metadata/action line and the following source or update body line must be separate; the request typically ends with a trailing newline.

## 9. Scripted Upsert

When the update depends on the current value or requires custom initialization logic, you can use **scripted_upsert**.

For example, incrementing stock quantity by a delta: if the document does not yet exist, initialize `stock` to 0 and then apply the delta:

~~~http
POST /products/_update/p-1001
{
  "scripted_upsert": true,
  "script": {
    "lang": "painless",
    "source": """
      if (ctx._source.containsKey('stock')) {
        ctx._source.stock += params.delta;
      } else {
        ctx._source.stock = params.delta;
      }
    """,
    "params": {
      "delta": 5
    }
  },
  "upsert": {
    "sku": "KB-1001",
    "name": "Mechanical Keyboard",
    "stock": 0,
    "status": "ACTIVE"
  }
}
~~~

With `scripted_upsert` set to `true`, the script runs whether the document already exists or not. When absent, the `upsert` object provides the initial source for the script. The script then modifies the source according to the written logic.

In the example, if the document does not yet exist, `upsert` initializes `stock` to 0, and the script increments it to 5. If the document already has `stock` equal to 20, the script increments it to 25.

If `scripted_upsert` is omitted or set to `false`, when the document does not exist, Elasticsearch uses the `upsert` object to create it without running the script. When the document already exists, the script runs as normal.

### When Is `scripted_upsert` Needed?

Use it when initialization values and update logic need to execute together, for example:

- Incrementing a counter if the document exists, creating the initial counter if absent.
- Updating total view counts.
- Conditionally adding or removing elements in a script.
- Creating an aggregated statistics document and updating fields based on current data.
- Modifying the source only if a business condition is satisfied.

Scripts can be more complex than partial docs and require careful control. Only use a script when the operation cannot be expressed clearly with simple `doc`/`upsert`.

### `doc_as_upsert` and `scripted_upsert`

These two options solve different needs. `doc_as_upsert` uses `doc` as the creation source; `scripted_upsert` runs the script even when the document does not yet exist. Elasticsearch does not allow using `doc_as_upsert` together with `scripted_upsert` in the same request. With scripted upsert, provide an `upsert` source and `script` following the Update API structure.

## 10. Scripts Can Skip Updates or Delete Documents

Painless scripts can control the operation through **ctx.op**.

Example updating `stock` only when `delta` is non-zero:

~~~json
{
  "script": {
    "lang": "painless",
    "source": """
      if (params.delta == 0) {
        ctx.op = 'noop';
      } else {
        ctx._source.stock += params.delta;
      }
    """,
    "params": {
      "delta": 0
    }
  }
}
~~~

Common operations:

- **index**: writes the source after the script completes.
- **noop**: leaves the document unchanged.
- **delete**: deletes the document.

When combining scripts with upsert, clearly define the initial source and `ctx.op` state. A script can set `noop` if no change is needed; the application should inspect the update result to know whether an actual update occurred.

Do not pass arbitrary user-supplied script strings into requests. Use controlled script sources and pass variable values through `params` to prevent syntax errors and limit risk.

## 11. `detect_noop` and Updates That Do Not Change Data

When using a partial document, Elasticsearch can check whether the sent values actually change the source. The **detect_noop** option is typically enabled by default for the Update API.

Example current source:

~~~json
{
  "status": "ACTIVE",
  "stock": 20
}
~~~

Request:

~~~json
{
  "doc": {
    "status": "ACTIVE"
  }
}
~~~

If the content does not change the document, Elasticsearch may return a **noop** result instead of indexing a new version of the source.

You can configure it explicitly:

~~~http
POST /products/_update/p-1001
{
  "detect_noop": true,
  "doc": {
    "status": "ACTIVE"
  }
}
~~~

`detect_noop` is helpful when applications frequently send repetitive state syncs. However, do not treat `noop` as an error. It means the current data is already equivalent to the update content according to Elasticsearch's check.

With scripts, noop detection depends on the script's logic; a script can explicitly set `ctx.op = 'noop'`.

## 12. Conditional Updates by Sequence Number and Primary Term

When multiple applications edit the same document, **optimistic concurrency control** may be needed to allow updates only if the document is still at the version the client read.

Elasticsearch provides:

- **_seq_no**: the operation's sequence number on the shard.
- **_primary_term**: the shard's primary term at that time.

GET or search responses can return this metadata. The application uses it when updating:

~~~http
POST /products/_update/p-1001?if_seq_no=12&if_primary_term=3
{
  "doc": {
    "price": 94.5
  }
}
~~~

If the document is still at sequence number `12` and primary term `3`, the update can proceed. If another request has modified the document, the condition no longer holds and Elasticsearch returns a version conflict, typically HTTP 409.

This is an "update if the version has not changed" condition, not a "create only if document does not exist" condition.

| Mechanism | Condition |
|---|---|
| **_create / op_type=create** | ID does not exist |
| **upsert** | Create if absent; update if present |
| **if_seq_no + if_primary_term** | Write only if current version matches the metadata read |
| **retry_on_conflict** | Retry update on version conflict per retry policy |

Do not use `if_seq_no`/`if_primary_term` as a substitute for the Create API. If the ID does not yet exist, a version-conditioned update request has no document to update and does not automatically turn into a create-only operation.

## 13. `retry_on_conflict` and Concurrent Updates

The Update API can encounter a version conflict when another request updates the document between Elasticsearch reading the source and writing the new source. **retry_on_conflict** lets Elasticsearch retry the update a number of times.

Example:

~~~http
POST /products/_update/p-1001?retry_on_conflict=3
{
  "script": {
    "source": "ctx._source.stock += params.delta",
    "params": {
      "delta": 1
    }
  }
}
~~~

If a conflict occurs, Elasticsearch can re-read the latest source and re-run the update script up to the configured number of retries.

This is useful for incrementing counters or changes based on the current source. However:

- Retrying does not guarantee the request will always succeed.
- The script may be executed multiple times during retries.
- The script should be safe when re-executed on a newer source.
- Side effects outside Elasticsearch should not be placed in scripts.
- To protect the specific version a client read, use `if_seq_no`/`if_primary_term` instead of automatically retrying an update based on stale data.

For partial docs writing a fixed value, retrying can be reasonable. For business logic requiring conflict detection for user resolution, return a conflict and ask the client to re-read rather than silently overwriting.

## 14. Upsert Does Not Replace a Stable Identifier

Upsert requires a document ID to identify the document to update or create. If the application lets Elasticsearch auto-generate an ID on every send, the same business record can become multiple distinct documents.

For example, a product has a unique SKU. The application can use a stable ID derived from the SKU or a stored internal ID:

~~~text
sku = KB-1001
document _id = product-KB-1001
~~~

Every sync for the same product must use the same ID. Only then does upsert update the right document.

Do not treat a SKU field as if Elasticsearch automatically enforces uniqueness on it. Elasticsearch only enforces uniqueness for `_id` within an index; it does not create a unique constraint on a regular field. If using SKU as the business key, normalize it and derive a stable `_id` from the SKU, or maintain an appropriate uniqueness mechanism.

Also note aliases and rollover indices. The same `_id` can exist across multiple backing indices if writing through an alias pointing to multiple indices; `_id` uniqueness does not automatically extend into a unique constraint across all backing indices.

## 15. Update API and `save()` in Spring Data Elasticsearch

Spring Data Elasticsearch offers multiple ways to write documents, but they do not share the same semantics.

| API | Typical meaning |
|---|---|
| **repository.save(entity)** | Writes the document by ID, typically using the Index API; the source sent is the entity |
| **ElasticsearchOperations.save(entity)** | Writes the entity following document-saving semantics |
| **ElasticsearchOperations.update(UpdateQuery, index)** | Executes the Update API; can use partial doc, upsert, or script |
| **ElasticsearchClient.create(...)** | Create-only, conflicts if ID already exists |
| **ElasticsearchClient.update(...)** | Update API with doc/upsert/script |

Calling `save` with an entity whose ID already exists typically writes the entity's source over that document. This is not equivalent to partially updating a few fields. If the entity holds only partial data, `save` may replace the source with an object missing fields.

Example entity containing only:

~~~json
{
  "id": "p-1001",
  "stock": 25
}
~~~

Calling `save` with this object may write a source missing `sku`, `name`, and `price`. If you only want to change `stock` while keeping the other fields, use the Update API with a partial doc.

Do not choose `save` merely because the method name sounds like upsert. Base your choice on actual semantics: `save`/index writes the entity's source; `update` with `upsert` applies create-or-update logic; the Create API enforces create-only.

## 16. Using `UpdateQuery` with `ElasticsearchOperations`

Spring Data Elasticsearch provides **UpdateQuery** to describe an Update API operation. You can use **Document** as the partial document and upsert source.

Example using explicit upsert:

~~~java
import org.springframework.data.elasticsearch.core.document.Document;
import org.springframework.data.elasticsearch.core.query.UpdateQuery;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

Document partial = Document.parse("""
{
  "price": 94.5
}
""");

Document initialDocument = Document.parse("""
{
  "sku": "KB-1001",
  "name": "Mechanical Keyboard",
  "price": 89.5,
  "stock": 20,
  "status": "ACTIVE"
}
""");

UpdateQuery updateQuery = UpdateQuery.builder("p-1001")
        .withDocument(partial)
        .withUpsert(initialDocument)
        .build();

operations.update(
        updateQuery,
        IndexCoordinates.of("products")
);
~~~

When the document exists, the partial document updates `price`. When it does not yet exist, `initialDocument` is used as the initial source.

### Using `doc_as_upsert` via `UpdateQuery`

If the partial document also suffices to create the document:

~~~java
Document document = Document.parse("""
{
  "sku": "KB-1001",
  "name": "Mechanical Keyboard",
  "price": 94.5,
  "stock": 20,
  "status": "ACTIVE"
}
""");

UpdateQuery updateQuery = UpdateQuery.builder("p-1001")
        .withDocument(document)
        .withDocAsUpsert(true)
        .build();

operations.update(
        updateQuery,
        IndexCoordinates.of("products")
);
~~~

Builder names such as `withDocument`, `withUpsert`, and `withDocAsUpsert` belong to Spring Data Elasticsearch's `UpdateQuery` API; detailed signatures can vary between versions. Check your project's actual dependency if you need additional options like `retry_on_conflict`, `seq_no`, or `primary_term`.

### Notes on `Document`

`Document` is Spring Data Elasticsearch's representation of JSON data. It can be created from JSON using `Document.parse` or built from a `Map` depending on the API version. Using `Document` makes the partial source and upsert source explicit without needing to construct a full entity.

If you need mapping/conversion control from entities, check how your Spring Data version converts objects to `Document`. Do not mix a raw JSON `Document` with an entity using a custom converter without verifying the resulting source.

## 17. Using the Elasticsearch Java API Client to Upsert

In Spring Boot applications using Spring Data Elasticsearch 5.x, you can inject the **ElasticsearchClient** created by Spring configuration to use the Update API directly.

Example:

~~~java
import co.elastic.clients.elasticsearch.ElasticsearchClient;

import java.util.Map;

Map<String, Object> partial = Map.of(
        "price", 94.5
);

Map<String, Object> initial = Map.of(
        "sku", "KB-1001",
        "name", "Mechanical Keyboard",
        "price", 89.5,
        "stock", 20,
        "status", "ACTIVE"
);

var response = elasticsearchClient.update(
        update -> update
                .index("products")
                .id("p-1001")
                .doc(partial)
                .upsert(initial),
        Map.class
);
~~~

Here:

- `index` specifies the target index.
- `id` is the stable ID of the document.
- `doc` is the partial document used when the ID already exists.
- `upsert` is the source used when the ID does not yet exist.
- `response` holds the Update API result.

Example using `doc_as_upsert`:

~~~java
var response = elasticsearchClient.update(
        update -> update
                .index("products")
                .id("p-1001")
                .doc(initial)
                .docAsUpsert(true),
        Map.class
);
~~~

The generic types of the partial document and returned document depend on how you use the Java API Client. The example uses `Map` to illustrate dynamic JSON; if you have an appropriate `Product` class, you can use that entity type. Builders and response types must match the Elasticsearch Java API Client version managed by Spring Boot.

Do not create a new `ElasticsearchClient` for every update. Use the shared configured bean to reuse transport, connection pool, TLS, credentials, and timeouts.

## 18. Create-Only via Elasticsearch Java API Client

To create a new document and fail if the ID already exists, use **create**:

~~~java
var response = elasticsearchClient.create(
        create -> create
                .index("products")
                .id("p-1001")
                .document(initial)
);
~~~

If `p-1001` does not yet exist, the document is created. If the ID already exists, Elasticsearch returns a conflict error. The application can catch the corresponding error and translate it into a business response.

Another way is using the Index API with `opType` CREATE:

~~~java
import co.elastic.clients.elasticsearch._types.OpType;

var response = elasticsearchClient.index(
        index -> index
                .index("products")
                .id("p-1001")
                .opType(OpType.Create)
                .document(initial)
);
~~~

Enum names and overloads may vary across client versions. Whether using the `create` endpoint or `opType` CREATE, the key point is that the server performs the existence check and write in a single operation.

### Handling Duplicates Explicitly

Example business flow:

~~~text
Call create-only
      |
      v
  Succeeded?
  |        |
 Yes       No
  |        |
Return   Inspect error type
 201       |
           +--> ID already exists: return conflict
           |
           +--> Mapping/auth/network: handle technical error
~~~

Do not catch every exception and return "already exists". Mapping, permission, or connection errors do not mean the ID is duplicated.

## 19. When to Use Version Conditions Instead of Upsert?

Upsert suits create-or-update synchronization, but some business cases need to protect data against concurrent updates.

Example:

1. User A reads price 100.
2. User B reads price 100.
3. User A changes price to 110.
4. User B submits price 105 based on stale data.

Without concurrency control, B's update could overwrite A's change. In that case, the application can use the `seq_no` and `primary_term` that were read to allow the update only if the version still matches.

This is optimistic concurrency control. When a conflict occurs, the application can:

- Return HTTP 409 so the client reloads and resolves it.
- Re-read the data and reapply the change according to business rules.
- Use an atomic script update if the business operation is an increment/decrement based on the current value.
- Use `retry_on_conflict` if the operation can be safely re-executed.

Do not use upsert to mask business conflicts. If you need to prevent users from overwriting a newer version, use version conditions.

## 20. Updating Stock: Choosing Partial Doc or Script?

Suppose the current `stock` is 20. Two different business operations may require two different update approaches.

### Setting Stock to a Specific Value

If the inventory system sends a new absolute value of 25:

~~~json
{
  "doc": {
    "stock": 25
  }
}
~~~

This is a partial document. It sets `stock` to 25.

### Increasing Stock by 5

If the request means "receive 5 additional units":

~~~json
{
  "script": {
    "source": "ctx._source.stock += params.quantity",
    "params": {
      "quantity": 5
    }
  }
}
~~~

This is an addition based on the current source. If two requests both add 5, a script update performs the change against the value present in Elasticsearch rather than both clients reading 20 and writing 25.

If the document does not yet exist and still needs initialization, you can combine the script with `upsert` and `scripted_upsert` as shown earlier.

Do not use a partial doc to simulate an increment if the client only knows the delta. If two clients read 20 and send `doc` `stock=25`, one increment will be lost. Choose the update style according to data semantics: absolute value or relative change.

## 21. Handling Update API Responses and Errors

The Update API can return a result indicating whether the document was created, updated, or unchanged.

Common statuses:

| Result | Meaning |
|---|---|
| **created** | Document was created via upsert |
| **updated** | Existing document was updated |
| **noop** | No change needed to be written |
| **404 document_missing_exception** | Update without upsert and ID does not exist |
| **409 version_conflict_engine_exception** | Version conflict occurred during update |
| **409 resource_already_exists_exception** | Create-only encountered an existing ID |
| **400 mapper_parsing_exception** | Data does not match mapping |
| **400 script_exception** | Script error during execution |
| **429 or overload error** | Cluster is under pressure or rejecting requests |

With the Update API and upsert, the `result` status can be `created` when the document did not exist and `updated` when it already existed. With `detect_noop`, the result can be `noop`.

Do not just check whether the request threw an exception. If the application needs to record audit logs or emit events, inspect the actual result to know whether the operation created, updated, or made no change.

### Refresh and Immediate Readability After Writing

Elasticsearch is near-real-time. A successful update operation does not guarantee the document immediately appears in every subsequent search request. If immediate readability after writing is needed, use an appropriate refresh policy, such as **wait_for**, depending on the API and configuration.

Do not force a refresh immediately after every update because it can degrade indexing performance. Use a refresh policy aligned with the application's consistency needs.

## 22. Bulk Updates in Spring Data Elasticsearch

For large numbers of documents, consider the Bulk API instead of sending a separate request per document. Bulk reduces round-trips and allows processing multiple actions in one submission.

Spring Data Elasticsearch has bulk abstractions and version-specific update support. If using the Java API Client, you can construct a `BulkRequest` with individual update or create operations.

NDJSON example with update/upsert:

~~~http
POST /_bulk
{ "update": { "_index": "products", "_id": "p-1001", "retry_on_conflict": 3 } }
{ "doc": { "stock": 25 }, "upsert": { "sku": "KB-1001", "name": "Mechanical Keyboard", "stock": 25 } }
{ "create": { "_index": "products", "_id": "p-1002" } }
{ "sku": "MS-1002", "name": "Wireless Mouse", "price": 25.0 }
~~~

In the bulk response:

- Check the `errors` field.
- Inspect each item in the `items` array.
- Classify create conflicts, version conflicts, mapping errors, and transient errors.
- Retry only appropriate errors.
- Do not blindly retry a create that already succeeded if there is no idempotency mechanism.

A bulk request can return HTTP 200 even if one or more items failed. Therefore, you must inspect each item result rather than relying solely on the overall HTTP status.

## 23. Idempotency and Duplicate Requests

A request can be resent due to a client timeout even if Elasticsearch already processed it successfully. If the operation is not designed to be idempotent, retrying can modify the data multiple times.

Examples:

- Setting `stock = 25`: resending normally keeps `stock` at 25.
- Incrementing `stock` by 5: resending a second time increments `stock` by another 5.
- Create-only with a fixed ID: succeeds the first time, receives 409 the next time.
- Upsert with a fixed `doc`: may reapply the same values, though other fields and scripts must be considered.

For increment/decrement operations, an idempotency key or a record of processed transaction IDs is needed to prevent the same event from being applied multiple times. You cannot rely solely on `retry_on_conflict` to guarantee a business operation runs once; `retry_on_conflict` handles internal version conflicts, not duplicate events from the client.

If using upsert to sync records from a source with a stable ID, define clearly which source has authority to overwrite which fields and how late-arriving records are handled.

## 24. Protecting Documents from Missing Fields

`doc_as_upsert` is convenient, but it can easily create incomplete documents if the partial doc is insufficient for initialization.

Example:

~~~json
{
  "doc": {
    "stock": 10
  },
  "doc_as_upsert": true
}
~~~

If the document does not yet exist, Elasticsearch creates a source with only `stock`. The document may lack `sku`, `name`, `price`, or a required status.

Ways to prevent this:

- Use an explicit `upsert` containing all required fields.
- Use `doc_as_upsert` only when `doc` is a complete, valid source.
- Validate input data before sending.
- Use appropriate mappings and consider `dynamic: strict` if the schema requires strict control.
- Perform business validation in the service layer.
- Monitor for documents missing fields using data-check queries.
- Do not treat mappings as a substitute for business validation; mappings primarily enforce types and index structure.

If required fields change per business rules, coordinate schemas and versioning across producers. An older producer might send `doc_as_upsert` missing newly added fields.

## 25. Choosing Operations by Business Goal

| Goal | Suitable approach | Behavior when ID already exists |
|---|---|---|
| Create or update by ID | Update API + `doc` + `upsert` | Updates |
| Use the same object for update and insert | `doc_as_upsert` | Updates |
| Run initialization and update logic via script | `scripted_upsert` | Runs script |
| Create uniquely, disallow overwriting | `_create` or `op_type=create` | Conflict |
| Replace entire source with new entity | Index API or `save` per entity-write semantics | Replaces source |
| Update only if document was not modified by someone else | `if_seq_no` + `if_primary_term` | Conflict if version changed |
| Increment/decrement based on current value | Script update | Applies calculation on current source |
| Write multiple documents | Bulk API | Inspect each item |

Before choosing an API, state the requirement in a concrete sentence:

- "If missing, create; if present, update the `stock` field."
- "Only create a new order; if the code already exists, return a conflict."
- "Update the price only if the document is still the version the user just read."
- "Increment the counter by one unit without overwriting the current value."

That descriptive sentence helps you pick the right choice among Update, Create, script, or optimistic concurrency.

## 26. Safe Upsert Implementation Workflow

A workflow can follow these steps:

1. **Choose a stable ID.** Every update to the same entity must use the same `_id`.
2. **Define semantics.** Do you need create-or-update or create-only?
3. **Choose the payload.** Distinguish partial doc from a full upsert source.
4. **Use `doc_as_upsert` appropriately.** Only when `doc` suffices to create a valid document.
5. **Use a script when logic depends on the current source.** Set `scripted_upsert` and an appropriate `upsert` source.
6. **Handle concurrency.** Choose `retry_on_conflict` or `if_seq_no`/`if_primary_term` per business needs.
7. **Inspect results.** Distinguish `created`, `updated`, `noop`, and conflicts.
8. **Design retries.** Determine whether the operation is idempotent or needs an idempotency key.
9. **Process bulk items.** Inspect every item result rather than only the HTTP status.
10. **Monitor data.** Verify newly created documents have complete fields and valid mappings.
11. **Choose a refresh policy.** Wait for refresh only when read-after-write requires it.
12. **Test race conditions.** Send concurrent requests with the same ID to verify only one create-only succeeds or that upsert behaves properly.

Upsert and `doc_as_upsert` help applications perform create-or-update in a single Update API operation. **upsert** provides a separate source for creating new documents; **doc_as_upsert** uses the partial document itself as the source when the ID does not yet exist; **scripted_upsert** runs the script even during creation. If the requirement is "create only when absent; reject if already present", use **_create** or **op_type=create**. When handling concurrency, distinguish `retry_on_conflict` from version conditions `if_seq_no`/`if_primary_term`; each mechanism resolves a different type of conflict.
