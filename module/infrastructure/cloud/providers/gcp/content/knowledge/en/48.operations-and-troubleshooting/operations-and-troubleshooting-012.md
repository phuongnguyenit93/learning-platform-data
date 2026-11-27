# Detecting Cost Anomalies from Billing and Audit Logs

An application operating normally can still generate an unexpectedly high Google Cloud bill. A forgotten VM, unplanned instance scaling, BigQuery queries scanning huge datasets, looping log writes, cross-region data transfers, or leaked credentials can all drive up costs rapidly. Checking only the end-of-month invoice usually catches problems too late and leaves teams unsure which change caused them.

To investigate effectively, combine **Cloud Billing** (which service, project, and SKU incurred charges) with **Cloud Audit Logs** (which principal or identity changed which resource and when), then corroborate with metrics, deployment history, and traffic. Billing and audit logs answer different questions: a cost spike does not prove a bad administrative action, and a resource-creation event does not prove that resource caused the entire cost increase.

This lesson belongs to the **Operations and Troubleshooting** chapter of the **CLOUD_PROVIDERS_GCP** module. The module covers project organization, IAM, and VPC; deploying Compute Engine, GKE, Cloud Run, storage, and databases; protecting resources, automating releases, and monitoring reliability and costs. This lesson focuses on anomaly detection, root-cause tracing, and controlled remediation in GCP operations.

> **Safety principle:** The queries and filters below are for observation and investigation. Never automatically delete VMs, wipe data, disable billing, or revoke production permissions based solely on a cost alert. Every intervention must consider SLOs, workload owners, security risks, and recovery plans.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish billing account, project, service, SKU, usage date, invoice month, credits, taxes, and adjustments.
- Understand Cloud Billing reporting latency and the limits of real-time cost data.
- Configure Budgets & alerts, cost anomalies, Billing export to BigQuery, and cost allocation.
- Write SQL to identify projects, services, and SKUs with abnormal cost increases while accounting for incomplete data.
- Read Cloud Audit Logs to identify principals, methods, resources, and change timestamps.
- Correlate billing, audit logs, and deployment/traffic metrics to form root-cause hypotheses.
- Build an alerting workflow, severity classification, cost controls, and false-positive mitigation.
- Build an investigation runbook with timelines, evidence, owners, and recurrence-prevention controls.

## 1. Three Evidence Sources and One Investigation Workflow

| Source | Can Answer | Cannot Answer Alone |
|---|---|---|
| Cloud Billing Reports / FinOps Hub | Where spending rose by project, service, SKU, and time; trends and forecasts | Who directly caused the cost or which change triggered it |
| Cloud Billing export to BigQuery | Granular daily cost analysis by project, SKU, labels, credits; some resource-level details | Full API call history or security root causes |
| Cloud Audit Logs | Principal, service, API method, resource, and timestamp of logged events | Exact dollar cost per API call or unlogged data operations |
| Cloud Monitoring / service metrics | CPU, instances, requests, egress, log ingestion, DB load, or jobs | Final invoice charges and billing discounts |
| CI/CD and change records | Releases, config diffs, reviewers, triggers, and commits | Confirmation that a specific change caused a spend spike without correlation |

Investigations should follow **where spend increased → which usage increased → which event or change aligns → validate hypothesis → remediate and re-measure**.

~~~mermaid
flowchart TD
    A["Budget / anomaly alert / daily report"]
    B["Verify scope, currency, data latency"]
    C["Billing: project → service → SKU → resource"]
    D["Monitoring: usage, instances, requests, egress"]
    E["Audit Logs: principal, method, resource, time"]
    F{"Evidence sufficient for root cause?"}
    G["Safe action per owner/runbook"]
    H["Gather more telemetry, narrow hypotheses"]
    I["Monitor cost and SLOs post-action"]
    J["Post-incident review and prevention"]
    A --> B --> C
    C --> D
    C --> E
    D --> F
    E --> F
    F -->|"Yes"| G --> I --> J
    F -->|"No"| H --> C
~~~

A cost spike can be completely legitimate: a marketing campaign driving traffic, a regional migration, an approved load test, or month-end batch processing. Investigation separates **budgeted legitimate growth** from **unexpected waste** and **security compromise signals**.

## 2. Cost Structure in Cloud Billing

### Key Concepts

| Field / Concept | Operational Meaning |
|---|---|
| Billing account | Payment account linked to one or more projects |
| Project | Where resource usage occurs; not every charge carries a project ID |
| Service | Product such as Compute Engine, Cloud Run, BigQuery, or Cloud Storage |
| SKU | Detailed pricing unit within a service, e.g., compute type, storage tier, or network transfer |
| `usage_start_time` / `usage_end_time` | Usage window billed for a line item |
| `export_time` | Timestamp when the record was exported/updated in BigQuery |
| `invoice.month` | Invoice month in `YYYYMM` format; may differ from usage month |
| `cost` | Line-item charge before credits; not necessarily net of credits |
| `credits` | Applicable credits/discounts, typically negative numbers |
| `cost_type` | Classification such as `regular`, `tax`, `adjustment`, `rounding error`, etc. |
| `currency` | Billing account currency; never sum across different currencies blindly |

**Gross cost** and **net cost** are not the same metric. In SQL examples, net cost is calculated as **SUM(cost) + SUM(credits.amount)** over matching line items. When credits change, net cost can rise even if actual resource consumption stays flat. Conversely, looking only at `cost` while ignoring credits may not match discounted spend.

### Usage Time Differs from Invoice Time

Some services meter usage over time windows, and line items can arrive delayed. Across month boundaries, late usage can land on the next invoice month; adjustments or taxes post in separate cycles. Therefore:

1. Analyze operational trends by **`usage_start_time`**.
2. Reconcile invoices by **`invoice.month`**.
3. State the timezone explicitly when aggregating by date.
4. Inspect `cost`, `credits`, `cost_type`, and `currency` together.
5. Never treat today's partial day or current hour as "complete spend for comparison" while reporting lags.

Cloud Billing carries reporting latency ranging from a few hours to over a day depending on service and billing arrangement. **Billing exports are not real-time usage meters**; use Cloud Monitoring and service metrics to catch spikes immediately after deployments.

## 3. Organizing Scope and Access Permissions

### Cost Scopes

An operations team should separate at minimum:

- Billing account or business unit.
- Project: development, staging, production, shared platform.
- Service and SKU.
- Environment, application, owning team, or cost center where labels/tags are supported.
- Resource ID when detailed billing export supplies it.

Not every SKU reports resource-level costs. Shared charges like networking, commitment fees, logging, support, or taxes may require dedicated allocation rules. A null resource field **is not always an export bug**.

### Typical Permissions Needed

| Role / Automation | Need | Permission Principle |
|---|---|---|
| FinOps analyst | Read billing reports and exported data | Read access to billing and required BigQuery dataset |
| SRE/on-call | Read service metrics and admin audit logs | Scoped read-only Logging/Monitoring |
| Security responder | Investigate IAM, Data Access, and security anomalies | Policy-approved read access to sensitive audit logs |
| Budget administrator | Create/edit budgets and notifications | Dedicated Billing Budgets permissions |
| Cost responder automation | Send tickets/alerts and propose changes | Read/notify permissions—never default resource deletion rights |

Permission to view Cloud Audit Logs **does not automatically cover every log type**. Data Access logs may require roles like Private Logs Viewer on the relevant log bucket. Billing data itself is financially and architecturally sensitive; enforce least-privilege IAM on datasets, dashboards, and exports.

## 4. Configuring Budgets, Cost Anomalies, and Alert Channels

### Budgets & Alerts

In Google Cloud Console, open **Billing → Budgets & alerts**, select a billing account, and:

1. Create a budget scoped to a billing account or filtered by project/service.
2. Choose the budget period and target amount.
3. Configure alert thresholds—for example, 50%, 80%, and 100% of actual spend plus a forecasted threshold if supported.
4. Configure email recipients, and optionally link Pub/Sub for programmatic notifications.
5. Assign a response owner, priority, and runbook.
6. Confirm recipients have clear on-call ownership and permissions.

**Alerts-only budgets are not hard caps.** Crossing a threshold does not automatically stop VMs, APIs, or spending. Google Cloud offers spend-cap budget mechanisms for certain eligible services, yet you should never assume every project or SKU stops when a budget triggers.

### Cost Anomalies / FinOps Hub

Cloud Billing includes **cost anomaly detection** based on trends and deviations. In the Console, view Anomalies/FinOps Hub and configure notification thresholds per available features and permissions. Keep in mind:

- Anomaly detection operates on reported spend, so it inherits reporting latency.
- Detected deviations do not automatically explain the technical root cause.
- Thresholds should weigh both **cost impact** and **deviation percentage** to avoid alert fatigue on tiny services.
- Email notifications, daily digests, and programmatic Pub/Sub notifications depend on active configuration and current feature support; verify enabled channels carefully.

For example, jumping from 1 to 4 currency units (300%) rarely warrants an urgent page, whereas jumping from 500 to 800 units (60%) has substantial budget impact. Alerts should balance **absolute increase** and **relative increase**.

### Programmatic Notifications

Budgets or anomaly events (where supported) can route to Pub/Sub and be processed by a Cloud Run service/function or Workflows to file tickets or notify on-call chat channels.

~~~mermaid
flowchart LR
    BILL["Cloud Billing budget / anomaly"] --> TOPIC["Pub/Sub topic"]
    TOPIC --> HANDLER["Notification handler"]
    HANDLER --> DEDUP["Deduplicate + enrich"]
    DEDUP --> TICKET["Incident / FinOps ticket"]
    DEDUP --> DASH["Link Billing / Logs Explorer"]
    DEDUP --> HUMAN["Owner verifies and acts"]
~~~

Pub/Sub can deliver duplicate or out-of-order notifications. Handlers need **idempotency/deduplication**, schema validation, correlation ID logging, and narrow IAM permissions. With budget Pub/Sub notifications, messages can fire multiple times per day rather than only when crossing a threshold. Never build a handler that shuts off production billing upon receiving a single message.

## 5. Enabling Billing Export to BigQuery

For deep investigation, configure **Cloud Billing → Billing export → BigQuery export**:

1. Select the target billing account.
2. Prepare a BigQuery project/dataset in a supported location per Billing export docs.
3. Enable **Standard usage cost export** for account/project/service/SKU/labels/credits data.
4. Consider **Detailed usage cost export** when resource-level cost visibility is needed where supported.
5. Grant FinOps/SRE read access to the dataset; never make it public.
6. Document export enablement date, billing account ID, dataset location, retention, and query costs.
7. Confirm rows have begun arriving before building dashboards.

### Common Table Names

~~~text
STANDARD:
  PROJECT.DATASET.gcp_billing_export_v1_BILLING_ACCOUNT_ID

DETAILED:
  PROJECT.DATASET.gcp_billing_export_resource_v1_BILLING_ACCOUNT_ID

PRICING:
  PROJECT.DATASET.cloud_pricing_export
~~~

In real billing tables, separators in the billing account ID appear as underscores; always **copy the exact table name shown in BigQuery** rather than guessing from the billing account ID.

Standard exports do not include resource-level lines for every row. Detailed exports broaden coverage, yet some services and charges still lack resource-level granularity. Enabling export does not necessarily backfill full historical billing; backfill behavior and arrival times depend on dataset location and export type.

### Operational Data Notes

- Export datasets grow large; set query byte limits, filter by time partitions, and build curated views.
- Billing export schemas gain new columns over time; avoid `SELECT *` in dashboards.
- Applying labels to already-running resources generally does not retroactively tag prior usage costs.
- Resource location and invoice month serve different analytical purposes.
- Add data-freshness checks; missing rows for today never prove spending dropped.

## 6. SQL: Finding Projects, Services, and SKUs with Rising Costs

The BigQuery examples below target **Standard usage cost export** in GoogleSQL. Replace the illustrative table path with your actual dataset table. Run against authorized data only; never commit real billing account IDs to public repositories.

### 6.1 Total Net Cost by Day and Service

~~~sql
-- Replace billing-lab.billing_export and table name with actual values.
-- Restrict to past 14 completed days; avoid treating today as complete.
WITH line_items AS (
  SELECT
    DATE(usage_start_time, 'UTC') AS usage_date,
    COALESCE(project.id, 'UNATTRIBUTED') AS project_id,
    service.description AS service_name,
    currency,
    cost_type,
    CAST(cost AS NUMERIC)
      + CAST(IFNULL((
        SELECT SUM(c.amount)
        FROM UNNEST(credits) AS c
      ), 0) AS NUMERIC) AS net_cost
  FROM `billing-lab.billing_export.gcp_billing_export_v1_XXXXXX_XXXXXX_XXXXXX`
  WHERE usage_start_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 16 DAY)
    AND usage_start_time < TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 2 DAY)
)
SELECT
  usage_date,
  project_id,
  service_name,
  currency,
  ROUND(SUM(net_cost), 2) AS net_cost
FROM line_items
WHERE cost_type = 'regular'
GROUP BY usage_date, project_id, service_name, currency
ORDER BY usage_date DESC, net_cost DESC;
~~~

**Reading results:** identify which project/service drove the largest spike before drilling down to SKUs. `UNATTRIBUTED` rows appear when certain fees are not tied directly to a project; never strip them out of financial totals blindly.

UTC is used here for clean auditing. If business reports use `Asia/Ho_Chi_Minh`, enforce one consistent timezone across the entire comparison and state it explicitly. Never compare UTC dates against local-timezone dates without normalization.

### 6.2 Top SKUs with Cost Increases Across Two Complete Windows

This compares the most recent 7 complete days (ending 3 days ago) against the preceding 7 days. This is an investigative **heuristic**, not Google Cloud's official anomaly detection definition.

~~~sql
DECLARE last_complete_day DATE
  DEFAULT DATE_SUB(CURRENT_DATE('UTC'), INTERVAL 3 DAY);

WITH daily AS (
  SELECT
    DATE(usage_start_time, 'UTC') AS usage_day,
    COALESCE(project.id, 'UNATTRIBUTED') AS project_id,
    service.description AS service_name,
    sku.description AS sku_name,
    currency,
    SUM(
      CAST(cost AS NUMERIC)
      + CAST(IFNULL((
        SELECT SUM(c.amount)
        FROM UNNEST(credits) AS c
      ), 0) AS NUMERIC)
    ) AS net_cost
  FROM `billing-lab.billing_export.gcp_billing_export_v1_XXXXXX_XXXXXX_XXXXXX`
  WHERE DATE(usage_start_time, 'UTC')
    BETWEEN DATE_SUB(last_complete_day, INTERVAL 13 DAY)
        AND last_complete_day
    AND cost_type = 'regular'
  GROUP BY usage_day, project_id, service_name, sku_name, currency
),
comparison AS (
  SELECT
    project_id,
    service_name,
    sku_name,
    currency,
    SUM(IF(usage_day BETWEEN DATE_SUB(last_complete_day, INTERVAL 6 DAY)
                         AND last_complete_day, net_cost, 0)) AS current_7d,
    SUM(IF(usage_day BETWEEN DATE_SUB(last_complete_day, INTERVAL 13 DAY)
                         AND DATE_SUB(last_complete_day, INTERVAL 7 DAY),
           net_cost, 0)) AS previous_7d
  FROM daily
  GROUP BY project_id, service_name, sku_name, currency
)
SELECT
  project_id,
  service_name,
  sku_name,
  currency,
  ROUND(current_7d, 2) AS current_7d,
  ROUND(previous_7d, 2) AS previous_7d,
  ROUND(current_7d - previous_7d, 2) AS increase_absolute,
  ROUND(
    SAFE_DIVIDE(current_7d - previous_7d, NULLIF(previous_7d, 0))
      * 100, 1
  ) AS increase_percent
FROM comparison
WHERE current_7d - previous_7d > 20
ORDER BY increase_absolute DESC
LIMIT 50;
~~~

**Interpretation:** the 20-unit currency threshold is **illustrative**—adjust to your spending scale and currency. When `previous_7d = 0`, percent increase is undefined; `SAFE_DIVIDE` yields `NULL` instead of failing, so never overlook newly appearing SKUs. Two-week windows can be skewed by holidays, campaigns, or batch schedules; compare matching day types or workload schedules when needed.

### 6.3 Separating Gross, Credits, and Net

~~~sql
SELECT
  DATE(usage_start_time, 'UTC') AS usage_day,
  service.description AS service_name,
  currency,
  ROUND(SUM(CAST(cost AS NUMERIC)), 2) AS gross_cost,
  ROUND(SUM(
    CAST(IFNULL((
      SELECT SUM(c.amount)
      FROM UNNEST(credits) AS c
    ), 0) AS NUMERIC)
  ), 2) AS credits_amount,
  ROUND(SUM(
    CAST(cost AS NUMERIC)
    + CAST(IFNULL((
      SELECT SUM(c.amount)
      FROM UNNEST(credits) AS c
    ), 0) AS NUMERIC)
  ), 2) AS net_cost
FROM `billing-lab.billing_export.gcp_billing_export_v1_XXXXXX_XXXXXX_XXXXXX`
WHERE DATE(usage_start_time, 'UTC')
  BETWEEN DATE_SUB(CURRENT_DATE('UTC'), INTERVAL 14 DAY)
      AND DATE_SUB(CURRENT_DATE('UTC'), INTERVAL 3 DAY)
  AND cost_type = 'regular'
GROUP BY usage_day, service_name, currency
ORDER BY usage_day DESC, net_cost DESC;
~~~

If gross is flat while net rises, check changes in credits, discounts, or commitment allocations. If both gross and usage quantities rise, investigate workload consumption. Never fold taxes or adjustments into operational usage spike queries without separating `cost_type`.

### 6.4 Resource-Level Costs from Detailed Export

If Detailed usage cost export is enabled and the service populates resource fields:

~~~sql
SELECT
  COALESCE(project.id, 'UNATTRIBUTED') AS project_id,
  service.description AS service_name,
  sku.description AS sku_name,
  COALESCE(resource.name, '(no resource detail)') AS resource_name,
  currency,
  ROUND(SUM(
    CAST(cost AS NUMERIC)
    + CAST(IFNULL((
      SELECT SUM(c.amount) FROM UNNEST(credits) AS c
    ), 0) AS NUMERIC)
  ), 2) AS net_cost
FROM `billing-lab.billing_export.gcp_billing_export_resource_v1_XXXXXX_XXXXXX_XXXXXX`
WHERE DATE(usage_start_time, 'UTC')
  BETWEEN DATE_SUB(CURRENT_DATE('UTC'), INTERVAL 10 DAY)
      AND DATE_SUB(CURRENT_DATE('UTC'), INTERVAL 3 DAY)
  AND cost_type = 'regular'
GROUP BY project_id, service_name, sku_name, resource_name, currency
ORDER BY net_cost DESC
LIMIT 100;
~~~

`resource.name` can be `NULL` even when exports work properly. Never use `resource.name` as a sole join key to audit logs, since names can collide across projects/zones, resources can be recreated, or IDs may be formatted differently. Always match on project, service, location, and time window as well.

### SQL and Query Cost Safety

- Test on narrow date ranges and use BigQuery dry runs to estimate bytes scanned.
- Maintain normalized views with stable schemas since Billing export may add fields over time.
- Never hardcode currency assumptions or sum accounts using different currencies.
- Filter `cost_type = 'regular'` for operational usage analysis, and include all `cost_type` values when reconciling invoices.
- When credits produce negative net cost, never interpret it as "negative resource usage."
- Save query versions, filters, and timezones for reproducibility.

## 7. Baseline-Driven Anomaly Detection Instead of Static Thresholds

Monthly budget thresholds help cap monthly spend yet miss many anomalies. For instance, a 70% surge during the morning hours is worth investigating even while monthly spend remains under budget.

### Building a Per-Service/Project Baseline

A practical strategy:

1. Pick one metric—net cost or gross cost—and keep it consistent across comparisons.
2. Slice by project/service/SKU or owned cost center.
3. Select days considered complete per internal SLA (e.g., 2–3 days lag), without treating that lag as a Cloud Billing guarantee.
4. Compare the target day against the same weekday across the prior 4–8 weeks if traffic is weekly-seasonal.
5. Use medians and dispersion rather than plain averages if past spikes skew history.
6. Set both absolute and relative thresholds; handle new workloads lacking history separately.
7. Enrich candidates with deployments, marketing events, load tests, and traffic shifts before paging.

### Detection Rule Pseudocode

~~~text
baseline = median(daily_cost_of_same_weekday_over_previous_6_weeks)
actual = cost_of_last_verified_complete_day
absolute_increase = actual - baseline
relative_increase = absolute_increase / max(baseline, small_floor)

if not enough_history:
    alert "new workload / insufficient baseline" with lower confidence
else if actual > minimum_impact
    and absolute_increase > absolute_threshold
    and relative_increase > relative_threshold:
    create anomaly candidate

enrich with known changes, traffic metrics and audit logs
assign owner and verify before remediation
~~~

A baseline of 0 requires special handling rather than alerting "infinite percent increase" and auto-deleting resources. For seasonal services or month-end batches, align with business calendars instead of purely weekday matching.

### Avoiding False Positives and False Negatives

| Phenomenon | Potential Misinterpretation | How to Verify |
|---|---|---|
| Delayed billing export updates | Latest day looks artificially low then jumps later | Check data freshness and `export_time` |
| Changing credits/discounts | Net cost rises while usage stays flat | Compare gross, credits, and invoice |
| Scheduled batch jobs | One day exceeds normal baseline | Check schedulers and business calendar |
| Seasonality / campaigns | Legitimate traffic growth | Check requests, business volume, and releases |
| Newly created project | No historical spend baseline | Alert on absolute spend and owner |
| Shared resources | Unclear which team owns the spend | Labels, tags, and allocation rules |
| SKU/rate change | Cost rises while quantity barely moves | Compare SKU, usage quantity, and pricing updates |
| Quota expansion | Zero immediate spend yet higher blast risk | Audit logs, quotas, and workload metrics |
| Security incident | Off-hours activity and unfamiliar resources | Combine IAM events, source IPs, and resource changes |

Managed Cloud Billing cost anomaly detection provides an extra alerting layer. Custom BigQuery baselines let you tailor logic to workloads, though they require maintenance and should never be treated as official billing calculations.

## 8. Cloud Audit Logs: Finding Who Did What, Where, and When

Cloud Audit Logs record distinct event types depending on service and logging configuration:

| Type | Characteristics | During Cost Investigations |
|---|---|---|
| Admin Activity | Configuration/metadata changes; enabled by default | Find new VMs, resizes, enabled services, bucket/config changes |
| Data Access | Data reads/writes by permission and service; usually requires explicit enablement (BigQuery has exceptions) | Find queries or data operations driving usage when logged |
| System Event | Google-initiated system actions | Separate platform actions from user actions |
| Policy Denied | Access denied by policy | Spot anomalous behavior or permission misconfigurations |

**Data Access logs are disabled by default for most services** (with exceptions like BigQuery). If not previously enabled, unlogged past events cannot be recovered retroactively. Enabling Data Access logging also incurs log storage costs; balance scope, retention, and security.

### Key Fields to Read

| Audit Log Field | Meaning |
|---|---|
| `timestamp` | When the event was recorded |
| `protoPayload.serviceName` | API service, e.g., `compute.googleapis.com` |
| `protoPayload.methodName` | API method/operation |
| `protoPayload.resourceName` | Target resource if present |
| `protoPayload.authenticationInfo.principalEmail` | Calling principal when available |
| `protoPayload.requestMetadata.callerIp` | Source IP when logged and unredacted |
| `protoPayload.status` | Call success or error status |
| `operation.id` / `operation.first` / `operation.last` | Tracks long-running operations where present |
| `resource.labels` | Project, zone, instance, or monitored resource metadata |

Not every event populates every field, and principals may be redacted in some contexts. One operation can emit multiple log entries; never count each log line as a separate VM creation.

### Finding VM Creation Events

In Logs Explorer, filter:

~~~text
log_id("cloudaudit.googleapis.com/activity")
protoPayload.serviceName="compute.googleapis.com"
protoPayload.methodName:"instances.insert"
~~~

Narrow by time range (e.g., hours/days before Compute Engine SKUs climbed), project, and zone to cut noise. Substring matching on `methodName` works across some API versions; if empty, inspect actual method names in service-specific audit logs rather than assuming no events occurred.

### Finding Compute Config Changes That Raise Costs

~~~text
log_id("cloudaudit.googleapis.com/activity")
protoPayload.serviceName="compute.googleapis.com"
(
  protoPayload.methodName:"instances.insert" OR
  protoPayload.methodName:"instances.setMachineType" OR
  protoPayload.methodName:"disks.insert" OR
  protoPayload.methodName:"instanceGroupManagers"
)
~~~

These events are **candidate causes**. Check operation outcomes, VM/disk types, uptime, and billing breakdowns to confirm whether the cost increase matches. With autoscaling, changes may originate from a service agent or controller rather than a human clicking Create.

### Finding Cloud Run / GKE / Cloud SQL Events

~~~text
log_id("cloudaudit.googleapis.com/activity")
(
  protoPayload.serviceName="run.googleapis.com" OR
  protoPayload.serviceName="container.googleapis.com" OR
  protoPayload.serviceName="cloudsql.googleapis.com"
)
~~~

Once you isolate the service, filter by specific `methodName` and `resourceName`. Cloud Run `min instances` updates, GKE node pool resizes, and Cloud SQL tier/HA/replica changes are key events to cross-check. Audit logs complement—rather than replace—reading live configurations and deployment history.

### Querying via gcloud CLI

Example searching Admin Activity events:

~~~bash
export PROJECT_ID="example-production-project"

gcloud logging read \
  'log_id("cloudaudit.googleapis.com/activity") AND
   protoPayload.serviceName="compute.googleapis.com" AND
   protoPayload.methodName:"instances.insert"' \
  --project="$PROJECT_ID" \
  --freshness=7d \
  --limit=100 \
  --format="table(timestamp,protoPayload.authenticationInfo.principalEmail,protoPayload.methodName,protoPayload.resourceName)"
~~~

This is a **read-only** query. Results depend on IAM, audit logging settings, retention, and log age. Use Logs Explorer when inspecting full details and linked operations. Never treat `principalEmail` alone as final human attribution: calls often come from pipeline service accounts.

### Checking Changes on Cloud Billing Accounts

Cloud Billing emits its own audit logs for billing account management and resource billing associations. If an anomaly involves a project switching billing accounts, billing permission changes, or billing enablement/disablement, check Logs Explorer for:

~~~text
protoPayload.serviceName="cloudbilling.googleapis.com"
~~~

Depending on resource location, permissions, and log routing, you may need to scope to the **billing account** rather than just the application project. Filter further by Admin Activity, timestamp, principal, and actual `methodName`. Cloud Billing audit logging documentation lists methods such as `UpdateResourceBillingProtection` and `DisableResourceBilling` for certain association and billing-disable actions.

Never confuse a billing-association change with a technical driver generating more CPU hours or egress. Moving a project between billing accounts shifts spend between **each account's** reports even when workload consumption is unchanged. Cross-check project associations, timestamps, and both financial reports.

## 9. Linking Billing and Audit Logs: Correlate, Never Jump to Causality

During investigation, build a unified timeline covering:

1. **Detection:** when did the budget or anomaly alert fire?
2. **Usage:** at what `usage_start_time` did the SKU begin climbing?
3. **Change:** what did Audit Logs and CI/CD record immediately beforehand?
4. **Workload:** how did Cloud Monitoring requests, node counts, network bytes, or CPU shift?
5. **Mitigation:** what change was applied, and did driver metrics return to normal?
6. **Billing confirmation:** did daily cost by usage date drop once exports finished catching up?

### Illustrative Hypothetical Timeline

| UTC Time | Source | Event | Next Question |
|---|---|---|---|
| 09:00 | CI/CD | Released `orders-api` v2.3 | Did autoscaling or logging config change? |
| 09:03 | Admin Activity | Deploy service account updated Cloud Run service | What changed in the revision config? |
| 09:07 | Monitoring | Instance count jumped from 3 to 25 | Driven by requests, concurrency, or min instances? |
| 09:10 | Monitoring | DB connections and p95 latency spiked | Retry storm or legitimate traffic? |
| 12:00 | Billing | Cloud Run and Cloud SQL usage rose | Which exact SKUs drove the cost? |
| Next day | Anomaly report | Cost deviation breached threshold | Confirm with owner and complete usage export |

This is an illustrative example, not an actual event timeline. Even if spend spikes the next day, **do not** declare the 09:00 release the root cause purely from proximity; inspect configuration diffs, traffic, usage metrics, and other events.

### Keys Linking Audit and Billing

Correlation attributes:

| Attribute | From Billing | From Audit / Monitoring | Notes |
|---|---|---|---|
| Project | `project.id` | `resource.labels.project_id` or parent resource | Normalize project IDs |
| Service | `service.description` | `protoPayload.serviceName` | Display names and API service names differ |
| Resource | `resource.name` (if present) | `protoPayload.resourceName` / `resource.labels` | May be missing or formatted differently |
| Region/zone | `location` or system labels | Resource labels, API request | Some SKUs are global/multi-region |
| Time | `usage_start_time` / `export_time` | `timestamp` | Billing lags behind real time |
| Owner | Labels/tags/project mapping | `principalEmail`, change tickets | API caller is not always the cost owner |

No universal SQL join key reliably maps every billing line item to an Audit Log entry. Linking them requires service knowledge and often asset inventory or deployment history lookups.

### Evidence-Based Attribution Workflow

Suppose Cloud Storage network egress spikes:

1. Billing confirms **network transfer SKUs** spiked, not storage capacity.
2. Metrics confirm egress bytes jumped on the matching bucket/endpoint where available.
3. Inspect CDN hit ratios, cache misses, request patterns, and client regions.
4. Check for changes to cache metadata, load balancer/CDN policies, CORS, or public ACLs.
5. Check Audit Logs for configuration changes; inspect Data Access logs only if enabled and authorized.
6. Check for legitimate traffic campaigns, bot crawls, abuse, or application download loops.
7. Apply the right fix and re-measure usage and spend once billing updates.

If a config change bypassed CDN caching, fixing CDN/cache policies cuts egress. If unauthorized scraping/abuse occurred, partner with Security to restrict access and protect data rather than merely tuning caches.

## 10. Checking Metrics by Cost-Driver Category

Billing identifies **the money**; Cloud Monitoring and service-specific metrics identify **the mechanism generating spend**.

| Rising SKU / Service | Metrics or State to Inspect | Common Hypotheses |
|---|---|---|
| Compute Engine VM CPU/RAM | VM count, machine type, uptime, MIG size | Extra VMs created, upsized, or forgotten batches |
| Persistent Disk / snapshots | Capacity, disk type, snapshot count and age | Orphaned disks, overly long snapshot retention |
| GKE nodes/workloads | Node count, node pools, Pod requests, autoscaling | Node pool expansion, overprovisioned requests, stuck jobs |
| Cloud Run CPU/memory | Request rate, concurrency, instance count, min instances | Traffic growth, instance-based billing, min instances change |
| Cloud SQL | CPU, storage, connections, tier, replicas | Tier/HA change, overloaded queries, auto-growing storage |
| BigQuery | Jobs, bytes processed, slot usage, reservations | Full-table scans, looping jobs, unpartitioned queries |
| Cloud Storage | Stored bytes, operations, egress, object versions | Copies, download loops, broken lifecycle, retention |
| Cloud Logging | Ingestion bytes, log volume by service/severity | Debug logging enabled, retry loops, duplicate logs |
| Pub/Sub | Messages published/delivered, backlog, subscriptions | Publish loops, redeliveries, extra subscriptions |
| Cloud CDN / Load Balancing | Request count, response size, cache hit/miss, egress | Cache misses, bot traffic, large objects |
| Secret Manager / Cloud KMS | API request counts by type, errors/quotas | App fetching secrets/keys repeatedly without caching |

Do not stare only at CPU when investigating BigQuery or network egress: billed consumption may live in bytes processed, operation counts, or network transfer rather than CPU utilization.

### Cloud Run: Inspect Autoscaling and Databases Together

Suppose a Spring Boot service sets HikariCP `maximumPoolSize` to 10 and max 40 instances. If every instance maxes out its pool simultaneously, the database faces roughly:

~~~text
40 instances × 10 connections/instance
  = 400 potential database connections
~~~

This is a configuration upper bound, not guaranteed active connections. Still, it highlights why **Cloud Run scaling** and **Cloud SQL connections** must be evaluated together. If the app retries infinitely when the DB slows down, instance counts surge, driving both business failures and cloud spend.

### BigQuery: Bytes Processed Differ from Dataset Size

BigQuery on-demand queries are generally driven by bytes processed/billed, whereas capacity-based pricing follows different rules. Even a static dataset can generate huge bills from repeated queries, missing partition pruning, or `SELECT *` on massive tables.

How to investigate:

- Inspect BigQuery Job History or `INFORMATION_SCHEMA.JOBS_BY_PROJECT` for the right project and region.
- Check job ID, principal, `creation_time`, `total_bytes_processed`/`total_bytes_billed`, and errors.
- Hunt for scheduled queries, automations, or BI dashboards refreshing aggressively.
- Check partition filters, clustering, caching, and slot utilization per billing model.

`INFORMATION_SCHEMA` is scoped by region/project and requires specific IAM permissions; never treat `total_bytes_billed` as a universal formula across all pricing models. Job metadata retention and visibility also differ from Billing export.

### Cloud Logging: Observability Itself Costs Money

Enabling `DEBUG` logging in production can emit millions of useless messages, inflating log ingestion and retention bills. However, turning off all security/audit logs to save money blinds incident response and violates compliance. Better approach:

1. Group logs by service and severity to pinpoint the volume driver.
2. Check recent releases that changed log levels, duplicated exporters, or triggered retry loops.
3. Trim noisy non-essential logs and sample high-volume traffic logs appropriately.
4. Preserve mandatory audit/security events, correlation IDs, and error signals.
5. Re-measure ingestion volume, triage capability, and spend.

## 11. When a Cost Spike Is a Security Signal

An unusual cost spike can indicate compromised credentials, unauthorized crypto-mining, workloads launched by unfamiliar principals, data exfiltration egress, or API abuse. Do not assume every spike is an attack—yet classify early so real security signals are not missed.

### Priority Red Flags

- New VMs/GPUs created in rarely used regions outside deployment windows.
- New service accounts or static keys with broad roles showing unusual activity.
- API usage surging without matching business traffic growth.
- Network egress to unexplained destinations.
- IAM policy or firewall edits right before unfamiliar resources appear.
- Logging disabled or audit retention/sinks modified outside change control.
- Rapid create-and-delete resource bursts spanning multiple projects.

### Separating Three Situations

| Category | Example | Handling |
|---|---|---|
| Legitimate change | Marketing campaign or approved batch | Confirm owner; update forecast/budget |
| Config / operational bug | Looping cron job, debug logs, bumped min instances | Rollback / change control while protecting SLOs |
| Suspected compromise | Unfamiliar principal launching crypto miners | Trigger security incident response, preserve evidence, isolate safely |

### When Suspecting Credential Compromise

1. Confirm scope: projects, principals, resources, timeframe, and estimated spend.
2. Capture evidence from logs/asset inventory per security policy without logging sensitive payloads.
3. Notify Security/on-call and the billing account owner.
4. Evaluate disabling credentials, revoking permissions, or isolating resources per runbook without accidentally breaking critical production services.
5. Check whether other projects share the same principal or key.
6. Recover with clean identities/keys and validate business workflows.
7. Monitor audit logs and billing afterward, review root cause, and harden controls.

**Never immediately delete suspected compromised resources before checking evidence preservation.** Depending on the incident, stopping, quarantining, or snapshotting for forensics may be vital; follow incident response and data protection policies strictly.

### Audit Logs and Attribution

Seeing a service account `principalEmail` in an audit log does not prove who triggered the change. Correlate with Cloud Build triggers, Git commits, CI runner identities, service agents, and impersonation chains. A service account can be used legitimately by automation or abused externally; logs identify **the API-calling identity**, not always **the ultimate human actor**.

## 12. 0–15–60-Minute Runbook on Receiving an Alert

The goal is not zeroing spend in two seconds, but **limiting financial loss without causing a larger outage or data loss**.

### 0–15 Minutes: Verify and Classify

1. Record alert ID, timestamp, billing account, currency, project, and budget/anomaly threshold.
2. Check whether the alert is fresh or a duplicate delivery; verify channel and source data.
3. Open Billing Reports or BigQuery with matching filters to identify service and SKU.
4. Account for reporting latency: today or yesterday may be incomplete.
5. Check absolute dollar impact; avoid declaring a P1 over a negligible amount.
6. Identify the workload owner, planned business events, and change calendar.
7. If compromise indicators appear, escalate immediately to Security Incident Response.

### 15–60 Minutes: Isolate and Act Safely

1. Use Detailed export or asset inventory to pinpoint candidate resources where available.
2. Compare before/after metrics: instances, egress, requests, BigQuery jobs, log volume.
3. Search Admin Activity / Data Access audit logs for matching events.
4. Cross-check PRs, deployments, config edits, and quota updates.
5. Estimate projected run rate if left unchecked.
6. Choose the minimal mitigation: roll back a release, dial back debug logs, fix job schedules, or cap autoscaling per runbook.
7. Obtain approval and communicate when production or compliance is impacted.
8. Monitor both cost drivers and service SLIs/SLOs after mitigating.

### 60 Minutes to 24 Hours: Confirm and Prevent Recurrence

- Verify post-mitigation usage/spend once Billing exports catch up—do not expect instant billing charts.
- Document root cause, contributing factors, timeline, and evidence links.
- Decide whether budget forecasts or anomaly thresholds need tuning.
- Add guardrails: quotas, labels, IaC reviews, branch protections, tests, and retention policies.
- Track action items with owners, priorities, deadlines, and verification criteria.
- Audit orphaned resources and lingering spend; verify cleanups safely.

### Suggested Severity Levels

| Severity | Illustrative Condition | Response |
|---|---|---|
| SEV1 | Suspected compromise or massive, rapidly escalating budget risk | Security incident + incident commander |
| SEV2 | Spend crosses major threshold; misconfigured workload still climbing | SRE/FinOps on-call, change control |
| SEV3 | Moderate increase with known owner and bounded ongoing risk | Ticket and handle during business hours |
| Informational | Planned growth or approved campaign | Tag known change and update forecast |

These levels are examples; organizations should define quantitative thresholds tailored to budgets, burn rates, and business criticality.

## 13. Automating Detection Without Automating Outages

A FinOps/SRE architecture often combines two complementary streams:

1. **Near real-time:** Cloud Monitoring alerts on request rates, autoscaling, egress, query jobs, or log ingestion to catch runaway workloads immediately.
2. **Reported spend:** Billing budget/anomaly notifications or Scheduled Queries on Billing exports to quantify dollar impact and isolate SKUs.

Never expect Billing exports to detect spikes minute-by-minute. For fast-moving failures, rely on quotas, metrics, and resource guardrails to bound blast radius before invoices catch up.

### Reference Architecture

~~~mermaid
flowchart TD
    BILL["Cloud Billing export → BigQuery"]
    METRIC["Cloud Monitoring metrics"]
    NOTI["Budget / anomaly notifications"]
    QUERY["Scheduled query / Workflows"]
    RULE["Anomaly rule + data freshness gate"]
    PUB["Pub/Sub / incident event bus"]
    ENRICH["Enrich with audit logs, owner and changes"]
    DEDUP["Dedup / severity / cooldown"]
    HUMAN["SRE + FinOps + Security"]
    ACTION["Manual approval / safe automated remediation"]
    VERIFY["Measure usage, SLO and delayed cost"]
    BILL --> QUERY --> RULE --> PUB
    METRIC --> PUB
    NOTI --> PUB
    PUB --> ENRICH --> DEDUP --> HUMAN --> ACTION --> VERIFY
~~~

Running a scheduler every few minutes does not make Billing export real-time. When data for a period is incomplete, rules should return **`INSUFFICIENT_DATA`** and rely on real-time metrics for early warning.

### Designing the Alert Handler

Handlers should:

- Validate event source, schema version, allowed billing account/project, and notification permissions.
- Build an idempotency key from event ID or account + budget/anomaly ID + time bucket + category.
- Deduplicate Pub/Sub deliveries and apply sensible cooldowns per root cause.
- Resolve owners from project catalogs, labels, or service registries—never assume the API caller owns the budget.
- Include impact, dashboard links, time window, candidate resources/SKUs, and data confidence in alerts.
- Rate-limit BigQuery/API queries so the detector itself never creates runaway bills.
- Never dump full billing datasets or sensitive audit logs into public chat channels.
- Never trigger destructive production actions from unverified payloads.

### Handler Rule Pseudocode

~~~text
on_cost_signal(signal):
    validate_signal_source_and_scope(signal)
    key = build_dedup_key(signal)

    if already_processed(key):
        return

    context = fetch_current_cost_breakdown_or_mark_delayed(signal)
    metrics = fetch_resource_metrics(signal.project, signal.time_window)
    change_events = find_relevant_admin_audit_events(
        signal.project, signal.time_window)
    owner = resolve_owner(signal.project, signal.service)

    severity = classify_impact_and_security_indicators(
        context, metrics, change_events)
    create_or_update_incident(key, owner, severity, evidence_links)

    if severity_is_critical:
        page_on_call()
    else:
        send_to_triage_queue()

    # Remediation must follow approvals/runbooks; never auto-delete production.
~~~

This is pseudocode, not a complete handler. Real implementations need timeouts, error handling, retries, IAM, observability, and durable deduplication storage.

### Should You Automatically Disable Project Billing?

Disabling billing can halt critical services or lock out data access; recovery can cost far more than the money saved. If an organization ever automates billing actions:

1. Restrict strictly to approved non-critical sandbox/test projects.
2. Maintain owner, business criticality, exception, and escalation metadata.
3. Run dry-runs and precondition checks first.
4. Keep full audit logs and an accountable billing/service recovery procedure.
5. Test against duplicate notifications, delayed data, and misconfigured thresholds.

For production, prefer targeted local fixes (such as pausing an unintended batch job) over project-wide shutdowns. **A cost alert is decision input, not an automated resource-destruction command.**

## 14. Four Real-World Investigation Scenarios

### Scenario A — Cloud Run Spend Multiplies After Deploy

Suppose Orders API runs Spring Boot on Cloud Run. Cloud Run bills jump after a release while completed order volume stays flat.

**Investigation:**

1. Billing: check whether CPU, memory, or instance-time SKUs jumped.
2. Monitoring: inspect requests, instances, concurrency, CPU utilization, and error rates.
3. Cloud Run revision configs: inspect min instances, concurrency, max instances, and CPU allocation/billing mode.
4. Cloud Audit Logs: inspect Cloud Run config changes, deployer principal, method, and timestamp.
5. Deployment history: check whether commits altered HikariCP, retry policies, log levels, or startup logic.
6. Database: check whether connection errors or query latency spiked.

**Hypotheses:** the release slowed per-request latency, forcing more instances, or `min instances` was increased. If legitimate traffic rose, the driver is workload volume rather than a release bug.

**Controlled action:** roll back the revision if user-facing SLOs degraded, or tune concurrency/min instances after load testing. Watch billing trends once exports update and confirm DB errors do not spike.

### Scenario B — Orphaned Compute Engine / GKE Resources

A test batch spun up extra VMs or a node pool and never cleaned up. Billing shows rising Compute Engine CPU and Persistent Disk charges.

**Investigation:**

- Detailed export/asset inventory surfaces candidate resources.
- Compute Engine Audit Logs show `insert` or `resize`, caller principal, and timeframe.
- GKE audit/change logs show cluster or node pool changes if tied to GKE.
- Resource labels, owners, and TTL tags confirm whether they were temporary test assets.
- Monitoring showing near-idle CPU does not mean zero cost.

**Action:** verify with the owner and confirm resources do not belong to a MIG, active cluster, or backup/DR system. Stop or delete only verified unused resources under change approval with rollback awareness. Disks and snapshots carry separate retention; stopping a VM does not delete its boot disk.

### Scenario C — Cloud Storage / Network Egress Spikes While Object Count Is Flat

Billing shows network egress spiking while object count and stored GiB barely change.

**Investigation:**

1. Separate storage capacity SKUs, Class A/B operation SKUs, and network transfer SKUs.
2. Measure egress bytes, request counts, and CDN cache hit ratios if applicable.
3. Inspect HTTP/load balancer logs for user agents, paths, and status codes per security policy.
4. Check for changes to `Cache-Control`, URL maps, Cloud CDN mode, or bucket IAM.
5. Check Data Access logs if enabled and authorized; never treat missing logs as proof of zero downloads.
6. Correlate with newly published assets, user campaigns, or bot scraping.

**Action:** fix caching, block abuse, or tighten access controls based on root cause. If private data was exposed publicly, trigger security incident response; CDN invalidation cannot recall copies already downloaded externally.

### Scenario D — High BigQuery Costs Driven by a Dashboard

A new dashboard refreshes constantly using full-table scans. Billing shows BigQuery Analysis spiking even though no new infrastructure was created.

**Investigation:**

- Project/service/SKU breakdown in Billing export.
- BigQuery Job History and `INFORMATION_SCHEMA` for the target region/project.
- Calling principal, scheduled query/BI tool, and `total_bytes_billed` for on-demand usage.
- Change records showing who created or edited the scheduled query or dashboard.
- Query plans, partition filters, materialized views, and refresh cadence.

**Action:** add partition pruning, throttle refreshes, materialize views, or evaluate capacity pricing. Validate query accuracy before changing logic, then re-measure billed bytes/slot usage and actual spend.

### Summary of the Four Scenarios

| Scenario | Cost Driver | Decisive Evidence | Risk of Rushing |
|---|---|---|---|
| Cloud Run | CPU/memory/instances | Revision config + metrics + Billing | Outage from capping scale too low |
| VM/GKE orphan | VM/node/disk hours | Resource inventory + audit + owner | Deleting shared infrastructure |
| Storage egress | Bytes transferred/requests | CDN/HTTP metrics + config diffs | Accidentally exposing data or causing 403s |
| BigQuery | Query bytes/slots | Job history + billing SKU | Breaking dashboards or business pipelines |

## 15. Labels, Tags, and Cost Attribution

Without clear cost ownership, investigations drag even with complete billing exports. A typical ownership schema includes:

| Metadata | Example | Meaning |
|---|---|---|
| `application` | `orders-api` | Responsible service |
| `environment` | `production` | Environment isolation |
| `team` | `commerce` | Owning team |
| `cost_center` | `cc-102` | Financial allocation |
| `managed_by` | `terraform` | Configuration source |
| `expires_at` | `2026-11-30` | Hint for temporary lab resources |

Not every service or SKU supports every resource-level label or tag. Combine:

- Clear project hierarchy.
- Resource labels/tags where supported and exported to Billing.
- A service ownership catalog with on-call and escalation contacts.
- Shared-cost allocation rules for networking, platform, support, and shared infra.
- `UNATTRIBUTED` or `UNALLOCATED` tracking reports to surface untagged spend.

**Never confuse labels with IAM permissions or TTL policies.** An `expires_at` label by itself never deletes a VM; cleanup automation must verify ownership, approvals, and safety preconditions first.

### Delayed Label Appearance

Adding a label today generally does not backfill past days' billing lines. Some tags also carry propagation lag. Consequently, early reports may bucket a resource under `UNLABELED` even after it is labeled. Avoid silently rewriting history; if re-allocating past spend, document the allocation rule and rule version.

### Business-Value Unit Cost Metrics

Alongside per-project spend, track:

~~~text
Cost per successful order
  = attributable net service cost / successful orders

Cost per 1,000 API requests
  = attributable net cost / valid requests * 1000

BigQuery cost per report
  = attributable analytics cost / completed reports
~~~

These are approximate KPIs once attribution is established. During legitimate traffic growth, total bills rise while **cost per successful order** stays flat or drops. That is not necessarily an incident—evaluate unit economics alongside forecasts.

## 16. Early Detection Through Quotas and Infrastructure Guardrails

Runaway bills usually follow technical gaps: overly high max instances, jobs lacking deadlines, `DEBUG` logging left on, missing storage lifecycles, cross-region transfers, or tight polling loops.

### Preventive Guardrails

| Control | Risk Reduced | Caution |
|---|---|---|
| Cloud Run max instances | Caps burst instance sprawl | Can drop legitimate traffic if set too low |
| GKE `ResourceQuota`/requests/limits | Bounds namespace capacity | Over-requesting can leave Pods `Pending` |
| CI job timeouts/cleanup | Prevents orphaned test VMs/clusters | Needs fallback sweepers if runners crash |
| Project/service quotas | Bounds specific resource usage | Not a hard cap on total bills |
| BigQuery maximum bytes billed | Blocks runaway queries | Pick thresholds above valid report sizes |
| Logging filters/sampling | Prevents unnecessary log volume | Never drop mandatory audit/security events |
| Storage lifecycle/retention | Prunes old versions and snapshots | Misconfigured rules can delete recoverable data |
| IAM / Org Policy | Blocks unintended resource types or regions | Test policies so valid workloads are not blocked |

Define guardrails in Infrastructure as Code / policy-as-code with peer review and testing. A "cost optimization" that causes user-facing errors often inflicts greater total business loss.

### Caution When Capping Autoscaling

Never just slash max instances to cut spend. Evaluate:

- Throughput and latency SLOs.
- CPU, memory, and connection pool limits.
- Scale-out speed and rejected request rates.
- Downstream quotas (Cloud SQL, Pub/Sub, partner APIs).
- Backlog size and processing latency.

Fixing a retry storm or infinite loop is far better than starving legitimate user requests of capacity.

## 17. Practicing Analysis with Synthetic Data

If you lack access to real Billing exports, practice detection logic on a synthetic dataset. The values below are **synthetic** and do not reflect real Google Cloud usage or pricing.

### A Daily Spend Table

| Date | Project | Service | Net Cost (Illustrative Units) |
|---|---|---|---:|
| 2026-11-09 | `orders-prod` | Cloud Run | 20 |
| 2026-11-10 | `orders-prod` | Cloud Run | 22 |
| 2026-11-11 | `orders-prod` | Cloud Run | 21 |
| 2026-11-12 | `orders-prod` | Cloud Run | 19 |
| 2026-11-13 | `orders-prod` | Cloud Run | 20 |
| 2026-11-14 | `orders-prod` | Cloud Run | 21 |
| 2026-11-15 | `orders-prod` | Cloud Run | 85 |
| 2026-11-15 | `orders-prod` | Cloud SQL | 26 |

This synthetic table shows Cloud Run jumping from ~20 to 85 units on November 15. Before declaring an incident, inspect instance/request metrics, releases, campaigns, and Cloud SQL spend. Both absolute and relative thresholds flag this, though the dataset is too short to isolate seasonality.

### SQL Using a Synthetic CTE

~~~sql
WITH sample AS (
  SELECT DATE '2026-11-09' AS usage_day, 'Cloud Run' AS service, 20.0 AS net_cost
  UNION ALL SELECT DATE '2026-11-10', 'Cloud Run', 22.0
  UNION ALL SELECT DATE '2026-11-11', 'Cloud Run', 21.0
  UNION ALL SELECT DATE '2026-11-12', 'Cloud Run', 19.0
  UNION ALL SELECT DATE '2026-11-13', 'Cloud Run', 20.0
  UNION ALL SELECT DATE '2026-11-14', 'Cloud Run', 21.0
  UNION ALL SELECT DATE '2026-11-15', 'Cloud Run', 85.0
  UNION ALL SELECT DATE '2026-11-15', 'Cloud SQL', 26.0
),
baseline AS (
  SELECT
    service,
    AVG(net_cost) AS baseline_cost
  FROM sample
  WHERE usage_day < DATE '2026-11-15'
  GROUP BY service
),
target AS (
  SELECT
    service,
    SUM(net_cost) AS target_cost
  FROM sample
  WHERE usage_day = DATE '2026-11-15'
  GROUP BY service
)
SELECT
  target.service,
  ROUND(target_cost, 2) AS target_cost,
  ROUND(baseline_cost, 2) AS baseline_cost,
  ROUND(target_cost - IFNULL(baseline_cost, 0), 2) AS absolute_increase,
  ROUND(
    100 * SAFE_DIVIDE(
      target_cost - baseline_cost,
      NULLIF(baseline_cost, 0)
    ), 1
  ) AS percent_increase,
  CASE
    WHEN baseline_cost IS NULL THEN 'NEW_SERVICE_OR_NO_HISTORY'
    WHEN target_cost >= 50
       AND target_cost - baseline_cost >= 30
       AND target_cost > 2 * baseline_cost THEN 'ANOMALY_CANDIDATE'
    ELSE 'REVIEW'
  END AS detection_result
FROM target
LEFT JOIN baseline USING (service)
ORDER BY target_cost DESC;
~~~

With these sample rows, Cloud Run is classified as **`ANOMALY_CANDIDATE`** because it breaches both absolute and relative thresholds. Cloud SQL lacks history in the dataset and is flagged separately, avoiding division by zero.

This example teaches rule logic; real detectors should span multiple weeks, align weekdays or business cycles, and wait for complete data. **A detection rule produces investigation candidates, never an automatic root-cause verdict.**

### Extended Practice Exercise

Modify the synthetic dataset to:

1. Add a week where Cloud Run spend rises due to an approved marketing event.
2. Add a brand-new service with no prior history.
3. Add a negative credit making net cost drop even while gross spend rises.
4. Add an incomplete day's rows and demonstrate why that day must be excluded.
5. Build an allowlist for planned maintenance alongside an investigation ticket for unexplained spikes.

When testing rules, evaluate both false positives and false negatives—not merely whether the 85-unit day fires.

## 18. Reconciling Results Before Publishing Final Root Cause

Custom cost reports can differ from the Billing Console due to timing, filters, credits, or fee grouping. Reconcile before finalizing RCA:

| Question | What to Verify |
|---|---|
| Right billing account? | Billing account ID and linked projects |
| Right currency? | `currency` field in export; avoid mixing accounts |
| Usage time vs. invoice? | `usage_start_time` differs from `invoice.month` |
| Data complete? | `export_time`, service lag, completed days |
| Credits included? | `cost + credits.amount`; separate gross vs. net |
| Taxes/adjustments included? | `cost_type` aligned with report purpose |
| Missing resource IDs? | Detailed export coverage and null `resource.name` |
| Labels complete? | Application date, propagation lag, service limits |
| Did audit event succeed? | `protoPayload.status`, operations, follow-up events |
| Which org team owns principal? | Service account owner, impersonation, CI triggers |

### Gross Spend Rises While Net Spend Stays Flat

For example, commitment discounts may absorb higher usage so net spend stays steady. Even if today's budget is untouched, rising gross usage flags growing consumption and financial risk if credits or commitments expire. Report both **resource usage** and **net cost after credits**.

### Net Spend Rises While Usage Stays Flat

Inspect discounts, expiring credits, SKU pricing updates, billing agreements, currency shifts, and adjustments. This points to financial/contractual changes rather than new infrastructure bugs; VM-creation Audit Logs will not explain it.

### Did Spend Drop Immediately After Fixing Config?

Do not judge immediately from Billing reports because usage reporting lags. First verify resource driver metrics dropped (instance counts, bytes processed, log ingestion). Then confirm billed costs once exports finish updating, noting the wait window explicitly.

### Monthly Totals Disagree with Daily Usage Queries

To reconcile invoices, group by **`invoice.month`** and include all `cost_type` values per Cloud Billing docs; daily usage queries differ due to late-arriving rows and adjustments. Never fudge SQL with manual offsets instead of identifying the exact line items.

## 19. Cost Anomaly Investigation Report Template

A useful report aligns SRE, FinOps, and Security around the same facts.

~~~markdown
# Cost anomaly investigation: CA-2026-011

## Details
- Status: INVESTIGATING / CONFIRMED / RESOLVED / FALSE_POSITIVE
- Billing account: <internal reference>
- Project/service/SKU:
- Currency:
- Detection source: Budget / anomaly / query / metrics
- Detected at (UTC):
- Owner / on-call:
- Business criticality:

## Impact
- Baseline: ... (window and methodology defined)
- Observed cost: ... (gross/net, data source)
- Estimated excess: ... (with lag/confidence noted)
- Projected run rate if unresolved:
- SLO and business impact:
- Potential security incident involvement:

## Timeline
| UTC | Source | Event/metric | Evidence link |
|---|---|---|---|
| | | | |

## Hypotheses
1. ...
2. ...

## Evidence
- Billing export query (version/filters):
- Metrics dashboard:
- Audit Logs query:
- Change/deployment record:
- Resource inventory:

## Root Cause and Contributing Factors
- Root cause (only once verified):
- Factors amplifying the increase:
- Ruled-out hypotheses and why:

## Remediation
- Action:
- Owner/approver:
- SLO guardrails:
- Rollback path:

## Verification
- Driver metrics before/after:
- Billing spend after complete export:
- No-regression checks:
- Cleanup / security follow-up:

## Recurrence Prevention
| Action | Owner | Deadline | Verification Method |
|---|---|---|---|
| | | | |
~~~

This template records evidence and decisions; it does not replace a formal Security Incident Report if compromise occurred. Never paste credentials, raw customer data, or sensitive billing datasets into public documents. Keep links pointing to IAM-protected Logs Explorer and Billing views.

## 20. Hands-On Exercise: From Alert to Root Cause

Suppose a team runs Orders API on Cloud Run with Cloud SQL, Cloud Storage, and BigQuery reporting. One day FinOps alerts: **total usage spend for `orders-prod` jumped significantly compared to last week**.

The goal is gathering evidence to confirm or refute hypotheses, writing a report, and proposing safe actions. You do not need to spin up billable GCP resources for the initial analysis; you can use the synthetic SQL in section 17.

### Part A — Preparation

1. Identify the billing account and authorized test project or dataset.
2. Record owner, business criticality, and meaningful cost-impact threshold.
3. Open Cloud Billing Reports and filter exact project, period, and currency.
4. Check whether budget/anomaly notifications are configured.
5. Confirm whether Standard/Detailed Billing exports exist and when collection began.
6. Verify read permissions for Cloud Logging, Audit Logs, and metrics.

**Evidence:** list of data sources, scope, time window, IAM access, and data lag level.

### Part B — BigQuery Analysis

1. Run SQL aggregating net cost by project/service/day on authorized data.
2. List the top three services contributing the largest absolute spend increase.
3. Drill down to SKUs for the top service.
4. Compare gross, credits, and net to rule out discount fluctuations.
5. If Detailed export exists, pull candidate resources and check for `NULL` `resource.name` rows.
6. Build a baseline vs. actual comparison using identical timezone, currency, and `cost_type`.
7. Document assumptions around data completeness and planned workload shifts.

**Evidence:** saved query (or sanitized extract), delta table, and threshold formula.

### Part C — Audit Logs and Metrics Correlation

1. Suppose Cloud Run spiked: inspect `run.googleapis.com` Admin Activity changes.
2. Cross-check revision configs, deploy timestamps, and Cloud Run instance counts.
3. Check Cloud SQL connections and error rates for retry storms or DB saturation.
4. If no config changed, check for legitimate traffic growth or client polling loops.
5. If changes came from a service account, trace the pipeline owner and triggering commits.
6. Check for unfamiliar principals, unexpected services, or out-of-schedule resource creation.
7. Build a timeline table noting correlation strength and missing evidence.

**Evidence:** links to Logs Explorer, dashboards, and change records without sensitive payloads.

### Part D — Decision Proposals

Draft three options:

- **No action / forecast update:** when traffic growth is legitimate and unit cost holds steady.
- **Controlled rollback/fix:** when a deploy or config triggered retry loops, log floods, or unexpected scaling.
- **Security incident response:** when credential abuse or rogue resource indicators appear.

For each option, document:

- Expected benefit.
- Risks to SLOs, data, and customers.
- Required approvers and operators.
- Rollback procedure.
- Post-change verification metrics.

Never stop, delete, or alter IAM on production during an exercise without an approved change workflow. Test detection logic against synthetic data or dedicated sandboxes.

### Part E — Reporting and Improvements

1. Fill in the section 19 report template using verified evidence.
2. State either a verified root cause or ranked hypotheses if evidence remains incomplete.
3. Quantify excess spend in the exact currency with scope and confidence bounds.
4. Propose three preventive actions with owners and deadlines.
5. Define one monitoring alert and one cost anomaly rule with sensible thresholds.
6. Test duplicate Pub/Sub notifications in a mock handler.
7. Outline how you will verify spend dropped once full billing exports arrive.

### Completion Criteria

| Area | Pass Criterion |
|---|---|
| Data accuracy | Separates usage vs. invoice, gross vs. net, currency, and data lag |
| Detection | Uses baseline, absolute/relative thresholds, and handles new services |
| Scoping | Identifies project, service, SKU, and resource where data permits |
| Audit correlation | Records principal/method/time without conflating correlation with causation |
| Security | Flags compromise indicators and escalation paths |
| Action | Defines owner, approvals, SLO impact, and rollback path |
| Re-measurement | Checks driver metrics first, then billing after complete export |
| Report | Includes timeline, evidence, conclusion, and action items |

## 21. Cost Anomaly Response Checklist

- [ ] Confirmed exact billing account and project.
- [ ] Confirmed alert is not a duplicate delivery or known scheduled threshold.
- [ ] Recorded timestamp, timezone, currency, and billing period.
- [ ] Separated actual spend, forecasts, and unfinalized estimates.
- [ ] Accounted for Billing export/Reports data lag.
- [ ] Separated usage date from invoice month.
- [ ] Compared gross cost, credits, and net cost.
- [ ] Filtered `cost_type` (`regular`/`tax`/`adjustment`) appropriately.
- [ ] Identified top contributing project, service, and SKU by absolute impact.
- [ ] Checked resource-level details where supported by service/export.
- [ ] Checked workload metrics and asset inventory.
- [ ] Correlated deploy/config changes in Audit Logs.
- [ ] Checked `principalEmail`, `resourceName`, and operation status where available.
- [ ] Verified whether Data Access logging was enabled in relevant scopes.
- [ ] Checked for IAM, service account, key, or API usage anomalies.
- [ ] Checked for approved traffic, campaigns, or batch jobs before declaring a bug.
- [ ] Identified owner, escalation path, and business criticality.
- [ ] Did not auto-delete or disable production billing from a single cost signal.
- [ ] Assessed SLO impact before capping autoscaling or capacity.
- [ ] Preserved evidence and followed security incident runbooks if compromise is suspected.
- [ ] Set expiration and cleanup owners for lab or temporary resources.
- [ ] Archived queries, filters, timelines, and evidence links.
- [ ] Measured driver metrics before and after remediation.
- [ ] Verified billed cost trends once exports completed.
- [ ] Created preventive actions and updated forecasts/budgets reasonably.

## Self-Check Questions

**1. Why cannot Billing export serve as a per-second cost meter?**

Because reported usage and spend carry latency and can include delayed records or adjustments. Use metrics or resource quotas for near-real-time technical detection, and Billing for financial analysis once data settles.

**2. Why is a 100% increase not always worse than a 20% increase?**

Because absolute financial impact differs. Rising from 1 to 2 may matter far less than rising from 1,000 to 1,200. Combine absolute deltas, percentages, and budget scale.

**3. How does `cost` differ from `net_cost`?**

Net cost across a group of lines is generally `cost` plus applicable credits. Changes in discounts or credits can raise net cost even when workload consumption is unchanged.

**4. When do you use `usage_start_time` versus `invoice.month`?**

Use `usage_start_time` to track operational usage trends when resources ran; use `invoice.month` to reconcile charges billed on a specific invoice.

**5. Are Data Access audit logs always available to query?**

No. Most services require explicit enablement beforehand (with exceptions like BigQuery); retention and IAM permissions also govern access.

**6. Can every billing line item be joined directly to an audit log via `resource.name`?**

No. Detailed export covers resource-level lines only within certain scopes; `resource.name` can be `NULL` or formatted differently from `resourceName` in audit logs. Correlate across project, service, location, time, and inventory.

**7. Why does a service account in an audit log not identify the final accountable person?**

Because the service account may be invoked by Cloud Build, automation, impersonation, or a workload controller. Correlate pipeline triggers, commits, and impersonation permissions.

**8. If a Budget alert crosses 100%, does GCP automatically shut down all services?**

Not for alerts-only budgets. Spend-cap budgets apply only to certain eligible services with specific mechanics. Every cost-control action must be designed and impact-assessed.

**9. If gross cost stays flat while net cost rises, what should you check?**

Inspect credits, discounts, commitment allocations, pricing updates, taxes/adjustments, and billing scope before blaming a technical regression.

**10. Can a new Cloud Run revision raise spend even if request counts stay flat?**

Yes. Requests may burn more CPU time, run at lower concurrency, trigger more retries, or raise `min instances`; measure instances, CPU, latency, and config diffs.

**11. Why must Pub/Sub cost notifications be deduplicated?**

Because Pub/Sub can deliver notifications more than once or out of order. Without deduplication, handlers can file duplicate tickets or fire remediation actions repeatedly.

**12. Why should you avoid turning off all logs to cut bills?**

Because you lose audit/security evidence and incident triage visibility. Optimize sampling and retention for noisy non-critical logs while retaining policy-mandated records.

## References

- [Cloud Billing — Export usage cost data to BigQuery](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery)
- [Cloud Billing — Standard usage cost data schema](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage)
- [Cloud Billing — Detailed usage cost data schema](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage)
- [Cloud Billing — Create and manage budgets](https://docs.cloud.google.com/billing/docs/how-to/budgets)
- [Cloud Billing — Programmatic budget/anomaly notifications](https://docs.cloud.google.com/billing/docs/how-to/budgets-programmatic-notifications)
- [Cloud Billing — View and manage cost anomalies](https://docs.cloud.google.com/billing/docs/how-to/manage-anomalies)
- [Cloud Billing — Audit logging](https://docs.cloud.google.com/billing/docs/audit-logging)
- [Cloud Logging — Understanding audit logs](https://docs.cloud.google.com/logging/docs/audit/understanding-audit-logs)
- [Cloud Logging — Enable Data Access audit logs](https://docs.cloud.google.com/logging/docs/audit/configure-data-access)
- [Cloud Logging — Audit logs best practices](https://docs.cloud.google.com/logging/docs/audit/best-practices)
- [Compute Engine — Audit logging](https://docs.cloud.google.com/compute/docs/logging/audit-logging)
- [BigQuery — INFORMATION_SCHEMA.JOBS views](https://docs.cloud.google.com/bigquery/docs/information-schema-jobs)
- [Cloud Monitoring — Metrics and alerting overview](https://docs.cloud.google.com/monitoring/docs/monitoring-overview)
- [Google Cloud — Cost optimization framework](https://docs.cloud.google.com/architecture/framework/cost-optimization)
- [Google Cloud Pricing Calculator](https://cloud.google.com/products/calculator)

## Conclusion

Detecting cost anomalies is a shared responsibility across **FinOps, SRE, and Security**. Cloud Billing shows which project, service, and SKU drove spending; Detailed exports help narrow down candidate resources; Cloud Audit Logs capture configuration changes and calling identities; and Monitoring plus change records validate technical mechanisms. No single data source tells the whole story—especially given Billing reporting lags and service-dependent audit log coverage.

A dependable workflow combines meaningful baselines, absolute and relative impact thresholds, data-freshness checks, correlated timelines, clear ownership, and non-disruptive mitigations. After intervening, check **resource driver metrics first**, then confirm **actual billed spend** once exports settle. Finally, feed post-incident reviews back into guardrails, IAM hygiene, CI/CD checks, cost attribution, and alerting to shrink both financial leakage and detection time for future incidents.
