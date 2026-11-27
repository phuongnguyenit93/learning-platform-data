# Asynchronously Launching Partitions and Shutting Down the Executor

## 1. Problem: Launching Multiple Workers from a Finite Task Application

In **Spring Cloud Task**, a Spring Boot application normally starts, performs a finite task, records the run outcome in **`TaskRepository`**, and exits. When data volume is large, the application can pair with **Spring Batch remote partitioning**: a **manager** splits work into partitions, and each **worker** runs a Spring Batch `Step` in its own process or container.

Suppose we need to process one million records split across eight key ranges. If creating a Kubernetes Pod takes several seconds, **launching eight workers sequentially** can spend significant manager time merely waiting for infrastructure provisioning before real processing even begins.

Spring Cloud Task supports passing a **`ThreadPoolTaskExecutor`** to **`DeployerPartitionHandler`** to **dispatch worker launch requests asynchronously**. Understand this accurately: *asynchrony during launch* **does not mean** the manager may mark the Spring Batch Job complete as soon as launch commands are sent. The manager still must monitor `StepExecution` records in **`JobRepository`** and aggregate outcomes.

Another equally important issue: a thread pool created to launch partitions can leave live threads running, preventing the **task manager JVM from exiting** after processing finishes. Therefore, this lesson in the **Remote Partitioning** chapter focuses on both **controlled parallel launching** and **closing the executor when the task lifecycle ends**.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish `Partitioner`, `PartitionHandler`, `TaskLauncher`, `ThreadPoolTaskExecutor`, and the worker `Step`.
2. Explain the differences between **asynchronous launching**, **parallel worker execution**, and **manager outcome waiting**.
3. Configure `DeployerPartitionHandler` with an executor to reduce worker-creation latency.
4. Tune `gridSize`, `maxWorkers`, thread pool size, polling interval, and timeouts.
5. Enable `spring.cloud.task.closecontextEnabled=true` and design graceful shutdown to prevent thread leaks.
6. Observe results across `TaskRepository`, `JobRepository`, and manager/worker logs.
7. Test restarts, launch errors, worker failures, and abrupt process termination.

## 2. Remote Partitioning Architecture with Spring Cloud Task

~~~mermaid
flowchart LR
    S["Scheduler / run trigger"] --> M["Manager Spring Cloud Task"]
    M --> P["Partitioner creates ExecutionContexts"]
    P --> H["DeployerPartitionHandler"]
    H --> E["ThreadPoolTaskExecutor (launch)"]
    E --> L["TaskLauncher / Spring Cloud Deployer"]
    L --> W1["Worker Task A"]
    L --> W2["Worker Task B"]
    L --> W3["Worker Task C"]
    W1 --> J[("Shared JobRepository")]
    W2 --> J
    W3 --> J
    H <--> J
    M --> T[("TaskRepository")]
    W1 --> T
    W2 --> T
    W3 --> T
~~~

| Component | Role | What **not** to confuse it with |
| --- | --- | --- |
| **Partitioner** | Splits range into per-partition `ExecutionContext`s, e.g., ID intervals | Does not create Pods or process items itself |
| **Manager `PartitionStep`** | Creates child `StepExecution`s, delegates to partition handler, aggregates outcomes | Must not report `COMPLETED` before worker results are confirmed |
| **DeployerPartitionHandler** | Submits workers to Spring Cloud Deployer; polls `JobRepository` for results | Not itself an executor running business data logic |
| **TaskLauncher** | Spawns worker processes/containers from a `Resource` and deployment properties | Not a `TaskExecutor` managing internal manager threads |
| **ThreadPoolTaskExecutor** | Executes *launch calls* from the manager in parallel | Not the count of running workers and does not replace `maxWorkers` |
| **DeployerStepExecutionHandler** | Worker `CommandLineRunner`: fetches its assigned `StepExecution` from `JobRepository` and runs the matching `Step` | Does not re-partition data itself |
| **JobRepository / JobExplorer** | Stores and reads `JobExecution` / `StepExecution`, per-partition status, and restart state | Distinct from Spring Cloud Task's `TaskRepository` |
| **TaskRepository / TaskExplorer** | Tracks lifecycle of manager and worker task processes | Does not hold granular Batch checkpoints per partition |

In a `DeployerPartitionHandler` deployment, **manager and all workers must access the same `JobRepository` store**. Per Spring Cloud Task integration docs, manager and workers also need access to the proper `TaskRepository` when using task/batch linking. Two processes pointing to separate databases that merely share table names **cannot coordinate**.

## 3. Where Exactly Does "Asynchronous" Apply?

Per the Spring Cloud Task Reference, when **no `TaskExecutor` is passed to `DeployerPartitionHandler`**, partition launch calls can happen sequentially. Each `TaskLauncher.launch(...)` call can spend time preparing the environment, such as asking Kubernetes to create a Pod.

When passing a `ThreadPoolTaskExecutor`, the handler can **submit multiple launch calls concurrently** per thread-pool policy. Suppose there are eight partitions and each Pod-creation request takes three seconds:

- Sequential dispatch: the request-submission phase alone can take nearly **24 seconds** in this illustration, before worker processing time.
- Four parallel requests: submission can finish in two waves, roughly **6 seconds** ideally.

This is purely an explanatory example, **not a performance guarantee**: API quotas, image-pull times, queues, databases, network latency, and Kubernetes limits all alter real timings.

~~~mermaid
sequenceDiagram
    participant M as Manager PartitionStep
    participant H as DeployerPartitionHandler
    participant E as ThreadPoolTaskExecutor
    participant L as TaskLauncher
    participant W as Worker tasks
    participant J as Shared JobRepository

    M->>H: handle(partitions)
    H->>E: submit launch(partition0)
    H->>E: submit launch(partition1)
    H->>E: submit launch(partition2)
    par Dispatch launch requests
        E->>L: launch worker 0
        E->>L: launch worker 1
        E->>L: launch worker 2
    end
    L-->>W: Spawn worker processes/containers
    W->>J: Execute Step and update StepExecution
    H->>J: Poll StepExecution status
    J-->>H: Some partitions still RUNNING
    H->>J: Poll again per configured interval
    J-->>H: Partitions reach terminal status
    H-->>M: Return StepExecutions for aggregation
    M-->>M: Manager Step finishes based on aggregated outcome
~~~

**Key points to remember:**

- "`launch` returned" may only mean the deployment platform **accepted the request** or generated a **worker execution ID**—it does **not** prove `workerStep` succeeded.
- `DeployerPartitionHandler` monitors partition outcomes in the shared `JobRepository`; the manager can still **wait a long time** while workers process.
- `ThreadPoolTaskExecutor` manages **only manager-side launch invocations**. Each worker is an independent process with its own lifecycle.
- `maxWorkers` caps concurrently running workers per handler logic; `corePoolSize` controls concurrent launch tasks inside the **manager**. The two numbers do not mean the same thing.

## 4. Partition Design and Data Independence

Example splitting 1,000,000 records by `source_id`:

| Partition | Start | End | Worker processes |
| --- | ---: | ---: | --- |
| partition0 | 1 | 125,000 | `source_id BETWEEN 1 AND 125000` |
| partition1 | 125,001 | 250,000 | `source_id BETWEEN 125001 AND 250000` |
| partition2 | 250,001 | 375,000 | `source_id BETWEEN 250001 AND 375000` |
| ... | ... | ... | ... |
| partition7 | 875,001 | 1,000,000 | `source_id BETWEEN 875001 AND 1000000` |

ID ranges live in the **worker `StepExecution`'s `ExecutionContext`**, not as mandatory JVM CLI flags. When a worker receives its step ID from `DeployerPartitionHandler`, it queries the repository to retrieve the planned `ExecutionContext`.

A safe partition must satisfy these properties:

1. **Disjoint:** no source record belongs to two ranges simultaneously.
2. **Complete:** the union of ranges covers the entire intended scope.
3. **Stable source:** if the source mutates mid-run, use a snapshot/manifest or data-versioning rule.
4. **Retryable:** write outputs with unique business keys/idempotency so re-running a worker produces no duplicate effects.
5. **Self-describing:** `minId`, `maxId`, and source version suffice for the worker to execute without relying on in-memory manager state.

Never pass an in-RAM Java object list from manager to worker and expect restartability after a manager crash; metadata and data resources must be accessed durably.

## 5. Configuring `ThreadPoolTaskExecutor` for the Manager

The Java examples below apply the **`DeployerPartitionHandler` usage in Spring Cloud Task 3.0.x** described in official Javadocs and reference docs. Pick compatible Spring Boot/Spring Batch/Spring Cloud Task releases; do not mix Batch 6 APIs into a Batch 5 project without verification.

### 5.1. Spring-Managed Executor Bean

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@Profile("manager")
public class PartitionLaunchExecutorConfig {

    @Bean(name = "partitionLaunchExecutor")
    public ThreadPoolTaskExecutor partitionLaunchExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("partition-launch-");

        // When context closes, do not immediately interrupt in-flight launch requests.
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(120);

        // Spring initializes and destroys the bean per lifecycle.
        return executor;
    }
}
~~~

**Explanation:**

- `corePoolSize=4` and `maxPoolSize=4`: up to four threads can execute concurrent launch calls in this example.
- `queueCapacity=16`: bounds queued launch calls not yet picked up by executor threads. Exceeding this limit can trigger **rejection** rather than unbounded queuing.
- `setWaitForTasksToCompleteOnShutdown(true)`: gives already-accepted launch tasks a chance to finish during executor shutdown; this does **not** mean waiting for all remote workers to finish processing.
- `setAwaitTerminationSeconds(120)`: caps how long Spring waits for the pool to terminate when closing the context. Do not confuse this with `DeployerPartitionHandler`'s timeout.
- This is a **Spring bean**, not a manually created `newFixedThreadPool` `ExecutorService` left unmanaged. Spring invokes the bean's destruction hook when `ApplicationContext` closes.

Shutdown wait duration must be evaluated alongside the container's **termination grace period**. If Kubernetes grants only 30 seconds to stop a Pod while the app attempts to wait 120 seconds, Java's wait cannot be guaranteed to finish before the Pod is killed.

### 5.2. `DeployerPartitionHandler` Using the Executor

~~~java
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.partition.PartitionHandler;
import org.springframework.cloud.deployer.spi.task.TaskLauncher;
import org.springframework.cloud.task.batch.partition.DeployerPartitionHandler;
import org.springframework.cloud.task.repository.TaskRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@Profile("manager")
public class RemotePartitionHandlerConfig {

    @Bean
    public PartitionHandler remotePartitionHandler(
            TaskLauncher taskLauncher,
            JobExplorer jobExplorer,
            TaskRepository taskRepository,
            ResourceLoader resourceLoader,
            @Qualifier("partitionLaunchExecutor")
            ThreadPoolTaskExecutor launchExecutor) {

        // Resource must be accepted by the infrastructure's TaskLauncher.
        Resource workerResource =
                resourceLoader.getResource("file:/opt/apps/remote-worker.jar");

        DeployerPartitionHandler handler =
                new DeployerPartitionHandler(
                        taskLauncher,
                        jobExplorer,
                        workerResource,
                        "workerStep",
                        taskRepository,
                        launchExecutor);

        handler.setApplicationName("remote-partition-worker");
        handler.setGridSize(8);
        handler.setMaxWorkers(4);
        handler.setPollInterval(10_000L);
        handler.setTimeout(30 * 60_000L);
        return handler;
    }
}
~~~

**This snippet assumes the manager application already has a real `TaskLauncher` bean** (for example, from an environment-appropriate Spring Cloud Deployer implementation); merely adding `spring-cloud-starter-task` does not provide a Kubernetes `TaskLauncher`. `file:/opt/apps/remote-worker.jar` fits only when the launcher can read that file path. For other deployers, `Resource` may be a Maven resource or matching artifact reference. Never copy that path to production if the platform cannot read the file.

In Spring Cloud Task 3.0.4, `DeployerPartitionHandler`'s six-argument constructor accepts `TaskLauncher`, `JobExplorer`, `Resource`, worker step name, `TaskRepository`, and `TaskExecutor`. If using another version, verify constructor signatures and dependencies against that version's Javadoc.

### 5.3. Understanding the Four Limits

| Setting | Scope | Meaning in this example |
| --- | --- | --- |
| `setGridSize(8)` | Spring Batch partitioning | Hints how many partitions/worker steps to create; `Partitioner` decides actual `ExecutionContext`s |
| `setMaxWorkers(4)` | `DeployerPartitionHandler` | Caps concurrent running workers at four per handler |
| `setCorePoolSize(4)` | Manager-side thread pool | Can dispatch up to four worker-creation requests simultaneously |
| `setQueueCapacity(16)` | Launch-call queue inside manager JVM | If launch calls arrive faster than threads process them, excess calls queue |
| `setPollInterval(10_000L)` | `JobRepository` monitoring | Polls partition statuses roughly every 10 seconds |
| `setTimeout(30 * 60_000L)` | Handler/manager | Caps how long the manager waits per configuration; **does not reliably kill workers** |
| `setAwaitTerminationSeconds(120)` | Executor shutdown in manager JVM | Waits for accepted launch calls when context closes |

`gridSize` is not a thread-pool setting; `maxWorkers` does not guarantee Kubernetes has enough capacity for that many Pods. To tune performance, measure **provisioning time**, **actual running workers**, **queue wait**, **partition processing time**, and **polling/aggregation overhead** separately.

## 6. Illustrative Manager Job and Partitioner

The manager needs a Spring Batch `Job` containing a **`PartitionStep`**. A `Partitioner` creates each key range inside `ExecutionContext`. The example below splits 1 to 1,000,000 into slices based on the suggested `gridSize`.

### 6.1. Partitioner

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.batch.core.partition.support.Partitioner;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.stereotype.Component;

@Component
public class RangePartitioner implements Partitioner {

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize <= 0) {
            throw new IllegalArgumentException("gridSize must be positive");
        }

        long upper = 1_000_000L; // Demo: fixed source scope.
        long width = (upper + gridSize - 1) / gridSize;
        Map<String, ExecutionContext> result = new LinkedHashMap<>();

        for (int index = 0; index < gridSize; index++) {
            long min = 1L + index * width;
            long max = Math.min(upper, min + width - 1);
            if (min > upper) {
                break;
            }

            ExecutionContext ctx = new ExecutionContext();
            ctx.putLong("minId", min);
            ctx.putLong("maxId", max);
            ctx.putString("sourceVersion", "v1");
            result.put("partition" + index, ctx);
        }

        return result;
    }
}
~~~

**Note:** in a real application, `upper` and source version should be **pinned via `JobParameters` or a restartable snapshot**, not hardcoded in source code. Changing how ranges split across restarts also requires care because partition `StepExecution`s are matched by name.

### 6.2. Job and Manager Step

~~~java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.core.partition.PartitionHandler;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
@Profile("manager")
public class ManagerJobConfig {

    @Bean
    public Step managerStep(
            JobRepository jobRepository,
            RangePartitioner partitioner,
            PartitionHandler remotePartitionHandler) {

        return new StepBuilder("managerStep", jobRepository)
                .partitioner("workerStep", partitioner)
                .partitionHandler(remotePartitionHandler)
                .build();
    }

    @Bean
    public Job remoteImportJob(
            JobRepository jobRepository, Step managerStep) {

        return new JobBuilder("remoteImportJob", jobRepository)
                .start(managerStep)
                .build();
    }
}
~~~

The manager step does not process records directly. It partitions and orchestrates `workerStep`. The number of partitions created by `Partitioner` must match source constraints and restart strategy; if more partitions exist than concurrent workers, the handler schedules them within `maxWorkers` and actual platform capacity.

## 7. Worker Executing the Step Remotely

A worker is **another finite Spring Boot Task application** spawned by the infrastructure. With `DeployerPartitionHandler`, the worker receives `JobExecution`/`StepExecution` IDs and the Step name via environment variables/arguments set by the handler. `DeployerStepExecutionHandler` restores the `StepExecution` from the **shared `JobRepository`** and executes the matching Step bean.

**Important:** the worker **must not launch a new Job** in place of the `StepExecution` created by the manager. If Spring Boot auto-runs the Job on worker startup, unintended `JobExecution`s will be created. In the `worker` profile, disable Batch Job auto-run and let `DeployerStepExecutionHandler` act as the runner.

### 7.1. `DeployerStepExecutionHandler` Bean

~~~java
import org.springframework.beans.factory.BeanFactory;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.cloud.task.batch.partition.DeployerStepExecutionHandler;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
@Profile("worker")
public class WorkerLaunchConfig {

    @Bean
    public DeployerStepExecutionHandler stepExecutionHandler(
            BeanFactory beanFactory,
            JobExplorer jobExplorer,
            JobRepository jobRepository) {

        return new DeployerStepExecutionHandler(
                beanFactory, jobExplorer, jobRepository);
    }
}
~~~

`DeployerStepExecutionHandler` is a `CommandLineRunner`. The worker needs a bean named `workerStep` so the handler can find it. `JobExecution` and `StepExecution` IDs supplied by the manager are used to fetch `ExecutionContext`, rather than recomputing partition bounds inside the worker.

### 7.2. Example Step Processing a Key Range

This example assumes `source_input` and `partition_result` already exist in the business database and every source row has a stable `source_id`. For brevity, it uses a `Tasklet` executing a ranged SQL update; for large item-by-item processing, replace it with a chunk-oriented step.

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
@Profile("worker")
public class WorkerStepConfig {

    @Bean
    public Step workerStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            JdbcTemplate jdbc) {

        return new StepBuilder("workerStep", jobRepository)
                .tasklet((contribution, chunkContext) -> {

                    var execution =
                            contribution.getStepExecution();
                    long min = execution
                            .getExecutionContext().getLong("minId");
                    long max = execution
                            .getExecutionContext().getLong("maxId");

                    jdbc.update("""
                        INSERT INTO partition_result
                            (source_id, processed_value)
                        SELECT source_id, payload
                        FROM source_input
                        WHERE source_id BETWEEN ? AND ?
                        ON CONFLICT (source_id) DO UPDATE
                        SET processed_value =
                            EXCLUDED.processed_value
                        """, min, max);

                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .build();
    }
}
~~~

Illustrative target table:

~~~sql
CREATE TABLE partition_result (
    source_id BIGINT PRIMARY KEY,
    processed_value TEXT NOT NULL
);
~~~

`ON CONFLICT` is only idempotent on `source_id` if business rules permit overwriting with the same source data. In production, account for `sourceVersion`, source immutability, and proper business keys. If the Batch metadata DB and business DB are separate, do not assume both commit inside a single atomic transaction.

**Never confuse worker step completion with a successful `TaskLauncher` call.** The worker must update its `StepExecution` to the proper terminal status before the manager has grounds to conclude the partition finished.

## 8. Profile Configuration and Worker Runtime Resources

### 8.1. Manager Profile

~~~yaml
# application-manager.yml
spring:
  main:
    web-application-type: none
  cloud:
    task:
      name: remote-partition-manager
      closecontextEnabled: true
      batch:
        fail-on-job-failure: true
  batch:
    job:
      enabled: true
    jdbc:
      initialize-schema: never
~~~

### 8.2. Worker Profile

~~~yaml
# application-worker.yml
spring:
  main:
    web-application-type: none
  cloud:
    task:
      name: remote-partition-worker
      closecontextEnabled: true
  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: never
~~~

Both profiles also need **`DataSource`, schema, and metadata privileges** configured beyond these abbreviated YAML snippets. Batch tables must be created beforehand via migrations; if managing the `TaskRepository` schema via migrations, keep version and prefix aligned too.

Documentation uses `spring.cloud.task.closecontextEnabled=true`. Depending on Boot binding, YAML may also use relaxed kebab-case `closecontext-enabled: true`. When composing multiple profiles, verify the final **effective resolved value**, especially if the platform overrides it via environment variables.

**Worker image / Resource:**

- The worker JAR must bundle `DeployerStepExecutionHandler` and `workerStep` alongside required JDBC/Batch dependencies.
- `TaskLauncher` must know how to run the worker JAR on the target platform; use the matching local/Kubernetes/Cloud Foundry implementation.
- The manager must have permissions to spawn workers, pass needed environment/deployment properties, and inspect platform status.
- **Never pass secrets via CLI flags or logs** where they can surface in process lists and Task metadata. Use a secret manager or protected environment variables.
- Never allow workers to hit a different database from the manager due to a wrong `spring.profiles.active` or `DataSource` URL.

On Kubernetes, worker resources may require valid DNS naming rules. Design `applicationName` and resource naming to satisfy your active deployer's constraints.

## 9. Closing Executor and ApplicationContext in the Right Order

This is the **most easily misunderstood** part of the topic. `ThreadPoolTaskExecutor` creates threads inside the manager; after launch requests are sent, pool threads can stay alive. Spring Cloud Task documentation explicitly notes that when using this executor to launch partitions asynchronously, **you must close the Spring context** because live threads can prevent the application from exiting.

### 9.1. Enabling Spring Cloud Task Context Closing

~~~properties
spring.cloud.task.closecontextEnabled=true
~~~

Spring Cloud Task closes the `ApplicationContext` after runners finish and `TaskExecution` metadata is updated. Closing the context runs Spring beans with lifecycle/destroy callbacks through resource cleanup, including the Spring-managed `ThreadPoolTaskExecutor`.

**Do not equate these milestones:**

| Milestone | What has happened | What you cannot infer yet |
| --- | --- | --- |
| A `TaskLauncher.launch` call returns | One worker-creation request was submitted | Worker finished executing its Step |
| `DeployerPartitionHandler.handle` returns | Handler completed monitoring and returned `StepExecution`s per contract | External non-repository business data is guaranteed right |
| Manager Spring Batch Job/runner completes | Manager obtained `JobExecution` result per lifecycle | JVM is guaranteed to exit |
| Spring context closes | Spring beans are asked to clean up resources | Non-Spring threads and all remote workers are guaranteed stopped |
| JVM exits | Manager process is no longer running | No remote workers or external side effects remain |

### 9.2. Do Not Close the Executor Immediately After Submitting

**Wrong:** shutting down the pool right after calling async submit methods before launch tasks have been accepted/processed or before `PartitionHandler` finishes coordinating.

~~~java
// Pseudocode illustrating an ordering bug:
for (Runnable launchCommand : commands) {
    executor.execute(launchCommand);
}
executor.shutdown(); // Can cut off the orchestration flow prematurely.
~~~

With `ThreadPoolTaskExecutor` as a Spring bean, **do not manually call shutdown** inside `Partitioner` or a runner right as it returns. Let the manager and `ApplicationContext` lifecycle decide when to clean up the pool after the Batch Job completes. If your architecture creates a standalone executor outside Spring, calling `shutdown`/`awaitTermination` is your responsibility with full error and timeout handling.

**Right approach:** the manager lets `DeployerPartitionHandler` complete its launch + monitoring contract, lets `JobRepository` persist terminal state, and only then lets Spring Cloud Task's lifecycle close the context and pool.

### 9.3. Graceful Shutdown Still Needs a Timeout

~~~java
executor.setWaitForTasksToCompleteOnShutdown(true);
executor.setAwaitTerminationSeconds(120);
~~~

These two settings give **already-accepted launch calls** time to finish when Spring closes the executor. They **do not wait in place of** `DeployerPartitionHandler` for worker outcomes, and **do not control stopping worker Kubernetes Pods**.

In production, you need:

- A handler timeout so the manager does not wait forever if a partition hangs.
- Appropriate I/O and transaction timeouts on workers.
- JVM/container shutdown grace limits no shorter than desired cleanup time.
- A policy for when the manager receives `SIGTERM` or is killed before worker outcomes update.
- A reconciliation procedure for remote workers still alive after the manager stops.

### 9.4. When a TaskBatch Job Fails

Per Spring Cloud Task, the default **task process exit code** when running Spring Batch does not always directly mirror `BatchStatus.FAILED`. The property:

~~~properties
spring.cloud.task.batch.fail-on-job-failure=true
~~~

is used to map Batch Job failure to a non-zero exit code in supported integration setups. **Still verify on your exact version and execution path**, and inspect `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION`, and worker logs rather than trusting only the manager's exit code.

## 10. Tracking Results Across Three Metadata Layers

### 10.1. Manager Batch `JobExecution`

~~~sql
SELECT JOB_EXECUTION_ID, STATUS, EXIT_CODE,
       START_TIME, END_TIME, EXIT_MESSAGE
FROM BATCH_JOB_EXECUTION
ORDER BY JOB_EXECUTION_ID DESC;
~~~

Check whether the Job is `COMPLETED` or `FAILED` and whether completion timestamps are present. If the manager was killed abruptly, `JobRepository` may not have updated final results even though workers processed part of the workload.

### 10.2. Per-Partition `StepExecution`

~~~sql
SELECT STEP_EXECUTION_ID, JOB_EXECUTION_ID,
       STEP_NAME, STATUS, EXIT_CODE,
       READ_COUNT, WRITE_COUNT,
       START_TIME, END_TIME
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = 1001
ORDER BY STEP_EXECUTION_ID;
~~~

`JOB_EXECUTION_ID=1001` is just an example ID. You may see names such as:

~~~text
managerStep
workerStep:partition0
workerStep:partition1
workerStep:partition2
...
~~~

Each partition has its own `StepExecution`. On a normal success path, the manager should only be considered truly complete when every required partition holds a valid terminal status and outcomes are aggregated.

### 10.3. Manager and Worker `TaskExecution`s

~~~sql
SELECT TASK_EXECUTION_ID, TASK_NAME, START_TIME,
       END_TIME, EXIT_CODE, ERROR_MESSAGE
FROM TASK_EXECUTION
WHERE TASK_NAME IN (
    'remote-partition-manager',
    'remote-partition-worker'
)
ORDER BY START_TIME DESC, TASK_EXECUTION_ID DESC;
~~~

There can be one `TaskExecution` for the manager and multiple `TaskExecution`s for worker processes. **Never assume `TaskExecution` ID equals `JobExecution` ID or `StepExecution` ID**: those are three distinct identifier layers.

If Spring Cloud Task Batch integration is enabled, `TASK_TASK_BATCH` can store links between `TASK_EXECUTION_ID` and `JOB_EXECUTION_ID`. Never rely solely on task name to identify a partition: multiple workers can share the same task name. Logs should include `jobExecutionId`, `stepExecutionId`, `partitionName`, and process/Pod ID alongside `taskExecutionId` when available.

## 11. Timeouts and Failures: Who Is Responsible?

| Symptom | Likely cause | Appropriate action |
| --- | --- | --- |
| Manager is slow before workers start | Sequential `TaskLauncher.launch`/provisioning or overloaded platform | Measure launch latency, configure thread pool, check quotas/Pod scheduling |
| Launch requests get rejected | Queue/thread pool full, scarce resources, or deployer API error | Check pool, `maxWorkers`, quotas, backoff; never swallow exceptions |
| Worker spawns but does not run Step | Wrong profile, missing `DeployerStepExecutionHandler`, mismatched `workerStep` name | Check runner and `StepExecution` ID environment |
| Manager polls forever without finishing | Worker writing to wrong `JobRepository`, hung Step, or DB unavailable | Check DB/schema, step logs, timeouts, thread dumps/Pod status |
| Manager times out while workers still process | Manager timeout **does not mean** remote execution was cancelled | Verify real workers, decide cancel/reconcile via deployer |
| Manager Batch job `FAILED` yet process exits 0 | Exit-code mapping disabled or different execution path | Configure `fail-on-job-failure`, verify exit code and `JobRepository` |
| Job finished yet manager JVM will not exit | Launch pool retains non-daemon threads, context not closed | Enable `closecontextEnabled=true`, Spring-managed executor bean, inspect shutdown |
| Pod killed mid-shutdown | Termination grace period too short or slow callback | Tune shutdown/termination timeouts, design recovery |
| Retries create duplicate data | Worker writes outside transactions/missing idempotency | Unique business keys, safe retries, outbox for external side effects |

**What not to do:** never "fix" hanging JVMs by calling `System.exit(0)` right after dispatching worker launches, as that destroys result aggregation and reports false success. Nor should you manually edit `BATCH_STEP_EXECUTION.STATUS` from `STARTED` to `COMPLETED` to "unblock" a partition.

## 12. Reruns After Errors, Interruptions, and Duplicate Handling

Spring Batch supports **restarting** a failed Job, and under partitioning rules, properly recognized completed steps **do not need to re-run** while failed steps can re-run per restart configuration. This requires intact `JobRepository` metadata and consistent `JobInstance`/partition identities.

However, workers are independent processes:

1. Manager creates `StepExecution` and issues launch.
2. Worker may commit business writes.
3. Worker or manager is killed before `JobRepository` records terminal status.
4. On restart, the framework may need to reprocess an incomplete partition.

**Mandatory requirement:** workers must be **idempotent** or use proper checkpoints/transactions. Reprocessing a partition must never re-send payments, emails, or insert duplicate outputs uncontrollably.

Supporting mechanisms:

- Partition by stable **business ranges/snapshots**, independent of `TASK_EXECUTION_ID`.
- Choose writers with **unique keys**, conditional UPSERTs, or work-keyed retry logic.
- When workers use chunk readers, ensure `ExecutionContext` and `ItemStream` are configured for restarts.
- For external non-DB side effects, use idempotency keys/outbox or reconciliation jobs.
- Prevent two workers from processing the same partition concurrently after a timeout if the old owner may still be running; consider leases/fencing.
- Distinguish launch timeout, manager wait timeout, and worker business deadlines.

## 13. Practice Labs: Comparing Sequential and Asynchronous Launching

Prepare a test environment with manager/worker artifacts, a valid `TaskLauncher`, a shared database, and a small verifiable business table. Do not use production data or intentionally kill production Pods.

### Lab A — Sequential Launching

1. Configure `DeployerPartitionHandler` **without passing a custom executor** per your version's API.
2. Run a job with four partitions and log the timestamp of each launcher call per partition.
3. Measure the duration from when the manager starts launching until all workers are created.
4. Query `JobRepository` to see when partitions actually started and finished.
5. Verify zero duplicate business results and confirm the job's final status.

### Lab B — Asynchronous Launching

1. Define a `ThreadPoolTaskExecutor` with `corePoolSize=2`, `maxPoolSize=2`, and a bounded queue.
2. Pass the executor to the `DeployerPartitionHandler` constructor.
3. Keep `maxWorkers=2` and `gridSize=4`; re-run against a fresh source/snapshot for a fair comparison.
4. Correlate `partition-launch-*` thread names in logs with worker creation timestamps.
5. Confirm launch-dispatch time may drop, while **the manager only completes the job after receiving partition outcomes**.
6. Lower `maxWorkers=1` to observe the real active-worker cap separately from launch thread count.

### Lab C — Closing the Executor

1. Enable `spring.cloud.task.closecontextEnabled=true` on the manager.
2. Keep `setWaitForTasksToCompleteOnShutdown(true)` and set a finite termination wait.
3. Run the Job normally and verify `JobRepository` holds terminal outcomes.
4. Observe the manager closing its Spring context and the process exiting; verify no thread pool holds the JVM alive.
5. Try disabling `closecontextEnabled` in the lab to observe the difference when the executor still has live threads; **do not treat a lab example as a guarantee that `false` always hangs the JVM**.
6. Separately observe worker processes exiting after `workerStep`; if a worker stays alive, investigate its context or background threads.

### Lab D — Controlled Failure

1. Configure a worker to throw an intentional exception when encountering a specific key range in the lab.
2. Verify `BATCH_STEP_EXECUTION` for that partition transitions to failed via the normal lifecycle.
3. Inspect manager Job status, task `EXIT_CODE`, and worker logs.
4. Fix the code or bad data and restart the exact `JobInstance` per Batch rules.
5. Verify completed partitions produce no duplicates and final output matches the source scope.

### Completion Checklist

- [ ] Can explain how **async launch calls** differ from **parallel worker execution**.
- [ ] Have a real `TaskLauncher` for the platform and a valid worker `Resource`.
- [ ] Manager/workers point to the **same `JobRepository`** and appropriate `TaskRepository`.
- [ ] `Partitioner` produces disjoint ranges over a pinned source.
- [ ] `gridSize`, `maxWorkers`, and thread pool sizes are configured and measured independently.
- [ ] `DeployerPartitionHandler` receives a Spring-managed `ThreadPoolTaskExecutor`.
- [ ] Worker has `DeployerStepExecutionHandler` and a matching `workerStep` bean name.
- [ ] Worker does not accidentally auto-run the Batch Job when receiving a `StepExecution`.
- [ ] Manager exits only after monitoring/aggregating partition statuses.
- [ ] `closecontextEnabled=true` helps close the context and executor after the task lifecycle.
- [ ] Timeouts exist for manager, workers, shutdown, plus cancel/recovery procedures.
- [ ] Target writes are protected by idempotency or transactions/checkpoints for restarts.
- [ ] Can query matching Batch `JobExecution`/`StepExecution` and `TaskExecution` records.
- [ ] Failure, worker timeout, task interruption, and safe recovery scenarios have been tested.

## 14. Key Takeaways

In **Spring Cloud Task remote partitioning**, `DeployerPartitionHandler` can accept a **`ThreadPoolTaskExecutor`** to **launch workers asynchronously**, reducing deployment request latency on platforms with slow container provisioning. This capability is separate from workers processing data in parallel and **does not relieve the manager of waiting for and aggregating `StepExecution` outcomes in `JobRepository`**.

Because executor threads can keep the manager JVM alive, use a **Spring-managed executor**, bounded shutdown policies, and `spring.cloud.task.closecontextEnabled=true` to close the context when the task finishes. Verify all three layers: **`JobRepository`** (partitions and restarts), **`TaskRepository`** (process lifecycle), and **actual business data**. Never equate a successful launch with successful processing, and never close the thread pool prematurely in a way that breaks monitoring.

### References

- [Spring Cloud Task Reference — Asynchronously launch remote batch partitions](https://docs.spring.io/spring-cloud-task/docs/current/reference/htmlsingle/#_asynchronously_launch_remote_batch_partitions)
- [Spring Cloud Task — DeployerPartitionHandler Javadoc](https://docs.spring.io/spring-cloud-task/docs/current/apidocs/org/springframework/cloud/task/batch/partition/DeployerPartitionHandler.html)
- [Spring Cloud Task — DeployerStepExecutionHandler Javadoc](https://docs.spring.io/spring-cloud-task/docs/current/apidocs/org/springframework/cloud/task/batch/partition/DeployerStepExecutionHandler.html)
- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html)
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
