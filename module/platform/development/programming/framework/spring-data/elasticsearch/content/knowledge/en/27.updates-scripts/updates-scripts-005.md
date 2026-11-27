# Modifying Arrays, Counters, and Nested Objects

In Elasticsearch, updating a document can modify a few fields, increment a counter, add or remove elements in an array, or edit an object nested inside the document. These operations must be designed carefully because Elasticsearch stores documents as JSON and, when updating, the engine typically reads the current version, applies the change, and reindexes the new document.

Spring Data Elasticsearch provides abstractions such as **ElasticsearchOperations**, **UpdateQuery**, and **Document** to perform partial updates. When changes depend on the document's current data, **Painless scripts** can be used to operate directly inside Elasticsearch. For conditional updates across multiple documents, `update-by-query` or bulk updates can be used depending on the scope and how data is identified.

This lesson focuses on common scenarios: modifying scalar arrays, updating arrays of objects, changing nested objects, incrementing/decrementing counters, protecting concurrent updates, handling missing documents, and choosing among partial documents, scripts, bulk updates, or `update-by-query`.

## 1. How Elasticsearch Performs Updates

Elasticsearch provides the Update API for a single document by ID. Under the hood, the engine fetches the current document, applies the partial document or script to its content, and then indexes the new version. Therefore, updating a single field still creates a new version of the document in the index.

There are two main approaches:

**Partial document** sends the fields to modify. Elasticsearch merges the sent content with the current document according to Update API semantics.

**Scripted update** runs a script on the current document. The script can read old values, perform calculations, add or remove elements, and decide whether to update or skip.

Example product document:

~~~json
{
  "id": "P-100",
  "name": "Wireless Keyboard",
  "price": 79.5,
  "stock": 12,
  "viewCount": 450,
  "tags": ["wireless", "keyboard"],
  "attributes": {
    "color": "black",
    "layout": "US"
  },
  "variants": [
    {
      "variantId": "V-1",
      "color": "black",
      "stock": 8
    },
    {
      "variantId": "V-2",
      "color": "white",
      "stock": 4
    }
  ]
}
~~~

Possible update requirements include:

- Changing the product price.
- Adding a new tag without introducing duplicates.
- Removing an expired tag.
- Incrementing `viewCount` after each view.
- Decrementing `stock` after order confirmation.
- Updating `stock` for a variant with a specific `variantId`.
- Adding a new variant to the array.
- Changing the `color` attribute inside `attributes`.

Choose the update approach based on whether you need to read current values to determine the change.

## 2. Partial Updates Using `UpdateQuery` and `Document`

When you know the exact new values for fields, a partial document is usually simplest.

Example changing only price and status:

~~~java
Document patch = Document.create();
patch.put("price", 85.0);
patch.put("status", "ACTIVE");

UpdateQuery updateQuery = UpdateQuery.builder("P-100")
    .withDocument(patch)
    .build();

UpdateResponse response = operations.update(
    updateQuery,
    IndexCoordinates.of("products")
);
~~~

In the example, only the fields sent in `Document` are requested for update. Other fields such as `name`, `stock`, and `tags` are preserved from the document's current content.

Data types in `Document` must be compatible with the mapping:

- `String` for `keyword`/`text` fields.
- `Boolean` for `boolean` fields.
- `Number` matching numeric types.
- `Map` or `Document` for objects.
- `List` for arrays.

Do not send numbers as strings if the mapping is numeric. Also avoid manually building JSON via string concatenation to construct patches.

### Partial Documents Do Not Automatically Perform Calculations

If you send:

~~~java
patch.put("viewCount", 451);
~~~

this assigns the new value `451`. It does not mean "read the current value and add 1". When an operation depends on current state, use a script.

### Updating Objects

For a regular object like `attributes`, you can send a partial object:

~~~java
Document attributesPatch = Document.create();
attributesPatch.put("color", "blue");

Document patch = Document.create();
patch.put("attributes", attributesPatch);
~~~

How objects and sub-fields are merged depends on Update API semantics and request structure. Verify the result on your running Elasticsearch version, especially when you want to preserve sibling attributes inside an object. If the goal is to change a single nested attribute without accidentally replacing the whole object, a script updating that exact sub-field expresses the intent more clearly.

### Arrays Are Treated as a Single Value

Partial updates do not offer append/remove operations for arrays. If you send a new array field, treat it as the entire array value to be written for that field. For instance, sending new `tags` replaces the current `tags` list with the sent list; it does not automatically append elements to the old array.

To add, remove, or edit an element based on current content, use a Painless script.

## 3. Using Painless Scripts in `UpdateQuery`

Painless is Elasticsearch's scripting language. An update script can access the document being updated via `ctx._source` and parameters passed via `params`.

An example incrementing a counter:

~~~java
Map<String, Object> params = Map.of(
    "amount", 1
);

UpdateQuery updateQuery = UpdateQuery.builder("P-100")
    .withScript("ctx._source.viewCount = (ctx._source.viewCount == null ? 0 : ctx._source.viewCount) + params.amount")
    .withParams(params)
    .withLang("painless")
    .build();

UpdateResponse response = operations.update(
    updateQuery,
    IndexCoordinates.of("products")
);
~~~

The script performs:

1. Reads the current `viewCount`.
2. If the field is missing or `null`, uses initial value `0`.
3. Adds `params.amount`.
4. Writes the result back to `_source`.

Do not concatenate user values directly into the script string. Use `params` to pass data; this separates script code from data and prevents escaping errors or generating distinct scripts per value.

The `UpdateQuery` builder API can differ across release trains. Verify overloads for `withScript`, `withParams`, `withLang`, `withDocument`, and upsert options in your project's Spring Data Elasticsearch version. Code snippets in this lesson illustrate common APIs and do not replace checking actual dependencies.

## 4. Adding Elements to a Scalar Array

Suppose the `tags` field is a keyword array:

~~~java
@Field(type = FieldType.Keyword)
private List<String> tags;
~~~

To add a new tag, you can use a script:

~~~java
Map<String, Object> params = Map.of(
    "tag", "sale"
);

String script = """
    if (ctx._source.tags == null) {
        ctx._source.tags = new ArrayList();
    }
    ctx._source.tags.add(params.tag);
    """;

UpdateQuery updateQuery = UpdateQuery.builder("P-100")
    .withScript(script)
    .withParams(params)
    .withLang("painless")
    .build();

operations.update(
    updateQuery,
    IndexCoordinates.of("products")
);
~~~

The script checks `tags` before adding. If the field does not exist yet, it creates an `ArrayList` and then appends the element.

### Avoiding Duplicates

If business rules require each tag to appear only once:

~~~java
String script = """
    if (ctx._source.tags == null) {
        ctx._source.tags = new ArrayList();
    }
    if (!ctx._source.tags.contains(params.tag)) {
        ctx._source.tags.add(params.tag);
    }
    """;
~~~

If the tag already exists, the script leaves the document unchanged. Depending on configuration and version, you can set `ctx.op = 'noop'` when no changes occur to avoid creating a new index revision:

~~~java
String script = """
    if (ctx._source.tags == null) {
        ctx._source.tags = new ArrayList();
    }
    if (ctx._source.tags.contains(params.tag)) {
        ctx.op = 'noop';
    } else {
        ctx._source.tags.add(params.tag);
    }
    """;
~~~

Use `noop` when there is genuinely no change to save. It helps distinguish updates that modified data from requests that did nothing.

### Limiting Array Size

Do not let arrays grow without bound. For tags, event histories, or ID lists, enforce an element count limit, TTL, or move long histories into a separate index. Oversized arrays bloat documents, increase reindexing overhead, and make every update resource-intensive.

## 5. Removing Elements from a Scalar Array

To remove all elements equal to `params.tag`, you can iterate backward through the array:

~~~java
Map<String, Object> params = Map.of(
    "tag", "obsolete"
);

String script = """
    if (ctx._source.tags != null) {
        for (int i = ctx._source.tags.size() - 1; i >= 0; i--) {
            if (params.tag.equals(ctx._source.tags[i])) {
                ctx._source.tags.remove(i);
            }
        }
    }
    """;
~~~

Iterating from back to front lets you remove elements without shifting the indices of remaining unvisited elements.

If you only need to remove the first matching element, you can loop and `break` after removing. Define the business rule clearly: remove one occurrence or remove all occurrences.

### Removing the Field When the Array Is Empty

After removing the last element, you can either keep the field as an empty array:

~~~json
{
  "tags": []
}
~~~

Or remove the field completely from `_source`:

~~~java
if (ctx._source.tags.isEmpty()) {
    ctx._source.remove('tags');
}
~~~

These two states can carry different meanings for the application and queries. Pick one consistent convention. If you treat `null`, an empty array, and a missing field as three distinct states, verify queries, serialization, and mappings accordingly.

## 6. Replacing or Adding Multiple Elements

When you need to replace the entire array with a list computed in the service, a partial document is a clear choice:

~~~java
Document patch = Document.create();
patch.put("tags", List.of("wireless", "keyboard", "sale"));

UpdateQuery updateQuery = UpdateQuery.builder("P-100")
    .withDocument(patch)
    .build();
~~~

If the new list needs to be merged with the existing list, you can use a script:

~~~java
Map<String, Object> params = Map.of(
    "newTags", List.of("sale", "featured")
);

String script = """
    if (ctx._source.tags == null) {
        ctx._source.tags = new ArrayList();
    }
    for (def tag : params.newTags) {
        if (!ctx._source.tags.contains(tag)) {
            ctx._source.tags.add(tag);
        }
    }
    """;
~~~

If element ordering matters, maintain clear ordering rules. If the array is simply a set of values, consider normalizing and deduplicating before writing.

## 7. Updating Counters

Counters frequently appear in fields such as:

- `viewCount`: number of views.
- `downloadCount`: number of downloads.
- `likes`: number of likes.
- `retryCount`: number of retries.
- `stock`: inventory quantity.

### Incrementing a Counter

Painless script:

~~~java
Map<String, Object> params = Map.of("delta", 1);

String script = """
    if (ctx._source.viewCount == null) {
        ctx._source.viewCount = 0;
    }
    ctx._source.viewCount += params.delta;
    """;
~~~

### Decrementing a Counter with Bounds Checking

Example decrementing `stock` without allowing negative values:

~~~java
Map<String, Object> params = Map.of("quantity", 2);

String script = """
    if (ctx._source.stock == null) {
        ctx.op = 'noop';
    } else if (ctx._source.stock < params.quantity) {
        throw new IllegalArgumentException('Insufficient stock');
    } else {
        ctx._source.stock -= params.quantity;
    }
    """;
~~~

In an ordering system, checking inventory and decrementing quantity must happen inside the same update script to avoid the time gap between read and write in the application tier. If quantity is insufficient, the script can raise an error for the service to handle per business rules.

However, Elasticsearch is not a transactional inventory management system. Do not use a single Elasticsearch document as the sole source of truth for financial or inventory workflows requiring strong transactional guarantees, reservations, ledgers, or multi-resource coordination. You can use a transactional database as the primary source and sync search state to Elasticsearch.

### Adding/Subtracting with a Signed Delta

A general script can accept a signed `delta`:

~~~java
Map<String, Object> params = Map.of("delta", -3);

String script = """
    int current = ctx._source.retryCount == null
        ? 0
        : ctx._source.retryCount;
    int next = current + params.delta;
    if (next < 0) {
        throw new IllegalArgumentException('Counter cannot be negative');
    }
    ctx._source.retryCount = next;
    """;
~~~

Check the numeric type of the field and `params`. For large counters, use `long` instead of `int`. Avoid unnecessary casting if values can exceed the 32-bit integer range.

### Event-Based Counting and Idempotency

An increment script can execute atomically for a single document update accepted by Elasticsearch. However, if the client times out after Elasticsearch already wrote the update successfully, the client might resend the request and increment the counter again.

If you need to prevent duplicate event processing, do not rely on simple addition alone. Use an event ID/idempotency key, record processed event markers, or design an update pipeline capable of deduplication. A single aggregate counter usually lacks enough information to tell which events have already been applied.

## 8. Updating Nested Objects

For a regular object:

~~~json
{
  "attributes": {
    "color": "black",
    "layout": "US",
    "backlit": true
  }
}
~~~

To change only `color`:

~~~java
Map<String, Object> params = Map.of(
    "color", "blue"
);

String script = """
    if (ctx._source.attributes == null) {
        ctx._source.attributes = new HashMap();
    }
    ctx._source.attributes.color = params.color;
    """;
~~~

The script manipulates the sub-property directly in `_source`. Other attributes like `layout` and `backlit` are preserved.

If the object can be `null`, initialize it before assigning. If the object has deeper nesting, check each level before accessing to avoid null pointer errors in the script.

### Updating Deep Fields

Example object:

~~~json
{
  "shipping": {
    "address": {
      "city": "Ho Chi Minh City",
      "district": "District 1"
    }
  }
}
~~~

Changing `district`:

~~~java
Map<String, Object> params = Map.of(
    "district", "District 3"
);

String script = """
    if (ctx._source.shipping == null) {
        ctx._source.shipping = new HashMap();
    }
    if (ctx._source.shipping.address == null) {
        ctx._source.shipping.address = new HashMap();
    }
    ctx._source.shipping.address.district = params.district;
    """;
~~~

Only create intermediate objects when needed. If the object is required by schema, you can validate before updating and treat a missing object as a data error rather than auto-initializing it.

## 9. Updating an Element in an Array of Objects

Suppose a document has a `variants` array:

~~~json
{
  "variants": [
    {
      "variantId": "V-1",
      "color": "black",
      "stock": 8
    },
    {
      "variantId": "V-2",
      "color": "white",
      "stock": 4
    }
  ]
}
~~~

To update the `stock` of variant `V-2`:

~~~java
Map<String, Object> params = Map.of(
    "variantId", "V-2",
    "newStock", 7
);

String script = """
    if (ctx._source.variants != null) {
        boolean found = false;
        for (def variant : ctx._source.variants) {
            if (params.variantId.equals(variant.variantId)) {
                variant.stock = params.newStock;
                found = true;
                break;
            }
        }
        if (!found) {
            ctx.op = 'noop';
        }
    } else {
        ctx.op = 'noop';
    }
    """;
~~~

The script iterates over the array in `_source`, locates the object with matching `variantId`, and updates `stock`. The example uses `break` to update only the first match. If `variantId` is not unique and all matches should be updated, omit `break`.

### Checking Whether the Element Exists

Two common policies are:

- If the variant is not found, `noop`, because the operation might be retried or the variant may have been removed.
- If the variant is not found, raise a business error, because an invalid ID needs to be detected.

Pick an explicit policy. Do not silently append a new variant when the original intent was to update an existing variant.

### Adding a New Object to the Array

~~~java
Map<String, Object> newVariant = Map.of(
    "variantId", "V-3",
    "color", "blue",
    "stock", 0
);

Map<String, Object> params = Map.of(
    "variant", newVariant
);

String script = """
    if (ctx._source.variants == null) {
        ctx._source.variants = new ArrayList();
    }
    boolean exists = false;
    for (def variant : ctx._source.variants) {
        if (params.variant.variantId.equals(variant.variantId)) {
            exists = true;
            break;
        }
    }
    if (exists) {
        ctx.op = 'noop';
    } else {
        ctx._source.variants.add(params.variant);
    }
    """;
~~~

The script checks the ID before appending to avoid adding duplicates. If you want to update when it already exists and add when absent, you can replace the `noop` branch with logic updating allowed fields.

### Removing an Object from the Array

Iterate backward to remove an element by `variantId`:

~~~java
Map<String, Object> params = Map.of(
    "variantId", "V-2"
);

String script = """
    if (ctx._source.variants != null) {
        for (int i = ctx._source.variants.size() - 1; i >= 0; i--) {
            if (params.variantId.equals(ctx._source.variants[i].variantId)) {
                ctx._source.variants.remove(i);
            }
        }
    }
    """;
~~~

If `variantId` is guaranteed unique, you can stop after the first removal. If legacy data could contain duplicate IDs, decide explicitly whether to remove one or all and handle inconsistent data.

## 10. Nested Mapping and Updating Nested Objects

An array of objects can be mapped as `object` or `nested`. Distinguish:

- **object**: values are flattened during indexing; queries do not preserve boundaries between individual objects in the array.
- **nested**: each element is indexed as a nested Lucene document so queries/aggregations preserve relationships within each object.

Example `nested` mapping:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Nested)
    private List<Variant> variants;
}
~~~

In `_source`, `variants` is still a JSON array of objects. Update scripts work on the parent document's `_source`, so adding, editing, or removing array elements still uses Painless loops as shown in earlier examples.

Important point: a nested object is not an independent document with its own ID that can be targeted directly via the Update API. The ID-based Update API targets the parent document. When modifying a nested object, Elasticsearch reindexes the parent document and its related nested Lucene documents.

### Why Can't Nested Children Be Updated by Their Own ID?

Nested documents have an internal relationship with the parent and are managed as part of the parent document. You cannot pass a nested object's ID as an independent document ID to the Update API. To modify a single line or variant, update the parent document via a script or resend the appropriate data portion.

If the application needs to update individual elements frequently, independently, and with separate lifecycles, consider modeling each element as a separate document in another index, storing the parent ID to link them at the application layer.

### Nested Queries Do Not Automatically Scope Scripts to One Child

A nested query can select parent documents that have a matching nested child. However, the update script still runs on the parent's `_source`. If you need to modify only the nested objects matching a condition, the script itself must loop through the array and check that condition. Do not assume a nested query automatically passes a single matched child object into the script.

## 11. Upsert: Update or Create If Missing

Some operations need to create the document if the ID does not yet exist. The Update API supports upsert.

Example partial document upsert:

~~~java
Document initial = Document.create();
initial.put("name", "Wireless Keyboard");
initial.put("stock", 0);
initial.put("viewCount", 0);

UpdateQuery updateQuery = UpdateQuery.builder("P-200")
    .withDocument(Document.from(Map.of("status", "ACTIVE")))
    .withUpsert(initial)
    .build();

operations.update(
    updateQuery,
    IndexCoordinates.of("products")
);
~~~

If the document exists, the partial document is applied. If it does not exist, the `upsert` content is used to create the document.

### `doc_as_upsert`

Some versions of `UpdateQuery` support `docAsUpsert`. When enabled, the partial document is also used as the creation content if the document does not yet exist. Check the API and semantics of your release.

Upsert needs enough required data to create a valid document. If you only send `status` while new documents require `name`, mapping compliance, and other business fields, upsert can create an incomplete document or violate application conventions.

### `scripted_upsert`

With scripted upsert, the script can execute even when the document does not yet exist. In that case, you must initialize `ctx._source` properly and distinguish creation from updates. The `scripted_upsert` and `upsert` options have distinct semantics; do not enable them just to make a script run in all cases.

## 12. Updating Multiple Documents Using `update-by-query`

If you need to change every document matching a condition, avoid fetching all of them to Java, editing each object, and sending them back. `update-by-query` lets Elasticsearch find documents by query and apply a script to each selected document.

Example incrementing `version` for all products in category `accessories`:

~~~http
POST /products/_update_by_query?conflicts=proceed
{
  "query": {
    "term": {
      "category": "accessories"
    }
  },
  "script": {
    "lang": "painless",
    "source": "ctx._source.catalogVersion = params.version",
    "params": {
      "version": 3
    }
  }
}
~~~

`update-by-query` runs across the set of documents matching the query. It can process in internal batches and return counts of updated documents, noops, conflicts, or errors.

### `update-by-query` with Object Arrays

Example resetting `stock` of variant `V-2` across products containing at least one `V-2` variant:

~~~http
POST /products/_update_by_query?conflicts=proceed
{
  "query": {
    "nested": {
      "path": "variants",
      "query": {
        "term": {
          "variants.variantId": "V-2"
        }
      }
    }
  },
  "script": {
    "lang": "painless",
    "source": """
      for (def variant : ctx._source.variants) {
        if (params.variantId.equals(variant.variantId)) {
          variant.stock = params.stock;
        }
      }
    """,
    "params": {
      "variantId": "V-2",
      "stock": 7
    }
  }
}
~~~

The nested query selects parent documents that have at least one matching variant. The script still iterates through the array in `_source` and updates the matching element by ID.

### Batch Updates and Load Control

`update-by-query` can affect large volumes of data. Consider:

- Does the query select the exact intended set of documents?
- Which alias/index can it run against?
- Appropriate batch size and throttling.
- How version conflicts are handled.
- Timeouts and task cancellation.
- Updated document counts and partial errors.
- Refresh timing so new data becomes searchable.

Do not run broad `update-by-query` operations during peak hours without assessing load and having a rollback/reindexing plan. For schema changes or large data transformations, reindexing into a new index may be preferable to in-place updates.

### Using the Elasticsearch Java API Client

The direct client provides an `update-by-query` API in supported client versions:

~~~java
UpdateByQueryResponse response =
    elasticsearchClient.updateByQuery(r -> r
        .index("products")
        .query(q -> q.term(t -> t
            .field("category")
            .value("accessories")
        ))
        .script(s -> s.inline(i -> i
            .lang("painless")
            .source("ctx._source.catalogVersion = params.version")
            .params("version", JsonData.of(3))
        )),
        RequestOptions.DEFAULT
    );
~~~

This illustrates the client API; response types, `JsonData` usage, and request overloads depend on the Elasticsearch Java API Client version. If the project uses a Spring Data abstraction for `update-by-query`, check the corresponding API in your release train. Do not mix legacy client requests directly with the newer Java API Client.

## 13. Bulk Updates When the List of IDs Is Known

If the application already knows the set of documents to update, bulk updates are generally preferable to sending individual requests.

Example updating `status` for multiple IDs using Spring Data operations:

~~~java
List<UpdateQuery> updates = List.of(
    UpdateQuery.builder("P-100")
        .withDocument(Document.from(Map.of("status", "ACTIVE")))
        .build(),
    UpdateQuery.builder("P-101")
        .withDocument(Document.from(Map.of("status", "ACTIVE")))
        .build(),
    UpdateQuery.builder("P-102")
        .withDocument(Document.from(Map.of("status", "ACTIVE")))
        .build()
);

operations.bulkUpdate(
    updates,
    IndexCoordinates.of("products")
);
~~~

The `bulkUpdate` API and return type can vary across Spring Data Elasticsearch versions. The goal of the example is to send multiple update operations in one bulk request to reduce network overhead.

The Bulk API does not guarantee all items succeed or roll back together. Some items may succeed while others fail. Always read each item's result, record failed IDs, and design retries for operations that can safely be re-executed.

### Choosing Bulk vs. `update-by-query`

| Scenario | Suitable approach |
|---|---|
| List of IDs and per-document patches are known | Bulk update |
| One query condition defines the document set and all documents use the same script | Update-by-query |
| Updating only a single document by ID | Update API / `UpdateQuery` |
| Complex business reading and computation across multiple sources | Service orchestration, followed by bulk update |
| Changing index structure or mapping | New index and reindex |

## 14. Concurrent Updates and Version Conflicts

Two requests can update the same document nearly simultaneously. Elasticsearch uses optimistic concurrency control to avoid overwriting a newer version unknown to the client.

The Update API can use `retry_on_conflict` to retry when a version conflict occurs. With increment scripts, retrying allows the script to re-run against the latest version under Elasticsearch's update mechanism.

Example configuring retry:

~~~java
UpdateQuery updateQuery = UpdateQuery.builder("P-100")
    .withScript("ctx._source.viewCount = (ctx._source.viewCount ?: 0) + params.delta")
    .withParams(Map.of("delta", 1))
    .withLang("painless")
    .withRetryOnConflict(3)
    .build();
~~~

Null-coalescing operator syntax in scripts can depend on Painless; explicit null checks as shown earlier are easier to read and less error-prone. Importantly, retry is not a mechanism guaranteeing a client request executes only once.

### Sequence Number and Primary Term

When the application reads a document and decides to write based on that exact version read, `if_seq_no` and `if_primary_term` can be used to update only if the document has not changed since that read.

If the condition no longer holds, Elasticsearch returns a version conflict. The service can re-read, recompute, or return a conflict error to the client.

This is useful when the update is a decision based on a read snapshot. For simple additions/subtractions executable by script, there is no need to read and write manually in the application.

### Retries Can Repeat Side Effects Outside Elasticsearch

`retry_on_conflict` handles conflicts internal to the update mechanism. It does not solve the case where a client resends the same business request after a timeout when the prior attempt already succeeded. For operations with side effects such as adding points, deducting inventory, or crediting money, an idempotency key and appropriate transactional source of truth are required.

## 15. Noop, Delete, and Conditional Updates

A script can decide to leave the document unchanged:

~~~java
String script = """
    if (ctx._source.status == params.status) {
        ctx.op = 'noop';
    } else {
        ctx._source.status = params.status;
    }
    """;
~~~

If the value is already correct, setting `noop` avoids unnecessarily reindexing the document.

Scripts can also request deleting the document using `ctx.op = 'delete'`, though you must distinguish deleting the document from removing an array element. Use `delete` only when business logic requires removing the entire document.

Do not use a script to replace a simple update when a partial document clearly expresses the intent. Scripts are more flexible but harder to govern and can consume more CPU.

## 16. Script Parameters and Update Safety

Do not concatenate input directly into scripts:

~~~java
// Avoid constructing scripts by concatenating user values.
String script = "ctx._source.name = '" + userInput + "'";
~~~

Instead, use `params`:

~~~java
Map<String, Object> params = Map.of(
    "name", userInput
);

String script = "ctx._source.name = params.name";
~~~

Benefits:

- The script source is stable and easy to cache.
- Data does not alter script syntax.
- Avoids escaping bugs when values contain quotes or special characters.
- Easier to test the script with varied values.

Only allow scripts and fields controlled by the application. Do not accept arbitrary Painless scripts from clients. In production environments, consider stored scripts or cluster script policies if many queries/updates share logic.

## 17. When Should You Change the Data Model?

If a document has a large array of objects and a small element is updated frequently, every update still causes the entire parent document to be reindexed. This can become costly when the array is large or many concurrent update requests occur.

Consider splitting elements into separate documents when:

- Each element has an independent lifecycle.
- An element is updated more frequently than its parent.
- The array can grow very large.
- Independent permissions or optimistic concurrency are needed per element.
- Independent searching, paging, and statistics per element are needed.

For example, instead of storing `variants` inside `product`:

~~~json
{
  "productId": "P-100",
  "variants": [
    {"variantId": "V-1", "stock": 8},
    {"variantId": "V-2", "stock": 4}
  ]
}
~~~

you can create a `variants` index where each variant is a document:

~~~json
{
  "variantId": "V-2",
  "productId": "P-100",
  "stock": 4
}
~~~

Then updating `V-2`'s stock updates a separate document. In exchange, queries must combine `product` and `variant` data at the application layer or via an appropriate mechanism. Elasticsearch does not automatically provide transactional joins between two indices like table relationships in a relational database.

## 18. Checking Update Results

The Update API typically returns information such as ID, version, sequence number, primary term, and operation result. Results can distinguish:

- **UPDATED**: the document was modified.
- **NOOP**: the script did not modify the document.
- **CREATED**: the document was created via upsert.
- **DELETED**: the document was deleted per script.

Enum types and response property names depend on the client API / Spring Data version. Read the response to distinguish successful updates, noops, and creations.

After an update, the document will not necessarily appear in the next search request immediately if a refresh has not occurred yet. Elasticsearch refreshes make new changes searchable. Do not enable immediate refresh after every operation unless instant visibility latency is required; frequent refreshes can reduce indexing performance.

If you need to read the document immediately by ID, the Get API can return the latest content without waiting for search visibility. Distinguish read-by-ID from search-after-refresh in tests.

## 19. Service Example Updating Variant Stock

Example service receiving product ID, variant ID, and quantity change:

~~~java
public void decreaseVariantStock(
        String productId,
        String variantId,
        int quantity) {

    if (quantity <= 0) {
        throw new IllegalArgumentException(
            "quantity must be positive"
        );
    }

    Map<String, Object> params = Map.of(
        "variantId", variantId,
        "quantity", quantity
    );

    String script = """
        if (ctx._source.variants == null) {
            throw new IllegalArgumentException('Variants are missing');
        }

        boolean found = false;

        for (def variant : ctx._source.variants) {
            if (params.variantId.equals(variant.variantId)) {
                if (variant.stock == null || variant.stock < params.quantity) {
                    throw new IllegalArgumentException('Insufficient stock');
                }

                variant.stock -= params.quantity;
                found = true;
                break;
            }
        }

        if (!found) {
            throw new IllegalArgumentException('Variant not found');
        }
        """;

    UpdateQuery updateQuery = UpdateQuery.builder(productId)
        .withScript(script)
        .withParams(params)
        .withLang("painless")
        .withRetryOnConflict(3)
        .build();

    operations.update(
        updateQuery,
        IndexCoordinates.of("products")
    );
}
~~~

This example illustrates checking and decrementing stock within the same update script on the parent document. In real-world applications:

- Translate script errors into appropriate business errors.
- Ensure `variantId` is unique within a product.
- Use an idempotency key if requests can be resent after timeouts.
- Consider a transactional data source for inventory.
- Log results without exposing sensitive data.
- Verify builder APIs and exception mapping for the dependency version in use.

## 20. Testing Operations That Modify Arrays and Objects

You should test updates against real data on a compatible Elasticsearch instance, because Painless, mappings, and Update API semantics cannot be verified solely by unit tests calling Java methods.

Important test cases:

| Case | Expected result |
|---|---|
| Add tag to existing array | New tag appears |
| Add existing tag under unique policy | No duplicate created |
| Remove tag | Occurrences removed per policy |
| Array does not yet exist | Script initializes or handles per rules |
| Empty array after removal | Retain empty array or remove field per convention |
| Increment counter | New value equals old value plus delta |
| Null counter | Uses defined initial value |
| Decrement stock with sufficient quantity | Stock decreases accurately |
| Decrement stock with insufficient quantity | Update fails and does not write a negative value |
| Update sub-object | Target field changes; sibling fields remain preserved |
| Update nested child | Correct child is modified in parent source |
| Missing child | Noop or error per policy |
| Upsert | Creates document with all required fields |
| Two concurrent updates | No silent overwrites per concurrency strategy |
| Client retry after timeout | Idempotency handled at the business layer |

Integration test skeleton:

~~~java
@Test
void addsTagWithoutDuplicates() {
    // Index product with tags ["wireless"].
    // Call update script to add "sale".
    // Read document by ID.
    // Assert tags contain "wireless" and "sale".
    // Call the same operation again.
    // Assert "sale" appears only once.
}
~~~

Another test should create a product with multiple variants having different data, update one variant, and confirm the remaining variants are unchanged. With nested mappings, tests should confirm the actual mapping is `nested` and that nested queries still work after updates.

## 21. Common Mistakes and Troubleshooting

| Symptom | Possible cause | Resolution |
|---|---|---|
| Entire array replaced | Sent a partial document containing the array field expecting an append | Use a script to add/remove elements |
| Tag appears multiple times | Append script did not check existence | Use `contains` or uniqueness rules |
| Removing elements misses occurrences | Stopped loop after the first match | Iterate backward if removing all occurrences |
| Script throws null pointer | Field or intermediate object does not exist | Check and initialize each level |
| Counter incremented twice | Client retried after timeout or duplicate event | Use an idempotency key / deduplication |
| Negative stock | Check and write separated in application | Check and decrement inside the same script |
| Update conflict | Multiple requests updating the same document | Bounded retry or optimistic concurrency |
| Nested child cannot be updated by ID | Nested object is not an independent document | Update the parent by ID |
| Script does not see the child selected by nested query | Script operates on parent `_source` | Loop through the array and check the child inside the script |
| Upsert creates document missing fields | Incomplete upsert payload | Build a valid upsert payload or use scripted upsert |
| Bulk has failed items | Bulk lacks all-or-nothing transactions | Read each item result and retry controllably |
| Search does not see changes yet | Index not yet refreshed | Use an appropriate refresh policy or read by ID |
| Script rejected | Invalid script or disallowed by policy | Check Painless and cluster script settings |

## 22. Choosing Partial Document, Script, Bulk, or `update-by-query`

| Need | Approach to consider |
|---|---|
| Assign new values to a few known fields | Partial document with `UpdateQuery` |
| Increment/decrement counter from current value | Scripted update |
| Add, remove, or edit an array element | Scripted update |
| Change a deep field inside an object | Scripted update or partial object patch with verified semantics |
| Update a non-existent document using a default payload | Upsert |
| Update multiple known IDs | Bulk update |
| Update all documents matching a query | Update-by-query |
| Each child requires frequent independent updates | Split children into separate documents |
| Business requires strong transactions or event deduplication | Use a suitable transactional/idempotency system as the source of truth |

Partial documents are readable and suited for assignments. Scripts are necessary when changes depend on current state. Bulk reduces requests when IDs are known. Update-by-query fits broad conditional changes.

Do not use scripts for every update. Nor should you fetch documents to Java, edit arrays, and rewrite the entire document when an atomic per-document operation can execute in Elasticsearch.

## 23. Pre-Deployment Update Checklist

- [ ] Determine whether the operation is value assignment or a change based on current state.
- [ ] Partial documents are not mistaken for array append/remove.
- [ ] Scripts use `params` instead of interpolating data into `source`.
- [ ] Fields and intermediate objects are checked for `null`.
- [ ] Element addition operations have an explicit duplicate policy.
- [ ] Removal operations specify whether one or all occurrences are deleted.
- [ ] Arrays have size limits and empty/missing rules.
- [ ] Counters use appropriate numeric types and value bounds.
- [ ] Conditions are checked before decrementing stock or counters.
- [ ] Nested children are updated through the parent document.
- [ ] Upsert contains all required data.
- [ ] Retries and optimistic concurrency fit contention levels.
- [ ] Client-retried requests have an idempotency strategy when needed.
- [ ] Bulk/`update-by-query` operations have load limits and per-item result reading.
- [ ] Refresh policy matches visibility requirements.
- [ ] Integration tests verify results on a real Elasticsearch instance.

Modifying arrays, counters, and nested objects requires choosing the right update mechanism. Partial documents fit assigning known values; Painless scripts fit reading and modifying current structures such as appending, removing, incrementing, or updating a child object. With nested mappings, children still belong to the parent document, so updates occur on the parent. When updating multiple documents, use bulk if IDs are known or `update-by-query` if the dataset is defined by a query; design concurrency, retries, and idempotency according to business requirements.
