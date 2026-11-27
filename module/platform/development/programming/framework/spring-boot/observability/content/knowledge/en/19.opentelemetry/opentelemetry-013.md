# Do Not Confuse OTel Metrics with Micrometer Metrics

A Spring Boot application may use Micrometer to measure request counts, processing times, and connection pools, while a third-party library creates its own metrics via the OpenTelemetry API. Both are called metrics and may even ship to the same observability platform, yet they do not automatically share a registry or export path. As a result, dashboards may show Spring Boot metrics while missing metrics emitted by the OpenTelemetry library.

This lesson **Do Not Confuse OTel Metrics with Micrometer Metrics** belongs to the **OpenTelemetry** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module teaches how to set up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; understanding context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production environments.

> **Principle:** In the Spring Boot ecosystem, **Micrometer is the primary metrics choice**. Micrometer provides the measurement API and `MeterRegistry` for applications; concrete registries export data to Prometheus, OTLP, or other backends. OpenTelemetry Metrics has its own API/SDK (`Meter`, `MeterProvider`, `SdkMeterProvider`). Using OTLP **does not mean** the application is using the OpenTelemetry Metrics SDK: `OtlpMeterRegistry` is still a Micrometer registry—it simply exports data over OTLP.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish the Micrometer metrics API, `MeterRegistry`, and the OpenTelemetry Metrics API/SDK.
2. Explain why Spring Boot defaults to Micrometer for metrics.
3. Understand that `OtlpMeterRegistry` is a Micrometer registry exporting via OTLP, not OpenTelemetry `SdkMeterProvider`.
4. Recognize why metrics created by a library using OTel `MeterProvider` may not flow through the Micrometer pipeline.
5. Distinguish OTel tracing support from OTel metrics support in Spring Boot.
6. Understand the role of Micrometer Observation and its handlers when creating metrics and traces.
7. Configure an appropriate Micrometer OTLP, Prometheus, or backend pipeline.
8. Know when to configure a dedicated OpenTelemetry `MeterProvider` for a dependency.
9. Avoid double-measuring an operation using both Micrometer and OTel instrumentation.
10. Verify metric names, units, temporality, histograms, and resource labels across the pipeline.

## 2. Two Metrics Systems, Two APIs, and Two Pipelines

**Micrometer** is the metrics facade in the Java/Spring ecosystem. Code creates `Counter`, `Timer`, `Gauge`, and `DistributionSummary` through the Micrometer API, registering meters into one or more `MeterRegistry` instances.

**OpenTelemetry Metrics** defines its own API and SDK. Code obtains a `Meter` from `OpenTelemetry`/`MeterProvider` and creates instruments such as `Counter`, `Histogram`, and `ObservableGauge`; the SDK manages aggregation, temporality, readers, and exporters.

~~~mermaid
flowchart TD
    A["Spring Boot application"] --> B["Micrometer API"]
    A --> C["OpenTelemetry Metrics API<br/>(if dependency uses directly)"]
    B --> D["MeterRegistry"]
    D --> E["Prometheus / OTLP / SaaS Registry"]
    E --> F["Metrics backend"]
    C --> G["OpenTelemetry MeterProvider"]
    G --> H["MetricReader / Exporter"]
    H --> I["OTLP Collector / backend"]
    I --> F
~~~

Both pipelines can send to the same backend, yet **they do not automatically synchronize data**. Identify which API creates the metric, which registry/provider receives the instrument, which reader/exporter ships the data, and which Resource/attributes travel along.

| Question | Micrometer | OpenTelemetry Metrics |
|---|---|---|
| Primary API | `MeterRegistry`, `Counter`, `Timer`, `Gauge` | `MeterProvider`, `Meter`, `LongCounter`, `Histogram`, `ObservableGauge` |
| Instrument registration | `MeterRegistry` | `Meter` from `MeterProvider` |
| Management/export | Registry implementation | SDK `MetricReader`, exporter, aggregation pipeline |
| Spring Boot default | Auto-configured via Actuator | Does not auto-create a full OTel Metrics SDK pipeline |
| OTLP export | `OtlpMeterRegistry` | OTel OTLP metric exporter/reader |
| Diagnostic endpoints | `/actuator/metrics`, optionally `/actuator/prometheus` | Depends on SDK/exporter; no automatic Actuator Micrometer endpoint |
| Primary goal | Spring ecosystem metrics across many backends | Metrics under the OpenTelemetry API/data model and OTLP pipeline |

## 3. Micrometer Metrics in Spring Boot

Spring Boot Actuator auto-configures Micrometer and builds a composite `MeterRegistry`. Concrete registries are added to the composite based on implementations on the classpath—for example Prometheus, OTLP, Datadog, StatsD, or a Simple in-memory registry.

A service recording metrics normally depends only on the Micrometer API:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Service;

@Service
public class CheckoutMetrics {

    private final Counter approved;

    public CheckoutMetrics(MeterRegistry registry) {
        this.approved = Counter.builder("checkout.authorization.result")
                .description("Number of approved authorizations")
                .tag("outcome", "approved")
                .register(registry);
    }

    public void authorizationApproved() {
        approved.increment();
    }
}
~~~

Application code does not need to know whether the backend is Prometheus or OTLP. The registry configured by Spring Boot accepts measurements and exports them using its corresponding implementation.

### 3.1 `MeterRegistry` Is the Abstraction; Concrete Registries Perform Export

- `SimpleMeterRegistry`: holds measurements in memory for testing/diagnostics.
- `PrometheusMeterRegistry`: exposes data in Prometheus scrape format.
- `OtlpMeterRegistry`: exports Micrometer metrics over OTLP.
- Vendor-specific registries: export using their respective backend protocols.

Merely injecting `MeterRegistry` does not prove data left the JVM. You need a registry with an active exporter and a receiving backend/Collector.

### 3.2 Observation Also Commonly Produces Micrometer Metrics

Spring Boot uses Micrometer Observation for metrics and tracing. Example:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Component;

@Component
public class InventoryObservation {

    private final ObservationRegistry observations;

    public InventoryObservation(ObservationRegistry observations) {
        this.observations = observations;
    }

    public void reserve() {
        Observation.createNotStarted("inventory.reserve", observations)
                .lowCardinalityKeyValue("result", "success")
                .observe(this::reserveInventory);
    }

    private void reserveInventory() {
        // Business operation.
    }
}
~~~

When Spring Boot auto-configures `DefaultMeterObservationHandler`, completed observations produce timers/metrics through Micrometer. If a tracing handler is also installed, observations produce spans. This does not mean Micrometer metrics were converted into OTel SDK metrics.

## 4. OpenTelemetry Metrics API and SDK

OpenTelemetry provides its own model:

- **`MeterProvider`:** entry point for obtaining `Meter` instances.
- **`Meter`:** groups instruments by instrumentation scope.
- **Instruments:** `Counter`, `UpDownCounter`, `Histogram`, `ObservableGauge`, and related types.
- **`MetricReader`:** collects/reads metric streams from the SDK.
- **`Exporter`:** serializes and delivers data to a destination such as OTLP.
- **`Resource`:** identifies the service/process emitting telemetry.
- **`Attributes`:** dimensions grouping data points.

Example using the OpenTelemetry API directly:

~~~java
import io.opentelemetry.api.metrics.LongCounter;
import io.opentelemetry.api.metrics.Meter;
import io.opentelemetry.api.OpenTelemetry;

public class OTelCheckoutMetrics {

    private final LongCounter approved;

    public OTelCheckoutMetrics(OpenTelemetry openTelemetry) {
        Meter meter = openTelemetry.getMeter("com.example.checkout");
        this.approved = meter.counterBuilder("checkout.authorization.approved")
                .setDescription("Approved checkout authorizations")
                .setUnit("{authorization}")
                .build();
    }

    public void recordApproved() {
        approved.add(1);
    }
}
~~~

This example creates an instrument via the OpenTelemetry API. It **does not register the Counter into Micrometer `MeterRegistry`**. Whether it exports depends on which `MeterProvider` the `OpenTelemetry` instance connects to and whether that provider has a matching reader/exporter.

### 4.1 The API Can Exist Without an SDK Pipeline

A dependency may depend on `opentelemetry-api` and call `GlobalOpenTelemetry.getMeter(...)`. If the runtime supplies no configured SDK `MeterProvider`, the API falls back to no-op/default behavior or a provider without an export reader. In that case, metrics neither appear in the Micrometer registry nor reach OTLP.

Having an `OpenTelemetry` bean or tracing provider does not prove a complete Metrics SDK provider/exporter is active either. Inspect the actual `MeterProvider` and metrics pipeline.

## 5. What Current Spring Boot Does and Does Not Do

In current Spring Boot, metrics across the Spring ecosystem are collected through **Micrometer**. Spring Boot documentation states explicitly that metrics are not collected/exported through OpenTelemetry's `SdkMeterProvider` by default; Spring Boot provides no default `SdkMeterProvider` bean. Instead, Micrometer metrics can be exported via OTLP using `OtlpMeterRegistry`.

A dependency using OpenTelemetry `MeterProvider` directly does not have its metrics automatically exported by Spring Boot either. If that dependency needs the OTel Metrics SDK, the application must provide/configure a suitable `MeterProvider` and wire it into the dependency. Always check your exact Spring Boot version because auto-configuration and starters can evolve across major releases.

| Capability | Spring Boot Micrometer Path | OpenTelemetry Metrics SDK Path |
|---|---|---|
| Default Spring Boot metrics | Yes | Not by default |
| `MeterRegistry` bean | Yes, via Actuator | Not replaced by `SdkMeterProvider` |
| Default `SdkMeterProvider` bean | No | Must be configured when using OTel Metrics SDK |
| Boot HTTP server/JVM metrics | Micrometer meters/observations | Not automatically exported via OTel SDK |
| Micrometer metrics over OTLP | Possible via `OtlpMeterRegistry` | Does not require OTel SDK `MeterProvider` |
| Dependency's OTel API instruments | Do not automatically enter Micrometer registry | Requires `MeterProvider`/reader/exporter and wiring |
| Actuator `/actuator/metrics` | Reads Micrometer registry | Does not automatically read OTel SDK instruments |

### 5.1 OTel Tracing Can Work While OTel Metrics Do Not

Spring Boot can integrate OpenTelemetry for traces via Micrometer Tracing and an OTLP exporter. That **does not imply** metrics are also shipped via `SdkMeterProvider`. Tracing providers and metrics providers are separate components in the OpenTelemetry SDK with independent exporters/readers and lifecycles.

An application can simultaneously:
- Create observations with `ObservationRegistry`.
- Record metrics via Micrometer `MeterRegistry`.
- Send traces via Micrometer Tracing/OpenTelemetry.
- Export Micrometer metrics via `OtlpMeterRegistry`.
- Avoid using the OpenTelemetry Metrics SDK directly.

This is a valid configuration aligned with Spring Boot's recommendation to use Micrometer for metrics.

## 6. Exporting Micrometer Metrics via OTLP

If your goal is sending metrics produced by Spring Boot/Micrometer to an OpenTelemetry Collector or OTLP-capable backend, the direct path is configuring the **Micrometer OTLP registry**.

### 6.1 Dependencies

With Gradle and a compatible Micrometer/Spring Boot BOM/dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-otlp'
}
~~~

Do not declare arbitrary versions when the Spring Boot BOM already manages Micrometer versions. Check compatibility before overriding Micrometer versions independently.

### 6.2 Configuring the OTLP Endpoint

Example Spring Boot properties:

~~~yaml
management:
  otlp:
    metrics:
      export:
        url: "http://otel-collector:4318/v1/metrics"
        step: 30s
        aggregation-temporality: cumulative
        compression: gzip
        resource-attributes:
          service.namespace: commerce
          deployment.environment.name: staging
~~~

Exact property binding depends on your Spring Boot/Micrometer version. Micrometer OTLP currently supports configuring URL, batch size, temporality, compression, headers, publish interval (`step`), and resource attributes. The default HTTP OTLP endpoint is commonly `localhost:4318/v1/metrics` with a one-minute publish interval if unconfigured.

In production environments:
- Point to a Collector endpoint reachable from the application network.
- Use TLS and authentication per infrastructure policy.
- Supply headers/secrets through secret management; never commit tokens into YAML.
- Tune timeouts/retries/queues to backend capacity.
- Verify the Collector receives the metrics signal specifically, not just traces.

### 6.3 Pipeline

~~~mermaid
flowchart LR
    A["Spring Boot business code"] --> B["Micrometer MeterRegistry"]
    B --> C["OtlpMeterRegistry"]
    C --> D["OTLP HTTP /v1/metrics"]
    D --> E["OpenTelemetry Collector"]
    E --> F["Metrics backend"]
~~~

Even though the export protocol is OTLP, instruments are still created with Micrometer and managed by the Micrometer registry. The Collector/backend receives OTLP metric data points; that does not turn `MeterRegistry` into `SdkMeterProvider`.

### 6.4 Resource Attributes in Micrometer OTLP Registry

`OtlpMeterRegistry` has its own Resource attributes configuration. Micrometer documentation describes defaults such as `telemetry.sdk.name=io.micrometer`, `telemetry.sdk.language=java`, the Micrometer version, and `service.name=unknown_service`. Attributes can be set via `management.otlp.metrics.export.resource-attributes`; `OTEL_RESOURCE_ATTRIBUTES` and `OTEL_SERVICE_NAME` are also supported per current registry behavior.

Do not assume `OtlpMeterRegistry` automatically reuses the OpenTelemetry SDK `Resource` bean created by Spring Boot. Verify actual resource labels in payloads/backends and configure a clear service identity source.

## 7. Exporting Micrometer Metrics via Prometheus

Another option is the Prometheus registry. This is still Micrometer metrics:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Endpoint configuration:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,metrics,prometheus"
~~~

After the application starts and handles traffic:

~~~bash
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/prometheus
~~~

`/actuator/metrics` uses Micrometer's native meter names; `/actuator/prometheus` serves Prometheus exposition format when the registry and endpoint are configured and exposed.

Prometheus can scrape the application directly. An OTLP Collector can also receive metrics from other OTLP sources. Both backend pathways can coexist, though you must actively avoid scraping/exporting the same set of metrics twice.

## 8. OTel Metrics SDK When a Dependency Requires It Directly

Sometimes a dependency provides instrumentation exclusively via the OpenTelemetry Metrics API. To receive those metrics, you must supply a real OTel SDK pipeline.

Architecturally, you need:

1. An OpenTelemetry SDK/`MeterProvider` configured with a `Resource`.
2. A metric reader (e.g., periodic exporting reader).
3. A matching exporter, such as an OTLP exporter.
4. A bean/provider consumed by the dependency's instrumentation.
5. Proper close/shutdown lifecycle when the application stops.
6. Either a dedicated OTLP ingest pipeline or a shared Collector alongside other signals.

~~~mermaid
flowchart TD
    A["Dependency instrumentation"] --> B["OpenTelemetry Metrics API"]
    B --> C["SdkMeterProvider"]
    C --> D["Periodic MetricReader"]
    D --> E["OTLP Metric Exporter"]
    E --> F["Collector"]
    F --> G["Metrics backend"]
~~~

Spring Boot Actuator may provide an `OpenTelemetry` API bean and register certain OTel SDK provider beans if the application provides them, depending on version. However, do not assume it automatically creates `SdkMeterProvider` and an OTLP metrics exporter. If you declare beans, wire the dependency to that exact instance/provider rather than letting the dependency hit a different global singleton.

### 8.1 Standalone SDK Architecture Example

Illustrative pseudocode showing components (not a copy-paste config for every Boot version):

~~~java
// Pseudocode: builders/dependencies depend on OpenTelemetry SDK version.
Resource resource = Resource.getDefault()
        .merge(Resource.create(Attributes.of(
                AttributeKey.stringKey("service.name"),
                "order-service")));

SdkMeterProvider meterProvider = SdkMeterProvider.builder()
        .setResource(resource)
        .registerMetricReader(periodicReader)
        .build();

OpenTelemetry openTelemetry = OpenTelemetrySdk.builder()
        .setMeterProvider(meterProvider)
        .build();
~~~

This illustrates architecture only; `periodicReader` must be built with an appropriate exporter, and the `OpenTelemetry` instance must be supplied to the dependency using the OTel Metrics API. Defining your own provider requires managing shutdown/lifecycle and avoiding multiple providers instrumenting the same work.

### 8.2 Do Not Spin Up an OTel SDK Just So "Metrics Say OpenTelemetry"

If application code already uses Micrometer and the goal is simply exporting to an OTLP-capable backend, adding a separate `SdkMeterProvider` is usually unnecessary. Using `OtlpMeterRegistry` is simpler, integrates cleanly with Spring Boot metrics auto-configuration, and keeps application instrumentation consistent.

Add the OTel Metrics SDK only when a dependency/framework genuinely requires the OTel API or an explicit architectural requirement mandates native OTel metrics.

## 9. Semantic Conventions: Metric Names Do Not Automatically Match

Micrometer and OpenTelemetry have their own conventions for naming, units, attributes, and aggregation. Sharing the OTLP protocol does not guarantee metric names and dimensions from both APIs match.

Spring Boot defaults to Micrometer/Spring conventions for observations. You can request OpenTelemetry stable semantic conventions for conventions Spring Boot supports:

~~~yaml
management:
  observations:
    conventions: open-telemetry
~~~

This changes the convention used for supported observations; **it does not switch the metrics engine from Micrometer to OpenTelemetry `SdkMeterProvider`**. Some custom properties that rename meters may stop taking effect when selecting OTel conventions. Not every custom metric name is automatically translated.

### 9.1 Example Difference in HTTP Metrics

An application may emit `http.server.requests` under Micrometer/Spring conventions; selecting OTel conventions maps supported observation names/attributes to the OpenTelemetry stable conventions supported by Spring Boot. Existing queries and dashboards may require updates when switching conventions.

Never infer that changing the convention property alone will:
- Create an OTel `MeterProvider`.
- Enable OTLP export.
- Add a Collector pipeline.
- Automatically export metrics from dependencies calling the OTel API.

Conventions answer "how are metrics named and described"; registries/providers answer "who owns instruments and where does data go."

## 10. Instrument and Data Point Mapping in Micrometer OTLP Export

`OtlpMeterRegistry` translates Micrometer meters into corresponding OTLP metric data point types. Common mappings per Micrometer documentation:

| Micrometer Meter | Typical OTLP Data Point |
|---|---|
| `Counter`, `FunctionCounter` | Sum |
| `Gauge`, `TimeGauge`, `MultiGauge` | Gauge |
| `Timer`, `DistributionSummary` | Histogram or Exponential Histogram depending on config |
| `LongTaskTimer`, `FunctionTimer` | Histogram/Summary mapping per support; `FunctionTimer` has sum/count limitations |
| Client-side percentiles | Summary data point when publishing percentiles only |

For `Timer` and `DistributionSummary`, histogram/SLO settings influence the emitted data point type. Micrometer OTLP currently prefers histograms for timers/summaries unless client-side-only percentiles are requested; Summary data points in OTLP are considered legacy for pre-computed percentiles and discouraged for new applications.

### 10.1 Histograms and Percentiles Are Not the Same

- **Histogram:** bucket/count/sum data can be aggregated across instances to estimate percentiles.
- **Client-side percentile:** the application calculates percentiles before export; results generally cannot be accurately merged across instances like histograms.
- **SLO buckets:** buckets chosen around service level boundaries, useful for corresponding alerts and queries.
- **Temporality:** cumulative or delta affects how additive measurements are represented over time.

Example SLO configuration for a timer:

~~~yaml
management:
  metrics:
    distribution:
      slo:
        checkout.payment.duration: 0.1s,0.3s,0.5s,1s
~~~

This illustrates choosing bucket boundaries for a meter name; actual key binding must match your Spring Boot version's property format. Verify the exporter/backend receives histogram data points and queries assume the right temporality.

## 11. Cardinality and Tags/Attributes

Both Micrometer tags and OTel attributes create dimensions on metric data. When values have too many possibilities, time-series counts grow quickly.

Avoid near-unique per-request values:

~~~java
// Avoid creating a metric series per request.
Counter.builder("checkout.requests")
        .tag("orderId", orderId)
        .register(registry)
        .increment();
~~~

Use stable, bounded dimensions instead:

~~~java
Counter.builder("checkout.requests")
        .tag("outcome", "approved")
        .tag("channel", "mobile")
        .register(registry)
        .increment();
~~~

Rules that apply to both metrics APIs:

- Never put `traceId`/`spanId`/`orderId`/`userId`/email into metric attributes.
- Normalize routes into templates rather than raw URLs containing IDs.
- Constrain exception, status, region, and channel values to controlled sets.
- Use logs/traces to investigate individual requests.
- Use metrics for trends and statistics across many requests.

If the same operation is instrumented via both APIs, cardinality can double or queries fragment due to differing name/tag mappings. Choose one instrumentation owner.

## 12. Avoiding Double Measurement Between Micrometer and OpenTelemetry

A common integration mistake:
- Spring MVC auto-instrumentation creates an observation/`Timer`.
- An OTel Java agent or another instrumentation library also creates a metric for the same HTTP server request.
- Custom code adds yet another `Counter`/`Timer` for the same operation.
- Both pipelines export metrics to the backend, and dashboards sum or display duplicate series.

The result can be doubled request counts, skewed latency comparisons, higher cost, and confusion over which meter is canonical.

### 12.1 Pick an Instrumentation Owner per Boundary

| Boundary | One Clear Choice |
|---|---|
| Spring MVC/WebFlux server requests | Spring Boot/Micrometer auto-observation or OTel agent instrumentation after choosing conventions |
| JDBC client/database | One chosen instrumentation implementation, never two running uncontrolled in parallel |
| Business operations | Micrometer Observation or OTel API per architecture |
| JVM/process metrics | Spring Boot/Micrometer binders or OTel runtime instrumentation; avoid duplicate publishing |
| Dependency exposing OTel Metrics API only | Provide an OTel `MeterProvider` pipeline if dependency metrics are needed |

Not all OTel auto-instrumentation creates metrics duplicating Spring Boot; coverage and supported signals depend on agent/library version. Inspect actual instrument names and instrumentation scopes instead of guessing.

### 12.2 Avoid Filtering Duplicate Names Only After Export

If two pipelines emit the same meaning under different names, hiding one name on a dashboard masks duplicate instrumentation rather than fixing the root cause. First inspect the metric source, registry/provider, scope, labels, and export path. Then disable the redundant instrumentation or establish clear conventions/ownership.

## 13. Decision Guide: Which Metrics API Should You Use?

### Case A — Typical Spring Boot Application

Use the Micrometer API and `MeterRegistry`; create custom counters/timers and `Observation`s; select Prometheus, OTLP, or another registry backend via dependencies/config. This is the default path in the Spring ecosystem.

### Case B — Simply Sending Micrometer Metrics to an OpenTelemetry Collector

Add `micrometer-registry-otlp` and configure `management.otlp.metrics.export`. You continue using Micrometer instruments and registries while the Collector ingests OTLP metrics.

### Case C — A Dependency Emits Metrics Only via the OTel API

Check which provider the dependency calls. If you need those metrics, supply/wire an `SdkMeterProvider`, reader, and exporter for the dependency and confirm metrics are no longer no-ops. Do not assume the Micrometer registry automatically picks up OTel instruments.

### Case D — Application Intentionally Chooses the Native OpenTelemetry Metrics SDK

Design an intentional SDK/provider/exporter pipeline and clearly divide which metrics Micrometer owns versus which the OTel SDK owns. Align naming, Resource, units, cardinality, and shutdown while avoiding double measurement. For Spring Boot applications, carefully weigh needs before replacing the default Micrometer pipeline.

## 14. Debugging Missing Metrics

| Symptom | Possible Cause | What to Check |
|---|---|---|
| `/actuator/metrics` shows metric yet Collector sees nothing | Micrometer registry not exporting or wrong endpoint | Check registry implementation, export URL/step, and exporter logs |
| OTLP traces exist yet OTLP metrics are missing | Tracing exporter configured, Micrometer OTLP registry missing | Check `micrometer-registry-otlp` and `management.otlp.metrics.export` |
| OTel API dependency creates metric yet backend misses it | Missing `SdkMeterProvider`/reader/exporter or dependency not wired to provider | Check provider instance, reader, and SDK pipeline |
| Prometheus shows metric yet OTel dashboard misses it | No OTLP export or backend does not ingest Prometheus | Inspect separate pipelines |
| Metric counts double | Duplicate instrumentation between Spring/Micrometer and OTel agent/library | Check instrumentation scope, meter names, and labels |
| Metric name differs from old dashboard | Convention/mapping changed | Check `management.observations.conventions`, naming conventions, and exporter |
| Resource/service name differs | Micrometer OTLP resource config differs from OTel SDK Resource | Check `service.name`, resource attributes, and Collector transforms |
| Histogram lacks expected buckets | Histogram/SLO unconfigured or exporter mapping differs | Check distribution properties, data point type, and temporality |
| Abnormal counter rate after restart | Counter semantics/reset mismatch with temporality/query | Check cumulative/delta and backend query |
| Actuator metrics lacks custom metric | Meter not registered to Spring `MeterRegistry` or wrong tag query | Inject the right registry; check meter ID/tag filters |
| Metrics missing in short-lived runs | Registry publishes on step/flush interval | Wait for export interval and check shutdown/flush |
| Some OTel metrics exist while Spring metrics are missing | Two provider pipelines have different configurations | Inspect each pipeline separately |

## 15. Playbook: OTLP Backend Has Traces but Missing Metrics

**Scenario:** Spring Boot successfully sends traces to the Collector. Tracing dashboards work, yet Actuator metrics do not appear.

1. **Identify metric source:** is the meter created via `MeterRegistry` or OTel `MeterProvider`?
2. **Check dependencies:** is `micrometer-registry-otlp` present if exporting Micrometer metrics via OTLP?
3. **Check Micrometer config:** `management.otlp.metrics.export.url`, headers, step, resource attributes, and enabled flags.
4. **Check endpoint/transport:** does the Collector accept the right OTLP HTTP path `/v1/metrics` or matching endpoint/transport?
5. **Check Collector pipeline:** the OTLP receiver must connect to a metrics pipeline and backend exporter.
6. **Check metric resource/name:** verify service name, attributes, and data point type.
7. **If metrics come from the OTel API:** verify `SdkMeterProvider`, reader, and exporter exist; Spring Boot does not automatically convert OTel API instruments into Micrometer meters.
8. **Check duplicate instrumentation:** compare metric counts/names/scopes if both the agent and Spring instrumentation are enabled.

Do not add an OTel SDK `MeterProvider` just because traces are running; first determine which API owns the missing metrics.

## 16. Self-Check Exercises

**Exercise 1 — Distinguish APIs.** A service injects `MeterRegistry` and creates a `Timer`. Is it using the OpenTelemetry Metrics SDK? Explain.

**Exercise 2 — OTLP Registry.** A project adds `micrometer-registry-otlp`. Why are the metrics shipped to the Collector over OTLP still Micrometer metrics?

**Exercise 3 — Dependency Using OTel API.** A library calls `openTelemetry.getMeter(...).counterBuilder(...)`, yet the metric never appears in the backend. List the pipeline components to check.

**Exercise 4 — Traces Present, Metrics Missing.** Spring Boot configures Micrometer Tracing and an OTLP trace exporter. Why does this not guarantee metrics are exported over OTLP?

**Exercise 5 — Convention Property.** Does setting `management.observations.conventions=open-telemetry` switch `MeterRegistry` to OTel `SdkMeterProvider`? What does this property actually change?

**Exercise 6 — Duplicate Instrumentation.** Spring MVC auto-observation and the OTel agent both measure HTTP server requests. Describe the symptoms that may appear and how to pinpoint the duplicate source.

**Exercise 7 — Cardinality.** A `Counter` has a `traceId` tag. Why is this inappropriate even when the backend supports OTLP?

**Exercise 8 — Choosing a Pipeline.** An application only wants to export Micrometer metrics to an OpenTelemetry Collector. Which dependency and configuration are needed? When is the native OTel Metrics SDK actually required?

### Suggested Answers

1. No. That is the Micrometer API; `MeterRegistry` owns the meter.
2. OTLP is a protocol/export format; `OtlpMeterRegistry` remains an implementation of Micrometer `MeterRegistry`.
3. Check `MeterProvider`, `SdkMeterProvider`, `MetricReader`, exporter, `Resource`, and dependency wiring.
4. Tracing and metrics are separate provider/export pipelines. Spring Boot does not automatically export OTel SDK metrics; Micrometer metrics require a corresponding registry.
5. No. It selects OpenTelemetry stable semantic conventions for supported observations; it does not swap the registry/SDK engine.
6. Duplicate counts, near-identical series, different instrumentation scopes; inspect the agent/library and Spring observations, then pick one owner per boundary.
7. Trace ID is nearly unique per request, creating massive series cardinality; use logs/traces to look up specific requests.
8. Add `micrometer-registry-otlp` and configure `management.otlp.metrics.export`; the native OTel SDK is only needed when a dependency/app genuinely uses the OTel Metrics API or has specific native OTel requirements.

## 17. Official References

- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): Spring Boot's use of Micrometer for metrics, OTel support, conventions, and auto-configuration boundaries.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer registries, Actuator endpoints, and custom metrics.
- [Micrometer — OTLP Registry](https://docs.micrometer.io/micrometer/reference/implementations/otlp.html): `OtlpMeterRegistry`, configuration, resource attributes, and data point mapping.
- [Micrometer — Registry Concepts](https://docs.micrometer.io/micrometer/reference/concepts/registry.html): `MeterRegistry`, composite registries, and implementations.
- [OpenTelemetry — Metrics API](https://opentelemetry.io/docs/specs/otel/metrics/api/): `MeterProvider`, `Meter`, and instruments.
- [OpenTelemetry — Metrics SDK](https://opentelemetry.io/docs/specs/otel/metrics/sdk/): `MetricReader`, aggregation, collection, and SDK export.
- [OpenTelemetry — Metrics Data Model](https://opentelemetry.io/docs/specs/otel/metrics/data-model/): data points, temporality, and aggregation.
- [OpenTelemetry — OTLP Specification](https://opentelemetry.io/docs/specs/otlp/): transport and export of telemetry data.
- [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation/introduction.html): Observation lifecycle and handlers for metrics/tracing.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): exposing and securing metrics endpoints.

**Key takeaway:** Micrometer and OpenTelemetry Metrics are two distinct metrics APIs/SDKs. Spring Boot uses Micrometer as its default metrics path; `OtlpMeterRegistry` sends Micrometer meters over OTLP, yet it is not `SdkMeterProvider`. Metrics created by a dependency via the OTel API require a separately configured and wired OTel Metrics SDK pipeline to export. Classify the instrument source before debugging, pick one instrumentation owner per boundary, inspect the registry/provider and Collector pipeline, and verify naming, Resource, temporality, and cardinality to prevent missing or double-counted metrics.
