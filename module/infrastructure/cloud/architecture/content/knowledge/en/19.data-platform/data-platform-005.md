# Pipeline Orchestration, Dependencies, and Rerunnability

## 1. Why Do Pipelines Need Orchestration?

A data platform typically spans many steps: ingesting data from applications, validating formats, storing raw data, standardizing, joining datasets, computing metrics, updating a warehouse or data lake, and serving reports and machine learning workloads. Each step may run on a different tool. If they are wired together only with independent cron jobs, the system struggles to know which step must run first, whether input data is ready, which task is failing, and whether a step can safely rerun without creating duplicate data.

**Orchestration** coordinates the execution lifecycle of tasks across schedules, events, and dependencies—managing state, retries, timeouts, concurrency, checkpoints, and outcomes. An orchestrator generally does not process data itself; it invokes workers, SQL jobs, containers, functions, notebooks, or managed services and tracks their progress.

A well-orchestrated pipeline answers:

- Which tasks must run, and which tasks depend on which?
- When is data considered ready?
- If a task fails midway, where does execution resume?
- How much parallelism is safe without overloading sources or targets?
- How do we prevent duplicate writes, duplicate publishes, or partially written partitions?
- How do we detect corrupted data even when a technical task exits successfully?
- Who receives alerts, and which runbook restores the pipeline?

In the **CLOUD_ARCHITECTURE** module, pipeline orchestration is an architectural decision shaping the reliability, scalability, security, cost, and operability of the data platform. The scheduler tool is only one piece; the quality of the dependency graph, data contracts, and rerunnability determines whether the pipeline is trustworthy.

### Learning Objectives

After this lesson, you will be able to:

1. Model pipelines as DAGs and declare explicit dependencies.
2. Choose appropriate schedules, event triggers, sensors, schedulers, or workflow engines.
3. Design isolated, idempotent, checkpointed tasks for safe retries.
4. Handle timeouts, retries, backoff, concurrency, backfills, and replays.
5. Manage late-arriving data, cross-pipeline dependencies, and data readiness conditions.
6. Monitor run status, data quality, SLAs, lineage, and cost.
7. Design recovery plans and runbooks for failed pipelines or corrupted runs.

## 2. Pipelines, Tasks, Workflows, and DAGs

- **Pipeline:** an end-to-end data processing chain from source to data product.
- **Task:** a unit of work with inputs, outputs, state, and resource limits.
- **Workflow:** describes the sequence, conditional branches, loops, or state transitions of a process.
- **DAG (Directed Acyclic Graph):** a directed graph with no cycles; edges express dependencies between tasks. DAGs fit pipelines where tasks do not have cyclic mutual dependencies within a single run.
- **Scheduler/orchestrator:** decides when to instantiate runs, which tasks are ready, which workers execute them, and which states are recorded.
- **Worker/executor:** performs the actual task work, such as a container running Spark, a SQL job, or a serverless function.

### 2.1. Example Data DAG

~~~mermaid
flowchart TD
    A["Extract application data"] --> B["Validate source schema"]
    B --> C["Load raw partition"]
    C --> D["Normalize and deduplicate"]
    D --> E["Build curated tables"]
    E --> F["Run data quality checks"]
    F --> G["Publish warehouse model"]
    G --> H["Refresh dashboard"]
    G --> I["Train feature dataset"]
~~~

Refreshing the dashboard and training the feature dataset can run in parallel once the warehouse model completes. If the dashboard only needs curated tables, it does not need to wait on feature training. Unnecessary dependencies increase total runtime and widen the blast radius when an unrelated branch fails.

### 2.2. DAGs Must Represent Real Dependencies

An edge from A to B means B cannot start until A's completion criteria are met. That does not always mean A merely returned exit code 0. For data workflows, completion criteria may include:

- Input partitions are committed/published.
- Manifests record the expected file or batch counts.
- Schema versions are compatible.
- Quality checks pass required thresholds.
- Watermarks confirm sufficient data has arrived up to the target timestamp.
- Upstream runs match the right date, tenant, region, or business period.

If a task only checks whether a file exists while the producer is still uploading it, consumers can read partial data. Use manifests/commit markers or atomic publishing to define data readiness.

## 3. Selecting an Orchestration Tool

No single orchestrator fits every workload. Choose among simple schedulers, managed workflow engines, or dedicated DAG platforms.

| Tool Category | Best Suited For | Trade-offs to Evaluate |
|---|---|---|
| Cron / simple scheduler | A few independent jobs, fixed schedules, minimal dependencies | Hard to manage DAGs, backfills, state, and complex retries |
| DAG orchestrator | Many tasks, dependencies, retries, sensors, backfills | Requires managing schedulers, metadata stores, workers, and upgrades |
| Managed workflow service | Reducing control-plane operational burden | Provider limits on duration, step counts, concurrency, state transitions, and cost |
| Event-driven orchestration | Pipelines triggered when files/messages/events arrive | Must manage duplicates, ordering, event storms, and late data |
| Stream processor | Continuous processing by event/partition/window | Different paradigm from batch DAGs; requires managing checkpoints, state, watermarks, and consumer lag |

Concrete tools include Apache Airflow, managed Airflow, cloud workflow/state machines, or built-in data platform schedulers. Compare options by operator/plugin ecosystem, execution model, secret integration, networking, auditing, SLAs, state exportability, and cost.

**An orchestrator is not a default data processing engine.** At scale, tasks typically launch jobs on specialized compute engines (SQL warehouses, Spark, containers, or managed services), while the orchestrator coordinates and monitors execution.

## 4. Defining Schedules and Triggers

Pipelines can start on a time schedule or upon an event. Your choice impacts freshness, system load, and behavior when upstream feeds lag.

### 4.1. Time-Based Schedules

For example, running an aggregation pipeline daily at 02:00 UTC. Schedules must explicitly define timezones, daylight saving rules where applicable, data intervals, and missed-run behavior.

- **Fixed schedule:** runs at fixed wall-clock times.
- **Interval schedule:** runs at fixed intervals.
- **Data interval:** the data window a run owns, e.g., 00:00 to 01:00.
- **Catchup:** backfilling runs for missed schedule intervals.
- **Misfire behavior:** how delayed runs or scheduler downtime are handled.

Never implicitly assume a run on "the 18th" processes data for the 18th. Pass explicit data interval start/end timestamps or business dates as immutable run parameters.

### 4.2. Event-Based Triggers

Pipelines can trigger when file uploads finish and a manifest commits; CDC watermarks cross a threshold; an upstream pipeline emits a completion event; a queue receives new messages; or an external system sends a webhook.

Event triggers can fire multiple times, out of order, or late. Use event IDs, source identities, object versions, and business partitions to deduplicate and route to the right run.

### 4.3. Sensors and Data Readiness

A sensor waits for a precondition, such as a partition appearing or an upstream run finishing. Polling sensors are simple but can generate excessive requests; deferrable or event-based sensors free up workers when supported by the tool.

Sensors require explicit timeouts, sensible polling intervals with jitter, unambiguous readiness predicates, alerts when data misses SLA, and handling for cases where an event arrived before underlying data committed.

## 5. Managing Intra-Pipeline and Cross-Pipeline Dependencies

### 5.1. Intra-DAG Dependencies

Downstream tasks execute once upstream tasks reach defined completion states. Keep dependencies minimal and express conditional branches explicitly.

~~~python
# Pseudocode: API/DSL varies by orchestrator.
extract >> validate >> load_raw >> transform
transform >> [build_dashboard_model, build_feature_table]
~~~

Not every task needs to depend on the entire DAG. If the dashboard task only needs `daily_sales`, tie it solely to that model's build task rather than waiting on unrelated ML jobs.

### 5.2. Cross-Pipeline Dependencies

Pipeline B may consume outputs from Pipeline A. Three common mechanisms:

1. **Explicit dataset/asset dependency:** A publishes a dataset/asset version; B waits on that asset.
2. **Event/manifest:** A emits an event upon committing output; B receives the event and verifies the manifest.
3. **External task sensor:** B checks A's run status for the matching business partition.

Prefer dependencies tied to data contracts or asset versions. Waiting merely for "Job A succeeded today" is insufficient if A ran on the wrong partition or with incomplete inputs.

### 5.3. Preventing Circular Dependencies

If Pipeline A waits on B while B waits on A, neither can ever execute. Break cycles by splitting into phases, using event handoffs, or redesigning the workflow state machine. DAGs must remain acyclic; cross-pipeline dependencies must be validated globally, not just within individual DAG files.

## 6. Task Design: Small, Clear, and Contract-Bound

A well-designed task defines:

- **Input contract:** input datasets/partitions/schemas/versions or parameters.
- **Output contract:** target path/table, schema, partition, manifest, and publish state.
- **Preconditions:** data and permission prerequisites before execution.
- **Side effects:** where the task writes, which events it emits, which external services it calls.
- **Retry policy:** which errors are retryable and retry bounds.
- **Timeouts/resources:** CPU, memory, disk, worker slots, and deadlines.
- **Observability:** logs, metrics, traces, run IDs, and owners.
- **Idempotency:** whether reruns create corrupt data or duplicate side effects.

Keep tasks granular enough to retry and observe independently, without over-fragmenting into tiny steps that bloat state transitions, scheduling overhead, and complexity. A monolithic transform without checkpoints risks restarting from scratch; conversely, spawning one task per row is unreasonable.

### 6.1. Separating Control Plane and Data Plane

The orchestrator manages control flow: run state, dependencies, schedules, and retries. The data plane handles heavy reads, writes, and computation. Never pass large datasets through the orchestrator's metadata store or XCom/state payloads; pass only references, partition keys, manifests, or object URIs.

This prevents metadata database bloat, scheduler slowdowns, and unintended exposure of credentials or sensitive payloads.

## 7. Retries, Timeouts, and Backoff

Tasks can fail due to network timeouts, rate limits, worker restarts, database failovers, or bad data. Classify failures before retrying.

| Error Category | Examples | Appropriate Behavior |
|---|---|---|
| Transient infrastructure | Timeouts, connection resets, brief 503s | Bounded retries |
| Throttling | API 429s, warehouse concurrency caps | Retry respecting `Retry-After`/backoff, reduce concurrency |
| Data quality / schema | Missing required fields, incompatible schemas | Fail/quarantine or wait for upstream; do not retry infinitely |
| Authorization/configuration | Expired credentials, missing IAM role, wrong bucket | Fail fast, alert owner |
| Deterministic code error | Reproducible exception on identical input | Do not retry repeatedly without fixing code/input |
| Unknown outcome | Request committed remotely but response was lost | Verify operation state/idempotency before re-executing |

### 7.1. Exponential Backoff with Jitter

A standard strategy:

\[
delay_n = \min(maxDelay,\ baseDelay \times 2^n) + jitter
\]

Jitter prevents synchronized retry storms across workers after an outage. Enforce max attempts and max elapsed time; total retry duration must not breach pipeline deadlines or downstream SLAs.

### 7.2. Layered Timeouts

- Task timeout: maximum runtime for a single task.
- Sensor timeout: maximum wait for data readiness.
- API/database timeout: maximum wait for external calls.
- DAG/run deadline: overall pipeline completion budget.
- Queue visibility/lease: duration a message remains locked to a consumer.

Timing out a task does not automatically cancel remote side effects. A task marked failed may have already written data before timing out. Retries must verify operation state, checkpoints, or idempotency.

## 8. Rerunnability: Idempotency as the Foundation

Pipelines rerun due to retries, worker crashes, scheduler restarts, backfills, manual reruns, or event replays. An **idempotent task** ensures running the same input/run multiple times yields identical results without duplicate side effects.

### 8.1. Idempotency Patterns

| Pattern | Implementation | Pitfalls to Avoid |
|---|---|---|
| Deterministic output paths | Write to paths keyed by dataset/partition/run version | Generating new random paths per retry creates duplicates |
| Atomic replace / partition overwrite | Write to staging, then atomically swap/replace partition | Deleting old partitions before new outputs finish |
| Upsert with business keys | Merge using unique keys and conflict rules | Unordered upserts overwriting newer records |
| Processed-event ledger | Record processed event IDs within the target transaction | Marking processed before side effects complete |
| Operation/idempotency keys | Attach a stable key to a command | Minting fresh keys on each retry |
| Manifest/commit markers | Publish dataset only once all files/batches complete | Letting consumers read temporary or partial outputs |

### 8.2. Example Safe Partition Processing

~~~text
1. Determine partition = business_date=2026-11-18.
2. Write outputs to staging/run_id=run-abc.
3. Verify row counts, schemas, checksums, and quality rules.
4. Write manifest with status VERIFIED.
5. Atomically publish partition pointer or commit marker.
6. Consumers read only partitions whose manifest is COMMITTED.
~~~

If a worker crashes at step 2, a rerun cleans up staging for the failed run or resumes from checkpoint. If it crashes after writing the manifest but before reporting success, the task recognizes the committed partition and avoids duplicate publication.

### 8.3. External Side Effects Outside the Database

If a task sends emails, calls partner APIs, or creates tickets, an internal database transaction cannot guard external side effects. Use provider idempotency keys where supported, persist operation references, query remote state before retrying, and run reconciliations. Never treat task failure as proof that a remote action did not happen.

## 9. Checkpoints and Processing Progress

Checkpoints mark completed data ranges or work units so tasks can resume without starting over.

Checkpoints can track source offsets/CDC positions, file/object manifests, partition/date ranges, primary-key ranges, batch sequences, stream processor state, or workflow step tokens.

Tie each checkpoint to an input version and transformation version. If transformation code changes, do not automatically resume mixing old and new outputs unless compatibility is verified.

~~~yaml
run_id: sales-daily-20261118-01
dataset: curated.daily_sales
data_interval_start: "2026-11-17T00:00:00Z"
data_interval_end: "2026-11-18T00:00:00Z"
source_watermark: "cdc-position-00981"
transform_version: "git-sha-abc123"
batches:
  - id: region-01
    rows_read: 120000
    rows_written: 120000
    status: VERIFIED
  - id: region-02
    rows_read: 98000
    rows_written: 98000
    status: VERIFIED
publish_status: COMMITTED
~~~

This manifest is illustrative, not a mandatory schema for any specific orchestrator. Production manifests should record checksums, schema versions, quality metrics, storage references, timestamps, owners, and approvals as needed.

## 10. How Backfill, Replay, and Rerun Differ

| Action | Meaning | Example |
|---|---|---|
| **Retry** | Re-attempting the same task/run after failure | Warehouse API timeout |
| **Rerun** | Re-executing an existing run | Rerunning a business date after worker failure |
| **Backfill** | Creating runs for past unprocessed or stale intervals | Loading 10 missing historical days |
| **Replay** | Re-emitting stored events/messages/changes | Replaying events from a DLQ or stream offset |
| **Reprocess** | Recomputing outputs from historical inputs with new logic/versions | Rebuilding curated models after a transform fix |

Backfills can generate heavy load and disrupt downstream consumers. Enforce concurrency caps, workload priorities, bounded time ranges, transformation versioning, and guards against overwriting newer results.

### 10.1. Data Intervals and Run Identity

A DAG may execute multiple runs for the same business date under different code versions or backfill reasons. Distinguish:

- Logical date/data interval: the data window processed by the run.
- Run ID: the specific execution instance.
- Input snapshot/version: the exact source dataset selected.
- Transform version: the logic applied.
- Backfill reason/actor: why and by whom it was triggered.

Never default to wall-clock start time as the business date; a run starting late past midnight may still belong to the previous day's interval.

### 10.2. Safe Backfill Procedure

1. Identify the date/key range and impacted downstream consumers.
2. Verify source retention and input reproducibility.
3. Test on a single small interval first.
4. Define output versions/paths or atomic partition replacement.
5. Cap concurrency to protect sources and targets.
6. Reconcile outputs before publishing.
7. Update consumer pointers only after partitions pass quality gates.
8. Log the version, reason, and reconciliation results.

## 11. Handling Late-Arriving Data and Watermark Dependencies

Daily batches can receive late events due to offline devices, network delays, or upstream retries. If a pipeline runs at 01:00 covering data up to 00:00, an event from yesterday might arrive at 03:00.

Strategies:

- **Fixed delay:** wait a buffer period after window close before finalizing.
- **Watermark:** define a time/offset threshold where older source data is assumed sufficiently complete.
- **Late-arrival window:** permit updating prior partitions within an allowed lateness window.
- **Correction/restate:** publish a revised partition version when data arrives past SLA.
- **Event-time processing:** bucket data by business event timestamp, not solely ingestion time.

Never treat a watermark as an absolute guarantee that no more late data exists; it is a policy estimate based on source behavior. Specify whether events arriving past the watermark are dropped, routed to corrections, or allowed to revise published outputs.

## 12. Concurrency, Pools, and Resource Limits

Orchestrators can launch many tasks simultaneously. Uncontrolled concurrency can overwhelm databases, source APIs, warehouses, object storage, or compute clusters.

Common controls:

- DAG concurrency: concurrent tasks within a single DAG.
- Global parallelism: total concurrent tasks across the orchestrator.
- Task pools/queues: caps across tasks sharing a dependency or compute class.
- Per-task concurrency: limits on mapped or parallel task instances.
- Warehouse slots/compute quotas: capacity caps at the data engine.
- API rate limits: call limits toward external systems.
- Priorities: favoring pipelines with stricter SLAs.

| Workload | Reference Limit | Rationale |
|---|---:|---|
| Extracting from production DB | 4 workers | Prevents excessive OLTP latency spikes |
| Warehouse transforms | Per slot/warehouse quota | Avoids compute contention |
| Partner API ingestion | 2 concurrent requests per partner | Respects partner rate quotas |
| Historical backfill | 1 low-priority pipeline | Avoids competing with daily SLAs |
| Data quality checks | Max 8 tasks | Balances speed and cost |

These numbers are examples; calibrate through load testing and actual quotas. Use backpressure to slow upstream ingestion when downstreams saturate rather than buffering unbounded queues.

## 13. Data Quality as a Pipeline Gate

Technical task success does not prove data correctness. Embed quality checks directly into the DAG and block publication when critical rules fail.

| Category | Example Rule |
|---|---|
| Schema | Required columns present, compatible data types |
| Completeness | Null ratios, minimum record thresholds |
| Uniqueness | Business keys have no duplicates |
| Validity | Values within valid domains, timestamps within bounds |
| Referential integrity | Child records reference valid parents |
| Reconciliation | Sums/counts match source or control totals |
| Freshness | Latest partition meets SLA age |
| Distribution/anomaly | Volumes, revenue, or error rates stay within normal variance |

Distinguish rule severities:

- **Hard failure:** corrupted data could drive wrong business decisions; block publishing.
- **Soft warning:** minor variance within tolerance; alert and record.
- **Quarantine:** isolate bad records for investigation rather than silently dropping them.

Tie quality gates to datasets/versions, storing results and reasons. When rules change, track which historical partitions require reprocessing.

## 14. Observability: Run State, Data Lineage, and SLAs

Orchestration requires visibility across both the control plane and data plane.

### 14.1. Useful Execution States

- `QUEUED`: run created, awaiting execution.
- `RUNNING`: actively executing.
- `WAITING`: blocked on a dependency or sensor.
- `RETRYING`: scheduled for retry per policy.
- `SUCCEEDED`: task/run satisfied completion criteria.
- `FAILED`: terminal or non-retryable failure.
- `SKIPPED`: bypassed by conditional branching.
- `CANCELLED`: intentionally aborted.
- `UPSTREAM_FAILED`: required dependency failed.
- `TIMED_OUT`: exceeded deadline.
- `COMPENSATING/RECONCILING`: executing compensating/reconciliation steps for side effects where applicable.

Exact state names differ by tool; what matters is consistent semantics and dashboard mappings.

### 14.2. Metrics to Monitor

| Metric | Question |
|---|---|
| DAG success rate | What percentage of runs finish within SLA? |
| Task retry count | Which tasks suffer frequent transient failures? |
| Run duration p50/p95 | Are pipeline runtimes creeping upward? |
| Queue/scheduler delay | Are runs waiting on workers or dependencies? |
| Upstream data age | How old is the newest available source data? |
| Data freshness lag | How delayed is publication relative to source events? |
| Backfill volume | How much historical backlog requires reprocessing? |
| Quality failure/quarantine | Which datasets are failing validation rules? |
| Resource utilization/cost | Are pipelines over-consuming compute? |
| SLA miss count | Is the platform breaching data commitments? |

### 14.3. Data Lineage and Traceability

Every output should trace back to its source dataset, source partition, and source watermark; run ID, task ID, and dependency versions; transformation code/version, configuration, and schema version; quality check results; target asset/table/partition; and triggering/approving user or service identity.

Lineage answers where a table came from, which logic version produced it, and which reports break if a source changes. Never rely solely on task names or raw text logs to reconstruct history.

## 15. Orchestrator Security and Governance

Orchestrators frequently hold read access to sources, write access to warehouses, code execution rights, and secrets. They are a sensitive control plane.

- **Least privilege:** assign each pipeline/task its own identity scoped to required sources/targets; avoid one shared admin credential across all DAGs.
- **Secret management:** retrieve secrets from a secrets manager or workload identity; never hardcode them in DAGs, parameters, or logs.
- **Code review:** DAGs/scripts are executable code; restrict who can modify and deploy them.
- **Network isolation:** workers connect only to required endpoints; use private connectivity to data stores.
- **Artifact integrity:** pin container image/dependency versions, scan packages, and control source repositories.
- **Parameter validation:** never pass unsanitized user inputs into shell commands or SQL queries.
- **Auditing:** log who triggers, retries, clears tasks, backfills, edits schedules, modifies connections/secrets, or changes permissions.
- **Environment separation:** isolate roles, connections, and data scopes across dev/staging/prod.
- **Data minimization:** metadata stores and task logs store only references, avoiding sensitive payloads.

Clearing tasks or rerunning jobs can repeat side effects. Operational actions should follow documented procedures and audit trails rather than being granted broadly to all developers.

## 16. Cost and Operations

Pipeline costs extend well beyond transform compute. Account for orchestrator control planes/workers and metadata databases; compute/warehouses/Spark/containers; temporary storage, staging, manifests, and output versions; data transfer, API calls, and CDC/stream ingestion; retries, backfills, duplicates, and reruns; logs, metrics, traces, lineage, and retention; plus ongoing maintenance of schedulers, plugins, connections, upgrades, and incidents.

Cost controls:

1. Prefer sensors/event-driven triggers over high-frequency polling where feasible.
2. Execute heavy work on dedicated compute engines rather than inside orchestrator workers.
3. Tier priorities; run backfills off-peak with low concurrency.
4. Avoid rerunning the entire pipeline when only one partition/task needs recovery.
5. Cache metadata sensibly and avoid redundant source queries.
6. Expire temporary artifacts via lifecycle rules while keeping required manifests/audits.
7. Track cost per published dataset/partition or per successful business run.

## 17. Case Study: Daily Booking Data Pipeline

**Context:** a booking platform ingests bookings from an OLTP database, payment events from a queue, and partner updates via REST API. Each morning, Business needs a daily revenue dashboard; ML needs a curated feature table. The partner API is occasionally slow, payment events can arrive late, and backfills must never degrade the daily pipeline.

### 17.1. Proposed DAG

~~~mermaid
flowchart TD
    Start["Scheduled daily run / upstream events"] --> Booking["Extract booking snapshot"]
    Start --> Payment["Ingest payment events"]
    Start --> Partner["Fetch partner updates"]
    Booking --> Raw["Commit raw manifests"]
    Payment --> Raw
    Partner --> Raw
    Raw --> Validate["Schema + completeness checks"]
    Validate --> Transform["Normalize and deduplicate"]
    Transform --> Curated["Publish curated partition"]
    Curated --> Finance["Build daily revenue model"]
    Curated --> Feature["Build ML features"]
    Finance --> Quality["Reconcile totals and quality"]
    Feature --> Quality
    Quality --> Publish["Publish versioned datasets"]
    Publish --> Dashboard["Refresh business dashboard"]
~~~

### 17.2. Run Design

- Each daily run uses a fixed data interval aligned with the designated business timezone.
- Booking extraction captures an explicit snapshot/CDC watermark; payment ingestion records event IDs for deduplication.
- Partner API calls enforce rate limits, timeouts, retries/backoff, and checkpoints per partner/page/token.
- Raw partitions publish only once manifests verify all files/batches are complete.
- Quality tasks check schemas, record counts, unique business keys, and payment totals by currency.
- Curated outputs are tagged with the transform version and commit/publish only after passing quality gates.
- Finance dashboards and ML features run in parallel if their dependencies are independent.
- Backfills use a dedicated low-priority queue and low concurrency to avoid starving workers/warehouses.

### 17.3. Failure Handling

| Scenario | Behavior |
|---|---|
| Partner API 429 | Honor `Retry-After`, reduce concurrency, resume from checkpoint |
| Late payment event | Record late event, trigger partition correction/restatement per policy |
| Worker crash after write | Inspect manifest/partition commit state and rerun idempotently |
| Partner schema change | Fail validation/quarantine, alert owner, block invalid publication |
| Finance reconciliation mismatch | Block dashboard publication, classify mismatch, run reconciliation |
| Long-running backfill | Throttle priority/concurrency, protect daily SLA |

### 17.4. Acceptance Criteria

- Dashboard reflects the exact business date and meets freshness SLA.
- Duplicate payments never inflate total revenue.
- Partner pagination checkpoints cleanly without skipping pages.
- Consumers read outputs only after manifests are `COMMITTED`.
- Backfills never cause daily pipelines to miss SLAs.
- Individual partitions can rerun without duplicating outputs.
- All outputs trace via lineage to source watermarks and transform versions.

## 18. Failed Pipeline Runbook

When a pipeline fails, never immediately clear or rerun the entire DAG. Follow a safe runbook:

1. Identify the pipeline, run ID, data interval, failed task, and upstream states.
2. Inspect task logs, error classification, worker health, resource exhaustion, and dependency status.
3. Check whether side effects already occurred: output files, DB writes, API calls, emitted events, or manifests.
4. Inspect checkpoints/manifests to determine which batches are `VERIFIED`/`COMMITTED`.
5. For transient errors, retry with the same operation identity; for data/schema errors, quarantine and fix inputs/code first.
6. If bad data was already published, identify impacted consumers, roll back/flag the version, and issue a formal correction.
7. Rerun the smallest possible task or partition scope.
8. Reconcile outputs and downstream systems before resolving the incident.
9. Document root cause, impact metrics, run IDs, and preventive actions.

Never manually edit the orchestrator's metadata database state just to turn a DAG green. Technical status must reflect real data outcomes.

## 19. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Using isolated cron jobs for complex DAGs | Hidden dependencies and unclear global state | Declare workflow graphs and upstream contracts |
| Triggering as soon as a file appears | Consumers read partially uploaded files | Use manifests/commit markers and readiness predicates |
| Non-idempotent tasks | Retries create duplicates or repeated side effects | Deterministic outputs, upserts, operation keys |
| Retrying every error blindly | Amplifies load and loops on deterministic bugs | Classify transient, permanent, and unknown errors |
| Missing timeouts | Sensors/tasks hang indefinitely | Enforce task, sensor, and run deadlines |
| Passing large data through orchestrator metadata | Metadata DB bloat and scheduler slowdowns | Pass references, paths, partitions, and manifests |
| Unbounded backfill concurrency | Degrades production pipelines | Separate queues, priorities, and resource pools |
| Using wall-clock time instead of business intervals | Wrong date partitions and poor reproducibility | Pass explicit data intervals and timezones |
| Warning-only quality checks that still publish | Dashboards surface corrupted numbers | Enforce hard quality gates on critical invariants |
| Ignoring late-arriving data | Incomplete totals or untracked silent edits | Watermarks, allowed lateness, and correction workflows |
| Assuming task success means valid data | Corrupted outputs get published | Reconciliation and quality validations |
| Clearing an entire DAG when one task fails | Wastes compute and duplicates side effects | Rerun minimal tasks/partitions after inspection |

## 20. Pipeline Orchestration Review Checklist

### DAGs and Dependencies

- [ ] DAG is acyclic; dependencies reflect true data requirements.
- [ ] Every task has clear input/output contracts, owners, and states.
- [ ] Data readiness relies on manifests, watermarks, or upstream asset versions.
- [ ] Cross-pipeline dependencies specify timeouts and clear semantics.
- [ ] Optional/failure branches are explicitly modeled.

### Retries and Rerunnability

- [ ] Tasks define timeouts, retry policies, backoff/jitter, and error classifications.
- [ ] Side effects use idempotency keys or persisted operation state.
- [ ] Checkpoints bind to input versions and transform versions.
- [ ] Reruns, backfills, and replays enforce bounded scope and concurrency.
- [ ] Duplicates, late data, and unknown outcomes are handled explicitly.
- [ ] Outputs use staging/manifests/atomic publishing to prevent partial reads.

### Data Quality and Operations

- [ ] Schema, completeness, uniqueness, validity, reconciliation, and freshness checks are active.
- [ ] Hard failures, quarantines, and warnings have explicit rules and owners.
- [ ] Run IDs, lineage, source watermarks, transform versions, and manifests are recorded.
- [ ] Dashboards track success rates, durations, retries, queue delays, freshness, lag, and quality.
- [ ] SLA misses and quality failures have alerts and runbooks.

### Security and Cost

- [ ] Task identities follow least privilege; secrets come from secure managers.
- [ ] Workers, networks, and environments are properly isolated.
- [ ] Code/DAG deployments undergo review and auditing.
- [ ] Backfills and heavy workloads run in dedicated pools/priorities.
- [ ] Cost per dataset/partition or per successful run is tracked.

## 21. Practice Exercise

**Scenario:** A company has three sources: booking OLTP, a payment event stream, and partner data via REST API. It must produce a daily revenue table by 07:00, an analytics product table by 08:00, and an ML feature table. The partner API has strict rate quotas; payment events arrive up to 2 hours late; historical jobs must support 90-day reruns.

Design the orchestration:

1. Draw the DAG and identify which tasks can run in parallel.
2. Choose scheduled/time triggers or event triggers per source; define business intervals and timezones.
3. Define data readiness and cross-pipeline dependencies.
4. Design checkpoints for REST pagination, CDC offsets, and output partitions.
5. Build retry/backoff/timeout rules per error category.
6. Describe idempotency so retries or reruns never double-count bookings/payments.
7. Define late-arrival windows, watermarks, and corrections for delayed payment events.
8. Design a 90-day backfill with low priority/concurrency and versioned outputs.
9. Place data quality gates before publishing dashboards and feature tables.
10. Specify dashboards, alerts, SLAs, and runbooks when the DAG misses deadlines.

**Self-check hints:** An event entering a queue does not mean a partition is complete. A task returning exit code 0 does not prove data validity. Backfills must never overwrite newer partitions with older logic. Every rerun must record its input snapshot, data interval, transform version, and output commit state.

## 22. Key Takeaways

Orchestration coordinates tasks and dependencies; it does not replace data processing engines, data contracts, or quality assurance. A reliable DAG accurately represents when data is ready, which tasks can parallelize, which failures are retryable, and which outputs have genuinely committed.

Safe rerunnability rests on idempotency, checkpoints, manifests, versioning, and reconciliation. Backfills and replays require clear scope, priority, and concurrency caps; late-arriving data requires watermarks/corrections; operations require lineage, freshness tracking, SLAs, alerts, and runbooks. Good design lets pipelines recover from partial failures without duplicating side effects, publishing incomplete data, or overloading sources and destinations.
