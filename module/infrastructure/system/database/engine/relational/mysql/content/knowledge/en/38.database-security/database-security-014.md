# Security

## Auditing, Enterprise Audit, and Boundaries with General/Slow Logs

In the `DATABASE_MYSQL` module, you learn to master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, and concurrency control. You also practice reading execution plans, optimizing queries, managing privileges, performing backups, and handling operational issues in relational databases. Auditing connects those skills to security requirements: when a notable activity occurs in the database, operations need to know **who** performed it, **when**, from **where**, on **which object**, and whether the action **succeeded**.

This lesson distinguishes MySQL Enterprise Audit from the general query log and slow query log. All three mechanisms can record SQL activity, yet they serve different goals. Choosing the wrong mechanism can cause a system to log too much sensitive data while still lacking sufficient evidence for a security investigation.

### 1. What Is Database Auditing?

Database auditing is the deliberate recording of events related to security and compliance. A useful audit record typically answers the following questions:

- **Who:** which MySQL account performed the operation? If end-user attribution is needed, the application must also supply the business identity.
- **When:** when did the event occur? Synchronize clocks across MySQL, application servers, and log collection systems for accurate correlation.
- **Where:** from which client host, address, or service did the connection originate?
- **What:** which operation was executed, on which schema, table, or resource?
- **Outcome:** did the operation succeed, fail, or get denied?

Events typically worth monitoring include successful and failed logins, disconnections, account and privilege changes, DDL operations, data modifications, access to sensitive tables, and administrative commands. The actual scope depends on organizational policy, data classification, and investigative requirements.

Auditing differs from merely storing business history in an application. An order history table may record which user changed an order's status, yet not necessarily show which DBA account ran a direct `UPDATE`. Conversely, MySQL-layer logs usually know the connection account and statement, but do not natively understand the end user, HTTP request ID, or business reason. For critical systems, these two layers complement each other.

### 2. MySQL Enterprise Audit

MySQL Enterprise Audit is an audit plugin included in MySQL Enterprise Edition. The plugin receives events from the MySQL server and writes them to the audit log according to configured format, policy, and filters. Depending on version and configuration, event classes can include connections, SQL statements, and table accesses.

Enterprise Audit's strength lies in selecting which events to log by policy. For instance, an organization can require logging activity by administrative accounts, privilege changes, or accesses to tables containing sensitive data. Filters must be designed and tested against the running MySQL version; do not assume every version shares the same syntax or exact event set.

**Installing and Checking the Plugin**

The plugin must be present in the corresponding Enterprise package. On systems using `.so` plugin libraries, it can be installed with:

```sql
INSTALL PLUGIN audit_log SONAME 'audit_log.so';

SELECT PLUGIN_NAME, PLUGIN_STATUS
FROM INFORMATION_SCHEMA.PLUGINS
WHERE PLUGIN_NAME = 'audit_log';

SHOW VARIABLES LIKE 'audit_log%';
```

On Windows, the library file typically carries a `.dll` extension. You can configure plugin loading at server startup using `plugin-load-add` in MySQL configuration. Choose a loading method suited to how your server is deployed and verify plugin status after startup. Do not run the install command if the plugin is not supplied or is incompatible with the server version.

**Event Filtering**

Versions of Enterprise Audit support filtering via filter management functions. The example below creates a filter logging all events and assigns it to a test account:

```sql
SELECT audit_log_filter_set_filter(
  'audit_all_for_lab',
  '{"filter":{"log":true}}'
);

SELECT audit_log_filter_set_user(
  'app_user@localhost',
  'audit_all_for_lab'
);
```

This is a broad configuration intended for testing in a lab environment. Logging every event for an account can generate huge logs and capture many statements containing sensitive data. In production, build filters tailored to requirements: account groups, event classes, statements, or protected objects. Check the exact JSON syntax and filtering capabilities against the documentation for your specific version of MySQL Enterprise Audit.

After configuration, log in with the test account, execute the chosen operations, and verify the audit log contains complete information on timestamp, account, event, and outcome. Also test an operation excluded by the filter to ensure the policy neither over-logs nor omits events unexpectedly.

**Limitations to Understand Clearly**

- The audit log records only events supported by the plugin and permitted by active filters. The absence of an event in the log does not prove the operation never happened.
- Audit plugins do not inherently store before-and-after snapshots of individual data rows. If old/new value history or business context is needed, add application-level auditing or an appropriate history-tracking mechanism.
- Local audit logs on the server are not automatically tamper-evident evidence. Anyone with OS or server administrative privileges can alter local log files. Forward logs to a centralized system with access controls and tamper protection.
- Audit logging incurs CPU, I/O, and storage overhead. Overly broad filters increase load and make finding critical events harder.

### 3. General Query Log

The general query log records connections and statements received by the server. It is a useful tool when you need a quick view of what an application is sending to MySQL, to confirm whether a statement was actually sent, or to inspect the sequence of operations in a debugging session.

The general log is not a full audit policy. It aims at recording overall query activity, without security-focused filtering at the granularity of Enterprise Audit. Nor does it show how slow a query ran; its main purpose is recording incoming activity.

**Enabling Temporarily for Investigation**

```sql
SHOW VARIABLES LIKE 'general_log';
SHOW VARIABLES LIKE 'log_output';

SET GLOBAL log_output = 'FILE';
SET GLOBAL general_log = ON;

-- Reproduce the operation to observe over a short period.

SET GLOBAL general_log = OFF;
```

`log_output` controls whether logs go to `FILE`, `TABLE`, or are disabled with `NONE`. When using `TABLE`, data can be read from `mysql.general_log`; when using `FILE`, know the log file path and protect OS-level file permissions. `SET GLOBAL` settings apply server-wide; required privileges depend on the MySQL version and privilege model in use.

Avoid leaving the general log enabled continuously on busy servers without evaluating impact. The log can grow very rapidly and contain parameter values or data embedded in application statements. Even though MySQL masks certain credential fields, treat log contents as sensitive data and restrict who can read them and how long they are retained.

### 4. Slow Query Log

The slow query log records statements exceeding a configured time threshold along with other filter conditions. Its goal is finding queries needing optimization—such as queries scanning too many rows, missing indexes, or waiting long on locks.

Commonly used variables include:

- `slow_query_log`: enables or disables the slow query log.
- `long_query_time`: time threshold in seconds; queries must exceed this threshold to qualify for logging.
- `min_examined_row_limit`: minimum number of rows examined for a query to be logged.
- `log_queries_not_using_indexes`: optional setting to also log queries not using indexes; enabling it can produce substantial log volume.
- `log_slow_admin_statements`: allows logging certain slow administrative statements.

Example temporary configuration to capture queries taking longer than one second and examining at least 100 rows:

```sql
SET GLOBAL slow_query_log = ON;
SET GLOBAL long_query_time = 1;
SET GLOBAL min_examined_row_limit = 100;

SHOW VARIABLES LIKE 'slow_query_log';
SHOW VARIABLES LIKE 'long_query_time';
```

Replace thresholds with realistic numbers for your system. One second may be too high for an API needing tens-of-milliseconds latency, yet too low for a long analytical report. `long_query_time` has both global and session scopes; changing the global value typically affects new connections, while the session variable can be adjusted individually for the current session.

The slow query log does not record every statement. A fast query reading sensitive data may not appear; a fast query altering privileges may likewise not appear. Therefore, never use the slow query log to prove who accessed data or to satisfy comprehensive audit requirements.

Once notable queries are identified, use `EXPLAIN` or `EXPLAIN ANALYZE` (if supported by your version) to analyze the execution plan. The slow query log helps find queries to review; execution plans explain how MySQL intends to execute or actually executed the query.

### 5. Comparing Logging Mechanisms

| Mechanism | Primary Goal | Capture Scope | Should Not Be Used To |
|---|---|---|---|
| MySQL Enterprise Audit | Policy-based security auditing | Event classes supported by the plugin and allowed by filters, such as connections, statements, or table access | Implicitly derive row-level before/after snapshots or tamper-proof evidence |
| General query log | Observing SQL and connection activity | Connections and statements received by the server | Measure query performance or serve as the sole audit policy |
| Slow query log | Diagnosing slow queries | Queries exceeding configured thresholds and filter conditions | Track all data accesses or privilege changes |
| Binary log | Replication and point-in-time recovery | Changes recorded in binlog format; not all read queries | Track all reads or replace audit logs |
| Application-level audit | Business history and end-user identity | Events explicitly logged by the application, potentially with request IDs and before/after values | Detect direct out-of-band DB actions without MySQL-layer logging |

The binary log is often mentioned alongside the general and slow logs because all three are MySQL logs, yet their purposes differ. The binary log serves data replication and recovery; depending on `binlog_format`, it records statements or row-change events. It does not record all `SELECT` statements and should not be treated as a security access log.

### 6. Designing an Investigable Audit Policy

Before turning on logs, write down the exact questions operations need to answer. For example: "Who read the table containing payment details?", "Which account granted `SELECT` to another account?", or "Were there failed logins from an unfamiliar host?". From those questions, define the required events, accounts, objects, and retention periods.

**Account identity.** Avoid sharing one MySQL account across multiple people or services. Create separate accounts per application and purpose with least privilege. If an application uses a connection pool, MySQL-side logs typically see only the service account; also log user IDs and request IDs at the application layer to correlate database events back to end users.

**Event scope.** Consider logging successful/failed logins, privilege changes, account creation or deletion, DDL on critical schemas, writes to sensitive data, and read access to protected tables. Not every system needs to log every `SELECT`; evaluate investigative needs and storage costs upfront.

**Protecting log contents.** SQL statements can contain emails, phone numbers, identifiers, or business data. Avoid logging sensitive values unnecessarily, restrict log read access, encrypt logs in transit and at rest, and apply retention periods matching organizational policy.

**Integrity and availability.** Separate log administration rights from database administration rights when possible. Ship logs to a centralized system, restrict delete/modify rights, alert on log-shipping interruptions, and synchronize clocks. Configure rotation, storage headroom, and alerts when filesystems near capacity. Never let logs fill disk and interrupt database availability.

**Testing coverage.** Build a matrix of accounts, operations, expected outcomes, and expected log records. Test successful, failed, denied, and filter-excluded operations. Repeat testing after MySQL upgrades, plugin updates, or filter policy changes.

### 7. Practical Workflow for Selecting and Verifying Logs

Suppose the security team needs to monitor access to the `payments` table, while the development team is hunting down a slow reporting query.

1. **Define goals.** Monitoring access to `payments` and privilege changes is an audit requirement. Finding the slow reporting query is a performance requirement.
2. **Choose mechanisms.** Use Enterprise Audit if your version and license support the needed events. Use the slow query log to locate the slow reporting query. Enable the general log only briefly if you need to see exactly which statements an application sends.
3. **Configure clearly scoped filters.** Start with the specific accounts or event groups to track. Avoid filters logging all activity in production before estimating volume and impact.
4. **Create test cases.** Log in with a test account, run a read query, execute an authorized action, and attempt a denied action. Confirm each event appears properly in the chosen log source.
5. **Correlate identities.** Inspect user, host, timestamp, and connection ID. When end-user attribution is needed, correlate with the request ID in application logs.
6. **Operationalize logging.** Forward logs to centralized storage, set access permissions, retention, rotation, and alerts. Assign ownership for reviewing anomalous events.
7. **Disable temporary log sources.** Once investigation ends, turn off the general log if enabled to avoid unnecessary data growth and overhead.

### 8. Handling Common Situations

| Symptom | How to Check |
|---|---|
| Events missing from Enterprise Audit | Verify the plugin status is `ACTIVE`, the filter exists and is assigned to the right `user@host`, and check the log path and MySQL write permissions; then reproduce a test event |
| Audit log grows too large | Narrow filters, review which accounts hold filters, forward logs centrally, and adjust retention; do not drop mandatory events solely to save space |
| General log grows rapidly | Turn off the general log once reproduction finishes; check `log_output` and log storage location |
| Fast queries missing from slow log | Expected behavior if queries do not exceed `long_query_time` or match filter criteria; use an appropriate audit source if access tracking is needed |
| Cannot identify the end user | Check whether the application shares one DB account or connection pool; add business auditing and correlation IDs at the application layer |
| Old logs disappeared | Check rotation, retention, and log-forwarding status to the central system; verify storage policy before concluding an event never occurred |

### 9. Self-Check Exercises

1. A user reads the `customer_payment` table in a few milliseconds. Why is the slow query log not an appropriate source for detecting this access?
2. Operations need to see every SQL statement an application sends over 10 minutes to reproduce a bug. Which mechanism fits, and what must be done once the investigation finishes?
3. Why can enabling Enterprise Audit without verifying filters and file write permissions still result in missing evidence?
4. The binary log can assist data recovery. Why does it not replace an access audit log?
5. A system shares the `app_user` account across all users. What data must be added at the application layer to trace an action back to the exact end user?

### 10. Selection Principles

Choose log sources based on the question you need to answer: **Enterprise Audit** for policy-filtered security events; **general query log** for short-term observation of connections and statements; **slow query log** for performance diagnostics; **binary log** for replication and recovery; **application auditing** for business history and end-user identity. A critical system may require combining multiple layers, yet each layer must have a clear goal, owner, access control, and retention period.
