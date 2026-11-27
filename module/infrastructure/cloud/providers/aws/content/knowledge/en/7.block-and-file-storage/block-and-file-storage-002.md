# EBS Volumes and Choosing a Disk Type

## Learning Objectives

After studying this lesson, you will be able to:

- Explain what **Amazon Elastic Block Store (Amazon EBS)** is, how volumes work alongside Amazon EC2, and the relationships among **Region, Availability Zone (AZ), volume, instance, filesystem, and snapshot**.
- Distinguish between **General Purpose SSD (gp3, gp2)**, **Provisioned IOPS SSD (io2, io1)**, **Throughput Optimized HDD (st1)**, **Cold HDD (sc1)**, and previous-generation **Magnetic (standard)**.
- Estimate **capacity, IOPS, throughput, I/O size, latency**, and instance limits to select a volume with sufficient performance, recoverability, and cost control.
- Create, attach, format, mount, monitor, resize/tune performance, and back up EBS in proper sequence using the AWS Console, AWS CLI, and Linux.
- Distinguish **EBS** from **Amazon EFS, Amazon S3, and EC2 instance store**, and recognize when a workload requires a shared filesystem across multiple AZs instead of a block volume.
- Design durable and secure storage through **encryption, IAM, snapshots, backup policies, RPO/RTO recovery**, and CloudWatch observability.

**Module Context:** Within **CLOUD_PROVIDERS_AWS**, storage knowledge connects with **Region/AZ** infrastructure, IAM, VPC, compute, databases, resilience, monitoring, and cost. This lesson belongs to the **Block and File Storage** chapter and focuses on **EBS volumes and choosing a disk type**. When designing AWS applications, choosing the right EBS type often determines read/write speed, response time, ongoing costs, and data safety.

> **Note on Figures:** Capacity, IOPS, and throughput limits in this lesson reflect current AWS EBS documentation to teach decision-making; pricing, quotas, instance support, and features vary by Region/platform. Always verify specifications before production deployment.

## 1. What Is EBS and What Problem Does It Solve?

**Amazon EBS** provides durable **block storage** for workloads using Amazon EC2 and certain integrated AWS services. To the operating system, EBS appears as a **block device** (similar to a physical disk) after attachment to an instance. Administrators can create partitions, filesystems, format, and mount volumes as needed.

An EBS volume:

- Is a resource created in **one specific Availability Zone**; EC2 instances generally must be in the **same AZ** to attach it.
- Exists **independently of the EC2 start/stop lifecycle**. However, **deletion on termination** depends on the `DeleteOnTermination` flag in each block device mapping; root volumes often have their own default policy.
- Can serve as a **root/boot volume**, **data volume**, or store frequently read/written data such as databases, indexes, logs, and application data.
- Can have its **capacity or performance adjusted** with **Elastic Volumes** under supported conditions without necessarily detaching or rebooting the instance.
- Supports **EBS snapshots** to create restore points and copy across to another AZ by creating a new volume from the snapshot.
- Provides SSD/HDD types optimized for different workload and cost profiles.

### EBS Is Block Storage, Not an Automatic Filesystem

~~~mermaid
flowchart LR
    A[Amazon EC2 instance] --> B[EBS block device]
    B --> C[Partition / filesystem: ext4, XFS, NTFS...]
    C --> D[Mount point: /data or D: drive]
    A --> E[Application / DB]
    E --> D
    B --> F[EBS snapshot]
    F --> G[Restore into another volume]
~~~

For example, an EC2 instance running PostgreSQL has a **gp3 root volume** for the operating system and a **gp3 or io2 data volume** holding the DB data directory. The OS might see the disk as `/dev/nvme1n1` on a Nitro instance, then mount it at `/var/lib/postgresql`. EBS does not inherently know it is PostgreSQL: the database, filesystem, and application remain responsible for consistent writes.

### How Does EBS Compare to Other AWS Storage Options?

| Service | Access method | Scope/strengths | Suitable use cases |
| --- | --- | --- | --- |
| **Amazon EBS** | Block device attached to EC2 | Single-AZ volume, low latency, random I/O; snapshots | Root disks, databases on EC2, logs/indexes, application data |
| **Amazon EFS** | Shared file system over NFS | File sharing for multiple instances across AZs within supported configurations | Shared web/content, home directories, workloads needing POSIX NFS |
| **Amazon S3** | Object storage via API | Durable objects, large-scale storage and distribution | Images, videos, backups, data lakes, static objects |
| **EC2 instance store** | Block device local to hardware host | Can offer very high I/O, but data is ephemeral | Cache/scratch, regenerable data, intermediate processing |
| **Amazon FSx** | Managed file systems by variant | Specialized for Windows, Lustre, ONTAP, OpenZFS, and supported needs | Enterprise file shares, HPC, protocol-dependent applications |

**Do not choose EBS if the real requirement is for multiple containers/EC2 instances across multiple AZs to concurrently access and modify a shared directory over NFS.** In that scenario, evaluate EFS or FSx first. EBS **Multi-Attach** supports block sharing for specialized cases, but it does not turn EBS into a standard shared filesystem and does not span multiple AZs.

## 2. AZ Scope, Durability, and Volume Lifecycle

Suppose the Region is `ap-southeast-1`, consisting of distinct AZs. An EBS volume in AZ A cannot be directly attached to an EC2 instance in AZ B.

~~~mermaid
flowchart TB
  subgraph Region["AWS Region"]
    subgraph A["Availability Zone A"]
      EC2A[EC2 application A] --- EBS[(EBS data volume)]
    end
    subgraph B["Availability Zone B"]
      EC2B[EC2 replacement B]
      EBSB[(Volume restored from snapshot)]
      EC2B --- EBSB
    end
    EBS -. Create snapshot .-> Snap[EBS snapshot in Region]
    Snap -. Create new volume in AZ B .-> EBSB
  end
~~~

This leads to important design conclusions:

1. **EBS is not a drive directly accessible from every AZ.** Within an AZ, AWS designs EBS for durability/availability appropriate to the volume type, yet a single volume remains bound to one AZ.
2. **Stopping an EC2 instance does not mean losing EBS.** Terminating EC2 can automatically delete the root volume and may delete data volumes if `DeleteOnTermination=true`.
3. **Snapshots provide the recovery mechanism.** Snapshots are stored by AWS on internally managed Regional S3 infrastructure and replicated across AZs within the Region; users do not access snapshots directly via the S3 API.
4. **Recovering in another AZ** requires creating a **new volume from the snapshot** in the target AZ, attaching it to an instance in that AZ, and handling consistency/application recovery.
5. **Cross-Region disaster recovery** typically requires copying snapshots to another Region or using database DR mechanisms; an EBS volume itself does not synchronously replicate to another Region.

**High EBS volume durability does not mean the entire application has High Availability.** If a service runs on a single EC2 instance in one AZ, an AZ outage can still bring the application down. You must design Multi-AZ architectures, database replication/failover, health checks, data protection, and recovery drills aligned with RTO/RPO targets.

## 3. Understanding Three Performance Metrics: IOPS, Throughput, and Latency

### 3.1. IOPS: I/O Operations Per Second

**IOPS (Input/Output Operations Per Second)** measures the number of reads/writes per second. Workloads needing many small, random operations—such as OLTP databases or transaction logs—typically focus on IOPS and latency.

Example: 3,000 IOPS at 16 KiB I/O yields a theoretical data rate of roughly:

\[
3{,}000 \times 16\ \text{KiB/s} \approx 46.9\ \text{MiB/s}
\]

If each I/O is 256 KiB at the same 3,000 IOPS, theoretical throughput increases several-fold, but it may hit the **EBS volume/instance throughput limit** before reaching that rate.

### 3.2. Throughput: Data Read/Written Per Second

**Throughput** is typically measured in **MiB/s**. Large-file processing, sequential scans, batch ETL, log pipelines, and data warehouses are more likely to be bottlenecked by throughput than IOPS.

Approximate planning relationship:

\[
\text{Throughput (MiB/s)}
\approx \frac{\text{IOPS}\times\text{I/O size (KiB)}}{1{,}024}
\]

**Actual limits** also depend on EBS type, how the service accounts for I/O size, concurrent I/O, instance bandwidth, filesystem, and application behavior. This is an estimation model, not a benchmark guarantee.

### 3.3. Latency: Time to Complete One I/O

**Latency** is the time from submitting an I/O request until receiving the result, typically measured in ms or µs. Transactional databases are much more sensitive to latency than batch jobs that do not require immediate responses.

Even if a volume is provisioned for 20,000 IOPS, a workload issuing **one sequential I/O at a time** with noticeable latency cannot utilize the provisioned capacity. Therefore, consider **queue depth/concurrency** alongside IOPS and throughput.

**Approximate rule of thumb via Little's Law** to estimate in-flight I/O:

\[
\text{Average concurrent/in-flight I/Os}
\approx \text{IOPS}\times\text{Latency (seconds)}
\]

For example, 10,000 IOPS at 1 ms corresponds to roughly 10 concurrent I/Os. This is an intuition aid under steady-state conditions, not a substitute for benchmarking/measurement.

### 3.4. Why Selecting a Volume Is Not Just About Max IOPS

End-to-end performance is capped by the **narrowest bottleneck**:

~~~mermaid
flowchart LR
    APP[Application: queries / file writes] --> FS[Filesystem & OS I/O scheduler]
    FS --> EC2[EC2 EBS bandwidth / IOPS cap]
    EC2 --> VOL[EBS volume: IOPS, throughput, latency]
    VOL --> OBS[CloudWatch metrics / benchmark]
~~~

- **Volume cap:** provisioning gp3 at 8,000 IOPS does not guarantee every workload achieves 8,000.
- **Instance cap:** an EC2 instance has a total EBS IOPS/throughput limit. Attaching multiple volumes does not exceed the instance's aggregate cap.
- **I/O pattern:** sequential/large I/O favors throughput; random/small I/O favors IOPS and latency.
- **Caching, filesystem, queue depth:** can cause metric variance; OS-level IOPS differs from merged operations at the storage layer.
- **Volumes restored from snapshot:** an uninitialized volume may experience higher latency on the first read of unhydrated blocks; plan for volume initialization.

## 4. Common EBS Volume Types

The following table focuses on practical selection, not list pricing.

| Volume type | Technology / target | Supported capacity | Max limits per AWS docs | Boot volume |
| --- | --- | --- | --- | --- |
| **gp3** | General purpose SSD; provisions IOPS and throughput independently of size | **1 GiB–64 TiB** | **80,000 IOPS**, **2,000 MiB/s** with eligible size, ratios, and instance | Yes |
| **gp2** | Previous-gen general purpose SSD; IOPS tied to volume size and burst credits | **1 GiB–16 TiB** | **16,000 IOPS**, **250 MiB/s** | Yes |
| **io2 Block Express** | Provisioned IOPS SSD, high sustained performance and low latency | **4 GiB–64 TiB** | **256,000 IOPS**, **4,000 MiB/s** when instance/config supports it | Yes |
| **io1** | Previous-gen Provisioned IOPS SSD | **4 GiB–16 TiB** | **64,000 IOPS**, **1,000 MiB/s** depending on instance/provisioning | Yes |
| **st1** | Throughput-optimized HDD for frequent sequential access | **125 GiB–16 TiB** | **500 MiB/s** max/volume, using throughput credits | No |
| **sc1** | Low-cost HDD for infrequent sequential access | **125 GiB–16 TiB** | **250 MiB/s** max/volume, using throughput credits | No |
| **standard** | Legacy Magnetic; primarily legacy systems | **1 GiB–1 TiB** | Low/variable performance; not recommended for new deployments | Yes |

**Note on max IOPS/throughput:** These are **technical ceilings**, not values available on every volume. You must satisfy capacity minimums, IOPS/GiB ratios, EC2 type (especially Nitro), EBS-optimized bandwidth, Regional conditions, and quotas. For example, you cannot configure a 1 GiB gp3 volume at 80,000 IOPS simply because the table lists 80,000 as the max.

### 4.1. gp3: Default Starting Choice for Most Workloads

`gp3` is typically the **default baseline choice to evaluate first** for root disks, application data, dev/test environments, and low-to-medium/high-performance databases:

- **3,000 IOPS** and **125 MiB/s throughput** baseline included in storage pricing, independent of increasing size.
- Can provision up to **80,000 IOPS** and **2,000 MiB/s** subject to ratios and technical limits; capacity above baseline incurs additional performance charges.
- Does not rely on **burst credits** for provisioned IOPS/throughput, delivering steadier performance than an equivalently sized gp2 volume.
- Decoupling performance from capacity avoids buying excess storage just to get more IOPS.

**Additional constraints to remember:** Additional gp3 IOPS obeys a maximum ratio of **500 IOPS/GiB**; reaching 80,000 IOPS requires a volume of at least **160 GiB**. Maximum provisioned throughput obeys a ratio of **0.25 MiB/s per IOPS** and other conditions; reaching 2,000 MiB/s requires at least **8,000 IOPS** and **16 GiB** of capacity, along with a capable instance.

Example: You need 120 GiB of storage and 6,000 IOPS / 250 MiB/s. `gp3` lets you create a 120 GiB volume with those target IOPS and throughput instead of inflating volume size just for IOPS like gp2. However, 6,000 IOPS / 250 MiB/s is **not a free configuration**: usage above baseline is billed according to applicable rates.

### 4.2. gp2: Understanding Legacy Deployments

`gp2` relies heavily on **volume size** to determine baseline performance at roughly **3 IOPS/GiB** (with documented floors/ceilings); smaller volumes can temporarily **burst up to 3,000 IOPS** using an I/O credit balance. Once credits deplete, sustained IOPS can drop well below burst levels.

Approximate examples:

- gp2 **100 GiB**: baseline around **300 IOPS**, can burst higher while credits remain.
- gp2 **1 TiB**: baseline roughly **3,072 IOPS**.
- Very large gp2 volumes can reach **16,000 IOPS** up to the volume type limit.

Do not run a short few-minute benchmark on a small gp2 volume and conclude it can sustain that throughput/IOPS continuously. Observe longer runs and burst balance metrics where applicable. For new workloads, gp3 is usually simpler to size and control.

### 4.3. io2 Block Express and io1: High Performance, Low Latency

`io2 Block Express` is worth evaluating for very latency-sensitive databases, heavy random I/O transactions, and workloads needing **sustained IOPS** beyond gp3's practical range. Per current AWS documentation, `io2` now runs on **Block Express** architecture for both existing and new volumes.

Published characteristics:

- Maximum capacity **64 TiB**.
- Provisioned IOPS up to **256,000**, up to **1,000 IOPS/GiB** and subject to instance limits.
- Maximum throughput **4,000 MiB/s**.
- Designed average latency **sub-500 µs** for 16 KiB I/O under specified conditions, lower than typical general-purpose SSDs.

These numbers require a **compatible EC2 instance (especially Nitro)**, sufficient provisioned IOPS, bandwidth, and enough workload concurrency. Weigh storage cost plus IOPS fees before choosing io2.

`io1` is an older Provisioned IOPS SSD type that may appear in existing infrastructure. For new deployments, AWS generally steers users toward `io2` due to its performance/durability characteristics and newer support; do not pick io1 out of habit.

### 4.4. st1 and sc1: HDDs for Sequential Access Streams

`st1` and `sc1` suit **throughput-oriented workloads**, where most I/O consists of relatively large, sequential reads/writes:

- **st1**: Big data, data warehouses on EC2, log processing, and batch scans with high throughput needs.
- **sc1**: Infrequently accessed data that still needs a block device for sequential processing and prioritizes low capacity cost.
- **Neither supports use as a boot volume.**
- **Unsuitable** for OLTP databases, small random I/O, or low-latency requirements.
- Performance depends on **throughput credit balance**, volume size, and access pattern; peak differs from sustained throughput.

When data is infrequently accessed and does not require a mounted block device, **S3 with an appropriate storage class/lifecycle** can be more economical and flexible than sc1. Do not assume HDD is always cheapest from per-GiB rates alone without considering operations, copies, snapshots, and management overhead.

### 4.5. standard (Magnetic): Avoid for New Deployments

`standard` is a previous-generation Magnetic volume type with inconsistent performance that does not suit modern low-latency workloads. When encountering legacy systems, evaluate a migration path to gp3 or another suitable type, verify boot/OS/app compatibility, and test data/performance before migrating.

## 5. EBS Type Selection Matrix by Workload

| Workload / real requirement | What to measure | Starting option to evaluate | When to consider another type |
| --- | --- | --- | --- |
| Linux/Windows root volume, CI runners, web apps | Normal IOPS, boot time, capacity | **gp3** | If performance is highly specialized or platform limits differ |
| MySQL/PostgreSQL on EC2, moderate transactional load | Random IOPS, p95/p99 latency, WAL/redo, throughput | **gp3** sized from measurements | **io2** if sustained IOPS/latency exceeds gp3 capabilities |
| High-transaction database, strict latency sensitivity | Consistent IOPS, tail latency, I/O wait | **io2 Block Express** | gp3 if benchmarks prove it meets targets at lower cost |
| Log analytics scanning large sequential datasets | Throughput, block size, scan duration | **st1** | gp3 when random I/O or low latency is needed |
| Cold dataset still requiring a block volume | Read frequency, mount requirements, access speed | **sc1** | **S3** if data can move from block to object |
| App needing NFS shared files across multiple AZs | File semantics, client count, latency, throughput | **EFS/FSx**, do not force onto standard EBS | EBS only if data is truly per-instance private block data |
| Stateful containers | Scheduler AZ binding, access modes, downtime | EBS CSI driver + **gp3** when data can be AZ-pinned | EFS/FSx or managed DB if multi-AZ/sharing is required |
| Regenerable scratch/cache | Speed and data loss tolerance | **Instance store** if instance type supports it | gp3 if data must persist beyond host lifecycle |
| User images/videos/files | API access, broad sharing, lifecycle | **S3** | EBS only when software strictly mandates a local filesystem |

**Tip:** For workloads without clear disk specs, start with **gp3**, establish a baseline, measure, and tune. Upgrade to a higher tier only once you have concrete evidence of bottlenecks, latency issues, or specific durability requirements.

## 6. Six-Step Process for Choosing an EBS Volume

### Step 1 — Characterize the Data and Constraints

Gather:

- **Current capacity** (GiB/TiB), daily/monthly growth, actual utilization ratio, expansion needs.
- **I/O pattern:** random vs. sequential, read/write ratio, typical I/O size, concurrent requests.
- **SLOs:** p95/p99 read/write latency, batch completion windows, minimum peak throughput.
- **Durability and recovery:** RTO, RPO, multi-AZ or multi-Region needs; impact if a volume is lost or corrupted.
- **Portability:** is data regenerable, must it move across instances/AZs/Regions, is it a boot disk?
- **Security:** encryption, KMS, IAM, log retention, backup regulations, and retention periods.

### Step 2 — Determine Whether You Need Boot, Block, or Shared File

If the OS boots from the drive, **st1/sc1 are unsuitable**. If multiple workloads must share a filesystem, evaluate EFS/FSx and data consistency before considering EBS Multi-Attach.

### Step 3 — Separate Limits by IOPS, Throughput, or Latency

For example, a workload averaging 4,000 IOPS with 16 KiB per request equates to roughly **62.5 MiB/s** if all I/O follows that pattern. `gp3` at 4,000 IOPS and 125 MiB/s may work on paper, but you must test latency and bursts under real load.

For a batch job needing **500 MiB/s** sequential streaming, gp3's 3,000 IOPS may not be the main factor; examine provisioned throughput, I/O size, and the EC2 instance's ability to drive sufficient bandwidth.

### Step 4 — Verify EC2 Performance Ceilings and AZ Alignment

- Does the EC2 instance support the desired volume type and provisioned rates?
- Does the instance's total **EBS bandwidth and IOPS cap** accommodate the **sum of all attached volumes**?
- Are the EC2 instance and EBS volume in the **same AZ**?
- Are account/Region quotas sufficient? Are there per-instance volume attachment limits?
- If EBS Multi-Attach is needed, is the instance a supported Nitro type and does the application coordinate concurrent writes?

Buying an io2 volume with 100,000 IOPS and attaching it to an instance with a lower cap is wasteful. Review **both the instance type and storage together**.

### Step 5 — Compare Total Cost

Total cost is not just **GiB × price/GiB-month**. Include provisioned IOPS and throughput (if applicable), snapshots/copies/restores, data transfer, KMS requests, monitoring, and operational effort. Model against the actual Region and scenario.

### Step 6 — Benchmark, Operate, and Review

Test with real workloads or benchmarks matching actual I/O size, queue depth, and duration. Monitor **IOPS, throughput, latency, queue length, saturation, CPU, and I/O wait**. Set alarm thresholds, document decisions, and revisit as workloads evolve.

~~~mermaid
flowchart TD
  A[Read data requirements and SLOs] --> B{Need multi-AZ shared filesystem?}
  B -->|Yes| C[Evaluate EFS/FSx]
  B -->|No| D{Random I/O, low latency?}
  D -->|Yes| E[Evaluate gp3]
  E --> F{Measured: gp3 misses sustained IOPS/latency?}
  F -->|Yes| G[Evaluate io2 Block Express]
  F -->|No| H[Keep gp3, tune IOPS/throughput per measurements]
  D -->|No, mostly sequential| I{Frequent or infrequent access?}
  I -->|Frequent| J[Evaluate st1 or gp3]
  I -->|Infrequent| K[Evaluate sc1 or S3]
  G --> L[Verify EC2/AZ, cost, restore, and benchmark]
  H --> L
  J --> L
  K --> L
~~~

## 7. Volume Sizing Scenarios with Numbers

### Example A — CRUD API with PostgreSQL Database on EC2

**Assumptions:**

- Current data 180 GiB, projected 300 GiB in year one.
- Peak 5,000 IOPS, average I/O size 16 KiB.
- Desired minimum throughput 200 MiB/s; p95 latency to be benchmarked.
- Critical transactional data requiring backups and recovery procedures.

**Estimate:** `5,000 × 16 / 1,024 ≈ 78.1 MiB/s` at the assumed I/O size; 200 MiB/s throughput leaves headroom for reads/writes or larger I/Os, though **it does not guarantee latency**. Start with **gp3 300 GiB, 6,000 IOPS, 250 MiB/s** on an EC2 instance with adequate EBS bandwidth. Above the gp3 baseline, extra provisioned IOPS/throughput incurs fees.

**There is not enough evidence to pick io2** solely because the workload is a database. Measure at peak; if gp3 fails tail latency or sustained IOPS despite an adequate instance, compare against io2 Block Express.

**Recovery:** Take DB-consistent backups/snapshots (or native DB mechanisms), monitor growth, and test restores. If surviving an AZ outage is required and snapshot restore time exceeds RTO, the architecture needs **DB replication/failover** rather than relying on a single volume.

### Example B — Batch Analytics on 2 TiB of Log Data

**Assumptions:** one EC2 instance runs batch jobs scanning large files continuously for several hours daily; mostly sequential reads, minimal random I/O, not a boot volume.

**Recommendation:** Evaluate **st1** for sequential throughput and cost efficiency. Calculate sustained throughput, schedule, and throughput credits; if long scans deplete credits, job completion may slow down. Compare gp3 if the job needs steady throughput, small random metadata I/O, or peak headroom.

**Note:** If logs can be stored in S3 and processed with Athena, Glue, EMR, or another architecture, re-evaluate whether a persistent block volume is needed at all times.

### Example C — Legacy Windows EC2 with Infrequently Read Drive

**Assumptions:** C: drive needs reliable booting; D: drive holds monthly exported reports read sequentially; data must persist across EC2 stops.

**Recommendation:** C: **gp3** since it is a boot volume. D: **sc1** can be tested if the application tolerates its latency/throughput and meets minimum size; however, S3 may make more sense if files do not need a block device. Set separate snapshot/lifecycle schedules aligned with data goals.

### Example D — Financial Service Requiring High Random I/O and Low Latency

**Assumptions:** operations team tested gp3 and missed tail latency targets; workload requires sustained IOPS and high concurrency on a capable Nitro EC2 instance.

**Recommendation:** Evaluate **io2 Block Express** sized with the right IOPS ratio, and benchmark p95/p99 latency and throughput. Review HA/DR plans and budget; one fast volume alone does not guarantee overall system availability.

## 8. Creating, Attaching, and Mounting a Volume in a Lab

> **Lab Prerequisites:** Use an authorized lab EC2 instance and account; the IDs below are illustrative. Replace all example values with real IDs before running. The `mkfs` command **erases existing data structures on the device**: only run it after confirming a newly created blank volume. For production, follow change review, snapshot/backup, and rollback procedures.

### 8.1. Check the EC2 Instance's Availability Zone

~~~bash
aws ec2 describe-instances \
  --instance-ids i-0123456789abcdef0 \
  --query 'Reservations[].Instances[].{Id:InstanceId,AZ:Placement.AvailabilityZone,State:State.Name}' \
  --region ap-southeast-1 \
  --profile lab
~~~

Assume the EC2 instance is in `ap-southeast-1a`. The name `1a` is an account-specific label; to compare AZs across accounts, use the **AZ ID** rather than just the display name.

### 8.2. Create a 100 GiB gp3 Volume in the Same AZ

~~~bash
aws ec2 create-volume \
  --availability-zone ap-southeast-1a \
  --size 100 \
  --volume-type gp3 \
  --iops 3000 \
  --throughput 125 \
  --encrypted \
  --tag-specifications 'ResourceType=volume,Tags=[{Key=Name,Value=lab-data-gp3},{Key=Environment,Value=lab}]' \
  --region ap-southeast-1 \
  --profile lab
~~~

The command returns a `VolumeId` (`vol-...`) and initial state. By default, `--encrypted` uses the account/Region EBS encryption key configuration; if a **customer managed KMS key** is required, specify the key and grant matching KMS permissions. Never embed access keys/secrets in scripts.

Check status:

~~~bash
aws ec2 describe-volumes \
  --volume-ids vol-0123456789abcdef0 \
  --query 'Volumes[0].{Id:VolumeId,State:State,AZ:AvailabilityZone,Type:VolumeType,Size:Size,Iops:Iops,Throughput:Throughput,Encrypted:Encrypted}' \
  --region ap-southeast-1 \
  --profile lab
~~~

### 8.3. Attach EBS to EC2

Once the volume is `available`:

~~~bash
aws ec2 attach-volume \
  --volume-id vol-0123456789abcdef0 \
  --instance-id i-0123456789abcdef0 \
  --device /dev/sdf \
  --region ap-southeast-1 \
  --profile lab
~~~

The OS may expose the device under a **different name** than `/dev/sdf`, especially on **EC2 Nitro/NVMe**. Inspect inside the instance:

~~~bash
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS,MODEL
sudo blkid
~~~

If multiple volumes share the same size, match **volume ID ↔ NVMe device** using the appropriate AWS/NVMe utility or device metadata. **Do not rely solely on `/dev/nvme1n1`**, as enumeration order can change across reboots/attachments.

### 8.4. Initial Format and Mount (Blank New Volumes Only)

The example below assumes you have **positively verified** the new volume's device is `/dev/nvme1n1` and it **contains no filesystem or data to preserve**:

~~~bash
# Final check before destructive operation
sudo file -s /dev/nvme1n1
lsblk -f /dev/nvme1n1

# ONLY on a newly created blank volume without a filesystem:
sudo mkfs.ext4 /dev/nvme1n1

sudo mkdir -p /data
sudo mount /dev/nvme1n1 /data
df -h /data
~~~

To persist mounts across reboots, retrieve the **filesystem UUID**:

~~~bash
sudo blkid /dev/nvme1n1
~~~

Using the real UUID, add a line like this to `/etc/fstab` following OS administration procedures:

~~~text
UUID=<actual-filesystem-uuid> /data ext4 defaults,nofail 0 2
~~~

Then validate syntax/mounting and rollback on the lab instance. `nofail` makes booting more resilient if a secondary drive is missing, but the application must handle an unavailable mount to avoid accidentally writing data onto the root drive.

**Windows:** You can similarly attach EBS via the AWS API, then use **Disk Management** or Windows tools to bring the disk online, initialize/format only if truly blank, and assign a drive letter. For disks with existing data, never re-initialize or reformat.

### 8.5. Safe Operations

- Separate **OS volumes** from **data volumes** when backups, resizing, and data access permissions require independent management.
- Never store sole copies of important data on one volume without snapshots/replication aligned with RPO.
- Before detaching an actively written volume, flush buffers and **unmount/quiesce applications**, especially databases.
- When replacing EC2 instances, always check AZ alignment and `DeleteOnTermination` settings for every mapping.

## 9. Resizing and Migrating gp2 to gp3 with Elastic Volumes

EBS provides **Elastic Volumes** to modify capacity, volume type, IOPS, and throughput within supported types and environments. On modern instances, many modifications occur while the volume remains attached and the application runs; however, **this does not mean every change has zero performance impact or can be immediately rolled back**.

### 9.1. Example: Expanding from 100 GiB to 200 GiB and Adjusting Performance

~~~bash
aws ec2 modify-volume \
  --volume-id vol-0123456789abcdef0 \
  --volume-type gp3 \
  --size 200 \
  --iops 6000 \
  --throughput 250 \
  --region ap-southeast-1 \
  --profile lab
~~~

Check progress:

~~~bash
aws ec2 describe-volumes-modifications \
  --volume-ids vol-0123456789abcdef0 \
  --region ap-southeast-1 \
  --profile lab
~~~

States include `modifying`, `optimizing`, and `completed`; monitor actual state and error messages. **Do not issue repeated back-to-back modifications**: AWS enforces a modification cooldown and requires each modification to finish before starting another. Changes may take minutes or hours depending on size and conditions.

### 9.2. Expanding EBS Does Not Automatically Expand the Filesystem

After AWS increases the block volume, the OS still needs to:

1. Detect the **new disk size**.
2. If the filesystem sits on a **partition**, expand that partition.
3. **Extend the filesystem** to use the additional space.

Example (after verifying the exact device):

~~~bash
lsblk
df -hT /data

# Only when an ext4 filesystem sits directly on the whole block device:
sudo resize2fs /dev/nvme1n1
~~~

If ext4 sits on a partition, expand the partition first using a tool like `growpart`, then resize the filesystem on the **partition device**, not the raw disk. For **XFS**, use `xfs_growfs` on the mounted **mount point** (such as `/data`) per OS documentation. On Windows, use Disk Management/PowerShell to Extend Volume under supported conditions.

**Always inspect filesystem type, layout (LVM/RAID/partition), block size, and mount point** before running any resize command. Systems with encrypted partitions, LVM, or RAID have additional layers that must be resized in the right order.

### 9.3. Why Can't You Shrink a Volume Directly?

Elastic Volumes supports **increasing**, but **cannot directly shrink an EBS volume's size**. To cut costs on an oversized volume:

1. Back up and verify recoverability.
2. Create a **smaller** volume large enough for the data and of the right type.
3. Create the filesystem properly on the new volume.
4. Use file/application-aware tools such as `rsync`, database backup/restore, or Windows `robocopy`.
5. Verify data integrity, downtime, permissions, and cut the application over to the new volume.
6. Delete the old volume only after confirming stability and a rollback path.

**A snapshot from a larger volume cannot be used directly to create a smaller volume** simply by specifying a smaller size.

### 9.4. What to Watch When Migrating gp2 to gp3

Suppose an existing gp2 volume is 500 GiB and delivers higher effective performance than the gp3 baseline on certain metrics. If you modify it to gp3 **without specifying IOPS/throughput**, AWS has behavior that preserves at least certain gp2-equivalent or gp3-baseline metrics; therefore, **do not assume a migration automatically bills only at the base gp3 storage rate**.

Proper procedure:

- Measure actual IOPS/throughput during peaks, sustained periods, and bursts.
- Choose gp3 with **explicitly declared IOPS/throughput** matching your SLO.
- Estimate storage cost plus any paid performance tier above baseline.
- Verify type/size/IOPS/throughput before and after, and monitor latency and errors.
- Keep snapshots/rollback plans ready; volume modification is not a simple "undo" action.

## 10. EBS Encryption, IAM, and KMS Keys

Amazon EBS supports **encryption at rest** and in-transit encryption where supported. EBS encryption relies on **AWS KMS** and can be enforced automatically if **EBS encryption by default** is enabled for the Region/account.

**Distinguish these layers:**

- **IAM permissions:** who can run `ec2:CreateVolume`, `ec2:AttachVolume`, `ec2:ModifyVolume`, `ec2:CreateSnapshot`, delete resources, or access copies?
- **KMS key policies and grants:** do the role/identity/service have permission to use the key to encrypt/decrypt during required operations? Customer managed keys and cross-account sharing require explicit key permission management.
- **OS/application:** EBS encryption protects data at the storage layer; applications still need TLS, secret management, and internal authentication. It does not stop users who have OS-level instance access from reading mounted files.
- **Backup encryption:** snapshots inherit/manage encryption per configuration; copying snapshots may involve different keys, KMS permissions, and charges.

**You cannot enable encryption in place with a simple toggle on an existing unencrypted EBS volume.** The standard approach is to take a snapshot, create an encrypted copy, restore an encrypted volume, and perform a controlled workload cutover. The exact plan depends on root/data volume status, downtime tolerance, and KMS keys.

Prefer **encryption by default**, temporary IAM roles for workloads, no static credentials on filesystems, and auditing volume/snapshot/KMS changes via CloudTrail.

## 11. Snapshots, Backups, and Recovery Planning

**EBS snapshots** capture a volume's block data at a point in time using an **incremental** mechanism after the first snapshot. AWS manages snapshot data on internal S3 infrastructure; snapshots are not S3 objects users can read via the S3 API.

### 11.1. What Are Snapshots Used For?

- Recovering after accidental file deletion, misconfiguration, or volume loss if an appropriate restore point exists.
- Creating a new volume from a snapshot in another AZ within the **same Region**.
- Copying snapshots to **another Region** to support disaster recovery.
- Creating AMIs, cloning test environments, or migrating data with proper procedures.

**AWS does not automatically back up EBS data according to your desired policy.** You must schedule snapshots with **Amazon Data Lifecycle Manager** or **AWS Backup** according to governance and recovery requirements.

### 11.2. Point-in-Time Does Not Automatically Guarantee Application Consistency

If a database is actively writing, a block volume snapshot may be **crash-consistent** rather than **application-consistent** without software coordination. For reliable transactional database recovery:

- Use native DB backup tools or quiesce/freeze I/O per documentation.
- For data spanning multiple volumes, consider multi-volume consistent snapshots or workload-supported backup solutions.
- Design transaction logs, point-in-time recovery, and DB-native replication strategies.
- **Test restores** in an isolated environment, verify integrity, and start the application—never rely solely on a `completed` status.

### 11.3. Snapshots Do Not Replace High Availability

| Objective | Suitable tool/design | What to evaluate |
| --- | --- | --- |
| Recover deleted files / corrupted data | Snapshots, AWS Backup, app backups | Backup frequency, restore testing, permissions, retention |
| Recover volume in another AZ | Snapshot → create volume in target AZ | Volume creation/initialization time, app restart |
| Application survives a single AZ outage | Multi-AZ replica/DB or failover architecture | Data consistency, failover time, health checks |
| Recover from full Region loss | Cross-Region snapshot copy or DR replication | RPO/RTO, IAM/KMS, DNS, routing, dependent data |
| Workload requiring near-zero RPO | Synchronous replication / suitable DB architecture | Periodic snapshots are usually insufficient |

**RTO (Recovery Time Objective)** = maximum tolerable application downtime; **RPO (Recovery Point Objective)** = maximum tolerable data loss measured in time. For example, snapshots every 24 hours cannot prove a 15-minute RPO.

### 11.4. Restore and First-Read Penalty

Volumes created from snapshots may require **data initialization** when blocks are accessed for the first time, causing higher initial latency. For workloads needing fast, predictable recovery, evaluate:

- Proactively initializing/warming up the volume per procedures, avoiding benchmarks on unhydrated data.
- **Fast Snapshot Restore (FSR)** for specific needs, checking enabled AZs and cost.
- Depending on current service capabilities, specifying a **provisioned volume initialization rate** for new volumes from snapshots where supported.
- Measuring real end-to-end time from "snapshot ready" to "application meeting SLO," rather than just volume-create API speed.

## 12. Multi-Attach Does Not Turn EBS into a Normal Shared Filesystem

EBS **Multi-Attach** allows **certain Provisioned IOPS SSD volumes** (`io1`, `io2`) to attach simultaneously to multiple Nitro-based EC2 instances **within the same AZ**, up to the supported instance limit (currently documented as **16**). This is a specialized capability for workloads that coordinate writes at the application/cluster level.

**Major risk:** Multiple machines mounting a standard filesystem such as ext4/XFS and writing concurrently **without a cluster filesystem/locking mechanism** can corrupt data. Multi-Attach requires applications that understand concurrency, write ordering, and proper **I/O fencing**.

Key points to remember:

- Multi-Attach does **not** work on gp2/gp3 or st1/sc1.
- Instances must be in the **same AZ**, offering no automatic protection against AZ outages.
- Multi-Attach is not supported for boot volumes.
- If shared files across multiple AZs are needed, evaluate **EFS/FSx** first.
- Multi-Attach projects require storage cluster design, fencing, quorum, and failure testing—not just toggling a console checkbox.

## 13. CloudWatch: Measure Bottlenecks Instead of Guessing

Amazon CloudWatch provides EBS metrics to monitor I/O and performance. View them in **EC2 Console → Elastic Block Store → Volumes → select volume → Monitoring**, or in CloudWatch by resource ID.

| Metric | Suggested use | How to interpret |
| --- | --- | --- |
| **VolumeReadOps / VolumeWriteOps** | Total read/write operations | Divide `Sum` by period seconds for observed IOPS |
| **VolumeReadBytes / VolumeWriteBytes** | Total bytes read/written | Divide `Sum` by time and convert to MiB/s |
| **VolumeQueueLength** | Number of pending or queued I/O requests | Sustained growth can indicate saturation or load exceeding capacity |
| **VolumeTotalReadTime / VolumeTotalWriteTime** | Total I/O processing time per supported metric | Combine with operation counts to estimate latency where applicable |
| **BurstBalance** | Remaining credit balance for applicable volume types | Useful for gp2/st1/sc1 credit tracking; gp3 does not use burst credits |
| **VolumeIdleTime** | Time the volume spent idle | Helps distinguish low load from true contention |
| **VolumeStalledIOCheck / VolumeIOPSExceededCheck / VolumeThroughputExceededCheck** | Operational health or limit-exceeded checks on supported platforms | Not available on all volume/instance types; verify before creating alarms |

**Throughput calculation example:** Over 60 seconds, `Sum(VolumeReadBytes)=6,291,456,000` bytes. Average throughput `≈100 MiB/s`. If a gp3 volume is at its 125 MiB/s baseline and the app consistently needs more, consider raising provisioned throughput—**after** confirming the instance has remaining headroom.

### Inspecting at the OS Level

On Linux, you can use:

~~~bash
lsblk
df -hT
iostat -xz 1
# If sysstat is installed:
# monitor await, util, r/s, w/s, rkB/s, wkB/s
~~~

**Note:** `iostat` measures at the OS layer, while CloudWatch measures at the EBS layer; figures can differ due to caching, request merging, and sampling intervals. Do not assume `%util=100` always means the volume has hit every limit in all environments.

For databases, also measure engine-level I/O read/write/wait times and application p95/p99 latency. Increase IOPS only when storage is confirmed as the bottleneck rather than CPU, lock contention, memory, network, or query plans.

## 14. Calculating EBS Costs Properly

Cost components to estimate:

1. **Provisioned storage:** volume capacity in GiB/TiB by type and duration; unattached `available` volumes continue accruing charges.
2. **Provisioned IOPS/throughput:** especially for gp3 above baseline or io1/io2, depending on unit rates and thresholds.
3. **Snapshots:** stored snapshot data by tier/cycle, cross-Region/account copies, and archive/retrieval if used.
4. **Fast Snapshot Restore / provisioned initialization:** if using paid acceleration features.
5. **Supporting infrastructure:** EC2 EBS-optimized throughput, bandwidth, instance cost, backup/monitoring operations, CloudWatch logs/metrics, and associated data transfer.

**Structural formula for gp3**, excluding taxes/discounts and auxiliary components:

\[
C_{\text{gp3}} \approx
S_{\text{GiB}} P_{\text{GiB-month}} +
\max(0, I-3000)P_{\text{IOPS-month}} +
\max(0, T-125)P_{\text{MiB/s-month}}
\]

Where `S` is provisioned capacity, `I` is provisioned IOPS, and `T` is provisioned throughput. Unit **prices P** vary by Region and time; never hardcode one USD figure across all environments.

### Comparison Example Without Hardcoded Prices

Suppose you need **200 GiB, 3,000 IOPS, 125 MiB/s**:

- With **gp3**, these IOPS/throughput levels fall within the baseline, so the EBS volume charge is primarily provisioned capacity.
- With **gp2**, 200 GiB provides roughly 600 baseline IOPS; 3,000 IOPS is only achievable temporarily via burst credits when conditions allow. A steady-state workload would require significantly over-provisioning gp2 capacity just for baseline IOPS, wasting money.
- With **io2**, 3,000 IOPS is achievable, but its cost and headroom may be unnecessary for this workload.
- If the data is purely long-term object storage, consider S3 instead of paying continuously for provisioned volumes.

**Cost optimization actions:** identify idle or unattached volumes still incurring charges, old snapshots lacking retention policies, gp2 volumes eligible for gp3 migration, gp3 volumes with over-provisioned unused IOPS/throughput, and cold data suited for object storage. Before deleting any volume or snapshot, verify ownership, dependencies, and recovery requirements.

Use the **AWS Pricing Calculator**, **AWS Cost Explorer**, **AWS Budgets**, and tags such as `application`, `environment`, and `owner` to track spend.

## 15. Troubleshooting by Symptom

| Symptom | Possible cause | What to check first |
| --- | --- | --- |
| Attach fails due to AZ | EC2 and volume are in different Availability Zones | Check `describe-instances`, `describe-volumes`, compare actual AZs |
| OS does not see device as `/dev/sdf` | Nitro NVMe device renaming | `lsblk`, match NVMe serial/volume ID |
| Mount reports wrong filesystem or no superblock | Unformatted volume, wrong device, corrupted FS, snapshot from another OS | `file -s`, `blkid`, kernel logs; never format before verifying data |
| Volume shows 200 GiB but filesystem still 100 GiB | Partition/filesystem not extended | `lsblk`, `df -hT`, LVM/partition layout, appropriate growpart/resize |
| Lower IOPS than provisioned | EC2 EBS bandwidth/IOPS cap, queue depth, I/O size, initialization, app bottleneck | EC2/EBS metrics, proper benchmark, `iostat`, latency |
| gp2/throughput HDD slows down over time | Burst credits depleted or unsuitable workload | `BurstBalance`, measure sustained I/O, evaluate gp3/st1/io2 |
| First reads on snapshot-restored volume are slow | Not yet fully initialized | Appropriate warm-up/FSR/provisioned initialization |
| App reports I/O errors | OS device error, volume state, storage-layer connectivity, filesystem, or kernel | CloudWatch, system logs, EC2 status, support/runbooks |
| Snapshot completed but DB restore fails | Snapshot not application-consistent or missing related volumes/logs | DB-aware backups, quiesce, restore testing |
| Cannot switch to st1/sc1 as root | st1/sc1 cannot be boot volumes | Keep root on gp3/SSD, use HDD for suitable data volumes |
| Unexpected cost spike after editing gp3 | Provisioned IOPS/throughput exceeds baseline | Check `describe-volumes`, Cost Explorer, and Regional pricing |
| Cannot attach simultaneously to multiple EC2s | Non-Multi-Attach type, different AZs, ineligible instance | Check io1/io2, Nitro, AZs, cluster/filesystem setup |
| KMS AccessDenied | Role/key policy/grant disallows operations on encrypted volume/snapshot | IAM policies, key policies, grants, account/Region, and CloudTrail |

### Suggested Investigation Sequence

~~~text
1. Verify EC2, volume ID, AZ, volume type, size, IOPS, throughput, encryption.
2. Verify attach state and block device inside the OS (matching exact volume ID).
3. Verify partition/filesystem/mount point; do not rush to format or fsck while the app is writing.
4. Measure actual I/O: IOPS, MiB/s, latency, queue, CPU, and EC2 EBS cap.
5. Cross-check volume type, random/sequential load, burst credits, snapshot initialization.
6. Inspect application logs, KMS/IAM, and other compute/network components.
7. Propose the smallest safe change, back up, re-test under equivalent load, monitor.
8. Record evidence and test restore if any change impacts data.
~~~

## 16. Designing Architecture with EBS Across Regions/AZs, IAM, and VPC

A reference architecture for an EC2-hosted application with transactional data on a managed database:

~~~mermaid
flowchart TB
    U[User] --> LB[Application Load Balancer]
    LB --> A[EC2 app AZ A]
    LB --> B[EC2 app AZ B]
    A --- VA[(EBS gp3 data/cache AZ A)]
    B --- VB[(EBS gp3 data/cache AZ B)]
    A --> DB[(RDS Multi-AZ)]
    B --> DB
    VA --> SA[EBS snapshot]
    VB --> SB[EBS snapshot]
    SA --> BK[AWS Backup / lifecycle]
    SB --> BK
    A --> CW[CloudWatch + CloudTrail]
    B --> CW
    DB --> CW
~~~

In this diagram:

- **Each EC2 instance's EBS** holds local per-AZ data; do not treat `VA` and `VB` as a synchronously shared filesystem.
- **Core business data** uses RDS Multi-AZ for relational and HA needs; if the application must self-host a database on EC2, design dedicated DB replication/failover.
- **IAM roles** for EC2/AWS Backup perform API calls with least privilege; **KMS** protects encrypted EBS data.
- **VPC, subnets, and SGs** control application and database traffic paths; attaching EBS does not replace network access controls.
- **Snapshots/lifecycle** address recovery and retention, while **CloudWatch** surfaces bottlenecks and CloudTrail supports change auditing.
- **Region/AZ** affects attachment placement, AZ recovery strategy, snapshot copying, and pricing.

### How Do EC2, ECS, EKS, and Lambda Differ When Using EBS?

- **EC2:** attaches EBS directly as root/data volumes.
- **ECS on EC2:** persistent data attached to EC2 hosts and used by containers requires lifecycle, placement, mount, and permission design; containers do not get individual EBS volumes by default.
- **ECS with supported managed EBS features:** can provision EBS per task within current service capabilities; verify task limits, AZ alignment, and lifecycle.
- **EKS:** uses the **Amazon EBS CSI driver** and PersistentVolume/PersistentVolumeClaim for persistent block storage; scheduler, AZ, and access modes must align with the volume.
- **Lambda:** does not attach an EBS volume like a regular EC2 disk. If a shared filesystem is needed, evaluate Lambda's **EFS** integration; temporary storage uses `/tmp` within its own limits/settings.

Common rule: **Do not force a compute service into an unsupported storage model.** Check resource limits, AZ scope, shareability, autoscaling, and recovery needs before choosing.

## 17. Checklist for Selecting and Operating EBS

- [ ] Confirmed the workload truly needs a **block device**; compared EBS against EFS, S3, FSx, or instance store.
- [ ] Documented current capacity, growth, read/write mix, I/O size, IOPS, MiB/s, latency, and queue depth.
- [ ] Selected volume type with clear rationale: gp3 for general needs; io2 for sustained IOPS/low latency; st1/sc1 for fitting sequential HDD workloads.
- [ ] Avoided st1/sc1 for boot volumes and avoided treating EBS Multi-Attach as an NFS shared filesystem.
- [ ] Verified EC2, volume, and Multi-AZ deployment compatibility; checked instance EBS bandwidth/IOPS caps.
- [ ] Sized IOPS and throughput accounting for volume size rules, instance/Region limits, and above-baseline costs.
- [ ] Applied least-privilege IAM permissions, required encryption/KMS, and CloudTrail auditing.
- [ ] Verified `DeleteOnTermination` settings and safe detach/terminate procedures.
- [ ] Implemented backups/snapshots aligned with RPO; tested restores and verified DB/application consistency.
- [ ] Designed cross-AZ/cross-Region application recovery aligned with RTO; did not treat snapshots as automatic failover.
- [ ] Configured metrics/logs/alerts for throughput, IOPS, latency, queue length, volume state, and application errors.
- [ ] Planned volume/filesystem expansion matching the OS/LVM/partition layout and noted volumes cannot shrink in place.
- [ ] Estimated costs for volumes, IOPS/throughput, snapshots/FSR, and monitoring; tagged owner/environment.
- [ ] Tested changes in a lab before modifying production storage.

## 18. Applied Exercises

### Exercise 1 — Choosing Disks for Three Applications

Select the EBS type and justify your choice for three scenarios:

1. An EC2 web server with a 40 GiB root disk, 500–1,500 IOPS, normal latency.
2. An EC2 instance processing 5 TiB of logs, scanning sequentially for hours daily, minimal random I/O, non-boot volume.
3. A transactional database measured at 70,000 IOPS on a matching workload, very strict tail latency, Nitro EC2 with sufficient EBS bandwidth.

**Hints:** (1) gp3; (2) evaluate st1 considering sustained throughput and credit balance, compared against gp3/S3; (3) evaluate io2 Block Express and compare benchmarks/cost against appropriately provisioned gp3. Avoid final conclusions without real measurements and cost targets.

### Exercise 2 — Why Does Increasing Size Not Increase Usable Space?

A `gp3` volume was increased from 100 to 200 GiB in the EC2 console, yet `df -h` still shows 100 GiB. Complete the following:

1. Explain the difference between block volume, partition, and filesystem.
2. Inspect using `lsblk`, `df -hT`, and `blkid`.
3. Propose steps to expand the partition and then filesystem cleanly for ext4 or XFS, accounting for whether LVM is present.
4. Describe how to back up and avoid operating on the wrong root/data device.

### Exercise 3 — Performance Math and Cost Control

A workload requires 10,000 IOPS with an average I/O size of 32 KiB. Calculate theoretical throughput:

\[
10{,}000 \times 32 / 1{,}024 = 312.5\ \text{MiB/s}
\]

Discuss:

- Is gp3 within technical limits? How much IOPS and throughput should be provisioned for margin?
- What is the minimum volume size required to provision 10,000 IOPS on gp3 at 500 IOPS/GiB? (**20 GiB**, though actual capacity must still match data and growth.)
- If the EC2 instance only has 250 MiB/s of EBS bandwidth, why won't raising gp3 from 250 to 500 MiB/s necessarily speed things up?
- If the workload shifts to 4 KiB random I/O with very strict p99 latency, should the selection change?

### Exercise 4 — Recovering After Losing an AZ

An application stores data solely on one EBS volume in AZ A. Snapshots run every 12 hours. The business requires **RTO 30 minutes, RPO 10 minutes**.

Explain why the current design cannot meet these two targets, then propose:

- A suitable replication mechanism or Multi-AZ database architecture instead of 12-hour snapshots alone.
- A recovery plan to restore a new volume from snapshot into AZ B when needed.
- Testing restoration time, data consistency, and DNS/routing/load balancer cutover.
- IAM/KMS permissions, monitoring, and ongoing cost estimates.

## 19. Summary

**EBS is block storage attached to EC2 within a single AZ.** Volume selection hinges on **I/O pattern**, **IOPS**, **throughput**, **latency**, **capacity**, **EC2 instance limits**, and **recovery/cost objectives**.

For most applications, `gp3` is a sound starting point thanks to its included baseline and decoupled performance configuration. `io2 Block Express` serves workloads demanding low latency and very high sustained IOPS. `st1/sc1` fit sequential workloads when HDDs genuinely meet demand. `gp2/io1/standard` must be understood to operate, optimize, or migrate legacy systems.

Choosing the right EBS volume is only one piece of a secure, reliable AWS architecture. Combine it with **IAM/KMS, VPC, Region/AZ planning, snapshots/restore testing, CloudWatch, and AWS Budgets**. Measure real workloads, calculate total costs, test recovery, and document selection rationale before moving to production.

### Official AWS Documentation for Reference

- [Amazon EBS volumes](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-volumes.html)
- [Amazon EBS volume types](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-volume-types.html)
- [General Purpose SSD volumes: gp3/gp2](https://docs.aws.amazon.com/ebs/latest/userguide/general-purpose.html)
- [Provisioned IOPS SSD / io2 Block Express](https://docs.aws.amazon.com/ebs/latest/userguide/provisioned-iops.html)
- [Modify an EBS volume using Elastic Volumes](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-modify-volume.html)
- [Extend the file system after resizing an EBS volume](https://docs.aws.amazon.com/ebs/latest/userguide/recognize-expanded-volume-linux.html)
- [Amazon EBS snapshots](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-snapshots.html)
- [EBS Multi-Attach](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-volumes-multi.html)
- [CloudWatch metrics for Amazon EBS](https://docs.aws.amazon.com/ebs/latest/userguide/using_cloudwatch_ebs.html)
- [Amazon EBS pricing](https://aws.amazon.com/ebs/pricing/)

Limits, pricing, APIs, and features vary by Region and instance type. When designing deployments, verify the latest AWS documentation against your actual account and Region.
