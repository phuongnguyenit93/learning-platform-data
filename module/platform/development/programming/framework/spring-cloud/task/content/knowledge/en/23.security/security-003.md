# Database Authorization for Task Execution and Schema Management

## 1. Why Is Database Authorization Part of Spring Cloud Task Operations?

**Spring Cloud Task** is used to run Spring Boot applications with a finite lifetime: reconciling transactions, importing files, exporting reports, or launching Spring Batch Jobs. When configured with JDBC, the framework writes metadata for each run to **TaskRepository**, such as task name, start/end timestamps, exit code, and arguments.

A task might run for only a few minutes yet hold overly broad database privileges. If the task execution account is allowed to `CREATE`, `ALTER`, `DROP`, or owns every table, a configuration error or code vulnerability could alter schema structure, wipe execution history, or corrupt business data.

Consider a `daily-close-task` that runs every night:

- It **needs** to insert a new TaskExecution and update its status when finished.
- It may **need** to write daily closing results into a business schema.
- It **does not need** to recreate metadata tables on every startup.
- It **should not** have privileges to make DDL changes across the entire database.
- Operators reading task history **do not necessarily** have permission to read every command-line argument, because arguments may contain sensitive data.

The solution is to separate **runtime operational privileges**, **schema/migration management privileges**, **monitoring read privileges**, and **business data access privileges**.

> **Core Principle:** the task process should only be granted privileges for operations it must perform at runtime. Creating, upgrading, or dropping tables should be a controlled deployment step, separate from the task runner account's privileges.

This lesson uses **PostgreSQL** as the primary example. Syntax for `GRANT`, `ALTER DEFAULT PRIVILEGES`, schemas, and sequences cannot be copied verbatim to MySQL, SQL Server, or Oracle; you must adapt it to your RDBMS and your project's Spring Cloud Task DDL version.

## 2. Defining Boundaries Between TaskRepository, JobRepository, and Business Schemas

An application may use one or multiple DataSources:

~~~mermaid
flowchart TD
    S["Scheduler / Kubernetes Job"] --> T["Spring Cloud Task JVM"]
    T --> C["TaskRepository"]
    T --> B["Spring Batch JobRepository (if any)"]
    T --> D["Business DB"]
    C --> CM["Schema task_meta: TASK_*"]
    B --> BM["Schema batch_meta: BATCH_*"]
    D --> DM["Schema finance: business tables"]
    M["Migration Job / CI-CD"] --> CM
    M --> BM
    M --> DM
    O["Monitoring / TaskExplorer"] --> CM
~~~

| Scope | Typical Objects | What is the account used for? | Need DDL privileges at runtime? |
|---|---|---|---|
| **TaskRepository** | `TASK_EXECUTION`, `TASK_EXECUTION_PARAMS`, `TASK_TASK_BATCH`, `TASK_LOCK` | Store and query run statuses | No, once schema is migrated |
| **Spring Batch JobRepository** | `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION`, contexts, sequences | Manage Job/Step/checkpoint/restart | No, once schema is migrated |
| **Business schema** | `finance.daily_close`, invoices, transactions | Process business data | Usually no |
| **Migration metadata** | Flyway or Liquibase history tables | Track which migrations were applied | Managed by the migration process |
| **Monitoring** | Metadata views or queries | Observability, reporting, incident investigation | No |

**TaskRepository is not JobRepository.** Granting privileges on `TASK_*` does not automatically grant privileges on `BATCH_*`. If a task uses Spring Batch, Batch runtime privileges must be reviewed separately. If a single JDBC user is used for all three groups, that user holds the **union of all privileges**; restrict by schema and separate DataSources when higher security is required.

Table names here follow common metadata schema examples. **Always cross-check the DDL packaged with your running Spring Cloud Task/Spring Batch version**, especially if you customized `tablePrefix`, schema, or ID generation mechanisms.

## 3. Role Separation: Migration, Runtime, Monitoring, and Administration

Recommended model:

| Role | What it can do | What it should NOT have |
|---|---|---|
| `task_migrator` | Create/alter metadata schemas, create tables/sequences/indexes, upgrade DDL | Superuser privileges or modifying schemas outside its scope |
| `task_runtime` | Read/write TaskRepository metadata for framework operations | `CREATE` on schema, `DROP`/`ALTER` objects, `GRANT OPTION` |
| `task_observer` | Read selected tables or views for observability | `INSERT`, `UPDATE`, `DELETE`, reading unnecessary sensitive data |
| `batch_runtime` | DML and sequences required for JobRepository | DDL on Batch schema |
| `business_runtime` | Specific granted business operations | DDL or access across other tenants/schemas |
| DBA / platform administrator | Manage roles, backups, restores, and high-level privileges | Do not use as routine application credentials |

At small scale, `task_runtime` and `business_runtime` may be a single login scoped to two restricted schemas. Still, separating accounts/connections reduces the blast radius if one service leaks credentials or runs unexpected SQL.

**Do not confuse an owner account with a runtime account.** In PostgreSQL, an object owner can alter or drop objects by ownership even without explicit DML `GRANT`s. Therefore, metadata tables should be created by the migration/schema owner role, **not** `task_runtime`.

## 4. What Privileges Does TaskRepository Actually Use?

Spring Cloud Task typically needs to create a TaskExecution on startup, write arguments, update final status, and read metadata for querying/fetching current state. When integration features are enabled, it may also access association and lock tables.

| Object | Purpose | Runtime privileges typically needed |
|---|---|---|
| `TASK_EXECUTION` | Record for a single task run | `SELECT`, `INSERT`, `UPDATE` |
| `TASK_EXECUTION_PARAMS` | Arguments for the run | `SELECT`, `INSERT` |
| `TASK_TASK_BATCH` | Links TaskExecution to Batch JobExecution | `SELECT`, `INSERT` when integration is used |
| `TASK_LOCK` | Supports single-instance/locking mode | `SELECT`, `INSERT`, `UPDATE`, `DELETE` depending on implementation |
| `TASK_SEQ` or equivalent ID generator | Allocates TaskExecution IDs | Depends on **table vs. native sequence** in DDL |
| `BATCH_*` tables and Batch sequences | Job/Step metadata | **Separate** privilege set for Batch repository |

This table is a **review checklist**, not an absolute privilege matrix for every release. For example, a `TaskRepository` implementation might use different SQL or have a metadata cleanup feature requiring `DELETE`. Determine required privileges from **actual runtime behavior and version DDL**, instead of granting `ALL PRIVILEGES` out of convenience.

### Real Sequences vs. Sequence-Emulating Tables

This is a critical distinction:

- For a **PostgreSQL native sequence** (an object with `relkind='S'`), calling `nextval(...)` typically requires `USAGE` or `UPDATE` on the sequence, not `INSERT` on a table.
- For a **sequence-emulating table** (for instance `TASK_SEQ` as a table, `relkind='r'`), the framework may run `SELECT`/`UPDATE` on the table to increment IDs; `GRANT USAGE ON SEQUENCE` will not work.
- Some Spring Cloud Task DDLs use a **sequence table**; documentation also describes variants using native sequences on certain databases. Never guess the object type solely from a `_SEQ` suffix.

`SELECT`, `USAGE`, and `UPDATE` on a sequence are not completely equivalent. Avoid granting `ALL` on a sequence if only `nextval` is needed; expand privileges only after inspecting how the JDBC incrementer behaves.

## 5. Inspect Schemas and Object Types Before Granting Privileges

Before writing `GRANT` statements, use a DBA/migrator account to verify the exact existing structure:

~~~sql
-- PostgreSQL: list objects in the TaskRepository schema.
SELECT
    n.nspname AS schema_name,
    c.relname AS object_name,
    c.relkind AS object_kind,
    pg_get_userbyid(c.relowner) AS owner_name
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'task_meta'
ORDER BY c.relname;
~~~

Common `relkind` values:

| Value | Object Type |
|---|---|
| `r` | Ordinary table |
| `S` | Sequence |
| `v` | View |
| `m` | Materialized view |
| `p` | Partitioned table |

For example, if `task_seq` has `relkind='r'`, apply **table privileges**. If it has `relkind='S'`, apply **sequence privileges**. If the object is missing, DDL may not have run yet, a different prefix may be in use, or the connection may be pointing at the wrong schema.

### Checking Current Account and Search Path

~~~sql
SELECT current_database() AS db_name,
       current_user AS db_user,
       current_schema() AS active_schema;

SHOW search_path;

SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 'task_meta'
ORDER BY table_name;
~~~

Note that PostgreSQL folds **unquoted** object identifiers to lowercase: `TASK_EXECUTION` in SQL usually maps to `task_execution`. If migrations created names using double quotes, such as `"TASK_EXECUTION"`, all access must match that exact casing. Never work around privilege errors by arbitrarily renaming tables at runtime.

## 6. PostgreSQL Example: Creating Dedicated Roles and Schema

Suppose the database is `appdb` and Task metadata lives in schema `task_meta`. A database administrator sets up the roles and schema:

~~~sql
-- Run as an admin role authorized to create roles/schemas.
-- Never store real passwords in migrations or documentation.
CREATE ROLE task_migrator LOGIN;
CREATE ROLE task_runtime LOGIN;
CREATE ROLE task_observer LOGIN;

GRANT CONNECT ON DATABASE appdb
    TO task_migrator, task_runtime, task_observer;

CREATE SCHEMA task_meta AUTHORIZATION task_migrator;

REVOKE ALL ON SCHEMA task_meta FROM PUBLIC;

GRANT USAGE ON SCHEMA task_meta TO task_runtime;
GRANT USAGE ON SCHEMA task_meta TO task_observer;
~~~

**This is a role model, not an unchecked copy-paste production script.** In real deployments, roles may already exist; authentication should use a secret manager/IAM/DB platform mechanism. `CREATE ROLE ... LOGIN` omits passwords directly in this example. If network policy or auth mechanisms require credentials, create and deliver them through a separate secure workflow.

Key takeaways:

- `USAGE ON SCHEMA` allows referencing objects inside the schema **when object privileges are also held**; it does not grant `SELECT`/`INSERT` on tables by itself.
- `CREATE ON SCHEMA` allows creating new objects; **do not grant it** to `task_runtime`.
- Role `task_migrator` owns the schema and runs DDL in the migration job; never put that credential into a worker task.
- `GRANT CONNECT` may not isolate connectivity if `CONNECT` remains granted to `PUBLIC` by default. If policy requires only specific roles to connect, a DBA must audit and adjust database-wide grants carefully to avoid breaking other applications with `REVOKE`.
- Also inspect `TEMP` privileges, the `public` schema, and other schemas on `search_path` if strict isolation is required.

## 7. Granting Per-Table TaskRepository DML After Migration

**Schema/DDL creation must finish first**, before granting runtime privileges. The statements below assume the corresponding tables were created in `task_meta`. If a feature is unused or the DDL omits a table, **skip the corresponding GRANT**; never create an empty dummy table just to make a `GRANT` succeed.

~~~sql
-- Core privileges for the TaskExecution lifecycle.
GRANT SELECT, INSERT, UPDATE
ON TABLE task_meta.task_execution
TO task_runtime;

GRANT SELECT, INSERT
ON TABLE task_meta.task_execution_params
TO task_runtime;

-- Only if Task-Batch integration uses the association table.
GRANT SELECT, INSERT
ON TABLE task_meta.task_task_batch
TO task_runtime;

-- Only if schema/single-instance feature uses TASK_LOCK.
GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLE task_meta.task_lock
TO task_runtime;
~~~

If runtime also handles metadata purging/cleanup or uses a DAO version with different SQL, verify and grant **only the privileges actually required**, rather than defaulting to `DELETE ON ALL TABLES` to avoid errors.

### When TASK_SEQ Is a Table

~~~sql
-- Run ONLY if task_meta.task_seq is an ordinary table (relkind='r').
-- Final privileges must match the actual incrementer SQL.
GRANT SELECT, UPDATE
ON TABLE task_meta.task_seq
TO task_runtime;
~~~

If an implementation uses `INSERT` during runtime ID initialization/increment, review the initializer design and grant accordingly. When separating migration from runtime, sequence tables should be **seeded beforehand** by migrations.

### When TASK_SEQ Is a Native Sequence

~~~sql
-- Run ONLY if task_meta.task_seq is a sequence (relkind='S').
GRANT USAGE
ON SEQUENCE task_meta.task_seq
TO task_runtime;
~~~

Never run both `GRANT` statements for the same object name: within a schema, an object cannot be both an ordinary table and a sequence. If the framework uses `SELECT` or `setval`, required privileges may differ; verify your version and run a smoke test with the runtime role itself.

### Observer Privileges

~~~sql
-- Allow basic status monitoring.
GRANT SELECT
ON TABLE task_meta.task_execution
TO task_observer;
~~~

`TASK_EXECUTION_PARAMS` may contain **raw task arguments**. Do not automatically grant `SELECT` on this table to everyone who views a dashboard. Create a **column-restricted view** or an authorized `TaskExplorer` service to control what data is exposed.

## 8. ALTER DEFAULT PRIVILEGES: Applying to Future Tables

New migrations may create additional indexes, tables, or sequences. Current `GRANT` statements **do not automatically apply** to objects created later.

PostgreSQL provides `ALTER DEFAULT PRIVILEGES` to set default permissions for objects **created in the future by a specific role**:

~~~sql
-- Run as task_migrator or a role authorized to manage that role.
ALTER DEFAULT PRIVILEGES
FOR ROLE task_migrator
IN SCHEMA task_meta
GRANT SELECT, INSERT, UPDATE
ON TABLES TO task_runtime;

ALTER DEFAULT PRIVILEGES
FOR ROLE task_migrator
IN SCHEMA task_meta
GRANT USAGE
ON SEQUENCES TO task_runtime;
~~~

This is a **schema-scoped default privilege example**, convenient for organizations where new metadata tables need similar read/write access. It can be broader than the minimum needed per table. Under strict least privilege, it is better to **write explicit per-object GRANTs in each migration** and verify automatically after deployment.

Two common misconceptions:

1. `ALTER DEFAULT PRIVILEGES` affects only **objects created in the future**, not existing tables; existing `GRANT`s must still be applied separately.
2. It applies to objects created by **the specified role** in PostgreSQL's session context. If migrations run under another role, `FOR ROLE task_migrator` will not trigger automatically. Check actual `current_user` when DDL executes.

Never grant default `ALL PRIVILEGES` to runtime; in particular avoid `TRUNCATE`, `REFERENCES`, `TRIGGER`, or privileges that expand blast radius without proven need.

## 9. Separating DDL/Migration from Task Application Startup

Spring Cloud Task can initialize metadata schemas at startup depending on configuration and platform support. However, if the runtime role lacks `CREATE TABLE`, a startup attempt to run DDL will fail, **even if all DML privileges are completely correct**.

When schemas are managed externally via Flyway, Liquibase, or a DBA, typical configuration is:

~~~yaml
spring:
  main:
    web-application-type: none
  application:
    name: daily-close-task

  datasource:
    url: ${TASK_DB_URL}
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}

  cloud:
    task:
      name: daily-close-task
      initialize-enabled: false
~~~

`${TASK_DB_URL}`, `${TASK_DB_USER}`, and `${TASK_DB_PASSWORD}` in this example represent Spring property placeholders: runtime must provide variables via secrets/environment per infrastructure standards.

**`spring.cloud.task.initialize-enabled=false`** disables TaskRepository schema initialization managed by Spring Cloud Task in supported release lines. When set, your project is responsible for **creating all tables/sequences/indexes before the task runs**.

If using Spring Batch or other SQL auto-initialization, configure them separately:

~~~properties
spring.batch.jdbc.initialize-schema=never
spring.sql.init.mode=never
~~~

These are common Spring Boot properties in supported versions. `spring.batch.jdbc.initialize-schema=never` disables **Batch** schema initialization and does not directly affect the Spring Cloud Task initializer. `spring.sql.init.mode=never` controls the generic SQL initializer and does not replace migration tool configuration.

If Flyway/Liquibase runs **inside the same runtime JVM** while pointing at the schema with a DML-only user, the app will still fail on startup. For clean privilege separation, use a **dedicated migration job** executed beforehand, or a dedicated migration datasource with controlled credentials that are never exposed to the runtime task.

## 10. Safe Deployment Pipeline: Migrate First, Run Task Later

A sound CI/CD workflow:

~~~mermaid
sequenceDiagram
    participant P as CI/CD Pipeline
    participant M as Migration Job
    participant DB as PostgreSQL
    participant T as Runtime Spring Cloud Task
    participant S as Scheduler / Job Controller

    P->>DB: Check version + backup/restore plan
    P->>M: Launch with task_migrator
    M->>DB: DDL + schema history + GRANT
    DB-->>M: Migration committed successfully
    M-->>P: Exit 0
    P->>S: Enable new task version execution
    S->>T: Launch with task_runtime
    T->>DB: TaskRepository DML + granted business data
    DB-->>T: Result
    T-->>S: Exit code, task lifecycle
~~~

**Security benefits of splitting into two steps:**

- If a runtime pod is compromised, the attacker has no migration credentials to `ALTER` or `DROP` tables.
- Schema upgrades can be reviewed, versioned, and rolled out sequentially.
- Multiple concurrently starting tasks will not race to create metadata tables.
- Newly granted privileges can be verified by a smoke test before re-enabling the scheduler.
- Application rollback does not automatically mean DDL rollback; data compatibility and backup plans are required.

You can manage migrations with Flyway or Liquibase, though you **do not need** both. Especially when multiple services share a metadata schema, only one workflow should own DDL to avoid conflicts and drift.

### Do Not Run Migrations via Each Task's Startup Hook

Do not place `CREATE TABLE IF NOT EXISTS` or `ALTER TABLE` inside a task's `ApplicationRunner`. Besides forcing runtime to hold DDL privileges, multiple replicas or Job retries can execute concurrently and cause races and schema errors. DDL should be managed centrally; the task should only verify dependencies are ready.

## 11. Schema and tablePrefix Configuration Must Match DDL

A frequent mistake: tables actually reside in `task_meta` while runtime looks in `public`, or DDL uses a prefix different from the SQL generated by TaskRepository.

Spring Cloud Task provides **`spring.cloud.task.tablePrefix`** (often also written in Spring Boot relaxed binding as `spring.cloud.task.table-prefix`) to override the default `TASK_` prefix. Before applying it, verify exactly how schema/table names are concatenated in your target version.

For example, if using PostgreSQL schema `task_meta` and standard unquoted table names:

~~~yaml
spring:
  cloud:
    task:
      initialize-enabled: false
      table-prefix: task_meta.TASK_
~~~

The illustrative goal is for runtime to generate SQL referencing `task_meta.TASK_EXECUTION`. **Do not assume** schema-prefixed `table-prefix` works identically across all custom `TaskConfigurer` setups, SQL generators, or versions; verify the actual SQL and corresponding migrations.

An alternative is keeping the `TASK_` prefix and configuring the JDBC connection to use `task_meta` as its default schema, for example:

~~~properties
spring.datasource.url=jdbc:postgresql://db.internal:5432/appdb?currentSchema=task_meta
spring.cloud.task.initialize-enabled=false
~~~

If using this approach, operators must verify the **effective `search_path`** and which DataSource TaskRepository actually uses. Never randomly combine a schema-qualified prefix, `currentSchema`, and `search_path` and end up with a double-qualified schema reference.

### `search_path` Risks

In PostgreSQL, placing a schema where untrusted roles can `CREATE` objects ahead of the intended schema in `search_path` creates security risks when resolving unqualified names. For task runtimes:

- Include only **trusted** schemas in the search path.
- Never grant `CREATE` on metadata schemas to runtime.
- Audit `public` schema policies per database version/upgrade.
- Prefer schema-qualified object names in administrative scripts.
- Separate tenants/schemas if isolation requires it; never rely on `search_path` as your sole authorization boundary.

## 12. With Spring Batch: Independent JobRepository Privileges

A task may run a Spring Batch Job to process millions of records in chunks. Spring Batch stores Job/Step metadata and `ExecutionContext` in `BATCH_*` tables, which may require `SELECT`, `INSERT`, `UPDATE`, and privileges on ID allocation objects.

Example of schema separation:

~~~text
appdb
├── task_meta    -> task_runtime, task_migrator
├── batch_meta   -> batch_runtime, batch_migrator
└── finance      -> finance_runtime, finance_migrator
~~~

A migration for `batch_meta` must use the **matching Spring Batch DDL**. For PostgreSQL, the DDL typically includes native sequences such as:

~~~text
BATCH_JOB_INSTANCE_SEQ
BATCH_JOB_EXECUTION_SEQ
BATCH_STEP_EXECUTION_SEQ
~~~

These are reference names; check the actual script since names/versions can differ. When native sequences are used, `batch_runtime` requires the corresponding sequence privileges, usually `USAGE` for `nextval`. Missing sequence privileges can stop a job from launching even when `BATCH_JOB_INSTANCE` and `BATCH_JOB_EXECUTION` already have DML grants.

Do not grant `ALL PRIVILEGES ON ALL TABLES IN SCHEMA batch_meta` just because a Step needs to write business data. Separate clearly:

- Batch metadata privileges for JobRepository.
- Business writer/reader privileges for tables processed by Steps.
- Schema/DDL management privileges for the migration role.
- Read-only observer privileges for dashboards, if any.

With multiple DataSources and transaction managers, configure the application so **TaskRepository uses the Task DataSource**, JobRepository uses the Batch DataSource, and business services use their respective transaction manager. `@Transactional` will not automatically pick the right repository across multiple transaction managers unless configuration is explicit.

## 13. Delete and Metadata Cleanup Privileges: Never Grant by Default to Runtime

Task and Batch metadata can grow quickly under frequent schedules. You need **retention, archiving, and cleanup** policies, yet you should not grant broad `DELETE` privileges to every task.

Separate roles:

| Activity | Typical Role |
|---|---|
| Create TaskExecution and update outcome | `task_runtime` |
| Purge/archive expired metadata | `task_maintenance` or controlled maintenance job |
| Analyze execution history | `task_observer`, read-only views/services |
| Create indexes, alter columns, or clean schema | `task_migrator` |
| Backup/restore/modify permissions | DBA / platform administrator |

With Spring Batch, arbitrarily deleting `JobInstance` or `ExecutionContext` can break the ability to **restart failed Jobs**. With TaskRepository, deleting still-running TaskExecutions or association tables can destroy audit trails. Cleanup therefore needs a formal workflow, age/status conditions, backups, and referential integrity checks.

**`DELETE` may still be needed on `TASK_LOCK` when using single-instance mode**, since that is a runtime locking mechanism; this **does not mean** granting `DELETE` on the entire `TASK_EXECUTION` history.

## 14. Risk of Data Exposure via TaskExecutionParams and Errors

`TASK_EXECUTION_PARAMS` records the arguments a task receives. If launched as:

~~~bash
java -jar daily-close-task.jar \
  --date=2026-11-23 \
  --api-token=THIS_IS_NOT_A_REAL_TOKEN
~~~

The `--api-token=...` argument can appear in process arguments, TaskRepository, logs, or orchestrators. **Never pass secrets this way**, even when database permissions are tightly configured.

Use environment variables / a secret manager instead:

~~~yaml
spring:
  datasource:
    url: ${TASK_DB_URL}
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}

partner:
  api:
    token: ${PARTNER_API_TOKEN}
~~~

Deployment configuration must provide these variables and enforce proper secret read permissions. Avoid dumping Spring Environment, full CLI args, or stack traces containing credentials into widely readable places.

Beyond arguments, `TASK_EXECUTION.ERROR_MESSAGE` can hold error messages and stack traces, including SQL, hostnames, or filenames. Even an observer role `task_observer` with read-only access to `TASK_EXECUTION` must still be governed by security and retention rules.

When dashboards serve multiple teams:

- Create views that omit `ERROR_MESSAGE` or sanitize sensitive content.
- Consider restricting access to `TASK_EXECUTION_PARAMS`.
- Enforce team/tenant authorization in the observability service layer if multiple tenants share metadata.
- Use audit logs to record who read/changed permissions or purged metadata.

## 15. Verify Effective Privileges Using the Runtime Account Itself

Do not just read the migration's `GRANT` statements: **test access as the actual runtime role** in an environment with the proper schema.

### Checking Catalog Privileges with SQL

~~~sql
SELECT current_user, current_database(), current_schema();

SELECT
    has_schema_privilege(
        current_user, 'task_meta', 'USAGE') AS can_use_schema,
    has_schema_privilege(
        current_user, 'task_meta', 'CREATE') AS can_create_schema_object;

SELECT
    has_table_privilege(
        current_user, 'task_meta.task_execution', 'SELECT') AS can_select,
    has_table_privilege(
        current_user, 'task_meta.task_execution', 'INSERT') AS can_insert,
    has_table_privilege(
        current_user, 'task_meta.task_execution', 'UPDATE') AS can_update,
    has_table_privilege(
        current_user, 'task_meta.task_execution', 'DELETE') AS can_delete;
~~~

Expected results in the runtime metadata model: `USAGE=true`, `CREATE=false`; `SELECT/INSERT/UPDATE=true` on `task_execution`, and `DELETE=false` if the app does not need to purge history.

Check the sequence if it is genuinely a PostgreSQL native sequence:

~~~sql
SELECT has_sequence_privilege(
    current_user, 'task_meta.task_seq', 'USAGE'
) AS can_nextval;
~~~

This query **will not work if `task_seq` is a table**; in that case use `has_table_privilege(...)` to check `SELECT`/`UPDATE`. Adjust table/sequence names if your actual DDL uses a different prefix.

### Positive and Negative Smoke Tests

1. **Positive:** run a test task as `task_runtime`, confirming a TaskExecution starts and finishes, obtains an ID, and records needed arguments.
2. **Positive:** if using TaskBatch integration or single-instance mode, exercise those code paths to verify privileges on auxiliary tables.
3. **Negative:** confirm `task_runtime` **lacks `CREATE` privilege** on the schema, owns no tables, and is not a member of migration/DB admin groups.
4. **Negative:** the observer account cannot update `TASK_EXECUTION` or inspect sensitive tables beyond its scope.
5. **Positive:** the migration job has privileges to alter the schema, and runtime privileges continue working after migration.
6. **Consistency:** test both **success** and **exception** paths, because `UPDATE` privileges when recording final state might remain untested if only startup was checked.

**Never run destructive DDL tests in production**. Use catalog checks or an isolated staging environment. For negative tests, check memberships/privileges via catalog functions rather than trying `DROP TABLE` just to “see if it gets rejected.”

## 16. Safe Verification Pipeline Pattern Before Enabling the Scheduler

~~~mermaid
flowchart TD
    A["Prepare version + schema migration"] --> B["Run migration as task_migrator"]
    B --> C{"Migration succeeded?"}
    C -- "No" --> X["Halt release, troubleshoot"]
    C -- "Yes" --> D["Inspect objects, owners, and grants"]
    D --> E{"Runtime has needed DML + ID privileges?"}
    E -- "No" --> X
    E -- "Yes" --> F["Smoke test task as task_runtime"]
    F --> G{"Task lifecycle recorded properly?"}
    G -- "No" --> X
    G -- "Yes" --> H["Verify missing DDL rights and observer scope"]
    H --> I{"Least-privilege satisfied?"}
    I -- "No" --> X
    I -- "Yes" --> J["Allow Scheduler/Job to run in production"]
~~~

A release should record an audit trail:

- Migration file hashes/versions and schema version.
- Verified list of objects, owners, and DML/sequence privileges.
- Artifact version of Spring Cloud Task (and Spring Batch if applicable).
- Smoke test `TaskExecutionId` result from the test run.
- Details of credential/role/secret changes if any.
- Application rollback plan, backup restoration, and handling for irreversible migrations.

If incompatible DDL changes occur while two task versions run concurrently, apply an **expand/migrate/contract** strategy or pause the scheduler during the upgrade. “Migration succeeded” does not prove older running workers can still operate.

## 17. Common Errors and Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `permission denied for schema task_meta` | `USAGE` not granted to runtime | `GRANT USAGE ON SCHEMA` and verify role/search_path |
| `permission denied for table task_execution` | Missing `INSERT`/`UPDATE`/`SELECT` on the right object | Verify DML grants and TaskRepository's DataSource |
| `permission denied for sequence task_seq` | `TASK_SEQ` is a native sequence and role lacks `USAGE` | Check `relkind` and grant on the sequence |
| `permission denied for table task_seq` | `TASK_SEQ` is a sequence-emulating table | Grant `SELECT/UPDATE` per incrementer SQL |
| `relation task_execution does not exist` | Wrong schema, prefix, search_path, or DDL hasn't run | Catalog check, JDBC currentSchema, migration logs |
| Runtime attempts `CREATE TABLE` | Task schema initialization still enabled | Disable `spring.cloud.task.initialize-enabled` when DDL is managed externally |
| Flyway reports missing CREATE/ALTER privilege | Migration running as `task_runtime` | Run migration job as `task_migrator` |
| Task starts but cannot finalize status | Has `INSERT` but lacks `UPDATE`, or DB disconnected on exit | Smoke test both success and failure terminations |
| Only Batch Job hits permission errors | `BATCH_*` differs from `TASK_*`, or Batch sequences lack grants | Inspect JobRepository/Step privileges separately |
| Single-instance fails to write lock | Missing privileges on `TASK_LOCK` | Check lock table grants and schema per release |
| Permissions vanish after a new migration | New objects lack GRANTs or were created by a different owner | Include per-migration GRANTs or verify default privileges |
| Runtime can drop tables despite no visible GRANT | Runtime is owner or member of a privileged role | Check ownership/memberships, not just ACLs |
| Logs or TaskExplorer expose tokens | Secrets passed via CLI and broad `TASK_EXECUTION_PARAMS` access | Move to secret manager and restrict SELECT |
| Task works in staging but fails in production | Differing DDL, schema, search_path, role, or datasource | Compare migration versions and `current_user`/`current_schema` |
| `GRANT ALL TABLES` works but is too broad | Schema mixes metadata and business tables | Separate schemas and grant per object |

### Investigation Sequence

1. Identify the **actual connecting account** via `current_user` and which DataSource the framework is using.
2. Check the error message: `schema`, `table`, or `sequence`, to avoid fixing the wrong object type.
3. Verify the object via `pg_class`, owner, schema, and prefix.
4. Check both `USAGE` on the schema **and** DML on the object.
5. Check whether an initializer/migration is attempting DDL when runtime has been stripped of DDL rights.
6. Run a smoke test as the runtime role to confirm startup and final status recording.
7. Never “quick-fix” with `GRANT ALL ON DATABASE` or by promoting runtime to owner/superuser.

## 18. Privileges in Multi-Tenant, Multi-Cluster, and Concurrent Task Environments

Database authorization must also consider data access boundaries:

- **Multiple tenants in one database:** `tenant_id` in SQL alone does not enforce security. You may need PostgreSQL Row-Level Security, separate schemas, separate accounts, or service-layer policies; verify runtime users cannot bypass policies.
- **Multiple clusters writing to the same TaskRepository:** schedulers can insert multiple TaskExecutions into one store; ensure ID allocators, transactions, and lock tables match the DDL properly.
- **Read-only vs. write-heavy tasks:** avoid sharing one broad credential across every task when roles can be split by workload group.
- **Tasks handling sensitive data:** place TaskRepository in a dedicated schema, with backups and logs governed by retention, encryption at rest, and TLS in transit per organizational policy.
- **Remote partitioning / Spring Batch:** manager and workers must access the same JobRepository (when designed that way), without needing identical permissions across the entire business DB.
- **Repeatedly launched Jobs:** runtime credentials may be cached across many Pods; during credential rotation, plan for in-flight tasks, connection pools, and new Jobs.

**DB authorization does not replace idempotency.** A worker with legitimate `INSERT` privileges can still write duplicate records if the application lacks business keys/unique constraints and proper retry/concurrency handling.

## 19. Hands-On Exercise: Verifying Runtime and Migration Privileges

### Objective

Deploy a `daily-close-task` with no web server, using PostgreSQL to store TaskExecution. The runtime account performs only DML while the migrator manages schemas; allow testing missing-privilege errors without granting broad permissions.

### Steps

1. **Pin versions:** lock compatible Spring Boot and Spring Cloud Task versions; obtain the PostgreSQL TaskRepository DDL for that exact release.
2. **Prepare two roles:** `task_migrator` and `task_runtime`. Provision credentials via a secret manager; never commit passwords to the repository.
3. **Create a dedicated schema:** `task_meta` owned by migrator; grant only `USAGE` to runtime.
4. **Run migrations:** create tables/sequences/indexes matching the DDL and prefix; confirm the object owner is not runtime.
5. **Apply targeted GRANTs:** `SELECT/INSERT/UPDATE` on `TASK_EXECUTION`, params table grants, lock/batch integration grants when actually used, and ID allocation grants matching the true `TASK_SEQ` object type.
6. **Disable startup initialization:** set `spring.cloud.task.initialize-enabled=false`, and disable other initializers when schemas are externally managed.
7. **Configure the runtime DataSource:** use `task_runtime`, an explicit `search_path`/schema, and a small pool.
8. **Run a successful task:** verify a new TaskExecution is created with `END_TIME`, exit code, and arguments saved properly.
9. **Run an intentional failure task:** have the runner throw an exception and verify TaskRepository still records error metadata if the lifecycle functions properly.
10. **Test a missing-privilege configuration in staging:** for example omit `UPDATE`; observe the error when finalizing TaskExecution, then restore the exact object `GRANT`.
11. **Verify observer:** read granted views/tables and confirm no write/delete privileges on history.
12. **Run a new migration version:** verify default/per-object `GRANT`s on new objects and smoke test after upgrading.
13. **If using Spring Batch:** add `batch_meta` and verify Job launch/restart sequences with appropriate Batch privileges.
14. **Audit data safety:** verify TaskExecutionParams, logs, and secrets contain no passwords or tokens.

| Check | Expected |
|---|---|
| `task_runtime` has schema `USAGE` | Yes |
| `task_runtime` has schema `CREATE` | **No** |
| `task_runtime` owns TaskRepository tables | **No** |
| `TASK_EXECUTION` has required lifecycle DML | Yes |
| `TASK_SEQ` granted according to actual object type | Yes |
| Startup does not auto-create DDL | Yes |
| TaskExecution records start/end of a run | Yes |
| `task_observer` reads only authorized data | Yes |
| Migrations use a dedicated role | Yes |
| No passwords in args/logs/metadata | Yes |

## 20. Production Checklist and Conclusion

- Use a **least-privilege runtime role**; never run tasks as superuser or schema owner.
- **Separate the migration role** and DDL pipeline from short-lived task JVMs.
- **Verify DDL by Spring Cloud Task version** before granting privileges.
- Ensure `USAGE ON SCHEMA`, exact table DML, and proper sequence/ID-table privileges.
- Never grant `CREATE` on metadata schemas, `DROP`/`ALTER` on objects, or `GRANT OPTION` to runtime.
- Disable auto-initialization when schemas are managed by external migrations.
- Verify `tablePrefix`, DataSource, and `search_path` match the actual schema.
- For Spring Batch, grant JobRepository privileges separately; never confuse `TASK_*` with `BATCH_*`.
- Use `ALTER DEFAULT PRIVILEGES` or controlled per-migration `GRANT`s; remember the difference between existing and future objects.
- Separate maintenance/cleanup accounts from task runtime wherever possible.
- Restrict access to `TASK_EXECUTION_PARAMS` and `ERROR_MESSAGE`; never pass credentials via CLI.
- Protect the database with TLS, secret rotation, RBAC, backups, retention, and environment-appropriate auditing.
- Run **smoke tests as the actual runtime role**, covering success, failure, sequences, and optional features.
- Enforce multi-tenant authorization and business idempotency beyond SQL privileges.
- Ensure rollbacks/upgrades do not break permissions or Spring Batch Job restartability.

**Conclusion:** For Spring Cloud Task, proper database authorization is more than allowing the app to connect. You must separate **the TaskRepository runtime account** from **the schema management account**, grant DML and ID allocation privileges based on the actual DDL, and restrict who can read metadata that might hold sensitive arguments or errors. With versioned schemas, separate migrations, and runtime-role verification after each upgrade, finite tasks become much safer to operate—even when scheduled, retried, or integrated with Spring Batch.

### References

- [Spring Cloud Task — Features: DataSource, tablePrefix, and schema initialization](https://docs.spring.io/spring-cloud-task/reference/features.html)
- [Spring Cloud Task — TaskRepository Schema Appendix](https://docs.spring.io/spring-cloud-task/docs/current/reference/html/appendix-task-repository-schema.html)
- [Spring Batch — Metadata Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html)
- [PostgreSQL — Privileges](https://www.postgresql.org/docs/current/ddl-priv.html)
- [PostgreSQL — GRANT](https://www.postgresql.org/docs/current/sql-grant.html)
- [PostgreSQL — ALTER DEFAULT PRIVILEGES](https://www.postgresql.org/docs/current/sql-alterdefaultprivileges.html)
