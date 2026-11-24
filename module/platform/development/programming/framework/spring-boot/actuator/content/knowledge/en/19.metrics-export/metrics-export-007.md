# Enabling or Disabling Individual Registries and Default Export Behavior

## 1. Choosing Metrics Destinations Before Configuring Export

An application can measure order counts, processing duration, or memory usage, then forward those same measurements to multiple monitoring systems. In Micrometer, `MeterRegistry` manages measurement instruments such as `Counter`, `Timer`, and `Gauge`. Each receiving system has an appropriate registry implementation; a composite registry (`CompositeMeterRegistry`) can distribute measurements to multiple child registries. `SimpleMeterRegistry` keeps measurements in memory without sending them to an external service. These foundational concepts explain why disabling one export destination does not necessarily stop measurement recording. [Source: Micrometer — Registry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html).

This article focuses on Spring Boot 3.3.x: deciding which registry gets auto-configured, the relationship between per-system flags and the global default, and what happens when no receiving registry remains. You do not need to run a monitoring server for the experiment at the end of this article.

Example scenario: local runs on a developer machine only need in-memory metrics; deployment environments use Prometheus; the Datadog library remains on the classpath, yet that environment does not use it. The goal is to configure destinations explicitly rather than editing counter code across individual features.

Three questions should be answered in order:

1. Is the required registry library on the classpath and included in auto-configuration?
2. Do the enable/disable flags permit that auto-configuration to run?
3. Does the created registry actually receive measurements, and does the external system have a path to collect them?

## 2. Two Levels of Enable/Disable Configuration

### 2.1. Per-Registry Flags

In Spring Boot 3.3, the property naming pattern is `management.<system>.metrics.export.enabled`. For example:

```properties
management.datadog.metrics.export.enabled=false
management.prometheus.metrics.export.enabled=true
management.simple.metrics.export.enabled=false
```

`<system>` is the system name supported by Spring Boot, such as `datadog`, `prometheus`, `simple`, `otlp`, or `jmx`. Do not substitute bean names or Java class names on your own. Setting `true` allows the auto-configuration branch to be evaluated further; library and bean conditions must still pass. Setting `false` prevents auto-configuration of the corresponding registry. Property naming is confirmed in the [Spring Boot 3.3 property appendix](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html).

Example disabling Datadog while its library remains packaged:

```yaml
management:
  datadog:
    metrics:
      export:
        enabled: false
```

This belongs in a Spring Boot application's `application.yml`, not a standalone Java program. Subsequent YAML examples are distinct configuration options; do not merge them by repeating multiple top-level `management:` keys in the same YAML document.

### 2.2. Shared Default for Registries Without a Per-System Flag

```yaml
management:
  defaults:
    metrics:
      export:
        enabled: false
```

This sets the default to disabled for registries that have not declared their own flag. Individual needed registries can then be re-enabled. Spring Boot documentation describes per-system enablement and the global default at [Metrics — Getting Started](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#getting-started).

Key distinction: `defaults` is a fallback when no per-system flag is set. It is not a master kill switch that overrides every other flag.

### 2.3. Precedence Order

For a given registry `X`, Spring Boot checks the per-system flag first. If none is set, it checks the shared default; if neither is set, the export-enabled condition matches by default. [Source: OnMetricsExportEnabledCondition, Spring Boot 3.3.13](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/export/OnMetricsExportEnabledCondition.java).

| Per-System Flag for X | Shared Default Flag | Export-Enabled Condition Outcome for X |
| --- | --- | --- |
| Unset | Unset | Enabled |
| Unset | `true` | Enabled |
| Unset | `false` | Disabled |
| `true` | Unset | Enabled |
| `true` | `true` | Enabled |
| `true` | `false` | Enabled |
| `false` | Unset | Disabled |
| `false` | `true` | Disabled |
| `false` | `false` | Disabled |

This table describes the **export-enabled condition**, which does not guarantee a bean will be created. For instance, `management.prometheus.metrics.export.enabled=true` does not download missing dependencies. The Prometheus branch also checks for `PrometheusMeterRegistry`, a `Clock` bean, and that the user has not already supplied the bean. [Source: PrometheusMetricsExportAutoConfiguration](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/export/prometheus/PrometheusMetricsExportAutoConfiguration.java).

A commonly misunderstood example:

```properties
management.defaults.metrics.export.enabled=false
management.prometheus.metrics.export.enabled=true
```

The per-system Prometheus flag still takes effect. To disable all Spring Boot auto-configured registries, inspect all active per-system flags in the effective configuration, not just the `defaults=false` line.

## 3. Practical Configuration Scenarios

### 3.1. Allowing Only Prometheus

Suppose a web application already includes Actuator and `io.micrometer:micrometer-registry-prometheus` under Spring Boot-managed versions:

```yaml
management:
  defaults:
    metrics:
      export:
        enabled: false
  prometheus:
    metrics:
      export:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health,prometheus
```

Read this in two parts: `defaults=false` together with `prometheus=true` selects the registry; `exposure.include` selects endpoints exposed over HTTP. You do not need to enable Simple as an intermediate step. Ensure no other configuration re-enables a second registry.

Prometheus typically actively pulls metrics from the application (pull/scrape); enabling the registry does not make the application send periodic HTTP requests to the Prometheus server. Configuring the scraper server is a separate step. [Source: Spring Boot — Prometheus](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#supported-monitoring-systems.prometheus).

### 3.2. Measuring Only in Memory on a Developer Machine

```yaml
management:
  defaults:
    metrics:
      export:
        enabled: false
  simple:
    metrics:
      export:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health,metrics
```

For a web application relying solely on auto-configuration without user-declared registries, this selects Simple while defaulting other registries to disabled. In-memory data is lost when the process terminates; it does not create historical storage.

If no external registry library has been added and defaults have not been changed, setting `simple=true` is usually unnecessary: Simple may be created as a fallback. Declaring it explicitly in the example documents the environment choice.

### 3.3. Temporarily Disabling One System While Keeping Others

```properties
management.datadog.metrics.export.enabled=false
```

This line affects only the Datadog branch; remaining registries continue evaluating their own conditions. When you want to stop exporting to one provider while keeping Prometheus, there is no need to flip the shared default.

Conversely, if the goal is to allow only a short list, setting the shared default to `false` and enabling each system explicitly communicates intent more clearly. In either approach, always inspect the effective configuration for each environment.

### 3.4. Separating Environment Configuration and Understanding Overrides

Example of two profile-specific configuration files selecting either `local` or `prod`:

```properties
# application-local.properties
management.defaults.metrics.export.enabled=false
management.simple.metrics.export.enabled=true
```

```properties
# application-prod.properties
management.defaults.metrics.export.enabled=false
management.prometheus.metrics.export.enabled=true
```

In this example, do not set `simple=true` in a shared file expecting prod's `defaults=false` to automatically disable it. The two properties have different names, so the per-system flag remains in effect. If multiple profiles are active simultaneously, check the merged result.

Two different kinds of precedence apply: Spring resolves the effective value of the **same key** across files, environment variables, and command-line arguments; then the registry condition evaluates **two different keys**, per-system first and shared default second. With a standard SpringApplication, command-line arguments can override values in files. [Source: Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

Example environment variables for the two enable/disable keys:

```text
MANAGEMENT_DEFAULTS_METRICS_EXPORT_ENABLED=false
MANAGEMENT_PROMETHEUS_METRICS_EXPORT_ENABLED=true
```

Bean-creation conditions are evaluated during context initialization. Do not assume that editing a file or environment variable of a running process instantly destroys or creates registries; for typical applications, new settings apply after a restart.

## 4. Simple as a Conditional Fallback Registry

### 4.1. Conditions for Creating Simple

Simple is evaluated after other registries. It is auto-created only when no `MeterRegistry` bean exists yet and the export-enabled condition for `simple` allows it. Therefore, even `management.simple.metrics.export.enabled=true` does not force creating an extra Simple registry if another registry already exists. [Source: SimpleMetricsExportAutoConfiguration](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/export/simple/SimpleMetricsExportAutoConfiguration.java).

The scenarios below assume Micrometer and Actuator are present, with no manually declared registries:

| Scenario | Expected Outcome |
| --- | --- |
| No external registry, defaults unchanged | Simple acts as the fallback measurement store |
| Prometheus has dependencies and auto-configures | Simple backs off because another registry exists |
| Prometheus explicitly disabled, shared default enabled, no other registry | Simple can be created |
| Shared default disabled, neither Simple nor any system enabled | Simple is not auto-created either |
| Shared default disabled, Simple explicitly enabled, no other registry | Simple is permitted as a fallback |
| Simple explicitly enabled while another registry exists | The enable flag does not bypass the missing-bean condition |

Fallback is not automatic failover on network errors. If a registry has been created and the external monitoring service stops responding, Spring Boot does not swap the existing registry for Simple. The missing-bean condition checks the application context, not server reachability.

### 4.2. What Happens When No Destination Remains?

In Boot 3.3's standard auto-configuration, if a `Clock` exists but no `MeterRegistry` bean exists at all, the no-op branch creates an empty `CompositeMeterRegistry`. [Source: NoOpMeterRegistryConfiguration](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/NoOpMeterRegistryConfiguration.java).

Thus, disabling all auto-configured exporters does not necessarily make `MeterRegistry` disappear or cause dependency injection to fail. Code can still call `counter.increment()`, but an empty composite has no child registry to retain the increment; the experiment below observes `0.0`.

Do not treat the existence of a registry bean or clean application startup as proof that metrics are being stored or exported. Inspect the registry type, child registries, and recorded values.

When multiple registries match, Boot can provide a primary composite for injection; when a single injectable registry exists, a composite wrapper is not always needed. Business code should not cast every `MeterRegistry` to `CompositeMeterRegistry`. [Source: CompositeMeterRegistryConfiguration](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/CompositeMeterRegistryConfiguration.java).

## 5. Distinguishing Four Types of Switches

| Configuration | What It Controls | What Cannot Be Inferred From It |
| --- | --- | --- |
| `management.prometheus.metrics.export.enabled=false` | Prometheus registry auto-configuration branch | Other registries are also disabled |
| `management.endpoints.web.exposure.exclude=prometheus` | Exposing the Prometheus endpoint over HTTP | The registry bean was destroyed |
| `management.metrics.enable.jvm=false` | Meter filter accepting meters in the `jvm` name prefix | All exporters are disabled |
| `management.metrics.use-global-registry=false` | Attaching Spring registries to Micrometer's static global registry | Registries in the Spring context stopped recording |

Endpoints also have `management.endpoint.prometheus.enabled`; an endpoint must satisfy its conditions and be exposed on the transport to be reachable. An HTTP 404 response can relate to exposure, path, or a missing endpoint; 401/403 can relate to access permissions. Do not rely on HTTP status codes alone to conclude whether a registry flag is enabled or disabled. [Source: Spring Boot — Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

`management.metrics.enable.*` is applied through a meter filter; it decides whether to accept meter groups by name. The registry can still exist to accept other meters. [Source: PropertiesMeterFilter](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/PropertiesMeterFilter.java).

In application code, injecting `MeterRegistry` clarifies which registry is in use. If static `Metrics.counter(...)` calls are used while global linking is disabled, separately inspect registries added to `Metrics.globalRegistry`; the static write path can differ from the Spring bean write path. The global linking property is documented in [Spring Boot — Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#getting-started).

## 6. Application-Declared Registries Are Your Own Responsibility

A `MeterRegistry` bean created by application code does not vanish just because `management.defaults.metrics.export.enabled=false` or a corresponding per-system flag is `false`. The flags covered here are conditions on Boot's auto-configuration; they are not a sweeper that shuts down arbitrary registry objects.

If you declare a registry manually, define appropriate bean lifecycle, profile, or conditional enablement, and avoid unintentionally creating two registries exporting to the same destination. The `MANUAL_BEAN` case in the experiment lets you observe this directly: both the shared default and Simple flag are off, yet the manually supplied Simple bean still counts.

## 7. Java Experiment: Observing Registries and Counter Values

### 7.1. Scope of the Experiment

This standalone program uses `ApplicationContextRunner` to create and close a Spring context per scenario, without opening HTTP or connecting to a monitoring system. It loads only three auto-configurations for basic metrics, Simple, and composite; it does not load Prometheus auto-configuration.

`PROMETHEUS_FLAG_ONLY` illustrates that setting a flag does not by itself load configuration or add libraries. Do not use that result to conclude Prometheus is broken in an application that already has full dependencies and auto-configuration.

Requires JDK 17 or higher, Maven, and network access for initial dependency resolution. The example pins Spring Boot 3.3.0 for reproducibility; property names and mechanics were verified for the 3.3 line. This dependency set is for the experiment, not a requirement to add test libraries to every application's production build.

Create a separate practice directory and place `pom.xml` and `RegistrySwitchDemo.java` side by side.

### 7.2. The pom.xml File

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.0</version>
    <relativePath/>
  </parent>
  <groupId>example</groupId>
  <artifactId>registry-switch-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-test</artifactId>
    </dependency>
    <dependency>
      <groupId>org.assertj</groupId>
      <artifactId>assertj-core</artifactId>
    </dependency>
  </dependencies>
</project>
```

`spring-boot-test` provides `ApplicationContextRunner`; AssertJ satisfies types used by the context runner API. Dependency versions are managed by the parent.

### 7.3. The RegistrySwitchDemo.java File

```java
import java.util.Locale;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.composite.CompositeMeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.actuate.autoconfigure.metrics.MetricsAutoConfiguration;
import org.springframework.boot.actuate.autoconfigure.metrics.CompositeMeterRegistryAutoConfiguration;
import org.springframework.boot.actuate.autoconfigure.metrics.export.simple.SimpleMetricsExportAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

public class RegistrySwitchDemo {
    private static ApplicationContextRunner runner() {
        return new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                MetricsAutoConfiguration.class,
                SimpleMetricsExportAutoConfiguration.class,
                CompositeMeterRegistryAutoConfiguration.class))
            .withPropertyValues("management.metrics.use-global-registry=false");
    }

    private static void show(String label, ApplicationContextRunner runner) {
        runner.run(context -> {
            if (context.getStartupFailure() != null) {
                throw new IllegalStateException(context.getStartupFailure());
            }
            MeterRegistry registry = context.getBean(MeterRegistry.class);
            Counter counter = registry.counter("demo.switch");
            counter.increment();
            int children = registry instanceof CompositeMeterRegistry composite
                ? composite.getRegistries().size() : -1;
            System.out.printf(Locale.ROOT, "%s: %s, children=%d, count=%.1f%n",
                label, registry.getClass().getSimpleName(), children, counter.count());
        });
    }

    public static void main(String[] args) {
        show("DEFAULT", runner());
        show("DEFAULTS_OFF", runner().withPropertyValues(
            "management.defaults.metrics.export.enabled=false"));
        show("SIMPLE_ON", runner().withPropertyValues(
            "management.defaults.metrics.export.enabled=false",
            "management.simple.metrics.export.enabled=true"));
        show("SIMPLE_OFF", runner().withPropertyValues(
            "management.defaults.metrics.export.enabled=true",
            "management.simple.metrics.export.enabled=false"));
        show("PROMETHEUS_FLAG_ONLY", runner().withPropertyValues(
            "management.defaults.metrics.export.enabled=false",
            "management.prometheus.metrics.export.enabled=true"));
        show("MANUAL_BEAN", runner()
            .withPropertyValues(
                "management.defaults.metrics.export.enabled=false",
                "management.simple.metrics.export.enabled=false")
            .withBean("manualRegistry", MeterRegistry.class, SimpleMeterRegistry::new));
    }
}
```

### 7.4. Compiling and Running

Run the following commands in PowerShell inside the directory containing the two files:

```powershell
mvn dependency:copy-dependencies -DincludeScope=runtime
New-Item -ItemType Directory -Force -Path target/classes | Out-Null
javac --release 17 -encoding UTF-8 -cp "target/dependency/*" -d target/classes RegistrySwitchDemo.java
java -cp "target/classes;target/dependency/*" RegistrySwitchDemo
```

On Linux/macOS, create the directory with `mkdir -p target/classes` and use `:` instead of `;` in the classpath when running `java`.

Stdout printed by the program:

```text
DEFAULT: SimpleMeterRegistry, children=-1, count=1.0
DEFAULTS_OFF: CompositeMeterRegistry, children=0, count=0.0
SIMPLE_ON: SimpleMeterRegistry, children=-1, count=1.0
SIMPLE_OFF: CompositeMeterRegistry, children=0, count=0.0
PROMETHEUS_FLAG_ONLY: CompositeMeterRegistry, children=0, count=0.0
MANUAL_BEAN: SimpleMeterRegistry, children=-1, count=1.0
```

`children=-1` is a convention chosen by this example for non-composite registries, not a negative registry count in Micrometer. Each scenario creates a fresh context so counters do not accumulate across lines.

Line-by-line explanation:

- `DEFAULT`: no flags set, no other registry present, Simple is created and retains the increment.
- `DEFAULTS_OFF`: Simple is not explicitly re-enabled; the empty composite retains the increment in no child registry.
- `SIMPLE_ON`: per-system `true` overrides shared default `false`.
- `SIMPLE_OFF`: per-system `false` overrides shared default `true`.
- `PROMETHEUS_FLAG_ONLY`: the flag alone does not load Prometheus auto-configuration into the runner.
- `MANUAL_BEAN`: the directly supplied bean persists despite both relevant auto-configuration flags being off; auto-configured Simple backs off.

The `management.metrics.use-global-registry=false` property in the runner keeps the experiment recording through each context's bean without linking to static global state. It does not prevent Simple from receiving increments.

## 8. Diagnosing Unexpected Results

| Symptom | What to Check |
| --- | --- |
| Set `defaults=false` but an external registry still exists | Look for per-system `true` flags in effective config and application-supplied beans |
| Enabled Prometheus but no registry appears | Check runtime classpath dependencies and auto-configuration conditions; flags do not replace classpath |
| Disabled a registry yet metrics are still visible | Check whether another registry or fallback Simple exists; do not assume stale data proves that exporter still runs |
| Registry bean exists but counts are always 0 | Check for an empty composite, meter filters, and bean vs. global write paths |
| Enabled Simple but no auto-configured Simple bean exists | Check whether another `MeterRegistry` bean caused the fallback condition not to match |
| Cannot reach `/actuator/prometheus` | Check registry, endpoint, exposure, port/path, and access permissions layer by layer |
| Changed configuration but process keeps old registry | Check whether the application recreated its context or restarted |

For standard Spring Boot applications, start with `--debug` to view the conditions evaluation report and see which auto-configuration branches matched. If inspecting via the `conditions` endpoint, that endpoint must be appropriately exposed and secured. Start from effective configuration and actual beans before checking data at the destination.

## 9. Self-Check

1. Shared default `false`, Prometheus `true`, library and conditions met: is Prometheus allowed to auto-configure?
2. Shared default `true`, Datadog `false`: which value does Datadog follow?
3. No other registry present, both Simple and shared default unset: what acts as the fallback measurement store?
4. Shared default `false`, no per-system flag enabled and no manually declared registry: can `MeterRegistry` still be injected? Does it retain counts in the experiment?
5. Why does `simple=true` not guarantee Simple coexists with Prometheus?
6. Why is disabling HTTP exposure insufficient to stop a registry from sending data to an external service?

Answers: (1) Yes, the per-system flag overrides the shared default, though remaining conditions must still be satisfied. (2) `false`. (3) Simple. (4) An empty composite can still exist thanks to no-op configuration; counts in the experiment remain `0.0`. (5) Simple also requires no other `MeterRegistry` bean to exist. (6) Exposure controls endpoint access paths; registry destinations and lifecycles belong to a different configuration layer.
