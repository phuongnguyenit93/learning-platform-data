## Limiting Value Ranges to Control Bucket Count and Storage Cost

A `Timer` measuring checkout duration typically sees results from tens to hundreds of milliseconds. If a histogram exports many thresholds in regions of little use for queries, Prometheus still scrapes the corresponding time series on every scrape. `minimum-expected-value` and `maximum-expected-value` let you choose the useful threshold range for a meter. In exchange, regions below the lowest threshold and above the highest finite threshold have less detail about distribution shape.

### What Does the Expected Value Range Bound?

When `percentiles-histogram` is enabled on a registry that supports aggregatable histograms, Micrometer takes the auto-generated boundaries falling within the expected range, adds the two endpoints, and merges them with any service-level objective (`slo`) boundaries. Duplicate boundaries appear only once. `slo` can add boundaries **outside the expected range**, so budget calculations for bucket count must include those boundaries too. If exporting only `slo` buckets with `percentiles-histogram` disabled, the two expected endpoints do not automatically create extra buckets.

With classic Prometheus histograms, the `le` label is an **inclusive upper bound**. Counters are cumulative. An 80 ms measurement is counted in `le="0.3"`, `le="1.0"`, and `le="+Inf"` because it lies below all three boundaries. Observations are still recorded at their actual values:

- A 2 ms measurement still contributes to the `le="0.01"` bucket if 10 ms is the first finite boundary. We can count measurements of 10 ms or less, but lack detail inside that region.
- A 2.3 s measurement still contributes to `_count`, `_sum`, and `le="+Inf"` if the highest finite boundary is 1 s. It does not contribute to `le="1.0"`. The difference between `+Inf` and the last finite boundary tells how many measurements exceeded that boundary, though buckets do not show how much slower they were.

If enough measurements fall into the top `+Inf` bucket that p99 lands in that bucket, Prometheus `histogram_quantile` returns the highest finite boundary. Dashboards may show p99 as 1 s even though the true p99 lies above 1 s. For a specific operational threshold such as 300 ms, keeping the `le="0.3"` bucket lets you directly count measurements meeting the threshold without interpolating from neighboring buckets.

### Configuration in Spring Boot Actuator

The following example applies to a Spring Boot 3.3 web application with `spring-boot-starter-actuator`, `micrometer-registry-prometheus`, and a registered `Timer` named `demo.checkout.duration`. The YAML snippet exposes the Prometheus endpoint for verification in a test environment.

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
  metrics:
    distribution:
      percentiles-histogram:
        "[demo.checkout.duration]": true
      minimum-expected-value:
        "[demo.checkout.duration]": 10ms
      maximum-expected-value:
        "[demo.checkout.duration]": 1s
      slo:
        "[demo.checkout.duration]": 300ms
```

Use the original Micrometer meter name in configuration keys. In Prometheus, the example `Timer` exports lines starting with `demo_checkout_duration_seconds_`, with boundaries `10ms`, `300ms`, and `1s` expressed in seconds. Spring Boot configuration looks up by name or dot-separated prefix segments, preferring the more specific key for each property. Choose a narrow enough prefix to avoid enabling histograms on unintended meters. For `DistributionSummary`, specify boundaries numerically in the unit of recorded data (after applying `scale`, if any), such as `512` and `65536` for sizes in bytes.

If dashboards only need the ratio of checkouts within 300 ms, you can set `percentiles-histogram` to `false` and keep the `300ms` boundary in `slo` for this meter. Then the classic histogram still has the 300 ms and `+Inf` boundaries. A single finite boundary like that provides very little information for estimating p95 or p99.

### Experiment with the Same Five Measurements

Save the following program as `BucketRangeDemo.java`. The example uses histogram counters directly in Micrometer Core 1.13.0 to observe finite boundaries before exporting to Prometheus. Boundaries passed into `DistributionStatisticConfig` in the program use nanoseconds because the meter is a `Timer`.

```java
import io.micrometer.core.instrument.Clock;
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.Tags;
import io.micrometer.core.instrument.cumulative.CumulativeTimer;
import io.micrometer.core.instrument.distribution.CountAtBucket;
import io.micrometer.core.instrument.distribution.DistributionStatisticConfig;
import io.micrometer.core.instrument.distribution.pause.NoPauseDetector;

import java.time.Duration;
import java.util.Arrays;

import static java.util.concurrent.TimeUnit.MILLISECONDS;

public class BucketRangeDemo {
    public static void main(String[] args) {
        run("wide", Duration.ofMillis(1), Duration.ofSeconds(30));
        run("narrow", Duration.ofMillis(10), Duration.ofSeconds(1));
    }

    private static void run(String label, Duration min, Duration max) {
        var config = DistributionStatisticConfig.builder()
                .percentilesHistogram(true)
                .minimumExpectedValue((double) min.toNanos())
                .maximumExpectedValue((double) max.toNanos())
                .serviceLevelObjectives((double) Duration.ofMillis(300).toNanos())
                .build()
                .merge(DistributionStatisticConfig.DEFAULT);
        var id = new Meter.Id("demo.checkout.duration", Tags.empty(),
                null, null, Meter.Type.TIMER);
        var timer = new CumulativeTimer(
                id, Clock.SYSTEM, config, new NoPauseDetector(), MILLISECONDS, true);

        for (long sample : new long[] {2, 80, 220, 900, 2300}) {
            timer.record(sample, MILLISECONDS);
        }

        var snapshot = timer.takeSnapshot();
        var buckets = snapshot.histogramCounts();
        System.out.printf("%s buckets=%d count=%d totalMs=%d le300=%d%n",
                label, buckets.length, snapshot.count(),
                (long) snapshot.total(MILLISECONDS), countAt(buckets, 300));
        if ("narrow".equals(label)) {
            System.out.printf("narrow le10=%d le1000=%d above1000=%d%n",
                    countAt(buckets, 10), countAt(buckets, 1000),
                    snapshot.count() - countAt(buckets, 1000));
        }
    }

    private static long countAt(CountAtBucket[] buckets, long millis) {
        double nanos = Duration.ofMillis(millis).toNanos();
        return (long) Arrays.stream(buckets)
                .filter(bucket -> bucket.bucket() == nanos)
                .findFirst()
                .orElseThrow()
                .count();
    }
}
```

Use JDK 17 or higher. Set `CP` to a classpath containing `io.micrometer:micrometer-core:1.13.0` and its runtime dependencies resolved by Maven or Gradle. From the directory containing the source file, compile and run in Bash with the following commands. In PowerShell, use `$env:CP` and `;` to separate classpath entries.

```bash
javac -cp "$CP" BucketRangeDemo.java
java -cp ".:$CP" BucketRangeDemo
```

Output for the five measurements 2, 80, 220, 900, and 2,300 ms:

```text
wide buckets=69 count=5 totalMs=3502 le300=3
narrow buckets=34 count=5 totalMs=3502 le300=3
narrow le10=1 le1000=4 above1000=1
```

Narrowing the range from 1 ms–30 s down to 10 ms–1 s reduces finite buckets from 69 to 34, while measurement count and total time remain 5 and 3,502 ms respectively. Both ranges count 3/5 measurements meeting the 300 ms threshold. In the narrow range, the difference `5 − 4 = 1` indicates one measurement exceeded 1 s. When exported to Prometheus, the 34 finite buckets in the experiment correspond to 35 `_bucket` lines if `+Inf` is included.

### Estimating Cost and Choosing Limits

For a classic histogram with **B finite boundaries**, each meter label set on one scrape target creates **B + 3** series for the histogram: B finite boundary series, one `+Inf` series, one `_count`, and one `_sum`. Count extra series separately if the exporter also publishes measurements such as `_max`. For example, 20 actual label combinations per target across 15 targets yield 300 label sets after adding target labels. Reducing from 69 to 34 finite boundaries saves `(69 − 34) × 300 = 10,500` active scraped series for that meter. At the same scrape interval, the number of samples ingested per cycle decreases proportionally. Storage savings in bytes also depend on retention, compression, and storage backend. Boundary count and label combination count are two separate factors. Narrowing the expected range does not reduce the number of label combinations.

1. **Choose boundaries that answer what you need.** Base them on data from normal hours as well as peak load, alert thresholds, service-level objectives, and maximum timeouts. Set the lower bound low enough to distinguish meaningful fast-response regions. Set the upper bound high enough to observe slow regions dashboards need to distinguish. Keep SLO boundaries explicit with `slo`.
2. **Count before and after under the same load and label set.** Read `/actuator/prometheus` on a test target, filter for `demo_checkout_duration_seconds_bucket`, and count lines for the same label set. Check `+Inf`, `_count`, `_sum`, and the 300 ms boundary against known data. The `/actuator/metrics/demo.checkout.duration` endpoint is useful for inspecting the meter, though it does not list Prometheus bucket lines.
3. **Inspect the tail via count difference.** Subtract the increase rate of the last finite bucket from the increase rate of the `+Inf` bucket to see how many requests per second exceeded that boundary. Divide that difference by the `_count` increase rate to get the ratio when traffic exists. If the ratio exceeding 1 s is frequently above 1% and p99 is an operational metric, you need a higher finite boundary so p99 can distinguish those slow requests.
4. **Aggregate instances using the same boundary set.** During rolling configuration updates, different boundaries may be reported by different subsets of instances. Only aggregate histograms from instances sharing the same boundary set. Evaluate p95 or p99 after configuration has converged, or keep the two instance subsets separate while comparing.

Example query for the ratio of checkouts completing within 300 ms across instances of the same application. Apply `rate` to each series before summing to handle counter resets on application restart. Use the exact `le` label value Prometheus stores for the 0.3 s boundary.

```promql
sum(rate(demo_checkout_duration_seconds_bucket{job="checkout",le="0.3"}[5m]))
/
sum(rate(demo_checkout_duration_seconds_count{job="checkout"}[5m]))
```

### References

- [Spring Boot 3.3 Actuator — Per-meter Configuration](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.customizing.per-meter-properties)
- [Micrometer 1.13.0 — How Histogram and SLO Boundaries Are Merged](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/distribution/DistributionStatisticConfig.java)
- [Prometheus — Classic Histograms and Computing Quantiles](https://prometheus.io/docs/practices/histograms/)