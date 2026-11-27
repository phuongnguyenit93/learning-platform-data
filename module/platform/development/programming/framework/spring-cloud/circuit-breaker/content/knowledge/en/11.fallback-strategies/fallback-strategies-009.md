# Measuring Fallback Usage Without Masking Real Outages

## Why Measure Fallbacks Separately?

In Spring Cloud Circuit Breaker, fallbacks let an application keep responding when a call to a dependent service fails or the Circuit Breaker is `OPEN`. However, if you only monitor the final HTTP status, a fallback returning HTTP 200 can make dashboards look completely normal even while the dependent service has been failing continuously.

Therefore, observe three parts of a protected operation separately:

1. **Business operations entering the protected boundary:** total requests the application intends to process through the Circuit Breaker.
2. **Primary dependency calls:** how many times the supplier actually starts, exception counts, and execution duration.
3. **Fallback:** how many times the handler is invoked, how many fallback responses are produced, how many times the fallback itself fails, and processing duration.

These three parts answer different questions. Fallback rate shows how often the application must rely on the backup path. Dependency failure rate shows how calls actually executed against the dependency are failing. Open-circuit rejection count shows when the Circuit Breaker is blocking new requests from reaching the dependency.

## Choosing the Right Denominator Before Computing Ratios

No single denominator fits every dashboard. Name each ratio explicitly and only divide counts that share the same scope:

| Metric | Formula | Meaning |
| --- | --- | --- |
| Operations using fallback rate | Fallback invocations / operations entering protected boundary | How many business operations needed the backup path. |
| Primary call exception rate | Exceptions from supplier / times supplier actually started | How frequently attempted calls to the dependency throw exceptions. |
| Fallback response rate | Fallback responses produced / fallback invocations | Whether the handler succeeded in producing an alternative result. |
| Fallback failure rate | Times handler threw an error / fallback invocations | Whether the backup path itself is failing. |
| Circuit Breaker rejection rate | Calls rejected while circuit open / operations entering protected boundary | How many operations were not sent to the dependency because the circuit is open. |

An important detail: when the Circuit Breaker is `OPEN`, the supplier does not run. Rejected calls can go straight to the fallback, increasing fallback invocations without increasing supplier starts. If you divide fallback invocations by supplier starts, the ratio can exceed 100% and ceases to represent an operation rate. Use operations entering the protected boundary as the denominator for the fallback rate.

For example, suppose over a 5-minute window 1,000 operations enter the protected boundary, 180 fallback invocations occur, 820 supplier starts occur, and 90 supplier exceptions occur:

- Operations using fallback rate: \(180 / 1,000 = 18\%\).
- Supplier exception rate: \(90 / 820 \approx 10.98\%\).
- There are 180 fallback invocations, within which you must further distinguish whether the handler returned a response or threw an error.

The first two ratios do not contradict each other. Part of the fallbacks may have been triggered because the Circuit Breaker rejected calls while open, not because the supplier just threw an exception.

## Distinguishing Fallback Invocation from Fallback Success

A fallback being invoked does not mean the fallback produced a useful result. Record at least three outcomes:

- `cache`: the handler returned cached data within the allowed age limit.
- `unavailable`: the handler returned a no-data or service-temporarily-unavailable status.
- `error`: the handler itself threw an error, for example because the cache was also unreachable.

`unavailable` is still a fallback response successfully produced in terms of handler execution, yet it is not available backup data. Merging `cache` and `unavailable` into a single "fallback succeeded" number can hide on dashboards that the system no longer has data to serve. Keep a response mode tag so operators know what users are actually receiving.

Similarly, the count of fallback responses returned does not prove the dependency is healthy. If the dependency is failing while the cache still works, the fallback can keep returning responses continuously even as dependency error rates surge.

## Instrumentation with Micrometer

Micrometer can record counters and timers for both primary operations and fallbacks. The example below instruments a synchronous catalog service. `CatalogClient`, `ProductCache`, `CachedProduct`, and `ProductView` are application types.

```java
import java.util.Optional;
import java.util.concurrent.TimeoutException;

import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;

@Service
public class CatalogService {
    private final CatalogClient catalogClient;
    private final ProductCache productCache;
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final MeterRegistry registry;

    public CatalogService(
            CatalogClient catalogClient,
            ProductCache productCache,
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            MeterRegistry registry) {
        this.catalogClient = catalogClient;
        this.productCache = productCache;
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.registry = registry;
    }

    public ProductView find(String productId) {
        increment("catalog.protected.operations");

        return circuitBreakerFactory.create("catalog").run(
            () -> {
                increment("catalog.primary.attempts");
                Timer.Sample sample = Timer.start(registry);
                try {
                    ProductView result = ProductView.current(
                        catalogClient.find(productId)
                    );
                    sample.stop(timer("catalog.primary.duration", "success"));
                    return result;
                } catch (RuntimeException error) {
                    increment("catalog.primary.exceptions", "reason", reason(error));
                    sample.stop(timer("catalog.primary.duration", "error"));
                    throw error;
                }
            },
            error -> fallback(productId, error)
        );
    }

    private ProductView fallback(String productId, Throwable cause) {
        String reason = reason(cause);
        increment("catalog.fallback.invocations", "reason", reason);
        Timer.Sample sample = Timer.start(registry);

        try {
            Optional<CachedProduct> cached = productCache.find(productId);
            if (cached.isPresent()) {
                CachedProduct entry = cached.get();
                ProductView result = ProductView.stale(entry.details(), entry.cachedAt());
                increment("catalog.fallback.responses", "mode", "cache");
                sample.stop(timer("catalog.fallback.duration", "response"));
                return result;
            }

            ProductView result = ProductView.unavailable(productId);
            increment("catalog.fallback.responses", "mode", "unavailable");
            sample.stop(timer("catalog.fallback.duration", "response"));
            return result;
        } catch (RuntimeException fallbackError) {
            increment("catalog.fallback.errors", "reason", reason);
            sample.stop(timer("catalog.fallback.duration", "error"));
            throw fallbackError;
        }
    }

    private String reason(Throwable error) {
        if (error instanceof CallNotPermittedException) return "circuit_open";
        if (error instanceof TimeoutException) return "timeout";
        if (error instanceof ResourceAccessException) return "connection_or_io";
        if (error instanceof HttpServerErrorException) return "http_5xx";
        return "other";
    }

    private void increment(String name, String... tags) {
        Counter.builder(name)
            .tags(tags)
            .register(registry)
            .increment();
    }

    private Timer timer(String name, String outcome) {
        return Timer.builder(name)
            .tag("outcome", outcome)
            .register(registry);
    }
}
```

In this example:

- `catalog.protected.operations` increments once for every operation entering the protected boundary.
- `catalog.primary.attempts` increments only when the supplier actually begins. When the Circuit Breaker is open and rejects calls, this counter does not increase.
- `catalog.primary.exceptions` counts exceptions thrown by the supplier. This counter does not necessarily equal the failures recorded by Resilience4j, because `recordException` or `ignoreException` predicates may classify some exceptions as ignored or successful in breaker statistics.
- `catalog.fallback.invocations` increments when the handler begins running, including when the cause is `CallNotPermittedException`.
- `catalog.fallback.responses` counts produced fallback responses and attaches `mode` to distinguish cached data from an unavailable status.
- `catalog.fallback.errors` counts cases where the fallback itself throws an error.
- Two timers separate primary call latency from fallback handler latency.

This is illustrative instrumentation; for production use, standardize metric names per your system conventions and ensure beans, result types, and provider APIs match your library version. If the fallback has more branches, add bounded, meaningful `mode` values.

## Categorizing Causes with Bounded Tags

The `reason` tag shows whether a fallback occurred because the circuit was open, a timeout, a connection error, or a 5xx response. Tag values must form a small, stable set. Example:

| `reason` Value | Meaning |
| --- | --- |
| `circuit_open` | Circuit Breaker rejected the new call. |
| `timeout` | The call timed out. |
| `connection_or_io` | Connection or resource access error. |
| `http_5xx` | Service or gateway returned a 5xx response. |
| `other` | Remaining errors needing investigation. |

Never put `productId`, `customerId`, full URLs, request IDs, exception messages, or stack traces into metric tags. Those values create very high cardinality, driving up memory and storage costs in the metrics backend. When you need to investigate a specific request, use logs or distributed traces with a correlation ID; keep metrics aggregated.

Classification in the example only recognizes a few common exception classes. If an HTTP client wraps errors in `ResourceAccessException` or `CompletionException`, normalize `cause` across known wrappers before classifying. Also remember that 4xx errors can be normal business errors, authentication failures, or configuration signals; do not lump them all into one group without consulting the API contract.

## Correlating Custom Metrics with Resilience4j

Custom counters measure behavior at the application boundary. Resilience4j metrics measure outcomes according to Circuit Breaker rules and its sliding window. Display both sources side by side:

| Source | Metrics to Inspect | Question Answered |
| --- | --- | --- |
| Application Micrometer | Protected operations, primary attempts, fallback invocations, fallback responses/errors. | Are users receiving backup results and is the handler working? |
| Resilience4j | State, buffered calls, failed calls, successful calls, not-permitted calls, failure rate, slow-call rate. | According to recording policy and sliding window, how does the Circuit Breaker evaluate the dependency? |
| HTTP client | Connection timeout, read timeout, status code, latency. | Did the failure happen during connect, waiting for response, or status handling? |
| Distributed tracing | Primary request span and fallback/cache span. | Which path did a specific request take and where was time spent? |

`primary.exceptions` does not replace Resilience4j's failure rate. For example, an exception matched by `ignoreException` is still counted as a supplier exception by the custom counter, yet is not added to the Circuit Breaker's failure rate. Conversely, if you want a cumulative counter solely for outcomes Resilience4j actually recorded as failures, use the Circuit Breaker's event publisher or metrics provided by the integration and verify the corresponding events for your library version.

When the circuit is `OPEN`, `not-permitted calls` rises while `primary.attempts` may drop. This is expected behavior: the Circuit Breaker is blocking new requests to protect the dependency. Never interpret a sudden drop in primary calls as dependency recovery; cross-check breaker state and rejected call counts.

## Computing Ratios on Dashboards

With Prometheus, Micrometer typically converts dot-separated metric names to underscores and appends `_total` to counters. Verify actual names at your application's metrics endpoint. Using the example names, you can construct expressions like:

```promql
# Rate of operations requiring fallback over 5 minutes
sum(rate(catalog_fallback_invocations_total[5m]))
/
clamp_min(sum(rate(catalog_protected_operations_total[5m])), 1)

# Ratio of supplier exceptions out of supplier attempts
sum(rate(catalog_primary_exceptions_total[5m]))
/
clamp_min(sum(rate(catalog_primary_attempts_total[5m])), 1)

# Ratio of fallback handler errors out of fallback invocations
sum(rate(catalog_fallback_errors_total[5m]))
/
clamp_min(sum(rate(catalog_fallback_invocations_total[5m])), 1)
```

These expressions return ratios from 0 to 1; multiply by 100 if the dashboard displays percentages. `clamp_min` prevents division by zero during zero-traffic periods. If a dashboard filters by dependency or instance, apply the exact same filter to both numerator and denominator.

Display both absolute counts and percentages. For instance, 100% fallback on a single request might be an isolated event; 20% fallback across thousands of requests has very different operational implications. Choose time windows suited to traffic volume and condition alert thresholds on a minimum request count.

## Designing Dashboards That Do Not Mask Outages

A useful dashboard places these side by side:

- Fallback ratio over total protected operations.
- Fallback counts by `reason`, especially `circuit_open`.
- Primary call rate and latency.
- Circuit Breaker state and rejected call counts.
- Ratio of fallbacks returning cache, returning unavailable, and throwing errors.
- Age of cached data used and fallback latency.

When the fallback rate rises alongside `circuit_open` and Resilience4j's failure rate, the dependency may be degrading and the Circuit Breaker is protecting the system. When the fallback rate rises without failure rate rising, check the fallback policy, classified business errors, or rejections from another cause. When fallback handler errors rise, the backup path itself is having problems and requires a separate alert.

Never configure alerts solely around a low fallback rate. A zero rate might indicate good health, or it could mean fallback instrumentation never ran or requests bypassed the instrumented boundary. Check operation volume, fallback counters, and sample traces to confirm instrumentation is active.

## Testing Instrumentation

Test both the primary path and fallback branches, and assert counters increment exactly once per operation:

| Scenario | Protected operations | Primary attempts | Fallback invocations | Expected Outcome |
| --- | ---: | ---: | ---: | --- |
| Dependency returns success | +1 | +1 | No increase | Primary duration records `success`. |
| Dependency throws timeout | +1 | +1 | +1 | Primary exception and fallback response are recorded. |
| Circuit Breaker is `OPEN` | +1 | No increase | +1 | Reason is `circuit_open`; primary is not called. |
| Cache has valid data | +1 | Per primary branch | +1 when fallback runs | Fallback response has mode `cache`. |
| Cache has no data | +1 | Per primary branch | +1 when fallback runs | Fallback response has mode `unavailable`. |
| Cache also throws error | +1 | Per primary branch | +1 | Fallback error increments; error propagates per application contract. |

Beyond unit tests, run an integration scenario that drives the Circuit Breaker to `OPEN`, then send requests to confirm the supplier does not run and fallbacks are still measured. Inspect metrics after the request finishes; counters and timers may update at slightly different points depending on export behavior.

## Common Observability Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Monitoring only final HTTP 2xx/5xx. | A 200 fallback hides dependency failures. | Measure primary calls, fallbacks, and Circuit Breaker separately. |
| Dividing fallback invocations by primary attempts. | Ratio distorts when circuit opens because supplier does not run. | Use protected operations as denominator for fallback rate. |
| Equating primary exceptions with Circuit Breaker failure rate. | Misses differences between raw exceptions and recording predicates. | Cross-check application counters against Resilience4j metrics. |
| Merging cache and unavailable into one result. | Hides whether fallback actually had substitute data. | Attach a bounded mode tag to fallback responses. |
| Putting IDs or exception messages into metric tags. | Cardinality explodes and may leak data. | Use bounded cause groups; keep details in logs/traces. |
| Looking only at percentages without volume. | A handful of requests can trigger false alarms with high ratios. | Display volume and require a minimum sample count. |

Measuring fallbacks properly distinguishes three states: the dependency is serving normally, the application is returning degraded results to preserve user experience, and the fallback path itself is failing. By tracking fallbacks alongside primary attempts, Circuit Breaker metrics, and backup data status, dashboards reflect the true health of the dependency rather than merely the final response shown to users.
