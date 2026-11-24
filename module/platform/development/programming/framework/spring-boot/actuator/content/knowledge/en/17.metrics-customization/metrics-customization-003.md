# Filtering, Renaming, or Denying Meters with MeterFilter

## 1. Why Is a Policy Layer Needed for Measurements?

A Spring Boot application can receive measurements from many places: business code, libraries, the JVM, and components auto-configured by Actuator. These sources do not necessarily follow a single naming and labeling convention.

Suppose order processing currently registers:

```text
legacy.orders.processed
    result=success
    request.id=req-101
```

The operations team wants to:

- Use the `shop.orders.` prefix to standardize names.
- Rename the `result` tag key to `outcome`.
- Remove `request.id` from this metric group so it does not split a separate series for each request.
- Avoid registering diagnostic metrics starting with `shop.orders.internal.`.

**MeterFilter is the mechanism for applying policies when meters are registered into a MeterRegistry.** It can transform identifiers or decide whether to accept/deny registration.

MeterFilter does not replace event-recording code. Business code must still call `increment`, `record`, or provide an appropriate reading source. The filter decides under what identifier that measurement enters the registry and whether it is registered at all.

In this lesson, `Meter` refers to a measurement instrument such as Counter, Gauge, or Timer; `Meter.Id` holds the identifier and associated metadata. The name together with the tag set is key to distinguishing measurements.

## 2. Three Extension Points of MeterFilter

| Method | Role |
| --- | --- |
| `map(Meter.Id)` | Returns the transformed identifier: name, tags, or appropriate metadata |
| `accept(Meter.Id)` | Decides to accept, deny, or defer to the next filter |
| `configure(Meter.Id, DistributionStatisticConfig)` | Customizes distribution configuration for types such as Timer and DistributionSummary |

These methods have default implementations, so a filter only needs to override the part it uses. For example, renaming usually only needs `map`; a denial rule usually only needs `accept`.

`configure` serves policies such as histogram or percentile configuration. When extending it, intentionally merge the new configuration with the existing configuration rather than accidentally erasing settings from the builder or other filters.

The scope of impact is the registry to which the filter is attached. If an application uses multiple independent registries, do not assume configuring one place automatically takes effect in all the others.

[Micrometer 1.13 Meter Filters documentation](https://docs.micrometer.io/micrometer/reference/1.13/concepts/meter-filters.html) presents these three roles and their corresponding utility methods.

### Filters Do Not Run on Each Increment

An already-registered Counter is held in a variable and incremented many times. MeterFilter is not invoked as an event filter before each increment.

Therefore, do not write `map` to read the current request from `ThreadLocal`, add random IDs, or fetch data from a network service. Mapping should be deterministic based on the input identifier and stable application configuration.

Tags that depend on a specific event must be designed at the appropriate recording site, with a controlled set of values. MeterFilter is not a substitute for that design.

## 3. Understanding NEUTRAL, ACCEPT, and DENY Correctly

The `accept` method returns one of three values of `MeterFilterReply`:

| Value | Meaning in the Decision Chain |
| --- | --- |
| `NEUTRAL` | Undecided; continue evaluating subsequent filters |
| `ACCEPT` | Accept; do not ask remaining `accept` methods |
| `DENY` | Deny; do not ask remaining `accept` methods |

If no filter makes an accept or deny decision, the meter is allowed to register.

This has two easily misunderstood consequences.

**NEUTRAL does not mean deny.** A filter that does not care about the current name can return NEUTRAL, allowing other rules to continue processing.

**ACCEPT is not just "I don't forbid it".** It decides the outcome immediately in the accept/deny chain. An overly broad ACCEPT rule can bypass subsequent deny rules or tag limits.

### Example of Wrong Ordering When Trying to Block Internal Metrics

The short snippets below assume a `registry` variable already exists:

```java
registry.config()
        .meterFilter(MeterFilter.acceptNameStartsWith("shop."))
        .meterFilter(MeterFilter.denyNameStartsWith("shop.orders.internal."));
```

A meter named `shop.orders.internal.debug` matches the first rule and receives ACCEPT. The subsequent deny rule is never asked.

If you want the deny exception to take higher priority:

```java
registry.config()
        .meterFilter(MeterFilter.denyNameStartsWith("shop.orders.internal."))
        .meterFilter(MeterFilter.acceptNameStartsWith("shop."));
```

Names matching neither rule are still not automatically forbidden, because both can return NEUTRAL.

To build an allowlist for a single group, you can add `MeterFilter.deny()` at the end, or use `denyUnless` with an appropriate predicate. Choose based on clear intent, not merely by ordering filter method names.

### accept and denyUnless Differ on Matching Cases

```java
MeterFilter.accept(id -> id.getName().startsWith("shop."));
MeterFilter.denyUnless(id -> id.getName().startsWith("shop."));
```

For a name starting with `shop.`:

- `accept(...)` returns ACCEPT, ending the decision chain.
- `denyUnless(...)` returns NEUTRAL, letting subsequent rules continue evaluating.

For non-matching names, `denyUnless` returns DENY. As a result, it can restrict a scope while still letting later rules deny specific cases within that scope.

## 4. map Ordering Differs from accept Ordering

For a new meter being created in Micrometer 1.13.0, you can picture it as:

```text
Initial identifier
    -> map of filter 1
    -> map of filter 2
    -> ... mapped identifier
    -> accept chain on mapped identifier
        -> DENY: return NOOP meter
        -> accepted: configure distribution if any, then create meter
```

`map` transformations chain sequentially: each filter receives the mapped result of the previous filter. Therefore, renaming the prefix first and then renaming a tag key based on the new prefix is a meaningful order.

The `accept` methods inspect **the identifier after the map chain**. If `legacy.orders.processed` has already been renamed to `shop.orders.processed`, accept/deny rules must be written against the corresponding final name.

Do not picture each filter as a complete "map then accept then configure" unit before moving to the next filter. The phases are orchestrated by the registry.

An early ACCEPT only stops asking subsequent `accept` methods. It does not mean later `map` transformations are skipped: the map chain already ran before the decision step. Likewise, do not infer that ACCEPT skips distribution configuration from other filters.

When the registry finds an existing meter, it can reuse the instance instead of walking the entire creation path again. This exact ordering is verified in [Micrometer 1.13.0 MeterRegistry](https://raw.githubusercontent.com/micrometer-metrics/micrometer/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/MeterRegistry.java).

## 5. Renaming Meters, Renaming Tag Keys, and Dropping Tags

The following three operations are distinct:

| Need | How to Express It |
| --- | --- |
| `legacy.orders.processed` to `shop.orders.processed` | Override `map`, return `id.withName(...)` |
| Tag key `result` to `outcome` | `MeterFilter.renameTag(prefix, fromKey, toKey)` |
| Drop tag key `request.id` | `MeterFilter.ignoreTags(...)`, optionally wrapped to restrict scope |
| Normalize a group of tag values | `MeterFilter.replaceTagValues(...)` with an appropriate mapping |

**renameTag does not rename the meter.** The first parameter is a name prefix used to scope which meters have their label key renamed.

Do not mutate the ID object in place or return null. Methods such as `withName` return a new ID; `map` must return the ID to use, or return the original ID when no change applies.

### Class Holding Shared Mappings

File `src/example/filter/OrderMetricFilters.java`:

```java
package example.filter;

import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.config.MeterFilter;

public final class OrderMetricFilters {

    private OrderMetricFilters() {
    }

    public static MeterFilter renameLegacyOrders() {
        return new MeterFilter() {
            @Override
            public Meter.Id map(Meter.Id id) {
                if (id.getName().startsWith("legacy.orders.")) {
                    return id.withName(
                            "shop." + id.getName().substring("legacy.".length()));
                }
                return id;
            }
        };
    }

    public static MeterFilter ignoreOrderRequestId() {
        MeterFilter delegate = MeterFilter.ignoreTags("request.id");

        return new MeterFilter() {
            @Override
            public Meter.Id map(Meter.Id id) {
                if (id.getName().startsWith("shop.orders.")) {
                    return delegate.map(id);
                }
                return id;
            }
        };
    }
}
```

The first filter only renames meters in the `legacy.orders.` group. The second filter only drops the tag for the `shop.orders.` group; it does not strip `request.id` from every other meter in the registry.

Scoping is part of the policy. Attaching `ignoreTags("request.id")` directly affects every identifier passing through it, not only order metrics.

## 6. Complete Program: Rename, Merge Tags, and Deny

The experiment below uses an isolated registry with a policy intentionally allowing only the `shop.` prefix after excluding the internal group. It makes the effect of each rule clear.

File `src/example/filter/MeterFilterDemo.java`:

```java
package example.filter;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.config.MeterFilter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public final class MeterFilterDemo {

    public static void main(String[] args) {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();

        try {
            registry.config()
                    .meterFilter(OrderMetricFilters.renameLegacyOrders())
                    .meterFilter(MeterFilter.renameTag(
                            "shop.orders.", "result", "outcome"))
                    .meterFilter(OrderMetricFilters.ignoreOrderRequestId())
                    .meterFilter(MeterFilter.denyNameStartsWith(
                            "shop.orders.internal."))
                    .meterFilter(MeterFilter.acceptNameStartsWith("shop."))
                    .meterFilter(MeterFilter.deny());

            Counter first = registry.counter(
                    "legacy.orders.processed",
                    "result", "success",
                    "request.id", "req-101");
            first.increment(2);

            Counter second = registry.counter(
                    "legacy.orders.processed",
                    "result", "success",
                    "request.id", "req-102");
            second.increment(3);

            Counter internal = registry.counter(
                    "legacy.orders.internal.debug");
            internal.increment(9);

            Counter outside = registry.counter("other.events");
            outside.increment(7);

            System.out.println("name=" + first.getId().getName());
            System.out.println("outcome=" + first.getId().getTag("outcome"));
            System.out.println("request.id="
                    + first.getId().getTag("request.id"));
            System.out.println("same-counter=" + (first == second));
            System.out.println("merged-count=" + first.count());
            System.out.println("internal-count=" + internal.count());
            System.out.println("outside-count=" + outside.count());

            System.out.println("original-name-present="
                    + (registry.find("legacy.orders.processed")
                            .counter() != null));
            System.out.println("mapped-name-present="
                    + (registry.find("shop.orders.processed")
                            .tag("outcome", "success").counter() != null));
            System.out.println("meters=" + registry.getMeters().size());
        } finally {
            registry.close();
        }
    }
}
```

The two registrations have different request IDs, yet after mapping they share the same name/tag:

```text
shop.orders.processed{outcome=success}
```

Because both are Counters for the same quantity, they share the same instance; recorded counts add into that Counter.

The internal meter is renamed to `shop.orders.internal.debug` and then rejected by the deny rule matching the new name. The `other.events` meter is not accepted and is rejected by the final DENY rule.

**The allowlist in the experiment is an intentional choice for this registry.** Do not drop the final `deny()` rule as-is into a Boot application that needs JVM/HTTP metrics and expect groups outside `shop.` to remain registered.

### Dependencies and Run Commands

The standalone example uses JDK 17+ and Micrometer 1.13.0. Create `pom.xml` in the root directory:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>meter-filter-demo</artifactId>
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

Maven is required in PATH; the first dependency download requires access to Maven Central. Run from the directory containing `pom.xml`.

PowerShell on Windows:

```powershell
mvn -q org.apache.maven.plugins:maven-dependency-plugin:3.6.1:copy-dependencies -DoutputDirectory=lib
javac --release 17 -encoding UTF-8 -cp "lib/*" -d out src/example/filter/OrderMetricFilters.java src/example/filter/MeterFilterDemo.java
java -cp "out;lib/*" example.filter.MeterFilterDemo
```

On Linux/macOS, use `:` in the run command's classpath:

```bash
java -cp "out:lib/*" example.filter.MeterFilterDemo
```

Stdout:

```text
name=shop.orders.processed
outcome=success
request.id=null
same-counter=true
merged-count=5.0
internal-count=0.0
outside-count=0.0
original-name-present=false
mapped-name-present=true
meters=1
```

`request.id=null` indicates the label key is no longer present in the ID, not that there is a tag with string value `"null"`.

In Micrometer 1.13.0, the registry has `close()` but does not implement `AutoCloseable`, so the example closes it in a `finally` block.

## 7. A Denied Meter Can Still Return an Object

When a filter returns DENY, Micrometer typically returns a NOOP meter, such as `NoopCounter`. Business code can still call `increment` on that object, but it will not record measurements like a real Counter.

In the program above, `internal` and `outside` are both non-null. However:

- The read value of the NOOP Counters in the experiment is `0.0`.
- The registry contains only one accepted Counter.
- Neither the internal metric nor `other.events` is registered.

Therefore, checking `counter != null` after a registration call does not prove the policy allowed it. When verifying filters, look up by the final identifier in the registry and check recorded values.

Blocking registration also does not automatically delete historical data already received by the monitoring system earlier. When switching policy in a new deployment, distinguish legacy data from metrics currently being registered.

## 8. Changing Identifiers Can Merge Multiple Sources Into One

Dropping tags or renaming multiple names to the same name can make previously distinct identifiers collide.

In section 6, merging requests into the same resulting Counter is intentional: the question to answer is total successfully processed orders, not a separate Counter per request.

However, not every merge has the same semantics.

| Instrument / Scenario | Consequence to Check |
| --- | --- |
| Counters for the same quantity after dropping a label | Calls can share one Counter and add events into it |
| Two Gauges measuring two different objects | Does not automatically become a Gauge summing both objects |
| Two names mapping to the same ID with different meter types | Can hit a meter-type conflict on registration |
| Two tags sharing the same meaning after normalization | Can intentionally reduce series count, but check queries and alerts |

Example illustrating Gauge on a fresh registry:

```java
registry.config().meterFilter(MeterFilter.ignoreTags("queue"));

AtomicInteger left = new AtomicInteger(2);
AtomicInteger right = new AtomicInteger(9);

Gauge a = Gauge.builder("shop.queue.depth", left, AtomicInteger::get)
        .tag("queue", "left")
        .register(registry);

Gauge b = Gauge.builder("shop.queue.depth", right, AtomicInteger::get)
        .tag("queue", "right")
        .register(registry);
```

After dropping the `queue` tag, the two registrations have the same ID. With the default registry and the order above, the existing Gauge keeps reading the `left` source; there is no automatic addition to 11.

If the combined size of both queues is needed, design an explicit aggregate source/function instead of using `ignoreTags` and expecting the registry to sum them.

When renaming tag keys, also check the case where an ID already contains both the old key and the new key. The policy must handle collisions clearly; do not treat the two keys as still independent after mapping them to the same key.

## 9. Integrating in Spring Boot Actuator

In Boot 3.3 with Actuator and metrics auto-configuration active, `MeterFilter` beans are attached by Boot to the Spring-managed registry.

The configuration below reuses `OrderMetricFilters` from section 5 with an explicit mapping order. It denies the internal orders group and lets other groups continue through the rest of the application's policy.

File `OrderMetricsConfiguration.java`:

```java
package example.filter;

import io.micrometer.core.instrument.config.MeterFilter;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;

@Configuration(proxyBeanMethods = false)
public class OrderMetricsConfiguration {

    @Bean
    @Order(10)
    public MeterFilter renameLegacyOrders() {
        return OrderMetricFilters.renameLegacyOrders();
    }

    @Bean
    @Order(20)
    public MeterFilter renameOrderResultTag() {
        return MeterFilter.renameTag(
                "shop.orders.", "result", "outcome");
    }

    @Bean
    @Order(30)
    public MeterFilter ignoreOrderRequestId() {
        return OrderMetricFilters.ignoreOrderRequestId();
    }

    @Bean
    @Order(40)
    public MeterFilter denyInternalOrders() {
        return MeterFilter.denyNameStartsWith("shop.orders.internal.");
    }
}
```

This configuration integrates into an existing Boot application, not a standalone application. The package must be scanned or the configuration must be imported. Let Boot's dependency management select the compatible Micrometer version.

`@Order` expresses the relative order among the filters in the example. The application still needs to check other filters or accept rules added elsewhere; an ACCEPT appearing earlier in the chain can affect deny rules.

Use the injected `MeterRegistry` to register business metrics. Do not create a separate registry and expect Boot's filter beans to be applied to it automatically. See [customizing metrics in Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.customizing).

If you only need to enable/disable a prefix, Boot also supports configuration such as:

```properties
management.metrics.enable.shop.orders.internal=false
```

That is an option for prefix-based accept/deny policies. Renaming meters or mapping tags still requires an appropriate mechanism such as a MeterFilter in code.

### Inspecting Mapped Names via Actuator

In an application with a web runtime, you can expose the diagnostic endpoint with practice-environment configuration:

```properties
management.endpoints.web.exposure.include=health,metrics
```

After the application's business code has registered and recorded the order Counter as in the example, with the default Actuator port and path:

```bash
curl "http://localhost:8080/actuator/metrics/shop.orders.processed?tag=outcome:success"
```

Use the **post-mapping** logical name `shop.orders.processed`, along with the `outcome` tag. Do not use the old name or the `result` key.

Names normalized by an exporter, such as converting dots to underscores for Prometheus export, are another representation layer. Query the `metrics` endpoint by the logical name in the registry.

The endpoint only shows measurements actually present in the application. Configuring a filter does not create Counters or emit events on its own. If the application uses authentication, a separate management port, or a custom base path, requests must follow that configuration.

Exposing an endpoint over HTTP is also different from accepting a meter: exposing `metrics` does not give metrics data to a meter that received DENY.

## 10. Limitations and Configuration Pitfalls to Recognize

### Configure Filters Before Registering Related Meters

In plain Java, attach filters right after creating the registry and before registering meters. In Boot, prefer filter beans so the metrics mechanism installs them at the right lifecycle phase.

Adding filters after meters already exist is not a bulk migration of old measurements. Do not rely on it to consistently rename, remove, or update instances to which the application already holds references.

Micrometer 1.13.0 warns when a filter is configured late. When rolling out name/tag changes, verify results in a fresh context and review queries, charts, and alerts using old identifiers.

### Tag Limits Must Sit in the Right Place in the Decision Chain

Example of registering a limit early:

```java
registry.config().meterFilter(
        MeterFilter.maximumAllowableTags(
                "shop.orders.", "outcome", 3, MeterFilter.deny()));
```

It caps the number of `outcome` tag values seen for the matching name group. However, if an earlier filter already returned ACCEPT for all `shop.`, the limit rule may never be asked during the `accept` phase.

A limit is only an additional safeguard. You still need to design a finite tag set and monitor whether measurements are being denied. Do not emit arbitrary values and merely hope a filter drops the excess.

### Filters Must Preserve Metric Semantics

A rename should not make two different quantities look like the same quantity. For example, do not rename both "orders received" and "orders completed" to one Counter just to have fewer names.

Similarly, dropping tags can reduce label combinations, but it also removes the ability to distinguish sources. Verify the meaning of the aggregation before deploying.

### Distinguish Registry Configuration from Other Data Scopes

MeterFilter does not rewrite business code, logs, traces, or external historical data. Nor is it a per-request filtering mechanism before business logic runs.

When a measurement is missing, check step by step: was it registered/recorded, what are its name/tags after `map`, which filter decided `accept`, and which registry is being queried.

## 11. Verification and Hands-On Practice

| What to Prove | How to Verify |
| --- | --- |
| Name mapping has the right scope | Legacy order names are renamed; out-of-scope names are untouched |
| Tag key rename works correctly | ID has `outcome`, no longer `result` |
| Tag removal has the right scope | `request.id` is absent on the order group, not arbitrarily stripped elsewhere |
| Deny chain has the right order | Internal names receive DENY before broad ACCEPT rules |
| NOOP is not mistaken for a registered meter | Compare counts and look up inside the registry |
| Merging makes sense | Two Counters for the same quantity merge; two Gauges do not sum sources |
| Boot attached filter beans | Build a context with metrics auto-configuration, register via injected registry, and look up by final name |

Practice exercises:

1. Run the two Java files in sections 5–6 and verify all 10 stdout lines.
2. Change one recording call from `result=success` to `result=failure`. The two outcomes should produce two distinct Counters under the `outcome` tag, even though request ID was dropped.
3. In a separate test registry, place the broad ACCEPT before the internal DENY. Confirm the internal meter gets registered and explain why.
4. Try placing a renaming filter after an ACCEPT filter in the list. Observe that mapping still runs before acceptance evaluation; do not treat this order like an HTTP filter chain.
5. Run the Gauge snippet in section 8 and check which source is read. Modify `right` alone and explain why the first registered Gauge does not change with it.
6. Integrate the configuration from section 9 and confirm metrics outside the order scope can still register under the application's existing policy.
7. Before applying a filter to a system, document: name scope, ID transformation, decision order, impact on tag combination count, and queries that need updating.

A clear MeterFilter policy must state which meters are kept, which meters are denied, what the final identifiers are, and whether any transformation alters the meaning of the numbers.
