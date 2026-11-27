# Dashboards by Client, Server, and Dependency

## 1. An RPC Needs to Be Viewed from Three Sides

In **Spring gRPC**, a request can pass through a client, a gateway, a receiving gRPC server, and multiple dependencies such as databases, HTTP services, or another gRPC service. Each side observes a different part of the same operation. With only a single combined dashboard, operations teams struggle to tell whether latency comes from the network, server handler, retries, or a dependency.

A useful dashboard system should have three linked perspectives:

- **Client dashboard:** what does the caller experience? Tracks logical RPCs, final status, caller wait time, retries, and deadlines.
- **Server dashboard:** how many RPCs does the service receive and process? Tracks request rate, server status, processing duration, in-flight calls, and saturation.
- **Dependency dashboard:** where do latency and errors originate beneath the service? Tracks outbound calls, databases, HTTP/gRPC dependencies, connection pools, and retries.

The three perspectives must not be summed or compared as if they measured the same event. One logical call on the client can produce multiple attempts on the server; one server call can produce multiple dependency calls. Dashboards must clearly indicate measurement scope.

## 2. Request Flow and Measurement Scope

~~~mermaid
flowchart LR
    C[Client application] -->|Logical RPC| S[Spring gRPC server]
    S -->|Outbound call| D1[Database]
    S -->|Outbound RPC| D2[Downstream gRPC service]
    C -.-> MC[Client metrics]
    S -.-> MS[Server metrics]
    D1 -.-> MD[Dependency metrics]
    D2 -.-> MD
~~~

For example, a client invokes an RPC, receives `UNAVAILABLE` on the first attempt, retries, and succeeds on the next attempt:

| Perspective | Observable Event Count |
| --- | ---: |
| Client logical call | 1 |
| Client attempts | 2 |
| Server received RPCs | 1 or 2, depending on which attempts reached the server |
| Dependency calls | 0 or more, depending on whether handlers ran and called dependencies |

Therefore:

- Client call count measures logical operations initiated/completed by the caller.
- Attempt count measures transport/RPC executions if supported by instrumentation.
- Server call count measures RPCs actually reaching the server application.
- Dependency call count measures each outbound call the service makes to a downstream system.

Do not derive retry counts by subtracting client calls from server calls. Attempts can fail before reaching the server; gateways may also generate their own retries.

## 3. Standardizing Metrics Before Building Dashboards

Before building panels, agree on the metric contract: name, metric type, start/end boundaries, labels, and units. The example below uses standardized application metric names with the `app_grpc` prefix. This is an illustrative convention, not mandatory names automatically emitted by every gRPC/OpenTelemetry version.

| Metric | Type | Scope |
| --- | --- | --- |
| app_grpc_client_calls_completed_total | Counter | One completed logical RPC on the client, tagged with final status |
| app_grpc_client_call_duration_seconds | Histogram | Time from when the client starts the logical call to terminal result |
| app_grpc_client_attempts_completed_total | Counter | Each completed client attempt, including initial attempt and retries |
| app_grpc_client_retry_recovered_total | Counter | Logical calls that ultimately returned OK after at least one retry |
| app_grpc_server_calls_started_total | Counter | RPCs received by the server application |
| app_grpc_server_calls_completed_total | Counter | Closed server RPCs, tagged with final status |
| app_grpc_server_call_duration_seconds | Histogram | Time from when the server receives the call until it closes the call |
| app_grpc_server_inflight | Gauge | Number of currently active server RPCs |
| app_grpc_dependency_calls_completed_total | Counter | Each completed outbound call to a dependency |
| app_grpc_dependency_call_duration_seconds | Histogram | Duration of outbound dependency calls |
| app_grpc_executor_active_threads | Gauge | Number of running workers per pool |
| app_grpc_executor_max_threads | Gauge | Maximum worker limit per pool |
| app_grpc_executor_queue_size | Gauge | Number of queued tasks per pool |
| app_grpc_executor_queue_capacity | Gauge | Configured capacity of the queue |
| app_grpc_executor_queue_wait_seconds | Histogram | Time a task waits from submission until execution starts |
| app_grpc_executor_rejected_total | Counter | Number of tasks rejected by the executor |

Histograms need buckets aligned with the service's target latency. Use seconds consistently as the unit; do not mix milliseconds and seconds in the same metric family.

If gRPC/OpenTelemetry instrumentation or Spring/Micrometer integration already provides metrics with equivalent meaning, prefer those and check the semantic conventions of your running version. Do not emit duplicate metrics just to rename them. Only create custom `app_grpc` metrics for gaps in instrumentation or when a stable cross-service contract is required.

## 4. Labels: Sufficient to Filter, Without High Cardinality

Useful labels generally have finite value sets:

| Label | Example | Notes |
| --- | --- | --- |
| service | catalog-service | Name of the observed service |
| target | catalog.internal | Target called by the client |
| method | catalog.v1.CatalogService/GetItem | Full gRPC method |
| grpc_status | OK, UNAVAILABLE, DEADLINE_EXCEEDED | Final status or attempt status, named clearly |
| dependency | inventory-db, pricing-service | Dependency name from an allowlist |
| operation | query-item, GetPrice | Bounded operation name |
| pool | grpc-callback, database-worker | Fixed executor name |
| environment | staging, production | Deployment environment |

Do not use request ID, trace ID, user ID, tenant ID, order ID, tokens, or exception messages as metric labels. High-cardinality values belong in logs/traces. Use normalized method and dependency names; avoid labels pulled directly from URLs, SQL, dynamic hostnames, or request content.

For histograms with many labels, time series count grows as the product of label values and buckets. Start with a small label set, measure actual series counts, and add dimensions only for concrete operational questions.

## 5. Client Dashboard: What Is the Caller Experiencing?

The client dashboard answers: from the calling application's perspective, are RPCs fast and reliable?

Key panels:

| Panel | Displays | Operational Question |
| --- | --- | --- |
| Logical call rate | Calls/second by target and method | How many operations are callers initiating? |
| Final status rate | OK rate and each gRPC status | Which errors are callers receiving? |
| Client latency p50/p95/p99 | Logical call duration | How long do callers wait? |
| Attempts per logical call | Average/distribution of attempts | Are retries amplifying load? |
| Retry recovery | Calls succeeding after retries | Are retries recovering transient errors? |
| Deadline exceeded | Count and ratio of DEADLINE_EXCEEDED | Are deadlines too tight or dependencies slow? |
| Cancellation | Count of CANCELLED calls | Are callers cancelling or upstream disconnecting? |

Client latency includes many components: client-side queueing, transport, network, gateway, server processing, and retry/backoff wait time. Do not conclude the server is slow solely from client p99; cross-reference the server and dependency dashboards.

## 6. PromQL for the Client Dashboard

The following queries assume the metric contract in Section 3 and that the `grpc_status` label represents the logical call's final status.

Call rate by target and method:

~~~promql
sum by (target, method) (
  rate(app_grpc_client_calls_completed_total[5m])
)
~~~

Logical call error ratio:

~~~promql
sum by (target, method) (
  rate(app_grpc_client_calls_completed_total{grpc_status!="OK"}[5m])
)
/
clamp_min(
  sum by (target, method) (
    rate(app_grpc_client_calls_completed_total[5m])
  ),
  1e-9
)
~~~

Client p95 latency:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, target, method) (
    rate(app_grpc_client_call_duration_seconds_bucket[5m])
  )
)
~~~

Average attempts per logical call:

~~~promql
sum by (target, method) (
  rate(app_grpc_client_attempts_completed_total[5m])
)
/
clamp_min(
  sum by (target, method) (
    rate(app_grpc_client_calls_completed_total[5m])
  ),
  1e-9
)
~~~

The attempts metric must increment once per attempt, including the initial attempt. If instrumentation only counts additional retries, the formula changes to `1 + retries/logical call`. Document semantics clearly in metric descriptions so dashboards do not misinterpret them.

Ratio of logical calls recovered via retries out of all successful logical calls:

~~~promql
sum by (target, method) (
  rate(app_grpc_client_retry_recovered_total[5m])
)
/
clamp_min(
  sum by (target, method) (
    rate(app_grpc_client_calls_completed_total{grpc_status="OK"}[5m])
  ),
  1e-9
)
~~~

## 7. Server Dashboard: How Is the Service Processing?

The server dashboard focuses on the load the application actually receives and its ability to finish RPCs:

| Panel | Displays | Operational Question |
| --- | --- | --- |
| Received RPC rate | Calls/second by method | How many requests is the service receiving? |
| Server status rate | OK and each gRPC status | Which error types are handlers returning? |
| Server latency p50/p95/p99 | Time from receive to close | Which methods show rising server processing time? |
| In-flight RPCs | Currently open calls | Are there hung calls or abnormally long streams? |
| Executor active/queue | Workers and backlog | Are callback or business pools saturated? |
| Rejected tasks | Tasks rejected | Has the server hit capacity limits? |
| Deadline/cancellation observed | Calls ending via timeout/cancel | Is work abandoned by callers or are deadlines too short? |

Server duration does not necessarily equal handler CPU execution time. For streaming RPCs, call duration can span the entire time the stream is open; split panels by RPC type when unary and streaming behave differently.

## 8. PromQL for the Server Dashboard

Server request rate:

~~~promql
sum by (method) (
  rate(app_grpc_server_calls_started_total[5m])
)
~~~

Ratio of server calls not ending with `OK`:

~~~promql
sum by (method) (
  rate(app_grpc_server_calls_completed_total{grpc_status!="OK"}[5m])
)
/
clamp_min(
  sum by (method) (
    rate(app_grpc_server_calls_completed_total[5m])
  ),
  1e-9
)
~~~

Server p95 duration:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, method) (
    rate(app_grpc_server_call_duration_seconds_bucket[5m])
  )
)
~~~

Executor queue utilization ratio:

~~~promql
app_grpc_executor_queue_size
/
clamp_min(app_grpc_executor_queue_capacity, 1)
~~~

Rejection rate by pool:

~~~promql
sum by (pool) (
  rate(app_grpc_executor_rejected_total[5m])
)
~~~

Queue occupancy should be read alongside active threads, max pool size, queue wait duration, and request latency. A low queue does not always mean a healthy service; the pool may be blocked on a dependency or concurrency-limited at another layer.

## 9. Dependency Dashboard: Where Is the Bottleneck?

An RPC server typically calls multiple dependencies. The dashboard must separate each dependency and operation to answer which downstream service is driving latency or errors.

| Panel | Displays | Meaning |
| --- | --- | --- |
| Dependency call rate | Outbound calls/second | How heavily is the service calling each dependency? |
| Dependency error rate | Status/error by dependency | Which dependency is failing? |
| Dependency latency p95/p99 | Outbound call duration | Is delay in DB, HTTP, or downstream gRPC? |
| Connection pool usage | Active/idle/pending connections | Are calls waiting for connections? |
| Dependency retries | Attempts and recovery | Are service-side retries increasing downstream load? |
| Circuit breaker state | Closed/open/half-open | Is the dependency isolated? |
| Timeout/cancel | Timeouts and cancelled calls | Are deadlines/cancellations propagating to dependencies? |

For databases, add query duration, connection acquisition wait, active connections, pending acquisitions, and pool timeouts. For HTTP/gRPC dependencies, monitor connection pools, DNS/connect/TLS handshakes if supported by instrumentation, statuses, and retry attempts.

## 10. PromQL for the Dependency Dashboard

Dependency call rate:

~~~promql
sum by (dependency, operation) (
  rate(app_grpc_dependency_calls_completed_total[5m])
)
~~~

Dependency error rate (example for a gRPC dependency with `grpc_status` label):

~~~promql
sum by (dependency, operation) (
  rate(app_grpc_dependency_calls_completed_total{grpc_status!="OK"}[5m])
)
/
clamp_min(
  sum by (dependency, operation) (
    rate(app_grpc_dependency_calls_completed_total[5m])
  ),
  1e-9
)
~~~

Dependency p95 latency:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, dependency, operation) (
    rate(app_grpc_dependency_call_duration_seconds_bucket[5m])
  )
)
~~~

If a dependency is not gRPC, do not force its status into `grpc_status`. Use an outcome/status label appropriate to the protocol, then normalize in the dashboard if comparison is needed. For instance, HTTP has status codes; databases have outcomes like `success`, `timeout`, or `connection_error`. Similarly, if call-start rate is needed instead of completion throughput, instrument a separate `started` counter.

## 11. Connecting the Three Dashboards for Root-Cause Analysis

When client p99 rises, compare across the same time range step by step:

| Observation | Likely Area to Investigate |
| --- | --- |
| Client p95 rises, server p95 stable | Network, gateway, client queue, or retry backoff |
| Client and server p95 rise together | Server processing or shared resources |
| Server p95 rises alongside dependency p95 | Dependency may be the bottleneck |
| Server p95 rises, dependency steady, executor queue grows | Thread pool saturation or CPU/lock contention |
| Client attempts/logical call rises | Retry amplification or transient transport errors |
| Dependency call rate rises faster than server RPC rate | One RPC calling a dependency multiple times or service-side retries |
| Server in-flight rises while request rate stays steady | Increasing call duration, long streams, or stuck handlers |

Dashboards narrow down the area; traces pinpoint a specific request. Use a trace ID to open the corresponding trace and inspect client, server, and dependency spans together. Logs should contain `trace_id`, `span_id`, and correlation ID in a controlled form, without credentials or sensitive payloads.

## 12. Grafana Layout and Drill-Down

An overview dashboard can be organized into three rows:

1. **Client:** call rate, final error rate, p95/p99, attempts per call.
2. **Server:** received rate, status, server duration, in-flight, executor saturation.
3. **Dependency:** call rate, error rate, p95/p99, connection pool, and retries.

Create dashboard variables with bounded cardinality:

- `environment`
- `cluster`/`namespace`
- `service`
- `method`
- `target` or `dependency`

Use links from method panels to server/dependency dashboards preserving the same time range and filters. From panels, link to Explore or trace view when exemplars/trace correlation are configured.

Do not make request ID a default dashboard variable because it is unsuitable for aggregating metrics. Search individual requests via traces/logs.

## 13. SLOs and Alerting

Alerts should be based on SLOs and user impact, not a single isolated metric:

| Alert | Conditions to Observe | Response |
| --- | --- | --- |
| Client error budget burn | Final error ratio exceeds threshold across multiple windows | Check target, status, and retries |
| Client latency SLO burn | p95/p99 exceeds target alongside real traffic | Drill down into server/dependency |
| Server saturation | Queue near capacity, active workers at max, and rising latency | Shed load, scale, or resolve bottleneck |
| Dependency degradation | Dependency error/latency rises and impacts RPCs | Check downstream, pool, and circuit breaker |
| Retry amplification | Attempts/logical call rises abnormally | Check root error and retry policy |
| In-flight RPC leak | In-flight rises continuously without traffic growth | Find non-terminating streams/calls |

Exact thresholds depend on SLOs, baselines, and traffic. Do not alert merely because p99 is high in a window with a handful of requests; combine volume, duration, error ratio, and multi-window burn rates to reduce false positives.

## 14. Common Mistakes When Building Dashboards

1. **Combining client calls and server calls.** Both metrics have different measurement scopes, especially with retries or gateway retries.
2. **Using only average latency.** Averages hide tail latency; histograms and p95/p99 are required.
3. **Undefined timing boundaries.** Client duration, server duration, and dependency duration cannot be compared if measured differently.
4. **Putting dynamic IDs in labels.** Cardinality can overload the monitoring backend.
5. **Treating all non-OK statuses as one error.** `UNAVAILABLE`, `DEADLINE_EXCEEDED`, `CANCELLED`, and `PERMISSION_DENIED` have distinct causes.
6. **Not measuring retry attempts.** Final success rate can mask retry amplification.
7. **Looking only at server latency.** The client can be slow due to network, gateway, or backoff.
8. **Looking only at dependency latency.** Queue wait and executor saturation can slow requests even when dependencies are healthy.
9. **Not checking histogram buckets.** Unsuitable buckets make p95/p99 inaccurate.
10. **Using dashboards as causal proof.** Dashboards narrow scope; traces, logs, and system checks confirm root cause.

## 15. Testing Dashboards and Metric Contracts

Before putting dashboards into operation, generate predictable scenarios:

| Test Scenario | Expected Dashboard Behavior |
| --- | --- |
| Normal successful RPC | Client completed OK, server started/completed, matching dependency calls |
| Server returns UNAVAILABLE | Client/server statuses reflect their respective measurement scopes |
| Client retries and succeeds | One logical call, multiple attempts, final status OK |
| Slow dependency | Dependency p95 rises; server/client latency may rise accordingly |
| Full executor queue | Queue occupancy/rejections rise and server status reflects overload |
| Deadline expires | Client deadline error; server/dependency may observe cancellation |
| Caller cancels stream | Client cancellation and server in-flight drops after cleanup |
| Zero traffic | Rates at or near 0; error ratio does not trigger divide-by-zero alerts |

Verify metric descriptions, labels, units, and histogram buckets. Compare counters with logs/traces over a short test window to catch double-counting or missing events. Verify dashboards never expose tokens, payloads, or sensitive IDs.

## 16. Practical Exercise

Given `CatalogService` calling `InventoryService` and a database:

1. Define the metric contract for client logical call completion, client attempt completion, server call start/completion, and dependency call completion.
2. Create three dashboards or three panel rows for client, server, and dependency.
3. Add call rate, final status ratio, p95/p99, and attempts per logical call.
4. Add server in-flight, executor active threads, queue size/capacity, and rejected tasks.
5. Add dependency latency, error rate, connection pool wait, and retries.
6. Write PromQL queries matching the metric contract and verify label cardinality.
7. Simulate retries, dependency latency, executor saturation, and deadline expiry.
8. Use traces to drill down from a client call to server spans and dependency spans.
9. Propose SLO-based alerts and check for false positives at low traffic.

**Completion criteria:** learners can distinguish client logical calls, server received RPCs, and dependency calls; design metrics with clear timing boundaries/labels; build RED and saturation dashboards across the three perspectives; write p95/error/retry queries; and use traces to identify root causes rather than guessing from a single panel.

### References

- [gRPC OpenTelemetry Metrics](https://grpc.io/docs/guides/opentelemetry-metrics/): gRPC client/server observability metrics.
- [OpenTelemetry Metrics](https://opentelemetry.io/docs/concepts/signals/metrics/): counters, histograms, gauges, and metric attributes.
- [Prometheus Querying](https://prometheus.io/docs/prometheus/latest/querying/basics/): PromQL and time-series queries.
- [Prometheus Histograms](https://prometheus.io/docs/practices/histograms/): histogram buckets and percentiles.
- [Grafana Dashboards](https://grafana.com/docs/grafana/latest/dashboards/): dashboard variables, panels, and drill-down.
- [Spring gRPC Reference](https://docs.spring.io/spring-grpc/reference/): gRPC client/server integration in Spring.
