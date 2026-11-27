# Building Incident Runbooks and Azure Support Requests

## 1. Objective: Repeatable Incident Response and Effective Coordination with Azure Support

When an application running on Microsoft Azure fails, recovery speed depends on more than one engineer's knowledge. Operations teams must know **where to detect failures, who is accountable, which diagnostic steps come first, when to change the system, what evidence to preserve, and when to engage Microsoft Support**. A clear runbook helps different on-call shifts make consistent decisions, reduces risky actions under pressure, and shortens recovery time.

This lesson belongs to the **Performance and Operations** chapter of the `CLOUD_PROVIDERS_AZURE` module. Scenarios draw on Azure knowledge from subscriptions, resource groups, Microsoft Entra ID, and RBAC to VNets, compute, storage, databases, Azure Monitor, security, quota management, and cost control. The focus is **writing an actionable runbook and assembling an Azure support request with sufficient evidence for support engineers to diagnose**.

After this lesson, you will be able to:

1. Distinguish incidents, alerts, performance issues, configuration change errors, service limits, and Azure platform outages.
2. Author a runbook with triggers, scope, operational permissions, diagnostic order, decision criteria, rollback, expected outcomes, and escalation paths.
3. Leverage Azure Monitor, Application Insights, Log Analytics, Activity Log, Resource Health, and Azure Service Health to isolate faults.
4. Classify technical, quota, and billing support requests; supply impact, UTC timestamps, correlation IDs, resource IDs, reproduction steps, and sanitized evidence.
5. Coordinate internal incident handling with Azure Support communication, track updates, and complete post-incident reviews.

**Scope:** This guide provides operational templates; resource names, configurations, thresholds, and owners in the examples must be adapted to your real system. Access permissions, recovery options, and Azure support entitlements depend on your subscription, product, and organization's support plan.

## 2. What Is a Runbook and How Does It Differ from Architecture Docs?

A **runbook** is an operational guide of ordered steps and explicit conditions enabling humans or automation to handle a specific situation. It answers: "When this alert fires, how does the on-call shift verify and act to restore the service to an acceptable level?"

An architecture document may show an API calling a database, queue, and storage. A runbook must also state:

- **Trigger:** which metric, threshold, symptom, or notification starts the workflow?
- **Impact scope:** which transactions and users are affected, and are SLOs breached?
- **Evidence:** where to inspect metrics, logs, traces, deployments, Resource Health, and Service Health?
- **Decisions:** when to roll back, scale, shift traffic, fail over, or hold steady to gather more data?
- **Authorization:** who may execute actions, who approves them, and who notifies stakeholders?
- **Exit criteria:** what must be verified to declare recovery and transition to post-incident review?

### 2.1. Runbook, Playbook, Checklist, and Post-Incident Review

| Document Type | Purpose | Example |
| --- | --- | --- |
| **Runbook** | Detailed operational steps for a specific known scenario | Handling an HTTP 5xx spike on App Service |
| **Playbook** | Coordination strategy for a broad class of situations | Responding to an Azure region loss or data-tier outage |
| **Checklist** | Reminds responders of mandatory checks | Pre- and post-rollback verification |
| **Dashboard** | Observes technical and business signals | Error rate, latency, CPU, dependency failures |
| **Post-incident review** | Analyzes impact, causes, lessons, and follow-up actions | Why alerts fired late and rollback took 20 minutes |

A good runbook links to dashboards, playbooks, IaC repositories, log stores, and approval workflows; avoid duplicating frequently changing settings across multiple files where they quickly go stale.

## 3. Standardizing Incident Classification and Coordination

An **alert** is a signal to evaluate; not every alert is an incident. An **incident** is an event that has degraded—or risks significantly degrading—a service relative to operational objectives. A brief high-CPU alert is not necessarily an incident if SLOs hold; conversely, a payment failure can be critical even while CPU looks normal.

### 3.1. Classifying by User Impact

You can use an **illustrative internal priority table** like this:

| Internal Priority | Example Impact | Expected Response |
| --- | --- | --- |
| **P0 / Critical** | Critical service down broadly, or severe data-loss risk | Launch incident coordination immediately; prioritize mitigation and comms |
| **P1 / High** | Core function failing for a subset of users; limited workaround | On-call investigates and posts regular status updates |
| **P2 / Medium** | Performance degraded while core features still work with workarounds | Prioritize investigation and schedule fix |
| **P3 / Low** | Minor defect, clarification request, negligible operational impact | File tracking issue and resolve via standard workflow |

This **is not a mandatory mapping** to Azure Support severities. Urgency when opening a support request should reflect **actual impact**, while severity options and support capabilities depend on support plan, issue type, and Azure support UI at creation time.

### 3.2. Roles in an Incident Response Session

| Role | Responsibility |
| --- | --- |
| **Incident Commander (IC)** | Overall coordination, impact assessment, escalation decisions, approving risky changes within delegated authority |
| **Technical Lead / Subject Matter Expert** | Leads investigation of relevant components, evaluates recovery options |
| **On-call Operator** | Runs read-only checks, authorized actions, saves logs, verifies outcomes |
| **Communications Owner** | Manages stakeholder updates, messaging, and update cadence |
| **Scribe / Observer** | Records UTC timeline, hypotheses, changes, and evidence |
| **Azure Support Liaison** | Creates/updates support requests, routes questions to internal specialists, tracks responses |

In small teams, one person may wear multiple hats; however, **production change authority** and the single source for status updates must always remain unambiguous.

### 3.3. Overall Response Flow

~~~mermaid
flowchart TD
    A["Alert / customer error report"] --> B["Verify SLIs, scope, and impact"]
    B --> C{"Does the incident have real impact?"}
    C -->|"Not yet"| D["Monitor / file issue and tune alert"]
    C -->|"Yes"| E["Activate IC, start UTC timeline"]
    E --> F["Gather facts: Azure Monitor, Activity Log, Service/Resource Health"]
    F --> G{"Is there a verified mitigation?"}
    G -->|"Yes"| H["Execute approved change; monitor and roll back if needed"]
    G -->|"Unclear"| I["Investigate further and escalate internally / to Azure Support"]
    I --> H
    H --> J{"Business journeys and SLOs recovered?"}
    J -->|"No"| F
    J -->|"Yes"| K["Stabilize, announce recovery"]
    K --> L["Reconcile data and post-incident review"]
~~~

Investigation and mitigation can proceed in parallel. Do not wait to prove the complete root cause before applying a safe mitigation backed by evidence and authorization.

## 4. Required Fields of an Operational Runbook

Every runbook should carry metadata easy to scan on call. The template below is an **illustrative document structure**, not a proprietary Azure configuration format:

~~~yaml
runbook_id: RB-AZ-APP-5XX
title: "HTTP 5xx spike on Azure API"
version: "1.0"
owner_team: "Application/SRE"
review_interval: "on internal cadence and after every significant change"
trigger:
  - "Error-rate alert exceeds SLO threshold"
  - "Synthetic transactions failing continuously"
service:
  subscription: "<subscription-id>"
  resource_group: "rg-orders-prod"
  primary_region: "<azure-region>"
  application: "orders-api"
dependencies:
  - "App Service or compute tier"
  - "Azure SQL / database"
  - "Key Vault and Microsoft Entra ID"
  - "VNet / Private Endpoint / DNS"
  - "Queue / storage / external integrations"
roles:
  incident_commander: "<role-or-oncall>"
  technical_owner: "<role-or-oncall>"
  support_liaison: "<role-or-oncall>"
links:
  dashboard: "<internal-monitoring-url>"
  deploy_history: "<internal-pipeline-url>"
  escalation_matrix: "<internal-doc-url>"
steps:
  - "Verify impact and scope"
  - "Collect metrics, logs, traces, Activity Log, Service Health"
  - "Select mitigation via decision tree"
  - "Execute approved change"
  - "Verify SLOs, backlogs, and data"
  - "Record timeline, update ticket, post-incident review"
stop_conditions:
  - "Risk of data loss exceeding objective detected"
  - "Missing permissions or unable to determine authoritative state"
  - "Mitigation causes greater impact than original incident"
~~~

Values in `<...>` are placeholders to replace. Production runbooks should live in version control with reviewers and review schedules. Production commands must specify **scope, required permissions**, pre/post-conditions, risks, and rollback steps.

### 4.1. Designing Each Step as a Verifiable Operation

A solid step has five parts:

1. **Precondition:** the operator has selected the exact subscription, region, and resource group and holds the required read or change permissions.
2. **Action:** inspect dashboards, run read-only commands, execute an approved rollback, or engage owners.
3. **Evidence:** capture output (UTC timestamp, query links, operation IDs) while redacting secrets and user data.
4. **Decision branch:** if errors cluster on one deployment, take the rollback branch; if Service Health lists an active event, open the platform coordination branch.
5. **Completion criteria and fallback:** probes healthy and SLOs restored; if failed, abort or revert to prior state per plan.

Avoid vague instructions like "check logs then restart" without specifying **which logs**, **when a restart is safe**, and **how stateful data impact is assessed**.

## 5. Collecting Azure Signals in the Right Order

Operations must separate app code bugs, dependency issues, config changes, quota/throttling, and Azure platform outages. No single dashboard covers every layer.

| Source | What Information Does It Provide? | When to Prioritize? |
| --- | --- | --- |
| **Azure Monitor metrics** | CPU, memory (if telemetry exists), request count, latency, availability, throughput, quotas/service-specific features | Confirming scope, timing, and trends |
| **Application Insights** | Requests, dependencies, exceptions, distributed traces, synthetic availability | API errors, slow endpoints, or dependencies |
| **Log Analytics** | KQL log and telemetry analysis when collection is configured | Querying by resource, request ID, deployment, or time range |
| **Azure Activity Log** | **Management plane** activity such as resource changes, deployments, permissions, and admin events | Suspecting a config change or deployment triggered errors |
| **Resource Health** | Health status and history of **supported** resources | Suspecting a specific VM/resource is unhealthy due to platform issues |
| **Azure Service Health** | Service incidents, planned maintenance, and advisories tied to your subscription/region | Suspecting Azure platform impact on a service or region |
| **Azure Status** | Public, high-level Azure service status | Checking broad global events; never replaces personalized Service Health |
| **Deployment/pipeline logs** | Artifact versions, IaC diffs, rollouts, and change timestamps | Errors began right after a deploy or config update |
| **Business data** | Order/payment success rates, queue backlogs, stuck transactions | Measuring real user impact |

**Activity Log does not automatically contain application or data-plane logs.** Tracing DB queries, API errors, or storage access requires enabling the corresponding diagnostic logs/telemetry before an incident hits. Similarly, an empty Service Health feed does not prove Azure is uninvolved—continue following empirical evidence.

### 5.1. Principles for Building a Timeline

Record timestamps in **UTC**, noting resolution and display time zone; separate:

- `T_impact`: when user transactions began degrading.
- `T_detected`: when monitoring or an engineer detected the issue.
- `T_declared`: when the incident was confirmed and roles assigned.
- `T_mitigated`: when primary impact was reduced.
- `T_recovered`: when SLOs and business metrics recovered over a defined window.
- `T_closed`: when observation, notifications, and incident closeout finished.

Never equate alert firing time with `T_impact` if telemetry shows users were affected earlier. Account for clock skew, sampling, time zones, and event ingestion lag across sources.

**Measuring runbook effectiveness:** for each incident, record `T_impact` to `T_detected` (detection time), `T_detected` to on-call acknowledgment (acknowledgment time), and `T_impact` to `T_recovered` (actual recovery time). Organizations can aggregate MTTD and MTTR across incidents, and compare individual recovery times against **RTO (Recovery Time Objective)** where defined. These are distinct metrics; never use Azure Support ticket closure time in place of when users actually regained service.

## 6. Read-Only Observation with Azure CLI and Kusto

The commands below are **read-only**, suitable for initial triage. Operators must replace placeholders, select the right subscription, and verify permissions. Never paste access tokens, SAS tokens, connection strings, or access keys into logs, support tickets, or screenshots.

### 6.1. Checking Context and Resources

~~~bash
# Active subscription and tenant
az account show \
  --query "{subscription:id,tenant:tenantId,name:name}" \
  -o json

# List subscriptions when verifying context
az account list \
  --query "[].{name:name,id:id,state:state}" \
  -o table

# Inspect resource properties by Resource ID
az resource show \
  --ids "/subscriptions/<subscription-id>/resourceGroups/rg-orders-prod/providers/<provider>/<type>/<name>" \
  -o json
~~~

Use `az account set --subscription ...` only when switching context intentionally after double-checking the environment; acting in the wrong subscription can be worse than the original outage. Prefer explicit `--subscription` flags where supported.

### 6.2. Reading Activity Log in the Incident Window

~~~bash
az monitor activity-log list \
  --resource-group rg-orders-prod \
  --start-time "2026-11-20T09:30:00Z" \
  --end-time "2026-11-20T10:30:00Z" \
  --query "[].{time:eventTimestamp,operation:operationName.value,status:status.value,correlation:correlationId}" \
  -o table
~~~

This queries management events in the resource group during the illustrative window. When spotting a change event, verify the exact resource ID, caller, and diff. **Temporal coincidence alone does not prove causality**; corroborate with app logs, deployment diffs, and before/after metrics.

### 6.3. Listing Supported Metrics for a Resource

~~~bash
az monitor metrics list-definitions \
  --resource "/subscriptions/<subscription-id>/resourceGroups/rg-orders-prod/providers/<provider>/<type>/<name>" \
  -o table
~~~

Metric names vary by resource type and SKU. Only after confirming supported metric names should you run `az monitor metrics list` with appropriate metric names, time windows, and aggregations. Never assume a managed PaaS service shares identical CPU metric names with VMs.

### 6.4. KQL Queries for Request and Dependency Errors

Example using **workspace-based Application Insights** with the `AppRequests` table, grouping errors in 5-minute bins:

~~~kusto
AppRequests
| where TimeGenerated between (datetime(2026-11-20T09:30:00Z) .. datetime(2026-11-20T10:30:00Z))
| summarize
    Total = sum(ItemCount),
    Failed = sumif(ItemCount, Success == false),
    P95DurationMs = percentile(DurationMs, 95)
    by AppRoleName, bin(TimeGenerated, 5m)
| extend FailureRatePercent = iff(Total == 0, real(null), 100.0 * Failed / Total)
| order by TimeGenerated asc
~~~

To identify failing dependencies when the workspace contains `AppDependencies`:

~~~kusto
AppDependencies
| where TimeGenerated > ago(1h)
| summarize
    Calls = sum(ItemCount),
    Failures = sumif(ItemCount, Success == false)
    by Target, Type, AppRoleName
| extend FailureRatePercent = iff(Calls == 0, real(null), 100.0 * Failures / Calls)
| order by Failures desc
~~~

Actual schemas and completeness depend on telemetry config, sampling, and retention; some environments use `requests` or `dependencies` instead. When sending evidence to support, specify the UTC range, query, sampling caveats, and **sanitized results free of sensitive data**.

### 6.5. When to Use Correlation IDs and Traces

A user request may traverse API Gateway → API → database → queue. **Correlation IDs / trace IDs** stitch those hops together. From a failed request, record UTC timestamp, endpoint, status code, operation ID, trace/correlation ID, and failing dependency. For Azure management-plane errors, preserve `correlationId`, `operation ID`, `deployment name`, or request IDs returned in responses. Do not conflate different ID types: each has a distinct origin and purpose.

## 7. Phased Incident Runbook Workflow

A practical runbook branches on evidence. The workflow below serves as a general Azure framework to specialize for App Service, VMs, AKS, Azure SQL, or Storage.

### Phase 1 — Confirm and Scope

**Input:** Alert, ticket, or user report.

**Actions:**

1. Confirm environment, subscription, resource group, region, service, and start time.
2. Check SLIs outside-in: are orders succeeding, and are errors isolated to one endpoint or app-wide?
3. Slice by region, zone, instance, release version, network path, or customer segment to bound scope.
4. Check Service Health and Resource Health for relevant events; do not stop investigating merely because a public status page is green.
5. Open an incident record, set internal priority by impact, and notify on-call roles.

**Output:** Verifiable impact statement, time window, and initial investigative hypothesis.

### Phase 2 — Rapid Evidence-Backed Investigation

Form a short list of high-signal hypotheses, each paired with a discriminating check:

| Symptom | Hypothesis | Discriminating Check |
| --- | --- | --- |
| 5xx spikes post-rollout | Bug in new app/deployment | Compare deploy timestamp, version, exceptions, canary |
| Slow responses and DB timeouts | Saturated connection pool, query, or DB | Dependency latency, connection counts, service metrics |
| Rising HTTP 429s | Rate limit/throttling at API or Azure service | Response headers, error codes, per-service quotas/metrics |
| HTTP 403 on Storage/Key Vault | Changed RBAC, identity, firewall, token, or network | Activity Log, role assignments, sign-in and service diagnostics |
| One zone failing | Backend placement, health probes, or zone event | Probe/instance metrics, Resource Health, Service Health |
| Deployment failure | Quota, Azure Policy, provider registration, RBAC, or template | Deployment operation details, error code, Activity Log |
| Anomalous cost spike | Autoscale, traffic, log ingestion, or new resources | Cost Management and new resources in Activity Log |

Never mutate production just to test a hypothesis when a lower-risk read-only check exists.

### Phase 3 — Mitigate and Verify Risk

Choose an action matching the evidence and approval level:

- **Roll back deployment** if strongly correlated with the release, a safe prior version exists, and database schema compatibility is confirmed.
- **Scale or adjust configuration** if resource saturation is evidenced and quotas/budgets allow; keep before/after metrics to avoid mistaking temporary relief for a permanent fix.
- **Shift traffic / fail over** when a healthy target exists and data, DNS, permissions, and split-brain/data-loss risks are addressed.
- **Throttle traffic, trip circuit breakers, curb retry storms** when a dependency is overloaded.
- **Engage dependency owners** and open Azure Support when evidence points to platform issues, undocumented service behavior, unexpected quota behavior, or unexplained failures after checking permissions and config.

Before acting, verify **approver, expected impact, data at risk, failure indicators, and rollback**. Actions like deleting resources, forced async data failover, or restoring backups into production carry hard-to-reverse consequences; execute strictly per approved runbook and authority.

### Phase 4 — Verify Recovery

Never close an incident merely because a rollback command returned success or a resource shows Running. Verify:

- Business transaction success rate and p95 latency across the agreed observation window.
- Dependency errors, connection pools, queue backlogs, database transactions, and background workers.
- Integrity of previously acknowledged data, with no duplicates from retries or failovers.
- Proper traffic distribution across zones, instances, and ingress paths; alerts returned to healthy thresholds.
- Removal of temporary security/cost risks—such as widened firewalls, oversized replica counts, or emergency resources.

**Output:** Documented recovery timestamp, final state, and SLO evidence. If limitations remain, document degraded-mode bounds and an expiration deadline.

### Phase 5 — Post-Incident Review and Runbook Improvement

Once stable, assemble the timeline: what changed, what failed, which actions restored service, and what remains unproven? Assign owners, deadlines, and closure criteria for every improvement; consider an action item closed only once **verified through testing or a drill**.

## 8. Complete Runbook Example: Orders API Returning 503 After Deployment

**Hypothetical scenario:** The `orders-api` runs on Azure App Service in `rg-orders-prod`. Following a deployment, `POST /orders` returns elevated HTTP 503s, disrupting order placement. Dependencies include Azure SQL, Key Vault, and a queue. Application Insights and an app rollback workflow are in place.

**Runbook objective:** restore order placement success rate to SLO, preserve order data integrity, and define when to open an Azure Support ticket. Addresses and numbers are illustrative only.

### 8.1. Triggers and Minimum Metadata

~~~yaml
runbook: RB-ORDERS-503
owner: "Orders / SRE"
trigger:
  - "5xx exceeds approved alert threshold"
  - "Synthetic POST/GET check failing"
preconditions:
  - "Confirm target subscription and App Service"
  - "Request/dependency dashboard and rollout history accessible"
  - "Rollback decision maker available per release process"
safety:
  - "Do not execute real payment transactions"
  - "Never include tokens, connection strings, or PII in reports"
  - "Never run backward database migrations without data impact review"
completion:
  - "SLIs recovered across observation window"
  - "No duplicate orders or queue backlog above threshold"
  - "Timeline and links to evidence recorded"
~~~

### 8.2. Branching Execution

**Step 1 — Observe:** inspect error rates and dependency failures before and after the rollout. Capture several `operation_Id`/trace IDs from 503 requests. Pin `T_impact`.

**Step 2 — Inspect changes:** align when the new artifact went live, app setting edits, instance counts, and Activity Log events. If deployment timing coincides with Azure SQL dropping connections across all versions, investigate the dependency rather than blaming app code prematurely.

**Step 3 — Check platform:** review Azure Service Health, Resource Health where available, App Service metrics, and scaling/cold-start events. If the resource appears unhealthy due to a platform event or hard-to-reproduce fault, prepare a support request with timestamps, resource ID, and request/correlation IDs.

**Step 4 — Choose mitigation:**

| Observed Condition | Candidate Decision |
| --- | --- |
| New version spikes errors, prior version healthy, DB rollback-compatible | Trigger rollback via approved pipeline/slot strategy |
| Azure SQL or Private Endpoint failures across all versions | Prioritize database/network/DNS checks; avoid blind rollback |
| 503s due to backend overload; CPU, pools, or queue depth over threshold | Shed traffic / bound retries; scale if quotas and budget permit |
| Root cause unclear while high impact persists | Escalate to IC, dependency teams, and Azure Support with evidence |
| Recovery risks data loss or ambiguous transaction state | Pause mutating actions; consult data owner on safe path |

**Step 5 — Verify:** run synthetic create-order and read-order checks with idempotency keys. Observe for at least one full SLO window; verify order counts, queue backlog, and dependency errors. Record the known-good deployment ID, recovery timestamp, and any active workarounds.

**Step 6 — Communicate:** share recovery level, remaining degraded features, and next update time. After closeout, launch the post-incident review and update the runbook.

### 8.3. Sample Timeline for Reference

| UTC Time (Hypothetical) | Event | Evidence |
| --- | --- | --- |
| 09:55 | Deploy version `v2.14` | Pipeline release log |
| 09:59 | 5xx rises, new orders begin failing | Synthetic transaction, `AppRequests` |
| 10:01 | Azure Monitor alert fires | Alert record |
| 10:04 | IC declares P1; assigns investigation | Incident timeline |
| 10:07 | Azure SQL dependency healthy; errors isolated to v2.14 | Distributed traces, metrics |
| 10:12 | Rollback to v2.13 approved | Change record |
| 10:17 | Traffic served by prior version | Deployment status, ingress logs |
| 10:21 | Order transactions meet SLO across verification window | Business SLI, synthetic test |

This example shows rollback reduced impact. Still, **root cause remains unproven** until comparing the two builds and error patterns. You do not need Azure Support merely to confirm a known application bug, yet support is warranted when signs point to Azure service issues, unexplained platform behavior, or platform-level expertise.

## 9. When Should You Open an Azure Support Request?

An **Azure Support request** is a case where Microsoft and your organization collaborate on an Azure service or account issue. Opening a ticket is **one branch of incident response**, not a substitute for incident ownership, mitigation actions, or internal communication.

Common request types:

| Request Type | When to Use | Prepare Ahead |
| --- | --- | --- |
| **Technical issue** | Azure service failing abnormally, unexpected behavior, deep diagnosis needed | Resource ID, region, timestamps, error codes, request/correlation IDs, impact, repro steps |
| **Service and subscription limits / quota** | Need higher vCPU or other quota; hitting allocation limits | Subscription, region, quota/SKU type, current limit, requested limit, business rationale, target date |
| **Billing / subscription management** | Invoice disputes, payment or subscription administration issues | Appropriate billing scope/account, billing period, relevant charges; never expose sensitive payment details in unguarded logs |
| **Account / access-related** | Access, permission, or account issues requiring support team review | Tenant/subscription, safely described identity, failing step, error code; use official authenticated channels |

**Distinguish entitlements:** billing or subscription management tickets follow different support paths from technical support. Eligibility to open technical tickets, contact limits, severities, channels, and response targets depend on your **Azure support plan** and subscription/partner policies. Never assume every subscription includes highest-urgency technical support.

### 9.1. Before Creating a Support Request

1. Check **Azure Service Health** and active advisories for the relevant service, region, and subscription.
2. Inspect the specific resource/failing path via metrics, logs, Resource Health, and Activity Log.
3. Look for recent changes in deployments, configs, RBAC, or Policy; document checks already run.
4. Confirm permissions to create support tickets at the target scope (e.g., appropriate Azure RBAC roles with `Microsoft.Support/supportTickets/write` per configuration) plus read access to the subscription/resource. **Never grant Owner just to open tickets** when a narrower role suffices.
5. Prepare impact summary, workarounds, UTC timestamps, resource IDs, and traces sufficient for support investigation.

During severe incidents, **do not wait to assemble every possible log** before opening a ticket; submit initial impact and available evidence, then update as new facts emerge. Keep an internal owner monitoring the ticket while continuing mitigation.

### 9.2. Portal Creation Flow

Exact UI labels may evolve, but the typical flow is:

1. Sign into the **Azure Portal** with an authorized account and select the target tenant/subscription.
2. Open **Help + support** or the resource/subscription support blade and select **Create a support request**.
3. Select problem classification, service/resource, and subscription; review recommended self-help solutions if shown.
4. Enter **Problem description**, permitted impact/severity, environment, and technical details.
5. Choose support plan/tier options if prompted and entitled; provide contact details, availability window, and preferred channel.
6. Review every field and attachment; strip secrets and unnecessary PII; submit.
7. Save the **support request ID**, portal link, submission time, and contact person in the incident record; track updates and supply follow-up findings.

Some quota requests route to the **Usage + quotas** experience or a dedicated quota workflow. Use whichever workflow Azure presents for that quota type rather than assuming every limit uses the same support form.

### 9.3. Severity Levels and How to Choose

Azure Support severities reflect **business impact and urgency** per support type and plan. Some channels display levels such as A/B/C or equivalents, yet **exact definitions, availability, and response targets depend on your actual subscription and support plan**.

When choosing severity, provide verifiable context:

- How many users, transactions, or production workloads are impacted?
- Is the system completely down, partially degraded, or limited to a test environment?
- Does an acceptable workaround exist, and what are its security, data, or performance trade-offs?
- Is there active risk of data loss, revenue interruption, or SLA breach?
- Is your engineering team staffed to collaborate continuously if handled at high urgency?

Never pick top severity hoping for a faster answer to a routine question, and never understate real production outages.

## 10. What Makes a High-Quality Azure Support Request?

Support engineers need to know **which resource is affected, when errors occurred, what the impact is, whether it reproduces, and what was already tried**. Keep the ticket concise enough to scan quickly yet precise enough to look up Azure-side telemetry.

### 10.1. Recommended Fields

| Field | Helpful Format |
| --- | --- |
| **Subject** | `Azure App Service — HTTP 503 spike after 09:59 UTC in [region]` |
| **Issue type & service** | Technical / App Service, Azure SQL, Networking, Storage, etc. |
| **Subscription & tenant** | Real IDs submitted via the official support channel; avoid scope mix-ups |
| **Resource** | **Full ARM resource ID**, resource group, region, SKU/tier, zone if relevant |
| **Impact** | Affected component, prod/staging environment, error rate, user count, business journey |
| **Timestamps UTC** | Onset, detection, latest repro, change timestamp, mitigation timestamp |
| **Error** | HTTP status, Azure error code, exact sanitized error message |
| **Identifiers** | `x-ms-request-id`, `x-ms-correlation-request-id`, `correlationId`, operation/trace IDs if returned |
| **Reproduction** | Concise steps with sanitized test inputs; reproduction frequency |
| **Checks performed** | Monitor/KQL, Health, Activity Log, deployments, network/RBAC/quotas |
| **Mitigation / workaround** | What was tried, outcome, remaining risk, whether impact persists |
| **Expected vs. actual** | Expected behavior per architecture/docs vs. observed behavior |
| **Contact & availability** | Owner, time zone, channel, response hours, bridge link if appropriate |
| **Evidence** | Screenshots, redacted logs, sanitized traces, timestamps, valid internal query references |

**Not every Azure service emits identical headers or correlation IDs.** Include only identifiers genuinely present in responses/logs, note each ID's source, and never fabricate placeholder IDs as if real.

### 10.2. Keeping Support Data Safe

Tickets may require resource IDs, tenant/subscription IDs, or resource names for investigation. These are operational metadata governed by organizational permissions, **not secrets**. Always transmit through **official support channels** and follow internal security policies.

Never attach:

- Passwords, client secrets, access keys, SAS tokens, bearer tokens, refresh tokens, or connection strings with credentials.
- Payment card data, customer PII, personal payloads, or unredacted sensitive logs.
- Full environment-variable dumps or secret-bearing config files when a short error excerpt suffices.
- Screenshots exposing unrelated sensitive details outside the error area.

When sharing network traces or diagnostic packages, inspect contents, time windows, and Azure Support's upload instructions. Authorize extra telemetry collection or temporary access only via organizational approval, with a clear owner and bounded data scope.

## 11. Reusable Technical Support Request Template

Illustrative example for an API experiencing HTTP 503s, intentionally using **placeholders and hypothetical figures**. Never submit verbatim as a real incident.

~~~text
Subject:
Azure App Service | Production HTTP 503 | <region> | 2026-11-20 09:59 UTC

Issue type:
Technical issue — Azure App Service

Subscription:
<subscription-id>

Resource:
 /subscriptions/<subscription-id>/resourceGroups/rg-orders-prod/
 providers/Microsoft.Web/sites/orders-api
(Wrapped above for readability; the actual ID is one continuous string.)

Region / SKU:
<region> / <app-service-plan-sku>

Business impact:
- Production orders-api, POST /orders affected.
- Approximately 28% of requests returned HTTP 503 between
  09:59 and 10:17 UTC.
- Customer order creation degraded; read-only endpoints remained available.
- No evidence of acknowledged order loss at the time of submission.
- Incident owner: <role / safe contact channel>.

Expected behavior:
POST /orders should accept a valid test transaction and return
the application's documented successful response within SLO.

Observed behavior:
503 responses with representative error code/message:
<sanitized-error-text>

UTC timeline:
09:55 Deployment v2.14 completed.
09:59 First observed impact via synthetic transaction.
10:01 Azure Monitor alert fired.
10:07 Dependency metrics appeared healthy.
10:12 Rollback approved.
10:17 Traffic started serving v2.13.
10:21 Success rate returned to SLO.

Correlation/request evidence:
- Example failed request time: 10:03:21 UTC
- App Insights operation ID: <sanitized-operation-id>
- Azure response request ID (if present): <actual-response-id>
- Deployment name/correlation ID (if relevant): <actual-id>
- Sanitized logs and metric snapshot: <attachment-or-reference>

Troubleshooting performed:
1. Checked Azure Service Health and Resource Health.
2. Correlated 5xx with deployment timeline.
3. Reviewed Application Insights requests and dependencies.
4. Confirmed database connectivity for healthy endpoints.
5. Rolled back to v2.13; errors decreased.

Current state:
Service recovered after rollback; root cause under investigation.
No further configuration changes planned until evidence review.

Assistance requested:
Please help determine whether platform-level App Service events,
instance behavior, or service-side diagnostics contributed to the
503 spike in the affected window, and recommend additional evidence
needed to distinguish platform behavior from the application release.

Availability:
<contact / timezone / preferred channel / on-call bridge>
~~~

**Key point:** The template states **hypotheses** and questions for support rather than claiming Azure is broken without proof. If the incident is ongoing, update `Current state` with live impact and active workarounds.

### 11.1. Quota Request Example

When a workload cannot deploy VMs due to quota:

~~~text
Issue: Quota increase / service and subscription limits
Subscription: <subscription-id>
Region: <azure-region>
Resource family/SKU: <VM family or exact quota category>
Current quota: <verified current limit>
Current usage: <verified usage>
Requested quota: <required limit>
Business reason: Planned capacity for 2 additional availability zones
Requested timeline: <business date>
Failure evidence: <error code, UTC timestamp, deployment operation ID>
Alternatives assessed: <supported SKU/region/capacity changes>
Contact: <responsible team and approved channel>
~~~

Distinguish **sufficient quota yet no physical VM capacity available in the zone/SKU** from **quota limit reached**: the two have different causes and remedies. Requesting a quota increase does not guarantee immediate physical VM allocation for a given region and SKU.

## 12. Coordinating Internal Incidents with Support Requests

Runbooks must clarify the operations team's responsibilities after opening a ticket. Filing a ticket does not hand incident command over to Microsoft.

~~~mermaid
sequenceDiagram
    participant U as User / Synthetic probe
    participant IC as Incident Commander
    participant OPS as Technical team
    participant SUP as Azure Support
    U->>IC: Error report / alert
    IC->>OPS: Verify impact, gather evidence
    OPS-->>IC: Scope, UTC, mitigation, and hypothesis
    IC->>SUP: Create support request with current facts
    par Parallel investigation
      SUP-->>IC: Request extra info / diagnostic guidance
      OPS->>OPS: Continue approved mitigation
    end
    OPS-->>IC: Verification / recovery results
    IC->>SUP: Update status and new evidence
    IC->>U: Communicate recovery level and remaining limits
    SUP-->>IC: Additional analysis / ticket resolution
    IC->>IC: Postmortem, action items, and closeout
~~~

### 12.1. Status and Update Cadence

Maintain **one internal incident record** as the source of truth for impact and decisions. The support ticket tracks Microsoft coordination.

A compact tracking table helps prevent dropped handoffs:

| Field | Sample Value |
| --- | --- |
| Internal incident ID | `INC-2026-0118` |
| Azure Support request ID | `<ticket-id>` |
| Internal priority | `P1` |
| Azure support severity | `level selected and confirmed in portal` |
| Ticket owner | `on-call / support liaison` |
| Last update UTC | `2026-11-20 10:45Z` |
| Next action | `Send operation ID of failed request` |
| Next update due | `per internal process cadence` |
| Mitigation state | `Rollback complete, monitoring` |

When updating Support, highlight **what changed**, timestamps, and outcomes: "After rollback at 10:17 UTC, error rate dropped from 28% back below SLO; still verifying whether 503s involved any platform event." Avoid dumping duplicate logs without explanation.

### 12.2. When to Escalate Further

Consider escalation when the incident breaches internal recovery targets, impact expands, new evidence reveals data/security risks, or coordination progress lags operational need. Update the support ticket with **updated business impact**, mitigation status, and engineering availability. Escalation paths depend on available support entitlements; never promise that raising severity automatically resolves the fault.

If an error compromises information security or suggests an attack, trigger your **organization's security incident process** too. Dedicated security reporting channels may apply—never treat it solely as a performance issue.

### 12.3. Closing the Ticket and Knowledge Management

Before closing a ticket, archive: verified root cause (if confirmed), applied fixes, how resolution was verified, cost/impact notes, and relevant docs or service limits to remember. If root cause remains unconfirmed, record **unknown / pending verification** with follow-up monitoring—never fabricate closure details.

Use cleared findings to update runbooks, dashboards, alerts, and IaC. Link the ticket ID and evidence inside the internal incident record so future shifts can trace history.

## 13. Post-Incident Review and Runbook Improvements

Once the system stabilizes, conduct an evidence-based **post-incident review** (PIR). A blameless approach uncovers systemic gaps rather than concluding "on-call was slow" or "Microsoft broke it."

### 13.1. Post-Incident Review Template

~~~markdown
# Incident Review: <incident-id>

## Impact
- Service, region, affected users:
- T_impact to T_recovered (UTC):
- Missed SLIs/SLOs or failed transactions:
- Data integrity / security impact:

## UTC Timeline
| Time | Event | Evidence | Action/Decision |
| --- | --- | --- | --- |
| ... | ... | ... | ... |

## Root Cause and Contributing Factors
- Trigger:
- Pre-existing conditions:
- How detection/coordination performed:
- What still lacks evidence:

## Mitigation and Recovery
- Options considered, tested, and outcomes:
- Why the final mitigation was chosen:
- Remaining risks and monitoring plan:

## Azure Support
- Support request ID:
- Evidence supplied:
- Verified analysis or guidance:

## Corrective Actions
| ID | Action | Owner | Deadline | Validation |
| --- | --- | --- | --- | --- |
| ... | ... | ... | ... | ... |
~~~

### 13.2. Turning Findings into Verifiable Action Items

| Finding | Proposed Change | Acceptance Evidence |
| --- | --- | --- |
| 5xx alert fired late | Add synthetic transactions and SLI-based alerts | Inject controlled fault in drill; measure detection time |
| Queried wrong subscription during triage | Put tenant/subscription/resource IDs in runbook; scope read commands | Runbook review and tabletop exercise on exact resource |
| Quota deployment failure caught only at release | Add preflight quota and region/SKU checks in pipeline | Pipeline warns pre-deploy; tested over-quota case |
| Rollback delayed over unknown migration compatibility | Design rollback-safe releases and schema checklist | Rehearse rollback in staging with representative data |
| Support repeatedly asked for timestamps/IDs | Standardize evidence bundle from alerts, traces, Activity Log | Mock ticket has all fields with zero leaked secrets |
| Dependency errors confused with API bugs | Add dependency metrics and distributed tracing | KQL and traces isolate failing tier |
| System recovered yet ticket left stale/untracked | Assign Support Liaison, update cadence, closure rule | Incident audit confirms owner and closure evidence |

Close an action item only when **actual behavior is verified**. Merging a PR, adding a panel, or editing one runbook line is insufficient until proven to detect or mitigate the scenario.

## 14. Regular Runbook Drills

A written runbook that goes untested quickly rots as Azure services, SKUs, networks, roles, or architectures change. Match drill depth to risk:

1. **Tabletop:** on-call receives a simulated alert, walks through decisions, locates resource IDs/dashboards, and identifies when to engage Azure Support.
2. **Read-only drill:** using a test environment or historical incident, rerun Azure Monitor, KQL, and Activity Log queries and verify access permissions.
3. **Controlled failure injection:** inject a bounded fault in staging (e.g., disable a test backend or deploy a faulty test build) and execute mitigation plus rollback.
4. **Support-request simulation:** draft a ticket using sanitized mock logs, verifying timestamps, correlation IDs, impact, and sharp questions before needing it live.
5. **Review:** measure MTTD, impact-confirmation time, mitigation-selection time, time back to SLO, steps requiring non-on-call specialists, and unclear doc steps.

For mutating drills, define owners, staging scope, stop triggers, synthetic data, rollback plans, and temporary resource cleanup. You do not need to disrupt production to test diagnostic workflows; isolated test environments catch most gaps.

### 14.1. Runbook Scorecard

| Criterion | Passing Bar |
| --- | --- |
| Easy to find and current | On-call locates approved version with owner and review date |
| Accurate scope | Explicitly states subscription, resource group, region, service, and permissions |
| Measurable triggers | Metric/alert and threshold tie directly to business impact |
| Data-driven diagnostics | Specifies how to pull logs, metrics, traces, Health, and deploy history |
| Controlled mitigation | Includes preconditions, approver, impact, rollback, and stop criteria |
| End-to-end verification | Checks transactions and data, not just resource Running state |
| Timely Microsoft Support | Knows when to file, appropriate severity, and safe data bundle |
| Useful postmortem | Includes timeline, causes/unknowns, owners, and validation evidence |

## 15. Capstone Exercise: Building a Runbook and Support Request for an Azure App

**Scenario:** The `orders-api` app runs in a production subscription on Azure App Service using Azure SQL, Key Vault, private networking, and Application Insights. Starting at 14:00 UTC, 20% of `POST /orders` calls return HTTP 503. On-call gets paged at 14:03 UTC. Azure Service Health shows no obvious platform incident; an app settings deployment ran at 13:55 UTC. Customers have not reported lost orders yet, though transactions are delayed.

**Task:** Produce an actionable runbook and an **unsubmitted** draft support request. The team's operational goal is restoring order placement within 30 minutes without losing or duplicating confirmed orders.

### Task 1 — Complete the Runbook

Using the templates in Sections 4 and 8, fill in owner, dashboard/CI-CD links, sample subscription and resource IDs, triggers, permissions, read-only checks, deployment/app-settings checks, database dependency checks, and rollback/scale/network branches.

Include at least **two hypothesis-discriminating checks**—for example, "new API bug" vs. "Azure SQL unresponsive." State when rollback is permitted and when mutations must pause for data-owner sign-off.

### Task 2 — Build the Evidence Package

Using synthetic data and hypothetical UTC timestamps, compile:

- `T_impact`, `T_detected`, change timestamps, mitigation timestamp, and `T_recovered`.
- Well-formed Resource ID, region, tier/SKU, and failing endpoint.
- Before/after error rate, p95 latency, and dependency failure metrics.
- An illustrative operation/trace ID **explicitly labeled hypothetical**, plus logs stripped of secrets and PII.
- Before/after order reconciliation results.

### Task 3 — Draft the Support Request

Using the Section 11 template, select technical support, fill in business impact, UTC timeline, expected/actual behavior, checks run, workarounds, and **specific questions for Microsoft**. Note that support plan/severity must be verified against the subscription; never promise a fixed response SLA.

### Task 4 — Close the Learning Loop

Assume rollback restored transaction success rate to target. Distinguish **service restored** from **root cause confirmed**. Write a PIR snippet with timeline, open unknowns, three action items with owners/validation, and runbook/monitoring updates. Draft a short status update for non-technical stakeholders.

**Completion criteria:** another engineer can follow the runbook without guessing scope or risky decisions; the support ticket holds enough evidence for support triage; sensitive data is redacted; outcomes are verified with business transactions; and corrective actions include re-testing.

## 16. Mistakes to Avoid

| Mistake | Why Harmful | Replace With |
| --- | --- | --- |
| Writing only "restart service if failing" | Masks root cause, adds downtime or state risk | Preconditions for restart, scope, approver, post-check criteria |
| Declaring an Azure outage from one HTTP 500 | 500s can stem from code, dependencies, or config | Cross-check traces, Activity Log, Health, and multi-resource errors |
| Watching only public Azure Status | Omits subscription- and resource-specific events | Combine Service Health, Resource Health, and app telemetry |
| Filing "Azure is very slow, please fix" | Lacks actionable scoping data | Supply impact, region, UTC, resource ID, error codes, steps, IDs |
| Pasting unredacted full logs | Can leak credentials and user data | Send redacted relevant excerpts through official channels |
| Assuming the ticket runs the incident | Drops internal mitigation and comms | IC retains command; Support Liaison tracks ticket |
| Always picking top severity out of habit | Misrepresents impact and ignores plan rules | Choose by real business impact and actual support entitlement |
| Treating successful rollback as root cause | Fault may stem from environment or another change | Form hypotheses, gather evidence, and re-test |
| Closing tickets when alerts clear | Leaves backlogs, lost orders, silent failures | Verify SLOs, data, queues, costs, and residual impact |
| Runbooks lacking owners or versions | Procedures rot as infrastructure changes | Review periodically and after major incidents or changes |

## 17. Applied Summary

An **Azure runbook** works when it defines triggers, accountable owners, user-centric metrics, layered evidence sources, decision branches, approved changes, and recovery criteria. An **Azure support request** works when it accurately captures business impact, resource and scope, UTC timestamps, error codes/correlation IDs, troubleshooting already performed, and focused questions for Microsoft specialists.

Together they form a closed operational loop: **detect → assess impact → investigate → mitigate → coordinate support → verify recovery → postmortem and improve**. Practiced and kept current with Azure architectural changes, runbooks enable evidence-based, shift-consistent responses that protect data, security, performance, and cost.
