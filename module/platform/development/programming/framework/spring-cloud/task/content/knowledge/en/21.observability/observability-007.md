# Distributed Tracing and Context Propagation to External Systems

## 1. Why Does Spring Cloud Task Need Distributed Tracing?

A **Spring Cloud Task** application handles finite work: importing data, reconciling transactions, generating reports, running on a schedule, or accepting launch requests from an API. The framework can save each run as a **TaskExecution** in **TaskRepository**, capturing identifiers, start/end times, and technical status. Yet business outcomes typically span more systems than a single JVM:

- An orchestration API receives a request and launches the task.
- The task reads from a database, calls a classification service, or writes files to object storage.
- The task publishes messages to a broker for other workers to process.
- A Spring Batch Job splits data into Steps or remote partitions.
- A scheduler retries after a timeout, even though side effects in an external system may have already occurred.

**Distributed tracing** connects operations within an execution flow into **spans** across one or more **traces**, answering: where is the task slow, which downstream failed, which systems did a request traverse, and how does a retry relate to a prior attempt?

Example: the `invoice-sync` task imports 10,000 invoices. `TaskRepository` shows `TaskExecution` 8041 failed after 6 minutes, but cannot itself show whether 5 minutes were spent waiting on the partner API or 1 minute on the database. A trace reveals the client spans and the latency/errors of each downstream hop.

**Do not conflate these three forms of evidence:**

| Mechanism | What question does it answer? | Limitations |
|---|---|---|
| `TaskRepository` | Which application run started/ended and with what exit code? | Not a distributed span store; does not hold full traces |
| Distributed tracing | Which components did the task call, where was time spent, and which span failed? | Subject to sampling or loss on crash; does not prove business commits |
| Business state / checkpoint | How far did invoices, reports, or transactions actually progress? | Does not itself provide a latency graph or external root cause |

Reliable operations require reconciling **all three**, alongside structured logs and orchestrator state.

## 2. Trace, Span, Context, and Correlation ID

| Term | Meaning | Usage example |
|---|---|---|
| **Trace** | Causal chain of a distributed operation | A report request from API to task, broker, and worker |
| **Trace ID** | Identifier for the whole trace | Looking up a flow in Jaeger, Tempo, Zipkin, or another tracing UI |
| **Span** | A timed operation with start/end, attributes, and error status | `task.reconcile`, `HTTP POST /payments`, `batch.step.import` |
| **Span ID** | Identifier for a single span | Distinguishing parent and child operations inside the same trace |
| **Trace context** | Trace ID, current span, sampling decision, and propagated flags | Used to link downstream spans into the right hierarchy |
| **Baggage** | Supplementary key/value data propagated across process boundaries per spec | An allowed correlation key; **never use for secrets** |
| **Correlation ID** | User-defined business/operational ID, not necessarily equal to trace ID | `taskExecutionId`, `businessKey`, `requestId` |

One trace can hold many spans; one task execution can have a **root span** and many child spans. However, **trace ID is not TaskExecution ID**. When the same business key is retried, a new `TaskExecution` is normally created and a new trace **may** be started; connect them using business key, attempt ID, or span links rather than forcing every retry to share one trace.

Illustrative example:

~~~text
businessKey = tenant-A/INVOICE_SYNC/2026-11-23/revision-1

Attempt 1:
  TaskExecutionId = 8041
  traceId         = 3b0a...9df1
  status          = FAILED

Attempt 2:
  TaskExecutionId = 8056
  traceId         = 7c42...3a12
  status          = COMPLETED

Two attempts share the same business intent but have two different lifecycles.
~~~

**Rule:** `TaskExecutionId` identifies the attempt, `businessKey` identifies the business intent, and `traceId` identifies the observed execution path. Use all three when investigating safe retries.

## 3. Sample Tracing Flow for a Spring Cloud Task

~~~mermaid
flowchart TD
    U["User / Scheduler"] --> API["Orchestration API or Data Flow"]
    API --> T["Spring Cloud Task: invoice-sync"]
    T --> DB["Read source DB"]
    T --> HTTP["HTTP client calls partner service"]
    HTTP --> EXT["Partner API"]
    T --> MQ["Publish event to broker"]
    MQ --> W["External Worker/Consumer"]
    W --> OUT["Target DB or Object Storage"]
    T --> TR["TaskRepository: TaskExecution"]
    T --> OT["Exporter / OpenTelemetry Collector"]
    API --> OT
    EXT --> OT
    W --> OT
    OT --> V["Tracing backend / UI"]
~~~

When **trace context is propagated properly** across boundaries, the tracing UI can display a tree like:

~~~text
reconcile-request (SERVER span at API)
└─ launch-task (CLIENT / producer span, if launcher is instrumented)
   └─ invoice-sync-task (task span in child JVM, if context is propagated)
      ├─ db-read (database span if instrumented)
      ├─ partner-call (HTTP CLIENT span)
      │  └─ partner-api (HTTP SERVER span if partner participates in tracing)
      └─ send-invoice-event (PRODUCER span)
         └─ consume-invoice-event (CONSUMER span when receiver extracts context)
~~~

**Do not assume every connection in this diagram appears automatically.** Specifically, **launching a new JVM/Pod** via a scheduler, Spring Cloud Data Flow, or `TaskLauncher` does not automatically transfer the parent JVM's current span context to the child JVM. Connecting traces requires an explicit carrier and context extraction mechanism. Even if an external partner does not support tracing, the task side still observes timing and status on its client span.

## 4. W3C Trace Context Standard: traceparent and tracestate

For HTTP, the common standard for interoperability across tracers is **W3C Trace Context**. Two key headers:

- `traceparent`: carries version, trace ID, **parent span ID**, and trace flags.
- `tracestate`: vendor/tool-specific extension data; may be absent.

Example valid header:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

| Part | Meaning |
|---|---|
| `00` | Format version |
| `4bf92f3577b34da6a3ce929d0e0e4736` | 16-byte Trace ID (32 hex chars) |
| `00f067aa0ba902b7` | 8-byte Parent Span ID (16 hex chars) |
| `01` | Trace flags in this example, with the sampled bit set |

When a service receives an HTTP request carrying `traceparent`:

1. Instrumentation **extracts** context from the header.
2. The service creates a **new server span** inheriting the trace ID with the proper parent relationship.
3. When making an outbound request, instrumentation **injects** the current span's context into outbound headers.
4. Downstream extracts it and creates the next span.

**Never reuse a fixed span ID across all calls.** Each span needs its own ID; the tracer/instrumentation is responsible for generating and propagating context. Also avoid hand-crafting `traceparent` strings from MDC when instrumentation is present, as that risks malformed context or conflicts with the tracing bridge.

### Baggage Differs from Trace Context

W3C **Baggage** uses the `baggage` header to carry allowlisted key/value pairs. It is not a security credential and may be forwarded across many systems. Never put into baggage:

- Tokens, API keys, passwords, or login cookies.
- Emails, phone numbers, invoice contents, or unnecessary personal data.
- SQL, large JSON payloads, or full `ApplicationArguments`.

For business correlation, consider a low-sensitivity opaque ID; enforce an **allowlist** and stripping rules at trust boundaries. Do not assume every baggage entry is propagated automatically unless configured.

## 5. Common Stack in Spring Boot: Micrometer Tracing + OpenTelemetry

On **Spring Boot 3.x** with Spring Boot Actuator, a common setup pairs **Micrometer Observation/Tracing** with the OpenTelemetry bridge and OTLP exporter.

Core roles:

| Component | Role |
|---|---|
| `ObservationRegistry` | Application-level observation API decoupled from a specific tracer |
| `Micrometer Tracing` | Connects observations to traces/spans, context propagation, and log correlation |
| `micrometer-tracing-bridge-otel` | Bridges to the OpenTelemetry SDK |
| `opentelemetry-exporter-otlp` | Exports traces over OTLP per configuration |
| **OpenTelemetry Collector** | Receives, transforms, batches, and exports telemetry in a pipeline |
| Jaeger / Tempo / tracing backend | Stores and visualizes traces to pinpoint slow or failing spans |

Example **Gradle Groovy DSL dependencies for Spring Boot 3.x**; versions managed by the Spring Boot BOM per compatibility matrix:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.cloud:spring-cloud-starter-task'

    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'

    // If TaskRepository uses PostgreSQL:
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

This is only the relevant dependency slice, not a complete build file. When using **Spring Boot 4.x or another release**, check starters/auto-configuration, versions, and property names in the release docs; do not assume all Boot 3.x properties remain unchanged.

Example `application.yml` for **Spring Boot 3.x** in a test environment:

~~~yaml
spring:
  application:
    name: invoice-sync-task
  main:
    web-application-type: none
  cloud:
    task:
      name: invoice-sync-task

management:
  tracing:
    sampling:
      probability: 1.0
  otlp:
    tracing:
      endpoint: http://otel-collector.monitoring.svc:4318/v1/traces
~~~

Explanation:

- `spring.application.name` sets the service/resource name so traces are easy to locate.
- `web-application-type: none` suits finite task JVMs; **no HTTP server is required** to send outbound OTLP.
- `management.tracing.sampling.probability: 1.0` is **100% sampling suited only to testing/low volume**. In production, pick sampling matching traffic and cost, and consider collector-side strategies.
- `management.otlp.tracing.endpoint` is an example OTLP/HTTP URL; a real Collector must be running with compatible NetworkPolicy/TLS and exporter setup.

**There is no guarantee spans will appear** merely from adding dependencies: an observation/span must be created, sampling must keep it, the exporter must work, and the app must have time to flush before exiting.

## 6. Creating a Root Span for Work Inside ApplicationRunner

A Spring Cloud Task app does not necessarily receive inbound HTTP requests. Consequently, there is **no automatic HTTP server span** wrapping `ApplicationRunner`. A clean option is creating an observation around the overall business workload.

Spring Boot 3.x example with `ObservationRegistry`:

~~~java
import java.time.LocalDate;
import java.util.List;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class InvoiceSyncRunnerConfiguration {

    @Bean
    ApplicationRunner invoiceSyncRunner(
            ObservationRegistry registry,
            InvoiceSyncService service) {

        return arguments -> {
            List<String> dates = arguments.getOptionValues("date");
            if (dates == null || dates.size() != 1) {
                throw new IllegalArgumentException(
                    "Required: --date=yyyy-MM-dd");
            }

            LocalDate date = LocalDate.parse(dates.get(0));

            Observation.createNotStarted("task.invoice.sync", registry)
                .lowCardinalityKeyValue("task.name", "invoice-sync-task")
                .observe(() -> service.syncForDate(date));
        };
    }
}
~~~

`InvoiceSyncService` is a business service provided by your project. `Observation.observe(...)` opens a scope while running the service and closes the observation when the lambda returns or throws. When the tracing bridge is configured, a span for `task.invoice.sync` can be emitted. If the service throws an exception, **do not catch and swallow it** just to log: the runner must let Spring Cloud Task and exit-code policies observe the failure.

### When Should You Create Child Spans?

Create child spans for meaningful units of work, such as `batch.partition.process`, `invoice.calculate`, or `result.publish`. Avoid creating a span for **every individual data row** across millions of rows: trace storage cost, cardinality, and payload size would explode.

~~~java
Observation.createNotStarted("invoice.write.result", registry)
    .lowCardinalityKeyValue("operation", "upsert")
    .observe(() -> resultService.saveOnce(result));
~~~

If `resultService` uses instrumented JDBC/HTTP clients, spans nest under the active observation. However, auto-instrumentation **depends on dependencies and versions**: plain `JdbcTemplate` does not guarantee every SQL span automatically, and external Java SDKs do not produce traces unless instrumented.

## 7. Propagating Context on Outbound HTTP Calls to External Systems

Suppose the task calls an invoice verification API. On Spring Boot 3.x, inject **Spring Boot-managed `RestClient.Builder`** to inherit framework observation/tracing customizers rather than constructing an uninstrumented HTTP client.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class PartnerClient {

    private final RestClient client;

    public PartnerClient(RestClient.Builder builder) {
        this.client = builder
            .baseUrl("https://partner.internal.example")
            .build();
    }

    public void verify(String invoiceId) {
        client.post()
            .uri("/api/invoices/{id}/verify", invoiceId)
            .retrieve()
            .toBodilessEntity();
    }
}
~~~

To run this example, your project needs `RestClient` support (Spring Framework 6.1+, typically with Spring Boot 3.2+), configured HTTP client timeouts/TLS, and a real endpoint. **No inbound web server is needed**; a `WebApplicationType.NONE` task can still issue outbound HTTP requests.

When an observation/span is active and instrumentation is wired:

1. The client creates an **HTTP CLIENT span**.
2. The propagator injects W3C `traceparent` and `tracestate` headers into the outbound request.
3. The partner receives, extracts, and continues the span **if the partner supports and trusts the context**.
4. The task records duration, HTTP status, and errors on its side even if the partner emits no traces.

**Using `RestClient` does not guarantee propagation automatically.** You must use the framework-instrumented builder, proper bridge/exporter, an active observation, and verify headers in a test environment. Calling `RestClient.create()` or `WebClient.builder()` directly may bypass Boot's customizers and `ObservationRegistry`.

The same rule applies to `WebClient`: prefer the auto-configured `WebClient.Builder`, handle reactive context properly, and never rely solely on `ThreadLocal` MDC across reactive pipelines.

### Never Pass Trace Context via URL or Business Payloads

Prefer standard header propagation. Never stuff trace IDs into query strings to "pass context," as URLs leak into access logs, proxies, and caches. You may send a **separate business correlation ID** in an API-contract header for cross-organization tracing, subject to sanitization and authorization.

## 8. Message Brokers: Context via Headers, Not Producer ThreadLocals

With Kafka, RabbitMQ, JMS, or other brokers, producer and consumer typically run in separate JVMs and **share no thread context**. Distributed tracing requires:

1. A **producer span** recording the publish operation.
2. Tracer/propagator **injecting** context into supported message headers/properties.
3. Consumer **extracting** context upon receipt.
4. Consumer starting a new span linked via parent or **span link** suited to async semantics.
5. Consumer processing the message and recording status/errors; duplicate deliveries are handled by separate idempotency logic.

~~~mermaid
sequenceDiagram
    participant T as Spring Cloud Task
    participant P as Message Producer
    participant Q as Broker
    participant C as Consumer Service
    participant O as Trace Collector

    T->>T: Open task observation
    T->>P: Publish domain event
    P->>Q: Event + trace context headers
    P->>O: Producer span
    Q->>C: Deliver event (may redeliver)
    C->>C: Extract context and create consumer span
    C->>C: Process idempotently
    C->>O: Consumer span + result
~~~

Not every messaging library injects/extracts W3C headers automatically. For example, with Spring Kafka/Micrometer, observation support must be **explicitly enabled on `KafkaTemplate` and listener containers** per your version/configuration; RabbitMQ and JMS likewise require matching instrumentation. If one hop lacks propagation, the tracing backend shows **two disconnected traces** even when the event arrived cleanly.

`messageId` or `eventId` is **not a trace ID**. When a broker redelivers a message, a new consumer span/attempt may be recorded. Deduplicate by message/business key to avoid duplicate side effects; use traces to understand individual attempts.

### Span Parent or Span Link?

For fast request/reply messaging, a parent–child relationship is intuitive. For queues with hours of backlog, fan-out, or scheduled jobs, causality may no longer represent synchronous continuous execution. **Span links** express "triggered by a prior trace" without stretching one trace across hours of queue dwell time.

Choose the model matching your tracer/library capabilities and semantic conventions; do not turn hours of queue wait between publish and consume into apparent latency of a single request.

## 9. Propagating Context Across Thread Pools and `@Async`

Trace context is typically bound to the **current scope** (thread-local or library context). If a runner uses `CompletableFuture` or `ExecutorService` without propagation, spans inside worker threads become **new root spans** lacking the task's trace ID.

Pattern to avoid:

~~~java
CompletableFuture.runAsync(
    () -> partnerClient.verify(invoiceId));
~~~

This uses the default pool and says nothing about propagation, timeouts, lifecycle management, or errors. In finite tasks, it also risks the runner returning **before the future completes**.

With **Spring Framework 6.1+**, a common approach is `ContextPropagatingTaskDecorator` on a Spring-managed executor:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class TracingExecutorConfiguration {

    @Bean("taskWorkerExecutor")
    ThreadPoolTaskExecutor taskWorkerExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        executor.initialize();
        return executor;
    }
}
~~~

This decorator relies on context propagation registered by libraries in your app; it requires the right dependencies and thread-local accessors for your tracing bridge. Never assume it propagates arbitrary custom contexts unless registered.

Use the executor and **await all required futures**:

~~~java
CompletableFuture<Void> first = CompletableFuture.runAsync(
    () -> service.process("partition-a"), taskWorkerExecutor);

CompletableFuture<Void> second = CompletableFuture.runAsync(
    () -> service.process("partition-b"), taskWorkerExecutor);

CompletableFuture.allOf(first, second).join();
~~~

If a future fails, `join()` throws `CompletionException`; do not swallow it, and configure timeouts/retry policies separately. This demonstrates propagation **within one JVM**, and does not replace injecting/extracting context across HTTP/messaging/task launches into a separate JVM.

## 10. From an API or Data Flow to a New Spring Cloud Task JVM

This is the most important boundary for Spring Cloud Task: a scheduler or `TaskLauncher` typically **spawns a new process**, rather than calling a method in the current JVM.

~~~mermaid
flowchart LR
    A["API / Spring Cloud Data Flow"] --> B["TaskLauncher / Kubernetes Job"]
    B --> C["New task JVM"]
    C --> D["ApplicationRunner root observation"]
    D --> E["HTTP / Broker / downstream spans"]
    A -. "Context must be propagated intentionally" .-> C
~~~

**There is no automatic trace propagation from `parentTaskExecutionId`.** `parentTaskExecutionId` is a relationship in **`TaskRepository`**, whereas `traceparent` is tracing context. When `TaskLauncher` starts a new JVM, the API or manager's current thread/span does not automatically exist inside the worker.

A launch contract should separate:

| Data | Purpose | Where to pass |
|---|---|---|
| `businessDate`, `tenant`, `revision` | Business inputs, often defining idempotency | Arguments/JobParameters or business repository |
| `parentTaskExecutionId` | Parent–child lineage between TaskExecutions | Spring Cloud Task's parent-execution-id mechanism if used |
| `traceparent`, `tracestate` | Tracing context, if organization policy permits | Secure carrier supported by launcher/worker |
| `correlationId` / `requestId` | Linking logs and runs under its own data policy | Non-sensitive request/command metadata |
| DB/API credentials | Runtime access | Protected secret manager/environment |

When an API triggers a task, two strategies exist:

**A. Fresh trace per task; link via correlation ID.** Simple and safe for long or scheduled tasks. Record an opaque request ID/business key in both API and task logs, linking the separate traces via shared metadata. Often best when a Job queues for a long time or retries repeatedly.

**B. Propagate W3C context via a controlled carrier.** The API/launcher injects context into launch metadata; the worker extracts it at startup and starts spans inside that context. When launching via Kubernetes, passing `traceparent` in env/args must account for Pod/command-line visibility, validation, and retention. Never allow arbitrary untrusted external headers to become trusted parents.

For jobs delayed by hours, **span links or correlation IDs** represent causality better than stretching a single trace abnormally.

## 11. Linking TaskExecution, Spring Batch, and Traces

`TaskExecution` has a per-run ID. `JobExecution` and `StepExecution` are **separate** Spring Batch metadata. To investigate end-to-end flows, emit structured logs with IDs at the right levels:

~~~text
event=task.started
task.name=invoice-sync-task
task.execution.id=8041
business.key=tenant-A/INVOICE_SYNC/2026-11-23/revision-1
trace.id=3b0a...9df1

event=batch.step.finished
task.execution.id=8041
job.execution.id=912
step.execution.id=1007
step.name=importInvoices:partition2
trace.id=3b0a...9df1
~~~

This is a **recommended log structure**, not default output from Spring Cloud Task or Spring Batch. Spring Boot + tracing can populate `traceId` and `spanId` in MDC/log patterns **when a current span exists**, while business keys and framework IDs must be attached from trusted sources.

### Using TaskExecutionListener to Log Identifiers

A listener can read `TaskExecution` and log identifiers:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.task.listener.TaskExecutionListener;
import org.springframework.cloud.task.repository.TaskExecution;
import org.springframework.stereotype.Component;

@Component
class TaskLifecycleLogger implements TaskExecutionListener {

    private static final Logger log =
        LoggerFactory.getLogger(TaskLifecycleLogger.class);

    @Override
    public void onTaskStartup(TaskExecution execution) {
        log.info("task.started taskName={} taskExecutionId={}",
            execution.getTaskName(), execution.getExecutionId());
    }

    @Override
    public void onTaskFailed(
            TaskExecution execution, Throwable throwable) {
        log.error("task.failed taskExecutionId={} errorType={}",
            execution.getExecutionId(),
            throwable.getClass().getSimpleName());
    }

    @Override
    public void onTaskEnd(TaskExecution execution) {
        log.info("task.ending taskExecutionId={} exitCode={}",
            execution.getExecutionId(), execution.getExitCode());
    }
}
~~~

**Do not assume a trace ID exists in all three callbacks.** If the root observation is opened only inside `ApplicationRunner`, it is not necessarily active during `onTaskStartup` or `onTaskEnd`. To include trace IDs at those points, design scope/correlation aligned with your lifecycle and version.

You can store `taskExecutionId ↔ traceId` mappings in your project's audit/monitoring store, without turning trace IDs into unique keys on `TASK_EXECUTION`. If creating custom tables, protect read permissions, set retention, and avoid failing listener callbacks if a slow tracing backend times out.

## 12. Tracing in Spring Batch and Remote Partitioning

In a task running Spring Batch:

- `TaskExecutionId` is one application run.
- `JobInstance` identifies a Batch job by job name and identifying `JobParameters`.
- `JobExecutionId` is one run/restart of a `JobInstance`.
- `StepExecutionId` identifies a Step execution or partition.
- `traceId`/`spanId` belong to the tracing system with their own lifecycle.

With **remote partitioning**, a manager may launch multiple worker JVMs. The manager's trace context **does not propagate automatically to workers** via `JobRepository` or `ExecutionContext`. Instead, design explicit carrier/propagation protocols or start fresh traces linked by `StepExecution` ID and business key.

Never store raw credentials or unbounded tracing baggage inside `JobParameters`/`ExecutionContext`: those are serialized into metadata readable by multiple services. If storing an opaque correlation ID in Batch metadata, evaluate cardinality, security, and retention.

### Choosing Spans for Long Batch Jobs

Never create one span per item across millions of records. Pick appropriate granularity:

| Level | Suggested span/observation | Attributes |
|---|---|---|
| Whole task | `task.invoice.sync` | `task.name`, `operation` |
| Whole Job | `batch.job.import` | Job name, status |
| Each Step | `batch.step.validate` / `batch.step.import` | Step name, status, attempt |
| Each partition | `batch.partition.process` | Partition name or bounded shard name |
| Outbound HTTP | Auto-created client span when instrumented | URL template, method, status (never raw sensitive URLs) |
| Message publish/consume | Producer/consumer span | Bounded-cardinality destination |

**Avoid using `taskExecutionId`, user IDs, unique file paths, invoice IDs, or business keys as low-cardinality metric tags.** In tracing, these IDs may serve as controlled span attributes when non-sensitive, yet should never generate millions of metric time series.

## 13. Errors, Retries, and Latency: Interpreting Traces Correctly

Example: `TaskExecution` 8041 runs initially and times out calling a partner API:

~~~mermaid
sequenceDiagram
    participant O as Scheduler
    participant T as Task Attempt 1
    participant P as Partner API
    participant DB as Business DB
    O->>T: Run invoice-sync for day 23
    T->>P: POST verify invoice
    P--xT: Timeout / no response
    T->>DB: Reconcile saved state
    T-->>O: FAILED per exit policy
    O->>T: Retry creates new TaskExecution
    T->>DB: Check idempotency key
    T->>P: Call again if verified unprocessed
~~~

A client span showing an error or timeout means **the caller did not receive the expected response**. It **does not prove** the partner failed to execute the transaction. If the partner committed and the response was lost, blind retrying can cause duplicate effects.

Therefore, when investigating:

1. Inspect the trace for endpoint, latency, and exception.
2. Inspect `TaskExecution` for attempt and exit code.
3. Inspect business state, outbox, or partner state via **idempotency key**.
4. Decide whether to retry, reconcile, or halt per business policy.

Each retry can have its own trace; record **attempt number**, a **sanitized business key**, and a **link to the prior trace** in your audit system. Never use trace sampling as proof of "no errors": spans can be dropped by sampling or lost when exporters fail.

## 14. Sampling, Cardinality, and Observability Cost

Spring Cloud Tasks often run in short bursts yet issue thousands of requests. Opening a span per item at 100% sampling can blow past budgets.

| Decision | Benefit | Risk |
|---|---|---|
| 100% sampling in staging | Easy propagation verification, complete test data | Should not be copied verbatim to high-volume production |
| Head-based sampling in app | Lowers network traffic and exporter cost | Can miss traces of rare errors |
| Tail-based sampling in Collector/backend | Prioritizes error/slow traces after observing outcome | Needs memory/buffers, right topology, and cannot recover unsent spans |
| Fewer spans wrapping key stages | Low overhead, readable trace trees | Lacks item-level detail if too coarse |
| Structured logs + task metadata | Investigation trail even when traces are sampled out | Requires clear retention, security, and correlation |

**Never use high-cardinality business keys as metric labels**—such as `tenantId` with hundreds of thousands of values, `invoiceId`, `taskExecutionId`, or raw URLs containing IDs. Selected fields may be attached to span attributes under control, keeping trace size limits in mind.

When every job failure must be caught, **alert on `TaskRepository`, scheduler/Job status, or aggregate metrics**, not solely on sampled error traces.

## 15. Flushing Telemetry Before a Task JVM Exits

This is a key difference for **finite** apps: exporters usually ship spans **asynchronously or in batches**. A fast-exiting JVM can terminate before the Collector receives all spans.

Desired lifecycle:

~~~mermaid
flowchart TD
    A["Open task observation"] --> B["Execute business logic"]
    B --> C["Stop observations/spans"]
    C --> D["Close Spring context gracefully"]
    D --> E["Exporter/SDK shutdown or flush per integration"]
    E --> F["JVM returns exit code to scheduler"]
    B --> G{"SIGKILL, crash, node power loss"}
    G --> H["No guarantee of flush or TaskRepository end"]
~~~

Recommendations:

- Do not call `System.exit(0)` or `Runtime.halt(...)` from inside a runner.
- Use Spring Boot's shutdown lifecycle: when explicit exit codes are needed, follow `SpringApplication.exit(context)` then `System.exit(code)` in `main` after work finishes.
- Use Spring-managed integrations/exporters so lifecycle hooks can close/flush; if wiring an SDK manually, call `forceFlush`/`shutdown` with proper timeouts.
- Never fire off futures and exit the JVM; the runner must await required work.
- Bound network timeouts on exports; **never let telemetry outages hang business Jobs indefinitely**.
- On Kubernetes, configure `terminationGracePeriodSeconds` and proper signal forwarding, noting `SIGKILL` or OOMKill skips shutdown hooks.

**There is never a 100% guarantee all trace data was exported on Job success** if the Collector is down, exporter buffers overflow, or the process is killed. Thus `TaskRepository` and logs must remain available outside the tracing backend.

## 16. Security and Trust Boundaries When Propagating Traces

Distributed tracing carries metadata across application boundaries. Incoming headers from external callers or partners are not always trustworthy.

Principles:

1. **Never treat a trace ID as authentication proof.** `traceparent` is observability data a client can spoof; it never replaces `Authorization` or JWTs.
2. **Validate/restrict incoming baggage.** Never let arbitrary baggage generate metric tags, log fields, or uncontrolled outbound headers.
3. **Propagate only across trusted endpoints per policy.** Start a fresh root trace at untrusted boundaries and retain an internal correlation ID instead of inheriting external traces.
4. **Never write PII, tokens, or raw business payloads into span attributes.** Use error codes/types and safe sizes/statuses.
5. **Secure the Collector:** TLS, authentication, NetworkPolicy, retention, RBAC, and tracing UI access controls.
6. **Review cross-tenant isolation:** trace queries must never let one tenant inspect another tenant's activity.
7. **Avoid raw URLs carrying IDs or sensitive query strings:** attach `http.route`/URL templates instead of full URIs wherever possible.

In multi-tenant tasks, business keys must suffice for idempotency without appearing verbatim in traces. Use opaque correlation tokens or hashes consistent with storage and access policies.

## 17. Common Errors and Diagnostic Steps

| Symptom | Possible causes | How to check |
|---|---|---|
| No task span despite `TaskExecution` | No root observation/span created; missing tracing bridge/exporter | Check dependencies, Observation code, sampling, exporter logs |
| Trace stops at API, does not reach task JVM | `TaskLauncher` did not propagate context across process boundary | Design carrier/extraction or correlation/span links |
| Downstream HTTP starts a separate trace | Uninstrumented client builder, lost active scope, proxy stripped header | Inspect outbound/inbound `traceparent` in test env |
| Consumer has a different trace ID than producer | Missing producer/consumer instrumentation or dropped headers | Check message carrier, propagation, and instrumentation |
| `@Async` span becomes a new root | Lost thread-local context on executor handoff | Use `ContextPropagatingTaskDecorator` or snapshot/propagation |
| Traces vanish on fast JVM exit | SDK/exporter did not flush, Collector unreachable | Check shutdown lifecycle, timeouts, exporter and collector logs |
| Trace exists without `TaskExecution` ID | Missing separate correlation logging | Use `TaskExecutionListener`, structured logs, and audit mapping |
| `TaskExecution` stuck with `END_TIME IS NULL` | Process still running or died before metadata commit | Check JVM/Pod state, logs, and business state |
| Sudden metrics cardinality spike | `invoiceId`/`taskExecutionId` put in low-cardinality tags | Strip IDs from metric labels; govern span attributes |
| Trace contains passwords or PII | Unfiltered headers, raw exceptions, payloads, or baggage logged | Apply sanitization, allowlists, RBAC, retention |
| HTTP timeout yet partner succeeded | Request executed but response was lost | Reconcile via idempotency key before retrying |
| Massive spans or millions of spans | Coarse observations or per-item spans | Scope spans to steps/chunks, apply sampling and limits |
| Tracing works locally, fails in Kubernetes | Wrong endpoint/TLS/NetworkPolicy/Collector config | Test OTLP connectivity, network rules, resource limits |
| Only some runs have traces | Sampling, batch buffer drops, restarts/crashes | Reconcile `TaskRepository` and scheduler status |

### Short Diagnostic Workflow

1. Confirm the **business task actually ran**, with `TaskExecution`/`JobExecution` and corresponding logs.
2. Confirm a root observation/span exists in the runner, tracing bridge, exporter, and Collector.
3. In staging, temporarily set sampling to 100% and enable safe exporter debug logs **without exposing secrets**.
4. Inspect actual HTTP/message headers via safe debug points; verify **same trace ID, distinct parent/child span IDs**.
5. For async executors, inspect the current span upon entering the worker thread and before outbound calls.
6. For `TaskLauncher`/new JVMs, distinguish true trace propagation from correlation IDs used only to link logs.
7. At task exit, verify spans stopped and the exporter had time to flush; inspect the tracing backend.
8. If telemetry is missing, never assume business work failed to run: verify business DB, `TaskRepository`, and scheduler.

## 18. Hands-On Lab: Tracing from Task to HTTP and Message Consumer

### Goal

Build a non-web `invoice-sync-task` running as a finite Spring Cloud Task that calls a REST API and publishes a message after saving data, observing traces/spans without misusing framework IDs as tracing context.

### Steps

1. **Prepare backend:** run an OpenTelemetry Collector and a tracing UI. Ensure the OTLP endpoint is reachable from the task JVM.
2. **Enable instrumentation:** add Actuator, Micrometer Tracing bridge, and a compatible OTLP exporter; set `management.otlp.tracing.endpoint`.
3. **Create root observation:** wrap business logic in `ApplicationRunner` with `Observation.createNotStarted(...).observe(...)`.
4. **Call HTTP:** use instrumented `RestClient.Builder`; verify outbound `traceparent` and downstream spans if the target service supports tracing.
5. **Publish message:** enable producer observation/propagation per library; have the consumer extract context and start a span. Disable instrumentation once to observe the broken trace and understand the boundary.
6. **Test thread pools:** run one partition on an undecorated executor vs. one using `ContextPropagatingTaskDecorator`.
7. **Record correlation:** log `taskExecutionId`, sanitized business key, and trace ID within proper scopes; do not force retries to reuse the same trace ID.
8. **Test failures:** have the API return timeouts/5xx; confirm the client span shows error, `TaskExecution` fails per exit policy, and business state does not duplicate on retry.
9. **Test shutdown:** let the JVM exit right after the runner completes; check whether all spans reach the backend and tune graceful close/flush and timeouts as needed.
10. **Test process boundary:** launch a separate worker JVM from the task; confirm no parent trace propagates automatically, then add a carrier or correlation strategy and compare.

Verification table:

| Check | Expected outcome |
|---|---|
| `TaskExecution` and trace ID | Distinct IDs linked via logs/audit when needed |
| Runner observation | Span representing the finite workload |
| HTTP client → server | Header/context propagated when both sides are instrumented |
| Producer → consumer | Message headers injected/extracted when broker integration supports it |
| Executor tasks | Context preserved with proper propagation |
| New worker JVM | Requires propagation/correlation across the process boundary |
| Task retry | Stable business key; trace/attempt IDs may differ |
| Telemetry failure | Never corrupts business outcome; `TaskRepository` still records execution |
| Security | Zero secrets/PII in span attributes or baggage |

## 19. Production Deployment Checklist

- Define a clear **root observation/span** for non-web Spring Cloud Task workloads.
- Pick Micrometer Tracing/OpenTelemetry and exporters matching your Spring Boot/Cloud version.
- Use an **instrumented HTTP client builder**; verify W3C `traceparent`/`tracestate` across every hop.
- For brokers, enable and test **producer inject + consumer extract**; never treat message IDs as trace IDs.
- For `@Async`/thread pools, enable context propagation and await all required futures.
- For child tasks/separate JVMs, design a **carrier or span link/correlation ID**; do not rely on parent `TaskExecution` ID for trace propagation.
- Distinguish `TaskExecution`, `JobExecution`, `StepExecution`, trace ID, and business key across logs and dashboards.
- Never put high-cardinality IDs into low-cardinality metric labels.
- Tune sampling, span granularity, and retention to budget; never use traces as your sole alert source.
- Never send secrets, PII, raw payloads/arguments, or arbitrary baggage externally.
- Let exporters/SDKs flush when closing the Spring context; test graceful shutdown and timeout limits.
- Reconcile `TaskRepository`, scheduler/container state, and business state before retrying after a crash.
- Test success paths, downstream timeouts, message redeliveries, child worker JVMs, and `SIGTERM`/`SIGKILL`.

**Conclusion:** Distributed tracing adds **cross-system execution paths and latency breakdowns** onto the lifecycle metadata Spring Cloud Task stores in `TaskRepository`. To make it work reliably, **create spans for finite runners**, **propagate W3C context across supported carriers**, and **explicitly handle thread, broker, scheduler, and new-JVM boundaries**. Traces assist incident investigation, yet never replace exit codes, checkpoints, idempotency, or business state. When those layers are tied together through safe correlation, scheduled and on-demand tasks become both observable and safely recoverable.

### References

- [Spring Cloud Task Reference](https://docs.spring.io/spring-cloud-task/reference/)
- [Spring Boot Reference — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Micrometer Tracing Reference](https://docs.micrometer.io/tracing/reference/)
- [Micrometer Context Propagation Reference](https://docs.micrometer.io/context-propagation/reference/)
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/)
- [W3C Trace Context Specification](https://www.w3.org/TR/trace-context/)
