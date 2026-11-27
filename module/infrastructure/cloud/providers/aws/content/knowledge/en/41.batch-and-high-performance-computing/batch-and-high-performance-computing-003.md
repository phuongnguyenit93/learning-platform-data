# Dependencies, Array Jobs, Retries, and Timeouts for Batch Jobs

## Learning Objectives

After this lesson, you can:

- Explain the lifecycle of an AWS Batch job and distinguish between PENDING, RUNNABLE, STARTING, RUNNING, SUCCEEDED, and FAILED states.
- Design dependency graphs to orchestrate ingest, preprocess, compute, aggregate, and publish steps.
- Choose regular job dependencies, SEQUENTIAL, or N_TO_N for array jobs.
- Split large workloads into array children using AWS_BATCH_JOB_ARRAY_INDEX.
- Configure retry strategies with attempts and evaluateOnExit per error type.
- Design idempotent jobs so retries do not create duplicate data or side effects.
- Choose timeouts based on processing duration, handle SIGTERM, and save checkpoints before a job stops.
- Distinguish AWS Batch retries from AWS Step Functions retry/catch handling.
- Monitor queue backlog, job duration, retries, failures, and queue-blocked events.
- Build a runbook to investigate stuck jobs, repeated retries, timeouts, or failed dependencies.

## 1. What Is an AWS Batch Job?

AWS Batch schedules and runs container workloads on compute environments. A job can be an independent task, a child in an array job, or a node in a multi-node parallel job. A job definition describes the image, command, resources, roles, retry strategy, and timeout; a job queue determines where the job waits; a compute environment supplies capacity to run it.

A batch workload typically consists of multiple steps:

~~~mermaid
flowchart TD
    A["Ingest data"] --> B["Validate / preprocess"]
    B --> C["Split partitions"]
    C --> D["Parallel compute"]
    D --> E["Aggregate results"]
    E --> F["Publish / notify"]
~~~

Dependencies ensure downstream steps run only when upstream steps satisfy completion criteria. Array jobs split a step into many independent parts. Retries re-run a failed attempt. Timeouts prevent an attempt from running forever if hung or exceeding its time budget.

These four mechanisms solve different problems. They must be coordinated alongside queue capacity, idempotency, logging, and business error handling.

## 2. Lifecycle and States of a Batch Job

When SubmitJob is called, a job transitions through these states:

| State | Meaning | What to Check |
|---|---|---|
| SUBMITTED | Job was just submitted and not yet evaluated by the scheduler | Job definition, queue, dependencies |
| PENDING | Job is waiting on dependencies or a resource dependency | Upstream jobs, consumable resources |
| RUNNABLE | No remaining dependencies; ready for the scheduler to allocate a host | Compute environment, capacity, quotas, queue policy |
| STARTING | Host selected; container is initializing | Image pull, init containers, container dependencies |
| RUNNING | Container is executing | Logs, CPU/memory, application progress |
| SUCCEEDED | Container exited with exit code 0 | Results, output manifest, audit |
| FAILED | Exhausted attempts or job was cancelled/terminated/failed | statusReason, attempts, CloudWatch Logs |

~~~mermaid
stateDiagram-v2
    [*] --> SUBMITTED
    SUBMITTED --> PENDING: Dependencies/resources not yet ready
    SUBMITTED --> RUNNABLE: No waiting dependencies
    PENDING --> RUNNABLE: Dependencies satisfied
    RUNNABLE --> STARTING: Scheduler allocates capacity
    STARTING --> RUNNING: Container initialization complete
    RUNNING --> SUCCEEDED: Exit code 0
    RUNNING --> RUNNABLE: Attempt failed and retries remain
    RUNNING --> FAILED: Retries exhausted or non-retryable error
    RUNNABLE --> FAILED: Cancel / terminate / management error
    SUCCEEDED --> [*]
    FAILED --> [*]
~~~

Distinguishing PENDING from RUNNABLE is crucial:

- PENDING typically waits for another job to succeed or a resource dependency.
- RUNNABLE is logically eligible to run, though compute capacity may not yet be available.
- STARTING includes image pull and container initialization time. Batch timeouts start counting when an attempt transitions to RUNNING, excluding STARTING time.

A job staying in RUNNABLE for a long time is not necessarily failing. Inspect statusReason, compute environment, vCPU/memory capacity, service quotas, and queue policy before increasing retries.

## 3. Dependency Graphs and DAGs

A dependency is a relationship between jobs: job B runs only after the jobs B depends on have completed successfully.

Example:

~~~mermaid
flowchart LR
    A["Extract"] --> B["Normalize"]
    B --> C["Partition"]
    C --> D1["Compute shard 0"]
    C --> D2["Compute shard 1"]
    C --> D3["Compute shard N"]
    D1 --> E["Aggregate"]
    D2 --> E
    D3 --> E
    E --> F["Publish"]
~~~

This is a directed acyclic graph (DAG): edges represent ordering, while independent branches can run in parallel.

A job can declare up to 20 dependencies. The scheduler waits for all dependencies to succeed before moving the dependent job from PENDING to RUNNABLE. If any dependency fails, the dependent job automatically transitions to FAILED.

Native Batch dependencies express "run when upstream SUCCEEDED." They do not natively express error-handling branches such as "if extract fails, send an alert, run compensation, or proceed with prior data." For workflows with error branches, conditions, approvals, or loops, use AWS Step Functions or a suitable orchestrator.

## 4. Declaring Dependencies for Regular Jobs

Suppose there are two jobs:

- prepare-dataset produces the input dataset.
- train-model runs only after prepare succeeds.

Submit the first job:

~~~bash
aws batch submit-job \
  --job-name prepare-dataset \
  --job-queue arn:aws:batch:ap-southeast-1:111122223333:job-queue/research-queue \
  --job-definition prepare-dataset:4 \
  --region ap-southeast-1
~~~

Save the returned job ID into depends-on.json:

~~~json
[
  {
    "jobId": "11111111-2222-3333-4444-555555555555"
  }
]
~~~

Submit the dependent job:

~~~bash
aws batch submit-job \
  --job-name train-model \
  --job-queue arn:aws:batch:ap-southeast-1:111122223333:job-queue/research-queue \
  --job-definition train-model:7 \
  --depends-on file://depends-on.json \
  --region ap-southeast-1
~~~

train-model remains PENDING until prepare-dataset becomes SUCCEEDED. If the upstream job exhausts retries and becomes FAILED, the downstream job also becomes FAILED; it does not automatically take an alternate branch.

### 4.1 Multiple Dependencies

A publish step may require both aggregate and validation to succeed:

~~~json
[
  {
    "jobId": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
  },
  {
    "jobId": "11111111-2222-3333-4444-555555555555"
  }
]
~~~

In that case, the job becomes RUNNABLE only after both jobs finish successfully. Keep dependency graphs small, clear, and named after business steps for easier troubleshooting.

## 5. Designing Operable DAGs

A good DAG has these traits:

- Each node performs one task with clear inputs/outputs.
- Each edge represents a genuinely necessary prerequisite.
- Independent branches are allowed to run in parallel.
- A validation step runs before publishing data.
- Failure handling exists when an upstream step fails.
- A correlation ID or workflow ID is carried across all jobs.
- Outputs are written to a staging area scoped by workflow/run ID.
- A final commit/publish step ensures consumers only see complete results.

Avoid creating one monolithic job doing every step when steps can retry, scale, or be observed independently. Conversely, do not split work so finely that container startup and orchestration overhead exceed actual processing time.

Do not use dependencies as a substitute for data validation. A job can exit with code 0 while producing empty output or a broken schema. Downstream steps should check manifests, row counts, checksums, or business invariants before proceeding.

## 6. Array Jobs: Running the Same Job Over Many Data Slices

An array job is a parent job managing multiple child jobs that share a job definition and resource configuration. Each child processes an independent slice of data and can run concurrently across multiple hosts.

- Array size must be from 2 to 10,000.
- The parent job serves as a management handle for the children.
- Child job IDs take the form parent-job-id:index.
- Indices start at 0.
- Containers receive the AWS_BATCH_JOB_ARRAY_INDEX environment variable.
- Timeouts apply to each individual child; parent array jobs do not have timeouts.

For example, a workload processing 500 partitions can be submitted with a single SubmitJob call of array size 500 instead of 500 separate requests.

~~~mermaid
flowchart TD
    P["Array parent: 500 children"] --> C0["Child 0"]
    P --> C1["Child 1"]
    P --> C2["Child 2"]
    P --> CN["Child 499"]
    C0 --> S["S3 result partitions"]
    C1 --> S
    C2 --> S
    CN --> S
~~~

Array size is the number of child jobs created, not a guarantee of simultaneous concurrency. Actual concurrency depends on the queue, compute environment, vCPU/memory, quotas, and scheduling policy.

## 7. Using AWS_BATCH_JOB_ARRAY_INDEX

Each child must identify its slice of data. Use the array index to map to a partition, file, shard, or parameter set.

Shell entrypoint example:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

index="$AWS_BATCH_JOB_ARRAY_INDEX"

python process_partition.py \
  --partition-index "$index" \
  --manifest "s3://research-data/manifests/run-2026-11-20.json"
~~~

Python example:

~~~python
import os

index = int(os.environ["AWS_BATCH_JOB_ARRAY_INDEX"])
manifest_uri = os.environ["INPUT_MANIFEST"]

print(f"Processing partition {index} from {manifest_uri}")
process_partition(manifest_uri=manifest_uri, partition_index=index)
~~~

The manifest should provide a stable mapping from index to input object or partition range. Do not assume filenames are always part-index.csv if data may be repartitioned between runs.

Include the workflow ID, dataset version, and array index in the output path, for example:

~~~text
s3://research-results/run-2026-11-20/partition=0042/
~~~

Each child writes only to its own output partition. The aggregate step verifies all partitions are present before publishing.

## 8. SEQUENTIAL Dependency for Array Jobs

If children must run sequentially by index, declare a dependency with type SEQUENTIAL without specifying a jobId.

Example sequential-dependency.json:

~~~json
[
  {
    "type": "SEQUENTIAL"
  }
]
~~~

Submit the array:

~~~bash
aws batch submit-job \
  --job-name process-sequentially \
  --job-queue research-queue \
  --job-definition process-partition:3 \
  --array-properties size=20 \
  --depends-on file://sequential-dependency.json \
  --region ap-southeast-1
~~~

Execution order will be:

- Child 0 runs first.
- Child 1 waits for child 0 to succeed.
- Child 2 waits for child 1 to succeed.
- Continues until the final child.

SEQUENTIAL is useful when each step updates shared state or requires strict ordering. It removes most parallelism benefits of an array job, so do not use it merely "just to be safe."

## 9. N_TO_N Dependency for Two Array Jobs

N_TO_N is used when one array job is the next stage corresponding 1-to-1 with each child of a previous array job. Child index i in array B waits for child index i in array A to succeed.

~~~mermaid
flowchart LR
    A0["Array A:0"] --> B0["Array B:0"]
    A1["Array A:1"] --> B1["Array B:1"]
    A2["Array A:2"] --> B2["Array B:2"]
    AN["Array A:N"] --> BN["Array B:N"]
~~~

After submitting array A, save its parent job ID. Create n-to-n-dependency.json:

~~~json
[
  {
    "jobId": "PARENT-ARRAY-JOB-ID",
    "type": "N_TO_N"
  }
]
~~~

Submit array B with an array size designed for matching index mapping:

~~~bash
aws batch submit-job \
  --job-name transform-partitions \
  --job-queue research-queue \
  --job-definition transform-partition:2 \
  --array-properties size=100 \
  --depends-on file://n-to-n-dependency.json \
  --region ap-southeast-1
~~~

With N_TO_N, child 42 of array B waits for child 42 of array A. This fits pipelines mapping each partition across multiple stages without waiting for all of array A to finish.

Design index mappings clearly across arrays. If a step must combine all results before running, use an aggregate job depending on the parent array rather than N_TO_N.

## 10. States of Parent and Child Array Jobs

The parent array job is a management entity; it is not a container executing work. The parent can be SUBMITTED, PENDING, FAILED, or SUCCEEDED. The parent often stays PENDING while children transition to RUNNABLE and execute.

Operational rules:

- Cancelling or terminating the parent cancels/terminates all children.
- Cancelling/terminating a single child marks that child FAILED without directly stopping its siblings.
- If any child fails, the parent array job eventually becomes FAILED once all children finish.
- Each child can be inspected via its job ID suffixed with :index.

Do not check only parent status when diagnosing issues. Identify the failed child index, its statusReason, attempt history, and log stream.

## 11. Retry Strategy: Attempt Counts for a Job

Retry strategy enables AWS Batch to automatically re-run a job when an attempt fails. Retryable failures include:

- Container exiting with a non-zero exit code.
- EC2 instance failure or termination.
- AWS service internal error or outage.
- Certain container startup or agent errors depending on evaluateOnExit.

attempts ranges from 1 to 10; this value includes the initial run. The default is 1, meaning no extra retries. When an attempt fails and attempts remain, the job returns to RUNNABLE.

The AWS_BATCH_JOB_ATTEMPT environment variable starts at 1 and increments with each run. It can be used to log attempt numbers or adjust diagnostic verbosity, but never use attempt number as an idempotency key because the same business operation spans multiple attempts.

Jobs that are cancelled/terminated or fail due to an invalid job definition are not retried under standard retry strategies. Job timeouts are also not automatically retried.

## 12. evaluateOnExit: Retrying by Error Type

evaluateOnExit lets you decide RETRY or EXIT based on:

- onExitCode: glob pattern on the exit code.
- onReason: pattern on the container/job reason.
- onStatusReason: pattern on the status reason.

If a rule specifies multiple conditions, all declared conditions in that rule must match for the action to apply. If no rule matches, AWS Batch retries by default while attempts remain. Therefore, add a trailing EXIT rule for remaining errors when you want an explicit policy.

Example strategy:

~~~json
{
  "attempts": 4,
  "evaluateOnExit": [
    {
      "action": "RETRY",
      "onReason": "AGENT"
    },
    {
      "action": "EXIT",
      "onExitCode": "2"
    },
    {
      "action": "EXIT",
      "onReason": "*"
    }
  ]
}
~~~

In this example:

- Agent-related errors may be transient, so retry.
- Exit code 2 represents an input/business validation error, so fail immediately.
- All other errors exit instead of retrying through all attempts.

This is an illustrative policy; define application exit codes and test actual reason/statusReason values. Do not classify every error as retryable, because schema, permission, or parameter errors will not resolve on their own.

## 13. Choosing Which Errors to Retry vs. Exit

| Error Category | Example | Typical Appropriate Action |
|---|---|---|
| Transient infrastructure | Host/agent failure, container start issue | RETRY |
| Transient dependency | API throttling, brief timeout | Bounded retry/backoff in app or orchestrator |
| Invalid input | Missing file, malformed schema, invalid parameter | EXIT |
| Permission | AccessDenied from IAM/bucket policy | EXIT and fix configuration |
| Business rule | Data does not qualify for processing | EXIT or route to exception workflow |
| Out of memory | Memory request too low or leak | Typically EXIT, investigate and raise resources |
| Application bug | Null pointer, logic error | EXIT to avoid repeating the same failure |
| Service outage | Backend temporarily unavailable | Bounded RETRY |

A good retry policy answers three questions:

1. Which errors are likely to resolve themselves?
2. How many retries are worthwhile before cost outweighs benefit?
3. Once retries are exhausted, who receives alerts and what data is needed to investigate?

Never retry unrecoverable errors. Re-running a job with bad parameters 10 times still fails, while consuming queue capacity and delaying other workloads.

## 14. Retries and Idempotency

AWS Batch can re-run a container after an attempt fails. A prior attempt may have written partial data, sent messages, or called APIs before crashing. If the next run repeats those side effects, results can be duplicated.

Idempotent design:

- Use a stable workflowId or businessRunId across retries.
- For array jobs, combine workflowId + arrayIndex to identify the partition.
- Write outputs to a staging path keyed by run ID.
- Use conditional writes, transactions, or idempotency tokens in backends.
- Publish/commit only after validation of the entire workflow succeeds.
- Log the attempt number for diagnostics, but exclude it from business identity.
- Avoid writing directly into aggregate tables if a child can retry after partial commits.

Example stable key:

~~~text
run-2026-11-20:partition-0042
~~~

If attempt 1 writes a file successfully but the container crashes before returning exit code 0, attempt 2 must recognize the existing output and verify its checksum or replace it safely.

## 15. Retries Are Not a Full Backoff Policy

AWS Batch retry strategy controls attempt counts and which errors trigger retries. It does not provide a backoffSeconds field to configure arbitrary exponential backoff.

If a dependency requires a cooldown or scheduled retry:

- Implement retry with backoff/jitter inside the application for short requests.
- Push work onto an SQS delay/retry queue where appropriate.
- Use Step Functions Wait and Retry to pace time between job submissions.
- Use EventBridge to restart workflows on a schedule or condition.

Do not sleep inside a container for hours as a substitute for a scheduler. A sleeping job still occupies compute capacity and can reduce queue throughput.

## 16. Timeout for a Job Attempt

By default, AWS Batch sets no timeout. If unconfigured, a container runs until its process exits.

attemptDurationSeconds defines the maximum duration a single attempt may run:

- Minimum value is 60 seconds.
- Counted from the startedAt timestamp when the attempt enters RUNNING.
- STARTING time, including image pull, is excluded.
- Upon expiration, Batch sends SIGTERM for controlled shutdown.
- If the container is still running after 30 seconds, Batch sends SIGKILL.
- Termination is best-effort; do not expect second-level precision.
- AWS Batch sets no universal maximum timeout, though Fargate jobs should not be expected to run longer than 14 days.

Timeouts are configured in the job definition or SubmitJob. A timeout on SubmitJob overrides the job definition's timeout. Timeout termination fails the job and is not automatically retried.

## 17. Timeouts with Array and Multi-Node Parallel Jobs

| Job Type | Timeout Scope |
|---|---|
| Regular job | Each attempt of the job |
| Array job | Each child job gets the configured timeout; parent array has no timeout |
| Multi-node parallel (MNP) | The entire job, not individual nodes separately |

If an array has 10,000 children and each child has a 1-hour timeout, the parent does not necessarily finish in 1 hour. The parent completes only when all children reach terminal states.

MNP timeouts apply to the entire job group. If one node stops responding, the MPI/NCCL application must handle node failures and coordinate shutdown; do not assume each node has an independent timeout.

## 18. Choosing Timeouts Based on Workload

Do not pick timeouts by choosing an overly broad number for every job. Use runtime history and business objectives.

| Workload | Typical Duration | Illustrative Timeout |
|---|---:|---:|
| Validate a file | 1–3 minutes | 5 minutes |
| Transform a partition | 5–20 minutes | 30 minutes |
| Render a scene | 20–90 minutes | 2 hours |
| Train a model | 2–6 hours | 8 hours |
| Batch reconciliation | 15–45 minutes | 1 hour |

These values are examples, not AWS defaults. Use p95/p99 runtime, input size, and cleanup time to pick timeouts. If a workload handles varied input sizes, separate job queues/job definitions or pass an appropriate timeout override at submission time.

A timeout that is too short causes false failures and wastes compute already consumed. A timeout that is too long lets hung jobs hold capacity and delays incident detection.

## 19. Handling SIGTERM and Checkpointing

Applications should catch SIGTERM to:

1. Stop accepting additional work units.
2. Flush completed data.
3. Write a checkpoint or progress marker.
4. Close files and connections.
5. Log the shutdown state.
6. Exit within the allowed shutdown grace period.

Python example:

~~~python
import signal
import sys

shutdown_requested = False

def handle_sigterm(signum, frame):
    global shutdown_requested
    shutdown_requested = True

signal.signal(signal.SIGTERM, handle_sigterm)

for item in load_work_items():
    if shutdown_requested:
        save_checkpoint()
        flush_outputs()
        sys.exit(143)

    process(item)

flush_outputs()
~~~

In production, save_checkpoint() must write state durably and idempotently. Never store progress only in memory. If work cannot resume, ensure partial outputs are never published and a new run can start safely.

## 20. How Do Retries and Timeouts Interact?

| Scenario | Outcome |
|---|---|
| Application exits non-zero, attempts remain | Can retry per evaluateOnExit |
| Application exits 0 | SUCCEEDED, no retry |
| Timeout expires | Batch terminates attempt, job FAILED, no automatic retry |
| User cancel/terminate | No automatic retry |
| Invalid job definition | No retry |
| Dependency job retries and then succeeds | Downstream proceeds once upstream is SUCCEEDED |
| Dependency job exhausts retries and becomes FAILED | Dependent job automatically becomes FAILED |

If you want a timeout to lead to a controlled retry, you cannot simply set attempts and expect Batch to retry timeouts. Let a workflow orchestrator detect timeout/failure states and decide whether to submit a new job with adjusted resources or timeouts.

Do not create an infinite submission loop from EventBridge when jobs repeatedly time out. Use a retry budget, maximum workflow duration, and a failure route.

## 21. Using AWS Step Functions to Orchestrate Batch

Native Batch dependencies fit simple DAGs. Step Functions fits when workflows require:

- Branching based on outcomes.
- Retries with intervals/backoff.
- Catching errors and running compensation.
- Waiting for approvals or timers.
- Parallel/Map processing and result aggregation.
- Persisting workflow state and tracking execution history.

With the service integration arn:aws:states:::batch:submitJob.sync, Step Functions waits for the Batch job to finish before transitioning to the next state.

Task state example:

~~~json
{
  "RunPreprocess": {
    "Type": "Task",
    "Resource": "arn:aws:states:::batch:submitJob.sync",
    "Parameters": {
      "JobName": "preprocess-dataset",
      "JobQueue": "arn:aws:batch:ap-southeast-1:111122223333:job-queue/research-queue",
      "JobDefinition": "arn:aws:batch:ap-southeast-1:111122223333:job-definition/preprocess:4"
    },
    "Next": "RunCompute"
  }
}
~~~

You can configure Retry and Catch on the Task state. Distinguish clearly between:

- Batch retry: re-runs attempts under the same Batch job ID.
- Step Functions retry: re-invokes the service integration, potentially submitting a new Batch job.
- Application retry: retries an API/request inside the same container.

If all three layers are enabled, total executions can multiply. Calculate the combined retry budget and ensure all side effects are idempotent.

## 22. Array Jobs vs. Step Functions Map

Array jobs fit when many children run the same job definition and differ mainly by input index. Step Functions Map fits when each item needs independent orchestration state, branching, per-item retry/catch, or differently structured inputs.

| Criterion | AWS Batch Array Job | Step Functions Map |
|---|---|---|
| Work units | Same job definition, differentiated by array index | Each item can carry distinct inputs |
| Orchestration | Native Batch scheduler | State machine |
| Dependencies | SEQUENTIAL/N_TO_N | State transitions, Map/Parallel |
| Retries | Per-job/child retry strategy | Per-Task/Map item retry |
| Error branching | Primarily FAILED/SUCCEEDED | Catch, Choice, compensation |
| Tracking | Batch job/child states | Workflow execution and state history |

Both can be combined: Step Functions orchestrates major stages, while each stage submits an array job for embarrassingly parallel work.

## 23. Capacity, Concurrency, and Resource-Aware Scheduling

An array size of 10,000 does not mean the compute environment must run 10,000 containers simultaneously. The scheduler moves jobs to RUNNABLE once dependencies are satisfied, and then allocates hosts only when sufficient vCPUs, memory, GPUs, and capacity are available.

To avoid queue overload:

- Choose vCPU/memory requests close to actual workload needs.
- Set compute environment maximum vCPUs aligned with budget.
- Use multiple queues or fair-share scheduling when workloads have differing priorities.
- Cap array sizes or split into waves if downstream systems cannot handle bursts.
- Use consumable resources/resource-aware scheduling for shared resources such as licenses, GPU slots, or internal quotas.
- Enforce concurrency limits at downstream APIs/databases.
- Monitor the queue head and RUNNABLE reasons.

Resource-aware scheduling factors consumable resources into scheduling decisions under FIFO/fair-share policies across supported compute platforms. It prevents dispatching jobs when required logical resources are not yet available.

## 24. Observability: Batch Metrics in CloudWatch

AWS Batch emits metrics in the AWS/Batch namespace with the JobQueueName dimension. As of 2026-10-06, AWS announced native job state-transition and duration metrics to monitor queue health, failures, and time spent in each state.

| Metric | Meaning | How to Use |
|---|---|---|
| JobsSubmitted | Number of submitted jobs | Monitor incoming volume |
| JobsMovedToPending | Jobs moving to PENDING | Identify dependency/resource waits |
| JobsMovedToRunnable | Jobs moving to RUNNABLE | Monitor readiness/retries |
| JobsMovedToStarting | Jobs moving to STARTING | Measure host allocation rate |
| JobsMovedToRunning | Jobs starting execution | Monitor throughput |
| JobsMovedToSucceeded | Jobs completing successfully | Monitor success rate |
| JobsMovedToFailed | Jobs transitioning to FAILED | Monitor failures |
| JobsRetried | Retried attempts | Detect retry storms |
| JobSubmittedToRunnableDuration | Time from submit to RUNNABLE | Measure dependency wait |
| JobAttemptRunnableToStartingDuration | Time from RUNNABLE to STARTING | Measure capacity wait |
| JobAttemptStartingToRunningDuration | Container initialization time | Measure image pull/init overhead |
| JobAttemptExecutionDuration | Time an attempt spends in RUNNING | Monitor runtime |
| JobAttemptDuration | Attempt time from STARTING to completion | Measure total attempt duration |

Metrics are emitted on an event-driven, best-effort basis; very fast state transitions may occasionally omit datapoints. Use metrics for monitoring and baselining, not as an exact audit ledger or billing reconciliation source.

JobAttemptRunnableToStartingDuration and JobSubmittedToFirstStartingDuration apply to AWS Batch compute jobs. Service jobs have a separate set of metrics centered on the SCHEDULED state. JobsMovedToFailed also includes cancelled or terminated jobs, so cross-check DescribeJobs/EventBridge when analyzing failure rates.

For array jobs, JobsSubmitted is emitted on the parent with a value equal to array size; other state/duration metrics are emitted per child job. Do not add parent and child counts together as if they were two separate job pools.

## 25. EventBridge and Job State Change Events

AWS Batch sends Batch Job State Change events to EventBridge whenever a submitted job changes state. Events can be routed to Lambda, SNS, SQS, or Step Functions to:

- Alert on FAILED jobs.
- Trigger the next step when a job becomes SUCCEEDED.
- Write audit records.
- Generate runtime reports.
- Trigger workflows for failed-data handling.

EventBridge delivery can produce duplicates; consumers should be idempotent by event ID or job ID + state + timestamp. Do not assume an event is always delivered for the initial submission.

Example event pattern for failed jobs:

~~~json
{
  "source": ["aws.batch"],
  "detail-type": ["Batch Job State Change"],
  "detail": {
    "status": ["FAILED"]
  }
}
~~~

Batch Job Queue Blocked events are also emitted when Batch detects a RUNNABLE job at the head of a queue blocking the queue. These events and statusReason in DescribeJobs help distinguish capacity shortages, misconfigurations, and invalid compute environments.

## 26. Logs and Attempt History

By default, Batch job logs are sent to the CloudWatch Logs log group:

~~~text
/aws/batch/job
~~~

The stream name can be retrieved via DescribeJobs; the current format typically combines job definition name, default, and ECS task ID. Do not hardcode stream names when the API returns the exact name.

When investigating a failed job, inspect:

- statusReason.
- attempts[] and each attempt's container exit code.
- startedAt, stoppedAt.
- container.reason.
- logStreamName.
- AWS_BATCH_JOB_ATTEMPT.
- AWS_BATCH_JOB_ARRAY_INDEX if it is an array child.
- Input/output manifests and workflow ID.

Configure appropriate CloudWatch Logs retention. Logs may be retained indefinitely by default if retention is unset; avoid printing sensitive data to stdout/stderr.

## 27. Troubleshooting Dependencies and Array Jobs

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Job stays PENDING too long | Dependency not yet SUCCEEDED | DescribeJobs upstream and check status/attempts |
| Downstream becomes FAILED immediately | A dependency failed | Check upstream job ID and failure cause |
| Array child does not run | Parent/dependency unsatisfied or queue lacks capacity | Check child state and queue metrics |
| Array parent stays PENDING | Children are still processing | Inspect child IDs; parent is not a container |
| One child failure fails the parent | Child exhausted retries or was cancelled | Identify failed index and rerun that partition |
| SEQUENTIAL runs very slowly | Each child waits for the previous child | Use only when strict ordering is truly required |
| N_TO_N child waiting | Corresponding upstream index not yet succeeded | Compare array parent IDs and child indices |
| Array children overwrite output | Shared output path | Separate paths by workflow ID and array index |
| Array creates many jobs but few run concurrently | Low compute capacity or quotas | Check RUNNABLE, vCPU/memory, and CE |
| Cancelling parent stops children | Cascading behavior by design | Cancel parent only when stopping the whole array |

## 28. Troubleshooting Retries and Timeouts

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Job retries up to 10 times | attempts set high or errors always match RETRY | Classify exit codes/reasons and add a catch-all EXIT |
| Job does not retry after cancel | Cancelled/terminated jobs are not retried | Use an orchestrator if a new job must be submitted |
| Job times out and becomes FAILED | Timeout termination does not auto-retry | Adjust timeout or handle retries in Step Functions |
| Job stops at threshold before cleanup finishes | SIGTERM handler did not flush in time | Checkpoint earlier, shut down cleanly, raise timeout |
| Job killed with SIGKILL | Did not exit within 30 seconds after SIGTERM | Shorten cleanup and save progress frequently |
| Retried job creates duplicates | Side effects committed before attempt crashed | Use idempotency keys, staging, and conditional commits |
| Job retries forever on permission error | AccessDenied classified as RETRY | Switch to EXIT and fix IAM/resource policies |
| Job exceeds timeout before running | Confusing STARTING duration with timeout | Batch timeout starts at RUNNING; track start duration separately |
| Fargate job stops near 14 days | Fargate resource availability limit | Split workload into shorter checkpointable stages |
| Step Functions spawns too many jobs | State machine retries multiply Batch attempts | Calculate total retry budget and enforce idempotency |

## 29. Case Study: Monte Carlo Simulation Pipeline

A research team needs to run 4,000 simulations using the same image and job definition. Each simulation takes a different seed and writes results to S3. After all complete, an aggregate job computes percentiles and publishes a report.

### Design

1. Job prepare-input validates the dataset and creates a manifest containing 4,000 seeds.
2. Array job simulate has size 4,000; each child reads the seed at AWS_BATCH_JOB_ARRAY_INDEX.
3. Each child writes to an output path scoped by runId/index.
4. Job aggregate depends on the array parent and runs only when the array succeeds.
5. Job publish depends on aggregate and validation.

~~~mermaid
flowchart TD
    A["prepare-input"] --> B["simulate array: 4,000 children"]
    B --> C["aggregate"]
    C --> D["validate report"]
    D --> E["publish"]
~~~

### Retries and Timeouts

- Simulation attempts have a 45-minute timeout based on p99 runtime.
- Retry 3 attempts for host/agent failures.
- Input validation errors exit immediately.
- Each child writes checkpoints and verifiable outputs.
- Aggregate verifies all 4,000 partitions exist before computing results.

### Observability

- JobsMovedToPending measures wait time on the prepare dependency.
- JobsMovedToRunnable and JobAttemptRunnableToStartingDuration show capacity wait.
- JobsRetried detects transient infrastructure errors.
- JobAttemptExecutionDuration identifies seeds with anomalous runtimes.
- EventBridge reports FAILED children so specific indices can be investigated.

### Takeaways

Array jobs submit large workloads in a single call. However, results are reliable only when each child has stable input/output mapping, idempotent retries, and an aggregate step that verifies completeness before publishing.

## 30. Lab: Dependencies, Arrays, Retries, and Timeouts

This lab uses an AWS sandbox with an existing job queue, compute environment, and permissions for batch:SubmitJob, batch:DescribeJobs, and batch:ListJobs. Do not use a production queue. Replace the queue, Region, and job definition with your provisioned sandbox resources.

### Step 1: Register a Job Definition with Retries and Timeout

Create partition-job.json:

~~~json
{
  "jobDefinitionName": "partition-worker-lab",
  "type": "container",
  "platformCapabilities": ["EC2"],
  "containerProperties": {
    "image": "public.ecr.aws/docker/library/python:3.12",
    "command": [
      "python",
      "-c",
      "import os,time; print('index=',os.getenv('AWS_BATCH_JOB_ARRAY_INDEX')); time.sleep(5)"
    ],
    "resourceRequirements": [
      {
        "type": "VCPU",
        "value": "1"
      },
      {
        "type": "MEMORY",
        "value": "1024"
      }
    ]
  },
  "retryStrategy": {
    "attempts": 3,
    "evaluateOnExit": [
      {
        "action": "RETRY",
        "onReason": "AGENT"
      },
      {
        "action": "EXIT",
        "onReason": "*"
      }
    ]
  },
  "timeout": {
    "attemptDurationSeconds": 300
  }
}
~~~

Register it:

~~~bash
aws batch register-job-definition \
  --cli-input-json file://partition-job.json \
  --region ap-southeast-1
~~~

The image and command are examples. In your sandbox, use an approved pullable image and verify compatibility with the compute platform.

### Step 2: Submit a Single Job

~~~bash
aws batch submit-job \
  --job-name partition-single-lab \
  --job-queue lab-queue \
  --job-definition partition-worker-lab \
  --region ap-southeast-1
~~~

Record the job ID and check status with DescribeJobs.

### Step 3: Submit an Array Job

~~~bash
aws batch submit-job \
  --job-name partition-array-lab \
  --job-queue lab-queue \
  --job-definition partition-worker-lab \
  --array-properties size=10 \
  --region ap-southeast-1
~~~

Inspect the parent job and children. Confirm AWS_BATCH_JOB_ARRAY_INDEX spans 0 through 9.

### Step 4: Test SEQUENTIAL Dependency

Create sequential-dependency.json:

~~~json
[
  {
    "type": "SEQUENTIAL"
  }
]
~~~

Submit another array with --depends-on file://sequential-dependency.json. Observe that each subsequent child index transitions to running only after the previous child succeeds.

### Step 5: Test a Standard Dependency

Submit job A and save its ID. Create depends-on.json containing that job ID and submit job B. Observe B staying PENDING and then transitioning to RUNNABLE once A succeeds.

### Step 6: Observe Retries

Use a test image/script that intentionally exits non-zero on the first run and succeeds on the next. Inspect attempts, AWS_BATCH_JOB_ATTEMPT, and the JobsRetried metric. Do not run failure tests on a production queue.

### Step 7: Observe Timeouts

Use a test job whose command runs longer than a 60-second timeout. Inspect the SIGTERM handler, status reason, and verify that timeout termination is not automatically retried.

### Step 8: Cleanup

Confirm all test jobs have finished. Do not delete shared job queues or compute environments. Only deregister job definition revisions or delete dedicated lab resources if permitted and no jobs still reference them.

## 31. Best Practices

### Dependencies and Orchestration

- Design small DAGs with clear stage names.
- Use native dependencies when only upstream SUCCEEDED is needed.
- Use Step Functions when branching, catch, wait, approvals, or compensation are needed.
- Avoid overly deep dependency chains when stages can be combined.
- Validate outputs before running downstream steps.
- Define failure routes and incident owners.

### Array Jobs

- Use arrays for independent workloads sharing a job definition.
- Keep index-to-input mappings stable.
- Isolate output paths by run ID and array index.
- Size arrays appropriately for queue capacity and downstream limits.
- Use SEQUENTIAL only when ordering is strictly mandatory.
- Use N_TO_N for index-matched stages.
- Monitor child jobs rather than only parent status.

### Retries and Idempotency

- Retry only transient errors by default.
- Use evaluateOnExit to separate RETRY from EXIT.
- Add a catch-all EXIT rule to prevent default retries on unclassified errors.
- Define an overall retry budget across Batch, application, and Step Functions.
- Use a stable idempotency key across all attempts.
- Do not retry permission/schema/business validation errors.
- Provide a failure workflow for jobs exhausting attempts.

### Timeouts and Graceful Shutdown

- Base timeouts on p95/p99 runtime plus cleanup.
- Remember timeouts start at RUNNING, not SUBMITTED/STARTING.
- Catch SIGTERM, checkpoint, and flush outputs.
- Keep shutdown under 30 seconds before SIGKILL.
- Split long jobs into checkpointable stages when needed.
- Do not expect timeout terminations to retry automatically.
- Account for Fargate's practical limits on multi-day workloads.

### Monitoring

- Track queue wait, capacity wait, startup, and execution durations separately.
- Track JobsRetried, JobsMovedToFailed, and JobsMovedToSucceeded.
- Use EventBridge state-change and queue-blocked events.
- Use DescribeJobs for statusReason/attempt history.
- Set CloudWatch Logs retention.
- Do not use best-effort metrics as an audit ledger.
- Reconcile output manifests to verify completeness.

## 32. Practice Questions

1. Which upstream state satisfies a dependency in AWS Batch?
2. What is the maximum number of dependencies a job can declare?
3. If a dependency fails, what state does the dependent job enter?
4. How does PENDING differ from RUNNABLE?
5. Why might a RUNNABLE job still not run?
6. How many children does an array job support?
7. What number does AWS_BATCH_JOB_ARRAY_INDEX start from?
8. Is an array parent a container running work?
9. How does a SEQUENTIAL dependency work?
10. How does an N_TO_N dependency map child jobs?
11. When should SEQUENTIAL not be used?
12. What happens when you cancel a parent array job?
13. What happens when a single child array job fails?
14. What does attempts: 4 mean for maximum runs?
15. What number does AWS_BATCH_JOB_ATTEMPT start from?
16. Which error attributes does evaluateOnExit inspect?
17. What does AWS Batch do if no rule matches?
18. Why include a catch-all EXIT rule?
19. Which failures are not retried under standard retry strategies?
20. Why do retries require idempotency?
21. What is the minimum attemptDurationSeconds?
22. From which state does the timeout clock start?
23. Which signal does AWS Batch send on timeout?
24. How long until an unresponsive container receives SIGKILL?
25. Does timeout termination retry automatically?
26. What practical duration limit applies to Fargate jobs?
27. How do array parent and child timeouts differ?
28. How do AWS Batch retries differ from Step Functions retries?
29. What does batch:submitJob.sync do in Step Functions?
30. Which metric measures wait time from RUNNABLE to STARTING?
31. Which EventBridge event fires when a queue is blocked?
32. Why should best-effort CloudWatch metrics not be used as an exact audit source?

### Answer Key

1. When the upstream job is SUCCEEDED.
2. Up to 20.
3. Automatically transitions to FAILED.
4. PENDING is still waiting on dependencies/resources; RUNNABLE is ready and waiting on the scheduler to allocate capacity.
5. The compute environment lacks vCPU/memory/GPU, quotas, or the queue policy has not allocated a host.
6. From 2 to 10,000.
7. 0.
8. No; the parent is a management handle for its children.
9. Each subsequent child index waits for the preceding child index to succeed.
10. Child i of the downstream array waits for child i of the upstream array.
11. When work is independent and requires parallelism.
12. All children are cancelled/terminated along with the parent.
13. The parent eventually becomes FAILED once children finish.
14. Up to four attempts, including the initial run.
15. 1.
16. Exit code, reason, and status reason.
17. The job is retried if attempts remain.
18. So unclassified errors do not retry by default.
19. Cancelled, terminated, invalid job definitions, and timeout terminations.
20. A previous attempt may have committed side effects before crashing.
21. 60 seconds.
22. When the attempt enters RUNNING.
23. SIGTERM.
24. 30 seconds.
25. No.
26. Do not expect Fargate jobs to run longer than 14 days.
27. The parent array has no timeout; timeouts apply per child.
28. Batch retries attempts within the same job ID; Step Functions retries may submit a new job.
29. The workflow waits for the Batch job to complete before moving to the next state.
30. JobAttemptRunnableToStartingDuration.
31. Batch Job Queue Blocked.
32. Because state-transition metrics are best-effort and may drop datapoints.

## 33. Interview Questions

### Are dependencies the same as queue priority?

No. Dependencies determine whether a job is logically eligible to run. Priority determines scheduling order among eligible jobs under a queue policy.

### Why is a PENDING job not always an error?

It may be waiting on a valid upstream job or a resource dependency. Check the dependency graph and wait time before intervening.

### When should you use an array job instead of submitting many SubmitJob requests?

When many work units share the same job definition and can be distinguished by index/parameters. Arrays reduce submission calls and provide parent/child tracking.

### Why are timeout retries not automatic?

AWS Batch timeout termination is designed to stop overdue attempts without automatically retrying them. If you want to re-run with adjusted timeout/resources, an orchestrator should decide whether to submit a new job.

### How do you prevent retries from producing duplicate outputs?

Use stable run ID + array index, idempotent writes, conditional commits, and staged outputs. Publish only after validation completes.

### Why must you distinguish Batch retries from Step Functions retries?

Batch retries re-run container attempts for the same job. Step Functions Task retries may call SubmitJob again and create a new job ID. Combining both without calculating a retry budget can multiply executions.

### Does the timeout include container image pull time?

No. Timeouts start at RUNNING; image pulling and initialization occur in STARTING. Monitor startup duration separately.

### Does an array parent being FAILED mean every child failed?

No. A single child failure causes the parent to eventually become FAILED once all children finish. Inspect individual child states to see which slices succeeded.

### Are CloudWatch metrics sufficient for auditing job counts?

No. Metrics are best-effort and can miss transition datapoints. Use Batch APIs, durably stored EventBridge events, and output manifests for auditing/reconciliation.

### When should you move a DAG from native dependencies to Step Functions?

When you need result-based branching, Catch/Retry/Wait, human approvals, compensation, Map/Parallel states, or full workflow history.

## 34. Production Checklist

### Dependencies and Workflows

- [ ] DAG has no unnecessary dependencies.
- [ ] Every job has a clear input/output contract.
- [ ] Downstream jobs run only after upstream success.
- [ ] Upstream failure handling branches exist.
- [ ] Outputs are validated before publishing.
- [ ] Workflow/run ID is propagated across all stages.

### Array Jobs

- [ ] Array size is within the 2–10,000 limit.
- [ ] AWS_BATCH_JOB_ARRAY_INDEX maps to inputs.
- [ ] Output paths are isolated by run ID and child index.
- [ ] Concurrency aligns with queue capacity and downstream limits.
- [ ] SEQUENTIAL/N_TO_N semantics are chosen accurately.
- [ ] A mechanism exists to identify and rerun individual failed children.

### Retries and Idempotency

- [ ] attempts reflects the retry budget.
- [ ] evaluateOnExit separates transient errors from permanent ones.
- [ ] An appropriate catch-all rule exists.
- [ ] Cancel/terminate/timeout are not expected to auto-retry.
- [ ] Side effects are idempotent across all attempts.
- [ ] Batch and Step Functions retries do not multiply beyond budget.
- [ ] A failure route exists for jobs exhausting attempts.

### Timeouts and Shutdown

- [ ] Timeout is at least 60 seconds and matches p95/p99 runtime.
- [ ] Timeout is understood to start at RUNNING.
- [ ] Applications catch SIGTERM and save checkpoints.
- [ ] Cleanup completes within the grace period.
- [ ] Fargate durations are designed under practical limits.
- [ ] Array child/MNP timeout semantics are verified.

### Observability and Operations

- [ ] CloudWatch dashboards scoped by JobQueueName.
- [ ] Queue wait, capacity wait, startup, and execution durations tracked.
- [ ] Retries, failures, and timeouts monitored.
- [ ] EventBridge state-change and queue-blocked events have idempotent consumers.
- [ ] Logs have retention policies and contain no secrets.
- [ ] Runbooks cover DescribeJobs, attempts, and statusReason.
- [ ] Output manifests include completeness/checksum validation.
- [ ] Owners and escalation paths exist for failed jobs.

## 35. Official References

- [AWS Batch job dependencies](https://docs.aws.amazon.com/batch/latest/userguide/job_dependencies.html)
- [AWS Batch array jobs](https://docs.aws.amazon.com/batch/latest/userguide/array_jobs.html)
- [Use the array job index to control job differentiation](https://docs.aws.amazon.com/batch/latest/userguide/array_index_example.html)
- [Automated job retries](https://docs.aws.amazon.com/batch/latest/userguide/job_retries.html)
- [EvaluateOnExit API](https://docs.aws.amazon.com/batch/latest/APIReference/API_EvaluateOnExit.html)
- [AWS Batch job timeouts](https://docs.aws.amazon.com/batch/latest/userguide/job_timeouts.html)
- [AWS Batch job states](https://docs.aws.amazon.com/batch/latest/userguide/job_states.html)
- [AWS Batch SubmitJob API](https://docs.aws.amazon.com/batch/latest/APIReference/API_SubmitJob.html)
- [AWS Batch job definition parameters](https://docs.aws.amazon.com/batch/latest/userguide/job_definition_parameters.html)
- [AWS Batch job queue blocked events](https://docs.aws.amazon.com/batch/latest/userguide/batch-job-queue-blocked-events.html)
- [AWS Batch event stream for EventBridge](https://docs.aws.amazon.com/batch/latest/userguide/cloudwatch_event_stream.html)
- [AWS Batch job state change events](https://docs.aws.amazon.com/batch/latest/userguide/batch_job_events.html)
- [AWS Batch CloudWatch metrics](https://docs.aws.amazon.com/batch/latest/userguide/using_cloudwatch_metrics.html)
- [Jobs stuck in RUNNABLE status](https://docs.aws.amazon.com/batch/latest/userguide/job_stuck_in_runnable.html)
- [Resource-aware scheduling](https://docs.aws.amazon.com/batch/latest/userguide/resource-aware-scheduling.html)
- [Run AWS Batch workloads with Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/connect-batch.html)

