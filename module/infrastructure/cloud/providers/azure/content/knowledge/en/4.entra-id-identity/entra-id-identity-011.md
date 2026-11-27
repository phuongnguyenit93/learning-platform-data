# Troubleshooting sign-in errors with sign-in logs and audit logs

A user reports that they cannot sign in to an application running on Microsoft Azure. The sign-in page may only show a generic message such as "Access denied", "Sign-in failed", or an AADSTS error code. To find the root cause, the operations team needs to know **whose sign-in request it was, to which application, from where, at what time, which policies it went through, and at which step it failed**. Microsoft Entra ID provides **sign-in logs** to answer those questions; **audit logs** help inspect identity or configuration changes that may have led to the incident.

This lesson belongs to the **Identity with Microsoft Entra ID** chapter in the `CLOUD_PROVIDERS_AZURE` module. In the Azure ecosystem, you work with tenants, subscriptions, resource groups, virtual networks, compute services, storage, and data. Properly diagnosing identity incidents helps maintain application availability, protect resources, and support operations, monitoring, and cost control for an Azure application architecture.

## 1. Distinguishing sign-in logs, audit logs, and Activity Log

Three log sources are easily confused when investigating a sign-in incident:

| Log source | Primarily records | Questions typically answered |
|---|---|---|
| **Microsoft Entra sign-in logs** | Authentication and sign-in activities of users or application identities. | Who signed in to which app? Did it succeed or fail? How were MFA and Conditional Access evaluated? |
| **Microsoft Entra audit logs** | Changes to objects or configurations in the Microsoft Entra ID directory. | Who changed a group, account, application, authentication method, or policy, and when? |
| **Azure Activity Log** | Events on the resource management plane (control plane) of an Azure subscription. | Who created, modified, or deleted a resource or changed Azure RBAC? |

For example: sign-in fails due to a Conditional Access policy → inspect the **sign-in log** to see which condition triggered. If you suspect the policy was recently modified → inspect the **audit log** to identify the update activity. If sign-in succeeds yet the user lacks permission to create a virtual machine → inspect **Azure RBAC** and the subscription's **Azure Activity Log**; that may be a resource authorization error rather than an authentication error.

**Not every sign-in creates an audit event.** Sign-in logs record sign-in attempts; audit logs record changes in the directory. Both sources can be related, yet they serve different purposes.

### Sign-in types to distinguish

| Sign-in type | Principal and scenario | When to inspect |
|---|---|---|
| **Interactive user sign-ins** | User participates in the sign-in flow, e.g., entering credentials and completing MFA. | User cannot open the Portal or an application. |
| **Non-interactive user sign-ins** | App uses an existing session, token, or refresh mechanism without direct user interaction. | App repeatedly prompts for sign-in or token refresh fails. |
| **Service principal sign-ins** | App or automated task signs in using an application identity. | Pipeline, daemon, or service-to-service authentication fails. |
| **Managed identity sign-ins** | Azure workload uses a managed identity to request tokens for another service. | An App Service, VM, or Function cannot access a resource via managed identity. |

Do not look only at interactive sign-ins if the application relies on token refresh sessions, service principals, or managed identities. The authentication flow type determines which log category to open.

## 2. Prerequisites and information to gather

To access logs, your account must hold appropriate read permissions in **the right Microsoft Entra tenant**. Roles such as **Reports Reader**, **Security Reader**, or administrative roles with corresponding permissions can view permitted log sections. Certain sensitive fields, risk evaluations, or Conditional Access details may require additional roles or feature tiers. Permission to view logs in Entra ID and permission to query a Log Analytics workspace are two separate authorization mechanisms.

Before starting, collect at minimum:

- **Tenant:** name and Tenant ID of the organization or environment where the issue occurred.
- **User or workload:** UPN/email, object ID, application/service principal ID if available.
- **Target application/resource:** application name or App ID/Resource ID.
- **Timestamp:** time of the error and the user's time zone; convert to UTC when correlating.
- **Traces:** error message, `AADSTS` code, **Correlation ID**, **Request ID**, and screenshots with sensitive data redacted if needed.
- **Context:** interactive or automated sign-in, device/browser, corporate or external network, VPN usage, MFA status.

Use an **exact timestamp** instead of "this morning." For instance, if a user in Vietnam (UTC+7) reports an error at 15:30 on 2026-11-20, the corresponding time is 08:30 UTC on the same day. Log data can experience ingestion latency; when searching, widen the time range around the reported timestamp.

Never ask users to provide passwords, OTP codes, access tokens, or client secrets for troubleshooting. Those details are never needed to read sign-in logs.

## 3. Key fields in a sign-in log

In the Azure Portal, fields may appear under different tabs or label names depending on sign-in type and UI version. The table below lists commonly used information:

| Field/section | Meaning | How to use |
|---|---|---|
| **Date/Time** | Timestamp of the sign-in event. | Compare against incident time and related logs. |
| **User / Identity** | User, service principal, or managed identity. | Identify the exact principal. |
| **Application** | Client application requesting sign-in. | Distinguish the Portal, internal apps, and SaaS apps. |
| **Resource** | API or resource for which the token is requested. | Locate the right target service among multiple components. |
| **Status** | Success, Failure, or interrupted/next-step-required status depending on UI and flow. | Isolate the failing attempt. |
| **Error code / Failure reason** | Error code and reason description identified by the service. | Form an initial diagnostic hypothesis. |
| **Correlation ID / Request ID** | Trace identifiers for the request or sign-in flow. | Correlate with error screens, app logs, and technical support. |
| **IP address / Location** | Network address and network-inferred location. | Verify network conditions or Conditional Access rules. |
| **Device info** | Operating system, browser, device state when data is available. | Determine impact of device policies. |
| **Authentication Details** | Authentication steps/methods and MFA outcome if recorded. | Check whether MFA requirements were met. |
| **Conditional Access** | Evaluation result of applicable policies. | Identify which policy blocked or required additional controls. |

**Correlation ID and Request ID do not substitute for each other.** Both are valuable when engaging app teams or Microsoft support; record the exact values shown on the sign-in error. When joining different log sources, verify which ID actually appears in each source rather than assuming every audit event shares the same correlation ID as a sign-in.

IP-based geographic location is inferred metadata; VPNs, proxies, mobile networks, or NAT can make the location differ from physical reality. Never rely on the Location field alone to conclude anomalous user behavior.

## 4. Reading sign-in logs in the Microsoft Entra admin center

### Step 1: Open the right tenant

1. Open the [Microsoft Entra admin center](https://entra.microsoft.com/).
2. Confirm the active account and **directory/tenant**.
3. Under **Microsoft Entra ID** → **Monitoring & health** → **Sign-in logs**, open the log list. Menu names and groupings may vary by UI version.
4. Select the right log category: interactive user, non-interactive user, service principal, or managed identity depending on the authentication flow under investigation.

If the user belongs to a partner tenant as a guest, identify both the application's tenant and the tenant where the sign-in request is processed. Do not assume signing in to the home tenant is sufficient to see all logs in the resource tenant.

### Step 2: Filter for the right events

1. Set a time range covering the error timestamp, accounting for time-zone conversion and log ingestion delay.
2. Filter by **User**, **Application**, **Status**, or other available fields.
3. If you have a Request ID or Correlation ID, use filters or details to find the matching record.
4. When a user retries multiple times, compare earlier and later records rather than opening only the most recent entry.

### Step 3: Analyze the record

Open the relevant record and inspect:

- **Basic info / Status:** application, resource, timestamp, error code, and failure reason.
- **Authentication Details:** which authentication steps succeeded, which failed, and whether MFA was prompted.
- **Conditional Access:** which policies were applied, with Success/Failure/Not applied or report-only results per displayed data.
- **Device info:** whether the device was recognized or met required conditions.
- **Location / Network:** source IP, network location, and related network conditions.

Do not interpret **sign-in success** as guaranteeing the user successfully used the application. Successful authentication can still be blocked at the application authorization, Azure RBAC, data, or network layer. Conversely, an interrupted sign-in status waiting for MFA is not necessarily a system failure.

### Step 4: Record the evidence

Use a consistent template so others can continue the investigation:

| Field | Fictional example |
|---|---|
| Tenant | `contoso.onmicrosoft.com` |
| User | `user@contoso.example` |
| Application | `Sales Portal` |
| Event time (UTC) | `2026-11-20T08:30:00Z` |
| Status | `Failure` |
| Error code | `53003` |
| Correlation ID | `<CORRELATION_ID>` |
| Device / IP | Observed data, sharing restricted |
| Conditional Access | Policy name and displayed outcome |
| Initial assessment | Inspect policy condition blocking access |

The values above are illustrative only. Real records may contain additional fields or blank entries.

## 5. Diagnosing common root-cause categories

AADSTS codes help narrow down causes, yet **an error code is not the entire conclusion**. Always read the failure reason, authentication details, Conditional Access tab, and actual configuration.

| Common symptom/code | Initial hypothesis | What to check |
|---|---|---|
| `AADSTS50034` | Account does not exist in the specified directory. | Check UPN, Tenant ID, guest account, home realm, and app config. |
| `AADSTS50020` | Sign-in identity is missing from the tenant required by the app, or wrong organizational context. | Check app's tenant, invitation/guest account, account selection. |
| `AADSTS50076` | MFA required due to policy or authentication conditions. | Check Authentication Details, method registration, and Conditional Access. |
| `AADSTS53003` | Access blocked by Conditional Access. | Open Conditional Access tab, find the failed policy and relevant condition. |
| `AADSTS50105` | User is not assigned to an app requiring assignment. | Check enterprise application, user/group assignments. |
| `AADSTS50011` | Reply/redirect URI does not match app configuration. | Compare request redirect URI against App registration. |
| `AADSTS700016` | App with submitted App ID not found in the active directory. | Check client ID, tenant, registration, and app consent. |
| `AADSTS7000215` | Invalid client secret. | Check app credential config and safe secret rotation workflow. |

Error messages may vary by authentication flow, protocol version, and configuration. To confirm root cause, prioritize **the details of the sign-in event itself** and the current configuration in the relevant tenant.

### Category A: Wrong tenant or account

Symptoms: user can sign in to app A yet fails on app B; error mentions user does not exist in directory; or app belongs to a partner organization.

Resolution steps:

1. Verify the required Tenant ID and the account chosen on the sign-in screen.
2. Check whether the user was invited or created in the right tenant.
3. If it is a B2B guest, check invitation redemption status and access to the resource tenant.
4. Cross-check the app registration/enterprise application against the expected tenant; never alter multi-tenant settings before understanding the access model.

### Category B: MFA or Conditional Access

Symptoms: user is prompted for additional verification, receives `AADSTS53003`, or fails only on a specific device or network.

Resolution steps:

1. Open the exact sign-in event and inspect **Authentication Details**.
2. Open **Conditional Access** to find policies that applied, failed, or evaluated in **report-only** mode.
3. Inspect relevant conditions: application, identity, groups, network locations, device state, and required authentication strength.
4. Correlate with policy change timestamps in the audit log.
5. If you have permissions and the feature is available, use **Conditional Access What If** to simulate conditions; simulation results assist evaluation only and do not replace real sign-in events.

Never disable MFA or turn off all Conditional Access policies just to "see if the error goes away." When adjustments are needed, identify the exact condition and blast radius and follow the organization's change process.

### Category C: Missing application assignment

Symptoms: authentication appears to succeed, yet the user cannot enter the app or receives assignment/consent errors.

Check **Enterprise applications** → the relevant app → **Users and groups** or appropriate assignment settings. Confirm whether the user/group is assigned, which app role is required, and whether group sync has completed. If the user can open the app yet cannot use a specific feature, inspect **authorization inside the application itself**.

### Category D: OAuth/OIDC or workload configuration errors

Symptoms: fails only during sign-in redirects, pipeline fails, or background process fails to acquire tokens.

Verify App ID, Tenant ID, redirect URI, authentication flow type, and app registration configuration. For service principals, check credential or certificate expiration without copying secrets into support tickets. For managed identities, verify the attached identity and permissions on the target resource; inspect **managed identity sign-in logs**. If the issue is Azure RBAC permissions after acquiring a token, check role assignments on the target resource.

## 6. Using audit logs to find changes leading to an incident

Sign-in logs typically show **how the failure occurred at authentication time**. Audit logs answer the next question: **what changed beforehand?**

For example, an account signed in normally yesterday, yet today it is prompted for MFA or blocked. Audit logs can reveal whether around that time changes occurred in:

- **Conditional Access policy:** creating, updating, deleting, or changing policy state.
- **Users and group memberships:** creating or disabling accounts, adding/removing group members, or modifying relevant attributes.
- **Authentication methods:** registering, removing, or changing authentication method details.
- **Application configuration:** enterprise application settings, app registrations, permissions, credentials, or assignments.
- **Directory role assignments:** changes to administrative roles in Microsoft Entra ID.

### Viewing audit logs in the Portal

1. Go to the [Microsoft Entra admin center](https://entra.microsoft.com/) and confirm the tenant.
2. Open **Microsoft Entra ID** → **Monitoring & health** → **Audit logs**.
3. Set the time range **before and during the error window**; a configuration change may precede an incident by hours or days.
4. Filter by **Activity**, **Category**, **Status**, **Target**, or **Initiated by** where available.
5. Open the audit event to inspect target resources, actor, operation, status, and recorded modified properties.

Key fields:

| Field | Purpose |
|---|---|
| **Activity / Operation** | Identifies what change action occurred. |
| **Date** | Identifies when the change occurred. |
| **Initiated by** | Identifies the user or application that performed it. |
| **Target(s)** | Object modified: user, group, application, policy, etc. |
| **Result** | Indicates whether the action succeeded, failed, or another outcome. |
| **Modified properties** | Details of changed attributes when provided by the log source. |
| **Correlation ID** | Helps link events within a configuration change activity. |

An audit event proves a change occurred, yet does not by itself prove that change **caused** the sign-in failure. To establish causality, verify that the corresponding policy or setting actually applied during the failing sign-in event.

### Reading both sources together

```text
Sign-in log: user blocked at 08:30 UTC
            │
            ├── Error: 53003
            ├── Conditional Access: policy "Require compliant device"
            └── Device: does not satisfy condition
                            │
                            ▼
Audit log: related policy modified at 07:55 UTC
            │
            ├── Initiated by: administrator / automation
            └── Changed properties: device condition / group
                            │
                            ▼
Verify current configuration, scope, and change approval
                            │
                            ▼
Conclude with evidence, remediate, and verify with a fresh sign-in
```

The diagram illustrates an investigation sequence, not output from a real tenant.

## 7. Exporting logs to Log Analytics for KQL queries

If an organization needs long-term analysis, cross-sign-in correlation, or dashboards, administrators can configure **Diagnostic settings** in Microsoft Entra to send sign-in logs and audit logs to a **Log Analytics workspace**, Storage account, or Event Hubs (depending on log type, licensing, and supported configuration).

Default log retention in Entra can depend on license tier, log type, and current policy. **Never assume logs persist indefinitely.** Verify available retention and export configurations before investigating older incidents. Log export must be enabled proactively; events that have already aged out of the source cannot be recovered retroactively.

Common tables in Log Analytics:

| Data type | Common KQL table |
|---|---|
| Interactive user sign-ins | `SigninLogs` |
| Non-interactive user sign-ins | `AADNonInteractiveUserSignInLogs` |
| Service principal sign-ins | `AADServicePrincipalSignInLogs` |
| Managed identity sign-ins | `AADManagedIdentitySignInLogs` |
| Microsoft Entra ID audit logs | `AuditLogs` |

Table names and column sets depend on exported data types and workspace schema. An absent table or empty query result in a workspace does not necessarily mean no events occurred; diagnostic settings may be disabled, pointed to the wrong tenant, or logs may not have ingested yet.

### Query 1: Failed interactive sign-ins

```kusto
SigninLogs
| where TimeGenerated >= ago(24h)
| where ResultType != "0"
| project TimeGenerated, UserPrincipalName, AppDisplayName,
          IPAddress, ResultType, ResultDescription, CorrelationId
| order by TimeGenerated desc
```

A `ResultType` of `"0"` typically represents successful authentication; other values may be error codes. This query inspects only interactive sign-ins; switch tables when investigating non-interactive or workload identities.

### Query 2: Investigating one user and one application

```kusto
SigninLogs
| where TimeGenerated between (ago(7d) .. now())
| where UserPrincipalName =~ "user@contoso.example"
| where AppDisplayName has "Sales Portal"
| project TimeGenerated, AppDisplayName, ResultType,
          ResultDescription, ConditionalAccessStatus,
          IPAddress, CorrelationId
| order by TimeGenerated desc
```

Replace UPN and application name with actual values. This query helps compare successes and failures around the time of a policy change.

### Query 3: Directory changes related to apps or policies

```kusto
AuditLogs
| where TimeGenerated >= ago(7d)
| where Category in ("Policy", "ApplicationManagement", "UserManagement")
| extend Actor = coalesce(
    tostring(InitiatedBy.user.userPrincipalName),
    tostring(InitiatedBy.app.displayName))
| project TimeGenerated, Category, ActivityDisplayName,
          Result, Actor, TargetResources, CorrelationId
| order by TimeGenerated desc
```

Categories may vary depending on actual operations. To locate a specific event, first check which categories and activities appear in your workspace, then narrow the filters. `TargetResources` is a complex field; when extracting object names, expand elements with `mv-expand` or index appropriately after checking schema.

### Query 4: Finding audit events by action keyword

```kusto
AuditLogs
| where TimeGenerated >= ago(7d)
| where ActivityDisplayName contains "Conditional Access"
| project TimeGenerated, ActivityDisplayName, Result,
          InitiatedBy, TargetResources, CorrelationId
| order by TimeGenerated desc
```

If a query returns no records, check keywords, table selection, permissions, time window, and export settings. KQL queries only read data that reached the workspace and do not replace opening the source record in the Entra Portal when analyzing Authentication Details.

## 8. Step-by-step troubleshooting workflow

When receiving a "I cannot sign in" ticket, follow this investigation sequence:

1. **Confirm the right tenant and application.** Record Tenant ID, App ID if available, user or workload, and UTC timestamp.
2. **Classify the authentication flow.** Interactive, non-interactive, service principal, or managed identity?
3. **Locate matching sign-in events.** Filter by UPN/identity, app, time window, Request ID, or Correlation ID.
4. **Read status and error.** Record error code, failure reason, resource, and network/device context.
5. **Inspect authentication steps.** Do Authentication Details show MFA, a method, or an additional requirement was not met?
6. **Inspect Conditional Access.** Identify which policy actually applied and the blocking reason if any.
7. **Look for changes prior to the incident.** In audit logs, check changes related to users, groups, applications, authentication methods, or policies.
8. **Distinguish authentication from authorization.** If a token was issued yet the app still returns 403, check app roles, API permissions, Azure RBAC, or app-internal permissions.
9. **Act within authority.** Apply the exact configuration fix, assign permissions through the approval workflow, or escalate to the tenant/policy owner.
10. **Re-verify.** Request a fresh sign-in test, confirm the new event, and record before/after outcomes.

Also document **checks that found no evidence**, such as "no Conditional Access audit changes in the past 48 hours" after confirming retention and filters. This prevents duplicate work and clarifies the boundaries of your conclusion.

## 9. Real-world scenarios

### Scenario A: User blocked after a Conditional Access change

**Symptom:** User signed in yesterday, yet today the app reports `AADSTS53003`.

**Investigation:** The sign-in event shows Failure and a Conditional Access policy requiring a compliant device. The audit log shows the policy was recently updated, adding the user's group to its scope.

**Evidence-based conclusion:** The policy change likely caused the error if the device condition in the sign-in event matches the newly added requirement. Administrators must verify policy intent and device compliance status, then adjust scope or remediate the device per procedure. Afterward, verify with a fresh sign-in event.

### Scenario B: B2B user cannot access an application

**Symptom:** A partner has a corporate account yet receives an error related to tenant or account.

**Investigation:** The sign-in log indicates the resource tenant differs from the home tenant or the account does not exist in the target tenant. The audit log shows the guest invitation was never redeemed or the guest account was deleted.

**Resolution path:** Check the B2B invitation workflow, guest status, enterprise application assignment, and account selection during sign-in. Never grant overly broad permissions simply to bypass an access error.

### Scenario C: Pipeline stops acquiring tokens

**Symptom:** A background app encounters `AADSTS7000215` after a credential change.

**Investigation:** Open service principal sign-in logs and match app ID and timestamp. Audit logs may show an operation modifying the application's credential.

**Resolution path:** Identify which credential the pipeline uses, check secret-store configuration and rotation workflows. Prefer managed identity or workload identity federation where appropriate to reduce secret-management risk. Never place client secrets into incident records.

### Scenario D: Sign-in succeeds, yet API denies access

**Symptom:** Sign-in log reports Success, yet the API returns HTTP 403.

**Investigation:** Entra authentication succeeded, so continue checking claims/roles, application permissions, consent, resource role assignments, or API authorization logic. Audit logs help if user assignments or app permissions changed; Azure Activity Log helps if Azure RBAC recently changed.

**Conclusion:** This is likely a post-sign-in **authorization** error, not an authentication error. Do not modify MFA or Conditional Access without evidence that those controls caused the 403.

## 10. Alerting, retention, and data protection

For critical systems, operations teams can build scheduled queries, workbooks, or log alerts over Log Analytics data to detect trends such as anomalous error spikes, persistent failures on a single application, or sensitive configuration changes.

When implementing, keep in mind:

- **Least privilege:** only authorized personnel should view sign-in details, IPs, identities, and audit events.
- **Personal data protection:** redact UPNs, IPs, or user details when sharing screenshots and reports outside authorized groups.
- **Retention periods:** check Entra licensing and policies; configure appropriate retention on workspaces or storage destinations.
- **Data latency:** sign-in logs and logs exported to workspaces may not appear instantaneously.
- **Schema differences:** different sign-in types have distinct schemas, visibility rules, and granularity.
- **Alert quality:** distinguish user typos and normal MFA prompts from actionable incidents; avoid noisy alerts.
- **Inference limits:** never conclude account compromise from an IP location, a single failure, or an isolated audit event alone.

## 11. Hands-on exercise: diagnosing a failed sign-in

Suppose user `user@contoso.example` reports an error accessing `Sales Portal` at 15:30 Vietnam time. You are an operator with read permissions on sign-in logs and audit logs in the organization's tenant.

**Requirements:**

1. Confirm the right tenant; convert the error timestamp to **08:30 UTC**.
2. In interactive sign-in logs, filter by user, application, and a time window around 08:30 UTC.
3. Locate the failed attempt; record Error code, Failure reason, Correlation ID, IP, and device info.
4. Open Authentication Details and Conditional Access to determine whether an MFA step or policy took effect.
5. In audit logs, check changes related to the user, group, app, and policy prior to the error timestamp.
6. Separate hypotheses supported by evidence from unconfirmed hypotheses.
7. Propose a remediation step matching the actual cause and describe how to verify with a new sign-in event.

**Report template:**

| Item | To fill in |
|---|---|
| Tenant ID / application | Verified ID and application name |
| User or workload identity | Appropriate identifier |
| Event time (UTC) | Error timestamp from logs |
| Sign-in type | Interactive, non-interactive, service principal, or managed identity |
| Status / Error code | Outcome and error code |
| Authentication / Conditional Access | Related step or policy |
| Audit evidence | Change event, timestamp, and actor if present |
| Root cause | Verified cause or items needing further investigation |
| Action | Approved adjustment or escalation |
| Verification result | Fresh sign-in event and post-action status |

A complete exercise must present **sign-in log evidence** for the symptom, **audit log evidence** if a related change exists, and clearly explain why the remediation path was chosen. If no related audit event exists, you can still finish the investigation with a bounded conclusion rather than inventing an unobserved change.

## 12. Knowledge self-check

**Question 1.** A user encounters `AADSTS53003`. Which source should you inspect first to understand the blocking condition?

A. Azure Activity Log of a storage account  
B. The sign-in event and its Conditional Access tab  
C. Only the audit log of a resource group

**Answer: B.** The sign-in event shows the policies and evaluation results for that specific sign-in attempt.

**Question 2.** A user reports an error right after being removed from an application group. Which source verifies the group change?

A. Microsoft Entra audit logs  
B. Blob access logs only  
C. App Service CPU metrics only

**Answer: A.** Audit logs can record membership modifications and the actor who performed them.

**Question 3.** A pipeline using a service principal fails to acquire a token, yet you only inspected interactive user sign-ins. What did you miss?

**Answer:** You need to open **service principal sign-ins** and check the application's App ID, credentials, tenant, permissions, and authentication flow.

**Question 4.** The sign-in log reports Success, yet the application returns 403. Does this mean MFA failed?

**Answer:** No. The token may have been issued successfully; inspect API authorization, app roles, consent, Azure RBAC, or internal application permissions.

**Question 5.** The audit log shows a policy change right before a sign-in failure. Can you immediately conclude the policy caused the failure?

**Answer:** Not yet. You must verify which policy actually applied to the sign-in event, which conditions failed, and when the change took effect.

**Question 6.** Why must you check sign-in type and retention before concluding "no logs exist"?

**Answer:** Events may reside in non-interactive, service principal, or managed identity logs; data may be delayed, past retention, or not yet exported to the workspace.

The most important skill when troubleshooting sign-in errors is **linking the authentication attempt to relevant configuration changes and drawing evidence-based conclusions**. Sign-in logs show what happened during the sign-in flow; audit logs show what changed in the tenant. Combining them with application details, Conditional Access, and resource permissions enables accurate incident resolution.
