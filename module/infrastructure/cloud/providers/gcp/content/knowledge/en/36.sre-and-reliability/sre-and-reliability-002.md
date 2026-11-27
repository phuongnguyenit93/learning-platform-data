# Defining SLIs and SLOs with Cloud Monitoring

A service can appear healthy from an infrastructure perspective yet still frustrate users: pages load slowly, checkout actions fail, or returned data is stale. To manage reliability based on real-world experience, operations teams must define what constitutes a good response, measure it with telemetry, and set verifiable targets.

In Site Reliability Engineering (SRE), a **Service Level Indicator (SLI)** measures service quality, a **Service Level Objective (SLO)** sets a target on an SLI over a period of time, and a **Service Level Agreement (SLA)** is a customer commitment that typically carries consequences or remedies if service levels are missed. Cloud Monitoring provides Service Monitoring and the SLO API to define SLIs, track SLO compliance, compute error budgets, and alert when the error budget is consumed too quickly.

In the CLOUD_PROVIDERS_GCP module, SLIs/SLOs connect services such as Cloud Run, GKE, Compute Engine, Cloud Load Balancing, and databases to operational workflows. A sound SLO system must reflect what users care about, rely on trustworthy metrics, define clear measurement scope, and tie into incident response and software release decisions.

After this lesson, you will be able to:

- Distinguish between SLI, SLO, SLA, and error budget.
- Select availability, latency, and business-quality SLIs from the user perspective.
- Distinguish between request-based SLIs and windows-based SLIs.
- Inspect metric type, metric kind, labels, and cardinality before using a metric in an SLO.
- Create services and SLOs in the Cloud Monitoring Console or via the Cloud Monitoring API.
- Calculate error budgets, monitor compliance, and configure burn-rate alerts.
- Use SLOs to prioritize reliability work, changes, and service improvements.

## 1. SLI, SLO, SLA, and Error Budget

### Service Level Indicator (SLI)

An SLI is a quantitative measurement of an aspect of service quality over a period of time. An SLI should be a strong proxy for user experience rather than merely reflecting server state.

Examples:

- Availability: the ratio of eligible requests processed successfully.
- Latency: the ratio of requests completed under a time threshold.
- Freshness: the ratio of data updated within an allowed timeframe.
- Correctness: the ratio of business outcomes matching defined criteria.
- Throughput: the ratio of work completed on time when the system is under load.

An SLI is commonly expressed as a ratio:

\[
SLI = \frac{\text{number of good serving units}}{\text{total number of eligible units}}
\]

For example, out of 100,000 eligible requests, 99,850 return a successful result:

\[
SLI_{availability} = \frac{99,850}{100,000} = 99.85\%
\]

SLIs can be viewed across multiple time windows depending on the decision being made: one hour for operational alerting, a few weeks for tactical decisions, and several months for long-term planning. Google Cloud recommends using 28 days as a starting point for measuring SLIs because it balances tactical and strategic needs.

The definition of "good" must align with the service contract. For a data-read API, HTTP 200 might indicate a good outcome; for an order-creation API, returning HTTP 200 when the order was not persisted is still a business failure. Choose measurement points close enough to the user experience to detect real issues.

### Service Level Objective (SLO)

An SLO is a performance target placed on an SLI over a **compliance period** (evaluation window). For example:

> Over every rolling 30-day window, at least 99.9% of profile read requests must succeed and at least 99% of requests must have latency under 300 ms.

These are two separate SLOs because availability and latency measure different dimensions. Cloud Monitoring models an SLO using an SLI, a goal, and a period. A service can have multiple SLOs to measure different aspects or user segments.

### Service Level Agreement (SLA)

An SLA is a service commitment agreed upon with customers or partners. An SLA may specify uptime percentages, exclusions, calculation methods, notification windows, and service credits if commitments are missed. An SLO is typically an internal operational target set strictly enough for engineering teams to detect risk before breaching the SLA.

Do not use SLO and SLA interchangeably. An SLO is an engineering operational tool; an SLA is a contractual commitment with conditions and consequences.

### Error Budget

The error budget is the share of service quality allowed to fall short while the SLO is still considered met. If the target is 99.9%, the error budget share is:

\[
Error\ budget = 1 - 0.999 = 0.001 = 0.1\%
\]

For a request-based SLI, if the compliance period has 1,000,000 eligible requests, the budget equals 1,000 bad requests. For a time-based SLI, a 99.9% SLO over 30 days equals roughly 43 minutes and 12 seconds of failure if measured as the proportion of good serving time.

The error budget provides a basis for balancing release velocity and reliability. When plenty of budget remains, the team can continue experimenting and releasing within agreed risk bounds. When the budget is burning quickly or exhausted, the team can prioritize bug fixes, reduce risky changes, and improve operational capacity.

## 2. Designing User-Meaningful SLIs

### Start from the Service Promise

Write down what the service promises users in business language before looking for metrics:

| User Promise | Measurable SLI |
|---|---|
| Users open the profile page and receive content | Ratio of successful profile requests |
| Users view the page within an acceptable time | Ratio of requests with latency under 300 ms |
| Orders are created and confirmed | Ratio of order-creation workflows completing successfully |
| Reports display up-to-date data | Ratio of reads where data age is under 10 minutes |
| Batch jobs start on schedule | Ratio of runs starting within 1 minute of schedule |

Do not pick a metric simply because it is already on a dashboard. CPU, memory, pod count, or instance count are useful for root-cause diagnosis, but they do not directly tell you whether users completed their tasks. Infrastructure metrics can serve as secondary signals or as SLIs for a specific infrastructure service if they align with that service's promise.

### Four Common Signal Categories

- **Availability:** requests or operations served successfully.
- **Latency:** requests served within a time limit.
- **Traffic:** volume of work submitted by users, helping interpret other SLIs.
- **Errors:** count or rate of errors; errors must be defined by user impact.

Traffic and errors often help explain shifts in availability/latency. They do not necessarily have to be standalone SLOs. A system may have multiple SLIs when users perform different types of work—for example, reads must be fast while writes must be accurate.

### Defining the Denominator and Exclusions

The denominator must include precisely the units the service is responsible for handling. Agree on:

- Whether internal requests, health checks, synthetic probes, and retries are counted.
- Whether requests with invalid user input count as service errors.
- At which measurement point client, gateway, or backend timeouts are counted.
- How canceled or incomplete requests are handled.
- Which endpoints, tenants, regions, or transaction types fall within SLO scope.

For example, HTTP 4xx errors caused by users submitting invalid data are usually not backend availability failures. However, if the service incorrectly returns 4xx due to a bug or misconfigured permissions, user experience is still affected. Define "good" criteria based on the endpoint contract and validate them against real-world scenarios.

### One SLI Should Measure One Dimension

Do not bundle availability and latency into a single ratio if the team needs to pinpoint causes clearly. One request might succeed slowly; another might fail very quickly. These two outcomes affect users differently and need separate SLIs.

If a product has multiple critical journeys, split SLIs by journey or request class. For example, a search API may require stricter latency than a report-export API. Grouping keeps targets aligned with expectations and prevents low-priority endpoints from masking issues on critical ones.

## 3. Choosing an SLI Type in Cloud Monitoring

Cloud Monitoring supports three ways to model an SLI in the SLO API:

| SLI Type | Calculation | When Appropriate |
|---|---|---|
| Basic SLI | Based on built-in metrics and definitions for certain service types | When the service type is recognized by Cloud Monitoring and has prebuilt availability/latency SLIs |
| Request-based SLI | Ratio of good requests to total requests in the compliance period | When each request is a unit of service and request-counting metrics exist |
| Windows-based SLI | Ratio of time windows meeting good criteria to total windows | When quality is evaluated by interval state, such as scheduled jobs or data freshness |

### Basic SLI

A Basic SLI uses prebuilt metrics for service types supported by Cloud Monitoring. According to Service Monitoring documentation, service types with built-in SLI metrics include Cloud Service Mesh, Istio on GKE, and App Engine. For other service types, verify the SLI options in the UI; in many cases, a custom SLI is required.

### Request-based SLI

A Request-based SLI measures the ratio of good requests to total requests:

\[
SLI_{request} = \frac{Good\ requests}{Total\ eligible\ requests}
\]

For example, a good request is one with an acceptable response code and latency under 300 ms. You can create separate availability and latency SLIs by applying different metric filters.

Metrics used for a request-based SLI must have a metric kind of `DELTA` or `CUMULATIVE`. `GAUGE` metrics cannot be used for request-based SLIs. If a metric stores a histogram or distribution, you can use a distribution cut to count observations within the good threshold.

### Windows-based SLI

A Windows-based SLI treats a time interval as good or bad according to configured criteria. For example, a 5-minute window is considered good if the success rate within that window reaches at least 99%. The final SLI is the number of good windows divided by the total eligible windows.

This type suits periodic processing services, batch jobs, freshness, or systems where users care whether an interval maintains required quality. Choose a window period suited to operational cycles and metric resolution; Cloud Monitoring requires a window period of at least 60 seconds that divides evenly into a day.

## 4. Preparing Metrics for SLIs

### Metric Sources

Cloud Monitoring can use:

- Google Cloud platform and service metrics.
- Application metrics emitted by code or OpenTelemetry.
- Prometheus metrics collected via Google Cloud Managed Service for Prometheus.
- Log-based metrics created from Cloud Logging when logs are structured and represent relevant events.
- Custom metrics written via the Cloud Monitoring API.

Metric examples:

| Service / Source | Metric or Signal | Suggested SLI |
|---|---|---|
| External HTTPS Load Balancer | `loadbalancing.googleapis.com/https/request_count` | Ratio of successful requests |
| HTTP application | Total requests and successful requests emitted by app | Availability |
| Application with latency histogram | Processing-time distribution | Ratio of requests under latency threshold |
| GKE with Prometheus | Request counter by route/status | Availability or latency |
| Batch workflow | Start/end timestamp metrics or job status | Ratio of jobs completing on time |
| Data pipeline | Data age or last update timestamp | Freshness |

Metric names, monitored resources, and labels vary by service. Inspect Metrics Explorer and the Metrics list for the exact service before creating an SLO.

### Checking Metric Kind and Cardinality

In Metrics Explorer, select the metric and inspect its metric kind, value type, monitored resource, and labels. For request-based SLIs, confirm the metric kind is `DELTA` or `CUMULATIVE`. Avoid metrics with labels containing timestamps, user IDs, or request IDs, as they create very high cardinality, increase costs, and make queries hard to manage.

A good SLI metric should:

- Have sufficient coverage for the in-scope requests or workflows.
- Maintain a stable definition across deployments.
- Include labels to cleanly separate good and total counts.
- Aggregate cleanly at the service level without losing meaning.
- Avoid double-counting requests from unintended retries or fan-out.
- Emit continuous data so missing telemetry can be detected.

Missing metrics do not mean the service is healthy. Monitor telemetry completeness and treat absent data as a distinct observability issue.

## 5. Hands-On: Creating an Availability SLI for an HTTPS Load Balancer

This example uses built-in HTTPS Load Balancer metrics to measure the ratio of requests with response code class `200` over total requests. This is an illustrative example following Google Cloud documentation. For real APIs, adjust the good condition to match your application contract; if 3xx responses are valid or specific business errors need exclusion, update the filter accordingly.

### Step 1: Inspect the Metric in Metrics Explorer

1. Open Google Cloud Console and select the project containing the HTTPS Load Balancer.
2. Go to **Monitoring → Metrics Explorer**.
3. Select monitored resource type `http_lb_rule`.
4. Select metric `loadbalancing.googleapis.com/https/request_count`.
5. Check the metric kind; request count must be valid for a request-based SLI.
6. Add the filter `response_code_class = 200` to capture only good requests per the example.
7. Use the `sum` aggregation to combine time series within the service scope.
8. Open the chart's JSON view to inspect the metric filter and alignment/aggregation settings.

Total requests filter:

~~~text
metric.type="loadbalancing.googleapis.com/https/request_count"
resource.type="http_lb_rule"
~~~

Good requests filter:

~~~text
metric.type="loadbalancing.googleapis.com/https/request_count"
resource.type="http_lb_rule"
metric.label."response_code_class"="200"
~~~

In environments with multiple load balancers, add label filters to scope down to the specific forwarding rule, project, backend, or service boundary. Without scoping, the SLI may accidentally merge traffic across multiple applications.

### Step 2: Define the Service in Cloud Monitoring

Cloud Monitoring attaches SLOs to a service. In the Console:

1. Open **Monitoring → Services**.
2. Select an auto-discovered service, or click **Define service** to create a custom service.
3. Name and describe the service according to a user-recognizable unit, such as `customer-api-prod`.
4. Select the resource or identification criteria matching the service's metrics.
5. Save the service and open its details page.

For Cloud Run, GKE, or self-deployed applications, do not assume built-in availability/latency SLIs are always available. If the service type lacks standard metrics, define a custom service and custom SLIs from Load Balancer, application, or Prometheus metrics.

### Step 3: Create the SLO in the Console

1. On the service details page, click **Create SLO**.
2. Choose an availability SLI or custom metric depending on the metric source.
3. Select request-based evaluation if counting good requests / total requests.
4. Confirm the metric and filters match the service scope.
5. Set the goal, for example `0.99` corresponding to 99%.
6. Select the compliance period, such as rolling 30 days or calendar week depending on reporting needs.
7. Review the definition and save the SLO.

Creating SLOs typically requires the Monitoring Editor role (`roles/monitoring.editor`) or a custom role with the corresponding Cloud Monitoring permissions.

## 6. Creating an SLO via the Cloud Monitoring API

Cloud Monitoring API v3 allows creating an SLO under an existing service. A request-based SLI for the Load Balancer example can be expressed using `goodTotalRatio`:

~~~json
{
  "displayName": "99% successful HTTPS requests per calendar week",
  "serviceLevelIndicator": {
    "requestBased": {
      "goodTotalRatio": {
        "totalServiceFilter": "metric.type=\"loadbalancing.googleapis.com/https/request_count\" resource.type=\"http_lb_rule\"",
        "goodServiceFilter": "metric.type=\"loadbalancing.googleapis.com/https/request_count\" resource.type=\"http_lb_rule\" metric.label.\"response_code_class\"=\"200\""
      }
    }
  },
  "goal": 0.99,
  "calendarPeriod": "WEEK"
}
~~~

The example above illustrates the API structure. Before using it, add filters to scope strictly to the target service's load balancer and verify the response code labels in your project. `goal` is a decimal greater than 0 and no more than 0.9999; `0.99` means 99%. `calendarPeriod` evaluates from the start of a calendar period; if you want a sliding window, use `rollingPeriod`.

Create the SLO using REST:

~~~bash
export PROJECT_ID="my-production-project"
export SERVICE_ID="customer-api-prod"

curl -X POST \
  "https://monitoring.googleapis.com/v3/projects/${PROJECT_ID}/services/${SERVICE_ID}/serviceLevelObjectives" \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  --data-binary @slo.json
~~~

In this example, save the JSON above as `slo.json`. The service must exist before calling the SLO creation endpoint. You can use the GET or list SLOs API to verify the resource name and saved configuration.

### Rolling Period vs. Calendar Period

Cloud Monitoring supports two ways to specify the compliance period:

- **Rolling period:** evaluates over a sliding window counting backward from the current time, such as 7 days or 30 days.
- **Calendar period:** evaluates from the beginning of a calendar day, week, fortnight, or month.

In the API, `rollingPeriod` uses a duration format and must be an integer number of days, up to 30 days. `calendarPeriod` supports `DAY`, `WEEK`, `FORTNIGHT`, and `MONTH`. Choose a rolling period when you want an always-current window; choose a calendar period when reporting and operational accountability are summarized by calendar cycles.

## 7. Calculating and Using the Error Budget

### Request-Based Error Budget

Suppose an API has a 99.9% availability SLO over 30 days. During the period, there are 2,000,000 eligible requests:

\[
Error\ budget = (1 - 0.999) \times 2,000,000 = 2,000
\]

Thus, up to 2,000 bad requests remain within the period's target. If 1,200 failed requests have already occurred, the remaining budget is 800 requests.

### Time-Based Error Budget

With a 99.9% target over 30 days:

\[
30 \times 24 \times 60 \times 0.001 = 43.2\text{ minutes}
\]

This conversion applies to SLIs measuring the proportion of good time. For request-based SLIs, calculate against eligible request counts rather than converting directly into downtime.

### Using the Budget in Release Decisions

| Budget Status | Suggested Action |
|---|---|
| Plenty remaining and stable burn rate | Proceed with release plans while continuing to monitor high-risk changes |
| Burning faster than normal | Investigate recent changes, increase observability, consider pausing rollout |
| Nearly exhausted | Prioritize bug fixes and risk reduction; consider deferring non-essential features |
| Exhausted | Enforce the team's reliability policy, focusing on restoring the SLO before resuming risky changes |

The error budget is not a quota meant to be deliberately spent down. It is a way to quantify how much risk the team and customers can accept during a period.

## 8. Alerting on SLOs and Burn Rate

A high-CPU alert only tells you resources are under load; a burn-rate alert tells you how quickly the service is consuming its error budget. Cloud Monitoring lets you attach alerting policies to SLOs to notify when the burn rate exceeds a threshold over a time window.

Burn rate is the normalized rate of error budget consumption. A burn rate of 1 means that if the current error rate persists for the entire compliance period, the budget will be depleted right at the end. A burn rate greater than 1 indicates consumption is faster than the SLO allows.

### Creating an SLO Alert in the Console

1. Open **Monitoring → Services** and select the service.
2. Under current status, locate the SLO to monitor.
3. Select the action to create an SLO alert.
4. Choose a burn-rate threshold and violation duration matching the urgency.
5. Select notification channels such as email, SMS, or integrations used by the organization.
6. Write alert documentation: which SLO is affected, which service, which dashboard/runbook to open, and initial actions.

You should configure alerts both for fast budget-burn incidents and slower longer-term trends. Short windows catch sudden outages; longer windows catch prolonged degradation. Thresholds must be based on actual traffic, service criticality, and the operations team's response capacity.

### Things to Watch Out For

- Burn rate is calculated from the SLI and the compliance/lookback period selected in the alert.
- SLO burn-rate alerts currently cap the lookback/compliance period at 24 hours; long-term budget tracking can use the SLO compliance dashboard alongside alerts.
- With low traffic, a handful of errors can produce a high error rate in a short window. Consider higher thresholds, appropriate durations, or minimum traffic conditions.
- Ensure working notification channels and clear runbooks exist; an alert with no recipient or no next action provides little value.

## 9. Applying SLIs/SLOs to Cloud Run, GKE, and Data Services

Cloud Monitoring does not automatically know the definition of "success" for every application. For each platform, choose measurement points and metric sources that accurately reflect the journey:

| Platform | Suggested Measurement Source | Example SLI |
|---|---|---|
| Cloud Run | Application or Cloud Run request metrics, HTTPS Load Balancer metrics, OpenTelemetry | Ratio of successful requests; ratio of requests under 300 ms |
| GKE | Application Prometheus metrics, service mesh, or load balancer | Ratio of good requests per route; ratio of latency under threshold |
| Compute Engine | Application, load balancer, uptime check, or log-based metrics | Ratio of successful transactions; ratio of valid health probes |
| BigQuery | Job completion metrics, query latency, business metrics | Ratio of critical queries finishing within threshold; ratio of pipelines updating data on time |
| Cloud Storage | Operation metrics, logs, or synthetic checks along application flows | Ratio of successful workload read/write operations |

For GKE-based services and custom services, the SLO UI often requires selecting `Other` to construct a custom SLI. If using Google Cloud Managed Service for Prometheus, scraped Prometheus metrics can be selected for custom SLIs provided they meet metric kind and structure requirements.

With Cloud Run or GKE, if platform-level request metrics cannot distinguish business journeys, emit application metrics with normalized route or operation labels. Do not place user IDs, order IDs, or request IDs in SLI labels; use bounded-cardinality labels such as service, route template, region, or status class.

## 10. Common SLI/SLO Design Mistakes

| Mistake | Consequence | Improvement |
|---|---|---|
| Choosing CPU or memory as the primary API SLI | Metrics look good while users still hit errors | Measure request success, latency, or workflow outcomes |
| Counting all HTTP 4xx as service errors | Error budget is drained by invalid client inputs | Classify error codes according to the API contract |
| Measuring at the backend while ignoring gateway errors | SLI misses the full end-to-end user journey | Measure at the load balancer or appropriate entry point, adding backend metrics for diagnosis |
| Grouping all endpoints into one SLO | Critical endpoints can be masked by high traffic from minor endpoints | Split SLIs by journey or request type |
| Setting a 100% SLO | Leaves no error budget to manage risk and sets unrealistic goals | Set goals grounded in historical data and user expectations |
| Using GAUGE metrics for request-based SLIs | SLI fails metric kind requirements | Use DELTA/CUMULATIVE metrics or design an appropriate windows-based SLI |
| Excessive metric cardinality | Increases cost and complicates aggregation and querying | Use labels with bounded value sets |
| Treating missing traffic as a good SLI | Lack of data does not prove the service is healthy | Monitor metric completeness alongside uptime/synthetic checks |
| Reviewing SLOs only monthly | Operational incidents are detected too late | Combine short-term burn-rate alerts with longer compliance periods |
| Changing metrics without SLO versioning | Results across periods are no longer comparable | Document definition changes, effective dates, and rationale |

## 11. Workflow for Implementing SLOs in an SRE Team

1. **Identify the service and users:** agree on service boundaries, critical journeys, and owners.
2. **Write the promise:** describe what users expect in verifiable statements.
3. **Define the SLI:** choose good events, total events, thresholds, and exclusions.
4. **Inspect telemetry:** verify metrics have appropriate coverage, labels, metric kind, and cardinality.
5. **Measure a baseline:** examine historical data to understand distributions, seasonality, low-traffic periods, and error spikes.
6. **Agree on goal and period:** set targets aligned with business impact, operational history, and any SLAs.
7. **Create service, SLI, and SLO:** configure in Cloud Monitoring and verify dashboards.
8. **Create alerts and runbooks:** set burn-rate thresholds, notification channels, and responsible owners.
9. **Integrate budget into change processes:** agree on how to act when the budget drops rapidly or is exhausted.
10. **Review periodically:** evaluate whether SLIs still represent user experience and metrics remain reliable.

Do not copy the exact same SLO target across every service. An internal service used a few times a day may not need the same target as a public payment API. Let journey criticality, failure impact, and improvement cost drive the target.

## 12. Pre-Publication SLO Checklist

- [ ] Service boundaries and owners are defined.
- [ ] Each SLI reflects a quality dimension users care about.
- [ ] Good events, total events, and exclusions are clearly documented.
- [ ] Metrics have suitable coverage, metric kind, and labels.
- [ ] High-cardinality labels are avoided.
- [ ] Missing telemetry and low-traffic edge cases are checked.
- [ ] Goal and compliance period are grounded in historical data and service needs.
- [ ] Error budget is calculated and its usage is agreed upon by the team.
- [ ] SLO is created and verified in Cloud Monitoring.
- [ ] Burn-rate alerts have thresholds, notification channels, and runbooks.
- [ ] A review process exists when the service, metrics, or user contract changes.

## 13. Conclusion

SLIs turn service experience into measurements; SLOs put verifiable targets on those measurements; error budgets help teams decide acceptable risk per period. Cloud Monitoring provides tools to link services with metrics, define request-based or windows-based SLIs, create SLOs, view compliance, and alert on burn rate.

Start from the user promise, pick metrics close enough to actual experience, validate telemetry quality, and only then set targets. When SLOs are connected to dashboards, alerts, and release workflows, teams can use reliability data to prioritize work and improve services intentionally.

## References

- [Concepts in service monitoring – Google Cloud Observability](https://docs.cloud.google.com/stackdriver/docs/solutions/slo-monitoring)
- [Creating an SLO – Google Cloud Observability](https://docs.cloud.google.com/stackdriver/docs/solutions/slo-monitoring/ui/create-slo)
- [Creating a service-level indicator from metrics](https://docs.cloud.google.com/stackdriver/docs/solutions/slo-monitoring/api/identifying-custom-sli)
- [ServiceLevelObjectives REST API – Cloud Monitoring](https://docs.cloud.google.com/monitoring/api/ref_v3/rest/v3/services.serviceLevelObjectives)
- [Alerting on your burn rate – Google Cloud Observability](https://docs.cloud.google.com/stackdriver/docs/solutions/slo-monitoring/alerting-on-budget-burn-rate)
- [Overview of service-level indicators](https://docs.cloud.google.com/stackdriver/docs/solutions/slo-monitoring/sli-metrics/overview)
