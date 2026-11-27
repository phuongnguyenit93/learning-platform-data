# Selecting Volume Performance by IOPS and Throughput

## Lesson Objectives

A volume with plenty of free capacity can still fail to meet an application's access speed requirements. Conversely, allocating more performance to a volume does not guarantee a faster application if the limit lies in Compute, the attachment, the filesystem, or the database.

This lesson belongs to the **Block Volume and Boot Volume** chapter of the **CLOUD_PROVIDERS_ORACLE** module. The focus is on selecting OCI storage configurations based on workload requirements while placing them in the context of monitoring, infrastructure limits, cost, and service maintainability.

After this lesson, you will be able to:

- Distinguish capacity, IOPS, throughput, and latency.
- Calculate the relationship between I/O operations, I/O size, and data transfer volume.
- Explain the role of volume performance tiers and VPU/GB in OCI.
- Identify volume, instance, and attachment path limits before making adjustments.
- Design measurements representative of the workload rather than just chasing one large benchmark number.
- Make decisions to scale up, scale down, or keep configurations with clear evidence and acceptance criteria.

Performance tiers, VPU/GB ranges, limits, and supportability may vary by resource, shape, and configuration. This lesson does not treat a fixed service specification table as a guarantee; when deploying, always retrieve specifications for the exact target OCI environment.

## 1. Four Metrics to Read Together

| Metric | Meaning | Common Units | Cannot Conclude From This Metric Alone |
| --- | --- | --- | --- |
| Capacity | Amount of data that can be stored | GB, GiB, TB, TiB | Whether the volume is fast enough |
| IOPS | Number of I/O operations completed per second | operations/second | How large each operation is, how long it takes |
| Throughput | Amount of data transferred per second | MB/s, MiB/s | Speed of small transaction processing or tail latency |
| Latency | Time to complete a single operation | ms, microseconds | Whether the whole system has enough capacity under concurrent tasks |

An application performing many small random reads may care strongly about IOPS and latency. A job continuously reading large files may care more about throughput. Databases often have multiple I/O patterns coexisting, so each group of operations must be analyzed.

With a Boot Volume, the operating system, logs, and applications can generate load together. With a data Block Volume, workload type and access patterns determine demand. Do not assume a boot volume never needs high performance, or that a data volume must always select the highest tier.

### 1.1. Standardize Units Before Calculating

In this lesson:

```text
1 KiB = 1,024 bytes
1 MiB = 1,024 KiB
1 GiB = 1,024 MiB

1 MB = 1,000,000 bytes
```

MiB/s and MB/s are not the same unit. When cross-referencing the Console, service documentation, and OS tools, read each source's unit definitions. Do not change a label from MB/s to MiB/s while keeping the same number and comparing them as equal.

## 2. Relationship Between IOPS and Throughput

### 2.1. When I/O Size Is Relatively Uniform

A basic estimate:

```text
Throughput = IOPS x average size per I/O
```

Example with 8 KiB I/O:

```text
20,000 IOPS x 8 KiB
  = 160,000 KiB/s
  = 156.25 MiB/s
```

If keeping 20,000 IOPS while increasing I/O size to 32 KiB:

```text
20,000 IOPS x 32 KiB
  = 640,000 KiB/s
  = 625 MiB/s
```

To achieve the same IOPS with larger I/O sizes, the storage path must deliver higher throughput. A throughput limit can cause observed IOPS to fall below the nominal IOPS tier.

### 2.2. Two Workloads May Require Different Configurations

| Illustrative Workload | I/O Size | Target | Corresponding Throughput/IOPS Under Simple Math |
| --- | --- | --- | --- |
| Small data accesses | 8 KiB | 20,000 IOPS | 156.25 MiB/s |
| Large file read batch | 1 MiB | 600 MiB/s | Approximately 600 IOPS |

Looking only at the numbers 20,000 and 600 might lead readers to think the first workload is "heavier." In reality, the second workload requires far higher data transfer volume. Both can also have different latency and durability requirements.

### 2.3. Mixed Workloads Must Be Summed by Group

Suppose in the same second, an application performs:

- 8,000 I/Os, each 8 KiB.
- 2,000 I/Os, each 256 KiB.

We have:

```text
Total IOPS = 8,000 + 2,000 = 10,000

Small group: 8,000 x 8 KiB = 62.5 MiB/s
Large group: 2,000 x 256 KiB = 500 MiB/s

Total throughput = 562.5 MiB/s
```

If you assume every I/O is 8 KiB, you will severely underestimate throughput. You also need to know the read/write ratio, sequential/random patterns, and concurrency level rather than relying on a single average size.

These calculations describe raw I/O work and do not yet include all differences from request splitting/merging, caching, metadata, and software layer overhead. They serve for estimation and sanity checks, not as substitutes for real measurements.

## 3. Volume Performance Tiers in OCI

### 3.1. Performance Is Configured at the Service Layer

OCI Block Volume provides performance options for volumes, with tiers such as Lower Cost, Balanced, Higher Performance, and Ultra High Performance depending on service support scope. When reviewing configuration, check which tiers apply to the volume type, capacity, and attachment in use.

A key parameter is **VPU/GB**, short for Volume Performance Units per GB. This is how the service expresses performance resources allocated relative to volume capacity; it is not the number of CPUs on the Compute instance.

Factors to read together:

- Volume capacity.
- Selected performance tier or VPU/GB.
- IOPS and throughput per unit of capacity at that configuration.
- Absolute per-volume limits.
- Instance and attachment conditions needed to utilize the performance.

Do not assume doubling VPU/GB will always make transactions twice as fast. If the workload was not hitting the previous limit or is bottlenecked at another layer, the effect may be minimal.

### 3.2. Both Capacity and Absolute Limits Play a Role

A conceptual model for reading specifications:

```text
Volume-side IOPS
  <= lesser of:
       capacity x IOPS per unit of capacity
       volume IOPS cap at the selected tier

Volume-side throughput
  <= lesser of:
       capacity x throughput per unit of capacity
       volume throughput cap at the selected tier
```

This is an explanatory model, not a universal API formula for every volume type. Use the exact specifications and units published by OCI for your specific configuration.

The model highlights two reasoning mistakes:

1. A small volume set to a high performance tier will not necessarily achieve the same total cap as a larger volume.
2. Continuously increasing capacity stops increasing performance once the cap is hit.

Do not increase capacity solely to get more performance without comparing supported options first. Increased capacity also affects cost, filesystem management, and how data is migrated if you want to change the design later.

### 3.3. Prerequisites for High Tiers Must Be Met

Some high-performance configurations have requirements for shape, attachment, multipath, or software components inside the instance. Do not look only at the volume's performance tier and assume the entire I/O path already qualifies.

Confirm:

- Whether the shape supports the intended configuration.
- Whether the attachment type in use satisfies requirements.
- If multipath is required, whether the necessary paths are actually active.
- Whether drivers, agents/plugins, and the OS are in a supported state.
- Whether total instance limits are sufficient for all active volumes together.

Do not modify drivers or multipath configuration based on an example that does not match your operating system. These are changes on the storage path requiring a plan and environment-appropriate documentation.

## 4. Actual Performance Is the Result of the Entire I/O Path

You can picture it as:

```text
Application
  -> filesystem and OS cache
  -> block layer, drivers, and attachment
  -> connection path and Compute limits
  -> volume service
```

Observable capability is constrained by the slowest component or lowest ceiling along the path, and is also shaped by workload characteristics.

### 4.1. Compute-Side Limits

An instance can attach multiple volumes, but total actual performance cannot be assumed to equal the sum of every volume's maximum tier. Shape storage limits and network bandwidth may be shared across multiple I/O loads.

Hypothetical example, not actual OCI shape figures:

```text
Volume A can deliver up to 400 MiB/s under suitable conditions.
Volume B can deliver up to 400 MiB/s under suitable conditions.
The instance configuration's I/O path only achieves 600 MiB/s total for that test.

A and B running together do not automatically achieve 800 MiB/s.
```

If both share an instance-side limit, increasing Volume A's performance tier further may not help. Identify the exact type of limit; likewise, do not assume the application NIC speed represents the exact storage specs for every shape and attachment type.

### 4.2. Caching Can Easily Mislead Measurements

Reading data already in RAM typically does not generate the same I/O down to the volume as reading uncached data. One fast benchmark run does not prove a volume can sustain that speed when the dataset exceeds RAM.

Similarly, an application writing to a buffer does not mean data has been durably persisted as required by transactions. Workloads requiring synchronous writes can exhibit different latency and throughput than workloads allowing buffered writes.

Test results must document:

- Whether data is cached or read from storage.
- How buffered I/O or direct I/O is used.
- Synchronization and durability guarantees required for writes.
- Dataset size, test duration, and background load.

Do not disable durable write guarantees just to get an attractive benchmark and then apply that result to a transactional workload with different requirements.

### 4.3. Concurrency and Latency Relate to IOPS

If an application sends only one I/O and waits for completion before sending the next, it may fail to utilize the volume's concurrent processing capability.

Under steady-state queueing relationships, you can estimate:

```text
Average in-flight/queued I/Os
  approximately equals IOPS x average latency in seconds

20,000 IOPS x 0.001 seconds = approximately 20 concurrent I/Os
```

This is a relationship between quantities measured over the same scope, not a formula guaranteeing performance simply by setting queue depth to 20. Pushing concurrency far beyond system capacity can cause queues and latency to spike without corresponding throughput gains.

Find the concurrency level that meets application targets, not just the level that produces the highest raw IOPS.

## 5. Start With Workload Requirements

### 5.1. Gather an I/O Profile

Before selecting a performance tier, record:

| Attribute | Questions to Answer |
| --- | --- |
| Application goal | What is the target transaction latency, business throughput, or batch completion time? |
| Data | What is the current size, growth rate, and space needed for logs/temp files? |
| I/O size | Mostly small, large, or mixed? |
| Access pattern | Random, sequential, read-heavy, write-heavy, or shifting by phase? |
| Concurrency | How many processes/threads/tasks issue I/O simultaneously? |
| Durability | Are synchronous writes or strict write ordering required? |
| Load cycles | Do peak hours, backups, batch jobs, and maintenance overlap? |
| Failure mode | Does load shift to remaining volumes or instances on failure? |

A Java application accessing an Oracle Database in a separate service does not necessarily generate heavy data I/O on the application server's volume. If slowness lies in remote DB queries, raising the Java machine's Boot Volume performance may not fix the issue.

### 5.2. Read Multiple Time Windows, Not Just Daily Averages

A 24-hour average can mask a multi-minute burst that causes errors or latency violations. Examine phases including:

- Startup and initial data loading.
- Normal load.
- Business peak load.
- Concurrent backups or batch jobs.
- Recovery after a component fails.

Headroom should be based on variance and adjustment lead time; there is no single fixed percentage that fits all systems. If the system must sustain load when one instance is lost, measure that scenario rather than just adding a small percentage to the average.

## 6. Configuration Selection Workflow

### Step 1: Define Verifiable Goals

For example: "Complete the batch job within 20 minutes without pushing API p95 past target during concurrent execution" is more specific than "need a fast disk."

Tie goals to test datasets and software versions. Explicitly state write durability modes, concurrency levels, and accompanying background tasks.

### Step 2: Calculate Both IOPS and Throughput Needs

Use the workload profile to estimate each I/O group and sum appropriately. If a workload needs 25,000 IOPS with 8 KiB blocks:

```text
Corresponding throughput
  = 25,000 x 8 / 1,024
  = 195.3125 MiB/s
```

Candidates must meet both requirements under appropriate conditions while maintaining acceptable latency. Sufficient IOPS with a throughput ceiling below demand still fails to meet requirements.

### Step 3: Cross-Check OCI Specs and Attachment Path

Retrieve specs for the specific capacity, performance tier, volume type, shape, and attachment. Check per-volume limits and instance-wide totals.

Also check OS-level configuration: whether the device matches the expected volume, whether the filesystem is mounted properly, and whether I/O path components operate as designed.

### Step 4: Measure Application Together With Infrastructure Metrics

Keep measurement conditions consistent enough and change one primary factor at a time. Record timestamps, workload, old/new configuration, and how steady state was determined.

A configuration is considered better only if it improves the required objective or maintains the objective at a more appropriate cost. Higher IOPS accompanied by worse transaction latency is not a successful outcome.

### Step 5: Decide on Changes and Observe Afterward

Possible actions include:

- Raising the volume performance tier when evidence shows the volume is the limit.
- Adjusting Compute or attachment when the bottleneck is on the instance path.
- Optimizing queries, read/write patterns, or concurrency if the application generates inefficient I/O.
- Separating or rescheduling background tasks competing for resources.
- Keeping the configuration unchanged when requirements are met and no evidence justifies a change.

Volume adjustability does not exempt you from monitoring latency and errors when applying changes. Document rollback conditions or fallback options if results fall short. Do not treat shrinking capacity as an automatic undo after expanding a volume.

## 7. Examples of Reading Results and Choosing Next Actions

### 7.1. Self-Managed Database With Many Small I/Os

Hypothetical scenario: data resides on a Block Volume, peak demand is around 25,000 IOPS with 8 KiB I/Os. Transaction latency targets are tracked separately.

Questions:

1. Does the volume configuration provide enough IOPS and roughly 195.31 MiB/s as estimated?
2. Can the instance and attachment utilize that level?
3. Does the I/O queue grow alongside slowdowns, or is the application waiting on locks/CPU?
4. Do synchronous writes, logs, and data create distinct I/O patterns?
5. Do concurrent backups add load beyond what was calculated?

If volume-side metrics are near limits and both queues and latency rise with load, testing a higher performance tier is justified. If IOPS are low while transactions wait on locks, increasing VPU/GB may not address the root cause.

### 7.2. Large Data Read Batch

A batch job needs to sustain 600 MiB/s with roughly 1 MiB I/Os. Simple math shows about 600 IOPS needed, yet the candidate must still have sufficient throughput and instance-side I/O path capacity.

Comparing only "maximum IOPS" could lead to picking an apparently over-provisioned tier where the batch still misses its deadline. Inspect sequential reads, caching, decompression/processing CPU, data source bandwidth, and competing jobs using the volume.

### 7.3. Boot Volume Holding Java Backend Logs

On normal days, the Boot Volume performs fine. When the application hits errors, log write rates, I/O latency, and used space all climb together.

Before raising the performance tier, check:

- Are logs looping abnormally due to a software bug?
- Are rotation and space limits working?
- Is the centralized log shipper backed up?
- Is the application using unnecessary synchronous writes for that type of log?
- Is there an operational requirement to separate I/O streams or allocate other resources?

Increasing performance might help partially, but it does not replace fixing unbounded log growth or the bug causing it.

### 7.4. Hypothetical Results Matrix

Numbers in this table are solely for practicing diagnostics, not specs of a specific OCI shape or volume.

| Observation | Hypothesis Worth Testing | Next Experiment |
| --- | --- | --- |
| IOPS near confirmed cap, latency rises as load increases | Volume may lack IOPS capacity | Test a more suitable tier while keeping workload and attachment path constant |
| IOPS not high, yet throughput near limit | Large I/Os are hitting transfer ceiling | Check throughput limits instead of just raising IOPS expectations |
| Multiple volumes slow down together on one instance | Shared Compute/attachment limit or background load | Check aggregate I/O, shape, and connection conditions |
| Actual I/O down to volume is low, application CPU is high | Compute or software may be the bottleneck | Profile CPU, queries, and concurrency |
| Second read is dramatically faster | Cache may be dominating the measurement | Measure with clearly documented cache state and dataset size |
| Volume tier raised, yet application metric unchanged | Bottleneck lies elsewhere or benchmark is unrepresentative | Cross-check layers; stop speculatively increasing config |

## 8. Observing via Monitoring and the Operating System

### 8.1. Combining Multiple Information Layers

At the OCI layer, observe metrics provided by the service for the volume and related resources, such as read/write operations and read/write bytes according to each metric's definition. Verify the right compartment, resource, time interval, unit, and aggregation.

At the OS layer, inspect devices, filesystems, queues, and I/O latency. At the application layer, inspect latency, business throughput, error rates, and wait times.

Do not directly add or compare numbers from different measurement scopes. The OS may split/merge I/Os; caches may absorb operations before they reach the volume; sampling intervals across sources may differ.

An example of normalizing metrics, not a specific Monitoring query expression:

```text
Over 60 seconds of observation:
  120,000 completed operations
  937.5 MiB data transferred

Average IOPS = 120,000 / 60 = 2,000
Average throughput = 937.5 / 60 = 15.625 MiB/s
Average size = 8 KiB per operation
```

Before dividing by time, know whether the source returns a total count, a pre-computed rate, or a cumulative counter. Do not divide a value that is already in operations/second a second time.

### 8.2. Read Commands in Linux

If you have an authorized test Linux machine, you can inspect using the following commands. The `iostat` utility usually belongs to the `sysstat` package and must be preinstalled.

```bash
# View devices and active filesystems
lsblk -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINT

# Replace with a data path that actually exists on the machine
findmnt -T /srv/app-data

# Observe device I/O in one-second intervals
iostat -xz 1 10
```

When reading `iostat`:

- Check the units and column meanings for the exact tool version in use.
- The first sample may reflect averages since boot; subsequent samples reflect the sampling interval.
- `await` is average latency observed at the device layer, including queue wait time as measured by the tool; do not treat it as pure internal latency of the volume service.
- High `%util` is a signal to investigate, not a rule proving every multi-queue device has exhausted all capacity.
- CPU `iowait` is not the busy percentage of one specific volume.

Do not generate write test load onto a volume containing live data just to find limits. If a dedicated benchmark is needed, use an appropriate test environment and test data, documenting workload, cache conditions, and durable write guarantees before comparing results.

## 9. Cost, IAM, and Availability When Changing Performance

### 9.1. Compare at the Same Service Target

Both capacity and performance resources can impact storage costs. Picking the lowest visible tier in a list does not mean the lowest total cost if batch jobs stretch out or require extra Compute to finish.

Conversely, the highest tier may create unused resources. Compare options when they meet the same requirements, then record each option's cost and operational limits based on actual environment data.

Do not overlook backups, clones, retained volumes, and Compute resources serving the same workload. Expanding capacity once for performance can leave ongoing costs behind even after load drops.

### 9.2. Change Permissions Must Be Properly Scoped

Someone viewing metrics and someone changing volume configuration may need different permissions. Grant appropriate permissions by compartment and operational responsibility; do not use tenancy-wide admin rights by default just to check performance.

Confirming the OS mounted the right volume must also happen before modifying OCI resources. Adjusting the wrong volume will not improve the target workload and skews cost assessments.

### 9.3. High Performance Does Not Replace Backup or Redundancy

Increasing VPU/GB does not create backups, does not protect against accidental deletion, and does not automatically make a single instance highly available.

If the system must maintain service levels when losing a component, evaluate failover load and recovery plans. When data spans multiple volumes, consistency and appropriate recovery must also be designed; splitting I/O load does not automatically solve those two requirements.

## 10. Selection Worksheet and Self-Check

Complete the worksheet below before proposing a performance tier change:

| Item | Evidence to Record |
| --- | --- |
| Target resource | Volume, attachment, instance, compartment, and application path |
| Application goal | Latency, business throughput, error rate, or batch duration |
| I/O profile | Size, read/write ratio, sequential/random, concurrency, durable write needs |
| Quantitative demand | IOPS, throughput, capacity, and load to sustain under failure |
| OCI configuration | Capacity, performance tier/VPU, supported limits and conditions |
| Related limits | Shape, aggregate multi-volume I/O, attachment, and dependencies |
| Baseline metrics | Measurement window, metrics, latency, queue depth, cache, and background load |
| Proposed change | Increase/decrease performance, change I/O path, optimize software, or keep unchanged |
| Measured result | Same workload, same data guarantees, impact on application goal |
| Operations | Expected cost, execution permissions, monitoring criteria, and fallback plan |

Self-check:

1. Why might a volume with high nominal IOPS still fail to meet the throughput of a large-file read batch?
2. Approximately how much throughput does a 20,000 IOPS workload with 8 KiB I/Os require? How does that change if I/Os become 32 KiB?
3. Is VPU/GB the number of CPUs allocated to an instance? What other limits must be read alongside this value?
4. Why does increasing capacity not guarantee performance keeps rising once the absolute limit is reached?
5. Do two volumes attached to the same instance automatically achieve the sum of their individual maximum performance tiers?
6. What factor might a benchmark be measuring when the second read is much faster than the first?
7. Why is higher throughput with worse transaction p99 not yet a successful result?
8. If a Java API is slow due to remote DB queries, what evidence would be needed to justify increasing Boot Volume performance?
9. When reading Monitoring, why must you determine whether a value is a total, rate, or counter before calculating IOPS?
10. What evidence would lead you to keep the volume tier unchanged and shift investigation to the attachment or software?

The output of this lab is a data-backed decision: how much IOPS and throughput the workload needs, where the limits lie, which configuration meets the goal, and what was measured to confirm that decision.
