# Roles of Meter, Meter.Id, MeterRegistry, and CompositeMeterRegistry

## 1. Starting from a concrete measurement

Suppose an application needs to count processed orders, broken down by intake channel and outcome. Each time an order completes, business code needs to record one more occurrence; the measured data can then be read within the application or sent to a monitoring system.

Micrometer divides this work into four concepts. **`Meter` is the measurement instrument; `Meter.Id` describes the instrument's identity and metadata; `MeterRegistry` creates, holds, and looks up instruments; `CompositeMeterRegistry` coordinates multiple registries so a single write is forwarded to multiple destinations.** Spring Boot Actuator integrates and exposes these measurements as part of the application's observability.

| Component | Question it answers | Example |
| --- | --- | --- |
| `Meter` | What is being measured, and through which interface is it read/written? | `Counter` counting completed orders |
| `Meter.Id` | How is this measurement instrument identified? | Name `shop.orders`, tags `channel=web`, `result=success` |
| `MeterRegistry` | Where do we obtain or register a measurement instrument? | `registry.counter(...)` returns the corresponding counter |
| `CompositeMeterRegistry` | Which registries should a single write be forwarded to? | Forwards `increment()` to two child registries |

In this lesson, "meter" refers to the measurement instrument object; "measurement" refers to a value or statistic it provides; "time series" refers to data stored by a monitoring system across multiple points in time. Creating a meter does not automatically give you a historical database.

Examples and implementation details are verified against **Micrometer 1.13.0**, the version line corresponding to Spring Boot 3.3. Standalone examples use Java 17+; when working inside a Boot project, let Boot manage the compatible Micrometer version.

## 2. Meter: the common interface of measurement instruments

`Meter` is the foundational interface for a set of related measurements. Types such as `Counter`, `Timer`, `Gauge`, `DistributionSummary`, and `LongTaskTimer` have different measurement semantics, not different naming styles for a single counter.

- `Counter` records cumulative increases, such as the number of orders processed.
- `Timer` records the count and duration of operations.
- `Gauge` reads a current value, such as the number of pending jobs.
- `DistributionSummary` observes the magnitude of samples, such as message sizes.

At the `Meter` level, two important operations are `getId()` to read the identity and `measure()` to iterate over statistics as `Measurement` objects. When recording data, use the type-specific interface: `Counter.increment()`, `Timer.record(...)`, or a gauge's observation mechanism. There is no universal `Meter.increment()` method for every type.

```java
Counter completed = registry.counter(
    "shop.orders", "channel", "web", "result", "success");

completed.increment();

Meter meter = completed;
Meter.Id id = meter.getId();

for (var measurement : meter.measure()) {
    System.out.println(
        measurement.getStatistic() + "=" + measurement.getValue());
}
```

The snippet above illustrates API usage inside a method that already has a `registry` variable; it is not a standalone program. A counter typically provides the `COUNT` statistic. For a timer with multiple statistics and, depending on configuration, additional histograms, a single meter can become multiple time series in the target system. Therefore, **the number of meters in a registry does not equal the number of exported time series**. [Micrometer Meter concept](https://docs.micrometer.io/micrometer/reference/concepts/meters.html).

## 3. Meter.Id: identity is distinct from measured values

### 3.1. What is inside an identity?

`Meter.Id` holds the name, tags, meter type, and metadata such as description and base unit. For example:

```text
name        = shop.orders
tags        = channel=web, result=success
type        = COUNTER
baseUnit    = orders
description = Completed orders
```

| Property | Role |
| --- | --- |
| `name` | Name of the concept being measured, such as `shop.orders` |
| `tags` | Categorization dimensions as key-value pairs |
| `type` | Instrument type such as `COUNTER`, `TIMER`, `GAUGE` |
| `baseUnit` | Unit that helps interpret the measured quantity; not the count value |
| `description` | Meaning description so operators understand the metric |

The current value, such as `3.0`, belongs to the counter's state/measurements, not to `Meter.Id`. Thus, a counter incrementing from 2 to 3 does not create a new ID.

### 3.2. Name and tags determine identity

In Micrometer 1.13, `Meter.Id.equals()` and `hashCode()` are based on **the name and normalized tag set**. Type, description, and base unit do not participate in this comparison. This is why it is important to distinguish between "present in metadata" and "participating in identification." [Meter.Id 1.13.0 source](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/Meter.java).

| Name and tags | Identity relationship |
| --- | --- |
| `shop.orders{channel=web,result=success}` and the same tag pairs written in reverse order | Same identity |
| `shop.orders{channel=web,result=success}` and `shop.orders{channel=web,result=failure}` | Different identity |
| `shop.orders{channel=web}` and `shop.orders{channel=web,result=success}` | Different identity |
| Same name and tags, changing only description/unit | Does not create a new identity |

Tags are key-value pairs, not a positional list. Give each key a single clear value; do not repeat keys to express multiple values simultaneously.

**Type not being in `equals()` does not mean you can register a Counter and a Timer with the same ID.** The registry validates the registered meter type and can throw `IllegalArgumentException` when re-registering with an incompatible type. To measure order duration, use a separate name expressing duration instead of trying to change the type of an existing counter.

### 3.3. Ids are immutable

Methods such as `withName(...)` and `withTag(...)` return a new ID object; they do not modify an already registered meter:

```java
Meter.Id original = completed.getId();
Meter.Id renamed = original.withName("shop.orders.renamed");

// original still carries the name shop.orders.
// completed is not renamed in the registry.
// renamed is only a new ID, not yet registered to any meter.
```

Do not call `getId().withName(...)` and expect the old metric to be renamed on the endpoint or dashboard. If a name needs to change, design and register a new meter, along with an appropriate migration path for data and queries.

## 4. MeterRegistry: where meters are created, held, and looked up

`MeterRegistry` is the abstraction that organizes meters within a specific scope. It provides convenience methods such as `counter(...)`, `timer(...)`, `gauge(...)`, search APIs, and configuration. The actual meter object is created according to the registry type and its configuration rules.

```text
Name + tags + measurement type
        |
        v
MeterRegistry: apply configuration / find or create meter
        |
        v
Return Counter / Timer / Gauge for application code to use
```

### 4.1. Registering does not always create a new object

Within the same registry, re-registering a meter with the same name, tags, and compatible type usually returns the existing meter. For example, two components both fetching the counter `shop.orders{channel=web,result=success}` are writing to the same measurement instrument in that registry.

This prevents accidentally creating multiple independent counters for the same measurement. However, re-registering to "update" a description, unit, or configuration is not a safe configuration approach: an existing meter usually keeps using the configuration and metadata applied when it was created. Finalize configuration before registering.

A registry can also apply `MeterFilter` instances to rename meters, add/strip tags, or deny a meter. Two input IDs that look different can collapse into the same ID after mapping; a denied meter may return a no-op object that does not record data. Do not treat holding a `Counter` variable as proof that the metric is definitely being exported. [Registration, type checking, and ID mapping in MeterRegistry 1.13.0](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/MeterRegistry.java).

### 4.2. A registry is a state boundary

Two separate registries can hold two counters with equal IDs while maintaining independent state. Incrementing a counter in registry A does not automatically increment the counter with the same ID in registry B. Equal IDs do not prove two Java objects are identical or that two metric stores are synchronized.

This is a common mistake when an application manually calls `new SimpleMeterRegistry()` inside a service while Actuator is reading the Spring-managed registry. The service increments its count, but it increments it in a different registry, so the endpoint never sees that data.

### 4.3. Searching and listing

```java
Counter optional = registry.find("shop.orders")
    .tags("channel", "web", "result", "success")
    .counter();

if (optional != null) {
    System.out.println(optional.count());
}

Counter required = registry.get("shop.orders")
    .tags("channel", "web", "result", "success")
    .counter();

int meterCount = registry.getMeters().size();
```

These are illustrative snippets inside a component that already has `registry`. `find(...).counter()` allows a missing result and returns `null`. `get(...).counter()` requires finding a matching counter and throws an exception if none exists. These search APIs do not register a new meter the way `registry.counter(...)` does.

When searching by name alone, multiple tag combinations may match; do not interpret a single found result as the sum of all meters with that name. To verify a specific series, specify all required dimensions.

### 4.4. SimpleMeterRegistry does not automatically export data externally

`SimpleMeterRegistry` keeps values in memory and is suitable for experimentation or testing. It does not automatically send metrics to Prometheus, Datadog, or a historical store. Specialized registries add the corresponding export mechanism; some systems receive periodically pushed data, while others scrape data from the application.

The registry manages measurement instruments and state for instrumentation; the monitoring system is typically responsible for storing history, time-based queries, dashboards, and alerts. Do not use an in-process in-memory counter as a substitute for business data requiring durability.

## 5. CompositeMeterRegistry: fanning out a write to multiple registries

`CompositeMeterRegistry` is itself a `MeterRegistry`. Business code can accept it via the `MeterRegistry` type, register counters/timers normally, and the composite registry attaches corresponding meters to its child registries.

```text
Business code
  Counter obtained from CompositeMeterRegistry
           |
           | increment()
           +--> Counter in registry A --> monitoring system A
           |
           +--> Counter in registry B --> monitoring system B
```

The application writes once to the composite; each attached child registry receives that write. This is how multiple monitoring destinations are supported without forcing every service to know about each specific system.

### 5.1. It is not the sum of its child registries

In Micrometer 1.13.0, `CompositeCounter.increment(amount)` invokes the child counters, whereas `count()` **reads from a single child counter**; if there are no children yet, it reads from a no-op object returning 0. It does not sum the children. [CompositeCounter 1.13.0 source](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/composite/CompositeCounter.java).

If A and B both record 5 orders, those are two destinations receiving the same 5 orders, not 10 orders. Therefore, summing the counts of the children to get a "composite total" double-counts. Also do not rely on registry addition order to guess which child `count()` selects; which child is chosen for reading is not a business aggregation policy.

In the following example, the two children are intentionally attached at different times so they have different counts. When checking data forwarding, read each child registry individually; a value read through the composite is not a status report of all children.

### 5.2. Without child registries, writes are not buffered for replay

You can create a counter in a composite before adding child registries. That counter is a valid instrument at the API level, but increments performed while no children exist do not form a pending queue. When a child is added later, Micrometer registers the corresponding meter on the new child; it does not replay increments that happened before attachment.

Even when A has already recorded data, adding B later does not copy A's existing count over to B. That is why registry wiring should be completed before real recording begins. [Composite registry behavior in Micrometer docs](https://docs.micrometer.io/micrometer/reference/concepts/registry.html).

### 5.3. Writing directly to a child registry does not flow back up to the composite

If code obtains A's counter directly and increments it, B does not automatically receive that increment. The composite only distributes operations invoked through meters belonging to the composite; it does not watch every change in each child for bidirectional synchronization.

Removing A via `composite.remove(a)` stops forwarding subsequent writes to A; it does not mean data already sent to monitoring system A is deleted. Child registries also have their own lifecycles. In a Spring application, let the lifecycle manager close registries; business services do not close shared registries themselves.

A composite is also not a durable store, an offline buffer during network outages, or a cross-instance metric aggregator. Network transmission and error handling depend on the specific registry/exporter.

## 6. Standalone Java program for verification

The example uses two `SimpleMeterRegistry` instances as two in-memory destinations. They let you observe the exact mechanism without starting Spring, an HTTP server, or an external monitoring system.

Create a Gradle Java project with a wrapper and JDK 17 available. Structure:

```text
meter-roles-demo/
  build.gradle
  settings.gradle
  gradlew / gradlew.bat and gradle/wrapper/
  src/main/java/MeterRolesDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'meter-roles-demo'
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
    mainClass = 'MeterRolesDemo'
}
```

`src/main/java/MeterRolesDemo.java`:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.Tags;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.composite.CompositeMeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public class MeterRolesDemo {

    public static void main(String[] args) {
        identityAndRegistry();
        compositeRouting();
    }

    private static void identityAndRegistry() {
        SimpleMeterRegistry local = new SimpleMeterRegistry();
        SimpleMeterRegistry isolated = new SimpleMeterRegistry();
        try {

            Counter first = Counter.builder("shop.orders")
                .tags("channel", "web", "result", "success")
                .description("Completed orders")
                .baseUnit("orders")
                .register(local);

            Counter again = Counter.builder("shop.orders")
                .tags("result", "success", "channel", "web")
                .description("Another description")
                .register(local);

            Counter failed = local.counter(
                "shop.orders", "channel", "web", "result", "failure");

            first.increment(2);
            again.increment();
            failed.increment();

            Meter meter = first;
            Meter.Id id = meter.getId();
            Meter.Id metadataOnly = new Meter.Id(
                id.getName(), Tags.of(id.getTags()),
                "requests", "Different metadata", Meter.Type.TIMER);
            Meter.Id renamed = id.withName("shop.orders.renamed");

            System.out.println("sameInstance=" + (first == again));
            System.out.println("type=" + id.getType());
            System.out.println("channel=" + id.getTag("channel"));
            System.out.println("successCount=" + first.count());
            System.out.println("failureCount=" + failed.count());
            System.out.println("localMeters=" + local.getMeters().size());
            System.out.println("differentTagsSameId="
                + id.equals(failed.getId()));
            System.out.println("metadataOnlySameId=" + id.equals(metadataOnly));
            System.out.println("originalName=" + id.getName());
            System.out.println("derivedName=" + renamed.getName());
            System.out.println("originalDescription=" + id.getDescription());

            for (var measurement : meter.measure()) {
                System.out.println("measurement="
                    + measurement.getStatistic() + ":" + measurement.getValue());
            }

            Counter other = Counter.builder("shop.orders")
                .tags("channel", "web", "result", "success")
                .register(isolated);
            other.increment(7);
            System.out.println("acrossRegistriesSameId="
                + id.equals(other.getId()));
            System.out.println("acrossRegistriesSameObject=" + (first == other));
            System.out.println("isolatedCount=" + other.count());
            System.out.println("localStill=" + first.count());

            boolean typeConflict = false;
            try {
                Timer.builder("shop.orders")
                    .tags("channel", "web", "result", "success")
                    .register(local);
            }
            catch (IllegalArgumentException exception) {
                typeConflict = true;
            }
            System.out.println("typeConflict=" + typeConflict);
        }
        finally {
            isolated.close();
            local.close();
        }
    }

    private static void compositeRouting() {
        CompositeMeterRegistry composite = new CompositeMeterRegistry();
        SimpleMeterRegistry a = new SimpleMeterRegistry();
        SimpleMeterRegistry b = new SimpleMeterRegistry();
        try {

            Counter jobs = composite.counter("batch.jobs", "queue", "daily");
            jobs.increment(5);
            System.out.println("emptyCompositeCount=" + jobs.count());

            composite.add(a);
            jobs.increment(2);
            System.out.println("aAfterAttach=" + a.get("batch.jobs").counter().count());

            composite.add(b);
            System.out.println("bAtAttach=" + b.get("batch.jobs").counter().count());

            jobs.increment(3);
            double countA = a.get("batch.jobs").counter().count();
            double countB = b.get("batch.jobs").counter().count();
            double view = jobs.count();
            System.out.println("aAfterFanout=" + countA);
            System.out.println("bAfterFanout=" + countB);
            System.out.println("compositeReadsOneChild="
                + (view == countA || view == countB));
            System.out.println("compositeReadsSum=" + (view == countA + countB));
            System.out.println("logicalMeters=" + composite.getMeters().size());
            System.out.println("childRegistries=" + composite.getRegistries().size());

            composite.remove(a);
            jobs.increment();
            System.out.println("aAfterDetach=" + a.get("batch.jobs").counter().count());
            System.out.println("bAfterDetach=" + b.get("batch.jobs").counter().count());
        }
        finally {
            composite.close();
            a.close();
            b.close();
        }
    }
}
```

Run from the project directory; Gradle compiles the Java code and executes `main`:

```bash
./gradlew -q run --console=plain
```

On Windows PowerShell use `.\gradlew.bat -q run --console=plain`. Program output:

```text
sameInstance=true
type=COUNTER
channel=web
successCount=3.0
failureCount=1.0
localMeters=2
differentTagsSameId=false
metadataOnlySameId=true
originalName=shop.orders
derivedName=shop.orders.renamed
originalDescription=Completed orders
measurement=COUNT:3.0
acrossRegistriesSameId=true
acrossRegistriesSameObject=false
isolatedCount=7.0
localStill=3.0
typeConflict=true
emptyCompositeCount=0.0
aAfterAttach=2.0
bAtAttach=0.0
aAfterFanout=5.0
bAfterFanout=3.0
compositeReadsOneChild=true
compositeReadsSum=false
logicalMeters=1
childRegistries=2
aAfterDetach=5.0
bAfterDetach=4.0
```

The example requires the Micrometer library and its dependencies resolved by Gradle; do not compile with a bare `javac` command missing a classpath. If invoking `javac`/`java` manually, include the resolved runtime JARs on the classpath for both compilation and execution; the classpath separator on Windows is `;`, and on Linux/macOS is `:`.

### 6.1. Explaining the identity and registry section

`sameInstance=true` confirms that re-registering a counter with the same name/tags in `local` returns the existing object. Reversing the order of the two tag pairs does not create a different identity. Because `first` and `again` point to the same counter, incrementing by 2 via the first variable and then by 1 via the second yields 3.

`failureCount=1.0` belongs to a different counter because `result=failure`. Hence `localMeters=2`, even though both share the name `shop.orders`. `metadataOnlySameId=true` only verifies the ID comparison rule: the `metadataOnly` object was not used to register a timer. Attempting to register a timer afterward leads to `typeConflict=true`, showing the registry still enforces type compatibility.

`originalDescription=Completed orders` shows that re-registering with a different description does not overwrite the existing description in this scenario. `derivedName` is a newly created ID, while `originalName` remains unchanged. No meter with the new name was registered merely by calling `withName()`.

`acrossRegistriesSameId=true` goes together with `acrossRegistriesSameObject=false` and the two values 3 and 7. Having identical IDs across two registries does not mean sharing a counter.

### 6.2. Explaining the composite section step by step

| Point in time | Action | A | B | Takeaway |
| --- | --- | --- | --- | --- |
| No children attached | `jobs.increment(5)` | No meter yet | No meter yet | Composite does not buffer 5 for replay |
| Attach A, then add 2 | `add(a)` and `increment(2)` | 2 | No meter yet | A only receives operations from when it was attached |
| Attach B | `add(b)` | 2 | 0 | B does not copy the 2 from A |
| Add 3 more via composite | `increment(3)` | 5 | 3 | Both children receive the same new write |
| Remove A, add 1 more | `remove(a)` and `increment()` | 5 | 4 | A no longer receives new writes |

`logicalMeters=1` is one logical meter in the composite, whereas `childRegistries=2` is the number of child registries at the time of printing. Do not multiply or combine these child counts as the number of business events.

The program only prints `compositeReadsOneChild=true` and `compositeReadsSum=false`, avoiding locking the output to an unguaranteed child choice. How each destination holds data is verified directly via `a.get(...).counter().count()` and `b.get(...).counter().count()`.

## 7. Applying this in Spring Boot Actuator

In a Boot application, inject the Spring-managed `MeterRegistry` into the component that needs instrumentation. Do not instantiate a new registry inside individual services, and do not cast the registry to `SimpleMeterRegistry` or `CompositeMeterRegistry` just to record a normal counter.

Example of a business component inside a Boot project that already has Actuator and Micrometer:

```java
package example.metrics;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class CheckoutMetrics {
    private final Counter success;
    private final Counter failure;

    public CheckoutMetrics(MeterRegistry registry) {
        this.success = Counter.builder("app.checkout.completed")
            .tag("result", "success")
            .description("Completed checkout attempts")
            .register(registry);
        this.failure = Counter.builder("app.checkout.completed")
            .tag("result", "failure")
            .description("Completed checkout attempts")
            .register(registry);
    }

    public void recordCompletion(boolean successful) {
        (successful ? success : failure).increment();
    }
}
```

This is an integrated component, not a standalone program with `main`. Code calls `recordCompletion(...)` once at the defined completion point for each checkout attempt. The two counters are registered once in the constructor and stored in fields; you do not create a registry or configure an exporter on every transaction.

To add common tags before meters are registered, you can provide a configuration class:

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
        return registry -> registry.config()
            .commonTags("application", "checkout");
    }
}
```

Do not add common tags after services have already registered meters and expect all old IDs to be rewritten automatically. Registry configuration, filters, and common dimensions should be finalized before recording begins.

### 7.1. Do not hard-depend on the injected registry class

Boot's overview documentation describes auto-configuring a composite registry for monitoring systems on the classpath. When reading the **Boot 3.3.0** implementation, note the more specific condition: the composite configuration applies when registries exist but there is no single candidate to inject; a single registry or a `@Primary` candidate can be used directly. Therefore, you cannot assert that every injected `MeterRegistry` bean is a `CompositeMeterRegistry`.

This is where the overview description is simplified compared to the conditions in code. The stable choice for a service is depending on `MeterRegistry`; when diagnosing, inspect the actual beans and auto-configuration conditions. [Boot 3.3 Metrics overview](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html), [CompositeMeterRegistryConfiguration 3.3.0 conditions](https://github.com/spring-projects/spring-boot/blob/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/CompositeMeterRegistryConfiguration.java).

### 7.2. Distinguishing the application registry, global registry, and endpoint

`Metrics.globalRegistry` is a static composite provided by Micrometer; static methods like `Metrics.counter(...)` use it. It is not object-identical to every registry injected by Spring. Boot has a mechanism to add auto-configured registries to the global registry according to the `management.metrics.use-global-registry` property; that connection can be disabled when an application needs static state isolation.

In Spring application code, injecting the registry usually makes ownership and testing clearer. In tests, a shared static registry can also retain meters from previous test runs if lifecycles are not managed. Do not manually add a registry to global or composite just because values are not showing up: confirm where writes are going first.

The `/actuator/metrics` endpoint is a way to diagnose measurements over HTTP when enabled, exposed, and the caller has proper authorization. It is not a `MeterRegistry`, and exposing this endpoint does not turn `SimpleMeterRegistry` into an exporter. Exporting to a target system depends on the corresponding registry and that system's configuration.

A name declared in a form like `app.checkout.completed` is a Micrometer name. Registries/exporters may translate names to the monitoring system's conventions, add suffixes, or convert units. When looking up in the registry, distinguish the canonical name in the application from the exported name in the target system.

## 8. Designing names and tags so the registry remains manageable

Names should describe the measured phenomenon; tags should describe finite dimensions useful for querying. For instance, `result=success|failure` and `channel=web|mobile` yield a small, understandable number of identity combinations.

Avoid putting order IDs, user IDs, UUIDs, timestamps, or raw URLs containing IDs into tags. Each new value combination increases the number of meters and potential exported time series. With 2 channels × 3 results × 4 regions, there are at most 24 combinations for that meter name if all appear; adding one million order IDs can make the identity space grow enormously.

24 is the number of name/tag combinations in the example, excluding the fact that one meter type can produce multiple time series, infrastructure tags, or separate instances. Therefore, counting `getMeters().size()` is not enough to predict the full cost in the monitoring system.

With a composite, an unbounded tag design is forwarded to multiple child registries and can multiply costs across destinations. A composite does not sanitize tags, reduce cardinality, or make sensitive data safe.

Common tags, filters, and naming conventions can differ across child registries, so the ID in each child after mapping may not match character-for-character with the logical ID in the composite. When diagnosing, inspect the actual ID in the exact registry and the actual exported data; do not look only at Java variable names.

## 9. Common misconceptions

| Misconception | Accurate understanding to use |
| --- | --- |
| A `Meter` is a single number | It is an instrument providing a set of measurements; number of statistics depends on type |
| `Meter.Id` holds the current count | The ID holds name/tags/metadata, not the counter value |
| Changing description creates a new meter | Identity is based on name and tags; changing metadata does not split identity |
| Equal IDs mean the same object everywhere | Meter reuse is scoped to a registry; two registries can hold independent state |
| Counter and Timer can share an ID because `equals` ignores type | The registry also checks type and can reject registration |
| `withName()` renames an already registered meter | It creates a new ID without altering the old meter |
| `SimpleMeterRegistry` pushes data over the network automatically | It holds values in memory without auto-exporting to other systems |
| A composite buffers metrics to backfill when adding a child | Writes before a child is attached are not replayed |
| `CompositeCounter.count()` is the sum of children | In the illustrated version, it reads one child; it does not sum children |
| Increment both the composite and each child to be sure data arrives | Can double-record; business code should use exactly one chosen write path |
| Creating a new registry makes Actuator see the metric automatically | An unmanaged registry does not automatically become Actuator's data source |
| One meter corresponds to exactly one time series | Meter type and exporter determine how many statistics/series are exported |

When metrics do not match expectations, check in order: **is it the right registry → what are the final name and tags → does the matching meter exist → does the composite have children → which child is being read → is the exporter configured**. These are distinct boundaries and require separate evidence.

## 10. Self-check

1. Register two counters with the same name/tags but reversed tag order in the same `SimpleMeterRegistry`. Predict the `==` relation and the result if incremented through both variables.
2. Keep the name, change `result=success` to `result=failure`. Explain why there is a different meter, then distinguish the number of meters from the number of time series in the target system.
3. Create two independent registries with counters sharing the same ID. Increment only in the first registry; explain why the IDs are equal yet the values differ.
4. Increment a counter in a composite before adding a child. Predict the new child's value and explain why no backfilling occurs.
5. Attach child A, record 2; attach child B, record 3. State each child's value and why composite `count()` must not be interpreted as a sum.
6. In a Boot application, a service counts metrics but Actuator does not see them. Check the service's registry source before modifying HTTP permissions or installing another monitoring system.
7. Explain why a service only needs to accept `MeterRegistry`, whereas infrastructure configuration is what cares about which registry exports to which system.

When reading a line `counter.increment()`, the learner should be able to identify all four elements: which instrument is writing, which ID receives the data, which registry owns it, and whether any composite is fanning out the write to child registries.
