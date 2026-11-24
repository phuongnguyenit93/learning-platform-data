# Choosing One Large Job vs. Multiple Small Jobs in Spring Batch

When building a batch system, an early decision with long-lasting impact is whether to **bundle the entire workflow into one `Job` with multiple `Step`s**, or **split it into independent `Job`s and orchestrate them**. The exact same sequence—"read orders → validate data → reconcile → export report"—can be implemented either way, yet behavior around **restarts, progress tracking, deployment, error handling, and business independence** will differ substantially.

In *Spring Batch Core Processing*, a `Job` is a unit of work with its own identity (`JobInstance`), run parameters (`JobParameters`), execution history (`JobExecution`), and terminal status. A `Step` is a processing stage inside a job, with its own `StepExecution` history and checkpoints. Therefore, the question "one large job or multiple small jobs" is fundamentally about **choosing operational boundaries and recovery boundaries**.

This lesson covers selection criteria, Spring Batch 5.2.x configuration examples, job parameter design, orchestration strategies, failure recovery, and cases calling for a hybrid model. There is no rule that "more jobs is always better" or "one job is always faster"; the right design reflects **business units, dependency coupling, and how the system must recover**.

## 1. Distinguishing Job, Step, and Chunk Boundaries

Spring Batch has three levels to keep distinct:

| Level | Identity / State | Primary Purpose | Recoverability |
| --- | --- | --- | --- |
| **`Job`** | Job name, `JobParameters` identifying `JobInstance`; `JobExecution` has status | Represents a launchable/manageable business unit of work | Restart `JobInstance` when metadata and job permit |
| **`Step`** | Step name; each run has a `StepExecution` | A processing phase inside a job | Can skip `COMPLETED` steps and resume incomplete ones per restart rules |
| **`Chunk`** | Commit boundary inside a chunk-oriented step | Groups items to read, process, write, and commit | Reader/writer checkpoints persist per transaction, resuming after committed chunks |

Example of a three-step job:

```text
Job: dailyOrders
  |
  +-- Step: loadOrders         [chunk size 500]
  |      +-- read -> process -> write -> commit
  |      +-- read -> process -> write -> commit
  |
  +-- Step: validateOrders     [tasklet or chunk]
  |
  +-- Step: publishSummary     [tasklet]
```

One large `Job` **does not mean one large transaction**. In Spring Batch, each chunk/step has its own configured transaction mechanism. If `publishSummary` fails after `loadOrders` already committed data, Spring Batch **does not automatically roll back data from prior steps**. What a multi-step job provides is **a unified control flow and unified restart history**, not end-to-end atomicity.

Conversely, splitting into three jobs gives each job its own `JobInstance` and `JobExecution`. The framework does not automatically infer that they belong to the same business period or must run in sequence; you must add orchestration and correlation.

## 2. Two Fundamental Architectural Models

### Model A — One Job with Multiple Steps

```text
Trigger: 02:00 / businessDate=2026-11-15
                |
                v
        Job dailyOrders
                |
         +------+-------+
         |              |
         v              |
    loadOrders          |
         |              |
         v              |
   validateOrders       |
         |              |
         v              |
   publishSummary       |
         |              |
         v              |
    Job COMPLETED <-----+
```

Pros: one trigger, one job name, one set of identifying parameters, one `JobExecution` representing the run attempt, and `Step` flow managed by Spring Batch. When a middle step fails, restarting the same `JobInstance` resumes from the right step/checkpoint when properly configured.

Cons: stages are coupled to a single job lifecycle, making independent scheduling or permissions difficult. If the final optional reporting step fails, the entire `JobExecution` may fail to reach `COMPLETED` even though mandatory ingestion steps succeeded. Splitting deployments or code ownership is harder if every stage lives in the same application.

### Model B — Multiple Independent Jobs with Orchestration

```text
             Scheduler / Workflow Orchestrator
                          |
                          v
                 Job importOrders
                          |
                 COMPLETED for period X?
                     /         \
                   No           Yes
                   |             |
                Alert/stop       v
                           Job validateOrders
                                 |
                            COMPLETED?
                             /     \
                           No       Yes
                           |         |
                        Alert        v
                               Job publishSummary
                                     |
                                COMPLETED?
                                     |
                               Finish workflow
```

Pros: each job has its own schedule, SLA, permissions, retry/restart rules, and deployment lifecycle. The second job can be reused in another workflow; an optional reporting job can carry its own failure policy.

Cons: requires a **durable orchestrator** to track dependencies, persist workflow state, and deduplicate triggers. You cannot simply call `JobLauncher.run(jobA)` followed by `run(jobB)` in every setup, because `JobLauncher` may be configured asynchronously and return before A completes. Individual `JobInstance` statuses do not automatically form an overall workflow status either.

### Model C — Hybrid

Real-world systems often use several **medium-sized jobs**, each containing a handful of tightly coupled steps, while a scheduler/workflow orchestrator manages job-level dependencies.

```text
Workflow: daily-finance
  |
  +-- Job A: importOrders
  |     +-- fetch
  |     +-- normalize
  |     +-- writeStaging
  |
  +-- Job B: reconcilePayments
  |     +-- matchTransactions
  |     +-- verifyTotals
  |
  +-- Job C: publishFinancialReport
        +-- aggregate
        +-- render
        +-- deliver
```

This strikes a balance when distinct business units or schedules exist, yet each unit still benefits from step-level checkpointing and restarts.

## 3. Key Decision Criteria

| Criterion | Favors **One Multi-Step Job** | Favors **Multiple Small Jobs** |
| --- | --- | --- |
| **Business unit** | Steps form a single business outcome whose completion should not be split | Each part has its own business output and completion criteria |
| **Schedule** | Same trigger, same period, same deadline | Different run times, on-demand triggers, or distinct events |
| **Dependencies** | Linear, tightly coupled; later steps only make sense after earlier ones complete | Loose dependencies or expressible via a DAG/orchestrator |
| **Restart** | Want to restart one `JobInstance` and let Batch pick steps to rerun | Want to restart parts independently without touching others |
| **Intermediate data** | Small or referenceable via `ExecutionContext`/internal staging | Output has a durable contract consumed by other jobs |
| **SLA** | Single deadline covers the whole pipeline | Separate SLAs, alerts, and priorities per stage |
| **Ownership** | Same team owns everything and releases together | Multiple teams, codebases, access controls, or deployments |
| **Resources** | Steps share similar profiles and tune together | Different infra needs; must scale/isolate CPU, RAM, or connection pools |
| **Duration / concurrency** | Sequential stages with cohesive progress | One stage takes hours, another is near-real-time, or reused across workflows |
| **Reprocess independence** | Any failure should recover in the context of the whole period | Need to rerun reports/reconciliation without re-reading raw source |
| **Operational visibility** | A single overall `JobExecution` is the right abstraction | Each unit needs separate history, dashboards, and alerts |
| **Infra complexity** | Prefer leaning on Spring Batch's built-in orchestration | Already operate a reliable scheduler/workflow engine |

**Most useful tie-breaker question:** If the final step fails, does the operator want to say "**the whole job is unfinished**" and restart that single work item, or "**ingestion is done; only reporting failed**"? That answer usually points to the right job boundary better than source code size.

Never use **step count** as the sole criterion. A 15-short-step job can be straightforward to operate, whereas a single-step job reading an unreplayable API can be far harder to recover.

## 4. Example: One Large Job with Multiple Steps

Suppose the business unit is "process orders for a day." Requirements: fetch data, check quality, and write summary results; if validation fails, the report must not be published.

You can define a `Job` with a sequential flow:

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class DailyOrdersJobConfig {

    @Bean
    public Job dailyOrdersJob(
            JobRepository jobRepository,
            @Qualifier("loadOrdersStep") Step loadOrders,
            @Qualifier("validateOrdersStep") Step validateOrders,
            @Qualifier("publishSummaryStep") Step publishSummary) {

        return new JobBuilder("dailyOrders", jobRepository)
                .start(loadOrders)
                .next(validateOrders)
                .next(publishSummary)
                .build();
    }
}
```

This is **Spring Batch 5.x Job configuration**; the three `Step` beans must be defined in the application context with `JobRepository`, transaction manager, and real readers/processors/writers or tasklets. `.next(...)` chains steps when the flow advances normally. When a step fails, Spring Batch handles flow termination and restart state per configuration—it does not blindly run the next step.

### Meaning of a `JobInstance`

Example launching by `businessDate`:

```java
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;

JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("sourceVersion", "orders-v3", true)
        .addString("requestedBy", "scheduler", false)
        .toJobParameters();
```

In Spring Batch 5.2, `true` marks an identifying parameter. `JobInstance` is determined by job name and identifying values; `requestedBy` is non-identifying so orchestration metadata is recorded without altering business identity.

Inside a multi-step job, steps can share `businessDate` and `sourceVersion` from `JobParameters`. `@StepScope` beans resolve these values at runtime. If the job fails in `validateOrdersStep`, restarting with the exact same identifying parameters resumes using persisted step metadata—**not by starting a brand-new `JobInstance`**.

### Where Should Intermediate Data Be Stored?

A common mistake is treating `ExecutionContext` as a store for full datasets passed between steps. It is meant for **checkpoints and small metadata**, such as a staging file ID, business date, offsets, or batch keys. Never stuff millions of `Order` objects or huge DataFrames into the context—serialization, metadata DB writes, and restarts will become prohibitively heavy.

For large intermediate datasets:

```text
loadOrdersStep
   -> write staging_orders(batch_id, order_id, ...)
   -> ExecutionContext stores only batch_id / staging location

validateOrdersStep
   -> read staging by batch_id

publishSummaryStep
   -> read verified results and publish
```

Design staging data with consistent keys/versions and explicit cleanup. Durable intermediate storage frees restarts from relying on in-memory objects and also makes **splitting the job later** feasible.

## 5. Example: Splitting into Multiple Orchestrated Jobs

If order ingestion runs at 02:00, payment reconciliation at 05:00, and reporting can be regenerated independently when templates change, consider three independent `Job`s.

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersWorkflowJobsConfig {

    @Bean
    public Job importOrdersJob(
            JobRepository repository,
            @Qualifier("importOrdersStep") Step step) {
        return new JobBuilder("importOrders", repository)
                .start(step)
                .build();
    }

    @Bean
    public Job reconcilePaymentsJob(
            JobRepository repository,
            @Qualifier("reconcilePaymentsStep") Step step) {
        return new JobBuilder("reconcilePayments", repository)
                .start(step)
                .build();
    }

    @Bean
    public Job publishReportJob(
            JobRepository repository,
            @Qualifier("publishReportStep") Step step) {
        return new JobBuilder("publishReport", repository)
                .start(step)
                .build();
    }
}
```

This configuration **only declares three jobs**; it does not wire them into a workflow. The corresponding `Step` beans must be provided. A scheduler or orchestrator is responsible for running each job on time and triggering downstream jobs only after confirming upstream success criteria.

Example orchestration logic:

```text
workflowKey = (businessDate=2026-11-15, tenant=VN)

1. Start importOrders with the period key.
2. Wait for terminal execution; verify status is COMPLETED,
   and quality gates (row counts/skips/reconciliation) pass.
3. Record the output version / staging dataset from importOrders.
4. Start reconcilePayments against that exact output version.
5. After reconcilePayments finishes, allow publishReport.
6. If publishReport FAILED, restart only publishReport
   per its own rules; do not automatically rerun importOrders.
```

Remember: a `JobExecution` returned by `JobLauncher.run(...)` **is not necessarily finished** if `JobLauncher` uses an asynchronous executor. The orchestrator must await terminal status via its API/events/infrastructure—never launch the next job simply because `run` returned.

### JobParameters Do Not Automatically Link Across Jobs

With three independent jobs:

```text
JobInstance(importOrders, businessDate=2026-11-15, ...)
JobInstance(reconcilePayments, businessDate=2026-11-15, ...)
JobInstance(publishReport, businessDate=2026-11-15, ...)
```

They have **three separate job identities**, even with identical `businessDate`. Spring Batch does not automatically know which import execution `reconcilePayments` depends on. The orchestrator must store links such as:

| Workflow Field | Purpose |
| --- | --- |
| `workflowId` or `workflowKey` | Identifies the overall end-to-end run |
| `businessDate` / `tenant` | Identifies the business period |
| `importJobExecutionId` | Points to the accepted import run |
| `importOutputVersion` | Points to the immutable input dataset for reconciliation |
| `reconcileJobExecutionId` | Verified reconciliation run |
| `reportJobExecutionId` | Report publication run |
| `workflowStatus` | Overall orchestration-level outcome |

A workflow status is **orchestrator data**, not a built-in `BatchStatus` spanning multiple jobs. Persist this state durably if recovery is needed after an orchestrator crash.

## 6. Restart and Failure Recovery Drive the Boundary

Recovery characteristics are among the strongest reasons to pick one model over the other.

### One Multi-Step Job

```text
Job dailyOrders / JobInstance for day X
  loadOrders       COMPLETED
  validateOrders   FAILED
  publishSummary   NOT_STARTED

Restart same JobInstance:
  loadOrders       typically skipped
  validateOrders   reruns from checkpoint/step start depending on design
  publishSummary   runs after validation succeeds
```

Spring Batch consults `JobRepository` metadata to see which steps completed. A `COMPLETED` step is normally skipped on restart unless `allowStartIfComplete(true)` is set. Incomplete steps resume via `ExecutionContext` when supported by readers/writers and a stable source.

**Limitation:** a `COMPLETED` step does not mean out-of-transaction side effects can be undone if a later step fails. Business compensation must be designed explicitly.

### Multiple Independent Jobs

```text
importOrders       COMPLETED
reconcilePayments  COMPLETED
publishReport      FAILED

Restart only publishReport with appropriate identifying parameters.
The two prior jobs do not rerun automatically.
```

The advantage is isolating the rerun scope. However, if `publishReport` reads "latest data" instead of a **specific output version** from `reconcilePayments`, restarting later could read a different dataset. When splitting jobs, **inter-job data contracts** must be versioned and durably identified.

### What If Job A Fails After Writing Data?

Splitting jobs **does not automatically solve** the case where A commits partial data and then becomes `FAILED`. Job B should only start when A meets success conditions, or when an explicit contract allows partial-result handling. Never assume each batch job is business-atomic just because it appears as one node on a scheduler.

| Incident | One Multi-Step Job | Multiple Jobs |
| --- | --- | --- |
| Middle step fails | Job restart uses step metadata to resume | Restart only the failing job; orchestrator tracks dependencies |
| Final report step fails | May mark overall job `FAILED` | Report job `FAILED`, import job stays `COMPLETED` |
| Need to rerun only the report | May require `allowStartIfComplete` or splitting out a job | Run/restart report job independently |
| Input changes after failure | Can invalidate reader checkpoints | Can cause downstream job to read wrong data version |
| Scheduler/orchestrator crashes | In-job step flow is stored in Batch metadata | Must recover workflow state outside `JobExecution`s |
| Data written to external API before metadata commit | Needs idempotency/reconciliation | Still needs idempotency/reconciliation; splitting jobs adds no atomicity |

## 7. Transactions and End-to-End Atomicity

A dangerous misconception: "Putting all stages into one job rolls back everything if the final step fails." Spring Batch **does not guarantee a single ACID transaction across all steps of a job**.

Example:

```text
Step 1: load 100,000 orders into DB       COMMITTED
Step 2: reconcile transactions           COMMITTED
Step 3: call API to publish results      FAILED
```

When Step 3 fails, the prior two steps have already durably committed data. Undoing them requires explicit compensation rules such as `PENDING`/`PUBLISHED` states, release markers, outboxes, or sagas. This holds equally for one job and multiple jobs.

A common pattern for publishing workflows is **staging → validation → publish**:

1. Ingestion writes to staging keyed by `batchId`.
2. Validation verifies counts, records, and quality rules.
3. Publish idempotently flips dataset status to `READY`/`PUBLISHED` or emits an outbox event.
4. Consumers read only published datasets.

If Step 3 fails after Steps 1–2 succeed, the system can safely retry publishing without wiping staging. This resilience comes from **data and transaction design**, not from how many jobs you declare.

## 8. Parameters and Identity Must Be Designed Up Front

Whether using one job or many, `JobParameters` must reflect how the business defines **one logical unit of work**.

Example:

```java
JobParameters params = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("tenant", "vn", true)
        .addString("inputVersion", "orders-v3", true)
        .addString("correlationId", "daily-finance-2026-11-15", false)
        .toJobParameters();
```

In Spring Batch 5.2.x, `addString(name, value, true)` marks an identifying parameter. With the **same job name** and identifying parameters, the framework resolves the same `JobInstance`. Non-identifying `correlationId` links logs and workflows, provided its value aligns with operational rules.

When splitting into multiple jobs, each job may need **a different set of identifying parameters**:

| Job | Example Identifying Parameters | Why |
| --- | --- | --- |
| `importOrders` | `businessDate`, `tenant`, `sourceVersion` | A period can be reloaded from a newly managed source version |
| `reconcilePayments` | `businessDate`, `tenant`, `stagingVersion` | Must identify the exact dataset being reconciled |
| `publishReport` | `businessDate`, `tenant`, `reportVersion` | Allows re-exporting a report version without re-ingesting |

Do not pass Job A's `jobExecutionId` as an identifying parameter of Job B by default. If A restarts and produces a new execution ID for the exact same logical output, it can inadvertently mint a new `JobInstance` for B and duplicate work. If B **genuinely** needs to run once per published output from A, use a **stable output version identifier**, not an execution ID tied to a single retry attempt.

### Renaming Jobs When Refactoring Models

Job name is part of `JobInstance` identity. If you split `dailyOrders` into `importOrders` and `publishReport`, Spring Batch cannot migrate old `dailyOrders` checkpoints to the two new jobs automatically. Plan a cutover: drain or resolve in-flight instances, record IDs/contracts, schedule the transition, and audit already-processed outputs.

## 9. When Should You Just Add a Step Instead of a New Job?

Not every processing stage warrants a separate job. Prefer **a step within the same job** when:

- The step has no standalone business meaning if run in isolation.
- It always shares the same period and input identity and only serves the current flow.
- Its output is purely internal intermediate data with no independent SLA or external consumer.
- On failure, operators want to restart **the same overall work item**, not manage a separate workflow.
- Independent deployment or resource scaling is unnecessary.

For instance, `loadCsv → validateRows → writeOrders` in an ingestion pipeline naturally forms three steps of **one job**. Together they establish "orders for businessDate X have been imported."

Conversely, "publish analytics reports to clients" may deserve its own job if it needs an hourly schedule, independent report-template versioning, separate operator permissions, and regeneration without re-reading CSVs.

### `Flow` and Conditional Branching Inside One Job

If a job has branches, Spring Batch offers flow transitions, `JobExecutionDecider`, and parallel flow splits where appropriate. You do not need to create a new job just because of a branch like "if error count exceeds threshold, route to a quarantine step."

A flow inside a job remains bound to that job's lifecycle; **flows do not alter `JobInstance` identity** and do not merge committed steps into a single global transaction.

### Does `JobStep` Replace an Orchestrator?

Spring Batch lets a child job run as a step of a parent job via `JobStep` and its builder. This can help when reusing a child job while expressing sequence under one parent job inside the same application.

However, it adds an extra layer of identities, job parameters, and restart semantics between parent and child. If you just have three tightly coupled steps, three `Step`s are simpler. If you need independent deployments, SLAs, and external-system triggers, a parent `JobStep` cannot replace distributed workflow orchestration.

## 10. Scheduling, Dependencies, and Orchestration Reliability

Splitting into multiple jobs only succeeds when inter-job dependencies are orchestrated durably. Options include Spring schedulers, Quartz, Kubernetes CronJobs coordinated by an orchestrator, or workflow engines like Airflow/Argo depending on organizational infrastructure.

Answer at least six questions:

1. **Trigger:** what starts Job A/B—wall-clock time, an event, a request, or data readiness?
2. **Success criterion:** does B start merely when A has `BatchStatus.COMPLETED`, or also require quality gates on record counts/skip ratios?
3. **Deduplication:** if the scheduler delivers a completion event twice, how is B prevented from running twice?
4. **Recovery:** if the orchestrator crashes after A finishes but before launching B, what detects and resumes the workflow?
5. **Dependency data:** which exact output version of A does B read?
6. **Backfill:** when reprocessing day X while day Y is running, how are the two workflows isolated?

A simple **DAG**:

```text
importOrders(X) ──> reconcile(X) ──> publish(X)
                        ^
                        |
              exchangeRates(X)
```

Looking at this DAG, `reconcile(X)` has two inputs and can start as soon as both upstream sources finish, rather than being locked into a rigid job that reads only one output. Multi-source or multi-team dependencies are a strong signal for **multiple jobs + orchestrator**.

At the same time, orchestration must never blindly increment `run.id` on every event redelivery. It needs explicit contracts for `JobInstance`, input versions, and restarts to prevent duplicate processing.

## 11. Performance: Do Not Decide by Job Count Alone

One ten-step job is not inherently slower than ten one-step jobs, nor does splitting jobs automatically boost throughput.

Real performance drivers are usually:

- Whether readers use cursors/paging/streaming vs. loading everything into RAM.
- `chunkSize`, commit counts, and transaction overhead.
- Writer throughput, batch inserts, network latency, and API rate limits.
- Processor CPU cost and partitioning/scaling design.
- Connection pools, lock contention, and database isolation.
- Context startup overhead, execution metadata writes, and scheduler latency.
- Volume of intermediate data written and re-read between stages.

### When Parallelism Is Needed

Inside **one job**, consider `split` flows, `partitioning`, or Spring Batch concurrency features when semantics allow. A single job does not force all work to run sequentially.

With **multiple jobs**, each job can be deployed and scaled independently—for example, ingestion on high-bandwidth workers, reconciliation on CPU-heavy workers, and reporting on appropriately sized workers. Yet running more concurrent jobs can also increase contention on shared databases and message brokers.

| Bottleneck | What to Check Before Splitting the Job |
| --- | --- |
| One step processing 10M records is slow | Optimize reader/writer, chunk size, paging, partitioning |
| Sequential steps waiting on I/O | Tune pipeline, async processing, or parallel flows when valid |
| One stage needs drastically different resources | Consider separate job/deployment for independent scaling |
| Multiple jobs contend on locks in one table | Coordinate concurrency, partition keys, transactions/isolation |
| Context/metadata startup overhead is high | Measure overhead when splitting into many processes and schedules |

Never use "number of jobs" as a primary performance lever. Measure duration and throughput **per step**, inspect `readCount`/`writeCount`/`rollbackCount`, and only then evaluate structural changes.

## 12. Failure Isolation, SLAs, and Operational Permissions

Splitting jobs provides sharper control and monitoring boundaries, at the cost of more entities and rules to manage.

Consider three functions with very different policies:

| Function | SLA | Failure Reaction | Suggested Boundary |
| --- | --- | --- | --- |
| Daily data ingestion | By 04:00 | Halt downstream publish, inspect input, restart | One multi-step ingestion job |
| Transaction reconciliation | By 07:00 | High-priority alert; rerun per period | Independent reconciliation job |
| Email report delivery | By 09:00, independently retryable | Never re-ingest data just because SMTP failed | Independent delivery job or idempotent delivery task |

If all three are bundled into `dailyFinance`, an SMTP outage at 08:55 marks the entire job `FAILED`, making dashboards blur "data is reconciled" with "email not sent." Separating delivery makes sense **if** business rules recognize reconciliation as complete independently of email delivery.

However, if report publication is an inseparable part of the business SLA, you still need a **workflow-level success criterion**: even with separate jobs, the period has not met its SLA until publishing succeeds. Technical status independence must never replace the business definition of success.

### Permission and Change Boundaries

Multiple jobs shine when:

- Team A may restart ingestion, but is not authorized to rerun settlement.
- Team B deploys report template updates without redeploying the ingestion pipeline.
- Each job requires distinct resource budgets, retention/logging, and alert routing.
- Scheduler tooling supports per-job backfill approvals.

A single multi-step job can still expose step-level logs and metadata, yet job-level operational tooling rarely grants fine-grained permissions per individual stage.

## 13. Monitoring Across Multiple Job Boundaries

In a multi-step job, `JobExplorer` returns one `JobExecution` alongside its child `StepExecution`s; dashboards display that parent-child tree directly.

With multiple jobs, the system needs **cross-job correlation**:

```text
workflowId: daily-finance:2026-11-15:VN
  |
  +-- importOrders JobExecution 801      COMPLETED
  +-- reconcilePayments JobExecution 815 COMPLETED
  +-- publishReport JobExecution 902     FAILED
  +-- publishReport JobExecution 911     COMPLETED (restart)
```

Never determine "workflow completed" solely by checking **whether a `jobName` exists in `JobRegistry`**; `JobRegistry` only lists registered job definitions. Execution history lives in `JobRepository` and is queried via `JobExplorer`. A job that **was supposed to run but has no execution yet** must also be reconciled against the scheduler/orchestrator's expected schedule.

Useful KPIs:

| View | KPI | Source |
| --- | --- | --- |
| Job | `BatchStatus`, `ExitStatus`, duration, restart count | `JobExecution` / `JobExplorer` |
| Step | read/write/filter/skip, commit/rollback, duration | `StepExecution` |
| Workflow | Overall status, pending dependencies, end-to-end latency, SLA | Orchestrator + execution IDs |
| Quality | Valid record count, rejects, skip rate, count reconciliation | Batch metadata + business validation |
| Performance | Step/job latency, throughput, DB/API duration | Micrometer, logs/traces, and app metrics |

When splitting into multiple jobs, dashboards must distinguish **Job A completed** from **overall workflow completed** so downstream failures are never overlooked.

## 14. Step-by-Step Decision Model

Apply this decision tree to a candidate group of stages in a workflow:

```text
Do the stages share a single mandatory business outcome?
  |
  +-- No --> Consider multiple Jobs with separate SLAs/triggers.
  |
  +-- Yes
       |
       v
  Must groups of stages be launched, restarted, authorized,
  or deployed independently?
       |
       +-- Yes --> Split those groups into separate Jobs;
       |           define output contracts and orchestration.
       |
       +-- No
            |
            v
       Do they need Step/Chunk recovery and sequential
       execution under the same JobParameters?
            |
            +-- Yes --> One Job with multiple Steps is a sensible default.
            |
            +-- No --> Consider a single tasklet, flow, or another design.
```

A "sensible default" never replaces analyzing intermediate data, transaction boundaries, and whether sources can be replayed.

### Project Scoring Matrix

The design team can score each factor from 1 to 5 against real needs; below is an **illustrative example**, not a framework formula:

| Factor | Project Priority | High Priority Usually Favors |
| --- | ---: | --- |
| Restart across stages as one unit | 5/5 | One multi-step job |
| Independent schedules and SLAs | 2/5 | Multiple jobs |
| Independent deploys and ownership | 1/5 | Multiple jobs |
| Keeping orchestration simple | 5/5 | One multi-step job |
| Backfilling one stage without rerunning all | 4/5 | Multiple jobs |
| Intermediate data has its own output contract/version | 4/5 | Multiple jobs |
| Stages share one immutable input and period | 5/5 | One multi-step job |

When criteria pull in opposite directions, the answer is usually **grouping tightly coupled steps into medium-sized jobs**, rather than going to extremes with one monolithic job or one job per tiny action.

## 15. Three Concrete Design Scenarios

### Scenario A — Ingest a CSV File, Normalize, and Write to Database

Requirements: each file has a `businessDate`, must be parsed, validated, deduplicated, and written to DB. All stages belong to one business transaction: "import file X."

**Suggestion:** one `Job` `importCsvOrders` with multiple steps, or a chunk step plus a summary verification step if needed. Checkpointed reader, idempotent writer, invalid rows quarantined per policy. Split out a separate quarantine job only if it has an independent schedule, permission model, or SLA.

Why: all steps share one input identity, one restart requirement, and no independent launch purpose.

### Scenario B — Import Orders, Reconcile, and Send Reports

Requirements: import runs overnight, reconciliation waits for bank feeds, reports send during business hours and can be regenerated when templates change.

**Suggestion:** three independent jobs orchestrated in one workflow keyed by `businessDate` and output versions:

```text
importOrders(datasetVersion=X)             COMPLETED
                 |
                 +--> reconcile(bankSnapshot=Y) COMPLETED
                               |
                               +--> publishReport(reportVersion=Z)
```

Why: distinct triggers, external dependencies, SLAs, and change lifecycles. The orchestrator tracks the relationships among X/Y/Z while ensuring publishing is idempotent.

### Scenario C — Run 50 Partitions of a Large Computation

Requirements: identical algorithm processing data by region or ID range, needing horizontal scaling and per-partition restarts.

**Do not default to creating 50 separate jobs.** Spring Batch supports **partitioning**, allowing a single job/step to spawn 50 independent partition `StepExecution`s, each worker receiving its own data slice. Job-level orchestration stays clean and partition metadata aids troubleshooting.

Separate jobs may fit if each region is a **business unit with its own schedule, permissions, and SLA**, but worker count alone is never a reason to split jobs.

## 16. Migrating from One Large Job to Multiple Small Jobs

When a single job grows hard to maintain, split along **business boundaries with explicit output contracts**, not along Java method or class names.

Suggested roadmap:

1. **Map the current flow:** list every step, inputs/outputs, checkpoints, side effects, durations, and dependencies.
2. **Group by independent outcomes:** identify which stages genuinely have separate SLAs, triggers, ownership, or reruns.
3. **Define intermediate data contracts:** dataset IDs, schema versions, completeness markers, checksums, and business keys.
4. **Design identifying parameters:** appropriate business dates, tenants, and versions for each new job.
5. **Add orchestration state:** workflow IDs, mappings from execution IDs to output versions, and trigger deduplication.
6. **Migrate schedules and permissions:** resolve any in-flight `FAILED`/`STARTED` old instances, deciding whether to restart on old code or perform a controlled replay.
7. **Shadow-run in staging:** compare data counts, correctness, latency, failure behavior, and restart scenarios.
8. **Cut over to production with a runbook:** prevent old and new jobs from writing ambiguously to the same dataset.
9. **Preserve history:** maintain a mapping from old jobs/instances to new workflows for auditing and investigation.

**Do not wipe Batch metadata to "clean history" during a job split.** New job names create new identities; reconcile already-processed data and preserve traces to avoid duplicate backfills.

### When Merging Multiple Jobs into One

Merging also brings trade-offs: you may lose independent restarts/reruns, need refactored `JobParameters` and schedules, alter operational permissions, and let final-step failures turn the whole job `FAILED`. If the separate jobs already have external consumers or independent output versions, do not drop those contracts merely because they became steps.

## 17. Testing the Architectural Choice

Do not test only the "green path"—test **how failures and recoveries behave** across your chosen boundaries.

| Test | One Multi-Step Job | Multiple Independent Jobs |
| --- | --- | --- |
| Happy path | Steps finish in order; job `COMPLETED` | Orchestrator runs dependencies in order |
| Mid-pipeline failure | Job `FAILED`, subsequent steps do not run | Downstream job is not triggered |
| Restart same period | Completed steps skipped; failing step resumes properly | Restart only failing job; prior jobs do not rerun |
| Failure after data commit | Zero duplicates or data loss on restart | Output version/idempotency keeps downstream safe |
| Concurrent jobs/workers | State/checkpoints do not race | Two competing executions are not launched for same identity |
| Input version changed | Detects source mismatch against checkpoint | Downstream blocked if output version is no longer valid |
| Scheduler disconnect | No unintended duplicate `JobInstance`s | Workflow state recovers when orchestrator restarts |
| Historical backfill | Does not disturb current active period | Related jobs process the exact backfill period dataset |
| Failed quality gate | Flow halts or branches per policy | Downstream blocked even if upstream job technically `COMPLETED` |
| Observability | All `StepExecution`s traceable under one job | All execution IDs traceable under one `workflowId` |

For Spring Batch 5.2.x, `spring-batch-test` provides `JobLauncherTestUtils`, `JobRepositoryTestUtils`, and scoping support for integration tests. For restart tests, use a test `JobRepository` that preserves data across **both executions in the same scenario**—do not wipe metadata between the `FAILED` run and the restart. Clean up the repository before/after tests only as needed to keep tests isolated.

### Typical Assertion Pattern for a Multi-Step Job

```java
// Pseudocode: job/step beans, test database, and fault injection
// are defined by the application.
JobExecution first = launcher.run(dailyOrdersJob, fixedParameters);
assertEquals(BatchStatus.FAILED, first.getStatus());

disableFailureInValidateStep();

JobExecution second = launcher.run(dailyOrdersJob, fixedParameters);
assertEquals(BatchStatus.COMPLETED, second.getStatus());

// Verify loadOrders did not write duplicate data.
// Verify publishSummary ran only after validation succeeded.
// Reconcile output business IDs, not just StepExecution.writeCount.
```

This is **illustrative pseudocode**, not a self-contained runnable unit test since infrastructure and `disableFailureInValidateStep` are omitted. For multi-job architectures, also test orchestration: duplicate upstream completion events spawn only one downstream logical run, and an orchestrator crashing between triggers resumes cleanly.

## 18. Common Mistakes

| Mistake | Consequence | Correction |
| --- | --- | --- |
| "Every processing class is its own job" | Too many triggers, parameters, metadata, permissions, and links | Group into steps around business units |
| "One job is a single transaction" | Assuming earlier steps roll back when the last step fails | Design transactions, staging, and compensation |
| Splitting jobs without durable orchestration | Downstream runs out of order or gets dropped after crash | Explicit workflow state, dependencies, and retry/dedup |
| Treating "Job A is `COMPLETED`" as sufficient to run B | Quality gates or reconciliation may not have passed | Separate technical status from business acceptance |
| Passing "latest" data between jobs | Restarts read different input than the prior run | Version outputs/datasets and pass explicit identifiers |
| Changing `run.id` to rerun instead of restarting | Mints new `JobInstance`, risks duplicates | Preserve identifying parameters when restarting the right instance |
| Storing large data in `ExecutionContext` | Bloated metadata, serializer errors, slow restarts | Use durable staging and keep only references in context |
| Turning on `allowStartIfComplete(true)` to mask bugs | Completed steps rerun unexpectedly | Enable only when required and idempotent |
| Adding more jobs to go faster | Increases startup overhead and resource contention | Profile bottlenecks; look at partitioning/chunking first |
| One monolithic job across incompatible SLAs | Hard to alert and rerun selectively | Split by domain, SLA, deployment, and permissions |
| Checking only `JobRepository` for missed runs | Un-triggered jobs have no metadata rows | Reconcile against orchestrator's expected schedule |
| Independent job DBs without reconciliation | No cross-job transaction; intermediate data drifts | Durable output contracts, idempotency, replay policy |

## 19. Finalizing the Design

When deciding, write out the completion statement for each unit:

> "For `businessDate` X, `importOrders` is complete only when source data has been parsed, validated, written, and count-reconciled. If any stage fails, that same work unit must restart from a safe checkpoint."

If that sentence accurately describes a cohesive pipeline, **one multi-step job** is usually right.

> "For `businessDate` X, `importOrders` completes and publishes dataset version V. `reconcilePayments` consumes V alongside bank feeds; `publishReport` can rerun independently over verified reconciliation results."

If that reflects how the business operates, **multiple jobs with output contracts and an orchestrator** make more sense.

When there is no clear need for separate schedules, permissions, SLAs, or deployments, **do not split jobs just to avoid a longer configuration file**. When stages are genuinely independent, **do not force them into one `JobInstance` just to get a single row on a dashboard**. Draw boundaries around recovery, data contracts, and operations—not around Java class counts.

## 20. References

The examples above use the **Spring Batch 5.2.x** API. In Spring Batch 6.x, some packages and APIs have changed; consult documentation matching your project dependencies when copying configuration.

- [Spring Batch Reference 5.2 — Job domain and JobInstance](https://docs.spring.io/spring-batch/reference/5.2/domain.html)
- [Spring Batch Reference 5.2 — Configuring a Job](https://docs.spring.io/spring-batch/reference/5.2/job/configuring.html)
- [Spring Batch Reference 5.2 — Configuring a Step](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/configuring.html)
- [Spring Batch Reference 5.2 — Configuring Step Flow](https://docs.spring.io/spring-batch/reference/5.2/step/controlling-flow.html)
- [Spring Batch Reference 5.2 — ItemStream and ExecutionContext](https://docs.spring.io/spring-batch/reference/5.2/readers-and-writers/item-stream.html)
- [Spring Batch Reference 5.2 — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/5.2/scalability.html)
- [Spring Batch Reference 5.2 — Advanced Metadata Usage / JobOperator](https://docs.spring.io/spring-batch/reference/5.2/job/advanced-meta-data.html)
- [Spring Batch Reference 5.2 — Testing](https://docs.spring.io/spring-batch/reference/5.2/testing.html)
- [Spring Batch 5.2 API — JobBuilder](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/job/builder/JobBuilder.html)
- [Spring Batch 5.2 API — JobExplorer](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/explore/JobExplorer.html)

**Conclusion:** Choose **one `Job` with multiple `Step`s** when stages produce one joint business outcome, run in the same period, and need unified restarts. Choose **multiple `Job`s** when each stage needs independent triggers, SLAs, deployments, operator permissions, or reruns—in exchange for building durable orchestration and explicit inter-job data contracts. Either way, restart correctness still depends on checkpoints, transactions, source versioning, and idempotent writers—never on job count alone.
