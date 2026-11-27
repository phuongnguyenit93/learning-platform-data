# Using Preemptible Capacity for Fault-Tolerant Workloads

## 1. Low-Cost Compute Comes with a Critical Assumption

Cloud providers typically offer lower-priced compute capacity in exchange for the right to **reclaim/preempt** machines when capacity is needed or service conditions dictate. Common names include **Spot Instances**, **Spot VMs**, **preemptible VMs**, or interruptible capacity. Naming, pricing, reclamation terms, advance notices, and support vary by provider, instance type, region, and time.

The mindset shift required in design is: **a machine can vanish while the workload is still running**. Applications must tolerate interruption, persist necessary state off the machine, detect reclamation signals when provided, and return unfinished work to queues.

In the **CLOUD_ARCHITECTURE** module, compute choices must be evaluated alongside reliability, security, scalability, cost, and operations. Preemptible capacity is a cost-optimization tool for suitable workloads—not a default setting for every workload.

After this lesson, you will be able to:

- Identify workloads suited and unsuited for interruptible capacity.
- Design workflows resilient to worker/VM/container reclamation.
- Handle interruption notices, graceful shutdown, checkpoints, retries, and idempotency.
- Combine preemptible capacity with on-demand/regular capacity to maintain minimum service levels.
- Diversify pools, instance types, zones, and task distribution to reduce capacity-shortage risk.
- Measure actual total cost, completion time, and SLO impact before expanding usage.

## 2. What Is Preemptible Capacity?

With standard on-demand or appropriately reserved compute, customers pay to use resources under the chosen service terms. With **spot/preemptible capacity**, cloud providers offer surplus or reallocatable capacity at a lower price while retaining the right to reclaim it when needed.

The design difference goes beyond price:

| Attribute | Standard / On-Demand Capacity | Preemptible Capacity |
| --- | --- | --- |
| Continuity | Generally steadier per chosen service commitment; still subject to infra faults | Adds proactive reclamation risk under spot terms |
| Pricing | Typically higher | Typically lower; may fluctuate by model/provider |
| Creation availability | Subject to quotas, machine types, zones, and capacity | Desired pool may fail to allocate at request time |
| Reclamation notice | Depends on failure/service type | Some services emit interruption notices or metadata; never assume ample warning in all cases |
| Best fit | Core APIs, stateful services, components needing stable capacity | Batch, workers, rendering, simulation, CI, splittable/retryable data processing |
| Application design | Still requires fault tolerance and HA | Must explicitly design retries, checkpoints, draining, and capacity fallbacks |

**Spot does not mean free or unreliable.** It is a compute purchasing model with different reclamation terms. Savings rates, instance lifespans, and allocation success cannot be treated as constants across regions or instance types.

Some services terminate instances on capacity reclamation; some platforms provide advance warnings, while other terminations happen abruptly or due to failures with no notice. Design so you **never depend on always receiving a warning**.

## 3. Which Workloads Fit?

The deciding factor is **how cheaply lost in-flight progress can be controlled**, not merely whether the workload runs on VMs.

### 3.1. Typically Suitable Workloads

| Workload | Why It Fits | Required Conditions |
| --- | --- | --- |
| File/image/video batch processing | Files can be split into small units and rerun | Persist checkpoints/partial outputs in durable storage |
| Rendering, encoding, simulation | Work splits into independent frames/tasks | Stable task IDs, verifiable outputs, retryable |
| Data processing/ETL | Can run by partition or micro-batch | Consistent offsets/checkpoints and output commits |
| CI builds/tests | Jobs are usually short and can rerun if an agent is reclaimed | Store artifacts/logs off-worker; pipeline supports sensible retries |
| Queue workers | Messages can be redelivered if a worker vanishes | Visibility timeouts/leases, ack after completion, idempotency |
| Interrupt-tolerant distributed training/compute | Can checkpoint model/training state | Worker coordination, frequent enough checkpoints, cluster recovery |
| Ephemeral dev/test | Rebuildable from IaC and sample data | No unique data on VMs; no production dependencies |

### 3.2. Workloads Requiring Caution or Usually Unsuitable

| Workload | Risk | Alternative Design Direction |
| --- | --- | --- |
| Primary databases or self-managed datastores | Reclamation threatens availability, consistency, and recovery | Managed DB/stable compute; if used for replicas or auxiliary tasks, test failover roles |
| Core APIs with strict latency/availability | Many instances in the same pool can be reclaimed or fail to replace in time | Keep stable baseline capacity; optionally add spot for supplemental replicas under control |
| Stateful services storing data only on local disk | Losing a node loses uncommitted/local data | Externalize state; use supported durable storage |
| Long tasks without checkpoints | Losing compute discards all elapsed work | Split tasks, add checkpoints, or use stable capacity |
| Interactive sessions pinned to one VM | Reclamation drops sessions and loses local state | Shared session store, stateless apps, and draining |
| Critical control/coordination systems | Losing a scheduler/leader can disrupt the whole cluster | Isolate control plane/leaders off spot pools; make only workers preemptible |

No table replaces testing. A multi-hour workload can still fit if checkpointing is reliable; a 5-second worker is still unsuitable if its side effects are non-idempotent and cannot be reconciled.

## 4. Reference Architecture: Queue + Preemptible Workers

Suppose BookingCloud adds thumbnail generation and report exporting. When users upload images, the API saves metadata and raw files in object storage, then emits a thumbnail message. Workers run on a spot pool and write outputs to object storage. The API and business database remain on stable capacity.

~~~mermaid
flowchart TB
    User["User"] --> API["Upload/API service<br/>Stable capacity"]
    API --> DB[("Metadata DB")]
    API --> OBJ[("Object storage: raw files")]
    API --> Q["Managed queue"]

    subgraph COMPUTE["Compute worker pool"]
      ON["Stable baseline workers<br/>On-demand baseline"]
      SP["Preemptible workers<br/>Spot / preemptible"]
    end
    Q --> ON
    Q --> SP
    ON --> OBJ
    SP --> OBJ
    ON --> MET["Logs / metrics / traces"]
    SP --> MET
    MON["Autoscaler / scheduler"] --> ON
    MON --> SP
    SP -.->|"Interruption notice if available"| DRAIN["Stop taking new tasks<br/>checkpoint / release lease"]
    DRAIN --> Q
~~~

Key points:

- The API confirms files and metadata only after durable persistence; never rely on worker local disks.
- The queue holds pending work; workers only pull tasks they can process.
- A stable worker baseline ensures forward progress even when spot pools are reclaimed or unavailable.
- Spot workers absorb redistributable load; upon reclamation, tasks return to the queue or are picked up by another worker.
- Object storage and the DB are authoritative sources; workers may stage temporary local outputs but must commit final results safely.

This is a logical diagram. For any given provider, check the exact queue service, autoscaling mechanics, interruption metadata, and IAM permissions.

## 5. Designing Tasks for Safe Re-Execution

A worker can terminate at any moment; even with an interruption notice, the app may not finish every operation in time. Therefore, the processing model must assume **any task can execute multiple times**.

### 5.1. Splitting Work into Independent Units

Instead of handing one worker a 500 GB dataset in a single task, split it into small partitions or objects:

~~~text
Job: generate-report-2026-11
  Task 0001: read partition 0001 -> write result 0001
  Task 0002: read partition 0002 -> write result 0002
  Task 0003: read partition 0003 -> write result 0003
  ...
  Finalize: verify all partitions -> publish report
~~~

If the worker processing task 0002 is reclaimed, the system reruns only that partition rather than restarting the whole job.

Every task should have:

- **Stable task ID:** identifies the same unit of work across retries.
- **Input version/checksum:** verifies which exact version of input data is being processed.
- **Lease/visibility timeout:** tracks which worker temporarily owns the task and when it may be reassigned.
- **Checkpoint:** records progress to durable storage at recoverable milestones.
- **Deterministic output path:** prevents retries from spawning unbounded orphan outputs.
- **Attempt count/deadline:** caps retries and flags persistently failing tasks.

### 5.2. Idempotency and Side Effects

An **idempotent operation** is one whose repeated execution with the same identifier/input produces the same final state as one valid execution. This property is essential when messages/tasks can be redelivered.

For example, a thumbnail worker:

1. Inputs include `task_id`, `source_object_version`, and resize parameters.
2. Writes output to a path derived from task/version, such as `thumbnails/{task_id}/{version}.jpg`.
3. Writes a temporary output and atomically publishes/renames or updates a manifest per storage semantics, avoiding exposing partial files to clients.
4. Persists completion status via an atomic conditional update or transaction.
5. On retry, if valid completed output with matching checksum already exists, succeeds without duplicating side effects.

For billing, email, or external system updates, never rely solely on "received ack." Require downstream-supported idempotency keys, deduplication tables, workflow states, or reconciliation processes. Not every side effect can be made strictly once-only by a queue alone.

### 5.3. Where and How Often to Checkpoint?

Checkpoints store enough state to resume or verify completed work: offsets, partitions, workflow steps, input versions, intermediate outputs, and checksums. Storage can be a durable DB, object storage, or a suitable checkpoint service.

Checkpoint frequency is a trade-off:

- Too frequent increases I/O, cost, and time spent not doing primary work.
- Too infrequent causes a reclamation to discard substantial progress.
- Non-atomic checkpoints relative to outputs can mark tasks done before data is durable, or write outputs while leaving status pending.

A simple heuristic for optimal checkpoint interval weighs failure/reclamation frequency, checkpoint write duration, and tolerable rework duration. Never apply one fixed formula to every workload; measure checkpoint overhead and rework time using representative loads.

### 5.4. Never Keep Sole State on Local Disk

Local SSDs/ephemeral disks are useful for caches or scratch space, but recoverable state must be pushed to durable storage. If network volumes are unavoidable, verify detach/re-attach behavior, durability, throughput, zone affinity, and attach limits when instances are reclaimed.

Design so workers can be rebuilt from image/IaC + config + durable storage. Never keep long-lived credentials, private keys, or unique data files on a spot VM's local disk.

## 6. Handling Interruptions: Notices, Draining, and Returning Tasks

### 6.1. Graceful Interruption Flow

When the platform issues a reclamation warning (if supported), the host agent or orchestration layer should:

1. **Stop accepting new work:** mark the worker unready in the scheduler/queue consumer.
2. **Stop polling messages:** fetch no new tasks; in-flight tasks must finish or release their lease.
3. **Checkpoint if time permits:** persist only confirmed durable checkpoints; never treat an interruption notice as a guarantee of sufficient time.
4. **Commit outputs atomically:** finalize side effects or save retryable intermediate state.
5. **Ack or release:** ack only when the task is complete and outputs are durable; otherwise withhold ack or release/requeue per service mechanics.
6. **Close resources:** flush essential logs/metrics, close connections, and exit promptly.

~~~mermaid
sequenceDiagram
    autonumber
    participant Cloud as Cloud capacity manager
    participant Agent as Worker/agent
    participant Queue as Task queue
    participant Store as Checkpoint/object store
    participant Next as Next worker

    Cloud-->>Agent: Interruption notice (if available)
    Agent->>Agent: Mark not-ready; stop polling
    Agent->>Agent: Stop task at safe point
    opt Sufficient time and valid checkpoint
        Agent->>Store: Write checkpoint/temp output
        Store-->>Agent: Confirm durable write
    end
    alt Task completed safely
        Agent->>Queue: Ack task
    else Task incomplete
        Agent->>Queue: Release lease / do not ack
        Queue-->>Next: Redeliver when lease expires
        Next->>Store: Read valid checkpoint
        Store-->>Next: Resume or rerun
    end
    Cloud->>Agent: Reclaim capacity
~~~

An interruption notice is an **opportunity for an orderly stop**, not a guarantee that the app will always run for a fixed extra duration. Read the documentation for your specific capacity type to learn how, when, and with what limits signals are delivered.

### 6.2. Queue Visibility Timeouts and Leases

If a worker pulls a message from a queue and is then reclaimed:

- When the worker acks after completion, the message is marked processed per queue semantics.
- If the worker dies before acking, the message reappears once the visibility timeout/lease expires.
- If visibility timeout is too short, long tasks get assigned concurrently to another worker while the first is still running.
- If too long, a dead worker stalls task recovery before a replacement picks it up.

For variable-duration tasks, extend visibility/leases via heartbeats if the queue supports them. Heartbeats must reflect that the worker is alive and making progress—never extend leases indefinitely for hung tasks. Workers still need idempotency because leases cannot prevent every duplicate delivery.

### 6.3. Container/Orchestrator Termination Deadlines

If spot VMs serve as nodes in Kubernetes or a container orchestrator, distinguish:

- **VM/underlying node interruption:** the node can vanish; workloads must be rescheduled elsewhere if capacity exists.
- **Pod eviction/drain:** the scheduler/orchestrator may grant Pods a graceful termination window, send stop signals, and run `preStop`/lifecycle hooks per configuration.
- **Application shutdown:** processes must handle `SIGTERM` or equivalent signals, stop taking tasks, and close connections.

Never assume Pod graceful shutdown windows always outlast VM reclamation windows. Use an interruption handler/DaemonSet or platform-managed mechanism (if available), cordon the node from scheduling, drain within a realistic time budget, and remain resilient to hard termination.

## 7. Ensuring Capacity When Spot Pools Are Unavailable

A common mistake is scaling an entire system on spot capacity and being caught off guard when demand spikes right as the provider runs short on pools. Low-cost capacity must never be the **sole prerequisite for minimum system progress**.

### 7.1. Baseline + Burst Model

Maintain steady baseline capacity for minimum throughput, adding spot workers when pools are available:

~~~mermaid
flowchart TB
    Q["Task queue / backlog"]
    AUTO["Scheduler / autoscaler"]
    BASE["Stable baseline<br/>On-demand"]
    SPOT["Elastic workers<br/>Spot capacity"]
    Q --> BASE
    Q --> SPOT
    AUTO --> BASE
    AUTO --> SPOT
    BASE --> DONE["Completed tasks"]
    SPOT --> DONE
    BACK["Spot pool unavailable / reclaimed"] --> AUTO
    AUTO -->|"Shift critical work to stable capacity<br/>or accept backlog per SLO"| BASE
~~~

If backlog grows while spot capacity disappears, the system can:

- Consume remaining baseline headroom.
- Spin up on-demand/regular capacity if quotas and provider inventory allow.
- Shed non-urgent work or throttle concurrency.
- Extend SLAs per business agreement for non-urgent batches.

Define a **minimum progress SLO**: e.g., queue backlog stays under a threshold or batches finish before deadlines. If baseline capacity cannot cover it, explicitly document how workload SLAs degrade when spot is unavailable.

### 7.2. Pool Diversification

Spread workloads across multiple capacity options to reduce reliance on one instance type or pool:

- Multiple instance families/sizes capable of running the same image and app.
- Multiple Availability Zones within latency and data constraints.
- Multiple pools across CPU architectures or accelerators when the workload supports them.
- Multiple node group/launch template types or capacity offerings under consistent security and observability standards.

Diversification must remain compatible with the app. Workloads requiring GPUs or local NVMe have narrower choices—you cannot add an unaccelerated instance pool and count it as equivalent fallback capacity.

**Capacity-optimized allocation** or availability-aware pool selection can reduce the odds of picking constrained pools depending on the provider. Still, diversification does not eliminate simultaneous reclamation when multiple pools face correlated market pressure or zone events.

### 7.3. Avoid Blind Price-Chasing

Do not pick a pool solely because its current spot price is lowest. Balance:

- Likelihood the pool has capacity when needed.
- Interruption rate and its impact on task progress.
- Price-performance per completed unit of work.
- Rework, checkpoint, retry, and orchestration overhead.
- On-demand fallback and headroom costs.

A cheap hourly rate does not guarantee a low **cost per successful outcome**. A frequently reclaimed pool causing repeated reruns can cost more than a pricier pool that completes tasks reliably.

## 8. Autoscaling and Queue Management

### 8.1. Scaling on Real Demand

For asynchronous workers, CPU is rarely the best scaling signal. Scale using:

- Queued message count (backlog).
- Age of the oldest message.
- Message arrival rate vs. processing rate.
- In-flight task count and average processing time.
- Batch completion targets and deadlines.
- Actual available capacity in each pool.

A rough rule of thumb:

`Required workers ≈ backlog / (target throughput per worker × allowed backlog drain time)`

This is only an initial estimate; factor in variable task durations, startup overhead, concurrency caps, retries, and quotas. Scaling on a single backlog snapshot while ignoring arrival rate causes under- or over-scaling.

### 8.2. Decoupling Retry Logic from Autoscaling

If tasks fail due to poison data or bugs, scaling up workers only multiplies failures. Classify errors:

| Error Type | Response |
| --- | --- |
| Worker reclaimed | Return retryable task to queue/lease; resume from checkpoint |
| Transient infra failure | Retry with backoff, jitter, and attempt caps |
| Dependency throttling | Lower concurrency, apply backpressure, honor service retry headers |
| Invalid input / deterministic bug | Route to DLQ or failed state for investigation; never retry endlessly |
| Runaway long task | Check heartbeat/lease, cap runtime, checkpoint, or split smaller |
| Pool out of capacity | Trigger fallback, keep backlog within SLO bounds, emit alert |

DLQs require owners, retention, dashboards, and replay workflows after root causes are fixed. Never bulk-replay messages if doing so triggers duplicate side effects on external systems.

## 9. Security for Preemptible Compute

Ephemeral machines do not reduce data-protection obligations. Workers may handle customer files, tokens, analytics datasets, or secrets.

### 9.1. Identity and Least Privilege

- Grant each worker/service role only the permissions needed to read inputs, write outputs/checkpoints, consume messages, or update status.
- Use platform-native short-lived workload identities/roles whenever possible; never bake static access keys into images, user data, or scripts.
- Separate permissions for schedulers, node bootstrapping, workers, and human operators.
- Audit sensitive actions and restrict who can replay DLQs.

### 9.2. Data and Disks

- Encrypt data in transit to queues, object storage, databases, and dependencies.
- Use appropriate encryption at rest and key management; verify worker permissions to access keys.
- Never store sensitive data solely on ephemeral disks.
- On normal exit, purge temporary data per policy; never rely on local cleanup alone since disks can vanish abruptly.
- Protect checkpoints/outputs against tampering or cross-task/cross-tenant mixing; use namespaced paths/keys and enforce authorization.

### 9.3. Supply Chain and Bootstrapping

Workers are typically provisioned automatically from images. Images need trusted sources, patches, vulnerability scans, artifact signing/verification where supported, and zero embedded secrets. Review IaC and launch templates like code; using spot capacity is no excuse to skip production controls.

## 10. Cost Efficiency: Measuring per Completed Unit of Work

To compare stable vs. spot capacity, measure **cost per successful work unit** rather than hourly instance price alone.

An analytical formula:

~~~text
Total workload cost
  = compute cost
  + storage/checkpoint cost
  + network/egress cost
  + queue/observability cost
  + rework cost from interruptions
  + on-demand fallback cost

Cost per successful task
  = total workload cost / valid completed tasks
~~~

Hypothetical example for a 10,000-task batch:

| Line Item | Stable Capacity Option | Spot-First Option |
| --- | ---: | ---: |
| Primary compute | 100 cost units | 55 |
| Retries/checkpoints/storage | 3 | 9 |
| Fallback capacity | 0 | 12 |
| Added observability/orchestration | 2 | 5 |
| **Total** | **105** | **81** |
| Successful tasks | 10,000 | 10,000 |
| **Cost/successful task** | **0.0105** | **0.0081** |

These numbers only illustrate the calculation method. In practice, compare identical work, equal completion rates, and identical deadlines, including operational effort. If spot-first only finishes 8,000 tasks on time, it cannot be declared cheaper while ignoring 2,000 late tasks.

Metrics to collect:

- Spot interruption rate, reclamation counts, and reasons if exposed by the provider.
- Time from notice to node termination; drain/checkpoint success rates.
- Task retries, duplicates, failures, and rework time.
- Backlog/age, p50/p95/p99 completion times, and deadline attainment rate.
- Spot vs. on-demand ratio, fallback duration, quota/capacity errors.
- Compute, storage, data transfer, logging costs, and cost per successful task.

## 11. Well-Architected Evaluation

| Perspective | Questions When Introducing Spot | Required Evidence |
| --- | --- | --- |
| **Operational Excellence** | When a worker is reclaimed, where do alerts go, how are tasks returned, and who handles DLQs? | Runbooks, interruption handlers, dashboards, chaos test results |
| **Security** | What secrets/data do workers touch, what permissions do they hold, and how are images managed? | Least-privilege IAM, image scanning, auditing, encryption, permission tests |
| **Reliability** | If a pool runs dry or suffers mass reclamation, does the workload keep progressing? | Baseline capacity, fallbacks, retry/checkpoint tests, deadlines/SLOs |
| **Performance Efficiency** | Do throughput and task latency hold when pools switch instance types or scale? | Load tests across instance mixes, backlog, p95 processing time, saturation |
| **Cost Optimization** | Does cost per completed task drop after factoring interruptions and fallbacks? | Billing + work-unit metrics, retry overhead, egress, storage |
| **Sustainability** | Are idle compute and redundant reruns minimized? | Utilization, checkpoint overhead, duplicate work, resource lifecycles |

Never label a workload "spot-ready" simply because hourly compute rates are lower. Prove the system withstands **disruption of the compute pool itself** while meeting business goals.

## 12. Practical Exercise: Designing an Interrupt-Tolerant Worker Pool

A data team must process 50,000 image files every night. Each file takes an average of 90 seconds to resize and extract metadata. Outputs must be ready before 06:00. Source files reside in object storage; metadata writes to a DB. The workload is non-interactive.

The team proposes:

> "Run all workers on spot VMs to save money. Each VM pulls a file from the queue, processes it, and writes to the DB. If a VM is reclaimed, the system launches another VM and users won't notice."

Redesign the solution by answering:

**Exercise 1 — Workload classification.** Why does this load appear suited for spot? Which conditions could make it unsuitable (tight deadlines, non-idempotent side effects, local state)?

**Exercise 2 — Defining task units.** Should a single file or a batch of files be the unit of work? How should task IDs, input versions, output paths, and completion states be structured so retries never corrupt results?

**Exercise 3 — Handling interruptions.** Diagram the sequence from pulling a message to processing, checkpointing, writing output, and acking. Add branches for VM death before notice, after checkpoint, and after writing output before ack.

**Exercise 4 — Capacity fallback.** Choose a minimum on-demand baseline, pool/zone/instance family count, and scaling by backlog/oldest-message-age. When spot capacity is unavailable, how does the system protect the 06:00 deadline?

**Exercise 5 — Security.** Define worker roles, object storage/DB/queue permissions, secrets, disks, and logs. Should emails or personal data appear in queue payloads?

**Exercise 6 — Cost measurement.** Compare spot-first against stable capacity using cost per successfully processed file, including retries, checkpoints, fallbacks, and missed-deadline penalties.

### Sample Answer Framework

| Component | Illustrative Decision | Evidence |
| --- | --- | --- |
| Task | Single file + object version + processing config | Retries produce no duplicate or mismatched-version outputs |
| State | Queue + DB task status + durable storage checkpoints | Recovers cleanly after killing a worker |
| Worker | Spot for bulk throughput, stable baseline for guaranteed progress | Queue age and deadlines met when spot drops |
| Shutdown | Stop polling, safe checkpoint, release/expire lease, never ack incomplete tasks | Tested interruption at multiple stages |
| Security | Workload identity and least privilege | Out-of-scope access deny tests |
| Cost | Total cost / validly completed files | Billing reconciled against work-unit metrics |

## 13. Pre-Spot/Preemptible Production Checklist

- [ ] Units of work are small, carry stable IDs, and are safely rerunnable.
- [ ] Essential state lives outside preemptible VMs/containers.
- [ ] Outputs are written atomically so partial results are never treated as final.
- [ ] Tasks implement idempotency/deduplication and handle repeated side effects.
- [ ] Queue leases/visibility timeouts, heartbeats, retries/backoff, DLQs, and replays are designed.
- [ ] Workers catch interruption notices where supported, stop polling, and shut down gracefully within realistic budgets.
- [ ] The system still behaves correctly if VMs die **without notice**.
- [ ] Stable baseline capacity or explicit backlog/deadline policies exist when spot is unavailable.
- [ ] Pools are diversified across machine types/zones genuinely supported by the workload.
- [ ] Autoscalers track backlog/age/throughput and do not amplify deterministic failures.
- [ ] IAM permissions, secrets, images, networking, disks, and logs meet security policies.
- [ ] Interruption rates, retries, checkpoint overhead, completion rates, SLOs, and cost per successful task are measured.
- [ ] Runbooks, owners, quota/capacity fallbacks, and pre-production drills are in place.

Preemptible capacity delivers value when **work tolerates mid-flight interruption** and the system resumes from durable state. Good design is not running a spot worker once—it is completing the right work with the right permissions within time and budget constraints even across repeated compute reclamations.
