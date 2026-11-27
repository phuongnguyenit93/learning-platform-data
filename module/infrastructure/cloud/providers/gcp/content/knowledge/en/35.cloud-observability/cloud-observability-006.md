# Cloud Audit Logs and Selecting Audit Log Categories

When operating Google Cloud, platform teams must be able to answer questions such as: who changed IAM permissions, which service read sensitive data, which operations were denied, and where a configuration change originated. Cloud Audit Logs records activity related to the use of Google Cloud resources, helping organizations investigate incidents, control changes, meet audit requirements, and demonstrate how resources are accessed.

Cloud Audit Logs is part of Cloud Logging. Each audit record typically contains information about the service, API method, resource, calling identity, outcome, and request context. However, the level of detail varies by service and API method. Therefore, audit design should begin by identifying which events must be recorded, which identities need tracking, and how log data will be protected, stored, and queried.

## 1. The Four Categories of Cloud Audit Logs

Cloud Audit Logs has four primary categories. Each category reflects a distinct group of activities and serves a specific investigative goal.

| Log Category | Contents | Default Status and Examples |
| --- | --- | --- |
| Admin Activity | Operations that modify resource configuration or metadata | Always enabled. Examples: creating a VM, changing a firewall rule, updating an IAM policy, or deleting a bucket |
| Data Access | Operations reading metadata, reading user-provided data, or writing user-provided data | Typically disabled by default, except for certain services like BigQuery. Examples: reading an object in Cloud Storage or querying a table |
| System Event | Administrative actions performed by Google systems on resources | Always enabled. Example: system actions that alter resource state or configuration |
| Policy Denied | Requests denied due to security policy or access control violations | Generated for cases and services supporting this log category; used to find why access was blocked |

Admin Activity and System Event are two essential sources for tracking resource changes. They are automatically recorded by Google Cloud and cannot be disabled through normal audit logging settings. Data Access requires proactive consideration because it can generate high log volume. Policy Denied helps identify blocked activity, though it does not replace inspecting IAM policies, VPC Service Controls, or other security policies.

### Admin Activity: Who Changed the Configuration?

Admin Activity logs administrative actions that modify resource configuration or metadata. Common examples include:

- Creating, updating, or deleting Compute Engine resources.
- Modifying the IAM policy of a project, folder, or resource.
- Creating or updating buckets, datasets, service accounts, or network configurations.
- Modifying service configurations that affect how resources operate.

This is usually the first log category to inspect when an unexpected change appears. If an account grants Owner permissions to another principal, Admin Activity records can help identify the calling identity, API method invoked, affected resource, and timestamp of the change.

### Data Access: Who Read or Wrote Data?

Data Access logs operations that access data or metadata. This category comprises three configuration groups:

| Configuration Group | Meaning | Examples |
| --- | --- | --- |
| ADMIN_READ | Reads resource configuration or metadata | Reading configuration details or metadata of a resource |
| DATA_READ | Reads user-provided data | Reading an object in Cloud Storage or querying data in BigQuery |
| DATA_WRITE | Writes, creates, updates, or deletes user-provided data | Uploading an object to a bucket or modifying data in a table |

A common point of confusion is that ADMIN_READ belongs to Data Access audit logs. It records reading configuration or metadata, whereas Admin Activity records administrative operations that modify configuration. Thus, a query reading an IAM policy may belong to ADMIN_READ; modifying an IAM policy belongs to Admin Activity.

Data Access is typically disabled by default on many services because read and write request volumes can be very large. BigQuery is a key exception: BigQuery Data Access audit logs are enabled by default and cannot be disabled. When investigating whether sensitive data was read, you cannot rely solely on Admin Activity; ensure Data Access logging is enabled for the relevant service and data scope.

### System Event: What Did the System Do Automatically?

System Event records administrative actions performed by Google systems on resources. These events can occur without a user directly invoking the corresponding administrative operation. When a resource changes state due to platform action, System Event helps operations teams distinguish system-initiated events from changes requested by users or applications.

System Event is always enabled. During investigations, review it alongside Admin Activity and other operational logs to understand the full chain of events rather than assuming every change originated from a user account.

### Policy Denied: Why Was a Request Blocked?

Policy Denied logs requests rejected due to security policies or access controls. For example, a user may hold IAM permissions at one level while the request is still blocked by another constraint, or an operation violates an organization policy.

When reviewing this log type, inspect the principal, resource, service, API method, status code, and denial reason details if provided by the service. Not every application error is Policy Denied: network failures, authentication errors, quota errors, or service state errors can have other causes. Correlate audit logs with application logs and service status.

## 2. Selecting Log Categories by Audit Question

Do not enable every Data Access category across every project without a clear objective. Start from the question you need to answer, then select the corresponding log type and service.

| Question to Answer | Log Category to Inspect | Scope Example |
| --- | --- | --- |
| Who created, modified, or deleted a resource? | Admin Activity | Project, folder, Compute Engine, IAM |
| Who read configuration or metadata? | Data Access – ADMIN_READ | Bucket metadata, service configuration |
| Who read business data? | Data Access – DATA_READ | Sensitive objects, BigQuery tables, secrets |
| Who created, modified, or deleted data? | Data Access – DATA_WRITE | Buckets, datasets, or data stores |
| What automated action did the platform take? | System Event | Resources managed by Google services |
| Why was a request denied? | Policy Denied and related logs | IAM, organization policies, or service controls |

For development environments with little sensitive data, organizations can prioritize Admin Activity and System Event while enabling Data Access selectively for services requiring detailed investigation. For production environments holding customer data, financial records, or application secrets, evaluate enabling DATA_READ and DATA_WRITE across storage services, databases, and Secret Manager.

A practical selection matrix might look like:

| Resource or Service | Control Question | Options to Evaluate |
| --- | --- | --- |
| IAM and service accounts | Who modified permissions or used an identity? | Admin Activity; Data Access ADMIN_READ if metadata reads must be tracked |
| Cloud Storage | Who read or wrote objects? | DATA_READ and DATA_WRITE |
| BigQuery | Who queried or modified data? | BigQuery Data Access is enabled by default; check scope and queryability |
| Secret Manager | Who accessed secret versions or modified secrets? | Admin Activity and Data Access per service support |
| Compute Engine and VPC | Who changed VMs, firewalls, or network settings? | Admin Activity; System Event for system-performed actions |
| Services using CMEK | Who changed key settings or accessed data through the service? | Cloud KMS Admin Activity and Data Access on the data service when needed |

Log category names do not guarantee that every API method of a service produces identical data fields. Before operationalizing an audit requirement, check each service's audit logging documentation to see which methods are logged, which categories are supported, and which fields can be queried.

## 3. Enabling Data Access Logs via IAM auditConfigs

Data Access logging is configured through the auditConfigs section of an organization, folder, or project IAM policy. Configuration can apply to all services or only specific services. When designing it, choose the right scope to satisfy audit policies without generating unnecessary log volume.

The example below illustrates configuring Cloud Storage to log data read and write operations:

~~~yaml
auditConfigs:
- service: storage.googleapis.com
  auditLogConfigs:
  - logType: DATA_READ
  - logType: DATA_WRITE
~~~

This is an auditConfigs snippet to merge into an existing IAM policy, not a standalone complete policy. When updating a policy, preserve existing bindings, conditions, other audit configs, and the current etag. Never overwrite an active policy with a file containing only this snippet.

If an organization wants a shared configuration across many services, it can use allServices as the service and add per-service configs for exceptions. Check inheritance rules from organization down to folders and projects, as well as per-service overrides. A lower-level config can alter how inherited settings apply to that service.

The exemptedMembers field allows excluding principals from certain Data Access audit logs. This mechanism directly impacts auditability. Use exemptions only with clear justification, approval, and documentation; avoid exempting operational accounts or critical service accounts merely to reduce log volume.

### Verifying Configuration After Enabling

After updating the IAM policy:

1. Re-read the policy at the exact organization, folder, or project level to confirm auditConfigs was saved.
2. Verify whether the configuration is overridden or affected by inherited policies.
3. Perform a safe test action on a test resource, such as reading or writing a non-sensitive object.
4. Open Logs Explorer and search for the Data Access log by service, principal, and test timestamp.
5. If no log appears, check whether the service supports that method, whether logs were excluded or routed to another bucket, and whether the viewer has sufficient log read permissions.

Enabling auditConfigs does not mean every record appears instantly in an arbitrary query. Verify the exact project holding the logs, the correct log category, time range, and resource scope.

## 4. Reading the Structure of an Audit Record

Cloud Audit Logs typically stores audit details in the protoPayload field using the AuditLog data type. A record can contain the following important fields:

| Field | Investigative Meaning |
| --- | --- |
| serviceName | Google Cloud service receiving the request |
| methodName | API method invoked |
| resourceName | Target resource affected |
| authenticationInfo | Identity or authentication details attached to the request |
| authorizationInfo | Permission check details for the resource |
| requestMetadata | Request context, potentially including caller origin info |
| status | Outcome or error of the operation |
| request and response | Partial request or response contents if logged by the service |
| timestamp | Time the record was generated |

Not every service provides every field or the same level of detail. Some values may be omitted, redacted, or unlogged for security reasons. Audit logs are not full copies of business data; do not assume object contents, data rows, or secrets will appear in the log record.

During investigation, pair principal with methodName, resourceName, status, and timestamp. Across multiple projects, verify whether logs reside in the resource project, a logging project, or a centralized destination routed by Log Router.

## 5. Querying Cloud Audit Logs in Logs Explorer

Logs Explorer lets you filter logs using Logging query language. You can start with the log ID, then narrow down by service, API method, principal, or resource.

Find administrative actions:

~~~text
log_id("cloudaudit.googleapis.com/activity")
protoPayload.serviceName="storage.googleapis.com"
~~~

Find object reads via Data Access:

~~~text
log_id("cloudaudit.googleapis.com/data_access")
protoPayload.serviceName="storage.googleapis.com"
protoPayload.methodName="storage.objects.get"
~~~

Find object writes:

~~~text
log_id("cloudaudit.googleapis.com/data_access")
protoPayload.serviceName="storage.googleapis.com"
protoPayload.methodName="storage.objects.create"
~~~

Find actions by a specific identity:

~~~text
log_id("cloudaudit.googleapis.com/data_access")
protoPayload.authenticationInfo.principalEmail="app-reader@example.iam.gserviceaccount.com"
~~~

Find requests denied by policy:

~~~text
log_id("cloudaudit.googleapis.com/policy")
protoPayload.status.code=7
~~~

These queries are starting points. Method names, resource types, and principal fields vary by service and identity type. When no results appear, widen filters on time and project before concluding an event was not logged.

A workflow for investigating an unauthorized change can proceed as follows:

1. Search Admin Activity around the time the change was detected.
2. Filter by serviceName and resourceName to identify the affected resource.
3. Inspect authenticationInfo to identify the calling principal.
4. Read methodName, authorizationInfo, and status to understand the action taken and its outcome.
5. Expand to Data Access to check whether data was read or written after the change.
6. Correlate timestamps with application logs, Cloud Monitoring alerts, and change management systems.

## 6. Log Reading and Log Management Permissions

Logs can contain identities, resource names, caller addresses, and sensitive operational metadata. Therefore, log viewing permissions must also follow the principle of least privilege.

| IAM Role | Primary Permission Scope | Suitable Audience |
| --- | --- | --- |
| roles/logging.viewer | Read most logs, excluding Data Access audit logs | Operations teams needing to inspect standard logs |
| roles/logging.privateLogViewer | Read private logs, including Data Access audit logs | Security or audit teams authorized to inspect data access activity |
| roles/logging.configWriter | Create and manage log routing configs such as sinks | Platform teams managing log flows |
| roles/logging.admin | Broad Cloud Logging administrative permissions | Authorized logging administration team |

Do not grant Cloud Logging admin permissions to everyone simply because they need to view some logs. Grant roles/logging.viewer to support teams, and grant roles/logging.privateLogViewer separately to teams authorized to investigate Data Access. Log reading, sink creation, and IAM policy modification permissions should be separated by responsibility.

Beyond IAM roles, protect the central log-receiving project, log buckets, sinks, and export destinations. Anyone with read permissions on a destination BigQuery dataset or Cloud Storage bucket can access exported log copies, even if they lack permission to view the original logs in the source project.

## 7. Storing, Routing, and Centralizing Logs

Cloud Logging Log Router ingests logs and routes them to log buckets or supported destinations such as BigQuery, Cloud Storage, and Pub/Sub. Sinks can be placed at the project, folder, or organization level. For multi-project organizations, aggregated sinks at the organization or folder level centralize logs for cross-project monitoring and auditing.

A common architecture includes:

- Workload projects generate Audit Logs when users or services call APIs.
- Folder- or organization-level sinks select required logs and send them to a security project.
- The security project stores logs in a dedicated log bucket with appropriate access controls and retention periods.
- A SIEM or analytics pipeline consumes logs from BigQuery or Pub/Sub when additional processing is needed.

When creating a centralized sink, ensure the sink's service identity has write permission to the destination. For sinks covering child resources, enable the option to include logs from child projects matching the intended scope. Test sink filters carefully to avoid accidentally omitting Data Access or Policy Denied logs required for audits.

Default log buckets have different retention periods: the _Required bucket retains mandatory log types such as Admin Activity and System Event for 400 days; the _Default bucket has a 30-day default retention period that can be adjusted per configuration, policy, and service limits. Data Access and other logs may route to _Default or organization-configured destinations. Confirm the actual storage location and retention policy for each log category before making archival commitments.

If regulatory or internal policy mandates longer log retention, configure appropriate retention or export logs to separately managed storage. Protect exported copies, restrict deletion rights, and control who can modify retention. Keeping logs longer does not automatically make them trustworthy if unauthorized users can still alter routing configurations or delete copies.

## 8. Cost and Quality of Audit Data

Data Access logs can grow rapidly when applications frequently read data or query tables. Costs depend on log volume collected, stored, and routed under Cloud Logging configurations as well as destination services. Before enabling organization-wide, estimate traffic, pilot on a representative project, and monitor actual usage.

Controls include:

1. Enable Data Access selectively for services and data scopes with clear audit requirements.
2. Use log buckets, sinks, and retention aligned with investigative and archival needs.
3. Monitor log volume by project, log type, and service to detect sudden spikes.
4. Avoid excluding mandatory events merely to save cost; if filtering is needed, evaluate the impact on auditability.
5. Restrict read access to private logs and administrative access to routing configurations.

A strong audit setup balances three demands: sufficient data for investigation, protection of log data from unauthorized access, and predictable costs. Never optimize costs by dropping events the organization relies on to detect unauthorized access or prove compliance.

## 9. Real-World Scenario: Investigating Anomalous Data Reads

Suppose the security team detects an application's service account reading a large number of objects in a bucket containing customer data outside normal operational hours. The team needs to determine what activity occurred and whether any prior permission changes took place.

**Step 1 – Identify identity and timeframe.** Use Cloud Storage Data Access logs to filter by principalEmail, bucket, and time range. Check methodName to distinguish object reads from list operations or metadata changes.

**Step 2 – Determine data scope.** Use resourceName and service-provided resource fields to identify the affected objects or buckets. Compare against the data scope the application is authorized to process.

**Step 3 – Check permission changes.** Search Admin Activity during and before the same timeframe to see whether IAM policies, service accounts, or bucket configurations were modified.

**Step 4 – Check blocked requests.** Search Policy Denied logs for denied access attempts or privilege escalation probes. Combine with application logs and Cloud Monitoring alerts to establish the sequence of events.

**Step 5 – Preserve evidence and remediate.** Export relevant logs to a protected investigation store, record the filters and time ranges used, and coordinate with workload owners to evaluate credentials and revoke permissions if needed.

This scenario is only possible if Data Access logging was already enabled and logs were retained long enough. If DATA_READ was not collected prior to the incident, Admin Activity may still show who modified permissions, but will not necessarily prove who read specific objects.

## 10. Checklist for Designing Cloud Audit Logs

Before promoting a project or workload to production, verify:

- Admin Activity and System Event are retained under Google Cloud's default mechanisms.
- Services holding sensitive data have been assessed and configured with appropriate Data Access logging.
- ADMIN_READ is clearly distinguished from Admin Activity, DATA_READ, and DATA_WRITE.
- Any exemptedMembers entries have documented justification, an owner, and explicit approval.
- Operations, security, and audit teams have appropriately scoped log read access; Data Access logs are visible only to authorized principals.
- Centralized sinks and log buckets have proper filters, writer permissions, retention, and storage locations.
- Key Logs Explorer queries have been tested against real data.
- Investigation procedures combine Audit Logs with application logs, alerts, and change management records.
- Cost and volume of Data Access logs are monitored periodically.

Cloud Audit Logs forms the evidentiary foundation for operations on Google Cloud. By choosing the right log categories for each audit question, enabling Data Access where needed, protecting log read access, and routing data to suitable storage, organizations can trace changes and data access more reliably while keeping operational costs under control.
