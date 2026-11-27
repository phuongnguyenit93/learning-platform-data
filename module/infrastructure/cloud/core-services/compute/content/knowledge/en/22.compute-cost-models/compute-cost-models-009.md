# Budgeting, Forecasting, and Measuring Cost per Request or Task

A compute system can meet its SLOs yet still exceed budget if operations teams track only the total bill without knowing which workload drives the cost. Conversely, cutting VM counts or unit prices does not necessarily make a service cheaper if latency rises, retries multiply, or task completion rates fall.

Compute budgeting requires connecting three perspectives:

- **Resource cost:** VMs, containers, serverless, GPUs, storage, networking, and supporting services.
- **Workload demand:** request counts, jobs, tenants, processing times, baseline load, and peak load.
- **Service outcomes:** successful requests, on-time completed tasks, SLOs, and output quality.

From there, an organization can forecast costs monthly or by scenario, calculate cost per request/job, pinpoint drivers of variance, and pick the right optimizations. This lesson covers building a cost model from usage, capacity, and billing data; allocating shared costs; calculating unit economics; and operating budgets through the FinOps loop.

## 1. Distinguishing Budgets, Forecasts, and Actual Costs

Three concepts are related but not identical:

- **Budget:** the approved spending limit for a defined scope and period, typically monthly, quarterly, or annually.
- **Forecast:** an estimate of likely spend based on current load, configuration, pricing, policies, and latest trends.
- **Actual:** costs and usage recorded in the billing system once data is updated or finalized.

For example, a team sets a monthly compute budget of 10,000 currency units. By day 15, actuals hit 6,500 and the end-of-month forecast is 12,000. The budget remains 10,000; the forecast signals a likely 2,000 overrun; actuals represent spend incurred to date.

Never alter the budget just to make forecast charts look on track. A budget is an approved ceiling; a forecast must reflect expected reality; actuals must come from the authoritative billing source.

### Common Budget Scopes

- Entire organization or cloud account.
- Business unit, team, or cost center.
- Product/service.
- Environment: production, staging, development, test.
- Region or project.
- Workload or tenant.
- A migration program or time-bounded project.

Every scope needs an owner, budget period, currency, shared cost allocation rules, and data source. If two reports use different scopes or allocation methods, numbers cannot be compared directly.

## 2. Defining the Compute Cost Scope

Compute cost is more than VM rates. A cost model should separate the following groups:

| Cost Group | Example Components | Common Units or Drivers |
|---|---|---|
| Compute | VMs, instance groups, container nodes, serverless, GPUs | Instance-hours, vCPU-time, memory-time, requests, GPU-hours |
| Storage | Block volumes, file storage, object storage, snapshots, backups | GiB-month, IOPS, throughput, operations |
| Network | Egress, inter-zone/inter-region, NAT, public IPs, load balancers | GB transferred, gateway-hours, capacity units |
| Managed services | Databases, caches, queues, streams, search | Instance-hours, storage, requests, throughput tiers |
| Software/licenses | OS, databases, middleware, security agents | Core-hours, host-hours, users, subscriptions |
| Observability | Metrics, logs, traces, retention, queries | Data ingest, GB-month, requests/queries |
| Shared platform | Cluster control planes, registries, CI/CD, support | Fixed fees or allocation drivers |
| Operations | Backup orchestration, security scanning, automation | Direct cost or allocated by workload |

Exact scope depends on reporting goals. An API unit cost report may include databases, caches, load balancers, and networking; a pure compute infrastructure report may cover only VMs/containers/GPUs. State clearly which costs enter the numerator.

### Direct Costs vs. Shared Costs

- **Direct cost:** can be attributed fairly accurately to a workload, such as a GPU job running on a dedicated instance.
- **Shared cost:** consumed by multiple workloads, such as shared Kubernetes nodes, NAT gateways, load balancers, observability workspaces, or multi-tenant database clusters.
- **Unallocated cost:** lacks sufficient metadata or drivers for allocation.

Do not omit shared costs simply because they are hard to split. Counting only direct VMs makes workload unit costs look artificially low. Nor should you allocate arbitrarily; document all drivers and assumptions.

## 3. Building a Cost Model from Usage and Pricing

Basic model:

\[
C_{total} = C_{compute} + C_{storage} + C_{network} +
C_{managed} + C_{license} + C_{observability} + C_{shared}
\]

For each group, cost can be calculated from quantities and effective rates:

\[
C_i = \sum_j Q_{i,j} \times P_{i,j}
\]

Where:
- \(Q_{i,j}\) is the usage quantity of meter or SKU \(j\).
- \(P_{i,j}\) is the corresponding effective unit rate.
- \(C_i\) is the cost of group \(i\).

Examples:
- 500 instance-hours multiplied by the per-instance-hour rate.
- 3,000 GiB-months multiplied by the storage rate per GiB-month.
- 2,000 GB of egress multiplied by tiered unit rates.
- 10 million invocations multiplied by the per-request rate, plus duration/memory-time if billed separately.

### List Price vs. Effective Price

Distinguish:
- List price: published sticker price.
- Contract/negotiated price: agreed contractual rate.
- Effective price: effective unit rate after discounts or commitment allocation per reporting conventions.
- Net cost: cost after adjustments as defined by the billing system.
- Invoice amount: payable amount, which may include taxes, credits, and non-usage items.

Do not multiply list price by usage and call it actual cost if the organization receives discounts, credits, or commitments. Reconcile against billing exports and define columns before building reports.

### One-Time Costs vs. Recurring Costs

Some charges occur once:
- Data migration or transfer egress during cutover.
- Initial snapshot creation.
- License onboarding.
- Dedicated capacity setup.
- Specialized deployment or support fees.

Other charges recur hourly, daily, or monthly. Forecasts must separate both types to avoid projecting a one-time migration expense into every subsequent month.

## 4. Defining Output Units to Calculate Unit Cost

Unit cost is only meaningful when the denominator reflects the outcome the service is meant to deliver.

Usable units include:
- Per incoming request.
- Per successful request.
- Per successful request within SLO.
- Per completed transaction.
- Per completed job.
- Per job completed on deadline.
- Per GB of data processed.
- Per image/video rendered to quality standards.
- Per inference hour or per thousand tokens, if workload-appropriate.
- Per active tenant per month.

### Cost per Request

Two metrics are typically useful:

\[
CostPerAttempt = \frac{AllocatedCost}{TotalAttempts}
\]

\[
CostPerSuccessfulRequest =
\frac{AllocatedCost}{SuccessfulRequests}
\]

If failed requests or retries consume resources, their cost still enters the numerator. When the denominator counts only successful requests, the metric reflects the real cost of producing a successful outcome.

You can add cost per successful on-time request:

\[
CostPerOnTimeSuccess =
\frac{AllocatedCost}{SuccessfulRequestsWithinSLO}
\]

This metric is valuable when latency and deadlines matter. Clearly define what counts as a valid request and how client-canceled requests are treated.

### Cost per Task

For batch jobs or workers:

\[
CostPerCompletedTask =
\frac{Compute + Storage + Network + Retry + SharedCost}
{CompletedTasks}
\]

If tasks finish with unacceptable or unusable outputs, define **accepted tasks** or **successful business outcomes** to avoid inflating the denominator.

### Cost per Unit of Work

Some workloads lack a clear request concept. Use:
- Cost per GB of ETL.
- Cost per record processed.
- Cost per minute of rendered video.
- Cost per inference at a defined batch size.
- Cost per successfully generated report.

Output units must be stable, measurable, and tied to business value.

## 5. Average Unit Cost vs. Marginal Cost

These two costs answer different questions.

- **Average unit cost:** total allocated cost divided by total output units.
- **Marginal cost:** incremental cost of processing one additional unit of work.

\[
AverageUnitCost = \frac{TotalCost}{TotalOutput}
\]

\[
MarginalCost \approx
\frac{\Delta TotalCost}{\Delta Output}
\]

For example, a cluster has a fixed cost of 1,000 currency units/month and processes 10 million requests. Average cost is 0.0001 currency units/request. If the cluster still has spare capacity, adding 1 million requests may only slightly increase network or database usage; marginal cost is lower than average.

Once load exceeds capacity, the system needs another node or a higher database tier. Marginal cost can jump in steps rather than linearly.

### Why Can Average Cost Be Misleading?

- Commitment costs are amortized into the period even when usage is low.
- Shared platform costs are split evenly despite uneven consumption.
- One tenant's burst can force the entire cluster to add nodes.
- Retries and errors raise costs without raising useful output.
- Reserve capacity raises average cost while delivering availability.

When making pricing, capacity, or optimization decisions, examine both average and marginal costs alongside SLOs.

## 6. Measuring Output and Cost in the Same Time Window

To calculate accurate unit costs, numerator and denominator must share the exact same:
- Time window.
- Workload boundary.
- Region/environment.
- Tenant or service scope.
- Currency and cost basis.
- Data state (provisional vs. finalized).

For instance, do not divide November's full cost by requests from only the first 20 days. Do not divide production cost by output that includes staging if staging is outside the scope.

### Billing Delays

Billing exports may arrive late or be adjusted post-usage. Output metrics are usually available near real-time. Today's unit cost report may temporarily use estimated costs, provided it is marked provisional and updated once billing finalizes.

### Timestamp Alignment

Use UTC or a standardized timezone. Account for:
- Usage start/end.
- Event time.
- Ingestion time.
- Invoice period.
- Request completion timestamp.
- Job accepted/completed timestamp.

If costs are recorded by UTC day while outputs aggregate by local day, convert both to the same timezone before comparing.

## 7. Allocating Shared Costs

Shared costs can be allocated using a driver reflecting each workload's consumption or received benefit.

| Shared Resource | Candidate Drivers | Notes |
|---|---|---|
| Kubernetes node compute | CPU requests, CPU usage, memory requests/usage | Choose a consistent rule; include system overhead |
| Database cluster | Query time, connection time, storage, workload tags | Raw query count alone may miss query heaviness |
| NAT/network gateway | Bytes, connections, or flow counts | Egress and connection costs may differ |
| Load balancer | Request count, processed bytes, capacity share | Complex requests may consume unevenly |
| Observability | Log/trace ingest, metric series, or retention | Cardinality and retention drive different costs |
| Shared storage | Capacity, IOPS, throughput, or object count | Capacity alone does not reflect all usage dimensions |
| Platform operations | Fixed share, instance count, or team allocation | State clearly that this is allocated overhead |

### Node Allocation Example

A node costs 120 currency units in a day. Three workloads account for 50%, 30%, and 20% of cumulative allocatable CPU usage respectively. Choosing CPU usage as the driver allocates costs as:

| Workload | Driver Share | Allocated Cost |
|---|---:|---:|
| API | 50% | 60 |
| Worker | 30% | 36 |
| Reporting | 20% | 24 |
| **Total** | **100%** | **120** |

If the goal is chargeback for reserved capacity, requests can replace usage. If the goal is reflecting actual resource consumption, usage fits better. No single driver is universally right for every report.

### Idle Capacity and Headroom

A cluster may hold spare capacity for bursts or failover. Idle costs can be allocated by:
- Each workload's share of reserved capacity.
- Share of demand at peak hours.
- Share of average consumption.
- A general shared platform overhead bucket.

Do not assign 100% of idle costs to the busiest workload if capacity is held for product-wide HA requirements. Document the rationale and allocation policy.

## 8. Building Inventory and Data Sources

A cost model combines multiple sources:

| Source | Primary Data | Used For |
|---|---|---|
| Cloud billing export | SKU, quantity, rate, cost, account, region, resource ID | Actual cost |
| Resource inventory | Instances, disks, IPs, clusters, services, tags | Defining scope and owner |
| Lifecycle events | Start/stop, scale, resize, terminate | Explaining runtime and capacity |
| Metrics | CPU, memory, network, storage, concurrency | Understanding utilization and headroom |
| Application telemetry | Requests, errors, latency, job outcomes | Measuring output and SLOs |
| Queue/batch systems | Enqueue, retry, complete, dead-letter | Measuring tasks and duplicate work |
| Pricing catalog | SKUs and rates by region/time | Building forecasts |
| Finance/contracts | Discounts, commitments, taxes, credits, currency | Calculating effective costs |

### Standardizing Resource Identity

Use stable resource IDs to join billing with inventory. Hostnames or pod names change during scaling or rollouts.

Recommended labels:
- service.
- environment.
- owner/team.
- cost center.
- product/project.
- region.
- tenant if policy permits.
- lifecycle or expiry.

Never put request IDs or user IDs into resource tags. Per-request identifiers belong in traces/logs, not cost allocation tags.

### Data Quality

Before forecasting:
- Check for ownerless resources.
- Check for unmapped SKUs.
- Check currencies.
- Check negative costs from credits/adjustments.
- Check duplicate or delayed billing records.
- Check missing or reset output metrics.
- Check tag coverage.
- Check deleted resources still carrying auxiliary charges.

Flag incomplete data rather than silently treating it as zero.

## 9. Cost Forecasting Methods

Three forecasting approaches can be combined.

### Workload Bottom-Up

Build from demand and configuration:
1. Forecast request/job volume.
2. Estimate safe throughput per instance.
3. Calculate required instances or resources over time.
4. Compute instance-hours or resource-time.
5. Add storage, networking, managed services, licenses, and shared costs.
6. Apply effective prices and discounts.

This fits workloads with solid metrics and capacity models.

### Run-Rate from Actuals

Take recent actuals and extrapolate across remaining days. For example, if the first 10 days of the month cost 3,000, a simple run-rate for a 30-day month is 9,000.

Run-rates are useful for early alerts but fail when facing:
- Seasonal load shifts.
- Campaign days.
- Migrations or one-off backups.
- Billing delays.
- One-time charges.
- Commitments or credits posted on different cycles.

### Growth Top-Down

Start from projected revenue, users, tenants, or business volume and translate to workload. For example, 20% user growth does not always mean exactly 20% request growth; inspect activity rates, caching, and requests per user.

Top-down helps quarterly/annual planning, though it must reconcile bottom-up to verify capacity and pricing.

## 10. Forecasting Compute from Demand and Capacity

For workloads running on fixed VMs or nodes within each interval:

\[
ComputeCost = \sum_t N_t \times H_t \times P_t
\]

Where:
- \(N_t\) is the number of billable instances in interval \(t\).
- \(H_t\) is the interval duration.
- \(P_t\) is the appropriate hourly rate per instance.

If instance types change, split by SKU. With autoscaling, use hourly or daily instance count profiles rather than multiplying end-of-period desired capacity across the whole month.

### Estimating Instance Counts

If one instance safely handles \(Q_{safe}\) requests/second and demand is \(D_t\):

\[
N_t = \left\lceil \frac{D_t}{Q_{safe}} \right\rceil
\]

Add capacity for:
- N-1 instance/AZ failure.
- Rolling deployment surges.
- Autoscaling delays.
- Bursts and traffic uncertainty.
- Background workloads.
- SLO-driven headroom.

Do not double-count headroom if \(Q_{safe}\) was already measured with utilization targets and failure reserves built in.

### Time-Segmented Forecasting

A system with heavy daytime load and light nighttime load should not be forecasted using a 24-hour average if autoscaling scales hourly. Split time into intervals:
- Business hours.
- Night hours.
- Weekends.
- Campaigns/peaks.
- Batch windows.
- Maintenance windows.

Compute capacity and cost per interval, then sum. This captures schedules and autoscaling far more accurately.

## 11. Low, Base, and High Scenarios

Forecasts always carry uncertainty. Instead of a single number, build three scenarios:

- **Low:** lower-than-expected demand, strong utilization optimization, no major incidents.
- **Base:** highest-probability forecast under current plans.
- **High:** high growth or bursts, rate/egress changes, higher retries, or larger capacity reserves.

Example:

| Driver | Low | Base | High |
|---|---:|---:|---:|
| Requests/month | 60 million | 80 million | 110 million |
| Peak multiplier | 1.5x | 2x | 2.5x |
| Instances needed at peak | 5 | 7 | 10 |
| Egress | 1.2 TB | 1.8 TB | 2.8 TB |
| Retry overhead | 1% | 3% | 7% |
| Capacity reserve | 10% | 20% | 30% |

Numbers in the table are illustrative assumptions. Each scenario must translate into usage quantities and costs per SKU, not simply multiply the total bill by an arbitrary factor.

### Scenario Drivers

Vary explicit drivers:
- Request growth.
- Average payload size.
- Cache hit ratio.
- CPU time per request.
- DB query time.
- Retry rate.
- Peak-to-average ratio.
- Number of replicas.
- Price/discounts.
- Storage retention.
- Egress per request.

This makes it clear which driver caused the delta whenever forecasts shift.

### Sensitivity Analysis

Quantify the impact when one driver moves. For instance, egress costs can jump sharply if response payloads grow; compute costs can step up when peaks exceed current capacity and force another replica.

Do not assume every cost scales linearly with request volume. Some items are fixed, some variable, some stepwise, and some tiered.

## 12. Fixed, Variable, and Stepwise Costs

Classifying cost behavior improves forecasts:

- **Fixed:** stays nearly constant within a given operating range, such as a subscription or minimum platform fee.
- **Variable:** changes with usage, such as requests, egress, or invocations.
- **Stepwise:** holds steady across a range then jumps when crossing a threshold, such as adding a VM, upgrading a database tier, or adding a node.
- **Hybrid:** combines fixed and variable parts, such as a cluster with baseline nodes plus autoscaling nodes.

A simple model:

\[
C = F + v \times U
\]

Where \(F\) is fixed cost, \(v\) is variable rate, and \(U\) is usage. For stepwise costs, add capacity or tier thresholds.

### Stepwise Example

One VM safely handles 1,000 requests/second. If peak is 900 requests/second, the team runs 1 VM. When peak grows to 1,100, 2 VMs may be needed. Compute cost nearly doubles even though demand rose only 22%.

This is why forecasts must incorporate capacity thresholds instead of simply scaling current cost by the request growth ratio.

## 13. Forecasting by Pricing Model

### On-Demand

Calculate usage against current meters and unit rates. Fits as a flexible baseline, though runtime, scaling profiles, and auxiliary resources must be forecasted.

### Reserved/Committed Use

Commitments lower unit rates while creating payment or coverage obligations for the term. When forecasting:
- Calculate eligible usage covered.
- Separate committed amounts from on-demand spillover.
- Allocate commitments per policy.
- Track commitment utilization/coverage.
- Account for unused portions if any.
- Track start/end dates and workload shifts.

A lower unit rate commitment does not guarantee lower total cost if usage falls short of the commitment. Compare total scenario costs, not just unit rates.

### Spot/Preemptible

Lower pricing with reclamation risk. Cost models must include:
- Useful compute time.
- Work lost upon interruption.
- Checkpoint storage and transfer.
- Retry/restart overhead.
- Fallback to on-demand.
- Job completion rates and deadlines.

Low unit prices paired with heavy retries can produce a higher cost per successful task.

### Serverless

Calculate:
- Request/invocation counts.
- Duration.
- Memory or CPU allocation.
- Provisioned/warm concurrency.
- Retries and timeouts.
- Data transfer and dependencies.

For continuously running workloads, compare serverless against VMs/containers on total cost at identical throughput and SLOs.

### GPU/Accelerators

Do not count only GPU-hours. Include:
- GPU count/type.
- Host CPU/RAM.
- Storage throughput and checkpoints.
- Network bandwidth.
- Idle GPU time.
- Batch size and utilization.
- Failed/aborted training time.
- Licenses and accelerator software stacks.

Unit economics may be cost per training step, per model run, per inference, or per accepted output.

## 14. Calculating Cost per Request for an API

An API usually has multiple cost components. A cost model can include:

\[
C_{API} = C_{app} + C_{database} + C_{cache} +
C_{network} + C_{loadbalancer} + C_{observability} + C_{shared}
\]

### Monthly Illustrative Example

Suppose an API has the following allocated costs:

| Component | Monthly Cost (Currency Units) |
|---|---:|
| Application VMs | 613.20 |
| Worker VMs | 197.10 |
| Managed database | 900.00 |
| Cache | 180.00 |
| Storage/backup | 120.00 |
| Network egress | 240.00 |
| Load balancer/NAT | 80.00 |
| Observability | 110.00 |
| Shared platform | 160.00 |
| **Total** | **2,600.30** |

During the month:
- 90 million request attempts.
- 80 million successful requests.
- 76 million successful requests within SLO.

Cost per attempt:

\[
2600.30 / 90{,}000{,}000
\approx 0.00002889
\]

Cost per successful request:

\[
2600.30 / 80{,}000{,}000
\approx 0.00003250
\]

Cost per successful on-time request:

\[
2600.30 / 76{,}000{,}000
\approx 0.00003421
\]

Cost per 1,000 successful requests is approximately 0.03250 currency units. This is an arithmetic illustration, not real cloud pricing.

### Interpreting Results

If cost per successful request rises, causes may include:
- Costs growing faster than output.
- Falling request success rate.
- Rising retries or timeouts.
- Falling cache hit ratio.
- Slow database queries holding workers longer.
- Peak traffic forcing extra reserve capacity.
- Rate or egress changes.

Do not jump straight to resizing VMs. Break down costs by component and examine request mix and SLOs before making changes.

## 15. Calculating Cost per Batch Task

For batch workers, measure the cost of the entire task lifecycle:

\[
C_{task} =
C_{compute} + C_{storage} + C_{network} +
C_{checkpoint} + C_{retry} + C_{orchestration}
\]

Example batch of 10,000 tasks:
- Worker compute: 0.80 currency units.
- Checkpointing/storage: 0.15.
- Data transfer: 0.05.
- Retry overhead: 0.20.
- Total: 1.20.
- Completed and accepted tasks: 9,600.

\[
CostPerAcceptedTask = 1.20 / 9600 = 0.000125
\]

If optimization cuts retries from 0.20 down to 0.05 while compute stays unchanged, cost per accepted task drops. Looking only at VM prices would miss that gain.

### Batches with Varying Durations

You can calculate:
- Cost per task.
- Cost per CPU-second.
- Cost per GB processed.
- Cost per successful batch.
- Cost per deadline-compliant batch.

Pick metrics suited to the work. A huge task may consume multiples of a small task's resources, making simple cost per task unfair. Group by size or complexity where needed.

## 16. Monthly and Quarterly Forecasting

A practical forecast should include:
- Actual-to-date.
- Estimate for the remainder of the period.
- One-time costs.
- Run-rate.
- Seasonal adjustments.
- Price/discount assumptions.
- Capacity plans.
- Low/base/high scenarios.
- Confidence levels and owners.

### Monthly Forecast

Split into:
- Actuals from month start through data cutoff.
- Daily/weekly forecast for remaining days.
- Recurring fixed charges.
- One-time project or migration costs.
- Expected credits/adjustments.

Do not use a simple run-rate if the month includes campaigns or periodic batch runs. Use day-of-week profiles and event calendars instead.

### Quarterly/Annual Forecast

Use long-term drivers:
- User/tenant growth.
- Requests per active user.
- Payload sizes.
- New feature adoption rates.
- Retention policies.
- Region expansion.
- Replica counts.
- Pricing/commitment renewals.
- Architectural changes or migrations.

Set assumption review dates. A 12-month forecast must be refreshed whenever traffic, SKUs, pricing, or architecture changes.

## 17. Building an Auditable Forecast Workbook

A workbook or data model should contain the following tabs/sections:

### Assumptions

- Currency and forecast period.
- Regions and SKUs.
- Effective rates.
- Demand growth.
- CPU time/request.
- Memory/request.
- Egress/request.
- Cache hit ratio.
- Retry rate.
- Capacity per instance.
- Headroom and availability reserves.
- Commitment coverage.
- Shared cost allocation policies.

### Workload Forecast

- Requests/jobs per day or month.
- Peak/average ratio.
- Success rate.
- On-time success rate.
- Payload/data processed.
- Retry count.
- Tenant/product mix.

### Resource Forecast

- Instance count by interval.
- Instance-hours or resource-time.
- Provisioned/consumed storage.
- Network transfer.
- DB/cache/queue capacity.
- GPU-hours.
- Warm/provisioned capacity.
- Rollout/failover reserves.

### Cost Forecast

- Quantity per meter.
- Unit rates.
- Discounts/commitments.
- Direct costs.
- Shared costs.
- One-time costs.
- Taxes/credits if in scope.
- Low/base/high totals.

### Unit Economics

- Cost per attempt.
- Cost per success.
- Cost per on-time success.
- Cost per job/GB/output.
- Marginal cost.
- SLOs and quality indicators.

### Actual vs. Forecast

- Budget.
- Actual.
- Forecast.
- Variance amount.
- Variance percent.
- Driver explanations.
- Owner.
- Action/date.

## 18. Variance Analysis: Explaining Differences

Variance:

\[
Variance = Actual - Budget
\]

Variance percentage:

\[
Variance\% = \frac{Actual - Budget}{Budget} \times 100\%
\]

When actual exceeds budget, variance is positive under this convention. Some organizations flip the sign to denote favorable/unfavorable; standardize the sign convention across dashboards.

### Decomposing Variance

Break variance into:
- Volume variance: more requests/jobs than forecasted.
- Rate variance: unit rate or SKU shifts.
- Mix variance: workload mix or instance type shifts.
- Efficiency variance: higher CPU time, retries, or resources per request.
- Capacity variance: added replicas, failover reserves, or idle capacity.
- Shared allocation variance: changes in allocation drivers.
- One-time variance: migration, incident, or project charges.
- Billing timing: delayed ingestion or adjustments.

### Example

Actual cost rose 15% over forecast. Analysis shows:
- Requests grew 8%.
- Egress/request grew 4% due to larger payloads.
- Retry rate rose from 2% to 4%.
- One database tier was upgraded in the final week.

Never report generically that "the cloud bill went up". Tying variance to drivers points directly to the right action: optimize payloads, fix retry bugs, tune queries, or update capacity forecasts.

## 19. Budgets and Guardrails

Budget alerts should fire at multiple levels:
- Threshold warnings at 50%, 75%, and 90% of budget.
- End-of-period forecast projected to exceed budget.
- A service showing rapid unit cost growth.
- A project containing ownerless resources.
- An SKU or region showing abnormal usage.
- Low commitment utilization.
- Spot fallbacks driving up on-demand spend.
- Idle GPUs or underused serverless provisioned capacity.

### Budgets Are Not a System Kill Switch

Never auto-stop production solely because a budget hits 100%. Responses must match severity and policy:
- Notify owners.
- Verify anomalies.
- Stop unneeded dev/test resources.
- Throttle or defer non-critical batch work.
- Lower log retention if policy allows.
- Adjust autoscaling guardrails safely.
- Request budget increases when traffic growth is legitimate.

Production guardrails must preserve SLOs and availability. Cost controls must distinguish mandatory workloads, deferrable workloads, and stoppable workloads.

### Anomaly Detection

Compare actuals against baselines for:
- Same day of week.
- Same hour of day.
- Same request volume.
- Same tenant count.
- Same deployment version.

A cost spike may reflect legitimate growth. Combine usage, output, and SLOs to distinguish anomalies from rising demand.

## 20. FinOps: Operating Cost Models in a Continuous Loop

FinOps connects engineering, finance, and product to manage cloud spend against delivered value.

A practical loop:

1. **Inform:** gather costs, usage, ownership, output, and SLOs.
2. **Optimize:** rightsize, schedule, autoscale, cache, improve efficiency, optimize pricing models.
3. **Operate:** maintain budgets, forecasts, owners, policies, and regular reviews.
4. **Measure:** audit unit costs, variances, quality, and business outcomes.
5. **Repeat:** refresh assumptions and actions from new data.

### Roles

- Engineering measures resource usage, capacity, and performance.
- Finance manages budgets, invoices, commitments, and forecasts.
- Product defines output, demand, feature mix, and business value.
- Platform/FinOps builds tagging, allocation, dashboards, and policies.

Do not hand all cloud costs solely to finance without engineering workload metrics; nor let engineering optimize unit rates blind to business value.

## 21. Choosing Optimization Actions from Unit Economics

| Signal | Actions to Test | Confirmation Metrics |
|---|---|---|
| Prolonged low CPU, VM billed overnight | Schedule, scale down, or resize | Instance-hours, p95, cost/request |
| High CPU, flat throughput | Profile, tune workers, or add targeted capacity | CPU, queues, throughput, p99 |
| Rising retry rate | Fix dependency errors, backoff/jitter, idempotency | Retry cost, success rate |
| High egress/request | Compress payloads, cache, shrink responses, or reroute | GB/request, latency, cost/success |
| Rapidly rising DB cost | Query optimization, caching, connection tuning | Query cost, DB CPU, p95 |
| Heavy shared-node idle | Bin packing, node pool sizing, autoscaling | Node-hours, utilization, unit cost |
| Low commitment utilization | Adjust coverage at renewal | Commitment waste, effective rate |
| Low GPU utilization | Batch, schedule, rightsize accelerators | GPU-hours/output, idle GPU |
| Idle serverless provisioned capacity | Tune provisioned concurrency or warm pools | Cold starts, provisioned cost, SLOs |
| Cost/request drops while errors rise | Evaluate quality trade-off | Success/on-time rate, errors, customer impact |

Every optimization should have:
- A baseline.
- A hypothesis.
- Small, reversible changes.
- SLO guardrails.
- Cost measurement.
- Before/after results.
- An owner and review date.

Never claim savings based solely on list prices. Confirm using actual costs or forecasts normalized for equivalent demand and scope.

## 22. Common Mistakes

1. **Forecasting solely from last month's total bill.** Ignores growth, seasonality, SKUs, and architectural changes.
2. **Using request attempts as the sole denominator.** Retries and errors hide true cost per success.
3. **Omitting shared costs.** Produces artificially low unit costs that fail to reconcile with total bills.
4. **Allocating shared costs without a policy.** Teams cannot explain or compare figures.
5. **Using average CPU to forecast instance counts.** Peaks, queues, DBs, memory, and AZ reserves may drive capacity.
6. **Assuming costs scale linearly with requests.** Autoscaling and pricing tiers create stepwise costs.
7. **Ignoring retries and failed work.** Consumed compute still costs money even with zero output.
8. **Failing to separate one-time costs.** Migrations or incidents distort forecasts for subsequent months.
9. **Confusing list price with effective cost.** Discounts/commitments alter real unit rates.
10. **Ignoring commitment waste.** Lower unit rates with insufficient usage can raise total cost.
11. **Misaligned time windows.** Mismatched numerator and denominator periods corrupt unit costs.
12. **Cutting costs by degrading SLOs.** Cost per success must always be read alongside latency, availability, and quality.
13. **Lacking variance owners.** Nobody takes responsibility to investigate or act.
14. **Using unfinalized billing data without labels.** Ingestion delays skew actuals and forecasts.

## 23. Comprehensive Example: API Forecast and Unit Cost

An API currently serves 80 million successful requests per month. The team forecasts 10% monthly growth next quarter. Capacity testing shows each instance safely handles 12 million requests/month under the current load profile, plus a 20% capacity reserve is required for peaks and failover.

### Calculating Capacity

Month 1 forecasted demand:

\[
80M \times 1.10 = 88M
\]

Instances needed by safe throughput:

\[
\lceil 88 / 12 \rceil = 8
\]

If the 20% capacity reserve is not already built into `Q_safe`, add it per policy and round appropriately. If `Q_safe` already incorporates that headroom, do not add it twice.

### Forecasting Cost

Break down costs:
- Application compute by instance-hours.
- Worker compute by job volume.
- Database by tier and storage.
- Cache by memory capacity.
- Network by egress/request.
- Observability by ingest volume.
- Shared platform by allocation rules.

Forecast month by month with request growth, peak profiles, and pricing assumptions. As requests grow alongside higher cache hit ratios, database costs may grow slower than compute. If payloads grow larger, network costs may outpace request growth.

### Tracking Unit Economics

Report monthly:
- Cost per attempt.
- Cost per successful request.
- Cost per successful on-time request.
- Cost per 1,000 requests.
- Error/retry rates.
- p95/p99 latency.
- Cost breakdown by component.

If cost/request drops while p99 breaches SLO, the optimization failed its goal. If cost/request rises from holding added HA reserves while availability improves to target, evaluate it against service value and risk reduction.

## 24. Budgeting and Unit Economics Checklist

### Scope and Data
- [ ] Defined period, currency, service, and environment.
- [ ] Defined direct, shared, and excluded costs.
- [ ] Billing exports contain SKU, quantity, unit, region, and cost basis.
- [ ] Resource inventory includes ID, owner, and tags.
- [ ] Output metrics include request/job success and timestamps.
- [ ] Billing delays and finalized states are explicitly flagged.

### Cost Model
- [ ] Separated compute, storage, network, managed services, and licenses.
- [ ] Separated one-time costs from recurring costs.
- [ ] List prices and effective/net costs are never mixed.
- [ ] Commitments, credits, and Spot/fallbacks are modeled accurately.
- [ ] Shared costs have approved allocation drivers and policies.
- [ ] Idle/HA reserves are allocated with documented rationale.

### Forecast
- [ ] Applied appropriate bottom-up, run-rate, or top-down methods.
- [ ] Demand forecasts capture peaks and seasonality.
- [ ] Capacity relies on safe throughput and SLOs.
- [ ] Built low/base/high scenarios.
- [ ] Tested sensitivity to retries, payloads, prices, and growth.
- [ ] Modeled fixed, variable, and stepwise costs.
- [ ] Combined actual-to-date with rest-of-period forecast.

### Unit Economics
- [ ] Defined successful requests/tasks.
- [ ] Separated cost per attempt from cost per success.
- [ ] Included cost per on-time success where needed.
- [ ] Numerator and denominator share identical time windows/scopes.
- [ ] Accounted for retries, failed work, and shared costs.
- [ ] Tracked both average and marginal costs.
- [ ] Evaluated unit costs alongside SLOs and quality.

### Governance
- [ ] Clear budget owners and workload owners.
- [ ] Configured budget alerts and forecast-overrun alerts.
- [ ] Performed variance analysis by volume/rate/mix/efficiency.
- [ ] Established anomaly handling and approval workflows.
- [ ] Optimizations include baselines, guardrails, and rollbacks.
- [ ] Forecasts and allocation policies undergo periodic review.

## Conclusion

Effective compute budgeting connects demand, capacity, pricing, and workload outcomes. Good forecasts model request/job volumes, peaks, safe throughput, resource-time, shared services, discounts, and one-time expenses. Unit costs must use meaningful outputs like successful requests or accepted tasks while capturing retries and shared costs. Tracking average cost, marginal cost, variance, SLOs, and quality reveals whether rising spend stems from demand, rates, efficiency, or capacity reserves. When cost models have clear owners, clean data sources, and regular updates via the FinOps loop, teams forecast more accurately, explain bills clearly, and optimize spend without sacrificing service quality.
