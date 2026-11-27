# Running batch jobs with Cloud Run Jobs

Not every serverless workload serves HTTP requests. Many workloads need to read a large dataset, process invoices in bulk, generate reports, synchronize data, or run scheduled maintenance tasks. These jobs typically run to completion and then stop, rather than keeping an HTTP server constantly ready.

Google Cloud Run Jobs lets you run a container to execute a job and exit. A single execution can consist of one or more tasks. Each task runs a container from the deployed image, receives input via environment variables or arguments, performs its assigned work, and signals success via its exit code. Cloud Run manages launching, task distribution, retries, and execution status.

With Java, you can package a batch program as a JAR inside a container image. The application does not need to open an HTTP port; it runs logic in `main`, processes data, and exits. This lesson covers designing tasks, splitting batches, controlling parallelism, recovering from failures, and operating Cloud Run Jobs safely.

## 1. How do Cloud Run Jobs differ from Cloud Run services?

Cloud Run offers two common execution models:

| Criterion | Cloud Run services | Cloud Run Jobs |
|---|---|---|
| Goal | Serve HTTP requests or gRPC requests | Run work until completion |
| Container lifecycle | Container serves requests and may be kept warm for subsequent requests | Container executes task and exits |
| HTTP port | Application typically must listen on a configured port | No need to open an HTTP port |
| How started | Request arrives at the service | User, API, scheduler, or workflow creates an execution |
| Output | HTTP response or stream | Exit code, task status, logs, and data saved in external systems |
| Suitable for | APIs, webhooks, web backends | Batches, migrations, reports, synchronization, and bulk data processing |

A Cloud Run Job is not simply an HTTP service that runs longer. It is designed for processes that run to completion. The container must exit with exit code 0 when a task succeeds; a non-zero exit code or a task timeout can cause Cloud Run to mark the task as failed and retry it according to configuration.

You do not need to write a request-waiting loop or run a web server inside a job's container. A Java program can start from `main`, read configuration, process the batch, save results, and exit.

### 1.1. When should you use Cloud Run Jobs?

Cloud Run Jobs fits workloads such as:

- Generating end-of-day or end-of-month reports.
- Reading CSV/JSON files from Cloud Storage and processing records individually.
- Synchronizing data between two systems.
- Running database migrations or maintenance tasks.
- Recomputing historical data.
- Processing large batches across multiple shards.
- Sending notifications against a prepared list.
- Running an operational task on demand.

If the work needs an immediate response for each HTTP request, a Cloud Run service fits better. If the work consists of multiple dependent steps, branching, per-step retries, or requires approvals, you can use Workflows to orchestrate Cloud Run Jobs and other services.

## 2. Architecture of a batch job

An execution can run a single task or multiple tasks. When there are multiple tasks, Cloud Run distributes tasks up to the configured count and caps how many run concurrently using parallelism.

~~~mermaid
flowchart TD
    T["Cloud Scheduler / Workflows / API"] --> E["Create Cloud Run Job execution"]
    E --> P["Distribute tasks"]
    P --> A["Task 0: shard 0"]
    P --> B["Task 1: shard 1"]
    P --> C["Task N: shard N"]
    A --> D["Read data and process"]
    B --> D
    C --> D
    D --> S["Database / Cloud Storage"]
    D --> L["Cloud Logging and task status"]
    S --> R["Execution completes when tasks finish"]
~~~

Each component has distinct responsibilities:

- **Job definition:** configuration of image, resources, task count, parallelism, timeout, retries, environment variables, and service account.
- **Execution:** a specific run of the job with that run's configuration and inputs.
- **Task:** a unit of execution within an execution. Each task has its own index and can be retried.
- **Container image:** contains the Java runtime, application, and dependencies.
- **Data store:** stores inputs, checkpoints, outputs, and business state.
- **Cloud Scheduler or Workflows:** starts the job on a schedule or as a step within a larger workflow.

Cloud Run Jobs manages the compute lifecycle. The application must still manage data correctness, idempotency, and recovery when a task finishes only part of its work.

## 3. One execution, multiple tasks, and parallelism

When creating a job, you can configure:

- **Task count:** total number of tasks that must complete in one execution.
- **Parallelism:** maximum number of tasks allowed to run concurrently.
- **Task timeout:** maximum duration allowed for a single task.
- **Max retries:** number of times Cloud Run may retry a failed task.
- **CPU and memory:** resources allocated per task.
- **Environment variables and arguments:** input configuration for the container.
- **Execution service account:** IAM identity used by tasks when calling Google Cloud APIs.

For example, a job has 40 tasks and parallelism set to 8. Cloud Run can run up to 8 tasks concurrently; as one task finishes or frees a slot, another task can start. Task count does not equal the number of containers running simultaneously. Parallelism controls execution concurrency.

Do not set parallelism equal to task count by default. If each task opens multiple database connections or calls external APIs, running them all simultaneously can overload dependencies. Start low, measure throughput, and scale up within practical limits.

### 3.1. Choosing how to partition data

Two common patterns:

- **One task processes the entire batch:** simple, suitable when data volume is moderate or parallel splitting is unnecessary.
- **Multiple tasks process shards:** each task receives an independent slice of data, improving throughput and allowing partial recovery.

For example, a manifest file containing 100,000 records can be divided into 20 shards. Each task processes one shard. A task must know which shard belongs to it and have a way to determine whether each record has already been completed.

Do not partition data by having every task read the entire list and filter locally if the list is large. That multiplies read volume and increases cost. Store shard IDs in a manifest, use range partitioning, or query by partition key.

## 4. Environment variables for tasks

Cloud Run Jobs provides environment variables so the container knows the task's position in the execution. Commonly used variables include:

| Variable | Meaning |
|---|---|
| `CLOUD_RUN_TASK_INDEX` | Task index, starting from 0 |
| `CLOUD_RUN_TASK_COUNT` | Total number of tasks in the execution |
| `CLOUD_RUN_TASK_ATTEMPT` | Attempt count of the current task |
| `CLOUD_RUN_TASK_EXECUTION` | Name of the execution containing the task |

These variables are useful for partitioning data and logging. Do not use task attempt as an idempotency key because its value changes on retry. Business keys must remain stable across attempts.

For example, task index 3 in a 10-task execution can process shard 3. If using hash-based partitioning, you can determine the shard via index modulo task count. However, if task count changes between two executions, the mapping from record to shard can also change. Use record keys to protect idempotency at the business level rather than relying solely on shard assignment.

## 5. Writing a Java program to run in a Cloud Run Job

A Java program for Cloud Run Jobs typically uses `main` as its entry point. It reads environment variables, initializes clients, processes its assigned work, and exits.

The example below illustrates the structure of a worker that partitions data by task index. `BatchRepository` and `WorkItem` are application-defined adapters/models.

~~~java
public final class BatchMain {

    public static void main(String[] args) throws Exception {
        int taskIndex = Integer.parseInt(
                System.getenv("CLOUD_RUN_TASK_INDEX"));
        int taskCount = Integer.parseInt(
                System.getenv("CLOUD_RUN_TASK_COUNT"));
        int attempt = Integer.parseInt(
                System.getenv("CLOUD_RUN_TASK_ATTEMPT"));

        String execution = System.getenv("CLOUD_RUN_TASK_EXECUTION");

        if (taskCount <= 0 || taskIndex < 0 || taskIndex >= taskCount) {
            throw new IllegalStateException("Invalid task coordinates");
        }

        System.out.printf(
                "Starting execution=%s task=%d/%d attempt=%d%n",
                execution, taskIndex, taskCount, attempt);

        try (BatchRepository repository = BatchRepository.connect()) {
            Iterable<WorkItem> items =
                    repository.loadShard(taskIndex, taskCount);

            for (WorkItem item : items) {
                repository.processIdempotently(item);
            }
        }

        System.out.printf(
                "Completed execution=%s task=%d%n",
                execution, taskIndex);
    }
}
~~~

This is an architectural example; in a real application, define `BatchRepository`, `WorkItem`, connection logic, and shard queries according to your data source. When running locally outside Cloud Run, allow passing task index/count through local configuration or provide controlled defaults.

The key rule is that `main` must exit normally only when the task's entire portion of work is completed. If processing fails and Cloud Run should retry, let the exception propagate or exit the process with a non-zero exit code. Do not catch an exception, merely log it, and exit with code 0, because the platform will treat the task as succeeded.

### 5.1. Closing resources

Use `try-with-resources` for database connections, streams, and clients with lifecycles that require closing. If a client is reused across the process, check the library's close API carefully. When the task finishes, do not leave background threads continuing to process data after `main` returns.

Do not keep a thread alive just to wait for new work. Cloud Run Jobs runs tasks to completion; if you need to handle requests continuously, use a Cloud Run service or an appropriate worker consumer.

## 6. Packaging Java into a container image

Cloud Run Jobs runs container images. A straightforward deployment approach is building a JAR and packaging it with a Java runtime.

Example Dockerfile with Java 21:

~~~dockerfile
FROM eclipse-temurin:21-jre

WORKDIR /app
COPY target/batch-worker.jar /app/batch-worker.jar

ENTRYPOINT ["java", "-XX:MaxRAMPercentage=75.0", "-jar", "/app/batch-worker.jar"]
~~~

The application does not need `EXPOSE` or to listen on an HTTP port for a Cloud Run Job. When the container starts, the Java process runs and exits once the batch completes.

You can use Java 17 or another LTS version suitable for your project. Ensure the JDK/JRE version, dependencies, and native libraries are compatible with the build environment and target image. Use maintained base images with up-to-date security patches and avoid bundling unnecessary compilers/build tools into the runtime image.

### 6.1. Building and pushing the image to Artifact Registry

A typical workflow:

~~~bash
gcloud builds submit \
  --tag REGION-docker.pkg.dev/PROJECT_ID/batch-images/batch-worker:VERSION
~~~

Replace `REGION`, `PROJECT_ID`, and `VERSION` with your environment values. The Artifact Registry repository must exist and the build identity needs push permissions. After building, the Cloud Run Job references the image by the pushed URI.

Use immutable tags or image digests for production releases. If you overwrite the same tag, the job may run a different image without the deployment configuration clearly reflecting the change. Record commit, build ID, and image digest for traceability.

## 7. Creating and running a Cloud Run Job

You can create a job using the Google Cloud Console, `gcloud` CLI, API, or Infrastructure as Code.

CLI example:

~~~bash
gcloud run jobs create daily-reconciliation \
  --image=REGION-docker.pkg.dev/PROJECT_ID/batch-images/batch-worker:VERSION \
  --region=REGION \
  --tasks=20 \
  --parallelism=5 \
  --task-timeout=2h \
  --max-retries=3 \
  --cpu=2 \
  --memory=2Gi \
  --service-account=batch-worker@PROJECT_ID.iam.gserviceaccount.com \
  --set-env-vars=BATCH_MODE=reconcile
~~~

The values for task count, parallelism, timeout, CPU, memory, and retries are illustrative only. Choose values based on processing duration, data size, and dependency capacity. Certain limits depend on region, CPU type, and project quotas; check service limits before deploying to production.

Run the job manually:

~~~bash
gcloud run jobs execute daily-reconciliation \
  --region=REGION \
  --wait
~~~

The `wait` option tells the CLI to wait for the execution to finish before returning. For long jobs, you can launch the execution and track its status via the Console, CLI, or API.

Other useful commands:

~~~bash
gcloud run jobs describe daily-reconciliation --region=REGION

gcloud run jobs executions list \
  --job=daily-reconciliation \
  --region=REGION
~~~

If the job already exists, use the update command or redeploy via IaC to change the image and configuration. Do not manually edit multiple environments without updating the authoritative configuration source.

## 8. Stable sharding and preventing duplicate processing

Suppose a batch has 1 million records. You can shard by hashing the record ID:

~~~java
static int shardFor(String recordId, int taskCount) {
    return Math.floorMod(recordId.hashCode(), taskCount);
}
~~~

Each task processes only records whose shard ID equals its task index. This approach is simple, with one caveat: if `taskCount` changes, the same record may map to a different shard. For large datasets or repeated runs, it is better to build a manifest containing fixed shard assignments for a batch or use stable partition keys.

Each record should have durable processing state:

| Field | Purpose |
|---|---|
| `batch_id` | Business batch identifier |
| `item_id` | Identifier of the record to process |
| `status` | `PENDING`, `RUNNING`, `SUCCEEDED`, or `FAILED` |
| `attempt_count` | Number of processing attempts |
| `lease_until` | Timestamp when the current processing claim expires, if using leases |
| `result_ref` | Reference to the output |
| `updated_at` | Last update timestamp |

Use a unique key such as `batch_id + item_id` to ensure a record does not produce duplicate business side effects when a task retries. If writing data and marking `SUCCEEDED` happen in the same database, use a transaction. If side effects happen in an external service, pass a stable idempotency key to that service if supported.

### 8.1. Task retries vs. job re-executions

Distinguish between:

- **Task retry:** Cloud Run retries a failed task within the same execution, up to max retries.
- **New job execution:** an operator, scheduler, or workflow launches the job again.
- **Business replay:** operations asks to reprocess a selected batch or group of records.

A task retry can restart the code from the beginning. If a task processed 80% of its records before timing out, the retry needs to skip completed records and continue with the remainder. Do not rely on container memory or temporary files to track progress.

A new execution may rerun all tasks. Therefore, the batch ID must represent the business period, such as the report date or input file ID. Do not generate a new batch ID on every retry if the goal is resuming the same batch. If intentionally rerunning with new data, create a new batch ID and record its relationship to the prior batch.

## 9. Checkpointing and recovery for long tasks

For long-running tasks, split work into small units that can be committed and resumed. After each mini-batch:

1. Process a group of records.
2. Commit the results.
3. Write a checkpoint or mark items completed.
4. Proceed to the next group.

If the container times out or the process stops, the retry can read the checkpoint and resume. Checkpoints must be stored in a database or Cloud Storage; files in the container filesystem are not durable state for subsequent runs.

Do not record a checkpoint before the side effect has been confirmed. If you write the checkpoint first and the process crashes before updating data, the next run may skip an uncompleted record. If data is written but the checkpoint is not yet updated, the next run may re-execute the side effect; idempotency handles that case.

For large datasets, use a per-shard manifest and a cursor over a monotonically increasing key. Avoid offset pagination on continuously changing datasets because records can be skipped or processed twice when rows are inserted or deleted between reads.

## 10. Error handling and retry configuration

Cloud Run Jobs can retry failed tasks up to the configured retry limit. A task can fail due to:

- Container process exiting with a non-zero exit code.
- Task exceeding its timeout.
- Initialization or resource errors.
- Transiently unavailable dependencies.
- Invalid input data or business errors.

Retries help with transient errors such as network resets, service unavailability, or throttling. Retries will not fix malformed data, missing IAM permissions, or incompatible schemas.

Classify errors carefully:

| Error type | Suggested handling |
|---|---|
| Transient network error | Retry with backoff and limit |
| API throttling | Lower concurrency, retry with backoff |
| Malformed record | Record failed item in an error/quarantine table; do not retry infinitely |
| Missing IAM permissions | Fix permission configuration; automatic retries rarely help |
| Database overload | Lower parallelism, limit connections, and retry under control |
| Task timeout | Tune batch size, set an appropriate timeout, or split tasks smaller |
| Indeterminate side effect outcome | Query by idempotency key before retrying |

If a record has a permanent error, write it to a dead-letter table or error file, then continue processing other records if policy allows. Once all records have been processed or categorized according to policy, the task can exit successfully with clear summary counts. If the batch requires every record to succeed, the task must fail so the execution is marked failed.

Do not convert every exception into exit code 0 just to make the job appear green. Execution status must accurately reflect business outcomes.

## 11. Timeouts and safe termination handling

Task timeout limits how long a task is allowed to run. Choose a timeout based on p95/p99 processing time plus time needed for cleanup. Too low a timeout causes unnecessary retries; too high a timeout delays detecting hung tasks.

The application should:

- Split batches into small units for checkpointing.
- Set database and external API timeouts shorter than the overall task deadline.
- Stop picking up new records as the deadline approaches.
- Commit safe in-progress work and close resources.
- Log progress and checkpoints after committing.
- Ensure retries can resume without duplicating side effects.

The container may receive a termination signal when a task is stopped or times out. You can register a shutdown hook to close resources and attempt to flush logs, but do not rely on a hook to persist unique business results. The process may be forcibly killed or lack sufficient time to finish cleanup. Checkpoints must be persisted during normal processing.

## 12. Scheduling runs with Cloud Scheduler

Cloud Scheduler can invoke the Cloud Run Jobs API on a cron schedule. This suits daily reports, hourly syncs, or weekly cleanups.

Basic flow:

~~~mermaid
sequenceDiagram
    participant S as Cloud Scheduler
    participant A as Cloud Run Jobs API
    participant J as Job execution
    participant T as Tasks
    S->>A: Call run API on schedule
    A->>J: Create execution
    J->>T: Distribute tasks
    T->>T: Process batch and save results
    T-->>J: Exit code and status
    J-->>S: API acknowledges execution creation
~~~

The scheduler typically receives acknowledgement that the API accepted the request to create an execution; that does not mean the batch has finished. Monitor executions separately for final outcomes.

When creating a schedule, specify the timezone explicitly and define a policy if the previous run has not finished yet. Two executions can overlap if a new schedule fires while an old job is still running. Use a lock by batch ID, execution status checks, or an orchestration mechanism to prevent two concurrent runs for the same period.

The scheduler needs a service account with permission to call the Cloud Run Jobs API, including `run.jobs.run` on the target job. Use a dedicated identity, restrict resource scope, and configure appropriate OAuth settings when calling Google APIs. Never embed a service account key inside the scheduler payload.

Do not rely on a server's default timezone to interpret schedules. If the schedule is in local time, configure the timezone on Cloud Scheduler and check DST policies, especially for skipped or repeated hours.

## 13. Orchestrating multiple jobs with Workflows

Cloud Run Jobs executes a single batch unit. When a workflow comprises multiple dependent jobs, Google Cloud Workflows can orchestrate:

1. Run the data import job.
2. Wait for the execution to complete and check its status.
3. Run the data quality validation job.
4. Run the aggregation job.
5. Send notifications or generate reports.

Workflows manages ordering, conditional branching, retries, and errors across steps. You do not need to write a long-lived Java process that launches job A, sleeps waiting, and then calls job B.

When using Workflows, decide how to track Cloud Run Job execution completion. Accepting the run API call does not mean the job is done. A workflow can call the Cloud Run Jobs API to create an execution, retrieve the operation/execution name, and poll or use an appropriate wait mechanism until a terminal state is reached.

If the workflow is simply one schedule running one job, Cloud Scheduler may suffice. When multiple steps, conditions, or compensations are required, use Workflows to orchestrate.

## 14. Access permissions and security

Cloud Run Jobs uses a service account to define permissions for code inside the container when calling Google Cloud APIs. Create dedicated service accounts per job or responsibility group.

Key principles:

- Grant only necessary roles on the exact project or resource.
- Use Application Default Credentials inside the container to obtain the runtime identity.
- Never bundle service account JSON keys inside the image.
- Store secrets in Secret Manager and grant access only to jobs that need them.
- Never write access tokens, secrets, or sensitive data into logs.
- Restrict who can create, update, and run jobs.
- Separate job deployment permissions from job execution permissions.
- Use VPC egress/private connectivity if the job needs to access internal services.
- Enforce least privilege for Cloud Storage, BigQuery, Cloud SQL, or external API access.

For instance, a job reading files from one bucket only needs read permission on objects in that bucket. A job writing results to another bucket needs separate write permission. Do not grant project-wide Storage Admin if only object viewer and object creator on two specific buckets are required.

If the job accesses Cloud SQL, configure connections and networking per service guidelines. Limit connections per task and total connections across parallelism. Do not configure huge default connection pools because each task is its own container.

## 15. Connecting to data and dependent services

Batch jobs commonly read from Cloud Storage, BigQuery, Cloud SQL, Firestore, or Pub/Sub. Choose a reading pattern suited to the data size and type.

- For large files, read via streams or chunks, avoiding loading the entire file into the heap.
- For BigQuery, use appropriate queries/jobs and read results by page or stream.
- For databases, use keyset pagination and short transactions.
- For Pub/Sub, clarify whether the job reads a snapshot or processes messages; do not build a custom consumer lacking ack/lease semantics.
- For external APIs, enforce timeouts, rate limits, retries with backoff, and bounded concurrency.

If each task opens 5 database connections and 20 tasks run concurrently, the dependency may receive roughly 100 connections from that execution alone, excluding other workloads. Calculate total connections before increasing parallelism.

For file-processing jobs, use a manifest containing object name, generation/version, and checksum. If an object is replaced while the job is running, the worker must know which version it is processing. Passing version or generation makes results reproducible and easier to investigate.

## 16. Logging, metrics, and operations

Cloud Run collects container stdout and stderr into Cloud Logging. The Java application should emit structured logs linking records to the job, execution, and task.

Useful fields:

- Job name and execution name.
- `CLOUD_RUN_TASK_INDEX`, `CLOUD_RUN_TASK_COUNT`, and `CLOUD_RUN_TASK_ATTEMPT`.
- Batch ID and input manifest ID.
- Record ID or shard ID.
- Counts of records read, succeeded, skipped, and failed.
- Current checkpoint or cursor.
- Processing duration and dependency errors.
- Final task outcome.

Do not log full payloads or secrets. For large batches, avoid writing a log line per record if doing so inflates costs and adds noise. Use per-batch summary counters, detailed logs for errors, and controlled sampling.

Metrics to track:

- Execution counts: started, succeeded, failed, and timed out.
- Execution and task durations.
- Task retry count and average attempts.
- Record throughput per second or minute.
- Failed record count and pending record count.
- CPU, memory, and OOMs.
- Database connection usage and dependency latency.
- Overlapping execution count.
- Compute and storage cost per batch.

Set alerts when executions fail, task retries spike, jobs exceed SLAs, or batch backlogs grow. Maintain a dashboard by batch ID so operators can see which batch is running and what portion has finished.

## 17. Cost and resource optimization

Cloud Run Jobs bills for compute resources used while tasks run under current Cloud Run pricing. When a job is not running, no task containers are active processing batches; however, costs may still come from Artifact Registry, Cloud Storage, logging, networking, databases, or called services.

Costs depend on:

- CPU and memory per task.
- Execution duration of each task.
- Task count and number of retries.
- Parallelism and total batch completion time.
- Data read/written and network egress.
- Cloud Logging volume.
- Databases, BigQuery, and supporting services.
- Execution frequency.

Increasing parallelism can reduce wall-clock completion time without necessarily reducing total compute time. If tasks contend on a database or external API, excessive parallelism can lower throughput and increase retries.

To optimize:

1. Measure actual CPU and memory usage instead of over-provisioning heavily.
2. Pick a batch size large enough to amortize overhead while still checkpointing frequently.
3. Bound parallelism according to dependency capacity.
4. Use streaming to reduce peak memory.
5. Reduce repetitive success logs.
6. Avoid retrying unrecoverable errors.
7. Run the job in a region close to data and dependencies.
8. Track runtime and cost per business unit, such as cost per 1,000 records.

## 18. Testing a batch job

Test both the Java program and how Cloud Run distributes tasks:

1. Run locally with a single task and a small batch.
2. Run with multiple tasks to verify partitioning neither skips nor duplicates records.
3. Fail a task partway through and verify retries resume safely.
4. Inject a permanently failing record and verify the quarantine/dead-letter policy.
5. Test task timeouts and checkpointing.
6. Increase parallelism to observe database connections and API rate limits.
7. Rerun the same batch ID to verify idempotency.
8. Launch two concurrent executions to test locking and overlap policies.
9. Verify secrets do not appear in logs or container images.
10. Test with a service account lacking permissions and with least-privilege permissions.
11. Verify Cloud Scheduler invokes the job in the right timezone.
12. Verify Workflows waits for completion status, not just API run acceptance.

Do not check exit codes alone. Reconcile input record counts, completed record counts, quarantined record counts, and batch totals. A task can exit with code 0 while silently skipping records due to a logic bug; validating output data catches that issue.

## 19. Workflow for designing a Cloud Run Job in Java

1. **Define the workload.** How much data per run, what is the deadline, and is parallelism needed?
2. **Choose the task unit.** Does one task process the entire batch or does each task process one shard?
3. **Design partitioning.** Use task index/count or a stable partitioning manifest.
4. **Design idempotency.** Use batch ID and item ID, unique keys, and durable checkpoints.
5. **Write the Java process.** Use `main`, read config, execute the assigned work, close resources, and return the right exit code.
6. **Package the container.** Select a JRE, build the image, and store it in Artifact Registry.
7. **Configure the job.** Set task count, parallelism, timeout, retries, CPU, memory, and service account.
8. **Protect dependencies.** Bound connections, request rates, and access permissions.
9. **Choose how to trigger.** Use CLI/API for manual runs, Cloud Scheduler for schedules, or Workflows for multi-step flows.
10. **Observe and recover.** Log by batch/task, persist checkpoints, and alert on execution failures.
11. **Load and failure test.** Simulate retries, timeouts, overlapping executions, and slow dependencies.

Cloud Run Jobs suits Java batch workloads that need to run to completion without maintaining an HTTP server. Designing splittable, idempotent, checkpointed tasks enables jobs to resume safely after timeouts or retries; parallelism must be tuned to match dependent service capacity.

## 20. Self-check questions

- How do Cloud Run Jobs differ from Cloud Run services in container lifecycle and triggering?
- Which two aspects do task count and parallelism control?
- How are `CLOUD_RUN_TASK_INDEX` and `CLOUD_RUN_TASK_COUNT` used to partition data?
- Why is `CLOUD_RUN_TASK_ATTEMPT` unsuitable as an idempotency key?
- Which exit code must the container return when a task succeeds?
- What happens when a task times out or the process exits with a non-zero code?
- Why are durable checkpoints needed instead of temporary files alone?
- How do you prevent retries from executing side effects twice?
- What does Cloud Scheduler acknowledge when calling the Jobs API?
- When should you use Workflows to orchestrate multiple Cloud Run Jobs?
- Why must parallelism be sized according to database and external API limits?
- Which metrics help identify that a batch is running slowly or failing?

Cloud Run Jobs lets you package a Java batch application into an execution unit that can run on demand or on a schedule. Partition tasks by data, bound parallelism, persist progress durably, and design safe retries. That way, batch workloads can scale with demand without keeping an HTTP service running continuously.
