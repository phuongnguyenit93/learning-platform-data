# Collecting and Investigating Events with Microsoft Sentinel

> **Chapter:** Security and Compliance  
> **Module:** CLOUD_PROVIDERS_AZURE — Explore the Microsoft Azure ecosystem from subscriptions, resource groups, and Entra ID to virtual networks, compute services, storage, and data; learn how to deploy, monitor, protect, and control costs of application architectures on Azure.

## Learning Objectives

After this lesson, you will be able to:

- Explain the role of **Microsoft Sentinel** in security monitoring and incident response across Azure and other systems.
- Identify event sources to collect, how to connect them into a Sentinel environment, and how to verify data quality.
- Use **Kusto Query Language (KQL)** to explore sign-in events, permission changes, and anomalous indicators.
- Distinguish **logs, alerts, incidents, entities, analytics rules, hunting**, and **playbooks**.
- Describe an incident investigation workflow from intake, verification, and scope expansion to remediation and post-incident review.
- Recognize limitations around access permissions, log latency, privacy, retention, and costs.

## 1. What Problem Does Microsoft Sentinel Solve?

In an application deployed on Azure, signs of intrusion do not necessarily appear in one place. For example, a compromised account may generate a sequence of events:

1. Multiple failed sign-in attempts appear in **Microsoft Entra ID**.
2. A successful sign-in occurs afterward.
3. The account modifies access permissions on a resource group.
4. A server or service begins connecting to an unusual network address.

If operations teams only look at the Azure portal for each individual service, it is hard to piece the traces into a unified story.

**Microsoft Sentinel** is a cloud-native **SIEM** (*Security Information and Event Management*) and **SOAR** (*Security Orchestration, Automation and Response*) solution. It helps:

- **Collect and centralize** security signals from Azure, Microsoft 365, devices, applications, on-premises systems, and third-party services.
- **Detect** noteworthy behavior using analytics rules, queries, and detection capabilities depending on the data source.
- **Correlate and investigate** alerts into incidents, surfacing accounts, devices, IPs, resources, and timelines.
- **Coordinate response** through automation rules and playbooks, with the option to require human approval for sensitive actions.

In a common deployment model, data is ingested into a **Log Analytics workspace**; Sentinel uses the workspace and security integrations for analysis and investigation. Certain capabilities, interfaces, and data storage locations may vary depending on the service and configuration supported by Microsoft at deployment time.

### Comparing Easily Confused Services

| Service | Focus | Example |
| --- | --- | --- |
| **Azure Monitor / Log Analytics** | Collect, query, and monitor operational telemetry | Viewing app errors, VM performance, querying logs |
| **Microsoft Defender for Cloud** | Security posture assessment, recommendations, and workload protection capabilities | Detecting weak configurations or threats against protected resources |
| **Microsoft Entra ID** | Authentication, identity governance, and access control | Sign-in logs, audit logs, Conditional Access |
| **Microsoft Sentinel** | Centralizing security signals, detection, investigation, and response orchestration | Detecting sequences of failed sign-ins and suspicious permission changes |

These services complement one another. Sentinel can ingest data or alerts from the other services, but **enabling Sentinel does not mean all log sources are automatically collected**.

## 2. Understanding Key Concepts in the Investigation Flow

| Concept | Meaning | Example |
| --- | --- | --- |
| **Event / log record** | A record of an activity at a specific point in time | User fails to sign in |
| **Data connector** | Method of connecting a data source to the Sentinel environment | Connecting Microsoft Entra ID |
| **Log Analytics table** | Table holding records queried via KQL in the workspace model | `SigninLogs`, `AzureActivity` |
| **Analytics rule** | Analytical condition that generates an alert when data meets criteria | 10 or more failed sign-ins within 15 minutes |
| **Alert** | Signal indicating a rule or product detected activity requiring review | "Multiple failed sign-in attempts" |
| **Incident** | Investigation case file, which can group one or more alerts and related data | "Potential compromised account" |
| **Entity** | Object extracted for linked investigation | Account, IP address, host |
| **Hunting** | Proactive querying to look for signs not yet caught by rules | Searching for anomalous accounts over 7 days |
| **Automation rule** | Event-handling rule orchestrating workflow steps | Assigning an incident to the on-call team |
| **Playbook** | Automated workflow, typically built on Azure Logic Apps | Sending notifications, creating tickets, enriching context |

**A log is not an alert; an alert is not an incident.** A log record may be completely normal. An analytics rule typically only creates an alert when conditions are met; multiple alerts can be grouped into a single incident to avoid duplicate handling.

## 3. Ingestion and Detection Architecture

~~~mermaid
flowchart LR
    A["Microsoft Entra ID\nSign-in / Audit"]
    B["Azure subscription\nActivity / Resource logs"]
    C["VM, Firewall, Hybrid\nWindows / Syslog / CEF"]
    D["Microsoft Defender\nAlerts / Incidents"]
    E["Data connectors\nDiagnostic settings / AMA / API"]
    W["Log Analytics workspace\nand related data"]
    Q["KQL / Analytics rules\nHunting / Workbooks"]
    I["Alerts → Incidents"]
    R["Triage → Investigation\n→ Response"]
    P["Automation rules\nLogic Apps playbooks"]

    A --> E
    B --> E
    C --> E
    D --> E
    E --> W
    W --> Q
    Q --> I
    I --> R
    I --> P
    P --> R
~~~

The diagram illustrates a common workflow; certain product integrations and data types may have their own connection methods or synchronization mechanisms.

Key components:

1. **Data sources:** where events originate. You must identify which services have required logs and their log-export capabilities.
2. **Ingestion pipeline:** data connectors, diagnostic settings, Azure Monitor Agent (AMA), Data Collection Rules (DCR), or other integration mechanisms.
3. **Data store and querying:** the Log Analytics workspace holds corresponding tables; KQL queries search and correlate signals.
4. **Detection:** analytics rules and alerts from integrated products route notable signals into the triage queue.
5. **Investigation and response:** analysts verify the incident, assess impact, execute response actions within authority, and document outcomes.

### Selecting Log Sources Based on Investigation Questions

| Security Question | Suggested Source | Common KQL Table |
| --- | --- | --- |
| Who signed in? Why did it fail? | Microsoft Entra sign-in logs | `SigninLogs` |
| Who modified Entra identities, groups, or roles? | Microsoft Entra audit logs | `AuditLogs` |
| Who created, deleted, or updated Azure resources on the control plane? | Azure Activity Log | `AzureActivity` |
| What sign-in/system privilege events occurred on Windows servers? | Windows Security Events via AMA | `SecurityEvent`; actual table depends on connector/config |
| What did Linux hosts or Syslog-emitting systems record? | Syslog via AMA | `Syslog` |
| What signals did network appliances sending Common Event Format emit? | CEF via supported collection mechanism | `CommonSecurityLog` |
| What alerts did endpoint protection tools raise? | Microsoft Defender integration or other EDR sources | Depends on connector and integration model |

**Azure Activity Log differs from Entra sign-in logs.** Activity Log describes Azure resource management operations (control plane), such as creating a VM or changing a role assignment in Azure RBAC. Sign-in logs answer identity authentication questions; both are frequently needed when investigating account abuse.

For operations **inside** a service, such as accessing a blob or reading a secret, check how to enable the corresponding **resource logs**. Never assume Azure Activity Log records every data-plane operation.

## 4. Preparing the Sentinel Environment

### 4.1. Defining Scope and Permissions

Before configuring, answer:

- Which **subscriptions, resource groups, applications, tenants**, and external sources must be monitored?
- Who is responsible for SOC operations, rule management, cost control, and data protection?
- Does the data have **storage location, retention period, or privacy** requirements?
- Which sources should be prioritized first to support a specific detection scenario?

A sensible starting scope for an Azure application is **Entra sign-in, Entra audit, Azure Activity**, and security logs from core workloads. Expand after verifying signal quality, latency, and cost.

Access permissions depend on the task performed. For example, Microsoft Sentinel Reader/Responder/Contributor roles grant different permission levels within Sentinel; workspace administration, configuring diagnostic settings, Entra administration, and running playbooks may require **separate additional permissions**. The principle is least privilege and separation of duties among viewers, investigators, rule editors, and automation managers.

### 4.2. Preparing a Log Analytics Workspace and Enabling Sentinel

In an environment with appropriate permissions:

1. Go to the Azure portal and create or select a **Log Analytics workspace** in an approved subscription, resource group, and region.
2. Verify the workspace's security settings, access permissions, data retention, and cost estimates.
3. Enable or connect **Microsoft Sentinel** to the workspace following the current product procedure.
4. Open **Data connectors** in the Sentinel interface used by your organization. Depending on interface transition stages, some Sentinel investigation and management experiences may be performed from the **Microsoft Defender portal**.
5. Verify that the workspace, tenant, subscription, and access permissions are all correct before ingesting live data.

Creating workspaces and enabling connectors can incur costs from data ingestion, retention, or related services. Use an authorized practice subscription and configure budgets/cost monitoring before scaling out.

### 4.3. Connecting Priority Data Sources

**A. Microsoft Entra ID**

Connect sign-in and audit sources following the data connector instructions applicable to your tenant. Configuration may involve Entra admin permissions, diagnostic export settings, and licensing prerequisites for each log type.

After connecting, check tables such as `SigninLogs` and `AuditLogs`. Depending on log types and integrations, table names or ingestion paths to the workspace may differ; verify the actual tables on the connector page and in the workspace schema.

**B. Azure Activity**

Connect management activity data from the subscriptions requiring monitoring. Verify data arrives in the `AzureActivity` table and cross-check source subscriptions using the relevant identifier field. Having permission on one subscription does not automatically let someone configure connectors for every other subscription.

**C. Windows, Linux, and Network Appliances**

For agent-based sources, consider **Azure Monitor Agent (AMA)** and **Data Collection Rules (DCR)** to specify collected data, transport paths, and valid filters. Windows Security Events, Syslog, and CEF have distinct deployment, OS/device, and configuration requirements.

For example, a Windows server may require an AMA connection and a DCR selecting the appropriate Security Events channel; simply enabling Sentinel without configuring collection for the server gives no reason to expect the `SecurityEvent` table will contain data.

**D. Integrating Alerts from Other Security Products**

Signals from Microsoft Defender and other products can be integrated via supported connectors. Determine whether the data is **raw logs, alerts, or synchronized incidents**, avoiding multiple ingestion paths for the same signal that would cause duplicate alerts.

### 4.4. Validating Data Before Writing Rules

Do not treat a connector's "Connected" status as sufficient. Check:

1. **Does the table exist and contain recent data?**
2. **Do analytical fields have values?** Such as `UserPrincipalName`, `IPAddress`, or `Caller`.
3. **Is the data coming from the right tenant/subscription/host?**
4. **What is the ingestion latency?** Many log sources do not arrive instantaneously.
5. **Are there missing records, timezone offsets, formatting errors, or duplicate signals?**

Initial validation query:

~~~kusto
// Run in a workspace that has the Entra sign-in connector enabled.
SigninLogs
| where TimeGenerated >= ago(24h)
| summarize
    TotalEvents = count(),
    LatestEventUtc = max(TimeGenerated),
    DistinctAccounts = dcount(UserPrincipalName)
~~~

For Azure management activity:

~~~kusto
AzureActivity
| where TimeGenerated >= ago(24h)
| summarize Events = count(), LatestEventUtc = max(TimeGenerated)
    by SubscriptionId
| order by Events desc
~~~

**How to interpret:** If there are no results, first check permissions, connector status, workspace, time range, and whether the source is actually generating logs. An empty table does not prove an environment is safe; it may indicate a **blind spot in visibility**.

### 4.5. Latency and Time in Investigations

`TimeGenerated` is the timestamp attached to the record per the data source's model; the time the system receives the log may be later. KQL also provides `ingestion_time()` in supported contexts, though you should not assume every source provides identical latency metadata.

When comparing events across multiple systems:

- Use **UTC** or explicitly label timezones when building timelines.
- Account for ingestion latency and source clock skew.
- Choose a wide enough query window to avoid missing delayed logs.
- Record both the event timestamp and the time the analyst observed it.

## 5. Querying Events with KQL

**Kusto Query Language (KQL)** is a tabular query language well-suited for filtering events, grouping, aggregating, and correlating log sources in Log Analytics.

Common operators:

| Operator | Purpose |
| --- | --- |
| `where` | Filters records matching a condition |
| `project` | Selects/renames output columns |
| `extend` | Computes additional columns |
| `summarize` | Groups and aggregates, e.g., `count()`, `dcount()` |
| `sort by` or `order by` | Sorts results |
| `join` | Combines datasets on a key |
| `bin()` | Buckets time into intervals for trend analysis |
| `ago()` | Computes a timestamp relative to the current time |

### 5.1. Finding Accounts with Repeated Failed Sign-Ins

~~~kusto
SigninLogs
| where TimeGenerated >= ago(24h)
| where tostring(ResultType) != "0"
| summarize
    FailedAttempts = count(),
    DistinctSourceIPs = dcount(IPAddress),
    FirstSeenUtc = min(TimeGenerated),
    LastSeenUtc = max(TimeGenerated)
    by UserPrincipalName
| where FailedAttempts >= 10
| order by FailedAttempts desc
~~~

**Meaning:** finds accounts with at least 10 unsuccessful sign-in records in 24 hours, counting distinct source IPs and the time range observed.

**Do not conclude an account is compromised from a threshold count alone.** A user mistyping a password, a legacy app caching stale credentials, or automated retry logic can produce a similar failure streak. Inspect error codes, application names, IPs, timestamps, and account context.

### 5.2. Viewing Failure Trends in 15-Minute Intervals

~~~kusto
SigninLogs
| where TimeGenerated >= ago(24h)
| where tostring(ResultType) != "0"
| summarize FailedAttempts = count()
    by bin(TimeGenerated, 15m)
| order by TimeGenerated asc
~~~

The output shows failure counts per time bucket. Combine this query with filters by account, application, or IP address to pinpoint spikes.

### 5.3. Finding Permission Changes on the Azure Control Plane

~~~kusto
AzureActivity
| where TimeGenerated >= ago(7d)
| where OperationNameValue has "Microsoft.Authorization/roleAssignments/"
| project
    TimeGenerated,
    Caller,
    OperationNameValue,
    ActivityStatusValue,
    ResourceId,
    CorrelationId
| order by TimeGenerated desc
~~~

This is a starting point to locate activities related to **Azure RBAC role assignments**. Inspect operation details, success/failure status, scope, actor, and whether an approved change request exists. Exact operation names and field values depend on how the source logs events.

To investigate changes to **administrative roles inside Entra ID**, use Entra audit logs:

~~~kusto
AuditLogs
| where TimeGenerated >= ago(7d)
| where Category =~ "RoleManagement"
| project
    TimeGenerated,
    OperationName,
    Result,
    InitiatedBy,
    TargetResources,
    CorrelationId
| order by TimeGenerated desc
~~~

These two queries cover **two distinct role systems**: Azure RBAC for Azure resources and Entra administrative roles for the identity directory.

### 5.4. Finding a Successful Sign-In After a Sequence of Failures

~~~kusto
let FailuresByAccount =
    SigninLogs
    | where TimeGenerated >= ago(2h)
    | where tostring(ResultType) != "0"
    | summarize
        FailedAttempts = count(),
        LastFailedUtc = max(TimeGenerated)
        by UserPrincipalName
    | where FailedAttempts >= 5;
SigninLogs
| where TimeGenerated >= ago(2h)
| where tostring(ResultType) == "0"
| join kind=inner FailuresByAccount on UserPrincipalName
| where TimeGenerated between (LastFailedUtc .. LastFailedUtc + 30m)
| project
    SuccessTimeUtc = TimeGenerated,
    UserPrincipalName,
    IPAddress,
    AppDisplayName,
    FailedAttempts,
    LastFailedUtc
| order by SuccessTimeUtc desc
~~~

This query is a **correlation hint by account and time**, not proof that the successful sign-in belongs to the same person or attack campaign as the failures. If there were multiple failure bursts, summarizing by `LastFailedUtc` may miss earlier streaks. When turning this into a production rule, tune the time window, session, IP, device, application, and log latency handling.

### 5.5. KQL Only Works on Real Data

The statements above require the table to exist in the workspace, the connector to be feeding data, and the user to have query permissions. If you encounter an error like "Failed to resolve table," check the **table name and connected data**. Never invent dummy tables by arbitrarily renaming them just to make a query run; verify the actual schema present.

## 6. Turning Queries into Alerts and Incidents

Using KQL for **hunting** is exploratory. For recurring monitoring, you can build a **scheduled analytics rule** based on the same detection logic.

For example, suppose the security team wants an alert when an account has **10 or more failed sign-ins coming from at least two IPs within 15 minutes**:

~~~kusto
SigninLogs
| where TimeGenerated >= ago(15m)
| where tostring(ResultType) != "0"
| summarize
    FailedAttempts = count(),
    DistinctIPs = dcount(IPAddress),
    FirstSeenUtc = min(TimeGenerated),
    LastSeenUtc = max(TimeGenerated)
    by UserPrincipalName
| where FailedAttempts >= 10 and DistinctIPs >= 2
~~~

### Designing a Rule with an Operational Mindset

1. **Name and purpose:** e.g., "Multiple failed sign-ins from multiple IPs."
2. **Source and schedule:** select the workspace, run frequency, and lookback period aligned with ingestion latency. For example, run every 5 minutes with a 15-minute overlapping lookback.
3. **Trigger condition:** if the query returns at least one row, handle according to the rule configuration. Understand grouping, event grouping, and limits of the rule type used.
4. **Entity mapping:** map the account using `UserPrincipalName`; for IPs, shape query output appropriately to map a specific IP address if needed. Aggregate values like IP count do not themselves represent an IP entity.
5. **Severity and classification:** set severity according to organizational context and detection hypothesis. Standardize technical names, investigation descriptions, and handling instructions.
6. **Incident settings and grouping:** configure incident creation and group related alerts to reduce duplicates.
7. **Testing and tuning:** evaluate against sample data, permitted historical lookback, and approval workflows before enabling in production.

**Note on duplicate alerts:** if a rule runs every 5 minutes with a 15-minute lookback, a single burst of logs may satisfy the condition across multiple runs. Configure sensible grouping, suppression/deduplication, and check for gaps caused by delayed ingestion.

**Note on false positives:** multiple IPs can originate from VPNs, proxies, corporate egress, or users frequently switching networks. Enrich with account risk signals, application type, error codes, trusted IPs, and post-sign-in events before escalating severity.

Never enable automated account lockouts from an experimental rule before evaluating user impact and approval requirements.

## 7. Systematic Incident Investigation Workflow

Suppose Sentinel generates an incident: **"Multiple failed sign-ins followed by success for deployment account."** An investigation workflow can follow seven steps.

### Step 1 — Intake and Triage

Open the incident in the Sentinel/Defender portal interface used by your environment, and review the title, severity, timestamp, alert source, analytics rule, owner, status, and related entities.

Confirm whether this requires investigation or is a recurring alert caused by an authorized change. Document what is known and unknown. Assign an incident owner per on-call operations procedures.

### Step 2 — Inspect Raw Log Sources

Open the raw records supporting the alert. Check:

- UTC timestamps, query window, and ingestion latency.
- Account, application, sign-in type, status, error codes.
- IP, host/device, and contextual details actually recorded in the logs.
- Which rule generated the alert; whether data is duplicated, missing, or filtered.

**Never treat an incident title as a forensic conclusion.** An incident is a starting point for verification.

### Step 3 — Build a Timeline

Example:

| Time (UTC) | Signal | Hypothesis to Verify |
| --- | --- | --- |
| 08:00–08:05 | 12 failed sign-in attempts | Possible credential-guessing activity |
| 08:07 | One successful sign-in | Is the success tied to the prior failure streak? |
| 08:10 | Azure RBAC change in subscription | Who performed it, at what scope, and was it approved? |
| 08:16 | Workload shows unusual network connection | Related to the account, workload, or an authorized change? |

This table is a **simulated scenario**, not real events. Link events using reliable keys such as account identifiers, request/correlation IDs, resource objects, and time windows; merely being "close together" in time is not sufficient.

### Step 4 — Expand the Scope

Run hunting queries to look for:

- Other accounts using the same source IP or experiencing similar failure sequences.
- Successful sign-ins near the suspicious timeframe.
- Permission changes, group membership additions, new apps, or new credentials.
- Anomalous activity on resources the account can access.
- Related endpoint/network signals, if those source logs are collected.

Leverage **Entities, Investigation, Logs, Hunting, Bookmarks**, and available investigation features depending on your environment's UI/capabilities. Conclusions must clearly separate **observations from logs**, **inferences**, and **claims lacking evidence**.

### Step 5 — Assess Impact and Confidence

Identify affected identities and resources, effective permissions of the principal, accessible data, duration of activity, potential lateral spread to other environments, and operational disruption of response actions.

For example, an account with only Reader on one resource group carries different risk than an account with Owner on a production subscription. Yet Reader can still view sensitive information depending on the resource and data-plane permissions, so inspect effective permissions rather than guessing from role names.

### Step 6 — Respond per Approved Procedures

Depending on evidence and authority, the response team may:

- Request verification from the account owner or change owner.
- Revoke sign-in sessions or disable suspected access methods via appropriate identity mechanisms.
- Review/revoke newly granted unauthorized permissions.
- Isolate affected workloads, rotate keys/secrets, and block malicious activity per runbook.
- Create tickets, notify relevant teams, and preserve evidence.

Response actions can affect production; blocking, disabling, or deleting should have approval mechanisms and recovery plans. **Never delete raw data or suspected resources just to close an incident.**

### Step 7 — Close the Incident and Improve Detection

Archive conclusions, evidence, relevant KQL queries, missing log sources, approvers, remediation actions, and recovery timestamps. Set the incident status/classification per actual procedures, such as true positive or false positive when justified.

After the investigation, review tuning connectors, alert thresholds, entity mappings, grouping, automation, and access controls. A key takeaway is often **increasing visibility** and reducing detection time next time.

## 8. Hunting: Searching for Signals Without Alerts

**Threat hunting** is the proactive process of forming hypotheses and searching for evidence in data. For example:

> Hypothesis: a user experienced a burst of failed sign-ins and performed resource management operations immediately afterward.

Approach:

1. Identify required sources: `SigninLogs` and `AzureActivity`.
2. Find accounts with notable sign-in behavior.
3. Correlate `UserPrincipalName` with `Caller`, while verifying identifier compatibility (same user, service principal, casing differences, display name).
4. Narrow the time window to inspect resource actions near the suspicious timeframe.
5. Record evidence, data gaps, and outcomes, even when the hypothesis is disproven.

Example listing Azure Activity showing permission grants and inspecting actors:

~~~kusto
AzureActivity
| where TimeGenerated between (ago(24h) .. now())
| where OperationNameValue has "Microsoft.Authorization/roleAssignments/"
| summarize
    Operations = count(),
    FirstSeenUtc = min(TimeGenerated),
    LastSeenUtc = max(TimeGenerated)
    by Caller, ActivityStatusValue
| order by Operations desc
~~~

When correlating multiple tables, KQL supports `join`. However, analysts must verify **whether the join keys carry the same business meaning**. Two identical text strings do not necessarily denote the same principal or session.

### Data Normalization

Devices may call the same concept by different names, such as `src_ip`, `sourceAddress`, or `IPAddress`. **ASIM (Advanced Security Information Model)** provides normalized schemas for many event types in Microsoft Sentinel, enabling reuse of detection/hunting logic across supported sources.

Normalization reduces effort when integrating multiple sources, but does not fabricate missing data and does not replace verifying parsers, schemas, or log completeness.

## 9. Automating Response with Automation Rules and Playbooks

An incident involves many repetitive steps: assigning an owner, enriching details, notifying an on-call channel, creating a ticket, or requesting approval. Sentinel can orchestrate these steps using **automation rules** and **playbooks**.

- **Automation rule:** evaluates conditions and applies Sentinel-supported actions; can trigger a playbook when configured.
- **Playbook:** a workflow built on **Azure Logic Apps** that can invoke connectors/APIs to send notifications, gather context, and perform actions on related systems.

Example of a safe early-stage playbook:

~~~mermaid
flowchart TD
    A["New incident with matching severity"]
    B["Automation rule checks conditions"]
    C["Logic Apps playbook"]
    D["Fetch incident details and entities"]
    E["Create ticket / send notification"]
    F["On-call analyst verifies"]
    G{"Evidence and approval present?"}
    H["Execute action per runbook"]
    I["Add notes / continue investigation"]

    A --> B --> C --> D --> E --> F --> G
    G -->|Yes| H
    G -->|Not yet| I
~~~

In production deployments:

- Grant the playbook and its workflow execution identity only necessary permissions.
- Verify Sentinel's permission to trigger the playbook, Logic Apps access rights, and permissions of each connector used.
- Design actions to be idempotent, prevent duplicate execution, and keep execution logs.
- Test with simulated data; never execute destructive actions automatically during initial testing.
- Require **human approval** for disruptive actions such as locking accounts, blocking services, or revoking broad permissions.

Automation shortens repetitive steps but never replaces analyst judgment on incidents with unclear context.

## 10. Data Security, Compliance, and Operational Costs

Collecting more logs is not automatically better. An effective Sentinel program must answer **why the data is needed, how long it is kept, and who is allowed to view it**.

### 10.1. Access Control and Sensitive Data

Logs may contain IP addresses, usernames, resource identifiers, file paths, and data related to personal activity. Therefore:

- Restrict workspace query permissions and incident access by appropriate role.
- Control sharing/exporting search results or forwarding logs via playbooks.
- Mask or limit sensitive fields when not needed for detection.
- Comply with organizational retention policies, data residency rules, and evidence-handling procedures.
- Record who investigated, what was found, and which remediation decisions were approved.

Never place real access secrets, passwords, or tokens inside examples, incident notes, or tickets.

### 10.2. Retention and Historical Investigation Capability

The ability to query older events depends on **data tier, retention configuration, access policies, and current storage/query capabilities**. If an incident is discovered weeks later after logs have expired, forensic tracing will be constrained.

Do not assume enabling a connector today automatically pulls all historical logs from before. Backfill capability depends on the specific source and connector.

### 10.3. Factors Affecting Cost

| Factor | Typical Impact | How to Control |
| --- | --- | --- |
| **Data ingestion volume** | High-volume or verbose sources increase ingested GB | Select high-value sources, filter properly, estimate GB/day |
| **Retention duration and tier** | Longer retention or different historical query methods can add charges | Align with investigation and compliance needs |
| **Log/connector types and add-on services** | Some sources, security products, and licenses have separate pricing | Verify applicable terms and service pricing |
| **Automation/Logic Apps** | Workflow runs, actions, and connector calls may incur charges | Avoid loops, prevent duplicate triggers, monitor runs |
| **Expanding monitoring scope** | Adding subscriptions, endpoints, and devices increases volume | Roll out in phases and measure actual spend |

Pricing models and tier names can change. When budgeting, use official pricing applicable to your **region, workspace, data type, and organizational terms**. Never estimate cost solely from alert or incident counts.

## 11. Guided Practice: From Events to Investigation Hypotheses

### Scenario

A team operates an internal application on Azure using Entra ID for users and deploying infrastructure across Dev/Prod subscriptions. The team wants to detect anomalous failed sign-in bursts before inspecting Azure permission changes.

**Goal:** practice querying, interpreting results, and determining investigative actions. If you have an authorized lab workspace, you can compare against real data; the simulated section below requires no resource creation or generating failed login traffic.

### Part A — Inspecting Real Data (If Authorized)

1. Open the assigned Sentinel workspace and confirm the right tenant/subscription.
2. Verify the Entra sign-in and Azure Activity connectors are ingesting data.
3. Run the query in section **5.1**, recording accounts with many failures, `FirstSeenUtc`, `LastSeenUtc`, and distinct source IP counts.
4. If signals warrant review, query related successful sign-ins and Azure Activity within a matching time window.
5. Write down one evidence-backed conclusion and one hypothesis still requiring verification.

Read data only within authorized scopes. Do not deliberately generate failed logins with real accounts just to create test data.

### Part B — Standalone Simulated Data

The following KQL snippet **generates 12 synthetic records** without needing the `SigninLogs` table. IP addresses belong to documentation example ranges.

~~~kusto
range i from 1 to 12 step 1
| extend
    UserPrincipalName = iff(i <= 10, "linh@example.test", "minh@example.test"),
    IPAddress = iff(i % 2 == 0, "203.0.113.10", "198.51.100.22"),
    ResultType = iff(i <= 10, "50126", "0"),
    TimeGenerated = ago(3m)
| where ResultType != "0"
| summarize
    FailedAttempts = count(),
    DistinctIPs = dcount(IPAddress)
    by UserPrincipalName
| where FailedAttempts >= 10 and DistinctIPs >= 2
~~~

**Expected Output:**

| UserPrincipalName | FailedAttempts | DistinctIPs |
| --- | ---: | ---: |
| `linh@example.test` | 10 | 2 |

This is only a signal matching the query condition. You do **not yet have evidence** of the actor, source country, device, post-sign-in behavior, or resource impact.

### Part C — Analyze Like an Investigator

Answer the following questions:

1. If the same result came from 10 automated retries by an internal app, would the incident still merit high priority?
2. What should you look for in `SigninLogs` to see whether a subsequent successful sign-in occurred?
3. If an Azure role assignment change appears, which source reveals the actor and scope?
4. If `AzureActivity` has no data, can you conclude "no permission changes occurred"?
5. What conditions must be verified before running an account-lockout playbook?

**Suggested Answers:**

- You must determine whether retries are legitimate, inspect the source system, and assess risk; failure count alone is insufficient.
- Check for successful status, timestamps, principal, IP, application, device, and correlation IDs if available.
- Azure Activity and role-assignment-related logs help inspect Azure RBAC operations; Entra audit logs cover directory role changes.
- No. An empty table may be caused by connectors, permissions, time windows, or latency; it is a visibility gap to clarify.
- Verify evidence, response authority, account criticality, impact on dependent systems, approval, and recovery plan.

### Part D — Drafting an Analytics Rule on Paper

Write a descriptive configuration for a rule based on the KQL in section 6:

| Property | Example Value |
| --- | --- |
| Name | Multiple failed sign-ins from multiple IPs |
| Source | `SigninLogs` |
| Condition | At least 10 failures, at least 2 IPs within 15 minutes |
| Check frequency | Every 5 minutes; overlapping window must be managed |
| Primary entity | Account: `UserPrincipalName` |
| Initial response | Inspect raw logs, account context, and subsequent successful sign-ins |
| Initial automation | Create ticket and assign investigator |
| Evaluation criteria | Latency, false positives, missing data, duplicate alert risk |

This document is a **practice design blueprint**. Deploying a real rule requires appropriate permissions and your organization's approval process.

## 12. Common Issues and Troubleshooting

| Symptom | Possible Cause | Troubleshooting Step |
| --- | --- | --- |
| No new events visible | Connector incomplete, source not emitting logs, ingestion delay | Check connector, source, time window, and latest ingested query |
| KQL reports table not found | Wrong workspace, table has no data yet, or wrong table name | Verify table in Logs and connector schema |
| Same behavior creates multiple incidents | Rule has overlapping window or improper grouping | Review schedule, suppression, grouping, and query logic |
| Alert lacks investigation details | Missing entity mapping or useful context fields dropped | Add entity mappings, query output fields, rule description |
| Incident exists but playbook does not run | Missing permissions, wrong trigger/condition, Logic Apps or connector error | Check run history, identity, role assignments, and workflow status |
| Cannot view logs inside incident | Mismatched Sentinel and Log Analytics permissions | Check roles at each scope and actual workspace |
| Unexpected cost spike | Overly broad collection, duplicate logs, or input volume surge | Audit volume per table, connectors, and retention |
| Cannot query events from last month | Retention expiry, data tier, or historical query permissions | Verify retention, connector history, and access policies |

## 13. Self-Check Questions

**Question 1.** Is Azure Activity Log sufficient to detect every data read inside a storage account?

**Answer:** No. Activity Log primarily reflects management/control plane operations. You must evaluate resource logs and data-plane monitoring capabilities for storage.

**Question 2.** An analytics rule triggers an alert after 10 failed sign-ins. Can you automatically classify that as a compromised account?

**Answer:** No. A threshold is a signal to investigate. You must rule out legitimate retries and inspect account context and corroborating evidence.

**Question 3.** Why can a rule running every 5 minutes with a 15-minute lookback generate duplicate alerts?

**Answer:** Consecutive runs query partially overlapping sets of events. Grouping, deduplication/suppression, and latency handling must be intentionally designed.

**Question 4.** Sentinel can use playbooks to respond; why shouldn't you automatically lock every account appearing in an alert?

**Answer:** Alerts can be false positives or lack context; locking accounts can disrupt services and impact legitimate users. Permissions, approvals, and recovery plans are required.

**Question 5.** Does an empty `SigninLogs` table mean nobody signed in over the last 24 hours?

**Answer:** Not necessarily. Check tenant, connector, workspace, time range, query permissions, log tier, and ingestion status.

## Key Takeaways

- **Microsoft Sentinel** combines security signal collection, SIEM, incident investigation, and SOAR response automation.
- Choose **log sources based on security questions**; connectors, permissions, and real data must be verified before writing detection rules.
- **KQL** supports filtering, aggregation, and correlation across logs, but query results are signals requiring contextual validation.
- An **alert** is a detection signal; an **incident** is a case file for investigation, triage, and tracking remediation.
- Good investigations require **timelines, entities, evidence, blast radius, and awareness of data limits**.
- Sustainable Sentinel operations balance **detection, access control, retention, automation, and cost**.
