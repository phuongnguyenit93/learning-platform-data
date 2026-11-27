# EBS IOPS, Throughput, and Performance Optimization

> **Chapter:** Block and File Storage  
> **Module:** CLOUD_PROVIDERS_AWS — learn how to design AWS infrastructure from Regions/AZs, IAM, and VPC to compute, storage, databases, integration, and serverless; make decisions grounded in security, monitoring, resilience, and cost.

## Learning Objectives

**Amazon Elastic Block Store (Amazon EBS)** provides durable block storage for supported AWS workloads, typically EC2. Increasing EBS capacity does not automatically increase performance; buying more IOPS does not guarantee a faster application either. To optimize effectively, operators must understand the relationship among **IOPS**, **throughput**, **latency**, **I/O size**, **queue depth**, and **EC2 instance** limits.

After this lesson, you will be able to:

1. Estimate throughput from IOPS and I/O size; use Little's Law to explain queue depth and latency.
2. Compare common EBS types—**gp3, gp2, io2, io1, st1, and sc1**—by access pattern and performance calculation.
3. Identify whether a bottleneck lies in the volume, EC2 instance, filesystem, application, or storage network.
4. Read **CloudWatch EBS** metrics, distinguishing averages, peak loads, latency, queue length, and burst credit consumption.
5. Select appropriate capacity, IOPS, throughput, and EC2 instance types for databases, web apps, batch jobs, and analytics.
6. Use the AWS CLI to inspect specs, read metrics, and benchmark with **fio** on a dedicated lab volume.
7. Plan configuration changes, protect data, monitor outcomes, and control costs.

## 1. Placing EBS in the Application I/O Path

EBS is a **block device**: the operating system sees a block device and can create partitions, format a filesystem, and mount it. An EC2 instance commonly attaches EBS volumes as OS or data drives. Typically, an EBS volume belongs to **one Availability Zone** and attaches to an instance in that matching AZ; the service replicates volume data within the AZ for durability.

~~~mermaid
flowchart LR
    A[Application: DB / web / batch] --> B[Filesystem / page cache]
    B --> C[Block I/O: kernel + NVMe driver]
    C --> D[EC2 EBS bandwidth / IOPS limit]
    D --> E[EBS volume performance]
    E --> F[Data blocks on EBS]
    G[CloudWatch & OS telemetry] -. Observes .-> A
    G -. Observes .-> C
    G -. Observes .-> D
    G -. Observes .-> E
~~~

Not all application I/O becomes EBS I/O: **page cache**, buffers, filesystem metadata, flush mechanisms, and batching alter the actual storage requests issued. Therefore, HTTP request rates or SQL query counts do not translate one-to-one into EBS IOPS.

**Example:** 10,000 API requests/second does not mean the disk needs 10,000 IOPS. If most data resides in RAM cache, EBS may receive only a small fraction of accesses. Conversely, a single SQL query might read many pages and generate hundreds of I/Os.

### 1.1. Comparing Block Storage, File Storage, and Object Storage

| Service | Access model | Suitable scenarios | Key points to remember |
|---|---|---|---|
| **Amazon EBS** | Block device/volume, typically attached to EC2 | Root disks, self-managed databases, apps needing a local filesystem | AZ-scoped volume; performance governed by volume type and instance limits |
| **Amazon EFS** | File storage over NFS | Multiple Linux machines sharing files and directory trees | Network/file access pattern; performance and cost models differ from EBS |
| **Amazon FSx** | Managed file storage per filesystem engine | Windows SMB, Lustre/HPC, OpenZFS, ONTAP per requirements | Select by protocol, performance, and ecosystem |
| **Amazon S3** | Object API | Static files, backups, data lakes, documents, media | Not a native block device; different IOPS/filesystem mechanics |
| **EC2 instance store** | Physical storage attached to host, where type supports | Scratch, cache, or replicated data | Do not use as the sole durable copy of critical data |

EBS supports **Multi-Attach** for certain supported volume types and instances, but that does not mean instances can freely write concurrently to a standard filesystem. This lesson focuses on EBS for **one workload with one or more volumes**; Multi-Attach is covered under limitations.

## 2. Four Quantities That Govern Performance

### 2.1. IOPS: I/O Operations Per Second

**IOPS (Input/Output Operations Per Second)** measures block read/write operations completed per second. This metric matters most for **small, random I/O**, such as databases reading 4–16 KiB pages, indexes, or metadata.

~~~text
Measured IOPS = (read operations + write operations) / seconds
~~~

**3,000 IOPS** means an average of roughly 3,000 operations processed per second during the measurement window; by itself, it says nothing about the byte size of each operation or how many milliseconds each takes.

Note: the application, OS, and EBS can split or merge I/Os. **I/O size** and **measurement point** affect reported op counts; compare metrics only under identical workload characteristics.

### 2.2. Throughput: Data Processed Per Second

**Throughput** is typically measured in **MiB/s** or **MB/s**. MiB uses base 2 (**1 MiB = 1,048,576 bytes**); MB typically uses base 10 (**1 MB = 1,000,000 bytes**). When comparing numbers, confirm which unit AWS uses.

Approximate formula for uniform-sized I/O:

~~~text
Throughput (MiB/s)
≈ IOPS × I/O size (KiB) / 1024
~~~

Example at the same **3,000 IOPS**:

| Average I/O size | Theoretical throughput at 3,000 IOPS |
|---|---:|
| 4 KiB | 11.72 MiB/s |
| 16 KiB | 46.88 MiB/s |
| 64 KiB | 187.5 MiB/s |
| 256 KiB | 750 MiB/s |

If the volume is capped at **125 MiB/s** throughput, the 64 KiB and 256 KiB rows **cannot automatically reach** those theoretical figures. IOPS, throughput, and instance limits jointly constrain real-world speed.

### 2.3. Latency: Delay of a Single I/O

**Latency** is the time to complete one operation from submission to result, usually measured in ms or µs.

A workload running 1,000 IOPS at hundreds of milliseconds latency can deliver a worse user experience than 800 IOPS at very low latency. When optimizing online databases, inspect **p95/p99 latency** at the application layer alongside storage latency, throughput, and IOPS.

High latency can stem from:

- Long queues in the application, kernel, or device.
- EBS volume exhausting its IOPS/throughput budget.
- EC2 instance hitting its EBS bandwidth/IOPS cap.
- Filesystem sync, lock contention, fsync, or dirty-page flushing.
- I/O reading snapshot-backed blocks that have not been fully hydrated.
- Workloads with small/random read/write patterns generating high op counts or queue contention.

Do not assume every IOPS increase reduces latency; the bottleneck may lie elsewhere.

### 2.4. Queue Depth: Outstanding I/Os Waiting for Completion

**Queue depth (QD)** is the number of outstanding I/O operations. To utilize high IOPS, systems often must submit enough I/Os in parallel. An approximate relationship from **Little's Law**:

~~~text
Outstanding I/O ≈ IOPS × latency (seconds)
~~~

Example: targeting **5,000 IOPS** at an average latency of **2 ms = 0.002 s** requires roughly **10 concurrent I/Os** in steady state. If only one request is issued at a time, IOPS throughput is throttled by the round-trip wait of each individual I/O.

**Important:** pushing QD too high can inflate latency and overload the application. Do not blindly maximize QD just for a prettier IOPS number when p99 SLOs suffer.

### 2.5. Reading All Four Quantities Together

| Workload | I/O size | Typically critical metrics | When to suspect a bottleneck? |
|---|---|---|---|
| OLTP database | Small, random, read/write mix | IOPS and latency | High DB I/O wait, growing queue, degrading query p99 |
| Backup or large data scan | Large, sequential | Throughput MiB/s | Throughput plateaus even as workers increase |
| Cached web server | Irregular I/O | Tail latency and burst behavior | Deploys/log rotation cause latency spikes |
| Search index | Mix of small/random and sequential | IOPS, throughput, latency | Index builds or segment merges lengthen queues |
| Data pipeline/batch | Mostly sequential, multi-worker | Throughput and job runtime | Volume or EC2 bandwidth saturates |

## 3. Limits That Jointly Govern Real-World Speed

You can visualize the throughput ceiling as:

~~~text
Actual throughput
≤ min(
    Available IOPS × effective I/O size,
    EBS volume throughput ceiling,
    EC2 instance EBS bandwidth ceiling,
    OS/filesystem/application limits and other factors
  )
~~~

Similarly for IOPS, actual rates cannot exceed the capacity of the **volume**, **instance**, or the application's rate of issuing I/O requests.

~~~mermaid
flowchart TD
    A[Application is slow] --> B[Measure I/O size + read/write mix]
    B --> C[Measure IOPS, MiB/s, latency, queue]
    C --> D{Which limit is hit first?}
    D -->|Volume IOPS| E[Increase IOPS or change volume type]
    D -->|Volume throughput| F[Increase throughput or change volume]
    D -->|EC2 EBS limit| G[Choose instance with higher EBS bandwidth]
    D -->|Application / filesystem| H[Tune cache, batching, concurrency, queries]
    E --> I[Re-benchmark and measure cost]
    F --> I
    G --> I
    H --> I
~~~

**Numeric example:** a workload writes **256 KiB** I/Os and needs **250 MiB/s**. The theoretical minimum IOPS is roughly:

~~~text
250 MiB/s × 1024 KiB/MiB ÷ 256 KiB = 1,000 IOPS
~~~

If the volume only has **125 MiB/s** throughput, raising IOPS from 3,000 to 6,000 **will not lift the throughput ceiling**. Conversely, a **4 KiB** workload wanting 250 MiB/s needs roughly **64,000 IOPS** in theory; provisioning 250 MiB/s on a 3,000-IOPS volume will not be enough.

## 4. Choosing an EBS Volume Type by Access Pattern

### 4.1. Volume Type Overview

| EBS volume type | Media | Suited for | Typical use cases | Key constraints |
|---|---|---|---|---|
| **gp3** | SSD | Balancing IOPS, throughput, and cost; independent tuning | Boot, web, apps, moderate databases, most general workloads | Includes baseline IOPS/throughput; provisioning above baseline incurs extra cost |
| **gp2** | SSD | IOPS tied to size; credit/burst model on certain sizes | Existing gp2 workloads, moderate burst needs | Raising baseline IOPS may require inflating size; credit depletion causes instability |
| **io2** | Provisioned IOPS SSD | High IOPS, consistency, and service durability specs | Mission-critical databases, heavy random I/O | Provisioned IOPS pricing; requires capable instance for very high targets |
| **io1** | Provisioned IOPS SSD | Provisioned IOPS for legacy workloads | Existing systems requiring io1 | Evaluate migrating to io2/gp3 for compatibility and cost |
| **st1** | Throughput-optimized HDD | Streaming, large-block sequential access | Sequential log/data warehouse pipelines, large scans | Unsuitable for small random I/O; cannot be used as boot volume |
| **sc1** | Cold HDD | Infrequently accessed data, lower throughput | Cold datasets needing block storage | Low performance; cannot be used as boot volume |
| **standard (magnetic)** | Previous-gen HDD | Legacy | Pre-existing systems | Not a common choice for new deployments |

**There is no single "fastest" volume type for every problem.** For example, **io2** addresses specialized IOPS and durability requirements, whereas **gp3** is usually more sensible when a workload does not demand those levels. **st1** provides good throughput for long sequential reads, yet is a poor fit for 4 KiB random I/O.

### 4.2. gp3: Decoupling IOPS and Throughput from Capacity

With gp3, the standard baseline of **3,000 IOPS** and **125 MiB/s** is included in storage pricing regardless of volume size within supported bounds. Users can **provision higher IOPS and throughput above baseline** within AWS-published limits and rules; allocations above baseline are billed separately.

Example (verify current Regional specs/pricing before creating):

~~~text
Volume A: gp3, 100 GiB, 3,000 IOPS, 125 MiB/s
Volume B: gp3, 100 GiB, 6,000 IOPS, 250 MiB/s
~~~

Both volumes have the same capacity but different I/O budgets. If the workload does **4 KiB random I/O** and genuinely exceeds 3,000 IOPS, B can help. If the workload uses only 100 IOPS but needs high bandwidth for file copies, focus on **throughput**. If the workload is capped by the EC2 instance, upgrading B's parameters may yield little gain.

**Key difference from gp2:** gp3 does not require inflating capacity just to raise baseline IOPS and **does not use CPU-style burst credits for gp3 IOPS/throughput** the way gp2 does. That makes gp3 performance much more predictable.

### 4.3. gp2: Volume Size Scaling and Burst Credits

With gp2, baseline IOPS scales with size—typically described as **3 IOPS/GiB** within type limits—while smaller sizes have **burst capability** via I/O credits. Under sustained heavy load, credits can deplete and drop performance back to baseline.

Conceptual example:

~~~text
Small gp2 volume:
- Briefly hits high IOPS via burst.
- Continuous load can drop back to baseline.
- Increasing size raises baseline but increases storage cost.
~~~

Therefore, if a gp2 system runs fast early in the hour and slows down late in a batch run, inspect **BurstBalance** and I/O patterns instead of merely adding worker threads.

### 4.4. io2/io1: When IOPS and Latency Matter Most

**Provisioned IOPS SSD** fits workloads demanding high IOPS, steadiness, and specialized durability characteristics. **io2 Block Express** on supported configurations reaches far higher limits than general-purpose SSDs, though exact ceilings depend on volume/instance specs and current AWS limits.

When choosing io2:

1. Define targets for **IOPS, p95/p99 latency, block size, write ratio, and durability**.
2. Verify **EC2 instance support** for the desired features/performance.
3. Account for both **GiB/month** and **provisioned IOPS**, plus instance and snapshot costs.
4. Benchmark on a production-equivalent setup.
5. Consider EBS Multi-Attach only when the application truly supports coordinated multi-host writes.

**Do not treat io2 as an automatic fix** for slow SQL caused by missing indexes, lock contention, or small connection pools. Query optimization often yields bigger gains than upgrading storage.

### 4.5. st1/sc1: Sequential Throughput Optimization and Cold Data

**st1** and **sc1** are HDD types with throughput-oriented performance models and should not be used for heavy small/random I/O. Neither can serve as an EBS boot volume. Portions of their performance model use burst buckets; large-block sequential reads/writes fit far better than OLTP databases.

Many workloads needing shared files or data lakes fit better on **EFS/FSx/S3** than st1/sc1. Choose by **access pattern and protocol**, not per-GiB rate alone.

## 5. EC2 EBS Limits and Reading Spec Tables

### 5.1. Fast Volume Attached to an Instance with Insufficient EBS Bandwidth

Each EC2 instance type has its own **baseline/maximum EBS bandwidth, throughput, and IOPS** specs. When multiple volumes attach to the same instance, aggregate I/O still passes through that instance's ceiling. Consequently:

- Raising gp3 to 1,000 MiB/s on a machine whose EBS throughput cap is lower will be throttled by EC2.
- Attaching two 500 MiB/s EBS volumes does not guarantee 1,000 MiB/s combined if the instance cannot sustain it.
- **"Up to"** figures usually imply burst/baseline mechanics; verify exact specs for the specific instance type.
- Instances use dedicated EBS paths and I/O packet caps defined by AWS/Nitro capabilities; do not infer them from general VPC network bandwidth.

### 5.2. EBS-Optimized and Nitro

Many modern instances are **EBS-optimized** by default. This provides a dedicated optimized path to EBS, but **does not remove the instance's EBS bandwidth/IOPS ceiling**. Certain granular telemetry or ultra-high performance tiers require **Nitro-based instances** and compatible OS/drivers.

Check instance types via the API instead of assuming every 2-vCPU machine has identical EBS capability.

### 5.3. Do Not Add Theoretical Numbers Mechanically

Suppose:

~~~text
gp3 #1: configured for 250 MiB/s
gp3 #2: configured for 250 MiB/s
EC2 instance: effective EBS ceiling 350 MiB/s
=> Combined throughput of both volumes is unlikely to exceed 350 MiB/s.
~~~

This is a simplified ceiling example: beyond throughput, real results also depend on IOPS, I/O size, read/write mix, queue depth, workload contention, and filesystem layout.

## 6. Reading CloudWatch Metrics to Spot What Is Missing

### 6.1. Common Metrics

Amazon EBS publishes metrics under the **AWS/EBS** namespace depending on volume type and EC2 platform. Common metrics:

| Metric | Common unit / statistic | Practical meaning |
|---|---|---|
| **VolumeReadOps** | Count; Sum over period | Read I/Os processed by the volume |
| **VolumeWriteOps** | Count; Sum over period | Write I/Os |
| **VolumeReadBytes** | Bytes; Sum | Bytes read from the volume |
| **VolumeWriteBytes** | Bytes; Sum | Bytes written to the volume |
| **VolumeTotalReadTime** | Seconds; Sum (when supported) | Cumulative read I/O processing time |
| **VolumeTotalWriteTime** | Seconds; Sum (when supported) | Cumulative write I/O processing time |
| **VolumeQueueLength** | Count; Average | Pending I/Os queued per metric definition |
| **BurstBalance** | Percent, on supported volume types | Remaining burst credit percentage, useful for gp2/st1/sc1 |
| **VolumeIdleTime** | Seconds, when supported | Time the volume spent with no active I/O |

Some **metrics or statistics are unavailable** for certain volume types/instances; newer metrics may also differ on Nitro platforms. Check the list of metrics **actually emitted in CloudWatch** for the volume you are studying.

### 6.2. Converting Metrics to IOPS and MiB/s

Suppose over **300 seconds**, CloudWatch reports:

~~~text
VolumeReadOps (Sum)  = 600,000
VolumeWriteOps (Sum) = 300,000
VolumeReadBytes (Sum)  = 62,914,560,000 bytes
VolumeWriteBytes (Sum) = 31,457,280,000 bytes
~~~

Calculate:

~~~text
Read IOPS  = 600,000 / 300 = 2,000
Write IOPS = 300,000 / 300 = 1,000
Total IOPS = 3,000

Read throughput  = 62,914,560,000 / 300 / 1,048,576 = 200 MiB/s
Write throughput = 31,457,280,000 / 300 / 1,048,576 = 100 MiB/s
Total throughput = 300 MiB/s
~~~

These figures imply an average effective I/O size of about **102.4 KiB** (300 MiB/s ÷ 3,000 IOPS), very different from a 4 KiB workload. These are **hypothetical exercise numbers**, not representative of any specific volume type.

**Watch your statistics:** divide **Sum** by period length to get rates; do not apply the same formula to Average on count metrics without understanding what the metric represents. A 5-minute window can hide a 10-second spike; for p99-sensitive systems, add OS/application telemetry.

### 6.3. Average Latency from CloudWatch

If `VolumeTotalReadTime` has valid data, you can estimate:

~~~text
Average read latency (ms)
≈ 1000 × VolumeTotalReadTime (Sum, seconds)
       / VolumeReadOps (Sum)
~~~

Do not divide when read ops = 0. Average latency metrics **do not reveal p99**; to observe tail latency, use OS/application instrumentation or detailed service-supported latency metrics.

### 6.4. Supplementing with Linux and Application Data

Common tools when you have OS access:

- **iostat -x 1**: I/O volume, await, queue depth, and device utilization per tool version.
- **lsblk**, **findmnt**, **df -h**: confirm exact EBS block device, mount point, and free space.
- **pidstat -d** or application profilers: identify which process drives I/O.
- **fio**: benchmark by block size, read/write mix, and queue depth; requires an isolated sandbox.
- **APM/JVM metrics**: query latency, lock waits, heap/cache behavior, worker concurrency.

**Never rely solely on `%util=100%` from `iostat` to conclude an SSD has hit its IOPS ceiling**: `%util` interpretation varies by device and parallelism. Combine latency, throughput, IOPS, queue depth, and published limits.

## 7. Step-by-Step Performance Optimization Workflow

### Step 1 — Define Application Targets

For instance, a query API must stay under **120 ms p95**, a batch export must finish within **20 minutes**, or a database must process **5,000 transactions/sec** with low error rates. These are application-level SLOs; do not set a goal like "maximize IOPS" detached from the workload.

### Step 2 — Record Current I/O Characteristics

During both peak and off-peak windows, collect:

- Read/write IOPS and MiB/s, average I/O size.
- Sequential/random pattern, read/write ratio, sync/async, fsync behavior.
- Average and p95/p99 latency (OS/app), queue depth.
- CPU/memory/cache hit rate, GC, query plans, and network load.
- Volume type, size, provisioned IOPS/throughput, EC2 instance type, and EBS limits.

### Step 3 — Check Limits Layer by Layer

| Observation | Hypothesis | Verification |
|---|---|---|
| IOPS near provisioned limit, MiB/s still low | Volume IOPS is the bottleneck | Compare metrics against volume specs; test raising IOPS in lab |
| MiB/s plateaus flat while IOPS is not high | Volume throughput cap | Check provisioned throughput and I/O size |
| Multiple volumes slow down together concurrently | EC2 instance EBS limit | Check instance EBS baseline/max and sum total I/O |
| Latency rises, app CPU high, EBS not busy | App/query/cache bottleneck | Profile CPU, queries, heap, locks |
| gp2 slows down after continuous run | Burst credits exhausted | Check BurstBalance and compare with baseline |
| EBS is fast enough yet job stays slow | Threads, serialization, network, locks, read amplification | Profile each pipeline stage |
| Read latency spikes after snapshot restore | Blocks read for first time / not yet hydrated | Review snapshot initialization procedures and FSR options |

### Step 4 — Optimize Before Buying Higher Specs

- Optimize queries and indexes to avoid unnecessary scans.
- Use batching, async I/O, and sensible concurrency.
- Improve cache hit rates; reduce redundant writes or read amplification.
- Consider compression or block-size tuning, watching CPU trade-offs.
- Separate batch and OLTP workloads if they contend for I/O.
- Adjust volume or instance sizing only after confirming the bottleneck via metrics.

### Step 5 — Make Controlled Changes and Re-Measure

Establish a **baseline** before changing anything; adjust one measurable variable at a time (e.g., 3,000 → 6,000 IOPS, or 125 → 250 MiB/s), keep workload conditions comparable, and evaluate **latency, throughput, error rate, and cost** afterward.

AWS **Elastic Volumes** often allows modifying size/type/IOPS/throughput on supported volumes without detaching. However, changes go through **modifying/optimizing/completed** states, face cooldown limits, and carry specific rules; check documentation before executing. Expanding EBS capacity may require **extending partitions/filesystems** in the OS; increasing IOPS/throughput typically does not require filesystem changes.

## 8. Lab 1 — Inspecting EBS Specs via AWS CLI (Read-Only)

> This section only inspects configuration without creating or modifying volumes. Use AWS CLI v2 in a **sandbox** with EC2/CloudWatch read permissions. Shell examples use **Bash** and Region `ap-southeast-1`; substitute your own profile/IDs.

### 8.1. Verify Account and Region

~~~bash
export AWS_PROFILE=aws-lab-dev
export AWS_DEFAULT_REGION=ap-southeast-1

aws sts get-caller-identity --profile "$AWS_PROFILE"
~~~

If using **CloudShell** with an active session and without an `aws-lab-dev` profile, omit the `export AWS_PROFILE=...` line and `--profile` flags.

### 8.2. Inspect a Provisioned Volume

~~~bash
REGION=ap-southeast-1
VOL_ID=vol-0123456789abcdef0

aws ec2 describe-volumes \
  --volume-ids "$VOL_ID" \
  --region "$REGION" \
  --query 'Volumes[].{Id:VolumeId,Type:VolumeType,GiB:Size,IOPS:Iops,MiBs:Throughput,AZ:AvailabilityZone,State:State,Encrypted:Encrypted}' \
  --output table
~~~

The example ID is **hypothetical**; use only a volume you are authorized to inspect. The `Throughput` column may be empty for volume types without a separate provisioned throughput parameter. Always check **VolumeType** before interpreting IOPS/throughput.

### 8.3. Check EC2 Instance Type EBS Limits

~~~bash
aws ec2 describe-instance-types \
  --instance-types m7i.large \
  --region "$REGION" \
  --query 'InstanceTypes[].{Type:InstanceType,EBS:EbsInfo.EbsOptimizedInfo}' \
  --output json
~~~

Attributes such as `BaselineBandwidthInMbps`, `MaximumBandwidthInMbps`, `BaselineThroughputInMBps`, `MaximumThroughputInMBps`, `BaselineIops`, and `MaximumIops` (when returned by the API) reveal instance EBS capabilities. **Mbps (megabits/s) differs from MB/s (megabytes/s) and MiB/s**; do not compare numbers directly without unit conversion.

To verify which type an actual instance uses (if authorized and given an instance ID):

~~~bash
INSTANCE_ID=i-0123456789abcdef0

aws ec2 describe-instances \
  --instance-ids "$INSTANCE_ID" \
  --region "$REGION" \
  --query 'Reservations[].Instances[].{Id:InstanceId,Type:InstanceType,AZ:Placement.AvailabilityZone,State:State.Name}' \
  --output table
~~~

### 8.4. Read CloudWatch Metrics Over a Time Window

Example fetching `VolumeReadOps` over the **past 30 minutes** in Bash with GNU `date` (such as AWS CloudShell Linux):

~~~bash
START_UTC=$(date -u -d '30 minutes ago' +%Y-%m-%dT%H:%M:%SZ)
END_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)

aws cloudwatch get-metric-statistics \
  --namespace AWS/EBS \
  --metric-name VolumeReadOps \
  --dimensions "Name=VolumeId,Value=$VOL_ID" \
  --start-time "$START_UTC" \
  --end-time "$END_UTC" \
  --period 300 \
  --statistics Sum \
  --region "$REGION" \
  --output table
~~~

Each datapoint represents **total read operations within a 300-second period** (for Sum), not read IOPS directly. To get average read IOPS, compute **Sum / 300**. Repeat with `VolumeWriteOps`, `VolumeReadBytes`, and `VolumeWriteBytes`. The CLI may return no datapoints if the volume had zero I/O, data has not propagated yet, or permissions are restricted.

**Quick exercise:** if `VolumeReadOps=450000` over 300 seconds, what is the read IOPS? If `VolumeReadBytes=47,185,920,000` bytes in the same window, roughly what are the read throughput and average I/O size?

## 9. Lab 2 — Benchmarking with fio on a Test Volume

**Proceed only if your sandbox permits and you have a dedicated EBS volume for this lab.** `fio` can write large amounts of data and degrade running applications; **never benchmark directly against a raw device**, **never use a production filesystem**, and never target a file holding important data. The goal is to observe the difference between **random 4 KiB IOPS** and **sequential 256 KiB throughput**, not to chase maximum numbers at any cost.

### 9.1. Prepare Lab Resources

- EC2 instance in the same AZ as an authorized volume, attached and mounted separately.
- An ext4/xfs (or equivalent) filesystem formatted **on the lab volume** per approved procedures; mount path e.g. `/mnt/ebs-lab`.
- At least **2 GiB free space** for a 1 GiB benchmark file, with no other workloads on the volume.
- `fio` installed from a trusted OS repository.
- Permissions to create/delete files in the lab directory, while monitoring EC2/EBS cost and runtime.

**Pre-run checks:**

~~~bash
TEST_DIR=/mnt/ebs-lab
TEST_FILE="$TEST_DIR/fio-training.bin"

findmnt "$TEST_DIR"
df -h "$TEST_DIR"
lsblk -o NAME,SIZE,TYPE,MOUNTPOINTS

test ! -e "$TEST_FILE" || {
  echo "File fio-training.bin already exists: refusing to overwrite"
  exit 1
}
~~~

If `findmnt` does not confirm the **exact mount point of your test volume**, stop; do not accidentally write files into a directory on the root filesystem.

### 9.2. Create the Benchmark File

This command **writes a new file** at `/mnt/ebs-lab/fio-training.bin`, not across the raw block device:

~~~bash
fio \
  --name=prepare \
  --filename="$TEST_FILE" \
  --size=1G \
  --rw=write \
  --bs=1m \
  --ioengine=libaio \
  --iodepth=8 \
  --direct=1 \
  --group_reporting
~~~

This write consumes I/O and takes time. If the mount point is wrong or free space is insufficient, do not continue. Pre-writing the file ensures subsequent read tests do not depend on a nonexistent file.

### 9.3. Measure 4 KiB Random Reads

~~~bash
fio \
  --name=randread-4k \
  --filename="$TEST_FILE" \
  --size=1G \
  --rw=randread \
  --bs=4k \
  --ioengine=libaio \
  --iodepth=32 \
  --direct=1 \
  --runtime=60 \
  --time_based \
  --group_reporting
~~~

Observe the **IOPS**, **BW**, and latency (`clat`/percentiles if shown) output lines. Re-run with `--iodepth=1` or `--iodepth=8` to see the effect of queue depth; do not raise QD arbitrarily if latency is already poor.

### 9.4. Measure 256 KiB Sequential Reads

~~~bash
fio \
  --name=seqread-256k \
  --filename="$TEST_FILE" \
  --size=1G \
  --rw=read \
  --bs=256k \
  --ioengine=libaio \
  --iodepth=16 \
  --direct=1 \
  --runtime=60 \
  --time_based \
  --group_reporting
~~~

Compare throughput with the 4 KiB random read step. Note that the same volume can deliver **good random IOPS** while **sequential throughput hits its provisioned cap**. Benchmark data can also be cached at other layers; `--direct=1` minimizes OS page cache effects but does not eliminate all caching or workload variance.

### 9.5. Clean Up Resources

After confirming the file is the one you created and is no longer needed:

~~~bash
rm -- "$TEST_FILE"
~~~

For cloud resources, clean up the **lab EC2 instance and EBS volume** per sandbox guidelines, checking `DeleteOnTermination`, snapshots, public IPv4s, and residual charges. **Never delete a volume used by another system.** If a snapshot must be kept, record its owner and retention period for cost management.

### 9.6. Results Log Table

| Test | Block size | Queue depth | Measured IOPS | Measured MiB/s | Mean / p99 latency |
|---|---:|---:|---:|---:|---:|
| Random read | 4 KiB | 1 | Enter result | Enter result | Enter result |
| Random read | 4 KiB | 8 | Enter result | Enter result | Enter result |
| Random read | 4 KiB | 32 | Enter result | Enter result | Enter result |
| Sequential read | 256 KiB | 16 | Enter result | Enter result | Enter result |

**Discussion:** as QD increases, do IOPS keep rising indefinitely? Does latency change? When switching block size from 4 KiB to 256 KiB, which metric increases more? Were results capped by the volume or by the instance?

## 10. Modifying an EBS Volume to Improve Performance

AWS provides **Elastic Volumes** to adjust certain properties of a live volume without always detaching. However, supported configurations and transition states vary by volume type, instance, and current rules.

### 10.1. Example Modifying gp3 Settings (Illustrative Only)

Scenario: a lab gp3 volume has 3,000 IOPS / 125 MiB/s, and after identifying the bottleneck the workload needs 6,000 IOPS / 250 MiB/s.

~~~bash
# ONLY EXECUTE if authorized and approved for a LAB volume
aws ec2 modify-volume \
  --volume-id vol-0123456789abcdef0 \
  --volume-type gp3 \
  --iops 6000 \
  --throughput 250 \
  --region ap-southeast-1
~~~

This illustrative command **modifies resources and can increase costs**; you do not need to run it to complete the core exercises. When authorized to apply it, track progress:

~~~bash
aws ec2 describe-volumes-modifications \
  --volume-ids vol-0123456789abcdef0 \
  --region ap-southeast-1
~~~

**Preparation checklist:** appropriate snapshot/backup, list of dependent applications, baseline metrics, budget approval, and a rollback or volume-migration plan. Never assume every modification can be immediately reversed; volumes enforce cooldown periods between edits and rollback rules vary by attribute.

### 10.2. When to Increase Size, IOPS, Throughput, or Upgrade EC2?

| Verified observation | Recommended action | Prerequisites |
|---|---|---|
| Out of GB space only; I/O not saturated | Increase **volume size** | Prepare to extend OS filesystem if needed |
| gp3 hits IOPS ceiling, MiB/s still low | Increase **provisioned IOPS** | Instance and workload have sufficient queue/concurrency |
| gp3 hits MiB/s ceiling, IOPS still low | Increase **provisioned throughput** | I/O size and EC2 EBS bandwidth permit |
| EC2 EBS bandwidth/IOPS hits ceiling | Change to a suitable **instance type** | Check AMI, quotas, AZ, cost, and downtime impact |
| gp2 frequently exhausts burst credits | Consider **gp3**, optimize workload | Compare cost and migration limits |
| Database I/O latency must be very low, gp3 falls short | Evaluate **io2** + suitable instance | Benchmark real latency and total cost |
| Heavy repeated reads of the same data | Optimize **cache/queries/indexes** | Prove bottleneck is not CPU or locks |

### 10.3. RAID, Striping, and Consequences

Multiple EBS volumes can be combined in the OS (e.g., RAID 0 striping) to spread I/O in specialized cases. However:

- Aggregate throughput remains capped by the EC2 instance.
- **RAID 0 widens the blast radius if any single volume fails**; it does not replace backups.
- Consistent snapshots across multiple volumes require mechanisms such as **multi-volume snapshots** and application quiescing where needed.
- For typical needs, a single properly sized and configured gp3/io2 volume is much simpler to operate.

Do not build RAID just to "double speed" without benchmarks first.

## 11. Cost and Choosing "Right-Sized" Performance

### 11.1. Components of an EBS Bill

**EBS costs may include**:

1. **Provisioned storage** by GiB capacity and duration of volume existence.
2. **Provisioned IOPS** for certain volume types, notably io1/io2 and gp3 allocations above baseline.
3. **Provisioned throughput** above the gp3 baseline.
4. **EBS snapshots**, snapshot data storage, and features like Fast Snapshot Restore if used.
5. **EC2 instances**, data transfer, and supporting workload resources.

Conceptual cost breakdown:

~~~text
Monthly total cost
≈ (Volume GiB × rate/GB-month × time ratio)
  + (Billable IOPS × rate/IOPS-month × time ratio)
  + (Billable throughput × rate/throughput-month × time ratio)
  + snapshots / FSR / EC2 / networking / logging
~~~

Line items vary by volume type and Regional price tables. Never plug unit rates into the formula without consulting current **AWS EBS Pricing** or the **AWS Pricing Calculator**.

### 11.2. Optimizing by Cost per Unit of Work

Workload A completes 1,000 jobs/hour at 3,000 IOPS; Workload B completes 1,100 jobs/hour at 10,000 IOPS, but costs three times as much. Raising IOPS makes sense only when work output increases, latency drops, or required SLOs improve **enough to justify the added spend**.

~~~text
Cost per successful job
= Total workload cost in period
  / Valid completed jobs

Cost per request
= Total workload cost in period
  / Requests completed meeting SLO
~~~

**Decision loop:** measure current load → make controlled change → re-benchmark → compute cost/job or cost/request → keep or adjust. AWS Budgets alerts are helpful, though they do not enforce hard spending caps automatically.

## 12. Security, Durability, and Resilience

### 12.1. EBS Data Encryption

- EBS supports **encryption at rest** integrated with **AWS KMS**; check account default encryption policies and required KMS permissions.
- Snapshots of encrypted volumes and volumes restored from them must respect corresponding encryption/KMS rules.
- **IAM policies** govern who can create, attach, modify, snapshot, and delete volumes; never embed access keys in scripts or AMIs.
- EBS does not replace **application-layer encryption**, filesystem permissions, or secrets management where required by the workload.

### 12.2. AZ-Scoped Volumes and Recovery Strategy

An EBS volume typically resides in **one AZ**, engineered for durability within that AZ. If the application must survive an entire AZ outage, add safeguards at the **application/data layer**:

- Replicate data across AZs via the application, database, or suitable managed service.
- Take snapshots aligned with RPO/RTO policies and test real restores.
- Fail over service to new instances/volumes in another AZ with an established data recovery workflow.
- Use EC2 Auto Scaling/Load Balancers for stateless tiers; avoid single-volume dependencies.
- Monitor snapshot retention, restore duration, and costs.

**EBS snapshots** are volume-level backups per service behavior; application-level consistency may require quiescing, flushing, or native database backup tools. Creating a snapshot does not guarantee logical consistency for an actively writing database.

### 12.3. Multi-Attach Is a Special Case

**EBS Multi-Attach** is available on AWS-supported volume types and EC2 instances/OSes (specifically io1/io2 under documented conditions), allowing one volume to attach to multiple instances **within the same AZ**. Use it only with **cluster-aware** applications/filesystems that coordinate locking and concurrent writes. Attaching a standard ext4/xfs filesystem and writing from multiple hosts **risks data corruption**. When shared files across multiple AZs are needed, evaluate EFS or FSx based on workload specifics.

## 13. Architecture Design Exercise

An online learning platform running on AWS has three components:

- **Java API** serving lesson reads and progress writes using EC2 + RDS.
- **Worker** processing report exports with hourly large-block sequential reads/writes.
- **Self-managed database** for a legacy component with small random I/O and sensitive query p99 latency.

Assume the system spans two AZs, cannot lose critical data, and has a fixed monthly budget.

### 13.1. Initial Proposal

| Component | Initial storage choice | What to measure | Scaling path |
|---|---|---|---|
| Java API | **gp3** for EBS root/data if EBS is used | Latency, throughput, log I/O, GC/queries | Optimize app/cache; upgrade gp3 only if truly bottlenecked |
| Sequential worker | **gp3** or **st1** if pattern fits and non-boot | MiB/s, block size, queue, job duration | Increase throughput, change instance, consider S3 for output storage |
| Legacy random I/O DB | Test **gp3**, consider **io2** if needed | IOPS, avg/p99 latency, queue, and DB waits | Improve indexes/cache or migrate to managed DB |
| Data backups | EBS snapshots and recovery copies/flows per RPO/RTO | Restore time, DB consistency, snapshot age | Periodic restore drills, multi-AZ as required |
| Shared files across multiple EC2s | **EFS/FSx** if workload requires file protocols | Concurrent clients, throughput, latency | Pick file service matching requirements |

Why not use io2 for every component? Because io2 is tuned for specialized demands, and its storage/IOPS pricing plus EC2 limits would be inefficient for lighter workloads. Why not choose st1 for the database? Because small random I/O is not a strength of throughput-optimized HDDs.

### 13.2. Calculation Exercise

An application needs **8,000 random IOPS**, average I/O size **8 KiB**, 70% reads and 30% writes. Answer the following:

1. Roughly what theoretical throughput in MiB/s is required?
2. If gp3 is provisioned at **8,000 IOPS / 125 MiB/s** and the EC2 instance supports it, is throughput the bottleneck based on theoretical math?
3. If average latency is 2 ms, roughly how many outstanding I/Os are needed per Little's Law?
4. If the workload shifts to 256 KiB I/O and still wants 8,000 IOPS, what is the theoretical throughput requirement?
5. If increasing IOPS does not reduce API p99 latency, which layers should you measure next?

**Suggested Answers:**

~~~text
1) 8,000 × 8 / 1024 = 62.5 MiB/s.
2) 62.5 MiB/s < 125 MiB/s; throughput is not the ceiling yet
   assuming all assumptions and other limits hold.
3) 8,000 × 0.002 = roughly 16 outstanding I/Os.
4) 8,000 × 256 / 1024 = 2,000 MiB/s.
5) Check query plans/cache, EC2 EBS bandwidth, queue depth,
   filesystem, CPU, locking, networking, and per-layer p99.
~~~

These are approximate calculations. Real performance also depends on I/O mix, system conditions, volume/type constraints, and concurrency.

## 14. Common Mistakes and How to Fix Them

| Symptom | Possible cause | Next diagnostic step |
|---|---|---|
| Increased IOPS but application did not speed up | Hit throughput cap, EC2 EBS limit, or app bottleneck | Measure I/O size, MiB/s, instance EBS limits, p95/p99 |
| Low sequential throughput despite high provisioned IOPS | Low throughput cap or unsuitable QD/block size | Compare provisioned MiB/s, fio bs, and concurrency |
| gp2 fast at start of run then slows down | Credit bucket depleted | Check BurstBalance and background load; consider gp3 |
| New volume from snapshot has high initial read latency | Snapshot data hydrating on first access | Review initialization/FSR procedures and cost |
| CloudWatch shows IOPS but no RAM/filesystem stats | EBS metrics differ from OS metrics | Install approved telemetry/agents; inspect iostat/df |
| Low CloudWatch IOPS yet high request p99 | Cache, locks, DB waits, or other latency | APM, query profiling, OS metrics |
| Expanded EBS size but filesystem did not grow | Partition/filesystem not extended | Check lsblk/findmnt/df and run proper resize steps |
| Cannot modify volume as planned | Active modification state, quota, or type/instance limits | Check describe-volumes-modifications and API docs |
| EBS deleted yet bill remains high | Snapshots, EC2, networking, FSR, or logs still exist | Cost Explorer and resource inventory by Region |
| Volume cannot attach to another EC2 | Different AZ or incompatible configuration | Check AvailabilityZone, attachment state, and volume type |
| Multi-Attach corrupts filesystem | Multiple writers on a non-cluster-aware FS | Redesign with cluster-aware FS or managed file storage |

## 15. Checklist and Self-Check

### Before Tuning Performance

- [ ] Defined concrete application-layer SLOs and a baseline representative of peak load.
- [ ] Calculated IOPS, MiB/s, I/O size, read/write mix, queue depth, and latency.
- [ ] Identified the exact **volume type, IOPS, throughput, size, and Region/AZ**.
- [ ] Verified against **EC2 EBS bandwidth/IOPS** and instance caps.
- [ ] Checked CPU, RAM, filesystem, queries, caching, and concurrency.
- [ ] Budgeted costs for volume, provisioned IOPS, throughput, snapshots, and EC2.
- [ ] Verified backup/restore, encryption, IAM/KMS, and blast radius.
- [ ] Prepared a verifiable change plan, monitoring, and lab cleanup.

### Knowledge Self-Check

1. How do IOPS and throughput differ? Why is 3,000 IOPS at 4 KiB very different from 256 KiB?
2. How does Little's Law explain the relationship among IOPS, latency, and outstanding I/O?
3. Why might raising gp3 from 3,000 to 10,000 IOPS fail to increase sequential throughput?
4. What is the fundamental difference between gp3 and gp2 regarding provisioning and bursting?
5. When should io2 be evaluated over gp3? What metrics justify that decision?
6. Why can instance EBS bandwidth cap the combined throughput of multiple attached volumes?
7. How is CloudWatch `VolumeReadOps` Sum converted into average read IOPS?
8. Why can running an `fio` benchmark on an active root filesystem jeopardize both data and measurement accuracy?
9. When expanding volume size, what extra steps must be checked inside the operating system?
10. Why is an AZ-scoped EBS volume insufficient by itself to make an application resilient to an entire AZ outage?
11. When are EFS or FSx more appropriate than EBS?
12. When is Multi-Attach safe, and why should a standard filesystem never be mounted read-write from multiple instances?

**Expected outcome:** you can **prove bottlenecks with metrics**, select a volume type and parameters suited to the access pattern, verify EC2 instance headroom, evaluate cost and recoverability, and re-measure performance after changes.

## Official AWS Documentation

- [Amazon EBS volume types](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-volume-types.html)
- [General Purpose SSD gp3 volumes](https://docs.aws.amazon.com/ebs/latest/userguide/general-purpose.html)
- [Provisioned IOPS SSD volumes](https://docs.aws.amazon.com/ebs/latest/userguide/provisioned-iops.html)
- [Monitor Amazon EBS volumes with CloudWatch](https://docs.aws.amazon.com/ebs/latest/userguide/using_cloudwatch_ebs.html)
- [Amazon EBS–optimized instances](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ebs-optimized.html)
- [Modify an Amazon EBS volume](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-modify-volume.html)
- [Initialize Amazon EBS volumes](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-initialize.html)
- [Amazon EBS Multi-Attach](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-volumes-multi.html)
- [Amazon EBS snapshots](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-snapshots.html)
- [Amazon EBS pricing](https://aws.amazon.com/ebs/pricing/)
- [AWS Pricing Calculator](https://calculator.aws/)

> **Note:** IOPS/throughput limits, EBS features, pricing, and EC2 options vary by Region, volume type, instance generation, and time. Before configuring production, verify current specifications in AWS documentation and APIs, benchmark real workloads, and approve changes through your organization's governance process.
