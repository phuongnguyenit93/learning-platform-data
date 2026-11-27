# Comparing BOMs, APIs, and Properties Across Spring Cloud Task Versions

## 1. Why Does Upgrading Spring Cloud Task Require Cross-Checking Multiple Layers?

**Spring Cloud Task** helps build **finite-running** Spring Boot applications: file imports, reconciliation, report exports, scheduled processing, or on-demand jobs. Each run can be recorded as a **TaskExecution** in **TaskRepository**; when paired with **Spring Batch**, the application also has JobRepository, StepExecution, and checkpoints.

Upgrading merely by editing one version line is not enough. There are cases where code compiles cleanly yet at JVM runtime:

- Spring Boot and Spring Cloud belong to two **incompatible release trains**.
- The runtime JAR pulls in Spring Framework, Spring Batch, or Spring Integration versions misaligned with the BOM.
- APIs, constructors, packages, or auto-configuration mechanisms have changed.
- Old properties no longer bind, or defaults changed, causing the task to write wrong metadata, fail to exit, or return the wrong exit code.
- TaskRepository or JobRepository tables/sequences have not been migrated.
- The scheduler retries after a crash, while business data already committed gets processed twice.

Therefore, a safe upgrade procedure must verify the full chain: **BOM → resolved dependencies → API → configuration properties → schema → runtime behavior → rollback**.

For example, `daily-close-task` closes revenue for `2026-11-23`. The new version must continue recording TaskExecution, accurately reflect when a Spring Batch Job fails, and avoid double-recording revenue if a prior run committed before the JVM died prior to writing final repository status.

## 2. Six Version Axes to Manage

| Axis | Example | Role |
|---|---|---|
| **Java/JDK** | JDK 17 or stack-supported Java version | Bytecode, runtime, JDBC driver, image |
| **Spring Boot** | `3.5.x`, `4.2.0` | Auto-configuration, dependency management, lifecycle |
| **Spring Cloud release train** | `2025.0.x`, `2025.1.x`, `2026.0.0` | BOM coordinating Spring Cloud projects |
| **Spring Cloud Task** | `3.x`, `5.x` | TaskRepository, TaskExecution, listeners, integration |
| **Spring Batch** | `5.x`, `6.x` | Job/Step, JobRepository, launch/restart APIs |
| **Database/platform** | PostgreSQL, JDBC, SCDF, Kubernetes | Metadata DDL, privileges, process orchestration |

**The Spring Cloud release train is not the Spring Cloud Task version.** Version `2026.0.0` is the release train/BOM, whereas the Task module version inside it can be `5.1.0`.

Do not infer Java or Batch versions solely from the Spring Cloud version. **The official support matrix**, the actually imported BOM, and the resolved dependency graph are the three most important sources.

## 3. Spring Boot and Spring Cloud Compatibility Table

Per Spring release documentation at the time of writing (**2026-11-24**):

| Spring Cloud Train | Published Compatible Spring Boot | Notes |
|---|---|---|
| `2026.0.0` / Paddington | **4.2.0** | Includes Spring Cloud Task **5.1.0** |
| `2025.1.x` / Oakwood | **4.0.x**; **4.1.x from 2025.1.2** | E.g. train `2025.1.4` uses Task `5.0.2` |
| `2025.0.x` / Northfields | **3.5.x** | Verify exact Task patch inside the BOM |
| `2024.0.x` / Moorgate | **3.4.x** | Check support/EOL status before choosing |
| `2023.0.x` / Leyton | **3.2.x**; **3.3.x from 2023.0.2** | Older line; plan replacement |

On **2026-11-20**, Spring announced Spring Cloud `2026.0.0` based on Spring Boot `4.2.0`; the train's module list confirms Spring Cloud Task `5.1.0`. The table above is only a **point-in-time snapshot**, not a guarantee that every Spring Boot patch pairs with every service release in the same train. When deciding on an upgrade, consult the compatibility matrix and release notes for **your exact target patch**.

Official sources:

- [Spring Cloud: release train compatibility](https://spring.io/projects/spring-cloud/)
- [Spring Cloud 2026.0.0 announcement](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/)
- [Spring Cloud release train documentation](https://docs.spring.io/spring-cloud-release/reference/)

### Baseline and Target Table for a Project

Before changing dependencies, fill out this table:

| Component | Baseline | Target | Evidence |
|---|---|---|---|
| Build/runtime JDK | `...` | `...` | `java -version` and image digest |
| Boot | `...` | `...` | Plugin/parent POM |
| Cloud train | `...` | `...` | Imported Cloud BOM |
| Task, Batch | `...` | `...` | Resolved dependency graph |
| Framework/Integration | `...` | `...` | Transitive dependencies |
| PostgreSQL driver/DB | `...` | `...` | Driver JAR and server version |
| Task/Batch schema | `...` | `...` | DDL and migration history |

The `...` placeholders are filled in by the learner from real builds, not pre-verified data. Distinguish **declared version** from **resolved version**; the two can diverge due to overrides or transitive dependencies.

## 4. What Is a BOM, and How Does Boot BOM Differ from Cloud BOM?

A **BOM (Bill of Materials)** contains a set of version constraints/management tested to work together. Importing a BOM **does not automatically add** all those libraries to your application.

~~~mermaid
flowchart TD
    B["Spring Boot parent/plugin/BOM"]
    C["Spring Cloud dependencies BOM"]
    B --> D["Spring Boot, Framework, and Boot-managed dependencies"]
    C --> E["Spring Cloud Task and Spring Cloud projects"]
    D --> G["Resolved runtimeClasspath"]
    E --> G
    G --> R["Spring Cloud Task JVM"]
    R --> T["TaskRepository / Batch JobRepository"]
~~~

- **Boot BOM** manages dependencies in the Spring Boot ecosystem, including core libraries, logging, JDBC, and Spring Batch depending on version.
- **Cloud BOM** coordinates Spring Cloud modules (Task, Config, Stream, etc.) per release train.
- **Custom version overrides** can beat the BOM or cause conflicts. Even if the app runs on a developer laptop, the runtime image may not match the development dependency graph.
- **Force/enforcedPlatform** in Gradle can alter version selection rules. Do not enable it just to "guarantee the newest version" without analyzing impact.

For Spring Batch, avoid forcing a major version outside the target Boot/Cloud stack. When a specific version is required due to a CVE, document the reason, check the support matrix, and run full integration tests.

## 5. Maven Example Importing the Cloud BOM

Example for a **published target**: Spring Boot `4.2.0` and Spring Cloud `2026.0.0`. This is a learning POM without test plugins or deployment-specific configuration:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
            https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.2.0</version>
    <relativePath/>
  </parent>
  <groupId>example</groupId>
  <artifactId>daily-close-task</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
    <spring-cloud.version>2026.0.0</spring-cloud.version>
  </properties>

  <dependencyManagement>
    <dependencies>
      <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-dependencies</artifactId>
        <version>${spring-cloud.version}</version>
        <type>pom</type>
        <scope>import</scope>
      </dependency>
    </dependencies>
  </dependencyManagement>

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
</project>
~~~

`java.version=17` is an **example parameter** and does not replace checking Boot's minimum JDK requirement and dependency requirements in a real build. When raising the target, verify Java release requirements before choosing build/runtime images.

Do not declare a direct version on `spring-cloud-starter-task` if you want the Cloud BOM to manage it. If an override is unavoidable, record exactly which artifact and why, and save the dependency tree proving the result.

### Checking Resolved Versions with Maven

~~~bash
mvn help:effective-pom
mvn dependency:tree -Dincludes=org.springframework.cloud
mvn dependency:tree -Dincludes=org.springframework.batch
mvn dependency:tree -Dincludes=org.springframework
mvn dependency:tree -Dincludes=org.springframework.boot
~~~

These commands are guidance for your project, not evidence of runs in this workspace. `effective-pom` shows configuration after inheritance; `dependency:tree` checks resolved versions. Look for `spring-cloud-task-core`, `spring-batch-core`, and `spring-core` rather than looking only at starters.

## 6. Gradle Groovy DSL Examples: Two Ways to Manage BOMs

**Approach 1 — Spring dependency-management plugin:**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.2.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

repositories {
    mavenCentral()
}

dependencyManagement {
    imports {
        mavenBom 'org.springframework.cloud:spring-cloud-dependencies:2026.0.0'
    }
}

dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-task'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

**Approach 2 — Gradle native platforms:**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.2.0'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:4.2.0')
    implementation platform(
        'org.springframework.cloud:spring-cloud-dependencies:2026.0.0')

    implementation 'org.springframework.cloud:spring-cloud-starter-task'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

The goal is a **compatible resolved graph**, not choosing whichever import style looks "newer." If you use version catalogs or multi-module builds, check constraints in **every module** that actually packages the final JAR.

Verification commands:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-cloud-task-core \
  --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-batch-core \
  --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-core \
  --configuration runtimeClasspath
~~~

On Windows you can run `gradlew.bat`. Do not inspect only `compileClasspath`, because `runtimeOnly` drivers and libraries can trigger `NoClassDefFoundError` or `NoSuchMethodError` when the process starts.

## 7. API Analysis: Do Not Just Compile — Run the Lifecycle Too

Notable Spring Cloud Task APIs:

| API Group | Function | Check Between Baseline/Target |
|---|---|---|
| `TaskExecution` | Metadata for one run | Getter types, nullability, timestamps, and exit code |
| `TaskRepository` and `TaskExplorer` | Save/read TaskExecution | DataSource/transactions, SQL, paging/lookup |
| `TaskExecutionListener` | Startup, failed, end callbacks | Signatures, timing, and exception behavior |
| `@BeforeTask`/`@AfterTask`/`@FailedTask` | Listener annotations | Package, auto-registration, bean lifecycle |
| `TaskConfigurer`/`DefaultTaskConfigurer` | Customize repository/schema | Constructors, bean wiring, table prefix |
| `ApplicationRunner`/`CommandLineRunner` | Finite unit of work | Ordering, errors, async, shutdown |
| `ExitCodeGenerator`/`ExitCodeExceptionMapper` | Process/task exit code | Whether exceptions yield non-zero codes |
| `JobOperator`/`JobLauncher` | Spring Batch | API, synchronous/asynchronous, restart |

**Source compatibility** means the code still compiles. **Behavior compatibility** means the task still writes `TaskExecution`, closes `END_TIME`, returns the right exit code, and exits the JVM cleanly. A major auto-configuration change can **cause zero compile errors** while making `TaskRepository` stop using the intended DataSource.

### Do Not Read "latest" Javadoc for an Older JAR

Always compare **baseline Javadoc/reference** against **target Javadoc/reference**. Audit template:

~~~text
API                           Baseline       Target        Evidence / action
TaskExecution.getExitCode     X              ?             compile + nullable test
TaskExecutionListener         X              ?             callback integration test
TaskConfigurer constructor    X              ?             compile + context test
JobLauncher / JobOperator     Batch 5.x      Batch 6.x?    migration + restart test
~~~

A `?` means **must be verified**; never assume a breaking change exists solely because a new major version appeared.

## 8. Common API Example: Spring Batch 5 to Spring Batch 6

Task applications often contain one or more Spring Batch Jobs. When upgrading Boot/Batch majors, inspect the launch mechanism.

**Spring Batch 6** Javadoc marks `org.springframework.batch.core.launch.JobLauncher` as **`@Deprecated(since="6.0", forRemoval=true)`** and recommends moving to `JobOperator`. Read the exact API of your target patch before refactoring.

A familiar Batch 5 snippet:

~~~java
JobExecution execution = jobLauncher.run(job, parameters);

if (execution.getStatus() != BatchStatus.COMPLETED) {
    throw new IllegalStateException(
        "Job did not complete: " + execution.getStatus());
}
~~~

This snippet is **only accurate for observing the final outcome when `JobLauncher` is synchronous**. If running asynchronously, `run` may return while the Job is still `STARTING`/`STARTED`. In Batch 6, do not merely swap the `JobLauncher` import for `JobOperator` and keep old assumptions; review the release's method signatures and completion contract.

Scenarios to test:

1. Batch Job completes; task returns the expected exit code.
2. Job is `FAILED` while the caller still receives a `JobExecution`; task must not silently exit 0 if failure reporting is required.
3. Restart with **the same identifying JobParameters** resumes the existing `JobInstance` when valid.
4. Rerunning an already `COMPLETED` `JobInstance` is rejected or handled as `ALREADY_COMPLETED` per policy.
5. Old Step `ExecutionContext`/checkpoints remain readable after schema migration.

Docs: [Spring Batch JobLauncher API](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/launch/JobLauncher.html) and [JobOperator API](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/launch/JobOperator.html).

## 9. Configuration Properties: Cross-Checking Keys, Defaults, and Behavior

Spring Cloud Task properties may be **retained**, **deprecated/renamed**, or have **changed defaults/behavior** across version lines.

| Property / Group | Meaning | What to Verify |
|---|---|---|
| `spring.cloud.task.autoconfiguration.enabled` | Enables/disables Task auto-configuration per supported version | Are TaskRepository beans still auto-created? |
| `spring.cloud.task.initialize-enabled` | Enables/disables metadata table initialization | Does runtime try to execute DDL? |
| `spring.cloud.task.initialize.enable` | Legacy key marked deprecated in older docs | Replace with `initialize-enabled` when target supports it |
| `spring.cloud.task.tablePrefix` / `table-prefix` | TaskRepository table prefix | Do SQL and DDL match? |
| `spring.cloud.task.closecontextEnabled` | Closes context after task | Binding/default and executor impact |
| `spring.cloud.task.single-instance-enabled` | Prevents concurrent tasks with same name | Lock table, transactions, and timeouts |
| `spring.cloud.task.single-instance-lock-ttl` | Single-instance lock TTL | Time unit, crash handling |
| `spring.cloud.task.parent-execution-id` | Links parent–child tasks | Proper ID passing/receiving across namespaces |
| `spring.cloud.task.external-execution-id` | Correlation with orchestrator | Do not confuse with TaskExecutionId |
| `spring.cloud.task.batch.fail-on-job-failure` | Failed Batch Job causes non-zero task exit | Right runner/integration and exit code |
| `spring.cloud.task.batch.applicationRunnerOrder` | Order of Batch integration runner | Do not confuse with Step ordering |
| `spring.batch.job.name` | Selects Spring Boot's Job | Do not confuse with old keys or custom launchers |

This table is a **checklist**, not a promise that every property keeps the same default in every version. Documentation may show **camelCase**; Spring Boot's **relaxed binding** recognizes matching kebab-case. However, **relaxed binding does not guarantee a removed alias still works**.

For each key, check three things:

- **Key/type:** does the target release recognize it, and did the name or type change?
- **Default:** when unset, what is the effective value? Which profiles override it?
- **Runtime:** does actual behavior match expectations, such as schema init, locking, or exit policy?

An unbound property can be **silently ignored without failing startup** in some configurations. That is why smoke tests are essential.

## 10. Diffing Properties Using Metadata and Reference Docs

Many Spring Boot/Cloud JARs bundle configuration metadata:

~~~text
META-INF/spring-configuration-metadata.json
META-INF/additional-spring-configuration-metadata.json
~~~

Metadata can list keys, types, defaults, deprecations, and replacement hints. It is useful for comparing baseline vs. target, though not every custom property or auto-configuration condition is fully described there.

Workflow:

1. Resolve both artifact sets from the **baseline/target** BOMs.
2. Extract metadata from JARs of **the exact version** of Spring Cloud Task, Spring Boot, and Batch.
3. Diff `added/removed/deprecated/type/default`.
4. Compare against keys actually used in your real configs, not just every framework key.
5. Read target reference/migration notes to understand semantic changes.
6. Test binding and effective behavior in an actual Spring Cloud Task process.

Sample audit table:

| Property | Baseline | Target | Action |
|---|---|---|---|
| `spring.cloud.task.initialize-enabled` | Present | Verify present | Keep `false` if external migrations manage schema |
| `spring.cloud.task.initialize.enable` | Legacy | Deprecated/removed? | Verify, migrate to new key |
| `spring.cloud.task.table-prefix` | Present | Verify present | Verify DDL and SQL prefix |
| `spring.cloud.task.batch.fail-on-job-failure` | Present with integration | Verify present | Test `FAILED` Job and JVM exit code |
| `spring.batch.job.names` | Older config | May no longer apply | Check target `spring.batch.job.name` |
| `myapp.batch.timeout` | Custom | Custom | Test `@ConfigurationProperties` |

A `?` marks an item to inspect, not an assertion that the API/property was removed.

### Verified Configuration Migration Example

Legacy config:

~~~properties
spring.cloud.task.initialize.enable=false
spring.cloud.task.tablePrefix=OPS_TASK_
spring.cloud.task.batch.jobNames=closeDayJob
~~~

A **proposed target configuration for testing**:

~~~yaml
spring:
  cloud:
    task:
      initialize-enabled: false
      table-prefix: OPS_TASK_
  batch:
    job:
      name: closeDayJob
~~~

If the project launches the Batch Job manually from an `ApplicationRunner`, you may need to disable auto-launch via `spring.batch.job.enabled=false` **when supported by the target**. Never leave both auto-launch and a custom runner enabled if you only intend to run once.

## 11. Bean Graphs and Auto-Configuration Can Change Even When API Names Stay the Same

After bumping versions, check the conditions controlling Spring Boot auto-configured beans:

- Are the expected starters/dependencies present?
- Do `@EnableTask`, custom `TaskConfigurer`, or legacy configs interfere?
- Which `DataSource` does `TaskRepository` use when multiple `DataSource`s exist?
- Are the transaction manager beans for TaskRepository, Batch JobRepository, and business services right?
- Was `@EnableBatchProcessing` added somewhere, changing auto-configuration responsibilities?
- Does any legacy dependency pull in `javax.*` inside a stack expecting `jakarta.*`?

Three test layers are needed:

| Layer | What It Verifies |
|---|---|
| **Compile** | Java APIs/constructors/methods remain valid |
| **ApplicationContext** | Beans and properties bind as expected |
| **End-to-end process** | Task runner runs finitely, records `TaskExecution`, exits with right code |

In a JVM task, common failures only appear **during context close** or when the repository writes final results. Thus a test that merely loads the context without executing the runner is insufficient.

## 12. TaskRepository DDL Can Change Between Releases

Familiar metadata objects:

~~~text
TASK_EXECUTION
TASK_EXECUTION_PARAMS
TASK_TASK_BATCH        (when Task–Batch integration is present)
TASK_LOCK              (when single-instance is used)
TASK_SEQ or equivalent ID allocation mechanism
~~~

Actual names and mechanisms depend on the DDL of **your exact version and database dialect**. A release may change columns, indexes, sequences, or SQL. Even when the table prefix stays `TASK_`, **you cannot conclude the schema is completely unchanged**.

| DDL Item | What to Compare |
|---|---|
| Tables/columns | Names, types, nullability, lengths, defaults |
| Keys and indexes | PK/FK/unique constraints, performance/locking |
| Sequence/ID table | Object type, name, current value |
| Timestamps and messages | Time types, serialization, error length limits |
| Table prefix/schema | Do runtime DAO table references match migrations? |
| Permissions | `SELECT`/`INSERT`/`UPDATE`/sequence privileges |
| Migration history | Which DDL version ran; any partial runs? |

PostgreSQL can inspect metadata object types:

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS object_name,
    c.relkind AS object_kind
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'task_meta'
ORDER BY c.relname;
~~~

`relkind='S'` is a native sequence; `relkind='r'` is a table. `TASK_SEQ` is not guaranteed to be a native sequence: check actual DDL/incrementers before granting privileges or modifying structure.

**Do not delete old metadata just to "let startup succeed."** Dropping `TaskExecution`/`JobExecution` breaks auditing, parent–child lineage, and restart checkpoints.

## 13. Spring Batch JobRepository Is a Separate Schema

If the application uses Spring Batch, compare both groups:

~~~text
task_meta/
  TASK_EXECUTION
  TASK_EXECUTION_PARAMS
  TASK_TASK_BATCH

batch_meta/
  BATCH_JOB_INSTANCE
  BATCH_JOB_EXECUTION
  BATCH_JOB_EXECUTION_PARAMS
  BATCH_STEP_EXECUTION
  BATCH_STEP_EXECUTION_CONTEXT
  ...
~~~

Spring Batch requires checking **identifying JobParameters**, `JobInstance`, `JobExecution`, `StepExecution`, `ExecutionContext`, transactions, and serializers.

A `JobInstance` is identified by **Job name + identifying parameters**. If a retry injects a random timestamp into an identifying `run.id`, Batch creates a new `JobInstance`, which is **not a true restart** of the previous run.

Test against this matrix:

| Scenario | Batch Metadata | Task Metadata |
|---|---|---|
| Job completes | `COMPLETED` | TaskExecution ends successfully per policy |
| Step fails | `FAILED`, committed checkpoint | Exit code reflects error when configured |
| Restart same key | Same `JobInstance`, new `JobExecution` when valid | New `TaskExecution` |
| Already completed job | Does not rerun same `JobInstance` | Task attempt may fail/reject |
| JVM receives SIGKILL | May remain `STARTED` | May lack `END_TIME` |

**Upgrading Batch without testing restarts from real checkpoints** is a major risk, especially for long-running tasks or tasks with external side effects outside the DB.

## 14. Migrations: Run DDL Separately Before Running the Task

When schemas are managed by Flyway/Liquibase/DBAs, do not let every task JVM run `CREATE/ALTER TABLE` at startup.

~~~mermaid
sequenceDiagram
    participant P as CI/CD
    participant M as Schema Migrator
    participant DB as Database
    participant S as Scheduler
    participant T as Spring Cloud Task

    P->>DB: Backup/snapshot + check migration version
    P->>M: Run with migration role
    M->>DB: DDL, sequences, indexes, GRANTs
    DB-->>M: Commit migration
    M-->>P: Success
    P->>S: Allow new artifact to run
    S->>T: Launch task with runtime role
    T->>DB: TaskRepository/Batch/business DML
    T-->>S: Exit code
~~~

Example on releases supporting these properties:

~~~yaml
spring:
  main:
    web-application-type: none
  cloud:
    task:
      name: daily-close-task
      initialize-enabled: false
  batch:
    jdbc:
      initialize-schema: never
  sql:
    init:
      mode: never
~~~

`spring.cloud.task.initialize-enabled` belongs to Task; `spring.batch.jdbc.initialize-schema` belongs to Boot-managed Spring Batch auto-init; `spring.sql.init.mode` is Boot's generic SQL initializer. They **do not replace each other**. Verify against the target version, especially when Flyway/Liquibase starters are present.

Principles:

- Migrations run under a role with DDL privileges; runtime only has required DML privileges.
- Diff old vs. new DDL per **dialect**; never apply H2 scripts to production PostgreSQL.
- Keep backups and perform **restore rehearsals**, not just application artifact rollbacks.
- If old and new workers overlap, design **expand → migrate → contract** DDL when needed.
- Smoke test TaskRepository and Batch JobRepository using runtime credentials after migration.

## 15. Exit Codes and Single-Instance Behavior Change Easily

### 15.1. Batch Job Exit Code

Spring Cloud Task/Batch integration provides:

~~~properties
spring.cloud.task.batch.fail-on-job-failure=true
~~~

If a Batch Job reaches `FAILED`, this setting can make the task return a non-zero exit code. Verify version, integration wiring, and the actual runner. Never rely merely on seeing the word `FAILED` in a log line.

### 15.2. Closing the Context

`spring.cloud.task.closecontextEnabled` can control closing the context after the task depending on version. When the application calls `SpringApplication.exit(context)` itself, verify you do not double-close and cause unwanted behavior. If executors, telemetry exporters, or message consumers exist, await/close resources cleanly in the lifecycle.

### 15.3. Single-Instance

Keys documented across multiple releases:

~~~properties
spring.cloud.task.single-instance-enabled=true
spring.cloud.task.single-instance-lock-ttl=60000
spring.cloud.task.single-instance-lock-check-interval=500
~~~

Values are **illustrative only**; verify time units, TTL/defaults, and lock algorithms in the target release. Test two JVMs with the same task name, killed workers, and lease/lock timeouts.

Single-instance by task name **does not replace unique business keys**. A task with a different name can still close the same day, or a retry can repeat side effects before TaskRepository finalizes status.

## 16. Phased Safe Upgrade Procedure

~~~mermaid
flowchart TD
    A["Capture baseline"] --> B["Pick compatible Boot + Cloud train"]
    B --> C["Compare release notes, APIs, properties"]
    C --> D["Update BOM, inspect resolved dependencies"]
    D --> E["Compile + context + config tests"]
    E --> F{"Pass?"}
    F -- "No" --> X["Fix on staging"]
    F -- "Yes" --> G["Staging schema migration"]
    G --> H["Task/Batch integration + crash tests"]
    H --> I{"Pass?"}
    I -- "No" --> X
    I -- "Yes" --> J["Canary with safe business key"]
    J --> K["Observe outcomes, errors, latency"]
    K --> L{"Meets criteria?"}
    L -- "Yes" --> M["Controlled rollout"]
    L -- "No" --> N["Stop/rollback or forward-fix"]
~~~

### A. Pre-Upgrade Inventory

- Boot plugin/parent, Cloud BOM, resolved Task/Batch/Framework versions.
- Build/runtime Java, Docker image digest, JDBC driver, and database server.
- Active `spring.cloud.task.*` and `spring.batch.*` properties; never store secret values.
- TaskRepository/JobRepository DDL, migration version, and sequence state.
- Sample successful/failed `TaskExecution` and Batch `JobExecution`/`StepExecution` records.
- Scheduler concurrency, connection pools, resource/timeout limits, OS exit codes.

### B. Executing Dependency Upgrades

- Change Boot/Cloud **per the compatibility matrix**; never bump individual Spring artifacts to latest arbitrarily.
- Remove obsolete version overrides; document reasons for any mandatory overrides.
- Check `runtimeClasspath`, not just `compileClasspath`.
- For major upgrades, read the migration guides for **Boot, Cloud Task, Batch**, and the JDK.

### C. Testing APIs, Configs, and Database

- Compile callers of `TaskExecutionListener`, `TaskConfigurer`, `JobOperator`, and custom DAOs.
- Diff configuration metadata, test old/new keys, and check defaults.
- Verify the auto-configuration bean graph when multiple `DataSource`s exist.
- Run migrations under the migration role; smoke test under the runtime role.
- Run success, failure, retry, concurrency, and `SIGKILL` tests.

### D. Canary and Rollout

- Run a workload with a clear, safe business key.
- Reconcile logs, `TaskExecution`, `JobExecution`, business output, and exit codes.
- On schema mismatches or rising errors, halt rollout and trigger the planned rollback/forward-fix.

## 17. Mandatory Test Table Before Approving an Upgrade

| Test Case | Passing Criteria |
|---|---|
| Dependency graph | No unexpected Spring Cloud/Batch/Framework version mismatches |
| Boot context | Correct beans for TaskRepository/TaskExplorer/DataSource/TransactionManager |
| Task success | Accurate start/end timestamps and exit code |
| Task failure | Exception observed; exit code matches policy |
| Task ID allocation | Multiple tasks do not collide on IDs; ID sequence/table works |
| Runtime DML-only | Startup does not attempt DDL when external migrations manage schema |
| Batch failure | `JobExecution.status=FAILED`; task exit reflects error when required |
| Batch restart | Identifying parameters stay stable; checkpoint resumes accurately |
| Single-instance | Two JVMs with same name enforce locking as designed |
| Async work | Runner awaits futures; neither exits early nor hangs forever |
| Crash after commit | Retry does not duplicate data |
| Parent/child | Task lineage and Batch mapping remain valid with workers |
| Security | Secrets never leak into `TaskExecution` arguments or logs |
| Observability | Trace/log/metric and repository correlation remain intact |

**Do not stop at "the task ran once and succeeded."** Many regressions only show up in `onTaskFailed`, transaction rollbacks, Batch restarts, shutdown, and JVM exit codes.

## 18. Diagnosing Common Post-Upgrade Errors

| Symptom | Suspect | How to Check |
|---|---|---|
| `NoSuchMethodError` / `NoClassDefFoundError` | Binary API/dependency mismatch | Dependency tree/insight inside runtime image |
| `UnsupportedClassVersionError` | Runtime Java version too old | `java -version` directly inside the container |
| TaskRepository bean missing | Auto-config or `TaskConfigurer` changed | Condition report, starters, and bean graph |
| Property has no effect | Key deprecated/removed or overridden | Metadata diff, active profiles, target docs |
| Runtime attempts `CREATE TABLE` | Init property/bean changed | SQL logs, migration config |
| `relation TASK_EXECUTION does not exist` | Wrong DDL/schema/tablePrefix | Check catalog, search path, DataSource |
| `permission denied for sequence` | Changed ID allocator or grants | Sequence/table type and runtime grants |
| Batch Job fails to launch | Incompatible API/schema/params | `JobOperator`, `JobRepository`, identifying params |
| Batch FAILED yet process exits 0 | Batch failure mapping disabled | Test `fail-on-job-failure` and actual exit code |
| Task stays Running after runner finishes | Web server/executor keeps JVM alive | `WebApplicationType.NONE`, threads/shutdown |
| Single-instance lock stuck | TTL/lock DAO/schema changed | Check Task lock config and crash tests |
| Retry duplicates data | Broken business idempotency or `JobInstance` identity | Unique business keys, checkpoints, outbox |
| Cannot read old checkpoints | DDL/serializer/Batch migration issue | Compare `ExecutionContext` with target schema |

**Never "fix" issues by wiping metadata tables or granting overly broad DB privileges.** That hides bugs, destroys task/job history, and breaks restartability.

## 19. Practice: Building a Comparison Matrix for an Upgrade

Suppose a project runs Spring Boot `3.5.x` + Spring Cloud `2025.0.x` and wants to evaluate upgrading to Boot `4.2.0` + Cloud `2026.0.0`. This is a **learning scenario**; jumping across major versions directly may not fit every application, so read migration guides and consider intermediate steps.

1. **Save baseline:** JDK/image, BOM, Task/Batch versions, runtime graph, DDL, and property keys.
2. **Pick target:** check matrix, security support, JDK, and JDBC driver.
3. **Update BOM** on a separate branch; do not override Task version arbitrarily.
4. **Analyze APIs:** `TaskExecutionListener`, `TaskConfigurer`, Spring Batch `JobLauncher`/`JobOperator`.
5. **Diff properties:** initialization, table prefix, Batch job name, exit policy, closecontext, single instance.
6. **Staging migration:** compare TaskRepository/JobRepository schemas and old checkpoints.
7. **Smoke test** with a finite non-web application:

~~~bash
java -jar daily-close-task.jar \
  --spring.main.web-application-type=none \
  --date=2026-11-23
~~~

8. **Inject failures** in the runner and a Batch Step; inspect metadata and OS exit code.
9. **Retry with the same business key**, confirming no duplicate data; test `JobInstance` restart.
10. **Canary** with safe data, monitoring logs/metrics/TaskRepository/JobRepository before broad rollout.

Upgrade handoff table:

| Item | Evidence |
|---|---|
| Boot/Cloud matrix | Train link and target patch |
| Resolved dependencies | Maven/Gradle report |
| API/migration notes | List of call sites and changes |
| Property diff | Keys/types/defaults and binding tests |
| Schema | Migration version, DDL diff, permissions |
| Runtime | `TaskExecution` + process exit code |
| Batch | `JobExecution`/`StepExecution` restart result |
| Business state | Unique keys and idempotency tests |
| Rollback | Image digest, backup/restore rehearsal |

## 20. Common Misconceptions

### "Cloud train 2026.0.0 means Task is also 2026.0.0"

**False.** The BOM train has its own version; Spring Cloud Task inside train `2026.0.0` is `5.1.0`.

### "Passing build means it's compatible"

**Not enough.** Runtime repositories, SQL, exit codes, and Batch checkpoints still must be verified.

### "Same property name means same default and behavior"

**Not guaranteed.** Property binders, profiles, bean conditions, and defaults can all change.

### "Converting camelCase to kebab-case keeps every old property working"

**False for removed keys.** Relaxed binding does not replace reading migration notes.

### "Spring Batch restart automatically guarantees exactly-once"

**No.** Checkpoints only help within configured boundaries; external side effects and business keys still require idempotency.

### "Rolling back the JAR is enough if the new schema fails"

**False if the migration isn't backward-compatible.** You need rollback/forward-fix plans covering the database as well as old and new workers.

## 21. Pre-Production Checklist

- [ ] Baseline and target identified for Java, Boot, Cloud, Task, Batch, driver, and DB.
- [ ] Boot/Cloud release train compatibility verified against official sources.
- [ ] BOM and dependency graph resolved with no unintended overrides.
- [ ] Public/customization APIs compile and deprecated/removed methods checked.
- [ ] Property keys, defaults, types, aliases, and binding behavior cross-checked.
- [ ] TaskRepository/JobRepository DDL matches target version and dialect with migrations ready.
- [ ] Runtime role has least-privilege grants; sequences and `tablePrefix` match schema.
- [ ] Tested task success, failure, exit codes, context shutdown, and async completion.
- [ ] Tested Batch Job failure, identifying parameters, and restart/checkpointing.
- [ ] Tested concurrent tasks, single-instance locking, and crash recovery.
- [ ] Business idempotency/unique keys protect retries.
- [ ] Secrets do not appear in command-line arguments, TaskRepository, or logs.
- [ ] Canary run completed with evaluation criteria and rollback/forward-fix plans ready.

**Conclusion:** To upgrade **Spring Cloud Task** reliably, start from a supported **Spring Boot ↔ Spring Cloud BOM** pair, confirm **actual resolved artifact versions**, reconcile **valid APIs and configs**, and verify **DDL, lifecycle, exit codes, Spring Batch, and retries**. Only when a finite task actually runs, records state, recovers, and completes business work accurately can an upgrade be considered operationally sound.

### References

- [Spring Cloud — release train compatibility](https://spring.io/projects/spring-cloud/)
- [Spring Cloud 2026.0.0 announcement](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/)
- [Spring Cloud Release reference](https://docs.spring.io/spring-cloud-release/reference/)
- [Spring Cloud Task reference](https://docs.spring.io/spring-cloud-task/reference/)
- [Spring Cloud Task 3.2 versioned reference](https://docs.spring.io/spring-cloud-task/reference/3.2/)
- [Spring Cloud Task Batch integration](https://docs.spring.io/spring-cloud-task/reference/batch.html)
- [Spring Boot dependency management](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html)
- [Spring Boot database initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html)
- [Spring Batch JobLauncher API](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/launch/JobLauncher.html)
- [Spring Batch metadata schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html)
