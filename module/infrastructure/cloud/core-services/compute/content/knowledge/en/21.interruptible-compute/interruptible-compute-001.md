# How Spot, Preemptible, and Interruptible Compute Work

## Learning Objectives

Spot, preemptible, and interruptible compute are ways to use a cloud provider's spare compute capacity at a price that is typically lower than on-demand machines. In exchange, the provider can reclaim the resources when needed. A workload running on this type of machine must tolerate being stopped, save state safely, and resume work on another instance.

After this lesson, you will be able to:

- Explain how reclaimable capacity works and its common naming conventions.
- Distinguish cost benefits from interruption and capacity shortage risks.
- Recognize preemption reasons, interruption notices, and lifecycle states.
- Select workloads suitable for Spot or preemptible compute.
- Design checkpointing, retries, idempotency, and graceful shutdown.
- Combine reclaimable machines with on-demand machines to maintain service levels.
- Operate Spot fleets, autoscaling groups, and Kubernetes node pools safely.
- Measure cost per completed unit of work instead of looking only at the hourly price.

## 1. What Is Interruptible Compute?

A cloud provider may have unused compute capacity at a given point in time. They can sell this spare capacity at a discounted rate. These machines or resources are commonly referred to by names such as:

- **Spot instance / Spot VM:** virtual machines using spare capacity, with variable pricing or provider-specific pricing mechanisms, that can be reclaimed.
- **Preemptible VM:** virtual machines that the provider can reclaim before the user explicitly stops them; some preemptible offerings also have a maximum runtime limit.
- **Interruptible compute:** a general term for compute resources that the provider or orchestration platform has the right to stop, reclaim, or replace with limited advance notice.

Terminology and terms of service are not identical across providers. Some Spot offerings have no fixed maximum runtime limit yet can still be reclaimed at any time; some preemptible offerings have their own lifespan limits. You must read the policies for the specific service, region, and resource type you are using.

The common thread is that users do not get a continuous capacity guarantee like on-demand machines or capacity reservations. The lower price compensates for accepting interruptions and the possibility of not obtaining machines when needed.

### 1.1. Why Do Providers Reclaim Machines?

Common reasons include:

- The provider needs capacity to satisfy higher-priority demand.
- A host or infrastructure zone requires maintenance or fault remediation.
- Capacity for an instance family or Availability Zone runs short.
- The market price or user-configured price threshold no longer matches product policy.
- The service enforces a runtime limit or specific reclamation conditions.
- The provider detects an infrastructure condition that requires moving or stopping workloads.

Not every reclamation is predictable. Some services send an interruption notice before stopping the machine; some provide other lifecycle signals; and there are also host failure scenarios where a machine disappears without sufficient time to handle it. Workload design must tolerate both noticed interruptions and sudden machine loss.

### 1.2. Trade-off Model

| Attribute | On-demand / reserved capacity | Spot / preemptible |
|---|---|---|
| Compute price | Typically higher at list rates | Typically discounted |
| Capacity retention | Per product commitment | Not continuously guaranteed |
| Reclamation timing | User or operational policy | Provider can reclaim |
| Advance notice | Not applicable to Spot reclamation | May exist; notice window and guarantees vary by service |
| Suitability | Workloads needing stability, stateful workloads, or strict latency | Fault-tolerant workloads capable of retry/checkpointing |
| Actual cost | More predictable | Depends on interruptions, retries, and lost work |

Spot is neither a free resource nor always available. Treat it as a lower-cost capacity source with uncertain availability.

## 2. Spot Capacity and Capacity Pools

A capacity pool is typically defined by a combination of attributes such as:

- Region and Availability Zone.
- Instance family, size, or accelerator type.
- CPU architecture and operating system platform.
- Tenancy or deployment model.
- Networking, storage, and product constraints.
- Related placement or reservation requirements.

Two instances with the same vCPU and RAM counts but in different families or zones can belong to two separate pools. One pool's capacity can be exhausted while another pool still has capacity available.

If you request only a single instance type in a single AZ, the system depends on a narrow pool. When that pool lacks capacity or experiences a high interruption rate, the autoscaler cannot easily replace machines.

### 2.1. Diversifying Capacity

To increase the odds of obtaining capacity, you can broaden the selection list:

- Multiple instance families with equivalent performance.
- Several sizes suitable for the same workload.
- Multiple Availability Zones within the same region.
- Multiple pools with CPU architectures or hardware configurations supported by the application.
- Combining Spot with on-demand capacity.

Do not diversify indiscriminately. The application must be compatible with the CPU architecture, RAM, GPU, networking, and storage of the alternative choices. Define the instance type set based on resource requirements and benchmarks, then expand within equivalent groups.

### 2.2. Pool Selection Strategies

Common strategies in Spot fleet services include:

| Strategy | Idea | When to consider |
|---|---|---|
| Lowest price | Prioritize pools with the lowest price | Highly fault-tolerant workloads where price is the primary goal and volatility is acceptable |
| Capacity optimized | Prioritize pools with better capacity availability | Wanting to reduce the risk of capacity shortage or interruption |
| Price-capacity optimized | Balance price and capacity availability | Wanting to lower costs while still caring about continuity |
| Diversified | Distribute across multiple pools | Wanting to reduce dependence on any single pool |

Strategy names, calculation methods, and support vary by provider. Do not assume two clouds use the same algorithm just because the names look similar.

Prioritizing stable capacity is often worth more than picking the cheapest pool if a single interruption wipes out hours of processing. Evaluate by cost per completed unit of work and success rate, not just machine price.

## 3. Spot Pricing and Total Actual Cost

Spot prices can vary by pool, time, region, and service policy. Some products publish current prices; others apply fixed discounts or proprietary pricing mechanisms. A maximum price threshold option may exist, though not every service offers it and behavior differs.

Setting the price threshold too low can cause instances to be reclaimed or fail to provision. If the workload supports checkpointing and self-recovery, it is usually better to pick an appropriate capacity strategy rather than relying solely on a very low price cap.

### 3.1. Hourly Cost Is Not Cost Per Outcome

Suppose a batch job needs 4 hours of useful CPU time. If the machine is reclaimed every 90 minutes and the work has not been checkpointed, the processing done before the interruption may have to be rerun. A lower hourly price does not guarantee a lower total cost.

A simple evaluation formula:

~~~text
Cost per completed unit of work =
  (compute + storage + network + checkpoint + retry + operations)
  / number of completed units of work
~~~

Items to account for:

- Compute time lost after each interruption.
- Cost of creating checkpoints, writing to object storage, or syncing state.
- Restart, data reload, and warmup overhead.
- Queue, retry, duplicate processing, and temporary storage costs.
- Fallback on-demand capacity costs.
- Operational and incident-handling effort.

### 3.2. Comparison Example

A batch worker group processes 10,000 tasks. There are two options:

| Metric | On-demand fleet | Hybrid Spot + on-demand fleet |
|---|---:|---:|
| Assumed average compute price | Higher | Lower |
| Retried tasks | Low | Potentially higher |
| Baseline capacity | Stable | On-demand holds the baseline |
| Burst capacity | On-demand | Spot supplements |
| Checkpointing requirement | Potentially simpler | Requires explicit design |
| Capacity shortage risk | Lower if reserved/guaranteed | Higher in Spot pools |
| Cost per successful task | Baseline | Must be measured after retries and interruptions |

You cannot conclude the Spot option is cheaper from the discount rate alone. Run a small-scale pilot, record interruptions, rework time, and total cost before migrating large workloads.

## 4. Interruption Notices and Reclamation Lifecycle

Some services provide an advance signal before reclaiming an instance. The signal may arrive via a metadata endpoint, event service, notification, API, or lifecycle state. How the signal is delivered and the advance notice window depend on the platform.

Upon receiving a notice, the application needs to transition into controlled shutdown mode:

1. Record the interruption event and the deadline for completion.
2. Stop accepting new work.
3. Deregister the instance from the load balancer or stop polling the queue.
4. Finish in-flight requests/jobs if enough time remains.
5. Write a checkpoint or persist intermediate results.
6. Flush critical logs and metrics.
7. Close connections, release locks/leases, and exit the process.
8. Allow the instance to be reclaimed or terminated according to the provider's lifecycle.

Never assume a notice will always arrive or always give enough time to finish all work. Notice windows can be short, vary by product, and may not appear at all during sudden host failures.

### 4.1. Two-Path Handling Design

A resilient system needs both paths:

- **Graceful interruption:** receive the notice, stop accepting new work, checkpoint, and exit.
- **Unexpected loss:** the instance vanishes before the shutdown handler can run; the workload is detected via heartbeat/lease expiration and the job is reassigned.

The second path is mandatory. If data correctness relies on the shutdown hook being guaranteed to run, the system is not yet interruption-tolerant.

~~~mermaid
flowchart TD
    A["Spot instance running"] --> B{"Interruption notice?"}
    B -->|Yes| C["Stop accepting new work"]
    C --> D["Drain and checkpoint"]
    D --> E["Flush and exit"]
    B -->|No, sudden machine loss| F["Heartbeat or lease expires"]
    F --> G["Scheduler detects lost worker"]
    E --> H["Job confirmed complete or reassigned"]
    G --> H
    H --> I["Another worker resumes"]
~~~

## 5. Checkpoint Design

A checkpoint is a saved snapshot of state sufficient to resume work from a recent point after an instance is stopped.

A good checkpoint should include:

- Job ID or partition ID.
- Schema version and application version.
- Offset, cursor, or processing position.
- State required for recovery.
- Timestamp and generation/version.
- Checksum or integrity verification mechanism.
- Completion status and compatibility metadata.

Checkpoints must be written to storage that persists independently of the reclaimable instance, such as object storage, a database, or a durable storage service. Data stored only on local ephemeral disk can be lost along with the machine.

### 5.1. Writing Checkpoints Safely

A safe checkpoint write workflow can include:

1. Create a consistent snapshot of state at a work boundary.
2. Write to a temporary object/key with a new generation.
3. Read back metadata or verify the checksum.
4. Write a manifest confirming the checkpoint is complete.
5. Only then update the latest checkpoint pointer.
6. Retain the previous checkpoint until the new checkpoint is confirmed.

This write pattern prevents a process stopped mid-write from leaving behind a partial file that gets mistaken for a valid checkpoint.

Do not overwrite the latest good checkpoint with an incomplete one. If using a database, use appropriate transactions or versioning mechanisms. If using object storage, design keys and manifests so that the checkpoint publish operation can be verified.

### 5.2. Choosing a Checkpoint Interval

Checkpointing too frequently increases I/O, network traffic, and cost. Checkpointing too infrequently increases the amount of work that must be rerun.

If work is interrupted randomly and interruption timing is independent of progress, the expected lost work is roughly half a checkpoint interval. This is only a simple estimation model; workload characteristics, interruption distribution, and checkpoint write duration can alter the actual result.

Consider:

- Time and cost to produce one checkpoint.
- Processing speed and rerun cost.
- Observed interruption frequency.
- State size and recovery duration.
- Job completion SLO and acceptable data loss tolerance.

You can checkpoint by elapsed time, record count, batch count, model steps, or transaction boundaries. For data pipelines, the message/partition offset is often a natural recovery point.

## 6. Retries and Idempotency

When a worker is reclaimed, the scheduler may reassign the same work to another worker. The old worker might have written results without acknowledging completion in time. If the new worker runs it again, results could be duplicated.

**Idempotency** means executing the same operation again with the same business key does not cause unintended changes to the final outcome.

Common techniques:

- Assign a stable idempotency key to each job or operation.
- Use unique constraints or conditional upserts in the database.
- Commit offsets / ack messages only after results are durably persisted.
- Use transactions or the outbox pattern for writes and event emission.
- Design retries with exponential backoff and jitter.
- Cap retry counts and route persistently failing jobs to a dead-letter queue.
- Store job state with a lease or fencing token so an old worker cannot overwrite a new worker.

### 6.1. Leases and Fencing Tokens

A worker can hold a lease for a bounded duration. If the worker misses heartbeats, the scheduler allows another worker to take over. However, the old worker may still be running briefly due to a network partition.

A fencing token is a monotonically increasing version number or session token. The storage system accepts operations only from the latest token. This prevents an old worker from writing results after job ownership has transferred to a new worker.

Leases detect lost workers; fencing tokens protect data when two workers simultaneously believe they own the work.

## 7. Workloads Suitable for Spot / Preemptible

Spot is best suited for workloads that can be sharded, retried, or recovered from checkpoints.

| Workload | Suitability | Conditions |
|---|---|---|
| Batch processing | High | Split jobs into small tasks, persist results durably |
| CI build/test | High | Builds can be rerun, caches stored off-instance |
| Rendering/transcoding | High | Split frames/chunks and write partial outputs |
| Data processing | High | Checkpoint offsets, partitions, and ensure safe reprocessing |
| ML training | Conditional | Framework supports model/optimizer checkpointing and resume |
| Stateless web/API | Conditional | Replacement capacity available, load balancer, and no local state |
| Kubernetes worker node | Conditional | Pods can reschedule, PDBs and termination handling properly designed |
| Database replica/read worker | Conditional | Replication and replica replacement procedures in place |
| Database primary | Low | Consider only with tested failover architecture and durable storage |
| Stateful singleton | Low | Risks state loss or service outage without a replacement |
| Latency-critical service | Low to medium | Use only for replaceable capacity without breaking SLOs |

Do not place 100% of a critical service's capacity on Spot if the service lacks a fallback plan. Even a stateless application can experience an outage if all instances sit in the same reclaimed pool.

### 7.1. Splitting Workloads into Reclaimable Parts

A common architecture:

- Control plane and scheduler run on stable capacity.
- A queue holds pending work.
- Spot workers process retryable tasks.
- Results and checkpoints are written to durable storage.
- A small group of on-demand workers serves as fallback capacity or handles tasks needing fast completion.
- An autoscaler adds workers based on backlog and replaces lost workers.

This separation isolates interruption impact to the worker tier while keeping state and orchestration on the stable layer.

~~~mermaid
flowchart LR
    U["Producer / API"] --> Q["Durable queue"]
    Q --> S["Scheduler"]
    S --> O["On-demand workers"]
    S --> P["Spot workers"]
    O --> R["Checkpoint / result store"]
    P --> R
    R --> D["Result consumer"]
    P -. "Interruption / retry" .-> S
~~~

## 8. Building a Mixed On-Demand and Spot Fleet

A mixed fleet typically uses stable capacity as a baseline, then adds Spot to handle variable load.

For example, a service needing at least 6 workers for baseline load and scaling up to 30 workers during peak hours:

- Maintain 6 on-demand workers or guaranteed capacity.
- Add Spot workers as queue backlog grows.
- If Spot capacity cannot be obtained, allow on-demand to scale up to a defined cap.
- When load drops, terminate Spot workers first per policy.
- Keep enough headroom to absorb interruptions and replacement worker startup time.

The Spot ratio should not be chosen based on discount alone. It depends on interruption rate, replaceability, SLOs, and the amount of on-demand capacity the budget can afford.

### 8.1. Allocation Policies

Guiding principles include:

- Keep the most critical capacity on on-demand or reserved capacity.
- Use Spot for load that can be shed or rerun.
- Diversify instance families and AZs within equivalent groups.
- Maintain a minimum on-demand capacity so you are not wholly dependent on Spot.
- Enable fallback to on-demand when Spot is unavailable if SLOs require it.
- Set maximum capacity limits and budget guardrails to prevent unexpected cost spikes.
- Avoid scaling all workers into a single pool or a single AZ.

Falling back to on-demand improves availability but can cause costs to spike rapidly during a Spot shortage. Configure caps, alerts, and job prioritization rules.

### 8.2. Avoiding Thundering Herds on Reclamation

If many instances are reclaimed simultaneously, all workers may retry or launch replacement instances at once. This creates traffic spikes against cloud APIs, registries, databases, queues, and dependencies.

Mitigate the risk by:

- Using backoff with jitter for retries.
- Rate-limiting instance launches and concurrent jobs.
- Distributing workers across multiple pools/AZs.
- Setting per-dependency concurrency limits.
- Separating high-priority and low-priority jobs.
- Avoiding having every worker pull the same large artifact simultaneously.
- Monitoring backlog and replacement throughput.

## 9. Spot in Autoscaling Groups

An instance group can combine multiple instance types and capacity sources. Typical configuration includes:

- List of allowed instance types.
- On-demand ratio or base count.
- Spot pool selection strategy.
- List of AZs.
- Desired/minimum/maximum capacity.
- Health checks and replacement policy.
- Instance warmup.
- Lifecycle hooks or interruption handlers.
- Capacity rebalancing if supported by the service.

Capacity rebalancing is a mechanism on some platforms that proactively replaces instances assessed as having elevated reclamation risk before the final interruption notice arrives. This mechanism may provision a new machine first, then drain and remove the old one. Replacement capacity is not always available, so sudden machine loss must still be handled.

### 9.1. How the Instance Group Operates

1. Scaling policy detects a capacity deficit.
2. Fleet manager selects an appropriate pool from the allowed list.
3. Instance launches and registers with monitoring.
4. Health check confirms the application is ready.
5. Load balancer or scheduler distributes work.
6. Interruption handler receives a notice if present.
7. Worker stops accepting work and checkpoints.
8. Fleet manager replaces the instance if capacity is available.
9. Scheduler reassigns incomplete tasks.

Do not equate desired capacity with healthy capacity. An instance that is provisioning, booting, or warming up does not yet contribute real processing capacity.

## 10. Spot in Kubernetes

Kubernetes can run Spot node pools for fault-tolerant workloads. Spot nodes can be reclaimed by the provider; Pods must be designed to reschedule and recover.

Components that must work together:

- Node pool or node group labeled as Spot.
- Taints/labels so only suitable workloads are scheduled onto these nodes.
- Tolerations and node affinity on Pods.
- Node termination handler or mechanism to receive interruption events.
- Draining the node before termination when time permits.
- PodDisruptionBudget (PDB) for controllable evictions.
- Replicas spread across multiple nodes/AZs.
- Persistent state on durable storage and proper detach/reattach mechanisms.

### 10.1. Example of Isolating Spot Workloads

For example, Spot nodes have dedicated labels and taints. Batch worker Pods accept scheduling onto that node group:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: batch-worker
spec:
  replicas: 8
  selector:
    matchLabels:
      app: batch-worker
  template:
    metadata:
      labels:
        app: batch-worker
    spec:
      nodeSelector:
        capacity-type: spot
      tolerations:
        - key: "capacity-type"
          operator: "Equal"
          value: "spot"
          effect: "NoSchedule"
      terminationGracePeriodSeconds: 90
      containers:
        - name: worker
          image: registry.example.com/batch-worker:3.0.0
          lifecycle:
            preStop:
              exec:
                command: ["/app/bin/stop-accepting-work"]
~~~

This is an illustrative example; labels, taints, and Spot identification depend on the node provider/controller. The `preStop` command must exist in the image and must stop accepting work in a way the application supports. Kubernetes may send SIGTERM after running the hook; the application must perform graceful shutdown and complete within the termination grace period.

### 10.2. Role and Limits of PDBs

A PodDisruptionBudget limits the number of Pods that can be disrupted by Kubernetes-controlled evictions. PDBs help protect availability during planned node drains, but they do not prevent the provider from shutting down a machine abruptly and do not guarantee Pods stay alive when a node is lost.

Therefore:

- Maintain sufficient replicas across independent nodes/AZs.
- Set a PDB appropriate to the replica count and required availability level.
- Configure a node termination handler to drain upon receiving a notice.
- Test node loss scenarios with no drain time.
- Ensure workloads have retries, checkpoints, or externalized state.

Do not treat a PDB as a guarantee against Spot interruptions.

## 11. Handling Interruptions in the Application

The application needs to know how to stop accepting work and finish in-progress work.

A queue-processing worker can follow this workflow:

1. Receive the interruption signal.
2. Transition worker state to draining.
3. Stop polling or receiving new messages.
4. Complete the current batch if enough time remains.
5. Commit results durably.
6. Ack the message or update the checkpoint after committing.
7. If time runs out, do not ack so the queue redelivers after the visibility timeout/lease.
8. Close the consumer and exit.

Never ack a message before results are committed. If the worker is reclaimed after acking but before writing results, work can be lost.

### 11.1. Java Graceful Shutdown Example

The snippet below illustrates a worker that can stop accepting new tasks, wait for current tasks, and save a checkpoint:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public final class WorkerLifecycle {
    private final AtomicBoolean draining = new AtomicBoolean(false);
    private final ExecutorService executor;
    private final CheckpointStore checkpointStore;

    public WorkerLifecycle(
            ExecutorService executor,
            CheckpointStore checkpointStore) {
        this.executor = executor;
        this.checkpointStore = checkpointStore;
    }

    public boolean canAcceptWork() {
        return !draining.get();
    }

    public void onInterruption() {
        if (!draining.compareAndSet(false, true)) {
            return;
        }

        stopPollingForNewTasks();

        executor.shutdown();
        try {
            if (!executor.awaitTermination(45, TimeUnit.SECONDS)) {
                requestCooperativeStopAtSafeBoundary();
                executor.shutdownNow();
                if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                    return; // Rely on periodic checkpoints when tasks cannot stop safely.
                }
            }
            checkpointStore.saveConsistentCheckpoint();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            executor.shutdownNow();
        }
    }

    private void requestCooperativeStopAtSafeBoundary() {
        // Request tasks to stop at a safe boundary per application protocol.
    }

    private void stopPollingForNewTasks() {
        // Stop the consumer or scheduler via the application API.
    }

    interface CheckpointStore {
        void saveConsistentCheckpoint();
    }
}
~~~

This code only illustrates the structure. In a real implementation, you must handle checkpoint errors, transaction states, remaining timeout, and task interruption. Do not invoke checkpointing concurrently with tasks mutating the same state without a consistent snapshot mechanism.

A JVM shutdown hook can help handle SIGTERM or controlled termination signals. However, it is not guaranteed to run during host power loss, kernel panic, or unnotified provider reclamation. Periodic checkpointing remains essential.

### 11.2. Shutdown Time Budget

Shutdown duration must be shorter than the actual advance notice window and the granted termination grace period. Allocate separate budgets for:

- Stopping new work intake.
- Completing in-flight requests/tasks.
- Writing the checkpoint.
- Flushing logs/metrics.
- Closing connections and exiting.

If the notice window is too short to complete the job, aborting cleanly and reassigning the task is usually safer than trying to finish and writing partial data.

## 12. Storage and Data Protection

Spot instances are generally treated as ephemeral compute. Data design must assume local ephemeral storage can disappear.

Principles:

- Store durable data in a database, object storage, or volumes with an independent lifecycle.
- Never store the sole copy of results on a Spot VM's root disk.
- Encrypt volumes, checkpoints, and temporary data.
- Use workload identity or short-lived credentials.
- Do not bake secrets into images or snapshots.
- Delete or revoke credentials when an instance is terminated.
- Set TTLs on temporary files and old checkpoints.
- Control access to checkpoints per job/tenant.
- Record versions to avoid restoring state with an incompatible binary.

If using persistent volumes, verify attach/detach semantics, zone affinity, and volume reattachment time on a replacement machine. Volumes do not automatically migrate across AZs in every service. For stateful data, design appropriate replication or independent storage.

## 13. Monitoring and Measuring Spot Effectiveness

Do not monitor only the count of running instances. Observe capacity fulfillment, interruptions, and impacted work as well.

| Metric | Meaning |
|---|---|
| Spot capacity requested/fulfilled | Spot capacity requested versus provisioned |
| Spot share | Percentage of running capacity on Spot |
| Interruption count/rate | Count or rate of reclaimed instances |
| Interruption reason | Reason or event type if provided by the cloud |
| Notice-to-drain duration | Time from notice until the worker stops accepting work |
| Checkpoint success rate | Percentage of checkpoints completed successfully |
| Checkpoint age | Age of the latest checkpoint |
| Work lost/retried | Volume of work that had to be reprocessed |
| Job completion rate | Rate of completed jobs |
| Queue backlog/age | Queue depth and age of queued work |
| Replacement time | Time until a replacement worker becomes ready |
| On-demand fallback share | Share of capacity shifted to on-demand |
| Cost per completed unit | Cost per completed job/record/frame |

Tag interruption events with instance pool, instance type, AZ, image version, and workload. Avoid using instance IDs as labels on all long-term metrics if instance counts are high; store IDs in events/logs for detailed investigation instead.

### 13.1. Essential Alerts

- Sudden spike in interruption rate within a pool.
- Spot capacity failing to provision for an extended period.
- On-demand fallback exceeding budget.
- Checkpoint failures or overly stale checkpoints.
- Queue backlog growing despite autoscaler scale-out.
- Replacement time exceeding SLO.
- Rising job retries or duplicate results.
- One AZ or instance family becoming a point of capacity concentration.

When an interruption occurs, distinguish provider events from application bugs. An instance being reclaimed is expected product behavior; failed checkpoints or duplicated data are design bugs that must be fixed.

## 14. Testing Interruption Resilience

Do not wait for the first Spot eviction in production to test the system. You can proactively terminate workers or nodes in a test environment to simulate failure points.

Test scenarios:

1. Stop a worker when no task is running.
2. Stop a worker mid-task but after a checkpoint.
3. Stop a worker while writing a checkpoint.
4. Stop a worker after committing results but before acking the message.
5. Sudden node loss with no notice.
6. Reclaim multiple workers simultaneously.
7. Failure to provision replacement Spot capacity.
8. Fallback to on-demand within budget limits.
9. Verify jobs are not lost and results are not duplicated.
10. Measure recovery time and rework cost.

After each test, reconcile the queue, checkpoints, database, and outputs. A test that only proves a Pod or VM is recreated is insufficient; you must prove business work resumes correctly.

## 15. Common Pitfalls

**Using Spot for non-interruptible workloads:** a singleton or primary without failover can take down the entire service. Put only replaceable capacity on Spot.

**Relying solely on interruption notices:** hosts can fail or vanish before the handler runs. Use periodic checkpoints and leases/heartbeats.

**Storing state only on local disk:** data is lost when the instance is reclaimed. Write state to durable storage.

**Acking messages before committing:** an interruption can cause work loss. Commit results first, then ack.

**Retrying without idempotency:** a new worker can produce duplicate results. Use idempotency keys, transactions, or fencing tokens.

**Picking only the cheapest pool:** cheap pools may lack capacity or suffer frequent interruptions. Measure cost per completed outcome and consider capacity-optimized.

**Using only a single instance type/AZ:** leaves the fleet dependent on a narrow pool. Diversify across compatible hardware groups.

**Running the entire fleet on Spot:** a wave of reclamations can wipe out capacity simultaneously. Maintain an on-demand baseline or appropriate fallback.

**Setting a PDB and assuming nodes cannot be reclaimed:** PDBs do not block abrupt provider shutdowns. Use replicas, drain handlers, and recovery.

**Doing overly long checkpoints in the shutdown hook:** remaining time may expire before saving completes. Checkpoint periodically and bound shutdown duration.

**Not testing capacity shortages:** the autoscaler may fail to find Spot pools. Implement fallback, queue buffering, and backlog limits.

**Comparing only hourly prices:** ignores retries, checkpoints, and lost work. Measure cost per successful unit of work.

## 16. Spot / Preemptible Deployment Checklist

- [ ] Read interruption, notice, runtime limit, and billing policies for the exact service.
- [ ] Workload can be retried, checkpointed, or safely replaced.
- [ ] State and outputs are stored outside the reclaimable instance.
- [ ] Jobs/messages have idempotency keys or deduplication mechanisms.
- [ ] Workers have heartbeats/leases and the scheduler detects lost machines.
- [ ] Handler stops accepting new work upon receiving an interruption notice.
- [ ] System remains correct under sudden machine loss without notice.
- [ ] Checkpoints are written atomically, verified, and versioned.
- [ ] Fleet diversifies instance types and AZs within compatible bounds.
- [ ] On-demand baseline or fallback is configured per SLO and budget.
- [ ] Autoscaler distinguishes requested capacity, warming-up capacity, and healthy capacity.
- [ ] Kubernetes Spot nodes have appropriate taints/labels, termination handlers, and drain policies.
- [ ] PDBs are scoped properly and not treated as guarantees against forced eviction.
- [ ] Metrics cover interruptions, checkpoints, retries, backlog, and cost per completed unit.
- [ ] Tested mid-task interruptions, mid-checkpoint interruptions, and sudden machine loss.
- [ ] Credentials, volumes, snapshots, and temporary data are protected when instances terminate.
- [ ] Cost caps and alerts are set for elevated on-demand fallback.

Spot, preemptible, and interruptible compute let you leverage spare capacity at lower cost, in exchange for workloads accepting that machines can be reclaimed. Use them for work that can be split, retried, or resumed from checkpoints; persist state in durable systems and ensure idempotent operations. Combining Spot with on-demand capacity, diversifying pools, and measuring cost per completed outcome will help reduce costs while preserving resilience when capacity is disrupted.
