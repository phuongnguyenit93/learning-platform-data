# Job Dependencies and Workflow Orchestration

A background processing pipeline often consists of multiple interrelated jobs. A data ingestion job must finish before a cleaning job starts; jobs processing individual partitions can run in parallel; an aggregation job may run only once all partitions are done; finally, a validation step decides whether to publish the results. If each job is scheduled independently, the system can easily execute out of order, process unready data, or skip steps when a job fails.

**Job dependencies** describe the conditions allowing a job to start or be considered complete. **Workflow orchestration** manages the ordering, state, conditions, retries, timeouts, schedules, and outcomes of the entire pipeline.

In **CLOUD_CORE_SERVICES_COMPUTE**, workflows can run on VMs, containers, Kubernetes Jobs, batch services, or serverless tasks. The design must decouple business logic from the orchestrator, model dependencies explicitly, control concurrency, and ensure the pipeline can resume or recover when a worker, node, or service fails.

## 1. Jobs, tasks, and workflows

Terminology can vary across platforms, but usually carries these meanings:

- **Job:** a unit of work with a clear completion objective, such as importing a dataset or generating a daily report.
- **Task/step:** a smaller step within a job or workflow, usually with its own input, output, and status.
- **Worker:** the process or container executing a job/task.
- **Queue:** where pending work requests wait for a worker to claim them.
- **Workflow:** a collection of jobs/tasks along with their dependency relationships and orchestration rules.
- **Scheduler:** the component deciding when or in what order jobs are dispatched for execution.
- **Orchestrator:** the component managing state and coordinating steps across a workflow.

A job can run on a VM, in a container, as a Kubernetes Job, or via a managed batch service. A workflow should not be coupled to a specific worker; it should describe the work to be done and dispatch it to suitable workers for execution.

### 1.1. Characteristics of a good job

A job should have:

- A unique identifier for the run or data unit.
- Clearly defined inputs and outputs.
- Verifiable completion criteria.
- Timeouts and resource limits.
- Controlled retry behavior.
- Idempotency or duplicate-prevention mechanisms.
- Sufficient logs, metrics, and status for investigation.
- A way to cancel or recover when execution is interrupted.

A job should process a bounded data scope. Jobs that are too large are hard to retry and recover; jobs that are too small can introduce excessive orchestration, queue, and network overhead.

### 1.2. Workflows as a dependency graph

Workflows are commonly represented as a directed graph. Each node is a job or task; each edge indicates that one step must finish or satisfy a condition before another step runs.

Example data pipeline:

~~~mermaid
flowchart TD
    A["Load data"] --> B["Validate format"]
    B --> C["Clean data"]
    C --> D1["Process partition A"]
    C --> D2["Process partition B"]
    C --> D3["Process partition C"]
    D1 --> E["Aggregate"]
    D2 --> E
    D3 --> E
    E --> F["Quality check"]
    F --> G["Publish results"]
~~~

The data loading and format validation jobs run sequentially. Once cleaning finishes, the three partition jobs can run in parallel. The aggregation job is a fan-in step waiting for results from all branches. Results are published only after quality checks pass.

## 2. Types of job dependencies

Dependencies are not merely "job A runs before job B". You must clearly describe the exact condition allowing the next job to start.

### 2.1. Completion-order dependencies

Job B can only start after Job A finishes. Depending on the workflow, "finishing" can encompass multiple states:

- Run B only when A succeeds.
- Run B after A finishes regardless of success or failure.
- Run B only if A fails.
- Run B if A was skipped under a defined condition.

For example, a temporary resource cleanup step should run after a processing job ends, even if the processing job failed. Meanwhile, a publish step only runs if all validation steps succeed.

### 2.2. Data dependencies

Job B requires outputs produced by Job A. Dependency conditions should verify both the existence and validity of the data:

- Files or objects have finished writing.
- The manifest contains all required partitions.
- Schema and version are compatible.
- Checksums or record counts meet expectations.
- Data is committed and readable from the consumer location.

Merely checking whether a file exists can be insufficient. Job A might leave an empty file, a partial write, or an output with the wrong version.

### 2.3. Resource or service dependencies

A job runs only when required resources are ready:

- The database is provisioned and accepting connections.
- Volumes are attached and mounted.
- Container images are pulled.
- Credentials or secrets are issued.
- Suitable GPUs or node pools have available capacity.
- External API rate limits allow proceeding.

These dependencies can change over time. The orchestrator must distinguish between "not ready yet, wait" and "cannot be satisfied, terminate or branch to failure".

### 2.4. Time and schedule dependencies

A job may depend on:

- A fixed wall-clock time, such as running after 01:00 UTC.
- A data window, such as processing only closed business days.
- An event arriving from another system.
- A minimum cooldown wait after a step.
- A deadline by which execution must finish.

Schedules and dependency graphs are separate concepts. A schedule triggers a workflow run; the dependency graph defines the ordering and conditions between steps within that run.

### 2.5. Conditional dependencies

Workflows can branch based on outputs or statuses:

- If data contains new records, run the transform step.
- If no new data exists, record a no-op and succeed.
- If quality checks fail, route to quarantine.
- If the error is recoverable, retry.
- If the error is unrecoverable, route to a manual handling branch.

Conditions should be evaluated from structured outputs or explicit states, avoiding parsing text logs to infer business logic.

## 3. DAGs and execution order

DAG stands for Directed Acyclic Graph, a directed graph with no cycles. DAGs are the standard representation for batch workflows because they identify steps that can run in parallel without creating dependency loops.

### 3.1. Directed

An edge A → B means B depends on A under a defined condition. Edge direction must be consistent: from predecessor step to successor step.

### 3.2. Acyclic

If A depends on B, B depends on C, and C depends on A, no step can ever start. The orchestrator should check for cycles before accepting a workflow.

Some business workflows contain loops, such as retrying a check step or paginating through data. Do not express loops by creating cycles in a static DAG. Use bounded loops, map/reduce, retry policies, or child workflows with clear termination conditions.

### 3.3. Topological order

A topological order is a valid linear ordering of nodes such that every predecessor appears before its successors. Multiple valid orderings can exist when some jobs are independent.

Example:

~~~text
fetch -> validate -> transform
                    |-> partition-A
                    |-> partition-B
                    |-> partition-C
                         |
                         v
                      aggregate -> publish
~~~

The three partitions can run in any order or concurrently, as long as `transform` has finished and resources are sufficient.

### 3.4. Critical path

The critical path is the longest dependency chain determining the earliest possible completion time of a workflow when all required resources are available.

If `fetch` takes 2 minutes, `validate` 1 minute, `transform` 3 minutes, the three partitions take 8, 5, and 6 minutes respectively, `aggregate` takes 2 minutes, and `publish` takes 1 minute, then the `partition-A` branch is the longest path. Ideal total duration is 2 + 1 + 3 + 8 + 2 + 1 = 17 minutes, excluding queuing, worker startup, retries, and resource contention.

Optimizing a job off the critical path may not reduce overall completion time. Optimizing jobs on the critical path or increasing parallelism on the longest branch usually has a much greater impact.

## 4. Sequential, parallel, fan-out, and fan-in

### 4.1. Sequential

Steps run one after another when the previous step's output is a required input for the next. Serialization is simple and easy to control, but increases total duration.

### 4.2. Fan-out

One step splits data or work into multiple independent branches. For example, splitting a dataset into 100 partitions and dispatching them to workers in parallel.

Fan-out must specify:

- Maximum branch count.
- Size of each partition.
- Naming and identification scheme for outputs.
- How to retry a failed branch.
- How to limit concurrency and resources.
- How to handle missing or duplicate partitions.

Do not spawn unbounded tasks just because the input has many items. Cap fan-out to avoid exhausting quotas, creating too many pods, or overloading databases.

### 4.3. Fan-in

Fan-in waits for results from multiple branches before continuing. Completion criteria can be:

- All branches succeed.
- A threshold percentage of branches succeed.
- A minimum number of results is reached.
- A deadline expires and missing branches are handled per policy.

If a workflow requires all partitions, do not mark fan-in successful merely because most branches completed. If partial results are acceptable, explicitly record missing partitions and reflect a partial-success status.

### 4.4. Map and reduce

Map applies the same processing operation across many elements or partitions. Reduce aggregates those results into a single shared output. This pattern is widely used in ETL, analytics, image processing, batch inference, and distributed computing.

Example:

1. Read a manifest of 500 files.
2. Map creates tasks to process each file group.
3. Workers write outputs keyed by partition ID.
4. Reduce reads the output manifest and verifies all partitions are present.
5. Aggregate and write the final result.

Pass references to objects or manifests rather than stuffing large data directly into orchestration payloads.

## 5. Orchestration vs. choreography

Two common organizational styles are centralized orchestration and event-driven choreography.

### 5.1. Orchestration

A workflow engine or orchestrator maintains overall state and decides the next step.

Pros:

- Full visibility into the entire workflow state.
- Easy to express dependencies, branches, timeouts, and retries.
- Provides execution history and resume capabilities.
- Can enforce global policies for concurrency and deadlines.

Trade-offs:

- The orchestrator is a critical component requiring HA and backups.
- Workflows can become coupled to the platform's API or state format.
- Massive workflows can create state persistence and coordination load.

### 5.2. Choreography

In choreography, each service emits an event upon completion or state change. Other services subscribe to events and independently decide what action to take.

Pros:

- Services have minimal direct dependency on a central coordinator.
- Scales naturally by event consumers.
- Fits event-driven architectures and autonomous service teams.

Trade-offs:

- Hard to inspect overall end-to-end progress.
- Easy to introduce event loops or duplicate processing if contracts are unclear.
- Requires correlation IDs, event schemas, idempotency, and tracing.
- Hard to determine overall completion state without a process manager.

### 5.3. Comparison

| Criterion | Orchestration | Choreography |
| --- | --- | --- |
| Control | Central engine decides next step | Services react to events |
| State tracking | Workflow engine holds state | Distributed across services/event stores |
| Dependencies | Explicitly declared in workflow | Expressed via event contracts |
| Process changes | Edit workflow definition | Modify producers/consumers and contracts |
| Best fit | DAGs, batches, multi-step processes | Event-driven, independent services |
| Risks | Orchestrator dependency and state growth | Harder observability, event loops, eventual consistency |

Both models can be combined. A workflow engine orchestrates the high-level pipeline while individual services use events to execute internal steps.

## 6. Workflow state and lifecycle

The orchestrator must persist state durably so it can resume after a worker or control process restarts.

### 6.1. Common states

| State | Meaning |
| --- | --- |
| Pending | Waiting on dependencies, schedule, or capacity |
| Ready | Eligible to be dispatched |
| Queued | Placed into a queue |
| Running | Worker is executing |
| Succeeded | Completed and output verified |
| Failed | Terminated due to unrecoverable error per policy |
| Retrying | Waiting for next execution attempt |
| Skipped | Bypassed due to workflow condition |
| Cancelled | Cancelled by request or policy |
| TimedOut | Exceeded execution time limit |
| Compensating | Executing compensating actions |
| PartialSuccess | Only a subset of branches completed per policy |

Do not lump every failure into a single `Failed` state. Timeouts, cancellations, dependency failures, and validation failures should be distinguished for accurate retries and reporting.

### 6.2. Job state vs. workflow state

An individual job can succeed while the workflow is still running because other branches remain active. The workflow completes only when all required steps and termination conditions are met.

Example:

- 9 out of 10 partitions succeed.
- The remaining partition is retrying.
- The workflow remains `Running` or `Waiting`, not yet marked `Succeeded`.
- If policy permits partial results after a deadline, the workflow may finish as `PartialSuccess`.

### 6.3. Durable state and checkpoints

State must be persisted durably, not kept only in RAM of the orchestrator or workers. Depending on the system, state may include:

- Workflow ID and run ID.
- Job ID and attempt number.
- Dependency status.
- Input/output references.
- Checkpoints and offsets.
- Timestamps and deadlines.
- Worker lease or ownership token.
- Error classification and retry schedule.

Checkpoints allow resuming from a saved milestone instead of rerunning an entire job. Checkpoints must be written in a safe order and tied to data versions to avoid resuming on mutated inputs.

## 7. Managing inputs, outputs, and artifacts between jobs

Workflows need a clear data contract between producers and consumers.

### 7.1. Pass data directly or by reference?

Small payloads like job IDs, partition IDs, versions, and URIs can travel through queues or workflow state. Large data should reside in object storage, shared storage, or databases and be passed by reference.

| Transfer method | Best fit | Risks |
| --- | --- | --- |
| Payload in message | Small metadata, short commands | Size limits, data duplication |
| Object storage reference | Large files, batch outputs | Requires access permissions, lifecycle, and consistency |
| Shared filesystem | Multiple workers reading/writing shared files | Locking, mount topology, and throughput |
| Database record | Transactional state or queryable metadata | Connection pressure and schema coupling |
| Queue/event | Asynchronous notifications and work distribution | Duplicates, ordering, and retention |

### 7.2. Output manifests

For fan-out/fan-in, a manifest describes each branch's output:

~~~json
{
  "workflow_id": "daily-report-2026-11-22",
  "input_version": "dataset-v42",
  "partitions": [
    {
      "partition_id": "part-000",
      "status": "SUCCEEDED",
      "uri": "s3://example-bucket/output/part-000.parquet",
      "checksum": "sha256:..."
    },
    {
      "partition_id": "part-001",
      "status": "SUCCEEDED",
      "uri": "s3://example-bucket/output/part-001.parquet",
      "checksum": "sha256:..."
    }
  ]
}
~~~

This is an illustrative structure. Real manifests need schema versions, timestamps, owners, and data verification fields. Consumers should read only outputs marked completed and verified against the expected input version.

### 7.3. Atomic output writes

Prevent consumers from reading files still being written by producers. A common pattern:

1. Write output to a temporary name or per-attempt prefix.
2. Flush/close and verify checksum or record count.
3. Write a completion manifest or marker.
4. Publish the official reference using an atomic operation supported by the storage.
5. Consumers read only published outputs.

Object storage typically does not provide atomic renames like a filesystem. You can use a manifest or pointer object updated once uploads finish.

## 8. Scheduling, queues, and concurrency

A workflow can determine which jobs are ready, while the scheduler still decides when to dispatch them and which workers receive them.

### 8.1. Ready queue

Once all mandatory dependencies reach the required state, a job transitions to `Ready` and enters a queue. Workers pick up jobs based on capacity, priority, tenant, resource requirements, and concurrency limits.

Do not dispatch jobs before checking dependencies. Workers should not have to poll predecessor jobs themselves if the orchestrator can determine readiness.

### 8.2. Concurrency limits

Limits can be enforced at multiple levels:

- Across an entire workflow.
- Per job type.
- Per tenant or customer.
- Per queue.
- Per worker pool.
- Per database/API dependency.
- Per zone or node pool.

For example, you might allow up to 20 partitions to run concurrently while allowing only 5 jobs to query the database at the same time. That keeps CPUs busy without overloading the database.

### 8.3. Backpressure

Backpressure slows down producers or throttles dispatch when consumers/dependencies cannot keep up.

Signals:

- Queue depth growing continuously.
- Rising queue age or wait time.
- Worker utilization near 100%.
- Database connection pool exhaustion.
- Dependency APIs returning 429 or 503.
- Increasing error/retry rates.

Measures:

- Cap the number of concurrently running jobs.
- Throttle enqueue rate.
- Use token buckets or rate limiters.
- Separate queues by workload or priority.
- Reduce batch size, or scale workers if dependencies have spare capacity.
- Pause non-essential branches.

Adding workers does not always clear a backlog. If the bottleneck is a database or external API, adding workers can accelerate errors.

### 8.4. Fairness and priority

One tenant can submit a flood of jobs and starve all workers. Use separate queues, weighted fair scheduling, quotas, or priority classes so critical workloads are not starved.

Priorities need bounds. If every job is marked highest priority, prioritization loses meaning.

## 9. Retries, timeouts, and error handling in workflows

Each task needs appropriate timeout and retry policies. Retries do not replace a dependency graph; they only govern how a failed task is retried.

### 9.1. Error classification

- **Transient:** temporary errors such as network timeouts, throttling, or service unavailable; safe to retry.
- **Permanent:** bad inputs, invalid schemas, permission denied, or business rule failures; generally should not auto-retry.
- **Resource/capacity:** insufficient CPU, memory, quotas, or workers; wait, scale, or switch pools.
- **Dependency:** database, queue, or API unavailable; apply timeouts, circuit breakers, and bounded retries.
- **Unknown:** unclassified; preserve evidence and apply conservative policies.

### 9.2. Retry policies

A policy usually includes:

- Maximum attempt count.
- Per-attempt timeout.
- Backoff between attempts.
- Jitter to avoid synchronized retries across jobs.
- Overall task/workflow deadline.
- Which errors are retryable vs. fatal.
- Dead-letter handling or manual intervention once retries are exhausted.

Exponential backoff can use growing wait intervals: 1 second, 2 seconds, 4 seconds, 8 seconds... Random jitter reduces thundering-herd retries. Cap both backoff and total retry duration.

### 9.3. Layered timeouts

Define separate timeouts for:

- Queue wait time.
- Worker startup/provisioning.
- Job execution.
- Network requests to dependencies.
- Lock acquisition.
- Workflow deadline.

A dependency request timeout should usually be shorter than the job's remaining time. If a job has 5 seconds left before its deadline while each API call has a 30-second timeout, the policy is misaligned.

### 9.4. Idempotency and duplicate handling

Queues and workers typically provide at-least-once semantics: the same message may be delivered multiple times when an ack is lost or a worker crashes after writing data.

Jobs must be idempotent or use deduplication:

- Use idempotency keys scoped by workflow/run/partition.
- Persist result status in the same transaction whenever possible.
- Use unique constraints or conditional writes.
- Track attempt IDs separately while keeping logical job IDs stable.
- Only ack messages after results are durably persisted.

End-to-end exactly-once is rarely a simple toggle flag. You can achieve near-exactly-once behavior through idempotency, transaction boundaries, and deduplication, while clearly defining the scope.

### 9.5. Dead-lettering and manual recovery

When retries are exhausted, jobs can move to a dead-letter queue or an intervention-required state. The record should retain:

- Job/workflow ID.
- Input reference and version.
- Attempt count.
- Error class and message scrubbed of sensitive data.
- Timestamps.
- Worker/image version.
- Trace/correlation ID.

Do not delete dead-letter items immediately after an alert fires. Have a procedure to analyze, fix root causes, replay safely, or mark permanently unrecoverable.

## 10. Cancellation, compensation, and long-running workflows

A workflow can be cancelled by a user, a deadline, or an incident. Cancelling a workflow does not mean every active task halts instantaneously.

### 10.1. Cancellation

The orchestrator should:

- Block dispatching new jobs.
- Send cancellation signals to running workers.
- Allow workers to clean up resources or write checkpoints.
- Reclaim leases after a timeout.
- Record `Cancelled` status and reason.
- Never mark `Succeeded` if only part of the work finished.

Workers must handle cancellation cooperatively; killing a process abruptly can leave partial files, locks, or ambiguous transactions.

### 10.2. Compensation

Some workflows include steps with side effects that cannot be rolled back with a single transaction. When a later step fails, compensating actions are required:

- Cancel created reservations.
- Release held quotas/funds.
- Mark orders as cancelled.
- Delete temporary artifacts.
- Emit compensating events to update downstream systems.

This is the Saga pattern. Compensation does not necessarily restore the exact previous state; it executes a new business action to bring the system into an acceptable state.

### 10.3. Long-running workflows

For workflows spanning hours or days:

- Persist state durably.
- Use timers/events instead of holding workers idle.
- Checkpoint at step boundaries.
- Set deadlines and policies for wait steps.
- Version workflow definitions.
- Handle compatibility when in-flight workflows encounter new versions.
- Support resuming and manual intervention.

## 11. Batch workflow example: daily report processing

A system needs to ingest transaction data, validate it, partition it, aggregate totals, and publish a report. Each run has a run ID keyed by data date.

### 11.1. Dependency graph

~~~mermaid
flowchart TD
    A["Create run + input manifest"] --> B["Download source files"]
    B --> C["Validate schema and checksum"]
    C --> D["Normalize records"]
    D --> E1["Partition 1"]
    D --> E2["Partition 2"]
    D --> E3["Partition 3"]
    E1 --> F["Verify all partitions"]
    E2 --> F
    E3 --> F
    F --> G["Aggregate metrics"]
    G --> H["Business quality checks"]
    H --> I{"Quality passed?"}
    I -- "Yes" --> J["Publish report"]
    I -- "No" --> K["Quarantine + alert"]
    J --> L["Mark run complete"]
    K --> M["Mark run failed / needs review"]
~~~

### 11.2. Orchestration rules

| Step | Start condition | Completion condition |
| --- | --- | --- |
| Create run | Schedule arrives or event received | Run ID and manifest persisted |
| Download | Run created | All source files downloaded and verified |
| Validate | Download succeeded | Schema/checksums valid |
| Normalize | Validate succeeded | Normalized output published |
| Partition | Normalize succeeded | Each partition has output and status |
| Verify | All partitions terminal | Sufficient partitions succeeded per policy |
| Aggregate | Verify passed | Aggregated dataset written |
| Quality check | Aggregate succeeded | Business rules passed |
| Publish | Quality check passed | Report published and versioned |

If a partition encounters a transient error, retry only that partition. Do not rerun the entire workflow if other partitions have already finished and their outputs remain valid.

### 11.3. Orchestration pseudocode

~~~python
def run_daily_report(run_id, manifest):
    source = download_sources(manifest)
    validate_sources(source)
    normalized = normalize(source, run_id)

    partition_refs = split_manifest(normalized)
    results = map_with_limit(
        items=partition_refs,
        max_concurrency=12,
        task=lambda item: process_partition(
            run_id=run_id,
            partition_id=item.id,
            input_ref=item.uri,
            idempotency_key=f"{run_id}:{item.id}",
        ),
    )

    verify_complete_partition_set(results, manifest)
    report = aggregate(results)
    quality_check(report)
    publish_versioned_report(run_id, report)
~~~

This pseudocode illustrates logic, not the API of a specific workflow engine. `map_with_limit` must enforce concurrency limits, persist per-partition state, and retry only errors classified as transient. Data-writing functions must be idempotent or write to per-attempt/versioned output paths.

## 12. Choosing an orchestration tool

The chosen platform should fit the workflow type, compute environment, and operational capabilities.

| Tool/group | Suitable pattern | Considerations |
| --- | --- | --- |
| Apache Airflow | Scheduled DAGs, data pipelines, and batch orchestration | Scheduler/metadata database, worker executors, backfills, and DAG versioning |
| Argo Workflows | Container-native workflows on Kubernetes | Pod lifecycle, artifact repository, RBAC, cluster capacity, and workflow CRDs |
| Temporal | Long-running workflows, stateful orchestration, and durable retries | Workflow code determinism/compatibility, worker deployment, and persistence service |
| AWS Step Functions | Managed state machines and AWS integrations | State transition pricing, service integrations, and service quotas |
| Azure Durable Functions | Durable orchestration for functions/apps on Azure | Replay semantics, function versioning, and storage backend |
| Google Cloud Workflows | Step-by-step service and API orchestration | Connectors, execution limits, and service integrations |
| Queue + custom worker | Simple, event-driven tasks | Must build state tracking, retries, dedupe, visibility, and recovery yourself |

Do not choose a tool based solely on feature count. Evaluate state durability, replay capabilities, scheduling, concurrency, observability, cost, execution limits, and vendor lock-in.

## 13. Security and access control across jobs

Each job should only have the permissions needed for its inputs, outputs, and dependencies.

- Use dedicated workload identities or service accounts for worker pools.
- Grant read permissions only to input prefixes and write permissions only to output prefixes.
- Never embed long-lived access keys in queue payloads or workflow definitions.
- Encrypt data at rest and in transit.
- Control who can create, modify, cancel, or replay workflows.
- Scrub secrets and sensitive data from error messages/logs.
- Audit manual interventions and elevated permissions.
- Restrict worker network egress to required dependencies.

If multiple tenants share a worker pool, isolate data, queues, identities, and resource quotas so one tenant's job cannot access another tenant's outputs.

## 14. Monitoring and operating workflows

Monitor both the overall workflow and individual jobs:

| Category | Metrics or signals |
| --- | --- |
| Workflow | Run count, success/failure rate, duration, age, and missed deadlines |
| Job | Queue wait, execution time, attempt count, timeouts, and status |
| Dependency | Ready job count, blocked job count, and dependency wait time |
| Queue | Depth, oldest message age, redeliveries, and dead-letter count |
| Worker | CPU, memory, concurrency, restarts, OOMs, and utilization |
| Data | Input/output bytes, partition completeness, checksums, and schema errors |
| Dependency service | API latency, 429/5xx responses, DB connections, and throttling |
| Cost | Compute time, storage, transfer, orchestration events, and cost per run |

### 14.1. Correlation IDs

Every workflow run should carry a correlation ID propagated across logs, traces, queue messages, and output manifests. Each job has its own job ID and attempt ID. This enables searching a single run and viewing all branches without stitching logs together by timestamp alone.

### 14.2. Useful alerts

Example alerts:

- Critical workflow did not start within its scheduled window.
- A job remains blocked longer than a threshold.
- Queue age increases continuously.
- Abnormal spike in retry rates.
- Non-zero dead-letter count for a critical pipeline.
- Sustained 429/5xx responses from a dependency.
- Workflow is approaching or breaching its deadline.
- Missing partition outputs or checksum mismatches.

Alerts should specify the workflow ID, job ID, attempt, dependency, and linked runbook. Generic alerts like "job failed" without context increase incident resolution time.

## 15. Optimizing workflow duration and cost

### 15.1. Optimizing the critical path

Measure the duration of each node and identify the longest branch. Optimize jobs on the critical path first, for example:

- Increase partition parallelism.
- Reduce dependency wait times.
- Use compute matched to CPU/RAM/I/O profiles.
- Place workers close to data sources.
- Reduce artifact sizes or serialization frequency.

### 15.2. Choosing batch size

Oversized batches make retries costly and tie up worker resources longer. Undersized batches generate excessive jobs, queue messages, orchestration transitions, and startup overhead.

Benchmark batch sizes across:

- Average processing time.
- Memory footprint.
- Error rate.
- Retry counts.
- Overall throughput.
- Orchestration cost per unit of data.

### 15.3. Leveraging appropriate compute

- CPU-bound: compute-optimized nodes/VMs.
- Memory-bound: sufficient RAM to prevent disk spill or OOMs.
- I/O-bound: appropriate storage/network throughput and concurrency.
- Bursty workloads: workers scaling by queue depth.
- Interruption-tolerant jobs: consider Spot/Preemptible instances with checkpointing.

Do not scale concurrency past database or API capacity. A workflow might finish faster individually while inflating total cost due to throttling, retries, and dependency scaling.

### 15.4. Stopping unneeded jobs

When one branch fails and the workflow can no longer succeed under policy, consider cancelling branches that are no longer useful. Before cancelling, verify whether workers support safe cancellation and cleanup.

## 16. Common design mistakes

- Failing to declare dependencies and letting jobs poll each other's state.
- Creating cyclic DAGs or branches without termination conditions.
- Treating an enqueued job as an already-executed job.
- Unbounded fan-out exhausting workers, quotas, or database connections.
- Fan-in counting only result counts without verifying all required partitions.
- Passing large payloads through queues or workflow state.
- Retrying permanent errors and generating useless load.
- Lacking idempotency, causing duplicates on message redelivery.
- Timing out a job while the worker continues writing outputs.
- Not versioning input/output schemas.
- Not persisting state durably and failing to resume after orchestrator restarts.
- Using one overly broad service account across all jobs.
- Lacking deadlines, leaving workflows waiting indefinitely.
- Lacking dead-letter queues or replay procedures.
- Monitoring only workers while ignoring dependencies and queues.

## 17. Workflow design checklist

**Dependency graph**

- [ ] Each job has clear inputs, outputs, and completion criteria.
- [ ] DAG contains no cycles outside controlled loops.
- [ ] Success/failure/always dependencies are explicitly defined.
- [ ] Fan-out is bounded and fan-in verifies complete results.
- [ ] Conditional branches use structured outputs/status.

**Execution**

- [ ] Queue wait timeouts, execution timeouts, and workflow deadlines are set.
- [ ] Concurrency limits are enforced per workflow, tenant, and dependency.
- [ ] Backpressure, priority, and fairness mechanisms are in place.
- [ ] Jobs implement idempotency or deduplication.
- [ ] Retries apply only to classified errors with backoff/jitter.
- [ ] Cancellation, checkpoints, and compensation exist where needed.

**Data**

- [ ] Input/output schemas and versions are recorded.
- [ ] Large data is passed by reference.
- [ ] Outputs are published only after complete writes and verification.
- [ ] Manifests track partitions, checksums, and input versions.
- [ ] Retention and cleanup are configured.

**Operations**

- [ ] Workflow state is stored durably.
- [ ] Correlation IDs span across all jobs.
- [ ] Dashboards highlight critical paths and blocked jobs.
- [ ] Alerts exist for queue age, retries, timeouts, and missed deadlines.
- [ ] Dead-letter, replay, and manual recovery procedures are documented.
- [ ] Worker identities have least-privilege permissions.
- [ ] Cost per run and cost per completed unit are estimated.

## 18. Safe workflow rollout procedure

1. Define business objectives and workflow data units.
2. Break the pipeline into small jobs with clear inputs/outputs.
3. Draw the DAG and define success/failure/conditional dependencies.
4. Identify parallelizable branches and the critical path.
5. Select the orchestrator, queues, and worker runtime.
6. Set up state store, artifact store, and manifests.
7. Configure timeouts, retries, idempotency, concurrency, and deadlines.
8. Configure identity, network policies, secrets, and auditing.
9. Test with small inputs, deliberate fault injection, and worker restarts.
10. Verify duplicates, partial results, cancellation, and resumption.
11. Measure duration, throughput, queue wait, resource usage, and cost.
12. Roll out gradually, monitor alerts, and tune policies from production data.

## 19. Operational principles

1. **Model dependencies explicitly:** use DAGs or state machines instead of relying on implicit ordering.
2. **Distinguish job state from workflow state:** one job succeeding does not mean the entire workflow is complete.
3. **Run only when dependency conditions are met:** success, failure, always, or conditional rules must be declared.
4. **Use bounded parallelism:** fan-out/fan-in improves throughput but requires concurrency control.
5. **Persist state durably:** orchestrators and workers can restart without losing progress.
6. **Design for idempotency:** message redeliveries or retries must not create duplicate side effects.
7. **Bound time and retries:** every job needs explicit timeouts, deadlines, and error policies.
8. **Enforce backpressure:** protect databases, APIs, and worker pools from cascading load.
9. **Pass artifacts by reference:** use manifests/versions/checksums to guarantee data correctness.
10. **Observe end-to-end:** correlation IDs, queue age, critical paths, and cost per run enable effective operations.

Job dependencies form the backbone of background processing and batch workflows. When dependencies are modeled as a DAG or state machine, the orchestrator can identify ready steps, execute safely in parallel, persist state, and recover from failures. Combining explicit data contracts, idempotency, timeouts, retries, backpressure, and observability enables workflows to process large volumes reliably, scalably, and cost-effectively.
