# Logs Explorer and Logging Query Language

Cloud Logging collects logs from Google Cloud services, applications, and infrastructure connected by an organization. When a request fails, a workload restarts, or an unexpected IAM change appears, operators need to locate the exact records, narrow down by resource and time range, and trace the identity, request, or related trace. Logs Explorer provides the interface to perform that work; Logging query language (LQL) allows expressing precise filters that can be saved and reused.

Within **CLOUD_PROVIDERS_GCP**, log-reading skills connect directly to operating projects, IAM, VPC, Compute Engine, GKE, Cloud Run, storage, and databases. Logs serve as evidence to understand how these services behave, identify root causes of errors, inspect configuration changes, monitor reliability, and support cost control.

After this lesson, learners will be able to:

- Select the right project, resource scope, log view, and time range in Logs Explorer.
- Recognize the key fields of a LogEntry and distinguish between text, JSON, and audit logs.
- Write LQL queries using comparisons, logical conditions, string searches, and regular expressions.
- Create filters for Compute Engine, GKE, Cloud Run, Cloud Audit Logs, and specific requests.
- Use query results to trace errors, the identity performing an action, and request traces.
- Save useful queries, share them with the proper scope, and convert important signals into metrics or alerts.

## 1. Where Does Logs Explorer Fit in Cloud Logging?

Cloud Logging ingests logs from multiple sources, normalizes them into log entries, and stores them according to log bucket and log view configurations. Logs Explorer is the interface for exploring and querying the entries a user is authorized to view. It is neither the only place where logs are generated nor a guarantee that every type of event has been recorded.

An overview flow:

~~~mermaid
flowchart LR
    A[VM, GKE, Cloud Run, Cloud SQL] --> C[Cloud Logging]
    B[Cloud Audit Logs and applications] --> C
    C --> D[Log Router]
    D --> E[Log buckets]
    D --> F[Log sinks and other storage destinations]
    E --> G[Logs Explorer]
    G --> H[LQL query]
    G --> I[Investigation and correlation]
    I --> J[Metrics, alerts, and incident handling]
~~~

Key concepts to distinguish:

- **Log entry** is an event record. It contains a timestamp, originating resource, severity level, and a payload with specific details.
- **Log Router** receives logs and applies inclusion filters/exclusion filters to decide which bucket stores them or which sink receives them.
- **Log bucket** is the storage location in Cloud Logging, configured with location and retention duration.
- **Log view** is a scoped view restricting a subset of logs within a bucket; access permissions to a view can be granted separately.
- **Logs Explorer** queries log entries within the scope the user has selected and is authorized to access.

If an event does not appear, the reason may be that the application has not logged it, the service has not enabled the required audit log type, Log Router excluded the entry, the log exceeded its retention period, the query scope is wrong, or the user lacks permissions. Rewriting a query cannot recover a log that was never collected.

### 1.1. Logs Explorer and Logs Analytics

Two tools serve related purposes but use different languages:

| Tool | Language | Best Suited For |
|---|---|---|
| Logs Explorer | Logging query language (LQL) | Finding entries, filtering by resource, severity, payload, time, and investigating individual events |
| Logs Analytics | SQL on analytics-enabled log buckets | Aggregating, grouping, computing, and analyzing log sets in tabular form |

For example, LQL uses `severity >= ERROR` to filter entries at error level or higher. In Logs Analytics, users write SQL statements with `SELECT`, `WHERE`, `GROUP BY`, and aggregate functions. Do not paste an LQL query into the SQL editor or vice versa.

## 2. Getting Started with the Logs Explorer Interface

The names and placement of some controls may change across UI versions, but the log-searching workflow still consists of the same core steps.

### 2.1. Selecting Scope and Time Range

1. Open Logs Explorer in the Google Cloud Console.
2. Select the project, resource scope, or log view matching where the logs are stored.
3. Choose the time range to investigate. You can use a preset range or specify custom start/end timestamps.
4. Identify the service and resource type emitting the logs, such as `gce_instance`, `k8s_container`, or `cloud_run_revision`.
5. Run the query and inspect the histogram and returned entry list.

The UI time range is an important boundary on results. If the query also contains a `timestamp` condition, that condition combines with the currently selected time range. When results are empty, check both places. Timestamps in log entries are typically expressed in UTC; convert time zones when correlating with user-reported error times.

### 2.2. Query Builder and Query Language

**Query Builder** is suitable when getting started or adding conditions via available fields. Users choose resource, log name, severity, and certain attributes; the UI generates the corresponding filter.

**Query language** is suitable when you need nested conditions, payload searches, regular expressions, audit log queries, or reusable long filters. You can switch from visual filters to the LQL query to inspect the generated syntax, then edit it directly.

When an entry is expanded, inspect resource, timestamp, severity, and payload. For structured logs, expand `jsonPayload` to inspect actual field names; for audit logs, inspect `protoPayload`; for text logs, inspect `textPayload`. You can use UI actions to add a field directly to the query if you want to filter further by an observed value.

### 2.3. Reading Results

- **Histogram** shows entry density over time. A sudden spike may coincide with a release or incident.
- **Log list** shows matching entries, typically ordered by timestamp.
- **Entry details** let you inspect full fields, resource labels, and payloads.
- **Trace link** if present lets you jump from the log to related spans in Cloud Trace.
- **Resource fields** show which resource type emitted the log and which project, cluster, instance, service, or namespace it belongs to.

Do not conclude a system is error-free just because no `ERROR` entries appear. An application might log errors at `WARNING`, use a custom payload, or fail to log when a request fails. Understand how the application emits logs before choosing a filter.

## 3. Structure of a LogEntry

Cloud Logging represents events as a `LogEntry`. Common fields:

| Field | Meaning | When to Use |
|---|---|---|
| `logName` | Log name, including project and log ID | Filter only audit logs, application logs, or a specific log |
| `resource.type` | Monitored resource type | Distinguish VMs, containers, Cloud Run, databases |
| `resource.labels` | Resource identifying labels | Filter by instance, cluster, namespace, service, or location |
| `timestamp` | Time when the event occurred | Investigate according to actual event time |
| `receiveTimestamp` | Time when Cloud Logging received the entry | Compare log ingestion delay |
| `severity` | Severity level | Focus on WARNING, ERROR, or higher |
| `insertId` | Entry identifier within a log | Cross-reference or deduplicate in certain pipelines |
| `textPayload` | Plain text content | Search messages written by an application or OS |
| `jsonPayload` | Structured JSON content | Filter by request ID, status code, module name, or custom fields |
| `protoPayload` | Protobuf content, common in audit logs | Find principal, method, resource, and operation status |
| `labels` | Labels attached by the system or log emitter | Group or filter by additional context |
| `httpRequest` | HTTP request info if present | Search method, URL, status, or latency |
| `trace`, `spanId` | Trace and span identifiers | Link logs to distributed requests |
| `operation` | Info grouping entries belonging to one operation | Track multi-step operations |

`logName` typically takes the form:

~~~text
projects/PROJECT_ID/logs/LOG_ID
~~~

In field paths, segments are separated by dots. For example, `resource.labels.cluster_name` or `jsonPayload.requestId`. Field names must match the actual entry structure exactly; do not guess JSON field names from message text.

### 3.1. Three Common Payload Types

**Text payload** stores a string:

~~~text
textPayload: "upstream connection timed out"
~~~

**JSON payload** stores structured data:

~~~json
{
  "severity": "ERROR",
  "message": "payment request failed",
  "requestId": "req-82f1",
  "httpStatus": 502,
  "durationMs": 3100
}
~~~

In Logs Explorer, these fields can be queried as `jsonPayload.requestId`, `jsonPayload.httpStatus`, and `jsonPayload.durationMs`.

**Proto payload** appears in protobuf-structured logs, particularly Cloud Audit Logs. For example, `protoPayload.authenticationInfo.principalEmail` can reveal the principal that performed an operation.

### 3.2. Severity

Standard severity levels in ascending order:

`DEFAULT`, `DEBUG`, `INFO`, `NOTICE`, `WARNING`, `ERROR`, `CRITICAL`, `ALERT`, `EMERGENCY`.

The condition `severity >= ERROR` matches ERROR and higher severities. Not all applications assign severity consistently; if an application writes `"ERROR"` inside `jsonPayload.message` without setting the `severity` field, the condition above may not return that entry.

## 4. Basic Syntax of Logging Query Language

LQL is an expression language used to select log entries. A query typically combines multiple conditions on resource, log name, time, severity, and payload.

Example:

~~~text
resource.type = "cloud_run_revision"
resource.labels.service_name = "orders-api"
severity >= ERROR
timestamp >= "2026-11-19T00:00:00Z"
~~~

The conditions above are combined with logical AND: an entry must satisfy all conditions. You can write `AND` explicitly to improve readability in complex expressions.

### 4.1. Comparisons and Searching

| Operator | Meaning | Example |
|---|---|---|
| `=` | Equals | `severity = ERROR` |
| `!=` | Not equals | `resource.type != "gce_instance"` |
| `>` / `>=` | Greater than / greater than or equal to | `httpRequest.status >= 500` |
| `<` / `<=` | Less than / less than or equal to | `jsonPayload.durationMs < 100` |
| `:` | Checks if string/value contains matching content | `textPayload : "timeout"` |
| `=~` | Matches regular expression | `textPayload =~ "timeout|deadline"` |
| `!~` | Does not match regular expression | `textPayload !~ "healthcheck"` |

For numeric fields, use numeric comparisons instead of substring searches. For example, `httpRequest.status >= 500` expresses intent far more accurately than searching for the text `"500"` across the entire payload.

### 4.2. Combining Logical Conditions

- `AND`: all conditions must be true.
- `OR`: at least one branch must be true.
- `NOT`: negates a condition.
- Parentheses `(...)`: clarify condition grouping and evaluation order.

Example fetching severe errors from two services:

~~~text
severity >= ERROR
(
  resource.labels.service_name = "orders-api"
  OR resource.labels.service_name = "payments-api"
)
~~~

Example excluding health check logs:

~~~text
resource.type = "cloud_run_revision"
severity >= WARNING
NOT textPayload : "healthcheck"
~~~

When combining AND and OR, always use parentheses so readers understand the intent and to avoid queries broader than intended.

### 4.3. Filtering Nested Fields and Checking Existence

Use field paths to drill into payloads:

~~~text
jsonPayload.requestId = "req-82f1"
jsonPayload.httpStatus >= 500
protoPayload.authenticationInfo.principalEmail = "deployer@example.com"
~~~

You can check whether a field exists using the `:*` operator:

~~~text
jsonPayload.stackTrace:*
~~~

This is useful when looking for entries that contain a stack trace field without needing to know its content beforehand.

### 4.4. Full-Text Search and Regular Expressions

`SEARCH("...")` searches for a string across searchable fields of an entry. This is a quick way to probe keywords when you do not yet know whether a message lives in `textPayload`, `jsonPayload`, or another field:

~~~text
resource.type = "k8s_container"
SEARCH("connection refused")
~~~

Once you know the field, filter that field directly for clearer and more targeted queries:

~~~text
jsonPayload.message : "connection refused"
~~~

Operators `=~` and `!~` use RE2 regular expressions. Example:

~~~text
textPayload =~ "timeout|deadline exceeded"
~~~

RE2 does not support every feature found in other regex engines. If a complex expression does not behave as expected, simplify the pattern or check RE2 syntax.

### 4.5. Filtering by Time and Log ID

You can filter time directly in the query:

~~~text
timestamp >= "2026-11-19T08:00:00Z"
timestamp < "2026-11-19T09:00:00Z"
~~~

These two conditions define a half-open interval, convenient when slicing logs by hour. Use RFC 3339/ISO 8601 format with an explicit time zone; `Z` denotes UTC.

The `log_id()` function filters by log ID:

~~~text
log_id("cloudaudit.googleapis.com/activity")
~~~

This can be combined with payload conditions to locate a specific administrative action. The example above specifies Admin Activity logs; the log ID name must match the audit log category you want to inspect.

## 5. Practical Query Patterns by GCP Service

The patterns below are starting points. Replace project, service, cluster, namespace, instance, and field names with actual values from the environment under investigation.

### 5.1. Cloud Run: Errors for a Service

~~~text
resource.type = "cloud_run_revision"
resource.labels.service_name = "orders-api"
severity >= ERROR
~~~

To find HTTP requests returning 5xx:

~~~text
resource.type = "cloud_run_revision"
resource.labels.service_name = "orders-api"
httpRequest.status >= 500
~~~

Application logs and request logs can have different structures. If querying `httpRequest.status` returns no results, open a sample entry to check whether the status code is stored in `httpRequest`, `jsonPayload`, or a text message.

### 5.2. GKE: Namespace and Container Logs

~~~text
resource.type = "k8s_container"
resource.labels.namespace_name = "production"
resource.labels.container_name = "checkout"
severity >= WARNING
~~~

Searching for errors with specific content:

~~~text
resource.type = "k8s_container"
resource.labels.namespace_name = "production"
SEARCH("connection refused")
~~~

When a pod restarts repeatedly, application logs can reveal the cause before the container exits. Combine container logs with Kubernetes events or restart count metrics to distinguish application crashes, resource exhaustion, probe failures, and node issues.

### 5.3. Compute Engine: Logs by Instance

~~~text
resource.type = "gce_instance"
resource.labels.instance_id = "INSTANCE_ID"
severity >= ERROR
~~~

If the instance ID is unknown, filter by project and zone or use available resource labels from an entry. Operating system logs can be shipped by Ops Agent; verify that the agent and collection pipeline are installed and configured.

### 5.4. Cloud Audit Logs: Who Changed IAM?

~~~text
log_id("cloudaudit.googleapis.com/activity")
protoPayload.methodName : "SetIamPolicy"
~~~

To find actions performed by a principal:

~~~text
log_id("cloudaudit.googleapis.com/activity")
protoPayload.authenticationInfo.principalEmail = "deployer@example.com"
~~~

Once an entry is found, also check `protoPayload.serviceName`, `protoPayload.methodName`, `protoPayload.resourceName`, `protoPayload.request`, and `protoPayload.status`. Some request fields may be redacted or omitted according to data protection policies.

### 5.5. Cloud Audit Logs: Denied Requests

~~~text
log_id("cloudaudit.googleapis.com/policy")
protoPayload.status.code = 7
~~~

Status code `7` corresponds to `PERMISSION_DENIED` in standard Google APIs status codes. Read `principalEmail`, `resourceName`, `methodName`, and request details to determine which principal was denied, which resource they acted on, and via which API. Not every permission error appears under the same log ID; broaden the scope if the service writes events to another log.

### 5.6. Cloud Audit Logs: Data Access

~~~text
log_id("cloudaudit.googleapis.com/data_access")
protoPayload.authenticationInfo.principalEmail = "analyst@example.com"
~~~

Data Access audit logs record certain data read/write operations, though many of these logs must be explicitly enabled per service and organizational configuration. If no entries appear, verify that the audit log category is enabled, check its scope, confirm permission to view private logs, and verify retention.

### 5.7. Finding Requests by Request ID or Trace

If the application writes `requestId` into JSON payload:

~~~text
jsonPayload.requestId = "req-82f1"
~~~

If logs include a trace ID:

~~~text
trace = "projects/PROJECT_ID/traces/TRACE_ID"
~~~

Traces connect logs and spans of a request traveling across multiple services. When a request passes through a gateway, Cloud Run, GKE, and a database, a consistent trace ID reduces search time. Linking only works when applications and tracing libraries propagate context properly.

## 6. Incident Investigation Workflow with Logs Explorer

Suppose users report that the payment API occasionally returns HTTP 502 after a release. You can follow this workflow:

1. **Lock down the scope:** confirm the production project, service name, region, and time window when errors occurred. Select the right resource scope and log view.
2. **Filter the primary signal:** start with resource type, service name, and `httpRequest.status >= 500`.
3. **Pinpoint timing:** inspect the histogram to see whether errors cluster in a short burst or persist over time. Compare against release timestamps.
4. **Open a representative entry:** read timestamp, revision, request URL, latency, trace, and payload. Note the request ID or trace ID.
5. **Follow the request:** search for other logs sharing the same request ID or trace ID across the gateway, downstream services, and database.
6. **Check for changes:** query Admin Activity around that time for IAM changes, service config updates, networking changes, or dependent resource changes.
7. **Correlate with metrics:** inspect request count, error rate, latency, CPU, memory, instance count, and database connections in Cloud Monitoring.
8. **Document findings:** record the query, timestamps, resources, trace, hypothesis, evidence, and remediation actions.

Starting query for this example:

~~~text
resource.type = "cloud_run_revision"
resource.labels.service_name = "payments-api"
httpRequest.status >= 500
timestamp >= "2026-11-19T08:00:00Z"
timestamp < "2026-11-19T09:00:00Z"
~~~

If logs show errors occurring only on the new revision, compare logs between the old and new revisions. If all revisions fail together, check dependencies such as database, secrets, DNS, and networking. If only a subset of requests fails, use request ID and trace to isolate the diverging execution path.

Logs provide evidence of recorded events; they do not prove root cause on their own. Cross-check logs with metrics, traces, deployment changes, and dependency health before concluding.

## 7. Saving, Reusing, and Sharing Queries

A good query can become a reusable operational tool. In Logs Explorer, users can save queries to avoid rewriting long filters.

When saving a query:

- Name it after its purpose, such as `prod-cloud-run-5xx` or `audit-iam-policy-changes`.
- Document the intended project/resource, time range, and meaning of the conditions.
- Use clear placeholders for service, namespace, or principal values that need substitution.
- Re-verify the query after switching projects or log views; a query valid in one project may yield no results in another.
- If sharing a query, confirm recipients have permission to view the corresponding logs and log view. Sharing a query does not grant read access to data.

Avoid saving multiple duplicate queries with indistinguishable names. A small set of queries with clear owners and descriptions is far more useful than a long unmaintained list.

## 8. From Queries to Metrics and Alerts

Logs Explorer is suited for finding and understanding entries. When you need to track continuous trends or notify on conditions, move the relevant signal into Cloud Monitoring.

- **Log-based counter metric** counts entries matching a filter, such as occurrences of a specific error.
- **Log-based distribution metric** extracts numeric values from payloads to analyze distributions, such as application-logged processing durations.
- **Alerting policy** periodically evaluates metrics or log conditions and notifies the on-call channel.
- **Dashboard** combines metrics, charts, and operational info to monitor a service.

For example, a 5xx log query helps locate specific entries. To track error rate over time, you need an appropriate metric and total requests as the denominator; counting errors alone without knowing total traffic can distort judgment when traffic surges or drops sharply.

When creating a log-based metric, choose a stable filter and avoid embedding unique request IDs into metric labels, as high cardinality makes metrics hard to manage and increases cost. Use metrics for aggregate trends; use log entries to investigate individual events.

## 9. Access Permissions and Protecting Log Data

Logs Explorer only displays logs that the principal is authorized to view within the selected scope. Common roles:

| Role | Purpose |
|---|---|
| `roles/logging.viewer` | View standard logs within the granted scope |
| `roles/logging.privateLogViewer` | View additional private logs, including many Data Access audit logs |
| `roles/logging.viewAccessor` | Access a granted log view |
| `roles/logging.admin` | Administer Cloud Logging configuration; broad permissions, restrict assignment |

The actual role required also depends on how the organization grants permissions, log scopes, and services. Prefer granting access at the appropriate project or log view scope; do not grant Logging admin roles just so users can read logs.

Logs may contain emails, IPs, tokens, request metadata, or personal data. Therefore:

- Never write passwords, access tokens, private keys, or unnecessary sensitive data into logs.
- Mask or strip sensitive fields before writing logs.
- Restrict log readers and retention periods according to business/legal requirements.
- Control who can create sinks, modify exclusion filters, or delete log buckets.
- Review log sinks to know which external projects, buckets, or systems receive data.
- Do not paste raw logs containing sensitive data into tickets or public discussions.

## 10. Common Querying Mistakes

**No results returned.** Check project/resource scope, log view, time range, resource type, and field names. Then verify whether the log was generated, routed into the bucket being viewed, and is still within its retention window.

**Filtering `severity >= ERROR` shows no errors.** The application might write error text in `jsonPayload.message` without setting severity. Open a sample entry and inspect actual fields.

**Wrong field name.** `jsonPayload.statusCode` differs from `jsonPayload.status_code`. Take the exact field name from a sample entry or the application schema.

**Wrong operator for data type.** Compare numbers with `>=` instead of substring matching; use parentheses when combining OR; check regex against RE2.

**Query too broad.** Starting with `SEARCH("error")` across all resources can return noisy results. Narrow time range, resource type, and service first.

**Missing Data Access audit logs.** Check audit configuration, `roles/logging.privateLogViewer` permission, log view, resource scope, and retention.

**Missing workload logs.** Verify the application writes to stdout/stderr or uses an appropriate logging client; check agent/collector, write permissions, and routing config.

**Confusing Logs Explorer with Logs Analytics.** LQL filters log entries in Explorer; SQL analyzes tables in Logs Analytics. Pick the right tool before writing your query.

**Concluding from a single entry.** One log may lack context or arrive late. Correlate multiple entries from the same request alongside traces, metrics, and audit events before drawing conclusions.

## 11. Practice: Investigating IAM Changes and API Errors

### Scenario A: Finding Who Changed IAM Permissions

A production service suddenly loses permission to read a bucket. The operations team needs to determine whether any IAM change occurred near when failures began.

1. Select the project containing the bucket or the project where the policy was modified.
2. Open Logs Explorer and choose a time window spanning before and after the failure began.
3. Run the query:

~~~text
log_id("cloudaudit.googleapis.com/activity")
protoPayload.methodName : "SetIamPolicy"
~~~

4. Open matching entries and note `principalEmail`, `methodName`, `resourceName`, `timestamp`, and `status`.
5. Inspect request/policy delta if provided by the entry; compare against approved changes.
6. If an unauthorized change is identified, execute incident response and restore the policy through an authorized principal.

### Scenario B: Finding Why an API Returns 5xx

An API on Cloud Run shows an elevated error rate after a deployment.

1. Filter `cloud_run_revision`, service name, and `httpRequest.status >= 500`.
2. Compare revisions across the error entries.
3. Grab the trace or request ID of a representative request.
4. Search for related logs in the same trace across downstream services.
5. Correlate latency, database connections, secret access, and deployment timestamps.
6. Identify the change correlated with the errors, test a fix, and monitor the error rate afterward.

Both scenarios show that LQL does more than search error messages. When filtering accurately by resource, principal, method, and time, logs serve as evidence to verify changes and follow request paths.

## 12. Checklist for Sustainable Operational Querying

### Before Running

- [ ] Selected the correct project, resource scope, or log view.
- [ ] Time range is appropriate and time zone has been accounted for.
- [ ] Identified the target resource type and log category.
- [ ] Verified permission to view the corresponding log category.

### When Writing LQL

- [ ] Narrowed by resource and time range first.
- [ ] Used exact field names verified from a sample entry.
- [ ] Used operators matching the field data type.
- [ ] Used parentheses for complex AND/OR expressions.
- [ ] Verified regex follows RE2 and tested against sample entries.
- [ ] Restricted full-text searches wherever possible.

### After Getting Results

- [ ] Opened entries and read full payloads.
- [ ] Checked principal, resource, timestamp, and trace/request ID as needed.
- [ ] Cross-checked against related metrics, traces, or audit events.
- [ ] Saved useful queries with clear names and descriptions.
- [ ] Ensured alerts/metrics have owners and clear remediation steps.
- [ ] Ensured logs are not shared beyond necessary scope.

## 13. Official References

- [Logs Explorer overview and interface](https://cloud.google.com/logging/docs/view/logs-explorer-interface)
- [Logging query language](https://cloud.google.com/logging/docs/view/logging-query-language)
- [Structured logging](https://cloud.google.com/logging/docs/structured-logging)
- [Cloud Audit Logs overview](https://cloud.google.com/logging/docs/audit)
- [Routing and storage overview](https://cloud.google.com/logging/docs/routing/overview)
- [Log buckets and views](https://cloud.google.com/logging/docs/buckets)
- [Cloud Logging access control](https://cloud.google.com/logging/docs/access-control)
- [Logs Analytics overview](https://cloud.google.com/logging/docs/analyze)
- [Log-based metrics](https://cloud.google.com/logging/docs/logs-based-metrics)

When investigating in a real environment, start from a sample entry to confirm the resource type and payload structure, then expand your query step by step. A targeted, explainable, and reusable query helps operations teams uncover evidence faster, reduce noise, and make data-driven decisions.
