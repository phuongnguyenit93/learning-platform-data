# Understanding Tag Cardinality and Its Impact on Memory

## 1. Why can a single metric create a huge number of objects?

Suppose an application wants to count order-read requests. A seemingly helpful way to tag is using the raw path: `/orders/1001`, `/orders/1002`, and continuing for every new order ID. The metric name stays just `app.http.requests`, yet the application is creating distinct meter identities.

In Micrometer, a meter is identified by **its name and set of tag key-value pairs** within a registry. Same name with one changed tag value can become another meter. Because the registry retains meters to continue recording and reading, creating unbounded identities can cause memory to grow steadily over time.

**Cardinality** in this context is the number of distinct values or value combinations produced by a measurement data set. Specify whether you are discussing cardinality of a single tag, of tag combinations for a metric name, or the number of time series in the monitoring system. Those three numbers are related, not identical.

This lesson uses Micrometer **1.13.0**, suited for the Spring Boot 3.3 line, to verify behavior with Java 17+. The goal is to understand sources of memory growth and design finite dimensions; do not try to find a fixed byte count applicable to every meter.

## 2. Distinguishing tag key count, value count, and combination count

### 2.1. Few tag keys can still have huge cardinality

| Recorded tags | Key count | Cardinality to watch |
| --- | --- | --- |
| `result=success` or `result=failure` | 1 | 2 values if only these two outcomes exist |
| `order.id` receiving a new ID per order | 1 | Can grow with the total number of orders ever processed |
| `method`, `route`, `status` all being finite sets | 3 | Combinations depend on each key's value count and which combinations actually appear |

A single `request.id` tag can be far more dangerous than many tags with small, stable value sets. Conversely, many binary tags can also create a large combinatorial space: 20 dimensions with 2 values each yield up to `2^20 = 1,048,576` theoretical combinations if every combination can occur.

### 2.2. The product estimates the combination space, not always the live count

For the same metric name, suppose there are 2 methods, 3 route templates, and 2 status codes:

```text
Maximum combinations under assumed value sets
  = 2 methods × 3 route templates × 2 statuses
  = 12
```

If every combination is recorded at least once, 12 corresponding meters exist. If only 5 combinations actually occur, only 5 meters may exist so far. Dimensions can correlate: one route only accepts GET, or one outcome cannot happen for a certain operation. Therefore, do not take the product and claim it is the actual measured meter count.

A more accurate description is the cardinality of the set of registered identities:

```text
ID = (metric name, final tag set)

N_meter = number of distinct IDs registered in the scope under consideration
```

Filters and common tags can alter an ID before the registry stores the meter; exporters also have their own name/label translation rules. When investigating, inspect identities at the right layer instead of merely counting tag strings in source code.

### 2.3. Event count is not meter count

A counter can be incremented a million times and remain a single meter if its name and tags do not change. Conversely, a million writes, each using a different UUID as a tag, can create a million identities.

Therefore, separate two questions: "how many events occurred?" and "how many categorizations were registered?" Putting each event into its own ID loses metrics' aggregation benefit while increasing state storage costs.

## 3. How do dangerous values enter tags?

| Value source | Why it easily inflates cardinality | Better representation |
| --- | --- | --- |
| Order ID, user ID, request ID | Every entity/call can produce a new value | Metrics use finite groups; per-entity detail uses appropriate logs/traces |
| URL containing IDs or query strings | URL space grows with data and input | Routed route template, not the raw URL |
| Verbatim exception message | Contains parameters, varying data, or stack traces | A standardized, bounded error code/category |
| Current timestamp | Almost every write produces a new value | Use the measurement's timestamp; never attach event time as a tag |
| Filenames, search keywords, free-form text | Driven by data or users | Business categories with finite value lists |
| Metric name concatenated with entity ID | Creates new names instead of new tags | Stable name; do not shift the problem from tags to names |

Example to replace:

```text
app.http.requests{route="/orders/1001", status="200"}
app.http.requests{route="/orders/1002", status="200"}
```

with a stable aggregating dimension such as:

```text
app.http.requests{route="/orders/{id}", status="200"}
```

In a real web application, prefer the route pattern matched by the framework's router rather than writing a regex that blindly strips all digit sequences. For instance, `/v2/reports/2026` may contain a valid version or business group; blindly stripping digits can merge distinct operations.

Unmatched routes also need a finite label such as `NOT_FOUND` per measurement design. If you keep the raw path of every 404, a caller only needs to send continuously new URLs to generate new tag values. [Micrometer guidance on tag value and URI normalization](https://docs.micrometer.io/micrometer/reference/concepts/naming.html).

Hashing user IDs does not solve distinct value count: one million distinct IDs usually still produce nearly one million distinct hashes. Truncating strings may shorten each label without ensuring cardinality stays small; causing hash collisions also obscures data group meanings.

## 4. At which layers does cardinality affect memory?

### 4.1. Inside the Java process itself

When accepting a new ID, the registry must retain the meter and structures for lookup/registration. Associated data can include name, tags, ID, map entries, counter/timer/gauge state, and additional statistical structures.

In Micrometer 1.13.0, `MeterRegistry` maintains a map keyed by post-mapping ID along with structures related to pre-filter IDs. The registry holds references to those objects; a local variable going out of scope in a method does not make a meter disappear. [Micrometer 1.13.0 meter registration and storage source](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/MeterRegistry.java).

```text
New ID accepted
  -> adds measurement state and lookup structures
  -> registry still holds references
  -> those objects stay alive in the heap
```

The garbage collector (GC) only reclaims objects that are no longer reachable under JVM rules. It does not automatically know that an old order ID "no longer needs to be measured." Thus, increasing GC frequency or expanding the heap does not fix the root cause of unbounded new ID creation.

Do not call every such case a library bug leak. The instrumentation code itself may have asked the registry to retain an ever-growing set of identities. Verify who holds references and why that set continues growing.

### 4.2. Meter type and distribution settings make per-ID cost vary

A simple counter and a timer with histograms/percentiles do not hold the same amount of state. A `Timer` or `DistributionSummary` can retain additional bucket counters, time-windowed statistical slots, or percentile approximation data. Enabling those features across tens of thousands of tag combinations can cost far more than a low-dimensional counter.

You can use a qualitative model:

```text
metrics-related memory
  ≈ sum of ID + measurement state + distribution stats per meter
    + registry / exporter structures
    + application-managed caches
```

This is not an exact byte formula. Cost depends on registry type, version, histogram settings, bucket counts, string lengths, object sharing, and JVM settings. Do not deduce "1,000 meters use exactly 500 times the memory of 2 meters" from count ratios alone.

Expiration of windowed MAX or histograms does not mean a timer's ID has a TTL. A maximum sample can expire while the meter carrying that tag set remains registered.

### 4.3. Composite registries and application code can hold extra state

With `CompositeMeterRegistry`, one logical meter can be attached to multiple child registries. Children maintain their own state/export structures, so account for costs across all participating registries. There is no fixed multiplier across all configurations, yet adding destinations does not shrink cardinality at the source.

A `Map<userId, Counter>` in application code can also grow unbounded. Even when using an application cache to skip registry lookups, the IDs still exist; removing an entry from that map does not automatically remove the meter from the registry. Keeping counters in fields is helpful for stable groups, not a reason to allocate a field/cache for every user.

A Gauge tracking an object via weak reference is also not a global ID-eviction policy. Do not treat gauge target garbage collection as a cardinality management strategy for all meters.

### 4.4. The monitoring system has its own costs

Each distinct label set can become a separate time series in the target system. Beyond application memory, there are costs for data transmission, series storage, indexing, querying, dashboards, and alert rules. Writing a query that sums across all users afterward does not erase the cost already paid to create and store each series.

A Timer can export multiple statistics; histograms add buckets. For a **hypothetical** example, if a classic histogram exports 20 bucket series plus 2 count/sum series per combination, 1,000 combinations create roughly 22,000 series at that layer. The 20 in the example already includes all counted buckets, before adding other statistics or infrastructure labels. Do not substitute this number for actual exporter configuration.

Limiting range and bucket counts affects distribution data and cost, yet does not replace bounding tags. [Histograms, percentiles, and configuration impact in Micrometer](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html).

## 5. Cardinality also has a time dimension

Suppose only 100 users are active per minute, yet each minute it is 100 different users. "100 active" does not prove the registry holds only 100 meters if the application creates per-user IDs without a lifecycle policy.

In a long-running process, inspect combinations registered over time, not only those receiving traffic right as you view a dashboard. In the monitoring system, continuously changing label values also creates new series over time, often called series churn.

Infrastructure tags must also be evaluated at the right scope. A fixed `region` with one value per instance may not multiply meters inside that instance, yet across a multi-region/multi-instance fleet, series count at the destination grows with existing combinations. Do not use single-JVM cardinality as a stand-in for the entire fleet.

Similarly, a "top customers" group that changes continuously over time can still generate many labels across history. If you need a bounded group, define a finite value set, overflow rules into a fallback bucket, and a clear lifecycle; merely naming a solution "top N" does not guarantee boundedness.

## 6. Designing bounds right at the recording point

### 6.1. Use monitoring questions to choose dimensions

Before adding a tag, state the question it helps answer. "Error rate by web/mobile channel" fits a finite `channel` dimension. "Track each order individually" is usually a per-event detail requirement, better suited to logs or traces with appropriate retention policies.

| Requirement | Viable metrics design |
| --- | --- |
| Distinguish outcomes | `result=success|failure|timeout|other` from a defined list |
| Distinguish operation groups | `operation=create|read|cancel` |
| Distinguish customer tiers | `tier=free|standard|premium|unknown`, if aligned with business model |
| Distinguish APIs | Stable route template such as `/orders/{id}` |
| Investigate a specific request | Keep details/correlation in logs or traces, without adding request ID to every meter |

You do not have to strip every tag to achieve minimum cardinality. The goal is sufficient analytical power at controllable cost. Collapsing all errors into "other" can lose investigative signal; keeping full raw error messages can create an unbounded value set. Build an intentional error taxonomy.

### 6.2. Normalize before passing values to the meter registration API

```java
String result = switch (resultCode) {
    case "OK" -> "success";
    case "TIMEOUT" -> "timeout";
    case "DECLINED" -> "failure";
    default -> "other";
};

registry.counter("app.orders.completed",
    "operation", "create",
    "result", result).increment();
```

This snippet illustrates a method with `registry` and a non-null `resultCode`. The input domain may be wide, yet the `result` tag only ever receives one of four prescribed values. Do not pass the raw `resultCode` into another tag and expect cardinality to be bounded.

Normalizing before registration avoids creating raw names/tags and application-managed caches keyed by raw data. Mapping filters like `ignoreTags` or `replaceTagValues` remain useful when dealing with shared instrumentation, though you must check versions, configuration, and retained structures; do not assume a tag transformation guarantees bounding the entire heap.

In particular, a filter that internally keeps a `Set`/`Map` of **every raw value ever seen** just to map them to a few groups can still grow memory inside that filter itself. If the mapping algorithm can compute directly from the input and a finite rule set, there is no need to memorize old raw inputs unboundedly.

### 6.3. Budget both combinations and statistic types

For each metric name, document its meaning, tag keys, expected value sets, possible combinations, meter type, and whether histograms/percentiles are enabled. Then estimate per-instance ID count and system-wide series count, including relevant deployment labels.

For example, 20 routes × 4 methods × 6 status groups yield at most 480 combinations assuming independence. Adding a `tenant` tag with 10,000 values raises the theoretical space to 4,800,000. One extra tag can scale impact more than all previous tags combined.

Test with known valid values as well as unfamiliar inputs, many 404s, new error messages, and repeated operation sequences with new IDs. Testing repeatedly with the same single customer will not expose cardinality growth risks.

## 7. MeterFilter is a guardrail, not a substitute for design

### 7.1. Limiting distinct values of a tag

Micrometer provides `maximumAllowableTags(prefix, tagKey, limit, onMaxReached)`. With `MeterFilter.deny()` on reaching the limit, registering new tag values beyond the cap is rejected; application code receives a non-recording (NOOP) meter. Operations on it do not automatically create a fallback aggregate group. [MeterFilter and DENY semantics](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html).

```java
registry.config().meterFilter(
    MeterFilter.maximumAllowableTags(
        "app.http.requests", "route", 100, MeterFilter.deny()));
```

This is illustrative configuration applied before registering meters. The threshold 100 is an example budget, not a universal standard for every application.

Key points to understand:

- `prefix` is a name prefix, not an exact single-name selector if multiple names share that prefix.
- This cap counts **distinct values of the chosen key** within the filter's scope, not the number of tag keys, nor does it directly cap the product across all dimensions.
- Other tags such as status, method, and tenant can still cause many combinations to be created.
- Already-accepted values continue recording; newly blocked values do not automatically rewrite to `OTHER`.
- This filter is not a "100 values per minute" window or an LRU cache. In the 1.13.0 implementation it retains the observed value set; removing a meter does not automatically refund tag-value quota.
- Retained values can depend on arrival order, not a list of the most important customers/routes.

These are characteristics to verify by version and concurrency environment, not an absolute heap-byte guarantee. [maximumAllowableTags 1.13.0 implementation](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/config/MeterFilter.java).

### 7.2. Limiting total meters and filter ordering

`maximumAllowableMetrics(...)` can serve as a broader cap at the registry. It governs registered IDs per filter mechanics, not byte limits or histogram series counts in the destination system. Budgets must leave room for built-in meters such as JVM/HTTP if covered by the same scope; do not assume removing a meter immediately resets all filter quota state.

Filters are ordered. A filter returning `ACCEPT` can prevent downstream filters' `accept(...)` decisions from being evaluated; placing a broad accept rule ahead of a cap filter can neutralize the protection you intended. Verify with the actual filter chain rather than inspecting one bean in isolation.

In a Boot application with Actuator, you can declare a `MeterFilter` bean to apply through the metrics infrastructure. Example protecting the `uri` dimension of the standard HTTP metric:

```java
package example.metrics;

import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CardinalityConfiguration {
    @Bean
    MeterFilter httpUriBudget() {
        return MeterFilter.maximumAllowableTags(
            "http.server.requests", "uri", 100, MeterFilter.deny());
    }
}
```

This is an add-on configuration component for a Boot application, not a standalone program. Verify actual metric/tag names, ordering, and managed registries. In a Boot project, let Boot manage the compatible Micrometer version. [Metrics customization and filters in Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

### 7.3. When blocking, account for missing data

NOOP allows business code to keep running, yet it does not mean measurements remain complete. If 5 events occur and 2 use denied labels, the sum across remaining counters may be only 3. Do not use that sum to conclude only 3 real requests happened.

Have a way to detect budget breaches using low-cardinality signals or appropriate diagnostics. Creating a new tag holding the raw blocked value to count rejections just reintroduces the original risk into a new metric.

## 8. Java experiment: counting IDs instead of guessing memory

The program below uses a small, fixed dataset to observe meter counts. It does not try to exhaust the heap and does not use `Runtime.freeMemory()` deltas after a single GC to claim bytes per meter.

Create a Gradle project with a wrapper and JDK 17 available:

```text
tag-cardinality-demo/
  build.gradle
  settings.gradle
  gradlew / gradlew.bat and gradle/wrapper/
  src/main/java/TagCardinalityDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'tag-cardinality-demo'
```

`build.gradle`:

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

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'TagCardinalityDemo'
}
```

The version is pinned to reproduce verified behavior; this is not a deployment patch recommendation.

`src/main/java/TagCardinalityDemo.java`:

```java
import java.util.List;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.config.MeterFilter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public class TagCardinalityDemo {

    public static void main(String[] args) {
        combinations();
        rawAndNormalizedPaths();
        tagLimit();
    }

    private static void combinations() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            List<String> methods = List.of("GET", "POST");
            List<String> routes = List.of("/orders", "/cart", "/checkout");
            List<String> statuses = List.of("200", "500");

            for (int repeat = 0; repeat < 100; repeat++) {
                for (String method : methods) {
                    for (String route : routes) {
                        for (String status : statuses) {
                            registry.counter("demo.http.requests",
                                "method", method, "route", route, "status", status)
                                .increment();
                        }
                    }
                }
            }
            System.out.println("combinations.meters=" + registry.getMeters().size());
            System.out.println("combinations.events=" + total(registry));
        }
        finally {
            registry.close();
        }
    }

    private static void rawAndNormalizedPaths() {
        SimpleMeterRegistry raw = new SimpleMeterRegistry();
        SimpleMeterRegistry normalized = new SimpleMeterRegistry();
        try {
            for (int i = 0; i < 1000; i++) {
                String path = "/orders/" + i;
                String status = i % 2 == 0 ? "200" : "500";
                record(raw, path, status);
                record(normalized, routeLabel(path), status);
            }
            System.out.println("raw.meters=" + raw.getMeters().size());
            System.out.println("normalized.meters=" + normalized.getMeters().size());

            for (int i = 0; i < 1000; i++) {
                String path = "/orders/" + i;
                String status = i % 2 == 0 ? "200" : "500";
                record(raw, path, status);
                record(normalized, routeLabel(path), status);
            }
            System.out.println("raw.repeatMeters=" + raw.getMeters().size());
            System.out.println("normalized.repeatMeters="
                + normalized.getMeters().size());
            System.out.println("raw.events=" + total(raw));
            System.out.println("normalized.events=" + total(normalized));
        }
        finally {
            raw.close();
            normalized.close();
        }
    }

    private static String routeLabel(String path) {
        return path.matches("/orders/[0-9]+") ? "/orders/{id}" : "NOT_FOUND";
    }

    private static void record(MeterRegistry registry, String route, String status) {
        registry.counter("demo.http.requests", "route", route, "status", status)
            .increment();
    }

    private static void tagLimit() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            registry.config().meterFilter(MeterFilter.maximumAllowableTags(
                "demo.limited.requests", "tenant", 2, MeterFilter.deny()));

            for (String tenant : List.of("alpha", "beta", "gamma", "alpha", "delta")) {
                registry.counter("demo.limited.requests", "tenant", tenant)
                    .increment();
            }

            System.out.println("limited.meters=" + registry.getMeters().size());
            System.out.println("limited.recordedEvents=" + total(registry));
            System.out.println("limited.gammaAbsent="
                + (registry.find("demo.limited.requests")
                    .tag("tenant", "gamma").counter() == null));

            Counter rejected = registry.counter(
                "demo.limited.requests", "tenant", "gamma");
            rejected.increment();
            System.out.println("limited.rejectedCount=" + rejected.count());
        }
        finally {
            registry.close();
        }
    }

    private static double total(MeterRegistry registry) {
        return registry.getMeters().stream()
            .filter(Counter.class::isInstance)
            .map(Counter.class::cast)
            .mapToDouble(Counter::count)
            .sum();
    }
}
```

Run from the project directory:

```bash
./gradlew -q run --console=plain
```

On Windows PowerShell use `.\gradlew.bat -q run --console=plain`. Gradle resolves dependencies and compiles/runs `main`. If invoking `javac`/`java` directly, the classpath must include the resolved Micrometer and dependency JARs on both steps.

Program output:

```text
combinations.meters=12
combinations.events=1200.0
raw.meters=1000
normalized.meters=2
raw.repeatMeters=1000
normalized.repeatMeters=2
raw.events=2000.0
normalized.events=2000.0
limited.meters=2
limited.recordedEvents=3.0
limited.gammaAbsent=true
limited.rejectedCount=0.0
```

### 8.1. Finite combinations are reused

The first loop records all 2 methods × 3 routes × 2 statuses, repeated 100 times. The result is 1,200 events yet only 12 meters. Increasing writes on the same IDs does not create 1,188 extra meters.

### 8.2. Raw paths vs route templates for the same data

On the first pass, 1,000 paths with distinct order IDs create 1,000 meters in the `raw` registry. Each path in this dataset pairs with only one chosen status, so the actual combination count is 1,000, not automatically 1,000 × 2.

In the `normalized` registry, all valid paths collapse to one template `/orders/{id}` with two statuses, yielding 2 meters. Repeating the exact same path set again leaves meter counts unchanged on both sides; total events rise to 2,000 on both.

Thus, normalization preserves total counts and status breakdown while giving up per-order-ID metric splits. This is an intentional granularity choice; if a single order must be looked up, use an appropriate detailed data source.

`routeLabel()` only illustrates the exact input pattern of the experiment. It is not a general-purpose URI normalizer for Spring applications; in practice, use matched routing metadata to preserve accurate semantics.

### 8.3. Limiters do not route blocked data into another group

The filter accepts the first two tenant values, `alpha` and `beta`. When `alpha` appears again, it is still counted. `gamma` and `delta` do not become meters, leaving 2 meters with a recorded total of 3.

The `rejected` variable is still a `Counter` you can call `increment()` on, yet its read count is 0 because it is a no-op meter. No `tenant=OTHER` meter is created. The single-threaded experiment fixes order for repeatable output; do not infer from it that a concurrent system always keeps a specific tenant group.

The program owns its registries so it closes them in `finally`. Business services injected with a Spring-shared registry do not close the registry after each request.

## 9. Checking memory impact in a real application

### 9.1. Prove the rate of identity creation

First separate request count from meter count. Track ID counts for suspect names in the right registry over a controlled load interval, while counting distinct values of tags like URI, tenant, or error code. If requests only reuse known groups while ID counts still climb, inspect which tags/names are actually changing.

`registry.getMeters().size()` reflects the meters exposed by that registry at read time; it does not measure heap bytes, does not count all series in the monitoring system, and does not automatically cover every registry in the process. If adding a gauge to report this count itself, avoid giving that gauge per-meter varying tags.

The `/actuator/metrics` endpoint can help find names and tags when configured, yet reading a name-aggregated response does not prove only one ID exists. A counter carrying thousands of tag sets can still sit under one metric name.

### 9.2. Verify what is retaining memory

Correlate ID count growth with heap/GC data over the same load interval. If heap analysis is needed, inspect registry structures, meters, tags, histograms, and application caches, then check reference paths keeping them alive and retained sizes with an appropriate tool.

Keep the same version, statistics configuration, and load conditions for meaningful comparisons. Temporary allocations when constructing strings/tags differ from long-lived retained memory; an instantaneous heap reading or total allocation rate does not replace analyzing live objects.

Do not create another unbounded `Set` holding every ID just to debug a cardinality issue and leave it in the application forever. Even a uniqueness-counting tool needs scope and a lifecycle.

### 9.3. Check the target system as well

In the monitoring system, inspect series counts by metric family, high-cardinality labels, and new series creation rate. For example, Prometheus can run `count by (__name__) ({job="checkout"})` to view active series by name within an example job scope; this is neither a count of Java meters nor does it cover every historical series that ever existed.

Histograms, instance labels, and rolling deployments can make series counts much higher than the IDs counted inside one JVM. [Prometheus instrumentation practices and label cost](https://prometheus.io/docs/practices/instrumentation/).

### 9.4. Fix the creation source before trying to purge data

Prioritize fixing unbounded names/tags, normalizing to finite domains, and verifying data still answers monitoring questions. Limits can be added as guardrails and distribution statistics narrowed to the metrics that truly need them.

Do not treat disabling histograms, expanding the heap, tuning GC, or scheduled restarts as solutions when new IDs continue arriving without bound. Removing meters can also break counter continuity while application code retains old references or recreates meters right afterward. Already-exported data in the target system also has its own lifecycle.

When dynamic-lifecycle meters are genuinely needed, design ownership, eviction points, cache references, and query impact explicitly; do not assume a standard registry automatically applies LRU/TTL to all identities.

## 10. Misconceptions to avoid

| Claim | What to distinguish |
| --- | --- |
| There is only one tag, so it is safe | A single tag receiving a new UUID every time still has unbounded cardinality |
| There is only one metric name, so there is only one meter | Each distinct tag set can create a different ID |
| Many requests mean many meters | The same ID can be recorded repeatedly |
| The product of tag value counts is always the live count | The product estimates the space; inspect combinations that actually appear |
| Hashing or truncating IDs solves cardinality | String length and distinct value count are two different factors |
| The dashboard sums everything, so per-tag resources do not matter | Registration/export/series-storage costs already occurred before aggregation queries |
| GC will collect meters with no recent requests | Registries/caches may still hold references; there is no default global TTL |
| Windowed MAX expiring means the meter expired | Statistical state expiration differs from ID lifecycle |
| Weak-referenced Gauges need no ID budget | Gauge target lifecycle does not replace an identity budget |
| `maximumAllowableTags` bounds all combinations | It bounds one key within filter scope; other dimensions still multiply |
| Denied data automatically goes to OTHER | DENY returns NOOP; data is dropped without another design |
| One meter always exports one series | Meter type, histograms, and exporters can produce multiple series |

## 11. Self-check

1. A metric has 2 `method` values, 10 `route` values, and 5 `status.group` values. Calculate the maximum combinations assuming independence and explain why the actual count may be lower.
2. There are 100,000 requests sharing the same tag set. Compare the meter count against 100,000 requests where each uses its own `request.id`.
3. In the Java example, explain why 1,000 raw paths create 1,000 meters whereas route templates create only 2, and why total event counts remain equal on both sides.
4. Keep 20 routes and add `tenant` with 50,000 values. List the questions to answer before accepting that dimension and the effect of enabling histograms.
5. A filter caps at 2 values, yet 5 events arrive in order: alpha, beta, gamma, alpha, delta. Predict the counter total and explain which data is no longer retained.
6. Heap keeps growing after counter variables in a method go out of scope. Point out what may still hold references and why triggering GC does not fix it.
7. Propose finite tag groups for an error message containing order ID, timestamp, and root cause; state which details should move to logs/traces instead of metrics.

Cardinality must be designed alongside measurement semantics: **keep useful analytical dimensions, block unbounded identity spaces, and verify costs in both the JVM and the monitoring system**.
