# Large-Scale Batch Jobs and Parallel Processing

## 1. The Architectural Problem: Completing Large Volumes Within Finite Time

A **batch processing** system takes a bounded set of jobs or data, processes it in waves, and produces verifiable outputs. Examples include end-of-day transaction settlement, sales data aggregation, transforming data for analytics warehouses, rendering thousands of videos, rebuilding search indexes, scientific simulations, or generating machine learning features.

As data volume grows from a few gigabytes to terabytes, running a single sequential program on one machine may miss the **deadline/SLA**. A parallel processing architecture splits work into concurrently executable units, distributes them across compute resources, and aggregates results in a controlled manner.

Within **CLOUD_ARCHITECTURE**, this topic is a **reference architecture pattern** moving from business requirements to decisions on **networking, compute, data storage, and deployment**. The goal is not merely running many machines: you must balance **reliability, security, scalability, cost, and operations** under Well-Architected principles.

### How Does Batch Differ from Streaming and Ordinary Background Jobs?

| Processing type | How data arrives and when it completes | Appropriate use cases |
|---|---|---|
| **Scheduled batch** | Runs on a closed dataset hourly/daily/weekly; clear start and end | End-of-day reports, monthly invoicing |
| **On-demand batch** | Triggered when a user or system submits a bounded job | Data exports, image-set conversion, video rendering |
| **Micro-batch** | Collects new data into small batches, running repeatedly | Near-real-time analytics when minute-level latency is acceptable |
| **Continuous streaming** | Processes an unbounded event stream, updating results incrementally | Fraud detection, real-time event monitoring |
| **Single background job** | Runs an asynchronous task; may need only one worker | Sending email, generating a thumbnail for one file |

Batch does not necessarily mean "runs overnight"; it is defined by **batch boundaries, completion states, and how outputs are published**. Parallel processing applies to both batch and streaming. A large batch job can also be triggered by an event rather than cron.

## 2. Translating Business Requirements into Design Targets

Before selecting cloud services, explicitly document workload characteristics:

| Characteristic | Questions to answer | Architectural impact |
|---|---|---|
| **Volume** | How many files/records/GB per run? Peak volume? | Partition count, parallelism, scratch capacity |
| **Time window** | How quickly must it finish? Allowable latency? | Target throughput, quotas, autoscaling |
| **Independence** | Do units share state or wait on each other? | Fan-out/fan-in, DAG, shuffle, synchronization |
| **Resource profile** | CPU-, GPU-, RAM-, disk-I/O-, or network-bound? | Compute family and worker sizing |
| **Data and correctness** | Must results be exact, approximate, or re-runnable? | Partition keys, deduplication, checkpoints, transactions |
| **Security classification** | Personal data, secrets, residency mandates? | IAM, encryption, private networking, ephemeral data handling |
| **Recovery SLA** | If a worker fails, how much lost time is tolerable? | Retries, per-partition recovery, reserve capacity |
| **Economics** | Runs daily/weekly? Max budget forecast? | On-demand compute, idle shutdown, interruptible capacity |
| **Dependencies** | Reading from OLTP, object storage, APIs, or on-prem systems? | Source throttling, hybrid links, processing locality |

For instance, a requirement to **"process 900 GB of logs daily and deliver reports within 90 minutes"** must translate into target read, transform, write, and publish rates. If the data source caps reads at 50 MB/s, adding workers will not bypass the source bottleneck.

### Three Acceptance Criteria to Distinguish

- **Correctness:** zero lost or double-counted records; outputs match business rules and input data versions.
- **Completion time:** measured from when data is **ready** until outputs are **published and usable**, including queue wait, shuffle, retries, and validation.
- **Recoverability:** if workers die or a whole run stalls, the job can rerun from checkpoints/stable inputs producing equivalent results within agreed bounds.

Measuring CPU compute time alone never proves an end-to-end pipeline SLA.

## 3. Reference Architecture Pattern

A common design separates the **control plane** (scheduling, orchestration, state management) from the **data plane** (reading, processing, and writing data):

~~~mermaid
flowchart TB
    T["Schedule / event / API"] --> O["Orchestrator / DAG"]
    O --> M["Build input manifest<br/>run_id, data version, partitions"]
    M --> Q["Task queue / scheduler"]
    Q --> W1["Worker 1"]
    Q --> W2["Worker 2"]
    Q --> WN["Worker N"]
    S[("Object storage / data lake<br/>immutable inputs")] --> W1
    S --> W2
    S --> WN
    W1 --> TMP[("Per-partition staging results")]
    W2 --> TMP
    WN --> TMP
    TMP --> V["Validate / reduce / merge"]
    V --> P[("Official results<br/>analytics table / files / index")]
    O <--> J[("Job state / checkpoints / metadata")]
    W1 -. "metrics / logs" .-> OBS["Observability & alerting"]
    W2 -. "metrics / logs" .-> OBS
    WN -. "metrics / logs" .-> OBS
    O -. "events" .-> OBS
    V --> O
~~~

Each block has a distinct role:

1. **Orchestrator** triggers on schedule/events, coordinates dependencies, records state, and decides when the full batch is complete. This can be a workflow engine, scheduler, or managed orchestration service.
2. **Manifest** "freezes" the input list and partitions for a single run. It records **run_id**, time range, schema/version, data locations, and checksums or reconciliation counts where appropriate.
3. **Queue/scheduler** distributes tasks, caps concurrency, and supports retries. A distributed data engine may include an internal scheduler, eliminating the need for a separate queue.
4. **Workers** are VMs, containers, managed batch jobs, serverless functions, distributed-engine executors, or HPC nodes. Each worker should process an **identifiable unit of work**.
5. **Staging** holds unpublished outputs written by partition and attempt. **Reduce/validation** aggregates, verifies completeness, and only then promotes outputs to ready.
6. **Metadata store** persists run state, attempts, checkpoints, lineage, and output versions; protect and back it up just like business data.
7. **Observability** tracks progress, queue lag, resource usage, errors, partition skew, and per-run cost.

This is a **logical pattern**, not a mandate to deploy seven separate products. Managed Spark may bundle scheduling, workers, and shuffling; container batch services may replace queues with job arrays; a simple two-step DAG may not need a separate metadata database.

## 4. Partitioning Work Is Prerequisite to Parallel Execution

### 4.1. Independence and Partitioning Strategies

Each **partition/shard** should satisfy these invariants:

- Clearly bounded scope: by date, key range, hash, file, or object list.
- Partitions within one run are **non-overlapping** when each input must be processed once.
- The union of partitions covers the entire dataset frozen in the manifest.
- A partition can be uniquely identified and re-run without relying on local state from a failed worker.
- Sized large enough that orchestration overhead does not dominate processing, yet small enough for load balancing.

| Partition by | Benefits | Things to check |
|---|---|---|
| **Time window** (day/hour) | Convenient for incremental runs and backfills | Peak hours create uneven partition sizes |
| **Hash(key)** | Uniform distribution across diverse keys | Keep bucket counts and hash rules fixed within a run |
| **Value range** (ID range) | Optimal when data is sorted by key | Sparse key spaces, hot ranges, and boundary errors |
| **File/object** | Easy fan-out over independent files | Giant files or millions of tiny files skew load |
| **Business key** | Co-locates all records for one entity | "Hot keys" create slow straggler workers |

For example, a ~900 GB source can split into thousands of work units, but **optimal partition sizing must be benchmarked** against read throughput, memory, and transform complexity. Figures like 128–512 MiB/partition are merely common **starting points** for columnar file analytics, not universal rules for every engine.

### 4.2. Parallelism Is Bounded

Distinguish three terms:

- **Task count:** total number of work units.
- **Concurrency:** number of tasks executing at a given instant.
- **Effective parallelism:** available cores/slots and genuinely simultaneous execution capacity.

Having 20,000 tasks does not mean launching 20,000 workers. Conversely, splitting data into only 10 partitions caps speed even with 100 idle workers. The orchestrator must enforce **bounded concurrency** so it does not breach quotas, choke data sources, or overwhelm downstream sinks.

### 4.3. Common Parallel Processing Patterns

| Pattern | How it works | Examples |
|---|---|---|
| **Embarrassingly parallel** | Independent tasks with little or no cross-task communication | Image format conversion, per-video rendering |
| **Fan-out / fan-in** | Spawn many tasks, then wait for all results to aggregate | Multi-file validation, daily rollups |
| **Map / shuffle / reduce** | Local map → group data by key → reduce per key | Counting events per product, large group-bys |
| **Multi-stage DAG** | Steps with dependency ordering; parallel across independent branches | ETL: ingest → clean → join → aggregate |
| **Synchronous parallel simulation** | Processes exchange state frequently at barriers | HPC, physics simulations using MPI |

In **map/shuffle/reduce**, mapping usually parallelizes easily; **shuffling** drives disk I/O, network transfer, and data re-sorting/redistribution. If one key dominates volume, the reducer owning that key becomes a **straggler** holding up the entire batch.

Skew mitigation techniques include salting hot keys (when aggregation semantics allow), local pre-aggregation before shuffling, broadcasting small lookup tables when memory allows, tuning partitioning, or changing join algorithms. Always verify mathematical correctness of reductions after key salting.

## 5. DAGs and Managing Cross-Stage Dependencies

When one task depends on another's output, model the workflow as a **directed acyclic graph (DAG)**:

~~~mermaid
flowchart LR
    A["Freeze manifest"] --> B["Read logs"]
    A --> C["Read product catalog"]
    B --> D["Normalize / drop invalid"]
    C --> E["Validate catalog version"]
    D --> F["Join & aggregate"]
    E --> F
    F --> G["Reconcile results"]
    G --> H["Publish new version"]
    H --> I["Notify completion"]
~~~

A solid DAG specifies **success criteria**, **failure branches**, **timeouts**, and **re-runnability** per step. Never treat "task enqueued" as proof of "task completed."

### Orchestration Options

**Simple fan-out/fan-in:** the orchestrator dispatches manifest tasks and waits for all to succeed, retrying failures. Best when tasks are independent with only a final aggregation step.

**Stateful workflow engine:** suited for multi-step pipelines, conditional branches, approval gates, or cross-system coordination. The orchestrator tracks progress; large datasets stay in object storage/data lakes—**never pass large datasets through workflow payloads**.

**Distributed data engine:** suited for distributed SQL, large joins, shuffles, group-bys, and data-layer checkpointing; the engine handles task scheduling and internal dependencies.

**HPC/job arrays:** suited for scientific or compute-intensive workloads needing high-performance CPU/GPU/interconnects, often with frequent barriers and inter-process communication.

Not every workload fits map/reduce. If tasks mutate a shared data structure, uncontrolled parallelism invites race conditions or consistency errors.

## 6. Choosing Compute and Deployment Models

| Compute option | Suitable for | Trade-offs |
|---|---|---|
| **Serverless functions** | Short, independent tasks with spiky load | Duration, RAM, payload, and concurrency limits; cold starts and quotas |
| **Managed batch/container jobs** | Scheduled waves, longer tasks, or custom libraries | Requires packaging images, managing quotas, timeouts, and scratch space |
| **Kubernetes Jobs** | Teams already operating clusters needing custom scheduling/resources | Requires managing node pools, quotas, images, and cluster health |
| **Managed distributed processing** | Distributed ETL/SQL, large shuffles/group-bys/joins | Startup overhead, memory/shuffle tuning, engine cost |
| **VM pool or HPC scheduler** | Custom binaries, MPI, dedicated CPU/GPU, OS-level control | Operating schedulers, capacity, images, and node recovery |
| **Single sufficiently large machine** | Moderate data, poorly parallelizable tasks, low ops tolerance | Single point of failure, vertical scaling ceiling |

**CPU-bound:** prioritize core performance, right-sized memory, and low contention. **Memory-bound:** inspect per-task peak memory, join/hash-table sizes, and disk spill mechanics. **I/O-bound:** monitor read/write throughput and connection counts; extra cores may not raise throughput. **GPU-bound:** evaluate batch size, GPU memory, accelerator provisioning time, and CPU↔GPU data transfers.

When using elastic compute, enforce **max concurrency** based on budget, quotas, and source/sink capacity. Ephemeral workers should launch from pinned images/versions with health checks, execution deadlines, retry policies, and post-exit resource cleanup.

### Quick Selection Guide

If the job is **independently processing millions of images**: prefer job arrays or queue-driven container workers. If it is **joining and grouping terabytes of data**: consider a distributed data engine with shuffle support. If it is **simulations requiring dense inter-node communication**: look at HPC with low-latency/high-throughput networking. If processing is tiny, steady, and self-contained: a single scheduled job may suffice without building a complex cluster.

## 7. SLA Sizing and Bottleneck Identification

Completion time depends on the **slowest path**: reading data, decoding, transforming, shuffling, writing, validating, and publishing.

For a **900 GB (decimal)** batch needing completion in **90 minutes**, minimum end-to-end data throughput assuming a single pass is:

\[
\text{Minimum throughput}=\frac{900\,000\text{ MB}}{90\times60\text{ s}}\approx166.7\text{ MB/s}.
\]

Suppose benchmarks show one worker processes **20 MB/s** on the same data and transforms. Simple division gives a bare minimum worker count of:

\[
N_{\min}=\left\lceil\frac{166.7}{20}\right\rceil=9.
\]

Factoring **70% usable efficiency** to absorb startup time, skewed tasks, and retries gives an initial estimate of:

\[
N_{\text{estimated}}=\left\lceil\frac{166.7}{20\times0.7}\right\rceil=12.
\]

**12 workers is only a preliminary sizing estimate**, not a guarantee of meeting the SLA. Measure object storage bandwidth, database throughput, write speeds, and sequential step durations too. If source reads cap at 100 MB/s, the pipeline cannot hit 166.7 MB/s by adding workers. Also reserve capacity for backfills and competing batches.

### Amdahl's Law and Scaling Efficiency

Not all work parallelizes. If the sequential fraction is **f** using **P** workers, ideal speedup is bounded by:

\[
S(P)=\frac{1}{f+(1-f)/P}.
\]

For example, with **10% sequential work** and **20 workers**, ideal speedup is only about **6.9x**; doubling workers will not halve runtime. Beyond sequential sections, network transfers, shuffles, contention, and coordination further reduce real-world gains.

### Optimize Before Scaling Blindly

1. **Push filters/projections close to the source:** read only required columns, time ranges, or records.
2. **Avoid redundant reads:** leverage columnar formats, appropriate compression, and bounded caching; avoid every task scanning the entire dataset.
3. **Shrink shuffles:** pre-aggregate locally, choose partition keys wisely, and optimize joins.
4. **Prevent small-file explosions:** compact files to balanced sizes to curb metadata and request overhead.
5. **Cap downstream concurrency:** databases, APIs, and brokers all enforce quotas/connection limits.
6. **Measure stragglers:** inspect per-partition durations rather than averages alone.

Speedup from adding workers typically holds only until hitting a data, resource, or sequentiality limit.

## 8. Data Correctness Under Concurrent Execution

### 8.1. Immutable Inputs and Run Identity

Each run needs an explicit **run_id**, **input snapshot/manifest**, **schema version**, and **data cutoff**. If the file list mutates mid-run, two tasks may read different input versions.

For continuously arriving data, bound runs via time partitions, snapshots, or source offsets/versions. Late data follows an explicit backfill/correction policy rather than silently mixing into already-published batches.

### 8.2. Retries, At-Least-Once, and Idempotency

In distributed systems, a worker may finish writing outputs yet lose connectivity before acknowledging; the scheduler may re-dispatch it. Many queues/workflows therefore provide **at-least-once semantics**, meaning tasks can execute multiple times.

An **idempotent** task with the same input and identity must yield the same final effect even across retries. A common strategy:

- Derive **task_id** from **run_id + partition_id + algorithm version**.
- Write outputs to staging tagged by partition and attempt IDs so two attempts never overwrite each other unpredictably.
- Confirm completion via a **conditional/transactional** status write accepting only one valid outcome.
- Publish steps reference only partitions that have been confirmed and reconciled.
- For external side effects (payments, emails, API writes), use **idempotency keys** at target systems or suitable transactional/reconciliation patterns.

Never claim "exactly once" merely because a queue acknowledges messages. **Exactly-once effect** must be proven end-to-end across reads, writes, commits, retries, and side effects within specific mechanism bounds.

### 8.3. Write to Staging, Then Publish Controlled Outputs

A run state machine might look like:

~~~mermaid
stateDiagram-v2
    [*] --> PLANNED
    PLANNED --> RUNNING
    RUNNING --> VALIDATING: tasks completed
    RUNNING --> RETRYING: retryable error
    RETRYING --> RUNNING
    RUNNING --> FAILED: error limit exceeded
    VALIDATING --> PUBLISHED: checks pass, commit succeeded
    VALIDATING --> FAILED: missing partition or reconciliation mismatch
    PUBLISHED --> [*]
    FAILED --> [*]
~~~

The orchestration pseudocode below illustrates **principles**, not a specific provider's API:

~~~text
manifest = freeze_input(run_id, input_version, partition_plan)

for partition in manifest.partitions:
    enqueue(task_id=(run_id, partition.id), max_attempts=3)

worker(task):
    input = read_only_partition(manifest, task.partition_id)
    output = deterministic_transform(input)
    location = write_unique_staging(run_id, task.partition_id, attempt_id, output)
    checksum = validate_local_output(location)
    commit_partition_once(run_id, task.partition_id, location, checksum)

coordinator(run_id):
    wait_until_all_partitions_committed_or_job_failed()
    check_coverage_counts_checksums_and_business_invariants()
    publish_new_version_atomically_if_supported()
    mark_run_published_only_after_commit_confirmation()
~~~

"Atomically" here requires **an underlying commit mechanism that actually supports it**: database/table-format transactions, compare-and-swap version pointers, or equivalent consistent publication. Never assume multi-object writes or renames in object storage form a transaction. If the destination lacks atomic version swaps, ensure readers only consume versions bearing a **completion marker** that is never created prematurely.

### 8.4. Checkpoints, Retries, and Non-Self-Recoverable Errors

| Error type | Examples | Appropriate response |
|---|---|---|
| **Transient** | Network timeouts, preempted worker, throttling | Bounded retries, exponential backoff + jitter |
| **Local data error** | Malformed row schema, corrupt object | Quarantine / data quality workflow; avoid infinite retries |
| **Global logic bug** | Code crashes across all partitions | Fail fast, stop dispatching tasks, fix code, rerun versioned |
| **Resource exhaustion** | OOM, out of scratch disk, low quotas | Tune partitions/concurrency, right-size memory, enable spill, or raise quotas |
| **Inconsistent results** | Financial totals mismatch, missing partition | Block publication, investigate, rerun failed portions |

**Checkpoints** should be granular enough to limit rework without causing excessive I/O overhead. For multi-hour tasks, save progress safely; for multi-second tasks, retrying the entire task is usually simpler.

## 9. Data, Network, and Security Design

### Organizing Data Storage

Large-scale data pipelines commonly separate **raw/bronze** (source data), **validated/clean** (normalized and checked), and **curated/serving** (consumer-ready). Layer names are conventions; what matters is tracking lineage and version for every result.

For tabular analytics, columnar formats and partition pruning cut I/O. For multimedia or simulations, split tasks by independent unit rather than forcing a tabular model. Large intermediate datasets may need local scratch/ephemeral disks or shuffle services; estimate **peak spill sizes**.

If the source is **OLTP**, avoid letting hundreds of workers scan the production database directly: consider snapshots, read replicas, exporting to object storage, or CDC pipelines, while throttling extraction rates. Evaluate storage load and replica lag/consistency guarantees.

### Networking and Resource Placement

- Place compute near data sources/sinks by region/zone and residency rules; estimate transfer costs **cross-region, cross-zone, Internet, or hybrid**.
- Use private subnets/endpoints or private links where appropriate; block unnecessary public inbound access to workers.
- Verify aggregate bandwidth, concurrent connections, NAT/proxy throughput, DNS, timeouts, and API quotas.
- Never rely on static worker IPs when compute scales dynamically; use service identities or designed connection mechanisms.
- Verify read paths, write paths, and control/metadata paths; one working direction does not guarantee the entire DAG runs.

### Least-Privilege Security

Each worker only needs permissions to **read input partitions, write assigned staging paths, and report status**—not delete or publish official datasets. Use a separate role with commit permissions for the coordinator or publisher. Never embed secrets in container images, public configs, or logs.

Sensitive data requires encryption in transit and at rest, key management, strict access controls, retention policies, and temp-file cleanup. Logs/traces must avoid raw PII payloads. For multi-tenant jobs, isolate via IAM, namespaces, compute resources, and per-tenant quotas. Secure container/image supply chains proportionally to risk.

## 10. Deployment, Observability, and Operations

### Reproducible Deployment Bundles

Every run should record **image digest/code version, configuration, schema version, input version, and partition plan**. This lets you identify the exact code/data version behind any result during audits or debugging.

CI/CD pipelines should test config and schema compatibility, then run tests on representative sample data. Avoid updating images mid-run such that two workers in the same batch execute different logic versions. For major changes, run a new versioned batch and compare outputs before swapping production.

### Metrics Needed on Dashboards

| Group | Metrics/signals | Meaning |
|---|---|---|
| **Progress** | Job duration, completed/remaining tasks, confidence-bounded ETA | Is the deadline at risk? |
| **Orchestration** | Queue depth, queue wait time, retry count, task timeouts | Do scheduler/workers have enough capacity? |
| **Performance** | Read/write MB/s, CPU, RAM, disk spill, network, shuffle size | Which resource is the bottleneck? |
| **Load distribution** | Median/p95/p99 task duration, partition sizes, straggler count | Is there data skew or oversized partitions? |
| **Data quality** | Input/output row counts, duplicates, invalid rows, checksums, late data | Is the batch safe to publish? |
| **Reliability** | Job success rate, checkpoint/restore counts, recovery time | Are SLOs being met? |
| **Cost** | Cost/run, vCPU-hours, GB processed, scratch storage, egress | Are costs spiking abnormally? |

Propagate consistent **run_id** and **task_id** fields across logs, metrics, and traces to drill down from dashboards to individual tasks. When a worker fails, operators must quickly locate its input partition, logs, attempt number, code version, and staging output.

Base alerts on impact: missed job deadlines, sustained multi-partition failures, reconciliation mismatches, or sharp cost spikes. Alerting solely on high CPU creates noise because batch jobs intentionally saturate CPUs for bounded durations.

### Repeatable Operational Management

- **Backfill:** allow rerunning historical windows under a dedicated `run_id`; never merge staging into production outputs before validation.
- **Schema evolution:** govern column additions/type changes/deletions, null/default rules, and downstream compatibility.
- **Data retention:** enforce TTLs to purge staging, logs, and checkpoints once recovery, investigation, and compliance windows lapse.
- **Graceful termination:** on scale-in/node preemption, let tasks checkpoint and release leases; uncommitted tasks retry cleanly.
- **Runbooks:** define on-call ownership, go/no-go metrics, pausing queues, restoring data, rerunning a single partition, and republishing outputs.

## 11. Well-Architected Trade-Offs

| Pillar | Choices that improve it | Trade-offs or risks to evaluate |
|---|---|---|
| **Operational Excellence** | DAGs, pinned images/versions, IaC, runbooks, alerts | Higher initial setup effort; requires maintaining workflows/metadata |
| **Security** | Task-scoped IAM, private networking, encryption, auditing | Granular controls can raise operational complexity |
| **Reliability** | Per-partition retries, checkpoints, multi-zone where appropriate | Adds checkpoint storage, replication cost, and verification time |
| **Performance Efficiency** | Proper partitioning, autoscaling, pre-aggregation, data locality | Scaling workers past a point can increase shuffle/contention |
| **Cost Optimization** | Ephemeral per-run compute, quotas, right-sizing, spot where safe | Interruptible capacity can be reclaimed, raising retries and SLA risk |
| **Sustainability** | Shut down idle capacity, raise work-per-GB efficiency | Measure real impact; cheapest pricing is not always lowest resource use |

Typical tensions:

1. **More workers** can cut wall-clock duration yet raise total cost if shuffle/coordination overhead is high.
2. **Spot/preemptible capacity** saves money yet fits idempotent, checkpointed tasks best; orchestration and final commit steps often need stable capacity.
3. **Persisting every intermediate output** aids debugging and step recovery yet expands storage, retention, and sensitive-data exposure.
4. **Multi-region data placement** adds resilience for some needs yet incurs transfer fees, consistency complexity, and residency risks if uncontrolled.
5. **Frequent micro-batches** lower output latency yet increase startup overhead, metadata churn, small files, and orchestration cost.

Deciding factors are **business SLOs, security boundaries, and TCO**, not maximum theoretical scale on a diagram.

## 12. Real-World Scenario: Processing 900 GB of Retail Logs Nightly

### 12.1. Hypothetical Context

An e-commerce marketplace ingests roughly **900 GB of access logs and product-view events daily** stored as objects in a single region. Business teams need view counts, conversion rates, and top products **within 90 minutes of daily data cutoff**. Data can arrive late, some events duplicate, and the product catalog table is versioned daily.

The figures below are **assumptions for architecture practice**, not specs of a particular cloud service. Design goals:

- **Correctness:** each event counts once by **event_id** within the frozen input set; flag late data for backfill.
- **Performance:** 95% of runs complete within 90 minutes, including validation and publishing (an example SLO needing business sign-off).
- **Reliability:** a single worker crash must not restart the entire pipeline; never publish metrics missing a partition.
- **Security:** user-identifying fields are minimized/anonymized per policy; workers never touch the transactional database directly.
- **Cost:** compute terminates after each run; enforce per-run budgets and spend anomaly alerts.

### 12.2. Proposed Architecture

1. **Freeze input:** a job creates a manifest of Day-D objects and schema version; enforce cutoff and late-data policies.
2. **Fan-out normalization:** each task reads an object/partition group, checks schema, normalizes timestamps, projects needed fields, and writes temp data.
3. **Deduplicate:** partition by `event_id` or equivalent so matching `event_id` records meet cleanly; define deterministic winner rules (e.g., highest version).
4. **Catalog join:** read the Day-D catalog snapshot, using a broadcast join if small enough and memory-tested; otherwise run a distributed join.
5. **Aggregate:** group by day and `product_id`, applying pre-aggregation where valid. For conversion rates, persist **numerators and denominators** separately before dividing to avoid flawed "averages of averages."
6. **Validate:** verify full partition coverage, input/output row counts against filter rules, valid event totals, `event_id` uniqueness, anomaly checks, and historical bounds.
7. **Publish:** write a new versioned output and flip the pointer/commit via platform-supported consistency guarantees; notify dashboards only post-commit.
8. **Backfill and cleanup:** route late events into controlled correction/backfill runs; purge stale staging past retention.

~~~mermaid
flowchart TB
    RAW[("Day-D raw objects")] --> MAN["Manifest + cutoff"]
    DIM[("Catalog version D")] --> JOIN["Join on product_id"]
    MAN --> N["Read / normalize / validate"]
    N --> DUP["Deduplicate by event_id"]
    DUP --> JOIN
    JOIN --> AGG["Aggregate by product_id / day"]
    AGG --> QA["Reconcile and quality checks"]
    QA -- "Pass" --> PUB[("Publish new report table version")]
    QA -- "Fail" --> ERR["Block publish + alert"]
    PUB --> BI["Dashboard / API"]
~~~

### 12.3. Capacity Estimate

Per Section 7, required theoretical throughput is **166.7 MB/s**, yielding **12 workers** assuming **20 MB/s/worker** and **70% usable efficiency**. However, **shuffle, join, validation, and publish** stages consume extra time, so sizing must be calibrated on the real pipeline under peak data; reserve capacity or algorithmic tuning may be needed.

Suppose post-benchmark the team selects **14 workers**, each at an effective rate of **0.25 currency units/hour**, running for **1.5 hours**. The **illustrative compute cost** is:

\[
14\times1.5\times0.25 = 5.25
\]

currency units per run. This is **not TCO**: you must also include orchestration, raw/staging storage, request fees, shuffle/network, logging, cross-zone transfer, retries, and engineering ops. Actual spend also hinges on whether 14 workers reliably meet the deadline.

### 12.4. Pre-Production Testing

| Scenario | How to test | Acceptance criteria |
|---|---|---|
| Peak volume | Replay representative 900 GB dataset with realistic skew | Job meets end-to-end SLO within planned resources |
| Worker preemption | Kill one worker mid-partition | Only uncommitted work retries; zero loss or double-counting |
| Task ACK failure | Simulate staging write succeeding while ACK drops | Retry produces no duplicate outputs |
| Bad schema file | Inject corrupt records into one partition | Quarantined or failed per policy; never silently published |
| Hot key | Generate an anomalously high-volume `product_id` | Measure skew; completes with exact totals preserved |
| Missing partition | Intentionally leave one task unfinished | Coordinator blocks publication and raises alert |
| Late-arriving data | Inject Day-D events past cutoff | Versioned correction/backfill applies cleanly |
| Budget overrun | Spike retries or run concurrent backfills | Quotas/budgets/alerts fire without overloading sources |

Claim "meets SLA" only after real measurements pass targets, including failover and retries. Paper estimates of 12 or 14 workers never replace benchmarks.

## 13. Design Practice Exercise

A company runs three workloads:

**A.** Nightly conversion of 50,000 independent PDFs to images; each takes 5–40 seconds and is retryable. **B.** Aggregating 2 TB of sales data via a heavy join between transactions and catalog tables; results needed before 7:00 AM. **C.** Running a scientific simulation across 64 processes that must exchange state after every computation step.

Answer the following:

1. Pick the primary compute model for **A, B, C**: serverless, batch containers, distributed data engine, VM/HPC, or another option. Justify via **dependencies, resource profile, and deadline**.
2. Design the **manifest, partition key, and idempotency key** for A or B. Show how missing partitions are caught and retry duplicates prevented.
3. Sketch a DAG with **at least four stages** for B; list acceptance gates before publishing.
4. If B runs slowly even after adding workers, which metrics diagnose the bottleneck?
5. Propose one **cost optimization** choice that could raise SLA-miss risk, and how to mitigate that risk.

**Reference guide for comparison:**

- **A:** suits fan-out/fan-in using batch containers or serverless if runtime limits, file sizes, and service quotas permit; each input file gets a deterministic `task_id` and versioned outputs.
- **B:** typically needs a distributed data engine for joins/shuffles; inspect skew, dimension table size, memory, spill, I/O, queue wait, and quotas. Pre-aggregating fields before shuffling can help.
- **C:** favors HPC/VMs with low-latency interconnects for frequent inter-process communication; splitting steps into independent queued tasks usually fails barrier/latency needs.
- Spot/preemptible compute cuts costs for A/B if processing is **idempotent, checkpointed**, and backed by time buffer; avoid putting critical final publish steps on easily reclaimed nodes without fallback.

## 14. Review Checklist for Parallel Batch Architectures

- [ ] **Volume, completion SLA, correctness, recovery, budget**, and clear owners are defined.
- [ ] Inputs are **version-frozen** with complete, non-overlapping partitions.
- [ ] Parallelism model matches task independence, shuffle needs, and inter-task communication.
- [ ] Compute is sized from **end-to-end benchmarks**; concurrency caps and quotas are justified.
- [ ] Retries are bounded; tasks are idempotent; checkpoints are tested where applicable.
- [ ] Staging and publish are strictly separated; results surface only after reconciliation and valid commits.
- [ ] Data layout, networking, IAM, encryption, secrets, and data retention are designed.
- [ ] Logs/metrics/traces correlate by `run_id` and `task_id`; alerts cover missed deadlines, reconciliation errors, and spend.
- [ ] Worker failures, duplicates, skew, missing partitions, and backfills have been rehearsed.
- [ ] Idle resources shut down; TCO covers storage, network, retries, and operations.

**Core principle:** Large-scale batch is not "throw as many workers at it as possible." Sound design begins with **stable inputs, clean work boundaries, measured throughput, and safe publication**—only then do you select cloud infrastructure matching business goals and Well-Architected trade-offs.
