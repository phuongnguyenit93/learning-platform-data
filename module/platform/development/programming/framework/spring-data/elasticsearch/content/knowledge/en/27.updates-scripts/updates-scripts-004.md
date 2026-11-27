# Update Scripts with Painless and Script Parameters

Elasticsearch supports updating documents using scripts. Instead of sending a fixed partial document, the application can ask Elasticsearch to execute a piece of code against the current document to compute new values, evaluate conditions, skip the update, or delete the document.

The default scripting language typically used for this operation is **Painless**. Scripts can read and modify `ctx._source` while receiving input data via the `params` map.

In Spring Data Elasticsearch, you can create an inline `Script`, attach it to an `UpdateQuery`, and call `ElasticsearchOperations.update(...)`. This approach is appropriate when updating a document by ID using conditional logic or calculations.

## 1. When Is a Script Update Needed?

If you only want to assign fixed values to a few fields, a partial document is usually simpler:

~~~json
POST /products/_update/P-1001
{
  "doc": {
    "status": "PUBLISHED"
  }
}
~~~

However, some business requirements need to read the current value before deciding how to update:

- Increment stock quantity by a certain amount.
- Increment a counter whenever an event occurs.
- Change status only if the current status is still `DRAFT`.
- Add an element to a list if it does not already exist.
- Update a processing timestamp.
- Skip the request if the new value equals the current value.
- Delete the document when a business condition is met.

Example incrementing stock:

~~~json
POST /products/_update/P-1001
{
  "script": {
    "lang": "painless",
    "source": "ctx._source.stock += params.quantity",
    "params": {
      "quantity": 5
    }
  }
}
~~~

Elasticsearch reads the current document, executes the script with parameter `quantity = 5`, and then writes the modified source if the script permits the update.

## 2. What Is Painless?

Painless is a scripting language designed by Elasticsearch to run in contexts such as update, query, ingest, and aggregation. The language has Java-like syntax and supports data types and APIs permitted by Elasticsearch in each script context.

Painless is not a general-purpose JVM shell. Scripts run inside a sandbox with restrictions and permissions based on the context. Do not assume you can arbitrarily invoke any Java class, access the filesystem, or open network connections from a script.

Common elements in an update script:

| Element | Meaning |
|---|---|
| `ctx._source` | Map containing the current document's content |
| `params` | Map of parameters passed in by the request |
| `ctx._id` | Document ID in contexts supporting this property |
| `ctx._index` | Index name of the document |
| `ctx.op` | Controls the operation, e.g., update, delete, or skip |
| `ctx._source.field` | Reads or assigns a field in the document |

With the ID-based Update API, scripts typically operate on `ctx._source`. Changes made in the script are saved as the document's new source. Scripts do not automatically alter the index mapping.

## 3. Reading and Updating `ctx._source`

Suppose the current document is:

~~~json
{
  "productId": "P-1001",
  "name": "Wireless Keyboard",
  "stock": 12,
  "status": "PUBLISHED"
}
~~~

Increment stock by 5:

~~~json
{
  "script": {
    "lang": "painless",
    "source": "ctx._source.stock += params.quantity",
    "params": {
      "quantity": 5
    }
  }
}
~~~

After the update, the document may look like:

~~~json
{
  "productId": "P-1001",
  "name": "Wireless Keyboard",
  "stock": 17,
  "status": "PUBLISHED"
}
~~~

A script can assign new values:

~~~painless
ctx._source.status = params.status;
ctx._source.updatedAt = params.updatedAt;
~~~

It can read values before modifying them:

~~~painless
if (ctx._source.stock < params.minimumStock) {
    ctx._source.status = 'LOW_STOCK';
}
~~~

You must check whether a field might be missing or null before performing operations on it. If `stock` does not exist, direct addition can cause a runtime error.

Safer example:

~~~painless
if (ctx._source.stock == null) {
    ctx._source.stock = 0;
}
ctx._source.stock += params.quantity;
~~~

The script above initializes `stock` to 0 if the field is missing, and then increments it. If business rules require rejecting a document missing `stock`, check and raise an error instead of initializing it automatically.

## 4. Passing Values via `params`

Do not concatenate input values directly into the script source string. Keep the source stable and pass data separately via `params`.

Example:

~~~json
{
  "script": {
    "lang": "painless",
    "source": "ctx._source.status = params.newStatus",
    "params": {
      "newStatus": "PUBLISHED"
    }
  }
}
~~~

Advantages of `params`:

- The script source does not have to change for each input value.
- Avoids quoting and escaping bugs during string concatenation.
- Separates update logic from business data.
- Helps Elasticsearch reuse the compiled script cache when the source is identical.
- Reduces the risk of constructing scripts from untrusted content.

If multiple fields need updating:

~~~json
{
  "script": {
    "lang": "painless",
    "source": "ctx._source.status = params.status; ctx._source.updatedBy = params.user; ctx._source.updatedAt = params.time",
    "params": {
      "status": "PUBLISHED",
      "user": "admin-01",
      "time": "2026-11-13T10:00:00Z"
    }
  }
}
~~~

Do not accept arbitrary Painless code fragments sent by clients. Clients should send data and business choices from an allowlist; script sources must be managed by the application.

## 5. Conditional Updates

A script can inspect current values before making changes.

Example publishing a product only if its current status is `DRAFT`:

~~~painless
if (ctx._source.status == 'DRAFT') {
    ctx._source.status = 'PUBLISHED';
    ctx._source.publishedAt = params.publishedAt;
} else {
    ctx.op = 'noop';
}
~~~

If the status is not `DRAFT`, the script sets `ctx.op = 'noop'`. Elasticsearch does not rewrite the document in that case.

Multiple conditions can be checked:

~~~painless
if (ctx._source.stock == null) {
    throw new IllegalArgumentException('stock is required');
}

if (ctx._source.stock >= params.quantity) {
    ctx._source.stock -= params.quantity;
    ctx._source.updatedAt = params.updatedAt;
} else {
    ctx.op = 'noop';
}
~~~

The example above deducts stock only if the quantity is sufficient. However, whether to use `noop` or return an error must follow the business contract:

- `noop`: requests leaving the document unchanged.
- Throwing an exception: the request fails and the application receives an error.
- Updating a rejection status: if business logic requires recording the rejection reason or processing state.

Do not use `noop` to hide data errors or programming bugs. Distinguish conditions where no update is needed from invalid data.

## 6. Controlling Operations with `ctx.op`

In an update script, `ctx.op` lets you control the document processing outcome. Common values in the update context include:

| Value | Behavior |
|---|---|
| `index` | Saves the document after the script modifies the source |
| `noop` | Does not write changes |
| `delete` | Deletes the document |

Example skipping when the value has not changed:

~~~painless
if (ctx._source.status == params.status) {
    ctx.op = 'noop';
} else {
    ctx._source.status = params.status;
}
~~~

Example deleting a document if expired:

~~~painless
if (ctx._source.expiresAt < params.cutoffTime) {
    ctx.op = 'delete';
}
~~~

When working with dates and times, keep data types and formats consistent. If a field is stored as a `date`, pass parameters with types and units matching how the script compares them; do not arbitrarily compare date strings unless the format guarantees lexicographical order matches chronological order.

`ctx.op` only controls operations in contexts that support it. Do not treat these values as a general Java API or assume every script context has the same set of operations.

## 7. Attaching a Painless Script to Spring Data `UpdateQuery`

Spring Data Elasticsearch provides `Script`, `ScriptType`, and `UpdateQuery` to construct update requests.

Example incrementing stock:

~~~java
import java.util.Map;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Script;
import org.springframework.data.elasticsearch.core.query.ScriptType;
import org.springframework.data.elasticsearch.core.query.UpdateQuery;

public class ProductStockService {

    private final ElasticsearchOperations operations;

    public ProductStockService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void increaseStock(String productId, int quantity) {
        Script script = new Script(
                ScriptType.INLINE,
                "painless",
                "if (ctx._source.stock == null) { "
                        + "ctx._source.stock = 0; "
                        + "} "
                        + "ctx._source.stock += params.quantity",
                Map.of("quantity", quantity)
        );

        UpdateQuery updateQuery = UpdateQuery.builder(productId)
                .withScript(script)
                .build();

        operations.update(
                updateQuery,
                IndexCoordinates.of("products")
        );
    }
}
~~~

Processing flow:

1. Create the Painless script source.
2. Select `ScriptType.INLINE`.
3. Specify the language as `painless`.
4. Pass parameters in a map.
5. Attach the script to `UpdateQuery` by document ID.
6. Call `ElasticsearchOperations.update(...)` with the target index or alias.

Imports and builder methods must match the Spring Data Elasticsearch version in the project. In the example, `Script` is Spring Data Elasticsearch's type, not `co.elastic.clients.elasticsearch._types.Script` from the Java API Client.

## 8. Separating Script Source from Code Using Constants

If a script is used across multiple services, you can place the source in a constant or dedicated class:

~~~java
public final class ProductScripts {

    private ProductScripts() {
    }

    public static final String INCREASE_STOCK =
            "if (ctx._source.stock == null) { "
            + "ctx._source.stock = 0; "
            + "} "
            + "ctx._source.stock += params.quantity";
}
~~~

Then:

~~~java
Script script = new Script(
        ScriptType.INLINE,
        "painless",
        ProductScripts.INCREASE_STOCK,
        Map.of("quantity", quantity)
);
~~~

Do not generate a new source string by interpolating individual values into the script. Keep the script stable and vary `params`.

If the script source is long, you can manage it via resource files or stored scripts. In that case, have a deployment and versioning process to ensure the application calls the exact script present on the cluster.

## 9. Updating Multiple Fields in the Same Script

A single script can update multiple fields in one update call:

~~~painless
ctx._source.status = params.status;
ctx._source.updatedBy = params.updatedBy;
ctx._source.updatedAt = params.updatedAt;

if (ctx._source.auditCount == null) {
    ctx._source.auditCount = 0;
}
ctx._source.auditCount += 1;
~~~

Java:

~~~java
Map<String, Object> params = Map.of(
        "status", "PUBLISHED",
        "updatedBy", "admin-01",
        "updatedAt", "2026-11-13T10:00:00Z"
);

Script script = new Script(
        ScriptType.INLINE,
        "painless",
        ProductScripts.PUBLISH_PRODUCT,
        params
);

UpdateQuery updateQuery = UpdateQuery.builder(productId)
        .withScript(script)
        .build();

operations.update(
        updateQuery,
        IndexCoordinates.of("products")
);
~~~

Changes in a single update script are applied as a single document update. If the script fails, Elasticsearch does not save part of the changes and leave the rest unfinished like a multi-document transaction. The update request fails.

However, this does not turn a sequence of multiple update requests into a transaction. When updating multiple documents, each document can succeed or fail independently.

## 10. Handling Null Fields, Missing Fields, and Data Types

Painless operates on JSON sources deserialized into runtime types. A field may:

- Not exist.
- Have a `null` value.
- Have an integer type.
- Have a floating-point type.
- Have a string or list type.
- Have a different type than the script expects due to historical data.

Example checking before adding:

~~~painless
def currentStock = ctx._source.stock;

if (currentStock == null) {
    currentStock = 0;
}

ctx._source.stock = currentStock + params.quantity;
~~~

If legacy data contains `stock` as a string, addition may fail or produce unexpected behavior. Standardize mappings and data before running scripts across the entire index.

For quantities, prices, and currency:

- Identify the numeric type stored in the source.
- Pass `params` using the corresponding Java type.
- Avoid mixing `integer`, `long`, `double`, and `decimal` arbitrarily.
- For money, consider storing the smallest unit as an integer/long or using scaled numeric conventions.
- Validate negative values, overflow, and business bounds before sending.

Example validating quantity:

~~~painless
if (params.quantity <= 0) {
    throw new IllegalArgumentException('quantity must be positive');
}

if (ctx._source.stock == null) {
    throw new IllegalArgumentException('stock is missing');
}

ctx._source.stock += params.quantity;
~~~

Script-side validation protects data when multiple clients exist, though you should still validate at the application layer to return early, clear errors.

## 11. Updating Lists in `_source`

Painless can manipulate lists inside `_source`.

Example adding a tag if absent:

~~~painless
if (ctx._source.tags == null) {
    ctx._source.tags = [];
}

if (!ctx._source.tags.contains(params.tag)) {
    ctx._source.tags.add(params.tag);
} else {
    ctx.op = 'noop';
}
~~~

Params:

~~~json
{
  "tag": "FEATURED"
}
~~~

Removing a tag:

~~~painless
if (ctx._source.tags != null) {
    ctx._source.tags.removeIf(tag -> tag == params.tag);
}
~~~

For large lists or nested structures, pay attention to the cost of reading, iterating, and rewriting the entire source. If a list grows unboundedly, consider a different document or index design instead of continuously appending elements to the same array.

If a list may contain heterogeneous data types, check element types before calling methods or comparing.

## 12. Script Updates and Upsert

ID-based updates normally require the document to already exist. If the document does not yet exist, Elasticsearch may return a document-missing error.

Upsert allows providing an initial document when the ID does not yet exist. Two concepts must be distinguished:

- `upsert`: the source used when the document does not yet exist.
- `scripted_upsert`: requests that the script still run when the document does not yet exist.

Conceptual example: create a counter with an initial value of 0, then increment by the parameter.

~~~json
POST /counters/_update/order-count
{
  "scripted_upsert": true,
  "script": {
    "lang": "painless",
    "source": "if (ctx._source.count == null) { ctx._source.count = 0; } ctx._source.count += params.increment",
    "params": {
      "increment": 1
    }
  },
  "upsert": {
    "count": 0
  }
}
~~~

In Spring Data Elasticsearch, you can build an upsert document and attach it to `UpdateQuery`:

~~~java
import org.springframework.data.elasticsearch.core.document.Document;

Document upsert = Document.create();
upsert.put("count", 0);

UpdateQuery updateQuery = UpdateQuery.builder("order-count")
        .withScript(script)
        .withUpsert(upsert)
        .withScriptedUpsert(true)
        .build();

operations.update(
        updateQuery,
        IndexCoordinates.of("counters")
);
~~~

When scripted upsert is enabled, the script runs even when the document does not yet exist. Design the script to work properly with the provided upsert source.

Do not confuse `scripted_upsert` with `doc_as_upsert`. `doc_as_upsert` uses a partial document as the upsert source; `scripted_upsert` lets the script run during the upsert flow. Choose the option that fits the required logic and check combination limits in your API version.

## 13. Distinguishing Script Update, Partial Document, and `update_by_query`

The three mechanisms have different purposes:

| Mechanism | Scope | Suitable when |
|---|---|---|
| Partial document update (`doc`) | One document by ID | Assigning fixed fields |
| Script update (`script`) | One document by ID | Calculating or checking current values |
| Update by query | Multiple documents matching a query | Running the same logic over a set of documents |

Partial update:

~~~json
POST /products/_update/P-1001
{
  "doc": {
    "status": "PUBLISHED"
  }
}
~~~

Script update:

~~~json
POST /products/_update/P-1001
{
  "script": {
    "lang": "painless",
    "source": "ctx._source.stock += params.quantity",
    "params": {
      "quantity": 5
    }
  }
}
~~~

Update by query:

~~~json
POST /products/_update_by_query
{
  "query": {
    "term": {
      "status": "DRAFT"
    }
  },
  "script": {
    "lang": "painless",
    "source": "ctx._source.status = params.status",
    "params": {
      "status": "ARCHIVED"
    }
  }
}
~~~

Update by query can process many documents matching a query, but requires attention to document counts, version conflicts, timeouts, throttling, and per-batch results. Do not use update-by-query for a single document when the ID-based Update API suffices.

## 14. Executing `update_by_query` and Parameters

An update-by-query request can accept a script and params similar to the Update API:

~~~json
POST /products/_update_by_query?conflicts=proceed
{
  "query": {
    "term": {
      "status": "DRAFT"
    }
  },
  "script": {
    "lang": "painless",
    "source": "ctx._source.status = params.newStatus; ctx._source.updatedAt = params.updatedAt",
    "params": {
      "newStatus": "ARCHIVED",
      "updatedAt": "2026-11-13T10:00:00Z"
    }
  }
}
~~~

`conflicts=proceed` allows processing to continue when version conflicts occur, but it does not mean every document was updated. The response includes the number of updated documents, version conflicts, failures, and batch details.

If you need to guarantee all documents are updated, do not simply set `conflicts=proceed` and assume a successful request means the data is fully synced. Check the response and have a retry/reconciliation strategy for failed documents.

Update-by-query is not an atomic transaction across the entire set of documents. Some documents may already be updated before the request encounters an error or timeout.

## 15. Script Parameters and Java Data Types

`params` is JSON data passed into Painless. In Java, you can use a map:

~~~java
Map<String, Object> params = Map.of(
        "quantity", 5,
        "status", "PUBLISHED",
        "enabled", true
);
~~~

Commonly used values:

| Java | JSON/Painless |
|---|---|
| `String` | string |
| `Integer`, `Long` | integer number |
| `Double`, `Float` | floating-point number |
| `Boolean` | boolean |
| `List<?>` | array |
| `Map<String, ?>` | object |
| `null` | JSON null, if the map permits null values |

Note that `Map.of(...)` does not permit `null` keys or values. If you need to pass `null` values, use a map that supports `null` such as `HashMap` and define clearly how the script handles that value.

Example passing a list:

~~~java
Map<String, Object> params = Map.of(
        "newTags",
        List.of("FEATURED", "PROMOTED")
);
~~~

Painless can iterate over parameters:

~~~painless
if (ctx._source.tags == null) {
    ctx._source.tags = [];
}

for (def tag : params.newTags) {
    if (!ctx._source.tags.contains(tag)) {
        ctx._source.tags.add(tag);
    }
}
~~~

Do not pass arbitrary Java objects that the JSON serializer cannot convert. Use simple, explicit, JSON-compatible data types.

## 16. Stored Scripts and Inline Scripts

There are two ways to send scripts:

- **Inline script**: the source is embedded directly in the request.
- **Stored script**: the source is stored on Elasticsearch under an ID, and requests reference only the ID.

Inline script:

~~~json
{
  "script": {
    "lang": "painless",
    "source": "ctx._source.status = params.status",
    "params": {
      "status": "PUBLISHED"
    }
  }
}
~~~

A stored script is created using the Stored Script API:

~~~http
PUT /_scripts/set-product-status
Content-Type: application/json

{
  "script": {
    "lang": "painless",
    "source": "ctx._source.status = params.status"
  }
}
~~~

Then use the ID:

~~~json
{
  "script": {
    "id": "set-product-status",
    "params": {
      "status": "PUBLISHED"
    }
  }
}
~~~

Stored scripts are useful when the same logic is used across multiple services or when scripts need to be deployed independently of the application. Versioning and update permissions for stored scripts are required.

In Spring Data, you can use the version-appropriate script type to reference a script ID instead of an inline source. Check the `Script` constructor/builder in your dependency, as script type representations can vary across API generations.

## 17. Script Compilation and Performance

Elasticsearch compiles Painless scripts and maintains a compiled script cache. If every request generates a different source by embedding values, the cache becomes less effective and compilation counts increase.

Recommended practices:

- Keep the script source stable.
- Pass varying data via `params`.
- Avoid overly long scripts or scripts doing too much work.
- Avoid iterating over very large arrays if the work can be handled in the application or by changing the data model.
- Use partial document updates if only assigning fixed fields.
- Benchmark performance before running `update_by_query` on large indices.

Scripts can consume significant CPU and generate heavy write load, especially when updating many documents. Set limits, monitor runtime, and choose appropriate batch sizes and throttling.

## 18. Handling Version Conflicts and Retries

Elasticsearch uses optimistic concurrency control. If a document changes between when an update reads the source and writes it back, the operation can encounter a version conflict.

With the ID-based Update API, you can configure `retry_on_conflict` so Elasticsearch retries the operation when a conflict occurs:

~~~http
POST /products/_update/P-1001?retry_on_conflict=3
{
  "script": {
    "lang": "painless",
    "source": "ctx._source.stock += params.quantity",
    "params": {
      "quantity": 1
    }
  }
}
~~~

In Spring Data, `UpdateQuery` offers a builder option for conflict retries in supported versions:

~~~java
UpdateQuery updateQuery = UpdateQuery.builder(productId)
        .withScript(script)
        .withRetryOnConflict(3)
        .build();
~~~

Retrying does not turn the operation into a multi-document transaction. It instructs Elasticsearch to retry the update when a conflict is detected.

For cumulative scripts, consider idempotency. If the application resends the same event due to a timeout, the script might add the quantity twice. Elasticsearch's internal retry handles version conflicts; it does not resolve duplicate requests at the application layer. Use an event ID, idempotency key, or deduplication mechanism if business rules require each event to be applied only once.

## 19. Script Security and Governance

Scripts are logic executed on the cluster. External clients must never be allowed to submit arbitrary Painless sources.

Key principles:

1. Script sources are controlled by the application or deployment team.
2. Input values are passed through `params`.
3. Validate data types, value ranges, and parameter sizes.
4. Do not allow users to pick arbitrary fields if doing so could alter sensitive data.
5. Restrict update permissions to the necessary indices.
6. Separate stored script management permissions from runtime update permissions whenever possible.
7. Monitor script compilations, runtime errors, and execution duration.
8. Do not log or place secrets in `params`.
9. Avoid scripts with unbounded loops or processing overly large structures.
10. Review the Elasticsearch cluster's script policies and context-specific limits.

Painless has a sandbox, but it does not replace Elasticsearch authorization. Anyone authorized to update documents can still modify data within their granted permissions.

## 20. Common Mistakes

### Concatenating Parameters into the Source String

Concatenating user input directly into `source` increases the risk of quoting errors, script cache misses, and injection. Use `params`.

### Failing to Check for Null Fields

Addition or calling methods on missing/null fields can cause errors. Check before operating or reject the data per business rules.

### Confusing Spring Data's `Script` with the Java Client's `Script`

Spring Data has `org.springframework.data.elasticsearch.core.query.Script`; the Java API Client has its own type. Select the exact type matching the API being called.

### Treating Painless Like Full Java

Painless runs inside a sandbox and only allows APIs appropriate for the script context. Do not assume all Java classes or libraries are usable.

### Using Scripts for Simple Assignments

If you only need to update `status = PUBLISHED`, a partial document is usually easier to understand. Only use scripts when logic or calculations based on current values are needed.

### Forgetting to Handle Non-Existent Documents

ID-based updates can fail if the document does not exist. Use upsert when business rules allow, and clarify whether the script should run during upsert.

### Confusing `noop` with Business Success

`ctx.op = 'noop'` simply means the document was not written. The application still must decide whether that represents a valid outcome, a business conflict, or a rejected condition.

### Assuming `update-by-query` Is Atomic

Update-by-query processes multiple documents in batches. Partial success, conflicts, and failures can occur. Always inspect the response.

### Making Duplicate Events Disappear with Retries

Retry-on-conflict does not protect against duplicate client requests. Use idempotency or deduplication for events that might be resent.

### Trying to Update Mappings with Painless

Painless modifies the document's source, not the mapping. To change field types or mapping structure, use an appropriate mapping management and reindexing workflow.

## 21. Script Update Implementation Workflow

When implementing a Painless update:

1. Determine whether the update is for one document or multiple documents.
2. Use a partial document if only assigning fixed values.
3. Write Painless source with clear logic and null checks.
4. Pass varying data via `params`.
5. Validate types and value ranges in the application.
6. Construct the Spring Data `Script` and `UpdateQuery`.
7. Choose the target index/alias and routing if the document requires custom routing.
8. Define behavior when the document does not exist: error, upsert, or scripted upsert.
9. Choose the policy (`noop`, `delete`, or exception) for conditional branches.
10. Configure conflict retries if appropriate.
11. Test with existing documents, missing fields, `null` values, wrong types, and unmet conditions.
12. Verify duplicate requests and idempotency.
13. Monitor script errors, version conflicts, and execution times.
14. For `update-by-query`, inspect `updated`, `conflicts`, and `failures` counts.
15. Manage stored scripts with versioning and deployment permissions.

## References

- [Elasticsearch — Painless scripting language](https://www.elastic.co/guide/en/elasticsearch/painless/current/painless-guide.html)
- [Elasticsearch — Update API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-update.html)
- [Elasticsearch — Update by query API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-update-by-query.html)
- [Elasticsearch — Script APIs](https://www.elastic.co/guide/en/elasticsearch/reference/current/modules-scripting-using.html)
- [Spring Data Elasticsearch — Reference documentation](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch.html)
- [Spring Data Elasticsearch — UpdateQuery API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/query/UpdateQuery.html)

## Conclusion

Painless enables updating documents based on their current source, input parameters, and business conditions. In Spring Data Elasticsearch, create a `Script` with a stable source and `params`, attach it to an `UpdateQuery`, and call `ElasticsearchOperations.update(...)`. Use `ctx._source` to read/modify data, `params` to pass values, and `ctx.op` to control `noop` or `delete` when appropriate. Distinguish single-document updates from `update-by-query`, handle upserts and version conflicts intentionally, and avoid using scripts in place of partial updates when simple fixed-field assignments suffice.
