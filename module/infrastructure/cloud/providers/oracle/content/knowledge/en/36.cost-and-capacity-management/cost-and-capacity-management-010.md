# Growth Forecasting, Quota Tracking, and Capacity Planning

## 1. Objectives and Context

In the **Cost and Capacity Management** chapter of the **CLOUD_PROVIDERS_ORACLE** module, capacity planning is the process of translating business demand into Oracle Cloud Infrastructure (OCI) resources that can be provisioned on time, meet service levels, and stay within budget.

A system can run at low CPU yet still fail to scale because it hits a memory quota, runs out of subnet IP addresses, or lacks suitable host capacity. Conversely, a tenancy with generous service limits can still incur unnecessary cost if resources run permanently at peak size.

After this lesson, learners can:

- Build a baseline from traffic, latency, utilization, and data growth.
- Translate forecasts into Compute, storage, network, and Oracle database demand.
- Read service limits, compartment quotas, and remaining allocatable headroom accurately.
- Calculate headroom for scaling, rolling deployments, and incidents.
- Design early-warning alerts, assign owners, and track plan costs.

This lesson assumes familiarity with tenancies, compartments, IAM, VCNs, and viewing basic metrics. Figures below are **hypothetical calculation assumptions**, not default limits, list prices, or Oracle provisioning guarantees.

## 2. Distinguish Demand, Limits, and Physical Capacity

| Concept | Question answered | Role in planning |
| --- | --- | --- |
| Demand | How much work must the application process? | Requests/sec, transactions/sec, batch/hour, daily data generated |
| Provisioned capacity | Which resources already exist? | Instance counts, OCPUs, RAM, storage size, DB config |
| Service limit | How much does Oracle allow the tenancy to use in that scope? | Oracle-set ceiling; check actual tenancy values |
| Compartment quota | How much does the organization allow the compartment to use? | Internal allocation boundary set by administrators |
| Resource availability in Limits API | Given usage and limits, how much more is permitted? | Limit headroom; not the number of free physical hosts |
| Host capacity | Does OCI have matching hardware to provision right now? | Depends on placement, shape, and placement constraints |
| Budget | How much will be spent or is projected? | Spend tracking and alerting mechanism |

Oracle distinguishes service limits set by Oracle from compartment quotas set by administrators. Some limits cannot be increased; do not build plans assuming every limit-increase request will be approved. See [Service Limits](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/overview.htm) and [Manage Your Service Limits](https://docs.oracle.com/en/solutions/oci-best-practices/manage-your-service-limits1.html).

In operations, verify three independent layers:

1. **Permitted:** Does IAM allow creating, modifying, and using the relevant resources?
2. **Within limits:** Are applicable service limits and quotas sufficient?
3. **Provisionable:** Do physical hardware, subnets, shapes, and dependent resources support it?

Budget availability must also be confirmed, though budget does not replace the three checks above.

### 2.1. Scope Is Part of a Limit's Identity

Do not simply write "40 Compute OCPUs remaining." A useful record specifies:

~~~text
tenancy / subscription if applicable / region / service /
limit-name / scope-type / availability-domain if applicable /
evaluated compartment / data retrieval timestamp
~~~

Limit names, units, and scopes must be read from OCI. Do not sum leftover OCPUs across multiple ADs and treat them as allocatable to a single instance. Nor should you check the primary region's limits and conclude the disaster recovery region has enough headroom.

[Limits by Service](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/default.htm) documents scopes per resource. In real plans, use the values displayed for your tenancy and subscription instead of copying default tables.

### 2.2. Quotas Across the Compartment Tree

Child compartment usage counts toward parent compartments. AD-scoped quotas apply to each AD unless constrained to a specific AD; region-scoped quotas must likewise be read in their scope. Service limits still bind even when internal quotas are set higher. See [Quota Policy Syntax](https://docs.oracle.com/en-us/iaas/Content/Quotas/Concepts/quota_policy_syntax.htm).

For example, an application team may have 24 OCPUs left under its own quota, while the parent compartment has only 8 OCPUs left after accounting for other teams. In that case, a plan to add 20 OCPUs is not yet feasible.

Do not derive effective quotas simply by adding all policies found. Account for parent levels, conditions, and policy combination rules; use the appropriate availability API output when supported.

## 3. Build a Verifiable Baseline

A baseline is a snapshot of system demand and behavior across a representative period. Choose a window covering the business cycle: for example, several weeks including weekdays, weekends, and periodic batch runs. If peak season is absent from historical data, explicitly note that forecasting gap.

### 3.1. Collect Both Business Inputs and Technical Signals

| Component | Data to collect | Purpose |
| --- | --- | --- |
| Business | Active users, orders, new customers, campaign calendar | Identify traffic drivers and events absent from history |
| Compute or workers | Throughput, CPU, RAM, queues, processing time | Find processing limits and resources needing scale |
| Application | p95/p99 latency, error rate, timeouts, concurrency | Determine capacity to meet SLOs |
| Block Volume and filesystem | Used capacity, provisioned capacity, IOPS, throughput, latency | Separate space exhaustion from I/O performance bottlenecks |
| Object Storage and logs | New data, expired data, versions, retention | Forecast retained storage capacity |
| Oracle Database | TPS, CPU, sessions, waits, I/O, space, redo/archive growth | Identify data bottlenecks and scaling conditions |
| VCN and connectivity | Available IP addresses, throughput, connections, transfer volume | Check ability to add nodes and sustain traffic |
| Financial | Costs by compartment, environment, application, and period | Correlate resource growth with delivered value |

RAM metrics may require an in-guest agent or monitoring tool. Confirm measurement sources and collection health; a chart with no data does not prove RAM is idle.

For databases, identify the exact service type in use: Base Database Service, Autonomous Database, or another Oracle configuration. Record that configuration's exact capacity unit; do not convert OCPU to ECPU using a generic ratio to plan across all services.

### 3.2. Record the Conditions of Each Measurement

A number like "350 requests/second per node" is useful only if you know:

- Shape, OCPU count, RAM, image, and application version.
- Request size, read/write ratio, cache hit rate, and endpoint distribution.
- Corresponding latency, error rate, and resource utilization.
- Background load, DB connections, and number of nodes participating in the test.
- Time range, timezone, and sample granularity.

Keep timestamps consistent, such as UTC when aggregating. Mark deployments, incidents, data imports, and configuration changes on the same timeline.

### 3.3. Avoid Misleading Baselines

Low monthly average CPU can hide 20-minute traffic spikes. Alongside averages, examine peak windows, percentiles, and time-series curves.

Do not sum per-instance p95 values and call the sum system-wide p95. If an aggregate percentile is needed, compute it from appropriately aggregatable data or histograms.

Nor should you treat every anomaly as a trend. A one-off reindex or backfill should be labeled separately, though it still needs room in the plan if that task will recur.

## 4. Forecast Growth from Demand to Node Count

### 4.1. Choose a Model Matching the Growth Driver

Two simple models are usually enough to start:

~~~text
Linear growth:
D(t) = D0 + a × t

Compounding growth:
D(t) = D0 × (1 + g)^t
~~~

Where:

- `D0` is demand at the baseline point.
- `a` is the absolute increment per period.
- `g` is the growth rate per period.
- `t` is the number of periods, in the same time unit as `a` or `g`.

For example, steady monthly new-customer onboarding may fit a linear model. Product traffic growing proportionally may fit an exponential model over a short horizon.

If a known event exists, you can use:

~~~text
D_peak(t) = D0 × (1 + g)^t × S(t) + E(t)
~~~

`S(t)` represents a seasonality factor; `E(t)` is incremental load not already in the trend. Check whether baseline data already reflects seasonality or events to avoid double counting.

Forecasts should include at least three scenarios: low, baseline, and high. Each scenario needs business rationale, update date, and an owner accountable for its assumptions.

### 4.2. Three-Month Traffic Forecast Example

Suppose current peak load is **1,200 requests/second**. The product team expects a campaign at the end of month three.

| Scenario | Monthly growth | Campaign multiplier | Calculation | Rounded-up peak load |
| --- | --- | --- | --- | --- |
| Low | 4% | 1.2 | 1,200 × 1.04³ × 1.2 | 1,620 requests/sec |
| Baseline | 8% | 1.4 | 1,200 × 1.08³ × 1.4 | 2,117 requests/sec |
| High | 12% | 1.6 | 1,200 × 1.12³ × 1.6 | 2,698 requests/sec |

These are hypothetical scenarios, not statistical confidence intervals. When new data arrives, update both growth rate and campaign multiplier.

### 4.3. From Throughput to Compute Capacity

Suppose load testing shows one **4 OCPU, 32 GB RAM** node serves **350 requests/second** while meeting:

- p95 latency at or below 200 ms.
- Error rate under 0.1%.
- CPU and RAM within team-approved operating thresholds.

350 requests/second is the **SLO-compliant capacity at the tested configuration**, not throughput at 100% CPU. Do not multiply by another CPU headroom factor if that margin was already baked into determining 350.

Formulas:

~~~text
N_serve = ceil(D_peak / safe_throughput_per_node)
N_steady = N_serve + redundant_nodes_for_failure_scenario
~~~

With a requirement to survive losing one node:

| Scenario | Nodes needed to serve | Steady-state nodes, with N+1 | OCPU | RAM |
| --- | --- | --- | --- | --- |
| Low | ceil(1,620 / 350) = 5 | 6 | 24 | 192 GB |
| Baseline | ceil(2,117 / 350) = 7 | 8 | 32 | 256 GB |
| High | ceil(2,698 / 350) = 8 | 9 | 36 | 288 GB |

The high scenario has nine nodes, so if one node fails, eight nodes remain with an assumed combined capacity of 2,800 requests/second.

This calculation assumes near-linear scaling. Before using in production, test with multiple nodes and the matching DB: connection pools, locks, or shared services can keep the ninth node from adding expected throughput.

### 4.4. Check Dependent Resources

If each node opens up to 40 DB connections, nine nodes can create up to 360 connections. During a rolling deployment using 11 nodes, the configured maximum rises to 440 connections.

That is not yet a forecast of active concurrent sessions, but it is a ceiling to check against DB capacity, connection limits, and application connection reuse. Adding nodes while leaving an I/O-bottlenecked DB unchanged may simply lengthen queues.

By the same rule, check subnet IPs, load balancer backends, boot volumes, logging, and other dependencies before locking node counts.

## 5. Forecast Storage and When Scaling Is Needed

### 5.1. Distinguish Used Capacity from Provisioned Capacity

Suppose application data currently uses 2,048 GiB, grows by 20 GiB/day net, and needs a 90-day plan:

~~~text
Data_volume_after_90_days
= 2,048 + 20 × 90
= 3,848 GiB
~~~

If used space must not exceed 75% of provisioned capacity:

~~~text
Capacity_to_provision
>= 3,848 / 0.75
>= 5,130.67 GiB

Rounded minimum calculated level: 5,131 GiB
~~~

Then pick a valid service configuration, accounting for size increments and applicable limits.

"Keep 25% of total capacity free" differs from "add 25% to data size." In this example, the correct math for the free-space target is dividing by 0.75.

GiB in the calculation is the example's data unit. When mapping to OCI, convert consistently to bytes or the exact unit used by metrics, quotas, and configurations; do not assume every GB label matches GiB.

### 5.2. Calculate Time Until Operational Threshold

If 4,000 GiB is currently provisioned, the 75% threshold is 3,000 GiB:

~~~text
Days_to_threshold
= (3,000 - 2,048) / 20
= 47.6 days
~~~

This number is far more actionable than "the disk is almost half full" because it can be compared against approval, resize, and verification lead times.

General formula for positive net growth rate:

~~~text
T_threshold = (Capacity_threshold - Current_data) / Net_daily_growth
~~~

If growth rate is zero or negative, do not divide directly. Record "no threshold breach projected under current model" and continue monitoring fluctuations.

### 5.3. Storage Requires More Than One Forecast Curve

Plan separately for:

- Active data, indexes, and free headroom for maintenance tasks.
- Redo logs, archive logs, application logs, and retention windows.
- Backups, recovery copies, object versions, and policy-held data.
- Scratch space for imports, index rebuilds, or data migrations.
- Required IOPS, throughput, and latency at forecasted load.

With a steady 10 GiB/day log stream and 30-day retention, steady-state retained data is roughly 300 GiB if expiration cleanup works properly. Do not extrapolate unbounded growth; nor should you assume expiration jobs ran without confirming metrics.

Snapshots, incremental backups, compression, and deduplication consume capacity differently. Use measured metrics from the active mechanism rather than multiplying backup count by full source size.

## 6. Calculate Capacity for Deployments and Incidents

### 6.1. Steady-State Demand Is Often Smaller Than Peak Allocation Demand

Continuing the high-scenario example: nine steady-state serving nodes, each with 4 OCPUs and 32 GB RAM.

| State | Nodes to count in plan | OCPU | RAM | Condition |
| --- | --- | --- | --- | --- |
| Current | 6 | 24 | 192 GB | Assumed baseline |
| High-load operation with N+1 | 9 | 36 | 288 GB | Eight remaining nodes cover load if one fails |
| Replace one node before deleting old | 10 | 40 | 320 GB | Need room for old and new nodes to coexist |
| Rolling deployment with up to two surge nodes | 11 | 44 | 352 GB | Nine existing nodes plus two surge nodes |

In the example, the level to verify against limits is **11 nodes**, equal to **44 OCPUs and 352 GB RAM**, even though steady-state operation uses only nine nodes.

If procedures allow adding a replacement node alongside two surge slots during a concurrent failure, the peak becomes 12 nodes. The plan must state which states are permitted to overlap; do not assume every buffer stacks independently or can always be shared.

An instance no longer serving traffic has not necessarily released its limit usage. Count resources as freed only after confirming lifecycle state and how the service records usage.

### 6.2. Surviving One Node Loss Differs from Losing an AD

N+1 in the table models losing **one node** only. It does not by itself prove the system survives losing an entire AD hosting multiple nodes.

Suppose the application is deployed across two ADs and each AD must independently handle the high scenario if the other AD goes down. At 350 requests/second per node, each AD needs at least eight ready nodes to serve 2,698 requests/second. That totals 16 nodes before adding extra redundancy requirements.

This is a hypothetical model for regions with matching topology. If a region has only one AD, spreading across fault domains does not provide resilience against losing that AD.

### 6.3. Capacity for Disaster Recovery

A DR plan must specify:

- RTO: maximum acceptable recovery time.
- RPO: maximum acceptable data loss.
- Load to serve immediately post-failover: full workload or a prioritized subset.
- Which resources already run, are reserved, or will be created during an incident.
- Limits, networking, images, IAM, secrets, and data in the recovery region.
- Measured provisioning, restore, sync, and traffic-cutover times.

Do not treat a valid Terraform plan as proof of recovering within RTO. Rehearse the recovery path and mark clearly which figures are measured versus still estimated.

## 7. Compute Headroom Against Service Limits and Quotas

### 7.1. Simple Model for One Resource Type

For the same service, limit-name, unit, and scope, let:

- `L`: tenancy service limit.
- `U_tenancy`: total usage in that scope.
- `Q_prod`: effective quota of the Production compartment.
- `U_prod`: usage in Production, including applicable child compartments.

Without tighter constraints at parent levels or other conditions:

~~~text
H_service = L - U_tenancy
H_prod = Q_prod - U_prod
H_effective = max(0, min(H_service, H_prod))
~~~

When a parent compartment has an active quota, include the parent's remaining headroom in the corresponding `min`. This is an arithmetic model to understand headroom; it does not replace OCI's full policy evaluation rules.

### 7.2. Example Where CPU and Memory Jointly Constrain Scaling

Suppose a snapshot in the same AD and timestamp yields:

| Resource | Service limit | Tenancy usage | Production quota | Production usage | Effective headroom in model |
| --- | --- | --- | --- | --- | --- |
| OCPUs of active family | 160 | 132 | 96 | 72 | min(28, 24) = 24 OCPU |
| RAM of active family | 1,280 GB | 1,056 GB | 768 GB | 576 GB | min(224, 192) = 192 GB |

Production usage covers the target application and other workloads. The application's current six nodes occupy only 24 OCPUs out of the compartment's 72 OCPUs.

To grow from six nodes to the peak of 11 nodes requires **adding five nodes**:

~~~text
Additional OCPUs = 5 × 4 = 20 OCPU
Additional RAM   = 5 × 32 = 160 GB
~~~

Under both limits in the table, this incremental demand fits within allocatable room:

~~~text
Production usage after scaling:
OCPU = 72 + 20 = 92 out of 96 quota
RAM  = 576 + 160 = 736 GB out of 768 GB quota
~~~

Both quotas reach roughly 95.8%. "Still creatable" only proves the immediate expansion step does not breach these two constraints; remaining slack afterward is too thin to assume the medium-term plan is safe.

To find the maximum new nodes allowed by these two resources alone:

~~~text
N_add_by_CPU = floor(24 / 4) = 6
N_add_by_RAM = floor(192 / 32) = 6
N_add_by_limits = min(6, 6) = 6
~~~

This result does not yet check IPs, boot volumes, other limits, or host capacity.

### 7.3. Case Where a Parent Quota Changes the Conclusion

Now suppose the parent compartment has only 8 OCPUs left. Effective OCPU headroom drops to:

~~~text
min(28 OCPU at tenancy, 24 OCPU in Production, 8 OCPU at parent)
= 8 OCPU
~~~

That suffices for only two 4-OCPU nodes; five new nodes will be blocked by limits. Adjust parent-level allocations or revise the plan before deployment day.

Quotas allocate consumption permission; they do not reserve physical hosts for a compartment. Raising an internal quota still does not prove OCI can provision those resources when needed.

## 8. Read Limits and Usage on OCI

### 8.1. Console Procedure

On the **Limits, Quotas and Usage** page:

1. Confirm tenancy, region, and subscription if selectable.
2. Choose the service and resource type to inspect.
3. Check scope, AD if applicable, unit, limit, usage, and availability.
4. Select the compartment to evaluate.
5. Cross-check quotas on that compartment and relevant parent levels.
6. Record retrieval timestamp and accountable owner.

Track every real constraint. Do not screenshot just the OCPU row while ignoring the RAM row or reservation resource groups if reservations are part of the plan.

### 8.2. IAM Permissions to Read Data

Example for group `CapacityReaders`:

~~~text
Allow group CapacityReaders to inspect resource-availability in tenancy
Allow group CapacityReaders to read resource-availability in compartment Production
~~~

`inspect` at tenancy scope supports listing services, definitions, and values; `read` allows reading resource availability in the granted compartment. Adjust group names, compartments, and identifier syntax to match your tenancy. See the IAM section in [Service Limits](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/overview.htm).

These policies do not grant rights to edit quotas or deploy infrastructure. If inventory and metrics from other services are needed, grant separate read permissions for those purposes.

### 8.3. OCI CLI Lookup Examples

The following commands use **Bash**, such as in an environment with OCI CLI and valid authentication ready. Replace sample values before running.

~~~bash
TENANCY_OCID="ocid1.tenancy.oc1..REPLACE_VALUE"
PROD_OCID="ocid1.compartment.oc1..REPLACE_VALUE"
REGION="REPLACE_REGION"
SERVICE="compute"

# Look up definitions: limit name, scope, and quota support.
oci limits definition list --compartment-id "$TENANCY_OCID" --service-name "$SERVICE" --region "$REGION" --all

# Look up tenancy service limit values in the target region.
oci limits value list --compartment-id "$TENANCY_OCID" --service-name "$SERVICE" --region "$REGION" --all
~~~

Take `LIMIT_NAME` from the definition output; do not guess technical limit names from shape display names. The quota-support attribute indicates whether compartment quotas can be set for that limit. Refer to [definition list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/limits/definition/list.html) and [value list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/limits/value/list.html).

For an `AD`-scoped limit:

~~~bash
LIMIT_NAME="REPLACE_WITH_LOOKED_UP_LIMIT_NAME"
AD_NAME="REPLACE_WITH_FULL_TENANCY_AD_NAME"

oci limits resource-availability get --compartment-id "$PROD_OCID" --service-name "$SERVICE" --limit-name "$LIMIT_NAME" --availability-domain "$AD_NAME" --region "$REGION"
~~~

For a `REGION`-scoped limit, run a separate command without the AD parameter:

~~~bash
LIMIT_NAME="REPLACE_WITH_REGION_SCOPED_LIMIT_NAME"

oci limits resource-availability get --compartment-id "$PROD_OCID" --service-name "$SERVICE" --limit-name "$LIMIT_NAME" --region "$REGION"
~~~

Run only the matching branch. Per [resource-availability get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/limits/resource-availability/get.html), the AD parameter is required for AD scope and must be omitted when not AD-scoped. Some limits do not support this API and may return 404; distinguish that from wrong identifiers or access issues.

If the service is tied to a subscription, select the exact subscription and pass `--subscription-id` on supported commands when needed. Keep that context consistent across pulls.

Output from the Limits API describes availability relative to usage, service limits, and quotas. It is not a host capacity report; some fields may also be unavailable for certain limits. See [resource-availability](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/limits/resource-availability.html).

### 8.4. Tracking Record Template

| Field | Details to store |
| --- | --- |
| Context | Tenancy, subscription if applicable, region, compartment |
| Resource key | Service, limit-name, scope-type, AD if applicable |
| Measurement | Unit, limit, usage, availability if returned |
| Planning | Incremental demand, concurrent peak, projected breach date |
| Freshness | Collection timestamp, last success, most recent error |
| Ownership | Operator, quota admin, limit-increase point of contact |
| Action | Work required, due date, verification status |

Do not sum tenancy usage with compartment usage, as the compartment may already be counted inside the tenancy total. Do not sum parent and child usage together either.

For fractional values, retain appropriate precision. For empty, unsupported, or unlimited fields, handle per API semantics rather than forcing them to 0.

## 9. Alert Before Hitting Quota Limits

### 9.1. Track Both Utilization Ratio and Time Remaining

Utilization percentage signals proximity to the ceiling:

~~~text
Quota_ratio = Usage / Quota
~~~

Yet what usually dictates when to act is:

~~~text
T_exhaust = Current_headroom / Net_daily_usage_growth

T_prep
= Limit_or_quota_processing_lead_time
+ Deployment_and_verification_time
+ Time_buffer
~~~

Open a work item when `T_exhaust <= T_prep`, or when a known upcoming event needs resources exceeding headroom even if current ratio looks low.

Independent example: quota 96 OCPUs, usage 72 OCPUs, growing steadily at 1 OCPU/day. Headroom is 24 OCPUs, or 24 days. If 14 days are needed for processing, seven days for deployment validation, and seven days for buffer, total lead time is 28 days. Action must start immediately even though only 75% of quota is used.

These durations are team planning assumptions, not Oracle request-processing SLAs. Without historical lead-time data, note the uncertainty and engage support contacts early.

### 9.2. Sample Operational Thresholds

| Sample condition | Action |
| --- | --- |
| Usage above 70% and climbing | Review forecasts, uncleaned resources, and upcoming plans |
| Usage above 85% or time remaining shorter than prep time | Create a task with an owner and due date |
| Usage above 95% or upcoming event lacks headroom | Prioritize before deployment; finalize fallback options |
| Data not refreshed within allowed window | Alert on collector failure; do not conclude capacity is sufficient |

These are illustrative thresholds. For fast growth or scarce resources, alert earlier. For nearly static workloads, avoid noisy alerts lacking concrete actions.

### 9.3. Automate Collection and Alerting

An implementable design:

~~~mermaid
flowchart LR
    A["Scheduled collector job"] --> B["Limits API and inventory"]
    A --> C["Load and data metrics"]
    B --> D["Normalize scope, units, timestamps"]
    C --> D
    D --> E["Compute headroom and forecasts"]
    E --> F["Store history and custom metrics"]
    F --> G["Monitoring Alarm / alerting system"]
    G --> H["Notifications and accountable owners"]
~~~

This is an integration built by the operations team. Do not assume every quota automatically ships a ready-made OCI Monitoring metric for direct alarming.

High-level logic:

~~~text
For each managed resource key:
    Fetch limit, usage, and availability if supported.
    If data failed or is stale:
        Mark UNKNOWN, alert collector owner.
        Never emit a "sufficient" conclusion.
    If data is valid:
        Compare against incremental demand and prep time.
        Emit alert with scope, shortfall, target date, and owner.
Record last successful collection timestamp per resource key.
~~~

When writing the collector, handle pagination, transient errors, backoff retries, and rate limits. Avoid excessive polling or creating per-request metric dimensions.

Capacity snapshots can change as other pipelines or teams provision concurrently. Re-check right before major operations; yesterday's "PASS" result does not lock headroom for today.

## 10. Check Host Capacity and Use Capacity Reservations

### 10.1. Capacity Reports Differ from the Limits API

OCI provides an API/CLI to generate a Compute capacity report evaluating host capacity for a shape configuration in an AD before creating or resizing instances. When calling this CLI, the compartment must be the root compartment. Refer to [compute-capacity-report create](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/compute/compute-capacity-report/create.html).

When using reports, record the exact shape, OCPU, RAM, location, and timestamp evaluated. An available result reflects point-in-time status; reading a report does not reserve resources for a later deployment.

Do not conclude "out of host capacity" from a generic instance-creation failure alone. Read the error or work request to separate host capacity shortages from quota, IAM, image, or configuration errors.

### 10.2. When to Consider Reservations

Capacity reservations fit when the cost of lacking resources on time outweighs the cost of holding unused capacity, such as a fixed-date system cutover or critical recovery requirements.

Compute reservations bind to a specific tenancy and AD; they do not span an entire region. Instances consuming a reservation must match its configuration, including shape and placement criteria. Unused reserved capacity still incurs charges. See [Capacity Reservations](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/reserve-capacity.htm).

Before choosing this option, verify that the shape, account type, and accompanying features support reservations. Do not assume every OCI resource or every Compute mode shares identical reservation mechanics.

### 10.3. Verify Actual Allocated Quantity

When creating a reservation, OCI may fulfill fewer instances than requested, or even zero instances if capacity is unavailable. Read the result after the request finishes. Having a reservation object exist is not proof that the full count was secured. See [Creating a Capacity Reservation](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/capacity-reservations-create_tabs.htm).

Include in plan evidence:

- Requested quantity and actual fulfilled quantity.
- Shape, OCPU, RAM, and AD configuration.
- Used vs. unused counts.
- Test launch result using the reservation.
- Owner, review date, and release conditions.

Do not mark a test "passed" right after submitting the request or inspecting only planned settings.

### 10.4. Track Quotas and Reservation Lifecycle

Compute has quota groups dedicated to capacity reservations; inspect corresponding Reservable and Reserved items. When an instance inside a reservation is terminated, capacity returns to the reservation; unused portions do not vanish on their own. See [Compute Quotas](https://docs.oracle.com/en-us/iaas/Content/Quotas/Concepts/resourcequotas_topic-Compute_Quotas.htm).

Accordingly, after a campaign ends, audit both remaining instances and active reservations. Deleting serving nodes does not prove reservation charges stopped.

### 10.5. Prepare Tested Fallback Options

If on-demand capacity falls short, fallback options may include another shape, another AD, or temporarily shedding background jobs. Every option needs explicit preconditions:

| Fallback option | What to verify beforehand |
| --- | --- |
| Switch CPU family or generation | Performance, images, drivers, licenses, memory, and applicable limit names |
| Switch CPU architecture | Binaries, native libraries, images, and all relevant benchmarks |
| Switch AD | Networking, dependent resources, data locality, and deployment time |
| Switch region | Data, latency, IAM, connectivity, RTO/RPO, and transfer costs |
| Throttle background load or queue | Business impact, backlog drain time, and queue bounds |

Do not treat a shape with more OCPUs as equivalent before re-measuring throughput and cost per unit of work.

## 11. Plan Limit Increases and Quota Allocations

### 11.1. Route Each Issue to the Right Action

| Issue | Appropriate action | Point of contact |
| --- | --- | --- |
| Insufficient service limit | Submit limit-increase request for exact resource and scope | Tenancy owner or Oracle account contact |
| Insufficient compartment quota | Review and adjust internal allocations | Administrator with quota management rights |
| Limits sufficient yet hosts unavailable | Check placement, capacity reports, reservations, or fallbacks | Infrastructure team |
| IAM blocks action | Add permissions for exact resource and compartment | IAM administrator |
| Subnet lacks IPs | Adjust network plan and node rollout layout | Network team |
| Cost exceeds acceptable level | Adjust schedule, sizing, serving scope, or budget | App owner and finance |

A limit-increase request should include:

- Tenancy, relevant subscription, region, and AD if applicable.
- Exact service and limit-name.
- Current limit, current usage, and desired **target** limit.
- Required-by date, growth forecast, and related business events.
- Peak demand during deployments, replacements, or recovery.
- Supporting evidence, contact person, and fallback plan.

Distinguish "increase by 40" from "raise total limit to 160"; state explicitly so targets are unambiguous.

### 11.2. Schedule Backward from the Target Date

Suppose campaign capacity is needed on day D:

~~~text
Day D: operate at campaign configuration
Before D: complete load testing and traffic shift paths
Earlier: verify resources, quotas, and reservations if any
Even earlier: complete limit or quota increase requests
~~~

Lead times between milestones should reflect change calendars, past turnaround experience, and system criticality. For new resource types or large jumps, engage early instead of relying on turnaround from an unrelated prior request.

Track task states cleanly:

~~~text
Planned → Submitted → Approved → Effective value visible
→ Provisioning tested → Ready for use
~~~

An approved request still requires checking the effective limit in the exact scope. Provisioning test evidence also applies only to the tested configuration and timestamp.

### 11.3. Allocate to Leave Room for Operations

When setting quotas for development, test, and production environments, reserve enough room for:

- Steady-state runtime needs.
- Deployments and rollbacks.
- Resource replacements.
- Confirmed upcoming projects or campaigns.
- Recovery operations running alongside current systems.

Team quotas may sum above the service limit if the organization knowingly accepts oversubscription. In that case, you cannot promise every team can scale to its quota simultaneously; establish priority rules and coordination for overlapping demand.

## 12. Tie Capacity to Cost and Utilization Efficiency

### 12.1. Separate Maximum Permitted Ceiling from Billable Runtime

A quota is a consumption boundary; raising a quota does not create instances. A capacity sheet needs two distinct columns:

- **Peak provisionable level needed**, e.g., 11 nodes during rolling deployment.
- **Expected runtime level over time**, e.g., six nodes at low load and nine nodes during peak windows.

For shapes billing CPU and RAM separately, estimate:

~~~text
C_compute
= OCPU-hours × unit_price_OCPU-hour
+ GB_RAM-hours × unit_price_GB_RAM-hour
~~~

Then add storage, storage performance, DB, backups, networking, observability, and dependent services per applicable pricing models.

If reservations exist, separate **used** vs. **unused** hours and quantities. Do not add full reservation costs on top of matching instances as if they were two independent resource sets.

This lesson does not use fixed unit prices. When building real plans, obtain active pricing and commercial terms for the exact configuration, region, and contract.

### 12.2. Combine Cost Forecasting with Technical Forecasting

Cost Analysis projects future spend from historical data. The output is a forecast and can differ from actuals. Supplement it with campaigns, migrations, or architectural changes absent from history. See [Cost Analysis](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/costanalysisoverview.htm).

OCI Budgets is a soft threshold for spend alerts; it does not stop resources from exceeding budget. Therefore, still maintain quotas, autoscaling bounds, and incident procedures separately. See [Track and Manage Usage and Cost](https://docs.oracle.com/en/solutions/oci-best-practices/track-and-manage-usage-and-cost1.html).

Compare at least these options:

| Option | Benefit to evaluate | Costs or conditions to factor |
| --- | --- | --- |
| Run 24/7 at high load sizing | Little reliance on instant scaling | Long stretches of underutilized resources |
| Run minimal baseline and scale with load | Ties cost to demand | Startup lag, headroom, and provisioning availability |
| Reserve capacity for critical load | Secures capacity for key milestones | Unused reservation fees and reservation scope |
| Optimize queries, caching, or batching | Lowers resources per unit of work | Engineering effort, testing, and correctness impact |

Optimization is not merely cutting node counts. An option with higher total cost that preserves SLOs during a critical campaign may fit business goals better.

### 12.3. Measure Cost per Unit of Work

~~~text
Cost_per_1M_requests
= In_scope_cost / Request_count × 1,000,000

Cost_per_order
= In_scope_cost / Successful_orders
~~~

Keep time windows and allocation scopes consistent. State explicitly whether DB, backups, logs, networking, and shared services are included.

Track unit cost alongside latency, errors, and backlog drain time. Cutting cost by letting requests fail or batches miss deadlines fails capacity objectives.

## 13. Practice: Build a 90-Day Plan Using Read-Only Data

This exercise relies on queries and calculations; it does not require creating billable resources or changing quotas.

### Step 1. Lock Scope

Choose an application, compartment, region, and AD if applicable. Record:

- SLOs and peak windows.
- Business units used for forecasting.
- Dependent resources and operations teams.
- 30-, 60-, and 90-day milestones plus deployment or campaign calendars.

If the tenancy has no active workload yet, use the hypothetical numbers in this lesson and mark them clearly as simulated data.

### Step 2. Build the Baseline

Gather historical data or use the stated assumptions. Separate application throughput, provisioned resources, and total compartment usage.

For real metrics, record timestamps, sources, and data gaps. Mark items "measured" only when matching measurement evidence exists.

### Step 3. Calculate Three Demand Scenarios

Compute business demand, node counts, OCPUs, RAM, and storage capacity at each milestone. Document rounding rules and applied headroom factors.

Cross-check scenarios against product calendars. Where unconfirmed assumptions are used, assign an owner and a review date.

### Step 4. Read Limits and Availability

Use the Console or CLI commands from section 8. Retrieve the exact limit-name and scope for every resource checked.

Where the API does not support an item, record `UNKNOWN` along with the next verification step. Never enter 0 or "sufficient" just to fill the table.

### Step 5. Compute Concurrent Peak

Tabulate steady-state, rolling deployment, node replacement, and recovery scenarios. State clearly which states can occur simultaneously.

From the lesson's example:

~~~text
Current: 6 nodes
Planned peak: 11 nodes
Incremental need: 5 nodes = 20 OCPU + 160 GB RAM
~~~

Compare the incremental need against **remaining headroom**, not all 11 nodes against headroom, since the existing six nodes are already in current usage.

### Step 6. Test a Parent-Level Constraint

Use the example where the parent compartment has only 8 OCPUs left. Explain why adding five nodes fails even though the team's own quota shows 24 OCPUs remaining.

Simulate this strictly on a spreadsheet or plan; do not lower real quotas just to provoke an error.

### Step 7. Finalize Actions and Alerts

Every shortfall needs a resource, scope, quantity, required-by date, owner, and fallback option. For resources without immediate shortfalls, compute projected threshold dates and set alerts matching lead time.

If proposing reservations, record expected cost, quantity to hold, and release conditions. Actual creation belongs to a separate infrastructure change with matching cost approval.

### Step 8. Complete the Decision Table

| Item | Peak demand | Current state and headroom | Conclusion | Action |
| --- | --- | --- | --- | --- |
| Compute OCPU | Peak and incremental need | Limit, quota, usage in exact scope | Sufficient / short / unverified | Raise limit, adjust quota, or change option |
| RAM | Peak and incremental need | Corresponding RAM limits | Sufficient / short / unverified | Manage independently of OCPU |
| Storage | Capacity and performance | Data, free space, growth rate | Days to threshold | Expand or tune retention |
| Network | IPs, throughput, connections | Current capacity | Sufficient / short / unverified | Adjust networking before adding nodes |
| Oracle Database | TPS, sessions, I/O, space | Measurements and service config | Bottlenecks and scale conditions | Optimize or resize configuration |
| Host capacity | Shape and placement needed | Reports, checks, or reservations | Verified readiness level | Complete prep before target date |
| Cost | Cost per run schedule | Budget and forecast | Within / outside tolerance | Pick option and internal approver |

## 14. Common Mistakes and Completion Criteria

### 14.1. Conclusions to Avoid

| Faulty conclusion | Consequence | Fix |
| --- | --- | --- |
| Having quota means instances can definitely launch | Plan relies on unverified physical capacity | Check host capacity and reservations when needed |
| Having OCPUs left is enough | Blocked by RAM, IPs, or dependent resources | Track the full provisioning dependency chain |
| Sizing only for steady-state nodes | Deployments or replacements have no room | Size for concurrent peak resource existence |
| Team quota is plentiful so parent levels need no check | Blocked at parent compartment | Evaluate the full compartment tree and shared usage |
| Autoscaling automatically handles every spike | Slow scale-out or rejected launches | Prepare thresholds, boot times, and headroom |
| Adding OCPUs fixes every DB bottleneck | Higher cost without lower latency | Inspect CPU, waits, I/O, locks, and actual load |
| Deleting nodes ends all related costs | Reservations, volumes, or backups remain | Check each resource's lifecycle |
| Collector failure means usage is 0 | Misses impending limit exhaustion | Use UNKNOWN status and freshness alerts |
| Low average CPU proves overprovisioning | Misses spikes or RAM/I/O pressure | Evaluate against SLOs and representative windows |
| Approved limit increase means ready to go | Effective value or physical capacity unverified | Verify effective limits and provisioning evidence |

### 14.2. What a Handover-Ready Plan Must Show

A plan meets requirements when a reviewer can answer using data:

1. What load is served today and projected at each milestone?
2. Which benchmarks and SLOs drive resource demand?
3. What is the concurrent peak during deployments or incidents?
4. Which limits and quotas apply, and in what scopes?
5. How much headroom remains after accounting for shared workloads?
6. When must limit increases or architecture changes begin?
7. To what extent has provisioning feasibility been verified?
8. What are the costs of the runtime schedule and reservations?
9. Who handles each shortfall and by what deadline?
10. When will data, assumptions, and the plan be updated?

Revisit forecasts after campaigns, shape changes, major code changes, or recovery drills. Compare projections against actuals to calibrate growth rates, per-node throughput, prep lead times, and buffers for the next cycle.
