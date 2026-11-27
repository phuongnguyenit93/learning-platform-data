# Post-Deployment Verification

A deployment can only be considered stable once the new version receives traffic properly, handles critical business flows, and continues emitting reliable telemetry for operations. A successful rollout status or a health endpoint returning `UP` is necessary, yet neither proves that users are error-free, latency has not increased, or downstream dependencies are working properly.

In Spring Boot, post-deployment verification combines Spring Boot Actuator, Micrometer Observation, metrics, logs, and distributed tracing. The process should answer four questions: which version is running; is the application ready to serve; have request quality or resource usage changed; and when anomalies occur, can operations trace the root cause across signals?

## Verification Goals and Scope

After this lesson, you will be able to:

- Establish a pre-release baseline and define acceptance criteria grounded in the service's SLOs.
- Verify rollout status, liveness, readiness, and critical business flows after traffic shifts to the new version.
- Read metrics to spot shifts in traffic, error rates, latency, and resource saturation.
- Use logs and traces to verify end-to-end request correlation across components.
- Decide whether to proceed with the rollout, pause, or roll back based on observed evidence.

The scope here is verifying a Spring Boot application after deployment to a live runtime environment. Illustrative commands assume the application includes Spring Boot Actuator with the required endpoints configured. Metric names and labels can vary by Spring Boot version, MVC/WebFlux stack, registry, and active instrumentation.

## Pre-Release Preparation

Post-deployment verification is hard to judge without knowing what normal looked like beforehand. Before starting a rollout, record:

1. **Release identity:** service name, environment, version or commit, image digest, release timestamp, deployment ID, and primary change set.
2. **Scope of changes:** new configuration, feature flags, data migrations, upgraded dependencies, and affected endpoints or business flows.
3. **Operational baseline:** request rate, error rate, p95/p99 latency, CPU, heap, GC, thread pools, connection pools, and key business metrics over a representative window.
4. **Decision criteria:** SLOs, error budget, active alert thresholds, rollout halt triggers, and a verified rollback procedure.
5. **Observability readiness:** confirm metrics, logs, and traces are already flowing prior to deployment; verify dashboards and alerts can distinguish the new version from the old one.

Baselines should come from the same service, same environment, and a window with comparable traffic patterns. When traffic rises or falls sharply, compare ratios and percentiles rather than raw request counts alone. For canary rollouts, always compare the new instance group against the stable group over the same timeframe under equivalent load.

## Post-Deployment Verification Workflow

### 1. Verify rollout status and version identity

First, confirm the deployment platform rolled out the intended image and configuration to the right environment. Check expected replica counts, running instances, restart counts, crash loops, image pull errors, secret/config mount failures, and rollout status. For rolling updates or canaries, know exactly which instances run the new version and what traffic share reaches them.

On the application side, verify version or build metadata via dashboards, startup logs, or a protected info endpoint. Never infer version solely from pod names or deployment timestamps. If the application exposes build information via Actuator, the `info` endpoint must be configured and protected appropriately; it is not safe to expose arbitrary build details publicly by default.

Signals requiring immediate investigation include repeated restarts, fewer ready replicas than expected, instances running the wrong image, missing configuration, failed migrations, or startup logs reporting dependency connection errors. An unready instance may not yet receive traffic, so service-wide aggregate dashboards can temporarily hide errors unique to the new version.

### 2. Verify health, liveness, and readiness

Spring Boot Actuator exposes a health endpoint to assess application status. When health probes are enabled, the two probe groups mean different things:

- **Liveness** indicates whether the process is healthy enough to keep running or needs a restart. Liveness should normally reflect internal process health.
- **Readiness** indicates whether the instance is ready to accept requests. Readiness may check dependencies essential to serving traffic.

Minimal configuration example for an application exposing health and probes over HTTP:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      probes:
        enabled: true
      show-details: when-authorized
```

In Kubernetes environments, Spring Boot may auto-configure health probes for the runtime. If not enabled automatically, enable them explicitly with `management.endpoint.health.probes.enabled=true`. HTTP reachability still depends on application security settings and management port configuration.

Check the corresponding endpoints, adjusting host, port, and credentials for your environment:

```bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
```

Expected output is an appropriate HTTP status and health status `UP` for required groups. Endpoints or probe groups may return 404 or be blocked if disabled, unexposed, or restricted by security; verify configuration and access permissions before concluding the app is broken.

Never include every external dependency in liveness. For example, if the database drops briefly and liveness flips to `DOWN`, the platform may repeatedly restart instances even though restarting cannot fix the database. That makes the outage worse. Readiness can check dependencies strictly needed to serve requests, while accounting for optional dependencies, circuit breakers, and degraded serving modes.

Health `UP` also does not replace smoke tests. It confirms configured health indicators pass, not that a specific API returns correct data or completes a business transaction.

### 3. Run smoke tests on critical flows

Once instances are ready and receiving traffic, run a small, controlled set of checks across key flows. Prioritize operations representative of request paths: authentication, reads, creating or updating a test entity, calling key dependencies, and processing messages if a message broker is used.

Smoke tests should verify:

- HTTP status and response schema match the API contract.
- Returned data is correct, not merely a 2xx response.
- Side effects occur exactly once and do not leave uncontrolled test data behind.
- Response latency stays within business flow limits.
- Requests hit the expected version and generate expected logs, metrics, and traces.

Example measuring status and total duration of a prepared smoke-test URL:

```bash
curl --fail --silent --show-error \
  --output /dev/null \
  --write-out 'status=%{http_code} total=%{time_total}s\n' \
  "$SMOKE_URL"
```

`SMOKE_URL` must point to an appropriate endpoint. For authenticated endpoints, pass credentials via the environment's secret mechanism; never hardcode tokens or passwords into scripts, logs, or shell history. Never run write operations in production without safe test fixtures and cleanup rules.

Smoke tests should traverse the real traffic path or corresponding ingress/gateway, because calling localhost directly only checks the instance and bypasses DNS, load balancers, TLS, routing, and outer-layer policies.

### 4. Inspect metrics across four signal groups

After smoke tests, watch metrics throughout the rollout and over a representative post-rollout window. The four standard signal groups are traffic, errors, latency, and saturation.

| Group | What to Observe | Post-Deployment Anomalies |
|---|---|---|
| Traffic | Request count, throughput, processed messages or jobs | Traffic drops to 0, skewed requests across instances, consumers stop receiving messages |
| Errors | HTTP 4xx/5xx, exceptions, timeouts, retries, failed messages | Error rate climbs, errors concentrate on the new version or a specific dependency |
| Latency | p50, p95, p99, and dependency call durations | p95/p99 rises while average barely moves; a specific endpoint slows sharply |
| Saturation | CPU, heap, GC, thread pools, connection pools, queue depth | Pools exhausted, queues growing, long thread waits, prolonged GC, CPU or memory nearing limits |

With Spring MVC or WebFlux and standard instrumentation, the `http.server.requests` timer metric is commonly used to observe HTTP requests. You can inspect it via Actuator when the `metrics` endpoint is exposed:

```bash
curl -fsS \
  'http://localhost:8080/actuator/metrics/http.server.requests'

curl -fsS \
  'http://localhost:8080/actuator/metrics/http.server.requests?tag=method:GET&tag=status:200'
```

The metrics endpoint returns available measurements for that meter and tag set. It does not automatically supply every percentile. To compute p95/p99 in a metrics backend, configure histograms or percentiles appropriately and ensure the registry supports that query style.

With the Prometheus registry, `/actuator/prometheus` can expose HTTP timers as series like `http_server_requests_seconds_count` and `http_server_requests_seconds_sum`; `_bucket` series appear when histograms are enabled. The sample PromQL queries below are only meaningful when the matching metric and histogram are exported:

```promql
# HTTP 5xx request ratio over total requests in 5 minutes
sum(rate(http_server_requests_seconds_count{status=~"5.."}[5m]))
/
clamp_min(sum(rate(http_server_requests_seconds_count[5m])), 1e-9)

# p95 latency from histogram
histogram_quantile(
  0.95,
  sum by (le) (rate(http_server_requests_seconds_bucket[5m]))
)
```

When reading results, slice by service, environment, version, and endpoint template if those labels exist. Compare error rates and latency of the new version against baseline or the stable group. Never look only at averages: a small number of very slow requests can hide inside the mean while still pushing p95/p99 past SLOs.

Check JVM and dependency metrics as well, depending on enabled instrumentation. Common meters include `jvm.memory.used`, `jvm.gc.pause`, `jvm.threads.live`, `process.cpu.usage`, `system.cpu.usage`, and datasource connection pool metrics. Inspect both usage and limits or wait states: high active connection counts become clearly actionable when viewed alongside max pool size, pending requests, and query latency.

If the service emits business metrics—such as orders created, successful payments, or completed messages—check them alongside technical metrics. An API can return HTTP 200 while business logic fails to produce the expected outcome.

**Note on cardinality:** Never add user IDs, order IDs, emails, request IDs, or free-form values to metric tags. Continuously changing values can explode time series counts, driving up storage costs and overloading the metrics backend. Keep metric tags to small, stable value sets; put detailed identifiers in logs or traces when needed for debugging and allowed by data policies.

### 5. Verify logs and correlation

Post-deployment logs catch startup errors, invalid configuration, dependency timeouts, abnormal retries, migration errors, and exceptions that surface only under live traffic. Filter logs by service, environment, version, deployment ID, and rollout timeframe. Compare error frequency against baseline and check whether errors cluster on a single instance or version.

Structured logs should carry enough context to filter and join with traces. Illustrative example:

```json
{
  "timestamp": "2026-11-22T07:30:15.421Z",
  "level": "ERROR",
  "service.name": "order-service",
  "service.version": "2.8.1",
  "deployment.id": "deploy-20261122-01",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7",
  "message": "Database call timed out"
}
```

Actual field names depend on the logging encoder and MDC setup. When Micrometer Tracing is configured, trace IDs and span IDs can be populated into MDC for output by log patterns or JSON encoders. Verify they actually appear in logs from your smoke-test requests; simply adding a tracing dependency without checking log formatting and the log pipeline is not enough to prove correlation works.

Inspect logs at three moments: startup, initial traffic admission, and after executing smoke-test flows. Some errors appear only when a code path is invoked for the first time or as connection pools come under load. Never raise global log levels carelessly during investigation; doing so can spike costs, leak sensitive data, or degrade performance. Never log access tokens, passwords, secrets, or unnecessary personal data.

### 6. Verify distributed tracing and telemetry pipelines

Pick a sampled smoke-test request and open its trace in the backend. Verify:

- The trace carries the right service name and new release version.
- Spans across gateway, Spring Boot application, and dependencies appear in logical order.
- Parent-child relationships and span durations accurately reflect the request path.
- Error spans carry appropriate status or exception details; unexplained gaps are not misread as fast dependencies.
- Trace IDs from logs open the matching trace in the tracing system.

For requests crossing multiple services, verify context propagation across HTTP or messaging boundaries. W3C Trace Context typically uses the `traceparent` header; systems may configure another format such as B3. If traces break into disconnected traces after deployment, check propagator configuration, client instrumentation, message headers, and Observation creation in participating services.

Sampling can keep some requests out of the trace backend. Use a request known to be sampled or generate controlled test traffic consistent with your sampling policy. Never conclude tracing is broken just because one random request lacks a trace; equally, never assume the pipeline works just because you see an old trace. Confirm fresh traces created after deployment reach the backend.

Check the entire telemetry path too: exporters are sending, Collectors are receiving and forwarding, the backend is ingesting fresh data, and credentials/TLS/network policies remain valid after config changes. If application metrics rise while dashboards stay flat, separate instrumentation issues from scrape/export/collector/backend failures. Inspect exporter logs and Collector health metrics if available.

### 7. Monitor canaries and make rollout decisions

In canary or rolling deployments, observe per version or instance group. Never expand a rollout just because the first few requests succeed. Allow sufficient traffic and time to validate critical flows, dependencies, and behavior under representative load.

You can use this decision table as an initial runbook:

| Observation | Appropriate Action |
|---|---|
| Readiness stable, smoke tests pass, error rate and latency within SLO, saturation normal | Proceed with planned rollout stages |
| Metrics fluctuate slightly within thresholds, not enough data to conclude | Hold current canary percentage, gather more data, and inspect logs/traces |
| 5xx errors, timeouts, or p95/p99 degrade noticeably on the new version | Pause rollout, isolate affected endpoint/dependency, and evaluate rollback |
| Readiness fails, continuous instance restarts, wrong data, or broken business flow | Halt rollout; execute approved rollback or recovery procedure |
| Metrics/logs/traces fail to reach backend after deployment | Pause release sign-off; restore telemetry pipeline or run defined fallback checks |

Final decisions must follow the organization's SLOs, error budgets, impact scope, and incident procedures. No single error percentage or latency threshold fits all services. When rolling back, keep monitoring because rolling back code does not automatically revert data migrations, published messages, cache mutations, or side effects that already ran. Verify backward compatibility and separate data recovery plans.

## Investigation Example: Slow API After Deployment

Suppose a new version rolls out cleanly and `/actuator/health` returns `UP`, yet dashboards show a sharp jump in p95 latency for `GET /api/orders`.

1. Break down metrics by version and endpoint template. If p95 increased only on the new version, the regression is tied to the release and the rollout must hold at its current percentage.
2. Check error rate, timeouts, and saturation. If active connections approach pool limits while pending connections and request latency climb together, the datasource pool is a strong lead.
3. Open a recent slow trace for the endpoint. If database spans dominate total duration, inspect queries, locks, indexes, query counts, and connection acquisition wait times.
4. Search logs by trace ID and deployment ID. Match timeouts, retries, or exceptions against the corresponding spans to pinpoint which step slowed down.
5. Pause the rollout. If metrics continue breaching SLOs and cannot be safely mitigated within the allowed window, roll back per runbook; then verify readiness, latency, and error rate return to baseline.

This example shows how `UP` health and green rollouts can still accompany performance regressions. Metrics expose scope and trends; traces pinpoint the slow step; logs provide error details and context. Combining all three drives evidence-based decisions.

## Post-Deployment Sign-Off Checklist

Before marking a deployment stable, verify:

- [ ] Expected service, version, image, and configuration are running; instance/replica counts match targets.
- [ ] No restart loops, startup failures, or unresolved migration errors exist.
- [ ] Liveness and readiness behave properly; instances receive traffic only when ready.
- [ ] Smoke tests across real traffic paths meet expected status, data correctness, and latency.
- [ ] Traffic, error rate, p95/p99 latency, and saturation stay within SLO/baseline criteria.
- [ ] Key business metrics reflect expected outcomes.
- [ ] New logs include version/deployment context and correlate with traces when tracing is enabled.
- [ ] Fresh traces cross key services/dependencies and arrive in the tracing backend.
- [ ] Metrics, logs, and traces continue ingesting post-deployment; dashboards and alerts work.
- [ ] Proceed or rollback decision is recorded with timestamp, evidence, and responsible owner.

A deployment can be declared stable when these checks pass across the defined observation window with no regressions breaching operational criteria. Save the version, timestamp, baseline, smoke test results, relevant dashboards, and any exceptions so the next release has clean reference data.
