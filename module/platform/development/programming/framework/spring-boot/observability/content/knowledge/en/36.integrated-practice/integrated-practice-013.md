# Production Readiness Checklist

Observability is only truly useful in production when operations teams can detect anomalies, determine blast radius, and trace root causes without destabilizing the application. Simply having a metrics endpoint or sending traces to a backend is not enough to be considered ready. You must simultaneously verify data quality, export reliability, access controls, cardinality cost, sampling, alerting, and incident response workflows.

This lesson provides a production readiness checklist for Spring Boot applications using Micrometer Observation, metrics, logs, and distributed tracing. Apply the checklist during pre-release reviews, re-verify after deployment, and archive evidence for every critical item. Values such as sampling rates, retention, alert thresholds, and cardinality budgets must be chosen according to each service's traffic, SLOs, and infrastructure capacity.

This lesson belongs to the **Integrated Practice** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module guides setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; this checklist brings together context propagation, tags/cardinality, exporters, sampling, and signal correlation into a single verification gate usable before live operations.

## Objectives

After this lesson, you will be able to:

- Assess the completeness and usefulness of metrics, logs, and traces before release.
- Verify instrumentation, context propagation, cardinality, and sampling.
- Confirm exporters, collectors, and backends behave reliably during network failures or application shutdowns.
- Protect management endpoints and eliminate sensitive data from telemetry.
- Design dashboards, SLOs, and alerts tied to operational actions.
- Compile verification evidence and make an evidence-based GO/NO-GO decision.

## How to Use the Checklist

Run checks against a configuration as close to production as possible. For each item, record one of three statuses:

| Status | Meaning | Action |
|---|---|---|
| PASS | Verification evidence exists and results meet criteria | Include in release evidence |
| FAIL | Missing data, misconfiguration, or criteria unmet | Fix and re-verify before release if mandatory |
| N/A | Does not apply to this service architecture | Document reason and reviewer |

Never mark PASS merely because a configuration file exists. You need runtime evidence such as metrics appearing, traces received by the backend, logs carrying correlation fields, endpoints secured, and alerts tested. If an item is N/A, explicitly state that the service does not use the corresponding component, such as having no messaging consumer.

## 1. Service Identity and Ownership

Telemetry must indicate which service, environment, and deployment version produced the data. Missing resource identity makes traces and metrics hard to distinguish across instances or environments.

| Item | Production-Ready Criterion | Evidence to Archive |
|---|---|---|
| Service name | Stable, unique name per service, e.g., `orders-service` | Resource attributes in traces and service labels in backend |
| Environment | Clearly distinguishes `dev`, `staging`, `production` | Resource attribute or deployment label |
| Service version | Can identify which build/release is emitting telemetry | Image tag, Git SHA, or version attribute |
| Instance identity | Can distinguish instances when investigating local failures | Pod/container/instance metadata provided by platform |
| Ownership | Team or on-call responsible for dashboards, alerts, and runbooks | Service catalog or ownership info in operations system |
| Time synchronization | Hosts/containers run synchronized clocks; log and span timestamps do not drift abnormally | NTP/clock sync configuration and real timestamp checks |

In Spring Boot, `spring.application.name` is the starting point for naming the application. Environment, version, and instance metadata can be supplemented through platform or OpenTelemetry resource configuration. Avoid using pod names as the service name because every scale event or rollout would create a brand-new service identity.

Basic configuration example:

```yaml
spring:
  application:
    name: orders-service
```

Resource names must stay consistent across metrics, logs, and traces. If metrics report `orders`, traces report `orders-service`, and dashboards use `order-api`, operations teams will have to maintain multiple names for the exact same service.

## 2. Instrumentation Coverage

Instrumentation must cover boundaries that help answer operational questions. Review along real execution flows rather than just counting how many Observations were created.

| Boundary | What to Observe | Verification Criterion |
|---|---|---|
| HTTP server | Traffic, latency, status, and route | Server metrics exist; routes use stable templates; failed requests are identifiable |
| Application/use case | Duration and key business outcomes | Observation exists for tracked use cases; stable names and bounded tags |
| HTTP/RPC client | Latency, errors, and called dependencies | Client instrumentation or equivalent Observation exists; trace context is propagated |
| Database | Query latency, errors, and pool saturation | Metrics/tracing exist for driver or pool; no dynamic SQL in tags |
| Messaging | Publish, consume, retries, and error handling | Producer/consumer boundaries covered; context propagated via message headers when supported |
| Background job | Duration, outcome, and execution runs | One Observation per appropriate unit of work; job errors recorded |
| Runtime | JVM, memory, GC, threads, and connection pools | Required meters exist to separate application bugs from resource exhaustion |

Do not instrument every method. A small getter or mapper rarely adds operational insight. Nor should you add manual Observations around HTTP clients or JDBC already covered by auto-instrumentation if the new span adds no context. Inspect traces for duplicate spans, overly granular spans, or overly broad boundaries.

For every custom Observation, you should be able to answer three questions: what operation is being measured, where does it start/end, and what will production on-call engineers do when the metric or span signals an anomaly?

## 3. Metrics: Usefulness and Cardinality

Metrics must show overall trends and support alerting. Verify at least four signal groups: traffic, errors, latency, and saturation. Add business metrics where they tie to concrete operational decisions.

### Metric Groups to Review

| Group | Example | Operational Question |
|---|---|---|
| HTTP traffic | Request count by route/method | Is traffic rising or dropping abnormally? |
| HTTP errors | 5xx responses, exception counts | Is the error ratio breaching the SLO? |
| HTTP latency | Duration histograms, p95/p99 from histograms | Are users experiencing slow requests? |
| Dependency | HTTP client duration/errors, DB query duration | Which dependency is slowing requests down? |
| Saturation | CPU, heap, GC pauses, thread pools, connection pools | Is the service close to exhausting resources? |
| Messaging | Queue depth, consumer lag, retries/failures | Is work backing up? |
| Business | Checkout accepted/rejected, payment outcomes | Is business functionality degrading even while HTTP returns 200? |

Not every service needs every meter in this table. Pick the groups matching your architecture, while ensuring critical dependencies have enough telemetry to detect bottlenecks.

### Controlling Cardinality

For each metric, list its tag keys and expected value sets. Estimate combinations by multiplying the cardinalities of tags. For instance, 4 methods × 6 status groups × 20 routes × 3 regions can create up to 1,440 combinations for a single metric before adding any other dimensions.

Mandatory criteria:

- Tag keys are stable and carry consistent meaning across endpoints.
- Tag values belong to a finite set or are normalized via an allowlist.
- HTTP URIs use route templates such as `/orders/{orderId}`.
- Never put `userId`, `orderId`, `requestId`, `traceId`, emails, tokens, raw query strings, or exception messages into metric tags.
- Never construct metric names or tag keys dynamically from request data.
- Maintain a cardinality budget for key metrics and a way to detect sudden series growth.

IDs may be needed in traces or logs to investigate a specific request, but they are not dimensions for grouping metrics. Use Micrometer Observation's low-cardinality key-values for metrics; high-cardinality attributes should only be added to traces when needed, permitted by data policy, and bounded by storage limits.

### Histograms and Latency

If dashboards need aggregated latency percentiles across multiple instances, verify histograms are enabled and the backend receives all buckets. Client-side percentiles cannot always be accurately aggregated across instances. Pick bucket boundaries suited to your SLO and required resolution; each bucket also increases series count.

Example configuration for the HTTP server timer in Spring Boot:

```yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
```

Do not enable histograms broadly for every meter without estimating cost. Check series counts before and after enabling, then confirm p95/p99 queries work on multi-instance data.

## 4. Distributed Tracing and Context Propagation

Traces must capture a request's journey across critical boundaries. Test a request flowing through at least one success path and one error path.

Tracing checklist:

- [ ] HTTP server spans are created with accurate service/resource identity.
- [ ] HTTP client spans appear for instrumented dependencies.
- [ ] Parent/child relationships are sound; no duplicate spans exist for the same call.
- [ ] W3C Trace Context (`traceparent`) is propagated over HTTP when configured for this standard.
- [ ] Messaging context is injected/extracted via message headers if the service uses a broker.
- [ ] Async executors, `@Async`, or callbacks preserve context using the configured propagation mechanism.
- [ ] Technical failures are properly marked on spans with appropriate exception events.
- [ ] Span names and attributes contain no unbounded input data or sensitive data.
- [ ] Traces can be queried by service name, operation, and time range.

Context propagation must be verified across both thread and process boundaries. A scope opened on one thread must not be held and closed arbitrarily from another thread. For asynchronous work, use the context propagation and executor mechanisms supported by your Spring/Micrometer stack. With messaging, producers and consumers have independent lifecycles; link them via trace context in messages rather than holding scopes open while waiting for messages.

Not every span needs payload data. Store only attributes with investigative value such as operation, dependency, status, or error category. Baggage propagated across services requires an allowlist, size limits, and explicit data policies.

## 5. Sampling and Trace Discoverability

Sampling affects exported traces, not metrics. A service can continue incrementing HTTP request counts while some requests have no traces because head sampling dropped them.

Check:

- Sampling probability is configured per environment and real traffic volume.
- Local/test environments can use high sampling for easier debugging; production needs an explicit budget.
- Services within the same trace respect sampling decisions and propagation headers.
- There is a way to investigate when a trace is unsampled, such as relying on metrics, logs, and policy-compliant request correlation.
- If slow/error traces must be retained, tail-based sampling and collector memory/buffer limits have been evaluated.
- Received trace rate and export error rate are monitored at the collector/backend where possible.

Head sampling decides early inside the SDK. The collector cannot retain a trace the application never sent. Tail-based sampling can only decide based on spans that reach the collector and requires sufficient buffering to wait for the full trace or decision window.

Never use trace IDs as metric tags to compensate for sampling. Use metrics for global trends, logs for events with correlation context, and traces for analyzing retained requests.

## 6. Logs and Signal Correlation

Logs must support investigating individual events while linking to traces whenever context exists.

| Item | Production-Ready Criterion |
|---|---|
| Structured logging | Logs in parseable format, preferring JSON in centralized environments |
| Correlation | Includes trace ID/span ID when the request executes inside a tracing context |
| Severity | Consistent log levels; actionable errors are not logged at DEBUG |
| Error details | Includes exception type and stack trace when needed; messages do not leak secrets or payloads |
| Volume | Does not log full payloads or overly verbose success logs causing log storms |
| Retention | Retention window and access controls match investigative needs |
| Redaction | Passwords, tokens, cookies, payment data, and personal data are stripped or masked |

Check your logging pattern or JSON encoder to ensure MDC fields such as `traceId` and `spanId` are emitted. Actual field names may be `trace_id`, `traceId`, or follow your platform's schema; standardize schemas across services for easy querying.

Do not assume logs will automatically contain a trace ID when a request is unsampled or has no tracing context. In those situations, logs still need timestamp, service, level, operation, and enough error context to act without exposing sensitive data.

## 7. Exporter, Collector, and Backend

The telemetry pipeline is part of the production system. Correct exporter configuration alone is not enough; verify transport paths, retries, queues, limits, and behavior when the backend goes down.

| Component | Verification Criterion |
|---|---|
| Metrics registry | Meters are registered and scraped successfully; scrape endpoint is not publicly exposed |
| Prometheus or metrics backend | Scrape targets healthy, timestamps and labels accurate, ingestion not dropping data |
| Tracing exporter | OTLP endpoint/protocol matches receiver; service/resource attributes preserved |
| OpenTelemetry Collector | Receivers, processors, exporters, and pipelines enabled; queues/retries bounded |
| Trace backend | Traces queryable by service and time; retention and access controls appropriate |
| Network | DNS, routing, firewalls, TLS, and authentication work from the deployment environment |
| Failure behavior | Export timeouts or backend unavailability never hang business requests indefinitely |
| Shutdown | Application has sufficient time to flush pending telemetry before process exit |

For OTLP, endpoint and protocol must match. OTLP/HTTP typically uses endpoints like `/v1/traces`; OTLP/gRPC typically uses the gRPC receiver address per collector configuration. Never point a gRPC exporter at an HTTP endpoint or vice versa.

If the exporter uses a batch processor, size queues, batches, timeouts, and retries to match service and backend capacity. Unbounded queues can drive up memory during prolonged backend outages. Overly small queues can drop telemetry during traffic spikes. Track exporter failures, dropped spans, queue utilization, and collector exporter errors if those components expose such metrics.

Applications need graceful shutdown to flush pending telemetry within the platform's termination grace period. Test rollouts/restarts under traffic; do not assume all buffered spans are shipped if the process is killed immediately.

## 8. Securing Endpoints and Telemetry Data

Actuator and telemetry can reveal internal structure, routes, traffic volume, errors, and environment details. Only expose required endpoints and restrict access.

- Only expose `health` and metrics endpoints needed by the scraper; never expose all Actuator endpoints by default in production.
- Restrict `/actuator/prometheus`, `/actuator/metrics`, and management endpoints using network policies, authentication, or Spring Security.
- Show health details only to authorized groups; readiness/liveness must reflect actual serving state.
- Protect OTLP receivers/exporters with network policies, TLS, and infrastructure authentication.
- Strip tokens, cookies, authorization headers, payment payloads, and personal data from log/span attributes.
- Do not accept baggage from untrusted sources without an allowlist and size limits.
- Define retention, access permissions, and data deletion procedures for metrics, logs, and traces.
- Verify dashboards and queries do not inadvertently display sensitive data.

Never dump full request/response bodies into spans just for extra context. Select essential attributes and apply redaction before export.

## 9. SLOs, Dashboards, and Alerts

Dashboards must answer "is the service meeting user expectations?" Alerts must point to clear next actions. A dashboard packed with charts untethered from SLOs or operational decisions is hard to use during an incident.

Verify dashboards include these perspectives where relevant:

- Request rate and traffic by key routes or operations.
- Error rate, especially 5xx errors and critical business errors.
- p50/p95/p99 latency against SLOs and by primary endpoints.
- Dependency latency/errors for databases, payment, identity, or external services.
- Saturation: CPU, heap, GC, thread pools, connection pools, and queue depth.
- Business outcomes such as checkout success or payment failures if these are core indicators.
- Telemetry pipeline health: scrape failures, exporter failures, dropped spans, or collector queues.

Alerts should specify an owner, severity, trigger condition, dashboard link, and runbook. Prioritize alerts based on SLO/error budgets or user-impacting symptoms. Avoid paging solely because a single instance had a brief CPU spike without evidence of service impact.

For histograms, verify p95/p99 queries use the right buckets and aggregations. Across multiple instances, aggregate histograms before computing quantiles as supported by your backend. Never add or average per-instance percentile values directly.

Every production alert should be tested by inducing the corresponding condition in staging or a safe test environment. Confirm notifications reach the right channel/on-call rotation and that the runbook can actually be executed.

## 10. Pre-Release Testing and Drills

Run checks against the build and configuration slated for deployment. A minimum test suite includes:

1. **Happy path:** Send successful requests, confirm HTTP metrics increment, traces are created per sampling policy, and logs include correlation fields.
2. **Error path:** Trigger controlled errors, confirm status/error metrics, error spans, and logs contain sufficient investigative context.
3. **Slow dependency:** Slow down a dependency in test, confirm latency shows up on the right client span and dashboard.
4. **Cardinality:** Send many requests with distinct IDs, confirm metric series counts do not grow per ID.
5. **Context propagation:** Call across HTTP clients, async executors, or message brokers and verify traces link across boundaries.
6. **Exporter unavailable:** Briefly disconnect the collector/backend in test, confirm business requests retain bounded timeouts and app memory does not grow unboundedly.
7. **Restart/rollout:** Restart the app under traffic, verify graceful shutdown and that telemetry loss stays within acceptable bounds.
8. **Access control:** Attempt to access Actuator endpoints from unauthorized networks/users and confirm denial.
9. **Alert test:** Trigger defined alert conditions and confirm the right recipients and runbook are reached.

You can use `ObservationRegistry` test handlers and meter registries in automated tests to verify names/tags. Use integration tests to verify real export or propagation when needed. Unit tests on tag normalization functions do not replace verifying that the backend receives telemetry.

## 11. Reference Production Configuration

The example below illustrates externalizing environment-specific values to environment variables. This is not a complete configuration for every service; endpoints, sampling rates, and exposure must be adapted to your deployment platform.

```yaml
spring:
  application:
    name: orders-service

management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
  endpoint:
    health:
      probes:
        enabled: true
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
  tracing:
    sampling:
      probability: ${TRACING_SAMPLING_PROBABILITY:0.1}
  otlp:
    tracing:
      endpoint: ${OTEL_EXPORTER_OTLP_TRACES_ENDPOINT:http://otel-collector:4318/v1/traces}
```

In this configuration, `0.1` is merely an illustrative value for a moderate-traffic environment; choose according to your sampling policy and actual trace volume. `health` and `prometheus` are exposed only over a management network or protected endpoints. If the service does not use Prometheus scraping, replace the endpoint to match your platform's metrics export model.

Never commit credentials or exporter tokens into configuration files. Pull secrets from a secret manager or platform secret injection mechanism. When using multiple Spring profiles, inspect the final resolved values after profiles and environment variables are applied to avoid accidentally running 100% sampling or wide endpoint exposure in production.

## 12. GO/NO-GO Decision Gate

Before release, classify the following items as mandatory criteria or risk-accepted items approved by an owner.

| Group | GO Criterion |
|---|---|
| Identity | Service, environment, and version can be unambiguously identified |
| Metrics | Core request/error/latency and saturation metrics carry data; cardinality within budget |
| Tracing | Traces for critical flows are created, exported, and linked across dependencies per sampling policy |
| Logs | Logs provide sufficient investigative detail, include correlation when context exists, and leak no secrets |
| Export pipeline | Endpoints, protocols, collectors, and backends verified; failure behavior is bounded |
| Security | Actuator, OTLP, and telemetry backends enforce proper access controls |
| SLO/alert | Dashboards, alerts, owners, and runbooks verified |
| Validation | Happy path, error path, propagation, exporter failure, and rollout verified |

Choose **NO-GO** if missing telemetry prevents on-call teams from detecting or investigating severe outages, sensitive endpoints are unintentionally exposed, cardinality threatens to exhaust the backend, or export failures can impact business requests. For inapplicable items, record N/A with justification. For accepted risks, record the owner, remediation deadline, and approver.

## Consolidated Checklist

### Service and Instrumentation

- [ ] Service name, environment, version, and owner are clearly defined.
- [ ] Key HTTP server, client, database, messaging, and job boundaries have been reviewed.
- [ ] No duplicate instrumentation or low-value spans exist.
- [ ] Observation names are stable and describe meaningful operations.

### Metrics and Traces

- [ ] Traffic, errors, latency, saturation, and critical business metrics emit data.
- [ ] Tag values are bounded; URIs use route templates; cardinality has a budget.
- [ ] Histograms/buckets match SLO queries and series cost budgets.
- [ ] Trace context propagates across HTTP, async, and messaging per architecture.
- [ ] Sampling policy and trace retention are confirmed.

### Logs, Export, and Security

- [ ] Logs have structured fields, correlation fields, and redaction.
- [ ] Metrics registry, OTLP exporter, collector, and backend have been verified.
- [ ] Queues/retries/timeouts and graceful shutdown are bounded.
- [ ] Actuator, OTLP, and telemetry backends are secured.
- [ ] Baggage/span attributes contain no unnecessary sensitive data.

### Operations and Release

- [ ] Dashboards and SLOs reflect user experience.
- [ ] Alerts specify owner, severity, notification channel, and runbook.
- [ ] Happy path, error path, slow dependency, exporter failure, and rollout have been tested.
- [ ] PASS/FAIL/N/A evidence is archived with the release.
- [ ] Remaining risks have explicit owners and documented acceptance decisions.

## Conclusion

Observability production readiness is the ability to detect, explain, and resolve anomalies under real operating conditions. Verify all three signals—metrics, logs, and traces; control cardinality, propagation, sampling, and sensitive data; test exporters and behavior during backend failures; and connect dashboards and alerts to SLOs, owners, and runbooks. Mark a service ready only when runtime evidence exists for critical flows and remaining risks have been formally accepted by accountable owners.
