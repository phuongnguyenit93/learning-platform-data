# Alerting on Error Rate and Saturation

## 1. Alerts Must Reflect User-Facing Errors and Resource Exhaustion Risk

In **Spring gRPC**, a service can stay alive and accept connections while RPCs continuously fail, latency spikes, or executors run out of capacity. A health check only indicates that the process answers a simple probe; it does not prove the service is serving requests within its SLO.

Two critical signal groups:

- **Error rate:** proportion of RPCs failing to deliver the outcome promised by the API, such as server errors, timeouts, or dependency failures impacting callers.
- **Saturation:** utilization of bounded resources such as executor threads, queues, database connections, outbound connection pools, or CPU.

A good alert answers three questions: what is broken, how severely are users impacted, and what should the on-call engineer do next. A single metric crossing a threshold for a few seconds does not necessarily warrant waking on-call; consider duration, traffic volume, SLO, and correlated signals.

## 2. Defining Error Rate Before Writing Rules

Not every non-`OK` gRPC status means the service is violating its availability SLO. For example:

| Status | Common Interpretation | Count as Availability Error? |
| --- | --- | --- |
| INTERNAL, UNKNOWN | Unexpected processing error | Usually yes |
| UNAVAILABLE | Service or dependency temporarily unavailable | Usually yes |
| DEADLINE_EXCEEDED | Did not complete within time budget | Yes if timeout is the service's/SLO's responsibility |
| RESOURCE_EXHAUSTED | Quota or capacity exhausted | Usually yes if callers did not intentionally exceed quota |
| INVALID_ARGUMENT | Request violates contract | Usually no |
| UNAUTHENTICATED, PERMISSION_DENIED | Caller lacks credentials/permissions | Usually no for availability SLIs |
| CANCELLED | Cancelled by caller or upstream | Depends on cause and SLO |
| NOT_FOUND | Resource does not exist | Usually a valid business outcome |

Define **eligible requests** and **bad events** according to each RPC's SLO. Using a naive expression like `grpc_status != OK` causes expected caller errors such as `INVALID_ARGUMENT` or `PERMISSION_DENIED` to inflate error rates falsely.

An application metric contract can tag `slo_result="good"` or `slo_result="bad"` on each completed logical server call:

| Metric | Type | Meaning |
| --- | --- | --- |
| app_grpc_server_calls_completed_total | Counter | Eligible completed RPCs for SLIs, labeled with service, method, grpc_status, and slo_result |
| app_grpc_server_call_duration_seconds | Histogram | Server RPC processing duration |
| app_grpc_server_inflight | Gauge | Currently active RPCs |
| app_grpc_executor_active_threads | Gauge | Running workers per pool |
| app_grpc_executor_max_threads | Gauge | Maximum workers per pool |
| app_grpc_executor_queue_size | Gauge | Queued tasks per pool |
| app_grpc_executor_queue_capacity | Gauge | Queue capacity per pool |
| app_grpc_executor_rejected_total | Counter | Tasks rejected by the executor |
| app_grpc_dependency_calls_completed_total | Counter | Completed outbound dependency calls, with outcome |
| app_grpc_db_pool_active | Gauge | Database connections currently in use |
| app_grpc_db_pool_max | Gauge | Database connection limit |
| app_grpc_db_pool_pending | Gauge | Requests waiting for a connection |

The names above are an illustrative metric contract, not mandatory defaults from gRPC or OpenTelemetry. If existing instrumentation already exports equivalent metrics, use them and map labels/semantics clearly.

Counters used in SLI formulas should contain only eligible requests per contract. RPCs excluded from the SLO such as `INVALID_ARGUMENT` or certain `CANCELLED` calls still need operational metrics for investigation, but must not enter the SLI denominator if the SLO excludes them.

## 3. Calculating Error Ratio Correctly

Error ratio over a time window is bad eligible requests divided by all eligible requests.

With Prometheus counters, use `rate()` to obtain the growth rate over the window. Always sum numerator and denominator over the same label set before dividing:

~~~promql
sum by (service, method) (
  rate(app_grpc_server_calls_completed_total{slo_result="bad"}[5m])
)
/
clamp_min(
  sum by (service, method) (
    rate(app_grpc_server_calls_completed_total[5m])
  ),
  1e-9
)
~~~

Do not average per-instance error ratios. An instance with 2 requests and 1 error should not carry the same weight as an instance with 20,000 requests and 10 errors. Summing bad events and eligible events first before dividing produces a traffic-weighted ratio.

If only gRPC status is available, you can match an SLO error status set:

~~~promql
sum by (service, method) (
  rate(app_grpc_server_calls_completed_total{
    grpc_status=~"INTERNAL|UNKNOWN|UNAVAILABLE|DEADLINE_EXCEEDED|RESOURCE_EXHAUSTED"
  }[5m])
)
/
clamp_min(
  sum by (service, method) (
    rate(app_grpc_server_calls_completed_total[5m])
  ),
  1e-9
)
~~~

This status list is only an example. Decide individually with the product/SLO owner whether `RESOURCE_EXHAUSTED`, `DEADLINE_EXCEEDED`, and `CANCELLED` are bad events; do not copy this regex blindly for every RPC.

## 4. Avoiding False Alerts at Low Traffic

A single error out of one request can produce a 100% error ratio when traffic is very low. Ratio alerts should be paired with a traffic floor or minimum request count:

~~~promql
(
  sum by (service) (
    rate(app_grpc_server_calls_completed_total{slo_result="bad"}[5m])
  )
  /
  clamp_min(
    sum by (service) (
      rate(app_grpc_server_calls_completed_total[5m])
    ),
    1e-9
  )
) > 0.02
and on (service)
sum by (service) (
  increase(app_grpc_server_calls_completed_total[5m])
) >= 100
~~~

The example above fires only when the error ratio exceeds 2% and there are at least 100 calls in 5 minutes. For low-traffic APIs, a threshold of 100 may not fit; use longer windows, absolute error counts, synthetic probes, or separate availability outage alerts.

Do not treat "no time series" as zero errors. Have separate alerts for telemetry target down, scrape failure, or missing metrics. If a service intentionally has no traffic, do not alert on availability using a ratio divided by zero.

## 5. Alerting on SLO and Error Budget Burn Rate

If a service has a 99.9% availability SLO, the error budget ratio is `1 - 0.999 = 0.001`.

Burn rate indicates how fast the error budget is being consumed relative to the allowed rate:

~~~text
burn rate = observed error ratio / allowed error ratio
~~~

For example, an error ratio of 1.44% against a 99.9% SLO corresponds to a burn rate of 14.4x. If sustained, the budget will exhaust much faster than planned.

Multi-window alerts use paired long/short windows to avoid waking on-call for brief spikes:

- The long window confirms the issue has persisted long enough.
- The short window confirms the issue is still ongoing.
- The same burn threshold must be exceeded across both windows.

The rule example below illustrates a 14.4x burn rate with 1-hour and 5-minute windows. With a 30-day error budget, this burn level consumes roughly 2% of the budget in one hour if sustained continuously.

~~~promql
(
  sum by (service) (
    rate(app_grpc_server_calls_completed_total{slo_result="bad"}[1h])
  )
  /
  clamp_min(
    sum by (service) (
      rate(app_grpc_server_calls_completed_total[1h])
    ),
    1e-9
  )
) / 0.001 > 14.4
and on (service)
(
  sum by (service) (
    rate(app_grpc_server_calls_completed_total{slo_result="bad"}[5m])
  )
  /
  clamp_min(
    sum by (service) (
      rate(app_grpc_server_calls_completed_total[5m])
    ),
    1e-9
  )
) / 0.001 > 14.4
~~~

Replace `0.001` with your actual SLO error budget. In production, use recording rules for error ratio/burn rate to avoid repeating long expressions, and choose window pairs based on budget size, severity, and on-call policy.

## 6. Saturation: Measuring Limits Being Reached

Saturation is the state where a resource is near or at its limit. For Spring gRPC, monitor at least:

| Resource | Metric/Signal | Saturation Sign |
| --- | --- | --- |
| Callback executor | Active threads / max threads | Workers continuously hitting max |
| Executor queue | Queue size / capacity | Queue growing and nearly full |
| Executor rejection | Rejected task rate | New work requests being rejected |
| Database pool | Active / max, pending | Unable to acquire connections on time |
| Outbound connection pool | Active / max, pending acquire | Handlers waiting for downstream connections |
| CPU | Utilization, throttling | CPU near quota or being throttled |
| Memory/GC | Heap, allocation, pauses | Increasing GC pauses, heap near limit |
| In-flight RPCs | Active calls and duration | Backlogged calls, non-terminating streams |

A single high gauge alone is not enough to declare an incident. For example, 90% CPU can be normal if throughput is high and latency is stable. Saturation alerts should combine utilization, queueing/wait, rejections, or latency to detect real impact.

## 7. Alerts for Executor Queues and Workers

Queue occupancy ratio per pool:

~~~promql
app_grpc_executor_queue_size
/
clamp_min(app_grpc_executor_queue_capacity, 1)
~~~

Alert for nearly full queue:

~~~promql
(
  app_grpc_executor_queue_size
  /
  clamp_min(app_grpc_executor_queue_capacity, 1)
) > 0.80
and on (service, pool)
(
  app_grpc_executor_active_threads
  /
  clamp_min(app_grpc_executor_max_threads, 1)
) > 0.90
~~~

Rejection alert:

~~~promql
sum by (service, pool) (
  rate(app_grpc_executor_rejected_total[5m])
) > 0
~~~

A queue above 80% and workers above 90% over a sustained window shows the pool is running out of capacity. A rejection rate greater than zero is an even stronger signal that the pool is already dropping tasks; whether it warrants a page or warning depends on traffic and RPC criticality.

If an executor has zero queue capacity or uses `SynchronousQueue`, queue occupancy does not carry the usual meaning. In that case, monitor active/max, rejections, task wait, and latency.

## 8. Alerts for Databases and Downstream Dependencies

Database pool utilization:

~~~promql
app_grpc_db_pool_active
/
clamp_min(app_grpc_db_pool_max, 1)
~~~

Pending connection acquisitions:

~~~promql
app_grpc_db_pool_pending > 0
~~~

Combine pending count with connection wait time or query latency. A few brief pending requests may be a normal burst; sustained pending requests alongside rising p95 acquisition wait and RPC latency are a much stronger signal.

For dependency calls, use error ratio and p95 latency per dependency:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, dependency) (
    rate(app_grpc_dependency_call_duration_seconds_bucket[5m])
  )
)
~~~

~~~promql
sum by (dependency) (
  rate(app_grpc_dependency_calls_completed_total{outcome="failure"}[5m])
)
/
clamp_min(
  sum by (dependency) (
    rate(app_grpc_dependency_calls_completed_total[5m])
  ),
  1e-9
)
~~~

Do not apply a single latency threshold across all dependencies. Database queries, cache lookups, and downstream gRPC calls have different baselines. Set thresholds per dependency SLO and check whether that delay propagates to user-facing RPCs or is absorbed by caches/fallbacks.

## 9. Defining Actionable Alert Rules

A Prometheus alert rule typically includes:

- `expr`: condition computed from metrics.
- `for`: duration the condition must hold before firing.
- `labels`: `severity`, `team`, or `service` for routing.
- `annotations`: summary, impact description, and runbook link.

Example rules file:

~~~yaml
groups:
  - name: spring-grpc-availability
    rules:
      - alert: GrpcServerHighErrorRate
        expr: |
          (
            sum by (service) (
              rate(app_grpc_server_calls_completed_total{slo_result="bad"}[5m])
            )
            /
            clamp_min(
              sum by (service) (
                rate(app_grpc_server_calls_completed_total[5m])
              ),
              1e-9
            )
          ) > 0.02
          and on (service)
          sum by (service) (
            increase(app_grpc_server_calls_completed_total[5m])
          ) >= 100
        for: 5m
        labels:
          severity: page
          team: platform
        annotations:
          summary: "High gRPC error rate on {{ $labels.service }}"
          description: "Error ratio exceeded 2% with sufficient traffic for at least 5 minutes."
          runbook_url: "https://runbooks.example/grpc/high-error-rate"

      - alert: GrpcExecutorSaturated
        expr: |
          (
            app_grpc_executor_queue_size
            /
            clamp_min(app_grpc_executor_queue_capacity, 1)
          ) > 0.80
          and on (service, pool)
          (
            app_grpc_executor_active_threads
            /
            clamp_min(app_grpc_executor_max_threads, 1)
          ) > 0.90
        for: 10m
        labels:
          severity: warning
          team: platform
        annotations:
          summary: "Executor near capacity: {{ $labels.service }}/{{ $labels.pool }}"
          description: "Queue above 80% and active workers above 90% for 10 minutes."
          runbook_url: "https://runbooks.example/grpc/executor-saturation"
~~~

These are illustrative rules following the lesson's metric contract. Verify actual label names, rule syntax, and runbook URLs before deploying. Never let example domains or unapproved thresholds go straight into production.

## 10. Choosing Severity and Hold Duration

One classification approach:

| Severity | Typical Condition | Action |
| --- | --- | --- |
| Page | Fast SLO burn, high error rate with substantial traffic, service unavailable | Wake on-call |
| Warning | Queue/pool nearly full or rising dependency latency without clear SLO impact yet | Create ticket/investigate during business hours |
| Info | Brief spike or anomalous metric without user impact | Dashboard/event, no page |

Choose `for` according to metric characteristics:

- Error rate can use a 5-minute rate window and a `for` duration of a few minutes to filter brief spikes.
- Queue saturation should persist continuously before alerting, unless rejections are already impacting users.
- Hard exhaustion such as sustained queue rejections or database pool timeouts may require faster alerts.
- Multi-window SLO burn is usually more effective than a single fixed threshold for every method.

Do not make `for` overly long to hide noise; alerts may fire too late. Also do not set `for` to 0 on noisy metrics without evaluating false positives.

## 11. Alertmanager: Grouping, Routing, and Inhibition

Alertmanager prevents sending hundreds of notifications for the same incident:

- **Grouping:** group alerts by service, cluster, or team so on-call receives one contextual notification.
- **Routing:** send high-severity alerts to page, warnings to operational channels, info to dashboards.
- **Deduplication:** merge identical alerts within the same group.
- **Inhibition:** when a service is completely down, suppress secondary alerts like queue or dependency latency to cut noise.
- **Silencing:** temporarily mute notifications during approved maintenance windows.

Never use inhibition to hide root-cause alerts or mask prolonged failures. Silences require an owner, a reason, and an expiration time.

## 12. Runbooks Must Specify Next Investigation Steps

An alert without a runbook usually just adds noise. A runbook for gRPC high error rate should guide responders to:

1. Confirm the alert has sufficient traffic and accurate SLO classification.
2. Break down by method and gRPC status to locate the failing RPCs.
3. Compare client latency with server latency.
4. Open sample traces to locate slow/failing spans.
5. Check dependency errors/latency, executor queues, rejections, and database pools.
6. Check rollouts/config changes near the start time.
7. Apply safe mitigations: rollback, shed load, scale, or stop retry storms per procedure.

A saturation runbook should state pool limits, queue capacities, database connection caps, and scaling steps. Increasing thread pools is not always right: it can overload databases or downstream services even further.

## 13. Testing Alerts Before Enabling Paging

Test three distinct parts:

| Test Type | What to Verify |
| --- | --- |
| Query test | PromQL returns expected results against sample data and actual labels |
| Rule test | for duration, thresholds, traffic floor, and multi-window logic fire/resolve accurately |
| Notification test | Alertmanager routes to the right team/severity and groups/deduplicates/inhibits properly |

Scenarios to simulate:

- High error ratio under heavy traffic.
- A single error under very low traffic.
- A spike in caller errors such as `INVALID_ARGUMENT` excluded from the availability SLI.
- Transient queue spike that subsides on its own.
- Sustained queue and active workers near max.
- Executor beginning to reject tasks.
- Rising database pool pending count and acquisition timeouts.
- Rising dependency latency while server fallbacks preserve the SLO.
- Telemetry target losing scrapes or metrics disappearing.
- Incident lasting across multiple burn-rate windows.

Use `promtool test rules` or an equivalent test framework to validate Prometheus rules in CI. Verify alerts resolve when data returns to normal; alerts must not get stuck firing due to labels or absent series.

## 14. Common Mistakes

1. **Treating every non-OK status as an availability failure.** Caller errors and business errors may be expected outcomes.
2. **Averaging per-instance error ratios.** Sum numerators and denominators before dividing.
3. **No traffic floor.** A single error can yield a 100% ratio and page falsely.
4. **Using only one short window.** Brief spikes create alert noise.
5. **Alerting only on CPU.** Queues, connection pools, and rejections can saturate before CPU.
6. **Alerting only on queue occupancy.** Small queues or non-queuing pools require active/max and rejection signals.
7. **Blindly increasing pool sizes.** This can shift saturation from the executor to databases or downstream services.
8. **Not distinguishing warning from page.** On-call gets paged by signals with no user impact.
9. **Missing runbooks or owners.** Alerts fail to tell responders how to act.
10. **Not testing alerts for missing metrics.** "No data" can be mistaken for zero errors.

## 15. Practical Exercise

Given `CatalogService` calling `InventoryService` and a database:

1. Define the availability SLI and the list of gRPC statuses counted as bad events.
2. Write a PromQL error ratio query with a traffic floor, aggregating by service/method before dividing.
3. Design a multi-window burn-rate alert based on the SLO error budget.
4. Create alerts for executor queue/active workers, rejected tasks, and database pool pending count.
5. Classify page vs. warning and choose an appropriate `for` duration per signal.
6. Write Prometheus rules including summary, description, and runbook URL.
7. Test low traffic, brief spikes, sustained saturation, dependency degradation, and missing telemetry.
8. Configure Alertmanager grouping, routing, deduplication, and inhibition.
9. Drill the runbook from alert to traces, server methods, and the failing dependency.

**Completion criteria:** learners can define error SLIs per contract, write error-rate alerts immune to low-traffic distortion, detect saturation in executors and dependencies, apply multi-window SLO burn rates, route alerts with proper severity, and provide runbooks with concrete investigation steps.

### References

- [Prometheus Alerting Rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/): expressions, `for`, labels, and annotations.
- [Prometheus Querying](https://prometheus.io/docs/prometheus/latest/querying/basics/): `rate`, `increase`, and aggregations in PromQL.
- [Prometheus Alerting Practices](https://prometheus.io/docs/practices/alerting/): user-centric alert design and noise reduction.
- [Alertmanager](https://prometheus.io/docs/alerting/latest/alertmanager/): routing, grouping, inhibition, and silencing.
- [Google SRE Workbook](https://sre.google/workbook/alerting-on-slos/): SLO-based alerting and error budget burn rates.
- [gRPC Status Codes](https://grpc.io/docs/guides/status-codes/): status semantics in gRPC.
- [Spring gRPC Reference](https://docs.spring.io/spring-grpc/reference/): gRPC client/server integration in Spring.
