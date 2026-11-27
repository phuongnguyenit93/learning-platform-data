# Separating Development, Testing, and Production Environments with Oracle Database

In a project using **Oracle Database**, developers need to test SQL, change schemas, and generate sample data; QA teams need repeatable test runs; and the live system must protect data, maintain service availability, and recover from incidents. If everyone shares one database without clear boundaries, an experimental `DELETE`, `ALTER TABLE`, or bulk update can directly impact real users.

**Environment separation** means organizing where applications run, where data and configs live, how privileges are granted, and how changes roll out according to distinct purposes. In this lesson, the three core environments are **development (DEV)**, **testing (TEST)**, and **production (PROD)**. A project may add **staging/UAT** before production, yet the separation principles remain the same.

The goal is not merely giving databases different names. A meaningful boundary must answer: **which data is used, who has access, which resources are shared, how do changes enter each environment, and what is the blast radius if an operation goes wrong?**

## 1. Why Separate Environments?

Suppose a team is building an order-management application. Developers need to test a migration adding a status column, testers want to wipe data to re-run test scenarios, and production is actively processing customer transactions.

If all three connect to a single Oracle database:

- A `TRUNCATE TABLE` statement meant to clean test data can wipe real data.
- An unverified migration can cause locks, application errors, or unexpected table structure changes.
- Customer data can be read or copied onto developer machines that fail data-protection rules.
- Performance tests generate heavy load, consuming sessions, CPU, I/O, and redo/undo, impacting real transactions.
- Tests interfere with each other and become hard to reproduce because multiple people edit the same data.
- When an error occurs, the team struggles to tell whether the cause was new code, test data, or operational actions.

When properly separated, DEV can iterate rapidly; TEST has controlled data and scenarios; PROD receives only verified, approved, and observable changes. Separation also clarifies the release path and establishes a foundation for access control, backups, monitoring, and auditing.

```text
                  Source code + versioned migrations
                              |
                              v
                       DEV (development)
                         - experimentation
                         - synthetic data
                              |
                              v
                       TEST (testing)
                         - CI/integration tests
                         - repeatable scenarios
                              |
                              v
                  STAGING / UAT (if present)
                         - release verification
                         - PROD-like config
                              |
                       release approval
                              v
                        PROD (production)
                         - real users
                         - monitoring/backups

              Production data never flows backward
              into DEV/TEST without protection steps.
```

The arrows show **promoting verified changes to the next environment**; they do not mean one environment's data is automatically copied into another.

## 2. Purpose and Characteristics of Each Environment

| Criterion | DEV | TEST | PROD |
|---|---|---|---|
| Primary purpose | Writing code, testing SQL/PL/SQL, developing migrations | Verifying correctness, integration, regression, and business flows | Serving users, protecting data, and meeting service-level commitments |
| Data | Synthetic or minimal sample data | Managed, reproducible datasets covering diverse scenarios | Real business data with classification and retention policies |
| Schema changes | Frequent, resettable | Via migrations on a defined test schedule | Via pipeline, approvals, and appropriate change windows |
| Access rights | Developers have permissions inside a sandbox | Test automation and testers have scoped permissions | Least privilege, auditing, separation of admin and deployment duties |
| Data reset/refresh capability | Can be re-initialized on demand | Reset to baseline state by procedure | Never reset ad hoc; changes are strictly controlled |
| Logging / monitoring | Prioritizes diagnostics | Tests both logging and alerting | Continuous monitoring, log security, incident detection, and SLOs |
| Backup / recovery | Scaled to development data value | Ensures the test environment can be rebuilt or restored | Engineered backup/recovery drilled against RPO/RTO |
| Availability level | Interruptions acceptable | Depends on test execution schedule | Aligned with business requirements, backed by incident procedures |

Teams may add further tiers: **local DEV** per developer; **shared DEV** for early integration; automated **integration TEST**; **UAT** for business acceptance; **performance TEST** for load; and **staging/pre-production** for realistic release checks. Exact labels matter less than the purpose and usage contract of each environment.

### 2.1. Development does not have to mirror production

DEV prioritizes fast feedback. You can use Oracle Database Free or a team-assigned Oracle PDB with synthetic data and sandbox-only privileges. Developers can iterate on migrations repeatedly, yet anything intended to exist in other environments must be captured in versioned scripts rather than living only in personal SQL history.

If running Oracle Free locally, keep that edition's resource and feature limits in mind. Passing a test locally does not prove performance, availability, or behavior across the full production configuration.

### 2.2. Testing requires a reproducible state

TEST must not become a "shared DEV." Every integration test run must know which schema version is deployed, what initial data exists, which seed scripts ran, and how to reset afterward. For parallel test runs, each job may need its own PDB/schema or database so concurrent tests do not overwrite or delete each other's rows.

Large-scale performance tests need a dedicated controlled environment; sharing compute or storage with other environments skews measurements and threatens service availability.

### 2.3. Production carries service accountability

PROD holds real data, enforces logged access, imposes strict change controls, and has incident-response procedures. Code and migrations arrive through a traceable pipeline. Production must avoid experimental scripts, shared accounts, and test-only seed data.

## 3. Oracle Isolation Level: Database, PDB, or Schema?

In Oracle, "separate environments" can be implemented at several levels. Those levels **are not equivalent in isolation**.

### 3.1. Relevant layers in Oracle

- **Oracle instance:** memory and background processes serving database access. Workloads sharing an instance can contend for CPU, memory, and I/O.
- **CDB (container database):** multitenant architecture managing shared resources and hosting PDBs. Accounts with CDB-level admin privileges have a wide blast radius.
- **PDB (pluggable database):** logical database inside a CDB with its own object catalog and local users. Applications typically connect using a **service name** pointing to the assigned PDB.
- **Schema / user:** ownership boundary for tables, views, packages, indexes, and logical objects. Two schemas can have distinct privileges while still sharing the same database/PDB, instance, storage tier, and many shared settings.
- **Tablespace / datafile:** logical/physical storage areas; separating tablespaces does not create an independent security or operational boundary like separating databases.

### 3.2. Comparing three models

| Model | Example | Advantages | Key limitations |
|---|---|---|---|
| Separate schemas in the same PDB | `APP_DEV`, `APP_TEST`, `APP_PROD` in one PDB | Easy to set up, low resource overhead; suits small labs | Share instance/PDB, backups, and global config; misconfigured grants or admin mistakes can hit multiple environments |
| Separate PDBs, same CDB | `DEV_PDB`, `TEST_PDB`, `PROD_PDB` in one CDB | Isolates objects and local users at PDB level; easier lifecycle management than schemas | Still share instance, infrastructure, and CDB admin layer; shared outages or load spikes propagate |
| Independent CDB/instance or database service | DEV, TEST, PROD on separate deployments | Clearer boundaries for config, resources, operations, and blast radius | Higher cost and admin overhead; requires automation and monitoring |

**For personal practice:** two PDBs or two separate Oracle databases clearly demonstrate data isolation; if resources are tight, two schemas can illustrate privilege separation, as long as you recognize it is a weaker isolation level.

**For production systems with strict requirements:** independent database/CDB deployments are generally preferred, combined with separated networks, identities, secrets, backups, and admin privileges. Simply placing DEV and PROD in two PDBs inside one CDB still allows an infrastructure fault or CDB-level change to affect both.

The right choice depends on cost, criticality, available Oracle features, and security requirements. No single isolation pattern fits every organization.

### 3.3. Recommended environment diagram

```text
DEV application  ----> dev-db.internal:1521  / DEV_APP_SERVICE
                         Oracle DEV database/PDB
                         user: app_dev_runtime
                         data: synthetic

TEST application ----> test-db.internal:1521 / TEST_APP_SERVICE
                         Oracle TEST database/PDB
                         user: app_test_runtime
                         data: controlled fixtures

PROD application ----> prod-db.internal:1521 / PROD_APP_SERVICE
                         Oracle PROD database/PDB
                         user: app_prod_runtime
                         data: real business data
```

Hostnames and service names are **hypothetical examples**. Having different hostnames or TNS aliases alone creates no isolation if they still route to the same database or if accounts hold cross-environment privileges. Always verify the actual connection target and privilege boundaries.

## 4. How Applications Connect to the Right Environment

In Oracle, an Easy Connect JDBC URL has the form:

```text
jdbc:oracle:thin:@//<host>:<port>/<service-name>
```

Three illustrative endpoints:

```text
DEV  jdbc:oracle:thin:@//dev-db.internal:1521/dev_app_service
TEST jdbc:oracle:thin:@//test-db.internal:1521/test_app_service
PROD jdbc:oracle:thin:@//prod-db.internal:1521/prod_app_service
```

Applications must receive connection settings from their deployment environment rather than editing source code before each release. In a Java / Spring Boot application, shared configuration can simply read injected environment variables or secrets:

```yaml
# application.yml - shared across all environments
spring:
  datasource:
    url: ${DB_JDBC_URL}
    username: ${DB_APP_USERNAME}
    password: ${DB_APP_PASSWORD}
    driver-class-name: oracle.jdbc.OracleDriver
```

In each environment, the deployment platform injects distinct `DB_JDBC_URL`, `DB_APP_USERNAME`, and `DB_APP_PASSWORD` values. Actual passwords live in a **secret manager or platform secret store**, scoped per environment; never commit them to Git, container images, docs, or logs. Any `.env` file holding secrets must likewise be protected and excluded from the repository.

If a project uses Spring profiles (`dev`, `test`, `prod`), profiles select matching configuration but **are not a security control**. Combine them with database privileges, network isolation, per-environment secrets, and restrictions on where workloads can connect. A DEV process should never be able to reach a PROD endpoint just because someone edited a config variable.

### 4.1. Verifying where Oracle is actually connected

Before running SQL that alters data or schemas, verify the current session's user and container:

```sql
SELECT
    SYS_CONTEXT('USERENV', 'DB_NAME')        AS database_name,
    SYS_CONTEXT('USERENV', 'CON_NAME')       AS container_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME')   AS service_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER')   AS session_user,
    SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema
FROM dual;
```

The output might reveal the session landed in a different PDB or schema than intended. `CURRENT_SCHEMA` is the schema Oracle uses to resolve unqualified object names and can be altered via `ALTER SESSION SET CURRENT_SCHEMA`; it is **not the login identity** and does not change user privileges. Inspect `SESSION_USER`, connection endpoint, and container info together.

Beyond checking names, deployment pipelines should enforce **wrong-environment safeguards**: separate deployment identities/secrets/network routes, approval gates for production, and target database identity checks before executing migrations. A SQL name check is only an extra defensive layer.

## 5. Separating Data: Harder Than Separating Database Names

DEV and TEST need realistic data shapes to exercise business logic, yet that never justifies copying production data arbitrarily.

### 5.1. Preferring synthetic data

Generate synthetic data matching the system's domain:

- Primary keys, foreign keys, reference data, and multi-table relationships.
- Normal and boundary cases: `NULL`, Unicode strings, large numbers, time-zoned timestamps, duplicates, and maximum lengths.
- Data covering business states: new order, paid, cancelled, failed, refunded.
- Concurrency cases: two sessions updating the same record, unique constraint collisions, rollback on failure.
- Scaled datasets for query plans/load testing; a few dozen rows do not represent queries over tens of millions of rows.

Seed sets must be **versioned, predictable in expected output, and repeatable**. Across repeated runs, scripts should cleanly purge their own test data or use deterministic keys to avoid unintended duplication.

### 5.2. When a copy of production is genuinely needed

Some bugs appear only under real data distributions, index selectivity, or table sizes. In such cases, consider an **authorized copy with sensitive data sanitized**. The process requires explicit approval, copy scope, retention expiry, and post-processing verification:

1. Define the testing purpose and the minimal subset of data needed.
2. Pick a DBA-supported snapshot/clone/export method, such as schema-level Data Pump or an approved cloning tool.
3. Mask, tokenize, or anonymize fields containing personal info, identifiers, phone numbers, addresses, payment details, and other sensitive contents per applicable regulations.
4. Preserve foreign-key integrity and consistency of masked values; avoid producing a broken dataset that fails business workflows.
5. Strip real passwords, tokens, webhooks, real email recipients, live payment endpoints, and outbound integration settings.
6. Verify access permissions and outbound network blocks before opening the copy to developers/testers; set a deletion/refresh deadline.

**Masking must occur before granting access to anyone not authorized to view original production data.** Renaming a schema, placing the database on an internal network, or labeling it "TEST" does not make real data safe. Copies can still leak through backups, exports, logs, caches, or reporting queries.

### 5.3. Resetting and data lifecycle

TEST should have a reliable way to return to a known baseline: spin up a fresh schema/PDB per run where feasible, run migrations from scratch, load deterministic seeds, and clean up afterward. When full resets are impractical, isolate tests by tenant/test-run ID with reliable cleanup.

Production must never be "refreshed" with a data-wiping script for testing convenience. Conversely, DEV/TEST reset scripts still need strict permissions and guards so they never accidentally target the wrong endpoint.

## 6. Separating Oracle Accounts and Access Privileges

Each environment should have dedicated identities per job function. An illustrative matrix:

| Identity | DEV | TEST | PROD |
|---|---|---|---|
| Runtime application | User with rights to run business logic in DEV | Similar user, scoped strictly to TEST | Minimal required DML/`EXECUTE` privileges; no administrative DDL rights |
| Schema owner / migration | Allowed to modify sandbox schema | Migration pipeline executes on TEST | Dedicated migration identity, used only under approved workflow |
| Developer | Works freely within sandbox scope | Read/run tests per granted need | Normally no direct write access to live data; emergency access is controlled |
| Tester / automation | Can test features | Rights to load/reset TEST fixtures | Never uses test accounts against production |
| DBA / operations | Administers within assigned scope | Administers and restores TEST | Controlled admin access, audited, emergency procedures, separation of duties |

Principle of **least privilege**: an application needs only `SELECT`, `INSERT`, `UPDATE`, `DELETE`, or `EXECUTE` on the exact objects it uses; never grant `DBA`/`SYSDBA` or object-creation/drop rights merely for convenience. A migration identity may need DDL privileges, yet should never serve as the daily API runtime account.

Separating Oracle usernames is insufficient if credentials are shared across environments. You also need:

- Separate secrets for DEV, TEST, and PROD, with rotation and revocation procedures.
- Separate IAM groups/roles and approvals for production; avoid sharing personal admin accounts.
- Network segmentation so ordinary DEV/CI workloads cannot reach PROD listeners/services directly.
- Auditing and trails for privileged actions, deployments, and sensitive data access.
- Time-bound emergency (*break-glass*) access with justification, approver, and post-incident review.
- Blocks preventing test/sandbox jobs from calling live external systems such as email, SMS, payment gateways, or production queues.

With Oracle multitenant, **CDB/common-user** privileges and local **PDB** privileges have different scopes. When creating accounts or granting privileges, the DBA must target the exact container; never assume identically named accounts across PDBs represent the same identity.

## 7. Keeping Schemas Consistent with Versioned Migrations

Environment separation pays off when changes move from DEV → TEST → PROD traceably. Opening SQL Developer to hand-edit each database creates **schema drift**: the same application version running against different tables, columns, indexes, or constraints.

A practical workflow:

1. Developers author migrations as versioned source files, e.g., `V001__create_orders.sql`, `V002__add_order_status.sql`, matching the chosen tool's convention.
2. DEV runs the migration and tests business behavior; mistakes are fixed with managed changes.
3. CI initializes the TEST database from a known baseline, applies all migrations in order, runs integration/regression tests, and stores logs.
4. Staging (if used) runs the **exact same migrations and application artifact** slated for PROD.
5. The PROD pipeline uses dedicated credentials, checks the target, requires approval, logs applied versions, and monitors post-deploy health.

Tooling can be Flyway, Liquibase, or any versioned, auditable SQL migration mechanism. Commit to one source of truth for schema changes; avoid mixing automated migrations with frequent untracked manual schema edits.

### 7.1. Oracle DDL typically auto-commits

Oracle performs an **implicit commit** around many standard DDL statements such as `CREATE TABLE`, `ALTER TABLE`, and `DROP TABLE`. You cannot treat a sequence of DDL statements as an application transaction undone by a simple `ROLLBACK`. Before deploying, plan for the system state if the first statement succeeds and a later one fails.

For large tables or zero-downtime apps, rollouts commonly follow **expand → migrate → contract**:

```text
1. Expand: add new objects/columns while old application code keeps working
2. Migrate: deploy new code and backfill/migrate data in controlled batches
3. Verify: check data integrity, performance, and compatibility
4. Contract: remove old structures once no consumers depend on them
```

Not every migration needs all four phases, yet breaking changes (renames, column drops, data-type changes) should be tested on TEST/staging first with a concrete stop or forward-fix plan. Never treat production backups as a casual "Undo button," because restoring can discard valid transactions committed after the backup point.

### 7.2. Separating seed data from production migrations

DDL/schema definitions must stay consistent across environments, whereas **test seed data** belongs only in DEV/TEST. You can organize files as:

```text
database/
  migrations/          # shared, version-controlled schema changes
  test-fixtures/       # synthetic data and test cases, never run on PROD
  environment-config/  # configuration references; no secrets
```

These paths illustrate source-code organization. If genuine business **reference data** exists (such as canonical status lookup codes), treat it as operational data with controlled update scripts—never mix it with fake customer/order test fixtures.

## 8. Pipeline Promoting Changes Across Environments

A sound pipeline carries the exact same verified code and artifact forward while each environment supplies its **own configuration, identities, and data**.

```text
Commit / Pull Request
         |
         v
Build + unit tests + review
         |
         v
Deploy DEV (DEV schema) --- developer smoke test
         |
         v
Deploy TEST (TEST schema) -- migrations + integration/regression tests
         |
         v
Staging/UAT if present ------- verify release criteria
         |
         v
Production approval / change window
         |
         v
Deploy PROD (PROD schema) -- smoke test + metrics + incident readiness
```

In practice, teams build an immutable artifact once and **promote that exact artifact** from TEST to PROD to prevent rebuild discrepancies. For schemas, the pipeline runs matching versioned migrations; never copy TEST database state directly to PROD because TEST holds different data and activity than production.

Appropriate pipeline gates include checking target database/PDB, current schema version, code-to-migration compatibility, automated test status, free disk space, estimated runtime, deployer authorization, and abort criteria. After execution, log release ID, migration versions, approver, timestamp, and key metrics.

### 8.1. When a deployment fails

Suppose a new release queries column `PAYMENT_STATUS` before the migration ran. A properly separated workflow catches the version mismatch in TEST and blocks it before production. If a failure still reaches PROD:

- Operations identifies the release, health/latency impact, containment steps, and halts rollout if needed.
- Developers confirm which schema version the code expects, backward compatibility, and fix options.
- DBAs assess migration state, active transactions/locks, privileges, and data repair or recovery options.

Choosing between rolling back the app, running an extra migration, or rolling forward must depend on **current observed state**. Rolling back an app binary does not undo committed DDL, and rolling back a database can affect real user data.

## 9. What Should Be Tested in Each Environment?

| Test type | Where does it run? | Evidence to observe |
|---|---|---|
| Business-logic unit tests | Local / CI; can mock repositories | Rules execute properly without needing live Oracle when unnecessary |
| Oracle integration tests | TEST or isolated Oracle for CI | SQL runs on Oracle; data types, transactions, constraints, rollbacks, PL/SQL work |
| Migration tests | Clean TEST and TEST with prior schema | Both fresh install and upgrade from previous version succeed without losing valid data |
| Regression / end-to-end | TEST / staging | APIs and business flows work across connected services |
| Performance / concurrency | Dedicated representative test environment | Execution plans, p95/p99 latency, pool saturation, sessions, locks, CPU, I/O at target load |
| Backup/restore, failover | Controlled drill environment | Actual recovery time, data consistency, reconnect behavior, and runbook steps |
| Post-release smoke tests | PROD using safe, bounded operations | Services healthy, critical queries run, error rates and latency remain normal |

Testing on real Oracle reveals differences from in-memory or other databases across SQL dialect, data types, sequences/identities, DDL semantics, locking, and transaction behavior. Never claim "tested on Oracle" if all integration tests actually ran against a different database engine.

### 9.1. Parity with PROD

TEST does not always need PROD's exact CPU count or data volume, yet relevant tests require awareness of these differences:

- Oracle version, patch level, edition/licensed features.
- CDB/PDB configuration, tablespaces, NLS character semantics, collation, time zone, and related parameters.
- Schema definitions, constraints, indexes, statistics, and data size/distribution.
- JDBC driver, connection pool, timeouts, transaction isolation, and application replica count.
- Network topology, latency, storage, backup, and HA setup if within test scope.

A fast execution plan on a 100-row table does not prove the same plan will hold in PROD on 100 million rows. For performance tests, explicitly document parity gaps to bound how results are interpreted.

## 10. Environment-Aware Monitoring and Backups

**Monitoring must also carry clear environment labels.** A DEV alert should never be mistaken for a PROD incident. Dashboards and logs should include at minimum the environment name, related service/instance/PDB, timestamp, and release ID. Useful metrics include:

- Endpoint availability and Oracle connection success rate.
- Session counts, active/waiting connection pool slots, and connection acquisition errors.
- Latency of critical SQL statements, waits/locks, and prominent `ORA-` errors.
- CPU, memory, I/O, tablespace/datafile usage, and growth trends.
- Backup progress, recoverability status, and agreed alert thresholds.

**Backups are distinct from environment separation.** Separate PDBs or schemas still need proper backup/recovery strategies; sharing underlying storage or an admin domain can create single points of failure. For PROD, agree on:

- **RPO (Recovery Point Objective):** how much data loss in time is tolerable if a disaster occurs.
- **RTO (Recovery Time Objective):** target time to restore service.
- Supported, verified Oracle backup mechanisms (e.g., RMAN), retention schedule, storage destination, copy protection, and restore drills.
- Who holds authority to choose a point-in-time recovery target, since restoring can discard transactions recorded after that timestamp.

In DEV/TEST, fast rebuilding from migrations and seeds may take priority over retaining every piece of test data. Still, valuable datasets or test artifacts should be protected according to project requirements.

## 11. Practice Lab: Proving DEV and TEST Are Truly Isolated

This lab assumes your DBA or administrator provisioned **two distinct Oracle targets**, e.g., `DEV_PDB` and `TEST_PDB`, plus two least-privilege accounts. You do not need to create instances/PDBs or use `SYSDBA` to complete it. If you only have one local Oracle instance, you may create two schemas with administrator guidance, while clearly noting the lab verifies **schema separation**, not full database isolation.

### Step 1 – Record connection targets

Log into **DEV** with the assigned account and run:

```sql
SELECT
    SYS_CONTEXT('USERENV', 'DB_NAME')        AS db_name,
    SYS_CONTEXT('USERENV', 'CON_NAME')       AS con_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME')   AS service_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER')   AS session_user
FROM dual;
```

Save the results for comparison. Exit the DEV session, log into **TEST**, and run the exact same query. When the two environments use separate PDBs, `CON_NAME` must reflect two different containers; if they are independent Oracle deployments, also compare the host/service targets supplied by your administrator. Username alone is not enough to prove isolation.

### Step 2 – Create sample data only in DEV

Confirm again that your session is in DEV. Inside your practice schema with `CREATE TABLE` privilege and sufficient quota, run:

```sql
CREATE TABLE lab_environment_marker (
    marker_id   NUMBER PRIMARY KEY,
    env_name    VARCHAR2(20 CHAR) NOT NULL,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL
);

INSERT INTO lab_environment_marker (marker_id, env_name)
VALUES (1, 'DEV');

COMMIT;

SELECT marker_id, env_name, created_at
FROM lab_environment_marker;
```

The `DEV` row is illustrative data; never use real user data. If the table already exists from an earlier lab, use a clean schema or clean up following DEV's permissions and rules—never run `DROP` blindly on an unverified connection.

### Step 3 – Verify TEST did not receive the DEV change

Connect to TEST using its corresponding account and run:

```sql
SELECT table_name
FROM user_tables
WHERE table_name = 'LAB_ENVIRONMENT_MARKER';
```

If TEST was freshly initialized and no migration created this table yet, the expected output is **zero rows**. `USER_TABLES` lists tables owned by the current schema; it confirms the logged-in schema state, though it is not the sole security proof. Cross-check `DB_NAME`, `CON_NAME`, `SERVICE_NAME`, `SESSION_USER`, and deployment architecture alongside it. If the table already appears in TEST, check whether another script created it or whether you connected to the wrong environment.

### Step 4 – Create the same structure in TEST via migration

In real workflows, DEV and TEST schemas stay aligned via **versioned migrations**. Once a verified migration runs on TEST, the table exists in both places, yet **each environment holds its own data**. Insert a row with `env_name = 'TEST'` in TEST via a managed fixture, then verify:

```sql
SELECT env_name, COUNT(*) AS row_count
FROM lab_environment_marker
GROUP BY env_name;
```

DEV should show only its `DEV` data; TEST should show only its `TEST` data. **Same table name, same structure, different datasets** is completely normal when environments are properly separated.

### Step 5 – Record lab evidence

In your lab report, record the isolation model used (database/PDB/schema), service names, usernames, migration versions, seed sources, outputs from both environment checks, and how TEST can be reset. Never record passwords, connection strings containing secrets, or sensitive data. Answer for yourself: can a TEST account log into PROD, can a DEV migration target PROD, and how severely could a disk-full error in DEV affect PROD? Those questions reveal true isolation depth.

## 12. Operational Scenario: Pointing at PROD by Mistake

Suppose during an integration test run, a configuration variable gets changed to the production Oracle endpoint. If privileges and networks are not separated, a test job executing data cleanup can cause a real outage even though the job is named `test`.

Defense in depth prevents or limits the damage:

1. The TEST runner only has network routes to Oracle TEST; the PROD endpoint is unreachable on allowed routes.
2. The runner holds TEST secrets only, never production secrets.
3. The TEST runtime account has zero privileges on PROD objects, even if a network path existed.
4. The pipeline checks target database/PDB identity and requires separate approval before migrating PROD.
5. Destructive scripts (`TRUNCATE`, large backfills, object drops) are reviewed and guarded for their intended environment.
6. Monitoring/auditing detects unexpected access; runbooks define who coordinates, who verifies data integrity, and how to stop blast radius growth.

Takeaway from this scenario: **an environment label in a UI or `APP_ENV=TEST` variable is not enough to protect data**. You need simultaneous boundaries across connection endpoints, networking, identities, Oracle privileges, deployment pipelines, and observability.

## 13. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Sharing one schema across DEV, TEST, and PROD | Data overwrites, schema drift, broken tests, risk to live users | Separate at least schemas by purpose; prefer separate PDBs/databases when strict isolation is required |
| Different service names pointing to the same PDB | Illusion of isolation while actually sharing data and resources | Verify service-to-Oracle target mapping and session context |
| DEV holding DBA or PROD credentials | Mistakes or leaked secrets have massive blast radius | Separate identities and privileges; never distribute PROD secrets to DEV developers/runners |
| Copying PROD database as-is into TEST | Leaks real user data, live endpoints, secrets, and sensitive info | Enforce scope approval, masking, endpoint/secret scrubbing, retention limits, and network isolation |
| Hand-editing tables differently in each environment | DEV/TEST/PROD run diverging schema versions | Use versioned migrations, control drift, and record deploy evidence |
| Running integration tests only on a non-Oracle database | Misses Oracle SQL dialect, constraints, transactions, and runtime behavior | Test against real Oracle when integration fidelity matters |
| Benchmarking performance on tiny datasets | Misleading conclusions on execution plans, indexes, and latency | Use representative data volume, distribution, and load; document gaps vs. production |
| Treating backups as migration rollback | Risk of losing valid transactions committed after the restore point | Design expand/contract migrations, forward-fix plans, and approved recovery procedures |
| Mixing logs and alerts across environments | Misclassified incidents and alert noise | Tag environment/service/release and route alerts separately |

## 14. Principles for Real-World Projects

When designing an Oracle environment for a new team, start with a **simple yet accurate diagram**: which app connects to which database/PDB, via which service, with which user/role, where data comes from, and who owns operations. From there, define migration, seeding, TEST reset, PROD protection, monitoring, and recovery strategies. Acceptance criteria for environment setup include:

- **Boundaries:** DEV/TEST cannot write to PROD; network paths and accounts are scoped strictly by purpose.
- **Data:** TEST has reproducible fixtures and carries no unmasked sensitive data.
- **Schema:** every environment knows its migration version; schemas do not silently change via ad-hoc manual edits.
- **Deployment:** artifacts and scripts promote in a controlled pipeline, use environment-specific secrets, and verify targets before running.
- **Testing:** real Oracle tests exist, and test environments sufficiently represent the risks being validated.
- **Operations:** dashboards, backups, runbooks, clear owners, and explicit abort thresholds exist for production.

**Separating DEV, TEST, and PROD means isolating the blast radius of actions.** For Oracle, you must consider **database/CDB/PDB, schema, user/role, connection service, data, compute/storage resources, and deployment workflows** together. Setting this up properly lets developers experiment freely in a sandbox, lets testers reproduce reliable results, and lets operators protect data and availability in live production.
