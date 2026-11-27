# Conflict Retries and Safe Limits for Non-Idempotent Updates

When multiple workers concurrently update an Elasticsearch document, one request may read an old source while another request has already written a newer version. Elasticsearch uses optimistic concurrency control to detect this situation. With the Update API, an application can ask Elasticsearch to automatically retry on version conflict using the `retry_on_conflict` parameter.

However, retrying conflicts is not the same as retrying the entire request from the application. This distinction is especially critical for **non-idempotent** operations, such as incrementing a counter, deducting inventory, or adding points. If a client times out after the server already succeeded and then resends the same command, the operation can be applied twice.

This lesson focuses on bounding retries, distinguishing conflicts from timeouts, using optimistic concurrency control, and designing safe update scripts in Spring Data Elasticsearch.

## 1. Why can an update encounter a conflict?

Elasticsearch stores documents on shards and manages internal versions. When the Update API processes a document, it essentially:

1. Reads the document's current source.
2. Applies a partial document or runs a script against that source.
3. Submits the new version to be written.
4. Checks whether the document was modified during processing.

Suppose two workers concurrently read a document with `stock = 10`:

~~~mermaid
sequenceDiagram
    participant A as Worker A
    participant B as Worker B
    participant ES as Elasticsearch
    A->>ES: Read stock = 10
    B->>ES: Read stock = 10
    A->>ES: Write stock = 12
    ES-->>A: Update succeeded
    B->>ES: Write stock = 13 based on old source
    ES-->>B: Version conflict
~~~

If Elasticsearch accepted B's write based on the old source, A's change could be lost. Optimistic concurrency control prevents that silent overwrite.

A conflict is not necessarily a data error. It indicates the document state changed relative to the version the request was based on. The application must decide whether it can retry on the new version or must return the conflict to business logic for handling.

## 2. Distinguishing retry_on_conflict from client-side retries

There are two distinct retry layers:

| Mechanism | Who executes it | When it retries | What is re-executed |
|---|---|---|---|
| `retry_on_conflict` | Elasticsearch | Update encounters a version conflict during read-modify-write | Elasticsearch reloads the document, re-runs the update/script, and tries writing again |
| Application retry | Application or message consumer | Client receives an error, timeout, or no response | The entire request is resent from the client |

With `retry_on_conflict`, Elasticsearch knows the prior write attempt did not succeed due to a conflict and can re-run the update on the latest source. The conflicted attempt was never committed as a saved document change.

With an application retry after a timeout, the client may not know whether the first request committed. If the server already updated successfully while the response was lost, resending the same counter-increment script can increment the counter a second time.

This is the core point when working with non-idempotent updates: internal conflict retries have different semantics from resending a request after an unknown outcome.

## 3. Idempotent and non-idempotent updates

An operation is idempotent if executing the same operation multiple times yields the same final state as executing it once.

| Operation | Example | Idempotency |
|---|---|---|
| Assign a fixed value | `status = PUBLISHED` | Usually idempotent |
| Set a flag | `active = true` | Usually idempotent |
| Increment a counter | `count += 1` | Non-idempotent |
| Deduct inventory | `stock -= quantity` | Non-idempotent |
| Add element with duplicate check | Add only if not already present | Can be idempotent under the comparison rule |
| Write current timestamp | `updatedAt = now` | Each execution can yield a different result |
| Add reward points | `points += amount` | Non-idempotent |

Example counter-increment script:

~~~painless
ctx._source.viewCount += 1;
~~~

Every successful execution increments by one. If the application sends the same event twice, the result increases by two.

Example status assignment:

~~~painless
ctx._source.status = params.status;
~~~

Resending the same `status` value leaves the same final state. This operation is usually idempotent with respect to source, though metadata such as version or update time may still change.

Do not rely solely on the HTTP method name to conclude an update is idempotent. Evaluate the script logic, parameters, side effects, and how the application retries.

## 4. Using retry_on_conflict with the Update API

The Update API supports the `retry_on_conflict` parameter so Elasticsearch retries on version conflicts.

~~~http
POST /products/_update/P-1001?retry_on_conflict=3
Content-Type: application/json

{
  "script": {
    "lang": "painless",
    "source": "ctx._source.stock += params.quantity",
    "params": {
      "quantity": 2
    }
  }
}
~~~

In this example:

- `P-1001` is the document ID.
- `retry_on_conflict=3` caps the number of retries on conflict.
- The script runs against the document's current source.
- If a write attempt hits a conflict, Elasticsearch reloads and re-runs the script within the retry limit.

Suppose two workers increment stock concurrently. One worker writes first. The other hits a conflict, reloads the new source, and applies its own increment onto the new value. If the retry succeeds, both operations are reflected.

If conflicts exceed the limit, the request still fails. `retry_on_conflict` does not guarantee request success and is not an unbounded wait mechanism.

### Retry limits must be bounded

Choose a small, justified value based on contention level and acceptable response latency. Do not raise retries very high to mask a hot document continuously updated by many workers.

A bounded retry limit helps:

- Cap the work Elasticsearch performs for a single request.
- Keep latency more predictable.
- Prevent a contended request from holding resources too long.
- Surface prolonged contention to the application for deliberate handling.

There is no single retry number fitting every workload. Measure conflict rate, latency, and throughput on real data before tuning.

## 5. Configuring retry_on_conflict in Spring Data Elasticsearch

Spring Data Elasticsearch provides `UpdateQuery` to build update requests. You can set the retry limit with the `withRetryOnConflict(...)` builder method.

Example using a stock-increment script:

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
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive"
            );
        }

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
                .withRetryOnConflict(3)
                .build();

        operations.update(
                updateQuery,
                IndexCoordinates.of("products")
        );
    }
}
~~~

Here:

- `ScriptType.INLINE` specifies that the script source is inline in the request.
- `painless` is the scripting language.
- `params.quantity` receives the increment amount.
- `withRetryOnConflict(3)` bounds internal retries on version conflict.
- `operations.update(...)` executes the update on the target index.

The `Script` class in the example is Spring Data's `org.springframework.data.elasticsearch.core.query.Script`. Avoid mistakenly importing the Script type from the Elasticsearch Java API Client.

Internal retries protect the read-modify-write operation from concurrent conflicts. They do not protect against an event being redelivered to a consumer or a client resending a request after a timeout.

## 6. When should explicit optimistic concurrency control be used?

There are cases where the application wants to enforce document version control itself. For example:

1. Read a document and display it to a user.
2. The user edits it.
3. Meanwhile, someone else updates the document.
4. The application wants to reject overwriting and ask the user to reload the data.

When reading a document, Elasticsearch can return:

- `_seq_no`: the operation's sequence number on the shard.
- `_primary_term`: the shard's primary term.

The update request can pass these two values back as conditions:

~~~http
POST /products/_update/P-1001?if_seq_no=17&if_primary_term=3
Content-Type: application/json

{
  "doc": {
    "name": "Wireless Keyboard Pro"
  }
}
~~~

Elasticsearch accepts the update only if the document still has the exact sequence number and primary term read earlier. If the document has changed, the request returns a version conflict.

### retry_on_conflict and if_seq_no/if_primary_term serve two different policies

- `retry_on_conflict`: asks Elasticsearch to reload and retry applying the update onto the fresh source.
- `if_seq_no` + `if_primary_term`: requires the update to be allowed only if the document still matches the version the application read.

When using explicit OCC conditions, on conflict the application usually needs to reload, compare changes, and decide whether to reapply or report the conflict to the user. Do not combine both policies as though they share the same goal; stale sequence/term conditions cannot become valid merely by repeating the same request.

## 7. Using OCC conditions via UpdateQuery

In Spring Data Elasticsearch versions that support OCC attributes on `UpdateQuery`, you can attach the sequence number and primary term:

~~~java
UpdateQuery updateQuery = UpdateQuery.builder(productId)
        .withDocument(partialDocument)
        .withIfSeqNo(seqNo)
        .withIfPrimaryTerm(primaryTerm)
        .build();

operations.update(
        updateQuery,
        IndexCoordinates.of("products")
);
~~~

`seqNo` and `primaryTerm` must come from the prior document read response, never generated or incremented by the application.

Builder method names and numeric types can depend on the Spring Data Elasticsearch version in use. Check the Javadoc matching your project's dependency. If the current API does not expose the needed properties, use the Elasticsearch Java API Client directly to pass OCC conditions.

With explicit OCC, a conflict is a signal for the application to make a decision. Reload the document, apply merge rules, or return an error for the user to resolve. Do not blindly retry with the same stale sequence number and primary term.

## 8. Can internal retries cause an increment script to apply twice?

This is a critical question for non-idempotent operations.

Suppose the script is:

~~~painless
ctx._source.counter += params.amount;
~~~

Elasticsearch reads `counter`, runs the script, and attempts to write. If that write attempt fails due to a version conflict, that attempt's change was not committed to the document. When `retry_on_conflict` triggers, Elasticsearch reads the fresh source and runs the script again against the fresh source.

Therefore, a single successful Update API call commits that request's change only once. Re-evaluating the script after a conflict does not mean failed attempts were already added to the document.

However, if the client sends a brand-new Update API call after a timeout, the server may have committed the first request. The new request is a separate update and can add the amount again.

Distinguish by example:

~~~text
One request, internal retry:
  Attempt 1: read 10 -> compute 12 -> write conflict (not committed)
  Attempt 2: read 15 -> compute 17 -> write succeeds
  Result: 17

Two requests due to client retry:
  Request 1: 10 -> 12 -> write succeeds
  Client times out, misses response
  Request 2: 12 -> 14 -> write succeeds
  Result: 14
~~~

In the first example, only the successful write is saved. In the second example, both independent requests can commit.

Thus, `retry_on_conflict` resolves writer contention within a single update request. It does not provide an idempotency key for client requests.

## 9. Safe bounds for application retries

Application retries require their own policy. A request timeout does not indicate with certainty whether Elasticsearch received, processed, or committed the operation.

Before retrying, classify the scenario:

| Scenario | Retry immediately? | Handling approach |
|---|---|---|
| HTTP 409 due to OCC | Do not blindly resend same request | Reload and decide to merge or report conflict |
| Update API exhausted `retry_on_conflict` | Can retry with a bound if business rules allow | Reload new state, reapply rules |
| HTTP 429 | Can retry | Backoff, jitter, bounded attempts |
| Connection error before request was sent | Can retry | Keep same idempotency key and payload |
| Timeout after request was sent | Outcome unknown | Reconcile state before reapplying non-idempotent action |
| HTTP 400 due to script/mapping | No | Fix source, params, or mapping |
| HTTP 401/403 | Do not keep retrying | Fix authentication or permissions |
| HTTP 404 document missing | Depends on business rules | Verify ID, use upsert if appropriate |

An application-level retry policy should include:

- Maximum retry count.
- Overall deadline for the entire operation.
- Exponential backoff.
- Jitter so workers do not retry in lockstep.
- Classification of retryable vs. permanent errors.
- Logging/metrics per failure reason.
- Concurrency limits so the cluster is not overloaded.

Example exponential backoff:

~~~java
Duration delay = Duration.ofMillis(100);

for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
        return executeUpdate();
    } catch (RetryableException ex) {
        if (attempt == maxAttempts) {
            throw ex;
        }

        sleepWithJitter(delay);
        delay = delay.multipliedBy(2);
    }
}
~~~

This is pseudocode illustrating the policy. In production applications, use a retry library or scheduler that supports interrupts, deadlines, and cancellation rather than writing thread-blocking loops manually. Do not retry data or authorization errors as if they were transient network failures.

## 10. Do not retry additive operations without idempotency

For example, a consumer receives a point-addition event:

~~~json
{
  "eventId": "evt-184",
  "accountId": "A-1001",
  "points": 50
}
~~~

Script:

~~~painless
ctx._source.points += params.points;
~~~

If the same event is redelivered, 50 points can be added again. A deterministic document ID for the account does not prevent duplicate event processing, because both requests update the same document and both are valid.

You need an operation identifier key, such as `eventId`, and to record applied markers using an appropriate design.

A simple approach for a small set of events is checking a processed ID list inside the same document:

~~~painless
if (ctx._source.processedEventIds == null) {
    ctx._source.processedEventIds = [];
}

if (ctx._source.processedEventIds.contains(params.eventId)) {
    ctx.op = 'noop';
} else {
    ctx._source.points += params.points;
    ctx._source.processedEventIds.add(params.eventId);
}
~~~

This script ensures the same event ID does not add points twice on that document, because the point update and event marker are written in the same single-document update.

However, the `processedEventIds` list will grow forever without a retention policy. Do not keep an unbounded array on a long-lived document.

Options for larger systems:

- Store a separate idempotency record by event ID using a deterministic ID and CREATE semantics.
- Use a monotonic event sequence/version per aggregate if the business model permits.
- Use a ledger or event store as the source of truth and build rebuildable projections.
- Keep a bounded deduplication window if the business contract only requires deduplication over a defined time window.

If the idempotency record and business document are two separate documents, those two writes do not automatically become an atomic transaction. Design processing state, retries, and reconciliation to handle crashes between the two steps. Do not claim a single standalone marker guarantees system-wide exactly-once delivery.

## 11. Using business sequences to block stale events

For state data with an increasing version per product, you can apply only events with a newer sequence:

~~~painless
if (ctx._source.eventVersion == null
        || params.eventVersion > ctx._source.eventVersion) {
    ctx._source.status = params.status;
    ctx._source.eventVersion = params.eventVersion;
} else {
    ctx.op = 'noop';
}
~~~

This prevents older events from overwriting newer state and turns same-version events into no-ops.

Important conditions:

- Versions must be issued by an authoritative source.
- Versions must be ordered within the proper aggregate scope, such as per product ID.
- All writers must follow the same rule.
- If events are additive and can arrive out of order, skipping a lower version can drop a valid event.

Sequence versions work well for snapshot state updates. They do not automatically replace an event ledger when every single event must be applied once.

## 12. Keeping business bounds directly inside the script

For stock-deduction operations, the script should verify conditions before modifying values:

~~~painless
if (params.quantity <= 0) {
    throw new IllegalArgumentException('quantity must be positive');
}

if (ctx._source.stock == null) {
    throw new IllegalArgumentException('stock is missing');
}

if (ctx._source.stock < params.quantity) {
    ctx.op = 'noop';
} else {
    ctx._source.stock -= params.quantity;
}
~~~

The script prevents negative stock by checking and deducting in the same update operation. Do not split this into two requests ("read stock" then "write stock") because another worker can change stock between those two steps.

However, `noop` only indicates the document was not updated. If business logic must distinguish "insufficient stock" from "event already processed," design an explicit response or status. Do not overload a single generic `noop` result for multiple distinct reasons without observability.

For quantities and monetary amounts, validate value ranges in both the application and the script. Do not allow clients to submit negative numbers or out-of-range values merely because the script has checks.

## 13. Separating conflict retries from update_by_query

Update-by-query updates multiple documents matching a query. It has its own conflict policy:

~~~http
POST /products/_update_by_query?conflicts=proceed
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

These two concepts are not the same:

- `retry_on_conflict` belongs to the single-document Update API by ID.
- `conflicts=proceed` in update-by-query allows the process to continue when hitting version conflicts on matched documents.

With `conflicts=proceed`, conflicting documents may remain un-updated during that run. Check `version_conflicts`, `failures`, `updated`, and summary fields in the response.

Update-by-query is not an index-wide transaction. A subset of documents may be updated before the task fails or times out. If retries are needed, determine the remaining documents and ensure the script is safe to re-run.

For a script setting a fixed state, re-running is usually idempotent. For a script incrementing quantities, adding points, or deducting money, re-running across already-updated documents can apply the operation a second time. You need a marker/version guard or a ledger to avoid that.

## 14. Handling bulk updates and partial failures

The Bulk API lets you send multiple update actions in one request. Each item has its own outcome; bulk is not a transaction.

Example scripted update actions:

~~~http
POST /_bulk
Content-Type: application/x-ndjson

{"update":{"_index":"products","_id":"P-1001","retry_on_conflict":3}}
{"script":{"lang":"painless","source":"ctx._source.stock += params.quantity","params":{"quantity":2}}}
{"update":{"_index":"products","_id":"P-1002","retry_on_conflict":3}}
{"script":{"lang":"painless","source":"ctx._source.stock += params.quantity","params":{"quantity":1}}}
~~~

When receiving the response:

1. Check the `errors` field.
2. Iterate through every item and action result.
3. Record succeeded items.
4. Classify version conflicts, mapping errors, missing documents, and transient errors.
5. Retry only eligible items.
6. Preserve the idempotency key/event identity if the operation may be redelivered.

Do not resend the whole bulk request just because one item failed. Items that succeeded could be applied again if the script is not idempotent.

Bulk updates can specify `retry_on_conflict` in each update action's metadata. That limit applies to per-item internal conflicts; it does not resolve timeouts of the whole bulk request or duplicate events at the consumer layer.

## 15. Retry limits and backpressure

When a document is continuously updated by many workers, increasing retries can make things worse. Every internal retry must reload and attempt to write again. Many contending requests can create amplification loops.

An operational policy should place bounds at multiple layers:

| Layer | Recommended bound | Purpose |
|---|---|---|
| Update API | Small, bounded `retry_on_conflict` | Resolve short-lived contention |
| Application retry | Maximum attempt count and deadline | Cap processing duration |
| Worker concurrency | Limit workers updating the same aggregate concurrently | Reduce contention |
| Queue | Backpressure and retry delay | Avoid overwhelming the cluster |
| Bulk | Batch size and concurrent request count | Keep memory/CPU within limits |
| Business logic | Idempotency key or version | Prevent duplicate application |

If a single document becomes a hotspot, consider changing the data model:

- Group updates by key onto a single consumer/partition.
- Use sharded counters and aggregate on read if semantics allow.
- Write separate events and build projections.
- Partition data by aggregate or tenant.
- Reduce updates to the same document via batch aggregation.

Do not raise retry limits to hide a data model with excessive contention.

## 16. Reading update results and observing noop/conflict

After an update, the application should inspect the result rather than ignoring the response.

The Elasticsearch Update API can return details such as:

- `result`: `updated`, `created`, or `noop`.
- `_version`: document version after the operation.
- `_seq_no` and `_primary_term`: document concurrency information.
- `get`: source if the request asked to return the document post-update.

Example `noop` response:

~~~json
{
  "_index": "products",
  "_id": "P-1001",
  "result": "noop",
  "_version": 8,
  "_seq_no": 19,
  "_primary_term": 2
}
~~~

`noop` does not mean an HTTP error. It indicates the script decided not to write a change. The application must distinguish a valid no-op from an operation rejected due to business conditions.

Record metrics for:

- Successful updates.
- `noop` counts.
- Version conflicts.
- Requests exhausting retry limits.
- Application retries.
- Timeouts with unknown outcome.
- Duplicate events detected.
- Latency and average attempt count.

These metrics help detect hot documents, retry storms, or idempotency design bugs.

## 17. Service example with bounded retries and result handling

The example below configures internal retries explicitly and returns the update result to the caller for inspection:

~~~java
import java.util.Map;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Script;
import org.springframework.data.elasticsearch.core.query.ScriptType;
import org.springframework.data.elasticsearch.core.query.UpdateQuery;
import org.springframework.data.elasticsearch.core.query.UpdateResponse;

public class InventoryService {

    private static final int MAX_CONFLICT_RETRIES = 3;

    private final ElasticsearchOperations operations;

    public InventoryService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public UpdateResponse reserve(
            String productId,
            int quantity
    ) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive"
            );
        }

        Script script = new Script(
                ScriptType.INLINE,
                "painless",
                "if (ctx._source.stock == null) { "
                        + "throw new IllegalArgumentException('stock missing'); "
                        + "} "
                        + "if (ctx._source.stock < params.quantity) { "
                        + "ctx.op = 'noop'; "
                        + "} else { "
                        + "ctx._source.stock -= params.quantity; "
                        + "}",
                Map.of("quantity", quantity)
        );

        UpdateQuery updateQuery = UpdateQuery.builder(productId)
                .withScript(script)
                .withRetryOnConflict(MAX_CONFLICT_RETRIES)
                .build();

        return operations.update(
                updateQuery,
                IndexCoordinates.of("products")
        );
    }
}
~~~

This snippet demonstrates a conditional update. Callers must inspect the result to know whether the operation updated or returned `noop`; if your API version represents the response differently, adjust the return type according to your dependency's Javadoc.

Important: this example does not by itself prevent a caller from sending the same reserve request twice. If requests can be retried after timeouts, add an idempotency key and business-level deduplication before deducting inventory.

## 18. Common mistakes

### Setting retry_on_conflict too high

Large retry counts do not eliminate contention. They can raise latency and load. Use small bounds, measure conflict rates, and fix hotspots architecturally.

### Confusing internal retries with client retries

Elasticsearch only knows about conflicts while processing a request. It does not know whether a client resent the same event after a timeout.

### Retrying the raw request after a timeout on an additive operation

If the first request committed, the second request will add again. You need idempotency keys, event deduplication, or state reconciliation.

### Retrying forever with stale OCC tokens

Stale `if_seq_no` and `if_primary_term` values keep mismatching once the document changes. Reload and decide whether to merge or return a conflict.

### Using retry_on_conflict as a substitute for validation

Retries do not fix bad data, broken scripts, wrong mappings, or missing permissions. Retry only transient recoverable errors.

### Treating noop as business success in all cases

`noop` only means the document was not written. Define clearly whether it means duplicate, unmet condition, or unchanged state.

### Retrying an entire bulk batch

Some items may have succeeded. Retrying the whole batch can repeat non-idempotent actions. Classify individual items and retry selectively.

### Treating update_by_query as a transaction

Update-by-query can partially succeed and experience version conflicts. Inspect the response, failures, and actual updated document count.

### Using an unbounded list of event IDs

Storing every event ID forever inside one document bloats `_source` and makes updates increasingly expensive. Choose a ledger, sequence, or bounded deduplication window.

### Assuming a deterministic ID is enough

Stable IDs prevent creating multiple documents for the same key. They do not stop two valid updates from both incrementing a counter or repeating side effects.

## 19. Process for designing safe retries

When implementing concurrent updates:

1. Determine whether the operation is idempotent or non-idempotent.
2. Identify the conflict source: multiple writers, stale read, or OCC tokens.
3. For updates by ID, choose a bounded `retry_on_conflict` for short-lived contention.
4. When using `if_seq_no` and `if_primary_term`, handle conflicts by reloading and deciding to merge.
5. Do not blindly retry mapping, script, validation, or authorization errors.
6. Set retry limits, deadlines, backoff, and jitter at the application layer.
7. For additive/subtractive operations, define idempotency keys or business sequences.
8. Distinguish timeouts with unknown outcomes from known version conflicts.
9. For bulk, inspect per-item results and retry only appropriate items.
10. For update-by-query, check `version_conflicts` and `failures`.
11. Bound concurrency and monitor hot documents.
12. Record metrics for conflicts, noops, retries, and duplicates.
13. Test concurrent writers, post-commit timeouts, and redelivered messages.
14. Verify the final `_source` via GET or search after tests complete.

## References

- [Elasticsearch — Update API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-update.html)
- [Elasticsearch — Optimistic concurrency control](https://www.elastic.co/guide/en/elasticsearch/reference/current/optimistic-concurrency-control.html)
- [Elasticsearch — Update by query API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-update-by-query.html)
- [Elasticsearch — Bulk API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-bulk.html)
- [Elasticsearch — Painless update context](https://www.elastic.co/guide/en/elasticsearch/painless/current/painless-update-context.html)
- [Spring Data Elasticsearch — UpdateQuery API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/query/UpdateQuery.html)
- [Spring Data Elasticsearch — Script API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/query/Script.html)
- [Spring Data Elasticsearch — ElasticsearchOperations API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/ElasticsearchOperations.html)

## Conclusion

`retry_on_conflict` allows Elasticsearch to reload a document and re-run an update after a version conflict within the same request. This limit handles read-modify-write contention; it does not prevent an application from resending an additive/subtractive operation after an ambiguous timeout. In Spring Data Elasticsearch, configure the limit with `UpdateQuery.withRetryOnConflict(...)`; when explicit version control is needed, use `if_seq_no` and `if_primary_term`, reload, and resolve conflicts in the application. For non-idempotent updates, add idempotency keys, event deduplication, or business sequences, while bounding retries, deadlines, and concurrency and inspecting per-item bulk results to avoid applying the same change twice.
