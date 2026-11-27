# Identifying Workloads Suitable for Reclaimable Resources

Interruptible compute resources generally have lower prices than resources guaranteed for continuous availability; in exchange, the provider can reclaim the machine or capacity when needed. Names like Spot, Preemptible, or Interruptible are product labels of individual platforms; provisioning terms, reclamation notices, runtime limits, and billing methods can differ. Therefore, selecting a machine type based on discount percentage alone is insufficient.

The decisive factor is how a workload behaves when an instance disappears unexpectedly. A batch task with checkpoints that can be rerun is usually a good fit. A service holding user sessions in memory, a primary database, or a job that cannot recover mid-execution usually needs more stable capacity. Many systems can combine both types: keep a baseline portion of capacity on regular machines and use reclaimable resources to handle flexible load.

This lesson guides you through classifying workloads, evaluating interruption tolerance, calculating economic efficiency, and designing recovery mechanisms before moving workloads to Spot or Preemptible compute. After this lesson, you will be able to:

- Identify workloads that can run on reclaimable resources versus workloads needing stable capacity.
- Evaluate retry, checkpoint, restart, and state recovery capabilities.
- Distinguish transient state from durable data while protecting consistency when an instance is stopped.
- Design workers, batch jobs, data pipelines, and training jobs to tolerate interruptions.
- Estimate real cost after factoring in rework time, checkpointing, and standby capacity.
- Combine interruptible capacity with on-demand or guaranteed capacity in a hybrid model.
- Test reclamation scenarios and establish decision criteria for each workload.

## 1. Nature of Interruptible Compute

A cloud provider can sell a portion of capacity without long-term commitments at a lower price. When that capacity needs to be allocated to higher-priority demand or per platform operational policy, the instance can be reclaimed. Users should not assume an instance will persist until the workload completes.

Common offerings are named Spot, Preemptible, or Interruptible. They can differ in:

- Reclamation reasons and conditions under which capacity is reclaimed.
- Advance notice duration before stopping or terminating.
- Behavior upon reclamation: shutdown, stop, hibernate, or terminate.
- Whether boot disks and data disks are retained.
- Maximum runtime limits, if any.
- How partial runtime and remaining storage costs are billed.
- Automatic re-provisioning or instance replacement mechanisms.

Do not treat a specific warning duration as a universal guarantee across all clouds. Some platforms send a signal before reclamation, but the window may be short, vary by event type, and applications may not always handle it in time. Proper design must tolerate the process stopping abruptly without time to checkpoint.

### Comparison with Regular Capacity

| Characteristic | Guaranteed / on-demand capacity | Reclaimable capacity |
|---|---|---|
| Purpose | Maintain service per allocated demand | Leverage spare or conditional capacity |
| Price | Typically higher or under specific commitments | Typically lower, potentially variable |
| Lifespan | Not reclaimed via normal Spot mechanisms, though infrastructure failures still occur | Can be reclaimed when the platform needs capacity |
| Suitability | Critical, stateful components, or strict latency/SLOs | Tasks capable of retry, checkpointing, or distribution |
| Operations | Must handle machine failures like any distributed system | Requires additional interruption handling and capacity replacement logic |

Regular capacity can still experience hardware failures, reboots, or zone incidents. Interruptible compute adds an additional source of disruption governed by allocation policy. Therefore, fault tolerance is necessary even without using Spot.

## 2. Criteria for Identifying Suitable Workloads

Evaluate workloads by recovery capability, not solely by runtime duration or CPU utilization.

### Decomposable and Rerunnable

Suitable workloads can usually be split into independent units:

- A file, image, video, or record that can be processed independently.
- A message in a queue that can be redelivered if a worker stops.
- A shard or partition that can be reprocessed without corrupting completed results.
- A test suite or build job that can be rerun from scratch.
- A batch that can be broken into multiple checkpointed tasks.

If a 10-hour job only saves output at the very end, being reclaimed at hour 9 can wipe out nearly all the effort. If the job is split into 5-minute tasks or checkpointed periodically, the amount of rework drops drastically.

### Safely Retryable

Retrying is only safe when repeated execution does not produce erroneous side effects. For example, reprocessing an image and writing the output to the same object key can be safe if the write is idempotent. Conversely, resending a payment debit command or sending an email can create duplicate transactions.

Determine:

- Can the task run multiple times and still yield the correct final result?
- Is there an idempotency key or unique job ID?
- Is there a deduplication mechanism or transactional outbox?
- Can the task be interrupted mid-write?
- Can completed tasks be distinguished from partially processed tasks?

Do not retry infinitely. Set retry caps, exponential backoff with jitter, a dead-letter queue, and a workflow for handling permanently failed tasks.

### Checkpointable and Recoverable

A checkpoint saves enough state to resume work after the process restarts. A checkpoint can contain:

- Processed position in a dataset or queue offset.
- Algorithm parameters and state.
- Model weights, optimizer state, and training step count.
- Pipeline state, partitions, and intermediate results.
- Code, dataset, schema, and configuration versions needed to resume.

Checkpoints must be written to durable storage external to the instance, such as object storage or volumes with an independent lifecycle. Saving checkpoints on the ephemeral local disk of a reclaimed machine does not enable recovery.

### Independent of a Single Instance

The less a workload is tied to a specific machine, the easier it is to use interruptible compute. Ask:

- Can it restart on a different instance?
- Can the environment be recreated from a VM image or container image?
- Does required data live outside the instance?
- Can lost workers be detected and replaced automatically?
- Are dependencies or licenses bound to host identity?

If the answer is no, refactor the component or keep it on stable capacity.

## 3. Workload Classification Matrix

| Workload | Initial suitability | Prerequisites |
|---|---|---|
| Image/video batch processing | High | Independent tasks, durable outputs, idempotent retries |
| CI build and test | High | Source/artifacts stored off-instance, jobs can rerun |
| Graphics rendering | High | Independent frames or chunks, progress checkpoints |
| ETL and data processing | High to medium | Partitions, offset checkpoints, safe duplicate handling |
| Distributed ML training | Medium to high | Model/optimizer checkpoints, fault-tolerant orchestration, worker synchronization |
| Batch/offline inference | High | Queues, retries, idempotent outputs, and deadline bounds |
| Horizontally scalable stateless API | Medium | Stable standby capacity, backend health checks, and fast instance replacement |
| WebSockets or long-lived sessions | Low to medium | Client reconnect, externalized sessions, and fallback capacity |
| Database primary or message broker quorum | Low | Requires stability, dedicated replication, and failover design |
| Host-locked licensing systems | Low | License vendor permits host replacement and restarts |
| Interactive tasks with very tight deadlines | Low | Cannot tolerate re-provisioning or retry latency |
| Single stateful control system | Low | Needs dedicated HA/failover design before using reclaimable capacity |

This is an initial classification. A workload unsuitable in its current form can become suitable after separating state, adding queues, checkpointing, or moving data to durable services.

## 4. Generally Suitable Workloads

### Batch Processing

Batch jobs usually process a dataset and terminate, making them easy to split into independent tasks. For example, a video transcoding system splits each video into segments; an image processing system splits by object; an ETL pipeline splits by partition or date.

Reference architecture:

~~~mermaid
flowchart TD
    A["Dataset / object storage"] --> B["Job queue"]
    B --> C["Interruptible worker pool"]
    C --> D["Process independent task"]
    D --> E["Write durable output"]
    E --> F["Mark task completed"]
    C -. "worker reclaimed" .-> G["Visibility timeout / retry"]
    G --> B
~~~

The queue holds work state. Workers pull tasks, process them, and acknowledge completion only after outputs are durably written. If a worker vanishes before acknowledgement, the queue can redeliver the task after the visibility timeout. The system must handle the possibility of a task running twice.

### CI/CD, Build, and Test

Builds, unit tests, integration tests, and certain performance tests can run on interruptible workers if:

- Source code and dependencies are pulled from a repository or shared cache.
- Build artifacts are pushed to a registry or artifact store.
- Logs and test results are shipped off the worker.
- Jobs can rerun from scratch or safely resume from cache.
- Pipelines do not hold deployment locks or perform non-repeatable production mutations.

Do not let Spot workers simultaneously run builds and hold long-lived production deployment credentials. Use short-lived workload identities, least privilege, and separate build steps from controlled release steps.

### Rendering, Encoding, and Media Processing

Frames, scenes, video segments, or encoding tasks can be subdivided. Keep a manifest recording which tasks completed, which outputs were verified, and which tasks need rerunning. For rendering, ensure chunks use identical asset, plugin, and configuration versions so stitched outputs remain consistent.

### Data Engineering and Analytics

ETL, map/reduce, batch queries, and log processing can be suitable if partitions are rerunnable. Save checkpoints by offset or watermark and use sinks with upsert/deduplication semantics. If the pipeline has non-data side effects, isolate them into a separate idempotent step.

## 5. Workloads Requiring Caution or Avoidance

### Database Primaries and Stateful Storage Systems

A database primary, metadata store, or sole state-holding node may be unsuitable without replication, failover, and recovery procedures. Instance reclamation can interrupt writes, prolong recovery time, or raise split-brain risks if fencing is improper.

Interruptible capacity can be used for read replicas, query workers, or auxiliary backup tasks if the system supports and has tested it. Do not put a database primary, critical quorum voter, or storage controller on Spot purely for lower cost.

### Interactive Services with Strict SLOs

An API can run on interruptible capacity if sufficient stable fallback capacity exists and reclaimed instances are replaced quickly. However, if the entire backend is Spot, a simultaneous reclamation wave can wipe out serving capacity. For low-latency APIs, keep the baseline on stable capacity and use Spot only for burst load or deferrable workloads.

### Long-Lived Sessions and In-Memory State

Desktop sessions, WebSockets, game sessions, or processes holding state in RAM will be affected when machines are reclaimed. Only use Spot if clients can reconnect, session state is externalized, tasks are checkpointed, or users accept session loss.

### Non-Splittable Jobs with Hard Deadlines

If a job must finish before a fixed deadline and cannot restart fast enough, an interruption can cause a deadline miss. Calculate reclamation probability, rerun duration, and standby capacity. You can run critical portions on stable machines and put only optional portions on Spot.

## 6. Evaluating Interruption Tolerance

To decide whether to use interruptible compute, score the workload against the following questions:

| Criterion | Good for interruptible | High risk |
|---|---|---|
| Splittability | Independent tasks of moderate size | One monolithic, unsplittable process |
| Retry | Idempotent, with deduplication | Retries cause duplicate transactions or corrupted data |
| Checkpoint | Frequent saves, tested recovery | No checkpoints or checkpointing is too slow |
| State | Externalized, recreatable | Lives only in RAM / local disk |
| Deadline | Deferrable or rerunnable | Hard deadline, no replacement capacity |
| Startup | Fast boot, standardized image | Slow warm-up, hard-to-load licenses or data |
| Dependencies | Headroom in capacity and quotas | Depends on a near-saturated service |
| Observability | Progress tracking, heartbeats, lost-worker detection | Unknown where tasks stopped |
| Consistency | Atomic/versioned outputs | Partial writes can corrupt data |

You can use an internal scoring rubric for screening, but never sum points and ignore a disqualifying condition. For instance, a workload scoring well everywhere except that retries can double-charge a user is still unsafe.

### Decision Questions

1. If the instance stops right now, what is the maximum amount of work lost?
2. How fast can recovery from a checkpoint complete?
3. Is there enough alternative capacity to rerun before the deadline?
4. Can a task be reassigned multiple times and still produce a single correct result?
5. If multiple instances are reclaimed simultaneously, can the system still serve traffic?
6. Do essential data and logs survive after the instance is deleted?

## 7. Checkpoint and Recovery Design

Checkpointing is a core part of long-running workloads. Checkpoint frequency must balance write overhead against potential lost work.

### Choosing a Checkpoint Interval

Suppose:

- Each checkpoint takes time $C$.
- Time between two checkpoints is $T$.
- Restart and recovery cost is $R$.
- Expected interruption rate is $\lambda$ times per unit time.

Checkpointing too frequently reduces useful compute time due to state writes. Checkpointing too rarely increases the amount of work that must be rerun. You can start with an approximate model to estimate the checkpoint interval, then measure empirically with real state sizes and storage throughput. For workloads without a stable interruption distribution, prefer choosing the interval based on the job's RPO and testing machine-loss scenarios.

You do not need to checkpoint all of RAM if a smaller algorithmic state suffices. For example, ETL can store committed offsets; file processing can store a list of completed chunks; training can store model weights, optimizer state, and step number.

### Writing Checkpoints Safely

A common workflow:

1. Create a new checkpoint at a temporary path or a new versioned object key.
2. Write complete data and metadata.
3. Verify size, checksum, and readability.
4. Flush or complete the upload per storage guarantees.
5. Only then update the active checkpoint manifest or pointer.
6. Retain a few prior versions to recover if the new checkpoint fails.

Never overwrite a valid checkpoint before the new checkpoint is verified. With object storage, use object versioning or versioned keys. With a filesystem, write a temporary file and perform an atomic rename when filesystem semantics allow.

### Handling Interruption Notices

If the platform issues a reclamation signal, the agent or application should:

- Stop accepting new tasks.
- Mark the worker as draining so the scheduler stops assigning further work.
- Save a checkpoint if enough time remains and checkpointing is safe.
- Complete ongoing writes or roll back uncommitted transactions.
- Push a final heartbeat and progress update to the coordinator.
- Exit cleanly before the stop deadline if possible.

Do not rely solely on notices. In some cases an instance can be stopped before the application can react. The supervisor must detect missed heartbeats, expired leases, or vanished workers to reassign tasks.

## 8. Retries, Idempotency, and Queue Semantics

Interruptible workers generally require at least one durable work coordination mechanism. The queue or scheduler should store task state externally from the worker.

### Task Lifecycle

~~~mermaid
stateDiagram-v2
    [*] --> Pending
    Pending --> Leased: Worker picks up task
    Leased --> Completed: Output committed
    Leased --> Pending: Lease expired / worker lost
    Leased --> RetryWait: Retryable error
    RetryWait --> Pending: Backoff elapsed
    RetryWait --> DeadLetter: Retry limit exceeded
    Completed --> [*]
    DeadLetter --> [*]
~~~

Workers should only acknowledge after outputs are durably written. If a worker is reclaimed after writing output but before acknowledging, the task may run again. Therefore, outputs must be idempotent:

- Use a stable task ID and key outputs by that ID.
- Use unique constraints or conditional writes to avoid duplicate records.
- Use processing/completed states with leases or fencing tokens.
- Separate non-repeatable side effects from retryable computation steps.
- Route repeatedly failing tasks to a dead-letter queue for investigation.

### Leases and Fencing

A worker may pause or lose network connectivity without stopping completely. If the scheduler assigns the same task to another worker, both workers might write data concurrently. A lease bounds how long a worker holds processing rights; a fencing token or generation number lets the sink reject writes from an old worker after ownership has been granted to a new worker.

Do not rely solely on heartbeats to guarantee exclusivity. Heartbeats can be delayed by network issues or hung machines. Critical writes must be guarded by transactions, compare-and-swap, versions, or fencing at the storage layer.

## 9. Capacity Allocation and Shortage Mitigation

Spot capacity is not always available across every instance type, region, or zone. A provisioning request can fail even when zero instances are running. Workloads should have a diversification strategy:

- Allow multiple equivalent instance families or sizes if the application supports them.
- Use multiple availability zones or capacity pools when data and architecture permit.
- Set per-type instance caps to avoid concentrating in one scarce pool.
- Configure fallback to on-demand or stable capacity for load that must finish.
- Separate high-priority tasks from deferrable tasks.

Diversification does not mean picking arbitrary machine types. Verify CPU architecture, RAM, GPU, network, local storage, instruction sets, and drivers. For GPUs, models and workloads must run on the selected accelerator families; not all GPUs are equivalent.

### Stable Baseline and Interruptible Burst

A hybrid architecture typically keeps enough stable capacity to serve minimum load, then uses Spot to supplement:

~~~mermaid
flowchart TD
    L["Workload / queue"] --> S["Scheduler"]
    S --> O["Stable capacity pool"]
    S --> P["Interruptible pool"]
    O --> R["Process priority / baseline tasks"]
    P --> B["Process retryable / batch tasks"]
    R --> D[("Durable output")]
    B --> D
    P -. "Capacity reclaimed" .-> Q["Requeue / retry / checkpoint"]
    Q --> L
~~~

Stable capacity can serve interactive requests, coordination, and non-deferrable tasks. The interruptible pool handles splittable or queueable work. If Spot capacity disappears, the queue grows while the primary service stays at its designed level.

## 10. Calculating Real Economic Efficiency

Lower hourly rates do not always mean lower total cost. Calculate cost per completed unit of work.

A simple model:

**Effective cost = compute cost + checkpoint storage + data transfer + coordination + rework**

**Cost per successful task = total effective cost / number of valid completed tasks**

Factors to include:

- Actual interruptible prices across regions and times of day.
- Useful instance runtime before reclamation.
- Task retry rate and lost processing time.
- Cost to create, read, and store checkpoints.
- Data transfer cost when tasks shift to other instances.
- Startup overhead to pull images, models, or datasets.
- Cost of stable standby capacity.
- Operational cost and added complexity.

### Simple Calculation Example

Suppose a batch needs 100 hours of useful compute. On-demand costs 1 unit/hour. Interruptible costs 0.4 units/hour. If interruptions cause total compute runtime to reach 125 hours and checkpoint/storage/transfer costs are 5 units:

| Option | Compute cost | Overhead cost | Total |
|---|---:|---:|---:|
| On-demand | 100 × 1 = 100 | 0 | 100 |
| Interruptible | 125 × 0.4 = 50 | 5 | 55 |

In this example, interruptible still saves money. However, if rework climbs to 230 hours and overhead is 10, the total becomes 102 units, higher than on-demand. These numbers are illustrative only; gather real pricing, interruption history, and processing times from the target environment.

### Do Not Optimize by Discount Percentage Alone

Track:

- Cost per successful job.
- Task retry or dead-letter rate.
- Ratio of useful compute time to total instance time.
- Time from interruption until task resumption.
- Cost of storing checkpoints and intermediate data.
- Deadline and SLO compliance rate.

If compute savings come with frequent missed deadlines, that choice may not fit the product.

## 11. Choosing Task Size and Runtime Duration

Tasks that are too long increase the amount of work lost on reclamation. Tasks that are too short increase coordination, startup, and metadata write overhead.

Balance:

- Task duration against interruption probability.
- Worker startup and data-loading time.
- Checkpoint cost and commit frequency.
- Output size and upload duration.
- Task splittability and even distribution.
- Deadlines and backlog drain rate.

For example, a transcoding pipeline can split video into 2–5 minute chunks instead of a 2-hour job if the codec and stitching process permit. A training job does not have to checkpoint every batch; it can save every N steps or measured time interval to balance cost.

There is no universal optimal task duration. Experiment with several task sizes and compare successful throughput, recovery time, and cost per unit of work.

## 12. Security and Data Management

Instances can be reclaimed, replaced, or launched in a different capacity pool. Therefore, avoid storing secrets or critical data solely on the machine:

- Fetch short-lived credentials from workload identity or a secret manager.
- Do not embed private keys, long-lived tokens, or passwords in images.
- Use least-privilege permissions for buckets, queues, databases, and registries.
- Encrypt data in transit and at rest per policy.
- Restrict metadata service access and protect instance identity.
- Wipe temporary data or sensitive caches when an instance shuts down.
- Ship logs and audit events off the instance.

For sensitive data, verify storage locations, processing regions, access controls, and retention rules. Cheaper compute does not reduce data protection responsibilities.

## 13. Reference Architecture Patterns

### Stateless Worker with Queue

- Queue holds tasks durably.
- Workers can stop and restart on different machines.
- Outputs are written keyed by task ID and acknowledged only after commit.
- Lease expiration enables task reassignment.
- Dead-letter queue captures failing tasks needing intervention.

This is usually the easiest pattern to start with for interruptible compute.

### Checkpointed Batch

- Scheduler splits batches into partitions.
- Each partition writes its own checkpoints and outputs.
- Reclaimed workers only trigger reruns of incomplete partitions.
- Aggregator verifies all partitions before publishing results.

### Distributed Training

- A stable capacity group can host coordination or parameter services if required by the architecture.
- Interruptible workers participate in computation via fault-tolerant mechanisms.
- Training checkpoints include model, optimizer, scheduler, random state, and step.
- When a worker is lost, orchestration replaces the worker or restores from the latest checkpoint.
- With synchronous training, losing one worker can stall the whole group; evaluate elastic training, worker replacement, and checkpoint cadence.

Not every distributed training framework supports hot-swapping workers. Check framework semantics and test real interruptions before migrating workloads.

### Hybrid API and Batch

- Interactive API serves requests on stable capacity.
- Heavy requests are enqueued.
- Interruptible workers process retryable background tasks.
- Results are durably persisted and the API returns progress status.

This decoupling ensures users do not depend on a Spot instance surviving throughout a long request.

## 14. Testing Interruption Before Production

Do not wait for the provider to reclaim real machines to discover whether the application recovers. Proactively simulate:

1. Stopping a worker mid-task.
2. Stopping a worker after writing output but before acknowledgement.
3. Stopping a worker while writing a checkpoint.
4. Dropping network connectivity to the queue or object storage.
5. Slowing down or failing checkpoints.
6. Reclaiming multiple workers simultaneously.
7. Attempting re-provisioning when Spot pools are out of capacity.
8. Shifting tasks to a different instance type.
9. Restarting from an older checkpoint and verifying outputs.

Pass criteria:

- No loss of acknowledged tasks.
- Tasks can rerun without creating duplicate outputs or side effects.
- Corrupted checkpoints never overwrite prior good checkpoints.
- Lost workers are detected within an acceptable timeframe.
- Queues do not grow unbounded and apply backpressure.
- Workloads complete within deadlines or fall back properly.
- Actual cost still meets targets after accounting for retries and recovery.

## 15. Workload Selection Workflow

~~~mermaid
flowchart TD
    A["Define workload and SLO"] --> B{"Can it be split or retried?"}
    B -- "No" --> C{"Can state be externalized and checkpointed?"}
    C -- "No" --> D["Use stable capacity"]
    C -- "Yes" --> E["Design recovery and test"]
    B -- "Yes" --> E
    E --> F{"Are retries idempotent and data durable?"}
    F -- "No" --> G["Add deduplication / transactions / checkpoints"]
    G --> H["Test interruption and recovery"]
    F -- "Yes" --> H
    H --> I{"Meets SLO, deadline, and cost?"}
    I -- "No" --> D
    I -- "Yes" --> J["Run interruptible canary"]
    J --> K["Scale gradually and monitor"]
~~~

A practical workflow:

1. Document tasks, deadlines, SLOs, and required durable data.
2. Classify state, dependencies, and splittability.
3. Design queues, retries, checkpoints, or resume mechanisms.
4. Select compatible, diversified instance types and pools.
5. Calculate effective cost and standby capacity.
6. Simulate interruptions in staging.
7. Run a canary on a fraction of the workload.
8. Monitor interruption rate, retries, recovery time, and cost per successful job.
9. Increase the interruptible ratio only once stability criteria are met.

## 16. Common Mistakes

1. **Treating Spot as cheaper on-demand machines:** ignoring reclamation risk.
2. **Not storing state outside the instance:** losing data or progress on termination.
3. **Handling only interruption notices:** applications still fail on sudden stops.
4. **Non-idempotent retries:** creating duplicate records, transactions, or side effects.
5. **Non-atomic checkpoints:** partially written new checkpoints break resume capability.
6. **Using a single capacity pool:** unable to re-provision when that pool runs dry.
7. **Putting an entire critical system on Spot:** a reclamation wave causes a service outage.
8. **Ignoring downstream dependencies:** scaling out workers overloads databases or storage.
9. **Comparing hourly prices only:** omitting rework compute, checkpoints, startup, and operations.
10. **Not testing simultaneous multi-instance reclamations:** underestimating correlated impact.
11. **Using incompatible licenses or host identity:** replacement machines fail to start the workload.
12. **Having no fallback:** backlogs grow with no stable capacity to meet critical deadlines.

## 17. Pre-Adoption Checklist for Interruptible Compute

- [ ] Workload can be split, retried, or checkpointed.
- [ ] Durable data is stored external to the instance.
- [ ] Tasks have stable IDs and duplicate-processing protection.
- [ ] Outputs are published only after complete write and verification.
- [ ] Lost workers are detected via leases/heartbeats/timeouts.
- [ ] Interruption notices are handled without depending exclusively on them.
- [ ] Retry limits, backoff, jitter, and dead-letter queues are configured.
- [ ] Alternative capacity pools or instance types are configured.
- [ ] Dependencies and downstream services tolerate fluctuating worker counts.
- [ ] Stable baseline capacity exists if the workload requires continuous SLOs.
- [ ] Cost per successful job is calculated, including retries and checkpoints.
- [ ] Single and simultaneous interruptions have been tested.
- [ ] Logs, metrics, alerts, and recovery runbooks are in place.
- [ ] Credentials, secrets, and sensitive data do not depend on instance lifecycle.
- [ ] Criteria exist for canarying, scaling out, and falling back to stable capacity.

## 18. Practice Exercise

A team processes 500,000 images every night. Each image takes an average of 8 seconds to resize and compress. The team currently runs on 20 on-demand VMs. Spot instances are available at an assumed price of 35% of on-demand, but workers may be reclaimed mid-processing. Outputs are written to object storage and task results are recorded in a database.

1. Why is this workload potentially suitable for interruptible compute?
2. Propose how to split tasks, track progress, and confirm completion.
3. If a worker is reclaimed after uploading the output but before updating task status, how do you avoid duplicate results?
4. What metrics should the team monitor besides hourly compute price?
5. Which components should continue running on stable capacity?
6. What interruption tests are needed before shifting most of the workload to Spot?

Hint: use a stable task ID per image, write outputs to deterministic object keys, and use conditional updates/unique constraints so completed status commits only once. Workers acknowledge only after verifying output. Monitor cost per successful image, retry rate, interruption rate, queue age, batch completion time, and storage cost. The queue, coordination database, and deadline-critical components should run on stable capacity; resize workers can use Spot after testing retries and deduplication.

## Conclusion

Interruptible compute works best for workloads that can be split, rerun, or resumed from checkpoints, keep durable data outside the instance, and handle retries safely. Batch jobs, CI, rendering, ETL, and many offline tasks are strong candidates. Database primaries, standalone stateful services, and strict-deadline interactive tasks require stable capacity or dedicated HA architectures. Final decisions should rest on SLOs, recovery capability, capacity supply, and cost per completed unit of work, validated by testing interruptions under near-production conditions.
