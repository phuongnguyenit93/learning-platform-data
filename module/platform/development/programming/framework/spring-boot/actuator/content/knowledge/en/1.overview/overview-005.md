# Relationship Between Spring Boot Actuator, Micrometer, and External Monitoring Systems

When you want to know how much work an application has processed, you need a way to record it in Java code. When you want to pull data from a running application, you need an access path or export mechanism. When you want to view trends over many hours and trigger alerts, you need somewhere to collect, store, and query data.

Spring Boot Actuator, Micrometer, and external monitoring systems participate in those tasks with distinct responsibilities. Understanding how they relate helps you avoid situations like “added the library yet dashboards are still empty” or “metrics appear in the application yet there is no history”.

This lesson uses Spring Boot 3.3 as the baseline for configuration. Follow the data path: **measure inside the app → register and convert → collect externally → store, query, and alert**.

## 1. Responsibility Map

| Component | Primary responsibility in the metrics flow | Example |
| --- | --- | --- |
| Application code and instrumented libraries | Record events, durations, or state to measure | A completed task increments a counter |
| Micrometer | Provide the metrics API and integration mechanisms for target backends | `Counter`, `Timer`, `MeterRegistry` |
| Spring Boot Actuator and auto-configuration | Integrate operational capabilities into Spring Boot and expose management access points | `health`, `metrics`, `prometheus` |
| External monitoring system | Collect, store, and analyze data over time | Prometheus or an equivalent monitoring service |
| Visualization and alerting tools | Query, present data, and notify when conditions are met | Grafana; Prometheus rules paired with Alertmanager |

Rows represent responsibilities; each row does not have to run on a separate server. One product may provide multiple functions, while a large system may split them across separate services.

Micrometer describes itself as a vendor-neutral application metrics facade. Spring Boot Actuator integrates Micrometer and provides auto-configuration for registries found on the classpath. Refer to [Spring Boot 3.3 — Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

### 1.1. A Concrete Flow with Prometheus

```text
INSIDE THE SPRING BOOT PROCESS

Business logic / built-in instrumentation
             │ records
             ▼
       Micrometer meters
             │
             ▼
    PrometheusMeterRegistry
             │ provides formatted data
             ▼
 Actuator's /actuator/prometheus

OUTSIDE THE PROCESS

Prometheus ── periodic HTTP GET ──> /actuator/prometheus
Prometheus <── returned payload ──── /actuator/prometheus
     │
     ├─ Stores metric samples over time
     ├─ Queries via PromQL
     └─ Evaluates alert rules

Grafana ── queries ──> Prometheus data source
```

In this model, Prometheus actively pulls data. The application simply answers each scrape request; adding the registry does not create a Prometheus server or a dashboard.

[Prometheus Overview](https://prometheus.io/docs/introduction/overview/) describes storing metrics as time series and the active HTTP scraping model. This is one specific integration style; not every monitoring system collects data in the same direction.

## 2. What Does Micrometer Provide?

### 2.1. Meters, Registries, and Tags

In Micrometer, a **meter** is an object that measures a quantity. Three common types:

- `Counter`: counts how many times an event happens, such as completed tasks.
- `Timer`: records duration and invocation count of an operation.
- `Gauge`: reads a current state value, such as queue length.

A **Registry (`MeterRegistry`)** manages meters and provides behavior suited to the target backend. **Tags (`tag`)** add classification dimensions—for example, the same task metric split by `result=success` and `result=failure`.

A `Counter` only increases by positive amounts. For operational monitoring, rate of increase over a time window is usually more useful than the cumulative total since startup. If you already use a `Timer` for an operation, it also tracks invocation count; avoid adding a redundant counter without a distinct purpose. See [Micrometer 1.13 — Counters](https://docs.micrometer.io/micrometer/reference/1.13/concepts/counters.html).

### 2.2. Why Are Backend-Specific Registries Needed?

A single common Java API does not mean all external systems share one format. The matching registry translates names, representations, and delivery mechanics for the destination system.

For example, a name in code might be `learning.tasks.completed`, while when exported for Prometheus it can be converted to underscore-separated form with a counter suffix. Therefore, distinguish **the meter name inside the application** from **the exported series name**. Naming conventions are described in [Micrometer 1.13 — Naming Meters](https://docs.micrometer.io/micrometer/reference/1.13/concepts/naming.html).

Do not guess names merely by replacing dots: units, meter types, and registry conventions also matter. When writing queries, verify the actual exported output.

### 2.3. In-Memory Registries vs. Exporting Registries

`SimpleMeterRegistry` keeps values in memory and does not export data anywhere. `PrometheusMeterRegistry` formats data for Prometheus scraping. `CompositeMeterRegistry` can combine multiple registries.

Registries are not shared historical stores across processes. In particular, creating a new registry does not inherit values from an older registry. See [Micrometer — Registry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html).

In a Spring Boot application, use the Spring-managed `MeterRegistry` when recording metrics for the configured backend. If a component constructs `new SimpleMeterRegistry()` itself and increments meters only there, those measurements will not automatically appear in the registry used by Actuator or your exporter.

## 3. Java Experiment: Micrometer Working Independently of Actuator

This experiment requires only Micrometer, without running Spring Boot or opening an HTTP server. Its goal is to clearly separate **recording metrics** from **exposing and storing metrics externally**.

### 3.1. Prepare Dependencies

Use JDK 17 or newer and a Gradle version compatible with that JDK. In a dedicated experiment directory, create `settings.gradle`:

```groovy
rootProject.name = 'metric-boundary-demo'
```

Create `build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.micrometer:micrometer-core:1.13.6'
}

tasks.register('copyMetricLibraries', Copy) {
    from configurations.runtimeClasspath
    into layout.projectDirectory.dir('lib')
}
```

The version is pinned so the experiment is easy to reproduce. This is a standalone Java project; the Spring Boot integration section below uses Spring Boot’s dependency version management.

### 3.2. Complete Program

Save `MetricBoundaryDemo.java` in the same directory as the two Gradle files:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public class MetricBoundaryDemo {
    public static void main(String[] args) {
        SimpleMeterRegistry first = new SimpleMeterRegistry();
        Counter completed = first.counter(
                "learning.tasks.completed", "result", "success");
        completed.increment();
        completed.increment(2);

        System.out.println("first=" + completed.count());
        System.out.println("meters=" + first.getMeters().size());
        first.close();

        SimpleMeterRegistry second = new SimpleMeterRegistry();
        Counter fresh = second.counter(
                "learning.tasks.completed", "result", "success");
        System.out.println("new=" + fresh.count());
        second.close();
    }
}
```

PowerShell commands, assuming `gradle`, `javac`, and `java` are on your PATH:

```powershell
gradle copyMetricLibraries
javac -encoding UTF-8 -cp "lib/*" MetricBoundaryDemo.java
java -cp ".;lib/*" MetricBoundaryDemo
```

On Linux/macOS, the classpath separator in the run command is `:`:

```bash
java -cp ".:lib/*" MetricBoundaryDemo
```

The Gradle command downloads libraries and requires Maven repository access if not cached. Expected standard output from the Java program alone:

```text
first=3.0
meters=1
new=0.0
```

### 3.3. Explaining the Output

- `first=3.0`: two increments of 1 and 2 yield a total of 3 in the first registry.
- `meters=1`: the program registered only one meter in that registry.
- `new=0.0`: the second registry starts with a fresh counter despite having the same name and tag.

In this test, console printing is done directly by `System.out.println`. That is not metric export to a monitoring system. There is no `/actuator/metrics`, no Prometheus history, and no alerting.

This output shows Micrometer can run outside Spring Boot. Adding Actuator to a Spring Boot app adds integration and operational access points; adding an external monitoring system lets you collect and analyze data over time.

## 4. How Does Actuator Connect Metrics to a Spring Boot Application?

Actuator provides operational access points. In Spring Boot 3.3, an endpoint must be enabled and exposed over the relevant transport before it can be used there; HTTP access is also governed by the security layer.

By default, only `health` is exposed over HTTP. Adding the Actuator dependency does not mean every endpoint is reachable over the network. See [Spring Boot 3.3 — Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

### 4.1. Two Metrics Access Points with Different Purposes

| Access point | Audience and purpose |
| --- | --- |
| `/actuator/metrics` | Developers or operators inspecting registered meter names and values |
| `/actuator/prometheus` | Prometheus scraping metrics in the matching format |

The `metrics` API is not designed as a periodic scraping target or operational metric store. It is useful for checking what the application has recorded. Its structure and purpose are detailed in [Actuator Metrics REST API 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html).

The `prometheus` endpoint requires the matching registry along with HTTP exposure. Micrometer can still serve Prometheus data without Actuator, but the application then has to wire its own HTTP handler. See [Micrometer 1.13 — Prometheus](https://docs.micrometer.io/micrometer/reference/1.13/implementations/prometheus.html).

### 4.2. Conditions to Verify Separately

With the Prometheus-scraping-Actuator model, distinguish:

1. Does the application actually record the needed metric?
2. Which registry receives the metric?
3. Are the Prometheus registry and matching endpoint present?
4. Is the endpoint exposed and reachable by the scraper?
5. Does Prometheus have the right target, address, and path configured?
6. Was data actually stored while the query or filter is wrong?

For example, seeing a metric in `metrics` is good evidence on the application side. It does not prove Prometheus has ever scraped it successfully.

## 5. Hands-On: Connecting a Spring Boot Application to Prometheus

This section shows **configuration snippets for an existing Spring Boot 3.3 web application**, not the standalone Java project in section 3. Assume the app runs on port 8080 with default `/actuator` prefix and root context path.

### 5.1. Dependencies on the Application Side

In the `dependencies` block of a project already using the Spring Boot plugin/BOM for version management, add the relevant dependencies:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-actuator'
runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
```

These are additions; the web application still needs its web dependency and existing main class. Do not copy the standalone Java project’s build config to replace Spring Boot’s setup.

### 5.2. Configuration for a Study Environment

Merge into `application.yml` for the test environment:

```yaml
spring:
  application:
    name: actuator-lab

management:
  endpoints:
    web:
      exposure:
        include: "health,metrics,prometheus"
  metrics:
    tags:
      application: "actuator-lab"
```

The `application` tag in this example is set explicitly to identify the data. Do not assume `spring.application.name` automatically becomes a tag in every destination system.

Exposing endpoints does not replace authentication and authorization. The example configuration assumes a controlled test network; if the app uses Spring Security, configure read access per your existing security rules.

### 5.3. Check the Application Side First

On Windows:

```powershell
curl.exe -i "http://localhost:8080/actuator/metrics"
curl.exe -i "http://localhost:8080/actuator/metrics/jvm.memory.used"
curl.exe -i "http://localhost:8080/actuator/prometheus"
```

The second command applies only when `jvm.memory.used` appears in the list. For a typical JVM application with default instrumentation enabled, this is a convenient check without creating a new business API.

Actual values vary by process. Inspect units, tags, and exported names; do not expect a fixed memory number. The two endpoints also return different formats: JSON diagnostic payloads versus Prometheus/OpenMetrics text format where supported.

The `learning.tasks.completed` counter from section 3 belonged to a separate program, so it **does not automatically appear in this Spring Boot app**. To record similar business metrics in Spring Boot, business code must write to the `MeterRegistry` managed by the application.

### 5.4. Configuration on the Prometheus Side

If Prometheus and the application run directly on the same machine, a minimal `prometheus.yml` could be:

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: "actuator-lab"
    metrics_path: "/actuator/prometheus"
    static_configs:
      - targets: ["localhost:8080"]
```

Start Prometheus with this file per your installation method, for example using the binary:

```powershell
.\prometheus.exe --config.file=prometheus.yml
```

`job_name` names the target group; `metrics_path` sets the scrape path; `targets` specifies the address Prometheus itself connects to. Refer to [Prometheus — Configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/).

If Prometheus runs inside a container, `localhost` refers to that container itself. In that case, use an address or service name reachable from Prometheus’s network. The same-host config above does not work unchanged across two containers or separate hosts.

### 5.5. Verify Collection and Querying

In the Prometheus query UI, check:

```promql
up{job="actuator-lab"}
```

For a scraped target, 1 means the scrape succeeded; 0 means the scrape failed. Seeing no series points to checking job name, target config, or whether scraping has started. The meaning of `job`, `instance`, and the `up` series is described in [Prometheus — Jobs and instances](https://prometheus.io/docs/concepts/jobs_instances/).

`up=1` indicates metric scraping works, not that all business functions are healthy. Nor is it the `UP` result from Actuator Health.

If the output already includes `jvm_memory_used_bytes` with `area="heap"`, try:

```promql
jvm_memory_used_bytes{job="actuator-lab",area="heap"}
```

Switch to graph view over time to observe stored samples. This is instantaneous memory usage at each scrape, not an event count; do not blindly apply counter rate calculations to it.

## 6. What Does the External System Add?

### 6.1. History and Queries Across Multiple Running Instances

Suppose there are two running instances of the same application. In a hypothetical observation window, instance A records 30 more completed tasks and instance B records 20 more. To answer “how many tasks did the service complete during that window?”, you need to:

- Know which instance each sample belongs to.
- Use the same definition of “completed”.
- Scope to the exact same time window.
- Handle counter resets when processes restart.

Do not take two cumulative totals from processes with different lifetimes and call that the 5-minute task count.

With counter series, Prometheus provides functions like `rate` to calculate average per-second increase and account for counter resets. Compute rates per series before aggregating across instances. Refer to [Prometheus — Query functions](https://prometheus.io/docs/prometheus/latest/querying/functions/).

**Illustrative example—use only if the Spring Boot app actually records and exports this counter:**

```promql
sum by (result) (
  rate(learning_tasks_completed_total{job="actuator-lab"}[5m])
)
```

This query asks for completion rate by result, in tasks per second. It does not run against the `SimpleMeterRegistry` from the exited program in section 3. Verify the actual series name, sufficient samples, and exact tags before interpreting results.

### 6.2. Visualization

In this illustrative setup, Grafana connects to Prometheus as a data source and runs queries to render dashboards.

Grafana supports many data source types and alerting rules. However, simply installing Grafana does not make the application get scraped. You need a working pipeline from source to the datastore Grafana queries. See [Grafana — Data sources](https://grafana.com/docs/grafana/latest/datasources/).

If Prometheus has data yet a dashboard panel is blank, check the data source, query, time range, and template variables before changing Java code.

### 6.3. Alerting and Notifications

In Prometheus’s alerting model, the Prometheus server evaluates rules; Alertmanager receives alerts to handle grouping, silencing, and routing notifications to configured channels. That capability must be configured separately. See [Prometheus — Alerting overview](https://prometheus.io/docs/alerting/latest/overview/).

A Micrometer `Counter` does not know who should be notified. Nor does an Actuator endpoint returning metrics create alert recipients.

To design a useful alert rule, specify the business question, evaluation interval, minimum traffic volume, and response action when alerted. That is operational design; never treat “some number crossed a threshold” as sufficient in all cases.

### 6.4. Limits of Collected History

An external system only retains data it actually received that has not aged out of retention. If metrics were never scraped or old data expired, adding dashboards cannot recover that history.

For instance, if a short-lived process runs and exits between two scrapes, Prometheus may miss reading its counters entirely. Likewise, a brief spike in a gauge state might not show up in samples taken 15 seconds apart. Choose collection strategies suited to process lifetime and the question being asked.

Aggregated metrics also do not replace a transaction ledger. If the business requires recording every single transaction accurately for reconciliation, durable business records must be designed separately; monitoring counters serve observation per their definition.

## 7. Push Model: Not Every Registry Needs Prometheus

In a **push** model, the application or collector actively sends data to a receiver. For example, Micrometer’s OTLP registry can send metrics via the OpenTelemetry Protocol to a compatible receiver.

```text
Application code
    ↓ records metrics
Micrometer + OTLP registry
    ↓ pushes data per configuration
Receiver / Collector / storage system
    ↓
Queries, visualization, and alerts
```

In Micrometer 1.13, the OTLP registry is provided by `micrometer-registry-otlp`; Spring Boot configuration uses properties under `management.otlp.metrics.export`. A destination endpoint and matching settings are required. See [Micrometer 1.13 — OTLP](https://docs.micrometer.io/micrometer/reference/1.13/implementations/otlp.html).

Actuator’s HTTP exposure configuration controls who can read HTTP endpoints. It does not replace push-based metric export settings. Even if `metrics` is not exposed over HTTP, a properly configured OTLP export pipeline can still operate.

Conversely, in the Prometheus scraping `/actuator/prometheus` example, blocking that endpoint stops direct scraping from pulling metrics. Identify which model you are using before editing configuration properties.

| Question | Direct Prometheus scrape model | OTLP push registry example |
| --- | --- | --- |
| Who initiates metric transfer? | Prometheus sends HTTP requests | The exporter pushes to the receiver |
| Which network direction must be open? | From Prometheus to the application | From the exporter to the receiving system |
| What role does the Actuator HTTP path play? | Provides the scrape endpoint in this example | Not the OTLP push transport |
| Where to check when data is missing? | Target, scrape attempts, permissions, format | Destination URL, export config, connectivity, auth, and ingestion |

Switching backends lets you keep Micrometer instrumentation code, though connection settings, metric representations, and queries still need review. API neutrality reduces code coupling; it does not guarantee dashboards port unchanged.

## 8. Relationship to Observation, Tracing, and Logs

The name “Micrometer” appears across multiple components. Distinguish their purposes:

| Component | Role |
| --- | --- |
| Micrometer Metrics and `MeterRegistry` | Record and manage metrics |
| Micrometer Observation and `ObservationRegistry` | Describe an observed operation; configured handlers can produce matching signals |
| Micrometer Tracing | Integrate trace creation and context propagation with a tracing library |

Spring Boot uses Micrometer Observation for metrics and tracing integrations. An observation produces only the signals supported by configured handlers. Do not infer from having an `ObservationRegistry` that traces are already being exported and stored. See [Spring Boot 3.3 — Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

Exporting traces requires a tracer integration, exporter, and matching receiver. Adding a Prometheus registry for metrics does not configure trace storage. See [Spring Boot 3.3 — Tracing](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html).

Logs may be written to process output or files and collected through a separate pipeline. Thus, never diagram all observability signals as if they all flow through `/actuator/prometheus`. That endpoint serves metrics, whereas logs and traces require their own integration paths.

## 9. Choosing Meaningful Metrics and Controlling Context

A properly running collection pipeline can still hold metrics that are hard to use. Before naming a meter or adding tags, describe the quantity you want to measure.

For instance, `learning.tasks.completed` should have a clear definition: after which condition does it increment? If a task is retried, are you counting attempts or task outcomes? Both definitions can be useful, but they must be expressed through consistent naming and recording.

Tags should answer useful questions and have bounded values. For example, `result=success|failure` classifies outcomes. Conversely, using each task’s unique ID as a tag can generate huge numbers of series.

A hypothetical calculation: 2 results × 3 task types × 4 running instances yield up to 24 combinations for a component series, if every combination occurs. Adding 100,000 task IDs can multiply scale dramatically. This estimate illustrates cost; a single meter can produce multiple series, so do not treat 24 as a fixed system-wide total.

In business code, record to the managed registry and avoid unbounded tag values taken directly from input. When you need to locate an individual task, contextualized logs or traces are usually better suited than creating a separate metric series per ID.

## 10. Troubleshooting Stage by Stage Instead of Changing All Config at Once

| Symptom | Stage to check first | Evidence to gather |
| --- | --- | --- |
| Meter missing inside the application | Instrumentation and registration | Meter name, executed code path, registry used |
| Meter exists in a custom registry but Actuator misses it | Registry boundary | Does the component use the managed `MeterRegistry` bean? |
| `metrics` works yet `prometheus` cannot be read | Registry and endpoint | Dependency, endpoint status, exposure, and permissions |
| Local machine can read it, Prometheus fails | Scraper network path | Address from Prometheus itself, port, TLS, authentication |
| Prometheus has series, Grafana is empty | Query and display | Data source, converted metric name, tags, time range |
| Chart drops sharply after restart | Counter interpretation | Per-instance series, rate functions, restart timestamps |
| Charts exist yet no notifications arrive | Alerting and delivery | Rules, evaluation state, notification sender config |

A practical investigation sequence:

1. Write down the metric name and the question to answer.
2. Verify the application records the expected event or value.
3. Verify the metric in the registry and export output.
4. Verify the collector scrapes or receives it successfully.
5. Verify stored data with a simple query.
6. Only then inspect dashboards and alert rules.

Each step should yield concrete evidence. For example, “curl from my laptop succeeded” only proves connectivity from that machine; it does not prove network reachability from Prometheus.

## 11. Self-Check on the Three-Component Relationship

### Scenario A: Micrometer Only

A Java program uses `SimpleMeterRegistry`, increments a counter, and exits.

**Analysis:** in-process metric recording exists. There is no Actuator HTTP layer, collector, or external history. That is the boundary clarified by the experiment in section 3.

### Scenario B: Actuator and Prometheus Registry Present

The application serves `/actuator/prometheus`, but Prometheus is not running yet.

**Analysis:** the application side has formatted data ready for scraping. There is no external server storing samples over time. Refreshing in a browser does not create monitoring history.

### Scenario C: Prometheus Scrapes Successfully Yet Dashboard Is Blank

**Analysis:** start from the query in Prometheus and the dashboard’s data source. Perhaps the Java meter name was transformed during export, a tag filter is wrong, or the time window holds no data. There is no basis to add another registry.

### Scenario D: `metrics` Exposure Removed Yet Metrics Still Appear Externally

**Analysis:** identify the actual export path. If Prometheus scrapes `prometheus` or an OTLP registry pushes metrics, closing the diagnostic `metrics` API does not stop those pipelines.

### Applied Exercise

Trace the path of one real metric in your application and fill in six items:

1. What event or state is being measured?
2. Which component records it?
3. Which registry holds or exports it?
4. Who initiates data transfer and over what path?
5. Where is history stored, and where are queries run?
6. Which rules and components handle notifications?

If a step cannot be filled in yet, note the exact evidence needed to verify that step. Doing so turns a monitoring config into an explainable, verifiable data flow.
