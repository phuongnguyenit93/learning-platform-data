# Handling Interruption Signals and Bounded Shutdown Time

Compute can be reclaimed when the provider needs to recover capacity, when an operations team scales in, when a node undergoes maintenance, or when an orchestrator replaces workloads. With Spot/preemptible VMs and certain types of interruptible compute, applications sometimes receive a notice before the resource is stopped. This window is usually short and depends on the provider, resource type, and reclamation reason.

The application must turn that notice into a deadline-driven workflow: stop accepting new work, preserve critical progress, finish operations that can safely complete, release leases or locks, and exit before the platform terminates the instance. If there is not enough time, the workload must stop at a consistent boundary so another instance can resume.

This lesson belongs to the **CLOUD_CORE_SERVICES_COMPUTE** module, **Interruptible Compute** chapter. It focuses on receiving and handling interruption signals, managing bounded shutdown time, coordinating with queues/orchestrators/OS, preserving data, and testing reclamation scenarios.

## 1. Why Handle Interruption Notices?

With interruptible compute, an instance surviving through an entire session is not guaranteed. The provider may need to reclaim resources to serve other demand or perform infrastructure operations. A workload running on that machine can be stopped while processing a request, message, or batch job.

If the application is unprepared:

- Running jobs can lose all progress.
- Received but incomplete messages can get stuck or be processed repeatedly.
- Transactions can end up in an indeterminate state for clients.
- Unflushed buffers can cause data loss.
- A new instance can start without knowing how far the old work progressed.
- Prolonged shutdowns can exceed the deadline and result in forced termination.

An interruption notice gives the application an opportunity to preserve progress. However, a notice is not a guarantee that the application will always have enough time or always receive the event. Design must leverage notices when available while still recovering from sudden machine loss.

### 1.1. Common Sources of Interruption

| Source | Example | Characteristics |
|---|---|---|
| Capacity reclaim | Spot/preemptible VM reclaimed | Advance notice may exist, but window and delivery vary |
| Scale-in | Autoscaling reduces instance count | Lifecycle hooks or drain time may exist |
| Rolling update | Orchestrator replaces instance/Pod | Typically has termination workflow and grace period |
| Scheduled maintenance | Host or platform requires maintenance | Schedule/events may exist, depending on service |
| Operator action | Operator stops or deletes machine | Can coordinate proactively, but still needs a deadline |
| Host failure | Physical machine or process fails abruptly | May have no useful notice |

Do not treat every stop scenario as a Spot eviction. Each source can have different advance warning, reliability, and acknowledgement mechanisms.

### 1.2. Notice, Signal, and Termination

Three events must be distinguished:

- **Interruption notice:** notification from the cloud/provider that the resource may soon be reclaimed or change state.
- **Shutdown signal:** signal sent to the process or service, such as SIGTERM on Linux or service stop control on Windows.
- **Forced termination:** the platform kills the process/VM when the deadline expires or when a sudden failure occurs.

A notice is usually an opportunity to start preparing early. A signal instructs the process to enter the stop workflow. Forced termination may give the application no chance to clean up.

## 2. Understanding the Signal Path

An interruption signal can be detected at multiple layers:

1. The cloud provider generates an event or interruption notice.
2. A provider agent, metadata endpoint, event bus, or API forwards the information to the workload/control plane.
3. The workload management component instructs the instance to stop accepting new work.
4. The orchestrator or OS sends a stop signal to the process.
5. The application executes a deadline-bounded shutdown workflow.
6. The platform terminates the instance when the application exits or when the allowed time expires.

~~~mermaid
sequenceDiagram
    participant C as Cloud Provider
    participant E as Event / Metadata / Agent
    participant O as Orchestrator / Lifecycle Manager
    participant A as Application
    participant Q as Queue / Load Balancer
    participant D as Durable Storage
    C->>E: Interruption notice
    E->>O: Resource about to be reclaimed + deadline
    O->>A: ShutdownRequested
    A->>A: Transition to quiescing
    A->>Q: Stop accepting new requests / messages
    Q-->>A: Drain or return lease per protocol
    A->>D: Save checkpoint / commit results
    D-->>A: Confirm durable write
    A->>A: Close connections and exit
    A-->>O: Shutdown complete
    O-->>C: Instance ready to stop
~~~

This diagram shows the general logical flow. On a specific platform, the provider may deliver the notice directly via metadata or an event service; the orchestrator may send SIGTERM; some services do not allow workloads to confirm interruption completion. Implement according to the mechanisms supported by the platform's official documentation.

### 2.1. Notification Channels

Depending on the environment, the application or agent may receive notifications via:

- Instance metadata or VM event endpoint.
- Cloud event service or event bus.
- Notification queue/topic.
- Autoscaling service lifecycle API.
- Kubernetes node/pod events and termination lifecycle.
- SIGTERM/SIGINT or Windows Service Control.
- Provider management agent.

Do not assume all clouds use the same metadata URL, event format, or advance notice window. Isolate provider integration inside a dedicated adapter so business logic does not depend on a specific API.

### 2.2. Polling vs. Event-Driven

**Polling** is when the workload or agent periodically checks for a new notice. Its advantage is simplicity when the provider only exposes a query endpoint; its drawback is detection latency and continuous requests.

**Event-driven** receives notifications when the provider emits an event. This reduces polling and can detect earlier, but requires handling duplicate events, delayed events, event bus disconnections, and out-of-order delivery.

Both can be combined: receive events as the primary signal and use polling as a reconciliation or fallback mechanism if the provider architecture supports it.

## 3. Normalizing Signals into an Internal Contract

Applications should not scatter separate logic for every interruption type across every module. Normalize sources into a single internal event, for example:

~~~json
{
  "type": "ShutdownRequested",
  "resource_id": "worker-instance-42",
  "reason": "capacity-reclaim",
  "source": "cloud-event",
  "event_id": "evt-7f21",
  "observed_at": "2026-11-22T10:15:00Z",
  "deadline_at": "2026-11-22T10:16:30Z"
}
~~~

Field meanings:

| Field | Purpose |
|---|---|
| type | Standardized event type |
| resource_id | Affected instance, VM, task, or Pod |
| reason | Spot reclaim, scale-in, maintenance, deployment, or operator |
| source | Metadata, event bus, signal, orchestrator, or admin |
| event_id | Event identifier for deduplication |
| observed_at | Time when the application observed the event |
| deadline_at | Latest completion time per source information |

This is an illustrative schema, not a standard payload of any single cloud provider. The adapter must translate the actual payload into the internal schema and retain event IDs/metadata needed for auditing.

### 3.1. Deadlines Must Have a Source and Reliability Level

If the provider gives an absolute deadline, store it along with the source and receipt timestamp. If only remaining duration is given, convert it into a deadline based on the process's monotonic clock to avoid skew from system clock adjustments.

Never invent a deadline longer than what the provider grants. If the deadline is unknown, the application should use a conservative shutdown budget per workload policy and prepare to stop immediately.

### 3.2. Handling Duplicate and Late Events

An event may be delivered multiple times due to event bus retries or both polling and event-driven paths detecting it. Handlers must be idempotent:

- The same `event_id` triggers only one state transition.
- Events arriving after shutdown has already started do not restart the workflow.
- A newer, shorter deadline must take precedence.
- Stale events must never extend an existing deadline.
- Log the source and timestamp for investigation.

If multiple distinct signals request a stop, take the strictest active deadline.

## 4. Managing the Shutdown Deadline

Advance notice can be short. The application needs a time budget instead of waiting indefinitely for jobs to finish.

Let:

- `T_d`: deadline timestamp by which the process must exit.
- `T_n`: time to stop accepting new work and drain.
- `T_j`: time to finish the running job if possible.
- `T_p`: time to checkpoint or commit data.
- `T_c`: time to close connections and resources.
- `T_s`: safety margin for latency, scheduling, and variance.

Budget condition:

~~~text
T_n + T_j + T_p + T_c + T_s <= T_remaining
~~~

Where `T_remaining` is the time from receiving the notice until the deadline. The safety margin must not be spent on business work; it is reserved for final steps that can take unpredictable time.

### 4.1. Prioritizing by Remaining Time

When a notice arrives, compute remaining time:

~~~text
T_remaining = T_d - T_now
~~~

Then choose the action:

| Remaining time | Priority action |
|---|---|
| Plenty of time relative to one job | Stop accepting new jobs, finish current job, and commit |
| Enough only for checkpointing | Stop job at a safe boundary, save progress, then release lease |
| Near safety margin | Stop all new work, write minimal checkpoint or recovery state |
| Past deadline | Do not start long cleanups; prioritize consistency and let recovery take over |

Thresholds must be measured from the actual workload. Do not use a fixed number of seconds for every application or provider.

### 4.2. Reserving a Safety Margin

Several shutdown steps have variable latency: writing to object storage, flushing logs, closing TLS connections, updating queue visibility, or deregistering from a load balancer. If the application waits until the last second, a single network timeout can push the process past the deadline.

Set an internal deadline earlier than the platform deadline:

~~~text
application_deadline = provider_deadline - safety_margin
~~~

The application must finish before `application_deadline`. The safety margin should be based on high percentiles of cleanup duration and real network conditions, not average values.

### 4.3. Use a Monotonic Clock for Timeouts

Absolute deadlines from events can use UTC for storage and auditing. However, in-process countdown timers should rely on a monotonic clock so system clock adjustments do not unexpectedly stretch or shrink remaining time.

If the host clock can drift, account for the skew and reduce the safety margin accordingly. Never extend a deadline just because the instance clock differs from the control plane clock.

## 5. State Machine for the Interruption Workflow

A state machine prevents handling shutdown across inconsistent branches.

~~~mermaid
stateDiagram-v2
    [*] --> Running
    Running --> NoticeReceived: Interruption notice
    NoticeReceived --> Quiescing: Block new work
    Quiescing --> Checkpointing: Work in progress
    Quiescing --> Finalizing: No active work
    Checkpointing --> Draining: Checkpoint/commit done
    Checkpointing --> Finalizing: Budget exhausted
    Draining --> Finalizing: Lease released or job acked
    Finalizing --> Exited: Resources closed
    Running --> ForcedExit: Machine lost / sudden kill
    NoticeReceived --> ForcedExit: Deadline expired
    ForcedExit --> [*]
    Exited --> [*]
~~~

States:

- **Running:** accepting and processing work normally.
- **NoticeReceived:** signal and deadline recorded.
- **Quiescing:** stopping acceptance of new requests, messages, or jobs.
- **Checkpointing:** saving progress of running work.
- **Draining:** completing, acknowledging, or releasing work per protocol.
- **Finalizing:** flushing data, closing connections, and stopping dependent agents.
- **Exited:** process exited cleanly.
- **ForcedExit:** process had no chance to finish; recovery relies on durable state.

Every state transition must be idempotent. Multiple threads may detect signals or receive events simultaneously; only a single coordination flow should own state transitions.

## 6. Stop Accepting New Work Immediately on Notice

Upon receiving a notice, the first step is usually to stop taking on additional work. If the application keeps accepting jobs while checkpointing, it may never terminate.

Depending on the workload:

- API: mark readiness false, deregister from the load balancer, or stop accepting new connections.
- Queue worker: stop polling/receiving new messages.
- Batch: stop claiming new partitions or chunks.
- Streaming consumer: stop fetching new records and determine which offsets can be safely committed.
- Scheduler: stop dispatching new jobs to the instance slated for reclamation.
- GPU worker: stop accepting new batches; save model or optimizer state if the job needs to resume.

### 6.1. Draining In-Flight Requests

For APIs, continue processing already-received requests within the remaining budget. If a request cannot finish:

- Return a retryable error if the protocol and client support it.
- Ensure the operation carries an idempotency key.
- Never report success before results are committed.
- Close connections per protocol if forced to stop.

For HTTP/2, WebSockets, or streaming responses, provide appropriate close or reconnect signaling. Do not keep connections open indefinitely when the deadline is near.

### 6.2. Queue Workers and Leases

For queues, received messages usually have a visibility timeout or lease. On shutdown:

1. Stop receiving/polling.
2. Continue the current job if sufficient time remains.
3. Persist results durably before acknowledging.
4. If unable to finish, save a checkpoint and release/let the lease expire per queue semantics.
5. Close the consumer once work is in a recoverable state.

Never acknowledge a message just to clear the queue before the instance is reclaimed. If results are not safely written, doing so can cause work loss.

### 6.3. Avoid Holding Leases Past Expiration Needlessly

If a worker cannot finish before the deadline, stop renewing the lease when insufficient runtime remains. Another worker needs the chance to pick up the job. Releasing the lease should coordinate with checkpointing so the job does not restart from scratch when resumption is possible.

## 7. Deadline-Driven Checkpointing

Checkpointing saves progress so a workload can resume on another instance. For interruptible compute, checkpointing should be designed in from the start rather than bolted on after an incident.

A checkpoint can contain:

- Job ID and algorithm version.
- Input reference and checksum.
- Partition, offset, or processing position.
- Required intermediate state.
- Committed outputs and in-progress outputs.
- Checkpoint timestamp and sequence/version.
- Metadata identifying the instance/worker that created the checkpoint.

### 7.1. Choosing Checkpoint Granularity

If checkpoints are too coarse, losing a machine forces lots of rework. If checkpoints are too frequent, the workload wastes I/O and write time. Choose granularity based on:

- Time to process one chunk.
- Checkpoint size.
- Durable write cost.
- Progress RPO.
- Typical interruption probability and deadlines.

For long jobs, splitting work into independent chunks is usually easier to recover than one monolithic operation.

### 7.2. Writing Checkpoints Consistently

Checkpoints must match saved outputs. If a checkpoint is written before the output, a subsequent run may skip nonexistent results. If output is written before the checkpoint, the job may rerun that segment.

Common approaches:

- Transactions covering both output and progress markers when in the same database.
- Idempotent outputs keyed uniquely by job/chunk.
- Writing output to a temporary object, verifying it, then writing a commit marker.
- Versioned checkpoints with a monotonically increasing sequence.
- Manifests referencing only completed, durable chunks.

Never overwrite a good checkpoint with an older delayed checkpoint. Use versions or compare-and-swap so only newer progress is accepted.

### 7.3. Checkpoints Must Live on Durable Storage

RAM, local ephemeral disk, or volumes tied strictly to the about-to-be-reclaimed instance are not the sole place to store checkpoints. Use a database, object storage, or durable volumes capable of outliving the instance lifecycle.

If the checkpoint service is unreachable, the application needs fallback behavior: finish a small committable unit, release the job to retry from the prior checkpoint, or write minimal recovery state to another durable location. Never pretend a checkpoint succeeded before storage confirms it.

## 8. Long Jobs and Non-Interruptible Work Units

Some tasks cannot pause at an arbitrary line of code. For example:

- Writing a large archive file.
- Executing a business transaction.
- Training an epoch or updating a model.
- Building an artifact that requires complete output.
- Running a schema-altering migration.

Identify safe points prior to deployment:

- Boundaries between chunks or partitions.
- Transaction boundaries.
- Output commit points.
- Moments when state can be serialized.
- Which steps must rerun if an interruption occurs.

If no safe point exists, design a wrapper or protocol to make the operation atomic/idempotent, or choose a compute tier less likely to be reclaimed.

### 8.1. Unable to Finish Before the Deadline

If a job has 20 minutes left but only 30 seconds remain before interruption, the application should not wait for completion. Instead:

1. Stop dispatching new jobs.
2. Ask the job to stop at the nearest safe point.
3. Save a checkpoint or committed progress.
4. Record state needed to resume.
5. Release the lease or allow the job to be reassigned.
6. Exit before the safety deadline.

### 8.2. Jobs Without Checkpoint Support

If checkpointing is not possible, strategies include:

- Splitting the job at the scheduler level.
- Writing outputs in idempotent chunks.
- Rerunning the entire uncommitted chunk.
- Leaving the job in the queue for another worker.
- Checkpointing at the input/output data layer instead of serializing full memory.

Not every application suits Spot/preemptible compute. Workloads requiring uninterrupted continuous processing with no recovery mechanism may need more stable compute.

## 9. Coordinating with Linux, systemd, and Container Runtimes

On Linux, SIGTERM is typically the soft termination request. Applications should catch the signal and transition into the same defined state machine. SIGKILL cannot be caught; when sent, the process cannot run cleanup.

### 9.1. Handling SIGTERM

A signal handler should do minimal work: flag shutdown requested or wake the event loop. Do not perform network I/O, complex file writes, or wait on long locks directly inside a signal handler.

Python example:

~~~python
import asyncio
import signal

shutdown_requested = asyncio.Event()

def on_shutdown_signal():
    shutdown_requested.set()

async def run():
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGTERM, on_shutdown_signal)
    loop.add_signal_handler(signal.SIGINT, on_shutdown_signal)

    await worker.start()
    await shutdown_requested.wait()

    # The steps below must use the deadline provided by the interruption manager.
    await worker.stop_accepting_new_jobs()
    await worker.checkpoint_or_finish_current_job()
    await worker.release_unfinished_lease()
    await worker.close()

asyncio.run(run())
~~~

This is an illustrative example. The `worker` functions represent application adapters; in production, wrap each step with timeouts derived from the shutdown budget, handle cancellation, and ensure an error in one step does not skip closing essential resources. `add_signal_handler` suits Unix event loops; Windows requires the corresponding service control mechanism.

### 9.2. systemd

systemd can send SIGTERM and wait up to `TimeoutStopSec` before terminating the process per service policy. This duration must be shorter than the external platform deadline and sufficient for the application to complete cleanup.

~~~ini
[Unit]
Description=Interruptible batch worker
After=network-online.target

[Service]
Type=simple
User=batch
ExecStart=/opt/batch/bin/worker
KillSignal=SIGTERM
TimeoutStopSec=40s
Restart=on-failure

[Install]
WantedBy=multi-user.target
~~~

The 40-second value is only a service configuration example, not a universal cloud notice duration. If the provider leaves only 30 seconds, a 40-second systemd timeout cannot protect the process. The outermost deadline always takes precedence.

### 9.3. Container Runtimes

When a container stops, the runtime typically sends a signal to the main process (PID 1), waits a grace period, then forcibly terminates if the process has not exited. Ensure:

- The application is PID 1, or signals are properly forwarded by an init/wrapper.
- The signal handler triggers the shutdown state machine.
- Container grace period does not exceed the instance/node deadline.
- Do not rely on a shell wrapper that swallows signals.
- Health/readiness is updated to stop receiving traffic.

## 10. Kubernetes Termination Lifecycle

When a Pod is deleted or replaced, Kubernetes moves the Pod to terminating, updates endpoints to stop routing new traffic to the Pod, runs the `preStop` hook if configured, sends the termination signal to containers, and waits `terminationGracePeriodSeconds`. Once the grace period expires, the runtime can forcibly terminate the container.

Example:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: batch-worker
spec:
  replicas: 4
  selector:
    matchLabels:
      app: batch-worker
  template:
    metadata:
      labels:
        app: batch-worker
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: worker
          image: registry.example/batch-worker:v4
          lifecycle:
            preStop:
              exec:
                command: ["/app/bin/drain", "--deadline-seconds=35"]
~~~

This is an illustrative configuration. The `drain` command must be a real tool inside the image and must stop accepting jobs, checkpoint, or release leases per protocol. `preStop` consumes time out of the termination grace period; hook time is not added on top of the 45-second budget. The application still needs to handle SIGTERM and track its own deadline.

For reclaimed nodes, distinguish the cloud provider's advance notice window from the Pod's termination grace period. The node may not have enough remaining time to grant the full grace period to every Pod. Never assume every Pod receives its full configured grace period during sudden node loss.

### 10.1. Pod Eviction and Node Interruption

Pod eviction can be caused by node drains, resource pressure, or administrative actions. Node interruption can be caused by cloud reclamation or host failure. Different events may travel through different handling paths.

If using a node termination handler or equivalent agent, verify:

- The agent receives notices from the correct provider.
- The agent has required permissions and is deployed on all applicable nodes.
- The order of cordon, drain, and terminate matches the platform.
- Whether PodDisruptionBudgets affect voluntary drains.
- Whether stateful workloads have appropriate volumes/replication.
- How the system behaves if the agent or event bus fails.

## 11. Windows Services and Windows Applications

A Windows Service receives stop requests through the Service Control Manager (SCM), typically `SERVICE_CONTROL_STOP`. The service should enter the stop-pending state, stop accepting new work, finish or checkpoint jobs, and report stopped once cleanup completes.

Key items to implement:

- Stop handler only signals the worker/event loop.
- Stop accepting new requests or messages.
- Use cancellation tokens or equivalent mechanisms to propagate the deadline down to tasks.
- Set timeouts on network, storage, and database operations.
- Flush necessary data and logs.
- Close connections, threads, timers, and handles.
- Record status if forced to stop before job completion.

Windows offers a preshutdown mechanism for services configured to support it, though timing and behavior depend on the SCM and system policy. Do not treat preshutdown as a guarantee of unlimited time. The cloud or hypervisor deadline remains the outer limit.

## 12. Distinguishing Graceful Stop, Pause, and Hibernate

Platforms may offer multiple actions when resources are reclaimed:

- **Stop:** stops the VM or process; running memory is not necessarily preserved.
- **Terminate:** deletes the instance/resource per service semantics.
- **Hibernate:** saves memory state to storage per service capability and stops the VM; not all instances/workloads support it.
- **Pause/suspend:** temporarily halts execution if supported by the platform, though resuming in the exact state should not be assumed by default.
- **Checkpoint:** the application itself saves business state to rerun on another compute instance.

Hibernation does not replace application-level checkpointing. A memory image can depend on hardware, kernel, network sessions, or external state; upon resume, the application still must verify connections and consistency. Application-level checkpoints are generally more portable across instances.

## 13. Deadline-Aware Worker: Implementation Example

Workers need an interruption manager that owns the deadline and drives state transitions. Jobs should be time-bounded, checkpoint at safe points, and acknowledge only after results are durable.

Skeleton Python example:

~~~python
import asyncio
import time

SAFETY_MARGIN_SECONDS = 5
shutdown_requested = asyncio.Event()
deadline_monotonic = None

def request_shutdown(deadline_seconds_from_now):
    global deadline_monotonic
    candidate = time.monotonic() + deadline_seconds_from_now

    # If multiple notices arrive, keep the earliest deadline.
    if deadline_monotonic is None:
        deadline_monotonic = candidate
    else:
        deadline_monotonic = min(deadline_monotonic, candidate)

    shutdown_requested.set()

def remaining_budget():
    if deadline_monotonic is None:
        return None  # No interruption yet: no stop deadline enforced.
    return max(
        0,
        deadline_monotonic - time.monotonic() - SAFETY_MARGIN_SECONDS,
    )

async def run_worker(queue):
    while not shutdown_requested.is_set():
        job = await queue.receive(timeout=1)
        if job is None:
            continue

        if shutdown_requested.is_set():
            await queue.release(job)
            break

        # Handler checks stop_event at safe points.
        outcome = await process_until_safe_point(
            job,
            stop_event=shutdown_requested,
            remaining_budget=remaining_budget,
        )

        if outcome.completed:
            await persist_result(job.id, outcome.result)
            await queue.ack(job)
            continue

        # Job incomplete: checkpoint then release within remaining budget.
        budget = remaining_budget()
        if budget > 0:
            try:
                await asyncio.wait_for(
                    save_checkpoint(job, outcome.checkpoint_state),
                    timeout=budget,
                )
            except asyncio.TimeoutError:
                pass  # Keep the latest committed durable checkpoint.

        budget = remaining_budget()
        if budget > 0:
            try:
                await asyncio.wait_for(queue.release(job), timeout=budget)
            except asyncio.TimeoutError:
                pass  # Lease will expire per queue semantics.
        break

    # Close consumer if time remains; otherwise let lease/connection timeout
    # and queue recovery mechanisms take over.
    budget = remaining_budget()
    if budget > 0:
        await asyncio.wait_for(queue.close(), timeout=budget)
~~~

This is an illustrative skeleton, not a complete queue library. `process_until_safe_point` must run normally when no notice is present and return an incomplete outcome only when `stop_event` is set or the budget is nearly exhausted. In production, `persist`, `ack`, `checkpoint`, `release`, and `close` steps need individual timeouts, versioned job states, and idempotent operations. If insufficient time remains or storage is unreachable, rely on the latest durable checkpoint and let the lease expire per queue semantics. Never acknowledge before committing results.

## 14. Handling Late or Missing Notices

Notices may arrive late due to event delivery delays, agent failures, network partitions, or host failures. Applications must have recovery mechanisms independent of notices.

### 14.1. Designing for Sudden Machine Loss

- Store critical state in durable storage.
- Checkpoint periodically rather than only on notice.
- Use bounded leases so another worker can take over abandoned jobs.
- Use idempotency keys for safe reprocessing.
- Define clear transaction boundaries.
- Run a watchdog to detect workers missing heartbeats.
- Never rely on cleanup hooks for data consistency.

### 14.2. Periodic Checkpoints vs. Emergency Checkpoints

Periodic checkpoints reduce the amount of rework when no notice arrives. When a notice does arrive, an emergency checkpoint saves the incremental progress since the last checkpoint.

Periodic frequency can be chosen based on checkpoint cost and acceptable progress loss. Do not wait until an interruption to write all state if doing so could exceed the deadline.

### 14.3. Reconciliation After Instance Loss

The scheduler or controller must detect jobs with expired leases, non-heartbeating instances, or unfinished execution states. It can:

1. Mark the old execution as interrupted/unknown.
2. Inspect checkpoints and committed outputs.
3. Create a new execution or reassign the job.
4. Use idempotency to avoid duplicate writes.
5. Record the attempt count and interruption reason.

Never treat an instance vanishing as proof that the job failed completely; outputs may have committed before acknowledgement was lost. Reconcile against durable state.

## 15. Provider-Specific Considerations

Each cloud provider has its own mechanisms and notice windows. Common examples:

| Platform | Typical mechanisms | Design notes |
|---|---|---|
| AWS EC2 Spot | Interruption notice via instance metadata and event service; rebalance recommendations may exist | Handle both notices and rebalance events; verify configured stop/hibernate/terminate behavior |
| Azure Spot VM | Scheduled Events / eviction notice depending on VM type and configuration | Monitor events via Scheduled Events and prepare for fast shutdown |
| Google Cloud Spot/Preemptible | Preemption notice via metadata/service events depending on VM type | Advance notice may be short; design frequent checkpoints |
| Kubernetes on cloud | Node events, termination handlers, and Pod termination lifecycle | Combine node notices with Pod drain and grace periods |

Notice windows, payload fields, event delivery, and post-notice actions can vary by compute type, region, and service policy. Verify current documentation for your exact instance type and configuration. Do not hardcode a single number across providers or assume notices are always sent.

### 15.1. Provider Adapters

Separate integrations into adapters:

- `AwsInterruptionAdapter`
- `AzureScheduledEventAdapter`
- `GcpPreemptionAdapter`
- `KubernetesTerminationAdapter`
- `OsSignalAdapter`

Each adapter translates provider-specific events into the internal `ShutdownRequested` event. Workers, checkpointing, and the shutdown manager share a single protocol. This reduces provider coupling and lets you test the state machine with simulated events.

## 16. Observing the Interruption Process

The application should record both timing and outcomes of each phase:

- Notice count by reason and source.
- Time from notice to start of quiescing.
- Time taken to stop accepting new jobs.
- Count of jobs in flight when notice arrived.
- Count of jobs completed, checkpointed, released, or retried.
- Checkpoint duration and checkpoint failure rate.
- Remaining deadline when entering finalization.
- Count of deadline overruns or forced terminations.
- Count of jobs reassigned after interruption.
- Duplicate processing count and idempotency outcomes.

Suggested metrics:

| Metric | Meaning |
|---|---|
| `interruption_notice_total` | Total interruption notices received |
| `interruption_notice_late_total` | Notices arriving with too little remaining budget |
| `shutdown_remaining_seconds` | Remaining time at the start of each phase |
| `shutdown_duration_seconds` | Total time from notice to exit |
| `checkpoint_duration_seconds` | Time taken to save checkpoints |
| `checkpoint_failure_total` | Total failed checkpoint attempts |
| `jobs_released_on_interrupt_total` | Jobs released during interruption |
| `jobs_retried_after_interrupt_total` | Jobs reassigned after interruption |
| `forced_termination_total` | Times the process failed to exit in time |

Logs should include event ID, resource ID, reason, deadline, state transitions, and correlation/job ID. Never log tokens, secrets, or sensitive payloads.

## 17. Testing Interruption Handling

Tests must prove the application reacts properly across varying time windows and dependency failures.

Scenarios:

1. Receive notice with no job running.
2. Receive notice right after pulling a message but before starting processing.
3. Receive notice when enough time remains to finish the job.
4. Receive notice when the job cannot finish before the deadline.
5. Receive two notices with duplicate event IDs.
6. Receive a second notice with an earlier deadline.
7. Receive a late event or an already-expired deadline.
8. Checkpoint storage times out or is unreachable.
9. Worker is killed mid-write between output and checkpoint.
10. Worker commits results but fails to acknowledge the queue.
11. Event agent is down, but the OS still sends SIGTERM.
12. No notice arrives and the instance vanishes abruptly.
13. Kubernetes Pod is terminating while the node is also being reclaimed.
14. Windows Service receives stop while processing a job.

### 17.1. Pass Criteria

- No new work accepted after entering quiescing.
- Deadlines are never extended by duplicate or late events.
- Checkpoints accurately reflect committed outputs.
- Messages are acknowledged only after durable results are written.
- Incomplete jobs can be retried or resumed.
- Cleanup completes before the application deadline in supported scenarios.
- When notices are lost or forced kills occur, durable state still allows recovery.
- No uncontrolled duplicate side effects are produced.

### 17.2. Rehearsing in a Safe Environment

Build an interruption simulator that emits events with short deadlines to test the state machine. Start with a canary worker, cap job counts, and use test data. Record phase timings, then gradually increase complexity.

Never test reclaiming a large production fleet without clear blast-radius limits, standby capacity, and stop conditions.

## 18. Real-World Example: Image Batch Processing on Spot VMs

An image processing system uses Spot VMs to reduce cost. Each job reads a batch of images from object storage, generates thumbnails, and writes outputs. Jobs may run for several minutes, while a reclamation notice may leave only a short window.

Design:

1. Scheduler pushes job ID and object list to a durable queue.
2. Worker acquires the job with a time-bounded lease.
3. Each image is processed as an independent chunk.
4. Thumbnails are written using idempotent keys based on job ID and object ID.
5. After each chunk, the worker saves a checkpoint listing completed objects.
6. Upon receiving an interruption notice, the worker stops polling the queue.
7. The worker finishes the current chunk if budget allows; otherwise it aborts at a safe point.
8. The worker writes a new checkpoint, releases the lease, and closes clients.
9. Another instance picks up the job, reads the checkpoint, and resumes unfinished items.

If a worker is lost before writing a checkpoint, the most recent chunk can be rerun. Because outputs use idempotent keys, rerunning does not create duplicate thumbnails. The queue and durable state let the system continue without the old instance.

## 19. Choosing Workloads Suitable for Interruptible Compute

Suitable workloads typically share one or more traits:

- Can be split into chunks or partitions.
- Can be checkpointed or rerun at acceptable cost.
- Do not require long-lived connections to a single client.
- Can use queues or schedulers for redistribution.
- Have idempotent outputs or clear transactions.
- Can tolerate variable completion times.

Examples:

- Batch rendering, transcoding, or image processing.
- Rerunnable CI builds and tests.
- Distributed data processing.
- Checkpointed simulations or research workloads.
- Queue-processing workers.
- Stateless services with standby capacity and instance replacement.

Less suitable workloads:

- Self-managed database primaries without proper replication/failover.
- Single-shot data writes without transactions/checkpoints.
- Critical sessions or state living solely in RAM.
- Long jobs that cannot stop or rerun.
- Systems requiring ultra-stable latency with no replacement capacity.

An unsuitable workload is not strictly barred from Spot/preemptible entirely. You can split interruptible portions onto low-cost compute while keeping stateful/critical components on stable compute.

## 20. Common Mistakes

- **Treating notices as guarantees:** events can arrive late, be dropped, or be unsupported in certain failure modes.
- **Using one timeout across all providers:** each compute offering has different deadlines and semantics.
- **Catching only SIGTERM:** misses earlier interruption notices from the cloud control plane.
- **Listening only to the event bus:** fails to handle event agent or network failures.
- **Continuing to accept new jobs after notice:** increases work to drain and risks exceeding deadlines.
- **Waiting for long jobs to finish at all costs:** leaves no time for checkpointing and cleanup.
- **Storing checkpoints only in RAM/local disk:** lost along with the instance upon reclamation.
- **Acking before committing:** risks losing both messages and outputs.
- **Releasing leases without checkpointing:** forces the next worker to rerun the entire job.
- **Not handling duplicate events:** shutdown handler runs multiple times and causes race conditions.
- **Letting newer events extend the deadline:** can exceed provider-allowed time.
- **Omitting a safety margin:** slow network or storage causes shutdown to be killed.
- **Using `preStop` as a replacement for application logic:** hooks do not automatically guarantee data and leases are handled cleanly.
- **Testing only graceful notices:** fails to verify host loss or forced termination.

## 21. Implementation Checklist

Before adopting interruptible compute, verify:

- [ ] Workloads can be split, checkpointed, or safely retried.
- [ ] Provider interruption notice sources are identified.
- [ ] An adapter maps both notices and OS signals into a unified shutdown event.
- [ ] Events include reason, resource ID, event ID, and deadline.
- [ ] Handlers process duplicate and late events idempotently.
- [ ] Internal deadline is shorter than the platform deadline with a safety margin.
- [ ] Application stops accepting new jobs immediately when quiescing.
- [ ] Queue leases, acknowledgements, and retries coordinate properly.
- [ ] Checkpoints are written to durable storage and versioned.
- [ ] Outputs and checkpoints are consistent and idempotent.
- [ ] Container/systemd/Windows Service timeouts fit within the outermost budget.
- [ ] Recovery mechanisms exist when notices never arrive or checkpoints fail.
- [ ] Metrics and logs capture timing of each shutdown phase.
- [ ] Tested short deadlines, duplicate events, missing notices, and forced terminations.

## 22. Key Takeaways

An interruption notice is an opportunity for workloads to prepare before compute is reclaimed. Applications must identify signal sources, normalize events, enforce deadlines and safety margins, stop accepting new work, checkpoint or finish what they can, release leases, close resources, and exit on time.

Designs should use an idempotent, deadline-aware state machine to coordinate cloud events, orchestrators, and OS signals. Queues, checkpoints, transactions, leases, and idempotency must be designed together so a new instance can resume seamlessly. Because notices do not always arrive, periodic checkpointing and durable state remain essential safeguards against sudden machine loss. Measure shutdown durations and rehearse interruptions regularly to prove workloads can recover safely within real-world time bounds.
