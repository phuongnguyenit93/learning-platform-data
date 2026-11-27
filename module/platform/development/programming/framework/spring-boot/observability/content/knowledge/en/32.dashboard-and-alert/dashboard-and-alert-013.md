# Runbooks Attached to Alerts

An alert reports that the HTTP 5xx error rate exceeded the threshold at midnight. The on-call engineer needs to know which service is affected, which dashboard to open first, how to determine whether errors started after a deployment or due to a dependency, and which mitigation actions are safe. If an alert only contains a metric name and a number, the recipient has to hunt for context while an incident is unfolding. A runbook attached to an alert turns a signal into an actionable, verifiable investigation procedure.

The lesson **Runbooks Attached to Alerts** belongs to the **Dashboard and Alert** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module teaches how to set up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; understand context propagation, tags/cardinality, exporters, sampling, and correlate signals to investigate errors, latency, and application behavior in production environments.

> **Principle:** A good alert must lead to concrete action. A runbook needs to state impact, trigger conditions, priority level, verification steps, links to dashboards/logs/traces, mitigation actions, recovery criteria, and escalation contacts. Steps must be safe, ordered, and clearly separate observation from production changes.

## 1. Learning Objectives

After this lesson, you will be able to:
1. Explain the relationship between an alert rule, its annotations, and a runbook.
2. Write executable runbooks for Spring Boot observability incidents.
3. Distinguish symptom, hypothesis, diagnosis, and mitigation.
4. Link alerts with dashboard panels, logs, traces, and deployment events.
5. Choose severity, duration windows, and impact criteria.
6. Design Prometheus alert annotations with a runbook URL and service context.
7. Write ordered triage steps that avoid blind configuration changes.
8. Define rollback, recovery, and verification criteria.
9. Manage ownership, escalation, and incident communication.
10. Test runbooks through tabletop or fault-injection exercises.

## 2. Alerts and Runbooks Do Two Different Jobs

An alert detects a condition requiring attention; a runbook guides the recipient to understand and resolve that condition.

| Component | Answers the Question |
|---|---|
| Alert name | What is abnormal? |
| Summary | What is the primary symptom? |
| Description | Which service/instance/impact is involved? |
| Severity | What level of response is needed? |
| Dashboard link | How is the situation changing over time? |
| Runbook link | What should be done next? |
| Logs/traces link | Where is the detailed evidence? |
| Owner/escalation | Who is responsible if it cannot be resolved? |

An alert should not stuff the entire runbook into annotations. Annotations should be brief, contextual, and contain stable links; the runbook holds the full procedure and is kept updated alongside the system.

~~~mermaid
flowchart TD
    A["Metric / SLO signal"] --> B["Alert rule"]
    B --> C["Notification with context"]
    C --> D["Runbook"]
    D --> E["Confirm impact"]
    E --> F["Investigate evidence"]
    F --> G["Mitigate safely"]
    G --> H["Verify recovery"]
    H --> I["Close / follow-up"]
~~~

## 3. Minimum Structure of a Runbook

A runbook should include these sections:
1. **Alert name and purpose:** describe the symptom, not just repeat the metric name.
2. **Severity and impact:** which users/capabilities are affected and to what extent.
3. **Trigger:** metric, threshold, window, labels, and alert duration condition.
4. **Dashboard:** links to relevant panels and default time range.
5. **Triage:** initial verification steps.
6. **Hypotheses:** common root causes and distinguishing evidence.
7. **Mitigation:** impact-reduction actions, applicability conditions, and rollback.
8. **Recovery:** criteria confirming the system is stable.
9. **Escalation:** owner, dependent teams, and when to escalate.
10. **Follow-up:** record timeline, root cause, and action items.

Avoid runbooks that are merely generic lists of possible causes. Each step should state explicitly what to inspect and which next step each finding leads to.

## 4. Severity and User Impact

Severity must reflect user impact and urgency, not simply how far a metric crossed a threshold.

| Level | Example | Response |
|---|---|---|
| Critical / SEV-1 | Most critical requests fail or service is unavailable | Trigger incident response immediately |
| High / SEV-2 | A major capability is clearly degraded, limited workarounds | On-call handles and updates incident |
| Warning | Resource pressure or latency increases without violating SLO yet | Monitor, investigate during business hours or per policy |
| Info | Unusual change worth noting | Do not page if there is no impact |

Define severity according to your organization's incident policy. Do not invent a new SEV scheme if your company already has a standard. Paging alerts need minimum traffic or symptom corroboration to avoid paging when sample volume is too low.

## 5. Writing Context-Rich Alert Annotations

Example Prometheus alert rule:

~~~yaml
groups:
  - name: spring-boot-http
    rules:
      - alert: SpringBootHighHttp5xxRate
        expr: |
          sum by (service) (rate(http_server_requests_seconds_count{
            status=~"5.."
          }[5m]))
          /
          clamp_min(sum by (service) (
            rate(http_server_requests_seconds_count[5m])
          ), 1)
          > 0.05
        for: 10m
        labels:
          severity: page
          team: order-platform
        annotations:
          summary: "HTTP 5xx rate is elevated for {{ $labels.service }}"
          description: "More than 5% of requests failed for 10 minutes."
          dashboard_url: "https://monitoring.example/d/order-service"
          runbook_url: "https://runbooks.example/spring-boot/http-5xx"
~~~

Illustrative example; metric names, labels, routing, and thresholds must match the application's actual Prometheus exposition. Do not copy example URLs into production. Consider adding `environment`, `cluster`, or a bounded route label if needed to distinguish blast radius.

Annotations should help recipients start immediately: service/environment, symptom and threshold/window, dashboard URL, runbook URL, and owner/team or escalation channel per internal convention. Do not embed tokens, credentials, customer data, or URLs containing secrets into alert annotations.

## 6. Sample Runbook: High HTTP 5xx Rate

**Goal:** Determine error scope, distinguish an application regression from a dependency outage, and reduce impact.

### 6.1 Confirm impact

1. Open the dashboard linked from the alert.
2. Confirm service, environment, cluster, and start time.
3. Compare 5xx rate against total request rate; check whether traffic is sufficiently high.
4. Check which route templates, status codes, and instances errors concentrate on.
5. Check p95/p99 latency and any breached SLOs.
6. Confirm errors via synthetic checks or user-facing signals if available.

If the 5xx rate spikes while request volume is near 0, inspect the denominator and telemetry gaps before declaring a major incident.

### 6.2 Gather evidence

- Open logs filtered by service, environment, and time window; look for exception classes/`error.type`.
- Open traces of failed requests; inspect the server span and downstream spans.
- Compare deployment/configuration changes against when the alert started.
- Check dependency health, timeouts, retries, and connection pool metrics.
- Distinguish errors across application validation, database, remote HTTP, or gateway.

Do not investigate by adding user IDs/emails into metric labels. Use trace IDs or correlation IDs with appropriate access controls to inspect an individual request.

### 6.3 Mitigation

Choose actions based on evidence:
- If a regression began right after a release and rollback is verified safe, execute rollback per deployment procedure.
- If a dependency is rate-limiting, apply a tested fallback/circuit breaker policy.
- If a specific route is causing abnormal load, shed traffic or disable the feature through an approved mechanism.
- If the pool is exhausted, identify connection leaks/slow queries before tuning the pool.
- If a database outage occurs, coordinate with the database owner and avoid mass-restarting healthy pods.

Every production change must follow organizational incident/change policy and be recorded in the timeline.

### 6.4 Recovery criteria

Close the alert only when:
- The 5xx rate returns to baseline over a confirmation window.
- Request rate is high enough for results to be meaningful.
- p95/p99 and related SLOs are stable.
- Dependency errors/timeouts have dropped.
- No failing instances or restart loops remain.
- Dashboards have no missing telemetry masking the situation.

## 7. Sample Runbook: High HTTP Latency

**Trigger:** p95/p99 latency exceeds budget over consecutive windows.

1. Confirm route, service, region/cluster, and timestamp.
2. Compare request rate, error rate, and in-flight requests.
3. Open the saturation dashboard: CPU, throttling, heap/GC, threads, and executor queues.
4. Check HikariCP active/idle/max/pending and acquisition wait.
5. Check HTTP client pool wait, downstream latency, timeouts, and retries.
6. Open slow traces to locate the span accounting for most of the duration.
7. Determine whether requests are waiting on local queues, database, remote APIs, or locks.
8. Apply mitigation at the identified bottleneck; avoid enlarging every pool simultaneously.
9. Monitor latency, backlog, and error rate after the change.
10. Confirm latency returns within SLO over the defined stability window.

Do not blame CPU solely because latency is high. Low CPU paired with high pool pending typically indicates waiting/saturation on a dependency or connection pool.

## 8. Sample Runbook: Database Connection Pool Exhausted

**Trigger:** Connection acquisition timeouts or sustained rise in pending threads.

### Triage

1. Confirm pool name, service instance, and start time.
2. Compare active, idle, max, pending, and acquisition duration.
3. Check connection usage duration and transaction duration if available.
4. Open slow request traces to look for long DB spans or transactions holding connections.
5. Check database availability, connection limits, locks, and slow queries.
6. Compare recent deployment/configuration changes.

### Hypotheses

| Hypothesis | Evidence to Look For |
|---|---|
| Slow query/lock | Long DB spans, rising query/lock waits |
| Connection leak | Active does not drop after workload, abnormal usage duration |
| Traffic burst | Arrival rate rises alongside concurrency |
| Pool too small | Pending rises under normal load while DB still has capacity |
| Database connection limit | DB connection count near server limit |
| Long-lived transactions holding connections | High transaction duration or external calls inside transactions |

### Mitigation and recovery

- Shed incoming load if a traffic burst is overloading the system.
- Stop or roll back a release introducing a query/transaction regression per procedure.
- Fix leaks/long transactions in the identified code path.
- Increase pool size only when the DB server has capacity and total connection budget has been calculated.
- Confirm pending/acquisition wait returns to baseline and DB latency stabilizes.

Do not raise pool size blindly; the combined pool size across all replicas can exceed the database's connection limit.

## 9. Sample Runbook: Queue Backlog or Consumer Lag

**Trigger:** Oldest message age, queue wait, or consumer lag exceeds SLO.

1. Confirm queue/topic, consumer group, and message type.
2. Compare arrival rate against completion throughput.
3. Check queue depth, oldest age, in-flight/unacked, and retry/dead-letter rate.
4. Check consumer instances, concurrency, partition assignment, and rebalances.
5. Inspect processing duration and dependency spans inside consumers.
6. Distinguish insufficient worker capacity from slow downstream DB/APIs.
7. Check whether poison messages/retry loops are occupying workers.
8. Scale consumer capacity only if downstream dependencies have headroom.
9. If necessary, pause/throttle producers or route messages according to defined policy.
10. Monitor backlog drain rate and end-to-end age until they return to target.

Kafka offset lag is a count of records/offset distance; do not convert it directly into wait time without considering throughput and record age.

## 10. Sample Runbook: Telemetry Exporter or Collector Losing Data

**Trigger:** Export failures, queue occupancy, or dropped spans/records increase.

1. Confirm whether application business SLOs are impacted or only the telemetry pipeline.
2. Check SDK queue size/capacity, dropped spans, and exporter duration.
3. Check Collector receiver rate, refused records, memory limiter, and exporter queue.
4. Check backend throttling, 429/503 responses, network, and DNS/TLS errors.
5. Pinpoint the first point of data loss: SDK, network, Collector, or backend.
6. Reduce telemetry volume per policy: sample normal traces, filter noisy health checks, rate-limit repetitive logs.
7. Preserve availability, latency, and telemetry-drop metrics if the pipeline still has capacity.
8. Restore the exporter/backend and drain queues at a controlled rate.
9. Confirm drop rates decrease, queue age stabilizes, and request latency is unaffected.
10. Clearly mark the period of incomplete telemetry so dashboard readers do not mistake missing data for zero.

Do not allow slow telemetry exports to block request threads. Telemetry loss must be surfaced clearly and have its own alerts.

## 11. Dashboards, Logs, and Traces in Runbooks

Runbooks should link directly to:
- Service overview dashboard.
- Saturation dashboard.
- Dependency dashboards (DB, HTTP client, messaging).
- Pre-populated log queries with service/environment/time range.
- Trace search by trace ID or error/latency filters.
- Deployment timeline.
- Health/readiness endpoints or platform status.
- Relevant SLO/error budget panels.

Links must be stable, respect appropriate access controls, and avoid query strings containing secrets/PII. If dashboards use variables, use standardized `service`/`environment` labels.

An investigation step should specify which evidence to look for. For example: open the slowest trace and inspect the DB client span; if the DB span accounts for most of the latency, switch to the DB pool/query runbook.

## 12. Ownership and Escalation

Every alert needs a clear owner. Runbooks should specify:
- Primary on-call team.
- Dependency owners (database, platform, messaging, network).
- When to page an incident commander.
- Escalation conditions if root cause is not found within the target timeframe.
- Incident update channels per internal process.
- Who is authorized to roll back or alter traffic/configuration.

Do not tie a specific individual into a runbook if on-call rotations change frequently; use a team alias or centrally managed on-call schedule.

## 13. Runbooks Must Be Safe and Easy to Execute

Runbook steps must:
- Start with read-only diagnosis.
- Clearly flag commands/queries that affect production.
- State preconditions and expected results.
- Document a rollback path for mitigations.
- Never require sharing credentials or PII.
- Never instruct restarting/scaling/disabling features without safety conditions.
- Never prescribe a single blanket action for every root cause.
- Include timestamps/timezones and instructions for recording the incident timeline.

If a runbook includes commands, use safe placeholders for namespace/service and require context verification before execution. Never store tokens or passwords in URLs, command histories, or documentation.

## 14. Testing and Maintaining Runbooks

A runbook is not complete just because text was written. Test that:
1. The alert rule fires on synthetic metrics at the expected threshold/window.
2. Annotation links open the right dashboard and runbook.
3. Queries use real labels, not assumed metric names.
4. On-call engineers have permission to access dashboards/logs/traces.
5. Triage steps lead to findable evidence.
6. Mitigations have an owner and a rollback path.
7. Recovery criteria are measurable via metrics.
8. Tabletop exercises confirm newcomers can follow the steps.
9. After an incident, new root causes are added and outdated steps removed.
10. Links, ownership, and version/config changes are reviewed periodically.

Attach a review date or owner metadata in the documentation system. Do not hardcode dates/owners inside alert rules if another source of truth already exists.

## 15. Troubleshooting Runbook and Alert Quality

| Issue | Possible Cause | How to Improve |
|---|---|---|
| Alert fires with no impact | Threshold too sensitive or missing minimum traffic | Correlate with SLO/user impact |
| On-call doesn't know where to start | Summary/links lack context | Add dashboard, service, environment, and runbook URL |
| Runbook has too many generic steps | Steps not tied to hypotheses/evidence | Write a symptom-driven decision path |
| Mitigation worsens the incident | Missing preconditions/rollback | Add safety checks and expected results |
| Dashboard has no data | Telemetry gap or wrong label | Add no-data detection and verify exporter |
| Alert re-fires right after handling | Recovery window too short or root cause unresolved | Set a stable recovery window and follow up |
| Multiple teams receive the same alert | Unclear routing/ownership | Define primary owner and dependency escalation |
| Broken runbook links | Dashboard/document moved | Check links automatically or periodically |
| Query fails to run | Metric name/labels differ in reality | Validate against scrape output and registry |
| Unable to confirm recovery | No measurable exit criteria | Define SLOs, baselines, and a stability window |

## 16. Playbook: From Alert to Closing an Incident

**Scenario:** On-call receives an alert with a runbook link.

1. Acknowledge per on-call policy and confirm service/environment.
2. Read summary, severity, trigger window, and impact.
3. Open the dashboard link and independently confirm the symptom.
4. Follow the alert's runbook; do not run mitigations before gathering evidence.
5. Record incident start time and recent changes.
6. Check logs/traces/metrics in the runbook's sequence.
7. State a hypothesis and the evidence confirming or refuting it.
8. Execute an authorized mitigation, recording the change and rollback path.
9. Monitor recovery criteria over a stability window.
10. Close the alert/incident per policy; record timeline, root cause, data gaps, and follow-up actions.
11. Update the runbook if any step was inaccurate or lacked evidence.

If telemetry is missing during an incident, record the data gap and rely on independent health/platform signals to avoid false conclusions.

## 17. Self-Check Exercises

**Exercise 1 — Alert contract.** Which alerts need a runbook URL? What minimum context should an annotation contain?

**Exercise 2 — Severity.** CPU rises high while request SLOs remain normal. Why might a warning suffice instead of paging?

**Exercise 3 — HTTP 5xx.** State the order of verifying impact, logs/traces, and deployment changes before mitigation.

**Exercise 4 — Pool exhaustion.** Why can increasing HikariCP maximum pool size worsen a database outage?

**Exercise 5 — Queue backlog.** Which metrics distinguish a producer burst from a consumer/downstream bottleneck?

**Exercise 6 — Telemetry loss.** Why must a runbook explicitly note periods of incomplete telemetry?

**Exercise 7 — Recovery.** Why shouldn't an incident be closed the instant a metric dips below the threshold once?

**Exercise 8 — Safety.** A runbook suggests restarting all pods when DB health is DOWN. Which additional conditions would you require?

### Suggested Answers

1. Actionable/paging alerts need a runbook URL; at minimum include service/environment, symptom, threshold/window, dashboard, and owner.
2. There is no user impact yet and headroom may still exist; inspect run queue/throttling and latency before paging.
3. Confirm request volume/route/status, open the dashboard, inspect logs/traces/dependencies, check the deployment timeline, and only then choose a mitigation.
4. Total connections across all replicas can exceed the DB limit, increasing contention and overloading the database.
5. Arrival/completion rate, queue depth, oldest age, consumer lag, processing duration, retries, and downstream latency.
6. Dashboard readers need to know that missing telemetry does not mean zero errors/traffic.
7. A stable recovery window and SLO/dependency checks are needed to prevent flapping or premature closure.
8. Check liveness/process health, dependency outage, readiness policy, blast radius, rollback, and only restart when evidence shows the process needs a restart.

## 18. Official References

- [Prometheus — Alerting Rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/): alert expressions, labels, annotations, and duration.
- [Prometheus — Alertmanager](https://prometheus.io/docs/alerting/latest/alertmanager/): grouping, routing, inhibition, and notifications.
- [Google SRE Workbook — Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/): user-impact and SLO-based alerting.
- [Google SRE Workbook — Incident Response](https://sre.google/workbook/incident-response/): incident roles, communication, and response processes.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): metrics instrumentation and Micrometer integration.
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): trace context, sampling, and exporters.
- [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation/introduction.html): Observation lifecycle and signal handlers.
- [OpenTelemetry Collector — Resiliency](https://opentelemetry.io/docs/collector/resiliency/): telemetry queue/retry and pipeline reliability.

**Key Takeaways:** Alerts detect symptoms; runbooks turn symptoms into verifiable verification, diagnosis, mitigation, and recovery steps. Every alert needs an owner, severity, impact, dashboard/log/trace links, and clear closure criteria. Start with read-only evidence, and modify production only when a hypothesis is backed by evidence and has a rollback path. Test links, queries, permissions, and tabletop exercises periodically so runbooks remain useful when real incidents occur.
