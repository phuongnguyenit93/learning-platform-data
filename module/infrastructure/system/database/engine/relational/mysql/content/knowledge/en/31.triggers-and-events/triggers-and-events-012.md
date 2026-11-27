# Choosing Constraints, Triggers, Events, or Application-Side Jobs

A business rule can be enforced in multiple places: constraints in the schema, triggers firing on writes, scheduled events, or jobs orchestrated by the application. Choosing the wrong place often produces inconsistent data, hard-to-trace side effects, duplicate jobs, or duplicated logic across multiple services.

Start by asking: does the rule need protection on every data write, an immediate reaction when a row changes, scheduled execution over time, or orchestration of a business workflow outside the database? Constraints are the first choice for data invariants that MySQL can express. Triggers fit synchronous reactions inside DML and database-only side effects. The Event Scheduler handles simple periodic jobs inside MySQL. Application jobs fit workflows requiring retries, observability, external service calls, or multi-step coordination.

This lesson belongs to the `DATABASE_MYSQL` module, where you master table design, data types, keys, SQL queries, indexes, transactions, concurrency control, execution plan reading, query tuning, and relational database operations. The goal is to place each rule in the right layer, understand transaction and security boundaries, and verify behavior when multiple applications write concurrently.

After this lesson, you will be able to:

- Distinguish constraints, triggers, the Event Scheduler, and application jobs.
- Choose `PRIMARY KEY`, `UNIQUE`, `NOT NULL`, `FOREIGN KEY`, and `CHECK` for data invariants.
- Recognize when a generated column or explicit DML statement is better than a trigger.
- Use triggers for row validation, internal auditing, or controlled secondary data updates.
- Understand that triggers execute row by row, sharing the invoking statement's transaction on transactional tables.
- Schedule simple tasks with the MySQL Event Scheduler.
- Choose application jobs for retries, queues, API calls, and multi-step workflows.
- Prevent duplicate job runs during replication, failover, or multi-worker processing.
- Design idempotency, observability, least privilege, and operational procedures.

## 1. Four Mechanisms Solving Four Categories of Problems

| Mechanism | When Does It Run? | Scope | Best Used For | Main Limitations |
| --- | --- | --- | --- | --- |
| Constraint | Checked during relevant INSERT/UPDATE/DELETE | Data invariants in schema | PK, uniqueness, FK relationships, value domains, single-row conditions | Cannot express all multi-table rules or workflows |
| Trigger | Synchronously with INSERT/UPDATE/DELETE on a table | Each affected row | In-DB auditing, OLD/NEW normalization/validation, secondary writes in same transaction | Hidden logic, per-row execution, restrictions, adds DML latency |
| Event Scheduler | At a scheduled time or interval | MySQL server and database | Simple periodic cleanup, aggregation, or maintenance | Depends on scheduler/definer/topology; limited retry/observability |
| Application job | By queue, schedule, or application event | Service/worker and external systems | Sending notifications, calling APIs, retries, multi-step workflows, distributed coordination | Requires designing retries, idempotency, privileges, and worker reliability |

These mechanisms can work together, but you should not enforce the same rule redundantly across multiple layers in conflicting ways. For example, a constraint protects `quantity > 0`; a trigger logs status-change audits; an outbox stores events to emit; an application worker sends notifications; and the Event Scheduler only purges expired data on a schedule.

## 2. Decision Workflow

Classify requirements by nature:

1. **Invariants that must hold across every write path:** prefer constraints. Data may be written from APIs, batch jobs, migrations, operational scripts, or other applications; constraints protect all those paths.
2. **Synchronous reaction to a single row's change:** consider a trigger if the logic must run inside the same statement/transaction and only touches the database.
3. **Tasks running hourly/daily:** use the Event Scheduler if the task is small, self-contained, operates solely on MySQL data, and fits the server's operational model. If retries, monitoring, or cross-system coordination are needed, use an application scheduler/queue.
4. **Multi-step workflows or external side effects:** place in the application. Use transactions/outbox to record the intent to emit, then let workers process with retries and idempotency.

Do not pick triggers just to "automate" everything. A trigger causes a DML operation to perform extra work invisible in the SQL statement itself. Do not pick the Event Scheduler just to run periodic SQL if your organization already has a centralized job platform with monitoring and coordination.

## 3. Constraints: First Choice for Data Invariants

Constraints are rules declared in the schema. MySQL enforces them whenever data is written, regardless of which application sends the statement.

### 3.1. NOT NULL and DEFAULT

`NOT NULL` prevents a column from accepting NULL. `DEFAULT` supplies a fallback value when INSERT omits the column or uses the DEFAULT keyword; DEFAULT does not replace a domain-checking constraint.

```sql
CREATE TABLE inventory_item (
    item_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    sku VARCHAR(40) NOT NULL,
    quantity INT UNSIGNED NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (item_id),
    UNIQUE KEY uq_inventory_item_sku (sku),
    CONSTRAINT chk_inventory_quantity_nonnegative
        CHECK (quantity >= 0)
) ENGINE = InnoDB;
```

The schema guarantees SKU is non-NULL and unique, and quantity is non-NULL and non-negative. The application does not have to verify these invariants manually before every INSERT; the application should still validate early for friendly messages while the database acts as the final safeguard.

### 3.2. PRIMARY KEY and UNIQUE

- `PRIMARY KEY` uniquely identifies each row and disallows NULL.
- `UNIQUE` prevents duplicate values within the unique key.
- In MySQL, a unique index can contain multiple rows with NULL in nullable columns; NULLs are not treated as equal under standard unique comparisons. If business rules require a value, combine with `NOT NULL`.

```sql
CREATE TABLE app_user (
    user_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(255) NOT NULL,
    external_ref VARCHAR(80) NULL,
    PRIMARY KEY (user_id),
    UNIQUE KEY uq_app_user_email (email),
    UNIQUE KEY uq_app_user_external_ref (external_ref)
) ENGINE = InnoDB;
```

Email cannot be NULL or duplicated. `external_ref` may be NULL; multiple rows without an external reference can coexist. If the rule requires external_ref to always exist and be unique, make the column NOT NULL.

### 3.3. FOREIGN KEY

Foreign keys protect relationships between child and parent tables. They prevent child rows from referencing non-existent parent keys while defining behavior when parent rows are deleted or updated.

```sql
CREATE TABLE sales_order (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    order_date DATETIME NOT NULL,
    order_status VARCHAR(20) NOT NULL DEFAULT 'OPEN',
    PRIMARY KEY (order_id),
    KEY idx_sales_order_customer (customer_id),
    CONSTRAINT fk_sales_order_customer
        FOREIGN KEY (customer_id)
        REFERENCES customer (customer_id)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT
) ENGINE = InnoDB;
```

Choose `RESTRICT`, `CASCADE`, or `SET NULL` according to business semantics. Do not use CASCADE just for convenient deletion if child data must be retained for audits or reporting. Ensure appropriate indexes exist for foreign keys to support checks and joins efficiently.

### 3.4. CHECK

CHECK suits conditions evaluated on the current row:

```sql
CREATE TABLE product_price (
    product_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    list_price DECIMAL(12, 2) NOT NULL,
    discount_price DECIMAL(12, 2) NULL,
    CONSTRAINT chk_list_price_nonnegative CHECK (list_price >= 0),
    CONSTRAINT chk_discount_valid CHECK (
        discount_price IS NULL
        OR (discount_price >= 0 AND discount_price <= list_price)
    )
) ENGINE = InnoDB;
```

MySQL enforces CHECK constraints starting in version 8.0.16. Earlier versions may parse the syntax without enforcing the constraint as expected; always verify server version and `SHOW CREATE TABLE` when deploying schemas. CHECK is not a place to query other tables, call services, or enforce rules requiring multiple rows.

### 3.5. When Constraints Are Not Enough

Constraints fit rules expressible directly in the schema: a row must hold valid values, a key must be unique, or an FK relationship must exist. Rules like "the sum of all unpaid orders must not exceed the customer's budget" require multi-row coordination and concurrency control. Checking with a SELECT before INSERT is unsafe because two transactions can pass the check concurrently.

For multi-row rules, design appropriate transactions and locking, use an atomically updated summary/ledger row, or serialize through a business workflow. Triggers alone do not eliminate race conditions.

## 4. Prefer Generated Columns or Explicit DML Before Triggers

Some automation needs do not require triggers:

- Default values: use `DEFAULT`.
- Values derived from columns in the same row: use a generated column if the expression and requirements fit.
- Values known to the application: pass directly in INSERT/UPDATE.
- Aggregated data updated by a workflow: consider explicit DML inside a transaction or a summary table with a refresh job.

Generated column example:

```sql
CREATE TABLE order_line (
    line_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    quantity INT UNSIGNED NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    line_total DECIMAL(14, 2)
        GENERATED ALWAYS AS (quantity * unit_price) STORED,
    PRIMARY KEY (line_id),
    CONSTRAINT chk_order_line_quantity CHECK (quantity > 0),
    CONSTRAINT chk_order_line_price CHECK (unit_price >= 0)
) ENGINE = InnoDB;
```

`line_total` is always derived from quantity and unit_price. No trigger is needed to copy the calculation into a regular column; generated columns express the data relationship directly in the schema.

## 5. Triggers: Synchronous Reaction to Row Changes

A trigger attaches to one table and one event: `INSERT`, `UPDATE`, or `DELETE`. MySQL triggers execute per row (`FOR EACH ROW`), with timing `BEFORE` or `AFTER`.

| Timing | Readable | Modifiable | Common Purpose |
| --- | --- | --- | --- |
| BEFORE INSERT | `NEW` | Assign values to `NEW` | Normalize or validate row about to be inserted |
| AFTER INSERT | `NEW` | Cannot edit source row via NEW | Write audit or secondary row after successful insert |
| BEFORE UPDATE | `OLD`, `NEW` | Assign values to `NEW` | Validate state transitions or normalize |
| AFTER UPDATE | `OLD`, `NEW` | Cannot edit source row via NEW | Record change history |
| BEFORE DELETE | `OLD` | Cannot edit OLD | Validate before deletion |
| AFTER DELETE | `OLD` | Cannot edit OLD | Write audit or update secondary data |

### 5.1. BEFORE Trigger Validating Changes

Example allowing transitions from OPEN only to PAID or CANCELLED, and blocking modifications to finalized orders:

```sql
DELIMITER //

CREATE TRIGGER bu_sales_order_status
BEFORE UPDATE ON sales_order
FOR EACH ROW
BEGIN
    IF OLD.order_status IN ('PAID', 'CANCELLED')
       AND NEW.order_status <> OLD.order_status THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'A completed order cannot change status';
    END IF;

    IF NEW.order_status NOT IN ('OPEN', 'PAID', 'CANCELLED') THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Unsupported order status';
    END IF;
END//

DELIMITER ;
```

Triggers can read OLD and NEW to compare states. However, if you only need to check an allowed value set, CHECK is usually simpler and clearer. The trigger here illustrates a state-transition rule referencing the old value.

### 5.2. AFTER Trigger Writing Audits

Audit logs are a good use case when changes must be recorded in the same transaction as the source data.

```sql
CREATE TABLE sales_order_status_audit (
    audit_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    old_status VARCHAR(20) NOT NULL,
    new_status VARCHAR(20) NOT NULL,
    changed_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    connection_account VARCHAR(288) NOT NULL,
    PRIMARY KEY (audit_id),
    KEY idx_order_status_audit_order_time (order_id, changed_at)
) ENGINE = InnoDB;
```

```sql
DELIMITER //

CREATE TRIGGER au_sales_order_status_audit
AFTER UPDATE ON sales_order
FOR EACH ROW
BEGIN
    IF NOT (OLD.order_status <=> NEW.order_status) THEN
        INSERT INTO sales_order_status_audit (
            order_id,
            old_status,
            new_status,
            connection_account
        )
        VALUES (
            NEW.order_id,
            OLD.order_status,
            NEW.order_status,
            USER()
        );
    END IF;
END//

DELIMITER ;
```

The `<=>` operator is MySQL's NULL-safe equality comparison. `USER()` records the connection account observed by the server; it is not necessarily the application end-user identity. If a business actor is needed, the application must pass context from a trusted source and control who may set it. Never treat an arbitrary client-set session variable as verified proof.

With InnoDB, the audit INSERT and source row UPDATE share the same transaction. If writing the audit fails, the source update statement also fails; if the transaction rolls back, the audit row rolls back too. That is the benefit of internal side effects inside the same database transaction.

## 6. Important Limitations of Triggers

- Triggers run row by row; there are no statement-level triggers. An UPDATE affecting 100,000 rows can invoke the trigger 100,000 times.
- Triggers cannot return a result set directly to the client. Use `SIGNAL` to reject statements with explicit errors.
- Triggers cannot manage transactions themselves via `START TRANSACTION`, `COMMIT`, or `ROLLBACK`.
- Triggers cannot modify a table already in use by the firing statement in a way that causes mutating-table errors; design to avoid updating the source table inside its own trigger.
- Never use triggers to make HTTP calls, send emails, or perform side effects outside MySQL. A database transaction cannot roll back an HTTP request already sent.
- Triggers cannot attach to views or temporary tables; define triggers on appropriate base tables.
- `TRUNCATE TABLE` does not fire DELETE triggers. Deletions/updates performed by foreign key cascades also do not fire corresponding triggers.
- Triggers have restrictions on dynamic SQL, result sets, and permitted statements; consult the Reference Manual for your version before adding complex logic.
- Triggers are hidden logic to anyone reading only an INSERT/UPDATE statement. Document them clearly and monitor performance.

MySQL supports multiple triggers on the same table, timing, and event. You can use `FOLLOWS` or `PRECEDES` to define relative ordering when creating a new trigger. Do not split a single rule across multiple order-dependent triggers if it can be kept cleanly in one trigger.

### 6.1. Triggers Do Not Automatically Solve Race Conditions

Suppose you must ensure total reserved items do not exceed available stock. A trigger reading `available_stock`, checking, and writing a reservation can hit a race condition if two transactions read the quantity before either updates it.

The solution must rely on atomic operations and proper locking, for example:

```sql
UPDATE inventory
SET available_quantity = available_quantity - p_quantity
WHERE product_id = p_product_id
  AND available_quantity >= p_quantity;
```

Then check affected rows in the same transaction. If zero rows were updated, stock is insufficient. The UPDATE both checks the condition and modifies the value under InnoDB's locking mechanism. Triggers are no substitute for this concurrency design.

## 7. Event Scheduler: Scheduled Tasks Inside MySQL

An Event is a database object executed by the MySQL Event Scheduler at a specific time or on a recurring interval. It fits simple periodic tasks operating solely on data inside the same server, such as batch-deleting expired sessions or refreshing a summary table.

### 7.1. Checking the Scheduler

```sql
SHOW VARIABLES LIKE 'event_scheduler';
```

Common values:

- `ON`: Event Scheduler is active and can run enabled events.
- `OFF`: scheduler is not running events; events can still exist.
- `DISABLED`: scheduler is disabled at startup and cannot be re-enabled by ordinary runtime changes.

Enabling the scheduler requires appropriate administrative privileges and supportive server configuration. In production, toggling it belongs in a DBA runbook—never let an application arbitrarily alter global variables.

### 7.2. Creating a Recurring Event

Example deleting at most 1,000 expired sessions every 5 minutes:

```sql
CREATE EVENT ev_purge_expired_sessions
ON SCHEDULE EVERY 5 MINUTE
STARTS CURRENT_TIMESTAMP + INTERVAL 5 MINUTE
ON COMPLETION PRESERVE
ENABLE
DO
    DELETE FROM app_session
    WHERE expires_at < CURRENT_TIMESTAMP
    ORDER BY expires_at
    LIMIT 1000;
```

Index `expires_at`:

```sql
CREATE INDEX idx_app_session_expires_at
ON app_session (expires_at);
```

Batch limits reduce single-run duration as well as lock and undo overhead. If deleting 1,000 rows per run cannot keep pace with expired session creation, the backlog will grow; monitor backlog size and tune interval/batch size.

### 7.3. One-Time Events and Recurring Events

Run once at a specific time:

```sql
CREATE EVENT ev_rebuild_monthly_summary
ON SCHEDULE AT '2026-12-01 02:00:00'
ON COMPLETION NOT PRESERVE
DO
    CALL sp_rebuild_monthly_summary();
```

Run repeatedly:

```sql
CREATE EVENT ev_refresh_daily_summary
ON SCHEDULE EVERY 1 DAY
STARTS '2026-11-20 02:00:00'
ON COMPLETION PRESERVE
DO
    CALL sp_refresh_daily_summary();
```

The examples assume both procedures exist, hold proper execution privileges, and perform their work without relying on a client reading a result set. Events have no interactive client consuming results like an API call. Nor do events accept input parameters like an API; if configuration is needed, store settings in a table or call a procedure that reads controlled configuration.

### 7.4. Managing and Monitoring Events

```sql
SHOW EVENTS FROM reporting_db;

SELECT
    EVENT_NAME,
    DEFINER,
    TIME_ZONE,
    EVENT_TYPE,
    EXECUTE_AT,
    INTERVAL_VALUE,
    INTERVAL_FIELD,
    STATUS,
    LAST_EXECUTED
FROM INFORMATION_SCHEMA.EVENTS
WHERE EVENT_SCHEMA = 'reporting_db';
```

Pause and re-enable:

```sql
ALTER EVENT ev_purge_expired_sessions DISABLE;
ALTER EVENT ev_purge_expired_sessions ENABLE;
```

Drop an event:

```sql
DROP EVENT IF EXISTS ev_purge_expired_sessions;
```

`LAST_EXECUTED` shows the most recent run, not a complete history of all runs. If you need run history, processed row counts, duration, errors, and retries, write structured logs to an operational table or use an external monitoring system.

## 8. Limitations and Risks of the Event Scheduler

- Events only run when `event_scheduler` is ON and the event is ENABLED.
- Events execute in their definer's context; the definer must exist and hold required privileges for statements in the event/called procedure.
- Events do not accept parameters like an API; configuration data is typically read from tables.
- Events do not natively provide retry queues, exponential backoff, dead-letter queues, or job dashboards like a dedicated worker platform.
- Event bodies still consume server CPU, I/O, locks, and connections/threads; a heavy job can impact transactional workloads.
- Schedules run per server/database; you must define time zones and behavior during server stops or failovers.
- Never assume an event runs strictly once in every HA scenario. Design jobs to be idempotent and designate which node is permitted to run the scheduler.
- Events can call procedures, yet procedures must obey stored-program and transaction rules.

The privilege to create/manage events is `EVENT` on the schema. Grant it intentionally and manage definers as operational identities with clear lifecycles.

## 9. Application Jobs: Application-Orchestrated Workflows

Application jobs fit when tasks must interact with multiple systems or demand stronger operational capabilities than the Event Scheduler:

- Sending emails, SMS, push notifications, or calling HTTP APIs.
- Processing files, object storage, or payment gateways.
- Running stateful multi-step workflows with retries and dead-letter queues.
- Distributing work across multiple workers and tuning concurrency.
- Requiring dashboards, tracing, alerts, SLAs, and pause/resume controls.
- Needing backoff policies, rate limiting, or per-tenant/user schedules.

Do not move all logic to the application and drop constraints. Data invariants should still be protected in the database; application jobs orchestrate workflows and side effects.

### 9.1. Idempotency and At-Least-Once Processing

Workers can frequently receive the same job again on timeouts, process crashes, or lost acknowledgments. Therefore, design processing to be idempotent: rerunning the same job must not produce duplicate business effects.

Example outbox/job table:

```sql
CREATE TABLE outbox_event (
    event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    idempotency_key VARCHAR(120) NOT NULL,
    aggregate_type VARCHAR(40) NOT NULL,
    aggregate_id BIGINT UNSIGNED NOT NULL,
    event_type VARCHAR(80) NOT NULL,
    payload JSON NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    processed_at TIMESTAMP(6) NULL,
    PRIMARY KEY (event_id),
    UNIQUE KEY uq_outbox_idempotency (idempotency_key),
    KEY idx_outbox_pending (status, event_id),
    CONSTRAINT chk_outbox_status
        CHECK (status IN ('PENDING', 'PROCESSING', 'DONE', 'FAILED'))
) ENGINE = InnoDB;
```

Within the business transaction, the application updates data and INSERTs an outbox event. If the transaction rolls back, both business data and the outbox row roll back together. A worker reads the outbox after commit, dispatches the message/API call, and updates status. If dispatch succeeds yet the worker crashes before marking DONE, the message may be sent again; the consumer or target API needs the idempotency key.

### 9.2. Preventing Multiple Workers from Processing the Same Job

With multiple workers, use atomic claiming, leases, or locks. MySQL supports `SELECT ... FOR UPDATE SKIP LOCKED` in modern versions to pick unprocessed rows without waiting on workers holding locks on other rows:

```sql
START TRANSACTION;

SELECT event_id, idempotency_key, payload
FROM outbox_event
WHERE status = 'PENDING'
ORDER BY event_id
LIMIT 20
FOR UPDATE SKIP LOCKED;

-- The application marks claimed events in the same transaction.
UPDATE outbox_event
SET status = 'PROCESSING'
WHERE event_id IN (/* fetched IDs */);

COMMIT;
```

This is an illustrative skeleton; in real applications, build the ID list with prepared statements and perform controlled updates. Never keep a transaction open while making HTTP calls. Claim jobs in a short transaction, commit, execute external side effects, and record the outcome in another transaction. Use leases/timeouts to reclaim abandoned jobs.

## 10. Transactions and Atomicity by Mechanism

| Mechanism | Execution Boundary | Atomicity to Understand |
| --- | --- | --- |
| Constraint | Inside DML statement | If violated, statement is rejected; with InnoDB, statement changes roll back |
| Trigger | Inside firing statement | Trigger DML joins the statement's transaction; trigger errors fail the statement; with transactional tables, related changes roll back together |
| Event | One server event execution | Transactional DML follows session/event transactions; design explicit transactions if the event runs multiple steps |
| Application job | Managed by worker/application | DB transactions do not span HTTP or message brokers; use outbox/saga/idempotency for external side effects |

Do not assume INSERTing an audit row in a trigger guarantees an email was sent. A trigger can write an outbox row in the same transaction; a worker sends the email after commit.

## 11. Replication, Failover, and Where Events Run

Triggers and events are both database objects, yet their replication behavior must be accounted for in design:

- DML executed on source/primary is written to binary logs per configuration; replicas apply changes via replication.
- With row-based logging, replicas apply row changes from binary logs and do not re-run triggers for those row events as standalone DML statements.
- With statement-based logging, statements may execute on replicas and triggers may participate; ensure semantics and logging configuration are appropriate.
- Event definitions can replicate, but schedulers should not run concurrently across multiple nodes capable of acting as writers.
- During failover, runbooks must designate which new primary is allowed to enable the scheduler, and the old node must stop running events before taking writes or being isolated.
- Application workers also need leader/lease or queue coordination so two deployments do not simultaneously run an exclusive task.

Check `binlog_format`, topology, and real failover procedures. Never enable the Event Scheduler on every replica "just in case", as node role changes can cause duplicate executions.

## 12. Security and Least Privilege

| Mechanism | Privileges / Identities to Manage |
| --- | --- |
| Constraint | Schema DML/DDL privileges; applications cannot bypass constraints merely by using another regular write path |
| Trigger | Trigger definer and privileges needed by the trigger body; ensure definer stays valid and avoid over-broad grants |
| Event | `EVENT` privilege to create/manage and definer privileges to execute the body |
| Application job | Service accounts, secrets, least-privilege DB grants, API credentials, and queue access |

Triggers/events can execute with definer privileges. A routine or trigger defined by a privileged account can allow DML from a lower-privilege user to perform actions beyond that user's direct grants. Review `SHOW CREATE TRIGGER`, `SHOW CREATE EVENT`, `DEFINER`, and related grants during deployment.

Never embed passwords or API keys inside trigger or event definitions. Use your application's secret manager for external service credentials.

## 13. Performance and Observability

### 13.1. Constraints

Constraints usually carry small, predictable cost compared to their data integrity benefits. Unique/FK constraints require indexes and can introduce key/lock checks. Do not drop constraints for speed before measuring; optimize indexes, batch sizes, and transactions first.

### 13.2. Triggers

Trigger cost multiplies by DML row count. A 50,000-row UPDATE can generate 50,000 audit rows. Triggers running extra queries or updating hot tables can lengthen lock durations, increase deadlocks, and add replication lag. Measure statement latency, affected row counts, deadlocks, and transaction duration.

### 13.3. Events

Monitor `LAST_EXECUTED`, `STATUS`, runtime duration, and processed row counts. `INFORMATION_SCHEMA.EVENTS` is not a full job history store. Log each run when SLAs, retries, or alerts are required. Set batch limits and index filtering predicates.

### 13.4. Application Jobs

Monitor queue depth, oldest job age, success/failure rates, retry counts, processing duration, lease expirations, and dead-letter counts. Use correlation IDs to link jobs back to the transaction that created the outbox row and the original business request.

## 14. Anti-Patterns to Avoid

| Anti-Pattern | Why It Is Dangerous | Remediation |
| --- | --- | --- |
| Validating uniqueness via SELECT then INSERT | Two transactions can both pass the SELECT | Use a UNIQUE constraint and handle duplicate-key errors |
| Using triggers instead of CHECK for simple rules | Logic is hidden and harder to spot in schema | Use CHECK/NOT NULL/UNIQUE/FK |
| Trigger sending emails or making HTTP calls | External side effects do not roll back with DB transactions | Write to an outbox and let a worker send |
| Trigger updating the same table modified by DML | Risks mutating-table errors and logic loops | Design explicit DML or a suitable secondary table |
| Trigger running heavy per-row queries | Latency and lock time scale with row count | Reduce per-row work or move batching to jobs |
| Using Event Scheduler for complex retry workflows | Lacks dedicated queues, leases, DLQs, and observability | Use an application job platform |
| Enabling scheduler on every node | Can run the same job multiple times after failover | Designate the writer and a role-transition runbook |
| Data-deletion jobs without batches or indexes | Long locks, huge undo logs, workload impact | Small batches, indexes, backlog monitoring |
| Assuming events run strictly once | Restarts/failovers/deployments can cause reruns or skips | Design idempotently and track run state |
| Enforcing business rules in only one service | Scripts/batches/other services can write bad data | Move invariants to constraints or proper DB transactions |
| Treating session variables as trusted actors | Clients can set arbitrary values if uncontrolled | Pass identity/context through authenticated channels and audit sources |

## 15. Scenario-Based Selection Matrix

| Requirement | Preferred Choice | Reason |
| --- | --- | --- |
| Email must be unique | `UNIQUE` + `NOT NULL` | Protects every write path and resolves race conditions in the database |
| Quantity must be non-negative | `CHECK` + `NOT NULL` | Single-row invariant |
| Child row must have a parent row | `FOREIGN KEY` | Engine-enforced referential integrity |
| Value computed from columns in the same row | Generated column | Avoids trigger synchronization |
| Record row-change audit in the same transaction | Trigger or explicit audit DML | Triggers cover all writers; explicit DML is clearer when one service owns writes |
| Send email after order creation | Outbox + application worker | External side effect needing retries/idempotency |
| Periodically purge expired sessions | Event Scheduler or application scheduler | Choose based on observability needs and topology |
| Aggregate large nightly reports | Application job or event calling procedure | Needs batching, runtime tracking, and replayability |
| Check shared budget across multiple rows | Transaction/locking or ledger model | Needs concurrency control, not just triggers |
| Call multiple services and wait for responses | Application workflow | Needs timeouts, retries, compensation, and observability |

## 16. Deployment Runbook

### Before Deployment

1. Write the rule in business language and identify which data must be protected.
2. Identify every writer: APIs, batch jobs, ETL, admin scripts, and integration services.
3. Choose the mechanism and document transaction boundaries explicitly.
4. Analyze race conditions, deadlocks, and retry behavior.
5. Verify MySQL version, storage engine, binary logging, and topology.
6. Review privileges, definers, schema migrations, and rollback capability.
7. Write tests for valid data, violating data, and concurrent writes.

### During Deployment

1. Deploy schemas/constraints before enabling application flows that depend on them.
2. Create triggers/events via reviewable, tracked migrations.
3. Verify `SHOW CREATE TABLE`, `SHOW CREATE TRIGGER`, or `SHOW CREATE EVENT`.
4. Confirm Event Scheduler and event status on the designated node.
5. Run smoke tests inside a controlled transaction.
6. Monitor constraint errors, trigger latency, deadlocks, event execution, and replication lag.

### During Rollback or Failover

- Disable events before switching roles if the old node remains active.
- Do not DROP triggers before assessing impact on integrity and auditing.
- Keep schema constraints compatible with all concurrently running application versions.
- If a worker job already emitted external side effects, database rollback cannot undo them; use compensation or idempotency.
- Verify definers and privileges on the new node.

## 17. Practice Exercises

1. Create a table with NOT NULL, PRIMARY KEY, UNIQUE, FOREIGN KEY, and CHECK. Attempt INSERT/UPDATE statements violating each constraint and record the errors.
2. Create a nullable unique key; insert multiple rows with NULL and explain why it succeeds. Then alter the column to NOT NULL.
3. Create a generated column computing line total and compare it with storing a regular column updated by triggers.
4. Create a BEFORE UPDATE trigger validating status transitions. Test both valid and invalid transitions.
5. Create an AFTER UPDATE audit trigger. Verify the audit row rolls back together with the source transaction.
6. Intentionally make the audit INSERT fail via a constraint on the audit table; observe whether the source UPDATE fails as well.
7. Run a multi-row UPDATE and measure audit row count and latency added by the trigger.
8. Create an Event Scheduler job deleting at most 1,000 expired rows per run. Inspect `event_scheduler`, `SHOW EVENTS`, and `LAST_EXECUTED`.
9. Disable the event, confirm it stops running; re-enable it and observe the next cycle.
10. Write an outbox row in the same transaction that creates an order. Roll back the transaction and confirm no outbox row remains.
11. Simulate a worker submitting the same idempotency key twice; ensure the consumer does not produce duplicate side effects.
12. Simulate two workers claiming jobs using short transactions and `SKIP LOCKED`; do not hold transactions open while calling external services.
13. Write an architecture decision record for a requirement—constraint, trigger, event, or application job—covering rationale, transactions, retries, security, and monitoring.

## 18. Completion Checklist

- [ ] Data invariants are expressed as constraints whenever possible.
- [ ] Considered generated columns/defaults before creating triggers.
- [ ] Triggers perform only short, synchronous, database-scoped work.
- [ ] Triggers do not send emails/HTTP requests or manage transactions themselves.
- [ ] Understood row-by-row trigger execution and impact on bulk DML.
- [ ] Checked TRUNCATE, FK cascade, and mutating-table limitations.
- [ ] Events have clear schedules, time zones, definers, privileges, and batch limits.
- [ ] Event Scheduler runs only on designated nodes in the topology.
- [ ] Application jobs have proper idempotency, retries, leases, and dead-letter handling.
- [ ] External side effects are orchestrated via outbox/workflows.
- [ ] Transaction boundaries and concurrency handling are defined.
- [ ] Logs, metrics, alerts, and runbooks exist for errors/failovers.
- [ ] Tests cover direct writes, bulk writes, rollbacks, and retries.

## 19. Completion Criteria

You have completed this lesson when you can classify a requirement as a data invariant, synchronous reaction, periodic task, or application workflow; select the right mechanism among constraints, triggers, events, and application jobs; explain transactions and concurrency; and design corresponding privileges, idempotency, replication/failover handling, and monitoring. You should also be able to articulate why a trigger or event cannot replace a job queue when a workflow requires calling external services and controlled retries.

## References

- [MySQL 8.4 Reference Manual — Constraint](https://dev.mysql.com/doc/refman/8.4/en/constraints.html)
- [MySQL 8.4 Reference Manual — CHECK Constraints](https://dev.mysql.com/doc/refman/8.4/en/create-table-check-constraints.html)
- [MySQL 8.4 Reference Manual — Trigger Syntax and Examples](https://dev.mysql.com/doc/refman/8.4/en/trigger-syntax.html)
- [MySQL 8.4 Reference Manual — Using Triggers](https://dev.mysql.com/doc/refman/8.4/en/triggers.html)
- [MySQL 8.4 Reference Manual — Event Scheduler](https://dev.mysql.com/doc/refman/8.4/en/events.html)
- [MySQL 8.4 Reference Manual — CREATE EVENT Statement](https://dev.mysql.com/doc/refman/8.4/en/create-event.html)
- [MySQL 8.4 Reference Manual — Replication and Triggers](https://dev.mysql.com/doc/refman/8.4/en/replication-features-triggers.html)
