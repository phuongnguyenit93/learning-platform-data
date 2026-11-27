# Backoff, Jitter, and Limiting Concurrent Requests

When bulk-ingesting data into Elasticsearch, an application can send multiple bulk requests concurrently to increase throughput. If the submission rate exceeds the cluster's processing capacity, write queues can fill up and Elasticsearch will reject some or all requests. Clients that keep retrying immediately generate additional load, making it even harder for the cluster to recover.

Three mechanisms must work together to regulate the ingestion flow:

- **Backoff**: increasing the wait time between retries to relieve pressure on the cluster.
- **Jitter**: adding randomness to the wait time so multiple clients do not retry in lockstep.
- **Concurrency limit**: capping the number of bulk requests running simultaneously to control the amount of work entering the system.

Using backoff alone without a concurrency limit can still accumulate too many in-flight requests. Limiting concurrency while retrying immediately can still create a continuous failure loop. A stable pipeline requires a retry policy, load limits, batch sizing, timeouts, and per-item error handling.

## 1. Why Does Bulk Ingestion Need Load Control?

### 1.1. Bulk Requests Reduce Overhead but Can Create Large Bursts

The Bulk API lets you send multiple index, create, update, or delete operations in a single request. Compared to sending individual documents one by one, bulk reduces round trips and uses network connections more efficiently.

Example:

~~~http
POST /_bulk
Content-Type: application/x-ndjson

{"index":{"_index":"products","_id":"P1001"}}
{"name":"Wireless Keyboard","price":49.9}
{"index":{"_index":"products","_id":"P1002"}}
{"name":"USB Hub","price":19.9}
~~~

However, bulk does not eliminate indexing cost. Elasticsearch still must analyze documents, update Lucene segments, write to the translog, replicate to replicas, and perform shard-level work.

A single request with too many documents or many concurrent bulk requests can increase:

- CPU and disk I/O.
- Heap usage and garbage collection pressure.
- Write thread pool queue depth.
- Merge activity and segment count.
- Network traffic between the coordinating node, primary shards, and replicas.
- Response times and request rejection rates.

### 1.2. When the Cluster Is Overloaded

When write-related thread pools or queues run out of space, Elasticsearch can return rejection errors. With bulk requests, you may receive a successful HTTP status at the request level while some items inside fail. In other cases, the entire request is rejected.

Common symptoms:

- HTTP 429.
- `es_rejected_execution_exception`.
- Bulk response with `errors: true`.
- Some items returning status 429 while other items succeeded.
- Request timeouts or gateway timeouts when the cluster is under heavy load.

Do not treat every error in a bulk response as transient. Mapping errors, wrong data types, or invalid documents will not resolve themselves on retry.

### 1.3. Immediate Retries Create a Retry Storm

Suppose 20 workers are sending bulk requests concurrently. The cluster begins returning 429. If all 20 workers retry immediately, they send another wave of requests at almost the exact same moment.

~~~mermaid
sequenceDiagram
    participant C as Bulk clients
    participant E as Elasticsearch
    C->>E: Burst of concurrent bulk requests
    E-->>C: 429 / rejected
    C->>E: Immediate retries
    E-->>C: More rejections
    C->>E: Repeated retries
    E-->>C: Queue remains overloaded
~~~

A retry storm increases the request rate right when the cluster lacks capacity to process it. Backoff and jitter spread out retry timing; a concurrency limit prevents the application from pushing too many new requests into the cluster.

## 2. What Is Backoff?

### 2.1. Waiting Before Retrying

Backoff is the policy of waiting before retrying a transient failure. Instead of resending immediately, the client pauses for a duration and tries again.

Fixed-delay schedule example:

| Retry Attempt | Wait Time |
|---:|---:|
| 1 | 1 second |
| 2 | 1 second |
| 3 | 1 second |
| 4 | 1 second |

Fixed backoff is simple, yet it does not widen the gap when failures persist. Against an overloaded system, retrying every second can still sustain continuous pressure.

### 2.2. Exponential Backoff

Exponential backoff grows the wait duration exponentially:

\[
d_n = \min(d_{max}, d_0 \times 2^{n-1})
\]

Where:

- \(d_0\): initial wait time.
- \(n\): retry attempt number, starting at 1.
- \(d_{max}\): maximum wait cap.
- \(d_n\): wait time before the \(n\)-th retry.

Example with a 200 ms initial delay and a 5-second maximum delay:

| Retry Attempt | Delay Before Cap |
|---:|---:|
| 1 | 200 ms |
| 2 | 400 ms |
| 3 | 800 ms |
| 4 | 1,600 ms |
| 5 | 3,200 ms |
| 6 | 6,400 ms |
| 7 | 12,800 ms |

Once the 5-second cap applies, subsequent retries wait no longer than 5 seconds.

Exponential backoff lowers retry frequency during prolonged errors. However, if all clients start at the same time and follow the same formula, they can still wake up and retry in near-lockstep.

### 2.3. Capping the Number of Retries

Do not retry indefinitely. Every operation needs an explicit limit, such as at most 5 retries after the initial send.

Distinguish:

- `attempt`: total number of sends, including the initial one.
- `retry`: number of resends after a failure.

If configuring `maxRetries = 5`, make clear whether that means 5 retries or 5 total attempts. Confusing the two can stretch processing times beyond expectations.

### 2.4. Capping Total Elapsed Time

Retry count is not the only limit. An operation should also have a deadline or maximum elapsed time.

Example:

- Single HTTP request timeout: 10 seconds.
- Maximum retries: 5.
- Total operation time: no more than 45 seconds.

Once the deadline expires, stop retrying even if attempts remain. This prevents an old batch from monopolizing workers when the pipeline needs to move on to newer data.

## 3. Jitter: Spreading Out Retry Timing

### 3.1. Why Exponential Backoff Alone Is Not Enough

Suppose 100 clients all hit 429 at time t = 0. Every client waits 1, 2, 4, and then 8 seconds. Because their start times and delays match, the clients generate synchronized spikes of requests at those exact timestamps.

This is synchronized retries. Jitter injects randomness into delays so clients spread out their retry times.

### 3.2. Full Jitter

Full jitter picks a random delay between 0 and the exponential cap:

\[
d_n \sim Uniform(0, \min(d_{max}, d_0 \times 2^{n-1}))
\]

For example, if the cap on the third retry is 800 ms, the actual delay can be any value from 0 to 800 ms.

Advantages:

- Reduces the likelihood of multiple clients retrying at the exact same instant.
- Lowers average load inside a retry window.
- Simple formula, easy to implement.

The downside is that it can pick a very short delay, even near 0. If you want to guarantee a minimum pause, consider equal jitter or a dedicated minimum floor.

### 3.3. Equal Jitter

Equal jitter keeps half of the exponential cap as a base wait and randomizes the other half:

\[
base_n = \min(d_{max}, d_0 \times 2^{n-1})
\]

\[
d_n = \frac{base_n}{2} + Uniform(0, \frac{base_n}{2})
\]

With an 800 ms cap, the delay falls between 400 and 800 ms.

Equal jitter avoids delays near 0 while still dispersing clients.

### 3.4. Decorrelated Jitter

Another option is decorrelated jitter, where the new delay depends on the previous delay:

\[
d_n = \min(d_{max}, Uniform(d_0, 3 \times d_{n-1}))
\]

This creates a well-dispersed delay sequence without strictly doubling on every retry. It requires storing the previous delay per operation or retry sequence.

### 3.5. Comparing Strategies

| Strategy | Conceptual Formula | Characteristics |
|---|---|---|
| Fixed | Always a constant interval | Simple, can synchronize clients |
| Exponential | Doubles per retry attempt | Widens gap, yet stays synchronized if started together |
| Full jitter | Random from 0 to exponential cap | Strong dispersion, can produce very short delays |
| Equal jitter | Half cap plus random portion | Provides a natural minimum wait |
| Decorrelated jitter | Based on previous delay | Well dispersed, requires slightly more state |

No single strategy fits every system. Full jitter is often a clean default for distributed retries; equal jitter is useful when you want to avoid overly short delays.

### 3.6. Honoring `Retry-After` When Provided by the Server

Some proxy or service layers return a `Retry-After` header. When present, clients should treat it as a scheduling signal for retries.

Distinguish:

- `Retry-After` as a number of seconds.
- `Retry-After` as an HTTP-date.
- Headers originating from a gateway/proxy rather than Elasticsearch directly.

Never retry earlier than the time requested by the server. You can add small positive jitter after that point so clients do not all fire at the exact cutoff, without violating the minimum delay.

If the requested wait exceeds the operation deadline, move the batch to a durable queue or mark it for later retry; do not block a worker thread indefinitely.

## 4. Classifying Errors Before Retrying

### 4.1. Retry Only Potentially Transient Errors

A solid retry policy separates transient errors from permanent errors.

| Error Category | Example | Handling Approach |
|---|---|---|
| Temporary overload/rejection | 429, `es_rejected_execution_exception` | Backoff + jitter, reduce concurrency |
| Temporary infrastructure error | Certain 502, 503, 504, connection reset | Bounded retry if operation still within deadline |
| Timeout | Request timeout or missing response | Retry only when semantics and idempotency allow |
| Mapping/validation | 400, mapper/parsing exception | Do not retry; fix data or mapping |
| Authorization | 401, 403 | Do not auto-retry; fix credentials/permissions |
| Version conflict | 409 or item version conflict | Handle per optimistic concurrency policy |
| Missing index | 404 or resource error | Fix configuration/index lifecycle; do not retry blindly |

HTTP status is only an initial signal. With the Bulk API, read each item's error type and status. An HTTP 200 response does not mean every operation in the bulk request succeeded.

### 4.2. Distinguishing Request-Level from Item-Level Errors

A bulk response contains an `errors` field and an `items` list. Each item holds the outcome of its corresponding operation.

Conceptual example:

~~~json
{
  "errors": true,
  "items": [
    {
      "index": {
        "_id": "P1001",
        "status": 201
      }
    },
    {
      "index": {
        "_id": "P1002",
        "status": 429,
        "error": {
          "type": "es_rejected_execution_exception",
          "reason": "rejected execution"
        }
      }
    },
    {
      "index": {
        "_id": "P1003",
        "status": 400,
        "error": {
          "type": "mapper_parsing_exception",
          "reason": "failed to parse field"
        }
      }
    }
  ]
}
~~~

In this example:

- `P1001` succeeded.
- `P1002` was temporarily rejected and can be retried.
- `P1003` failed mapping and requires fixing the data or mapping.

Do not resend the entire bulk request as if no item succeeded. Place only items identified as retryable into the retry batch. Resending everything re-writes successful items, wastes resources, and can cause side effects under `update`/`create` semantics.

### 4.3. Do Not Retry All 4xx or 5xx Errors Alike

Some 5xx errors are transient, though not all. Some 4xx errors like 429 are retryable. Base your policy on status, error type, and operation context.

Examples:

- 429 from write queue rejection: usually retryable.
- 400 from `mapper_parsing_exception`: retrying will not fix it.
- 409 version conflict: may require re-reading and recomputing the update rather than resending the exact same payload.
- 403 from an index block or permission issue: identify the root cause; avoid creating a retry loop.

### 4.4. Dead-Letter Queue for Non-Recoverable Errors

Non-retryable items or items that exhaust their retry budget should be recorded in a dead-letter queue (DLQ) or reprocessable error store.

A useful DLQ record should contain:

- Document ID and target index/alias.
- Operation type.
- Payload or a secure reference to the payload.
- Error type, status, and reason.
- Attempt count.
- Timestamp and correlation/batch ID.
- Schema or pipeline version if applicable.

Do not log complete sensitive data if payloads include personal information. Store a reference to an access-controlled location instead.

## 5. Idempotency and Retry Safety

### 5.1. Why Can Retries Cause Duplicate Writes?

A request may have been processed by Elasticsearch while the response was lost in transit. The client sees a timeout and cannot know whether the operation succeeded.

If you retry a non-idempotent operation, results can be duplicated or corrupted.

Examples:

- `index` with a stable `_id` generally overwrites the same document ID, so retrying the same payload is idempotent in final state.
- `create` with the same `_id` a second time can return a conflict because the document was already created.
- `update` with a counter-increment script can increment twice if the first attempt succeeded but the response was lost.
- `delete` with the same ID usually yields the same deleted final state, though response/semantics may differ between the first run and retry.

### 5.2. Using Deterministic Document IDs

If the data source has a stable key, use that key as `_id`—for instance, a product ID or source-generated event ID.

This ensures retrying an index operation for the same document does not create additional documents.

Do not generate a new random ID on every retry when the goal is updating the same entity. Each retry with a different ID creates a duplicate document.

### 5.3. Update Scripts and External Side Effects

Update scripts that increment, append, or trigger downstream events must be designed carefully for retries. You may need:

- A unique event ID for deduplication.
- A version or sequence number.
- Optimistic concurrency control.
- Durable tracking of processed state at the source.
- Operations designed to run repeatedly without changing the result on the second execution.

A retry policy cannot by itself make a non-idempotent operation safe.

### 5.4. Handling Version Conflicts

Under optimistic concurrency, a version conflict indicates the document changed after the client read it. Resending the old update may keep conflicting or overwrite newer changes.

A proper flow may need to:

1. Read the latest state.
2. Recompute the change.
3. Send the update with the new version/sequence token.
4. Cap conflict retries.
5. Route persistent conflicts to manual handling.

## 6. Limiting Concurrent Requests

### 6.1. What Is a Concurrency Limit?

A concurrency limit bounds the number of requests currently being processed or awaiting responses at any instant.

For example, a limit of 4 means the pipeline allows at most 4 in-flight bulk requests. Only when one request completes can the next request be sent.

This differs from a rate limit:

- **Concurrency limit**: caps the number of simultaneous in-flight tasks.
- **Rate limit**: caps the number of requests or operations per unit of time.

A system holding 4 concurrent requests that each finish in 100 ms achieves high throughput. If latency climbs to 10 seconds, concurrency stays at 4 while throughput drops automatically. Conversely, a rate limit can block new requests even when max concurrency is not reached.

### 6.2. Why Must Concurrency Be Bounded?

Allowing unbounded in-flight requests lets the client push more work than the cluster can process. As latency climbs, queued requests pile up, tying up connections, buffers, and application memory.

A concurrency limit helps:

- Restrict simultaneous requests hitting Elasticsearch.
- Keep client-side queues within controlled bounds.
- Reduce pressure on thread pools and connection pools.
- Provide a clear throttling point when the cluster slows down.
- Simplify applying backpressure to producers.

### 6.3. Bulk Size and Concurrency Are Two Separate Knobs

A bulk request of 100 documents with 4 concurrent requests puts up to roughly 400 documents in flight, excluding queues and retries.

Doubling both bulk size and concurrency roughly quadruples in-flight work.

Adjust one parameter at a time with measurements:

- Bulk size: document count and byte size per request.
- Concurrency: in-flight bulk requests.
- Queue capacity: batches waiting to be sent.
- Retry budget: max attempts and total retry duration.
- Producer rate: rate of incoming data.

Do not raise everything at once, or it becomes difficult to identify which knob overloaded the cluster.

### 6.4. Estimating Throughput with Little's Law

A useful relationship:

\[
L = \lambda \times W
\]

Where:

- \(L\): average number of in-flight requests.
- \(\lambda\): average throughput, requests/second.
- \(W\): average processing time per request, seconds.

Rearranging:

\[
\lambda \approx \frac{L}{W}
\]

With concurrency 4 and average completion time 0.5 seconds, theoretical throughput is roughly 8 requests/second. This is only an estimate; it does not mean Elasticsearch has the CPU, disk, or write capacity to sustain that rate.

When latency increases, actual throughput at fixed concurrency naturally drops. Never crank concurrency up unboundedly trying to force throughput up, as that usually worsens latency and rejections.

## 7. Adaptive Concurrency Control

### 7.1. AIMD: Additive Increase, Multiplicative Decrease

A common strategy is Additive Increase, Multiplicative Decrease (AIMD):

- When the system remains healthy over a window, increase concurrency by a small increment.
- On overload signals such as 429s or latency spikes, scale concurrency down proportionally.
- Keep concurrency within configured min/max bounds.

Example:

~~~text
maxInFlight = 4

healthy windows:
  4 -> 5 -> 6 -> 7

overload:
  7 -> floor(7 * 0.5) = 3
~~~

This probes cluster capacity gradually while backing off quickly on rejections.

### 7.2. Do Not Increase Concurrency Just Because There Are No 429s

Absence of rejections does not guarantee the cluster is idle. CPU, disk I/O, merge pressure, heap, and write latency may already be elevated.

An adaptive controller should watch multiple signals:

- 429 / rejection rate.
- Bulk request latency p50/p95.
- Successful throughput.
- Write thread pool active/queue/rejected metrics.
- Node CPU and disk utilization.
- Heap pressure and GC.
- Producer ingest lag.

Adjust only on reliable metrics. Do not scale load up when metrics are missing or stale.

### 7.3. Hysteresis and Stabilization Periods

If a controller adjusts concurrency every few milliseconds, the system can oscillate continuously. Use measurement windows, cooldown periods, and separate thresholds for scaling up vs. scaling down.

Example:

- Increase only after 3 consecutive windows with zero rejections and latency within bounds.
- Decrease immediately on repeated rejections or p95 exceeding threshold.
- After decreasing, wait for a cooldown before increasing again.
- Enforce min concurrency and max concurrency.

Specific numbers must be benchmarked against your cluster and workload rather than treated as universal production defaults.

### 7.4. Global Limits and Per-Index / Per-Tenant Limits

A single application-wide limit may be insufficient when multiple indices or tenants have different priorities.

You can use:

- A global semaphore to protect the cluster.
- Per-index limits so one index cannot starve others.
- Per-tenant quotas to isolate workloads.
- Priority queues for critical data.
- Fair scheduling so large tenants do not starve small tenants.

If multiple application instances send bulk requests concurrently, an in-JVM semaphore limits only a single instance. System-wide limits require a coordinator or per-instance quota allocation.

## 8. Combining Backoff with Concurrency Limits

### 8.1. Throttling Model

A pipeline can be structured as follows:

~~~mermaid
flowchart TD
    A[Producer] --> B[Bounded batch queue]
    B --> C[Concurrency limiter]
    C --> D[Bulk request]
    D --> E[Elasticsearch]
    E --> F{Bulk response}
    F -->|All success| G[Acknowledge batch]
    F -->|Retryable items| H[Retry scheduler with backoff and jitter]
    F -->|Permanent failures| I[Dead-letter queue]
    H --> C
    G --> B
    I --> B
~~~

The queue must have bounded capacity. When the queue is full, the producer must wait, throttle down, or persist to a durable log. Never replace a bounded queue with an unbounded in-memory list.

### 8.2. Retries Should Not Hold Permits While Sleeping

A common design mistake is holding a concurrency permit during the entire backoff sleep. If many requests hit 429, all permits can end up held by sleeping tasks, stalling the pipeline even after the cluster recovers.

A better flow:

1. Acquire a permit and send the request.
2. Receive the response.
3. Release the permit.
4. Classify failed items.
5. Schedule the retry with delay.
6. When the retry is due, acquire a fresh permit before sending.

That way, sleep time never ties up in-flight request slots.

### 8.3. Bounding the Retry Queue

The retry queue must also be bounded. If the cluster stays unhealthy for a long time while producers keep generating data, an unbounded retry queue will grow indefinitely.

Options include:

- Limiting the number of pending retry batches.
- Persisting batches to a durable queue.
- Using capped exponential backoff.
- Moving items that exhaust their retry budget to a DLQ.
- Applying backpressure to the producer.
- Applying business-approved prioritization or shedding policies if allowed.

### 8.4. Avoiding Stacked Multi-Layer Retries

If the HTTP client, Spring service, message consumer, and scheduler each implement independent retries, a single operation's total attempts can multiply. For example, three layers each retrying 3 times can produce far more requests than intended.

Designate a single layer to own the retry policy for bulk operations, or budget total attempts across layers. Record retry attempts clearly in logs and metrics.

## 9. Designing Bulk Size and Flush Strategies

### 9.1. Sizing Bulks by Bytes and Document Count

Bulk size is often configured by document count, yet document sizes vary widely. 1,000 tiny documents and 1,000 huge documents impose very different loads.

Monitor all of:

- Documents per bulk request.
- Total request bytes.
- Average and p95 document size.
- Bulk processing time.
- Rejection rate.

Do not build oversized bulk requests merely to lower HTTP call counts. Oversized bulks raise memory pressure and make retrying failed requests costlier.

### 9.2. Flushing by Size or Time

A batcher can flush when:

- Maximum document count is reached.
- Byte threshold is reached.
- Wait timeout since the first document elapses.
- A shutdown or checkpoint signal arrives.

Example:

~~~text
flush when:
  documentCount >= 500
  OR estimatedBytes >= 5 MiB
  OR oldestDocumentAge >= 1 second
~~~

These are illustrative numbers only. Benchmark against actual document sizes and cluster behavior.

### 9.3. Do Not Confuse Flush Interval with Retry Backoff

Flush interval controls when an accumulating batch is sent. Retry backoff controls when a failed batch or item is retried.

An overly short flush interval produces many tiny bulk requests. An overly short retry delay puts pressure on a struggling cluster. Configure and observe these two parameters separately.

## 10. Example Java Retry Policy Implementation

### 10.1. Computing Exponential Backoff with Full Jitter

Plain Java example:

~~~java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

public final class RetryDelayPolicy {

    private final Duration initialDelay;
    private final Duration maxDelay;

    public RetryDelayPolicy(
            Duration initialDelay,
            Duration maxDelay) {
        this.initialDelay = initialDelay;
        this.maxDelay = maxDelay;
    }

    public Duration fullJitterDelay(int retryNumber) {
        if (retryNumber < 1) {
            throw new IllegalArgumentException(
                "retryNumber must be >= 1"
            );
        }

        long initial = initialDelay.toMillis();
        long cap = maxDelay.toMillis();

        long exponentialCap = initial;

        for (int i = 1; i < retryNumber; i++) {
            if (exponentialCap > cap / 2) {
                exponentialCap = cap;
                break;
            }
            exponentialCap *= 2;
        }

        exponentialCap = Math.min(exponentialCap, cap);

        long delay = ThreadLocalRandom.current()
            .nextLong(exponentialCap + 1);

        return Duration.ofMillis(delay);
    }
}
~~~

This snippet illustrates capped delay computation. Production code should validate that `initialDelay` is positive, `maxDelay` is not smaller than `initialDelay`, guard against overflow during duration conversion, and establish clear units/precision. If `maxDelay` can approach `Long.MAX_VALUE`, avoid overflow in `exponentialCap + 1`.

### 10.2. Checking the Retry Budget

~~~java
public boolean canRetry(
        int retriesAlreadyUsed,
        int maxRetries,
        Instant deadline,
        Clock clock) {

    return retriesAlreadyUsed < maxRetries
        && clock.instant().isBefore(deadline);
}
~~~

Passing `Clock` makes deadline testing deterministic. Do not rely solely on `Thread.sleep` and attempt counts; operations must stop once the deadline expires.

### 10.3. Do Not Sleep on Callback Threads

When using an asynchronous HTTP client or bulk listener, never call `Thread.sleep` inside completion callbacks. That blocks response-handling threads and can degrade client throughput.

Use a scheduler or delayed queue to schedule retries:

~~~java
scheduler.schedule(
    () -> retryQueue.offer(failedItems),
    delay.toMillis(),
    TimeUnit.MILLISECONDS
);
~~~

This snippet illustrates the idea only. `retryQueue` must be bounded and `offer` failure must be handled when the queue is full. Retry tasks must still acquire a concurrency permit before sending requests.

## 11. Limiting Concurrency with a Semaphore

### 11.1. Synchronous Semaphore Example

~~~java
public final class BulkConcurrencyLimiter {

    private final Semaphore permits;

    public BulkConcurrencyLimiter(int maxInFlight) {
        if (maxInFlight < 1) {
            throw new IllegalArgumentException(
                "maxInFlight must be positive"
            );
        }
        this.permits = new Semaphore(maxInFlight);
    }

    public void execute(Runnable request) throws InterruptedException {
        permits.acquire();
        try {
            request.run();
        } finally {
            permits.release();
        }
    }
}
~~~

This is a simple synchronous example. For asynchronous HTTP requests, do not release the permit immediately upon method return if the request is still running. The permit must be released only when the future completes, including exceptional completion or cancellation.

### 11.2. Semaphore for `CompletableFuture`

Conceptual pattern:

~~~java
public <T> CompletableFuture<T> executeAsync(
        Supplier<CompletableFuture<T>> requestSupplier) {

    permits.acquireUninterruptibly();

    try {
        CompletableFuture<T> future = requestSupplier.get();

        return future.whenComplete((result, error) ->
            permits.release()
        );
    } catch (Throwable error) {
        permits.release();
        throw error;
    }
}
~~~

In production code, consider interruptible `acquire` or `tryAcquire(timeout)` to avoid indefinite blocking. Handle cases where the supplier throws synchronously or the future is cancelled. Each permit must be released exactly once.

### 11.3. Do Not Queue Too Many Futures Ahead of the Limiter

If a producer creates hundreds of thousands of `CompletableFuture` instances before waiting on the semaphore, pending tasks and objects still bloat the heap.

Place the limiter ahead of request creation or submission, combined with a bounded queue and backpressure so only a finite number of tasks wait.

### 11.4. Timing Out While Waiting for a Permit

If a permit cannot be acquired within the allowed time, the operation can be:

- Returned to the queue.
- Rejected with an overload status.
- Written to a durable queue.
- Timed out and transitioned to an observable failure.

Avoid letting threads wait indefinitely for permits inside a fixed-size executor, as that can exhaust worker threads.

## 12. Integrating with Spring Data Elasticsearch

### 12.1. `BulkOperations`

Spring Data Elasticsearch provides the `BulkOperations` abstraction for batching writes:

~~~java
BulkOperations bulk = operations.bulkOps(
    BulkOperations.BulkMode.BULK,
    ProductDocument.class
);

bulk.insert(products);
bulk.execute();
~~~

Exact syntax and overloads depend on the Spring Data Elasticsearch version. `BulkOperations` expresses bulk writes, while overall retry, backoff, and concurrency policies must still be designed in the ingestion layer or bulk management component.

Do not assume a single `execute()` call automatically implements every desired per-item retry policy.

### 12.2. Classifying Errors After `execute`

Depending on the version, bulk execution can return a result or throw an exception on request failure. Verify whether your API exposes per-item responses or only request-level failures.

When exact per-item retries are required:

1. Keep the list of original operations in order.
2. Read each corresponding item response.
3. Classify status and error type.
4. Build a new operation list containing only retryable items.
5. Route permanent errors to a DLQ.
6. Never retry items that already succeeded.

If high-level abstractions do not expose sufficient item metadata, use the Elasticsearch Java API Client or a lower-level bulk response API in your ingestion component.

### 12.3. Using the Elasticsearch Java API Client

The Elasticsearch Java API Client provides the Bulk API and item responses so the application can inspect every operation. Conceptual pattern:

~~~java
BulkResponse response = esClient.bulk(b -> b
    .operations(operations)
);

List<BulkOperation> retryable = new ArrayList<>();

for (int i = 0; i < response.items().size(); i++) {
    BulkResponseItem item = response.items().get(i);

    if (isRetryable(item)) {
        retryable.add(originalOperations.get(i));
    } else if (item.error() != null) {
        deadLetter(item, originalOperations.get(i));
    }
}
~~~

This snippet illustrates correlating response items back to original operations by position. Exact class names, accessors, and `BulkOperation` builders depend on your Java API Client version. Ensure item ordering is preserved when chunking batches or filtering retryable items.

### 12.4. `BulkProcessor` and Limiting Concurrent Requests

Some versions of the Elasticsearch Java API Client or client libraries provide `BulkIngester`/`BulkProcessor` to batch requests and limit concurrent bulk requests. Exact APIs vary by client version.

When using them, check the corresponding settings:

- Maximum operations per bulk.
- Maximum bytes per bulk.
- Flush interval.
- Maximum concurrent bulk requests.
- Listener handling bulk responses and errors.
- Retry/rejection policy if provided by the component.

Do not infer current client settings from legacy `BulkProcessor` names in older libraries. Spring Data Elasticsearch versions and Elasticsearch Java API Client versions must remain compatible.

### 12.5. Avoiding Overlapping Retry Layers

Spring retry, HTTP client retry, message broker redelivery, and bulk listeners may all be active simultaneously. Without a unified retry budget, actual send attempts can exceed what each layer expects individually.

Designate one layer as primary owner for item-level retries and track attempt counts across the operation. Other layers should propagate errors or handle only clearly separated failure modes.

## 13. Circuit Breakers and Backpressure

### 13.1. Circuit Breaker

If the cluster fails continuously, a circuit breaker can temporarily pause new requests:

- Closed: requests are allowed through.
- Open: requests are rejected or queued during a cooldown window.
- Half-open: a small number of probe requests are allowed to verify cluster recovery.

A circuit breaker differs from backoff. Backoff controls when an operation retries; a circuit breaker controls whether new requests are sent to the dependency at all.

### 13.2. Backpressure to the Producer

If an ingestion consumer reads faster than Elasticsearch can write, application queues grow. Bounded queues surface this early.

Options:

- Pause/resume message consumption.
- Scale down consumer count.
- Tune fetch batch size.
- Block waiting for queue capacity.
- Persist data to a durable log or broker.
- Signal overload upstream.

Never silently drop data when a queue fills. If shedding is required, enforce an explicit business policy and metrics.

### 13.3. Distinguishing Cluster Overload from Source Data Bursts

If producers push data in bursts, rate smoothing or batch scheduling before submission may help. If the cluster is overloaded even at average sustained rates, backoff only smooths bursts temporarily; you need more capacity, lower indexing cost, or a reduced ingest rate.

Backoff is not a substitute for capacity planning.

## 14. Timeouts, Cancellation, and Shutdown

### 14.1. Request Timeout and Operation Deadline

Every bulk request should have a request timeout. Every entire batch/retry sequence should have its own deadline.

If a request times out, the client cannot tell whether the server executed part or all of the operations. This is why idempotency and deterministic IDs are critical.

### 14.2. Cancellation

When a job is cancelled or the application shuts down:

- Stop accepting new batches.
- Stop scheduling new retries.
- Wait for in-flight requests to finish within a grace period.
- Persist unprocessed batches if needed.
- Route remaining failures to the DLQ or durable retry queue.
- Release each semaphore permit exactly once.

Do not discard an in-memory retry queue on shutdown unless the data is already persisted durably elsewhere.

### 14.3. Graceful Shutdown

A shutdown sequence might look like:

1. Mark the ingestion service as stopping.
2. Pause producers or consumers.
3. Flush accumulating batches if deadline permits.
4. Wait for in-flight requests within a grace period.
5. Persist unsent batches or pending retries.
6. Close the bulk client and scheduler.
7. Emit metrics for succeeded, failed, and pending items.

If the cluster is failing, do not stall shutdown indefinitely trying to retry. Ensure pending data is durably persisted so it can resume on the next startup.

## 15. Monitoring Retries and Concurrency in Production

### 15.1. Recommended Metrics

Track:

- Bulk requests sent per second.
- Documents and bytes per bulk request.
- Bulk latency p50/p95/p99.
- In-flight request count.
- Current concurrency limit.
- Requests waiting for permits.
- Item success/failure counts.
- Retry counts by status/error type.
- Actual retry delays.
- Retry queue depth and oldest item age.
- DLQ item count.
- 429s and `es_rejected_execution_exception`.
- Write thread pool active, queue, and rejected counts.
- CPU, heap, GC, disk I/O, and merge pressure.

Keep metric label cardinality bounded. Never use arbitrary document IDs or tenant IDs as Prometheus labels, as that creates massive time-series cardinality. Use logs or traces for specific identifiers.

### 15.2. Correlated Logging

Every batch should carry a batch ID or correlation ID. Log fields:

- Batch ID.
- Attempt number.
- Item count and byte size.
- Request duration.
- Error type/status.
- Retry delay.
- Concurrency limit at submission time.
- Counts of retryable, permanent, and successful items.

Do not log full payloads if they contain sensitive data.

### 15.3. Trend-Based Alerting

Alerts can be driven by:

- Sustained spikes in 429s.
- Steadily rising retry queue depth.
- Oldest retry age exceeding SLA.
- Sharp jumps in p95 bulk latency.
- Repeated concurrency reductions.
- Abnormal DLQ growth.
- Increasing producer lag.

A handful of brief 429s can happen during burst workloads. What matters is the rate, duration, and impact on ingest lag.

## 16. Benchmarking and Tuning Configuration

### 16.1. Start with Conservative Settings

An initial test baseline might use:

- Moderate bulk size by bytes and document count.
- Low concurrency.
- Capped exponential backoff.
- Full jitter.
- Finite retry budget.
- Bounded queues.
- Request timeouts and operation deadlines.
- Retries restricted to transient item errors.

This is a starting point for measurement, not a universal production profile.

### 16.2. Stepwise Load Testing

A benchmarking workflow:

1. Send a small bulk request and measure baseline latency.
2. Increase bulk size while holding concurrency fixed.
3. Record throughput, latency, and rejections.
4. Keep a sensible bulk size and increment concurrency step-by-step.
5. Find the stable throughput plateau before rejections climb.
6. Test intentional bursts and 429 errors in a test environment.
7. Verify jitter disperses retries and concurrency stays bounded.
8. Test slow clusters, timeouts, and shutdowns.
9. Pick an operating point with headroom rather than running right at the limit.

### 16.3. Do Not Optimize for Throughput Alone

A configuration with high peak throughput yet terrible p99 latency, growing retry queues, or frequent rejections is not healthy.

Evaluate simultaneously:

- Successful documents/second.
- End-to-end ingest lag.
- Bulk latency.
- Rejection rate.
- Retry volume.
- Heap/CPU/disk.
- Permanent error rate.
- Recovery behavior after bursts.

### 16.4. Testing with Multiple Clients

Jitter only proves its value when multiple clients avoid synchronized retries. Simulate multiple workers or application instances hitting 429 at once, then inspect retry timestamps.

A single-client test cannot prove the system avoids synchronized retry storms.

## 17. Reference Configuration Example

The following parameters only illustrate a bounded pipeline:

| Parameter | Example Value | Purpose |
|---|---:|---|
| Bulk documents | 500 | Limit operations per batch |
| Bulk bytes | 5 MiB | Avoid oversized requests |
| Max in-flight | 4 | Cap concurrent bulk requests |
| Initial backoff | 200 ms | Starting delay |
| Max backoff | 10 seconds | Cap exponential delay |
| Jitter | Full jitter | Disperse retry timing |
| Max retries | 5 | Cap retry attempts |
| Request timeout | 10 seconds | Bound a single HTTP request |
| Operation deadline | 45 seconds | Bound the full retry sequence |
| Retry queue | 100 batches | Cap in-memory backlog |

Do not copy this table blindly into production. Tune for document size, shard count, node capacity, network, workload, and SLAs.

## 18. Common Pitfalls

| Symptom | Possible Cause | Remedy |
|---|---|---|
| 429s climb after each retry | Immediate retry or too short a delay | Exponential backoff and jitter |
| Multiple clients retry at the same instant | Identical exponential delays without jitter | Full/equal/decorrelated jitter |
| Cluster stays overloaded despite backoff | Too many in-flight requests or producer rate too high | Cap concurrency, bounded queues, backpressure |
| Bulk with successful items resent completely | Not handling partial failure | Retry only retryable failed items |
| Mapping errors repeat forever | Retrying permanent data errors | Classify errors and route to DLQ |
| Duplicate documents created | Retrying with new IDs or non-idempotent operations | Deterministic IDs and deduplication |
| Counters increment twice | Non-idempotent update script and response timeout | Event IDs/versions or repeatable update design |
| Semaphore permits leak | Released only on success path | Release in completion/`finally`, including errors and cancellation |
| Pipeline stalls after cluster recovers | Holding permit during backoff sleep | Release permit before scheduling retry |
| Heap grows despite small concurrency | Creating too many futures or unbounded queues | Bounded queues and limiter before request creation |
| Shutdown drops batches | Retry queue lives only in memory | Persist pending batches and graceful shutdown |
| Throughput drops as concurrency increases | Cluster saturated, queues/latency grow | Reduce concurrency and find stable operating point |
| Multi-layer retries multiply request volume | HTTP, service, and broker all retry | Unified retry budget |
| Metric dashboards explode in series | Arbitrary ID/tenant labels | Bounded labels and logs/traces for specifics |

## 19. Practical Implementation Workflow

When building a bulk ingestion pipeline, proceed in order:

1. Identify which bulk operations can be retried safely.
2. Enforce deterministic document IDs or suitable deduplication.
3. Choose batch size by both document count and byte size.
4. Set a concurrency limit for in-flight requests.
5. Use bounded queues and backpressure for producers.
6. Separate request-level and item-level error classification.
7. Retry only identified transient errors.
8. Use capped exponential backoff and jitter.
9. Release concurrency permits while waiting for retry.
10. Cap max retries and operation deadlines.
11. Route permanent errors or exhausted retries to a DLQ.
12. Monitor retries, queue depth, 429s, latency, and cluster resources.
13. Benchmark bulk size and concurrency incrementally.
14. Test bursts, multi-client contention, partial success, timeouts, and shutdowns.
15. Roll out with capacity headroom and the ability to shed or throttle load if the cluster shows stress.

## 20. Key Takeaways

- Backoff spaces out retries; exponential backoff grows wait times as failures repeat.
- Jitter injects randomness so multiple clients do not retry simultaneously.
- Full jitter picks delays from 0 up to the exponential cap; equal jitter preserves a base pause.
- Use a cap, max retries, and operation deadlines to bound retries.
- Honor `Retry-After` when supplied by servers/proxies while preserving jitter without retrying early.
- Classify errors by status and error type; 429 is typically retryable, whereas mapping/validation errors require fixing data.
- The Bulk API has partial failures: HTTP 200 does not mean every item succeeded.
- Retry only transiently failed items; never resend an entire bulk request containing succeeded items.
- Deterministic document IDs and idempotent operations make retries safe when responses are lost.
- Concurrency limits cap in-flight requests; rate limits cap submission rate.
- Combine concurrency limiters, bounded queues, and backpressure to avoid unbounded backlogs.
- Never hold semaphore permits while sleeping for backoff.
- Control stacked retry layers to prevent multiplying request volume.
- Monitor bulk latency, 429s, retry queue depth, DLQ, concurrency, heap, and write thread pools.
- Choose bulk size, concurrency, and retry policies through benchmarks on production-like workloads.

Backoff, jitter, and concurrency limits reinforce each other. Backoff gives the cluster time to recover, jitter disperses retry attempts, and concurrency limits keep in-flight work within manageable bounds. Combined with per-item retries, idempotency, bounded queues, and backpressure, a bulk ingestion pipeline can recover from overload without unleashing a fresh wave of traffic that makes matters worse.
