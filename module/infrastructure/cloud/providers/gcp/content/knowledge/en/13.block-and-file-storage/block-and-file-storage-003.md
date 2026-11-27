# Hyperdisk and IOPS, Throughput Configuration

When an application running on Compute Engine begins handling high transaction volumes or reading data at high speed, CPU and RAM are no longer the sole factors determining performance. A database can slow down because the disk cannot satisfy enough read/write operations per second; an analytics system can slow down because the disk bandwidth is insufficient, even when the I/O operation count is modest.

**Google Cloud Hyperdisk** is a family of high-performance block storage services for supported workloads and virtual machines on Compute Engine. Rather than only increasing disk capacity to gain performance, many Hyperdisk types let you configure **IOPS** and/or **throughput** according to demand, within the limits of the disk type, capacity, machine type, and deployment location.

In the **Block and File Storage** chapter of the `CLOUD_PROVIDERS_GCP` module, this lesson connects knowledge of Compute Engine, projects, IAM, VPCs, availability, and cost to disk selection, database operations, deployment automation, and performance observability. The content focuses on how to **design, configure, and evaluate Hyperdisk** through practical examples.

After this lesson, you will be able to:

1. Distinguish Hyperdisk from Persistent Disk, Filestore, and Cloud Storage by access model.
2. Explain the three metrics **IOPS**, **throughput**, and **latency**, along with their relationship to I/O size and concurrency.
3. Select the appropriate Hyperdisk type for OLTP, data analytics, HPC, or applications requiring cross-zone redundancy.
4. Configure and inspect `provisioned IOPS` / `provisioned throughput` values via Google Cloud Console and `gcloud`.
5. Measure actual performance, identify VM and workload limits, and tune configurations based on evidence.
6. Plan costs, data protection, snapshots/backups, and troubleshoot errors when creating, attaching, or modifying Hyperdisk.

## 1. Hyperdisk Is Block Storage, Not a Default Shared File System

A Hyperdisk volume appears to a supported VM as a **block storage device**. The operating system can detect the device, create partitions, format a filesystem, or hand it to a data management system such as a database. Applications interact through a filesystem or directly with the block device depending on the deployment.

~~~mermaid
flowchart LR
    APP["Application / database"] --> OS["OS + filesystem<br/>or direct block access"]
    OS --> VM["Compute Engine VM"]
    VM --> HD["Hyperdisk volume<br/>capacity + IOPS + throughput"]
    HD -. "Actual limits" .-> CAP["Machine type, size,<br/>I/O profile, quota"]
~~~

### 1.1. Choosing the Right Storage Model

| Google Cloud Option | Access model | Common needs | Questions before choosing |
| --- | --- | --- | --- |
| **Hyperdisk** | Block storage attached to supported VMs; some multi-attach modes depending on disk type | Databases, high-IOPS random workloads, high-bandwidth read/write data | Does the VM support the desired Hyperdisk type and performance level? |
| **Persistent Disk** | Block storage for Compute Engine | General-purpose boot/data disks where performance/cost fits | How does performance depend on disk type, size, and machine type? |
| **Filestore** | Managed file storage service accessed over NFS per supported configuration | Multiple clients sharing a filesystem and common directory paths | Are POSIX/file sharing and the NFS model required? |
| **Cloud Storage** | Object storage accessed via APIs and corresponding tools | File uploads, images, large datasets, backups, static assets | Does the app work with objects or require a block device/filesystem? |

An application where multiple VMs need to access **a directory over NFS** should consider Filestore. Do not treat multi-attach support on certain Hyperdisks as equivalent to a safe shared file system: the filesystem/application must handle synchronization, locking, and consistency accordingly.

### 1.2. Hyperdisk Types

Google Cloud offers the following families; **support across regions, zones, machine series, and configurations is subject to change**.

| Type | Optimization focus | User-provisionable metrics | Typical workloads |
| --- | --- | --- | --- |
| **Hyperdisk Balanced** | Balanced price, IOPS, and bandwidth across many applications | **IOPS and throughput** | General-purpose databases, enterprise apps, transactional services |
| **Hyperdisk Balanced High Availability** | Data replicated across two zones in the same region per product mechanism | **IOPS and throughput** | Critical apps requiring a zone-fault-tolerant storage layer |
| **Hyperdisk Extreme** | High IOPS, low latency by design and supported configuration | **IOPS**; throughput is derived from IOPS, not set independently | Large databases, SAP HANA, transactional systems requiring high IOPS |
| **Hyperdisk Throughput** | High sequential read/write bandwidth with moderate IOPS | **Throughput**; IOPS is derived from throughput | Large-volume data processing, analytics, and cost-sensitive jobs |
| **Hyperdisk ML** | Very high read bandwidth and shared read modes when supported | **Throughput**; IOPS is derived from throughput | Machine learning datasets, AI/HPC, and distributed read jobs |

**Not every type lets you tune both IOPS and throughput independently.** For instance, passing `--provisioned-iops` to Hyperdisk Throughput or Hyperdisk ML is invalid because their IOPS performance is derived from throughput. Conversely, Hyperdisk Extreme lets you set IOPS without setting throughput directly.

**Hyperdisk Balanced High Availability** replicates across two zones within a region; that does not mean your application or database is automatically deployed to the standby zone. You must combine it with VM architecture, application design, failover mechanisms, RTO/RPO targets, and live testing. Multi-writer/read-only attach modes also carry specific restrictions; never enable disk sharing just because the option is visible.

## 2. Three Quantities to Understand: IOPS, Throughput, and Latency

### 2.1. IOPS Is the Number of I/O Operations per Second

**IOPS (Input/Output Operations Per Second)** measures how many read or write operations the system completes in one second. Transactional workloads often execute many small, random accesses; in those cases, IOPS is a critical metric.

For example, a database performing 8,000 small page reads and 4,000 writes per second generates about **12,000 IOPS** total. IOPS does not indicate how many bytes each operation transfers; 12,000 IOPS with 4 KiB blocks versus 256 KiB blocks produces vastly different data volumes.

### 2.2. Throughput Is the Volume of Data Transferred per Second

**Throughput** measures data read/written per unit of time, usually expressed in **MiB/s** in Google Cloud disk configurations. Meanwhile, documentation and applications sometimes use MB/s, GiB/s, or Gb/s. Always align units before comparing:

- 1 MiB = 1,048,576 bytes.
- 1 MB = 1,000,000 bytes.
- 1 GiB = 1,024 MiB.
- Mb/s means **megabits per second**, which differs from MB/s and MiB/s.

If you know the average I/O size, estimate:

\[
\text{Throughput (MiB/s)} \approx
\frac{\text{IOPS}\times\text{Average I/O size (bytes)}}{1,048,576}
\]

| Illustrative load pattern | IOPS | Average I/O | Approximate throughput |
| --- | ---: | ---: | ---: |
| Small transactional reads/writes | 12,000 | 4 KiB | 46.9 MiB/s |
| API saving medium-sized files | 8,000 | 16 KiB | 125 MiB/s |
| Batch data scanning | 1,000 | 256 KiB | 250 MiB/s |
| Large-block sequential reads | 2,000 | 1 MiB | 2,000 MiB/s |

These values illustrate the mathematical relationship only—**they are not benchmark results**. A real workload may combine varying I/O sizes, interleaved reads/writes, cache hits, and compute steps.

### 2.3. Latency Is the Time to Complete an Operation

**I/O latency** is the time from when a read/write request is submitted until completion at the corresponding measurement point. Even when average IOPS is high, a database can feel sluggish if a subset of requests suffers high p95/p99 latency.

During design and testing, record:

- **p50** to see typical latency;
- **p95/p99** to detect slow-operation tails;
- **read/write latency** separately, rather than a blended average;
- **queue depth / outstanding I/O** to verify whether the application issues enough concurrent requests;
- **CPU, RAM, filesystem, page cache, and transaction behavior** to separate disk bottlenecks from other bottlenecks.

An estimate from Little's Law in steady state:

\[
\text{Average concurrent I/Os}\approx
\text{IOPS}\times\text{Average latency (seconds)}
\]

For example, to reach 20,000 IOPS at an average latency of 2 ms, the workload needs roughly **40 concurrent in-flight I/Os**, assuming appropriate queuing and measurement. This is a way to check whether the load generates enough requests, not a promise that raising queue depth always makes the system faster. Overly deep queues can degrade p99 latency.

### 2.4. Four Common Scenarios

| Signal | Likely explanation | Investigation direction |
| --- | --- | --- |
| IOPS at threshold, MiB/s still low | Many small or random I/Os | Increase IOPS if appropriate; optimize queries and I/O count |
| Throughput at threshold, IOPS still low | Large I/Os or sequential scans | Inspect throughput, data read paths, and machine support |
| Both below provisioned levels, yet p99 is high | Queuing, CPU, filesystem, sync writes, or another limit | Measure queue depth, CPU, operation types, VM limits, and latency |
| High provisioned performance, low measured values | VM cap too low, insufficient load, caching, flawed test | Cross-check machine type, I/O size, and benchmark methodology |

**Rule:** do not simply raise IOPS when users report a slow application. First determine whether the workload is constrained by **operation count**, **data volume**, **response time**, or another component.

## 3. Understanding Provisioned Performance and Actual Limits

**Provisioned IOPS** and **provisioned throughput** are target performance levels configured for Hyperdisk—**not metrics measured from the application** and not guarantees that the workload will always hit those levels. A volume configured for 20,000 IOPS might only execute 800 IOPS if the application does not issue more requests; it can also fall short if the VM or I/O pattern cannot sustain it.

~~~mermaid
flowchart TD
    W["Workload: I/O size,<br/>random/sequential, concurrency"] --> OBS["Measured performance"]
    D["Hyperdisk: type, size,<br/>provisioned IOPS/throughput"] --> OBS
    VM["VM: machine series,<br/>vCPU, disk limits"] --> OBS
    G["Guest OS / filesystem,<br/>cache, CPU, scheduler"] --> OBS
    OBS --> ACT["Evaluate latency,<br/>IOPS, MiB/s, and cost"]
~~~

### 3.1. Limits to Check Before Setting Numbers

| Limit layer | Question to answer | Consequence if ignored |
| --- | --- | --- |
| **Hyperdisk type** | Does this type let you set IOPS, throughput, or only one of the two? | Disk creation/update rejected or wrong expectations configured. |
| **Volume capacity** | For the chosen size, what is the valid IOPS/throughput range? | Cannot provision levels higher than allowed for the size. |
| **IOPS–throughput relationship** | Does the pair satisfy the disk type's formula/constraints? | Invalid pair even when each number alone appears within maximum limits. |
| **Machine series and machine type** | Does the VM support the disk type, access mode, and target performance? | Disk may fail to attach or performance gets capped by VM limits. |
| **Aggregate VM limit** | Are multiple disks sharing the VM's total IOPS/throughput cap? | Combined disk performance falls short of the sum of individual provisions. |
| **Zone/region and quota** | Is the resource supported in the target location, and are quota/capacity sufficient? | Disk creation or attachment fails. |
| **Real load and OS** | What are the actual block size, queue depth, filesystem, cache, and CPU levels? | High provisioned performance goes unused or p99 worsens. |

**Example of disk-type limits:** current Hyperdisk Balanced documentation cites ceilings of **160,000 IOPS and 2,400 MiB/s per volume**, though valid provisioned values still depend on capacity and the relationship between the two metrics. Hyperdisk Extreme has different IOPS limits; Hyperdisk Throughput and ML follow throughput-based provisioning rules. These ceilings are not guaranteed actuals for every VM.

For machine types whose total IOPS or throughput capability exceeds a single Hyperdisk Balanced volume's ceiling, **multiple volumes** and a workload capable of distributing I/O may be required to saturate the VM. Conversely, attaching many volumes to a small VM cannot bypass the VM's aggregate cap.

### 3.2. How IOPS and Throughput Relate to I/O Pattern

In Hyperdisk performance documentation, maximum IOPS is typically evaluated at small I/O sizes such as **4 KiB**, while maximum throughput is evaluated at larger sizes such as **256 KiB** or higher, depending on type and scenario. A workload should not expect to hit both the IOPS ceiling and throughput ceiling simultaneously with a single I/O size.

A useful planning estimate:

\[
\text{Observed throughput} \lesssim
\min\left(
\text{disk throughput limit},
\ \text{actual IOPS}\times\text{average I/O size},
\ \text{VM limit}
\right)
\]

In this expression, the product IOPS × I/O size must be converted into the same units as throughput. This is a **bottleneck-checking model**, not a substitute for measurement: caching, overhead, read/write mix, concurrency, and latency also play a role.

**Reads + writes share performance limits** under Hyperdisk's half-duplex model. For example, a 20,000 IOPS limit does not mean you get 20,000 read IOPS **and** 20,000 write IOPS simultaneously. Sum read and write traffic according to the service's limit specifications.

### 3.3. Example: Choosing a Valid IOPS and Throughput Pair

Suppose an application needs **6,000 IOPS** and **300 MiB/s**, with around 70 GiB of data plus room to grow to 100 GiB. A **100 GiB Hyperdisk Balanced** volume provisioned with 6,000 IOPS and 300 MiB/s is an example configuration within the common supported range; you must still verify VM type and zone.

For Hyperdisk Balanced, the valid throughput range formula for a given IOPS level `P` in current documentation is:

- Minimum: `MAX(140, P / 256)` MiB/s;
- Maximum: `MIN(2400, P / 4)` MiB/s;
- Must also satisfy limits based on **capacity** and service support conditions.

With `P = 6000`, the formula yields a range from 140 to 1,500 MiB/s. **300 MiB/s** lies within that range, yet achieving 300 MiB/s with a workload consisting solely of 4 KiB I/Os would require far more than 6,000 IOPS. Thus **valid configuration** and **workload meeting expectations** are two distinct checks.

Do not apply this formula to Hyperdisk Extreme, ML, or Throughput; each type has its own mechanism and limits.

### 3.4. Baseline, Additional Provisioned Performance, and Cost

Some Hyperdisk types include **baseline performance** in their default configuration or follow specific pricing models. Provisioning above the included baseline increases cost. Baseline levels, billing rates per capacity/IOPS/throughput, regional pricing, and product updates must be checked against the official pricing table.

Think of the cost model as:

\[
\text{Storage cost} \approx
\text{billable capacity}
+ \text{billable provisioned performance}
+ \text{snapshots/backups and related services}
\]

Do not simply multiply "IOPS × hours" and treat it as the fee for every Hyperdisk type: billing units, free/included baselines, and billing rules vary. Use the **Google Cloud Pricing Calculator** or official pricing tables for your specific disk type, region, capacity, and provisioned levels.

**Economic decision:** if a workload regularly consumes only 2,000 IOPS yet is provisioned for 60,000 IOPS, you may be paying for rarely used capacity. Conversely, provisioning right at the average can cause bottlenecks during peak hours. Use p95/p99 metrics, peak traffic, and load tests to pick an appropriate level and monitor continuously.

## 4. Choosing a Hyperdisk Type by Workload Profile

### 4.1. Transactional Databases (OLTP)

An e-commerce application executes many small page reads/writes, index updates, and transaction log writes. The team needs to track **IOPS, latency, and log flush speed**, while monitoring slow queries.

A reasonable starting point is **Hyperdisk Balanced** because it lets you adjust both metrics. When a workload truly demands exceptionally high IOPS, evaluate **Hyperdisk Extreme** alongside a supported machine type. Buying a high-IOPS disk will not fix missing indexes, overly long transaction locks, or a saturated CPU.

### 4.2. Sequential Data Scans and Analytics Pipelines

Batch jobs reading large files may require **high MiB/s** with moderate I/O operation counts. In such cases, evaluate Hyperdisk Throughput while verifying performance limits for the chosen **size** and the application's parallel read capability. Hyperdisk ML targets ultra-high read bandwidth use cases and supported multi-VM read-sharing attach modes.

If the pipeline operates primarily on objects and does not need a block device, **Cloud Storage** may be a better storage model. If multiple machines operate on a standard NFS directory, consider **Filestore**.

### 4.3. Critical Data Requiring Zone Fault Tolerance

When the business requires a data layer capable of surviving zone outages within a region, evaluate **Hyperdisk Balanced High Availability**, where data is replicated between two zones per the product model. Still, you must answer:

- Which instance will keep running or take over after an outage?
- Does the filesystem/database support attach/failover and handling in-flight writes?
- What **RTO/RPO** does this design achieve in actual testing?
- If an **entire region** goes down, where are the backups or DR strategy?

Do not assume an HA volume replaces snapshots, application-consistent backups, or recovery from accidental deletion. Replication can replicate erroneous operations as well.

### 4.4. Illustrative Decision Matrix

| Key characteristic | Candidate to evaluate | Evidence to collect |
| --- | --- | --- |
| Balanced OLTP, small I/Os with uneven traffic spikes | Hyperdisk Balanced | Peak IOPS, write latency, p99, and provisioning cost |
| Very high-IOPS transactional database | Hyperdisk Extreme | Actual IOPS, machine series limits, database tuning |
| Large-volume sequential scans/writes | Hyperdisk Throughput | MiB/s, large I/O sizes, capacity requirements |
| AI/HPC massive data reads, many readers | Hyperdisk ML | Read-only attach support, throughput, supported machines |
| Data availability across two zones in one region | Hyperdisk Balanced High Availability | Replica mechanism, failover, consistency, and RTO/RPO |
| Multiple machines opening a filesystem over NFS | Filestore | File sharing needs, network latency, NFS permissions |
| Storing images, backups, or data as objects | Cloud Storage | API/object semantics, storage classes, and request costs |

Every final decision must verify **product support in the target zone/region**, machine type, IAM permissions, data classification, backups, reliability, and total architecture cost.

## 5. Hands-on: Configuring Hyperdisk Balanced with `gcloud`

This section demonstrates the workflow for **creating a new data disk**, inspecting provisioned values, and modifying IOPS/throughput. Commands are examples for learners to run **in an approved lab project**; reading the lesson does not create resources. Disks can incur charges for as long as they exist, even when detached from a VM.

### 5.1. Prerequisites and Safety Before Creating

Prepare the following:

- A project with an active Cloud Billing account and an account granted appropriate permissions for the Compute Engine Disks API.
- A zone that supports **Hyperdisk Balanced** and a supported machine type if you plan to attach the disk to a VM.
- An unused disk name in the zone, plus sufficient quota/capacity for the size and provisioned levels.
- Dedicated lab workload/data; never use a production disk for formatting or write benchmarks.
- Approved budget and a plan to delete the disk upon completion.

Relevant permissions typically include creating/viewing/updating/deleting Compute Engine disks, attaching disks to instances, and managing VMs if performing attachments. Grant only the IAM permissions needed for the task. For disks using CMEK, also verify encryption key permissions and policies.

### 5.2. Select Project and Zone

Run in Bash or Cloud Shell:

~~~bash
export PROJECT_ID="YOUR_LAB_PROJECT_ID"
export ZONE="YOUR_SUPPORTED_ZONE"
export DISK_NAME="hd-balanced-lab"

gcloud config set project "$PROJECT_ID"
gcloud config get-value project

# Read-only: check disk types available in the target zone
gcloud compute disk-types list \
  --zones="$ZONE" \
  --filter="name~hyperdisk"
~~~

Replace placeholders with a verified project and zone. **Do not** assume every zone supports every Hyperdisk type or machine type. If the Compute Engine API is not yet enabled, enabling it must follow your lab project's procedures and permissions.

### 5.3. Create Hyperdisk Balanced with Illustrative Performance

~~~bash
gcloud compute disks create "$DISK_NAME" \
  --zone="$ZONE" \
  --type=hyperdisk-balanced \
  --size=100GB \
  --provisioned-iops=6000 \
  --provisioned-throughput=300
~~~

Parameters:

| Parameter | Meaning |
| --- | --- |
| `--type=hyperdisk-balanced` | Selects the balanced block volume type. |
| `--size=100GB` | Data disk capacity; units are interpreted by gcloud per Compute Engine disk size rules. |
| `--provisioned-iops=6000` | Target IOPS level for the volume. |
| `--provisioned-throughput=300` | Target throughput level in MiB/s. |
| `--zone` | Location of the **zonal** disk; the attached VM must normally reside in the same zone, per compatibility rules. |

For Hyperdisk Balanced with a user-specified size, current troubleshooting documentation requires providing **both provisioned IOPS and throughput**. This example specifies both explicitly to avoid errors when setting a custom size while omitting one parameter.

**Note:** CLI validation during disk creation only confirms product/quota eligibility; it does not prove the VM or application will achieve the desired performance.

### 5.4. Inspect Provisioned Capacity and Performance

~~~bash
gcloud compute disks describe "$DISK_NAME" \
  --zone="$ZONE" \
  --format="yaml(name,type,sizeGb,provisionedIops,provisionedThroughput,status,users)"
~~~

Fields to inspect:

- `type`: disk type, e.g., Hyperdisk Balanced.
- `sizeGb`: configured capacity.
- `provisionedIops`: provisioned IOPS target, **distinct** from currently consumed IOPS.
- `provisionedThroughput`: provisioned throughput target, **distinct** from currently measured throughput.
- `users`: instances currently using the disk as returned, if any.

If the disk is not yet attached to a VM, there are no workload benchmark results to compare against. Save the disk description as configuration evidence prior to making changes.

### 5.5. Adjust Performance Without Changing Capacity

Suppose after measurement, the team decides to increase from **6,000 to 8,000 IOPS** and **300 to 400 MiB/s**, within supported disk-type/capacity limits:

~~~bash
gcloud compute disks update "$DISK_NAME" \
  --zone="$ZONE" \
  --provisioned-iops=8000 \
  --provisioned-throughput=400

gcloud compute disks describe "$DISK_NAME" \
  --zone="$ZONE" \
  --format="yaml(name,sizeGb,provisionedIops,provisionedThroughput)"
~~~

Hyperdisk supports changing provisioned performance in many cases **without increasing capacity** and while in use, subject to product rules. However:

1. **Cooldown:** current documentation specifies that modifying IOPS/throughput on most Hyperdisks can happen **no more often than once every 4 hours** per tracked metric; Hyperdisk ML uses roughly **6 hours** for throughput. For Balanced/Balanced HA, IOPS and throughput have separate cooldown timers.
2. **Time to take effect:** typical adjustments can take **up to roughly 15 minutes** to take effect; some modes and Hyperdisk ML differ. Do not treat a successful CLI response as meaning performance changed instantaneously.
3. **Configuration constraints:** values cannot exceed limits determined by disk type, capacity, or the IOPS/throughput relationship; quotas and policies can also block changes.
4. **Cost impact:** provisioning higher performance can increase billing even if the application does not consume all of it.
5. **Change rollback:** record previous values, measurements, and approvers; if you need to lower provisioned levels, check the cooldown and retest during a representative load window.

Do not run multiple `update` commands back-to-back to "trial-and-error until it works" when the product enforces a cooldown. Calculate the valid range first, pick a reviewed target, and measure after the change takes effect.

### 5.6. Why Not Use the Same Flags for Every Hyperdisk Type?

| Type | Creation flags to note | What must not be assumed |
| --- | --- | --- |
| Hyperdisk Balanced | `--type=hyperdisk-balanced`, size, IOPS, throughput | That every IOPS/throughput pair is valid. |
| Hyperdisk Extreme | Size and `--provisioned-iops` | That throughput is an independently provisioned parameter. |
| Hyperdisk Throughput | Size and `--provisioned-throughput` | That `--provisioned-iops` can be set directly. |
| Hyperdisk ML | Size and `--provisioned-throughput`, appropriate access mode | That IOPS is a direct tuning knob or read-write attach works in all modes. |
| Hyperdisk Balanced High Availability | Regional location, HA configuration, and product-specific performance | That it can be created/attached like a regular zonal disk just by swapping the type name. |

In particular, Hyperdisk Balanced High Availability is a **regional** option using a two-zone model; creating and managing it requires commands/resources appropriate for a **regional disk**, rather than arbitrarily substituting `--zone` from a zonal example.

## 6. Attaching Hyperdisk to a VM and Checking from the OS

A newly created volume is only a block storage resource. For an application to use it, you must attach it to a **compatible Compute Engine VM**, then prepare a filesystem or another block access method.

### 6.1. Execute Only on a Verified Lab VM

~~~bash
export VM_NAME="YOUR_COMPATIBLE_LAB_VM"

# Read-only: inspect machine, zone, and attached disks
gcloud compute instances describe "$VM_NAME" \
  --zone="$ZONE" \
  --format="yaml(name,machineType,disks)"

# Write operation: attach the lab-created data disk
gcloud compute instances attach-disk "$VM_NAME" \
  --zone="$ZONE" \
  --disk="$DISK_NAME" \
  --device-name=hd-balanced-lab
~~~

Before attaching, verify the VM uses a **machine series that supports the Hyperdisk type** and does not already hold a disk with the same name or in a different zone. Certain attach/multi-writer modes support only specific disk types and configurations; the example above targets a **standard single-VM data disk**.

### 6.2. Discovering the Disk in Linux and Protecting Data

On the **Linux lab VM**, inspect state:

~~~bash
lsblk -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINTS
ls -l /dev/disk/by-id/google-hd-balanced-lab
sudo blkid /dev/disk/by-id/google-hd-balanced-lab || true
~~~

If this is a **newly created, completely empty volume**, the operator can initialize a filesystem per OS procedures. Before formatting, it is mandatory to:

- Cross-check the serial/device name against the disk just created in Console/gcloud.
- Confirm the path is not the boot disk and does not contain partitions/filesystems/data to keep.
- Have an appropriate backup if there is any doubt about existing data.

Example **for a new, empty volume only**:

~~~bash
# WARNING: formatting erases any existing data structures on the device
sudo mkfs.ext4 /dev/disk/by-id/google-hd-balanced-lab

sudo mkdir -p /mnt/hyperdisk-lab
sudo mount /dev/disk/by-id/google-hd-balanced-lab /mnt/hyperdisk-lab
df -h /mnt/hyperdisk-lab
~~~

Never run `mkfs` on a production disk, a disk containing data, or an unverified device. After mounting, directory ownership and persistent mount settings across reboots (e.g., UUID-based `/etc/fstab`) must be configured per OS and application standards.

### 6.3. Disk Capacity, Filesystem, and Performance Are Three Separate Dimensions

These operations are not equivalent:

- **Increasing Hyperdisk capacity:** changes the volume's size attribute within allowed bounds; the guest OS partition/filesystem may need separate expansion.
- **Increasing provisioned IOPS/throughput:** changes performance settings; does not automatically grow mounted capacity.
- **Changing machine type:** can alter the VM's aggregate I/O limit or disk compatibility; review stop/start/compatibility procedures.

Do not treat `df -h` as proof of IOPS or throughput: that command displays filesystem capacity. Likewise, successful provisioning does not guarantee the workload reaches that level if the filesystem or VM is bottlenecked.

## 7. Benchmarking: Proving the Application Can Use Provisioned Performance

Running `fio` once can help clarify I/O limits, but you must separate **synthetic benchmarks** from **real application latency**. Fio lets you test various I/O sizes, random/sequential patterns, read/write mixes, and queue depths. Achieving high numbers in a sequential test does not guarantee a database running small queries will reach the same throughput.

### 7.1. Safety Rules When Testing I/O

**Benchmark only on a lab data disk or a dedicated test file.** Never run write commands against the raw device of a disk holding data; never select the boot disk by mistake. The examples below use **a test file** inside the filesystem mounted on the lab Hyperdisk.

Before running:

1. Verify the VM, machine type, disk type, size, provisioned IOPS, and provisioned throughput.
2. Verify `/mnt/hyperdisk-lab` resides on the exact test disk using `df -h`, `lsblk`, and the device name.
3. Ensure enough free space exists for the temporary file (e.g., 2 GiB) and that it holds no business data.
4. Choose a test window that will not disrupt other users; benchmarks can raise I/O latency for workloads sharing the VM/disk.
5. Account for VM/disk charges and tool installation if Internet/NAT access is needed; on Debian/Ubuntu Linux, `fio` is available from package repositories.

### 7.2. Safely Preparing a Test File

**On the lab VM**, after verifying the disk is mounted with proper write permissions:

~~~bash
sudo apt-get update
sudo apt-get install -y fio

# Apply only to the mount point created specifically for the lab
sudo chown "$(id -u)":"$(id -g)" /mnt/hyperdisk-lab

# Write sample data to ONE test file; do not write directly to the raw block device
fio --name=prepare \
  --filename=/mnt/hyperdisk-lab/fio-scratch.bin \
  --size=2G \
  --rw=write \
  --bs=1M \
  --ioengine=libaio \
  --iodepth=8 \
  --direct=1 \
  --group_reporting
~~~

The preparation command **overwrites `fio-scratch.bin`** if it already exists; confirm this path is not used by any application and holds no data to keep. Using a dedicated file limits the blast radius compared to writing directly to the block device.

### 7.3. Measuring IOPS with 4 KiB Random Reads

~~~bash
fio --name=randread-4k \
  --filename=/mnt/hyperdisk-lab/fio-scratch.bin \
  --size=2G \
  --rw=randread \
  --bs=4k \
  --ioengine=libaio \
  --iodepth=32 \
  --direct=1 \
  --readonly \
  --time_based \
  --runtime=60 \
  --group_reporting
~~~

Notable options:

- `--rw=randread` and `--bs=4k` simulate many small random reads.
- `--iodepth=32` allows multiple in-flight requests; increasing queue depth can boost IOPS up to a point, while also affecting latency.
- `--direct=1` attempts to bypass typical page caching so measurements stay closer to the disk path; filesystems, kernels, and environments can still influence results.
- `--readonly` reduces the chance of accidental writes during read tests.
- `--time_based --runtime=60` measures over a 60-second window rather than stopping after a fixed byte count.

Record **IOPS**, **BW** (MiB/s), **lat/clat**, latency percentiles, and CPU usage. Repeat runs and compare under consistent conditions.

### 7.4. Measuring Throughput with 256 KiB Sequential Reads

~~~bash
fio --name=seqread-256k \
  --filename=/mnt/hyperdisk-lab/fio-scratch.bin \
  --size=2G \
  --rw=read \
  --bs=256k \
  --ioengine=libaio \
  --iodepth=16 \
  --direct=1 \
  --readonly \
  --time_based \
  --runtime=60 \
  --group_reporting
~~~

This benchmark targets **MiB/s** and latency for large reads. Do not compare IOPS from a 256 KiB profile directly against the maximum IOPS documented for a 4 KiB profile as if they were the same test.

### 7.5. Measuring Mixed Load When Appropriate

A real service may read and write concurrently. If you need to test a mixed load, run it only against a **dedicated test file**:

~~~bash
# WRITES to the test file; do not run on production data
fio --name=mixed-4k \
  --filename=/mnt/hyperdisk-lab/fio-scratch.bin \
  --size=2G \
  --rw=randrw \
  --rwmixread=70 \
  --bs=4k \
  --ioengine=libaio \
  --iodepth=32 \
  --direct=1 \
  --time_based \
  --runtime=60 \
  --group_reporting
~~~

The 70% read ratio is illustrative; use the ratio observed in your real system. Database workloads also involve journals, fsync, transaction logs, caches, write synchronization, locks, and other factors, so **`fio` is only one of several measurements**.

### 7.6. Interpreting Results Beyond Peak Numbers

| Measurement result | Question to investigate | Possible action |
| --- | --- | --- |
| IOPS near provisioned level, p99 begins rising | Is it constrained by operation count? | Compare peak demand, optimize queries, consider increasing IOPS |
| MiB/s near provisioned level, IOPS has headroom | Is it bandwidth-constrained? | Adjust throughput if supported by the disk type |
| Low IOPS and MiB/s, high CPU | Is the application or benchmark saturating CPU? | Measure CPU, vCPUs, threads, and machine type |
| Low performance across multiple disks on one VM | Has the machine's aggregate IOPS/throughput cap been hit? | Check machine limits and combined load |
| Good random reads, yet application remains slow | Database locks, network, fsync, queries, or caching? | Measure end-to-end and inspect other components |
| Performance fluctuates after provision change | Has the new config taken effect? Is the load comparable? | Check cooldown/propagation and rerun with the same profile |

After testing, delete **only the lab benchmark file**:

~~~bash
rm -- /mnt/hyperdisk-lab/fio-scratch.bin
~~~

Do not use `*` wildcards or wipe the entire mount point if other data resides there. For sensitive data, ordinary file deletion is not a secure erasure mechanism guaranteeing removal of all copies.

## 8. Observing Performance and Tuning in Production

### 8.1. Measure Both the Disk Layer and the Application Layer

When putting Hyperdisk into production, build a dashboard that can explain:

- **Actual IOPS:** total read/write ops, tracking peak hours and p95 over time.
- **Actual throughput:** read/write MiB/s; whether it hits the provisioned cap.
- **Latency:** guest-OS I/O latency and correlated query/business latency.
- **Queue depth / pending I/O:** whether requests are queuing for disk; whether the workload generates enough requests to utilize provisioned performance.
- **Machine utilization:** CPU, memory, thread pools, and other resources that could create ceilings.
- **Disk configuration:** capacity, IOPS, throughput, disk type, timestamp of last provision change, and attached instances.
- **Cost:** cost tracked by Hyperdisk type, size, provisioned performance, snapshots, and related services.

Cloud Monitoring and OS tools may gather metrics from different sources. **Do not equate VM disk read/write metrics with all traffic hitting Hyperdisk directly**, since caching, filesystem layers, and sampling intervals can make measurements differ.

### 8.2. Evidence-Based Tuning Workflow

~~~mermaid
flowchart TD
    S["Measure workload, SLO<br/>IOPS, throughput, latency"] --> B{"Where is the real bottleneck?"}
    B -->|Disk / volume| D["Check disk type limits,<br/>size, and provisioned levels"]
    B -->|VM / application| A["Optimize CPU, concurrency,<br/>queries, filesystem, or VM"]
    D --> V{"Does machine type have<br/>enough headroom?"}
    V -->|No| M["Select appropriate VM<br/>based on capability and cost"]
    V -->|Yes| P["Test new provisioned level<br/>within supported range"]
    P --> R["Wait for change to take effect,<br/>re-measure under same conditions"]
    M --> R
    A --> R
    R --> C{"Meets SLO and budget?"}
    C -->|No| S
    C -->|Yes| E["Record decision,<br/>alerts, and periodic review"]
~~~

Even when provisioned settings can be modified while a volume is in use, planning is still required: raising performance can raise cost; lowering it too aggressively can spike latency. Changing machine types, migrating data, or changing disk types also introduces disruption, compatibility, and rollback risks.

### 8.3. Recording Configuration Decisions

An illustrative decision record:

~~~yaml
workload: order-db
environment: production
storage:
  product: hyperdisk-balanced
  size_gib: 100
  provisioned_iops: 6000
  provisioned_throughput_mib_per_s: 300
requirements:
  peak_read_write_iops: 4500
  p99_io_latency_ms: "<approved SLO threshold>"
  backup_rpo: "<approved target>"
evidence:
  - "4 KiB read/write benchmark under production-like load"
  - "IOPS, MiB/s, p95/p99 latency, and VM quota"
  - "Before-and-after cost comparison"
review_after: "<next review date>"
owner: "<responsible team>"
~~~

Values in angle brackets are placeholders, not YAML for direct deployment. Record measurements alongside the **exact machine type and zone** so a provisioned level from one VM is not blindly reused elsewhere.

## 9. Availability, Data Protection, and Access Control

### 9.1. High-Performance Hyperdisk Does Not Replace Backups

IOPS and throughput answer *how fast reads/writes occur*, whereas **backups, replication, and recovery** answer *whether data can be recovered when corrupted or when infrastructure goes down*.

| Risk | Appropriate tool or measure to consider | Limitations |
| --- | --- | --- |
| App accidentally drops a table or writes bad data | Snapshots, database backups, point-in-time recovery if supported | Replicas can replicate erroneous writes too. |
| One zone goes down | Hyperdisk Balanced High Availability and appropriate VM/failover design | Standard zonal Hyperdisk Balanced does not automatically become a regional disk. |
| Entire region disrupted | Cross-region DR plan, async replication if supported by disk type, backup/restore | RPO/RTO depend on replication mechanism, sync timing, and workload cutover capability. |
| Filesystem corruption or application bug | Application-consistent backups, restore verification, approved remediation workflow | A point-in-time snapshot is not guaranteed transactionally consistent. |
| Identity or encryption key compromised | Least-privilege IAM, Secret Manager, Cloud KMS/CMEK where appropriate | Encryption does not replace application controls and recoverability. |

**Hyperdisk snapshots** can provide point-in-time data protection. For actively writing databases, pay attention to **application-consistent snapshots**: Google Cloud documentation recommends coordinating application or filesystem quiescing when application consistency is required on Hyperdisk. Simply clicking snapshot while a database is running does not automatically guarantee consistent recovery of all transactions.

Perform **restore tests** periodically, verify data integrity, and measure **actual RPO/RTO**. A backup that has never been successfully restored is insufficient evidence for DR goals.

### 9.2. Differences Between Zonal Disks and Hyperdisk Balanced High Availability

~~~mermaid
flowchart TB
    subgraph Z["Zonal Hyperdisk Balanced"]
      VM1["VM - zone A"] --> D1["Volume in zone A"]
    end
    subgraph HA["Hyperdisk Balanced High Availability - one region"]
      VM2["Active VM in zone A"] --> RD["Logical regional volume"]
      RD --> RA["Replica zone A"]
      RD --> RB["Replica zone B"]
      STANDBY["Standby VM zone B"] -. "Failover per design" .-> RD
    end
~~~

Hyperdisk Balanced High Availability **replicates synchronously** across two zones within a region under operational conditions. Replica states (such as syncing or degraded) and recovery limits must be monitored. If a replica fails, do not assume RPO remains 0 at all times without checking **actual replica status**.

To keep an application running after a zone failure, you must design:

1. VMs or instance groups able to run in the standby zone;
2. Failure detection, service switching, and supported volume attachment procedures;
3. Networking, IAM, images, quotas, and secrets at the recovery location;
4. Database/filesystem recovery and data verification;
5. Traffic shifting, SLO monitoring, and failover/failback drills.

**Multi-writer does not mean safe multi-reader/writer file sharing.** When multiple VMs write to the same block volume, you must use a clustered filesystem or appropriate coordination software. Mounting a standard filesystem read-write from multiple VMs without locking/consistency coordination can corrupt data.

### 9.3. Encryption, IAM, and Sensitive Data

Hyperdisk belongs to Google Cloud-managed storage infrastructure; when an organization requires key control, consider **Customer-Managed Encryption Keys (CMEK)** where supported by the volume type and configuration. Processes must account for Cloud KMS permissions, key lifecycles, restore capability, and how disabling/destroying keys affects data readability.

Govern permissions on these principles:

- Someone who **reads metrics** does not necessarily need permission to delete disks.
- Someone who **adjusts provisioned IOPS/throughput** needs disk configuration permissions, cost approval workflows, and monitoring.
- Someone who **attaches a disk to a VM** can indirectly grant software on that VM access to the data; therefore control VM identity, OS permissions, and attach paths together.
- Someone who **manages snapshots/backups** needs appropriate permissions and must safeguard sensitive data inside copies.
- **Production** operators must verify organizational constraints, data residency, logs, and backups before moving disks or creating copies.

An encrypted block disk does not automatically secure data if the application uses an over-privileged database account or if the VM is compromised.

## 10. Common Troubleshooting When Creating, Attaching, and Tuning Hyperdisk

| Symptom | Possible cause | How to verify |
| --- | --- | --- |
| Creation command fails on disk type or location | Zone does not support the selected Hyperdisk type or configuration | Check current disk type/location lists; verify exact project and zone. |
| Creation reports invalid provisioned value | IOPS/throughput outside range for size, disk type, or pair relationship | Check limit tables/formulas for that exact type; for Balanced with custom size, supply both values. |
| Cannot create/attach despite valid parameters | Quota, capacity, IAM, or Organization Policy | Read API error message, quotas, identity, and policies. |
| Disk created but VM fails to attach | VM does not support disk type, wrong zone, wrong access mode, or incompatible attached disk config | Cross-check machine series, zone/region, access mode, and attachment limits. |
| Disk visible in Console, but Linux sees no filesystem | Block device is attached only; not yet formatted or mounted | Inspect `lsblk`, `blkid`, device ID; do not rush to format without verifying data. |
| Disk size increased, yet `df -h` unchanged | Partition/filesystem not expanded inside guest OS | Inspect each layer block device → partition → filesystem and run appropriate resize steps. |
| IOPS increased, yet benchmark did not improve | VM bottleneck, insufficient I/O size/queue depth, or change not yet active | Compare disk provisions, VM limits, cooldown/propagation, and benchmark profile. |
| High IOPS but low throughput | Workload uses small I/Os; mathematical throughput is correspondingly low | Compute IOPS × I/O size; verify actual read/write behavior. |
| Good throughput but high database latency | Transactions, fsync, CPU, queuing, caching, or contention | Check p95/p99, query tracing, OS metrics, and I/O wait. |
| Update rejected despite valid new values | Cooldown period between performance updates has not elapsed | Check provision change history and cooldown period per disk type. |
| VM slows down after adding multiple disks | Aggregate per-machine IOPS/throughput cap reached | Check performance limits by machine type; measure total I/O across all disks. |
| Bill rises even though VM is stopped | Hyperdisk remains provisioned and billed according to existing configuration | Inspect un-deleted disks, provisioned settings, and Billing Reports. |
| Data loss after using multi-writer | Filesystem/application does not support safe concurrent writes | Inspect access mode, cluster design, fencing mechanisms, and backups. |

### 10.1. Investigating a Slow Database

Suppose a database on Compute Engine reports query p99 jumping from 80 to 450 ms. Do not immediately jump from 6,000 to 60,000 IOPS. Instead:

1. **Identify which queries are slow:** reads/writes, lock waits, transaction logs, index scans, or backend call steps.
2. **Measure I/O on the VM:** op counts, sizes, throughput, latency, and queue depth during the incident window.
3. **Read Hyperdisk configuration:** size, provisioned IOPS/throughput, and timestamp of the latest modification.
4. **Check machine type limits:** vCPU count/machine series, total disks, and current caps.
5. **Inspect CPU and RAM:** cache misses, CPU contention, or heavy GC/worker activity can be the primary bottleneck.
6. **Test under representative load:** record before/after results when changing one deliberate variable.
7. **Verify cost and risk:** determine whether the new provision level justifies the SLO gain; maintain backup and recovery mechanisms.

If throughput is only 60 MiB/s while the database performs many 4 KiB writes, raising throughput to 2,000 MiB/s without addressing IOPS or queries may yield no improvement. If the entire VM is capped below the disk's setting, raising the disk provision will not fix the root cause either.

### 10.2. Using Read-Only Commands for Before/After Comparisons

~~~bash
gcloud compute disks describe "$DISK_NAME" \
  --zone="$ZONE" \
  --format="yaml(name,type,sizeGb,provisionedIops,provisionedThroughput,status,users)"

gcloud compute instances describe "$VM_NAME" \
  --zone="$ZONE" \
  --format="yaml(name,machineType,disks,status)"
~~~

In Cloud Console, the **Compute Engine → Storage → Disks** page displays capacity and provisioned settings by disk type; Cloud Monitoring and application dashboards help compare observed metrics against configured values.

Avoid copying numbers from another VM's screenshot or benchmark without knowing the machine type, disk count, workload, and measurement timestamp.

## 11. Scenario Exercise: Choosing Hyperdisk for Three Workloads

An enterprise builds an online learning platform on Google Cloud with three components:

1. **Order database:** stores course enrollment transactions, peaking around 16,000 IOPS, mostly 8 KiB I/Os, requiring low p99 latency.
2. **Batch analytics:** scans large datasets nightly, 256 KiB sequential reads, needing roughly 900 MiB/s; IOPS count is not the primary target.
3. **Training data:** a large dataset read concurrently by multiple VMs for machine learning models, with little or no writing during training.

The operations team has quota and access to Hyperdisk-supported machine types, yet faces a limited storage budget and zero tolerance for data loss from operational mistakes.

### 11.1. Step 1 — Convert Load from IOPS to MiB/s

For the database, estimate data transferred at peak:

\[
16,000 \times 8 \ \text{KiB} \div 1,024
= 125 \ \text{MiB/s}
\]

The **125 MiB/s** figure reveals nothing about latency or fsync frequency; you still need to measure p95/p99, transaction log writes, and queuing. If sequential backup scans run concurrently, peak throughput can far exceed estimates based solely on transactional operations.

For batch analytics, 900 MiB/s with 256 KiB I/Os corresponds to:

\[
900 \ \text{MiB/s} \div 0.25 \ \text{MiB/I/O}
= 3,600 \ \text{IOPS}
\]

Here **throughput** is the dominant criterion; buying very high IOPS is unlikely to help. When shifting to data warehouse queries or object pipelines, the access pattern might make another service more suitable than Hyperdisk.

### 11.2. Step 2 — Select Candidates

| Workload | Initial candidate | Why | Conditions to verify |
| --- | --- | --- | --- |
| Order database | Hyperdisk Balanced; evaluate Extreme if genuinely higher IOPS is required | IOPS and latency demand; provisionable from measured results | Machine type, DB tuning, p99, backups, HA, and cost |
| Batch analytics | Hyperdisk Throughput or a storage solution fitting the data format | High MiB/s requirement with large operations | Minimum size, valid throughput for size, CPU, and processing speed |
| Training data | Hyperdisk ML if shared read design is supported | Focus on read throughput and multi-VM read attach modes | Read-only attachment support, quota, VM/zone, data release workflow |

The team must still design **backups** for mutable data and **data classification** per policy, regardless of disk type.

### 11.3. Step 3 — Build a Configuration Proposal

Create the following table for each workload:

| Field | Value to verify |
| --- | --- |
| Storage capacity and growth | Current usage, reserve capacity, disk size limits |
| Hyperdisk type | Balanced, Extreme, Throughput, ML, or Balanced HA |
| Required IOPS | Average, p95, peak, read/write mix |
| Required throughput | MiB/s at realistic I/O sizes |
| Latency/SLO | p50, p95, p99, and business requirements |
| Machine type | Supports disk type and aggregate I/O demand |
| Location | Zone/region, residency, availability |
| Provisioned performance | Valid values by size, type, and product formula |
| Cost | Capacity, IOPS, throughput, snapshots, other resources |
| DR | Snapshots, backups, RPO/RTO, failover plan |
| Tests | Fio profiles and corresponding application measurements |

A strong proposal presents **evidence for every value**, rather than simply saying "pick Extreme because it is fastest."

### 11.4. Step 4 — Re-evaluate Changes After One Month

After one month, suppose the Order database consumes only 5,000 IOPS most of the time, spiking to 14,000 IOPS during a 30-minute peak window. The team provisioned 50,000 IOPS.

Analyze:

- Can provisioned levels be lowered while preserving a safety margin for peak load and p99?
- Do reports show CPU or lock contention is actually the limiting factor?
- Can batch schedules be shifted to avoid resource contention?
- Are projected savings substantial enough to justify tuning?
- Which time window should be re-measured after modifying settings and waiting for propagation?

**Suggested guidance:** profile the real load, review trends and growth, select a lower provisioned level **that still comfortably covers reasonable peak demand**, test under control, and observe. Do not automatically drop down to the average or leave it high merely because it was configured initially.

## 12. Cleaning Up Lab Resources and Verifying Costs

If you created a disk and attached it to a lab VM during the hands-on section:

1. Stop any processes using the mount point; delete **only** the dedicated benchmark file if present.
2. Unmount the filesystem inside the VM and confirm no critical I/O remains.
3. Detach the disk from the VM once safe.
4. Delete **the exact** lab volume created; never delete disks holding real data or disks handed over to others.
5. Verify the disk list and Billing Reports after deletion.

**Inside the VM**, after stopping applications using the mount point:

~~~bash
sudo umount /mnt/hyperdisk-lab
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS
~~~

**Outside the VM**, with `gcloud` pointed at the right project:

~~~bash
# Verify resource ID and attachment state before deleting
gcloud config get-value project
gcloud compute disks describe "$DISK_NAME" \
  --zone="$ZONE" \
  --format="yaml(name,type,sizeGb,users)"

# Detach only the lab-created data disk, after safely unmounting
gcloud compute instances detach-disk "$VM_NAME" \
  --zone="$ZONE" \
  --disk="$DISK_NAME"

# Delete only this lab's disk; never delete disks holding data to keep
gcloud compute disks delete "$DISK_NAME" --zone="$ZONE" --quiet

# Verify the lab volume is gone
gcloud compute disks list --filter="name=$DISK_NAME"
~~~

If you only created the disk and **never attached it**, skip the unmount/detach steps, but still verify disk name, zone, and owner before deleting.

**Stopping a VM does not automatically delete Hyperdisk.** Remaining volumes and their provisioned performance settings can still incur charges. Charges accumulated while the lab ran may appear with a delay in Cloud Billing reports.

## 13. Self-Check Questions

**1. Is a volume provisioned with 20,000 IOPS guaranteed to always deliver 20,000 IOPS?**  
No. Provisioned performance is a target; application load, capacity, disk type, machine type, queue depth, and other limits determine actual throughput.

**2. Roughly how many MiB/s is a workload achieving 10,000 IOPS with 4 KiB I/Os transferring?**  
Roughly **39.1 MiB/s**. You must convert KiB to MiB and distinguish IOPS from byte throughput.

**3. Can you set both provisioned IOPS and provisioned throughput on Hyperdisk Extreme?**  
Not under this disk type's direct configuration model: users provision IOPS, while throughput is derived according to product rules.

**4. Do Hyperdisk Throughput and Hyperdisk ML have an independent provisioned IOPS knob?**  
No. For these types, IOPS is determined from provisioned throughput according to the service formula.

**5. Why might increasing IOPS on a disk fail to speed up a database?**  
Because the workload may be constrained by CPU, machine type, locks, queries, I/O size, or throughput rather than IOPS.

**6. Why can't a zonal Hyperdisk Balanced volume in zone A be treated as having zone B redundancy?**  
Because a zonal volume does not automatically create a replica in zone B. You must evaluate Hyperdisk Balanced High Availability or an appropriate replication/recovery mechanism.

**7. Can you use multi-writer and mount a regular ext4 filesystem so two VMs can write safely together?**  
Not by default. You need a concurrent-write management and consistency solution supported by the filesystem/application.

**8. Does increasing disk capacity automatically expand the filesystem or raise provisioned throughput?**  
Not automatically in a way you can rely on across all configurations. Volume size, filesystem, and performance parameters are separate layers to manage.

**9. Do snapshots automatically guarantee application-consistent recovery while a database is actively writing?**  
No. You must design and test an application-consistent snapshot mechanism per business requirements, along with a restore procedure.

**10. If a VM is deleted while keeping the Hyperdisk, can billing continue?**  
Yes. Existing volumes and provisioned settings can continue incurring charges under product billing policies.

## Google Cloud References

- **Google Cloud Hyperdisk overview:** https://cloud.google.com/compute/docs/disks/hyperdisks — Hyperdisk types, workloads, and features.
- **Hyperdisk performance overview:** https://cloud.google.com/compute/docs/disks/hyperdisk-performance — provisioned performance, IOPS, throughput, and limits.
- **Hyperdisk performance limits by machine series:** https://cloud.google.com/compute/docs/disks/hyperdisk-perf-limits — per-VM/machine-type caps.
- **Hyperdisk Balanced:** https://cloud.google.com/compute/docs/disks/hd-types/hyperdisk-balanced — size, IOPS, and throughput limits.
- **Hyperdisk Extreme:** https://cloud.google.com/compute/docs/disks/hd-types/hyperdisk-extreme — configuration and limits suited for high IOPS.
- **Hyperdisk Throughput:** https://cloud.google.com/compute/docs/disks/hd-types/hyperdisk-throughput — throughput and IOPS provisioning formulas.
- **Hyperdisk ML:** https://cloud.google.com/compute/docs/disks/hd-types/hyperdisk-ml — read throughput, attachments, and limits.
- **Hyperdisk Balanced High Availability:** https://cloud.google.com/compute/docs/disks/hd-types/hyperdisk-balanced-ha — dual-zone replication and recoverability.
- **Create Hyperdisk volumes:** https://cloud.google.com/compute/docs/disks/add-hyperdisk — creation and attachment options.
- **Modify Hyperdisk size and performance:** https://cloud.google.com/compute/docs/disks/modify-hyperdisks — resizing, cooldowns, and adjusting provisions.
- **Analyze provisioned IOPS and throughput:** https://cloud.google.com/compute/docs/disks/analyze-iops-hyperdisk — inspecting configurations and comparing metrics.
- **Benchmark Hyperdisk performance:** https://cloud.google.com/compute/docs/disks/benchmark-hyperdisk-performance — testing methodology and measurement caveats.
- **Snapshot best practices:** https://cloud.google.com/compute/docs/disks/snapshot-best-practices — data protection, consistency, and restore.
- **Compute Engine disks pricing:** https://cloud.google.com/compute/disks-image-pricing — pricing structure by type, capacity, and performance.

Supported disk types, maximum specifications, provisioning formulas, compatible machine types, propagation times, and pricing are subject to change. In real deployments, verify current documentation at deployment time and test with the **exact workload, machine type, capacity, and zone**. Choosing the right Hyperdisk means selecting a justified performance level that satisfies latency/SLOs and recoverability within an acceptable budget.
