# Tracking Resource Changes with Activity Log

When operating Azure, knowing which resources currently exist is not enough. Operations teams also need to answer: who created, modified, or deleted a resource; when the operation occurred; whether it succeeded or failed; and which subscription the change belonged to. **Azure Activity Log** provides a history of events at the Azure management plane to help investigate changes, audit administrative activity, and detect anomalous operations.

This lesson belongs to the **Resource organization and governance** chapter of the `CLOUD_PROVIDERS_AZURE` module. In this module, you explore the Microsoft Azure ecosystem from subscriptions, resource groups, and Microsoft Entra ID to virtual networks, compute services, storage, and data; while learning how to deploy, monitor, protect, and control costs for an application architecture.

## 1. What Does Activity Log Record?

Azure Activity Log is an Azure-generated platform log that records **control-plane** (resource management layer) events. Common events include:

- Creating, updating, or deleting resources, such as virtual machines, virtual networks, storage accounts, or resource groups.
- Management configuration changes, such as updating network settings or modifying resource properties.
- Azure RBAC permission changes, such as creating or deleting role assignments.
- Operations related to Azure Policy, autoscale, and other administrative activities.
- Azure service health events, resource health status, alerts, and platform recommendations.

Activity Log is organized per **subscription**. Someone with permission to read a subscription's logs can view events within their granted scope, even when events span multiple resource groups or resource types.

### Control Plane vs. Data Plane

Distinguish Activity Log from logs of operations inside a service:

| Operation type | Example | Where information is typically found |
|---|---|---|
| Control plane | Creating a storage account, changing firewall settings, deleting a VM, granting a role assignment | Azure Activity Log |
| Data plane | Reading or writing blobs, querying data, accessing tables or queues | Resource/service logs (resource logs), if supported by the service and collection is enabled |

For example, creating a storage account is recorded in Activity Log. An application reading a specific blob occurs on the data plane and requires configuring appropriate logs for the storage service. Therefore, do not treat Activity Log as a complete record of all application activity.

Activity Log is also distinct from Microsoft Entra audit logs. Entra audit logs record changes inside the identity directory, such as creating users or modifying groups. Activity Log focuses on Azure resource management events within a subscription. When investigating a permission change, you may need to cross-reference both sources if actions involved both identities and resources.

## 2. Event Categories in Activity Log

Azure classifies events by category. Common categories include:

| Category | Content | Example scenarios to monitor |
|---|---|---|
| `Administrative` | Administrative operations on Azure resources and configurations. | Creating, updating, deleting resources; changing role assignments. |
| `Security` | Security-related events emitted by the platform. | Certain security events or security alerts from Azure services. |
| `ServiceHealth` | Azure service health events. | Service incidents, maintenance, or advisories affecting services. |
| `ResourceHealth` | Health status of a specific resource. | Resource impacted or transitioning to an unavailable state. |
| `Alert` | Events related to Azure alerts. | An alert firing or changing state. |
| `Recommendation` | Recommendations provided by Azure services. | Optimization or configuration improvement recommendations. |
| `Policy` | Azure Policy evaluation or enforcement events. | Non-compliant resource or operation denied by policy. |
| `Autoscale` | Autoscale-related events. | A rule automatically scaling instance count up or down. |

When your goal is checking who modified a configuration, start with `Administrative`. If an event involves an action denied by policy, check `Policy` as well. If an application is affected by a platform outage, inspect `ServiceHealth` and `ResourceHealth`.

## 3. Reading an Activity Log Event

Each event contains fields describing the timestamp, actor, operation, target resource, and outcome. Field names displayed in the Azure Portal may differ from field names in raw JSON or Log Analytics tables.

| Field | Meaning | Question it helps answer |
|---|---|---|
| `eventTimestamp` | Time the event occurred in UTC. | When did the change happen? |
| `submissionTimestamp` | Time the event was submitted/recorded into the logging pipeline. | When was the event ingested into Activity Log? |
| `caller` | Identity or principal that initiated the operation, such as a user, service principal, or workload identity. | Who or what component performed it? |
| `operationName` | Name of the operation executed by the resource provider. | Which management action was called? |
| `status` | Operation status, such as Started, Succeeded, or Failed. | Did the operation succeed or fail? |
| `resourceId` | Resource identifier path of the impacted Azure resource. | Which resource was changed? |
| `resourceGroupName` | Name of the associated resource group, if applicable. | Which group does the resource belong to? |
| `correlationId` | Identifier used to link related events within a single operation flow. | Which events belong to the same execution? |
| `level` | Event severity level, such as Informational, Warning, or Error. | What is the event severity? |
| `properties` | Additional properties depending on the event type and resource provider. | Are there extra details about the operation? |

Not every event includes all fields or shares the exact same `properties` structure. When investigating, open the event's details or JSON view rather than assuming every event carries identical fields.

### Distinguishing Occurrence Time and Ingestion Time

`eventTimestamp` indicates when the operation occurred; `submissionTimestamp` indicates when the event was submitted to the logging system. The two timestamps can differ. When building a timeline, use the event timestamp as the primary anchor and account for ingestion latency when correlating with application logs or external systems.

### The Caller Is Not Always a Human

The `caller` field can represent a user account, application, service principal, or service-managed identity. If you see an application name or automation identity, correlate it with deployment schedules, pipelines, or workload identity configurations. Do not conclude an individual person performed an action solely from a service principal's display name.

`correlationId` is especially useful when one action generates multiple events across different steps. Use this ID to locate related events instead of filtering only by a single resource name.

## 4. Viewing Activity Log in the Azure Portal

You can view logs at the subscription level or from a specific resource's page.

### View Subscription Logs

1. Sign in to the [Azure Portal](https://portal.azure.com/) with an account that has permission to read Activity Log.
2. Open **Monitor** and select **Activity log**. Alternatively, open **Subscriptions**, select the target subscription, and select **Activity log**.
3. Confirm the correct tenant and subscription. Cross-check the Subscription ID if multiple subscriptions have similar names.
4. Select the time range to investigate.
5. Filter by subscription, resource group, resource, category, operation, status, or caller depending on your objective.
6. Select an event to inspect the summary and JSON details.

### View Logs for a Specific Resource

1. Open the resource under investigation, such as a virtual machine or storage account.
2. In the resource menu, select **Activity log**.
3. Set the time range and review operations related to that resource.
4. Open individual events to check caller, operation, status, timestamp, and correlation ID.

### Example: Investigating a Change

Suppose a virtual network in the Production environment unexpectedly has its configuration changed. You can:

1. Open Activity Log for the Production subscription and set the time range from when the issue was noticed backward.
2. Filter by category `Administrative`, the resource group containing the virtual network, and relevant update operations.
3. Find the event with the matching operation, then inspect `caller`, `eventTimestamp`, and `status`.
4. If the caller is an automation account, correlate `correlationId` and timestamp with deployment pipelines.
5. Open other events sharing the same correlation ID to see the full sequence of operations.
6. Record the Subscription ID, resource ID, UTC timestamp, caller, operation, status, and necessary JSON evidence.

Activity Log shows that a management operation was requested and its outcome. It may not include complete before-and-after values for every property. If you need to know exactly which property changed from which value to which value, also use Change Analysis/Change history or a configuration-tracking mechanism suited to the resource type.

## 5. Querying Activity Log with Azure CLI

Azure CLI is useful when you need repeatable searches, saved outputs, or to integrate checks into operational workflows.

### List Events in a Time Range

```bash
az monitor activity-log list \
  --subscription "<SUBSCRIPTION_ID>" \
  --start-time "<START_UTC>" \
  --end-time "<END_UTC>" \
  --query "[].{Time:eventTimestamp, Caller:caller, Operation:operationName.localizedValue, Status:status.localizedValue, Resource:resourceId, Correlation:correlationId}" \
  --output table
```

Replace placeholders with the Subscription ID and UTC timestamps in ISO 8601 format, such as `2026-11-20T08:00:00Z`. Choose a time range matching the incident and verify the subscription before running the command.

### Filter by Resource Group

```bash
az monitor activity-log list \
  --subscription "<SUBSCRIPTION_ID>" \
  --resource-group "rg-app-prod" \
  --start-time "<START_UTC>" \
  --end-time "<END_UTC>" \
  --output table
```

You can also use `--caller`, `--status`, `--resource-id`, or `--correlation-id` to narrow results. When filtering by a specific operation, inspect the actual operation name in an event before using it in a query condition.

### Verify Context Before Querying

```bash
az account show --query "{Name:name, SubscriptionId:id, TenantId:tenantId}" --output table
```

Match the Subscription ID and Tenant ID against the environment under investigation. Querying Activity Log does not modify resources, but selecting the wrong subscription can cause you to miss events or draw wrong conclusions about the environment.

## 6. Querying with Azure PowerShell

If your operations team uses Azure PowerShell, `Get-AzActivityLog` retrieves events by time range and resource scope:

```powershell
$start = (Get-Date).ToUniversalTime().AddHours(-24)
$end = (Get-Date).ToUniversalTime()

Get-AzActivityLog -StartTime $start -EndTime $end -ResourceGroupName "rg-app-prod" |
    Select-Object EventTimestamp, Caller, OperationName, Status, ResourceId, CorrelationId |
    Sort-Object EventTimestamp -Descending
```

Ensure PowerShell is using the right Azure context before querying:

```powershell
Get-AzContext | Format-List Account, Tenant, Subscription, Environment
```

Azure CLI and Azure PowerShell outputs depend on each tool's active context. Confirm the subscription and tenant in whichever tool you are using.

## 7. Retaining and Analyzing Activity Log Long-Term

Activity Log can be viewed directly in Azure for the most recent **90 days**. If you need longer retention, centralized analytics, or audit compliance, configure log export to an appropriate storage destination.

### Configure Diagnostic Settings

1. In the Azure Portal, open **Monitor** and select **Activity log**; locate **Diagnostic settings** or the Activity Log export option.
2. Create a diagnostic setting at the subscription scope to be monitored.
3. Select the categories to export, such as `Administrative`, `Security`, `Policy`, `ServiceHealth`, or `ResourceHealth` as needed.
4. Choose one or more supported destinations: Log Analytics workspace, Storage account, or Event Hubs.
5. Save the configuration and verify data begins appearing at the destination.

Activity Log diagnostic settings are configured at the subscription level. Enabling diagnostic settings on an individual resource to collect resource logs does not replace subscription-level Activity Log export.

### Choosing a Destination by Requirement

| Destination | When to use | Considerations |
|---|---|---|
| **Log Analytics workspace** | Searching with KQL, building workbooks, dashboards, and query-based alerts. | Ingestion and retention costs; workspace access control required. |
| **Storage account** | Long-term log retention or archival and audit workflows. | Lifecycle policies, data protection, access permissions, and retention duration. |
| **Event Hubs** | Streaming events to external analytics systems or SIEMs. | Requires appropriate consumers, throughput management, and endpoint security. |

Select categories aligned with monitoring goals to avoid shipping unnecessary data. For audit requirements, agree on retention periods, read permissions, retrieval workflows, and log protection with security or platform governance teams.

### Analyzing Data in Log Analytics with KQL

When Activity Log is sent to a Log Analytics workspace, records typically appear in the `AzureActivity` table. Example query for succeeded or failed administrative operations in the past 24 hours:

```kusto
AzureActivity
| where TimeGenerated >= ago(24h)
| where CategoryValue == "Administrative"
| project TimeGenerated, Caller, OperationNameValue, ActivityStatusValue, ResourceGroup, ResourceId, CorrelationId
| order by TimeGenerated desc
```

To focus on failed operations, you can use:

```kusto
AzureActivity
| where TimeGenerated >= ago(7d)
| where CategoryValue == "Administrative"
| where ActivityStatusValue == "Failure"
| project TimeGenerated, Caller, OperationNameValue, ActivityStatusValue, ResourceId, CorrelationId
| order by TimeGenerated desc
```

Column names and values may vary across data sources or schema versions. If a query reports a missing column, open the **Schema** of the `AzureActivity` table in your workspace to confirm actual field names. Never infer that an empty query result means no changes occurred; verify the time range, category, subscription, and log export configuration first.

## 8. Creating Alerts for Critical Changes

Reading logs after an incident helps investigation; Activity Log alerts help teams react early when sensitive operations occur.

For example, a team can create Activity Log alerts for scenarios such as:

- A new role assignment is created in the Production subscription.
- A critical resource is deleted.
- Administrative operations fail repeatedly or are denied by Azure Policy.
- A Service Health event impacts services currently in use.

High-level Portal workflow:

1. Open **Monitor** → **Alerts** and create a new alert rule.
2. Select the subscription or required scope.
3. Choose a signal/condition under **Activity Log**.
4. Filter by category, operation, resource group, resource, status, or caller to target the exact events to detect.
5. Attach an **Action group** to send notifications or trigger response workflows.
6. Set a clear name, severity, and description explaining the alert rule's purpose.
7. Test the rule with a suitable test event or verify the conditions with the operations team.

For instance, an alert on role assignment changes might filter category `Administrative` and operation `Microsoft.Authorization/roleAssignments/write`. Confirm the actual operation name from an event in your environment before saving the condition. Avoid overly broad alerts where routine administrative actions generate excessive notification noise.

The Action group determines how notifications are delivered. Verify recipients, communication channels, and handling procedures so alerts reach the right accountable team. Never send notifications containing sensitive details to unauthorized channels.

## 9. Resource Change Investigation Workflow

When an unexpected change is discovered, follow a consistent sequence to preserve sufficient evidence:

1. **Scope:** identify the subscription, resource group, resource ID, and time window when the change occurred.
2. **Locate events:** filter by `Administrative` and relevant operations; open event details and JSON.
3. **Identify actor:** inspect `caller`, application or workload identity, and cross-check against granted permissions.
4. **Determine outcome:** read `status`, `level`, `eventTimestamp`, and `submissionTimestamp`.
5. **Correlate operation chain:** search for events with the same `correlationId` or `operationId` to understand the sequence.
6. **Cross-check legitimate activity:** review deployment schedules, pipelines, change requests, and maintenance notices.
7. **Assess impact:** check the resource's current state and related service logs.
8. **Preserve evidence:** record key fields, queries used, UTC timestamps, and data sources.
9. **Remediate and monitor:** execute organization-approved recovery or incident response workflows; monitor subsequent events to confirm results.

Never jump to concluding a change is unauthorized simply because the caller looks unfamiliar. It could be a pipeline service principal, managed identity, or platform-initiated action. Cross-check identity, correlation ID, timing, and deployment schedules before concluding.

## 10. Limitations and Best Practices

- Activity Log focuses on the control plane; enable resource logs separately for services needing data-plane visibility.
- Built-in retention is limited to 90 days. Configure log export if longer retention is required.
- Activity Log shows the operation and status, but does not always contain a full before/after configuration diff.
- Some events may arrive in logs with delay; consider both event time and submission time when correlating.
- Permissions to view Activity Log and permissions to configure diagnostic settings are separate. Grant permissions following least privilege.
- Select the right tenant and subscription before investigating or creating alerts.
- Protect workspaces, storage accounts, and Event Hubs receiving logs; logs may contain user identifiers, resource IDs, and sensitive operational metadata.
- Periodically check diagnostic settings and alert rules to detect missing configurations or inactive destinations.

For critical resources, combine Activity Log with Azure Policy, Change Analysis, resource logs, Entra audit logs, and your organization's change management system. Each source adds a distinct perspective, making audits and investigations better substantiated.

## 11. Hands-On Exercise: Investigating a Change in a Resource Group

Suppose the team receives a report that a storage account in `rg-app-prod` had its network configuration changed in the morning. You are tasked with finding the relevant event and documenting evidence.

**Assumed Inputs**

| Attribute | Value |
|---|---|
| Subscription | `Production` |
| Resource group | `rg-app-prod` |
| Resource | Application storage account |
| Priority category | `Administrative` |
| Time range | From discovery of the issue backward, in UTC |

**Steps**

1. Confirm the Tenant ID and Subscription ID of the Production environment.
2. Open Activity Log on the subscription or the storage account's page; select an appropriate time range.
3. Filter by category `Administrative` and resource group `rg-app-prod`.
4. Locate the event updating the storage account configuration; open its JSON details.
5. Record `eventTimestamp`, `caller`, `operationName`, `status`, `resourceId`, and `correlationId`.
6. Search for other events sharing the same correlation ID to determine the full operation sequence.
7. Cross-check the caller against approved pipelines or change requests.
8. If you need to identify the exact network property that changed, look up Change Analysis/Change history or a configuration source storing before-and-after state.

**Result Recording Template**

| Field | Value to fill in |
|---|---|
| Subscription ID | Verified ID |
| Resource ID | Full path of the storage account |
| Event time (UTC) | Timestamp when the event occurred |
| Caller | User or workload identity |
| Operation | Management operation name |
| Status | Operation outcome |
| Correlation ID | Identifier linking related events |
| Supporting evidence | Event JSON, pipeline run, or change record |
| Assessment | Authorized change, needs further verification, or anomalous activity |

The exercise is complete when you can identify the relevant event, explain the actor and outcome, and document evidence so others can verify it. If no event appears, re-check the subscription, UTC time range, filters, read permissions, and log export status before drawing conclusions.

## 12. Knowledge Self-Check

**1. A new storage account is created. Where should you look for the event?**

- A. Only in the application's blob access logs.
- B. In the subscription's Activity Log, under the appropriate administrative category.
- C. Only in Microsoft Entra sign-in logs.

Answer: **B**. Creating a storage account is a control-plane operation and is therefore recorded in Activity Log.

**2. Activity Log shows who called the operation and its success status, but you need to know the property values before and after the change. What should you do?**

- A. Assume all old and new values are always inside Activity Log.
- B. Use Change Analysis/Change history or a configuration-tracking source suited to the resource.
- C. Look only at the subscription name.

Answer: **B**. Activity Log is an administrative event history; property-level comparison data may require a dedicated source.

**3. Why export Activity Log to Log Analytics or a Storage account?**

- A. Because Activity Log has a default 90-day viewing window and exporting enables long-term retention or analysis.
- B. Because Activity Log only records events after a workspace is created.
- C. Because exporting logs automatically grants Owner permissions to operators.

Answer: **A**. Exporting logs enables policy-based retention and centralized analysis beyond the default window.

**4. Which field helps correlate multiple events belonging to the same operation flow?**

- A. `resourceGroupName`.
- B. `correlationId`.
- C. `level`.

Answer: **B**. `correlationId` helps find events related to the same operation or execution flow.

**5. An event has a service principal as its caller. Can you conclude a specific employee performed the action?**

Answer: No. A service principal represents an application or workload. You must cross-check the application identity, pipeline, managed identity, and correlation ID before attributing the source of the action.

Once you know how to filter, read, retain, and alert on Activity Log, you can systematically track changes at the Azure management plane, support incident investigations, and strengthen operational control across every subscription.
