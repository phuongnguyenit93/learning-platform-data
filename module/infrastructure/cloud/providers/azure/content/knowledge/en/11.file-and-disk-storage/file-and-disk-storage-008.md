# IOPS, Throughput, Host Cache, and Disk Bursting

> **Chapter:** File and Disk Storage  
> **Module:** `CLOUD_PROVIDERS_AZURE` — Explore the Microsoft Azure ecosystem from subscriptions, resource groups, and Entra ID to virtual networks, compute services, storage, and data. Learn how to deploy, monitor, protect, and control costs for an application architecture on Azure.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish **IOPS, throughput, latency, queue depth**, and I/O operation size.
2. Calculate performance requirements for databases, logs, backups, and ETL from workload metrics.
3. Identify independent limits of **managed disks**, **Azure VMs**, and applications.
4. Choose the right Azure Managed Disk type based on capacity, sustained performance, and latency.
5. Distinguish **host caching** modes (`None`, `ReadOnly`, `ReadWrite`) and risks for data requiring durability.
6. Understand **credit-based disk bursting** and **on-demand bursting**, eligibility conditions, and cost.
7. Gather evidence via Azure CLI, Azure Monitor, and guest OS I/O tools to diagnose bottlenecks.

## 1. Context: Same Capacity, Very Different Disk Behavior

A company uses an Azure VM to run an order-processing application. The VM holds three types of data:

- **Database**: random access to small data pages, requiring thousands of operations per second.
- **Transaction log**: sequential writes, sensitive to latency and write durability.
- **Backup/batch export**: transferring large blocks of data over an extended duration.

Looking only at capacity, all three might use a 1 TiB disk. Yet their performance needs differ completely: the database is easily bottlenecked by **IOPS and latency**, while backups are typically bottlenecked by **throughput**.

On Azure, disks attach to VMs using Azure Managed Disks. Actual speed depends simultaneously on disk type, provisioned performance settings, VM limits, caching, and how the application issues I/O. Sometimes a disk advertises 10,000 IOPS while the VM permits less; other times a short benchmark hits high speed via **bursting** before dropping back to baseline.

So the questions to ask are: **How many IOPS, how many MiB/s, for how long, at what target latency, and across which limits?**

## 2. Five Foundational Concepts

### 2.1. IOPS — read/write operations per second

**IOPS** (*Input/Output Operations Per Second*) measures completed I/O operations per second. Example:

~~~text
Read operations:    3,200/s
Write operations:   1,800/s
Total:              5,000 IOPS
~~~

This is an aggregate figure; deeper analysis must also examine I/O size, read/write ratio, and distribution over time. A workload running 5,000 operations at 4 KiB differs sharply from 5,000 operations at 256 KiB.

### 2.2. Throughput — data volume per second

**Throughput** represents data transfer rate, such as MB/s or MiB/s. Given an average I/O size in KiB:

\[
\text{Throughput (MiB/s)}
\approx
\frac{\text{IOPS}\times\text{I/O size (KiB)}}{1024}
\]

Examples:

| IOPS | I/O size | Corresponding throughput |
| ---: | ---: | ---: |
| 2,000 | 8 KiB | 15.625 MiB/s |
| 2,000 | 32 KiB | 62.5 MiB/s |
| 2,000 | 256 KiB | 500 MiB/s |
| 8,000 | 8 KiB | 62.5 MiB/s |

Two workloads both running at 2,000 IOPS can demand **32×** different bandwidth.

**Unit note:** 1 MiB = 1,048,576 bytes, whereas 1 MB = 1,000,000 bytes. SKU spec pages and monitoring tools may display different units; standardize units when sizing.

### 2.3. Latency — time to complete an I/O

**Latency** is the elapsed time from issuing a read/write operation until receiving its completion, typically measured in ms. For transactional applications, pay attention to **p95/p99 latency** rather than averages alone.

A system can achieve high throughput while still feeling slow to users if a small fraction of requests suffer severe tail latency spikes.

### 2.4. Queue depth and parallelism

**Queue depth** describes the number of outstanding I/Os waiting or in flight at a layer. An application issuing synchronous reads one at a time may fail to saturate disk performance even when ample disk headroom remains.

By **Little's Law**, for a steady-state system we can approximate:

\[
\text{Outstanding I/O}\approx\text{IOPS}\times\text{Latency (seconds)}
\]

For example, at 4,000 IOPS and 5 ms latency:

~~~text
4,000 × 0.005 = roughly 20 outstanding I/Os
~~~

This is only an estimate to understand concurrency demand. Pushing queue depth too high can inflate latency without raising IOPS once limits are reached.

### 2.5. Access patterns and block sizes

| Attribute | Examples | Significance |
| --- | --- | --- |
| I/O size | 4 KiB, 8 KiB, 64 KiB, 1 MiB | Determines bytes moved per operation |
| Random/sequential | SQL random page, sequential backup | Affects caching and app optimization |
| Read/write mix | 90/10, 70/30, 20/80 | Shapes read/write paths and latency |
| Concurrency | 1, 8, 32, 128 concurrent I/Os | Controls ability to saturate resources |
| Working set | 2 GiB or 2 TiB | Determines cache effectiveness |
| Peak duration | 60 seconds or 4 hours | Dictates whether bursting helps |

**Never use maximum IOPS from a 4 KiB test to forecast throughput for a large-block backup job.**

## 3. The I/O Path Through an Azure VM Has Multiple Limit Layers

~~~mermaid
flowchart TD
    A["Application\nSQL, API, ETL"]
    B["Guest OS\nfilesystem, page cache, queue"]
    V["VM size\ncached / uncached limits"]
    H["Azure host cache\nif supported"]
    D["Managed disk\nSKU, size, provisioned performance"]
    S["Azure storage platform"]
    A --> B --> V
    V --> H
    H -->|"Cache miss / uncached I/O"| D --> S
    H -.->|"Supported cache hit"| A
~~~

This diagram illustrates **functional layers**, not exact internal physical Azure protocols.

### 3.1. Per-managed-disk limits

Each disk has IOPS and throughput caps tied to its SKU, size, or provisioned performance. Purely **hypothetical** example:

~~~text
Disk data-01:
  Provisioned IOPS:       5,000
  Provisioned throughput: 200 MiB/s
~~~

Both ceilings apply **simultaneously**. Hitting throughput first prevents reaching full IOPS with large blocks; hitting IOPS first prevents increasing operation counts solely via software latency reductions.

### 3.2. VM size limits

VMs also enforce aggregate I/O caps—especially **uncached IOPS/throughput** and, on supported VMs, **cached I/O** limits.

Suppose:

~~~text
Disk:              5,000 IOPS, 200 MiB/s
VM uncached limit: 4,000 IOPS, 160 MiB/s
Disk host caching: None
~~~

Overall performance ceiling:

~~~text
IOPS       ≤ min(5,000, 4,000) = 4,000
Throughput ≤ min(200, 160)     = 160 MiB/s
~~~

That is an **upper bound**, not a guaranteed rate. Real applications may observe less due to latency, queue depth, locks, CPU, or filesystem overhead.

### 3.3. Does attaching multiple data disks increase performance?

You can use multiple disks and shard data or stripe them via LVM/Storage Spaces to pool their capabilities. However:

- Aggregate I/O still stays bounded by VM limits.
- Disks may contend on the same I/O path.
- Striping complicates backups, recovery, and troubleshooting.
- VMs limit total attachable data disks/LUNs.
- Certain disk types allow scaling IOPS/throughput independently without adding extra disks or capacity.

**Never assume two disks automatically double IOPS** if the VM is already saturated.

### 3.4. Four bottleneck types to distinguish

1. **Disk-level throttling**: the disk hits provisioned IOPS or throughput.
2. **VM-level throttling**: aggregate I/O hits the VM's cached/uncached cap.
3. **Workload-limited**: the app issues too few outstanding I/Os or stalls on locks, CPU, or external services.
4. **Burst-limited**: the disk exhausts burst capacity or no longer qualifies for bursting.

If raising disk IOPS produces no improvement, inspect VM ceilings and workload concurrency before scaling further.

## 4. Choosing Azure Managed Disks by Demand

| Disk type | Typical workloads | Performance model | Host caching | Bursting |
| --- | --- | --- | --- | --- |
| **Standard HDD** | Low-I/O, latency-insensitive workloads | Tied to tier/size | Depends on supported VM/config | Do not design around bursting |
| **Standard SSD** | General apps needing SSD at moderate cost | Tied to tier/size | Per supported configuration | Credit-based on eligible configs |
| **Premium SSD (v1)** | Production VMs needing stronger IOPS/latency | Tied to tier/size | Available in supported scenarios | Credit-based or on-demand by tier and eligibility |
| **Premium SSD v2** | Needs independent IOPS and throughput provisioning | Tunable within SKU limits | **Host caching not supported** | Does not use v1-style disk bursting |
| **Ultra Disk** | Extreme performance, low-latency workloads | Provisioned performance independently | **Host caching not supported** | Does not use standard bursting |

This comparison is directional. OS/data disk eligibility, VM/region/zone support, maximum IOPS/MBps, and billing models can change. For production selection, verify exact specs for **the current SKU, region, and VM size**.

### Why do Premium SSD v2 and Ultra Disk size differently?

With Premium SSD (v1), baselines typically tie to size/tier. With Premium SSD v2 and Ultra Disk, performance is provisioned independently within supported bounds. Consequently:

- Choose capacity based on stored data requirements.
- Choose provisioned IOPS based on sustained operation rate.
- Choose provisioned throughput based on sustained bytes/second.
- Verify the VM has sufficient I/O headroom.
- Cost out provisioned settings rather than relying on brief bursts to meet SLOs.

**1 TiB of capacity does not deliver identical performance across all disk types.**

## 5. Calculating Application Performance Needs

### 5.1. OLTP: small random I/O, latency-sensitive

Suppose a database generates during peak hours:

~~~text
Read operations/second:  4,500
Write operations/second: 1,500
Average I/O size:        8 KiB
Peak window:             3 hours
Latency objective:       p99 under 10 ms
~~~

IOPS demand:

\[
4500+1500=6000\ \text{IOPS}
\]

Throughput demand:

\[
6000\times8/1024 = 46.875\ \text{MiB/s}
\]

This workload skews toward **IOPS and latency**; required throughput is modest. However, the peak lasts **3 hours**, so do not assume credit-based bursting can sustain above-baseline speeds for the entire window.

### 5.2. Backup: large I/O, high throughput

Suppose a backup reads sequentially at 2,000 IOPS averaging 256 KiB per operation:

\[
2000\times256/1024=500\ \text{MiB/s}
\]

Despite only 2,000 IOPS, this job demands **500 MiB/s**. If VM uncached throughput is only 160 MiB/s, the workload cannot hit 500 MiB/s through that path regardless of disk IOPS upgrades.

### 5.3. Account for concurrent workloads

| Window | Workload | Dominant demand |
| --- | --- | --- |
| 09:00–11:00 | Peak database load | 6,000 IOPS, low p99 |
| 02:00–03:00 | Off-peak database + backup | Heavy backup throughput |
| 10:00 ad-hoc backup | Peak database + backup | Aggregate VM ceiling and disk contention |

Peaks of two tasks **do not always occur together—or stay separated**. Measure real timelines to size hardware and schedule backups properly.

### 5.4. Budgeting headroom

If CPU, VM I/O, and disk IOPS sit constantly near their caps, minor traffic spikes drive queue depth and latency up sharply. Budget headroom based on:

- Traffic variability and expected growth.
- Peak windows, restarts, recoveries, or log replays.
- User latency SLOs.
- Online performance-tuning capabilities of your disk type.
- Budget and availability targets.

No single fixed headroom percentage fits every business; base yours on telemetry and realistic load tests.

## 6. Host Cache: None, ReadOnly, and ReadWrite

**Azure host caching** caches data at the VM host layer for supported disks and VMs. It accelerates compatible I/O patterns, particularly repeated reads. Not every I/O is served from cache.

| Mode | Meaning | When to evaluate |
| --- | --- | --- |
| `None` | Disables Azure host caching for the disk | Transaction logs, workloads needing strict write semantics, or disks not supporting caching |
| `ReadOnly` | Enables read caching without write-back caching | Read-heavy data files with repeating working sets |
| `ReadWrite` | Enables read and write caching per supported mechanics | Certain OS disks and apps with explicit support guidance |

### 6.1. Host cache vs. guest OS caching

Multiple cache layers can coexist:

~~~mermaid
flowchart LR
    A["Application\nbuffer pool"]
    B["Guest OS\npage cache"]
    C["Azure host cache\nif enabled"]
    D["Managed disk"]
    A --> B --> C --> D
~~~

If a report reads the same file repeatedly, later reads may be served largely from application cache, OS page cache, or host cache. Consequently:

- The application may report very high read bandwidth.
- Physical read I/O reaching the managed disk may be much lower.
- "Warm cache" benchmarks run faster than "cold cache" runs.
- Cache hit ratio depends on working set size and access patterns, not just enabling a setting.

**Host caching is not a backup or durable application storage layer.**

### 6.2. ReadOnly caching

For repeated-read workloads on supported disks, `ReadOnly` can reduce physical read I/O to storage, lower latency, and boost guest-observed read throughput.

Example of a database querying similar datasets repeatedly:

1. Blocks are fetched on first access.
2. Subsequent reads hit caches at an appropriate layer.
3. Fewer reads traverse down to the managed disk.
4. When patterns fit, application read speed improves.

Limits to note:

- If every read touches brand-new offsets, caching offers little benefit.
- `ReadOnly` does not directly raise the managed disk's write ceiling.
- Cached reads can count toward **the VM's cached I/O limits**.
- Measure with realistic read patterns and verify application compatibility.

### 6.3. ReadWrite caching and durability

`ReadWrite` is not a "free speed boost for every database disk." Certain apps rely on strict write ordering, flushes, or durable write semantics; picking the wrong mode can compromise correctness or crash recovery.

Typical guidance for SQL Server on Azure VMs:

| Disk role | Typically considered cache | Rationale |
| --- | --- | --- |
| OS disk | `ReadWrite` per supported OS disk config | Supports OS activity |
| SQL data disk | `ReadOnly` when VM/disk supports it | Leverages repeated reads; verify SQL guidance |
| SQL transaction log disk | `None` | Write path requires strict durability semantics and low latency |
| Backup/staging | Measure real load before deciding | Sequential I/O often gains little from caching |

This is **SQL Server guidance**, not universally transferable verbatim to PostgreSQL, Oracle, MySQL, or other database engines. Follow I/O durability documentation for each engine and environment.

### 6.4. Host cache restrictions to verify

- **Premium SSD v2 and Ultra Disk do not support host caching.**
- Support across Standard SSD/Premium SSD (v1), OS/data disks, and VM sizes must be verified for each specific pairing.
- Changing host caching may require stopping/restarting the VM or disrupt active I/O.
- Changing cache modes requires testing, backups, maintenance windows, and rollback plans.
- Cache hits do not increase **provisioned disk write IOPS** in all scenarios.

Never change caching on a production transaction log disk simply because a `ReadWrite` benchmark looked higher for a few seconds.

## 7. Disk Bursting: Conditionally Exceeding Baseline

Workloads rarely drive completely flat I/O:

~~~text
09:00–09:59   500 IOPS
10:00–10:02 3,000 IOPS
10:03–10:59   500 IOPS
~~~

**Disk bursting** enables supported Azure disks to process I/O above baseline for limited durations under defined conditions. It helps optimize costs when peaks are brief and load stays low most of the day.

### 7.1. Credit-based bursting

In **credit-based** bursting, while usage stays below baseline, the disk accumulates **burst credits** up to a cap. When load spikes above baseline, the disk spends credits; once credits drop or deplete, above-baseline capacity ends.

~~~mermaid
flowchart LR
    L["Load below baseline\nAccumulate credits"]
    C["Credits available\nup to cap"]
    P["Peak above baseline\nSpend credits"]
    E["Credits low / depleted\nReturn to baseline"]
    L --> C --> P --> E --> L
~~~

Purely illustrative math **for intuition only**, not Azure's exact credit accounting formula:

~~~text
Baseline:        500 IOPS
Peak:          3,000 IOPS for 60 seconds
Excess:        2,500 IOPS
Excess work: 150,000 operations above baseline
~~~

Actual service behavior depends on credit bucket sizes, disk SKU/tier, burst IOPS and throughput caps, and accumulation duration. Never cite 150,000 as a real tier credit limit.

### 7.2. On-demand bursting

Eligible **Premium SSD (v1)** configurations support **on-demand bursting**:

- Does not depend on accumulating credit buckets the same way credit-based bursting does.
- Allows exceeding baseline up to supported burst ceilings.
- May require explicit enablement and **incur additional charges**, depending on pricing terms.
- Remains bounded by disk and VM limits; never scales infinitely.

Do not assume every Premium SSD has on-demand enabled or that all OS/data disks, regions, and tiers support it.

### 7.3. Disk types and bursting mechanisms

| Disk type | Accurate view |
| --- | --- |
| Eligible smaller Premium SSD (v1) tiers | May include credit-based bursting |
| Other eligible Premium SSD (v1) tiers | May support conditional on-demand bursting |
| Eligible Standard SSD | Credit-based bursting on supported configs |
| Premium SSD v2 | Provision performance within limits; does not rely on v1-style disk bursting |
| Ultra Disk | Provision performance per demand where supported; no standard bursting |
| Standard HDD | Do not treat bursting as a baseline sizing mechanism |

Verify exact numbers against the **current SKU/size/API/region**, rather than relying on generic tables from another environment.

### 7.4. Disk bursting vs. VM bursting

**Disk bursting** applies to managed disks. **VM-level bursting**, where supported by a VM size, is a separate mechanism with its own rules.

Even when a disk can burst higher, the VM's aggregate uncached IOPS/throughput cap can enforce a lower ceiling. Conversely, spare VM headroom does not grant extra burst credits to a disk.

### 7.5. Short peaks vs. sustained load

A 30-second benchmark can look great while burst credits remain. A 4-hour ETL job may fall back to baseline partway through, extending runtime unexpectedly.

When deciding whether to rely on bursting, measure:

1. **Baseline IOPS and throughput** needed continuously.
2. **Peak duration** and fraction of the day spent peaking.
3. Whether the SKU supports bursting, its credit capacity, and peak caps.
4. Whether the VM has sufficient cached/uncached headroom.
5. Whether SLOs tolerate falling back to baseline.
6. On-demand fees versus upgrading the disk SKU.

Never treat peak burst specs as a steady-state SLO guarantee.

## 8. Distinguishing Cache Hits, Bursts, and Throttling

| Situation | Symptoms | Evidence to compare |
| --- | --- | --- |
| **High host cache hit rate** | Guest reads run much faster than physical disk reads | Guest/app counters, disk metrics, warm/cold tests |
| **Active burst credits** | Initial high speed followed by drop to baseline | Disk SKU/burst behavior, performance timeline |
| **On-demand bursting** | Sustained above-baseline speed per enabled config | Disk properties, billing, VM caps |
| **Disk throttling** | Disk hits provisioned IOPS or throughput | Disk-level utilization/latency |
| **VM throttling** | Multiple data disks plateau while individual disks keep headroom | VM cached/uncached IOPS/bandwidth |
| **Insufficient app concurrency** | Disk/VM retain headroom while IOPS stays low | Queue depth, threads, locks, CPU |
| **Memory/page cache** | Second read runs vastly faster with minimal guest disk I/O | OS/application cache metrics |

**Cache speed and burst speed are distinct phenomena.** A test can reflect both simultaneously, so rigorous benchmarks must record working set, duration, cache mode, and burst state.


## 9. Inspecting Azure VM and Managed Disk Configurations

Commands in this section are **read-only**. Replace resource group, VM, and disk names with authorized names in your subscription.

### 9.1. Confirm tenant, subscription, and VM size

~~~bash
az login

az account show \
  --query "{subscription:name, subscriptionId:id, tenantId:tenantId}" \
  --output json

# Select the target subscription only after verifying identifiers.
az account set --subscription "<SUBSCRIPTION_ID>"

az vm show \
  --resource-group rg-data-prod \
  --name vm-db-prod \
  --query "{name:name, location:location, size:hardwareProfile.vmSize}" \
  --output json
~~~

VM size governs attachable data disk count, disk type compatibility, and I/O limits. Always cross-check **cached/uncached IOPS and cached/uncached throughput** for the exact family/size in Azure technical docs when sizing.

### 9.2. Inspect OS disk, data disks, LUNs, and caching

~~~bash
az vm show \
  --resource-group rg-data-prod \
  --name vm-db-prod \
  --query "storageProfile" \
  --output json
~~~

Key fields:

- `storageProfile.osDisk.caching`.
- `storageProfile.dataDisks[].name`.
- `storageProfile.dataDisks[].lun`.
- `storageProfile.dataDisks[].caching`.
- `storageProfile.dataDisks[].managedDisk.id`.

**Illustrative** partial configuration snippet:

~~~json
{
  "name": "data-sql-01",
  "lun": 0,
  "caching": "ReadOnly",
  "managedDisk": {
    "id": "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-data-prod/providers/Microsoft.Compute/disks/data-sql-01"
  }
}
~~~

This confirms LUN 0 uses `ReadOnly`. However, it **does not reveal cache hit rates** or actual runtime performance.

### 9.3. Inspect SKU and provisioned performance

~~~bash
az disk show \
  --resource-group rg-data-prod \
  --name data-sql-01 \
  --query "{name:name, sku:sku.name, sizeGiB:diskSizeGb, iops:diskIOPSReadWrite, throughputMBps:diskMBpsReadWrite, burstingEnabled:burstingEnabled, state:diskState}" \
  --output json
~~~

Depending on SKU/API, `diskIOPSReadWrite`, `diskMBpsReadWrite`, or `burstingEnabled` may return `null` or be inapplicable. Seeing `null` alone is **insufficient** to conclude credit-based bursting support. Verify tier, region, and disk documentation.

### 9.4. Check VM size capabilities by region

~~~bash
# Example command listing VM SKUs in a region.
az vm list-sizes \
  --location southeastasia \
  --output table
~~~

This command returns a long list. To find exact cached/uncached IOPS and throughput caps, consult the I/O capability table for the specific VM family/size, because `list-sizes` does not necessarily expose all performance caps.

### 9.5. Commands to avoid during read-only diagnostics

Actions like changing cache mode, resizing a VM, upgrading disk tier, or enabling on-demand bursting can affect availability and billing. Never run `az vm update` or `az disk update` before gathering bottleneck evidence, verifying compatibility, ensuring backups, and preparing a rollback plan.

## 10. Collecting Performance Metrics at the Right Layer

### 10.1. Azure Monitor: inspect both VM and disk

Open Azure Monitor → Metrics for the **VM** and relevant **Managed Disks**. Useful metric groups:

| Group | What to learn |
| --- | --- |
| Read/write operations per second | Read and write IOPS |
| Read/write bytes per second | Per-direction throughput |
| Read/write latency | Do I/O slowdowns align with app latency? |
| Disk IOPS/bandwidth consumed percentage | Are you nearing provisioned ceilings? |
| VM cached/uncached performance | Is the VM hitting its own I/O cap? |
| VM CPU/memory | Are non-disk bottlenecks present? |
| OS disk and each data disk | Which specific disk generates the load? |

**Exact metric names and dimensions depend on resource type/SKU.** Do not assume every disk emits identical metrics. Inspect resource metric definitions before copying metric names from another example.

### 10.2. Query metric definitions via CLI

~~~bash
DISK_ID=$(az disk show \
  --resource-group rg-data-prod \
  --name data-sql-01 \
  --query id \
  --output tsv)

az monitor metrics list-definitions \
  --resource "$DISK_ID" \
  --output table
~~~

Then pick metrics actually present in that list, such as read/write operations or bytes per second. For VM-level metrics, retrieve the VM resource ID and inspect definitions at that scope.

When interpreting charts, remember Azure Monitor metrics use **aggregation intervals**. A 1-minute average can smooth away multi-second bursts. Choose suitable aggregations and time granularities.

### 10.3. On Linux: iostat and lsblk

When the guest has the `sysstat` package installed:

~~~bash
# Collect 5 consecutive samples, 1 second apart.
iostat -dx 1 5

# Identify the measured disk, size, and mountpoint.
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS
~~~

In `iostat -x`, column names may vary by version:

| Column | Meaning |
| --- | --- |
| `r/s`, `w/s` | Read/write operations per second |
| `rkB/s`, `wkB/s` | Read/write rates in tool units |
| `r_await`, `w_await`, `await` | Average I/O wait/service time |
| `aqu-sz` | Average outstanding/queued I/O requests |
| `%util` | Guest-OS-measured device busy percentage |

**Do not conclude a disk is saturated solely from `%util=100`** on multi-queue virtual devices. Examine IOPS, throughput, latency, queue depth, and Azure caps together.

### 10.4. On Windows: Performance Monitor

On Windows VMs, use PerfMon or existing telemetry for counters such as:

- `PhysicalDisk\Disk Reads/sec`, `Disk Writes/sec`.
- `PhysicalDisk\Disk Read Bytes/sec`, `Disk Write Bytes/sec`.
- `PhysicalDisk\Avg. Disk sec/Read`, `Avg. Disk sec/Write`.
- `PhysicalDisk\Current Disk Queue Length`.

Correlate OS disk/LUN numbers with corresponding managed disks. Drive letters like `C:` or `D:` do not replace verifying the Azure disk Resource ID.

### 10.5. Do not confuse metric layers

Suppose an application dashboard reports 12,000 read IOPS while the managed disk metric shows 3,000 read IOPS. This is not necessarily a measurement bug:

- Some reads may be served from application caches.
- Some may be served from the guest OS page cache.
- Some may hit Azure host cache when supported.
- Guest, VM, and managed disk metrics do not have to record identical operation counts.

To isolate behavior, test **cold reads** vs. **warm reads**, recording working set, cache mode, disk metrics, and app-level operations.

### 10.6. Observe long enough

For workloads with 90-minute backups, checkpoints, or burst credits, a 10-second snapshot is rarely enough. Collect telemetry across:

1. Pre-peak baseline.
2. Peak onset.
3. Mid- and late-peak periods.
4. Post-peak wind-down.
5. Recovery phases right after restarts or cache mode changes.

The goal is **sustained performance and application SLOs**, not a single peak IOPS number.

## 11. Controlled Benchmarking

### 11.1. Three distinct benchmark questions

- **IOPS test:** how many operations/s can small random I/O reach given sufficient concurrency?
- **Throughput test:** how many MiB/s can large sequential I/O reach?
- **Application benchmark:** how do real queries/APIs perform in business latency and throughput?

`fio` or DiskSpd outputs do not replace SQL, ETL, or API benchmarks. Two runs differing in block size or queue depth can yield vastly different numbers.

### 11.2. Control comparison variables

Before running benchmarks, record:

| Parameter | Fix or document |
| --- | --- |
| VM size | Family, size, region/zone |
| Disk | SKU, size, provisioned IOPS and MBps |
| Cache | None/ReadOnly/ReadWrite |
| Workload | Block size, random/sequential, read/write ratio |
| Concurrency | Threads/jobs and queue depth |
| Dataset | File size, warm/cold cache |
| Duration | Warm-up length, test duration, peak length |
| Bursting | Credit/on-demand availability and prior credit state |
| Environment | Filesystem, OS, drivers, background tasks |

Changing VM size, disk tier, and queue depth simultaneously makes it impossible to tell which change drove the result.

### 11.3. fio example on a dedicated lab filesystem

The following commands **write test data**. Run only on a **dedicated lab disk** after verifying mount point, free space, and absence of data to retain. Never point `fio` at raw devices holding real data or production volumes.

~~~bash
# Writes a 2 GiB file; run ONLY on a dedicated test disk.
fio \
  --name=sequential-write-lab \
  --filename=/mnt/bench-volume/fio-test.bin \
  --size=2G \
  --rw=write \
  --bs=256k \
  --ioengine=libaio \
  --iodepth=16 \
  --direct=1 \
  --runtime=60 \
  --time_based \
  --group_reporting
~~~

Once the test file is validly created, you can measure random reads:

~~~bash
fio \
  --name=random-read-lab \
  --filename=/mnt/bench-volume/fio-test.bin \
  --size=2G \
  --rw=randread \
  --bs=8k \
  --ioengine=libaio \
  --iodepth=32 \
  --direct=1 \
  --runtime=60 \
  --time_based \
  --group_reporting
~~~

How to interpret:

- `IOPS` and `BW`: operation rate and data rate.
- `latency` and percentiles: I/O wait behavior.
- CPU load and concurrent tasks.
- Azure Monitor charts over the exact same window.

**Limitations:** `--direct=1` mainly bypasses the **guest OS page cache** on supported systems; **it does not necessarily bypass Azure host cache**. A 2 GiB file may also be far smaller than your real working set. A 60-second benchmark easily reflects **bursting** rather than multi-hour sustained performance.

### 11.4. Test sustained duration rather than short peaks

If an application runs continuously for 2–4 hours, **sustained** benchmarks must use sufficient duration and dataset size inside an authorized lab environment. Watch throughput over time; if speed starts high and then drops, inspect burst credits, caches, and VM throttling.

Never ramp up test intensity in production without application safeguards and blast-radius limits.

## 12. Investigation Workflow When a Disk or Database Slows Down

Suppose after traffic growth, API latency rises and the database logs frequent disk waits.

### Step 1 — Pinpoint user pain

Record VM/disk names, workload, timestamps, p95/p99 application latency, read/write mix, and recent changes (deployments, backups, disk/VM resizes, snapshots, or cache edits).

### Step 2 — Read actual configuration

Use Section 9 Azure CLI queries to verify:

- Each disk's SKU and provisioned IOPS/throughput.
- VM size and uncached/cached limits.
- OS/data disk caching modes.
- Whether bursting is supported or enabled.
- Total data disks and co-located workloads on the VM.

### Step 3 — Calculate IOPS and throughput

From observed metrics, compute average I/O size:

\[
\text{I/O size (KiB)}
\approx
\frac{\text{Throughput (MiB/s)}\times1024}{\text{IOPS}}
\]

Seeing 80 MiB/s at 5,120 IOPS gives an average I/O size around **16 KiB**.

### Step 4 — Compare disk caps, VM caps, and workload

| Symptom | Stronger suspect | What to check |
| --- | --- | --- |
| Disk near IOPS cap, VM has headroom | Disk IOPS-bound | Raise provisioned IOPS/SKU, shard load |
| Disk near throughput cap, IOPS not high | Disk throughput-bound | Throughput cap, block size, I/O pattern |
| Multiple disks plateau as VM nears uncached cap | VM-level throttle | Choose a VM size with more I/O headroom |
| Disk/VM retain headroom, low queue | App lacks concurrency | Threads, DB waits, locks, queue depth |
| High queue, rising latency, flat IOPS | Likely saturated | Disk/VM caps, CPU/memory |
| Benchmark fast initially, slows after minutes | Burst depleted or workload shifted | SKU, credit/burst behavior, timeline |
| Repeated reads fast, cold reads slow | Cache effects | Working set, host/OS/app caches |
| Slow transaction log writes | Write latency/durability | Log disk caching, DB log waits, flushes |

### Step 5 — Rule out non-disk factors

Disks are not the only culprit. Also inspect:

- SQL locks or suboptimal query plans.
- CPU saturation, RAM shortage, paging/swapping.
- Database connection pools or thread pools.
- Background backups/antivirus/agents competing for I/O.
- Nearly full filesystems, readahead settings, or I/O schedulers.
- Applications generating excessive tiny I/Os or unnecessary synchronous flushes.
- Dependent network/service latency at other tiers.

### Step 6 — Change only one controlled variable

Options include increasing provisioned IOPS/throughput, changing disk tier, choosing a larger VM size, separating data/logs, tuning caching per database guidance, optimizing queries/batching, or rescheduling backups.

Before making any change, verify downtime impact, reversibility, backups, and cost impact.

### Step 7 — Measure real outcomes

After the change, verify:

1. Did p95/p99 application latency decrease?
2. Do IOPS/throughput meet targets throughout the **entire peak**?
3. Are there signs of disk/VM throttling, queue buildup, or burst exhaustion?
4. Were durability, write errors, or recoverability affected?
5. Is the added cost justified by the SLO improvement?

**True optimization improves user behavior and operability, not merely a higher IOPS figure on a spec sheet.**


## 13. Two Real-World Deployment Scenarios

### 13.1. SQL Server OLTP and transaction logs

**Context:** SQL Server runs on an Azure VM, placing data files and transaction logs on separate managed disks. Peak hours bring heavy small random reads/writes; nightly backups run later.

Initial analysis:

| Component | Workload | Primary target |
| --- | --- | --- |
| Data disk | 8 KiB random I/O, read-heavy | IOPS, read latency |
| Transaction log disk | Sequential writes, durability critical | Write latency, correctness |
| Backup disk or target | Large sequential I/O | Throughput and completion window |
| VM | Aggregate I/O across all disks | Cached/uncached caps and headroom |

Arithmetic example:

~~~text
Data I/O: 5,500 IOPS × 8 KiB
  → roughly 42.97 MiB/s

Transaction log I/O: 1,000 IOPS × 32 KiB
  → roughly 31.25 MiB/s
~~~

Selection approach:

1. Measure baseline and p95/p99 latency per I/O path.
2. Size SKU/IOPS/throughput for sustained peaks with headroom.
3. Consider `ReadOnly` host caching on the SQL data disk where supported and aligned with SQL Server guidance.
4. Prefer `None` on the transaction log disk when recommended for the workload/disk.
5. Verify VM-level I/O limits; avoid provisioning disks far beyond what the VM can utilize.
6. Never rely on burst credits to carry multi-hour peak transactional windows.
7. Monitor SQL wait stats, log write latency, CPU/memory, disk/VM metrics, and app SLOs.

**Takeaway:** two disks of identical capacity do not necessarily share the same cache mode or SKU because their read/write and durability demands differ.

### 13.2. Batch analytics reading large datasets

**Context:** a pipeline reads large files to generate reports, running roughly two hours nightly. Estimated demand:

~~~text
Sequential read operations: 1,500 IOPS
Average size:               512 KiB
Required throughput:        750 MiB/s
Window:                     2 hours
~~~

Analysis:

- 1,500 IOPS looks modest for many disks, yet **750 MiB/s** is substantial throughput.
- Choosing a disk solely by max IOPS may fall short on throughput.
- The VM's uncached path must sustain that byte rate.
- `ReadOnly` caching offers little help when data is read once across a huge working set.
- A two-hour sustained run makes relying solely on credit-based bursting risky.
- Consider disks allowing independent throughput provisioning if supported by VM/region.

To optimize end-to-end, also evaluate batch size, I/O parallelism, data partitioning, compression CPU overhead, and downstream service latency.

### 13.3. Initial decision matrix

| Workload | Primary criteria | Host cache to evaluate | Bursting assessment |
| --- | --- | --- | --- |
| OLTP random read | IOPS, p99 latency | `ReadOnly` data disk on supported configs | Fits brief peaks only with ample headroom |
| Transaction log | Write latency, durability | `None` per product guidance | Never rely on it for continuous writes |
| Backup/restore | Sequential throughput | Measure against real workload | Account for job duration |
| ETL/batch | MiB/s, completion window | Not beneficial by default | Check peak length and cost |
| General business VM | Cost, latency, IOPS, throughput | Per OS/data role and SKU | Helpful for short spikes |
| High-performance DB | Provisioned IOPS/throughput, latency | v2/Ultra do not support caching | Pick sustainable baseline over credits |

## 14. Practice Calculations and Bottleneck Identification

### 14.1. Simulated dataset

A VM has one data disk with **purely hypothetical** limits:

| Parameter | Value |
| --- | ---: |
| Disk baseline IOPS | 5,000 |
| Disk baseline throughput | 180 MiB/s |
| VM uncached IOPS | 4,000 |
| VM uncached throughput | 150 MiB/s |
| Host cache | None |
| Average I/O size | 64 KiB |
| Peak duration | 3 hours |

#### Problem A — How much throughput does 4,000 IOPS require?

\[
4000\times64/1024=250\ \text{MiB/s}
\]

**Answer:** requires 250 MiB/s, exceeding both the 180 MiB/s disk baseline throughput and the 150 MiB/s VM uncached throughput. Raising disk IOPS alone will not fix the throughput ceiling.

#### Problem B — If the VM caps at 150 MiB/s, what is the max IOPS at 64 KiB?

\[
\text{IOPS}\leq\frac{150\times1024}{64}=2400
\]

**Answer:** theoretical ceiling is around **2,400 IOPS** due to throughput before factoring in latency or software overhead. Even though the VM advertises 4,000 uncached IOPS, this block size hits the throughput cap first.

#### Problem C — Should bursting be relied on for a three-hour peak?

**Answer:** not by default. Verify SKU, burst type, credit/on-demand caps, VM ceilings, and cost. For sustained three-hour performance, size sustainable provisioned/baseline capacity or adjust the architecture.

#### Problem D — What if you swap the disk to a 400 MiB/s SKU while keeping the VM?

**Answer:** the VM uncached throughput ceiling remains 150 MiB/s. Upgrade the VM size or redesign I/O paths if the true requirement is higher.

### 14.2. Classifying IOPS-bound vs. throughput-bound workloads

| Workload | IOPS | I/O size | Corresponding throughput |
| --- | ---: | ---: | ---: |
| A | 10,000 | 8 KiB | 78.125 MiB/s |
| B | 800 | 512 KiB | 400 MiB/s |
| C | 1,000 | 16 KiB | 15.625 MiB/s |

**Question:** which workload places the highest IOPS pressure? Which needs the greatest bandwidth? Can you determine their latencies from this table alone?

**Hints:**

- A demands the highest operation count.
- B demands the highest throughput.
- C is smaller in both IOPS and throughput, yet can still feel slow if backend latency is high.
- Not enough data to determine latency; you need concurrency, queue depth, disk/VM specs, and real workload behavior.

### 14.3. Distinguishing host cache from disk burst

Hypothetical test result:

~~~text
Host cache: ReadOnly
Guest application:     12,000 read IOPS
Managed disk metric:    3,000 read IOPS
Second read pass:       noticeably faster
~~~

**Question:** is Azure's metric definitely broken?

**Answer:** no. Many reads may be served from application/OS/host caches. Compare cold vs. warm cache runs, working set size, guest counters, and storage metrics. Metrics measured at different layers need not match.

### 14.4. Designing an improvement plan

A VM has 4 data disks. Total workload demand is 6,000 uncached IOPS, VM limit is 5,000 uncached IOPS, and each disk still has headroom.

**Question:** if you raise provisioned IOPS on all four disks, will the application reach 6,000 IOPS?

**Answer:** you cannot exceed the VM's 5,000 uncached IOPS cap by modifying disks alone. Evaluate a larger VM size or distribute the workload across multiple VMs/I/O paths while verifying throughput and application concurrency.

### 14.5. Planning your observability checklist

Fill in real evidence for your system:

| Question | What to verify |
| --- | --- |
| When does the app slow down? | Peak timeline, p95/p99 latency |
| Bound by IOPS or throughput? | Ops/s, bytes/s, I/O size |
| Is the disk near its cap? | SKU, provisioned values, metrics |
| Is the VM hitting its I/O ceiling? | Cached/uncached limits and counters |
| Is caching skewing results? | Caching mode, warm/cold, guest/disk metrics |
| Is bursting supported and long enough? | SKU, mode, peak length, credits/on-demand |
| Are non-disk factors involved? | CPU/RAM/locks/queries/dependencies |
| Which change is safe and effective? | Impact, downtime, rollback, cost, SLO |

## 15. Common Misconceptions

| Misconception | Accurate understanding |
| --- | --- |
| "Large disk capacity guarantees a fast app." | SKU, provisioned IOPS/throughput, VM, and workload all matter. |
| "10,000 IOPS equals 10,000 MB/s." | You need I/O size and data units. |
| "Meeting disk IOPS alone is enough." | Throughput, latency, and VM caps also apply. |
| "Attaching two extra disks doubles IOPS." | VM aggregate limits and concurrency can bottleneck. |
| "ReadWrite cache is always faster and safe for databases." | Must respect write durability semantics and workload guidance. |
| "ReadOnly cache speeds up all reads and writes." | Helps repeated reads with good hit rates; does not boost writes by default. |
| "Premium SSD v2 and Ultra Disk support host caching like Premium SSD v1." | Neither supports host caching. |
| "Burst IOPS provides all-day sustained speed." | Conditional, bounded, and credits can run out. |
| "Enabling disk bursting raises the VM I/O limit." | Disk and VM caps are independent. |
| "A 30-second benchmark proves production meets SLOs." | Must test sustained performance, latency, and real workloads. |
| "Slow I/O is always the disk's fault." | Can stem from CPU, memory, locks, database, or app design. |
| "Changing cache mode is always zero-downtime." | May require maintenance/restarts; verify and prepare rollback. |

## 16. Self-Check Questions

**Question 1.** A workload runs 3,000 IOPS averaging 16 KiB/I/O. Roughly what throughput is that?

**Answer:** `3000 × 16 / 1024 = 46.875 MiB/s`.

**Question 2.** A disk is provisioned for 10,000 IOPS, yet the VM has a 6,000 uncached IOPS limit and caching is `None`. Can it sustain 10,000 uncached IOPS?

**Answer:** No. The VM's 6,000 limit caps performance before even considering throughput or application behavior.

**Question 3.** Why can backups run slowly even when IOPS is not high?

**Answer:** Backups use large block sizes demanding many MiB/s. Throughput caps at the disk or VM can become the primary bottleneck.

**Question 4.** What does `ReadOnly` host caching help with, and does it boost write performance?

**Answer:** It can speed up reads on cache hits; do not assume it directly increases managed disk write capacity.

**Question 5.** Why do transaction logs typically avoid arbitrary write caching?

**Answer:** Logs require durable write semantics and reliable crash recovery; follow guidance from your database engine and Azure VM/disk docs.

**Question 6.** A disk runs fast for the first two minutes, then drops to baseline. Name three causes to investigate.

**Answer:** Exhausted burst credits, VM/disk bandwidth caps, or shifts in load/cache behavior. Verify using configuration and metrics.

**Question 7.** Premium SSD v2 needs higher IOPS without increasing capacity: what should you evaluate?

**Answer:** Independent IOPS/throughput provisioning within SKU/VM/region limits and associated costs; do not apply Premium SSD v1 bursting/host-cache models.

**Question 8.** Why does `fio --direct=1` not guarantee bypassing all caches?

**Answer:** It mainly bypasses the guest OS page cache on supported OSes; host caches and other layers may still participate.

**Question 9.** You upgrade a disk from 200 MiB/s to 500 MiB/s while the VM limit stays 160 MiB/s. What should you expect for uncached I/O?

**Answer:** You cannot surpass the VM's 160 MiB/s uncached throughput ceiling by upgrading the disk alone. Evaluate upgrading the VM or architecture after confirming the bottleneck.

**Question 10.** If IOPS hits target yet p99 latency remains high, has the system met its SLO?

**Answer:** Not necessarily. Application SLOs often depend on tail latency, contention, and end-to-end request time; check business metrics.

## Key Takeaways

- **IOPS** measures operations/sec; **throughput** measures data/sec; **latency** is operation time; **queue depth** reflects queued/in-flight operations.
- **Throughput ≈ IOPS × I/O size** once units align. Size disks for IOPS, MiB/s, and latency together.
- Real-world speed is bounded simultaneously by **disk, VM, cached/uncached paths, and workload**.
- **Host caching** offers `None`, `ReadOnly`, and `ReadWrite`; use only where supported by the disk type and read/write semantics.
- **Disk bursting** helps absorb short peaks but never replaces provisioned baselines for multi-hour sustained loads.
- Distinguish **credit-based bursting, on-demand bursting**, and per-SKU provisioned IOPS/throughput tuning.
- Always correlate **Azure Monitor + guest metrics + application SLOs**, and evaluate cost and rollback before resizing disks/VMs or changing cache modes.
