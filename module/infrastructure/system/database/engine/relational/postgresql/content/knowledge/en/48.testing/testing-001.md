# Separating Schema, SQL, Transaction, and Performance Testing in PostgreSQL

A PostgreSQL system can start up successfully and still contain serious bugs. A migration might create the wrong constraint; a SQL statement might return wrong results when encountering NULL; two concurrent transactions might overwrite each other's data; a query that is fast on a development machine might become tens of times slower when data grows or concurrency is high.

Therefore, database testing needs to be divided into groups with different goals and measurement methods. **Schema testing** verifies structure, constraints, indexes, dependencies, and migrations. **SQL testing** verifies statements, functions, views, and business results. **Transaction testing** verifies correctness across commits, rollbacks, isolation, and concurrency. **Performance testing** measures latency, throughput, resource usage, and the ability to maintain SLOs under load.

These groups are related to one another, but they cannot replace one another. A query returning correct results in a single session does not prove that a transaction is safe when run concurrently. A migration creating all expected objects does not prove that legacy SQL remains compatible. A good benchmark also does not prove that the data is correct.

This lesson belongs to the **Testing** chapter of the *Database Engine Relational PostgreSQL* module. It guides you on how to split a test suite by layer, design fixtures and environments, write SQL/PostgreSQL examples, verify concurrency, measure performance, and organize them in CI/CD.

> **Principle:** Each test must answer a clear question, with deterministic input data, expected results, and reproducible evidence. Choosing the right testing layer helps locate bugs where they arise and reduces diagnosis time.

## 1. Learning Objectives

After this lesson, you can:

1. Explain why schema, SQL, transaction, and performance tests must be separated.
2. Determine appropriate scope and assertions for each test group.
3. Create isolated test databases with a specific PostgreSQL version.
4. Verify tables, columns, types, constraints, indexes, views, triggers, and routines.
5. Test migrations from an old schema to a new schema.
6. Write SQL tests for results, NULL, boundary values, and side effects.
7. Test functions, procedures, triggers, and permissions.
8. Design reproducible fixtures and seed data.
9. Verify commits, rollbacks, savepoints, and deferred constraints.
10. Verify isolation levels, lost updates, non-repeatable reads, and serialization failures.
11. Create concurrency tests with multiple database sessions.
12. Measure query plans, latency, throughput, CPU, I/O, WAL, and lock waits.
13. Use EXPLAIN, pg_stat_statements, and pgbench appropriately.
14. Design performance tests with baselines and representative workloads.
15. Separate smoke tests, regression tests, integration tests, and load tests.
16. Integrate appropriate tests into CI/CD without destabilizing the pipeline.
17. Diagnose failures based on test type and evidence.
18. Build a test coverage matrix and release criteria.

## 2. Why Separate Testing Groups?

A database has multiple layers of behavior. A change in one layer can affect another layer, but the ways bugs are detected differ.

| Test group | Primary question | Evidence |
|---|---|---|
| Schema | Does the database structure match the contract? | Catalog assertions, schema diff, migration result |
| SQL | Does the query/function return the right results and side effects? | Expected rows, values, SQLSTATE, object state |
| Transaction | Do multiple operations preserve consistency under commit/rollback/concurrency? | Commit state, isolation schedule, lock/serialization result |
| Performance | Does the system meet SLOs under the expected workload? | Latency distribution, throughput, resource metrics |

### 2.1. Schema tests do not replace SQL tests

A table can have the right columns and constraints while a function still calculates the wrong total amount. Schema tests verify that objects exist and are defined correctly; SQL tests verify behavior.

### 2.2. SQL tests do not replace transaction tests

An UPDATE statement that runs correctly with a single session can cause lost updates when two sessions write concurrently. Transaction tests must control operation ordering and verify post-commit results.

### 2.3. Transaction tests do not replace performance tests

A transaction can be correct in terms of consistency yet hold locks too long, causing queueing and increasing p99 latency. Performance tests measure impact under load and over time.

### 2.4. Performance tests do not replace correctness tests

A fast query that returns missing rows or uses the wrong calculation is still a bug. Before benchmarking, verify query semantics and the dataset.

### 2.5. Tests can share a pipeline but need separate reporting

A CI pipeline can run all four groups. However, results must be clearly categorized to know whether a failure lies in DDL, SQL, concurrency, or resource usage.

## 3. Testing Scope and the Test Pyramid

Not every test needs to run on every pull request.

A common organization is:

```text
                 End-to-end / Production-like
               Performance and resilience tests
             Transaction / concurrency integration
                 SQL behavior regression
                 Schema and migration tests
                 Static SQL/config checks
```

Tests at the bottom are typically fast, have few dependencies, and run frequently. Tests higher up require production-like environments, large datasets, or many sessions, so they run less often but must be scheduled and have appropriate gates.

### 3.1. Static checks

You can check migration naming, SQL lint, forbidden patterns, configuration syntax, and dependency declarations without needing a database.

### 3.2. Schema tests

Initialize an empty database, apply migrations, and assert on the catalog. These can run on every pull request if time permits.

### 3.3. SQL behavior tests

Load small fixtures, invoke queries/functions, and compare against expected results. These should be fast and deterministic.

### 3.4. Transaction tests

Require at least two connections and a controlled schedule. These can run in integration CI or a dedicated test suite.

### 3.5. Performance/load tests

Require stable resources, a representative dataset, and multiple runs. Usually run on a dedicated runner, staging, or pre-release; shared ephemeral CI hosts should not be used to draw accurate conclusions about p99.

## 4. Designing the Test Environment

A test is only trustworthy when you know which PostgreSQL version, configuration, and data it ran on.

Record:
- PostgreSQL major/minor version.
- Image/package digest.
- Extensions and versions.
- Encoding, locale, and collation.
- Important postgresql.conf settings.
- Authentication and roles.
- Hardware/container CPU, memory, and storage limits.
- Connection pool settings.
- Migration framework/version.
- Dataset seed and generator version.

### 4.1. Isolate the database per test run

Prefer a dedicated database or an ephemeral PostgreSQL instance for each job/test suite. Avoid letting parallel tests share a schema and delete each other's data.

### 4.2. Use the same major version as production

A test passing on PostgreSQL 16 does not prove a migration will pass on PostgreSQL 17. Use the target version for migration tests; if supporting multiple versions, run a compatibility matrix.

### 4.3. Containers do not automatically mean production-like

Containers are convenient for CI, but default memory, storage, and kernel environments can differ from production. Use containers for correctness/integration; performance gates need resource limits and a controlled environment.

### 4.4. Do not use unprocessed production data

Generate synthetic data or mask/anonymize according to policy. If skew/cardinality needs to be preserved, generate data with a similar distribution without exposing sensitive information.

### 4.5. Test roles and permissions

Do not run every test as superuser. Create roles matching the application, migration owner, read-only user, and reporting user. Overly broad privileges can mask permission bugs in production.

## 5. Managing Fixtures and Test Data

A fixture is controlled input data so tests are repeatable.

A good fixture:
- Is small enough to run fast.
- Has rows representing business rules.
- Includes NULL and boundary cases.
- Has stable keys.
- Does not depend on unintended insert order.
- Can be reset between test cases.
- Contains no sensitive data.

### 5.1. Deterministic seed data

Example:

```sql
INSERT INTO customers (id, email, status)
VALUES
    (101, 'a@example.test', 'active'),
    (102, 'b@example.test', 'inactive'),
    (103, NULL, 'pending');
```

Use the `.test` domain for illustrative addresses. With identity/sequence columns, if a test assigns IDs manually, synchronize the sequence before switching to auto-generated inserts.

### 5.2. Test data must include boundary cases

For example, with an orders table:
- No items.
- One item.
- Multiple items.
- Quantity equal to 0 if allowed by the schema.
- Values near precision limits.
- NULL in optional fields.
- Duplicate business key.
- Non-existent customer.
- Timestamps near day/month/DST boundaries.

### 5.3. Create fixtures via migrations and factories

You can use SQL files, test factories, or application fixtures. Avoid manually copying the schema into tests because the test schema can drift from actual migrations.

### 5.4. Resetting data

Several options:
- Transaction rollback for isolated tests.
- Truncate tables in an isolated database.
- Drop/recreate the database between suites.
- Restore a snapshot/template database.

TRUNCATE ... CASCADE can wipe many dependent tables; use it only in an isolated test environment with a clear scope.

### 5.5. Do not depend on row order

SQL does not guarantee row order without ORDER BY. Assertions should compare sets or require explicit ordering.

## 6. Schema Testing: Verifying the Structural Contract

Schema tests verify that the database has the exact objects and properties expected by the application.

Typical scope includes:
- Schemas and ownership.
- Tables/partitioned tables.
- Columns, data types, defaults, generated/identity attributes.
- NULLability.
- Primary/foreign/unique/check constraints.
- Indexes and operator classes.
- Views/materialized views.
- Sequences.
- Functions/procedures and signatures.
- Triggers.
- Enums/domains/composite types.
- Grants, roles, and row-level security.
- Extensions.
- Dependencies.

### 6.1. Verify object existence

Example:

```sql
SELECT to_regclass('public.orders') IS NOT NULL AS orders_exists;
```

In the test, assert that the result is true. `to_regclass` returns NULL if the relation does not exist.

### 6.2. Verify column definitions

```sql
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'orders'
ORDER BY ordinal_position;
```

Compare important columns against the defined contract. `information_schema` provides standardized views; when PostgreSQL-specific details such as identity/generated attributes are needed, use `pg_catalog`.

### 6.3. Verify data type and typmod

`data_type` may not show full precision/scale or length. You can use `format_type` with catalog metadata:

```sql
SELECT
    a.attname,
    format_type(a.atttypid, a.atttypmod) AS formatted_type,
    a.attnotnull
FROM pg_attribute AS a
JOIN pg_class AS c ON c.oid = a.attrelid
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relname = 'orders'
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
```

### 6.4. Verify constraints

```sql
SELECT
    conname,
    contype,
    convalidated,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'public.orders'::regclass
ORDER BY conname;
```

Check `convalidated` to detect constraints added with NOT VALID that have not yet been validated.

### 6.5. Verify indexes

```sql
SELECT
    indexrelid::regclass AS index_name,
    indisunique,
    indisprimary,
    indisvalid,
    indisready,
    pg_get_indexdef(indexrelid) AS definition
FROM pg_index
WHERE indrelid = 'public.orders'::regclass
ORDER BY indexrelid::regclass::text;
```

An index that exists with `indisvalid = false` cannot be considered a usable index. Check the expression, predicate, included columns, and operator class if they are part of the contract.

### 6.6. Verify foreign keys

Schema tests should verify referenced table/columns, ON UPDATE, ON DELETE, match type, and deferrability. Asserting only the constraint name can miss a wrong definition.

### 6.7. Verify defaults and generated columns

Verify that the default expression is right, sequence ownership is appropriate, and generated expressions are correct. Do not just check whether a column has a default; check the stored expression.

### 6.8. Verify views and routines

Use `pg_get_viewdef`, `pg_get_functiondef`, or catalog signatures to check required definitions. Avoid snapshotting the entire catalog unnecessarily because it can create brittle tests when PostgreSQL versions change.

### 6.9. Verify grants

```sql
SELECT
    grantee,
    privilege_type,
    is_grantable
FROM information_schema.role_table_grants
WHERE table_schema = 'public'
  AND table_name = 'orders'
ORDER BY grantee, privilege_type;
```

Also run tests using the application role to confirm actual privileges. A catalog query alone does not prove every access path works.

## 7. Schema Migration Tests

Schema tests must verify both the final schema and the path to that schema.

### 7.1. Test from an empty database

Workflow:
1. Create a new database.
2. Run all migrations in order.
3. Verify migration history.
4. Assert tables, constraints, indexes, views, functions, and grants.
5. Run SQL smoke tests.

This detects new migrations with missing dependencies or wrong ordering.

### 7.2. Test upgrading from a realistic old schema

An empty database does not represent a production upgrade. Restore a snapshot/schema fixture of an older version and run the latest migrations.

Test supported source versions and data states that may exist.

### 7.3. Test migrations with data

Load rows with NULLs, duplicate values, values outside the new domain, large tables, foreign key relationships, historical timestamps, and extension-specific objects.

After migration, check row counts, data mapping, constraints, and application behavior.

### 7.4. Test idempotency according to the framework's contract

Versioned migrations usually run only once. There is no need to force every migration SQL script to be infinitely repeatable if the framework guarantees versioning. However, operational backfill/recovery scripts need safe retries and state checks before mutating.

### 7.5. Test mid-flight failures

If a migration spans multiple transactions or includes non-transactional commands, simulate failures at critical points:
- DDL succeeds but the next step fails.
- CREATE INDEX CONCURRENTLY is canceled.
- Backfill worker stops mid-batch.
- Deployment stops after expand but before the app release.

Verify that the database is in a resumable state or has a recovery runbook.

### 7.6. Schema diff

You can dump schema-only before/after and compare, but raw diffs need normalization for owners, privileges, or irrelevant ordering. Prefer assertions on key contracts over snapshotting the entire output.

### 7.7. Do not only test fast migrations

A migration might pass on a 20-row fixture yet block a billion-row production table. Schema correctness and operational safety need separate testing on data of representative scale.

## 8. SQL Testing: Verifying Semantics and Results

SQL tests verify that statements return the right rows/values and produce the right side effects.

Scope:
- SELECT filters, joins, aggregates.
- INSERT/UPDATE/DELETE.
- Upsert and conflict handling.
- Functions/procedures.
- Views.
- Triggers.
- Operators/casts.
- NULL semantics.
- Sorting/pagination.
- JSON/array/date/time/numeric behavior.
- SQLSTATE/error conditions.

### 8.1. Verify results using expected rows

```sql
SELECT
    order_id,
    total_amount
FROM order_totals
WHERE order_id = 9001;
```

Tests must assert the exact row count and `total_amount` value, not just assert that the query raises no exception.

### 8.2. NULL semantics

SQL uses three-valued logic: TRUE, FALSE, and UNKNOWN. Comparing `column = NULL` does not return TRUE; use `IS NULL` or `IS NOT DISTINCT FROM` as intended.

Example:

```sql
SELECT count(*)
FROM customers
WHERE email IS NULL;
```

Test cases must distinguish NULL from empty strings, zero, and missing JSON keys.

### 8.3. JOIN semantics

Verify that INNER JOIN filters out unmatched rows, LEFT JOIN keeps unmatched rows, predicates in ON vs. WHERE can yield different results, duplicate keys increase row counts, and NULL keys do not match with standard equality.

### 8.4. Aggregate semantics

Test `count(*)`, `count(column)`, `sum`, `avg`, and `min`/`max` with empty sets, NULLs, and duplicate rows. `sum` can return NULL on an empty set; if business logic expects zero, use `COALESCE` intentionally.

### 8.5. ORDER BY and pagination

If pagination requires stable ordering, add a unique tie-breaker:

```sql
SELECT id, created_at
FROM events
ORDER BY created_at DESC, id DESC
LIMIT 50;
```

Do not test ordering when a query does not declare an ORDER BY clause.

### 8.6. Upsert behavior

```sql
INSERT INTO inventory (sku, quantity)
VALUES ('SKU-01', 5)
ON CONFLICT (sku)
DO UPDATE SET quantity = inventory.quantity + EXCLUDED.quantity
RETURNING sku, quantity;
```

Test the insert path, conflict path, concurrency, and expected quantity. Ensure the right unique constraint is the conflict target.

### 8.7. SQLSTATE and error behavior

If the application depends on error categories, assert on SQLSTATE rather than comparing full error messages that may vary by version/locale. For example, unique violation typically has SQLSTATE `23505`; foreign key violation `23503`; serialization failure `40001`.

### 8.8. Test side effects

After INSERT/UPDATE/DELETE, check trigger side effects, audit rows, updated timestamps, related aggregates, outbox records, sequence state when relevant, and foreign key cascades.

## 9. Testing Functions, Procedures, and Triggers

### 9.1. Function contract

Verify input types and defaults, return type/shape, NULL handling, volatility/strictness when part of the contract, error conditions, permissions, and `search_path` assumptions.

### 9.2. Function tests in SQL

Example tax calculation function:

```sql
CREATE OR REPLACE FUNCTION calculate_tax(amount numeric, rate numeric)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT round(amount * rate, 2);
$$;
```

A test can verify:

```sql
SELECT calculate_tax(100.00, 0.10) = 10.00 AS expected_result;
```

Add cases for NULL, negative numbers if permitted, precision/scale, and rounding boundaries.

### 9.3. Procedures and transaction control

Procedures can be invoked with CALL. Transaction control inside a procedure has restrictions depending on how it is invoked and the execution context. Test in the exact same way the application invokes it; do not infer behavior from a different context.

### 9.4. Trigger tests

Test each event (INSERT/UPDATE/DELETE), conditional firing, OLD/NEW values, recursion risk, and interaction with bulk operations. Assert post-trigger data and behavior when a trigger raises an exception.

### 9.5. SECURITY DEFINER

Run tests with an unprivileged role to verify permission boundaries. Check owner, safe `search_path`, and execute privileges. A function running under superuser does not prove the app role has the right permissions.

## 10. Testing Types, Collation, and Time Behavior

### 10.1. Numeric

Test precision, scale, rounding, overflow, and division. For money-like values, explicitly define the numeric scale and rounding policy.

### 10.2. Timestamp

Distinguish `timestamp without time zone` from `timestamptz`. Test session `TimeZone`, daylight saving boundaries, and serialization through the driver.

### 10.3. Text and collation

Test Unicode normalization, case sensitivity, accents, ordering, and unique constraints under the collation. Results can depend on the locale provider/version.

### 10.4. JSONB

Test missing keys, JSON null, SQL NULL, arrays, nested objects, containment operators, and index usage. JSON null and SQL NULL are two different states.

### 10.5. Arrays and ranges

Test empty arrays, NULL arrays, NULL elements, lower bounds if used by the application, inclusive/exclusive range bounds, empty ranges, and overlap/containment operators.

### 10.6. Enum and domain types

Test valid values, invalid values, casts, defaults, and application deserialization. If an enum gains a new value, check how older clients handle unknown values.

## 11. Choosing Frameworks and Tools for SQL Tests

Several options:
- pgTAP: extension providing assertion functions for PostgreSQL objects and query results.
- pg_prove: popular runner for pgTAP test files.
- psql scripts: suitable for smoke tests and simple tests with exit-on-error.
- Application test framework: uses the real driver to test SQL issued by the application.
- Migration framework: checks ordering/versions and runs schema migrations.
- SQL lint/parser: catches syntax/style/patterns before runtime.

### 11.1. pgTAP

Illustrative example:

```sql
BEGIN;
SELECT plan(2);

SELECT has_table('public', 'orders', 'orders table exists');
SELECT col_not_null('public', 'orders', 'id', 'orders id is not null');

SELECT * FROM finish();
ROLLBACK;
```

Assertion names and argument order should be verified against the installed pgTAP version. A test suite can run inside a transaction to roll back test objects/data if the tests do not require separate transaction boundaries.

### 11.2. psql smoke test

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f tests/smoke.sql
```

`ON_ERROR_STOP=1` makes `psql` return an error when a statement fails. CI must check the exit code, save logs, and not treat output containing `ERROR` lines as passing.

### 11.3. Application integration tests

Use the same driver, connection pool, and transaction boundaries as the application. SQL executed directly via `psql` may differ from prepared statement behavior or type mapping in the driver.

### 11.4. One framework is not mandatory for all tests

pgTAP fits catalog/SQL assertions; application test frameworks fit business flows; pgbench fits workloads. Choose the tool based on the question to answer.

## 12. Transaction Testing: Goals and Scope

Transaction tests verify that multiple statements execute as a single unit and preserve consistency when errors or concurrency occur.

Check:
- Atomicity: all changes commit or roll back according to the transaction boundary.
- Consistency: constraints/invariants remain true.
- Isolation: concurrent transactions observe behavior according to the isolation level.
- Durability: confirmed commits survive restarts/failures according to the durability configuration.

ACID is a conceptual framework; each test must define a specific invariant.

### 12.1. Atomicity

If a workflow writes an order, order lines, and a payment record, an error in the final step must roll back the changes within the same transaction.

### 12.2. Consistency

Constraints, foreign keys, unique keys, and business invariants must hold before and after the transaction.

### 12.3. Isolation

Test whether concurrent transactions cause lost updates, duplicate processing, or invalid states.

### 12.4. Durability

Commit durability depends on PostgreSQL configuration, storage, and replication policy. Tests must specify whether they are checking local commit, synchronous replica acknowledgment, or disaster recovery guarantees.

## 13. Testing Commit, Rollback, and Savepoints

### 13.1. Commit

```sql
BEGIN;

INSERT INTO accounts (id, balance)
VALUES (1, 100.00);

COMMIT;
```

After commit, another connection must see the committed row according to isolation semantics.

### 13.2. Rollback

```sql
BEGIN;

UPDATE accounts
SET balance = balance - 25
WHERE id = 1;

ROLLBACK;
```

After rollback, `balance` must retain its pre-transaction value.

### 13.3. Savepoint

```sql
BEGIN;

UPDATE accounts
SET balance = balance - 10
WHERE id = 1;

SAVEPOINT before_optional_step;

UPDATE accounts
SET balance = balance - 1000
WHERE id = 1;

ROLLBACK TO SAVEPOINT before_optional_step;

COMMIT;
```

The test verifies that the part before the savepoint is committed and the part after the savepoint is rolled back.

### 13.4. Deferred constraints

A DEFERRABLE constraint can be checked at the end of the transaction rather than after each statement. Test both success and failure at COMMIT; do not only check statement results before commit.

### 13.5. Sequence behavior on rollback

Sequence values from `nextval` are not returned when a transaction rolls back. Tests should not assume contiguous IDs without gaps. This is intentional behavior to support concurrency.

## 14. Isolation Levels in PostgreSQL

PostgreSQL supports:
- Read Committed.
- Repeatable Read.
- Serializable.

READ UNCOMMITTED is treated as READ COMMITTED in PostgreSQL.

### 14.1. Read Committed

Each statement typically sees a new snapshot as of the time the statement begins. Two SELECTs in the same transaction can see different data if another transaction commits in between.

### 14.2. Repeatable Read

A transaction uses a stable snapshot for ordinary queries within the transaction. PostgreSQL implements this using snapshot isolation; certain anomalies can still occur in general models, so it should not be equated with Serializable.

### 14.3. Serializable

PostgreSQL uses Serializable Snapshot Isolation to detect dependencies that could create anomalies. A transaction can be aborted with a serialization failure and need to retry the entire transaction.

### 14.4. Setting the isolation level

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT balance
FROM accounts
WHERE id = 1;

COMMIT;
```

Set the level before the transaction executes a query. Test the exact isolation level that the application transaction uses.

## 15. Testing Concurrency with Multiple Sessions

A concurrency test requires at least two independent connections. True interleaving cannot be simulated by running sequentially on a single connection.

### 15.1. Testing lost updates

Suppose the initial balance is 100. Two sessions both read 100, each subtracts 10 and writes back 90. The final result can be 90 instead of 80 if the application uses an unsafe read-modify-write under Read Committed.

Illustrative schedule:

```text
Session A                 Session B
---------                 ---------
BEGIN                     BEGIN
SELECT balance = 100      SELECT balance = 100
compute 90                 compute 90
UPDATE balance = 90
                          UPDATE balance = 90
COMMIT                    COMMIT
Final balance may be 90
```

A solution can be an atomic update:

```sql
UPDATE accounts
SET balance = balance - 10
WHERE id = 1;
```

Or locking the row before reading/modifying, or using optimistic concurrency with a version column. Tests must verify that the final result matches the business rule.

### 15.2. SELECT FOR UPDATE

```sql
BEGIN;

SELECT balance
FROM accounts
WHERE id = 1
FOR UPDATE;

-- Application calculates and writes based on the locked row.

COMMIT;
```

The second session must wait for the lock or follow defined behavior. Tests must verify timeout/retry policies and ensure locks are not held long while the application performs external work.

### 15.3. Deadlocks

Create two transactions that lock two rows in opposite orders. PostgreSQL detects the deadlock and aborts one transaction with SQLSTATE `40P01`. Tests verify that the application handles retries properly and retries all required transaction logic.

### 15.4. Serialization failures

With Serializable, test schedules that can trigger serialization failures. SQLSTATE `40001` is the signal to retry the transaction per policy. Do not retry only the last statement if earlier logic depended on the aborted snapshot.

### 15.5. Unique conflicts

Two sessions concurrently insert the same business key. Verify that the unique constraint protects the invariant and the application handles `23505` or `ON CONFLICT` properly.

### 15.6. Lock timeout and statement timeout

Test when a lock is not granted within the limit and when a query runs too long. Distinguish:
- `lock_timeout`: wait time per lock acquisition attempt.
- `statement_timeout`: execution time of a statement.
- `idle_in_transaction_session_timeout`: limit for an idle session inside a transaction.

Do not set global timeouts in tests without understanding their impact on other statements.

## 16. Testing Business Transactions

Instead of testing only isolation primitives, write tests around workflows.

Example of transferring money between two accounts:
1. Debit source account.
2. Credit destination account.
3. Write ledger/audit record.
4. Commit.

Invariant: the total balance remains unchanged if there is no fee, and no account violates business rules.

### 16.1. Concurrent transfers

Run multiple opposite-direction transfers. Lock accounts in a consistent ID order to reduce deadlocks. Test balances, ledger sums, and retry behavior.

### 16.2. Idempotency

A request can be resent due to a timeout or network retry. Use an idempotency key with a unique constraint so the same business operation is not executed twice.

### 16.3. Outbox pattern

If a transaction both updates business rows and emits an event, write an outbox row in the same transaction. Test that rollback leaves no phantom event and publisher retries neither lose nor duplicate the logical event.

### 16.4. Deferred business validation

If an invariant can only be checked at the end of the transaction, consider deferred constraints or application validation. Test commit boundaries and transaction interleavings.

### 16.5. External side effects

A PostgreSQL transaction rollback cannot automatically retract emails, HTTP requests, or messages already sent externally. Workflow testing must verify whether side effects are emitted post-commit via outbox/worker or compensated via a saga.

## 17. Performance Testing: Defining SLOs and Workloads

Performance testing starts from requirements, not from an arbitrary query benchmark.

Define expected throughput, p50/p95/p99 latency, peak concurrency, read/write mix, data volume and growth, burst patterns, connection count, lock contention, replication topology, resource limits, maintenance windows, and error budget.

### 17.1. Latency percentiles

Mean latency can hide tail latency. A system with a 20 ms average but a 2-second p99 can cause timeouts for a subset of requests. Measure p50, p95, and p99 alongside error rates.

### 17.2. Throughput

Record transactions/second, queries/second, or business operations/second. Distinguish sustained throughput from short bursts.

### 17.3. Workload mix

A SELECT-only benchmark does not represent a system with inserts/updates, vacuum, index maintenance, and replication. Use a mix close to production.

### 17.4. Capacity headroom

Meeting SLOs at 100% CPU in a test leaves little headroom for traffic spikes, autovacuum, or failover. Define the maximum acceptable resource utilization.

## 18. Using EXPLAIN to Understand Query Cost

### 18.1. Basic EXPLAIN

```sql
EXPLAIN
SELECT *
FROM orders
WHERE customer_id = 42;
```

The estimated plan shows how the planner intends to execute the query without actually running it.

### 18.2. EXPLAIN ANALYZE

```sql
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT *
FROM orders
WHERE customer_id = 42;
```

This command executes the statement and reports actual timing/rows/buffers. Run it only on safe queries and in appropriate environments. For UPDATE/DELETE, the statement actually modifies data; you can use transaction rollback in a test environment, keeping in mind that side effects outside the transaction or sequence advancements are not necessarily undone.

### 18.3. Estimated rows vs. actual rows

Large discrepancies between estimated and actual rows can cause the planner to choose an unsuitable join/order/index. Check statistics, data skew, correlated columns, and expression statistics when needed.

### 18.4. Buffers and I/O

BUFFERS helps distinguish cache hits, reads, and temp blocks. If `track_io_timing` is enabled, I/O timing can be observed in supported reports.

### 18.5. Do not assert rigid plan text

The planner can change across PostgreSQL versions, statistics, and cost settings. Tests should usually assert latency/rows/resource budgets or key properties rather than requiring line-by-line identical plan text.

### 18.6. A query plan is not a full benchmark

A single EXPLAIN ANALYZE does not represent concurrency, cache state, connection pools, network, or mixed workloads. Use it for diagnosis and to complement workload benchmarks.

## 19. Using pg_stat_statements and Database Statistics

If the workload needs query-level tracking, `pg_stat_statements` provides statistics for normalized statements.

```sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read,
    temp_blks_written
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

Column names can differ across extension versions. Check the actual schema before writing dashboards/tests.

### 19.1. Before and after snapshots

Capture counters before the test, run the workload, capture counters after the test, and compute the delta. Do not compare cumulative counters if extension stats were not reset or test intervals differ.

### 19.2. pg_stat_database

Can be used to observe transactions, blocks, temp files, and conflicts at the database level. These are aggregate counters and do not replace per-request tracing.

### 19.3. pg_stat_activity

Used to observe active sessions, waits, transaction age, and query state during a load test. Appropriate privileges are needed to view query text/session details.

### 19.4. Lock metrics

Combine `pg_locks`, `pg_stat_activity`, and application tracing to identify lock contention. A slow query may be waiting on a lock rather than consuming CPU.

## 20. Using pgbench for Load Tests

`pgbench` is a benchmarking tool bundled with PostgreSQL. It supports a built-in TPC-B-like workload and custom scripts.

### 20.1. Initialize test data

Example on a dedicated test database:

```bash
pgbench -i -s 10 testdb
```

The scale factor determines the size of the built-in dataset. Choose the size based on goals and storage budget.

### 20.2. Run the benchmark

```bash
pgbench -c 20 -j 4 -T 120 -P 10 testdb
```

Example parameters:
- `-c`: number of concurrent clients.
- `-j`: number of client worker threads.
- `-T`: test duration.
- `-P`: progress output interval.

### 20.3. Custom script

You can write a SQL file for a business workload:

```sql
\set customer_id random(1, 100000)
BEGIN;
SELECT balance
FROM accounts
WHERE id = :customer_id;
COMMIT;
```

This is an illustrative workload only. To test write paths, add statements with transaction semantics and appropriate cleanup/reset.

### 20.4. Standardize benchmarks

Record the `pgbench` version, PostgreSQL version, command line, client host, dataset scale, settings, connection topology, and result logs. Run a warm-up before taking measurements.

### 20.5. Do not compare two non-equivalent environments

If CPU, storage, network, or cache differ, state so clearly. Use a normalized workload and multiple runs; do not conclude that a query engine is slower just from two numbers on different machines.

## 21. Performance Tests for Write-Heavy Workloads

Write workloads have different costs from read workloads:
- WAL generation.
- Index maintenance.
- Foreign key checks.
- Trigger execution.
- Row locks.
- Checkpoint pressure.
- Vacuum/dead tuples.
- Synchronous replication acknowledgment.

### 21.1. Batch inserts

Compare single-row inserts, multi-row inserts, and COPY when they reflect the application path. Do not optimize with COPY if the real application must process small individual transactions.

### 21.2. Update amplification

An update can create a new tuple version, update indexes, and generate WAL. Measure updated rows, WAL bytes, bloat, and vacuum work.

### 21.3. HOT updates

If an update modifies only non-indexed columns and the page has sufficient free space, PostgreSQL can perform a HOT update. Index design and `fillfactor` affect this capability. Do not assume every update is HOT.

### 21.4. Checkpoints and WAL

Load tests longer than one checkpoint cycle help reveal steadier behavior. Monitor WAL generation, checkpoint write/sync time, and replication lag.

### 21.5. Vacuum

Run write-heavy tests long enough to observe autovacuum. Short tests may finish before maintenance pressure appears.

## 22. Testing Connection Pooling and Concurrency Capacity

Database performance depends on connection counts and how the pooler distributes sessions.

Check application connection pool size, PgBouncer mode, `max_connections`, pool queueing, transaction duration, prepared statements, idle-in-transaction sessions, connection churn, and failover reconnect storms.

### 22.1. Do not increase max_connections to solve everything

Many connections consume memory and increase scheduling/lock contention. Check pool sizing, query duration, and backpressure before increasing it.

### 22.2. Transaction pooling

Transaction pooling can restrict session-level features. Test prepared statements, temporary tables, session variables, advisory locks, and SET assumptions under the pooler mode.

### 22.3. Connection saturation

Load tests must measure time spent waiting to acquire a connection in the application pool, not just query execution time inside PostgreSQL.

### 22.4. Reconnect storms

After a failover/restart, many clients may reconnect simultaneously. Test jitter/backoff and limits on connection attempts.

## 23. Performance Testing for Indexes and the Planner

### 23.1. Index effectiveness

Compare queries with/without an index on a representative dataset. Check whether the planner uses the index under realistic conditions.

### 23.2. Index size and cache

Large indexes can consume buffer cache and storage. An index that speeds up one query can reduce the cache hit rate of another workload.

### 23.3. Composite indexes

Column order affects query predicates/ordering. Test real query patterns; do not mechanically create indexes matching column lists.

### 23.4. Partial/expression indexes

Test that predicates/expressions match the query and function semantics. Expression volatility and collation can affect index eligibility.

### 23.5. Statistics

After loads/restores/backfills, run `ANALYZE` appropriately. Test both data skew and correlated columns; uniform/average distributions can make estimates wrong.

## 24. Designing Stable Performance Tests

A reliable benchmark requires controlling variables.

1. Pin PostgreSQL/extension versions.
2. Use equivalent hardware/storage or resource limits.
3. Generate a representative dataset.
4. Run `ANALYZE` and establish an appropriate vacuum state.
5. Define the cold/warm cache strategy.
6. Warm up before measuring.
7. Run multiple iterations.
8. Record p50/p95/p99 and throughput.
9. Record CPU, memory, I/O, WAL, locks, and replica lag.
10. Define a regression budget.
11. Save raw logs and command lines.
12. Compare the same workload and same duration.

### 24.1. Cold cache vs. warm cache

Cold-cache testing may require restarting/clearing caches in a dedicated environment; there is no universal safe way to clear all OS caches on every platform. Document the method clearly. Warm-cache tests need consistent warm-up.

### 24.2. Data scale

Use multiple scale points if growth matters: small, current, and projected. Query plans and index/cache behavior can change once the dataset exceeds memory.

### 24.3. Load shape

Test constant load, ramp-up, burst, and soak tests. Soak tests detect bloat, memory growth, worker leaks, and degradation over time.

### 24.4. Regression budget

For example, a team might set thresholds:
- p95 of critical queries increases by no more than 10%.
- Throughput decreases by no more than 5%.
- Error rate does not exceed the SLO.
- Replica lag does not exceed the replication budget.

These are examples. Choose thresholds based on baseline, SLO, and business impact.

## 25. Combining All Four Test Groups in a Feature Change

Suppose a new feature adds `orders.status` and a query aggregating revenue by status.

**Schema tests**
- Column `status` has the right type/default/nullability.
- Check constraint or enum is correct.
- Appropriate index exists and is valid.
- Migration from an old schema with data succeeds.

**SQL tests**
- Aggregate query returns the right totals.
- NULL/unknown status is handled per policy.
- Filtering by time range and status is correct.
- Function/view returns the right shape.

**Transaction tests**
- Order state transitions do not create invalid states.
- Two workers do not process the same order twice.
- Rollback occurs when the payment step fails.
- Concurrent updates are serialized or conflicts handled properly.

**Performance tests**
- Aggregate query meets its latency budget.
- Index does not reduce write throughput beyond budget.
- Query remains stable at peak concurrency and large dataset size.
- WAL/replica lag stays within limits.

A feature is complete only when each layer has appropriate evidence.

## 26. Testing Data Migrations and Backfills

A backfill is a large write workload, so it requires combining schema, SQL, transaction, and performance tests.

### 26.1. Correctness

Assert correct mapping for all categories and edge cases. For large tables, use reconciliation by key ranges or canonicalized checksums.

### 26.2. Idempotency

Re-run batches or restart a worker mid-way. Results must be correct and not overwrite newer changes.

### 26.3. Transaction boundaries

Each batch should have a clear commit boundary. Test crashing after commit but before updating the progress marker, or vice versa, to ensure resume logic neither skips nor duplicates rows.

### 26.4. Concurrency

Run the backfill alongside application writes. Test race conditions between the row snapshot and new updates. Use predicates/versioning/locking as designed.

### 26.5. Performance

Measure batch duration, WAL, replica lag, lock waits, dead tuples, and vacuum. Establish pause/resume thresholds.

### 26.6. Recovery

Test when a worker fails, a connection drops, a replica lags, or disk approaches threshold. Do not test only the happy path running cleanly from start to finish.

## 27. Security and Permission Tests

Although this lesson focuses on the four main groups, permissions are part of the schema and SQL contract.

Verify:
- The application role has only the privileges it needs.
- The read-only role cannot mutate data.
- The migration role has appropriate DDL permissions.
- Function execution grants are correct.
- RLS policies filter rows accurately.
- SECURITY DEFINER does not open privilege escalation.
- `search_path` does not permit object shadowing.
- Sensitive columns are not exposed via views/logs.

Run tests using realistic roles, not only the database owner.

## 28. CI/CD: Organizing Stages

A reference pipeline:

```text
Commit / Pull Request
        |
        v
Static SQL and migration checks
        |
        v
Create ephemeral PostgreSQL
        |
        v
Apply migrations
        |
        v
Schema assertions
        |
        v
SQL behavior tests
        |
        v
Transaction/concurrency tests
        |
        v
Build and package
        |
        v
Staging performance / load suite
        |
        v
Release gate
```

### 28.1. Pull request stage

Run static checks, schema creation, migration tests, SQL unit tests, and fast transaction tests. If multiple PostgreSQL versions are needed, use matrix jobs.

### 28.2. Nightly stage

Run larger datasets, randomized/property tests, concurrency schedules, soak tests, and the performance regression suite.

### 28.3. Pre-release stage

Run migrations from a production-like snapshot, backup/restore, failover, peak load, and operational acceptance.

### 28.4. Deployment gate

Do not deploy when schema migrations fail or critical SQL/transaction regressions remain open. Performance regressions need clear severity/thresholds; avoid failing the pipeline over meaningless noise.

### 28.5. Artifacts and evidence

Save the PostgreSQL version/image digest, migration logs, test reports, SQLSTATE/error details, key EXPLAIN plans, benchmark commands/results, environment settings, and dataset seed/version.

## 29. Test Parallelism and Isolation

Tests running in parallel can cause contention and flaky results.

### 29.1. Database per worker

Create a dedicated database/schema per worker or test shard. Do not use the same fixed IDs in a shared database.

### 29.2. Shared resources

If tests share a cluster, they still contend for CPU, I/O, and connections. Do not run performance tests in parallel with correctness suites on the same instance if stable performance results are needed.

### 29.3. Advisory locks

Advisory locks can be used to coordinate shared test resources, but they require a clear namespace/key scheme and proper release.

### 29.4. Flaky transaction tests

Use barriers/latches and explicit schedules instead of arbitrary sleeps. Sleep-based tests depend heavily on runner speed and cause flakiness.

### 29.5. Cleanup on test failure

Ensure connections are closed, transactions rolled back, and test databases dropped even when an assertion fails. For process crashes, rely on job cleanup/ephemeral instance lifecycles.

## 30. Test Reporting: Reporting Each Layer Separately

A useful report can present:

| Group | Passed | Failed | Skipped | Duration | Evidence |
|---|---:|---:|---:|---:|---|
| Schema |  |  |  |  | Migration/catalog assertions |
| SQL |  |  |  |  | Query/function results |
| Transaction |  |  |  |  | Multi-session schedules |
| Performance |  |  |  |  | Latency/throughput/resource logs |

Do not collapse everything into a single line saying "database tests passed". A test suite might pass SQL while transaction tests never ran; the report must make this clear.

### 30.1. Failure classification

- Schema failure: migration, object definition, dependency, or permission.
- SQL failure: syntax, semantics, data mapping, or expected result.
- Transaction failure: isolation, lock, deadlock, retry, or atomicity.
- Performance failure: latency, throughput, resource saturation, or regression.

### 30.2. Reproducibility

Record command, seed, version, and environment. If a bug occurs only in a concurrency test, save the schedule and session logs.

### 30.3. Avoid false passes

Tests skipped due to missing extensions or permissions should not be reported together as passes. Distinguish skipped, not applicable, and failed.

## 31. Diagnosing Failures by Layer

### 31.1. Schema test fails

Check whether migrations ran in the right order, catalog definitions match the PostgreSQL version, `search_path`/schema owner differ, extensions/packages are available, constraints/indexes are valid/validated, and whether the test checks the contract rather than unstable internal details.

### 31.2. SQL test fails

Check whether fixtures are accurate and deterministic, NULL/duplicate/ordering semantics are defined, session settings such as timezone/`search_path`/collation differ, the driver maps types differently from `psql`, triggers/functions have side effects, and SQLSTATE differs from expectations.

### 31.3. Transaction test fails

Check the actual isolation level, transaction boundaries/autocommit, lock order/blocker chain, retry policy for `40001`/`40P01`, idempotency/duplicate requests, and whether the test schedule is deterministic or relies on random timing.

### 31.4. Performance test fails

Check dataset/statistics/cache state, query plan/estimated rows, CPU/memory/I/O saturation, lock waits/connection pool queues, WAL/checkpoints/vacuum, and whether the regression reproduces across multiple runs.

## 32. Anti-Patterns to Avoid

- Only testing database startup.
- Only asserting object existence without checking definitions.
- Running all tests as superuser.
- Using fixtures that differ from the production schema.
- Depending on row order without ORDER BY.
- Failing to test NULL and boundary values.
- Using a single session to claim transaction concurrency safety.
- Using fixed sleeps to control concurrency.
- Measuring only average latency.
- Benchmarking on overly small datasets.
- Running performance suites on shared runners under uncontrolled load.
- Asserting exact EXPLAIN text across PostgreSQL versions.
- Running EXPLAIN ANALYZE on destructive statements without isolation.
- Assuming rollback undoes sequence values or external side effects.
- Only testing migrations from an empty database.
- Ignoring migration failures/retries.
- Treating skipped tests as passes.
- Failing to save environment, seed, and raw evidence.

## 33. Example Test Plan for a Release

Suppose a release adds a `payments` table, a fee calculation function, and a payment capture workflow.

| Test ID | Group | Scenario | Expected result |
|---|---|---|---|
| DB-S-01 | Schema | Apply migration on empty DB | Table, PK, FK, index are correct |
| DB-S-02 | Schema | Upgrade DB with existing orders | Existing rows are preserved |
| DB-Q-01 | SQL | Calculate fee for standard amount | Value matches rounding rule |
| DB-Q-02 | SQL | NULL/negative amount | Behavior matches domain rules |
| DB-Q-03 | SQL | Duplicate external reference | Unique violation/ON CONFLICT works |
| DB-T-01 | Transaction | Payment step fails | Order/payment changes roll back |
| DB-T-02 | Transaction | Two workers capture same order | Only one logical capture |
| DB-T-03 | Transaction | Serialization/deadlock retry | Workflow retries safely |
| DB-P-01 | Performance | Capture at peak concurrency | p95/p99 within SLO |
| DB-P-02 | Performance | Bulk payment ingest | Throughput and WAL within budget |
| DB-P-03 | Performance | Reporting query | Plan and latency meet budget |

### 33.1. Entry criteria

- Migrations reviewed.
- Test database matches target PostgreSQL version.
- Fixtures and seeds versioned.
- Expected business rules approved.
- Performance thresholds defined.

### 33.2. Exit criteria

- No open schema/SQL/transaction blockers.
- Performance meets SLO or has risk acceptance.
- Test report includes evidence.
- Skipped tests have a reason and owner.
- Known issues have severity, mitigation, and deadline.

## 34. Schema Test Checklist

- [ ] Create an empty database and apply all migrations.
- [ ] Upgrade from supported source schema versions.
- [ ] Verify schemas, tables, and partitions.
- [ ] Verify column types, defaults, identity/generated, and nullability.
- [ ] Verify PK/FK/UNIQUE/CHECK and deferrability.
- [ ] Verify indexes, expressions, predicates, and validity.
- [ ] Verify views/materialized views.
- [ ] Verify functions/procedures/signatures.
- [ ] Verify triggers and event behavior.
- [ ] Verify sequences, enums, domains, and extensions.
- [ ] Verify grants, roles, and RLS.
- [ ] Verify migration history and failure recovery.

## 35. SQL Test Checklist

- [ ] Test expected rows and values.
- [ ] Test NULL/empty/zero semantics.
- [ ] Test joins and duplicate cardinality.
- [ ] Test aggregates on empty sets.
- [ ] Test ordering and pagination stability.
- [ ] Test INSERT/UPDATE/DELETE/UPSERT.
- [ ] Test functions, procedures, and triggers.
- [ ] Test SQLSTATE/error behavior.
- [ ] Test numeric/date/time/JSON/array/collation edge cases.
- [ ] Test permissions using application roles.
- [ ] Test side effects and audit/outbox records.
- [ ] Test using the application's real driver.

## 36. Transaction Test Checklist

- [ ] Test commit and rollback.
- [ ] Test savepoints.
- [ ] Test deferred constraints at commit.
- [ ] Test sequence behavior on rollback.
- [ ] Test Read Committed/Repeatable Read/Serializable per use case.
- [ ] Test lost updates and concurrent upserts.
- [ ] Test row locks and lock timeouts.
- [ ] Test deadlock detection/retry.
- [ ] Test serialization failure/retry.
- [ ] Test idempotency and duplicate requests.
- [ ] Test outbox/external side effects.
- [ ] Test multiple sessions with deterministic schedules.

## 37. Performance Test Checklist

- [ ] Define SLO, workload mix, and concurrency.
- [ ] Record PostgreSQL version/config/hardware.
- [ ] Use a representative dataset with skew.
- [ ] Warm up and run multiple measurements.
- [ ] Record p50/p95/p99, throughput, and error rate.
- [ ] Collect EXPLAIN ANALYZE/BUFFERS for critical queries.
- [ ] Monitor CPU, memory, I/O, and temp files.
- [ ] Monitor WAL, checkpoints, vacuum, and replica lag.
- [ ] Measure connection pool queues and lock waits.
- [ ] Test read-heavy, write-heavy, mixed, burst, and soak workloads.
- [ ] Define a regression budget.
- [ ] Save raw results and benchmark commands.

## 38. Best Practices

- Separate schema assertions, SQL behavior, transaction schedules, and load benchmarks into distinct suites.
- Run tests on the real/target PostgreSQL version.
- Use deterministic fixtures and database isolation.
- Assert important behaviors/contracts instead of unstable catalog internals.
- Test migrations from older schemas containing data.
- Use application roles and the real driver.
- Coordinate concurrency with barriers instead of sleeps.
- Test retries for SQLSTATE `40001` and `40P01` when workflows can encounter them.
- Measure tail latency, throughput, and resource metrics.
- Separate correctness CI from performance runners with controlled environments.
- Save test evidence and classify skipped/failed results.
- Update the test plan when schemas, PostgreSQL major versions, or workloads change.

## 39. Official Reference Documentation

- [PostgreSQL — Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): constraint semantics.
- [PostgreSQL — Information Schema](https://www.postgresql.org/docs/current/information-schema.html): schema metadata views.
- [PostgreSQL — System Catalogs](https://www.postgresql.org/docs/current/catalogs.html): catalog definitions.
- [PostgreSQL — Transactions](https://www.postgresql.org/docs/current/tutorial-transactions.html): transaction basics.
- [PostgreSQL — Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): isolation levels and anomalies.
- [PostgreSQL — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): row/table locks and deadlocks.
- [PostgreSQL — EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html): plan inspection and execution.
- [PostgreSQL — Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html): database and session statistics.
- [PostgreSQL — pg_stat_statements](https://www.postgresql.org/docs/current/pgstatstatements.html): query-level statistics.
- [PostgreSQL — pgbench](https://www.postgresql.org/docs/current/pgbench.html): benchmark tool.
- [PostgreSQL — Error Codes](https://www.postgresql.org/docs/current/errcodes-appendix.html): SQLSTATE categories.
- [pgTAP](https://pgtap.org/documentation.html): SQL testing assertions for PostgreSQL.

Paths containing `/current/` change with the current documentation version. When writing tests for a production cluster, use the manual for the exact major version and the actual versions of related extensions/frameworks.

## 40. Summary

Separating schema, SQL, transaction, and performance testing clarifies exactly what is being proven:

1. **Schema tests** verify that structure and migrations produce the right contract.
2. **SQL tests** verify that statements, functions, triggers, and business results are correct on boundary data.
3. **Transaction tests** verify atomicity, isolation, locking, retries, and consistency when multiple sessions operate concurrently.
4. **Performance tests** verify that latency, throughput, and resource usage meet requirements on a representative workload.

The four groups should share fixtures, versions, and business expectations while keeping assertions and evidence separate. When a release changes schema or SQL, run correctness tests first; once logic and consistency are verified, measure performance in a controlled environment. A reliable database release must prove correct data, safe transactions, and workloads meeting SLOs.
