# Log Analytics and Log Analysis

## 1. Why Is Log Analysis Necessary?

A Google Cloud application generates many kinds of events throughout its operational lifecycle: requests arriving at services, errors in source code, configuration changes, IAM operations, database accesses, and VM or container events. Each log entry records an event at a point in time. When collected and analyzed properly, these events help teams answer critical operational questions:

- When did errors start appearing, and which service or version are they concentrated in?
- Did the failed request rate rise after a deployment?
- Which resource generates the most alerts?
- Who modified IAM, firewall rules, or storage configurations?
- Which components did a slow request pass through, and is there a corresponding trace?
- In which region and for how long must logs be stored to satisfy operational, investigative, and compliance requirements?

In the `CLOUD_PROVIDERS_GCP` module, **Log Analytics and log analysis** connect infrastructure services with system observability. Learners need to know how to collect logs from Compute Engine, GKE, Cloud Run, storage services, and databases; route logs to appropriate storage; search for events; use SQL to aggregate data; and govern access permissions, retention periods, and costs.

Google Cloud provides **Cloud Logging** to ingest, route, store, and query logs. In current documentation and Console interfaces, the SQL-based log analysis interface is called **Observability Analytics**. The name **Log Analytics** still appears in many documents, common usage, and governance contexts. In this lesson, Log Analytics refers to the SQL log analysis capability within Cloud Logging; when working in the Console, look for the Observability Analytics page.

## 2. Log Processing Architecture in Cloud Logging

A log stream typically passes through the following components:

1. **Sources:** Google Cloud services, applications, VMs, containers, Cloud Audit Logs, or external systems.
2. **Cloud Logging API and Log Router:** ingests log entries and applies sinks and exclusions to decide where to store or forward them.
3. **Log bucket:** stores logs according to region, retention period, and encryption configuration.
4. **Log view:** provides a filtered view over a bucket's data and supports access control.
5. **Logs Explorer:** searches and investigates log entries using Logging query language.
6. **Observability Analytics:** analyzes logs with SQL, aggregates trends, creates charts, and combines logs with traces.
7. **External analytics destinations:** BigQuery, Cloud Storage, or Pub/Sub when further storage, integration, or processing is needed.

~~~mermaid
flowchart TD
    A[Cloud Run / GKE / Compute Engine] --> D[Cloud Logging API]
    B[Cloud Audit Logs / Google Cloud services] --> D
    C[Applications / Ops Agent / external systems] --> D
    D --> E[Log Router]
    E --> F[Log bucket]
    E --> G[Sink to BigQuery / Cloud Storage / Pub/Sub / another project]
    E --> H[Exclusion]
    F --> I[Log views]
    I --> J[Logs Explorer]
    I --> K[Observability Analytics / SQL]
    K --> L[Charts and custom dashboards]
    K --> M[Linked BigQuery dataset]
~~~

Log Router processes logs written to the Cloud Logging API. A **sink** is a routing rule with a filter and a destination. Sinks can be configured at the project, folder, or organization level depending on resource type and governance scope. This lets organizations consolidate logs from multiple projects into central storage, forward a subset of logs to BigQuery or Pub/Sub, or separate security logs from routine application logs.

A sink can have **exclusions** to skip log entries that do not need to be sent to that sink's destination. Exclusions must be designed cautiously: dropping audit logs or critical events can deprive teams of investigative data. Explicitly verify which logs are excluded, at what scope, and whether those logs are still preserved in another bucket or destination.

### Common Log Sources

| Source | Examples | Analytical Value |
|---|---|---|
| Cloud Run | Request logs, container stdout/stderr, application errors | Track HTTP status codes, revisions, errors, and deployment timing |
| Compute Engine | System logs, applications, Ops Agent, startup scripts | Investigate VM failures, machine resources, and host-level services |
| GKE | Container logs, node logs, Kubernetes events, control-plane audit logs | Track pods, deployments, nodes, and cluster management activity |
| Cloud SQL | Database logs, connections, errors, and configured audit logs | Detect anomalous connections, query errors, and operational issues |
| Cloud Storage | Audit logs and recorded access events | Investigate bucket access permissions and object operations |
| Cloud Audit Logs | Admin Activity, Data Access, System Event, Policy Denied | Trace administrative actions, data access, and policy decisions |
| Custom applications | JSON logs, exceptions, request IDs, trace IDs | Connect business events with requests and traces |

For VMs, **Ops Agent** can collect OS logs and application logs as configured. For containers and managed services, many log types are integrated directly or collected from stdout/stderr. Custom applications can emit structured logs so Cloud Logging parses fields such as severity, request, trace, and payload.

## 3. Structure of a Log Entry

A log entry can contain many fields. During analysis, understand the meaning of key fields before writing filters or queries.

| Field | Meaning | How It Is Used |
|---|---|---|
| `logName` / `log_name` | Log name and path within the project | Distinguish application logs, audit logs, or service-specific logs |
| `timestamp` | Time the event occurred according to the source | Build timelines and filter by time |
| `receiveTimestamp` / `receive_timestamp` | Time Cloud Logging received the log | Analyze delay between emission and ingestion |
| `severity` | Event severity level | Filter `WARNING`, `ERROR`, `CRITICAL`, and other levels |
| `resource` | Resource type and identifying resource labels | Group logs by VM, container, project, zone, or service |
| `textPayload` / `text_payload` | Plain text content | Read text-based messages |
| `jsonPayload` / `json_payload` | Structured JSON content | Extract fields such as `request_id`, `status`, `user_id` |
| `protoPayload` / `proto_payload` | Protocol Buffers payload, common in audit logs | Analyze typed method, principal, and event details |
| `labels` | Additional labels provided by services or applications | Group by environment, component, or custom attributes |
| `httpRequest` / `http_request` | HTTP request info if present | Analyze method, URL, status, and latency |
| `trace`, `spanId` / `span_id` | Trace and span identifiers | Link logs with distributed traces |
| `insertId` / `insert_id` | Log entry identifier supplied by source | Help detect duplicate entries in certain contexts |

Field names in the API structure typically use camelCase; the SQL schema in Observability Analytics exposes snake_case names. For example, `jsonPayload` becomes `json_payload`, and `httpRequest` becomes `http_request`.

Example of a structured JSON log entry:

~~~json
{
  "severity": "ERROR",
  "message": "Payment request failed",
  "service": "checkout",
  "environment": "production",
  "request_id": "req-7f31",
  "http_status": 503,
  "trace_id": "projects/demo-project/traces/4bf92f3577b34da6a3ce929d0e0e4736",
  "timestamp": "2026-11-19T07:30:00Z"
}
~~~

This example illustrates a payload produced by an application. When writing actual logs, use the exact format supported by the Cloud Logging library or API; custom fields go into `jsonPayload` while metadata such as severity, timestamp, and trace can be mapped to top-level `LogEntry` fields.

### Choosing Severity Consistently

Commonly used severity levels include `DEFAULT`, `DEBUG`, `INFO`, `NOTICE`, `WARNING`, `ERROR`, `CRITICAL`, `ALERT`, and `EMERGENCY`.

- `DEBUG`: troubleshooting details, generally unnecessary to keep at full detail across all production environments.
- `INFO`: normal events useful for operations.
- `NOTICE`: noteworthy events that are not yet warnings.
- `WARNING`: anomalous situations requiring attention.
- `ERROR`: a failed operation or request.
- `CRITICAL`, `ALERT`, `EMERGENCY`: severe incidents requiring rapid response per organizational procedures.

Do not assign `ERROR` to every log. If an application logs all events at the same severity, queries and alerts struggle to distinguish genuine failures from normal operations.

## 4. Storing Logs in Log Buckets

A **log bucket** is where Cloud Logging stores, indexes, and enables querying of logs. Buckets can belong to a project, billing account, folder, or organization per the supported resource model. User-created buckets are created at the project level.

When a project, billing account, folder, or organization is created, Cloud Logging automatically creates two system buckets:

| Bucket | Typical Contents | Default Retention |
|---|---|---|
| `_Required` | Admin Activity, System Event, and certain other mandatory audit logs | 400 days, fixed |
| `_Default` | Data Access audit logs, application logs, and service logs not routed to `_Required` | 30 days, customizable |

The `_Required` bucket cannot be deleted and its retention period cannot be changed. The `_Default` bucket also cannot be deleted, though its routing rules and retention can be adjusted as needed. When an organization needs to retain data longer, segregate logs by team, or meet specific storage requirements, it can create user-defined log buckets and route logs using sinks.

### Properties to Decide When Creating a Bucket

- **Location:** storage region for logs. A log bucket is a regional resource. Choose a region based on latency, availability, workload placement, and data residency requirements.
- **Retention:** number of days to retain logs. User-created buckets can be configured from 1 to 3650 days per current documentation; verify applicable limits and policies before deployment.
- **Encryption:** uses Google-owned and Google-managed encryption keys by default; CMEK can be configured for eligible buckets.
- **Lock:** locks a bucket to prevent updates or deletion. Locking is irreversible and also locks the retention policy; perform only after retention policies are approved.
- **Log views:** define subsets of logs users are permitted to view inside the bucket.

A bucket's location cannot be changed after creation. To move data to another region, create a new bucket in the target region, update sinks to route logs appropriately, and manage the old bucket according to retention policy. Do not treat `global` as offering extra fault tolerance: Cloud Logging documentation notes that `global` or multi-region buckets provide no additional redundancy guarantees over a single-region bucket such as `us-west1`.

Log Router processes logs in the region where they are ingested. Sinks can forward logs to another destination, so choosing a bucket's region alone does not prove the entire data flow stays within one region. When data residency requirements apply, review buckets, sinks, destinations, and analytics services together. Buckets in the `global` location do not support CMEK.

## 5. How Do Logs Explorer and Log Analytics Differ?

Cloud Logging provides two primary query interfaces. They serve different tasks and use different query languages.

| Criterion | Logs Explorer | Log Analytics / Observability Analytics |
|---|---|---|
| Goal | Search, view, and investigate log entries | Analyze, aggregate, spot trends, and join data |
| Language | Logging query language (LQL) | GoogleSQL-based SQL, with certain limitations |
| Output | Log entry list, histogram, and individual entry details | Tables, aggregations, charts, and SQL result sets |
| Common operations | Filter by resource, log name, severity, timestamp | `SELECT`, `WHERE`, `GROUP BY`, `JOIN`, time and JSON functions |
| Suitable scenarios | Find a failing request, inspect an IAM change | Count errors per hour, compare services, compute average latency |
| Prerequisite | Log view permissions and matching data scope | Log bucket must be upgraded for Observability Analytics |

### Logs Explorer: Finding the Right Event

Logging query language is a Boolean expression used to select log entries within the chosen resource scope or log view. Example:

~~~text
resource.type="cloud_run_revision"
severity>=ERROR
timestamp >= "2026-11-19T06:00:00Z"
logName:"run.googleapis.com"
~~~

The filter above locates logs from Cloud Run revisions with severity ERROR or higher, within the specified time range, and with a log name containing the indicated string. During investigation, start with a narrow time range, resource type, and severity; then open log entries to inspect payload, trace, and metadata.

Logs Explorer is ideal when answering questions about a specific event. For example: which request returned HTTP 503, which service account performed an operation, or which VM logged a startup error.

### Log Analytics: Finding Trends with SQL

Observability Analytics provides a SQL editor and Query Builder. Users can query log views or analytics views, view tabular results, build charts, and save charts to custom dashboards.

To query a log bucket using SQL, the bucket must be upgraded to use Observability Analytics. After upgrading, users can still continue viewing logs in Logs Explorer.

SQL is particularly useful when you need to:
- Count logs by severity, resource type, or time bucket.
- Calculate error counts per hour or per revision.
- Extract fields inside JSON payloads.
- Compute average latency by URL or service.
- Join logs with traces to investigate requests across multiple components.
- Standardize data using analytics views for query reuse.

Do not use one interface for every goal. When searching for a specific log entry, Logs Explorer is usually faster for investigation. When aggregating thousands of events into trends, SQL is better suited.

## 6. Enabling Log Analytics for a Log Bucket

In the current interface, upgrading a bucket is performed from the **Logs Storage** page.

1. Open Google Cloud Console and select the target project.
2. Navigate to **Logging → Logs Storage**.
3. Locate the bucket to analyze and check the **Observability Analytics available** column.
4. If the status displays **Upgrade**, select **Upgrade** and confirm.
5. Wait for the operation to complete; upgrading may take several minutes.
6. Open **Observability Analytics**, select a log view belonging to the upgraded bucket, and begin writing SQL queries.

Prerequisites to verify before upgrading:

- The bucket must be created at the project level.
- User-created buckets must be unlocked; `_Required` has specific exceptions.
- The bucket must not have a pending update operation.
- If the project lies inside a VPC Service Controls perimeter, verify whether Logging and Cloud KMS services are restricted by the perimeter, especially when the bucket uses CMEK.
- Verify current feature availability and limits applicable to your specific environment.

**Upgrading is an irreversible operation.** Once Observability Analytics is enabled on a bucket, you cannot disable the feature or revert the bucket to its previous configuration. Therefore, confirm analysis goals, access permissions, storage region, and compliance requirements before upgrading. Current documentation states that new log entries arriving after the upgrade can be analyzed with Observability Analytics; verify historical query behavior on the bucket in your environment before planning around full historical data.

### Upgrading with gcloud

For an existing bucket, you can use:

~~~bash
gcloud logging buckets update BUCKET_ID \
  --location=LOCATION \
  --enable-analytics \
  --async
~~~

Replace `BUCKET_ID` and `LOCATION` with actual values. The `--async` flag returns a long-running operation. Monitor the operation until completion and verify success or error status. When upgrading, do not combine retention changes or other bucket property changes into the same update command.

## 7. Querying Logs with SQL

### Data Source Path Structure

When querying a log view in Observability Analytics, the source path follows this format:

~~~sql
FROM `PROJECT_ID`.`LOCATION`.`BUCKET_ID`.`LOG_VIEW_ID`
~~~

Each component represents:

- `PROJECT_ID`: ID of the project containing the bucket.
- `LOCATION`: region of the log bucket.
- `BUCKET_ID`: bucket name.
- `LOG_VIEW_ID`: ID of the log view inside the bucket.

These names are placeholders; substitute actual resource values. If a project ID contains dots, follow Google Cloud SQL identifier quoting guidance. In Observability Analytics, the log view schema is based on the `LogEntry` structure.

### Example 1: Counting Error Logs by Hour and Resource Type

~~~sql
SELECT
  TIMESTAMP_TRUNC(timestamp, HOUR) AS hour,
  resource.type AS resource_type,
  COUNT(*) AS error_count
FROM
  `PROJECT_ID`.`LOCATION`.`BUCKET_ID`.`LOG_VIEW_ID`
WHERE
  timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
  AND severity IN ('ERROR', 'CRITICAL')
GROUP BY
  hour,
  resource_type
ORDER BY
  hour DESC
LIMIT 500
~~~

This query aggregates error log counts by hour and resource type over the last 24 hours. Operations teams can use the output to pinpoint when errors surged and which service needs investigation.

### Example 2: Extracting Status from a JSON Payload

Suppose the application writes `status` and `request_id` into `jsonPayload`:

~~~sql
SELECT
  timestamp,
  severity,
  JSON_VALUE(json_payload.request_id) AS request_id,
  JSON_VALUE(json_payload.status) AS status
FROM
  `PROJECT_ID`.`LOCATION`.`BUCKET_ID`.`LOG_VIEW_ID`
WHERE
  json_payload IS NOT NULL
  AND JSON_VALUE(json_payload.status) = 'FAILED'
ORDER BY
  timestamp DESC
LIMIT 100
~~~

`JSON_VALUE` extracts a scalar value from a JSON field. Inspect the schema before writing queries because payloads can vary across log types. `json_payload.status IS NOT NULL` checks whether the field exists; `JSON_VALUE(json_payload.status) IS NOT NULL` checks whether the extracted scalar value is non-NULL. These two conditions are not always equivalent.

### Example 3: Calculating Average Latency by URL

~~~sql
SELECT
  http_request.request_url AS request_url,
  AVG(http_request.latency.seconds) AS average_latency_seconds,
  COUNT(*) AS request_count
FROM
  `PROJECT_ID`.`LOCATION`.`BUCKET_ID`.`LOG_VIEW_ID`
WHERE
  http_request IS NOT NULL
  AND http_request.request_method = 'GET'
GROUP BY
  request_url
ORDER BY
  average_latency_seconds DESC
LIMIT 20
~~~

This query groups GET requests by URL and ranks URLs with the highest average latency at the top. Results help identify endpoints needing deeper inspection. For thorough analysis, combine with traces, application logs, and service version metadata at the time of the request.

### Example 4: Grouping Logs by Severity

~~~sql
SELECT
  severity,
  COUNT(*) AS entry_count
FROM
  `PROJECT_ID`.`LOCATION`.`BUCKET_ID`.`LOG_VIEW_ID`
WHERE
  severity IS NOT NULL
GROUP BY
  severity
ORDER BY
  entry_count DESC
LIMIT 100
~~~

This query shows the distribution of logs by severity. If `ERROR` or `CRITICAL` counts spike abruptly, filter further by resource type, log ID, and timestamp to find the root cause.

### Notes When Using SQL

- Observability Analytics supports GoogleSQL functions with certain exceptions. DDL, DML, JavaScript UDFs, BigQuery ML functions, and SQL variables are not supported in this page's SQL editor.
- Use the time-range selector to choose the time interval. If the query includes a `timestamp` condition in `WHERE`, the time-range selector setting is ignored.
- JSON-typed fields must be accessed via appropriate JSON functions such as `JSON_VALUE`.
- RECORD-typed fields such as `http_request` require checking subfields; for example, `http_request.request_method IS NOT NULL`.
- When using `GROUP BY`, every expression in `SELECT` must either be in the grouping clause or aggregated with functions such as `COUNT`, `AVG`, `MAX`.
- Select only needed columns and limit the time range to keep results readable and reduce data scanned.
- Do not assume every log entry represents a single unique request. One request can emit multiple log entries across different components.

Observability Analytics does not automatically deduplicate log entries before running a query. Logs Explorer performs some deduplication based on `log_name`, `timestamp`, and `insert_id`. If counts require deduplication, design check logic around appropriate identifiers and weigh performance cost; deduplicating queries generally run slower.

## 8. Analytics Views: Standardizing Queries for Reuse

An **analytics view** is a resource created from a SQL query to define a custom schema over observability data. Rather than repeating transformations in every query, teams can create a view exposing normalized fields such as service name, environment, request ID, severity, and latency.

For instance, raw logs may contain varied payload shapes. An analytics view can extract common fields for application teams to reuse:

~~~sql
SELECT
  timestamp,
  severity,
  resource.type AS resource_type,
  JSON_VALUE(json_payload.service) AS service_name,
  JSON_VALUE(json_payload.environment) AS environment,
  JSON_VALUE(json_payload.request_id) AS request_id,
  JSON_VALUE(json_payload.message) AS message
FROM
  `PROJECT_ID`.`LOCATION`.`BUCKET_ID`.`LOG_VIEW_ID`
WHERE
  json_payload IS NOT NULL
~~~

Once saved, the analytics view can be referenced in the `FROM` clause of other queries. View names and schemas are defined by the creator; altering a view's query can affect downstream queries relying on it. Therefore, establish owners, descriptions, naming conventions, and a review process.

Console workflow to create a view:

1. Open **Observability Analytics**.
2. Select a log view as the source.
3. Open the SQL editor and test the query.
4. Verify results, column names, and data types.
5. Select **Save → Save as analytics view**.
6. Provide a name and description, then save.

Analytics views are currently marked as **Public Preview** in Google Cloud documentation. Before relying on them in critical operational workflows, check release status and applicable terms at deployment time. A linked BigQuery dataset cannot be created directly on an analytics view.

## 9. Combining Log Analytics with BigQuery

Observability Analytics can query logs and traces directly inside the Cloud Logging interface. You **do not need** a linked BigQuery dataset if your goal is simply querying logs, analyzing logs/traces, saving queries, or building dashboard charts.

A **linked BigQuery dataset** is needed when you want to:

- JOIN log entries with other business datasets in BigQuery.
- Query logs from BigQuery Studio, Looker Studio, or compatible tools.
- Leverage the BigQuery engine and BigQuery processing capabilities.
- Create SQL-based alerting policies driven by query results.

A linked dataset is a read-only pointer to a log bucket. Cloud Logging continues storing the logs; BigQuery reads the data via the linked dataset without creating a separate data copy inside a standard BigQuery table.

### Access Permissions and Security Boundaries

When querying a linked dataset, permissions are evaluated through BigQuery's IAM layer rather than Cloud Logging's IAM layer. This means granting access to the dataset extends the security boundary of logs into BigQuery.

A principal granted access to a linked dataset can query all virtual views inside that dataset; you cannot restrict a principal to only one specific virtual view within a linked dataset. Therefore:

- Create a linked dataset only when there is a genuine analytical requirement.
- Review BigQuery dataset and project permissions before granting access.
- Do not expose logs containing secrets, tokens, or unnecessary personal data to broad user groups.
- Use log views to restrict queryable data within Cloud Logging while understanding that BigQuery dataset permissions have their own scope.
- Audit access logs and permission-granting workflows after creating the link.

A log bucket can be linked to at most one BigQuery dataset. To create a link, the bucket must be upgraded for Observability Analytics and the creator needs appropriate Logging configuration permissions, typically `roles/logging.configWriter`.

## 10. Creating Alerts from SQL Queries

A SQL-based alerting policy runs a query periodically over log data and sends notifications when results satisfy a condition. For example, a team can alert when the proportion of request logs with severity `ERROR` crosses a threshold over a defined window.

SQL alerting policies created from Observability Analytics execute on the BigQuery engine. Accordingly, the queried log view must have a linked BigQuery dataset. This alert type queries only **log views**, not analytics views.

Before creating an alert, define:

1. **Signal:** error count, error rate, latency, or a business condition.
2. **Time window:** the interval over which the query evaluates.
3. **Threshold:** the exceedance level warranting action.
4. **Frequency:** evaluation schedule and condition persistence duration.
5. **Recipients:** the on-call team directly responsible for handling it.
6. **Runbook:** initial verification steps and how to confirm resolution.

Do not alert on every `ERROR` log if the system has known or self-recovering errors. Thresholds, duration, and notification content should reflect user impact. A good alert identifies the service, time window, relevant query, and initial investigation steps.

## 11. IAM and Log Query Access Control

Logs often contain sensitive data such as emails, IPs, user IDs, request metadata, or infrastructure metadata. Access control must be designed alongside storage and analysis.

Common predefined roles:

| Role | Purpose |
|---|---|
| `roles/logging.viewer` | View logs and query `_Required` and `_Default` buckets within the granted scope |
| `roles/logging.viewAccessor` | Access log views in a project; can restrict specific views via IAM conditions or log view policies |
| `roles/observability.analyticsUser` | Use and query analytics views within granted permissions |
| `roles/logging.configWriter` | Configure Logging, such as creating a linked BigQuery dataset when holding required permissions |
| BigQuery dataset roles | Query linked datasets using BigQuery permissions, independent of Cloud Logging permissions |

Users who only investigate logs should not be granted permission to modify sinks, buckets, retention, or IAM policies. Separate viewer, configurator, and data administrator roles. With log views, grant permissions by user group and required log scope. When creating a linked BigQuery dataset, re-evaluate who can query the data through BigQuery.

## 12. Analyzing Logs in a Real-World Scenario

A checkout service running on Cloud Run begins returning many HTTP 5xx responses after a new revision is released. Users report failed payments, though the service still succeeds intermittently.

### Step 1: Identify Timeframe and Scope

Open Logs Explorer, select the project hosting the service, set the time range from before the release to the present, and filter by resource type `cloud_run_revision`. Search for request logs with HTTP status 500 or higher. Compare when the error spike started against the revision deployment timestamp.

### Step 2: Count Failing Requests per Minute

In Observability Analytics, select the log view containing request logs and run:

~~~sql
SELECT
  TIMESTAMP_TRUNC(timestamp, MINUTE) AS minute,
  JSON_VALUE(resource.labels.service_name) AS service_name,
  COUNT(*) AS failed_requests
FROM
  `PROJECT_ID`.`LOCATION`.`BUCKET_ID`.`LOG_VIEW_ID`
WHERE
  resource.type = 'cloud_run_revision'
  AND http_request.status >= 500
  AND timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 2 HOUR)
GROUP BY
  minute,
  service_name
ORDER BY
  minute DESC
LIMIT 120
~~~

The output shows failing requests per minute and service. If a particular window shows a sharp spike, widen investigation into the corresponding revisions, URLs, and application logs. Verify the schema of `resource.labels.service_name` before using the query; if that field is absent in the log view, replace it with the actual field from the schema.

### Step 3: Correlate Application Logs and Traces

From the request log, grab `trace` and `span_id` if present. Open the corresponding trace to see which Cloud Run service, API, or downstream component the request traversed. When joining multiple log/trace tables, use both trace ID and span ID to identify spans; do not JOIN on span ID alone because span IDs are not guaranteed to be globally unique across the system.

Search application logs by `request_id` to view exceptions or error codes from downstream dependencies. If the error originates from the database, correlate timestamps with connection logs and Cloud SQL resource status.

### Step 4: Remediate and Verify

If errors began after the new revision, the development team inspects code changes, environment configuration, service account permissions, and downstream service connectivity. After rolling back or deploying a fix, re-run the query over a comparable time window to compare error rates. Save the query and chart to a dashboard for post-release monitoring.

**Expected outcome:** the team identifies the window when errors spiked, the affected service/revision, and the requests and traces to investigate; after remediation, new data confirms the error rate returns to normal levels.

## 13. Best Practices for Designing a Logging System

### Structured Logging

- Prefer JSON payloads for applications so logs can be filtered and aggregated by fields.
- Use consistent field names across services, such as `service`, `environment`, `request_id`, `trace_id`, `user_action`.
- Assign semantically accurate severity and avoid logging the same event redundantly at multiple levels.
- Include `trace` and request IDs to connect logs with traces and other services.
- Never log passwords, access tokens, private keys, session cookies, or unnecessary personal data.

### Organizing Storage and Routing

- Choose buckets according to purpose, access permissions, retention, and data residency.
- Use organization- or folder-level sinks when centralizing logs across multiple projects.
- Create log views to scope data by user group.
- Review exclusions to avoid dropping audit logs or investigative logs.
- Never lock a bucket before confirming retention, sinks, and archival procedures; locking is irreversible.
- Verify sink destination locations to ensure compliance with regional storage requirements.

### Writing Efficient Queries

- Start with a narrow time window and specific resource type.
- Select only necessary fields instead of pulling entire payloads.
- Use `WHERE` to filter before aggregating.
- Use `TIMESTAMP_TRUNC` to group data by minute, hour, or day.
- Use `JSON_VALUE` when accessing values inside JSON.
- Use `LIMIT` to cap returned row counts.
- Use `CONTAINS_SUBSTR` for substring searches when appropriate; regex extraction is better suited for extracting complex patterns.
- Check for duplicates if counting events or requests.

### Controlling Costs

Upgrading a bucket and running SQL from the Observability Analytics page do not incur separate charges for the upgrade operation or Log Analytics queries under Cloud Logging's published pricing model. However, the overall logging pipeline can still generate costs:

- Ingestion or storage fees based on log type and usage volume.
- Retention fees when storing logs longer than default retention periods.
- Destination service costs when routing to BigQuery, Cloud Storage, or Pub/Sub.
- BigQuery costs when using linked datasets and querying with the BigQuery engine.
- Network log costs generated by services such as VPC Flow Logs, Firewall Rules Logging, or Cloud NAT logs.

Reduce costs by selecting only needed logs to retain, configuring retention to match requirements, using controlled exclusions, and avoiding duplicate logging or oversized payloads. Never cut mandatory audit logs solely to reduce cost if doing so compromises investigation capability or compliance requirements.

## 14. Troubleshooting Common Issues

| Symptom | Causes to Check | Resolution |
|---|---|---|
| Logs Explorer returns no results | Wrong project, resource, time range, log view, or filter | Widen time range, remove conditions, verify log source and scope |
| Logs Explorer has logs, but SQL shows no data | Bucket not upgraded, wrong log view selected, or insufficient permissions | Check Observability Analytics status, bucket, and IAM |
| SQL reports field not found | Schema differs from expected or payload is JSON-typed | Open the Schema pane, use exact field names and `JSON_VALUE` |
| SQL returns duplicate rows | Observability Analytics does not auto-deduplicate log entries | Check `log_name`, `timestamp`, `insert_id` and deduplicate only when required by the query |
| Cannot upgrade bucket | Bucket not at project level, locked, has pending update, or VPC-SC restricts API | Check upgrade prerequisites, permissions, and perimeter configuration |
| Cannot query linked dataset | Missing BigQuery permissions or dataset link not ready | Verify dataset permissions, bucket link, and link-creation permissions |
| Cannot create SQL alert | Log view lacks linked dataset or query targets an analytics view | Create a linked dataset and query a log view in the alert |
| Analytics results differ from Logs Explorer | Different query languages, different scopes, or duplicate handling | Compare same bucket/view, time window, and conditions; check deduplication logic |

When upgrading a bucket with gcloud, the command may return a long-running operation. Check the operation status rather than re-running the upgrade command repeatedly. If the operation fails, inspect the error details and resolve the cause before retrying.

## 15. Limitations to Keep in Mind

- Logs Explorer and Observability Analytics use different query languages; an LQL filter cannot be copied verbatim into SQL without conversion.
- Only upgraded buckets can be queried with Observability Analytics. Upgrading cannot be undone.
- Analytics views are currently in Public Preview per referenced documentation; verify terms and release status before depending on them in production.
- Observability Analytics does not automatically deduplicate log entries; counts may differ from Logs Explorer.
- Linked BigQuery datasets extend data access into BigQuery's permission layer; dataset permissions must be governed carefully.
- SQL-based alerting policies require a linked BigQuery dataset and can only query log views.
- Bucket location cannot be changed after creation; plan storage regions upfront.
- Seeing no logs or findings in a query does not prove a system has no incidents. The log source may be disabled, a sink may have excluded logs, retention may have expired, or the user may lack view permissions.
- Log Analytics assists investigation and analysis; it does not automatically fix applications, IAM configurations, or cloud resources.

## 16. Self-Check Questions

1. When should you use Logs Explorer, and when should you use Observability Analytics?
2. Why must a log bucket be upgraded before querying it with SQL?
3. A log entry has `timestamp` and `receive_timestamp`. How do these two fields help investigate ingestion latency?
4. When a field resides inside a JSON payload, why should you inspect the schema and use `JSON_VALUE`?
5. Why should a bucket upgrade require approval before execution?
6. When is creating a linked BigQuery dataset necessary? How does it change security boundaries?
7. Why can a SQL-based alerting policy not query an analytics view?
8. An Observability Analytics query returns more rows than Logs Explorer. Which factors would you inspect?
9. When an organization has data residency requirements, what components besides the log bucket's location must be checked?
10. How can you reduce logging costs while preserving sufficient data for operations and investigation?

## References

- [Cloud Logging overview](https://docs.cloud.google.com/logging/docs/overview)
- [Analyze logs using Logs Explorer and Observability Analytics](https://docs.cloud.google.com/logging/docs/log-analytics)
- [Query and analyze logs with Observability Analytics](https://docs.cloud.google.com/logging/docs/analyze/query-and-view)
- [Sample SQL queries](https://docs.cloud.google.com/logging/docs/analyze/examples)
- [Configure log buckets](https://docs.cloud.google.com/logging/docs/buckets)
- [Store log entries](https://docs.cloud.google.com/logging/docs/store-log-entries)
- [Cloud Logging locations and regionality](https://docs.cloud.google.com/logging/docs/region-support)
- [Create a linked BigQuery dataset on a log bucket](https://docs.cloud.google.com/logging/docs/analyze/query-linked-dataset)
- [Monitor SQL query results with an alerting policy](https://docs.cloud.google.com/logging/docs/analyze/sql-in-alerting)
- [Create, query, and manage analytics views](https://docs.cloud.google.com/logging/docs/analyze/create-and-manage-analytics-views)
