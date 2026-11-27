# Machine Families, Machine Types, and Custom Machine Configurations in Compute Engine

> **Chapter:** Compute Engine  
> **Lesson:** Machine Families, Machine Types, and Custom Machine Configurations  
> **Module:** CLOUD_PROVIDERS_GCP

In the **CLOUD_PROVIDERS_GCP** module, learners explore Google Cloud from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage, and databases. Through deployment scenarios, learners need to know how to choose services, protect resources, automate releases, and track reliability and cost. In Compute Engine, one decision that directly impacts all those goals is **selecting the virtual machine (VM) type**.

A Java application requiring lots of RAM with modest CPU differs from a scientific computing server needing strong CPU; an API with steady traffic differs from an interruptible batch job; an AI workload needing GPUs differs from a system requiring large SSD capacity and high IOPS. Choosing a machine type is not just "how many vCPUs and GB of RAM," but also involves **CPU architecture, network/disk performance, zonal availability, scalability, and lifecycle cost**.

This lesson focuses on **machine family**, **machine series**, **predefined machine type**, and **custom machine type**, with examples on the Google Cloud Console and Google Cloud CLI (`gcloud`). All project names, VMs, and load numbers in this lesson are hypothetical; verify regional/zonal availability and current documentation during actual deployments.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Explain the hierarchy **machine family → machine series → machine type → instance**.
2. Distinguish optimization targets: **general-purpose/cost-optimized**, **compute-optimized**, **memory-optimized**, **storage-optimized**, **accelerator-optimized**, and network-oriented series.
3. Read machine type names like `e2-standard-4`, `n2-highmem-8`, and `e2-custom-4-12288`, understanding vCPU/RAM specifications without wrongly assuming all series share the same ratio.
4. Choose between **predefined** and **custom** based on measured demand, hardware limits, and cost.
5. Recognize custom machine type constraints: supported series, valid vCPU counts, min/max RAM, increment steps, and **extended memory**.
6. Use the CLI to list/inspect machine types, create test VMs, and change machine types following proper procedures.
7. Evaluate CPU architecture, boot image, disk, networking, GPU, quotas, zonal capacity, software licensing, and security choices.
8. Design **right-sizing** experiments, evaluating reliability, availability, and total cost before applying to production.

## 2. Four Commonly Confused Naming Levels

| Level | Meaning | Illustrative Examples |
|---|---|---|
| **Machine family** | Grouping oriented around workload type and performance goals | General-purpose, memory-optimized, accelerator-optimized |
| **Machine series** | A specific hardware/configuration line within a family | E2, N2, N2D, N4, C4, M4, G4 |
| **Machine type** | Specific CPU/RAM combination and resource profile within a series | `e2-standard-4`, `n2-highmem-8` |
| **VM instance** | A running or provisioned virtual machine in a project and zone | `orders-api-01` running type `e2-standard-4` |

A **machine series** may support many predefined types; some series also support **custom machine types**. A series name alone is not a complete VM configuration.

~~~mermaid
flowchart TD
    F["Machine families<br/>By workload objective"]
    F --> G["General-purpose"]
    F --> C["Compute-optimized"]
    F --> M["Memory-optimized"]
    F --> A["Accelerator-optimized"]
    F --> S["Storage-optimized"]
    G --> E2["Series E2"]
    G --> N2["Series N2"]
    G --> N4["Series N4"]
    E2 --> P["Predefined: e2-standard-4"]
    E2 --> U["Custom: e2-custom-4-12288"]
    P --> VM1["VM instance: web-01"]
    U --> VM2["VM instance: worker-01"]
~~~

The diagram focuses on the **hierarchy principle** and shows only a subset of the catalog; Google Cloud regularly adds or updates series, generations, and zonal availability.

### 2.1. Machine Family Does Not Equal CPU Vendor

Series may use Intel, AMD, or Google-designed/co-designed Arm CPUs depending on the generation. For example:

- `N2` is typically Intel x86; `N2D` is AMD x86.
- `N4` and `N4D` have different underlying platforms; `N4A` uses Arm-based Google Axion.
- `C4A` and `T2A` are also Arm examples across different generations and segments.
- Some GPU-optimized series pair with different CPUs depending on the series and configuration.

**Do not infer the ISA from a single letter in the name.** Always check the **architecture (`x86_64` or `arm64`)**, CPU platform, and image/software support for the series you plan to use.

### 2.2. A vCPU Is Not Necessarily an Independent Physical Core

In many x86 VMs, one **vCPU** corresponds to one hardware thread; the ratio to physical cores depends on the platform and the series' SMT policy. Actual performance also depends on clock speed, microarchitecture, cache, NUMA, overcommit, or CPU sharing models. A `4 vCPU` VM in series A cannot be assumed to deliver the same throughput as a `4 vCPU` VM in series B.

In particular, **shared-core** VMs provide shared/burst CPU capacity specific to the machine type, which differs from how a standard dedicated-vCPU VM is evaluated.

## 3. Workload Categories and Machine Families

Below is a view organized by **design goal**. Series names and classifications may evolve across generations; check Google Cloud's comparison tables when selecting SKUs.

| Family / Orientation | Typically Suited Workloads | Example Series | Key Trade-offs |
|---|---|---|---|
| **General-purpose** | Web/APIs, typical Java apps, middleware, dev/test, versatile services | E2, N2/N2D, N4/N4D/N4A, some C3/C4 lines | Balanced CPU, RAM, network, and price; significant differences across generations |
| **Cost-optimized / economical** | Light loads, low CPU demand, lab/practice apps | E2, E2 shared-core | Low cost for suitable tasks; must verify steady/burst performance |
| **Compute-optimized** | High CPU loads, technical computing, throughput-oriented HPC | C2/C2D, H3/H4D depending on features | High CPU performance; RAM ratios, network, and hardware vary by series |
| **Memory-optimized** | In-memory databases, large caches, SAP/high-RAM applications | M1/M2/M3/M4, newer specialized series | High RAM cost, less flexibility; software/zonal constraints |
| **Storage-optimized** | High random I/O, hot datasets, systems relying on local disks | Z3 and specialized Z-series | Abundant local storage; requires durable data/replication strategy |
| **Accelerator-optimized** | ML training/inference, rendering, or GPU tasks | G2/G4, A2/A3/A4 and newly supported series | GPU/VRAM, drivers, quotas, capacity, and high cost |
| **Network-optimized / specialized networking** | Data planes requiring high network throughput/low latency | C4N, specialized memory/network lines | Topology, deployment region, and pricing constraints |

**Note:** Despite sharing the letter "C", **C2** and **C4** may appear in different groups in newer-generation tables. Start from your **workload profile and official specs**, rather than permanently labeling the entire C-letter family as compute-optimized.

### 3.1. General-Purpose: Starting Point for Most Systems

Without benchmarks yet, general-purpose is usually the sensible place to start:

- **E2:** cost-efficiency oriented; fits dev/test, small web services, or moderate loads once latency/performance is verified.
- **N2/N2D:** x86-based general-purpose, supporting predefined and custom types within specific limits.
- **N4/N4D/N4A:** newer general-purpose generation; when choosing, check CPU vendor/architecture, series availability, and machine image ecosystem.
- **T2A/T2D:** Tau lines targeting specific CPUs/ISAs, suitable when workloads run on the respective hardware; do not assume all custom options are available.

For example, a Java REST API at 250 requests/second does not automatically "need C4 because of high request count." If actual CPU is only 25%, RAM is 70%, and wait time is mostly in Cloud SQL, simply adding CPU may not improve p95 latency.

### 3.2. Compute-Optimized

When an application is **CPU-bound** and measurably benefits from higher single-threaded or multi-threaded compute power, evaluate compute-optimized options such as C2/C2D or HPC series per current capabilities.

Examples: image-processing batch jobs, scientific simulations, heavy compilation, or continuous numerical computation. Check:

- **Single-thread** and **multi-thread** performance.
- Memory/cache per vCPU, NUMA characteristics, RAM bandwidth.
- Available instance sizes in the target zone.
- **Processing time per unit of work**, rather than CPU utilization alone.

### 3.3. Memory-Optimized

Use when RAM is the primary bottleneck, such as in-memory databases, large-scale analytics, or applications licensed per core that require high memory. Before choosing a large M-series machine:

1. Verify actual working set, page faults, swap usage, and application caching behavior.
2. Check whether query/index tuning, data partitioning, or a caching tier can solve it.
3. Compare **custom with extended memory** on supported N-series against **predefined memory-optimized** if cost and sizing allow.
4. Verify software licensing constraints, OS image support, zonal availability, and HA plans.

More RAM **does not replace** database backup, replication, and recovery strategies.

### 3.4. Accelerator-Optimized

ML workloads may require GPUs to hit target throughput or latency. G/A lines support dedicated combinations of CPU, RAM, GPU, and local storage; in many cases, **the GPU count is a fixed property of the machine type**.

Before choosing:

- What GPU model, how much **VRAM**, compute precision, and CUDA/driver toolkit are needed?
- Is it training, online inference, or interruptible batch?
- Is high-speed networking across multiple GPU nodes required?
- Are quotas and capacity available in the planned zone?
- Can **Vertex AI** or managed services reduce operational overhead?

Do not assume GPUs can be attached to any machine type. Accelerator families have distinct configuration rules; even N1 with attached GPUs and custom G2 follow separate rules.

### 3.5. Storage-Optimized and Local SSD Limitations

Storage-optimized lines can deliver large local storage capacity/performance, fitting databases or pipelines with high IOPS demands. However, **Local SSDs** should not be treated as the sole durable copy. Data can be lost during stop/delete/recreation events or lifecycle transitions per product behavior.

For non-disposable data, design appropriate **Persistent Disk/Hyperdisk**, replication, snapshots, and backups. Bandwidth/IOPS are also capped by both the **machine type** and the disk type/size/configuration; buying a high-speed disk does not mean every VM can saturate the disk's maximum specs.

## 4. Reading Predefined Machine Types

### 4.1. Common Naming Convention

Many machine series follow the pattern:

~~~text
<series>-<ratio/profile>-<vCPU count>
~~~

Examples:

| Machine Type | Interpretation | Notes |
|---|---|---|
| `e2-standard-2` | E2 series, standard profile, 2 vCPUs | RAM follows E2 standard profile |
| `e2-standard-4` | E2, standard, 4 vCPUs | General-purpose example |
| `n2-highmem-8` | N2, high RAM-to-vCPU ratio, 8 vCPUs | Suited for memory-heavy workloads |
| `n2-highcpu-8` | N2, low RAM-to-vCPU ratio, 8 vCPUs | Must check actual RAM size |
| `e2-micro` | Small E2 shared-core | Do not read `micro` as a fixed vCPU count |

Many newer series use different naming conventions, including suffixes for CPU variants, local SSDs, GPUs, or specialized configurations. **Always use `gcloud compute machine-types describe` or official documentation to read exact `guestCpus` and `memoryMb`**, rather than guessing from an unfamiliar series name.

### 4.2. Standard, Highmem, and Highcpu Represent Different Ratios

Compared to a `standard` machine with the same vCPU count:

- `highmem` typically has **more RAM per vCPU**.
- `highcpu` typically has **less RAM per vCPU**.
- `standard` typically selects the series' balanced ratio.

However, exact ratios **vary by series and generation**. Never use `n2-highmem` ratios to infer the RAM of `c4-highmem`.

### 4.3. When Is Predefined Appropriate?

**Advantages:**

- Predefined shapes are easy to standardize across instance templates, managed instance groups (MIGs), and runbooks.
- Convenient for comparing prices and resource limits.
- Fits well when the vCPU/RAM ratio closely matches actual workload needs.

**Limitations:**

- May over-provision RAM or vCPU if your application needs a different ratio than the profile.
- Stepping up to a larger type often increases both CPU and RAM even when only one resource is lacking.
- Specific configurations may not be available in all zones or may lack capacity.

Do not pick custom just to "optimize" a minor discrepancy; first weigh the cost and maintenance risk of non-standard configurations.

## 5. Custom Machine Types: Why and When to Use Them?

A **custom machine type** lets you choose vCPU count and RAM size within the **series' allowed limits**, instead of picking a fixed-ratio predefined profile.

Suppose a Java application has:

- Typical CPU at 30–45%, peaking at 75% on a 4-vCPU machine.
- Steady RAM usage around 9–10 GiB, targeting 12 GiB.
- Closest predefined profiles offer too much RAM or mismatch the required ratio.

One candidate is:

~~~text
e2-custom-4-12288
│  │      │ └── 12,288 MB (12 GiB in Compute Engine convention)
│  │      └──── 4 vCPUs
│  └─────────── custom machine type
└────────────── E2 machine series
~~~

This is a **valid configuration under current E2 limits**: 4 vCPUs, 12 GiB RAM, equaling 3 GiB/vCPU with MB divisible by 256. However, **valid does not equal optimal**. Compare it against predefined `e2-standard-4`, `e2-highmem-4`, and other series in terms of real price/performance.

### 5.1. Not Every Series Supports Custom

Current Compute Engine documentation lists general-purpose custom support on specific series:

| Machine Series | Custom General-Purpose? | Key Takeaways |
|---|---|---|
| **E2** | Yes | Named `e2-custom-*`, no extended memory |
| **N1** | Yes | Custom names start with `custom-*`, without an `n1-` prefix |
| **N2 / N2D** | Yes | vCPU/RAM limits per series; supports extended memory |
| **N4 / N4D / N4A** | Yes | Varying vCPU count limits; supports extended memory |
| **G2** | Yes, under special GPU rules | vCPU/RAM options depend on GPU count; not like standard N-series custom |
| **Other series** | Do not assume support | Check the official custom types list at deployment time |

**Warning:** `N4A`/Arm and `N4D`/AMD do not share the exact same list of valid vCPU counts merely because both start with `N4`.

### 5.2. Examples of vCPU/RAM Constraints

The table below illustrates how to read official limits; **re-verify at deployment time** because series specifications can change.

| Series | Example Supported Custom vCPU Counts | Standard RAM per vCPU (Illustrative Limits) | Extended Memory |
|---|---|---|---|
| **E2** | 2, 4, …, 32 | 0.5–8 GiB/vCPU | No |
| **N2** | 2–32 in increments of 2; larger counts per supported steps | 0.5–8 GiB/vCPU | Yes |
| **N2D** | 2, 4, 8, 16, 32, 48, 64, 80, 96 | 0.5–8 GiB/vCPU | Yes |
| **N4** | 2–80, multiples of 2 | 2–8 GiB/vCPU | Yes |
| **N4D** | 2, 4, 8, 16, 32, 48, 64, 80, 96 | 0.5–8 GiB/vCPU | Yes |
| **N4A** | 1–64, depending on allowed configurations | 2–8 GiB/vCPU | Yes |
| **N1** | 1 or suitable even numbers, up to 96 | N1-specific ratios | Yes |

Check **maximum vCPUs, vCPU increment step, RAM per vCPU, maximum total RAM, and RAM increment in MB**. For many general-purpose custom series, RAM is selected in **256 MB** increments in the machine type string.

**Unit conversion in CLI:** in Compute Engine documentation, machine type names historically use `MB`/`GB` labels, where in standard examples **1 GB = 1,024 MB**; for instance, `12 GiB = 12,288 MB`. Do not pass decimal 12 GB = 12,000 MB into a custom string expecting it to be valid.

### 5.3. Extended Memory

When an application needs more RAM than the series' standard maximum ratio per vCPU, some custom types offer **extended memory**.

Example:

~~~text
n2-custom-2-20480-ext
│  │      │  │     └── extends RAM per series limits
│  │      │  └──────── 20 GiB (20,480 MB)
│  │      └─────────── 2 vCPUs
│  └────────────────── custom
└───────────────────── N2
~~~

With a standard ceiling of `8 GiB/vCPU`, 2 vCPUs cap at `16 GiB`; 20 GiB exceeds that cap and thus requires the `-ext` suffix. Extended memory carries an **extra rate/surcharge** and separate discounting rules. Many predefined types, E2 custom, and G2 custom **do not** support extended memory.

For workloads bound by **per-vCPU software licensing** (such as certain commercial licenses), extended memory can be beneficial by keeping vCPU count low while increasing RAM; however, factor in license rules, memory surcharge, and performance.

### 5.4. Custom Does Not Mean Arbitrary Hardware Selection

Custom machine types **only solve a specific set of configurable hardware parameters**. They do not let you arbitrarily choose:

- Any CPU vendor/model/ISA regardless of series.
- Arbitrary GPU counts or custom VRAM sizes.
- Arbitrary Local SSD capacities and network interfaces.
- Disk types, networking queues, or throughput exceeding the machine series' limits.
- Regions/zones lacking the underlying hardware.
- Arbitrary combinations of OS image, architecture, and CPU platform.

Even a custom type that is valid in vCPU and RAM can still **fail to create a VM** due to quotas, capacity, organization policies, incompatible images, or disk/GPU configuration errors.

## 6. Workload-Driven Machine Type Selection Process

### 6.1. Questions to Ask Before Selecting a SKU

1. **What is the workload?** Java API, batch job, database, cache, GPU rendering, or HPC?
2. **What are the hard constraints?** CPU architecture, kernel/drivers, licensing, GPU/Local SSD, memory footprint, p99 latency?
3. **What are average and peak loads?** CPU, RAM, QPS, request concurrency, disk IOPS, disk throughput, network throughput?
4. **Can it scale horizontally?** Multiple VMs with MIG, load balancer, and autoscaling, or does it require one large machine?
5. **What are the operational constraints?** Zones, backups, SLOs, RTO/RPO, failover, maintenance?
6. **What cost model is acceptable?** On-demand, commitments, Spot for batch, plus disk/network/license costs?

### 6.2. Candidate Selection Matrix

| Hypothetical Workload | Key Characteristics | Initial Selection | What to Verify |
|---|---|---|---|
| Typical Java REST API | Balanced CPU/RAM, stateless | E2/N2/N4 predefined | p95/p99 latency, heap/GC, Cloud SQL connection pool |
| Large-heap Java worker | 4 vCPUs enough, short on RAM | Highmem or suitable N/E custom | OOMs, GC pauses, actual RAM consumption |
| CPU-bound data processing | Sustained high CPU, moderate RAM | Compute-optimized or newer general-purpose | Throughput per unit cost |
| In-memory cache | Very large RAM, low latency | Memory-optimized or custom extended memory | RAM consumption, HA, data durability |
| Non-time-critical batch | Can checkpoint/retry | Mainstream series + Spot VM | Preemption, idempotency, local data loss |
| ML inference | Needs GPU/VRAM per model | G/A accelerator series or Vertex AI | VRAM, GPU utilization, cold start time |
| High-IOPS database | I/O bound, latency sensitive | Series with suitable disk throughput | Hyperdisk/PD, replication, IOPS bottlenecks |
| Legacy x86 system | App/driver/license x86-only | Compatible Intel/AMD series | Image, kernel, drivers, licensing |
| Containerized microservice | Suitable for serverless | Compare Cloud Run vs. VM | Ops overhead, scaling speed, workload limits |

**Remember:** simply saying "runs Java" is not enough to pick a machine series. Java is cross-platform, but native libraries, JDK distributions, container images, and agents can be architecture-dependent. A Java workload using x86_64-only JNI binaries will not run natively on Arm.

### 6.3. Reading Metrics for Right-Sizing

| Metric | Signal | Selection Impact |
|---|---|---|
| Average and p95 CPU utilization | Sustained high CPU, long queues | Increase CPU, switch to faster CPU series, or scale horizontally |
| Memory used, page faults, swap, OOM | RAM shortage or high memory pressure | Increase RAM, use highmem/custom, tune heap |
| Disk IOPS/throughput/latency | Disk is the bottleneck while CPU is low | Review disk type and machine-type throughput caps |
| Network throughput/packet loss | NIC or route bottleneck | Select appropriate series/network tier; optimize architecture |
| p95/p99 application latency | Users impacted despite low average CPU | Inspect GC, DB, lock contention, cache, cold starts |
| Requests/concurrency and peak hours | Short but sharp traffic spikes | MIG/autoscaling or managed services |
| Uptime and idle time | VM running with no workload | Dev/test shutdown schedules, Spot for batch, or serverless |

**Cloud Monitoring** provides baseline infrastructure metrics; detailed RAM, process/JVM, and disk metrics may require the **Ops Agent** or application-emitted metrics. Without RAM metrics, never conclude a VM is over- or under-provisioned on memory from a CPU chart alone.

### 6.4. Benchmarking Under Controlled Conditions

A valid comparison should hold constant:

- Source code, JDK/container version, dataset, request pattern, and read/write ratio.
- Database tier, connection pool size, network latency, OS image, and region.
- Disk type, disk size, and IOPS/throughput settings when evaluating CPU.
- JVM warm-up procedure, test duration, and sustained load long enough to surface GC/swap effects.
- Target SLO, e.g., p95 latency under 200 ms at 500 RPS, rather than raw total requests alone.

Compare at least **2–3 candidates**: a smaller predefined type, a right-sized predefined type, and a custom or alternative series. Across different CPU architectures, rebuild and retest all native dependencies.

## 7. Inspecting Machine Types in the Google Cloud Console

In the Google Cloud Console, select the target project and go to **Compute Engine → VM instances → Create instance**.

### 7.1. Configuration Steps

1. Confirm **project ID**, **region**, and **zone**.
2. Under **Machine configuration**, select the family and series matching your workload.
3. Choose a predefined **machine type** or `Custom` if supported by the series.
4. For custom, enter vCPU count and RAM; the Console usually shows valid limits and estimated pricing.
5. Verify x86/Arm architecture, OS image, disk, and network settings.
6. Select a least-privilege **service account** and configure access scopes/identity appropriately.
7. Choose the subnet, internal/external IP, and firewall ingress according to environment policies.
8. Review **estimated cost**, quota/capacity, and billing configuration.
9. In a sandbox, only create the VM if authorized and budgeted; verify and clean up resources afterward.

**Do not enable an external IP or open SSH/HTTP to the Internet by default** just to test a machine type. Use VMs without external IPs, IAP/OS Login, and Cloud NAT where appropriate. Remember that VMs, disks, IPs, and logs can incur charges even during short tests.

## 8. Exploring Configurations with the Google Cloud CLI

The commands below are **read-only** and can be run in Cloud Shell or an environment configured with `gcloud`:

~~~bash
# Verify active identity and default project.
gcloud auth list
gcloud config get-value project

# List actual machine types available in an authorized zone.
gcloud compute machine-types list \
  --project=PROJECT_ID \
  --zones=asia-southeast1-a

# Inspect a predefined machine type.
gcloud compute machine-types describe e2-standard-4 \
  --project=PROJECT_ID \
  --zone=asia-southeast1-a \
  --format="yaml(name,guestCpus,memoryMb,description)"

# List existing VMs and their machine types.
gcloud compute instances list \
  --project=PROJECT_ID \
  --format="table(name,zone,machineType,status)"
~~~

Replace `PROJECT_ID` with an authorized sandbox project. `asia-southeast1-a` is an illustrative zone; **do not assume every series has sufficient capacity in this zone**. If a type does not appear in the list, check the zone, series, and permissions, and consult documentation or machine family comparison tables when needed.

### 8.1. Interpreting `describe` Output

Suppose the output shows:

~~~yaml
name: e2-standard-4
guestCpus: 4
memoryMb: 16384
~~~

This illustrates how to read **4 vCPUs and 16,384 MB (16 GiB)**, not a guarantee that every `standard-4` type always has 16 GiB. You can also query other attributes regarding memory, architecture, and series configuration via the CLI if exposed by the API.

## 9. Creating Predefined and Custom VMs in a Sandbox

**The commands in this section modify cloud resources and may incur charges.** They are for illustration and should only be run in authorized projects. Actual execution requires the Compute Engine API enabled, valid billing, necessary IAM permissions, zonal quota/capacity, and appropriate VPC/subnet and images.

### 9.1. Predefined Type Creation Example

~~~bash
gcloud compute instances create lab-predefined \
  --project=PROJECT_ID \
  --zone=asia-southeast1-a \
  --machine-type=e2-standard-4 \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --boot-disk-size=30GB \
  --subnet=SUBNET_NAME \
  --no-address
~~~

`--no-address` demonstrates a VM **without an external IPv4 address**. VM administration still requires IAM and secure access paths (e.g., IAP/OS Login per configuration); a VM without a public IP may be unable to install packages from the Internet without appropriate outbound routing.

### 9.2. Custom E2 Creation Example: 4 vCPUs, 12 GiB RAM

~~~bash
gcloud compute instances create lab-custom \
  --project=PROJECT_ID \
  --zone=asia-southeast1-a \
  --machine-type=e2-custom-4-12288 \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --boot-disk-size=30GB \
  --subnet=SUBNET_NAME \
  --no-address
~~~

Format:

~~~text
e2-custom-<NUMBER_OF_VCPUS>-<MEMORY_MB>
~~~

The value `12288` is 12 × 1024 MB; a ratio of 3 GiB RAM/vCPU sits within typical E2 custom limits. If changed to an out-of-bounds ratio, the API rejects the request before the VM runs.

### 9.3. Using `--custom-cpu` / `--custom-memory` Flags

The same configuration can be expressed as:

~~~bash
gcloud compute instances create lab-custom-alt \
  --project=PROJECT_ID \
  --zone=asia-southeast1-a \
  --custom-cpu=4 \
  --custom-memory=12GB \
  --custom-vm-type=e2 \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --subnet=SUBNET_NAME \
  --no-address
~~~

By Compute Engine convention, `12GB` in the custom CLI flag context corresponds to approximately 12 GiB. **Do not** combine `--machine-type` with custom flags on the same VM without checking CLI rules.

### 9.4. N2 Extended Memory Example

~~~bash
# Illustrative syntax; run only where zone/capacity permits.
gcloud compute instances create lab-extmem \
  --project=PROJECT_ID \
  --zone=ZONE \
  --machine-type=n2-custom-2-20480-ext \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --subnet=SUBNET_NAME \
  --no-address
~~~

Two N2 vCPUs with 20 GiB RAM is an example of **extended memory**. Memory exceeding the standard ratio has its own pricing and discount rules; verify pricing details before provisioning.

### 9.5. Inspecting the Created Instance

~~~bash
gcloud compute instances describe lab-custom \
  --project=PROJECT_ID \
  --zone=asia-southeast1-a \
  --format="yaml(name,machineType,status,disks,networkInterfaces)"
~~~

When working with real lab resources, tear down the VM and check for remaining **disks, static IPs, snapshots, and reservations** once no longer needed. Deleting a VM does not automatically guarantee all related resources are deleted or stop billing.

## 10. Changing the Machine Type of an Existing VM

### 10.1. Resizing Is Not a Default Live Operation

For many standard VMs, you must **stop the VM to `TERMINATED`**, change the machine type, and start it again. Ensure you have a **maintenance window**, appropriate backups/snapshots, and a rollback plan.

~~~mermaid
flowchart LR
    A["Measure and decide to resize"] --> B["Check support, quota, capacity, disk, snapshot"]
    B --> C["Stop VM (TERMINATED)"]
    C --> D["set-machine-type"]
    D --> E["Start VM"]
    E --> F["Smoke test + benchmark"]
    F --> G{"Meets SLO?"}
    G -->|Yes| H["Monitor, update docs and cost"]
    G -->|No| I["Roll back or move workload per approved plan"]
~~~

Illustrative commands:

~~~bash
# 1. Disruptive step: stop the VM.
gcloud compute instances stop VM_NAME \
  --project=PROJECT_ID \
  --zone=ZONE

# 2. Only while stopped and when the transition is supported.
gcloud compute instances set-machine-type VM_NAME \
  --project=PROJECT_ID \
  --zone=ZONE \
  --machine-type=e2-custom-4-12288

# 3. Start and verify.
gcloud compute instances start VM_NAME \
  --project=PROJECT_ID \
  --zone=ZONE
~~~

**Never run these commands directly in production before assessing constraints.** Certain configurations **do not support in-place changes**, such as instances with Local SSDs, VMs inside a MIG, bare metal, cross-generation/certain architecture shifts, accelerator-specific types, or network interface changes; in those cases, you may need to **create a new VM / migrate the workload**. Google Cloud provides dedicated guides for changing generations, switching CPU architectures, and adjusting GPUs.

### 10.2. Common Resize Pitfalls

| Change / State | Risk | Mitigation |
|---|---|---|
| Stopping a VM handling live orders | Downtime if no redundant replica exists | Use MIG/load balancer or planned maintenance window |
| New machine type lacks zonal capacity | VM may fail to restart as expected | Check zone, quotas, reservations, and rollback plan |
| Using an **ephemeral external IP** | IP may change on stop/start | If a fixed IP is needed, reserve a static IP and update DNS/configs |
| Attached **Local SSD** | Data loss risk and usually unsupported for direct resize | Back up/migrate per dedicated documentation |
| VM inside a **Managed Instance Group** | MIG may recreate the VM, overwriting manual edits | Update the **instance template** and perform a MIG rolling update |
| Switching x86 ↔ Arm | Images, binaries, agents, and drivers may fail to run | Build/test and migrate to a new VM as required |
| Unsupported in-place generation upgrade | `set-machine-type` fails or is unavailable | Move workload to a new VM per official guidance |
| Imbalanced RAM/vCPU change | OOMs, GC pauses, throttling, degraded throughput | Benchmark beforehand and monitor afterward |
| Stopping VM to cut costs | Disks, IPs/reservations, and ancillary resources still bill | Check Cloud Billing by SKU |

**Persistent Disks/Hyperdisks** retain data across normal VM stop operations, but do not replace backups/snapshots. Do not rely solely on restarting when recovering from accidental data deletion or application bugs.

## 11. Quotas, Capacity, Regions/Zones, and Compatibility

### 11.1. Quota Is Not Capacity

- **Quota:** the resource limit a project/region is permitted to consume. Can be requested to increase for valid business needs.
- **Capacity:** the physical hardware **actually available** in a zone when creating/starting a VM. Remaining quota **does not guarantee** sufficient capacity.
- **Availability:** a machine series may be supported in a region, but not in every zone or configuration variant.
- **Reservation:** a tool to reserve capacity for eligible configurations where supported; carries its own pricing, constraints, and consumption rules.

For instance, when deploying 30 large VMs in one zone, even with 100 vCPUs of remaining quota, the request can still fail due to lack of zonal capacity. For mission-critical workloads, distribute across zones, evaluate reservations, and maintain recovery plans.

### 11.2. CPU Architecture and the Software Ecosystem

| Requirement | How to Verify |
|---|---|
| OS image | Is an image compatible with the series/ISA and drivers available? |
| Container image | Are matching `linux/amd64` or `linux/arm64` images built? |
| JDK/JVM | Do the JDK distribution and native components support the target architecture? |
| JNI/native libraries | Can they compile for the target architecture? |
| Monitoring/security agents | Are Ops Agent, EDR, backup agents, and plugins supported? |
| Licensing | How is it billed per vCPU/socket/architecture? |
| Network/disk | What are the throughput and feature limits for the specific machine series? |

**Never switch from N2 x86 to N4A Arm simply by changing the machine type name** without testing the application. Switching architectures typically requires new images, build pipelines for the new ISA, and a documented migration process.

### 11.3. Do Not Confuse Machine Type with Other Resources

A VM also depends on:

- **Boot disk** and data disks: Persistent Disk/Hyperdisk/Local SSD with distinct characteristics.
- **VPC network, subnet, internal/external IP, firewall, routes, Cloud NAT:** determine connectivity.
- **Service account, IAM, OS Login, Shielded VM, Secure Boot** as supported: determine identity and security posture.
- **Managed instance group (MIG), load balancer, health checks:** scalability and reliability.
- **Cloud Monitoring/Logging/Ops Agent:** resource and application observability.

Picking the right machine type while missing a database route, IAM permission, or firewall rule will still break the system.

## 12. Cost: Optimizing for Outcomes and Total Cost of Ownership

### 12.1. Sources of Compute Engine Cost

| Component | How Cost Is Driven | Notes |
|---|---|---|
| Predefined VM | Machine series/type, runtime duration, provisioning model | Pricing varies by zone/region and licenses |
| Custom VM | Custom vCPUs, RAM, and runtime duration | Includes a **custom premium**; verify current pricing |
| Extended memory | RAM beyond the series' standard ratio | Carries a surcharge and separate discount rules |
| Disks / snapshots | Type, capacity, IOPS/throughput per product | Can still bill while the VM is stopped |
| Network / IP / Load Balancer | Egress, external IPs, NAT, LB per configuration | Not included inside vCPU pricing |
| Licensing | OS and commercial software | Must account for vCPU/VM/architecture rules |
| Logging, monitoring, backups | Data ingestion/retention, snapshots, operations | Configure appropriate budgets and alerts |
| Operations / reliability | Engineering effort for patching, HA, backups, incidents | Lowest unit price does not equal lowest TCO |

According to current custom configuration documentation, custom machine types carry an **on-demand premium** compared to equivalent predefined types; **do not assume custom is always cheaper** merely because it uses less RAM. Exact prices and discounts can change; use the **Google Cloud Pricing Calculator** and regional/term quotes.

### 12.2. SUD, CUD, and Spot

- **Sustained use discounts (SUD):** automatically applied to **eligible series/resources**, not all newer-generation VMs or all GPUs.
- **Committed use discounts (CUD):** commitments to resource usage or spend under specific program terms; coverage differs across series, custom types, and extended memory.
- **Spot VMs:** substantial savings for workloads tolerant of preemption at any time; should implement retries, checkpoints, queues, and resilience.
- **Reservations:** address capacity risk for critical configurations with distinct billing; do not confuse them with discount commitments.
- **Scheduling:** dev/test VMs can be stopped when idle, though disk/IP and related resource fees continue.

**Do not arbitrarily stack discounts.** Eligibility conditions, SKU types, commitments, and provisioning models can be mutually exclusive.

### 12.3. Cost Comparison Example Without Fabricated Unit Prices

Suppose a Java API runs on `e2-highmem-4` but actually needs only 12 GiB of RAM. Options:

| Option | Assumptions | What to Measure |
|---|---|---|
| Keep predefined highmem | No machine changes needed; excess RAM capacity | Current TCO, p95 latency, discount eligibility |
| Switch to `e2-custom-4-12288` | Reduces allocated RAM; incurs custom premium | Actual custom cost, resize downtime, JVM performance |
| Move to a newer compatible series | Potentially better price/performance | Architecture, code compatibility, zone, disk/network, migration |

Evaluation formula:

~~~text
Total monthly cost ≈
  VM compute cost (vCPU/RAM, duration, pricing model)
+ Disk, snapshot, and backup cost
+ Network egress/NAT/IP/load balancer cost
+ Logging/monitoring/licensing cost
+ Operational effort and downtime risk
- Eligible discounts actually applied
~~~

Compare properly using **cost per 1,000 requests meeting SLO**, **cost per successful job**, or **cost per GB processed**, rather than looking solely at hourly VM price.

## 13. Case Study: Selecting a VM for a Java Orders API

### 13.1. Context

A development team deploys a Java API on Compute Engine backed by Cloud SQL PostgreSQL, order images in Cloud Storage, and Pub/Sub for events. The API runs statelessly behind a load balancer and requires **p95 latency under 200 ms** at tested peak load. Infrastructure is managed across projects, IAM, VPC, pipelines, and Cloud Monitoring.

Hypothetical metrics observed under realistic load:

| Metric | Hypothetical Result |
|---|---|
| Current VM | `e2-standard-8` |
| Average / peak CPU | 20% / 46% |
| Typical RAM usage | 10–11 GiB |
| JVM heap | 8 GiB |
| p95 latency | 150 ms |
| Critical data | Cloud SQL and Cloud Storage; nothing stored on local disk |
| Traffic | ~3x peak spikes during promotional campaigns |

### 13.2. Candidates and Hypotheses

- **A: `e2-standard-8`:** keep configuration, minimal change, though CPU is underutilized.
- **B: `e2-custom-4-12288`:** test halving vCPUs to 4 while keeping 12 GiB RAM to evaluate cost efficiency.
- **C: `n2-highmem-4` or a compatible newer series:** compare latency/throughput and post-discount cost.

Do not jump straight to B: the prior peak CPU was 46% of **8 vCPUs**; dropping to 4 vCPUs could push CPU near saturation, altering GC times and p99 latency. Run **load tests** covering bursts, warm-up, MIG load distribution, and Cloud SQL failure modes.

### 13.3. Safe Rollout Plan

~~~mermaid
flowchart LR
    U["Users"] --> LB["HTTP(S) Load Balancer"]
    LB --> MIG["Managed Instance Group<br/>Orders API instances"]
    MIG --> SQL["Cloud SQL: PostgreSQL"]
    MIG --> OBJ["Cloud Storage"]
    MIG --> PUB["Pub/Sub"]
    MON["Cloud Monitoring/Logging"] -. "Metrics and logs" .-> MIG
    CICD["CI/CD + Instance Template"] --> MIG
~~~

1. Create a **new instance template** with the candidate machine type.
2. Spin up a test or canary group in a sandbox/isolated group with matching application configuration.
3. Benchmark CPU, heap/GC, Cloud SQL connections, p95/p99 latency, failover, and network throughput.
4. If results pass, perform a **rolling update** on the MIG under safe rollout policies; never manually edit individual VMs inside a MIG.
5. Monitor errors, timeouts, latency, and SKU-level costs over at least one representative load cycle.
6. If SLOs degrade or capacity is insufficient, roll back to the verified template.

For systems that can be containerized, also **compare Cloud Run or GKE** at the architectural level, though switching platforms is a separate decision requiring evaluation of features, operational effort, security, and total cost.

## 14. Common Issues When Selecting or Changing Machine Types

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `Invalid machine type` | Wrong series name, vCPU count, or RAM step/ratio | Cross-check custom docs and CLI `machine-types list` |
| Series missing in zone | Not yet supported or unavailable in that zone | Check other zones and architectural requirements |
| `ZONE_RESOURCE_POOL_EXHAUSTED` or capacity error | Insufficient available hardware | Try another zone/type, reservation, or adjust deployment plan |
| Quota exceeded | Insufficient project/region quota | Check quotas and request adjustment via proper process |
| VM fails to start after resize | New type lacks capacity or incompatible image/driver | Roll back to old type, inspect logs and migration options |
| New `-ext` type invalid | Series does not support extended memory or exceeds limits | Use supported N-series and a valid ratio |
| Java API slow despite low CPU | DB, GC, I/O, network, lock, or concurrency bottleneck | Check application tracing, heap, and Cloud SQL |
| Switched to Arm and containers fail to start | x86-only images or native dependencies | Build multi-arch/arm64 images and test |
| Resized a VM in MIG and config reverted | MIG manages instances via its template | Update the template and run a rolling update |
| Fast disk but low IOPS | Machine type caps throughput/IOPS | Check both machine and disk limits |
| VM stopped yet billing continues | Persistent disks, static IPs, snapshots, reservations | Inspect Cloud Billing by SKU |
| Chose Spot for critical API | VM preempted unexpectedly | Use standard VMs/proper HA, or reserve Spot for fault-tolerant loads |
| Expecting automatic vertical scaling | Changing vCPU/RAM usually requires a stop or template change | Design horizontal scaling/MIG if needed |

## 15. Practice Exercises and Self-Assessment Questions

### 15.1. Exercise A — Reading Machine Types

A company has three configurations:

~~~text
A: e2-standard-4
B: n2-highmem-8
C: e2-custom-4-12288
~~~

Determine:

1. Which configurations are predefined and which is custom?
2. How many vCPUs and GiB of RAM does C have?
3. Why can you not deduce B's exact RAM solely by multiplying E2 ratios?
4. Are A and C guaranteed identical performance running the same JDK version? Explain.
5. Which metrics must be collected before choosing C for production?

**Hint:** A/B are predefined, C is custom; C has 4 vCPUs and 12 GiB. Highmem ratios and CPU platforms depend on the series; compare workloads and metrics rather than inferring from names.

### 15.2. Exercise B — Selecting Types for Different Workloads

| System | Scenario | What to Propose |
|---|---|---|
| Web API | Moderate CPU, 12 GiB RAM, horizontally scalable | Which predefined? Which custom? Why? |
| Batch video | Retryable and not strictly deadline-critical | Which series, and is Spot suitable? |
| In-memory cache | Very large RAM, moderate CPU | Trade-offs among highmem/custom-ext/memory family? |
| AI inference | Model requires specific GPU/VRAM | Why choose A/G or Vertex AI over E2? |
| Legacy Java | Contains x86_64 JNI libraries | Can you switch straight to Arm? |
| SQL-heavy API | Low CPU, high p99 due to DB queries | Should you increase vCPUs before optimizing queries? |

State your **assumptions**, measurement approach, and factors that would alter your recommendation. There is no single fixed answer based solely on a series name.

### 15.3. Exercise C — Identifying Valid Custom Strings

Evaluate these hypothetical machine type strings:

1. `e2-custom-4-12288`
2. `e2-custom-3-12288`
3. `n2-custom-2-20480`
4. `n2-custom-2-20480-ext`
5. `n4-custom-4-16384`

**Verification hints per current documentation:**

- **(1)** Valid under typical E2 custom limits.
- **(2)** Invalid: E2 custom requires even vCPU counts under current limits.
- **(3)** Invalid for standard RAM because 20 GiB on 2 vCPUs exceeds the 8 GiB/vCPU cap.
- **(4)** Valid under N2 extended memory design, subject to other limits and zonal/capacity availability.
- **(5)** Valid in terms of the 4 vCPU / 16 GiB RAM ratio for N4, though zonal availability and creation-time support must still be checked.

### 15.4. Exercise D — Changing the Type of a Production VM

An order-processing VM uses `e2-standard-8`, has a Persistent Disk, an ephemeral external IPv4 address, and is managed by a MIG. The team wants to switch to `e2-custom-4-12288` to lower costs.

Answer:

1. Why should you avoid running `gcloud compute instances set-machine-type` directly on a VM in a MIG?
2. What steps must be prepared to update the instance template and run a rolling update?
3. What risks exist with the ephemeral external IP?
4. What must be verified before cutting vCPUs in half?
5. If the new type lacks capacity, how should rollback be prepared?
6. After rollout, which metrics should be tracked to confirm real cost savings?

**Hint:** Update the template/MIG via a rolling strategy with rollback capability; never manually modify MIG-managed VMs. Validate SLOs under real load; an instance-level ephemeral external IP is not a stable design behind a load balancer.

## 16. Production Machine Type Selection Checklist

- [ ] Distinguished between machine family, series, type, and instance.
- [ ] Identified whether the workload is CPU-bound, memory-bound, IO-bound, GPU-bound, or network/DB-bound.
- [ ] Measured CPU, RAM, disk, network, p95/p99 latency, and representative peak loads.
- [ ] Verified x86/Arm architecture, OS image, JDK, native libraries, agents, and licensing.
- [ ] Checked machine series **availability in the target zone** and estimated quotas/capacity.
- [ ] For custom types, verified **vCPU step, RAM ratio, memory increment, extended memory**, and pricing.
- [ ] Checked throughput/IOPS limits across both the machine type and Persistent Disk/Hyperdisk/Local SSD.
- [ ] Benchmarked 2–3 candidates and compared cost **per unit of work meeting SLO**.
- [ ] Distinguished predefined/custom options from Spot, SUD, CUD, and reservations.
- [ ] Secured the VM with IAM, least-privilege service account, VPC/firewalls, OS hardening, and patching.
- [ ] Prepared backups/snapshots, health checks, rollback, migration plans, or MIG rolling updates.
- [ ] Monitored Billing, logging, network egress, disks, and resources still billed when VMs stop.
- [ ] Selected a deployment approach matching reliability, cost, and the team's operational capacity.

## 17. Official Documentation and Verification Sources

Series catalogs, resource ratios, pricing, and resize support evolve across generations. Consult current Google Cloud documentation before provisioning real VMs:

- [Machine families resource and comparison guide](https://docs.cloud.google.com/compute/docs/machine-resource)
- [General-purpose machine family](https://docs.cloud.google.com/compute/docs/general-purpose-machines)
- [Compute-optimized machine family](https://docs.cloud.google.com/compute/docs/compute-optimized-machines)
- [Memory-optimized machine family](https://docs.cloud.google.com/compute/docs/memory-optimized-machines)
- [Accelerator-optimized machine family](https://docs.cloud.google.com/compute/docs/accelerator-optimized-machines)
- [Create a VM with a custom machine type](https://docs.cloud.google.com/compute/docs/instances/creating-instance-with-custom-machine-type)
- [Edit the machine type of a compute instance](https://docs.cloud.google.com/compute/docs/instances/changing-machine-type-of-stopped-instance)
- [Troubleshoot resource availability errors](https://docs.cloud.google.com/compute/docs/troubleshooting/troubleshooting-resource-availability)
- [Spot VMs](https://docs.cloud.google.com/compute/docs/instances/spot)
- [Sustained use discounts](https://docs.cloud.google.com/compute/docs/sustained-use-discounts)
- [Compute Engine instance pricing](https://cloud.google.com/compute/vm-instance-pricing)
- [Google Cloud Pricing Calculator](https://cloud.google.com/products/calculator)

**Key Takeaway:** Start from your **actual workload and SLO**, pick the **family** based on the bottleneck, choose the **series** for architecture/feature support, and then select a **predefined or custom machine type** to balance vCPU–RAM–IO with cost. A valid custom type is not automatically cheaper or faster. A sound choice is only confirmed when **benchmarks, quotas/capacity, operability, security, and end-to-end cost** all meet requirements.
