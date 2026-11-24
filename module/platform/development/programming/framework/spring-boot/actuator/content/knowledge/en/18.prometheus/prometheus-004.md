# Understanding count, sum, and buckets of Timer or DistributionSummary

Four calls take 100, 200, 500, and 800 ms respectively. From that, three questions can be answered. How many calls were measured? What is the total duration? How many calls fell within a threshold? In Prometheus, read the `_count`, `_sum`, and `_bucket` series of a classic histogram to answer each question.

## Choosing a meter based on the quantity to measure

| Micrometer Meter | What is each observation? | What does `_count` count? | What does `_sum` sum? |
| --- | --- | --- | --- |
| `Timer` | Duration of an operation. Recorded using `Duration` or with a `TimeUnit`. | Number of durations recorded. | Total duration. The Prometheus registry exports in seconds. |
| `DistributionSummary` | A numeric value such as response size in bytes. | Number of values recorded. | Total value in the measured unit, such as total bytes. |

`_count` only counts the times the meter receives an observation. For example, if the program records the size once per response, `_count` is the number of responses measured. A timer's `_sum` is the sum of each call's duration, so when calls run concurrently, the sum can exceed wall-clock elapsed time.

`DistributionSummary` is the meter type name in Micrometer. When exporting buckets to Prometheus, this meter can be exported as a histogram. Use `Timer` when measuring duration so Micrometer converts to the proper unit for the monitoring system.

## Reading the series of a classic histogram

Suppose `demo.request.duration` is a timer that recorded the four durations above and is configured with two boundaries: 200 ms and 500 ms. The relevant portion in the Prometheus export data looks like:

~~~text
demo_request_duration_seconds_count 4
demo_request_duration_seconds_sum 1.6
demo_request_duration_seconds_bucket{le="0.2"} 2
demo_request_duration_seconds_bucket{le="0.5"} 3
demo_request_duration_seconds_bucket{le="+Inf"} 4
~~~

`le` means *less than or equal*, i.e., **less than or equal to**. The `le="0.5"` bucket counts all three calls of 100, 200, and 500 ms. Because buckets are nested, **subtract** two adjacent buckets to count the calls between two boundaries.

| Question | How to read | Result |
| --- | --- | --- |
| How many calls took at most 200 ms? | Bucket `le="0.2"`. | 2 calls |
| How many calls took more than 200 ms and at most 500 ms? | Bucket `le="0.5"` minus bucket `le="0.2"`. | 3 − 2 = 1 call |
| How many calls took more than 500 ms? | `_count` minus bucket `le="0.5"`. | 4 − 3 = 1 call |
| Average latency of the four calls? | `_sum / _count`. | 1.6 s / 4 = 0.4 s, or 400 ms |

The `+Inf` bucket covers all observations. Within the same histogram and same label set, its value equals `_count`. With a `DistributionSummary` measuring bytes, the reading method is identical. If there are four samples of 256, 1024, 1024, and 4096 bytes, then `_count` is 4, `_sum` is 6400 bytes, and bucket `le="1024"` is 3.

`_count` and `_sum` can still appear when buckets are not enabled. If you need to count at specific boundaries, configure `serviceLevelObjectives(...)` when registering the meter or `management.metrics.distribution.slo` by meter name in Spring Boot. Queries by `le` must use the actual exported boundary in the right unit. For example, a timer boundary of `200ms` is exported as `le="0.2"`.

## Hands-on with two meters and fixed data

The standalone Java example uses `micrometer-core`. It uses `SimpleMeterRegistry` to print measurements and finite buckets right inside the process. In a Prometheus registry, the same observations and boundaries yield the corresponding measurements as in the example above, along with the `+Inf` bucket of the export format.

Create `build.gradle` in a separate test directory:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.micrometer:micrometer-core:1.13.0'
}

application {
    mainClass = 'example.MeterSnapshotDemo'
}
~~~

Create `src/main/java/example/MeterSnapshotDemo.java`:

~~~java
package example;

import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public class MeterSnapshotDemo {
    public static void main(String[] args) {
        var registry = new SimpleMeterRegistry(SimpleConfig.DEFAULT, new MockClock());
        try {
            Timer timer = Timer.builder("demo.request.duration")
                    .serviceLevelObjectives(Duration.ofMillis(200), Duration.ofMillis(500))
                    .register(registry);

            DistributionSummary payload = DistributionSummary.builder("demo.response.size")
                    .baseUnit("bytes")
                    .serviceLevelObjectives(512, 1024)
                    .register(registry);

            for (long millis : new long[] {100, 200, 500, 800}) {
                timer.record(Duration.ofMillis(millis));
            }
            for (int bytes : new int[] {256, 1024, 1024, 4096}) {
                payload.record(bytes);
            }

            System.out.printf(Locale.ROOT, "Timer count=%d sum=%.3f s%n",
                    timer.count(), timer.totalTime(TimeUnit.SECONDS));
            for (var bucket : timer.takeSnapshot().histogramCounts()) {
                System.out.printf(Locale.ROOT, "  le=%.3f s count=%.0f%n",
                        bucket.bucket(TimeUnit.SECONDS), bucket.count());
            }

            System.out.printf(Locale.ROOT, "Summary count=%d sum=%.0f bytes%n",
                    payload.count(), payload.totalAmount());
            for (var bucket : payload.takeSnapshot().histogramCounts()) {
                System.out.printf(Locale.ROOT, "  le=%.0f bytes count=%.0f%n",
                        bucket.bucket(), bucket.count());
            }
        } finally {
            registry.close();
        }
    }
}
~~~

With JDK 17 or later and a compatible Gradle version, run `gradle -q run`. Program output:

~~~text
Timer count=4 sum=1.600 s
  le=0.200 s count=2
  le=0.500 s count=3
Summary count=4 sum=6400 bytes
  le=512 bytes count=1
  le=1024 bytes count=3
~~~

To self-check, add one more call of exactly 500 ms. `Timer count` increases to 5, `sum` to 2.100 seconds, and the 500 ms bucket increases to 4. The 200 ms bucket still counts 2 calls.

## From cumulative measurements to windowed questions

In Prometheus, directly reading `_sum / _count` computes the average of cumulative measurements in the series being viewed. If the application has been running for many hours and the question only concerns the last 5 minutes, use the increase rate of both series in the same window. The example below aggregates instances belonging to the same `demo` job:

~~~promql
sum(rate(demo_request_duration_seconds_sum{job="demo"}[5m]))
/
sum(rate(demo_request_duration_seconds_count{job="demo"}[5m]))
~~~

The numerator is seconds of duration recorded per second. The denominator is calls recorded per second. The result is **seconds per call**. Sum the measurements of each instance before dividing so that an instance handling more calls is weighted appropriately. Apply `rate` to each series before summing to handle counter resets when a process restarts.

To compute the ratio of calls taking at most 200 ms in the same window, use the bucket as the numerator:

~~~promql
sum(rate(demo_request_duration_seconds_bucket{job="demo", le="0.2"}[5m]))
/
sum(rate(demo_request_duration_seconds_count{job="demo"}[5m]))
~~~

Both sides must select the same set of measured calls. When aggregating across multiple instances, every series in the denominator must have a corresponding bucket in the numerator. If the denominator is 0 or the window lacks samples to compute a rate, display a missing-data state. Both queries use the same principle for a meter measuring size, except the average calculation then has units of bytes per call.

### References

- [Micrometer 1.13 – Timer and duration units](https://docs.micrometer.io/micrometer/reference/1.13/concepts/timers.html)
- [Micrometer 1.13 – Histogram boundaries](https://docs.micrometer.io/micrometer/reference/1.13/concepts/histogram-quantiles.html)
- [Prometheus – Histograms and summaries](https://prometheus.io/docs/practices/histograms/)