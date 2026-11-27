# OCPU, vCPU, and Comparing Billing Units Across Services

In Oracle Cloud Infrastructure (OCI)'s **Cost and Capacity Management** chapter, understanding billing units bridges technical configuration and budget. An application running on Compute, a managed Oracle database, and an event-handling function may all consume CPU, yet their bills are measured in different quantities.

This lesson falls within the scope of **CLOUD_PROVIDERS_ORACLE**. The running scenario involves a team deploying an application on OCI that needs to select resources for the application and database while maintaining performance, availability, and the ability to reconcile costs by compartment. Tenancy, IAM, and VCN concepts serve only as context; the focus here is reading the exact configuration, measurement units, and pricing scope.

After this lesson, you can:

- Distinguish OCPU, vCPU, ECPU, and usage accumulated over time.
- Convert CPU counts according to the exact shape family instead of applying one ratio across all of OCI.
- Build calculations for Compute Flex, databases, Functions, and accompanying resources.
- Compare options by total cost to meet the same workload requirement.

> Product rules in this lesson were checked against Oracle documentation on **November 21, 2026**. All numeric unit prices in examples are **hypothetical prices for learning how to calculate**, in USD, excluding taxes, discounts, or free allowances. When preparing a real estimate, obtain the exact SKU, deployment model, and commercial terms in effect.

## 1. Distinguish CPU Counts and Billing Units

### 1.1. Core, Thread, and vCPU

A physical core executes program instructions. With simultaneous multithreading such as SMT, a single core can provide multiple hardware execution threads. The operating system or virtual machine sees the logical processors corresponding to the allocated configuration.

**vCPU** is a virtual CPU unit. In the OCI Compute lines examined in the table below, it maps to an execution thread or core depending on processor design. The vCPU count helps describe the configuration, but it does not fully describe capability: CPU generation, per-core processing speed, cache, RAM, and I/O limits all affect the outcome.

Two threads on the same core share that core's resources. Therefore, increasing the number of visible threads does not mean application performance scales linearly.

### 1.2. OCPU Must Be Read by Shape Family

**OCPU**, short for Oracle CPU, is the CPU allocation and pricing unit used by many OCI services. According to the [Compute Shapes documentation](https://docs.oracle.com/en-us/iaas/Content/Compute/References/computeshapes.htm), the rules for the following Compute lines are:

| Compute line | Resources corresponding to 1 OCPU | Corresponding vCPU count |
| --- | --- | ---: |
| x86 using AMD or Intel | 1 physical core with 2 threads | 2 |
| Arm Ampere A1 | 1 Arm core | 1 |
| Arm Ampere A2, A4 | 2 Arm cores | 2 |

Thus, the statement "1 OCPU always equals 2 vCPUs" lacks scope. The statement "every Arm shape has 1 OCPU equal to 1 vCPU" is also incorrect. When encountering a new shape, check the definition for that exact line.

Example of **CPU count conversion**, not yet performance conversion:

```text
x86 VM:  2 OCPU × 2 = 4 vCPU
A1 VM:   4 OCPU × 1 = 4 vCPU
A2 VM:   2 OCPU × 2 = 4 vCPU
```

All three configurations have the same vCPU count under the rules above. They still must be benchmarked under the same application load before concluding on serving capacity.

### 1.3. ECPU Is a Separate Measurement Model

In Autonomous Database, **ECPU** is a compute resource metric abstracted from a pool of compute and storage servers. It does not directly specify a fixed number of physical cores. Current documentation uses ECPU when creating or cloning a new Autonomous Database; OCPU is a legacy metric that may still appear in existing systems. See [Compute Models in Autonomous AI Database](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/autonomous-compute-models.html).

Do not infer that because names both contain "CPU," their counts can be substituted directly:

```text
4 Compute vCPU ≠ automatically 4 Database ECPU
2 Compute OCPU ≠ automatically the same cost as 2 Database OCPU
```

Some Autonomous Database migration documents illustrate an older 4 OCPU configuration with a 16 ECPU configuration at a roughly comparable cost level. That is a sizing guide in the context of migrating and pricing that specific service, not a hardware law saying "1 OCPU = 4 ECPU" across all services. See [Autonomous Database ECPU FAQ](https://www.oracle.com/a/ocom/docs/autonomous-database-ecpu-faq.pdf).

## 2. Read a Price Line Using Three Questions

Before calculating cost, identify all three items:

1. **Which resource is being purchased?** For example, VM CPU, VM memory, database software, or volume capacity.
2. **What is each unit?** For example, OCPU-hour, GB RAM-hour, ECPU-hour, or 10,000 requests.
3. **How is the quantity measured?** For example, provisioned configuration, resources actually consumed under service mechanics, provisioned capacity, or billable request count.

A calculation is valid only when the units of quantity and unit price match:

```text
Cost = Billable usage × Corresponding unit price

OCPU-hours × USD / OCPU-hour = USD
GB-hours   × USD / GB-hour   = USD
ECPU-hours × USD / ECPU-hour = USD
```

If there are multiple SKUs or multiple configuration intervals, sum the components:

```text
C_total = Σ (Q_i × P_i)
```

Where `Q_i` is the usage of fee line `i`, and `P_i` is the unit price of that exact line. The base formula does not yet include tier rules, free allowances, commitments, and taxes; those factors must be applied line by line.

### 2.1. OCPU-Hours Are Not the Number of OCPUs at a Point in Time

A VM with 3 OCPUs billed for 8 hours generates:

```text
Q_cpu = 3 × 8 = 24 OCPU-hours
```

A group of three VMs, each with 1 OCPU running for 8 hours, also generates 24 OCPU-hours. Although the accumulated CPU quantity is identical, the two options can differ in RAM, disk, bandwidth, load distribution, and fault tolerance.

With multiple configuration intervals:

```text
Q_cpu = Σ (Billable OCPUs in interval k × Hours in interval k)
```

Distinguish two types of metrics:

| Metric | Question answered |
| --- | --- |
| Configured OCPUs or GB RAM | How much resource is allocated to the system at that point in time? |
| OCPU-hours or GB-hours | How much billable resource accumulated over the entire period? |
| CPU utilization | How busy is the allocated CPU resource? |
| Successful requests, completion time | What work output did the resource produce? |

For a running Standard Flex VM, idle CPU does not turn the calculation into "price × CPU utilization percentage." CPU utilization is useful for rightsizing, whereas configured CPU and RAM are the components of the Flex pricing model. See [Compute FAQ](https://www.oracle.com/cloud/compute/faq/).

### 2.2. Comparison Price per vCPU vs. Billed Price

Oracle may display both a **Comparison price (/vCPU)** column and a **Unit price** column to aid comparison. Read them alongside the line's **Unit** column; the comparison column does not create a second charge. See [OCI Price List](https://www.oracle.com/cloud/price-list/).

If one OCPU of the shape under consideration corresponds to `k` vCPUs, the normalized CPU price portion is:

```text
P_vcpu_comparison = P_ocpu / k

C_cpu = OCPU × hours × P_ocpu
      = vCPU × hours × P_vcpu_comparison
```

Hypothetical example for x86:

```text
P_ocpu = 0.04 USD/OCPU-hour
k      = 2
P_vcpu_comparison = 0.02 USD/vCPU-hour

2 OCPU × 10 hours × 0.04 = 0.80 USD
4 vCPU × 10 hours × 0.02 = 0.80 USD
```

Both calculations describe the exact same CPU portion. Do not add `0.80 + 0.80`, and do not multiply OCPU count by the per-vCPU price.

## 3. Each Service Has Its Own Set of Billing Units

The table below is a map for reading estimates. A single resource can generate multiple fee lines, and the model of the specific service determines which lines appear.

| Service or component | Units to look up on the price list | Items to add when comparing |
| --- | --- | --- |
| Compute Standard Flex | OCPU-hours and GB RAM-hours | Boot volume, block volumes, paid OS or software |
| Base Database Service | OCPU-hours or ECPU-hours depending on model | Infrastructure/software component of the SKU, storage, backups |
| Autonomous Database on ECPU | ECPU-hours | Database storage, backups, and enabled features |
| OKE | Cluster-hours if a paid tier; worker resources | Compute, RAM, storage, load balancer; virtual node fees if used |
| OCI Functions | Invocations and GB memory-seconds | Supporting services and add-on features if enabled |
| Block Volume | GB capacity-months and VPU/GB-months | Backups and configured performance |
| Object Storage | GB-months and request units | Data retrieval by storage tier, data transfer when applicable |
| Flexible Load Balancer | Load balancer-hours and Mbps-hours | Related network data transfer lines |

Storage, network, and cluster metrics can be checked on the [OCI Price List](https://www.oracle.com/cloud/price-list/). Database, Functions, and worker models are explained separately in the following sections.

The practical takeaway is that **a service's CPU price does not represent the full price of that service**. To compare Compute against a managed database, align all required scope: storage, backups, software operations, maintenance, and recovery requirements.

## 4. Calculate Compute Flex Cost from CPU and RAM

### 4.1. Formula for a Constant Configuration

Suppose the VM under consideration has two billing lines, CPU and RAM:

```text
C_vm = H × (N_ocpu × P_ocpu + M_gb × P_memory)
```

Where:

- `H`: hours the VM is billed during the period.
- `N_ocpu`: configured OCPU count.
- `M_gb`: RAM capacity in GB using the service's unit.
- `P_ocpu`: USD/OCPU-hour.
- `P_memory`: USD/GB-hour.

For multiple VMs with the same configuration and schedule, multiply the result by the VM count. For different VMs, compute each VM individually then sum.

### 4.2. Same 4 vCPU, 16 GB RAM

Assume a 30-day month, each VM running the entire month:

```text
H = 30 × 24 = 720 hours
```

This table evaluates **CPU and RAM only**, using purely hypothetical prices:

| Option | OCPU | vCPU | RAM | CPU price, USD/OCPU-hour | RAM price, USD/GB-hour |
| --- | ---: | ---: | ---: | ---: | ---: |
| x86 VM | 2 | 4 | 16 GB | 0.040 | 0.0030 |
| Arm A1 VM | 4 | 4 | 16 GB | 0.025 | 0.0025 |
| Arm A2 VM | 2 | 4 | 16 GB | 0.035 | 0.0025 |

Calculations:

```text
x86:
  CPU + RAM per hour = 2 × 0.040 + 16 × 0.0030 = 0.128 USD
  720 hours          = 92.16 USD

Arm A1:
  CPU + RAM per hour = 4 × 0.025 + 16 × 0.0025 = 0.140 USD
  720 hours          = 100.80 USD

Arm A2:
  CPU + RAM per hour = 2 × 0.035 + 16 × 0.0025 = 0.110 USD
  720 hours          = 79.20 USD
```

In this hypothetical number set, A1 has a lower price per OCPU than x86 yet a higher combined CPU and RAM total. The reason is the required OCPU count and the RAM component. The result only illustrates how to normalize; it does not reflect commercial pricing or rank real CPU lines.

Nor can we conclude A2 is the best choice for the application. You must verify Arm images, JDK, native libraries, container images, monitoring agents, and actual load. A configuration that is cheap per hour but cannot run the software or needs more instances can lose its advantage.

### 4.3. Configuration Changing Mid-Month

Suppose an x86 VM uses the rates from the example above:

| Interval | OCPU | RAM | Billable hours |
| --- | ---: | ---: | ---: |
| Normal load | 2 | 16 GB | 600 |
| High load | 4 | 32 GB | 120 |

Then:

```text
Q_cpu    = 2 × 600 + 4 × 120   = 1,680 OCPU-hours
Q_memory = 16 × 600 + 32 × 120 = 13,440 GB-hours

C_cpu    = 1,680 × 0.040  = 67.20 USD
C_memory = 13,440 × 0.003 = 40.32 USD
C_vm     = 107.52 USD
```

This is a sum across time intervals, not taking the largest configuration for the whole month, nor substituting average CPU utilization for the OCPU count.

### 4.4. Run Schedule, Stopped State, and Persisting Resources

For Standard Compute, properly stopping via OCI can pause compute billing, but it does not automatically delete volumes holding data. Stop billing rules depend on the shape family; Dense I/O, GPU, HPC, and certain other types have exceptions. Simply shutting down from inside the OS also does not replace stopping via the Console or API. See [Resource Billing for Stopped Instances](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/resource-billing-stopped-instances.htm).

Therefore, an estimation sheet needs separate schedules:

```text
Lab VM CPU/RAM:        billable hours per run schedule
Boot/block volumes:    duration the volumes remain retained
Backups:               duration and capacity stored
Load balancer:         duration the service exists under its fee model
```

Do not apply a single "application uptime hours" variable to every resource line.

## 5. Read OCPU and ECPU for Database Services

### 5.1. Separate the Product and Deployment Model Properly

The following three options can all serve an application using Oracle Database, yet they differ in cost scope:

| Option | What must be included in the calculation |
| --- | --- |
| Self-managed database on Compute | VM, RAM, storage, backups, software used, and operational effort |
| Base Database Service | OCPU/ECPU metric for the exact shape, edition, license model, storage, and backups |
| Autonomous Database | ECPU metric or legacy metric of an existing instance, workload type, storage, backups, add-on features |

Hence, comparing a "2 OCPU VM" against a "2 OCPU database" on CPU price alone omits service scope.

### 5.2. Base Database Does Not Have Only One CPU Metric

The Base Database price list currently includes both ECPU and OCPU models. With the ECPU model on standard x86, the price list separately specifies the **Base Database Compute Infrastructure** component and software SKUs by edition or BYOL. Therefore, read all applicable lines for the configuration rather than treating a single ECPU price as the total. See [Base Database Service Pricing](https://www.oracle.com/database/base-database-service/pricing/) and [Oracle Service Descriptions](https://www.oracle.com/contracts/docs/paas_iaas_universal_credits_3940775.pdf?download=false).

Calculation template for an ECPU option with separate components:

```text
C_base_db = Q_infrastructure_ecpu_h × P_infrastructure
          + Q_database_ecpu_h × P_selected_edition_or_byol
          + C_database_storage
          + C_backup
          + C_other_applicable_components
```

Do not assume `Q_infrastructure_ecpu_h` always equals `Q_database_ecpu_h`; populate according to the configuration and service measurement rules. Likewise, if a SKU already bundles infrastructure or software components, do not add that component a second time.

**License Included** and **Bring Your Own License (BYOL)** are also two distinct choices. BYOL requires appropriate license entitlements; it is not a discount code selectable for any system. Cost modeling must preserve edition and license model details alongside CPU counts. See [Base Database Service FAQ](https://www.oracle.com/database/base-database-service/faq/).

### 5.3. Autonomous Database: Base Compute and Auto-Scaled Resources

With the ECPU model, consider both compute and storage; additional compute from autoscaling is billed, and backup storage is a separate component from database storage. See [Autonomous Database Billing Summary](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/autonomous-database-billing-overview.html).

A time-interval estimation model is:

```text
C_autonomous = Σ (ECPU_billable_k × H_k × P_ecpu_k)
             + C_database_storage
             + C_backup_storage
             + C_other_applicable_features
```

If the billable ECPU count in an interval already includes the autoscaled portion, do not add the increment again.

In an example solely for calculating compute quantity, suppose the report indicates equivalent billable ECPU totals:

```text
4 ECPU for 650 hours
8 ECPU for 70 hours

Q_ecpu = 4 × 650 + 8 × 70 = 3,160 ECPU-hours
```

Multiply `3,160 ECPU-hours` by the price matching the workload and license model, then add storage, backups, and applicable components. Do not convert to Compute vCPU to apply VM rates.

### 5.4. Sharing a Unit Name Is Not Enough to Merge Prices

Two lines both labeled ECPU-hour from two different products can still differ in:

- Resource components included in the SKU.
- Workload type and features included in the service.
- Software entitlements and license model.
- How autoscaling and base resources are measured.

Only sum usage quantities before multiplying by unit price if the lines genuinely share the same unit price and applicable terms. Otherwise, calculate each line's cost first, then sum the dollar amounts.

## 6. OKE and Functions: Application Units Differ from VM Units

### 6.1. OKE with Managed Worker Nodes

OKE managed nodes run on Compute inside the tenancy; users pay for the instances executing workloads. Virtual nodes use a different resource allocation model at the pod level. See [Comparing Virtual Nodes with Managed Nodes](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengcomparingvirtualwithmanagednodes_topic.htm).

For a cluster using managed nodes, you can structure:

```text
C_oke = C_cluster_if_applicable
      + Σ C_worker_compute_and_memory
      + C_worker_boot_volumes
      + C_persistent_storage
      + C_load_balancing
      + C_other_services
```

A pod requesting low CPU does not automatically reduce the OCPU count of running nodes. For example, you must still include all three provisioned nodes in the estimate even if at the measurement moment the application occupies only a fraction of their resources. To reduce base cost, you need a change that lowers actual billable resources, such as resizing shapes or node counts while meeting operational requirements.

When using virtual nodes, estimate using the corresponding pod resource lines and virtual node fees; do not copy the managed node formula directly. Nor should you add a hypothetical managed VM if the actual option has no such resource.

### 6.2. Functions Use Invocations and GB Memory-Seconds

OCI Functions bills execution by memory and duration, alongside an invocation component. Provisioned concurrency also has separate pricing rules. See the pricing section at [OCI Functions](https://www.oracle.com/cloud/cloud-native/functions/).

For an example examining standard invocations only, without provisioned concurrency:

```text
Q_execution = Σ (Memory_GB_j × Billable_duration_seconds_j)

C_functions = N_billable_invocations × P_invocation
            + Q_execution × P_gb_second
```

Billable duration must follow the exact measurement and rounding rules of the service. When applying free allowances, determine the remaining free amount for the period before computing billable usage.

Assume all usage below is billable, with no free allowance applied:

```text
N = 1,000,000 invocations
Memory per invocation = 0.5 GB
Billable duration per invocation = 0.2 seconds

P_invocation = 0.0000003 USD/invocation
P_gb_second  = 0.00002 USD/GB-second
```

We get:

```text
Q_execution = 1,000,000 × 0.5 × 0.2 = 100,000 GB-seconds

C_invocation = 1,000,000 × 0.0000003 = 0.30 USD
C_execution  = 100,000 × 0.00002     = 2.00 USD
C_functions  = 2.30 USD
```

You cannot compare `100,000 GB-seconds` directly against a `USD/OCPU-hour` rate. To compare against a long-running VM, align traffic volume, latency requirements, retries, startup time, and required supporting services.

A memory change also affects duration: moving from `0.5 GB × 0.2 seconds` to `1 GB × 0.1 seconds` keeps the memory-time product unchanged in a simple model. If raising RAM does not proportionally reduce duration, execution can become more expensive.

## 7. Storage and Network Change CPU Comparison Outcomes

### 7.1. Block Volume Has Capacity and Performance

Block Volume has a capacity component and a performance component measured in VPUs per GB. VPU stands for **Volume Performance Unit**, not VM CPU. Performance tiers are explained in [Block Volume Performance](https://docs.oracle.com/en-us/iaas/Content/Block/Concepts/blockvolumeperformance.htm).

If the performance unit price is quoted **per VPU per GB-month**, the illustrative formula for a volume kept the entire month is:

```text
C_volume = D_gb × P_capacity_gb_month
         + D_gb × VPU_per_gb × P_one_vpu_gb_month
```

Assume:

```text
D_gb = 500 GB
VPU_per_gb = 10
P_capacity_gb_month = 0.03 USD/GB-month
P_one_vpu_gb_month  = 0.002 USD/(VPU/GB-month)

C_capacity    = 500 × 0.03       = 15 USD
C_performance = 500 × 10 × 0.002 = 10 USD
C_volume      = 25 USD/month
```

If the price list already presents a combined price for the 10 VPU/GB level, use that level's price; do not multiply by 10 again. The unit name and pricing presentation must be read together.

A 500 GB provisioned volume does not automatically turn into an 80 GB bill simply because files occupy 80 GB in the filesystem. For resources existing part of a month, apply the service's time proration. The Block Volume price list describes proration by the number of seconds in the month, with the corresponding minimum duration. See [Storage notes in the OCI Price List](https://www.oracle.com/cloud/price-list/).

### 7.2. GB-Months, Requests, and Bandwidth Are Not the Same Quantity

When encountering the following units, keep them on separate lines:

| Unit | Quantity described | Common mistake |
| --- | --- | --- |
| GB RAM-hours | Memory allocated to compute over time | Confusing with disk capacity |
| GB capacity-months | Storage over a period of time | Applying VM runtime hours to a volume kept all month |
| GB transferred | Amount of data crossing a billable path | Confusing with stored data size |
| Mbps-hours | Bandwidth capacity measured over time | Confusing Mbps with GB or MB/s |
| Price per 10,000 requests | A block of request counts | Multiplying total requests directly by the whole-block price |

Arithmetic example: if the unit price is `P` USD per 10,000 requests, then 5,000,000 requests correspond to `500 × P` before applying other billing rules.

GB and GiB also differ in unit base. When exporting configurations or building spreadsheets, keep the exact unit provided by the service and convert deliberately when needed; avoid applying the same "GB" label to numbers from two different bases.

## 8. Comparing by Work Output and Availability

### 8.1. Hourly Price Is Only One Angle

Suppose we measure the same batch job with identical input data, verify identical output, and look only at CPU plus RAM:

| Hypothetical option | Cost per hour | Completion time | Cost per run |
| --- | ---: | ---: | ---: |
| A | 0.128 USD | 4 hours | 0.512 USD |
| B | 0.140 USD | 3 hours | 0.420 USD |

B is more expensive per hour yet cheaper per completed job run. This conclusion is based on hypothetical test measurements; do not infer it directly from vCPU counts or architecture names.

For APIs, a useful metric is:

```text
Cost per million successful requests
  = Cost in measurement window
    / Successful requests in measurement window
    × 1,000,000
```

Only compare windows meeting the same latency and error-rate criteria. An option that drops many requests or raises latency excessively does not satisfy the same requirement, even if total cost divided by submitted requests appears low.

For Java applications, keep JDK version, heap configuration, JVM warm-up window, test data, and database path consistent. If one option hits a disk or database bottleneck while the other does not, document the cause rather than attributing the entire difference to OCPUs.

### 8.2. Account for Sufficient Redundant Capacity

Suppose the application requires two x86 VMs from the example in section 4 to satisfy the chosen deployment design:

```text
CPU and RAM for two VMs = 2 × 92.16 = 184.32 USD/30 days
```

You must add each VM's boot volume, shared storage, load balancer, and related resources. This is still not the entire application bill.

At the same time, two VMs do not by themselves prove the system survives losing one VM. If each VM handles only 60% of peak load, two VMs meet load when both are healthy, but the remaining VM will overload when the other fails. Estimates must start from the remaining capacity required after the chosen failure event, not just total OCPUs during normal operation.

Keep the following aspects consistent across compared options:

- Target traffic volume and acceptable latency.
- Instance or node count, placement, and redundant capacity.
- Data capacity, backups, and recovery objectives.
- Operating schedule, baseline load, and traffic spikes.
- Operational effort the team must handle.

## 9. Process for Building a Reconcilable Comparison Sheet

### Step 1: Lock Workload Requirements

Write a short specification, such as: "Java API must sustain 300 requests/second, p95 under 250 ms; 200 GB data; continue serving when one application VM goes down." This is an input for sizing and benchmarking, not proof that a particular configuration satisfies the requirement.

### Step 2: Record Configuration and Duration

For each option, record shape, architecture, OCPU/vCPU or ECPU, RAM, replica count, running intervals, and configuration changes. Do not just write "CPU = 4."

### Step 3: Create One Line per Pricing Component

Working table template:

| Component | Identifiers to preserve | Usage quantity | Unit price | Subtotal |
| --- | --- | --- | --- | --- |
| Application CPU | Shape, SKU, compartment | OCPU-hours | USD/OCPU-hour | `Q × P` |
| Application RAM | Corresponding RAM SKU | GB-hours | USD/GB-hour | `Q × P` |
| Database | Product, metric, edition, license | ECPU-hours or OCPU-hours | Exact SKU price | `Q × P` |
| Capacity | Resource type, storage tier | GB-months | USD/GB-month | Per billable quantity |
| Volume performance | VPU level and SKU | VPU × GB-months | Corresponding unit price | Per selected level |
| Remaining lines | Cluster, LB, requests, network... | Own unit | Own price | Compute separately then sum |

Each line should also retain price source, price retrieval date, currency, and how discounts apply. When a service already bundles a component into another SKU, note the bundling to avoid double counting.

### Step 4: Calculate Both Baseline and Peak Scenarios

Split the estimation period into intervals where resources change rather than assuming the largest configuration runs all month. Keep recovery redundancy, deployment overlap windows, and resources retained after the application stops as separate items if they exist in the design.

### Step 5: Reconcile Against Usage Data

In a tenancy with appropriate billing read permissions, use Cost Analysis or cost reports to reconcile products, SKUs, time ranges, compartments, and usage quantities. The [Autonomous Database Compute Models](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/autonomous-compute-models.html) documentation illustrates how database SKUs map to cost and usage information.

If the estimate and actual data diverge, check in order:

1. Do the units match the unit prices?
2. Were all instances, hours, and scaling events included?
3. Were any storage, backup, or service components omitted?
4. Was a bundled price component counted twice?
5. Did discounts, contract pricing, reporting lag, or timezone boundaries cause the two compared windows to differ?

Use the same time range and currency when reconciling. Do not treat an amount shown in an incomplete window as the final period bill.

### Step 6: Verify Provisioning Feasibility

A low estimate does not guarantee deployability. Required OCPUs must fit within service limits, applicable quotas, and shape availability at the deployment location. Pricing units help calculate cost; capacity constraints decide whether that configuration is available when needed. Maintain an alternative shape option with its own benchmark results and estimate when the design calls for it.

## 10. Mistakes to Spot When Reading an Estimate

| Claim or calculation | Correction |
| --- | --- |
| "Every Arm has 1 OCPU = 1 vCPU" | Check the shape family: A1 differs from A2/A4 |
| "Both have 4 vCPUs so performance must match" | Benchmark with identical workload, data, and quality targets |
| Multiplying OCPU count by the vCPU comparison price column | Use the OCPU price, or convert both quantity and price |
| Adding both comparison price and OCPU price | Count the same CPU portion only once |
| Calculating only CPU for Flex VMs | Add RAM and dependent resources |
| Using CPU utilization to directly discount a VM bill | Use that metric to decide on rightsizing |
| Applying a 4:1 ECPU rule to every product | Check the service's own metric and documentation |
| Choosing BYOL solely because the displayed price is lower | Verify the license model and appropriate entitlements |
| Assuming stopping an application drops all costs to 0 | Check OCI state and each persisting resource |
| Comparing a single VM against a redundant system | Align availability and recovery requirements |

When finishing a comparison sheet, you should be able to explain every line: **which resource is provisioned, which quantity is measured, which unit price applies, and what work output is delivered in return**. From there, cost decisions can be verified with configuration and usage data rather than relying on a single "price per CPU" figure.
