# Diagnosing Gauge Data Loss and Uncontrolled Meter Growth

## 1. Separate the Two Failure Modes Before Fixing Anything

A Gauge reads the **current value** from an object. MeterRegistry stores registered meters, while the external monitoring system stores time series exported from them. These three layers are related, not identical.

The two symptoms in the title can occur at the same time:

- A Gauge turns into `NaN`, freezes at an old value, or disappears from charts.
- The number of meters in the process or time series in the monitoring system grows continuously.

Do not assume both stem from "Micrometer losing data." Determine whether the observed object is still alive, which meter is being read, and which name/tag sets are being created.

| Symptom | First diagnostic question |
| --- | --- |
| Has a value initially, then turns NaN or disappears | Who is holding the object observed by the Gauge? |
| Replaced the object, yet Gauge keeps reading the old value | Was it re-registered with the same ID? |
| Brief spike does not appear on the chart | Was the Gauge sampled while the spike occurred? |
| Meter count grows with request count | Do names or tags contain per-request data? |
| Registry reads fine, yet monitoring system lacks it | Check export, collection, and query |
| No new meters appear after adding a filter | Was meter registration denied? |

This lesson uses **Java 21, Spring Boot 3.3.13, and Micrometer 1.13.15**. The program in section 6 tests directly against `SimpleMeterRegistry`; it needs neither an HTTP server nor Prometheus.

## 2. A Gauge Does Not Implicitly Own the Measured Object

### 2.1. Distinguishing Holding the Gauge from Holding the Source Data

With standard object-and-value-function registration, a Gauge holds a weak reference to the observed object by default. If the application does not keep that object alive, the garbage collector can reclaim it. Depending on the registry, subsequent results can be `NaN` or missing exported samples. This behavior is described in the [Micrometer Gauge documentation](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html).

Problematic snippet:

```java
void registerQueueDepth(MeterRegistry registry) {
    var depth = new AtomicInteger(0);
    Gauge.builder("app.queue.depth", depth, AtomicInteger::get)
            .tag("queue", "mail")
            .register(registry);
}
```

This is an illustrative snippet requiring Micrometer and `AtomicInteger` imports. After the method returns, no long-lived owner holds `depth`. There is no guarantee the failure shows up immediately; GC timing is non-deterministic.

Keeping a reference variable to the **Gauge** does not necessarily keep the **object measured by the Gauge** alive. Inspect data ownership, not just whether the meter was registered.

Weak references do not prevent objects from being collected; see [WeakReference in Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ref/WeakReference.html). Do not call `System.gc()` once and sleep a few milliseconds to claim a deterministic moment when a Gauge will lose its value.

### 2.2. Keep State in an Object with an Appropriate Lifecycle

Component example inside a Spring Boot application that already has Actuator:

```java
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

import java.util.concurrent.atomic.AtomicInteger;

@Component
public final class QueueDepthMetrics {
    private final AtomicInteger depth = new AtomicInteger();

    public QueueDepthMetrics(MeterRegistry registry) {
        Gauge.builder("app.queue.depth", depth, AtomicInteger::get)
                .tag("queue", "mail")
                .register(registry);
    }

    public void updateDepth(int currentDepth) {
        depth.set(currentDepth);
    }
}
```

Save the component in `QueueDepthMetrics.java` within a Spring-scanned package. This is an integration component, not a standalone program with `main`.

The bean holds `depth` via a `final` field; code updates that exact same object. The application must call `updateDepth` from wherever the actual queue size is known. A Gauge does not infer queued work from its metric name.

If a long-lived queue object already exists, you can measure its size directly instead of maintaining a secondary counter that risks drifting from real state. The value supplier should be fast, thread-safe, and avoid heavy network queries on every sample.

The builder also offers `strongReference(true)` to retain the measured object. That is a lifecycle trade-off: the object can stay alive as long as the meter. Do not enable this option across unbounded short-lived objects with unbounded IDs and skip cleanup.

### 2.3. NaN Does Not Have Only One Cause

A live object can still produce `NaN` if the computation itself returns that value. For example, floating-point division `0.0 / 0` yields `NaN`; the program in section 6 checks this case.

When encountering NaN, check in order:

1. Is the source object still kept alive?
2. Can the value function yield an undefined value, such as a zero denominator?
3. Are there errors inside the measurement function or related diagnostic logs?
4. Are you reading the right tag set, right registry, and right process?

Do not replace all NaNs with 0 on dashboards before understanding the cause. "No valid measurement" differs from "queue is empty."

## 3. Re-registering the Same ID Does Not Swap the Source Object

Inside a registry, the name and tag set define meter identity. Re-registering with the same ID does not create a new Gauge that automatically tracks the replacement object. The first-registration-wins mechanism can be verified in [MeterRegistry 1.13.15](https://github.com/micrometer-metrics/micrometer/blob/v1.13.15/micrometer-core/src/main/java/io/micrometer/core/instrument/MeterRegistry.java).

Example:

```java
var firstState = new AtomicInteger(7);
Gauge first = Gauge.builder("app.queue.depth", firstState, AtomicInteger::get)
        .tag("queue", "mail")
        .register(registry);

var newState = new AtomicInteger(99);
Gauge second = Gauge.builder("app.queue.depth", newState, AtomicInteger::get)
        .tag("queue", "mail")
        .register(registry);
```

Both calls share the same name and tag. In the `SimpleMeterRegistry` test, `first == second` is `true`; the Gauge keeps reading `firstState`.

Practical consequences:

- Reassigning an application field to a new `AtomicInteger` does not automatically update the registered Gauge's target object.
- Re-registering after each update may not change the value as you expect.
- Re-registering with the same ID does not necessarily increase meter count; growth usually comes from **genuinely different IDs**.
- When the object must be replaced, prefer one stable owner able to supply the current value, or perform controlled lifecycle removal and re-registration.

Do not "fix" duplicate registration by adding a UUID or timestamp to a tag. That dodges ID collision by creating infinite new IDs and turns a value bug into a meter-count explosion.

Also avoid reusing the same ID for different meter types or measurement semantics. One ID must represent one clear measurement.

## 4. A Gauge Can Miss Brief Spikes Without Being Broken

Suppose between two reads, a variable takes the values:

```text
0 -> 20 -> 0
```

If the next read occurs at the end, the Gauge reports 0. It does not store a history of every update and does not remember the peak of 20.

In the program in section 6, two calls `set(20)` then `set(0)` execute before reading the Gauge. The result is 0.0.

Choose the meter type by question:

| Question | Typically suited instrument |
| --- | --- |
| How many items are currently waiting? | Gauge |
| How many requests arrived in total? | Counter |
| How long does each task take to process? | Timer |
| What is the size distribution of processed items? | DistributionSummary |

Shortening the scrape interval can raise the odds of catching fluctuations, yet never turns a Gauge into an all-events recorder. If you need event counts or distributions, fix the instrumentation instead of merely increasing collection frequency.

## 5. Why Does Meter Count Grow Uncontrollably?

### 5.1. Every New Tag Value Set Creates Another Identity

The following IDs are distinct:

```text
app.queue.depth{queue=mail}
app.queue.depth{queue=image}
app.queue.depth{queue=mail,requestId=request-1}
app.queue.depth{queue=mail,requestId=request-2}
```

Even with only one metric name, meter count can grow huge. Cardinality is the number of distinct values or identifier combinations across dimensions.

Prometheus likewise creates separate time series for distinct label sets; multiple dimensions multiply combinations. See [Cardinality matters](https://prometheus.io/docs/practices/the_zen/#cardinality-matters).

Budgeting example, for a measurement with:

```text
4 queues x 3 states x 2 regions = at most 24 combinations
```

This is the maximum number of possible combinations in the example model, not a claim that every combination already appeared. If you add a fresh `requestId` per request, the value domain is no longer bounded by 24.

### 5.2. Unbounded Sources of IDs

| Tagging approach | Problem | Better alternative |
| --- | --- | --- |
| Tag `requestId`, `traceId`, `userId`, `orderId` | Value domain grows with traffic | Put identifiers in logs/traces; keep metrics to bounded groups |
| Tag containing raw URL with ID or query string | Every URL can become a new value | Use route templates like `/orders/{id}` where appropriate |
| Tag containing raw exception/error message | Messages may include IDs and dynamic text | Use error codes or categorized error types |
| Metric name containing UUID/timestamp | Name count also grows without bound | Keep names fixed, design bounded dimensions |
| Meter per short-lived object, never removed | Registry accumulates IDs over time | Aggregate by group or manage lifecycle explicitly |

Hashing `userId` into another string does not reduce the number of distinct values. Arbitrarily truncating strings can cause collisions while still failing to enforce a meaningful budget.

For HTTP applications, inspect the actual route tag, especially on route-not-found errors or manual metric sites. Do not look solely at the tag name `uri` and assume values are normalized.

### 5.3. Distinguishing Meters in the JVM from Time Series in Monitoring

These two counts are not always equal:

- Number of meters in one process's `MeterRegistry`.
- Number of time series currently stored or queried in the monitoring system.

External systems also have instance/job/Pod labels, multiple replicas, and historical data from prior deployments. A Timer or histogram meter can also export as multiple series.

Therefore, measure at the right scope. `/actuator/metrics` listing names is not a full count of all meter combinations. One static name can still contain thousands of tag sets.

## 6. Runnable Program to Distinguish Behaviors

The following example opens no web server. It uses libraries managed by Spring Boot to test Gauges in memory, isolated from external collection issues.

File tree:

```text
gauge-diagnostics/
├── pom.xml
└── src/main/
    ├── java/example/GaugeDiagnostics.java
    └── resources/logback.xml
```

Full contents of `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>gauge-diagnostics</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Full contents of `src/main/java/example/GaugeDiagnostics.java`:

```java
package example;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.config.MeterFilter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import java.lang.ref.Reference;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

public class GaugeDiagnostics {
    public static void main(String[] args) {
        var registry = new SimpleMeterRegistry();
        var limited = new SimpleMeterRegistry();
        try {

            var depth = new AtomicInteger(4);
            Gauge first = Gauge.builder("lab.queue.depth", depth, AtomicInteger::get)
                    .tag("queue", "mail")
                    .register(registry);
            depth.set(7);
            System.out.println("current=" + first.value());

            var replacement = new AtomicInteger(99);
            Gauge second = Gauge.builder("lab.queue.depth", replacement, AtomicInteger::get)
                    .tag("queue", "mail")
                    .register(registry);
            replacement.set(100);
            System.out.println("sameGauge=" + (first == second));
            System.out.println("afterReplacement=" + second.value());
            System.out.println("stableMeters=" + count(registry, "lab.queue.depth"));

            depth.set(20);
            depth.set(0);
            System.out.println("afterSpike=" + first.value());

            Gauge retained = Gauge.builder("lab.retained.depth",
                    new AtomicInteger(9), AtomicInteger::get)
                    .strongReference(true).register(registry);
            if (retained.value() != 9.0) {
                throw new IllegalStateException("Unexpected retained gauge value");
            }

            var denominator = new AtomicInteger(0);
            Gauge ratio = Gauge.builder("lab.ratio", denominator,
                    value -> 0.0 / value.get()).register(registry);
            System.out.println("ratioIsNaN=" + Double.isNaN(ratio.value()));

            var requestStates = new ArrayList<AtomicInteger>();
            for (int i = 0; i < 5; i++) {
                var state = new AtomicInteger(i);
                requestStates.add(state);
                Gauge.builder("lab.bad.depth", state, AtomicInteger::get)
                        .tag("requestId", "request-" + i)
                        .register(registry);
            }
            System.out.println("unboundedPatternMeters=" + count(registry, "lab.bad.depth"));

            limited.config().meterFilter(MeterFilter.maximumAllowableTags(
                    "lab.limited.depth", "queue", 2, MeterFilter.deny()));
            var boundedStates = List.of(
                    new AtomicInteger(1),
                    new AtomicInteger(2),
                    new AtomicInteger(3));
            var queues = List.of("mail", "image", "video");
            for (int i = 0; i < queues.size(); i++) {
                Gauge.builder("lab.limited.depth", boundedStates.get(i), AtomicInteger::get)
                        .tag("queue", queues.get(i))
                        .register(limited);
            }
            System.out.println("limitedMeters=" + count(limited, "lab.limited.depth"));
            System.out.println("videoRegistered=" +
                    (limited.find("lab.limited.depth").tag("queue", "video").gauge() != null));

            registry.remove(first);
            System.out.println("afterRemove=" + count(registry, "lab.queue.depth"));

            Reference.reachabilityFence(depth);
            Reference.reachabilityFence(replacement);
            Reference.reachabilityFence(denominator);
            Reference.reachabilityFence(requestStates);
            Reference.reachabilityFence(boundedStates);
        } finally {
            registry.close();
            limited.close();
        }
    }

    private static int count(MeterRegistry registry, String name) {
        return registry.find(name).meters().size();
    }
}
```

Contents of `src/main/resources/logback.xml`:

```xml
<configuration>
    <root level="OFF"/>
</configuration>
```

This logging config only gives the lab deterministic stdout; it is not a recommendation to disable diagnostic logs in real applications.

Using JDK 21 and Maven, run from the directory containing `pom.xml`:

```shell
mvn package
java -jar target/gauge-diagnostics-1.0.0.jar
```

Maven compiles with the library classpath and packages an executable JAR. Do not run `javac GaugeDiagnostics.java` alone without preparing dependencies.

Exact stdout:

```text
current=7.0
sameGauge=true
afterReplacement=7.0
stableMeters=1
afterSpike=0.0
ratioIsNaN=true
unboundedPatternMeters=5
limitedMeters=2
videoRegistered=false
afterRemove=0
```

Explanation:

- `current`: updating the actual source object updates the Gauge.
- `sameGauge`, `afterReplacement`, `stableMeters`: the same ID stays on the first Gauge, and only one meter exists for that name.
- `afterSpike`: peaks between observations are not accumulated by the Gauge.
- `ratioIsNaN`: a calculation can produce NaN even while the source object is alive.
- `unboundedPatternMeters`: five `requestId` values produce five meters; 5 is only the lab's loop bound.
- `limitedMeters`, `videoRegistered`: the filter accepts two tag values and denies the third.
- `afterRemove`: removing the Gauge leaves zero meters for that ID in the test registry.

`Reference.reachabilityFence` explicitly keeps objects alive until the end of verification; in applications, ownership is usually a bean or long-lived business object. The program does not predict GC timing or build a GC test with hypothetical stdout.

Checking `retained.value()` also confirms `strongReference(true)` works with the example's library version.

## 7. Tag Limits Are a Safeguard, Not an Aggregation

In the lab:

```java
limited.config().meterFilter(MeterFilter.maximumAllowableTags(
        "lab.limited.depth", "queue", 2, MeterFilter.deny()));
```

This snippet is taken from the full program. It caps the number of distinct values for tag `queue` on names starting with that prefix inside the configured registry.

Things to distinguish:

- A limit of 2 is illustrative, not a universal threshold for production apps.
- The filter does not add the denied meter's value into an existing meter.
- A denied meter does not appear in the registry merely because registration code did not throw an exception.
- Limiting one tag does not automatically cap remaining tags.
- The filter does not clean up IDs that already accumulated beforehand.

The API also provides `maximumAllowableMetrics` for a broader cap. Understand filter scope and ordering before using them, especially `ACCEPT` rules that can affect evaluation of subsequent filters. Cross-check [Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html) and [MeterFilter 1.13.15 source](https://github.com/micrometer-metrics/micrometer/blob/v1.13.15/micrometer-core/src/main/java/io/micrometer/core/instrument/config/MeterFilter.java).

Safeguard configuration example in Spring Boot:

```java
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class QueueMetricConfiguration {
    @Bean
    MeterFilter queueTagLimit() {
        return MeterFilter.maximumAllowableTags(
                "app.queue.depth", "queue", 20, MeterFilter.deny());
    }
}
```

Place this class in a scanned configuration package. The value 20 is an illustrative budget that must be replaced by an actual design decision. Other tags still need their own budgets.

In a Spring app, use the Spring-managed `MeterRegistry` and register filters during configuration before creating related metrics. Do not assume a registry created with `new` or a static registration path receives Spring bean filters automatically. See [Spring Boot custom metrics and MeterFilter](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.customizing).

### Do Not Collapse Gauge Tags Without Aggregating Data

Removing the `queue` tag or setting every value to `all` can cause multiple Gauges to share the same ID. That does not make the registry sum queue sizes automatically; the first-registered Gauge can continue determining the value.

If you need the total item count, design **one object/function returning the total** and register one total Gauge. If you need to distinguish a bounded set of queues, keep the `queue` dimension with a managed value set.

Likewise, caching an `AtomicInteger` for every ID prevents GC loss but becomes a memory leak if IDs are unbounded. Fixing lifecycle and fixing cardinality must go together.

## 8. Diagnostic Procedure on a Running Application

### Step 1: Identify Where Data First Goes Wrong

Distinguish four points:

```text
business object
    -> Gauge.value() in the right registry
    -> exported/scraped data
    -> query and dashboard
```

Record the metric name, tags, instance/Pod, and timestamp. An empty chart can result from a query filter or time window; it is not enough to conclude the object was garbage-collected.

### Step 2: Check Identity and Value Directly in the Registry

Diagnostic snippet for an injected registry:

```java
int totalMeters = registry.getMeters().size();
int queueMeters = registry.find("app.queue.depth").meters().size();
Gauge mail = registry.find("app.queue.depth").tag("queue", "mail").gauge();
```

If `mail` is `null`, check registration, tags, filters, and the registry in use before reading values. If the Gauge exists, compare the actual source object against `mail.value()`.

Do not log every ID/tag inside a high-load loop just to diagnose cardinality; sampling and counting by name or tag key is far safer to control.

### Step 3: Use Actuator for Its Intended Purpose

In a web application that already has Actuator, you can expose the diagnostic endpoint under your existing access policy:

```properties
management.endpoints.web.exposure.include=health,metrics
```

Example querying an app on port 8080:

```shell
curl -sS http://localhost:8080/actuator/metrics
curl -sS -G --data-urlencode "tag=queue:mail" http://localhost:8080/actuator/metrics/app.queue.depth
```

On Windows PowerShell, use `curl.exe` to avoid the alias. Adjust the URL to your actual port, context path, and credentials.

Use Micrometer names such as `app.queue.depth` when calling this endpoint. The metrics API is for diagnostics and supports filtering via `tag=key:value`; do not use it in place of a production metric collection system. See [Spring Boot 3.3 metrics API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html).

If a query omits enough tags, you may be viewing multiple meters of the same name aggregated together. When checking one measurement source, filter by the exact ID instead of matching only by name.

### Step 4: Cross-Check Exported Data and External Systems

If using Prometheus, you need the Prometheus registry and matching exposed endpoint; the `metrics` endpoint having data does not prove Prometheus scraped it.

Check the right target/instance, exported convention name, last scrape, and query. For example, if the actual exported name is `app_queue_depth`, you can count present series with:

```promql
count(app_queue_depth)
count by (queue) (app_queue_depth)
```

This counts series within query scope at evaluation time, not historical meters inside one JVM. Distinguish instant queries from range queries; see [Prometheus querying basics](https://prometheus.io/docs/prometheus/latest/querying/basics/).

Removing a meter in the JVM does not delete history already stored in the external system. After fixing, monitor both the rate of new ID creation and how old data expires in your monitoring backend.

### Step 5: Inspect Ownership and Lifecycle

Locate Gauge registration in constructors, binders, request handlers, or scheduled tasks. For each important Gauge, answer:

- Which object is being measured?
- Who keeps it alive, and for how long?
- Are values updated on the same object or swapped to a new object?
- Is the meter registered once or repeatedly?
- If the resource disappears, who removes the meter?

GC of the source object is not an automatic contract to delete every registered ID. When managing dynamic resources, the owner must manage both the source object and its corresponding meter.

### Step 6: Check the Rate of New Identity Creation

Track meter counts by name over time and count distinct values per tag. Compare against the number of queues, regions, states, or business categories that genuinely need distinguishing.

If meter count grows nearly linearly with request count even while business resources stay stable, look for per-request data in names/tags. If JVM meter count is stable yet external series grow, check replicas, infrastructure labels, and identity changes across deployments.

## 9. Fix the True Cause, Avoid Creating a Second Bug

| Hasty fix | Risk | Sound approach |
| --- | --- | --- |
| Add a new UUID tag so the Gauge updates | Meter count grows endlessly | Update the stable object of the right ID |
| Keep every object in an unbounded Map | Stops NaN but leaks memory | Manage a bounded resource set and lifecycle |
| Drop tags on multiple Gauges hoping for a sum | ID collision; value may reflect only the first source | Aggregate data before measuring |
| Increase scrape frequency to fix NaN | Does not restore a lost object | Fix ownership or value supplier |
| Raise tag limit when hitting the cap | Delays incident to a higher threshold | Fix value domain and monitor denied meters |
| Replace all missing data with 0 | Masks measurement bugs | Distinguish zero values from missing measurements |

After fixing, verify at least two independent behaviors: the Gauge tracks the right source across multiple updates, and ID count stays within budget as request load rises. If valid dynamic resources exist, also test removing meters when resources end.

## 10. Self-Check

**A. After a while a Gauge becomes NaN, yet the app still holds the Gauge variable. Is that enough to rule out GC?**

No. Check whether the source object measured by the Gauge is still held by a strong reference.

**B. The same name/tag is registered with a new AtomicInteger, yet the value remains old.**

The registry may still be using the Gauge from the first registration. Update that exact object or manage lifecycle replacement; do not add random IDs.

**C. There is only one metric name, yet the JVM holds thousands of meters for it.**

Inspect the tag sets. Name count is not ID combination count.

**D. Does removing the queue tag from three Gauges automatically create a total Gauge?**

No. You need a function reading the total or properly maintained aggregate data; making IDs collide does not sum measurement sources.

**E. A Gauge returns 0 after a variable rose to 20 and dropped back to 0 before reading.**

That is normal current-value sampling behavior. If you need to capture every event or distribution, choose a better-suited meter type.

**F. After adding a tag cap, metrics for a new queue do not appear, yet the program throws no error.**

Check the MeterFilter's decision. The meter may have been denied; the filter does not fold that data into another queue.
