# Resource Rightsizing Based on Azure Advisor and Metrics

## 1. What Is Rightsizing and Why Do It?

In Microsoft Azure, applications are built from components such as Virtual Machines (VMs), App Service, Azure Kubernetes Service (AKS), Azure SQL Database, storage, networking, and monitoring services. At project kickoff, teams often over-provision resources to reduce capacity risk. Months later, actual utilization may be lower than expected; conversely, some resources show low CPU while hitting bottlenecks in memory, IOPS, network bandwidth, or another service limit.

**Rightsizing** is the process of adjusting resource type, size, count, or provisioning model to match **actual demand and reliability requirements**, reducing waste while preserving performance, scalability, and user-facing targets. Rightsizing does not mean blindly picking the cheapest SKU.

For example: an API runs on a **4 vCPU, 16 GiB RAM** VM; average CPU hovers around 12%, yet occasionally hits 85%. Azure Advisor flags a downsize recommendation. Looking solely at average CPU could lead a team to pick an undersized VM and trigger peak-hour timeouts. A sound decision cross-checks CPU over time, guest memory, I/O, networking, real traffic, availability requirements, and post-change cost.

In the **Cost Management** chapter of the Azure ecosystem, rightsizing is a core FinOps practice: connecting **cost data** with **utilization and operational outcomes**, then verifying savings after the change.

After this lesson, you will be able to:

- Distinguish rightsizing from autoscaling, shutdown/scheduling, and commitment purchasing.
- Use **Azure Advisor** recommendations as analysis candidates alongside **Azure Monitor metrics**, VM insights, and **Cost Management** data.
- Select appropriate time windows, metrics, and thresholds for VMs, App Service, AKS, SQL, and storage; recognize when low CPU does not mean idle capacity.
- Compare keeping current sizing, downsizing SKUs, or switching operational models, with conditional savings estimates.
- Plan canary testing, monitoring, rollback, and post-rightsizing verification without violating application SLOs.

## 2. How Does Rightsizing Differ from Other Cost Optimizations?

| Measure | Impact | Example | Limitations |
| --- | --- | --- | --- |
| **Rightsizing** | Re-selects appropriate resource size/type or instance count | Moving VM from 4 vCPU/16 GiB to 2 vCPU/8 GiB when data proves sufficient | Must evaluate CPU, memory, I/O, network, quotas, and disruption |
| **Autoscaling** | Dynamically adjusts instance count/capacity via load rules | App Service scale-out on traffic, AKS HPA | Does not fix poorly chosen base SKUs; min/max bounds can still waste |
| **Scheduling / stop** | Halts or scales down resources off-hours | Shutting down lab VMs at night | Unsuitable for 24/7 systems; non-compute fees persist |
| **Reserved Instances / Savings Plan** | Lowers unit rate via usage commitments per product terms | Buying commitments for steady workloads | Does not remove idle capacity; carries wrong-scope risk |
| **Tier / architecture optimization** | Changes service model or storage tier | SQL serverless for intermittent workloads, changing Blob tiers | Differences in features, latency, transaction fees, and ops |
| **Deleting unused resources** | Eliminates resources no longer needed | Cleaning up expired test VMs | Requires verifying owner, dependencies, data, and retention |

Rightsizing should typically occur **before** locking in long-term price commitments: buying commitments for unneeded capacity lowers the unit rate while still paying for excess waste.

~~~mermaid
flowchart TD
    A["Inventory and actual costs"] --> B["Azure Advisor: candidate list"]
    B --> C["Azure Monitor: load and limits"]
    C --> D["Assess SLOs, dependencies, risks"]
    D --> E{"Sufficient evidence?"}
    E -->|No| F["Add telemetry / observe longer"]
    F --> C
    E -->|Yes| G["Compare SKUs and total cost"]
    G --> H["Test on canary / staging"]
    H --> I{"Health checks pass?"}
    I -->|No| J["Rollback and analyze"]
    I -->|Yes| K["Roll out and measure actual savings"]
~~~

## 3. Three Data Sources to Combine

### 3.1 Azure Advisor: Finding Candidates and Hypotheses

**Azure Advisor** provides tailored recommendations for Azure resources and service telemetry, spanning **Cost** alongside Performance, Reliability, Security, and Operational Excellence. With proper permissions and supported resources, you can see suggestions for underutilized resources, shutting down idle ones, or resizing; recommendation scope, calculations, and eligibility **depend on resource type and timing**.

In the Azure Portal, open **Advisor → Cost**, filter by subscription/resource group or resource type, and review each recommendation. Record:

- Resource ID, subscription, owner, environment, tags, and resource type.
- The problem/impact Advisor flags and the **specific suggestion** (resize, shutdown, or other adjustment).
- **Estimated** savings, calculation assumptions, and last updated timestamp.
- Links to underlying metrics/eligibility criteria (if provided by the UI).
- SLA/SLO risks, feature limits, related costs, and decision status.

**Advisor is an analytical signal, not an order to execute immediately.** Having zero recommendations does not prove resources are optimal; having a recommendation does not prove a change is safe. Advisor may lack guest telemetry, ignore month-end batch spikes or unusual traffic patterns, and exclude certain resource types.

### 3.2 Azure Monitor Metrics: Proving Capacity

**Azure Monitor Metrics** holds platform-level resource metrics and supports charting, aggregation selection, time ranges, and alerting. For VMs, a common signal is **Percentage CPU**; network, disk throughput, IOPS, latency, VM availability, and host-level metrics must be selected per VM/disk type.

Questions to answer before rightsizing:

1. What are **average, p95, and peak** CPU across business hours and spike windows?
2. How much RAM remains free during peak load, and is there swapping, OOM, or memory pressure?
3. Are disk IOPS, throughput, latency, queue depth, or **VM-size and disk-SKU limits** being approached?
4. Are network bandwidth, connection counts, packet rates, and NIC/SKU limits sufficient?
5. Are there batch jobs, backups, indexing, ETL, financial closes, or periodic events absent from the measurement window?
6. If one instance fails, can surviving instances carry the load? Does rightsizing eliminate required failover headroom?

**Important note:** Guest-level metrics, especially **used RAM**, may require the Azure Monitor Agent/VM insights or custom collection. Never assume "Azure Monitor always has RAM for every VM." If data is missing, add instrumentation or run controlled testing first.

### 3.3 Cost Management: Measuring Real Economic Value

**Microsoft Cost Management** reports costs by subscription, resource, tag, service, and time window (depending on permissions and billing account type). Data arrives with latency and reflects discounts, reservations/savings plans, allocation rules, and taxes/currency.

From Cost Analysis/exports, gather **allocated spend**, compute charges, and fees that do not disappear when downsizing a VM: disks, snapshots/backups, public IPs, outbound traffic, load balancers, monitoring, and licenses. For resources covered by reservations/savings plans, distinguish **internal cost allocation** from **actual net cash reduction**.

For example, shrinking a VM size while keeping the exact same disks and log ingestion reduces compute without yielding a **proportional drop in total solution cost**.

## 4. Selecting Time Windows and Normalizing Baselines

### 4.1 Long Enough to Capture Seasonality and Peaks

Never base rightsizing on a few hours of CPU graphs. The right observation window depends on business cycles. A practical rule of thumb is collecting **at least 30 days**, extending to **60–90 days or more** if monthly/quarterly peaks, holidays, or seasonal swings exist; this is an **analytical guideline**, not a fixed Advisor default.

Inspect:

- Off-peak hours, peak hours, weekdays, and weekends.
- Nightly batch jobs, backups, month-end reports, and campaign surges.
- Actual request traffic; if a workload suffered an outage or throttling, low CPU may simply mean traffic wasn't reaching it.
- Percentage of missing metrics, sampling, sample counts, and scaling/deployment timestamps.
- Growth forecasts and upcoming release changes.

**Pair percentiles with meaningful peaks:** A 15% average CPU does not rule out 95% spikes; the p95 of **hourly averages** is not the p95 of 1-minute samples, and hides multi-second bursts. Check aggregation and time grain before comparing thresholds.

### 4.2 Baselines Must Include SLIs

Rightsizing targets cost, yet outcomes must protect user **SLIs/SLOs**. For a VM-hosted API:

| Category | Required Baseline | Risk Signals |
| --- | --- | --- |
| User experience | p95/p99 request latency, HTTP/business success rate | Rising latency, timeouts, business errors |
| CPU | Average, peak, by peak business windows | CPU saturation, throttling, run-queue buildup |
| Guest memory | Used/available, swap, page faults, OOM | Memory pressure after cutting RAM |
| Disk | Read/write throughput, IOPS, latency, queue, tier caps | Hitting VM or disk caps, latency spikes |
| Network | Bytes/s, connections, VM/NIC caps, packet drops if available | Transfer bottlenecks, dropped connections |
| Availability | Healthy replicas, failover capacity, zones, spare headroom | Insufficient capacity when one node fails |
| Cost | Monthly compute spend, discounts, accompanying fees | Paper savings that fail to lower total bill |

A well-defined target states: "Reduce API compute cost by **at least 15%** in the first full month, while keeping success SLI ≥ **99.9%**, p95 latency ≤ **300 ms** under representative load, and surviving single-instance failure." These numbers are **illustrative only**; set targets based on real business needs.

## 5. Reading Key Metrics by Resource Type

### 5.1 Azure Virtual Machines

CPU describes only one dimension of a VM size. A low-CPU VM may still require:

- Large **RAM** for caches or JVM heaps, causing smaller VMs to OOM.
- Multiple disks or high IOPS/throughput; smaller VM sizes impose lower aggregate disk I/O limits.
- High network bandwidth, accelerated networking, or NIC/connection limits unsupported by smaller sizes.
- Specific CPU families/architectures, GPU features, local temp disks, or local storage sizes.
- Burst headroom while another node is down or before autoscale completes.

For example, Dsv5 SKUs like **Standard_D4s_v5** (4 vCPU, 16 GiB RAM) and **Standard_D2s_v5** (2 vCPU, 8 GiB RAM) illustrate stepping down one size; **never assume** quotas, disk/network caps, regional availability, and availability zones remain identical. Verify SKU availability in the target region/zone and check live quotas.

### 5.2 App Service

Rightsizing App Service can involve changing the **App Service plan SKU/tier**, lowering instance counts, or tuning autoscale min/max bounds. Check:

- Per-instance and peak CPU, memory, and HTTP response times.
- How many apps **share the same App Service plan**: lowering the tier affects every app on that plan, not just the one under review.
- Tier-gated features: deployment slots, scale-out limits, networking features, zone redundancy, and connection caps.
- Cold starts, warm-up, health checks, staging slots, and rollback readiness.

**Do not downgrade an App Service plan just because one web app gets little traffic** if the plan also hosts workers or other APIs. Every tier change must audit feature dependencies and co-hosted apps.

### 5.3 AKS

In AKS, distinguish **pod resource requests/limits**, actual usage, **node pool VM SKUs**, node counts, and **HPA/VPA/Cluster Autoscaler** settings as configured and supported. Low cluster-wide CPU often stems from inflated pod requests preventing Kubernetes from bin-packing efficiently, or intentional spare capacity held for SLOs.

Before shrinking node size or count:

1. Inspect **per-pod** CPU/memory, `OOMKilled` events, throttling, and requests vs. usage at peak load.
2. Confirm the scheduler can place workloads onto smaller nodes, factoring in **`maxPods`, taints, affinity, topology spread, DaemonSets, and system pods**.
3. Check `PodDisruptionBudget`, `maxUnavailable`, autoscaler min/max, and surge capacity needed during upgrades or node failures.
4. Test on a canary node pool, measuring ingress performance, queues, DB connections, and scale-up times.

Cutting node count by 20% may not cut the bill by 20% if workloads still consume reserved capacity, system node pools use different SKUs, or disks, load balancers, and traffic persist.

### 5.4 Azure SQL Database and Data Services

For Azure SQL, evaluate tier/compute choices using CPU, data I/O, log write I/O, storage, connections, query duration, waits, and tier features. Metrics differ across **DTU/vCore**, provisioned/serverless, and database engines; select the exact service metrics in Azure Monitor.

Low CPU paired with high query latency can indicate lock contention, I/O bottlenecks, or poorly tuned queries. Before downsizing, inspect execution plans, query performance, batch peaks, scaling speed, and failover impact. If evaluating serverless for eligible workloads, factor in minimum vCores, auto-pause/warm-up behavior where supported, and workload patterns—never treat a single CPU percentage as proof of savings.

### 5.5 Storage and Other Services

Storage rightsizing can mean adjusting access tiers, disk types, or provisioned performance; balance **capacity, access frequency, operation costs, egress, rehydration/retrieval fees, latency, retention, and durability**. For Azure Managed Disks, performance depends on both the disk SKU/size and the VM size. Low used capacity does not automatically allow downgrading disk tiers if the app depends on provisioned IOPS.

For message brokers, caches, or other managed databases, inspect resource-specific metrics (throughput, queue depth, memory, evictions, connections, errors) and feature caps on the target SKU.

## 6. Lab 1: Finding Candidates in Azure Advisor

### 6.1 Checking Context and Fetching Recommendations

Using Azure CLI in a signed-in terminal with subscription read access:

~~~bash
# Confirm the active subscription before analyzing.
az account show \
  --query "{subscription:id,name:name,tenantId:tenantId}" -o table

# Select the target subscription. Replace placeholder with actual ID.
az account set --subscription "<subscription-id>"

# Fetch all recommendations to inspect structure and scope.
az advisor recommendation list --output json

# Optionally filter Cost category if supported by CLI/extension version.
az advisor recommendation list --category Cost --output json
~~~

These commands are **read-only** and do not resize anything. In the Portal, open **Azure Advisor → Cost** to review recommendations, impact, affected resources, estimated savings, and explanatory fields. Check your CLI version's actual schema and flags before automating JSON parsing.

**Never batch-resize the entire recommendation list automatically.** First assign owners, classify environments, pull SLO data, check maintenance calendars, and decide approve/reject per item. When postponing or dismissing a recommendation, record the **reason and review date** so dismissals do not become permanent blind spots.

### 6.2 Building an Actionable Candidate List

Hypothetical triage table:

| Resource | Advisor Suggestion | Initial Decision | Rationale |
| --- | --- | --- | --- |
| VM `vm-orders-api-02` | Downsize due to low utilization | **Analyze further** | Need guest RAM, CPU peaks, and disk/network caps |
| VM `vm-lab-report` | Shut down/resize idle resource | **Evaluate stop schedule** | Business hours only; check batch jobs |
| App Service plan `asp-orders` | Review capacity/cost | **Hold** | Hosts 3 shared apps; missing per-app metrics |
| SQL `sqldb-orders` | Review compute tier | **Hold** | Month-end peaks; query latency rising |

Recommendations in this table are **learning scenarios**, not output from any live subscription. Before finalizing changes, collect current observational data.

## 7. Lab 2: Inspecting VM and Azure Monitor Metrics

### 7.1 Confirming Current VM Size

~~~bash
RG="rg-cost-lab"
VM="vm-orders-api-02"

# Read current VM configuration without modifying resources.
az vm show \
  --resource-group "$RG" \
  --name "$VM" \
  --query "{id:id,location:location,size:hardwareProfile.vmSize}" \
  -o json

VM_ID=$(az vm show --resource-group "$RG" --name "$VM" --query id -o tsv)
~~~

Match the VM ID against the Advisor recommendation and Cost Management records. Two similarly named VMs in different subscriptions or resource groups can have very different specs, loads, and policies.

### 7.2 Inspecting CPU Across Multiple Windows

Set two UTC timestamps for your target window. The command below fetches 1-hour buckets:

~~~bash
# Example: replace timestamps with the 30-day analysis window (ISO 8601 UTC).
START_UTC="2026-10-01T00:00:00Z"
END_UTC="2026-10-31T00:00:00Z"

az monitor metrics list \
  --resource "$VM_ID" \
  --metric "Percentage CPU" \
  --start-time "$START_UTC" \
  --end-time "$END_UTC" \
  --interval PT1H \
  --aggregation Average Maximum \
  --output json
~~~

`Percentage CPU` and available aggregations depend on resource namespace; check metric definitions if CLI returns an error. **Hourly Average** shows baseline load, while **Hourly Maximum** reveals spikes within each bucket. Never compare an hourly average against a 1-minute maximum as if they share the same resolution.

To inspect 5-minute peaks, switch to `--interval PT5M` where metrics, retention, and query limits allow; split wide date ranges into smaller chunks if needed. Retention, granularity, and API limits vary by data source and configuration.

### 7.3 Adding RAM, Disk, and Network

For a VM:

- **RAM:** Enable/read guest metrics via Azure Monitor Agent/VM insights or another reliable collector. Check peak `Available Memory`, swap/commit, and memory pressure; exact metric names depend on collector setup.
- **Disk:** Inspect IOPS, throughput, latency, queue depth, and disk/VM capping metrics in Azure Monitor. Downsizing to a VM whose disk throughput cap sits below peak will keep CPU looking fine while stalling disk I/O.
- **Network:** Compare peak in/out, retries, packet drops, and VM/NIC caps, especially for ingress/egress-heavy workloads.
- **Application SLIs:** Inspect response latency, errors/timeouts, and queue depth from Azure Monitor/Application Insights; CPU is a diagnostic signal, not the user-facing service goal.

Outside peak traffic, a sample dataset might show 11% mean CPU, 28% p95 CPU, 84% max CPU, 7.5 GiB peak RAM, and 80 MB/s peak disk throughput. Cutting RAM from 16 to 8 GiB when guest peak already hits 7.5 GiB is **unsafe** without headroom and testing, regardless of low CPU. These numbers simply illustrate the reasoning.

### 7.4 KQL Example When Metrics Are Exported to Log Analytics

By default, not all platform metrics land automatically in Log Analytics' `AzureMetrics` table. The example below works only if the workspace already receives `AzureMetrics` rows via diagnostic settings/export; verify actual field and metric names before running:

~~~kusto
let vmId = tolower(
    "/subscriptions/<subscription-id>/resourceGroups/rg-cost-lab/providers/Microsoft.Compute/virtualMachines/vm-orders-api-02"
);
AzureMetrics
| where TimeGenerated >= ago(30d)
| where tolower(ResourceId) == vmId
| where MetricName == "Percentage CPU"
| summarize
    Samples = count(),
    AvgOfBucketAvgs = avg(Average),
    P95OfBucketAvgs = percentile(Average, 95),
    HighestBucketMaximum = max(Maximum)
| project Samples, AvgOfBucketAvgs, P95OfBucketAvgs, HighestBucketMaximum
~~~

`P95OfBucketAvgs` is the p95 of **already-aggregated bucket averages**, not the p95 of raw CPU samples. If sampling, export gaps, or missing series undermine accuracy, verify using Metrics Explorer/API or other telemetry.

## 8. Making the Decision: From Data to Candidate SKU

### 8.1 Decision Matrix for a Hypothetical VM

Suppose a `Standard_D4s_v5` VM (4 vCPU, 16 GiB) serves an API. Azure Advisor suggests resizing. After 45 days of observation:

| Criterion | Hypothetical Observation | Assessment |
| --- | --- | --- |
| CPU median / p95 | 14% / 32% | Indicates spare CPU most of the time |
| CPU max in peak windows | 86% during brief bursts | Check burst duration and growth trend |
| Guest RAM peak | 9.2 GiB | **Cannot** drop directly to an 8 GiB VM without memory tuning |
| Disk IOPS/throughput peak | Below current SKU cap | Must check against smaller SKU's cap |
| Network peak | Spikes during report exports | Check candidate VM/NIC cap |
| Application SLIs | 99.95% success, 190 ms p95 | Must remain stable after resize |
| Failover headroom | Surviving node takes 2× load on failure | Preserve N−1 fault tolerance |

Correct conclusion right now: **not yet eligible to downsize from `Standard_D4s_v5` to `Standard_D2s_v5`**, because 9.2 GiB peak RAM exceeds the target SKU's 8 GiB before even counting OS overhead and headroom. You could optimize app memory/caches or select a different SKU family with a higher RAM-to-vCPU ratio, then re-measure.

A mature process prioritizes **real bottlenecks and SLOs** over mechanically following "low CPU" prompts.

### 8.2 Checking SKUs, Quotas, and Service Limits

Example command to inspect available SKUs in a region (results also depend on subscription restrictions, zones, and quotas):

~~~bash
az vm list-skus \
  --location southeastasia \
  --resource-type virtualMachines \
  --size Standard_D2s_v5 \
  --output table
~~~

Consult SKU documentation for vCPU/RAM, temp disk, max data disks, uncached/cached IOPS, storage throughput, network bandwidth, accelerated networking, architecture, zones, and limits. Then verify live allocation availability, VM quotas, and availability set/VMSS/cluster constraints. A SKU query output **does not guarantee** a resize call will always succeed at runtime.

### 8.3 When to Downsize SKUs, Cut Instances, or Change Architecture?

| Load Pattern | Promising Direction | Conditions |
| --- | --- | --- |
| Steady load; CPU/memory/disk/network low with clear headroom | Step down one SKU tier | Verify target size caps, SLOs, and failover |
| Highly variable load with long idle spans | Autoscale or suitable serverless option | Scale latency, cold starts, quotas, and cost |
| Many instances running very lightly | Controlled reduction of min replicas/nodes | Preserve HA, quorum, peaks, and maintenance capacity |
| Dev VMs used only during work hours | Scheduled stop/start or automation | Check batch dependencies/owners; account for disk/IP fees |
| Low CPU but high RAM | Memory-optimized SKU or heap/cache tuning | Sufficient RAM and disk/network caps; recalculate total cost |
| IOPS/latency is the bottleneck | Optimize disk tier, caching, or I/O pattern | Never downsize VMs below needed IOPS/throughput |
| Covered by Reservation/Savings Plan | Evaluate commitment impact before resizing | Avoid stranded commitment charges across the term |

## 9. Calculating Savings: Estimates vs. Actual Cost

### 9.1 Basic Formula

For hourly-billed workloads:

\[
\mathrm{SavingsMonth}_{compute}
=(\mathrm{PriceOldHourly}-\mathrm{PriceNewHourly})
\times \mathrm{HoursUsed}\times \mathrm{InstanceCount}.
\]

Using **purely hypothetical prices** for calculation practice—not Azure retail rates: an old VM has an effective compute price of **0.20 USD/hour**, the new VM is **0.10 USD/hour**, running **730 hours/month**:

\[
(0.20-0.10)\times730=73\ \text{USD/month for one VM}.
\]

Across **5 VMs** meeting the same conditions:

\[
73\times5=365\ \text{USD/month};
\qquad 365\times12=4,380\ \text{USD/year (estimated)}.
\]

Do not present that result as **"50% off total application spend."** It reflects only the hypothetical compute delta assuming identical runtime hours and no other rate factors. Real pricing depends on region, OS/licensing, purchasing mode, discounts, reservations, savings plans, taxes, currency, zones, and timing.

### 9.2 Total Cost of Ownership (TCO) of the Change

Checklist before claiming savings:

| Line Item | Changes When Shrinking VM Size? | Notes |
| --- | --- | --- |
| Hourly compute | Usually yes | Depends on SKU, purchasing model, and commitments |
| Provisioned disks | Usually **no** | Disk capacity/tier stays unchanged unless modified separately |
| Snapshots/backups | Possibly no | Depends on retention and data volume |
| Network egress/load balancer | Not guaranteed | Depends on traffic and resource types |
| Log ingestion/monitoring | Possibly no | Depends on log/metric volume and retention |
| License/OS | Depends on SKU and licensing | Check license benefits and billing terms |
| Reserved capacity/savings plan | Must evaluate separately | Effective cash/amortized impact differs from PAYG |
| Engineering effort, testing, risk | One-time and ongoing operational cost | Can make minor short-term savings unattractive |

**Payback period** helps prioritize work:

\[
\mathrm{PaybackMonths}=
\frac{\mathrm{OneTimeChangeCost}}
{\mathrm{MonthlyNetSavings}}.
\]

Suppose engineering and testing take **600 USD** of effort for **150 USD/month** in net savings: payback takes **4 months**, assuming load and pricing hold steady. Also factor in downtime risk; financial savings do not justify breaching availability commitments.

### 9.3 Closing the Loop After One Billing Cycle

Post-rollout, compare Cost Management before and after across **identical scope, tags, charge model, and period length**. Isolate effects from traffic shifts, other SKU edits, service rate changes, reservations, FX rates, and new charges. In shared environments, measure savings by resource/charge type rather than subscription grand totals alone.

If allocation noise prevents proving savings, report **net savings unverified** rather than treating Advisor's upfront estimate as realized savings.

## 10. Safe Rollout and Rollback Plan

Resizing VMs or App Service plans can trigger restarts, downtime, or lost headroom. In production, use a change record and maintenance window:

1. **Preflight:** Confirm owner, scope, old/new SKUs, quotas, dependencies, backups, monitoring, RBAC permissions, and low-impact timing.
2. **Lock baseline:** Record SLI success/latency, CPU/RAM/disk/network, costs, and traffic rates by version.
3. **Start small:** Resize one canary instance or a matching staging environment first. If there is only **a single VM** without redundancy, explicitly disclose disruption risk and prepare restore steps.
4. **Preserve rollback:** Record the original SKU, boot/extension/OS configs, verify ability to resize back plus quota/capacity, and back up data as needed.
5. **Monitor:** Watch readiness, SLIs, CPU/memory pressure, disk latency, network throughput, and queues across at least one representative peak.
6. **Decide:** If health/SLOs degrade or spare capacity falls short, roll back or halt rollout; proceed in waves only when healthy.
7. **Post-check:** After a representative billing/load cycle, verify actual costs and refreshed recommendations; update inventory, budgets, and runbooks.

### 10.1 VM Resize Command — Approved Changes Only

The illustrative command below **modifies a live VM**. It may require a restart/deallocation, cause downtime, or alter allocation/attached capabilities depending on VM/size; never run it on production merely to "test if it saves money."

~~~bash
# Illustrative only within an approved change plan:
az vm resize \
  --resource-group rg-cost-lab \
  --name vm-orders-api-02 \
  --size Standard_D2s_v5

# Verify after the change:
az vm show \
  --resource-group rg-cost-lab \
  --name vm-orders-api-02 \
  --query "{size:hardwareProfile.vmSize,provisioningState:provisioningState}" \
  -o json
~~~

Do not treat `provisioningState: Succeeded` as proof the application is healthy. Run end-to-end checks and watch guest memory, disk/network, and workloads through peak hours. For rollback, confirm the prior SKU remains available and test-verify the resize-back procedure in emergency runbooks.

### 10.2 Using SLIs as Rollback Gates

Pre-defined thresholds before changing:

| Metric | Baseline | Stop / Rollback Trigger (Example) |
| --- | --- | --- |
| API success rate | ≥ 99.9% | Below 99.5% within evaluation window with sufficient traffic |
| p95 latency | 180 ms | Above 300 ms for 10 minutes under comparable traffic |
| Guest RAM | Peak within safe margin | Swapping/OOM or available memory drops below approved headroom |
| Disk I/O | Clear headroom | Sustained high I/O latency or disk/VM throttling |
| Network | Spare bandwidth | Unusual rise in packet drops or connection timeouts |
| Availability | Survives 1 instance loss | Insufficient capacity for target failover scenario |

Thresholds are **illustrative** and must come from real SLOs and baselines. Missing metrics never count as a PASS; if telemetry drops out right after downsizing, verify health across other layers immediately.

## 11. Common Mistakes

| Flawed Claim or Action | Why It Fails | Fix |
| --- | --- | --- |
| "Average CPU is under 20%, cut VM by 50%" | Peaks, RAM, disk/network, and failover may be the real constraint | Check percentiles, peaks, guest memory, and business cycles |
| "Advisor suggested it, apply immediately" | Advisor lacks full business context and hidden dependencies | Owner review, metric verification, and canary rollout |
| "No Advisor recommendations means fully optimized" | Not all resources or waste patterns trigger recommendations | Audit inventory, Cost Management, Azure Monitor, and manual reviews |
| "Stepping down one SKU always saves 50%" | Prices vary by SKU/region/discounts and non-compute fees stay | Calculate effective rates and net TCO |
| "Platform RAM metrics suffice for all VMs" | Guest memory may not be collected | Enable VM insights/AMA or another reliable source |
| "Resizing VMSS instances in place is harmless" | Rolling policies, availability, max surge, and health probes impose limits | Canary nodes, verify capacity, and plan rollback |
| "Stopping a VM stops all costs" | Disks, backups, IPs, and related items still bill; OS shutdown isn't deallocate | Check billing lines and confirm `deallocated` state |
| "Downsize AKS nodes based on average CPU" | Requests, PDBs, DaemonSets, peaks, and min-nodes may require capacity | Analyze scheduler/pods and failover headroom |
| "24 hours of metrics is enough" | Misses weekends, ETL, month/quarter-end, and rare events | Measure full business cycles and note missing data |
| "Cost went down, task complete" | Latency, error rates, or RTO/RPO may have degraded | Verify SLOs and reliability post-change |

## 12. Ownership and Rightsizing Record Checklist

Document a rightsizing decision in a concise table:

| Field | Required Details |
| --- | --- |
| Resource / owner | Resource ID, subscription, RG, service, environment, owner |
| Advisor | Recommendation ID/summary, timestamp, estimated savings, assumptions |
| Data window | 30/60/90 days, peak events, sampling/missing data |
| Utilization | CPU, guest memory, disk IOPS/throughput/latency, network, hourly profile |
| User impact | Current SLIs/SLOs, critical path, traffic peaks, HA/failover |
| Proposal | Old/new SKU, scaling policy, quotas, dependencies, feature limits |
| Cost estimate | Compute, storage, discounts, commitments, monitoring, effort cost |
| Gates | Approver, canary plan, stop triggers, rollback, recovery steps |
| Post-change | Observed metrics, errors/latency, next-cycle actual cost, verdict |
| Review schedule | Owner and next review date as traffic evolves |

Records must contain **measurable inputs and a post-change verification plan**. Rightsizing is never one-and-done; sizing needs evolve continuously as products, users, and pricing models change.

## 13. Practice Exercises and Self-Check

### Exercise 1: Why Is a Recommendation Not Enough?

Azure Advisor flags a VM for very low average CPU and recommends downsizing. 45-day metrics show 25% p95 CPU, yet peak RAM reaches 9.2 GiB while the target SKU has only 8 GiB; disk I/O also spikes heavily during reporting runs.

**Prompt:** Should you downsize immediately? What additional data is needed?

**Suggested answer:** **No.** Peak RAM already exceeds the target SKU's capacity, risking memory pressure or OOMs. Inspect guest memory peaks, disk IOPS/throughput/latency, networking, SLOs, reporting windows, failover capacity, and quotas. You may tune app/cache memory or pick a higher RAM-per-vCPU SKU and test first.

### Exercise 2: Calculating Conditional Savings

**Hypothetical** compute rates: old VM 0.24 USD/hour, new VM 0.16 USD/hour, 8 instances running 720 hours/month; instance count stays unchanged. Disk/backup and monitoring costs stay constant.

**Solution:**

\[
(0.24-0.16)\times8\times720
=460.8\ \text{USD/month, compute only}.
\]

If the new architecture adds 80 USD/month in another service, net savings drop to **380.8 USD/month** before considering discounts/commitments and implementation effort. If compute is covered by a reservation, actual cash reduction may differ from hypothetical hourly rates.

### Exercise 3: Choosing a Rollout Plan

An API runs across 4 VMs in two availability zones and must stay up if one VM fails. The team wants to downsize all 4 VMs in one night because average CPU looks great.

**Suggested answer:** Verify **N−1 capacity** on the smaller SKU, peak RAM/disk/network metrics, AZ/quota availability, rolling update capability, and SLOs. Test one canary VM, verify app/traffic health, then roll out sequentially within min-healthy limits; keep rollback ready and expand only while metrics hold steady. If N−1 capacity fails, adjust scale or architecture first.

### Self-Check Questions

1. How does rightsizing differ from autoscaling and reservations/savings plans?
2. Why is Azure Advisor only the starting point for an optimization decision?
3. Low average CPU paired with high p95 latency can point to which bottlenecks?
4. Which VM metrics must be added if Azure Monitor lacks guest RAM data?
5. Why must VM downsizing inspect both VM and disk IOPS/network caps?
6. When should you inspect 60–90 days of metrics instead of 7 days?
7. When modifying an App Service plan, why must you audit every app sharing that plan?
8. In AKS, why doesn't low cluster CPU automatically allow removing nodes?
9. How do you distinguish estimated Advisor savings from actual net savings?
10. What conditions require halting or rolling back a rightsizing test?

**Expected outcome:** You can pick a candidate from **Azure Advisor**, gather **Azure Monitor metrics** alongside application SLIs, evaluate **CPU, RAM, I/O, networking, and redundancy**, estimate conditional savings, and execute a safe rollout. A decision only succeeds when **cost savings are verified** and **performance and reliability stay on target**.
