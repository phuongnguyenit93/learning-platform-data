# Setting SLIs, SLOs, and User-Impact-Based Alerts

## Context: Monitoring to Know Whether the Service Is Actually Serving Well

A virtual machine can be `RUNNING` with CPU below threshold and memory still available, yet users still hit timeouts when opening the application. Conversely, CPU may surge during a heavy load burst while the system keeps responding quickly with zero errors. Alerting solely on machine state or resource thresholds causes operations teams to miss user-impacting incidents or suffer too many alerts that require no action.

To focus on service quality, define **SLIs (Service Level Indicators)**, **SLOs (Service Level Objectives)**, and alerts tied to real impact:

- **SLI** is a metric measuring an aspect of the service that users care about, such as the proportion of successful requests or requests completing within 300 ms.
- **SLO** is the quantitative target for an SLI over a time window, such as 99.9% of valid requests succeeding over a 30-day window.
- **Alert** is a signal requiring human or automated response when errors, error budget consumption, or risk of user impact crosses a threshold.

In the **CLOUD_CORE_SERVICES_COMPUTE** module, SLIs/SLOs connect CPU, RAM, network, storage, VMs, containers, and serverless to the outcomes the application delivers. The goal is to know whether the service is performing well or poorly from the user's perspective, prioritize the right problems, and balance reliability with release velocity.

## 1. How Do SLIs, SLOs, and SLAs Differ?

| Concept | Meaning | Example |
|---|---|---|
| SLI | Actual measured indicator | 99.94% of API requests succeeded over 30 days |
| SLO | Internal or service-level target for an SLI | At least 99.9% of API requests succeed over 30 days |
| SLA | Formal commitment to customers, typically with terms and remedies on breach | If availability drops below commitment, customers may qualify for service credits |

SLIs answer "how is the service performing?". SLOs answer "what level of quality is the target?". SLAs answer "what does the organization commit to customers, and what are the contractual consequences?". SLOs can be stricter than SLAs so the organization retains a safety margin before breaching commitments.

Not every metric should be called an SLI. CPU utilization, thread counts, or pod counts are useful operational metrics, yet they only become direct SLIs if they represent an outcome users care about. For example, the proportion of requests completing on time is an SLI; high CPU is a diagnostic signal or leading indicator of risk to that SLI.

## 2. Selecting SLIs from User Journeys

Start by identifying what the service provides and how users perceive failure. For an API, users care whether requests succeed and respond fast enough. For an order processing system, they also care whether orders are processed accurately and status updates promptly. For a storage service, they care whether data remains readable, accurate, and available when needed.

Common SLI categories:

| SLI category | User question | Example measurement |
|---|---|---|
| Availability / success | Do requests complete successfully? | Good requests / valid requests |
| Latency | Are responses fast enough? | Proportion of requests under 300 ms; p95/p99 for diagnosis |
| Throughput / capacity | Can the service handle the required volume of work? | Requests or jobs completed per second/minute |
| Correctness | Are the results accurate? | Proportion of transactions verified accurate or free of business errors |
| Freshness | Is data updated recently enough? | Data age or delay from generation until availability |
| Durability / recoverability | Is data retained and recoverable when needed? | Restore test success rate, RPO/RTO targets met |

Not every service needs an SLI in every category. Choose a small set of indicators representing critical journeys that can be measured reliably and have clear owners.

### 2.1. Start from critical journeys

Example with an ordering service:

1. User submits an order creation request.
2. API authenticates and validates the payload.
3. System writes the order to the database.
4. Event is enqueued.
5. Worker processes payment or fulfillment.
6. User sees the updated order status.

An API returning HTTP 200 does not guarantee the entire journey finished. If events stall in the queue or workers stop processing, users still see orders stuck in pending too long. Therefore, the service may need an SLI for API success/latency and a freshness or processing-delay SLI for order status.

### 2.2. Choosing measurement boundaries

Measure at the boundary closest to users, such as the API gateway or service ingress. Per-VM/pod internal metrics aid diagnosis, yet do not always capture failures from DNS, load balancers, TLS, networking, or dependencies.

If a service exposes many endpoints, group by journey or criticality. Do not let rarely used endpoints mask failures in core functions, and do not let one minor endpoint distort overall indicators if user impact differs.

## 3. Defining Clear, Verifiable SLIs

An SLI should specify precisely:

- **Population:** which requests, transactions, jobs, or users are included in the sample?
- **Good event:** what criteria count as success?
- **Bad event:** what criteria count as failure?
- **Measurement point:** measured at client, gateway, service, or backend?
- **Window:** over what time interval is it aggregated?
- **Exclusions:** which cases are excluded from the sample and why?

Example availability SLI definition for an API:

```text
valid_requests = valid requests reaching production endpoints
good_requests  = requests returning a successful response per the API contract
                 within the defined timeout limit

availability SLI = good_requests / valid_requests
```

5xx errors, timeouts, and internal errors are normally bad events. Certain 4xx responses caused by invalid user input may be excluded from a platform availability SLI, provided that exclusion is explicitly defined. If 429s caused by system load shedding prevent users from completing valid actions, they may be bad events. Never exclude an error class simply to make the numbers look prettier while users remain impacted.

### 3.1. Latency SLIs

A latency SLI should measure the proportion of valid requests completing under a chosen threshold:

```text
latency SLI = requests_completed_within_threshold / valid_requests
```

For example: at least 99% of valid requests complete within 300 ms. This is a ratio-based objective, distinct from looking only at p99. Percentiles such as p95/p99 are invaluable for analyzing distributions and tail latency, yet you should not average per-instance p99 values to compute a service-wide SLI. Aggregate histograms or request-level data across the entire population properly.

### 3.2. SLIs for jobs, queues, and data

For asynchronous processing, a job accepted into a queue does not mean it has completed. You can measure:

- Proportion of valid jobs completing successfully.
- Proportion of jobs completing within the business deadline.
- Age of the oldest message in the queue.
- Latency from event emission until the result is usable by the user.

For data pipelines, freshness can measure elapsed time from source timestamp until the record or partition becomes available. Account for late events, out-of-order arrivals, and retried jobs to avoid skewed measurements.

### 3.3. Avoiding easily gamed SLI definitions

Common pitfalls:

- Measuring only requests that reached the backend, ignoring requests rejected at the gateway or load balancer.
- Measuring only internal health checks instead of real user journeys.
- Excluding timeouts or 429s from the sample even though they block users from finishing work.
- Counting a retry as a successful request while ignoring long user wait times or repeated attempts.
- Measuring average latency instead of distributions and threshold-exceedance ratios.
- Choosing a denominator that shrinks during failures, causing failed requests to vanish from the sample when the system breaks.

SLI definitions and versions should be documented so teams share a common understanding and can audit them.

## 4. Setting Meaningful SLOs

An SLO needs a target, population, time window, and measurement source. Example:

> Over every rolling 30-day window, at least 99.9% of valid requests to the production API must complete successfully.

Another SLO can target latency:

> Over every rolling 30-day window, at least 99% of valid requests must complete within 300 ms.

SLOs should reflect user needs and real operational capabilities. A 99.999% target is meaningless if the system lacks the corresponding architecture, telemetry, and recovery processes. An overly loose SLO provides no incentive to improve; an overly tight SLO can burn huge costs without delivering commensurate value.

### 4.1. Choosing time windows

Common windows:

- **Rolling window:** e.g., trailing 30 days; reflects continuous quality and updates on every evaluation.
- **Calendar window:** e.g., calendar month; convenient for reporting, though incidents straddling month boundaries get split.
- **Short window:** a few minutes or an hour; useful for fast alerting, less suitable as a standalone long-term commitment.

SLOs and alerts can use different windows. A 30-day SLO evaluates the target; alerts use 5-minute, 1-hour, or 6-hour windows to detect error budget burn rate.

### 4.2. Choosing target levels based on need

To pick an SLO, examine:

1. How much disruption or delay users can tolerate.
2. Contractual commitments or SLAs if present.
3. Current architecture, failure domains, dependencies, and recovery capabilities.
4. Historical SLIs and hourly/daily/seasonal variations.
5. Cost required to achieve the next tier of reliability.
6. Operations team capacity for measurement and incident response.

Start from actual historical data, then align on SLOs across product owners, engineering, and operations. Whenever an SLO changes, document the rationale, effective date, and impact on error budgets.

### 4.3. Multi-tier service SLOs

A product may have an overall SLO alongside dedicated SLIs/SLOs for key components. For example, a web application might set an SLO for completed user actions; the API gateway, database, and queue track internal metrics to aid root cause analysis. Do not mechanically multiply component SLOs to infer the overall SLO when dependencies are non-independent or employ retries/fallbacks.

For multi-endpoint services, define separate SLOs for critical flows such as login, checkout, or search. Weighting should reflect traffic volume or business criticality, not merely endpoint counts.

## 5. Error Budget: Allowable Failure Within the SLO

The error budget is the maximum proportion of failed SLIs permitted by the SLO within the measurement window. For a success-rate SLO:

```text
error_budget_fraction = 1 - SLO_target
allowed_bad_events = valid_events x error_budget_fraction
```

For example, a 99.9% availability SLO has a 0.1% error budget. With 1,000,000 valid requests in the window, at most 1,000 requests may be bad events while still meeting the objective.

### 5.1. Calculating equivalent downtime

If an SLO is defined over continuous availability time, a 99.9% target over a 30-day window allows:

\[
30\times24\times60\times(1-0.999)=43.2\text{ minutes}
\]

This is a time-based SLO conversion. For request-based SLOs, minutes of downtime do not translate directly to error budget because traffic varies by time of day. One minute of failure during peak traffic consumes far more budget than one minute during quiet hours.

### 5.2. Using error budgets for decision-making

Error budgets help teams decide when to prioritize reliability:

- Plenty of budget remaining: continue normal releases and monitor.
- Budget burning rapidly: lower rollout risk, expand testing, or defer non-urgent changes.
- Budget nearly or fully exhausted: prioritize root cause fixes, curtail high-risk changes, and improve resilience.

An error budget is not a quota meant to be "spent down." It is an accepted risk ceiling, not an error allowance to consume. Likewise, do not automatically freeze all releases solely because budget is low when an urgent security patch or critical fix is needed; maintain policies that balance security risk and reliability.

### 5.3. Example budget tracking table

| SLI/SLO | Target | Error budget | Measurement |
|---|---:|---:|---|
| API availability | 99.9% | 0.1% of requests | Good requests / valid requests |
| API latency | 99% under 300 ms | 1% of requests exceeding threshold | Requests under 300 ms / valid requests |
| Job completion | 99.5% within 5 minutes | 0.5% late or failed jobs | On-time jobs / eligible jobs |

These examples are illustrative targets. Real SLOs must be selected based on user behavior, criticality, and service baseline data.

## 6. Alerting on Error Budget Burn Rate

Alerts based solely on "CPU above 90%" or "memory above 85%" often generate signals disconnected from actual incidents. **Error budget burn rate** alerts focus on how quickly the service is consuming its error budget.

Burn rate is the ratio between the observed error rate and the error rate permitted by the SLO:

```text
allowed_error_rate = 1 - SLO_target
observed_error_rate = bad_events / valid_events
burn_rate = observed_error_rate / allowed_error_rate
```

If the SLO is 99.9%, the allowed error rate is 0.1%. If 1% of requests fail during an observation window, the burn rate is 10x the allowable pace. If sustained, the budget will exhaust far ahead of schedule.

### 6.1. Why multiple windows?

A very short window reacts quickly yet is easily triggered by a brief spike. A long window is steadier yet may detect outages too late. Combining short and long windows lets alerts react promptly to genuine outages while filtering random isolated errors.

For instance, an alert can require elevated burn rate simultaneously over 5 minutes and 1 hour. Another rule can watch moderate burn rate over 30 minutes and 6 hours. Tune exact thresholds to your SLO, traffic volume, and team response time.

### 6.2. Burn rate examples

Assuming a 99.9% availability SLO (error budget fraction = 0.001):

| Observed error rate | Burn rate | Interpretation |
|---:|---:|---|
| 0.1% | 1x | Matches exact maximum sustainable consumption pace |
| 0.2% | 2x | Consuming budget twice as fast as sustainable |
| 1% | 10x | Budget draining very rapidly |
| 5% | 50x | Major incident, likely requiring immediate emergency response |

Burn rate must use the exact same population and bad-event definitions as the SLI. If alert metrics use a different denominator than the SLO, results will be misleading.

### 6.3. Multi-window, multi-burn-rate pattern

For a 99.9% SLO over a 30-day window (720 hours), illustrative starting thresholds can be tested:

| Severity | Burn rate | Long and short windows | Approximate meaning |
|---|---:|---|---|
| Critical/page | 14.4x | 1 hour and 5 minutes | Consumes roughly 2% of error budget in 1 hour |
| Warning/ticket | 6x | 6 hours and 30 minutes | Consumes roughly 5% of error budget in 6 hours |

Requiring both long and short windows to exceed the threshold prevents alerts from firing on brief spikes. These numbers are common starting points for a 30-day SLO, not mandatory rules. Adjust them for traffic volume, severity, response time, and signal-to-noise accuracy.

### 6.4. Prometheus alert rule example

Suppose the application exports counter `http_requests_total` with labels `service`, `environment`, and `outcome`, where `outcome` is `good` or `bad` matching the SLI definition. You can define a recording rule for the error ratio and apply multiple windows:

```yaml
groups:
  - name: orders-api-slo
    rules:
      - record: service:sli_error_ratio:rate5m
        expr: |
          sum(rate(http_requests_total{
            service="orders-api",
            environment="prod",
            outcome="bad"
          }[5m]))
          /
          clamp_min(sum(rate(http_requests_total{
            service="orders-api",
            environment="prod",
            outcome=~"good|bad"
          }[5m])), 1e-9)

      - alert: OrdersApiHighErrorBudgetBurn
        expr: |
          (
            sum(rate(http_requests_total{
              service="orders-api",
              environment="prod",
              outcome="bad"
            }[5m]))
            /
            clamp_min(sum(rate(http_requests_total{
              service="orders-api",
              environment="prod",
              outcome=~"good|bad"
            }[5m])), 1e-9)
          ) > 0.0144
          and
          (
            sum(rate(http_requests_total{
              service="orders-api",
              environment="prod",
              outcome="bad"
            }[1h]))
            /
            clamp_min(sum(rate(http_requests_total{
              service="orders-api",
              environment="prod",
              outcome=~"good|bad"
            }[1h])), 1e-9)
          ) > 0.0144
        for: 2m
        labels:
          severity: page
        annotations:
          summary: "Orders API is burning its availability error budget quickly"
          description: "Investigate user-visible failures, dependencies and recent changes."
```

This example assumes metrics are properly instrumented and `outcome` reflects the same SLI used in the SLO. In production, use dedicated recording rules per window, add a minimum request count guard to prevent triggering on tiny samples, and validate syntax against your running Prometheus version. `clamp_min` here only prevents division by zero; it does not replace a low-traffic handling policy.

## 7. Alerts Must Lead to Action

A good alert tells the responder what is affected, how urgent it is, and what to check first. Never page solely because a metric crossed a threshold if there is no sign of service impact or imminent risk.

### 7.1. Distinguishing symptom alerts from cause alerts

- **Symptom alert:** users are hitting errors, latency is rising, jobs are delayed, or SLO burn is high. These are usually the right signals to page on.
- **Cause/resource alert:** CPU, RAM, disk, connection pools, or network are nearing limits. Useful for early detection, yet should only page when risk is clear or impact is already occurring.
- **Diagnostic signal:** logs, traces, and granular metrics used to find the root cause after an alert fires.

For example, 95% CPU for one minute may not warrant paging if latency and error rates remain normal. However, if sustained CPU throttling drives down the ratio of requests under 300 ms and accelerates burn rate, page on the SLO and use CPU metrics to diagnose.

### 7.2. Classifying response levels

| Level | When to use | Response channel |
|---|---|---|
| Page / Critical | Major active impact, rapid SLO budget burn, immediate human response required | Direct on-call, incident channel |
| Warning | Degrading trend or noticeable budget consumption, not yet urgent enough to wake someone | Tickets, team ops chat, or daytime shift |
| Info | State changes, forecasts, or capacity planning updates | Dashboards, logs, or reports |

Every alert needs an owner, severity, service/environment, dashboard link, runbook, and clear resolution criteria. Alerts lacking clear ownership or concrete actions just create noise.

### 7.3. Tying alerts to users and blast radius

An alert should state:

- Affected service and user journey.
- Current error rate or latency compared to the SLO.
- Number of affected requests/users/tenants if measurable.
- Affected region, endpoint, version, or workload group.
- Incident start time and rate of escalation.
- Related recent changes, dependencies, or deployments if identified.

Do not speculate about root causes in alert titles. Describe the symptom and link supporting data for the responder to verify.

## 8. Connecting SLIs to Compute and Infrastructure Metrics

Infrastructure metrics do not replace SLIs, yet they explain why an SLI degrades. Monitor across the layers of the compute stack:

| Layer | Useful metrics | How it can impact SLIs |
|---|---|---|
| VM/host CPU | CPU utilization, steal time, load, throttling, run queue | Increases processing time, causes timeouts, or lowers throughput |
| VM/host memory | Working set, swap, page faults, OOMs, memory pressure | GC pauses, reclaim overhead, OOM kills, or process restarts |
| Storage | IOPS, throughput, queue depth, latency, volume fullness | Slow database queries, write failures, or delayed jobs |
| Network | Packet loss, retransmissions, RTT, connection errors, bandwidth | Request timeouts, dependency failures, or reduced throughput |
| Container/orchestrator | Pod pending, restarts, throttling, node pressure, readiness | Missing replicas, slow rollouts, or misrouted requests |
| Serverless | Cold starts, concurrency, throttling, duration, invocation errors | Elevated latency or dropped/unprocessed requests |
| Dependencies | Database pools, queue age, cache hit ratio, downstream errors | User journeys fail to complete even while compute stays healthy |

Label metrics by service, environment, region/zone, workload, and version to scope analysis properly. Avoid exploding cardinality by putting user IDs, request IDs, or personal data into metric labels; granular attributes belong in logs or traces.

### 8.1. Ordering dashboards from user experience to root cause

A useful operational dashboard can be structured as:

1. Current SLI/SLO status and remaining error budget.
2. Error rate, latency distribution, and throughput by endpoint/journey.
3. Blast radius by region, zone, tenant, or version.
4. Dependency metrics such as databases, queues, caches, and external APIs.
5. CPU, memory, storage, network, and VM/container/serverless health.
6. Deployments, config changes, and incident annotations on the timeline.

This layout lets responders see impact first and then drill down into likely causal components.

## 9. Using Metrics, Logs, and Traces to Investigate

The three telemetry signals reinforce each other:

- **Metrics:** time-series data suited for spotting trends, computing SLIs, and triggering alerts.
- **Logs:** detailed timestamped events with context, suited for finding specific errors, requests, or changes.
- **Traces:** path of a request across services, suited for locating which component adds latency or fails.

When an SLO alert fires, use metrics to bound scope and start time; logs to inspect error events; and traces to follow requests through the API, database, queue, and dependencies. Use correlation IDs or trace IDs to link data without turning unique IDs into high-cardinality metric labels.

### 9.1. Example investigation of rising latency

Suppose an API's latency SLI drops from 99.2% to 94% of requests under 300 ms. The dashboard reveals only the order creation endpoint in one region is affected. Traces show most of the duration sits in database writes. Database metrics show rising write latency and queue depth; simultaneously, the storage volume's IOPS approach its limit.

This chain of evidence points the team to the data write path and storage rather than scaling CPU across the entire API fleet. Remediation might involve reducing write load, tuning database/storage configuration, scaling storage capacity appropriately, or rolling back a recent change. Afterward, verify SLI recovery and declining burn rate.

### 9.2. Synthetic monitoring and low traffic

A low-traffic service may lack enough samples to compute request-based SLIs over short windows. Synthetic monitoring periodically sends test transactions from an external vantage point—such as test logins, API calls, or loading a key page.

Synthetic checks help catch outages during low traffic and validate the full path from DNS, TLS, and gateway to the application. However, synthetic traffic does not fully represent real user behavior; separate synthetic results from real request SLIs and prevent test accounts or test data from polluting business state.

During low traffic, you can:

- Use longer measurement windows to gather more samples.
- Pair synthetic checks with real-traffic SLIs.
- Enforce a minimum sample count before computing burn rates.
- Alert separately on missing telemetry or insufficient samples.
- Never interpret "zero failed requests" as 100% availability when the service received zero traffic.

## 10. Example SLI/SLO Designs for Compute Models

### 10.1. API service on VMs or containers

| Component | Example definition |
|---|---|
| Availability SLI | Valid requests returning success within timeout / total valid requests |
| Availability SLO | 99.9% over a rolling 30-day window |
| Latency SLI | Requests completing within 300 ms / total valid requests |
| Latency SLO | 99% over a rolling 30-day window |
| Alert | Multi-window availability or latency burn rate exceeding threshold; page when impact is significant |
| Diagnostic metrics | CPU throttling, memory pressure, pod restarts, VM networking, database latency |

For containers, a `Ready` pod is a component signal, not the final SLI. For VMs, a `running` instance likewise does not prove the API works. SLIs should measure requests through real endpoints.

### 10.2. Queue worker

| Component | Example definition |
|---|---|
| Success SLI | Jobs completed successfully / valid jobs received |
| Timeliness SLI | Jobs completed within 5 minutes / valid jobs |
| SLO | 99.5% of jobs complete within 5 minutes over 30 days |
| Alert | Late-job ratio rising or oldest message age crossing threshold; page when backlog threatens business commitments |
| Diagnostic metrics | Queue depth, oldest message age, worker concurrency, retries, dead-letter count, CPU/RAM |

Rising queue depth alone is not necessarily an incident if workers still keep up faster than arrival rates. Message age and on-time completion ratio reflect user impact much better.

### 10.3. Serverless function

| Component | Example definition |
|---|---|
| Success SLI | Invocations completing per contract / valid invocations |
| Latency SLI | Invocations completing within threshold / valid invocations |
| Alert | Error rate, throttling, or duration causing fast SLO burn |
| Diagnostic metrics | Cold starts, concurrency, timeouts, memory, retries, and downstream latency |

Invocations may be retried automatically. Distinguish retry attempts from unique logical units of work; otherwise, retries can inflate counted successes while users suffer latency or duplicate processing.

### 10.4. Internal VM or compute platform

If an organization provides a compute platform to internal teams, the platform's users are application teams. SLIs can measure VM provisioning requests succeeding on time, p95 provisioning duration, node/container readiness ratio, or volume attachment success rate.

Example SLOs:

- 99% of valid VM creation requests provision within 5 minutes over 30 days.
- 99.9% of valid volume attachment requests complete within the defined deadline.
- 99% of node pool scale-outs produce a Ready node within 8 minutes.

These are compute platform SLOs, distinct from SLOs of applications running on those VMs. An application can remain healthy even when a new VM request is slow; conversely, the platform may provision a VM on time while the application still fails due to misconfiguration or dependencies.

## 11. Response Workflow When an SLO Alert Fires

An alert should trigger a clear procedure rather than merely sending a notification. A runbook can follow this sequence:

1. **Confirm impact:** check SLIs, error budget burn, endpoint, region, tenant, and start time.
2. **Determine scope:** check whether the issue affects the whole service or a slice of traffic, a version, or one fault domain.
3. **Inspect recent changes:** deployments, images, configs, scaling policies, network rules, or database migrations.
4. **Check dependencies:** use traces and metrics to inspect databases, queues, caches, storage, and external APIs.
5. **Check compute:** CPU, memory, throttling, OOMs, pending/restarting pods, VM health, disk I/O, and networking.
6. **Pick mitigation action:** roll back, scale out, fail over, disable a feature, shed load, or shift traffic per runbook.
7. **Verify recovery:** SLIs improve, burn rate drops, backlogs drain, and health checks stabilize.
8. **Conduct postmortem:** document timeline, root cause, impact, time to detect/recover, and preventive actions.

Never scale out mechanically if the bottleneck is a database or quota; adding workers can overload the dependency further. Actions must be grounded in evidence and knowledge of system-wide limits.

### 11.1. Minimum runbook contents

- Alert name, related SLI/SLO, and trigger conditions.
- Severity, owner, and on-call rotation.
- Dashboards showing SLI metrics, burn rate, and dependencies.
- Log/trace queries or links to investigative tools.
- Initial verification steps and safe first actions.
- Rollback/failover/scaling criteria and limits to watch.
- Notification channels, escalation paths, and incident update procedures.
- Alert closure criteria and recovery verification steps.

## 12. Common Misconceptions

**Low CPU means the service is healthy.** A service can fail due to databases, DNS, networking, storage, or dependencies while CPU remains idle.

**High CPU always requires a page.** High CPU can be normal under heavy load. Page only when it causes or is about to cause user impact, or poses an imminent capacity exhaustion risk.

**A 99.9% SLO always equals 43.2 minutes of downtime.** That figure is only the time-based conversion over a 30-day window. Request-based SLOs depend on traffic distribution.

**Per-instance p99 can be averaged to yield service-wide p99.** Percentiles do not aggregate linearly. Aggregate histograms or underlying request data properly.

**Zero failed requests means 100% SLI.** When samples are missing or telemetry drops, SLIs can be undefined. Distinguish zero traffic, no data, and success.

**All 4xx errors must be excluded from availability.** Some 4xx codes represent client input errors, yet 429s or policy/service errors blocking valid user actions can be bad events. Define strictly by contract and impact.

**The higher the SLO, the better.** Overly ambitious targets inflate costs and slow down releases without matching business value. Choose targets grounded in user need and practical capability.

**More alerts mean safer systems.** Noisy alerts train responders to ignore critical signals. Page only when immediate action is needed; keep diagnostic signals on dashboards or tickets.

## 13. SLI/SLO and Alerting Checklist

### SLI/SLO definition

- [ ] Identified user journeys and critical functions.
- [ ] Each SLI specifies population, good/bad events, measurement point, window, and exclusions.
- [ ] Availability, latency, freshness, or job completion selected to fit the service type.
- [ ] SLO targets and windows align with user needs.
- [ ] SLIs measure near the user boundary without missing gateway/dependency failures.
- [ ] Low traffic, missing telemetry, and synthetic monitoring are accounted for.

### Error budgets and alerting

- [ ] Error budgets are calculated from the exact same SLI definition as the SLO.
- [ ] Dashboards track remaining budget and burn rate.
- [ ] Alerts use multi-window rules or appropriate noise-filtering mechanisms.
- [ ] Pages tie directly to user impact or imminent severe risk.
- [ ] Every alert has an owner, severity, dashboard, and runbook.
- [ ] Alert routing and escalation paths have been tested.

### Operations and continuous improvement

- [ ] Metrics, logs, and traces correlate via service/resource/trace context.
- [ ] Dashboards present user experience first, followed by resources and dependencies.
- [ ] Runbooks cover verification, mitigation, recovery, and postmortem steps.
- [ ] Error budgets guide release decisions and reliability prioritization.
- [ ] SLIs/SLOs are reviewed whenever products, traffic, or user journeys change.

## Conclusion

SLIs measure service quality from the user's perspective; SLOs set quantitative targets for SLIs over a window; error budgets represent allowable failure. Alerts should focus on user impact and budget burn rate, combining multiple windows to catch incidents while minimizing noise. Compute metrics such as CPU, RAM, storage, and networking remain essential, primarily to explain root causes after an SLI signals trouble. With clear population and good/bad event definitions, user-journey dashboards, and actionable runbooks tied to alerts, operations teams prioritize the right incidents and improve reliability on solid evidence.
