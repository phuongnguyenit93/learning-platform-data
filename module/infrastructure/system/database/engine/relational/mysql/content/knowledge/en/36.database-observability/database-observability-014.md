# Limiting Sensitive Data and Log/Trace Retention

## Objectives

In the **System Observability** chapter, this lesson helps you design logs and traces informative enough to diagnose MySQL without turning the observability platform into a duplicate of business data. After this lesson, you can:

- Identify sensitive data that can appear in application, MySQL, and telemetry-collection logs and traces.
- Select fields permitted for logging, and strip or redact data before sending it to storage.
- Understand the risks of the general query log, slow query log, and statement data in Performance Schema.
- Define retention periods based on purpose, sensitivity, and operational requirements; manage backups and long-term archives as well.
- Verify that prohibited data does not leak into logs/traces and that expired data is purged according to policy.

## 1. Good Observability Requires Data Boundaries

Logs record events that occurred; traces describe which components a request traversed and how long each step took. For MySQL, these signals help pinpoint slow queries, connection errors, deadlocks, abnormal access, and resource bottlenecks. However, SQL text, parameters, connection info, or user-linked attributes can expose sensitive business data.

For example, the following statement embeds an email literal directly in the SQL:

```sql
SELECT id, status
FROM customer
WHERE email = 'lan@example.com';
```

If an application writes the raw SQL into logs, that email can be replicated into centralized log systems, search indexes, object archives, support exports, and backups of all those systems. Anyone with log-read privileges could then view data they are not authorized to access in the application.

Therefore, every observability signal must answer two questions: **What information is genuinely needed for operations?** and **Who can view that information across its entire storage lifecycle?** Collecting more data does not equate to better observability. The goal is capturing enough context to find root causes with minimal sensitive data exposure.

## 2. Identifying Data That Can Appear in Logs and Traces

Risk is not limited to what an application logs explicitly. A data field can pass through many layers: application, driver, MySQL, collection agent, forwarder, storage backend, and analysis tools. Inventory this entire pipeline.

| Source | Data That May Appear | Risks to Control |
|---|---|---|
| Application logs | Emails, phone numbers, names, order IDs, form payloads, tokens | Exposure of personal data or credentials |
| MySQL query logs | SQL text, literal values, table/column names, connecting accounts | Exposure of query parameters, business schema, or account identities |
| Error log | Error details, client addresses, usernames, database names, or file paths | Disclosure of infrastructure details and identifiers |
| Audit log | Users, connection sources, actions, accessed objects | May contain identifying data; often requires stricter protection and longer retention than diagnostic logs |
| Traces | Operation names, query text, span attributes, baggage, forwarded URLs or headers | Sensitive data propagating across multiple services |
| Agent and proxy logs | Labels, metadata, connection configs, shipping errors | May inadvertently log credentials or internal topology |

Classify data before selecting log fields. A practical classification includes:

| Category | Examples | Handling |
|---|---|---|
| Prohibited | Passwords, access tokens, refresh tokens, private keys, connection strings with credentials, one-time verification codes | Never log at any level; strip at the source |
| Sensitive | Government IDs, emails, phone numbers, addresses, payment details, user content, parameter values containing personal data | Never log raw values; if an approved purpose exists, log only minimized or pseudonymized forms |
| Internal | Schema names, table names, hostnames, service accounts, tenant IDs, query structure | Log only when needed; restrict viewers and retention |
| Standard operational | Operation type, duration, rows examined, normalized error codes, application version | Can be logged per allowlist and retention policy |

Classification must evaluate field combinations too. A `trace_id` is usually not personal data, yet when linked to a user-mapping table or a specific event, it can act as a lookup key leading to sensitive records. Similarly, `tenant_id`, `customer_id`, or table names may lack personal content while still revealing internal structure or customer identities.

## 3. Controlling MySQL Query Log Content

MySQL provides multiple diagnostic sources. Each has a different purpose and detail level; never enable all of them and forward everything to log storage without assessment.

### General Query Log

The general query log records activity received by the server, including client statements. It is valuable for short-term targeted investigations, yet it generates large volumes and stores full statement text. If SQL contains sensitive literals, those values appear in the log.

In production, keep the general query log disabled during normal operations. When enabling it for an investigation, bound the time window, target hosts, and authorized readers; decide storage location, rotation, and turn-off time beforehand. `log_output` supports `FILE`, `TABLE`, `FILE,TABLE`, or `NONE`; these options determine output destination and do not automatically strip or mask sensitive values.

### Slow Query Log

The slow query log finds queries exceeding duration thresholds. It is valuable for performance tuning, though logged query text can still contain literal values. Thus, enabling the slow query log does not mean the data is automatically safe.

Example starting configuration in the MySQL option file:

```ini
[mysqld]
general_log = OFF
slow_query_log = ON
long_query_time = 1
log_output = FILE
```

`long_query_time = 1` is just an illustrative one-second value, not a universal threshold for every system. Choose thresholds based on latency targets, actual load, and manageable log volume. When investigating queries containing sensitive data, restrict log file read permissions and retention; prefer aggregated metrics or fingerprints over raw SQL text.

Inspect current settings with read-only commands:

```sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
  'general_log',
  'slow_query_log',
  'long_query_time',
  'log_output'
);
```

Production configuration changes must follow your change-management process, verify MySQL version behavior, and assess impact beforehand. Never enable detailed logging broadly merely to collect data "just in case."

### Error Log, Audit Log, and Performance Schema

The error log helps diagnose startup failures, storage errors, connection issues, and server faults. While it typically omits row data, it can still contain account names, client addresses, database names, or internal file paths. Restrict read permissions and enforce appropriate retention.

Audit logs focus on who performed which action, from where, and on which object. Because this serves security investigations and accountability, integrity guarantees, access controls, and retention periods differ from performance logs. Enable only events needed for defined control objectives.

Performance Schema provides in-memory diagnostic data. For example, `events_statements_summary_by_digest` aggregates statistics by digest; `DIGEST_TEXT` represents normalized statement patterns and is usually preferable to storing raw SQL. Conversely, statement history tables can expose `SQL_TEXT`, which must be treated as potentially containing sensitive data.

Example reading digest statistics:

```sql
SELECT
  DIGEST_TEXT,
  COUNT_STAR,
  AVG_TIMER_WAIT,
  SUM_ROWS_EXAMINED
FROM performance_schema.events_statements_summary_by_digest
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 10;
```

Digests reduce literal exposure but are not complete anonymization. Schema, table, and column names or query shapes can still leak internal details. Restrict query access to Performance Schema tables and inspect contents before exporting data off the server.

## 4. Designing Logs and Traces with an Allowlist

Define your log/trace schema using an explicit allowlist of permitted fields. Each field should have a documented purpose, owner, data classification, and retention period. Drop undeclared fields by default. This is far easier to govern than logging everything and trying to detect and scrub dangerous fields afterward.

A performance-oriented query record might contain:

```json
{
  "event": "db.query",
  "service": "order-api",
  "operation": "find-orders-by-status",
  "db.system": "mysql",
  "db.operation": "SELECT",
  "db.query.summary": "SELECT orders WHERE status = ?",
  "duration_ms": 42,
  "rows_examined": 1200,
  "outcome": "success",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"
}
```

This is an illustrative schema example; exact attribute names depend on your instrumentation library. The record keeps the operation, summarized query shape, duration, row count, and trace correlation ID. It omits emails, customer IDs, query parameters, and SQL containing literals.

Key implementation rules:

1. **Minimize at the source.** Applications or instrumentation must strip sensitive data before emitting events out of process. Collector-side redaction is an extra layer; data traversing queues or proxies could still be persisted there.
2. **Prefer stable operation names.** Use `find-orders-by-status` instead of putting URLs, usernames, or input values into span names. Request-specific span names inflate cardinality and risk leaking data.
3. **Never log raw parameters.** Use placeholders, query summaries, or controlled fingerprints. Keep bind parameters out of log messages, exceptions, and trace attributes.
4. **Filter headers and baggage.** Forward only required headers. Strip `Authorization`, cookies, tokens, and unnecessary identifiers before creating spans or propagating across services.
5. **Mask deliberately.** When correlating events to an entity is required, use controlled pseudonyms or opaque reference IDs that cannot be reversed from logs. Unkeyed hashes of emails or phone numbers remain vulnerable to dictionary attacks; never treat plain hashes as anonymous.
6. **Control error outputs.** Exceptions can embed SQL statements, parameter values, file paths, or raw inputs. Normalize error messages and keep detailed stack traces within protected boundaries.

Avoid attaching every `user_id`, `order_id`, or `tenant_id` to every span. When investigating a specific case is needed, use an access-controlled, time-bounded lookup mechanism rather than turning every trace into a searchable index of user data.

## 5. Choosing Retention Periods for Logs and Traces

Retention must start from usage purpose. Debug logs for short-term incident triage rarely need the same retention as audit logs for compliance investigations. Traces are high-volume and most useful close to an incident; aggregated metrics can be retained longer for trend analysis.

A policy should specify retention per data category:

| Data Category | Primary Purpose | Example Starting Retention | Considerations |
|---|---|---:|---|
| Temporary debug logs | Investigating a specific bug | 1–7 days | Enable only for bounded windows; delete once investigation ends |
| Operational application logs | Error hunting and correlating recent requests | 14–30 days | Minimize personal data; restrict search access |
| Slow query logs | Analyzing slow queries | 7–30 days | May contain SQL text; weigh fingerprints and thresholds |
| Detailed traces | Following request flows and latency | 3–14 days | High volume; use sampling and attribute limits |
| Aggregated metrics | Performance trend analysis | 90 days to 13 months | Keep aggregated data; avoid high-cardinality identifying labels |
| Audit logs | Access investigations and compliance controls | Per security/legal policy; e.g., 90–365 days | Require integrity protection, read controls, and archival processes |

These durations are starting examples for policy discussions, not mandatory standards or legal advice. Official retention periods must reflect applicable laws, contracts, internal policies, recovery targets, investigative needs, and storage costs. Where legal requirements mandate specific durations, those take precedence.

For each log/trace class, document:

- **Purpose:** which incidents or controls require this data?
- **Owner:** which team owns the content and retention schedule?
- **Hot retention:** how long must data remain fast-searchable?
- **Long-term archive:** is archiving needed, who can access it, and is it encrypted?
- **Expiration:** which system purges the data, how quickly, and how is deletion verified?
- **Exceptions:** who can place legal holds or extensions, under what rationale, and on what review date?

### Accounting for Copies and Data Paths

Deleting records from a search UI does not guarantee the data is gone. Logs may linger in queues, storage buckets, regional replicas, snapshots, backups, or downloaded exports. Policies must cover the lifecycle of all organization-managed copies.

If data resides in immutable backups where individual records cannot be purged immediately, define backup expiration lifetimes, restrict restore permissions, and specify post-restore scrubbing procedures. A restore must never inadvertently reintroduce expired data into live log stores.

Estimate baseline capacity with:

```text
Approximate storage = daily generated data × retention days
```

For example, a system generating 2 GB of compressed logs per day retained for 30 days requires roughly 60 GB for a single copy, before indexes, replicas, and headroom. With three independent copies, physical storage can be substantially higher. Trimming fields, sampling traces, and shortening debug log retention simultaneously lower risk and cost.

## 6. Securing Log and Trace Stores

Even after data minimization, log stores remain sensitive systems because they centralize rich operational traces. Apply these safeguards:

- **Least privilege:** separate permissions for collector config, ingestion, search, export, and retention administration. Developers do not automatically need read access to all production logs.
- **Authentication and encryption:** enforce service authentication, encryption in transit, and encryption at rest with proper key management.
- **Access auditing:** log who queries, exports, or modifies retention policies; protect the audit trail from modification by accounts that administer logs.
- **Environment separation:** never ship production logs to development or testing environments without data minimization and formal approval.
- **Export limits:** cap query results, download lifetimes, and sharing permissions; govern dashboards or saved query links shared widely.
- **Configuration security:** never place credentials in agent configs, command lines, log variables, or repositories; use a secret manager and service identity mechanisms.

Sampling reduces trace storage volume. You can sample normal successful requests at a low rate while retaining higher proportions of errors or high-latency outliers via tail sampling. However, sampling is not a redaction control: every generated span must still obey allowlists and redaction before emission.

## 7. Validating Policies Before Production Rollout

A policy works only if it can be verified. Test in a controlled environment using synthetic canary data with easily searchable markers, such as `SENSITIVE_TEST_9F31`, dummy emails, and dummy tokens. Send those values through expected query, error, and trace paths; then search every log destination, queue, and storage tier to confirm raw values never appear.

Recommended rollout workflow:

1. Inventory all log/trace emitters, collectors, queues, stores, dashboards, exports, and backups.
2. Classify data fields; identify prohibited, minimized, and allowed fields.
3. Enforce allowlists at the source; disable raw SQL logging and verbose debug output unless formally approved.
4. Configure retention per signal type, plus archival, deletion, and backup handling rules.
5. Test with synthetic canary data, verify search results across all destinations, and audit access permissions.
6. Exercise expiration workflows; confirm data is purged from active stores and backup lifetimes are enforced.
7. Monitor dropped-log rates, redaction errors, storage growth, and unexpected schema fields.

If secrets or personal data are discovered inside logs, restrict access immediately, determine scope and affected copies, rotate potentially exposed credentials, and execute deletion or quarantine per incident response procedures. Record decisions and evidence in a protected incident system. Never copy log snippets containing exposed data into regular tickets, emails, or chat channels.

## 8. Checklist for MySQL Systems

Before enabling or changing observability settings, verify:

- [ ] General query log is enabled only with a clear investigation goal and expiration time.
- [ ] Slow query log has an appropriate threshold; operators understand SQL text can still contain sensitive literals.
- [ ] Error log, audit log, and Performance Schema data have appropriate read access controls.
- [ ] Logs and traces follow allowlists; passwords, tokens, cookies, credentials, and raw bind parameters are excluded.
- [ ] Span names, labels, and baggage contain no unnecessary identifiers or user input.
- [ ] Each data class has an owner, purpose, retention period, archival rule, and purge process.
- [ ] Backups, snapshots, regional replicas, and restored data fall under the retention lifecycle.
- [ ] Log access and exports are permission-controlled, encrypted, and audited.
- [ ] Canary testing proves prohibited data does not appear in collection destinations.

## Conclusion

Safe MySQL observability starts with deciding which data is permitted to leave applications and database servers. Favor operations, durations, row counts, normalized error codes, and digest statistics; collect raw SQL text or granular payloads only under controlled conditions. Every log and trace type requires retention grounded in purpose, applicable requirements, and the full lifecycle of all copies. By minimizing data at the source, enforcing least-privilege access on storage, and verifying expiration, operations teams retain strong diagnostic signals without creating an unmanageable trove of sensitive data.
