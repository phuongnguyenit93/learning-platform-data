# Alert Handling Procedures and Audit Evidence

When operating applications on Microsoft Azure, alerts can fire due to resource outages, suspicious access, administrative permission edits, non-compliant configurations, or unexpected cost spikes. Receiving an alert is only the starting point. Operations teams must verify the signal, assess impact, act at the right priority level, and preserve trustworthy evidence of what occurred.

A sound procedure answers two sets of questions:

- **Operations and security:** what event happened, whom did it affect, what action is needed, have services been restored, and has recurrence been prevented?
- **Auditing and traceability:** how did the organization detect it, who decided the response, what changes were made, and what evidence proves controls are operating effectively?

In the CLOUD_PROVIDERS_AZURE module, this process links Microsoft Entra ID, Azure subscriptions, and resource groups with Azure Monitor, Microsoft Defender for Cloud, Microsoft Sentinel (if deployed), Azure Policy, monitoring tools, authorization mechanisms, and cost controls. This lesson focuses on how organizations execute the workflow; certain log sources, retention features, and integrations must be configured upfront and may incur costs.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish monitoring signals, alerts, incidents, security findings, and non-compliance findings.
2. Build an alert handling lifecycle spanning intake, triage, verification, response, recovery, and case closure.
3. Identify appropriate evidence sources in Azure and Microsoft Entra ID, including recognizing when data is missing if collection was never configured.
4. Record chain of custody, integrity, timestamps, actors, storage locations, and retention periods for evidence.
5. Write basic KQL queries, inspect Azure Activity Logs, and compile audit-ready records.
6. Propose safe automation while keeping human approval gates for high-impact actions.

Examples assume an application running inside a resource group in an Azure subscription with administrators and an incident on-call team. All timestamps in records are standardized to UTC for easy cross-region and cross-system correlation.

## 2. Distinguishing Alerts, Incidents, and Evidence

| Concept | Meaning | Example |
|---|---|---|
| Signal or event | A system-generated record or measurement | A role assignment write operation appears in Azure Activity Log |
| Alert | Notification generated when a condition or detection rule is satisfied | Azure Monitor alerts when HTTP 5xx rate exceeds threshold |
| Security finding/recommendation | Finding about a risk or security configuration needing improvement | Defender for Cloud detects a resource with an insecure setting |
| Incident | Case requiring investigation, coordination, and workflow handling | A suspected compromised identity leading to multiple unauthorized edits |
| Audit evidence | Data or records proving an event, decision, or control execution | Raw logs, queries, role assignments, approval tickets, remediation reports |
| Control | Mechanism or process governing risk | MFA, Azure RBAC, Azure Policy, privileged access alerts |
| Noncompliance | State failing to meet a defined rule | A storage account violating an encryption or network policy |

**An alert does not automatically equal a security incident.** An alert may be a false positive, legitimate activity, or a symptom of a technical outage. Multiple alerts can map to the same incident. Conversely, an incident might be discovered via a user report without an automated alert.

Audit evidence is also broader than forensic evidence for an attack. It can demonstrate the organization configured controls beforehand, detected drift, approved changes, executed responses, and evaluated outcomes. Therefore, maintain records combining both system telemetry and human interpretations and decisions.

## 3. Signal and Evidence Sources on Azure

### 3.1. Commonly Used Data Sources

| Source | Data Type | When to Use | Limits to Remember |
|---|---|---|---|
| Azure Monitor metric alerts | Resource metrics: CPU, errors, latency, connection count | Availability/performance incidents | Metrics show symptoms, rarely root cause alone |
| Azure Monitor log alerts | Log query results run on a schedule and condition | Anomalous behavior, app errors, or admin actions | Only works if target logs are collected and rules enabled |
| Azure Activity Log | Subscription-scope control-plane events, like creating/deleting resources or changing permissions | Tracing ARM operations and callers | Does not replace data-access logs; has default retention limits |
| Resource logs/diagnostic logs | Service-specific logs: Key Vault, Storage, network, database… | Investigating data-plane access and service activity | Many log types require enabling diagnostic settings and choosing a destination first |
| Log Analytics workspace | Central store for querying log tables routed to the workspace | Correlating sources by timestamp, IP, resource ID, or correlation ID | Ingestion/retention cost, access rights, and ingestion latency depend on config |
| Microsoft Entra sign-in/audit logs | Sign-ins, identity changes, app config and Entra role edits | Investigating unusual sign-ins, app updates, and identity changes | Licensing, retention, and export settings vary by tenant |
| Microsoft Defender for Cloud | Recommendations, security alerts, and workload protection insights when plans are enabled | Detecting posture issues and threats | Detection coverage depends on enabled protection plans and config |
| Microsoft Sentinel | Analytics rules, incidents, entities, investigation, and automation | SOC needing alert correlation and centralized investigation | Must be deployed, connected to sources, and permissioned; not present automatically in every subscription |
| Azure Policy | Definitions, assignments, exemptions, and compliance state | Proving configurations meet defined rules | Compliance assessment does not replace operational or legal checks |
| Azure Resource Graph | Querying current resource inventory, types, regions, tags, and properties | Cross-checking affected scope | Reflects current observed state, not full historical timeline |
| Change tickets, deployment logs, repos, and approvals | Requesters, approvers, commits, pipeline runs, applied changes | Explaining legitimacy and human decisions | Must link to system telemetry via IDs and timestamps |

**Important note:** Azure Activity Log is a control-plane log. It can show that a Key Vault or policy was reconfigured, yet it does not inherently record every time an app reads a secret. Investigating data-plane actions requires verifying the target service's audit/diagnostic logging and confirming it was enabled before the incident occurred.

### 3.2. Preparing Before an Alert Fires

You cannot guarantee full historical event retrieval if logging was never enabled or retention has expired. Design observability from deployment time:

1. Inventory critical resources: Entra ID, production subscriptions, Key Vault, Storage, App Service/AKS, databases, networking, and CI/CD tools.
2. Define required alerts: service failures, sensitive role changes, anomalous identity activity, unauthorized data access, resource deletions/edits, and policy violations.
3. Route mandatory logs to a Log Analytics workspace, Storage Account, or Event Hub via diagnostic settings or each service's log export settings.
4. Select retention duration, read permissions, encryption requirements, network bounds, and storage locations aligned with organizational policy.
5. Verify in practice that logs arrive in the right destination, right table, with required fields, and are queryable; toggling a setting does not guarantee successful ingestion.
6. Configure Action Groups or notification channels so alerts reach the on-call team, and test escalation flows.
7. Synchronize clocks and standardize UTC timestamps; establish correlation keys like subscription ID, resource ID, operation ID, and correlation ID.
8. Document alert rule owners, runbooks, emergency channels, and approvers for disruptive actions.

For production resources, consider both audit data retention limits and post-incident recovery needs. Compliance/retention policies depend on organizational rules, contracts, and applicable laws; no single retention period fits every type of evidence.

## 4. Designing the Alert Handling Lifecycle

A standard workflow can be structured in eight steps:

~~~mermaid
flowchart TD
    A[Alert intake] --> B[Normalize and create case record]
    B --> C[Deduplicate and verify]
    C --> D{Valid alert?}
    D -->|No| E[Document reason and tune rule]
    D -->|Yes| F[Assess severity and impact]
    F --> G[Investigate and preserve evidence]
    G --> H[Contain and remediate]
    H --> I[Verify recovery]
    I --> J[Close case and improve]
    E --> J
~~~

This diagram shows the baseline flow. During severe incidents, evidence preservation and containment may run in parallel as decided by the incident commander. Never delay urgent damage-stopping actions solely to finish a form, yet always record the decision and its impact on evidence.

### Step 1: Intake and Recording

Every alert should be linked to a case or incident record with a stable ID, such as `SEC-2026-0042`. At minimum record:

- System detection time and on-call acknowledgment time (UTC).
- Alert source, alert rule ID, alert instance ID, original severity, and current status.
- Relevant tenant, subscription, resource group, resource ID, region, and environment.
- Affected entities: applications, hosts, accounts, IPs, request IDs, or service principals.
- Assignee/team, communication channel, and links to dashboards or tickets.
- Links to the original alert payload or raw export, not merely pasting text into a ticket.

If multiple alerts reflect the same chain of events, link them to one incident; never reduce alert counts by deleting raw records.

### Step 2: Deduplicate and Verify

Before acting:

1. Verify the alert originates from a legitimate source, not a spoofed notification.
2. Identify which rule triggered, its threshold, and evaluation window.
3. Cross-check related alerts sharing the same resource, identity, correlation ID, or time window.
4. Check maintenance windows, approved changes, recent deployments, and operational telemetry.
5. If suspected false positive, retain raw data and triage rationale; never simply delete the alert.

For example, a "VM CPU over 90%" alert may stem from a scheduled batch job. However, that same metric paired with unusual egress traffic and recent permission edits warrants deeper investigation. Even a scheduled legitimate event must be checked if it exceeds accepted risk thresholds.

### Step 3: Assess Severity and Priority

Tool-assigned severity and **organizational handling priority** can differ. A high-severity technical alert with no user impact may be handled after a medium-severity alert actively disrupting a payment system.

Reference matrix:

| Priority Level | Impact and Likelihood | Sample Handling |
|---|---|---|
| P1 – Critical | Suspected active compromise, critical data exposed, or core production system broadly down | Activate incident coordination, respond and escalate immediately |
| P2 – High | Significant risk to a production service without signs of lateral spread | Assign accountable owner; urgent investigation |
| P3 – Medium | Limited anomaly, low impact, or no evidence of compromise yet | Remediate within committed internal SLA |
| P4 – Low | Configuration improvement, low-risk finding, or signal to monitor | Move to backlog with owner and due date |

This is a sample classification, **not a default Azure SLA**. Organizations must define response times tailored to on-call hours, data sensitivity, notification obligations, and business criticality. Whenever new facts shift the blast radius, upgrade or downgrade priority and document why.

### Step 4: Investigate and Build a Timeline

Responders must answer:

- What actually happened? Which independent signals corroborate it?
- What are the start time, end time, and investigation window?
- Did the action come from a user, service principal, managed identity, or Azure service?
- Which resource IDs, client IPs, correlation IDs, change requests, and deployments are involved?
- Which applications, datasets, regions, and customers might be impacted?
- Which logs are trustworthy, which are missing, and what cannot yet be concluded?

Timelines should capture both **event timestamp** and **collection/ingestion timestamp**. Logs can arrive in a workspace late; never infer causal order strictly from ingestion order. Distinguish observed facts from investigative hypotheses.

### Step 5: Contain, Mitigate, and Remediate

Depending on severity, measures may include:

- Restricting permissions of the suspected identity, revoking credentials or sessions where permitted.
- Pausing pipelines or automation producing unexpected changes.
- Tightening network rules, blocking suspicious traffic flows, or isolating workloads.
- Restoring configurations via controlled IaC/rollback, patching vulnerabilities, or updating policies.
- Shifting traffic to healthy resources and activating appropriate recovery plans.

Actions such as disabling identities, cutting network links, deleting workloads, or rotating keys can disrupt systems or alter forensic traces. Record the decision-maker, rationale, scope, timestamp, tools, and outcome; follow appropriate approval workflows. For fast-spreading incidents, exercise pre-defined emergency authority and complete records immediately afterward.

**Never delete suspected compromised resources before considering evidence preservation.** If deleting or altering something is unavoidable to halt damage, document which evidence was captured and what gaps remain.

### Step 6: Recover and Verify

An incident should only be considered remediated when supported by data:

- Services operate within agreed SLIs/SLOs or operational criteria.
- Relevant excessive permissions, vulnerabilities, or misconfigurations are fixed.
- The original alert stopped firing because the root cause was resolved, not merely because the rule was disabled.
- No signs of recurrence appear across the observation window.
- The application owner or incident commander signs off on completion criteria.

For data-related incidents, verify data integrity and recoverability per internal requirements, rather than relying solely on an Azure resource showing "Healthy."

### Step 7: Close the Case and Archive Records

A case closes once a clear disposition is recorded: confirmed incident, benign activity, false positive, duplicate, or accepted risk. Record who approved closure and based on which evidence.

The final case file should link raw telemetry, timeline, decisions, changes, post-fix verification checks, related notifications, and action items. Never just screenshot an alert marked "Resolved," since that status proves neither root cause nor response effectiveness.

### Step 8: Post-Incident Review and Continuous Improvement

Evaluate detection latency, response time, which actions worked well, which logs were missing, which approval flows lagged, and which rules generated excessive low-value noise. Every improvement item needs an owner, priority, and due date. Reviews can remain blameless toward individuals while clearly establishing operational accountability and decision authority.

## 5. Roles and Escalation Mechanisms

| Role | Primary Responsibilities |
|---|---|
| On-call/SOC analyst | Verify, triage, create or update cases, collect initial context |
| Incident commander | Coordinate major incidents, set priorities, approve and track response actions |
| Application/service owner | Assess business impact, analyze app behavior, confirm recovery |
| Cloud/IAM/SRE engineer | Inspect permissions, infrastructure, logs, and execute technical fixes |
| Security/Compliance | Determine handling obligations, evidence standards, assist reviews and audits |
| Evidence custodian | Govern collection, handover, storage, integrity, and access to evidence |
| Independent auditor/reviewer | Cross-check evidence against control criteria and report gaps |

In small teams, one person may wear multiple hats, yet records must still specify who executed and who reviewed/approved. For sensitive changes, separate the person altering configurations from the approver or outcome verifier whenever feasible.

Notification channels must distinguish routine technical tasks, security incidents, and situations potentially affecting contractual/legal obligations. When data leakage is suspected, security and legal teams or designated organizational leads must be engaged per active procedures; never publish unsubstantiated conclusions prematurely.

## 6. Required Properties of Audit Evidence

Usable evidence must meet at least these criteria:

1. **Relevant:** directly supports a claim or control criterion.
2. **Traceable provenance:** specifies generating system, tenant/subscription/resource scope, export method, and exporter's permissions.
3. **Time-bounded:** includes timestamps, timezone, and observation window; out-of-period data should serve only as context.
4. **Reproducible:** captures queries, filters, policy IDs, alert IDs, or correlation IDs sufficient for an authorized person to reproduce results while data remains retained.
5. **Integrity:** preserves originals, restricts edits, and includes hashes or equivalent tamper protections where needed.
6. **Access-controlled:** only authorized personnel can view or handle it; avoid placing logs with personal data or secrets into public tickets.
7. **Explained:** states what the evidence proves, what it does not prove, and any data limitations.
8. **Retained per policy:** storage location, retention duration, legal hold needs, and post-obligation disposal methods must be defined.

### 6.1. Incident Evidence vs. Control Evidence

| Audit Question | Appropriate Evidence | Limitations to Interpret |
|---|---|---|
| Who modified Azure RBAC? | Azure Activity Log, current role assignments, change ticket | Activity Log shows control-plane actions; does not itself prove malicious intent |
| Were anomalous sign-ins investigated? | Entra sign-in logs, case record, SOC disposition, and outcomes | Sign-in logs may be missing if expired or lacking access prerequisites |
| Does Key Vault have audit logging enabled? | Diagnostic settings, ingested logs, pipeline check evidence | Current settings alone do not prove logs existed throughout the entire prior period |
| Are configuration policies followed? | Azure Policy assignments, compliance state, exemptions, remediation history | Compliance only checks rules defined in the policy |
| Are production pipelines approved? | Run ID, commit SHA, deployment record, approvals, and IAM permissions | Dashboard screenshots are supporting evidence; must link to source records |
| Are alerts handled on time? | Alert ID, ticket with state transition history and timestamps, escalation logs | Current status alone does not prove timing of each step |
| Is data recoverable? | Backup job history, retention settings, and restore test results | "Backup successful" does not replace testing restores |
| Are costs controlled? | Cost Management budgets, cost alerts, analysis reports, optimization decisions | Budget alerts do not automatically cap Azure spend |

A single control criterion often requires **multiple evidence sources**. For example, proving a permission change was authorized requires the approval ticket, the actual execution log, and post-change role assignment state.

### 6.2. Raw Data, Preserved Exports, and Presentations

Distinguish clearly:

- **Source data:** events recorded in Azure/Entra, ticketing systems, or security platforms.
- **Preserved exports:** JSON, CSV, or structured exports pulled with defined filters and stored in an evidence vault.
- **Analysis artifacts:** KQL queries, timelines, charts, or investigator notes.
- **Presentation artifacts:** executive summaries, screenshots, or conclusion tables sent to auditors.

Never alter raw data or overwrite original exports "to make them readable." If sensitive fields must be stripped for sharing, create a separate **redacted copy**, document which fields were masked, and keep the untouched original under strict access control.

Screenshots help explain UI state, but rarely suffice to verify completeness across thousands of events or historical changes. Prefer structured data and reproducible exports whenever possible.

## 7. Controlled Evidence Collection and Preservation

### 7.1. Chain of Custody

Chain of custody documents who collected evidence, where it was stored, who accessed/transferred it, and any changes from collection through audit. Its purpose is giving reviewers confidence that data was not altered outside documented procedures.

Example manifest record:

~~~json
{
  "evidenceId": "EV-SEC-2026-0042-01",
  "incidentId": "SEC-2026-0042",
  "source": "Azure Activity Log",
  "scope": "/subscriptions/<SUBSCRIPTION_ID>",
  "eventWindowStartUtc": "2026-11-20T08:00:00Z",
  "eventWindowEndUtc": "2026-11-20T09:00:00Z",
  "collectedAtUtc": "2026-11-20T09:20:00Z",
  "collectedBy": "soc-analyst-01",
  "exportFormat": "JSON",
  "fileName": "EV-SEC-2026-0042-01.json",
  "sha256": "<SHA256_OF_SAVED_FILE>",
  "storageReference": "<RESTRICTED_EVIDENCE_OBJECT_URI>",
  "classification": "confidential",
  "retentionPolicy": "<APPROVED_POLICY_ID>",
  "notes": "Export of role assignment events; see query record."
}
~~~

A manifest like the above **does not by itself prove** logs were collected accurately or the file is immutable. It must be paired with the actual file, access-controlled storage, access history, and the hashing method. A SHA-256 hash detects changes to the exported file's contents; it does not prove internal data was accurate or unaltered prior to export.

### 7.2. Minimum Collection Procedure

1. Record the case ID, data source, operator, tenant/subscription, and query criteria.
2. Export a wide enough time window to cover before, during, and after the signal; explicitly label ranges in UTC.
3. Prefer structured exports preserving all essential fields such as event ID, resource ID, caller, correlation ID, status, and timestamp.
4. Store the original export in an evidence repository with restricted RBAC, encryption, and access logging per organizational standards.
5. Compute the hash on the **exact saved file**, record it in the manifest, and protect the manifest under the same controls.
6. Perform analysis or redaction only on controlled copies; record operator and method.
7. Upon handover, log sender, recipient, timestamp, new location, and hash verification result.
8. Retain per retention policy and legal hold if applicable; purge on schedule only after confirming preservation obligations have ended.

Evidence storage can use Azure Blob Storage with encryption, private endpoints/network restrictions, Azure RBAC, and appropriate immutable storage mechanisms where required. **Immutable storage has specific modes and configuration prerequisites** (such as time-based retention or legal holds). Verify governance requirements and test before applying to data needing edits or deletion. Never confuse "Blob versioning enabled" with tamper-proof immutability.

### 7.3. Verifying File Integrity with SHA-256

On an authorized collection machine within an approved evidence directory, run:

~~~powershell
Get-FileHash -Algorithm SHA256 -LiteralPath ".\EV-SEC-2026-0042-01.json"
~~~

Or on Linux:

~~~bash
sha256sum EV-SEC-2026-0042-01.json
~~~

After copying, recompute the hash on the received copy and compare against the manifest. If mismatched, quarantine the file to investigate the cause—never overwrite or silently update the hash.

Avoid printing access tokens, connection strings, or secrets into unnecessary evidence files. Where personal data is present, apply matching classification and access policies. In formal forensic scenarios, security/legal teams must define specialized preservation protocols.

## 8. Hands-On Evidence Querying in Azure

The snippets below demonstrate **read-only** investigation. The operator requires proper permissions, and data must still fall within its retention window.

### 8.1. Azure CLI: Inspecting Azure Activity Log

Check the current subscription:

~~~bash
az account show --output table
~~~

List events over the last 24 hours:

~~~bash
az monitor activity-log list --offset 24h --output json
~~~

Scope to the application's resource group:

~~~bash
az monitor activity-log list \
  --resource-group rg-orders-prod \
  --offset 24h \
  --query "[].{time:eventTimestamp,operation:operationName.value,status:status.value,caller:caller,resource:resourceId,correlation:correlationId}" \
  --output json
~~~

Output reflects only Activity Log events queryable at execution time. When generating audit evidence, save the command, scope, query timestamp, and output file. Structured exports may still be bounded by pagination, permissions, or retention; verify completeness before drawing conclusions.

### 8.2. KQL: Investigating Role Assignment Changes

If Azure Activity Log is routed to a Log Analytics workspace populating the `AzureActivity` table, use Kusto Query Language:

~~~kusto
AzureActivity
| where TimeGenerated between (ago(24h) .. now())
| where OperationNameValue =~ "MICROSOFT.AUTHORIZATION/ROLEASSIGNMENTS/WRITE"
| project
    TimeGenerated,
    SubscriptionId,
    ResourceGroup,
    ResourceId,
    Caller,
    ActivityStatusValue,
    CorrelationId,
    OperationNameValue
| order by TimeGenerated asc
~~~

This query helps find role assignment create/update operations. Depending on log schema and event type, you may need to inspect detailed records or cross-check current role assignments to see exact principals, roles, and scopes modified. A "Write" operation alone does not prove permissions were granted illegitimately.

To track permission removals, also check `OperationNameValue` matching `ROLEASSIGNMENTS/DELETE`. Field names and representations depend on the log table; inspect the schema and a real record before concluding.

### 8.3. KQL: Investigating Microsoft Entra ID Sign-Ins

If sign-in logs are routed to a Log Analytics workspace, query the `SigninLogs` table:

~~~kusto
SigninLogs
| where TimeGenerated > ago(24h)
| where ResultType != "0"
| project
    TimeGenerated,
    UserPrincipalName,
    AppDisplayName,
    IPAddress,
    ResultType,
    ConditionalAccessStatus,
    CorrelationId
| order by TimeGenerated desc
~~~

Results show failed sign-ins and aid investigation, **without proving an account is compromised**. Some workloads using service principals or managed identities log to separate sign-in tables depending on export settings and licensing; never rely solely on user sign-in tables to conclude no workload activity occurred.

### 8.4. Checking a Service's Log Pipeline

Example listing diagnostic settings for an Azure resource:

~~~bash
az monitor diagnostic-settings list \
  --resource "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/<RESOURCE_GROUP>/providers/<PROVIDER_NAMESPACE>/<RESOURCE_TYPE>/<RESOURCE_NAME>" \
  --output json
~~~

Output shows diagnostic settings configured on supporting resources, such as destinations and enabled categories. To prove logs actually arrived, cross-check data in the corresponding Log Analytics, Storage, or Event Hub destination. If logs are missing during an audit window, explicitly document the gap and its identified or investigated cause—never infer "no events occurred."

### 8.5. Linking Evidence to Changes and Approvers

A legitimate role change should form a traceable chain:

~~~text
Change ticket CHG-1428
   |
   +-- Requester and business justification
   +-- Approval: approver, UTC timestamp
   +-- Pull request/commit and pipeline run (if using IaC)
   +-- Azure Activity Log: operation + correlationId
   +-- Post-change role assignment state
   +-- Permission verification result and closure sign-off
~~~

Every link should use specific IDs accessible to auditors under granted permissions. If a ticketing system only stores links to logs expiring after a few days, evidence may vanish before audit time. Plan timely exports/archival before expiration.

## 9. Real-World Scenario: Anomalous Permission-Grant Alert

**Scenario:** An orders application runs in a production subscription using Azure Key Vault and a CI/CD pipeline. Security receives an alert about a new role assignment operation on resource group `rg-orders-prod` outside normal deployment hours.

### 9.1. Verify the Signal

The alert indicates an operation involving `Microsoft.Authorization/roleAssignments/write`. The analyst opens case `SEC-2026-0042`, recording UTC timestamp, resource ID, caller, and correlation ID. Responders cross-check:

- Activity Log for the operation, status, and related event sequence.
- Current role assignments to identify principal, role, and scope.
- Microsoft Entra sign-in/audit logs (where relevant) to understand the API-calling identity.
- Pipeline run IDs and change tickets within the same time window.
- Subsequent operations on Key Vault or other resources if diagnostic logs were enabled.

They observe the caller is a pipeline service principal, yet no approved deployment exists. That warrants deeper investigation, though it is not yet sufficient to confirm an attack.

### 9.2. Assess and Respond

If the granted role carries high privileges in production without valid explanation, the incident commander may escalate priority, ask the IAM team to verify the identity, inspect token/credential sources, and narrow permissions or pause the pipeline per emergency procedures.

Before and during remediation, preserve related logs and snapshot initial role assignments. After containment, inspect other changes in the same timeframe, signs of data access, blast radius, and credential rotation needs. Even if a legitimate automation bug is found, the team still must fix the pipeline, documentation, and approval gates to prevent recurrence.

### 9.3. Post-Handling Audit Package

| Artifact | Minimum Content |
|---|---|
| SEC-2026-0042 | Timeline, severity, responders, conclusions, decisions, and timestamps |
| EV-01 | Azure Activity Log export, commands/KQL, scope, and hash |
| EV-02 | Cross-check of role assignments, scope, and principals |
| EV-03 | Pipeline run, commit, approval records or documentation of missing approval |
| EV-04 | Related Entra logs and Key Vault diagnostic logs, if available |
| EV-05 | Action/rollback records, approvers, and outcomes |
| EV-06 | Final verification results, detection rule updates, and action items |

If data-plane logging was never enabled, the report must state **insufficient visibility to conclude** on certain data-read actions, rather than asserting zero access occurred. Honest reporting of gaps is essential for credible audit evidence.

## 10. Automating Alerts and Evidence Preservation Safely

Azure Monitor Action Groups, Logic Apps, Azure Functions, Automation, or Microsoft Sentinel automation/playbooks (when deployed) can assist with:

- Creating cases and paging on-call teams from alerts.
- Normalizing resource IDs, severities, timestamps, and log links.
- Looking up resource metadata, owners, tags, and change windows.
- Collecting read-only snapshots following templates and exporting structured records into controlled storage.
- Routing approval requests for risky containment actions.
- Tracking overdue items, sending escalation reminders, and generating periodic reports.

Clearly separate **collection/enrichment automation** from **modification or deletion automation**. Locking accounts, deleting resources, altering network rules, or rotating credentials can cause outages and alter forensic evidence. Where auto-remediation exists, define triggers, scope, idempotency, execution privileges, audit trails, circuit-breakers/pause switches, and rollbacks.

Automation identities should use managed identities on supporting Azure services or workload identity federation in CI/CD rather than hardcoded secrets. Grant least-privilege RBAC and store secrets (only when truly needed) in approved secret stores. Never grant an alert-handling workflow subscription-wide Owner just to write one evidence artifact.

### Reducing Noise and Improving Alert Quality

When alerts overwhelm responders, critical signals get missed. Improve iteratively:

1. Measure false positive rates, duplicate alerts, and ownerless alerts.
2. Tune thresholds, correlation logic, evaluation windows, dynamic thresholds, or suppression per tool capabilities.
3. Enrich with context such as environment, `Criticality` tag, change windows, and affected entities.
4. Link each rule to a runbook specifying verification steps and escalation criteria.
5. Re-evaluate effectiveness after tuning and keep rule modification histories.

Disabling a rule should only occur with a documented decision and suitable compensating controls; avoid cutting alert counts simply by silencing risk signals.

## 11. Alert Handling Record Template

Organizations may use different case management tools, yet a minimal record should capture these fields:

~~~yaml
caseId: SEC-2026-0042
alertSource: Azure Monitor
alertId: "<SOURCE_ALERT_ID>"
detectedAtUtc: "2026-11-20T08:41:00Z"
acknowledgedAtUtc: "2026-11-20T08:45:00Z"
tenantId: "<TENANT_ID>"
subscriptionId: "<SUBSCRIPTION_ID>"
resourceId: "<RESOURCE_ID>"
severity: P2
status: Investigating
owner: team-security-operations
summary: "Unplanned role assignment write on production resource group"
businessImpact: "Under investigation"
observedFacts:
  - "Role assignment write operation recorded"
hypotheses:
  - "Possible unapproved deployment credential use"
evidenceRefs:
  - EV-SEC-2026-0042-01
actions:
  - atUtc: "2026-11-20T09:10:00Z"
    approvedBy: "<APPROVER>"
    actor: "<OPERATOR>"
    description: "Restricted deployment identity pending review"
    outcome: "Completed; verified by IAM engineer"
decision: "Open - scope still being assessed"
nextReviewAtUtc: "2026-11-20T10:00:00Z"
~~~

Values in this template are illustrative only and do not describe a real incident. The finalized case should add chronological events, links to raw records, closure approver, recovery sign-off, and root cause once sufficiently investigated.

### Pre-Closure Record Quality Check

- Are the case ID and original alert IDs present?
- Do all events and actions carry UTC timestamps?
- Are observed facts clearly separated from hypotheses or conclusions?
- Have scope, resources, authorized principals, and affected data ranges been identified?
- Does evidence exist for actions marked complete?
- Are missing logs documented alongside resulting conclusion limits?
- Are raw exports and hashes saved in access-controlled storage?
- Are the closure approver and action-item owners clearly named?

## 12. Common Mistakes

**Relying solely on tool-assigned severity.** Alert severity and business impact often differ. Evaluate environment, data sensitivity, and blast radius.

**Marking "Resolved" without proving remediation.** Alert status does not replace logs, post-fix checks, and service-owner sign-off.

**Assuming Azure retains all logs forever.** Each source has distinct retention and export settings. Configure upfront, test queries, and monitor ingestion.

**Taking screenshots instead of preserving raw data.** Screenshots can omit filters, timestamps, paginated rows, and context. Pair with JSON/CSV exports or reproducible queries where appropriate.

**Pasting secrets and sensitive data into shared tickets.** Logs and evidence may contain restricted data. Share strictly via controlled repositories and channels; use redacted copies when needed.

**Deleting resources or rotating tokens without logging.** This can erase forensic trails or break services. Preserve feasible evidence and record rationale, especially during emergencies.

**Confusing control-plane logs with data-plane logs.** Activity Log showing ARM actions does not prove whether an app read data. Enable service-specific resource logs.

**Creating policies/audit rules and assuming compliance is achieved.** You need data proving rules applied, alerts were triaged, and exceptions were governed.

**Failing to designate an evidence custodian.** Data can scatter across locations, expire, or lack an accountable party during audits. Assign an evidence custodian and retention schedule.

## 13. Self-Check

1. **Is an alert automatically an incident?** No. Verify, triage, and assess impact before classifying.
2. **Does Azure Activity Log prove every secret read from Key Vault?** No. Configure and inspect appropriate data-plane logs.
3. **What are three essential elements in an evidence record?** Provenance/scope, UTC timestamps/collection method, and integrity verification; access controls and limitation notes are also required.
4. **Is a file with a SHA-256 hash automatically valid evidence?** No. A hash only detects post-computation file modifications; provenance and chain of custody are still required.
5. **What evidence proves an Azure RBAC change was approved?** Ticket/approval, execution log, actual role assignment state, and verification results.
6. **If a KQL query returns zero rows, can you conclude no event occurred?** Not yet. Check query scope, permissions, log source, retention window, and ingestion status.
7. **After silencing a faulty alert, why is a post-incident review still needed?** To identify root cause, control gaps, and measures preventing recurrence.
8. **Should you automatically delete an entire workload on a high-severity security alert?** Not by default. Consider false positives, evidence impact, blast radius, and runbook approvals.
9. **Who decides evidence retention duration?** Organizational policy driven by risk, contracts, audit obligations, and applicable laws; no single timeline fits all cases.
10. **Why must data limitations be stated in reports?** To avoid drawing conclusions beyond what available evidence can substantiate.

## 14. References

- [Azure Monitor documentation](https://learn.microsoft.com/azure/azure-monitor/) — alerts, logs, metrics, and diagnostic settings.
- [Azure Activity Log](https://learn.microsoft.com/azure/azure-monitor/essentials/activity-log) — subscription control-plane events.
- [Azure Monitor Logs / KQL](https://learn.microsoft.com/azure/azure-monitor/logs/log-query-overview) — querying and analyzing logs.
- [Microsoft Defender for Cloud](https://learn.microsoft.com/azure/defender-for-cloud/) — security posture, recommendations, and security alerts.
- [Microsoft Sentinel](https://learn.microsoft.com/azure/sentinel/) — detection, investigation, and incident orchestration.
- [Microsoft Entra monitoring and health](https://learn.microsoft.com/entra/identity/monitoring-health/) — sign-in logs and identity auditing.
- [Azure Policy](https://learn.microsoft.com/azure/governance/policy/) — configuration compliance evaluation.
- [Azure Blob immutable storage](https://learn.microsoft.com/azure/storage/blobs/immutable-storage-overview) — mechanisms protecting retained data.
- [Azure RBAC](https://learn.microsoft.com/azure/role-based-access-control/overview) — resource-scoped authorization.

In real environments, always cross-check configurations, log tables, and deployed features. A strong audit report presents both the evidence supporting conclusions and any remaining data limitations.
