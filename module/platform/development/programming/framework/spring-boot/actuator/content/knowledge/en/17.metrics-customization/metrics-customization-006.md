# Configuring Histograms, Percentiles, and Service-Level Objective Boundaries

A payment service with an average latency of 180 ms can still miss a target of **at least 95% of payments completing in 250 ms or less**. The average shows the mean time per request. To know how many requests meet the threshold, you need to count observations up to 250 ms. To understand tail latency, you can examine p95 or p99.

## Three Ways to Represent Distributions

| Micrometer Setting in Spring Boot | Data Collected | Question It Answers |
| --- | --- | --- |
| `percentiles` | Percentiles estimated by the application for each meter name and tag set. `0.95` is p95, the value around the 95th position of the sorted distribution. | What is the p95 of a single instance or a single tag set? |
| `percentiles-histogram` | Counters across thresholds chosen by Micrometer. The monitoring system can sum corresponding counters and estimate percentiles for the whole group. | What is the p95 across all payment-serving instances? |
| `slo` | Cumulative counters at specific boundaries, such as `250ms`. When percentiles-histogram is enabled on Prometheus, these boundaries are added to the bucket set. | How many requests completed in 250 ms or less? |

A **cumulative bucket** labeled `le="0.25"` counts every observation with duration **≤ 0.25 seconds**. Thus, a request taking exactly 100 ms is counted in both the 100 ms bucket and the 250 ms bucket. Subtracting the count at 100 ms from the count at 250 ms yields the number of requests in the interval (100 ms, 250 ms]. The `+Inf` bucket includes all observations and has the same count as `_count` in a classic Prometheus histogram.

The `250ms` threshold only creates a measurement boundary. A service-level objective (SLO) also needs a **target ratio**, an **eligible request set**, and an **evaluation window**. This example treats every request recorded by the timer as eligible. If a real target counts only successful and fast transactions as good, the numerator must select both success status and latency bucket. The denominator must match the definition of eligible requests.

## Configuring Spring Boot Actuator for Prometheus

The example uses Spring Boot 3.3, Micrometer 1.13, and classic Prometheus histograms. In a Spring Boot Web application, include `spring-boot-starter-actuator` and `io.micrometer:micrometer-registry-prometheus` managed by Spring Boot's dependency management. For local testing, add these lines to `application.properties`:

~~~properties
management.endpoints.web.exposure.include=health,metrics,prometheus
management.metrics.distribution.percentiles-histogram.checkout.duration=true
management.metrics.distribution.minimum-expected-value.checkout.duration=5ms
management.metrics.distribution.maximum-expected-value.checkout.duration=2s
management.metrics.distribution.slo.checkout.duration=100ms,250ms,500ms
~~~

- `checkout.duration` is the `Timer` name in Micrometer. Use that name in configuration and when inspecting `/actuator/metrics/checkout.duration`. When exported to Prometheus, the timer has base name `checkout_duration_seconds` and buckets use seconds.
- Spring Boot applies each distribution property by meter name prefix and prefers the longest matching prefix. For timers, specify `ms` or `s` explicitly. For `DistributionSummary`, boundaries are numeric in the unit of the recorded quantity, such as bytes.
- `minimum-expected-value` and `maximum-expected-value` bound the range of auto-generated buckets, helping control time series count. They do not discard samples outside the range; samples exceeding the highest finite boundary still appear in `+Inf` and `_count`. Setting too narrow a range loses resolution in the tail when estimating percentiles.
- If you only track ratios at fixed thresholds, set `percentiles-histogram.checkout.duration=false` and keep `slo` to export only the declared finite buckets. If you need to test client-computed percentiles separately, disable histograms, remove `slo` for the meter, and set `management.metrics.distribution.percentiles.checkout.duration=0.95,0.99`. With the Prometheus registry in this example, when histograms are enabled, the meter is represented by buckets; compute percentiles by querying the buckets.

For Actuator's automatic HTTP latency, you can apply the same configuration style to the default meter name `http.server.requests`. When querying, select the route set and statuses matching the objective definition. In deployed environments, configure endpoint access permissions according to the monitoring system's scope.

## Testing with Five Observations Having Verifiable Output

In a test application that already has an `@SpringBootApplication` class, place the class below in the same package as the startup class or in a subpackage scanned by Spring. Change `package example;` to match the application's package. When the application starts, `ApplicationRunner` records five simulated durations into `Timer` so results are repeatable without depending on network speed or `Thread.sleep`.

~~~java
package example;

import java.time.Duration;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CheckoutMetricsSample {
    @Bean
    ApplicationRunner recordCheckoutSamples(MeterRegistry registry) {
        return args -> {
            Timer timer = registry.timer("checkout.duration");
            for (long millis : new long[] {80, 100, 250, 400, 700}) {
                timer.record(Duration.ofMillis(millis));
            }
        };
    }
}
~~~

Once the application is running on port 8080, fetch the scrape output:

~~~bash
curl -fsS http://localhost:8080/actuator/prometheus
~~~

Look for the following lines. The histogram also has auto-generated buckets, so this is only the subset to compare. Line order and numeric formatting may differ.

~~~text
checkout_duration_seconds_bucket{le="0.1"} 2
checkout_duration_seconds_bucket{le="0.25"} 3
checkout_duration_seconds_bucket{le="0.5"} 4
checkout_duration_seconds_bucket{le="+Inf"} 5
checkout_duration_seconds_count 5
checkout_duration_seconds_sum 1.53
~~~

**3/5 = 60%** of requests completed in 250 ms or less. The two samples at the exact boundaries 100 ms and 250 ms confirm the `≤` rule. Five samples are enough to verify the counting mechanism. Evaluating percentiles or SLOs requires many more observations.

## Computing p95 and SLO Attainment Across Multiple Instances

Assume instances belong to the same Prometheus job `checkout`, export the same set of bucket boundaries, and receive traffic during the measurement window. To inspect p95 for the entire job over the last 5 minutes:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(checkout_duration_seconds_bucket{job="checkout"}[5m])
  )
)
~~~

Apply `rate` to each series before summing so Prometheus handles counter resets when an application restarts. Keep the `le` label so the function knows each bucket boundary. The result is in seconds and is an **estimate**, because Prometheus interpolates within the finite bucket containing the quantile. Aggregated instances must share the same set of boundaries. When changing boundaries across deployments, verify versions are aligned before interpreting combined p95.

To compute the attainment ratio at the chosen boundary, divide the increase rate of requests `≤ 250 ms` by the increase rate of total requests, with the same filter and window:

~~~promql
sum(rate(checkout_duration_seconds_bucket{job="checkout", le="0.25"}[5m]))
/
sum(rate(checkout_duration_seconds_count{job="checkout"}[5m]))
~~~

The result is a ratio from 0 to 1. The bucket at the exact boundary gives the count of good requests. `rate` estimates counter increase rate from scrapes within the window. If the denominator is 0 or there are not enough scrapes yet, display a no-data state. A 5-minute window is convenient for quick observation; for periodic SLO evaluation, use the window specified by the target and compare the ratio against `0.95`.

For instance, one instance has 90/100 requests within threshold and another instance has 10/10. The group achieves 100/110 ≈ **90.9%**. Averaging the two ratios yields 95% because that calculation assigns equal weight to both instances despite different request counts. Similarly, averaging per-instance p95 values exported by individual applications does not reproduce the p95 of the combined observation set.

## Checking Costs and Configuration Mistakes

- **No buckets appear.** Check the Prometheus registry, endpoint access permissions, meter name, and whether the timer has recorded observations. Use `/actuator/metrics/checkout.duration` to confirm the meter, then check buckets and units at `/actuator/prometheus`.
- **Expected boundary series missing in query.** Check the actual `le` label in Prometheus. `250ms` in timer configuration corresponds to 0.25 seconds on export; the example query uses `le="0.25"`.
- **Time series count grows rapidly.** Each bucket adds another series per label combination. Prefer enabling for specific meter groups that need measurement, use labels with finite cardinality, and avoid transaction IDs in tags. Check bucket resolution around the region of interest before narrowing the range or switching to exporting only SLO thresholds.

### References

- [Spring Boot 3.3 – Per-meter Metrics Configuration](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
- [Micrometer 1.13 – Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/1.13/concepts/histogram-quantiles.html)
- [Prometheus – Histograms and Summaries](https://prometheus.io/docs/practices/histograms/)