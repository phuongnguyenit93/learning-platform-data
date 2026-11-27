# Distinguishing Learning, Testing, and Production Environments When Installing PostgreSQL

The exact same `CREATE TABLE` statement can run on a personal laptop, inside a testing pipeline, or on a server serving thousands of users. Yet **the safety of an operation depends on the environment you are connected to**, not on how simple the statement looks. Dropping and recreating a practice database is routine; doing the same to a production database can cause severe downtime or unrecoverable point-in-time data loss.

When learning how to install PostgreSQL, the goal is not merely getting a server started. Learners must clearly distinguish:

- **Local learning/development environment** (*local learning/development*): where you test syntax and build features.
- **Automated testing environment** (*test/CI*): where data can be recreated deterministically to verify behavior.
- **Integration/pre-production environment** (*integration/staging/pre-production*): where components are tested together under production-like configuration.
- **Production environment** (*production*): where live data, service-level commitments, security, and recoverability are top priorities.

This lesson presents an environment-separation model, PostgreSQL setup examples for learning and testing, verification steps to confirm which target you are connected to, rules for managing data and credentials, and prerequisites before promoting a change to production. Examples serve as practical guides for modern PostgreSQL; always cross-check exact versions, OS, and infrastructure before applying.

## 1. Why Distinguish Environments Right From Installation?

Imagine a developer testing user registration. To reset sample data, they run this SQL snippet:

~~~sql
TRUNCATE TABLE app.users RESTART IDENTITY CASCADE;
~~~

In a **dedicated test database**, this statement can be part of normal test cleanup. However, if the connection string accidentally points to production, it wipes massive numbers of rows and dependent tables via `CASCADE`. PostgreSQL has no idea "the author intended this as a test" simply because the client is a laptop.

Separating environments mitigates major risks:

1. **Data loss:** test or seed commands destroy live data.
2. **Data exposure:** production copies containing emails, phone numbers, API keys, or personal data end up on insufficiently secured learning machines.
3. **Configuration drift:** queries succeed locally but fail in production due to differences in versions, extensions, privileges, or timeouts.
4. **Misleading performance:** testing on 20 rows reveals nothing about table scans or lock contention across millions of rows.
5. **Security exposure:** using the high-privilege `postgres` account for both applications and learners.
6. **Non-reproducibility:** every machine creates tables manually in different ways, causing bugs that appear in only one environment.
7. **Difficult recovery:** lacking verified backups or not knowing when to use rollback, restore, or failover.

Therefore, **an environment is not just a database name**. It is the combination of infrastructure, data, authorized users, privileges, configuration, deployment processes, safeguards, monitoring, and availability targets.

## 2. Quick Comparison of Environment Types

| Criterion | Learning / Local | Automated Test / CI | Staging / Pre-Production | Production |
| --- | --- | --- | --- | --- |
| Primary goal | Learn SQL, try features, debug | Verify code and repeatable migrations | Rehearse integration and releases | Serve real business traffic |
| Data | Synthetic, small, disposable | Auto-seeded, isolated per test | Representative structure/volume; anonymized if derived from real data | Official business data |
| Provisioning | Local PostgreSQL, container, lab instance | Ephemeral DB/container per job or suite | Dedicated managed instance, matching production config as closely as possible | Instance/cluster administered per operational requirements |
| Privileges | Learner may have table creation rights in lab | Test role scoped strictly to test DB | Production-like roles, migration role separated | Strict least privilege, access auditing |
| Data reproducibility | Can reset intentionally | Preferably automated and idempotent | Planned resets, never ad-hoc across shared teams | Never reset via test scripts |
| Backups | Depends on value of study data | Usually unnecessary per run if reproducible | Needed for valuable configs/data and restore drills | Mandatory per RPO/RTO, with restore tests |
| Monitoring | Logs and basic tools | Test results, container logs | Metrics, traces, logs to catch issues pre-release | Alerts, SLOs, incident response, and runbooks |
| Network security | Loopback/local only when possible | Isolated CI network | Restricted access matching production | Private network, TLS, strict authentication policies |
| Incident impact | Usually affects one learner | Affects pipeline | Affects testing/deployment rehearsals | Affects customers, revenue, and live data |

This is a **target model**; not every organization starts with all four tiers on day one. A small project might begin with local + test + production, yet **production must never serve as a destructive testing ground**. As team size, integrations, and risk grow, a dedicated staging tier becomes essential.

### 2.1. Release Flow Diagram

~~~mermaid
flowchart LR
    L["Local<br/>test SQL and code"] --> T["Test/CI<br/>ephemeral DB and tests"]
    T --> S["Staging<br/>integration checks"]
    S --> P["Production<br/>controlled rollout"]
    M["Migrations in Git"] --> T
    M --> S
    M --> P
    D["Synthetic / anonymized data"] --> L
    D --> T
    D --> S
    P -. "never copy sensitive data directly" .-> D
~~~

A key aspect of this model: **the exact same migration set is tested and promoted through each environment**, rather than hand-editing one table locally, another in staging, and a third variant in production.

## 3. Database, Schema, and PostgreSQL Cluster: Different Isolation Levels

In PostgreSQL, these units are not interchangeable:

| Unit | Meaning | Isolation Level |
| --- | --- | --- |
| **Schema** | Namespace like `public`, `sales` inside one database | Separates object names/privileges; **still shares the same database** |
| **Database** | Named data container a client connects to, such as `shop_dev` | Separates tables/schemas within one PostgreSQL instance; **still shares instance resources** |
| **PostgreSQL instance/cluster** | Single PostgreSQL server managing multiple databases and shared structures/settings | Shares processes, WAL, memory, instance config, and system resources |
| **Separate VM/container/managed deployment** | Infrastructure-level deployment and administrative boundary | Strong isolation when network, storage, identity, and privileges are separated |

For instance, placing `shop_dev` and `shop_prod` as two databases inside one instance reduces accidental table-name collisions, yet **provides incomplete isolation**:

- Both share server CPU, RAM, I/O, disk, and connection limits.
- A single superuser account can affect both.
- An instance crash or full disk impacts both.
- Settings like `shared_buffers`, `max_connections`, and `wal_level` are instance-wide, not per database.

Consequently, **production** should have clear infrastructure and privilege boundaries separating it from learning/test environments. For single-machine learning, hosting multiple databases in one instance remains handy as long as you understand its isolation limits.

## 4. Learning Stage: Installing PostgreSQL to Practice SQL Safely

Several valid options exist:

1. **Direct local install** on your personal machine: ideal for learning services, config files, `psql`, OS permissions, and basic operations.
2. **Running PostgreSQL in a container**: convenient for creating/removing isolated labs, pinning versions, and rebuilding quickly.
3. **Cloud lab instance**: useful for practicing remote connectivity, TLS, and managed service operations, though incurring cost and requiring network controls.

For beginners, local containers minimize host-system modifications. Still, containers **are not automatically secure**: publishing ports on all interfaces, using weak passwords on shared networks, or mounting a production volume still poses real risks.

### 4.1. Example: Running a PostgreSQL Lab with Docker

This example is **strictly for local learning on your own machine** with an explicitly pinned image version:

~~~bash
docker run --name pg-learning-41 \
  -e POSTGRES_USER=lab_admin \
  -e POSTGRES_PASSWORD=lab-only-change-me \
  -e POSTGRES_DB=learning_db \
  -p 127.0.0.1:5541:5432 \
  -v pg-learning-41-data:/var/lib/postgresql/data \
  -d postgres:17
~~~

This uses Bash-style line continuation; in PowerShell/Windows, write it on a single line or use compatible line continuation syntax. Run it only when Docker is installed and no container/volume with those names already exists.

Explanation:

- `postgres:17` pins the major version branch in this example, avoiding unexpected major jumps from `latest`. When strict reproducibility is required, pin patch versions or digests per image policy.
- `POSTGRES_DB=learning_db` creates the initial database when the **data directory is empty**.
- `-p 127.0.0.1:5541:5432` binds the port strictly to host loopback, avoiding accidental network exposure.
- `pg-learning-41-data` is a persistent Docker volume: deleting the container **does not automatically delete the volume**; great for learning, though important to remember when resetting.
- Password `lab-only-change-me` is an **illustrative placeholder, never for real services**, and passing secrets via environment variables/CLI can be visible to tools or host administrators. Production requires a proper secret manager/secure injection mechanism.

Test connecting directly inside the container:

~~~bash
docker exec -it pg-learning-41 \
  psql -U lab_admin -d learning_db
~~~

Or from the host if `psql` is installed:

~~~bash
psql -h 127.0.0.1 -p 5541 -U lab_admin -d learning_db
~~~

You do not need OS root privileges to learn SQL syntax; the privileged `lab_admin` role in this **lab instance** must stay confined here and never be reused in production.

### 4.2. Verifying the Right Server and Database After Connecting

Inside `psql`:

~~~sql
SELECT
    current_database() AS database_name,
    current_user AS connected_role,
    current_setting('server_version') AS postgres_version,
    current_setting('port') AS server_port,
    current_setting('TimeZone') AS session_timezone;
~~~

And meta-commands:

~~~text
\conninfo
\l
\dn
~~~

`\conninfo` displays current connection details; `\l` lists databases; `\dn` lists schemas visible to your role. Commands starting with `\` are **`psql` meta-commands**, not SQL statements sent verbatim over JDBC.

When connecting through a proxy or load balancer, the host/port seen by the client may differ from the actual backend database address. To confirm the target database, combine connection profiles, infrastructure checks, user identity, TLS verification, and metadata queries rather than trusting a prompt label alone.

### 4.3. Creating a Practice Schema

~~~sql
CREATE SCHEMA IF NOT EXISTS sandbox;

CREATE TABLE IF NOT EXISTS sandbox.notes (
    note_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT notes_title_nonblank
        CHECK (length(btrim(title)) > 0)
);

INSERT INTO sandbox.notes (title)
VALUES ('Learn PostgreSQL in an isolated environment');

SELECT note_id, title, created_at
FROM sandbox.notes
ORDER BY note_id;
~~~

These steps **actually write data to the learning database**. `CREATE TABLE IF NOT EXISTS` does not verify that an existing table matches your intended structure; when managing real applications with migrations, use version-controlled migrations rather than ignoring name collisions.

### 4.4. Cleaning Up the Lab Safely Within Scope

To stop the container while keeping data:

~~~bash
docker stop pg-learning-41
~~~

To start it again:

~~~bash
docker start pg-learning-41
~~~

If you intentionally want to remove the **lab container**:

~~~bash
docker rm -f pg-learning-41
~~~

This does not automatically delete the named volume `pg-learning-41-data`. **The following volume-removal command wipes all PostgreSQL data inside that lab volume**; run it only after confirming it is strictly a test volume with no data you want to keep:

~~~bash
docker volume rm pg-learning-41-data
~~~

Never run these container/volume commands on someone else's system or production infrastructure. Important data must have backups and verified recovery procedures prior to deletion.

## 5. Automated Testing: Databases Must Be Reproducible and Isolated

A **test** environment is not merely "a dev database with a few extra rows." Effective tests need to:

- Produce deterministic input data.
- Assert expected pass/fail conditions per design.
- Re-run repeatedly without depending on leftover data from prior runs.
- Never write to production or another teammate's database.
- Clean up resources after tests, or isolate environment lifecycles when debugging failures.

Consider an e-commerce system with `customers` and `orders` tables. When testing integrity rules, use transactions and rollbacks inside a **dedicated test database**:

~~~sql
BEGIN;

CREATE TEMP TABLE test_customers (
    customer_id BIGINT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE
);

INSERT INTO test_customers (customer_id, email)
VALUES (1, 'demo@example.test');

SELECT count(*) AS expected_one
FROM test_customers;

ROLLBACK;
~~~

Here `CREATE TEMP TABLE` creates a session-scoped temporary table, and `ROLLBACK` undoes transaction changes. This demonstrates isolated experimentation; for integration tests validating constraints against the **application's real schema**, run actual migrations on a dedicated test database and load fixtures rather than substituting hand-crafted temp tables.

### 5.1. Creating a Dedicated Test Database Per Job

In CI, a common pattern is:

~~~text
CI job A -> PostgreSQL service A -> database test_a -> schema migration -> fixtures -> tests -> cleanup
CI job B -> PostgreSQL service B -> database test_b -> schema migration -> fixtures -> tests -> cleanup
~~~

Two jobs never share a writable database. Even when each job uses an ephemeral container/instance, `DROP DATABASE` should only target **resources owned by that specific job** with verified identity.

If CI cannot spin up a fresh container per run, enforce unique database naming conventions, test-scoped privileges, audited cleanup, and resource caps. Never give test jobs credentials capable of dropping other databases on the same server.

### 5.2. Test Data Strategies

| Preparation Approach | When to Use | Considerations |
| --- | --- | --- |
| **Fixed seed** | Verifying core logic and clear expected outputs | Easy to reproduce; small volume |
| **Data factory** | Many input/relationship permutations | Must satisfy constraints and clean up per test |
| **Property-based testing** | Exploring edge cases | Log random seeds to reproduce failures |
| **Anonymized production-like data** | Integration, analytics, performance checks | Requires strict sensitive-data policies |
| **High-volume snapshot** | Testing migrations and query plans | Resource-intensive; verify schema/version alignment |

Avoid taking a snapshot with unmasked personal data to "test like production" on an unsecured laptop or runner. Fields like emails, phone numbers, addresses, login keys, tokens, and payment records require strict minimization/anonymization policies. **Renaming a dump file is not anonymization.**

### 5.3. Limitations of Per-Test Transaction Rollback

Many frameworks wrap each test in a transaction and roll back after assertions finish. While useful, this cannot test everything:

1. **Sequences/identities** do not roll back like table rows: issued sequence numbers do not rewind, so never expect IDs to reset to 1 on every test.
2. Tests using **multiple connections** do not share one transaction; uncommitted changes on connection A are invisible to connection B.
3. An outer test transaction can **mask commit-time bugs** because real application code never commits during the test.
4. External side effects such as message queues, files, or HTTP calls do not roll back with PostgreSQL.
5. Any SQL error inside a transaction puts PostgreSQL into an aborted state; continuing requires a rollback or an explicit savepoint.

Therefore, combine unit tests, real PostgreSQL integration tests, true commit/rollback tests, and concurrency tests matching business scope.

### 5.4. Example: Testing Constraints Inside a Test

~~~sql
BEGIN;

CREATE TEMP TABLE test_products (
    product_id BIGINT PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    price NUMERIC(12, 2) NOT NULL CHECK (price > 0)
);

INSERT INTO test_products (product_id, sku, price)
VALUES (1, 'SKU-001', 120000.00);

SAVEPOINT before_invalid_insert;

-- Intentional error: unique_violation, SQLSTATE 23505.
INSERT INTO test_products (product_id, sku, price)
VALUES (2, 'SKU-001', 130000.00);

-- Must run in the same session after the error:
ROLLBACK TO SAVEPOINT before_invalid_insert;

SELECT count(*) AS expected_one
FROM test_products;

ROLLBACK;
~~~

This is an **interactive execution pattern**: the client must still send `ROLLBACK TO SAVEPOINT` after the failing statement. Runners or scripts configured with "stop immediately on SQL error" halt before the rollback line; in code, your test framework catches the exception and issues the rollback itself. `SAVEPOINT` illustrates partial transaction recovery for testing errors—not that production code should silently swallow errors and keep going.

## 6. Staging: Matching Production in Behavior-Defining Attributes

**Staging** is where release candidates are rehearsed before production. It does not need to match production's exact CPU count or terabytes of storage, yet it must reflect factors that alter behavior:

| Aspect | How Closely Should Staging Match Production? |
| --- | --- |
| PostgreSQL major version | Should share the same major version with controlled minor/patch levels; minimize feature or planner drift |
| Extensions | Same extensions and compatible versions when relied upon |
| Schema and migrations | Identical migration history; test migrations from a production-like state |
| Role privileges | Test using real application roles rather than masking issues with superuser |
| Encoding/collation | Compatible comparison, sorting, and unique-key rules |
| `search_path` and TimeZone | Explicitly aligned to avoid table-resolution or timestamp interpretation mismatches |
| TLS and connection path | Test authentication, proxies, pooling, timeouts, and routing |
| Data | Representative variety and scale, anonymized if sourced from production |
| Migration/DDL locks | Test impact on concurrent queries, not just whether the script finishes |
| Backup/restore | Capable of rehearsing system recovery requirements |
| Monitoring | Sufficient logs/metrics to spot regressions during releases |

Any differences between staging and production must be **explicitly documented**. For example, if staging holds 10,000 rows while production holds 200 million rows, an index scan in staging does not prove that query is fast enough in production.

### 6.1. When Using a Copy of Production Data

Testing query plans or migrations on representative data is valid, though security risk is high. Recommended workflow:

1. Have a clear justification and formal approval under organizational policy.
2. Extract only needed tables/columns, minimizing data before transfer whenever possible.
3. **Anonymize or synthesize** personal data using approved rules; verify combined fields cannot re-identify individuals.
4. Strip unnecessary credentials, tokens, secrets, password hashes, and payment details.
5. Encrypt data in transit and at rest; restrict human and application access.
6. Enforce strict retention deadlines, deletion procedures, and access audits.

Never assume `pg_dump` sanitizes data: it logically exports whatever data the user can read. Options like `--exclude-table` or object filters do not protect privacy in remaining columns.

### 6.2. Staging Is Not a Playground for Ad-Hoc Destructive Tests

Staging is often a **shared resource across multiple teams** with interconnected service workflows. If one developer runs `DROP SCHEMA ... CASCADE` to reset it, other teams lose their test environment.

A better strategy:

- Schedule announced staging reset windows or automated rebuild pipelines.
- Isolate test data by tenant or namespace when supported by the application.
- Track exact schema versions, app builds, and loaded datasets.
- Maintain snapshots/rollback capability before major changes if the staging state holds value.

Staging remains **non-production** in purpose, yet that does not mean arbitrary destructive actions are acceptable.

## 7. Production: Stability, Security, and Recoverability First

Production holds live data and workloads that real users depend on. Design and configuration must satisfy business commitments, not merely pass a test suite.

Foundational requirements typically include:

- Infrastructure and access controls separated from learning/test environments.
- Versioned, peer-reviewed schema/migration workflows with controlled deployment gates.
- Secured connection paths: network policies, TLS, strong authentication, and secret management.
- Application roles following **least privilege**; never use superuser for routine requests.
- Automated backups, planned retention, and periodic **restore drills**.
- Alerting and monitoring on disk, CPU, I/O, sessions, locks, replication (if used), WAL, and autovacuum.
- Load shedding, timeouts, connection limits, and outage response plans.
- Release procedures with clear rollback/forward-fix plans and named owners.
- Documented RPO/RTO targets backed by tested recovery or failover drills.

### 7.1. Never Disable Durability Settings to "Speed Things Up"

PostgreSQL exposes parameters controlling WAL writes, flushing, and storage synchronization. In normal production systems, **never disable durability safeguards** such as `fsync` or `full_page_writes` just to boost small benchmarks. Similarly, configuring `synchronous_commit` requires understanding the trade-off between latency and potential loss of recent transactions during a crash.

You can inspect current values:

~~~sql
SHOW fsync;
SHOW full_page_writes;
SHOW synchronous_commit;
SHOW wal_level;
SHOW max_connections;
~~~

Defaults and active values must be evaluated alongside data-safety goals, storage hardware, standby topology, and backup procedures. Never copy a list of "tuning parameters" from a blog or local setup straight to production without benchmarking and testing.

### 7.2. Connection Pools and Load Differences

Locally, a learner opens two connections and runs queries. Production runs multiple application instances, each maintaining its own pool:

~~~text
App instance A: 20 connections
App instance B: 20 connections
App instance C: 20 connections
--------------------------------
Total potential: 60 connections
~~~

When services scale across multiple replicas/containers, total connections climb rapidly. Pool sizing must account for `max_connections`, per-session memory, query patterns, long transactions, poolers like PgBouncer (if used), and actual server capacity—bigger pools are not automatically faster.

In production, monitor **active / idle / idle in transaction** states and connection wait times. Long-running `idle in transaction` sessions hold snapshots and locks, blocking autovacuum and causing table bloat.

### 7.3. Managing Time and Timezones

A subtle release bug happens when local and production use different `TimeZone` settings. PostgreSQL provides `TIMESTAMP WITHOUT TIME ZONE` and `TIMESTAMPTZ` with distinct semantics. For event timestamps, standardize on `TIMESTAMPTZ` and normalize display formatting in the application.

Check:

~~~sql
SHOW TimeZone;

SELECT
    now() AS current_instant,
    now() AT TIME ZONE 'UTC' AS utc_wall_time;
~~~

`TIMESTAMPTZ` represents an exact instant and displays in the session's timezone; it does not store the user's originally selected timezone name. When testing edge cases around daylight saving transitions or midnight boundaries, verify explicit business expectations rather than relying on your laptop's local clock.

## 8. Separating Connection Configs by Environment

Applications typically parameterize connections per environment:

~~~text
DB_HOST
DB_PORT
DB_NAME
DB_USER
DB_PASSWORD / secret reference
DB_SSL_MODE
DB_POOL_SIZE
DB_CONNECT_TIMEOUT
DB_STATEMENT_TIMEOUT
APPLICATION_ENV
~~~

Never hardcode URLs into source code per deployment. Prefer externalized configs and managed secret injection; never commit files with real passwords to Git.

Illustrative example:

| Attribute | Local | Test/CI | Staging | Production |
| --- | --- | --- | --- | --- |
| Host | `127.0.0.1` | Isolated CI service | `pg-stg.internal` | `pg-prod.internal` |
| Port | `5541` | Internal `5432` | Per infrastructure | Per infrastructure |
| Database | `learning_db` | `test_<run_id>` | `shop_staging` | `shop` |
| Role | `lab_admin` / `lab_app` | `test_runner` | `shop_app_staging` | `shop_app_prod` |
| Data | Synthetic | Fixtures | Representative, controlled | Live |
| Secret | Lab-only | Short-lived secret | Dedicated staging secret | Protected/rotated production secret |

These hostnames are examples only. **A database name or `APPLICATION_ENV=production` variable is not sufficient proof you are connected to the right production database.** Identification must rely on managed connection profiles, server identity, network topology, privileges, and pipeline verification steps.

### 8.1. Checking Context Before Running Migrations or Risky Tasks

A read-only verification query for operators:

~~~sql
SELECT
    current_database() AS database_name,
    current_user AS role_name,
    session_user AS authenticated_role,
    inet_server_addr() AS server_address,
    inet_server_port() AS server_port,
    current_setting('server_version') AS server_version,
    current_setting('application_name') AS application_name;
~~~

`inet_server_addr()` returns `NULL` over Unix-domain sockets; behind proxies, the returned address may not distinguish backend tiers on its own. Combine deployment identity, authenticated profiles, and access policies rather than trusting a single field.

In `psql`, halt deployment scripts on the first error:

~~~bash
psql \
  -h pg-stg.internal \
  -U migration_user \
  -d shop_staging \
  -v ON_ERROR_STOP=1 \
  -f migration.sql
~~~

This is an **example of running a write-capable migration against staging**; never run it unless `migration.sql` is reviewed and the target environment is confirmed. `ON_ERROR_STOP=1` stops `psql` on SQL errors, yet does not automatically guarantee prior statements rolled back; design explicit transaction boundaries and separate DDL commands that cannot run inside transactions.

### 8.2. Using Privileges as Guardrails

A far more reliable safeguard than human memory is **not granting unnecessary privileges**:

- CI test roles can create/modify/drop objects only inside their job's test database.
- Production developer roles (if access is granted at all) are restricted to metadata or approved read-only queries.
- Application roles lack `DROP TABLE` or `ALTER TABLE`.
- Migration roles receive elevated privileges strictly through audited, approved pipelines.
- Backup accounts hold only backup-required permissions, not blanket superuser rights for all tasks.

In PostgreSQL, you can assign object ownership to group roles and grant login roles specific privileges via `GRANT`. Pay attention to **role ownership**, `CREATE` on schemas, sequence privileges, and default privileges for newly created objects. Granting only `SELECT` on a table may not suffice for operations involving `INSERT ... RETURNING` or sequences.

### 8.3. Never Share Credentials Across Environments

Using the same password/role across test, staging, and production creates **lateral access** risk: credentials leaked from a CI runner or laptop can open access to production. Always isolate:

1. Credentials and secret lifecycles.
2. ACLs/firewalls/network paths.
3. Role privileges and database ownership.
4. Access logging and monitoring.
5. Personnel/services authorized for writes or administration.

These boundaries prevent a mistake in learning or testing from spilling over into live data.

## 9. Migrations: Keeping One Schema Consistent Across Environments

Migrations exist so database structures remain **reproducible and upgradeable**, rather than edited manually per machine.

Example of two versioned scripts:

~~~sql
-- V001__create_products.sql
CREATE TABLE app.products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    price NUMERIC(12, 2) NOT NULL CHECK (price > 0)
);
~~~

~~~sql
-- V002__add_active_flag.sql
ALTER TABLE app.products
ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE;
~~~

These examples **assume schema `app` already exists** from an earlier migration or database owner setup. They illustrate versioned migration scripts—not SQL files meant to run standalone on a missing schema while skipping prerequisites.

Promotion flow:

~~~text
Commit migration to Git
        |
        v
Run on fresh test DB + automated tests
        |
        v
Run on staging with representative data
        |
        v
Review outcome, duration, locks, rollback plan
        |
        v
Deploy to production via authorized pipeline
        |
        v
Monitor application and database post-deploy
~~~

### 9.1. Not Every ALTER TABLE Is Cheap

A migration finishing in milliseconds on a 50-row table can block on locks or rewrite massive amounts of data in production. While PostgreSQL supports transactional DDL for many commands, you must still understand lock levels and costs:

- Adding a column can be cheap in some cases, whereas changing column types or backfilling large tables may require table rewrites.
- Standard index creation blocks writes; `CREATE INDEX CONCURRENTLY` allows concurrent writes with specific conditions and caveats.
- `CREATE INDEX CONCURRENTLY` cannot run inside an explicit transaction block.
- Validating foreign keys/constraints on huge tables can take a long time; consider `NOT VALID` followed by `VALIDATE CONSTRAINT` where appropriate.
- Evaluate `lock_timeout`, `statement_timeout`, and migration retry logic to avoid holding blocking locks indefinitely.

Example SQL targeting an **existing table verified in staging**:

~~~sql
CREATE INDEX CONCURRENTLY idx_products_active
ON app.products (is_active);
~~~

There is no guarantee a single-column index on boolean `is_active` benefits every data distribution; this simply illustrates DDL with special operational requirements rather than universal index advice.

### 9.2. Deploying Breaking Changes Safely

Instead of dropping or renaming a column still used by live code in a single release, follow a phased strategy:

1. **Expand:** add new structures while old code continues working.
2. **Migrate/backfill:** copy data gradually in bounded batches.
3. **Switch:** deploy application code reading/writing the new structure.
4. **Contract:** remove legacy structures only after confirming zero old consumers remain.

This sequence is vital in staging and production where multiple app instances roll out gradually. A migration merely "succeeding in SQL" does not prove old and new app versions operate safely side by side during rollout.

## 10. Backups and Recovery: How Test, Staging, and Production Differ

### 10.1. Backup Goals Must Reflect Data Value

Locally, losing a seeded database costs a few minutes to rebuild. In production, losing recent orders can be a major business incident. Agree on two metrics:

- **RPO (Recovery Point Objective):** maximum acceptable data loss measured in time.
- **RTO (Recovery Time Objective):** maximum acceptable time to restore service.

Targets like "15-minute RPO, 2-hour RTO" are illustrative examples only. Having "yesterday's dump file" does not meet them; backup/WAL frequency, storage, staffing, and restore speed must all support those targets.

### 10.2. pg_dump/pg_restore for Small Databases and Logical Checks

A custom-format logical backup:

~~~bash
pg_dump \
  -h 127.0.0.1 -p 5541 -U lab_admin \
  -d learning_db \
  -F c \
  -f learning_db.dump
~~~

Create a **separate restore target** in the lab, then restore:

~~~bash
createdb \
  -h 127.0.0.1 -p 5541 -U lab_admin \
  learning_restore

pg_restore \
  -h 127.0.0.1 -p 5541 -U lab_admin \
  -d learning_restore \
  --no-owner --no-privileges \
  --exit-on-error \
  learning_db.dump
~~~

This is a **restore-testing drill**, not a command to overwrite production. `learning_restore` must exist as an empty database, the user needs database-creation privileges, and dump contents/extensions/roles must be compatible with the target environment.

`pg_dump` backs up one database logically; it does not automatically capture cluster-wide objects like roles, server configuration files, or WAL history. Real systems require separate plans for those components.

### 10.3. Production Often Requires Base Backups and WAL Archiving

For **point-in-time recovery (PITR)**, PostgreSQL uses a base backup plus a continuous archive of WAL segments to replay changes up to a chosen timestamp. This requires dedicated configuration, storage capacity, encryption, monitoring, and restore drills.

~~~mermaid
flowchart LR
    A["Base backup at T0"] --> B["WAL archive T0→T1"]
    B --> C["WAL archive T1→T2"]
    C --> D["Restore base backup + replay WAL"]
    D --> E["State at target point in time"]
~~~

**Replication does not replace backups.** An accidental `DELETE` or bad data migration on the primary replicates almost immediately to standbys. Standbys provide high availability and read scaling, not an immutable historical timeline to undo logical mistakes.

In staging, rehearsing restores from sanitized backups validates both infrastructure procedures and application compatibility. Any real data brought into non-production must still adhere to data-protection policies.

### 10.4. Backup Criteria by Environment

| Environment | Practical Criteria |
| --- | --- |
| Lab | Seed data is reproducible; back up valuable study exercises as needed |
| Test/CI | Data is rebuilt automatically; keep failure logs/artifacts per retention rules |
| Staging | Snapshots/restores for major rehearsals; avoid retaining unnecessary sensitive data |
| Production | Backup + WAL/PITR policy matching RPO, retention, off-site failure-domain storage, restore drills, and audits |

## 11. Observing PostgreSQL and Testing Depth by Environment

Each tier requires different observability:

- **Local:** inspect server logs, `psql` errors, and query output.
- **CI:** capture startup, migration, test, and container logs on job failure.
- **Staging:** enable metrics/tracing comparable to production; test alerts and connection failure handling.
- **Production:** continuous monitoring against SLOs, alert thresholds, on-call rotation, and incident runbooks.

Useful status queries:

~~~sql
SELECT
    datname,
    numbackends,
    xact_commit,
    xact_rollback,
    deadlocks,
    blks_read,
    blks_hit
FROM pg_stat_database
WHERE datname = current_database();
~~~

And sessions holding open transactions:

~~~sql
SELECT
    pid,
    usename,
    state,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE datname = current_database()
  AND xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Counters in `pg_stat_database` are cumulative statistics, not per-second rates. `pg_stat_activity` also hides certain details depending on role privileges; grant monitoring access per security policy rather than by default to every account.

### 11.1. Testing Failure Modes Often Missed Locally

Examples:

- Two requests updating the same row concurrently: how do deadlocks, lost updates, or serialization failures behave?
- If a statement inside a transaction raises `23505`, does the transaction roll back cleanly or attempt to commit?
- What does the application do if the connection times out right at `COMMIT`, leaving transaction outcome unknown?
- Does a migration hold locks too long alongside concurrent writes?
- Is the app role genuinely denied when attempting `DROP TABLE` or reading forbidden schemas?
- Does restoring from backup recover all constraints, sequences, extensions, and required data?

Never experiment with these casually in production. Simulate them safely in test/staging and feed findings into production runbooks.

### 11.2. Data-Driven Performance Differences

A query:

~~~sql
EXPLAIN
SELECT *
FROM app.products
WHERE is_active = TRUE;
~~~

may pick a `Seq Scan` on a table with a few dozen rows—which may be optimal for the planner. On tens of millions of rows, execution plans depend on data skew in `is_active`, available indexes, selected columns, and statistics.

In test/staging with representative data:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sku, price
FROM app.products
WHERE is_active = TRUE;
~~~

`EXPLAIN (ANALYZE, BUFFERS)` **actually executes the SELECT** to measure runtime and buffer/page activity. It can impose heavy load on large tables. For DML statements, `EXPLAIN ANALYZE` actually modifies data unless wrapped and rolled back—assess risk before running it in any environment.

To analyze production load safely, rely on production query metrics or authorized copies in a dedicated performance environment rather than running destructive load tests directly against live production.

## 12. Preventing "Wrong Environment" Mistakes with Layered Defenses

No magic SQL statement makes production immune to human error. Apply **defense in depth**:

### 12.1. Identification Layer

- Name connection profiles distinctly and display clear environment badges in SQL clients.
- Distinguish actual endpoints and networks, not just `DB_NAME`.
- Before critical actions, query `current_database()`, `current_user`, and infrastructure details.
- Set a distinct `application_name` per client source to aid log/metric correlation.

Client example:

~~~sql
SET application_name = 'postgres-learning-lesson-41';

SELECT
    current_database(),
    current_user,
    current_setting('application_name');
~~~

`application_name` aids observability; **it is not an identity verification mechanism**: any authorized client can set this string freely.

### 12.2. Privilege-Restriction Layer

- Test users have zero privileges in production.
- Application users hold only required DML on needed objects.
- Migration credentials are not embedded in runtime app images running 24/7.
- `DROP`/`ALTER` rights stay bound to separate ownership/administrative roles.
- High-impact actions require formal review/approval and audit trails.

### 12.3. Infrastructure Layer

- Local setups bind only loopback or private interfaces.
- CI uses isolated networks/services and per-job databases.
- Staging and production separate network policies, cloud accounts, namespaces, or deployment boundaries according to risk.
- Staging credentials cannot authenticate to production.
- Require TLS and server verification across networks demanding transport security.

### 12.4. Process Layer

- Migrations undergo code review and dry runs.
- Destructive reset scripts run solely in designated environments after verifying target resources.
- Backup/restore tests precede major changes as required.
- Rollouts support halting on metric degradation with tested rollback/fix-forward plans.
- CI/CD runs log job identity, migration version, executing role, and target environment.

A **pre-flight checklist before risky operations**:

| Question | If You Cannot Answer Yet |
| --- | --- |
| Which exact server/instance and database am I connected to? | Stop and verify |
| What privileges does the current account hold? | Check connection and privilege policies |
| Is data in this environment disposable? | Do not run reset commands without authorization |
| Has the script been tested on an isolated DB? | Test in test/staging first |
| Are backups/restores ready if something fails? | Do not perform major production changes |
| Is someone assigned to monitor post-change? | Assign ownership and monitoring first |

## 13. Scenario Walkthroughs: Choosing the Right Environment

### Scenario A — Learning Foreign-Key Violations

You want to intentionally insert an order referencing a non-existent customer to observe error `23503`. The right environment is **lab or test**—never production. In a lab, use a dedicated schema with synthetic rows and roll back afterward.

### Scenario B — Testing a Column-Addition Migration on a Large Table

You need to confirm a migration does not lock a table too long, supports two concurrent app versions, and finishes within budget. Start with **integration tests** on a fresh DB for syntax correctness, then **staging** with representative volume and load. Production receives the migration only through the approved pipeline.

### Scenario C — Testing Connection Loss During Writes

You want to see how application rollback, retries, and idempotency behave when the DB becomes temporarily unreachable. Use a test environment where you can intentionally sever networking, restart containers, or inject faults; never restart a production primary just to test.

### Scenario D — Investigating a Slow Production Query

Live data causes a query to take several seconds. Use metrics, slow-query logs, and `EXPLAIN` to diagnose current behavior; if you need `EXPLAIN ANALYZE` or index experiments on large datasets, use a staging/performance environment with representative data and a safe test plan. Never extrapolate production plans from a few local rows.

### Scenario E — Rehearsing Backup Recovery

A production backup must be verified. Restore into an **isolated environment** with appropriate privileges, capacity, and data protection. Never restore over an active production database just "to check if the dump file is readable."

### Scenario F — Adding a PostgreSQL Extension

An application library requires an extension such as `pg_trgm`. First confirm extension availability on your server version and installation privileges; test locally/in CI, verify migrations and compatibility in staging, and only then promote to production.

~~~sql
-- Practice example on a database you are authorized to administer.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

SELECT extname, extversion
FROM pg_extension
WHERE extname = 'pg_trgm';
~~~

Do not assume every managed service supports every extension or permits regular app roles to install extensions. Extension approvals also affect security and future PostgreSQL upgrades.

## 14. Common Mistakes When Organizing PostgreSQL Environments

| Mistake | Why It Is Risky | How to Improve |
| --- | --- | --- |
| Testing `TRUNCATE`/`DROP` on production | Destroys data and causes downtime | Separate lab/CI DBs, least privilege |
| Using one `postgres` user for apps and tests | Overly broad privileges, poor auditability | Separate roles per environment and task |
| Separating only `shop_dev` and `shop_prod` in one instance and assuming full isolation | Still shares resources and failure domain | Separate deployments/networks/secrets to protect production |
| Using `postgres:latest` in CI | Major version can shift unexpectedly on pull | Pin major/patch/digest per policy |
| Keeping real production data on laptops | Privacy breach and secret exposure | Use synthetic seeds or approved anonymized data |
| Running tests against a shared mutable DB | Flaky tests, cross-interference, non-reproducible | Ephemeral DB/container per job or suite |
| Only testing via single-connection rollbacks | Masks commit bugs, concurrency races, external side effects | Include real commits, multi-connection tests, idempotency |
| Staging diverges from production in schema/extensions | Surprises appear only at go-live | Promote identical migrations, track config differences |
| Manual schema edits in production | Environment drift, hard to audit/recover | Version-controlled, reviewed migrations |
| Setting `fsync=off` in production for speed | Increases risk of data loss/corruption on crash | Keep validated durability settings |
| Having `pg_dump` without testing restores | Unknown whether backups are complete or usable | Periodic restore drills into isolated environments |
| Skipping backups because standbys exist | Logical errors replicate immediately | Maintain backups + PITR per RPO/RTO |
| Unbounded connection pool sizes | Exhausts connections, memory, and increases contention | Benchmark load, cap pools, configure timeouts |
| Treating environment labels as authentication | Misnamed profile can still hit live production | Enforce network boundaries, separate credentials, verify instance |
| Running lab cleanup without checking volume names | Can wipe non-lab data | Verify exact container/volume names and data ownership |

## 15. Practice Exercises and Evaluation Criteria

### Exercise 1 — Identifying the Four Environments

Given four goals:

1. Run an invalid `INSERT` to inspect error codes.
2. Re-test all migrations on an empty database on every code push.
3. Rehearse a PostgreSQL upgrade and measure DDL locking before release.
4. Serve live customer orders with strict backups, alerts, and access control.

Match each to **local/lab**, **test/CI**, **staging**, or **production**, and explain why the other environments are suboptimal for each goal.

### Exercise 2 — Distinguishing Isolation Levels

Suppose a PostgreSQL instance holds both `shop_dev` and `shop_prod`. Answer:

- Do both databases share the instance's CPU and disk?
- Can a single superuser modify both?
- If the disk holding WAL fills up, will only `shop_dev` be impacted?
- What extra boundaries are needed to shield production from dev mistakes?

**Hint:** databases and schemas provide SQL-layer naming/privilege boundaries, not full failure-domain or resource isolation.

### Exercise 3 — Building a Safe Lab

Run PostgreSQL in a container binding a host port strictly to `127.0.0.1`, creating database `learning_db`, schema `sandbox`, and table `sandbox.notes`. Connect with `psql`, run `SELECT current_database(), current_user` and `\conninfo` to verify. When finished, stop the container while keeping the volume; explain why data persists upon restarting.

### Exercise 4 — Testing Errors Inside a Transaction

Create a temporary table with `UNIQUE`, insert `SKU-001`, then use a savepoint to attempt a duplicate insert. Observe SQLSTATE `23505` and use `ROLLBACK TO SAVEPOINT` to continue querying. Explain what happens if you do not roll back after a statement fails.

### Exercise 5 — Comparing Versions and Privileges

Build a table recording `server_version`, extensions, `TimeZone`, `search_path`, and roles across local/staging/production (reading only permitted metadata). Identify which differences can impact:

- Migration syntax/types.
- String comparisons, uniqueness checks, and sorting.
- Timestamp display formatting.
- `CREATE INDEX`, `ALTER TABLE`, and application DML privileges.

### Exercise 6 — Designing a Production-Scale Test Plan

A query is slow only on a 10-million-row table. Propose how to generate data of representative scale and distribution **without using unauthorized sensitive info**, conditions for running `EXPLAIN (ANALYZE, BUFFERS)`, and metrics to compare before and after adding an index.

### Exercise 7 — Testing Backup and Restore

Dump `learning_db` using `pg_dump -F c`, restore into `learning_restore`, and inspect `sandbox.notes` and its row count. Explain why merely seeing a `.dump` file does not prove you can recover an entire production system.

### Exercise 8 — Reviewing a Deployment Scenario

A developer wants to run this script directly:

~~~sql
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
~~~

against a connection profile named "Test" whose actual URL points to production. Identify all guardrails needed to prevent this incident: profiles/infrastructure, network, roles, privileges, confirmations, migration workflows, backups, and auditing. **Do not run those two commands**; this is a risk-analysis exercise.

## 16. Checklist Before Transitioning from Learning to Real Operations

| Question | When Is It Satisfied? |
| --- | --- |
| Do you know the exact current server and database? | Connection verified via multiple signals, not just a profile name |
| Is the schema reproducible? | Migrations succeed from scratch on an empty database |
| Are tests independent and repeatable? | Automated fixtures and cleanup; tests never touch production DBs |
| Is non-production data safe? | Free of unauthorized secrets/PII; access tightly controlled |
| Are configs and versions consistent? | Differences tracked, compatibility verified in staging |
| Does the app handle transaction errors? | Clean rollback/commit logic, appropriate retries/idempotency |
| Are access privileges restricted? | Separate app/test/migration/backup roles, no superuser abuse |
| Are migrations verified? | Tested in CI and staging with monitoring/recovery plans |
| Are backups and restores tested? | Proven successful restore into an isolated environment |
| Are load and alerts in place? | Connections, disk, locks, WAL, backups, and autovacuum monitored |
| Is operational ownership defined? | Runbooks, on-call rotation, and incident response agreed |
| Are recovery targets defined? | RPO/RTO backed by tested backup/PITR/failover procedures |

## 17. Conclusion

**Learning environments** prioritize exploration, practice, and reproducibility; **test environments** prioritize automated pass/fail checks, deterministic data, and isolation; **staging** prioritizes rehearsing production-critical behaviors before release; **production** prioritizes data protection, high availability, and incident recovery.

Differences go far beyond row counts or database names. What truly separates them are **infrastructure boundaries, privileges and secrets, permitted data, configuration, migrations, backups, monitoring, and operational accountability**. A SQL statement can be 100% valid syntactically yet disastrous when executed in the wrong environment.

Before running any write, delete, or schema-change operation, always verify **where you are connected, which privileges you hold, how valuable the data is, and how to recover if it fails**. That core habit lets you learn PostgreSQL safely and grow toward operating reliable production systems.
