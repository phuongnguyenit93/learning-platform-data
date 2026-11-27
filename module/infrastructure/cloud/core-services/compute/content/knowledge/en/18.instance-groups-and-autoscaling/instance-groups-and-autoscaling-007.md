# Safe Scale-in and Protecting Instances Running Active Tasks

Autoscaling lets a machine group add or remove instances according to demand. Scale-out creates additional serving capacity; scale-in removes existing capacity. If an instance is terminated while still accepting requests, running jobs, holding leases, or writing data, reducing machine counts can drop work, trigger duplicate processing, or disrupt service.

**Safe scale-in** is the process of removing an instance from the serving pool, stopping new work assignment, allowing active work to complete or checkpoint, releasing shared resources, and only then stopping the machine. The goal is to trim capacity while preserving data correctness, service continuity, and fault recovery.

This lesson belongs to the **Instance Groups and Autoscaling** chapter of the **CLOUD_CORE_SERVICES_COMPUTE** module. The module explores cloud compute capacity models—from virtual machines and containers to serverless; how to choose CPU, memory, networking, and security settings; and how to deploy applications, scale under load, ensure availability, and optimize operating costs. Within that scope, safe scale-in lets machine groups optimize instance counts without losing requests, jobs, or critical state.

## 1. What is scale-in and why protect active workloads?

### 1.1. Scale-out and scale-in

- **Scale-out:** increasing the number of instances or replicas to handle additional load.
- **Scale-in:** decreasing the number of instances or replicas when load drops or excess capacity must be removed.
- **Desired capacity:** the number of instances the autoscaling controller is targeting.
- **Minimum capacity:** the minimum number of instances to maintain.
- **Maximum capacity:** the upper bound of the machine group.
- **Scale-in candidate:** an instance selected for removal from the group.
- **Drain:** stopping new workload assignment to an instance and waiting for in-progress work to finish or hand off.
- **Termination:** stopping the instance or container after draining meets its exit conditions.

Scale-in is not simply shutting down whichever machine has the lowest CPU. A machine with low CPU might still be processing an important transaction, holding a long-lived connection, running a batch job, or serving as a required quorum member.

### 1.2. What can happen if a machine is stopped too early?

Terminating an active instance abruptly can cause:

- In-flight requests reset or time out.
- Running jobs lose progress and must restart from scratch.
- Messages get acknowledged before results are durably persisted.
- A single task runs concurrently on two workers.
- Transactions or file writes are left incomplete.
- Database, cache, or partner connections close abruptly.
- Clusters lose quorum or fall below healthy replica minimums.
- Load balancers keep sending traffic to an instance about to terminate.
- Local disks or scratch data are deleted before syncing.

Impact depends on the workload. For stateless web servers, connection draining is often enough to replace a machine. For queue workers, you must manage leases, acknowledgements, and checkpoints. For databases or stateful systems, you also need replication, failover, and quorum protection workflows.

### 1.3. Workload types and scale-in strategies

| Workload type | Risks during scale-in | Common protection approach |
|---|---|---|
| Stateless web/API | In-flight requests and long-lived connections get severed | Stop accepting new requests, deregister from load balancer, wait for requests to finish |
| Queue worker | Running jobs get lost or processed twice | Stop pulling new messages, finish/checkpoint jobs, ack after commit |
| Batch/compute job | Loss of progress on long-running jobs | Checkpoint, resume, or wait for job completion |
| Stateful service | Loss of data, replicas, or quorum | Replication, leader handoff, failover, and quorum checks |
| Stream processor | Lost offsets or out-of-order processing | Controlled offset commits/checkpoints, partition ownership transfer |
| GPU worker | Lost model state, batches, or long tasks | Drain batch, save checkpoints, release accelerator cleanly |

A machine group may run multiple workload types. In that case, separate instances by role or provide dedicated drain mechanisms for each task type.

## 2. Lifecycle of an instance during scale-in

### 2.1. Required states

A safe workflow should distinguish at least these states:

1. **In service:** the instance is serving and accepting new work.
2. **Scale-in selected:** the controller selects the instance to reduce capacity.
3. **Protected/held:** the instance is temporarily held if running non-interruptible work or matching a protection condition.
4. **Draining:** the instance stops accepting new work; active operations finish or hand off.
5. **Quiescent:** no active requests/jobs remain; resources and leases are released.
6. **Terminating:** the system stops processes and the instance.
7. **Terminated:** the instance has left the group and resources are reclaimed.

Not every platform exposes these exact state names. This is a logical state model for designing applications and automation.

~~~mermaid
stateDiagram-v2
    [*] --> InService
    InService --> Selected: Autoscaler picks scale-in candidate
    Selected --> Protected: Non-interruptible task active
    Protected --> InService: Task finished or protection expired
    Selected --> Draining: Allowed to begin scale-in
    Draining --> Quiescent: No active work remains
    Draining --> InService: Scale-in canceled / rolled back
    Quiescent --> Terminating: Stop process and release machine
    Terminating --> Terminated
    Terminated --> [*]
~~~

### 2.2. Standard sequence

A controlled scale-in sequence typically includes:

1. The controller determines desired capacity must decrease.
2. Select a removable instance according to policy.
3. Send a drain signal to the application/agent and mark the instance ineligible for new work.
4. Application stops accepting new requests/jobs; load balancer or service discovery begins removing the instance from target pools.
5. Wait for routing updates to propagate across relevant components.
6. Wait for active requests/jobs to finish, checkpoint, or hand off.
7. Commit state, acknowledge messages, and release leases/locks.
8. Close connections, flush telemetry, and release resources.
9. Signal drain completion so the platform proceeds with termination.
10. Verify the instance has left the group and remaining capacity sustains load.

Exact ordering among deregistration, readiness, and shutdown signals depends on the load balancer, orchestrator, and how the app receives traffic. Design so there is no window where an instance stops accepting work while the system still routes new requests to it.

### 2.3. Drain deadlines

Draining cannot run indefinitely. Define:

- **Grace period:** maximum time allowed for orderly shutdown.
- **Task deadline:** maximum allowed duration of a single request or job.
- **Termination deadline:** time at which the platform forcefully kills the instance.
- **Checkpoint interval:** interval between progress saves.
- **Lease/visibility timeout:** duration a worker holds exclusive processing rights over a message or resource.

If work exceeds the grace period, the application needs checkpoint/resume, requeueing, or handoff. Waiting indefinitely can prevent autoscaling from ever shrinking capacity and inflate costs.

## 3. Identifying which instance is safe to remove

### 3.1. Do not select based solely on CPU

Low CPU does not mean a machine is idle. A worker may be waiting on I/O, holding a transaction, running a long job, or holding a lock. Likewise, high CPU does not mean a machine cannot drain once it stops accepting new work and its current workload finishes shortly.

Beyond CPU and memory, inspect:

- Active request count.
- Running job count and estimated remaining time.
- Queue depth and message arrival rate.
- Open connection count.
- Replication, partition, or shard status.
- Leader/coordinator role.
- Unflushed data or pending checkpoints.
- Whether local storage holds data that must be preserved.
- Instance health and incident status.

### 3.2. Scale-in candidate selection policies

Common selection policies include:

- Removing the newest or oldest instance depending on deployment goals.
- Preserving balance across availability zones.
- Preferring instances with spare capacity and fewer active tasks.
- Preferring instances marked drain-ready.
- Retaining instances with special roles or un-migrated data.
- Selecting by cost or instance type in mixed-configuration groups.

Default provider termination policies may optimize for zone balance or instance age without knowing which machine is running a long job. To protect tasks, applications should expose operational state for the autoscaler or automation to inspect.

### 3.3. Separating workload state from infrastructure metrics

You can expose metrics such as:

- `active_requests`
- `active_jobs`
- `inflight_messages`
- `oldest_job_age`
- `drain_ready`
- `estimated_drain_seconds`
- `checkpoint_age`
- `active_leases`

These metrics inform the system which instances can drain safely. Ensure metrics have acceptable reporting lag and do not become a single point of failure.

If application state cannot feed directly into autoscaler decisions, use lifecycle hooks or application-layer protection after an instance is selected before allowing termination to proceed.

## 4. Safe draining for web servers and APIs

### 4.1. Stop accepting new requests

When draining starts:

- Mark the instance unready or ineligible for traffic.
- Remove the instance from target groups/service discovery.
- Stop accepting new connections on the listener if managed directly by the app.
- Keep serving in-flight requests until completion or deadline.
- Return appropriate responses if clients send new requests to a draining instance.

Readiness and deregistration are rarely instantaneous. Health check intervals, caches, connection reuse, and propagation across nodes introduce lag. Set an adequate propagation delay and verify the load balancer stops routing new requests.

### 4.2. Keep-alive and long-lived connections

HTTP keep-alive, WebSockets, gRPC streams, or TCP sessions can outlive a single request. Closing the listener immediately resets open connections.

Applications should define:

- Rejecting new streams once draining begins.
- Sending graceful close frames/signals where protocol supports it.
- Giving clients time to reconnect or migrate to another endpoint.
- Capping maximum time for connection draining.
- Handling idempotent requests and safe retries.

For WebSockets or long-lived streams, never assume the load balancer will transparently migrate open connections to another instance. Clients and servers need reconnect/resume protocols or clean notified session termination.

### 4.3. Readiness and deregistration ordering

A typical sequence:

1. Application transitions internal state to draining.
2. Readiness endpoint returns unready for new requests.
3. Load balancer stops selecting the instance once health state updates.
4. Application continues finishing in-flight requests.
5. Once requests finish or deadline expires, close listeners and exit the process.

Some systems require deregistering the target first before sending `SIGTERM`; others use a pre-stop hook to coordinate. The key is aligning health check intervals, deregistration delays, shutdown timeouts, and grace periods.

### 4.4. Readiness and drain endpoint example

Illustrative pseudocode:

~~~text
state = SERVING

on_start_drain():
    state = DRAINING
    readiness_endpoint = NOT_READY
    stop_accepting_new_requests()

    wait_until(
        active_requests == 0
        OR drain_deadline_reached
    )

    notify_long_lived_clients_to_reconnect()
    close_remaining_connections()
    flush_logs_and_metrics()
    exit_cleanly()
~~~

This is a logical model, not runnable code. Real applications must synchronize readiness with the load balancer/orchestrator and ensure requests rejected during draining do not lose data.

## 5. Safe draining for queue workers

### 5.1. Why do queue workers need a dedicated workflow?

Workers typically pull a message, process a task, and acknowledge completion to the queue. If an instance dies mid-processing:

- The message may be redelivered after visibility timeout or lease expiry.
- The job may run concurrently on another worker if the lease expires while the old worker is still alive.
- If acknowledged before results are durably saved, the message disappears even though work never finished.
- Without acknowledgements or checkpoints, the job must restart from the beginning.

Many queue systems provide at-least-once delivery semantics. Messages may be delivered more than once, so applications must be idempotent to handle duplicates safely.

### 5.2. Worker shutdown sequence

Upon receiving a drain command:

1. Transition the worker to stop accepting new jobs.
2. Stop polling or stop fetching new messages.
3. Renew leases/visibility timeouts for active jobs if needed.
4. Allow active jobs to finish within the time limit.
5. Persist results and checkpoints durably.
6. Acknowledge messages only after commits succeed.
7. For jobs unable to finish, checkpoint and release/requeue per queue protocol.
8. Release locks, leases, and resources.
9. Report drain-ready so the instance can terminate.

Crucially, never acknowledge a message simply because the worker received a shutdown signal. Acknowledgement must follow completion or recoverable state persistence.

### 5.3. Visibility timeouts and leases

In visibility-timeout queues, once a message is received it becomes temporarily hidden from other workers for a configured duration. If processing takes longer without renewal, the message reappears and another worker picks it up.

You must:

- Choose visibility timeouts suited to expected processing durations.
- Renew visibility/leases while jobs remain active.
- Cap total renewal duration.
- Ensure stale workers stop or lose write authority once leases expire.
- Use idempotency keys or fencing tokens for data-mutating operations.

A lease represents time-bounded ownership in a coordination system, yet by itself it does not halt an old worker process. If a stale worker keeps running after lease expiry, the system needs fencing tokens or storage-side ownership checks to block stale writes.

### 5.4. Checkpoints and requeueing

Long jobs should write periodic checkpoints. A checkpoint must store enough state for another worker to resume without repeating committed side effects.

Example of a job processing 1,000 files:

- Record the list of completed files.
- Write each batch's output to durable storage.
- Save the next cursor or offset.
- Acknowledge the original message only after all batches finish and commit.
- If the drain deadline hits, save the checkpoint and let the message retry/requeue.

Never store checkpoints solely on the local disk of an instance about to be terminated unless that data is synced or the volume is retained by an explicit workflow.

### 5.5. Worker pseudocode example

~~~text
on_drain_signal():
    accepting_new_jobs = false
    stop_polling_queue()

    for each active_job:
        while job_is_running(active_job):
            renew_visibility_lease(active_job)

            if job_can_finish_before_deadline(active_job):
                continue_processing(active_job)
            else:
                save_checkpoint_to_durable_store(active_job)
                stop_job_safely(active_job)
                release_or_allow_retry(active_job)

        if job_result_is_committed(active_job):
            acknowledge_message(active_job)

    close_queue_client()
    report_drain_complete()
~~~

In production implementations, handle races among shutdown signals, job completion, lease renewal, and acknowledgements. Result persistence and acknowledgement steps must be strictly ordered, retryable, and idempotent.

## 6. Long-running tasks, batch jobs, and GPU workloads

### 6.1. Handling jobs longer than the drain window

If a job can run for hours while the autoscaler grants only a few minutes for draining, you cannot wait for completion. Three main strategies exist:

- **Checkpoint/resume:** periodically save progress and resume on another instance.
- **Task boundaries:** split jobs into small units that can be independently reassigned.
- **Protected execution:** temporarily exclude instances running non-interruptible jobs from selection.

You can combine all three. For example, split a long job into 5-minute batches, checkpointing after each batch; an instance only finishes its current batch before exiting.

### 6.2. GPUs and accelerators

GPU workloads may need significant time to finish inference batches, training steps, or model checkpoints. Before termination:

- Stop accepting new batches.
- Finish the active batch or save recoverable state.
- Flush outputs and checkpoints to durable storage.
- Release accelerator contexts and device resources.
- Verify no processes remain holding the GPU in drivers/runtimes.
- Update job state so the scheduler can reassign work.

If a framework writes checkpoints only at certain training step boundaries, drain at a clean boundary. Killing a process mid-checkpoint can corrupt artifacts.

### 6.3. Streaming systems and partitions

In stream processors, each worker may own one or more partitions. Scale-in must transfer ownership cleanly:

1. Stop accepting new partition assignments.
2. Finish processing in-flight records.
3. Commit offsets or checkpoints according to system semantics.
4. Release partition ownership.
5. Another worker takes over the partitions.
6. Monitor consumer lag and duplicate processing.

Committing offsets before results are durably written risks logical data loss. Committing after writing results can produce duplicates if a worker crashes between the two operations; sinks therefore usually require transactions or idempotency.

## 7. Stateful services and quorum protection

### 7.1. Do not terminate replicas arbitrarily

For databases, cache clusters, distributed storage, or control planes, each instance may hold critical data or cluster roles. Scale-in must inspect:

- Whether the node is leader/primary.
- Remaining healthy replica count.
- Replication lag.
- Quorum and voting membership.
- Shard/partition placement.
- Unreplicated or unflushed data.
- Failover and recovery capability after the node departs.

A three-voter cluster can lose quorum if two nodes are removed closely together or one node is removed while another voter is unhealthy. Counting remaining instances alone is not enough; verify which members actively hold voting quorum.

### 7.2. Leader handoff and replica removal

Stateful scale-in workflows typically require:

1. Selecting a removable replica per data placement policy.
2. Migrating shards or replicas if needed.
3. Verifying replication has caught up.
4. Stepping down and transferring leader/primary role to another node if held by the departing node.
5. Updating cluster membership and quorum per product procedures.
6. Confirming the node has exited the cluster cleanly.
7. Only then terminating the compute instance.

Never use a VM termination command as a substitute for a database or distributed system's `remove-node` command. The application must be notified and finish membership updates first.

### 7.3. Local ephemeral storage

If a workload keeps needed data on local SSDs or ephemeral disks, termination can wipe that data. Determine:

- Which data is regenerable cache.
- Which data represents unsynced checkpoints or outputs.
- Whether volumes persist after instance deletion.
- Whether volumes need detaching and reattaching.
- Proper ordering of flush, unmount, and detach.
- Recovery procedure if an instance disappears abruptly.

Good designs persist critical state in durable storage and treat local disks as regenerable caches or scratch space.

## 8. Lifecycle hooks and cloud platform protection mechanisms

### 8.1. Lifecycle hooks

Many machine group platforms offer lifecycle hooks or termination notifications. When an instance is picked for termination, the platform pauses it in a wait state so automation or agents can perform draining.

A hook can trigger:

- Sending a notification to the instance or orchestrator.
- Putting the application into draining mode.
- Removing the target from the load balancer.
- Waiting for jobs to finish or checkpoint.
- Recording completion and signaling termination to proceed.

Lifecycle hooks have timeouts and may support heartbeats/extensions per provider APIs. When timeouts expire, the platform may proceed with termination per configuration. Hooks therefore require clear timeouts, retries, and fallbacks.

### 8.2. Instance scale-in protection

Some autoscaling services allow marking instances as protected from scale-in. This is useful when a machine runs non-interruptible jobs or holds special roles.

Understand the scope of protection:

- It may only stop the instance from being selected during certain desired-capacity reductions.
- It does not necessarily prevent health replacements, hardware failures, manual terminations, or events outside that feature's scope.
- You must clear protection once the job completes.
- Protecting too many instances prevents scale-in and drives up costs.

Scale-in protection is an assistive safeguard; applications must still implement checkpointing, retries, and sudden-instance-loss handling.

### 8.3. Termination policies

Termination policies decide which instance gets chosen when the group reduces capacity. Selection may consider instance age, zone balance, instance type, or platform-supported custom criteria.

When jobs vary in runtime, combine policies with drain-ready status. Do not assume default termination policies know how many active jobs or how much critical data sit on a machine.

### 8.4. Time-limited termination notices

Some environments provide advance notice before reclaiming capacity, such as preemptible/spot instances. Warning windows can be short and vary by provider, event type, and region.

Applications should handle notices on a best-effort basis:

- Stop accepting new work immediately.
- Write a fast checkpoint.
- Commit completed results.
- Leave incomplete jobs safely retryable.
- Never rely on always receiving a warning before losing the machine.

Advance notices do not guarantee enough time to finish every task.

## 9. Kubernetes and the pod termination lifecycle

### 9.1. Pod termination sequence

When a Pod is deleted, Kubernetes initiates termination and starts the grace period timer. If a `preStop` lifecycle hook is configured, it runs inside the grace period; afterward, the container receives `SIGTERM`. Once the grace period expires, remaining processes may receive `SIGKILL`.

Simultaneously, the Pod is marked `Terminating` and endpoint controllers update serving endpoints. Propagation through `kube-proxy`, dataplanes, Ingress, or cloud load balancers takes time. Applications must not assume traffic stops the instant a signal arrives.

### 9.2. Relevant configuration fields

A Pod spec can configure:

~~~yaml
spec:
  terminationGracePeriodSeconds: 90
  containers:
    - name: api
      image: example/api:1.2.3
      lifecycle:
        preStop:
          exec:
            command: ["/app/bin/drain", "--timeout=60s"]
~~~

This example only illustrates structure. The image must actually include the drain binary; hook duration plus shutdown duration must fit inside the overall grace period. The grace period clock starts as soon as termination begins, meaning `preStop` consumes part of that budget.

The application must still handle `SIGTERM`. `preStop` does not replace graceful shutdown logic and does not guarantee active requests finish if the process fails to manage them.

### 9.3. Readiness, preStop, and SIGTERM

A common coordination pattern:

1. Upon termination start, `preStop` calls an endpoint or command to switch the app to draining.
2. The readiness probe returns unready to curb new traffic.
3. The application waits for endpoint propagation and finishes active requests.
4. The container receives `SIGTERM`.
5. The application closes listeners, flushes telemetry, and exits before the grace period expires.

You can alternatively trigger draining on `SIGTERM` and use `preStop` for a short propagation delay, while avoiding duplicate non-idempotent logic in both places. Always test exact behavior with your runtime, probes, and Ingress controller.

### 9.4. PodDisruptionBudget (PDB)

A `PodDisruptionBudget` caps voluntary disruptions for a Pod group when operations go through the Eviction API, such as during many node drain workflows. PDBs help protect minimum ready Pods during certain disruptions.

PDBs do not replace graceful shutdown and do not block every form of Pod deletion. Direct deletes, force deletes, or certain scaling/rollout operations may bypass eviction rules. Understand the exact controller and operations involved.

### 9.5. Deployments, StatefulSets, and workers

- **Deployment:** suited for stateless workloads; needs readiness, rolling updates, and shutdown handling.
- **StatefulSet:** provides more stable identities and ordering; scaling down still requires handling data, cluster membership, and storage.
- **Job/CronJob:** ensure jobs can retry or checkpoint; never assume Pods always run uninterrupted to completion.
- **Queue worker:** stop polling, complete/checkpoint jobs, and ack in order.
- **DaemonSet:** typically tied to node lifecycle; plan for node draining and agent cleanup.

Kubernetes controllers differ in behavior. Do not reuse a single termination configuration blindly across every workload type.

## 10. Autoscaling policies to reduce scale-in risks

### 10.1. Scale-in stabilization

Load metrics can dip briefly and rebound. If scale-in reacts immediately, the machine group can oscillate (flapping), causing repeated drains and cold starts.

Mitigations include:

- Scale-in stabilization windows.
- Cooldowns or waiting windows after scale-out.
- Lower thresholds for scale-in than for scale-out (hysteresis).
- Minimum capacity as a buffer.
- Capping how many instances can be removed per evaluation cycle.
- Scheduled scaling for workloads with predictable load shapes.

Distinguish autoscaler stabilization from drain timeout. Stabilization decides *when* to start reducing capacity; drain timeout limits *how long* an instance may take to wrap up active work.

### 10.2. Scaling in on workload metrics

CPU or network utilization tells only part of the story. For queue workers, better metrics may include:

- Queue depth per worker.
- Active running jobs.
- Age of oldest message.
- Message arrival and completion rates.
- Median and high-percentile processing times.
- Number of draining workers.
- Number of instances genuinely eligible for removal.

Do not scale in if significant backlog remains even when CPU is low because workers are waiting on I/O or dependencies. Conversely, when queues are empty and no jobs are running, capacity can shrink faster down to minimum capacity.

### 10.3. Rate-limiting scale-in

Removing only a fraction of capacity per cycle helps:

- Preserve enough replicas while nodes drain.
- Limit how many jobs must checkpoint concurrently.
- Avoid dumping sudden load onto remaining workers.
- Reduce risks of losing quorum or exhausting capacity.
- Allow time to observe errors after each batch.

For stateful workloads, scale-in rate limits should reflect replication speed, quorum constraints, and data migration throughput rather than a simple instance percentage.

### 10.4. Calculating post-drain capacity

Suppose a group has 10 workers, each safely handling 20 concurrent jobs. If you scale in 4 workers while 120 jobs remain active, the surviving 6 workers may lack capacity if all jobs transfer or retry simultaneously.

Account for:

- Remaining instance processing capacity.
- Active load and pending backlog.
- Drain duration.
- Traffic bursts occurring while machines are replaced.
- Potential error or retry spikes.
- Headroom needed for a zone or node outage.

Do not push desired capacity below safe operating levels merely because metrics dipped for a brief window.

## 11. Handling errors and race conditions during scale-in

### 11.1. Instance terminated before draining finishes

This can happen when lifecycle hooks time out, hosts crash, autoscalers force-terminate, or cloud infrastructure fails. Applications must assume graceful shutdown might not occur.

Safeguards:

- Jobs must be retryable or resumable.
- Results must be persisted durably before acknowledgement.
- Use idempotency keys for side effects.
- Leases must expire so another worker can reclaim orphaned jobs.
- Checkpoints must live outside the instance.
- Run reconciliation to detect jobs stuck in unknown states.

### 11.2. Old and new workers processing concurrently

If a lease expires while the old worker is still alive, a new worker may pick up the same job. Prevent corruption by:

- Renewing leases while the worker actively owns the job.
- Using fencing tokens or monotonically increasing versions.
- Validating tokens at the data store during writes.
- Using idempotent writes or transactions.
- Blocking stale workers from committing merely because their process is still alive.

### 11.3. Duplicate shutdown signals

Automation may fire drain signals multiple times, or a container may receive both `preStop` and `SIGTERM`. Shutdown handlers must be idempotent:

- Transition state to draining once.
- Stop accepting new work after the first transition.
- Never acknowledge/release the same message multiple times beyond allowed semantics.
- Never close shared clients before active jobs using them finish.
- Enforce explicit timeouts and clean exit paths.

### 11.4. Draining never finishes

Causes include hung requests, jobs without deadlines, unclosed connections, broken lease renewals, or active-work metrics failing to decrement.

Enforce deadlines, log remaining active tasks, checkpoint/requeue where possible, and define when force-termination is permitted. An instance stuck draining must not hold capacity indefinitely without alerts and an owner.

### 11.5. No shutdown signal delivered

If a host crashes or is abruptly preempted, no drain occurs. Every critical workload must therefore tolerate sudden instance loss; graceful shutdown merely reduces lost progress rather than replacing fault tolerance.

## 12. Design example: queue worker group

A worker group processes messages from a queue. Each job runs from a few seconds to several minutes, writing results to a database and object storage.

Design:

1. Autoscaler adjusts worker counts based on queue depth and message age.
2. Workers enforce bounded concurrency and database connection pool caps.
3. When chosen for scale-in, the instance receives a lifecycle event.
4. An agent puts the worker into draining mode and stops polling new messages.
5. Active jobs continue renewing visibility leases.
6. Jobs close to finishing complete within the drain deadline.
7. Jobs exceeding the deadline write checkpoints to object storage and become eligible for retry.
8. Workers commit results first, then acknowledge the message.
9. Workers release leases, close database/queue clients, and report drain-ready.
10. The lifecycle hook completes and the autoscaling group terminates the instance.
11. Queue depth, oldest message age, active jobs, and failed jobs are monitored after scale-in.

~~~mermaid
flowchart TD
    A["Receive scale-in event"] --> B["Mark worker draining"]
    B --> C["Stop polling / accepting new jobs"]
    C --> D{"Any active jobs left?"}
    D -->|No| H["Close clients, release leases"]
    D -->|Yes| E{"Can job finish before deadline?"}
    E -->|Yes| F["Commit results then ACK"]
    F --> D
    E -->|No| G["Save checkpoint and allow retry"]
    G --> H
    H --> I["Report drain-ready"]
    I --> J["Terminate instance"]
~~~

In this design, `ACK` always follows result commit. If commit succeeds but `ACK` fails, the message may be redelivered; processing must therefore be idempotent to avoid duplicate side effects.

## 13. Testing the scale-in workflow

### 13.1. Functional testing

In staging, simulate these cases:

- Instance with zero active requests/jobs.
- Instance serving short HTTP requests.
- Instance holding WebSocket or gRPC streams.
- Workers running both short and long jobs.
- Visibility leases nearing expiration.
- Jobs mid-checkpoint.
- Instances holding leader or replica roles.
- Lifecycle hook timeouts.
- Instances killed before draining finishes.

Verify data correctness, execution counts, queue states, request errors, and drain durations.

### 13.2. Concurrent load and scale-in testing

Generate cyclic load ramps and observe:

- Desired capacity vs. actual capacity.
- Number of draining instances.
- Active requests/jobs per instance.
- Queue depth and oldest message age.
- Request error rates and latency.
- Time from scale-in event to termination.
- Job retries, duplicates, and failures.
- Remaining capacity after each batch.

Test what happens when traffic rebounds while some instances are mid-drain. The autoscaler must be able to scale back out without stale drain states blocking or delaying needed capacity.

### 13.3. Fault injection testing

Proactively simulate:

- Killing processes immediately after pulling messages.
- Dropping network connectivity mid-write.
- Letting queue visibility timeouts expire.
- Slowing down or refusing database connections.
- Making lifecycle callbacks unresponsive.
- Sending `SIGTERM` twice.
- Extending jobs past the grace period.

The goal is proving the system recovers accurately: zero lost acknowledged jobs, zero uncontrolled duplicate side effects, and clean continuation after an instance vanishes.

### 13.4. Completion criteria

A scale-in cycle counts as successful only when:

- The instance stopped accepting new work.
- Active requests/jobs finished or persisted recoverable state.
- Messages were acknowledged only after proper commits.
- Leases/locks and partition ownership were released cleanly.
- Quorum and minimum replica counts remained intact.
- The instance deregistered from load balancers/service discovery.
- Surviving capacity meets load and SLOs.
- No orphaned jobs or anomalous error spikes follow scale-in.

## 14. Metrics and alerts to monitor

| Metric | Meaning | Alert when |
|---|---|---|
| Active requests | Requests currently processing on an instance | Fails to drop during drain window |
| In-flight jobs | Claimed but unfinished jobs | Jobs remain active near grace period expiry |
| Drain duration | Elapsed time from drain start to drain-ready | Exceeds target percentile or deadline |
| Drain timeout count | Number of drains hitting timeout | Spikes suddenly |
| Requeued/retried jobs | Jobs reassigned for retry | Spikes abnormally after scale-in |
| Duplicate processing | Signs of duplicate job execution | Duplicate side effects detected |
| Queue oldest age | Age of the oldest queued message | Climbs after reducing workers |
| Lease expiry | Leases expiring while jobs are still active | Increases or stale workers detected |
| Target deregistration time | Time to remove instance from load balancer | Exceeds expected propagation time |
| Remaining capacity | Post-scale-in capacity | Falls below required headroom |
| Scale-in protection count | Instances currently protected | Too high or never decreases |
| Quorum/replica health | Stateful cluster health | Replicas drop below threshold or quorum degrades |

Break down metrics by workload group, zone, and application version. Avoid watching only fleet-wide job totals, because one instance may still hold a long job even when total job counts look low.

## 15. Common mistakes

**Terminating immediately when desired capacity drops.** Desired capacity is a group target, not proof an instance is safe to stop. Always drain and verify first.

**Picking instances solely by CPU.** Low CPU does not prove no critical tasks are running. Inspect active work, leases, and application state.

**Removing an instance from the load balancer without stopping queue polling.** Workers can keep pulling queue jobs even after HTTP traffic stops. Every workload source needs its own drain hook.

**Acknowledging messages before persisting results.** If the machine stops after `ACK`, the message will not be redelivered even though results were never saved. Always commit first, `ACK` second.

**Waiting indefinitely for every job to finish.** One hung job can block scale-in forever. Enforce deadlines, checkpointing, requeueing, and alerts.

**Only increasing the termination grace period.** Longer timers will not fix non-resumable jobs or broken leases. Design proper checkpointing and retries.

**Treating scale-in protection as an absolute guarantee.** Protection has narrow scope; hosts can still disappear due to crashes or external operations.

**Relying on PDBs as the sole Pod safeguard.** PDBs govern only certain voluntary evictions; they do not replace graceful shutdown or block all deletion paths.

**Ignoring long-lived connections.** WebSockets, gRPC streams, and TCP sessions require close notifications, reconnects, or resume logic.

**Never testing sudden machine loss.** Graceful shutdown may never execute. Workloads must survive crashes and retries.

**Scaling in too many instances at once.** Doing so can starve remaining capacity, trigger retry storms, or break cluster quorum. Cap batch sizes and watch headroom.

## 16. Safe scale-in implementation checklist

### Workload design

- [ ] Classified workloads as stateless, queue, batch, stream, or stateful.
- [ ] Identified which state must be durably saved before stopping.
- [ ] Designed jobs to be retryable, resumable, or checkpointed.
- [ ] Used idempotency keys/fencing tokens for side effects and leases.
- [ ] Defined task deadlines and maximum processing durations.

### Draining and shutdown

- [ ] Implemented explicit serving/draining states.
- [ ] Stopped accepting new requests/jobs when draining begins.
- [ ] Deregistered from load balancers/service discovery in proper order.
- [ ] Waited for in-flight requests or signaled clients to reconnect.
- [ ] Renewed leases/visibility timeouts while jobs remain active.
- [ ] Committed results before acknowledging messages.
- [ ] Checkpointed/requeued jobs unable to finish before deadlines.
- [ ] Closed connections and released locks/leases.
- [ ] Configured timeouts and fallbacks when draining stalls.

### Autoscaling and platform

- [ ] Selected scale-in candidates based on workload state.
- [ ] Configured lifecycle hooks/termination notices where supported.
- [ ] Documented scope limits of instance scale-in protection.
- [ ] Configured scale-in stabilization and per-batch removal limits.
- [ ] Maintained adequate minimum capacity and headroom.
- [ ] Protected quorum, replicas, and partition ownership.
- [ ] On Kubernetes, coordinated readiness, `SIGTERM`, `preStop`, and grace periods.
- [ ] Verified which eviction operations are governed by PDBs.

### Testing and operations

- [ ] Tested short requests, long requests, and streaming connections.
- [ ] Tested short jobs, long jobs, lease expirations, and checkpoints.
- [ ] Tested lifecycle hook timeouts and sudden instance loss.
- [ ] Monitored drain duration, active jobs, retries, and duplicate processing.
- [ ] Verified post-scale-in capacity satisfies SLOs.
- [ ] Configured alerts for overly long protection or rising drain timeouts.
- [ ] Documented findings and updated runbooks after incidents.

## 17. Key takeaways

- Scale-in must remove capacity only after workloads stop accepting new work and safely handle active tasks.
- Low CPU does not prove an instance is idle; inspect active requests, jobs, leases, checkpoints, and cluster roles.
- Web/APIs need readiness, deregistration, connection draining, and long-lived connection handling.
- Queue workers must stop polling, maintain valid leases, commit results first, and then `ACK`.
- Long jobs require checkpoint/resume, task splitting, or temporary scale-in protection.
- Stateful services require replication, leader handoff, and quorum checks before removing nodes.
- Lifecycle hooks and scale-in protection assist coordination, yet never replace fault tolerance.
- Kubernetes requires aligning readiness, `preStop`, `SIGTERM`, termination grace periods, and PDBs within their exact scopes.
- Autoscalers should use stabilization, batch limits, and headroom to avoid overly aggressive scale-in.
- Always test both graceful shutdown and sudden instance loss.

## Glossary

| Term | Meaning |
|---|---|
| Scale-in | Decreasing the number of instances or replicas in a compute group. |
| Scale-out | Increasing the number of instances or replicas to handle load. |
| Desired capacity | Target instance count aimed for by the autoscaling controller. |
| Drain | Stopping new work assignment and finishing or handing off in-progress work. |
| Graceful shutdown | Orderly process termination to close connections and save state safely. |
| Lifecycle hook | Mechanism pausing an instance lifecycle transition so automation can run actions. |
| Scale-in protection | Mechanism shielding an instance from certain automated scale-in operations. |
| Termination policy | Rule selecting which instance gets removed from a group. |
| Connection draining | Stopping new connections to a target and letting existing connections finish. |
| In-flight request/job | A request or job that has started but not yet finished. |
| Checkpoint | Saved progress state enabling resumption after a worker changes. |
| Idempotency | Property allowing an operation to run repeatedly without unintended extra side effects. |
| Acknowledgement (ACK) | Confirming a message has been processed per queue system semantics. |
| Visibility timeout | Duration during which a received message stays hidden from other workers. |
| Lease | Time-bounded ownership of a resource or task. |
| Fencing token | Ordered/versioned token blocking stale owners from writing after a lease transfers. |
| Quorum | Number of members required for a cluster to reach consensus or operate per protocol. |
| PodDisruptionBudget | Kubernetes policy limiting certain voluntary disruptions on a Pod group. |
| `terminationGracePeriodSeconds` | Time Kubernetes grants for Pod termination before forcefully killing containers. |
| `preStop` | Container lifecycle hook executed before sending the stop signal. |
| `SIGTERM` | Signal requesting an orderly process shutdown. |
| Retry storm | Surge of simultaneous client retries amplifying load while a dependency fails. |
| Scale-in stabilization | Dampening window before an autoscaler executes capacity reductions. |
