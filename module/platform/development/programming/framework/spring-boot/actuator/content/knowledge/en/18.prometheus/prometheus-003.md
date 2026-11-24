## Reading Converted Metric Names, Labels, Units, and Suffixes

A meter named `http.server.requests` in Spring Boot can appear in Prometheus under multiple names, such as `http_server_requests_seconds_count` and `http_server_requests_seconds_sum`. These two lines describe two different measurements of the same `Timer`. To read a line accurately, identify the original meter name, the label set, the unit of the value, and the meaning of the suffix.

### From Micrometer ID to time series

With the default configuration of `micrometer-registry-prometheus` in Micrometer 1.13, dot-separated meter names are typically converted to underscore-separated names. Export rules also depend on the meter type and unit. For example, the `Timer` `demo.checkout.duration` has the metric family `demo_checkout_duration_seconds`. A gauge `demo.checkout.queue.memory` with a base unit of `bytes` can be exported as `demo_checkout_queue_memory_bytes`. Renaming filters or custom naming conventions can change the output. Read the actual names on the endpoint before writing queries.

A label is a key–value pair inside curly braces. Micrometer may normalize the tag key `payment.channel` to `payment_channel` upon export. The value `web` remains the value of that dimension. To Prometheus, the series name plus the entire label set identifies a time series. Two lines with the same name having `payment_channel="web"` and `payment_channel="mobile"` are two distinct series. Reordering labels on the same line does not create a new series. Each new label value can increase the number of series, so prefer bounded values such as payment channel or route template rather than order IDs or URLs containing IDs.

The `job` and `instance` labels are typically attached by Prometheus when scraping according to the target configuration. They can appear in PromQL results even though the application does not print them in `/actuator/prometheus`. The `le` and `quantile` labels have meanings defined by the histogram or summary type, distinct from business labels.

### What do units and suffixes tell you?

| Name or suffix | Value to read | Example |
| --- | --- | --- |
| `_total` | Cumulative value of a Counter. The counter may reset when the process restarts. | `demo_checkout_attempts_total 3` is three cumulative attempts. |
| `_count` | Cumulative observation count of a Timer or distribution. The unit is count even if the family name contains `_seconds` or `_bytes`. | `demo_checkout_duration_seconds_count 2` is two measurements. |
| `_sum` | Sum of observed values, in the metric family's unit. | `demo_checkout_duration_seconds_sum 0.2` is 0.2 seconds in total. |
| `_bucket{le="..."}` | Number of measurements less than or equal to the bucket's upper bound in a classic histogram. The `le` threshold uses the measured quantity's unit, while the line value is a count. | With `le="0.1"`, a value of `1` means one measurement did not exceed 100 ms. |
| `_max` | Gauge exported by Micrometer's Prometheus registry for distribution meters such as Timer. This is the maximum value over the meter's statistical window. | `demo_checkout_duration_seconds_max 0.16` is 160 ms. |
| `{quantile="..."}` on a summary family name | Quantile computed by the application when configured to export quantiles this way. The line value has the unit of the measured quantity. | `quantile="0.95"` selects the p95 estimate. Averaging p95 across multiple instances does not yield the system-wide p95. |
| Unit suffix such as `_bytes` | For a memory Gauge, the value is the number of bytes at read time. A Gauge can go up or down. | `demo_checkout_queue_memory_bytes 2048` is 2,048 bytes, equivalent to 2 KiB. |

`_seconds` describes the unit of duration. For example, when recording `Duration.ofMillis(160)` into a `Timer`, this duration corresponds to 0.16 seconds when exported. For a custom Gauge or `DistributionSummary`, `baseUnit("bytes")` declares the unit. The value supplied by application code must actually be in bytes. If code passes 2 meaning 2 KiB, merely adding `baseUnit("bytes")` will cause the output to be interpreted as 2 bytes.

Check the `# TYPE` line to distinguish `counter`, `gauge`, `summary`, and `histogram`. `# HELP` explains the metric when a description is exported. These lines are metadata. A Timer can export `_count` and `_sum` even without buckets. The `_bucket` lines in the example below come from configured SLO milestones. For a classic histogram, `le="+Inf"` includes all measurements and therefore equals `_count` if the remaining labels are identical.

### Cross-checking with two measurements

Save the following program as `MetricReadingDemo.java`. The program runs in a simple Micrometer registry to inspect the original names, tags, and values before export.

```java
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicLong;

import static java.util.concurrent.TimeUnit.SECONDS;

public class MetricReadingDemo {
    public static void main(String[] args) {
        var registry = new SimpleMeterRegistry();
        try {
            var timer = Timer.builder("demo.checkout.duration")
                    .tag("payment.channel", "web")
                    .serviceLevelObjectives(Duration.ofMillis(100), Duration.ofMillis(250))
                    .register(registry);
            timer.record(Duration.ofMillis(40));
            timer.record(Duration.ofMillis(160));

            var attempts = registry.counter("demo.checkout.attempts", "payment.channel", "web");
            attempts.increment(3);
            var queuedBytes = new AtomicLong(2048);
            var gauge = Gauge.builder("demo.checkout.queue.memory", queuedBytes, AtomicLong::get)
                    .baseUnit("bytes")
                    .register(registry);

            var snapshot = timer.takeSnapshot();
            System.out.printf(Locale.ROOT, "%s %s=%s count=%d sumSeconds=%.3f maxSeconds=%.3f%n",
                    timer.getId().getName(), "payment.channel", timer.getId().getTag("payment.channel"),
                    snapshot.count(), snapshot.total(SECONDS), snapshot.max(SECONDS));
            for (var bucket : snapshot.histogramCounts()) {
                System.out.printf(Locale.ROOT, "boundarySeconds=%.3f count=%.0f%n",
                        bucket.bucket(SECONDS), bucket.count());
            }
            System.out.printf(Locale.ROOT, "%s=%.0f%n", attempts.getId().getName(), attempts.count());
            System.out.printf(Locale.ROOT, "%s=%.0f %s%n",
                    gauge.getId().getName(), gauge.value(), gauge.getId().getBaseUnit());
        } finally {
            registry.close();
        }
    }
}
```

Use JDK 17 or later. Resolve `io.micrometer:micrometer-core:1.13.0` and its dependencies with Maven or Gradle, then set `CP` to the classpath containing the JAR files. The following commands use Bash. In PowerShell, reference the variable as `$env:CP` and use `;` as the classpath separator.

```bash
javac -cp "$CP" MetricReadingDemo.java
java -cp ".:$CP" MetricReadingDemo
```

Program output:

```text
demo.checkout.duration payment.channel=web count=2 sumSeconds=0.200 maxSeconds=0.160
boundarySeconds=0.100 count=1
boundarySeconds=0.250 count=2
demo.checkout.attempts=3
demo.checkout.queue.memory=2048 bytes
```

If the same meters are registered and the same data is recorded into the default Prometheus registry of Micrometer 1.13, the output can be read as in the following illustrative sample. The sample omits metadata to focus on the series.

```text
# TYPE demo_checkout_duration_seconds histogram
demo_checkout_duration_seconds_bucket{payment_channel="web",le="0.1"} 1
demo_checkout_duration_seconds_bucket{payment_channel="web",le="0.25"} 2
demo_checkout_duration_seconds_bucket{payment_channel="web",le="+Inf"} 2
demo_checkout_duration_seconds_count{payment_channel="web"} 2
demo_checkout_duration_seconds_sum{payment_channel="web"} 0.2
# TYPE demo_checkout_duration_seconds_max gauge
demo_checkout_duration_seconds_max{payment_channel="web"} 0.16
demo_checkout_attempts_total{payment_channel="web"} 3
# TYPE demo_checkout_queue_memory_bytes gauge
demo_checkout_queue_memory_bytes 2048
```

Between the 40 ms and 160 ms samples, only the 40 ms sample satisfies `le="0.1"` and both satisfy `le="0.25"`. Buckets are cumulative, so subtracting `2 − 1` indicates there is one sample in the range above 100 ms up to and including 250 ms. The total duration of 0.2 seconds divided by 2 measurements gives an average of 0.1 seconds each. `_max` indicates the largest value still within the statistical window. It can decrease over time, so read it as a Gauge.

### Finding the right series in a Spring Boot application

With Actuator and `io.micrometer:micrometer-registry-prometheus` in the web application, expose both endpoints to cross-check in a test environment:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
```

After generating data for the meter you want to inspect, query the original name on the diagnostic endpoint and find the metric family in the scrape output. For example, with JVM buffer memory and the default Actuator path:

```bash
curl -fsS 'http://localhost:8080/actuator/metrics/jvm.buffer.memory.used?tag=id:direct'
curl -fsS 'http://localhost:8080/actuator/prometheus' | grep '^jvm_buffer_memory_used_bytes'
```

The Spring Boot 3.3 API documentation includes the line `jvm_buffer_memory_used_bytes{id="direct"} 45056.0`. Read that line as the `direct` buffer pool currently using 45,056 bytes at the time of the scrape. Values on a running application change according to JVM state. For business metrics, use the same cross-checking approach and keep tag keys consistent across meters of the same name. If a label combination is missing, check whether the meter has been registered and whether its tag keys differ from other meters with the same name.

In PromQL, select the right series for the goal. For example, the 5-minute average checkout duration for the web channel across instances of a service:

```promql
sum(rate(demo_checkout_duration_seconds_sum{job="checkout",payment_channel="web"}[5m]))
/
sum(rate(demo_checkout_duration_seconds_count{job="checkout",payment_channel="web"}[5m]))
```

Take `rate` on each series before summing to handle counter resets. The numerator is seconds of recorded duration per second and the denominator is measurements per second, so the ratio is seconds per measurement when traffic is present. If a dashboard needs milliseconds, multiply the entire ratio by 1,000. If the goal is the completion ratio within 250 ms, use the increase rate of the `_bucket` series with `le="0.25"` in the numerator and keep the increase rate of `_count` in the denominator. The value of `le` in the query must match the label stored by Prometheus.

### References

- [Spring Boot 3.3 — Prometheus endpoint output example](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/prometheus.html)
- [Spring Boot 3.3 — Endpoint for looking up meter names and tags](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html)
- [Micrometer 1.13 — Prometheus integration and meter types](https://docs.micrometer.io/micrometer/reference/1.13/implementations/prometheus.html)
- [Micrometer 1.13.0 — Source code of naming conventions for Prometheus](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/implementations/micrometer-registry-prometheus/src/main/java/io/micrometer/prometheusmetrics/PrometheusNamingConvention.java)
- [Prometheus — Metric names, labels, and units](https://prometheus.io/docs/practices/naming/)