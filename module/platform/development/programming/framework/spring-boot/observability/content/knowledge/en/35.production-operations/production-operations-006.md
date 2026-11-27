# Fallback When the Telemetry Backend Fails

Telemetry helps operations teams understand application state, but the telemetry pipeline itself can fail. A Collector can stop, an exporter can lose connectivity, the backend can reject data, the network can partition, or storage quotas can fill up. When that happens, Spring Boot applications must still process business traffic within committed bounds while minimizing telemetry loss and recovering cleanly.

Fallback design needs to answer three questions: will the application keep serving requests, which signals remain preserved, and how will the pipeline recover when the backend comes back online? For most business systems, a telemetry failure is a degraded observability state; it must not turn into a user transaction failure.

This lesson explains how to design fallback behavior for Micrometer Observation, metrics, logs, and distributed tracing in Spring Boot—from the application through the OpenTelemetry Collector to the backend.

## 1. Identify Where Failures Occur

A typical pipeline has these stages:

1. The application creates Observations, meters, log events, and spans.
2. Micrometer registries or tracing bridges record signals in-process.
3. Exporters move data out of the application.
4. The OpenTelemetry Collector or agent receives, processes, and forwards data.
5. The backend ingests, stores, indexes, and serves queries.

Failures at each stage manifest differently. Avoid collapsing everything into a single "telemetry down" state, because remediation depends on where data is being lost.

| Failure Point | Symptoms | Primary Risk | Fallback Direction |
|---|---|---|---|
| In-app registry or SDK | Fails to create meters/spans, misconfigured handlers | Missing signals right at the source | Keep config minimal, catch config errors at startup, and maintain independent diagnostic logs |
| Exporter or network link | Timeouts, send errors, rising retries | Full queues, lost signals, or resource exhaustion | Asynchronous export, short timeouts, bounded retries, and bounded queues |
| Collector agent/sidecar | App cannot reach the local endpoint | Data queues in the SDK and then gets dropped | Bounded SDK queues, agent health checks, and an alternate route if architecture allows |
| Collector gateway | Agents cannot forward data | Multiple agents accumulate backlogs simultaneously | Queues/retries in agents, multiple gateways, or fallback endpoints |
| Backend ingest/storage | Collector send errors, quota or storage exhausted | Data rejected or backlog grows | Bounded retries, quota-bounded persistent queues, capacity alerts, and load-shedding policies |
| Query/UI | Data is ingested, but dashboards or queries fail | On-call assumes applications stopped emitting telemetry | Check ingestion independently from query paths; use APIs or verify alternate signals |

Distinguishing ingest failures from query failures is critical. An empty dashboard does not prove applications stopped emitting telemetry. Data may already be ingested while queries or the UI are failing. Check stage by stage from source to backend.

## 2. Establish Fallback Principles Before Choosing Technology

A solid fallback strategy follows these principles:

- **Never block business requests on telemetry.** Do not perform synchronous HTTP exports inside controllers, services, or Observation handlers running on request threads. Use registries/exporters and batch span processors with proper asynchronous handling.
- **Bound every resource.** In-memory queues, disk queues, retry counts, timeouts, worker counts, and flush intervals must all be bounded.
- **Accept controlled telemetry loss.** When every destination is unavailable and buffers are full, dropping data under a clear policy is better than exhausting heap or hanging the application.
- **Preserve high-value signals.** Maintain aggregate metrics and essential operational logs; sample traces according to traffic and defined budgets.
- **Decouple application health from telemetry backend health.** Backend failures must not automatically mark the application unhealthy or fail readiness checks.
- **Monitor the pipeline over an independent channel.** Never send "exporter failing" alerts solely through the failing exporter itself.
- **Recover in a controlled manner.** When the backend comes back, drain backlogs at a bounded rate to avoid triggering a second overload.

The goal is not to guarantee every span and log is saved under every condition. The goal is to keep the application stable, know clearly which telemetry can be dropped, and recognize when the pipeline returns to normal.

## 3. Isolate Telemetry from the Business Execution Path

In a Spring Boot application, recording metrics and creating Observations typically happen in-process, while export should be decoupled from business request execution. Recording a counter updates data in the local registry. For tracing, a batching span processor queues finished spans and exports them on a dedicated worker.

Never write a custom Observation handler that makes HTTP calls to a backend whenever an Observation starts or stops. Doing so leaks network latency, timeouts, and backend failures directly into business requests. Custom handlers should perform local, fast, bounded work.

Reference architecture:

~~~mermaid
flowchart TD
    A["Spring Boot application"] --> B["Micrometer Observation / MeterRegistry"]
    B --> C["Local SDK queues and exporters"]
    C --> D["Collector agent / sidecar"]
    D --> E["Bounded queue and retry"]
    E --> F["Collector gateway"]
    F --> G["Telemetry backend"]
    B --> H["Actuator metrics endpoint"]
    H --> I["Prometheus scraper"]
    A --> J["Structured stdout logs"]
    J --> K["Node or platform log collector"]
~~~

Placing a Collector agent close to the application lets the app send to a local-network endpoint. The agent handles batching, retries, and forwarding to the gateway. This reduces the application's direct coupling to remote backends, though it does not eliminate all failures: if the agent stops or its queue fills up, the in-app SDK still needs bounded fallback behavior.

If exporting directly from the application to a backend, carefully verify the timeouts, export schedule, queues, and retries of that specific exporter. Do not assume every `MeterRegistry`, tracing bridge, or exporter shares identical buffering behavior.

## 4. Retries, Timeouts, and Queues Must Be Bounded

Retries help during brief disruptions, such as a gateway restart or a few seconds of network drop. Unbounded retries can cause backlogs to grow endlessly, consume heap, pin threads, and slam the backend the moment it recovers.

A resilient configuration should define:

- **Timeout:** the maximum time a single export attempt may wait. Timeouts should fit the export worker budget, not scale with business request durations.
- **Backoff:** an increasing delay between retries, usually with jitter so multiple instances do not retry in lockstep.
- **Retry horizon:** total duration a batch is kept for retry attempts before dropping or falling back to another policy.
- **Queue capacity:** maximum number of batches or items the exporter/Collector may hold.
- **Overflow policy:** behavior when the queue is full—for example, rejecting new items, evicting old items, or dropping per processor policy.
- **Concurrency:** number of concurrent export workers, preventing unbounded growth when the backend slows down.
- **Payload size:** limits on batch sizes and attributes so a single item does not consume abnormal memory.

For example, if a Collector has a queue of 5,000 batches and each batch averages 80 KB in memory, payloads alone require about 400 MB—excluding runtime overhead and queue data structures. Never pick a queue size purely from a default value; measure batch sizes and memory budgets under realistic load.

A full queue does not always crash the application. If the exporter runs asynchronously and the queue is full, new data may simply be dropped. The system must emit signals indicating dropped item counts so operators know the extent of data loss.

### Example OpenTelemetry Collector configuration

The snippet below illustrates an OTLP receiver, memory limiter, batching, retries, and an exporter queue. It is a starting example; verify component names and schema against your deployed Collector version.

~~~yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 512
    spike_limit_mib: 128
  batch:
    timeout: 5s
    send_batch_size: 512

exporters:
  otlp:
    endpoint: telemetry-gateway.internal:4317
    timeout: 10s
    tls:
      ca_file: /etc/otel/certs/ca.pem
    sending_queue:
      enabled: true
      queue_size: 5000
    retry_on_failure:
      enabled: true
      initial_interval: 1s
      max_interval: 30s
      max_elapsed_time: 300s

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlp]
    metrics:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlp]
    logs:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlp]
~~~

In this example, the Collector maintains a queue and retries for the configured duration. Once retries expire or the queue fills up, data can still be dropped. `memory_limiter` protects the Collector process from memory pressure; it does not replace queue bounds, disk quotas, or capacity monitoring.

This configuration does not create a persistent queue automatically. In-memory queues lose data when the Collector restarts or the process is killed. If survival across restarts is required, configure a storage extension and persistent queue per your Collector version's docs, along with quotas, permissions, and retention policies for the storage volume.

Never configure an infinite queue trying to save every piece of telemetry. A bounded queue with observable drops is usually far safer than an unbounded queue that can exhaust Collector or node resources.

## 5. Choose Fallback Behavior by Signal Type

Metrics, traces, and logs have different characteristics. What works for metrics may not suit traces or logs.

### Metrics: prioritize aggregate figures and local scraping

Metrics are critical for tracking trends, rates, and SLOs. If a push-based metrics backend fails, a local scrape endpoint can offer an alternate collection path when a Prometheus server or backup scraper remains operational.

With Spring Boot Actuator, when the application has the appropriate Prometheus registry and exposes the endpoint, an illustrative configuration is:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
~~~

The Actuator Prometheus endpoint typically resides at `/actuator/prometheus`. Expose this endpoint only on a controlled management network and configure proper authentication and network policies. The matching Prometheus registry dependency is required; exposing the endpoint without the registry produces no Prometheus data.

A scrape endpoint does not persist metrics by itself. If the scraper also goes down, data in the local registry may roll over or be lost on process restart. Treat it as an alternate collection path when a scraper is active, not as durable storage.

Some systems use `CompositeMeterRegistry` or add `SimpleMeterRegistry` as a local registry. This can help for testing or in-process inspection, but it does not automatically replay missed data to a remote registry once the backend recovers. Counters and timers in a local registry are not a durable queue either. Add a backup registry only when it is clear who scrapes it, where data is read, and how double counting is avoided.

### Traces: bounded queues, sampling, and deliberate drops

Traces are typically larger than metric samples and can carry many spans, attributes, and events. During prolonged collector/backend outages:

- Keep bounded batch queues in the SDK or Collector.
- Use bounded timeouts and retries.
- Maintain head sampling at a level aligned with your resource budget.
- Accept span drops when queues fill up and measure dropped span counts.
- Use persistent queues only when retention needs and cost justify them.

If the system relies on tail sampling at a Collector to retain error or slow traces, remember that the Collector must receive enough spans and have enough memory to decide. When the gateway is unavailable, gateway-side tail-sampling policies cannot operate. If you need to retain a subset of traces during a gateway outage, design a local Collector or explicit fallback head-sampling policy; do not assume error traces will always be kept.

Never automatically raise the sampling rate while the backend is failing. Doing so pushes extra data into already-full queues and adds load right when the pipeline is degraded. If sampling must change, use a tested policy and watch its impact on memory, CPU, and transfer volume.

### Logs: keep local output bounded

For containerized applications, structured logs are usually written to stdout/stderr for collection by the runtime or node agent. If the log backend fails, the platform can continue holding logs on the node within rotation and disk quota limits.

Never redirect all logs into unbounded files inside the container. Configure rotation, size limits, and retention at the runtime/platform layer. If the node agent or log pipeline also fails, logs may be lost when containers or nodes are replaced.

Preserve high-value operational logs such as startup errors, exporter errors, queue overflows, shutdowns, and recoveries. Avoid logging a line on every continuous retry, or fallback itself will trigger a log storm. Apply rate limiting or periodic error summaries.

Never dump full trace payloads or entire Observations into logs as a "backup" for tracing. That inflates log volume, risks exposing sensitive data, and makes querying harder.

## 6. Should an Application Become Unhealthy When the Telemetry Backend Fails?

For most business services, the answer is no. Readiness answers whether an instance can accept business traffic. Liveness answers whether the process is still running and needs a restart. A telemetry backend is not a direct business dependency in most architectures.

If readiness depends on sending traces to a backend, a telemetry outage can pull every instance out of the load balancer. The application stops serving users even though the database and business dependencies are completely healthy. If liveness depends on the backend, the orchestrator may continuously restart instances when the root cause is an external observability service.

Separate these states cleanly:

| State | Meaning | Behavior |
|---|---|---|
| Application readiness | Application can serve business requests | Depends on business prerequisites, not by default on the telemetry backend |
| Application liveness | Process is alive and not deadlocked | Do not restart solely because an exporter cannot connect |
| Telemetry health | Whether exporter/Collector can send and receive signals | Reports degraded state separately for dashboards and alerts |
| Telemetry delivery quality | Whether backlogs, drops, or data loss occur | Tracks queues, retries, export failures, and storage capacity |

You can create a dedicated health indicator or separate health group for telemetry. However, avoid placing that indicator inside the readiness group unless the service has an explicit business requirement that telemetry must work before serving traffic.

Clearly define exceptions: some systems have legal or contractual requirements where recording an audit event is mandatory to complete a transaction. In those cases, audit events must be recorded through a durable mechanism with appropriate guarantees, such as a transactional outbox or audit store. Never rely on a trace exporter or metrics backend as the sole mechanism for recording mandatory transactions.

## 7. Self-Monitor Telemetry Over an Independent Channel

If an exporter fails and alerts about that exporter only travel through the same exporter, on-call responders may never learn the pipeline stopped sending data. You need an independent observation channel or an external check.

Signals to monitor include:

- Successful and failed export counts.
- Export duration and timeout counts.
- Queue size, queue utilization, and oldest item age if exposed by the component.
- Counts of dropped spans, metrics, or logs.
- Retry counts and retry duration.
- Collector receiver accepted/refused, exporter send failures, and memory limiter state.
- Persistent queue usage, disk usage, and backlog growth rate.
- End-to-end delay from signal creation until queryable in the backend.

Internal metric names in SDKs and Collectors change across versions, distros, and exporters. Inspect the actual internal telemetry of your running components rather than hardcoding dashboards from unverified metric names.

Ways to build an independent monitoring channel:

1. Scrape local application or Collector health/metrics from an independent Prometheus instance.
2. Emit rate-limited diagnostic logs via stdout for platform collection.
3. Verify synthetic spans or heartbeats from a component outside the main pipeline.
4. Alert when the backend receives no signals within an expected window, even if no errors are emitted from inside the backend.
5. Use infrastructure monitoring to track disk, memory, network, and pod/agent status.

A dead-man signal helps detect cases where the entire pipeline silently stops shipping data. For example, an independent probe emits periodic heartbeats and an external monitor alerts if the heartbeat disappears. The probe must traverse the observed path while the alert travels via a separate channel.

## 8. Recover the Backend Without Causing a Secondary Overload

When the backend comes back online, queues across many applications may hold large backlogs. If every agent flushes its backlog at maximum speed simultaneously, the backend can overload again and repeat the outage.

Recovery should include these steps:

1. Confirm the backend ingests fresh data stably and has sufficient quota/storage.
2. Inspect queues, retry counts, drop counts, and age of queued data.
3. Let agents drain backlogs in bounded batches at a throttled rate.
4. Watch ingest latency, backend CPU, memory, storage, and rejection errors.
5. Increase drain rate gradually if the backend has spare capacity.
6. Once queues return to normal, confirm export success and ingestion delay have recovered.

Old data can lose operational value. A trace from hours ago may no longer matter for current alerts; delayed metric samples can skew dashboard time windows. Therefore, persistent queues need retention/TTL rules and policies for stale data. Never retain backlogs indefinitely.

Retries can cause duplicate delivery in some pipelines or when connections drop after the backend accepted a batch but before the client received the acknowledgment. Never assume telemetry delivery is always exactly-once. This is also why metrics and traces must not be used as ledgers or strict transactional records.

## 9. Shutdown and Restart During a Pipeline Outage

When an application receives a shutdown signal, the SDK may attempt to flush pending data. Flushing must have a clear timeout. If the backend is unresponsive, the application must exit within the platform's shutdown grace period rather than hanging indefinitely.

With Spring Boot, let the framework or configured SDK manage integration and lifecycle. If you manually instantiate an exporter, processor, or registry, close resources in lifecycle hooks and call flush/shutdown using the library's API with a finite deadline. Never call flush per request, and never create a new exporter per business operation.

Account for:

- The deployment environment's shutdown grace period.
- Maximum flush time must be shorter than the remaining shutdown deadline.
- In-memory queues are lost when the process terminates.
- Persistent queues survive restarts only if storage is configured durably and mounted properly.
- Many instances restarting together can spike connection load and create an export burst right after startup.

If the telemetry backend is failing, shutdown cannot guarantee all data was delivered. Record unexported and dropped item counts where components support it; this data is needed for incident reports.

## 10. Fallback Testing Scenarios

Do not test the pipeline only when every component is healthy. Run failure drills to confirm applications stay within resource limits and on-call engineers detect the degradation.

| Scenario | Outcomes to Verify |
|---|---|
| Block connectivity from application to Collector | Business requests keep processing; exporter timeouts/retries stay bounded; queues do not grow unbounded |
| Stop the Collector agent | Applications do not hang; agent/exporter alerts fire; queue overflow follows policy |
| Stop the gateway for several minutes | Agents retry with backoff; queues stay within quota; backend avoids a retry storm |
| Backend returns quota or rate-limit errors | Collector records export failures; queues and retries remain bounded; capacity alerts fire |
| Fill the persistent queue | Collector executes the defined overflow policy; application and node disks do not fill up |
| Recover the backend after an outage | Backlog drains at a bounded rate; backend does not experience a secondary overload |
| Restart application while exporter fails | Shutdown completes within timeout; data is retained or dropped as designed |
| Stop the log agent | stdout/file rotation stays within quota; node does not run out of disk; no log storm occurs |
| Telemetry backend down while business logic is healthy | Readiness/liveness do not fail merely because the observability backend is down |

In each test, measure both sides: telemetry quality and business serving quality. Watch p95/p99 latency, error rate, CPU, heap, thread pools, and application throughput. A fallback only passes if it holds defined bounds under prolonged failure conditions.

## 11. Runbook When the Telemetry Backend Stops Receiving Data

When dashboards or alerts show telemetry interruption, responders can proceed in order:

1. **Confirm scope:** one service, one node, one Collector, or the entire backend? Cross-check multiple sources and timestamps instead of relying on a single broken dashboard.
2. **Check the source:** is the application still generating metrics/traces/logs? Are Actuator endpoints, local logs, and SDK state healthy?
3. **Check the exporter:** endpoint, DNS, TLS certificates, authentication, timeouts, retries, and connection errors.
4. **Check the Collector:** is the receiver accepting data, is the memory limiter rejecting data, are queues full, is the exporter failing?
5. **Check the backend:** quotas, ingestion rate, storage, tenant, authentication, and service status.
6. **Protect the application:** keep queues within quota, avoid unbounded sampling or retries, and confirm readiness/liveness do not depend on telemetry outside business requirements.
7. **Monitor recovery:** verify fresh signals reach the backend, drain backlogs at a bounded rate, and document the window of missing telemetry.

Never purge queues or mass-restart Collectors before checking whether queues hold unique data that should be preserved. If restarts are necessary, record queue sizes, storage state, and data-loss policy first.

## 12. Design Mistakes to Avoid

**Synchronous export on request threads.** A slow backend inflates latency and can turn a telemetry issue into a business outage. Use asynchronous export and inspect exporter threads and queues.

**Infinite retries.** Backlogs grow until memory or disk runs out. Set retry horizons, backoff, quotas, and overflow policies.

**Unbounded queues.** Unbounded buffers only delay failure and enlarge the blast radius. Assign explicit resource budgets to every queue.

**Marking applications unhealthy when the telemetry backend fails.** Orchestrators may drain or restart instances that are still handling business traffic normally. Separate telemetry health from readiness/liveness.

**Using SimpleMeterRegistry as a backup store.** This registry keeps data in process memory and does not replay it to a backend. Define clear scrape paths and limits.

**Increasing sampling while the backend is already overloaded.** Extra spans put more stress on queues and networks. Keep budgeted sampling policies and change them only after assessing impact.

**Treating retries as a guarantee against loss or duplication.** Connections can drop after the backend receives a batch but before the client sees the acknowledgment. Telemetry does not replace an audit store or transaction log.

**Using the same channel to report failures of that channel.** External checks and an independent alerting path are required to detect signal loss.

**Skipping outage drills.** Configurations with queues and retries can still misbehave in practice. Test prolonged outages, full queues, restarts, and recovery.

## 13. Operational Conventions to Standardize

A Spring Boot service can codify these decisions into deployment standards:

1. Export telemetry asynchronously; never make business requests wait on a telemetry backend.
2. Set timeouts, retry horizons, backoff, queue capacity, and overflow policies at every stage.
3. Prefer Collector agents/gateways to aggregate, batch, and control export; use direct export only with clear operational justification.
4. Use scrape endpoints or stdout as alternate collection paths when infrastructure supports ingesting and storing them.
5. Use persistent queues only when surviving restarts is required; configure quotas, retention, permissions, and capacity monitoring.
6. Keep readiness/liveness tied to business serving ability; report telemetry health separately.
7. Monitor export failures, queue utilization, dropped data, ingest delay, and backend status over an independent channel.
8. Throttle recovery drain rates and run periodic outage drills.
9. Never use metrics, traces, or log pipelines as audit stores or transaction ledgers.

When the telemetry backend fails, applications should enter a controlled degraded state: continue serving business traffic within resource bounds, retain what signals can be kept, record lost data metrics, and recover the pipeline at a safe rate. Fallback is only dependable when queues, retries, health checks, and recovery procedures have been tested under real failure conditions.
