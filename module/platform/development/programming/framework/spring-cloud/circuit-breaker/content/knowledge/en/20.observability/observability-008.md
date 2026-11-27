# Controlling Tag Cardinality and IDs in Metrics

Metrics help track Circuit Breaker state, error rates, slow calls, and rejected requests. However, every unique combination of metric name and tag set can become a separate time series in storage systems like Prometheus. If tags contain IDs that vary per request, customer, or resource, time series counts can explode rapidly, driving up memory usage, storage capacity, and query costs.

In the **SPRING_CLOUD_CIRCUIT_BREAKER** module, instance names and metric tags must be designed with bounded sets of values. With Resilience4j and Micrometer, a Circuit Breaker name should represent a stable dependency or operation; request, user, order, or SKU IDs belong in logs and traces. The goal is to observe service protection status without turning metrics into an individual event store.

## 1. What Is Metric Cardinality?

**Cardinality** is the number of distinct values that can appear in a tag set or the number of time series produced from tag combinations. In Prometheus, a time series is identified by the metric name and its complete label set. A single new value on one tag can cause the system to create a brand-new time series.

For example, a metric counting Circuit Breaker calls has tags:

- `name`: Circuit Breaker instance name.
- `outcome`: outcome such as success, failure, or rejected.
- `kind`: call kind, depending on how the metric is instrumented.

If the application has 10 instance names, 3 outcomes, and 2 kinds, the theoretical maximum number of combinations is:

$$
10 \times 3 \times 2 = 60
$$

This example illustrates the number of combinations if the metric includes all those tags. Actual time series counts depend on which combinations occur and how the library exports metrics.

Suppose you add a `customerId` tag with 100,000 values. Potential cardinality now scales with customer count, even if each customer makes only a few calls. A single tag with many distinct values is usually far more dangerous than several tags with small, fixed value sets.

## 2. Why Do Dynamic IDs Drive Up Cardinality?

Do not use continuously changing values as labels:

| Tag to Avoid | Why It Is Dangerous | Suitable Alternative |
| --- | --- | --- |
| `requestId` or `traceId` | Nearly every request produces a new value | Put IDs into linked traces or logs |
| `customerId`, `userId`, `tenantId` | Customer counts can be huge and grow over time | Use a bounded tenant tier if analysis is genuinely needed |
| `orderId`, `paymentId`, `transactionId` | Every transaction creates a new value | Record IDs in logs or traces |
| `sku`, `productId`, `resourceId` | Resource sets can be enormous | Use a finite business group such as `inventory-read` |
| Full URL with path variables or query | Every distinct path/query creates a new label value | Use a route template such as `/items/{sku}` |
| Exception message | Content may include IDs, URLs, input data, or variable text | Use stable exception categories such as `timeout`, `connection`, `other` |

For example, if each request adds a `sku` tag, an Inventory service with 500,000 SKUs can generate hundreds of thousands of label values. If the same metric also carries `outcome` and `region` tags, combinations multiply further across those dimensions.

Metrics are built to answer aggregate questions like "How many failed calls did the `inventory` Circuit Breaker have in 5 minutes?". Questions like "Which request involved SKU X?" belong in logs or traces, where specific events can be retrieved.

## 3. Choosing Stable Circuit Breaker IDs

The instance name is used in Resilience4j configuration and typically appears as a tag in metrics. Names should represent a dependency or operation group with a stable lifecycle.

Appropriate examples:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory-read:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
      payment-create:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        failureRateThreshold: 30
      customer-profile-read:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 15
        failureRateThreshold: 50
~~~

These names form a finite set corresponding to operations defined in code. Each instance can maintain its own configuration and state, while the name never depends on request data.

An inappropriate example is generating names per customer:

~~~java
// Do not construct a Circuit Breaker ID from high-cardinality data.
String circuitBreakerName = "inventory-" + customerId;
CircuitBreaker circuitBreaker =
        circuitBreakerRegistry.circuitBreaker(circuitBreakerName);
~~~

With 50,000 customers, the registry can spawn tens of thousands of instances. Each instance keeps its own state and sliding window; sample counts become fragmented and metrics can generate massive numbers of time series.

Use a fixed name per dependency instead:

~~~java
CircuitBreaker circuitBreaker =
        circuitBreakerRegistry.circuitBreaker("inventory-read");
~~~

If analysis by customer segment is needed, map customers into a few predefined groups, such as `customer-tier=standard|premium`, and add that tag only when an operational question actually requires it. Never place unique identifiers into metrics.

## 4. Choosing Tags with Finite Value Sets

A good label typically has a small, controlled, and operationally meaningful set of values:

| Tag | Valid Value Examples | Notes |
| --- | --- | --- |
| `service` | `order`, `inventory`, `payment` | Fixed service name |
| `dependency` | `inventory-service`, `payment-provider` | Managed dependency name |
| `operation` | `inventory-read`, `payment-create` | Fixed operation group |
| `environment` | `dev`, `staging`, `prod` | Never put unique build IDs into tags |
| `region` | `ap-southeast-1`, `eu-west-1` | Finite deployment regions |
| `outcome` | `success`, `failure`, `not_permitted` | Standardized outcome |
| `exception_group` | `timeout`, `connection`, `http_5xx`, `other` | Maps many exceptions into finite groups |
| `state` | `closed`, `open`, `half_open` | Circuit Breaker state |

Not every metric needs all of these tags. Each added tag introduces another multiplicative dimension. Add a tag only when it answers a specific question in a dashboard or alert.

Avoid placing uncontrolled values into tags such as exception messages, full URLs, dynamically generated class names, or header contents. When detailed context is needed, write it to logs or traces linked to metrics via trace IDs or exemplars where supported.

## 5. Cardinality Multiplies Across Tag Combinations

Suppose a metric has:

- 40 Circuit Breaker names.
- 3 outcomes.
- 4 exception groups.
- 3 regions.

The theoretical maximum number of combinations is:

$$
40 \times 3 \times 4 \times 3 = 1,440
$$

If that metric is exported as a histogram with many buckets, stored series increase further by the number of buckets plus aggregate series like `count` and `sum`. With Prometheus histograms, every label set creates multiple bucket series; thus histogram cardinality is substantially more expensive than a simple counter.

This ceiling calculation illustrates the impact of each dimension, not the exact number of series guaranteed to be created. Actual metrics contain only label sets that have occurred, and different metrics may use different tag sets.

A useful design practice is budgeting cardinality before adding labels:

1. List the metrics to be exported.
2. List the labels on each metric.
3. Estimate the number of valid values for each label.
4. Multiply counts to estimate potential combinations.
5. Multiply further by the bucket factor if using histograms.
6. Identify labels that can be dropped or replaced with finite value groups.

Do not judge solely by the count of label keys. Two labels with 3 values each are far cheaper than a single label with millions of values.

## 6. Resilience4j and Micrometer Metrics

When integrating Resilience4j with Micrometer, Circuit Breaker metrics typically provide information such as:

- Call counts by outcome.
- Calls rejected because the circuit is OPEN.
- Current instance state.
- Failure rate and slow call rate.
- Calls buffered in the sliding window and window capacity.

Exact meter names and tags can vary by Resilience4j version, Micrometer module, and export mechanism. Typically, the Circuit Breaker instance name is used as a tag to distinguish instances. Inspect actual meters on the application's metrics endpoint rather than assuming all versions share identical names or tag sets.

For instance, with fixed instances `inventory-read`, `payment-create`, and `customer-profile-read`, dashboards can compare failure rates or rejections by name. There is no need to add `requestId`, `customerId`, or `sku` to locate individual requests.

When using Spring Boot Actuator, expose the `metrics` or `prometheus` endpoint according to your application's security policy. Expose only necessary endpoints and restrict access; metrics endpoints can reveal dependency names and operational system details.

## 7. Capping Tag Values with MeterFilter

Micrometer provides `MeterFilter` to control meters before they are registered into the registry. You can cap the number of distinct values for the `name` tag on Circuit Breaker meters:

~~~java
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MetricsCardinalityConfiguration {
    @Bean
    MeterFilter circuitBreakerNameLimit() {
        return MeterFilter.maximumAllowableTags(
                "resilience4j.circuitbreaker",
                "name",
                50,
                MeterFilter.deny()
        );
    }
}
~~~

This example caps the number of accepted `name` tag values for meters matching the prefix. Once the threshold is exceeded, the filter rejects registering new meters according to the supplied filter action. Confirm the prefix and tag key against the actual meters emitted by your version; if meter names differ, the filter will not apply as expected.

A tag cap is an extra safeguard. It does not replace stable ID design. If the application has already created thousands of dynamic Circuit Breakers in the registry, blocking new meters alone does not eliminate all those instances and states sitting in memory.

Do not set the limit so low that important legitimate instances lose metrics. Choose the threshold based on managed dependencies and operations, and monitor alerts if any meters are denied.

## 8. Normalizing Exceptions into Finite Groups

Do not use exception messages as labels because messages can contain URLs, IDs, or input data. Instead, map exceptions into a few stable groups:

~~~java
import java.net.ConnectException;
import java.net.SocketTimeoutException;

public String classifyFailure(Throwable failure) {
    if (failure instanceof SocketTimeoutException) {
        return "timeout";
    }
    if (failure instanceof ConnectException) {
        return "connection";
    }
    if (failure instanceof DownstreamHttpException http
            && http.getStatusCode() >= 500) {
        return "http_5xx";
    }
    if (failure instanceof CallNotPermittedException) {
        return "circuit_open";
    }
    return "other";
}
~~~

The groups `timeout`, `connection`, `http_5xx`, `circuit_open`, and `other` have a finite value set. When using these groups as tags on custom metrics, do not attach exception messages or stack traces. For exceptions from other HTTP libraries, map according to the actual exception types of the client in use.

The snippet above only illustrates a classification helper; it does not automatically add tags to every Resilience4j metric. Any custom counter or timer must be designed separately while preserving the same finite-value-set rule.

## 9. Using Logs and Traces for High-Cardinality IDs

Metrics, logs, and traces serve different purposes:

| Data Type | Best Suited to Store | Example |
| --- | --- | --- |
| Metrics | Aggregate numbers, bounded tags, trends over time | Failure rate of `inventory-read` |
| Logs | Detailed events and IDs for investigation | Request ID, SKU, sanitized exception message |
| Traces | Path of a single request across multiple services | Trace ID, span ID, duration of each call |

Example log containing IDs for investigation:

~~~java
log.warn(
        "Inventory dependency failed: circuitBreaker={}, requestId={}, sku={}, errorGroup={}",
        "inventory-read",
        requestId,
        sku,
        classifyFailure(failure)
);
~~~

Values like `requestId` and `sku` fit logs with access controls and retention policies, but should not be promoted into metric tags. Filter or mask sensitive data before logging. If your observability stack supports trace exemplars, you can link a metric data point to a concrete trace without turning trace IDs into labels on every time series.

## 10. Avoiding Dynamic Circuit Breaker IDs in OpenFeign

With OpenFeign, a naming resolver can construct IDs from client name and method. This produces a controllable set of names if clients and methods form a fixed set:

~~~java
@Bean
CircuitBreakerNameResolver circuitBreakerNameResolver() {
    return (clientName, target, method) ->
            clientName + "_" + method.getName();
}
~~~

For example, `inventory_getInventory` is a stable ID as long as client and method names do not change. Never incorporate request values into the resolver:

~~~java
// Avoid: each SKU can spawn a separate instance and a separate metric series.
return (clientName, target, method) ->
        clientName + "_" + method.getName() + "_" + currentSku;
~~~

A Circuit Breaker ID must identify a group of calls that share the same state and sliding window. If every SKU gets its own instance, failure history fractures and the circuit cannot reflect the overall health of the Inventory service.

When renaming a client or method, the ID can change as well. Treat that as a configuration change requiring synchronized updates to `resilience4j.circuitbreaker.instances` keys and dashboards filtering by instance name.

## 11. Monitoring Cardinality and Detecting Unexpected Spikes

In production, monitor:

- Total application time series and growth over time.
- Distinct `name` tag values across Circuit Breaker meters.
- Number of Circuit Breaker instances managed by the registry.
- Number of meters rejected by cardinality limits if recorded by the system.
- Memory consumption and metrics storage usage.
- Rate of newly appearing meters after each deployment.

If time series spike after a release, inspect changes involving tags and IDs. Look specifically for new labels pulling values from requests, full URLs, tenants, SKUs, or exception messages.

You can use PromQL to group and count series by metric or label after confirming actual metric names emitted by the exporter. Avoid queries that themselves return massive detailed result sets in dashboards; aim to monitor aggregate counts and growth trends.

A helpful dashboard can display:

| Panel | Operational Question |
| --- | --- |
| Instances by name | Are any unexpected Circuit Breaker IDs appearing? |
| Time series by metric family | Which metric family consumes the most series? |
| Series growth rate | When did cardinality start climbing? |
| Denied meters | Are any limits blocking legitimate metrics? |
| Failure rate and state | Which dependencies are Circuit Breakers protecting? |

## 12. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Putting request ID or trace ID into labels | Nearly every request spawns a new time series | Use logs or traces to store IDs |
| Creating Circuit Breakers per customer or SKU | Registry and metrics grow with resource count | Use fixed instance IDs per dependency or operation |
| Using full URLs as tags | Path variables and query strings create unbounded values | Use route templates or endpoint groups |
| Using exception messages as labels | Messages carry dynamic and sensitive data | Map exceptions into finite groups |
| Adding extra labels just for ad-hoc filtering | Label combinations multiply rapidly | Keep only labels answering specific operational questions |
| Enabling histograms with too many label dimensions | Every bucket multiplies time series count | Limit labels and buckets to actual needs |
| Relying solely on MeterFilter to fix dynamic IDs | Dynamic instances still accumulate in the registry | Fix naming logic and instance lifecycle |
| Renaming IDs without updating dashboards | Dashboards lose data or misgroup metrics | Treat IDs as part of the metrics contract |

## 13. Workflow for Designing Tags and IDs

When adding metrics for a Circuit Breaker, follow these steps:

1. Define the questions the dashboard or alert needs to answer.
2. Choose a stable Circuit Breaker ID by dependency or operation, never derived from request data.
3. List required labels and the expected maximum values for each label.
4. Estimate total label set combinations and histogram cost if applicable.
5. Route unique IDs, dynamic URLs, and exception messages to logs or traces.
6. Use `MeterFilter` as an added safeguard on key tags after verifying actual meter names and tags.
7. Monitor instance counts, time series counts, denied meters, and cardinality trends after deployment.
8. When changing naming resolvers or instance names, update Resilience4j configuration and dashboards together.

Controlling cardinality starts with instance naming and tag selection. When IDs represent stable call groups, labels draw from finite value sets, and per-request details stay in logs or traces, Resilience4j metrics deliver full visibility into Circuit Breaker state without producing uncontrollable time series growth.
