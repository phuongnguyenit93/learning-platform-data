# Timeouts, Retries, Pagination, and Long-Running Operations

A Java application on Google Cloud frequently calls multiple APIs: reading configuration from Secret Manager, listing objects in Cloud Storage, querying BigQuery, creating Compute Engine resources, or launching Dataflow pipelines. These calls traverse the network and depend on remote services. They can be slow, temporarily unavailable, return thousands of results, or take many minutes to complete.

Without timeouts, a thread can stay blocked far too long. If every error is retried, the system can amplify load on an already overloaded service or repeat a write operation. Without handling pagination, an application reads only the first page or loads entire datasets into memory. If a caller waits on a long operation over a single HTTP request, users and gateways can time out even while the backend Google Cloud task continues running.

In Java and Spring, four mechanisms must work together:

- **Timeouts and deadlines:** bounding wait time per call and for the overall operation.
- **Retries:** retrying transient errors under bounded policies with backoff and jitter.
- **Pagination:** reading large result sets page by page using page tokens to continue.
- **Long-running operations (LRO):** initiating long tasks, persisting the operation name, and tracking status via polling or callbacks.

Cloud Client Libraries for Java use GAX to provide retries, paging, and LROs across many Google Cloud APIs. For HTTP APIs or external Spring services, applications can use `RestClient` or `WebClient` with corresponding policies configured. The goal is to keep the application responsive within defined budgets, avoid duplicate mutations, and resume work after process interruptions.

After this lesson, you will be able to:

- Distinguish connect timeout, per-attempt timeout, total timeout, and request deadline.
- Choose which errors should be retried and which should fail immediately.
- Design exponential backoff, jitter, retry budgets, and idempotency.
- Use `RetrySettings` from the Google API Client Libraries for Java.
- Configure timeouts and retries for Spring `WebClient`.
- Read complete paginated results using `PagedResponse` or page tokens.
- Track, recover, and handle errors from `OperationFuture`.
- Measure timeouts, retries, pagination, and LRO completion durations in production.

## 1. Timeouts and Deadlines

### Why Set Timeouts?

When calling an API from a Java application, wait time can include:

1. Waiting to acquire a connection from the connection pool.
2. Establishing TCP and TLS to the server.
3. Sending the request and waiting for server processing.
4. Receiving response headers and body.
5. Decoding the response, retrying, or polling if needed.

If you configure only an application-layer timeout without bounding lower layers, requests can still hang in connection pools or sockets longer than expected. Timeouts should be derived from the time budget acceptable to callers.

### Types of Timeouts

| Type | What it limits | Example |
|---|---|---|
| Connection timeout | Time to establish a TCP connection to the server | Max 2 seconds to open a connection |
| Read/response timeout | Time waiting for response data or gaps between chunks | Max 5 seconds to receive a response |
| Per-attempt RPC timeout | Time for a single API call attempt | Max 3 seconds per attempt |
| Total operation timeout | Total time for a logical call, including delays and retries | Max 10 seconds across the entire retry chain |
| Application deadline | Maximum time for the entire business request | HTTP request must finish within 8 seconds |
| LRO polling timeout | How long the client keeps polling a long operation | Poll operation for up to 2 hours |

A **timeout** usually limits a single step or wait interval. A **deadline** is the final point in time by which all work must finish. Across multiple layers, an outer deadline must exceed the sum of budgets of downstream calls while remaining within the original request limit.

For example, a Spring API has an 8-second deadline. If it calls two services sequentially, neither service should have an 8-second total timeout. You might allocate 3 seconds to the first service, 3 seconds to the second, and leave the remainder for processing, serialization, and response delivery. If an operation takes much longer, switch to an LRO or asynchronous model.

### Do Not Confuse Timeout with Cancellation

A client timing out does not mean the server stopped processing. The request may have reached the server and mutated data before the response was lost. This is especially critical for resource creation, payments, or deployment commands. After a timeout, actual server state could be:

- Request never reached the server.
- Server received it but has not executed it yet.
- Server succeeded, but the response never reached the client.
- Server is still processing.

Therefore, for write operations, timeouts must be paired with idempotency design and status lookup mechanisms.

## 2. Retrying Properly

### Which Errors Are Retryable?

Retries fit transient errors where a subsequent attempt has a reasonable chance of succeeding. Common cases to evaluate:

| Error | Should retry? | Notes |
|---|---|---|
| Connection loss, connection reset, network timeout | Conditionally | Retry only if the operation is safe to repeat or carries an idempotency key |
| HTTP 429 / RESOURCE_EXHAUSTED | Usually yes | Respect `Retry-After` or server retry guidance |
| HTTP 500, 502, 503, 504 | Usually yes | Use backoff; never retry indefinitely |
| gRPC UNAVAILABLE | Usually yes | Temporary service or connectivity issue |
| gRPC DEADLINE_EXCEEDED | Conditionally | Check whether the server already executed the operation |
| HTTP 400 / INVALID_ARGUMENT | No | Fix the payload or request |
| HTTP 401 / UNAUTHENTICATED | Do not loop infinitely | Refresh credentials via the proper mechanism and retry boundedly |
| HTTP 403 / PERMISSION_DENIED | No | Fix IAM or permission configuration |
| HTTP 404 / NOT_FOUND | Usually no | Except for eventual consistency cases documented by the API |
| HTTP 409 / ABORTED | API-dependent | May require re-reading state, updating version, or retrying a transaction |

These are general guidelines. Follow each Google Cloud API's retry policy, because identical error codes can carry different semantics depending on the operation.

### Exponential Backoff

Exponential backoff increases the wait interval after each failure:

\[
delay_n = \min(maxDelay,\ initialDelay \times multiplier^{n-1}), \quad n \ge 1
\]

Example with an initial delay of 200 ms, multiplier of 2, and max delay of 2 seconds:

| Retry attempt | Delay before retry (excluding jitter) |
|---|---:|
| 1 | 200 ms |
| 2 | 400 ms |
| 3 | 800 ms |
| 4 | 1,600 ms |
| 5 onward | 2,000 ms |

Backoff relieves pressure on struggling services. However, if all clients retry at the exact same instant, they can create synchronized traffic spikes.

### Jitter

Jitter adds randomness to wait durations to spread retries out. Google Cloud Java Client Libraries enable jitter automatically for retries; there is no need to set a jitter flag manually in current GAX configurations. For Spring or custom HTTP clients, you can use full jitter:

\[
actualDelay = random(0,\ cappedExponentialDelay)
\]

Jitter helps prevent multiple instances from retrying simultaneously after a disconnect or widespread outage.

### Retry Budgets and Limits

A retry policy needs at minimum:

- Maximum attempt count or total timeout.
- Initial delay, multiplier, and max delay.
- Per-attempt timeout.
- Allowlist of retryable status codes.
- Retry budget system-wide or per dependency.

Never retry indefinitely. Retrying across multiple layers multiplies call volume. For example, an API gateway retrying 3 times, a Spring service retrying 3 times, and a Cloud Client Library retrying 3 times can produce up to 27 backend calls for a single initial request. Designate which layer owns retries and disable or bound duplicate retries elsewhere.

When a service returns `Retry-After` or gRPC `RetryInfo`, honor the server-requested wait within your deadline and application policy.

## 3. Idempotency Before Retrying Writes

An operation is **idempotent** if executing it multiple times with the same inputs produces the same final state as executing it once. For instance, updating a resource to a declared target state can usually be made idempotent; creating a new order is generally not automatically idempotent.

### Dangerous Scenario

An application sends a resource creation request. The server creates it successfully, but the response is lost on the network. The client times out and retries. If the API cannot recognize the retry, two resources or two transactions may be created.

Ways to mitigate the risk:

- Use `requestId`, an idempotency key, or a client token if supported by the API.
- Use client-specified resource IDs where permitted by the API.
- Use conditional updates such as `ETag`, `generation`, or `If-Match` to avoid overwriting newer changes.
- After a timeout, query status by resource name or operation name before retrying.
- Design business endpoints with unique keys and store processing results to return the same outcome on duplicate requests.

Do not invent an `Idempotency-Key` header assuming a Google Cloud API understands it. Use only mechanisms documented by the specific API and check idempotency key retention windows.

### Operation Classification

| Operation | Retry approach |
|---|---|
| GET/list/read | Usually safe to retry on transient errors |
| PUT updating to a declared state | Usually idempotent, though check preconditions |
| DELETE resource | Can be idempotent regarding final state; retries may return `NOT_FOUND` |
| POST creating a resource | Retry only when the API supports request ID/idempotency or status can be checked first |
| Money transfer, order creation, email dispatch | Requires an idempotency key or business-layer deduplication |

Retries do not replace transactions, optimistic locking, or business state validation.

## 4. Configuring Retries for Google Cloud Java Client Libraries

### GAX RetrySettings

Cloud Client Libraries for Java use GAX for many RPC operations. `RetrySettings` controls timeouts and retries:

| Property | Meaning |
|---|---|
| `initialRetryDelayDuration` | Wait time before the first retry |
| `retryDelayMultiplier` | Delay growth factor |
| `maxRetryDelayDuration` | Delay cap |
| `initialRpcTimeoutDuration` | Timeout for the first RPC attempt |
| `rpcTimeoutMultiplier` | RPC timeout multiplier across attempts |
| `maxRpcTimeoutDuration` | Per-RPC timeout cap |
| `totalTimeoutDuration` | Maximum total duration of the retried operation |
| `maxAttempts` | Maximum attempt count |

Illustrative configuration:

~~~java
import com.google.api.gax.retrying.RetrySettings;
import java.time.Duration;

RetrySettings retrySettings =
    RetrySettings.newBuilder()
        .setInitialRetryDelayDuration(Duration.ofMillis(200))
        .setRetryDelayMultiplier(2.0)
        .setMaxRetryDelayDuration(Duration.ofSeconds(2))
        .setInitialRpcTimeoutDuration(Duration.ofSeconds(2))
        .setRpcTimeoutMultiplier(1.0)
        .setMaxRpcTimeoutDuration(Duration.ofSeconds(2))
        .setTotalTimeoutDuration(Duration.ofSeconds(10))
        .setMaxAttempts(5)
        .build();
~~~

This is an example configuration, not optimal for every API. GAX enforces both attempt limits and total timeout; calls cannot exceed the overall budget. Jitter is applied automatically.

In GAX, an RPC timeout of `Duration.ZERO` can allow a single RPC to wait indefinitely until the connection drops or a connect timeout occurs. Do not rely on this value as a business deadline; always set an explicit total timeout or max attempts.

### Attaching RetrySettings to a Specific RPC

Each Cloud Client Library provides its own `Settings` class. RPC names and builder accessors depend on the library. General pattern:

~~~java
// Illustrative: settings and RPC builder names depend on the API in use.
SomeServiceSettings.Builder settingsBuilder =
    SomeServiceSettings.newBuilder();

settingsBuilder.someReadCallSettings()
    .setRetrySettings(retrySettings);

SomeServiceClient client =
    SomeServiceClient.create(settingsBuilder.build());
~~~

Do not assume one `RetrySettings` applies across the entire client. Inspect `StubSettings` for the exact library to see which RPCs retry, which status codes are retryable, and which settings govern retries versus polling. Service teams usually tune defaults to match API behavior; override them only with metrics and clear justification.

### Avoiding Double Retries

Cloud Client Libraries automatically retry certain RPCs by default. If wrapping those calls with Resilience4j or Spring Retry, define clearly which layer owns retries. For operations that already have GAX retries, it is usually best to keep retries inside the client library and apply circuit breakers or bulkheads at the application layer rather than duplicating the same policy.

## 5. Timeouts and Retries in Spring WebClient

Spring `WebClient` fits reactive applications or high-concurrency outbound calls. Timeouts should be configured on the HTTP connector to bound connection and response phases; `Mono.timeout` can add an overall deadline for the reactive pipeline.

### Configuring Connection and Response Timeouts

Example using Reactor Netty:

~~~java
import io.netty.channel.ChannelOption;
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

@Configuration
class HttpClientConfiguration {

    @Bean
    WebClient partnerWebClient() {
        HttpClient httpClient =
            HttpClient.create()
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2_000)
                .responseTimeout(Duration.ofSeconds(5));

        return WebClient.builder()
            .baseUrl("https://partner.example.com")
            .clientConnector(new ReactorClientHttpConnector(httpClient))
            .build();
    }
}
~~~

Connection timeout bounds TCP connection establishment; response timeout bounds waiting for a response at the HTTP client layer. For long data streams, consider read/write and idle timeouts appropriate to the protocol.

### Conditional Retries

The example below retries only network errors and selected transient status codes. Adjust error filtering for your actual API:

~~~java
import java.time.Duration;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

Mono<String> loadStatus(String id) {
    return partnerWebClient.get()
        .uri("/jobs/{id}", id)
        .retrieve()
        .bodyToMono(String.class)
        .retryWhen(
            Retry.backoff(3, Duration.ofMillis(200))
                .maxBackoff(Duration.ofSeconds(2))
                .jitter(0.5)
                .filter(error ->
                    error instanceof WebClientRequestException
                    || (error instanceof WebClientResponseException response
                        && (response.getStatusCode().value() == 429
                            || response.getStatusCode().is5xxServerError()))))
        .timeout(Duration.ofSeconds(10));
}
~~~

This snippet illustrates retrying a `GET`. For `POST` or write operations, add retries only after ensuring idempotency. Timeouts and retries must fit within one overall deadline; if every retry gets a fresh timeout without a total cap, requests can exceed the caller's budget.

This example demonstrates error filtering and does not inspect the `Retry-After` header. If a partner API returns `Retry-After`, add retry logic that reads the response header and schedules the next attempt accordingly while preserving the overall deadline.

When using synchronous Spring `RestClient`, configure timeouts on `ClientHttpRequestFactory` or the underlying HTTP client. `RestClient` is the modern synchronous choice; `WebClient` suits non-blocking and streaming workloads. Never rely on controller-level timeouts in place of socket or HTTP connector timeouts.

## 6. Pagination: Reading Data Page by Page

### Why Do APIs Paginate?

APIs limit records per response to prevent oversized payloads, high memory usage, or slow responses. A list request typically returns:

- The list of items on the current page.
- `nextPageToken` to request the next page.
- Optionally a total record count, though not every API provides one.

`pageSize` is the maximum number of items the client wants. The server may return fewer items; never conclude pagination is finished merely because the item count is smaller than `pageSize`. The termination condition is typically the absence of `nextPageToken`.

### Using GAX PagedResponse

Many list methods in Cloud Client Libraries for Java return `PagedResponse`. `iterateAll()` automatically fetches subsequent pages as needed:

~~~java
import com.google.cloud.secretmanager.v1.ListSecretsRequest;
import com.google.cloud.secretmanager.v1.ProjectName;
import com.google.cloud.secretmanager.v1.Secret;
import com.google.cloud.secretmanager.v1.SecretManagerServiceClient;

void listAllSecrets(String projectId) throws Exception {
    try (SecretManagerServiceClient client =
             SecretManagerServiceClient.create()) {

        ListSecretsRequest request =
            ListSecretsRequest.newBuilder()
                .setParent(ProjectName.of(projectId).toString())
                .setPageSize(100)
                .build();

        SecretManagerServiceClient.ListSecretsPagedResponse response =
            client.listSecrets(request);

        for (Secret secret : response.iterateAll()) {
            process(secret);
        }
    }
}
~~~

`iterateAll()` lazily loads each page as the loop demands data. While convenient for processing all results, it does not eliminate execution time or network calls. Each subsequent page can still hit timeouts, retries, or permission errors.

If you only need the current page, use `response.getPage().getValues()`. For manual control, read `getNextPageToken()` and pass that token into the next request.

### Manual Pagination

~~~java
String pageToken = "";

do {
    ListSecretsRequest.Builder builder =
        ListSecretsRequest.newBuilder()
            .setParent(ProjectName.of(projectId).toString())
            .setPageSize(100);

    if (!pageToken.isEmpty()) {
        builder.setPageToken(pageToken);
    }

    var page = client.listSecrets(builder.build());

    for (Secret secret : page.getPage().getValues()) {
        process(secret);
    }

    pageToken = page.getNextPageToken();
} while (!pageToken.isEmpty());
~~~

Each call retrieves one page. This approach fits when you need progress checkpoints, want to return pages individually to callers, or want to stop after a record limit.

### Pagination in REST APIs and Spring

In REST APIs, requests typically accept `pageSize` and `pageToken`, and responses return `items` and `nextPageToken`:

~~~http
GET /v1/projects/my-project/secrets?pageSize=100&pageToken=eyJvZmZzZXQiOjEwMH0
~~~

Illustrative response:

~~~json
{
  "items": [
    { "name": "projects/my-project/secrets/db-password" }
  ],
  "nextPageToken": "eyJvZmZzZXQiOjIwMH0"
}
~~~

Pass back the exact token returned by the server; do not decode, increment offsets, or edit tokens yourself. Keep query filters, sorting, and scopes identical across pages. If an API uses cursors, the token is usually bound to the original query.

### Designing Pagination for Your Spring API

A Spring endpoint can accept page size and cursor, returning items along with `nextPageToken`:

~~~java
public record PageResponse<T>(
    List<T> items,
    String nextPageToken
) {}
~~~

Principles:

- Enforce a maximum page size on the server, such as 100 or 500 depending on query cost.
- Use a deterministic sort order with a unique tie-breaker, such as `created_at, id`.
- Prefer keyset/cursor page tokens over large offsets as datasets grow.
- Avoid putting secrets or access permissions in plaintext tokens; sign or encrypt cursors if needed.
- Validate that the token matches the current user, tenant, filters, and sort order if the token encodes query context.
- Use an empty token or omit the next token to signal end of data according to your published contract.

### Pagination and Mutating Data

While the client reads page 1, new records may be inserted or existing records deleted. Unless the API guarantees snapshot consistency, pages can contain duplicates or skip items. Reduce risk by:

- Sorting by a stable field with a unique tie-breaker.
- Using keyset cursors anchored to the last record on the page instead of offsets.
- Using a snapshot timestamp or read time when supported by the API.
- Deduplicating by resource ID when the contract permits.
- Saving checkpoints after completing each page so processing can resume.

Do not assume page tokens remain valid indefinitely. Some APIs expire or invalidate tokens once underlying data state changes.

## 7. Long-Running Operations (LRO)

### What Is an LRO?

Some Google Cloud operations take several minutes or longer: creating a GKE cluster, launching a Dataflow job, provisioning a Dataproc cluster, or modifying large resources. Instead of holding an HTTP connection open for the entire duration, the API returns an operation representing the running task.

Basic flow:

~~~mermaid
sequenceDiagram
    participant App as Java/Spring application
    participant API as Google Cloud API
    participant Worker as Backend service
    App->>API: Send resource creation request
    API-->>App: Return operation name
    API->>Worker: Start work
    loop Poll on schedule/backoff
        App->>API: Get operation status
        API-->>App: done=false + metadata
    end
    Worker-->>API: Complete or fail
    App->>API: Get operation status
    API-->>App: done=true + response/error
~~~

An operation typically includes:

- `name`: server-assigned operation identifier.
- `metadata`: progress or task details, depending on the API.
- `done`: indicates whether the operation has finished.
- `response`: result payload if succeeded.
- `error`: error code and details if failed.

The operation name must be persisted if the application needs to resume tracking after a restart.

### Identifying LROs in Java Client Libraries

In Cloud Client Libraries for Java, LROs typically have methods ending in `Async` or expose an `OperationCallable`. The return type is usually `OperationFuture`:

~~~java
OperationFuture<ResponseT, MetadataT> future =
    client.someLongRunningMethodAsync(request);
~~~

`OperationFuture` tracks the operation through polling calls. Client libraries come preconfigured with default polling intervals and retries chosen by the service team; you do not need to write a custom polling loop unless special requirements demand it.

### Waiting for Results with OperationFuture

Example with Dataproc:

~~~java
import com.google.api.gax.longrunning.OperationFuture;
import com.google.cloud.dataproc.v1.Cluster;
import com.google.cloud.dataproc.v1.ClusterControllerClient;
import com.google.cloud.dataproc.v1.ClusterOperationMetadata;
import com.google.cloud.dataproc.v1.CreateClusterRequest;
import java.util.concurrent.CancellationException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

Cluster createCluster(CreateClusterRequest request) throws Exception {
    try (ClusterControllerClient client =
             ClusterControllerClient.create()) {

        OperationFuture<Cluster, ClusterOperationMetadata> future =
            client.createClusterAsync(request);

        try {
            return future.get(30, TimeUnit.MINUTES);
        } catch (TimeoutException | CancellationException timeout) {
            // Caller or polling mechanism stopped waiting. Server-side operation may still be running.
            String operationName = future.getName();
            if (operationName != null) {
                saveOperationName(operationName);
            }
            throw timeout;
        }
    }
}
~~~

`Future.get(timeout, unit)` limits how long the calling thread waits for a result. Timing out on `get` does not mean the backend cancelled the task. Save the operation name so tracking can continue.

The 30-minute limit on `Future.get` does not change the underlying polling timeout configured by GAX for the service. If the default polling policy finishes earlier, the client may throw `CancellationException` before the caller hits 30 minutes. When longer tracking is needed, configure the polling algorithm for that specific LRO as shown next. If a timeout occurs before the initial request returns an operation name, `getName()` may be null; in that case use a request ID or API-supported status lookup rather than blindly resending the create request.

### Distinguishing Caller Wait Timeouts from Polling Timeouts

GAX uses separate `RetrySettings` for LRO polling. If polling's total timeout is exceeded, the library can throw `CancellationException` and stop client-side polling. This **does not mean** the Google Cloud task was cancelled. The backend may continue and succeed later.

Therefore:

- `TimeoutException` from `Future.get(timeout, unit)` means the caller stopped waiting.
- `CancellationException` from GAX's total timeout can mean the client library stopped tracking the operation.
- An operation is truly cancelled only when the API supports cancellation and the server confirms or reports a cancelled state.

Do not discard the operation name when the caller times out. Use it to query status, resume tracking, or handle late results.

### Persisting and Resuming Operations

`OperationFuture` provides `getName()` to retrieve the operation name. Some `OperationCallable` instances also provide `resumeFutureCall(operationName)` to construct a future tracking a previously started operation:

~~~java
String operationName = loadOperationName(jobId);

OperationFuture<Cluster, ClusterOperationMetadata> resumed =
    client.createClusterOperationCallable()
        .resumeFutureCall(operationName);

Cluster result = resumed.get();
~~~

Callable and response type names vary by API. Always resume operations using a client of the matching service and its corresponding operation name. If an API does not support resuming via the client library, call `Operations.GetOperation` or the tracking endpoint documented by the service.

### Configuring Polling for an LRO

If an operation routinely takes longer than the default timeout, you can raise the total timeout or adjust the polling interval for that specific LRO RPC:

~~~java
import com.google.api.gax.longrunning.OperationTimedPollAlgorithm;
import com.google.api.gax.retrying.RetrySettings;
import com.google.api.gax.retrying.TimedRetryAlgorithm;
import com.google.cloud.dataproc.v1.ClusterControllerClient;
import com.google.cloud.dataproc.v1.ClusterControllerSettings;
import java.time.Duration;

ClusterControllerSettings.Builder settingsBuilder =
    ClusterControllerSettings.newBuilder();

TimedRetryAlgorithm pollingAlgorithm =
    OperationTimedPollAlgorithm.create(
        RetrySettings.newBuilder()
            .setInitialRetryDelayDuration(Duration.ofSeconds(5))
            .setRetryDelayMultiplier(1.5)
            .setMaxRetryDelayDuration(Duration.ofSeconds(45))
            .setTotalTimeoutDuration(Duration.ofHours(2))
            .build());

settingsBuilder.createClusterOperationSettings()
    .setPollingAlgorithm(pollingAlgorithm);

ClusterControllerClient client =
    ClusterControllerClient.create(settingsBuilder.build());
~~~

This snippet adjusts polling only for `createClusterOperation`; other LROs on the same client keep their own settings. Do not raise timeouts arbitrarily. Consider actual completion times, business SLAs, quotas, and how the API handles operations.

### Cancelling Operations

Some APIs support cancelling operations, though cancellation is usually best-effort. The server may not support it or the task may have passed the point of cancellation. Cancelling the client-side future and sending a cancel command to the server are two distinct actions. When cancellation is needed, invoke the service-supported cancel API and continue checking operation status for the final outcome.

## 8. Combining Pagination, Retries, and Deadlines

A single `iterateAll()` call can trigger many network requests. Each page fetch has its own retries, yet the entire data-reading task still needs an overall time limit and checkpointing.

For example, a batch job reading 100,000 secrets:

1. Choose an appropriate page size, such as 100.
2. Use `iterateAll()` if sequential processing suffices without fine-grained checkpoints.
3. Use manual pagination if you need to persist the token after each page.
4. Retry transient errors while fetching pages, never permission errors or invalid tokens.
5. Record processed items via resource IDs or checkpoints.
6. When the job restarts, resume from the last valid checkpoint; if the token expired, restart the query using snapshot or deduplication rules.

Never hold a database transaction open across the entire pagination loop. Process each page in short transactions to reduce locking and simplify recovery.

## 9. Designing Spring APIs for Long-Running Work

If your Spring application exposes an endpoint to launch a long-running task, do not block callers on the HTTP response until the task finishes. Use an asynchronous pattern instead:

1. Client calls `POST /exports`.
2. Spring validates the request, checks the idempotency key, and persists a job record.
3. Spring dispatches the work to a worker or queue.
4. The API returns `202 Accepted` with `jobId` and a status URL.
5. Client calls `GET /exports/{jobId}` to poll for `QUEUED`, `RUNNING`, `SUCCEEDED`, or `FAILED`.
6. Once finished, the client downloads the result via the provided URL or resource.

Illustrative response:

~~~http
HTTP/1.1 202 Accepted
Location: /v1/exports/job-7f31
Retry-After: 5
Content-Type: application/json

{
  "jobId": "job-7f31",
  "status": "RUNNING",
  "statusUrl": "/v1/exports/job-7f31"
}
~~~

`Retry-After` suggests how long the client should wait before polling again. The status endpoint should be lightweight and must never re-trigger the task. Persist job state and operation names durably so tracking survives application restarts.

### State and Idempotency

If a client resends `POST /exports` because the first response timed out, the idempotency key lets the server recognize the duplicate request. The server should store the key, payload hash, job ID, and creation result within a single transaction. If the same key arrives with a different payload, return a conflict error per your contract.

Do not tie up an HTTP request thread polling a Google Cloud LRO for hours. A background worker or scheduler can track the operation, update the job record, and emit an event upon completion.

## 10. Observability and Operations

Timeouts, retries, pagination, and LROs require telemetry to distinguish service issues from configuration or application bugs.

Track:

- Retry counts per RPC and total retries per dependency.
- Rate of requests ending in timeout, broken down by connect/read/RPC/total timeout.
- Actual latency of each attempt and the overall logical operation.
- Pages fetched, items per page, failed page fetches, and expired tokens.
- Active LROs, operation age, completion time p50/p95/p99, and failure rates.
- Operations where client polling stopped while the backend continued processing.
- Rate of requests rejected by circuit breakers or throttled by bulkheads.

Logs should include correlation IDs, resource names, operation names, attempt numbers, and error codes. Never log access tokens, secrets, sensitive payloads, or full page tokens if a token can reveal query context.

### Useful Alerts

- Rapid spikes in retry rates or exhausted retry budgets.
- Rising `429`/`RESOURCE_EXHAUSTED` rates.
- Timeout p95/p99 exceeding request budgets.
- Pagination repeatedly receiving the same page token or abnormal page counts.
- LROs running past expected thresholds or making no progress.
- Unfinished operation counts climbing continuously.

Circuit breakers stop an application from flooding a failing dependency. Bulkheads cap concurrent calls so one slow dependency cannot exhaust all threads or connection pools.

## 11. Common Issues and Fixes

| Symptom | Possible cause | Fix |
|---|---|---|
| Requests hang for a long time | Missing connect/read/total timeouts or overly high lower-layer timeouts | Set layered timeouts and an overall deadline |
| Retries never succeed | Retrying configuration, validation, or IAM errors | Filter for transient error codes; fail permanent errors immediately |
| Backend receives duplicate requests | Retrying non-idempotent POST operations | Use request ID/idempotency keys or check status before retrying |
| 429 errors surge after adding retries | Retrying too fast or stacked retry layers | Increase backoff, add jitter, reduce retries, and honor `Retry-After` |
| Only the first page is returned | Code reads only the first response's values | Use `iterateAll` or a page-token loop |
| Infinite loop during pagination | Token not updated or API returns repeating tokens | Verify termination conditions, detect repeated tokens, and log |
| Duplicate or missing records across pages | Dataset mutates during pagination or unstable sort | Use cursors/snapshots, stable sort with tie-breakers, and deduplication |
| LRO times out yet the resource still gets created | Client stopped waiting/polling while backend continued | Save operation name; check status before issuing new requests |
| Unexpected LRO cancellation handling | Treating `CancellationException` as proof of server cancel | Distinguish client polling timeouts from server-side cancel API calls |
| Spring WebClient timeouts behave unexpectedly | Using only `Mono.timeout` or only socket timeout | Configure connection/response timeouts plus a business deadline |

## 12. Production Checklist

- [ ] Appropriate connect, response/read, and total deadlines are configured.
- [ ] Dependency timeout budgets fit inside the caller request's deadline.
- [ ] Retries apply only to transient errors and are capped by max attempts or total timeout.
- [ ] Exponential backoff, jitter, and `Retry-After`/`RetryInfo` are respected.
- [ ] No uncontrolled stacked retries exist across gateway, Spring, and GAX.
- [ ] Write operations use idempotency keys, request IDs, or status lookups.
- [ ] Pagination uses server-issued page tokens with explicit termination conditions.
- [ ] Page size caps, stable sorting, and data-mutation handling are in place.
- [ ] LROs persist operation names and can resume after restarts.
- [ ] Caller timeouts, polling timeouts, and server-side cancellations are clearly distinguished.
- [ ] Metrics and alerts cover retries, timeouts, page counts, and LRO durations.
- [ ] Tokens, secrets, and sensitive data are never logged.

## 13. Conclusion

Timeouts bound wait times; retries ride out transient failures; pagination processes large datasets incrementally; LROs track lengthy work without holding a single request open continuously. All four mechanisms must be designed together around business deadlines and API capabilities.

With Google Cloud Java Client Libraries, leverage built-in retries, pagination, and LRO support in GAX before building custom replacements. With Spring `WebClient` or custom REST APIs, configure HTTP client timeouts, conditional retries, and idempotency for writes. By persisting page tokens, operation names, and checkpoints properly, applications can resume work after timeouts or restarts without unintended side effects.

## References

- [Configure client-side retries – Java](https://docs.cloud.google.com/java/docs/client-retries)
- [RetrySettings – Java Client Libraries](https://docs.cloud.google.com/java/docs/reference/gax/latest/com.google.api.gax.retrying.RetrySettings)
- [Manage pagination – Java](https://docs.cloud.google.com/java/docs/pagination)
- [Page interface – Java Client Libraries](https://docs.cloud.google.com/java/docs/reference/gax/latest/com.google.api.gax.paging.Page)
- [Manage long-running operations – Java](https://docs.cloud.google.com/java/docs/long-running-operations)
- [OperationFuture – Java Client Libraries](https://docs.cloud.google.com/java/docs/reference/gax/latest/com.google.api.gax.longrunning.OperationFuture)
- [REST Clients – Spring Framework](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html)
- [WebClient configuration and timeouts – Spring Framework](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html)
- [Cloud Client Libraries for Java](https://docs.cloud.google.com/java/docs/reference)
