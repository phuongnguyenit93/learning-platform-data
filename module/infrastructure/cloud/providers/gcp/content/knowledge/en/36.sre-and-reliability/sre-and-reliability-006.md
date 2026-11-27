# Timeouts, Retries, Backoff, and Circuit Breakers When Calling GCP APIs

## 1. Why Do API Calls Need Fault-Tolerance Mechanisms?

An application running on Cloud Run, GKE, or Compute Engine routinely calls multiple Google Cloud APIs to read configuration, fetch secrets, manage resources, write data, or deploy workloads. These calls traverse the network and depend on quotas, service health, DNS, TLS connections, authentication, client load, and backend load. Even when an API operates normally most of the time, a traffic surge, transient network glitch, or quota hit can cause a batch of requests to fail.

For example, a Cloud Run service receives a request to generate a report. To process a single request, the service calls Cloud Asset Inventory to list resources, Secret Manager to read connection configuration, and Cloud Storage to save the output. If one call hangs, threads or request slots remain occupied. If clients retry too aggressively, request volume spikes just as the service is overloaded. If multiple layers retry simultaneously, a single user action can trigger dozens of API calls.

Four mechanisms are commonly combined to keep this under control:

- **Timeouts** cap how long a single call or an entire operation is allowed to take.
- **Retries** re-attempt a call when an error is likely transient and the operation is safe to repeat.
- **Backoff** spaces out retry attempts to ease pressure on the target service.
- **Circuit breakers** temporarily stop sending requests to a failing or overly slow dependency, then probe it again in a controlled way.

These mechanisms complement one another. A timeout does not fix an error on its own; a retry does not make a broken API healthy; backoff does not replace quota management; a circuit breaker does not cap concurrent requests. Design them around time budgets, operation semantics, and application SLOs.

In the `CLOUD_PROVIDERS_GCP` module, these mechanisms tie directly to operating IAM, VPC, Compute Engine, GKE, Cloud Run, storage, and databases. Each API can have distinct error characteristics, quotas, and retry policies, so do not apply one identical configuration to every service.

## 2. Timeouts and Deadlines

### 2.1. Distinguishing Timeouts and Deadlines

A **timeout** is the maximum duration an operation is allowed to run. A **deadline** is an absolute point in time after which the caller stops waiting for a result. For example, a request starting at 10:00:00 with a 3-second timeout has a deadline of 10:00:03.

In distributed systems, deadlines are usually more useful than resetting a fresh timeout at each hop. Suppose the API gateway allocates 4 seconds for a request, and the application spends 1 second on authentication and cache reads. When calling a Google Cloud API, the application has only about 3 seconds left. If the application sets another 4-second timeout for the downstream call, total latency can exceed the budget the original caller accepted.

An end-to-end deadline should account for:

- Time spent waiting in queues or thread pools.
- Connection setup, DNS, TLS, and authentication time when incurred.
- Processing time for each API attempt.
- Backoff wait time between attempts.
- Time to process results and return the response to the caller.

Do not set overly long timeouts merely to boost success rates. Requests that are no longer useful to the user can still hold connections, memory, and workers while a backend is struggling.

### 2.2. Per-Attempt Timeouts vs. Total Operation Timeouts

When retries are enabled, distinguish two limits:

| Limit | Meaning | Example |
|---|---|---|
| Attempt timeout | Maximum time for a single API call | Max 1 second per call |
| Operation deadline / total timeout | Total time across the initial call, all retries, and backoff | Max 4 seconds for the entire operation |

Suppose an operation has a 4-second budget, a 1-second attempt timeout, and increasing backoff. If the first attempt takes 1 second, the next retry must draw from the remaining budget. Never start a new attempt if the remaining time is too short for it to be useful.

This can be visualized as:

~~~text
Total deadline: 4,000 ms
|--- Attempt 1: 1,000 ms ---|-- Backoff: 200 ms --|
                                      |-- Attempt 2: max 1,000 ms --|
                                                                     |-- remaining budget --|
~~~

This is only an illustrative time allocation; attempt timeouts and retry counts must be tuned to actual latency, request criticality, and SLOs.

### 2.3. Choosing Timeouts with Evidence

There is no single right timeout for every GCP API. Start from how long users or upstream callers can wait, then measure latency under normal load and during incidents. A fast metadata read can use a short timeout; creating snapshots, exporting data, or waiting on long-running operations requires separate timeout and polling designs.

Steps for choosing timeouts:

1. Identify the SLO and end-to-end latency budget for the request.
2. Measure p50, p95, and p99 latency of the API by method, project, and region.
3. Separate connect timeout from request/read timeout if your HTTP client or RPC library supports it.
4. Set attempt timeout above typical latency yet short enough to free resources when the backend hangs.
5. Set total timeout less than or equal to the caller's remaining budget.
6. Test under high load, quota throttling, and slow-backend conditions.
7. Monitor timeout rates and adjust based on data rather than a one-off trial.

Too short a timeout causes false failures when the backend is merely slightly slow. Too long a timeout keeps requests alive too long, increases queued work, and lets a single dependency slowdown cascade across tiers.

### 2.4. Propagating Deadlines and Canceling Work

When a service receives a request and calls another service, it must propagate the remaining time downstream. With gRPC, deadline propagation tells downstream layers when the caller stops waiting. gRPC documentation notes that Java and Go support propagation by default in documented scenarios; HTTP clients or other libraries may need explicit timeout/cancellation propagation.

If the caller cancels the request or the deadline expires, the application should cancel dependent work wherever possible. Stopping the wait on the client while letting background tasks keep running wastes CPU, connections, and quota without producing useful results.

Use a monotonic clock such as `System.nanoTime()` to measure elapsed durations and track in-process budgets. Never use wall-clock time such as `LocalDateTime.now()` for elapsed time because system clocks can shift.

## 3. When Should You Retry?

Retries are appropriate when an error is likely transient, the operation can be repeated safely, and time budget remains. Before retrying, answer three questions:

1. Is the error likely to resolve on its own after a short interval?
2. Could the server have already executed the operation even though the client never received a response?
3. Is there enough time and quota left to try again?

### 3.1. Classifying Errors

The following table is a starting guide. Error codes can differ between HTTP/JSON and gRPC; the specific policy of each API and client library always takes precedence.

| Common HTTP / gRPC | Meaning | Typically Appropriate Handling |
|---|---|---|
| `408` / `DEADLINE_EXCEEDED` | Request or RPC timed out | Retry only if the operation is safe, deadline remains, and there is reason to expect the next try to succeed |
| `429` / `RESOURCE_EXHAUSTED` | Quota or rate limit reached | Slow down, inspect quota info and retry hints from the server/API; apply longer backoff |
| `500` / `INTERNAL` | Server-side internal error | May retry idempotent operations with backoff |
| `502`, `503`, `504` / `UNAVAILABLE` | Gateway or service temporarily unavailable | May retry idempotent operations with bounded retries |
| `400` / `INVALID_ARGUMENT` | Invalid request parameters | Fix the request; retrying unchanged usually will not help |
| `401` / `UNAUTHENTICATED` | Missing or expired credentials | Refresh credentials via a valid mechanism, then retry in a controlled manner if appropriate |
| `403` / `PERMISSION_DENIED` | Insufficient permissions or blocked by policy | Check IAM, Organization Policy, VPC Service Controls, or configuration; do not retry continuously |
| `404` / `NOT_FOUND` | Resource or method does not exist in current context | Verify resource name, scope, and state; retry only when API docs note eventual consistency |
| `409` / `ALREADY_EXISTS`, `ABORTED` | State or transaction conflict | Re-read state; you may need to rerun the full transaction as documented |
| `412` (HTTP) | Precondition failed | Re-read generation, metageneration, or ETag; verify state before deciding the next action |
| `FAILED_PRECONDITION` (gRPC) | Current state fails an operation precondition; in Google API mapping this often maps to HTTP 400 | Fix the condition or resource state; do not retry unchanged |

Do not classify errors by message string alone. Google Cloud warns that error messages can change; rely on HTTP status codes, gRPC status codes, and structured error details such as `google.rpc.ErrorInfo` or `RetryInfo` when provided by the API.

Some Google Cloud guidance for Service Usage and Service Infrastructure recommends retrying with exponential intervals plus randomness, noting minimum intervals of 30 seconds for `429` quota errors and 1 second for `500`/`503`. That guidance applies to the APIs/scenarios covered in those documents, not as a universal number across every GCP API. If a specific API returns `Retry-After`, `RetryInfo`, or different quota documentation, follow that guidance.

### 3.2. Not Every Timeout Means the Request Never Ran

A client sends a resource-creation command, the server executes it successfully, and the response is lost on the return path. The client observes only a timeout. If the client resends the creation command without deduplication, it can create two resources or two jobs.

For operations with side effects, determine state before retrying. Options include:

- Using an idempotency key or request ID if the API supports it.
- Using preconditions such as generation, metageneration, or ETag.
- Recording the operation ID to query long-running operations.
- Reading resource state before resending a create/update command.
- Designing operations as upserts or conditional overwrites when supported by the API.

Do not assume every Google Cloud API supports idempotency keys. Read the contract for the specific method.

## 4. Idempotency: The Safety Prerequisite Before Retrying

An operation is **idempotent** if executing it multiple times under the same conditions produces the same final state as executing it once. For example, reading a resource or listing items is typically safe to repeat. Creating a new notification or publishing a message may create another entity on every call, so it is not inherently idempotent.

### 4.1. Categorizing Operations

| Operation Type | Example | Retry Principle |
|---|---|---|
| Read-only | GET, list, get metadata | Usually safe to retry on transient errors |
| Set state to a fixed value | Set configuration to `enabled=true` | Can be idempotent if API semantics guarantee it |
| Create | Create VM, subscription, notification | Retry only with a request ID, precondition, or way to look up the outcome |
| Increment / append | Increment counter, append event | Do not retry blindly; requires deduplication or a sequence key |
| Delete | Delete resource | Check semantics when already deleted; use version/precondition if needed |
| Long-running operation | Export, import, snapshot, deploy | Distinguish retrying the start command from retrying polling |

### 4.2. Using Preconditions in Cloud Storage

Cloud Storage illustrates clearly why idempotency matters. Several object update operations are safe only when requests carry appropriate preconditions. For instance, `ifGenerationMatch` can bind an operation to an expected generation; `ifMetagenerationMatch` or ETag can protect metadata updates. If the resource state has changed, the precondition fails instead of silently overwriting a newer version.

Illustrative Java example writing an object only if it does not already exist:

~~~java
BlobId blobId = BlobId.of(bucketName, objectName);
BlobInfo blobInfo = BlobInfo.newBuilder(blobId).build();

Blob created = storage.create(
    blobInfo,
    payload,
    Storage.BlobTargetOption.doesNotExist()
);
~~~

`doesNotExist()` attaches the corresponding precondition so the operation will not overwrite an existing object. If a response is lost, a retry may encounter a precondition failure because the first attempt already created the object. In that case, read metadata and verify generation/content rather than continuing to retry creation.

Option names and precondition passing differ across libraries and versions. Check your client's API reference before applying.

### 4.3. Long-Running Operations

Some APIs return an operation instead of an immediate final result. Separate two phases:

1. **Start operation:** trigger an export, import, snapshot, or long job. Handle the case where the request succeeds on the server but the response containing the operation name is lost.
2. **Poll operation:** query the status of an existing operation. Polling is typically a read operation, can use its own backoff, and must never start a new operation.

If you have an operation ID, persist it durably so tracking can resume after a process restart. Never resend the start command simply because one poll call timed out.

## 5. Exponential Backoff and Jitter

### 5.1. Exponential Backoff

When many clients retry immediately, a recovering server gets hit with extra load. Exponential backoff lengthens the wait after each failure:

\[
d_n = \min(d_{\max}, d_0 \times m^n)
\]

Where:

- \(d_0\): initial wait duration.
- \(m\): multiplier, usually greater than 1.
- \(n\): retry attempt index, starting at 0.
- \(d_{\max}\): upper bound on wait duration.

Example with \(d_0=200\) ms, \(m=2\), \(d_{\max}=2\) seconds:

| Retry Attempt | Backoff Before Jitter |
|---:|---:|
| 1 | 200 ms |
| 2 | 400 ms |
| 3 | 800 ms |
| 4 | 1,600 ms |
| 5 onward | 2,000 ms |

The upper cap keeps wait times from growing unboundedly. Capping retry counts and total deadlines ensures operations terminate in a controlled manner.

### 5.2. Jitter to Avoid Synchronized Retries

If thousands of instances retry after exactly 1, 2, and 4 seconds, they create synchronized load waves. This phenomenon is commonly called a thundering herd. **Jitter** adds randomness to wait times so clients spread out their retry attempts.

A common variant is full jitter:

\[
d_{\text{actual}} = random(0, d_n)
\]

For example, if the backoff for a retry is 800 ms, the client picks a random duration between 0 and 800 ms. This is one illustrative algorithm; libraries may use other jitter variants. Google Cloud Client Libraries for Java always enable jitter in their retry mechanism, and their documentation describes a randomized delay between 1 and the computed retry delay value.

Do not add another external jitter layer if the client library already applies backoff and jitter, unless you clearly understand how the two layers interact.

### 5.3. Combining Backoff with Retry-After and Quotas

When the server returns `Retry-After` or structured retry information, prioritize the server-requested wait time. If the server indicates quota will replenish after an interval, retrying sooner only increases errors and can keep consuming quota.

For quota errors, backoff must be long enough to genuinely reduce request rate. At the same time, check:

- Is quota limited by project, user, method, or region?
- Is a single batch job or multiple services sharing the quota?
- Can requests be coalesced, results cached, or a batch API used?
- Should concurrency be reduced or run schedules adjusted?
- Should a quota increase be requested after optimizing load?

Retry is a transient-fault recovery mechanism; it is not a fix for chronic quota exhaustion.

## 6. Retry Limits and Retry Budgets

### 6.1. Per-Request Limits

A logical operation should have explicit bounds:

- Maximum attempt count, including the initial call.
- Total timeout or deadline.
- Maximum backoff.
- List of retryable errors.
- Idempotency conditions.
- Stop condition when the caller cancels or the deadline expires.

Never retry infinitely. Once the budget is exhausted, return a handleable error to the caller, offload work to a queue, or serve a fallback result if business rules permit.

### 6.2. Why Multi-Layer Retries Amplify Load

Suppose the frontend, backend, and an SDK layer each allow 3 retries after the initial call. One original operation can generate up to:

\[
4 \times 4 \times 4 = 64 \text{ calls at the lowest layer}
\]

When the backend is already overloaded, these extra calls make matters worse. Google SRE highlights retry amplification as a factor capable of turning a small error rate into a cascading failure.

Designate a single layer as the **retry owner** for each call. If the GAX client library already retries RPCs, the business layer should not blindly retry the same failure. If the business layer must retry a larger workflow composed of multiple RPCs, explicitly budget and track completion state for each step.

### 6.3. Process- or Service-Level Retry Budgets

A retry budget caps the total number of retries a process or service may issue over a period of time. It can be expressed as:

- Maximum retries per minute.
- Ratio of retries to original requests.
- A token bucket allowing a fixed burst of retries and refilling over time.
- Separate retry limits per API method or quota domain.

When the budget runs out, new requests stop retrying automatically. This protects backends and quotas during spreading failures. Budget levels should be chosen through load testing and SLOs; a fixed number will not fit every service.

## 7. Circuit Breakers

### 7.1. What Problem Do Circuit Breakers Solve?

Retries help when errors are transient. However, if a dependency fails continuously or latency spikes sharply, continuing to send requests merely ties up client connections and workers while adding load to the backend. A circuit breaker tracks dependency call outcomes and temporarily short-circuits requests when error rates or slow-call rates cross thresholds.

A circuit breaker typically has three states:

~~~mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> OPEN: Errors or slow calls exceed threshold
    OPEN --> HALF_OPEN: Wait duration expires
    HALF_OPEN --> CLOSED: Probes succeed
    HALF_OPEN --> OPEN: Probes continue to fail
~~~

- **CLOSED:** requests pass through; the breaker records outcomes and durations.
- **OPEN:** requests fail fast without calling the dependency; the app can return an error, serve cached data, or enqueue work.
- **HALF_OPEN:** after a wait duration, only a limited number of probe calls are allowed through to test whether the dependency has recovered.

Some libraries add states such as `METRICS_ONLY`, `DISABLED`, or `FORCED_OPEN`. Their exact semantics and operation depend on the library.

### 7.2. Configuring a Circuit Breaker

Key parameters include:

| Parameter | Purpose |
|---|---|
| Sliding window | Number of recent requests or time span used to compute rates |
| Minimum number of calls | Minimum sample size before evaluating error rates |
| Failure rate threshold | Failure percentage that trips the breaker to OPEN |
| Slow call duration threshold | Duration above which a call counts as slow |
| Slow call rate threshold | Slow-call percentage that opens the breaker |
| Wait duration in OPEN | How long the breaker stays OPEN before permitting probes |
| Permitted calls in HALF_OPEN | Number of probe calls allowed |
| Record/ignore exceptions | Classifies which errors count toward failure rate |

Do not configure an overly sensitive breaker. A low-traffic service may lack enough samples for meaningful error ratios; authentication or invalid-argument errors do not reflect dependency health. Record network errors, timeouts, and transient server errors; separate quota errors, business errors, and configuration errors.

Circuit breakers are typically created per dependency or per group of methods sharing a failure domain. Never share one global breaker across all Google Cloud APIs: Cloud Storage may be healthy while Compute Engine has an outage. Tripping a global breaker would block healthy services too.

### 7.3. A Circuit Breaker Is Not a Bulkhead or Rate Limiter

These three mechanisms serve different purposes:

- A circuit breaker stops calling a dependency showing signs of unhealthiness.
- A rate limiter caps the rate at which requests are sent.
- A bulkhead caps concurrent operations so one slow dependency cannot exhaust all application workers or connections.

A circuit breaker does not limit concurrent in-flight calls on its own. Resilience4j documentation also notes that its sliding window is not a concurrency limit; to limit concurrent tasks, use a Bulkhead.

## 8. Combining Timeouts, Retries, Backoff, and Circuit Breakers

A sensible execution order for a logical operation:

1. The caller establishes an end-to-end deadline.
2. The circuit breaker checks whether the dependency is OPEN.
3. If permitted, the client library executes an attempt with a timeout not exceeding remaining budget.
4. If the failure is retryable and the operation is idempotent, the retry engine waits with backoff and jitter.
5. Before each attempt, check the deadline, retry budget, and cancellation status.
6. The final outcome is recorded into the circuit breaker and telemetry.
7. On failure, the business layer decides whether to return an error, serve cache, enqueue, or enter degraded mode.

When a circuit breaker wraps a logical call that performs internal retries, the breaker typically records the final outcome of the entire operation. If placed inside a retry decorator, the breaker may record every individual attempt and trip open while retries of the same operation are still in progress. Choose the ordering according to your measurement goals and test the real behavior.

Do not stack multiple retry layers. For example, if GAX already performs 4 attempts, an outer retry wrapper can multiply total calls severalfold. Inspect default client settings before adding retries in the application layer.

## 9. Configuring Retries in Google Cloud Java Client Libraries

### 9.1. Understand Defaults Before Changing Them

Cloud Client Libraries for Java use GAX to configure retries. Default retries are chosen by each service team per RPC. A service may enable retries for some methods and disable them for others. Retryable status codes and timing bounds live in the generated `*StubSettings` classes.

`RetrySettings` typically includes these parameters:

- `initialRetryDelayDuration`: initial wait time.
- `retryDelayMultiplier`: backoff growth factor.
- `maxRetryDelayDuration`: maximum wait cap.
- `initialRpcTimeoutDuration`: timeout for the first attempt.
- `rpcTimeoutMultiplier`: timeout multiplier across attempts.
- `maxRpcTimeoutDuration`: maximum per-attempt timeout cap.
- `totalTimeoutDuration`: maximum total time for the operation.
- `maxAttempts`: maximum number of calls.

GAX separates per-RPC attempt limits from total operation limits. When configuring retries, always set `totalTimeoutDuration` or `maxAttempts` to prevent unbounded retries. Jitter is enabled in the retry mechanism of Cloud Client Libraries for Java.

### 9.2. Example Configuration for an RPC

The following snippet illustrates retry configuration for the `listAssets` RPC of the Cloud Asset API. This is an example for configuring a specific method; actual retryable codes and durations must be verified against the documentation for the API you are calling.

~~~java
import com.google.api.gax.retrying.RetrySettings;
import com.google.api.gax.rpc.StatusCode;
import com.google.cloud.asset.v1.AssetServiceClient;
import com.google.cloud.asset.v1.AssetServiceSettings;
import com.google.cloud.asset.v1.AssetServiceStubSettings;
import com.google.common.collect.ImmutableSet;

import java.time.Duration;

RetrySettings retrySettings =
    RetrySettings.newBuilder()
        .setInitialRetryDelayDuration(Duration.ofMillis(200))
        .setRetryDelayMultiplier(2.0)
        .setMaxRetryDelayDuration(Duration.ofSeconds(2))
        .setInitialRpcTimeoutDuration(Duration.ofSeconds(2))
        .setRpcTimeoutMultiplier(1.0)
        .setMaxRpcTimeoutDuration(Duration.ofSeconds(2))
        .setTotalTimeoutDuration(Duration.ofSeconds(8))
        .setMaxAttempts(4)
        .build();

AssetServiceStubSettings.Builder stubBuilder =
    AssetServiceStubSettings.newBuilder();

stubBuilder
    .listAssetsSettings()
    .setRetrySettings(retrySettings)
    .setRetryableCodes(
        ImmutableSet.of(StatusCode.Code.UNAVAILABLE)
    );

AssetServiceSettings settings =
    AssetServiceSettings.create(stubBuilder.build());

try (AssetServiceClient client = AssetServiceClient.create(settings)) {
    // Call client.listAssets(request) with an appropriate request and scope.
}
~~~

In this example, `UNAVAILABLE` illustrates a transient service error. Do not copy this exact retryable code list to every RPC. If a method can return quota exhaustion, consult its status codes, quota guidance, and defaults. For non-idempotent operations, never enable retries simply because an error code looks transient.

### 9.3. Inspecting Actual Client Configuration

Before overriding configuration:

1. Identify the exact Cloud Client Library and GAX versions in use.
2. Open the client's generated `*StubSettings` to inspect default retryable codes and `RetrySettings`.
3. Determine whether the method is idempotent, conditionally idempotent, or non-idempotent.
4. Compare total timeout against the incoming request deadline.
5. Check whether the application, HTTP transport, or service mesh adds extra retries.
6. Verify actual call counts via logs or metrics; do not infer attempt counts solely from configuration because jitter and total timeout may prevent the final attempt from running.

For the Cloud Storage Java client, the documentation specifies its own retry strategy: non-idempotent calls are not retried automatically; certain conditionally idempotent operations are retried only when appropriate preconditions are set. For instance, `ifGenerationMatch`, `ifMetagenerationMatch`, or ETag may be required conditions for certain operations.

## 10. Circuit Breakers in Java Applications

Cloud Client Libraries provide retry settings for RPCs. Circuit breakers are typically implemented at the application layer using a resilience library such as Resilience4j. A breaker protects the application from repeatedly calling a slow or failing dependency; it does not replace GAX retry settings.

Illustrative configuration example:

~~~java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;

import java.time.Duration;
import java.util.function.Supplier;

CircuitBreakerConfig breakerConfig =
    CircuitBreakerConfig.custom()
        .slidingWindowSize(20)
        .minimumNumberOfCalls(10)
        .failureRateThreshold(50)
        .slowCallRateThreshold(50)
        .slowCallDurationThreshold(Duration.ofSeconds(2))
        .waitDurationInOpenState(Duration.ofSeconds(15))
        .permittedNumberOfCallsInHalfOpenState(3)
        .recordException(this::isTransientGcpFailure)
        .ignoreExceptions(IllegalArgumentException.class)
        .build();

CircuitBreaker breaker =
    CircuitBreaker.of("cloud-asset-api", breakerConfig);

// The GAX client already handles retries inside the logical call.
Supplier<MyResult> protectedCall =
    CircuitBreaker.decorateSupplier(
        breaker,
        () -> invokeCloudAssetApi()
    );

MyResult result = protectedCall.get();
~~~

`MyResult`, `isTransientGcpFailure()`, and `invokeCloudAssetApi()` represent application types and logic. In a real implementation, classify exceptions by GAX/HTTP status code and ignore validation or business errors that do not reflect dependency health.

The sample config uses a sliding window of 20 calls, minimum 10 samples, 50% thresholds, and 3 probes in HALF_OPEN. These are illustrative values only, not production defaults. Tune based on traffic, latency, SLOs, and API recovery times.

If using Resilience4j Retry outside GAX, decide clearly which layer owns retries. Do not let both layers retry the same error without a shared limit.

## 11. Hands-On Scenario: Cloud Run Calling Cloud Asset API

A Cloud Run service receives requests to generate an inventory report for a project. The service calls the Cloud Asset API to list resources and saves the result to Cloud Storage. When request volume increases, the Cloud Asset API starts returning `429` and occasional `UNAVAILABLE` responses.

### Symptoms

- Endpoint p95 latency jumps from under one second to several seconds.
- `429` rate rises alongside the number of Cloud Run instances.
- Request count to Cloud Asset API far exceeds report-generation requests.
- Many requests keep waiting even after users close the page or deadlines expire.
- Retries amplify request counts, making quota recovery harder.

### Remediation Approach

1. **Measure the dependency properly:** separate Cloud Asset API latency and error rates from Cloud Run endpoint latency. Record method, project, status code, attempt count, and trace ID.
2. **Set deadlines:** establish the report's end-to-end budget. Subtract time already spent before calling Cloud Asset API and bound the operation's total timeout.
3. **Classify errors:** retry `UNAVAILABLE` when read operations are safe; for `429`, lower concurrency, check quota guidance, and apply API-documented wait intervals.
4. **Shed or reduce load:** cache inventory data if freshness allows, batch scheduled runs, or move report generation to a background job instead of holding HTTP requests open.
5. **Check idempotency:** `listAssets` is a read operation and safe to repeat; if the workflow starts an export operation, persist the operation name so lost responses do not spawn duplicate jobs.
6. **Bound retries:** set max attempts, total timeout, and a retry budget. Only one layer owns RPC retries.
7. **Trip the circuit breaker:** if failure or slow-call rates cross thresholds, pause new calls to Cloud Asset API. Return an in-progress status, serve cached data, or enqueue the job per business requirements.
8. **Controlled probing:** when the breaker enters HALF_OPEN, allow a small number of read probes. If they succeed consistently, close the breaker; if errors persist, reopen it.
9. **Verify recovery:** monitor 429/503 rates, retry rates, p95/p99 latency, and in-flight requests. Raise concurrency only when quotas and backends have sufficient headroom.

### Expected Outcome

Cloud Run no longer holds requests indefinitely; API call counts stay bounded; retries are spread over time; quotas are not amplified across multiple layers; failing dependencies are isolated; and users receive responses or processing statuses within the defined budget.

## 12. Operational Monitoring and Alerting

You cannot evaluate retries and circuit breakers solely by checking whether the outer endpoint returns HTTP 200. Measure attempt counts, latencies, and dependency states as well.

Metrics to monitor:

| Metric | Operational Meaning |
|---|---|
| Request count by API/method/status | Identifies rising traffic and error codes |
| Attempt count / retries per logical operation | Detects retry amplification |
| First-attempt success rate | Measures stability prior to retries |
| Attempt latency and total operation latency | Distinguishes one slow attempt from multiple attempts |
| Timeouts and `DEADLINE_EXCEEDED` | Spots mismatched time budgets or slow dependencies |
| `429` / `RESOURCE_EXHAUSTED` | Tracks quota and rate limits |
| `5xx` / `UNAVAILABLE` | Tracks transient service failures |
| Circuit breaker state and rejected calls | Shows when a dependency is isolated |
| Retry budget remaining / retries denied | Verifies protective limits are actively working |
| In-flight calls and queue depth | Detects occupied workers or connections |

Break down metrics by service, method, project, and region where cardinality allows. Never put user IDs, high-cardinality resource IDs, or secrets into metric labels. Use structured logs and traces to follow a logical operation across multiple attempts.

Cloud Monitoring can chart metrics and alert when error rates, latency, quota usage, or rejected calls cross thresholds. OpenTelemetry can add spans per attempt, `retry.attempt` attributes, breaker states, and backoff durations. Never log access tokens, API keys, secret contents, or sensitive payloads.

Alerts should focus on SLO impact—for example, rising deadline-exceeded ratios, steadily rising retry ratios, near-exhausted quotas, prolonged OPEN breaker states, or a dependency failing to recover across multiple HALF_OPEN cycles. Occasional isolated retries are normal; rapidly rising retries alongside rising latency and error rates warrant investigation.

## 13. Testing Fault Tolerance

Before releasing, test plausible failure scenarios:

- API responds slower than the attempt timeout.
- Connection resets before a response arrives.
- Server completes work but the response is lost.
- API returns `429`, `500`, `503`, or non-retryable status codes.
- Caller cancels the request mid-backoff.
- Deadline expires before the next attempt can run.
- Retry budget is exhausted.
- Circuit breaker transitions to OPEN when the dependency fails and HALF_OPEN during recovery.
- One instance fails while other instances continue serving.
- Client restarts while tracking a long-running operation.

Verify that retries do not duplicate side effects, do not exceed deadlines, and do not create synchronized request waves. For breakers, verify validation/permission errors do not trip the circuit mistakenly, and one failing API does not block independent GCP APIs.

Use mock servers, fault injection, or test environments to simulate failures. During load tests, observe both the calling system and the dependency; a test measuring only frontend responses can miss surging backend call counts.

## 14. Design Checklist for a GCP API Call

Before shipping an API call to production, confirm:

- [ ] End-to-end deadline and remaining time budget for the API call are defined.
- [ ] Attempt timeout and total timeout are configured separately without exceeding the caller's deadline.
- [ ] Retryable errors are classified per the exact API and RPC documentation.
- [ ] Operation is classified as idempotent, conditionally idempotent, or non-idempotent.
- [ ] Request IDs, preconditions, ETags, or state lookups prevent duplicate creation where needed.
- [ ] Exponential backoff has an upper bound and jitter.
- [ ] `Retry-After`, `RetryInfo`, quota guidance, or API wait intervals are respected.
- [ ] Max attempts, total timeout, and a retry budget are enforced.
- [ ] Only one layer owns retries for each RPC.
- [ ] Circuit breaker records appropriate errors and is scoped per dependency.
- [ ] Rate limiter or bulkhead is present when rate and concurrency control are needed.
- [ ] Fallback or handling path exists when the breaker is OPEN.
- [ ] Metrics, logs, and traces capture both logical operations and individual attempts.
- [ ] Timeouts, lost responses, quotas, retries, and breaker recovery have been tested.

## 15. Self-Check Questions

1. Why can resetting a 5-second timeout at every tier cause a request to exceed a user's 5-second deadline?
2. When a Cloud API returns `429`, why can increasing retry counts worsen quota exhaustion?
3. A resource-creation request timed out, yet the server may have completed it. What mechanisms should you use before resending?
4. Which two distinct problems do exponential backoff and jitter solve?
5. Why can retrying simultaneously in the frontend, backend, and GAX client generate far more calls than expected?
6. How should an OPEN circuit breaker handle new requests, and when does it transition to HALF_OPEN?
7. Why cannot a circuit breaker replace a bulkhead or rate limiter?
8. When should the GAX client library own retries, and when does an application-layer workflow need to manage its own retries?
9. For a long-running operation, why is retrying the start command different from retrying the poll command?
10. Which metrics help distinguish a true dependency outage from retry amplification?

## References

- [Configure client-side retries for Java Cloud Client Libraries](https://docs.cloud.google.com/java/docs/client-retries)
- [GAX RetrySettings reference](https://docs.cloud.google.com/java/docs/reference/gax/latest/com.google.api.gax.retrying.RetrySettings)
- [Cloud Storage retry strategy](https://docs.cloud.google.com/storage/docs/retry-strategy)
- [Cloud Storage request preconditions](https://docs.cloud.google.com/storage/docs/request-preconditions)
- [Service Usage API troubleshooting and retry intervals](https://docs.cloud.google.com/service-usage/docs/troubleshooting)
- [Troubleshoot the Cloud Monitoring API](https://docs.cloud.google.com/monitoring/api/troubleshooting)
- [gRPC deadlines](https://grpc.io/docs/guides/deadlines/)
- [gRPC retry](https://grpc.io/docs/guides/retry/)
- [Google SRE Book: Addressing Cascading Failures](https://sre.google/sre-book/addressing-cascading-failures/)
- [Resilience4j CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker)
