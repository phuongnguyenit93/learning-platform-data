# Shared Data Store, Access Permissions, and Version Compatibility

## 1. Why Does Spring Cloud Data Flow Need a Shared Data Store?

**Spring Cloud Task** supports finite-running Spring Boot applications: start up, execute business logic, update execution metadata in **`TaskRepository`**, and terminate. **Spring Cloud Data Flow (SCDF)** adds an orchestration layer: registering applications, creating task definitions, launching on demand or on schedules, tracking history, and displaying outcomes via a dashboard/API.

In the **Data Flow** chapter, this lesson answers three tightly coupled operational questions:

1. **Shared data store:** which metadata tables do the Data Flow server, task applications, and Spring Batch applications need to see?
2. **Access permissions:** who can read, who can write, who can create tables, and how are credentials passed without exposing secrets?
3. **Version compatibility:** when Data Flow, Spring Cloud Task, Spring Batch, or schemas are upgraded, how do old and new processes still understand the same data?

A common scenario: an administrator launches `daily-settlement` from the Data Flow Dashboard, the task outputs its report successfully, yet the **Task Executions** page shows no run. The cause is not necessarily a task failure; the task may be using a **private in-memory H2 database**, the wrong database/schema, a missing JDBC driver, insufficient permissions to write metadata, or an incompatible schema.

According to Spring Cloud Data Flow guides, for the system to display a task application's history, **Data Flow and the task must access the same compatible execution metadata store**. For Spring Batch jobs, job/step history must also be written to the store Data Flow is configured to query.

### Learning Objectives

After this lesson, you will be able to:

- Distinguish **Data Flow**, **Spring Cloud Task**, and **Spring Batch** metadata stores from **business databases**.
- Design DataSource connections for tasks launched by SCDF, tasks launched outside SCDF, and jobs in **Composed Task Runner**.
- Configure read/write/schema migration permissions following the **principle of least privilege**.
- Identify credential exposure risks when SCDF passes configuration down to Kubernetes Pods.
- Build a compatibility matrix across **Data Flow – Boot – Cloud Task – Batch – JDBC driver – schema**.
- Test connectivity, schemas, permissions, and migrations before upgrading production.

## 2. Data Layers That Must Not Be Conflated

A task-processing system can involve multiple data layers:

| Layer | Example Tables / Objects | Purpose |
| --- | --- | --- |
| **SCDF server metadata** | App registrations, task definitions, schedules, deployment info | Data Flow Server registers, orchestrates, and displays resources |
| **Spring Cloud Task metadata** | `TASK_EXECUTION`, `TASK_EXECUTION_PARAMS`, `TASK_SEQ`, related tables | Records the state of **each task process run** |
| **Spring Batch metadata** | `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION`, `BATCH_*_EXECUTION_CONTEXT` | Tracks jobs/steps, item counters, and restartability |
| **Business database** | `orders`, `settlements`, `report_outbox` | Stores real business outputs, business keys, custom checkpoints if any |
| **Orchestration infrastructure** | Kubernetes Job/Pod, CronJob, Cloud Foundry Task | Spawns processes, manages resources, timeouts, and exit codes |

**Sharing a metadata store does not mean sharing all business data.**

A common deployment pattern:

- Data Flow Server uses PostgreSQL `scdf_metadata` to store orchestration metadata.
- Tasks launched by the server write `TASK_EXECUTION` into the same matching metadata database/schema.
- If a task runs Spring Batch, `BATCH_*` tables also belong where SCDF/Batch can read and update them per the version's contract.
- Order processing itself still writes to a separate `business_db` database via the business DataSource and transaction manager.

If a task has **multiple DataSources**, never assume Spring Cloud Task will automatically pick the metadata store. Configure `TaskConfigurer` to bind `TaskRepository` and `TaskExplorer` to the intended DataSource, and verify that Batch's `JobRepository` uses the agreed-upon store.

~~~mermaid
flowchart TB
    U["SCDF Dashboard / Shell / REST API"] --> S["Spring Cloud Data Flow Server"]
    S --> M[("Shared Metadata DB")]
    S --> P["Task Platform / Deployer"]
    P --> A["Task A: Spring Cloud Task"]
    P --> B["Task B: Spring Cloud Task + Batch"]
    A --> M
    B --> M
    A --> BA[("Business Database")]
    B --> BA
    M --- T["TASK_*: task runs"]
    M --- J["BATCH_*: jobs and steps"]
    M --- D["SCDF metadata: definitions and orchestration"]
~~~

The diagram above is a **logical model**. Even within the same database, components can use **separate SQL accounts** scoped to needed privileges. When splitting physical schemas or databases, explicitly verify SCDF's read, write, and query capabilities for your version; never just create two tables with the same name and treat them as connected.

## 3. What Must Be Verified for "Same Database"?

Two configurations with the same hostname do not necessarily point to the same metadata set. To confirm sharing, verify:

| Item to Match | Example | Risk if Mismatched |
| --- | --- | --- |
| **DB engine** | PostgreSQL | Different driver/DDL |
| **DB host/cluster** | `metadata-db.internal:5432` | Task writes to another cluster |
| **Database name** | `scdf_metadata` | Tables share names but hold separate data |
| **Schema / `search_path`** | `public` or configured metadata schema | `TASK_EXECUTION` sits in an unread namespace |
| **Table prefix** | `TASK_`, `BATCH_` | Repository uses different table names than actual DDL |
| **Driver and protocol** | `org.postgresql.Driver`, `jdbc:postgresql:...` | Task cannot connect or fails bootstrap |
| **Effective permissions** | `SELECT`, `INSERT`, `UPDATE`, ID-generation privilege | Task fails to allocate IDs or write status |
| **Schema version** | DDL compatible with runtime | Queries/INSERTs encounter mismatched columns or types |

**SCDF 2.11 documentation explicitly notes:** when Data Flow launches a standard task, the server forwards its DataSource properties—such as `spring.datasource.url`, `driverClassName`, `username`, and `password`—to the task application. As a result, the task writes metadata to the shared store **provided** the application receives that configuration, includes the driver, and does not override the DataSource elsewhere.

For **externally launched tasks** (CLI, separate scheduler, another Kubernetes Job), nothing ensures they receive properties injected by SCDF. You must **supply the matching DataSource configuration yourself** if you want them to appear in SCDF.

### 3.1. Three Common Launch Paths

~~~mermaid
flowchart LR
    S["Data Flow Server"] -->|"launch task + DataSource properties"| A["Task run via SCDF"]
    C["External scheduler"] -->|"must configure DB separately"| B["Task run outside SCDF"]
    S --> D["Composed Task Runner"]
    D --> E["Child task 1"]
    D --> F["Child task 2"]
    A --> M[("Shared metadata store")]
    B --> M
    D --> M
    E --> M
    F --> M
~~~

| Launch Path | Conditions for Metadata Sharing |
| --- | --- |
| **Simple task launch from SCDF** | SCDF injects datasource config; task must have the driver and proper schema/permissions |
| **Composed Task Runner (CTR)** | Runner and **every child task** must reach the same shared store with matching drivers |
| **Task run outside SCDF** | Must **explicitly** configure the DataSource pointing to the store SCDF reads; never rely on default H2 |
| **Multi-platform runs** | Even if pods/jobs run in another namespace/cluster, network routes, DNS, firewalls, and permissions must reach the right metadata store |

**Do not confuse "SCDF Server launched the task" with "the task wrote metadata."** The deployer may create a Pod successfully while the application crashes due to a missing driver or lack of permissions on `TASK_EXECUTION`.

## 4. Test Configuration with PostgreSQL

Suppose an organization runs PostgreSQL at `metadata-db.internal:5432`, database `scdf_metadata`, default schema `public`. To illustrate least privilege, the server and task use **two distinct runtime accounts**.

### 4.1. Data Flow Server Side

Example **SCDF server** `application.yml` (abbreviated):

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://metadata-db.internal:5432/scdf_metadata
    username: scdf_server
    driver-class-name: org.postgresql.Driver
    # Password: provide via Kubernetes Secret/secret manager.
~~~

In practice, add a **password delivery mechanism** (such as `SPRING_DATASOURCE_PASSWORD` in the server environment), infrastructure configuration, and database properties required by your deployed **SCDF version**. `driver-class-name` uses kebab-case; Spring Boot binds it compatibly with `driverClassName`.

**This is server configuration**, not an instruction to auto-create metadata schemas in production. SCDF may auto-initialize some tables depending on version/config; production environments should use controlled migrations rather than having multiple apps race to create tables.

### 4.2. Task Application Side

Example `application.yml` for a **task intentionally connecting to the same database**:

~~~yaml
spring:
  main:
    web-application-type: none
  datasource:
    url: jdbc:postgresql://metadata-db.internal:5432/scdf_metadata
    username: task_writer
    driver-class-name: org.postgresql.Driver
    # Password: provide via the task runtime's secret.
  cloud:
    task:
      name: daily-settlement
      initialize-enabled: false
~~~

`initialize-enabled: false` is appropriate only after a DBA/migration has created a compatible TaskRepository schema. If the database is empty and auto-initialization is disabled, the application cannot write `TASK_EXECUTION`.

**Important when Data Flow launches tasks:** SCDF can pass DataSource properties from the server down to the task. If you want the task to use a **different account** (such as `task_writer`) while sharing the same metadata store, ensure property binding precedence and actual platform configuration **do not overwrite those values unexpectedly**. Do not look at YAML inside a JAR and assume the task used that account; inspect the **resolved runtime connection details** without printing passwords.

### 4.3. The JDBC Driver Must Be Packaged with the Task Artifact

Having the PostgreSQL driver in SCDF Server **does not mean** every task JAR/image includes that driver. With Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-task</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Starter and driver versions should be managed via a **compatible BOM**. When the application uses Spring Batch, add the Spring Batch starter and verify `JobRepository` separately. Never pick arbitrary versions of Spring Boot, Task, and Batch independently just because each exists on Maven Central.

### 4.4. When Using a Separate Business Database

A task may need:

- `metadataDataSource` pointing to `scdf_metadata`.
- `businessDataSource` pointing to `orders_db`.

In this case, **explicitly configure `TaskConfigurer`**, transaction managers, and JDBC/JPA beans so **`TaskRepository`** writes to the metadata DB. With Spring Batch, also specify which DataSource/transaction manager `JobRepository` uses.

APIs can query via `TaskExplorer` and `JobExplorer`, but they **do not automatically synchronize business results** across the two databases. Processing a refund in the business database and then failing to update metadata can leave SCDF showing an incomplete state even though funds moved. Retry/idempotency design by business key remains mandatory.

## 5. Access Permissions: Separating Users and Responsibilities

There are three distinct authorization layers:

1. **SCDF API/RBAC:** which users or service accounts may register apps, launch tasks, stop tasks, view executions, or configure schedules.
2. **Platform RBAC:** which server/deployer may create Kubernetes Jobs/Pods, read Secrets, access namespaces, or invoke cloud APIs.
3. **Database privileges:** which runtime accounts may `SELECT`, `INSERT`, `UPDATE`, use sequences/sequence tables, or create/alter schemas.

A user permitted to **view the SCDF Dashboard** should not implicitly receive direct SQL access. Likewise, granting Kubernetes permission to create Pods **does not grant permission** to insert into `TASK_EXECUTION` in PostgreSQL.

### 5.1. Recommended Responsibility Matrix

| Role | Required Permissions | Should Not Be Broadly Granted |
| --- | --- | --- |
| **SCDF server runtime** | Access to SCDF metadata and any task/batch tables the server reads/creates/updates | DB superuser; unrestricted writes to all business DBs |
| **Spring Cloud Task runtime** | `SELECT/INSERT/UPDATE` on needed TaskRepository tables and schema-level ID generation | `CREATE/DROP/ALTER` across the database |
| **Spring Batch runtime** | Read/write on Batch metadata tables, plus Task tables if Cloud Task integration is enabled | Broad DDL, access to unrelated apps |
| **Custom Dashboard using TaskExplorer** | If direct DB access is needed, `SELECT` only on required metadata tables | `UPDATE` status or `DELETE` history |
| **Migration/DBA role** | Bounded, audited `CREATE/ALTER/DROP` to apply migrations | Shared as the runtime account for all tasks |

**Do not apply a fixed permission list blindly across all versions.** SCDF Server can pre-create `TaskExecution` records before the deployer starts the process, meaning **the server sometimes needs write permissions on task tables too**. The task account may need permissions on `TASK_SEQ`; single-instance mode may need `TASK_LOCK`; Batch integration requires `TASK_TASK_BATCH` and `BATCH_*`. Always check **actual DDL, enabled features, and deployment behavior**.

### 5.2. PostgreSQL Example: Granting Permissions by Need

Below is an **illustrative SQL template**, not a drop-in migration for every system:

~~~sql
-- Run using an approved DBA/migration account.
-- Example assuming TaskRepository tables reside in the public schema.

GRANT CONNECT ON DATABASE scdf_metadata TO task_writer;
GRANT USAGE ON SCHEMA public TO task_writer;

GRANT SELECT, INSERT, UPDATE
ON TABLE public.TASK_EXECUTION
TO task_writer;

GRANT SELECT, INSERT, UPDATE
ON TABLE public.TASK_EXECUTION_PARAMS
TO task_writer;
~~~

In PostgreSQL, unquoted table names are folded to lowercase; this example assumes standard unquoted DDL. If your actual DDL uses **quoted, case-sensitive** names, adjust the statements accordingly.

**The snippet above does not cover every runtime permission.** Execution ID generation may use `TASK_SEQ` or another sequence mechanism; enabling `TASK_TASK_BATCH`, `TASK_LOCK`, or Spring Batch introduces additional objects. For native database sequences, `USAGE`/`SELECT` on the sequence may be needed. For table-backed sequences, DML privileges differ. DBAs must inspect the **actual schema** before granting.

When **SCDF server and tasks use two separate accounts**, prepare dedicated privileges for `scdf_server` on the tables SCDF accesses rather than assuming `task_writer`'s permissions suffice. Afterward, run an integration test using **the actual runtime account** to verify there are no permission-denied errors on `INSERT`, `UPDATE`, or `nextval`.

### 5.3. Read Access Must Also Be Restricted

`TASK_EXECUTION_PARAMS` can store command-line arguments; `ERROR_MESSAGE` and `EXIT_MESSAGE` can expose hostnames, file paths, stack traces, or sensitive details if logged carelessly.

- Never pass passwords, tokens, or API keys via `--password=...`.
- Never log the full environment or DataSource URLs containing credentials.
- Scope SCDF REST API/Dashboard permissions by environment, team, and need.
- When exporting metadata to BI systems, use column-restricted views or redact sensitive fields.
- Require TLS for database connections and restrict network ingress via firewalls/NetworkPolicies.

## 6. Protecting Credentials When SCDF Launches Tasks on Kubernetes

Spring Cloud Data Flow can **pass database connection details down to tasks at launch time**. In the SCDF 2.11 Kubernetes documentation, the default mechanism can pass credentials as application properties; with certain `entryPointStyle` values such as `exec` or `shell`, those values can be exposed in Pod descriptions or command lines.

SCDF 2.11 documentation describes an option to use **Kubernetes Secrets** for credentials:

~~~properties
spring.cloud.dataflow.task.use.kubernetes.secrets.for.db.credentials=true
~~~

**This is configuration for servers/deployment paths that support the feature**, not a property understood by arbitrary Spring Cloud Task applications.

When enabled, ensure the corresponding `secretKeyRefs` are configured on the **task platform account** and the Secret actually exists in the namespace where workers run. Exact environment variable names, Secret names, and data keys depend on your chart/manifests/release version.

**Structural illustration**—never place real passwords in source code:

~~~yaml
spring:
  cloud:
    dataflow:
      task:
        use:
          kubernetes:
            secrets:
              for:
                db:
                  credentials: true
        platform:
          kubernetes:
            accounts:
              default:
                secretKeyRefs:
                  - envVarName: "spring.datasource.username"
                    secretName: metadata-db
                    dataKey: username
                  - envVarName: "spring.datasource.password"
                    secretName: metadata-db
                    dataKey: password
~~~

`secretKeyRefs` keys and their interaction with `use.kubernetes.secrets.for.db.credentials` must be **verified against your actual SCDF version and Helm chart**; this snippet only illustrates placement and structure. Never assume every SCDF release implements this configuration with identical syntax.

**Operational recommendations:**

1. Supply credentials via a Secret manager/Kubernetes Secret, never hardcoded YAML inside images.
2. Restrict which service accounts/pods can read the metadata DB Secret.
3. Verify how the deployer injects arguments/environment variables so credentials never show up in logs, process lists, `kubectl describe`, or TaskExecution metadata.
4. Coordinate password rotation with active Jobs so running transactions are not disrupted unexpectedly.
5. Separate read-only observability permissions from task creation/editing and metadata write privileges.
6. Audit who launched a task or changed DataSource/deployment properties.

**Never treat base64 as encryption.** Kubernetes `Secret.data` uses base64 for encoding, which provides no confidentiality against anyone permitted to read the Secret.

## 7. Multi-Layer Version Compatibility

A task application may build cleanly yet still **fail to share metadata** if components span incompatible framework or schema generations.

~~~mermaid
flowchart LR
    A["SCDF Server version"] --> B["SCDF metadata schema"]
    C["Spring Cloud Task + Boot"] --> D["TASK_* schema"]
    E["Spring Batch version"] --> F["BATCH_* schema"]
    G["JDBC driver + Database engine"] --> H["Connection / SQL execution"]
    B --> I{"Compatibility verified?"}
    D --> I
    F --> I
    H --> I
    I -->|Yes| J["Integration + migration tests"]
    I -->|No| K["Do not deploy to production"]
~~~

### 7.1. Compatibility Matrix to Manage

| Component | What to Verify |
| --- | --- |
| **SCDF Server** | Release version, API/dashboard, admin schema, supported platforms, and task app versions |
| **Spring Boot** | Required Java runtime, DataSource auto-configuration, JDBC/Hibernate versions |
| **Spring Cloud Task** | Boot-compatible release, `TaskExecution` structure, SQL schema/DDL, `TaskConfigurer` |
| **Spring Batch** | Metadata schema, column/data types, `JobRepository`, restartability, and execution context |
| **Spring Cloud Deployer** | `TaskLauncher` implementation, how app properties/secrets are passed, artifact URIs |
| **Database engine & JDBC driver** | Dialect, timestamp types, schema prefix, locks/sequences, server version |
| **Task artifact** | JAR/image version, Spring Cloud BOM, DB driver dependency, target launch environment |

**Never treat the word "current" in documentation URLs as proof that a version combination works together.** Pin exact releases in manifests/Helm charts and verify against that release's compatibility matrix.

In **SCDF 2.11**, documentation includes branches supporting both Boot 2 and Boot 3 task apps, using settings/metadata like `spring.cloud.deployer.bootVersion` and `spring.cloud.task.schemaTarget` on specific execution paths. That is a prime example of why you must verify **launch path and schema target** before upgrading; never blindly set `schemaTarget=boot3` across all tasks without validating their contracts.

### 7.2. Version Maintenance Context

Per Spring's announcement on **April 21, 2025**, **Spring Cloud Data Flow 2.11.x** and **Spring Cloud Deployer 2.9.x** are the **final open-source lines**; future releases follow a commercial model for Tanzu Spring customers. This **does not mean** existing 2.11.x deployments immediately stop working or lack updates under active support contracts.

When planning enterprise upgrades, check **distribution sources and entitlement to newer versions**, support timelines, CVEs/patches, and vendor compatibility matrices. Avoid asserting a fixed "latest" version without confirming it at deployment time.

### 7.3. Why "Same Table Names" Does Not Guarantee Compatibility

Suppose a Task 2.x writes metadata using an older DDL while SCDF Server and Task 3.x expect a newer layout. You may encounter:

- `column does not exist` errors on queries.
- Data type errors when inserting/updating timestamps or exit codes.
- ID allocation failures due to incompatible sequence table mechanics.
- Batch metadata query failures from mismatched `BATCH_*` schemas.
- Mapping errors from wrong table prefixes or schema targets.
- Apps starting up while history queries or restarts silently malfunction.

Therefore, compatibility must be **tested at the SQL and business levels**, not stopped at `mvn package` or seeing a Pod reach `Running`.

## 8. Safe Schema Management and Migrations

### 8.1. Who Creates the Tables?

In demos, Spring Cloud Task can auto-create its schema via `spring.cloud.task.initialize-enabled`, and SCDF has version-dependent schema initialization. In **production**, many task processes and servers can start concurrently, so prevent every process from racing to create or alter metadata tables uncontrolled.

A clean model:

1. **DBA or migration pipeline** owns the metadata schema and holds DDL privileges.
2. **SCDF server and task runtimes** receive only the DML privileges needed to read/write data.
3. **Task, Batch, and SCDF migrations** are matched to the exact deployed version set.
4. **Never hand-alter columns** in `TASK_EXECUTION` or `BATCH_JOB_EXECUTION` as a "quick fix" for a failing SQL query.
5. **Never purge old metadata** before assessing impact on restarts, audits, and task/job links.

### 8.2. Staged Upgrade Procedure

~~~mermaid
flowchart TD
    A["Lock inventory of current versions + schema"] --> B["Back up DB and test restore"]
    B --> C["Build staging copy of data/DDL"]
    C --> D["Run official migrations"]
    D --> E["Test SCDF, Task, Batch per matrix"]
    E --> F{"All tests PASS?"}
    F -->|No| G["Halt upgrade, resolve compatibility"]
    F -->|Yes| H["Drain active tasks + execute planned rollout"]
    H --> I["Smoke test, audit, and monitor"]
~~~

**Step 1 — Inventory:** record SCDF Server version, task JARs/images, Spring Boot/Cloud BOM, Spring Batch, Spring Cloud Deployer, JVM, DB engine/driver, table prefixes, and `schemaTarget` settings if used.

**Step 2 — Preserve:** back up metadata and **test restoration**. If old Batch Jobs must remain restartable, preserve `BATCH_JOB_*`, `BATCH_STEP_*`, and execution contexts. Creating a dump file without testing restore is insufficient.

**Step 3 — Test migrations in staging:** apply official DDL/migrations on a faithful copy. Verify tables, indexes, sequences/sequence tables, constraints, and new permissions.

**Step 4 — Multi-version testing:** if performing a rolling upgrade, verify both old and new binaries can read/write the same schema **during the overlap window**. If not guaranteed, plan to **pause new launches**, let running Jobs finish, migrate, and switch over together.

**Step 5 — Cutover:** update containers/images, DataSources, secrets, deployment properties, and platform configuration. Avoid changing too many variables simultaneously without clear fault isolation.

**Step 6 — Verify:** launch a smoke-test task, read back `TASK_EXECUTION` and `BATCH_JOB_EXECUTION`, test dashboard views, retries, and restarts, then monitor across several operational cycles.

**Step 7 — Rollback plan:** rolling back binaries **does not automatically roll back schema**. If DDL changes are backward-incompatible, prepare a backup restore plan and a clear maintenance window. Never blindly run old code against a new schema.

## 9. Verifying Store and Permissions with SQL

The following **PostgreSQL** commands are meant to be run using authorized inspection tools and **the exact runtime account being verified**, never executed automatically from an unprivileged business task.

### 9.1. Confirm the Actual Connection

~~~sql
SELECT
    current_database() AS database_name,
    current_schema() AS default_schema,
    current_user AS login_role;
~~~

Run the same query from both the SCDF Server environment and the task environment (using matching configuration) to verify the actual database/schema. The two roles may differ, yet both must resolve to the same metadata tables.

### 9.2. Check Whether Metadata Tables Exist

~~~sql
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_name IN (
    'task_execution',
    'task_execution_params',
    'batch_job_execution',
    'batch_step_execution'
)
ORDER BY table_schema, table_name;
~~~

In PostgreSQL, unquoted DDL folds uppercase identifiers like `TASK_EXECUTION` to lowercase `task_execution` in `information_schema`. If tables were created with double-quoted identifiers, adjust the name filter accordingly.

### 9.3. Check Privileges on Task Tables

~~~sql
SELECT
    has_table_privilege(
        current_user, 'public.task_execution', 'SELECT'
    ) AS can_select,
    has_table_privilege(
        current_user, 'public.task_execution', 'INSERT'
    ) AS can_insert,
    has_table_privilege(
        current_user, 'public.task_execution', 'UPDATE'
    ) AS can_update;
~~~

Results should match the role's responsibilities. If the schema is not `public`, substitute the full schema-qualified name. **Table privileges alone are not enough** if execution ID generation relies on a sequence or sequence table the role cannot access.

### 9.4. Read Executions via SQL

~~~sql
SELECT
    TASK_EXECUTION_ID,
    TASK_NAME,
    START_TIME,
    END_TIME,
    EXIT_CODE,
    ERROR_MESSAGE
FROM TASK_EXECUTION
ORDER BY TASK_EXECUTION_ID DESC
LIMIT 20;
~~~

If the task runs Spring Batch:

~~~sql
SELECT JOB_EXECUTION_ID, STATUS, EXIT_CODE,
       START_TIME, END_TIME
FROM BATCH_JOB_EXECUTION
ORDER BY JOB_EXECUTION_ID DESC
LIMIT 20;
~~~

These read queries confirm **committed metadata**; they do not prove a process/pod is still alive or that business outcomes finished properly. Combine them with logs, `TaskExplorer`/`JobExplorer`, and business data checks.

### 9.5. Minimal Verification Test Suite

One end-to-end integration test is worth far more than `SELECT 1`:

1. Using the task runtime account, run a test task with a successful `ApplicationRunner`; it must **create a `TaskExecution` and update completion**.
2. Using a controlled-failure test task, verify `EXIT_CODE` and `ERROR_MESSAGE` in the repository.
3. In SCDF Dashboard/API, locate that exact run and confirm its status.
4. If using Batch, run a single-Step Job and verify Job/Step metadata plus Task–Batch linkage per version.
5. Perform a controlled rerun and verify retry/idempotency; never hand-edit `EXIT_CODE` in the DB.
6. Repeat across every supported platform account, including scheduled jobs and externally launched jobs if your organization uses them.

## 10. Troubleshooting by Symptom

| Symptom | Common Causes | Priority Check |
| --- | --- | --- |
| Task finishes, SCDF shows no execution | Task used private H2 or wrong host/database/schema | Compare resolved JDBC URL, database, schema, and tables |
| Task startup fails with `No suitable driver` | Task JAR/image lacks JDBC driver | Check driver dependency in task artifact and JDBC URL |
| `permission denied for table task_execution` | Runtime role lacks DML on task tables | Check `current_user` and `has_table_privilege` |
| `permission denied for sequence` / ID failure | Missing privilege on `TASK_SEQ` mechanism | Inspect DDL and permissions on sequence/sequence table |
| `relation task_execution does not exist` | Schema unmigrated, wrong `search_path`, or table prefix | Inspect `information_schema`, JDBC schema, and table init |
| Batch Job missing or restart fails | `BATCH_*` not in SCDF's store or schema/version mismatch | Check `JobRepository` DataSource, DDL, and `JobExecution` |
| CTR runs, child tasks lack history | One or more child apps use a different datasource/driver | Inspect each child's config and permissions |
| Errors after upgrade despite DB connectivity | New binary / old DDL or vice versa | Check version matrix, migration logs, columns/indexes |
| Dashboard shows task failed despite business writes | Process died before updating TaskRepository | Check infra/logs, idempotency, and committed outputs |
| DB password exposed in Pod description | SCDF passed credentials as properties or wrong entrypoint style | Review Kubernetes Secrets and version-specific SCDF config |
| Runs on platform A appear, B does not | B points to a separate DB or lacks network route | Compare config/runtime/network policies per platform |
| Tasks disrupted after secret rotation | Secret/credential rotated mid-run | Review connection pools, pod lifetimes, and rotation strategy |

**Troubleshooting rule:** never alter or overwrite metadata tables just to turn the dashboard "COMPLETED." If a task already produced business results yet lacks `END_TIME`, investigate why the process could not update metadata, then design safe recovery.

## 11. Real-World Design Scenarios

### Scenario A — One SCDF Server, Many Scheduled Tasks

One SCDF server launches `daily-billing`, `email-digest`, and `reconciliation` on Kubernetes. The three tasks differ in function yet share one PostgreSQL metadata DB. Each app packages the driver and holds write privileges on TaskRepository tables. History is viewed in the Dashboard.

**Design takeaway:** restrict runtime database privileges and network access; tasks do not need access to each other's business tables. Each task enforces duplicate protection by business key, because a shared metadata store **does not guarantee exactly-once execution**.

### Scenario B — Task Launched Outside Data Flow

A payments system has an independent scheduler running `nightly-reconciliation.jar`. To view its executions in SCDF, the scheduler must supply a DataSource pointing to **the same metadata store** used by SCDF; merely matching `spring.cloud.task.name` is not enough.

**Design takeaway:** externally launched tasks still need the JDBC driver, schema settings, and write privileges. Log the launch origin/correlation ID so SCDF schedules are never confused with external schedulers.

### Scenario C — Composed Task Runner with Two Child Tasks

CTR orchestrates `download-data` followed by `transform-data`. CTR and both child apps run in separate Pods; each app needs a compatible metadata DataSource. The second child uses a profile that accidentally falls back to H2.

**Consequence:** CTR cannot track the child's status accurately. Inspect **every image and profile**, rather than testing connectivity only from CTR or SCDF Server.

### Scenario D — Upgrading a Mixed Boot 2 / Boot 3 Environment

Some legacy tasks run on Boot 2 while newer tasks use Boot 3, and an SCDF 2.11 server supports multiple task generations under specific configuration conditions.

**Design takeaway:** pin `bootVersion` / `schemaTarget` appropriately where supported, test TaskRepository/Batch schemas and JDBC dependencies, and keep separate test matrices per task generation. **Never upgrade all metadata schemas** without assessing impact on tasks/JobInstances that still require restarts.

## 12. Production Readiness Checklist

### Connectivity and Schema

- [ ] SCDF Server, task apps, and child tasks use **the same verified metadata database/schema**.
- [ ] Tasks run by external schedulers also receive the metadata DB config if they must appear in SCDF.
- [ ] Every task artifact bundles a JDBC driver compatible with the DB engine.
- [ ] When using multiple DataSources, `TaskConfigurer` and `JobRepository` point to the right store.
- [ ] Table prefixes `TASK_`, `BATCH_`, and `schemaTarget` are verified for the release.
- [ ] Metadata tables, indexes, and sequences were created via controlled migrations.

### Permissions and Security

- [ ] Server, task, batch, viewer, and migration roles have **separate least-privilege grants** matching actual needs.
- [ ] Task runtimes hold no broad DDL privileges; execution ID allocation permissions are tested.
- [ ] SCDF API/RBAC, Kubernetes RBAC, and SQL privileges are managed independently.
- [ ] Secrets are supplied securely per SCDF/deployer version and never appear in command lines or logs.
- [ ] Database uses TLS with restricted network sources; credential rotation is planned.
- [ ] No passwords or tokens are stored in `TASK_EXECUTION_PARAMS` or error messages.

### Versioning and Operations

- [ ] Maintain an inventory of SCDF/Boot/Cloud Task/Batch/Deployer/JDBC/DB/schema versions.
- [ ] Tested both old and new versions in staging for rolling upgrades.
- [ ] Backed up **and tested restore** before upgrading metadata schemas.
- [ ] Prepared procedures for active Jobs/Tasks, restarts, and binary/schema rollbacks.
- [ ] Tested a succeeding task, a failing task, and a Batch Job end-to-end via SCDF UI/API.
- [ ] Prepared runbooks for investigating DB/schema/permission mismatches and unclosed metadata.
- [ ] Implemented business reconciliation and idempotency for tasks killed before writing final status.

## 13. Summary

For **Spring Cloud Data Flow** to orchestrate and display **Spring Cloud Task** history, writers and readers must access **the same effective metadata store**: not only matching table names, but matching **database, schema, table prefix, driver, permissions, and schema version**. With **Spring Batch**, also verify `BATCH_*` tables and job/step restartability.

Access controls must be separated across the **SCDF API**, **deployment infrastructure**, and **database**. In Kubernetes environments, pay close attention to how Data Flow forwards credentials to tasks and verify your exact version's Secrets integration. During upgrades, evaluate **the entire version stack and DDL**, run migrations with backup/rollback plans, and prove via integration tests that tasks can write, SCDF can read, and business data stays accurate.

### References

- [Spring Cloud Data Flow 2.11 — Sharing Data Flow's Datastore with Tasks](https://docs.spring.io/spring-cloud-dataflow/docs/2.11.0/reference/htmlsingle/)
- [Spring Cloud Data Flow — Architecture and Database](https://dataflow.spring.io/docs/concepts/architecture/)
- [Spring Cloud Data Flow — FAQ: task/batch applications and shared database](https://dataflow.spring.io/docs/resources/faq/)
- [Spring Cloud Data Flow — Kubernetes database credentials and Secrets](https://docs.spring.io/spring-cloud-dataflow/docs/current/reference/htmlsingle/)
- [Spring Cloud Task — DataSource, table prefix and schema initialization](https://docs.spring.io/spring-cloud-task/reference/features.html)
- [Spring Cloud Task — Task Repository Schema](https://docs.spring.io/spring-cloud-task/docs/current/reference/html/appendix-task-repository-schema.html)
- [Spring Cloud — Release train / Spring Boot compatibility](https://spring.io/projects/spring-cloud/)
- [Spring — Spring Cloud Data Flow End of Open-Source, April 21, 2025](https://spring.io/blog/2025/04/21/spring-cloud-data-flow-commercial/)
