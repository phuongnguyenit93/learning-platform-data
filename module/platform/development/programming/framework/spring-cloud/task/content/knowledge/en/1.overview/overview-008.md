# Functional Limitations and Solution Selection Criteria

## 1. Placing Spring Cloud Task in Its Proper Role

**Spring Cloud Task** is suited for building Spring Boot applications **that run for a finite duration**: starting up, accepting arguments, processing a unit of work, recording the outcome, and terminating the process. Unlike an HTTP service or a continuously running consumer, a task run has a clear start and end point.

In the Spring ecosystem, the standout value of Spring Cloud Task is **execution lifecycle tracking**. When properly configured, the **TaskRepository** component stores metadata for each run in a relational database, helping answer:

- Which task ran, when did it start, and when did it finish?
- Which executions succeeded, failed, or never recorded an end timestamp?
- What identifier did the run have, what arguments did it carry, and what exit code did it return?
- Can external systems query the history for operations or auditing?

For example, in an e-commerce system, paid order data must be reconciled every night. A short-lived process receives the reconciliation date, executes processing, writes business results, and exits. Spring Cloud Task can store the run history of this process. However, **scheduling**, **duplicate-processing prevention rules**, **resuming from an interrupted record**, and **multi-step orchestration** are requirements that must be evaluated separately.

~~~mermaid
flowchart LR
    A["Trigger source: CronJob, API, operational tool"] --> B["Spring Boot + Spring Cloud Task app"]
    B --> C["Execute finite business logic"]
    B --> D["TaskRepository"]
    D --> E[("Metadata database")]
    C --> F["Business outcomes / target system"]
    B --> G["Terminate process, return exit code"]
~~~

Point to distinguish: **TaskRepository records the application execution**, while business data (reconciled orders, exported files, updated transactions, etc.) must still be managed by the corresponding business system. An execution record with exit code 0 does not by itself prove that all external side effects met requirements.

## 2. Functional Limitations to Understand Clearly

| Need | What Spring Cloud Task Provides | Limitations and Complementary Components |
| --- | --- | --- |
| Process lifecycle tracking | Creates and updates execution records, start/end timestamps, exit code, error info | Does not replace business logs, distributed traces, metrics, or alerting |
| Scheduled triggering | Can be launched by external systems | Not a standalone scheduler; use Kubernetes CronJob, a scheduler, or an orchestrator |
| On-demand execution | Application can receive arguments from CLI or environment | APIs, request authentication, queues, and process spawning must be designed externally |
| Large-volume data processing | Can run arbitrary data processing code | No built-in per-record chunk, checkpoint, skip, or retry mechanisms; consider Spring Batch |
| Restarting after failure | Has metadata from the previous run | Does not automatically resume the exact interrupted step/record; requires business logic or Spring Batch |
| Preventing duplicate runs | Each run has a distinct execution ID; concurrency limits for certain patterns can be configured in supported versions | Does not guarantee exactly-once processing across all systems; still needs locks, data constraints, and idempotency |
| Orchestrating multiple tasks | Each task application can be an execution unit | Does not natively model full DAGs, dependencies, approvals, and compensations; use an orchestrator or Spring Cloud Data Flow when appropriate |
| Continuous, low-latency processing | Can do work while running | Not suitable as a consumer or long-lived service just to ingest continuous events |
| Metadata governance | Stores execution info via TaskRepository | Requires designing schemas, access permissions, retention, cleanup, and database monitoring |

### 2.1. A Finite Lifecycle Is an Essential Condition

Spring Cloud Task shines when the work has a clearly defined **completion point**. Examples include generating a daily report, syncing a bounded dataset, loading a file, running a controlled migration, or computing a reconciliation period.

If an application opens a web server, keeps background threads alive, or continuously waits for messages, the process may not exit as expected. When that happens, the short-lived task model loses its purpose. For pure task applications, you can set the configuration properties:

~~~yaml
spring:
  main:
    web-application-type: none
  cloud:
    task:
      name: order-reconciliation
~~~

The application must still ensure that runners and background resources shut down properly. Disabling the web server **does not automatically shut down every thread or asynchronous task**.

### 2.2. Having Execution History Does Not Mean Having a Scheduler

Storing metadata for a run is a different responsibility from deciding **when** to run. You can use:

- **Kubernetes CronJob** when each run is packaged as a container and needs schedules, resource limits, and pod creation policies.
- **Quartz or an existing scheduler** when managing triggers and execution schedules inside an application/system.
- **An API or orchestration system** when an operator or another workflow decides the launch time.
- **Spring Cloud Data Flow** when the system already uses this platform to deploy, launch, and monitor tasks on supported infrastructure.

For recurring schedules, distinguish who is the **schedule authority** and who is the **execution state store**. Do not infer from the mere existence of a TaskRepository record that a task is scheduled, automatically retried, or automatically backfilled for missed runs.

### 2.3. Metadata Does Not Replace Business Fault Tolerance

A process can be stopped by a forced kill signal, out-of-memory error, database connection loss, or infrastructure termination. When the application fails to run its termination handlers in time, the execution record **may lack an end timestamp or fail to reflect the final state**. Therefore, you must add infrastructure-level process monitoring, timeouts, alerts for overly long runs, and a reconciliation procedure for abnormal executions.

Furthermore, writing metadata and writing business data are not by default inside **a single atomic transaction**. For example, a report file may have been uploaded to object storage, yet the process crashes before updating status. If re-run without verification rules, the system could create the file or send notifications twice.

Safe design typically requires:

1. **An explicit business key** for a unit of work, such as customer ID and reconciliation date.
2. **Idempotency**: repeating the same request causes no additional unintended side effects.
3. **Unique constraints or business state** in the datastore that owns the output.
4. **An explicit retry policy** specifying max attempts, backoff intervals, and retryable error types.
5. **Independent reconciliation** when the process status and business outcome status diverge.

Concurrency-limiting features for certain execution patterns, if used in the corresponding Spring Cloud Task version, only solve part of the overlap problem. They do not replace idempotency or duplicate-write prevention at the output datastore.

### 2.4. Chunking, Checkpoints, and Restarts Belong to a Different Scope

If the job processes millions of records and requires splitting into chunks, recording processed positions, conditional retry/skip, and resuming from the previous stop point, **Spring Batch** is the specialized choice. When combined with Spring Cloud Task:

- **Spring Cloud Task / TaskRepository** tracks a single run of the **application**.
- **Spring Batch / JobRepository** tracks the **job, steps, and batch processing state**.
- When appropriate integration is enabled, task and job execution records can be linked for traceability.

The two repositories address two different state layers. Do not rebuild a checkpoint mechanism by stuffing custom state into TaskRepository metadata.

## 3. Criteria for Deciding Whether to Use Spring Cloud Task

Before choosing a framework, describe the **unit of work**, **launch mechanism**, **success criteria**, and **failure handling**. The table below supports architectural evaluation:

| Criterion | Indicator Favoring Spring Cloud Task | Questions to Answer Before Deploying |
| --- | --- | --- |
| Lifecycle | Each run has clear inputs and termination criteria | Is the process guaranteed to exit after completion? |
| Traceability | Need to store execution history in a database for later inspection | How long must metadata be retained, and who may view it? |
| Frequency and latency | Periodic or on-demand work that tolerates application startup cost | Is frequency too high or SLA too tight relative to startup time? |
| Processing complexity | Finite work with few steps or delegable to specialized libraries | Are chunking, checkpoints, and step-by-step restarts needed? |
| Trigger source | Appropriate scheduler, API, orchestrator, or operational action exists | Who handles timeouts, retries, missed schedules, and concurrency limits? |
| Data state | Has business keys and safe re-run capability | If the process dies after writing partial results, how does the next run handle it? |
| Infrastructure | Reliable relational database and schema management process exist | Is TaskRepository ready when multiple processes start concurrently? |
| Operations | Logs, metrics, alerts, and execution lookup tools exist | How do we detect hanging tasks, duplicate runs, or tasks that never launched? |

**Selection rule:** use Spring Cloud Task when you need a short-lived application model **and** the benefits of persistently stored execution history. If you are only running a very simple script without needing this history, a CLI program, container job, or existing tool may suffice. If the complexity lies in batch processing, orchestration, or continuous event streams, add the specialized component.

~~~mermaid
flowchart TD
    A{"Does the work have a clear end point?"}
    A -->|No| B["Continuous service / consumer / event-processing system"]
    A -->|Yes| C{"Need checkpoints, chunks, step-level restarts?"}
    C -->|Yes| D["Spring Batch"]
    C -->|No| E{"Need persistent per-run execution history?"}
    E -->|No| F["Simple CLI, script, or container job"]
    E -->|Yes| G["Spring Cloud Task"]
    D --> H{"Want to run the job as a finite app with task metadata?"}
    H -->|Yes| I["Spring Batch + Spring Cloud Task"]
    H -->|No| J["Spring Batch with appropriate runtime infrastructure"]
    G --> K["Add scheduler / orchestrator if needed"]
    I --> K
~~~

This diagram only helps identify the **primary processing component**. For instance, whether you choose Spring Batch or Spring Cloud Task, if it must run at 2:00 AM daily, you still need a scheduled trigger mechanism.

## 4. Comparison with Common Alternatives

| Solution | Primary Strength | When to Choose |
| --- | --- | --- |
| **Spring Cloud Task** | Tracks lifecycle and metadata of finite Spring Boot applications | Short-lived work needing per-execution traceability |
| **Spring Batch** | Organizes job/step, chunks, checkpoints, restarts, skip/retry for batch processing | Large data volumes or needing granular recovery |
| **Spring Cloud Task + Spring Batch** | Provides both process history and batch processing state management | Batch jobs packaged as applications launched on demand/schedule |
| **Kubernetes Job / CronJob** | Runs processes in containers; manages schedules, pods, resources, and some retry policies | Need container execution and scheduling infrastructure; can combine with Spring Cloud Task |
| **Quartz / Spring Scheduling** | Organizes triggers or schedules within an application system | Primary requirement is scheduling; can trigger a separate task |
| **Spring Cloud Data Flow / workflow orchestrator** | Deploys, triggers, and orchestrates multiple tasks with dependencies | Workflows with multiple runs/dependencies needing a centralized operational UI |
| **Message consumer / long-lived service** | Continuously receives and processes events, typically optimizing latency and throughput | Events arrive continuously with no natural application end point |

These solutions are not mutually exclusive: **Spring Cloud Task is an execution-tracking layer**, while schedulers, container runtimes, Batch, and orchestrators can coexist to satisfy different requirements.

## 5. Real-World Selection Scenarios

### Scenario A — Nightly Order Reconciliation

**Requirement:** At 2:00 AM daily, reconcile the previous day's transactions; each run needs an identifier, timestamps, outcome, and the ability to diagnose failure causes.

**Recommendation:** Spring Cloud Task for the reconciliation process; Kubernetes CronJob or scheduler to launch it; TaskRepository stores history. Pass the reconciliation date as an input argument; place a unique constraint by reconciliation date/period in the business data. If re-running the same date, logic must recognize already-processed work.

**Evaluation point:** record count and reprocessing capability. If chunking and restarts are needed, add Spring Batch.

### Scenario B — Loading Five Million Rows from a File

**Requirement:** batching, resuming after errors, skipping invalid rows by policy, and knowing which batches completed.

**Recommendation:** Spring Batch is the processing core. Can be packaged as a Spring Cloud Task application if tracking each process launch is also desired. TaskRepository is **not sufficient** to replace JobRepository.

### Scenario C — Processing Order Events in Tens of Milliseconds

**Requirement:** continuous message ingestion, low latency, and high throughput.

**Recommendation:** long-lived service/consumer paired with an appropriate broker. Starting a new Spring Boot task for every message usually incurs unnecessary startup and database connection overhead.

### Scenario D — Workflow of Data Import, Validation, and Report Publication

**Requirement:** the next step only runs after the previous step succeeds; step-by-step retries and full-workflow monitoring are required.

**Recommendation:** a workflow system or Spring Cloud Data Flow (if infrastructure fits) handles orchestration; individual steps can be deployed as Spring Cloud Task. Each task's metadata still needs to link to the workflow ID/processing date for end-to-end lookup.

### Scenario E — One-Time Administrative Command

**Requirement:** update a small-scope configuration with no need to query execution history in a database.

**Recommendation:** a simple CLI or operational task can suffice. Do not add TaskRepository and metadata tables if they do not solve an actual requirement.

## 6. Sketching an Application to Verify Selection Criteria

Assume you have added the Spring Cloud Task dependency compatible with your Spring Boot/Spring Cloud version and configured a DataSource along with the metadata schema. The following minimal example illustrates **per-run inputs and finite termination**:

~~~java
@SpringBootApplication
@EnableTask
public class ReconciliationTaskApplication {

    public static void main(String[] args) {
        var context = SpringApplication.run(
            ReconciliationTaskApplication.class, args
        );
        System.exit(SpringApplication.exit(context));
    }

    @Bean
    ApplicationRunner reconciliationRunner(ReconciliationService service) {
        return args -> {
            var values = args.getOptionValues("businessDate");
            if (values == null || values.size() != 1) {
                throw new IllegalArgumentException(
                    "Must pass --businessDate=yyyy-MM-dd"
                );
            }

            LocalDate businessDate = LocalDate.parse(values.get(0));
            service.reconcileOnce(businessDate);
        };
    }
}
~~~

The example assumes a **ReconciliationService** bean and a **reconcileOnce** method implemented with a safe reprocessing policy. Java imports are omitted to focus on the processing flow.

Illustrative launch:

~~~bash
java -jar reconciliation-task.jar --businessDate=2026-11-23
~~~

After running, you can query history in the metadata table (exact table/column names depend on the corresponding Spring Cloud Task schema):

~~~sql
SELECT TASK_EXECUTION_ID, TASK_NAME, START_TIME,
       END_TIME, EXIT_CODE, EXIT_MESSAGE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'order-reconciliation'
ORDER BY START_TIME DESC;
~~~

Read both **execution status** and **business outcomes** together. If a record lacks an end timestamp, that is a signal to inspect the actual process rather than jumping to the conclusion that the task is still running. If the business outcome already exists yet the process reported an error, re-running must follow idempotency rules.

## 7. Safe Design and Operations Checklist

Before deploying the application to production, review the following points:

1. **Inputs and outcomes:** required arguments, formats, default values, exit codes, and the definition of "success" are clear; sensitive data is not written directly into task names, arguments, or logs.
2. **DataSource and schema:** TaskRepository points to the right database, the account has only necessary permissions, and schemas are managed via a migration process; do not rely on uncontrolled auto-table creation in production.
3. **Safe re-runs:** business keys, data constraints, or idempotent mechanisms exist; clearly define who manages retries, which errors are retried, and after how many attempts to stop.
4. **Parallelism and overlap:** decide whether multiple runs of the same task are permitted concurrently; if not, enforce it at the scheduler/runtime and business data layer.
5. **Timeouts and cancellation:** runtime limits exist; shutdown signals are handled where possible; procedures exist to inspect incomplete metadata after a crash.
6. **Observability:** logs include execution IDs and business keys for correlation; metrics cover success/failure counts, durations, late or missed runs; alerts match SLAs.
7. **Security:** do not put passwords, tokens, or sensitive customer data into persisted arguments; enforce permissions on who can trigger tasks and who can view history.
8. **Metadata lifecycle:** define retention periods, lookup indexes, cleanup policies, and database cost as run counts grow.
9. **Realistic failure testing:** test mid-run errors, database connection drops, duplicate launches, forced termination, and re-launching with the same business arguments.

## 8. Selection Conclusion

Choose **Spring Cloud Task** when a job has a finite lifecycle, needs persistent execution history, and is deployed as a standalone Spring Boot application. Choose **Spring Batch** when the focus is batch data processing with checkpoints and restarts. Use a **scheduler or orchestrator** when deciding when to run and coordinating multiple jobs; use a **long-lived service/consumer** for continuous event streams.

A sound architecture typically separates four responsibilities clearly: **who launches**, **who executes business logic**, **who stores execution metadata**, and **who prevents duplicate side effects on retries**. Separating these four responsibilities lets you leverage Spring Cloud Task within its intended scope without expecting the framework to solve the entire operational problem on its own.
