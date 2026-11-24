# Distinguishing Auto-Collected Metrics From Measurements Requiring Configuration or Extra Libraries

## 1. "Having Actuator" Does Not Yet Answer "What Is Being Measured?"

When you add Actuator, many metric names appear before you write a single line of instrumentation code. That easily leads to two misunderstandings: every operation in the app is already measured, or merely exposing an endpoint will make missing numbers appear.

To read a system accurately, determine **what produces the measurement, which boundary it observes, and what conditions make that integration active**. Some infrastructure indicators are registered automatically by Spring Boot; some integrations activate only when matching libraries and beans exist; and some business questions require the application itself to define measurements.

This lesson uses **Spring Boot 3.3.x, Micrometer 1.13.x, and Java 17+** as its scope. Examples run on JDK 21 and pin Boot 3.3.0 to keep the lab environment deterministic. When using another version line, consult that line's documentation instead of carrying over property names or auto-configuration conditions verbatim.

Key terms used in this lesson:

| Term | Meaning in the Measurement Pipeline |
| --- | --- |
| Instrumentation | Code or integration that actually observes events/state |
| Meter | Micrometer measurement object, such as a Timer, Counter, or Gauge |
| MeterRegistry | Where meters are registered and connected to storage/export mechanisms |
| Binder | Component binding a resource's set of measurements to a registry |
| Endpoint | Interface for reading application information over HTTP/JMX |
| Monitoring backend | External system collecting, storing history, and querying metrics |

Auto-configuration typically wires supported components together. It does not automatically know what "valid order," "successful payment," or "one processed file" means in your business domain.

## 2. Separate the Stages Before Hunting for Missing Metrics

```text
A resource or event needs observation
    → Matching instrumentation exists
    → Meter is registered in the active registry
    → Measurement samples/state exist to read
    → A read or export path exists
    → An external system scrapes and stores history if needed
```

Stages are related yet do not substitute for one another:

- **Collection/recording:** an HTTP call completes, JVM memory changes, or application code records a Timer.
- **Registration:** the meter appears in the registry with a specific name, type, and tag set.
- **Endpoint exposure:** a management interface is allowed to be accessed over HTTP/JMX.
- **Export and storage:** using the corresponding registry/exporter and configuring a monitoring backend to receive data.

Therefore, an unexposed `metrics` endpoint does not prove the JVM is unmeasured. Conversely, an accessible endpoint does not prove measurements exist for every service method. A counter at 0, a nonexistent meter, and an HTTP access denial are three distinct situations.

In Boot 3.3, endpoints have separate enable/exposure rules; by default only `health` is exposed over HTTP. Changing exposure addresses only that access path. See [Boot 3.3 endpoint rules](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.exposing).

## 3. Understand "Automatic" as "Automatic When Conditions Are Met"

When evaluating a metric, place it in the right category:

| Category | How It Appears | Example Question to Check |
| --- | --- | --- |
| Built-in integration, usual conditions already met | Boot registers when initializing a matching environment | Does the registry already have JVM memory metrics? |
| Built-in integration, depends on technology/beans | Appears only when the app uses a supported resource | Is there a suitable DataSource/pool or executor? |
| Built-in integration, requires enabling a specific setting | Must enable the technology's setting or build objects the right way | Is Tomcat MBean registry enabled? |
| Requires extra module/exporter | A dependency supplies the missing integration piece | Are the Hibernate metrics library or Prometheus registry present? |
| Requires application-defined measurement | Business code or custom instrumentation defines the boundary | Where is a "successful order" actually determined? |

Categories can combine. Hibernate is an example needing both a matching metrics module and enabled statistics. Prometheus requires the matching registry, an exposed scrape endpoint, and a Prometheus server actually scraping. Do not classify a technology using a single binary "automatic yes/no" box.

### Cases Commonly Integrated Out of the Box

| Scope | Common Names/Groups | What Must Not Be Inferred From the Name |
| --- | --- | --- |
| JVM | `jvm.memory.used`, `jvm.threads.*`, `jvm.gc.*` | Not every metric exists on every JVM/GC |
| Process, system | `process.*`, `system.*`, `disk.*` | Read capability depends on OS and runtime environment |
| Integrated HTTP server | `http.server.requests` | Does not mean every business step inside a request is measured separately |
| Supported executors/schedulers | `executor.*` | Does not cover arbitrary `Executor` objects created manually anywhere |
| Supported connection pools | `jdbc.connections.*`, pool-specific metrics when present | Not individual SQL statement execution times |

The JVM has binders for memory, GC, classes, and threads; the actual list of meters depends on process resources. See [Micrometer 1.13 JVM binders](https://docs.micrometer.io/micrometer/reference/1.13/reference/jvm.html).

For executors in Boot 3.3, the standard integration path is `ThreadPoolTaskExecutor`/`ThreadPoolTaskScheduler` beans backed by a suitable `ThreadPoolExecutor`. A local variable holding a manually created pool is no proof that pool is bound. See [TaskExecutorMetricsAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/metrics/task/TaskExecutorMetricsAutoConfiguration.html).

For DataSources, reading pool attributes requires supported metadata/providers. Measurements of borrowed or idle connections do not automatically become query latency measurements. See [DataSource pool metadata providers configuration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jdbc/metadata/DataSourcePoolMetadataProvidersConfiguration.html).

Cross-check specific metric names and integrations in [Boot 3.3 Supported Metrics and Meters](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.supported). Do not treat that table as a guarantee that every meter appears immediately upon startup; event-driven Timers often appear only after the corresponding execution path runs.

## 4. Conditions Easily Overlooked

### 4.1. Tomcat: Having HTTP Metrics Does Not Mean Having All Tomcat Metrics

In Boot 3.3, the `tomcat.*` group requires Tomcat's MBean registry to be enabled. Example setting:

```properties
server.tomcat.mbeanregistry.enabled=true
```

This condition is specific to the Tomcat group; do not use it as a generic fix for missing `http.server.requests`. HTTP request observation and internal container statistics observe different scopes. Apply this setting only when the application actually runs Tomcat.

### 4.2. Hibernate: Requires Both Metrics Module and Statistics

In a Boot 3.3 project using JPA/Hibernate, add the BOM-managed dependency:

```groovy
implementation 'org.hibernate.orm:hibernate-micrometer'
```

At the same time, enable statistics on the corresponding `EntityManagerFactory`:

```properties
spring.jpa.properties.hibernate.generate_statistics=true
```

Having `spring-boot-starter-data-jpa` alone is insufficient to assume the `hibernate.*` group is ready. Adding the dependency without enabling statistics also misses a precondition. Connection pool metrics, repository invocations, and ORM statistics are distinct observation angles.

The Tomcat and Hibernate conditions above are documented in [Boot 3.3 metrics integration](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html). Do not enable every statistic just to fill every panel on a dashboard; choose what needs observing and weigh the overhead of that setting.

### 4.3. Cache: Also Depends on Cache Type, Statistics, and Creation Timing

Having a cache manager does not prove every cache has metrics. You need a compatible provider/binder, library statistics enabled where required, and caches bound to the registry. In Boot 3.3, caches configured at startup follow the standard auto-binding path; caches created dynamically later need explicit registration.

Boot provides `CacheMetricsRegistrar.bindCacheToRegistry(...)` for explicit registration. Its boolean return indicates whether the cache is supported and bound successfully; do not call it and ignore the result. See [CacheMetricsRegistrar API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/metrics/cache/CacheMetricsRegistrar.html).

Check the exact cache implementation before adding configuration. A property name enabling statistics for one provider is not a universal contract for every cache library.

### 4.4. HTTP Clients: Construct Objects via the Configured Path

To receive Boot's integration, use injected builders such as `RestTemplateBuilder`, `RestClient.Builder`, or `WebClient.Builder` per client type. Objects created directly via constructors or static factories without applying observation customizers can bypass that integration.

Example configuration snippet in an app already having Spring Web:

```java
@Bean
RestClient downstreamClient(RestClient.Builder builder) {
    return builder.build();
}
```

This is a configuration fragment requiring imports for `org.springframework.context.annotation.Bean` and `org.springframework.web.client.RestClient`; it is not a standalone program. "Having an HTTP library on the classpath" and "the object sending requests is instrumented" are two separate checks.

## 5. Runnable Example: Three Distinct Origins of Meters

The following project uses JDK 21 and Gradle 8.5. First dependency resolution needs Maven Central; Gradle must be installed or a compatible wrapper included in the project. The example uses the `application` plugin, so the run task is `run`.

```text
metrics-boundary-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/
    │   ├── MetricsBoundaryApplication.java
    │   └── DemoController.java
    └── resources/application.properties
```

**`settings.gradle`**

```groovy
rootProject.name = 'metrics-boundary-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

application {
    mainClass = 'demo.MetricsBoundaryApplication'
}
```

**`src/main/resources/application.properties`**

```properties
management.endpoints.web.exposure.include=health,metrics
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=OFF
```

**`src/main/java/demo/MetricsBoundaryApplication.java`**

```java
package demo;

import io.micrometer.core.annotation.Timed;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class MetricsBoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(MetricsBoundaryApplication.class, args);
    }

    @Bean
    PricingService pricingService() {
        return new PricingService();
    }

    @Bean
    ApplicationRunner experiment(PricingService pricing, MeterRegistry registry) {
        return args -> {
            pricing.calculate(2);
            boolean annotationMeterPresent =
                    registry.find("demo.price.calculate").timer() != null;

            Timer duration = Timer.builder("demo.price.duration")
                    .description("Duration of explicit price calculations")
                    .tag("operation", "calculate")
                    .register(registry);

            duration.record(() -> { pricing.calculate(2); });
            duration.record(() -> { pricing.calculate(3); });

            boolean jvmMeterPresent =
                    !registry.find("jvm.memory.used").gauges().isEmpty();

            System.out.println("JVM_MEMORY_PRESENT=" + jvmMeterPresent);
            System.out.println("ANNOTATION_ONLY_PRESENT=" + annotationMeterPresent);
            System.out.println("MANUAL_DURATION_COUNT=" + duration.count());
        };
    }

    public static class PricingService {
        @Timed("demo.price.calculate")
        public int calculate(int quantity) {
            return Math.multiplyExact(quantity, 100);
        }
    }
}
```

**`src/main/java/demo/DemoController.java`**

```java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {
    @GetMapping("/demo/ping")
    public String ping() {
        return "ok";
    }
}
```

Run the first time without starting a web server to verify the registry and measurements in isolation:

```shell
gradle --console=plain run --args="--spring.main.web-application-type=none"
```

The three lines printed by the application are:

```text
JVM_MEMORY_PRESENT=true
ANNOTATION_ONLY_PRESENT=false
MANUAL_DURATION_COUNT=2
```

Gradle may print extra task output; the three lines above are the experiment's stdout. There is no fixed duration in the output because execution speed depends on the machine and JVM.

Explaining each line:

1. **JVM_MEMORY_PRESENT=true:** the app never calls memory binders itself, yet Boot registered JVM meters via auto-configuration.
2. **ANNOTATION_ONLY_PRESENT=false:** `PricingService` is a bean and was called, yet the initial dependencies/configuration lacked an AOP mechanism processing `@Timed` on arbitrary services. An annotation alone does not execute measurement.
3. **MANUAL_DURATION_COUNT=2:** two code blocks wrapped with `Timer.record(...)` were recorded explicitly. `calculate` ran three times in total, yet this Timer wraps only two of them.

Thus, "a method ran three times" does not automatically imply "every related timer has count three." You must check where the measurement is recorded.

`registry.find(...)` only looks up already registered meters. Using `registry.timer("name-to-check")` to test whether a meter exists can create a brand-new Timer yourself, making the check no longer prove the integration created it.

The example omits a database, Prometheus, or an external monitoring server. Those components are not prerequisites to observe the fundamental difference between automatic binders, unprocessed annotations, and explicit measurement.

## 6. Opening HTTP to Observe Automatic Web Measurements

Rerun the application in default web mode:

```shell
gradle --console=plain run
```

The application keeps the web server running. Open another terminal and trigger events:

```shell
curl http://localhost:8080/demo/ping
curl http://localhost:8080/actuator/metrics
```

Calling `/demo/ping` returns `ok`. On Windows PowerShell, use `curl.exe` if `curl` is an alias. Inspect the request group for the specific route just called:

```shell
curl --get http://localhost:8080/actuator/metrics/http.server.requests --data-urlencode "tag=uri:/demo/ping"
curl http://localhost:8080/actuator/metrics/demo.price.duration
```

In a fresh process with just one `/demo/ping` call, look for the `COUNT` statistic of the request with that URI tag. The manual timer `demo.price.duration` still has two recordings from the runner, because the ping controller does not record into that Timer.

Actuator requests themselves can also generate HTTP metrics. Therefore, do not take an unfiltered `http.server.requests` total and attribute all of it to a single business endpoint. Use `availableTags` to inspect real tag values when diagnosing.

The endpoint accepts original Micrometer names like `http.server.requests`; display names after backend transformation may differ. The `metrics` endpoint serves diagnostics of recorded meters, not a historical store to scrape instead of a backend. See [Boot 3.3 metrics REST API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html).

If running in an environment with a changed management port, base path, or Spring Security, use the matching address and credentials. A 401/403 response is insufficient to conclude instrumentation is missing. The practice example omits production security configuration.

## 7. Adding @Timed Processing and Comparing Before and After

For `@Timed` on the example's service to be processed by Spring AOP, add the following dependency to the same `dependencies` block:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-aop'
```

Also create **`src/main/java/demo/TimingConfiguration.java`**:

```java
package demo;

import io.micrometer.core.aop.TimedAspect;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class TimingConfiguration {
    @Bean
    TimedAspect timedAspect(MeterRegistry registry) {
        return new TimedAspect(registry);
    }
}
```

Then rerun without a web server using the command from Section 5. The initial three lines change to:

```text
JVM_MEMORY_PRESENT=true
ANNOTATION_ONLY_PRESENT=true
MANUAL_DURATION_COUNT=2
```

Now the `demo.price.calculate` meter exists after the first call. By the time the runner finishes, the annotation has observed **three** `calculate` calls: one direct call earlier and two inside the `Timer.record` blocks. The manual Timer still counts **two**.

To verify further right at the end of the runner, you can add this diagnostic line:

```java
System.out.println("ANNOTATED_TIMER_COUNT=" + registry.get("demo.price.calculate").timer().count());
```

In this aspect-enabled variant, the added line prints `ANNOTATED_TIMER_COUNT=3`. These are two differently named meters measuring chosen scopes; do not sum both counts and claim five price calculations occurred.

Micrometer provides `TimedAspect` to handle the annotation via AOP. With Spring AOP, calls must pass through the proper proxy; manual `new` instantiation, `this` self-invocation, or unproxiable class/method structures all need checking. Specialized integrations may support annotations via their own mechanisms, so do not generalize repository annotation behavior to arbitrary services. See [Micrometer 1.13 TimedAspect mechanism](https://docs.micrometer.io/micrometer/reference/1.13/concepts/timers.html#_the_timed_annotation).

In production code, pick measurement boundaries based on the question you need answered. If two mechanisms time the same operation for the same purpose, avoid double-recording or naming/interpreting them in ways that tempt readers to sum duplicate events.

## 8. Prometheus Is an Addition for the Export Path

The initial lab did not need Prometheus to have meters. When you want Prometheus to scrape the application, add the corresponding registry to the project:

```groovy
implementation 'io.micrometer:micrometer-registry-prometheus'
```

Expose the scrape endpoint alongside active endpoints:

```properties
management.endpoints.web.exposure.include=health,metrics,prometheus
```

Run the app in web mode and check:

```shell
curl http://localhost:8080/actuator/prometheus
```

Distinguish three things: the dependency supplies the registry/exporter, the endpoint serves data for scraping, and the Prometheus server has a target configured to actually scrape. Simply writing `prometheus` in exposure does not install the registry. An endpoint returning data does not set up a historical storage server either.

Meter names may be converted to Prometheus conventions, and a Timer can emit multiple statistical series. When searching for a metric in the backend, check the actual exported name instead of passing transformed names to `/actuator/metrics/{name}`. See [Micrometer 1.13 Prometheus integration](https://docs.micrometer.io/micrometer/reference/1.13/implementations/prometheus.html).

Likewise, having an auto-configured registry does not mean every backend already has credentials, endpoints, and permissions to receive data. Connection/export settings for any backend must be verified for that backend.

## 9. Having a Timer Does Not Mean Having Every Desired Statistic

A basic Timer supplies event count and total time; distribution statistics depend on configuration and registry/backend support. If a dashboard wants histograms or latency SLO buckets, that is an additional configuration requirement, not a reason to time the same request again with a second Timer.

Example additional configuration for supported HTTP timers:

```properties
management.metrics.distribution.percentiles-histogram.http.server.requests=true
management.metrics.distribution.slo.http.server.requests=100ms,300ms,1s
```

These lines configure statistics for an existing measurement; they do not generate requests, add a Prometheus registry, or replace scrape setup. Nor will the `metrics` endpoint JSON turn into a full histogram; inspect distribution data in an exporter/backend that supports it.

Meter filters can also deny registration, rename metrics/tags, or alter statistics. Hence, a meter missing even though instrumentation ran can involve a filter. See [Micrometer 1.13 MeterFilter](https://docs.micrometer.io/micrometer/reference/1.13/concepts/meter-filters.html).

Every tag value combination can multiply metric series. Choose tags with bounded value sets and stable meaning, such as operation type; never put order IDs, email addresses, or free-form error messages into tags just to look up one execution. Histograms multiply series further, so weigh scope and tag cardinality together.

## 10. Metrics, Observation, and Tracing Are Related Yet Not Interchangeable

Instrumentation can use Micrometer Observation to produce data for metrics and, with tracing infrastructure present, for traces. That does not mean an arbitrary manual Timer automatically generates traces, or that merely adding Actuator sends traces to a backend.

Check separately: is an observation created, which handlers process it, is tracing integration present, and does an exporter connect to a backend? Low-variance values suit metric tags; high-cardinality details like individual request identity must be handled via appropriate mechanisms and data policies. See [Observability in Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

Time boundaries must also be defined. The lesson's example is synchronous computation; `Timer.record` wraps an immediately executing block. If the block merely submits async work and returns, timing that block does not automatically become task completion time. With reactive chains, inspect subscription execution and termination signals rather than only publisher creation time.

Similarly, JDBC pool metrics do not contain individual SQL durations. When you need JDBC/R2DBC observation at a different layer, pick the matching integration, verify its dependencies and supported boundaries; do not infer that coverage from already having connection counts.

## 11. Diagnose by Evidence Instead of Adding Dependencies Blindly

| Symptom | What to Check First | Appropriate Verification |
| --- | --- | --- |
| No meter in registry | Auto-configuration conditions, beans/libraries, filters, instrumentation code | Query registry and trigger one controlled event |
| Meter exists, yet zero events | Has the code path actually run and finished? | Compare before/after around one operation |
| Meter in app, yet unreadable via HTTP | Enable/exposure, address, management port, authorization | Check endpoint config and HTTP response |
| HTTP client has no metrics | Did the active client receive observation customization? | Inspect client creation site and use injected builder |
| Specific cache/pool has no metrics | Resource type, binder/provider, stats toggle, creation timing | Verify concrete resource and bind capability |
| Meter in Actuator, yet backend empty | Registry/exporter, connectivity, scrape target, query name/tags | Compare exported output and backend config |
| Count larger than expected | Multiple call paths, runners/background jobs, multiple tags, or double counting | Filter exact tags, compare before/after deltas |

You can enable the auto-configuration condition report during diagnostics, such as running with `--debug`. The report explains which conditions failed to match; it does not replace verifying samples after an actual invocation. Because the example silenced logs for clean stdout, remove `logging.level.root=OFF` when diagnostic logs are needed.

Avoid two noisy workarounds: exposing every endpoint to hunt for an uncreated Timer, or creating a dummy meter with the same name just to make it show up in the list. Neither proves the original integration path actually works.

## 12. Practice Exercises to Test Differentiation

Run each scenario on a fresh startup so configurations or counts from prior runs do not mix:

1. **Keep the initial setup:** explain why the JVM meter is present, the annotation meter is absent, and the manual Timer has count 2 even though the method ran three times.
2. **Remove metrics from exposure:** confirm the three registry lines in non-web mode stay unchanged; in web mode, distinguish endpoint access from meters already registered.
3. **Add AOP starter with TimedAspect:** confirm the annotation meter is created and counts three calls, while the manual Timer still counts two.
4. **Add only prometheus to exposure without the registry:** explain why naming an endpoint in config does not supply a missing library/exporter. After adding the registry, check the scrape endpoint and Prometheus server target separately.
5. **Suppose you want to know successful checkout counts:** identify where business completion truly happens and propose a bounded measurement/tag set. Do not use total HTTP 2xx or pool connection counts to substitute for that business definition.

When evaluating any metric, state the version, measurement source, activation conditions, observed boundary, and read/export path. Those details explain why an indicator appears automatically in one environment yet requires extra configuration or libraries in another.
