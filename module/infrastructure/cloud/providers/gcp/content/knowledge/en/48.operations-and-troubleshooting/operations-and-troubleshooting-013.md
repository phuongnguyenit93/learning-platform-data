# Monitoring Service Health and Working with Google Cloud Support

When a Cloud Run API sees rising 5xx errors, a Cloud SQL database drops connections, or multiple VMs fail to provision, operations teams must answer two questions in parallel: **how severely is our own service affected?** and **is an underlying Google Cloud infrastructure incident involved?** Google Cloud Service Health, Personalized Service Health, Cloud Monitoring, and Cloud Customer Care each provide distinct perspectives for answering those questions. Using the right source, priority level, and Support escalation workflow shortens time-to-detect, limits user impact, and avoids misattributing root causes.

This lesson belongs to the **Operations and Troubleshooting** chapter of the **CLOUD_PROVIDERS_GCP** module. Within the context of operating Google Cloud from projects, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage, and databases, learners will connect Service Health telemetry with logs, metrics, traces, SLOs, mitigations, and Google's support process. Examples feature a multi-tier Java/Spring Boot workload, though the principles apply across applications.

After this lesson, learners will be able to:

- Distinguish public Service Health, Personalized Service Health, Cloud Monitoring resource health, and support cases.
- Query events by project, product, region, timestamp, relevance, event state, and update history.
- Configure least-privilege IAM to view Service Health and manage support cases.
- Build proactive alerts using Service Health logs and Cloud Monitoring notification channels.
- Triage incidents by user impact, test infrastructure-fault hypotheses, and choose safe mitigations.
- Gather evidence for complete Customer Care support cases, choose appropriate priorities, and track responses.
- Distinguish priority upgrades from escalations, knowing when to hand off 24/7 and when to focus on internal fixes.
- Build runbooks, timelines, handoffs, incident reviews, and fallbacks when dashboards or service APIs are unavailable.

## 1. Four Layers of Telemetry to Combine

| Source | Question Answered | Key Limitation |
|---|---|---|
| Public **Google Cloud Service Health** | Is there an announced broad Google Cloud incident? | Not an exhaustive list of every single-project incident |
| **Personalized Service Health (PSH)** | Which Google Cloud events may affect our project/organization? | Relevance is a triage hint, not a substitute for measuring real impact |
| **Cloud Monitoring, Logging, Trace, and SLOs** | How are our application and users actually impacted? | Detects symptoms without proving Google-side root cause |
| **Cloud Customer Care / Support case** | How do we submit evidence, request help, and coordinate remediation? | Depends on support offering, IAM permissions, and impact/priority |

An SRE should never glance at the public status page and conclude "Google Cloud is healthy" just because no global incident appears. Narrow regional events or incidents affecting a subset of projects appear in Personalized Service Health; equally, customer misconfigurations cause outages that Service Health never reports.

### 1.1. Public Service Health

Public portal: **https://status.cloud.google.com/**. This is a quick check for broad Google Cloud incidents, affected products, and locations. You can inspect products/regions, historical published incidents, and RSS feeds for fallback monitoring.

Characteristics:

- Accessible without project IAM permissions.
- Useful during broad Google Cloud Console or IAM disruptions.
- Details are published and refined iteratively as investigation progresses.
- Does not guarantee every isolated failure, every project, or every timeframe gets a public incident.
- Save the incident URL/event ID and check timestamp in your internal incident record.

### 1.2. Personalized Service Health

Personalized Service Health lists events scoped to your project or organization, highlighting relevance, products, and locations. Its UI, Service Health API, and Cloud Logging records can feed internal dashboards, alerts, and response workflows.

PSH is your primary channel for Google Cloud events relevant to your organization's environment; the public status page serves as a supplement and fallback.

### 1.3. Application Telemetry Is Irreplaceable

A Spring Boot app can return 500s due to an exhausted connection pool while Cloud SQL is healthy. Conversely, Cloud SQL can experience a disruption while the API keeps serving via caching or failover. You need all of:

- Request rate, error rate, and p95/p99 latency.
- Cloud Run revision/instance errors, GKE Pod restarts, Compute Engine instance health.
- Cloud SQL connection errors, query latency, replication lag, or database status.
- Cloud Storage/Pub/Sub errors and backlogs if workloads depend on them.
- Logs/traces carrying correlation IDs, timestamps, and regions.
- Business SLIs such as failed orders, slow checkouts, or growing processing backlogs.

**Define internal incidents by user impact and SLO burn**, not by whether Google has posted an event.

## 2. Anatomy of a Service Health Event

A Service Health event describes a disruption affecting a Google Cloud product. Typical fields include:

| Field | How to Use It |
|---|---|
| Event ID | Reference key for incident timelines and Support cases |
| Title / description | Summary of symptoms published by Google |
| Category | Event classification per current API, e.g., `incident` |
| Event state | Overall state, typically **Active** or **Closed** |
| Product(s) | Potentially impacted Google Cloud services |
| Location(s) | Affected regions/zones or scopes |
| Relevance | Estimated relevance to the project based on Google's telemetry |
| Start / update / end time | Milestones across the incident timeline |
| Workaround / diagnosis | Published explanation or interim workaround, if available |
| Full history / report | Update chronology and post-incident report, if published |

Not every event immediately includes a root cause or estimated recovery time. When facts are unavailable, record **"Google investigating / not yet published"** rather than speculating on technical causes.

### 2.1. Event State and Granular Status

- **Active:** the overall event remains under observation; one or more products/locations may still be recovering.
- **Closed:** the overall event has concluded per Google's assessment or merged into another event.
- **Affected / Resolved** at product-location level: shows individual regions recovering while the overall event remains Active.

If Cloud SQL in region A is marked Resolved while region B remains Affected, do not assume all regions recovered. Conversely, a Closed event does not guarantee your application automatically recovered queues, connection pools, caches, or failed transactions.

### 2.2. Relevance Is Not Absolute Proof

Relevance indicates estimated relevance between an event and your project; docs/APIs may show values such as **IMPACTED** or **RELATED**. When you spot an event:

1. Check which projects actually use the affected product and location.
2. Correlate event timestamps against when SLIs degraded.
3. Compare error codes and observed symptoms.
4. Rule out your own networking, IAM, quotas, deployments, and dependencies.
5. Check whether the event lists a workaround or fresh updates.

A `RELATED` event does not mean 100% of resources in your project are broken. Equally, having no matching event does not prove the bug is definitely in your code.

### 2.3. Timestamps and Timezones

Record timestamps in **ISO 8601 with UTC offset**, preferring UTC across distributed teams—for example, `2026-11-19T08:15:00Z` or `2026-11-19T15:15:00+07:00`. Distinguish:

- When user impact began.
- When monitoring fired alerts.
- When the Google Cloud event was published.
- When mitigations deployed and SLIs recovered.
- When Google closed the event or published an incident report.

Never equate Google's publication timestamp with when your application outage started.

## 3. Accessing Service Health by Project

### 3.1. Prerequisites and IAM

For a project with billing and proper permissions, operations teams can be granted access to the Service Health dashboard/API via:

| Purpose | Role / Permission |
|---|---|
| View project events | `roles/servicehealth.viewer` |
| Read events via API | `servicehealth.events.list` and `servicehealth.events.get`, plus required location permissions |
| Administer Service Health | `roles/servicehealth.admin` only when genuinely required |
| Read Service Health logs | Appropriate Cloud Logging permissions |
| Create log-based alerts and notification channels | Appropriate Cloud Monitoring/Logging roles for policies/channels |

Personalized Service Health Viewer is read-only. **Never grant Project Owner/Editor just to view service status.** If users should view events without seeing impacted resource names in Preview features, create a custom role excluding resource-level impact permissions per Google documentation.

Example IAM binding run by an administrator (replace placeholders):

~~~bash
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="group:oncall@example.com" \
  --role="roles/servicehealth.viewer"
~~~

This example is not a default command to run blindly in production; administrators must verify group identity, scope, and IAM policies before granting.

### 3.2. Viewing in the Console

1. Open Google Cloud Console and select the **exact affected project**.
2. Go to **Tools → Service Health**.
3. Inspect both Active and Closed events linked to the project.
4. Filter/focus on the product, location, and relevance under investigation.
5. Open the event: read Overview, Full Incident History, start/update/end timestamps, workarounds, and per-location status.
6. If a post-incident report is published later, review documented root causes and preventive actions.
7. Archive the event ID, URL, and timestamps in your internal incident ticket.

In multi-project organizations, inspect your workload's entire dependency chain—not just the Cloud Run project: databases, Shared VPCs, networking, and data platforms may reside in other projects.

### 3.3. Using the Service Health API

The Service Health API lets you list and retrieve events by project or organization to feed operational tooling. You need:

- **Service Health API** enabled on the querying project per documentation.
- An identity holding `roles/servicehealth.viewer` or an equivalent custom role.
- In certain API contexts, service invocation permissions and billing/project setup per documentation.
- Pagination, filtering, and backoff handling in API clients.
- Tracking event IDs and version/update timestamps so updates do not spawn duplicate incidents.

Consult current official API/CLI docs directly, as surfaces and fields can evolve across v1/v1beta versions. Resource-level impacted-resource lookups may be in **Preview**, so do not assume complete coverage across all products.

## 4. Proactive Service Health Monitoring via Cloud Logging

Waiting for an SRE to log into the Console delays detection. Personalized Service Health can emit logs whenever events are created or updated, integrating with Cloud Monitoring log-based alerts.

### 4.1. Alerting Path

~~~mermaid
flowchart LR
    G[Google Cloud service event] --> PSH[Personalized Service Health]
    PSH --> L[Cloud Logging EventLog]
    L --> AP[Cloud Monitoring alert policy]
    AP --> CH[Notification channel]
    CH --> OC[On-call / ticket / incident]
    OC --> TRI[Triage impact + mitigation]
~~~

Notification channels can be email, Slack, PagerDuty, webhooks, Pub/Sub, or other Cloud Monitoring channels configured by your org. When an alert fires, Monitoring creates a **Monitoring alerting incident**, which is distinct from a **Google Service Health event** and a **Cloud Support case**; link their IDs instead of conflating them into a single record.

### 4.2. Querying the Logs

Service Health logs use the payload type:

~~~text
type.googleapis.com/google.cloud.servicehealth.logging.v1.EventLog
~~~

The project log name follows a structure similar to:

~~~text
projects/PROJECT_ID/logs/servicehealth.googleapis.com%2Factivity
~~~

Example Logs Explorer filter:

~~~text
logName="projects/PROJECT_ID/logs/servicehealth.googleapis.com%2Factivity"
jsonPayload.category="INCIDENT"
jsonPayload.state="ACTIVE"
jsonPayload.relevance=("IMPACTED" OR "RELATED")
~~~

Substitute `PROJECT_ID`; verify actual log entries match these fields/values before saving an alert. Overly strict filters may miss event updates; overly broad filters spam on-call whenever unrelated services post events.

### 4.3. Designing Low-Noise Alerts

Layer alerts thoughtfully:

| Alert Type | Example Condition | Suggested Channel |
|---|---|---|
| Critical Google event | New Cloud SQL/GKE/Cloud Run event in an active region with high relevance | On-call |
| Event update | Workaround, impact, or state changes | Update existing incident |
| Non-urgent event | Product not on active request path | Slack / tracking channel |
| Application SLO breach | Error rate, latency, or burn rate crosses threshold | Page immediately—do not wait for Service Health |
| Service Health pipeline failure | Missing expected log/API signals | Health check on the alerting pipeline |

**Never page solely on a Service Health event.** For live user impact, prioritize SLO alerts and use Service Health events as context. At the same time, events touching critical infrastructure may warrant immediate paging even before SLOs dip—for instance, failover risk or shrinking redundancy headroom.

### 4.4. Testing Alerts

Test in a sandbox project or with alert configs that cleanly separate test from production:

1. Create a test notification channel.
2. Create a policy filtering Service Health `EventLog`s.
3. Use Google's documented testing workflow for notifications and log-based alerts.
4. Confirm notifications actually reach the right person/channel.
5. Verify event and project links inside the notification.
6. Confirm event updates do not spawn duplicate tickets uncontrollably.
7. Document how to disable test alerts and clean up test configurations.

Never fake an urgent incident on a production project just to test paging. For end-to-end drills, use a flow pre-approved by on-call to avoid false-alarm pages.

## 5. Fallback Plan When Service Health Itself Is Impacted

Monitoring tools also rely on Google Cloud IAM, Console, Logging, and APIs. During a widespread disruption, operators may be unable to sign into PSH, or alerts may arrive delayed.

Establish fallback paths:

1. Check the public page **https://status.cloud.google.com/** from an independent device/network.
2. Check supplemental public feeds such as RSS if integrated by your organization.
3. Keep runbooks and on-call contacts outside the failing cloud footprint (per security policy).
4. Use external telemetry or synthetic probes from a separate failure domain whenever possible.
5. Check application systems and dependencies directly; never delay mitigation just because status pages fail to load.
6. Once PSH recovers, reconcile event history and finalize the incident timeline.

Google provides a Service Health **Status API** to check feature health; automated systems can pair it with public status/RSS fallbacks. Verify reachability, reporting scope, and rate-limit policies before relying on it in mission-critical automation.

## 6. Triage: Confirm Real Impact Before Concluding Root Cause

Triage aims to quantify impact, bound the incident, and take safe impact-reducing actions—not immediately assign blame.

### 6.1. 10-Step Workflow

1. **Confirm:** is the alert genuine or a false positive? Are real user requests failing?
2. **Classify impact:** affected users, features, revenue, data integrity, and SLO burn.
3. **Define scope:** project, region/zone, product, revision, cluster, database instance, traffic path.
4. **Build timeline:** start time, latest deploys/config changes, spikes, quotas, network events.
5. **Check PSH / public status:** does a product/location event match the symptoms?
6. **Correlate logs/metrics/traces:** check concrete errors like timeouts, connection refused, 429s, 5xx, and dependency latency.
7. **Audit self-inflicted changes:** rollouts, firewalls, IAM, schema migrations, credential rotations.
8. **Mitigate:** roll back revisions, shed load, fail over, or degrade gracefully per approved runbooks.
9. **Decide on Support:** does the incident require Google investigation or feature/limit assistance?
10. **Maintain update cadence:** incident commander, current status, evidence-backed ETA (if any), and action owners.

### 6.2. Separating Platform Faults from Configuration Faults

| Symptom | Possible Google Cloud Cause | Possible App / Config Cause | What to Check |
|---|---|---|---|
| Cloud Run 503 spike | Regional platform disruption | Slow startup, max instances, CPU/memory, downstream timeouts | Cloud Run request logs, revision, PSH, DB |
| Cloud SQL connect timeouts | Cloud SQL/network regional incident | IP/firewall/connector, exhausted pool, unavailable instance | Cloud SQL metrics, VPC logs, PSH |
| GKE Pods `Pending` | Compute capacity/quota issue | Requests/limits, taints, IP range, node policy | Scheduler events, nodes, Compute quotas |
| Pub/Sub backlog climbing | Delivery/regional disruption | Failing consumers, ack deadlines, quotas, retry storms | Subscription metrics, consumer logs, PSH |
| GCS 403 | IAM/platform authorization issue | Principal lacks role, org policy, wrong token | Principal, resource IAM, audit logs |
| Multiple projects hitting 5xx | Shared regional failure | Shared library/config, DNS, shared release | Control group comparison, network, PSH |

Never disable IAM controls, open network-wide firewalls, or expose endpoints publicly just because root cause is unclear. Mitigations must stay within approved change boundaries and remain reversible.

### 6.3. Correlation Does Not Equal Causation

If a Google Cloud event began around the same time latency climbed, it may be related yet insufficient proof. Verify:

- Do error messages, HTTP statuses, and traces match the published symptoms?
- Are only the affected regions/products failing, or unrelated ones too?
- Did any major deploy or quota exhaustion coincide with the spike?
- Did SLIs recover after applying the workaround or when the event resolved?
- Did documentation or Support confirm specific impact?

In incident reports, distinguish **observed**, **suspected**, and **confirmed** facts. Never write "Google caused an outage" based solely on guesswork.

## 7. Mitigations and Technical Decisions

Service Health may publish a workaround, yet SREs must still evaluate risks for their specific workload.

| Workload | Mitigation Option | Risks / Preconditions |
|---|---|---|
| Cloud Run API | Roll back revision, shift traffic, carefully raise min instances | Ineffective if dependencies in the same region are broken |
| Cloud SQL | Shift read traffic, execute DR/failover per runbook | Replica lag, single-writer constraints, RPO, DNS, app reconnects |
| GKE | Shift workloads to another zone/region with capacity | Quotas, cluster/namespace config, network dependencies |
| Pub/Sub | Throttle producers, scale consumers on recovery, hold backlog | Retention limits, duplicates, DLQs, idempotency |
| Storage | Use pre-designed backups/replicas | Consistency, object versions, data residency |
| Java / Spring Boot | Circuit breakers, bounded retries, shed non-critical features | Retry storms, lost state, unsynchronized data |

**Never trigger a database failover solely because the public status page shows an issue.** Verify SLO thresholds, replica health, RPO/RTO, failback paths, and decision authority first.

### 7.1. Containing Retry Storms

When backends time out, Java clients may retry aggressively and worsen the outage. Design:

- Short, realistic timeouts within the request budget.
- Exponential backoff with jitter.
- Capped retry counts and overall deadlines.
- Circuit breakers and bulkheads protecting thread and connection pools.
- Idempotency keys for creation/payment operations under retry.
- Queuing/backpressure instead of unbounded traffic.

### 7.2. Decision Process

Every mitigation option should document: **impact reduced**, **data-loss or disruption risk**, **operational cost**, **rollback path**, **approver**, and **abort signals**. When data is incomplete, choose low-risk mitigations first while opening a Support case in parallel if Google-side insight is needed.

## 8. Cloud Customer Care: Roles and Support Offerings

Google Cloud Customer Care provides billing and technical support according to your organization's support tier. Access to support cases does not grant permission to modify production resources; those roles are separate.

### 8.1. Support Tiers

| Tier | Typical Scope | Important to Know |
|---|---|---|
| Basic Support | Billing support and self-service/community resources per policy | Do not assume SLA-backed technical support case responses |
| Standard Support | Technical support within defined scope and business hours | Fits apps not requiring 24/7 response across all priorities |
| Enhanced Support | Faster technical support, 24/7 coverage on select priorities/languages | Includes escalations and add-on capabilities |
| Premium Support | Mission-critical support, TAM, and deeper engagement per contract | May include follow-the-sun and contracted services |

Supported tiers, languages, regions, business hours, and target initial response times vary by service terms. Never hardcode "P1 always gets a 15-minute response" for every account. Check the **Technical Support Services Guidelines** and your active support offering.

### 8.2. IAM for Support Cases

| Purpose | Role |
|---|---|
| View support cases | `roles/cloudsupport.techSupportViewer` |
| Create/update/manage support cases | `roles/cloudsupport.techSupportEditor` |
| Manage support accounts and sharing settings | `roles/cloudsupport.admin` only when truly needed |

Roles can be granted at organization, folder, or project level per support scope. If on-call only needs read access to open cases, do not grant Editor. Shift leads and support liaisons may hold Editor on production projects, whereas organization-wide grants require careful review.

### 8.3. Should You Open a Case When a Google Incident Is Already Posted?

You may **skip opening a new case** if the public/PSH notice already matches your symptoms and scope, your SREs have a working workaround, and no custom guidance is needed. However, consider opening a case if:

- Business impact is severe and you need project-specific impact confirmation.
- Symptoms differ from or exceed the published scope.
- You need confirmation on workarounds, ETAs, or recovery guidance.
- Data-loss risk requires joint investigation.
- No published incident or matching PSH event exists.

When opening a case for a known issue, **link it to the known issue/event** if the UI supports it and highlight specific differences; avoid filing duplicate cases for the same incident.

## 9. Case Priorities: P1, P2, P3, P4

Google Support priority measures **business impact and urgency**; it does not necessarily match internal SEV1/SEV2 labels or Cloud Monitoring alert severities.

| Console Priority | Reference Impact Level | Examples |
|---|---|---|
| **P1 — Critical** | Production unusable or severely impacted with no rapid workaround; immediate action needed | Widespread payment failures, critical data at risk |
| **P2 — High** | Production noticeably degraded; partial workaround may exist | One region slow/erroring after shifting part of traffic |
| **P3 — Medium** | Limited scope; minimal or no direct user impact | Intermittent staging failure, configuration question |
| **P4 — Low** | Technical question or minor issue; service functions normally | Architecture consultation, tuning advice |

The Cloud Support API may define additional enum values depending on version and offering, so do not assume every Console user can select every API level. The table above follows standard Customer Care P1–P4 definitions.

### 9.1. Pick the Right Priority with Evidence

On-call should document:

- Number of affected users, orders, or transactions.
- Lost or degraded production functionality.
- Error percentage and SLO impact.
- Data loss, corruption, or integrity risk.
- Whether a workaround exists and how long it takes to apply.
- Why immediate assistance is required rather than waiting until next business hours.

Never inflate priority just to get a faster answer on a non-urgent issue. When production impact changes, **update the existing case's priority** with justification.

### 9.2. P1 and Collaboration Expectations

P1 cases generally require close customer collaboration: authorized decision-makers and engineers joining troubleshooting bridges, supplying logs/timelines, and answering questions continuously. Assign an active responder and handoff plan before opening a P1; never file a P1 and go unreachable for hours.

Initial response time is a **support target**, not a commitment that Google will finish resolving the root cause within that window. Your application SLA and Customer Care response targets are distinct concepts.

## 10. Preparing a Technical Dossier Before Opening a Case

A well-prepared case saves Support from asking basic follow-up questions. You do not need to wait until you know the root cause before filing a P1, yet you must include impact and minimum diagnostics.

### 10.1. Evidence Checklist

| Category | Useful Information |
|---|---|
| Business impact | Affected users, blocked revenue/actions, SLO breach |
| Timestamps | Start/end in UTC ISO 8601, recurrence, duration |
| Environment | Organization/project ID, project number, region/zone, product/version |
| Resource identifiers | Cloud Run service/revision, Cloud SQL instance, GKE cluster, VM name, Pub/Sub subscription |
| Symptoms | HTTP/gRPC status, error codes, messages, latency, frequency |
| Reproduction | Minimal repro steps, expected vs. actual |
| Recent changes | Deploys, configs, IAM, quotas, schemas, networking, rotations |
| Diagnostics | Cloud Logging query, Monitoring chart URL, trace ID, API request ID |
| Actions attempted | Mitigations, rollbacks, restarts, and their observed outcomes |
| Service Health | Event ID/link, relevance, product/location |
| Request to Google | Specific questions, scope confirmation, diagnosis, workaround, ETA, or next steps |

Do not dump entire log archives when 10 lines reproduce the issue. Pick the exact timeframe and essential evidence while keeping raw originals in logging per retention policies.

### 10.2. Protecting Data Shared with Support

Share only what internal policy and support contracts allow. Before submitting:

- Strip or redact access tokens, API keys, secrets, private keys, and passwords.
- Avoid sending unapproved personal or financial data.
- If screenshots or sensitive diagnostics are required, use secure channels prescribed by Google and your organization.
- Never paste service account JSON keys into descriptions or attachments.
- Reproduce with synthetic test data and sandbox resources whenever possible.
- Limit case visibility to people who genuinely need it.

Google may ask for specific logs or diagnostics; always check data classification and minimize sensitive fields before sharing.

## 11. Creating and Tracking Cases in Google Cloud Console

### 11.1. Creating a Case

1. Open **Support → Cases** in Google Cloud Console.
2. Select the exact **project or organization** owning the case.
3. Check **Known issues** and open duplicate cases.
4. Click **Get help** or the Console's current case-creation workflow.
5. Select the product and specific feature, describing expected vs. actual behavior and observed errors.
6. Set priority based on business impact and choose a support channel permitted by your offering.
7. Submit the case; save the case ID and link in your internal incident record.
8. Monitor updates, supply requested evidence, and apply safe workarounds.

Console UI, language options, and chat/phone/email channels vary by support tier and version; do not assume every account has every channel.

### 11.2. Case States

Support cases move through states such as new, assigned/in progress with a specialist, waiting on customer, solution provided, or closed (UI labels may differ from API enums). When replying to Google:

- Keep replies inside the existing case ID instead of opening duplicates.
- Provide timestamped updates and concrete evidence.
- Confirm whether suggested workarounds were tested and what happened.
- Update impact if the incident worsens or improves.
- Record Incident Commander decisions in internal logs.

If Support's suggestion does not solve the issue, update or reopen the case per procedure; never mark an internal incident resolved solely because the support case shows `solution provided`.

### 11.3. One Case per Distinct Issue

Do not bundle unrelated issues into one sprawling case, and do not file duplicate cases for the same error hoping for faster service. Each issue deserves one case with an owner, update cadence, and link in the incident tracker. When a shared root symptom spans multiple projects, link affected projects/resources in one case if your Support scope allows.

## 12. Technical Case Description Template

Illustrative example for a Spring Boot API on Cloud Run depending on Cloud SQL. IDs are synthetic and do not reflect a real incident:

~~~text
Subject: [Production impact] Cloud SQL connection timeouts affecting orders API

Priority: P2 (high impact; partial workaround active)
Project: commerce-prod-example
Products: Cloud SQL for PostgreSQL; Cloud Run
Region: asia-southeast1
Start time: 2026-11-19T08:15:00Z
Current state: Ongoing; mitigated by reducing traffic and concurrency

Business impact:
- Approximately 14% of order submissions fail or exceed 5 seconds.
- p99 latency rose from 650 ms to 7 seconds.
- Payment confirmation is deferred; no confirmed data loss so far.

Expected:
- Cloud Run service connects to Cloud SQL under normal load.

Observed:
- Intermittent connection timeout and JDBC pool acquisition timeout.
- Error spikes across two Cloud Run revisions with no new release.

Evidence:
- Request log query/link: [internal sanitized URL]
- Monitoring chart: [internal sanitized URL]
- Example trace ID: [redacted/approved ID]
- Cloud SQL instance identifier: orders-db-test-placeholder
- Personalized Service Health event: [link if applicable]

Changes and mitigation:
- No schema migration or IAM change during the observed window.
- Reduced max instances and enabled temporary backpressure.
- Existing connections recover intermittently.

Request:
- Please confirm whether a service-side incident affects this region/instance.
- Recommend safe diagnostic steps and any available workaround.
- Advise when additional information or coordinated troubleshooting is needed.

Technical contact:
- On-call engineering team, available via support case/bridge.
~~~

The example uses fabricated metrics to illustrate structure. For a P1, clearly document severe production failure with no rapid workaround; if impact is already largely mitigated, choose the matching priority. Never fabricate fake links or trace IDs in real cases.

### 12.1. Case Update Template

~~~text
Case update — 2026-11-19T09:05:00Z
Observed change: Error rate decreased from 14% to 2% after routing adjustment.
Still impacted: API latency and a subset of payment confirmations.
Mitigation: Holding max concurrency at approved temporary value.
New evidence: Trace IDs and region-scoped charts attached (sanitized).
Request: Please confirm whether the suspected Cloud SQL disruption remains active.
Next internal checkpoint: 2026-11-19T09:20:00Z.
~~~

Keep updates concise, chronological, noting what was tried and what specific question Google needs to answer. Avoid spamming duplicate logs when nothing new emerged.

## 13. Escalation, Priority Changes, and Follow-the-Sun Handoffs

**Raise priority** when impact escalates beyond initial triage—e.g., P3 to P1 because production is down. **Escalate a case** when management intervention is needed because coordination, progress, or handling scope fails to match the situation. These are two distinct actions.

| Situation | Action to Consider |
|---|---|
| P2 turns into a severe production outage | Raise priority (e.g., to P1) and explain impact |
| Thin evidence on a brand-new case | Continue triage and update the case; do not escalate prematurely |
| Response arrived yet suggested fix failed | Share test results and request deeper investigation |
| Serious coordination delay or missing owner | Follow your offering's case escalation process |
| Incident spans multiple timezones | Use follow-the-sun coverage where supported by tier and priority |

Escalation options, priority changes, and follow-the-sun depend on Enhanced/Premium terms. In many workflows, P1 automatically receives continuous handling and a technical bridge; for P2, 24/7 continuous handling may require Premium Support.

### 13.1. Coordination Roles

- **Incident Commander (IC):** coordinates impact response and approves mitigations/cutovers.
- **Technical Lead:** analyzes logs/metrics/traces and tests technical fixes.
- **Support Liaison:** owns Customer Care communication, case IDs, and response follow-ups.
- **Communications Lead:** updates stakeholders and external status pages.
- **Scribe:** logs timeline, decisions, evidence, and next actions.

One person can wear multiple hats on small teams, but production decision authority must always be clear. Google Support is an investigation partner, never a replacement for the workload owner's operational accountability.

### 13.2. Shift Handoffs

A minimum handoff covers: current impact, severity, open cases and priorities, Service Health event IDs, active mitigations, explicit "do not touch" warnings, current hypothesis, Google's last update, next expected update, next technical step, rollback status, and the incoming shift owner.

Never hand off a case with just "Google is looking into it"; give the incoming responder enough context to act without restarting triage from scratch.

## 14. Incident Runbook Combining Service Health and Support

This runbook applies to a Cloud SQL latency incident breaking a Cloud Run API. All timings below are **internal coordination examples**, not Google SLAs.

| Time Since Detection | SRE Actions | Evidence / Output |
|---|---|---|
| T+0–5 min | Validate alert, declare internal incident, assign IC | SLIs, impact, start time |
| T+5–10 min | Identify project/region/product; check PSH and public status | Event ID/link, state, relevance |
| T+10–15 min | Check recent deploys, DB metrics, traces, quotas/IAM | Hypotheses and scope |
| T+15–25 min | Apply safe mitigation: backpressure/rollback/reroute per runbook | Before/after SLIs, decision |
| When impact warrants help | Open/update support case at appropriate priority | Case ID, evidence, business impact |
| During incident | Watch Google updates, staff bridge, update stakeholders | Timeline, checkpoint statuses |
| As platform recovers | Verify DB, backlog, failover state, data, latency | Validation and data reconciliation |
| Post-incident | Restore normal config, close alerts/incident, postmortem | Action items and owners |

### 14.1. Decision Points

Before failing over a database or shifting regional traffic:

1. Could it cause data loss or split-brain?
2. What data loss and downtime do RPO/RTO allow?
3. Has the replica caught up? Are network/secret permissions ready in the target region?
4. Do quotas/capacity suffice? Which dependencies remain in the old region?
5. Who approves, and what is the point of no return for rollback?
6. How will post-switch metrics prove recovery?

Never auto-failover a stateful system simply upon receiving a Service Health log event. Automation should stop at alerting and recommendations until cutover safety is verified.

### 14.2. Once Google Marks the Event Resolved

Execute application-level recovery:

- Confirm request success rates and latency stabilize.
- Clear broken connection pools, restarting only if required.
- Drain Pub/Sub backlogs safely with rate limits and idempotency.
- Reconcile hung transactions and order statuses.
- Revert temporary mitigations under change control.
- Maintain heightened monitoring through a defined soak period.
- Complete the postmortem once evidence settles, even if Google's incident report publishes later.

## 15. Hands-On Scenario: Java API Disrupted by Cloud SQL Dependency

A Spring Boot application runs on Cloud Run in Singapore, connects to Cloud SQL PostgreSQL in the same region, and publishes order events to Pub/Sub. One afternoon, timeout rates spike.

### Step 1: Detect and Measure Impact

Cloud Monitoring shows:

- Request rate matches baseline.
- 5xx error rate rises; p99 latency breaches SLO.
- HikariCP pending connections climb with frequent connection timeouts.
- Database query latency and connection errors spike around the same time.

**Do not immediately blame a Google-side Cloud SQL outage.** Check max instances, pool sizes, quotas, recent deploys, and networking.

### Step 2: Check Service Health

Open PSH for both the Cloud SQL and Cloud Run projects; check any matching regional/product events. Record `eventId`, state/relevance, `startTime`, latest update, and workarounds. Check the public status page if needed.

If no event exists, keep investigating all possible causes. Even if an event exists, still verify application telemetry before choosing mitigations.

### Step 3: Mitigate Impact

Within approved runbooks:

- Cap concurrency or max instances to protect DB connections.
- Enable backpressure and curb retry storms.
- Shift reads to caches or read replicas if supported by design.
- Fail over only if DR is tested and data/recovery gates pass.
- Preserve idempotency for order writes and event publishes.

### Step 4: Open a Support Case If Needed

If error rates materially disrupt users, select P1 or P2 based on impact, workaround availability, and support tier. Provide:

- Project ID, instance, region, and UTC timestamps.
- JDBC/Cloud SQL error codes and connection/query latency charts.
- Cloud Run request logs/traces, container revision, and recent changes.
- Relevant Service Health event (if any).
- Mitigations applied, remaining impact, and specific questions.

### Step 5: Complete Recovery and Learn

Once SLOs recover, reconcile pending orders, Pub/Sub backlogs, and database integrity. Archive Support records and the incident report, and track action items: pool saturation alerts, DR drills, PSH dashboards, on-call support IAM, and case templates.

## 16. Separating Service Health, Cloud Monitoring, and SLOs in Reporting

Executive incident reports usually need three layers:

| Layer | Question | Metrics / Evidence |
|---|---|---|
| Provider event | What event did Google Cloud report? | PSH event state, product/location, timeline |
| Customer technical impact | How was our workload affected? | 5xx, latency, DB errors, quotas, traces |
| Business impact | How were users and business operations affected? | Failed orders, conversion, support tickets, data integrity |

Example: "PSH reported a Cloud SQL incident in region A starting 08:10 UTC; our API timeouts spiked at 08:14 UTC; roughly 11% of orders required retries with zero confirmed data loss; mitigation applied at 08:30 UTC; SLIs stabilized at 09:05 UTC." That report is far more accurate than "Google Cloud was down for 55 minutes."

### 16.1. SLIs and Incident Detection

Alert on error-budget burn rates or SRE-approved thresholds. PSH events help classify root causes and predict blast radius, not serve as the sole trigger for declaring internal incidents.

In multi-region/hybrid setups, aggregate Service Health events at org/folder scope while limiting resource-detail exposure, and watch for shared dependencies across projects like Shared VPC, Cloud SQL, or Artifact Registry.

### 16.2. Do Not Confuse Provider and Application Timelines

User impact can outlast Google marking a platform issue Resolved due to backlogs, caches, replica lag, un-restarted apps, or stale client connections. Conversely, an app may recover earlier via failover before Google closes the event. Report both timelines in parallel.

## 17. Governance, Security, and Cost

### 17.1. Role-Based Access

- SRE/on-call: Service Health Viewer and project-scoped Monitoring/Logging read access.
- Support Liaison: Tech Support Editor scoped to projects needing case management.
- Extended after-hours engineers: audited emergency break-glass access.
- Security: approves which logs/attachments may be shared with Customer Care.
- Platform team: manages alert policies, notification channels, log sinks, and org-level integrations.

Never grant organization-wide visibility to vendors or on-call responders beyond their scope. In multi-team orgs, group-based IAM, least privilege, and periodic access reviews prevent leaking sensitive resource details.

### 17.2. Archiving Incident Records

Store event/case IDs, chat timelines, trace samples, and runbook logs in your incident system. Define retention, access controls, redaction, and storage policies. If routing multi-project Service Health logs to Cloud Logging sinks or BigQuery, account for ingest/storage/query costs and sink writer permissions.

Service Health logs represent provider-side telemetry; full application RCA also requires change logs, audit logs, deployment events, SLIs, and business metrics.

### 17.3. Connecting FinOps and Availability

During an incident, spinning up backup regions or adding replicas raises spend. Prioritize reliability and safety per SLO/DR policy first, then account for cost. Never delay critical mitigations over a temporary Cloud Billing forecast bump when the action is already approved in your continuity plan.

## 18. Post-Incident: Postmortems and Improvements

A blameless retrospective focuses not on blaming individuals, but on uncovering systemic conditions, missed signals, and ways to shrink future impact.

### 18.1. Postmortem Contents

1. **Summary:** incident description and user impact scope.
2. **Timeline:** chronological sequence from detection to recovery, mixing Google event updates and customer actions.
3. **Impact:** failed requests/transactions, latency, data impact, duration, SLO/error budget burn.
4. **Contributing factors:** single-region dependencies, connection pools, missing backpressure, alerting blind spots, etc.
5. **What worked:** detection, rollback, Support engagement, workarounds.
6. **What did not work:** missing case template, insufficient IAM, delayed alert pipeline, etc.
7. **Action items:** owner, deadline, acceptance criteria, and verification tests.
8. **References:** incident ID, PSH event ID, support case, charts, logs, and reports.

If Google publishes an incident report later, update the confirmed root cause section—never author speculation as if it were Google's official finding.

### 18.2. High-Value Improvements

- Configure PSH alerts filtered to active products and locations.
- Center paging on SLO alerts while cutting unrelated noise.
- Provision Support IAM and run training for on-call shifts.
- Pre-build support case templates and evidence-collection checklists.
- Rehearse failovers, restores, and Java client recovery.
- Test fallbacks when Console, PSH, or APIs are unavailable.
- Add customer-impact models and business KPI dashboards.
- Clarify ownership across Shared VPC, databases, and platform projects.

## 19. Troubleshooting When Telemetry or Cases Fail to Appear

**Cannot open Service Health dashboard.** Check that the right project is selected, billing is active, and you hold `roles/servicehealth.viewer`. If IAM or Console is disrupted, switch to the public status page to keep triaging.

**No event shown despite application errors.** It may be a project-specific issue, an unconfirmed/unpublished event, or a service/region mismatch. Check app telemetry and recent changes, and open a support case if impact requires assistance.

**No Service Health logs arriving.** Confirm the Service Health API is enabled per docs, Logging permissions are intact, and filters match real products/events. Never treat a brief absence of logs as proof no incident exists.

**Log-based alert never fires.** Check policy enablement, notification channels, Logs Explorer filters, permissions, and existing Monitoring incidents. Avoid `state=ACTIVE` if you also need notifications when events close or update.

**Duplicate notifications.** Event updates emit fresh log entries; deduplicate by event ID and update timestamp, linking them to the same internal incident.

**Support Cases page is empty.** Check your organization/project selector and `roles/cloudsupport.techSupportViewer`; cases filed under another project will not appear if you only hold permissions on the current project.

**Cannot file a technical support case.** Check your organization's support tier and `roles/cloudsupport.techSupportEditor`; Basic support covers billing rather than technical case entitlements of paid tiers.

**Priority mismatches impact.** Document business impact and update the case's priority per offering terms; never open a second case instead of raising priority on the existing case.

**Google marks Resolved yet API still errors.** Inspect app-layer recovery, backlogs, stale connections, data integrity, and SLOs. If symptoms persist, update the case with fresh evidence.

**Unsure whether to escalate.** Weigh current impact, response history, coordination status, and support tier entitlements; update priority when impact changes before escalating just to nudge progress.

## 20. Operations Team Checklist

### Before Incidents

- [ ] Clear inventory of projects, regions, products, and application dependencies.
- [ ] On-call holds Service Health Viewer plus appropriate Logs/Monitoring access.
- [ ] Designated responders hold permissions to view/create support cases per offering.
- [ ] PSH alerts filtered to critical services, regions, and relevance.
- [ ] SLOs and synthetic probes operate independently of status pages.
- [ ] Public status/RSS fallbacks, runbooks, and contacts stored outside primary failure domain.
- [ ] Case templates, redaction guides, and support contacts ready.
- [ ] Rehearsed DR/rollbacks and Service Health alerts.

### During Incidents

- [ ] Recorded UTC timestamps and business impact; assigned Incident Commander.
- [ ] Correlated PSH/public events with SLIs, logs, traces, and change timelines.
- [ ] Avoided declaring root causes from unverified guesswork.
- [ ] Mitigations passed risk gates, fit SLO/RTO/RPO, and had rollbacks.
- [ ] Support case filed with accurate priority, product/project/region, symptoms, and evidence.
- [ ] Support liaison updates case/timeline without creating duplicates.
- [ ] Shift handoffs, stakeholder updates, and next checkpoints scheduled.

### After Incidents

- [ ] SLIs stabilized; data, backlogs, and transactions reconciled.
- [ ] Temporary mitigations cleanly reverted under change control.
- [ ] Service Health and Support event IDs archived in incident record.
- [ ] Postmortem separates confirmed root cause from hypotheses.
- [ ] Action items have owners, deadlines, and validation tests.
- [ ] Support permissions, alert noise, and fallback procedures improved.

## 21. Scenario Exercises

**Scenario A — Google event without direct errors.** PSH flags a `RELATED` event on BigQuery in a region used for internal reporting. No requests error out, yet the end-of-day dashboard slips. Classify internal severity, verify reporting SLA, pick the alert channel, and decide whether to open a dedicated case or simply track the published event.

**Scenario B — No Google event yet users impacted.** A Spring Boot API fails 20% of requests right after an IAM update to its service account. Public status shows "healthy," and PSH has no matching event. Outline triage steps, logs/IAM evidence, rollback, and criteria for opening a Google case if unresolved.

**Scenario C — Event Resolved yet application still degraded.** A Pub/Sub subscription holds a 2-million-message backlog after a regional disruption. Design backpressure, consumer scaling, deduplication, DLQ handling, SLO recovery tracking, and stakeholder updates. Why should you not close the internal incident the moment Google's event moves to `Closed`?

**Scenario D — Existing P2 case, production collapses.** A workload degrades from partial errors to a complete outage with no workaround. Detail the business-impact evidence to add, how to upgrade priority, bridge participation duties, and when to escalate.

## 22. Official References

- [Public Google Cloud Service Health](https://status.cloud.google.com/)
- [Personalized Service Health — Overview](https://cloud.google.com/service-health/docs/overview)
- [Service Health events and incident concepts](https://cloud.google.com/service-health/docs/concepts)
- [How Google Cloud communicates incidents](https://cloud.google.com/service-health/docs/incident-communication)
- [View Service Health dashboard](https://cloud.google.com/service-health/docs/view-events)
- [Manage Personalized Service Health access](https://cloud.google.com/service-health/docs/manage-access)
- [Service Health API](https://cloud.google.com/service-health/docs/list-events)
- [Service Health logs and export](https://cloud.google.com/service-health/docs/logs)
- [Alerting from Cloud Logging](https://cloud.google.com/service-health/docs/configure-alerts-cloud-logging)
- [Checking when Personalized Service Health is disrupted](https://cloud.google.com/service-health/docs/service-health-disruption)
- [Integrating Service Health with operational systems](https://cloud.google.com/service-health/docs/how-to-integrate)
- [Cloud Customer Care — Create and manage support cases](https://cloud.google.com/support/docs/customer-care-procedures)
- [Cloud Customer Care — Best practices](https://cloud.google.com/support/docs/best-practices)
- [Cloud Customer Care — IAM access control](https://cloud.google.com/support/docs/access-control)
- [Cloud Customer Care — Language and working hours](https://cloud.google.com/support/docs/language-working-hours)
- [Enhanced Support overview](https://cloud.google.com/support/docs/enhanced)
- [Google Cloud Technical Support Services Guidelines](https://cloud.google.com/terms/tssg)
- [Cloud Monitoring documentation](https://cloud.google.com/monitoring/docs)
- [Cloud Logging documentation](https://cloud.google.com/logging/docs)
- [Cloud Trace documentation](https://cloud.google.com/trace/docs)

## 23. Summary

**Service Health reflects Google Cloud's platform status, while SLIs/SLOs reflect the health of your application and users.** SRE teams must monitor both, correlate products/locations/timelines, apply runbook mitigations, and engage Customer Care through evidence-backed support cases with the right priority and clear ownership. Personalized Service Health surfaces project-relevant events, the public status page provides fallback during broad outages, and Cloud Monitoring/Logging/Trace measure real user impact.

Good operations go beyond receiving alerts or opening tickets. The real outcome is limiting user impact, safeguarding data, confirming service recovery, preserving incident history, and turning lessons learned into repeatable alerts, runbooks, DR drills, and Google Cloud Support collaboration workflows.
