# Spot Interruptions and Interruption-Resilient Workload Design

## 1. What Problem Does Amazon EC2 Spot Solve?

Amazon EC2 Spot lets you run workloads on spare EC2 compute capacity at lower prices than On-Demand. AWS publishes potential savings of up to 90% compared to On-Demand rates, though actual prices and capacity availability depend on instance type, Availability Zone (AZ), time, and system-wide demand.

In exchange, AWS can reclaim a Spot Instance whenever it needs the capacity. An instance may be interrupted even when the application is completely healthy and properly configured. Therefore, Spot suits workloads that can pause, retry, split into small tasks, or shift work onto other workers.

A strong Spot design does not try to keep one specific machine alive forever. It preserves business progress even as workers are replaced. Common techniques include:

- Splitting workloads into small, independent tasks.
- Checkpointing progress to durable storage.
- Using queues to distribute work.
- Processing messages idempotently so retries do not create duplicate side effects.
- Monitoring interruption signals and proactively draining workers.
- Using Auto Scaling Capacity Rebalancing to replace instances at elevated risk of reclamation.
- Combining On-Demand capacity for workload tiers needing stronger capacity assurance.

Spot is a cost optimization mechanism for interruption-tolerant compute. It is neither a capacity guarantee nor an HA substitute for fault-tolerant application design.

## 2. Learning Objectives

After this lesson, learners will be able to:

1. Explain Spot capacity pools, Spot pricing, and interruption causes.
2. Distinguish rebalance recommendations from Spot interruption notices.
3. Describe terminate, stop, and hibernate behaviors upon Spot reclamation.
4. Capture interruption signals from EventBridge and EC2 Instance Metadata Service v2 (IMDSv2).
5. Design a shutdown/drain sequence within the warning window.
6. Use EC2 Auto Scaling Capacity Rebalancing and appropriate allocation strategies.
7. Achieve instance flexibility across multiple instance types and AZs.
8. Combine an On-Demand baseline with flexible Spot capacity.
9. Design interruption-resilient queue workers, batch jobs, containers, and Kubernetes workloads.
10. Use checkpointing, idempotency, retries, and persistent storage to preserve progress.
11. Test interruptions using AWS Fault Injection Service (FIS).
12. Measure cost per completed work unit and build an operational runbook.

## 3. When Should You Use Spot?

Spot fits when work can be retried, distributed, or resumed from checkpoints.

| Workload | Suitability | Design Conditions |
|---|---|---|
| Batch processing | Highly suitable | Small job chunks, retries, and checkpoints |
| CI build/test runners | Suitable | Retryable pipelines; artifacts stored off-instance |
| Queue consumers | Suitable | Ack messages only after commit, idempotent, tuned visibility timeout |
| Stateless web/API tiers | Suitable | On-Demand baseline, multi-AZ, load balancing, and autoscaling |
| Data ETL / analytics | Suitable | Durable intermediate state, partitioned workloads |
| ML training | Conditionally suitable | Frequent model/optimizer checkpoints, resumable training |
| Rendering / transcoding | Suitable | Split by frame/chunk; store outputs off-instance |
| HPC / simulation | Conditionally suitable | Distributed checkpointing, handle worker loss and recommunication |
| Database primary | Unsuitable | Databases require stable, stateful compute |
| Stateful single-node services | Unsuitable | Losing a node risks losing state or taking down the entire service |
| Strict-SLA workloads unable to tolerate capacity shortfalls | Unsuitable | Use On-Demand or appropriate capacity reservations |

Do not judge workload fit solely by whether a process can restart. Evaluate rerun cost, risk of uncommitted data loss, recovery duration, business integrity, and replacement capacity availability.

## 4. Spot Capacity Pools and Flexibility

A Spot capacity pool is a combination of:

- Instance type, such as `m7i.large`.
- Availability Zone, such as a specific AZ within a Region.

Two pools with the same instance type in different AZs count as two separate pools. Capacity in each pool fluctuates with supply and demand.

Allowing only one instance type in one AZ ties the workload to a single pool. When that pool runs low on capacity or faces reclamation, the system has few replacement options.

Increase flexibility by:

- Selecting multiple instance types capable of handling the workload.
- Enabling multiple AZs when data and architecture permit.
- Using attribute-based instance type selection where appropriate.
- Avoiding launch group or Availability Zone group constraints unless strictly required.
- Spreading across multiple pools to diversify risk.

Substitute instance types must match on CPU architecture, vCPU count, memory, GPU, network bandwidth, EBS bandwidth, local NVMe, and licensing. An instance with more vCPUs is not automatically a drop-in substitute if the application is memory- or GPU-bound.

### 4.1. Spot Placement Score

Spot placement score helps estimate how likely a Region/AZ and configuration can fulfill a Spot capacity request. The score reflects capacity conditions at query time, not a guarantee that capacity will remain available at launch or throughout execution.

Use placement scores to compare placement options before launching large fleets. Refresh scores whenever conditions or requirements change.

## 5. Why Do Spot Instances Get Interrupted?

EC2 can reclaim Spot Instances primarily in these situations:

1. **Capacity:** AWS needs the capacity back for other demand, host maintenance, or infrastructure changes.
2. **Price constraint:** if a request sets a maximum price and the Spot price exceeds that threshold, the instance can be interrupted. AWS recommends not setting a maximum price without a specific reason; setting a cap can increase interruption frequency.
3. **Request constraints:** constraints such as launch groups or Availability Zone groups can cause related instances to be reclaimed together when constraints can no longer be satisfied.

Spot prices adjust gradually based on long-term supply and demand and are not the sole indicator of interruption likelihood. A low-priced pool can still face tight capacity. Therefore, picking solely the lowest-priced pool is a poor strategy for minimizing interruptions.

## 6. Three Spot Interruption Behaviors

When creating a Spot request, you can choose an interruption behavior where supported by the service:

| Behavior | Result | When to Consider |
|---|---|---|
| Terminate | Instance is terminated; EBS volumes persist or delete based on volume/lifecycle settings | Standard for fleets/Auto Scaling and replaceable workers |
| Stop | Instance stops; EBS volumes are preserved and only storage charges accrue while stopped | Standalone persistent Spot requests needing to resume the same instance |
| Hibernate | RAM is saved to an encrypted EBS root volume and instance transitions to stopped | Specific apps needing process state resumption and meeting hibernate prerequisites |

Terminate is the default behavior. For stop, the Spot request must be persistent and satisfy Spot request/EC2 Fleet constraints. When matching capacity returns, EC2 can restart the instance per the request.

Hibernation imposes requirements on instance type, AMI, root EBS volume, encryption, RAM, and OS configuration. Data on instance store volumes is lost on hibernation. Never use hibernate for instances in an Auto Scaling group or managed by Amazon ECS; those platforms expect lifecycle replacement under their own models.

**Note on warning time:** for terminate/stop, a Spot interruption notice is typically sent about two minutes before EC2 reclaims the instance. For hibernate, hibernation begins immediately without a two-minute shutdown window. Never build workflows that depend on always getting a full two minutes.

## 7. Two Critical Signals: Rebalance Recommendation and Interruption Notice

### 7.1. EC2 Instance Rebalance Recommendation

A rebalance recommendation signals that an instance faces an elevated risk of interruption. It can arrive earlier than an interruption notice, allowing systems to proactively:

- Stop dispatching new work to the instance.
- Launch replacement capacity.
- Migrate tasks or checkpoint progress for another worker.
- Drain the target from load balancers.
- Flush logs and metadata.

This signal is not guaranteed to arrive before an interruption notice. In some cases, both signals arrive almost simultaneously.

### 7.2. Spot Instance Interruption Notice

An interruption notice warns that EC2 intends to stop or terminate a Spot Instance. For terminate/stop, the warning window is typically around two minutes.

AWS emits notices via:

- EventBridge events.
- Instance metadata on the Spot Instance itself.

Notices are emitted on a best-effort basis. Applications must tolerate interruptions even if an event is never received.

AWS recommends polling the interruption metadata endpoint every 5 seconds. Do not wait until the interruption notice to start checkpointing; use rebalance recommendations for extra lead time.

## 8. Receiving Interruption Notices via IMDSv2

On a Linux Spot Instance, retrieve an IMDSv2 token and poll `spot/instance-action`.

Example:

```bash
TOKEN=$(curl -sS -X PUT \
  "http://169.254.169.254/latest/api/token" \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")

curl -sS \
  -H "X-aws-ec2-metadata-token: $TOKEN" \
  "http://169.254.169.254/latest/meta-data/spot/instance-action"
```

When no interruption is pending, the endpoint returns HTTP 404. This is the normal state, not an error requiring an application restart.

When an action is pending, the response looks like:

```json
{
  "action": "terminate",
  "time": "2026-11-20T08:22:00Z"
}
```

Action values can include `terminate`, `stop`, or `hibernate`. The application should:

1. Poll the endpoint periodically, roughly every 5 seconds.
2. Treat HTTP 404 as no pending interruption.
3. Upon receiving an action, transition the instance to draining state.
4. Stop accepting new work.
5. Write checkpoints and flush data.
6. Report shutdown status back to the control plane if time permits.

Use IMDSv2 and never hardcode tokens. Configure metadata endpoints to require IMDSv2 whenever workloads are compatible.

## 9. Receiving Interruptions via Amazon EventBridge

EventBridge lets you handle interruptions outside the instance. Example rule for Spot interruption notices:

```json
{
  "source": ["aws.ec2"],
  "detail-type": ["EC2 Spot Instance Interruption Warning"]
}
```

Rule for rebalance recommendations:

```json
{
  "source": ["aws.ec2"],
  "detail-type": ["EC2 Instance Rebalance Recommendation"]
}
```

A sample interruption event:

```json
{
  "version": "0",
  "id": "12345678-1234-1234-1234-123456789012",
  "detail-type": "EC2 Spot Instance Interruption Warning",
  "source": "aws.ec2",
  "region": "ap-southeast-1",
  "resources": [
    "arn:aws:ec2:ap-southeast-1a:111122223333:instance/i-0123456789abcdef0"
  ],
  "detail": {
    "instance-id": "i-0123456789abcdef0",
    "instance-action": "terminate"
  }
}
```

EventBridge targets can include Lambda, SQS, SNS, or Systems Manager Automation depending on your workflow. An external handler can:

- Identify the affected workload/ASG/cluster.
- Mark the instance as impending reclamation.
- Stop schedulers from assigning new tasks.
- Trigger checkpoint commands.
- Log an incident record and send notifications.
- Track replacement instance readiness.

Never rely on EventBridge as the sole signal source because interruption notices and rebalance recommendations are best-effort. Pair events with metadata polling and self-healing workload recovery.

## 10. Graceful Shutdown Sequence Under Tight Deadlines

Upon a termination notice, prioritize high-value, fast actions. A typical sequence:

1. Mark the instance `DRAINING`.
2. Stop accepting new requests or tasks.
3. Deregister the target from load balancers or queue consumer pools.
4. Complete in-flight commits if possible.
5. Persist checkpoints to S3, EFS, FSx, or a suitable database.
6. Record task state, offsets, partitions, or leases.
7. Flush critical logs and metrics.
8. Cleanly release distributed locks/leases.
9. Signal the control plane that the instance is ready to terminate.

Do not try to finish a long-running workload inside two minutes. If work cannot finish within the window, checkpoint and hand off the remainder to another worker.

Graceful shutdown needs an internal timeout shorter than the expected deadline. If cleanup cannot finish in time, exit safely and let retry/recovery resume. A hung shutdown script will not prevent EC2 from reclaiming the instance.

## 11. Designing Interruption-Resilient Applications

### 11.1. Stateless Compute

For web/API tiers and microservices:

- Never keep sole session state inside a Spot Instance's memory.
- Store uploads and artifacts in S3.
- Store sessions/caches in appropriate shared services.
- Use an ALB across multiple instances and AZs.
- Maintain an On-Demand baseline if the service requires guaranteed minimum capacity.
- Upon a rebalance recommendation, stop routing new requests to that instance.

Spot works well for load-scaling capacity while On-Demand maintains baseline capacity. Never assume Spot will always be available to meet minimum service capacity.

### 11.2. Checkpointable Jobs

Break long jobs into steps capable of saving progress:

- Read inputs by partition or range.
- Write intermediate outputs to S3/EFS/FSx.
- Write checkpoints containing job ID, partition, offset, step, and version.
- Have new workers read the latest checkpoint and resume.
- Commit final outputs transactionally or with idempotency keys.

Checkpoints must be atomic or versioned so stale workers cannot overwrite newer progress. Never store progress variables solely on local disk or in RAM.

### 11.3. Idempotency and Duplicate Execution

Interruptions can strike after a consumer performs a side effect but before it acknowledges the message. Redelivered messages are normal.

Use business-operation idempotency keys, unique constraints on event/job IDs, conditional writes or transactions, expiring leases/locks, and output paths keyed by job ID/attempt/version.

Processing pattern:

1. Receive message or job.
2. Check idempotency key.
3. Read latest checkpoint/version.
4. Execute a chunk of work.
5. Atomically commit output and state where possible.
6. Acknowledge/delete the message only after commit succeeds.

Never assume a queue delivers exactly once as a guarantee against duplicate application side effects.

## 12. EC2 Auto Scaling Capacity Rebalancing

Capacity Rebalancing lets an Auto Scaling group proactively replace a Spot Instance that receives a rebalance recommendation.

When enabled:

1. EC2 Spot emits a rebalance recommendation.
2. Auto Scaling evaluates and attempts to launch a replacement Spot Instance.
3. The replacement passes health checks.
4. Once the replacement is healthy, Auto Scaling begins terminating the old instance.
5. Lifecycle hooks can perform additional draining/shutdown steps.

This helps get replacements ready before old instances are reclaimed. It does not guarantee a replacement will always launch, as target pools might lack capacity or health checks might fail.

Auto Scaling proactively launches a replacement only when the new pool offers equal or better availability than the instance receiving the rebalance recommendation. If alternative pools have higher interruption risk, Auto Scaling keeps evaluating other pools; the old instance can still be interrupted before a replacement is ready.

Auto Scaling may temporarily exceed the group's maximum size by up to 10% of desired capacity to launch replacements before terminating old instances. Account for headroom and brief overlap costs.

### 12.1. Enabling Capacity Rebalancing

Example:

```bash
aws autoscaling update-auto-scaling-group \
  --auto-scaling-group-name workers-spot-asg \
  --capacity-rebalance \
  --region ap-southeast-1
```

Inspect configuration:

```bash
aws autoscaling describe-auto-scaling-groups \
  --auto-scaling-group-names workers-spot-asg \
  --region ap-southeast-1 \
  --query "AutoScalingGroups[].{CapacityRebalance:CapacityRebalance,Desired:DesiredCapacity,Min:MinSize,Max:MaxSize,AZs:AvailabilityZones,Instances:Instances[].{Id:InstanceId,AZ:AvailabilityZone,Health:HealthStatus,State:LifecycleState}}"
```

### 12.2. Lifecycle Hooks

Lifecycle hooks help drain workers, deregister instances from service discovery, flush logs and checkpoints, capture metadata, and update job states.

However, Spot interruptions have a hard deadline. EC2 can forcibly terminate an instance once the ~2-minute warning window expires even if lifecycle hooks have not completed. Hooks do not extend how long EC2 lets you keep Spot capacity. Treat hooks as a cleanup opportunity, not a guarantee that shutdown will finish.

## 13. Choosing Allocation Strategies and Diversifying Capacity

AWS recommends `price-capacity-optimized` for most Spot workloads. This strategy balances price and capacity depth, picking pools less likely to be interrupted among competitively priced pools.

| Strategy | Supported Services | Behavior | Use Case |
|---|---|---|---|
| `price-capacity-optimized` | Auto Scaling, EC2 Fleet, Spot Fleet | Prioritizes deep capacity pools, then considers price | Best default for most workloads |
| `capacity-optimized` | Auto Scaling, EC2 Fleet, Spot Fleet | Prioritizes pools with highest available capacity | Workloads with high interruption cost |
| `capacity-optimized-prioritized` | Auto Scaling, EC2 Fleet, Spot Fleet | Optimizes capacity while honoring instance type priority on a best-effort basis | Workloads with instance type ordering preferences |
| `diversified` | EC2 Fleet, Spot Fleet | Spreads instances across multiple Spot pools | Large fleets wanting reduced single-pool dependency |

Note: `diversified` is an EC2 Fleet/Spot Fleet strategy and is not among the Spot allocation strategies for EC2 Auto Scaling groups. For Auto Scaling groups, pick one of the strategies supported in current documentation.

Avoid `lowest-price` for production workloads needing availability. That strategy considers only price and may select pools with much higher interruption risk.

### 13.1. Instance Flexibility

For example, a workload needing 4 vCPUs and 16 GiB of memory can evaluate multiple compatible instance families instead of pinning one type. Verify CPU architecture, instruction sets, memory, network/EBS bandwidth, GPU/local storage, AMIs/drivers, and licensing.

With an Auto Scaling mixed instances policy, list multiple instance types across multiple AZs to maximize available Spot pools.

### 13.2. Spot Placement Score Is Not a Reservation

Placement scores reflect relative probability at query time. A high score neither guarantees launch success nor prevents subsequent interruptions. Never treat a placement score as a capacity reservation.

## 14. Combining Spot with On-Demand Capacity

A common pattern maintains an On-Demand baseline for essential load while using Spot for elastic capacity.

Examples:

- On-Demand: minimum API capacity, control planes, coordinators, monitoring.
- Spot: queue workers, batch jobs, rendering, ETL, or replaceable web capacity.
- When Spot pools tighten, the system throttles throughput, buffers backlog in queues, or taps fallback capacity per policy.

In an Auto Scaling mixed instances policy, configure:

- `OnDemandBaseCapacity`: baseline On-Demand capacity count.
- `OnDemandPercentageAboveBaseCapacity`: On-Demand share above the baseline.
- `SpotAllocationStrategy`: Spot pool selection strategy.

Never configure unbounded On-Demand fallback. During Spot shortages, costs can surge sharply if everything spills onto On-Demand. Set quotas, maximum capacities, budget alerts, and admission controls.

## 15. Amazon ECS: Draining Tasks on Spot

### 15.1. ECS on EC2 Spot

If an ECS cluster uses an Auto Scaling group capacity provider:

- Enable managed instance draining where appropriate.
- Configure managed termination protection aligned with scale-in policy.
- Ensure services maintain desired task counts and spread across multiple instances/AZs.
- Tune `minimumHealthyPercent`/`maximumPercent` for deployments.
- Tasks must handle `SIGTERM` and stop accepting new work.
- Set appropriate health checks and load balancer deregistration delays.

ECS managed instance draining transitions container instances to `DRAINING` when replaced or receiving Spot interruption signals. The scheduler attempts to reschedule tasks onto other instances.

When using managed instance draining, you do not also need `ECS_ENABLE_SPOT_INSTANCE_DRAINING` for the same purpose. Configure termination protection and draining properly on the capacity provider; the two features solve different goals.

### 15.2. Fargate Spot

Fargate Spot provides Fargate capacity at Spot rates. When a task is interrupted, ECS emits a warning roughly two minutes prior via a task state change event on EventBridge and sends `SIGTERM` to containers. Applications must handle this signal for controlled shutdown.

Applications should catch `SIGTERM`, stop pulling new requests/jobs, flush outputs and checkpoints, finish cleanup within the window, and let SQS or workflows retry uncommitted tasks.

Fargate Spot does not automatically fail over tasks to Fargate On-Demand when Spot capacity is unavailable. Capacity provider strategies must include standard Fargate capacity if the service needs steady availability.

## 16. Amazon EKS: Interruption-Resilient Nodes and Pods

### 16.1. EKS Managed Node Groups with Spot

EKS managed node groups with `Spot` capacity type configure Auto Scaling groups and Capacity Rebalancing per EKS best practices. Supply multiple instance types to widen capacity pools.

Upon a rebalance recommendation, EKS attempts to launch a replacement node. Once the new node is `Ready`, EKS cordons and drains the old node. If an interruption notice arrives before the new node is `Ready`, EKS still attempts best-effort draining.

Never assume every Pod gets a full two minutes. EKS drains sequentially to protect the Kubernetes API server; when multiple nodes are reclaimed simultaneously or nodes run dense Pods, some Pods may receive signals late or be forcibly terminated.

For Spot workloads:

- Keep Pod `terminationGracePeriodSeconds` short—AWS recommends 30 seconds or less.
- Avoid lengthy `preStop` hooks.
- Use topology spread constraints so replicas do not land on the same node/AZ.
- Use `PodDisruptionBudget` appropriately, but do not treat PDBs as protection against Spot reclamation.
- Persist checkpoints to durable storage.
- Monitor Pod eviction and node termination metrics.

Workloads requiring guaranteed graceful termination should run on On-Demand capacity.

### 16.2. Karpenter Interruption Handling

Karpenter can watch interruption events via an SQS interruption queue. Upon receiving an event, Karpenter taints and drains the node and launches a replacement node for displaced Pods.

When enabling interruption handling:

- Create the queue and EventBridge rules per Karpenter documentation.
- Grant Karpenter IAM permissions to read the queue.
- Configure `--interruption-queue` or the corresponding Helm value.
- Design Pods for disruption and checkpointing.
- Do not simultaneously run AWS Node Termination Handler for the same interruption events without understanding conflicts between the two controllers.

## 17. AWS Batch, EMR, and Data Processing Workloads

### 17.1. AWS Batch

AWS Batch fits jobs capable of retries or checkpointing. When using Spot:

- Split jobs into small pieces.
- AWS recommends checkpointing or splitting jobs into ~30-minute chunks or shorter.
- Avoid multi-hour uncheckpointed runs.
- Configure retry strategies; Batch supports 1 to 10 attempts.
- Start with 1–3 retries and tune based on failure profiles.
- Store checkpoints and outputs in S3/EFS/FSx rather than local-only state.
- Use `evaluateOnExit` to distinguish retryable Spot interruptions from configuration/validation errors that should fail fast.

Retries cannot fix deterministic application failures. If the cause is bad input data or permission denied, transition to `FAILED` and alert instead of retrying endlessly.

### 17.2. Amazon EMR and Spark

Spot fits task nodes or replaceable executor capacity well. For big data:

- Keep source data and intermediate results in S3/HDFS appropriately.
- Size partitions so tasks complete within reasonable durations.
- Use speculative execution or engine task retries where appropriate.
- Avoid placing critical metadata/control planes on Spot.
- Test the impact of losing multiple executors simultaneously.

### 17.3. ML Training and HPC

Checkpoints should include model weights, optimizer state, epoch/step, random seeds, and dataset cursors if reproducibility is required. Version checkpoints and write manifests for clean resumption.

For distributed training, define behavior when a worker disappears: full job restart, elastic training, or checkpoint resumption. Pick the strategy matching your framework and restart cost.

## 18. Queue Workers: A Common Pattern to Leverage Spot

A worker polls SQS messages and processes jobs. Upon receiving an interruption signal:

1. Stop polling for new messages.
2. If actively processing a message, checkpoint progress.
3. If completion fits in remaining time, commit side effects.
4. Delete the message only after commit succeeds.
5. Otherwise, let visibility timeout expire or update visibility so another worker retries the message.
6. Another worker picks it up and resumes from the checkpoint.

Set visibility timeout longer than expected processing time without delaying recovery excessively. For long jobs, call `ChangeMessageVisibility` alongside periodic checkpoints. Configure a DLQ to isolate poison messages.

Never delete a message before committing results. If a worker is interrupted after deleting the message but before writing outputs, work is silently lost.

## 19. Storage and State When an Instance Is Reclaimed

| Storage | On Terminate/Stop | Usage Pattern |
|---|---|---|
| Instance store | Data lost on terminate or stop/start | Ephemeral cache/scratch; never store sole copies |
| EBS volume | Retained or deleted depending on DeleteOnTermination and behavior | Data that must survive instance replacement |
| S3 | Durable per bucket lifecycle/policies | Checkpoints, artifacts, outputs, logs |
| EFS | Shared file system across compute | Shared state or checkpoints |
| FSx | Shared/high-performance file system by type | HPC, ML, and high-throughput workloads |
| DynamoDB/RDS | Durable structured state | Job state, leases, idempotency records |

Hibernation saves RAM to an encrypted EBS root volume via suspend-to-disk, but does not preserve instance store volumes. Never substitute hibernation for application checkpointing: RAM snapshots are not consistent business state, and resuming still depends on Spot capacity availability.

## 20. Cost Model: Measuring Cost per Completed Outcome

Hourly instance price is only one slice of total cost. A Spot workload can look cheap per hour yet cost more per outcome if frequent interruptions cause heavy rework.

Evaluate:

- Spot compute cost plus On-Demand baseline.
- Temporary overlap cost of replacement capacity during Capacity Rebalancing.
- EBS volumes remaining billed while instances are stopped.
- S3/EFS/FSx checkpoint and artifact storage.
- Data transfer, NAT, and cross-AZ traffic.
- CloudWatch logs/metrics and EventBridge/SQS orchestration.
- Reprocessing cost after interruptions.
- Engineering time spent operating and debugging failed jobs.

A practical formula:

```text
Cost per successful unit =
  (Compute + Storage + Network + Orchestration + Rework)
  / Number of successfully completed units
```

Track both throughput and completion time. If interruptions cause excessive reruns, compare total cost against On-Demand.

Spot savings can reach up to 90% off On-Demand, though discounts are not fixed. Prices vary by pool and time; use AWS Cost and Usage Reports/Data Exports and Cost Explorer to measure actual spend.

## 21. Monitoring Interruptions and Operational Effectiveness

Track these signals:

- Count of rebalance recommendations.
- Count of Spot interruption notices.
- Interrupted instances by instance type/AZ/pool.
- Elapsed time from rebalance recommendation to interruption.
- Successful job checkpoints.
- Job retries, failures, and duplicates.
- Queue age and backlog.
- Drain duration.
- Replacement instance launch success rate.
- Cost per completed job.

Use EventBridge to route interruption events to Lambda/SQS or monitoring pipelines. Log instance ID, ASG, instance type, AZ, job ID, and timestamp to identify frequently reclaimed pools.

Do not track raw interruption counts alone. A pool with a higher interruption rate running very short jobs can remain economical, whereas a single interruption on an uncheckpointed long training run can waste hours of compute.

## 22. Security and Safe Operations

- Use IAM instance profiles/IRSA/task roles instead of storing access keys on instances.
- Protect checkpoints and artifacts with KMS encryption.
- Scope S3 prefix read/write permissions by job or service.
- Never place secrets in user data or checkpoints.
- Enforce IMDSv2 and constrain hop limits per architecture.
- Secure EventBridge rules, SQS interruption queues, and Lambda execution roles.
- Log interruptions and shutdowns without logging sensitive payloads.
- Use standardized, regularly patched AMIs.
- Cap maximum capacity to prevent runaway spend during replacements.
- Configure budget alerts for Spot, On-Demand fallback, and storage.

Interruption handlers need least-privilege permissions. A handler that only updates instance/job status and triggers checkpoints should not have rights to administer entire Auto Scaling groups or delete buckets.

## 23. Common Anti-Patterns

| Anti-Pattern | Consequence | Fix |
|---|---|---|
| Using Spot for database primaries | Interruptions disrupt data and availability | Use managed databases/On-Demand compute |
| Picking a single instance type/AZ | Pool exhaustion leaves no fallback | Diversify across instance types and AZs |
| Relying solely on 2-minute notices | Notices are best-effort; rebalance signals may arrive late | Checkpoint periodically and build self-healing recovery |
| Waiting until interruption to start checkpointing | Insufficient time to persist progress | Checkpoint periodically and on rebalance signals |
| Storing sole outputs on instance store | Data vanishes upon reclamation | Use S3/EBS/EFS/FSx appropriately |
| Non-idempotent workers | Retries create duplicate side effects | Idempotency keys and transactional updates |
| Unbounded retries | Poison messages and runaway costs | Retry budgets, DLQs, and alarms |
| Using lowest-price for important fleets | Picks cheap pools prone to reclamation | `price-capacity-optimized` |
| Lifecycle hooks exceeding two minutes | Spot still terminates at hard deadline | Complete cleanup quickly; checkpoint earlier |
| Putting 100% of critical capacity on Spot | Capacity shortfalls across multiple pools | On-Demand baseline and admission controls |
| Using hibernate inside ASG/ECS | Incompatible with managed lifecycle replacement | Use terminate/drain and replacement |
| Tracking only hourly instance rate | Misses rework cost and recovery delays | Measure cost per successful unit |

## 24. Sample Runbook: Spot Worker Receiving an Interruption

### 24.1. Scenario

An Auto Scaling group runs SQS workers on Spot Instances. A worker processing an ETL job receives a rebalance recommendation.

### 24.2. Handling Sequence

1. EventBridge receives `EC2 Instance Rebalance Recommendation`.
2. Handler identifies instance ID, ASG, AZ, and active worker/job.
3. Worker enters `DRAINING` state and stops polling new messages.
4. Worker writes checkpoint with job ID, partition, offset, and output version.
5. Worker commits intermediate output to S3.
6. Worker updates job lease/state in the database.
7. Auto Scaling Capacity Rebalancing launches a replacement instance.
8. Replacement passes health checks and joins the worker fleet.
9. Old worker finishes cleanup, flushes logs, and exits.
10. If an interruption notice arrives before cleanup ends, worker halts; message/lease expires so the new worker resumes.
11. New consumer reads checkpoint, validates version, and continues the job.
12. CloudWatch records completion, retry, and interruption metrics.

### 24.3. Stop Conditions and Escalation

- No valid checkpoint: mark job for restart from the nearest safe boundary.
- Checkpoint checksum/version mismatch: quarantine artifact and refuse to resume from corrupted state.
- Replacement capacity unavailable: retain jobs in queue and throttle producers if backlog breaches thresholds.
- DLQ growing: halt automated redrives and investigate poison messages.
- On-Demand spend breaching budget: lower admission rate or cap fallback per policy.

## 25. Testing Interruptions with AWS Fault Injection Service

AWS provides the ability to initiate Spot interruptions for application testing. Tests can trigger rebalance recommendations, emit interruption notices, and interrupt instances after roughly two minutes according to configured behavior.

Testing workflow:

1. Use a staging environment or lab account.
2. Pick a Spot Instance holding no sole copy of data.
3. Ensure replacement workers/instances or queues preserve work.
4. Enable checkpointing and interruption handlers.
5. Run FIS/EC2 Spot interruption tests per AWS documentation.
6. Observe EventBridge events and IMDSv2 metadata.
7. Verify the worker stops picking up new tasks.
8. Verify checkpoints and logs were persisted.
9. Verify another worker resumes the job.
10. Check for duplicate side effects and DLQ entries.
11. Measure drain time and end-to-end job completion time.
12. Compare results against RTO and cost targets.

Never test interruptions on database nodes or production workloads without rollback plans. Define stop conditions and assign an observer.

## 26. AWS CLI: Inspecting and Configuring Spot Auto Scaling

### 26.1. Enable Capacity Rebalancing

```bash
aws autoscaling update-auto-scaling-group \
  --auto-scaling-group-name batch-spot-asg \
  --capacity-rebalance \
  --region ap-southeast-1
```

### 26.2. Inspect Auto Scaling Group Configuration

```bash
aws autoscaling describe-auto-scaling-groups \
  --auto-scaling-group-names batch-spot-asg \
  --region ap-southeast-1 \
  --query "AutoScalingGroups[].{Desired:DesiredCapacity,Min:MinSize,Max:MaxSize,CapacityRebalance:CapacityRebalance,AZs:AvailabilityZones,Instances:Instances[].{Id:InstanceId,AZ:AvailabilityZone,Lifecycle:LifecycleState,Health:HealthStatus}}"
```

### 26.3. Inspect Spot Interruption History via Request Status

```bash
aws ec2 describe-spot-instance-requests \
  --filters Name=state,Values=active,closed,failed \
  --region ap-southeast-1 \
  --query "SpotInstanceRequests[].{RequestId:SpotInstanceRequestId,InstanceId:InstanceId,State:State.Code,Status:Status.Code,Message:Status.Message,Type:LaunchSpecification.InstanceType}"
```

Use request status together with CloudTrail/CloudWatch to diagnose root causes. Never treat request state counts alone as your sole interruption rate metric.

### 26.4. Inspect Spot Price History

```bash
aws ec2 describe-spot-price-history \
  --instance-types m7i.large m7a.large c7i.large \
  --product-descriptions "Linux/UNIX" \
  --start-time 2026-11-19T00:00:00Z \
  --end-time 2026-11-20T00:00:00Z \
  --region ap-southeast-1
```

Price history helps analyze past costs. It does not reliably forecast future capacity or interruptions.

## 27. Lab Exercise: Building an Interruption-Resilient Worker

### 27.1. Objective

Build a worker fleet with Spot capacity that processes jobs from SQS and resumes work seamlessly after an instance interruption.

### 27.2. Prerequisites

- Lab AWS account.
- An SQS queue and DLQ.
- An S3 bucket for checkpoints and outputs.
- An EC2 Auto Scaling group spanning multiple instance types and at least two AZs.
- A launch template and IAM instance profile.
- An EventBridge rule for rebalance recommendations/interruption warnings.
- CloudWatch logs and alarms.
- A job worker splittable into partitions.

### 27.3. Steps

1. Choose a job divisible into independent partitions.
2. Design checkpoints storing job ID, partition ID, offset, and version.
3. Persist checkpoints to S3 or a database with conditional writes.
4. Make consumers idempotent by job ID/partition/version.
5. Create a Spot Auto Scaling group across multiple instance types/AZs.
6. Select `price-capacity-optimized`.
7. Enable Capacity Rebalancing.
8. Configure workers to poll IMDSv2 and wire the EventBridge handler.
9. Upon rebalance recommendation, stop workers from claiming new jobs.
10. Write checkpoints and commit outputs.
11. Test interruptions in the lab via FIS or EC2 Spot interruption tests.
12. Verify old instances are replaced and jobs resume on new workers.
13. Send duplicate jobs to verify idempotency.
14. Send malformed payloads to verify DLQ routing.
15. Measure interruption count, job retries, completion time, and cost per successful unit.

### 27.4. Completion Criteria

- Multiple Spot capacity pools are available.
- Capacity Rebalancing is enabled.
- Workers catch interruption signals or recover cleanly even if signals are missed.
- Workers stop accepting new work and persist checkpoints.
- Replacement workers resume jobs from valid checkpoints.
- Duplicate executions cause no duplicate side effects.
- Poison messages route to the DLQ.
- Dashboards surface interruptions, retries, backlog, and completions.
- Cost per successful unit is computed and compared against On-Demand.

## 28. Self-Check Questions

### Question 1

What is a Spot Instance?

**Answer:** Unused EC2 compute capacity offered at lower rates than On-Demand, subject to reclamation by AWS when capacity is needed.

### Question 2

What defines a Spot capacity pool?

**Answer:** Instance type and Availability Zone. Each combination is a distinct pool.

### Question 3

How does a rebalance recommendation differ from an interruption notice?

**Answer:** A rebalance recommendation signals elevated interruption risk and may arrive early; an interruption notice warns that the instance is about to be stopped/terminated, typically ~2 minutes in advance.

### Question 4

Can you always rely on getting a full two-minute interruption notice?

**Answer:** No. Notices are best-effort; rebalance signals can arrive late or simultaneously. Workloads must checkpoint periodically and recover autonomously.

### Question 5

Why is `price-capacity-optimized` usually better than `lowest-price`?

**Answer:** It balances price with capacity depth, choosing pools less likely to be interrupted among competitively priced options. `lowest-price` optimizes purely for price and may pick pools prone to frequent reclamation.

### Question 6

What does Capacity Rebalancing in Auto Scaling do?

**Answer:** When a Spot Instance receives a rebalance recommendation, Auto Scaling attempts to launch a replacement first, wait for health checks, and then terminate the old instance.

### Question 7

Can lifecycle hooks extend how long a Spot Instance remains alive indefinitely?

**Answer:** No. Spot has a hard interruption window; instances can be terminated once the warning window expires even if lifecycle hooks are still running.

### Question 8

Why must workers be idempotent?

**Answer:** A worker may be interrupted after committing side effects but before acknowledging the message. Redelivered messages must not produce duplicate business side effects.

### Question 9

Why should checkpoints never live solely on instance store volumes?

**Answer:** Instance store data is lost on stop or terminate. Checkpoints must reside on durable storage or shared databases.

### Question 10

Do EKS Spot Pods always get a full two minutes of graceful shutdown?

**Answer:** No. EKS drains on a best-effort basis and can lag when many nodes are reclaimed or nodes are densely packed. Workloads should use short termination grace periods and checkpoints.

### Question 11

What does AWS Batch recommend for jobs running on Spot?

**Answer:** Split or checkpoint jobs into short units (~30 minutes or less) and configure appropriate automated retries.

### Question 12

Should Spot efficiency be measured by hourly instance price or cost per successful unit?

**Answer:** Cost per successful unit captures compute, storage, network, orchestration, and rework costs, making it far more accurate for real-world evaluation.

## 29. Production Checklist

### Workload Fit

- [ ] Workload can retry, checkpoint, or redistribute.
- [ ] Spot is not used for database/stateful primaries or critical control planes.
- [ ] On-Demand baseline covers non-interruptible capacity.
- [ ] Rework costs and recovery time are accounted for.

### Capacity Strategy

- [ ] Multiple compatible instance types are configured.
- [ ] Multiple appropriate AZs/pools are included.
- [ ] Allocation strategy is `price-capacity-optimized` or another explicitly justified strategy.
- [ ] No single-pool dependency exists.
- [ ] Capacity Rebalancing is enabled when using Auto Scaling.
- [ ] Headroom exists for replacements and maximum capacity is capped.

### Interruption Handling

- [ ] Rebalance recommendation handler is implemented.
- [ ] Spot interruption handler via EventBridge and/or IMDSv2 is implemented.
- [ ] Team recognizes notices are best-effort and may arrive late.
- [ ] Workers stop accepting new tasks while draining.
- [ ] Periodic checkpointing is active.
- [ ] Shutdown completes faster than the deadline.
- [ ] Design does not depend on lifecycle hooks holding instances past hard deadlines.

### Application Reliability

- [ ] Consumers are idempotent.
- [ ] Messages are acknowledged only after commits succeed.
- [ ] Retry budgets and DLQs are configured.
- [ ] Checkpoints reside on durable storage.
- [ ] Versioning/leases prevent stale workers from overwriting newer checkpoints.
- [ ] Duplicate and out-of-order handling is implemented where needed.

### Service Integration

- [ ] ECS managed draining/Fargate Spot is properly configured.
- [ ] EKS Spot node groups span multiple instance types with Pod disruption design.
- [ ] Karpenter interruption queue has appropriate IAM/resource permissions.
- [ ] AWS Batch jobs include retries and checkpoints.
- [ ] Sole copies of state are never stored on Spot workers.

### Monitoring and Cost

- [ ] Interruption/rebalance metrics are tracked.
- [ ] Queue age/backlog and DLQ alarms are active.
- [ ] Job retry, checkpoint failure, and completion metrics are tracked.
- [ ] Cost per successful unit is measured.
- [ ] Budget alerts and caps on On-Demand fallback are configured.
- [ ] Interruptions have been tested in lab/staging environments.

## 30. Official References

### EC2 Spot and Interruptions

- [Amazon EC2 Spot best practices](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/spot-best-practices.html)
- [Spot Instance interruptions](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/spot-interruptions.html)
- [Spot Instance interruption notices](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/spot-instance-termination-notices.html)
- [EC2 instance rebalance recommendations](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/rebalance-recommendations.html)
- [Behavior of Spot Instance interruptions](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/interruption-behavior.html)
- [Billing for interrupted Spot Instances](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/billing-for-interrupted-spot-instances.html)
- [Spot placement score](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/how-sps-works.html)

### Auto Scaling and Allocation

- [Capacity Rebalancing in Auto Scaling](https://docs.aws.amazon.com/autoscaling/ec2/userguide/ec2-auto-scaling-capacity-rebalancing.html)
- [Spot allocation strategies](https://docs.aws.amazon.com/autoscaling/ec2/userguide/allocation-strategies.html)
- [EC2 Fleet and Spot Fleet allocation strategies](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-fleet-allocation-strategy.html)
- [Gracefully handle instance termination](https://docs.aws.amazon.com/autoscaling/ec2/userguide/gracefully-handle-instance-termination.html)
- [Mixed instances policy](https://docs.aws.amazon.com/autoscaling/ec2/userguide/ec2-auto-scaling-mixed-instances-groups.html)

### ECS, EKS, and Batch

- [ECS managed instance draining](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instance-draining.html)
- [ECS Fargate capacity providers and Spot notices](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-capacity-providers.html)
- [EKS managed node groups](https://docs.aws.amazon.com/eks/latest/userguide/managed-node-groups.html)
- [EKS Karpenter best practices](https://docs.aws.amazon.com/eks/latest/best-practices/karpenter.html)
- [AWS Batch Spot best practices](https://docs.aws.amazon.com/batch/latest/userguide/bestpractice6.html)
- [AWS Batch automated job retries](https://docs.aws.amazon.com/batch/latest/userguide/job_retries.html)

### Testing and Operations

- [Initiate a Spot Instance interruption](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/initiate-a-spot-instance-interruption.html)
- [AWS Fault Injection Service](https://docs.aws.amazon.com/fis/latest/userguide/what-is.html)
- [Amazon CloudWatch User Guide](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/WhatIsCloudWatch.html)
