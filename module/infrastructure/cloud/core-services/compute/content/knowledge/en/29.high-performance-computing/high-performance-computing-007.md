# Checkpointing and Recovering Long-Running Jobs

## Lesson Objectives

High-Performance Computing (HPC) workloads frequently run for hours or days, processing massive datasets, running numerical simulations, training models, or executing distributed computations across many nodes. A hardware fault, dropped node connection, job wall-time expiration, Spot instance reclamation, or killed process can wipe out hours of computation if the application does not persist intermediate state.

A checkpoint is a saved state snapshot sufficient for a job to resume from a previously completed point. Recovery is the workflow of verifying checkpoints, restoring the execution environment, and resuming computation after an interruption. Together, these mechanisms minimize recomputed work, shorten recovery time, and control costs for long-running workloads.

After this lesson, you will be able to:

- Distinguish checkpoints, snapshots, backups, and intermediate outputs.
- Identify the state required to resume a job with accurate results.
- Choose between synchronous, asynchronous, full, and incremental checkpointing.
- Calculate checkpoint intervals based on storage cost and failure probability.
- Design consistent checkpoints for distributed and MPI applications.
- Choose suitable filesystems, block storage, object storage, and local scratch.
- Coordinate checkpoints with schedulers, wall time, preemption, and shutdown signals.
- Recover jobs from verified checkpoints while avoiding overwriting known-good data.
- Monitor checkpoint overhead, recovery time, and lost compute work.

## 1. Why Do Long-Running Jobs Need Checkpoints?

An HPC job typically executes a sequence of dependent steps. Each step consumes CPU/GPU, memory, network, and I/O. If a job stops at step 95 out of 100 without a checkpoint, the system may have to restart from step 1.

Common causes of interruption:

- Node or host hardware failure.
- Kernel, OS, or container runtime crash.
- Job hitting the scheduler wall-time limit.
- Cloud capacity reclamation or Spot instance interruption.
- Process OOM kill or exceeding resource limits.
- Network partition isolating part of the nodes in a distributed job.
- Operator stopping a job for maintenance or upgrades.
- Application, library, driver, or input data errors.
- Job preemption to yield resources to a higher-priority workload.

Not every failure comes with advance notice. Consequently, applications should never rely solely on shutdown hooks right before termination. Periodic checkpoints and checkpoints at work boundaries limit damage when processes vanish abruptly.

### 1.1. Checkpoints Reduce Lost Compute Time

Suppose a simulation runs for 12 hours and saves a checkpoint every 30 minutes. If a random failure strikes, the amount of work to recompute is far smaller than running without checkpoints. In return, each checkpoint consumes data write time, I/O, and may briefly pause workers.

Checkpointing must balance three goals:

- Minimize compute work lost after a failure.
- Keep checkpointing overhead at an acceptable level.
- Ensure checkpoints are consistent and durable enough to restore cleanly.

A checkpoint written quickly yet inconsistently can be useless. A complete checkpoint that takes too long to write erodes overall throughput.

## 2. Distinguishing Checkpoints, Snapshots, Backups, and Outputs

These terms are related but serve distinct purposes.

| Concept | Purpose | Typical contents |
|---|---|---|
| Checkpoint | Resume a running job | Compute state, iteration, application memory, RNG, offsets |
| Snapshot | Capture the state of a resource at a point in time | Disk, volume, VM, or filesystem |
| Backup | Protect data for restoration after loss or corruption | Data copies, metadata, and history |
| Intermediate output | Interim results of a step | Output files, partitions, tensors, or artifacts |
| Final output | Completed results of the job | Reports, models, processed datasets |

A VM or volume snapshot is not necessarily an application checkpoint. If a snapshot is taken while multiple processes are mid-write, it may only be crash-consistent. Distributed applications often require a logical synchronization point across nodes.

Nor does a backup automatically allow resuming computation from the exact iteration. A backup restores bytes, whereas the application must know how to read and interpret state.

### 2.1. A Checkpoint Must Answer Recovery Questions

A useful checkpoint must identify:

- Which step or iteration the job is at?
- Which inputs have already been processed?
- Which state has been committed?
- Which code and schema versions produced the checkpoint?
- How many workers/ranks exist and how is data partitioned?
- Which files belong to the same checkpoint generation?
- Can completeness of the checkpoint be verified?
- Can the job resume with a different node count or resource configuration?

Without this metadata, an operator risks restoring mismatched files, reprocessing committed data, or combining states from different points in time.

## 3. Identifying What State to Save

A checkpoint does not necessarily dump a process's entire RAM. Save the state sufficient for the application to reconstruct logical state and resume computation accurately.

Common components:

| Component | Examples |
|---|---|
| Progress | Iteration, timestep, batch index, task ID |
| Application state | Matrices, vectors, solver state, data structures |
| Input position | File offset, partition, cursor, sequence number |
| Random state | Seeds and CPU/GPU RNG states |
| Distributed state | Rank, world size, shards, partition map |
| ML training state | Model, optimizer, scheduler, gradient scaler |
| Data pipeline | Sampler state, dataloader position, shuffle state |
| Output commit | List of completed outputs, checksums, and manifest |
| Compatibility metadata | App version, schema version, library/runtime version |

Not every application needs every field. Determine required state from the algorithm and reproducibility requirements.

### 3.1. Essential State vs. Derived Data

Distinguish data mandatory for resuming from data that can be recomputed:

- **Essential state:** losing it makes accurate resumption from the checkpoint impossible.
- **Derived state:** can be recomputed from inputs and essential state.
- **Cache:** speeds execution but does not determine correctness.
- **Temporary state:** scratch files or uncommitted buffers.

You can omit caches to shrink checkpoint size, but factor cache rebuild time into recovery time. For workloads relying on huge caches, post-recovery warmup can be substantial.

### 3.2. Checkpoint Boundaries

Pick boundaries where state is consistent and recoverable:

- After finishing a simulation timestep.
- After a committed batch of data.
- After an epoch or optimizer step in training.
- After finishing processing a partition.
- After all ranks finish a collective phase.
- After intermediate outputs are durably written.

Never save state mid-transaction or mid-collective unless the application has an explicit mechanism to recover in-flight operations.

## 4. Checkpointing Strategies

### 4.1. Full Checkpoint

A full checkpoint saves all required state at a generation.

Advantages:

- Simple to reason about and restore.
- No need to chain multiple generations.
- Easy to verify integrity.
- Minimal dependency on earlier checkpoint history.

Disadvantages:

- Large storage footprint.
- Potentially long write times.
- Heavy I/O and storage costs.
- Can spike network traffic when many nodes write concurrently.

Full checkpoints fit when state size is moderate, simple recovery outweighs write cost, or write duration fits within budget.

### 4.2. Incremental Checkpoint

An incremental checkpoint saves only state modified since the previous checkpoint or a base generation.

Advantages:

- Shrinks bytes written.
- Allows higher checkpoint frequency.
- Cuts network/storage I/O when delta changes are small.

Disadvantages:

- Recovery must merge the base and deltas.
- One corrupted delta can invalidate subsequent generations.
- Complex retention and compaction management.
- Requires strict ordering and dependency tracking across generations.

Keeping periodic full checkpoints alongside a bounded chain of deltas helps control recovery time. Periodically create a new base so recovery never replays too many deltas.

### 4.3. Synchronous Checkpoint

In synchronous checkpointing, workers pause or wait at a safe point until checkpoint data finishes writing.

The advantage is straightforward confirmation that the checkpoint is durable before proceeding. The drawback is that I/O time directly subtracts from productive compute time.

For distributed jobs, synchronous checkpointing typically requires coordination across ranks so everyone saves state at the same logical step.

### 4.4. Asynchronous Checkpoint

Asynchronous checkpointing lets the application continue computing while state is persisted in the background.

Copy-on-write, snapshot buffers, or double buffering can capture a consistent state snapshot without stalling the whole application for long.

Benefits:

- Reduces application-visible pause time.
- Overlaps I/O with compute.
- Raises overall throughput when storage has sufficient bandwidth.

Risks:

- Source state may mutate while the background writer is flushing.
- Extra buffers consume RAM.
- Background I/O can contend for CPU, memory bandwidth, and storage.
- The job may fail before the asynchronous checkpoint completes.

Only mark a generation committed after all data is written and verified. Never treat initiating a background write as a safe checkpoint.

## 5. Choosing the Checkpoint Interval

Checkpointing too often inflates overhead. Checkpointing too rarely inflates work lost when failures happen.

Factors governing the interval:

- Time required to write one checkpoint.
- Mean time between failures (MTBF) or observed interruption rate.
- Cost to recompute lost work.
- Remaining wall time.
- Storage capacity and bandwidth.
- Availability of asynchronous checkpointing.
- Maximum acceptable work loss.

### 5.1. Simple Overhead Model

Suppose:

- C is the time to write one checkpoint.
- M is the mean time between failures.
- T is the interval between consecutive checkpoints.
- Each failure loses on average roughly T/2 of work since the latest checkpoint.
- C is much smaller than T and M.

Approximate time-fraction overhead can be modeled as:

~~~text
Overhead(T) ≈ C / T + T / (2 * M)
~~~

The `C/T` term represents time spent writing checkpoints; `T/(2*M)` represents expected work lost to random failures under this simplified model.

Taking the derivative and minimizing yields the approximate optimal interval:

~~~text
T_opt ≈ sqrt(2 * C * M)
~~~

This formula is an initial estimation model, not a mandatory configuration value. It assumes randomly distributed failures and relatively stable checkpoint times, and does not fully capture restart time, recovery overhead, contention, or correlated failures.

### 5.2. Interval Calculation Example

Suppose writing a checkpoint takes 2 minutes and the mean time between failures is estimated at 20 hours.

Convert units to minutes:

- C = 2 minutes.
- M = 20 × 60 = 1,200 minutes.

~~~text
T_opt ≈ sqrt(2 * 2 * 1200)
      ≈ sqrt(4800)
      ≈ 69.3 minutes
~~~

Roughly 69 minutes serves as a starting point for testing. If a job has hard deadlines, interruptions cluster around maintenance windows or Spot notices, or checkpoint write times fluctuate with storage load, adjust using real telemetry.

### 5.3. Setting an RPO Limit

Recovery Point Objective (RPO) is the maximum amount of work or data loss acceptable when a failure occurs.

If policy prohibits losing more than 15 minutes of computation, the checkpoint interval must be short enough to meet that RPO, factoring in failed checkpoints and durable commit time. A new checkpoint only counts as a recovery point after commit finishes.

RPO is not just the scheduled interval. If the latest checkpoint is corrupted or incompatible, the actual recovery point falls back one or more generations.

### 5.4. Measure Instead of Relying Only on Formulas

Record:

- Checkpoint start and completion timestamps.
- Bytes written and storage throughput.
- Application pause duration.
- Checkpoint success rate.
- Recovery duration per generation.
- Compute minutes lost after failures.
- Failure/interruption counts by workload type.

Test several intervals and compare useful throughput, total runtime, and cost per completed job. For fluctuating workloads, use adaptive intervals driven by state size, storage load, or remaining wall time.

## 6. Creating Consistent, Atomic Checkpoints

A checkpoint must never be published as valid when only part of its files have been written. If a process dies mid-write, recovery might read partial files and corrupt state.

A safe workflow:

1. Pick a unique logical checkpoint ID or generation.
2. Capture state at a consistent boundary.
3. Write parts to a temporary location or a new generation prefix.
4. Flush data and complete all writes.
5. Compute checksums and sizes for every file.
6. Read/verify required metadata.
7. Write a manifest describing all files, versions, and the checkpoint step.
8. Only after every part succeeds, publish the generation as committed.
9. Retain the previous generation until the new generation is verified.

### 6.1. POSIX Filesystems

On POSIX filesystems, a common pattern writes a temporary file within the same filesystem, flushes data, and renames it to the canonical path. Same-filesystem rename typically provides atomicity at the directory-entry level, though crash durability also depends on `fsync` of both the file and parent directory as well as filesystem semantics.

Pseudo-code:

~~~python
write(temp_path, checkpoint_bytes)
flush_and_fsync(temp_path)
verify_checksum(temp_path)
atomic_rename(temp_path, committed_path)
fsync_parent_directory(committed_path)
~~~

These functions are pseudo-code illustrating operation order. On HPC parallel filesystems, verify actual client, metadata server, and cache semantics; never assume every rename/`fsync` behaves identically across all filesystems.

### 6.2. Object Storage

Object storage typically provides PUT object operations without POSIX atomic rename semantics. Never emulate rename with copy-then-delete and assume it is transactional.

A suitable pattern:

1. Write each generation under a unique prefix.
2. Use immutable object keys per rank/file.
3. Verify checksums, sizes, and metadata.
4. Write the complete manifest last.
5. Update a `latest` pointer using conditional writes or versioning if supported by the service.
6. During recovery, select only generations with a committed manifest where all required objects exist.

Example layout:

~~~text
checkpoints/
  job-4821/
    generation-000120/
      rank-0000.bin
      rank-0001.bin
      rank-0002.bin
      manifest.json
    generation-000121/
      rank-0000.bin
      rank-0001.bin
      manifest.json
    latest.json
~~~

The manifest must record checkpoint step, rank count, object names, checksums, sizes, app version, and schema version. The `latest` pointer must only reference committed generations.

### 6.3. Manifest as the Commit Point

The manifest is proof that a generation finished cleanly. Never create the manifest before every checkpoint file finishes writing.

If a job terminates before the manifest is written, that generation is treated as incomplete and skipped by recovery. If the manifest exists yet an object is missing or fails checksum verification, the generation is invalid and recovery must fall back to an earlier checkpoint.

This avoids mistakenly picking the newest checkpoint solely by directory name or timestamp.

## 7. Checkpointing Distributed and MPI Applications

An MPI job typically has many concurrent ranks exchanging messages. Rank states depend on one another. If each rank checkpoints at a different point without coordination, recovery can assemble incompatible states.

### 7.1. Coordinated Checkpointing

Coordinated checkpointing establishes a shared logical recovery point:

1. Coordinate ranks to advance to a checkpoint boundary.
2. Quiesce or synchronize necessary operations.
3. Ensure in-flight collectives/messages reach a safe state.
4. Each rank writes its own state.
5. Gather completion status and verify all ranks succeeded.
6. Write a shared manifest for the generation.
7. Allow the job to resume execution.

A barrier helps synchronize ranks, but a barrier alone does not guarantee all communication state is saved consistently. The application must clearly define which messages are processed, which remain pending, and which state belongs to the same logical step.

### 7.2. Uncoordinated Checkpointing

Uncoordinated checkpointing allows each rank to save independently. This reduces synchronization wait times, but complicates recovery because inconsistent global states, orphan messages, or cross-rank dependencies can arise.

Techniques such as message logging or specialized protocols address some issues at the cost of higher complexity and overhead. For most standard MPI applications, coordinated checkpointing is easier to design and test.

### 7.3. Distributed Manifests

A shared manifest should record:

- Job ID and checkpoint generation.
- Logical timestep/iteration.
- Rank count and rank-to-file mapping.
- Node/rank topology if needed.
- Checksum and size of each file.
- Application build/version.
- MPI/library version if it affects compatibility.
- Schema version.
- Checkpoint timestamp and commit status.

If recovery changes rank count, the application must support state repartitioning or remapping. Never assume a checkpoint written with 128 ranks can restore cleanly onto 64 ranks.

## 8. Checkpointing Machine Learning Training

Long-running training workloads usually need to save far more than model weights. Saving weights alone allows training to continue from the current model, yet resets the optimizer and learning-rate schedule, altering the training trajectory.

A training checkpoint typically includes:

- Model parameters and buffers.
- Optimizer state, such as momentum or Adam moments.
- Learning rate scheduler state.
- Gradient scaler state when using mixed precision.
- Global step, epoch, and batch position.
- Random states for Python, framework, CPU, and GPU.
- Dataset sampler/shuffle state.
- Distributed rank state or shard metadata.
- Model, optimizer, and training run configurations.
- Code, framework, and schema versions.

### 8.1. Optimizer Step Boundaries

Checkpoint at complete optimizer step boundaries, after gradient accumulation and the optimizer update finish. Saving mid-accumulation without persisting full gradient buffers and associated state causes resumed training to diverge from uninterrupted runs.

With distributed data parallel training, each rank may need to save local state or use sharded checkpointing. Ensure all ranks belong to the exact same training step before publishing the generation.

### 8.2. Conceptual PyTorch Example

~~~python
checkpoint = {
    "step": global_step,
    "model": model.state_dict(),
    "optimizer": optimizer.state_dict(),
    "scheduler": scheduler.state_dict(),
    "rng_cpu": torch.get_rng_state(),
    "rng_cuda": torch.cuda.get_rng_state_all(),
    "config": training_config,
}

save_to_temporary_location(checkpoint)
verify_and_publish_checkpoint()
~~~

This is a conceptual example. In distributed or sharded training environments, each rank may need to save its own state slice, synchronize completion, and use framework-specific checkpoint APIs. Never gather all state onto one process if doing so exhausts RAM or network capacity.

### 8.3. Data Loaders and Reproducibility

To resume accurately, the job must know what the next batch is. If a sampler shuffles randomly, saving only epoch and batch index is insufficient; save RNG/sampler state or use a deterministic way to reconstruct data ordering.

For streaming or sharded datasets, save partition and offset. Upon recovery, avoid reprocessing already committed batches or skipping unprocessed batches.

## 9. Choosing Where to Store Checkpoints

Storage location directly dictates write time, survival across node failures, and cost.

| Storage | Advantages | Limits/considerations |
|---|---|---|
| Local NVMe/SSD | Fast I/O, low latency | Can be lost if node fails or is reclaimed |
| Network block volume | Can survive independently of VM | Bounded IOPS/throughput and zone attachment |
| HPC parallel filesystem | High throughput for many nodes/ranks | Metadata and bandwidth contention when many jobs write concurrently |
| Shared POSIX filesystem | Easy for file-based apps | Performance depends on backend, locking, and metadata |
| Object storage | Durable, scalable, well-suited for generations | Higher latency, API semantics differ from filesystems |
| Database/metadata store | Suitable for manifests and small state | Unsuitable for massive checkpoint payloads |

### 9.1. Hierarchical Checkpointing

Multiple tiers can be combined:

- Flush quickly to local NVMe or memory snapshots to minimize application pauses.
- Replicate asynchronously to a parallel filesystem or object storage.
- Mark as durable only once the copy on the durable tier is verified.

If a node dies before durable replication finishes, the local checkpoint can be lost. Therefore, treat the local tier strictly as a cache or staging buffer; calculate RPO only against generations committed on storage surviving the target failure domain.

### 9.2. Parallel Filesystems and Write Contention

Many ranks concurrently writing small files can overload the metadata server. Ways to relieve pressure:

- Aggregate state into larger files per rank group.
- Use aggregator ranks or I/O nodes.
- Tune concurrent writer counts.
- Write in large, reasonably sequential chunks.
- Avoid creating millions of small files.
- Test at production-equivalent concurrency.

Aggregators reduce file counts but can become a bottleneck or single point of failure. Measure throughput and fault tolerance along the write path.

### 9.3. Object Storage and Multipart Uploads

For large checkpoints, multipart uploads boost throughput and allow per-part retries. Publish the manifest only after multipart upload completion and checksum validation.

Clean up incomplete uploads to prevent orphaned part accumulation and billing waste. Lifecycle policies can purge stale incomplete multipart uploads, provided they never delete a generation currently being written.

## 10. Protecting Integrity and Compatibility

Checkpoints can outlive the application version that wrote them. When code, schemas, or libraries change, older files may fail to load or load incorrectly.

Each generation should store:

- Checkpoint schema version.
- Application version/build ID.
- Required library/runtime versions.
- Model/config version.
- Architecture or precision mode if it affects binary format.
- Endianness/serialization metadata if format-dependent.
- Checksums for every file and the manifest.

### 10.1. Checksums and Validation

Before resuming:

1. Verify the manifest exists and has committed status.
2. Verify all required files exist.
3. Compare file sizes against the manifest.
4. Verify checksums.
5. Verify schema and application versions.
6. Verify rank/shard counts and mappings.
7. Run content validation if the application has invariants.
8. Begin compute only after every check passes.

Checksums detect byte corruption, not logical state bugs. Range checks, conservation laws, model tensor shape checks, or business invariants may also be needed.

### 10.2. Schema Migration

If an older checkpoint is incompatible with the new application, three options exist:

- Resume using the exact application version that created the checkpoint.
- Convert the checkpoint using a versioned, tested migration tool.
- Start a fresh job from canonical inputs if safe conversion is impossible.

Never mutate the only copy of a checkpoint in place. Keep the original, produce a migrated generation, and record the source/version mapping.

## 11. Recovering a Job from a Checkpoint

Recovery requires a clear sequence. Restoring the wrong generation or launching two concurrent instances of the same job can duplicate outputs and break consistency.

A workflow:

1. Identify the stopped job and root cause.
2. Inspect scheduler state and confirm old processes no longer hold resources.
3. Locate the newest committed checkpoint generation.
4. Verify the manifest, checksums, and compatibility.
5. Identify required inputs, configs, and application version.
6. Allocate appropriate resources for the new job.
7. Read the checkpoint and restore state.
8. Verify logical step, partitions, rank mapping, and committed outputs.
9. Resume from the next incomplete step.
10. Write and verify a new checkpoint generation.
11. Confirm final outputs and update job status.

~~~mermaid
flowchart TD
    A["Job stopped / node lost"] --> B["Confirm old job terminated"]
    B --> C["Find committed checkpoint"]
    C --> D["Verify manifest, checksum, version"]
    D --> E{"Checkpoint valid?"}
    E -->|No| F["Fall back to previous generation"]
    F --> D
    E -->|Yes| G["Allocate resources and restore state"]
    G --> H["Check committed inputs/outputs"]
    H --> I["Resume from next logical step"]
    I --> J["Write new checkpoint generation"]
    J --> K["Complete and verify outputs"]
~~~

### 11.1. Selecting the Latest Valid Generation

Never pick purely by largest directory name or newest timestamp. Pick the generation with a committed manifest, all files present, valid checksums, and compatible schema.

If the newest generation is corrupt, fall back to the previous valid generation. Record the amount of recomputed work and why the corrupt generation was rejected.

### 11.2. Preventing Two Jobs from Writing the Same Output

When a job is requeued, ensure the old instance/job is no longer writing outputs. Use leases, fencing tokens, or scheduler ownership checks to prevent two executions from updating the same output concurrently.

A restarted job should receive a new execution ID while keeping its logical job ID and checkpoint lineage. Output commits must distinguish attempts and generations.

## 12. Output Commit and Exactly-Once Effects

State checkpointing is insufficient if external outputs were written before the checkpoint was updated. For example, a worker writes results to a database and crashes before updating the checkpoint. Upon resume, the worker might write the results again.

A safe pattern:

1. Write outputs to a staging path scoped to job/step.
2. Verify output completeness.
3. Commit outputs via a manifest or transaction.
4. Update the checkpoint/processed marker in the same logical transaction if possible.
5. During recovery, read the manifest to skip already committed steps.
6. Use idempotency keys or unique keys for external side effects.

For object storage, use immutable keys scoped by job ID, step, and generation. Publish the manifest after all objects finish. For databases, use transactions or unique constraints. Never infer committed outputs from filenames alone.

End-to-end exactly-once processing usually requires transactional design and idempotency on every side effect. A checkpoint alone does not guarantee exactly-once behavior.

## 13. Coordinating Checkpoints with Schedulers and Wall Time

HPC schedulers typically allocate resources for a bounded wall time. Jobs may be killed at the limit even while computing cleanly.

Checkpointing plans must factor in:

- Remaining time before the wall-time limit.
- p95/p99 checkpoint write duration.
- Shutdown and flush time.
- Warning signal lead time from the scheduler.
- Buffer time for slow nodes or heavy filesystem load.
- Scheduler requeue/preemption policies.

Never wait until the final seconds to start checkpointing. If a checkpoint takes longer than remaining wall time, the job will be killed mid-write.

### 13.1. Pre-Termination Warning Signals

Some schedulers can send a signal prior to wall-time expiration. In Slurm, you can configure a warning signal ahead of the limit:

~~~bash
#!/bin/bash
#SBATCH --job-name=long-simulation
#SBATCH --time=08:00:00
#SBATCH --signal=USR1@300

srun ./solver --resume-from latest
~~~

This example requests `USR1` 300 seconds before the time limit. The solver application needs a signal handler or control hook to trigger checkpointing and exit gracefully. Verify signal configuration and propagation to job steps against your cluster's Slurm version and policy.

Never perform complex I/O or call non-async-signal-safe functions directly inside a low-level signal handler. The handler should set a flag or wake an event loop; the main thread executes the checkpoint at a safe point.

### 13.2. Requeue

Some schedulers allow requeuing a job after preemption or when configured to do so. Requeuing does not automatically restore application state. Your script or workflow must locate a valid checkpoint and pass the proper resume arguments.

Prevent infinite requeue loops when a checkpoint is corrupted or the job fails deterministically at the same step. Track attempt counts, cap restarts, and transition the job to an investigation state once the threshold is exceeded.

### 13.3. Cloud Spot Interruptions

If an HPC job runs on cloud Spot/preemptible VMs, an interruption notice gives only a brief window to shut down. You should:

- Listen for notices via the provider's mechanism.
- Stop accepting new tasks or pause launching work.
- Trigger a checkpoint if enough time remains.
- Prioritize writing checkpoints to durable external storage.
- Avoid relying on local ephemeral disks.
- Prepare replacement capacity and resume workflows.

If time is insufficient, abandon the incomplete new checkpoint and recover from the latest committed generation. Never publish a partial checkpoint trying to squeeze out the last few seconds.

## 14. Recovering Distributed Jobs

For multi-node jobs, recovery must provision compatible resources and restore all ranks/shards belonging to the same generation.

Questions to resolve:

- Must the node/rank count remain identical?
- Can placement or network topology change?
- Is any state tied to an old node's local disk?
- Is the MPI implementation compatible with checkpointing?
- Do communicators and collective states need to be rebuilt?
- Are input datasets still at the exact same version?
- Were all rank checkpoints committed under the same generation?

### 14.1. Restarting with the Same Topology

Restoring with the same rank count and mapping is simpler when checkpoints hold per-rank state. Verify new nodes share the required architecture, runtime, libraries, and filesystem paths.

### 14.2. Restarting with a Different Topology

If rank counts change, the application must support state repartitioning. For example, a matrix partitioned row-wise across 16 ranks must be re-sharded when resuming on 8 ranks.

Some frameworks support resharding or elastic training; many MPI solvers do not. Never just alter the scheduler task count and expect the binary to restore cleanly.

### 14.3. Partial Node Failures

When one rank fails, remaining ranks may hang in collective operations or lose communicator validity. Without fault-tolerant MPI support, you usually must terminate the entire job step and restart from a global checkpoint.

Only keep surviving ranks running when the runtime, communication library, and application implement an explicitly designed recovery protocol.

## 15. Optimizing Checkpoints for GPUs and Large Workloads

GPU checkpoints may hold model weights, optimizer states, activations, or simulation arrays. Large sizes increase GPU-to-host copy times and storage write times.

Optimization strategies:

- Save only state necessary to resume.
- Write at safe iteration/step boundaries.
- Use asynchronous copies when supported by the framework while ensuring a consistent snapshot.
- Use sharded checkpoints to avoid funneling all state through one node.
- Tune concurrent writer count and chunk size.
- Compress only if I/O savings outweigh CPU/GPU cost.
- Use incremental checkpoints when state changes slowly.
- Measure contention against training/inference and network collectives.

Compression shrinks transfer volume yet consumes CPU and extends time until the checkpoint is durable. On GPU jobs, CPU-side compression can starve data loaders or communication threads. Benchmark end-to-end rather than measuring compression speed alone.

### 15.1. RAM Snapshots and Process-Level Checkpointing

Some technologies snapshot raw memory/process state to restore processes nearly verbatim. This differs from application-level checkpointing.

Process-level checkpointing depends heavily on kernel, runtime, drivers, file descriptors, network sockets, GPU state, and host configuration. It may be incompatible across different nodes or software versions.

Application-level checkpoints are usually far more portable across nodes and versions because they store logical state, though they require application serialization/resume support. Choose based on portability needs and application control.

## 16. Security and Checkpoint Lifecycle Management

Checkpoints may contain input data, model weights, user data, internal state, or sensitive datasets. Protect them with the same rigor as production data.

Principles:

- Encrypt in transit and at rest.
- Use workload identities with least privilege.
- Separate checkpoint write permissions from delete/retention permissions.
- Never store long-lived secrets in checkpoints if they can be fetched securely on resume.
- Scope read access by job, project, or tenant.
- Log audit trails for create, read, restore, delete, and redrive actions.
- Use checksums to detect tampering or corruption.
- Set retention policies matching recovery value and compliance mandates.
- Purge old checkpoints per policy while preserving generations needed for rollback.
- Protect manifests from unauthorized edits or redirection to untrusted objects.

Never write access tokens or short-lived credentials into checkpoints. Re-issue credentials under the new execution's identity on resume.

### 16.1. Retention and Cleanup

Keeping too few checkpoints risks losing recovery options if the newest generation is corrupt. Keeping too many inflates storage costs and keeps sensitive data around longer than necessary.

A retention policy might retain:

- The latest verified generation.
- One or several prior generations for rollback.
- Periodic full checkpoints as bases.
- Deltas required to restore from those bases.
- Checkpoints placed under retention lock if required for audits.

Delete old generations only after verifying the new generation and confirming dependency chains remain intact. With incremental checkpoints, never delete a base while deltas still depend on it.

## 17. Monitoring Checkpoint and Recovery Effectiveness

Monitor checkpointing at the job, node, rank, and storage levels.

| Metric | Meaning |
|---|---|
| checkpoint_duration_seconds | Time taken to create one checkpoint |
| checkpoint_bytes_written | Bytes written per generation |
| checkpoint_success_total | Count of completed checkpoints |
| checkpoint_failure_total | Count of failed checkpoints |
| checkpoint_pause_seconds | Duration the application paused to save |
| checkpoint_age_seconds | Age of the latest committed generation |
| checkpoint_validation_failures | Count of generations failing validation |
| recovery_duration_seconds | Time from restore start until execution resumes |
| recovery_success_total | Count of successful recoveries |
| lost_compute_seconds | Compute time that had to be rerun |
| job_restart_count | Number of times a job restarted |
| storage_throughput_bytes_per_second | Checkpoint write/read throughput |
| checkpoint_overhead_ratio | Ratio of checkpoint time to total runtime |

### 17.1. SLO Indicators

Targets you can set:

- RPO: maximum acceptable compute loss.
- RTO: maximum time from failure detection until the job resumes.
- Checkpoint success rate: percentage of checkpoints committed cleanly.
- Recovery success rate: percentage of jobs resuming cleanly.
- Maximum checkpoint age: maximum age of a valid checkpoint.
- Checkpoint overhead budget: fraction of runtime spent checkpointing.

Set thresholds by workload class. A scientific simulation might tolerate an RTO of tens of minutes; a near-real-time pipeline may require much faster recovery.

### 17.2. Distinguishing Slow Checkpointing from Slow Recovery

Slow checkpointing usually points to serialization, memory copies, filesystem metadata, or storage throughput.

Slow recovery can stem from:

- Provisioning replacement nodes and GPUs.
- Pulling images/containers.
- Attaching volumes.
- Downloading large checkpoints.
- Decompressing and deserializing.
- Rebuilding communicators or data partitions.
- Warming caches and compiling kernels.

Optimize recovery by measuring every stage, not just checkpoint write times.

## 18. Testing Recovery Capabilities

A checkpoint is only trustworthy once tested end-to-end. A job successfully writing files does not prove it can resume accurately.

Scenarios to test:

1. Job stops cleanly after a checkpoint.
2. Job is killed right before a checkpoint begins.
3. Job is killed mid-write of a file.
4. Job is killed after writing files but before manifest commit.
5. One rank fails to write its checkpoint.
6. A file has a corrupted checksum.
7. A new generation is missing an object.
8. A new application version cannot read an old schema.
9. Node-local scratch vanishes.
10. Job is requeued with a different node or rank count.
11. Scheduler sends a pre-walltime warning signal.
12. Spot interruption triggers mid-compute or mid-checkpoint.
13. Output is committed while the checkpoint was not updated.
14. Two executions attempt to write to the same logical job.

After each test, verify:

- Recovery selects the right generation.
- Incomplete generations are ignored.
- Job resumes from the exact right logical step.
- Outputs are neither missing nor duplicated.
- Distributed state is consistent.
- RPO and RTO meet targets.
- Retry costs and temporary data remain controlled.

### 18.1. Controlled Fault Injection

You can deliberately kill processes, throttle storage, or disconnect a worker in a test environment. Bound the blast radius, use reproducible test data, and confirm no impact on other workloads.

Never destroy the sole copy of a checkpoint or delete production data to test recovery. Clone test environments and verify rollback paths prior to fault injection.

## 19. Long-Running Job Recovery Runbook

A runbook should define owners, stop conditions, and verifiable actions.

### When a Job Stops Unexpectedly

1. Record the job ID, execution ID, scheduler state, and stop timestamp.
2. Confirm old processes are no longer running or writing outputs.
3. Check nodes, filesystems, storage, and failure root cause.
4. Locate the latest committed checkpoint generation.
5. Verify manifest, checksums, schema, and app version.
6. Verify input versions and already committed outputs.
7. Provision suitable resources and placement.
8. Resume from the valid generation.
9. Monitor progress, errors, and the next checkpoint.
10. Reconcile final outputs and record total recovery time.

### When the Latest Checkpoint Is Invalid

- Never overwrite the previous checkpoint.
- Mark the corrupt generation as invalid in metadata/audit logs.
- Fall back to the prior committed generation.
- Calculate the amount of work to recompute.
- Investigate storage errors, checksum mismatches, and writer failures.
- Fix root causes before increasing checkpoint frequency.

### When Recovery Repeatedly Fails

- Halt automatic retries after hitting the threshold.
- Preserve checkpoints and logs for investigation.
- Check compatibility and schema migration.
- Verify rank counts, architecture, and dependencies.
- Attempt restoring a copy inside an isolated environment.
- Resume production only after confirming a valid recovery point.

## 20. Common Mistakes and How to Avoid Them

**Saving only model weights:** optimizer, RNG, sampler, or solver state is lost. Save all state needed to resume.

**Overwriting a known-good checkpoint:** a process killed mid-write destroys the prior recovery point. Use immutable generations and commit manifests last.

**Treating file existence as a complete checkpoint:** files may be truncated or unflushed. Verify checksums, sizes, and manifests.

**Letting MPI ranks write independently without coordination:** states may belong to different logical steps. Use coordinated checkpoints or an explicit recovery protocol.

**Saving only to local disk:** losing the node loses the checkpoint. Replicate to durable storage and commit only after durable persistence completes.

**Checkpointing too frequently:** I/O dominates runtime and creates contention. Measure C, MTBF, and overhead to tune intervals.

**Checkpointing too rarely:** hours of compute are lost on failures. Set an RPO and test interruptions.

**Asynchronous checkpointing without snapshotting state:** the writer reads mutating memory. Use copy-on-write, immutable buffers, or safe points.

**Omitting version/schema metadata:** newer application builds cannot read older checkpoints. Record compatibility metadata and migration paths.

**Resuming with a different topology without repartitioning support:** state is misdistributed. Keep topology fixed or use frameworks supporting resharding.

**Not coordinating outputs and checkpoints:** outputs are duplicated or dropped after recovery. Use commit manifests, transactions, and idempotency.

**Assuming scheduler requeue auto-recovers state:** requeue simply restarts the job; the application must load the checkpoint and resume.

**Never testing restores:** checkpoint files exist on disk yet fail to restore. Run periodic recovery drills.

## 21. Checkpointing and Recovery Checklist

- [ ] Defined failure model and RPO/RTO targets.
- [ ] Cataloged essential state, derived state, and committed outputs.
- [ ] Checkpoints are taken at logical safe points.
- [ ] Checkpoint interval is derived from measured write time, MTBF, and overhead.
- [ ] Clear full checkpoint or base generation and incremental policy exists.
- [ ] Asynchronous checkpoints capture consistent snapshots.
- [ ] Generations use unique IDs and commit manifests last.
- [ ] Every file includes size/checksum and schema/application versions.
- [ ] Checkpoints persist durably outside local ephemeral storage.
- [ ] Distributed ranks synchronize and are recorded in a shared manifest.
- [ ] ML training saves optimizer, scheduler, RNG, and sampler state as needed.
- [ ] Scheduler warning signals and wall-time budgets are factored in.
- [ ] Requeues cannot spawn two concurrent executions writing to one logical job.
- [ ] Recovery selects the latest valid committed generation.
- [ ] Outputs use commit markers or idempotency to prevent duplicates.
- [ ] Credentials are re-issued on resume; no long-lived secrets sit inside checkpoints.
- [ ] Retention preserves enough generations for rollback and cleanup never deletes active bases.
- [ ] Dashboards track checkpoint age, duration, failures, recovery time, and lost compute.
- [ ] Tested mid-write crashes, bad checksums, missing files, and sudden node loss.
- [ ] Runbook and owners exist for failed job recovery.

Checkpointing turns a long-running job into recoverable segments, but only works when state is saved consistently, durably, and verifiably. Choose proper safe points, tune intervals around write cost and failure risk, commit generations via manifests after all data lands, and validate compatibility before resuming. Combining checkpoints with scheduler signals, suitable storage, idempotent outputs, and recovery drills lets HPC workloads survive failures without rerunning entire jobs or corrupting results.
