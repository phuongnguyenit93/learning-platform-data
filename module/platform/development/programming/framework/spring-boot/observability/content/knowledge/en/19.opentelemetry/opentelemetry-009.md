# `SdkMeterProvider` in OpenTelemetry

In the **OpenTelemetry** chapter of the **SPRING_BOOT_OBSERVABILITY** module, `SdkMeterProvider` is the SDK component that manages meters and metric collection. It supplies `Meter` instances to instrumentation, combining resource metadata, views, aggregations, and metric readers to turn recorded measurements into metric streams and export them to an observability system.

When deploying Spring Boot, two integration paths must be distinguished. Most Spring Boot applications use **Micrometer Observation and `MeterRegistry`** managed by Spring Boot Actuator. An application or library choosing the OpenTelemetry Metrics API directly may use the **OpenTelemetry SDK with `SdkMeterProvider`**. Either path can export metrics to a backend, though you should never create two independent pipelines recording the same measurement.

This lesson in the **SPRING_BOOT_OBSERVABILITY** module focuses on metrics, logs, and distributed tracing: understanding the role of `SdkMeterProvider`, creating instruments, configuring Resource/Views/`MetricReader`, exporting via OTLP, bounding cardinality, and verifying data from application to backend.

## 1. Where Does `MeterProvider` Fit in the OpenTelemetry Architecture?

OpenTelemetry separates the **API** from the **SDK**. The API defines the interfaces instrumentation calls; the SDK implements measurement storage, aggregation, and metric export. `MeterProvider` is the API abstraction, while `SdkMeterProvider` is the OpenTelemetry SDK implementation.

```text
Spring Boot application
    |
    +-- instrumentation (HTTP / business / database)
    |                  |
    |                  v
    |              MeterProvider API
    |                  |
    |                  v
    |              Meter
    |                  |
    |            instruments
    |        Counter / Histogram / Gauge
    |                  |
    |                  v
    |            measurements
    |                  |
    |                  v
    |             SdkMeterProvider
    |              /    |     \
    |        Resource  Views  MetricReaders
    |                            |
    |                            v
    |                      MetricExporter
    |                            |
    |                            v
    |                         OTLP
    |                            |
    |                            v
    |                    Collector / backend
    |
    +-- Micrometer MeterRegistry (a separate pipeline if chosen by app)
```

| Component | Responsibility |
| --- | --- |
| `MeterProvider` | Supplies `Meter` instances to instrumentation |
| `SdkMeterProvider` | Manages instruments, aggregations, views, and readers in the SDK |
| `Meter` | Groups instruments by instrumentation scope |
| Instrument | Declares how measurements are recorded, such as counter or histogram |
| `Resource` | Metadata about the service/process producing metrics |
| `View` | Customizes aggregation or attribute sets for an instrument |
| `MetricReader` | Collects/reads metric data from the SDK per export mode |
| `MetricExporter` | Serializes/transports metric data to a backend format, e.g., OTLP |

**`SdkMeterProvider` is not a metrics backend.** It holds in-process aggregation state and feeds data to readers. Historical storage, time-range queries, and dashboards belong to the collector/backend such as Prometheus or a compatible metrics platform.

## 2. API vs. SDK: Why Keep Them Separate?

Instrumentation should generally depend on the API so it is not locked into a specific exporter or backend. The application wires the SDK and configures the provider at the composition root.

- **API:** `io.opentelemetry.api.metrics.MeterProvider`, `Meter`, `LongCounter`, `DoubleHistogram`, and instrument interfaces.
- **SDK:** `io.opentelemetry.sdk.metrics.SdkMeterProvider`, readers, views, and aggregations.
- **Exporter:** modules such as the OTLP metric exporter providing outbound transport.

If only the API is present without a matching SDK/provider implementation, instruments may operate as no-ops; code compiles, yet no data is exported. Calling `GlobalOpenTelemetry.getMeterProvider()` does not by itself prove an SDK or exporter is installed.

Do not let individual libraries create their own `SdkMeterProvider` and exporters. Multiple providers can split telemetry into inconsistent pipelines, duplicate series, attach differing resources, or complicate shutdown. An application should have **one clear owner** for the provider and lifecycle of each primary metrics pipeline.

## 3. Instruments: Recording Data with the Right Semantics

`Meter` provides instruments. Choosing the semantically right instrument matters more than picking whichever API is easiest to write.

| Instrument | Semantics | Example |
| --- | --- | --- |
| Counter | Monotonically increasing value; never decreases | Total accepted orders |
| UpDownCounter | Value that can increase or decrease | Pending background tasks |
| Histogram | Distribution of recorded values | Processing duration, payload size |
| Gauge / ObservableGauge | Current value observed at collection time | Active connections |
| ObservableCounter | Cumulative sum read from a callback | Total bytes from a read-only source |
| ObservableUpDownCounter | Observed value that can increase or decrease | Current queue depth |

Do not use a counter for current state such as active connections; never decrement a counter when a request finishes. For processing duration, a histogram usually fits because distributions can be aggregated in the backend. Gauges suit instantaneous state, though `rate()` cannot be applied to them like counters.

### Example Creating a Meter and Counter

The following snippet uses the OpenTelemetry Metrics API:

```java
import io.opentelemetry.api.metrics.LongCounter;
import io.opentelemetry.api.metrics.Meter;
import io.opentelemetry.api.metrics.MeterProvider;

public final class OrderMetrics {
    private final LongCounter acceptedOrders;

    public OrderMetrics(MeterProvider meterProvider) {
        Meter meter = meterProvider
                .meterBuilder("orders.business")
                .setInstrumentationVersion("1.0.0")
                .build();

        this.acceptedOrders = meter
                .counterBuilder("orders.accepted")
                .setDescription("Number of accepted orders")
                .setUnit("{order}")
                .build();
    }

    public void recordAccepted(String channel) {
        acceptedOrders.add(
                1,
                io.opentelemetry.api.common.Attributes.of(
                        io.opentelemetry.api.common.AttributeKey
                                .stringKey("channel"),
                        channel));
    }
}
```

In real applications, `channel` must be a bounded, normalized value such as `web`, `mobile`, or `partner`. Do not pull arbitrary client headers directly if they can hold thousands of values.

Metric name, description, and unit are part of the telemetry contract. Names should stay stable, units explicit, and descriptions meaningful. Never switch the same metric name from "seconds" to "milliseconds" without managing migration.

### Histogram for Processing Duration

```java
import io.opentelemetry.api.metrics.DoubleHistogram;
import io.opentelemetry.api.metrics.Meter;

public final class CheckoutMetrics {
    private final DoubleHistogram duration;

    public CheckoutMetrics(Meter meter) {
        this.duration = meter.histogramBuilder("checkout.duration")
                .setDescription("Checkout operation duration")
                .setUnit("s")
                .build();
    }

    public void recordDuration(double seconds, String outcome) {
        duration.record(
                seconds,
                io.opentelemetry.api.common.Attributes.of(
                        io.opentelemetry.api.common.AttributeKey
                                .stringKey("outcome"),
                        outcome));
    }
}
```

Seconds are chosen in this example to match duration conventions. `outcome` should have a bounded set such as `success`, `declined`, and `error`. Do not put order ID, Trace ID, or exception messages into metric attributes.

## 4. Creating `SdkMeterProvider` with `Resource` and `MetricReader`

A provider needs to know:

1. **Resource:** service name, service version, environment, and stable process metadata.
2. **Reader:** collection mechanism, such as periodic push via OTLP or pull via a matching exporter/reader.
3. **View (if needed):** aggregation, buckets, or attribute filtering for instruments.
4. **Lifecycle:** when the provider is initialized, kept alive, and shut down.

Standalone configuration example using the OTLP/gRPC exporter:

```java
import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.common.Attributes;
import io.opentelemetry.exporter.otlp.metrics.OtlpGrpcMetricExporter;
import io.opentelemetry.sdk.OpenTelemetrySdk;
import io.opentelemetry.sdk.metrics.SdkMeterProvider;
import io.opentelemetry.sdk.metrics.export.PeriodicMetricReader;
import io.opentelemetry.sdk.resources.Resource;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

public final class StandaloneMetrics {
    public static void main(String[] args) {
        Resource resource = Resource.getDefault().merge(
                Resource.create(Attributes.of(
                        AttributeKey.stringKey("service.name"),
                        "orders-service",
                        AttributeKey.stringKey("deployment.environment.name"),
                        "development")));

        var exporter = OtlpGrpcMetricExporter.builder()
                .setEndpoint("http://localhost:4317")
                .build();

        var reader = PeriodicMetricReader.builder(exporter)
                .setInterval(Duration.ofSeconds(30))
                .build();

        SdkMeterProvider meterProvider = SdkMeterProvider.builder()
                .setResource(resource)
                .registerMetricReader(reader)
                .build();

        OpenTelemetrySdk openTelemetry = OpenTelemetrySdk.builder()
                .setMeterProvider(meterProvider)
                .build();

        OrderMetrics orderMetrics =
                new OrderMetrics(openTelemetry.getMeterProvider());
        orderMetrics.recordAccepted("web");

        // Flush demo measurements before ending the process.
        boolean flushed = meterProvider.forceFlush()
                .join(10, TimeUnit.SECONDS);
        if (!flushed) {
            throw new IllegalStateException("Metrics flush did not complete");
        }

        meterProvider.close();
    }
}
```

This is a **standalone SDK** example illustrating wiring. A short-lived program that runs and exits immediately may close the provider before a collection cycle; newly recorded data might not be exported yet. In long-running services, keep the provider alive throughout the service's lifetime. Exporter/reader APIs can vary across OpenTelemetry versions; use a compatible BOM and verify packages/modules.

### Resource Attributes

Resource describes **where telemetry is produced**, not individual requests:

| Attribute | Example | Should It Change Per Request? |
| --- | --- | --- |
| `service.name` | `orders-service` | No |
| `service.version` | `2.4.1` | No within the same process |
| `deployment.environment.name` | `production` | No within the same deployment |
| `service.instance.id` | Instance/pod ID | Not per request |
| `tenant.id` | Current tenant | Do not set as resource for multi-tenant services |

Do not place user ID, order ID, Trace ID, or request-specific values into Resource. Those values fragment identity or inflate cardinality unnecessarily.

## 5. `MetricReader` and `MetricExporter`

The reader determines **when and how metrics are collected**. The exporter determines **where data goes and over which transport**.

| Reader/Export Pattern | Behavior | Suitable Use Case |
| --- | --- | --- |
| `PeriodicMetricReader` | Collects on an interval and sends data to an exporter | Periodic OTLP push |
| Pull reader/exporter | Exposes metrics for a scraper to sample | Pull-model backends when supported by exporter/SDK |
| Custom reader/processor | Specialized integration | Only when clearly needed and lifecycle is controlled |

With a periodic reader, the interval is an operational trade-off. Too short increases network/export overhead; too long delays visibility and risks losing larger batches on abrupt process termination. Tune the interval for freshness, batch size, load, and backend capacity.

An OTLP metric exporter typically sends metrics to a collector, which routes them to a backend. `localhost:4317` works only if the collector shares the network namespace or has port mapping configured. In Docker/Kubernetes, use real DNS/service names and configure TLS/auth as needed.

**Do not equate OTLP export with Prometheus scraping.** OTLP is typically pushed to a receiver; traditional Prometheus scrapes an exposition endpoint. If you want Prometheus pull, choose the corresponding integration and verify output/temporality instead of assuming a URL change suffices.

## 6. Views: Controlling Aggregation and Attributes

Views let you configure how an instrument is aggregated and which attributes are retained in the metric stream. They are useful when:

- You need histogram aggregation with explicit bucket boundaries aligned to SLOs.
- You want to drop unnecessary attributes.
- You want to standardize output metric streams for the backend.
- You need to prevent high-cardinality tags from reaching the exporter.

Illustrative example creating a View for a histogram:

```java
import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.sdk.metrics.InstrumentSelector;
import io.opentelemetry.sdk.metrics.View;
import io.opentelemetry.sdk.metrics.Aggregation;
import java.util.List;

var selector = InstrumentSelector.builder()
        .setName("checkout.duration")
        .build();

var view = View.builder()
        .setAggregation(
                Aggregation.explicitBucketHistogram(
                        List.of(0.05, 0.1, 0.25, 0.5, 1.0, 2.5)))
        .setAttributeFilter(key ->
                !key.equals(AttributeKey.stringKey("debug.payload")))
        .build();
```

View/aggregation APIs and attribute filters may differ across SDK versions. Register the View on `SdkMeterProvider`'s builder (typically pairing instrument selector and view) and verify the actual emitted metric stream. The snippet above shows only View configuration, not a full provider.

Views are not a substitute for designing clean attributes at the source. Avoid producing high-cardinality attributes in the first place; filters are an extra safeguard, not license to record arbitrary tags.

### Explicit Histogram Boundaries

Bucket boundaries must reflect units and operational thresholds. For checkout duration in seconds, boundaries `0.05`, `0.1`, `0.25`, `0.5`, `1.0`, and `2.5` seconds are helpful if they match SLOs. If most requests finish under 10 ms or over 10 seconds, those buckets fit poorly.

Do not pick buckets merely from an online example. Examine real histogram distributions, latency targets, and resulting time-series volume. Bucket count, attribute combinations, and instance count all compound cardinality.

## 7. Cardinality and Metric Attributes

A metric stream is typically identified by metric identity, resource, and attribute set. When attributes take unbounded values, series counts grow rapidly.

Suppose an instrument has:

- `route`: 20 route templates.
- `method`: 4 methods.
- `status_class`: 5 groups.
- `region`: 3 regions.

Simple combinatorial maximum is 20 × 4 × 5 × 3 = 1,200 combinations per instance. Across 50 instances, that becomes 60,000 series before counting histogram buckets or other metrics. Adding `orderId` with millions of values will blow through cardinality budgets rapidly.

| Attribute | Assessment | Reason |
| --- | --- | --- |
| `route=/orders/{id}` | Appropriate | Route templates have a bounded value set |
| `method=GET/POST` | Appropriate | Small cardinality |
| `status_class=2xx/4xx/5xx` | Appropriate | Easy to aggregate |
| `provider=bank_a/bank_b` | Appropriate if curated | Dependency breakdown |
| `orderId` | Avoid | Nearly every transaction creates a new series |
| `traceId` / `spanId` | Avoid | Nearly unique per trace/span |
| Raw URL/query string | Avoid | Contains IDs, tokens, or unbounded strings |
| Verbatim exception message | Avoid | Both high-cardinality and data-leak risk |

The OpenTelemetry SDK may enforce cardinality limits or aggregation limits depending on version/configuration. When limits are reached, the SDK may collapse excess attributes into an overflow series or handle them per defined semantics; check behavior for your exact version. **Never rely on limits to excuse poorly designed attributes.**

## 8. Temporality: Cumulative vs. Delta

Metrics exporters and readers require consistent temporality semantics:

- **Cumulative:** each collection reports the running total since the instrument/process started or reset.
- **Delta:** each collection reports only the change since the previous collection.

Example of a counter recording 5, then recording 3 more:

| Collection | Cumulative | Delta |
| --- | ---: | ---: |
| Collection 1 | 5 | 5 |
| Collection 2 | 8 | 3 |

The backend must understand temporality to compute rates, resets, and aggregations accurately. Do not sum repeated cumulative points as though each point were a new increment. Do not assume every reader/exporter/backend defaults to the same temporality; check the OTLP payload, SDK temporality preference, and backend semantics.

For histograms, delta vs. cumulative also changes how bucket counts, sum, and count are interpreted. When changing exporters or backends, test the migration carefully and avoid double counting during parallel runs.

## 9. Observable Instruments and Callbacks

Counters and Histograms are recorded when events happen. Observable instruments read values from a callback when SDK collection runs. They fit stateful measurements such as queue depth or active worker count.

Illustrative example:

```java
import io.opentelemetry.api.metrics.Meter;
import io.opentelemetry.api.metrics.ObservableLongGauge;
import java.util.concurrent.atomic.AtomicLong;

public final class QueueMetrics implements AutoCloseable {
    private final AtomicLong queueSize;
    private final ObservableLongGauge gauge;

    public QueueMetrics(Meter meter, AtomicLong queueSize) {
        this.queueSize = queueSize;
        this.gauge = meter.gaugeBuilder("orders.queue.size")
                .ofLongs()
                .setDescription("Current number of queued orders")
                .setUnit("{order}")
                .buildWithCallback(measurement ->
                        measurement.record(queueSize.get()));
    }

    @Override
    public void close() {
        gauge.close();
    }
}
```

Callbacks must be lightweight, non-blocking, and never call databases or remote services. They execute on the collection schedule; if a callback does heavy work, metrics scraping/exporting itself degrades application performance. Close observable instruments when their owning component shuts down to release callback registrations.

Never register a new callback per request. Create the instrument once in the bean/service lifecycle and let the callback read existing state.

## 10. Integrating `SdkMeterProvider` with Spring Boot: Pick One Owner

Spring Boot Actuator commonly uses Micrometer `MeterRegistry` to instrument HTTP, JVM, `DataSource`, and `Observation`. If a project uses Micrometer as its main abstraction, Spring Boot auto-configuration and Micrometer registries are the natural integration path.

If a project includes libraries or instrumentation using the OpenTelemetry Metrics API directly, the OTel SDK may be required. In that case, clearly decide how the application owns the provider and export:

**Option A — Micrometer-first**

- Spring Boot manages `MeterRegistry`.
- Custom business metrics use the Micrometer API.
- The registry/exporter is configured for the chosen backend.
- Tracing can use the Micrometer Tracing bridge.

**Option B — OpenTelemetry SDK-first**

- The application configures `SdkMeterProvider` and `MetricReader`.
- OTel API instrumentation records directly through `MeterProvider`.
- The exporter sends metrics to the collector/backend.
- Provider/reader lifecycles are owned by the application or integration framework.

**Never record the same business event through both pipelines** if the backend aggregates them as two independent metrics. Incrementing both a Micrometer `Counter` and an OTel `Counter` for the same order can double-count orders.

### Spring Configuration for an Application-Owned Provider

A Spring configuration can register the provider as a bean with a clear lifecycle. Conceptual example:

```java
import io.opentelemetry.exporter.otlp.metrics.OtlpGrpcMetricExporter;
import io.opentelemetry.sdk.metrics.SdkMeterProvider;
import io.opentelemetry.sdk.metrics.export.PeriodicMetricReader;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import java.time.Duration;

@Configuration(proxyBeanMethods = false)
class OpenTelemetryMetricsConfiguration {

    @Bean(destroyMethod = "close")
    SdkMeterProvider sdkMeterProvider() {
        var exporter = OtlpGrpcMetricExporter.builder()
                .setEndpoint("http://otel-collector:4317")
                .build();

        var reader = PeriodicMetricReader.builder(exporter)
                .setInterval(Duration.ofSeconds(30))
                .build();

        return SdkMeterProvider.builder()
                .registerMetricReader(reader)
                .build();
    }
}
```

This illustrates when **the application itself owns the OTel metrics provider**. Add appropriate `Resource`/`View`/attributes, use the right BOM and endpoint, and ensure instrumentation receives this provider bean (via constructor injection or the wired `OpenTelemetry` SDK). Declaring this bean alone does not migrate all Micrometer Actuator metrics onto the OTel SDK.

If your Spring Boot version or starter already auto-configures the OTel SDK/bridge, do not create an extra standalone bean doing the same job. Identify which API your instrumentation actually calls.

## 11. `SdkMeterProvider` and Correlation with Traces/Logs

Metrics typically answer "how many", "how long", and "what rate" over a time window. Tracing shows the execution path of a recorded request; logs capture detailed errors and events.

```text
Metrics:
  checkout.duration histogram p95 increases
  payment.authorizations{outcome="error"} increases
              |
              v
     find affected time window/route
              |
              v
Trace (if sampled and exported successfully):
  POST /checkout
    order.confirm
      payment.authorize
        HTTP provider call (slow)
              |
              v
Logs with traceId/spanId:
  "provider timeout"
```

`SdkMeterProvider` does not manage `TracerProvider` or the logs SDK. Each signal is configured separately, though they can share `Resource`/service identity for backend correlation. Exemplars can be used when supported by the registry/exporter/backend so a metric sample links to a representative trace without placing Trace ID into metric labels.

Never attach `traceId` or `spanId` to counter/histogram attributes. Those IDs are nearly unique and will explode series counts. Use low-cardinality attributes such as route template, operation, status class, and outcome.

Trace sampling does not govern metric sampling either. Even when a trace is sampled out, metrics are still recorded via `SdkMeterProvider`/`MetricReader` or Micrometer registry. This is critical for SLIs: compute them from full-coverage metrics rather than inferring request counts from sampled traces.

## 12. Common `SdkMeterProvider` Configuration Pitfalls

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Code creates `Meter` yet backend shows no data | No-op API, provider lacks reader, or exporter inactive | Check SDK dependencies, provider wiring, and reader registration |
| Backend shows wrong service name | Missing or overridden Resource | Check Resource attributes in the metric stream |
| Metrics export once then stop | Broken reader lifecycle/interval or app shutdown | Check `PeriodicMetricReader` and provider lifecycle |
| Counter double-counted | Same event recorded in both Micrometer and OTel | Audit instrumentation and pipelines |
| Series count spikes unexpectedly | High-cardinality attributes or excessive histogram buckets | Inspect attribute combinations, Views, and cardinality limits |
| Gauge never updates | Unregistered callback, wrong state reference, or instrument closed | Check callback lifecycle and collection interval |
| Export timeout or growing queue | Unresponsive Collector/backend | Check network, retries, batching, and capacity |
| Wrong rates after changing reader/exporter | Different temporality or reset semantics | Verify cumulative/delta and backend query logic |
| One instance missing metrics | Service not scraped/exported or mismatched labels | Check targets, resource, endpoint, and discovery |
| Collector receives metrics yet dashboard is empty | Query or datasource mismatch | Check post-conversion names, units, and actual labels |

### Do Not Confuse API Metric Names with Backend Names

Instrumentation records metric names like `orders.accepted`; exporters may normalize names or units to fit backend conventions. Never write PromQL or dashboards from guessed names. Inspect exposition/OTLP output and actual series names after pipeline processing.

## 13. Verification Workflow from Instrument to Backend

1. **Check dependencies/versions:** OpenTelemetry API, SDK, and exporter share a compatible BOM; no unintended duplicate providers exist.
2. **Check provider wiring:** instrumentation obtains `Meter` from the active provider, not a no-op/default provider outside the pipeline.
3. **Check Resource:** service name, version, and environment are accurate and free of request-specific metadata.
4. **Record a known measurement:** increment a counter a known number of times and record a histogram with known values.
5. **Check reader:** reader is registered, interval is appropriate, and the process stays up long enough for collection to run.
6. **Check exporter:** endpoint/protocol/TLS/auth and collector receiver match; check for errors/drops.
7. **Check backend:** metric name, unit, attributes, temporality, and Resource labels align.
8. **Check cardinality:** series count across instruments, attributes, buckets, and instances fits budget.
9. **Check shutdown:** provider closes/flushes per lifecycle so the final batch is not lost on graceful shutdown.
10. **Cross-check Micrometer:** if the app has Actuator, determine which metrics flow through `MeterRegistry` and which go directly through OTel to avoid double counting.

### Test Matrix

| Test | Expected Result |
| --- | --- |
| Create counter and increment 3 times | Counter total reflects 3 per temporality/backend semantics |
| Record histogram with known values | Count/sum/buckets reflect measurements |
| Set Resource service name | Metric stream carries accurate resource/service identity |
| Omit registering `MetricReader` | No export pipeline runs via that reader |
| Collector unreachable | Export errors/retries/drops observed; backend lacks data |
| Change trace sampling probability | Does not directly alter counter metrics |
| Add attribute with millions of values | Cardinality surges; must be removed/bounded |
| Close `ObservableGauge` | Callback stops being collected after lifecycle ends |
| Switch cumulative to delta | Backend query/aggregation must interpret temporality accurately |
| Record same event in two registries | Risk of double counting when backend ingests both series |

## 14. Scenario Exercise

A Spring Boot application has two pipelines. HTTP server metrics and business counters are created through Micrometer, while an internal library records an OTel Counter directly. After deployment, dashboards show accepted orders at nearly double the actual volume.

**Questions:**

1. Why doesn't `SdkMeterProvider` automatically merge the Micrometer registry and OTel metrics into one pipeline?
2. How can you verify the event is being recorded in both places?
3. If you keep the OTel SDK for the library, what must be ensured about the provider, resource, and exporter?
4. Should you attach `orderId` to the OTel Counter to track individual orders?

**Analysis Hints:**

- Micrometer `MeterRegistry` and OpenTelemetry `SdkMeterProvider` are distinct implementations/pipelines unless a specific bridge/integration connects them.
- Inspect metric names, resource attributes, exporter outputs, and call sites incrementing counters; the same event may be emitted into both pipelines and summed together on the dashboard.
- Choose a single owner for the measurement or explicitly separate two metrics with distinct semantics; avoid summing them as the same event.
- If keeping OTel, ensure instrumentation receives the right `MeterProvider`, `SdkMeterProvider` has an active `MetricReader`/exporter, `Resource` uses a consistent service identity, and lifecycle closes properly.
- Never place `orderId` into metric attributes due to high cardinality; use traces/logs/controlled business queries to investigate individual transactions.

### Completion Checklist

| Topic | Can Explain / Verify |
| --- | --- |
| API and SDK | Distinguish `MeterProvider` and `SdkMeterProvider` |
| Meter and instruments | Pick Counter, UpDownCounter, Histogram, Gauge by semantics |
| Resource | Set stable service identity |
| `MetricReader`/exporter | Explain collection and export |
| `PeriodicMetricReader` | Understand interval, batching, and lifecycle |
| Views | Control aggregation, buckets, and attributes |
| Cardinality | Avoid Trace ID/order ID/raw URL as metric attributes |
| Temporality | Distinguish cumulative and delta |
| Observable instruments | Lightweight callback, registered once, closed cleanly |
| Spring Boot boundary | Avoid accidentally spinning up two Micrometer/OTel pipelines |
| End-to-end | Verify measurement, export, ingestion, and backend queries |

**Key takeaway:** `SdkMeterProvider` is the SDK hub managing `Meter`s, instruments, `Resource`, `View`s, and `MetricReader`s to collect metrics. Instrumentation records measurements; readers collect them; exporters ship data; backends store and query history. In Spring Boot, clearly pick Micrometer-first or OpenTelemetry SDK-first per measurement, prevent double counting, bound attribute cardinality, verify temporality, and manage lifecycle cleanly. Metrics correlate with logs and traces in the backend yet keep separate sampling and pipelines; never use Trace ID as a metric label or treat `SdkMeterProvider` as a metric store.
