# Choosing a Metadata Database vs. Other Mechanisms in Spring Batch

When building a batch job, development teams often focus on `ItemReader`, `ItemProcessor`, and `ItemWriter`, treating where **execution metadata** is stored as a mere configuration detail. However, choosing metadata storage is a **design decision that directly affects restarts, concurrent runs, multi-node operations, failure investigation, and infrastructure costs**.

For example, suppose a job processing 2 million transactions fails after committing 1.5 million. With a persistent `JobRepository` and accurate checkpoints, it can resume from the remaining portion. If it only kept transient state in memory and the process died, the data needed to restart is gone. The system would then have to rerun from the beginning and rely on idempotency, or use a separate checkpoint mechanism built by the application itself.

In the **Design Decisions** section of **Spring Batch Core Processing**, we answer: **when should you use a relational database for Spring Batch metadata, when is an ephemeral/stateless repository sufficient, and which parts of `JobRepository` can—and cannot—be replaced by mechanisms outside Spring Batch?**

## 1. What Is Metadata in Spring Batch?

**Batch metadata** is data describing execution: which job ran, with which parameters, in what status, which steps completed, which failed, and what context must be restored on restart.

```text
Job definition: importOrdersJob
           |
           v
JobInstance (job name + identifying JobParameters)
           |
           +-- JobExecution #101, FAILED
           |       |
           |       +-- StepExecution #501
           |               status=FAILED
           |               readCount=1500000
           |               context={reader position, ...}
           |
           +-- JobExecution #102, COMPLETED (restart)
                   |
                   +-- StepExecution #502
                           status=COMPLETED
```

Core components:

| Component | What Does It Store? | Role During Recovery |
| --- | --- | --- |
| `JobInstance` | Logical job identity, defined by job name and identifying `JobParameters` | Groups executions belonging to the same logical run |
| `JobExecution` | A single execution attempt, timestamps, status, exit status, failures | Indicates whether a restart is allowed and which attempt failed |
| `StepExecution` | Per-step status, read/write/filter/skip/commit/rollback counters | Identifies which step needs to run next and which already completed |
| `ExecutionContext` | Persisted key/value state at job or step scope | Restores reader/writer positions, tokens, checkpoints, and other state |
| `JobParameters` | Business period, input, tenant, version, identifying values | Determines whether to restart the same instance or launch a new instance |

`JobRepository` is the central interface Spring Batch uses to manage metadata. `JobExplorer` is typically used to **read and query** metadata, while `JobLauncher` or `JobOperator` launches and operates jobs depending on version and configuration.

Crucial point: metadata **is not the processed business data itself**. `BATCH_STEP_EXECUTION.WRITE_COUNT=1000` does not guarantee that 1,000 unique business records exist in the target system. Metadata enables framework execution and restarts; verifying output data still requires unique keys, transactions, manifests, and business reconciliation.

## 2. Metadata Storage Options to Distinguish

Not all options are equivalent implementations you can swap freely in production. Some preserve the full `JobRepository` contract, some only suit **jobs that never need restarts**, and others **complement** the repository rather than replacing it.

| Option | Nature | State Across Process Restart | Best Suited For |
| --- | --- | --- | --- |
| **JDBC `JobRepository` on a persistent RDBMS** | Repository implementation using `BATCH_*` tables in PostgreSQL, MySQL, Oracle, SQL Server, etc. | Yes, if DB and metadata are retained | Production batch jobs needing restarts, auditing, multiple executions, or multiple nodes |
| **JDBC `JobRepository` on an embedded in-memory DB** | Still a JDBC repository, but DB lives in process/test RAM | Usually lost when DB/process terminates | Unit/integration tests, demos, short jobs needing no post-process history |
| **JDBC on a file-backed embedded DB** | Embedded DB persisting files on disk | Can survive process restart if files remain, with operational limits | Demos/labs or tiny workloads with explicit backup policies |
| **Resourceless repository** | Lightweight repository not backed by persistent DB metadata, available in newer Spring Batch versions | No durable basis to restart after process death | Simple, isolated tasks needing no job history/restart; verify exact version |
| **Custom `JobRepository`** | Self-implemented metadata storage contract | Depends on implementation | Specialized cases with heavy design, testing, and maintenance capacity |
| **Scheduler/orchestrator, audit store, logs** | External orchestration and logging tools | May maintain their own history | **Supplementary**; does not inherently replace Spring Batch metadata/checkpoints |

A common confusion: **in-memory H2 is not the same as a resourceless repository**. In-memory H2 still uses the JDBC schema and transactions of `JobRepository`; data is simply lost when the H2 lifecycle ends. Conversely, a resourceless repository is designed without JDBC metadata persistence, so features relying on durable state and restarts have explicit limitations.

### Version Dependencies

Examples in this lesson use **Spring Boot 3.x and Spring Batch 5.x** for JDBC configuration. Versions 5.x and 6.x have differences in APIs, packages, lightweight repository support, and configuration. Specifically, do not take `MapJobRepositoryFactoryBean` from legacy Spring Batch docs and treat it as a default in Spring Batch 5/6. When considering a resourceless or custom repository, verify the **exact version** your application runs and the feature limits of that implementation.

## 3. Why Is a JDBC Metadata Database Usually the Production Default?

Using a relational database as `JobRepository` lets Spring Batch persist metadata with the transaction, locking, and durability properties production batches typically need.

```text
          Spring Batch Job
          /             \
         v               v
   Business data        JobRepository JDBC
  (orders/report)       (BATCH_* metadata)
         |               |
         +-------+-------+
                 |
          Persistent database
          / backup / HA / audit
```

With a properly operated RDBMS, you gain:

1. **State survives JVM/Pod death:** committed execution metadata and context do not depend on process memory.
2. **Grounded restarts:** steps can resume from context updated by `ItemStream` at checkpoint boundaries.
3. **Job history visibility:** `JobExplorer`, operational dashboards, and read-only queries can inspect past executions.
4. **Partial concurrency guarding:** the repository uses `JobInstance` identity and versioned metadata updates to curb unauthorized concurrent runs of the same instance.
5. **Multi-node support:** processes sharing a persistent repository configuration see the same metadata; additional orchestration and locking are still needed in many scenarios.
6. **Governed operations:** databases come with established backup, monitoring, access control, retention, schema migration, and disaster recovery policies.

**A JDBC repository does not automatically guarantee end-to-end exactly-once.** If a writer calls external APIs or writes to object storage outside the DB transaction, committed metadata does not mean external side effects were recorded at the same instant. You still need idempotency, outboxes, manifests, or business reconciliation.

## 4. What Do the `BATCH_*` Tables Store?

With the standard Spring Batch JDBC schema, the core tables include:

| Table | Typical Contents | Question Answered |
| --- | --- | --- |
| `BATCH_JOB_INSTANCE` | Instance ID, job name, and identifying key | Which job instance owns this business period? |
| `BATCH_JOB_EXECUTION` | Execution ID, timestamps, status, exit code/message | Which run failed or completed? |
| `BATCH_JOB_EXECUTION_PARAMS` | Parameters, types, identifying flag | Which input/period/version did the job run with? |
| `BATCH_STEP_EXECUTION` | Step name, status, read/write/skip/commit/rollback counters | How many items did each step process? |
| `BATCH_JOB_EXECUTION_CONTEXT` | Job-scoped context snapshot | What state must be restored at job level? |
| `BATCH_STEP_EXECUTION_CONTEXT` | Step-scoped context snapshot | What checkpoints do readers/writers hold? |

Some schemas also use sequences/tables for ID generation; exact names and details depend on the database and Spring Batch version. **Use the DDL bundled with your exact dependency version**—never copy schemas across major versions without checking migrations.

### Querying Execution History

Read-only SQL aggregating across executions and steps:

```sql
SELECT
    ji.JOB_NAME,
    ji.JOB_INSTANCE_ID,
    je.JOB_EXECUTION_ID,
    je.START_TIME,
    je.END_TIME,
    je.STATUS AS JOB_STATUS,
    se.STEP_NAME,
    se.STATUS AS STEP_STATUS,
    se.READ_COUNT,
    se.WRITE_COUNT,
    se.COMMIT_COUNT,
    se.ROLLBACK_COUNT
FROM BATCH_JOB_INSTANCE ji
JOIN BATCH_JOB_EXECUTION je
  ON je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
LEFT JOIN BATCH_STEP_EXECUTION se
  ON se.JOB_EXECUTION_ID = je.JOB_EXECUTION_ID
WHERE ji.JOB_NAME = 'importOrdersJob'
ORDER BY je.JOB_EXECUTION_ID DESC;
```

Because one `JobExecution` can have multiple `StepExecution`s, the `JOIN` output may contain multiple rows per execution. When counting job runs, do not count each step row as a separate job execution.

Never manually update `BATCH_JOB_EXECUTION.STATUS` or rows in `BATCH_STEP_EXECUTION_CONTEXT` to "unlock" a restart. That state is managed by the framework; hand-editing it can cause restarts to resume at wrong offsets, skip data, or create duplicate output.

## 5. Production JDBC `JobRepository` Configuration Example

With **Spring Boot 3.x, Spring Batch 5.x**, and PostgreSQL, a straightforward setup can share one `DataSource` for metadata and business data (when security and isolation rules permit).

### 5.1. Gradle Dependencies

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}
```

Do not pin a Spring Batch version different from Spring Boot's dependency management without verifying compatibility. When using Spring Batch 6 or another Spring Boot generation, adjust code, imports, and configuration to match that version.

### 5.2. `application.yml`

```yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/batch_runtime
    username: ${BATCH_DB_USER}
    password: ${BATCH_DB_PASSWORD}
    hikari:
      maximum-pool-size: 12

  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: never

app:
  batch:
    checkpoint-enabled: true
```

`app.batch.checkpoint-enabled` is an **illustrative application property**; Spring Batch has no global switch with that name. State saving depends on each `ItemStream`, step configuration, and repository. Never treat a custom property as an automatic switch that enables restarts.

Meaning of the Spring Boot settings:

- `spring.datasource.*`: database connection settings used by Boot when no separate datasource is declared.
- `spring.batch.jdbc.initialize-schema=never`: production does not run `BATCH_*` schema creation scripts at every startup. Schemas must be provisioned via migrations or approved deployment procedures.
- `spring.batch.job.enabled=false`: prevents Spring Boot from auto-launching discovered jobs on application context startup when jobs are triggered intentionally by a scheduler, API, or CLI. This **does not disable** the job launcher when called directly by the application.
- Hikari pool size is purely illustrative; ideal sizing depends on thread/chunk/partition counts and DB characteristics. Do not inflate pools unboundedly because metadata feels slow.

**Note:** the `BATCH_*` schema must exist and match your Spring Batch version before jobs run. Use Flyway/Liquibase or an approved DDL pipeline; Spring Batch ships per-database schema scripts, but auto-creating tables in production can require overly broad DDL privileges and introduce upgrade risks.

### 5.3. A Job Restartable by Business Period

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class ImportOrdersConfiguration {

    @Bean
    Step importOrdersStep(JobRepository repository,
                          PlatformTransactionManager transactionManager) {
        return new StepBuilder("importOrdersStep", repository)
            .tasklet((contribution, context) -> {
                String businessDate = contribution.getStepExecution()
                    .getJobParameters().getString("businessDate");
                if (businessDate == null) {
                    throw new IllegalArgumentException("Missing businessDate");
                }

                // Illustrative processing entry point, not a full file-import pipeline.
                System.out.println("Processing businessDate=" + businessDate);
                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
    }

    @Bean
    Job importOrdersJob(JobRepository repository, Step importOrdersStep) {
        return new JobBuilder("importOrdersJob", repository)
            .start(importOrdersStep)
            .build();
    }
}
```

In this example, `JobRepository` is supplied by Spring Batch/Boot auto-configuration, and `StepBuilder` accepts the transaction manager explicitly per the Spring Batch 5.x API. This tasklet **does not save line positions**, as it only demonstrates launching. A job reading millions of rows requires readers/writers with `ItemStream`, checkpointing, and dedicated transactions.

Launching for a period:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-16") // identifying by default
    .addString("sourceVersion", "file-v7")   // identifying
    .toJobParameters();

JobExecution execution = jobLauncher.run(importOrdersJob, parameters);
```

`jobLauncher` and `importOrdersJob` in the snippet are injected beans. If an instance for the same parameters is already `COMPLETED`, Spring Batch normally refuses to run it again. If it previously ended `FAILED`/`STOPPED` and the job allows restarts, a subsequent execution attaches to **the same `JobInstance`**. Never attach a new identifying `UUID` on each restart if you want to use existing checkpoints.

## 6. Same Database for Metadata and Business Data or Separate?

Even after choosing a JDBC repository, you must decide whether metadata lives in **the same database/datasource** as business tables or in a separate database.

### Option A: Shared Database and Coordinated Transactions

```text
       Spring Batch Step
          /       \
         v         v
  Business tables   BATCH_* tables
         \         /
          \       /
          Transaction boundary
             same database
```

**Pros:** fewer connections and less infrastructure; in properly configured chunks, business writes and checkpoints can participate in the same local database transaction. Rolling back a chunk prevents updating the reader's position when the chunk's business changes failed to commit.

**Cons:** separating privileges between metadata and business data can be harder; heavy batch loads impact the metadata store directly; schema upgrades or DB incidents affect both layers.

### Option B: Dedicated Database/Schema for Metadata

```text
          Spring Batch Step
           /           \
          v             v
   Business database    Metadata database
   (orders/report)      (BATCH_* tables)
        |                     |
   Transaction A         Transaction B
```

**Pros:** clean separation of permissions, retention, backups, scaling, and monitoring; multiple apps can share metadata infrastructure without granting broad access to business tables.

**Critical con:** if the step writes business data to DB A while the repository persists checkpoints to DB B using two independent local transactions, **there is no automatic atomic commit across them**. One side can commit before the other fails. On restart, the application may re-read already-written data or miss items depending on how checkpoints and transactions are arranged.

Distributed transactions exist in some architectures, though they add complexity and are not universally compatible. In most cases, design **idempotent** writers with business keys/unique constraints and reconciliation. If strict atomicity between metadata and business data is a hard requirement, verify the exact transaction wiring and capabilities of your datasources and transaction managers rather than looking only at database names.

### Separating `DataSource`s Requires Explicit Bean Wiring

Spring Boot provides mechanisms to designate the Spring Batch datasource when multiple `DataSource` beans exist, using annotations or configs appropriate to your Boot version. However, selecting a datasource for **the repository** does not automatically move **the step writer's** transaction to the same database. In Spring Batch 5.x, builders like `.chunk(size, transactionManager)` accept a specific transaction manager. When using multiple transaction managers, verify which target each step writes to and where checkpoints are stored.

Prove the desired behavior with an integration test that injects a failure **after at least one chunk has committed**, not merely by checking that the context boots.

## 7. Embedded Databases: When Are They Appropriate?

An embedded database like H2 is very useful in demos and tests:

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:batch_test;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
  batch:
    jdbc:
      initialize-schema: always
```

This uses in-memory H2 with the matching Spring Batch schema. It supports **real integration tests** exercising `JobRepository`, transactions, and checkpoints within the test database lifecycle. Once the process or in-memory DB shuts down, metadata disappears.

### When Appropriate

- Learning how Batch persists `JobInstance`, `JobExecution`, `StepExecution`, and contexts.
- Integration tests needing a JDBC repository where data can be created/wiped per test.
- Short-lived tools/demos that make no promise of resuming after process termination.

### When Inappropriate

- Long-running production jobs needing restarts after failures or Pod evictions.
- Multi-node deployments that must share one metadata history.
- Workloads needing backups, retention, and multi-period auditability across deployments.
- Verifying PostgreSQL/Oracle/production-specific SQL, locking, or isolation behavior that H2 does not faithfully emulate.

**File-backed H2** can retain metadata across process restarts if the volume/path persists, yet it still has limitations around concurrency, HA, backups, recovery, and multi-container access. A persisted DB file **does not automatically make it equivalent to a properly operated production RDBMS**.

In CI, when production schemas, transactions, or locking matter to the test, use Testcontainers with the real target database rather than relying entirely on H2.

## 8. When Is a Stateless (Resourceless) Repository Used?

Newer Spring Batch versions include **`ResourcelessJobRepository`** for cases where maintaining a metadata database is undesirable. It is a worthwhile option for simple jobs where state limitations are acceptable.

Examples worth considering:

- Generating a small file from fully re-readable input with no irreversible side effects.
- Running a short, idempotent tasklet in a single process on an external schedule with no need for Spring Batch run history.
- Pipelines where every invocation is an isolated unit, retries/reruns from scratch are orchestrated externally, and re-reading/re-writing is designed to be safe.

### Limitations You Must Explicitly Accept

1. Do not rely on it to **restart from checkpoints after a process crash** as you would with persistent JDBC metadata.
2. Do not treat it as a store for **durable job history** across deployments.
3. Do not use it as a **multi-process/multi-node coordinator** to prevent duplicate period runs.
4. Check concurrency support and usage scope for your exact Spring Batch version; lightweight repositories carry simpler contracts than JDBC.
5. If auditing is required, persist business run history to another system; ephemeral container logs do not satisfy durable audit requirements.

Never pick a resourceless repository simply to **avoid creating `BATCH_*` tables** when the job still has restart SLAs or non-idempotent targets. The cost of "saving a database" merely shifts into manual recovery logic, missed-period monitoring, and duplicate-data cleanup.

### Dropping the Metadata DB Does Not Mean Dropping State

If an external system tracks progress—such as a `processed_files` table or message offsets—**you have effectively moved state management to another application/infrastructure layer**. You must then explicitly define:

- What constitutes a committed point?
- Is state written **before or after** output genuinely succeeds?
- What prevents two workers from claiming the same period?
- What happens if the process dies between writing output and updating state?
- How are run history and backfills tracked?

That can be a valid architecture, but it cannot be treated as functionally equivalent to a JDBC `JobRepository` merely because both "run jobs."

## 9. Can Schedulers, Orchestrators, Queues, and Logs Replace the Metadata DB?

These components provide **parts of the picture**, but responsibilities must remain distinct:

| Component | Primary Responsibility | Does Not Provide Out of the Box |
| --- | --- | --- |
| `@Scheduled` | Triggers methods on cron/fixed intervals while process is alive | `ItemStream` checkpoints, durable `JobExecution` history |
| Quartz | Persists triggers, misfire handling, schedules, clustering if configured | Spring Batch chunk/step metadata and restart contexts |
| Kubernetes CronJob | Spawns Kubernetes Jobs/Pods on schedule | Committed reader positions inside a batch job |
| Airflow/Control-M/orchestrator | Tracks DAGs, dependencies, schedules, and business periods | Native visibility into Spring Batch chunk internals |
| Message broker | Dispatches requests and redelivers on failure | Proof that all downstream side effects applied once |
| Application logs/traces | Diagnostics, timelines, and correlation | Reliable restartable transaction/checkpoint state |
| Business audit store | Records business events and accepted outcomes | Full `JobRepository` API semantics unless explicitly implemented |

In enterprise systems, a clean division of labor looks like:

```text
Orchestrator / Scheduler
        |
        | businessDate, sourceVersion
        v
Spring Batch JobLauncher / JobOperator
        |
        +--> Spring Batch Job/Step
        |         |
        |         +--> Business data / output
        |         +--> JobRepository JDBC (BATCH_*)
        |
        +--> Audit store / metrics / alerts
```

The scheduler answers **when to launch**. `JobRepository` answers **how far the job/step got, its status, and how to restart**. The audit store answers **which inputs, rules, and outputs were accepted and who/what triggered them**. They link via `businessDate`, `jobInstanceId`, `jobExecutionId`, and correlation IDs, without duplicating roles.

## 10. Is Building a Custom Metadata Repository on Redis/NoSQL Worth It?

Suppose an organization already runs Redis or a NoSQL store and wants to avoid an RDBMS. Do not assume Spring Batch ships a production-ready `JobRepository` for every such store. If no version-matched implementation exists and you replace the JDBC repository, the team must implement **the full contract** for managing `JobInstance`, `JobExecution`, `StepExecution`, versions, and contexts.

Minimum requirements are non-trivial:

- Atomically create `JobInstance` by identifying parameters, preventing two processes from creating duplicates.
- Enforce valid state transitions (`STARTING`, `STARTED`, `FAILED`, `COMPLETED`, etc.).
- Implement optimistic concurrency/version checks to detect conflicting updates.
- Persist `ExecutionContext` accurately at checkpoints; avoid advancing state when output failed to commit.
- Recover and query execution history after process/node crashes.
- Manage serialization and context schema/version evolution.
- Behave reliably under network partitions, retries, and ambiguous timeouts.
- Satisfy performance, monitoring, backup, disaster recovery, and security requirements.

Using a cache with eviction or TTL for checkpoints without careful design can wipe recovery data right when a job needs to restart. Using a Redis lock purely to guard the launcher **does not replace** execution metadata.

A custom repository is only worth considering under extraordinary infrastructure constraints, strong long-term testing/maintenance capacity, and an evidence-backed architectural decision. For most enterprise batch systems, Spring Batch's well-supported JDBC repository carries a lower total cost of ownership than writing a custom non-relational repository.

## 11. Transaction Consistency Is the Most Important Criterion

Suppose an order-import job uses chunk size 100. During a run:

```text
Chunk 1: records 1..100     -> output commit + checkpoint
Chunk 2: records 101..200   -> output commit + checkpoint
Chunk 3: records 201..300   -> process crashes before commit
```

With proper checkpointing and transactions, restart resumes right before chunk 3. However, if metadata and business output **do not share an atomic transaction**, two classes of drift can occur:

| Scenario | What Can Happen | Potential Consequence |
| --- | --- | --- |
| Output committed, checkpoint did not | Restart re-reads items already written to target | Duplicates if writer is not idempotent |
| Checkpoint updated, output did not actually commit | Reader reopens at the newer position | Risk of silently skipping/losing data |

A persistent repository **remembers state**, but cannot fix broken application transaction boundaries. To guard against both risks:

1. Ensure transaction manager/datasource wiring for chunks and the repository is crystal clear; when atomicity is needed, favor a transaction boundary covering both business writes and metadata.
2. Use unique business keys, upserts, or idempotent writers—especially against external target systems.
3. For APIs/messaging, use stable idempotency keys, transactional outboxes, and reconciliation where appropriate.
4. Run integration tests injecting failures **after at least one chunk commit** and verify exact final output.

### `saveState` and `ItemStream` Cannot Be Ignored

If readers or writers must restore positions, they must participate in the `ItemStream` lifecycle:

```java
// Illustrative example of a framework-managed reader.
FlatFileItemReader<OrderRow> reader =
    new FlatFileItemReaderBuilder<OrderRow>()
        .name("ordersReader")
        .resource(inputResource)
        .lineMapper(orderLineMapper)
        .saveState(true)
        .build();
```

`OrderRow`, `inputResource`, and `orderLineMapper` are application-supplied components. `name` must be stable so state keys stay consistent; `.saveState(true)` enables checkpoint persistence for restarts. If wrapping an `ItemStream` inside a delegate not automatically recognized by the step, register or delegate `open`, `update`, and `close` properly. **Choosing a JDBC metadata repository is not enough** if the reader/writer fails to save checkpoints or input mutates between runs.

## 12. Concurrency and High Availability (HA)

A common scenario: two Spring Boot instances both configure `@Scheduled(cron = ...)` and fire `JobLauncher` at the same time.

```text
Node A 02:00 -> launch importOrdersJob(businessDate=2026-11-16)
Node B 02:00 -> launch importOrdersJob(businessDate=2026-11-16)
                   |
                   v
          Shared JDBC JobRepository
                   |
           same JobInstance key
```

A shared JDBC repository detects and blocks many concurrent runs of **the same `JobInstance`** via identity and transactions. However:

- If Node A passes `runId=A` and Node B passes `runId=B` as **identifying** parameters, they create two distinct instances processing the exact same November 16 data.
- The repository is not a cluster-wide scheduler leader election for all triggers.
- If two distinct job instances write to the same file/table, you still need output policies and unique keys/locks.
- `STARTED` status can remain orphaned after sudden process crashes; operational procedures must verify real process liveness before restarting.

When **each business period must run only once**, design defense in depth: period/input-based identifying parameters, a distributed scheduler or single trigger source, target database constraints/idempotency, and failure reconciliation.

### Persistent Metadata with Stateless Application Deployments

In Kubernetes, short-lived batch Pods can read/write business data from databases or object storage while storing metadata in an external persistent RDBMS. A new Pod can access the existing `JobRepository` as long as credentials, schemas, and networking remain valid. However, if the reader checkpointed **an offset into the old Pod's local ephemeral file**, the missing file on the new Pod breaks the restart. Successful restarts require **both metadata and input/output resources** to remain accessible—not just the repository database.

## 13. Performance: Is a Metadata Database Really Too Expensive?

In chunk-oriented processing, `JobRepository` updates metadata and contexts at execution/checkpoint milestones. This introduces transaction and I/O overhead. Still, before discarding a persistent repository, measure its actual overhead relative to:

- Source querying and data fetching.
- Processor CPU, serialization, and memory allocation.
- Batched database writes, network/API latency, and transaction locks.
- `ExecutionContext` size and number of serialized keys.
- Commit frequency caused by overly small `chunk size`.
- Metadata DB connection latency and `BATCH_*` table indexing/locking.

Never conclude "JobRepository is slow" simply because logs show many `UPDATE BATCH_STEP_EXECUTION` statements. If chunks commit every single item, increasing chunk size often cuts metadata updates far more than swapping storage engines—though larger chunks trade off longer locks, higher memory, and larger failure rollbacks.

### Optimization Ideas Before Replacing Storage

| Action | Benefit | Risk to Measure |
| --- | --- | --- |
| Tune chunk size appropriately | Cuts commit/metadata round-trips | Longer transactions and larger rollbacks |
| Keep `ExecutionContext` small | Reduces serialization and I/O | Must not drop restart-critical state |
| Tune DB indexes and connection pool | Reduces connection waits, locks, query cost | Oversized pools can overload the DB |
| Separate business and metadata load if needed | Isolates workloads | Cross-DB transactions lose default atomicity |
| Housekeep expired metadata | Curbs table growth and backup cost | Purging too early loses history/restartability |
| Optimize readers/writers and SQL | Boosts real throughput | Must re-verify checkpoints and idempotency |

A batch processing 100 million records does not put 100 million rows in `BATCH_*`: metadata scales primarily with job/step executions and contexts, not per-item events by default. Bottlenecks usually lie in SQL, I/O, or chunk sizing rather than source row volume directly.

## 14. Retention, Auditing, Backups, and Security

### 14.1. How Long Should Metadata Be Retained?

Do not keep metadata forever without a plan, yet never purge it right after a `FAILED` job. Deleting context for an instance that still needs a restart destroys recoverability.

A typical policy covers:

1. **Restartable executions:** retain all instances, executions, steps, and contexts needed.
2. **Past operational lifecycle:** retain per troubleshooting and dashboard SLAs; archive or purge after an approved window.
3. **Long-term business audit:** store in a dedicated audit store capturing business keys, input sources, output manifests/checksums, and launcher/trigger identity.
4. **Backup and recovery:** verify metadata DB backups can actually restore in sync with business data, input, and output snapshots for mid-flight runs.

Cleaning up `BATCH_*` tables must respect foreign key constraints and active executions; never run unguarded scheduled bulk `DELETE`s. A summary audit report in another warehouse **cannot power a Spring Batch restart** once detailed checkpoints are deleted.

### 14.2. Sensitive Data in Metadata

`JobParameters`, `ExecutionContext`, and `EXIT_MESSAGE` can leak sensitive values if developers put them there. Avoid patterns like:

```java
new JobParametersBuilder()
    .addString("apiToken", "secret-token-here")
    .toJobParameters();
```

This persists secrets in metadata tables and exposes them in logs and dashboards. Instead, use a secret manager, workload identity, or short-lived credentials, passing only **references** and non-sensitive business parameters.

Separate database permissions for runtime users (DML needed for metadata) from migration users (DDL). Segregate read permissions on metadata tables too: operators checking status may not need access to raw `ExecutionContext` blobs or stack traces containing internal data.

## 15. Trade-Off Matrix by Requirement

| Requirement / Criterion | Persistent JDBC | In-Memory JDBC | Resourceless / Non-Persistent | Custom External State |
| --- | --- | --- | --- | --- |
| Restart after process crash | Suitable when state/resources remain valid | Unreliable once RAM DB disappears | Unsuitable if durable checkpoints are needed | Suitable only if full contract is built properly |
| Job history across deployments | Yes | Usually no | Not by default | Depends on design |
| Multi-node shared execution state | Supported via shared DB and proper config | Unsuitable | Not a design goal | Complex; must handle concurrency manually |
| Simple test setup | Possible via Testcontainers | Very suitable | Suitable if tests need no metadata | Usually unnecessary |
| Consistent transactions/checkpoints | Can coordinate with business DB | Within test DB scope | No durable DB checkpoints | Depends on custom atomic commit capability |
| Backup/DR | Backed by DB infrastructure | No | No durable history by default | Must design separately |
| Infrastructure cost | Requires DB/schema/ops | Low | Very low for simple jobs | High dev/maintenance cost risk |
| Data loss risk on bad restart | Low if configured properly | High after process crash | High if relying on lost state | Depends on maturity |

### Quick Selection Guide

```text
Does the job need checkpoint-based resume after process/node failure?
                     |
                  +--+--+
                  |     |
                 Yes    No
                  |     |
                  v     v
       Use persistent   Need durable execution history
       JDBC DB          or multi-node coordination?
                        |            |
                       Yes           No
                        |            |
                        v            v
                 Persistent     Consider lightweight/in-memory
                 JDBC DB        repository for small jobs if
                                full rerun from start is safe
```

**Note:** this diagram is an initial decision aid, not a substitute for checking transactions, outputs, compliance, and framework version limits. Even if a job doesn't need a "reader checkpoint" because omitting or duplicating effects isn't allowed, that **never means** you can casually skip durable state or idempotency.

## 16. Four Real-World Scenarios

### Scenario A: Nightly Payment Reconciliation Job

Requirements: 3 million transactions/day; multi-step; must resume from last committed chunk on failure; monitoring dashboard and audit required.

**Recommendation:** JDBC `JobRepository` on a persistent, backed-up RDBMS with managed schemas, identifying parameters using `businessDate`/source version. Checkpointed readers, idempotent writers keyed by transaction ID, and a separate business audit store. If metadata and business DBs differ, thoroughly test transaction boundaries and reconciliation.

Why not in-memory or resourceless? Losing state on process death forces re-running millions of transactions, raising duplicate risk and breaking auditability.

### Scenario B: Generating a Small Report Safe to Rebuild from Scratch

Requirements: reads immutable data, writes a temporary file in seconds; on failure, delete temp file and rerun everything; no internal Batch execution history needed.

**Worth considering:** a version-appropriate lightweight repository, or in-memory JDBC in simple setups. Ensure output files are temporary/versioned, publish only after validation, and ensure reruns do not append or overwrite corruptly. The scheduler/orchestrator still needs to know which trigger failed to re-fire it.

Why can this work? Because **rerunning from scratch is designed to be safe**, requiring no mid-stream recovery. Still maintain an external audit store if long-term compliance requires it.

### Scenario C: Multiple Pods Processing Large Files on Object Storage

Requirements: CronJob spawns Pods; Pods can be evicted; readers process partitions; inputs live in S3; backfills required.

**Recommendation:** external persistent JDBC repository outside Pods, fixed input object versions in parameters, stable partition keys, and idempotent writers. Ensure restarts can reopen resources from a fresh Pod. If using a distributed scheduler, store schedules externally; never expect `JobRepository` to fire missed cron triggers.

The biggest risk is not just the metadata DB, but **partition ranges, reader state, and object versions** shifting between runs, or two Pods publishing to the same output key.

### Scenario D: Architecture Already Has a Workflow Engine and Audit Store

Requirements: orchestrator tracks DAG state, a `business_batch_run` table exists, plus an event log. The team wants to drop `BATCH_*` tables to "avoid storing state twice."

**Considerations:** keep the JDBC repository if using Spring Batch's `ItemStream` checkpoints and restarts. The audit store holds business events and the DAG engine manages scheduling/flow; neither naturally replaces `StepExecutionContext`. If the job is genuinely a single atomic idempotent operation safe to retry from scratch, a lightweight repository can be considered with recovery responsibility explicitly assigned to the orchestrator.

Never delete the repository before clarifying whether the orchestrator knows **which chunk committed** versus merely "task succeeded/failed."

## 17. Testing to Prove Your Metadata Choice Is Sound

A metadata design should never be judged solely by `ApplicationContext` starting cleanly. Test the exact guarantees the chosen option promises.

### 17.1. Real JDBC Repository + Restart

With Spring Batch 5.x, use `@SpringBatchTest`, `JobLauncherTestUtils`, or `JobLauncher` against a test database. Scenario:

1. Input `A001` through `A005`, chunk size 2.
2. First chunk commits `A001`, `A002`; processor/writer throws a controlled error on the next chunk.
3. Verify the first execution is `FAILED` and committed business output holds only the first part.
4. Relaunch with **the exact same identifying `JobParameters`**, same input version, and preserved repository.
5. Verify the second execution is `COMPLETED`, shares the same `JobInstance.id` with a different `JobExecution.id`, and final output holds all 5 business keys.
6. Verify zero duplicates, zero omissions, context applied properly, and previously committed rows were not doubled.

Assertion snippet, assuming `first`, `restarted`, and `jdbcTemplate` are set up:

```java
assertThat(first.getStatus()).isEqualTo(BatchStatus.FAILED);
assertThat(restarted.getStatus()).isEqualTo(BatchStatus.COMPLETED);

assertThat(restarted.getJobInstance().getId())
    .isEqualTo(first.getJobInstance().getId());

assertThat(restarted.getId()).isNotEqualTo(first.getId());

List<String> ids = jdbcTemplate.queryForList(
    "SELECT order_id FROM processed_orders ORDER BY order_id",
    String.class
);
assertThat(ids).containsExactly("A001", "A002", "A003", "A004", "A005");
```

This is an **illustrative assertion snippet** for an integration test, not a full test class; `processed_orders` and failure fixtures must be provisioned in the test environment. If the repository sits in a different database from target data, add a test failing one side at commit time to observe and prove idempotency/reconciliation.

### 17.2. Restart Across Two Separate Processes/Pods

Tests inside a single JVM do not prove recovery across process death. For durable restart targets, test:

- Execution #1 runs on process A, commits several chunks, and is killed/stopped at a test point.
- Keep metadata DB, input object/version, and committed partial outputs intact.
- Start a new process B with compatible configuration/credentials.
- Process B restarts the same `JobInstance` per operational procedure.
- Output reconciles accurately with zero duplicate rows, files, or messages.

If state lived only in in-memory H2 or Pod A's ephemeral local file, this test exposes the architectural gap immediately.

### 17.3. Testing Concurrent Launches

Have two launchers attempt to start the exact same identifying parameters nearly simultaneously. Verify metadata status and proper concurrency/exception handling while ensuring zero duplicate output. Also test two job instances with **different parameters targeting the same business key**, demonstrating that the repository alone does not replace target unique constraints or scheduler locks.

### 17.4. Testing Resourceless or Non-Persistent State

If choosing a lightweight repository, tests must prove the **rerun-from-scratch** contract:

- Kill the process or spawn a fresh invocation after failure; do not expect old checkpoints to reappear.
- Input remains unchanged or version-pinned.
- Partial outputs from failed runs are quarantined or cleaned up per policy.
- Rerunning from scratch yields one accurate final result via idempotency or atomic single-publish.
- External systems detect incomplete periods and re-trigger within SLA.

Never write tests expecting cross-process `JobExplorer` history if the chosen repository does not support it.

## 18. Pre-Deployment Decision Checklist

| Architectural Question | Why It Must Be Clarified |
| --- | --- |
| Can the job run for hours or process millions of items? | Cost of rerunning from scratch may be high |
| Is checkpoint restart required after power loss / Pod kill? | Demands durable state and stable inputs/outputs |
| Can multiple nodes/launchers trigger simultaneously? | Needs shared metadata and period deduplication |
| Is the output idempotent? | Prevents duplicates on retries/restarts or non-atomic commits |
| Can metadata and business data share a transaction? | Determines risk of checkpoint-vs-output drift |
| Are execution history queries and audits needed? | Drives storage, retention, and security choices |
| How is the `BATCH_*` schema created and upgraded? | Prevents startup failures and framework upgrade incompatibilities |
| How are identifying `JobParameters` defined? | Governs restarting an instance vs. starting fresh |
| Do inputs and outputs survive Pod replacement? | Persistent repository alone fails if resources vanish |
| Is there a metadata cleanup policy? | Avoids unbounded DB growth or deleting restartable state |
| Can the team maintain a custom repository if proposed? | Evaluates maintenance cost and consistency risks |
| Have crash/restart and concurrency been tested? | Proves design contracts under real failure conditions |

## 19. Sample ADR for Metadata Decisions

An **Architecture Decision Record (ADR)** helps future engineers understand why a metadata storage mechanism was chosen and which constraints were accepted.

```markdown
# ADR: Metadata repository for importOrdersJob

## Context
- Job processes ~2 million rows/day.
- Pods may restart mid-processing.
- Must resume from committed chunks and retain 90 days of history.

## Decision
- Use Spring Batch JDBC JobRepository on persistent PostgreSQL.
- Use businessDate + sourceVersion as identifying JobParameters.
- Checkpointed ItemStream reader; business-key idempotent writer.
- Scheduler tracks triggers separately; audit store retains output manifests.

## Consequences
- Requires BATCH_* schema migrations, backups, metrics, and housekeeping.
- If metadata and output reside in separate DBs, reconciliation is required.
- Do not use in-memory H2 or non-persistent repositories in production.

## Verification
- Integration test failing and restarting the same JobInstance.
- Kill Pod and restart from a new Pod.
- Test concurrent launches and verify zero duplicate output.
```

Numbers and retention periods in this ADR are **illustrative examples**, not Spring Batch defaults. Real ADRs must reflect your organization's SLAs, data policies, and infrastructure.

## 20. Conclusion

In Spring Batch, choosing a metadata database is a decision about **remembering and recovering execution state**, not merely picking a place to write logs. When production jobs require restarts after failure, checkpoints, multi-execution tracking, or multi-node coordination, **a JDBC `JobRepository` on a persistent RDBMS should usually be the default choice**. In-memory embedded DBs shine in tests and demos; resourceless repositories fit short jobs safe to rerun from scratch; custom repositories are complex architectural undertakings requiring compelling justification and long-term maintenance capacity.

Schedulers, audit stores, and message brokers play vital roles, but **do not automatically replace `JobRepository`**. A sound design ties storage choices to transactions, `ExecutionContext`, input stability, output accessibility, idempotency, retention, and real failure/restart testing.

## References

- [Spring Batch Reference — JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html): repository role, JDBC configuration, and related transactions.
- [Spring Batch Reference — Meta-Data Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): `BATCH_*` tables, `JobInstance`, `JobExecution`, `StepExecution`, and contexts.
- [Spring Batch Reference — Configuring a Job](https://docs.spring.io/spring-batch/reference/job/configuring.html): `JobParameters`, lifecycle, statuses, and restarts.
- [Spring Batch Reference — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): `open`, `update`, `close` contract and checkpoint persistence.
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html): testing executions, steps, restarts, and Spring Batch Test.
- [Spring Boot Reference — Spring Batch](https://docs.spring.io/spring-boot/reference/io/spring-batch.html): auto-configuration, schema initialization, and job launching.
- [Spring Framework Reference — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction boundaries and coordinating transaction managers.
