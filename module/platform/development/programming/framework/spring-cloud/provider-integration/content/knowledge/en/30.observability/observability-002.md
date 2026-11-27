# Measuring latency, error rate, throttling, and retry counts

## 1. Context and objectives

In the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, we practice integrating Spring Boot with managed services from **AWS, Azure, and Google Cloud**, including storage, messaging, data, identity, permissions, and secret protection. When bringing cloud SDKs into production applications, the question is not only whether a request succeeded or failed. Operations teams also need to know how long requests take, how frequently errors occur, whether services are rate-limiting requests, and how many times the SDK had to retry.

For example, an API receives a request to generate a report. It reads metadata from object storage, queries a database, and then sends a message to a worker. The user sees the API return success, yet behind the scenes the SDK may have retried twice due to throttling. If you only measure HTTP duration at the controller, operations will not know that the cloud provider is returning 429/503 errors, backoff wait time is rising, or retries are masking a degrading dependency.

This lesson explains how to measure four critical signals:

- **Latency:** how long a cloud operation takes, including retries when measured at the logical operation level.
- **Error rate:** how many operations fail out of the total number of operations.
- **Throttling:** how many operations are rate-limited or temporarily rejected by the service due to quota/capacity.
- **Retries:** how many additional attempts the SDK or application performed before succeeding or ultimately failing.

After this lesson, you will be able to:

- Use Micrometer Timer, Counter, and histograms in Spring Boot.
- Define metrics that are comparable across AWS, Azure, and Google Cloud.
- Distinguish logical call, attempt, retry, and backoff duration.
- Classify throttling by HTTP status, service error code, or gRPC status.
- Build dashboards/PromQL queries for p95 latency, error rate, throttle rate, and retry rate.
- Avoid high metric cardinality, double counting, and retry storms.

## 2. Four signals and how to interpret them

A logical operation is a business action the application wants to complete, such as `upload_document` or `send_job`. An SDK may issue multiple network attempts for the same logical operation.

~~~mermaid
flowchart TD
    A[Logical operation: upload document] --> B[Attempt 1]
    B -->|429 / throttled| C[Backoff]
    C --> D[Attempt 2]
    D -->|503 / transient| E[Backoff]
    E --> F[Attempt 3]
    F -->|Success| G[Logical operation completed]
    G --> H[Logical-call latency]
    B --> I[Attempt metrics]
    D --> I
    F --> I
    C --> J[Backoff duration]
    E --> J
~~~

| Signal | Typical unit/metric | Operational question |
|---|---|---|
| Latency | seconds, histogram, and p50/p95/p99 | How long must the user or worker wait? |
| Error rate | errors / total logical calls | What fraction of operations fail to complete? |
| Throttling | throttled errors / total calls or attempts | Are requests constrained by quota/rate limit/capacity? |
| Retries | extra retries / logical calls | How heavily must the SDK retry? |

Do not collapse these four signals into a single UP/DOWN state. A dependency can still succeed on 99.9% of requests while p99 latency spikes due to retries; or error rate can stay low while throttle counts climb near quota limits.

## 3. Measuring latency at the right boundary

### 3.1. Logical-call latency vs. attempt latency

There are two ways to measure duration:

- **Logical-call latency:** from when the application invokes the SDK until the SDK returns its final result. This duration typically includes serialization, networking, attempts, backoff, and deserialization.
- **Attempt latency:** the duration of each individual request sent to the cloud provider. A logical call may have one or more attempts.

Measuring logical-call latency answers “how long did the application wait to finish the operation?”. Attempt latency helps distinguish slow provider/network responses from time spent waiting on retries.

Example:

| Component | Duration |
|---|---:|
| Attempt 1 | 120 ms |
| Backoff 1 | 200 ms |
| Attempt 2 | 180 ms |
| Backoff 2 | 400 ms |
| Attempt 3 | 100 ms |
| **Logical-call latency** | **1,000 ms** |

If you only measure the final attempt, the dashboard reports 100 ms and hides the fact that the application actually waited one full second.

### 3.2. Using Timer instead of building a custom duration Gauge

Micrometer Timer is built for timed operations. A Timer records at least total time and event count; the registry can additionally publish max, histograms, or percentiles depending on configuration.

Example timing a block of code:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

@Component
public class StorageOperationTimer {
    private final MeterRegistry registry;

    public StorageOperationTimer(MeterRegistry registry) {
        this.registry = registry;
    }

    public void upload(Runnable operation) {
        Timer timer = Timer.builder("cloud.dependency.duration")
                .tag("provider", "azure")
                .tag("service", "blob")
                .tag("operation", "upload")
                .register(registry);

        timer.record(operation);
    }
}
~~~

In a real application, use stable operation names such as upload, download, send_message, or get_object rather than method names containing IDs or resource names. If you want to include internal SDK retry time, wrap the Timer around the **entire SDK call**.

### 3.3. Histograms and percentiles

Commonly used percentiles:

- **p50:** the experience of the median request.
- **p95:** 95% of operations finish within this time or faster.
- **p99:** the slow tail, often revealing retries, network instability, or contention.

Client-side percentiles computed independently by each instance cannot be accurately aggregated across multiple Pods. With Prometheus, use histograms with buckets to compute percentiles from aggregated data. Micrometer supports publishPercentileHistogram() and serviceLevelObjectives(...).

Example configuring buckets around an operation's target SLOs:

~~~java
import java.time.Duration;

Timer timer = Timer.builder("cloud.dependency.duration")
        .tag("provider", "aws")
        .tag("service", "s3")
        .tag("operation", "get_object")
        .publishPercentileHistogram()
        .serviceLevelObjectives(
                Duration.ofMillis(100),
                Duration.ofMillis(250),
                Duration.ofMillis(500),
                Duration.ofSeconds(1),
                Duration.ofSeconds(2))
        .register(registry);
~~~

Choose buckets based on realistic SLOs and operation types. A small get_object, upload_large_file, and send_message have different latency distributions; do not apply one latency threshold to every operation.

## 4. Measuring error rate with the right denominator

### 4.1. Distinguishing final failures from retried-and-recovered failures

Suppose 1,000 logical calls experience:

- 20 calls failing on the first attempt, then succeeding on SDK retry.
- 5 calls failing after exhausting retries.

The final error rate at the logical-call level is 5 / 1,000 = 0.5%. However, those 20 calls still generated extra load, increased latency, and may signal a degrading dependency. Therefore, measure all three:

- **Final error rate:** failed logical calls / total logical calls.
- **Attempt error rate:** failed request attempts / total attempts.
- **Retry rate:** extra retries / total logical calls.

Do not report attempt error counts as the end-user error rate if the SDK still completed the operation successfully.

### 4.2. Classifying errors into stable categories

A shared set of categories across providers:

| Category | Example | Meaning |
|---|---|---|
| throttled | AWS throttling error, Azure 429, Google RESOURCE_EXHAUSTED | Service is enforcing rate limits or quota |
| timeout | Connect/read/API call timeout | Result not received within the deadline |
| network | DNS, connection reset, I/O | Transport or connectivity error |
| authorization | IAM/RBAC/permission denied | Invalid identity or insufficient permissions |
| not_found | Bucket/container/queue/object does not exist | Missing resource or invalid path |
| server | 5xx/service unavailable | Server-side failure at the service |
| conflict | Conditional write conflict, version/ETag conflict | Resource state changed concurrently |
| other | Remaining errors | Needs further investigation |

Error classification should rely on **service error codes and SDK exceptions**, not HTTP status alone. Some AWS services return throttling errors with HTTP 400; Azure can return 503 Server Busy; Google APIs can return gRPC RESOURCE_EXHAUSTED.

### 4.3. Counting errors with Counter

A Counter increases monotonically with event occurrences. Monitoring backends typically compute its rate over a time window to derive error rates.

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class CloudErrorMetrics {
    private final MeterRegistry registry;

    public CloudErrorMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordFinalError(
            String provider,
            String service,
            String operation,
            String errorType) {

        registry.counter(
                "cloud.dependency.errors",
                "provider", provider,
                "service", service,
                "operation", operation,
                "error_type", errorType)
            .increment();
    }
}
~~~

Only pass bounded values such as azure, blob, upload, timeout, or throttled. Never pass exception messages or full URLs into tags.

## 5. Throttling: distinguishing it from ordinary server errors

**Throttling** occurs when a service limits the request rate or resource consumption of the caller. Causes can include:

- Exceeding request rate or quota.
- Too many concurrent requests.
- Exceeding limits on a specific partition, namespace, table, or resource.
- The service protecting capacity or experiencing high load.

Throttling is not synonymous with every HTTP 429/503 across all services. Keep both error_type=throttled and normalized status codes/groups for analysis.

| Provider | Observable signals | Notes |
|---|---|---|
| **AWS** | SDK error type Throttling, service error codes like ThrottlingException, RequestLimitExceeded; some services have specific codes like SlowDown | Do not filter on HTTP 429 alone; use service error codes/SDK classification |
| **Azure** | HTTP 429 Too Many Requests; some services return 503 Server Busy or service-specific codes | Check Retry-After or corresponding retry headers; distinguish quota from transient errors |
| **Google Cloud** | gRPC RESOURCE_EXHAUSTED, HTTP 429, or quota-specific errors | UNAVAILABLE is transient but does not automatically mean throttling |

### 5.1. Metrics for throttling

You can define dedicated Counters:

~~~java
registry.counter(
        "cloud.dependency.throttled.calls",
        "provider", "azure",
        "service", "blob",
        "operation", "upload")
    .increment();
~~~

Standardize the rule: does the counter increment when **a logical call or an attempt** is throttled? It is recommended to record them separately:

- cloud.dependency.throttled.calls: number of logical calls with at least one throttle response.
- cloud.dependency.throttled.attempts: total number of throttled attempts.

These two metrics answer different questions. If you keep only one metric, document its definition clearly and never mix both counting rules.

### 5.2. Tracking Retry-After

When a service sends Retry-After or a corresponding retry header, the client should respect that delay according to the SDK/service guidance. Without explicit guidance, exponential backoff with jitter helps spread retry requests evenly.

Do not retry immediately after a 429. Doing so adds pressure to an already constrained quota or capacity. Also cap attempt count or total operation time; unbounded retries can hold threads and requests indefinitely.

## 6. Retries: counting extra attempts and backoff duration

### 6.1. Attempts vs. retries

If a logical call has three attempts:

- Attempt 1 is the initial attempt.
- Attempts 2 and 3 are two retries.
- Total attempts = 3; retry count = 2.

This definition matters when building dashboards. Do not name a metric retry_count and increment it on the first attempt.

### 6.2. What should be measured

| Metric | Meaning |
|---|---|
| cloud.dependency.calls | Total logical calls |
| cloud.dependency.retries | Extra attempts after the initial attempt |
| cloud.dependency.retry.exhausted | Logical calls that exhausted retries and still failed |
| cloud.dependency.backoff.duration | Total wait time between attempts |
| cloud.dependency.attempts | Total request attempts if exposed by the SDK/pipeline |
| cloud.dependency.duration | Logical-call completion time, including retries/backoff if timed around the SDK call |

Not every SDK exposes the same attempt/retry metrics. Distinguish metrics controlled by the **application** from telemetry provided by the **SDK/provider**.

### 6.3. Retry policy and backoff

A retry policy typically defines:

- Which errors are retryable: throttling, transient timeouts, certain 5xx or transport errors.
- Which errors should not be retried: permission denied, resource not found, malformed payload, validation errors.
- Maximum attempts or maximum total duration.
- Exponential backoff, max delay cap, and jitter.
- How Retry-After is handled.
- Behavior upon retry exhaustion: return error, enqueue for later, or trigger a recovery workflow.

Illustrative backoff schedule:

~~~text
Initial delay = 100 ms
Multiplier = 2
Maximum delay = 1 s

Retry 1: around 100 ms + jitter
Retry 2: around 200 ms + jitter
Retry 3: around 400 ms + jitter
Retry 4: capped around 1 s + jitter
~~~

This is only an example, not the default of every SDK. Use the provider's built-in retry strategy when appropriate and avoid wrapping it in another unbounded retry loop in the service layer.

## 7. Setting up Micrometer in Spring Boot

Spring Boot Actuator integrates Micrometer and auto-configures MeterRegistry when a matching registry implementation is on the classpath. Add Actuator:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

If exporting metrics to Prometheus, add the registry:

~~~xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
~~~

Example configuration:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  endpoint:
    health:
      show-details: never
  metrics:
    tags:
      application: provider-integration
~~~

Useful endpoints:

- /actuator/metrics: inspect meters in the registry for diagnostics.
- /actuator/prometheus: scrape metrics when the Prometheus registry is on the classpath and the endpoint is exposed.
- /actuator/health: health endpoint, not a substitute for metrics.

Expose only necessary endpoints inside an administrative network. Do not expose env, configprops, or sensitive endpoints to the Internet.

## 8. Building a unified metric wrapper across cloud providers

A shared metrics layer enables cross-provider comparison, while each SDK adapter still classifies errors using provider-specific codes. The example below records logical-call latency, logical calls, final errors, and throttled calls.

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import java.util.function.Function;
import java.util.function.Supplier;
import org.springframework.stereotype.Component;

@Component
public class CloudOperationMetrics {
    private final MeterRegistry registry;

    public CloudOperationMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public <T> T record(
            String provider,
            String service,
            String operation,
            Supplier<T> action,
            Function<RuntimeException, Failure> classifier) {

        long started = System.nanoTime();
        String outcome = "success";

        try {
            return action.get();
        } catch (RuntimeException ex) {
            outcome = "error";
            Failure failure = classifier.apply(ex);

            Counter.builder("cloud.dependency.errors")
                    .tags(
                            "provider", provider,
                            "service", service,
                            "operation", operation,
                            "error_type", failure.errorType(),
                            "status_class", failure.statusClass())
                    .register(registry)
                    .increment();

            if (failure.throttled()) {
                Counter.builder("cloud.dependency.throttled.calls")
                        .tags(
                                "provider", provider,
                                "service", service,
                                "operation", operation)
                        .register(registry)
                        .increment();
            }
            throw ex;
        } finally {
            Timer.builder("cloud.dependency.duration")
                    .tags(
                            "provider", provider,
                            "service", service,
                            "operation", operation)
                    .publishPercentileHistogram()
                    .serviceLevelObjectives(
                            Duration.ofMillis(100),
                            Duration.ofMillis(250),
                            Duration.ofMillis(500),
                            Duration.ofSeconds(1),
                            Duration.ofSeconds(2))
                    .register(registry)
                    .record(System.nanoTime() - started, TimeUnit.NANOSECONDS);

            Counter.builder("cloud.dependency.calls")
                    .tags(
                            "provider", provider,
                            "service", service,
                            "operation", operation,
                            "outcome", outcome)
                    .register(registry)
                    .increment();
        }
    }

    public record Failure(
            String errorType,
            String statusClass,
            boolean throttled) {
    }
}
~~~

Values for provider, service, operation, errorType, and statusClass must be normalized before passing them in. classifier should be a small adapter that never throws new exceptions and only returns bounded categories such as throttled, timeout, authorization, not_found, server, network, or other.

This snippet records the **final outcome** of the logical call. If the SDK retries internally and succeeds, the call counts as success; retry attempts inside the SDK must be obtained from separate telemetry if the SDK provides it. To measure a void call, add an overload accepting Runnable or wrap the result into a non-null value.

### 8.1. Example wrapping an Azure Blob operation

~~~java
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.models.BlobStorageException;
import java.io.ByteArrayInputStream;
import org.springframework.stereotype.Service;

@Service
public class DocumentStorage {
    private final BlobClient blobClient;
    private final CloudOperationMetrics metrics;

    public DocumentStorage(
            BlobClient blobClient,
            CloudOperationMetrics metrics) {
        this.blobClient = blobClient;
        this.metrics = metrics;
    }

    public void upload(byte[] content) {
        metrics.record(
                "azure",
                "blob",
                "upload",
                () -> {
                    blobClient.upload(
                            new ByteArrayInputStream(content),
                            content.length,
                            true);
                    return Boolean.TRUE;
                },
                ex -> {
                    if (ex instanceof BlobStorageException storageException) {
                        int status = storageException.getStatusCode();
                        boolean throttled = status == 429;
                        String type = throttled ? "throttled"
                                : status == 403 ? "authorization"
                                : status == 404 ? "not_found"
                                : status >= 500 ? "server" : "other";
                        return new CloudOperationMetrics.Failure(
                                type, status / 100 + "xx", throttled);
                    }
                    return new CloudOperationMetrics.Failure(
                            "other", "unknown", false);
                });
    }
}
~~~

This example illustrates an adapter for a synchronous Azure Blob operation. In a real application, do not create a new BlobClient per request; inject a preconfigured client and manage its lifecycle in configuration. The classifier treats HTTP 429 as throttling. For HTTP 503, inspect the service error code (such as ServerBusy where supported) and retry headers before classifying; not every 503 is throttling.

## 9. Measuring application-controlled retries

If the application uses its own retry wrapper, increment the counter for **each additional retry**, not on the initial attempt:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import java.time.Duration;
import org.springframework.stereotype.Component;

@Component
public class CloudRetryMetrics {
    private final MeterRegistry registry;

    public CloudRetryMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordRetry(
            String provider,
            String service,
            String operation,
            String reason) {
        registry.counter(
                "cloud.dependency.retries",
                "provider", provider,
                "service", service,
                "operation", operation,
                "reason", reason)
            .increment();
    }

    public void recordBackoff(
            String provider,
            String service,
            String operation,
            Duration delay) {
        registry.timer(
                "cloud.dependency.backoff.duration",
                "provider", provider,
                "service", service,
                "operation", operation)
            .record(delay);
    }
}
~~~

Call recordRetry(...) when the retry policy decides to make another attempt, and recordBackoff(...) with the actual wait duration. When using SDK auto-retry without application-level callbacks per attempt, **do not treat this counter as the SDK's retry count**.

## 10. Provider-specific telemetry in AWS, Azure, and Google Cloud

Micrometer provides application-layer metric naming and aggregation. Cloud SDKs and providers add their own telemetry, though not all SDKs emit the same data.

### 10.1. AWS SDK for Java 2.x

AWS SDK for Java 2.x supports MetricPublisher. When SDK metrics are enabled, data can include:

- ApiCallDuration: duration of the entire logical call.
- ApiCallSuccessful: whether the logical call succeeded or failed.
- RetryCount: number of retries for the logical call; 0 means no retries.
- BackoffDelayDuration: how long the SDK waited before an attempt.
- ErrorType: attempt classification, including Throttling, ServerError, ConfiguredTimeout, IO, and Other.
- AwsRequestId and AwsExtendedRequestId: AWS-side request identifiers useful for log/trace correlation.

SDK metrics are disabled by default. You can use CloudWatchMetricPublisher for long-running applications or another publisher suited to your environment. The AWS CRT-based S3 client currently has limitations in SDK metrics support; verify your client variant before relying on this telemetry.

Example attaching a publisher to a service client:

~~~java
import software.amazon.awssdk.metrics.MetricPublisher;
import software.amazon.awssdk.services.s3.S3Client;

MetricPublisher publisher = createMetricPublisher();

S3Client s3 = S3Client.builder()
        .overrideConfiguration(config ->
                config.addMetricPublisher(publisher))
        .build();
~~~

createMetricPublisher() represents the chosen publisher configured per AWS SDK documentation. Close the publisher with the application lifecycle when it implements AutoCloseable; do not create a new publisher per request.

### 10.2. Azure SDK for Java

The Azure SDK uses an HTTP pipeline and retry policy from Azure Core. Ways to observe it:

- Use **Micrometer Timer/Counter in the application wrapper** to measure logical-call latency and final outcomes.
- Use distributed tracing/OpenTelemetry to link application operations with requests to Azure.
- BASIC-level HTTP logging can provide HTTP method, sanitized URL, attempt count, response code, and content length for debugging.
- Azure Monitor/service metrics help observe throttling and service health on the cloud side.

Azure SDK HTTP logging is designed for debugging. Microsoft does not recommend relying on log formats or context keys for stable alerting/monitoring; use distributed tracing and metrics with clear contracts instead.

When configuring retries for the Azure Storage SDK, review RequestRetryOptions/retry policies suited to the client. Keep attempt counts and total duration bounded, and respect retry information returned by the service. If you need SDK-level attempt counts as metrics, verify the telemetry API of the exact library/version in use; do not parse free-form logs into production counters.

### 10.3. Google Cloud Java client libraries

Google Cloud Java client libraries can emit telemetry via OpenTelemetry when enabled:

- gcp.client.request.duration: request duration and request rate metric.
- HTTP/gRPC-level traces.
- DEBUG logs for failed transport requests, including ones that ultimately succeed after retry.

Google Cloud Java retry settings typically use exponential backoff and jitter. Set MaxAttempts or TotalTimeout to bound operations; never configure unbounded retries.

RESOURCE_EXHAUSTED usually indicates a need to inspect quotas/rate limits, whereas UNAVAILABLE indicates temporary service unavailability and does not automatically imply throttling. Keep error classification in per-API adapters.

## 11. Querying metrics and building dashboards

Assume Prometheus receives these Micrometer metrics:

- cloud_dependency_duration_seconds_bucket
- cloud_dependency_calls_total
- cloud_dependency_errors_total
- cloud_dependency_throttled_calls_total
- cloud_dependency_retries_total

Actual metric names are normalized according to the registry and naming conventions. Inspect /actuator/prometheus before writing queries.

### 11.1. p95 latency by provider/service/operation

~~~promql
histogram_quantile(
  0.95,
  sum by (le, provider, service, operation) (
    rate(cloud_dependency_duration_seconds_bucket[5m])
  )
)
~~~

This query calculates p95 from histograms aggregated across instances. Use rate on the bucket counter and preserve the le label so histogram_quantile can compute the quantile.

### 11.2. Final error rate

~~~promql
sum by (provider, service, operation) (
  rate(cloud_dependency_calls_total{outcome="error"}[5m])
)
/
sum by (provider, service, operation) (
  rate(cloud_dependency_calls_total[5m])
)
~~~

This is the final failure rate of logical calls. Handle zero-denominator cases in dashboards/alerts, such as using clamp_min or traffic-presence guards.

### 11.3. Throttle rate

~~~promql
sum by (provider, service, operation) (
  rate(cloud_dependency_throttled_calls_total[5m])
)
/
sum by (provider, service, operation) (
  rate(cloud_dependency_calls_total[5m])
)
~~~

The throttled_calls metric should increment at most once per logical call that encounters at least one throttle response. If the counter increments per attempt, the denominator must be an attempt counter instead of the logical-call counter.

### 11.4. Retry rate

~~~promql
sum by (provider, service, operation) (
  rate(cloud_dependency_retries_total[5m])
)
/
sum by (provider, service, operation) (
  rate(cloud_dependency_calls_total[5m])
)
~~~

A value of 0.15 means an average of 0.15 extra retries per logical call over the observation window; it does not mean 15% of calls failed. Display it alongside the final error rate to see whether retries are rescuing calls or merely prolonging failures.

### 11.5. Essential dashboard panels

| Panel | Group by | Purpose |
|---|---|---|
| p50/p95/p99 logical latency | provider, service, operation | Compare typical experience and slow tail |
| Logical call throughput | provider, service, operation | Track operation volume over time |
| Final error rate | provider, service, operation, error_type | Detect user-facing failures |
| Throttled call/attempt rate | provider, service, operation | Detect quota/capacity pressure |
| Retry per call | provider, service, operation, reason | Spot rising retries before error rate climbs |
| Backoff duration | provider, service, operation | Identify time lost waiting on retries |
| Request/attempt IDs in traces | trace/request | Investigate a specific operation |

## 12. SLOs and alerting

SLOs should be grounded in business requirements. For example, a report-generation API might target:

- 99% of logical calls to object storage complete under 1 second.
- Final error rate below 0.5% over a 30-minute window.
- Throttle rate below 0.1% under normal load.
- Average retries below 0.05 per logical call.

These numbers are examples, not universal standards across services. High load, object size, cloud region, storage tier, and operation type all influence SLOs.

Alerts should often combine multiple signals:

- **p95 rising and retries rising:** dependency is slowing down or throttling, forcing the SDK to retry.
- **Throttling rising while final errors stay low:** the SDK is masking a quota/capacity issue; address it before retries exhaust.
- **Final errors rising and retry exhausted rising:** retries can no longer overcome failures.
- **Latency rising while throttling stays low:** investigate networking, DNS, connection pools, serialization, or server latency.
- **Error rate rising on a single operation:** check permissions, resource paths, or payloads for that operation.

Do not alert on a single 429 request. Use rates, sustained duration, error budgets, and business impact to avoid noisy alerts.

## 13. Cardinality, security, and sensitive data

Metric labels multiply across every combination of values. Putting requestId, blobName, bucketName, customerId, or URLs into labels can cause time-series counts to explode rapidly.

**Use labels with small, stable value sets:**

- provider: aws, azure, gcp.
- service: s3, blob, queue, pubsub.
- operation: get_object, upload, send_message.
- outcome: success, error.
- error_type: throttled, timeout, authorization, not_found, server, network, other.
- status_class: 2xx, 4xx, 5xx, unknown.

**Never use as metric labels:**

- Request ID, trace ID, or correlation ID.
- Account, project, subscription, bucket, container, or object names when unbounded.
- Customer/user/tenant ID.
- Exception messages, full URLs, tokens, SAS strings, or credentials.

Request IDs and trace IDs belong in **logs/traces** to investigate individual calls, not as metric dimensions. Never log Authorization headers, access tokens, SAS query strings, or sensitive message/object payloads.

## 14. Avoiding double counting and misinterpreting retries

A call can be measured at multiple layers:

1. HTTP server metrics measuring requests to Spring Boot.
2. Service metrics measuring the generate_report business operation.
3. Cloud dependency metrics measuring the logical SDK call.
4. SDK telemetry measuring individual requests/attempts.
5. Provider-side metrics measuring the service in the cloud.

These are distinct perspectives, not duplicates, as long as names and boundaries stay clear. Duplication happens when the same operation is instrumented twice at the same layer—for example, combining Spring auto-instrumentation with an @Observed annotation on an already auto-instrumented method.

Rules:

- Document clearly which metrics measure logical calls and which measure attempts.
- Do not add SDK RetryCount into application-recorded retry counters.
- Do not count one final error as multiple logical errors just because multiple attempts failed.
- Do not wrap SDK auto-retry in another application-level retry loop without accounting for total attempts and total timeout.
- Use parent/child trace spans to see controller request → service → cloud SDK.

When the SDK retries internally, a Timer wrapping the SDK measures total duration; measuring attempts requires SDK or HTTP pipeline telemetry. When the application handles retries itself, instrument each retry right where the policy decides to perform the next attempt.

## 15. Testing metrics and retry behavior

A test suite should verify both recorded metrics and retry behavior:

| Scenario | Expected result |
|---|---|
| Cloud call succeeds on first attempt | Calls increment by 1, errors 0, retries 0 |
| Call fails permanently | Calls increment by 1, errors increment by 1 |
| First attempt throttles, next succeeds | Logical call succeeds; throttle/retry counts increment per convention |
| Retries exhausted after multiple failures | One final error for the logical call; retry count equals extra attempts |
| Permission denied | Classified as authorization; no futile retries |
| Timeout | Classified as timeout; total duration stays within configured budget |
| Retry-After present | Next retry does not happen before the requested wait time |
| No Retry-After | Backoff is bounded and includes jitter |
| Request with unique ID | ID appears only in traces/logs, never creating new metric series |
| Multiple Pods running | Histograms aggregate and percentiles compute across Pods |

### 15.1. Testing Timer with SimpleMeterRegistry

In unit tests, SimpleMeterRegistry can verify recorded metrics:

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class CloudOperationMetricsTest {
    @Test
    void recordsSuccessfulLogicalCall() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        CloudOperationMetrics metrics = new CloudOperationMetrics(registry);

        Boolean result = metrics.record(
                "azure",
                "blob",
                "upload",
                () -> Boolean.TRUE,
                ex -> new CloudOperationMetrics.Failure(
                        "other", "unknown", false));

        assertEquals(Boolean.TRUE, result);
        assertEquals(
                1.0,
                registry.get("cloud.dependency.calls")
                        .tag("provider", "azure")
                        .tag("service", "blob")
                        .tag("operation", "upload")
                        .tag("outcome", "success")
                        .counter()
                        .count());
    }
}
~~~

This test verifies that a successful logical call is counted exactly once. Add tests for exceptions, throttling, and retry wrappers, and assert that tags use bounded values. For Prometheus histograms, write integration tests against the corresponding registry to verify exported buckets and metric names.

### 15.2. Testing on real cloud

Emulators or mocks cannot validate quotas, throttling, and retry behavior of managed services under production load. Use a test account/project to:

- Generate controlled load and observe service responses/error codes.
- Verify SDK retry policies, Retry-After handling, total timeouts, and attempt counts.
- Compare SDK telemetry with application-recorded metrics.
- Verify IAM/RBAC permissions and permission-denied cases.
- Verify dashboards/alerts do not leak resource IDs or secrets.

Do not intentionally overload production to trigger throttling. Use bounded quota/load tests in authorized test environments.

## 16. Common pitfalls and fixes

| Symptom | Possible cause | Fix |
|---|---|---|
| p95 is low yet users wait a long time | Measuring only the last attempt instead of the logical call | Wrap the Timer around the entire SDK call |
| Error rate is low while latency climbs | SDK retries succeed after multiple attempts/backoffs | Monitor retry count, backoff, and throttle rate |
| Throttling stays zero despite 429s | Classifying only by generic exception class or ignoring service codes | Inspect HTTP/service error codes and SDK classification |
| Unusually high retry count | Nested retries across SDK, service, and message worker | Choose one retry owner and bound total attempts and timeout |
| Error counter exceeds total calls | Counting each failed attempt as a final logical error | Separate attempt errors from final errors |
| p95 cannot be aggregated across Pods | Using client-side percentiles instead of histograms | Export histograms and compute percentiles in the backend |
| Time-series count keeps growing | Tags include request ID, object name, or customer ID | Replace with bounded label sets |
| Azure metrics lack retry count | SDK telemetry/logging not enabled or lacks stable metric | Use wrapper for app-owned retries; tracing/service metrics for SDK retries |
| Google client library metrics missing | Telemetry opt-in disabled or exporter unconfigured | Enable OpenTelemetry signals and verify exporter |
| AWS SDK metrics missing | SDK MetricPublisher disabled by default | Configure a publisher compatible with your client variant |
| Retries push requests past SLA | Backoff/attempt limits too high or missing total timeout | Set total timeout and max attempts within business budget |

## 17. Hands-on exercises and self-check questions

**Scenario A — Slow S3:** An API calls GetObject on AWS S3. p95 latency rises from 150 ms to 1.2 seconds while final error rate stays low. Investigate retry count, BackoffDelayDuration, attempt error types, and connection pool metrics to pinpoint the cause.

**Scenario B — Azure Blob throttling:** Blob uploads begin returning bursts of 429/503 responses. Measure logical-call latency, throttle rate, retry counts, and Retry-After headers; propose concurrency limits or load shaping before increasing retries.

**Scenario C — Google Cloud quota:** Calling a Google Cloud API returns RESOURCE_EXHAUSTED. Classify the error, observe `gcp.client.request.duration`, inspect quotas, and cap MaxAttempts/TotalTimeout.

**Scenario D — Nested retries:** A service configures 3 attempts at the application layer while the SDK also retries 3 attempts. Calculate the worst-case maximum requests generated and redesign around a single clear retry owner.

**Scenario E — Wrong error rate:** A dashboard shows a 4% error rate, yet users only see 0.2% failed requests. Identify how the dashboard is counting failed attempts instead of final logical calls and separate the two metrics.

**Scenario F — Cardinality:** A developer adds blobName and requestId as metric tags. Explain why time-series count explodes, how to move those IDs to traces/logs, and how to keep metric labels bounded.

### Self-check questions

1. **How does logical-call latency differ from attempt latency?** Logical-call latency covers all attempts and backoff; attempt latency measures a single request.
2. **If a call makes three attempts, what is the retry count?** Two, because the initial attempt is not a retry.
3. **What should the end-user error rate count?** Logical calls ending in failure divided by total logical calls.
4. **Why is a separate attempt error rate needed?** It surfaces transient errors that SDK retries mask while still adding load and latency.
5. **Does HTTP 429 always mean throttling on every provider?** No; inspect service error codes and SDK/service semantics.
6. **Which retry metrics can AWS SDK for Java 2.x emit?** RetryCount, along with BackoffDelayDuration and ErrorType depending on enabled telemetry.
7. **Why avoid parsing Azure debug logs for long-term alerts?** Log formats/context keys are not stable contracts; use metrics and distributed tracing.
8. **What limits should Google Cloud Java retries have?** MaxAttempts or TotalTimeout, paired with exponential backoff and jitter.
9. **Why should Prometheus use histograms for multi-Pod p95?** Histogram buckets can be aggregated; per-Pod client-side percentiles cannot be summed accurately.
10. **Should request IDs be placed in metric tags?** No; IDs belong in traces/logs because they create excessive cardinality.

## 18. Summary

Measuring cloud dependencies requires distinguishing **logical calls** from **request attempts**. A Timer wrapping the entire SDK call reveals how long the application actually waits; histograms enable aggregating p95/p99 across instances; Counters track logical calls, final errors, throttling, and retries with clear definitions.

AWS SDK for Java 2.x can emit RetryCount, BackoffDelayDuration, and ErrorType via MetricPublisher. Azure SDK provides retry policies, tracing, and HTTP logging for diagnostics; do not depend on log formatting for production metrics. Google Cloud Java libraries offer OpenTelemetry telemetry and retry settings that must be bounded by MaxAttempts or TotalTimeout.

Combine application metrics with SDK and provider telemetry, keep tag cardinality low, classify throttling according to service semantics, and avoid nested retries. Dashboards should display latency, final error rate, throttle rate, and retry rate side by side to detect degradation before users encounter failures.

### Official references

- [Spring Boot 3.5 — Metrics](https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html)
- [Spring Boot 3.5 — Observability](https://docs.spring.io/spring-boot/3.5/reference/actuator/observability.html)
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html)
- [Micrometer — Prometheus Registry](https://docs.micrometer.io/micrometer/reference/implementations/prometheus.html)
- [AWS SDK for Java 2.x — Publish SDK Metrics](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/metrics.html)
- [AWS SDK for Java 2.x — Metrics Reference](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/metrics-list.html)
- [AWS SDK for Java 2.x — Retry Strategies](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/retry-strategy.html)
- [Microsoft Learn — Azure SDK for Java Logging](https://learn.microsoft.com/azure/developer/java/sdk/logging-overview)
- [Microsoft Learn — Azure SDK HTTP Client and Pipeline](https://learn.microsoft.com/azure/developer/java/sdk/http-client-pipeline)
- [Google Cloud — Enable Telemetry in Java Client Libraries](https://docs.cloud.google.com/java/docs/observability)
- [Google Cloud — Configure Client-side Retries for Java](https://docs.cloud.google.com/java/docs/client-retries)
