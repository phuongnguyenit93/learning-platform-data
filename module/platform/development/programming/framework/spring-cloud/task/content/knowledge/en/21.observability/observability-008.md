# Exporting Metrics, Flushing Telemetry, and Short-Lived Process Lifecycles

A **Spring Cloud Task** application often runs for only a few seconds or minutes: it boots Spring Boot, parses arguments, runs an import/report/maintenance job, updates `TaskExecution`, and exits. During that brief window, it can emit **metrics** via Micrometer, **traces** via Micrometer Tracing/OpenTelemetry, and **logs**. Yet **recording a measurement in memory does not mean the backend received it**.

Suppose `invoice-report-task` finishes in **8 seconds**, while a metrics registry uses a **60-second** export interval. Business outputs and `TASK_EXECUTION.EXIT_CODE` may be completely right, yet dashboards show nothing for that run. If the process terminates abruptly before the exporter ships its final batch, metrics, spans, and logs can also be lost. That is why this lesson in the **Observability** chapter focuses on **metric export, flush/shutdown behavior, and short-lived process lifecycles**.

This lesson explains the differences among **TaskRepository, metrics, traces, and logs**; compares **pull, push, Prometheus Pushgateway, and OTLP**; shows how to order completion before closing `ApplicationContext`; covers Spring Boot/Spring Cloud Task configuration; details testing strategies for short-lived Tasks; and outlines operational rules for reliable observability.

> **Version scope:** Examples target Spring Boot 3.x, Spring Cloud Task 3.x, and compatible Micrometer versions; exporter properties, dependencies, and APIs can change in newer releases. Always use compatible BOMs and check configuration docs for your exact version. No single universal property guarantees "all metrics, traces, and logs flushed successfully" across every exporter.

## 1. Four Telemetry Sources That Do Not Replace Each Other

| Source | What does it store? | Purpose | Limitation on short Tasks |
| --- | --- | --- | --- |
| **TaskRepository** | `TaskExecution`: ID, task name, timestamps, arguments, exit code, exit message | Verifying whether and how a Task process ran and exited | May lack end details if Pod is killed before updating |
| **Metrics** | Counter, Timer, Gauge; e.g., imported row counts, duration | Aggregating trends, SLOs, success rates, throughput | Periodic exporters may not push in time; scrapes may miss |
| **Traces** | Spans for Task, runner, JDBC/HTTP, and business steps | Investigating latency and causal chains | Batch span processors may still buffer unsent spans |
| **Logs** | Detailed events with timestamps, errors, and correlation IDs | Investigating individual `TaskExecution` runs, safe arguments, stack traces | Log agents/buffers or Pods may be cleaned up before collection |

**A `COMPLETED` `TaskExecution` does not prove metrics were exported**, and **received metrics do not prove `TaskRepository` updated successfully**. Sound operations correlate all sources while knowing which source is authoritative for each state.

For example, a dashboard showing a run produced 3,200 invoices is only meaningful alongside **business evidence** (output tables, checksums, report IDs) and matching Job/Task status. Metrics aid observation and alerting, not primary outcome storage.

## 2. Task Lifecycle and Points Where Telemetry Is Easily Lost

~~~mermaid
sequenceDiagram
    participant K as Kubernetes Job / Scheduler
    participant T as Spring Cloud Task
    participant M as Micrometer / OTel SDK
    participant E as Exporter / Collector
    participant R as TaskRepository

    K->>T: Launch Java process
    T->>R: Create TaskExecution
    T->>M: Start observations / counters / spans
    T->>T: Runner processes business work
    T->>M: Record metrics and close business spans
    T->>R: Update TaskExecution end state
    T->>M: Close context / exporter per lifecycle
    M-->>E: Send final batch if exporter supports and time permits
    T-->>K: Process exit code
~~~

This diagram shows the **conceptual lifecycle**, not a strict guarantee of internal callback ordering across all versions and exporters. Notably, the observation wrapping the **entire Task** can finish at a different moment than the observation around a **runner**; measurements finalize only when observations/timers stop. Flushing **before final measurements are recorded** means the exporter cannot ship data that does not exist yet.

Key moments:

1. **Startup:** Spring Boot initializes the context, `TaskRepository`, `ObservationRegistry`, and `MeterRegistry`; startup can take longer than the business work itself.
2. **Runner executing:** the app starts timers, increments counters, creates spans, and logs.
3. **Runner completing:** business timers must stop; async work must truly complete before being considered done.
4. **Task ending:** Spring Cloud Task records `TaskExecution` status, invokes listeners, and closes framework observations.
5. **Context closing:** exporters/SDKs get a chance to run shutdown hooks; export success **depends on backend, SDK, deadlines, and network conditions**.
6. **Process exit:** the orchestrator receives the exit code; in-memory telemetry ceases to exist.

**Core risk:** a `Counter.increment()` inside a runner only mutates the in-memory `MeterRegistry`. With periodic export, not a single publish tick may occur before the JVM exits. A `Timer` completes only when stopped; a `Span` is typically ready for export only after `span.end()`.

## 3. What Observations Does Spring Cloud Task Provide?

Spring Cloud Task integrates **Micrometer Observation** to measure Task and runner execution times. Per official observability documentation, standard observation/metric names are:

| Name | Type | Meaning |
| --- | --- | --- |
| `spring.cloud.task` | Timer | `TaskExecution` lifecycle duration |
| `spring.cloud.task.active` | Long Task Timer | Active Task info while the observation remains open |
| `spring.cloud.task.runner` | Timer | Duration of an `ApplicationRunner`/`CommandLineRunner` |
| `spring.cloud.task.runner.active` | Long Task Timer | Runner currently executing |

For tracing, documentation also describes `spring.cloud.task` and `spring.cloud.task.runner` spans when tracing is integrated. Metric names appearing in Prometheus or OTLP may undergo **unit/naming conversion** by the registry; avoid hardcoding backend names before checking actual emitted series.

Runner observations can be enabled on supported versions via:

~~~yaml
spring:
  cloud:
    task:
      observation:
        enabled: true
~~~

To export metrics externally, you need at least **`spring-boot-starter-actuator`** and an appropriate **Micrometer registry**, plus exporter configuration. To export traces, also add **Micrometer Tracing** and a compatible bridge/exporter. Setting `observation.enabled=true` alone **does not create a Collector, dashboard, or telemetry shipper**.

Spring Cloud Task docs include tags such as task name, status, exit code, task execution ID, and parent/external execution ID. Not every tag fits aggregate dashboards because some IDs change **every run**; inspect actual cardinality in your registry and backend. For custom business metrics, favor low-cardinality tags.

### 3.1. Distinguishing Framework Metrics from Business Metrics

Task observations tell you how long a process ran and its overall status. To track **how many rows were imported, rejected, or how many reports were generated**, define dedicated application metrics:

- `business.task.records` — processed records split by `result=accepted|rejected`.
- `business.task.duration` — Timer for a business operation.
- `business.task.outcome` — Counter by `outcome=success|failure|skipped`.
- `business.task.export.failure` — Counter or log for telemetry export failures (when instrumented).

These names are **illustrative designs**, not metrics emitted automatically by Spring Cloud Task.

## 4. Pull vs. Push: Why Short-Lived Tasks Are a Special Case

### 4.1. Prometheus Pull / Scrape

Prometheus normally **scrapes** `/actuator/prometheus` from a running process:

~~~text
Prometheus --(HTTP scrape every 30s)--> /actuator/prometheus
~~~

For long-lived servers, this works naturally because an endpoint is always up. However, a Task running **8 seconds** may:

- Exit before the first scrape arrives.
- Open no HTTP server due to `spring.main.web-application-type=none`.
- Run in a short-lived Kubernetes Job Pod before ServiceMonitor/PodMonitor discovery even detects it.
- Record timers only as the Task finishes; mid-run scrapes miss final measurements.

Consequently, **merely adding `micrometer-registry-prometheus` and Actuator does not guarantee observability for short Tasks**. For finite tasks, consider **push** telemetry or sources based on `TaskRepository`/Kubernetes Job events.

### 4.2. Pushing Metrics via OTLP or a Push Registry

An `OtlpMeterRegistry` can push metrics to an **OpenTelemetry Collector** over HTTP OTLP. Example Spring Boot 3.x config:

~~~yaml
management:
  otlp:
    metrics:
      export:
        url: "http://otel-collector.monitoring.svc:4318/v1/metrics"
        step: 10s
        connect-timeout: 2s
        read-timeout: 5s
~~~

Add BOM-managed dependencies:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-otlp</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

**`step` is a periodic export interval**, not a guarantee of "send immediately when the Task finishes." In Micrometer OTLP, the default step is commonly **1 minute**. Setting `10s` helps longer tasks push multiple times, yet a 2-second Task may still see **zero periodic pushes**.

Furthermore, the OTLP exporter succeeds only when the Collector is reachable, DNS/TLS/auth are valid, networking is clear, and the exporter is active. Even an HTTP 2xx response from the Collector does not mean the downstream storage backend ingested and indexed the data immediately; collector pipelines, buffers, and retries may still intervene.

### 4.3. Prometheus Pushgateway for Service-Level Batch Jobs

Spring Boot provides **Prometheus Pushgateway** integration for short jobs when the matching exporter dependency is added and enabled:

~~~yaml
management:
  prometheus:
    metrics:
      export:
        pushgateway:
          enabled: true
~~~

A live Pushgateway must be running with base URL, grouping keys, auth, and networking matching your Spring Boot version. Pushgateway is **not** a Prometheus server; it caches pushed metrics so **Prometheus can scrape Pushgateway**.

~~~mermaid
flowchart LR
    A["Task runs 5–20 seconds"] -->|Push metrics| P[("Prometheus Pushgateway")]
    S["Prometheus"] -->|Scrape Pushgateway| P
    S --> G["Dashboard / alerts"]
~~~

**Important warning from Prometheus:** Pushgateway is a cache **decoupled from process lifetimes**. When a Task finishes without cleanup rules, series linger indefinitely and make dead Jobs appear still active. Prometheus recommends Pushgateway mainly for **service-level batch jobs**, not as a catch-all sink for every Pod; avoid high-churn `pod` or `instance` labels inside grouping keys.

Depending on version and config, Pushgateway shutdown options may push final metrics or delete the group. **Deleting the group immediately at Task exit can erase metrics before Prometheus scrapes them.** Never enable shutdown DELETE blindly for ultra-short Tasks; pick push and cleanup policies based on metric semantics, scrape intervals, and historical needs.

### 4.4. Exporter Selection Table

| Export path | Best suited for | Short-Task caveats |
| --- | --- | --- |
| Actuator Prometheus pull | Long-lived apps with persistent HTTP endpoints | Pods vanishing before scrape lose that run's metrics |
| Prometheus Pushgateway | **Service-level batch job** outcomes with stable grouping keys | Needs final push and controlled stale-series cleanup |
| OTLP push to Collector | Infrastructures already running OTel Collector for unified signals | Step/flush/shutdown and exporter timeouts are critical |
| StatsD or other push backends | Existing agents/backends with suitable protocols | Sending does not equal storage; packet loss or buffer drops possible |
| `TaskRepository` + external aggregator | Authoritative run outcomes even without HTTP endpoints | Requires querying repository and reconciling with Kubernetes Jobs |
| Structured logs → log collector | Per-`TaskExecution` debugging | Depends on log scraping, buffers, and retention |

**Real systems usually combine** `TaskRepository`, logs, and one metrics/tracing path; avoid forcing all observability data through a single channel.

## 5. "Metric Recorded" Is Not "Successfully Delivered"

Consider three stages:

~~~text
App records metric in memory
    → Registry / SDK prepares batch
    → Transport sends to Collector/Pushgateway
    → Backend stores and makes queryable
~~~

Different success milestones prove different things:

| Milestone | What it proves | What it does NOT prove |
| --- | --- | --- |
| `Counter.increment()` ran | Registry value incremented | Exporter shipped it |
| Exporter logged "send started" | Delivery was attempted | Receiver accepted it |
| Transport received HTTP 2xx | HTTP target accepted payload per protocol | Full pipeline ingested it and dashboards updated immediately |
| Collector reported points received | Initial collector ingestion | Downstream storage persisted data durably |
| Dashboard queries series | Backend holds data at query time | Zero past runs were ever lost |
| `TaskRepository` recorded `exitCode=0` | Task technically completed cleanly | Metrics also succeeded or business data is 100% valid |

Therefore, **flush** does not guarantee **durable backend persistence**. Systems may accept best-effort telemetry while strict auditing relies on business tables/`TaskRepository` as authoritative truth.

### 5.1. ForceFlush and Shutdown in OpenTelemetry

Per the OpenTelemetry specification:

- `forceFlush` on `TracerProvider` requests exporting **finished spans** still buffered in processors.
- `forceFlush` on `MeterProvider` with push readers requests collecting and exporting metrics within exporter limits.
- `shutdown` releases resources and typically flushes per SDK semantics; it requires **bounded timeouts and result checks**.
- For **pull** exporters, `forceFlush` does not replace Prometheus scraping the endpoint.

Exact APIs depend on the SDK and Spring Boot auto-configuration. **Never spin up a second OpenTelemetry SDK** inside an app already managed by Spring Boot or an agent just to call `forceFlush`; that causes duplicate spans/metrics or conflicting resource attributes.

If your app **directly owns** `SdkTracerProvider` or `SdkMeterProvider`, invoke `forceFlush` per your SDK version's API and **await completion with a finite deadline** before shutting down the SDK. When Spring Boot/Micrometer manages exporters, rely on context lifecycle and flush/shutdown hooks supported by your **specific registry**, testing on your actual dependency versions.

### 5.2. Avoid Flushing Too Early

A common mistake is flushing **inside the runner** before `run()` returns and assuming all Task metrics have shipped.

~~~text
Runner starts
  → app increments Counter
  → calls flush inside run()
  → runner returns
  → spring.cloud.task.runner observation stops
  → TaskExecution updates
  → spring.cloud.task observation may only finish now
~~~

With that sequence, an early flush **cannot ship runner/Task Timers that have not stopped yet**. Let **observations finish first**, then rely on shutdown-time final export supported by the exporter. You may test an interim flush for in-runner business metrics, yet it never replaces post-lifecycle final export.

## 6. ApplicationContext and Process Shutdown Timing

In Spring Cloud Task, you can set:

~~~yaml
spring:
  main:
    web-application-type: none
  cloud:
    task:
      closecontext-enabled: true
~~~

`spring.cloud.task.closecontext-enabled=true` tells Spring Cloud Task to **close the `ApplicationContext` after the task completes**, freeing resources/threads so the process can exit. It also lets exporter beans run **destroy callbacks** during context close.

**However, this is not a "forceFlush all exporters cleanly" command.** A registry/SDK may:

- Push final data on close, or simply stop its internal scheduler, depending on implementation.
- Have a timeout shorter than network latency needed to deliver.
- Log errors without failing the Task when telemetry is best-effort.
- Miss final measurements if observation lifecycles and destroy callbacks are misaligned.

Never use `Thread.sleep(60000)` as a blanket workaround just to wait for `step=60s`: it inflates Job cost, wastes resources, and still fails to guarantee delivery. Verify your **actual exporter's close/flush behavior** or design an export path tailored to short-lived processes.

### 6.1. Asynchronous Work Must Finish Before the Task Exits

**Unsafe** example:

~~~java
@Bean
ApplicationRunner unsafeRunner(ExecutorService executor) {
    return args -> {
        executor.submit(() -> generateReport()); // Runner returns immediately.
    };
}
~~~

If the runner returns immediately, Spring Cloud Task may treat work as finished while background threads are still running. Context shutdown can interrupt threads, skewing Task duration and processed counts.

Safer example:

~~~java
@Bean
ApplicationRunner safeRunner(ExecutorService executor) {
    return args -> {
        Future<?> result = executor.submit(() -> generateReport());
        result.get(); // Wait and propagate exceptions back to runner.
    };
}
~~~

This requires an `ExecutorService` bean, `generateReport()`, proper executor shutdown, and interrupt handling. **Never wait unboundedly** in production: enforce a business deadline, cancel safely, and return a failure exit code on timeout.

## 7. Practical Example: Recording Counters and Timers with Micrometer

Suppose a Task imports daily data. We want to measure:

- **Accepted/rejected** record counts.
- Runner processing duration.
- Final **success/failure** outcome across a small category set.

An `ApplicationRunner` can use the injected `MeterRegistry`:

~~~java
import java.time.LocalDate;
import java.util.List;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ImportMetricsConfiguration {

    @Bean
    ApplicationRunner importRunner(
            MeterRegistry registry, ImportService importer) {

        return args -> {
            LocalDate date = requiredDate(args);
            Timer.Sample sample = Timer.start(registry);
            String outcome = "failure";

            try {
                ImportResult result = importer.importFor(date);

                registry.counter(
                        "business.task.records",
                        "result", "accepted").increment(result.accepted());
                registry.counter(
                        "business.task.records",
                        "result", "rejected").increment(result.rejected());

                outcome = "success";
            } finally {
                sample.stop(registry.timer(
                        "business.task.duration",
                        "operation", "import"));

                registry.counter(
                        "business.task.outcome",
                        "operation", "import",
                        "outcome", outcome).increment();
            }
        };
    }

    private static LocalDate requiredDate(ApplicationArguments args) {
        List<String> values = args.getOptionValues("business-date");
        if (values == null || values.size() != 1) {
            throw new IllegalArgumentException(
                    "Expected --business-date=yyyy-MM-dd");
        }
        return LocalDate.parse(values.get(0));
    }
}

interface ImportService {
    ImportResult importFor(LocalDate businessDate);
}

record ImportResult(long accepted, long rejected) {}
~~~

This snippet demonstrates **recording measurements**, not exporter setup. A real app needs an `ImportService` bean and Spring Boot/Micrometer/`TaskRepository` config. Processing here is **synchronous**. If the importer throws, `finally` still records the Timer and `failure` counter, and the exception propagates so the Task/Kubernetes sees the failure.

**Limitation:** if `requiredDate(args)` throws **before** `try`, the custom business meters are not recorded. To measure validation failures too, move argument parsing inside `try/finally` and assign an appropriate outcome. Under `SIGKILL`, `finally` has no execution guarantee either.

### 7.1. Why Not Use `taskExecutionId` as a Metric Tag?

Avoid writing:

~~~java
registry.counter(
        "business.task.outcome",
        "taskExecutionId", "4101",
        "tenantId", "tenant-" + dynamicTenantId);
~~~

Each `TaskExecution` ID and unbounded tenant creates a **new time series**; storage and query costs escalate rapidly. For aggregate metrics, use low-cardinality tags such as `operation=import`, `outcome=success|failure`, and `environment=prod`. Put `TaskExecution` IDs in **logs, traces, or metadata tables** for detailed lookups.

### 7.2. Persist Business Counts in an Authoritative Store

If `accepted=980, rejected=20` must be audited or reconciled, do not rely only on `counter.increment(980)`. Persist outcomes in a business table, e.g.:

~~~sql
CREATE TABLE import_run (
    source_id       varchar(120) NOT NULL,
    business_date   date NOT NULL,
    status          varchar(30) NOT NULL,
    accepted_count  bigint NOT NULL DEFAULT 0,
    rejected_count  bigint NOT NULL DEFAULT 0,
    completed_at    timestamptz,
    PRIMARY KEY (source_id, business_date)
);
~~~

This table is a minimal model; production apps need transactions, `RUNNING/FAILED/COMPLETED` states, and safe retry/claim policies. Metrics are an **observability copy**, never a substitute for an outcome table when correctness and recovery matter.

## 8. Closing Exporters: Coordinating Spring Boot, Micrometer, and OTel

An app may use **Micrometer `MeterRegistry`** for metrics and **Micrometer Tracing** with the OTel bridge for traces. Even though both belong to observability, **metrics and traces can have different export pipelines**:

| Component | Common buffer | When is data ready? | Shutdown behavior to verify |
| --- | --- | --- | --- |
| Micrometer `Timer` | `MeterRegistry` aggregation | When timer/sample stops | Final publish or registry close if supported |
| Micrometer `Counter` | In-registry measurement | Immediately on increment | Final publish step before exit if exporter supports |
| `LongTaskTimer` | Active task state | While running, via scrape/publish | Short Tasks may finish before collection |
| OTel `Span` | `BatchSpanProcessor` | When span ends | Managed SDK `forceFlush`/`shutdown` |
| App logs | Logger/collector buffer | When log is appended | Logback/Log4j shutdown + stdout collection |
| `TaskRepository` | JDBC transaction | After repository updates and commits | Stable DB connection, not killed before end callback |

**Never close `MeterRegistry` inside `ApplicationRunner`** while Spring is still closing runner/Task observations. Doing so can drop final observations or break other beans using the closed registry.

**Never call `System.exit(0)` abruptly right after incrementing a counter**, bypassing context close and destroy hooks. Follow a clean Spring Boot shutdown path with bounded timeouts for exporters.

If **manually managing an OTel SDK** (not created by Spring or an agent), the conceptual flow is:

~~~text
1. Stop creating new work; await all Futures/Steps.
2. Close open spans/observations.
3. Call forceFlush on supported providers.
4. Wait for results with a bounded timeout; log errors.
5. Call shutdown/close to release resources.
6. Exit process with exit code matching business outcome.
~~~

**Use the exact API for your version** of `SdkTracerProvider`, `SdkMeterProvider`, or specific registry; the steps above are not runnable Java code. In auto-configured Spring Boot apps, usually let **`ApplicationContext` manage the lifecycle** and inspect your exporter's shutdown callbacks before adding manual flushes.

### 8.1. Never Let Shutdown Block Indefinitely

A dead Collector or long network timeout can pin a Pod for too long. Budget shutdown time explicitly:

~~~text
Max total Job time        = 15 minutes
Business work budget      = 14 minutes
Shutdown/telemetry budget = 20 seconds
Kubernetes safety buffer  = 40 seconds
~~~

This allocation is illustrative, not a default. If a Kubernetes Job hits `activeDeadlineSeconds` or a Pod has too little `terminationGracePeriodSeconds`, flushing can be cut short mid-flight. Conversely, setting an overly long telemetry timeout can cause a successful business job to be marked failed just because the observability backend stalled.

**Keep failure policies explicit:** when telemetry is best-effort, metric export failures should log a warning without turning a valid business transaction into a failure. When strict auditing is mandatory, write outcomes to a durable DB/outbox and sync asynchronously rather than trusting in-JVM flushes for exactly-once delivery.

## 9. Kubernetes: Pods Can Terminate Before Metrics Leave

Kubernetes CronJobs/Jobs can spawn a Pod per run and clean up old Pods per retention. Common scenarios:

- **Normal container exit:** context shutdown runs; the backend can still miss metrics if the exporter does not flush.
- **`SIGTERM`:** the app gets a graceful shutdown window, provided shutdown hooks finish within the grace period.
- **`SIGKILL`/OOM:** the process skips shutdown hooks; neither `finally`, exporters, nor `TaskRepository` final updates can be trusted.
- **Eviction/node failure:** the Pod may die mid-export or before the log collector finishes reading.
- **Image pull/config failure:** the app never starts, so **no `TaskExecution` or business metrics exist**; only Kubernetes events remain.

Illustrative manifest:

~~~yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: invoice-report-observability-test
spec:
  backoffLimit: 1
  activeDeadlineSeconds: 900
  template:
    spec:
      restartPolicy: Never
      terminationGracePeriodSeconds: 40
      containers:
        - name: task
          image: registry.example.com/batch/invoice-report-task:1.0.0
          args:
            - "--business-date=2026-11-23"
          env:
            - name: OTEL_SERVICE_NAME
              value: "invoice-report-task"
            - name: TASK_DB_URL
              valueFrom:
                secretKeyRef:
                  name: invoice-task-db
                  key: jdbc-url
            - name: TASK_DB_USER
              valueFrom:
                secretKeyRef:
                  name: invoice-task-db
                  key: username
            - name: TASK_DB_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: invoice-task-db
                  key: password
~~~

This manifest **omits the OTLP Collector URL and credentials**, assuming image-level config; configure `management.otlp.metrics.export.url` in the app or via env vars. Secrets must exist beforehand. `terminationGracePeriodSeconds` does not guarantee 40 seconds if the Job hits other limits or the Pod dies ungracefully.

When pushing over HTTP, verify **DNS, NetworkPolicy, TLS, and auth** from the Job's namespace to the Collector/Pushgateway. A reachable port on a laptop does not prove Pods can reach it.

## 10. Verifying Telemetry Actually Reached the Backend

Never declare success merely because `Counter.increment()` was called in code. Run a repeatable test:

### 10.1. Test Setup

1. Use a test environment with a live Collector/Pushgateway or queryable metrics backend.
2. Configure the right registry, endpoint, auth, and service name.
3. Run a Task **shorter than one export step** (e.g., 5 seconds vs. `step=60s`).
4. Record a counter and timer while logging `TaskExecution` ID and `businessDate` in logs/business tables.
5. Wait per infrastructure ingest SLA, then query the metric by `service.name`, `operation`, `outcome`, and timestamp.
6. Inspect exporter logs and timeout errors rather than looking only at summary dashboards.
7. Test both normal shutdown and failed export to confirm your failure policy.

### 10.2. Verification Matrix

| Scenario | Action | What to verify |
| --- | --- | --- |
| **A. Faster than export step** | 5s Task, OTLP `step=60s` | Periodic push won't fire; verify whether exporter shutdown ships data |
| **B. Long enough duration** | 70s Task, OTLP `step=10s` | Backend gets multiple ticks, yet final outcome still needs verification |
| **C. Network drop at shutdown** | Block Collector before shutdown | Exporter logs error/timeout; does the Task preserve its business outcome? |
| **D. Collector received, slow backend** | Observe buffered pipeline | Do not declare backend broken just because dashboards lag slightly |
| **E. Unstopped Timer** | Flush before runner returns | Final duration metric may be absent |
| **F. `SIGTERM`** | Send graceful shutdown to Job | Context closes, but measure actual shutdown duration against timeout |
| **G. `SIGKILL`/OOM** | Force-kill process in test env | No guarantee of final flush or `END_TIME` |
| **H. Stale Pushgateway series** | Task pushes then never runs again | Metrics persist until cleaned up; do not read as still running |
| **I. Retry** | Fail Job then retry same business key | Do not count two runs as two completed reports if business finished once |
| **J. Backend off, business valid** | Stop exporter/Collector in test | Reconcile `TaskExecution`, business tables, and best-effort policy |

**Pass criteria:** you can explain differences among in-memory recordings, export calls, Collector receipts, and backend series; reproduce an ultra-short Task; and prove Task outcomes never depend on scrape timing luck.

## 11. Monitoring Scheduled Tasks and Retries

A daily CronJob has three failure modes requiring alerts:

1. **Never ran:** CronJob suspended, missed schedule, image pull error, missing Pod. Here **no in-Task metrics exist**; monitor Kubernetes CronJob/Job state and expected schedules.
2. **Ran and failed:** `TaskExecution` has non-`0` exit code or Spring Batch `JobExecution` is `FAILED`, plus Pod failure; backend metrics may be missing if the exporter failed to flush.
3. **Reported success while business data is missing:** Task/Job exited `0` yet report is missing or row counts mismatch; reconcile business tables/artifacts.

**Never treat "no metrics" as the sole signal that a Task never ran.** It may have finished before a scrape, or the Collector may be broken. Likewise, a `last_success` metric sitting in Pushgateway can be **stale** and does not prove today's schedule ran.

A solid dashboard combines:

| Indicator / question | Preferred source |
| --- | --- |
| Did today's scheduled Job run? | Kubernetes CronJob/Job or scheduler |
| Did the Task start and end? | `TaskRepository` `TASK_EXECUTION` |
| Which attempt failed? | Exit code, Pod status, logs, `JobRepository` if using Batch |
| How many rows processed, any duplicates? | Business tables / checksums / unique keys |
| Median/p95 duration of completed runs | Exported Timer metrics |
| Exporter lag or delivery failures | Exporter logs, Collector metrics, pipeline health |

### 11.1. Querying TaskRepository to Reconcile

~~~sql
SELECT TASK_EXECUTION_ID,
       TASK_NAME,
       START_TIME,
       END_TIME,
       EXIT_CODE,
       EXIT_MESSAGE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'invoice-report-task'
ORDER BY START_TIME DESC;
~~~

If a Task was killed, `END_TIME IS NULL` **does not prove it is still running**. Cross-check Pod/Job state and elapsed hours. With read-only access to `TaskRepository`, pair these results with logs; never edit metadata manually just to turn a dashboard green.

### 11.2. Cross-Layer Identifiers

Use traceable correlation IDs:

~~~text
Kubernetes Job name/UID
   ↔ TaskExecution ID
   ↔ Spring Batch JobExecution ID (if any)
   ↔ businessKey = (tenantId, businessDate, reportVersion)
   ↔ traceId/spanId
~~~

**Do not** turn every ID into a Micrometer metric tag. Keep correlation IDs in structured logs and traces; for metrics use stable low-cardinality dimensions such as task name, environment, operation, and status. Keep PII, unbounded tenant IDs, tokens, secret filenames, and raw source data out of labels and attributes.

## 12. Common Mistakes

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `TaskExecution` exists, metrics missing | In-memory-only registry, no exporter, or Task shorter than export step | Check dependencies, `management.*.export`, shutdown/publish |
| Prometheus fails to scrape Pod | Task exited fast, no HTTP server, slow discovery | Use push where appropriate or monitor repository/scheduler |
| Backend sees partial pushes, misses final duration | Timer/Task observation had not stopped at publish time | Ensure observations close before final export |
| `step=10s` still loses metrics on 2s Task | Periodic tick never fired | Never rely on `step` instead of final flush/shutdown |
| JVM hangs due to exporter/thread | Non-daemon thread or unclosed context | Check `closecontext-enabled`, lifecycle beans, timeouts |
| Pod killed mid-push | Job deadline/termination grace too short, infra failure | Bound and test timeouts; rely on durable stores |
| Trace missing final span | `BatchSpanProcessor` did not flush, unclosed span, or early SDK close | Check end/`forceFlush`/shutdown per SDK |
| Pushgateway still shows `success=1` from yesterday | Series persisted after Task exit | Manage grouping keys, stale cleanup, expected timestamps |
| Sudden metric series explosion | Unbounded `TaskExecution` ID, Pod UID, or tenant in tags | Reduce cardinality; move IDs to logs/traces |
| Task reports success despite import errors | Swallowed exception or Batch failure unmapped to exit code | Fix error propagation; reconcile business/`TaskRepository` |
| Zero metrics because Task never booted | Image pull/config/DB failure before Micrometer initialized | Check Pod events/Job status and startup logs |
| Exporter outage hangs Task | Excessive shutdown retries/timeouts | Enforce deadlines and clear best-effort policy |

## 13. Production Design Rules

- **Measure meaningful outcomes:** duration, records, retries, outcome; never replace authoritative audit tables with metrics.
- **Pick the right export path:** pull for long-lived services; push/Pushgateway/Collector for short batch jobs within proper scope.
- **Respect intervals:** a 5-second Task with a 60-second export step may never push periodically before exit.
- **Finish work before closing:** await business I/O, commit transactions, stop timers/spans, update `TaskRepository`, then let exporter lifecycles close/flush.
- **Control shutdown:** finite timeouts, sensible `terminationGracePeriodSeconds` and Job deadlines; never use arbitrary sleeps to guarantee telemetry.
- **Separate failure policies:** metrics/traces are usually best-effort while business outcomes must be durable; if telemetry is mandatory, use a durable outbox/reconciliation rather than trusting JVM memory.
- **Protect secrets:** authenticate exporters via Secrets; never log passwords in CLI args, metric tags, or logs.
- **Avoid high cardinality:** `TaskExecution` ID, Pod UID, and request ID belong in logs/traces or metadata.
- **Monitor absences:** missed CronJobs emit zero internal metrics; track scheduler/Job state and expected schedules.
- **Verify at the backend:** after Task exit, inspect metrics/traces/logs at the final destination rather than assuming a `MeterRegistry` bean suffices.

## 14. Self-Assessment Exercise

A `daily-settlement-task` runs for **7 seconds** nightly via a Kubernetes CronJob. It records `business.task.outcome{outcome="success"}`, `business.task.duration`, and spans for an HTTP call; `TaskRepository` records exit code `0`. Infrastructure uses Micrometer OTLP with `step=60s`.

1. Explain why `TaskRepository` has a success row while dashboards show zero metrics.
2. If you change `step` from `60s` to `10s`, is delivery guaranteed for a 7-second Task? Why or why not?
3. Sketch the required ordering among completing business work, stopping timers/spans, closing context, and exporter flush.
4. Distinguish `spring.cloud.task.closecontext-enabled` from OTel SDK `forceFlush`.
5. Choose among Prometheus scrape, Pushgateway, OTLP Collector, and `TaskRepository` queries, justifying based on monitoring needs.
6. If the Pod receives `SIGKILL` at second 6, what states can metrics and `TaskExecution` be in?
7. Pushgateway still holds yesterday's success series while today's CronJob created no Job: how do you detect the missed schedule?
8. Propose low-cardinality tags for metrics and where to store `TaskExecution` ID and `traceId` for investigations.
9. Design a test simulating a Collector outage to verify error policy: broken telemetry must not corrupt business results.
10. When auditing requires 100% run accounting, why must you use a durable table/outbox rather than Micrometer counters alone?

**Guided answer:** metrics are recorded in the JVM, yet the periodic push exporter has not fired; `step=10s` is still longer than a 7-second Task. Close metrics/spans before final export and verify shutdown behavior of your exact implementation. `TaskRepository`/Job status and business tables remain authoritative for reconciliation; telemetry aids visibility rather than replacing data correctness.

## 15. Summary

1. **Short lifetimes are a design property of Spring Cloud Task**, not a bug. Observability must expect processes to exit before scrapes or periodic pushes.
2. **Recording a metric ≠ sending a metric ≠ backend storing a metric.** Verify every boundary.
3. Spring Cloud Task provides Task/runner observations; exporting metrics/traces requires Actuator, compatible registries/exporters, and Collectors/backends.
4. **A `step` interval does not guarantee final export.** For short Tasks, use supported final push/close/flush mechanisms and test them end-to-end.
5. **`closecontext-enabled` is not a "forceFlush everything" button.** It closes the context and triggers lifecycle hooks, while delivery still depends on the registry/SDK, transport, and timeouts.
6. Never close exporters **before** runner/Task observations stop; never keep processes alive indefinitely just waiting for an export tick.
7. With Prometheus Pushgateway, manage **grouping keys and stale series**; with OTLP, govern **intervals, deadlines, Collectors, and pipelines**.
8. **Metrics are observability signals**, whereas `TaskRepository`, Kubernetes Jobs, and business tables establish execution and correctness.
9. Always test **normal exit, timeouts, `SIGTERM`/`SIGKILL`, exporter outages, and retries** before promoting short Tasks to production.

### Official References

- [Spring Cloud Task — Observability](https://docs.spring.io/spring-cloud-task/reference/observability.html)
- [Spring Cloud Task — Features and Enable Task Metrics](https://docs.spring.io/spring-cloud-task/reference/features.html)
- [Spring Boot — Actuator Metrics (OTLP, Prometheus, Pushgateway)](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Micrometer — OTLP Metrics Registry](https://docs.micrometer.io/micrometer/reference/implementations/otlp.html)
- [OpenTelemetry Specification — Metrics SDK ForceFlush, Shutdown](https://opentelemetry.io/docs/specs/otel/metrics/sdk/)
- [OpenTelemetry Specification — Tracing SDK ForceFlush, Shutdown](https://opentelemetry.io/docs/specs/otel/trace/sdk/)
- [Prometheus — When to Use the Pushgateway](https://prometheus.io/docs/practices/pushing/)
