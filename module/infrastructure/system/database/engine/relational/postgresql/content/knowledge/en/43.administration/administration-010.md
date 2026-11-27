# Script Automation with Error Handling, Timeouts, and Logging in PostgreSQL

## 1. Why Do Administrative Scripts Need Guardrails?

Recurring PostgreSQL tasks are commonly automated with SQL scripts, `psql`, shell scripts, Python, schedulers, or CI/CD pipelines. Examples include running migrations, granting privileges, checking replication, refreshing data, analyzing tables, generating reports, batch purging data, and running maintenance.

Automation brings consistency and reduces manual work. However, a script can cause major outages if it targets the wrong database, runs twice concurrently, waits indefinitely on a lock, keeps executing after a failed SQL statement, logs passwords, or reports success despite a rolled-back transaction.

A reliable operational script must clearly define:

- **Scope:** which cluster, database, schema, objects, and identities may be touched?
- **Preconditions:** do server version, role, topology, backups, disk headroom, and application state satisfy requirements?
- **Safety:** is the operation idempotent, transactional, dry-runnable, or reversible?
- **Errors:** how are SQL errors, lost connections, permission denied, deadlocks, and OS errors classified?
- **Timeouts:** do connection, lock wait, SQL statements, and the overall job each have independent limits?
- **Concurrency:** how do we prevent two scheduler runs from executing the same task simultaneously?
- **Observability:** who ran it, where did it run, how long did it take, how many rows were affected, and what was the outcome?
- **Completion:** does the exit code accurately reflect the outcome so schedulers and CI detect failures?

The goal of this lesson is building automation that is controllable, observable, and recoverable. A script finishing without evidence of its actual outcome cannot be considered a successful run.

```text
              SCHEDULE / OPERATOR
                      |
                      v
             Validate target and inputs
                      |
                      v
              Acquire job ownership
                      |
                      v
             Connect with bounded wait
                      |
                      v
              Run guarded SQL steps
                /             \
               v               v
             Success          Error
               |               |
               v               v
            Commit         Rollback/stop
               |               |
               +-------+-------+
                       |
                       v
             Write result and metrics
                       |
                       v
               Exit with status code
```

## 2. Learning Objectives

After this lesson, you can:

1. Design PostgreSQL scripts with preconditions, scope, and exit criteria.
2. Run `psql` in non-interactive, fail-fast mode.
3. Distinguish `psql` exit codes.
4. Manage transactions and understand the limits of transactional DDL.
5. Configure connection timeouts, lock timeouts, and statement timeouts.
6. Bound total runtime for the entire job.
7. Distinguish client timeouts from server-side cancellation.
8. Handle SQL errors, connection drops, deadlocks, and serialization failures.
9. Design bounded retries with backoff and idempotency.
10. Prevent concurrent execution using advisory locks or scheduler locks.
11. Write logs with timestamps, run IDs, targets, and outcomes.
12. Protect passwords, connection strings, and sensitive data in logs.
13. Use shell error handling and traps properly.
14. Validate affected row counts and postconditions after each critical step.
15. Design dry runs, batch processing, and checkpoints.
16. Separate transactional operations from operations prohibited inside transactions.
17. Monitor scripts via `application_name` and PostgreSQL statistics.
18. Schedule jobs with `cron`, `systemd`, or CI/CD.
19. Build runbooks for timeouts, failures, retries, and recovery.
20. Preserve evidence for audits and ongoing automation improvements.

## 3. Classifying Errors Before Writing Scripts

Not all errors deserve the same response. Classify errors to decide whether to stop, retry, roll back, or escalate to an operator.

| Error Category | Examples | Typically Appropriate Action |
| --- | --- | --- |
| Input/configuration | Missing database name, wrong environment | Halt before connecting |
| Authentication | Expired password, wrong auth rule | Halt, fix credentials/config |
| Connection | Server unreachable, DNS failure | Bounded retry if appropriate |
| Permission | SQLSTATE 42501 | Halt, review privileges |
| Syntax/object | SQLSTATE 42601, 42P01 | Halt, fix script/schema |
| Constraint/data | Unique/FK/check violation | Halt or handle per business rules |
| Lock contention | SQLSTATE 55P03 or lock timeout | Retry entire transaction if idempotent |
| Deadlock | SQLSTATE 40P01 | Bounded retry of entire transaction |
| Serialization | SQLSTATE 40001 | Retry entire transaction |
| Statement timeout | SQLSTATE 57014 | Halt or investigate; never retry blindly |
| Connection loss | SQLSTATE class 08 or client disconnect | Reconcile transaction outcome before retrying |
| Resource exhaustion | Disk full, OOM, too many connections | Halt and resolve capacity |
| External process | Scheduler, filesystem, or network error | Halt and record exit code |

### 3.1. Fail Fast

Configuration errors, missing privileges, wrong objects, and invalid data do not resolve themselves on retry. Retrying repeatedly only adds load and log noise.

### 3.2. Conditional Retries

Deadlocks and serialization failures can arise from normal concurrency. PostgreSQL requires clients to retry the entire transaction in these cases. Never re-run only the final statement after an earlier transaction rolled back.

### 3.3. Ambiguous Commit Outcomes

If a connection drops right when the client sends `COMMIT` or awaits its response, the client cannot tell whether the transaction committed. Never assume a dropped connection means a rollback. Use an idempotency key, operation ledger, or reconciliation query before retrying.

### 3.4. Never Swallow Errors

A script must never print "success" after ignoring a SQL error. Every error affecting the outcome must produce a non-zero exit status or be explicitly recorded as an intentional outcome.

## 4. Running psql in Automation Mode

### 4.1. Key Options

Example executing a SQL file:

```bash
psql -X -w -v ON_ERROR_STOP=1 -d appdb -f maintenance.sql
```

Meaning:

- **-X:** ignore user `psql` startup files (`psqlrc`), reducing environment dependence.
- **-w:** never prompt interactively for a password; fail if credentials are missing.
- **-v ON_ERROR_STOP=1:** stop the script on any SQL error.
- **-d:** select the database.
- **-f:** execute the SQL file.

Inside the SQL file itself, you can also set:

```sql
\set ON_ERROR_STOP on
\set VERBOSITY verbose
\timing on
```

### 4.2. Why Is ON_ERROR_STOP Necessary?

By default, `psql` continues executing remaining commands after a script error. In automation, this creates partial broken states: table creation fails yet subsequent grants or version inserts still execute.

`ON_ERROR_STOP` tells `psql` to stop whenever a SQL command or meta-command fails. If the script has an open transaction, closing the session upon error rolls back uncommitted changes.

### 4.3. psql Exit Codes

In non-interactive mode, common exit codes are:

| Exit code | Meaning |
| ---: | --- |
| 0 | Completed normally |
| 1 | Fatal error in `psql` itself |
| 2 | Server connection failed in non-interactive mode |
| 3 | Script error occurred while `ON_ERROR_STOP` was enabled |

Schedulers must check exit codes rather than grepping stdout for the word "ERROR". Some wrappers alter exit codes; verify the entire invocation chain.

### 4.4. Avoid Arbitrary Shell Interpolation

Store SQL in reviewed files or quoted heredocs. For instance, `<<'SQL'` stops the shell from expanding `$VARIABLE` inside the SQL body.

Never concatenate user input directly into SQL strings. With `psql` variables, use proper quoting:

- **:'var'** to quote a value as a SQL literal.
- **:"var"** to quote an identifier.
- **:var** performs raw text substitution and is unsafe for arbitrary data.

### 4.5. Single Transaction Option

`psql` offers **--single-transaction** (or **-1**) to wrap compatible `-c`/`-f` commands in one transaction. Use it only when every command can execute inside a transaction. Commands like `CREATE DATABASE`, `DROP DATABASE`, `VACUUM`, and `CREATE INDEX CONCURRENTLY` cannot run inside a transaction block.

### 4.6. Split Files by Phase

For complex deployments, separate:

- Preflight.
- Transactional schema/data changes.
- Non-transactional operations.
- Postflight validation.

Each phase gets its own exit code, log, and recovery step. Never dump every command into a single file assuming everything can roll back together.

## 5. Transactions and Atomicity

### 5.1. Group Related Changes into Transactions

```sql
BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '2min';

ALTER TABLE app.orders
    ADD COLUMN source_code text;

UPDATE app.orders
SET source_code = 'legacy'
WHERE source_code IS NULL;

COMMIT;
```

If any statement fails before `COMMIT`, the transaction enters the aborted state and uncommitted transactional changes are discarded.

### 5.2. SET LOCAL

`SET LOCAL` applies only within the current transaction. Once the transaction commits or rolls back, the setting reverts to its prior value. This is ideal for scoping timeouts to a specific migration.

### 5.3. Transactions Do Not Make Everything Rollbackable

Some commands cannot execute inside a transaction block; external actions like sending files, calling APIs, or restarting services cannot be rolled back by PostgreSQL. Design workflows with reconcilable and compensating steps.

### 5.4. Never Hold Transactions Open While Waiting Externally

Avoid opening a transaction and then making HTTP calls, waiting for user input, or processing slow files. Long transactions hold locks and snapshots, increase bloat pressure, and block vacuum.

### 5.5. Checking Affected Row Counts

In `psql`, the `ROW_COUNT` variable can be inspected right after a SQL command:

```sql
UPDATE app.orders
SET status = 'archived'
WHERE created_at < current_date - interval '2 years';

\echo Updated rows: :ROW_COUNT
```

In production scripts, compare affected rows against expected bounds. If the count exceeds limits or is unexpectedly zero, abort the transaction or require review.

### 5.6. Use Constraints and Preconditions

Do not verify only afterward. Use preconditions—such as schema version, object existence, expected owner, and row counts—to prevent scripts from running against the wrong state.

## 6. Timeouts to Distinguish

Automation generally needs multiple independent timeouts. No single timeout protects every layer.

| Timeout | What It Limits | Configuration |
| --- | --- | --- |
| Connection timeout | Time to establish connection | `PGCONNECT_TIMEOUT` or libpq `connect_timeout` |
| Lock timeout | Time waiting on a lock | `lock_timeout` |
| Statement timeout | Runtime of one statement | `statement_timeout` |
| Idle transaction timeout | Idle duration inside a transaction | `idle_in_transaction_session_timeout` |
| Idle session timeout | Idle session duration | `idle_session_timeout` |
| Job timeout | Total process/job runtime | Scheduler or OS timeout |
| Retry budget | Total retry time / attempt count | Wrapper logic |

### 6.1. Connection Timeout

Bound connection establishment time:

```bash
export PGCONNECT_TIMEOUT=5
psql -X -w -d appdb -c 'SELECT 1;'
```

Value is in seconds. When multiple hosts appear in a connection string, total wall time can exceed a single timeout as `libpq` tries each address.

### 6.2. Lock Timeout

`lock_timeout` limits how long a statement waits for a lock. Example:

```sql
SET lock_timeout = '5s';
```

If a migration needs a lock and cannot acquire it within 5 seconds, PostgreSQL aborts the statement with a lock-not-available error. This keeps DDL from waiting indefinitely and queuing traffic behind it.

### 6.3. Statement Timeout

```sql
SET statement_timeout = '2min';
```

If a statement runs longer than the threshold, PostgreSQL cancels it. This measures server-side statement execution time; it does not limit the entire job.

Do not set `statement_timeout` overly low for valid backups, index builds, or batch jobs. Use `SET LOCAL` per step when steps need different budgets.

### 6.4. Idle-in-Transaction Timeout

```sql
SET idle_in_transaction_session_timeout = '1min';
```

This closes sessions that sit idle inside a transaction for too long. It curtails abandoned transactions, though it can disconnect applications that hold transactions open across external operations.

### 6.5. Idle Session Timeout

`idle_session_timeout` closes idle sessions outside transactions. Be cautious with connection pools, proxies, and middleware that do not expect the server to close idle connections proactively.

### 6.6. Job Timeout

A process wrapper can bound total job runtime:

```bash
timeout --signal=TERM --kill-after=30s 15m \
  psql -X -w -v ON_ERROR_STOP=1 -d appdb -f maintenance.sql
```

This example uses GNU coreutils on Linux. Syntax and behavior differ on Windows or other schedulers. Job timeout is an outer safeguard; `statement_timeout` is still needed so the server cancels SQL proactively.

### 6.7. Timeouts Do Not Roll Back Everything

Killing a client process does not guarantee non-transactional actions revert. Closing the connection usually rolls back open transactions, yet already-committed work, external side effects, and non-transactional commands persist. After any timeout, verify state before re-running.

## 7. Designing Timeouts per Step

### 7.1. Short Preflight

Connection establishment and status checks should use short connect timeouts. Preflight queries should be lightweight and never scan huge tables.

### 7.2. Keep Lock Waits Shorter Than Statement Budgets

For example, `lock_timeout = 5s` and `statement_timeout = 2min`. If locks are unavailable promptly, the script exits before piling up user wait queues.

### 7.3. Leave Room for Rollback and Cleanup

The job budget should leave margin for logging, rollbacks, closing sessions, and reporting outcomes. Never set the job timeout equal to the longest statement timeout if more steps follow.

### 7.4. Match Timeouts to Workloads

A large analytical report may need several minutes; adding a constraint on a huge table needs its own plan; health checks should finish in seconds. Document the rationale for every timeout.

### 7.5. Avoid Confusing Overlapping Timeouts

If `statement_timeout` is 2 minutes while the job timeout is 30 seconds, the wrapper kills the client before PostgreSQL returns the statement timeout error. Order statement timeouts, retry budgets, and job budgets coherently.

## 8. Idempotency and Safe Re-Execution

### 8.1. What Is Idempotency?

An idempotent operation can run multiple times and leave the system in an equivalent final state as running once, under defined conditions.

Example:

```sql
CREATE TABLE IF NOT EXISTS app.job_runs (
    job_name text PRIMARY KEY,
    last_success_at timestamptz
);
```

However, `IF NOT EXISTS` only avoids errors when an object name already exists; it does not prove the existing object has the expected schema, owner, or constraints. Catalog verification is still needed.

### 8.2. UPSERT with Business Keys

```sql
INSERT INTO app.job_runs (job_name, last_success_at)
VALUES ('daily_aggregate', clock_timestamp())
ON CONFLICT (job_name)
DO UPDATE
SET last_success_at = EXCLUDED.last_success_at;
```

Use a unique key representing the operation or business identity to prevent duplicates on retry.

### 8.3. Migration Ledgers

Store migration version, checksum, and applied timestamp. Before running a migration, check:

- Does the version already exist?
- Does the checksum match the reviewed file?
- Is an earlier migration stuck in an incomplete state?
- Has a newer version already been applied?

Never mark a migration complete before the schema-change transaction commits.

### 8.4. Do Not Confuse IF EXISTS with Safety

`DROP TABLE IF EXISTS` can succeed even if the object was accidentally dropped earlier. Idempotency requires verifying target, owner, schema, and expected state; `IF EXISTS` merely suppresses one name-missing error.

### 8.5. Conditional DML

Use unique constraints, upserts, operation IDs, and predicates so retries never create duplicates. Avoid "select to check existence, then insert" patterns without concurrency-safe constraints.

### 8.6. External Side Effects

If a script updates PostgreSQL and also sends emails, calls APIs, or writes files, a database transaction cannot roll back external actions. Use the outbox pattern, receiver-side idempotency keys, or reconciliation steps.

## 9. Bounded Retries and Backoff

### 9.1. Retries Do Not Fix Logic Errors

Never retry syntax errors, permission denied, missing relations, or invalid inputs. Those require fixing the script or configuration.

### 9.2. SQLSTATEs to Recognize

Notable codes:

| SQLSTATE | Meaning | Action |
| --- | --- | --- |
| 40001 | Serialization failure | Retry entire transaction if idempotent |
| 40P01 | Deadlock detected | Bounded retry of entire transaction |
| 55P03 | Lock not available | May retry after backoff if policy allows |
| 57014 | Query canceled | Determine cause; never retry unconditionally |
| 42501 | Insufficient privilege | Halt and fix privileges |
| 42601 | Syntax error | Halt and fix script |
| 23505 | Unique violation | Handle per business logic |
| 08xxx | Connection exception class | Check transaction outcome before retrying |

### 9.3. Exponential Backoff

Example increasing delays: 1s, 2s, 4s, 8s, with jitter and attempt limits. Jitter prevents multiple jobs from retrying at the exact same instant.

### 9.4. Retry the Entire Transaction

Upon serialization failure or deadlock, the current transaction is invalid. Restart the entire transaction from the beginning, including all reads that write decisions depend on.

### 9.5. Set a Retry Budget

For example, at most 4 attempts or 2 minutes total elapsed time. Once the budget is exhausted, log the final error and return a non-zero exit code.

### 9.6. Never Retry Blindly After Connection Loss on COMMIT

If the client disconnects during `COMMIT`, the transaction may have committed. Query status from a new connection using an operation ID to verify. If indeterminate, report `UNKNOWN` for operator handling.

## 10. Preventing Concurrent Runs

### 10.1. Why Is Concurrency Control Needed?

`cron`, `systemd` timers, or CI pipelines can launch a new run while the prior one is still active. Two scripts archiving data, rotating partitions, or altering schemas concurrently can collide.

### 10.2. Advisory Transaction Locks

For a single transaction:

```sql
BEGIN;

DO $$
BEGIN
    IF NOT pg_try_advisory_xact_lock(4200, 554) THEN
        RAISE EXCEPTION 'maintenance job is already running';
    END IF;
END
$$;

-- Perform operations belonging to the same transaction.
ANALYZE app.orders;

COMMIT;
```

Two integer keys namespace the job. If the lock is already held, the script errors and the transaction rolls back. Transaction-level advisory locks release automatically on commit or rollback.

### 10.3. Advisory Session Locks

For jobs spanning multiple transactions, use `pg_try_advisory_lock` and `pg_advisory_unlock` to hold a session-level lock. If the connection closes, the session lock releases.

Ensure every exit branch unlocks or closes the session; never reuse the same key for unrelated jobs.

### 10.4. Advisory Locks Are Cooperative

PostgreSQL does not force arbitrary DDL/DML to honor advisory locks. Only scripts following the same key convention serialize. Advisory locks do not replace row/table locks and are not an authorization mechanism.

### 10.5. OS-Level Locks

On Linux, `flock` prevents two processes on the same host from running concurrently. It does not coordinate jobs across different hosts or containers unless the lock file resides on a filesystem with appropriate locking semantics.

### 10.6. Use Two Layers When Needed

A scheduler lock stops duplicates on the same host; a PostgreSQL advisory lock protects across hosts sharing a database. Pick one primary mechanism and document its scope clearly.

## 11. Logging: What Should Be Recorded?

### 11.1. Logs Must Answer Who, What, and When

Every run should log:

- UTC timestamp.
- Run ID and change/job ID.
- Environment, host/cluster, and database.
- Script name and version/checksum.
- Application name or service identity.
- Attempt number.
- Event markers: start, step, success, failure.
- Duration and rows affected.
- SQLSTATE and exit code on failure.
- Postcondition outcomes.
- User or scheduler that triggered the run.

### 11.2. Structured Logs

Key-value or JSON formatting aids searching:

```text
timestamp=2026-11-14T08:00:00Z level=INFO run_id=run-104 job=analyze_orders database=appdb event=start
timestamp=2026-11-14T08:00:03Z level=INFO run_id=run-104 job=analyze_orders rows=0 event=complete
timestamp=2026-11-14T08:00:03Z level=INFO run_id=run-104 job=analyze_orders exit_code=0 result=success
```

You do not need to log every SQL value; log enough metadata to trace the run.

### 11.3. Never Log Secrets

Avoid logging:
- Passwords or connection strings containing passwords.
- Access tokens or private keys.
- PII or sensitive query parameters.
- Credential file contents.
- Full environment dumps.

Never enable shell `xtrace` in scripts handling secrets or connection data.

### 11.4. Log SQLSTATE Instead of Messages Alone

SQLSTATEs classify errors much more reliably than prose messages. Log redacted messages when helpful, ensuring no sensitive data slips into logs.

### 11.5. Client-Side and Server-Side Logs

Client logs show job, attempt, duration, and exit code. PostgreSQL server logs show backend PID, query duration, lock waits, error context, and session identity. Correlate both using timestamps, database, user, and `application_name`.

### 11.6. Permissions and Retention

Log files can contain schema names and query samples. Enforce strict file permissions, rotation, retention, and access controls. Never retain logs indefinitely on a filling volume.

## 12. Shell Wrapper with Error Handling

The Bash example below illustrates a Linux wrapper. Replace service, database, and change ID for your lab environment and configure `.pg_service.conf`/credential stores before running.

```bash
#!/usr/bin/env bash
set -Ee -o pipefail
umask 077

CHANGE_ID="CHG-2026-0001"
PGSERVICE="app_admin"
PGDATABASE="appdb"
LOG_DIR="./logs"

if [ -z "$PGSERVICE" ] || [ -z "$PGDATABASE" ] || [ -z "$CHANGE_ID" ]; then
    printf '%s\n' "Missing required configuration" >&2
    exit 64
fi

mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/pg-admin-$(date -u +%Y%m%dT%H%M%SZ).log"
printf 'Log file: %s\n' "$LOG_FILE" >&2
exec >>"$LOG_FILE" 2>&1

log() {
    printf '%s level=%s change_id=%s %s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$CHANGE_ID" "$2"
}

on_error() {
    rc=$?
    log ERROR "line=$1 exit_code=$rc"
    exit "$rc"
}

on_exit() {
    rc=$?
    if [ "$rc" -eq 0 ]; then
        log INFO "result=success exit_code=0"
    else
        log ERROR "result=failure exit_code=$rc"
    fi
}

trap 'on_error "$LINENO"' ERR
trap on_exit EXIT

export PGCONNECT_TIMEOUT=5
export PGAPPNAME="pg-admin-$CHANGE_ID"

log INFO "event=start database=$PGDATABASE service=$PGSERVICE"

psql -X -w -v ON_ERROR_STOP=1 \
    -d "service=$PGSERVICE dbname=$PGDATABASE" <<'SQL'
\set ON_ERROR_STOP on
\set VERBOSITY verbose
\timing on

SET lock_timeout = '5s';
SET statement_timeout = '2min';
SET idle_in_transaction_session_timeout = '1min';

BEGIN;

DO $$
BEGIN
    IF NOT pg_try_advisory_xact_lock(4200, 554) THEN
        RAISE EXCEPTION 'maintenance job is already running';
    END IF;
END
$$;

ANALYZE app.orders;

COMMIT;
SQL

log INFO "event=psql_completed"
```

### 12.1. Why Use set -Ee -o pipefail?

- **-e:** exit when a command fails in shell contexts where `errexit` applies.
- **-E:** inherit the `ERR` trap inside functions and subshells where Bash supports it.
- **pipefail:** fail a pipeline if any component fails, not only the final command.

`set -e` has exceptions inside `if`, `while`, `&&`, `||`, pipelines, and functions. Never treat it as a substitute for explicit exit-code checks.

### 12.2. Error Trap and Exit Trap

The `ERR` trap records the line number and exit code on command failures. The `EXIT` trap records the final result. Never log raw commands or full environments that might contain secrets.

### 12.3. Log File Permissions

`umask 077` restricts permissions on newly created files to the user running the script. Existing log directories still need explicit permission and ownership management.

### 12.4. Service Files and Passwords

The example uses a `libpq` service name. Define the service in `.pg_service.conf` or a managed location; pull passwords from a secret manager, `.pgpass` with strict permissions, or an organization-approved auth mechanism. `-w` guarantees `psql` never hangs waiting for an interactive password prompt.

### 12.5. Never Enable xtrace

Do not add `set -x` to wrappers if commands can reference connection details or credentials. When debugging, log only allowlisted and redacted values.

### 12.6. Wrappers Must Account for Log Rotation

The example writes timestamped files. For frequently running jobs, use `logrotate` or centralized logging and monitor disk capacity and retention.

## 13. SQL Scripts with Guardrails

A SQL script should state preconditions and scope explicitly.

```sql
\set ON_ERROR_STOP on
\set VERBOSITY verbose
\timing on

-- Apply timeouts to this session only.
SET lock_timeout = '5s';
SET statement_timeout = '2min';

BEGIN;

-- Prevent concurrent runs of the same job.
DO $$
BEGIN
    IF NOT pg_try_advisory_xact_lock(4200, 554) THEN
        RAISE EXCEPTION 'another run owns this job';
    END IF;
END
$$;

-- Verify target before making changes.
DO $$
BEGIN
    IF current_database() <> 'appdb' THEN
        RAISE EXCEPTION 'unexpected database target';
    END IF;
END
$$;

ANALYZE app.orders;

COMMIT;
```

### 13.1. Checking the Database Target

Scripts should verify `current_database()` themselves and may verify server identity, schema version, or environment. Never blindly trust that the scheduler passed the right parameter.

### 13.2. Checking the Role

Use `current_user` and `session_user` to verify identity. If the script requires an owner role, execute `SET ROLE` explicitly and verify before running DDL.

### 13.3. Checking the Object Owner

Inspect `pg_class.relowner`, `pg_namespace.nspowner`, or `pg_get_userbyid()` to confirm the target has the expected owner.

### 13.4. Checking Affected Rows

For critical DML, log row counts and abort if counts fall outside expected bounds. When using `psql`'s `ROW_COUNT`, read it immediately after the target statement.

### 13.5. Assertions Must Actually Halt Execution

A precondition check must stop the script when unsatisfied. `RAISE EXCEPTION` inside a `DO` block raises a SQL error; with `ON_ERROR_STOP`, `psql` exits with an error code.

## 14. Running Large Batches with Checkpoints

### 14.1. Why Not Update Millions of Rows in One Transaction?

A huge single transaction can:
- Hold locks for a long time.
- Spike WAL generation and replication lag.
- Pin old snapshots, blocking vacuum.
- Incur massive rollback work on failure.
- Prolong crash recovery.

### 14.2. Bounded Batching

Use stable keys and predicates to process chunks. Illustrative primary-key batch example:

```sql
WITH batch AS (
    SELECT order_id
    FROM app.orders
    WHERE archived_at IS NULL
      AND created_at < current_date - interval '2 years'
    ORDER BY order_id
    LIMIT 1000
    FOR UPDATE SKIP LOCKED
)
UPDATE app.orders AS o
SET archived_at = clock_timestamp()
FROM batch
WHERE o.order_id = batch.order_id;
```

The application loops until no matching rows remain. `SKIP LOCKED` helps worker queues and batch concurrency, though it skips currently locked rows; a follow-up pass is needed to guarantee completeness.

### 14.3. Recording Checkpoints

Store job ID, last processed key, batch number, rows affected, and timestamp in a control table. Checkpoints must commit alongside the batch or follow explicit recovery semantics.

### 14.4. Ensure Retries Never Skip or Duplicate Work

Selection predicates must exclude already-processed rows. Use unique keys, status transitions, and transactions to update data and checkpoints atomically.

### 14.5. Bounding WAL and Replication Impact

Monitor WAL bytes, replica replay lag, disk headroom, and archive throughput. Shrink batch sizes or sleep between batches if production traffic must take priority.

### 14.6. Resumable Batch Jobs

When a job times out, read the checkpoint and verify row state. Never reset checkpoints or restart from scratch simply because a process returned an error.

## 15. Dry Runs and Pre-Change Reviews

### 15.1. What Does Dry-Run Mean?

A dry run previews targets, expected row counts, affected objects, and execution plans without committing changes. Not every SQL operation can be fully simulated.

### 15.2. Transaction Rollbacks in Labs

For transactional changes, you can test inside a transaction and `ROLLBACK` in lab/staging to validate SQL and estimate affected rows. Note this does not fully simulate lock durations, commit behavior, or external side effects.

### 15.3. SELECT Previews Before UPDATE/DELETE

```sql
SELECT count(*) AS candidate_rows
FROM app.orders
WHERE created_at < current_date - interval '2 years'
  AND archived_at IS NULL;
```

Then inspect sample rows and expected ranges before running DML.

### 15.4. Caps and Guardrails on Destructive Operations

For example, require affected rows to stay below an approved ceiling. If exceeded, raise an exception and stop for operator review.

### 15.5. Target Review

Log database, host/service name, schema, and change ID before starting. Require target allowlists for production automation.

### 15.6. Dry Runs Do Not Replace Backups

Before destructive changes, verify backups/PITR and recovery procedures. A transaction rollback never protects against non-transactional operations or committed logic bugs.

## 16. Operations Prohibited Inside Transaction Blocks

Certain administrative tasks require dedicated workflows:

| Command / Operation | Transaction Block |
| --- | --- |
| `CREATE DATABASE` | No |
| `DROP DATABASE` | No |
| `VACUUM` | No |
| `CREATE INDEX CONCURRENTLY` | No |
| `REINDEX CONCURRENTLY` | No |
| Other specific admin commands | Check version docs |

### 16.1. Isolate Non-Transactional Steps

Run preflight and backup checks first; execute the standalone command; then run postflight state checks. If it fails mid-way, follow that command's specific recovery procedure.

### 16.2. CREATE INDEX CONCURRENTLY

Avoids long write locks of standard `CREATE INDEX`, yet runs in multiple phases and can leave behind an invalid index on failure. Check `pg_index.indisvalid` and clean up index state before retrying.

### 16.3. VACUUM

`VACUUM` must run outside a transaction block. Never wrap it inside `BEGIN`/`COMMIT` or pass `--single-transaction` for files containing `VACUUM`.

### 16.4. CREATE/DROP DATABASE

These alter cluster-level state. Run in a separate autocommit session after verifying database names, active connections, and dependencies. Never combine them with regular migration transactions.

### 16.5. External Operations

Restarting PostgreSQL, swapping config files, altering firewalls, or updating DNS lie outside database transactions. Workflows need explicit step states and compensating actions.

## 17. Server-Side PostgreSQL Logging

### 17.1. application_name

Set `application_name` to the job/change ID to identify sessions:

```sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    client_addr,
    state,
    query_start,
    wait_event_type,
    wait_event
FROM pg_catalog.pg_stat_activity
WHERE application_name LIKE 'pg-admin-%';
```

Set via `libpq` `PGAPPNAME` or the `application_name` connection parameter.

### 17.2. log_line_prefix

A log prefix can include timestamp, PID, user, database, application name, and client address. Exact syntax depends on PostgreSQL version:

```conf
log_line_prefix = '%m [%p] user=%u db=%d app=%a client=%h '
```

Keep formats consistent so client and server logs correlate cleanly.

### 17.3. Slow Statement Logging

`log_min_duration_statement` logs statements exceeding a duration threshold. Balance diagnostic visibility against log volume. Parameter values may contain sensitive data depending on queries and logging settings.

### 17.4. Connection Logs

`log_connections` and `log_disconnections` help trace session lifecycles. On systems with heavy connection churn, log volume can grow considerably.

### 17.5. pgaudit and Audit Trails

`pgaudit` logs auditable activities per policy. Audit configuration must weigh volume, retention, overhead, and log access controls. Never log every statement without a storage plan.

### 17.6. Server Logs Do Not Replace Application Logs

PostgreSQL logs show what the server observed; scheduler/application logs show how the job was launched and what responses it received. Both sides are needed to diagnose failures.

## 18. Monitoring Jobs While Running

### 18.1. Active Sessions

Locate jobs by `application_name`:

```sql
SELECT
    pid,
    datname,
    usename,
    state,
    wait_event_type,
    wait_event,
    clock_timestamp() - query_start AS query_age,
    left(query, 200) AS query_sample
FROM pg_catalog.pg_stat_activity
WHERE application_name = 'pg-admin-CHG-2026-0001';
```

### 18.2. Lock Waits

Use `pg_blocking_pids(pid)` to identify backends blocking your job. Before canceling or terminating, check transaction owners and business impact.

### 18.3. Cancel vs. Terminate

- `pg_cancel_backend(pid)` requests cancellation of the current query; the session may survive afterward.
- `pg_terminate_backend(pid)` terminates the session, rolling back any open transaction when the connection closes.

These are high-impact administrative actions; verify PID, user, database, and `application_name` first.

### 18.4. Progress Views

Certain operations expose progress views such as `pg_stat_progress_create_index`, `pg_stat_progress_vacuum`, `pg_stat_progress_analyze`, and others depending on version. Use them to see which phase an operation is in instead of merely waiting for timeouts.

### 18.5. Metrics Outside the Database

Monitor process CPU/memory, disk I/O, networking, scheduler runtime, queue depth, and replica lag. A long-running query may be waiting on storage or locks rather than burning CPU.

## 19. Retry Wrappers and Execution Principles

A retry wrapper must:

1. Retry only explicitly classified errors.
2. Retry the entire transaction when a transaction aborts.
3. Enforce maximum attempts.
4. Use exponential backoff and jitter.
5. Enforce a total retry budget.
6. Log attempt number, SQLSTATE, and delay.
7. Never retry when commit outcome is ambiguous without reconciliation.
8. Return the final failure to the scheduler.

### 19.1. Pseudocode

```text
for attempt in 1..MAX_ATTEMPTS:
    start a fresh database transaction
    execute the complete idempotent unit of work

    if committed:
        record success
        stop

    if error is retryable and budget remains:
        rollback/close the failed transaction
        wait with exponential backoff plus jitter
        continue

    record failure
    return non-zero
```

### 19.2. Never Retry Individual Statements When Logic Depends on Prior Reads

If a transaction reads a balance, checks a condition, and updates it, retrying only the final `UPDATE` can break invariants. Retry the entire transaction to re-read fresh state.

### 19.3. Backoff with Jitter

A simple formula:

```text
delay = min(max_delay, base_delay * 2^(attempt - 1))
actual_delay = random(0, delay)
```

Cap both max attempts and max elapsed time so jobs cannot stretch indefinitely.

### 19.4. Retries Do Not Replace Incident Resolution

If every attempt times out because a lock blocker persists, retrying just repeats the failure. Log the blocker, investigate the long transaction, and stop when the budget runs out.

## 20. Schedulers: cron, systemd, and CI/CD

### 20.1. Cron

`cron` fits simple scheduled jobs. Requirements:
- Use absolute paths.
- Declare required environment variables.
- Set working directories explicitly.
- Redirect stdout/stderr to logs.
- Check exit codes and alert.
- Prevent overlap using locks.
- Never rely on interactive shell profiles.

### 20.2. systemd Timers

`systemd` services and timers can manage:
- Overall job timeouts.
- Bounded restart policies.
- Execution user/group.
- Environment files with strict permissions.
- Standard output/error routed to the journal.
- Dependencies and ordering.

Never use a restart policy to loop a destructive job indefinitely.

### 20.3. CI/CD

Migration pipelines should enforce:
- Pinned artifact/script versions.
- Verified target environments.
- Secure secret injection.
- Policy-based approval gates.
- Preflight and backup checks.
- Fail-fast execution.
- Postflight verification.
- Preserved logs and exit statuses.
- Zero secrets printed in command traces.

### 20.4. A Scheduler Is Not a Lock

A cron schedule does not guarantee the previous run finished. Use scheduler concurrency controls, OS locks, or PostgreSQL advisory locks matching the job's scope.

### 20.5. Timezones and Daylight Saving Time

Schedules should declare timezones explicitly. If jobs run on UTC, log UTC; if running on local time, account for daylight saving transitions and schedule shifts across environments.

## 21. Automation Security

### 21.1. Least Privilege

Give each job a dedicated role with minimal required rights. Metrics readers do not need `SUPERUSER`; `ANALYZE` jobs need rights only on target objects; migration roles need DDL rights strictly within assigned schemas.

### 21.2. Credential Handling

Prefer secret managers, `libpq` service files, and protected `.pgpass` files. Avoid:
- Long-lived `PGPASSWORD` in environments when better options exist.
- Passwords in command-line arguments.
- Passwords in logged URLs.
- Secrets in source control.
- Debug traces printing full commands.

### 21.3. Identity and Attribution

Give jobs dedicated users and `application_name` values. Never share one superuser account across all automation.

### 21.4. Target Allowlists

Production scripts should verify the host, database, and cluster identity match an allowlist. One misconfigured environment variable can send a staging job straight to production or vice versa.

### 21.5. Destructive Command Protection

For `DROP`, `TRUNCATE`, massive `DELETE`, or role revocations, require preflight checks, expected row bounds, target validation, and change-process approval. Never let scripts guess targets from ambiguous database names.

## 22. Postconditions and Verifying Success

### 22.1. Exit Code 0 Is Not Enough

A process can exit 0 without achieving the intended state due to flawed script logic or zero matching rows.

### 22.2. Postconditions

After every operation, verify the expected end state. Examples:
- Schema version updated.
- Index exists and `indisvalid = true`.
- Role has expected owner and privileges.
- Table has required constraints.
- Replication state is healthy.
- Job checkpoint advanced.
- Affected row counts fall within expected bounds.

### 22.3. Never Mark Success Before Commit

Write job success into the ledger inside the same transaction when feasible. If the ledger lives outside the transaction, record `STARTED`/`RUNNING` beforehand and `SUCCEEDED` only after commit plus postconditions pass.

### 22.4. Exactly-Once Requires Explicit Design

Schedulers can re-run after crashes or miss responses even when transactions committed. Exactly-once semantics never come for free from a scheduler; build them using operation keys, unique constraints, idempotency, and reconciliation.

### 22.5. Record Unambiguous Outcomes

Distinguish:
- `SUCCEEDED`.
- `FAILED`.
- `RETRYABLE_FAILURE`.
- `TIMED_OUT`.
- `UNKNOWN_OUTCOME`.
- `SKIPPED_ALREADY_APPLIED`.

Never log `SUCCEEDED` when commit status is uncertain.

## 23. Timeout Troubleshooting Runbook

1. Identify which layer timed out: connect, lock, statement, or job.
2. Record run ID, database, `application_name`, and timestamp.
3. Inspect `pg_stat_activity` to see whether the backend is still running.
4. Check `wait_event` and `pg_blocking_pids()` if the query is waiting.
5. Check PostgreSQL logs for SQLSTATEs and server cancellations.
6. Determine whether the transaction committed, rolled back, or has an unknown outcome.
7. If the client was killed, verify the backend exited and transactions rolled back.
8. Never retry destructive operations before verifying state.
9. Adjust timeouts or batch sizes only after understanding root cause.
10. Save evidence and update runbooks.

## 24. Failed Job Runbook

### 24.1. Halt Auto-Retries on Non-Retryable Errors

Permission, syntax, missing object, and constraint errors demand investigation. Never raise retry counts to paper over logic bugs.

### 24.2. Gather Evidence

Capture:
- Script version and checksum.
- Run and change ID.
- Exit code.
- SQLSTATE.
- Client and server logs.
- Target identity.
- Last successful step.
- Transaction and job ledger state.
- Rows affected and checkpoint.

### 24.3. Inspect Partial State

For workflows with non-transactional steps, identify which steps finished. Never re-run the entire script blindly if an earlier step partially created objects or indexes.

### 24.4. Choose Resume or Rollback

If operations are idempotent and checkpoints are valid, resume from a safe point. If state is ambiguous, pause for reconciliation. If compensating actions exist, follow the reviewed runbook.

### 24.5. Close the Incident or Change

Mark complete only once postconditions pass, logs are saved, and partial states are resolved.

## 25. Example: Migration with Preflight and Postflight

### 25.1. Preflight

```sql
SELECT
    current_database() AS database_name,
    current_user AS effective_role,
    session_user AS login_role,
    current_setting('server_version_num') AS server_version_num,
    pg_postmaster_start_time() AS server_started_at;
```

Confirm the database and identity match the deployment target.

### 25.2. Migration

```sql
\set ON_ERROR_STOP on

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '2min';

DO $$
BEGIN
    IF current_database() <> 'appdb' THEN
        RAISE EXCEPTION 'wrong database';
    END IF;
END
$$;

ALTER TABLE app.orders
    ADD COLUMN IF NOT EXISTS source_code text;

COMMIT;
```

`IF NOT EXISTS` prevents errors if the column already exists, yet you must still verify data type, nullability, defaults, and column/table ownership to confirm schema accuracy.

### 25.3. Postflight

```sql
SELECT
    table_schema,
    table_name,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'app'
  AND table_name = 'orders'
  AND column_name = 'source_code';
```

If the query returns no rows or the wrong data type, the job must not be marked successful.

## 26. Example: ANALYZE Job with Timeouts and Locks

```sql
\set ON_ERROR_STOP on
\timing on

SET lock_timeout = '5s';
SET statement_timeout = '10min';

ANALYZE VERBOSE app.orders;
```

`ANALYZE` generates I/O/CPU workload and requires proper privileges. It must not run under `--single-transaction` if the file includes maintenance commands disallowed in transactions. Log runtime, output, and outcome.

## 27. Example: Checking Indexes After CREATE INDEX CONCURRENTLY

`CREATE INDEX CONCURRENTLY` cannot run inside a transaction block. Once finished, inspect the catalog:

```sql
SELECT
    n.nspname AS schema_name,
    t.relname AS table_name,
    i.relname AS index_name,
    x.indisready,
    x.indisvalid
FROM pg_catalog.pg_index AS x
JOIN pg_catalog.pg_class AS i
  ON i.oid = x.indexrelid
JOIN pg_catalog.pg_class AS t
  ON t.oid = x.indrelid
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = t.relnamespace
WHERE n.nspname = 'app'
  AND t.relname = 'orders';
```

If the index is invalid after a failure, diagnose the cause and clean up/retry per runbook. Never check only whether the object name exists.

## 28. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Omitting `ON_ERROR_STOP` | `psql` continues after SQL errors | Enable fail-fast |
| Checking stdout only | Misses process failures | Check exit codes |
| Omitting connect timeout | Job hangs waiting to connect | `PGCONNECT_TIMEOUT` |
| Omitting `lock_timeout` | DDL queues indefinitely on locks | Explicit lock budget |
| Setting only client job timeouts | Server query may keep running | Combine with `statement_timeout` |
| Retrying every error | Adds load and loops permanent errors | Classify by SQLSTATE |
| Retrying only the final statement | Breaks transaction logic | Retry the entire transaction |
| Retrying after `COMMIT` disconnect | Duplicate operations | Reconcile via operation ID |
| Omitting advisory locks | Overlapping job runs | Concurrency control |
| Skipping target checks | Runs on wrong prod/database | Preflight and allowlists |
| Logging passwords | Credential leakage | Secret stores and redaction |
| Enabling `set -x` | Prints commands and secrets | Never use xtrace in prod |
| Overly long transactions | Lock, bloat, and WAL pressure | Batching and checkpoints |
| Using `--single-transaction` with `VACUUM` | Command fails | Isolate non-transactional steps |
| Using `IF NOT EXISTS` as validation | Wrong schema slips through | Postconditions and catalog checks |
| Marking success before `COMMIT` | Inaccurate ledger | Record after commit |
| Logging messages only | Hard to classify errors | SQLSTATE + exit code |
| Not rotating logs | Disk exhaustion | Retention and `logrotate` |
| Omitting postconditions | Exit 0 with broken state | Verify outcomes |
| Omitting run IDs | Hard to correlate | Correlation IDs |
| No resume plan | Re-runs cause duplicates | Checkpoints and idempotency |

## 29. New Automation Design Checklist

Before deploying, verify:

1. Target cluster, database, and schema are explicitly specified.
2. Login role follows least privilege.
3. Credentials come from a secret manager or secure `libpq` config.
4. Script version/checksum is pinned.
5. Preflight verifies version, role, and expected state.
6. Transaction boundaries are sound.
7. Non-transactional operations are isolated.
8. `ON_ERROR_STOP` is enabled for `psql` scripts.
9. Connection, lock, statement, and job timeouts are configured.
10. Job uses idempotency or an operation ledger.
11. Concurrency lock is active if overlapping runs are unsafe.
12. Retries apply only to identified transient errors.
13. Retry budget and backoff are bounded.
14. Logging includes UTC timestamps, run ID, SQLSTATE, and exit code.
15. Logs never leak credentials or sensitive PII.
16. Affected rows stay within expected bounds.
17. Postconditions are verified.
18. Scheduler receives accurate exit codes.
19. Resume, rollback, and compensation plans exist.
20. Log retention and alert owners are defined.

## 30. Practice Exercises with Answers

These exercises assume a PostgreSQL lab or staging environment. Never use example scripts to modify production without verifying targets, privileges, and recovery procedures.

### Exercise 1. Why do administrative scripts need fail-fast?

**Answer:** So an error in an earlier step stops later steps from executing against a broken partial state.

### Exercise 2. Which psql option skips reading startup files?

**Answer:** `-X`.

### Exercise 3. Which psql option stops execution on SQL errors?

**Answer:** `-v ON_ERROR_STOP=1`, or `\set ON_ERROR_STOP on` inside the script.

### Exercise 4. Which psql option suppresses interactive password prompts?

**Answer:** `-w`.

### Exercise 5. What does exit code 0 mean?

**Answer:** `psql` exited normally; postconditions are still needed to prove the desired state was achieved.

### Exercise 6. What does psql exit code 3 usually indicate?

**Answer:** A script error occurred while `ON_ERROR_STOP` was enabled.

### Exercise 7. What is PGCONNECT_TIMEOUT used for?

**Answer:** Bounding how long the client waits to establish a server connection.

### Exercise 8. How does lock_timeout differ from statement_timeout?

**Answer:** `lock_timeout` limits how long a statement waits for locks; `statement_timeout` limits total statement execution time.

### Exercise 9. What does idle_in_transaction_session_timeout protect against?

**Answer:** Terminates sessions left idle inside an open transaction for too long.

### Exercise 10. How does a job timeout differ from a statement timeout?

**Answer:** A job timeout limits the entire wrapper/process; a statement timeout limits each SQL statement on the server.

### Exercise 11. Does killing the client guarantee transaction rollback?

**Answer:** Uncommitted transactions usually roll back when the connection closes, yet commit outcomes and external/non-transactional side effects must still be verified.

### Exercise 12. Why is ON_ERROR_STOP needed with psql -f?

**Answer:** So `psql` does not continue executing subsequent statements after a SQL error.

### Exercise 13. Can --single-transaction be used with VACUUM?

**Answer:** No. `VACUUM` cannot run inside a transaction block.

### Exercise 14. Can CREATE DATABASE run inside BEGIN/COMMIT?

**Answer:** No.

### Exercise 15. Can CREATE INDEX CONCURRENTLY run inside a transaction block?

**Answer:** No.

### Exercise 16. How long does SET LOCAL stay in effect?

**Answer:** For the current transaction; once the transaction ends, it reverts to the prior value.

### Exercise 17. Why avoid holding transactions open during external API calls?

**Answer:** It holds locks and snapshots open longer, increasing bloat and lock contention.

### Exercise 18. What is an idempotent operation?

**Answer:** An operation that can be repeated and still leave the system in an equivalent state under defined conditions.

### Exercise 19. Does IF NOT EXISTS prove an object matches the expected schema?

**Answer:** No. It only prevents errors when an object with that name already exists.

### Exercise 20. Why does a migration ledger need checksums?

**Answer:** To detect if a migration file changed after being applied and prevent version drift.

### Exercise 21. What is SQLSTATE 40001?

**Answer:** Serialization failure; typically requires retrying the entire transaction.

### Exercise 22. What is SQLSTATE 40P01?

**Answer:** Deadlock detected; allows bounded retries of the entire transaction.

### Exercise 23. What is SQLSTATE 42501?

**Answer:** Insufficient privilege; halt and fix permissions.

### Exercise 24. What does SQLSTATE 57014 usually relate to?

**Answer:** Query canceled, whether by statement timeout or client/operator cancellation.

### Exercise 25. Why not retry all connection errors?

**Answer:** Connection loss can occur right during `COMMIT`, leaving the outcome ambiguous; blind retries can create duplicates.

### Exercise 26. What is the purpose of exponential backoff?

**Answer:** Increases the wait between retries to reduce pressure on a struggling system.

### Exercise 27. What is jitter?

**Answer:** A randomized component added to backoff delays to prevent many clients from retrying simultaneously.

### Exercise 28. When is an advisory transaction lock released?

**Answer:** When the transaction commits or rolls back.

### Exercise 29. When is an advisory session lock released?

**Answer:** When explicitly unlocked or when the session ends.

### Exercise 30. Does an advisory lock automatically block all SQL?

**Answer:** No. It is a cooperative lock; scripts must follow the same convention.

### Exercise 31. What is application_name used for?

**Answer:** Tagging sessions with their service, job, or change ID for visibility in `pg_stat_activity` and logs.

### Exercise 32. Why is a run ID needed?

**Answer:** Links logs, metrics, retries, and scheduler events belonging to the same execution.

### Exercise 33. Why never log passwords?

**Answer:** Logs often have broad read access and long retention; secrets could leak beyond intended boundaries.

### Exercise 34. What does psql -w do?

**Answer:** Prevents interactive password prompts; fails immediately if credentials are missing instead of hanging the job.

### Exercise 35. What permissions should .pgpass have on Unix?

**Answer:** Restricted permissions, typically `0600`, so `libpq` accepts it and other users cannot read it.

### Exercise 36. Why avoid shell set -x with secrets?

**Answer:** `xtrace` prints commands after variable expansion and can expose credentials or connection details.

### Exercise 37. What does pipefail do?

**Answer:** Ensures a pipeline returns a non-zero status if any command in the pipeline fails, rather than only the last command's status.

### Exercise 38. Does set -e catch every error in Bash?

**Answer:** No. It has contextual exceptions; explicit exit-code checking and error handling are still required.

### Exercise 39. How do ERR traps and EXIT traps differ?

**Answer:** `ERR` traps trigger on failing commands; `EXIT` traps run whenever the shell exits to log final status.

### Exercise 40. Why do log files need rotation?

**Answer:** To prevent logs from growing indefinitely and filling the filesystem.

### Exercise 41. What can PostgreSQL log_line_prefix include?

**Answer:** Timestamp, PID, user, database, `application_name`, and client address.

### Exercise 42. What is log_min_duration_statement used for?

**Answer:** Logging statements whose execution duration exceeds a configured threshold.

### Exercise 43. How does pg_cancel_backend differ from pg_terminate_backend?

**Answer:** Cancel requests aborting the current query; terminate closes the entire session.

### Exercise 44. Why inspect pg_stat_activity before terminating?

**Answer:** To verify the exact PID, user, database, application, and transaction impact.

### Exercise 45. What is a postcondition?

**Answer:** A state assertion that must hold after an operation to confirm success.

### Exercise 46. Why isn't exit code 0 enough?

**Answer:** A script can exit cleanly at the process level while failing to achieve the intended database state.

### Exercise 47. Does a scheduler guarantee exactly-once execution?

**Answer:** No. Operation keys, unique constraints, idempotency, and reconciliation are required.

### Exercise 48. How should batch checkpoints commit relative to data?

**Answer:** Update the checkpoint inside the same transaction as the batch so data and progress remain consistent.

### Exercise 49. What is the trade-off of SKIP LOCKED?

**Answer:** It skips currently locked rows; subsequent passes or workers are needed to ensure those rows eventually get processed.

### Exercise 50. Why avoid processing millions of rows in one long transaction?

**Answer:** Increases lock duration, WAL volume, rollback cost, snapshot retention, and vacuum pressure.

### Exercise 51. Does a dry run replace a backup?

**Answer:** No. Dry runs do not protect against destructive or committed non-transactional changes.

### Exercise 52. Why does CREATE INDEX CONCURRENTLY need a postflight check?

**Answer:** It can fail midway and leave an invalid index; you must verify `indisready`/`indisvalid`.

### Exercise 53. Why avoid retrying immediately when a job times out?

**Answer:** You must verify whether the server operation is still running and inspect commit/partial state before re-running.

### Exercise 54. Does a client job timeout guarantee the server query stops immediately?

**Answer:** No. Server-side `statement_timeout` and checking backend state after client termination are needed.

### Exercise 55. Why distinguish warnings from failures?

**Answer:** Warnings may be acceptable under policy; failures must return a non-success status or trigger explicit handling.

### Exercise 56. Why run target preflight checks?

**Answer:** Prevents scripts from executing against the wrong cluster, database, or role.

### Exercise 57. Which transaction do you retry on deadlock?

**Answer:** Retry the entire transaction including its initial reads and writes from the start.

### Exercise 58. When is an UNKNOWN outcome needed?

**Answer:** When connection loss occurs around commit and it is not yet clear whether the transaction committed or rolled back.

### Exercise 59. What signals should the scheduler receive?

**Answer:** Clear exit codes, log/run IDs, and accurate success/failure/timeout statuses.

### Exercise 60. Build a checklist before enabling a recurring admin job

**Suggested answer:**

1. Define owner, target cluster/database, and least-privilege role.
2. Configure credentials via a secret manager or service file.
3. Verify preconditions and target allowlists.
4. Enable `psql` `ON_ERROR_STOP` and check exit codes.
5. Set connection, lock, statement, and job timeouts.
6. Define transaction boundaries and isolate non-transactional operations.
7. Ensure idempotency, operation ledgers, and checkpoints.
8. Prevent overlaps using scheduler or advisory locks.
9. Log run ID, UTC timestamps, SQLSTATE, duration, and rows affected.
10. Verify postconditions, retry budgets, alerting, and recovery procedures.

## 31. Production Checklist

| Check | Requirement to Guarantee |
| --- | --- |
| Job owner | Accountable team or operator assigned |
| Target | Cluster, database, and schema verified |
| Identity | Dedicated role, least privilege |
| Credentials | Secret manager/service file, no logged passwords |
| psql mode | `-X`, `-w`, and `ON_ERROR_STOP` |
| Exit codes | Scheduler inspects process status |
| Transactions | Clear boundaries and rollback behavior |
| Non-transactional steps | Isolated from transaction blocks |
| Connection timeout | Bounded |
| Lock timeout | Aligned with lock budget |
| Statement timeout | Tailored per operation |
| Idle transaction timeout | Policy defined |
| Job timeout | Overall runtime budget |
| Retries | SQLSTATE allowlist and max attempts |
| Backoff | Exponential + jitter |
| Unknown commits | Reconciliation path defined |
| Idempotency | Operation keys, ledgers, and constraints |
| Concurrency | Advisory or scheduler lock |
| Batching | Bounded batch size and checkpoints |
| Dry runs | Previews and target validation |
| Logging | UTC, run ID, change ID, SQLSTATE |
| Log security | Redaction, permissions, retention |
| `application_name` | Correlates with `pg_stat_activity` |
| Server logs | Prefix and slow statement policy |
| Postconditions | Post-commit state checks |
| Affected rows | Within expected range |
| Alerting | Assigned owner and failure alerts |
| Resume | Checkpoints and recovery steps |
| Rollback | Reviewed compensating actions |
| Versioning | Scripts and SQL version-controlled |
| Evidence | Raw logs, metrics, and exit codes |
| Scheduler | Environment, timezone, and overlap policy |
| Review | Periodic job audits |

## 32. Summary

Reliable PostgreSQL automation requires controlling targets, privileges, transactions, errors, timeouts, concurrency, retries, and logs. `psql` must stop on SQL errors; schedulers must receive accurate exit codes; server-side timeouts must bound queries; client/job timeouts must bound total runtime; and logs must support tracing without exposing secrets.

Key principles:

1. **Verify the target before running.** A valid script on the wrong database is still an outage.
2. **Enable fail-fast.** Use `ON_ERROR_STOP` and check exit codes.
3. **Layer timeouts.** Connect, lock, statement, idle transaction, and job timeouts solve distinct failure modes.
4. **Group transactional changes carefully.** Know which commands cannot execute inside transactions.
5. **Design for idempotency.** Retries must never produce duplicates or corrupt data.
6. **Classify retries.** Deadlocks and serialization failures differ from permission or syntax errors.
7. **Reconcile commit outcomes.** Connection drops around `COMMIT` create ambiguous state.
8. **Prevent concurrent runs.** Use scoped scheduler locks or advisory locks.
9. **Emit structured logs.** Include UTC timestamps, run IDs, SQLSTATEs, duration, and rows affected.
10. **Protect credentials.** Never log passwords or enable `xtrace` near secrets.
11. **Enforce postconditions.** Exit code 0 must pair with state verification.
12. **Batch and checkpoint.** Avoid huge transactions and support safe resumption.
13. **Isolate non-transactional operations.** Provide dedicated preflight, postflight, and recovery steps.
14. **Observe both client and server.** `application_name`, `pg_stat_activity`, and PostgreSQL logs correlate cleanly.
15. **Prepare recovery before automating.** Know when to retry, resume, roll back, or escalate to an operator.

Job completion model:

```text
Input and target validated?
            |
            v
Connection within budget?
            |
            v
Concurrency lock acquired?
            |
            v
SQL completed and committed?
            |
            v
Postconditions verified?
            |
            v
Logs and metrics persisted?
            |
            v
Exit code accurately returned?
        /              \
       Yes              No
        |                |
        v                v
    SUCCEEDED      FAILED / UNKNOWN
```

**Final review question:** "If the job loses connection right after sending `COMMIT`, can it verify whether the operation succeeded without creating duplicates? If a migration waits too long for a lock, which timeout stops it? If `psql` hits an error mid-file, does the scheduler receive a non-zero exit code? And after a run finishes, do we have a run ID, SQLSTATE, duration, and postcondition proving the final state?" Good automation must answer all of these questions before entering a production schedule.
