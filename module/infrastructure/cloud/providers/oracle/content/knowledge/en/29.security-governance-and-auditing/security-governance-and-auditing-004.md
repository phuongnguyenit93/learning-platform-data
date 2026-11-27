# OCI Audit and tracing administrative operations

## 1. Objectives and context

In the **Security, Governance, and Auditing** chapter of the **CLOUD_PROVIDERS_ORACLE** module, this lesson focuses on using OCI Audit to explain an Oracle Cloud Infrastructure change: which identity sent the request, which operation was called, which resource was affected, at what time, and how the API responded.

After this lesson, learners will be able to:

- Distinguish administrative operation evidence from data access evidence or in-host activity.
- Read key fields of an Audit event and correlate related events.
- Scope queries by tenancy, compartment, region, time, and OCID.
- Query via Console, OCI CLI, and Logging Search with appropriate permissions.
- Build an investigation timeline, preserve evidence, and design log forwarding for monitoring.

The overarching scenario is a VCN Security List that was modified, introducing a rule allowing SSH from the Internet. The investigation has two separate parts: identifying the operation that altered the configuration and verifying whether any actual connection exploited that configuration.

## 2. What does OCI Audit record?

OCI Audit automatically records calls to supported public API endpoints. Calls can originate from the Console, CLI, SDK, custom programs, or other OCI services. Thus, someone editing a resource through a browser and a pipeline editing a resource via an SDK both leave API evidence. Audit does not require installing an agent inside virtual machines to record these calls. [OCI Audit Overview](https://docs.oracle.com/en-us/iaas/Content/Audit/Concepts/auditoverview.htm).

The first thing to determine before searching is **which management layer the question is about**.

| Investigation question | Evidence to prioritize |
| --- | --- |
| Who called the API to edit the VCN Security List? | OCI Audit for network management operations |
| Who called the API to change a Compute instance configuration? | OCI Audit for Compute APIs |
| Were there any SSH connections to the VM after the change? | Flow logs, OS logs, or appropriate access logs |
| Who read a specific object in a bucket? | Properly configured Object Storage access logs |
| Who ran an SQL statement in Oracle Database? | Database-level auditing mechanism |
| Why did a business request fail? | Application logs, traces, and related infrastructure logs |

According to Oracle's documented scope, Object Storage Audit records bucket-related events and does not cover operations on individual objects. Do not assume that uploading, reading, or deleting an object appears in OCI Audit. [Audit Scope](https://docs.oracle.com/en-us/iaas/Content/Audit/Concepts/auditoverview.htm).

The table above guides evidence source selection for an investigation. Supplemental sources still must be enabled, authorized, and retained according to each environment's configuration.

A recorded API call also does not mean every change inside a resource is fully described. For example, an API call to reboot a VM and a file-editing command run by a user inside the OS are two activities at two different layers.

## 3. Traceability model: from identity to impact

You can visualize the path of an operation as follows:

~~~mermaid
flowchart LR
    A["User or workload"] --> B["Console / CLI / SDK"]
    B --> C["IAM authentication and authorization"]
    C --> D["OCI service API"]
    D --> E["Target resource"]
    D --> F["OCI Audit"]
    F --> G["Query and build timeline"]
    G --> H["Cross-check network, host, and app logs"]
~~~

This diagram shows the components to cross-check during an investigation; it does not depict the internal logging order of every service.

### 3.1. Technical identity and accountable owner

Audit helps identify the principal appearing in a request. A principal can be a user, a VM using instance principal, a workload using resource principal, or another technical identity.

If the principal belongs to a deployment pipeline, additionally locate the pipeline run, source code version, and approver. If the principal is a shared API user, the record only identifies that account; attributing responsibility to an individual requires additional evidence.

IP addresses and user agents add context but do not prove on their own who is sitting at the keyboard. Multiple people may share the same NAT, VPN, or proxy; a tool can also modify its user agent.

### 3.2. Request, response, and final state

When reading an event, separate three questions:

1. Which request was sent?
2. How did the API respond?
3. What state did the resource end up in?

A `202` response usually indicates the request was accepted for processing. For asynchronous operations, cross-check the work request or resource state before confirming the final outcome. Even a successful response from a configuration update API does not prove the business service worked properly after the change.

Conversely, an error response only describes the outcome of that specific request. Do not use a single denied request to conclude that the entire session contained no other successful changes.

## 4. Reading an Audit event

### 4.1. Fields to extract first

In standard Audit JSON format, the following fields help build an initial investigation key set:

| Field | Purpose |
| --- | --- |
| `eventId`, `eventTime` | Event identification and timestamp |
| `data.eventName` | API operation name |
| `data.compartmentId`, `data.resourceId` | Scope and target resource |
| `data.identity.principalId` | Executing principal |
| `data.identity.ipAddress` | Source IP |
| `data.request.id`, `data.request.action` | Request ID and HTTP method |
| `data.response.status` | Response status code |
| `data.eventGroupingId` | Correlate events from the same operation |
| `data.stateChange.previous/current` | Before and after states if present |

`eventGroupingId` can link multiple events of a long-running API operation. Fields may be empty or vary by service and schema version; `stateChange` is not a guaranteed complete configuration snapshot for every operation. [Audit Log Event Structure](https://docs.oracle.com/en-us/iaas/Content/Audit/Reference/logeventreference.htm).

### 4.2. Abbreviated example

The following JSON is **mock data for illustration**, with many attributes omitted. Values in `<...>` are placeholders. Do not use this sample as a schema contract for log processing programs.

~~~json
{
  "eventId": "8f46c630-5d95-4ea1-bca1-64cb08e8a621",
  "eventTime": "2026-11-20T02:10:00Z",
  "data": {
    "eventName": "UpdateSecurityList",
    "compartmentId": "<COMPARTMENT_OCID>",
    "resourceId": "<SECURITY_LIST_OCID>",
    "eventGroupingId": null,
    "identity": {
      "principalId": "<PRINCIPAL_OCID>",
      "principalName": "network-deployer",
      "ipAddress": "198.51.100.27",
      "userAgent": "example-deployment-client"
    },
    "request": {
      "id": "example-request-001",
      "action": "PUT"
    },
    "response": {
      "status": "200"
    },
    "stateChange": {
      "previous": null,
      "current": null
    }
  }
}
~~~

The appropriate interpretation is: at the timestamp recorded in `eventTime`, the principal with the stated OCID sent an `UpdateSecurityList` operation to the target Security List and the API returned `200`.

You cannot yet conclude from this sample that:

- The person behind the principal is definitely the legitimate account owner.
- The update content was specifically an SSH rule from `0.0.0.0/0`.
- SSH traffic actually traversed it.
- No other related operations occurred before or after the event.

In this example, `stateChange` provides no change details. To determine which rule was modified, cross-check the prior configuration, deployment payload, full record if available, and resource state.

The address `198.51.100.27` is an illustrative address; it does not represent a real access source.

### 4.3. Do not conflate three identifier types

- **Event ID** identifies a single event during collection and correlation.
- **Request ID** helps link a record to an API request, caller tool logs, or support tickets.
- **Resource OCID** helps track a resource across multiple operations and timestamps.

Do not use display names as unique keys: names can collide or be renamed. Also do not assume one business action generates exactly one event. A single Terraform run or Console action can emit multiple read, update, and status-check API calls.

When passing logs to another tool, inspect the actual JSON before writing filters. Field names and wrapper structures from CLI or Logging Search outputs may differ from the raw event layout. Avoid writing parsers by copying UI column headers.

## 5. Scoping Audit read permissions

The investigation team should have Audit read permissions within their assigned scope. The example below assumes identity domain `Default`, group `AuditReaders`, and compartment `AuditLab` already exist:

~~~text
Allow group 'Default'/'AuditReaders' to read audit-events in compartment AuditLab
~~~

Replace the domain, group, and compartment with actual names. Administrators must place policies at a location matching the grant scope and the tenancy's IAM model.

The authorization resource for Audit is `audit-events`. The `read` permission grants `AUDIT_EVENT_READ` for the `ListEvents` operation; `inspect` does not grant this permission. Using `manage` instead of `read` on `audit-events` itself does not add administrative APIs or log deletion APIs. [Audit Policy Reference](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/auditpolicyreference.htm).

If the UI needs to let investigators browse the compartment tree, administrators can additionally grant compartment discovery permissions as needed, for example:

~~~text
Allow group 'Default'/'AuditReaders' to inspect compartments in tenancy
~~~

This is a scope discovery permission, separate from Audit read permissions. Do not grant Administrator permissions merely to troubleshoot missing log visibility.

With Logging Search, querying only `"<COMPARTMENT_OCID>/_Audit"` requires the corresponding Audit permissions. When also searching service logs or custom logs, check permissions for the log group and log content; Audit read permission does not automatically grant read access to every log in the tenancy. [Permissions Required to Search Logs](https://docs.oracle.com/en-us/iaas/Content/Logging/Concepts/searchinglogs.htm).

In operations, separate the roles of infrastructure modifier and evidence reviewer. One person may be granted both roles during practice labs, but reports must clearly record which identity was used for each action.

## 6. Scoping an investigation before writing filters

A query returning no results is meaningful only within the scope actually searched. Before each lookup, record:

| Search dimension | Information to determine |
| --- | --- |
| Tenancy | Are you using the right tenancy and profile? |
| Region | Where is the relevant API/resource or identity domain? |
| Compartment | Which compartment did the resource belong to at operation time? |
| Time | Time zone, start/end range, observation latency |
| Identity | Principal OCID, expected tool or pipeline |
| Resource | OCID of the affected object |
| Permissions | Which scopes is the searcher permitted to read? |

### 6.1. Region and compartment are two separate dimensions

Do not assume selecting the root compartment searches the entire tenancy or searches every region. Confirm child compartment scope and selected regions in the tool you are using. When calling `ListEvents` via CLI, treat each compartment/region pair as an explicit query scope.

For IAM, check the compartment containing the identity domain and the region associated with the domain or operation under investigation. Do not mechanically apply a Compute instance's region to all IAM events. Oracle's IAM reporting guide also requires selecting the right compartment containing the domain and checking regions when data is missing. [Querying IAM Events from OCI Audit](https://docs.oracle.com/en/learn/generating-iam-reports-from-oci-audit/).

If a resource moved compartments, check both the old and new scopes along the change timeline. Current name and location are insufficient to infer the location of every historical record.

### 6.2. Normalizing timestamps

In investigation reports, store timestamps in UTC standard time and add local time when coordinating with operations teams.

Example:

~~~text
Local time: 2026-11-20 09:10:00 +07:00
UTC time:   2026-11-20 02:10:00 Z
~~~

Someone reporting "incident at 9:10" might mean when the alert arrived, not when the API changed the configuration. Expand the search window before and after the reported timestamp, then narrow down once an anchor event is found.

Audit has processing latency; Oracle's search documentation states events near the current time may take around 15 minutes to appear. Therefore, after a lab operation, wait and re-query the same scope before concluding logs are missing. [Searching Audit Log Events](https://docs.oracle.com/en-us/iaas/Content/Audit/Tasks/searching-log-events.htm).

This latency should not be treated as an incident detection SLA for a monitoring system. Measure the actual latency of the entire collection, processing, and notification pipeline.

## 7. Querying in the Console and Logging Search

### 7.1. UI workflow

You can open Audit from **Observability & Management → Logging → Audit**. The Audit interface integrated with Logging lets you explore events and export JSON data; Audit can also be searched via the special `_Audit` log group in Logging Search. [Audit Interface in Logging](https://docs.oracle.com/en-us/iaas/Content/Logging/Concepts/audit_logs.htm).

Follow this sequence:

1. Confirm the currently selected tenancy and region.
2. Select the relevant compartment, then set the time window.
3. Start with a known resource or timestamp.
4. Open an event and inspect the detailed JSON.
5. Record the principal OCID, resource OCID, request ID, operation, and response status.
6. Search further for preceding and subsequent events by resource or principal.
7. Export the necessary data along with a description of the query scope.

When tracing Security List changes, do not filter only for `PUT` from the outset. Configuration read requests, resource queries, or operations belonging to a deployment sequence can explain the context of the update.

If the screen displays only partial results, check pagination and filters before constructing a timeline. Screenshots aid quick communication, whereas JSON exports and query scope allow others to re-verify details.

### 7.2. Querying by resource

The sample below uses the OCI Logging Search query language. Replace placeholders with real OCIDs, then select time and region in the UI:

~~~text
search "<COMPARTMENT_OCID>/_Audit"
| where data.resourceId = '<SECURITY_LIST_OCID>'
| sort by datetime asc
~~~

This query answers: **within the selected scope, which events occurred for that resource in chronological order?**

If you do not yet know exactly where the OCID appears in a service's events, search more broadly and inspect actual records. Resource creation, deletion, or operations on parent resources may require different matching logic.

### 7.3. Querying by principal and operation

Once you have the principal to examine, you can narrow down:

~~~text
search "<COMPARTMENT_OCID>/_Audit"
| where data.identity.principalId = '<PRINCIPAL_OCID>'
  and data.eventName = 'UpdateSecurityList'
| sort by datetime asc
~~~

These two query templates are practice examples for fields observed in JSON; they do not replace schema verification. They rely on field-based searching in Logging Search. Each search has a time range limit, documented by Oracle as 14 days; split ranges appropriately for longer investigations. [Logging Search and Advanced Queries](https://docs.oracle.com/en-us/iaas/Content/Logging/Concepts/searchinglogs.htm).

Once a suspect event is identified, remove the operation name filter and expand to related compartments/regions if needed. One principal might edit policies, modify networking, and operate on Compute within the same activity sequence.

## 8. Querying with OCI CLI and preserving raw results

### 8.1. Lab prerequisites

The lab machine needs OCI CLI configured with valid authentication. The example below uses PowerShell and the `AUDIT_LAB` profile. The profile's identity has Audit read permissions in the target compartment; this profile does not need infrastructure modification permissions just to run queries.

The commands are examples for learners to run in their own environment. Replace placeholders; the sample time window must be adjusted to match actual events.

### 8.2. Fetching a fully paginated event window

~~~powershell
$auditRegion = 'ap-singapore-1'
$auditCompartment = '<COMPARTMENT_OCID>'
$auditStart = '2026-11-20T01:50:00Z'
$auditEnd = '2026-11-20T02:40:00Z'

$auditArguments = @(
    'audit', 'event', 'list',
    '--profile', 'AUDIT_LAB',
    '--region', $auditRegion,
    '--compartment-id', $auditCompartment,
    '--start-time', $auditStart,
    '--end-time', $auditEnd,
    '--all',
    '--output', 'json'
)

$auditOutput = & oci @auditArguments
if ($LASTEXITCODE -ne 0) {
    throw 'Audit query failed; do not save output as valid evidence.'
}

$auditJson = [string]::Join(
    [Environment]::NewLine,
    [string[]]$auditOutput
)
$auditParsed = $auditJson | ConvertFrom-Json -ErrorAction Stop
if ($null -eq $auditParsed.data) {
    throw 'data field not found in result; inspect the output.'
}

$auditFile = Join-Path (Get-Location) 'audit-window.json'
[System.IO.File]::WriteAllText(
    $auditFile,
    $auditJson,
    [System.Text.UTF8Encoding]::new($false)
)

Get-FileHash -LiteralPath $auditFile -Algorithm SHA256
~~~

`--all` retrieves all pages of the query; it does not automatically traverse all compartments, regions, or entire history. Time arguments use RFC 3339, precise to the minute; set seconds and fractional seconds to `0`. Per the CLI reference, start time is inclusive and end time is exclusive based on event processing time. [`oci audit event list` Reference](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/audit/event/list.html).

The script above checks the exit code and JSON parseability before saving. This prevents treating error messages or invalid output as a successful Audit export.

### 8.3. Distinguishing query time from timeline reconstruction time

When analyzing, use the appropriate timestamp inside the event to describe when activity occurred, while preserving the exact time window used to fetch the data. Do not assume processing time, event time, and the time the investigator downloaded the logs always match.

For recurring extraction jobs built by the operations team, consider:

- Iterating over an approved list of compartments/regions.
- Splitting windows according to volume and current tool limits.
- Using overlap between fetches to reduce the risk of missing late-arriving data.
- Deduplicating by an event key verified against the actual schema.
- Updating the collection watermark only after results are successfully saved.
- Logging authentication failures, pagination errors, API rate limits, and collection gaps.

This is a process design recommendation, not a guarantee that a simple polling script will satisfy all retention requirements. Oracle notes `ListEvents` is not intended for bulk export; for large-scale export streams, use appropriate Logging and Connector Hub mechanisms. [Audit Query API Usage Limits](https://docs.oracle.com/en-us/iaas/Content/Audit/Tasks/listing-log-events.htm).

## 9. Practice tracing a Security List change

### 9.1. Hypothetical context

Operations detected that SSH might be accessible from the Internet at **09:15 on 2026-11-20, UTC+7**. The target Security List belongs to compartment `Prod-Network`. Hypothetical collected facts include:

| Time (UTC) | Observed fact |
| --- | --- |
| 02:06 | A pipeline starts a network configuration deployment |
| 02:10 | Audit shows `UpdateSecurityList`, principal `P`, response `200` |
| 02:12 | Configuration checker detects a rule with source `0.0.0.0/0` to port 22 |
| 02:15 | Operations team receives alert |
| 02:24 | Another update operation restores the rule to internal scope |

All timestamps in this table belong to the hypothetical scenario. They are not query results from a live tenancy.

### 9.2. Investigation steps

**Step 1 — Lock down the target and save the observed configuration.**

Record the tenancy, region, compartment, and Security List OCID. Save the configuration observed at investigation time, but label it accurately as "configuration at collection time"—avoid calling it the immediate post-incident configuration unless proven.

**Step 2 — Find the resource's event sequence.**

Start with a window wider than the alert timestamp, such as 01:50–02:40 UTC. Cross-check all related operations, including the suspect update and the remediation update. Retain the request ID of each event.

**Step 3 — Identify the principal and execution path.**

For principal `P`, find the corresponding deployment job details. Compare pipeline timestamps, workload identity, request ID if logged on the tool side, and source code changes.

If logs only identify a technical principal, state that exact level of conclusion. Do not substitute an engineer's name for the principal merely because that engineer typically manages the pipeline.

**Step 4 — Prove the content of the change.**

If the event includes sufficiently detailed before/after state, compare ingress rules and related fields. Otherwise, use pre-deployment configurations, IaC diffs, or saved configuration snapshots.

A successful `UpdateSecurityList` operation does not prove on its own that it opened port 22. That link requires evidence of the configuration payload.

**Step 5 — Assess reachability and actual access.**

Check components that can affect the path such as routes, IP addresses, NSGs, associated Security Lists, and OS firewalls. An overly broad Security List rule increases risk, while actual connectivity depends on the overall configuration.

Then cross-check available flow logs and host logs within the relevant window. If suitable logs are unavailable, explicitly document that limitation rather than concluding definitively that no one connected.

**Step 6 — Link to change management.**

Cross-check approval tickets, maintenance windows, and configuration versions. Separately record the remediation action, executor, and how the configuration was verified to have returned to the desired state.

### 9.3. Writing a verifiable conclusion

A conclusion appropriate to the hypothetical facts might read:

> Within the inspected region and compartment, Audit recorded principal P calling UpdateSecurityList on resource R at 02:10 UTC with API returning 200. Comparing deployed configuration versions shows an SSH rule with source 0.0.0.0/0 was introduced in the corresponding deployment. There is insufficient evidence in the available log set to determine whether any external SSH session succeeded during the exposure window.

This phrasing clearly separates recorded events, cross-checked results, and what remains unverified. If only the Audit event is available so far, omit claims about the rule content until supplemental evidence is obtained.

## 10. Hands-on lab in an isolated compartment

The practice goal is to prove learners can trace back a known operation without needing to open network ports to the Internet.

### 10.1. Preparation

Use a lab compartment and a dedicated lab network resource provided by an administrator. Record the region, compartment OCID, resource OCID, and initial display name.

The actor performing the change needs permission to update the corresponding attribute. The investigator needs Audit read permissions. If using the same account for both roles in the lab, note that in the results.

There is no need to create extra Compute instances, databases, or billable services just to generate an Audit event.

### 10.2. Create an easily identifiable change

1. Record the UTC timestamp before acting.
2. Use an authorized admin tool to change the lab Security List's display name to a timestamped or tagged name, such as `audit-lab-after`.
3. Leave network rules unchanged.
4. Record the executing principal, completion timestamp, and request ID if provided by the tool.
5. After confirming the rename, record the end time of the practice window.

Choosing a rename creates an administrative trail without altering traffic policy. This is an operation on an assigned lab resource, not an instruction to test modifying production resources.

### 10.3. Locate the event again

Wait for logs to be processed, then search by the exact compartment, region, and recorded time range. Start with the resource OCID; then cross-check:

- Is there an update operation matching the rename?
- Does the principal match the executing identity?
- Does the response code match the observed outcome?
- Does the event provide before/after state information?
- Are there other read or update API calls in the same window?

Export the matching record and enough surrounding context to explain the operation sequence. When parsing JSON with custom tools, keep the original export and create a separate analysis copy.

### 10.4. Restore and document results

Change the display name back to its original value using the same authorized workflow. Locate the restoration event and distinguish it from the first event.

Lab results should include a brief table containing: UTC timestamp, region, compartment OCID, resource OCID, principal OCID, operation name, response code, event ID, and request ID if available. If any field is missing, write "not present in observed record".

The lab achieves its goal when learners can point to the exact event corresponding to the operation performed and accurately explain the limits of the evidence. The event is not required to contain full `stateChange` details.

## 11. Retention, forwarding, and monitoring of Audit

### 11.1. Audit retention and evidence retention requirements

Audit logs are retained for **365 days**. Oracle describes retention at the tenancy level, applying across regions and compartments; this value is currently non-configurable. [Audit Log Retention Period](https://docs.oracle.com/en-us/iaas/Content/Audit/Tasks/settingretentionperiod.htm).

Do not confuse data retention duration with the maximum time span of a single query. Also distinguish built-in reports in IAM identity domains: Oracle documentation states those reports contain 14 days of data, while older data can be queried via OCI Audit within Audit's retention period. [Types of IAM Reports](https://docs.oracle.com/en-us/iaas/Content/Identity/reports/understand-types-reports.htm).

If the organization needs to retain evidence longer, design a dedicated archive store and verify log delivery into it. Do not wait until right before expiration to start collecting.

### 11.2. Reference forwarding architecture

~~~mermaid
flowchart LR
    A["Audit in Logging / _Audit"] --> B["Connector Hub"]
    B --> C["Object Storage archive"]
    B --> D["Supported integration targets"]
    D --> E["Processing and correlation in SIEM"]
    C --> F["Investigation and archive verification"]
~~~

This is a reference architecture; each route must be configured and authorized according to the actual target. Logging integrates with Connector Hub to forward logs, including archiving scenarios to Object Storage. [Archiving Logs to Object Storage](https://docs.oracle.com/en-us/iaas/Content/connector-hub/archivelogs.htm).

For the Audit source, check the `_Audit` selection and connector filter conditions. [Configuring Connectors for Audit](https://docs.oracle.com/en-us/iaas/Content/Logging/Concepts/connectors.htm).

In production deployments, define at least:

- Which sources are collected: tenancy, compartments, regions, and event types.
- Who can modify or stop the connector.
- Whether source read permissions and target write permissions are properly scoped.
- How to detect when forwarding stops or gaps appear.
- How to handle duplicate data, late-arriving data, or schema changes.
- How to test reading archived data back when an investigation is needed.

Do not assume a newly created connector automatically transfers all historical data remaining in Audit. Backfill needs must be verified and organized as a separate task.

Oracle's bulk export documentation directs new requests to Logging and Service Connector Hub instead of the legacy support-ticket process. [Audit Bulk Export](https://docs.oracle.com/en-us/iaas/Content/Audit/Concepts/bulkexport.htm).

### 11.3. Controlling the evidence repository

For exported and archived copies, apply the following principles:

- Preserve the raw original, and create separate redacted or normalized copies for analysis.
- Record the collector, collection timestamp, query used, and data scope.
- Compute hashes when needed to verify whether a file changed after collection.
- Restrict permissions to read, modify, delete, and alter storage configurations.
- Define retention periods, lifecycle rules, and immutability/anti-deletion requirements per organizational policy.
- Periodically test recoverability, readability, and interpretability of stored data.

A hash detects changes relative to the hashed copy; on its own, it does not prove the original data was complete or from a trustworthy source. Evidence also requires collection context and access controls.

Audit logs can contain usernames, IP addresses, OCIDs, paths, and sensitive metadata. Share only what is necessary with authorized individuals; when creating illustrative samples or sharing externally, keep the original in a controlled location and use properly sanitized copies.

### 11.4. Anomaly detection and cost control

Detection rules can be proposed around signals such as policy modifications, sensitive network configuration updates, deletions of critical resources, or multiple authorization failures from the same principal.

A condition based solely on API name is usually insufficient. For example, `UpdateSecurityList` could be a valid change, a rename, or a risky rule update. Combine resource, principal, timing, change content if available, and deployment schedules.

Monitoring channels must be tested with controlled test events. Observe both cases where suspicious events occur and cases where the collection pipeline breaks. A dashboard showing zero alerts does not prove there are no issues.

When budgeting costs, account for export storage, replicas, analytical queries, and integration targets. Tune retention detail to investigation goals; avoid replicating all logs to multiple locations without a clear use case. Do not apply a short deletion window just to save space when that conflicts with evidence retention requirements.

## 12. Troubleshooting missing events or insufficient evidence

| Symptom | How to check |
| --- | --- |
| No results after a lab operation | Check region, compartment, UTC, and wait for processing |
| Have resource management rights but cannot read Audit | Check `audit-events` permissions of the querying identity |
| Logs exist but full sequence is missing | Check pagination, filters, and time range |
| Events appear in only one compartment | Verify child compartment traversal and historical location of the resource |
| Name search returns nothing or multiple resources | Use OCID, then check the name at the time of the event |
| Detailed changes not visible | Check `stateChange` and supplement with historical configs/IaC |
| Cannot find object operations or SQL statements | Switch to log sources at the corresponding data layer |
| Principal is a pipeline identity | Cross-check jobs, commits, and approval records |
| Same event appears multiple times in aggregated store | Check overlap between fetches and deduplication rules |
| Old query fails or misses fields | Inspect actual JSON and verify input source schema |

When handing over results to others, document enough for them to reproduce the investigation:

~~~text
Ticket ID:
Investigation question:
Tenancy / profile:
Inspected regions:
Inspected compartments:
UTC time window:
Collection time (UTC):
Source and query:
Resource OCID:
Principal OCID:
Event ID / request ID / grouping ID if any:
API outcome:
Supplemental evidence:
Proven conclusion:
Unverified points:
Location of raw export and hash if computed:
~~~

A valuable report must distinguish between "no events in the searched scope", "insufficient data to observe", and "evidence exists for the conclusion". When scope, identity, timestamps, and evidence sources are clearly documented, OCI Audit becomes the foundation for tracing infrastructure changes and verifying operational accountability.
