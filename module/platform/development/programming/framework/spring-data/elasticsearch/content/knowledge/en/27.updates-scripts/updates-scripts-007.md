# Delete by Query, Conflicts, and Per-Task Outcomes

Elasticsearch supports deleting multiple documents at once using `_delete_by_query`. The application sends a query to identify the set of documents to delete; Elasticsearch takes a snapshot of the matching data and then executes delete operations in batches. This API is useful for cleaning up expired data, deleting documents by status, purging a tenant's data, or running scheduled maintenance jobs.

Because deletion happens in batches over data that may be concurrently updated, the outcome is not simply "succeeded" or "failed". Version conflicts, shard failures, timeouts, or task cancellation can occur after a portion of documents have already been deleted. You must read the response and task status to know the exact count of deleted documents, conflicts, batches executed, retries, and partial failures.

In Spring Data Elasticsearch, you can invoke a query-based delete via `ElasticsearchOperations.delete(...)` and receive a `ByQueryResponse`. For long-running jobs, consider asynchronous execution at the Elasticsearch layer, tracking task IDs, rate throttling, and designing safe re-runs.

## 1. What Is Delete by Query?

`_delete_by_query` deletes documents matching a Query DSL query. Unlike delete-by-ID, the application does not need to know each document's ID beforehand; it only specifies the search criteria.

Example deleting expired sessions:

```http
POST /sessions/_delete_by_query
Content-Type: application/json

{
  "query": {
    "range": {
      "expiresAt": {
        "lt": "2026-01-01T00:00:00Z"
      }
    }
  }
}
```

Elasticsearch locates documents with `expiresAt` earlier than the threshold and deletes them. The request can process more documents than normal pagination limits because the server splits the work into batches automatically.

### Comparing Deletion Approaches

| Deletion approach | When to use | Characteristics |
|---|---|---|
| Delete by ID | The `_id` of a single document is known | Directly deletes one document; can include routing and conditional versioning |
| Delete by query | Need to delete all documents matching a condition | Server searches and deletes in batches; conflicts and partial results can occur |
| Bulk delete | Application already has a list of IDs to delete | Sends multiple delete actions in one bulk request; must inspect each item result |
| Delete index | Want to remove all data in an index | Index-level operation; affects all documents and mappings in the index |

Delete by query is not an atomic transaction. If one batch succeeds in deleting documents and a subsequent batch hits an error, the already-deleted documents are not automatically restored.

## 2. How Delete by Query Works

At a high level, Elasticsearch performs these steps:

```text
Application sends query
       |
       v
Elasticsearch creates snapshot/search context
       |
       v
Finds matching documents
       |
       v
Splits results into batches
       |
       v
Sends delete action for each batch
       |
       +----> Success: increment deleted
       |
       +----> Version conflict: record conflict
       |
       +----> Other error: record failure
       |
       v
Returns response or completes task
```

Delete by query uses a snapshot of data at the moment the search begins. Documents added after the snapshot is created are not automatically included in that run's deletion set.

When deleting each document, Elasticsearch uses internal version info from the snapshot. If a document was modified after the snapshot was taken, the delete operation can encounter a version conflict. This mechanism prevents a cleanup job operating on stale data from accidentally deleting a newer version of the document.

### No Automatic Rollback

If a task deletes 10,000 documents and then hits an error on the next batch, those 10,000 deleted documents remain deleted. Delete by query does not wrap all batches in a single transaction. When recoverability is required, you must have snapshots/backups or a storage design supporting data restoration.

## 3. Writing Tightly Scoped Queries

Example deleting products archived before a certain date:

```http
POST /products/_delete_by_query
Content-Type: application/json

{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "status": "ARCHIVED"
          }
        },
        {
          "range": {
            "archivedAt": {
              "lt": "2026-01-01T00:00:00Z"
            }
          }
        }
      ]
    }
  }
}
```

`filter` is appropriate for business criteria that do not need relevance scoring. Clearly verify:

- Target index or alias.
- Tenant, document type, or status to delete.
- Cutoff timestamp and timezone.
- Whether fields have the right mapping types.
- Whether the query could accidentally match new or active documents.

### Checking Before Deleting

Before calling delete by query, run the exact same query with `_count` or `_search` to verify scope:

```http
POST /products/_count
Content-Type: application/json

{
  "query": {
    "bool": {
      "filter": [
        { "term": { "status": "ARCHIVED" } },
        {
          "range": {
            "archivedAt": {
              "lt": "2026-01-01T00:00:00Z"
            }
          }
        }
      ]
    }
  }
}
```

If you need to inspect sample documents, use `_search` with a small `size` and fetch only the necessary fields. The count is an estimate as of the check time; data can still change before delete by query begins.

## 4. Synchronous Response and Key Fields

When run synchronously, Elasticsearch returns the result after the operation completes or stops due to an error. An abbreviated response may look like:

```json
{
  "took": 147,
  "timed_out": false,
  "total": 1200,
  "deleted": 1198,
  "batches": 3,
  "version_conflicts": 2,
  "noops": 0,
  "retries": {
    "bulk": 0,
    "search": 1
  },
  "throttled_millis": 0,
  "requests_per_second": -1.0,
  "failures": []
}
```

Field meanings:

| Field | Meaning |
|---|---|
| `took` | Execution time, in milliseconds |
| `timed_out` | Whether the search phase timed out |
| `total` | Number of documents found in the snapshot to process |
| `deleted` | Number of documents successfully deleted |
| `batches` | Number of bulk delete batches sent |
| `version_conflicts` | Number of documents encountering version conflicts |
| `noops` | Number of operations causing no change (typically 0 for delete by query) |
| `retries.bulk` | Number of retries due to errors in the bulk phase |
| `retries.search` | Number of retries due to errors in the search phase |
| `throttled_millis` | Total duration spent throttling |
| `requests_per_second` | Configured rate; `-1` typically indicates unlimited |
| `failures` | List of errors recorded during processing |

Do not just check for HTTP status 200. Read `deleted`, `version_conflicts`, `timed_out`, and `failures` to determine whether the task met business objectives.

### `total` Does Not Equal `deleted`

The two numbers can differ. For example, `total = 1200`, `deleted = 1198`, `version_conflicts = 2` means 1,200 documents belonged to the snapshot set, yet only 1,198 were deleted. The remaining two documents changed after the snapshot or hit conflicts.

## 5. When Do Version Conflicts Arise?

Suppose delete-by-query starts and finds document `p-100` with current version 7. Before the delete action is sent, another process updates the document to version 8.

```text
Time T1: Delete by query creates snapshot
              p-100, version 7

Time T2: Application updates p-100
              p-100, version 8

Time T3: Delete by query sends delete
              based on version 7

Result: version conflict
         document version 8 is not deleted by the stale operation
```

This is a necessary safeguard to avoid mistakenly deleting a recently updated document. A conflict is not necessarily a mapping or query syntax error; it can be a normal consequence of a multi-writer system.

### Common Causes

- A user updates a document while the cleanup job is running.
- Another consumer changes the document's status.
- Another sync job rewrites a document with the same ID.
- Multiple delete/update tasks run concurrently on the same dataset.
- An alias points to an index receiving continuous writes.

## 6. `conflicts=abort` and `conflicts=proceed`

The `conflicts` parameter controls behavior when a version conflict occurs.

### Default: `abort`

```http
POST /products/_delete_by_query?conflicts=abort
```

This is the default behavior. Upon encountering a version conflict, the task halts and returns the corresponding conflict/failure result. Documents already deleted in earlier batches remain un-restored.

### Continue: `proceed`

```http
POST /products/_delete_by_query?conflicts=proceed
```

With `proceed`, Elasticsearch skips documents encountering version conflicts and continues processing the remaining documents. The response records the conflict count in `version_conflicts`.

`proceed` does not mean Elasticsearch automatically retries deleting the conflicted document with the new version. It means skipping that conflict so the task can continue. If business rules still require deleting that document, the application may need to re-check with a fresh query and decide whether to run a follow-up pass.

### Which Policy to Choose?

| Scenario | Potentially suitable policy |
|---|---|
| Cleaning up rarely changing data; want to stop on anomalies | `abort` |
| Large cleanup; tolerate some documents changing mid-run | `proceed` |
| Data with strict audit requirements | Use `abort` or `proceed` with reporting and separate conflict handling |
| Deleting by a status that changes continuously | Design explicit query/version/watermark rules; do not rely solely on `proceed` |

Do not pick `proceed` merely to make the response look successful. Conflict counts must still be monitored and handled per business requirements.

## 7. Distinguishing Version Conflicts from Other Failures

Version conflicts are one specific category of issue. `failures` can contain other errors such as shard unavailable, mapping/operation failures, or bulk item errors.

| Indicator | Interpretation | Action |
|---|---|---|
| `version_conflicts > 0` | Document changed between snapshot and delete | Choose `abort`/`proceed` and evaluate whether a re-run is needed |
| `timed_out: true` | Search phase timed out | Check cluster load, query, scroll/timeout, and shards |
| `failures` non-empty | Specific errors occurred in search or bulk phase | Inspect each failure to identify shard/document and root cause |
| `retries.search > 0` | Search phase had to retry | Monitor shard availability and cluster load |
| `retries.bulk > 0` | Bulk delete phase had to retry | Check indexing pressure, thread pools, and throttling |

If `failures` has entries, store enough details for investigation. Do not merely log a generic message like "delete failed" while discarding the index, shard, status, and returned cause.

## 8. Running Delete by Query Asynchronously

A large deletion task can take a long time. Instead of holding an HTTP connection open until completion, you can use `wait_for_completion=false`:

```http
POST /events/_delete_by_query?wait_for_completion=false&conflicts=proceed
Content-Type: application/json

{
  "query": {
    "range": {
      "expiresAt": {
        "lt": "2026-01-01T00:00:00Z"
      }
    }
  }
}
```

The response returns a task ID instead of waiting for the full result:

```json
{
  "task": "node-1:123456"
}
```

The application saves the task ID and uses the Tasks API to track it. The asynchronous task continues running on Elasticsearch after the initial HTTP request returns.

### Why Use Async?

- Avoids tying up application request threads for long durations.
- Allows periodic progress tracking.
- Allows proactively cancelling the task if needed.
- Allows adjusting the rate while the task is running.
- Integrates cleanly into schedulers or job orchestration.

Async does not make deletion a transaction and does not guarantee task completion if the cluster experiences failures. The application must still manage state, timeouts, retries, and final outcomes.

## 9. Tracking Tasks with the Tasks API

After receiving the task ID, retrieve its status:

```http
GET /_tasks/node-1:123456
```

While the task is incomplete, the response may contain `completed: false` along with task/status information:

```json
{
  "completed": false,
  "task": {
    "node": "node-1",
    "id": 123456,
    "action": "indices:data/write/delete/byquery",
    "status": {
      "total": 100000,
      "deleted": 45000,
      "batches": 45,
      "version_conflicts": 3,
      "noops": 0,
      "retries": {
        "bulk": 0,
        "search": 1
      },
      "requests_per_second": 500.0,
      "throttled_millis": 1200
    }
  }
}
```

When finished, the response has `completed: true` and a `response` object containing the final result:

```json
{
  "completed": true,
  "response": {
    "took": 12000,
    "timed_out": false,
    "total": 100000,
    "deleted": 99997,
    "batches": 100,
    "version_conflicts": 3,
    "failures": []
  }
}
```

Status fields while running reflect point-in-time progress at poll time, not the final outcome. Only treat the task as finished when `completed` is `true` and you have read the corresponding `response` or `error`.

### Reasonable Polling

Do not poll the Tasks API every few milliseconds. Poll at an interval suited to the job's duration, such as every few seconds or longer, and back off for long-running tasks. When running multiple tasks, avoid synchronizing all clients to poll at the exact same instant.

## 10. Cancelling a Running Task

You can issue a cancellation request:

```http
POST /_tasks/node-1:123456/_cancel
```

Cancelling a task requests stopping the work; it is not a rollback. Documents deleted before the task stops remain deleted. The task may take some time to halt at an appropriate processing boundary.

After sending cancel, continue checking the Tasks API to confirm the final status. Do not mark the job as "rolled back" or "no data deleted" merely because the cancel endpoint returned success.

### When to Cancel?

- You discover the query scope is broader than intended.
- Cluster load exceeds operational thresholds.
- The task is deleting the wrong tenant or data type.
- You need to halt for incident response or maintenance.

If a mis-scoped query deleted a portion of data, you need a restoration process from backups or source data; cancel cannot restore documents.

## 11. Throttling with `requests_per_second`

Delete by query can place heavy load on search and bulk indexing thread pools. The `requests_per_second` parameter limits processing speed.

Example limiting to roughly 500 processing unit requests per second under the API's throttling mechanism:

```http
POST /events/_delete_by_query?requests_per_second=500
Content-Type: application/json

{
  "query": {
    "range": {
      "expiresAt": {
        "lt": "2026-01-01T00:00:00Z"
      }
    }
  }
}
```

A value of `-1` indicates no throttling. This rate is enforced via pauses between batches; it is not an exact guarantee of documents deleted per second across all workloads.

### Adjusting Rate While a Task Is Running

For async tasks, you can re-throttle:

```http
POST /_delete_by_query/node-1:123456/_rethrottle?requests_per_second=100
```

You can slow down when the cluster is under load or speed back up once the system stabilizes. Re-throttling does not alter the query and does not reprocess prior conflicts.

## 12. Splitting Tasks with `slices`

`slices` lets Elasticsearch split a delete-by-query job into sub-tasks running in parallel across different portions of data.

Example:

```http
POST /events/_delete_by_query?slices=auto&wait_for_completion=false
Content-Type: application/json

{
  "query": {
    "range": {
      "expiresAt": {
        "lt": "2026-01-01T00:00:00Z"
      }
    }
  }
}
```

`slices=auto` lets Elasticsearch pick the slice count based on shards. You can specify an integer if you have measured the workload.

### Benefits and Trade-offs

- Increases parallelism and can shorten total execution time.
- Each slice can create its own search context and batches.
- More slices increase concurrent resource consumption.
- Total sub-tasks can raise search/bulk load and heap pressure.
- Overall counts and `max_docs` may not divide evenly across slices.

Do not increase slices blindly just to make a task faster. Monitor CPU, heap, indexing pressure, search thread pools, shard count, and batch duration.

## 13. Key Operational Parameters

Delete by query has many control parameters. Common ones include:

| Parameter | Purpose | Notes |
|---|---|---|
| `conflicts` | Choose `abort` or `proceed` | `proceed` skips version conflicts without retrying those documents |
| `wait_for_completion` | Run synchronously or asynchronously | Async returns a task ID for polling |
| `requests_per_second` | Limit batch rate | `-1` typically means unlimited |
| `slices` | Split task into parallel parts | Increases resource load if too large |
| `scroll_size` | Number of documents per search batch | Large batches increase payload and memory usage |
| `scroll` | Duration to keep internal scroll context alive | Must be long enough between batches |
| `max_docs` | Limit number of documents processed | Not a random or top-N selector without appropriate sort/logic |
| `refresh` | Refresh shards after deletion | Has cost; enable only when search must see changes immediately |
| `routing` | Restrict operation by routing value | Use only when the proper routing is known |
| `timeout` | Wait timeout for related operations | Does not replace async handling for long tasks |

### `max_docs`

Example capping at 10,000 documents:

```http
POST /logs/_delete_by_query?max_docs=10000
```

`max_docs` limits the number of processed documents, not a mechanism guaranteeing selection of the exact 10,000 newest or oldest documents. If deletion must follow a business order, define the query and selection criteria upfront; delete by query should not be used like an arbitrarily sorted paginated query.

When combining `max_docs` with slicing, the actual document count may not strictly equal the limit due to parallel distribution and execution. If exact limits are required, select IDs/datasets separately and delete by list or controlled partitions.

### `refresh`

`refresh=true` requests refreshing the involved shards after the operation completes so changes are immediately visible to search. Refreshing incurs cost and is unnecessary if the application can wait for the normal refresh interval.

## 14. Routing and Shard Scope

If the routing value is known, you can limit delete by query to the relevant shard:

```http
POST /tenant-data/_delete_by_query?routing=tenant-42
Content-Type: application/json

{
  "query": {
    "term": {
      "status": "EXPIRED"
    }
  }
}
```

Routing only limits which shard is queried. It does not replace a tenant condition in the Query DSL. For multi-tenant data, keep the `tenantId` filter in the query to express business scope explicitly, while also using routing if your index architecture supports it.

Especially with parent-child mappings, routing must match how documents were indexed. Query-based deletion must target the exact index, query, and routing to avoid missing documents or affecting unintended scope.

## 15. Per-Task Outcomes in the Application System

If the application runs many delete-by-query jobs, do not store only a single `success = true/false` flag. Each task should have its own status record to track its lifecycle and results.

A status model might include:

```text
CREATED
   |
   v
SUBMITTED
   |
   v
RUNNING ---------> CANCELLING
   |                   |
   v                   v
COMPLETED           CANCELLED
   |
   +----> COMPLETED_WITH_CONFLICTS
   |
   +----> COMPLETED_WITH_FAILURES

RUNNING / SUBMITTED ----> FAILED
```

These are application-defined business statuses, not official Elasticsearch Tasks API status names.

### Information to Store per Job

| Field | Purpose |
|---|---|
| `jobId` | Stable business ID of the job |
| `taskId` | ID returned by Elasticsearch when run asynchronously |
| `indexOrAlias` | Target index/alias |
| `queryDescription` or query hash | Identifies the deletion criteria submitted |
| `submittedAt`, `startedAt`, `finishedAt` | Timing tracking |
| `status` | Business status of the job |
| `total` | Number of documents found |
| `deleted` | Number of documents deleted |
| `versionConflicts` | Number of conflicts |
| `batches` | Number of batches executed |
| `retries` | Search/bulk retry counts |
| `timedOut` | Whether a timeout occurred |
| `failures` | Error summary and references for investigation |
| `cancelRequested` | Whether cancellation was requested |

You do not necessarily need to store the entire raw response if it can be large or contain sensitive data. Persist fields needed for auditing and controlled log/trace references.

## 16. Evaluating Task Outcomes

A task should only be considered satisfactorily completed after evaluating all metrics, not merely because the task stopped.

Examples:

| Result | Interpretation |
|---|---|
| `completed=true`, `deleted=total`, `failures=[]`, `timed_out=false` | Task deleted the entire set of documents found in the snapshot |
| `deleted < total`, `version_conflicts > 0`, no other failures | Some documents changed and were skipped, or task halted per conflict policy |
| `failures` non-empty | Errors require investigation; do not mark as fully successful |
| Task cancelled | A portion may already be deleted; read the final result and handle the remainder |
| Task no longer found | Task may have completed and its result expired, the task/node was lost, or ID is wrong; reconcile with job records and logs |

### `completed` Does Not Mean Fully Successful

The Tasks API may report the task as completed while the response still contains version conflicts or failures. The `completed` flag describes task lifecycle, whereas business success depends on the response contents.

## 17. Re-Running After Conflicts or Failures

If a task finishes with version conflicts, you may consider re-running the query to process documents that still match. However, before re-running, check:

- Do the conflicted documents still satisfy the deletion criteria?
- Were they updated to a state that should be retained?
- Could re-running the query mistakenly delete newer versions?
- Were new documents added during execution?
- Is the job safe to run repeatedly?

For example, if the query deletes sessions with `expiresAt < now`, a session extended during the job may hit a conflict. Re-running the same query afterward will not delete the session if `expiresAt` was updated into the future. That is desirable behavior.

Conversely, if the query relies only on a `cleanup=true` flag and another process updated the content while keeping that flag, re-running could still delete the document. Thus, retries must be driven by business rules, not simply by conflict counts.

### Do Not Blindly Retry the Entire Task

Retrying a broad query can delete newly created documents that arrived after the first run if they also match the criteria. If the requirement is to process only a dataset as of a point in time, anchor the scope with a watermark or partition and use appropriate snapshots/backups.

## 18. Delete by Query in Spring Data Elasticsearch

Spring Data Elasticsearch provides query-based deletion via `ElasticsearchOperations`. In supporting APIs, the method returns `ByQueryResponse`, containing delete-by-query result details.

Example deleting expired events:

```java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.query.ByQueryResponse;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class EventCleanupService {

    private final ElasticsearchOperations operations;

    public EventCleanupService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public ByQueryResponse deleteExpiredEvents(String cutoff) {
        Query query = NativeQuery.builder()
            .withQuery(q -> q.range(r -> r
                .field("expiresAt")
                .lt(co.elastic.clients.json.JsonData.of(cutoff))
            ))
            .build();

        return operations.delete(query, EventDocument.class);
    }
}
```

`EventDocument.class` helps Spring Data resolve the index mapping. If you need to target a specific alias/index, use an overload accepting `IndexCoordinates` if supported by your Spring Data version.

### Reading `ByQueryResponse`

```java
ByQueryResponse response = deleteExpiredEvents(cutoff);

long total = response.getTotal();
long deleted = response.getDeleted();
long conflicts = response.getVersionConflicts();
long batches = response.getBatches();
boolean timedOut = response.isTimedOut();
var failures = response.getFailures();
```

Accessors and packages of `ByQueryResponse` can vary across Spring Data Elasticsearch versions. Consult the Javadoc of your project's dependency. Crucially, the application must check `deleted`, conflicts, timeouts, and `failures` before declaring the job successful.

### Notes on Synchronous vs. Asynchronous Execution

`ElasticsearchOperations.delete(query, clazz)` is typically an abstraction for delete-by-query that returns results once the call completes according to your version's API. If you need control over `wait_for_completion=false`, task ID tracking, re-throttling, or cancellation, check your client/API capabilities; you may need to use the Elasticsearch Java API Client directly instead of the high-level abstraction.

## 19. Service Example Inspecting Results

Do not return a success response simply because no exception was thrown. Map the result into an explicit business model:

```java
public record CleanupResult(
        long total,
        long deleted,
        long versionConflicts,
        long batches,
        boolean timedOut,
        boolean hasFailures) {

    public boolean completedWithoutIssues() {
        return !timedOut
            && !hasFailures
            && versionConflicts == 0
            && deleted == total;
    }
}
```

Mapping from `ByQueryResponse`:

```java
public CleanupResult toResult(ByQueryResponse response) {
    return new CleanupResult(
        response.getTotal(),
        response.getDeleted(),
        response.getVersionConflicts(),
        response.getBatches(),
        response.isTimedOut(),
        !response.getFailures().isEmpty()
    );
}
```

`completedWithoutIssues()` is just an example rule. For jobs using `conflicts=proceed`, conflicts may be acceptable in certain cases, though you should still persist the conflict count and decide whether reprocessing is needed.

## 20. Separating Query Scope and Deletion Policy from the Service

For critical deletion tasks, build queries from explicit business criteria instead of concatenating JSON strings or accepting raw Query DSL from clients.

Example internal DTO:

```java
import java.time.Instant;

public record ExpiredEventCriteria(
        String tenantId,
        Instant expiresBefore) {
}
```

Building the query:

```java
public Query buildDeleteQuery(ExpiredEventCriteria criteria) {
    return NativeQuery.builder()
        .withQuery(q -> q.bool(b -> b
            .filter(f -> f.term(t -> t
                .field("tenantId")
                .value(criteria.tenantId())
            ))
            .filter(f -> f.range(r -> r
                .field("expiresAt")
                .lt(co.elastic.clients.json.JsonData.of(criteria.expiresBefore().toString()))
            ))
        ))
        .build();
}
```

Before running, validate that `tenantId` is non-empty and `expiresBefore` is valid. If a job is only authorized to delete data for a single tenant, never allow callers to omit the tenant filter.

## 21. Handling Async Execution at the Application Layer

A job runner can save a job record before submitting, then update the task ID and poll results:

```text
Scheduler / Internal API
        |
        v
Create cleanup job record
        |
        v
Submit delete-by-query (async)
        |
        v
Persist Elasticsearch task ID
        |
        v
Worker polls Tasks API
        |
        +----> completed=false: update progress, poll later
        |
        +----> completed=true: read response/error
                         |
                         v
                 Evaluate conflicts/failures
                         |
                         v
                 Update business status
```

Key design points:

- Do not submit the same job multiple times just because the client missed the first response.
- Use an idempotent job ID at the application layer.
- If submission times out, check whether the task was created before resubmitting.
- Persist the task ID immediately upon receipt.
- Poll with backoff and a time limit.
- Handle lost tasks or node restarts.
- When cancelling, continue waiting for final status and record the deleted document count.

## 22. Controlling Concurrent Tasks

Multiple large delete-by-query tasks running simultaneously can strain the cluster. Enforce concurrency limits per index or workload type.

Example policies:

- Run only one large cleanup on the same index at a time.
- Smaller jobs can run in parallel if resources permit.
- Production tasks enforce a `requests_per_second` limit.
- Jobs configure `slices` according to shard count and cluster capacity.
- Use a queue to prevent schedulers from launching overlapping runs of the same schedule.
- Provide a cancel/disable switch when the cluster exceeds load thresholds.

Do not use a single fixed concurrency number for all clusters. Measure search/bulk thread pools, CPU, heap, disk I/O, indexing pressure, and primary application latency.

## 23. Refresh and Visibility of Deleted Documents

Delete by query does not necessarily remove documents from search immediately if shards have not refreshed. `refresh=true` requests a refresh after the operation completes.

Example:

```http
POST /sessions/_delete_by_query?refresh=true
```

Refresh affects visibility of changes in search, not backup or rollback guarantees. If the application can tolerate waiting for the normal refresh interval, there is no need to enable refresh for every cleanup.

## 24. Handling Aliases and Rollover Indices

If delete by query runs on an alias pointing to multiple indices, check whether the alias has a write index or custom filter/routing. Delete by query can affect all indices represented by the alias within the request's scope.

For time-series data or rollover indices:

- If an old index has reached end-of-life, deleting the whole index via lifecycle policy or index deletion can be far more efficient than deleting individual documents.
- If only part of the data within an index needs deletion, delete by query can be appropriate.
- If an alias points to multiple index generations, verify the alias scope before running.
- If a job must delete per tenant, always include tenant filters and appropriate routing.

Do not run cleanups against broad aliases without verifying the exact list of indices the alias resolves to.

## 25. Guarding Dangerous Deletion Operations

Delete by query can remove large amounts of data. Useful operational safeguards:

1. Run `_count` first and record the expected document count.
2. Require mandatory filters such as tenant, status, or time range.
3. Confirm index/alias and environment before submitting.
4. Cap `max_docs` if business rules permit a quantity limit.
5. Run asynchronously to obtain a task ID and monitoring/cancellation capability.
6. Apply throttling and concurrency limits.
7. Persist per-task outcomes for auditability.
8. Ensure snapshots/backups exist if data must be recoverable.

Do not accept arbitrary Query DSL directly from a public API and forward it straight to `_delete_by_query`. Enforce index, mandatory filters, and caller permissions in the application layer.

## 26. Testing Delete by Query

Integration tests should run against a compatible Elasticsearch instance with controlled fixture data. Mocking `ElasticsearchOperations` can verify the service calls the right method, but cannot test Query DSL behavior, version conflicts, or actual deletion results.

Cases to test:

- Only documents matching the query are deleted.
- Non-matching documents remain intact.
- Queries with a tenant filter do not delete other tenants' data.
- Date ranges handle boundaries and timezones accurately.
- `deleted` matches the expected count when there are no concurrent updates.
- Version conflicts are handled per `abort` or `proceed`.
- Responses with failures are reflected in the job status.
- Async tasks are polled until completion.
- Cancellation is not interpreted as rollback.
- Throttling and slicing do not corrupt data scope.
- Re-running a job causes no unintended side effects.

To reproduce conflicts, an integration test can concurrently update a document already in the snapshot while delete-by-query is running. Because timing can be hard to control, such tests need a sufficiently large dataset or proper test synchronization; do not rely on a short `sleep` to assert a conflict will occur.

## 27. Common Mistakes

### Checking Only HTTP Status

HTTP success does not mean all documents were deleted. Inspect `deleted`, `version_conflicts`, `timed_out`, and `failures`.

### Assuming `conflicts=proceed` Retries Conflicted Documents

`proceed` skips conflicted documents and continues. If reprocessing is needed, the application must evaluate and run an appropriate follow-up query.

### Assuming Cancel Undoes Data Deletion

Cancel only requests stopping the task. Already-deleted documents remain lost; backups/restores are required to recover them.

### Retrying the Entire Query Without Checking Scope

Re-running a query may match newly arrived or newly modified documents. Use watermarks/partitions and explicit business rules.

### Ignoring `failures`

A task can complete while still having failures. Store error details and determine whether to retry or raise a business error.

### Setting Batch Size/Slices Too High

More parallelism is not always faster. Monitor heap, CPU, search/bulk thread pools, and indexing pressure.

### Ignoring Routing

For indices using custom routing or parent-child mappings, missing routing can broaden scans or miss the expected shards. Verify routing against mappings and actual data.

### Deleting Across an Overly Broad Alias

An alias may point to multiple indices. Check the alias and scope before running.

## 28. Cleanup Job Implementation Workflow

A cleanup job can be designed in this sequence:

1. Accept validated business criteria, never arbitrary queries from clients.
2. Identify index/alias, tenant, and time range.
3. Run `_count` or a sample search to verify scope.
4. Build the query with `NativeQuery` or the Query API.
5. Choose `conflicts=abort` or `proceed` per requirements.
6. Choose synchronous or asynchronous execution; for long tasks, prefer async and persist the task ID.
7. Choose batch size, keep-alive, `requests_per_second`, and `slices` based on cluster load.
8. Monitor the task via the Tasks API.
9. Upon completion, inspect the full response and classify conflicts/failures/timeouts.
10. Persist the outcome in the job record and audit log.
11. If retries are needed, re-determine the document set and ensure re-runs are safe.
12. Mark the job successful only when results satisfy business criteria.

## 29. Conclusion

Delete by query deletes documents matching a Query DSL query by taking a snapshot, finding matching documents, and sending deletes in batches. Because data can be updated concurrently, version conflicts must be handled deliberately. `conflicts=abort` stops on conflicts; `conflicts=proceed` skips conflicted documents and continues without retrying them. Responses must be evaluated using `total`, `deleted`, `batches`, `version_conflicts`, `timed_out`, `retries`, and `failures`.

For long jobs, use `wait_for_completion=false` to get a task ID, track it via the Tasks API, adjust rate with re-throttle, and stop it with cancel when necessary. Cancelling a task does not roll back already-deleted documents. In Spring Data Elasticsearch, `ElasticsearchOperations.delete(query, entityClass)` provides the abstraction and `ByQueryResponse` for results; if granular async task management is needed, using the Elasticsearch Java API Client directly may be required. Narrow queries, checking counts beforehand, throttling load, storing per-job outcomes, and making retries safe are key pillars of a reliable deletion workflow.

## References

- [Elasticsearch – Delete by query API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-delete-by-query)
- [Elasticsearch – Tasks API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-tasks-get)
- [Elasticsearch – Cancel tasks API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-tasks-cancel)
- [Elasticsearch – Rethrottle delete by query](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-delete-by-query-rethrottle)
- [Elasticsearch – Query DSL](https://www.elastic.co/docs/reference/query-languages/query-dsl)
- [Spring Data Elasticsearch – Operations and NativeQuery](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch – `ByQueryResponse` API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/query/ByQueryResponse.html)
