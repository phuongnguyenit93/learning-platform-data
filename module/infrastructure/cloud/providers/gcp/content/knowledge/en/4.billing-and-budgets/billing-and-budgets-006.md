# Distinguishing Budget Alerts from Resource Limit Mechanisms

## Learning objectives

After this lesson, learners will be able to:

1. Explain the differences between an **alerts-only Cloud Billing budget**, a **resource quota**, a **system limit**, and **application/service-configured limits**.
2. Identify when a **spend cap budget** can be used on eligible Google Cloud services and the limitations of this mechanism.
3. Understand why **setting a 100 USD budget does not inherently stop an invoice from exceeding 100 USD**, and why hitting a quota does not mean costs drop to zero.
4. Select appropriate control layers for Compute Engine, Cloud Run, GKE, Cloud Storage, BigQuery, and related resources.
5. Design multi-layered cost governance: estimation, alerts, resource controls, incident response, access control, and actual spend tracking.

## 1. Context: one goal, three different questions

In the **CLOUD_PROVIDERS_GCP** module, learners deploy Google Cloud from organization/project hierarchy, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage, and databases, while also needing to secure resources, automate releases, maintain reliability, and monitor costs. Unexpected cost spikes can stem from a forgotten VM left running, aggressive autoscaling, sudden log bursts, growing storage, or repeated analytics queries.

Suppose a team runs an API with a **500 USD** monthly budget. They set alerts at 50%, 80%, and 100%, assuming the API will automatically stop when spend hits 500 USD. That assumption creates risk: **an alerts-only budget exists to notify, not to automatically lock services or halt billing**.

To design properly, distinguish:

- **An alerts-only budget** answers: *Is spend approaching or exceeding plan, and who needs to know to act?*
- **Quotas or resource limits** answer: *How many CPUs can be allocated, how many requests can be sent, or how many instances can run within a given scope?*
- **A spend cap budget**, if supported by the product and account, answers: *Can new usage of an eligible service be paused based on estimated gross spend?*

A cost-safe system usually requires combining alerts with technical guardrails, because no single setting covers every cost driver and operational risk.

## 2. Comparison table of mechanisms

| Mechanism | Primary unit | Effect when threshold is hit | Typical scope | Guarantees invoice will not exceed dollar cap? |
|---|---|---|---|---|
| **Alerts-only Cloud Billing budget** | Currency: USD, VND, etc., matching the billing account | Sends notifications based on actual or forecasted cost; can emit Pub/Sub events | Billing account, project, folder, service, labels per supported config | **No** |
| **Spend cap budget** for eligible services | *Estimated* gross monthly cost of a single service | Pauses new usage of the selected service once the cap takes effect | Single project and single eligible service | **Not absolute**: subject to latency, in-flight usage, and out-of-scope costs |
| **Allocation quota** | Resource/capacity count: CPUs, IP addresses, instances, etc. | Usually rejects additional allocations above the quota | Per project, region/zone, service, or other service-defined dimensions | **No** |
| **Rate quota** | Requests or consumption per time interval | Usually rejects/throttles requests above the limit | Per project, API, region, or consumer | **No** |
| **Concurrent quota** | Number of concurrently running operations | Limits new operations exceeding concurrency | Per service and quota scope | **No** |
| **System limit** | Fixed technical boundary | Prevents operations beyond product-defined limits | Per resource/service | **No** |
| **Service configuration limit** | Max instances, node count, max bytes billed per query, etc. | Slows creation or caps consumption of a specific component | Per workload | **No** |

**Terminology note:** Cloud Billing currently distinguishes between **alerts-only budgets** and **spend cap budgets**. Therefore, you should not generalize that *every Google Cloud budget is alert-only*. This lesson explains how each mechanism works while emphasizing that no single mechanism guarantees a hard cap on the entire system's total invoice.

## 3. Alerts-only budgets: managing spend plans via signals

### 3.1. How does an alerts-only budget work?

Cloud Billing lets you create an **alerts-only budget** to compare recorded consumption against a target dollar amount. A budget typically includes:

1. **Monitoring scope**: an entire billing account or a set of projects, services, folders/organization, or eligible labels.
2. **Budget period**: e.g., monthly, quarterly, yearly, or a custom range per tool capabilities.
3. **Budget amount**: a fixed amount or based on the prior period.
4. **Threshold rules**: such as 50%, 80%, 100%; can evaluate **actual cost** or **forecasted cost** where supported.
5. **Recipients and channels**: emails to configured recipients, linked Cloud Monitoring channels, or Pub/Sub events for programmatic handling.

Example: a **500 USD/month** test budget is configured with actual-cost thresholds at 50%, 80%, and 100%.

| Threshold | Illustrative amount | Signal | What does **not** happen automatically with alerts-only budgets |
|---|---:|---|---|
| 50% | 250 USD | Reminds the team to review usage trends | Does not reduce CPU quota or delete VMs |
| 80% | 400 USD | Prompts investigation of cost growth drivers | Does not disable autoscaling or lock APIs |
| 100% | 500 USD | Reports budget reached/exceeded based on recorded data | Does not automatically stop services or guarantee billing stops at 500 USD |

If consumption continues, total spend can exceed 500 USD. If charges accrue faster than data aggregation, actual spend at the time the email arrives may already be higher than the value reported in the alert.

### 3.2. Actual cost vs. forecasted cost

- **Actual cost threshold**: notifies when recorded charges for the budget scope and period reach the threshold.
- **Forecasted cost threshold**: notifies when the forecasting algorithm predicts period-end spend will reach the threshold, even while recorded spend is still low.

Forecasts provide early warning, but are **estimates based on current data**. Forecasts shift with usage patterns and may not reflect an upcoming sudden traffic spike.

### 3.3. Latency and limits to remember

- **Costs have processing and reporting latency**; never treat budget alerts as a real-time on/off switch.
- Notifications **do not necessarily arrive instantaneously** the moment a request crosses a threshold.
- Setting multiple budgets over overlapping scopes can produce **multiple alerts for the same spend**; establish triage rules and clear ownership.
- A project-scoped budget does not cover costs in other projects outside its selected scope.
- **An alert is a signal requiring action.** If nobody receives it, nobody is on call, or no runbook exists, alerts deliver little value.

### 3.4. Setting up an alerts-only budget in the Console

Hands-on steps (button names may vary across UI updates):

1. Open **Google Cloud Console → Billing → Budgets & alerts** and select the billing account or project with appropriate cost-management permissions.
2. Create an **alerts-only budget**; confirm the exact account, project, and service scope.
3. Choose **Monthly** or an appropriate period; enter the approved target amount.
4. Configure thresholds, such as **50%, 80%, 100% actual**, and add **100% forecast** if helpful.
5. Choose email recipients and notification channels; consider **Pub/Sub** integration when an event-processing application exists.
6. Save, then double-check scope, thresholds, owner identities, and cost dashboards.

To perform these actions, users need **appropriate Cloud Billing permissions**. Permissions to create budgets and permissions to create VMs or deploy apps belong to separate permission sets.

## 4. Spend cap budgets: when a budget has an enforcement mechanism

Current Cloud Billing documentation includes a **spend cap budget** type for **eligible services**, distinct from alerts-only budgets.

### 4.1. Enforcement mechanics

- Created for **a single project and a single eligible service**, on a **monthly period** starting on the first day of the month.
- Google Cloud tracks **gross estimated usage costs** (estimated gross spend based on list prices, before credits/discounts).
- When estimated spend exceeds 100% of the cap, the system **pauses new usage** of the selected service in that project until the cap is lifted or a new period begins.
- In-flight requests may still complete and incur charges. Fixed costs from persistent resources may **not be halted**.
- Enforcement is not instantaneous. **Overages can still be billed normally.**

According to the eligible services list published in Google Cloud documentation at the time of writing, spend caps support **Gemini API**, **Gemini Enterprise Agent Platform (formerly Vertex AI)**, **Cloud Run**, and **Cloud Run functions**. Always check the current eligibility list and conditions before establishing policies; do not generalize this to Compute Engine, GKE, Cloud Storage, Cloud SQL, or all of Google Cloud.

Spend caps have notable limitations: they cannot span multiple projects or services simultaneously, do not support custom periods, and do not aggregate across labels, folders, or organizations; certain customer segments or charge types are ineligible. Once triggered, **application availability** can be impacted because new requests are blocked.

### 4.2. Illustrative interpretation

A project uses **Cloud Run** and **Cloud SQL**:

- The team sets a **100 USD spend cap** for Cloud Run where supported on the account.
- Once the cap is enforced, **new Cloud Run usage** in that project is paused per product behavior.
- **Cloud SQL, storage, or other resources** outside the cap scope can still incur charges.
- Cloud Run charges exceeding the threshold due to **latency or in-flight requests** can still be billed.

Thus, a spend cap is a **conditional cost guardrail for one service**, not a 100 USD total-invoice cap for the entire project.

### 4.3. When to consider a spend cap?

Useful for **test environments or workloads that can safely pause when hitting the cap**. For production systems with strict SLOs, carefully evaluate the impact of blocking traffic before enabling: saving a modest amount of spend could result in service outages and far greater revenue loss.

## 5. Quotas and system limits: resource guardrails instead of dollar guardrails

Google Cloud enforces **quotas** and **system limits** to share resources fairly, protect services, and constrain technical consumption.

### 5.1. Three types of quotas

| Type | Characteristics | Illustrative example | When reached |
|---|---|---|---|
| **Allocation quota** | Limits total allocated resource capacity | Compute Engine CPUs per region, number of IP addresses | Additional allocations above quota are rejected |
| **Rate quota** | Limits API or service consumption over a time interval | Requests per minute | Excess requests may be rejected/throttled; retry per guidance |
| **Concurrent quota** | Limits simultaneously running operations | Concurrent long-running operations | New operations may be rejected until slots free up |

**System limits** are fixed technical bounds imposed by a service and typically cannot be changed; by contrast, quotas often have adjustment request mechanisms (increases or decreases depending on type and scope).

### 5.2. Example: CPU quota is not a billing cap

Suppose a project has a **32 vCPU quota** in a region and has already allocated all 32 vCPUs to VMs:

1. A command to create another 4-vCPU VM may be rejected due to insufficient quota.
2. **The 32 allocated vCPUs keep running and accruing charges** according to resource type, state, and pricing terms.
3. Disks, IP addresses, outbound traffic, and other services can still generate costs.
4. Lowering a quota does not automatically stop existing VMs; verify each quota's and service's exact behavior.

With a rate quota, an API capped at 1,000 requests/minute (hypothetical) may reject the 1,001st request, but **active Compute Engine or storage charges do not automatically decrease**.

### 5.3. How do quotas differ from budgets?

A **budget** measures recorded/forecasted spend for a **billing scope**. A **quota** limits **types and quantities of resources/operations** within an API or service-defined scope. They do not convert directly one-to-one:

~~~text
Budget 500 USD/month
    Does NOT imply:
       CPU quota = 16 vCPUs
       Cloud Run max instances = 5
       BigQuery quota = X queries/minute

To set technical limits:
    Price estimation + load forecast + real measurements
    → choose quotas/limits per resource
    → re-evaluate reliability and budget
~~~

A low quota can **block needed autoscaling**, causing errors or degraded service quality. A high quota helps an app absorb larger traffic bursts, without by itself telling you what the bill will be.

### 5.4. Viewing and adjusting quotas

In the Console:

1. Select the **project** to inspect.
2. Navigate to **IAM & Admin → Quotas & System Limits**.
3. Filter by **Service**, **Quota**, and **Location**; inspect current limits and utilization.
4. Identify whether the quota is **rate/allocation/concurrent**, its project/region scope, and whether it is adjustable.
5. If supported by the service, submit an **adjustment request** via the UI or appropriate API/CLI, based on granted permissions.

Do not assume every quota can be lowered: quota types, minimum floors, platform limits, and admin permissions vary. Many quota increase requests require approval. Production quota changes require evaluating performance, rejection behavior, and disruption risk before applying.

## 6. Service-level configuration limits: controlling consumption rate

Quotas are one layer. Many services also provide **service-specific configuration parameters** to control created resources or workload volume.

| Service/scenario | Applicable limit controls | What can still incur costs |
|---|---|---|
| **Cloud Run** API traffic spike | **Maximum instances**, concurrency, CPU/memory, min-instances tuning | Requests, CPU/memory, network egress, logs, and backend services; max instances may be briefly exceeded in some cases |
| **Compute Engine** | CPU/instance quotas, machine-type restrictions via policy; automation to stop test environments | Running VMs, disks, snapshots, IPs, traffic, licenses |
| **GKE** | Cluster/node pool autoscaling min/max, resource requests/limits, namespace quotas where appropriate | Provisioned nodes, persistent volumes, networking, logging, cluster management |
| **Cloud Storage** | Object lifecycle, retention, write/delete governance rules, and data classification | Stored data, requests, egress, storage/retrieval/early-deletion fees depending on storage class |
| **BigQuery** | Per-query **maximum bytes billed**, appropriate quotas, job permissions/reservations if used | Storage, other jobs, slot reservations, or related services |
| **Cloud SQL** | Appropriate instance sizing and HA choices, provisioning and backup controls | Continuous instance, storage, backups, and network charges within applicable pricing |

### 6.1. Cloud Run max instances

Example of inspecting service status before deciding to adjust:

~~~bash
gcloud run services describe SERVICE_NAME \
  --project=PROJECT_ID \
  --region=REGION
~~~

Once approved, you can cap instance count at the service level:

~~~bash
gcloud run services update SERVICE_NAME \
  --project=PROJECT_ID \
  --region=REGION \
  --max=3
~~~

**This is an instance-count limit, not a spending lock.** Cloud Run may briefly exceed the maximum during traffic surges or revision transitions; capping instances can cause requests to queue or fail when capacity saturates. Evaluate SLOs, concurrency, processing latency, and Cloud SQL dependencies before picking a number.

### 6.2. GKE autoscaling and requests/limits

Suppose a node pool can autoscale from 2 to 6 nodes. A max limit prevents the autoscaler from adding nodes indefinitely in that pool, however:

- A maximum of 6 nodes **does not mean 6 units of cost**: VM type, disks, other node pools, storage, and networking still drive the invoice.
- **Kubernetes CPU/memory limits** constrain container resource consumption; they do not directly cap cluster-wide costs.
- When nodes run out of room, pods can stay **Pending**. Setting limits too low can leave the app unable to serve load.

### 6.3. Cloud Storage lifecycle and BigQuery

- **Object lifecycle** transitions storage classes or deletes objects based on rules. This curbs storage accumulation over time, but you must evaluate retention, retrieval, early-deletion policies, and other data charges.
- **BigQuery maximum bytes billed** can block an on-demand query estimated to process more data than the configured threshold. It does not prevent all other BigQuery costs, nor replace overall cost governance and access control.

## 7. Which solution fits your cost-control goal?

A practical design divides controls into complementary layers:

~~~mermaid
flowchart TB
    A["Business goals and acceptable risk"] --> B["Load and pricing estimation"]
    B --> C["Alerts-only budget: observe and alert"]
    B --> D["Quotas, config limits: constrain consumption"]
    B --> E["Spend cap if service and account are eligible"]
    C --> F["Runbooks and accountable owners"]
    D --> F
    E --> F
    F --> G["Monitor cost, reliability, review periodically"]
    G --> B
~~~

| Need | Primary choice | Trade-offs to check |
|---|---|---|
| Know before spend exceeds plan | Budget forecast/actual alerts, cost reports, owners | Latency, false signals, who is on call |
| Prevent an API from autoscaling excessively | Cloud Run max instances or equivalent autoscaling limits | Failed requests, higher latency when hitting the ceiling |
| Prevent spinning up extra VMs | Allocation quotas, IAM/organization policies where appropriate | Does not stop existing VMs/disks; can block operations |
| Block sudden API request bursts | Rate quotas, app/API-gateway throttling | Clients need backoff; risk of rejecting valid requests |
| Control per-query billed services | Maximum bytes billed/query, access controls, and job monitoring | Affects only supported query types and pricing models |
| Pause new usage at a dollar cap for an **eligible service** | Spend cap budget if eligible | Pauses service; does not cap other costs or latency overages |
| Cut overnight dev/test environment costs | Shutdown schedules, autoscaling, and lifecycle cleanup of temporary resources | Must exclude production and preserve needed data |

## 8. Automating alert responses: adds action without a hard guarantee

An **alerts-only budget** can publish programmatic notifications via **Pub/Sub**; operations teams can build workflows to receive events, evaluate context, and execute authorized actions.

~~~mermaid
flowchart LR
    A["Cloud Billing alerts-only budget"] --> B["Pub/Sub budget notification"]
    B --> C["Cloud Run function / workflow"]
    C --> D{"Valid scope and conditions?"}
    D -->|Unclear| E["Send alert and require human approval"]
    D -->|Confirmed| F["Predefined action for the workload"]
    F --> G["Log, verify, monitor"]
~~~

For example, an 80% threshold event for a **test project** can create a ticket, notify owners, and propose shutting down a lab VM tagged for auto-teardown. If automating shutdowns, the workflow must validate the exact project, tags, owner, resource type, and support a **dry-run** mode for testing first.

### Limits and risks

- **Reporting latency** can let spend exceed the budget before the action runs.
- Events can be redelivered; handling logic must be **idempotent** to avoid repeating destructive changes.
- Automatically stopping services can cause **downtime**, data-stream loss, or user impact; never apply directly to production without approval and a recovery plan.
- Stopping one resource type **does not stop all charges** (disks, snapshots, stored data, and other resources may still bill).
- Using the Cloud Billing API to **disable billing** can halt services, affect resources, and fail to guarantee clean recovery. This is a high-risk measure, not a default budget guardrail.

A solid cost workflow includes **alert milestones**, **accountable owners**, **action scope**, **verification**, **rollback**, and an **audit trail**. Creating an alert alone does not mean you have an automated control system.

## 9. Scenario: e-commerce project running Cloud Run, Cloud SQL, and Cloud Storage

Suppose startup **Minh An** has projects **store-dev** and **store-prod**. A Java/Spring API runs on Cloud Run, uses PostgreSQL on Cloud SQL, stores product images in Cloud Storage, runs report cron jobs, and uses a CI/CD pipeline. The team targets **300 USD/month** for dev and monitors production at **2,000 USD/month**.

These numbers are **training assumptions**, not Google Cloud cost forecasts. Real deployments require pricing-tool estimates and load telemetry.

### 9.1. Initial mistake

The team sets a 300 USD dev budget with a 100% alert and concludes: "Dev cannot exceed 300 USD." Meanwhile, a broken CI loop generates heavy requests, a database-test VM is left running, and Cloud Storage capacity grows daily.

Analysis:

1. An alerts-only budget can **emit a signal once recorded spend is high enough**, but does not block workloads.
2. Existing VMs keep running even if CPU quota blocks creating new VMs.
3. Cloud Storage keeps accruing charges for stored data within applicable pricing scope.
4. Setting only **Cloud Run max instances** leaves Cloud SQL, Storage, networking, and CI outside that limit.
5. Choosing a **spend cap** for Cloud Run (where eligible) only caps that selected service—it does not guarantee total dev spend stops at 300 USD.

### 9.2. Layered control design

| Layer | Dev (disruption acceptable) | Prod (reliability prioritized) |
|---|---|---|
| **Budget** | Alerts-only 300 USD/month; 50/80/100% and forecast thresholds | Alerts-only 2,000 USD/month; 50/80/100% and forecast thresholds |
| **Responders** | Dev team receives emails/tickets; resolves same day | On-call operators and product owner with escalation |
| **Cloud Run** | Low max instances based on test load; consider spend cap if service/account eligible | Max instances sized to SLO and peak load; load-test before capping |
| **Compute Engine** | Tight quotas, lab VM shutdown schedule, restricted VM-creation permissions | Headroom quotas; risk assessment before changes |
| **Cloud Storage** | Expire test data via lifecycle and data policies | Retain data per business, backup, and compliance requirements |
| **Cloud SQL** | Right-sized tier; enable HA only when test case requires it | Availability, recovery, backups, and sizing per requirements |
| **CI/CD** | Restrict deploy permissions; guard against looping jobs | Approvals, testing, controlled rollout, and rollback |
| **Cost monitoring** | Dashboard by service, project, environment | Trend by service, cost per order, anomaly alerts |

The team must distinguish **baseline fixed costs** (VMs, Cloud SQL, disks, steady storage), **variable costs** (requests, load-driven compute, logging, egress), and **overlooked costs** (snapshots, backups, transfers, or secondary environments). Baseline fixed costs are precisely why quotas and request caps do not act as a total-bill ceiling.

### 9.3. Example operational response cycle

| Signal | Investigation | Appropriate action |
|---|---|---|
| Dev at 50% budget early in the month | Reports by service, newly created resources | Review trends and resource owners |
| Dev at 80%, Cloud Run requests spiking | Legitimate traffic or buggy job? Current max instances? | Throttle test traffic, fix the job, adjust limits after testing |
| Dev at 100% | Billing data latency, lab VMs, Storage, SQL, egress | Prioritize top cost drivers; alert project owner |
| Production cost forecast exceeds budget | Compare against business demand, traffic, pricing, and SLOs | Investigate and optimize deliberately; never arbitrarily stop services |
| Request CPU quota increase due to blocked autoscaling | Current utilization, VM rates, availability requirements | Raise quota only after verifying capacity need and budget |

### 9.4. Metrics to track

- **Cost by project, environment, service, and business unit** (e.g., cost per 1,000 requests or per order).
- **In-period spend burn rate** and variance from forecast.
- **Quota utilization and quota-exhaustion events**, and whether they caused errors or latency.
- **Actual instance counts, vCPUs, storage volume, and outbound transfer.**
- **Alert acknowledgment/resolution rate**, root causes, and actions taken.
- **SLOs and service quality** after applying limits.

## 10. Process for choosing limits in a new GCP project

1. **Define business value and risk tolerance:** which environments can pause safely? What availability does production require?
2. **Estimate costs:** fixed vs. variable components, normal vs. burst traffic, region, storage, egress, and databases.
3. **Set alerts-only budgets first:** right billing scope and thresholds, with accountable responders assigned.
4. **Set quotas and service limits:** based on load-tested capacity, not by mechanically converting a budget dollar figure.
5. **Verify spend cap eligibility if needed:** eligible services only; assess service impact when triggered.
6. **Build runbooks:** investigation steps, decision-makers, risk checks when scaling down, and recovery steps.
7. **Test limit behavior:** simulate load to observe errors, latency, retries, and monitoring; no need to run up a high bill.
8. **Review periodically:** tune quotas, sizing, alerts, lifecycle rules, and costs against actuals.

### A reviewable control template

~~~yaml
# Internal specification example, not a manifest applied directly via Google Cloud API.
environment: development
project_id: store-dev
owner: development-team
monthly_cost_plan:
  currency: USD
  amount: 300
alerts_only_budget:
  actual_threshold_percentages: [50, 80, 100]
  forecast_threshold_percentage: 100
  response_owner: development-team
technical_controls:
  cloud_run_max_instances: "Determined via load testing"
  compute_engine_quota: "Checked and tuned per region"
  storage_lifecycle: "Delete eligible test data after N days"
spend_cap_budget:
  enabled: false
  decision: "Consider only if service and billing account are eligible"
review:
  cadence: weekly
  check_cost_and_reliability_together: true
~~~

This template forces reviewers to separate **estimated spend**, **alert signals**, **consumption guardrails**, and **service-quality risks**. Placeholder strings must be replaced with verified parameters in real deployments.

## 11. Common misconceptions

**"Setting a 100 USD budget means Google Cloud will not charge more."** False for **alerts-only budgets**. Certain **spend cap budgets** can pause new usage on eligible services, yet still have latency and narrow scope.

**"Raising quotas is free because quotas are just numbers."** Changing a quota alone does not create charges, but it **permits higher consumption** if users or autoscalers provision more resources.

**"Hitting the CPU quota stops the VM bill."** Existing VMs can keep running and accruing charges; quotas normally block **new allocations**, not shut down existing resources.

**"Setting Cloud Run max instances = 3 guarantees Cloud Run costs will not exceed three instances."** Instance count does not translate directly into dollars; request volume, duration, resource sizing, active revisions, egress, and companion services all affect spend. Max instances can also be briefly exceeded in some situations.

**"Having Pub/Sub notifications means the system automatically disables billing."** Pub/Sub delivers events. Enforcing actions requires building a separate, authorized, error-handled workflow. Disabling billing automatically carries severe data and availability risks.

**"Protecting the budget means lowering every quota to the minimum."** Overly tight limits can prevent workloads from serving legitimate traffic, causing errors and SLO breaches. Cost control must be balanced against product goals.

## 12. Practice exercises and self-check questions

### Exercise A: choose the right mechanism

For each requirement, identify whether to use a **budget alert**, **quota/system limit**, **service configuration limit**, **spend cap budget if eligible**, or a **combination**:

1. The CFO wants to be notified when total production spend is projected to exceed 20,000 USD/month.
2. The dev team wants lab VMs prevented from scaling up in count indefinitely.
3. A Cloud Run API in staging needs to curb runaway instance scaling.
4. A manager wants new requests to an eligible Cloud Run service paused when that service's estimated gross spend hits a monthly cap, accepting potential downtime.
5. A BigQuery setup needs to stop individual on-demand queries from scanning excessive data.
6. Operations wants to reduce the risk of running out of quota during peak production load.

### Suggested answers

| Item | Mechanism to consider | Rationale |
|---|---|---|
| 1 | **Alerts-only budget forecast + recipients** | Tracks monetary trend; does not auto-stop resources |
| 2 | **Allocation quota and IAM** | Caps new VM allocations and creation permissions |
| 3 | **Cloud Run max instances + monitoring** | Caps instance growth rate; must test error behavior at capacity |
| 4 | **Spend cap budget** for eligible service/project | Can pause new usage; verify scope and overage behavior carefully |
| 5 | **Maximum bytes billed** and quota/job controls where appropriate | Constrains individual queries; does not replace budgets |
| 6 | **Quota monitoring, load forecasting, early adjustment requests** | Prevents autoscaling from being blocked by quota exhaustion |

### Exercise B: analyze claims

Suppose a project has:

- Alerts-only budget **600 USD/month**, 100% actual alert.
- Compute Engine quota **16 vCPUs** in region A.
- Currently running 4 VMs of 4 vCPUs each; plus 100 GiB of storage and a Cloud SQL instance.

**Question:** If the monthly bill forecast is **900 USD** and no more VMs can be created in region A due to quota exhaustion, evaluate these three statements:

1. "CPU quota is maxed out, so the total invoice will stop at 600 USD."
2. "Once the alerts-only budget hits 100%, it will delete a VM."
3. "To reduce the bill, we must investigate specific cost drivers rather than looking only at quotas."

**Solution guide:** (1) False, because quotas do not cap ongoing charges; (2) False, because alerts-only budgets notify rather than delete VMs; (3) True. Inspect VMs, Cloud SQL, storage, networking, logs, operational needs, and whether cost reductions impact service availability.

## 13. Summary and references

**Core principle:** *Budget alerts tell you when to pay attention; quotas and service limits constrain portions of resource consumption; spend cap budgets only pause new usage within eligible service scopes.* Reliable cost control requires combining policies, permissions, monitoring, estimation, and tested actions.

Recommended official documentation:

1. [Create, edit, or delete budgets and budget alerts — Google Cloud Billing](https://docs.cloud.google.com/billing/docs/how-to/budgets) — alerts-only budgets, thresholds, scopes, email, and Pub/Sub.
2. [Manage spend cap budgets — Google Cloud Billing](https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps) — eligible services, mechanics, and spend cap limitations.
3. [Cloud Quotas overview](https://docs.cloud.google.com/docs/quotas/overview) — allocation/rate/concurrent quotas and system limits.
4. [View and manage quotas](https://docs.cloud.google.com/docs/quotas/view-manage) — inspecting usage and adjusting quotas by project and service.
5. [Set maximum instances for services — Cloud Run](https://docs.cloud.google.com/run/docs/configuring/max-instances) — service- and revision-level max instances.
6. [About maximum instances — Cloud Run](https://docs.cloud.google.com/run/docs/configuring/max-instances-limits) — exceptions and cost/reliability trade-offs.
7. [Disable billing usage with notifications — Cloud Billing](https://docs.cloud.google.com/billing/docs/how-to/disable-billing-with-notifications) — warnings on latency and risks of automatically disabling billing.
