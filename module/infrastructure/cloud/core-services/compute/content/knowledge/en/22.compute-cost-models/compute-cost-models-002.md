# On-Demand and How to Measure Resource Usage Time

On-demand is a model for consuming compute resources as needed without committing in advance to a long-term capacity purchase. Users spin up VMs, containers, or serverless workloads when needed and pay per the billing unit defined by the service. This model offers flexibility for fluctuating workloads, development and testing environments, and systems whose demand cannot yet be reliably forecasted.

To control costs, you must understand two distinct concepts: **the time a resource is provisioned and billed** and **the amount of resources actually consumed by the workload**. A VM may use only 10% CPU yet still be billed for compute for the entire time it remains in a billable state. Conversely, a stopped VM may incur no CPU fees while attached volumes, IPs, snapshots, or licenses continue generating charges.

This lesson explains how on-demand works, how to determine billable intervals, how to measure usage across VMs, containers, and serverless, how to read billing exports, allocate costs, and reconcile operational metrics with the bill.

## 1. What Is On-Demand?

On-demand is a model for provisioning resources upon request. Users select the resource type, configuration, and deployment region; the provider allocates the resource and records usage against the corresponding meter.

Common characteristics:

- No multi-month or multi-year usage commitment required.
- Resources can be created, modified, or deleted as needed.
- Costs vary by time, configuration, and billed resource quantity.
- Well-suited for unpredictable loads or short runtimes.
- Unit prices are generally higher than some committed or pre-purchased capacity options, depending on the service and terms.

On-demand does not mean every component only charges when the CPU is busy. Each resource type has its own meter. A VM may be billed for the time the instance is in a billable state; a block volume may be billed by provisioned capacity per month; network egress by data transferred; serverless by request count and execution duration.

### Example

A development team spins up 4 VMs for testing for 3 hours, then deletes them. If the compute meter charges for the duration the VMs exist in a billable state, compute cost is determined by the configuration and billable duration of the 4 VMs. If the team keeps the 4 disks after deleting the VMs, the storage meter may continue accruing charges.

On-demand gives teams agility to create and tear down resources, but it requires lifecycle and cleanup processes to prevent unused resources from continuing to incur charges.

## 2. Distinguishing Provisioned Time, Operational Time, and Utilization

Three metrics are frequently confused:

- **Provisioned time:** the duration a resource is allocated or exists in the manner the service bills for.
- **Operational time:** the duration a resource is in a state capable of operating or serving a workload.
- **Utilization:** the percentage or amount of resources actually used during that interval.

For example, an 8-vCPU VM is billed for 10 hours. During those 10 hours, average CPU busy time is only 20%. If the unit price is a fixed instance-hour rate, compute usage is still 10 instance-hours; the 20% CPU is an operational metric and does not automatically reduce the bill to 2 hours.

Similarly, a VM with 32 GiB RAM provisioned for 10 hours may still be billed by its provisioned configuration and duration even if the process only uses 8 GiB. Exact billing depends on the service; some serverless or container platforms meter by vCPU-second and GiB-second, which is a different metering model.

### Comparison Table

| Concept | Question Answered | Example |
|---|---|---|
| Provisioned time | How long is the resource held/allocated? | VM exists in a billable state for 10 hours |
| Runtime | How long does the workload actually execute? | Job runs for 42 minutes |
| Utilization | How busy is the resource during that time? | Average CPU 20% |
| Billable usage | How many billing units does the provider's meter record? | 10 instance-hours or 80 vCPU-hours |
| Charge | How much does that usage convert to in money? | Billable quantity multiplied by unit price, after adjustments |

To manage costs, track both billable usage and utilization. Billable usage explains what is charged; utilization shows whether resources are over-provisioned or used efficiently.

## 3. Time and Resource Measurement Units

Providers may use various measurement units. Always check the exact unit of each meter on the pricing page and in the billing export.

| Unit | Meaning | Common Use Cases |
|---|---|---|
| Instance-second | One instance billed for one second | Some VMs or compute services |
| Instance-minute | One instance billed for one minute | Some per-minute services |
| Instance-hour | One instance billed for one hour | Hourly VMs and capacity |
| vCPU-second / vCPU-hour | Number of vCPUs multiplied by time | Containers or CPU-metered compute |
| GiB-second / GiB-hour | Memory capacity multiplied by time | Memory-metered serverless/containers |
| GPU-hour | One GPU or accelerator type billed for one hour | GPU instances or accelerators |
| Request / invocation | One call or execution | Functions/serverless APIs |
| GB-month / GiB-month | Storage capacity multiplied by monthly duration | Volumes, snapshots, or object storage |
| GB transferred | Data crossing a network boundary | Egress or inter-region transfer |

Unit names and conversion rules can differ. GB and GiB are not identical; a billing hour may not equal 3,600 seconds of usage in every case if minimum charges or rounding apply. Do not infer rounding rules solely from the metric name.

### vCPU-hour Example

A VM with 4 vCPUs is billed for 5 hours:

\[
vCPU\text{-}hours = 4 \times 5 = 20
\]

If there are 3 VMs with the same configuration and duration:

\[
3 \times 4 \times 5 = 60\ vCPU\text{-}hours
\]

If the provider bills per fixed instance-hour, the billable quantity may be 15 instance-hours instead of 60 vCPU-hours. Use the exact meter in the billing export when calculating cost.

### Memory-Time Example

A container is allocated 2 GiB memory for 30 minutes:

\[
GiB\text{-}hours = 2 \times 0.5 = 1
\]

Some services bill CPU and memory separately; some bundle them into an instance configuration; some bill by requests and duration. Do not apply the GiB-hour formula across every compute type.

## 4. Which VM Intervals Are Billable?

A VM transitions through multiple states in its lifecycle. When a billable interval starts and ends depends on the provider, VM type, OS license, disk type, and attached services.

Common states:

| State | Operational Meaning | Billing Behavior to Verify |
|---|---|---|
| Requested / provisioning | Machine creation request submitted, platform allocating | May have specific metering rules; check billing records |
| Starting / booting | Machine is booting | Billable start may tie to allocation or running state |
| Running | Machine is active | Typically incurs compute charges by configuration and time |
| Stopping | Machine is shutting down | Determine exact point when compute meter stops |
| Stopped / deallocated | Machine stopped or compute released | Compute may stop billing, while disk/IP/license may continue |
| Hibernated / suspended | Sleep state or RAM saved to storage | Compute and storage rules depend on the service |
| Terminating / deleting | Deleting the resource | Check meter stop time and remaining attached resources |
| Terminated / deleted | Compute resource deleted | Compute typically ends; detached resources may remain |

Do not rely solely on the timestamp of clicking Start/Stop as proof. An API request may be accepted before the state transition completes. Reconcile lifecycle events with billing usage records.

### Running Does Not Always Mean the Workload Is Doing Work

A VM in the running state where the application has not started, is waiting for traffic, or has idle CPU can still accrue compute charges. This commonly happens in:
- Development environments left on overnight.
- VMs waiting for batch jobs.
- Standby instances receiving no traffic.
- Machines keeping caches or connections warm.
- Machines waiting for manual approval or action.

If a workload does not need machines continuously, consider scheduled start/stop, autoscaling, scale-to-zero, or an appropriate serverless model.

### Stopped Does Not Mean Total Cost Is Zero

After stopping a VM, the following components may still be billed:
- Boot disks or data disks.
- Snapshots and backups.
- Retained public/static IPs.
- Reserved capacity or commitments.
- Hourly or host-based licenses.
- Network appliances, NAT, or load balancers.
- Monitoring/logging services storing data.

When you need to stop costs, inspect every resource created alongside the VM and their dependencies.

## 5. How to Measure VM Usage Time

To measure billable time, collect data from both the control plane and the billing system.

### Lifecycle Data

At minimum, capture:
- Resource ID.
- Resource type and SKU/instance family.
- Region/zone.
- Creation request timestamp.
- Timestamp transitioning to running.
- Stop/deallocate timestamp.
- Terminate/delete timestamp.
- Subsequent start/stop cycles.
- Account/project/subscription.
- Cost allocation tags or labels.

Timestamps should be stored in UTC or with an explicit timezone. When computing duration, use the actual state transition timestamps if provided by the platform.

### Calculating Intervals

For a VM with a single billable interval:

\[
T_{billable} = t_{end} - t_{start}
\]

If the VM is started/stopped multiple times, sum the billable intervals:

\[
T_{total} = \sum_{k=1}^{n}(t_{end,k} - t_{start,k})
\]

This formula only determines duration from state events. The final result must be reconciled with the provider's meter quantity, since minimum durations, rounding, license meters, or special rules may apply.

### Example

A VM is created and runs from 09:10 to 12:40, then stops. Event-based duration is 3 hours 30 minutes.

If the service bills per second with no additional minimums/rounding:

\[
T = 3.5\ hours
\]

If the service bills hourly with rounding rules or minimum charges, the billable quantity may differ. Do not round up or down on your own before reading the pricing terms.

### Multiple Instances

Suppose 5 VMs have different billable run windows:

| VM | Billable start | Billable end | Event-Based Duration |
|---|---|---|---:|
| vm-a | 08:00 | 10:00 | 2 hours |
| vm-b | 08:30 | 11:30 | 3 hours |
| vm-c | 09:00 | 10:15 | 1.25 hours |
| vm-d | 10:00 | 12:00 | 2 hours |
| vm-e | 10:30 | 12:30 | 2 hours |
| **Total** |  |  | **10.25 instance-hours** |

Total instance-hours are not the same as the group's elapsed wall-clock time. The group existed from 08:00 to 12:30, which is 4.5 hours, yet total compute volume is 10.25 instance-hours.

## 6. Calculating On-Demand Cost from Billable Usage

Simple model:

\[
Cost_{compute} = \sum_i Quantity_i \times UnitPrice_i
\]

Where:
- Quantity is the recorded billable units.
- UnitPrice is the unit rate for the exact SKU, region, OS, and pricing dimension.
- i represents each meter line item or configuration interval.

The total bill may add storage, network, licenses, support, taxes, and adjustments. Do not use a single VM unit price to estimate total system cost.

### Illustrative Example

Suppose a VM type has a hypothetical unit price of 0.12 currency units per instance-hour. A team runs 3 VMs for 5 hours with no discounts or add-ons:

\[
Quantity = 3 \times 5 = 15\ instance\text{-}hours
\]

\[
Cost = 15 \times 0.12 = 1.80
\]

This is an illustrative calculation, not pricing from any specific provider. Actual prices depend on region, OS, machine type, licenses, currency, discounts, and usage timing.

### When Configuration Changes Mid-Period

If a VM resizes from 2 vCPUs to 8 vCPUs mid-day, split it into separate meter segments:

\[
Cost = Q_{small}P_{small} + Q_{large}P_{large}
\]

Do not multiply total time by the final configuration. Similarly, if changing region, OS license, or instance family, separate each SKU.

### Discounts and Credits

On-demand usage may be reduced by credits, promotions, negotiated discounts, or pricing programs. Billing exports often distinguish list cost, effective cost, net cost, or adjustments depending on the provider. Clarify whether you are analyzing:
- List price.
- Cost before discounts.
- Cost after discounts.
- Internally allocated cost.
- Actual payable amount after credits/taxes.

Do not compare two workload groups using cost columns with different definitions.

## 7. Compute Resources Are Not the Only Meter

A single VM can generate multiple independent cost lines.

| Component | Common Unit | Can It Still Charge When VM Stops? |
|---|---|---|
| Compute instance | Instance-second/hour or vCPU-time | Usually stops when compute deallocates, per service rules |
| Boot/data disk | GiB-month, provisioned IOPS, or throughput | Yes |
| Snapshot/backup | Stored capacity or operations | Yes |
| Public/static IP | IP-hour or IP retention conditions | Possibly |
| Network egress | GB transferred | Whenever traffic occurs |
| NAT/load balancer | Gateway-hour, capacity unit, processed bytes | Possibly |
| License | Hourly, per core, host, or subscription | Depends on terms |
| Monitoring/logging | Ingest, retention, queries | Yes |
| Reservation/commitment | Commitment fee | Per contract, independent of VM running state |

A stopped VM retaining a 500 GiB disk for 30 days can still generate significant storage charges. Tracking only compute instance-hours will fail to explain the full bill.

### Detached Resources

Map relationships between:
- VMs and disks.
- VMs and IPs.
- VMs and snapshots.
- VMs and load balancers/backends.
- VMs and licenses.
- VMs and log/monitoring workspaces.

When terminating a VM, check the delete-on-termination policy. Some disks or IPs may be intentionally retained; do not auto-delete if data must be preserved.

## 8. On-Demand in Containers and Kubernetes

In container platforms, multiple billing layers may exist.

### Self-Managed Kubernetes on VMs

If a cluster runs on organization-managed VMs, the cloud provider typically bills compute per node VM and related resources. Pod CPU requests/limits help the scheduler manage capacity, but they are not necessarily the direct billing meter for the VM invoice.

For example, a node has 8 vCPUs and runs 10 pods. If total CPU requests equal 5 vCPUs, the provider may still charge the node based on VM capacity while the node is billable, not just for the 5 requested vCPUs.

To allocate costs to pods, use an allocation model based on:
- CPU requests or usage.
- Memory requests or working set.
- GPU allocation.
- PVCs and storage.
- Network or service-specific charges.
- Overhead from system daemons and the node.

This is internal cost allocation, which can differ from direct billable usage.

### Resource-Time Metered Container Services

Some managed or serverless container services charge by vCPU-second, GiB-second, requests, or task runtime. In this case, meters tie directly to the task/container's resource configuration and service-defined duration.

Read carefully:
- When metering starts.
- When metering stops.
- Whether a minimum duration applies.
- Whether CPU and memory are billed separately.
- Whether idle capacity is billed.
- Whether charges apply for requests, network, storage, or the control plane.

### Kubernetes Node Autoscaling

Node scale-out/scale-in changes the number of billable VMs. Pod scheduling and eviction can keep nodes alive longer than workloads. The cluster autoscaler may keep empty nodes during a scale-down delay to avoid churn.

Measure:
- Node billable hours.
- Node utilization and allocatable capacity.
- Pod requests/usage.
- Empty node duration.
- Scale-up/scale-down delays.
- System overhead and daemonset usage.

Prolonged low node utilization can indicate overprovisioning, though you should not downsize nodes based solely on averages if workloads have bursts or availability requirements.

## 9. On-Demand in Serverless

Serverless typically shifts measurement from VM uptime to execution count and resources per execution.

Meters may include:
- Request/invocation count.
- Duration in milliseconds or other time units.
- Memory configuration or consumed memory.
- CPU or vCPU-time.
- Provisioned concurrency or warm capacity.
- Data transfer and supporting services.

### Duration-Based Example

A function is invoked 10,000 times with an average duration of 250 ms per invocation. Total execution duration:

\[
10{,}000 \times 0.25 = 2{,}500\ seconds
\]

If the function is configured with 1 GiB memory and metered by memory-time:

\[
2{,}500 \times 1 = 2{,}500\ GiB\text{-}seconds
\]

This calculation excludes request charges, provisioned capacity, networking, or other services. Some platforms have per-invocation rounding rules, minimum durations, or separate memory pricing rules.

### Cold Starts and Idle

Cold start time may be included in billable duration or handled according to platform-specific rules. Provisioned concurrency or warm instances can incur charges even with low request volume. Review the relevant meters and weigh them against latency benefits.

### Comparing VMs and Serverless

| Criterion | On-Demand VM | Function/Serverless |
|---|---|---|
| Primary unit | Instance/configuration time | Requests, duration, and resource-time |
| Idle | Usually billed while VM is billable | Execution may not charge when idle, though warm/provisioned capacity may charge |
| Control | User manages OS and runtime | Provider manages most of the platform |
| Bursts | Requires autoscaling or pre-provisioned capacity | Scales automatically per service limits and quotas |
| Ancillary costs | Disks, IPs, network, licenses | Requests, duration, provisioned capacity, network, and dependencies |
| Measuring utilization | OS/process/VM metrics | Invocations, duration, concurrency, memory/CPU metrics |

Do not conclude that serverless is always cheaper than VMs. For continuously running workloads, serverless can be costlier or have different performance limits. Compare cost per completed unit of work and SLOs.

## 10. Measuring Runtime with Operational Metrics

Billing records tell you how many units the provider charges. Operational metrics tell you how resources are used.

### VM Metrics

- Instance state and uptime.
- CPU utilization over time.
- Available memory / working set.
- Disk IOPS, throughput, and latency.
- Network bytes/packets.
- Process uptime and service health.
- Boot time, shutdown time, and restart count.

### Container Metrics

- Container start/stop timestamps.
- CPU usage and throttling.
- Memory working set and OOM events.
- Pod/container uptime.
- Requests/limits.
- Queue depth and replica count.
- Node allocatable capacity and node idle time.

### Serverless Metrics

- Invocation count.
- Duration distribution.
- Concurrent executions.
- Throttles and retries.
- Cold starts.
- Memory used.
- Errors and timeouts.
- Provisioned/warm capacity.

### Why Both Billing and Monitoring Are Needed

For example, billing shows a VM ran 720 hours in a month. Monitoring shows 4% average CPU, 15% RAM used, and zero requests at night. That is evidence to consider scheduling or resizing.

Conversely, a VM running 720 hours with 70% average CPU, p95 latency meeting SLOs, and continuous load may represent appropriate capacity. Uptime numbers look identical, yet optimization decisions differ completely.

## 11. Billing Exports and Usage Records

Cloud providers typically offer cost management reports, usage details, or billing exports for line-item cost analysis.

Useful fields may include:
- Usage start/end time.
- Resource ID or resource name.
- SKU/service/meter.
- Region/zone.
- Usage quantity and unit.
- Pricing unit and rate.
- Cost before/after discount.
- Currency.
- Project/account/subscription.
- Tags/labels or cost allocation tags.
- Charge type such as usage, tax, credit, adjustment, or commitment.

Field names and granularity vary by provider. Some lines may lack a resource ID, or costs may be aggregated by meter rather than per instance.

### Billing Exports as the Source of Billing Truth

Do not construct your own invoice by summing VM log durations when the billing system provides official usage quantities. Lifecycle logs are helpful for investigation and analysis, while billing exports are the authoritative source for reconciling provider-recorded meter quantities.

### Usage Delays and Finalized Costs

Cost data may arrive late or be adjusted after usage occurs. Current-day reports may be incomplete. Distinguish:
- Usage event time.
- Ingestion/record time.
- Invoice period.
- Finalized charge.
- Subsequent adjustments or credits.

Do not conclude current-day costs are abnormally low if billing data is not yet finalized.

## 12. Tagging for Cost Allocation

To know who or which workload generates usage, enforce consistent tagging/labeling rules.

Tags to consider:
- service or application.
- environment: dev, test, staging, production.
- team or cost center.
- owner.
- project/product.
- customer/tenant if policy permits.
- lifecycle or expiry date.
- managed-by or IaC stack.

### Avoid Unstable Tags

Do not use constantly changing values like request IDs or timestamps as resource tags. Tags should have moderate cardinality and be applied from provisioning pipelines.

### Untagged Costs

Some costs cannot be attributed directly to a single resource:
- Shared networks.
- NAT gateways.
- Load balancers.
- Monitoring workspaces.
- Shared Kubernetes nodes.
- Support plans.
- Commitment discounts.
- Inter-region data transfer.

Define how shared costs are allocated: by traffic, CPU usage, memory requests, instance count, revenue, or another suitable driver. Document clearly that this is an internal allocation policy, not a direct provider meter.

### Shared Node Allocation Example

A VM node incurs 100 currency units of compute cost in a day. Three workloads have average CPU requests of 50%, 30%, and 20% of allocatable CPU respectively. If the organization chooses CPU requests as the allocation driver, internal costs can be split 50, 30, and 20.

This is only an allocation rule. If one workload actually uses very little CPU while holding large requests, request-based allocation will differ from usage-based allocation. Choose a driver aligned with chargeback/showback goals and publish it clearly.

## 13. Measuring and Calculating Time Using Event Data

One implementation approach is storing each resource's lifecycle events in a table or logging system.

Example structure:

| resource_id | event | timestamp_utc | region | sku |
|---|---|---|---|---|
| vm-101 | started | 2026-11-01T02:00:00Z | region-a | compute-medium |
| vm-101 | stopped | 2026-11-01T05:30:00Z | region-a | compute-medium |
| vm-101 | started | 2026-11-01T08:00:00Z | region-a | compute-medium |
| vm-101 | terminated | 2026-11-01T10:00:00Z | region-a | compute-medium |

From the events, intervals can be reconstructed:
- 02:00–05:30: 3.5 hours.
- 08:00–10:00: 2 hours.
- Total duration per lifecycle events: 5.5 hours.

If the meter charges by instance-hour without rounding/minimums, the reference quantity is 5.5 instance-hours. Reconcile against the billing export to confirm.

### Pseudocode for Interval Calculation

~~~text
for each resource_id:
    sort lifecycle events by timestamp
    open_interval = none

    for event in events:
        if event starts a billable state:
            if open_interval is none:
                open_interval = event.timestamp

        if event ends a billable state:
            if open_interval exists:
                duration += event.timestamp - open_interval
                open_interval = none

    if open_interval exists:
        duration += report_end_time - open_interval
~~~

This logic must handle edge cases:
- Missing stop events.
- Duplicate or out-of-order events.
- VMs terminated while running.
- Resources resized mid-interval.
- Timezone or clock skew.
- Delayed event recording.
- Failed or rolled-back state transitions.

Do not use a simple script to replace official meters when invoice reconciliation is required.

## 14. Process for Reconciling Monitoring with Billing

A workflow that can run daily or periodically:

1. Pull resource inventory by account/project/subscription.
2. Pull lifecycle events for the same period.
3. Pull billing usage exports by meter and resource ID.
4. Normalize timezones and currencies.
5. Map SKUs, regions, OS, and pricing dimensions.
6. Compute event-based runtime for cross-checking.
7. Compare event-derived quantity against billing quantity.
8. Investigate variances caused by rounding, minimums, licenses, delays, or missing events.
9. Apply tags and allocate shared costs.
10. Record cost owners and optimization actions.

### Discrepancy Example

Lifecycle events show a VM ran for 10 hours, while the billing export shows 11 instance-hours. Possible causes:
- The meter started billing before the running timestamp captured by event logs.
- Minimum charges or rounding applied.
- The VM restarted during the period with a missing event.
- The billing line includes a different SKU or license.
- Event time and billing time follow different rules.
- The export is not finalized or includes an adjustment.

Do not alter billing quantities to force a match with logs. Document the variance and verify the meter definition.

### Daily vs. Monthly Checks

Daily checks help catch resources running after hours, whereas invoices usually aggregate over a period with discounts/credits. Monthly reviews should examine:
- Usage quantity.
- Unit price and effective price.
- Pre-discount and post-discount costs.
- Shared costs.
- Commitment coverage.
- Taxes/credits/adjustments.
- Percentage of unowned/untagged cost.

## 15. Optimizing Costs Based on Usage Time

### Scheduled Start/Stop

Suitable for:
- Development VMs.
- Test environments.
- Sandboxes.
- Build agents that do not need to run continuously.
- Labs or training environments.

For example, an environment used only 10 hours per day, 5 days per week. If it can stop after hours without harming data or background tasks, compute runtime drops significantly.

Before scheduling:
- Check cron jobs and batch tasks.
- Check backup windows.
- Check licenses.
- Check dependencies and connections.
- Use lifecycle hooks for graceful shutdown.
- Ensure disks and data persist.
- Provide pre-workday startup and health checks.

### Autoscaling and Scale to Zero

Autoscaling fits fluctuating loads. Scale to zero works when workloads tolerate cold starts or sit behind durable queues.

Avoid rapid scaling that causes instance churn, bootstrap overhead, or request errors. Monitor min/desired/max counts, cooldowns, startup duration, and queue backlogs.

### Rightsizing

If VMs run for full periods with low CPU/RAM utilization, consider:
- Choosing smaller instances.
- Reducing provisioned memory if the runtime allows.
- Separating workloads to eliminate wasted headroom.
- Using instance families matched to CPU/memory ratios.
- Using containers to share node capacity.
- Moving suitable workloads to serverless or job services.

Rightsizing must be based on peaks, p95/p99, failover headroom, and seasonal traffic—not average CPU alone.

### Cleaning Up Auxiliary Resources

Look for:
- Unattached disks.
- Outdated snapshots.
- Unused IPs.
- Empty load balancers/backends.
- Unneeded NATs or gateways.
- Old images.
- Excessive log retention.
- Unused provisioned IOPS volumes.

Attach expiry tags and an owner review workflow before deletion to avoid losing necessary data.

## 16. When Does On-Demand Fit and When Should Other Models Be Considered?

| Workload Characteristics | Why On-Demand May Fit | What to Consider |
|---|---|---|
| Unstable, unpredictable load | Flexible scale up/down of resources | Autoscaling and quotas |
| Hourly dev/test | Pay only when needed | Scheduling and cleanup |
| Short-term or experimental workloads | No long-term commitment required | Minimum charges and startup time |
| Steady year-round production load | Easy to start and flexible | Commitments/reservations can lower unit prices |
| Retryable batch jobs | Spin up compute when queues fill | Spot/preemptible if interruptions are tolerable |
| APIs requiring instant response | Can maintain minimum capacity | Serverless cold starts and provisioned capacity |
| Periodic GPU workloads | On-demand avoids idle GPUs | GPU quotas, availability, and startup delays |

On-demand is usually the flexible baseline to start with. Once steady usage patterns are understood, organizations can combine on-demand with reserved/committed capacity or spot to balance cost and risk.

Do not compare raw unit prices in isolation. Compare cost per completed unit of work, factoring in downtime, retries, performance, licenses, storage, and networking.

## 17. Common Mistakes When Measuring Usage Time

1. **Using CPU utilization to infer billable hours.** Low CPU does not reduce instance-hours if the meter bills by instance time.
2. **Assuming Stop VM stops all charges.** Disks, IPs, snapshots, licenses, and network services may continue billing.
3. **Using button-click times as billing timestamps.** API requests and state transitions can differ in timing.
4. **Rounding times manually.** Minimum and rounding rules depend on the meter.
5. **Multiplying total duration by the final configuration.** Mid-period VM resizes require splitting intervals by SKU.
6. **Summing elapsed wall-clock time instead of instance-hours.** Parallel VMs generate total instance-hours greater than clock duration.
7. **Ignoring auxiliary resources.** Compute bills do not explain storage, egress, IP, and monitoring charges.
8. **Treating pod requests as VM billable quantities.** Node VMs may be billed by capacity while pod metrics are for internal allocation.
9. **Ignoring warm/provisioned capacity.** Serverless or container warm capacity may carry separate meters.
10. **Comparing list cost with net cost.** Standardize discounts, credits, and charge types.
11. **Missing owners/tags.** Costs accrue with no identifiable responsible team.
12. **Checking only current-day reports.** Billing exports may be delayed or adjusted.

## 18. Comprehensive Example: Measuring an On-Demand Test Environment

A team has a test environment consisting of:
- 2 application VMs, 4 vCPUs each.
- 1 worker VM, 8 vCPUs.
- 3 data disks, 100 GiB each.
- One public IP and load balancer.
- The environment runs from 09:00 to 13:00 on the test day.

### Computing Compute Runtime

Application VMs:

\[
2 \times 4\ hours = 8\ instance\text{-}hours
\]

Worker VM:

\[
1 \times 4\ hours = 4\ instance\text{-}hours
\]

Total:

\[
8 + 4 = 12\ instance\text{-}hours
\]

If metered by vCPU-hour:

\[
(2 \times 4 + 8) \times 4 = 64\ vCPU\text{-}hours
\]

These two numbers measure different things. Billing exports may use one or multiple meters depending on service configuration.

### Computing Storage

If the 3 × 100 GiB disks are kept for 30 days:

\[
3 \times 100 \times 30 = 9{,}000\ GiB\text{-}days
\]

Storage usually has its own billing unit like GiB-month, converted using hours/days in the period. Running compute for only 4 hours does not mean disks are billed for only 4 hours.

### Checking Auxiliary Resources

After testing, VMs are stopped, but the team keeps disks for 7 more days to analyze results. Then:
- Compute may stop billing after deallocation per provider rules.
- Disks continue accruing storage charges.
- Public IP may still incur fees if retained.
- Load balancer may continue charging hourly and traffic fees.
- Logs/monitoring may still incur ingest/retention fees.

Cost reports should break out compute, storage, network, and shared services rather than logging a single line "test environment 4 hours".

## 19. Workflow for Building Usage and Cost Reports

A report can include the following sections:

### Usage

- Resource ID and owner.
- Resource type/SKU.
- Region/zone.
- Billable start/end or usage quantity.
- Unit.
- Event-based runtime.
- CPU/RAM/network/storage utilization.
- Idle time or out-of-schedule time.

### Cost

- List cost.
- Effective/net cost.
- Discounts/credits.
- Storage/network/licenses.
- Shared cost allocation.
- Cost center/team.
- Cost per request/job/transaction.

### Reconciliation

- Billing quantity.
- Event-derived quantity.
- Delta.
- Variance reason.
- Investigation status.
- Responsible owner.

### Action

- Stop/schedule.
- Resize.
- Autoscale.
- Delete orphaned resources.
- Change pricing model.
- Improve tagging.
- Review commitments.
- Optimize workload.

## 20. Checklist for Measuring On-Demand Resource Usage Time

- [ ] Identified meters and billing units for each resource.
- [ ] Read billable start/end, minimum duration, and rounding rules.
- [ ] Distinguished provisioned time, runtime, utilization, and billable usage.
- [ ] Collected resource IDs and lifecycle events.
- [ ] Timestamps have explicit timezones and are normalized.
- [ ] Handled multiple start/stop cycles within the same period.
- [ ] Split intervals when VMs resized or changed SKUs.
- [ ] Reconciled event-derived durations with billing exports.
- [ ] Separated compute, disks, snapshots, IPs, networking, and licenses.
- [ ] Distinguished VM node billing from pod-level allocation.
- [ ] Calculated requests/duration/resource-time for serverless.
- [ ] Applied owner, service, environment, and cost center tags.
- [ ] Defined shared cost allocation methods.
- [ ] Checked for billing data delays and adjustments.
- [ ] Measured utilization alongside billable hours to detect overprovisioning.
- [ ] Audited orphaned disks, IPs, snapshots, and load balancers.
- [ ] Established scheduling/autoscaling policies and cleanup owners.
- [ ] Defined cost per request/job/transaction where applicable.

## Conclusion

On-demand lets teams provision and consume compute as needed, but costs are governed by each service's meters and billable rules. The time a VM is billed is not equivalent to the time its CPU is busy; an idle VM can still incur compute charges, and a stopped VM can retain disk, IP, snapshot, or license charges. Accurate measurement requires combining lifecycle events, usage quantities in billing exports, and operational metrics. By separating instance-hours, vCPU-time, memory-time, request duration, and auxiliary resources, operations teams can reconcile bills, uncover idle time, allocate costs, and choose the right scheduling, autoscaling, or rightsizing strategies.
