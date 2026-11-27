# Organizing SQL Files and Experiment Logs for Reproducible Results in PostgreSQL

A query returning the right result once does not prove it is reliable. Without information about the initial dataset, PostgreSQL version, command execution order, or validation criteria, others cannot reproduce and evaluate your conclusion.

A SQL experiment should be **a runnable input bundle** containing the schema, sample data, queries, success criteria, orchestration script, and execution logs. Results can then be verified independently instead of relying on terminal screenshots or undocumented manual steps known only to the author.

This lesson uses `psql` and PostgreSQL to organize an end-to-end lab. Examples include `DROP SCHEMA ... CASCADE`, so **run them only in a dedicated practice database**, never against production data.

## 1. What does a "reproducible" experiment mean?

A handoff-ready test suite should answer:

1. **Goal:** which SQL semantics, constraint, or performance aspect is being tested?
2. **Input conditions:** which server, database, schema, data, and settings?
3. **Ordering:** which file runs first, and which files depend on others?
4. **Actual command:** who runs it, via `psql` or another tool, and with which flags?
5. **Expectation:** which metrics, row sets, or behaviors count as correct?
6. **Observation:** what were the actual output, errors, warnings, and exit codes?
7. **Repeatability:** can you reset and re-run without undocumented manual steps?

| Criterion | Meaning |
| --- | --- |
| Repeatability | Same environment and procedure re-run yields equivalent conclusions |
| Reproducibility | Another person builds an equivalent environment and verifies the same conclusion |
| Traceability | Logs trace back to the exact SQL files, config, and code version executed |
| Verification | Automated assertions or clear comparison criteria exist |

Results do not have to match byte-for-byte: `EXPLAIN ANALYZE` may report different timings across runs, and a `SELECT` without `ORDER BY` does not guarantee row order. Given fixed inputs, **business results** and key invariants are what must remain reproducible.

## 2. Separating responsibilities across files

Instead of putting every command into one long file, organize them as:

~~~text
postgresql-labs/
├── README.md
├── .gitignore
├── .env.example
├── sql/
│   ├── run.psql
│   ├── 00_recreate_schema.sql
│   ├── 10_seed_data.sql
│   ├── 20_queries.sql
│   ├── 30_explain.sql
│   └── 90_assertions.sql
├── scripts/
│   └── run-lab.sh
├── expected/
│   └── paid-orders.md
├── reports/
│   └── experiment-template.md
└── logs/
    └── .gitkeep
~~~

| Path | Responsibility |
| --- | --- |
| `README.md` | Goal, prerequisites, reset instructions, expected results |
| `00_recreate_schema.sql` | Recreate tables, constraints, and indexes in the lab schema |
| `10_seed_data.sql` | Load deterministic seed data |
| `20_queries.sql` | SQL queries under study |
| `30_explain.sql` | Query plan analysis when needed |
| `90_assertions.sql` | Validate invariants and raise an error if wrong |
| `run.psql` | Orchestrate execution order inside `psql` |
| `scripts/run-lab.sh` | Invoke `psql`, capture logs, and check exit codes |
| `expected/` | Expected result sets or behavioral descriptions |
| `reports/` | Conclusion reports tied to specific runs |
| `logs/` | Execution evidence, stdout/stderr, and metadata |

Prefixes `00`, `10`, `20`, `90` make filenames readable; **they do not make PostgreSQL execute files in order automatically**. `run.psql` is where the dependency order is declared.

~~~mermaid
flowchart TD
    A["README and environment"] --> B["00: Create schema"]
    B --> C["10: Seed data"]
    C --> D["20: Queries"]
    D --> E["90: Assertions"]
    E --> F{"Run valid?"}
    F -->|"Yes"| G["Log PASS + report"]
    F -->|"No"| H["Log FAIL + investigate"]
~~~

## 3. Creating an isolated lab database

Suppose you name the database `lab_pg52`. With an administrative role permitted to create databases, run:

~~~bash
createdb -h 127.0.0.1 -p 5432 -U postgres lab_pg52
~~~

Creating the database only needs to happen once. Grant a `lab_user` role appropriate privileges inside the lab database; never use cluster-wide administrative privileges for routine exercises.

Verify connectivity before resetting:

~~~bash
psql -X -h 127.0.0.1 -p 5432 \
  -U lab_user -d lab_pg52 \
  -c "SELECT current_database(), current_user, version();"
~~~

Database and role names can be adjusted to fit your environment. Always confirm you are in **the right practice database** before running schema-dropping commands. In shared environments, each person or CI job should have its own database/schema so nobody wipes someone else's data.

## 4. File 00_recreate_schema.sql

Lab goal: count paid orders per customer while retaining customers who have 0 orders.

~~~sql
-- RUN ONLY IN database lab_pg52.
BEGIN;

DROP SCHEMA IF EXISTS lab52 CASCADE;
CREATE SCHEMA lab52;

CREATE TABLE lab52.customers (
    customer_id integer PRIMARY KEY,
    customer_name text NOT NULL,
    city text NOT NULL
);

CREATE TABLE lab52.orders (
    order_id integer PRIMARY KEY,
    customer_id integer NOT NULL
        REFERENCES lab52.customers (customer_id),
    status text NOT NULL
        CHECK (status IN ('paid', 'pending', 'cancelled')),
    total numeric(12, 2) NOT NULL CHECK (total >= 0),
    created_at timestamptz NOT NULL
);

CREATE INDEX idx_lab52_orders_customer_status
    ON lab52.orders (customer_id, status);

COMMIT;
~~~

Explanation:

- `DROP SCHEMA IF EXISTS lab52 CASCADE` deletes every object inside schema `lab52`, including prior data. This is a **destructive operation**, suitable only for a privately owned practice schema.
- `BEGIN` and `COMMIT` group DDL into a transaction. PostgreSQL supports rolling back many common DDL statements, though not every administrative command is allowed inside a transaction.
- `lab52.customers` and `lab52.orders` use schema-qualified names, reducing reliance on `search_path`.
- `PRIMARY KEY`, `FOREIGN KEY`, and `CHECK` prevent invalid seed data from slipping in silently.
- `numeric(12,2)` preserves exact decimal arithmetic for monetary totals; `timestamptz` captures unambiguous points in time.

Never replace `lab52` with `public` and run this against a shared team database. In real systems, use controlled schema migrations, not learning reset scripts.

## 5. File 10_seed_data.sql: deterministic data

~~~sql
BEGIN;

INSERT INTO lab52.customers
    (customer_id, customer_name, city)
VALUES
    (1, 'An',   'HCM'),
    (2, 'Binh', 'HAN'),
    (3, 'Chi',  'HCM'),
    (4, 'Dung', 'DNG');

INSERT INTO lab52.orders
    (order_id, customer_id, status, total, created_at)
VALUES
    (101, 1, 'paid',      120.00, '2026-11-01 08:00:00+00'),
    (102, 1, 'paid',       80.00, '2026-11-01 09:00:00+00'),
    (103, 2, 'paid',      150.00, '2026-11-02 10:00:00+00'),
    (104, 2, 'cancelled', 300.00, '2026-11-02 11:00:00+00'),
    (105, 3, 'paid',      220.00, '2026-11-03 12:00:00+00');

COMMIT;
~~~

This dataset is chosen deliberately:

| Customer | Paid order count | Paid revenue |
| --- | ---: | ---: |
| An | 2 | 200.00 |
| Binh | 1 | 150.00 |
| Chi | 1 | 220.00 |
| Dung | 0 | 0.00 |
| **Total** | **4** | **570.00** |

Dung has no orders; Binh has one cancelled order. These two cases verify filtering and `LEFT JOIN` behavior.

All IDs and timestamps are fixed, avoiding `now()` or `random()`. Those functions fit other labs, but inside datasets meant for exact comparisons, they cause outputs to vary with the clock or random state.

## 6. File 20_queries.sql: queries under verification

~~~sql
SET TIME ZONE 'UTC';
SET DateStyle TO 'ISO, YMD';

-- Include customers who have zero paid orders.
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS paid_order_count,
    COALESCE(SUM(o.total), 0)::numeric(12, 2) AS paid_revenue
FROM lab52.customers AS c
LEFT JOIN lab52.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'paid'
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;

-- Summary totals for reconciliation.
SELECT
    COUNT(*) AS paid_orders,
    COALESCE(SUM(total), 0)::numeric(12, 2) AS paid_revenue
FROM lab52.orders
WHERE status = 'paid';
~~~

The first query must return the four rows shown in the seed summary table. The second query must return count `4` and revenue `570.00`.

Important details:

1. Placing `status = 'paid'` in the `ON` clause preserves customers who have no paid orders.
2. `COUNT(o.order_id)` does not count `NULL` rows produced on the orders side when `LEFT JOIN` finds no match.
3. `COALESCE` returns 0 revenue for customers with no orders.
4. `ORDER BY c.customer_id` makes row order deterministic for comparison.
5. `numeric` is preferable to approximate floating-point types when validating monetary sums.

Never rely on PostgreSQL "usually returning rows by ID" without `ORDER BY`. The optimizer is free to change access paths and output ordering.

## 7. File 90_assertions.sql: turning expectations into errors on mismatch

~~~sql
DO $$
DECLARE
    v_paid_count bigint;
    v_paid_revenue numeric;
    v_customer_count bigint;
BEGIN
    SELECT COUNT(*), COALESCE(SUM(total), 0)
    INTO v_paid_count, v_paid_revenue
    FROM lab52.orders
    WHERE status = 'paid';

    SELECT COUNT(*)
    INTO v_customer_count
    FROM lab52.customers;

    IF v_paid_count <> 4 THEN
        RAISE EXCEPTION
            'Wrong paid count: actual=%, expected=4',
            v_paid_count;
    END IF;

    IF v_paid_revenue <> 570.00 THEN
        RAISE EXCEPTION
            'Wrong revenue: actual=%, expected=570.00',
            v_paid_revenue;
    END IF;

    IF v_customer_count <> 4 THEN
        RAISE EXCEPTION
            'Wrong customer count: actual=%, expected=4',
            v_customer_count;
    END IF;

    RAISE NOTICE 'LAB52 assertions passed';
END
$$ LANGUAGE plpgsql;
~~~

PostgreSQL executes the `DO` block as an anonymous PL/pgSQL routine. If a condition fails, `RAISE EXCEPTION` triggers an error so the runner/CI marks the run failed. When all checks pass, `NOTICE` confirms assertions ran to completion.

Assertions can be extended to check:

- Exact list of returned IDs.
- Per-customer revenue, including customers with 0 orders.
- Absence of orphan rows or negative values.
- A rolled-back operation leaving no residual data impact.
- Results from an indexed query matching an established baseline query.

Never assert "Execution Time must equal 0.123 ms," as timing varies with hardware and server load.

## 8. File run.psql: canonical execution order

~~~text
\set ON_ERROR_STOP on
\pset pager off
\pset null '(null)'

\echo === Environment ===
SELECT
    current_database() AS database_name,
    current_user AS role_name,
    current_setting('server_version') AS server_version,
    current_setting('TimeZone') AS timezone_name;

\echo === Recreate schema ===
\ir 00_recreate_schema.sql

\echo === Seed data ===
\ir 10_seed_data.sql

\echo === Queries ===
\ir 20_queries.sql

\echo === Assertions ===
\ir 90_assertions.sql

\echo === Finished ===
~~~

Inside `psql`:

- `\i file.sql` includes a file by the provided path.
- `\ir file.sql` includes a file relative to **the directory of the file containing the include command**, which is very convenient when `run.psql` and SQL files all reside in `sql/`.
- `\set ON_ERROR_STOP on` halts the script when an error occurs.
- `\pset pager off` prevents an interactive pager from interrupting automated runs.
- `\pset null '(null)'` distinguishes SQL NULL from empty strings.
- `\echo` inserts clear markers into logs.

Commands starting with `\` are **`psql` meta-commands**, not SQL. When executing via JDBC or a SQL console that does not support psql, use a different orchestration mechanism.

## 9. Invoking psql from the terminal

From the repository root:

~~~bash
psql \
  -X \
  -v ON_ERROR_STOP=1 \
  -h 127.0.0.1 \
  -p 5432 \
  -U lab_user \
  -d lab_pg52 \
  -f sql/run.psql
~~~

| Option | Meaning |
| --- | --- |
| `-X` | Skips personal `.psqlrc` config, reducing environment drift |
| `-v ON_ERROR_STOP=1` | Stops on SQL script errors |
| `-h`, `-p` | Explicitly specifies host and port |
| `-U`, `-d` | Explicitly specifies role and database |
| `-f` | Executes commands from the script |

With `ON_ERROR_STOP`, `psql -f` can return exit code `3` when an error occurs inside the script. Connection failures or client errors return other codes. Treat **any nonzero exit code as a failure**, rather than scanning output only for the word ERROR.

### The single-transaction option

`psql -1` can wrap statements from `-f` and `-c` in a single transaction, but this example already includes `BEGIN` / `COMMIT` inside setup files. Do not enable `-1` without redesigning transaction boundaries.

Also, commands like `CREATE DATABASE` cannot run inside a transaction block. Therefore the lab database is created beforehand, outside `run.psql`.

## 10. Runner and logging script

Contents of `scripts/run-lab.sh` for Bash:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p logs

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
log_file="logs/$stamp-lab52.log"
meta_file="logs/$stamp-lab52.meta.txt"

{
  printf 'experiment=lab52-paid-orders\n'
  printf 'started_at_utc=%s\n' "$stamp"
  printf 'host=127.0.0.1\n'
  printf 'port=5432\n'
  printf 'database=lab_pg52\n'
  printf 'role=lab_user\n'
  printf 'script=sql/run.psql\n'
  psql --version
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    printf 'git_commit=%s\n' "$(git rev-parse HEAD)"
  fi
} > "$meta_file"

if psql -X -a -v ON_ERROR_STOP=1 \
    -h 127.0.0.1 -p 5432 -U lab_user -d lab_pg52 \
    -f sql/run.psql > "$log_file" 2>&1; then
  printf 'exit_code=0\n' >> "$meta_file"
  printf 'PASS: %s\n' "$log_file"
else
  result=$?
  printf 'exit_code=%s\n' "$result" >> "$meta_file"
  printf 'FAIL (exit %s): %s\n' "$result" "$log_file" >&2
  exit "$result"
fi
~~~

The script records:

- Start timestamp in UTC for traceability.
- Database name, role, host, port, and script executed.
- `psql` version and Git commit SHA if available.
- Executed `psql` input lines via `-a` (echo input), results, and errors.
- Exit code in metadata and runner PASS/FAIL status.

`> "$log_file" 2>&1` merges `psql` stdout and stderr into one file. For automated parsing, you can split `.out.log` and `.err.log`. If two jobs start in the same second, `stamp` can collide; in CI, include a unique run ID or job ID.

**Security:** never hard-code passwords in scripts. Use your environment's credential store or `.pgpass` with strict permissions. On Unix, `.pgpass` requires owner-only permissions (e.g., `chmod 600`); never commit real credentials.

## 11. README template so teammates can run it themselves

A README needs minimal essentials:

~~~markdown
# Lab 52 - Paid orders

## Goal
Verify that LEFT JOIN preserves all customers and computes paid order counts accurately.

## Requirements
- PostgreSQL server and psql client
- Dedicated lab database lab_pg52 for practice
- Role lab_user permitted to create schemas in the lab database
- Bash if running scripts/run-lab.sh

## Run
From the root directory:

    psql -X -v ON_ERROR_STOP=1 -h 127.0.0.1 -p 5432 \
      -U lab_user -d lab_pg52 -f sql/run.psql

Or:

    bash scripts/run-lab.sh

## Expected results
- 4 customers
- 4 paid orders, total 570.00
- Dung still appears with count 0
- Assertions pass and psql exits with code 0

## Warning
Script 00_recreate_schema.sql drops schema lab52.
Never run against a production database.
~~~

Others should never have to ask "which table gets created first?", "which role do I use?", "what sample data is needed?", or "how do I know the output is right?" All of that belongs in reproducibility documentation.

## 12. Structured experiment logs

A per-run report can record:

~~~markdown
# Experiment - lab52-paid-orders

- Run ID: <run identifier>
- Goal: verify paid order statistics with LEFT JOIN
- SQL version: <Git commit and working tree status>
- PostgreSQL server: <version>
- psql client: <version>
- Database/schema: lab_pg52 / lab52
- Host/port/role: <lab values>
- Timezone: UTC
- Started at: <UTC timestamp>
- Script: sql/run.psql
- Expected result: count 4, revenue 570.00
- Observed result: <values from log>
- Exit code: <number>
- Discrepancies/warnings: <if any>
- Log: logs/<run-id>-lab52.log
- Conclusion: PASS/FAIL, root cause, and next actions
~~~

Each field answers one question: **when, where, which code, what ran, what happened**.

Place expected outcomes in `expected/` or assertions; place observed output in logs. Never edit raw logs after a run to make them match expectations. Write explanations in `reports/`.

## 13. Controlling sources of non-determinism

### 13.1. SELECT ordering

~~~sql
-- Ordering not guaranteed.
SELECT customer_id FROM lab52.customers;

-- Deterministic ordering.
SELECT customer_id
FROM lab52.customers
ORDER BY customer_id;
~~~

`LIMIT` results can also vary without `ORDER BY`:

~~~sql
SELECT customer_id
FROM lab52.customers
ORDER BY customer_id
LIMIT 3;
~~~

When the sort column can contain duplicates, add a tie-breaker key so ordering is completely deterministic.

### 13.2. Dates, locales, and formatting

`now()`, `clock_timestamp()`, and `CURRENT_DATE` depend on execution time. `timestamptz` formats according to the session `TimeZone`. That is why the example uses `+00` timestamps and `SET TIME ZONE 'UTC'`.

Text sorting can depend on database collation. When comparing Unicode outputs across systems, control or document collation rules.

### 13.3. Random values and sequences

`random()` produces varying data unless seeded intentionally. Sequence `nextval()` does not roll back the same way table rows do and can leave gaps in IDs. When writing seed scripts for exact verification, pick fixed IDs or reset sequences properly.

### 13.4. Personal configuration

`.psqlrc`, `PGHOST`, `PGDATABASE`, `search_path`, `DateStyle`, `TimeZone`, and role-level settings can cause results to differ across machines. Use `-X`, pass explicit connection settings, and record any influential parameters.

## 14. Recording EXPLAIN and measuring performance

A `sql/30_explain.sql` file can contain:

~~~sql
EXPLAIN (VERBOSE, COSTS, FORMAT TEXT)
SELECT c.customer_id, COUNT(o.order_id)
FROM lab52.customers AS c
LEFT JOIN lab52.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'paid'
GROUP BY c.customer_id
ORDER BY c.customer_id;
~~~

`EXPLAIN` shows only the estimated plan. To measure actual runtime metrics:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT c.customer_id, COUNT(o.order_id)
FROM lab52.customers AS c
LEFT JOIN lab52.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'paid'
GROUP BY c.customer_id
ORDER BY c.customer_id;
~~~

`EXPLAIN ANALYZE` **actually executes the SQL statement**. On `UPDATE` or `DELETE`, it modifies data; test only in a safe lab and inside an appropriate transaction/rollback.

When recording performance metrics, log server version, table/index sizes, statistics state, execution plan, actual rows, buffers, timings, system load, and run counts. Do not expect identical execution times across runs. On tables with only a few rows, PostgreSQL may pick `Seq Scan` even when an index exists; that does not prove the index is broken.

## 15. Exporting CSV when automated diffing is needed

Logs containing SQL and notices are great for debugging, yet hard to diff programmatically. Export clean results separately:

~~~bash
psql -X -v ON_ERROR_STOP=1 \
  -h 127.0.0.1 -p 5432 -U lab_user -d lab_pg52 \
  --csv \
  -c "
    SELECT customer_id, customer_name
    FROM lab52.customers
    ORDER BY customer_id;
  " > customers.csv
~~~

Depending on your `psql` version, you can use `\copy (SELECT ...) TO STDOUT WITH (FORMAT csv, HEADER true)` instead of `--csv`. Distinguish server-side `COPY` from client-side `\copy` to avoid file-permission confusion.

Separate **execution logs**, **result artifacts**, and **conclusion reports**. To diff CSVs reliably, normalize row ordering, null representation, encoding, time zone, and data formatting.

## 16. Concurrency experiments need two separate sessions

Topics like MVCC, lock waits, and deadlocks cannot be simulated properly with a single sequential `run.psql` stream. They require a multi-session timeline:

| Step | Session A | Session B | State |
| --- | --- | --- | --- |
| 1 | `BEGIN` | — | A opens transaction |
| 2 | `UPDATE ... WHERE id=1` | — | A holds lock |
| 3 | — | `BEGIN` | B opens transaction |
| 4 | — | `UPDATE ... WHERE id=1` | B waits on A |
| 5 | `COMMIT` | UPDATE resumes | A releases lock |
| 6 | — | `COMMIT` | B finishes |

Record each session's `pg_backend_pid()`, synchronization steps, timeouts, outcomes, and rollback/commit details. Never rely solely on `sleep 1` hoping operations always interleave identically across machines.

## 17. Integrating with Git and keeping data safe

**Should be committed:** SQL files, runners, README, assertions, synthetic sample data, small expected results, and report templates.

**Avoid committing:** passwords, tokens, logs containing sensitive data, production dumps, and large regenerable artifacts.

Example `.gitignore`:

~~~gitignore
.env
.env.*
!.env.example
.pgpass
*.pgpass
logs/*.log
logs/*.meta.txt
artifacts/*.csv
~~~

`.gitignore` does not purge secrets already committed into Git history. Manage credentials and scrub sensitive data at the source.

A SHA from `git rev-parse HEAD` identifies only the commit, not uncommitted edits. For strictly traceable experiments, also record working-tree status or checksums of the exact files executed.

## 18. Integrating into CI

Once `run.psql` has assertions and clear exit codes, a pipeline can:

~~~text
Checkout source code
   ↓
Start test PostgreSQL
   ↓
Create isolated lab database/role
   ↓
Run psql -X -v ON_ERROR_STOP=1 -f sql/run.psql
   ↓
Archive logs, metadata, and artifacts
   ↓
Mark PASS or FAIL
~~~

Mandatory rules:

- Never point reset scripts at production.
- Give each job an isolated database or schema.
- Record or pin the PostgreSQL server version.
- Pull credentials from the CI secret store.
- Preserve logs even when a job fails.
- Any nonzero exit code must fail the job.

When using Docker, record the exact image tag, hostname, port, and where the client runs. `127.0.0.1` inside one container does not automatically reach PostgreSQL running in another container.

## 19. Common mistakes when saving and running experiments

### Saving only query.sql

Without schema and input data, results are hard to reproduce. Save setup, seed data, and execution order too.

### Leaving ON_ERROR_STOP disabled

SQL can fail while the script keeps running. Always enable it and check exit codes in automation.

### Using cwd-dependent include paths

Scripts work when run from `sql/` but break from the repo root. Use `\ir` and a runner that fixes its working directory.

### Using overly broad DROP CASCADE

Can wipe someone else's data. Scope drops strictly to your own lab database/schema and verify the connection first.

### Comparing SELECT without ORDER BY

The same set of rows can come back in a different order. Add `ORDER BY` with a deterministic tie-breaker.

### Confusing expected with actual

Never edit logs to match expectations. Write expectations beforehand, keep actual outputs in logs, and summarize findings in reports.

### Assuming EXPLAIN ANALYZE is "read-only"

For DML, the query executes and modifies data. Measure only in a safe test environment.

### Letting passwords and real data enter logs

`psql -a` can print SQL literals verbatim. Use synthetic data, secret stores, and proper retention rules.

### Judging performance by a single number

Timings vary with cache warmth and load. Measure across multiple runs, document conditions, and inspect distributions.

### Recording only the Git commit when uncommitted edits exist

The commit SHA no longer matches the exact files executed. Record dirty working-tree status or file checksums when needed.

## 20. Workflow for creating a new PostgreSQL lab

1. Define a testable hypothesis.
2. Prepare an isolated practice database/schema.
3. Write the schema and constraint creation script.
4. Write deterministic seed data, including edge cases.
5. Write queries with explicit filters and ordering.
6. Write assertions encoding expectations.
7. Orchestrate files in `run.psql` via `\ir`.
8. Run `psql -X` with `ON_ERROR_STOP` and explicit connection details.
9. Record logs, exit code, timestamps, versions, and commit/checksum.
10. Compare expected vs. actual, and investigate errors in raw logs.
11. Re-run from a clean state after fixes.
12. Commit source files and a clear README so others can reproduce it.

A great indicator is when a teammate or CI job can stand up a fresh database solely from the repository and README without asking the author what manual steps were run beforehand.

## 21. Conclusion

**A reproducible PostgreSQL experiment is not just a correct SQL query—it is a complete workflow with inputs, ordering, checks, and evidence.** Splitting files along **reset schema → seed → queries → assertions**, running `psql` with `\ir` and `ON_ERROR_STOP`, storing logs with metadata, and tying results to code versions allow anyone to verify conclusions independently.

When input conditions are controlled and every discrepancy is traceable in logs, learning queries, indexes, and transactions becomes reliable, maintainable, and easy to scale into automated testing for PostgreSQL projects.
