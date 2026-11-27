# Customizing tablePrefix and Schema Names in Spring Cloud Task

## 1. Why Customize the Metadata Store?

Every time a **Spring Cloud Task** application launches, the framework can persist a **TaskExecution** record in **TaskRepository** to track the task name, start time, end time, exit code, and execution details. For finite-running applications like data imports, report exports, or scheduled jobs, this metadata repository enables run tracing, failure detection, and reconciliation with business outcomes.

In a real system, multiple applications or environments may share the same database server. If every application accesses the default metadata tables without an organizational strategy, problems arise:

- Table name collisions across applications or components sharing a single database.
- Uncertainty over which tables belong to development, testing, or production.
- Difficulty applying separate access controls, migrations, and backups to metadata.
- Changing table-name configuration causes the application to miss prior `TaskExecution` history.
- Spring Cloud Task and Spring Batch use distinct sets of metadata tables that coexist in one store, causing configuration confusion.

Two common organizational mechanisms are **`tablePrefix`** (a prefix on Spring Cloud Task metadata object names) and **schema** (a database namespace). They serve different purposes and must stay synchronized with the **actual DDL** created in the database.

## 2. Distinguishing tablePrefix, Schema, Database, and DataSource

| Concept | What Is It? | PostgreSQL Example | Role |
|---|---|---|---|
| Database | Logical database on a server | `appdb` | Fundamental connection scope |
| Schema | Namespace holding tables, sequences, indexes... inside a database | `task_meta` | Groups objects and supports access control |
| `tablePrefix` | String prepended before **metadata table name suffixes** used by the framework | `OPS_TASK_` | Renames the tables queried by the framework |
| Table | Object storing actual records | `task_meta.ops_task_execution` | Holds `TaskExecution` rows |
| DataSource | Application connection configuration | JDBC URL + user + pool | Determines where the framework connects |
| TaskRepository | Spring Cloud Task component writing/reading run history | Uses metadata tables in the chosen DataSource | Observes `TaskExecution` lifecycle |

Illustrative model:

~~~mermaid
flowchart TD
    A["Spring Cloud Task Application"] --> B["TaskRepository"]
    B --> C["DataSource: appdb / task_runner"]
    C --> D["Schema: task_meta"]
    D --> E["OPS_TASK_EXECUTION"]
    D --> F["OPS_TASK_EXECUTION_PARAMS"]
    D --> G["Other metadata tables/sequences"]
    A --> H["Business Service"]
    H --> I["Business tables and data"]
~~~

This diagram illustrates **one deployable layout**, not that Spring Cloud Task automatically creates all objects merely by setting two configuration properties.

For example, with the common default prefix **`TASK_`**, the execution table name is **`TASK_EXECUTION`**. Replacing it with **`OPS_TASK_`** yields **`OPS_TASK_EXECUTION`**. Placing these under schema **`task_meta`** resolves to **`task_meta.ops_task_execution`** in PostgreSQL when using unquoted identifiers.

Three points to remember:

1. **A prefix is not a schema.** Changing `tablePrefix` does not create a new schema.
2. **A schema is not a prefix.** Switching a connection's default schema does not alter the prefix or suffix of table names.
3. **Configuration and DDL must match.** If the repository looks for `OPS_TASK_EXECUTION` while the database only has `TASK_EXECUTION`, queries fail even if both live in the same schema.

## 3. Which Objects Are Affected by tablePrefix?

Spring Cloud Task uses a group of tables and—depending on DBMS and version—key-generation objects such as sequences or ID tables. Exact names and structures must come from the **DDL script for your deployed Spring Cloud Task version**, matched to your target database.

Familiar tables include:

| Purpose | Common Name with `TASK_` Prefix | Illustrative Name with `OPS_TASK_` Prefix |
|---|---|---|
| Application execution | `TASK_EXECUTION` | `OPS_TASK_EXECUTION` |
| Parameters attached to an execution | `TASK_EXECUTION_PARAMS` | `OPS_TASK_EXECUTION_PARAMS` |
| Task and batch job link | `TASK_TASK_BATCH` | `OPS_TASK_TASK_BATCH` |

**Rule:** The framework prepends the configured prefix to the object name suffixes it defines. Thus, to get `OPS_TASK_EXECUTION`, configure the prefix `OPS_TASK_`, not just `OPS_`. Exact table names, extra tables, and sequences still depend on schema and version.

Some databases treat identifiers as case-sensitive when enclosed in double quotes. In PostgreSQL, an **unquoted** identifier written `OPS_TASK_EXECUTION` is stored/resolved as `ops_task_execution`, whereas a table created with quoted `"OPS_TASK_EXECUTION"` is a distinct identifier. Ensure DDL and framework SQL statements follow consistent naming conventions.

> **Limitation:** `tablePrefix` configures table addressing; it is not an automatic rename, move, or data migration feature. A `TaskRepository` with a changed prefix reads a different set of tables. Old history is not automatically moved to the new tables.

## 4. Configuring table-prefix in a Spring Cloud Task Application

In Spring Cloud Task versions supporting configuration via Spring Boot properties, set the table prefix in `application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none

  application:
    name: nightly-revenue-task

  cloud:
    task:
      name: nightly-revenue-task
      table-prefix: OPS_TASK_
~~~

`spring.cloud.task.table-prefix` specifies the table-name prefix used by Spring Cloud Task infrastructure to access metadata. Spring Boot supports relaxed binding, so in matching versions a Java property like `tablePrefix` can be expressed in YAML as `table-prefix`. Verify which property syntax your **pinned dependency version** actually accepts; never assume every Spring Cloud Task branch shares identical configuration APIs.

An equivalent `application.properties` example:

~~~properties
spring.main.web-application-type=none
spring.application.name=nightly-revenue-task
spring.cloud.task.name=nightly-revenue-task
spring.cloud.task.table-prefix=OPS_TASK_
~~~

**Never vary the prefix arbitrarily per run** without also preparing the matching tables and permissions. If a CronJob launches run A with `OPS_TASK_` and run B with `TASK_`, both runs appear in **two different metadata stores** despite sharing the same task name. That causes dashboards, monitoring queries, and error handling to report incomplete data.

In complex environments, Spring Cloud Task also lets you customize repository/configurer infrastructure at the bean level according to your version's API. Use that only when properties configuration falls short, and verify DataSource selection, transaction managers, repositories, and library compatibility. For standard prefix changes, prefer consistent properties configuration.

## 5. Placing Metadata in a Dedicated Schema: PostgreSQL Example

Suppose an application uses database `appdb` and wants to place Spring Cloud Task metadata into schema `task_meta`, alongside business tables in `business`.

~~~text
PostgreSQL server
└── appdb
    ├── business
    │   ├── orders
    │   └── payments
    └── task_meta
        ├── ops_task_execution
        ├── ops_task_execution_params
        └── ... (version-specific metadata objects)
~~~

With PostgreSQL, one approach is configuring the **default schema/search path** on the JDBC connection of the DataSource used by `TaskRepository`:

~~~yaml
spring:
  main:
    web-application-type: none

  datasource:
    url: jdbc:postgresql://db.internal:5432/appdb?currentSchema=task_meta
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}

  cloud:
    task:
      name: nightly-revenue-task
      table-prefix: OPS_TASK_
~~~

The host `db.internal:5432/appdb` is only an example. `currentSchema=task_meta` is a **PostgreSQL JDBC Driver** parameter; it affects how **unqualified** object names are resolved on connections using that URL. It **does not create schema `task_meta`** and **does not rename tables**.

If the same DataSource serves business logic and Spring Batch, changing the default schema can affect unqualified queries from **every component sharing that connection**. Therefore, when strict data and privilege partitioning is needed, explicitly design which DataSource serves task metadata and which serves business/Batch; never alter a global search path without checking other repositories.

With HikariCP and drivers supporting `Connection.setSchema(...)`, some deployments also configure a pool's default schema. However, exact behavior depends on the JDBC driver, pool, settings, and versions. The `currentSchema` example above is **specific to PostgreSQL**; never copy it verbatim to MySQL, Oracle, or SQL Server.

### Creating the Schema and Granting Privileges via Migration

A dedicated migration can prepare the namespace and privileges before launching the task:

~~~sql
-- PostgreSQL example; execute with an admin/migration account.
CREATE SCHEMA IF NOT EXISTS task_meta;

-- task_runner is a pre-created runtime role.
GRANT USAGE ON SCHEMA task_meta TO task_runner;

-- After migrations create all metadata tables/sequences:
GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES IN SCHEMA task_meta TO task_runner;

GRANT USAGE, SELECT
ON ALL SEQUENCES IN SCHEMA task_meta TO task_runner;
~~~

The snippet above **does not create the TaskRepository tables yet**. You still must apply the DDL matching your Spring Cloud Task version, adapt prefixes to `OPS_TASK_`, and ensure objects are created inside `task_meta`.

Granting `ON ALL ... IN SCHEMA` applies only to objects existing when the statement executes. For future migrations, grant permissions on new objects or configure `ALTER DEFAULT PRIVILEGES` for the **role owning migration-created objects**. Avoid requiring runtime accounts to hold schema `CREATE/DROP` privileges in production when schemas are deployed via a migration pipeline.

## 6. Synchronizing Runtime Configuration with Actual DDL

Changing `spring.cloud.task.table-prefix` only changes **the table addresses the repository queries**. Creating schemas, tables, keys, indexes, and ID generators is a separate database deployment task.

A sound workflow:

~~~mermaid
flowchart TD
    A["Pin Spring Cloud Task version + database dialect"] --> B["Obtain official DDL for that exact version"]
    B --> C["Choose schema and tablePrefix"]
    C --> D["Transform DDL under review"]
    D --> E["Apply Flyway / Liquibase / DBA migration"]
    E --> F["Grant privileges to runtime user"]
    F --> G["Configure DataSource and table-prefix"]
    G --> H["Launch test task"]
    H --> I{"TaskExecution written to target table?"}
    I -- "Yes" --> J["Verify completion, parameters, monitoring queries"]
    I -- "No" --> K["Check schema, table names, sequences, privileges"]
    K --> D
~~~

**Step 1 — Identify base DDL.** Obtain the schema script bundled with your active release, matching the DBMS and key-generation method. Never create a table with just `TASK_EXECUTION_ID` and consider it done; the repository requires additional columns, constraints, and objects to function.

**Step 2 — Choose a naming strategy.** For example, `schema=task_meta` and `tablePrefix=OPS_TASK_`. Document these exact values across deployment configs, migrations, and runbooks.

**Step 3 — Apply DDL cleanly.** If the original script uses the default prefix, apply the prefix transformation consistently across table names, keys/sequences, and dependent references. Verify search-and-replace does not accidentally rename columns or unrelated objects. Review transformed SQL before running.

**Step 4 — Verify repository via real connection.** Launch a small task using the configured runtime DataSource. Confirm the repository writes to the intended schema and tables—both on normal completion and when a runner throws an exception.

**Step 5 — Put schema creation in CI/CD or migrations.** Avoid letting multiple Pods race to create tables on first launch. Auto-initialization mechanisms, if present in your version, must be reviewed carefully alongside custom prefixes/schemas. Never assume an auto-init tool automatically transforms DDL scripts for a custom prefix.

### PostgreSQL Schema Verification Example

~~~sql
-- Run against the target database using a runtime-equivalent connection.
SELECT current_database();
SELECT current_schema();
SHOW search_path;

-- Locate deployed metadata tables in the chosen schema.
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 'task_meta'
  AND table_name LIKE 'ops_task_%'
ORDER BY table_name;

-- Example history query (if this version's schema uses the table name below).
SELECT task_execution_id, task_name, start_time, end_time, exit_code
FROM task_meta.ops_task_execution
ORDER BY task_execution_id DESC
LIMIT 10;
~~~

If `information_schema` lacks the expected tables, verify that migrations ran, landed in the intended schema, the account has visibility privileges, and table names did not differ due to case sensitivity.

## 7. Organizational Strategies: Change Prefix, Change Schema, or Both?

| Approach | Example | Advantages | Limitations |
|---|---|---|---|
| Keep default prefix, separate schemas | `task_a.task_execution`, `task_b.task_execution` | Easy per-namespace permissions/backups with standard table DDL | Requires accurate schema/DataSource setup per application |
| Share schema, change prefix | `public.ops_task_execution` and `public.billing_task_execution` | Distinguishes table groups within one namespace | Does not isolate permissions or resources by itself |
| Separate both schema and prefix | `task_meta.ops_task_execution` | Clear ownership and easy visual identification | Extra config and migrations to keep synchronized |
| Separate database or DataSource | Metadata placed in `taskmeta` DB separate from business DB | Connection-, privilege-, and operations-level isolation | More complex configuration, monitoring, and backups |

No single pattern fits every system:

- **Single standalone application:** keeping default names is usually simplest.
- **Multiple applications in one database:** consider separating schemas per team/environment before inventing custom prefixes if the DBMS supports it.
- **One application running multiple task types:** they can share one `TaskRepository` table set and differentiate via `TASK_NAME` and `TASK_EXECUTION_ID`. No separate prefix per business task is needed if the goal is merely distinguishing history.
- **Strict authorization requirements:** a prefix is only a naming convention. Real DB security relies on roles, schemas, databases, and object grants.

**Important:** changing schema or prefix does not grant a “run once per day” guarantee. If two CronJobs fire on the same day, each still creates its own `TaskExecution`. Business-key idempotency, locking, or orchestration policies are still required.

## 8. When the Same Application Uses Spring Batch

Spring Cloud Task and Spring Batch frequently work together: a finite task application launches a batch job, writes data, and terminates.

Both frameworks maintain separate repositories:

| Scope | Spring Cloud Task | Spring Batch |
|---|---|---|
| Repository | `TaskRepository` | `JobRepository` |
| History | `TaskExecution`: **task application** lifecycle | `JobExecution` / `StepExecution`: jobs, steps, checkpoints |
| Familiar table set | `TASK_*` | `BATCH_*` |
| Prefix | **Spring Cloud Task** config | Separate **Spring Batch** config |
| Changing schema | Must configure corresponding namespace and connection | Must configure Batch's namespace and connection separately |

Setting `spring.cloud.task.table-prefix=OPS_TASK_` **does not simultaneously rename `BATCH_*` tables**. If Spring Batch table prefixes are customized, configure them separately per your Spring Boot/Spring Batch version, such as via `JobRepository` infrastructure or that version's configuration properties.

Example layout:

~~~text
appdb
├── task_meta
│   ├── ops_task_execution
│   ├── ops_task_execution_params
│   └── ...
├── batch_meta
│   ├── batch_job_instance
│   ├── batch_job_execution
│   └── ...
└── business
    ├── imported_orders
    └── report_exports
~~~

In this layout, `TaskRepository` and `JobRepository` may require **two separate repository/DataSource configurations**, even when targeting the same PostgreSQL database. Setting the search path on one datasource does not turn two repositories into two distinct datasources automatically. Depending on version, inspect bean configurations directly for Task/Batch DataSource selection and custom configurers.

If sharing a single schema instead of separating them, keep Task and Batch table namespaces clear to avoid mixing application run data with job/step data. When decommissioning or migrating one framework, never accidentally drop tables still serving the other.

## 9. From Config Change to Data Migration: A Migration Problem

Suppose a system currently stores history in `public.task_execution` and wants to move to `task_meta.ops_task_execution`. Changing YAML alone without migrating data causes problems:

- The new app looks for `task_meta.ops_task_execution`, which may not exist and fail at runtime.
- If new tables are created empty, old records **do not automatically appear** in the new repository.
- Dashboards and old queries may keep reading the old tables, causing skewed metrics.
- Key generators can collide if rows are copied without synchronizing sequences/identities.
- Old and new app versions running concurrently may write to two different places.

A migration plan should clarify:

1. **Goal:** separate metadata only for **new runs**, or migrate **historical data too**?
2. **Cutover window:** pause or coordinate schedules so no task processes write to the old schema during cutover. Check active tasks and runs missing `END_TIME`.
3. **Target DDL:** create exact target tables/sequences/indexes/constraints for the target version before moving data.
4. **Data and relationships:** if keeping history, copy related tables/sequences/foreign keys, preserving IDs and mappings accurately. Never copy `TASK_EXECUTION` while forgetting parameters or Batch links.
5. **ID generator:** after copying IDs, ensure the next sequence/identity value exceeds the maximum copied ID so new writes do not collide.
6. **Permissions:** apply grants for runtime, migration, monitoring, and backup roles.
7. **Update app and observability tools together:** YAML/properties, DataSources, dashboards, SQL scripts, alerts, and support runbooks.
8. **Rollback readiness:** take snapshots/backups, document how to revert to the prior deployment, and define how runs created post-cutover will be handled.

Even if history need not be carried into the new repository, **archive or back up** the old tables per retention policy rather than dropping them immediately. Changing prefix/schema is a **production data-structure change**, not a display-label tweak.

~~~mermaid
sequenceDiagram
    participant O as Operator / Migration
    participant DB as Database
    participant A as Spring Cloud Task
    participant M as Monitoring
    O->>A: Pause new launch schedules
    O->>DB: Create target schema + DDL, prepare grants
    O->>DB: Migrate data if needed, sync ID generator
    O->>A: Deploy new schema/prefix configuration
    A->>DB: Write test TaskExecution
    O->>DB: Verify target tables and status
    O->>M: Update queries / dashboards
    O->>A: Resume launch schedules
~~~

When running via Kubernetes Jobs or schedulers, also ensure **unfinished legacy jobs** follow a defined handling plan before switching target repositories. The new schema cannot automatically detect or close out `TaskExecution` records left hanging in the old schema.

## 10. Complete Example: Dedicated Metadata for a Report-Export Task

### 10.1. Objective

A `nightly-revenue-task` application running on a schedule or on demand with:

- PostgreSQL database `appdb`.
- Metadata schema: `task_meta`.
- Table prefix: `OPS_TASK_`.
- Persistent metadata for querying run history.
- Business tables potentially residing in a separate schema managed by the business service.

### 10.2. Spring Boot Configuration

~~~yaml
spring:
  main:
    web-application-type: none

  application:
    name: nightly-revenue-task

  datasource:
    url: jdbc:postgresql://db.internal:5432/appdb?currentSchema=task_meta
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}

  cloud:
    task:
      name: nightly-revenue-task
      table-prefix: OPS_TASK_
~~~

`${...}` placeholders represent environment variables supplied securely at deployment. Include the PostgreSQL driver dependency, Spring Cloud Task with compatible Spring Boot/Spring Cloud versions, datasource configuration, and **migrations that created the schema/tables before the task runs**.

### 10.3. Runner and Business Logic

~~~java
import java.time.LocalDate;
import java.util.List;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.configuration.EnableTask;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableTask
public class RevenueTaskApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
            SpringApplication.run(RevenueTaskApplication.class, args);
        System.exit(SpringApplication.exit(context));
    }

    @Bean
    ApplicationRunner revenueRunner(RevenueService service) {
        return arguments -> {
            List<String> dates = arguments.getOptionValues("date");

            if (dates == null || dates.size() != 1) {
                throw new IllegalArgumentException(
                    "Must pass --date=yyyy-MM-dd");
            }

            LocalDate date = LocalDate.parse(dates.get(0));
            // Wait for service completion, or let exceptions propagate.
            service.exportForDate(date);
        };
    }
}
~~~

`RevenueService` is a business service built by the project. Example run:

~~~bash
java -jar nightly-revenue-task.jar --date=2026-11-23
~~~

After a successful run, `TaskRepository` persists the run into the configured metadata objects. **The report output table** and export-date idempotency remain the responsibility of `RevenueService`; the repository does not store business outcomes automatically.

### 10.4. Post-Run Verification

Inspect using an account with metadata read privileges:

~~~sql
SELECT task_execution_id, task_name, start_time, end_time, exit_code
FROM task_meta.ops_task_execution
WHERE task_name = 'nightly-revenue-task'
ORDER BY task_execution_id DESC
LIMIT 5;
~~~

In environments with multiple schemas and configs, this query checks the **exact physical location**, confirming the task did not silently write to another default table set. Also inspect the parameters table and business results, test failure paths (e.g., invalid date), and verify exit codes on the orchestrator side.

## 11. Common Errors and Root-Cause Analysis

| Symptom | Possible Cause | Priority Checks |
|---|---|---|
| `relation "ops_task_execution" does not exist` | DDL missing, wrong schema/search_path, prefix mismatch, or differently quoted identifier | Query `information_schema`, `current_schema()`, actual table names |
| `permission denied for schema task_meta` | Role missing `USAGE` or object grants | Inspect `GRANT`s for schema/tables/sequences |
| ID creation error, missing sequence, or duplicate key | Wrong key/sequence script, copied data without syncing generator | Inspect dialect-correct DDL, max ID value, and allocator state |
| Task runs, yet dashboard shows “no history” | Dashboard reads old prefix/schema or another datasource | Compare connection strings and observed SQL |
| Fails only in production | Schema migrations skipped, runtime user lacks grants, or search path differs from staging | Compare migration version, grants, and effective JDBC URL |
| `TaskRepository` and `JobRepository` collide on tables | Confused Spring Task and Batch metadata namespaces | Inspect `TASK_*` vs `BATCH_*` tables and per-repository configs |
| New task starts IDs from the beginning | Pointing to a **brand-new table set** after prefix/schema change | Check migration/historical rows and target sequence |
| Multiple environments mix metadata | Sharing schema/prefix and DB or using wrong secrets | Check profiles, DataSource, roles, database, and schema |

### Concise Diagnostic Workflow

1. **Capture effective configuration safely:** dependency versions, `table-prefix`, JDBC URL with sensitive credentials masked, active profiles, and the DataSource name used by `TaskRepository`.
2. **Verify connection context:** using the same role and database, run `SELECT current_database(), current_schema()`, plus `SHOW search_path` on PostgreSQL.
3. **Cross-check DDL:** verify table names, sequences, indexes, and grants. Do not look only for `TASK_EXECUTION`.
4. **Locate a test run record:** launch a task with an easily identifiable name, then query the chosen table group directly.
5. **Compare against Batch and business config:** when multiple DataSources or profiles exist, confirm which repository uses which connection.

Avoid fixing configuration mistakes by manually running `UPDATE`/`DELETE` on `TaskRepository` data, as that can erase execution history or break links to Batch metadata. Diagnose schema/prefix mapping before intervening in data.

## 12. Pre-Production Deployment Checklist

| Question | Passing Criterion |
|---|---|
| Are Spring Cloud Task version and dialect locked? | Matching dependencies and DDL reviewed |
| Is the `tablePrefix` value consistent everywhere? | Runtime config, DDL, migrations, and monitoring use the same convention |
| Does the schema actually exist? | Created by migrations and accessed under the right namespace |
| Are runtime permissions sufficient yet minimal? | Has required DML/sequence grants without schema create/drop privileges |
| Are sequences/identities in the right state? | New `TaskExecution` writes do not collide with existing IDs post-migration |
| Are multi-DataSource components verified? | `TaskRepository`, `JobRepository`, and business logic use their intended connections |
| Tested both success and failure? | `TaskExecution` appears in target tables with accurate timestamps and exit codes |
| Is there a plan for legacy data? | Decided whether to copy, archive, or retain the old repository |
| Updated dashboards, alerts, and backups together? | No queries left pointing at the old metadata table set |
| Ready with rollback/cutover plan? | Backups taken, launch freeze window scheduled, safe recovery procedure defined |

**Conclusion:** `tablePrefix` determines **which metadata table names Spring Cloud Task accesses**, while schema determines **which database namespace the connection targets**. Customizing safely requires keeping **repository configuration, DataSources, DDL/migrations, access grants, and observability tools** synchronized. For systems running finite-lifecycle tasks, this consistency ensures `TaskRepository` records accurate history, aids debugging, supports task reruns, and lets multiple applications or environments coexist without mixing metadata.
