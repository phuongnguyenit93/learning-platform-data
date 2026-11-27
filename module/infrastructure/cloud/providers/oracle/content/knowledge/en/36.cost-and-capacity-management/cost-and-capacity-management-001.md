# Reading the OCI Pricing Model by Compute, Storage, and Network

In Oracle Cloud Infrastructure (OCI)'s **Cost and Capacity Management** chapter, reading the pricing model is the step that turns an infrastructure diagram into an explainable cost estimate. A Java application running on two virtual machines does not just incur "the cost of two servers": there are also RAM, boot volumes, data, backups, and network traffic serving users.

This lesson focuses on the three groups **Compute, Storage, and Network** within the scope of CLOUD_PROVIDERS_ORACLE. The goal is to correctly identify billable quantities, build an estimation formula, and recognize the impact of configuration, usage duration, data growth, and availability.

> All USD unit prices in the examples are **hypothetical figures for learning purposes**, not OCI quotes. Service rules were checked against Oracle documentation on November 21, 2026. When preparing a real estimate, use the SKU, unit, region, currency, and rate card applicable to the account at the time of calculation.

## 1. Start from the Billable Quantity

A single resource line on a diagram can generate multiple billing lines. For each line, record:

| Component to read | Meaning | Example input to record |
| --- | --- | --- |
| Service and SKU | The service and specific product code | Compute Standard of the exact shape family |
| Metric or unit | The quantity used to measure usage | OCPU-hour, GB-hour, GB-month |
| Quantity | Usage measured in that exact unit | 2,880 OCPU-hour |
| Unit price | Price per unit | USD/OCPU-hour |
| Pricing rule | Price tiers, free allowance, minimums, time-proration rules | Is RAM billed separately? |
| Applicable scope | Region, billing period, subscription, and account terms | Same month and same currency |
| Subtotal | Quantity multiplied by price after applying rules | Cost of one SKU in the period |

Starting formula:

```text
Line item cost = billable usage quantity × corresponding unit price

Infrastructure cost =
    sum of Compute lines
  + sum of Storage lines
  + sum of Network lines
  + additional services in the architecture
```

Do not add quantities with different units directly. "1,000 OCPU-hour + 500 GB-month" is not a meaningful total usage; each line must be converted into money first.

### 1.1. Distinguish List Price from Effective Price

OCI has Pay As You Go and Annual Universal Credits models. Usage is still measured by the service's metric; the effective price and payment obligation depend on the agreement. BYOL is an option for certain eligible services and must be separated from license-included options. [Source: Billing Models Offered](https://docs.oracle.com/en/cloud/get-started/subscriptions-cloud/ocpib/billing-models-offered.html).

An estimation sheet should include "price source" and "price retrieval date" columns. If contract pricing is used for Compute while list pricing is used for Network, state it clearly; otherwise, readers may assume the entire sheet received the same discount.

For committed contracts, view consumed service usage and committed payment obligations separately. Do not assume that a low-usage month automatically reduces all payment obligations accordingly.

### 1.2. Standardize Time and Capacity

Use a consistent estimation period:

- A 30-day month has 720 hours; a 31-day month has 744 hours.
- 730 hours can be used as an average planning assumption, but it must be stated explicitly.
- A machine serving only 10 hours/day across 22 workdays has 220 scheduled operating hours.
- GB, GiB, TB, and TiB must be checked against the SKU's metric definition rather than converted out of habit.

"GB-month" is capacity accumulated over time. For a resource that keeps constant capacity for half a period, a time-prorated estimation model can use half a GB-month if the service rules allow it.

Do not apply 220 Compute running hours to a boot volume that continues to exist for the entire month.

## 2. Compute: Paying for What Configuration and for How Long?

### 2.1. Read OCPU and RAM as Two Separate Lines

For the corresponding Standard Flex shapes, the price list specifies OCPU per hour and memory per GB-hour. Some other SKUs use GPU-hour or separate metrics; read the exact product line. [Source: Oracle Cloud Price List, Compute](https://www.oracle.com/cloud/price-list/#pricing-compute).

Model for a homogeneous group of machines:

```text
C_compute = N × H × (O × P_ocpu + M × P_memory)

N        : number of instances
H        : billable hours per instance
O        : OCPUs allocated per instance
M        : GB of memory allocated per instance
P_ocpu   : USD/OCPU-hour
P_memory : USD/GB-hour
```

Hypothetical example, a machine with 2 OCPU and 16 GB RAM:

```text
P_ocpu   = 0.040 USD/OCPU-hour
P_memory = 0.003 USD/GB-hour

Hourly cost = 2 × 0.040 + 16 × 0.003
            = 0.128 USD

720 hours   = 720 × 0.128
            = 92.16 USD
```

If you only multiply 2 OCPU by the OCPU price, you only calculate 57.60 USD and miss 34.56 USD for RAM.

Observed CPU percentage helps evaluate resource utilization. In this allocation model, a 2 OCPU machine averaging only 15% CPU utilization is not billed only 15% of the OCPU cost. To reduce cost, you must change the allocated resources or billable duration while still meeting load requirements.

### 2.2. OCPU Does Not Always Equal One vCPU

According to the Compute Shapes documentation:

| Architecture family | Relationship to note |
| --- | --- |
| Common x86 | 1 OCPU corresponds to 2 vCPU |
| Ampere A1 | 1 OCPU corresponds to 1 core, 1 vCPU |
| Arm A2 and A4 | 1 OCPU corresponds to 2 cores, 2 vCPU |

Check the exact shape family; do not apply the A1 rule to all Arm machines. [Source: Compute Shapes](https://docs.oracle.com/en-us/iaas/Content/Compute/References/computeshapes.htm).

When comparing two options, keep the same performance target. The label "4 CPU" might mean four vCPU or four OCPU. For a Java application, also record load-test results, JVM memory requirements, latency, and request throughput. A configuration costing less per OCPU is not necessarily cheaper per transaction.

Self-constructed example:

```text
Option A: 0.128 USD/hour, handles 200 requests/second
Option B: 0.100 USD/hour, handles 120 requests/second

Target: at least 180 requests/second, same latency requirement
```

Option B is cheaper per machine, but a single machine fails to meet the target. Decisions should be based on a complete configuration that satisfies the load.

### 2.3. Hourly Pricing and Measurement Granularity

OCI publishes Compute billing per second, with a one-minute minimum for VMs and a one-hour minimum for bare metal, then per second thereafter. Check the terms of the specific product when adding it to an estimate. [Source: Per-second billing for Compute instances](https://docs.oracle.com/en-us/iaas/releasenotes/changes/20facdce-34bf-4648-a0a7-de5db73657ce/index.htm).

Therefore, the unit "USD/hour" does not automatically mean every running session is rounded up to a full hour.

If configuration or machine count changes, split into intervals:

```text
C_compute = Σ [N_i × H_i × (O_i × P_ocpu_i + M_i × P_memory_i)]
```

For example, a system with two baseline machines running all month and three additional machines for 40 peak hours:

```text
Total instance-hours = 2 × 720 + 3 × 40
                     = 1,560 instance-hours
```

Do not multiply five machines by 720 hours if the three extra machines are only actually billed for 40 hours each. Conversely, do not omit startup time, idle waiting, or post-peak serving time if those intervals remain billable.

### 2.4. Stop, Shutdown, and Terminate Have Different Effects

Rules depend on the shape:

| Situation | Key point to check on OCI |
| --- | --- |
| Standard instance stopped via Console/API | Compute charges pause |
| Dense I/O, HPC, and many GPU shapes stopped | Billing may continue |
| VM in the GPU A10 line stopped | Listed in documentation as a case where billing pauses |
| Shutting down only inside the OS | Does not replace stopping on OCI |

Verify the exact shape before estimating savings. [Source: Resource Billing for Stopped Instances](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/resource-billing-stopped-instances.htm).

For a plan to turn off development environments outside business hours, separate two questions:

1. Which time intervals are excluded from Compute charges?
2. Which resources are retained and continue to incur costs?

Boot volumes, data, backups, and remaining services must be calculated independently. Terminating an instance should also not be interpreted as "every associated resource has definitely been deleted."

## 3. Storage: Capacity, Performance, and Access Operations

Storage does not have a single pricing model. Distinguish between disks attached to machines, object stores, and recovery copies.

### 3.1. Block Volume and Boot Volume: Provisioned Capacity

Block Volume is measured by provisioned capacity and performance tier selection. Boot volumes are billed at Block Volume pricing, separate from instance pricing. Volume backups reside in Object Storage and are measured by the storage capacity consumed by the backup. [Source: Block Volumes FAQ, Billing](https://www.oracle.com/cloud/storage/block-volumes/faq/).

For example, a 500 GB provisioned volume containing only 80 GB of data must still be estimated at 500 GB provisioned. Deleting files inside the OS does not reduce the provisioned volume capacity.

A storage inventory should list separately:

| Resource | Inputs to collect | Check against omissions |
| --- | --- | --- |
| Boot volume | Capacity, performance, lifetime | Included for every instance? |
| Data block volume | Provisioned capacity and VPUs/GB | Included the allocated free space? |
| Backup | Actual backup capacity, retention policy | Included recovery history? |
| Cross-region replica | Destination capacity and replication traffic | Included both destination storage and network? |

### 3.2. Separate Capacity Cost and Performance Cost

For Block Volume pricing lines with a VPU performance component, use the model:

```text
C_block = S × P_capacity × T
        + S × V × P_vpu × T

S          : provisioned GB capacity
V          : configured VPU/GB level
P_capacity : USD/GB-month
P_vpu      : price per VPU per month, standardized as below
T          : fraction of the monthly period
```

To check dimensions:

```text
S GB × V (VPU/GB) = total VPU

Total VPU × price USD/(VPU-month) × T month = USD
```

This formulation prevents multiplying the VPU level twice. If the quoting tool already provides **the surcharge for the entire performance level per GB-month**, use directly:

```text
C_block = S × (P_capacity + P_performance_level) × T
```

Hypothetical example:

```text
S = 500 GB
V = 10 VPU/GB
P_capacity = 0.020 USD/GB-month
P_vpu = 0.001 USD/(VPU-month)
T = 1

Capacity    = 500 × 0.020            = 10.00 USD
Performance = 500 × 10 × 0.001       =  5.00 USD
Total       = 500 × (0.020 + 0.010)  = 15.00 USD
```

If you already use the 0.010 USD/GB-month surcharge for the performance level in the example, do not multiply by 10 again.

The OCI price list states that Block Volume is prorated over time, with a one-minute minimum and per-second billing thereafter within the calendar month. Use the exact number of seconds in the given month when a granular estimate is needed. [Source: Oracle Cloud Price List, Storage](https://www.oracle.com/cloud/price-list/#pricing-storage).

### 3.3. Buying More VPUs Must Match Performance Targets

Actual performance is also constrained by the volume, instance, and attachment method. Read the IOPS and throughput limits of the configuration in use. [Source: Block Volume Performance](https://docs.oracle.com/en-us/iaas/Content/Block/Concepts/blockvolumeperformance.htm).

Reasoning example: an application needs 20,000 IOPS, but the instance or attachment path is capped below that target. Increasing volume performance alone can raise the estimate without resolving the bottleneck.

In the estimation sheet, add a "reason for performance level" column: measured IOPS, throughput, or load-test requirements. That way, VPU changes can be evaluated alongside actual benefit.

### 3.4. Object Storage: Time-Weighted Capacity and Request Counts

Object Storage measures capacity in byte-hours accumulated over the month, request counts, and data egress to the Internet; DELETE requests are listed in documentation as free. [Source: Object Storage FAQ](https://www.oracle.com/cloud/storage/object-storage/faq/).

Expanded estimation model:

```text
C_object =
    C_capacity
  + C_requests
  + C_retrieval_if_applicable
  + C_early_deletion_if_applicable
  + C_restored_copy_if_applicable
  + C_data_transfer_if_applicable
```

Include network in only one place in the summary sheet to avoid double counting.

Capacity must be time-weighted, not just the figure seen at month-end:

```text
Assume a month consists of two equal halves:

First half: 1,000 GB
Second half: 3,000 GB

GB-months = 1,000 × 0.5 + 3,000 × 0.5
          = 2,000 GB-months
```

Using 3,000 GB for the entire month overestimates this model; using only 1,000 GB misses growth.

Requests also need the right pricing unit. For example, assuming a hypothetical price of 0.004 USD per 10,000 requests and 2,000,000 billable requests:

```text
Pricing units = 2,000,000 / 10,000 = 200
C_requests    = 200 × 0.004 = 0.80 USD
```

A single application page can trigger many object calls. Do not equate user count, page views, and API requests to the object store.

### 3.5. Cheaper Tiers Must Be Read Alongside Access Conditions

| Tier | Key conditions |
| --- | --- |
| Standard | Frequently accessed data, no minimum retention period like the two tiers below |
| Infrequent Access | 31-day minimum; has retrieval charges |
| Archive | 90-day minimum; requires restore before reading and adds storage charges for the restored copy per rules |

Deleting or overwriting data so that it is removed early can incur charges for the remaining minimum retention duration. [Source: Object Storage Storage Tiers](https://docs.oracle.com/en-us/iaas/Content/Object/Concepts/understandingstoragetiers.htm).

When choosing a tier, model the entire lifecycle:

```text
Data lifecycle cost =
    storage over the retention period
  + operation requests
  + retrieval/restore and restored copy if applicable
  + data transfer
  + remaining minimum retention fee if applicable
```

Reasoning example: logs retained for only seven days are placed immediately into a tier with a much longer minimum retention period. A lower price per GB-month alone does not prove that option is cost-effective.

Backups also require actual consumed capacity metrics and data change rates. Do not assume "backups are always free," nor assume every backup consumes the full capacity of the source volume.

## 4. Network: Read Along the Data Path

### 4.1. Do Not Lump All Traffic into One Number

Tabulate the traffic flows before choosing unit prices:

| Flow | Classification needed |
| --- | --- |
| Users sending data into OCI | Inbound |
| Application sending responses or files to users outside OCI | Outbound Internet |
| Applications and services within the same region exchanging data | Intra-region |
| Replicating data to another region | Cross-region |
| On-premises enterprise systems connecting to OCI | Internet/VPN or FastConnect |
| Traffic passing through a Load Balancer | Load balancer service charges and related data transfer |

Oracle states that data movement within the same region, including between availability domains, is not charged, and the first 10 TB/month of Internet egress is free. Verify the exact terms and scope of the allowance before deducting it. [Source: Virtual Cloud Network Pricing](https://www.oracle.com/cloud/networking/virtual-cloud-network/pricing/).

Inbound traffic is listed as free; outbound unit prices beyond the threshold are grouped by origin region. Do not select pricing based on where the viewer is located. [Source: Oracle Cloud Price List, Networking](https://www.oracle.com/cloud/price-list/#pricing-networking).

Intra-region traffic having no data transfer fee does not mean every service processing that flow is free.

### 4.2. Separate Transferred GB from Bandwidth Mbps

- **GB per period**: amount of data transferred, suitable for volume-based egress models.
- **Mbps or Gbps**: rate, suitable for describing link capacity or service bandwidth metrics.
- **Mbps-hour**: bandwidth billed over a duration; not GB.

In decimal units, a link truly sustaining 100 Mbps for one hour carries a theoretical data volume of:

```text
100,000,000 bits/second × 3,600 seconds / 8
= 45,000,000,000 bytes
= 45 GB in decimal
```

This is a unit conversion to understand speed and data volume. It is not an OCI billing conversion rule, nor does it prove that a link configured at 100 Mbps always transfers a full 45 GB every hour.

To approximate application egress:

```text
Approximate egress =
    number of outbound responses × average compressed response size
  + user file downloads
  + other outbound flows
```

One million responses at 100 KB each in decimal generate about 100 GB of response payload. Add other real flows if present; use network measurements to calibrate the estimate.

### 4.3. Egress Formula with Free Allowance and Tiers

For one eligible traffic group, one threshold, and one overage price:

```text
G_billable = max(0, G_eligible - F_available)
C_egress   = G_billable × P_egress

G_eligible : GB within the exact pricing scope
F_available: remaining free allowance applicable in the period
P_egress   : price for the corresponding outbound group
```

If there are multiple tiers:

```text
C_egress = Σ (GB falling in tier k × price of tier k)
```

Inputs must share the same unit. Do not subtract a GiB measurement directly from a TB threshold without normalizing.

The free allowance may already be consumed by other workloads within the relevant billing scope. Therefore, do not re-grant the full threshold to every VM, bucket, or compartment in an application estimate. When reconciling, use the billable quantity of the exact SKU and contract terms.

### 4.4. Flexible Load Balancer Has Its Own Model

Flexible Load Balancer has a base fee and a bandwidth fee. Documentation describes per-minute measurement: billable bandwidth is the configured minimum if usage is below that level, or the actual usage of that minute if higher. [Source: Creating a Load Balancer, Bandwidth](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/managingloadbalancer_topic-Creating_Load_Balancers.htm).

Hourly-normalized estimation model:

```text
C_lb = H × P_base
     + Σ [B_billable_i × H_i × P_bandwidth]

B_billable_i : billable Mbps in interval i
P_bandwidth  : USD/(Mbps-hour)
```

Hypothetical example, an hour using only 5 Mbps when the minimum is 20 Mbps: use 20 Mbps for the bandwidth estimate of that interval. Do not use 5 Mbps, and do not assume the configured maximum if it has not been reached.

Load Balancer charges and egress charges are two distinct line items. Data delivered to users outside OCI must still be evaluated under the network rules for that path.

### 4.5. FastConnect and Cross-Region Replication

FastConnect is billed per port-hour based on port speed. According to the FAQ, private virtual circuits incur no additional OCI data transfer charges; connectivity providers may have separate fees. [Source: FastConnect FAQ](https://www.oracle.com/cloud/networking/fastconnect/faq/).

For a disaster recovery option in another region, build a separate inventory:

```text
Disaster recovery cost =
    storage resources in the destination region
  + cross-region replicated data volume
  + Compute maintained in the destination region
  + supporting services and connectivity used
```

This is an architectural inventory model, not a fixed percentage surcharge. Source data volume, data change rate, sync frequency, and DR operating mode determine the quantities to enter in each line.

## 5. Comprehensive Example: 30-Day Estimate for a Java Application Tier

### 5.1. Assumptions and Estimation Boundaries

A team deploys an application tier consisting of:

- Two Standard Flex VMs, each with 2 OCPU, 16 GB RAM, billed for 720 hours.
- Each machine has one 50 GB boot volume and one 250 GB data volume.
- All 600 GB of block storage remains constant all month at a hypothetical 10 VPU/GB level.
- Object Storage has an average capacity of 1,000 GB during the month.
- There are 2,000,000 billable Object Storage requests.
- Eligible outbound traffic is 5,000 GB; remaining applicable free allowance for this problem is 2,000 GB.
- One Flexible Load Balancer exists for 720 hours, assuming steady billable bandwidth of 20 Mbps.

**The 2,000 GB here is a hypothetical remaining input for the problem**, not a statement of a per-application OCI quota.

The example is pre-tax, before discounts and credits. The stated quantities are hypothetical billable amounts, except egress still requires subtracting the given free allowance.

This scope excludes databases, backups, logging, DNS, WAF, or paid software licenses. When a real architecture includes those components, their lines must be added. If using a managed Oracle Database, obtain the SKU and licensing option of the database service itself.

### 5.2. Hypothetical Unit Price Set

| Price line | Hypothetical unit price | Unit |
| --- | ---: | --- |
| Compute OCPU | 0.040 | USD/OCPU-hour |
| Compute memory | 0.003 | USD/GB-hour |
| Block capacity | 0.020 | USD/GB-month |
| Block performance | 0.001 | USD/(VPU-month), multiplied by total VPUs |
| Object capacity | 0.015 | USD/GB-month |
| Object request | 0.004 | USD/10,000 requests |
| Egress above given free allowance | 0.020 | USD/GB |
| Load Balancer base | 0.010 | USD/hour |
| Load Balancer bandwidth | 0.0001 | USD/(Mbps-hour) |

These prices are set to illustrate the calculations. Do not use them for purchasing decisions.

### 5.3. Calculate Each Line Before Summing

| Component | Calculation | Hypothetical cost, USD |
| --- | --- | ---: |
| OCPU for two VMs | 2 × 2 × 720 × 0.040 | 115.20 |
| RAM for two VMs | 2 × 16 × 720 × 0.003 | 69.12 |
| Block capacity, boot and data | 600 × 0.020 | 12.00 |
| Block performance | 600 × 10 × 0.001 | 6.00 |
| Average object capacity | 1,000 × 0.015 | 15.00 |
| Object requests | 2,000,000 / 10,000 × 0.004 | 0.80 |
| Billable egress | max(0, 5,000 − 2,000) × 0.020 | 60.00 |
| Load Balancer base | 720 × 0.010 | 7.20 |
| Load Balancer bandwidth | 720 × 20 × 0.0001 | 1.44 |
| **Total within hypothetical scope** | **Sum of the nine lines above** | **286.76** |

Compute totals 184.32 USD, Storage totals 33.80 USD, and Network plus Load Balancer totals 68.64 USD.

This table helps explain variances: increasing RAM changes the RAM line; increasing file downloads changes egress; increasing VPUs changes block performance. You do not need to rebuild the whole model when one input changes.

### 5.4. Three Changes and Estimated Impact

**Running the two VMs for only 220 hours in the month**, assuming Compute charges actually pause outside working hours:

```text
New Compute = 2 × 220 × (2 × 0.040 + 16 × 0.003)
            = 56.32 USD

Compute reduction = 184.32 − 56.32 = 128.00 USD
```

If all remaining components stay as shown in the table, the total drops to 158.76 USD. This is the result of assuming other lines remain unchanged; storage or Load Balancer charges cannot automatically be reduced in proportion to VM runtime.

**Reducing RAM per VM from 16 GB to 12 GB**, still running 720 hours:

```text
RAM cost reduction = 2 × (16 − 12) × 720 × 0.003
                   = 17.28 USD/month
```

Before applying, measure heap, off-heap memory, OS usage, and latency under high load. A cheaper configuration only helps if it still meets requirements.

**Increasing block performance from 10 to 20 VPU/GB** for the entire month:

```text
Performance increase = 600 × (20 − 10) × 0.001
                     = 6.00 USD/month
```

Capacity in the example stays unchanged. If volume size also increases at the same time, both the capacity line and the performance line change.

These three calculations are three independent scenarios compared to the baseline table; do not stack them unless intentionally designing a combined scenario.

## 6. Incorporating Capacity and Availability Requirements into the Pricing Sheet

A low estimate that lacks serving capacity cannot be used to approve an architecture. Record technical assumptions alongside quantities:

| Requirement | Impact on the pricing model |
| --- | --- |
| Survive loss of one instance | Remaining instances must have enough capacity to carry the load |
| Retain 30 days of recovery data | Must estimate historical capacity and change rate |
| Cross-region disaster recovery | Adds destination storage, replication, and standby resources |
| Double file download volume | Must recalculate outbound volume and price tiers |
| Add instances for horizontal scaling | Adds OCPU, RAM, boot volumes, and related services |
| Seasonal resource scaling | Split into intervals with different durations and counts |

These are relationships for building the model, not claims that every component scales linearly. Two machines can share one bucket or one Load Balancer; do not double the entire system when only doubling the VM count.

In the two-VM example, explicitly state whether each VM can handle the full minimum load if the other fails. If each machine can only carry half of normal load, the number "two VMs" does not by itself prove availability.

Create at least three estimation columns: baseline load, expected load, and peak load. Each column keeps the same calculation method while substituting quantities with the assumptions of the corresponding scenario.

## 7. From Estimation to Reconciliation on OCI

### 7.1. Build an Input Checklist Before Using Tools

A recording template can be placed directly in the design document:

```text
Estimation period:
Currency:
Price retrieval date and source:
Region / network pricing group:
Billing model:
Compartment / environment / owner:

Compute:
  shape family, instance count, OCPU, RAM, billable hours
  OS / paid software if applicable

Storage:
  boot volume, data volume, provisioned GB, VPU/GB
  object tier, time-weighted capacity, requests, retrieval
  backups, retention period, cross-region replicas

Network:
  source → destination, transfer direction, connectivity path
  outbound GB, remaining free allowance, unit price per group
  Load Balancer base and bandwidth, FastConnect if applicable

Load, redundancy, and growth assumptions:
Components excluded from the total:
```

Oracle provides Cost Estimator to estimate monthly usage and cost. Use the tool after gathering the inputs, then check whether the added lines cover the whole architecture. [Source: Estimating Monthly Costs](https://docs.oracle.com/en-us/iaas/Content/Billing/Tasks/signingup_topic-Estimating_Costs.htm).

Do not treat a total displayed by the tool as proof that backups, network, or databases were automatically included. Output scope depends on the components and quantities entered.

### 7.2. Reconcile by SKU and Matching Time Period

Cost Analysis supports viewing costs by service, SKU, compartment, region, and related filters. Select the same time range and pay attention to UTC date boundaries. [Source: Cost Analysis](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/costanalysisoverview.htm).

A useful reconciliation sequence:

1. Select the period and currency matching the estimate.
2. Filter the scope of the application or environment being reviewed.
3. Break down by service and SKU to view OCPU, RAM, storage, and network separately.
4. Compare usage quantities first, then compare unit prices and subtotals.
5. Record root causes of variance in the assumptions for the next estimation period.

If quantity matches but cost differs, check effective price, tiers, credits, and applicable terms. If quantity differs, look for runtime, orphaned resources, actual configuration, or omitted data flows.

For detailed reports, use the billable quantity and unit of the SKU; do not assume every "usage" field is already the post-rounding or billable quantity. [Source: Cost Reports](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/costusagereportsoverview.htm).

Lines with different units must be reconciled independently. A Flex machine having two usage lines for CPU and RAM is expected in this model and does not automatically indicate double billing.

## 8. Pricing Reading Mistakes That Skew the Entire Estimate

| Mistake | How to fix the model |
| --- | --- |
| Assuming one OCPU always equals one vCPU | Check the exact shape family and architecture |
| Calculating only CPU for Flex machines | Add a RAM line with its own quantity |
| Multiplying the bill down by CPU utilization % | Use allocated resources and billable duration |
| Using active file size as billable block storage | Record provisioned volume capacity |
| Omitting boot volumes | Add a boot volume for every instance |
| Omitting performance or multiplying VPUs twice | Verify whether the rate is per VPU or for the full performance level |
| Looking only at object GB-month price | Add requests, retrieval, restore, and minimum retention when applicable |
| Using month-end object size for the whole period | Calculate time-weighted capacity |
| Deducting the full free allowance per resource | Verify allowance scope and remaining balance |
| Confusing Mbps with outbound GB transferred | Separate bandwidth capacity from total data volume |
| Stopping a VM and deleting all related lines | Inventory resources that still exist |
| Doubling VMs and doubling the entire price sheet | Separate per-machine items from shared components |
| Mixing list price, contract price, and credits into one number | Document each step from usage to payable amount |

A readable estimate must answer for every line item: **what quantity is being paid for, where the quantity comes from, which unit price applies, and which assumption will change the figure**. When these four points are clear, the pricing model becomes a tool for selecting OCI configurations, balancing cost with capacity, and tracking post-deployment variances.
