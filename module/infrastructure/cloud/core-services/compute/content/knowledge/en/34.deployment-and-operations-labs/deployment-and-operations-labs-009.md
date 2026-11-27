# Measuring Performance, Right-Sizing Configurations, and Calculating Workload Costs

## Lesson Objectives

After this lesson, you will be able to:

- Build a performance baseline for a workload running on cloud virtual machines.
- Measure CPU, memory, storage, network, latency, and throughput using OS and platform metrics.
- Analyze bottlenecks to tune CPU, RAM, disk, and network configurations appropriately.
- Estimate costs based on runtime duration and accompanying resources.
- Compare cost per unit of work, validate changes, and plan continuous optimization.

## 1. Starting from the Workload and Service Objectives

Right-sizing is the process of selecting just enough resource capacity for a workload to meet performance, reliability, and scalability requirements at a reasonable cost. Configurations cannot be chosen merely from an application name or average CPU over a short window. You must understand what the workload actually does, how load varies, and how quickly users expect results.

Before measuring, characterize the workload:

- **Processing type:** Web/API, batch, data processing, database, cache, build, or compute tasks.
- **Load pattern:** Requests/second, job count, concurrent users, data sizes, and peak times.
- **Resource profile:** CPU-bound, memory-bound, I/O-bound, or network-bound.
- **Service objectives:** Throughput, p95/p99 latency, error rate, batch completion time, and recovery time.
- **Operational constraints:** Minimum replica counts, deployment regions, redundancy requirements, software licensing, and maintenance windows.

For example, an order-lookup API may require p95 under 300 ms at 500 requests/second. An image-processing batch job may allow a 40-minute completion window yet must process 100,000 images every night. Two workloads have different objectives, so CPU, RAM, disk selection, and pricing models also differ.

Define representative load and peak load upfront. Benchmarking only at low load risks under-provisioning when concurrency spikes. Benchmarking only at extreme peaks risks over-provisioning for most of the day.

## 2. Establishing a Baseline and Measuring Performance

A baseline is the dataset describing current workload behavior on a defined configuration and dataset. Record machine specs, operating system, application version, volume type, instance type, replica count, and measurement timestamps for fair comparisons.

### 2.1. Metric Groups to Monitor

| Group | Metrics to observe | Signs requiring investigation |
|---|---|---|
| CPU | Utilization, load average, user/system/iowait time, CPU throttling if any | Sustained CPU saturation, growing runnable queue, or rising processing time |
| Memory | Used/available, working set, swap, page faults, OOM kills | RAM nearly exhausted, rising swap, OOM-killed processes, or continuous GC |
| Storage | IOPS, throughput, latency, queue length, used capacity | High I/O wait, long queues, rising latency, or volume running out of space |
| Network | Bytes/s, packets/s, retransmissions, errors/drops, latency | Bandwidth or PPS hitting limits, rising retransmissions |
| Application | Request rate, throughput, p50/p95/p99, error rate, queue depth | Latency rising despite low CPU, timeout errors, or accumulating backlogs |
| Platform | Instance status, burst balance/credits, autoscaling, throttling | Resources throttled by instance type or scaling policy |

Low CPU utilization does not prove a workload needs no extra resources. The application might be waiting on disk, database, locks, or external APIs. Conversely, high CPU during a short burst can be normal if p95, throughput, and error rates still meet targets.

### 2.2. Tools on Linux

Use the following commands to inspect the virtual machine:

~~~bash
uptime
top
free -h
vmstat 1
iostat -xz 1
df -h
ip -s link
ss -s
~~~

- `uptime` and load average indicate runnable/waiting demand; compare against vCPU count and workload type.
- `top` or equivalent tools identify processes consuming CPU and RAM.
- `free -h` reports available memory; do not look solely at the free column because Linux uses RAM for caching.
- `vmstat` reveals runnable queues, swap, I/O wait, and system activity over time.
- `iostat -xz` monitors block device latency and queue depths if sysstat is installed.
- `df -h` checks filesystem capacity; full disks cause failures even when IOPS remain low.
- `ip -s link` and `ss -s` help spot interface errors, packet drops, and socket counts.

Run commands across periods carrying representative load. A single point-in-time snapshot is insufficient. If tools are missing, install packages compatible with the OS and organizational image policies.

### 2.3. Metrics from the Cloud Platform

With Amazon EC2 and CloudWatch, start from `CPUUtilization`, `NetworkIn`, `NetworkOut`, and instance status checks. EBS metrics such as `VolumeReadOps`, `VolumeWriteOps`, `VolumeReadBytes`, `VolumeWriteBytes`, and `VolumeQueueLength` help assess storage activity. Exact metrics depend on volume type and configuration.

In-guest memory and filesystem metrics are usually not collected by default via basic EC2 metrics. Install the CloudWatch Agent or an approved monitoring agent to collect memory used/available, disk used, and OS metrics. Check collection intervals, resolution, ingestion costs, and data retention.

On Azure, use Azure Monitor and VM Insights. On Google Cloud, use Cloud Monitoring and the Ops Agent. Always check each platform's metric definitions, units, sampling intervals, and aggregation scopes before comparing.

## 3. Designing Repeatable Tests

A valid benchmark must be reproducible and must not disrupt production users.

1. Choose a test environment closely matching production, running the same application version and representative data types.
2. Record instance type, vCPU, RAM, architecture, disk type/size, IOPS/throughput limits, networking, OS, and replica count.
3. Generate test data large enough to reflect real behavior without containing sensitive production data.
4. Run a warm-up phase so caches, JIT, or connection pools stabilize.
5. Step load up at defined levels, holding each level long enough for metrics to stabilize.
6. Record throughput, p50/p95/p99, error rate, CPU, memory, disk, network, and queue depth.
7. Repeat the test and compare under identical conditions. Flag runs disturbed by background jobs or dependency glitches.

For an API, you might test 100, 250, 500, and 750 requests/second, holding each step for 10 minutes after warm-up. These numbers only illustrate stepped loading; select levels matching your SLOs and expected traffic. Halt testing if error rates or latency breach agreed safety limits.

For batch jobs, record completion duration, records processed/second, CPU time, I/O wait, peak memory, and cost per batch. Do not record total duration alone, because two configurations can finish in the same time with vastly different resource usage and cost.

## 4. Analyzing Bottlenecks and Right-Sizing CPU

When CPU is the bottleneck, symptoms usually include sustained high CPU utilization, growing runnable queues, flat throughput under rising load, and worsening latency. Distinguish CPU user, system, and iowait time to avoid adding vCPUs when the application is actually waiting on I/O.

Tuning workflow:

1. Check CPU levels during normal and peak hours, not only full-day averages.
2. Identify processes or threads consuming CPU; look for expensive loops, serialization, compression/encryption, or overly heavy queries.
3. Test an instance with more vCPUs or a different architecture if the workload can leverage parallelism.
4. Re-measure throughput and p95/p99. If throughput rises without improving latency, another bottleneck may exist.
5. If CPU stays consistently low with no needed bursts, test a smaller configuration and re-verify SLOs.

For burstable instances, monitor CPU credits or burst balance metrics per the provider's model. Low average CPU can hide a workload repeatedly exhausting credits and getting throttled. For continuously running workloads, an instance type with steady CPU performance may fit better despite a different hourly unit price.

Do not reduce vCPUs solely from average `CPUUtilization`. A single thread can saturate one core while overall multi-core utilization stays low. Check per-core metrics and the application's concurrency model.

## 5. Right-Sizing Memory, Storage, and Networking

### 5.1. Memory

Observe available memory, working set, swap, page faults, and OOM kills. Identify peak usage under peak load plus needed growth headroom.

If memory nears exhaustion, find the cause before adding RAM: memory leaks, unbounded caches, oversized buffers, or worker concurrency exceeding design. After adding RAM, re-run benchmarks and check whether processing times improve or only costs rise.

On Linux VMs, memory used for page cache can be reclaimed; hence `available` is usually more useful than `free`. On containers, check both container memory limits and node memory. A process can be OOM-killed for exceeding its container limit even when the host still has free RAM.

### 5.2. Storage

Evaluate capacity, IOPS, throughput, and latency together. A volume with enough capacity may lack performance. Databases are typically sensitive to latency and random IOPS; large-file processing is typically sensitive to sequential throughput.

With EBS, select the right volume type and tune size, IOPS, and throughput within the volume type's capabilities. With gp3, IOPS and throughput can be configured independently within service limits. Do not raise IOPS if the application is waiting on locks or CPU; verify the root cause from queues and latency first.

Check filesystems, inodes, log growth, snapshots, and temporary storage. If volumes frequently near capacity, expand storage or establish lifecycles for logs and temporary data.

### 5.3. Networking

Track throughput, packets per second, retransmissions, packet drops, and latency to dependent services. Instance types impose different network limits; a data-intensive workload may need a higher instance/network tier even with low CPU.

If networking saturates, inspect payload sizes, connection counts, keep-alive, compression, regional placement of dependencies, and batching opportunities. Increasing bandwidth will not fix latency caused by cross-region databases or repeated DNS lookups.

## 6. Hands-On Example: Right-Sizing an API on EC2

Suppose an order-lookup API runs on two VMs of the same type. During peak hours, testing yields:

| Metric | Baseline |
|---|---:|
| Request rate | 400 requests/second |
| p50 latency | 75 ms |
| p95 latency | 420 ms |
| Error rate | 0.4% |
| Peak-hour average CPU | 88% |
| Lowest available memory | 1.1 GiB |
| Disk I/O wait | 2% |
| Network throughput | 35% of measured limit |

CPU is high and p95 climbs while disk I/O wait is low, memory remains available, and the network is unsaturated. This points to testing more CPU capacity or optimizing CPU-heavy code paths before scaling disk or network.

Suppose testing a configuration with more vCPUs yields:

| Metric | Baseline | After adjustment |
|---|---:|---:|
| Request rate | 400 requests/second | 400 requests/second |
| p95 latency | 420 ms | 235 ms |
| Error rate | 0.4% | 0.1% |
| Peak CPU | 88% | 54% |
| Lowest available memory | 1.1 GiB | 1.0 GiB |

If peak load continues growing, evaluate horizontal scaling and database connection limits. Do not assume vertical instance resizing is the sole solution. You can add replicas, reduce per-request work, cache suitable results, or optimize queries.

These numbers illustrate decision-making only, not performance guarantees for any specific instance type. Real outcomes depend on application code, data, cloud region, and service configuration.

## 7. Building a Workload Cost Model

Workload costs typically span multiple components. Multiplying VM hourly rate by hours alone misses storage, data transfer, IP addresses, NAT, load balancers, backups, logs, licenses, and dependent services.

General formula:

~~~text
Total period cost =
  Compute
+ Storage
+ Network egress and network processing fees
+ Load balancers and IP addresses
+ Backups and snapshots
+ Monitoring and logs
+ Licenses / support / dependent services
~~~

For hourly compute:

~~~text
Compute cost =
  Number of instances
  x Running hours in period
  x Unit price per instance-hour
~~~

For capacity-based storage:

~~~text
Storage cost =
  Billable capacity (GB-month)
  x Unit price per GB-month
~~~

For network egress:

~~~text
Egress cost =
  Billable outbound volume (GB)
  x Unit price per GB
~~~

Some services charge by requests, IOPS, provisioned throughput, log ingestion volume, query counts, or data retention duration. Use the exact billing units from the regional and service price list.

### 7.1. Monthly Cost Calculation Example

Suppose a workload runs continuously for a 730-hour month across two VMs at an assumed rate of $0.096/hour each; each VM uses a 100 GB volume; Internet egress is 200 GB; snapshots retain 50 GB; log ingestion is 20 GB.

To illustrate the calculation, assume these unit prices. These are hypothetical figures, not current cloud pricing:

| Component | Quantity | Assumed unit price | Cost |
|---|---:|---:|---:|
| Compute | 2 x 730 instance-hours | $0.096/instance-hour | $140.16 |
| Block storage | 2 x 100 GB-months | $0.08/GB-month | $16.00 |
| Network egress | 200 GB | $0.09/GB | $18.00 |
| Snapshot | 50 GB-months | $0.05/GB-month | $2.50 |
| Log ingestion | 20 GB | $0.50/GB | $10.00 |
| **Total** | | | **$186.66/month** |

Compute calculation: `2 x 730 x 0.096 = 140.16 USD`. The remaining rows multiply quantity by unit price. This total excludes taxes, discounts, NAT Gateways, load balancers, public IPs, API requests, licenses, support fees, or unlisted services. Replace all assumed unit prices with actual pricing for your region, purchasing model, and deployment date.

### 7.2. Comparing Options by Total Cost

Suppose Option B uses a larger instance yet finishes the same workload faster or reduces required replicas. You cannot judge which option is cheaper from hourly unit price alone; compute total period cost and cost per successful transaction.

~~~text
Cost per successful request =
  Total workload cost in period
  / Successful requests in period

Cost per job =
  Total workload cost in period
  / Completed jobs in period
~~~

If a larger configuration halves processing duration while compute unit price rises less than double, compute cost per job may drop. Still, add storage, networking, and related services for an accurate comparison.

## 8. Cost Estimation and Allocation Tools

Cloud tools help estimate and inspect costs against usage data:

- **AWS Pricing Calculator:** Build pre-deployment estimates by instance type, running hours, volumes, data transfer, and accompanying services.
- **AWS Cost Explorer:** Inspect actual cost trends over time, by service, region, and tag.
- **AWS Cost and Usage Report:** Analyze granular usage and line-item charges.
- **AWS Compute Optimizer:** Receive right-sizing recommendations for supported resources based on historical metrics and lookback windows.
- **Azure Pricing Calculator, Cost Management, and Advisor:** Estimate, analyze spend, and review recommendations for Azure resources.
- **Google Cloud Pricing Calculator, Billing reports, and Recommender:** Estimate, analyze costs, and view optimization recommendations.

Automated recommendations are inputs for investigation, not blind change commands. Check observation windows, peak usage, scaling history, SLOs, and seasonal load waves before applying them.

Apply consistent tags or labels such as `service`, `owner`, `environment`, `cost-center`, and `workload`. Without attributing costs to owners, operations teams struggle to tell which workload drove a cost increase. Set budgets and alerts per service/team to catch anomalies early.

## 9. Post-Right-Sizing Cost Optimization

After finding a suitable configuration, evaluate operational optimizations:

- **Shut down unused resources:** Schedule dev/test environments, lab machines, and batch jobs that do not need to run outside defined windows.
- **Use autoscaling:** Scale on relevant metrics like request rate, queue depth, or CPU; set min/max and cooldowns to avoid oscillation.
- **Choose purchasing models:** On-Demand suits unpredictable loads; Savings Plans or Reserved Instances can lower costs for steady usage; Spot suits interruptible batch jobs with checkpointing.
- **Optimize storage:** Delete unattached volumes, expired snapshots, and redundant logs; align volume types and IOPS to actual demand.
- **Reduce data transfer:** Co-locate compute near dependencies, cache appropriately, shrink payloads, and avoid unnecessary cross-region transfer.
- **Track idle costs:** Running instances doing little work, oversized unused volumes, or NAT/load balancers left behind for stopped workloads.
- **Maintain sensible headroom:** Do not cut resources so aggressively that you lose headroom for peaks, failover, or rolling deployments.

Long-term commitments should follow only after establishing a stable baseline and predictable usage. Never buy commitments based on one unusually high-usage month. Spot offers lower prices in some scenarios but can be reclaimed; applications must tolerate interruptions and persist checkpoints durably.

## 10. Hands-On Verification Workflow

Execute in a cost-bounded lab or staging environment:

1. Tag resources and record the initial configuration.
2. Run a representative workload, collecting CPU, memory, disk, network, throughput, p95/p99, and error rate.
3. Identify bottlenecks using multiple correlated metrics rather than a single isolated indicator.
4. Change one configuration group at a time: CPU/instance family, memory, volume, or network.
5. Re-run the exact dataset, load level, and duration. Record post-adjustment results.
6. Calculate compute, storage, network, backup, log, and dependent service costs for the same period.
7. Calculate cost per request/job and compare against SLOs, throughput, and error rates.
8. Verify scaling, failover, restarts, and recovery before applying to production.
9. Monitor actual costs post-change and roll back if performance or reliability misses targets.

The results table should include at least:

| Configuration | vCPU/RAM | Disk | Throughput | p95 | Error rate | Period cost | Cost/job |
|---|---|---|---:|---:|---:|---:|---:|
| Baseline | Record original config | Record type/size | Measure | Measure | Measure | Calculate | Calculate |
| Candidate A | Record test config 1 | Record type/size | Measure | Measure | Measure | Calculate | Calculate |
| Candidate B | Record test config 2 | Record type/size | Measure | Measure | Measure | Calculate | Calculate |

Accept a new configuration only when performance meets SLOs, error rates stay within thresholds, peak headroom remains sufficient, and costs are fully accounted for. Archive metrics, configurations, pricing assumptions, and results so future reviews are reproducible.

## 11. Right-Sizing and Cost Checklist

- [ ] Described workload, load patterns, SLOs, and peak hours.
- [ ] Baseline captures hardware, software, dataset, and measurement timestamps.
- [ ] Collected CPU, memory, disk, network, and application metrics.
- [ ] Verified bottlenecks using multiple correlated metrics.
- [ ] Benchmarked multiple configurations under identical conditions.
- [ ] Preserved headroom for bursts, failover, and rolling deployments.
- [ ] Calculated compute, storage, egress, NAT, load balancer, backup, log, and relevant license costs.
- [ ] Calculated cost per request/job or appropriate business unit.
- [ ] Used pricing for the exact region, purchase model, and date; documented assumptions.
- [ ] Resources carry owner, service, environment, and cost-center tags.
- [ ] Budgets, alerts, and periodic cost reviews are established.
- [ ] Rollback plan exists if the new configuration fails SLOs.

## Conclusion

Performance measurement reveals what CPU, memory, storage, and networking a workload truly requires. Right-sizing must rely on representative load, both infrastructure and application metrics, and verification after every change. Cost models must capture all direct resources and supporting services, then normalize into cost per successful request or job. Combining repeatable benchmarks, cost attribution, and continuous monitoring maintains performance within budget.