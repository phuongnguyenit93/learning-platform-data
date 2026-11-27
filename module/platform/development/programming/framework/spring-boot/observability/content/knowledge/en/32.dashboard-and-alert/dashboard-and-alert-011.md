# Alerting on Health State

In the **Dashboard and Alert** chapter of the **SPRING_BOOT_OBSERVABILITY** module, alerting on health state is how you detect and notify when an application or dependency transitions into a state requiring action. Spring Boot Actuator provides health indicators and health groups such as `readiness` and `liveness`; metrics backends like Prometheus collect signals and evaluate alert rules periodically. Combining these layers properly helps operations teams detect when an instance can no longer receive traffic, a process needs inspection, or a critical dependency is failing.

A health endpoint returning `DOWN` does not automatically send a notification. There must be a path from health state to a scrape target or metric, an evaluation rule, Alertmanager, and a recipient. You must also decide which states genuinely warrant alerting: readiness `DOWN` may just be a pod rolling out; liveness `DOWN` typically leads to a restart; an optional dependency `DOWN` may only need dashboard tracking. Alerts should reflect impact and required action, avoiding alarms on every brief state transition.

## 1. Learning Objectives

After this lesson, you will be able to:
1. Explain Actuator health states and how to turn them into alertable signals.
2. Distinguish liveness, readiness, and dependency health.
3. Choose alert conditions based on user and service impact.
4. Combine Actuator health groups with a metrics backend.
5. Write Prometheus alert rules with `for`, severity, and stable labels.
6. Distinguish scrape failures from genuine application `DOWN` states.
7. Reduce alert flapping using sustained duration, grouping, and inhibition.
8. Design dashboards for current state and state transition history.
9. Test alert rules using sample data and fault injection.
10. Write runbooks attached to each alert so on-call engineers can take action.

## 2. From Health Endpoint to Notification

The Actuator health endpoint provides status at the moment it is queried. Prometheus or a monitoring system must scrape an appropriate endpoint/metric; alert rules evaluate the scraped data; Alertmanager or an equivalent service groups, deduplicates, inhibits, and routes notifications.

~~~mermaid
flowchart LR
    App["Spring Boot + Actuator"]
    Health["Health groups / health metrics"]
    Scrape["Prometheus scrape"]
    Rules["Alert rules"]
    AM["Alertmanager"]
    Notify["On-call / chat / ticket"]
    Runbook["Dashboard + runbook"]
    App --> Health --> Scrape --> Rules --> AM --> Notify
    Notify --> Runbook
~~~

| Layer | Responsibility |
| --- | --- |
| Actuator | Evaluates health indicators and returns status/groups. |
| Micrometer/Prometheus registry | Exposes scrapeable metrics. |
| Prometheus | Stores time series and evaluates alert expressions. |
| Alertmanager | Groups, deduplicates, inhibits, and routes alerts. |
| On-call/runbook | Assesses impact, diagnoses, and restores service. |

Do not assume that merely exposing `/actuator/health` automatically gives Prometheus a `health=DOWN` metric. If scraping a JSON health endpoint, Prometheus needs an exporter/integration or collector converting the response into metrics. Another option is emitting health state as a gauge/counter from the application, or using a blackbox probe to monitor HTTP endpoint availability. Verify the actual metric before writing rules.

## 3. Choosing Which Health States to Alert On

Health state carries multiple meanings. Before creating an alert, clarify whether the state represents the process, traffic-serving readiness, or a dependency.

| Health State | Meaning | Typically Appropriate Monitoring Action |
| --- | --- | --- |
| Liveness DOWN | Process is not in a state where it can continue running. | Monitor restart loops and replica count; alert when impact is sustained. |
| Readiness DOWN | Instance is not ready to receive traffic. | Monitor ready instance count and remaining capacity ratio. |
| Database DOWN | Database dependency is unhealthy per indicator. | Alert based on impact to request paths, pool, and error rate. |
| Optional service DOWN | Non-essential dependency is failing. | Dashboard or warning if degraded mode still works. |
| Health endpoint unreachable | Probe cannot fetch a health response. | Distinguish app down from network/scrape failure. |

Do not page on every individual instance readiness `DOWN` during normal rollouts if the deployment controller already handles traffic draining. An alert on service-level availability or low ready replica count usually reflects impact much better.

Liveness `DOWN` may be used by Kubernetes to restart a container. Alerts should observe restart loops, crash frequency, and capacity impact rather than merely repeating single restart events.

## 4. Designing Health Groups for Alerting

Health groups should be shaped around operational decisions:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,db
        liveness:
          include: livenessState
        external:
          include: search,partnerApi
~~~

The example above is only appropriate if the database is a mandatory dependency for serving traffic. If the application has caches/fallbacks/degraded modes, decide readiness according to the actual contract. Do not include remote dependencies in liveness merely because they are business-critical.

A separate group for external services can help dashboards display degraded dependencies without automatically pulling instances out of traffic rotation. Keep names and membership stable so rules do not change unexpectedly when beans are added/removed.

Protect health details with authorization. Monitoring probes only need minimal status; do not expose connection strings, hostnames, or exception messages to unauthorized callers.

## 5. Health State Must Be Represented as a Metric

Prometheus alert rules operate on time series. Several approaches convert health states into metrics:
- Micrometer health metrics if provided by your version and integration.
- A custom gauge with stable values, such as 1 for UP and 0 for DOWN.
- A Prometheus blackbox probe checking endpoint availability.
- A collector reading Actuator health and exporting statuses as metrics.

Do not generate dynamic metric names or label values on every state change. The metric contract should have a stable name and label set.

Illustrative custom gauge example:

~~~java
@Component
class DependencyHealthMetric {

    private final AtomicInteger healthy = new AtomicInteger(1);

    DependencyHealthMetric(MeterRegistry registry) {
        Gauge.builder("app.dependency.health", healthy, AtomicInteger::get)
                .tag("dependency", "catalog-db")
                .register(registry);
    }

    void markUp() {
        healthy.set(1);
    }

    void markDown() {
        healthy.set(0);
    }
}
~~~

This is merely an example of a numeric gauge. In production, avoid maintaining a second health state independent of `HealthIndicator` because the two states can drift out of sync. It is better to have a single source of truth with an adapter/collector translating that state into a metric. Avoid executing heavy health checks on every scrape.

## 6. Distinguishing App Health from Scrape Health

Prometheus provides the `up` metric for scrape targets. `up == 0` means Prometheus failed to scrape the target successfully; it does not prove the application returned health `DOWN`. Causes can include a stopped process, closed port, network policy/firewall/DNS error, wrong scrape path/port, misconfigured TLS/authentication, or timeout.

Conversely, a target can scrape successfully (`up == 1`) while a health group reports `DOWN`. These two signals answer different questions and should have separate alerts/runbooks.

Example scrape failure alert:

~~~yaml
groups:
  - name: spring-boot-availability
    rules:
      - alert: SpringBootScrapeFailed
        expr: up{job="spring-boot"} == 0
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Failed to scrape Spring Boot target"
          description: "Check process, network, port, TLS, and scrape configuration."
~~~

This rule alerts that the monitoring path is broken. It does not replace alerts for readiness or business availability.

## 7. Alerting on Readiness and Service Capacity

A single instance with readiness `DOWN` does not always warrant a page. Track ready replicas versus desired replicas to evaluate service-wide capacity.

Example if Kubernetes state metrics are collected:

~~~yaml
- alert: SpringBootReadyReplicasLow
  expr: |
    kube_deployment_status_replicas_available{
      namespace="production",
      deployment="order-service"
    }
    <
    kube_deployment_spec_replicas{
      namespace="production",
      deployment="order-service"
    }
  for: 5m
  labels:
    severity: page
  annotations:
    summary: "Order service lacks ready replicas"
    description: "Available replicas have been below desired replicas for 5 minutes."
~~~

Metric names and labels depend on kube-state-metrics/version/deployment. Without Kubernetes metrics, use service discovery or equivalent application metrics. Avoid hardcoding examples into your environment without verifying labels.

You can alert when the ready ratio drops below a threshold:

~~~promql
sum by (namespace, deployment) (kube_deployment_status_replicas_available)
/
sum by (namespace, deployment) (kube_deployment_spec_replicas)
< 0.8
~~~

Handle the case where desired replicas equals 0 and distinguish intentional rollouts. Capacity alerts should reflect the ability to serve traffic, not a single pod being replaced.

## 8. Alerting for Dependency Health

Dependency alerts should tie to real impact. For instance, database health `DOWN` for several minutes may require alerting, whereas if a health indicator times out because its probe query is too heavy, the alert may reflect health check overload itself.

A status metric with bounded labels can be used:

~~~promql
app_dependency_health{dependency="catalog-db"} == 0
~~~

Example rule:

~~~yaml
- alert: SpringBootCriticalDependencyDown
  expr: app_dependency_health{dependency=~"catalog-db|message-broker"} == 0
  for: 3m
  labels:
    severity: page
  annotations:
    summary: "Critical dependency is DOWN"
    description: "Check dependency health, connection pool, error rate, and related traces."
~~~

Do not attach dependency URLs, dynamic hostnames, tenant IDs, or exception messages to labels. Use logical dependency names with a small set of values. If a dependency is optional, use a warning or dashboard-only signal depending on degraded mode.

## 9. `for`, Flapping, and Alert Stability

Health states can flip rapidly during deployments, restarts, or flaky dependencies. An alert rule with `for` requires the expression to stay true for a period before transitioning to firing.

~~~yaml
- alert: SpringBootReadinessDegraded
  expr: app_readiness_status == 0
  for: 2m
  labels:
    severity: warning
  annotations:
    summary: "Instance is not ready"
~~~

Choose `for` based on scrape interval, health indicator timeout, readiness propagation/rollout duration, severity of capacity reduction, and how long the system can tolerate degraded mode.

Do not set `for` so long that critical incidents are detected late. Nor set it so short that a single missed scrape triggers a page. Use `for` to filter transient conditions; use grouping/inhibition to curb notification storms.

Alertmanager can group by `alertname`, `service`, `cluster`, or `namespace`. Inhibition can suppress granular alerts when a higher-level alert is already firing—for example, suppressing per-pod alerts when a full cluster outage is confirmed. Do not group so broadly that two independent incidents get hidden together.

## 10. Severity, Routing, and Ownership

Severity should align with impact and response time:

| Severity | When to Use | Suggested Route |
| --- | --- | --- |
| page/critical | Service unable to serve traffic or capacity below safe threshold. | Immediate on-call. |
| warning | A dependency/instance is degraded but capacity remains sufficient. | Operations channel or ticket. |
| info | Expected transition, rollout, or maintenance. | Dashboard/event log. |

Every alert should have an owner/team, stable `service`/`environment`/`cluster` labels, a summary describing impact, a description listing signals and check steps, a verified runbook reference, and clear routing/escalation policies.

Do not stuff dynamic identifiers into labels just to show them in notifications. Annotations are better suited for explanatory content; labels must stay bounded for reliable grouping.

## 11. Dashboard for Health State

A dashboard should display both current status and trends:
- Total UP/ready instances.
- Desired vs. available replicas.
- Readiness/liveness failures over time.
- Dependency health by logical name.
- Restart count and restart rate.
- Scrape `up` by target.
- HTTP error rate/latency when health is degraded.
- Alert states and deployment annotations.

Do not rely on a single aggregate green light to conclude the system is healthy. A good dashboard supports drilling down from service capacity to instances, then to dependencies and related traces/logs.

~~~mermaid
flowchart TD
    Service["Service health overview"]
    Service --> Capacity["Ready / desired replicas"]
    Service --> Probe["Liveness and readiness"]
    Service --> Dependencies["Dependency states"]
    Service --> Scrape["Scrape availability"]
    Capacity --> Instance["Instance drill-down"]
    Dependencies --> Metrics["Latency / errors / pool metrics"]
    Instance --> Trace["Trace and log investigation"]
~~~

Use annotations for deploy/maintenance windows so on-call engineers can separate intentional transitions from incidents.

## 12. Testing Alert Rules

Alert rules should be tested with sample input series. With Prometheus, use `promtool test rules` to verify expressions, `for` durations, labels, and annotations.

Conceptual test file example:

~~~yaml
rule_files:
  - alerts.yml

evaluation_interval: 1m

tests:
  - interval: 1m
    input_series:
      - series: 'app_readiness_status{service="order-service",instance="a"}'
        values: '1 0 0 0 0'
    alert_rule_test:
      - eval_time: 4m
        alertname: SpringBootReadinessDegraded
        exp_alerts:
          - exp_labels:
              service: order-service
              instance: a
              severity: warning
~~~

Test format and expected labels must match your Prometheus version. If a rule has `for: 2m`, pick an evaluation time sufficiently after the expression first becomes true. Add tests for healthy state, `DOWN` shorter than `for`, sustained `DOWN`, recovery, single-instance readiness `DOWN` with sufficient remaining capacity, scrape failure separate from health `DOWN`, and optional dependencies producing warnings only.

Beyond rule tests, run integration tests for the health metric adapter/collector to ensure the metric reflects the exact same source of truth as Actuator health.

## 13. Fault Injection and Operational Testing

Use test/staging environments to create controlled states:
- Make a health indicator return `DOWN`.
- Disconnect a test database/broker dependency.
- Cause the health endpoint to time out.
- Stop an instance to test `up`.
- Force readiness `REFUSING_TRAFFIC` during a simulated rollout.
- Restore the dependency and verify the alert resolves.
- Send multiple transitions to test flapping/grouping.

Do not inject faults directly in production without change/incident authorization. Use canary/staging and limit blast radius. Verify notifications reach the right route with an owner and runbook, not just the Prometheus expression.

## 14. Troubleshooting

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Health DOWN but no alert | Missing metric adapter/scrape or wrong metric name in rule. | Check health endpoint, scrape target, and actual series. |
| `up == 0` while app is healthy | Scrape path/network/TLS/auth error. | Check Prometheus targets page and connectivity from scraper. |
| Alert fires during normal rollout | Short `for` or per-pod rule. | Use service capacity and rollout-aware policy. |
| Flapping alert | Short health indicator timeout, flapping dependency, or missing `for`. | Check latency, timeout, scrape interval, and grouping. |
| Readiness DOWN with no traffic impact | Excess capacity or overly strict group. | Cross-check desired/available replicas and degraded mode. |
| Whole service paged for optional dependency | Optional group used as readiness/page signal. | Split dependency alerts by criticality. |
| Alert does not resolve after health UP | Stale series, rule expression/labels, or scrape lag. | Check latest samples and evaluation state. |
| Too many duplicate notifications | Wrong grouping/inhibition/repeat interval. | Review Alertmanager routing tree. |
| Alert lacks runbook | Rule missing annotations or ownership metadata. | Add owner, action, and runbook reference. |
| Dashboard green while users see errors | Health indicators don't cover business paths. | Cross-check HTTP SLIs, latency, error rate, and traces. |

## 15. Runbook: Health State Alert Firing

1. Identify the alert name, service, environment, cluster, and affected instances.
2. Check the alert expression and when firing began.
3. Verify Prometheus scrape `up` to distinguish scrape failure from health `DOWN`.
4. Query the corresponding health group via an authorized management interface.
5. Check readiness/liveness and available replicas versus desired replicas.
6. Identify which dependency indicator is `DOWN` and cross-check dependency latency/error metrics.
7. Check deployment/maintenance events around the alert timestamp.
8. Open correlated traces/logs to find root cause; do not rely on health status alone.
9. Assess service capacity and user impact before scaling or restarting.
10. Follow the corresponding dependency/service runbook; avoid mass restarts during a shared dependency outage.
11. Watch for the alert to resolve and verify readiness/capacity return to normal.
12. Document root cause, detection/recovery times, and tune the rule if it was a false positive.

## 16. Self-Check Exercises

### Exercise 1 — Single-Pod Readiness DOWN

One pod's readiness goes `DOWN` during a rollout, while the service still has enough replicas. Should you page immediately?

**Answer:** Usually no. Monitor capacity and rollout context; only page when available replicas/capacity fall below threshold or user impact emerges.

### Exercise 2 — `up == 0`

Prometheus reports `up == 0`, yet an operator calling the health endpoint directly sees `UP`. What possibilities should be checked?

**Answer:** Scrape path/port, DNS, network policy, TLS/authentication, or timeouts between Prometheus and the target. `up` measures scrape success, not application health status.

### Exercise 3 — Health DOWN with No Metric

Actuator returns `DOWN`, but Prometheus has no health series. What is the common cause?

**Answer:** Health JSON has not been converted into a metric; missing adapter/exporter or scrape config. Simply exposing the endpoint does not automatically create a health gauge in every setup.

### Exercise 4 — Alert Flapping

Dependency health alternates `UP`/`DOWN` every 20 seconds. How do you reduce the notification storm?

**Answer:** Check probe timeout/cadence and dependency latency, apply an appropriate `for`, group alerts, and use inhibition. Do not extend `for` excessively if the service is losing capacity to serve.

### Exercise 5 — Optional Dependency

Search service is `DOWN`, but fallback cache continues serving requests. Which severity should be set?

**Answer:** Usually `warning` or a dashboard signal per degraded-mode policy—do not page as a service outage if user impact and capacity remain within SLO.

### Exercise 6 — Green Dashboard While Requests Fail

Health groups are `UP`, yet HTTP 5xx rises. Which additional signals are needed?

**Answer:** HTTP error rate, latency/SLOs, dependency metrics, and traces. Health indicators only reflect configured checks, not overall business correctness.

## 17. Implementation Checklist

- [ ] Health groups accurately reflect liveness, readiness, and dependency criticality.
- [ ] A clear metric source exists for health state; do not assume JSON becomes a metric automatically.
- [ ] Scrape `up` is alerted separately from application health.
- [ ] Alert on service capacity when appropriate instead of paging every pod readiness transition.
- [ ] Optional dependencies have severity/routing matching degraded mode.
- [ ] Rules have `for` based on scrape cadence and user impact.
- [ ] Labels are stable and bounded; no request/tenant/trace IDs or exception messages.
- [ ] Alerts include owner, severity, summary, description, and runbook.
- [ ] Alertmanager grouping, inhibition, and repeat intervals are tested.
- [ ] Dashboard shows ready/desired replicas, dependency states, and scrape health.
- [ ] HTTP error rate/latency are used to complement health state.
- [ ] Prometheus rule tests cover healthy, transient DOWN, sustained DOWN, and recovery.
- [ ] Integration tests verify the health adapter uses the right source of truth.
- [ ] Fault injection executed in staging/canary with bounded blast radius.
- [ ] Notifications verified to reach the right on-call route.
- [ ] Runbook and post-incident false-positive review process exist.

**Key Takeaways:** Alerting on health state requires a clear pipeline from Actuator health groups to metrics, rules, Alertmanager, and runbooks. Distinguish readiness/liveness from dependency health and scrape availability; alert on impact/capacity, use `for` with grouping to curb flapping, keep labels bounded, and test both firing and recovery. Health state is one operational signal; combine it with HTTP SLIs, metrics, logs, and traces to decide action.
