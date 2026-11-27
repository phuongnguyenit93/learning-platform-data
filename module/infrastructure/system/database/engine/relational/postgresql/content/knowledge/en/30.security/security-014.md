# Access Logging, Auditing, and Sensitive Data Handling in PostgreSQL

A secure PostgreSQL system must answer two core sets of questions:

1. **Who accessed or modified data, when, from where, and how?**
2. **While recording those events, did the system accidentally leak sensitive data?**

These two goals sometimes conflict. Logging full SQL statements and parameters helps investigate incidents, yet can also leak passwords, emails, phone numbers, access tokens, or health data into log files. Conversely, logging merely "a query ran" is insufficient to determine which records changed.

PostgreSQL offers multiple observability and auditing layers:

- **Server logs**: connections, disconnections, errors, DDL statements, and slow statements as configured.
- **pgAudit** (optional extension): statement-level and object-class audit events depending on configuration.
- **Audit tables + triggers**: row-level change history for `INSERT`/`UPDATE`/`DELETE`.
- **Application logs/traces**: business user identity, request ID, authorization decisions, and external system interactions.
- **Privileges, RLS, views, and data protection**: controls limiting who can read source data or logs.
- **Backups, retention, encryption, and investigation runbooks**: ensuring logs remain useful, protected, and bounded in lifetime.

~~~mermaid
flowchart TD
    U["User / service"] --> API["API: authentication, authorization, request_id"]
    API --> DB["PostgreSQL session"]
    DB --> SQL["SQL statements"]
    DB --> SLOG["Server log: connect/error/statement/duration"]
    SQL --> PA["pgAudit if installed and configured"]
    SQL --> TR["DML triggers: row change audit"]
    TR --> AT["Audit table in same transaction"]
    API --> AL["Safe app logs / traces"]
    SLOG --> SIEM["Controlled log pipeline / SIEM"]
    PA --> SIEM
    AL --> SIEM
    AT --> AUD["Least-privilege audit reviewer"]
~~~

This article belongs to the **Security** chapter of the **Database Engine Relational PostgreSQL** module. We will compare logging approaches, build row-level auditing on a table holding personal data **without copying sensitive values into audit logs**, and design access control, retention, deletion, encryption, and incident response policies.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish system logs, operation audits, data change audits, and performance telemetry.
2. Identify what PostgreSQL server logs capture and what they omit.
3. Deliberately configure `log_connections`, `log_disconnections`, `log_statement`, `log_min_duration_statement`, and `log_line_prefix`.
4. Understand risks of exposing literal and bound parameter values across SQL, server logs, and error messages.
5. Explain the role and limits of the **pgAudit** extension.
6. Design audit triggers that avoid cloning full `OLD`/`NEW` payloads when tables contain sensitive fields.
7. Understand that audit triggers and business mutations **roll back together in the same transaction**.
8. Know why DML triggers **cannot observe SELECTs** and do not replace read-access auditing.
9. Interpret `session_user`, `current_user`, `application_name`, and request IDs with proper awareness of trust boundaries.
10. Restrict access to audit tables and log files under least privilege.
11. Minimize sensitive data inside views, SQL text, app logs, query plans, and statistics.
12. Distinguish encryption at rest, TLS, field-level encryption, and hashing/HMAC.
13. Design retention, backups, and auditing policies aligned with legal and business requirements.
14. Build an investigation runbook combining event correlation and log tamper resistance where needed.
15. Run verification queries and reason through failure scenarios.

## 2. Threat Model: What Needs Protection?

Before turning on verbose logging everywhere, inventory what is at risk:

| Asset | Threat | Controls Needed |
| --- | --- | --- |
| DB login credentials | Leaking passwords or connection strings | Secret manager, TLS, rotation, log redaction |
| Personal data (PII) | Logs recording emails, phones, addresses | Data minimization, masking, ACLs |
| Auth tokens, API keys | Printed in SQL, logs, or errors | Never log, secret scrubbing, rotate on leak |
| Transaction history | Deletion or tampering of audit trails | Privilege separation, centralized shipping, immutable storage where needed |
| Human actor identity | DB logs show only a shared pool role | App identity, request ID, trusted mapping |
| SQL plans / queries | Exposing schema, tables, or literal values | Scoped monitoring grants, restricted query text |
| Log files & backups | Unauthorized reads or indefinite retention | Encryption, access reviews, retention, secure deletion |

An environment with exhaustive audit logs where every developer can read raw logs full of customer PII is **no safer** than one engineered around data minimization.

### Questions to Establish Up Front

- Which fields qualify as **PII** (personally identifiable information), financial data, health data, or trade secrets?
- Which exact events must be provable?
- How long must logs be retained?
- Who is permitted to read, export, delete, or reconfigure logs?
- What degree of tamper resistance is required for evidence?
- Do users or partners have deletion or retention-limitation rights?

No single logging profile fits every industry and jurisdiction.

## 3. Four Frequently Confused Logging Layers

| Layer | Example | What It Answers | Limits |
| --- | --- | --- | --- |
| **Connection log** | Session from host A logs in as role X | Connection role, client IP, timestamps | Does not identify the real web end user |
| **Statement log** | Role X issues an `UPDATE` | SQL statement emitted when logging enabled | Does not inherently capture actual OLD/NEW values |
| **Row audit** | Customer 101 status changed active → blocked | Exactly which row changed and selected fields | DML triggers cannot observe `SELECT` |
| **Application audit** | User 42 approved request 9001 | Business intent, actor, request ID | Must correlate with DB transaction and guard integrity |

### Avoid a Major Misconception

**Seeing an `UPDATE` in the statement log does not prove the `UPDATE` committed.** The statement might have failed or its transaction might have rolled back later.

Likewise, in-database row audit entries written in the same transaction record **committed** mutations once the transaction commits; they do not persist **rejected attempts**.

## 4. What Do PostgreSQL Server Logs Contain?

Depending on configuration and PostgreSQL version, server logs can contain:

- Successful logins, disconnections, and authentication failures.
- `ERROR`, `FATAL`, and `PANIC` messages plus context stacks.
- Statements selected by command class or execution duration.
- Deadlocks, lock waits, checkpoints, autovacuum, and replication events when enabled.
- Error context details, sometimes containing SQL text or sensitive parameters.
- Role names, database names, `application_name`, process IDs, and client endpoints.

**Server logs are not a default SQL table** you can query via `SELECT` to inspect history. PostgreSQL writes them to files, `stderr`, `syslog`, Windows event logs, or another configured destination.

### Design Question

Are your logs primarily for **troubleshooting** or **compliance auditing**? The two overlap yet are not identical:

- Troubleshooting highlights slow or failing statements.
- Compliance verifies which actions occurred and who was authorized.
- Forensics often correlates multiple independent sources while preserving integrity.

## 5. Choosing log_destination and logging_collector

An **illustrative reference configuration** in `postgresql.conf`:

~~~conf
# Reference example ONLY — DO NOT copy blindly to production.
log_destination = 'csvlog'
logging_collector = on
log_connections = on
log_disconnections = on
log_statement = 'ddl'
log_min_duration_statement = '500ms'
log_min_error_statement = error
log_line_prefix = '%m [%p] user=%u db=%d app=%a client=%r tx=%x '
~~~

### Meaning of Each Setting

- `csvlog`: structured columnar format convenient for log ingestion pipelines.
- `logging_collector`: lets PostgreSQL manage writing captured log streams to files.
- `log_connections`: records connection attempts/events per options and version.
- `log_disconnections`: records session disconnections.
- `log_statement='ddl'`: logs data-definition statements changing schema objects.
- `log_min_duration_statement='500ms'`: logs statements running at or beyond the configured threshold.
- `log_min_error_statement=error`: logs the SQL statement associated with errors meeting the severity threshold.
- `log_line_prefix`: adds correlation metadata to text log lines (structured formats capture corresponding fields separately).

### Pay Attention to Parameter Context

Parameters such as `logging_collector` or `shared_preload_libraries` require a **server restart**, not just a reload. Others allow reload or session/role overrides depending on `context`. Check `pg_settings.context` on your target PostgreSQL version rather than assuming `SELECT pg_reload_conf()` activates everything.

**The snippet above is educational, not a universal security baseline.** Logging slow queries or DDL can still expose sensitive SQL literals; strict PII environments may choose tighter thresholds or modes.

## 6. Comparing stderr, csvlog, and jsonlog

| Destination / Format | Strengths | Notes |
| --- | --- | --- |
| `stderr` + collector | Simple, widely supported | Needs parsing when shipped to SIEM |
| `csvlog` | Structured columns, easy ingestion | Protect files; handle CSV quoting properly |
| `jsonlog` | Structured JSON | Available since PostgreSQL 15; verify major version |
| `syslog` | Integrates with OS logging | Format, metadata, and permissions depend on OS |
| OS / event logging | Ties into host infra | Does not automatically supply business audit fields |

Choosing a structured format **does not sanitize sensitive data automatically**. JSON and CSV logs still record query text, parameters, PII, and error details just like plain text logs.

### Managing Log Files

- Store logs in directories with tight ACLs—never exposed via web servers.
- Configure rotation (`log_rotation_age`, `log_rotation_size` where applicable) to prevent disk exhaustion.
- Enforce retention limits and deletion rights per policy.
- Ship logs to centralized collectors for auditing and incident response.
- Encrypt storage/backups and protect transit channels to log collectors.

## 7. log_line_prefix: Useful Correlation, Not Proof of Human Identity

Example:

~~~conf
log_line_prefix = '%m [%p] user=%u db=%d app=%a client=%r tx=%x '
~~~

Common placeholders:

| Placeholder | Purpose |
| --- | --- |
| `%m` | Timestamp with milliseconds |
| `%p` | Backend process ID |
| `%u` | Database user |
| `%d` | Database name |
| `%a` | `application_name` |
| `%r` | Remote host and port |
| `%x` | Transaction ID (when assigned) |
| `%c` | Session ID for grouping session lines |
| `%l` | Per-session line sequence number |

A well-chosen prefix ties error entries back to a specific session and time window across busy concurrent workloads.

### Caveat

`application_name` is client-supplied and mutable mid-session. Use it to label services operationally, **not as tamper-proof proof of human identity**.

Similarly, the client IP often belongs to a load balancer, connection pooler, or app host rather than the end user's device.

## 8. log_statement: Which Level Makes Sense?

Common values:

| Value | General Meaning |
| --- | --- |
| `none` | Logs no statements via the `log_statement` rule |
| `ddl` | Logs data-definition statements |
| `mod` | Logs DDL plus data-modifying statements |
| `all` | Logs every statement matching scope |

### Risks of log_statement='all'

- Massive log volume with high I/O, CPU, and storage cost.
- Query strings with inline literals like `WHERE email = '...'` enter logs.
- Certain configurations or execution paths record bound parameters too.
- Administrative SQL or query syntax may reveal secrets.
- Expands sensitive-data footprint and audit review burden.

**Never turn on `log_statement='all'` in PII-heavy production simply because "we need auditing"** without a threat model, load benchmarks, retention policy, and log protection.

### A Logged Statement Does Not Prove Outcome

An `UPDATE` logged before completion may still:

- Violate a constraint.
- Hit a deadlock and abort.
- Be rolled back later in the transaction.
- Match 0 rows.
- Affect thousands of rows.

Server statement logs alone do not provide a complete row-change history.

## 9. log_min_duration_statement and Slow Queries

~~~conf
log_min_duration_statement = '500ms'
~~~

Records statements exceeding the threshold. Setting `-1` disables duration-based statement logging.

### Why Does PII Risk Remain?

A slow query might still look like:

~~~sql
-- ANTI-PATTERN: personal data literal embedded directly in SQL text.
SELECT *
FROM accounts
WHERE email = 'private-person@example.test';
~~~

Even with `log_statement='none'`, statements still get logged when slow or failing. **Parameterized queries stop SQL injection and omit literals from SQL text, yet do not guarantee logging pipelines never capture bound parameters.**

### Sampling

PostgreSQL offers duration sampling options in newer versions such as `log_min_duration_sample` and `log_statement_sample_rate`. Sampling cuts log volume, though by definition **sampling is not complete auditing**—specific security events can be missed.

## 10. Query Parameters Can Leak Through Logs Too

PostgreSQL versions provide controls capping logged parameter lengths, such as:

~~~conf
# Example suppressing parameter value logging where supported.
log_parameter_max_length = 0
log_parameter_max_length_on_error = 0
~~~

Verify parameter names and behavior against your **exact major version** and logging configuration.

### Never Promise "Parameterization Guarantees Secrets Stay Unlogged"

Prepared statements:

~~~sql
SELECT customer_id
FROM customers
WHERE email = $1;
~~~

Let us note carefully: in source line 277-281 it used `~~~sql`! Keep `~~~sql` exact. Let's make sure we don't mix fence styles anywhere.

Indeed:
Prepared statements keep the email literal out of the SQL template text. However:

- Drivers, servers, or APM agents may log bound parameters depending on configuration.
- Apps might log full request payloads prior to binding.
- Error contexts or details may include offending values.
- Dynamic SQL may still embed literals accidentally.
- `pg_stat_activity.query` and third-party monitors may expose recent statements.

When handling tokens or passwords, **never log raw values** and avoid passing raw secrets inside unnecessary SQL statements.

## 11. Other Logging Settings Worth Understanding Correctly

| Setting | Purpose | Trade-off / Risk |
| --- | --- | --- |
| `log_min_messages` | Server log severity threshold | Too verbose inflates volume |
| `log_min_error_statement` | Logs statement when error meets severity | Query text may hold sensitive data |
| `log_error_verbosity` | Error detail verbosity | `CONTEXT`/`DETAIL` may leak values |
| `log_lock_waits` | Logs long lock waits | Extra volume; does not replace concurrency analysis |
| `deadlock_timeout` | Controls deadlock check and lock-wait log delay | Affects deadlock detection, not purely logging |
| `log_checkpoints` | Checkpoint telemetry per version | Volume and I/O diagnostics |
| `log_autovacuum_min_duration` | Logs long autovacuum runs | Operational diagnostics, not access audit |
| `log_duration` | Logs durations of completed statements | Quickly spikes log volume |
| `log_temp_files` | Logs temporary spill files | Not evidence of PII access |

Enable settings deliberately per goal. Complete error logs **never replace `SELECT` auditing**, and complete `SELECT` auditing **never replaces latency monitoring**.

## 12. pgAudit: Statement-Level Audit Extension

**pgAudit** is a separate PostgreSQL extension—**not included in the core default installation everywhere**.

When installed and configured, pgAudit logs categorized operations such as:

- `READ`: `SELECT` and configured read actions.
- `WRITE`: `INSERT`/`UPDATE`/`DELETE`/`TRUNCATE` and configured writes.
- `DDL`: schema alterations.
- `ROLE`: role and privilege changes within scope.
- `FUNCTION`/`MISC`, and additional classes depending on pgAudit version.

### Strengths of pgAudit

- Provides richer structured audit records than basic `log_statement`.
- Categorizes SQL commands cleanly.
- Can log referenced objects under object-audit mode.
- Helps answer "who ran which operation class against which object".

### Limitations

- Does not record **the exact rows a `SELECT` returned**.
- Does not replace row-change audits when `OLD`/`NEW` state tracking is needed.
- Can still log sensitive object names, SQL text, or bound parameters.
- Increases log volume and I/O load.
- Availability depends on PostgreSQL/pgAudit major version, package support, and server setup.

**pgAudit is not a magic compliance switch.** You still need log ACLs, retention rules, integrity protection, and test coverage.

## 13. Configuring pgAudit: Never Overwrite Preloaded Libraries

Supported environments add `pgaudit` to `shared_preload_libraries` and restart PostgreSQL per extension docs.

**Illustrative configuration** example:

~~~conf
# Apply only after installing a version-compatible pgAudit package.
# NEVER overwrite existing libraries already needed by the server.
shared_preload_libraries = 'pgaudit'
pgaudit.log = 'read, write, ddl, role'
pgaudit.log_parameter = off
~~~

**Never blindly copy `shared_preload_libraries = 'pgaudit'`** onto a host already loading `pg_stat_statements` or monitoring agents—you would drop required libraries on restart. Always **append to the existing list** and verify compatibility and restart windows.

Once preloaded and installed:

~~~sql
-- Executed by DBA in target database with appropriate rights.
CREATE EXTENSION IF NOT EXISTS pgaudit;
~~~

Caveats:

- pgAudit packages may not exist on every managed PostgreSQL tier.
- Configuration mechanics vary across cloud providers.
- Different `pgaudit.*` settings carry distinct session vs. system scopes.
- `pgaudit.log_parameter = off` suppresses bound parameters in pgAudit entries without stopping other logging layers from capturing parameters.
- Verify real coverage through realistic tests in your target environment.

## 14. You Cannot Audit SELECT Using DML Triggers

A common misconception:

> "I'll add an AFTER SELECT trigger on customers so every read is logged."

PostgreSQL **has no regular row-level `SELECT` trigger** on tables analogous to `AFTER INSERT/UPDATE/DELETE`.

~~~sql
-- INTENTIONALLY INVALID; not legal PostgreSQL table trigger syntax:
CREATE TRIGGER audit_select
AFTER SELECT ON customers
FOR EACH ROW
EXECUTE FUNCTION audit_read();
~~~

To audit reads, combine:

1. Server statement logs or pgAudit `READ` logging.
2. Application/API access audits recording verified actors and resources.
3. Scoped view or function access layers where appropriate.
4. Connection and request-trace correlation.

### "SELECT Executed" Differs From "What Data Was Viewed"

A logged `SELECT * FROM customers WHERE status='active'` does not prove which rows the UI rendered or how many rows were actually returned to the end user.

Proving which business objects a user accessed typically requires API/service-tier auditing of authorized resource IDs—while still scoping logged IDs to prevent PII sprawl.

## 15. Application Logs Must Supply Business Identity

Connection pools typically share one DB role, such as `shop_api`, across many end users.

PostgreSQL sees:

~~~sql
SELECT
    session_user,
    current_user,
    current_setting('application_name', true) AS application_name;
~~~

- `session_user`: DB session authorization identity.
- `current_user`: active effective role; shifts under `SET ROLE` or `SECURITY DEFINER`.
- `application_name`: client-supplied, mutable label.

**None of these fields prove which human website user clicked a button.**

### Recommended Application Audit Event Shape

Log strictly necessary fields:

~~~json
{
  "event_type": "customer.status_changed",
  "actor_id": "user-42",
  "request_id": "req-7f31",
  "resource_type": "customer",
  "resource_id": "101",
  "old_status": "active",
  "new_status": "blocked",
  "result": "success"
}
~~~

This structure is synthetic—never treat example IDs as real data. **Do not include emails, national IDs, access tokens, or full request bodies** unless explicitly required and protected.

Derive the actor strictly from trusted authentication state, never blindly from a client-supplied `actor_id` field.

## 16. Request Correlation and Trust Boundaries

Services can pass a gateway/tracing request ID to correlate layers:

~~~text
request_id -> app audit -> DB session / transaction -> pgAudit/server log
~~~

In PostgreSQL, you can tag transaction-local metadata:

~~~sql
BEGIN;

SET LOCAL application_name = 'shop-api';

SET LOCAL app.request_id = 'req-lab-391';
SET LOCAL app.actor_id = 'user-42';

-- Business SQL statements run here.

COMMIT;
~~~

### Trust Boundary

`app.request_id` and `app.actor_id` are custom GUCs. Many session roles can assign arbitrary values to them.

Therefore:

- **Never use `current_setting('app.actor_id')` as primary authorization** if untrusted DB clients can overwrite it.
- Do not treat it as tamper-proof forensic proof.
- Have only trusted services/gateways set it, locking down DB credentials and privileges.
- With connection pooling, enforce `SET LOCAL` inside explicit transactions and verify reset behavior.
- For high-assurance non-repudiation, rely on signed/external trusted audit services.

## 17. pg_stat_activity Is a Point-in-Time Snapshot, Not History

~~~sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    client_addr,
    state,
    backend_start,
    xact_start,
    query_start,
    wait_event_type
FROM pg_stat_activity
WHERE datname = current_database();
~~~

`pg_stat_activity` reflects active/recent backend state at inspection time, not an append-only archive of every historical SQL statement.

### Handle the query Column Carefully

The `query` column displays current or most recent SQL text—potentially including sensitive literals. Visibility into other sessions' SQL is restricted by role privileges and predefined monitoring roles like `pg_read_all_stats`.

**Never grant broad monitoring roles to users who should not read raw queries.** Never expose `pg_stat_activity.query` on unguarded dashboards.

### An Idle State Does Not Mean No PII Was Touched

An `idle` session may well have queried PII moments earlier. Conversely, seeing a query in `pg_stat_activity` does not prove its results were delivered to a human viewer.

## 18. pg_stat_statements Is Not a Forensic Audit Log

`pg_stat_statements` aggregates normalized/fingerprinted query workload metrics: call counts, total execution time, buffer hits/reads, and related statistics per version.

It excels at:

- Optimizing frequent queries.
- Identifying CPU and I/O hotspots.
- Guiding index creation.
- Tracking performance trends over time.

It **never replaces**:

- Per-request auditing.
- Proof of every data read.
- Row-level `OLD`/`NEW` history.
- End-user business actor logs.

Restrict access to `pg_stat_statements` text and metrics appropriately. When enabling it alongside `pgaudit`, include both in `shared_preload_libraries` rather than dropping `pgaudit`.

## 19. Lab: Customer Table With Sensitive Data

Let us build an isolated practice schema containing:

- `customers`: identity and contact records.
- `change_audit`: records **mutation metadata only**, omitting email/phone values.
- A `SECURITY DEFINER` trigger function writing audit rows.
- A view exposing masked emails.

**Warning:** `DROP SCHEMA IF EXISTS sec_audit_lab CASCADE` deletes every object inside that schema. Run strictly in a **dedicated practice database**, never in production or alongside valuable data.

~~~sql
-- RUN IN LAB DATABASE ONLY.
DROP SCHEMA IF EXISTS sec_audit_lab CASCADE;
CREATE SCHEMA sec_audit_lab;

CREATE TABLE sec_audit_lab.customers (
    customer_id bigint PRIMARY KEY,
    display_name text NOT NULL,
    email text NOT NULL,
    phone text,
    status text NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'blocked', 'deleted')),
    created_at timestamptz NOT NULL
        DEFAULT transaction_timestamp(),
    updated_at timestamptz NOT NULL
        DEFAULT transaction_timestamp()
);

CREATE TABLE sec_audit_lab.change_audit (
    audit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL,
    operation text NOT NULL
        CHECK (operation IN ('INSERT', 'UPDATE', 'DELETE')),
    old_status text,
    new_status text,
    contact_changed boolean NOT NULL DEFAULT false,
    occurred_at timestamptz NOT NULL
        DEFAULT clock_timestamp(),
    db_session_role name NOT NULL,
    db_effective_role name NOT NULL,
    request_id text,
    actor_claim text,
    transaction_id bigint NOT NULL
);
~~~

### Why Omit a Foreign Key from change_audit.customer_id to customers.customer_id?

To preserve audit records after a customer row is deleted, a foreign key referencing `customers` would block or cascade-delete audit history depending on its action. Storing `customer_id` as historical metadata keeps delete trails intact.

**Omitting the FK does not mean audit data is implicitly trusted.** Still harden the audit trigger function and write grants strictly.

### Lab Fixture Data

~~~sql
INSERT INTO sec_audit_lab.customers (
    customer_id, display_name, email, phone, status
)
VALUES
    (101, 'Lan', 'lan@example.test', '+00-000-101', 'active'),
    (102, 'Minh', 'minh@example.test', '+00-000-102', 'active'),
    (103, 'Hoa', 'hoa@example.test', NULL, 'blocked');
~~~

`example.test` and the synthetic phone numbers represent no real people.

## 20. Designing Audit Tables Without Cloning PII

Convenient yet dangerous pattern:

~~~sql
-- ANTI-PATTERN on tables holding PII:
INSERT INTO audit_log(old_row, new_row)
VALUES (to_jsonb(OLD), to_jsonb(NEW));
~~~

When the source table contains emails, phone numbers, addresses, tax IDs, or tokens, this **duplicates sensitive data into audit tables**, which are often retained longer and read by broader operations teams.

Our lab keeps fields minimal:

- `customer_id`: business reference key (still personal data when correlated elsewhere).
- `operation`: `INSERT`/`UPDATE`/`DELETE`.
- `old_status`/`new_status`: status transitions only.
- `contact_changed`: boolean flag showing whether email or phone changed.
- Timestamp, DB session role, effective function role, and transaction ID.
- App-provided request and actor claims (marked clearly as **unverified against spoofing**).

### Trade-Off of Omitting Old/New Emails

You know "contact info was updated", without being able to reconstruct the exact previous email from `change_audit`. That is deliberate **data minimization**.

If legal or business compliance genuinely mandates tracking prior PII values, design separate encryption, strict ACLs, and short retention rather than dumping `to_jsonb(OLD)` blindly.

## 21. Writing a Scoped Audit Trigger

The PL/pgSQL function below uses `SECURITY DEFINER` so that under strict least privilege, the application role does not need direct `INSERT` grants on the audit table.

~~~sql
CREATE OR REPLACE FUNCTION sec_audit_lab.audit_customer_change()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, sec_audit_lab
AS $fn$
DECLARE
    v_customer_id bigint;
    v_old_status text;
    v_new_status text;
    v_contact_changed boolean := false;
    v_request_id text;
    v_actor_claim text;
BEGIN
    IF TG_OP = 'INSERT' THEN
        v_customer_id := NEW.customer_id;
        v_old_status := NULL;
        v_new_status := NEW.status;

    ELSIF TG_OP = 'UPDATE' THEN
        v_customer_id := NEW.customer_id;
        v_old_status := OLD.status;
        v_new_status := NEW.status;
        v_contact_changed :=
            OLD.email IS DISTINCT FROM NEW.email
            OR OLD.phone IS DISTINCT FROM NEW.phone;

    ELSIF TG_OP = 'DELETE' THEN
        v_customer_id := OLD.customer_id;
        v_old_status := OLD.status;
        v_new_status := NULL;

    ELSE
        RAISE EXCEPTION 'Unsupported trigger operation: %', TG_OP;
    END IF;

    -- Set by session/app; NOT tamper-proof proof of identity.
    v_request_id := nullif(
        left(current_setting('app.request_id', true), 100),
        ''
    );

    v_actor_claim := nullif(
        left(current_setting('app.actor_id', true), 100),
        ''
    );

    INSERT INTO sec_audit_lab.change_audit (
        customer_id,
        operation,
        old_status,
        new_status,
        contact_changed,
        db_session_role,
        db_effective_role,
        request_id,
        actor_claim,
        transaction_id
    )
    VALUES (
        v_customer_id,
        TG_OP,
        v_old_status,
        v_new_status,
        v_contact_changed,
        session_user,
        current_user,
        v_request_id,
        v_actor_claim,
        txid_current()
    );

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;

    RETURN NEW;
END;
$fn$;

CREATE TRIGGER trg_customers_90_audit
AFTER INSERT OR UPDATE OR DELETE
ON sec_audit_lab.customers
FOR EACH ROW
EXECUTE FUNCTION sec_audit_lab.audit_customer_change();
~~~

### Why Handle SECURITY DEFINER Carefully Here?

Inside `SECURITY DEFINER`, SQL executes under the **function owner's privileges**. That lets the app write to `customers` while the trigger writes to `change_audit` without granting the app direct `INSERT` on `change_audit`.

Ensure:

- The function owner is a tightly governed trusted role, never an app writer permitted to `ALTER FUNCTION`.
- `search_path` is pinned safely (never writable by untrusted roles).
- Target tables are schema-qualified.
- No untrusted dynamic SQL is constructed.
- `EXECUTE` privileges and trigger/DDL permissions are restricted.
- Runtime app roles neither own nor can alter the trigger function or audit table.
- Inside `SECURITY DEFINER`, `current_user` reflects the **function owner**, not the caller login.

### Why Avoid Storing Full OLD/NEW Payloads?

The trigger compares `OLD` and `NEW` in memory, persisting only status transitions and the `contact_changed` boolean—preventing PII replication across every update.

## 22. Are Inserts Run Before Creating the Trigger Audited?

No. Triggers react solely to DML events **occurring after trigger creation** (subject to enabled modes). The three seeded customers were inserted **before** creating the trigger, so no initial `INSERT` audit rows exist for them.

Operational takeaway:

- Never expect `CREATE TRIGGER` to retroactively scan past rows.
- If compliance needs an initial baseline, run a dedicated **backfill** step.
- Distinguish initial backfill snapshots from real-time `INSERT` events.
- Avoid fabricating "new events" with current timestamps that mislead incident investigators.

## 23. Testing UPDATE and Inspecting Audit Metadata

~~~sql
BEGIN;

SET LOCAL app.request_id = 'req-lab-391';
SET LOCAL app.actor_id = 'user-42';

UPDATE sec_audit_lab.customers
SET
    status = 'blocked',
    email = 'lan-updated@example.test',
    updated_at = clock_timestamp()
WHERE customer_id = 101;

SELECT
    audit_id,
    customer_id,
    operation,
    old_status,
    new_status,
    contact_changed,
    occurred_at,
    db_session_role,
    db_effective_role,
    request_id,
    actor_claim,
    transaction_id
FROM sec_audit_lab.change_audit
WHERE customer_id = 101
ORDER BY audit_id;

ROLLBACK;
~~~

Inside the transaction prior to rollback, expect:

| Field | Meaning |
| --- | --- |
| `customer_id` | `101` |
| `operation` | `UPDATE` |
| `old_status` | `active` |
| `new_status` | `blocked` |
| `contact_changed` | `true` |
| `request_id` | `req-lab-391` |
| `actor_claim` | `user-42` |
| `transaction_id` | Assigned transaction ID |
| `db_effective_role` | Function owner under `SECURITY DEFINER` |

**Neither the old nor new email is written into the audit table.**

### After ROLLBACK

Both the customer `UPDATE` and the new row in `change_audit` are undone. Note that the identity sequence behind `audit_id` remains incremented without rolling back sequence values; gaps in `audit_id` **do not prove committed audit rows were deleted**.

## 24. Testing INSERT and DELETE

~~~sql
BEGIN;

SET LOCAL app.request_id = 'req-lab-392';

INSERT INTO sec_audit_lab.customers (
    customer_id, display_name, email, status
)
VALUES (
    104, 'Demo', 'demo@example.test', 'active'
);

DELETE FROM sec_audit_lab.customers
WHERE customer_id = 104;

SELECT
    customer_id, operation, old_status, new_status
FROM sec_audit_lab.change_audit
WHERE customer_id = 104
ORDER BY audit_id;

ROLLBACK;
~~~

Within the transaction, expect:

- One `INSERT` audit row for customer `104`.
- One `DELETE` audit row for customer `104`.

After `ROLLBACK`, customer `104` and both audit rows disappear.

### DELETE and Data Privacy Policies

Retaining `customer_id` in audit history after row deletion helps investigations, yet that ID can still link back to an individual across external systems. Assess deletion obligations, retention rules, and re-identification risks carefully rather than assuming "ID-only means zero PII".

## 25. Same-Transaction Auditing: Benefits and Limits

**Benefits:**

- No customer mutation commits if a mandatory audit trigger fails with an unhandled exception.
- Business and audit rows commit atomically together.
- Full access to `OLD` and `NEW` values within DML context.
- Easily queried via SQL by ID and timestamp.

**Limitations:**

- Transaction rollback also rolls back the audit `INSERT`.
- DML triggers never observe `SELECT` reads.
- Table owners, superusers, or privileged DDL roles can disable triggers or alter audit rows.
- Audit tables add write, index, WAL, and autovacuum overhead.
- Not inherently tamper-proof against adversaries holding top DB/host privileges.

### Need to Audit Failed Attempts Too?

Use **application security logs, PostgreSQL server logs, or pgAudit** outside the DB transaction with independent storage controls. Never try catching an exception inside the trigger to `INSERT` into an audit table expecting it to survive an outer transaction rollback.

PostgreSQL PL/pgSQL trigger/exception blocks are **not autonomous transactions**.

## 26. Never Swallow Audit Errors Inside Triggers

Anti-pattern:

~~~sql
-- ANTI-PATTERN inside an audit trigger:
BEGIN
    INSERT INTO audit_table (...);
EXCEPTION
    WHEN OTHERS THEN
        NULL;
END;
~~~

If auditing is mandatory, silently swallowing failures lets business writes commit with zero audit trail, breaking compliance completely.

Even if auditing is configured best-effort, emit proper failure alerts and never rely on an in-transaction `EXCEPTION` handler to preserve external audit records.

**Your policy must state explicitly whether audit write failures block business writes**, and you should test disk-full, revoked-permission, constraint-failure, and disconnected-collector scenarios.

## 27. Separating Privileges Across PII Tables and Audit Tables

Ideally:

- App roles hold strictly needed row/column rights.
- App roles **never own** customer or audit tables.
- App roles lack direct `INSERT`/`UPDATE`/`DELETE` on audit tables.
- Audit trigger functions belong to an independent minimal owner.
- Auditor roles hold strictly `SELECT` on needed audit metadata.
- DBA and superuser sessions are monitored independently.
- Log shippers read log files per policy without automatically holding `SELECT` on all PII tables.

### Illustrative Role Model

The following statements create **cluster-wide** roles. Run only in an appropriate lab or governed environment, avoiding production naming collisions.

~~~sql
-- Run only under a role authorized to create roles.
CREATE ROLE sec391_writer NOLOGIN;
CREATE ROLE sec391_auditor NOLOGIN;

GRANT USAGE ON SCHEMA sec_audit_lab
TO sec391_writer, sec391_auditor;

GRANT SELECT (customer_id, display_name, status)
ON TABLE sec_audit_lab.customers
TO sec391_writer;

GRANT INSERT (customer_id, display_name, email, phone, status),
      UPDATE (display_name, status)
ON TABLE sec_audit_lab.customers
TO sec391_writer;

GRANT SELECT
ON TABLE sec_audit_lab.change_audit
TO sec391_auditor;
~~~

Here `sec391_writer` lacks direct `SELECT` on `email` or `phone`. Real apps map an authenticated login role carefully; our lab uses passwordless `NOLOGIN` roles to avoid embedding credentials in scripts.

### Does the Audit Trigger Work Without Direct Audit INSERT on the Writer?

With a properly configured `SECURITY DEFINER` trigger function, the trigger inserts into `change_audit` using the function owner's rights. **Never solve a `permission denied` error by granting the writer direct `INSERT`/`UPDATE`/`DELETE` on audit tables** without diagnosing trigger ownership and grants properly.

### Verifying Grants

~~~sql
SELECT
    has_table_privilege(
        'sec391_writer',
        'sec_audit_lab.change_audit',
        'INSERT'
    ) AS writer_can_insert_audit,
    has_table_privilege(
        'sec391_auditor',
        'sec_audit_lab.change_audit',
        'SELECT'
    ) AS auditor_can_read_audit;
~~~

In our clean lab without extra grants, expect `writer_can_insert_audit=false` and `auditor_can_read_audit=true`. Watch for group memberships, `PUBLIC` grants, or ownership modifying effective privileges in live clusters.

## 28. Risks Inside SECURITY DEFINER Audit Functions

`SECURITY DEFINER` runs with function-owner privileges, creating an escalation path if implemented carelessly.

Mandatory precautions:

1. Function owner must be a trusted role—never an app writer permitted to `ALTER FUNCTION`.
2. Pin a safe `search_path`, excluding schemas writable by untrusted users.
3. Schema-qualify critical tables and functions.
4. Never build dynamic SQL from untrusted fields without strict allowlists and quoting.
5. Restrict `EXECUTE` grants and trigger administration rights.
6. Never mistake `current_user` inside the function for the web login user.
7. Test under actual application roles rather than superuser alone.

### Why Is session_user Still Insufficient?

If 10,000 web users share one DB login `shop_api`, `session_user` equals `shop_api` for every request. Authenticate the human actor in the application and bind context reliably.

When high compliance demands non-repudiable human attribution, use external signed audit services rather than relying exclusively on mutable session GUCs.

## 29. Masking Views: Grant Access Strictly to the View

A reporting view can present masked email addresses:

~~~sql
CREATE VIEW sec_audit_lab.customer_public AS
SELECT
    customer_id,
    display_name,
    CASE
        WHEN position('@' IN email) > 0 THEN
            left(email, 1)
            || '***'
            || substring(email FROM position('@' IN email))
        ELSE '***'
    END AS masked_email,
    status
FROM sec_audit_lab.customers;
~~~

Example query:

~~~sql
SELECT customer_id, masked_email
FROM sec_audit_lab.customer_public
ORDER BY customer_id;
~~~

Expected output:

~~~text
101 | l***@example.test
102 | m***@example.test
103 | h***@example.test
~~~

### Masking Fails If Direct Base-Table SELECT Remains

If a role holds both `SELECT` on the view and `SELECT (email)` on the underlying table, it bypasses masking by querying the base table.

Enforce:

- Grant `SELECT` solely on the view to reporting roles needing it.
- Grant zero `SELECT (email)` access on the base table to those roles.
- Audit view ownership and RLS interaction.
- On PostgreSQL 15+, understand `security_invoker` vs. `security_barrier` semantics carefully when combining views with RLS and base-table grants.

**Masking emails in a view does not make data completely anonymous**. Email domains, IDs, and display names can still identify individuals.

## 30. RLS Does Not Replace Data Masking

**Row-level security (RLS)** answers: **which rows** may a role view?

**Column privileges / masking views** answer: **which columns or masked forms** may a role view?

Conceptual example:

~~~sql
-- Illustrative only; requires a table with tenant_id and proper trust model.
ALTER TABLE some_schema.customer_records
ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_read
ON some_schema.customer_records
FOR SELECT
USING (
    tenant_id = current_setting('app.tenant_id')::bigint
);
~~~

Do not execute verbatim without creating the table/schema. Remember `current_setting('app.tenant_id')` is **not a trusted tenant source** if untrusted sessions can `SET` it freely.

Also watch for owner/superuser/`BYPASSRLS` exceptions bypassing RLS; always include them in privilege audits.

If a role is authorized under RLS to read 1,000 rows yet should only see masked emails, **RLS never masks emails by itself**. Both controls address orthogonal axes.

## 31. Where Else Can Sensitive Data Appear?

Beyond core tables:

- Base tables and indexes.
- WAL, physical standbys, and replicas.
- Backups, snapshots, base backups, and PITR archives.
- Logical replication and CDC change streams.
- Temp spill files during sorts and hashes.
- Server logs, pgAudit logs, and application logs.
- Metrics, distributed traces, and error trackers.
- `pg_stat_activity.query` and query statistics views.
- SQL dumps and CSV exports.
- Test fixtures, staging clones, notebooks, and BI exports.
- Client logs and browser network captures.
- `psql` history, shell history, and CI output.
- Database error `DETAIL`/`CONTEXT` payloads.
- Audit tables storing raw `OLD`/`NEW` rows.

### Consequence

"Deleting a user's email from `customers`" **does not immediately erase copies in backups, logs, and audit tables**. Design explicit retention and purge workflows across every copy, aligned with legal obligations.

## 32. Data Classification and Minimization

Illustrative classification matrix:

| Class | Examples | Recommended Handling |
| --- | --- | --- |
| Public | Public product codes | Policy-aligned logging |
| Internal | Non-PII document IDs | Role-restricted logs |
| PII | Email, phone, physical address | Minimize, mask, short bounded retention |
| Highly sensitive | National IDs, financial, health records | Strict ACLs, encryption, access auditing |
| Auth secrets | Passwords, refresh tokens, API keys, private keys | Never log; secret manager and rotation |

Classification drives:

- Table, view, and log access privileges.
- Fields allowed inside audit records.
- Retention durations.
- Masking strictness.
- Third-party export policies.
- Data deletion workflows.

**Never cite "we need auditing" as an excuse to log all PII indiscriminately.** Capture strictly the minimum attributes serving a defined purpose.

## 33. Encryption Across Different Layers

| Mechanism | Primary Protection | Does Not Automatically Protect |
| --- | --- | --- |
| TLS client ↔ PostgreSQL | Data in transit over the wire | Authorized DB queries or downstream logs |
| Disk / volume encryption | Physical disk theft / offline snapshots | Valid SQL queries or DB superusers |
| Encrypted backups | Offloaded backup artifacts | Running DB servers or apps |
| Field-level encryption | Column values per cipher/key scope | Metadata or decrypted app responses |
| App-side encryption | Keeps field plaintext out of DB | App secrets/keys, metadata, blind indexes |
| HMAC / tokenization | Pseudonymous exact matching | Cross-dataset linkability if keys/designs leak |

### pgcrypto Helps Without Solving Key Management

PostgreSQL's `pgcrypto` extension offers encryption and hashing primitives. Yet when apps transmit both plaintext and decryption keys to PostgreSQL, both must still be protected in transit, in memory, and across logs.

**Column encryption never replaces access control, auditing, or key rotation.** Define where keys live, where decryption happens, and compromise recovery plans.

## 34. Hashing PII Does Not Equal Anonymization

Common anti-pattern:

~~~text
Store SHA256(email) in audit logs => completely anonymous data
~~~

False. Emails belong to guessable domains vulnerable to dictionary and brute-force attacks. Static hashes reused across systems also allow cross-system profile linking.

### Matching Without Storing Plaintext

Consider:

- Keyed HMAC with secrets managed securely outside the log store.
- Tokenization via a dedicated controlled service.
- Salting/peppering and rotation strategies matching data models.
- Storing purely a boolean like `contact_changed` when exact comparison is unnecessary.

Remember HMAC still counts as **pseudonymized data**, not irreversible anonymization—holders of the key or reference tables can re-link identities.

### Passwords Differ From PII Lookups

Passwords require dedicated work-factor salted password hashing / KDFs (such as Argon2id), never bare SHA-256 or reversible encryption. Never log passwords—or even password hashes unnecessarily.

## 35. Connection Between SQL Injection and Logging

JDBC / prepared statements separate SQL syntax from input values:

~~~java
String sql = """
    SELECT customer_id, status
    FROM sec_audit_lab.customers
    WHERE customer_id = ?
    """;

try (PreparedStatement statement =
        connection.prepareStatement(sql)) {

    statement.setLong(1, customerId);

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong("customer_id"));
        }
    }
}
~~~

### Avoid Secret-Logging Anti-Patterns

~~~java
// DO NOT:
logger.info("Lookup email=" + userEmail + ", token=" + token);

// DO NOT:
String sql = "SELECT * FROM customers WHERE email='" + userEmail + "'";
~~~

Prepared statements block SQL injection and omit raw literals from SQL templates. Still audit JDBC driver, DB server, and APM tracing settings so verbose logging does not print bound parameters.

**Never claim "our queries are parameterized, so sensitive values can never reach logs."**

## 36. SQL Comments and application_name Are Not Secret Stores

Frameworks often embed trace identifiers in SQL comments:

~~~sql
SELECT 1 /* request_id=req-lab-391 */;
~~~

If comments embed emails, tokens, or personal data, statement logs record them verbatim.

Similarly:

~~~sql
SET application_name = 'shop-api';
~~~

`application_name` appears across server logs, `pg_stat_activity`, and monitoring dashboards. Put only service names or approved non-sensitive labels there—never JWTs, emails, or session secrets.

### Guard Request IDs Too

Opaque random request IDs with bounded TTLs and scopes are great for correlation. If a request ID allows fetching sensitive records in an external observability store, enforce authorization there as well.

## 37. Auditing SELECTs at the Application Tier When Resource IDs Matter

An API endpoint such as:

~~~text
GET /customers/101
~~~

can emit an audit event:

~~~json
{
  "action": "customer.read",
  "actor_id": "user-42",
  "resource_id": "101",
  "result": "allowed",
  "request_id": "req-lab-393"
}
~~~

### Avoid Recording False Evidence

- Emit `allowed` strictly after authorization checks succeed.
- Reflect failures accurately if the query errors—never log "read success" unconditionally.
- Omit full response payloads.
- When batch reads touch many customer IDs, choose granularity matching business need and cost.
- Remember cache hits bypass PostgreSQL altogether; SQL auditing alone cannot track cached reads.

To prove which business records a human user read, **the application tier is indispensable** because it understands user identity, authorization, caches, and API responses.

## 38. Auditing DDL and Policy Changes

A breach can start with a privilege change such as:

~~~sql
GRANT SELECT ON TABLE sensitive_customers TO PUBLIC;
~~~

or:

~~~sql
ALTER TABLE sensitive_customers DISABLE ROW LEVEL SECURITY;
~~~

Audit trails must therefore cover **schema and privilege mutations**, not just row DML.

Useful sources:

- Server `log_statement='ddl'` (note not every role/grant command classifies uniformly as DDL across tools).
- pgAudit `DDL` and `ROLE` classes.
- Migration/change management records.
- PostgreSQL event triggers for supported DDL events.
- Periodic catalog snapshots reviewing roles, grants, and policies.
- CI/CD and cloud control-plane audit logs.

### Event Triggers Differ From DML Triggers

PostgreSQL provides `CREATE EVENT TRIGGER` for supported database-wide DDL events, not per-row `SELECT`/`UPDATE` auditing.

Event triggers carry constraints on supported event types, superuser/privilege requirements, and versions. They do not capture every configuration tweak or SQL command.

**Never attach a DML trigger to `customers` expecting it to catch `GRANT`, `ALTER ROLE`, or `CREATE EXTENSION`.**

## 39. Auditing High-Privilege Administrative Actions

DBAs, superusers, and object owners can modify ACLs, RLS, triggers, extensions, or server logging settings.

Consequently, an audit table stored **inside the same cluster** cannot guarantee immutability against an adversary holding superuser or host OS privileges.

Strengthen integrity with:

1. Shipping server logs off-host to a centralized service with separated write/read permissions.
2. Restricting rights to delete, alter, or stop log collectors.
3. Using immutable/WORM storage or cryptographic log signing where compliance demands it.
4. Enforcing synchronized clocks and trusted source metadata.
5. Alerting on edits to log configs, role grants, RLS flags, and `SECURITY DEFINER` routines.
6. Governing privileged access via approval workflows and session recording.
7. Preparing incident playbooks for suspected log tampering.

### Is an In-Database Hash Chain Enough?

A hash chain stored inside a DB table detects casual tampering, yet an admin with full control can alter rows and recompute the entire chain.

For strong tamper-evidence, **anchor digests outside the audited database's trust domain** or use independent append-only/WORM storage.

## 40. Retention Is a Security Decision

Keeping logs indefinitely creates serious risks:

- Enlarges breach exposure if log archives leak.
- Inflates storage, backup, and search costs.
- Conflicts with data deletion and minimization mandates.
- Slows search and incident triage across massive noise.
- Multiplies copies across SIEM, object storage, and exports.

### Define Clear Retention Policies

| Attribute | Question to Answer |
| --- | --- |
| Log type | Connection, SQL audit, row audit, or app audit? |
| Purpose | Incident response, operations, or compliance? |
| Duration | How long is legally/operationally justified? |
| Access | Who may read, export, or purge? |
| Storage | DB tables, local disk, SIEM, object buckets? |
| Deletion | Automated purge, backup expiry, legal holds? |
| Encryption | At rest, in transit, key lifecycle? |
| Governance | Who periodically reviews policy changes? |

**Never impose an arbitrary "universal standard" like 30 days or 7 years across every industry.** Align retention with specific legal, contractual, and risk obligations.

## 41. Personal Data Deletion Requests and Audit Trails

When a user requests data deletion, copies may live in:

- The `customers` row.
- `change_audit` rows referencing `customer_id`.
- Historical server logs containing email SQL literals.
- Backup snapshots.
- BI exports.
- Object storage CSV drops.
- Caches and search indexes.
- Downstream notification systems.

Deleting the `customers` row alone does not delete those downstream copies.

### Practical Approach

1. Maintain a comprehensive data inventory and flow map.
2. Document copy locations and retention schedules per system.
3. Separate data subject to mandatory erasure from records legally required for audit/fraud prevention.
4. Minimize or pseudonymize retained audit records per policy.
5. Enforce finite expiration windows on logs and backups.
6. Verify downstream exports, search indexes, and monitoring pipelines.
7. Record deletion completion evidence without logging redundant PII in the deletion log itself.

Exact rules depend on governing laws and contracts; consult legal counsel alongside engineering designs.

## 42. Verifying Log Pipelines Against Dropped or Duplicate Events

Centralized logging pipelines can suffer from:

- Network partitions.
- Log files rotating before shipping finishes.
- Collector restarts.
- Duplicate deliveries during retries.
- Clock skew between apps and PostgreSQL.
- Full agent queues dropping records.
- CSV/JSON parser errors.
- At-least-once agent delivery semantics.

Check:

- Do logs include sequences, offsets, or source metadata to detect gaps?
- Are timestamps formatted in standardized UTC with proper precision?
- Can event IDs or request IDs deduplicate retries?
- Do collector drops alert immediately—or pause critical flows if policy demands strict blocking?
- Are raw source logs preserved safely long enough to verify parsers?
- Who holds privileges to edit or delete pipeline configurations?

**A dashboard showing "zero alerts" proves nothing** if telemetry ingestion silently drops events.

## 43. Apply Log Masking at the Right Layer

Masking solely in the SIEM dashboard while leaving plaintext PII inside raw server log files still exposes data to anyone reading raw logs.

Apply controls progressively from source onward:

1. **Source minimization:** avoid putting PII in SQL literals, query comments, and app logs.
2. **Driver/app redaction:** scrub bodies, tokens, and credentials before logging.
3. **DB log settings:** restrict statement and parameter verbosity cleanly.
4. **Collector filtering:** drop or tokenize sensitive fields before forwarding.
5. **Storage ACLs/encryption:** protect both raw and processed logs.
6. **Dashboard masking:** show fields strictly per viewer role.
7. **Retention/purge:** expire logs promptly once unneeded.

Never rely solely on collector regex rules to catch every PII pattern—encoding, escaping, multi-line errors, and split fields bypass regex easily. Regex is defense-in-depth, not your primary shield.

## 44. Monitoring Signals That Should Trigger Alerts

High-value signals include:

- Spikes in authentication failures.
- Logins from unapproved sources or regions.
- Unusual spikes in `SELECT` volume against sensitive tables.
- Large batch exports or `COPY` operations.
- `GRANT`/`REVOKE`, `ALTER ROLE`, and RLS/privilege edits.
- Disabling `logging_collector`, pgAudit, or audit triggers.
- Elevated audit insert failures or unexpected transaction rollbacks.
- Log shipping lag or dropped-event metrics.
- Superuser sessions outside approved maintenance windows.
- Queries containing suspicious literal tokens or secrets.
- Abnormal response sizes returned from sensitive APIs.

### Reducing False Positives

- Separate approved migrations and backfills from ad-hoc activity.
- Track approved change windows explicitly.
- Baseline normal behavior per service role.
- Audit changes to alert rules and allowlists themselves.
- Avoid auto-blocking live production queries solely on noisy heuristic alerts without tested runbooks.

## 45. Incident Investigation Runbook

Suppose an employee is suspected of unauthorized access to sensitive records.

Standard steps:

1. Define the **time window**, affected hosts, and target tenant/resource IDs.
2. Preserve evidence immediately across server logs, pgAudit, app logs, and audit tables.
3. Align timestamps/timezones and capture the logging configuration active at the incident time.
4. Correlate `request_id`, `session_user`, `current_user`, backend PID/session ID, and client addresses.
5. Check effective grants, RLS policies, and memberships active **at the time of the event**, not solely current state.
6. Determine whether `SELECT` ran, whether results were cached/exported, and what the API actually returned.
7. Verify `COMMIT` vs. `ROLLBACK` outcomes for DML events.
8. Revoke compromised access and rotate exposed credentials promptly.
9. Maintain proper chain-of-custody records for preserved evidence.
10. Document findings clearly distinguishing **observed facts**, **reasonable inferences**, and **unproven gaps**.

**Never conclude "the user saw every customer record" solely because `SELECT *` appears in a statement log.** The query could have errored, returned empty results via RLS, or been dropped by the client.

## 46. SQL Queries to Inspect Active Logging Configuration

Read-only diagnostic queries:

~~~sql
SELECT
    name,
    setting,
    unit,
    context,
    source
FROM pg_settings
WHERE name IN (
    'log_destination',
    'logging_collector',
    'log_connections',
    'log_disconnections',
    'log_statement',
    'log_min_duration_statement',
    'log_min_error_statement',
    'log_line_prefix',
    'log_parameter_max_length',
    'log_parameter_max_length_on_error'
)
ORDER BY name;
~~~

### Meaning of Output Fields

- `setting`: effective setting value in the current query context.
- `unit`: unit if applicable.
- `context`: change level required (`postmaster`, `sighup`, `user`, `superuser`, etc.).
- `source`: configuration source supplying the value.

Older PostgreSQL major versions may lack newer parameters; `WHERE name IN (...)` cleanly omits unknown names without failing.

### Inspecting Installed Extensions

~~~sql
SELECT
    extname,
    extversion
FROM pg_extension
WHERE extname IN ('pgaudit', 'pg_stat_statements');
~~~

Absence of `pgaudit` in one database does not prove the OS package is missing—nor does its presence prove session auditing is properly preloaded and configured. Inspect `shared_preload_libraries`, active settings, and test logs directly.

## 47. Never Use pg_stat_activity for Long-Term History

A snapshot query:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    query_start
FROM pg_stat_activity;
~~~

shows only live backend state—never crash-persistent history or an event archive.

For durable history, use:

- Shipped server logs and pgAudit logs.
- Application-tier audit events.
- Trigger-based DML row audits.
- Structured log retention pipelines.

Never continuously poll `pg_stat_activity.query` and copy raw SQL strings into an unredacted table without evaluating secret duplication and overhead.

## 48. Auditing Trigger Catalog Definitions

~~~sql
SELECT
    tgname,
    tgenabled,
    pg_get_triggerdef(oid) AS trigger_definition
FROM pg_trigger
WHERE tgrelid = 'sec_audit_lab.customers'::regclass
  AND NOT tgisinternal
ORDER BY tgname;
~~~

Reports triggers currently attached to the table and their enabled status.

### Security Note

Anyone authorized to alter schemas or triggers can tamper with audit triggers. Manage DDL strictly via controlled migrations, separate owners from runtime roles, and monitor privileged changes.

Never inspect `tgenabled` today and assume every historical row change was audited—a trigger could have been disabled temporarily or bypassed via replication/maintenance modes earlier.

## 49. Cost of Row Auditing and Server Logs

Each `UPDATE` on `customers` triggering an audit row adds:

- An extra `INSERT` into the audit table.
- Extra WAL volume and dirty buffers.
- Index updates and disk growth.
- Autovacuum and retention purge load.
- Failure coupling if the audit table cannot be written.

Meanwhile, `log_statement='all'` or pgAudit `READ` at tens of thousands of QPS produces massive log streams stressing disk, network, collectors, and storage budgets.

### Measure With Realistic Tests

Lab write-impact measurement:

~~~sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL)
UPDATE sec_audit_lab.customers
SET
    status = CASE
        WHEN status = 'active' THEN 'blocked'
        ELSE 'active'
    END,
    updated_at = clock_timestamp()
WHERE customer_id = 101;

ROLLBACK;
~~~

**`EXPLAIN ANALYZE UPDATE` executes the `UPDATE` for real.** Run only inside a rolled-back lab transaction; `WAL` option requires PostgreSQL 13+.

Production concurrency, index counts, and collector throughput differ significantly from a tiny lab—never extrapolate synthetic timings blindly.

## 50. Separating Application Failures From DB Audit Evidence

An API returning HTTP 500 could stem from:

- Connection failure before reaching PostgreSQL.
- Permission denied.
- Constraint violation.
- Statement timeout or connection drop.
- Explicit application rollback.
- Serialization/deadlock failure awaiting retry.
- Downstream external API error after DB commit.

A DB audit row alone cannot tell the whole story. Investigations correlate:

- API outcome codes.
- DB transaction commit/rollback fate.
- DB server errors and statement logs.
- DML audit rows (if committed).
- External service logs and outbox state.
- Active roles and grants at incident time.

**Never report "the database committed the change" merely because a trigger ran prior to transaction rollback.**

## 51. Common Pitfalls

1. **Enabling `log_statement=all` permanently** on PII-rich systems without controlling volume or log access.
2. **Assuming prepared statements never leak parameters**, ignoring driver/server/error logging.
3. **Trying to audit `SELECT` with DML triggers**, when PostgreSQL has no regular row-level `SELECT` trigger.
4. **Dumping `to_jsonb(OLD)` and `to_jsonb(NEW)` on PII tables** into long-lived audit tables.
5. **Treating same-transaction audit `INSERT`s as durable proof of failed mutations**.
6. **Assuming audit triggers commit independently** when outer rollbacks undo them.
7. **Assuming audit tables are tamper-proof against superusers**.
8. **Equating `session_user`/`current_user` with human web users** behind shared connection pools.
9. **Trusting client-mutable `app.actor_id` GUCs** as proof of authorization.
10. **Granting app roles `UPDATE`/`DELETE` rights on audit tables**.
11. **Writing `SECURITY DEFINER` triggers with unsafe `search_path`**.
12. **Leaving `PUBLIC EXECUTE` open on privileged routines** without review.
13. **Enabling pgAudit without verifying packages, preload libraries, restarts, and live output**.
14. **Overwriting `shared_preload_libraries`** and dropping vital extensions like `pg_stat_statements`.
15. **Treating `pg_stat_activity` as a historical audit log** rather than a live snapshot.
16. **Treating `pg_stat_statements` as per-request auditing** rather than aggregated workload metrics.
17. **Confusing "statement logged" with "statement committed"**.
18. **Assuming a logged `SELECT` proves the user viewed every matching row**.
19. **Giving monitoring dashboards unrestricted access to raw query text and logs**.
20. **Masking logs solely in dashboards** while keeping raw secrets on disk.
21. **Claiming plain `SHA-256(email)` creates anonymous data**.
22. **Assuming disk encryption stops SQL roles or query logs from exposing data**.
23. **Forgetting WAL, backups, replicas, and exports** when handling deletion requests.
24. **Skipping log rotation and retention**, causing disk exhaustion or over-retained PII.
25. **Ignoring collector or log-shipping failures**, leaving unmonitored audit blind spots.
26. **Omitting request IDs and synchronized timestamps**, crippling correlation.
27. **Trusting `application_name` or SQL comments as security identity** despite client mutability.
28. **Failing to audit `GRANT`, `ALTER ROLE`, RLS edits, and disabled audit configs**.
29. **Swallowing trigger exceptions**, letting business mutations commit without required audits.
30. **Running `EXPLAIN ANALYZE UPDATE` in production as if read-only**, mutating live data.
31. **Testing solely as superuser**, missing runtime and auditor privilege failures.
32. **Conflating compliance auditing with query tuning/monitoring**.
33. **Adding an audit trigger later and expecting historical backfill automatically**.
34. **Overlooking index/GIN/WAL overhead on massive audit tables**.
35. **Lacking uniform privacy classification**, letting each service log PII inconsistently.

## 52. Practice Exercises With Answers

Use schema `sec_audit_lab` for SQL exercises. Perform error-inducing or mutating exercises strictly inside a lab database with transaction rollback where appropriate.

### Exercise 1. Do connection logs and data changes live in the same place?

**Answer:** Not automatically. Connection logs track sessions; row-level change auditing requires dedicated data-change tracking.

### Exercise 2. Does `log_statement='all'` prove `COMMIT` succeeded?

**Answer:** No. Statements can fail, affect zero rows, or roll back later in the transaction.

### Exercise 3. Is pgAudit always pre-installed in PostgreSQL?

**Answer:** No. Compatible packages, `shared_preload_libraries`, configuration, and `CREATE EXTENSION` are required.

### Exercise 4. Can DML triggers capture `SELECT` queries?

**Answer:** No. PostgreSQL lacks regular row-level `SELECT` triggers on tables; use pgAudit, server logs, or application access logs for read auditing.

### Exercise 5. Why avoid logging full `OLD`/`NEW` payloads?

**Answer:** It copies emails, phones, tokens, and other sensitive columns into audit storage, inflating breach risk and deletion complexity.

### Exercise 6. What should application audit logs capture?

**Answer:** Event type, verified actor ID, request ID, minimal resource ID, timestamp, and outcome—omitting secrets and bloated payloads.

### Exercise 7. Is `session_user` always the human website user?

**Answer:** Not behind connection pools where thousands of users share one database login.

### Exercise 8. Who is `current_user` inside a `SECURITY DEFINER` function?

**Answer:** Normally the function owner while the function executes, not the web caller.

### Exercise 9. Is `app.actor_id` tamper-proof?

**Answer:** No if callers can execute `SET` on custom GUCs. Rely on trusted gateway/app auth and proper identity bindings.

### Exercise 10. Testing Audit Trigger Rollback on UPDATE

~~~sql
BEGIN;

UPDATE sec_audit_lab.customers
SET status = 'blocked'
WHERE customer_id = 101;

SELECT COUNT(*) AS audit_rows_in_transaction
FROM sec_audit_lab.change_audit
WHERE customer_id = 101;

ROLLBACK;
~~~

**Answer:** The audit row inserted inside the transaction rolls back together with the `UPDATE`.

### Exercise 11. Why can `audit_id` exhibit numeric gaps?

**Answer:** Identity sequences advance even when transactions roll back. Sequence gaps do not prove audit rows were deleted.

### Exercise 12. Is creating a masked email view sufficient on its own?

**Answer:** No. If roles retain base-table `SELECT`, they can read raw emails directly; restrict grants and review RLS/view behavior.

### Exercise 13. Does RLS hide the `email` column?

**Answer:** RLS primarily restricts rows; use column privileges or masked views to restrict columns and presentation.

### Exercise 14. Does hashing emails with SHA-256 anonymize them?

**Answer:** Usually not. Emails are guessable and static hashes link records; consider threat modeling and keyed HMAC or tokenization.

### Exercise 15. What does SSL/TLS protect?

**Answer:** Network transit; it does not prevent authorized SQL queries or logging from exposing plaintext after DB decryption.

### Exercise 16. Does disk encryption stop DBAs from running `SELECT`?

**Answer:** No. It addresses offline storage media threats under your threat model, never SQL ACLs or RLS.

### Exercise 17. Does `pg_stat_activity` replace historical logs?

**Answer:** No. It displays current/recent backend activity snapshots rather than persistent request archives.

### Exercise 18. Does `pg_stat_statements` track individual user requests?

**Answer:** Not for forensic auditing; it aggregates normalized workload metrics.

### Exercise 19. What is `log_line_prefix` for?

**Answer:** Prepending timestamps, PIDs, roles, database names, app names, client endpoints, and session/transaction IDs for log correlation.

### Exercise 20. Should access tokens be placed inside `application_name`?

**Answer:** No. `application_name` enters server logs and monitoring views and is client-controlled.

### Exercise 21. Does `log_parameter_max_length=0` guarantee zero PII across all logs?

**Answer:** No. Inline SQL literals, app logs, error details, or other tools can still log values, and parameter behavior depends on PostgreSQL version.

### Exercise 22. What is the advantage of out-of-band auditing?

**Answer:** Persists evidence outside the main DB transaction and privilege domain, essential for capturing failed attempts and defending against rogue DB admins.

### Exercise 23. What should happen to a business `UPDATE` if the audit `INSERT` fails?

**Answer:** Depends on policy. If auditing is mandatory, unhandled errors should abort the mutation—never silence them with `WHEN OTHERS THEN NULL`.

### Exercise 24. Why is `log_statement=all` costly?

**Answer:** Generates heavy log volume, disk/network/parsing overhead, and high PII exposure; evaluate workload and scope carefully.

### Exercise 25. Why avoid logging full HTTP request bodies for troubleshooting?

**Answer:** Request bodies routinely hold tokens, passwords, and PII; log allowlisted metadata fields instead.

### Exercise 26. Does a logged SQL `SELECT` prove a user saw 1,000 rows?

**Answer:** No. RLS could filter rows, queries can error or return fewer rows, or results may come from caches or get dropped before UI display.

### Exercise 27. Which SQL query checks whether an audit trigger is currently enabled?

~~~sql
SELECT tgname, tgenabled
FROM pg_trigger
WHERE tgrelid = 'sec_audit_lab.customers'::regclass
  AND NOT tgisinternal;
~~~

**Answer:** Inspects current catalog metadata without proving historical continuity.

### Exercise 28. How do you check the reload/restart context of logging parameters?

~~~sql
SELECT name, setting, context, source
FROM pg_settings
WHERE name IN ('logging_collector', 'log_statement');
~~~

**Answer:** `context` shows whether changes require restart, reload, or session scope; cross-check against version docs.

### Exercise 29. How long should logs be retained?

**Answer:** According to operational purpose, legal/contractual obligations, data classification, and approved retention schedules—no single duration fits all systems.

### Exercise 30. Once a customer row is deleted, is a deletion request automatically finished?

**Answer:** Not necessarily. Evaluate audit tables, backups, WAL/replicas, exports, search indexes, and logs under governing deletion and retention rules.

### Exercise 31. Why shouldn't the app role own the audit table?

**Answer:** Owners can modify or drop data and table definitions; separating ownership shrinks impact if app credentials leak.

### Exercise 32. Do DDL event triggers replace pgAudit `READ` logging?

**Answer:** No. Event triggers fire on supported DDL events, never on `SELECT` queries.

### Exercise 33. What happens if the log collector falls behind or stops?

**Answer:** Pipelines risk lag, dropped events, or queue/disk exhaustion depending on architecture; monitor health, backpressure, and runbooks.

### Exercise 34. What sensitive data can appear in query error logs?

**Answer:** Inline SQL literals, logged parameters, `DETAIL`/`CONTEXT`, object names, and data values echoed in exceptions; restrict log access strictly.

### Exercise 35. Why audit changes to `GRANT` and RLS policies?

**Answer:** A single privilege or policy change can expose sensitive tables broadly without generating business row mutations.

### Exercise 36. How should incident investigation conclusions be framed?

**Answer:** Correlate independent sources, verify commit/grant/RLS/cache state, clearly separate directly observed facts from inferences and open gaps, and avoid overclaiming.

## 53. Security and Auditing Design Checklist

- [ ] Maintain an inventory of PII/sensitive data and clear logging purposes.
- [ ] Separate connection logs, statement logs, read access audits, row audits, and app traces.
- [ ] Define strict access controls for reading, exporting, and deleting logs.
- [ ] Never log passwords, tokens, private keys, or excess request payloads.
- [ ] Use bound parameters without assuming logging tools automatically scrub values.
- [ ] Review `log_statement`, `log_min_duration_statement`, and `log_min_error_statement`.
- [ ] Check PostgreSQL version and `pg_settings.context` before editing config or restarting.
- [ ] Standardize structured log formats, rotation, and controlled shipping.
- [ ] Keep `application_name` concise and free of sensitive data.
- [ ] Propagate request/trace IDs and maintain synchronized UTC clocks.
- [ ] Evaluate pgAudit package availability, preload impact, and workload overhead.
- [ ] Benchmark disk I/O and log volume before enabling high-volume `READ`/`WRITE` logging.
- [ ] Never attempt to audit `SELECT` queries with DML triggers.
- [ ] In row audits, allowlist columns rather than blindly logging `to_jsonb(OLD/NEW)`.
- [ ] Account for in-DB audits rolling back with caller transactions.
- [ ] Never swallow mandatory audit failures inside exception handlers.
- [ ] Separate writer, auditor, and owner privileges away from runtime apps.
- [ ] Harden `SECURITY DEFINER` triggers with trusted owners and safe `search_path`.
- [ ] Never trust caller-mutable custom GUCs as verified actor identity.
- [ ] Treat DB `session_user` separately from human/business actors.
- [ ] Restrict access to `pg_stat_activity.query` and workload statistics views.
- [ ] Combine column grants/masked views for column redaction with RLS for row scope.
- [ ] Encrypt network transit, storage/backups, and manage keys per threat model.
- [ ] Never equate bare SHA-256 PII hashes with true anonymization.
- [ ] Track copies across WAL, backups, replicas, exports, caches, and log pipelines.
- [ ] Assign ownership to retention, deletion, and legal-hold policies.
- [ ] Monitor pipeline lag, event gaps, duplicates, and logging config changes.
- [ ] Audit `GRANT`, `ALTER ROLE`, RLS/trigger edits, and admin operations.
- [ ] Maintain an incident response runbook and evidence preservation workflow.
- [ ] Test under real application and auditor roles, not solely superuser.
- [ ] Benchmark trigger write cost, I/O, WAL growth, and p95/p99 latency.
- [ ] Verify committed DML, rolled-back DML, failed statements, and `SELECT` paths independently.
- [ ] Never run `DROP SCHEMA` or `EXPLAIN ANALYZE` DML in production.

## 54. Official PostgreSQL Documentation

Always consult documentation matching your **exact server major version** and vendor extension guides:

- [Error Reporting and Logging](https://www.postgresql.org/docs/current/runtime-config-logging.html) — `log_destination`, `logging_collector`, `log_statement`, `log_line_prefix`, parameter logging, and rotation.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring.html) — monitoring and statistics collectors.
- [The pg_stat_activity View](https://www.postgresql.org/docs/current/monitoring-stats.html) — live session metadata and visibility rules.
- [Client Authentication](https://www.postgresql.org/docs/current/client-authentication.html) — connection authentication.
- [Database Roles](https://www.postgresql.org/docs/current/user-manag.html) — roles and attributes.
- [Privileges](https://www.postgresql.org/docs/current/ddl-priv.html) — object access privileges.
- [Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) — RLS, policies, and bypass exemptions.
- [PL/pgSQL Trigger Functions](https://www.postgresql.org/docs/current/plpgsql-trigger.html) — `OLD`, `NEW`, and `TG_OP`.
- [CREATE TRIGGER](https://www.postgresql.org/docs/current/sql-createtrigger.html) — DML trigger events and limits.
- [Event Triggers](https://www.postgresql.org/docs/current/event-triggers.html) — auditing/handling DDL events.
- [CREATE FUNCTION](https://www.postgresql.org/docs/current/sql-createfunction.html) — `SECURITY DEFINER` and routine security.
- [Function Security](https://www.postgresql.org/docs/current/perm-functions.html) — safe `search_path` and privilege hygiene.
- [The pg_stat_statements Module](https://www.postgresql.org/docs/current/pgstatstatements.html) — aggregated query workload statistics.
- [SSL Support](https://www.postgresql.org/docs/current/ssl-tcp.html) — TLS transport security.
- [pgcrypto](https://www.postgresql.org/docs/current/pgcrypto.html) — DB-side encryption/hashing primitives and caveats.
- [Backup and Restore](https://www.postgresql.org/docs/current/backup.html) — backup and PITR recovery.
- [System Catalog pg_trigger](https://www.postgresql.org/docs/current/catalog-pg-trigger.html) — trigger metadata.
- [System View pg_settings](https://www.postgresql.org/docs/current/view-pg-settings.html) — runtime parameters and reload contexts.
- [pgAudit project documentation](https://github.com/pgaudit/pgaudit) — extension details, version compatibility, and configuration.

The `/current/` URLs point to current PostgreSQL docs. Logging options, `jsonlog`, pgAudit, monitoring grants, settings, and event triggers vary across versions—verify against your live deployment version.

## 55. Summary

**Auditing succeeds when it captures the right events, ties them to trustworthy identities, records sufficient context without copying excess secrets, and protects the integrity of the trail itself.**

Core principles to keep in mind:

1. **Server logs, pgAudit, row audits, and application audits complement one another**; no single layer replaces all others.
2. **DML triggers record `INSERT`/`UPDATE`/`DELETE` mutations, never ordinary `SELECT` reads.** Combine DB and app logging to cover reads.
3. **In-DB audit triggers share the caller's transaction:** rolling back business work rolls back the audit rows too. Persist denied or failed attempts outside the DB transaction.
4. **Never log raw `OLD`/`NEW` payloads from PII tables** when status and change flags suffice.
5. **Never crank up full statement and parameter logging blindly**: logs quickly become a secondary secrets store.
6. **Prepared statements protect SQL grammar without guaranteeing logs exclude parameters**.
7. **Treat `session_user`, `current_user`, `application_name`, and custom request claims realistically.** None inherently prove web user identity.
8. **RLS, column privileges, masking views, and `SECURITY DEFINER` serve distinct roles**; design them together and test with real roles.
9. **Encryption, keyed HMAC, retention, and data inventories** belong inside your logging/audit design from day one, never as afterthoughts.
10. **Audit tables inside the same DB cannot withstand high-privilege admin tampering alone**; isolate logs off-host when tamper resistance matters.
11. **Monitor pipeline health and privilege/policy changes** so audit trails cannot quietly vanish or get disabled.
12. **Investigations must clearly separate logged SQL statements, committed state, API responses, and proven human actions**.

By combining the right observability layers, minimizing sensitive data at the source, and maintaining strong governance, PostgreSQL supports rigorous auditing and incident forensics without turning your logs into the next breach.
