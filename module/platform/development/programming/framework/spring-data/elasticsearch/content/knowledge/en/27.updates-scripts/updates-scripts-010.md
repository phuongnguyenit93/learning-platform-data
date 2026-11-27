# Script Cost, Input Safety, and Edge-Case Testing

Painless scripts allow updating documents and computing values directly inside Elasticsearch. Scripts are helpful when an operation needs to read multiple fields, apply conditions, or transform data per document. However, scripts incur CPU costs, can generate heavy write load, and become a security risk if an application concatenates untrusted input directly into script code.

When using scripts in Spring Data Elasticsearch, control three aspects:

- **Cost:** distinguish script compilation cost from per-document execution cost; estimate how many documents are updated and how much data must be rewritten.
- **Input safety:** keep script code fixed, pass data via `params`, and validate types and value ranges at the application layer.
- **Edge cases:** define behavior for missing fields, `null` values, wrong types, empty collections, out-of-bounds values, duplicate requests, or concurrent updates.

Scripts should not be the default choice for every operation. If a task can be accomplished with a single-field update, an ingest pipeline, or application-side processing without reading document state on Elasticsearch, consider the simpler solution.

## 1. How Do Scripts Work in Elasticsearch?

Elasticsearch supports Painless, a scripting language designed for operations on Elasticsearch data. Scripts can run in various contexts, such as:

- Update context: modifying a document's `_source`.
- Update by query context: updating multiple documents matching a query.
- Ingest context: transforming documents in an ingest pipeline.
- Score context: computing relevance scores.
- Sort or aggregation context: using expressions in certain queries and aggregations.

Each context allows different variables and APIs. For example, update scripts normally read and write through `ctx._source`, whereas script scores can access fields via `doc`. Do not copy an example from one context verbatim into another context.

Example updating a single document:

~~~http
POST /products/_update/42
Content-Type: application/json

{
  "script": {
    "lang": "painless",
    "source": "ctx._source.stock = params.stock",
    "params": {
      "stock": 25
    }
  }
}
~~~

Elasticsearch receives the Painless code, compiles it if needed, and executes it in the update context on the specified document. The script assigns the `stock` field to the value from `params`.

In update scripts, `ctx._source` is a map representing the document's `_source` content. `params` is a map holding input data passed by the application in the request. Using `params` keeps script code stable and separates logic from data.

## 2. Two Types of Cost: Compilation and Execution

When evaluating script performance, separate two stages:

1. **Compilation:** Elasticsearch compiles Painless code into an executable form.
2. **Execution:** Elasticsearch runs the script within the document or query context.

Compilation cost is typically reduced by the script compilation cache. Execution cost is still incurred every time the script runs.

### 2.1. Compilation Cost

If every request sends a different script string, Elasticsearch may have to compile many script variants. Generating too many unique script sources in a short period can spike compilations, cause cache churn, and hit compilation rate limits.

Example to avoid:

~~~java
String source = "ctx._source.stock = " + userProvidedStock;
~~~

Every input value produces a different source. This also mixes data with program code, making safety harder to enforce.

Keep `source` fixed and pass values via `params`:

~~~json
{
  "script": {
    "lang": "painless",
    "source": "ctx._source.stock = params.stock",
    "params": {
      "stock": 25
    }
  }
}
~~~

When source, language, and context match, Elasticsearch can reuse the compiled script from the cache. Changing `params` values does not require creating a new source.

### 2.2. Execution Cost

Caching does not make script execution free. Every processed document still requires evaluating expressions, reading fields, checking conditions, and potentially rewriting `_source`.

Execution cost grows with:

- Number of documents processed.
- Expression complexity and loop counts.
- Number of fields or collection elements read.
- Size of `_source` loaded and rewritten.
- Number of shards involved and degree of parallelism.
- Index write, refresh, and merge rates.
- Target system processing time if combined with exports or synchronization.

A short script running across millions of documents can still consume substantial resources. Conversely, a complex script running on a single document may be negligible. Always evaluate both per-document cost and the number of affected documents.

### 2.3. Compilation Cache and Limits

Elasticsearch provides a script cache and compilation rate limit settings. Setting names and defaults can vary across versions. Common settings include:

- `script.cache.max_size`: number of compiled scripts held in the cache.
- `script.cache.expire`: expiration time for cache entries if configured.
- `script.max_compilations_rate`: rate limit for script compilations.
- `script.allowed_types`: permitted script types, e.g., `inline` or `stored`.
- `script.allowed_contexts`: permitted script execution contexts.

Do not raise limits merely to mask dynamic source generation. First use fixed sources, `params`, and stored scripts where appropriate. If cluster settings need tuning, measure compilation rates and cache evictions under realistic load, and adjust per system operational policy.

## 3. Fixed Script Source and `params`

A core principle is never interpolating input data into the script code string. Keep `source` fixed and pass values via `params`.

Example incrementing stock by a received quantity:

~~~http
POST /products/_update/42
Content-Type: application/json

{
  "script": {
    "lang": "painless",
    "source": "ctx._source.stock = (ctx._source.stock == null ? 0 : ctx._source.stock) + params.delta",
    "params": {
      "delta": 5
    }
  }
}
~~~

The script code does not change with `delta`. The application sends only the new value in `params`.

Benefits:

- Reduces the number of script sources requiring compilation.
- Prevents inputs from becoming part of program syntax.
- Easier to read, test, and reuse scripts.
- Easier to enforce data types and value bounds.
- Enables migrating from inline scripts to stored scripts without altering business logic.

### 3.1. Do Not Let Users Submit Arbitrary Scripts

Do not build an API that accepts script bodies submitted by clients and executes them directly. API users should only choose from application-defined business operations, such as `increaseStock`, `setStatus`, or `appendTag`. The server maps that operation to a controlled script source and passes only validated parameters.

If dynamic field selection is needed, enforce an allowlist at the application tier:

~~~java
Set<String> allowedFields =
        Set.of("viewCount", "downloadCount", "favoriteCount");

if (!allowedFields.contains(request.field())) {
    throw new IllegalArgumentException("Unsupported counter field");
}
~~~

Do not concatenate untrusted field names directly into script sources. For selectable fields, check names against an allowlist or map from an enum to fixed field names.

### 3.2. `params` Do Not Replace Validation

Passing data via `params` separates data from code, but does not automatically guarantee valid data. For example, `delta` might be negative, `null`, excessively large, or of a type disallowed by business rules.

The application should validate before sending the request:

- Correct data types.
- Values within permitted bounds.
- Bounded string and collection sizes.
- Enum or status belonging to a valid list.
- Consistency among related values.

Scripts can also enforce invariants that must hold at the moment of update, yet API-level validation remains necessary to return early, clear errors.

## 4. Painless and Safety Boundaries

Painless is designed with a sandbox and an API allowlist. A script is not an arbitrary Java program with full access to the JVM, filesystem, or network. Usable classes and APIs depend on the context and Elasticsearch's allowlist.

However, a sandbox does not mean every script is safe with respect to resources or logic. A script with large loops, operations over huge collections, or execution across too many documents can still cause heavy CPU and memory load.

Principles:

- Use only script sources controlled by the application or operations team.
- Never execute sources submitted by end users.
- Pass data via `params`.
- Bound string lengths, collection sizes, and processed element counts.
- Avoid loops without clear bounds.
- Do not read or write fields outside business scope.
- Limit document counts in `update-by-query` using specific queries.
- Set timeouts and cancellation mechanisms for long tasks as supported by the API.
- Enforce appropriate permissions on script endpoints and indices.

### 4.1. Controlling Script Types and Contexts

Clusters can restrict allowed script types and execution contexts. For instance, an environment might allow only stored scripts or only specific contexts. This configuration acts as a cluster-level defense.

Do not enable every script type and context if the application only needs update scripts. Conversely, do not disable contexts the application depends on without checking first. Inventory script use cases before modifying configuration, test in staging, and inspect logs for compilation or rejected-context errors.

### 4.2. Stored Scripts

If the same script is used in multiple places, you can store it on the cluster and invoke it by ID:

~~~http
PUT /_scripts/increment-stock
Content-Type: application/json

{
  "script": {
    "lang": "painless",
    "source": "ctx._source.stock = (ctx._source.stock == null ? 0 : ctx._source.stock) + params.delta"
  }
}
~~~

Usage:

~~~http
POST /products/_update/42
Content-Type: application/json

{
  "script": {
    "id": "increment-stock",
    "params": {
      "delta": 5
    }
  }
}
~~~

Stored scripts enable centralized source management and avoid sending long sources in every request. They do not reduce per-document execution cost. Updating stored scripts requires versioning, review, and controlled deployment because multiple services may share the same ID.

## 5. Cost of Updates and `update-by-query`

### 5.1. Updating a Single Document

The Update API fetches the current document, executes the script or merges the partial document, and writes a new version of the document. Elasticsearch does not modify a few bytes in-place inside a Lucene segment. Each update creates a new version, and the old document is marked deleted for later cleanup via segment merges.

Thus, a script update incurs read, execution, and write costs. If a document is large, changing a small field still involves processing and rewriting the document under Elasticsearch's storage model.

Example:

~~~http
POST /products/_update/42
Content-Type: application/json

{
  "script": {
    "source": "ctx._source.status = params.status",
    "params": {
      "status": "ACTIVE"
    }
  }
}
~~~

This is a single-document operation. If the application already knows the target value and needs no logic based on current state, a partial document update can be simpler than a script:

~~~http
POST /products/_update/42
Content-Type: application/json

{
  "doc": {
    "status": "ACTIVE"
  }
}
~~~

Choose a script when conditions or calculations based on the current document are required. Choose a partial update when simply assigning known fields.

### 5.2. Update by Query

`_update_by_query` finds documents matching a query and runs a script on each document:

~~~http
POST /products/_update_by_query
Content-Type: application/json

{
  "query": {
    "term": {
      "status": "LEGACY"
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

The task can touch thousands or millions of documents. Costs include searching documents, loading content to process, running the script, and rewriting updated documents. Shard counts, matched document counts, `_source` size, write rate, and refreshes all affect completion time.

Before running in production:

1. Run the query separately to estimate matched document counts.
2. Inspect sample documents and expected script outputs.
3. Estimate volume and write load.
4. Test on staging or a narrow scope.
5. Set rate limits and monitor the task.
6. Prepare handling for version conflicts and per-batch errors.

### 5.3. Throttling, Slicing, and Asynchronous Tasks

Update-by-query supports throttling and task-tracking mechanisms:

- `requests_per_second` caps batch rate per request configuration.
- `wait_for_completion=false` runs asynchronously and returns a task ID.
- `slices` splits work into parallel partitions.
- The Task API enables tracking progress, errors, and status.
- Task cancellation can be used if the task must stop and the API/version supports it.

Increasing slices can boost throughput, yet also raises CPU, heap, and I/O pressure. Do not arbitrarily set maximum parallelism. Tune based on cluster load and user query priority.

Example running asynchronously with throttling:

~~~http
POST /products/_update_by_query?wait_for_completion=false&requests_per_second=200
Content-Type: application/json

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
~~~

The response returns a task ID to track via the Tasks API. A rate of 200 requests per second is only a configuration example; choose values based on actual load and batch throttling semantics.

### 5.4. Version Conflicts and Retries

While `update-by-query` runs, a document might be updated by another application. The task can then encounter a version conflict. Depending on requirements, you can let the task stop on conflicts or continue with remaining documents using `conflicts=proceed`.

~~~http
POST /products/_update_by_query?conflicts=proceed
Content-Type: application/json

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
~~~

`conflicts=proceed` does not resolve conflicts by overwriting newer data. It lets the task continue and reports the conflict count in the response. The application must decide whether to retry conflicted documents, and must avoid blind retries with non-idempotent scripts.

## 6. Idempotency and Repeated Updates

An idempotent script produces the same result when re-run with the same inputs and target state. This property matters because requests can be retried after timeouts, tasks can be re-executed, or batches can be sent multiple times.

Example assigning status:

~~~json
{
  "script": {
    "source": "ctx._source.status = params.status",
    "params": {
      "status": "ARCHIVED"
    }
  }
}
~~~

Running multiple times still sets `status` to `ARCHIVED`. This operation is idempotent on the `status` field.

Conversely, incrementing a counter:

~~~json
{
  "script": {
    "source": "ctx._source.viewCount += params.delta",
    "params": {
      "delta": 1
    }
  }
}
~~~

Running twice increments twice. If the first request was processed by Elasticsearch yet the response was lost, a client retry can increment the counter unexpectedly.

### 6.1. Handling Non-Idempotent Operations

Several options:

- Use a unique event ID and record processed markers to prevent re-application.
- Design updates around target values instead of deltas if business rules allow.
- Use optimistic concurrency to detect updates based on stale versions.
- Route events through a system with deduplication capabilities.
- Record item-level results when using the Bulk API.

There is no universal retry mechanism safe for all scripts. Determine beforehand whether the operation is safe to apply multiple times.

## 7. Type Safety and Missing Fields

Painless works on JSON data converted into runtime types. A field may be absent, `null`, have an unexpected type, or hold an array instead of a scalar.

Scripts must define explicit behavior for each case. Never assume every document has every field or that historical data always conforms to the current schema.

### 7.1. Distinguishing Missing Fields from `null`

In the update context, you can check keys in `_source`:

~~~painless
if (!ctx._source.containsKey('stock')) {
    ctx._source.stock = 0;
} else if (ctx._source.stock == null) {
    ctx._source.stock = 0;
}
~~~

The example above assigns default `0` for both a missing key and a `null` key. If business rules distinguish them, keep two separate branches with distinct outcomes.

Do not access nested fields without checking intermediate objects. For instance, `ctx._source.address.city` can fail if `address` does not exist or is `null`. Check every level before reading.

### 7.2. Wrong-Type Values

Legacy documents might contain:

- `stock` as the string `"10"` instead of a number.
- `price` as `null`.
- `tags` as a string instead of an array.
- `createdAt` in inconsistent formats.

Do not cast arbitrarily and proceed if data violates the contract. Skip the document, flag an error, or stop the task depending on severity.

Example checking a collection before adding an element:

~~~painless
if (!ctx._source.containsKey('tags') || ctx._source.tags == null) {
    ctx._source.tags = [];
}

if (!(ctx._source.tags instanceof List)) {
    throw new IllegalArgumentException('tags must be a list');
}

if (!ctx._source.tags.contains(params.tag)) {
    ctx._source.tags.add(params.tag);
}
~~~

This script initializes the list when missing or `null`, rejects mistyped data, and adds the tag only if absent. Depending on Painless version and collection types, initialization or type-check syntax should be verified on the target cluster.

### 7.3. Empty Collections and Duplicate Elements

For arrays, determine:

- Does a missing array equal an empty array?
- Are `null` elements permitted?
- Are duplicate elements permitted?
- Is there a maximum element count?
- Does element order carry meaning?

A naive append script can grow an array without limit or introduce duplicates on retries. If the data represents a set, check for duplicates before adding. If the collection can grow very large, consider a separate storage model or enforce a cap.

## 8. Numeric Safety and Boundary Values

Arithmetic scripts must explicitly handle:

- Negative values.
- Zero.
- Maximum or minimum values.
- Integer overflow.
- Division by zero.
- Floating-point `NaN` or `Infinity` from invalid data or expressions.
- Type conversions among `integer`, `long`, `double`, and `decimal`.

For example, incrementing `stock` must clarify whether `delta` can be negative:

~~~painless
if (params.delta == null) {
    throw new IllegalArgumentException('delta is required');
}

if (params.delta < 0) {
    throw new IllegalArgumentException('delta must not be negative');
}

def current = ctx._source.stock == null ? 0 : ctx._source.stock;

if (!(current instanceof Number)) {
    throw new IllegalArgumentException('stock must be numeric');
}

ctx._source.stock = current.longValue() + params.delta;
~~~

This illustrates data validation. In production code, validate `delta` in the application layer before sending the script, and verify result bounds to prevent overflow. If `stock` has a business upper bound, ensure `current + delta` does not exceed that limit.

### 8.1. Division by Zero

Example calculating an average price:

~~~painless
if (params.count == null || params.count <= 0) {
    throw new IllegalArgumentException('count must be greater than zero');
}

ctx._source.average = params.total / params.count;
~~~

If `count` can be zero, define the business behavior: reject the update, keep the old value, set `null`, or assign a default value. Do not let a division error act as implicit handling.

### 8.2. Rounding and Currency

Do not perform arbitrary floating-point arithmetic on currency when business logic requires exact precision down to the smallest unit. Define the storage unit—such as storing integers in cents or the smallest currency unit—and enforce rounding rules in the business layer.

With `scaled_float`, Elasticsearch stores values using a scaling factor; the application still must standardize conversion and rounding. Do not add a string-formatted currency value to a number or rely on `double` representation for financial accuracy.

## 9. Controlling Input Size and Complexity

Even when `params` cannot become script code, overly large inputs can still make a script consume excessive CPU or memory.

Bound inputs:

- Maximum string length.
- Maximum list element count.
- Maximum map key count and valid keys.
- Maximum loop iterations.
- Date ranges or price ranges within bounds.
- Number of documents affected by `update-by-query`.

For example, do not iterate over a client-supplied collection without capping its element count. If a client sends hundreds of thousands of tags, the script consumes proportional resources and can stall requests.

For `update-by-query`, the query defines document scope and the script runs on every document in that scope. A missing or wrong filter can affect the entire index. Verify the query and estimate hit counts before executing.

## 10. Avoiding No-op Updates and Unnecessary Rewrites

If a script does not alter the document, you can set `ctx.op = 'noop'` to tell Elasticsearch to skip the update:

~~~http
POST /products/_update/42
Content-Type: application/json

{
  "script": {
    "source": """
      if (ctx._source.status == params.status) {
        ctx.op = 'noop';
      } else {
        ctx._source.status = params.status;
      }
    """,
    "params": {
      "status": "ACTIVE"
    }
  }
}
~~~

No-op is helpful when multiple requests might set the exact same value repeatedly. It avoids creating a new document revision when there is no change to persist.

In `update-by-query`, `ctx.op = 'noop'` can skip documents that do not need changes after the script inspects state. Do not use no-op to cover up overly broad queries or unclear script logic; keep both query conditions and script conditions clear.

## 11. Updating Fields, Removing Fields, and Document Operations

In the update context, a script can modify `_source` or control the operation:

- Assign new fields or update existing fields.
- Remove keys from the `_source` map.
- Set `ctx.op = 'noop'` to skip updating.
- Set `ctx.op = 'delete'` to delete the document when business rules require.

Example removing a legacy field:

~~~json
{
  "script": {
    "source": "ctx._source.remove(params.field)",
    "params": {
      "field": "legacyCode"
    }
  }
}
~~~

If the field name comes from the request, `params.field` must still be checked against an allowlist. Never let clients arbitrarily delete system fields, authorization fields, or business key fields.

Example skipping a document if conditions are not met:

~~~painless
if (ctx._source.status != 'PENDING') {
    ctx.op = 'noop';
} else {
    ctx._source.status = 'PROCESSING';
}
~~~

If deleting documents conditionally, validate strictly:

~~~painless
if (ctx._source.expired == true) {
    ctx.op = 'delete';
}
~~~

Deletion is a high-impact operation. Use it only when business conditions are clearly defined, the query scopes the exact document set, and proper auditing or recovery mechanisms exist.

## 12. Concurrent Updates and Optimistic Concurrency

Two requests may read the same document version and then try to update it. Elasticsearch uses internal versioning to protect update operations. The Update API provides `retry_on_conflict` to retry when a version conflict occurs:

~~~http
POST /products/_update/42?retry_on_conflict=3
Content-Type: application/json

{
  "script": {
    "source": "ctx._source.stock = (ctx._source.stock == null ? 0 : ctx._source.stock) + params.delta",
    "params": {
      "delta": 1
    }
  }
}
~~~

When retrying, Elasticsearch can execute the script on the newer document version. This helps for cumulative increments, though the application must still understand operation semantics and ensure requests are not duplicated by the client.

### 12.1. Using `if_seq_no` and `if_primary_term`

If the application reads a document, computes on the client side, and wants to update only if the document is still the same version it read, use optimistic concurrency with sequence number and primary term:

~~~http
POST /products/_update/42?if_seq_no=17&if_primary_term=3
Content-Type: application/json

{
  "doc": {
    "price": 199.99
  }
}
~~~

If the document changed since being read, Elasticsearch returns a version conflict instead of silently overwriting. The application can re-read, recompute, or return a conflict error to the caller.

`retry_on_conflict` and `if_seq_no`/`if_primary_term` serve different strategies:

- `retry_on_conflict`: lets Elasticsearch retry the update based on a newer version.
- `if_seq_no` and `if_primary_term`: requires updating the exact version observed.

Choose based on business consistency needs; do not enable unconditional retries if the script is unsafe to re-run.

## 13. Scripts in the Bulk API

When updating multiple documents with known IDs, the Bulk API reduces round-trips by sending multiple actions in one request:

~~~http
POST /_bulk
Content-Type: application/x-ndjson

{"update":{"_index":"products","_id":"42"}}
{"script":{"source":"ctx._source.stock += params.delta","params":{"delta":2}}}
{"update":{"_index":"products","_id":"43"}}
{"script":{"source":"ctx._source.stock += params.delta","params":{"delta":3}}}
~~~

Each update action can use the same script source with different `params`. Inspect every item in the bulk response: a bulk request can return HTTP success while individual items still fail.

Bulk does not make updates free. It lowers request overhead, yet every document still needs processing and writing. Choose an appropriate batch size, avoid oversized requests, and maintain per-item retry policies.

## 14. When to Use Scripts and When Not To

| Need | Approach to consider |
|---|---|
| Assign a few known fields | Partial document update |
| Increment counter based on current value | Update script |
| Modify only documents matching a condition | Conditional update script or `update-by-query` |
| Transform data during indexing | Ingest pipeline |
| Compute at query time without persisting | Query/aggregation or context-appropriate script |
| Batch update by known IDs | Bulk update |
| Complex calculations needing business libraries or multiple data sources | Process in the application and write results |
| Major schema transformation | Reindex or controlled migration |

Do not use scripts just because they can do something. Scripts run on the Elasticsearch cluster and consume cluster resources. If logic needs external service calls, other databases, or libraries unsupported by Painless, handle it in the application or an appropriate pipeline.

## 15. Layered Script Testing

A script should be tested across multiple layers:

1. Unit tests for application-tier business logic: validation, value ranges, parameter mapping.
2. Integration tests for scripts against a compatible Elasticsearch version.
3. Performance tests with document counts and `_source` sizes near production scale.
4. Concurrency and retry tests if the operation has concurrent updates.

Mocked requests can verify the application sends the expected source and `params`, but cannot prove the Painless script compiles and executes properly on Elasticsearch. Integration tests are essential for critical scripts.

### 15.1. Edge-Case Matrix

For a stock update script, you can build a matrix:

| Case | Input / state | Expected behavior |
|---|---|---|
| Normal field | `stock=10`, `delta=2` | `stock=12` |
| Missing field | no `stock`, `delta=2` | Initialize per chosen rule |
| Null field | `stock=null` | Initialize or reject per contract |
| Zero delta | `delta=0` | No-op or preserve unchanged |
| Negative delta | `delta=-1` | Reject if business allows increments only |
| Wrong type | `stock="ten"` | Report data error or route to separate handling |
| Maximum value | `stock` near limit, large `delta` | Reject if limit exceeded |
| Missing document | ID absent | Handle not found or upsert as required |
| Repeated request | Same event sent twice | Do not double-increment if dedup is required |
| Two concurrent updates | Two deltas updating simultaneously | Result matches concurrency policy |

This matrix forces the application to define explicit behavior rather than letting types or exceptions decide randomly.

### 15.2. Testing Missing Fields, `null`, and Wrong Types

Prepare separate documents for each state:

~~~json
{"name": "A", "stock": 10}
~~~

~~~json
{"name": "B"}
~~~

~~~json
{"name": "C", "stock": null}
~~~

~~~json
{"name": "D", "stock": "10"}
~~~

Run the script against each document and assert:

- Valid documents are updated accurately.
- Missing/`null` fields follow the defined rule.
- Mistyped fields are rejected or handled intentionally.
- No other documents are altered.

### 15.3. Testing Idempotency

Run the exact same request twice:

- With a status-assignment script, the final value must remain identical.
- With a counter-increment script, the value will increment twice unless deduplication exists.
- With a tag-append script, check whether duplicates are introduced.
- With a field-removal script, the second run should have well-defined behavior.

Do not test only a single happy-path run. Retries are a real-world part of distributed systems.

### 15.4. Testing Concurrency

Send concurrent requests updating the same document and verify:

- Whether version conflicts occur.
- Whether `retry_on_conflict` yields the right result.
- Whether any updates are lost.
- Whether duplicate events mutate data twice.
- How the application handles conflicts and retries.

For counters, distinguish two legitimate concurrent increment requests from one request resent due to a timeout. The two cases carry different business meanings.

## 16. Benchmarking and Monitoring Scripts

To evaluate scripts:

- Measure single-document update latency.
- Measure bulk update throughput and latency.
- Track matched document counts for `update-by-query`.
- Monitor task progress, version conflicts, and failures.
- Monitor CPU, heap, indexing pressure, merges, and refreshes.
- Monitor compilation rates and script cache evictions if dynamic sources are suspected.
- Compare against partial updates or ingest pipelines where applicable.

Test on data with `_source` sizes, shard counts, and concurrency close to production. Benchmarking one small document locally does not reliably predict the cost of `update-by-query` over millions of documents on a cluster.

### 16.1. Testing on a Small Scope First

For large migrations or `update-by-query`, start with a narrow scope:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "status": "LEGACY"
          }
        },
        {
          "term": {
            "tenantId": "tenant-test"
          }
        }
      ]
    }
  }
}
~~~

Estimate matched documents with `_count` or a small-size search before running the script. Once results are verified, expand scope by batch or tenant.

### 16.2. Monitoring `update-by-query` Tasks

When running asynchronously, persist the task ID and check status:

~~~http
GET /_tasks/<task_id>
~~~

The response can include processed document counts, updates, no-ops, version conflicts, and batch errors. Use this information to determine whether the task finished cleanly or needs investigation.

Do not treat an accepted task as a completed task. The orchestrating application must persist state and report final outcomes.

## 17. Complete Example: Controlled Counter Update

The example below illustrates separating service-layer validation from a fixed script source.

~~~java
public void increaseViewCount(String productId, long delta) {
    if (productId == null || productId.isBlank()) {
        throw new IllegalArgumentException("productId is required");
    }

    if (delta <= 0 || delta > 10_000) {
        throw new IllegalArgumentException("delta is outside the allowed range");
    }

    UpdateQuery updateQuery = UpdateQuery.builder(productId)
            .withScript("""
                if (ctx._source.viewCount == null) {
                    ctx._source.viewCount = 0L;
                }
                ctx._source.viewCount += params.delta;
                """)
            .withParams(Map.of("delta", delta))
            .build();

    operations.update(updateQuery, IndexCoordinates.of("products"));
}
~~~

This is an illustrative example; builder methods and `UpdateQuery` types vary by Spring Data Elasticsearch release train. In your project, use the version-matching API or build update requests via the corresponding Elasticsearch Java Client.

Key points to preserve:

- Product ID is checked before building the request.
- `delta` is bounded by business limits.
- Script source is fixed.
- `delta` is passed via `params`.
- Missing fields are initialized according to a defined rule.
- The system needs a retry/deduplication policy if requests can be resent.

If the counter must increment strictly once per event, validating `delta` alone is insufficient. An event ID or deduplication mechanism is required so the same event is not applied multiple times.

## 18. Pre-Production Script Checklist

- [ ] Script source is controlled in code or a reviewed stored script.
- [ ] Inputs are passed via `params`, never concatenated into `source`.
- [ ] Dynamic field names or operations are restricted by an allowlist.
- [ ] Data types, `null`, and missing fields have explicit behavior.
- [ ] Strings, collections, loops, and affected document counts are bounded.
- [ ] Logic handles zero, negative values, overflow, and division by zero.
- [ ] Script idempotency is determined.
- [ ] Version conflict, retry, and deduplication policies exist.
- [ ] `update-by-query` queries have scope verified before running.
- [ ] Throttling, task monitoring, and cancellation procedures exist for long tasks.
- [ ] Integration tests run on a compatible Elasticsearch instance.
- [ ] Benchmarks and monitoring cover CPU, heap, cache, and indexing pressure.
- [ ] Partial updates, bulk, ingest pipelines, or reindexing have been considered.

## 19. Conclusion

Scripts in Elasticsearch have two main costs: compilation and execution. The compilation cache reuses scripts with stable sources, and `params` vary input data without creating new sources. Still, every document must execute the script and may require rewriting the entire document, so `update-by-query` on large datasets must be estimated, throttled, and monitored.

Input safety starts with never executing arbitrary client-submitted scripts, never concatenating data into `source`, validating types and value ranges, and bounding collection sizes and document scope. The Painless sandbox reduces dangerous access, but does not eliminate CPU, memory, or logic bugs.

Testing should cover missing fields, `null`, wrong types, empty collections, zero, negative numbers, arithmetic bounds, duplicate requests, version conflicts, and concurrent updates. For critical tasks, run integration tests against a real compatible Elasticsearch instance and benchmark with production-like data. Use scripts only when logic genuinely depends on document state; partial updates, bulk operations, ingest pipelines, or application-side processing may be simpler choices.
