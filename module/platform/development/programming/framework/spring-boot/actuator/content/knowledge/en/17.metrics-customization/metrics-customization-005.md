# Enabling or Disabling Metric Groups with management.metrics.enable

## 1. Controlling Which Metrics the Registry Accepts

A Spring Boot application can emit metrics for the JVM, HTTP, databases, caches, and business logic. Not every environment needs to collect all of those metrics.

`management.metrics.enable` is a **map of rules by metric name**, used to allow or deny meters when they are registered into a Spring Boot-configured registry.

For example:

```properties
management.metrics.enable.jvm=false
```

This rule disables the `jvm` group, such as `jvm.memory.used` and `jvm.threads.live`, within the scope of registries where Boot's filter applies. It does not mean stopping the JVM, halting business processing, or disabling all of Actuator.

You can visualize it as:

```text
Instrumentation or business code wants to register a meter
    -> registry checks rules/filters
        -> accepted: create or reuse real meter
        -> denied: return a non-recording meter
    -> calling code can still use the meter interface
```

This lesson uses Spring Boot 3.3.0 and Micrometer 1.13.0 to verify behavior. Per-metric-group configuration is described by Boot in [Per-meter Properties](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.customizing.per-meter-properties).

## 2. Basic Configuration: Disable a Group or Allow Selectively

### 2.1. Keep Defaults and Exclude Only Unneeded Groups

If no matching rule is set, this enable mechanism allows meters by default, provided no other filter denies them.

For example, disable only JVM metrics and the HTTP client metric group by its corresponding name:

```yaml
management:
  metrics:
    enable:
      jvm: false
      "http.client.requests": false
```

Equivalent properties form:

```properties
management.metrics.enable.jvm=false
management.metrics.enable.http.client.requests=false
```

Metrics outside those two groups are not disabled by these two rules. Quoting the dotted key in YAML helps readers see clearly that it is a single group-name key; it does not turn it into a regular expression.

The name used is the **Micrometer name**, for example `http.client.requests`, not the name converted to Prometheus's naming convention such as `http_client_requests_seconds_count`.

### 2.2. Disable by Default and Enable Only Needed Groups

Use the special key `all` as the fallback value for names without a specific rule:

```yaml
management:
  metrics:
    enable:
      all: false
      jvm: true
      "jvm.gc": false
      "http.server.requests": true
      "app.orders": true
```

With this configuration, considering Boot's enable mechanism alone:

| Meter Name | Deciding Rule | Result |
| --- | --- | --- |
| jvm.memory.used | jvm=true | Allowed |
| jvm.threads.live | jvm=true | Allowed |
| jvm.gc.pause | jvm.gc=false | Denied |
| http.server.requests | http.server.requests=true | Allowed |
| app.orders.accepted | app.orders=true | Allowed |
| cache.gets | all=false | Denied unless another specific rule applies |

`all=false` is not an absolute veto over every name. It is a **fallback value**, so a specific group can still be re-enabled.

Conversely, `all=true` does not prevent a specific group from being set to false.

### 2.3. Enabling Does Not Create Missing Instrumentation

Setting `management.metrics.enable.app.orders=true` only allows the corresponding name to be registered. It does not automatically create an order counter, does not instrument services on its own, and does not cause every library to start emitting metrics.

To have data, all of these conditions are still required:

1. Instrumentation or code that registers the meter.
2. A suitable registry.
3. Meter name permitted by rules/filters.
4. Events or values to record.
5. An export/collection path if external observation outside the application is needed.

## 3. More Specific Names Are Evaluated Before Parent Groups

Rules are resolved along dot-separated segments of the name. For `app.orders.debug.payload`, the lookup order is:

```text
app.orders.debug.payload
app.orders.debug
app.orders
app
all, if no rule was found yet
default true, if even all is absent
```

As soon as a rule is found at the most specific level checked, that result is used. **Seeing a parent group set to false does not mean every child group is permanently disabled.**

For example:

```properties
management.metrics.enable.all=false
management.metrics.enable.app.orders=true
management.metrics.enable.app.orders.debug=false
management.metrics.enable.app.orders.debug.audit=true
```

Results:

| Meter Name | First Rule Found | Allowed? |
| --- | --- | --- |
| app.orders.accepted | app.orders=true | Yes |
| app.orders.debug.payload | app.orders.debug=false | No |
| app.orders.debug.audit.saved | app.orders.debug.audit=true | Yes |
| app.billing.completed | all=false | No |

This lets you open a business domain, disable a detailed internal branch, and still keep a specific sub-branch you actually need to observe.

### Group Boundaries Are Name Segments, Not Arbitrary String Prefixes

In Spring Boot 3.3.0:

```properties
management.metrics.enable.app.orders=false
```

matches `app.orders` and `app.orders.accepted`, but does not automatically match `app.ordersx.accepted`.

The implementation looks up the full name and then strips one trailing dot-delimited segment at a time. You can verify this lookup in [Spring Boot 3.3.0 PropertiesMeterFilter](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/PropertiesMeterFilter.java). Do not replace that rule with an assumption that all configurations use `String.startsWith` on an arbitrary string.

## 4. Disabling Metrics Differs from Hiding Endpoints and Disabling Exporters

The following settings act at different layers:

| Configuration | Affected Layer | Meaning |
| --- | --- | --- |
| management.metrics.enable.jvm=false | Meter registration by name | Denies the JVM group in the filtered registry |
| management.endpoint.metrics.enabled=false | Actuator metrics endpoint | Disables the diagnostic metrics endpoint |
| management.endpoints.web.exposure.exclude=metrics | HTTP accessibility | Does not expose the metrics endpoint over the web |
| management.prometheus.metrics.export.enabled=false | Prometheus exporter/registry | Disables the corresponding Prometheus export mechanism in Boot config |

For example, exposing only health:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health
```

Not exposing metrics over HTTP **does not mean meters have stopped existing or stopped being collected via another registry**.

Similarly, disabling the metrics endpoint does not automatically disable the prometheus endpoint or every active exporter. Disabling Prometheus export alone also does not imply other registries have been disabled.

[Spring Boot 3.3 Actuator Endpoints documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html) distinguishes between enabled endpoints and exposed endpoints. When troubleshooting, clarify whether you want to stop registering a meter group, stop exporting to a system, or only change endpoint accessibility.

## 5. How Does a Denied Meter Behave?

A filter that denies a meter typically causes the registry to return a **non-recording** object, also called a NOOP meter. Code can still invoke methods defined on the Micrometer interface.

For a denied counter in this lesson's experiment:

```text
counter.increment(2) can still be called
counter.count() returns 0
registry.find(name).counter() finds no registered counter
```

Distinguish carefully:

- **Real counter with value 0:** the meter exists but has not been incremented yet.
- **Denied counter:** the returned object ignores recordings; the registry does not publish it as an accepted counter.

Do not use a zero value to conclude that a business event never happened. The event may have occurred while the measurement was denied by configuration.

DENY and NOOP behavior is explained by Micrometer in [Meter Filters](https://docs.micrometer.io/micrometer/reference/1.13/concepts/meter-filters.html).

### Scope of Resource Impact

Denying a meter can reduce retained statistics and exported data, but it does not guarantee eliminating all related overhead:

- Business code still executes.
- Code may already have computed tags or prepared inputs before calling the meter.
- Instrumentation/binder components or background tracking mechanisms may still be initialized depending on the library.
- Previously sent data remains in the monitoring system per its retention policy.

Therefore, do not treat management.metrics.enable as a kill switch for all activity of the instrumented library. If the goal is to eliminate an expensive collection task, measure actual impact and inspect the lifecycle of the corresponding instrumentation.

## 6. Java Experiment Verifying Registration Rules

The program below initializes isolated Spring contexts using Boot's actual metrics auto-configuration. Each case applies configuration before creating the registry.

The `app.*` names are test counters registered by the program, not auto-generated JVM or HTTP metrics. No web server is needed to verify the enable mechanism.

### 6.1. Preparing a Standalone Project

Use JDK 17 or higher; JDK 21 is recommended. File `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-actuator-autoconfigure'
    implementation 'org.springframework:spring-context'
    implementation 'io.micrometer:micrometer-core'
}

application {
    mainClass = 'demo.MetricsEnableDemo'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
    options.compilerArgs += ['-parameters']
}

tasks.register('copyRuntimeDependencies', Copy) {
    from configurations.runtimeClasspath
    into layout.buildDirectory.dir('runtime-libs')
}
```

File `settings.gradle`:

```groovy
rootProject.name = 'metrics-enable-demo'
```

Versions are managed by the Spring Boot 3.3.0 BOM. In a Boot application that already has dependency management and Actuator, you do not need to create this extra project; it serves independent verification.

### 6.2. Complete Source Code

File `src/main/java/demo/MetricsEnableDemo.java`:

```java
package demo;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;
import org.springframework.boot.actuate.autoconfigure.metrics.MetricsAutoConfiguration;
import org.springframework.boot.actuate.autoconfigure.metrics.MetricsProperties;
import org.springframework.boot.actuate.autoconfigure.metrics.export.simple.SimpleMetricsExportAutoConfiguration;
import org.springframework.boot.autoconfigure.ImportAutoConfiguration;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.MapPropertySource;

public class MetricsEnableDemo {
    @Configuration(proxyBeanMethods = false)
    @ImportAutoConfiguration({
        MetricsAutoConfiguration.class,
        SimpleMetricsExportAutoConfiguration.class
    })
    public static class Config {
    }

    public static void main(String[] args) {
        runCase("default", Map.of(),
                "app.orders.accepted");

        runCase("prefix", Map.of(
                "management.metrics.enable.app.orders", "false"),
                "app.orders",
                "app.orders.accepted",
                "app.ordersx.accepted");

        runCase("exceptions", Map.of(
                "management.metrics.enable.all", "false",
                "management.metrics.enable.app.orders", "true",
                "management.metrics.enable.app.orders.debug", "false",
                "management.metrics.enable.app.orders.debug.audit", "true"),
                "app.orders.accepted",
                "app.orders.debug.payload",
                "app.orders.debug.audit.saved",
                "app.billing.completed");

        runCase("star-normalized", Map.of(
                "management.metrics.enable.all", "false",
                "management.metrics.enable.app.*", "true"),
                "app",
                "app.orders.accepted");

        runCase("literal-star", Map.of(
                "management.metrics.enable.all", "false",
                "management.metrics.enable[app.*]", "true"),
                "app.orders.accepted");
    }

    private static void runCase(String label, Map<String, String> enableProperties,
            String... meterNames) {
        Map<String, Object> properties = new HashMap<>();
        properties.put("management.metrics.use-global-registry", "false");
        properties.putAll(enableProperties);

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {
            context.getEnvironment().getPropertySources().addFirst(
                    new MapPropertySource("case-" + label, properties));
            context.register(Config.class);
            context.refresh();

            SimpleMeterRegistry registry = context.getBean(SimpleMeterRegistry.class);
            System.out.println("[" + label + "]");
            if (label.equals("star-normalized") || label.equals("literal-star")) {
                System.out.println("bound.rules=" + new TreeMap<>(
                        context.getBean(MetricsProperties.class).getEnable()));
            }
            for (String name : meterNames) {
                Counter counter = registry.counter(name, "channel", "web");
                counter.increment(2);
                boolean visible = registry.find(name)
                        .tag("channel", "web").counter() != null;
                System.out.printf(Locale.ROOT, "%s registered=%s count=%.0f%n",
                        name, visible, counter.count());
            }
        }
    }
}
```

`management.metrics.use-global-registry=false` keeps the test cases independent of the static global registry. Each context has a fresh registry, so results never mix meters or counts from earlier cases.

`TreeMap` only prints the configuration map in a deterministic order in the two asterisk cases; displayed line order does not determine which rule is more specific.

### 6.3. Running the Program

With Gradle installed, or the experiment project's own wrapper:

```shell
gradle -q run
```

You can also compile/run directly after running `gradle -q copyRuntimeDependencies`. Commands on Windows:

```shell
javac --release 17 -encoding UTF-8 -parameters -cp "build/runtime-libs/*" -d build/manual-classes src/main/java/demo/MetricsEnableDemo.java
java -cp "build/manual-classes;build/runtime-libs/*" demo.MetricsEnableDemo
```

On Linux/macOS, replace the `;` separating classpath entries in the `java` command with `:`.

### 6.4. Verified Stdout

```text
[default]
app.orders.accepted registered=true count=2
[prefix]
app.orders registered=false count=0
app.orders.accepted registered=false count=0
app.ordersx.accepted registered=true count=2
[exceptions]
app.orders.accepted registered=true count=2
app.orders.debug.payload registered=false count=0
app.orders.debug.audit.saved registered=true count=2
app.billing.completed registered=false count=0
[star-normalized]
bound.rules={all=false, app=true}
app registered=true count=2
app.orders.accepted registered=true count=2
[literal-star]
bound.rules={all=false, app.*=true}
app.orders.accepted registered=false count=0
```

There are no timing metrics dependent on execution scheduling. Every test counter is incremented by the same amount of 2, making accepted meters clearly distinguishable from denied meters.

## 7. Reading the Results Instead of Looking Only at Property Values

### 7.1. Default Case

With no extra enable rules, `app.orders.accepted` is registered and has a count of 2.

This demonstrates the enable filter's default in the experiment context; a real application may still have another MeterFilter denying the same name.

### 7.2. Disabling a Prefix Group

With `app.orders=false`:

```text
app.orders             -> denied
app.orders.accepted    -> denied
app.ordersx.accepted   -> still allowed
```

The result proves both that the exact key name itself is affected and that segment boundaries matter. Not every name sharing the same leading characters belongs to the same group.

### 7.3. Re-enabling a Sub-branch

The exceptions case uses four rules:

```text
all=false
app.orders=true
app.orders.debug=false
app.orders.debug.audit=true
```

The normal order branch works, the debug branch is blocked, the debug.audit sub-branch is re-enabled, and billing is blocked by the all=false fallback.

The proper way to read this is to find the most specific rule for **each name**, rather than reading the lines like an ordered sequence of on/off commands that overwrite one another.

### 7.4. Why app.* Can Look Like a Wildcard Even Though the Filter Does Not Process Globs

This is what the last two cases deliberately test.

In the star-normalized case, the input has:

```properties
management.metrics.enable.all=false
management.metrics.enable.app.*=true
```

Yet the bound map printed out is:

```text
{all=false, app=true}
```

With the property source used in the Boot 3.3.0 experiment, the asterisk is not preserved in the map key. The rule actually received is `app=true`, so even the exact name `app` is opened.

The literal-star case preserves the key using bracket notation:

```properties
management.metrics.enable.all=false
management.metrics.enable[app.*]=true
```

The map is now:

```text
{all=false, app.*=true}
```

The name `app.orders.accepted` does not find an `app.*` rule while walking the name and parent groups, so it is blocked by all=false. **Preserving the asterisk does not turn the key into a glob expression.**

Spring Boot documents the rules for preserving special characters in map keys in [Binding Maps](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.relaxed-binding.maps). The two cases above are for diagnosing how binding behaves, not recommended configuration patterns.

To enable the app group, the clear way is:

```properties
management.metrics.enable.app=true
```

Do not add `.*`, do not write regexes, and do not rely on special characters accidentally getting normalized away. When a configuration containing special characters produces puzzling results, inspect the bound map instead of inferring a matching algorithm from the input line.

## 8. Applying in a Boot Application and Checking the Right Layer

### 8.1. Choose Rules by Actual Names

In an application that already has Actuator, start with the meter names that instrumentation actually registers. For example, if you have `jvm.memory.used`, `jvm.gc.pause`, and `http.server.requests`, you can disable those groups or individual names.

Setting `management.metrics.enable.http_server_requests_seconds_count=false` is not how you disable the Micrometer timer named `http.server.requests`. Suffixes like `_count` or `_sum` are part of backend-specific exported data, not necessarily the original meter name.

### 8.2. Observe a Fresh Run

Configure a clear verification case:

```yaml
management:
  metrics:
    enable:
      "app.orders": false
  endpoints:
    web:
      exposure:
        include: health,metrics
```

After the application executes the business path that registers the counter, check:

```shell
curl "http://localhost:8080/actuator/metrics"
curl "http://localhost:8080/actuator/metrics/app.orders.accepted"
```

These URLs apply to a web application with the same metric names; this lesson's console program does not open an HTTP port. Host, port, base path, and authentication requirements follow the application's configuration.

When only this filtered registration path exists, the denied name does not appear as an accepted meter in the corresponding registry. The detail endpoint may return not found; that is different from failing to expose the metrics endpoint altogether.

If there are multiple registries or a composite registry, identify the child registry actually used to export data. Do not use a result from an unexported registry to conclude the whole application stopped emitting a metric.

### 8.3. Verify Enabled Behavior Too

Change the rule to true, start a new context/process, and trigger the event again. Confirm:

- The meter appears in the target registry.
- The value increases with the defined event.
- Other groups still follow their rules.
- Data exported to the backend matches the verified name and tags.

Testing both enabled and disabled paths helps distinguish instrumentation that never ran from a filter working properly.

### 8.4. Do Not Assume This Is a Live Runtime Toggle

Standard configuration is applied during initialization. Merely editing a file or changing a value in Environment does not guarantee existing meters are deleted, recreated, or toggled immediately.

To verify with the standard mechanism in this lesson, change the configuration and start a new context/application. If a system has a custom refresh mechanism, verify that mechanism's contract regarding registries, cached meters, and exported data.

Samples blocked while disabled are also not buffered to be replayed when enabled.

## 9. Filtering Scope and Coordinating Filters

### 9.1. This Property Filters by Name, Not by Tag

The rule:

```properties
management.metrics.enable.http.server.requests=false
```

acts on the meter name, not a specific status, method, or URI. Likewise, `app.orders=false` has no built-in syntax here to "disable only channel=web".

If filtering by tag is needed, use an appropriate MeterFilter mechanism or adjust instrumentation design. Do not append tag conditions to the property name expecting Boot to parse it as a label query.

### 9.2. true Is Not Necessarily the Final Accept Decision

In Boot 3.3.0's PropertiesMeterFilter:

- An enable result of false returns DENY.
- An enable result of true returns NEUTRAL so other filters can still evaluate it.

Therefore, true can still be denied by another filter. Conversely, an earlier ACCEPT filter can end acceptance evaluation early, preventing subsequent filters from being consulted at that step.

If enable configuration seems ineffective, inspect custom filters and application order instead of immediately adding duplicate rules. This is a consequence of the filter chain, not `all` or child group rules changing their meaning.

### 9.3. The Registry Must Be Within Configured Scope

Boot properties do not automatically apply to arbitrary Java objects created with `new SimpleMeterRegistry()`. Prefer the Spring-managed registry for application code.

The experiment imports Boot's metrics auto-configuration to test the real filter-application process; it does not reimplement a lookup algorithm to fake a simulated result.

## 10. Choosing Sensible Groups in Operations

Two common configuration strategies:

| Strategy | Best When | Considerations |
| --- | --- | --- |
| Allow by default, disable selected groups | You want broad observability and only trim unused groups | New groups may appear automatically if instrumentation is added |
| all=false, enable only a required allowlist | You want strict control over permitted metric domains | Must update the list when adding metrics needed for diagnosis |

Do not disable a group just because it has many names without checking which dashboards or alerts depend on it. A small change like disabling `jvm` can wipe out memory, thread, and GC data even when the original goal was to drop one sub-branch.

Once disabled at the source, dashboards reading historical data may still display older points within the query window. Missing data should also not automatically be interpreted as a measurement of 0; those two states mean different things.

## 11. Common Issues and Self-Diagnosis

| Symptom | Cause to Check | Fix |
| --- | --- | --- |
| Child metric stays enabled even though parent is false | A more specific rule is set to true | Trace from full name up to parent groups |
| all=false yet some metrics still register | A true exception, another ACCEPT filter, or another registry | Check effective config, filter chain, and exporting registry |
| Used app.* and saw the app group enabled | Key may have been normalized during binding | Use app directly; inspect the bound enable map |
| Disabled Prometheus name but timer remains | Configuring by exported name instead of Micrometer name | Use original name such as http.server.requests |
| Hid metrics from HTTP yet backend still gets data | Changed exposure instead of denying meters | Choose the right control layer |
| Counter returns 0 even though business logic ran | May be a NOOP counter due to denial | Check registry.find and enable rules |
| Set true yet metric is still absent | Instrumentation has not created the meter or another filter denies it | Trigger a concrete event and check remaining conditions |
| Edited file yet running process did not change | No corresponding registry refresh mechanism | Test with a fresh context and verified effective config |
| A service still emits disabled data | Recording to a separate registry or another instrumentation path | Check where it actually registers and exports |

## 12. Practice

1. **Disable parent, re-enable a child name.** With app.orders=false and app.orders.accepted=true, predict the outcome for app.orders.accepted and app.orders.rejected, then verify in a fresh context.
2. **Change the fallback value.** Keep all=false while adding app.billing=true. Explain why order metrics are not automatically opened.
3. **Check name boundaries.** Compare app.orders.accepted with app.ordersx.accepted under rule app.orders=false.
4. **Distinguish NOOP from a real counter at 0.** Check meter presence in the registry alongside the count value.
5. **Pick the right layer.** For requirements "stop keeping the JVM group", "only remove the metrics URL from HTTP", and "stop exporting to Prometheus", select the three corresponding properties and explain their scope of impact.

After these experiments, you should be able to identify which name is being evaluated, what the most specific matching rule is, and which registry applies the rule. That is the foundation for enabling/disabling metric groups deliberately while understanding why measurements appear or are absent.
