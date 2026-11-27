# Changing CPU, Memory, and Machine Type in the Workload Lifecycle

An application's resource demand changes with user volume, data growth, software releases, and business cycles. A virtual machine that is sufficient at initial deployment may become overloaded after a few months; conversely, an over-provisioned machine kept for headroom can cause prolonged waste. Therefore, selecting CPU, RAM, and machine type should be treated as a decision that can be evaluated and adjusted throughout the workload lifecycle.

Changing a virtual machine's configuration is typically called **resizing** or **vertical scaling**. Depending on the platform and machine type, the operation may occur while the machine is running, require a reboot, require stopping the machine, or require creating a new machine and migrating the workload. This lesson covers how to choose the right approach, prepare application state, execute controlled changes, and verify after resizing.

## 1. Why Change Configuration During the Workload Lifecycle?

Initial sizing is usually based on forecasts. Once a system enters production, actual telemetry shows how CPU, memory, network, and storage demand differs from initial assumptions.

Common reasons:

- **Load growth:** higher request rates, concurrent users, or data volume make CPU or RAM a bottleneck.
- **Application changes:** new releases may increase worker counts, heap sizes, caches, or processing requirements.
- **Business cycles:** month-end, peak seasons, or campaigns can create bursty demand.
- **Cost optimization:** consistently idle machines can be downsized to save money.
- **Workload shifts:** an API service may evolve into data processing, caching, or compute-intensive tasks.
- **New hardware requirements:** the application needs newer CPU generations, more RAM, faster networking, GPUs, or different storage devices.
- **Availability needs:** machine sizing must align with redundancy models, failover behavior, and recovery time.

Do not resize solely because of a few-minute spike in a single metric. Examine trends, sustained duration, latency, throughput, errors, and related resources to pinpoint the true cause.

## 2. What Are Resizing and Vertical Scaling?

Vertical scaling changes the amount of resources on a single machine or node, typically by selecting a larger or smaller machine type. For example:

- Increasing from 2 to 4 vCPUs when the workload is CPU-bound.
- Increasing from 8 to 16 GiB of RAM when the working set no longer fits in memory.
- Switching to a memory-optimized family when the application needs a high RAM-to-vCPU ratio.
- Choosing a machine type with higher network bandwidth or I/O limits when the current machine hits those ceilings.
- Downsizing from 8 to 4 vCPUs and from 32 to 16 GiB of RAM when utilization stays consistently low.

Distinguish three scaling approaches:

| Change Method | Description | When Appropriate | Impacts to Consider |
|---|---|---|---|
| Scale up | Increase resources of a single machine | Workloads hard to split, needing large RAM or high single-node performance | Higher unit cost, upper limits, may require restart |
| Scale down | Decrease resources of a single machine | Machine has been over-provisioned over a sustained period | Risk of insufficient headroom afterward; monitor peak loads |
| Scale out/in | Add or remove machines | Stateless or partitionable workloads | Requires load balancing, orchestration, state synchronization, and autoscaling |

Scale up and scale down alter the capacity of individual machines. Scale out and scale in alter the number of machines. Both can be combined: a pool of adequately sized nodes that also scales node count up and down with demand.

### Not Every Change Is Just Adding CPU and RAM

A machine type is typically a bundle of resources. When switching machine types, beyond vCPU count and RAM, the following attributes may also change:

- CPU generation, x86-64 or Arm architecture, and single-threaded performance characteristics.
- CPU-to-RAM ratio and NUMA topology.
- Network bandwidth, packets per second, and number of network queues.
- Machine-level storage IOPS and throughput limits.
- Number or availability of local disks.
- GPUs, accelerators, or device partitioning capabilities.
- Maximum number of attached volumes, NICs, or peripheral devices.
- Support for live migration, hibernation, confidential computing, or other platform features.

Therefore, you cannot simply compare vCPU counts before and after. Compare the full specification of each machine type.

## 3. Mechanisms for Changing CPU and Memory

### Hot Changes (Hot-Add / Hot-Remove)

Some platforms support adding or removing CPU and/or RAM while the virtual machine is running. This mechanism is commonly called hot-plug or hot-add/hot-remove.

For it to work, all of the following must be met simultaneously:

- The hypervisor and machine type support hot changes.
- The guest OS detects and brings the new resources online.
- The kernel, drivers, and boot configuration permit hot-plugging.
- The application or runtime can recognize resource changes dynamically.
- The platform does not require a restart for that specific change type.

Some operating systems may detect newly added CPUs while the application still keeps a thread pool sized to the CPU count at startup. Similarly, the OS may see new RAM while a JVM or application with a fixed heap configuration does not automatically raise its memory limit.

Hot-add does not mean every change is zero-disruption. Capabilities and limits vary by provider, hypervisor, machine type, OS, and configuration. Always check the documentation for the exact SKU before planning.

### Changes Requiring a Restart

Some resize operations work by stopping or restarting the machine. The system updates the allocated resources at the hypervisor layer and boots the OS again with the new configuration.

Potential impacts include:

- The service temporarily stops accepting requests.
- Existing TCP connections and sessions are dropped.
- In-RAM caches are lost and require warm-up.
- Processes must restart.
- IP addresses, host placement, or device states may change depending on platform and configuration.
- The machine may have to wait for hardware capacity in the target cluster.

If the application runs on a single machine, schedule a maintenance window or plan to shift traffic to another node before stopping the machine.

### Stopping the Machine Before Changing Machine Type

Many platforms require the VM to be in a stopped/deallocated state before changing certain machine attributes. Stopping allows the platform to release current allocations and apply the new configuration on startup.

Distinguish stop states carefully:

- Reboot: restarts the OS; may stay on the same host or keep the same resources depending on the platform.
- Stop/start: stops the machine and reallocates resources on start; may change the host and public IP address if not using a static IP.
- Deallocate: releases compute capacity from the cluster; may require reallocation on start.
- Suspend/hibernate: saves state via a platform-specific mechanism; not always compatible with changing machine type.

Exact state names and semantics vary across providers. Before operating, confirm whether the command you run is restart, stop, or deallocate, and which data is affected.

### Replacing the Machine with a New Configuration

When in-place resizing is unavailable, a new architecture is needed, or CPU architecture changes, you can provision a new VM from an appropriate image and migrate the workload.

This pattern is commonly called replace, blue-green, or migration. It allows testing the new machine before cutting over traffic, but requires managing data, network addresses, machine identity, certificates, sessions, and application dependencies.

For stateful systems, implement data synchronization or ownership handover mechanisms to avoid data loss or split writes.

## 4. When Should You Increase CPU?

CPU is typically the bottleneck when the workload requires more computation than current processing capacity provides. Common signs include:

- Sustained high CPU utilization during load periods.
- Growing run queue or number of processes waiting for CPU.
- Rising p95/p99 latency as concurrency increases.
- Throughput plateaus even as incoming request rate rises.
- CPU throttling or hitting CPU quotas in containerized environments.
- Batch jobs completing slower than target SLAs.

High CPU does not always mean more vCPUs are needed. The application might have an infinite loop, lock contention, excessive data processing, continuous retries, or an inefficient algorithm. Profile before resizing.

### Increasing vCPU Count

Adding vCPUs helps when the application can genuinely execute in parallel. For example, a service handling many independent requests or a worker pool can utilize additional cores.

However, a single sequential thread will not necessarily run faster with more vCPUs. Other factors such as clock speed, IPC, caches, NUMA, and platform CPU limits also matter.

### Switching to a Compute-Optimized Family

If the workload is frequently CPU-bound while RAM has ample headroom, a compute-optimized family may be worth testing. Compare both single-threaded and multi-threaded performance, CPU generation, architecture, and price per unit of work.

Do not assume compute-optimized is faster for every task. A memory-bound or I/O-bound workload may see no improvement from switching families.

### Checking the Application After Increasing CPU

After resizing, verify:

- The number of CPUs recognized by the operating system.
- Application worker counts, thread pools, and connection pools.
- CPU affinity or cpuset settings, if configured.
- Cgroup limits, container requests/limits, and quotas.
- Whether the JVM or runtime updated its available CPU count.
- Whether throughput and latency improved proportionally.

Some runtimes detect available cores at startup. If CPU is changed without restarting the application, thread pool configurations may remain unchanged.

## 5. When Should You Increase RAM?

RAM is typically the bottleneck when the workload's working set exceeds available memory or when the application needs a larger cache to meet latency targets.

Possible symptoms:

- Sustained low available memory.
- Increased swap-in/swap-out activity.
- Rising major page faults or memory pressure.
- Processes terminated by OOM killer or containers showing `OOMKilled`.
- Frequent garbage collection or prolonged GC pauses.
- Rising cache evictions and falling cache hit rates.
- Latency increases as dataset size or concurrency grows.

Distinguish genuine RAM shortage from a memory leak. If a process continuously retains more memory without load increasing, adding RAM may only delay a crash. Investigate object retention, native memory, unbounded caches, and buffers before scaling up the machine.

### Increasing RAM Capacity

Increasing RAM is appropriate when the working set is legitimate and data needs to stay in memory. Estimate peak usage including OS, runtime, caches, buffers, thread stacks, agents, and headroom.

For JVMs, increasing machine RAM does not automatically increase **-Xmx**. Re-evaluate maximum heap size while leaving room for metaspace, direct buffers, native memory, thread stacks, JIT, and agents.

For containers, increasing node RAM does not automatically raise pod/container memory limits. Requests and limits must be adjusted based on scheduler policies and actual usage.

### Switching to a Memory-Optimized Family

If an application needs high RAM per vCPU, memory-optimized instances can reduce over-provisioning of CPU. Check the RAM/vCPU ratio, memory bandwidth, NUMA, CPU generation, networking, and I/O limits for the machine series.

### Checking After Increasing RAM

After resizing, verify:

- The operating system recognizes the full new RAM capacity.
- The new memory is online and allocatable.
- Swap usage and memory pressure decrease.
- Heap, cache, or application limits have been tuned accordingly.
- Container limits and scheduler resource requests align.
- Throughput, latency, and OOM rates improve.
- The cost increase is justified by the observed benefit.

## 6. Choosing a New Machine Type for the Workload

Before changing machine types, create a comparison table between the current configuration and candidate configurations.

| Component | Questions to Answer |
|---|---|
| CPU | How many vCPUs? Which CPU generation? x86-64 or Arm? What are single-threaded/multi-threaded capabilities? |
| RAM | How much capacity? Is the RAM/vCPU ratio suitable? Are there hot-add limits? |
| Network | Do bandwidth, PPS, latency, and interface limits change? |
| Storage | Do VM-level IOPS/throughput limits change? Are there local/ephemeral disks? |
| GPU/Accelerator | Are accelerators needed? Are drivers and frameworks compatible? |
| NUMA | Does the node count and vCPU/RAM layout affect the workload? |
| Availability | Are live migration, restart, or in-place resize supported? |
| Region and Quota | Is the machine type available in the target region/zone? |
| Cost | How do compute, disk, network, licensing, and reservation costs change? |

### CPU Architecture Changes

Migrating from x86-64 to Arm can reduce costs or improve efficiency for compatible workloads, but it is rarely a direct in-place resize. Verify that the image, kernel, drivers, binaries, native libraries, security agents, and licenses support the new architecture.

If an application relies on architecture-specific binaries, you typically must rebuild or use a different image. For critical workloads, provision new machines on the target architecture, run tests, and shift traffic gradually.

### Changing GPUs or Accelerators

GPU machine types can have specific requirements for drivers, runtimes, firmware, and deployment zones. When moving from a non-GPU to a GPU machine, verify that the OS detects the device, the framework sees the right GPU, and the workload actually utilizes it.

When downsizing or removing GPUs, verify that the application no longer depends on CUDA/ROCm or device libraries. Some images and services may fail to start if expected drivers or devices are absent.

### Checking Local Disks and Temporary Data

Some machine types include local SSD/NVMe or ephemeral disks. When switching machine types, the count, capacity, or lifecycle of these disks may change. Data on local disks may be lost on stop, deallocate, host migration, or machine replacement depending on the platform.

Before resizing, classify data:

- Durable data that must survive the machine lifecycle.
- Regenerable caches.
- Disposable temporary data.
- Logs or checkpoint files that must be moved to persistent storage.

Never rely on local disks as the sole copy of important data.

## 7. Pre-Resize Evaluation Process

### Step 1: Define the Change Objective

State the problem to solve and desired outcome clearly. Examples: reduce p95 below a threshold, prevent OOMs, shorten batch jobs, or cut monthly costs.

Without clear success metrics, it is difficult to evaluate whether resizing worked.

### Step 2: Collect Baseline Metrics

Gather metrics over a period representative of both normal and peak load:

- CPU utilization, run queue, and throttling.
- Available RAM, working set, RSS, swap, and OOM events.
- Disk IOPS, throughput, queue depth, and latency.
- Network throughput, PPS, retransmissions, and packet drops.
- Request rate, concurrency, p95/p99 latency, and error rate.
- Hourly cost and utilization.

Note schedules of batch jobs, backups, deployments, and periodic tasks so a brief spike is not mistaken for sustained demand.

### Step 3: Identify the True Bottleneck

If CPU is high while throughput stays flat, profile the application and inspect locks, retries, and thread contention. If RAM is high, distinguish a legitimate working set from a leak. If latency climbs while CPU and RAM have headroom, check disks, networking, external dependencies, and service limits.

Only resize the component tied to the bottleneck. Adding CPU will not fix a slow disk; adding RAM will not fix packet loss.

### Step 4: Select One or More Candidate Configurations

Compare machine types against the workload and associated limits. Consider testing a larger size within the same family before switching families. For specialized workloads, test a memory-optimized or compute-optimized machine to measure performance per unit cost.

### Step 5: Verify Platform Conditions

Confirm machine type availability in the target region/zone, sufficient quotas, and whether reservations/capacity match. Check stop requirements, live resize support, licenses, CPU architecture, local disks, and security features.

### Step 6: Plan the Change and Rollback

Define the timing, owner, execution order, health checks, and abort criteria. Record the current machine type, application configuration, network addresses, volumes, metadata, and exact steps to revert to the previous configuration.

### Step 7: Test in Staging or on a Single Node First

If running a cluster, test on one node or a small group first. Validate application behavior, performance, and dependencies before rolling out across the entire system.

## 8. Preparing Application and Data Before Stopping the Machine

Resizing may restart the machine or move it to another host. Determine application state before proceeding.

### Stateless Workloads

For stateless services, drain the node from the load balancer, wait for in-flight requests to complete, resize, and return the node to rotation. Ensure health checks gate traffic until the application is ready.

### Stateful Workloads

For databases, queues, or services holding state in memory, prepare a concrete plan:

- Identify replicas or standby nodes.
- Check replication lag and sync status.
- Fail over primary/leader roles if supported by the architecture.
- Pause writes or quiesce the workload as required.
- Create consistent backups or snapshots.
- Ensure data on local disks is migrated or recoverable.
- Test startup and recovery procedures after restart.

Disk snapshots taken while an application is actively writing may only be crash-consistent. For databases, use appropriate backup or quiesce mechanisms to guarantee application-level consistency.

### Connections and User Sessions

Restarting can drop TCP connections, in-memory sessions, and active tasks. Services should support controlled retries, externalized sessions, or graceful shutdown. If requests have side effects, ensure idempotency to avoid duplicate processing when clients retry.

### Verifying Backups and Recoverability

A backup is only useful if it can be restored. Before risky changes, verify backup timestamps, data scope, access permissions, encryption keys, and recovery time. Never treat snapshots as a complete substitute for application-level backups when strict consistency is required.

## 9. Performing an In-Place Resize

Operation names in the console, CLI, or API vary by provider. General workflow:

1. Record the current configuration and running image/version.
2. Verify snapshots/backups, local data, and application status.
3. Drain traffic or shift workloads to other nodes if needed.
4. Stop or restart the machine as required by the resize type.
5. Select the new machine type and confirm the change.
6. Start the machine.
7. Verify the OS detects the expected CPU, RAM, and devices.
8. Check volumes, networking, drivers, and agents.
9. Start the application and wait for health checks to pass.
10. Return the machine to service and monitor metrics.

Avoid making multiple hardware changes at once without a baseline. Changing CPU family, RAM, networking, and storage simultaneously makes it hard to determine which change caused improvements or regressions.

### Post-Resize Checks on Linux

The following commands help verify OS-detected resources:

~~~sh
lscpu
nproc
free -h
cat /proc/meminfo
lsblk
ip -brief address
dmesg --level=err,warn
~~~

You can inspect additional devices and topology with:

~~~sh
lscpu -e
numactl --hardware
df -h
systemctl --failed
~~~

Not every image has `numactl`. Output from `lscpu` and `free` reflects the guest OS view; cross-check against machine metadata reported by the platform.

### Post-Resize Checks on Windows

PowerShell can inspect OS-detected hardware configuration:

~~~powershell
Get-CimInstance Win32_ComputerSystem |
  Select-Object NumberOfLogicalProcessors, TotalPhysicalMemory

Get-CimInstance Win32_Processor |
  Select-Object Name, NumberOfCores, NumberOfLogicalProcessors

Get-CimInstance Win32_OperatingSystem |
  Select-Object TotalVisibleMemorySize, FreePhysicalMemory
~~~

Compare the output against the VM configuration and check Event Viewer for driver, device, or service startup errors.

## 10. Replacing the Machine with a New Configuration

When in-place resizing is unsupported or major architectural changes are needed, provision a new machine.

A simple blue-green workflow:

~~~mermaid
flowchart TD
    A["Measure load and choose new machine type"] --> B["Provision new VM from tested image"]
    B --> C["Attach appropriate configuration, identity, and permissions"]
    C --> D["Sync data or join cluster"]
    D --> E["Smoke tests and benchmarks"]
    E --> F{"Health checks pass?"}
    F -- "No" --> G["Keep traffic on old machine and investigate"]
    F -- "Yes" --> H["Shift traffic gradually"]
    H --> I["Monitor errors, latency, and throughput"]
    I --> J{"Stable?"}
    J -- "No" --> K["Fail traffic back to old machine"]
    J -- "Yes" --> L["Complete cutover and retire old machine"]
~~~

### Components to Migrate

- Compatible image or operating system.
- Persistent data volumes and filesystems.
- Network configuration, firewalls/security groups, and routes.
- Identity, roles, service accounts, and access permissions.
- Secrets, certificates, and runtime configurations.
- Monitoring, logging, backup, and security agents.
- DNS, load balancers, service discovery, and endpoints.
- Hardware/instance-bound licenses or activations, if applicable.

Do not copy the old machine's machine identity, host keys, or unique certificates onto the new machine if doing so creates duplicate identities. Use a fresh identity provisioning workflow and re-register agents.

### Data Synchronization and Traffic Cutover

Depending on the workload, use replication, snapshots, backup/restore, or application-level sync. For databases, define the cutover window, replication lag threshold, and safeguards against dual-primary writes.

Shifting traffic incrementally surfaces problems early. Start with a small fraction of requests, monitor error rates and latency, and scale up as stability is confirmed.

## 11. Post-Resize Verification

After making the change, verify both resources and application outcomes.

| Category | Metrics or Checks | Expected Outcome |
|---|---|---|
| CPU | Detected vCPUs, utilization, run queue, throttling | New resources recognized; CPU bottleneck relieved if that was the cause |
| RAM | Available RAM, working set, swap, OOM, heap | No new memory pressure; application utilizes the increased capacity properly |
| Storage | IOPS, throughput, latency, mounts, and filesystems | Volumes operate properly without data loss or unexpected degradation |
| Network | IP, routes, DNS, throughput, packet loss | Internal and external connectivity work as expected |
| Application | Health checks, error rate, p95/p99, throughput | SLOs are met |
| Security | Identity, roles, agents, certificates, policies | Permissions and security controls remain intact |
| Cost | Machine price, disk, network, reservations | Actual costs align with targets |

Monitor long enough after resizing to cover a representative load cycle. A quick check right after boot may miss cache warm-up, batch jobs, peak hours, or memory leaks.

### Signs You Need to Roll Back

- The machine fails to boot or drivers do not recognize devices.
- The application fails to start or health checks fail.
- Latency or error rates worsen significantly.
- Network or storage throughput is lower than before.
- OOMs, crashes, or kernel errors occur.
- SLOs cannot be met after the defined stabilization window.
- Cost increases outweigh expected benefits.

If rollback means switching back to the previous machine type, verify that old machine capacity is available and quotas/reservations still apply. If you migrated to a new machine, keep the old machine during the validation period so traffic can fail back if needed.

## 12. Autoscaling and Periodic Right-Sizing

Not every load fluctuation requires manual resizing. If workloads vary hourly or seasonally, autoscaling can adjust node or instance counts automatically.

### Manual Vertical Scaling

Appropriate when:

- Load grows over the long term and is predictable.
- Current machine sizing is no longer adequate.
- Changes are infrequent and can fit maintenance windows.
- The workload is hard to partition or requires a single large node.

### Vertical Pod Autoscaler and Node Autoscaling

In Kubernetes, the Vertical Pod Autoscaler (VPA) can recommend or adjust pod CPU/memory requests based on metrics and policies. Some update modes may require pod restarts. A node autoscaler can add or remove nodes when pods become unschedulable or nodes are underutilized.

Distinguish clearly:

- VPA adjusts requests/limits per policy; it does not automatically transform a node into a different hardware type in every environment.
- Cluster/node autoscalers change the number of nodes or node pools.
- Changing node machine types usually involves creating new nodes and draining old ones.
- Pods with stateful storage or local data need dedicated migration plans.

### Autoscaling by Workload

For stateless services, scale-out responds quickly and avoids machine downtime. For stateful workloads, scale-out is harder because data, partitions, and leaders must be coordinated.

If a single machine needs more RAM than the maximum offered by its current family, vertical scaling to a larger family or data sharding may be appropriate. If requests are independent and distributable, scale-out improves capacity alongside higher availability.

### Periodic Right-Sizing

Schedule configuration reviews monthly or after major changes. Compare p50/p95/p99 usage, peak load, headroom, cost, and SLOs. Never downsize solely on low average CPU because RAM, I/O, burst peaks, and recovery requirements must also be factored in.

## 13. Impact on Availability and Resilience

Resizing can introduce a disruption point. For critical services, avoid relying on a single machine if availability must be maintained during configuration changes.

Ways to reduce impact:

- Run multiple instances behind a load balancer.
- Drain one node at a time.
- Configure health checks and readiness checks.
- Use replicas for stateful data or services.
- Keep enough spare capacity to absorb traffic when one node stops.
- Roll out one availability zone at a time if required by architecture.
- Verify quotas and provisioning availability before starting.
- Maintain a clear rollback plan and observation window.

In multi-node clusters, resizing one node at a time reduces risk but extends total change duration. Balance rollout speed against remaining headroom. If every node runs near full capacity, draining one node can overload the remaining ones.

### Capacity Reservations and Quotas

A new machine type may lack capacity in the desired zone. GPU, vCPU, or instance count quotas can also block creation. Before resizing production, verify quotas, reservations, and available capacity across all target zones.

Do not delete the old machine immediately after the new one boots successfully. Keep the fallback option until the workload passes the validation period and data integrity has been verified.

## 14. Cost and Efficiency After Changing Configuration

Larger machines usually cost more per hour, yet total cost per unit of work can drop if the workload finishes faster or requires fewer nodes.

Factor in:

- Compute pricing by machine type and runtime.
- Additional disks, snapshots, IOPS, and throughput.
- Network traffic and cross-zone/cross-region charges.
- OS or software licensing.
- Reservations or usage commitments.
- Spare capacity costs for HA.
- Operational overhead from restarts, migrations, or managing more nodes.

One way to compare is:

\[
Cost\ per\ unit = \frac{Total\ operating\ cost}{Completed\ work\ units}
\]

A work unit can be a request, record, job, transaction, or productive processing hour.

For example, machine A processes 1,000 requests/second at 1 currency unit/hour; machine B processes 2,500 requests/second at 2 currency units/hour. If both meet the same SLO, B's cost per request can be lower despite a higher hourly rate. Calculate from real measurements at comparable error rates and latencies.

### Avoiding Excessive Scale-Down

Downsizing saves money but removes headroom for bursts, batch jobs, failover, and warm-up. Before downsizing, check peak loads, seasonal events, scale-up feasibility, and provisioning time. A smaller configuration is only viable if it still meets SLOs under defined scenarios.

## 15. Implementation Differences Across Platforms

Providers use different names and procedures. General examples:

| Platform | Typical Change Method | Points to Verify |
|---|---|---|
| AWS EC2 | Select a different instance type; often requires stopping the instance before changing | Supported instance types, instance store, ENIs, architecture, stop/start state, and quotas |
| Microsoft Azure | Resize VM to another VM size; may require restart or deallocate if host lacks capacity | VM size availability in cluster, disks/ephemeral disks, accelerated networking, and quotas |
| Google Cloud Compute Engine | Change machine type; typically requires VM to be in stopped state for machine type changes | Machine family, CPU platform, local SSDs, GPUs, zone, and quotas |

This table describes general patterns only. Exact behavior varies by machine type, region, OS, and features. Before operating on production, verify the current procedure for the specific SKU.

Some platforms support online CPU/RAM increases within certain limits; those features do not apply to all machine types. Distinguish hot resource updates from full machine type changes.

## 16. Example: Scaling Up an API Service

An API service runs on a VM with 4 vCPUs and 16 GiB RAM. After request volume grows, the operations team observes:

- p95 CPU stays above 85% during peak hours.
- Run queue grows as concurrency increases.
- Available RAM still has about 5 GiB free.
- Disk latency and network packet loss are normal.
- p99 latency breaches the SLO during heavy traffic bursts.

Profiling shows request handling can parallelize and the thread pool is CPU-bound. The team tests an 8 vCPU / 32 GiB machine type in staging. Results show higher throughput and lower p99 latency, though cost and new RAM usage still need evaluation.

Production rollout plan:

1. Provision a new node with the image and 8 vCPU / 32 GiB configuration.
2. Register the node with the load balancer without sending traffic yet.
3. Run smoke tests and load tests.
4. Shift a fraction of traffic to the new node.
5. Monitor CPU, RAM, p95/p99 latency, error rate, and cost.
6. Gradually increase traffic if results remain stable.
7. Drain and retire the old node after verification.

If the application uses only a single CPU thread or the backend database is the true bottleneck, adding vCPUs might yield no improvement. This example highlights that resizing should be guided by profiling and validated under representative load.

## 17. Pre- and Post-Resize Checklists

### Before Making Changes

- [ ] Defined objective and success metrics.
- [ ] Collected CPU, RAM, network, storage, and application metrics.
- [ ] Identified the true bottleneck rather than relying on a single metric.
- [ ] Compared full machine types, not just vCPU count.
- [ ] Verified CPU architecture, drivers, GPUs, and software compatibility.
- [ ] Checked local/ephemeral disks and classified data.
- [ ] Verified quotas, reservations, and capacity in the target region/zone.
- [ ] Checked whether resizing requires stop, restart, or deallocate.
- [ ] Drained traffic and prepared replicas if needed.
- [ ] Verified backups/snapshots and recovery plans.
- [ ] Recorded previous configuration, network addresses, volumes, and permissions.
- [ ] Established abort criteria and rollback plan.

### After Making Changes

- [ ] OS detects the expected CPU, RAM, and devices.
- [ ] Applications, drivers, agents, and services started successfully.
- [ ] Volumes, filesystems, networking, DNS, and security policies work.
- [ ] Heap, thread pools, container requests/limits, and caches are tuned appropriately.
- [ ] Health checks, error rate, latency, and throughput meet targets.
- [ ] No OOMs, kernel errors, packet loss, or storage regressions observed.
- [ ] Monitored across a representative load cycle.
- [ ] Cost per unit of work is within target.
- [ ] Updated inventory, manifests, or configuration documentation.
- [ ] Old machine retired only after the new setup proves stable.

## Conclusion

Changing CPU, RAM, and machine type is a normal part of the workload lifecycle. Resize decisions should be driven by metrics and profiling while accounting for every resource bundled with a machine type. Before changing configurations, understand hot-add, restart, stop/deallocate, or machine replacement workflows; prepare data, connections, backups, and rollback plans. After resizing, verify OS-level resources, tune runtimes and application limits, and monitor SLOs and costs. For critical workloads, rolling out node by node or using blue-green deployment minimizes disruption and preserves a safe path back to a stable configuration.
