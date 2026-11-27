# Instance Families and EC2 Configuration Selection

> **Chapter:** EC2 Instances  
> **Module:** CLOUD_PROVIDERS_AWS — explore the AWS ecosystem from Regions/AZs, IAM, and VPC to compute, storage, databases, integration, and serverless; learn how to choose services, design, deploy, monitor, recover, and control costs.

## Learning Objectives

Amazon Elastic Compute Cloud (**Amazon EC2**) provides virtual servers configurable by CPU, RAM, storage, networking, operating system, and compute purchasing model. Choosing the right **instance family** and **instance size** is a critical decision because it directly affects latency, throughput, load limits, availability, and operating costs.

After this lesson, you will be able to:

1. Distinguish **instance family**, **generation**, **processor variant**, and **instance size** in EC2 naming.
2. Identify the **general purpose**, **compute optimized**, **memory optimized**, **storage optimized**, and **accelerated computing** families, along with their appropriate use cases.
3. Select configurations based on CPU/vCPU, RAM, x86_64 or arm64 architecture, EBS, instance store, networking, and availability by Region/AZ.
4. Explain the **burstable performance** characteristics of the T family and the impact of CPU credits.
5. Compare On-Demand, Savings Plans, Reserved Instances, Spot Instances, and costs beyond virtual machine pricing.
6. Use the AWS CLI to inspect instance type specifications and availability; plan data-driven testing and **right-sizing**.
7. Propose a safe initial configuration with monitoring, recovery plans, and post-load-measurement adjustments.

## 1. What Is an EC2 Instance Type?

An **EC2 instance** is a virtual server running in an **Availability Zone (AZ)** within a Region. The **instance type** defines most of the hardware capabilities allocated to the machine: vCPU count, RAM capacity, CPU architecture, network bandwidth, EBS capability, and specialized storage or acceleration features if any.

For example, the name **`m7i.large`** can be broken down as follows:

~~~text
m7i.large
│││ └── size: large
││└──── variant: i (the Intel line of this generation)
│└───── generation: 7
└────── family: m (general purpose)
~~~

Some other names: **`c7i.large`**, **`r7i.large`**, **`m7g.large`**, **`t3.medium`**. These are **examples for learning how to read names**, and do not assert that they are the latest generation, the cheapest, or always have capacity available in an AZ.

### 1.1. Four Components to Distinguish

| Component | Meaning | Question to Ask When Choosing |
|---|---|---|
| **Family** | Resource optimization focus (M, C, R, T, I, P...) | Does the workload primarily need CPU, RAM, disk, or GPU? |
| **Generation** | Hardware/design generation of that group | How do the performance, features, and pricing of available generations compare? |
| **Variant** | Processor line or specialized feature; suffixes do not have an absolute meaning across all generations | Are the OS, libraries, and AMI compatible with the CPU/hardware? |
| **Size** | Resource allocation tier within a type, such as small, medium, large, xlarge... | How many vCPUs, GiB of RAM, and how much bandwidth are needed? |

Instance family names are defined by AWS. Do not infer every specification solely from the name; cross-check the **EC2 Instance Types documentation** or the **`DescribeInstanceTypes`** API. For instance, vCPU count does not fully reflect single-thread performance, turbo levels, CPU credits, or I/O limits.

### 1.2. How Does an Instance Differ from an Auto Scaling Group?

- **EC2 instance:** a specific virtual machine with an instance ID, AMI, subnet, security group, IAM role, and attached EBS volumes.
- **Launch template:** a configuration template for launching instances; stores reusable parameters.
- **EC2 Auto Scaling group:** manages the number of instances according to minimum/desired/maximum capacity, replaces unhealthy instances, and can distribute across multiple AZs.
- **Elastic Load Balancing:** distributes connections across multiple instances/targets, enabling the architecture to scale horizontally.

Choosing a good instance type **does not replace** a multi-AZ architecture, backups, or monitoring. A single very powerful machine can still become a **single point of failure**.

## 2. Overview of EC2 Instance Family Groups

### 2.1. Core Comparison Table

| Group | Example Families | Optimization Focus | Typical Workloads | Risk of Choosing Wrong |
|---|---|---|---|---|
| **General purpose** | M | Balanced CPU, RAM, networking | Web/API, enterprise applications, mixed services | Can be wasteful if only CPU or RAM is actually needed |
| **Burstable general purpose** | T | Baseline CPU + credits, suited for intermittent load | Dev/test, small apps with low baseline load and occasional spikes | Sustained high CPU load leads to credit exhaustion or extra charges depending on mode |
| **Compute optimized** | C | CPU relative to RAM | Batch processing, encoding, computation, suitable game servers | Insufficient RAM if the workload has a large heap/cache |
| **Memory optimized** | R, X, some specialized families | High RAM per vCPU | In-memory analytics, caches, self-managed databases | High price with idle CPU if RAM is overestimated |
| **Storage optimized** | I, D, H and related lines | Local storage and I/O tailored to each type's characteristics | Local NoSQL, log/search needing fast disk access or large capacity | Risk of losing instance store data when the instance terminates; requires replication |
| **Accelerated computing** | G, P, Inf, Trn, F and related families | GPU or specialized accelerators | AI training/inference, graphics, parallel processing, FPGA | High cost, requires compatible runtime/drivers |
| **HPC optimized** | Hpc and specialized lines | Scientific computing, network/CPU bandwidth for HPC | Simulations, parallel computing, MPI | Depends on cluster design, EFA, placement, and Region support |
| **High-memory / specialized** | U and lines for specific workloads | Extremely large RAM, custom profiles | Large-scale in-memory databases, specialized applications | High cost, quotas, capacity, licensing, and operational demands |

The names in the example column represent **grouping patterns**, not an exhaustive list. Some instance types combine multiple characteristics simultaneously, such as supporting both local NVMe and strong CPUs. Evaluate the specifications **of the specific type**, not just the family.

### 2.2. General Purpose: A Reasonable Starting Point

The **M** family is suitable when it is not yet clear which resource is the bottleneck: web servers, common Java/.NET applications, API servers, or workers with relatively balanced CPU and RAM needs.

Deployment examples:

- A Spring Boot application with APIs, a small cache, and a connection to RDS should usually **start load testing** with M.
- If measurements show CPU frequently hitting the ceiling while RAM has headroom, consider **C** or increasing the number of replicas.
- If CPU is not high but the JVM heap/working set frequently runs out of RAM, consider **R** or tuning memory settings.

The RAM-to-vCPU ratio can vary by generation and variant. Do not apply a rule such as “all M instances have exactly 4 GiB/vCPU” to pick a configuration without checking the actual specs.

### 2.3. Compute Optimized: When CPU Is the Limit

The **C** family is suitable when each request/job requires heavy computation while RAM requirements are relatively small, for example:

- Image/video processing where the work runs primarily on CPU.
- Compression/decompression, data processing, compilation, and compute batch jobs.
- Web backends with high CPU time and a compact working set.
- Algorithms that need many vCPUs and scale across threads.

Measure **CPU utilization over time, the number of threads actually running in parallel, p95/p99 latency, and memory**. A single-threaded workload may not speed up when adding many vCPUs; per-core performance and parallel design can matter more than core count.

### 2.4. Memory Optimized: When Data Must Reside in RAM

The **R** family and other memory-optimized types are suitable for:

- Self-managed caches/in-memory stores when data and overhead must fit in RAM.
- Databases or search engines requiring large caches.
- JVM applications with large heaps or large session data.
- Data analytics with large working sets suffering from garbage collection pressure or swapping.

Do not size RAM to match raw data size alone. You must add **OS, runtime, metadata/indexes, memory fragmentation, buffers/caches, replicas, and peak load**. A machine with 64 GiB of RAM does not mean an application can safely use all 64 GiB for the JVM heap.

If the primary need is a database, consider **Amazon RDS/Aurora/DynamoDB/ElastiCache** instead of self-managing databases/caches on EC2, depending on requirements and the level of control needed.

### 2.5. Storage Optimized: Distinguishing Local Storage from EBS

Some **I/D/H** families have local storage attached to the instance, typically targeting throughput, IOPS, or capacity. However:

- **Instance store** is tied to the physical host: data **does not persist after the instance is terminated**, and it should not be treated as a standalone durable storage tier; data can also be lost during certain host failure events.
- **Amazon EBS** is block storage attached within an AZ, with its own durability mechanisms, snapshots, and performance configurations; it is not the same as instance store.
- Some instance types **do not have instance store**; in those cases, use EBS or another storage service.
- If a workload stores important data on instance store, it must have **replication, backups, recovery, and fault-tolerance testing**.

A log/search system with replicas and index-rebuilding mechanisms can leverage local NVMe. A single database with no replicas stored only on instance store poses a major operational risk.

### 2.6. Accelerated Computing and HPC

GPUs/accelerators help workloads whose libraries/software can leverage hardware acceleration. For example:

- **G/P:** imaging, graphics, or AI depending on the GPU type; do not assume all G/P types are equivalent.
- **Inf/Trn:** AWS accelerators designed for inference/training respectively, with dedicated SDKs/runtimes.
- **Hpc:** scientific simulation workloads requiring compute performance and appropriate networking infrastructure.

Before selecting, check the **framework, drivers, CUDA or relevant runtime, AMI, CPU architecture, quotas, and AZ availability**, and compare with managed services like SageMaker or Batch where appropriate.

## 3. vCPU, CPU Architecture, and Burstable Performance

### 3.1. vCPU Does Not Equal One Physical Core

A **vCPU** is the logical processing unit advertised by EC2 for an instance type. On many x86 lines using simultaneous multithreading (SMT), a vCPU may correspond to a hardware thread; on many AWS Graviton lines, a vCPU typically corresponds to a physical core. Therefore:

- **2 vCPUs** across two different CPU lines do not guarantee the same operations per second.
- Application thread count, vector instruction support, cache, CPU clock, memory architecture, and compiler efficiency all have an impact.
- When running Java, measure **GC pauses, heap pressure, JIT warm-up, and startup** as well; CPU utilization alone is not enough.
- Use benchmark data **on your real workload** to decide when price/performance is close.

Some instance types support **CPU options** such as adjusting the core count or threads per core within AWS-allowed limits for licensing or specialized workloads. Change these only when you understand the impact on performance and licensing costs.

### 3.2. x86_64 and arm64: Selecting by Dependency Chain

AWS offers many x86 families based on Intel/AMD and many **AWS Graviton** families based on Arm. For example:

~~~text
m7i.large  -> an Intel x86_64 variant of the M family
m7g.large  -> an AWS Graviton arm64 variant of the M family
~~~

**Compatibility verification process:**

1. Verify that the **Amazon Machine Image (AMI)** supports the target `x86_64` or `arm64` architecture.
2. Verify that the application, runtime (Java JDK, Node.js, Python...), native/JNI libraries, packages, and binaries support the target architecture.
3. If using containers, images must have the appropriate build or a multi-architecture manifest.
4. Check agents, monitoring, security software, drivers, and third-party dependencies.
5. Run benchmarks and functional tests before migrating production workloads.

**Note:** the same Java bytecode can often run on the corresponding JDK across multiple architectures, but **native dependencies** and container images can still be incompatible. You cannot “switch” an x86 AMI to Arm simply by changing the instance type.

### 3.3. CPU Credits in the T Family

The **T** family provides baseline CPU performance and a **CPU credits** mechanism to burst when the workload needs extra capacity. Key concepts to remember:

- When running below baseline, the instance can **accumulate credits** according to the instance type's rules.
- When running above baseline, the instance **spends credits** for additional CPU capacity.
- **Standard** mode (if supported by the type) may throttle sustained CPU usage when credits are exhausted.
- **Unlimited** mode allows operating above baseline under certain conditions, but can incur **surplus CPU credit charges** if usage exceeds billable thresholds per AWS policy.
- Different T lines and generations have their own characteristics/default settings; do not assume all T types share the same mode and billing behavior.

Example:

~~~text
Workload A: CPU 5-10% most of the day, high for a few minutes
  -> T may be suitable if credits and costs are monitored.

Workload B: CPU 80-95% continuously for many hours
  -> An appropriate C or M may offer more predictable performance/price.
~~~

Monitor **`CPUUtilization`**, **`CPUCreditBalance`**, **`CPUSurplusCreditBalance`**, and related metrics when supported by the instance type. Looking only at monthly average CPU can hide credit-exhaustion events and latency spikes.

## 4. RAM, EBS, Instance Store, and Network Capacity

### 4.1. Sizing RAM by Working Set and Peak Load

A mental formula for an application server:

~~~text
Required RAM
≈ OS + agent RAM
  + application RAM (heap/native/off-heap)
  + page cache/buffers
  + headroom for peaks and variance
~~~

Do not take a single number from a development machine as the production configuration. Measure:

- Resident set size (RSS), JVM heap and non-heap, swap usage, and out-of-memory errors.
- Memory per container/pod if running Docker/ECS/EKS on EC2.
- Peak periods, scale-out/scale-in events, and application deployments.
- Cache hit rate, memory pressure, GC pauses, and their impact on latency.

Leave headroom to avoid swapping and the OOM killer. If the workload grows with data volume, plan scaling based on **data size and instance count**, not just vCPU.

### 4.2. EBS Throughput and EBS-Optimized Support

EBS offers multiple volume types, such as **gp3** for general-purpose SSD, **io2** for high IOPS per service characteristics, and other types suited to specific workloads. When selecting EC2, evaluate both:

- **Volume performance:** IOPS, throughput, size, and the configurable limits of the EBS volume type.
- **Instance EBS bandwidth:** each instance type has its own EBS bandwidth specification, which can cap total throughput across multiple volumes.
- **Latency and I/O queues:** queue length, block size, read/write ratio, and burst patterns.
- **AZ and lifecycle:** an EBS volume is created in one AZ and attached to a compatible EC2 instance in the matching AZ; snapshots are commonly used for backup/restore workflows.
- **Security:** enable EBS encryption per account standards; use appropriate IAM/KMS permissions if needed.

**Example:** a volume rated for very high throughput may not achieve those numbers if the instance has lower EBS throughput or if the workload generates small, non-parallel I/O. Measure both ends to avoid paying for storage performance the instance cannot utilize.

### 4.3. Network Performance and Connection Limits

EC2 instance types advertise networking capabilities (such as network performance tiers, ENA support, and advanced features). Consider reviewing:

- Actual throughput and packets-per-second in practice.
- Cost and latency of **intra-AZ, inter-AZ, and inter-Region** traffic along the path.
- The number of attachable ENIs/IP addresses/security groups per type/size when designing multi-interface networking.
- EC2 placement groups/EFA when running HPC or extremely latency-sensitive workloads.
- Connectivity to RDS, S3, EFS, API Gateway, and on-premises systems over specific VPC routes.

**Do not conclude that “up to X Gbps” means continuously guaranteed bandwidth**. AWS may apply baseline/peak levels and limits based on traffic type or instance size. Check documentation and benchmark.

### 4.4. Ephemeral Storage and Instance Lifecycle

Distinguish states:

| Scenario | EBS root/data volume | Instance store |
|---|---|---|
| **Reboot** | Data is normally preserved | Data is normally preserved |
| **Stop → Start** on an EBS-backed instance | Data on EBS persists per configuration | Instance store data is **not guaranteed to persist** across stop/start |
| **Terminate** | Root EBS typically has `DeleteOnTermination=true` by default configuration; data volumes can be kept or deleted | Instance store data is lost |
| **Host failure** | EBS and recovery procedures have their own durability characteristics | Local instance store may be lost; requires replicas/backups |

**Do not assume every EBS root volume is always deleted or always retained**: verify `DeleteOnTermination` on each volume attachment. Snapshots also have their own costs and lifecycle.

## 5. Region, Availability Zone, AMI, and Deployment Constraints

### 5.1. Region/AZ Determines Provisioning Availability

An instance type may be listed in documentation yet:

- Not yet be offered in your chosen **Region** or **AZ**.
- Be constrained by **service quotas** by vCPU/family category and purchase option.
- Be out of On-Demand/Spot capacity at launch time.
- Have specific conditions regarding Local Zones, Wavelength Zones, Outposts, or specialized hardware.

For multi-AZ architectures, check **instance type offerings** in each AZ and have alternatives ready (for example, using a set of equivalent instance types in an Auto Scaling group/Mixed Instances Policy).

An AZ name such as `ap-southeast-1a` can map to different physical AZs across accounts. When coordinating across multiple accounts, reference the **AZ ID** to match physical zones.

### 5.2. AMI and Operating System

An **AMI (Amazon Machine Image)** defines the OS and launch environment. Choose an AMI based on:

1. Matching `x86_64` or `arm64` CPU architecture.
2. OS, kernel, virtualization, and hardware support compatible with the instance type.
3. Required drivers/agents, such as ENA, NVMe, or management tools.
4. Security patches, trusted publisher source, update process, and lifecycle schedule.
5. Boot mode, EBS/root volume type, and AWS-supported options.

Do not reuse one pre-selected AMI across every family without verifying compatibility. Changing CPU architecture or drivers may require **a new AMI, new container builds, and re-testing**.

### 5.3. Tenancy and Licensing

EC2 supports tenancy/host options depending on instance type and Region, such as shared, dedicated instances, or Dedicated Hosts. Selection is influenced by hardware isolation requirements, compliance, software licensing, and cost.

Running Windows Server or software licensed per core/vCPU/host can make licensing costs outweigh raw compute pricing. Check current licensing rules before switching families or changing vCPU counts.

## 6. Workload-Driven EC2 Selection Process

### 6.1. Start from Requirements, Not Instance Names

~~~mermaid
flowchart TD
    A[App requirements and SLO] --> B[Measure CPU, RAM, I/O, network, peak]
    B --> C{What is the primary bottleneck?}
    C -->|Balanced| M[M / general purpose]
    C -->|Sustained CPU| C[C / compute optimized]
    C -->|RAM| R[R / memory optimized]
    C -->|Local storage / specific IOPS| S[I / D / storage optimized]
    C -->|GPU / accelerator| G[G / P / Inf / Trn]
    C -->|Low load, short bursts| T[T / burstable]
    M --> D[Check architecture, AMI, Region/AZ, quota]
    C --> D
    R --> D
    S --> D
    G --> D
    T --> D
    D --> E[Benchmark performance + measure cost]
    E --> F{Meets SLO and budget?}
    F -->|No| B
    F -->|Yes| H[Deploy with monitoring, backups, scaling]
~~~

Before selecting a family, gather:

| Factor | Questions to Answer | Metrics/Outputs to Have |
|---|---|---|
| **Latency** | What ms threshold must p95/p99 stay under? | SLOs and latency charts |
| **Throughput** | How many requests/sec or jobs/hour? | Average and peak |
| **CPU** | Is CPU high continuously or only in short spikes? | CPUUtilization, load, thread profile |
| **RAM** | What are the working set, heap, cache, and peak? | RSS, memory peak, OOM/GC |
| **Storage** | Does data need durability or can it be rebuilt? IOPS/throughput? | GB, IOPS, block size, latency |
| **Network** | Which services are called? Bandwidth and cross-AZ traffic? | Gbps, connection count, flow metrics |
| **Architecture** | Does the app have arm64 native binaries, drivers, JDK, and images? | Compatibility matrix |
| **Operations** | Uptime target, RTO/RPO, number of AZs? | SLA/SLO, failover plan |
| **Cost** | Monthly budget, load stability? | TCO compute + storage + network |

### 6.2. Five Initial Selection Scenarios

**Scenario A — Java/Spring Boot API:** a REST application processing orders, using external RDS outside EC2, peaking during business hours. **Start with M** with enough RAM for the JDK, heap, OS, and agents. Benchmark request load, CPU, GC, and p99; if CPU is high while RAM has headroom, consider C. For HA, use ≥2 AZs, Auto Scaling + load balancer.

**Scenario B — Compute Batch:** CPU-based image processing and report generation, jobs split into small units, minimal RAM needed. **Start with C**, checking parallelism. If retryable, consider **Spot** or AWS Batch; store durable results in S3/appropriate EBS rather than relying on a single instance.

**Scenario C — Self-Managed In-Memory Cache:** large hot dataset, moderate CPU. **Start with R** or a specialized memory-optimized type; design replication, disk persistence if needed, and recovery procedures. Consider ElastiCache when you want AWS to manage operations.

**Scenario D — ML Inference:** model requires a GPU or specialized accelerator and stable latency. **Test G/Inf or managed services** based on model, framework, throughput, batch size, and runtime; compare against actual CPU inference before choosing.

**Scenario E — Infrequent Dev/Test:** a small API run during study hours with low load and occasional bursts. **T** may fit, but check CPU credits, Unlimited mode, and associated fees. If running only short jobs, consider Lambda, ECS Fargate, or shutting down EC2 off-hours.

These recommendations are **testing starting points**, not fixed answers for every workload.

## 7. Pricing Comparison and EC2 Purchasing Models

### 7.1. Purchase Options

| Model | Main Mechanism | When Suitable | What to Consider |
|---|---|---|---|
| **On-Demand** | Pay for usage with no long-term commitment | Labs, testing, variable workloads | Price can be higher than commitment options for steady loads |
| **Savings Plans** | Commit to a compute spend level for a term/plan terms | Steady usage needing optimization | Cost commitment, varying flexibility scope by Savings Plan type |
| **Reserved Instances (RI)** | Depending on RI type, receive cost discounts or reserve capacity under specific terms | Predictable, steady workloads | Commitment, terms, Region/AZ, family/size flexibility depending on type |
| **Spot Instances** | Use spare EC2 capacity at variable prices | Batch, queue workers, CI jobs, interruptible stateless nodes | AWS can reclaim capacity; needs checkpointing/retry/fallback |
| **Dedicated Hosts/Instances** | Dedicated hardware/tenancy resources per selection | Special licensing or compliance | Different cost and capacity management |

**Savings Plans do not automatically guarantee capacity**; cost discounts and capacity reservation are separate concerns. If you need guaranteed capacity in an AZ, evaluate **On-Demand Capacity Reservations** under their specific terms and pricing.

**Spot Instances** can be interrupted when AWS needs the capacity back; in many cases there is roughly a **two-minute** interruption notice (depending on action/notice type). Applications must treat instance loss as an expected event, checkpointing to S3/appropriate EBS or using queues with retries. Do not run a single unrecoverable component on Spot.

### 7.2. Actual Total Cost

Do not calculate the EC2 instance price in isolation. An estimation model:

~~~text
Total monthly workload cost
≈ instance hours * applicable compute rate
  + EBS volumes and snapshots
  + data transfer / NAT / load balancing / public IPv4
  + CloudWatch metrics, logs, alarms, tracing
  + software licenses and support services
  + other AWS resources used by the application
~~~

Specifically:

- EBS can continue incurring charges when an instance is **stopped**; snapshots also exist independently.
- **Public IPv4 addresses** can incur charges under AWS pricing, including Elastic IPs; do not assume public IPs are free.
- Data transfer across AZs, out to the Internet, or through NAT/Load Balancers can generate substantial costs.
- When instances run intermittently, start/stop schedules can save more than trying to pick a slightly cheaper hourly family.
- Do not confuse “Free Tier” with unconditional free usage; eligibility and promotional terms vary by account/program/time.

Use **AWS Pricing Calculator**, the Region's EC2 pricing page, **Cost Explorer**, and **AWS Budgets** for forecasting/monitoring. Budgets alert on spending; **they do not automatically block all charges by default**.

### 7.3. Optimizing Price/Performance

The goal is not the cheapest instance per hour, but the **cost per unit of work meeting SLOs**:

~~~text
Cost per successful request
≈ total workload cost in period
  / successful requests in period

Cost per completed job
≈ total batch cost in period
  / valid completed jobs in period
~~~

For example, a C machine with a higher hourly price that finishes a batch job significantly faster can be cheaper per job than a T machine. Likewise, a higher-priced R machine that eliminates OOM/GC errors and reduces replica count can lower total cost.

## 8. Security, Monitoring, and Recovery After Selecting a Type

### 8.1. Minimum Secure Configuration

An initial EC2 configuration should include:

1. **IAM role via instance profile** with least privilege; avoid embedding long-lived access keys in user data/AMIs.
2. **Security groups** opening only required ports, preferring SSM Session Manager instead of opening SSH 22/RDP 3389 to the Internet.
3. **IMDSv2** so applications/agents retrieve metadata and credentials more securely; verify SDK/agent compatibility.
4. **EBS encryption** and KMS key governance per organizational policy.
5. Patched AMIs, automated or controlled scheduled updates, and restricted OS privileges.
6. Appropriate VPC subnets/route tables: private subnets if the workload does not need direct inbound Internet access; configure NAT/VPC endpoints as needed for service access.
7. Consistent tagging, for example **Project=aws-lab**, **Environment=dev**, **Owner=team-cloud**, **ManagedBy=iac**, and **CostCenter=training**.

### 8.2. Metrics to Monitor

| Group | Suggested Metrics | How to Use |
|---|---|---|
| **CPU** | CloudWatch `CPUUtilization`; credit metrics for T if applicable | Detect sustained CPU load and credit risks |
| **RAM** | Memory used/RSS/heap via CloudWatch Agent, SSM, or app telemetry | Identify OOMs, memory leaks, and GC pressure |
| **Disk/EBS** | Queue, read/write ops/bytes, latency, available space | Locate EBS/instance store bottlenecks, prevent disk full |
| **Network** | NetworkIn/NetworkOut, packet metrics, and application errors | Detect saturation or abnormal traffic |
| **App latency** | p95/p99, throughput, error rate | Measure real SLOs rather than just machine metrics |
| **Health** | EC2 status checks, ALB target health, instance recovery signals | Trigger alerts and replace unhealthy instances |

**CloudWatch EC2 basic monitoring** does not provide full guest OS **RAM or filesystem usage** by default; you must install an appropriate agent/telemetry if you want to monitor them. Check sampling intervals and costs for logs/custom metrics.

### 8.3. Availability and Recovery

- For stateless web/APIs, use a **multi-AZ Auto Scaling group + load balancer** to replace instances and tolerate single-machine/AZ failures by design.
- For stateful workloads, store data on an appropriate durable tier, take backups/snapshots, and **practice restores**. EBS volumes belong to one AZ; snapshots can support recovery workflows within AWS capabilities.
- Use launch templates/IaC and appropriate AMIs to **recreate** instances. Do not rely on manual configuration existing on only a single machine.
- Select fallback instance types in case an AZ runs out of capacity; consider **multiple instance types** in Auto Scaling.
- Define **RTO** (recovery time objective) and **RPO** (acceptable data loss) to determine replica placement, backups, and monitoring.

## 9. Read-Only Practice with AWS CLI: Comparing Instance Types

The lab below prioritizes **not creating EC2 resources** to avoid unintended costs. You need AWS CLI v2 configured via IAM Identity Center/role or a CloudShell session with EC2 read permissions, at least `ec2:DescribeInstanceTypes` and `ec2:DescribeInstanceTypeOfferings`.

### Step 1 — Verify Identity and Region

Example using Bash:

~~~bash
export AWS_PROFILE=aws-lab-dev
export AWS_DEFAULT_REGION=ap-southeast-1

aws sts get-caller-identity --profile "$AWS_PROFILE"
aws configure list --profile "$AWS_PROFILE"
~~~

Verify that `Account` and `Arn` belong to the intended sandbox. If using **CloudShell** with a pre-authenticated identity, omit `export AWS_PROFILE=...` and the corresponding `--profile` flags when the `aws-lab-dev` profile does not exist.

### Step 2 — Read CPU, RAM, Architecture, EBS, and Network Specs

~~~bash
aws ec2 describe-instance-types \
  --instance-types t3.medium m7i.large c7i.large r7i.large m7g.large \
  --region ap-southeast-1 \
  --query "InstanceTypes[].{Type:InstanceType,vCPU:VCpuInfo.DefaultVCpus,RAM_MiB:MemoryInfo.SizeInMiB,Arch:ProcessorInfo.SupportedArchitectures,Network:NetworkInfo.NetworkPerformance,EBS:EbsInfo.EbsOptimizedSupport,LocalStorage:InstanceStorageSupported}" \
  --output table
~~~

**Interpreting the output:**

- **RAM_MiB** is capacity in MiB; to convert to GiB, divide by **1024**.
- **Arch** indicates which AMI architectures are compatible.
- **Network** is the advertised classification/bandwidth info; check baseline/peak bandwidth if your decision depends on networking.
- **EBS** indicates EBS optimization support; it is not enough on its own to determine IOPS/throughput.
- **LocalStorage** helps distinguish whether an instance supports instance store.

If a type is not accepted by the API or is unavailable in the Region, consult the Region's documentation/offerings and pick an equivalent-role type; there is no need to force the exact example names.

### Step 3 — Check Whether a Type Is Offered in an AZ

~~~bash
aws ec2 describe-instance-type-offerings \
  --region ap-southeast-1 \
  --location-type availability-zone \
  --filters "Name=location,Values=ap-southeast-1a" "Name=instance-type,Values=m7i.large,m7g.large,c7i.large" \
  --query "InstanceTypeOfferings[].{Type:InstanceType,AZ:Location}" \
  --output table
~~~

The output lists instance types advertised in that AZ. **Being in offerings does not guarantee immediate launch**: quotas, capacity, AMIs, purchasing options, subnets, and other limits still need to be checked. Your account's AZ name may map to a different physical AZ than another account's.

### Step 4 — Build Your Own Comparison Table

Record the returned data using the template below (illustrative entries; replace with CLI results):

| Candidate | Family | vCPU / RAM (check via API) | Architecture | Testing Rationale |
|---|---|---|---|---|
| `t3.medium` | T | Read from API | x86_64 | Lab/variable load, monitor credits |
| `m7i.large` | M | Read from API | x86_64 | Balanced application baseline |
| `c7i.large` | C | Read from API | x86_64 | Candidate for CPU-heavy jobs |
| `r7i.large` | R | Read from API | x86_64 | Candidate for memory-heavy workloads |
| `m7g.large` | M | Read from API | arm64 | Price/performance comparison if compatible |

For the same workload, write a **test hypothesis**: “C will reduce job duration because CPU is the bottleneck,” “R will reduce OOM errors,” or “Graviton lowers cost/request if libraries support it.” Only then run load tests using approved tools.

### Step 5 — Evaluate and Make a Decision

Suggested **scorecard** before purchasing or deploying:

| Criterion | Reference Weight | Measurement Source |
|---|---:|---|
| Meets p95/p99 latency and throughput | 30% | Load test / APM |
| No RAM shortage or GC/OOM issues | 20% | OS/JVM telemetry |
| Sufficient CPU/I/O/network headroom at peak | 20% | CloudWatch + OS metrics |
| Cost/request or job | 20% | Pricing Calculator + test measurement |
| Availability and operability | 10% | AZ offerings, quotas, AMI, HA |

Weights vary by problem; for batch jobs, throughput/cost may matter more than p99 latency. **Do not select by total score if a mandatory requirement such as security, SLA, or architecture compatibility is unmet.**

If you have permissions and a lab environment that allows running actual benchmarks, create only instances whose configurations and cleanup times are planned in advance; verify pricing, EBS, public IPv4, Region/AZ, and permissions before launching. This is an optional extension; the core lab above does not require launching machines.

## 10. Case Study Exercise: Choosing EC2 for a Multi-Tier Application

An online learning platform has:

- **Web/API** using Java, serving tens to thousands of requests/minute depending on class hours.
- **Workers** generating thumbnails/packaging videos from a queue, able to retry.
- **Redis/cache** holding frequently accessed data.
- **RDS** storing learner data (already using a managed database, not colocated on EC2).
- **S3** storing videos/documents and exported report logs.
- Availability required when an instance fails, deployed across two AZs, with alerting and cost control.

### 10.1. Initial Proposal

| Component | Suggested Initial EC2 Family | Scaling / Operations Approach | Why |
|---|---|---|---|
| Java Web/API | **M** (balanced) | Auto Scaling ≥2 AZs, ALB, monitor p99/heap | Balances CPU and RAM, has a scale-out path |
| CPU Video Processing Worker | **C** | Queue, retries, Spot if interruption-tolerant | Compute-bound work, divisible into small units |
| Self-managed Redis/cache | **R** or managed service | Replication, backups, failover | Large working set in RAM |
| Business data | **RDS**, not requiring EC2 | Multi-AZ/backups per SLO | Reduces self-managed DB overhead |
| Videos and objects | **S3**, not placed on instance store | Least-privilege IAM, lifecycle as needed | Decouples data from instance lifecycle |

When measuring:

- If API CPU stays continuously high while heap is stable, test **C** and re-measure.
- If API frequently hits OOM/GC pauses, test **R** or adjust memory profile/replica count.
- If GPU-accelerated workers lower cost/job, benchmark G/P against C instead of picking by label.
- If Redis is critical, consider **ElastiCache** instead of a single R machine.

### 10.2. Discussion Questions

1. Why not consolidate the API, Redis, and database onto one large EC2 instance?
2. If workers can be terminated mid-execution, how should queues/checkpoints be designed to use Spot safely?
3. Is an R machine with double the RAM and low CPU utilization always cost-optimal?
4. When migrating a Java application from x86 to Graviton, which dependencies must be tested?
5. How can EBS, data transfer, NAT/ALB, and public IPv4 fees affect the comparison of “which machine is cheaper”?
6. When an AZ lacks capacity for the chosen type, what fallback options does the architecture have?

## 11. Common EC2 Selection Mistakes

| Symptom | Possible Cause | Remediation |
|---|---|---|
| High CPU and sharp p99 spikes despite plenty of RAM | Chose M/R for a CPU-heavy workload or too few replicas | Compare C, scale out, profile CPU and threads |
| Low CPU yet machine OOMs or swaps | Insufficient RAM/heap tuning, memory leak | Measure RSS/heap/GC; consider R, fix application |
| Sustained load on T slows down or increases cost | CPU credits and Unlimited mode | Check CPU credit metrics, move to M/C if appropriate |
| Slow I/O despite a very fast EBS volume | Instance EBS bandwidth or I/O pattern is the bottleneck | Measure instance/volume limits, queue depth, and block size |
| Fails to boot after switching to Graviton | AMI/container/native binaries do not support arm64 | Choose arm64 AMI, build multi-arch, and test |
| Instance type cannot launch in an AZ | Unsupported, insufficient quota/capacity, or misconfiguration | Check offerings, quotas, AMI, AZ, and fallback types |
| Low EC2 rate yet high bill | EBS, snapshots, data transfer, NAT, public IPv4, logging | Calculate TCO, inspect Cost Explorer by service/tag |
| Resources keep incurring charges after termination | Leftover EBS data volumes, snapshots, Elastic IPs, or auxiliary components | Check lifecycle settings and clean up via checklist |
| Spot node disappears, work is lost | No checkpoint/retry, stateful workload | Use queues, checkpoints, multiple instance types/On-Demand fallback |
| Application goes down when one AZ fails | Running only one instance or storing state locally | Multi-AZ, ALB/ASG, externalize state, and test failover |

## 12. Decision Checklist and Self-Test

Before approving an instance type:

- [ ] Defined CPU, RAM, disk, network, peaks, p95/p99, and SLOs.
- [ ] Selected the family based on the **actual bottleneck**, not a “stronger” name.
- [ ] Verified **AMI/OS/drivers/runtime** compatibility with x86_64 or arm64.
- [ ] Checked **Region/AZ offerings**, service quotas, and type fallback options.
- [ ] Evaluated **EBS throughput**, instance store, and data durability requirements.
- [ ] Selected a purchase option matching runtime hours and interruption tolerance.
- [ ] Accounted for EBS, public IPv4, NAT, data transfer, monitoring, and software fees.
- [ ] Configured appropriate IAM role, security groups, IMDSv2, EBS encryption, and patch management.
- [ ] Set up CPU/RAM/I/O/network/app monitoring, alerts, and a right-sizing plan.
- [ ] Prepared backups, Auto Scaling/multi-AZ if needed, a recovery plan, and post-lab cleanup.

**Knowledge self-check:**

1. What components does `m7i.large` represent, and why is a larger size not always optimal?
2. When is T more suitable than C? How can CPU credits affect performance and cost?
3. When you increase EBS IOPS but throughput does not increase, what instance-side limits should you inspect?
4. Why does having the same 2 vCPUs on x86_64 and Arm not equate to identical performance?
5. For data requiring durability, why shouldn't you store only a single copy on instance store?
6. How do Spot, Savings Plans, and Capacity Reservations serve different goals?
7. Which metrics help distinguish CPU shortage, RAM shortage, and network/disk capacity limits?
8. What reasons can prevent an EC2 instance type listed for a Region from launching in a specific AZ?
9. Why must true cost include EBS, networking, and public IPv4 rather than just EC2 pricing?
10. How can an EC2 application remain resilient when an instance or AZ goes down?

**Expected outcome:** you can select **family → type/size → AMI/architecture → storage/network → purchase option**, justify it with workload data, verify it via API/benchmarks, and identify the accompanying security, monitoring, recovery, and cost-optimization measures.

## Official AWS Documentation

- [Amazon EC2 instance types](https://docs.aws.amazon.com/ec2/latest/instancetypes/instance-types.html)
- [Amazon EC2 instance type naming conventions](https://docs.aws.amazon.com/ec2/latest/instancetypes/instance-type-names.html)
- [Amazon EC2 user guide — Instance types](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/instance-types.html)
- [Amazon EC2 burstable performance instances](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/burstable-performance-instances.html)
- [Amazon EBS volume types](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-volume-types.html)
- [EC2 Spot Instances](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/using-spot-instances.html)
- [Amazon EC2 Auto Scaling](https://docs.aws.amazon.com/autoscaling/ec2/userguide/what-is-amazon-ec2-auto-scaling.html)
- [AWS Compute Optimizer — EC2 recommendations](https://docs.aws.amazon.com/compute-optimizer/latest/ug/view-ec2-recommendations.html)
- [AWS EC2 pricing](https://aws.amazon.com/ec2/pricing/)
- [AWS Pricing Calculator](https://calculator.aws/)
- [Amazon CloudWatch metrics for EC2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/viewing_metrics_with_cloudwatch.html)

> **Application note:** Instance families, generations, Region/AZ availability, pricing, EBS/network limits, and promotional programs are updated by AWS over time. Instance names in this lesson illustrate the selection methodology; in real deployments, retrieve **current** specifications, availability, and pricing from AWS, then test against your workload.
