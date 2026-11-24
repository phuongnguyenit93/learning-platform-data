# How Micrometer Provides an Abstraction Layer for Metrics

An order-processing service may need to know how many requests are rejected per minute, how long successful processing runs take, and how many orders are currently waiting. Those are questions about counts, durations, and states that can be represented numerically.

If every place in business code called a monitoring product's API directly, switching products would force changes across many layers. Micrometer places a common instrumentation API between the application and different collection and export mechanisms.

After this lesson, you can explain the roles of `Meter`, `MeterRegistry`, and per-monitoring-system registries; read a measurement point with its name and tags; and verify that the same instrumentation code works across different registries. Examples use Micrometer 1.13.0, from the Micrometer line used with Spring Boot 3.3.x, with Java 17 code runnable on JDK 21.

## 1. Understand metrics before the abstraction layer

A metric is quantitative information about an application. When collected over time, it helps answer questions such as:

- Is the number of rejected requests rising quickly or slowly?
- How is the average processing time changing?
- How many items are currently sitting in the queue?

For example, the `shop.checkout.rejected` counter with tag `reason=validation` represents the number of times a checkout request was rejected as invalid. A monitoring system can use samples over time to calculate the rejection rate over a time window.

This information differs from a log record describing the details of a single failure, or a trace following a request's path across multiple components. Metrics are typically useful for observing trends and comparing groups; to inspect the details of a specific request, an appropriate observability source is needed.

On the input side, the application decides **what to measure and when**. On the output side, the monitoring system decides **how to store, query, and display measurements**. Micrometer provides a way to connect those two sides using a common instrumentation model.

## 2. What dependency does Micrometer solve?

Suppose an application wants to record how many times checkout is rejected. When coupled directly to a specific monitoring library, the instrumentation point can depend on how that library creates counters, names metrics, and attaches labels. When a second destination is added, business classes may have to learn yet another API.

With Micrometer, code at the instrumentation point only uses the common API:

```java
Counter rejected = registry.counter(
        "shop.checkout.rejected", "reason", "validation");
rejected.increment();
```

This snippet requires a `registry` variable of type `MeterRegistry` and importing `io.micrometer.core.instrument.Counter`. The standalone example in Section 6 provides all the components in full.

Code calling `increment()` does not need to know whether the data ultimately goes to Prometheus, another monitoring service, or only stays in memory during testing. How it connects to destinations resides in configuration and the registry implementation.

Micrometer is designed as a facade API for instrumenting JVM applications, helping instrumentation code avoid vendor lock-in. [Purpose of Micrometer](https://docs.micrometer.io/micrometer/reference/concepts.html).

The benefit has a clear boundary: switching monitoring systems usually concentrates in dependencies, export configuration, and operations. The business semantics of the measurement point remain the application's responsibility. A misplaced counter will still produce misleading numbers even after switching registries successfully.

## 3. How do the components relate to each other?

```text
Application code and built-in instrumentation
        |
        v
Common API: Counter, Timer, Gauge, ...
        |
        v
MeterRegistry
        |
        +--> in-memory registry for testing
        |
        +--> registry for monitoring system A
        |
        +--> registry for monitoring system B
                      |
                      v
           Collection/export, storage, and querying
                      |
                      v
                 Charts and alerts
```

| Component | Responsibility | Question it addresses |
| --- | --- | --- |
| Application instrumentation code | Chooses when and what data to measure | When should the rejection count be incremented? |
| `Meter` | Common model of a measurement instrument | Which measurements does this instrument provide? |
| `Counter`, `Timer`, `Gauge` | APIs for different measurement semantics | Counting events, measuring duration, or reading current state? |
| `MeterRegistry` | Registers, manages, and finds meters; provides the appropriate implementation | Which registry does the meter belong to? |
| System-specific registry | Translates the Micrometer model into that system's representation and export format | How is the data formatted and sent out? |
| Monitoring system | Ingests, stores, computes, and serves queries | What was the error rate in the last five minutes? |
| Spring Boot Actuator | Integrates, auto-configures, and exposes management capabilities in Spring Boot applications | How are the registry and built-in instrumentation wired into the application? |

`MeterRegistry` is an **abstract class in Java**, while `Counter`, `Timer`, and `Gauge` are measurement interfaces. Do not interpret "abstraction layer" in the article title as merely the `abstract` keyword: at the design level, it is also a shared contract that decouples calling code from each system's implementation.

Micrometer does not itself become a historical storage server, dashboard, or alerting engine. Those capabilities typically live in the monitoring system and its accompanying operational components.

### Three registries that clarify the roles

- `SimpleMeterRegistry`: holds measurements in memory, suitable for experimentation and testing; does not automatically export data to a monitoring server.
- System-specific registry: for example `PrometheusMeterRegistry`, providing an implementation tailored to the target system.
- `CompositeMeterRegistry`: connects multiple child registries so instrumentation points can write to multiple destinations.

Registries are where meters are created and held; a composite registry enables sharing a single write path across multiple child registries. [Micrometer registry concepts](https://docs.micrometer.io/micrometer/reference/concepts/registry.html).

## 4. The shared contract: name, tags, and meter type

### 4.1. Name describes the quantity; tags describe dimensions

Consider three counters:

```text
shop.checkout.rejected {channel=web, reason=validation}
shop.checkout.rejected {channel=mobile, reason=validation}
shop.checkout.rejected {channel=web, reason=stock}
```

The shared name tells you what quantity is being counted. Tags, also called dimensions, tell you which group a measurement belongs to. Operators can view the total across groups or filter by channel and reason.

Within the same registry, a meter is identified by the combination of **name and tag set**. Changing a tag value creates a different identity. Re-registering the same name and tags for the same instrument type retrieves the existing meter; it does not automatically create an independent counter for each Java variable. [Meter model](https://docs.micrometer.io/micrometer/reference/concepts/meters.html).

```java
Counter first = registry.counter(
        "shop.checkout.rejected", "reason", "validation");
Counter same = registry.counter(
        "shop.checkout.rejected", "reason", "validation");
first.increment();
System.out.println(same.count());
```

In `SimpleMeterRegistry`, the snippet above prints `1.0`. Both variables reference the same counter. When moving to another registry, you still need to understand how that implementation aggregates and exposes measurements to interpret readings accurately.

Do not register a `Counter` and then reuse that same identity for a `Timer`. With the version in this example, the registry throws an `IllegalArgumentException` on this type conflict. The meter type is part of the contract that must stay consistent, not a way to attach an extra data channel under the same identity.

### 4.2. Logical names do not necessarily match exported names

Micrometer recommends lowercase words separated by dots, such as `shop.checkout.duration`. A registry may translate names to the target system's conventions, along with unit representations and corresponding statistics. [Meter naming conventions](https://docs.micrometer.io/micrometer/reference/concepts/naming.html).

Therefore, when reading Java code, look for the registered logical name; when writing queries for a monitoring system, check the actual exported name and structure. Do not deduce a time-series name simply by copying the Java name verbatim or appending suffixes from memory.

### 4.3. Number of meters and number of time series can differ

A single meter does not necessarily produce only one value. A `Timer` provides at minimum the recorded count and total time; additional statistics depend on the registry type and configuration. Consequently, two tags creating two meter identities does not mean the monitoring system only has to store two time series.

Keeping the name and tag schema consistent for the same quantity allows counters or timers to be queried and compared meaningfully. For instance, all groups of `shop.checkout.duration` should use the same meaning for the `outcome` tag.

## 5. Choosing an instrument by the meaning of the question

| Question | Typically appropriate instrument | Key point to understand |
| --- | --- | --- |
| How many rejections have occurred? | `Counter` | Increases monotonically with recordings; suited for computing event rates |
| How long did the recorded operations take? | `Timer` | Tracks count and total time, accepting explicit time units |
| How long is the queue right now? | `Gauge` | Reads the current state at observation time |
| How are payload sizes distributed? | `DistributionSummary` | Records distributions of non-time values, such as byte counts |
| Which long-running tasks are still active and how long have they been running? | `LongTaskTimer` | Suited for tracking tasks that are still in flight |

This table guides semantic selection; it is not a requirement to use every meter type in one application.

### Counter and Gauge do not replace each other

`Counter` is for cumulative increases caused by events. Do not use counter decrements to represent the number of in-flight requests. The number of running tasks or queue length can go up and down, so it typically requires a current-state measurement.

`Gauge` observes an object or a value-supplying function. Changes occurring between two collections do not automatically become a complete history. If you need to know the total number of times an event happened, merely reading the current value is not enough. [Gauge semantics](https://docs.micrometer.io/micrometer/reference/1.13/concepts/gauges.html).

### Timer already includes the recorded count

If each processing run is already recorded in a `Timer`, you can use the timer's count to know how many such events occurred; there is no need to add a counter just to recount the exact same set of events. A counter is more appropriate when the counting question has a distinct meaning. [Counter semantics](https://docs.micrometer.io/micrometer/reference/1.13/concepts/counters.html).

In the next example:

- The Counter counts requests rejected due to input validation.
- The Timer measures successful checkout runs.

Those are two distinct event sets. A rejected attempt does not automatically increment the timer's success count.

### Units are part of the contract

`Timer.record(Duration)` or `Timer.record(amount, TimeUnit)` expresses the unit explicitly. The registry converts measurements to the unit appropriate for the destination. When reading back with `totalTime(...)`, the caller also specifies the desired unit. [Timer and time units](https://docs.micrometer.io/micrometer/reference/1.13/concepts/timers.html).

For example, 120 ms and 80 ms total 200 ms, which is also 0.2 seconds. Those two representations describe the same amount of time. Putting the word "milliseconds" in a name while passing a unitless number to another instrument does not provide as clear a contract as the time API.

## 6. Java example: same instrumentation code, different registries

The example creates a standalone in-memory registry and a composite registry connected to two other in-memory registries. The goal is to observe how instrumentation code is decoupled from destinations; the program does not connect to an external server.

### 6.1. Preparing dependencies

Create a separate experiment directory with two files:

```text
micrometer-abstraction-demo/
├── pom.xml
└── MicrometerAbstractionDemo.java
```

Contents of `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>micrometer-abstraction-demo</artifactId>
    <version>1.0.0</version>

    <dependencies>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-core</artifactId>
            <version>1.13.0</version>
        </dependency>
    </dependencies>
</project>
```

The version is pinned so the standalone example is reproducible. In a Spring Boot project using Boot's dependency management, use the Micrometer version managed by Boot's BOM rather than copying this experimental version number into every module.

### 6.2. Complete code

Contents of `MicrometerAbstractionDemo.java`:

```java
import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.composite.CompositeMeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public class MicrometerAbstractionDemo {

    static final class CheckoutMetrics {
        private final Counter rejected;
        private final Timer successfulDuration;

        CheckoutMetrics(MeterRegistry registry) {
            rejected = Counter.builder("shop.checkout.rejected")
                    .description("Checkout requests rejected by validation")
                    .tag("channel", "web")
                    .tag("reason", "validation")
                    .register(registry);

            successfulDuration = Timer.builder("shop.checkout.duration")
                    .description("Duration of successful checkouts")
                    .tag("channel", "web")
                    .tag("outcome", "success")
                    .register(registry);
        }

        void rejectedByValidation() {
            rejected.increment();
        }

        void successfulCheckout(Duration duration) {
            successfulDuration.record(duration);
        }
    }

    public static void main(String[] args) {
        SimpleMeterRegistry local = new SimpleMeterRegistry();
        SimpleMeterRegistry first = new SimpleMeterRegistry();
        SimpleMeterRegistry second = new SimpleMeterRegistry();
        CompositeMeterRegistry composite = new CompositeMeterRegistry();
        try {

            composite.add(first);
            composite.add(second);

            runScenario(new CheckoutMetrics(local));
            runScenario(new CheckoutMetrics(composite));

            printSnapshot("local", local);
            printSnapshot("first", first);
            printSnapshot("second", second);
        } finally {
            composite.close();
            first.close();
            second.close();
            local.close();
        }
    }

    private static void runScenario(CheckoutMetrics metrics) {
        metrics.rejectedByValidation();
        metrics.successfulCheckout(Duration.ofMillis(120));
        metrics.successfulCheckout(Duration.ofMillis(80));
    }

    private static void printSnapshot(
            String label, MeterRegistry registry) {
        Counter rejected = registry.get("shop.checkout.rejected")
                .tags("channel", "web", "reason", "validation")
                .counter();
        Timer duration = registry.get("shop.checkout.duration")
                .tags("channel", "web", "outcome", "success")
                .timer();

        System.out.printf(Locale.ROOT,
                "%s rejected=%.0f completed=%d totalMs=%.0f meanMs=%.0f%n",
                label, rejected.count(), duration.count(),
                duration.totalTime(TimeUnit.MILLISECONDS),
                duration.mean(TimeUnit.MILLISECONDS));
    }
}
```

The classes have distinct roles:

1. `CheckoutMetrics` depends only on the common APIs `MeterRegistry`, `Counter`, and `Timer`. Both meters are registered once in the constructor and stored in fields.
2. `runScenario(...)` only describes the recordings. It does not inspect what type the registry has and has no per-destination branches.
3. `main` owns how the registries are wired. Child registries are added before creating meters and before running the scenario.
4. `printSnapshot(...)` reads data by name and tags to verify each destination.
5. The `finally` block closes the registries created by the program itself. With API 1.13.0 used here, the program calls `close()` directly.

Two fixed duration values are passed so the output can be verified. The program does not claim real business logic always takes 120 ms or 80 ms, nor does it use `Thread.sleep(...)` to simulate performance measurements.

### 6.3. Compile and run

Maven and JDK 17 or newer are required. On JDK 21, it still compiles targeting Java 17 language level. In the directory containing the two files, download runtime dependencies into `lib`:

```shell
mvn -q dependency:copy-dependencies -DincludeScope=runtime -DoutputDirectory=lib
```

On PowerShell/Windows:

```powershell
New-Item -ItemType Directory -Path out -Force | Out-Null
javac -encoding UTF-8 --release 17 -cp "lib/*" -d out MicrometerAbstractionDemo.java
java -cp "out;lib/*" MicrometerAbstractionDemo
```

On Linux/macOS:

```shell
mkdir -p out
javac -encoding UTF-8 --release 17 -cp "lib/*" -d out MicrometerAbstractionDemo.java
java -cp "out:lib/*" MicrometerAbstractionDemo
```

The classpath separator between entries is `;` on Windows and `:` on Linux/macOS. Maven needs access to the dependency repository on the first run if the machine does not yet have the libraries cached.

Stdout:

```text
local rejected=1 completed=2 totalMs=200 meanMs=100
first rejected=1 completed=2 totalMs=200 meanMs=100
second rejected=1 completed=2 totalMs=200 meanMs=100
```

`Locale.ROOT` keeps number formatting consistent across machine locale settings.

### 6.4. What proves the abstraction layer is working?

The exact same constructor `CheckoutMetrics(MeterRegistry)` accepts both `SimpleMeterRegistry` and `CompositeMeterRegistry`. The exact same `runScenario(...)` produces accurate results at the destinations without changing how `increment()` or `record(...)` is called.

`local` receives an independent scenario run. `first` and `second` both receive the scenario written to `composite`; the application did not execute the business logic twice to feed two destinations.

Each destination records one rejection and two successes. The timer has a total of 200 ms, so the mean is 100 ms. The `completed` count comes from `Timer.count()`, not from the rejection counter.

Both child registries are in-memory so the experiment requires no network. This demonstrates decoupling at the API and distribution mechanism. When using a registry for an external system, you still need to verify export configuration and actual results in that system.

## 7. Boundaries of reuse

### 7.1. Recording code stays intact; output configuration can change

What typically remains intact:

- The logical name and meaning of the measurement point.
- API calls to `Counter`, `Timer`, and `Gauge`.
- When counters are incremented or durations are recorded in the business flow.
- Tag categorization conventions with controlled value sets.

What still needs attention when switching monitoring systems:

- Registry library, target endpoint, credentials, and operational configuration.
- Physical naming conventions, exported units, and data formats.
- Pull-based scraping versus push-based publishing mechanisms.
- Aggregation intervals, counter representations, and statistical windows.
- Queries, dashboards, alerts, and statistical features supported by the destination.

For example, you cannot expect a query written for one system to run verbatim in another merely because both ingest data from Micrometer. The abstraction layer keeps code at the instrumentation point stable, while interpreting the output data must match the target system.

### 7.2. A composite registry is not a historical replay store

A counter increment while a composite registry has no destinations will not be replayed just because a child registry is added later. The new child registry only begins receiving subsequent writes. Adding a registry mid-flight while the application is running does not reconstruct data that occurred earlier.

For state-reading instruments such as gauges, observation timing has different semantics from replaying counter increments. When verifying, identify the meter type rather than applying counter rules to every instrument.

### 7.3. In-memory measurements do not prove data reached the server

A successful `increment()` call is not a receipt proving the monitoring server stored the data. Check step by step: whether the meter was recorded, whether the right registry was configured, whether data was exported or scraped, and whether the destination holds the right data.

In particular, `SimpleMeterRegistry` is a useful testing tool but does not automatically create external historical charts. Conversely, data already stored in a monitoring system may remain queryable even if the application process just restarted and local counters reset.

### 7.4. Choosing meaningful aggregations

The absolute value of a counter can depend on the lifetime of the process. To answer "how many times per second is this happening now," you need the rate of change over an appropriate time window rather than looking only at the current total.

For timers, two instances with different invocation counts should not be averaged by taking the arithmetic mean of their two averages. For example:

```text
Instance A: total 200 ms for 2 runs -> average 100 ms
Instance B: total 800 ms for 1 run -> average 800 ms
Overall: total 1000 ms for 3 runs -> average about 333.33 ms
```

The value 450 ms from `(100 + 800) / 2` is not the average of the three runs. Calculations must use quantities over the same time window and with the same meaning. A common API does not fix an incorrect aggregation query.

Do not assume a timer always has every percentile or histogram enabled. Those statistics must be configured and appropriately supported by the destination; this lesson relies only on count and total time for verification.

## 8. Tags are useful when their cardinality is controlled

The number of distinct tag combinations is commonly referred to as cardinality. For instance, a measurement point with three channels, two outcomes, and four regions has at most `3 × 2 × 4 = 24` combinations before accounting for additional dimensions. Not every combination has to appear.

Each combination can entail multiple time series depending on meter type and configuration. Adding per-user or per-request tags can cause the number of identities to grow continuously.

| Tag | Example | Assessment by measurement goal |
| --- | --- | --- |
| `channel` | `web`, `mobile` | Reasonable if the value set is bounded |
| `outcome` | `success`, `failure` | Reasonable when semantics are consistent |
| `reason` | `validation`, `stock` | Reasonable when normalized into clear groups |
| `requestId` | A new ID per request | Usually causes combinations to grow per request |
| `userId` | One value per user | Usually unsuitable for general metrics categorization |
| `uri` | Path containing specific order IDs | Must be normalized into route templates when measuring HTTP |

User-supplied data must be normalized and bounded before becoming a tag. For fine-grained per-request identifiers, logs or traces are usually the more suitable place for lookup, following the application's observability design.

One control mechanism at the registry level is `MeterFilter`: it can deny meters, transform identities, or configure statistics. A filter that denies registration may return a no-op instrument that does not record data, so calling code continues running without storing measurement data. [MeterFilter](https://docs.micrometer.io/micrometer/reference/1.13/concepts/meter-filters.html).

Filters are an additional control layer. They do not replace choosing meaningful tags with managed value sets right at the instrumentation point. Configuring global rules before creating meters keeps behavior consistent.

## 9. Bringing this model into Spring Boot Actuator

In Spring Boot, you typically add `spring-boot-starter-actuator` to the project, use the dependency version managed by Boot, and inject the Spring-provided `MeterRegistry`. Corresponding registry libraries on the classpath are auto-configured when relevant conditions and properties allow. [Metrics in Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

You can turn `CheckoutMetrics` from the example into an application bean and inject `MeterRegistry` via its constructor. Business code continues calling `rejectedByValidation()` or `successfulCheckout(...)`; configuration selects the data destinations.

Setting an application name or deployment region via shared configuration helps categorize meters consistently. The following example is a configuration file for a Spring Boot application that already has the Actuator dependency, not something to add to the standalone Java program:

```java
package example.metrics;

import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.actuate.autoconfigure.metrics.MeterRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MetricsConfiguration {
    @Bean
    MeterRegistryCustomizer<MeterRegistry> commonMetricsTags() {
        return registry -> registry.config().commonTags(
                "application", "checkout-service",
                "region", "vn-south");
    }
}
```

The file is placed at `example/metrics/MetricsConfiguration.java` under the source root and must be within Spring's component-scan scope or imported. Common tags are configured before meters are registered. [MeterRegistryCustomizer API 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/metrics/MeterRegistryCustomizer.html).

In a web application, Actuator's `metrics` endpoint helps inspect existing measurements; exporting to a monitoring system and exposing management endpoints are separate pieces of configuration. Having measurements on the inspection endpoint does not prove an external server is collecting data. When exposing management interfaces over the network, apply access controls appropriate to the exposed data.

Actuator also integrates many built-in measurements. Domain-specific business metrics still need to be defined accurately by the application. Before adding a measurement, check whether an equivalent quantity already exists to avoid duplicate recording or creating two confusing names.

## 10. Common mistakes and how to recognize them

| Symptom | What to check |
| --- | --- |
| `increment()` is called, but the monitoring backend shows no data | Which registry is actually used, filters, export config, collection path, and read timing |
| A child registry is added later, but old counter values are missing | Composite registries do not replay increments made before a destination was attached |
| Each Java variable was expected to have its own counter, yet numbers add up | Do the name and tags match inside the same registry? |
| Error when registering a meter | Is the same identity being used for different instrument types? |
| Time-series count grows very rapidly | Do tags contain request IDs, user IDs, or unnormalized data? |
| Code records ms, while the chart displays a different unit | Check input units, exported units, and the query |
| Using a timer and also adding a counter that counts every success | Are two distinct quantities needed, or are you double-recording the exact same meaning? |
| Gauge drops to `NaN` or loses data | Is the state object still held by a strong reference? |

Gauges typically hold a weak reference to the observed object. If you register a temporary object and stop retaining it, the garbage collector may reclaim that object. For an `AtomicInteger` representing state, the application must keep the object alive for the lifetime of the measurement, such as in a bean field.

Managing lifecycles properly is also important for registries. In a standalone program, you own creating and closing registries. In Spring Boot, using Spring-managed beans ensures instrumentation follows the shared configuration and lifecycle.

## 11. Practice exercises to verify understanding

Make each change in the standalone program and predict the output before running:

1. Add one call to `successfulCheckout(Duration.ofMillis(50))` in `runScenario(...)`. Each destination must show `completed=3`, `totalMs=250`; the mean formats as `83` because the print pattern uses `%.0f`.
2. Remove `composite.add(second)`. `first` still receives data; `printSnapshot("second", second)` will report that the meter is not found because the example uses the mandatory `get(...)` lookup. This helps distinguish destination-wiring errors from instrumentation-point errors.
3. Register another counter with the same name but tag `reason=stock`, then increment it once. The `reason=validation` counter stays unchanged; queries must select the exact group you want to inspect.
4. In a separate experiment with a new composite registry, create a counter and increment it before adding any child registries. Then add a child registry and read it back: prior increments are not recovered. Increment again to verify the new write path.
5. In a new in-memory registry, register a counter with the same name and tags via two variables and increment through one variable. Read through the other variable to confirm they share a single meter.

For integration testing of a real application, separate two questions: did the instrumentation point record the right data into the registry, and did the monitoring system successfully receive the exported data? Each question needs evidence at the right boundary.

