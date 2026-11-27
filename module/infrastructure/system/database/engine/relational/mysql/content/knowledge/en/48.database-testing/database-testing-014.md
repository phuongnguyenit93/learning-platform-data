# Organizing Evidence for Bug Reproduction and Regression Evaluation

A MySQL bug can only be fixed with confidence when the team can reproduce it, understand the conditions that trigger it, and prove the fix does not break previously working behavior. A screenshot or a single error-message line is rarely enough. You must gather structured evidence: environment version and configuration, schema, minimal data, SQL statements with parameters, transaction boundaries, concurrent operation ordering, expected results, and actual results.

An evidence packet is the collection of information and files needed for someone else to replay the failure scenario in a controlled environment. For MySQL, a good packet separates data bugs, SQL bugs, transaction/concurrency bugs, execution plan regressions, driver bugs, and configuration mismatches. Once fixed, that same packet becomes the input for writing a regression test that keeps the bug from returning.

This lesson fits within mastering MySQL from table design, queries, indexes, and transactions to execution plan analysis, privilege management, and operational troubleshooting. The focus is turning a vague bug report into a repeatable test case with clear evaluation criteria.

## 1. What Questions Must Evidence Answer?

A useful bug report enables its recipient to answer:

1. **What happened?** Describe observed behavior, error message, `SQLSTATE`, MySQL error code, affected row counts, and timestamp.
2. **What should have happened?** State the specific business outcome or API contract, avoiding vague descriptions like "the data should be right."
3. **Where and on which versions?** Record server version, driver, framework, session configuration, schema, and deployment environment.
4. **How to reproduce it?** Provide fixtures, SQL statements, parameter types and values, operation ordering, transaction boundaries, and concurrency conditions.
5. **How reliably does it reproduce?** Note reproduction rate, wait times, triggering conditions, and attempts that did not fail.
6. **What proves it is fixed?** Include the previously failing reproduction test, post-fix regression test, data-integrity checks, and performance measurements when applicable.

Never combine expected and actual results into one sentence. Strong example: "When two requests order the same product with 1 unit remaining in stock, only one transaction commits; final inventory equals 0 and only one order succeeds." Weak example: "Sometimes inventory goes wrong."

## 2. Structure of an Evidence Packet

Organize the packet in a clean, transferable layout:

~~~text
mysql-bug-2026-014/
  README.md
  manifest.json
  environment/
    server-version.txt
    session-variables.txt
    schema.sql
    grants-redacted.sql
    application-dependencies.txt
  reproduction/
    setup.sql
    reproduce.sql
    parameters.txt
    expected-result.md
    actual-result.txt
    session-timeline.md
  diagnostics/
    explain.txt
    explain-analyze.txt
    processlist-redacted.txt
    innodb-status-redacted.txt
    relevant-log-excerpts.txt
  regression/
    test-case.md
    test-output.txt
~~~

Not every bug needs every file. Attach only relevant evidence, and note in `README` which parts do not apply and why. A small, clean, runnable packet is far more helpful than a directory stuffed with unguided giant logs.

`README` should document:

- Internal issue ID, impact severity, and investigation owner.
- Summary of reproduction conditions plus expected vs. actual outcomes.
- Versions and environment used during collection.
- Exact steps to run in order.
- How to reset data back to the initial state.
- Which files contained sensitive data that was sanitized or replaced.
- Latest run results and known limitations of the packet.

`manifest` can record file checksums to verify the packet wasn't altered during handoff between teams. Never put passwords, tokens, private keys, connection strings with secrets, or real personal data into manifests or logs.

## 3. Capturing MySQL and Application Fingerprints

Two environments both labeled "MySQL 8" can still differ in patch version, SQL mode, time zone, collation, optimizer settings, plugins, and schema. Capture the fingerprint from the exact instance and connection exhibiting the bug.

### 3.1. Server Version and Session Configuration

Run these queries on the relevant connection:

~~~sql
SELECT
  VERSION() AS server_version,
  @@version_comment AS distribution,
  @@hostname AS server_host,
  @@port AS server_port;

SELECT
  @@session.sql_mode AS sql_mode,
  @@session.time_zone AS session_time_zone,
  @@global.time_zone AS global_time_zone,
  @@session.transaction_isolation AS transaction_isolation,
  @@session.autocommit AS autocommit,
  @@character_set_connection AS character_set_connection,
  @@collation_connection AS collation_connection,
  @@character_set_results AS character_set_results;
~~~

Some variables or variable names differ across MySQL versions. If a query is incompatible, record the version first and adjust the list accordingly; do not skip capturing variables just because one variable name doesn't exist.

When the bug involves queries or performance, add relevant variables such as `optimizer_switch`, `optimizer_search_depth`, `innodb_flush_log_at_trx_commit`, `innodb_buffer_pool_size`, `innodb_lock_wait_timeout`, `max_connections`, and `binlog_format`. You do not need to dump thousands of unrelated variables; specify the selected set and why.

### 3.2. Schema, Indexes, and Privileges

Extract exact definitions of involved tables:

~~~sql
SHOW CREATE TABLE app_db.orders;
SHOW CREATE TABLE app_db.inventory;
SHOW INDEX FROM app_db.orders;
~~~

The schema must preserve data types, `NULL`/`NOT NULL`, defaults, collations, generated columns, partitions, foreign keys, check constraints, and indexes. Copying only partial DDL can omit the root cause, such as a unique index or collation causing two values to collide.

If the bug depends on privileges, record the connected account and effective grants in redacted form:

~~~sql
SELECT CURRENT_USER(), USER();
SHOW GRANTS;
~~~

`CURRENT_USER()` reports the MySQL account used for privilege checking; `USER()` shows the username and host provided by the client. The two can differ due to account-matching rules. Never export password hashes or authentication secrets.

### 3.3. Application and Driver Versions

Record the actual runtime versions of:

- Java runtime and JDK vendor.
- MySQL Connector/J and JDBC API.
- Spring Boot, Spring Framework, Hibernate/JPA, or MyBatis.
- HikariCP or other connection pool.
- Flyway/Liquibase and schema migration version.
- Container image, operating system, and process time zone.

Capture the dependency tree or packaged artifact list. Versions declared in build files can differ from runtime versions due to BOMs, transitive dependencies, or overrides. For bugs occurring only in the application, also save a redacted JDBC URL and relevant connection properties.

## 4. Reproducing with Minimal, Resettable Data

### 4.1. Building the Smallest Fixture That Preserves the Bug

A fixture is the schema and data needed to replay a scenario. Start from the failing dataset, then progressively strip unnecessary tables, columns, and rows until the minimal set still reproduces the exact failure. Minimization isolates the core condition and makes tests faster.

For example, a non-atomic inventory update bug may need only two tables:

The example uses a `CHECK` constraint enforced by MySQL starting in version 8.0.16. When testing on older versions, do not treat this constraint as proof that the server prevented negative values.

~~~sql
CREATE TABLE inventory (
  product_id BIGINT PRIMARY KEY,
  quantity INT NOT NULL,
  CONSTRAINT chk_quantity_nonnegative CHECK (quantity >= 0)
) ENGINE = InnoDB;

CREATE TABLE orders (
  order_id BIGINT PRIMARY KEY,
  product_id BIGINT NOT NULL,
  quantity INT NOT NULL,
  status VARCHAR(20) NOT NULL,
  CONSTRAINT fk_orders_inventory
    FOREIGN KEY (product_id) REFERENCES inventory(product_id)
) ENGINE = InnoDB;

INSERT INTO inventory (product_id, quantity)
VALUES (101, 1);
~~~

The fixture must contain enough data to trigger the failure condition. If the bug involves duplicate keys, preserve the unique index and two colliding values. If the bug involves the optimizer, the data must preserve realistic distributions and selectivity; a two-row table may fail to reproduce an execution plan seen on millions of rows.

### 4.2. Creating a Repeatable Initial State

The setup script must be re-runnable without prior runs polluting results. You can delete in foreign-key dependency order and re-insert fixtures inside a transaction, or create a fresh database/schema per run.

~~~sql
START TRANSACTION;

DELETE FROM orders WHERE product_id = 101;
DELETE FROM inventory WHERE product_id = 101;

INSERT INTO inventory (product_id, quantity)
VALUES (101, 1);

COMMIT;
~~~

In a test environment, resets must ensure no other worker or session writes to the fixture concurrently. Never run reset scripts on production. In automated tests, give each test uniquely keyed data or an isolated schema/database to prevent data races across tests.

### 4.3. Preserving Important Data Characteristics

Do not preserve row counts alone. Bugs can depend on:

- `NULL` ratios, duplicate rates, and column value distributions.
- Distribution skew, cardinality, and predicate selectivity.
- Unicode strings, collation, case, accents, or trailing spaces.
- Scaled `DECIMAL` values, negative numbers, `BIGINT` boundaries, and casts.
- Leap days, time zones, fractional seconds, or legacy zero dates.
- Foreign key relationships, insert order, and cascades.
- Rows per partition, index statistics, and historical data.

When using synthetic data instead of production data, preserve the failure-inducing characteristics while replacing real identities and sensitive values. Document how the data was generated so others can recreate the exact fixture.

## 5. Recording SQL, Bind Parameters, and Results

### 5.1. SQL Must Include Parameter Types and Values

A prepared statement is more than an SQL string with question marks. Record parameter positions, JDBC types, and sanitized values for every parameter. Example:

~~~sql
UPDATE inventory
SET quantity = quantity - ?
WHERE product_id = ?
  AND quantity >= ?;
~~~

| Position | JDBC type | Test value |
|---:|---|---:|
| 1 | `INTEGER` | `1` |
| 2 | `BIGINT` | `101` |
| 3 | `INTEGER` | `1` |

If a driver binds a parameter as `VARCHAR` instead of `BIGINT`, MySQL may perform different conversions, impacting index usage or comparison outcomes. Record how the application actually binds parameters, not just the raw SQL copied from logs.

Never casually substitute literals for parameters during reproduction. Literals can make the optimizer pick a different execution plan from a prepared statement or alter type inference.

### 5.2. Recording Expected and Actual Results

For each step, record:

- Returned row count.
- Relevant column values, including `NULL`s.
- Affected row count (`executeUpdate` or affected rows).
- `SQLSTATE`, vendor error code, and verbatim error message.
- Warnings if any, such as `SHOW WARNINGS` immediately after the statement.
- Execution duration and timeouts.
- Transaction state: active, committed, or rolled back.

Queries without `ORDER BY` have no guaranteed row order. If a bug involves ordering, add an explicit `ORDER BY` in the test matching the expected contract; never treat an accidental order from one execution plan as a stable guarantee.

For decimal values, compare using business precision/scale; never convert `DECIMAL` to `double` and assert exact equality. For timestamps, record session time zone and column precision.

## 6. Recording Transaction Boundaries and Concurrency

Many bugs emerge only when two or more transactions interleave. A single standalone SQL statement cannot reproduce lost updates, write skew, deadlocks, or dirty reads.

### 6.1. Recording the Full Session Sequence

For each session, record:

- Logical session name and connection/thread ID if available.
- Start/end timestamps of each statement.
- `START TRANSACTION`, `COMMIT`, `ROLLBACK`, and `autocommit` state.
- Isolation level.
- Data read before writing.
- Requested locks, lock waits, and received errors.

Example interleaved timeline for two sessions:

~~~text
Session A                         Session B
BEGIN                             BEGIN
SELECT quantity = 1               SELECT quantity = 1
UPDATE quantity = quantity - 1
                                  UPDATE quantity = quantity - 1
COMMIT                            COMMIT or error/rollback
~~~

This is only a timeline skeleton. A real packet must record exact timestamps and outcomes to show which session blocked, which committed, and which rolled back.

### 6.2. Recording Isolation Level and Autocommit

Capture:

~~~sql
SELECT
  @@session.transaction_isolation,
  @@session.autocommit,
  @@session.innodb_lock_wait_timeout;
~~~

Isolation level governs snapshots and locking behavior. `READ COMMITTED`, `REPEATABLE READ`, and `SERIALIZABLE` can yield different observed outcomes. `autocommit` also determines whether each statement is its own transaction or part of an application-managed transaction.

During reproduction, preserve the application's exact transaction boundaries. Running statements one by one in an SQL console with default autocommit may fail to reproduce bugs inside `@Transactional` or multi-statement JDBC transactions.

### 6.3. Collecting Lock and Deadlock Information

In MySQL 8, Performance Schema provides live lock data:

~~~sql
SELECT * FROM performance_schema.data_locks;
SELECT * FROM performance_schema.data_lock_waits;
~~~

These tables require Performance Schema enabled and appropriate read privileges; exact columns vary by version. For InnoDB deadlocks, capture:

~~~sql
SHOW ENGINE INNODB STATUS;
~~~

The `LATEST DETECTED DEADLOCK` section shows the participating transactions, indexes, and locks. Capture it promptly after the incident because "latest" is overwritten by subsequent deadlocks. For metadata lock issues, inspect `metadata_locks` in Performance Schema and the transactions holding the relevant DDL/DML.

Never write only "deadlock occurred." Save both contending statements, locked indexes/records, lock acquisition order, and which transaction was chosen as the victim. That evidence drives fixes to update ordering, shorter transactions, or safe retries.

## 7. Collecting Execution Plans and Performance Evidence

When bugs involve slow queries, timeouts, or load spikes, the packet must include SQL, parameters, schema, indexes, and execution plans. Saving only runtime screenshots does not reveal which access path the optimizer selected.

### 7.1. EXPLAIN and EXPLAIN ANALYZE

For read queries, capture the plan:

~~~sql
EXPLAIN FORMAT=TREE
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 9001
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 20;
~~~

Since MySQL 8.0.18, `EXPLAIN ANALYZE` executes the `SELECT` and reports actual timing, loop counts, and rows per iterator:

~~~sql
EXPLAIN ANALYZE
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 9001
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 20;
~~~

`EXPLAIN ANALYZE` actually executes the query. Use it only on safe read statements, in authorized environments, after evaluating cost. Never run it directly on statements with side effects or queries scanning massive tables on production during peak hours.

Record key signals:

- Access type and chosen index.
- Estimated rows vs. actual rows.
- Filters and conditions pushed down to the storage engine.
- Sorts, temporary tables, materialization, and join order.
- Iterators with abnormal timing or loop counts.
- Large discrepancies between estimates and actuals.

Plans can change across server versions, statistics, data sizes, parameter values, and cache state. When comparing two environments, use identical fixtures or representative data, identical parameter types, and identical execution methods.

### 7.2. Recording Statistics and Index Structure

The optimizer relies on statistics to estimate cardinality and choose plans. Capture:

~~~sql
SHOW INDEX FROM orders;
SHOW TABLE STATUS LIKE 'orders';
~~~

In MySQL 8, inspect histograms if the table has them:

~~~sql
SELECT *
FROM information_schema.column_statistics
WHERE schema_name = 'app_db'
  AND table_name = 'orders';
~~~

Do not run `ANALYZE TABLE` just to make the packet look "cleaner" before capturing baseline state. That command can refresh statistics and alter the plan; if measuring its impact, record the exact timestamp, command executed, and before/after plans.

### 7.3. Slow Query Log and Performance Schema

When privileges and configuration permit, extract slow query logs or Performance Schema digest statistics. Digests group structurally identical SQL queries even when parameter values differ. Record:

- Digest or sanitized SQL statement.
- Execution count and total time.
- Average, maximum, and percentile durations if collected.
- Rows examined, rows sent, and temporary tables.
- Collection timestamps, observation window, and slow query log settings.

Slow query logs may contain sensitive literals. Sanitize values before adding them to the packet. Never enable heavy logging or change global production settings without impact evaluation and formal approval.

## 8. Designing Regression Tests from Reproduced Bugs

A regression test must fail while the bug exists and pass once the fix is applied. If a test only exercises the new code path without reproducing the triggering failure condition, it can miss the original bug.

### 8.1. Choosing the Right Test Layer

| Test type | Used to verify | MySQL example |
|---|---|---|
| Unit test | Pure logic without database | Quantity math, rounding rules, or input validation |
| Repository/integration test | Real SQL, mappings, constraints, and transactions | Filtered queries, joins, generated keys, rollback |
| Migration test | Schema evolution across versions | Upgrading old schemas, checking post-migration indexes and data |
| Concurrency test | Multi-transaction interactions | Concurrent inventory decrement, preventing double booking |
| Performance test | Throughput, latency, and resources | Comparing plans and p95 after index changes |
| Security test | Privileges and data isolation | Read-only account cannot `INSERT`/`UPDATE` |

Bugs depending on MySQL behavior must have integration tests running against the target server series. H2 or mocked databases can assist with certain unit tests, yet they cannot replace MySQL when verifying dialects, collations, locking, `JSON`, indexes, or transaction semantics.

### 8.2. Writing Tests with Explicit Initial State and Outcomes

A repository test should:

1. Seed uniquely keyed fixtures.
2. Invoke the exact statement or service method that caused the bug.
3. Read back database state inside an appropriate transaction.
4. Assert business outcomes, affected rows, and constraints.
5. Clean up data or roll back per the test strategy.

Example testing a conditional update:

~~~java
@Test
void shouldNotDecreaseInventoryBelowZero() {
    inventoryRepository.insert(101L, 1);

    int firstUpdate = inventoryRepository.reserve(101L, 1);
    int secondUpdate = inventoryRepository.reserve(101L, 1);

    assertThat(firstUpdate).isEqualTo(1);
    assertThat(secondUpdate).isZero();
    assertThat(inventoryRepository.quantityOf(101L)).isZero();
}
~~~

This illustrative test assumes `reserve` executes an equivalent conditional `UPDATE`:

~~~sql
UPDATE inventory
SET quantity = quantity - ?
WHERE product_id = ?
  AND quantity >= ?;
~~~

Zero affected rows means no row satisfied the update condition. In real applications, distinguish nonexistent products from insufficient stock if the business contract requires separate error codes.

### 8.3. Testing Transaction Atomicity

When a business flow updates multiple tables, verify that a failure in a later step leaves no partially committed changes. For instance, creating an order and decrementing inventory must commit or roll back together in one transaction.

Verify:

- When all steps succeed, both changes persist.
- When the second step fails, the order is not partially saved.
- When the application throws an exception, the transaction manager rolls back per configured rules.
- No external side effects are emitted before transaction commit when atomicity is required.

### 8.4. Writing Synchronized Concurrency Tests

Concurrency tests must control the exact point where two transactions start together. Use `CountDownLatch`, `CyclicBarrier`, or equivalent synchronization primitives to enforce deterministic interleaving. Avoid using `Thread.sleep` as primary synchronization since execution speed varies with hardware and load.

For a last-seat reservation scenario, create a record with one remaining seat, launch two nearly simultaneous transactions, and verify:

- At most one transaction succeeds in booking.
- The other transaction receives an "out of stock" result or defined error.
- Final remaining count is non-negative.
- No two valid reservations exist for the same unique slot.

Run the test repeatedly using barriers and separate connections per worker. Record isolation level, autocommit, transaction boundaries, and deadlock/lock-timeout handling. Retries are only safe if the operation is idempotent or business keys prevent duplicate records.

## 9. Running Tests on Real MySQL in an Isolated Environment

### 9.1. Pinning the Server Version

Use a MySQL container or managed test instance to create an isolated environment. Pin the image to an approved patch tag or digest; never use `latest` because the same test could run on different server versions across builds.

The test environment should match factors affecting the bug:

- MySQL version and edition.
- SQL mode, time zone, charset, and collation.
- Storage engine, plugins, and transaction settings.
- Schema migrations and indexes.
- Authentication, TLS, and application privileges if relevant to the test.

Testcontainers is a strong choice for Java integration tests. The example below wires a container JDBC URL into Spring Boot; replace the image with the patch version or digest approved by your project:

~~~java
@Testcontainers
@SpringBootTest
class OrderRepositoryIT {

    @Container
    static final MySQLContainer<?> mysql =
        new MySQLContainer<>("mysql:8.4.4");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", mysql::getJdbcUrl);
        registry.add("spring.datasource.username", mysql::getUsername);
        registry.add("spring.datasource.password", mysql::getPassword);
    }
}
~~~

The example uses a specific tag for illustration. In practice, pick a supported patch tag/digest in your project and use the exact same image across CI and local reproduction. If the bug depends on production configuration, add the matching variables and initialization scripts.

### 9.2. Eliminating Order-Dependent Tests

Every test must create its own data and never depend on outcomes of earlier tests. Address:

- Unique keys and data so parallel tests do not collide.
- Data committed by tests that transaction rollback cannot undo.
- Unexpected mutations from Event Scheduler jobs, triggers, or background workers.
- Time zones, clocks, and current dates making tests sensitive to when they run.
- Unlogged random seeds preventing bug reproduction.
- Parallel tests sharing one database or schema.

If tests depend on time, inject `Clock` in the application to pin the instant. When testing MySQL's `NOW()`, record session time zone and use explicit test time windows; never assume JVM and server clocks match identically.

## 10. Evaluating Performance Regressions

A fix can produce correct results while making queries slower, holding extra locks, or opening more connections. For performance bugs, compare before-and-after baselines in equivalent environments.

Measurements to include:

| Metric | What to compare |
|---|---|
| Throughput | Successful transactions or queries per second |
| Latency | p50, p95, p99, and timeouts |
| Rows examined | Rows MySQL reads to satisfy the query |
| Rows sent | Rows returned to the client |
| Execution plan | Access paths, join order, sorts, temporary tables, and iterators |
| Locking | Lock waits, deadlocks, and transaction duration |
| Resources | CPU, memory, I/O, and connection counts |

Run identical data, identical parameters, identical load, and identical configuration. Run multiple iterations after warm-up, noting whether caches are warm or cold. Never compare single runs when system variance is high.

Set regression thresholds against SLOs and real baselines—for example, p95 does not regress beyond an agreed threshold while throughput holds steady or improves. Never use raw `EXPLAIN` text alone as the sole criterion: the optimizer may choose a different plan that actually runs faster on real data.

## 11. Classifying Bugs from Evidence

An evidence packet helps narrow down the root category:

| Symptom | Category to investigate | Next evidence needed |
|---|---|---|
| Wrong row results despite SQL succeeding | SQL logic or data | Fixtures, parameters, schema, expected/actual |
| Duplicate key or constraint violation | Schema and business rules | `SHOW CREATE TABLE`, indexes, transaction timeline |
| Bug appears only under concurrent requests | Concurrency/locking | Session timeline, isolation, `data_locks`, deadlocks |
| Query slows down after deploy | Optimizer/schema/config | `EXPLAIN`, statistics, SQL mode, version, and benchmarks |
| App fails while SQL console works | JDBC/ORM/pool/session | Bind types, driver version, connection properties, session variables |
| Only one account fails | Privileges/authentication | `CURRENT_USER`, `SHOW GRANTS`, plugins, and TLS |
| Passes alone yet fails in CI | Isolation/flaky test/environment | Seeds, time zone, shared DB, parallelism, and server image |
| Failure after migration | Schema evolution/data compatibility | Migration order, DDL, data conversion, and schema diff |

Never conclude a bug belongs to MySQL simply because a stack trace contains `SQLException`. An `SQLException` can come from the server, network, driver, pool timeout, or transaction manager. Use `SQLSTATE`, vendor error codes, nested causes, and failure timing to classify properly.

## 12. Protecting Data Inside Evidence Packets

Logs and reproduction datasets may contain personal information, payment details, tokens, or connection secrets. Before sharing:

- Replace names, emails, phone numbers, addresses, and identifiers with fake data.
- Strip passwords, tokens, private keys, cookies, and secrets from JDBC URLs.
- Never export password hashes from `mysql.user`.
- Preserve data types, lengths, distributions, relationships, and failure-triggering traits after anonymization.
- Restrict packet access and retention per organizational policy.
- Clearly note what data was altered so recipients do not mistake it for raw production data.

Never send a full production dump just because it reproduces the bug easily. When a large dataset is needed to test the optimizer, generate synthetic data with matching distributions and include the generation script.

## 13. Reproduction and Regression Checklist

### Before Reproducing

- [ ] Documented expected result and actual result separately.
- [ ] Recorded MySQL, driver, framework versions, and session config.
- [ ] Captured schema, indexes, privileges, and migration version.
- [ ] Created a minimal, anonymized, resettable fixture.
- [ ] Recorded SQL, bind parameter types, and parameter values.
- [ ] Recorded transaction boundaries, isolation, and autocommit.
- [ ] For concurrency bugs, recorded each session's timeline.
- [ ] For performance bugs, saved `EXPLAIN` and baseline measurements.

### After Fixing

- [ ] Re-ran the exact original reproduction test.
- [ ] Added a regression test at the right testing layer.
- [ ] Ran tests on the target MySQL version.
- [ ] Ran migration tests if the schema changed.
- [ ] Verified atomicity, constraints, and data after commit/rollback.
- [ ] Ran concurrency tests if the bug involved multiple transactions.
- [ ] Compared latency, throughput, and resources when performance is affected.
- [ ] Saved test output and updated the evidence packet manifest.

## 14. Practice Scenario

A sales API occasionally creates two successful orders even when only one unit of a product remains in stock. The team has only an "order created" log entry and a post-incident snapshot of the `inventory` table.

Assemble a reproduction packet:

1. Record MySQL version, engine, schema, indexes, SQL mode, isolation level, and autocommit.
2. Build a fixture with one product at `quantity = 1` and an `orders` table with production-like primary/foreign keys.
3. Capture the actual SQL reading inventory, creating orders, and decrementing stock; record bind parameters and transaction boundaries.
4. Stand up two sessions with separate connections, synchronized at start via a barrier to issue two concurrent requests.
5. Record the timeline of reads/writes/commits, affected rows, lock waits, and final results for both sessions.
6. Define the invariant: no negative quantity and at most one confirmed order per unit of inventory.
7. Build a regression test exercising both concurrent transactions; run it repeatedly on the target MySQL version.
8. After fixing, verify one transaction succeeds, the other is rejected or retried per rules, final data is accurate, and no unexpected deadlocks arise.

One valid fix is a conditional `UPDATE` checking affected rows within the same transaction that creates the order. If inventory decrement fails, the order must not commit. Tests must assert complete post-commit/rollback database state, not just HTTP status codes.

## 15. Self-Check Questions

1. What components does an evidence packet need so someone else can replay the bug?
2. Why must SQL be recorded alongside bind parameter types and values?
3. Why must the schema preserve indexes, constraints, collations, and storage engines?
4. What information belongs in the timeline of a deadlock or lost-update bug?
5. How does `EXPLAIN ANALYZE` differ from `EXPLAIN`, and what precautions apply when running it?
6. Why cannot H2 replace MySQL integration tests for locking or collation bugs?
7. How do you write a deterministic concurrency test without relying on `Thread.sleep`?
8. When must performance regression be evaluated beyond checking data correctness?
9. How do you anonymize a fixture while preserving the data traits that trigger the bug?
10. Why must a regression test fail before the fix and pass after the fix?

Good evidence turns an elusive bug into a scenario that can be replayed, observed, and verified. When a packet captures full environment fingerprints, schemas, fixtures, SQL, parameters, transaction timelines, and expected outcomes, the team can pinpoint the true root cause, write reliable regression tests, and evaluate a fix's impact before releasing.
