# Maintenance Scheduling by Workload Criticality

## 1. Why Schedule Maintenance by Workload?

Compute systems require updates to operating systems, kernels, firmware, hypervisors, drivers, runtimes, and agents to fix bugs, patch vulnerabilities, maintain compatibility, and preserve performance. However, rebooting a stateless API server is completely different from rebooting a primary database, a GPU node running a multi-day training job, or a controller host for a continuous manufacturing system.

Applying the same maintenance schedule to every workload can disrupt critical services, lose processing progress, break quorum, or breach recovery objectives. Conversely, delaying maintenance too long increases security risk, hardware failure risk, and operational overhead. The proper approach is to classify workloads by criticality, evaluate the impact of each maintenance type, and then select the appropriate timing, deployment strategy, and recovery plan.

In the cloud, maintenance spans multiple layers. The provider may maintain physical hosts or hypervisors; the operations team manages the guest OS, container hosts, runtimes, and applications. Some events can live-migrate workloads; others require a reboot or host replacement. Serverless services reduce host management responsibility, yet still require updates to runtimes, dependencies, function packages, and images controlled by the development team.

After this lesson, learners will be able to:

- Classify workloads by criticality and business impact.
- Use SLO, RTO, RPO, dependencies, and recovery time to determine maintenance windows.
- Distinguish maintenance across hosts, hypervisors, guest OS, container hosts, runtimes, and applications.
- Choose rolling, canary, blue/green, live migration, failover, or checkpointing based on the workload.
- Schedule maintenance for VMs, Kubernetes, databases, GPU/HPC, and serverless workloads.
- Control capacity, approvals, notifications, monitoring, and rollback before and after each cycle.

## 2. Maintenance Scheduling Principles

### 2.1. Criticality Must Reflect Real Impact

Workload criticality indicates the consequences if a workload experiences downtime, performance degradation, or data loss. Do not rely solely on system names or owner titles. Evaluate impact on customers, revenue, safety, compliance, internal operations, and dependent services.

An internal application may be highly critical if it controls a production workflow. A public-facing service may tolerate brief maintenance if it has multiple replicas and automated traffic shifting. Therefore, criticality is a property of the workload within its architectural and business context, not merely a server label.

### 2.2. Planned Maintenance vs. Emergency Maintenance

**Planned maintenance** includes routine updates, version upgrades, firmware replacements, configuration changes, or scheduled host replacements. These activities can be prepared with testing, notifications, spare capacity, and runbooks.

**Emergency maintenance** addresses actively exploited vulnerabilities, severe defects, risk of data loss, or hardware failures. Notification lead times and approval flows may be shortened, but an accountable owner, impact assessment, decision log, and recovery plan are still required. Never use the emergency label to bypass controls for changes that could be scheduled normally.

### 2.3. Do Not Lump All Maintenance Types into One Window

A workload may need separate windows for:

- Security updates that do not require a reboot.
- Kernel or driver updates that require a reboot.
- OS or runtime upgrades involving compatibility changes.
- Provider-announced host/hypervisor maintenance.
- Network, storage, or firmware changes that could affect multiple hosts.
- Recovery testing, failover, and DR drills.

Each type has a different blast radius and time requirement. A library patch in a container image can be released via the application pipeline; a kernel update on a database host may require failing over the primary role before rebooting.

### 2.4. Account for Preparation and Verification Time

A maintenance window is not just the time needed to run an update command. Allocate time for pre-checks, backups or checkpoints, draining traffic, applying the change, waiting for stabilization, and confirming the service meets SLOs. If a window barely covers a reboot with no time for post-reboot verification, the maintenance schedule is incomplete.

## 3. Tiering Workload Criticality

### 3.1. A Reference Tiering Model

Organizations can adopt the four tiers below and tailor them to their industry and internal policies:

| Tier | Characteristics | Examples | Maintenance Approach |
|---|---|---|---|
| Tier 0 – Mission Critical | Outages can cause severe consequences, affecting safety, core transactions, or many other services | Critical control planes, core payment systems, manufacturing control, central identity services | Maintain in small clusters, tested failover, strict approvals, recovery plan and on-call coverage |
| Tier 1 – High Criticality | Outages significantly affect customers or business operations; only brief disruption is acceptable | Core APIs, transactional databases, order platforms, customer authentication services | Rolling/canary, multi-zone redundancy or multiple replicas, off-peak windows |
| Tier 2 – Medium Criticality | Can tolerate limited downtime or slower processing for a bounded period | Internal reporting, batch workers, support systems | Schedule by group, drain or pause jobs, advance notice, recover via runbook |
| Tier 3 – Flexible | Can be stopped and restarted; data is easily recreated or does not serve live business traffic directly | Dev/test, sandboxes, ephemeral runners, staging environments | Automated maintenance on a shared schedule, optimizing for cost and update velocity |

This is a reference classification model, not a mandatory standard. A workload may be tiered differently depending on time of year, region, or peak events. For example, a retail system may require higher protection during a major sales campaign than on normal days.

### 3.2. Determining Criticality Using Key Factors

When assigning tiers, evaluate at least:

1. **Business impact:** How severely does an outage affect customers, revenue, production, or contractual obligations?
2. **SLO/availability target:** What availability level does the service require and how much error budget remains?
3. **RTO:** Maximum acceptable time to restore the service after disruption.
4. **RPO:** Maximum acceptable data loss, expressed as a time interval or recovery point.
5. **Data criticality:** Can data be regenerated or must it be strictly preserved?
6. **Dependency:** Is the workload a shared foundation for many downstream services?
7. **Recovery complexity:** Can failover happen automatically or does it require manual steps and data reconciliation?
8. **Security exposure:** Internet exposure, access privileges, and severity of vulnerabilities to patch.
9. **Maintenance duration:** How long does the update take, and does it require a reboot or migration?
10. **Capacity headroom:** Does the system have enough resources to run while a node or zone is under maintenance?

### 3.3. Distinct Roles of SLO, RTO, and RPO

SLOs describe service quality targets during normal operation, such as request success rate or p99 latency. RTO describes the maximum time to recover after an incident. RPO describes the amount of data loss tolerable during recovery. These metrics complement each other.

A service can have a high availability SLO while accepting a longer RTO for a cold DR environment. Conversely, a batch system may not require continuous availability but needs a very low RPO to avoid re-running hours of data processing. Maintenance schedules must respect both interruption tolerance and state preservation.

### 3.4. Maintenance Priority Matrix

| Criticality | Change Urgency | Handling Approach |
|---|---|---|
| Tier 0/1 | Actively exploited vulnerability or severe safety risk | Trigger emergency process; narrow scope, deploy in small batches, keep on-call engaged and verify immediately |
| Tier 0/1 | Routine patches without active emergency exploitation | Test first, schedule an approved window, ensure failover/capacity, and validate step by step |
| Tier 2 | Security patches or routine upgrades | Group by service, notify in advance, and use rolling updates where possible |
| Tier 3 | Routine updates | Automate on schedule, rebuild from standard images, and monitor outcomes |

Criticality is not an excuse to indefinitely delay severe patches. For Tier 0/1, invest in HA mechanisms, representative test environments, and automation so updates can proceed rapidly with low disruption risk.

## 4. Classifying Maintenance Activities

### 4.1. Host and Hypervisor Maintenance

Cloud providers may announce maintenance events for physical servers, hypervisors, NICs, or storage infrastructure. Depending on the service, the provider may live-migrate VMs, require a reboot, schedule host replacement, or stop instances during a window.

Operations teams must check the event type, scope of affected hosts, deadline, default behavior, and options to defer or self-reboot when offered. Do not assume every service supports live migration or that every migration has zero latency impact. Latency-sensitive workloads or those using GPU passthrough, local devices, or special configurations may face different constraints.

### 4.2. Guest Operating System Maintenance

The guest OS is the operating system inside a VM. Work typically includes updating packages, kernels, system libraries, monitoring agents, security agents, SSH/RDP configurations, and certificates. Kernel or foundational component updates may require a reboot.

Operations teams control images, repositories, patch schedules, reboot policies, and post-update checks. For stateless VMs, replacing hosts with a new image can be easier to control than in-place patching. For stateful VMs, clearly identify data, volumes, network addresses, and application state before replacing hosts.

### 4.3. Container Host and Kubernetes Node Maintenance

Kubernetes nodes may require updates to the OS, kernel, container runtime, kubelet, CNI, CSI, or GPU drivers. Before maintenance, a node is typically cordoned to stop scheduling new pods, then drained to move workloads to other nodes. Consider PodDisruptionBudgets (PDBs), replicas, local storage, DaemonSets, and remaining capacity.

A PDB can block a drain if evicting pods exceeds the allowed disruption budget. This mechanism protects availability; do not bypass PDBs just to finish maintenance quickly. Increase replicas, add capacity, adjust the schedule, or coordinate with workload owners beforehand.

### 4.4. Database and Stateful System Maintenance

Databases may involve primary/replica roles, quorum, transaction logs, replication lag, and failover procedures. Maintenance must ensure replicas are sufficiently synchronized before switching roles. Updating replicas sequentially followed by a controlled failover usually minimizes disruption, though exact sequencing depends on the database engine and vendor guidance.

In quorum-based clusters, never reboot too many nodes simultaneously. Identify the minimum nodes required for quorum, replication health, recovery readiness, and the impact of losing a fault domain. Snapshots do not replace restore-tested backups.

### 4.5. GPU/HPC and Long-Running Job Maintenance

GPU or HPC nodes may run training, simulation, or analytics jobs lasting hours to days. Rebooting mid-job can waste substantial progress if not checkpointed. Maintenance schedules must coordinate with job schedulers, queues, expected completion times, checkpoint capabilities, and replacement node capacity.

You can mark nodes to stop accepting new jobs, let running jobs finish, request checkpoints, and then drain the nodes. For workloads without checkpoint support or with very long runtimes, arrange a dedicated window and coordinate in advance with workload owners. Verify drivers, CUDA/runtime, firmware, and libraries after updating because version mismatches can prevent jobs from starting.

### 4.6. Serverless Maintenance

The provider manages the host and most of the underlying OS for serverless services. Application teams remain responsible for runtime versions, dependencies, function packages, container images, memory/CPU settings, concurrency, triggers, and IAM permissions.

When a runtime is deprecated or needs an upgrade, test on an alias, stage, or small traffic slice first; measure errors, latency, and cold starts; then shift traffic gradually. For event-driven functions, verify retries, idempotency, and dead-letter queues to prevent duplicate processing or dropped events during updates.

## 5. Selecting Maintenance Windows

### 5.1. Based on Workload Traffic Patterns

Do not assume every system should be maintained at midnight. Analyze traffic by hour, day of week, user timezones, batch schedules, reconciliation runs, backup times, and business peaks. Global services may have no shared off-peak hour; in that case, use rolling updates by region or cluster.

For internal systems, windows can align with dependent departments' working hours. For continuous manufacturing systems, coordinate with on-site operations and shift handovers. For financial systems, avoid book-closing or reconciliation periods.

### 5.2. Determining Window Duration

Duration must account for:

- Preparation time, backup/checkpoint verification, and on-call confirmation.
- Time for draining, failover, or traffic shifting.
- Time for installation, reboot, live migration, or node replacement.
- Time waiting for agents, volumes, networks, and supporting services to become ready.
- Time for smoke tests, SLO checks, and post-change observation.
- Buffer time for rollback or recovery.

If an update typically takes 30 minutes, but the system needs 20 minutes for verification and 30 minutes of recovery buffer, a 30-minute window is insufficient. Do not schedule tight windows merely because the update command usually runs fast.

### 5.3. Maintenance Schedules by Tier

Reference schedule example:

| Tier | Reference Window | Strategy | Entry Criteria |
|---|---|---|---|
| Tier 0 | Dedicated window approved by service owner and operations; may be split across multiple phases | Canary, rolling by fault domain, failover | Healthy replicas/quorum, spare capacity, on-call and rollback ready |
| Tier 1 | Off-peak hours per user region | Rolling or blue/green | Stable SLOs, healthy standby backends, tested traffic shifting |
| Tier 2 | Periodic weekly/monthly maintenance window | Small batches, drain and replace | Batches stopped or rescheduled, backups completed |
| Tier 3 | Fixed automated schedule, potentially outside business hours | Rebuild from image or batch update | Recreatable resources, automated verification of results |

Exact timings must rely on operational data and user commitments. This table does not replace the organization's change management process.

### 5.4. Timezones, Notifications, and Freeze Periods

Schedules must explicitly specify timezones, such as `Asia/Ho_Chi_Minh` or UTC, to prevent confusion across distributed teams. Notifications should state scope, affected services, expected start/end times, potential impact, contacts, and escalation steps if the window is exceeded.

A freeze period restricts changes during holidays, sales campaigns, or financial closes. A freeze should not block emergency patching when security or safety risk is high enough; maintain an exception process with proper approvals.

## 6. Risk Assessment Before Scheduling

### 6.1. Change Risk

Assess each change by:

- Impact severity if the change fails.
- Probability of failure based on history, complexity, and version maturity.
- Number of affected nodes, zones, and workloads.
- Ability to roll back or replace rapidly.
- Compatibility with applications, drivers, agents, and dependent services.
- Observability to detect failures early.

Do not schedule patches solely based on CVSS scores or severity labels. Factor in active exploitation, exposure, privileges gained upon exploitation, and the value of affected assets. An actively exploited vulnerability on a public-facing host may require faster action than a less reachable vulnerability in an isolated environment.

### 6.2. Capacity Headroom

Rolling maintenance temporarily reduces available nodes. Before draining a node, verify whether remaining nodes have enough CPU, RAM, GPU, storage IOPS, and network throughput to absorb the workload. Also check cloud quotas, IP limits, load balancer targets, database connections, and standby region capacity.

If a cluster runs near capacity during normal operation, you cannot assume a node can be maintained without service impact. You may need to temporarily scale out, shed load, defer batch jobs, or split maintenance into smaller batches.

### 6.3. Dependencies and Blast Radius

One host may run multiple workloads. A change to DNS, IAM, networking, storage drivers, or the hypervisor can affect more than a single VM. Map dependencies to determine which services must be checked together and avoid maintaining components sharing a fault domain in the same batch.

### 6.4. Go/No-Go Decision

Before starting, the accountable owner must confirm:

- Patches or versions have been tested in an appropriate environment.
- Backups, snapshots, or checkpoints are usable and verified.
- Replicas, quorum, and capacity meet requirements.
- Workload owners and on-call engineers are ready.
- Dashboards, alerts, and runbooks are operational.
- Clear rollout stop criteria and rollback conditions are defined.

If any mandatory condition is unmet, postpone or adjust the scope. For emergency maintenance, document accepted risks and compensating controls.

## 7. Maintenance Deployment Strategies

### 7.1. In-Place Maintenance

In-place maintenance updates the OS or software directly on the existing host. This suits workloads where data and configuration are tied to the host, or where replacement is difficult. It requires backups, package checks, a reboot plan, and the ability to restore the prior version.

Risks include configuration drift across hosts, hard-to-reproduce update failures, and complex rollbacks. For large fleets, use automation and batching rather than manual bulk updates.

### 7.2. Rolling Maintenance

Rolling maintenance updates one node or small batch at a time while the rest continue serving. Typical sequence:

1. Select one node or a small slice as a canary.
2. Drain traffic/jobs and confirm workloads have moved off.
3. Update, reboot, or replace the node.
4. Wait for health checks and inspect metrics.
5. Proceed to the next node only once the canary is stable.
6. Repeat across fault domains to avoid losing too much capacity at once.

Rolling limits blast radius at any moment but requires sufficient capacity and workload distribution mechanisms. If nodes share a rack, zone, or host group with common dependencies, avoid maintaining the entire group simultaneously.

### 7.3. Canary Deployment

Canary deploys the change to a small percentage of nodes or traffic first. Observe error rate, latency, CPU, memory, restarts, logs, and business metrics. If no anomalies appear during the predefined observation window, gradually increase coverage.

Canary is especially useful for kernels, drivers, security agents, runtimes, and new images. Choose canaries representative of production configurations: instance families, zones, CPU architectures, GPUs, storage, and workload groups. A canary running only a trivial app may miss compatibility failures on specialized workloads.

### 7.4. Blue/Green or Immutable Replacement

Blue/green creates a new group of hosts with the updated image or version, validates the new group, and shifts traffic from old to new. Immutable replacement substitutes new hosts for old ones instead of making ongoing in-place edits.

The advantage is easy fallback to the old group when data and state permit. Drawbacks include needing temporary capacity, data synchronization, address management, and handling schema changes. For stateful workloads, traffic cannot simply be shifted if data is not replicated or the application lacks dual-version compatibility.

### 7.5. Live Migration and Host Maintenance

Live migration moves a running VM to another host with minimal disruption when supported by the platform. However, there may be latency spikes, brief pauses, or restrictions with passthrough devices, local disks, GPUs, and special configurations.

If the provider requires a reboot or stop/start, treat it as a potentially disruptive event. Check automation policies, event deadlines, and self-service scheduling options. Workload criticality determines whether failover, scale-out, or a downtime window is needed.

### 7.6. Drain, Pause, and Checkpoint

Draining stops a node from accepting new workloads and migrates or finishes active ones. For queue workers, stop new consumers and wait for in-flight items to finish. For HPC/GPU, the scheduler marks nodes unschedulable for new jobs and requests checkpoints. For containers, use cordon/drain; for load balancers, use connection draining to let active requests complete.

Checkpoints must capture enough state to resume or restart: model/optimizer state, data position, batch progress, configuration, and software versions. Verify that the new version can read the checkpoint before relying on it to protect long-running jobs.

## 8. Maintenance Workflows by Compute Type

### 8.1. Stateless VMs Behind a Load Balancer

For stateless API or web servers with multiple instances:

1. Confirm healthy backend count and remaining capacity.
2. Remove the instance from the target group or enable connection draining.
3. Wait for in-flight requests to complete within the timeout.
4. Update the OS or replace the instance with a new image.
5. Wait for agents, network, application, and readiness checks.
6. Return the instance to the pool; monitor error rate and latency.
7. Proceed to the next instance.

If an autoscaling group or managed instance group manages the fleet, use instance refresh or an equivalent feature. Configure minimum healthy capacity, maximum surge, and proper health checks to avoid replacing too many instances simultaneously.

### 8.2. Stateful VMs

For VMs hosting databases, file services, or local-state apps, first identify whether data resides on boot disks, data volumes, local disks, or external services. Create consistent backups/snapshots, verify replicas, and prepare a failover plan. You may need to transfer roles, detach volumes, or replace the host while preserving persistent volumes.

Never reboot or replace a host solely because the VM was removed from the load balancer. The workload may still serve internal traffic or hold active transactions. Explicitly stop the application or fail over its role per system guidelines.

### 8.3. Kubernetes Nodes

A basic workflow using `kubectl`:

```bash
# Prevent the scheduler from placing new pods on the node
kubectl cordon node-01

# Evict workloads according to the current disruption policy
kubectl drain node-01 --ignore-daemonsets --timeout=10m

# After maintenance and verifying the node is healthy
kubectl uncordon node-01
```

Before running `drain`, check PDBs, replicas, unmanaged pods, DaemonSets, local PVs, `emptyDir`, topology spread, and remaining node capacity. The command may be blocked when a PDB forbids disruption. Do not automatically add flags that bypass controls or delete local data just to force a drain to succeed.

After updating the OS, container runtime, kubelet, or drivers, check node `Ready` status, CNI/CSI, DNS, GPU device plugins, logs, and pod scheduling capability. Test a representative workload before moving to the next node.

### 8.4. Primary/Replica Databases

For replicated databases, a reference sequence is:

1. Check backups, replication lag, quorum, and recovery readiness.
2. Update replicas one node at a time, maintaining sufficient healthy copies.
3. Verify queries, replication, and readiness to assume the primary role.
4. Execute a controlled failover per the runbook.
5. Update the former primary once it is acting as a replica or removed from the cluster.
6. Confirm topology, consistency, backups, and normal application connectivity.

This sequence is illustrative. Rolling upgrade mechanisms, failover behavior, and version compatibility differ across database engines. Never alter the sequence arbitrarily or skip quorum checks required by product documentation.

### 8.5. GPU/HPC Clusters

Mark nodes unschedulable for new jobs; review running jobs and expected completion times. If supported by the scheduler, request job checkpoints or requeuing. Drain only after jobs finish or state is safely saved. Post-maintenance, verify GPU health, ECC, drivers, CUDA/runtime, network fabric, and storage mounts.

For multi-node distributed jobs, evaluate the entire job group. Rebooting a single node can fail the job across all remaining nodes if the framework lacks elastic recovery. Coordinate maintenance with queue policies, reservations, and cluster utilization windows.

### 8.6. Serverless and Managed Runtimes

The provider handles the host OS and most foundational patches. Application teams must still track runtime deprecation notices, update dependencies, build new images, and deploy functions via aliases/stages. Verify concurrency, event retries, idempotency, cold starts, permissions, and logs after switching.

If the provider automatically updates runtimes on a schedule, read compatibility policies and deadlines carefully. Choose the upgrade timing if supported by the service; otherwise, test early in a matching environment and prepare a compatible release.

## 9. Automating Maintenance Schedules

### 9.1. Centralized Schedules and Workload Metadata

Each workload should have minimum metadata:

- Technical owner and business owner.
- Criticality tier and environment.
- SLO, RTO, RPO, and critical dependencies.
- Timezone, maintenance window, and freeze periods.
- Resource type: VM, node pool, database, GPU cluster, or serverless.
- Drain, failover, checkpoint, and rollback methods.
- Notification channels, approvers, and on-call contacts.

A centralized schedule helps detect overlapping maintenance events, such as multiple databases sharing a network cluster or multiple nodes in the same fault domain scheduled to reboot simultaneously.

### 9.2. Patch Rings

Divide the fleet into rings:

| Ring | Scope | Purpose |
|---|---|---|
| Ring 0 – Lab | Test environments and representative hosts | Catch installation, boot, driver, and compatibility issues |
| Ring 1 – Canary | Small group of low-risk workloads or representative nodes | Validate on near-production configurations |
| Ring 2 – Early production | Small production slice by zone/group | Confirm real-world behavior under live traffic |
| Ring 3 – Broad rollout | Remainder of the fleet | Complete rollout once metrics remain stable |

Do not populate canaries solely with atypical hosts. Include representatives of the instance families, CPU architectures, GPUs, storage drivers, and deployment zones you need to protect.

### 9.3. Policy and Automation Guardrails

Automation can run pre-flight checks before executing:

- Is the workload within a valid maintenance window?
- Does the tier require approval or on-call confirmation?
- Does the node have enough replicas and capacity to drain?
- Is there a recent, verified backup/checkpoint?
- Is another event maintaining the same fault domain?
- Is the patch on the tested/approved list?
- Can the host roll back or be replaced if health checks fail?

If checks fail, automation should halt and report why rather than pushing ahead. For emergency changes, use an exception path that records the decision and accountable owner.

### 9.4. Example YAML Schedule

Illustrative internal maintenance schedule data structure:

```yaml
workload: orders-api
criticality: tier-1
owner: platform-orders
timezone: Asia/Ho_Chi_Minh
maintenance:
  type: guest-os-patch
  window:
    day: Sunday
    start: "01:00"
    duration_minutes: 120
  strategy: rolling
  max_unavailable: 1
  prechecks:
    - healthy_capacity
    - backup_status
    - on_call_confirmed
  stop_conditions:
    - error_rate_above_slo
    - p99_latency_above_threshold
  rollback: replace_with_previous_image
```

This is an illustrative schema, not a cloud provider standard format. In practice, add approval rules, blackout dates, change IDs, resource groups, health check criteria, and handling when work cannot finish within the window.

## 10. Monitoring During and After Maintenance

### 10.1. Technical Metrics

Track at least:

- Availability, error rate, request success rate, and p50/p95/p99 latency.
- CPU, memory, disk I/O, network throughput, and packet drops.
- Healthy replica count, pod availability, node Ready status, and target health.
- Database replication lag, quorum, connections, transaction errors, and backup status.
- GPU health, job completion, checkpoint status, and scheduler queues.
- Restart counts, boot duration, agent heartbeats, and package/runtime errors.

### 10.2. Business Metrics

A system can pass technical health checks while still failing business workflows. After maintenance, check successful transaction counts, queue backlogs, processed orders, data synchronization, batch outputs, and users' ability to complete key actions.

For databases, run validation queries and verify replication. For workers, ensure queues are not growing abnormally. For payment systems, verify test transactions and reconcile per approved procedures.

### 10.3. Post-Change Observation Period

Do not stop monitoring as soon as a host boots cleanly. Some failures only surface when load climbs, caches are cold, subsequent jobs start, or batch runs begin. Set an observation period tailored to the workload and SLO, with an assigned observer and clear completion criteria.

### 10.4. Rollout Stop Criteria

Example stop conditions:

- Error rate exceeds threshold for a defined duration.
- p95/p99 latency breaches SLO or spikes abnormally compared to baseline.
- Replicas lose sync, quorum becomes unsafe, or backups/checkpoints fail.
- Nodes fail to return to healthy status within the deadline.
- Remaining cluster CPU, memory, I/O, or network exceeds safe headroom.
- GPU/HPC jobs fail to resume or drivers/runtimes are incompatible.

Thresholds must be defined in advance from real telemetry. When a stop condition triggers, halt further rollout, preserve logs and state, and decide whether to roll back or proceed under control.

## 11. Rollback and Recovery

### 11.1. Define Rollback Before Starting

Rollback may involve reverting to a previous image, restoring packages, shifting traffic back to blue, failing back a database, or recovering from a checkpoint. Some kernel patches can be removed; certain firmware or schema changes are hard to reverse. Explicitly document which steps can roll back automatically and which require manual restore or intervention.

### 11.2. Snapshots Are Not Backups

Snapshots usually capture volume state at a point in time, while application consistency depends on how the snapshot was taken. For databases or multi-volume systems, use quiescing, checkpoints, or application-consistent backups. Test restores before relying on backups as your recovery plan.

### 11.3. When to Roll Back vs. Push Forward?

If an error directly impacts SLOs, data integrity, or security and the root cause is unclear, rolling back can reduce risk. If the issue is a non-impacting warning, you can investigate within the canary scope. Decisions must follow agreed stop conditions rather than schedule pressure.

For databases, rolling back binaries may be incompatible with an upgraded schema. For serverless, older function versions may not understand newer data formats. For containers, older images may fail to read new data formats. Therefore, design for backward compatibility and use expand-and-contract strategies for schema or format changes.

### 11.4. Completion and Post-Maintenance Review

After maintenance, update node status, versions, execution times, check results, incidents encountered, and follow-up actions. If the window was exceeded, notify workload owners and users per procedure. Record actual durations to improve future estimates.

## 12. Workload Scheduling Examples

### Example 1: Tier 1 API on Stateless VMs

A commercial API runs on multiple VMs behind a load balancer, with a high availability SLO and lower traffic during certain hours. Each VM can be replaced from a standard image.

**Schedule and strategy:** deploy canary first, then roll out by zone. Remove each VM from the target group, wait for connection draining, replace with the patched image, and verify readiness. Maintain minimum healthy capacity and never maintain VMs in the same fault domain concurrently.

**Go/no-go criteria:** healthy targets, stable error rate and p99 latency, autoscaling quota available, and on-call confirmed. Halt rollout if errors rise or remaining capacity breaches safe utilization limits.

### Example 2: Tier 0 Database with Primary and Replicas

A database serves core transactions, requires a low RPO, and has replicas in separate fault domains. Rebooting the primary directly risks downtime and failover issues.

**Schedule and strategy:** allocate a dedicated window, verify backups and replication lag, update replicas one node at a time, verify promotion readiness, perform a controlled failover, and then maintain the former primary once it is a replica. Monitor transaction errors, consistency, quorum, and recovery time.

**Go/no-go criteria:** enough healthy replicas, synchronized replication, restorable backups, application supports endpoint switching, and database team on call. If replication lag exceeds threshold, defer failover or halt rollout.

### Example 3: Tier 2 GPU/HPC Cluster with Long-Running Jobs

A GPU cluster runs lengthy training and simulation jobs. Each job can take hours to restart and consumes expensive compute.

**Schedule and strategy:** use the scheduler to stop new jobs on the target node group; let short jobs finish, request checkpoints for long jobs, and requeue per policy. Maintain small node groups, verify drivers, runtime, fabric, and run a representative benchmark job before reopening the queue.

**Go/no-go criteria:** checkpoints verified, no jobs active on target nodes, sufficient replacement capacity, compatible drivers/runtimes, and workload owner agreement on schedule.

### Example 4: Tier 1 Serverless Runtime Upgrade

An order-processing function uses a soon-to-be-deprecated runtime. The provider manages the host, but the application team must upgrade the runtime and dependencies.

**Schedule and strategy:** build the new version, run unit/integration tests, deploy to a test alias, shift a traffic slice, monitor error rate, duration, cold starts, and dead-letter queues, then shift full traffic. Keep the prior version for rollback within data-compatibility boundaries.

**Go/no-go criteria:** successful invocations, no unintended IAM changes, idempotent event handling, working retries and DLQ, and latency within SLO.

## 13. Common Mistakes

- **Using the same window for all workloads:** ignores differing business rhythms, dependencies, and recovery capabilities.
- **Tiering solely by system name:** fails to evaluate business impact, SLO, RTO, RPO, and data criticality.
- **Treating Tier 0 as an excuse not to patch:** critical workloads need safe deployment mechanisms to stay up to date.
- **Maintaining multiple nodes in the same fault domain:** risks losing quorum or all redundant capacity.
- **Draining without checking PDBs/local storage:** can block operations or destroy needed ephemeral data.
- **Rebooting GPU nodes while jobs run:** loses progress if not checkpointed or requeued.
- **Assuming live migration is always disruption-free:** some workloads and devices have limitations or brief pauses.
- **Checking only that the host booted:** misses application, replication, data, and business logic failures.
- **Ignoring capacity headroom:** remaining nodes can overload while part of the cluster is under maintenance.
- **Never testing restores:** backups or snapshots might fail to recover required application state.
- **Having no stop conditions:** rollouts continue even after error rates or latency breach thresholds.
- **Failing to record results:** future maintenance repeats the same errors and estimates duration poorly.

## 14. Pre-, During-, and Post-Maintenance Checklist

### Pre-Maintenance

- [ ] Owner, criticality tier, SLO, RTO, and RPO identified.
- [ ] Maintenance type identified: host, hypervisor, guest OS, container host, driver, or runtime.
- [ ] Window selected based on load, batch schedules, timezone, freeze periods, and user notification.
- [ ] Dependencies, fault domains, quorum, and capacity headroom verified.
- [ ] Patches/images/runtimes tested in a suitable environment.
- [ ] Backups, snapshots, or checkpoints verified along with restore capability.
- [ ] Runbook, approvers, on-call engineer, go/no-go criteria, and stop conditions in place.
- [ ] Drain, failover, live migration, or node replacement procedure defined.
- [ ] Rollback plan, time limit, and overrun escalation path defined.

### During Maintenance

- [ ] Execute according to approved canary or batch size.
- [ ] Drain traffic/jobs before rebooting or replacing nodes.
- [ ] Monitor health, error rate, latency, replication, and capacity.
- [ ] Halt rollout if any stop condition is triggered.
- [ ] Record versions, nodes, timestamps, and step-by-step outcomes.

### Post-Maintenance

- [ ] Verify nodes/VMs/pods/functions are healthy and on target versions.
- [ ] Check technical SLOs and business metrics.
- [ ] Verify replicas, quorum, queues, data integrity, and checkpoints.
- [ ] Monitor through the full observation period.
- [ ] Revoke temporary access, close maintenance access windows, and clean up temporary resources.
- [ ] Update inventory, maintenance schedules, tickets, and runbooks.
- [ ] Document lessons learned and actual duration.

## 15. Conclusion

Scheduling maintenance by workload criticality starts with business impact, SLOs, RTO, RPO, dependencies, and recovery capability. Tier 0/1 workloads require testing, spare capacity, small-batch rollouts, failover, and on-call coverage; Tier 2 can be grouped into periodic windows; Tier 3 generally suits automation and rebuilding from images.

Distinguish host/hypervisor maintenance from guest OS, container host, and application-managed runtime maintenance. Select rolling, canary, blue/green, live migration, drain, or checkpoint strategies based on compute type and data state. A maintenance cycle is complete only when the service is verified both technically and functionally, metrics remain stable throughout the observation period, and outcomes are recorded to improve future scheduling.
