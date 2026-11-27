# Opening Support Requests and Collecting Diagnostic Information

An effective support request (SR) tells Oracle Support exactly which service is having an issue, in what scope, since when, and what needs to be investigated. "Cannot create VM" only describes a symptom; a ticket containing region, OCID, UTC timestamps, request IDs, and check results helps the support engineer locate the exact operation in the system.

In Oracle Cloud Infrastructure (OCI) operations, opening an SR must go hand in hand with access control and diagnostic data protection. Tenancy and compartment define the resource context; VCN, Compute, storage, and database services provide different layers of evidence. The operations team remains responsible for mitigating impact, monitoring availability, and controlling costs while waiting for support.

This lesson guides you through preparing, opening, and tracking a technical SR. Illustrative commands are for reading state and are not executed automatically while reading the lesson. All IDs, resource names, and scenario figures below are illustrative data.

## 1. Learning Outcomes

After this lesson, learners can:

- Distinguish between technical support requests, account or billing support, and service limit increase requests.
- Verify account eligibility, IAM permissions, and support portal permissions before an incident occurs.
- Describe impact using metrics to select an appropriate severity level.
- Correlate an incident with resources, API requests, work requests, Audit, and relevant logs.
- Build a compact diagnostic bundle with timestamps and sensitive data removed.
- Track communication with Oracle Support until recovery is verified and follow-up items are closed.

The lab deliverable is a draft SR along with an evidence manifest. In learning environments, do not submit fake SRs just to test the UI.

## 2. When Should You Open a Support Request?

Open an SR when you need Oracle to investigate, clarify service behavior, or perform account-scoped support actions. You do not need to wait until root cause is identified to open an SR for a major-impact incident; you can send initial facts and add evidence later.

| Scenario | Initial Handling Path | Information to Highlight |
| --- | --- | --- |
| API or resource behaves abnormally, not explained by configuration | Technical support request | Failing operation, region, resource, time, request ID |
| Lost account access or tenancy administration issue | Corresponding account or sign-in support channel | Tenancy identifier and authorized contact |
| Need explanation for an invoice or charge | Billing support | Billing period and cost item needing clarification |
| Need to raise allowed resource limits | Service limit increase workflow | Limit name, region, current limit, requested limit, and reason |
| Want Oracle to explain a recovered incident | Add investigation or RCA request to appropriate ticket | Incident window, impact, evidence, and open questions |

Oracle describes these request types in [Support Requests](https://docs.oracle.com/en-us/iaas/Content/GSG/Tasks/contactingsupport.htm). Formal SR creation applies to paid accounts per Oracle's support terms; users on Always Free or Free Tier only should refer to Support Chat and Cloud Customer Connect described there.

Before submitting, check service notices, maintenance notices, and incidents already published by Oracle, if accessible. Record the source and check timestamp. Not seeing a notice does not prove the service is completely healthy; an issue may affect only one resource, a subset of customers, or not yet be published.

Also distinguish:

- **Service limit** is the service limit applying to the corresponding scope.
- **Compartment quota** is a limit set by the organization for resource governance.
- **Capacity** is actual provisioning availability at the requested location and time.

For example, having remaining OCPU limit is not enough to conclude every shape can be provisioned immediately. In the SR, copy the exact error code and check results for each factor rather than lumping them together as "insufficient quota".

## 3. Prepare Support Permissions Before an Incident

### 3.1. Verify Identity and Permissions Across Two Layers

On-call personnel need to know which tenancy they sign in to, with which account or identity domain, whether contact emails work, and who the backup is.

The first time using support in the Console may require email verification and adding contact details to set up an account on My Oracle Cloud Support. The organization also manages user groups and support permissions in that portal. See details in [Configuring Your Oracle Support Account](https://docs.oracle.com/en-us/iaas/Content/GSG/Tasks/usingsupport.htm).

Two permission layers must be verified separately:

1. **OCI IAM:** permission to call Support Management operations and read resources, logs, and metrics needed for diagnosis.
2. **Support portal:** permission to create, view, or update SRs in the selected user group.

Having permission to manage Compute resources does not mean you are fully set up to create SRs. Conversely, someone authorized to create SRs may not have permission to read Audit or database logs. Preparing contacts with appropriate permissions avoids delays when collecting data.

### 3.2. Example Policies for Support Management

For two IAM groups with the illustrative names below, sample policies are:

~~~text
Allow group OCISupportReaders to read tickets in tenancy
Allow group OCISupportOperators to manage tickets in tenancy
~~~

These are two groups with distinct responsibilities: the first views requests; the second creates and updates requests. Adjust group names and group identifiers according to the actual identity domain when deploying. The [Securing Support Management](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/support-management.htm) documentation provides these policy examples.

According to the [Support Management IAM Policy Reference](https://docs.oracle.com/en-us/iaas/Content/GSG/support/policy-reference.htm), the resource type is `tickets`; creating and updating requires the `manage` level, while `read` covers reading and listing. This policy does not grant Compute, VCN, or Database administration permissions.

If you cannot create an SR or SRs appear read-only, check both IAM and user group permissions in the support portal. For portal permissions, contact your organization's Customer User Administrator (CUA); do not solve it by granting full tenancy admin rights to the user.

## 4. Choose Severity Based on Actual Impact

Severity must reflect current impact, urgency, and available workarounds. The fact that an environment is labeled production is important context but is not enough on its own to describe impact level.

The technical SR creation interface currently describes levels from **Critical issue**, **Significant impairment**, **Technical issue** to **General guidance**. Read the definitions and display conditions when creating a request; Critical level includes confirmation that the request relates to a severe incident. Refer to [Creating a Support Request](https://docs.oracle.com/en-us/iaas/Content/GSG/support/create-incident.htm).

Use the following questions to prepare the business impact section:

| Question | Verifiable Answer |
| --- | --- |
| Which function is impacted? | Cannot confirm orders, cannot provision new Compute, backups failing |
| What is the scope? | One instance, two subnets, one region, or one user group |
| Since when? | Detection time, last known normal operation time, and UTC timestamps |
| How much impact? | 420/1,000 transactions failing in 10 minutes; two additional nodes failed to provision |
| Is there a workaround? | Using standby nodes; handles current load but redundancy is reduced |
| Is there any business deadline? | Backup window ending soon or capacity needed before a known traffic surge |
| Who can coordinate? | Primary contact, backup contact, and availability window |

Do not infer a guaranteed resolution time from severity level. Response conditions, coordination, and service commitments must be checked against the applicable support agreement. When impact changes, update the SR with new figures and request a severity review if needed.

Example phrasing:

> Since 02:10 UTC, two provisioning attempts for new nodes in the ordering system failed. Six existing nodes continue serving traffic; no failed transactions due to this incident have been recorded. Scaling and standby recovery capacity is reduced ahead of the expected load increase at 06:00 UTC.

This paragraph helps the recipient understand the problem far better than a subject reading only "Production down", while avoiding claiming the system is down when metrics do not show that.

## 5. Minimum Identification Information Set

### 5.1. Resources, Location, and Time

| Field | What to Record | Notes |
| --- | --- | --- |
| Tenancy | Tenancy OCID and recognizable name if appropriate | Verify the right organization account |
| Compartment | Compartment OCID of the resource or operation | Do not use name alone because names can duplicate |
| Region | Region where the operation or resource is impacted | Distinguish from the tenancy home region |
| Availability domain, fault domain | Actual value if present and relevant | Do not guess or fill in for non-applicable services |
| Resource | Service type, name, and OCID | Include directly related dependent resources |
| Time | Last success, first failure, sample timestamps, and recovery time | Use ISO 8601 with time zone, preferring UTC |
| Tool | Console, OCI CLI, SDK, or IaC tool and version | Distinguish user workstation from CI/CD environment |
| Operation | Actual API name, command, or operation sequence | Strip credentials from commands |

For example, `2026-11-21T09:10:00+07:00` corresponds to `2026-11-21T02:10:00Z`. Writing "this morning" loses context when support engineers work in different time zones.

If the exact start time is unknown, clearly record "first observed at" instead of treating it as the guaranteed fault onset time. Keep timestamps from client clocks and server clocks separate if clock skew is suspected.

### 5.2. Distinguish Between ID Types

| ID Type | What Is It Used For? | Does Not Replace |
| --- | --- | --- |
| Resource OCID | Identifies an object such as instance, subnet, volume, or database | A specific API call |
| `opc-request-id` | References a single API request processing at the service | The entire lifecycle of a long operation |
| Work request ID | Tracks asynchronous operations and their errors or logs | Request ID of each status-polling call |
| Application trace ID | Traces a request inside the application when tracing is configured | Proof that OCI received the corresponding API call |
| SR number | Tracks the support case with Oracle Support | Resource OCID or internal incident ID |

Oracle requires providing the response `opc-request-id` when assistance is needed for a specific API request; see [REST APIs — Request and Response Format](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/usingapi.htm). Preserve the exact real ID value in an authorized support channel.

For asynchronous tasks, an initial successful HTTP response does not prove provisioning completed. Also save the `opc-work-request-id`, final status, errors, and related resources per [Asynchronous Work Requests](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/workrequests.htm). Do not mistakenly report the request ID of a status-get command as the request ID of the initial create operation.

If an operation was retried, list the attempts:

~~~text
attempt | time_utc             | operation      | result          | opc_request_id
1       | 2026-11-21T02:10:00Z | LaunchInstance | accepted        | <response-id-1>
2       | 2026-11-21T02:14:00Z | LaunchInstance | accepted        | <response-id-2>

work_request_id   | related_attempt | final_status | observed_at_utc
<work-request-1>  | 1               | FAILED       | 2026-11-21T02:12:00Z
<work-request-2>  | 2               | FAILED       | 2026-11-21T02:16:00Z
~~~

This illustrative table only shows how to link data. Do not repeat resource-creation operations merely to fill rows.

## 6. Organize Work During an Active Incident

During a major incident, service recovery and evidence collection should have clear owners. Do not let the entire team stop mitigating impact just to wait together for an SR reply.

~~~mermaid
flowchart TD
    A["Detect and determine impact"] --> B["Record UTC timestamps, resources, and request IDs"]
    B --> C["Mitigate impact per runbook"]
    B --> D["Create SR with initial evidence"]
    C --> E["Update outcomes and changes in timeline"]
    D --> E
    E --> F["Add diagnostics for specific questions"]
    F --> G["Verify recovery via business tests"]
    G --> H["Complete investigation, close SR, and track follow-ups"]
~~~

A practical division of roles:

- The coordinator maintains the timeline, assesses impact, and decides operational changes.
- The technical engineer gathers evidence and executes mitigation actions within assigned permissions.
- The Support liaison keeps the SR updated, routes questions to the right team, and ensures follow-through.

A small team may combine roles, but must explicitly document who holds which responsibility. Every action such as rollback, route change, scaling, failover, or restart must have a timestamp and outcome in the timeline. Otherwise, a change made by the operations team itself can be misinterpreted as natural progression of the incident.

## 7. Choose Evidence at the Right Layer

### 7.1. Start with Investigative Questions

Every file should help answer a question:

- Did the request reach the OCI service?
- Did the failure occur during authentication, validation, or asynchronous processing?
- Is the impact isolated to one resource or multiple resources sharing a dependency?
- Were there any configuration changes near the start time?
- Did mitigation actions change the symptoms?

Select corresponding data from there:

| Layer | Priority Evidence | Question Supported |
| --- | --- | --- |
| IAM and API | Principal, compartment, operation name, HTTP status, error code, request ID | Are identity, scope, and error type verified? |
| Work request | ID, operation type, timestamps, status, errors, and logs | Which asynchronous stage failed? |
| Audit | Events related to API calls and configuration changes | Who called what operation and when? |
| Monitoring | Metric, dimension, time range, interval, and alarm | How did impact level change over time? |
| Service logs | Enabled and relevant service logs | What errors did the service observe? |
| OS and application | Journal, application logs, deployed version, traces | Is there an issue inside the workload? |

Audit records API activity for supported services by tenancy and compartment. Events may arrive with delay; check the right scope and time window per [Viewing Audit Log Events](https://docs.oracle.com/en-us/iaas/Content/Audit/Tasks/viewinglogevents.htm).

Do not treat the absence of an Audit event as sole proof that a request never existed. Similarly, service logs that were not enabled before the incident cannot provide the historical data you need.

### 7.2. Compute

For provisioning failures or unreachable instances, select data matching the symptoms:

- Instance OCID if already created; region, availability domain, fault domain, shape, and image.
- Lifecycle state and observed creation, start, or stop timestamps.
- Work requests and associated errors if the operation supports work requests.
- Available health, CPU, memory, or I/O metrics; clearly note which metrics are not collected.
- Boot logs or serial console history if retrievable with current permissions.
- Most recent OS updates, application changes, or configuration changes if relevant.

The RUNNING state reflects only one aspect of the instance; check access paths and workload health to evaluate serving capability.

Collecting diagnostics also differs from performing disruptive diagnostic actions. For example, a diagnostic reboot stops, rebuilds, and restarts the VM and causes downtime; Oracle recommends using it after other troubleshooting steps in [Performing a Diagnostic Reboot](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/diagnostic-reboot.htm). Do not treat this operation as routine log reading.

### 7.3. VCN and Network Connectivity

For network errors, describe **source → destination → protocol → port → timestamp** before attaching diagrams.

For example: "From private IP of app node A to private endpoint of database B, configured TCP port, timing out starting 02:10 UTC; node C in another subnet can still connect."

Useful evidence includes:

- VCN, subnet, VNIC, and the NSGs or security lists actually applied.
- Route tables attached to the subnet and relevant gateways or DRG along the path.
- Return path, DNS resolution, and OS firewall configuration if applicable.
- Test results from each source with timestamps and error type: timeout, connection refused, or TLS error.
- VCN Flow Logs if enabled for the scope to observe.
- Status of VPN, FastConnect, or customer-side devices if used on the path.

A failed ping alone does not prove an application port is blocked. Do not open all ingress for a "quick test"; trace the path and modify rules only through the proper operational workflow.

### 7.4. Storage

For Block Volume, collect the volume OCID, related attachments, attachment type, and OS I/O observations. Separate device health, filesystem, and application data to avoid blaming every latency spike on the volume.

For Object Storage, record region, namespace, bucket, operation name, relevant object if needed, size, and upload type. Specify which authentication mechanism the request uses without sending credentials. Do not attach object contents if metadata and logs suffice for the question under investigation.

For File Storage, record the filesystem, mount target, mount path, affected clients, and relevant mount options. Describe client-side errors along with necessary network configuration.

### 7.5. Oracle Database Services

First identify the exact product: Autonomous Database, Base Database Service, Exadata Database Service, or another specific service. OS access, collection tools, and operational responsibilities differ by product.

Initial information typically includes:

- OCID of the affected service resource and related resources.
- Version or patch level if viewable and relevant to the issue.
- Error timestamp, operation, full ORA error string, and affected application.
- Work request when service management operations generate one.
- Evidence of connections, load, or backups directly tied to the incident.
- Diagnostic bundles, alert logs, or traces only when supported by the product and required for investigation.

In environments with tools such as Autonomous Health Framework or Trace File Analyzer, follow instructions for the exact product and Support's specific request. Do not assume every database service allows SSH to hosts or shares a single collection workflow.

SQL text, bind values, traces, and dumps may contain business data. Consider scope before exporting; a diagnostic log does not automatically become data safe for broad sharing.

## 8. Collection Example Using OCI CLI on PowerShell

The following example applies when reading a Compute instance and querying Audit within a compartment. It **does not collect all** evidence types listed above.

Prerequisites:

- OCI CLI is installed and validly authenticated.
- A pre-configured profile has permissions to read the required data.
- The operator replaces region, OCID, and timestamps with real values.
- The output directory resides in a location approved by the organization for storing diagnostic data.

### 8.1. Create a Dedicated Directory and Record Context

~~~powershell
$caseProfile = "SUPPORT_READ"
$caseRegion = "ap-singapore-1"
$caseCompartmentId = "<compartment-ocid>"
$caseInstanceId = "<instance-ocid>"
$caseStartUtc = "2026-11-21T02:00:00Z"
$caseEndUtc = "2026-11-21T02:30:00Z"

$caseSuffix = [guid]::NewGuid().ToString("N").Substring(0, 8)
$caseDirName = "oci-diag-" + $caseSuffix
$caseOutputDir = Join-Path $env:TEMP $caseDirName
New-Item -ItemType Directory -Path $caseOutputDir -ErrorAction Stop |
    Out-Null

$caseContext = [ordered]@{
    collectedAtUtc = (Get-Date).ToUniversalTime().ToString("o")
    region = $caseRegion
    compartmentId = $caseCompartmentId
    instanceId = $caseInstanceId
    startUtc = $caseStartUtc
    endUtc = $caseEndUtc
    purpose = "Read-only collection for a specific incident"
}

$caseContext | ConvertTo-Json |
    Out-File -LiteralPath (Join-Path $caseOutputDir "context.json") -Encoding utf8

oci --version 2>&1 |
    Out-File -LiteralPath (Join-Path $caseOutputDir "oci-version.txt") -Encoding utf8

Write-Output $caseOutputDir
~~~

`SUPPORT_READ` is merely an illustrative profile name, not a mechanism that grants read rights automatically. Verify the actual permissions of the identity in the profile. Do not include authentication configuration files in outgoing bundles.

### 8.2. Read Compute Status

~~~powershell
$caseInstanceArgs = @(
    "compute", "instance", "get",
    "--instance-id", $caseInstanceId,
    "--region", $caseRegion,
    "--profile", $caseProfile,
    "--output", "json"
)

& oci @caseInstanceArgs 2> (Join-Path $caseOutputDir "instance-get.stderr.txt") |
    Out-File -LiteralPath (Join-Path $caseOutputDir "instance-get.raw.json") -Encoding utf8

$caseInstanceExitCode = $LASTEXITCODE
Write-Output "instance-get exit code: $caseInstanceExitCode"
~~~

Keep stderr as well when the command fails. If the instance no longer exists or never received an OCID, record that status clearly and prioritize data from the initial request and work request instead of trying to recreate the resource just to gather info.

Output may contain internal metadata or names; treat it as raw data requiring review before sharing.

### 8.3. Read Audit Within a Narrow Time Window

~~~powershell
$caseAuditArgs = @(
    "audit", "event", "list",
    "--compartment-id", $caseCompartmentId,
    "--start-time", $caseStartUtc,
    "--end-time", $caseEndUtc,
    "--region", $caseRegion,
    "--profile", $caseProfile,
    "--all",
    "--output", "json"
)

& oci @caseAuditArgs 2> (Join-Path $caseOutputDir "audit.stderr.txt") |
    Out-File -LiteralPath (Join-Path $caseOutputDir "audit.raw.json") -Encoding utf8

$caseAuditExitCode = $LASTEXITCODE
Write-Output "audit-list exit code: $caseAuditExitCode"
~~~

This command only queries the specified compartment and region. It does not automatically search every compartment or region in the tenancy. `--all` fetches all pages of query results; therefore, restrict the time window to the incident before running. Audit time parameters require minute-level precision with seconds set to 0 per [OCI CLI — audit event list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/audit/event/list.html).

If data has not appeared yet, consider processing delay, permissions, and query scope. Do not replace it with an unbounded export of the entire tenancy's Audit logs.

### 8.4. Retrieve Work Requests and Targeted Debug Info

From the resource page in the Console, find the related work request, open its status, and retrieve provided errors or logs. Paths and visibility vary by service; see [Work Requests](https://docs.oracle.com/en-us/iaas/Content/General/Concepts/workrequestoverview.htm).

If CLI debug is needed to investigate a read command:

1. Enable `--debug` only for the selected run.
2. Capture both stdout and stderr into a restricted-access location.
3. Record the execution time and distinguish this new request from the original failing request.
4. Review headers, payloads, metadata, and returned data before sending.

Debugging a `get` command cannot fully recover the request ID of a previously executed `create` command. Avoid re-running side-effecting operations just to capture debug output. For applications using SDKs, design logging from the start to capture request IDs and error context while excluding credentials and unnecessary business data.

## 9. Package and Protect Diagnostic Information

### 9.1. Separate Raw Originals from Support-Ready Copies

Keep raw originals in an internal repository with access controls. Create a sanitized copy to send to Oracle and clearly note what was removed. Redaction must preserve correlation: the same address or user must be replaced with the same consistent label if they need to be correlated across multiple logs.

Information types requiring special review:

| Data Type | Handling Before Sending |
| --- | --- |
| Private keys, passwords, tokens, client secrets, session cookies | Remove from content; if already exposed, revoke or rotate per procedure |
| OCI config, environment variables, IaC state files | Do not send in full; extract needed fields and review sensitive values |
| Database wallets or credential documents | Do not include in routine diagnostic bundles |
| HAR and HTTP traces | Review auth headers, cookies, query strings, request and response bodies |
| SQL, traces, dumps, objects, or app payloads | Identify personal and business data before exporting |
| OCIDs and network addresses | Provide when needed for identification in authorized SRs; use caution on public forums |

Do not redact away entire OCIDs or request IDs that Oracle needs to locate events in authorized cases. If organizational policy restricts sharing, state the restriction to Support to agree on an appropriate delivery method.

Attach through the support portal or a verified upload channel for the SR. Do not create a public bucket or public URL merely to transfer a diagnostic bundle.

### 9.2. Small but Well-Guided Bundle

A sanitized bundle can be organized as follows:

~~~text
diagnostics-sanitized/
  manifest.txt
  timeline.csv
  request-attempts.csv
  instance-summary.json
  work-request-errors.txt
  audit-extract.json
  metrics-window.png
  network-path.txt
~~~

This is a structural suggestion, not a mandatory file set for every SR. Keep only files relevant to the investigative questions.

Example `manifest.txt` content:

~~~text
Incident reference: INC-EXAMPLE-001
Affected service: OCI Compute
Region: ap-singapore-1
Incident window UTC: 2026-11-21T02:10:00Z to 2026-11-21T02:25:00Z
Collection time UTC: 2026-11-21T02:28:00Z

timeline.csv:
  Observations and operator actions; all timestamps are UTC.

request-attempts.csv:
  Initial API requests linked to asynchronous work requests.

audit-extract.json:
  Relevant entries from the affected compartment only.

Redaction:
  Customer identifiers replaced with stable labels.
  Authentication material and unrelated payloads removed.

Gaps:
  No guest OS logs: the affected instances did not finish provisioning.
  No complete historical flow logs available for this window.
~~~

Explicitly noting evidence gaps is better than filling them with speculation. If using chart screenshots, preserve metric names, resource dimensions, time range, time zone, and resolution; images cropped without time axes are often hard to use.

After finalizing the outgoing package, you can compute checksums for the final files for handover verification. If you continue editing or redacting, recompute checksums. Do not treat checksums as a method of concealing content or granting access.

## 10. Write SR Content So the Recipient Can Start Investigating

A good description clearly separates **facts**, **hypotheses**, and **requested assistance**. Do not state a hypothesis as a confirmed conclusion.

### 10.1. Subject with Scope and Symptom

Template:

~~~text
[Service][Region][Environment] Observed symptom since <UTC time>
~~~

Example:

~~~text
[Compute][ap-singapore-1][Production]
New instance provisioning fails; existing instances remain available
~~~

Do not include passwords, customer names, or transaction payloads in the subject.

### 10.2. Usable Description Template

~~~text
1. Summary
   We observe <specific symptom> on <service> in <region>.

2. Business impact
   Affected function:
   Affected users, requests or resources:
   Current measured error rate or loss of capacity:
   Workaround and remaining risk:
   Relevant business deadline:
   Requested severity and reason:

3. Timeline (UTC)
   Last known successful operation:
   First observed failure:
   Selected failed attempts:
   Mitigation actions and observed results:
   Current status:

4. Environment and identifiers
   Tenancy OCID:
   Compartment OCID:
   Region:
   Availability domain / fault domain, if relevant:
   Resource OCIDs:
   Client or tool version:
   Authentication method (no credentials):

5. Operation and observations
   Expected result:
   Actual result:
   Exact error code and sanitized message:
   Original response opc-request-id:
   Related work request ID and final status:
   Frequency and scope:

6. Checks already performed
   Check:
   Time performed:
   Result:
   Supporting attachment or evidence reference:

7. Recent changes
   Confirmed changes:
   Unknown or unverified items:

8. Evidence
   Attachment manifest:
   Collection window and time zone:
   Redactions and missing data:

9. Assistance requested
   Please investigate <specific unresolved question>.
   Please advise on <safe next diagnostic step or mitigation>.
   RCA requested if appropriate.

10. Contacts
    Primary and backup contacts:
    Time zone and availability:
    Internal incident reference:
~~~

The template is in English for convenience when international coordination is needed; you can fill it in using the language suited to your Support workflow. The value of the template lies in its structure and facts, not in using one fixed language.

The "Checks already performed" section must include results. "Checked network" is too broad; "02:18 UTC, inspected route table attached to subnet X, found no changes compared to approved configuration; extract in file Y" helps the recipient decide the next step.

### 10.3. Clear Support Requests

Questions you can ask:

- Please investigate why the specific work request failed within the stated window.
- Please confirm whether there is a known service issue or limitation associated with these IDs.
- Please advise on the next diagnostic step given the current impact and access permissions.
- After recovery, please clarify the root cause and preventive recommendations if available.

Do not ask Support to confirm a guessed root cause before sufficient evidence exists. For instance, "please investigate the failed work request" establishes a much better investigation scope than "please fix the faulty hypervisor" when there is no host-level evidence.

## 11. Create and Verify the Request Was Recorded

In the OCI Console, open the **Help** menu, select **Create a Support request**, or navigate via **Support Center**. Choose the appropriate request type, fill in the description, impact level, and service classification. For technical SRs, choose a support user group with permission and ability to track the ticket. See current steps and fields in [Creating a Support Request](https://docs.oracle.com/en-us/iaas/Content/GSG/support/create-incident.htm).

Button names and intermediate steps may differ depending on the support flow or transition to My Oracle Cloud Support. When the UI differs from this guide, consult Oracle documentation to confirm the corresponding path.

Before submitting:

1. Verify the right tenancy, region, service, and contact information.
2. Re-read the impact level alongside available facts.
3. Confirm attachments are sanitized copies and comply with portal display limits.
4. Ensure at least one person can monitor replies.

After submitting, save the SR number and link the case in the internal incident record. Confirm that the on-call engineer or backup can view the request and has permission to update it. Do not treat clicking submit as the sole proof that the request was received.

If the SR is not visible, check the account, user group, filters, and active portal before creating another ticket. [Listing Support Requests](https://docs.oracle.com/en-us/iaas/Content/GSG/support/list-incidents.htm) explains that visibility depends on user group, permissions, and migrated portal SR details if applicable.

If you cannot sign in to the Console, use the sign-in support channel guided by Oracle at [Troubleshooting Signing In to the Console](https://docs.oracle.com/en-us/iaas/Content/GSG/Tasks/signinginIdentityDomain.htm). Never share passwords or MFA codes with others so they can open an SR on your behalf.

## 12. Track the SR and Collaborate with Support

### 12.1. Every Update Should Add New Information

A concise update should include:

~~~text
Update time UTC: 2026-11-21T02:40:00Z

Current impact:
  Existing application nodes remain available.
  New provisioning remains blocked.

New observation:
  The same work request is still FAILED; no new create attempts were made.

Action performed:
  Compared relevant configuration with the approved deployment baseline.

Result:
  No difference found in the reviewed fields.
  This does not establish the root cause.

Evidence added:
  sanitized-comparison.txt, covering the fields listed in its header.

Assistance needed:
  Please review the asynchronous failure for the work request already provided.

Next coordination:
  Primary and backup contacts are available during the stated support window.
~~~

Distinguish "no differences found in the inspected fields" from "no changes at all". The first phrasing states the boundary of the evidence.

When Oracle asks you to run a command or change configuration, verify:

- The exact resource, product, version, and environment scope.
- The goal of the action and expected data.
- Impact on availability, performance, capacity, and cost.
- Who will execute it, the change window, and how to recover if there is operational impact.

If instructions are unclear, ask back on the SR before running operations that may stop machines, fail over, generate large dumps, or alter data. Record both successful and failed outcomes of the requested step.

### 12.2. Escalate with Specific Justification

Consider requesting coordination or escalation when impact grows, temporary workarounds no longer suffice, or case handling does not meet applicable support terms.

Add metrics, deadlines, and desired actions to the existing ticket. Use the escalation process specified on the portal or in the support agreement; avoid opening multiple duplicate SRs just to gain attention. If multiple SRs are needed for distinct issues, cross-link them and describe the scope of each ticket.

Shift handovers must include the SR number, impact status, pending questions, owner of the next action, and timestamp of the last update. Notification emails do not replace having an actual person actively tracking the case.

## 13. Practice Scenario: Compute Provisioning Failure

### 13.1. Initial Facts

A team operates an ordering system in the illustrative region `ap-singapore-1`. Six existing instances continue serving, but two attempts to add instances failed at the asynchronous stage.

Recorded timeline:

| UTC Time | Observation or Action |
| --- | --- |
| 01:50 | Recorded last successful provisioning within the inspected window |
| 02:10 | First provisioning request accepted |
| 02:12 | First work request transitioned to FAILED |
| 02:14 | One controlled retry performed |
| 02:16 | Second work request transitioned to FAILED |
| 02:18 | Team halted further create attempts and collected IDs, errors, and related config |
| 02:25 | Verified six existing nodes still serving; no failed transactions observed from this issue |

These details are scenario data for the exercise and do not describe a real Oracle incident.

### 13.2. How to Build the Case

The team prepares:

1. Tenancy, compartment, region, and IDs from both attempts.
2. Provisioning response request IDs and corresponding work request IDs.
3. Verbatim asynchronous errors from the work requests, reviewed for sensitive data.
4. Shape, image, availability domain, subnet, and relevant deployment parameters.
5. Check results for service limits, applied quotas, and configuration changes.
6. Evidence that the six existing nodes are still serving along with remaining redundancy level.
7. A request asking Oracle to investigate why the two work requests failed.

The team does not write "definitely out of capacity" if the only fact is failed provisioning. Do not raise severity to the highest level without corresponding impact.

### 13.3. Mitigate Impact and Control Costs

The coordinator evaluates using existing standby capacity or selecting an approved alternative configuration. Changing shape, deployment placement, or region can affect performance, network addressing, licensing, data connectivity, and cost; evaluate against the real architecture.

During investigation:

- Limit retry counts and log each attempt's result; stop once reproducible evidence is captured.
- Check whether timed-out attempts left behind running or creating resources.
- Record temporary resources created for recovery and who is responsible for tearing them down.
- Revoke extra debug logging and narrow collection scopes once no longer needed.
- Monitor diagnostic bundle storage costs and retention periods per internal policy.

Do not hastily delete related resources while investigation is still needed. When cleanup is necessary, save identifiers, configuration, and required evidence first, and log the action in the timeline.

## 14. Verify Recovery and Close the Case

"No more errors seen" is one signal, but the impacted functionality must be re-tested.

For a Compute provisioning scenario, verification criteria might include an approved deployment completing, the instance reaching the desired state, workload checks passing, and standby capacity restored. If verification creates resources or cost, perform it in line with real deployment needs or an approved test plan.

Before closing the SR:

- Record the recovery start time and stability observation window.
- State relevant business or infrastructure verification results.
- Record the action that restored service and the confidence level of that assessment.
- Clarify open questions, RCA needs, and next follow-up tracking.
- Revoke temporary permissions, debug configurations, and unneeded temporary resources.
- Archive internal records per retention policy and confirm the owning team agrees to close.

Distinguish three cognitive states: service has recovered; root cause is confirmed; preventive measures are deployed. These may be reached at different times. If recovered while root cause remains unclear, document that status accurately and align on continued investigation with Support.

## 15. Common Mistakes That Delay Support Cases

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Attaching only error screenshots | Missing searchable IDs, timestamps, or error strings | Include raw text and required identifiers |
| Wrong region or wrong compartment | Searches wrong scope | Pull values from the actual resource and request |
| Sending the request ID of a new read command | Fails to locate the original failing operation | Link each ID to its operation and timestamp |
| Recording only initial HTTP success | Misses asynchronous failures | Include work request status and errors |
| Sending multi-day logs | Slows transfer, adds irrelevant noise | Filter by window, resource, and question |
| Redacting all lookup IDs | Support lacks data to locate events | Share necessary identifiers via authorized channel |
| Sending raw credentials or wallets | Credential exposure | Sanitize, restrict access, and rotate exposed secrets |
| Immediately restarting or deleting resources | Destroys evidence, changes symptoms | Save evidence and assess impact before acting |
| Writing only "checked" | Hard to know what remains unchecked | Record scope, timestamp, result, and proof file |
| No dedicated SR owner | Support questions sit across multiple shifts | Assign primary and backup contacts |

## 16. End-to-End Exercise in a Learning Environment

Choose a simulated scenario matching resources you are authorized to observe, such as an existing provisioning error record or a connection error from sanitized sample logs. Do not create downtime in shared environments just to generate data.

Complete in sequence:

1. Write an impact description in three to five sentences, noting which facts are simulated.
2. Record tenancy, compartment, region, and related resources using placeholders if producing documentation only.
3. Normalize the timeline to UTC, keeping the original time zone if cross-reference is needed.
4. List request IDs, work request IDs, and information gaps; never invent IDs and present them as real facts.
5. Select only evidence directly answering investigative questions, create a manifest, and review for sensitive data.
6. Fill out the SR template from Section 10, including suggested severity and rationale.
7. Write one mid-incident update and one recovery verification record.
8. List temporary resources, temporary permissions, extra logs, and cleanup items to track.

A draft meets requirements when someone else can determine exact scope, understand impact level, locate every piece of evidence, and know what question Oracle needs to help resolve. Keep this exercise as a draft; only open real SRs for genuine support needs authorized by your organization.
