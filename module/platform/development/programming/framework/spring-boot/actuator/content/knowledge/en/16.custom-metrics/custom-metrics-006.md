# Measuring Size Distributions with DistributionSummary

## 1. From an Individual Size to the Shape of Data

Suppose a service generates JSON messages. Some messages are only a few hundred bytes, while others reach tens of thousands of bytes. Knowing only “10,000 messages were generated” does not reveal how much data must be transmitted. Knowing only the total bytes also does not tell you whether most messages are small or a few are huge.

**Micrometer's DistributionSummary records a non-negative quantity per observation**, and then aggregates those observations. The quantity is typically a size, the number of items in a batch, or a clearly defined ratio. A call like `record(500)` can mean “this message is 500 bytes long.”

This lesson belongs to custom metrics in Spring Boot Actuator. The relationship between components is:

```text
Business logic identifies one observation
    -> DistributionSummary.record(size)
    -> MeterRegistry aggregates
    -> Actuator enables inspection
    -> registry exports data to monitoring system if configured
```

Micrometer provides the measurement instrument; the application decides what to measure and when; Actuator exposes access to metrics in a Spring Boot application. The [Micrometer Distribution Summaries documentation](https://docs.micrometer.io/micrometer/reference/1.18/concepts/distribution-summaries.html) uses response size as a typical case. The Java examples below are verified on Micrometer 1.13.0, matching the Spring Boot 3.3 generation; upgrading the application to a newer version is not required.

### Choose the Right Measurement Instrument

| Question to answer | Appropriate tool | Meaning of the data |
| --- | --- | --- |
| How many events occurred? | `Counter` | Increasing count or cumulative total |
| How many items are currently in the queue? | `Gauge` | State sampled at observation time |
| How long did an operation take? | `Timer` | Duration distribution, with time units |
| How many bytes long is each message? | `DistributionSummary` | Size distribution of individual messages |
| How many records does each batch contain? | `DistributionSummary` | Item-count distribution of individual batches |

For example, recording queue depth every second into a summary builds a distribution of **sampling reads**, not a distribution of message sizes. That is only right if that is precisely the question being measured. For durations, use `Timer` to get proper unit handling and integrations.

## 2. Understanding Count, Total Amount, Mean, and Max

Given a sequence of observations `100, 500, 900, 0` bytes:

| Java statistic | Result | How to read it |
| --- | --- | --- |
| `count()` | `4` | Four observations were accepted |
| `totalAmount()` | `1500.0` | Total size is 1,500 bytes |
| `mean()` | `375.0` | Average of 375 bytes per observation |
| `max()` | `900.0` right after recording | Largest observation still retained in the max window |

The mean formula is:

```text
mean = totalAmount / count, when count > 0
mean = 0, when there are no observations yet
```

Do not confuse `count` with total bytes. `record(500)` increments the observation count by **one**, while adding **500** to the total amount.

In cumulative implementations, count and total amount accumulate over the meter's lifetime; some registries use step-based intervals, so read them according to your actual registry's semantics. `max` has its own time window rather than automatically meaning “the largest value since the application started.” Count/total accumulation and max recording in the version used here can be checked in [CumulativeDistributionSummary 1.13.0](https://raw.githubusercontent.com/micrometer-metrics/micrometer/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/cumulative/CumulativeDistributionSummary.java).

Summary holds aggregated statistics and enabled distribution structures; it is not a list retaining every individual size for later querying. Thus, from count, total, and max alone, you cannot reconstruct the full original dataset.

### Which Values Are Recorded?

- **Positive numbers:** adds one observation and its corresponding amount.
- **Zero:** still a valid observation; count increments, total does not increase.
- **Negative numbers:** ignored in the Micrometer implementation examined here.
- **NaN or infinity:** must be guarded at the data boundary; do not use them to represent “unknown size.”

In Micrometer 1.13.0, the guard before recording is `amount >= 0`; this also keeps `NaN` out of the recording branch, though it does not guard the application against positive infinity. For computed `double` data, you can check `Double.isFinite(value) && value >= 0` before calling the meter. For a byte array's size, `length` is inherently a non-negative integer. See [AbstractDistributionSummary 1.13.0](https://raw.githubusercontent.com/micrometer-metrics/micrometer/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/AbstractDistributionSummary.java).

“No event” is different from “an event of size 0.” When there is no event, do not call `record`; recording 0 to fill idle time drags the mean down by inflating the denominator.

## 3. Defining One Observation Precisely

Before naming a meter, write a one-sentence definition:

> Every time a JSON payload is successfully built, record once the byte count of the payload after UTF-8 encoding and before compression.

This sentence specifies:

1. **Subject:** one JSON payload.
2. **Recording point:** after successful creation.
3. **Unit:** bytes.
4. **Data boundary:** after encoding, before compression.
5. **Counting rule:** one payload corresponds to one `record` call.

If you need to measure compressed data, measure the compressed byte array and use a clearly distinct name or tag set. Do not mix pre-compression and post-compression byte counts in the same series.

For text, `String.length()` is the count of UTF-16 code units, not the number of bytes transmitted over the wire. For example:

```java
byte[] encoded = text.getBytes(java.nio.charset.StandardCharsets.UTF_8);
summary.record(encoded.length);
```

This is an illustrative integration snippet: `text` is existing content and `summary` is a registered meter. If the payload is already a `byte[]`, read `length` directly to avoid extra encoding just for measurement.

In addition, “one sample per payload” yields a per-payload average. If batches vary in record count, the average batch size is not the average record size. Identify the right denominator before using results for decisions.

## 4. Standalone Java Experiment

This experiment verifies input handling, buckets, scaling, and max expiration without running an HTTP server. It uses `SimpleMeterRegistry` with `MockClock` so results do not depend on real elapsed wait times.

### Preparing a Separate Project

Use JDK 17 or later, JDK 21 recommended. Create a small standalone Gradle project with `build.gradle`:

```groovy
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
    mainClass = 'demo.DistributionSummaryDemo'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
}

tasks.register('copyRuntimeDependencies', Copy) {
    from configurations.runtimeClasspath
    into layout.buildDirectory.dir('runtime-libs')
}
```

`settings.gradle`:

```groovy
rootProject.name = 'distribution-summary-demo'
```

File `src/main/java/demo/DistributionSummaryDemo.java`:

```java
package demo;

import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.distribution.CountAtBucket;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.time.Duration;
import java.util.Locale;

public class DistributionSummaryDemo {
    public static void main(String[] args) {
        MockClock clock = new MockClock();
        SimpleMeterRegistry registry = new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);
        try {
            DistributionSummary sizes = DistributionSummary.builder("demo.payload.size")
                    .baseUnit("bytes")
                    .description("Payload size per accepted event")
                    .minimumExpectedValue(1.0)
                    .maximumExpectedValue(1000.0)
                    .serviceLevelObjectives(100, 500, 1000)
                    .distributionStatisticExpiry(Duration.ofSeconds(10))
                    .distributionStatisticBufferLength(3)
                    .register(registry);

            for (double value : new double[] {100, 500, 900, 0, -5}) {
                sizes.record(value);
            }
            System.out.printf(Locale.ROOT,
                    "sizes: count=%d total=%.0f mean=%.2f max=%.0f%n",
                    sizes.count(), sizes.totalAmount(), sizes.mean(), sizes.max());

            for (CountAtBucket bucket : sizes.takeSnapshot().histogramCounts()) {
                System.out.printf(Locale.ROOT, "bucket <= %.0f: %.0f%n",
                        bucket.bucket(), bucket.count());
            }

            DistributionSummary ratio = DistributionSummary.builder("demo.fill.ratio")
                    .baseUnit("percent")
                    .scale(100)
                    .serviceLevelObjectives(70, 90, 100)
                    .register(registry);
            ratio.record(0.25);
            ratio.record(0.75);
            ratio.record(0.90);
            System.out.printf(Locale.ROOT,
                    "ratio: count=%d total=%.0f mean=%.2f max=%.0f%n",
                    ratio.count(), ratio.totalAmount(), ratio.mean(), ratio.max());

            DistributionSummary overflow = DistributionSummary.builder("demo.size.overflow")
                    .maximumExpectedValue(1000.0)
                    .register(registry);
            overflow.record(1500);
            System.out.printf(Locale.ROOT, "overflow: count=%d total=%.0f%n",
                    overflow.count(), overflow.totalAmount());

            clock.add(Duration.ofSeconds(31));
            System.out.printf(Locale.ROOT,
                    "after 31s: count=%d total=%.0f max=%.0f%n",
                    sizes.count(), sizes.totalAmount(), sizes.max());
        } finally {
            registry.close();
        }
    }
}
```

Run with an installed Gradle, or replace `gradle` with the experiment project's wrapper if present:

```shell
gradle -q run
```

You can also compile and run directly. After `gradle -q copyRuntimeDependencies` places dependency JARs into `build/runtime-libs`, run these commands on Windows:

```shell
javac --release 17 -encoding UTF-8 -cp "build/runtime-libs/*" -d build/manual-classes src/main/java/demo/DistributionSummaryDemo.java
java -cp "build/manual-classes;build/runtime-libs/*" demo.DistributionSummaryDemo
```

On Linux/macOS, use `:` instead of `;` between classpath entries in the `java` command.

### Stdout

```text
sizes: count=4 total=1500 mean=375.00 max=900
bucket <= 100: 2
bucket <= 500: 3
bucket <= 1000: 4
ratio: count=3 total=190 mean=63.33 max=90
overflow: count=1 total=1500
after 31s: count=4 total=1500 max=0
```

`Locale.ROOT` fixes the decimal separator as a dot. `MockClock.add(...)` only advances the experiment registry's clock without sleeping the thread for 31 seconds. `registry.close()` is called in `finally` to close the registry created by the program itself.

## 5. Reading the Experiment Results

### 5.1. Why Five Numbers Produced a Count of Four

The input array contains `100, 500, 900, 0, -5`. Four non-negative numbers were recorded, while `-5` was ignored:

```text
count = 4
total = 100 + 500 + 900 + 0 = 1500
mean  = 1500 / 4 = 375
```

If business rules consider negative sizes an error, detect that error when computing the size. The summary ignoring negative numbers does not mean the input data was valid.

### 5.2. Buckets Are Cumulative Counts by Threshold

`serviceLevelObjectives(100, 500, 1000)` creates thresholds to observe. A bucket at threshold `b` answers: **how many samples have a value less than or equal to b?**

| Threshold | Samples included | Count |
| --- | --- | --- |
| `<= 100` | `0, 100` | `2` |
| `<= 500` | `0, 100, 500` | `3` |
| `<= 1000` | `0, 100, 500, 900` | `4` |

Do not sum `2 + 3 + 4` to find the sample count because the same sample appears in multiple buckets. The number of samples in `(100, 500]` is `3 - 2 = 1`.

In this dataset:

```text
Proportion of samples <= 500 bytes = 3 / 4 = 75%
Proportion of samples > 500 bytes  = (4 - 3) / 4 = 25%
```

The API is named “service level objectives,” yet declaring thresholds only creates observability data. It does not enforce a 99% target, reject oversized payloads, or send alerts automatically.

### 5.3. maximumExpectedValue Is Not Input Validation

The `demo.size.overflow` meter sets maximum expected value to 1,000 yet still accepts the 1,500 sample, giving count 1 and total 1,500.

`minimumExpectedValue` and `maximumExpectedValue` mainly bound generated bucket ranges and distribution structure overhead. They do not replace business rules like “payload must not exceed 1 MiB.” If oversized data must be rejected, enforce that rule in application logic; how rejected cases are reflected in metrics is a separate measurement decision.

Builder methods and unit/threshold semantics can be checked in [DistributionSummary 1.13.0](https://raw.githubusercontent.com/micrometer-metrics/micrometer/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/DistributionSummary.java).

### 5.4. Why Max Dropped to 0 While Total Remained 1,500

In the program we configured:

```text
expiry = 10 seconds
bufferLength = 3
Time for all old data to expire = expiry * bufferLength = 30 seconds
```

After the clock advances 31 seconds with no new samples, old max data has expired. Count and total in the cumulative registry remain, while `max()` returns 0.

The mechanism uses rotating buffers; do not interpret it as an exact per-sample sliding window down to each timestamp. The example intentionally advances past the full expiration period so the outcome is unambiguous. You can inspect the algorithm in [TimeWindowMax 1.13.0](https://raw.githubusercontent.com/micrometer-metrics/micrometer/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/distribution/TimeWindowMax.java).

Therefore, a max of 0 after a quiet period does not prove “all payloads were previously empty.” To view historical trends, you need data collected over time by a monitoring system.

## 6. Units and Scale: Record What You Read Consistently

`baseUnit("bytes")` describes the unit; it does not convert a KiB value into bytes. Calling `record(2)` with base unit bytes means recording 2 bytes, not 2 KiB.

`scale(k)` multiplies **each sample's value** by `k` before feeding statistics. For example, with input ratios in `[0, 1]` and `scale(100)`:

```text
Input values:      0.25, 0.75, 0.90
Recorded values:   25,   75,   90
count = 3
total = 190
mean  = 63.333...
max   = 90
```

The buckets `70, 90, 100` in the example are evaluated in the **post-scale** domain. Thus the original `0.75` sample lands in buckets `<= 90` and `<= 100`, not `<= 70`.

When using `scale(100)`, pass `0.75` to represent 75%, not 75 which would multiply into 7,500. Expected values and SLO thresholds must also match the scaled numeric domain.

A distribution of ratios answers “what was the ratio of each event.” It does not automatically yield a volume-weighted aggregate ratio. For example, batch A achieved `1/1` and batch B achieved `0/99`: the average of the two ratios is 50%, whereas the overall record success rate is `1/100 = 1%`. When a weighted aggregate ratio is needed, keep total successes and total attempts rather than inferring from averaged ratios.

## 7. Integrating into a Spring Boot Actuator Application

This section provides **files integrated into an existing Spring Boot 3.3 application** that has a `@SpringBootApplication` class in package `demo` or configuration scanning that package. The two classes below alone do not constitute a complete Spring Boot application.

### 7.1. Use the Spring-Managed MeterRegistry

In a Boot project with dependency management configured, add Actuator; add the Prometheus registry when exporting to Prometheus:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

Do not copy the standalone experiment's Micrometer 1.13.0 version to override Boot's managed dependencies. Boot auto-configures registries based on libraries on the classpath; see [Metrics in Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#getting-started).

File `PayloadMetrics.java`:

```java
package demo;

import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.Objects;
import org.springframework.stereotype.Component;

@Component
public class PayloadMetrics {
    private final DistributionSummary payloadSizes;

    public PayloadMetrics(MeterRegistry registry) {
        this.payloadSizes = DistributionSummary.builder("app.payload.size")
                .description("Encoded JSON payload size per successful event")
                .baseUnit("bytes")
                .tag("format", "json")
                .minimumExpectedValue(1.0)
                .maximumExpectedValue(1048576.0)
                .serviceLevelObjectives(1024, 16384, 65536)
                .publishPercentileHistogram()
                .register(registry);
    }

    public void recordEncodedPayload(byte[] payload) {
        Objects.requireNonNull(payload, "payload");
        payloadSizes.record(payload.length);
    }
}
```

The meter is registered once when the bean is created and reused thereafter. In real processing flows, call `recordEncodedPayload(encodedBytes)` at the defined success point. Do not create `SimpleMeterRegistry` inside the bean: that registry would be isolated from the one Actuator observes.

Tag `format=json` is a bounded value. Do not use message IDs, user IDs, or payload contents as tags.

### 7.2. Test Data and Endpoint Inspection

To test locally with deterministic data, you can temporarily add the following configuration to the experiment application:

```java
package demo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class PayloadMetricsDemoConfig {
    @Bean
    ApplicationRunner seedPayloadMetrics(PayloadMetrics metrics) {
        return args -> {
            for (int size : new int[] {100, 500, 900, 0}) {
                metrics.recordEncodedPayload(new byte[size]);
            }
        };
    }
}
```

This bean creates exactly four samples per startup. When wired into real business logic, remove the seed runner so metrics reflect only real events.

For a web application running on the default port 8080, you can expose the endpoints under test in local configuration:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
```

If using only the default in-memory registry, you can omit the Prometheus dependency and remove `prometheus` from the exposure list. Address, base path, and authentication requirements follow the running application's configuration.

Verification requests:

```shell
curl "http://localhost:8080/actuator/metrics/app.payload.size?tag=format:json"
curl "http://localhost:8080/actuator/prometheus"
```

On a fresh process with only the four seed samples and no other business samples:

- `COUNT` must be 4.
- `TOTAL` must be 1,500 bytes.
- Max immediately after recording is 900 bytes; a later read may have expired past the window.
- The 1,024-byte bucket in exported output must include all four samples.

These are verification conditions, not a fixed JSON payload across all registries. The `metrics` endpoint diagnoses statistics published by the meter; it does not automatically return all buckets or p95. To view the Prometheus histogram, inspect the `prometheus` endpoint with the corresponding registry.

If you filter by the wrong tag, use the wrong registry, or hit the endpoint before the bean/event creates the meter, the output will not reflect what you intend to measure. When multiple tag sets share the same name, select the exact tag to avoid reading unintended aggregates.

## 8. Histograms and Percentiles Answer Different Questions

**Buckets** tell you how many samples fall below a known threshold, such as “how many payloads are at most 64 KiB.” **Percentiles** find the threshold corresponding to a proportion of samples, such as “what is the p95 size.”

A p95 of 64 KiB is understood as a distribution estimate: roughly 95% of observations have sizes not exceeding that threshold. It does not mean 95% of total bytes are under 64 KiB, nor is it the maximum size.

There are three related configuration options:

| Configuration | Goal |
| --- | --- |
| `serviceLevelObjectives(...)` | Adds buckets at specific business thresholds to check |
| `publishPercentiles(0.50, 0.95)` | Computes approximate percentiles client-side per meter ID |
| `publishPercentileHistogram()` | Exports histogram buckets so a supported monitoring system can compute percentiles and aggregate compatible distributions |

You do not need all three just to obtain count and total. With Prometheus and multi-instance aggregation needs, histograms are usually more appropriate than publishing client-side p95 per instance. Never sum or average p95 values to produce an overall p95. A meter with only a few SLO buckets counts accurately at those thresholds, yet can be too coarse for useful p95 estimation. See [Micrometer 1.13 Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/1.13/concepts/histogram-quantiles.html).

Cost should be evaluated by meter IDs and buckets/percentiles per ID. For instance, 4 formats × 3 outcomes × 40 buckets yields 480 bucket series per instance in classic histogram export, before counting count, sum, max, and other series. Adding a tag with millions of values causes cost to escalate rapidly.

Set sensible expected bounds so excessive automatic buckets are not generated. Keep bucket boundaries consistent across instances to be aggregated, and do not use histogram configuration as data validation.

## 9. Querying Prometheus Data with Exact Names and Windows

With the default naming convention, Micrometer name `app.payload.size` and unit `bytes` typically export under the prefix `app_payload_size_bytes`. Check the actual name on the endpoint before writing queries, especially if the application customizes its naming convention. Naming rules and tag cardinality risks are explained in [Naming Meters](https://docs.micrometer.io/micrometer/reference/concepts/naming.html).

The queries below apply to a **classic histogram** scraped by Prometheus, using the series names from the example.

Average bytes per payload over the last 5 minutes, grouped by format:

```promql
sum by (format) (rate(app_payload_size_bytes_sum[5m]))
/
sum by (format) (rate(app_payload_size_bytes_count[5m]))
```

Dividing the summed byte rate by the summed sample rate gives the properly weighted mean across instances. Do not take a simple average of per-instance `mean` values when instances handle different sample counts.

Size p95, preserving the boundary label `le` when aggregating buckets:

```promql
histogram_quantile(
  0.95,
  sum by (format, le) (
    rate(app_payload_size_bytes_bucket[5m])
  )
)
```

Proportion of payloads at most 65,536 bytes over the same window:

```promql
sum by (format) (
  rate(app_payload_size_bytes_bucket{le="65536.0"}[5m])
)
/
sum by (format) (
  rate(app_payload_size_bytes_count[5m])
)
```

The `le` label string must match the exported data exactly; if the registry formats it as `65536`, use that value. Bucket 65,536 comes from the example's `serviceLevelObjectives` configuration. Do not put a fictional bucket in a query when the configuration does not export it.

`rate` requires sufficient scrape data within the window. When there are no events, the denominator can be 0 and the ratio undefined; decide how to display gaps instead of defaulting to 0% or 100%. Scope by job/service appropriately if the same metric exists across multiple applications.

Using rates of sum/count and computing quantiles from histograms can be cross-checked with [Prometheus Histograms and Summaries](https://prometheus.io/docs/practices/histograms/). The Java class name `DistributionSummary` does not force exported output to always be Prometheus's `summary` type; histograms are exported per configuration and registry.

## 10. Mistakes That Easily Skew Conclusions

| Symptom | Common cause | Fix |
| --- | --- | --- |
| Count exceeds actual payloads | Recorded in both caller and handler layers, or retries each recorded while read as unique payloads | Lock down “per attempt” vs “per successful payload,” then record at one point |
| Unusually low mean | Recording 0 during idle periods with no events | Record only on real observations; reserve 0 for actual zero-size events |
| Incorrect Vietnamese text size | Using `String.length()` as byte count | Measure the encoded byte array |
| Some observations vanish | Negative or invalid input values | Inspect computation and handle boundary data |
| Changed max expected yet large payloads still added | Mistaking histogram range for business limit | Enforce validation in separate business logic |
| Max is 0 after idle time | Max sample expired past its window | Read alongside count, total, time, and scrape history |
| Count/total present but no p95 | Percentiles/histogram not enabled, or inspecting wrong endpoint | Verify meter config, registry, and exported data type |
| Actuator does not see meter | Private registry created or meter not created/recorded per expected lifecycle | Use injected registry and check registration point |
| High memory usage or series explosion | Too many tag values, buckets, or percentiles | Bound tags, choose expected range and distribution config per question |

Same name and same tag set usually return the already-registered meter in the registry. Therefore, do not call the builder multiple times with the same ID expecting different scale/bucket settings to create independent meters. Finalize unit and configuration before registering, then keep the reference for reuse.

## 11. Self-Verification Practice

1. **Add a 1,000-byte sample before advancing MockClock in the first experiment.** Count must be 5, total 2,500, mean 500, and max 1,000. Buckets 100/500/1000 must have counts 2/3/5 respectively.
2. **Add no new samples; only advance MockClock.** Count and total in the cumulative SimpleMeterRegistry stay unchanged; once past the full max retention period, max drops to 0. Distinguish “no new samples” from “adding a 0 sample.”
3. **Change the measurement question from payload size to batch size.** Write one sentence defining the exact observation, unit, and recording point; explain why `record(batch.size())` does not tell how many bytes each record weighs.
4. **Design a threshold for payloads.** If the goal is knowing the share of payloads at most 64 KiB, place a 65,536-byte bucket; explain why looking only at the mean cannot answer that ratio.

After these exercises, you should be able to explain why count and total have different meanings, why max can expire independently, and what distribution configuration suffices to answer the size question being measured.
