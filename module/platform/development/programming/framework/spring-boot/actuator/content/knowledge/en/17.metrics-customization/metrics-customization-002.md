# Applying Naming Conventions and Understanding How Registries Transform Metric Names

## 1. A Metric Can Appear Under Different Names at Different Layers

You register a timer in Java with the name `checkout.payment`, yet when inspecting Prometheus data you see `checkout_payment_seconds_count` and `checkout_payment_seconds_sum`. Meanwhile, calling Actuator with an underscore-separated name does not find the metric.

This can be normal behavior: **the name used to declare the meter** and **the time series name exported to the monitoring system** serve two different layers.

In this lesson:

- **Meter** is a Micrometer measurement instrument, such as `Counter` or `Timer`.
- **Registry** is where meters are registered and metric export is organized.
- **Naming convention** transforms names into a form suitable for the target system.
- **Tag/label** adds classification dimensions consisting of a key and a value.
- **Time series** is a series of measurements with a specific name and label set in the monitoring system.

The goal is to assign meaningful names directly in code, preserve portability across multiple monitoring systems, and look up the right name in the right place when inspecting data.

You can visualize the path as follows:

```text
Name and labels declared in code
    → MeterFilter if identity is modified
    → Meter.Id in registry
        → Actuator metrics uses meter name
        → Conventions and exporters of each registry
            → Name, unit, and statistical series at target system
```

Not every difference in the output is a rename of `Meter.Id`. Conversely, if a filter genuinely alters identity, the effective name in the registry must also be checked again.

## 2. Name at the Source According to What Is Being Measured

### 2.1. Prefer Lowercase Words and Dots

Micrometer recommends lowercase words separated by dots:

```text
checkout.orders
checkout.payment
inventory.refresh
upload.payload
```

Write names in this neutral form rather than copying raw Prometheus series names into code. Each registry has its own convention to convert to the appropriate format on export. [Micrometer's Naming Meters documentation](https://docs.micrometer.io/micrometer/reference/1.13/concepts/naming.html) explains the choice of lowercase letters and dots to improve portability across systems.

An easy-to-read structure is "functional domain → object or operation". This is a project organizational style, not a mandatory syntax requiring strictly two or three segments.

| Unclear or hard-to-maintain name | Improvement | Reason |
| --- | --- | --- |
| `count` | `checkout.orders` | Shows what object is being counted |
| `paymentTime` | `checkout.payment` with Timer type | Clear functional domain and consistent naming style |
| `checkout.payment.12345` | `checkout.payment` | A transaction ID is not a new metric type |
| `checkout.payment.prod` | `checkout.payment` with environment label | Environment is a classification dimension |
| `checkout.payment.seconds.sum` | `checkout.payment` with Timer | Let the registry generate statistics and output names |
| `calls` shared for HTTP and database | Split into `http.calls` and `database.calls` | Summing two unrelated operation types lacks meaning |

The meter type and description should clarify the name. For example, `checkout.orders` can use a Counter to count orders for a defined event; `checkout.payment` uses a Timer to measure the duration of a single payment processing step. Do not use the same name and the same labels for incompatible meter types or quantities.

A name should carry enough context so that even when label filters are removed, a reader still understands what the measurement represents. Do not create one generic metric for counts, byte sizes, and durations and then use labels to distinguish those three quantities.

### 2.2. Keep Variable Data in Labels with Controlled Cardinality

Instead of creating a new name for each payment method:

```text
checkout.payment.creditcard
checkout.payment.banktransfer
```

you can keep a single name `checkout.payment` and use a `payment.method` label with an agreed set of values.

Label keys should also use lowercase letters and dots, such as `payment.method` or `order.type`. Label values are classification data; do not assume the registry will merge `CreditCard`, `creditcard`, and `credit_card` into the same group.

The development team should normalize business values right where labels are produced. For example, agree on a finite set of values for payment methods and a fallback value for unknown cases.

Do not move request IDs, emails, current timestamps, or transaction IDs into labels as a way to "fix" high-cardinality names. Every distinct label combination can still create a new time series. Prometheus guidelines also emphasize that classification dimensions must be meaningful and unbounded value sets must be avoided. [Prometheus Metric and label naming](https://prometheus.io/docs/practices/naming/).

### 2.3. Units Must Be Consistent, Not Inferred Only from Name Strings

For a Timer, record durations using `Duration` or an API with an explicit unit:

```java
payment.record(Duration.ofMillis(120));
payment.record(Duration.ofMillis(180));
```

This snippet illustrates usage with an already-registered `payment` timer. The registry knows this is a duration and converts it to the target system's base unit on export.

Do not rename a timer to have a `millis` suffix and assume exported data will definitely stay in milliseconds. A name does not replace a Timer's unit conversion mechanism. Likewise, do not mix byte measurements with item count measurements in the same metric.

Micrometer allows reading durations back in a specified unit, for example `totalTime(TimeUnit.MILLISECONDS)`. The Prometheus output of the same timer may represent duration in seconds. [Timers documentation](https://docs.micrometer.io/micrometer/reference/1.13/concepts/timers.html) describes the role of units in the API and when exporting measurements.

## 3. What Does a Registry Transform?

### 3.1. Case Conversion and Handling Unsuitable Characters

From the name `checkout.payment`, a convention can produce:

| Illustrative convention | Case conversion result |
| --- | --- |
| Dot-separated | `checkout.payment` |
| Snake case | `checkout_payment` |
| Camel case | `checkoutPayment` |

This is only an example of **case conversion**. The final series name also depends on the meter type, unit, exporter, and library version.

Names with spaces, hyphens, or special characters may be handled differently across systems. Do not rely on one registry accepting an awkward name to treat that name as a shared convention across the entire application. Using a simple set of lowercase words from the start reduces surprises.

### 3.2. One Meter Can Produce Multiple Statistical Series

In this lesson's Prometheus example:

| Meter in Java | Exported series | Meaning |
| --- | --- | --- |
| Counter `checkout.orders` | `checkout_orders_total` | Cumulative count |
| Timer `checkout.payment` | `checkout_payment_seconds_count` | Number of recordings tracked by the timer |
| Timer `checkout.payment` | `checkout_payment_seconds_sum` | Total duration in seconds |
| Timer `checkout.payment` | `checkout_payment_seconds_max` | Maximum duration per the timer's statistical window |

Multiple lines do not mean the application registered multiple timers for the same task. They can simply be the statistics of a single meter.

If histograms or additional statistics are enabled, the output may contain more series. Do not treat the table above as a fixed list for every registry and every configuration.

### 3.3. Label Keys and Label Values Have Different Roles

In the upcoming experiment:

```text
In Java:      payment.method = CreditCard
Prometheus:   payment_method = CreditCard
```

The label key changed its representation; the value remained unchanged. Therefore, when querying Prometheus data you must use the key that Prometheus actually receives, while using the exact value of the group you want to inspect.

Do not take the naming rules of one version as an absolute guarantee across all versions. Libraries may change how characters and suffixes are handled; inspecting actual exported data is necessary when upgrading.

## 4. Complete Java Experiment with Prometheus Registry

The example uses JDK 21 and `micrometer-registry-prometheus:1.13.0`. This is a standalone Micrometer program that does not require running a Prometheus server or starting Spring Boot.

It uses a real registry and calls `scrape()` to inspect exported data. This exposition approach is described in [Micrometer Prometheus documentation](https://docs.micrometer.io/micrometer/reference/1.13/implementations/prometheus.html).

### 4.1. Dependency

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>meter-naming-lab</artifactId>
    <version>1.0.0</version>
    <dependencies>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-registry-prometheus</artifactId>
            <version>1.13.0</version>
        </dependency>
    </dependencies>
</project>
```

The version is pinned to keep the experiment reproducible. When adding the library to a Spring Boot application, use the version managed by Spring Boot to keep components compatible.

In this version, the registry uses the new Prometheus Java client under package `io.micrometer.prometheusmetrics`. Do not mix imports with the package of the `prometheus-simpleclient` variant.

### 4.2. Source Code

Save at `src/main/java/demo/MeterNamingDemo.java`:

```java
package demo;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.config.NamingConvention;
import io.micrometer.prometheusmetrics.PrometheusConfig;
import io.micrometer.prometheusmetrics.PrometheusMeterRegistry;

import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

public class MeterNamingDemo {
    public static void main(String[] args) {
        PrometheusMeterRegistry registry =
                new PrometheusMeterRegistry(PrometheusConfig.DEFAULT);
        try {
            Counter orders = Counter.builder("checkout.orders")
                    .tag("order.type", "Express")
                    .register(registry);
            orders.increment(2);

            Timer payment = Timer.builder("checkout.payment")
                    .tag("payment.method", "CreditCard")
                    .register(registry);
            payment.record(Duration.ofMillis(120));
            payment.record(Duration.ofMillis(180));

            System.out.println("counterId=" + orders.getId().getName());
            System.out.println("timerId=" + payment.getId().getName());
            System.out.println("tagKey=" +
                    payment.getId().getTags().get(0).getKey());
            System.out.println("tagValue=" +
                    payment.getId().getTag("payment.method"));
            System.out.println("snake=" +
                    NamingConvention.snakeCase.name(
                            "checkout.payment", Meter.Type.TIMER));
            System.out.println("camel=" +
                    NamingConvention.camelCase.name(
                            "checkout.payment", Meter.Type.TIMER));
            System.out.printf(Locale.ROOT, "timerCount=%d timerMs=%.0f%n",
                    payment.count(), payment.totalTime(TimeUnit.MILLISECONDS));

            registry.scrape().lines()
                    .filter(line -> line.startsWith("checkout_"))
                    .sorted()
                    .forEach(System.out::println);
        } finally {
            registry.close();
        }
    }
}
```

The program records two orders and two duration samples of 120 ms and 180 ms. The durations are supplied directly so they do not depend on machine speed.

The two calls `NamingConvention.snakeCase.name(...)` and `NamingConvention.camelCase.name(...)` merely let us observe case conversion in isolation. The `scrape()` output shows the actual result after both the registry and the exporter have processed meter type and unit.

### 4.3. Compile and Run

From the directory containing `pom.xml`, use Maven to download dependencies and JDK 21 to compile. The first download requires access to the Maven repository.

On PowerShell/Windows:

```powershell
mvn -q dependency:copy-dependencies -DoutputDirectory=target/dependency
javac --release 21 -cp "target/dependency/*" -d target/classes src/main/java/demo/MeterNamingDemo.java
java -cp "target/classes;target/dependency/*" demo.MeterNamingDemo
```

On Linux/macOS, use the same first two commands and replace the run command with:

```bash
java -cp "target/classes:target/dependency/*" demo.MeterNamingDemo
```

Stdout:

```text
counterId=checkout.orders
timerId=checkout.payment
tagKey=payment.method
tagValue=CreditCard
snake=checkout_payment
camel=checkoutPayment
timerCount=2 timerMs=300
checkout_orders_total{order_type="Express"} 2.0
checkout_payment_seconds_count{payment_method="CreditCard"} 2
checkout_payment_seconds_max{payment_method="CreditCard"} 0.18
checkout_payment_seconds_sum{payment_method="CreditCard"} 0.3
```

The program prints only data lines starting with `checkout_` and sorts them for deterministic ordering. This is not the entire scrape text: type and help lines starting with `#` were excluded from printing.

### 4.4. Reading Results at the Right Layer

- `getId().getName()` still returns `checkout.orders` and `checkout.payment`.
- In meter identity, the label key is still `payment.method`.
- Simple snake-case convention produces `checkout_payment`; it does not yet represent all output suffixes of a Timer.
- Prometheus exports durations in seconds: 120 + 180 ms corresponds to a total of 0.3 seconds.
- `_count` equal to 2 is the number of measurements, not seconds.
- `_max` equal to 0.18 seconds when read immediately after the two samples in the program.

A timer's maximum value also depends on the statistical window; do not infer that it is always the all-time maximum since JVM startup. For this lesson, the key takeaway is that the series name tells you which statistic you are reading and you must read the right unit.

## 5. Applying in Spring Boot Actuator

### 5.1. Register with the Original Name and Application Registry

In a Spring Boot application, inject the configured `MeterRegistry` and register with the original name:

```java
Timer payment = Timer.builder("checkout.payment")
        .tag("payment.method", "CreditCard")
        .register(meterRegistry);
```

This illustrates usage with `meterRegistry` provided by the application. There is no need to manually change the name to `checkout_payment_seconds` in Java just because Prometheus is used.

Constructing `new PrometheusMeterRegistry(...)` in section 4 served the standalone experiment. In a Spring Boot service, creating your own extra registry can place measurements outside the registry used by Actuator and the application's exporter.

To export Prometheus in a Spring Boot application that already has Actuator, add the Spring Boot-managed `io.micrometer:micrometer-registry-prometheus` dependency and expose the endpoints to test:

```properties
management.endpoints.web.exposure.include=health,metrics,prometheus
```

This configuration is for the practice environment; management endpoint access permissions still follow the application's security configuration.

### 5.2. Looking Up the Original Name via the metrics Endpoint

Suppose the application is running on port 8080 and has recorded the timer above:

```bash
curl "http://127.0.0.1:8080/actuator/metrics"
curl --get "http://127.0.0.1:8080/actuator/metrics/checkout.payment" --data-urlencode "tag=payment.method:CreditCard"
```

On PowerShell, you can call `curl.exe` to avoid the alias. If the application has a separate management path or port, use the corresponding URL.

With the `metrics` endpoint, use `checkout.payment` and label key `payment.method` as in the registry. Do not use `checkout_payment_seconds_sum` as the selector name for this endpoint.

Then read the Prometheus output:

```bash
curl "http://127.0.0.1:8080/actuator/prometheus"
```

In this output, look for exported series names such as `checkout_payment_seconds_sum` along with the `payment_method` label key under the experiment's library versions.

[Spring Boot's Metrics Endpoint documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.endpoint) requires using the meter name, rather than the name normalized for the monitoring system, when selecting metrics via `/actuator/metrics/{name}`.

### 5.3. Configuring by Original Name When Using Spring Boot Mechanisms

For example, histogram configuration for a timer is selected using the meter name:

```properties
management.metrics.distribution.percentiles-histogram.checkout.payment=true
```

Meanwhile, a Prometheus query uses the exported name:

```promql
checkout_payment_seconds_sum{payment_method="CreditCard"}
```

This query selects the cumulative total duration for the matching group; it does not automatically compute average duration or processing rate.

Distinguishing the two places avoids configuring Prometheus names at the Spring Boot layer, or querying dot-separated names as if they were series names generated by the exporter.

## 6. NamingConvention Differs from Identity Changes via MeterFilter

There are three distinct changes:

| Change | Primary Effect |
| --- | --- |
| Renaming at the meter declaration call | Changes the name registered by application code |
| `MeterFilter` mapping names/labels | Can alter the identity registered in the registry |
| `NamingConvention` and exporter | Converts representation to suit the receiving system |

`MeterFilter` can replace names, add or drop labels, and adjust statistics. It is not merely a tool for converting dots to underscores. [Meter Filters documentation](https://docs.micrometer.io/micrometer/reference/1.13/concepts/meter-filters.html) describes these responsibilities.

Micrometer also allows installing a custom convention:

```java
registry.config().namingConvention(customConvention);
```

This is an extension point, where `customConvention` is a `NamingConvention` implementation provided by the application. It must be configured during initialization, before registering the relevant meters.

Do not replace every registry's default convention with `NamingConvention.snakeCase` just to make names "uniform". A system-specific convention may also account for meter type, units, and specific constraints. Using a simple string case conversion can discard that handling.

In Spring Boot, `MeterRegistryCustomizer` is the right place to customize a registry before meters are registered. If only one target system needs changes, scope the customization to that registry type. When using multiple target registries, it is reasonable for the same original name to export as different names.

Such a change should be treated as a monitoring data contract change: you must verify actual names, queries, dashboards, and alerts that consume them.

## 7. Name Collisions After Conversion and Reserved Suffixes

### 7.1. Two Different Original Names Can Still Export to the Same Name

An example to examine before using:

```text
checkout.payment
checkout_payment
```

When a system normalizes dots to underscores, those two names can lose their distinction in the output.

The same can happen with two label keys:

```text
payment.method
payment_method
```

Do not use both to represent two different meanings and rely on the registry to preserve the difference. How collisions behave depends on the exporter and version: there may be warnings, registration errors, or data not exported as intended. Do not rely on implicit behavior when designing names.

The way to prevent this is to standardize on one original naming style, use each name for one clear quantity, and verify the mapping to each target system.

### 7.2. Do Not Manually Append Exporter Statistic Suffixes

With Micrometer Counters and Timers, let the exporter handle suffixes such as `_total`, `_count`, `_sum`, and `_bucket` according to meter type.

In particular, Micrometer 1.13 moved the Prometheus registry to the new Java client and has rules for handling reserved suffixes like `.total`, `.created`, `.bucket`, and `.info`. A suffix manually added to the original name may be stripped or regenerated based on meter type; thus tweaking name strings by intuition does not guarantee the desired output.

The migration guide also notes that `.info` has special meaning for Gauges, so do not turn this recommendation into a blanket rule forbidding any name containing the word `info`. The key point is knowing which suffixes belong to which meter type convention before using them. [Micrometer 1.13 Migration Guide — Invalid Meter suffixes](https://github.com/micrometer-metrics/micrometer/wiki/1.13-Migration-Guide#invalid-meter-suffixes).

For this lesson's experiment, choosing `checkout.orders` for the Counter and `checkout.payment` for the Timer is sufficient; there is no need to manually create extra meters named after output statistical series.

## 8. Diagnosing When a Metric Cannot Be Found Under the Expected Name

Proceed from code toward actual data:

1. Confirm the name and labels at the meter registration site; check the instrument type and unit.
2. Check whether any `MeterFilter` changes identity, denies the meter, or drops labels.
3. Read the `/actuator/metrics` list and details using the effective name in the registry.
4. Confirm which target registry and exporter are configured.
5. Read `/actuator/prometheus` or the equivalent output of the target system.
6. Cross-check series name, label keys, label values, unit, and statistic.
7. If libraries were just upgraded, check export rule changes before editing declaration code.

| Symptom | What to Check |
| --- | --- |
| Actuator does not recognize underscore-separated name | Using Prometheus exported name where meter name is required |
| Prometheus lacks the dot-separated name from Java | Name was normalized during export |
| Metric name matches but label filter does not match | Label key changed format or value differs in casing |
| `sum` is 1,000 times smaller than expected milliseconds | May be reading seconds instead of milliseconds |
| Multiple lines appear for one timer | Check whether they are count, sum, max, or bucket |
| Different original names have missing/anomalous exported data | Check post-conversion collisions and reserved suffixes |
| Convention changed but data is inconsistent | Check configuration timing, affected registry, and already-registered meters |

Measurements that were filtered out, not yet registered, or recorded in another registry cannot be solved merely by changing query names. Do not conclude every "not found" case is caused by dots vs. underscores.

## 9. When Renaming, Protect How Others Consume the Metrics

Metric names and label keys are part of the contract between the application and the monitoring system. Renaming `checkout.payment` to a new name can stop existing dashboards from receiving data, even though the code compiles and the application runs.

Before renaming, determine:

- Whether the original name, meter type, and unit change meaning.
- What the exported names on the active registries will become.
- Which queries, recording rules, dashboards, and alerts reference the old names or labels.
- How the transition period will be represented so readers do not mistakenly sum old and new numbers.

Renaming merely to make names "prettier" still carries compatibility costs. For framework-generated metrics, prefer supported built-in names or documented renaming mechanisms; avoid bulk-editing based solely on output series strings you observe.

## 10. Check Your Understanding

1. Java registers `checkout.payment`, but Prometheus exports `checkout_payment_seconds_sum`. Which name is used to select the meter via Actuator?
2. What `_count` and `_sum` values do the two samples 120 ms and 180 ms produce in the experiment?
3. Why does `NamingConvention.snakeCase.name(...)` only print `checkout_payment` while scrape also includes `_seconds_count`?
4. When label key `payment.method` becomes `payment_method`, does the value `CreditCard` automatically become `credit_card`?
5. Are the two names `checkout.payment` and `checkout_payment` always safe for representing two different quantities?

Answer key: use the original name `checkout.payment`; count is 2 and sum is 0.3 seconds; because case conversion does not include all meter-type/unit/statistic processing of the exporter; the value does not automatically change as assumed; the two names can collide after normalization.

Once you can read the original name, map it to the actual output name, and accurately explain each label, unit, and statistic suffix, you can choose new names consistently and diagnose metric lookup issues without guessing.
