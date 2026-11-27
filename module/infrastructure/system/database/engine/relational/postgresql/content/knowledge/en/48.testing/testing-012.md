# Integrating Database Tests into CI and Managing Isolated Environments

The database is part of the application. Testing source code without verifying how the application works with PostgreSQL misses many bugs: migrations that fail to run, queries with wrong data types, constraints rejecting valid data, improper privileges, or transaction behavior differing from application assumptions. Integrating database checks into Continuous Integration (CI) catches these bugs as soon as changes are pushed to the repository.

For reliable results, every run requires a database environment that can be provisioned fresh, configured deterministically, populated with deterministic test data, and destroyed once finished. This lesson explains how to organize PostgreSQL testing layers in CI, build isolated environments, execute migrations, manage test data, support parallel execution, and collect diagnostics when tests fail.

## 1. Why Test PostgreSQL in CI?

Unit tests usually verify the logic of an isolated function or component. They are fast and easy to run, yet they cannot replace testing against real PostgreSQL. Many behaviors appear only when queries execute on the database:

- Data types, casts, `NULL`s, collations, and timezones can produce results different from application assumptions.
- Constraints, foreign keys, unique indexes, triggers, and defaults can reject or transform data.
- Migrations can fail when applied to a real schema or when upgrading from a prior version.
- Database roles and privileges on schemas, tables, sequences, or functions can differ from administrative account privileges.
- Transactions, locks, isolation levels, and concurrent queries can expose bugs that unit tests fail to simulate.
- Extensions or PostgreSQL-version-specific features may be absent in some developers' local environments.

CI provides a repeatable test run on every pull request or commit. Whenever a change breaks a migration, SQL query, constraint, or read/write flow, the pipeline catches it before merging to the main branch.

A solid pipeline must clearly define which configuration built the database, which schema state tests run against, and which dataset is used. Without controlling these factors, a passing test might merely reflect leftover data or state from an earlier run.

## 2. Testing Layers That Can Run in CI

Not every change requires running a massive integration suite. Tests can be layered by scope and cost so the pipeline gives fast feedback while still verifying critical behavior.

### 2.1. Migration testing

Create an empty database and apply all migrations from the start. This verifies that a fresh environment can be built accurately from the repository's migration history.

Beyond the empty-database path, also test upgrading from a prior-version schema. For example, build a database via migrations up to version N, load representative data, and then apply migration N+1. This catches errors that appear only when tables already hold rows, such as adding a `NOT NULL` column without a default or performing an incompatible data type conversion.

### 2.2. Query and repository testing

Run real queries on PostgreSQL to verify reads, writes, filtering, sorting, pagination, joins, aggregations, and `NULL` handling. Use small yet intentional datasets: boundary-timestamp rows, duplicates, missing relationships, empty strings, `NULL` values, and constraint-violation candidates.

These tests verify both SQL and data mapping between the application and database. They also expose discrepancies between PostgreSQL syntax/behavior and in-memory databases used in unit tests.

### 2.3. Constraint and transaction testing

Execute targeted write operations to verify unique constraints, foreign keys, check constraints, triggers, and rollback behavior. For example, when writing an order alongside its line items, an invalid line item must roll back the transaction so no partial order remains.

For multi-connection flows or concurrent processing, test across separate PostgreSQL connections. A single-connection test cannot faithfully simulate lock contention between transactions.

### 2.4. Integration and smoke testing

Integration tests launch the application or relevant components, connect to the prepared database, and execute a representative business flow. Smoke tests have a narrower scope: confirming the application connects, reads required config, and executes a basic query.

These tests run once the database is ready and migrations complete. They provide evidence that the application, connection configuration, privileges, and schema work together.

### 2.5. Bounded performance testing

You can include select critical queries in CI to catch major plan or timing regressions. However, shared CI runners experience variable load and resources. Use wide thresholds to catch severe regressions, capture `EXPLAIN` output when needed, and reserve precise benchmarking for environments with stable resources.

## 3. Designing an Isolated Database Environment

An **isolated environment** is a test environment whose data and schema state are independent of other runs. One job must never depend on data created by an earlier job, nor modify a team's shared database or production.

Several common isolation levels exist. The choice depends on startup time, CI resources, parallelism needs, and parity with deployment environments.

### 3.1. One PostgreSQL container per job

CI starts a dedicated PostgreSQL container for each job. When the job ends, the container is destroyed and its data vanishes if no persistent volume is attached.

Pros:

- Each job gets its own instance, easy to recreate and clean up.
- PostgreSQL version and startup settings can be pinned.
- Extensions, locales, and server parameters can be provisioned consistently.
- Multiple jobs can run in parallel without sharing data.

The drawback is time overhead for container startup and extension installation. If a suite runs multiple groups in parallel inside one job, assign a separate database or schema to each group to avoid collisions.

This is usually a strong choice for integration tests because the environment closely matches a real PostgreSQL server and starts fresh on every run.

### 3.2. One dedicated database per pipeline or worker

A single PostgreSQL instance can serve multiple test runs while each pipeline or worker gets its own database—for instance, **app_ci_1042** for pipeline 1042 and **app_ci_1043** for pipeline 1043.

This saves server startup time but requires managing database lifecycles. The pipeline creates the database before running, connects to that exact database, and drops it on completion. Dropping can fail if open connections linger, so close connection pools before cleanup.

Dedicated databases also allow testing database-scoped schemas or extensions. Remember that certain extensions must be installed individually per database.

### 3.3. One dedicated schema per worker

You can share one database and create per-worker schemas such as **ci_1042_worker_1**, **ci_1042_worker_2**. Each worker sets `search_path` to access its own schema.

This is lighter than spinning up multiple PostgreSQL instances or databases. However, all queries and migrations must respect the assigned schema. Hard-coded schema-qualified references, database-level extensions, or queries ignoring `search_path` can break isolation.

Do not rely on per-schema isolation alone if the application spans multiple schemas, creates unqualified objects improperly, or runs migrations altering shared objects. Verify how the application selects its schema per connection.

### 3.4. Transaction rollback per test

Some test suites open a transaction before each test and roll back afterward. This is fast because the database does not have to be rebuilt per case.

However, rollback reverts only changes inside that transaction on that single connection. If test code opens a second connection, spawns async work, or commits in another transaction, changes persist. Some database administration commands also cannot run inside a transaction.

Transaction rollback fits synchronous tests with controlled single-connection access. For multi-connection tests or tests creating databases/schemas, use dedicated databases/schemas or another cleanup strategy.

### 3.5. Comparing isolation approaches

| Isolation approach | Independence level | Startup cost | Key considerations |
|---|---|---|---|
| Dedicated container per job | High, both instance and data | Medium | Startup time and resource usage |
| Dedicated database on one instance | High at database level | Low to medium | Create/drop privileges and dangling connections |
| Dedicated schema per worker | Medium | Low | `search_path`, shared objects, and migrations |
| Transaction rollback | Connection/transaction scoped | Very low | Does not cover committed changes or other connections |

When CI runs independent jobs, a dedicated container is usually the simplest and safest option. To cut startup overhead, a dedicated database per worker on a shared instance offers a balanced trade-off. Dedicated schemas and transaction rollbacks fit suites engineered to respect those isolation boundaries.

## 4. Creating Reproducible PostgreSQL Containers

Docker Compose is a convenient way to run PostgreSQL locally or in CI jobs. The file below defines a test database:

~~~yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: app_test
      POSTGRES_USER: app_test_user
      POSTGRES_PASSWORD: ci_only_password
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app_test_user -d app_test"]
      interval: 2s
      timeout: 3s
      retries: 20
    tmpfs:
      - /var/lib/postgresql/data
~~~

Here, `tmpfs` stores PostgreSQL data in ephemeral container memory. When the container stops, the data disappears. If CI does not support `tmpfs` or standard volumes are needed, use a disposable container and remove its volume after the job.

Start the database:

~~~bash
docker compose up -d postgres
~~~

Check status:

~~~bash
docker compose ps
docker compose exec postgres pg_isready -U app_test_user -d app_test
~~~

When finished:

~~~bash
docker compose down -v
~~~

The final command removes the container and Compose-managed volumes for that project. Use it only in dedicated test environments; never run it on a Compose project holding data you want to keep.

### 4.1. Health checks and readiness

A running container does not mean PostgreSQL is ready to accept queries. PostgreSQL needs time to initialize the cluster, read config, and start listening.

**pg_isready** checks whether the server accepts connections. A Compose healthcheck lets dependent services wait until the database reports healthy.

Even so, `pg_isready` does not verify that migrations ran, extensions exist, or application accounts hold the right privileges. The pipeline needs a separate step to run migrations, optionally followed by a smoke test query.

### 4.2. Pinning versions and configuration

Never use the **latest** tag for database images in CI. Pick a specific PostgreSQL version, such as **postgres:16**, and update intentionally when upgrading. For stricter reproducibility, pin the image digest.

Beyond the version, standardize all factors affecting outcomes:

- Installed extensions and extension versions.
- Encoding, locale, collation, and timezone.
- Server parameters required by the application.
- Created roles and privileges.
- Executed init scripts and migrations.

If production uses extensions like `pgcrypto`, `uuid-ossp`, `PostGIS`, or internal extensions, CI must install matching extensions. Base PostgreSQL images do not necessarily include every extension an application uses.

## 5. Organizing Database Test Steps in a Pipeline

A pipeline can be divided into clear stages:

1. Check out source code and install required tools.
2. Start PostgreSQL or provision an isolated database.
3. Wait until the database is ready.
4. Create required application roles and settings.
5. Run migrations.
6. Load fixtures or test data.
7. Run query, repository, and integration tests.
8. Collect logs on failure.
9. Close connections and destroy the temporary environment.

This ordering prevents tests from starting before the database is ready or before the schema reaches the right version.

### 5.1. GitHub Actions example with a PostgreSQL service

The example below illustrates a CI job with a PostgreSQL service. Replace migration and test commands with your repository's real scripts:

~~~yaml
name: database-tests

on:
  pull_request:
  push:
    branches: [main]

jobs:
  integration:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: app_test
          POSTGRES_USER: ci_admin
          POSTGRES_PASSWORD: ci_admin_password
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U ci_admin -d app_test"
          --health-interval 2s
          --health-timeout 3s
          --health-retries 20

    env:
      PGHOST: 127.0.0.1
      PGPORT: 5432
      PGDATABASE: app_test
      PGUSER: ci_admin
      PGPASSWORD: ci_admin_password

    steps:
      - uses: actions/checkout@v4

      - name: Wait for PostgreSQL
        run: |
          for attempt in $(seq 1 30); do
            if pg_isready -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE"; then
              exit 0
            fi
            sleep 2
          done
          echo "PostgreSQL did not become ready"
          exit 1

      - name: Apply migrations
        run: ./scripts/migrate-test.sh

      - name: Run database integration tests
        run: ./scripts/test-database.sh
~~~

In GitHub Actions, the service container is provisioned for the job and reachable over the mapped port. If the job itself runs inside a container, hostnames and ports may differ; use the service hostname per workflow configuration rather than assuming `127.0.0.1`.

Passwords in the example are strictly for ephemeral CI databases. For shared services or external resources, pull secrets from the CI secret store and grant least privilege. Never commit real passwords into repositories or logs.

### 5.2. Creating an application role with least privilege

Use a separate admin role to create schemas and run migrations, then run integration tests under an application role holding only required privileges. This catches code accidentally relying on superuser privileges.

Illustrative application role creation:

~~~sql
CREATE ROLE app_runtime LOGIN PASSWORD 'runtime_test_password';

GRANT CONNECT ON DATABASE app_test TO app_runtime;
GRANT USAGE ON SCHEMA public TO app_runtime;

GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES IN SCHEMA public
TO app_runtime;

GRANT USAGE, SELECT, UPDATE
ON ALL SEQUENCES IN SCHEMA public
TO app_runtime;
~~~

Those grants apply only to existing objects. To automatically grant privileges on tables and sequences created later, configure default privileges as the role owning the objects:

~~~sql
ALTER DEFAULT PRIVILEGES FOR ROLE migration_owner
IN SCHEMA public
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_runtime;

ALTER DEFAULT PRIVILEGES FOR ROLE migration_owner
IN SCHEMA public
GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO app_runtime;
~~~

If the application calls functions or uses additional schemas, grant matching privileges. Never grant superuser to the runtime role just to make tests pass.

## 6. Running and Controlling Database Migrations

Migrations evolve schemas across versions. CI should execute the exact migration tool and workflow used during deployment so the real schema path is tested.

A common flow creates an empty database, applies all migrations in order, checks the schema, runs tests on the new schema, and also builds a prior-version database with representative data to test the upgrade migration.

Example running a SQL migration file with `psql`:

~~~bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/001_create_schema.sql
~~~

`ON_ERROR_STOP` tells `psql` to stop on SQL errors so the job fails instead of continuing with a half-applied schema. If your project uses Flyway, Liquibase, or another migration tool, invoke that tool's official migration command.

### 6.1. Testing fresh databases vs. upgrade databases

These two paths catch different classes of bugs:

- **Fresh install:** verifies the full migration history can build a new database from scratch.
- **Upgrade path:** verifies new migrations can transform an existing schema and existing data.

For example, adding a `NOT NULL` `status` column succeeds on an empty table yet fails when the table already has rows. You need a strategy to add the column, backfill existing rows, and only then enforce `NOT NULL`.

Large changes often require multiple phases to stay compatible with running application versions: add the new column, dual-write or backfill, switch the application to the new column, and drop the old column in a later release. CI can verify each phase so migrations do not break live applications.

### 6.2. Migrations must be ordered and locked

Never let multiple jobs run migrations concurrently against a shared database. Two processes may attempt to create the same object or update the migration history table simultaneously, causing errors or inconsistent states.

Giving each job its own database avoids conflicts cleanly. When sharing a database, the migration tool needs locking or a history table so only one process alters the schema at a time. Never force an already-applied migration to re-run by bypassing history.

### 6.3. Non-transactional migrations

Many PostgreSQL DDL statements run inside transactions, yet some operations cannot execute inside a transaction block—such as **CREATE INDEX CONCURRENTLY**. The migration tool must support flagging non-transactional migrations or running them appropriately.

CI must run migrations via the real deployment tool to expose this constraint. Wrapping every migration inside a transaction in a test script can yield behavior different from deployment.

### 6.4. Handling migration failures

When a migration fails, save full logs, the migration name, `SQLSTATE`, and database state. If the migration ran inside a transaction and rolled back cleanly, fix the migration and re-run on a fresh database. If it contained non-transactional steps or partial commits, recreate the test environment and verify state before continuing.

Never patch the schema manually just to turn tests green. Every change must live in migrations so other environments reproduce the exact same state.

## 7. Managing Test Data

An isolated environment only prevents runs from interfering with one another. Test data still needs explicit, repeatable preparation.

### 7.1. Fixtures and seed data

Fixtures are fixed datasets loaded prior to tests. Seed data typically creates baseline records shared across tests. Fixtures can live in SQL, CSV, JSON, or code factories.

Data should be small, clear, and tailored to specific scenarios. For instance, to test orders, create one customer with two orders—one paid and one pending. Tests assert totals, statuses, and relationships without relying on rows created by other tests.

Avoid real production data. When realistic structures are needed, generate synthetic data or use data anonymized through an approved process. Never commit personal information or credentials into repository fixtures.

### 7.2. Data must make results deterministic

Reliable tests know their exact inputs and expected outputs. Avoid relying on row ordering when queries lack `ORDER BY`. Avoid using current wall-clock time directly when tests expect fixed results; pass explicit timestamps or freeze the application clock.

Example:

~~~sql
INSERT INTO customers (customer_id, name)
VALUES
  (101, 'An'),
  (102, 'Binh');

INSERT INTO orders (order_id, customer_id, total, status)
VALUES
  (1001, 101, 150.00, 'paid'),
  (1002, 101, 50.00, 'pending'),
  (1003, 102, 75.00, 'paid');
~~~

Paid revenue aggregation query:

~~~sql
SELECT customer_id, sum(total) AS paid_total
FROM orders
WHERE status = 'paid'
GROUP BY customer_id
ORDER BY customer_id;
~~~

Expected results are `150.00` for customer `101` and `75.00` for customer `102`. Because data is created directly inside the test environment, tests do not depend on prior run state.

### 7.3. Cleaning up data after tests

Several cleanup options exist:

- Transaction rollback if all changes stay in one transaction on one connection.
- Deleting created rows by a test-specific identifier key.
- `TRUNCATE` tables in the test schema before loading fixtures.
- Dropping the database or schema once the worker finishes.

Example:

~~~sql
TRUNCATE TABLE orders, customers RESTART IDENTITY CASCADE;
~~~

`CASCADE` can affect tables referencing the named tables, so use it only inside isolated test schemas or databases. `RESTART IDENTITY` resets sequences owned by the truncated tables; omit it if sequence resets are unnecessary.

Design cleanup so a test failing midway never corrupts subsequent runs. With disposable containers or databases, destroying the entire environment after the job is usually simple and reliable.

## 8. Running Parallel Tests Without Collisions

CI often runs multiple jobs or test workers concurrently to shorten execution time. If all workers share one schema and identical fixture keys, they can overwrite or delete each other's data.

Partitioning options include:

- **Database per pipeline:** each pipeline receives its own database.
- **Schema per worker:** each worker gets its own schema and `search_path`.
- **Unique data keys:** every test record carries a unique namespace or identifier.
- **Container per job:** each job gets its own PostgreSQL instance.

Example creating a per-pipeline, per-worker schema:

~~~sql
CREATE SCHEMA ci_1042_worker_3;
~~~

Point the worker to the schema:

~~~sql
SET search_path TO ci_1042_worker_3, public;
~~~

Ensure the application opens connections with that `search_path` and migrations run inside that schema. If tests hard-code schema names like `public.orders`, `search_path` cannot isolate those queries.

Never let two workers concurrently run migrations or `TRUNCATE` a shared table. When parallel tests require large baseline datasets, you can migrate a template database and clone per-worker databases if infrastructure and privileges allow, factoring in storage and clone time.

## 9. Using Testcontainers to Manage PostgreSQL Lifecycles

In Java projects, Testcontainers can launch a PostgreSQL container directly inside the test suite. Tests obtain the JDBC URL, username, and password from the running container, run migrations, and connect the application to that database.

Example with JUnit and Testcontainers:

~~~java
@Testcontainers
class OrderRepositoryIT {
    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16")
            .withDatabaseName("app_test")
            .withUsername("test_user")
            .withPassword("test_password");

    @BeforeAll
    static void configureDatabase() {
        System.setProperty("test.jdbc.url", postgres.getJdbcUrl());
        System.setProperty("test.jdbc.user", postgres.getUsername());
        System.setProperty("test.jdbc.password", postgres.getPassword());
    }

    @Test
    void readsOrdersFromPostgres() {
        // Apply migrations, insert fixture, and run assertions.
    }
}
~~~

This condensed example illustrates container lifecycle; real projects declare compatible Testcontainers dependencies, configure JUnit integration, and wire properties into the actual datasource. In Spring or other frameworks, use dynamic property mechanisms rather than system properties.

A container can be shared across a test class or suite to cut startup time. If tests run in parallel and mutate shared data, give each worker its own database/schema or disable parallelism for stateful groups.

A major benefit of Testcontainers is running tests against real PostgreSQL at the declared version. This reduces discrepancies between developer laptops and CI, particularly for PostgreSQL-specific SQL, extensions, indexes, transactions, and data types.

## 10. Collecting Logs and Diagnostics When CI Fails

A job reporting merely "database tests failed" is hard to debug. On failure, pipelines should capture enough evidence to pinpoint the phase and root cause:

- PostgreSQL startup logs and health check status.
- Server version, extensions, and relevant configuration.
- Migration logs, including the last successfully applied migration name.
- `SQLSTATE`, error messages, and relevant queries where safe to log.
- Test output and failing test names.
- `EXPLAIN` or `EXPLAIN ANALYZE` output for selected performance queries.
- Application logs and sanitized connection details with credentials stripped.

Inspect container logs via:

~~~bash
docker compose logs --no-color postgres
~~~

Or query version and extension details:

~~~sql
SELECT version();

SELECT extname, extversion
FROM pg_extension
ORDER BY extname;
~~~

Never enable unrestricted logging of full statements or bind parameters if they can contain passwords, tokens, or personal data. CI logs are often accessible across the organization; limit sensitive content and retention.

When tests fail intermittently, check causes such as shared data, test execution order, insufficient timeouts, unclosed connection pools, uncommitted/unrolled-back transactions, or system-clock dependencies. Re-running once can help gather extra diagnostics, but never treat retries as a fix for the underlying bug.

## 11. Common Design Mistakes

| Symptom | Common cause | Resolution |
|---|---|---|
| Passes locally, fails in CI | Different PostgreSQL version, extensions, or locale | Pin images and environment configuration |
| Migration fails only when DB has data | Tested only fresh installs | Add upgrade tests from a prior version |
| Order-dependent tests | Leftover data or shared state | Explicit fixtures and post-test cleanup |
| Parallel tests fail intermittently | Multiple workers mutating the same table/schema | Dedicated database or schema per worker |
| Container running, app fails to connect | PostgreSQL not ready or wrong host/port | Health checks and connection verification |
| Tests pass despite missing app privileges | Running all tests as superuser | Run under a least-privilege runtime role |
| Test rolls back yet data persists | Writes committed on another connection | Control connections or destroy environment |
| CI is slow and resource-heavy | Launching an instance per tiny test | Share container per suite, isolate DB/schema per worker |

Other practices that produce misleading results:

- Sharing a persistent development database for CI makes state across runs unpredictable.
- Running tests against manually created schemas while skipping migrations.
- Running migrations as admin and then running the app under that same admin role, hiding missing privileges.
- Using live production data directly as fixtures.
- Using the `latest` image tag, causing the same commit to run on different PostgreSQL versions at different times.
- Running `TRUNCATE` on a shared database without strict scope control.
- Discarding logs on job failure, making it impossible to tell whether failure occurred in startup, migrations, connections, or queries.

## 12. Organizing Pipelines by Cost and Reliability

Run fast checks early and resource-heavy checks later:

| Stage | Contents | Appropriate trigger |
|---|---|---|
| Fast checks | Migration syntax checks, SQL lint, and unit tests | Every commit |
| Core database | Provision PostgreSQL, migrate from scratch, verify constraints | Every pull request |
| Integration | Repositories, transactions, privileges, and app flows | Every pull request or main branch |
| Upgrade | Upgrade from prior-version schema with representative data | Pull requests with migrations and scheduled runs |
| Performance | Benchmark critical queries and inspect plans | Main branch or dedicated pipeline |

Not every repository needs exactly five separate jobs. What matters is preserving the boundary between fast checks and integration checks while ensuring every job runs against a deterministic database environment.

When a change affects only one module, run the relevant test group first for quick feedback. However, shared migrations or core data type changes still require full integration coverage because impacts can ripple across components.

## 13. Principles for Maintaining Test Environments

Treat CI database environments as code. Store Compose files, workflows, migration scripts, fixtures, and extension configs in the repository or a versioned config store so anyone can reproduce the exact environment.

Give every run a clean lifecycle: provision fresh, verify readiness, run migrations, load data, execute tests, archive diagnostics, and destroy temporary resources. Never let one pipeline's state become an implicit input to the next.

Pin PostgreSQL and migration tool versions, align extensions with target environments, test both fresh databases and upgrades, and run tests under roles matching production application privileges. When tests run in parallel, give every worker strict data boundaries. Following these rules catches database bugs early in CI and keeps results reproducible across developer machines, CI, and deployment environments.
