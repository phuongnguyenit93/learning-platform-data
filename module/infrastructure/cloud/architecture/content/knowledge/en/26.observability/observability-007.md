# Symptom-Based Alerting and Error Budget Burn Rate

A system can have CPU at 90%, frequent pod restarts, or rising database latency without users yet experiencing visible errors. Conversely, CPU can look normal while login requests fail, checkouts time out, or APIs return wrong data. If operations teams alert solely on resources, they can receive many notifications that do not reflect real impact while missing incidents that directly affect users.

**Symptom-based alerting** detects when a service is no longer delivering what users need, such as failing requests, slow responses, or incomplete transactions. An **error budget** is the amount of error or disruption permitted by an SLO over a given period. **Burn rate** describes the rate at which the error budget is being consumed relative to the sustainable rate allowed by that SLO.

This lesson belongs to the **Observability** chapter of the **CLOUD_ARCHITECTURE** module. The goal is to design alerts tied to SLIs/SLOs, separate symptoms from causes, detect rapid error budget consumption via burn-rate alerts, route alerts to the right owners, and improve response quality. The content connects performance, reliability, operations, cost, and Well-Architected principles.

## 1. Why Must Alerting Start from User Experience?

Monitoring produces abundant signals: CPU, memory, network, queue depth, database connections, pod restarts, HTTP statuses, and log errors. However, operations cannot treat every metric fluctuation as an incident.

Consider the Booking API:
- Application CPU rises to 85% during a traffic surge, yet requests still complete within SLO.
- The database connection pool hits its limit, p95 latency rises, and some requests time out.
- Payment confirmations fail even though the overall API still returns 200 for other requests.
- A background worker runs 10 minutes behind, yet users are unaffected because the queue has enough headroom.

If paging triggers on CPU or every warning, on-call engineers are interrupted by events needing no immediate intervention. If alerts only trigger when a process crashes, users can be impacted for a long time before detection.

Good alerts must answer:
1. Are users experiencing errors or latency worse than committed?
2. Which service, endpoint, tenant, or workflow is impacted?
3. How fast is the SLO error budget being consumed?
4. Who needs to act and what should they do first?
5. When should we page immediately vs. create a ticket or observe?

~~~mermaid
flowchart TB
    U["User journey"] --> SLI["Service level indicators"]
    SLI --> SLO["Service level objectives"]
    SLO --> EB["Error budget"]
    SLI --> BR["Burn rate"]
    BR --> ALERT["Symptom-based alerts"]
    ALERT --> ONCALL["On-call / incident response"]
    ONCALL --> FIX["Mitigation and recovery"]
    FIX --> REVIEW["Post-incident review"]
~~~

## 2. Distinguishing Metrics, SLIs, SLOs, SLAs, and Error Budgets

These concepts are related but not interchangeable.

| Concept | Meaning | Example |
|---|---|---|
| Metric | An observable measurement | HTTP 5xx count, p95 latency, CPU usage |
| SLI | Indicator representing a service quality aspect | Proportion of valid requests completing successfully |
| SLO | Internal target for an SLI over a time window | 99.9% availability over 30 days |
| SLA | Service commitment to customers/partners, often with clauses | Contractually committed availability |
| Error budget | Allowable errors remaining under the SLO | 0.1% failed requests within the SLO window |

A metric only becomes an SLI when it reflects a quality aspect users care about and is explicitly defined. For example, CPU utilization is usually a cause metric or capacity signal; by itself it does not reflect Booking API availability.

### 2.1. Choosing SLIs Around User Journeys

Start from actions users need to complete:
- Search for properties and receive valid results.
- Sign in and access an account.
- Create a booking successfully.
- Confirm payment.
- Download authorized documents.

An SLI must clearly define:
- Which events are eligible events?
- Which events count as good or bad?
- How are timeouts, cancellations, and client aborts counted?
- Are synthetic probes included in the SLI?
- Are internal requests, health checks, and retries double-counted?
- Is it segmented by region, endpoint, tenant, or service tier?

Example simple availability SLI:

\[
Availability\ SLI = \frac{Good\ Events}{Eligible\ Events}
\]

If there are 100,000 eligible requests in a window and 99,950 good requests:

\[
SLI = \frac{99,950}{100,000} = 99.95\%
\]

A request counted as good must meet agreed criteria, such as returning a success status and completing within deadline. If an API returns HTTP 200 while the workflow fails to create a valid booking, an SLI based solely on status codes mismeasures quality.

### 2.2. Latency SLI

Latency can be expressed as the percentage of requests completing within a threshold:

\[
Latency\ SLI = \frac{Requests\ within\ threshold}{Eligible\ requests}
\]

For example, an SLO requiring 99% of search requests to complete within 300 ms. Do not track only average latency because a small fraction of very slow requests can be masked by the majority of fast requests. Use histograms or distributions to compute quantiles and percentages under thresholds.

### 2.3. SLOs Must Have Scope and Windows

An SLO should state:
- Which service or capability is measured.
- Which request population is in scope.
- The SLI and calculation formula.
- The target percentage.
- The time window, e.g., rolling 30 days.
- The data source and handling of missing telemetry.
- The accountable owner.

Do not assign the same SLO to every endpoint when business criticality and controllability differ. Setting an overly loose SLO yields no useful signal; setting an overly strict one causes alert noise and unnecessary cost.

## 3. Error Budget: The Allowable Error Margin

If the availability SLO is 99.9%, the error budget is 0.1% bad events over the evaluation window.

\[
Error\ Budget = 1 - SLO
\]

With 100,000 eligible requests:
- A 99.9% SLO allows 100 bad requests.
- A 99.95% SLO allows 50 bad requests.
- A 99.99% SLO allows 10 bad requests.

For time-based availability SLOs, this translates to allowable downtime duration in the window. For request-based SLOs, the budget is measured in failed requests out of eligible requests.

Error budgets provide a basis for balancing delivery speed with reliability:
- When the budget is healthy, teams have room for controlled changes.
- When the budget is burning rapidly, teams must prioritize risk reduction and remediation.
- When the budget is exhausted, release policies may restrict high-risk changes until reliability improves.

An error budget does not mean teams are licensed to deliberately cause errors. It quantifies the acceptable level of imperfection built into the service design.

### 3.1. Monthly Budget Example

Suppose the Booking API receives 10 million eligible requests in 30 days with a 99.9% availability SLO.

\[
Budget = 10,000,000 \times 0.001 = 10,000
\]

If 6,000 bad requests have already occurred, 4,000 requests remain in the budget. If bad requests surge within an hour, the system could exhaust the budget before month-end even while the cumulative SLI still temporarily looks above target.

This is why teams must monitor both remaining error budget and burn rate, not just end-of-window SLO compliance.

## 4. Symptom-Based Alerts vs. Cause-Based Alerts

**Symptom-based alerts** fire when a service is violating or about to violate user experience. **Cause-based alerts** fire on an underlying condition or infrastructure state that could lead to impact.

| Signal | Category | How to Use |
|---|---|---|
| Rising booking failure rate | Symptom | Page if exceeding impact threshold |
| Search p99 latency exceeds SLO | Symptom | Page based on severity and duration |
| Availability SLI drops sharply | Symptom | Page |
| CPU at 90% briefly | Cause/capacity | Dashboard or ticket depending on context |
| Database connection pool exhausted | Proximate cause | High-priority alert if impact occurs |
| Queue oldest age exceeds business deadline | Symptom or near-symptom | Page if delayed processing affects customers |
| Single node restart | Cause | Usually no page if other replicas still serve traffic |
| Certificate nearing expiry | Leading indicator | Ticket/alert before impact occurs |

Cause alerts remain very valuable. They surface early risks before users are affected. However, symptom alerts should never be replaced by a list of infrastructure thresholds.

A practical model:
- Symptom alerts determine when immediate human response is needed.
- Cause alerts aid diagnostics and incident prevention.
- Informational signals support dashboards, capacity planning, and trends.
- Predictive alerts warn of approaching limits when confidence is high enough.

## 5. What Is Burn Rate?

Burn rate is the speed at which the error budget is being consumed relative to the rate that would exhaust the budget exactly at the end of the SLO window.

\[
Burn\ Rate = \frac{Observed\ Error\ Rate}{Allowed\ Error\ Rate}
\]

Where:

\[
Allowed\ Error\ Rate = 1 - SLO
\]

If the availability SLO is 99.9%, the allowed error rate is 0.1% or 0.001.

- Burn rate = 1: consuming the budget at the exact pace permitted across the window.
- Burn rate = 2: consuming twice as fast as permitted.
- Burn rate = 10: consuming ten times as fast.
- Burn rate < 1: current error level is below the sustainable budget pace.

Burn rate is not a raw error ratio. It normalizes error rates against the SLO target, enabling risk comparison across services with different SLOs.

### 5.1. Calculation Example

Availability SLO = 99.9%; allowed error rate = 0.1%.

If the observed error rate over 5 minutes is 2%:

\[
Burn\ Rate = \frac{2\%}{0.1\%} = 20
\]

The service is consuming its error budget 20 times faster than the sustainable pace. However, a 5-minute window may have few requests or be skewed by low traffic; combine additional windows and minimum event counts to reduce false positives.

### 5.2. Estimating Time to Budget Exhaustion

Assuming burn rate stays roughly constant, you can estimate:

\[
Time\ to\ exhaust \approx \frac{Remaining\ budget\ fraction \times SLO\ window}{Burn\ rate}
\]

For example, a 30-day SLO window with 50% remaining budget and a burn rate of 10:

\[
Time \approx \frac{0.5 \times 30\ days}{10} = 1.5\ days
\]

This is a simplified estimate assuming constant burn rate and uniform budget consumption under the measurement model. In reality, traffic and errors fluctuate; use it as an urgency indicator rather than a guaranteed forecast.

## 6. Multi-Window, Multi-Burn-Rate Alerting

Using only a long window delays detection. Using only a short window allows tiny bursts to trigger false positives. One approach is combining multiple time windows and burn-rate thresholds.

For example:
- Short window detects an active ongoing incident.
- Long window confirms the errors are sustained and meaningfully impactful.
- Requiring the same burn-rate threshold across both windows avoids paging on very brief spikes.

~~~mermaid
flowchart TB
    SLI["SLI error events"] --> W1["Short window"]
    SLI --> W2["Long window"]
    W1 --> C{"Both windows exceed burn threshold?"}
    W2 --> C
    C -->|"Yes"| PAGE["Page on-call"]
    C -->|"No"| KEEP["Keep observing / lower-severity alert"]
~~~

### 6.1. Illustrative Policy Example

Suppose the SLO is 99.9% over 30 days. A reference policy might use:
- Burn rate 14.4 across 1-hour and 5-minute windows: urgent page.
- Burn rate 6 across 6-hour and 30-minute windows: high-severity page.
- Burn rate 3 across 24-hour and 2-hour windows: priority alert or ticket, depending on org policy.

These numbers are common illustrative examples showing how windows pair together, not mandatory thresholds. Tune them to your SLO window, traffic, criticality, alerting platform, and on-call policies.

### 6.2. Calculating Budget Consumed

With burn rate r over duration t, the fraction of error budget consumed is approximately:

\[
Budget\ consumed \approx r \times \frac{t}{T}
\]

Where T is the SLO window; this formula assumes a steady rate over the interval and consistent error event definitions.

For example, a burn rate of 14.4 sustained for 1 hour in a 30-day window:

\[
14.4 \times \frac{1}{720} = 0.02 = 2\%
\]

That is roughly 2% of the monthly error budget consumed in a single hour. Pairing two windows captures both current severity and incident persistence.

### 6.3. Why Use Two Windows?

A 20-second failure can produce a very high burn rate in a 1-minute window yet not warrant a page if total requests were small and it already self-recovered. The longer window confirms whether the trend has sustained impact.

Conversely, a 6-hour window alone delays alerting when the entire service just went down. The short window provides faster response. Multi-window alerting balances speed and precision.

## 7. Symptom Alerts: Availability, Latency, Traffic, and Correctness

SLIs must reflect what the service actually delivers to users.

### 7.1. Availability and Request Failures

Measure the proportion of eligible requests failing to return a successful result. Agree on counting rules:
- 5xx responses are normally bad events.
- 4xx caused by invalid client input may be excluded from availability SLIs, except where the system failed to deliver proper functionality.
- Server-side timeouts are normally bad.
- Client aborts before the server processes the request may need exclusion or separate classification.
- Retries should be attributed to the original request or business operation to avoid distorting ratios.

Do not mechanically exclude all 4xx responses. For instance, HTTP 429 rate-limiting valid users may reflect degraded experience; decide whether the SLI intends to measure that.

### 7.2. Latency and Tail Latency

Alerts can rely on:
- Proportion of requests exceeding a deadline.
- p95/p99 exceeding thresholds over sufficient duration.
- Absolute slow request count paired with slow ratio.

Quantiles fluctuate heavily on small samples. Histogram buckets better support computing percentages within thresholds and aggregating across instances. Never average per-pod p95 values as if that were the service-wide p95.

### 7.3. Traffic and Saturation

A sudden drop in traffic can be a symptom: the gateway is not receiving requests, DNS broke, or clients cannot connect. Unusual traffic spikes may reflect legitimate demand, bots, or retry storms.

Saturation metrics like CPU, memory, thread pools, connection pools, and queue depth are causes/early warnings. Link them to SLIs: if saturation is high while SLOs remain green, monitoring or a capacity ticket may suffice; once latency/errors breach, page on the symptom.

### 7.4. Correctness and Business Outcomes

HTTP 200 does not guarantee correct business execution. Measure:
- Booking creation success and read-back consistency.
- Payment confirmation outcomes.
- Proportion of valid predictions/outputs.
- File upload completion.
- Queue jobs finishing before deadline.
- Proportion of transactions with valid state transitions.

Correctness SLIs need independent verification sources and must never place sensitive data into metric labels.

## 8. Designing Alert Rules: From Metrics to Action

A good alert rule should specify:
- Related service and SLO.
- Condition and measurement windows.
- Severity level.
- Hold duration or minimum event count.
- Receiving owner/team.
- First response action.
- Linked dashboards/runbooks.
- Resolution and suppression behavior.

Conceptual PromQL example for request error ratio:

~~~promql
sum(rate(http_requests_total{service="booking-api",status=~"5.."}[5m]))
/
sum(rate(http_requests_total{service="booking-api"}[5m]))
~~~

This is an illustrative PromQL example. Production rules must exclude or classify non-SLI requests, maintain bounded label cardinality, and handle zero denominators.

A simple burn-rate expression might look like:

~~~promql
(
  sum(rate(http_requests_total{service="booking-api",status=~"5.."}[5m]))
  /
  sum(rate(http_requests_total{service="booking-api"}[5m]))
) / 0.001
~~~

With a 99.9% SLO, the allowed error ratio is 0.001. This expression returns the burn rate for the current error ratio. Multi-window alerts must compare multiple expressions/windows in the same condition rather than alerting on a single 5-minute expression alone.

### 8.1. Handling Low or Zero Denominators

If there are no requests, the error ratio may be undefined or empty. That does not prove the service is healthy. Supplement with:
- Synthetic probes at an appropriate cadence.
- Traffic-absence alerts when traffic is expected.
- Minimum event count or minimum traffic conditions.
- Separate monitoring for ingress/DNS/edge.

For low-traffic services, request-based SLIs may need longer windows or synthetic transactions, while avoiding letting synthetic probes mask real user experience.

## 9. Paging, Tickets, and Dashboards: Response Tiers

Not every alert should wake up the on-call engineer.

| Level | When to Use | Response Channel |
|---|---|---|
| Page / Critical | Users are severely impacted or error budget is burning rapidly | Immediate on-call page |
| High | Potentially major impact requiring prompt response | On-call/incident channel |
| Ticket / Warning | Capacity risks, trends, or slow budget burn | Ticket with deadline |
| Info | Normal operational events or changes | Dashboard/event log |

Paging should be reserved for when:
- Urgent human action is required.
- Impact is happening now or imminent with severe consequences.
- There is a clear owner and runbook.
- It cannot wait until next business hours.

If an alert requires no action, it belongs as a ticket or dashboard signal rather than a page. Paging on CPU spikes that do not affect users breeds alert fatigue, causing engineers to miss real incidents.

## 10. Reducing Alert Noise and Alert Fatigue

Alert fatigue occurs when on-call engineers receive too many duplicate, unhelpful, or non-actionable alerts. As a result, critical alerts can be overlooked.

Causes:
- Static thresholds untied to traffic or SLOs.
- Per-instance alerts not aggregated into service-level symptoms.
- One incident firing multiple alerts across multiple layers.
- Alerts lacking owners or runbooks.
- Thresholds oscillating near boundaries causing flapping.
- Retry storms amplifying secondary errors.
- Dashboard warnings routed as pages.
- Metrics lacking labels/context needed to assess scope.

Improvements:
1. Group alerts by incident, service, and symptom.
2. Use multi-window/multi-burn-rate for SLO alerts.
3. Add for-durations or hysteresis for oscillating signals.
4. Use scoped inhibition/suppression, e.g., suppress pod alerts when a region outage page is active.
5. Separate pages, tickets, and info signals.
6. Auto-resolve once recovery conditions stabilize.
7. Review alerts post-incident and remove rules that drive no action.
8. Track false positives, duplicates, and acknowledgement rates.

Never suppress all alerts during a major incident. A secondary alert might still represent a separate impact or unmitigated area; suppression must have explicit scope.

## 11. Alert Routing, Ownership, and Escalation

An alert only has value when it reaches the right person who can act.

Define:
- Service owner and primary/secondary on-call.
- On-call rotation schedules and timezone coverage.
- Escalation paths when unacknowledged.
- Incident commander when multiple services are affected.
- Dependency teams such as database, network, identity, and security.
- Communications owner if customers/partners need updates.
- Runbooks, dashboards, recent deployments, and change context.

Alert payloads should include:
- SLO/service name and symptom.
- Severity and burn rate.
- Error ratio/count and breaching windows.
- Affected region/endpoint/cohort.
- Start time and trend.
- Links to dashboards/queries/runbooks.
- Recent change/deploy context if available.
- Owner and escalation path.

Avoid putting raw request bodies, tokens, emails, or PII into alert payloads. Alerts should carry controlled identifiers so authorized analysts can query details.

## 12. Correlating Symptoms with Causes for Fast Diagnosis

Symptom alerts set urgency; cause telemetry finds the root cause. Build a dependency map:

~~~mermaid
flowchart TB
    USER["Search p99 latency SLO breach"] --> API["Booking API"]
    API --> FEAT["Feature / cache lookup"]
    API --> DB["Database"]
    API --> PAY["Payment dependency"]
    FEAT --> REDIS["Redis saturation"]
    DB --> CONN["Connection pool / locks"]
    PAY --> EXT["Provider latency / quota"]
~~~

When p99 latency spikes, dashboards can show side by side:
- Recent deploys/changes.
- API concurrency, thread pools, and GC.
- Cache hit/miss rates, hot keys, and latency.
- Database connection waits, slow queries, locks, and replication lag.
- External API latency, quotas, and 429s.
- Network packet loss, DNS, and TLS handshakes.
- Queue depth/oldest age.

Do not create separate paging alerts for every single cause and page all of them simultaneously. Keep cause alerts at ticket or warning level unless they represent an imminent outage risk, such as an expiring certificate or nearly full database storage.

## 13. Burn-Rate Policies by Service Tier

Services with different business impact can use different SLOs, windows, and escalation rules. Avoid forcing one policy across all services.

| Service Tier | Examples | Alert Priority | Action on High Burn |
|---|---|---|---|
| Tier 0 | Booking commit, payment confirmation | Fast page | Immediate incident response and mitigation |
| Tier 1 | Search, login, customer API | Page per burn-rate policy | Rollback, capacity, or dependency mitigation |
| Tier 2 | Notifications, reporting | Page on real deadline/impact | Queue drain, retries/backfill |
| Tier 3 | Internal analytics batches | Ticket or page by data deadline | Reschedule, recompute, adjust capacity |

SLOs can differ between customer-facing and internal workloads. However, if an internal batch produces data needed for next-day transactions, its deadline can still carry major business impact.

### 13.1. Do Not Let Low Traffic Mask Outages

A low-traffic endpoint can show a 100% error ratio from a single request. A high-traffic endpoint with a 1% error ratio can affect thousands of users. Alert policies should combine:
- Error ratio.
- Absolute failed event count.
- Burn rate.
- Minimum traffic.
- Synthetic user journeys.
- Service criticality.

Do not optimize around a single percentage threshold alone.

## 14. When the Error Budget Burns Rapidly

When a burn-rate alert fires, teams need a repeatable workflow:

1. Confirm the SLI, breaching windows, and affected service scope.
2. Check traffic/denominator, telemetry gaps, and duplicate counting.
3. Identify onset time, deployment/config changes, and dependency changes.
4. Estimate user impact and time until budget exhaustion.
5. Apply impact-reducing mitigation before attempting a permanent fix.
6. If tied to a release, consider pausing rollouts or rolling back per runbook.
7. Shed load, disable non-essential features, or switch to degraded mode if approved.
8. Monitor SLI/burn rate after mitigation.
9. Record incident timeline, budget consumed, and recovery.
10. Create action items to reduce recurrence.

### 14.1. Release Policies When Budget Runs Low

Organizations can define release policies:
- Healthy budget: release via normal process.
- Rapidly burning budget: tighten canaries, require extra approvals, or shrink release scope.
- Exhausted budget: pause risky releases for the service until reliability improves, except changes needed for incident/security remediation.

This is an internal governance policy; error budgets should not mechanically block every deploy when a hotfix is required to restore service.

## 15. Synthetic Monitoring and Real-User Monitoring

**Real-user monitoring (RUM)** observes experience from real user requests/sessions. **Synthetic monitoring** proactively runs test transactions on a schedule or from multiple locations.

RUM:
- Reflects real traffic and real devices.
- Supports breakdown by browser, region, cohort, and network.
- Only produces data when real users visit.
- Requires privacy controls and appropriate sampling.

Synthetic:
- Detects broken DNS, TLS, login, or user journeys even when real traffic is low.
- Can probe from multiple regions.
- Easy to standardize and repeat.
- Does not fully represent every user, account, device, or payment path.

Combine both to avoid false-healthy states during low traffic and prevent green synthetic checks from masking issues affecting a specific user cohort.

Synthetic tests must use dedicated test accounts/data, avoid creating real bookings/payments, and clean up afterward. If end-to-end production testing is necessary, design safe and idempotent side effects.

## 16. Well-Architected Trade-Offs in Alerting

| Aspect | Good Design | Risks to Control | Evidence |
|---|---|---|---|
| **Reliability** | Alerts on SLI/SLO, burn rate, with owners and runbooks | Delayed alerts, missing telemetry, false positives | Incident drills, SLO dashboards, alert reviews |
| **Security** | Alerts on anomalous privilege/data access, protected payloads | PII/secrets in alerts, overly broad SIEM permissions | Access reviews, redaction tests, audits |
| **Performance Efficiency** | Tracks latency and user journeys, catches saturation early | High-cardinality metrics, resource-heavy queries | Query costs, scrape/ingestion health |
| **Cost Optimization** | Pages at the right times, tiers hot/warm telemetry | Excessive SIEM/log volume and on-call toil | Cost per service, alert actionability |
| **Operational Excellence** | Escalation, incident workflows, feedback loops | Alert fatigue, missing ownership | MTTD/MTTA/MTTR, duplicate rate |
| **Sustainability** | Collects right-sized signals with sensible retention | Redundant telemetry, wasteful storage and analytics compute | Data minimization, retention/cost reviews |

Key trade-offs:
- Short windows detect fast but are noisier; long windows are steadier but slower.
- Burn-rate alerts reflect budget consumption but depend on SLI quality.
- Frequent paging speeds awareness but increases fatigue and on-call cost.
- Request-based SLIs fit high-traffic APIs; synthetic or workflow SLIs may be needed for low-traffic services.
- Symptom alerts cut noise from harmless causes but require strong cause telemetry for investigation.
- Over-segmenting SLOs exposes cohorts at the expense of complexity and cardinality.

## 17. SLO-Driven Alert Design Process

A practical review process:

1. **Map user journeys:** identify actions users need to complete.
2. **Select SLIs:** success, latency, freshness, correctness, or workflow completion.
3. **Write SLOs:** target, window, scope, denominator, and owner.
4. **Calculate error budgets:** error ratio and corresponding error count/minutes.
5. **Measure baselines:** traffic, error distribution, latency, seasonality, and missing telemetry.
6. **Choose burn-rate thresholds:** multi-window tiers aligned with criticality and response times.
7. **Create symptom alerts:** page only on significant SLO impact/threat.
8. **Add cause alerts:** capacity, dependencies, expiries, and pipeline health.
9. **Configure routing:** owners, severities, on-call, escalation, and runbooks.
10. **Reduce noise:** deduplication, grouping, scoped inhibition, hysteresis, and resolve policies.
11. **Test:** synthetic failures, traffic bursts, low denominators, telemetry loss, and burn simulations.
12. **Review:** false positives, missed incidents, time-to-detect, toil, and budget policies.

### Production Readiness Checklist for Alerts

| Item | PASS Criteria |
|---|---|
| User impact | Alert describes a concrete symptom or risk |
| SLI/SLO | Definition, scope, and owner exist |
| Burn calculation | Allowed error rate and windows are calculated accurately |
| Multi-window | Thresholds and paired conditions have been tested |
| Denominator | Low/zero traffic and minimum event counts are handled |
| Actionability | Recipient, action, and runbook exist |
| Severity | Page/ticket/info matches impact level |
| Noise control | Scoped grouping/dedup/suppression is configured |
| Diagnosis | Cause-metric dashboards and deploy context are linked |
| Privacy | Alerts contain no unnecessary secrets/PII |
| Resilience | Telemetry pipeline and alert routing are tested |
| Review | Post-incident rule tuning process exists |

## 18. Illustrative ADR — Burn-Rate Alerts for Booking API

> **Context:** Booking API has a 99.9% availability SLO over a rolling 30-day window. Traffic varies by hour. Current CPU alerts generate frequent pages that do not directly reflect booking experience.
>
> **Option A:** Page when CPU exceeds 80% for 5 minutes. Simple to configure and useful for capacity, but can page while SLOs remain met or miss dependency failures.
>
> **Option B:** Use request-based availability and latency SLIs with multi-window burn-rate alerts; keep CPU/DB/cache as cause alerts.
>
> **Illustrative decision:** Choose Option B. Apply fast burn-rate policies for the Tier 0 booking flow; slower thresholds for reporting. Route cause alerts to dashboards/tickets unless there is an imminent outage risk.
>
> **Alert payload:** service, SLO, burn rate, error ratio/count, short/long windows, region, endpoint, dashboard, runbook, and owner.
>
> **Mitigation:** pause risky rollouts, roll back if clearly correlated, cap concurrency, or switch to an approved fallback; monitor SLIs after action.
>
> **Verification:** inject 5xxs, latency, low traffic, zero traffic, metric gaps, duplicate series, and traffic bursts; verify pages fire only under agreed conditions.
>
> **Review triggers:** SLIs fail to represent user journeys, high false positives, or significant changes in workload/traffic patterns.

## 19. Hands-On Exercise: Alerting When Booking API Burns Error Budget

The Booking API has:
- 99.9% availability SLO over 30 days.
- Latency SLO: 99% of search requests complete under 300 ms.
- Normal traffic is 2,000 requests/second, dropping below 20 requests/second late at night.
- CPU normally fluctuates between 40% and 85%.
- Payment confirmation is a separate workflow that can fail even while the search API remains healthy.

An existing rule pages whenever CPU exceeds 80% for 5 minutes. During a campaign, CPU hits 88% while the availability SLO stays green. Another night, CPU is only 35%, yet payment confirmations time out at 8% for 10 minutes.

**Requirements:**
1. Define separate symptom SLIs for search, booking commit, and payment confirmation.
2. Calculate the allowed error ratio for a 99.9% SLO.
3. Calculate burn rates at 1%, 2%, and 8% error ratios.
4. Design multi-window burn-rate policies for severe incidents and slow degradation.
5. Handle low-traffic/zero-traffic periods to avoid false-healthy states.
6. Classify CPU, DB connections, and payment latency into cause alerts.
7. Design page/ticket routing and alert payloads.
8. Propose mitigations and release policies during rapid budget consumption.
9. Design a synthetic probe for payment confirmation without creating real transactions.
10. Choose metrics to evaluate alert quality after 30 days.

### Solution Guidance

- Separate SLIs by workflow. Search measures success and latency; booking commit measures accurate transaction completion; payment confirmation measures confirmation outcomes per provider/application semantics.
- A 99.9% SLO has an allowed error ratio of 0.1% (0.001).
- At 1% error ratio, burn rate = 1% / 0.1% = 10.
- At 2%, burn rate = 20.
- At 8%, burn rate = 80.
- During low traffic, combine minimum event counts, longer windows, and synthetic checks; zero traffic during hours when requests are expected can itself be a distinct symptom.
- CPU at 88% is a cause/capacity signal; if SLIs stay green, paging is unnecessary. An 8% payment timeout is a payment workflow symptom requiring a page even when CPU is low.
- Alert payloads include workflow, SLI/SLO, burn rate, failed count, short/long windows, region, provider, recent deploys, dashboard, and runbook.
- Mitigations include rolling back related changes, reducing concurrency, budgeted retries, circuit breakers, or switching to manual review/fallback per business policy.
- Synthetic payment checks should use a sandbox or provider test mechanism; any production probe must use a safe authorization/verification path without creating real charges.
- Review page actionability, false positives, duplicate alerts, MTTD, MTTA, MTTC, budget consumed, and missed incidents.

### Self-Check Questions

1. How does a metric differ from an SLI?
2. Why is CPU not an availability SLI?
3. What is the error budget for a 99.9% SLO?
4. What does a burn rate of 10 mean?
5. Why are multi-window alerts better than a single short window?
6. Which assumptions underlie the budget-consumed calculation?
7. When should an alert page vs. open a ticket?
8. How do you distinguish a symptom alert from a cause alert?
9. Why does low traffic make error ratios unstable?
10. What does synthetic monitoring add to real-user monitoring?
11. How do you avoid alert storms when a dependency fails?
12. How should error budgets influence release policies?

Effective alerting starts from what users need to accomplish and the quality commitments a service has set. SLIs/SLOs define good vs. failed; error budgets quantify allowable failures; burn rates reveal how fast the budget is being spent. Combining multi-window alerts, cause telemetry, clear ownership, and runbooks helps operations teams respond promptly, cut alert fatigue, and make data-driven reliability decisions.
