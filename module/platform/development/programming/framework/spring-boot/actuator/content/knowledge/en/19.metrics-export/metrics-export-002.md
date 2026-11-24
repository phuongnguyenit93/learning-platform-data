# Choosing the Right MeterRegistry for Your Monitoring System

The same `orders.completed` counter can be scraped by Prometheus over HTTP, sent to an OpenTelemetry Collector, or kept only in memory for testing. Business code records once against the Micrometer API. The registry determines what format measurements are converted into and where they go.

## Start from the Destination

Before choosing a dependency, determine which system will store and query the metrics, which party initiates the connection, and what protocol or authentication credentials that endpoint requires.

| Infrastructure in Use | Micrometer Registry | How Data Reaches the Destination |
| --- | --- | --- |
| Prometheus scraping each application instance | `micrometer-registry-prometheus` | Prometheus actively calls the exposed `/actuator/prometheus` endpoint. This is the pull model. |
| OpenTelemetry Collector or OTLP-compatible HTTP receiver | `micrometer-registry-otlp` | The application periodically sends metrics to an OTLP HTTP URL, typically with path `/v1/metrics`. This is the push model. |
| Datadog ingesting directly via its metrics API | `micrometer-registry-datadog` | The registry periodically sends metrics to the Datadog API. Configure the API key and URI matching your data storage region. |
| Testing or inspecting measurements locally | `SimpleMeterRegistry` | Measurements stay in process memory. They can be read via the Micrometer API or the Actuator `metrics` endpoint when exposed. |

For example, if a Collector is the shared ingress for your system, use OTLP so the application sends to the Collector and the Collector routes to the backend. If the operations team already scrapes each instance with Prometheus, use the Prometheus registry and keep the scrape target in Prometheus configuration. For a short-lived process, review whether collection can occur before the process exits, for both scrape intervals and periodic export intervals.

## Matching Dependencies and Configuration in Spring Boot 3.3

Use `spring-boot-starter-actuator` and Spring Boot's dependency management. The Gradle lines below are **options** for the `dependencies` block. Enable multiple simultaneously only when you genuinely need to export to multiple destinations.

### Prometheus Pulling Data

~~~groovy
runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
~~~

~~~properties
management.endpoints.web.exposure.include=health,prometheus
~~~

Spring Boot can auto-configure the registry when the dependency is present at runtime. Exposing the endpoint allows Prometheus to scrape measurements at `/actuator/prometheus` when using the default management path. Verify that Prometheus can reach the management port and configure the scrape job for each target properly. `/actuator/metrics` serves ad-hoc inspection via Actuator. For scraping, use the `prometheus` endpoint.

### OpenTelemetry Collector Receiving Metrics

~~~groovy
runtimeOnly 'io.micrometer:micrometer-registry-otlp'
~~~

~~~properties
management.otlp.metrics.export.url=http://otel-collector:4318/v1/metrics
management.otlp.metrics.export.step=30s
~~~

The example assumes `otel-collector` resolves within the application's network and the Collector has enabled the OTLP HTTP receiver for the metrics pipeline. `step` is the export interval. If the receiver requires authentication, configure the corresponding headers via `management.otlp.metrics.export.headers.*` and supply values from environment secrets. Use an HTTPS URL when the receiver requires TLS. When switching backends, check whether the receiver expects `cumulative` or `delta` aggregation temporality.

### Datadog Receiving Directly via API

~~~groovy
runtimeOnly 'io.micrometer:micrometer-registry-datadog'
~~~

~~~properties
management.datadog.metrics.export.api-key=${DATADOG_API_KEY}
~~~

Supply `DATADOG_API_KEY` to the process from a secret store. If you use a non-default Datadog site or route through a proxy, set `management.datadog.metrics.export.uri` according to your infrastructure address. Check the right site and wait at least one export interval before concluding that data has not arrived.

## A Single Write Can Flow Through Multiple Registries

Applications should inject `MeterRegistry` via the constructor and register `Counter`, `Timer`, or `Gauge` instances with it. When multiple auto-configured registries are active, Spring Boot can provide a `CompositeMeterRegistry` to distribute a single write to its child registries. Spring Boot uses a simple in-memory registry as a fallback when no other backend is configured.

When migrating monitoring systems, you can enable both the old and new registries during a comparison phase. If both pipelines send data to the same store, check for double-counting risk. When the migration finishes, you can disable the old registry with its dedicated flag. For example, `management.datadog.metrics.export.enabled=false` disables the Spring Boot auto-configured Datadog registry. If configuring multiple profiles with the same classpath, check the enable and disable flags in the profiles actually loaded.

### Testing Distribution in Java

A standalone example using two in-memory registries to observe the effect of a single write. Create `build.gradle` in a test directory:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.micrometer:micrometer-core:1.13.0'
}

application {
    mainClass = 'example.RegistryDemo'
}
~~~

Create `src/main/java/example/RegistryDemo.java`:

~~~java
package example;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.composite.CompositeMeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public class RegistryDemo {
    public static void main(String[] args) {
        var composite = new CompositeMeterRegistry();
        var first = new SimpleMeterRegistry();
        var second = new SimpleMeterRegistry();
        try {
            Counter completed = composite.counter("orders.completed");
            composite.add(first);
            completed.increment();

            composite.add(second);
            completed.increment();

            System.out.println("first=" + first.get("orders.completed").counter().count());
            System.out.println("second=" + second.get("orders.completed").counter().count());
        } finally {
            composite.close();
        }
    }
}
~~~

With JDK 17 or higher and a compatible Gradle version, run `gradle -q run`. Output:

~~~text
first=2.0
second=1.0
~~~

The first registry was present for both increments. The second registry was present starting from the second increment. When adding a child registry, the composite registers already-known meters with the new registry. Earlier writes exist only in the registries that received them.

## Verify Where Measurements Will Be Used

1. Trigger a repeatable operation, such as completing a test order to increment the counter once.
2. For Prometheus, locate the metric at the endpoint and then check the scrape target and queries in Prometheus. For OTLP or Datadog, verify the send path, export interval, and data at the Collector or target backend. Reading the measurement locally only confirms the recording step.
3. When switching registries, compare metric names, timer units, tags, histogram buckets, and rate-calculation semantics in the new backend. The same meter in code may appear with a different name or representation due to each system's conventions.

### References

- [Spring Boot 3.3 – Micrometer and Registry Auto-Configuration](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
- [Micrometer 1.13 – Prometheus Registry](https://docs.micrometer.io/micrometer/reference/1.13/implementations/prometheus.html)
- [Micrometer 1.13 – OTLP Registry](https://docs.micrometer.io/micrometer/reference/1.13/implementations/otlp.html)