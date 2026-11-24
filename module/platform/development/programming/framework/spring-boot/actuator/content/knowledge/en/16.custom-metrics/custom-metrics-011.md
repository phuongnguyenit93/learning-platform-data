# Controlling Meter Registration in Loops and Releasing Unneeded Meters

## 1. Two Questions That Must Be Separated

A service processes thousands of tasks per minute. On each task, it must increment the count of succeeded or failed tasks. At the same time, some processing pools may be created and stopped while the application is running.

In this situation, there are two distinct problems:

1. **Registration and recording:** is it necessary to look up or create a meter on every loop iteration?
2. **Lifecycle:** when a measurement source genuinely ceases to exist, who removes the corresponding meter?

In Micrometer, a `Meter` is a measurement object such as Counter, Gauge, or Timer. `MeterRegistry` manages registered meters; business code uses those objects to record events or read state.

A sound design keeps the number of meter identities stable even as event counts grow very large. Processing another million tasks should not automatically create another million meter IDs.

This lesson uses two scenarios: a Counter set with a finite outcome set for recording inside a loop, and a Gauge with an explicit lifecycle-management component when its source is replaced.

## 2. Repeated Registration with the Same Identity Does Not Create a New Meter

A meter identity is distinguished primarily by **name and tag set**. Global settings or MeterFilters can transform names/tags before the registry uses that identity.

In a fresh registry with no special filters, the snippet below reuses a single Counter:

```java
Counter first = registry.counter(
        "demo.loop.events", "outcome", "success");

for (int i = 0; i < 1_000; i++) {
    registry.counter("demo.loop.events", "outcome", "success")
            .increment();
}

Counter again = registry.counter(
        "demo.loop.events", "outcome", "success");
```

Same name and tags, same Counter type, and no intervening removal: `first` and `again` point to the same Counter. After this loop, the Counter has value `1000.0` in `SimpleMeterRegistry`.

Therefore, the claim “putting register inside a loop always creates a new meter each iteration” is false. However, each call still goes through meter building/lookup code; creating builders, strings, and tags on every event adds allocation, normalization, and lookup overhead.

When the identity set is known upfront, register once and retain references for recording. There is no need to place registry lookups on hot processing paths. Exact performance gains must be measured in your application rather than inferred as a fixed ratio.

[Micrometer 1.13.0's MeterRegistry source](https://raw.githubusercontent.com/micrometer-metrics/micrometer/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/MeterRegistry.java) shows the registry looks up an existing meter before creating a new one.

### What Re-registering Does Not Solve

- Passing a new source object to a Gauge with the same name/tags does not switch the existing Gauge to the new source.
- Changing description on a later registration should not be used to update configuration of an existing meter.
- Registering a different type, such as a Gauge under the same name/tags as an existing Counter, can trigger a type-conflict error; meter type is not a way to create separate identities for the same name/tags.
- Changing tags on every event changes the problem: the registry may end up managing many distinct meters.

The short snippets in this lesson assume an existing `registry` variable and appropriate imports. The complete runnable program is in Section 7.

## 3. Changing Tags Inside Loops Is the Real Source of Identity Growth

Example to avoid in production serving code:

```java
for (String requestId : requestIds) {
    registry.counter("demo.request.events", "request.id", requestId)
            .increment();
}
```

If every request has a new ID, each ID creates a new name/tag combination. Embedding the request ID into the metric name, such as concatenating into `demo.request.events.<id>`, causes the exact same problem.

**Cardinality** in this context is the number of label combinations producing distinct metric series. A label key with very many values can increase application memory usage, export overhead, and storage volume in the monitoring system.

Suppose a meter has three labels with 2, 3, and 4 allowed values respectively. If every combination occurs, there can be `2 × 3 × 4 = 24` identities for that name. The count does not depend on each label in isolation.

Meter count in the registry also does not always equal exported series count externally. A Timer can emit multiple statistics, and histogram configuration can produce many additional series per tag combination.

| Need | Sensible representation |
| --- | --- |
| Count tasks by outcome | Tag with finite value set such as `success`, `failure` |
| Compare preconfigured worker pools | Pool name tag from a controlled list |
| Look up a specific request | Logs or traces carrying that identifier |
| Track URLs | Use route templates or bounded value groups matching observation intent |
| Track transient individual objects | Consider aggregate measurements over a stable source |

Do not try to solve this by putting all request IDs into a `ConcurrentHashMap<String, Counter>`. A thread-safe map can still grow unbounded.

Even a bounded cache is not enough: evicting a Counter from an application cache does not automatically remove the Counter from the registry. Conversely, removing from the registry while a cache still holds the old object can leave code writing into a meter that is no longer registered.

See also [Micrometer's naming and tag value conventions](https://docs.micrometer.io/micrometer/reference/1.13/concepts/naming.html).

## 4. Separating Registration from Recording Loops

If there are only two processing outcomes, initialize both Counters upfront and select by enum. The identity set is governed by the business contract rather than arbitrary input strings.

File `src/example/lifecycle/OutcomeCounters.java`:

```java
package example.lifecycle;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

import java.util.EnumMap;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;

public final class OutcomeCounters {

    public enum Outcome {
        SUCCESS, FAILURE
    }

    private final Map<Outcome, Counter> counters =
            new EnumMap<>(Outcome.class);

    public OutcomeCounters(MeterRegistry registry) {
        Objects.requireNonNull(registry, "registry");

        for (Outcome outcome : Outcome.values()) {
            Counter counter = Counter.builder("demo.jobs.processed")
                    .tag("outcome", outcome.name().toLowerCase(Locale.ROOT))
                    .description("Number of completed tasks by outcome")
                    .register(registry);
            this.counters.put(outcome, counter);
        }
    }

    public void record(Outcome outcome) {
        this.counters.get(Objects.requireNonNull(outcome, "outcome"))
                .increment();
    }

    public double count(Outcome outcome) {
        return this.counters.get(Objects.requireNonNull(outcome, "outcome"))
                .count();
    }
}
```

The loop in the constructor runs over two enum constants. This is a **bounded, intentional registration loop**, completely different from a loop creating meters per request ID.

On the task-processing path, call `record` to increment the existing Counter. The map is populated only at construction and never mutated afterward. Under concurrent use, publish this component safely to threads, such as via a Spring bean; never turn the map into a place for adding dynamic labels after initialization.

Counters stay alive alongside the statistics component and are not removed after every task. Repeatedly removing and recreating Counters can drop unexported increments and introduce counter resets. Counter semantics and event-counting usage are presented in [Micrometer's Counter documentation](https://docs.micrometer.io/micrometer/reference/1.13/concepts/counters.html).

If you also need to time those exact events with a Timer, remember Timer already tracks recording count; add a separate Counter only when it answers a different meaningful question.

## 5. Removing a Meter Is a Lifecycle Change, Not Deleting a Java Variable

How to remove a registered meter:

```java
registry.remove(meter);
```

Store the object returned at registration so you pass the exact identity already processed by registry configuration. Manually constructing a new `Meter.Id` can omit common tags or filter transformations.

Distinguish three places holding state:

```text
Application
    -> map, field, listener, or callback holding the meter object

MeterRegistry
    -> registration entry and meter bindings

External monitoring system
    -> received metric samples and historical data
```

Removing from one place does not automatically delete from every place.

### 5.1. The Old Object Can Still Be Used by the Application

In `SimpleMeterRegistry`, after a Counter has been removed, a Java variable still holding that Counter can still call `increment()`. It does not re-register itself by doing so.

If you re-register the same name/tags, the new Counter starts with its own fresh state. Writing to the old Counter does not update the new Counter. Section 7's program demonstrates this.

Therefore, when removing a meter, simultaneously stop old recording paths and clear references inside the component's managed structures. Do not merely see `find(...)` return null and conclude every usage path has been cleaned up.

### 5.2. Removing a Meter Does Not Force GC to Reclaim the Source

For a Gauge, the measurement source may still be strongly held by a bean, map, or callback. Removing the Gauge does not force the source to vanish immediately. The reverse also matters: a Gauge source being reclaimed by GC does not prove the registration entry was cleaned up properly.

Do not use `System.gc()` as a meter-release procedure or as a mandatory test assertion. Managing registrations and reclaiming memory are two distinct mechanisms.

### 5.3. Exported Data Has Its Own Lifecycle

Calling `remove` does not send a command deleting all history to the monitoring system. Stored samples, staleness handling for stopped series, and data retention depend on the external system.

Removing a meter too early can also prevent a short-lived event from ever being seen by a scraper. There is no guarantee that removal flushes a “final sample.”

Consequently, creating many arbitrary tags and removing them right after each request remains a broken design, even if the concurrent number of meters appears low.

## 6. A Gauge-Managing Component That Closes Exactly Once

Suppose an application has an image-processing pool named `image`. We want a Gauge showing active task count. The pool-management component updates state and closes its metrics when the pool reaches end of life.

The example below manages only **the metric**. It does not stop an executor or wait for business tasks itself. Before closing, the coordinating component must ensure no threads still need to update the metric.

**Usage contract:** at any time, only one component manages the `demo.pool.active{pool=image}` identity in a registry. A new instance is created only after the old instance has finished closing; no other component removes or re-registers the same identity outside this workflow.

File `src/example/lifecycle/PoolActiveGauge.java`:

```java
package example.lifecycle;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;

import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

public final class PoolActiveGauge implements AutoCloseable {

    private final MeterRegistry registry;
    private final AtomicInteger active = new AtomicInteger();
    private final Gauge gauge;
    private boolean closed;

    public PoolActiveGauge(MeterRegistry registry, String poolName) {
        this.registry = Objects.requireNonNull(registry, "registry");

        String name = Objects.requireNonNull(poolName, "poolName").strip();
        if (name.isEmpty()) {
            throw new IllegalArgumentException("poolName must not be blank");
        }

        this.gauge = Gauge.builder(
                        "demo.pool.active", this.active, AtomicInteger::get)
                .tag("pool", name)
                .description("Number of active tasks in the processing pool")
                .register(this.registry);
    }

    public synchronized void setActive(int value) {
        if (this.closed) {
            throw new IllegalStateException("metrics already closed");
        }
        if (value < 0) {
            throw new IllegalArgumentException("active must not be negative");
        }
        this.active.set(value);
    }

    @Override
    public synchronized void close() {
        if (this.closed) {
            return;
        }
        this.closed = true;
        this.registry.remove(this.gauge);
    }
}
```

The `active` field holds the measurement source. This value must be updated by business logic to match the described quantity; Gauge does not infer task count from an executor it was never given.

`synchronized` coordinates `setActive` and `close`: once closed, updates through this component are rejected. `AtomicInteger` provides thread-safe reads for the Gauge reader function, which does not acquire the manager component's lock.

`close()` is **idempotent** within this object's scope: calling it again does not perform a new removal. Do not set the value to 0 and re-register to simulate closing.

### Why Can Uncontrolled Repeated close Calls Be Dangerous?

In Micrometer 1.13.0, `remove(Meter)` delegates to removing by meter ID. It does not compare and remove only if the exact Java object matches.

If an old instance was removed, a new instance reused the same ID, and a late cleanup callback still ran and called `remove`, it could remove the new instance's meter.

The `closed` flag in the example stops a second close on the old object itself from doing that. However, that flag cannot coordinate two independent manager objects; the single-owner-per-identity contract must still be upheld.

When multiple threads create and destroy processing pools, you need a lifecycle manager coordinating operations per key. Checking `find` sees empty and then calling `register` does not by itself form an atomic ownership guard.

## 7. Complete Program Verifying the Scenarios

File `src/example/lifecycle/MeterLifecycleDemo.java`, using the two classes from Sections 4 and 6:

```java
package example.lifecycle;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import java.util.ArrayList;
import java.util.List;

public final class MeterLifecycleDemo {

    public static void main(String[] args) {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();

        try {
            OutcomeCounters counters = new OutcomeCounters(registry);

            for (int i = 0; i < 6; i++) {
                OutcomeCounters.Outcome outcome = i % 3 == 0
                        ? OutcomeCounters.Outcome.FAILURE
                        : OutcomeCounters.Outcome.SUCCESS;
                counters.record(outcome);
            }

            System.out.println("outcome.meters="
                    + meterCount(registry, "demo.jobs.processed"));
            System.out.println("success="
                    + counters.count(OutcomeCounters.Outcome.SUCCESS));
            System.out.println("failure="
                    + counters.count(OutcomeCounters.Outcome.FAILURE));

            // Create only three IDs to illustrate a registration pattern to avoid.
            List<Meter> requestMeters = new ArrayList<>();
            for (int i = 1; i <= 3; i++) {
                Counter counter = registry.counter(
                        "demo.request.events", "request.id", "req-" + i);
                counter.increment();
                requestMeters.add(counter);
            }

            System.out.println("request-id.meters="
                    + meterCount(registry, "demo.request.events"));

            // Sequential experiment: no other threads are writing to these meters.
            for (Meter meter : requestMeters) {
                registry.remove(meter);
            }
            requestMeters.clear();

            System.out.println("request-id.meters-after-cleanup="
                    + meterCount(registry, "demo.request.events"));

            Counter oldCounter = registry.counter("demo.reused.events");
            oldCounter.increment(5);
            registry.remove(oldCounter);

            System.out.println("removed-counter-registered="
                    + (registry.find("demo.reused.events").counter() != null));

            oldCounter.increment();
            Counter newCounter = registry.counter("demo.reused.events");
            System.out.println("old-counter=" + oldCounter.count());
            System.out.println("new-counter=" + newCounter.count());

            PoolActiveGauge oldPool = new PoolActiveGauge(registry, "image");
            try {
                oldPool.setActive(2);
                System.out.println("active=" + poolValue(registry));
            } finally {
                oldPool.close();
            }

            System.out.println("pool-gauge-after-close="
                    + (registry.find("demo.pool.active")
                            .tag("pool", "image").gauge() != null));

            try (PoolActiveGauge replacement =
                         new PoolActiveGauge(registry, "image")) {
                replacement.setActive(1);
                System.out.println("replacement-active=" + poolValue(registry));

                oldPool.close();
                System.out.println("replacement-after-old-close="
                        + poolValue(registry));
            }
        } finally {
            registry.close();
        }
    }

    private static long meterCount(MeterRegistry registry, String name) {
        return registry.getMeters().stream()
                .filter(meter -> meter.getId().getName().equals(name))
                .count();
    }

    private static double poolValue(MeterRegistry registry) {
        return registry.get("demo.pool.active")
                .tag("pool", "image")
                .gauge()
                .value();
    }
}
```

The program intentionally creates three Counters tagged with request IDs to show entry count growing, then cleans them up in a bounded experiment. This part is not a pattern to put into real request-handling paths.

`getMeters` calls and lookups in the example serve verification. Do not put full-registry scans inside every task-processing iteration.

### Dependencies and Compile Commands

Create `pom.xml` in the root directory of the experiment:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>meter-lifecycle-demo</artifactId>
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

JDK 17+ and Maven are required. Downloading dependencies the first time requires Maven Central access. From the directory containing `pom.xml`, run in PowerShell:

```powershell
mvn -q org.apache.maven.plugins:maven-dependency-plugin:3.6.1:copy-dependencies -DoutputDirectory=lib
javac --release 17 -encoding UTF-8 -cp "lib/*" -d out src/example/lifecycle/OutcomeCounters.java src/example/lifecycle/PoolActiveGauge.java src/example/lifecycle/MeterLifecycleDemo.java
java -cp "out;lib/*" example.lifecycle.MeterLifecycleDemo
```

On Linux/macOS, use `:` in the classpath of the run command:

```bash
java -cp "out:lib/*" example.lifecycle.MeterLifecycleDemo
```

Stdout from the sequential run:

```text
outcome.meters=2
success=4.0
failure=2.0
request-id.meters=3
request-id.meters-after-cleanup=0
removed-counter-registered=false
old-counter=6.0
new-counter=0.0
active=2.0
pool-gauge-after-close=false
replacement-active=1.0
replacement-after-old-close=1.0
```

The outputs prove:

- Six events used only two outcome Counters.
- Three request ID values created three registration entries; cleanup removed those entries from the registry in the experiment.
- The old Counter still held in a variable incremented to 6, while the newly registered Counter started at 0.
- The old pool's Gauge was removed.
- Closing the old object again did not remove the replacement instance's Gauge, thanks to once-only close control.

In Micrometer 1.13.0, the registry has `close()` without implementing `AutoCloseable`, so the program closes the registry in `finally`. `PoolActiveGauge` implements `AutoCloseable` itself so it works with try-with-resources.

## 8. Applying in Spring Boot Actuator

In a Boot 3.3 application with Actuator and metrics auto-configuration active, inject the Spring-managed `MeterRegistry`. Keep `OutcomeCounters` as a bean living alongside the application so services use it when completing tasks.

Example configuration reusing the two classes above:

```java
package example.lifecycle;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.config.MeterFilter;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MetricsConfiguration {

    @Bean
    public OutcomeCounters outcomeCounters(MeterRegistry registry) {
        return new OutcomeCounters(registry);
    }

    @Bean(destroyMethod = "close")
    public PoolActiveGauge imagePoolMetrics(MeterRegistry registry) {
        return new PoolActiveGauge(registry, "image");
    }

    @Bean
    public MeterFilter poolTagLimit() {
        return MeterFilter.maximumAllowableTags(
                "demo.pool.", "pool", 8, MeterFilter.deny());
    }
}
```

This is configuration for an existing Boot application, not a standalone application. The package must be within scan scope or imported. In that application, let Boot's dependency management choose the compatible Micrometer version.

The Gauge bean in this configuration has its lifecycle tied to the context. If processing pools are dynamic objects created/destroyed at runtime, a fixed singleton bean does not replace a per-pool lifecycle manager.

The tag limit is an additional safeguard. In the example, it applies to the `pool` key of names starting with `demo.pool.`. When a new value exceeds the limit, the filter can cause that registration call to return a no-op (NOOP) meter. Receiving a returned object does not by itself prove the meter was successfully registered and exported.

Configure filters before related meters via Boot's configuration mechanisms, as guided by [the metrics documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html). Do not add a filter late assuming it will automatically clean up all existing meters.

This limit also does not turn arbitrary tag values into a sound design. In Micrometer 1.13.0's implementation, the filter remembers previously seen values; removing a meter does not automatically return a “tag slot” like a TTL cache. Details are in [MeterFilter.maximumAllowableTags](https://raw.githubusercontent.com/micrometer-metrics/micrometer/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/config/MeterFilter.java).

To group multiple meters into a shared bundle, you can use MeterBinder to organize registration. Doing so does not automatically provide unbind for dynamic sources; source ownership and meter removal responsibilities still need to be defined.

## 9. Release Procedure in a Multithreaded System

A typical procedure for a dynamic source is:

```text
Active
    -> Stop accepting new work using the old source
    -> Wait for / coordinate in-flight recording paths per business contract
    -> Remove the exact meters managed by the component
    -> Clear references in application maps, listeners, callbacks, or caches
    -> End lifecycle
```

Depending on the business source, the order of stopping resources and removing meters may need adjustment so the shutdown phase remains observable. What must hold is that no old path keeps writing into a replaced meter, and no old cleanup path removes the new version's meter.

If a component registers multiple meters, store a list of meters belonging to that component and clean up from that list. Also handle partial registration followed by an error during initialization. Do not run overly broad name scans guessing which meters belong to you.

When using a composite registry, manage registration and removal through the original registry while checking actual export configuration. Never remove arbitrarily from a child registry assuming everywhere else was cleaned up.

| Operation | Scope to understand |
| --- | --- |
| `registry.remove(meter)` | Removes the matching identity from the target registry |
| Clearing a variable or deleting an entry from a private cache | Drops one application reference path; does not replace registry removal |
| `registry.clear()` | Removes every meter in the registry; unsuitable for cleaning up one group |
| `registry.close()` | Ends the lifecycle of the entire registry and related exporting; do not use to clean up one meter in a shared registry |

Do not schedule a periodic task calling `clear()` to “prevent leaks” in an application. It can wipe out JVM/HTTP metrics and other measurements while live components still hold old references.

A source created and destroyed repeatedly must be tested across multiple cycles. The registry returning to the expected entry count is useful evidence, yet not sufficient to prove no listeners, background threads, or application references remain.

## 10. Diagnostics and Practice Exercises

| Symptom | What to check |
| --- | --- |
| Meter count grows nearly linearly with task count | Do tags or names contain per-task changing IDs? |
| Meter count is stable yet heavy allocation occurs in loops | Are builders/tags recreated or registry lookups called on every event? |
| Counter after replacement does not increment as expected | Does business flow hold the old Counter or the new Counter? |
| New source's Gauge still reads the old number | Was the same identity re-registered before removing the old source? |
| Removed yet memory does not drop | Are caches, callbacks, beans, or sources still holding references? Or are you only seeing GC timing variance? |
| Removed yet backend still retains history | Are you confusing registry state with external data retention policy? |
| New Gauge vanishes after an old close callback | Are identity ownership and cleanup idempotency guaranteed? |
| Metrics for a new tag are missing | Is a filter limiting or denying registration? |

Practice:

1. Run the three classes in Sections 4, 6, and 7 and verify all 12 lines of stdout.
2. Run Section 2's snippet separately on a fresh registry and confirm 1,000 recordings still use one Counter with the same identity.
3. Increase events recorded via `OutcomeCounters` while keeping two enum constants. Counter count remains two; their values grow with event count.
4. Loop 100 cycles of creating `PoolActiveGauge`, updating, closing, and recreating with the same name sequentially. After each close, the corresponding Gauge must be absent from the registry; shared Counters remain intact.
5. Try calling `setActive` after `close` and verify the state error. Never continue using a closed component.
6. In a separate test registry, configure a limit of two tag values and then try a third value. Check registry lookup results as well, not just whether the registration call returns an object.
7. Audit one loop in your application: identify the maximum name/tag set, where meter references are held, and lifecycle termination conditions. If a dynamic cache exists, align cache policy with registry policy.

The goal is keeping meters stable per observed quantity, recording events through appropriate references, and removing meters according to the real lifecycle of the source.
