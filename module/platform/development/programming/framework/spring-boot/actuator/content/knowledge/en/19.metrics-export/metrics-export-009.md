# Distinguishing OTLP Metrics Export from OTLP Trace Export

## 1. One Protocol, Two Different Kinds of Questions

When you see both `/v1/metrics` and `/v1/traces` on the same Collector, it is tempting to assume that simply enabling "OTLP" makes the application send all telemetry automatically. To configure it properly, separate **what type of data is produced** from **which protocol transports it**.

**Metrics** are numeric measurements organized by name, timestamp, and attribute set. They answer aggregate questions: what is the throughput, is the error rate rising, how much memory is in use, and how is latency distributed?

**Traces** capture the execution path of a single invocation, potentially spanning multiple services. A trace consists of **spans**; each span describes an operation with start/end timestamps, identifiers, and relationships to other operations. Traces help investigate a specific execution: where did this request travel, which step was slow, and which operation failed?

| Criterion | Metrics | Trace |
| --- | --- | --- |
| Unit of observation | Numeric data points, counters, distributions, or gauges | Spans belonging to a trace |
| Typical perspective | Aggregated behavior over time | A single execution and relationships among operations |
| Examples | Request counts, memory usage, latency distributions | Server span receiving a request, client span calling another service |
| Analysis keys | Metric name and attribute set | Trace ID, Span ID, parent–child links, and attributes |
| Typical question | "What was the error rate over the last 5 minutes?" | "Which step failed for this errored request?" |

Suppose three operations take 10, 20, and 90 ms:

- A timer can record a count of 3 and total time of 120 ms, yielding an average of 40 ms.
- The corresponding spans can retain per-operation details and relationships inside traces.
- Knowing only the 40 ms average is insufficient to reconstruct the latency and path of each individual request.
- Having a few slow traces is also insufficient to infer the slow-request rate across all traffic without understanding sampling.

Metrics and traces complement each other. Use metrics to see which service group has rising error rates, then investigate affected executions with traces. Data concepts are presented in OpenTelemetry's documentation on [metrics](https://opentelemetry.io/docs/concepts/signals/metrics/) and [traces](https://opentelemetry.io/docs/concepts/signals/traces/).

## 2. OTLP Is Not a Single Switch for All Signals

OTLP stands for **OpenTelemetry Protocol**, a transport protocol for observability data. The same protocol family defines distinct message types for each signal.

For OTLP/HTTP, the default paths are:

| Signal | Default Path | Request Type |
| --- | --- | --- |
| Metrics | `/v1/metrics` | `ExportMetricsServiceRequest` |
| Traces | `/v1/traces` | `ExportTraceServiceRequest` |

Both use HTTP POST, yet their payloads have distinct schemas. Changing the URL suffix does not convert a batch of metrics into spans. A receiver can support both, yet it still handles each signal separately.

OTLP also supports gRPC transport. The standard port is 4318 for HTTP and 4317 for gRPC. Those are protocol defaults, not proof that the port is open on a given host. Examples in this article use **OTLP/HTTP**; do not change 4318 to 4317 while leaving HTTP sender configuration intact.

These paths and message types are defined in the [OTLP specification](https://opentelemetry.io/docs/specs/otlp/).

Distinguish three names that frequently appear together:

- **OpenTelemetry:** the collection of APIs, SDKs, specifications, and tools for observability.
- **OTLP:** the data-exchange protocol.
- **OpenTelemetry Collector:** the process that receives, processes, and forwards telemetry.

Using OTLP in an application does not by itself mean every measurement was produced via the OpenTelemetry Metrics SDK. In this article's Spring Boot 3.3 setup, metrics are recorded through **Micrometer MeterRegistry**, and the OTLP registry converts them into OTLP data. Tracing uses Micrometer Tracing with the OpenTelemetry bridge and a span exporter.

## 3. Two Pipelines in Spring Boot 3.3

### 3.1. The Metrics Pipeline

```text
Counter / Timer / Gauge
        |
        v
Micrometer MeterRegistry
        |
        v
OtlpMeterRegistry
        |
        v
POST /v1/metrics
        |
        v
Collector: metrics pipeline
```

`MeterRegistry` manages measurement instruments. `OtlpMeterRegistry` is one way to export measurements to an OTLP receiver. A Prometheus registry or another registry is a different export option.

JVM meters can generate data even when the application receives no HTTP requests. A business counter changes only when application code actually increments that counter.

Spring Boot auto-configures the appropriate registry based on dependencies and activation conditions. See [metrics in Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

### 3.2. The Trace Pipeline

```text
Instrumented operation
        |
        v
Micrometer Observation / Micrometer Tracing
        |
        v
OpenTelemetry bridge and span builder
        |
        v
Span processor -> OTLP span exporter
        |
        v
POST /v1/traces
        |
        v
Collector: traces pipeline
```

**Instrumentation** means making an operation observable. The HTTP server may already be instrumented by the framework; a custom application operation may require creating an observation or span explicitly.

The trace export path requires instrumented operations, a tracing system, sampling decisions, and an appropriate exporter. Having an export dependency without creating spans leaves no business traces to send.

Conversely, seeing a trace context or Trace ID in logs only shows that tracing context was created/propagated. It does not prove the storage backend received the spans.

### 3.3. Observation Is a Shared Entry Point, Not a Single Merged Exporter

`ObservationRegistry` manages observation configuration and handlers reacting to observation lifecycles. `MeterRegistry` manages measurements. These two types serve different roles.

When corresponding handlers are configured, a single observation can feed both metrics and tracing:

```text
                        -> metrics handler -> MeterRegistry
Operation Observation
                        -> tracing handler -> spans and trace exporter
```

However:

- Incrementing a `Counter` directly does not automatically create a span.
- Creating a span via `Tracer` does not automatically mean a corresponding business metric was recorded.
- An observation can feed both while each keeps its own export schedule, filters, storage, and transport failures.

In Boot 3.3, an observation's low-cardinality keys are used for both metrics and traces; high-cardinality keys go only to traces in this mechanism. Therefore, do not put Trace IDs or unique request IDs into metric tags trying to "link" every data point to individual requests.

See [Boot 3.3 Observation mechanics](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html) and [Micrometer Observation lifecycle](https://docs.micrometer.io/micrometer/reference/observation/introduction.html). Using high-cardinality tags on traces still warrants caution around sensitive data and cost; traces are not a dumping ground for arbitrary input data.

## 4. Dependencies and Configuration Must Match Each Pipeline

This article pins Spring Boot **3.3.x**, with runnable examples on version **3.3.13**. Do not copy property names or starters from newer Boot versions assuming they exist in the 3.3 branch.

### 4.1. Core Dependencies

Beyond Actuator, each pipeline needs:

| Purpose | Main Dependency in Example |
| --- | --- |
| Export Micrometer metrics via OTLP | `io.micrometer:micrometer-registry-otlp` |
| Bridge Micrometer Tracing to OpenTelemetry | `io.micrometer:micrometer-tracing-bridge-otel` |
| Export OpenTelemetry spans via OTLP | `io.opentelemetry:opentelemetry-exporter-otlp` |

Although the artifact name `opentelemetry-exporter-otlp` covers more than just "trace exporter," adding it to a Boot 3.3 app **does not automatically bridge Micrometer meters to the OpenTelemetry Metrics SDK**. In this example, the metrics path still needs the dedicated OTLP registry.

Boot 3.3 does not auto-configure OpenTelemetry SDK metrics pipelines simply because the SDK is on the classpath. Do not simultaneously attach a Java Agent or another OpenTelemetry starter in this example; those are alternative integration models that can change how telemetry is produced and cause duplicate writes if layered without control.

The tracing dependency combination is confirmed in [Boot 3.3 Tracing](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html).

### 4.2. Two Separate Property Branches

| Setting | OTLP Metrics | OTLP Trace in Boot 3.3 |
| --- | --- | --- |
| Ingestion target | `management.otlp.metrics.export.url` | `management.otlp.tracing.endpoint` |
| Outbound headers | `management.otlp.metrics.export.headers.*` | `management.otlp.tracing.headers.*` |
| Metrics export step | `management.otlp.metrics.export.step` | Does not use metrics step key |
| Trace sampling | Not controlled by tracing sampling config | `management.tracing.sampling.probability` |
| Disabling the branch | `management.otlp.metrics.export.enabled=false` | `management.tracing.enabled=false` disables broader tracing auto-configuration |

The last tracing toggle in the table covers both span export and trace propagation under Boot auto-configuration; do not mistake it for disabling only a target endpoint. Custom Java or application-owned integrations must be evaluated separately.

The asymmetry between `url` and `endpoint` is real. These keys are not interchangeable:

```properties
management.otlp.metrics.export.url=http://127.0.0.1:4318/v1/metrics
management.otlp.tracing.endpoint=http://127.0.0.1:4318/v1/traces
```

A misspelled key might not raise an obvious startup error; the application may fall back to defaults or lack the intended exporter. Always verify against the [Boot 3.3 property appendix](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html) and inspect received telemetry.

### 4.3. Same Collector Still Needs Separate Auth Settings

If the receiver requires authentication, each branch needs its own headers:

```yaml
management:
  otlp:
    metrics:
      export:
        headers:
          Authorization: "Bearer ${METRICS_OTLP_TOKEN}"
    tracing:
      headers:
        Authorization: "Bearer ${TRACES_OTLP_TOKEN}"
```

This adds onto a complete configuration for receivers that actually require Bearer tokens. The two variables may hold the same or different values depending on system permissions. Header configuration for metrics is not copied automatically to the tracing branch.

In production, inject tokens via environment secret mechanisms and use HTTPS per receiver contract. In the local lab below, the receiver listens only on loopback without tokens so we can focus on differences between the two signals.

## 5. Distinguishing Export Step from Trace Sampling

### 5.1. Step Answers "How Often Are Metrics Published?"

For example, `management.otlp.metrics.export.step=10s` configures the OTLP registry's export interval. It does not mean recording only one in ten requests, or recording events only on every tenth second.

Counters can be incremented on every call; when the export step arrives, the registry sends data points formatted according to the meter's semantics and export settings. One data point can represent many operations. Do not assume each business request triggers a separate OTLP HTTP request.

### 5.2. Sampling Answers "Which Traces Are Selected for Recording/Export?"

`management.tracing.sampling.probability` controls trace sampling probability in the tracing system. Boot 3.3 defaults to 0.1; in a learning environment you can set 1.0 to see traces easily.

For requests starting a new trace, a probability of 0.1 does not guarantee exactly one trace is kept out of every ten requests. For traces arriving from upstream systems, sampling decisions also involve parent context and the active sampler.

Changing probability to 0.0 does not stop `Counter.increment()` calls in the application from running. Conversely, disabling the OTLP metrics registry does not disable the span exporter.

| Configuration Change | What Changes Directly | What Must Not Be Inferred |
| --- | --- | --- |
| Metrics step 10s -> 30s | Metrics export cadence | Trace retention probability drops |
| Trace sampling 1.0 -> 0.1 | Trace sampling decision | Only 10% of events are counted by counters |
| Change metrics URL | Metrics send destination | Trace send destination changes automatically |
| Remove OTLP metrics registry | Ability to export via this registry | All tracing was removed |

### 5.3. Span Batching Schedule Is a Third Concept

A span typically must finish before being processed for export. The tracing system can batch spans with its own queue, flush schedule, and timeouts. Those mechanisms are distinct from whether a trace was sampled.

Do not use `management.otlp.metrics.export.step` to tune span batching. Nor should you invent a `management.otlp.tracing.step` property just to make the two branches look symmetrical.

Because there are two exporters, do not expect metrics and spans to arrive in the same network packet, same second, or same batch count.

## 6. Collector Shares a Receiver Yet Needs Two Pipelines

A single OTLP receiver can accept multiple signals, yet processing pipelines are still declared per signal type:

```text
                        -> metrics pipeline -> metrics destination
Shared OTLP/HTTP Receiver
                        -> traces pipeline  -> trace destination
```

Declaring the receiver only defines the ingestion component. You must wire it into the appropriate pipelines under `service.pipelines`. Having only a traces pipeline does not create a metrics path.

Processors and destinations can also differ: traces might pass through Collector filtering/sampling; metrics might pass through separate transformations or aggregations. Adding a span-to-metrics connector is extra configuration, not something OTLP performs automatically by default.

Pipeline-based component activation is described in [OpenTelemetry Collector configuration](https://opentelemetry.io/docs/collector/configuration/).

## 7. Lab: One Operation Producing Both Metrics and Spans

This lab is a standalone Maven project for learning the mechanics, not instructions to alter the structure of your working module. Prepare JDK 21, Maven, dependency download access, and a Collector build with the `otlp` receiver and `debug` exporter.

The application and Collector run directly on the same host; ports 8080 and 4318 must be free. If using containers, adjust network addresses and listen interfaces; `127.0.0.1` in two separate containers does not refer to the same process.

### 7.1. Creating the Minimal Project

Structure:

```text
otlp-signals-demo/
├── pom.xml
├── collector.yml
└── src/main/
    ├── java/example/OtlpSignalsApplication.java
    └── resources/application.yml
```

`pom.xml` pins the Boot version so dependencies for both pipelines are managed consistently:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>otlp-signals-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-registry-otlp</artifactId>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-tracing-bridge-otel</artifactId>
        </dependency>
        <dependency>
            <groupId>io.opentelemetry</groupId>
            <artifactId>opentelemetry-exporter-otlp</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`src/main/java/example/OtlpSignalsApplication.java`:

```java
package example;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class OtlpSignalsApplication {
    public static void main(String[] args) {
        SpringApplication.run(OtlpSignalsApplication.class, args);
    }
}

@RestController
class DemoController {
    private final Counter calls;
    private final ObservationRegistry observations;

    DemoController(MeterRegistry meters, ObservationRegistry observations) {
        this.calls = Counter.builder("signal.demo.calls").register(meters);
        this.observations = observations;
    }

    @GetMapping("/demo")
    public String demo() {
        calls.increment();
        return Observation.createNotStarted("signal.demo.work", observations)
                .lowCardinalityKeyValue("operation", "demo")
                .observe(() -> "ok\n");
    }
}
```

Each call to `/demo` performs two distinct actions:

1. `calls.increment()` increments the `signal.demo.calls` counter.
2. Observation `signal.demo.work` wraps an operation returning a string, allowing the observation mechanism to produce both a timer and a span when the required handlers are configured.

The HTTP server also has an observation/span for serving the request. Therefore one call does not necessarily correspond to exactly one span. The business counter in the example increments only on `/demo`; reading diagnostic endpoints does not increment it.

This is complete Spring Boot source within the project above. Do not compile just the Java file with `javac` without the dependency classpath; Maven handles compiling and running with the required libraries.

### 7.2. Configuring Both Exporters

`src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: otlp-signals-demo

server:
  address: 127.0.0.1
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: "health,metrics"
  otlp:
    metrics:
      export:
        enabled: true
        url: http://127.0.0.1:4318/v1/metrics
        step: 10s
    tracing:
      endpoint: http://127.0.0.1:4318/v1/traces
  tracing:
    sampling:
      probability: 1.0
```

Points to read carefully:

- There are **two full URLs**, one for each signal type.
- `step: 10s` sits under the metrics export branch.
- `probability: 1.0` sits under the tracing sampling branch.
- The `metrics` endpoint is exposed solely for local lab diagnostics; external export does not require exposing it.
- HTTP over loopback is used for the lab; remote receiver configs must follow their own TLS and authentication requirements.

### 7.3. Configuring the Collector

`collector.yml`:

```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 127.0.0.1:4318

exporters:
  debug:
    verbosity: detailed

service:
  pipelines:
    metrics:
      receivers: [otlp]
      exporters: [debug]
    traces:
      receivers: [otlp]
      exporters: [debug]
```

Both pipelines share the `otlp` receiver and print received telemetry via `debug`. The `debug` exporter lets you inspect received payloads; it is not a long-term store or trace search UI.

Open the first terminal in the project directory and run your installed Collector:

```shell
otelcol --config=collector.yml
```

The executable name may be `otelcol.exe` or `otelcol-contrib` depending on your installation; use the executable that includes the configured components. Check startup logs to confirm the receiver and both pipelines are running.

Open a second terminal in the directory containing `pom.xml`:

```shell
mvn spring-boot:run
```

Wait for the application to start up cleanly. Maven commands must run with JDK 21; check `mvn -version` if the terminal's Java version does not match.

### 7.4. Generating Telemetry and Reading Results

In PowerShell, send three requests with `curl.exe`:

```powershell
1..3 | ForEach-Object {
    curl.exe --fail --silent --show-error http://127.0.0.1:8080/demo
}
```

Stdout of the three successful responses:

```text
ok
ok
ok
```

Read the counter:

```powershell
curl.exe --fail --silent --show-error http://127.0.0.1:8080/actuator/metrics/signal.demo.calls
```

In a fresh run where nobody else called `/demo` besides those three calls, the `COUNT` measurement must be 3. The actual output is JSON describing the meter; do not rely on exact field order or whitespace in the JSON.

After a couple of intervals, check the Collector terminal:

- **Metrics branch:** shows metric `signal.demo.calls` and measurements from observation `signal.demo.work`; JVM/framework metrics may also appear.
- **Traces branch:** shows spans for operation `signal.demo.work`, with Trace ID/Span ID and execution timestamps.
- The operation span runs inside the HTTP request context, so its relationship to the server span can be observed.

Do not expect the counter, timer, and spans to appear in the exact same log printout. Block headings and formatting depend on the Collector version; identify the signal type and metric/span names rather than matching a hardcoded log snippet with fixed IDs.

### 7.5. Experimenting with Trace Sampling Set to 0

Stop the **application** while leaving the Collector running. Restart the application with:

```shell
mvn spring-boot:run "-Dspring-boot.run.arguments=--management.tracing.sampling.probability=0.0"
```

Call `/demo` three times with fresh requests that do not send `traceparent` or any parent trace context. Evaluate only telemetry whose timestamps belong to the new run.

Results to verify:

| Observation | Expected in This Experiment |
| --- | --- |
| Business response | Still prints three lines of `ok` |
| Counter in new process | `COUNT = 3` |
| OTLP metrics | Still sent per registry configuration |
| New spans for the three root requests | Not selected for export at 0.0 probability |

The Collector may still print older batches or fresh JVM metrics; those are not new `/demo` traces. Likewise, do not conclude "there is no Trace ID" merely because spans were not exported: trace context and export decisions are separate concerns.

### 7.6. Disabling Only the OTLP Metrics Export Path

Stop the application and restart with sampling 1.0 and the OTLP metrics registry disabled:

```shell
mvn spring-boot:run "-Dspring-boot.run.arguments=--management.tracing.sampling.probability=1.0 --management.otlp.metrics.export.enabled=false"
```

Call `/demo` and compare using the new timestamps:

- Traces can still be created and exported via the configured tracing pipeline.
- The OTLP metrics registry is disabled, so metric batches are no longer published through this branch.
- That does not mean all in-app measurements vanish: another registry or diagnostic registry may still exist under auto-configuration.

Restore the full configuration when finished. Each restart resets the example's in-memory counter; do not compare absolute counter values across two separate processes and mistake that for transit data loss.

## 8. Verifying Each Signal with the Right Kind of Evidence

### 8.1. Evidence for Metrics

You can verify across three layers:

1. **In the application:** the meter exists and its value changes when the operation runs.
2. **At the OTLP receiver:** metrics arrive with the expected names, attributes, and timestamps.
3. **In the storage backend:** queries return the matching time series after forwarding.

`/actuator/metrics` is for inspecting meters inside the application. It is neither an OTLP ingestion endpoint nor evidence that spans reached the Collector.

If data appears on a dashboard under a name transformed by the storage backend, do not confuse that name with the name needed at the Actuator endpoint. Know which naming convention each layer uses.

### 8.2. Evidence for Traces

Follow a sampled request:

1. Is the operation actually instrumented for tracing?
2. Was the span created and ended?
3. Did the sampling decision permit recording/exporting it?
4. Did the exporter send to the right trace ingestion branch?
5. Can the trace and expected spans be found at the receiver or storage backend?

Seeing a Trace ID in logs is insufficient to confirm steps 4–5 succeeded. Conversely, missing a specific trace does not mean metrics for that request were skipped.

In the lab, Collector `debug` logs prove telemetry reached the collector. To prove long-term persistence, add a real exporter/storage backend and query it there; the `debug` exporter does not provide that evidence.

### 8.3. Trace Context Propagation and Span Export Are Separate Paths

Between two services, trace context can travel in headers of **business requests**. Spans are exported to the Collector over a separate connection:

```text
Service A -- business request + trace context --> Service B
    |                                                 |
    +-- export spans --> Collector <-- export spans --+
```

Both A and B exporting spans successfully without propagating context properly still yields disconnected traces. A system that propagates context properly while an exporter fails will also leave an incomplete trace dataset in storage.

When using HTTP clients in Boot, use Boot-configured builders to preserve observability integration and context propagation. With async flows or multiple threads, check context propagation explicitly; having a metrics registry does not handle this.

### 8.4. Do Not Compare Span Counts the Same Way as Counters

A single request can generate a server span, business span, client span, and several more spans. Some traces can be sampled out or dropped at the application/Collector. Batches can also arrive at different times.

Therefore, do not use a rule like "span count must equal request count" to validate the export pipeline. In the example, you can expect three `signal.demo.work` spans only when those three calls were instrumented, sampled, and collected completely under lab conditions.

For the same reason, total observed spans are not a reliable denominator for system-wide error rates unless sampling policies are accounted for. Metrics recorded directly in the application and metrics derived from spans are two distinct data sources and must be identified clearly before comparing.

## 9. Mistakes to Spot Immediately

| Claim or Symptom | Correct Analysis |
| --- | --- |
| "We have `micrometer-registry-otlp`, so we definitely have traces" | That dependency serves the metrics registry; check the tracing bridge, span exporter, and instrumented operations |
| "We have `opentelemetry-exporter-otlp`, so all Micrometer meters are sent" | Check the metrics registry and its config; that artifact does not bridge separate metrics APIs automatically |
| "Metrics reached the Collector, so traces must have too" | Check the trace URL, traces pipeline, sampling, and span payloads separately |
| "Increase sampling to 1.0 to fix missing metrics" | Trace sampling does not make counters increment more; investigate the metrics path separately |
| "Change `step` to reduce span send latency" | That step belongs to the metrics registry; check the span processor path |
| "Changing `/v1/metrics` to `/v1/traces` converts the data" | Payload schemas do not change with a URL string; you need the exporter for that signal |
| "Just exposing Actuator endpoints makes the Collector pull traces" | The example uses two exporters that actively POST; diagnostic endpoints do not export spans for them |
| "Same host/port means metrics headers apply to traces too" | Headers are configured in two separate branches; permissions per signal type can differ |
| "Three requests means the backend must contain exactly three spans" | One request can produce multiple spans and is still subject to sampling |
| "A Trace ID on a metric means the whole trace is stored" | Links or exemplars, when supported, only aid navigation; still verify the trace actually exists in storage |
| "Running a Java Agent alongside the example gives identical output" | An Agent is a different integration model; naming conventions and sources can differ and cause duplicate telemetry |

When only one signal is missing, verify step by step: **telemetry producer -> instrumentation -> filter/sampling decision -> exporter -> ingestion endpoint -> pipeline -> storage backend**. Avoid changing settings in both branches at once, or it becomes hard to tell which change resolved the issue.

## 10. Scenario Self-Check

**Scenario 1: JVM metrics appear, yet no traces appear even though the app starts normally.**

JVM metrics can come from default meters without any business requests. Check the tracing pipeline and trigger an instrumented operation first; do not treat JVM metrics as proof that spans were created.

**Scenario 2: After setting sampling to 0.0, the `signal.demo.calls` counter still increments. Is that a contradiction?**

No. The counter increment still executes whenever `/demo` is called. Trace sampling decisions do not disable that call. In the lab, new root requests without parent context have no spans selected for export, while metrics continue to be recorded and exported.

**Scenario 3: Both URLs point to the same Collector; the metrics branch receives HTTP 401 while traces are accepted.**

Check headers, credentials, and permissions on the metrics branch specifically, along with gateway/receiver policies. Sharing a host does not prove both requests send the same credentials or hold the same permissions.

**Scenario 4: The metrics dashboard shows a group of slow requests, yet you cannot find a trace for one specific request.**

That trace might not have been sampled, may have expired from retention, been filtered, failed in transit, or been queried with the wrong criteria. Aggregated metrics lack the detail required to reconstruct an unstored trace.

**Scenario 5: Both services send spans, yet their operations do not appear in the same trace.**

Check context propagation across business requests and across asynchronous boundaries. Exporting spans from each service and preserving relationships between them must be verified separately.

After this lesson, you should be able to explain three things from configuration and evidence: **what telemetry is generated, which exporter sends it, and where receipt of that exact signal is confirmed**.
