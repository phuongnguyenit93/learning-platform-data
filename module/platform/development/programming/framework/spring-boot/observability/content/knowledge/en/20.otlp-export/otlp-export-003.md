# OTLP Metrics in Spring Boot

Spring Boot can export metrics collected by Micrometer to observability systems that support the OpenTelemetry Protocol (OTLP). This integration sends Counter, Timer, Gauge, and distribution measurements over a vendor-neutral protocol, typically through an OpenTelemetry Collector to a metrics backend.

The **"OTLP Metrics"** lesson belongs to the **OTLP export** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module teaches how to set up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; covering context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production environments.

**Key takeaway:** in Spring Boot's standard metrics integration, Micrometer manages metric instruments and `OtlpMeterRegistry` converts and exports them via OTLP. This is a metrics pipeline, separate from exporting spans and logs with OpenTelemetry.

## 1. What Are OTLP Metrics?

OTLP is the telemetry transmission protocol between applications, collectors, and backends. For metrics, an OTLP payload contains resource, scope/instrumentation metadata, and metric data points, rather than just plain text lines like Prometheus exposition.

```mermaid
flowchart LR
    A["Spring Boot application"] --> B["Micrometer meters"]
    B --> C["OtlpMeterRegistry"]
    C --> D["OTLP/HTTP metrics"]
    D --> E["OpenTelemetry Collector"]
    E --> F["Metrics backend"]
    F --> G["Query, dashboard, alerts"]
```

| Component | Role |
| --- | --- |
| Micrometer `MeterRegistry` | Manages Counter, Timer, Gauge, tags, and measurements |
| `OtlpMeterRegistry` | Converts meter data into OTLP metrics and publishes periodically |
| OTLP receiver | Accepts metrics payloads over OTLP |
| OpenTelemetry Collector | Receives, processes, batches, routes, and exports telemetry |
| Metrics backend | Storage, querying, and alerting |
| Dashboard | Displays SLIs, trends, and operational health |

**OTLP is not a metrics database.** Configuring only the sending endpoint does not create storage or dashboards. The receiver and downstream backend must be deployed and configured separately.

## 2. Spring Boot Uses Micrometer to Export Metrics via OTLP

Spring Boot chooses Micrometer as its metrics abstraction. When the OTLP registry dependency is on the runtime classpath, auto-configuration can create an `OtlpMeterRegistry` and bind settings from the `management.otlp.metrics.export` namespace.

This has an important consequence: metrics collected by Spring Boot/Micrometer **do not flow through OpenTelemetry `SdkMeterProvider` by default**. If a third-party dependency creates its own OpenTelemetry `MeterProvider`, metrics from that dependency are not automatically exported by the Micrometer registry. Separate provider configuration and wiring are needed if you want to export them.

For a typical Spring Boot application, instrument metrics with Micrometer:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Service;

@Service
public class CheckoutMetrics {
    private final Counter accepted;

    public CheckoutMetrics(MeterRegistry registry) {
        this.accepted = Counter.builder("checkout.accepted")
                .description("Accepted checkout attempts")
                .tag("channel", "web")
                .register(registry);
    }

    public void recordAccepted() {
        accepted.increment();
    }
}
```

When the active registry is `OtlpMeterRegistry`, this meter is exported over OTLP according to the publish schedule. Business code does not need to know the specific receiver or backend.

Spring Boot documentation explains the Micrometer choice and OTLP metrics at [Observability — Metrics](https://docs.spring.io/spring-boot/reference/actuator/observability.html).

## 3. Adding the OTLP Registry Dependency

With Gradle Groovy and Spring Boot dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-otlp'
}
```

Some projects using an umbrella observability starter may already pull the OTLP registry into runtime. Before adding the dependency, check dependency management configuration to avoid duplicate declarations or overriding with incompatible versions.

With Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-otlp</artifactId>
    <scope>runtime</scope>
</dependency>
```

Do not pick a `micrometer-registry-otlp` version outside the Spring Boot BOM without checking the compatibility matrix.

## 4. Configuring the OTLP Endpoint

Spring Boot supports the following property:

```yaml
management:
  otlp:
    metrics:
      export:
        url: http://localhost:4318/v1/metrics
```

The `/v1/metrics` path is the standard OTLP/HTTP metrics endpoint. If the Collector runs in another container, replace `localhost` with a hostname reachable from the application, such as `otel-collector`. Inside a container, `localhost` typically points to the application container itself.

Example local configuration:

```yaml
spring:
  application:
    name: checkout-service

management:
  otlp:
    metrics:
      export:
        url: http://localhost:4318/v1/metrics
        step: 30s
        aggregation-temporality: cumulative
        compression-mode: gzip
```

Properties must match your project's Spring Boot/Micrometer release line. Current configurations offer options such as `url`, `step`, `aggregation-temporality`, `compression-mode`, `batch-size`, `headers`, `resource-attributes`, and timeouts. See [Spring Boot Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/) and [Micrometer OTLP registry](https://docs.micrometer.io/micrometer/reference/implementations/otlp.html).

### URL and Protocol

| Endpoint | Meaning |
| --- | --- |
| `http://localhost:4318/v1/metrics` | Local OTLP/HTTP metrics receiver |
| `https://otlp.example.com:4318/v1/metrics` | OTLP/HTTP over TLS |
| `localhost:4317` | Usually an OTLP/gRPC receiver, not an HTTP `/v1/metrics` URL |

Do not change ports or paths arbitrarily. The receiver must enable the matching protocol, and the registry sender must use the corresponding protocol. Micrometer's standard `OtlpMeterRegistry` typically uses an HTTP sender; another transport requires an appropriate sender implementation.

## 5. Publish Interval, Batch, and Timeouts

`step` is the interval at which the registry publishes metrics:

```yaml
management:
  otlp:
    metrics:
      export:
        step: 30s
        batch-size: 10000
        connect-timeout: 1s
        read-timeout: 10s
```

- **step:** the publish/aggregation interval of the registry. Shorter intervals make data fresher but typically increase send frequency.
- **batch-size:** number of meters/measurements grouped into a payload per registry configuration; exceeding it can generate multiple requests.
- **connect-timeout:** time limit for establishing a connection.
- **read-timeout:** time limit for waiting for a response from the receiver.

These are starting examples, not production sizing. Measure meter count, payload size, network latency, and ingest capacity. Do not choose a tiny `step` solely to make dashboards look instantaneously updated.

### Export Interval Differs From Scrape Interval

With Prometheus pull, the scraper decides when to sample the endpoint. With OTLP push, the registry proactively publishes on the `step` cadence. Data also needs time for instrumentation, aggregation, transport, ingestion, and querying; it does not necessarily appear the instant a Counter increments.

## 6. Aggregation Temporality: Cumulative and Delta

OTLP supports two common temporalities:

- **Cumulative:** accumulated value since the start of the aggregation stream.
- **Delta:** newly accrued value within a single time interval, independent of prior intervals.

Example of a Counter incrementing 12 times in interval A and 8 more times in interval B:

| Interval | Cumulative | Delta |
| --- | ---: | ---: |
| A | 12 | 12 |
| B | 20 | 8 |

The backend must understand temporality to compute rates, aggregations, and resets accurately. A backend supporting only one temporality may reject or misprocess the other.

Configuring cumulative:

```yaml
management:
  otlp:
    metrics:
      export:
        aggregation-temporality: cumulative
```

The current Micrometer OTLP registry typically defaults to cumulative, though this should be verified by version. Registry configuration, environment variables, and backend capabilities all affect behavior. Do not switch between delta and cumulative without checking both sides.

### Resets and Restarts

Cumulative series require reset handling when a process restarts or meter state resets. Delta streams represent per-interval increments, yet the backend still needs to understand start timestamps and corresponding semantics. If the backend receives the wrong temporality, rates can spike, drop, or double.

When changing temporality in production, treat it as a data contract change: test queries, alerts, dashboards, and aggregations before rollout.

## 7. Resource Attributes and Service Identity

OTLP metrics attach to a **Resource** describing the entity generating the data, such as service name, deployment environment, and region.

Example:

```yaml
management:
  otlp:
    metrics:
      export:
        resource-attributes:
          service.name: checkout-service
          deployment.environment: production
          cloud.region: ap-southeast-1
```

Property names and resource attribute binding depend on the registry/Spring Boot version. Micrometer's OTLP registry also supports resource attributes from OpenTelemetry environment variables such as `OTEL_RESOURCE_ATTRIBUTES` and `OTEL_SERVICE_NAME` by default.

Resource attributes commonly include fields like `telemetry.sdk.name`, `telemetry.sdk.language`, `telemetry.sdk.version`, and `service.name`. If `service.name` is misconfigured, data may appear under `unknown_service`. Verify resource attributes in the backend rather than assuming YAML loaded properly.

### Resource Attributes Differ From Meter Tags

| Resource attribute | Meter tag |
| --- | --- |
| Describes the source/instance/service emitting telemetry | Categorizes a single meter |
| Applies to the group of metrics from the resource | Can vary per meter |
| Example: `service.name` | Example: `payment.method` |
| Groups by service/environment | Dimension of each series |

Do not duplicate metadata into both resource and every meter tag unless the backend requires it; doing so can complicate queries or increase cardinality.

## 8. Headers and Authentication

An OTLP receiver may require an authorization header. Spring Boot allows configuring custom headers under the `management.otlp.metrics.export.headers` namespace.

Syntax example:

```yaml
management:
  otlp:
    metrics:
      export:
        url: https://otlp.example.com/v1/metrics
        headers:
          Authorization: Bearer token-managed-outside-source
```

This is an illustrative value; do not commit real tokens to the repository. Use a secret manager, Kubernetes Secret, or your platform's credential management mechanism. Confirm the header name and auth format expected by the receiver.

Protect the transport with TLS; issue tokens with only the required ingest permissions; set up rotation/expiry; do not print sensitive headers to logs; and use tenant/project scoping if supported by the backend.

## 9. Compression and Payload Size

OTLP payloads can grow large when there are many meters, tags, or histogram buckets. Gzip can reduce transmitted bytes but increases CPU and processing cost.

```yaml
management:
  otlp:
    metrics:
      export:
        compression-mode: gzip
        batch-size: 5000
```

Measure active meters, data points per export, payload size before/after compression, CPU, network throughput, and error rates from payloads exceeding receiver limits.

Smaller batches can reduce individual request sizes but increase request count; larger batches reduce overhead but can increase memory usage and the risk of oversized payloads. Choose based on receiver and workload.

## 10. How Micrometer Meter Types Map to OTLP

| Micrometer meter | Common OTLP data point |
| --- | --- |
| Counter, FunctionCounter | Sum |
| Gauge, TimeGauge, MultiGauge | Gauge |
| Timer | Histogram or Summary depending on configuration |
| DistributionSummary | Histogram or Summary |
| LongTaskTimer | Mapping depends on implementation |
| FunctionTimer | Sum/count per registry support |

OTLP has Sums, Gauges, Histograms, Exponential Histograms, and Summaries. Mapping details belong to the Micrometer registry version. Do not assume every Meter type contains every statistical field; some mappings export only count/sum.

See [Micrometer OTLP](https://docs.micrometer.io/micrometer/reference/implementations/otlp.html) for version-specific mappings and limitations.

## 11. Histograms, Percentiles, and SLOs

To query latency percentiles, verify that the Timer is configured with an appropriate histogram/distribution and that the backend supports that data point type.

Example configuration class illustrating a `MeterFilter`:

```java
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MetricsConfiguration {

    @Bean
    MeterFilter timerFilter() {
        return MeterFilter.maxExpected(
                "http.server.requests",
                java.time.Duration.ofSeconds(10));
    }
}
```

The filter above bounds the expected value; it does not automatically enable histograms for every version/registry. Configure distribution/percentiles appropriately for your project's Micrometer/Spring Boot version, then verify the OTLP data points in the backend.

Histograms are not free. Many routes, statuses, methods, and buckets can multiply the total number of data points. Use only low-cardinality tags such as route templates (`/orders/{id}`), method, status group, application, and environment. Do not attach `traceId`, `user.id`, `order.id`, or session IDs as metric tags.

## 12. Exemplars and Trace Correlation

The Micrometer OTLP registry supports OTLP exemplars. In Spring Boot, an `ExemplarContextProvider` can supply exemplar context; with Micrometer Tracing, a provider can be auto-configured. Current default configuration includes only sampled traces in exemplars.

An exemplar carries a trace reference inside a metric observation, helping jump from a metric to a trace if the backend and dashboard support it. Verify:

1. An active tracing context exists at measurement time.
2. The registry/exemplar provider supports it.
3. The OTLP exporter encodes the exemplar.
4. The Collector preserves exemplars during processing/forwarding.
5. The metrics backend stores exemplars.
6. The dashboard has a trace datasource and mapping configured.

Do not assume enabling OTLP metrics gives you correlation. You need a separate tracing pipeline, and the sampled trace must still be within retention.

## 13. Collector Receiving OTLP Metrics

A Collector pipeline has receivers, processors, and exporters. Example OTLP/HTTP receiver for local testing:

```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:
    timeout: 5s
    send_batch_size: 1024

exporters:
  debug:
    verbosity: basic

service:
  pipelines:
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
```

The debug exporter is only for verifying the Collector receives data in local/test environments. Production needs an exporter to a metrics backend along with TLS/auth, retry/queue, and resource limit configuration.

The application must connect to the OTLP/HTTP endpoint that the Collector listens on. With the receiver above, the metrics path is typically `/v1/metrics`. If only gRPC on 4317 is enabled while the application sends HTTP, requests will fail.

The Collector does not create a backend by itself. A working receiver does not mean the backend is storing data. Monitor Collector internal telemetry, accepted/refused points, send failures, queue saturation, and retries.

## 14. Testing OTLP Metrics End-to-End

Do not stop at the application starting up. Verify layer by layer:

1. **MeterRegistry:** trigger a business request or test Counter; verify the meter exists in the registry/Actuator metrics if the endpoint is exposed.
2. **OTLP registry:** confirm `micrometer-registry-otlp` is on the runtime classpath, auto-configuration creates the registry, and the endpoint property binds.
3. **Export request:** use a test Collector/receiver; verify requests reach the right `/v1/metrics` URL, responses are valid, and payloads are accepted.
4. **Resource/dimensions:** inspect `service.name`, environment, meter name, unit, tags, temporality, and histogram data points.
5. **Query:** generate controlled traffic; compare counter/rate against operations performed in the same window. For Timers, cross-check count and sum; for p95, confirm the histogram actually exists.
6. **Receiver failures:** test a wrong endpoint, bad auth, or stopped Collector in a test environment. Observe export errors/timeouts and verify business requests do not fail.
7. **Recovery:** restore the Collector/backend and observe the registry resuming export on subsequent cycles.

Do not assume all data points lost during offline periods are replayed. Behavior depends on the registry, aggregation temporality, buffers, and process lifecycle.

## 15. Operating During Export Failures

| Symptom | Possible Cause | Check |
| --- | --- | --- |
| No metrics at Collector | Wrong URL, protocol, DNS, or network | Endpoint, port, `/v1/metrics` path |
| HTTP 404 | Wrong path or receiver route | OTLP/HTTP receiver and metrics path |
| HTTP 401/403 | Wrong token/header or missing permissions | Secret, auth config, tenant scope |
| TLS handshake failed | Invalid CA/certificate/SNI | Trust store, SSL bundle, hostname |
| Export timeout | Slow receiver/backend or congested network | Connect/read timeouts, latency, queue |
| Payload rejected | Schema, payload size, or point type | Receiver response and registry version |
| Some meters missing | Filter, unregistered meter, or batch/export failure | `MeterRegistry`, filters, exporter logs |
| Cannot query p95 | Histogram not enabled or backend lacks support | Data point type and histogram config |
| Service appears as `unknown_service` | Resource identity not configured | `service.name` and OTEL resource attributes |
| Values jump after restart | Cumulative reset/temporality handling | Start timestamps and backend semantics |

### Protecting the Application

- Bound connect/read timeouts.
- Do not let the exporter retry infinitely on request threads.
- Monitor queues/buffers and memory where supported.
- Monitor exporter errors and Collector queues.
- Do not turn telemetry failures into business failures unless explicitly required by business rules.
- Do not log secrets or sensitive payloads.

Do not claim zero data loss without testing it. Step-based registries may hold state only in-process; restarts or disconnections can lose unpublished measurements.

## 16. When Should You Use OTLP Metrics?

| Condition | OTLP Metrics Fit When |
| --- | --- |
| OTLP-capable Collector/backend exists | Managed receiver/endpoint is available |
| Want vendor-neutral transport | Avoiding coupling the app to proprietary APIs |
| Need routing/transformation at Collector | Centralized policies exist |
| Multiple telemetry signals | Want consistent resource metadata conventions |
| Network allows outbound only | App pushes OTLP outbound to collector |
| Backend has a specific query model | Confirmed support for needed temporality/histograms |

OTLP is not automatically better than Prometheus scraping. Choose based on topology, operations, query model, retention, and SLOs. Both pipelines can be used if needed, while avoiding duplicate ingestion and controlling cardinality.

## 17. Hands-On Exercise: Exporting Counter and Timer via OTLP

Run in local/test with an OTLP/HTTP Collector:

1. Add Actuator and `micrometer-registry-otlp` via dependency management.
2. Configure `management.otlp.metrics.export.url` pointing to the Collector's `/v1/metrics`.
3. Declare `service.name` and environment metadata.
4. Create Counter `checkout.accepted` and Timer `checkout.processing`.
5. Send test requests producing both success and error outcomes.
6. Observe the Collector receiving metrics and the backend displaying the right resource/tags.
7. Enable histograms if p95/p99 is needed; verify the actual data points.
8. Stop the Collector during the test and observe exporter behavior and recovery.
9. Verify metrics still record all requests per instrumentation even when trace sampling is set to a lower rate.

Items to record:

| Item | Evidence |
| --- | --- |
| Dependency | OTLP registry present at runtime |
| Endpoint | Reachable URL/protocol/path |
| Export | Collector accepted metrics |
| Resource | Correct service/environment |
| Meter | Counter/Timer has right name/unit |
| Temporality | Backend reads cumulative or delta accurately |
| Distribution | Histogram has required data points |
| Resilience | Timeouts/failures do not break business requests |
| Data quality | No unnecessary high-cardinality tags |

## 18. Self-Check Questions

1. Is OTLP a protocol or a metrics backend?
2. In Spring Boot, which component manages metrics when exporting via OTLP?
3. Why should Micrometer `OtlpMeterRegistry` not be confused with OpenTelemetry `SdkMeterProvider`?
4. Which dependency provides the OTLP registry for Micrometer?
5. Which path does an OTLP/HTTP metrics endpoint typically use?
6. How does `step` differ from a Prometheus scrape interval?
7. How do cumulative and delta aggregation temporalities differ?
8. Why must the backend know the temporality?
9. How does resource attribute `service.name` differ from meter tag `application`?
10. What do `batch-size`, connect timeout, and read timeout affect?
11. Which Micrometer meter types map to OTLP metrics?
12. To get p95 latency, which layers must you verify histograms at?
13. Which components does an OTLP exemplar need to open a trace?
14. Why does a receiver accepting a payload not mean the backend saved the metrics?
15. When the Collector is unavailable, why should you not assume all samples are replayed?

## References

- [Spring Boot — Metrics and OTLP](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): registry dependency, URL, custom headers, and OTLP metrics export.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): Micrometer's role and differences from OpenTelemetry `MeterProvider`.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): `management.otlp.metrics.export` properties.
- [Micrometer — OTLP Registry](https://docs.micrometer.io/micrometer/reference/implementations/otlp.html): configuration, temporality, compression, resource attributes, and meter mapping.
- [OpenTelemetry — OTLP Specification](https://opentelemetry.io/docs/specs/otlp/): OTLP transport and protocol.
- [OpenTelemetry Collector](https://opentelemetry.io/docs/collector/): receivers, processors, exporters, and pipelines.

## Conclusion

**OTLP metrics in Spring Boot is the path for exporting Micrometer-managed metrics to an OTLP-capable system.** Adding `micrometer-registry-otlp`, configuring `management.otlp.metrics.export`, defining resource attributes, and ensuring receiver/backend compatibility are the essential steps. `step`, batch, timeouts, compression, temporality, histograms, and headers determine pipeline quality and reliability.

In operations, verify each layer from application meters to the registry, Collector, and backend; monitor exporter errors, queues, service identity, and cardinality. Keep clear boundaries between metrics, traces, and logs: OTLP metrics do not automatically export spans or logs, but when these pipelines are configured consistently, they work together to investigate errors and latency.
