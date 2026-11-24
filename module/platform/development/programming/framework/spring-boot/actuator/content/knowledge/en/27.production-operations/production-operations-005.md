# Choosing Alerts with Clear Time Windows and Handling Instructions

## 1. Alerts Must Lead to a Decision

In production operations, a metric crossing a threshold is not enough to page the on-call engineer. A useful alert must state **which service is affected, over what window the signal went bad, who owns it, and what the recipient should do next**. If every small fluctuation generates a notification without a clear action, on-call responders will struggle to spot critical incidents.

Start from user-impacting symptoms: failed request rate, latency failing to meet objectives, critical jobs failing to complete, or queues lagging enough to breach deadlines. CPU or thread counts are diagnostic evidence; they should only directly wake an on-call responder when there is a corresponding reason and action. [Prometheus alerting principles](https://prometheus.io/docs/practices/alerting/).

This article uses the illustrative `orders` service, Spring Boot Actuator/Micrometer as the metrics source, Prometheus for condition evaluation, and Alertmanager for notification routing. The 5% threshold, 5-minute window, and 2-minute duration are choices for the lab exercise, not optimal settings for every production environment.

Chain of responsibility to understand:

```text
Application records metrics
  → Prometheus scrapes samples and evaluates expressions over time
  → Rule transitions state inactive / pending / firing
  → Alertmanager groups, routes, and sends notifications
  → Owner uses runbook to verify, mitigate impact, and monitor recovery
```

The **time window** determines which data is used for measurement. The **condition hold duration** determines when a rule qualifies for firing. The **notification schedule** determines when the on-call responder receives the message. The **runbook** is the evidence-based handling guide. These four components must align with each other.

## 2. Selecting Signals and Response Levels

Before writing PromQL, fill out a short contract for each alert:

| Component | Question to answer | Example |
| --- | --- | --- |
| Impact | What are users unable to do? | A portion of order requests return HTTP 5xx |
| Scope | Which environment, service, and business group? | `job=orders`, `env=prod` |
| Measurement | What are the numerator, denominator, unit, and excluded data? | 5xx rate / total HTTP request rate, excluding Actuator |
| Timing | Over what window is it measured, how often evaluated? | 5m window, evaluated every 30s |
| Threshold | Why does this number indicate actionable impact? | Over 5%, traffic at least 1 request/second in the example |
| Owner | Which team receives and owns it? | Orders team |
| Action | What first step does the responder take? | Check error scope, recent changes, and related dependencies |
| Recovery | What proves the incident is over? | Metrics are fresh, error rate dropped, and business check succeeds |

Distinguish response levels:

- **Page:** requires prompt response, has serious impact or risk, and has an accountable on-call responder.
- **Warning/ticket:** requires investigation but does not necessarily wake an on-call responder immediately, e.g., losing metrics from one instance while the service still operates.
- **Dashboard/log:** supports observation and root-cause analysis; not every change needs a notification.

`severity` is a team-defined label; setting `severity: page` does not automatically place a call or send a message. Alertmanager must have a matching route and receiver.

Do not average instance error rates equally. An instance with 1 error/1 request does not carry the same weight as an instance with 1 error/10,000 requests. Sum the error counts/rates and divide by the sum of request counts/rates within the same scope.

## 3. Do Not Confuse Time Parameters

| Parameter | Role | Example |
| --- | --- | --- |
| `scrape_interval` | Interval between Prometheus scrapes | 15s |
| Window `[5m]` | Historical span included in each measurement evaluation | `rate(counter[5m])` |
| Rule evaluation interval | How often the condition is recomputed | 30s |
| `for: 2m` | Same label set must continue satisfying condition across evaluations for 2m | Pending before firing |
| `group_wait` | Wait to batch a new notification group | 30s illustrative |
| `group_interval` | Cadence to consider sending updates for an existing group | 5m illustrative |
| `repeat_interval` | Reminder interval when the group has not changed significantly | 4h illustrative |

`for` is not an averaging window. `rate(...[5m]) > 0.05` combined with `for: 2m` means the rolling-window measurement must keep satisfying the condition long enough; it does not mean "continuous errors for 7 minutes". A short but large error burst can still keep the 5m window ratio above the threshold for 2m. [Alerting rule semantics](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/).

Example with `up == 0` and `for: 2m`, without a `rate` window:

| Time | Input data | Expected state |
| --- | --- | --- |
| 0m | `up=1` | Inactive |
| 1m | `up=0` for the first time | Pending |
| 2m | Still `up=0` | Pending |
| 3m | Condition held for 2m | Firing |
| 4m | `up=1` | Stops firing unless configured to keep firing longer |

If the condition clears during the pending phase, the `for` timer must restart when it reappears. This is continuity of **expression results at evaluation timestamps**, not continuous observation at every instant between scrapes.

Parameters `group_wait/group_interval/repeat_interval` belong to Alertmanager; they do not alter PromQL windows or replace `for`. Delivery timing is also affected by grouping, routing, inhibition, silences, and delivery errors. Do not promise exact detection time by adding 5m + 2m + 30s. [Notification timing in Alertmanager](https://prometheus.io/docs/alerting/latest/configuration/).

Some versions support `keep_firing_for` to keep an alert firing after the condition no longer holds. That is an anti-flapping policy when closing an alert, not proof the service has recovered. The examples here do not use this option; check your tool version before adding it.

## 4. Confirming Actuator Metric Sources

For an existing Spring Boot web application, Actuator and the Prometheus registry are needed. In Gradle, use the dependencies managed by Spring Boot:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

Enable the needed endpoints in application configuration:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
```

Spring Boot records HTTP requests under the Micrometer name `http.server.requests`; Prometheus typically receives the counter `http_server_requests_seconds_count`. Verify actual metric names and labels at `/actuator/prometheus` because applications can customize them. `/actuator/metrics` is a diagnostic tool, not a historical store for rules to compute time windows. [Spring Boot 3.3 Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

This example assumes the `status` label holds the HTTP code and `uri` uses templated paths. Filtering `uri!~"/actuator.*"` excludes management paths with that prefix. If the application changes the base path or label names, update both numerator and denominator together.

`job` and `instance` are labels attached by Prometheus per scrape target. The `env` label in the example is declared in the scrape configuration; do not assume Spring Boot adds it automatically. `up=0` means the scrape failed, which does not by itself prove business logic failed or readiness is rejecting load. [Job, instance, and auto-generated series](https://prometheus.io/docs/concepts/jobs_instances/).

Minimal `prometheus.yml` file for local lab testing:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 30s
rule_files:
  - alerts.yml
scrape_configs:
  - job_name: orders
    metrics_path: /actuator/prometheus
    static_configs:
      - targets: ["127.0.0.1:8080"]
        labels:
          env: prod
```

The `prod` label here only simulates a production filter; the address is still the local machine. This configuration loads rules without declaring Alertmanager, so it is not a complete notification pipeline yet. The endpoint must be reachable under the application's authentication/network mechanisms; do not take a 401/403 scrape error as evidence that business requests failed.

## 5. A Rule Set with a Clear Contract

Save the following into `alerts.yml`. Three rules separate three questions: whether processed requests have a high error rate, whether one target can still be scraped, and whether the whole job still has `up` samples.

```yaml
groups:
  - name: orders-production
    interval: 30s
    rules:
      - alert: OrdersHigh5xxRatio
        expr: |
          (
            sum by (job, env) (
              rate(http_server_requests_seconds_count{
                job="orders", env="prod", status=~"5..",
                uri!~"/actuator.*"
              }[5m])
            )
            /
            sum by (job, env) (
              rate(http_server_requests_seconds_count{
                job="orders", env="prod", uri!~"/actuator.*"
              }[5m])
            )
          ) > 0.05
          and on (job, env)
          sum by (job, env) (
            rate(http_server_requests_seconds_count{
              job="orders", env="prod", uri!~"/actuator.*"
            }[5m])
          ) >= 1
        for: 2m
        labels:
          service: orders
          team: orders
          severity: page
        annotations:
          summary: "Orders has high HTTP 5xx rate"
          description: "5xx rate exceeds 5% over 5m, traffic at least 1 req/s, condition held for 2m."
          runbook_id: "orders-high-5xx"

      - alert: OrdersMetricsUnreachable
        expr: up{job="orders", env="prod"} == 0
        for: 2m
        labels:
          service: orders
          team: orders
          severity: warning
        annotations:
          summary: "Failed to scrape metrics from an Orders instance"
          description: "Scrape failed continuously for 2m; business service outage not yet concluded."
          runbook_id: "orders-metrics-unreachable"

      - alert: OrdersMetricsMissing
        expr: absent_over_time(up{job="orders", env="prod"}[5m])
        for: 1m
        labels:
          service: orders
          team: orders
          severity: warning
        annotations:
          summary: "Entire up series missing for Orders job"
          description: "No up samples in 5m window and missing-sample condition held for 1m."
          runbook_id: "orders-metrics-missing"
```

### 5.1. 5xx Ratio and Traffic Condition

The first rule computes the growth rate of each counter series with `rate` before summing. This preserves counter-reset handling per instance. Numerator and denominator share the same scope filters, except for the numerator's `status` condition. [Prometheus rate function](https://prometheus.io/docs/prometheus/latest/querying/functions/#rate).

`sum by (job, env)` aggregates instances, paths, and statuses within the same service/environment. `and on (job, env)` pairs the sufficient-traffic condition with the ratio for that exact scope. The comparison expression does not use `bool`, so it filters out elements not meeting the condition.

Do not change it to `ratio > bool 0.05` and use it directly as an alert: a result with value 0 is still an element present in the vector, whereas alerts evaluate element presence. If using intermediate boolean results, a proper final filter is required. [Comparisons and vector matching](https://prometheus.io/docs/prometheus/latest/querying/operators/).

One failed request out of one request is 100%, yet not necessarily enough evidence to page under the same policy as thousands of requests. The condition of at least 1 req/s reduces noise for this example; it also creates a blind spot for low-traffic services or when requests cannot reach the application. Those services need external synthetic checks, business signals, or a dedicated low-traffic policy.

Do not apply "every 4xx is a system error". If the business treats certain 4xx codes as service failures, define the appropriate good/bad request sets before writing rules. HTTP 5xx also does not reflect business errors accidentally returning 200 or errors occurring before requests reach the application.

### 5.2. No Data Differs from Zero Value

`OrdersMetricsUnreachable` only works when the `up` series still exists and has value 0. If a target is dropped from service discovery, the series may disappear; `up == 0` has no element left to fire an alert.

`OrdersMetricsMissing` checks for no `up` samples across the entire job within a 5m window and requires the condition to hold for 1m. It detects losing the entire job, not losing a single instance from the list while other instances still have samples. Checking each expected target requires a reliable inventory source to compare against. [absent_over_time function](https://prometheus.io/docs/prometheus/latest/querying/functions/#absent_over_time).

A flat counter, no 5xx series, and losing all metrics are three distinct cases. Do not replace all missing data with 0 to make dashboards green. These rules also cannot monitor Prometheus itself stopping evaluation; an independent monitoring path is needed for the alerting system.

## 6. Testing Windows and Alert Lifecycle

Valid syntax does not prove timing is right. Save the next file as `alerts.test.yml`. Mock data is sampled every 1m for readability; rules still evaluate every 30s. It does not replace the `scrape_interval=15s` value of the live example.

```yaml
rule_files:
  - alerts.yml
evaluation_interval: 30s
tests:
  - name: sustained-errors-and-recovery
    interval: 1m
    input_series:
      - series: "http_server_requests_seconds_count{job=\"orders\",env=\"prod\",instance=\"orders-1:8080\",uri=\"/orders\",status=\"200\"}"
        values: "0+540x10 6000+600x10"
      - series: "http_server_requests_seconds_count{job=\"orders\",env=\"prod\",instance=\"orders-1:8080\",uri=\"/orders\",status=\"500\"}"
        values: "0+60x10 600+0x10"
    alert_rule_test:
      - eval_time: 2m
        alertname: OrdersHigh5xxRatio
        exp_alerts: []
      - eval_time: 3m
        alertname: OrdersHigh5xxRatio
        exp_alerts:
          - exp_labels:
              job: "orders"
              env: "prod"
              service: "orders"
              team: "orders"
              severity: "page"
            exp_annotations:
              summary: "Orders has high HTTP 5xx rate"
              description: "5xx rate exceeds 5% over 5m, traffic at least 1 req/s, condition held for 2m."
              runbook_id: "orders-high-5xx"
      - eval_time: 10m
        alertname: OrdersHigh5xxRatio
        exp_alerts:
          - exp_labels:
              job: "orders"
              env: "prod"
              service: "orders"
              team: "orders"
              severity: "page"
            exp_annotations:
              summary: "Orders has high HTTP 5xx rate"
              description: "5xx rate exceeds 5% over 5m, traffic at least 1 req/s, condition held for 2m."
              runbook_id: "orders-high-5xx"
      - eval_time: 16m
        alertname: OrdersHigh5xxRatio
        exp_alerts: []
  - name: low-traffic-is-not-paged
    interval: 1m
    input_series:
      - series: "http_server_requests_seconds_count{job=\"orders\",env=\"prod\",instance=\"orders-1:8080\",uri=\"/orders\",status=\"500\"}"
        values: "0+1x15"
    alert_rule_test:
      - eval_time: 10m
        alertname: OrdersHigh5xxRatio
        exp_alerts: []
  - name: healthy-without-a-5xx-series
    interval: 1m
    input_series:
      - series: "http_server_requests_seconds_count{job=\"orders\",env=\"prod\",instance=\"orders-1:8080\",uri=\"/orders\",status=\"200\"}"
        values: "0+600x15"
    alert_rule_test:
      - eval_time: 10m
        alertname: OrdersHigh5xxRatio
        exp_alerts: []
  - name: zero-traffic-is-not-success-evidence
    interval: 1m
    input_series:
      - series: "http_server_requests_seconds_count{job=\"orders\",env=\"prod\",instance=\"orders-1:8080\",uri=\"/orders\",status=\"200\"}"
        values: "0+0x15"
      - series: "http_server_requests_seconds_count{job=\"orders\",env=\"prod\",instance=\"orders-1:8080\",uri=\"/orders\",status=\"500\"}"
        values: "0+0x15"
    alert_rule_test:
      - eval_time: 10m
        alertname: OrdersHigh5xxRatio
        exp_alerts: []
  - name: brief-scrape-failure-resets-pending
    interval: 1m
    input_series:
      - series: "up{job=\"orders\",env=\"prod\",instance=\"orders-1:8080\"}"
        values: "1 0 1 1 1"
    alert_rule_test:
      - eval_time: 2m
        alertname: OrdersMetricsUnreachable
        exp_alerts: []
      - eval_time: 3m
        alertname: OrdersMetricsUnreachable
        exp_alerts: []
  - name: sustained-scrape-failure-and-recovery
    interval: 1m
    input_series:
      - series: "up{job=\"orders\",env=\"prod\",instance=\"orders-1:8080\"}"
        values: "1 0 0 0 1"
    alert_rule_test:
      - eval_time: 2m
        alertname: OrdersMetricsUnreachable
        exp_alerts: []
      - eval_time: 3m
        alertname: OrdersMetricsUnreachable
        exp_alerts:
          - exp_labels:
              job: "orders"
              env: "prod"
              instance: "orders-1:8080"
              service: "orders"
              team: "orders"
              severity: "warning"
            exp_annotations:
              summary: "Failed to scrape metrics from an Orders instance"
              description: "Scrape failed continuously for 2m; business service outage not yet concluded."
              runbook_id: "orders-metrics-unreachable"
      - eval_time: 4m
        alertname: OrdersMetricsUnreachable
        exp_alerts: []
  - name: target-disappears-from-discovery
    interval: 1m
    input_series:
      - series: "up{job=\"orders\",env=\"prod\",instance=\"orders-1:8080\"}"
        values: "1 1 stale _ _ _ _ _ _"
    alert_rule_test:
      - eval_time: 5m
        alertname: OrdersMetricsMissing
        exp_alerts: []
      - eval_time: 7m
        alertname: OrdersMetricsMissing
        exp_alerts:
          - exp_labels:
              job: "orders"
              env: "prod"
              service: "orders"
              team: "orders"
              severity: "warning"
            exp_annotations:
              summary: "Entire up series missing for Orders job"
              description: "No up samples in 5m window and missing-sample condition held for 1m."
              runbook_id: "orders-metrics-missing"
      - eval_time: 7m
        alertname: OrdersMetricsUnreachable
        exp_alerts: []
      - eval_time: 7m
        alertname: OrdersHigh5xxRatio
        exp_alerts: []
```

### 6.1. Running Tests

Use `promtool` with the same version as the Prometheus expected to load the rules; this example set was tested with promtool 3.2.1. You do not need to start Prometheus, the Java application, or send notifications to run these unit tests.

On Linux/macOS, when `promtool` is in PATH:

```shell
promtool check config prometheus.yml
promtool check rules alerts.yml
promtool test rules alerts.test.yml
```

On PowerShell, if `promtool.exe` is in the current directory:

```powershell
.\promtool.exe check config prometheus.yml
.\promtool.exe check rules alerts.yml
.\promtool.exe test rules alerts.test.yml
```

Rule check output:

```text
Checking alerts.yml
  SUCCESS: 3 rules found
```

Test file run output:

```text
  SUCCESS
```

The commands must return exit code 0. Tests verify both expected labels and annotations, so changing description text or owner team requires intentionally updating expectations. How data is declared and rules are tested is described in [Prometheus unit testing documentation](https://prometheus.io/docs/prometheus/latest/configuration/unit_testing_rules/).

### 6.2. Reading the Seven Scenarios

| Scenario | Expected evidence |
| --- | --- |
| Sustained errors then recovery | Not firing at 2m; firing at 3m and 10m; resolved by 16m |
| Low traffic | Even if all requests fail, does not page under this traffic-gated policy |
| No 5xx series | Only good requests does not fire an error-rate alert |
| No requests | Does not fire ratio alert; do not interpret as proof of healthy service |
| Brief scrape failure | Pending interrupted, does not fire |
| Sustained scrape failure | Still pending at 2m, firing at 3m, recovered at 4m |
| Target disappears | Missing-samples rule fires; `up == 0` rule cannot replace it |

`0+540x10` represents 11 samples starting from 0 and increasing by 540 per minute. Alongside the error series increasing by 60/min, that is 600 requests/min, of which 10% are 5xx. After the error phase, the 5xx series stays flat while successful requests keep rising to test recovery.

`stale` represents a series that is no longer current; `_` represents a missing sample. In the final scenario, the last real `up` sample is at 1m. By 6m, the 5m window no longer contains that real sample; after `for: 1m`, the test checks firing at 7m. This is not a guarantee to "always wait 6 minutes from Prometheus startup": if newly started with no prior history, the missing-sample expression can immediately evaluate true. Initialization/maintenance policies must be defined separately.

The seven test groups have 16 check points in total. They verify math, labels, annotations, and firing states at selected timestamps; they do not prove real service discovery, actual scraping, Alertmanager routes, or that the on-call engineer received the page. The notification path needs a separate integration test in a test channel, with defined recipients and content.

## 7. Runbooks Must Specify the Next Step

In the example, `runbook_id` points to the three guides right below. When putting them into your team's system, store them where on-call responders can access them and add `runbook_url` with an actual link. Do not attach a URL that merely looks like documentation but has no content or cannot be read by on-call responders.

### 7.1. `orders-high-5xx` — High Error Rate

**Owner:** Orders team; current on-call responder receives and handles it. **Severity:** page under the example policy. **Meaning:** in `job=orders, env=prod`, HTTP 5xx rate over a 5m window exceeds 5%, with traffic at least 1 request/second, and the expression holds for 2m.

**First steps, within 5 minutes of acknowledging:**

1. Record start time, alert labels, and affected user scope. Check whether there are alerts from the gateway/external callers; do not look only at application self-reporting.
2. Open the same time range on the dashboard. Inspect the 5xx numerator, total traffic, and ratio separately. Verify samples are fresh and expected targets are still scraped.
3. Break down by path, status, and instance to see whether errors are isolated or widespread. Cross-check deployment times, configuration changes, and dependency incidents.
4. Check a representative business operation. Prefer read operations or appropriate test accounts; do not repeat actions that could create duplicate orders/transactions just to confirm an error.

Diagnostic expression you can run in Prometheus:

```promql
sum by (instance, uri, status) (
  rate(http_server_requests_seconds_count{
    job="orders", env="prod", status=~"5..", uri!~"/actuator.*"
  }[5m])
)
```

This is an error rate to locate scope, not an error ratio and not a replacement for the main rule. Add only dimensions with bounded cardinality; do not create labels by user ID, order ID, or URLs containing identifiers.

**Choosing actions based on evidence:**

| Evidence | Next action |
| --- | --- |
| Errors started after a release and concentrate on the new version | Cross-check changes; roll back per established procedure only after confirming data/config compatibility and that the previous version remains suitable |
| Multiple instances fail together calling a dependency | Verify the dependency, escalate to its owning team; use a pre-designed fallback if it meets business requirements |
| Pool/connection/threads saturated | Identify the bottleneck before increasing load or instance count; adding app instances may overload the dependency further |
| Only one path fails | Prioritize that scope; check error codes, inputs, and related version instead of changing the whole system |
| Root cause not identified after 5 minutes or impact grows fast | Escalate to Orders shift lead/incident commander with time, scope, metrics, and steps already tried |

Do not use a mass restart as a default step: it can destroy evidence and fail to resolve a shared root cause. Every mitigation change needs an owner, execution timestamp, post-change measurement, and a rollback plan if things worsen.

**Recovery confirmation criteria:**

- Metric samples are fresh and expected scrape targets still exist.
- 5xx rate dropped while sufficient traffic exists to evaluate; business checks work.
- No independent signal indicates the gateway or users are still seeing errors.
- Monitor for at least 10 more minutes in this lab exercise; production must choose a duration based on service risk and load cycles.

The rule stopping firing is not enough: it may stop because total traffic fell below the minimum condition or data disappeared. If traffic vanished along with errors, switch to investigating external access/metrics pipeline instead of concluding healthy.

After the incident, record timeline, root cause, effective actions, and improvements needed in rules/runbooks. Do not raise thresholds just to reduce pages without assessing missed impact.

### 7.2. `orders-metrics-unreachable` — Scrape Failure

**Owner:** Orders team, coordinating with the monitoring platform team if the failure is in the collection pipeline. **Severity:** warning in the example; escalate if observability loss is critical or there is evidence business functionality also broke.

1. Confirm the affected `instance` and inspect the scrape error on Prometheus's Targets page.
2. Distinguish connection/timeout errors, 401/403 codes, wrong path, or invalid metric format. Test from the collector's network environment; a successful call from a personal machine does not prove the scrape path works.
3. Check application ports, endpoint config, auth/TLS changes, and saturation levels. Do not remove authentication just to make `up` turn 1.
4. Cross-check business requests and remaining instances. If users are impacted, switch to the appropriate error-rate/unreachable runbook rather than fixing only the dashboard.
5. Hand off to the network/monitoring owning team once the issue is confirmed in that layer, with target, timestamp, and exact scrape error.

**Recovery:** `up=1` across consecutive scrapes, required metrics actually return, and data is fresh. In the lab, at least three successful scrapes can be used; production monitoring duration must be agreed upon by the team. A single HTTP 200 without business metrics has not completed observability recovery.

### 7.3. `orders-metrics-missing` — Entire Job Has No Samples

**Owner:** Orders team coordinating with the monitoring team. **Meaning:** no `up` samples for the entire job/environment filter in the selected window; not a conclusion that all servers are down.

1. Check whether the job is still in configuration and service discovery, whether `job/env` labels changed, and whether Prometheus is evaluating rules normally.
2. Compare expected instance count against the inventory/deployment source. Distinguish intentionally stopped services from targets lost from discovery.
3. If remote write or an intermediate query layer exists, check data lag and label filters right where rules execute. Data in another Prometheus does not automatically appear where evaluation runs.
4. Verify business functionality via an independent path; if both observability and serving paths fail, escalate per incident policy.
5. Fix the proven configuration/pipeline issue, then confirm both the target list and metric series have returned.

**Recovery:** full target count per inventory, fresh `up` samples, and updated business metrics. Any single series appearing so `absent_over_time` stops matching does not prove all expected instances are restored.

## 8. Choosing Windows Aligned with Risk

Short windows react quickly but are prone to oscillation; long windows smooth data but can detect slowly and stay bad after an incident ends. Increasing `for` indefinitely to cut noise can also delay serious incidents. Test against realistic load and failure shapes, not just a linear ramp.

| Scenario | Selection direction |
| --- | --- |
| Clear user errors and high request volume | Window short enough to react, with an impact-linked threshold |
| Very low-traffic service | Do not rely solely on ratios; add external synthetic/business checks |
| Batch job running every few hours | Base on latest completion and business deadline, do not page on zero HTTP rate |
| Approaching capacity exhaustion | Estimate time remaining and actionable scaling/cleanup steps |
| Lost measurement path | Alert on data/pipeline quality separately from performance alerts |

If a reliability objective (SLO) already exists, alerts can be based on error budget consumption speed (burn rate). With a 99.9% objective, the allowed error ratio is 0.001; if actual error ratio is 1%, burn rate equals `0.01 / 0.001 = 10`. This is a comparison against the budget, not "10% errors".

A policy may require the same burn-rate threshold on a long window to confirm significant consumption and a short window to confirm the incident is still ongoing. That differs from using one window plus `for`. Choose window pairs, thresholds, and page/ticket levels based on SLO, response cost, and traffic; do not replace the illustrative 5% rule with a copied number without defining good/bad event sets. [Google SRE: alerting on SLOs](https://sre.google/workbook/alerting-on-slos/).

For latency, clearly specify whether the objective is average, percentile, or percentage of requests meeting a deadline. Do not average per-instance p95s as service-wide p95. Choose appropriate histogram data and verify sufficient samples before setting percentile alerts; naming a window "5m" does not make a low-sample measurement reliable.

## 9. Keeping Notifications Low-Noise Without Hiding Incidents

- Keep routing/identity labels stable: environment, service, team, severity, and actionable scope. Put measured values, long descriptions, and runbook links into annotations. Continuously changing values in labels can create new alerts and break `for` continuity.
- Group by shared action scope, e.g. `alertname, job, env`; do not group production and test environments into one contextless notification.
- Use inhibition when a root incident explains secondary alerts, with sufficiently narrow label filters. Do not suppress independent user-impact signals just because CPU is high.
- Silences need scope, owner, reason, and expiration. A silence does not fix a condition, turn firing into recovery, or replace incident tracking.
- Monitor the alerting pipeline itself: successful evaluations, input data, Prometheus, Alertmanager, and delivery outcomes. You cannot rely solely on a system to self-report when it stops running.

In this article, notification grouping timings only explain roles. Testing a real delivery path requires receiver config, a test channel, and evidence of successful receipt. A passing PromQL unit test does not prove an on-call responder received a page.

## 10. Checks Before Promoting Rules to Operations

1. Cross-check metric names, data types, labels, and scope against actual scrapes; confirm numerator/denominator measure the same request set.
2. Run syntax checks and test threshold, pending, firing, recovery, low-traffic, and missing-data conditions. Add counter-reset, multi-instance, and per-path error cases when applying to a real service.
3. Evaluate against historical load data and an observation period with an owner to learn notification count, detection speed, and missed incidents. Choose an observation length covering key load cycles.
4. Test routes/receivers using a defined test channel; confirm the right receiving team, timing, content, and recovery notifications when configured.
5. Have an on-call engineer walk through the runbook without verbal explanation from the author. Fix any step missing conditions, unreachable links, or vague exit criteria.
6. Change thresholds/windows only after stating the impact on noise, detection time, and blind spots; record changes alongside test results.

## 11. Practice Exercises

1. Replace `for: 2m` with `for: 3m` and predict the firing timestamps of the two rules with a 2m hold duration before running tests. Do not edit tests just to pass; re-explain the timing contract.
2. Add a short error burst into data with sufficient history. Check how long the 5m ratio stays above threshold and whether `for` prevents firing.
3. Add two instances with sharply unequal traffic. Compare the ratio computed from sums with the average of the two ratios and choose the result reflecting user impact.
4. Create a scenario where only one instance disappears from discovery. Show that the whole-job missing rule does not detect it, then design a comparison against an expected inventory source.
5. Read the three runbooks and note what data must be gathered before each mitigation action. Test a scenario where the ratio alert stops firing because traffic drops to 0 to avoid a false recovery conclusion.

A quality alert connects measurement, time window, action, and recovery criteria. When recipients understand why they were called and can start investigating with concrete evidence, alerting fulfills its true role in production operations.
