# Distribution Statistic Expiry, Ring Buffers, and Maximum Values

An HTTP request takes 800 ms. Afterwards the service receives no further requests, yet the chart keeps showing `max = 800 ms` across several scrapes before dropping to 0. This can be normal behavior for a time-windowed maximum. To read the chart accurately, determine how long statistics retain samples, which mode the registry uses for export, and when the monitoring system scrapes.

## From a Single Measurement to Statistics with Different Lifetimes

Micrometer uses `Timer` for durations and `DistributionSummary` for non-time magnitudes, such as response sizes in bytes. Each meter is identified by name and tag set. A single recording on a `Timer` can update the measurement count (`count`), total time (`totalTime`), maximum (`max`), and distribution data if the corresponding configuration is enabled.

- **Time-windowed maximum** keeps the recent peak. When an old peak expires, `max` can drop to a smaller sample still inside the window, or to 0 if the window is empty.
- **Application-computed percentiles** rely on an internal rotating-buffer histogram. After an old sample expires, it no longer affects percentiles. Percentile values are estimates and can differ from the raw sample value even when there is only one observation.
- **Exported count, sum, and buckets** follow the registry's representation. For instance, with Prometheus, regular `Timer` histogram buckets are cumulative counters. Expiration of `max` happens independently of those counters.

## Two Parameters Controlling the Ring Buffer

`expiry` is the duration the rotation algorithm uses to periodically discard old data. `buffer-length` is the number of buckets in the ring buffer. Buckets are reused in turn. When rotating back to a bucket, that bucket's old data is cleared. Where a recording lands relative to rotation boundaries affects how long a sample continues contributing to statistics.

For basic `Timer` implementations in Micrometer 1.13, two mechanisms use the same configuration properties yet interpret rotation timing differently.

| Statistic | Mechanism | With `expiry=10s` and `buffer-length=3` |
| --- | --- | --- |
| `max()` using `TimeWindowMax` | Rotates one bucket after each `expiry`. A full cycle clearing all old data takes `expiry × buffer-length`. | Rotates every 10 seconds. Full cycle is 30 seconds. A peak recorded near the end of a bucket can expire in less than 30 seconds from when it was recorded. |
| Internal percentiles using `TimeWindowPercentileHistogram` | In Micrometer 1.13.0, the internal histogram rotates one bucket every `expiry / buffer-length`. | Rotates roughly every 3.33 seconds. Full cycle is about 10 seconds. |

The default `buffer-length` is 3 in core distribution configuration. The effective `expiry` also depends on the registry. For example, the Prometheus registry in Micrometer 1.13 uses the registry's `step` as the default `expiry`. This `step` is configured in the application. The interval between Prometheus scrapes is configured separately on the Prometheus server.

## Reading Maximum Values by Registry

| Registry and Export Mode | `Timer` Count and Sum | Meaning of Maximum |
| --- | --- | --- |
| `SimpleMeterRegistry` in `CUMULATIVE` mode | Cumulative since the meter was created. | `Timer.max(unit)` reads the peak remaining in `TimeWindowMax` and converts it to the requested unit. |
| `SimpleMeterRegistry` in `STEP` mode with `StepTimer` | Returns metrics for the most recently completed step interval. | `max()` uses its own rotating window. A just-completed interval can have `count = 0` while a peak from the previous interval still lingers. |
| Prometheus registry with a regular `Timer` | `_count` and `_sum` are cumulative. When exporting classic histograms, `_bucket` series are also cumulative across scrapes. | `_seconds_max` is a gauge in seconds. Each scrape reads the peak still present in the application's window at that moment. |
| OTLP registry 1.13 with Histogram data points | With cumulative temporality (`CUMULATIVE`), data points accumulate from the start time. With delta temporality (`DELTA`), data points describe the corresponding export interval. | Micrometer 1.13 only supports the `max` field on Histogram data points in `DELTA` mode. Therefore, when switching from Prometheus to OTLP, verify the temporality mode and actual fields received by the collector. |

Step-based export modes can vary between registries. The table describes the named implementations with `Timer` measuring completed operations. For `DistributionSummary`, when a registry exports a maximum, read the unit according to recorded values and the meter's unit or scale configuration.

## Configuration in Spring Boot

Example in `application.properties` applied to the `http.server.requests` HTTP meter of a web application using Actuator.

```properties
management.metrics.distribution.expiry.http.server.requests=10s
management.metrics.distribution.buffer-length.http.server.requests=3
```

The suffix is the Micrometer meter name in the application. Spring Boot's distribution properties apply by meter name prefix and prefer the longest matching prefix. Setting only these two properties changes how windowed statistics rotate. To export local percentiles or histograms, enable the specific statistic type needed. `maximum-expected-value` adjusts the bucket range published with percentile histograms, whereas `expiry` and `buffer-length` adjust the timing of rotating buffers.

When choosing an expiry for `max`, consider scrape or push intervals, gaps from heavy load, and how often observations occur. Keeping peaks longer gives the next collection a better chance to observe the peak, while also keeping stale peaks visible longer. Increasing buffer count can increase memory used by ring-buffered distribution statistics, especially when a meter has many tag combinations. Changing these two properties is also independent of data retention in the monitoring system.

## Verification with a Mock Clock

Standalone example on Java 17+ with `io.micrometer:micrometer-core:1.13.0` and runtime dependencies. Save as `TimerWindows.java`. The program records exactly one 800 ms sample per registry, then advances the clock to observe `count`, total time, `max`, and p95 change.

```java
import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.CountingMode;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

public class TimerWindows {
    public static void main(String[] args) {
        run(CountingMode.CUMULATIVE);
        run(CountingMode.STEP);
    }

    private static void run(CountingMode countingMode) {
        MockClock clock = new MockClock();
        SimpleConfig config = new SimpleConfig() {
            @Override
            public String get(String key) {
                return null;
            }

            @Override
            public CountingMode mode() {
                return countingMode;
            }

            @Override
            public Duration step() {
                return Duration.ofSeconds(10);
            }
        };

        SimpleMeterRegistry registry = new SimpleMeterRegistry(config, clock);
        try {
            Timer timer = Timer.builder("demo.latency")
                    .distributionStatisticExpiry(Duration.ofSeconds(10))
                    .distributionStatisticBufferLength(3)
                    .publishPercentiles(0.95)
                    .register(registry);

            timer.record(Duration.ofMillis(800));

            clock.add(Duration.ofSeconds(1));
            print(countingMode, 1, timer);

            clock.add(Duration.ofSeconds(10));
            print(countingMode, 11, timer);

            clock.add(Duration.ofSeconds(10));
            print(countingMode, 21, timer);

            clock.add(Duration.ofSeconds(10));
            print(countingMode, 31, timer);
        } finally {
            registry.close();
        }
    }

    private static void print(CountingMode mode, int elapsedSeconds, Timer timer) {
        double p95 = timer.takeSnapshot().percentileValues()[0].value(TimeUnit.MILLISECONDS);
        System.out.printf(Locale.ROOT, "%s t=%ds count=%d total=%.0fms max=%.0fms p95=%.0fms%n",
                mode, elapsedSeconds, timer.count(), timer.totalTime(TimeUnit.MILLISECONDS),
                timer.max(TimeUnit.MILLISECONDS), p95);
    }
}
```

In Bash, set `MICROMETER_CP` to the classpath containing the runtime JARs resolved by Maven or Gradle for `micrometer-core:1.13.0`, then run these two commands.

```bash
javac --release 17 -cp "$MICROMETER_CP" TimerWindows.java
java -cp ".:$MICROMETER_CP" TimerWindows
```

Program output with Micrometer 1.13.0.

```text
CUMULATIVE t=1s count=1 total=800ms max=800ms p95=772ms
CUMULATIVE t=11s count=1 total=800ms max=800ms p95=0ms
CUMULATIVE t=21s count=1 total=800ms max=800ms p95=0ms
CUMULATIVE t=31s count=1 total=800ms max=0ms p95=0ms
STEP t=1s count=0 total=0ms max=800ms p95=772ms
STEP t=11s count=1 total=800ms max=800ms p95=0ms
STEP t=21s count=0 total=0ms max=800ms p95=0ms
STEP t=31s count=0 total=0ms max=0ms p95=0ms
```

- At 1 second, `STEP` still returns the previous interval's count because the first 10-second interval is still in progress. `max` and p95 have already received the sample. The `772 ms` value is an estimate from the internal histogram, rounded to milliseconds when printed.
- At 11 seconds, the sample has left the percentile window while still contributing to `max`. `STEP` now reports one measurement belonging to the just-completed first interval.
- At 21 seconds, `STEP` reports a completed interval with no samples, while `max` is still 800 ms. By 31 seconds, `max` drops to 0 in both modes. `CUMULATIVE` retains the measurement count and total time. A `0` value for `max` or p95 in this run reflects that the corresponding window is empty.

## Verifying in Prometheus

With Actuator exposing the Prometheus endpoint and traffic flowing, compare `http_server_requests_seconds_max` and `http_server_requests_seconds_count` over the same label set. `max_over_time(http_server_requests_seconds_max[5m])` takes the highest gauge value **among the scraped points** of each series in 5 minutes. A peak may expire before the next scrape, or remain in the application's window from before the query interval. Consequently, the timestamp when the gauge is observed and when the slow request occurred can differ.

When seeing `_max` equal to 0, inspect the increase in `_count` over a suitable window to distinguish periods of low or zero traffic from genuinely low latency. If the entire series disappears, check scrape health and meter presence. On `_max`, use comparisons or maximum aggregations across gauge samples. `rate()` on `_count` measures request arrival rate.

## References

- [Spring Boot 3.3 — Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
- [Micrometer 1.13 — Timers](https://docs.micrometer.io/micrometer/reference/1.13/concepts/timers.html)
- [Micrometer — Difference Between max and Percentile Expiry](https://github.com/micrometer-metrics/micrometer/issues/3298)
- [Micrometer 1.13.15 — PrometheusMeterRegistry](https://github.com/micrometer-metrics/micrometer/blob/v1.13.15/implementations/micrometer-registry-prometheus/src/main/java/io/micrometer/prometheusmetrics/PrometheusMeterRegistry.java)
- [Micrometer 1.13 — OTLP](https://docs.micrometer.io/micrometer/reference/1.13/implementations/otlp)
- [Prometheus — Aggregation Over Time](https://prometheus.io/docs/prometheus/latest/querying/functions/#aggregation_over_time)
