# Passing Parameters, Configuration, and Parent–Child Identifiers in Remote Partitioning

## 1. Problem and Objectives

A finite **Spring Cloud Task** application may need to process millions of records on a schedule or on demand. When a single process cannot meet the processing deadline, we can combine it with **Spring Batch remote partitioning**: the manager splits work into multiple partitions and dispatches them to independently running workers.

For example, a transaction reconciliation task for `tenant-A` on `2026-11-23`:

- The manager receives the business request, runs a Batch Job, and splits data into four ID ranges.
- Each worker receives one partition, processes its assigned range, and updates its `StepExecution` status.
- The manager awaits each worker's outcome, aggregates the `JobExecution`, and completes the run.
- Spring Cloud Task records metadata for the manager application and for workers when each worker is also launched as an appropriately configured task.

A sound implementation must answer three questions: **which parameters are shared across the entire Job**, **which information is specific to each partition**, and **which IDs link parent–child `TaskExecution`s with `JobExecution`/`StepExecution`**.

Key point: `TaskExecutionId` identifies a task process run; `JobExecutionId` identifies a Batch Job execution; `StepExecutionId` identifies a Step/partition execution. They **cannot be used interchangeably**, even though all three may be represented as integers.

## 2. Distinguishing Remote Partitioning and Remote Chunking

Spring Batch offers different distributed processing models:

| Aspect | Remote partitioning | Remote chunking |
|---|---|---|
| Distribution unit | **Partition / `StepExecution`** | Data **chunk** |
| Reader | Workers typically read data within partition bounds | Manager typically reads/splits chunks and sends them |
| Core payload | `StepExecution` and `ExecutionContext` | Request/reply messages carrying chunk items |
| Checkpoint | Tied to per-partition `StepExecution`/`ExecutionContext` | Depends on chunk, manager, worker, and broker strategy |
| Common failure | Wrong range or `StepExecution`, duplicate partition launches | Message redelivery causing duplicate chunk processing |

This lesson focuses on **remote partitioning**, specifically the model where a manager launches workers as **Spring Cloud Tasks** via a compatible launcher/deployer.

For the dispatch channel, two options are common:

- **Messaging-based:** the manager sends a request message to execute a `StepExecution` over a message broker; workers consume and update status.
- **Task-launching/deployer-based:** `PartitionHandler` launches worker applications via a task launcher/deployer; some Spring Cloud Task Batch lines provide components such as `DeployerPartitionHandler`.

Bean names, constructors, request-passing formats, and configuration properties depend on the versions of Spring Batch, Spring Cloud Task, and Spring Cloud Deployer. Never assume that merely adding a dependency makes the framework split work properly on its own.

## 3. Architecture: TaskRepository and JobRepository

~~~mermaid
flowchart TD
    C["CronJob / API / CLI"] --> M["Manager Spring Cloud Task"]
    M --> MT["TaskRepository: parent TaskExecution"]
    M --> J["Batch JobExecution"]
    J --> P["Manager Step + Partitioner"]
    P --> A["StepExecution partition0"]
    P --> B["StepExecution partition1"]
    P --> D["StepExecution partition2"]
    A --> H["PartitionHandler + launcher"]
    B --> H
    D --> H
    H --> W1["Worker Task 1"]
    H --> W2["Worker Task 2"]
    H --> W3["Worker Task 3"]
    W1 --> WT["TaskRepository: child TaskExecutions"]
    W2 --> WT
    W3 --> WT
    W1 --> JR["Batch JobRepository: step/checkpoint"]
    W2 --> JR
    W3 --> JR
    JR --> M
    W1 --> BD["Business DB / output"]
    W2 --> BD
    W3 --> BD
~~~

| Repository | Stored unit | Purpose |
|---|---|---|
| Spring Cloud Task `TaskRepository` | Manager and worker `TaskExecution`s | Tracks processes, start/end times, exit codes, parent relationships |
| Spring Batch `JobRepository` | `JobInstance`, `JobExecution`, `StepExecution`, `ExecutionContext` | Identifies Jobs/Steps, status, checkpoints, and restarts |
| Business database / output store | Actually processed business data | Ensures outcomes, business keys, and idempotency |

**Manager and workers must share the same Batch metadata context.** In a shared `JobRepository` setup, workers must access the exact database and schema holding the `StepExecution`s created by the manager. If a worker points to a different `JobRepository`, it will fail to locate `StepExecution` or write status into an unrelated store.

One manager `TaskExecution` can have multiple worker `TaskExecution`s; one `JobExecution` has multiple `StepExecution`s. The relationship is not a simple one-to-one mapping.

## 4. Four Categories of Information to Pass

| Category | Example | Appropriate scope |
|---|---|---|
| **JobParameters** | `tenant`, `businessDate`, `revision` | Shared across a `JobInstance`/`JobExecution` |
| **Partition ExecutionContext** | `minId`, `maxId`, `shardId` | Specific to one `StepExecution` |
| **Application/deployment config** | DataSource, Spring profile, worker image, pool size, memory, timeout | Worker runtime environment |
| **Correlation and lineage IDs** | Parent TaskExecution ID, Child TaskExecution ID, JobExecution ID, StepExecution ID | Parent–child and Job/Step tracing |

In addition, there is a **business key** used to prevent duplicate writes (e.g., tenant/date/transaction). The business key never changes merely because a run received a new `TaskExecution` ID.

Core principles:

1. `JobParameters` are **not** JVM environment settings. Passing `--date=...` does not automatically turn it into an identifying `JobParameter`.
2. `ExecutionContext` is **not** shared environment variables. Each `StepExecution` owns its own partition data.
3. `ParentTaskExecutionId` is **not** `JobExecutionId`; they belong to two separate namespaces and repositories.
4. Secrets **must not be stored in `JobParameters`, `ExecutionContext`, or command-line arguments**, as they can be persisted in metadata and logs.
5. Platform execution IDs from Pods/`TaskLauncher` assist operations, but do not replace Task/Batch IDs.

## 5. JobParameters: Identifying the Shared JobInstance

Spring Batch identifies a **`JobInstance`** by **Job name plus the set of `JobParameters` with `identifying=true`**.

Example:

~~~text
Job name: reconcileTransactionsJob

Identifying:
  tenant       = tenant-A
  businessDate = 2026-11-23
  revision     = 1

Non-identifying:
  traceId      = request-15e7
~~~

In Spring Batch 5:

~~~java
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;

JobParameters parameters = new JobParametersBuilder()
    .addString("tenant", "tenant-A", true)
    .addString("businessDate", "2026-11-23", true)
    .addLong("revision", 1L, true)
    .addString("traceId", "request-15e7", false)
    .toJobParameters();
~~~

All partitions of a `JobExecution` share the Job's `JobParameters`; **workers must not launch a new `JobInstance` per partition**. If each worker adds an identifying `run.id` or timestamp, Batch treats them as separate `JobInstance`s, losing the ability to restart the same `JobInstance` and its old checkpoints.

When retrying after failure, preserve identifying parameters if the **business intent is unchanged**. If you need to re-run against a new snapshot or algorithm under an intentional revision, update the business key/identifying parameters accordingly.

**Never make `partitionId` an identifying `JobParameter` to distinguish workers within one `JobExecution`.** Separate `StepExecution` IDs and `ExecutionContext`s already distinguish each worker's slice.

## 6. ExecutionContext: Per-`StepExecution` Partition Data

`Partitioner.partition(int gridSize)` returns a `Map<String, ExecutionContext>`. Each entry consists of a **partition name** and a small dataset describing the work slice for the corresponding `StepExecution`.

Java example splitting IDs into non-overlapping closed ranges:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;

public class IdRangePartitioner implements Partitioner {

    private final long maxId;

    public IdRangePartitioner(long maxId) {
        this.maxId = maxId;
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize <= 0) {
            throw new IllegalArgumentException("gridSize must be positive");
        }

        Map<String, ExecutionContext> partitions = new LinkedHashMap<>();
        if (maxId <= 0) {
            return partitions;
        }

        long size = (maxId + gridSize - 1) / gridSize;
        for (int i = 0; i < gridSize; i++) {
            long first = i * size + 1;
            long last = Math.min(maxId, (i + 1) * size);

            if (first > maxId) {
                break;
            }

            ExecutionContext context = new ExecutionContext();
            context.putLong("minId", first);
            context.putLong("maxId", last);
            partitions.put("partition" + i, context);
        }

        return partitions;
    }
}
~~~

With one million IDs and `gridSize=4`:

| Partition name | `minId` | `maxId` |
|---|---:|---:|
| `partition0` | 1 | 250.000 |
| `partition1` | 250.001 | 500.000 |
| `partition2` | 500.001 | 750.000 |
| `partition3` | 750.001 | 1.000.000 |

All components must follow the same range convention (e.g., `id >= minId AND id <= maxId`). If one worker uses `id < maxId`, boundary records can be dropped; if two workers apply inconsistent boundary math, records can be processed twice.

### What Should and Should Not Be Stored in ExecutionContext

**Should:** ID bounds, shard names, source snapshot IDs, file/manifest references, and small serializable checkpoint values.

**Should not:** millions of records, credentials, datasource objects, connections, HTTP clients, or sensitive data. `ExecutionContext` is persisted in `JobRepository` and must stay serializer-compatible across restarts on potentially upgraded workers.

A **partition name** like `partition0` is meaningful only within the scope of its manager step/`JobExecution`, not as a cluster-wide unique ID.

## 7. Worker Reading JobParameters and StepExecutionContext via @StepScope

Spring Batch lets Step-scoped beans read active Job parameters and `StepExecution` context via **late binding**:

~~~java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class WorkerConfiguration {

    @Bean
    @StepScope
    Tasklet reconcilePartitionTasklet(
            @Value("#{jobParameters['tenant']}") String tenant,
            @Value("#{jobParameters['businessDate']}") String businessDate,
            @Value("#{stepExecutionContext['minId']}") Long minId,
            @Value("#{stepExecutionContext['maxId']}") Long maxId,
            ReconcileService service) {

        return (contribution, chunkContext) -> {
            service.reconcileRange(
                tenant, businessDate, minId, maxId);
            return RepeatStatus.FINISHED;
        };
    }
}
~~~

`ReconcileService` is the application business service to build. Inputs:

- `tenant` and `businessDate`: **shared `JobParameters`**.
- `minId` and `maxId`: **partition-specific `ExecutionContext`**.
- `@StepScope`: instantiates the bean per Step context, avoiding singletons bound to another partition's values.

This pattern assumes the worker has already been attached to a **valid `StepExecution`** by the remote partitioning infrastructure. Merely passing `--min-id=123` to a Java process does not create a `StepExecution` in `JobRepository` or make `stepExecutionContext['minId']` work.

If a partition performs long-running work, the service must use chunk transactions or checkpointed units with idempotent design—never rely solely on a `Tasklet` returning `FINISHED`.

## 8. Manager Step and PartitionHandler

The manager configures a partitioned Step. `PartitionHandler` is the layer that dispatches `StepExecution`s to workers, distinct from `Partitioner`:

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.partition.PartitionHandler;
import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ManagerConfiguration {

    @Bean
    Step managerStep(
            JobRepository jobRepository,
            Partitioner idRangePartitioner,
            PartitionHandler remotePartitionHandler) {

        return new StepBuilder("managerStep", jobRepository)
            .partitioner("reconcileWorkerStep", idRangePartitioner)
            .partitionHandler(remotePartitionHandler)
            .gridSize(4)
            .build();
    }
}
~~~

This snippet targets **Spring Batch 5** and assumes matching `idRangePartitioner` and `remotePartitionHandler` beans exist. It does not yet create a worker launcher, configure a message broker, or choose a worker image.

When using task launching/deployer, specify:

- Resource URI/container image and worker version.
- Mechanism to pass `StepExecution` ID/metadata per the handler's protocol.
- Deployment properties: resource limits, pool/concurrency, timeouts, and retries.
- How the manager collects terminal statuses from `StepExecution` when workers finish or die.
- How configs/secrets are provided to workers.

When using messaging, replace those with broker configuration, request/reply channels, and matching adapters.

**`gridSize` specifies the desired partition count**, not a guarantee that exactly `gridSize` worker JVMs run concurrently. Actual concurrency depends on the handler, quotas, CPU/DB pools, and deployment environment.

## 9. Passing Parameters from Manager to Worker via the Right Channels

| Information | Appropriate channel | Notes |
|---|---|---|
| `tenant`, `businessDate`, `revision` | `JobRepository` → `JobParameters` | One `JobInstance` has a consistent set of identifying parameters |
| `minId`, `maxId`, `shardId` | `JobRepository` → `StepExecutionContext` | Per partition; never copied arbitrarily across workers |
| `StepExecutionId` | Official `PartitionHandler` protocol | Identifies the pre-created `StepExecution` made by the manager |
| Parent `TaskExecution` ID | Spring Cloud Task `parent-execution-id` mechanism | Links parent–child tasks when workers launch as tasks |
| Profiles, log level, timezone, pool size | Environment / config server | Manager and workers are separate JVMs |
| DB passwords and API tokens | Secret manager / Kubernetes Secret / Vault | Keep out of CLI args and metadata |
| CPU/memory/retries | Platform deployment properties | Not identifying `JobParameter`s |
| Trace/correlation ID | Non-sensitive tracing context/metadata | Used for log tracing, not as a business key |

~~~mermaid
sequenceDiagram
    participant O as Scheduler
    participant M as Manager Spring Cloud Task
    participant JR as Batch JobRepository
    participant H as PartitionHandler
    participant W as Worker Spring Cloud Task
    participant TR as TaskRepository

    O->>M: tenant/date/revision
    M->>JR: Create JobExecution + JobParameters
    M->>JR: Create StepExecutions + ExecutionContexts
    M->>H: Dispatch partition StepExecutions
    H->>W: Launch + deployment config + Step ID
    W->>TR: Create child TaskExecution if configured
    W->>JR: Read StepExecution/JobParameters/ExecutionContext
    W->>W: Process assigned partition
    W->>JR: Write status/checkpoints
    W-->>H: Complete or fail
    H-->>M: Aggregate StepExecutions
~~~

This diagram shows the logical information flow. Some handlers pass messages instead of directly launching JVMs; exact ID-passing mechanics and repository write timings vary by release.

**Never invent CLI flags like `--jobExecutionId`/`--stepExecutionId` and assume they are a universal protocol.** Use supported APIs/handlers and verify how they construct worker execution requests.

## 10. Parent–Child `TaskExecution` Identifiers

When both manager and workers are Spring Cloud Task applications, each process can have its own `TaskExecution`:

~~~text
Manager:
  taskExecutionId   = 5001
  taskName          = reconcile-manager

Worker partition0:
  taskExecutionId   = 5002
  parentExecutionId = 5001
  taskName          = reconcile-worker

Worker partition1:
  taskExecutionId   = 5003
  parentExecutionId = 5001
  taskName          = reconcile-worker
~~~

`parentExecutionId` expresses the relationship **worker `TaskExecution` → manager `TaskExecution`**. Spring Cloud Task versions that support this use `spring.cloud.task.parent-execution-id` to pass the parent `TaskExecution` ID to child tasks.

Illustrative example passing parent metadata on a manual launch:

~~~bash
java -jar reconcile-worker.jar \
  --spring.cloud.task.parent-execution-id=5001 \
  --trace-id=reconcile-2026-11-23
~~~

**That command alone is not enough to run remote partitioning**: the worker still needs the protocol to receive its `StepExecution`, Batch repository configuration, and worker Step. In real deployments, the launcher/handler builds the full required context rather than passing only `parent-execution-id`.

| Identifier | Owning system | Meaning |
|---|---|---|
| `parentTaskExecutionId` | Spring Cloud Task / `TaskRepository` | Parent run that launched the worker |
| `childTaskExecutionId` | Spring Cloud Task / `TaskRepository` | Worker process run |
| `jobInstanceId` | Spring Batch / `JobRepository` | Job name + identifying `JobParameters` |
| `jobExecutionId` | Spring Batch / `JobRepository` | A run/restart attempt of a `JobInstance` |
| `stepExecutionId` | Spring Batch / `JobRepository` | A specific `StepExecution`/partition |
| `partitionName` | `Partitioner` | Logical name within the manager Step context |
| `externalExecutionId` | Task launcher/deployer | Container/Pod ID or external platform run ID |
| `businessKey` | Business data | Deduplicates results on retry |

Never substitute `parentTaskExecutionId` for `jobExecutionId`; two numbers may coincide by chance without sharing any equivalence. One manager `TaskExecution` may run multiple Jobs, and each Job has multiple `StepExecution`s.

When `spring-cloud-task-batch` and the appropriate linking listener are integrated, the framework can write `TaskExecution`–`JobExecution` mappings into dedicated metadata. Verify that this mechanism is enabled, the repository has the right schema, and workers actually have the integration configured—never infer mappings solely from task names.

## 11. Environment Configuration and Secrets for Workers

A worker runs in its own JVM/container, so it **does not automatically inherit the manager's beans, `DataSource`, transactions, or Java variables**. It needs its own configuration or configuration explicitly supplied at launch.

Example `application.yml` for the worker:

~~~yaml
spring:
  main:
    web-application-type: none
  application:
    name: reconcile-worker
  datasource:
    url: jdbc:postgresql://db.internal:5432/batchdb
    username: ${DB_USER}
    password: ${DB_PASSWORD}
  cloud:
    task:
      name: reconcile-worker

logging:
  level:
    root: INFO
~~~

`${DB_USER}` and `${DB_PASSWORD}` represent Spring Boot environment placeholders injected via deployment secrets/configs. Never hardcode real credentials; workers must access the shared `JobRepository` schema and business tables with proper privileges.

Critical requirements:

1. **Consistent repository:** manager and workers read/write the same `JobExecution` and `StepExecution` in the shared `JobRepository`.
2. **Clear `DataSource` separation:** `TaskRepository`, Batch repository, and business DB may live in three separate places; wire the right datasources and transaction managers.
3. **Schema/serializer compatibility:** workers must run supported releases with compatible `ExecutionContext` structures.
4. **Secure secrets:** never pass credentials via command line, `JobParameters`, or `ExecutionContext`; those values can end up stored in repositories and logs.
5. **Tenant isolation:** every worker query must enforce tenant/authorization filters rather than using tenant merely as a log label.
6. **Resource limits:** with a large `gridSize`, per-worker connection pools add up and can overload the database.

## 12. Retries and Crash Windows: Metadata vs. Business Outcomes

| Incident | What can happen | Resolution |
|---|---|---|
| Launcher rejects worker | Manager sees a partition never ran | Check deployer/image/quotas and apply bounded retries |
| Worker starts with wrong `JobRepository` | Child `TaskExecution` exists, but Batch Step is not updated properly | Compare `DataSource`/schema config and `StepExecution` ID |
| Worker receives `SIGKILL` mid-partition | `StepExecution` stays `STARTED` or at an old checkpoint | Verify process death and recover per your release procedure |
| Worker commits data then dies before `TaskRepository` finalizes | Business state may be complete while child `TaskExecution` lacks `END_TIME` | Cross-check repositories and business DB |
| Manager is killed after launching workers | Workers may still be running | Locate orphan workers and prevent duplicate launches |
| Worker receives a partition twice | May produce duplicate side effects | Unique business keys, transactions, checkpoints, fencing if needed |
| Wait timeout expires | Does not prove workers rolled back | Look up terminal status by `StepExecution` ID and platform ID |
| Source data changes between restarts | Old ranges may now mean different data | Pin snapshot/cutoff and partition mapping |

**A Spring Cloud Task retry does not automatically equal a Spring Batch restart.** A retry creates a new `TaskExecution` ID, yet it may need to resume the same `JobInstance`/`StepExecution` under Batch rules. Never append a new identifying timestamp just to work around restart errors.

If a partition processing transaction IDs `250001..500000` commits some transactions and crashes, a retry may reprocess items. Enforce unique constraints by **business key**, proper transaction/chunk checkpoints, and idempotency for all HTTP/message side effects. `TaskRepository` does not protect business outcomes from duplication.

## 13. The Manager Must Await `StepExecution` Status

A task launcher returning "request accepted" **does not mean** the worker has finished processing.

~~~mermaid
flowchart TD
    A["Manager creates StepExecutions"] --> B["Launch worker partitions"]
    B --> C{"Terminal StepExecution status?"}
    C -- "No" --> D["Poll / reply / wait per handler"]
    D --> E{"Timeout?"}
    E -- "No" --> C
    E -- "Yes" --> F["Cross-check processes, Batch repository, retry policy"]
    C -- "Yes" --> G{"All partitions succeeded?"}
    G -- "Yes" --> H["Manager step completes"]
    G -- "No" --> I["Manager step fails or follows policy"]
~~~

Bound launch timeouts, processing timeouts, retry backoffs, memory/CPU, DB connections, and concurrency. When the manager stops, have a policy for launched workers that are still running. When a worker container restarts itself, preserve its `StepExecution` binding and avoid duplicating business side effects.

Never rely on partition completion order. `partition3` can finish before `partition0`.

## 14. Observability and Tracing Along the ID Chain

Suggested manager log format:

~~~text
event=partition.launched
managerTaskExecutionId=5001
jobInstanceId=201
jobExecutionId=340
stepExecutionId=890
partitionName=partition2
businessDate=2026-11-23
~~~

Corresponding worker log:

~~~text
event=partition.completed
parentTaskExecutionId=5001
childTaskExecutionId=5004
jobExecutionId=340
stepExecutionId=890
partitionName=partition2
processedCount=250000
~~~

This is a **suggested log structure**, not a built-in default format. Pull IDs from the right repositories/contexts; never print passwords, tokens, sensitive arguments, or the entire `ExecutionContext`.

Illustrative SQL with familiar default metadata table names:

~~~sql
-- Find child TaskExecutions of a manager run.
SELECT TASK_EXECUTION_ID, TASK_NAME, PARENT_EXECUTION_ID,
       START_TIME, END_TIME, EXIT_CODE
FROM TASK_EXECUTION
WHERE PARENT_EXECUTION_ID = :parent_task_execution_id
ORDER BY TASK_EXECUTION_ID;

-- Find StepExecutions of a Batch Job run.
SELECT STEP_EXECUTION_ID, JOB_EXECUTION_ID, STEP_NAME,
       STATUS, READ_COUNT, WRITE_COUNT,
       START_TIME, END_TIME
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = :job_execution_id
ORDER BY STEP_EXECUTION_ID;
~~~

If custom table prefixes/schemas are configured, adjust to match the **deployed DDL**. `TASK` and `BATCH` tables hold distinct metadata and do not implicitly share a direct foreign key connecting those two tables.

A useful tracing chain:

~~~text
business key / request ID
  -> manager TaskExecution
     -> JobInstance + JobExecution
        -> partition StepExecutions
           -> child TaskExecutions + platform execution IDs
              -> checkpoint / logs / business outcome
~~~

## 15. Common Pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| Worker cannot see `minId`/`maxId` | Wrong `StepExecution`/`ExecutionContext` or missing `@StepScope` | Check handler, `JobRepository`, and `@StepScope` beans |
| Every worker processes the same range | Shared min/max passed via env/CLI | Read each partition's dedicated `ExecutionContext` |
| A new `JobInstance` is created per worker | Worker manually invokes `JobLauncher` with differing identifying params | Worker must execute the manager-created `StepExecution` |
| Retry creates a new `JobInstance` | Identifying `run.id`/timestamp | Keep identifying parameters stable |
| `TaskRepository` shows worker, Batch lacks Step | Worker points to wrong `JobRepository` | Check datasource/schema/`StepExecution` ID |
| Missing parent link | Parent `TaskExecution` ID not passed | Verify launcher and `parent-execution-id` property |
| Confusing parent ID with `JobExecution` ID | Mixed ID namespaces | Refer to the identifier table in section 10 |
| Secrets appear in metadata | Passwords/tokens placed in `JobParameters` | Use a secret manager |
| Manager reports success right after launch | Not waiting for terminal `StepExecution` status | Fix `PartitionHandler`/wait/reply policy |
| Workers keep running after manager crash | No orphan-handling policy | Query worker status before retrying |
| Overlapping or missing data | Bad partition/reader bounds | Verify union and intersection of ranges |
| Multiple JVMs overload the DB | `gridSize` or concurrency too high | Cap workers/pools and measure throughput |
| `StepExecution` stays `STARTED` after crash | Metadata never finalized | Recover per Batch release docs after verifying process stopped |

### What Not to Do

Do not use `Thread.sleep` to "wait for workers to finish", do not replace `stepExecutionId` with `taskExecutionId`, do not create a separate `JobExecution` inside a worker and call it remote partitioning, and do not rely solely on a worker's exit code to decide the Job completed.

## 16. Practice Exercise

Build a Spring Cloud Task manager application and a worker image running a Spring Batch worker Step:

1. Configure a **shared `JobRepository`** with a version-matched schema; configure `TaskRepository` for each process if you want to inspect parent–child tasks.
2. Choose `tenant`, `businessDate`, and `revision` as identifying `JobParameters`.
3. Create a `Partitioner` splitting four ID ranges with zero overlap and zero gaps.
4. Build a worker Step/Tasklet using `@StepScope` that reads both `JobParameters` and `ExecutionContext`.
5. Configure a `PartitionHandler` compatible with your chosen deployer or messaging platform.
6. Prepare the worker image, configuration, secrets, transaction manager, and resource limits.
7. Enable parent `TaskExecution` ID propagation and observe worker `TaskExecution`s.
8. Run the Job and record `JobInstance` ID, `JobExecution` ID, `StepExecution` IDs, and parent/child `TaskExecution` IDs.
9. Inject a failure in `partition2` and verify the manager handles the outcome properly.
10. Restart with the same identifying parameters; verify checkpoints and ensure results are not duplicated.
11. Drill killing one worker and killing the manager; check for orphan workers before retrying.
12. Inspect business data, check for secrets in metadata/logs, and verify behavior when source data mutates.

| Check item | Expected result |
|---|---|
| Parent and child `TaskExecution`s | Traceable when parent ID is propagated |
| One `JobExecution`, multiple `StepExecution`s | Workers update their own exact `StepExecution` |
| `JobParameters` | Consistent across partitions of the same Job |
| `ExecutionContext` | Each partition has its own distinct range |
| Manager and worker `JobRepository` | Point to the exact same metadata |
| Retries | Do not create unintended `JobInstance`s or duplicate writes |
| Worker or manager crash | Clear reconciliation and recovery procedure exists |
| Secrets | Absent from Task/Batch arguments and `ExecutionContext` |

## 17. Conclusion

Combining **Spring Cloud Task** with **Spring Batch remote partitioning** requires clearly separating:

- **Job-level:** `JobParameters`, `JobInstance`, and `JobExecution` govern identity and restartability.
- **Partition-level:** `StepExecutionId`, `partitionName`, and `ExecutionContext` determine which slice a worker processes.
- **Process-level:** manager and worker `TaskExecution`s, `parentExecutionId`, external execution IDs, and deployment configuration govern process tracing and operations.

The manager must supply enough context for each worker to **attach to its pre-created `StepExecution`**, rather than merely launching a JVM with a few CLI flags. `TaskRepository` tracks parent–child lifecycles, `JobRepository` manages partitions and checkpoints, and unique business keys plus transactions protect outcomes. When failures happen, reconcile **all three metadata layers and actual business data** before restarting to avoid omissions or duplicate processing.
