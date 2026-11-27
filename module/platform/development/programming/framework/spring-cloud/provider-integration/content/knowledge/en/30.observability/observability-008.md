# Designing alerts tied to service quality and remediation

## 1. Context and objectives

In the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, we practice integrating Spring Boot with managed services from **AWS, Azure, and Google Cloud** using the corresponding Spring Cloud libraries and SDKs. Once an application runs in the cloud, metrics, logs, and traces become truly useful only when they help operations teams recognize degraded service quality, understand its impact, and act promptly.

An alert such as “CPU above 80%” can be helpful in certain cases, yet it says nothing about whether users are encountering errors. By contrast, an alert stating “request error rate exceeds SLO budget and is burning error budget at 14x” ties directly to service quality and urgency.

This lesson explains how to design alerts grounded in **Service Level Indicators (SLIs), Service Level Objectives (SLOs), error budgets, and burn rates**. We then apply these principles across Prometheus/Alertmanager, Amazon CloudWatch, Azure Monitor, and Google Cloud Monitoring.

After this lesson, you will be able to:

- Select SLIs reflecting availability, latency, throughput, and asynchronous processing quality.
- Define request-based or time-window SLOs and calculate error budgets.
- Calculate burn rates and design fast-burn/slow-burn alerts.
- Write alert rules with sustained evaluation windows, severity, owner, and runbooks.
- Reduce alert noise via grouping, inhibition, composite conditions, and maintenance windows.
- Map the same SLO across CloudWatch, Azure Monitor, and Google Cloud Monitoring.
- Test alerts, run incident drills, and refine thresholds using real telemetry.

## 2. Good alerts start from user experience

An alert should answer four questions:

1. **What is degrading?** Availability, latency, message age, backlog, or a specific business flow.
2. **Who is affected and what is the scope?** One operation, one region, one dependency, or the whole service.
3. **How urgent is it?** Are users seeing errors right now, or is the error budget eroding gradually?
4. **What should the responder do?** Which dashboard to inspect, which runbook to follow, which team to contact, and when to escalate.

Example of a poor alert:

~~~text
CPU > 80%
~~~

This carries no service name, sustained duration, user impact, or remediation steps.

Example of a better alert:

~~~text
Service: document-api
Signal: availability SLO burn rate
Condition: burn rate > 14.4 over 1-hour and 5-minute windows
Severity: page
Impact: 30-day error budget is exhausting rapidly
Owner: team-document-platform
Runbook: /runbooks/document-api/availability
~~~

CPU remains valuable as a diagnostic signal or saturation alert, yet it should page only when evidence shows it threatens serving capacity or demands immediate intervention.

## 3. Distinguishing SLI, SLO, SLA, and error budget

| Concept | Meaning | Example |
|---|---|---|
| **SLI** | Quantitative measure of actual service quality | Successful request ratio, p95 latency |
| **SLO** | Target quality objective over a time window | 99.9% successful requests over 30 days |
| **SLA** | Customer-facing commitment, typically carrying contractual consequences | 99.5% monthly availability |
| **Error budget** | Allowable unreliability while still meeting the SLO | 0.1% permitted failing requests for a 99.9% SLO |

An SLO is an internal reliability management tool; an SLA is an external commitment to customers. SLOs are typically set stricter than SLAs so engineering has room to act before breaching contractual terms.

An error budget does not mean teams are encouraged to cause errors. It quantifies remaining risk allowance within an evaluation period. When the budget runs low, teams can slow risky changes, prioritize reliability work, or tighten release gates.

## 4. Choosing the right SLIs for Spring Boot applications

Avoid forcing one SLI onto every system. Select indicators based on what users or dependent systems genuinely require.

### 4.1. Availability

Define a good request as one handled successfully per contract. For example:

\[
Availability = \frac{GoodRequests}{EligibleRequests}
\]

For HTTP APIs, 2xx and certain 3xx responses may count as successful depending on contract; 5xx responses are typically service failures. Client-induced 4xx responses from invalid user input are usually excluded from service availability failures. However, certain 4xx codes like 429 from service rate-limiting may warrant a dedicated SLI if users cannot complete tasks.

Keep definitions consistent across metrics, SLOs, and dashboards. Never let one service treat 429 as a failure while another silently ignores it without clear documentation.

### 4.2. Latency

A latency SLI can be the ratio of requests completing within a threshold:

\[
LatencySLI = \frac{GoodRequestsWithinThreshold}{EligibleRequests}
\]

Example: 99% of document GET requests complete under 300 ms over 30 days.

Do not rely solely on average latency because a small tail of very slow requests can stay hidden. Use histograms to track p95/p99 or the fraction of requests meeting an SLO latency threshold.

### 4.3. Throughput and saturation

Throughput (requests/second, messages/second) and saturation (CPU, memory, thread pools, connection pools, queue capacity) are typically diagnostic signals or capacity alerts. They become SLIs when rate or intake capacity is explicitly part of the contract—for example, an API committed to handling at least 500 transactions/second.

Avoid setting SLOs like “CPU below 70%” if users do not care directly about CPU numbers. Tie saturation to request latency, error rate, or backlog.

### 4.4. Asynchronous flows

For message-processing workers, appropriate SLIs include:

- Ratio of jobs completing successfully.
- Ratio of jobs completing within the business deadline.
- Age of the oldest unprocessed message.
- Ratio of messages routed to the DLQ.
- Elapsed time from job acceptance until results are ready.

With queues, “message accepted by broker” does not equal “business work completed”. If users wait for a preview result, measure from when the API accepted the job until the preview is ready.

## 5. Defining good events and eligible events

Before computing an SLI, define both denominator and numerator:

- **Eligible event:** a request/job qualified to count in the SLI.
- **Good event:** an eligible event meeting the quality criterion.
- **Bad event:** an eligible event failing the quality criterion.

Example availability SLI for the document API:

| Case | Eligible? | Good? |
|---|---:|---:|
| GET returns 200 | Yes | Yes |
| GET returns 500 due to application bug | Yes | No |
| GET returns 503 due to unavailable dependency | Yes | No |
| GET returns 404 for nonexistent document | Yes | Per contract; typically a valid response |
| POST returns 400 for malformed payload | Potentially yes | Per contract; usually not an availability error |
| Internal health check | Usually no | Not applicable |
| Request blocked at WAF before reaching service | Depends on SLO and measurement boundary | Do not automatically count as app error |

Do not exclude every error response from the denominator merely because it is 4xx. Clearly separate caller errors, quota/rate-limit errors, auth errors, and service errors. If requests are rejected by product policy, consider a dedicated SLI for legitimate rejection rates.

For latency SLIs, failed requests may be treated as bad events without waiting for successful completion latency. Avoid counting only successful requests in the denominator, because during heavy failures a latency SLI could look artificially healthy.

## 6. Calculating SLOs and error budgets

For request-based SLOs:

\[
ErrorBudget = 1 - SLOGoal
\]

Permitted bad events during the window:

\[
AllowedBadEvents = EligibleEvents \times ErrorBudget
\]

For example, a service with 99.9% availability over 30 days receiving 2,000,000 eligible requests:

\[
ErrorBudget = 1 - 0.999 = 0.001 = 0.1\%
\]

\[
AllowedBadEvents = 2,000,000 \times 0.001 = 2,000
\]

The service may incur up to roughly 2,000 bad requests in the evaluation period and still meet its SLO.

For time-based SLOs, if the target is 99.9% healthy minutes:

\[
AllowedBadTime = TotalTime \times (1 - SLOGoal)
\]

In 30 days there are 43,200 minutes:

\[
43,200 \times 0.001 = 43.2\text{ minutes}
\]

Request-based and time-based SLOs carry different semantics. A single high-traffic minute can contain thousands of bad requests yet count as just one bad minute in a time-based SLO. Pick the model matching user experience and how the service is measured.

## 7. Burn rate: error budget consumption speed

Burn rate measures the current error rate relative to the maximum sustainable error rate for the SLO:

\[
BurnRate = \frac{ObservedErrorRate}{AllowedErrorRate}
\]

With a 99.9% SLO, the allowed error rate is 0.1%.

| Observed error rate | Burn rate | Interpretation |
|---:|---:|---|
| 0.05% | 0.5x | Consuming slower than allowed budget pace |
| 0.1% | 1x | Consuming at the exact maximum pace to hit SLO |
| 0.5% | 5x | Budget depleting 5 times faster than sustainable |
| 1.44% | 14.4x | Budget depleting very rapidly |
| 5% | 50x | Severe incident if sustained |

A 1x burn rate does not imply good short-term quality; it means sustaining that error rate across the entire window would consume 100% of the error budget.

Estimated time to exhaust a 100% remaining budget:

\[
TimeToExhaustion \approx \frac{SLOWindow}{BurnRate}
\]

With a 30-day SLO and a 14.4x burn rate:

\[
30 / 14.4 \approx 2.08\text{ days}
\]

If part of the budget was already spent earlier, remaining time is shorter.

## 8. Multi-window, multi-burn-rate alerts

An alert checking only a short window can fire on brief spikes. An alert checking only a long window can detect outages too late. Combining two windows confirms that errors are both sizable and ongoing.

Example for a 99.9% SLO over 30 days:

| Tier | Long window | Short window | Suggested burn rate | Goal |
|---|---|---|---:|---|
| Fast burn | 1 hour | 5 minutes | 14.4x | Page quickly during severe incidents |
| Medium burn | 6 hours | 30 minutes | 6x | Page/urgent ticket depending on service |
| Slow burn | 24 hours | 2 hours | 3x | High-priority ticket or team alert |
| Very slow burn | 3 days | 6 hours | 1x | Track budget and plan improvements |

These are illustrative starting values based on a 30-day error budget. Adjust them to your SLO window, traffic profile, sensitivity, and team response capacity.

A multi-window condition typically takes the form:

~~~text
burn_rate_long_window > threshold
AND
burn_rate_short_window > threshold
~~~

Requiring both windows to match suppresses spikes that already ended before the alert fires. When traffic is very low, error ratios fluctuate sharply; add a minimum request-volume guard or use an appropriate time-based SLI.

## 9. Designing severity and notification channels

Not every alert warrants paging an on-call engineer.

| Severity | When to use | Typical channel | Expected response |
|---|---|---|---|
| SEV1 / page | Broad user impact, severe fast burn | On-call paging | Immediate response |
| SEV2 / urgent | Critical flow degraded, rapid budget burn without full outage | On-call/incident channel | Rapid response per policy |
| SEV3 / ticket | Slow burn, capacity risk, or errors with a workaround | Ticket/engineering queue | Handle during business hours |
| INFO | Deployments, threshold warnings, or signals to watch | Dashboard/chat | No immediate action required |

Base severity on impact, urgency, and blast radius. Do not page solely because an infrastructure metric crossed a threshold without a clear urgent action.

## 10. Alerts must include owner and runbook

A production alert should carry:

- **Stable name:** e.g., `DocumentApiAvailabilityFastBurn`.
- **Service/team:** who owns remediation.
- **Signal and condition:** which SLI, windows, and threshold.
- **Severity:** page, urgent, ticket, or info.
- **Summary:** short description readable on a phone screen.
- **Description:** current value, threshold, affected resource, and timestamp.
- **Runbook URL:** diagnostic and recovery steps.
- **Dashboard URL:** relevant charts/panels.
- **Escalation:** when to escalate to an incident commander or dependency team.

A runbook should guide responders through:

1. Confirm the alert is still firing and check when it began.
2. Identify the affected SLI/SLO, region, and operation.
3. Inspect recent deployments, traffic shifts, dependency latency, and error classes.
4. Use traces/logs to locate representative failing requests or jobs.
5. Apply controlled mitigation: rollback, disable a feature, throttle concurrency, or fail over if authorized by the runbook.
6. Verify the SLI recovers and error budget burn rate returns to safe levels.
7. Document timeline, root cause, and post-incident follow-ups.

If responders do not know what to do after reading an alert, redesign that alert.

## 11. Prometheus: SLI-based alert rules

Consider Spring Boot Micrometer metrics exported to Prometheus. Converted metric names are commonly `http_server_requests_seconds_count` and its histogram buckets; verify exact names at `/actuator/prometheus`. The `service` label in these examples must be populated via common tags or target relabeling; if absent, filter by a target label such as `job` or omit the service selector.

### 11.1. Availability error ratio

~~~promql
sum(rate(http_server_requests_seconds_count{
  service="document-api",
  status=~"5.."
}[5m]))
/
sum(rate(http_server_requests_seconds_count{
  service="document-api"
}[5m]))
~~~

This expression calculates the 5xx ratio over 5 minutes. In production systems, filter to eligible routes/operations, exclude health checks, and explicitly decide whether 429/4xx responses count as bad events.

### 11.2. p95 latency

~~~promql
histogram_quantile(
  0.95,
  sum by (le, uri) (
    rate(http_server_requests_seconds_bucket{
      service="document-api",
      uri!~"/actuator/.*"
    }[5m])
  )
)
~~~

Never put raw paths containing IDs into labels. Rely on URI templates provided by instrumentation so you do not generate separate alert instances per resource.

### 11.3. Illustrative alert rule

~~~yaml
groups:
  - name: document-api-slo
    rules:
      - alert: DocumentApiHighErrorRate
        expr: |
          (
            sum(rate(http_server_requests_seconds_count{
              service="document-api",
              status=~"5.."
            }[5m]))
            /
            sum(rate(http_server_requests_seconds_count{
              service="document-api"
            }[5m]))
          ) > 0.02
        for: 5m
        labels:
          severity: page
          team: document-platform
          service: document-api
        annotations:
          summary: "Document API error rate is above 2%"
          description: "5xx ratio has remained above 2% for 5 minutes."
          runbook_url: "https://runbooks.example/document-api/availability"
~~~

This example uses a static threshold to illustrate syntax. For production SLOs, prefer error-budget burn-rate alerts paired with minimum traffic guards to prevent firing on tiny sample sizes.

## 12. Prometheus: burn-rate alerts and Alertmanager

Suppose recording rules produce two series:

- `document_api:error_ratio:rate5m`
- `document_api:error_ratio:rate1h`

For a 99.9% SLO, the allowed error ratio is 0.001. Burn rate equals error ratio divided by 0.001.

~~~yaml
groups:
  - name: document-api-burn-rate
    rules:
      - alert: DocumentApiFastBurn
        expr: |
          (
            document_api:error_ratio:rate1h / 0.001 > 14.4
          )
          and
          (
            document_api:error_ratio:rate5m / 0.001 > 14.4
          )
        for: 2m
        labels:
          severity: page
          team: document-platform
          service: document-api
        annotations:
          summary: "Document API is burning its error budget rapidly"
          description: "1h and 5m error-budget burn rates are both above 14.4x."
          runbook_url: "https://runbooks.example/document-api/availability"
~~~

To avoid division by zero or alerts during zero traffic, recording rules should have valid denominators and can include a minimum request rate. Do not blindly append `or vector(0)` if doing so turns “missing data” into “zero errors”.

Alertmanager handles:

- **Grouping:** combining multiple alerts with the same service/cluster/alertname into a single notification.
- **Routing:** dispatching to the right team/on-call receiver based on labels.
- **Inhibition:** suppressing secondary alerts while a broader root-cause alert is firing.
- **Silence:** muting alerts temporarily during maintenance or active incidents.
- **Deduplication:** avoiding duplicate notifications for the same alert fingerprint.

Example routing configuration:

~~~yaml
route:
  receiver: platform-ticket
  group_by: [alertname, service, cluster]
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  routes:
    - matchers:
        - severity="page"
      receiver: document-oncall
    - matchers:
        - severity="ticket"
      receiver: document-platform-ticket
~~~

Receiver names reflect your environment's notification integrations, not default service names. Declare matching receivers in the `receivers` section and protect webhook/paging integration credentials.

## 13. Alerts for latency, traffic, and saturation

SLO alerts do not eliminate technical alerts. They complement one another:

| Signal | Question | Appropriate alert |
|---|---|---|
| Error ratio | Are users receiving errors? | Burn rate / error budget |
| Latency p95/p99 | Are requests slower than target? | Latency SLI burn rate |
| Traffic | Is traffic abnormal or missing altogether? | Traffic anomaly / no-traffic for services expecting steady traffic |
| Saturation | Are resources nearing exhaustion? | CPU, heap, thread pool, connection pool |
| Dependency | Is an external DB/storage/API slow or failing? | Dependency latency/error rate |
| Queue age/backlog | Are jobs waiting too long? | Oldest age, backlog growth, and job completion SLO |
| DLQ | Are failed messages piling up? | DLQ arrival rate/count/age |

Saturation alerts should usually be warnings/tickets while SLIs remain unaffected. When CPU, thread pools, and latency climb together, composite conditions or runbooks can prioritize response.

Do not apply one threshold across every workload. A 200 ms API latency can be normal for one service and severe for another. Set thresholds from actual SLOs and baselines.

## 14. AWS CloudWatch: alarms, composite alarms, and SLOs

CloudWatch supports metric alarms, anomaly detection, composite alarms, and SLOs via CloudWatch Application Signals.

### 14.1. Metric alarms

A metric alarm evaluates a metric or metric math expression against a threshold over evaluation periods. You can configure:

- Metric and dimensions.
- Statistic and period.
- Static threshold or anomaly detection band.
- Evaluation periods and datapoints to alarm (M-out-of-N).
- Missing data treatment.
- Alarm actions, such as an SNS topic.

M-out-of-N avoids alarming on a single outlier datapoint—for example, requiring 3 out of 5 datapoints above threshold before entering ALARM. Choose period and datapoint counts based on metric delay and required response time.

### 14.2. Composite alarms

A composite alarm combines child alarm states using AND/OR/NOT. Example:

~~~text
ALARM(DocumentApiHighErrorRate)
AND ALARM(DocumentApiHighLatency)
AND NOT ALARM(MaintenanceWindow)
~~~

Composite alarms cut notification noise and create aggregate health indicators. Child alarms remain useful for diagnostics; you can attach actions only at the composite level to avoid firing multiple notifications for one incident.

Composite alarms evaluate only the states of referenced alarms rather than computing metrics directly. Child alarms and composite alarms must meet CloudWatch account/region rules per AWS documentation.

### 14.3. Application Signals SLOs and burn rate

CloudWatch Application Signals lets you create service/operation SLOs based on latency or availability. You can choose request-based or period-based SLOs, track attainment/error budgets, and create burn-rate alarms with multiple lookback windows.

Burn rate:

\[
BurnRate = \frac{ObservedErrorRate}{1 - SLOGoal}
\]

For example, a 99.9% SLO has a baseline error rate of 0.1%. If the 1-hour error rate reaches 1.44%, the burn rate is 14.4x.

CloudWatch supports multi-window burn-rate alerting. One effective pattern pairs a longer and shorter window to confirm the fault is still active. Alarms can send SNS notifications or integrate into incident workflows depending on your environment.

### 14.4. Missing data and metric delay

Never treat missing data as zero by default. If an application stops publishing metrics, an alarm may need to transition to `INSUFFICIENT_DATA` or apply missing-data semantics intentionally. For low-traffic metrics, pair with a separate availability/heartbeat metric to distinguish idle services from broken exporters.

## 15. Azure Monitor: metric alerts, SLIs, and action groups

Azure Monitor supports metric alert rules, log search alerts, dynamic thresholds, multi-condition alerts, and action groups.

### 15.1. Metric alert rules

A metric alert rule defines:

- Target resource or resource scope.
- Metric and aggregation.
- Condition/threshold.
- Evaluation frequency and lookback window.
- Severity and description.
- Action group to send notifications or trigger automation.

Use static thresholds when SLOs are crisp, or dynamic thresholds when metrics exhibit seasonality backed by reliable historical baselines.

### 15.2. Dynamic thresholds

Dynamic thresholds learn patterns from metric history to identify anomalous bands, useful when traffic or CPU follows daily/weekly cycles. However:

- Sufficient historical data is required to learn baselines.
- After deployments or major traffic shifts, the model needs time to adapt.
- Dynamic thresholds detect deviations from history, not business SLOs.
- They do not replace burn-rate alerts when the goal is protecting error budgets.

### 15.3. SLIs/SLOs and fast/slow burn

Azure Monitor lets you define availability or latency SLIs, configure baseline targets (SLOs) and evaluation periods, and enable alerting. You can create:

- Baseline alerts when an SLI drops below SLO.
- Fast burn rate alerts to catch rapid error-budget depletion.
- Slow burn rate alerts to catch prolonged degradation.

Action groups define who gets notified and which automations execute when an alert fires. Enable the common alert schema so webhooks, Logic Apps, and Functions receive a consistent payload across alert types.

### 15.4. Dimension splitting and alert noise

Metric alerts can split by dimensions. Each dimension time series can generate separate alerts and incur separate charges. Split only on essential dimensions like `region` or `operation`; avoid splitting on unique IDs or dimensions irrelevant to remediation.

Alert processing rules can suppress or reroute notifications during maintenance windows. Always specify clear scopes and expiration times so production alerts are never accidentally silenced indefinitely.

## 16. Google Cloud Monitoring: SLO-based alerting policies

Cloud Monitoring supports alerting policies based on metric conditions or SLO service monitoring.

### 16.1. SLO burn-rate policies

Google Cloud Monitoring can create alerting policies driven by an SLO's burn rate. A burn rate greater than 1 means that if sustained across the compliance period, the service will miss its SLO.

You can configure two policy types:

- **Fast burn:** short window, high threshold; alerts on major incidents requiring rapid action.
- **Slow burn:** longer window, lower threshold; alerts on sustained degradation steadily draining the error budget.

Google's documentation offers illustrative starting points around 10x over a 1–2 hour lookback for fast burn and 2x over a 24-hour lookback for slow burn. These are not mandatory thresholds; tune them to your SLO, traffic, and response model.

Cloud Monitoring SLO burn-rate alerts currently enforce limits on compliance periods/lookbacks for certain selectors; documentation notes that compliance periods longer than 24 hours cannot be used with that burn-rate alert selector. When tracking a 28/30-day SLO, use shorter lookbacks to govern immediate alerting while monitoring the long-term budget on dashboards.

### 16.2. Notification channels and documentation

Alerting policies can notify email, Pub/Sub, webhooks, PagerDuty, or other supported channels. The documentation section should include:

- Summary of the firing condition.
- Affected service/SLO.
- Links to dashboards and trace/log queries.
- Remediation and escalation instructions.

A notification channel is only a delivery pipe. Test endpoints, permissions, and recipients before depending on them in production.

## 17. Alerting for message processing and cloud dependencies

In Spring Cloud Provider Integration, services may depend on SQS, Service Bus, Pub/Sub, S3, Blob Storage, databases, or external APIs. Separate API SLIs from asynchronous job SLIs.

Example for the preview pipeline:

| SLI | Example target | Alert |
|---|---|---|
| API acceptance availability | 99.9% of valid job requests accepted | Fast burn if API stops accepting jobs |
| Job completion availability | 99.5% of jobs complete successfully | Burn rate on job outcomes |
| Job completion latency | 99% of jobs complete within 2 minutes | SLO latency alert |
| Queue age | 99% of messages begin processing within 60 seconds | Fast/slow age alert |
| DLQ rate | Below 0.1% of jobs | Alert when arrival rate/count climbs |
| Storage dependency | 99.9% of read/write operations succeed | Dependency SLO or error-rate alert |

Do not page for every single message entering a DLQ if DLQ items are handled in scheduled batches. Page when the DLQ affects critical jobs, arrival rate spikes abnormally, or oldest DLQ age exceeds committed remediation windows.

If queue backlog grows while job completion SLOs still pass, a warning may suffice. If both backlog and oldest age climb together, job completion latency is about to breach and alert severity should escalate.

## 18. Alert fatigue, deduplication, and maintenance

Alert fatigue occurs when responders receive too many notifications lacking clear actions. A healthy alerting system should:

- Group alerts by service/cluster/region instead of alerting per instance.
- Deduplicate identical conditions.
- Inhibit secondary alerts when a broader root-cause alert already explains the outage.
- Enforce silences/maintenance windows with explicit expiration times.
- Use `for` / evaluation periods to filter out brief spikes.
- Page only when user impact or high risk demands immediate action.
- Separate notifications and incident creation from single raw metric alarms when appropriate.

Do not set `for` too long, delaying incident detection. Do not set it too short, causing flapping alerts. Pick durations aligned with scrape/export intervals, backend latency, and response times.

After every incident, review:

- Did the alert fire at the right time?
- Were any alerts redundant or delayed behind the root-cause alert?
- Did the runbook shorten time to recovery?
- Do thresholds reflect realistic SLOs?
- Can an infrastructure alert be replaced by a user-facing SLI?

## 19. Testing, drills, and operating alerts

Never wait for a production outage to discover whether alerts work.

### 19.1. Testing rules

With Prometheus, use `promtool test rules` to verify expressions and state-transition timing. With CloudWatch/Azure/Google, create test resources and feed sample metrics/queries to verify conditions, notification channels, and runbooks.

Verify:

- Alerts fire when the SLI breaches.
- Alerts stay quiet during short spikes under the sustained duration.
- Fast burn and slow burn trigger distinctly as intended.
- Zero-traffic periods follow explicit policy.
- Grouping/inhibition never hides independent incidents.
- Notifications reach the right team with dashboard and runbook links.
- Resolved notifications fire once conditions recover.

### 19.2. Incident drills

In staging:

1. Inject controlled dependency failures to elevate error rates.
2. Increase handler latency to push p95 past SLO.
3. Reduce consumer capacity so backlog and message age climb.
4. Verify fast-burn/slow-burn alerts and routing.
5. Have on-call follow the runbook, diagnose root cause, and restore health.
6. Confirm alerts resolve and error budget burn rate returns to normal.

Never inject intentional faults in production without an approved game-day procedure and bounded blast radius.

### 19.3. Monitoring the health of the alerting system itself

Measure the alerting pipeline itself:

- Alert delivery success/failure rate.
- Time from metric breach to notification delivery.
- Acknowledged alert ratio and false-positive rate.
- Off-hours pages requiring no action.
- Mean time from alert to acknowledge and mitigation.
- Incidents reported by users before any alert fired.

If users consistently report incidents before alerts fire, improve SLI definitions, thresholds, or telemetry coverage.

## 20. Summary

Alerting tied to service quality starts from **SLIs and SLOs**, not from a catalog of available metrics. Define good and eligible events, compute error budgets, monitor burn rates, and use multi-window alerts to distinguish critical incidents from gradual degradation.

Prometheus/Alertmanager provides rules, grouping, routing, inhibition, and silences. CloudWatch provides metric/composite alarms and SLO burn-rate alarms through Application Signals. Azure Monitor supports metric alerts, dynamic thresholds, SLI/SLO fast/slow burn, and action groups. Google Cloud Monitoring supports SLO-based burn-rate alerting policies paired with notification channels and documentation.

Every alert needs a severity, owner, clear condition, dashboard, and runbook. Test notifications, practice recovery drills, audit false positives, and measure alert delivery so alerts genuinely help operations protect user experience.

### Official references

- [Google SRE Workbook — Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/)
- [Google Cloud — Alerting on budget burn rate](https://docs.cloud.google.com/stackdriver/docs/solutions/slo-monitoring/alerting-on-budget-burn-rate)
- [Google Cloud — Creating an SLO alerting policy](https://docs.cloud.google.com/stackdriver/docs/solutions/slo-monitoring/ui/create-alert)
- [Prometheus — Alerting rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/)
- [Prometheus — Alertmanager](https://prometheus.io/docs/alerting/latest/alertmanager/)
- [Amazon CloudWatch — Service level objectives](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-ServiceLevelObjectives.html)
- [Amazon CloudWatch — Using alarms](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Alarms.html)
- [Amazon CloudWatch — Composite alarms](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/alarm-combining.html)
- [Azure Monitor — Create service level indicators](https://learn.microsoft.com/azure/azure-monitor/fundamentals/service-level-indicators-create)
- [Azure Monitor — Create metric alert rules](https://learn.microsoft.com/en-us/azure/monitoring-and-diagnostics/alert-metric)
- [Azure Monitor — Dynamic thresholds](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-dynamic-thresholds)
- [Azure Monitor — Alert types](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-types)
- [Azure Monitor — Common alert schema](https://learn.microsoft.com/en-us/azure/azure-monitor/platform/alerts-common-schema-definitions)
