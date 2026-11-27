# Writing an Incident Runbook with Recovery Verification Criteria

A runbook for Spring Cloud Circuit Breaker should guide on-call engineers from customer impact down to the failing dependency, and then restore traffic through verifiable steps. The `OPEN` state is a protection mechanism, not standalone proof that the entire API is broken. An incident is considered recovered only when service quality, the dependency, resources, and fallback behavior have all returned within agreed limits.

This lesson uses Resilience4j as the Spring Cloud CircuitBreaker implementation example. The workflow also applies to applications using other implementations, though metric names, state-transition methods, and inspection tools must be adapted to the active provider and Release Train.

## 1. Runbook Objectives and Scope

A runbook must help on-call engineers answer five questions:

1. Which APIs, routes, regions, or request groups are affecting customers?
2. Which dependency is slow, failing, overloaded, or unreachable?
3. How are the Circuit Breaker, TimeLimiter, Bulkhead, and fallback reacting?
4. Which actions reduce impact without putting additional load on the dependency?
5. Which measurable criteria prove traffic can be restored and the incident closed?

Before an incident occurs, the service team should populate the following details in their live deployment runbook:

| Information | Example | Values to Verify in Your Project |
| --- | --- | --- |
| Service and owned APIs | `order-service`, `GET /orders/{id}` | Service name, owner, critical routes |
| Protected dependencies | `inventory`, `payment`, `profile` | Breaker IDs and target endpoints |
| On-call and incident channels | Backend on-call, incident channel | Rotation schedule, escalation, dependency owner |
| Service SLOs | Availability 99.9%, p95 under 800 ms | Approved SLOs |
| Timeout limits | Client timeout 1.5 s; TimeLimiter 1.8 s | Actual deadlines per dependency |
| Fallback policy | Cache up to 60 seconds for inventory | Allowed data staleness and business rules |
| Observability sources | Actuator, Prometheus, Grafana, tracing | Internal URLs, dashboards, access permissions |

Do not use illustrative values from this article as production configuration without comparing against your system's SLAs, traffic, capacity, and data contracts.

## 2. Preparing Before an Incident

A runbook is only useful if on-call responders can find the right details without reading source code while an incident is unfolding. Prepare in advance:

- A list of breaker IDs, dependencies, owners, timeouts, failure thresholds, slow-call thresholds, `waitDurationInOpenState`, and permitted calls in `HALF_OPEN`.
- Dashboards showing request rate, error rate, p95/p99 latency, SLO/error budget, fallbacks, breaker state, timeouts, Bulkhead, and connection pools.
- Links to dependency dashboards, health checks, tracing, logs, and the dependency-owning team's escalation path.
- Fallback rules: which data may be stale, maximum staleness age, when `unavailable` must be returned, and when fallbacks are disallowed.
- Tested load-shedding actions: concurrency caps, disabling non-essential features, reducing traffic, controlled caching, or shedding load.
- Configuration deployment/rollback steps and who is authorized to approve production changes.
- Recovery verification criteria and the post-recovery stability observation window.

Example Resilience4j configuration to record alongside the breaker ID:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallRateThreshold: 70
        slowCallDurationThreshold: 800ms
        waitDurationInOpenState: 20s
        permittedNumberOfCallsInHalfOpenState: 3

  timelimiter:
    instances:
      inventory:
        timeoutDuration: 1500ms
```

This is only an example so the runbook has concrete data. In production, record the actual deployed values, configuration sources (profiles, environment, config server, or properties), and application version. Never assume a YAML file in the repository always reflects runtime configuration.

## 3. When to Declare an Incident?

Prioritize customer impact and SLOs. A breaker transitioning to `OPEN` may signal dependency trouble, yet a fallback may still serve requests within contract. Conversely, an API can violate its SLO even while the breaker stays `CLOSED`.

| Signal | Suggested Classification | Initial Action |
| --- | --- | --- |
| API 5xx or timeout rate persistently exceeds SLO with sufficient traffic | Customer-facing incident | Declare incident, identify affected routes and regions |
| p95/p99 exceeds SLO, rapid error budget burn | Performance incident | Inspect dependency latency, queues, and pools |
| Critical breaker remains `OPEN`, fallbacks surge | Warning to investigate; escalate if SLI degrades | Inspect dependency and fallback quality |
| Bulkhead rejections rise, queues/thread pools saturate | Overload or resource contention | Reduce concurrency/traffic and inspect stuck tasks |
| Brief single `OPEN`, API still meets SLO, valid fallback | Protection event | Monitor; do not page solely on state |

Alert rules need appropriate time windows and minimum traffic thresholds. A single failed request should not page if the SLO is not threatened. A breaker `OPEN` alert can stay at warning severity when no service impact is present.

## 4. Incident Response Procedure

### Step 1 — Confirm Impact and Scope

Within the first few minutes, the on-call engineer should capture:

- Start time and triggering alerts.
- Affected APIs/routes, regions, tenants, or customer segments.
- Current request rate, error rate, timeouts, p95/p99, and SLO/error budget.
- Application version, pods/instances, and recent configuration or deployment changes.
- Proportion of requests hitting fallback and whether fallback data remains valid.

Inspect dashboards at the API level first, then break down by instance and dependency. Never infer a system-wide outage from a single breaker on a single pod.

### Step 2 — Identify the Dependency and Triggered Safeguard

Correlate breaker IDs with metrics and traces:

- `CLOSED` with rising failure/slow-call rate: the dependency may be degrading while the breaker has not crossed thresholds or gathered enough samples.
- `OPEN` with rising `not permitted`: the breaker is blocking calls; check when it opened, preceding errors/slow calls, and the corresponding dependency.
- `HALF_OPEN` repeatedly returning to `OPEN`: probe calls are still failing or slow; the dependency is unstable or taking too much load.
- TimeLimiter timeouts rising while client requests stay hung: check cancellation, HTTP client timeouts, and occupied worker threads.
- Rising Bulkhead rejections/queues: inspect worker counts, queue capacity, blocking work, and processing times.
- Fallbacks rising while the API still returns 2xx: verify cache freshness and response semantics; a success status code does not prove data correctness.

Trace several representative requests to confirm whether time is spent in DNS/connect, connection pools, responses, internal processing, or fallbacks. Inspect 4xx errors separately so caller business errors are not mistaken for dependency health issues.

### Step 3 — Protect the System and Limit Blast Radius

Choose actions based on root cause and approved runbooks:

- Reduce or temporarily pause non-essential traffic to the overloaded dependency.
- Constrain caller concurrency or Bulkheads to prevent unbounded queuing.
- Reduce or temporarily disable retries for errors that amplify load; keep total retry time within the request deadline.
- Use caches/snapshots only while data remains within max staleness and business rules allow.
- Reject non-essential requests early when out of capacity rather than holding threads/connections indefinitely.
- Escalate to the dependency owner with timestamps, trace/request IDs from logs, error rates, latency, and request volumes.

Do not bypass the Circuit Breaker or force `CLOSED` just to restore request rates. Do not raise `permittedNumberOfCallsInHalfOpenState` while the dependency is still overloaded. Do not enlarge queue capacities to mask a slow dependency.

### Step 4 — Recover the Dependency Before Increasing Traffic

The dependency-owning team must confirm the root cause is resolved: instances are healthy, connection/database pools are not exhausted, infrastructure errors have subsided, latency is back within bounds, and backlogs are no longer growing.

Verify via health endpoints or lightweight approved synthetic requests. Health checks should represent real serving capability without creating a heavy load spike. If the dependency relies on downstream databases or other systems, verify those components before declaring recovery.

Never treat a single HTTP 200 response as proof of recovery. Observe success rates, latency, saturation, and errors over a window long enough relative to the dependency's traffic and load cycle.

### Step 5 — Let the Circuit Breaker Probe Recovery

Once `waitDurationInOpenState` expires, Resilience4j can transition to `HALF_OPEN` to permit a bounded number of probe requests. If `automaticTransitionFromOpenToHalfOpenEnabled` is disabled, the transition is triggered by the next arriving call after the wait duration expires; do not mistake an `OPEN` state shown during zero traffic for proof that the dependency is still failing.

During this stage:

- Monitor permitted probe counts and success/failure outcomes.
- Keep non-essential traffic low so probes do not compete with heavy load.
- Observe breakers per instance; do not look solely at an aggregate metric.
- If the breaker returns to `OPEN`, continue protecting the dependency, investigate remaining causes, and wait for the next recovery cycle.
- If probes succeed and the breaker returns to `CLOSED`, keep monitoring before restoring full traffic.

Do not send continuous synthetic probes via scripts or high-frequency health checkers. Respect `permittedNumberOfCallsInHalfOpenState` and configured safeguards.

### Step 6 — Ramp Traffic in a Controlled Manner

Restore gradually: reopen a portion of traffic or a subset of instances first, observe, and then step up further. After each step, compare:

- API request success/error ratio and p95/p99.
- Dependency success/error ratio and response latency.
- Circuit Breaker state, failure rate, slow-call rate, and not-permitted calls.
- TimeLimiter timeouts, Bulkhead rejections, queues, and connection pools.
- Fallback rate, fallback failures, and cache data age.

If any recovery condition is violated, stop increasing traffic and return to load-shedding measures. Do not roll out a new configuration across all instances simultaneously before verifying stability on a canary.

## 5. Recovery Verification Criteria

An incident may be marked recovered only when all predefined gates are satisfied. The table below is a template adaptable to your service's SLOs and baselines:

| Gate | Sample Verification Criterion | Evidence to Retain |
| --- | --- | --- |
| Dependency availability | 5xx/connection error rate below 1% for at least 10 minutes, no new error bursts | Dependency dashboard, health/synthetic checks |
| Dependency latency | p95 within agreed timeout budget; p99 does not exceed serving deadline | HTTP client metrics, traces, and latency dashboard |
| Circuit Breaker | Relevant breakers back in `CLOSED` and stable for at least 10–15 minutes; no repeated reopening | State gauge/events by instance and breaker ID |
| Probe results | Permitted calls in `HALF_OPEN` succeeded as configured | Circuit Breaker events, logs, and actual request counts |
| Caller SLI | API success rate and latency back within SLO across the observation window | SLI/SLO dashboard and error budget |
| Timeout and Bulkhead | Timeouts, rejections, queue depth, and active workers back to safe baseline/capacity | TimeLimiter/Bulkhead metrics and executor metrics |
| Fallback quality | Fallback rate back to baseline; no stale data beyond max age; fallback errors at 0 or approved threshold | Fallback counters, cache age, and business logs |
| Backlog and resources | Queues, connection pools, CPU, memory, and thread counts stable; backlog not growing | Resource and dependency dashboards |

Numbers such as 1%, 10 minutes, and 10–15 minutes are examples only. Choose an observation window longer than the circuit open duration and wide enough to cover a representative load cycle. If traffic is low, supplement with controlled synthetic checks rather than relying on a rate computed from only a few requests.

The `CLOSED` condition must be verified per instance. Resilience4j normally maintains state in each process's local registry; aggregate metrics can hide a pod still stuck in `OPEN`. Never assume replicas share a single state unless the application explicitly built custom synchronization.

## 6. Caution During Restarts or Rollouts

Restarting an application can discard Circuit Breaker state held in process memory, and new instances usually start in a fresh state. That does not prove the dependency has recovered. If all instances restart at once, many replicas may immediately resume sending traffic to the dependency upon startup, causing a sudden load surge.

If a restart is part of an approved remediation action:

- Use a rolling restart or canary, keeping traffic limits in place while new instances boot.
- Confirm the dependency has sufficient capacity before scaling up the number of traffic-serving instances.
- Monitor breaker state, request rate, latency, and fallbacks after each batch of instances.
- Never treat a breaker starting in `CLOSED` after a restart as an independent recovery criterion.

## 7. Symptom-and-Action Matrix

| Symptom | Causes to Check | Priority Action |
| --- | --- | --- |
| `OPEN`, not-permitted rising, API SLI still healthy | Fallback is protecting successfully; dependency may still be failing | Keep traffic controlled, inspect dependency and fallback freshness |
| `OPEN`, API 5xx rising | Missing or invalid fallback; route depends directly on backend | Reduce traffic, restore dependency, review fallback contract |
| `CLOSED`, timeouts and p95 rising | Threshold not reached, insufficient samples, mismatched client/pool timeout or slow-call threshold | Investigate latency, reduce concurrency, verify breaker configuration |
| Repeated `HALF_OPEN` then `OPEN` | Dependency still unstable, failing probes, or excessive recovery load | Keep load throttled, fix dependency, do not arbitrarily raise probes |
| Bulkhead full, queue growing | Hung blocking tasks, small pool, or slow dependency | Check worker/client timeouts, shed load, bound concurrency |
| TimeLimiter timeouts rising while threads remain busy | Cancellation cannot stop I/O or client timeout is too long | Check client-layer timeouts and interrupt/cancel behavior |
| Fallback rate rising while 2xx status remains steady | API heavily serving cached or backup data | Check freshness, business correctness, and separate SLI for degraded responses |
| Only one pod has breaker `OPEN` | Pod-specific dependency path, network issue, or load skew | Analyze by instance rather than aggregates alone |

## 8. Example Queries for Investigation

The queries below illustrate how to inspect Prometheus data. Metric names and labels must be verified at `/actuator/prometheus` on the running version before placing them into a runbook.

**Breakers currently OPEN by ID:**

```promql
max by (instance, name) (resilience4j_circuitbreaker_state{state="open"})
```

**Failed Circuit Breaker calls by ID:**

```promql
sum by (instance, name) (rate(resilience4j_circuitbreaker_calls_seconds_count{kind="failed"}[5m]))
```

**Rejected calls:**

```promql
sum by (instance, name) (rate(resilience4j_circuitbreaker_not_permitted_calls_total[5m]))
```

**TimeLimiter timeouts:**

```promql
sum by (instance, name) (rate(resilience4j_timelimiter_calls_total{ kind="timeout"}[5m]))
```

**Caller HTTP 5xx rate:**

```promql
sum(rate(http_server_requests_seconds_count{job="order-service",status=~"5.."}[5m]))
/
clamp_min(sum(rate(http_server_requests_seconds_count{job="order-service"}[5m])), 0.001)
```

Do not copy queries verbatim if your registry's metric names differ. For instance, timers/counters may be normalized with `_seconds_count` or `_total` suffixes; verify actual metric names and types before use. Always preserve `instance` or `pod` labels in investigative queries to spot differences across replicas.

## 9. Recording Decisions and Handoff

In the incident channel or ticket, record using this template:

```text
Incident ID:
Service / route:
Dependency / breaker ID:
Start time / detection source:
Customer impact and affected region:
API SLI/SLO at detection:
Breaker states by instance:
Timeout / Bulkhead / fallback symptoms:
Containment actions and approver:
Dependency recovery evidence:
HALF_OPEN probe results:
Traffic restoration steps:
Recovery gates and observation window:
Incident resolved time:
Follow-up owner and due date:
```

Never put tokens, passwords, personal data, or sensitive payloads into tickets or logs. Use trace IDs or request IDs permitted by internal policy to correlate data across systems.

## 10. Post-Incident: Preventing Recurrence

Once the service stabilizes, conduct a data-driven review:

- Identify root causes and contributing factors: dependency, network, pools, timeouts, retries, configuration, or deployment changes.
- Compare `failureRateThreshold`, `slowCallRateThreshold`, `minimumNumberOfCalls`, sliding window, and `waitDurationInOpenState` against real data; never tune thresholds solely to reduce alert noise.
- Review caller, HTTP client, and gateway timeouts so nested deadlines align sensibly.
- Inspect Bulkhead capacity, queues, executors, and client cancellation support.
- Evaluate fallbacks: freshness, business correctness, fallback success rate, and cases where fallbacks also failed.
- Improve dashboards, alerts, runbooks, and synthetic checks wherever responders lacked evidence when making decisions.
- Create action items with owners, due dates, and verification methods.

Do not turn post-incident reviews into automatic configuration edits. Every adjustment to thresholds, timeouts, retries, or fallbacks must be tested under representative load with a rollback plan.

## 11. Incident Closure Checklist

- [ ] Customer impact returned within SLO over the agreed observation window.
- [ ] Dependency stabilized across error rate, latency, and capacity.
- [ ] Relevant breakers verified per instance and did not reopen during confirmation.
- [ ] `HALF_OPEN` probes succeeded; no anomalous probes or sudden traffic spikes occurred.
- [ ] Timeouts, Bulkhead rejections, queues, and connection pools returned to safe levels.
- [ ] Fallbacks dropped back to baseline; stale data did not exceed business limits.
- [ ] No lingering backlogs or blocked tasks remained after timeouts.
- [ ] Emergency changes documented with an owner and rollback plan if needed.
- [ ] Incident timeline, recovery evidence, and action items saved.

## References

- [Spring Cloud CircuitBreaker – Resilience4J](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j.html): factory, instance configuration, TimeLimiter, Bulkhead, and metrics.
- [Resilience4j – CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker): state machine, sliding window, HALF_OPEN permissions, and event publisher.
- [Resilience4j – Micrometer](https://resilience4j.readme.io/docs/micrometer): metrics for Circuit Breaker, TimeLimiter, and Bulkhead.
- [Spring Boot – Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): metrics, tags, histograms, and export.
- [Prometheus – Querying](https://prometheus.io/docs/prometheus/latest/querying/basics/): querying time series and labels in PromQL.
