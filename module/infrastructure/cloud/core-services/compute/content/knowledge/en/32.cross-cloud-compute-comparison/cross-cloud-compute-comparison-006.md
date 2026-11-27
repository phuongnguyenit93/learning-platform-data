# Comparing Interruptible Resources, Cost Commitments, and Capacity Reservations

When running compute on the cloud, organizations routinely choose among on-demand resources, lower-priced interruptible resources, long-term usage commitments for discounts, and reserved capacity to guarantee provisioning availability. These options solve different problems. **Spot/Preemptible lowers prices in exchange for accepting interruptions; savings plans or committed-use discounts reduce unit prices when committing to spend/usage; capacity reservations guarantee matching resources within the reserved scope.** A discount program does not automatically guarantee capacity, and a capacity reservation does not necessarily generate a discount by itself.

In multi-cloud environments, product names and commitment scopes vary across providers. Compare them by economic and operational mechanics rather than names alone. This lesson uses common concepts from AWS, Microsoft Azure, and Google Cloud as examples while focusing on identifying suitable workloads, calculating total cost, managing interruption risk, and avoiding over-committing.

## 1. Four Compute Purchasing Options and Their Goals

| Category | Primary Goal | Trade-Off | Key Question to Answer |
|---|---|---|---|
| On-demand/pay-as-you-go | Flexible provisioning, pay as you use | Unit price is usually higher than committed options | How much flexibility does the workload need? |
| Spot/Preemptible/interruptible | Utilize spare capacity at lower cost | Can be reclaimed; unsuitable for all workloads | Can the work be interrupted and resumed? |
| Savings/commitment discount | Lower unit price by committing spend or usage | Financial obligation over the commitment term | Is baseline usage stable enough to commit? |
| Capacity reservation | Reserve provisioning capability for a resource type within a scope | May incur fees even when unused | Do we need guaranteed capacity in a specific zone/region? |

An architecture can combine all four. For instance, databases and control planes use on-demand or reserved capacity; steady baseline workloads use compute commitments; batch jobs run on Spot; capacity shortfalls fall back to on-demand.

### Three Questions Not to Conflate

1. **How much does it cost?** This is a question about unit prices, discounts, and billing commitments.
2. **Can we launch machines when needed?** This is a question about capacity availability, quotas, regions, and placement.
3. **Can machines be stopped mid-run?** This is a question about interruption policies and workload fault tolerance.

An option may excel at one question while failing the other two. For example, a compute commitment lowers the bill for eligible usage, yet it does not guarantee a specific instance can always launch in a desired zone.

## 2. On-Demand: The Flexible Baseline

On-demand means paying per usage without purchasing a prior long-term commitment. Organizations can create or delete instances as needed within provider quotas and available capacity.

### Advantages

- Flexible when demand fluctuates or is hard to forecast.
- No need to forecast long-term usage to buy commitments.
- Fits development, testing, short-lived workloads, or variable load segments.
- Serves as a useful fallback when Spot capacity is reclaimed or reserved capacity is exhausted.

### Limitations

- Unit price is typically higher compared to effective rates after commitment discounts.
- Does not guarantee infinite capacity; quotas, instance families, zones, and infrastructure conditions can still constrain provisioning.
- If workloads run steadily year-round, paying 100% on-demand can be expensive.

On-demand serves as a helpful baseline for cost comparisons. When evaluating a savings program, compare against on-demand costs for the exact same configuration, region, OS, licenses, usage hours, and accompanying components.

## 3. Spot, Preemptible, and Interruptible Compute

Spot/Preemptible uses spare provider capacity offered at a lower price. The provider reserves the right to reclaim capacity to serve other demand or maintain infrastructure. Therefore, users must design workloads to tolerate stopped instances or tasks.

Names differ by platform, yet core characteristics are similar:

- Capacity may be unavailable at launch time.
- Running instances can be reclaimed according to provider policy.
- Interruption notices may be issued, though warning times and exact behaviors differ.
- Do not rely on Spot for workloads requiring continuous uptime without failover/checkpoint mechanisms.
- Pricing and interruption rates fluctuate by region, zone, family, size, and time.

### Provider Product Examples

| Provider | Common Name | Aspects to Compare |
|---|---|---|
| AWS | EC2 Spot Instances | Uses spare EC2 capacity; can receive interruption notices; diversify instance types/zones and use capacity-optimized allocation where appropriate |
| Microsoft Azure | Azure Spot Virtual Machines | Lower price than pay-as-you-go; offers eviction policies and optional max price per product; no continuous capacity guarantee |
| Google Cloud | Spot VMs | VMs may be preempted; fits workloads that can restart/resume; check limits and behavior by machine series/region |

Service names, terms, prices, and features are subject to change. When planning in production, check current documentation and pricing by region, machine family, OS/licensing, and workload type.

### Suitable Workloads

- Batch processing divisible into chunks.
- Recreateable CI/CD runners and test workers.
- Rendering, encoding, or image processing with checkpoints.
- Distributed training capable of saving model/optimizer checkpoints.
- Big data jobs capable of retrying partitions.
- Stateless workers processing messages with at-least-once semantics.
- Development or test environments that can tolerate shutdowns.

### Workloads Generally Unsuitable as Single-Instance Spot

- Database primaries or stateful systems without replication/failover.
- Control planes or management services without redundancy.
- Interactive applications with uninterruptible user sessions.
- Long-running tasks without checkpoints and high rerun costs.
- Workloads with licenses or devices tightly bound to a single instance.
- Services with ultra-short RTOs and no capacity fallback.

Spot can still participate in these systems as auxiliary workers or non-critical replicas if failure modes are explicitly designed for.

## 4. Designing Workloads to Tolerate Interruptions

Low Spot prices pay off only if interruptions do not discard excessive work or cause unacceptable business impact.

### Chunking and Checkpointing

Split jobs into partitions/chunks with clear commit boundaries. Store checkpoints in object storage, databases, or persistent storage independent of instance lifecycles. When a worker is reclaimed, a new task resumes from the valid checkpoint.

A checkpoint should contain:

- Job ID and partition/chunk ID.
- Input version or snapshot ID.
- Processed offset/cursor/step.
- Algorithmic state needed to resume.
- Code/schema version and output reference.
- Checksum, sequence number, and creation timestamp.

Publish a checkpoint only after data is uploaded and verified. Never overwrite a good checkpoint with a partially written file.

### Idempotency and Retries

A task may be reassigned after an interruption or lost acknowledgment. Use stable idempotency keys, deterministic output keys, conditional writes, or deduplication so reruns do not create duplicate side effects.

Retries should include:

- Classification of transient vs. permanent errors.
- Exponential backoff and jitter.
- Maximum attempt counts and total retry time bounds.
- Dead-letter handling or escalation states when limits are exceeded.
- Concurrency limits to avoid retry storms.

### Graceful Shutdown

Upon receiving an interruption notice or stop signal, workers should stop taking new work, finish safe units of work, save checkpoints, flush logs, and exit within the allotted window. However, notices may not arrive or the window may be too short; periodic checkpointing remains mandatory.

### Diversification and Fallback

Do not depend on a single instance type or single zone. Use multiple compatible machine families, multiple zones, or distinct capacity pools whenever the workload allows. If Spot lacks capacity, the scheduler can retry later, switch pools, or fall back to on-demand within budget.

## 5. Savings Plans and Spend Commitments

Savings plans or equivalent programs reduce unit prices when a customer commits to an eligible spend level over a set term. The provider applies discounted rates to qualifying usage per product rules; unused portions of the commitment may still be billed.

### General Mechanics

- Organization estimates baseline usage over the term.
- Selects commitment amount, term, applicability scope, and payment option.
- Qualifying usage is billed at discounted rates.
- Usage exceeding the commitment is typically billed at standard/on-demand rates or covered by other programs.
- If usage falls below the commitment, the unused portion becomes wasted spend.

A spend commitment is a financial obligation; it is not automatically an instance-allocation reservation. Read carefully whether the commitment is measured in USD/hour, resource units, service types, or other metrics.

### Provider Examples

| Provider | Common Program | Points to Compare |
|---|---|---|
| AWS | Compute Savings Plans, EC2 Instance Savings Plans | Hourly spend commitment; flexibility scope varies by plan type; discounts apply to eligible usage rather than reserving capacity |
| Microsoft Azure | Savings plan for compute | Hourly spend commitment over term; compute scope and eligibility depend on program terms |
| Google Cloud | Spend-based or resource-based Committed Use Discounts (CUDs) | Mechanics and scope differ by CUD type; verify resource family, region, project/organization, and discount application |

Product names, discount levels, terms, and application rules can change. Do not compare advertised discount percentages across providers without normalizing usage type, region, OS/licensing, term, payment option, and amortized cost calculations.

### When Suitable

- Baseline workloads running steadily across many months.
- Production services with relatively stable baseline capacity.
- Compute fleets with enough usage history to forecast accurately.
- Organizations capable of centralized commitment governance and cost allocation across teams.

### Risks

- Over-forecasting leaves commitments underutilized.
- Workloads move regions/families/services and become ineligible.
- Growth or traffic drops diverge sharply from forecasts.
- Overlapping commitment programs complicate effectiveness attribution.
- Commitment buyers and consuming teams lack transparent cost-sharing mechanisms.

## 6. Reserved Instances and Committed-Use Discounts

Reserved Instances (RIs) or committed-use discounts are commitment programs tied to configurations, resource levels, or spend over a fixed period. Depending on the provider, a reservation may provide billing discounts, capacity reservations, or both within a specific scope.

Crucially, read the product definition rather than inferring from the word "Reserved". In some clouds, reservations are strictly a billing discount mechanism while capacity reservation is a separate product. In other cases, zone- or resource-specific reservations also confer capacity assurance.

### Dimensions to Compare

- Region or zone.
- Machine family/series and size.
- OS, tenancy, licensing, or platform.
- Commitment term.
- Payment option: all upfront, partial upfront, monthly, or no upfront.
- Sharing scope across accounts/projects/subscriptions.
- Ability to exchange, modify, cancel, or sell under product terms.
- How discounts apply to usage and precedence relative to other programs.

### Provider Examples

| Provider | Discount/Commitment Concept | Capacity Concept to Distinguish |
|---|---|---|
| AWS | EC2 Reserved Instances and Savings Plans | Zonal Reserved Instances can provide capacity reservation within eligible scope; Regional RIs are primarily billing discounts; On-Demand Capacity Reservations are a separate capacity-holding mechanism |
| Azure | VM Reservations and Savings plan for compute | Reservations lower costs for matching usage; On-demand Capacity Reservation is a separate mechanism for reserving capacity within supported scope |
| Google Cloud | Committed Use Discounts | Compute Engine reservations hold capacity for matching configurations/zones; verify CUD applicability rules alongside reservations and specific resources |

Product details change and carry per-resource-type exceptions. Check provider documentation before signing commitments or finalizing capacity plans.

## 7. Capacity Reservations: Guaranteeing Provisioning

A capacity reservation sets aside a specified amount of resources within a provider-supported scope—such as region/zone, machine family, size, platform, or hardware attributes. The goal is to minimize the risk of failing to launch instances when needed.

Capacity reservations matter especially for:

- Production workloads needing to scale or recover inside a specific zone.
- Disaster recovery requiring ready compute in the target region.
- Workloads requiring scarce GPUs/accelerators or specialized machine families.
- Applications with predictable high-traffic events.
- Systems needing rapid replacement of failed instances without waiting for capacity to free up.

### Capacity Reservations Do Not Automatically Lower Prices

Reservations may be billed for the reserved resources even while idle, depending on the service and reservation type. If you want both guaranteed capacity and unit discounts, check whether the provider allows commitment discounts to apply to usage covered by reservations.

### Scope and Flexibility

A reservation can be constrained by:

- Specific zone or region.
- Instance family/series, size, and CPU architecture.
- GPU type, accelerator, or local storage.
- OS/platform and tenancy.
- Instance count or capacity units.
- Start time, end time, and modification rules.

The narrower the reservation, the more reliably it secures the exact capacity needed—but the higher the risk of mismatch if architecture evolves. Balance certainty against reusability.

## 8. Distinguishing Discount Commitments from Capacity Reservations

| Question | Savings/Committed-Use Discount | Capacity Reservation |
|---|---|---|
| Goal | Reduce cost for eligible usage | Guarantee capacity provisioning availability |
| Financial commitment? | Usually yes over the commitment term | May incur capacity-holding charges by time and usage |
| Guarantees instance launch? | Not automatically | Within supported scope, configuration, and reservation terms |
| Risk of underutilization? | Yes; unused commitment can go to waste | Yes; idle capacity can still incur charges |
| Scope | Can flex across spend, family, region, or resources | Usually tied to a specific region/zone and capacity configuration |
| When to use | Baseline usage is sufficiently stable | Guaranteed capacity is needed at specific times/locations |

An organization can purchase a savings plan to lower baseline costs while maintaining capacity reservations for critical zones/instances. Verify discount application order and billing rules so benefits are not double-counted.

## 9. Quick Comparison Across AWS, Azure, and Google Cloud

The table below is a conceptual map, not a price sheet or guarantee across all SKUs. Product names and support vary by service, region, and time.

| Need | AWS | Azure | Google Cloud |
|---|---|---|---|
| Interruptible compute | EC2 Spot Instances | Azure Spot VMs | Spot VMs |
| Flexible spend commitment | Compute Savings Plans; EC2 Instance Savings Plans | Savings plan for compute | Spend-based CUDs per service |
| Resource/config commitment | EC2 Reserved Instances | VM Reservations | Resource-based CUDs per type |
| Dedicated capacity hold | On-Demand Capacity Reservations; some zonal RIs include capacity benefit | On-demand Capacity Reservation | Compute Engine reservations |
| Spot questions | Interruption behavior, pools, allocation strategy | Eviction policy, max price, capacity | Preemption behavior, machine series, and zone |
| Commitment questions | Spend/hour, plan scope, eligible usage | Hourly commitment, eligible compute scope | CUD type, resource scope, and sharing |
| Reservation questions | AZ, instance attributes, reservation utilization | Region/zone, VM attributes, reservation scope | Zone, machine type, reservation matching |

### Fair Comparison Principles

When comparing the three providers, normalize:

1. Identical vCPU, memory, and CPU architecture or equivalent benchmark performance.
2. Identical region or equivalent latency/data residency constraints.
3. Identical OS, licensing, tenancy, and accelerators.
4. Identical usage hours and load profile.
5. Identical commitment term and payment option.
6. Identical level of capacity assurance.
7. Identical assumptions for interruptions, retries, and lost work.
8. Identical accounting for networking, storage, support, taxes, discounts, and currency.

Never treat the lowest Spot price in a single zone as representative of global production costs. Nor should you compare a 3-year all-upfront commitment rate against monthly on-demand while ignoring the time value of money and underutilization risk.

## 10. Selecting Spot Pools and Diversifying Capacity

Spot capacity can run dry in one pool while remaining available in another. Pools are typically differentiated by zone, instance type/family, and underlying infrastructure attributes. Diversification raises the odds of finding capacity and lowers dependence on a single configuration.

### Selection Strategies

- Declare multiple instance families/sizes compatible with the application.
- Span multiple zones when data and networking requirements allow.
- Use allocation strategies that optimize capacity or balance price and availability per provider features.
- Avoid picking a single pool purely because it had the lowest price at deployment time.
- Maintain on-demand or reserved fallback capacity for critical work.
- Track interruption rates and capacity launch failures per pool.

### A Diverse Fleet Does Not Mean Identical Machines

If machine types differ in CPU architecture, instruction sets, GPUs, local disks, or network bandwidth, images and applications must remain compatible. Use scheduler capability constraints so tasks run only on matching pools.

### Matching Pools to Workloads

Workloads that checkpoint frequently can tolerate higher-interruption pools. Workloads near deadlines or requiring hours of startup should favor steadier pools or fallbacks. Do not optimize hourly price while ignoring completion probability.

## 11. Calculating Effective Spot Cost

A low hourly rate does not automatically yield a low cost per completed outcome. Account for interruptions, reruns, checkpointing, startup, retries, and lost output.

A simple model:

\[
C_{effective} = C_{compute} + C_{restart} + C_{checkpoint} + C_{storage} + C_{network}
\]

Where:

- `C_compute`: cost of actual compute runtime.
- `C_restart`: cost of work that must be rerun after interruptions.
- `C_checkpoint`: CPU, I/O, and storage cost to persist checkpoints.
- `C_storage`: durably stored inputs, outputs, and artifacts.
- `C_network`: data transfer, egress, and synchronization.

You can calculate cost per completed task:

\[
C_{per\ success} = \frac{C_{effective\ total}}{N_{completed}}
\]

### Illustrative Example

Suppose a batch job requires 100 useful compute hours. On-demand has an illustrative unit rate of 1.00 unit/hour. Spot costs 0.30 units/hour, but interruptions force 15% of completed compute to be rerun; checkpointing and storage add 4 units.

- On-demand: roughly 100 units.
- Raw Spot compute: 100 × 0.30 = 30 units.
- Rerunning 15% of work: roughly 15 × 0.30 = 4.5 units.
- Checkpointing/storage: 4 units.
- Illustrative Spot total: 38.5 units.

In this example Spot stays cheaper, yet if interruptions lose 150 hours or trigger steep deadline penalties, the outcome can flip. This is a simplified model; in practice, use actual interruption telemetry, time-of-day pricing, and instance performance.

## 12. Sizing Commitment Levels Appropriately

Commitments should be anchored to predictable baseline usage—not peak demand or uncertain growth targets.

### Separating Baseline from Variable Load

A workload typically exhibits:

- **Baseline:** steady usage needed almost continuously.
- **Seasonal/known peaks:** predictable calendar-driven load spikes.
- **Burst/uncertain demand:** irregular, hard-to-predict spikes.
- **Experimental/dev:** workloads that can stop or change rapidly.

Apply commitments to the stable baseline; use capacity reservations for critical peaks requiring guaranteed provisioning; use on-demand or Spot for variable segments depending on interruption tolerance.

### Historical Analysis

Collect hourly/daily usage across key dimensions: service, region, family, OS, project/account, and environment. Separate commitment-eligible usage from ineligible usage. Account for seasonality, maintenance, migrations, downtime, and planned workload retirements.

### Choosing the Commitment Level

A conservative approach:

1. Identify the minimum steady usage present most of the time.
2. Exclude temporary loads, dev/test, and soon-to-be-retired workloads.
3. Model effective discounts across candidate commitment tiers.
4. Simulate scenarios where usage drops, grows, or shifts provider/region.
5. Start below the average forecast if uncertainty remains high.
6. Monitor utilization and coverage after purchasing.
7. Increase commitments only after real-world data confirms the baseline.

Never buy commitments just to chase a high headline discount percentage. The objective is minimizing risk-adjusted total cost, not maximizing percentage savings on hypothetical usage.

## 13. Distinguishing Commitment Utilization from Coverage

Two metrics are frequently confused:

- **Commitment utilization:** the percentage of the commitment value actually consumed.
- **Discount coverage:** the percentage of eligible usage receiving a discount.

For example, an organization has a commitment of 100 units/hour and eligible usage of 80 units/hour. Utilization is 80%; 20 units of commitment go unused. If the organization's total eligible usage is 160 units/hour, coverage could be 50% because only 80 of 160 units receive a discount.

Track both metrics to avoid high utilization paired with low coverage, or high coverage achieved by over-purchasing commitments that generate waste.

### Additional Metrics

- Effective discount rate relative to on-demand baseline.
- Unused commitment cost.
- Reservation utilization and idle reserved capacity.
- Remaining on-demand spend after applying commitments.
- Spot interruption rate and lost work.
- Cost per completed job/request.
- Monthly/quarterly forecast variance.

## 14. Choosing Capacity Reservations Based on Capacity Shortage Risk

Capacity reservations pay off when the cost of not getting machines on time outweighs the cost of holding capacity. Not every workload needs reservations.

### Quantifying Risk

Evaluate:

- Probability of needing to scale or recover inside a zone/region.
- Revenue/SLO impact if machines cannot be provisioned.
- Wait time for alternative capacity.
- Feasibility of switching machine families/zones.
- Reliance on scarce GPUs, accelerators, or specialized configs.
- Cost of the reservation while capacity sits idle.

### When to Reserve

- Large, time-bounded high-load events.
- DR requiring a specific VM count to launch within RTO.
- Workloads needing scarce GPUs or specialized configurations.
- Production fleets requiring guaranteed minimum capacity per zone.
- Systems needing rapid node replacement after incidents.

### When Not to Over-Reserve

- Workloads that easily shift across zones/families.
- Highly volatile loads lacking sufficient history.
- Resources used only a few hours per month.
- Architectures about to change or migrations nearing completion.
- Workloads where autoscaling/on-demand carries low shortage risk.

### Reservations Do Not Replace Quotas

Capacity reservations and quotas are distinct mechanisms. Quotas limit permitted consumption; reservations hold capacity within a specific scope. A reservation does not automatically raise quotas or guarantee that IAM, networking, images, licenses, and dependencies are ready. Verify quotas and permissions before scale/DR drills.

## 15. Combining Spot, Commitments, and Capacity Reservations

An effective strategy layers multiple capacity types by criticality:

| Workload Tier | Suitable Options | Rationale |
|---|---|---|
| Control planes and core services | On-demand or capacity reservations | Requires resilience and guaranteed availability |
| Steady production baseline | Savings/committed-use discounts | Predictable usage; optimizes unit rate |
| Critical scheduled peaks | Capacity reservations or matching commitments | Needs guaranteed capacity at specific times |
| Checkpointed batch jobs | Spot/Preemptible | Trades interruption tolerance for lower cost |
| Unpredictable bursts | On-demand or flexible pools | Avoids over-committing |
| Dev/test | Short-lived on-demand or Spot | Can be stopped and recreated |
| DR capacity | Reservations or tested capacity plans | Must meet RTO in the target region/zone |

### Tiering Example

A video processing platform has a steady baseline of 20 workers running continuously, plus 0–80 workers during campaigns. It can:

- Purchase commitments for the 20-worker baseline if configuration/usage is stable enough.
- Run checkpointed batch rendering on Spot.
- Use on-demand fallback for deadline-sensitive jobs.
- Hold capacity reservations for a required GPU group in a specific zone if GPU shortage risk is high.
- Cap concurrency so storage and databases are not overwhelmed during scale-out.

Do not commit to the full 100-worker peak if most of the time that level is unneeded.

## 16. Impact of Term, Payment, and Modifiability

Longer commitments typically yield deeper discounts while increasing forecast risk. Upfront payments can lower unit rates or nominal total cost while requiring upfront cash; no-upfront options preserve cash flow without eliminating the commitment obligation.

Before selecting term/payment, check:

- Offered 1-year, 3-year, or other term lengths.
- Upfront/partial/no-upfront options and cash-flow accounting.
- Ability to change family, size, region, or scope.
- Whether commitments can be canceled, resold, or transferred.
- Terms when accounts/projects move across organizations.
- Consequences if workloads shut down or re-architect.
- How discounts apply when multiple commitments qualify simultaneously.

Do not assume "modifiable" means unrestricted changes. Every provider enforces specific rules and limits.

## 17. Calculating Multi-Cloud Total Cost of Ownership (TCO)

Compute unit rate is not the whole cost. Choosing Spot or commitments can shift storage, networking, licensing, monitoring, and operational costs.

### Cost Components

- Compute usage and commitment payments.
- Capacity reservations or idle reserved capacity.
- Persistent disks, snapshots, and object storage.
- Network egress, inter-region transfers, and private connectivity.
- Licenses, OS, and commercial software.
- Logging, metrics, tracing, and backups.
- Retries, checkpointing, lost work, and reprocessing.
- Engineering time maintaining diverse fleets and handling interruptions.
- Migration, data gravity, and multi-cloud operational overhead.

### General Formula

\[
TCO = C_{compute} + C_{commitment} + C_{reservation} + C_{storage} + C_{network} + C_{license} + C_{operations}
\]

When using commitments, do not add both hypothetical on-demand charges and commitment fees for the same usage. Use billing exports or provider calculators aligned with exact billing semantics to avoid double counting.

### Cost per Successful Work Unit

For batch/workers, compare cost per completed job or per million processed records. For APIs, compare cost per successful request at the same SLO. This folds interruptions, retries, and performance into one unified metric.

## 18. Example Comparing Three Strategies

Suppose a workload needs 1,000 vCPU-hours per week, with a steady baseline of 500 vCPU-hours and 500 variable vCPU-hours. Pricing figures below are purely illustrative.

| Strategy | Implementation | Strengths | Risks |
|---|---|---|---|
| 100% on-demand | Pay as you go for all usage | Flexible, simple | High unit rate |
| Commitment for 500 + on-demand for remainder | Commit baseline, pay variable usage on demand | Discounts the stable portion cleanly | Unused commitment waste if baseline shrinks |
| Commitment for 500 + Spot for variable | Baseline discounted, batch runs on Spot | Potentially lower cost | Requires checkpointing, retries, and fallback |
| Commitment + reservation for mandatory peaks | Discount baseline, hold capacity for key peaks | Increases capacity certainty | Idle reservations can incur charges |

Before deciding, simulate at least three scenarios: 30% usage drop, 30% usage growth, and prolonged interruptions/capacity shortages. Compare total cost and SLO attainment probability—not just hourly rates.

## 19. Governance for Commitments and Reservations

Commitments are multi-period financial decisions; reservations are capacity decisions. Both need clear owners, approvals, and review cadences.

### Roles

| Role | Responsibilities |
|---|---|
| Service owner | Forecast workloads, validate baseline and SLOs |
| Platform/cloud team | Analyze instance families, regions, capacity, and technical application |
| FinOps/Finance | Model discounts, commitment utilization, budgets, and cash flow |
| Procurement | Review terms, contracts, and commercial clauses |
| SRE/Operations | Validate interruption tolerance, fallbacks, and DR capacity |
| Architecture review | Assess portability, lock-in, and migration plans |

### Commitment Purchasing Process

1. Collect historical usage representative of seasonality.
2. Normalize usage by region, family, OS/licensing, and account scope.
3. Identify the genuinely stable baseline.
4. Simulate multiple commitment levels and payment options.
5. Quantify unused commitment risk if workloads shrink.
6. Assign budget ownership and discount allocation rules.
7. Approve according to financial thresholds.
8. Track utilization/coverage and adjust at the next review cycle.

### Capacity Reservation Process

1. Identify workload, zone, machine type, and timing of capacity needs.
2. Verify quotas, eligibility, networking, and images.
3. Quantify idle capacity cost against shortage risk.
4. Reserve the narrowest scope that still meets RTO/SLO.
5. Verify actual utilization and scaling/attachment behavior.
6. Drill scale-out or DR inside the reserved zone.
7. Shrink reservations when demand or architecture changes.

## 20. Operational Metrics to Track

### Spot/Preemptible

- Interruption rate by pool/zone/family.
- Launch failure or capacity-unavailable rate.
- Lead time from notice to termination when notices are provided.
- Lost compute time and resume counts.
- Retry success rate and task completion time.
- Fallback rate to on-demand.
- Cost per completed task.

### Commitments

- Commitment utilization.
- Discount coverage.
- Unused commitment cost.
- Effective discount rate vs. baseline.
- Remaining on-demand spend.
- Forecast variance and seasonal usage trends.

### Capacity Reservations

- Reserved capacity utilization.
- Idle reservation cost.
- Capacity launch success within reservation scope.
- Quota headroom.
- Number of times reservations were exercised in scale/DR drills.
- Mismatches between reservation attributes and live workloads.

### Dashboards Must Distinguish Metrics

Do not collapse Spot savings, commitment savings, and reservation utilization into a single number. A clear dashboard separates:

- Equivalent on-demand cost.
- Actual cost after discounts.
- Unused commitment cost.
- Idle reservation cost.
- Spot savings vs. baseline and reprocessing costs.
- Impact on SLOs and completion rates.

## 21. Troubleshooting and Adjustment Decisions

| Symptom | Possible Cause | Action |
|---|---|---|
| Spot frequently fails to launch | Pool/zone lacks capacity or config is too narrow | Expand compatible pools/zones or use fallback |
| Spot interruptions spike | Shifting capacity pressure or concentration in one pool | Diversify, switch allocation strategy, and strengthen checkpoint resilience |
| Spot is cheap per hour but cost/job is high | Heavy rework, retries, or startup overhead | Measure lost work, tighten checkpoints, or move critical jobs to on-demand |
| Commitment utilization is low | Over-committed above baseline or workload shrank | Check modify/sharing rules and reduce future commitments |
| Discount coverage is low | Commitment scope mismatches usage or commitment is too small | Verify eligibility, region/family, and sharing scope |
| Reservations stay idle long-term | Wrong zone/size reserved or peak patterns shifted | Evaluate modifying/canceling if terms allow |
| Launch fails despite reservation | Quotas, attribute mismatch, IAM, images, or dependencies | Inspect all prerequisites beyond the reservation |
| Multi-cloud costs cannot be compared | Differing currencies, taxes, licenses, terms, or amortization | Normalize cost basis and benchmark workloads |
| DR fails to launch | Missing quotas, reservations, or dependencies in target region | Run periodic drills and audit capacity plans |
| Teams dispute discount allocation | Unclear ownership and sharing methodology | Establish transparent showback/chargeback |

### When to Move Workloads Off Spot

Shift part or all of a workload to on-demand/capacity reservations when:

- Interruptions breach deadlines or SLOs.
- Reprocessing costs erase the cost-per-success advantage.
- The workload lacks safe checkpointing or idempotency.
- Capacity pools are unstable during critical windows.
- Remaining work is high-value and close to deadline.

You do not have to abandon Spot completely. You can move only critical tasks or tail work onto steadier capacity.

## 22. Common Mistakes

- **Treating Spot as always-available cheap capacity:** low price does not guarantee launch availability.
- **Running stateful primaries on Spot without failover:** interruptions can cause outages or data loss.
- **Treating savings plans as capacity reservations:** discounts do not hold instances in required zones.
- **Assuming all Reserved Instances hold capacity:** semantics differ across providers and reservation types.
- **Committing to peak usage:** nonexistent usage still wastes commitment spend.
- **Looking only at headline discount percentages:** ignoring terms, upfront cash, eligibility, and unused commitments.
- **Making reservations overly specific:** workload changes in family/zone strand reservations.
- **Ignoring quotas:** reservations do not bypass all provisioning limits.
- **Not diversifying Spot pools:** relying on one zone/family elevates interruption risk.
- **Comparing prices under unequal conditions:** differing regions, OS, licenses, terms, or performance skew conclusions.
- **Ignoring lost work and networking:** low raw compute rates can hide high total costs.
- **Lacking commitment ownership:** nobody tracks utilization or holds budget accountability.

## 23. Checklist for Choosing Interruptible Resources, Commitments, and Capacity

**Spot/Preemptible:**

- [ ] Workload supports checkpointing, retries, and idempotent handling.
- [ ] Durable storage is decoupled from the instance.
- [ ] Interruption handling exists and does not rely solely on notices.
- [ ] Pools/zones/families are suitably diversified.
- [ ] On-demand fallback is configured for critical tasks.
- [ ] Interruptions, lost work, and cost per success are measured.

**Savings/Commitments:**

- [ ] Baseline is derived from representative historical usage.
- [ ] Region/family/service/OS scope and eligibility are verified.
- [ ] Simulated usage drops, growth, and migrations.
- [ ] Accounted for term, upfront/payment terms, and unused commitment risk.
- [ ] Budget owner and discount allocation mechanism are assigned.
- [ ] Utilization, coverage, and effective savings are tracked.

**Capacity Reservations:**

- [ ] Specific capacity requirement is tied to SLO/RTO.
- [ ] Zone/region, machine type, size, and hardware attributes match the workload.
- [ ] Quotas, IAM, images, networking, and dependencies are ready.
- [ ] Idle cost and reservation modification rules are evaluated.
- [ ] Scale-out/DR drills have been executed within reservation scope.
- [ ] Utilization is monitored and reviewed as architecture evolves.

**Multi-Cloud Comparison:**

- [ ] Identical workload benchmarks and equivalent performance.
- [ ] Identical region/latency and data residency assumptions.
- [ ] Identical OS/licensing, term, payment, and cost basis.
- [ ] Accounted for networking, storage, support, retries, and operations.
- [ ] Separated discounts from capacity guarantees.
- [ ] Documented placement and fallback decisions.

## Conclusion

Spot/Preemptible fits workloads that can tolerate interruptions, checkpoint, and retry; savings plans or committed-use discounts suit steady baseline usage needing lower unit rates; capacity reservations fit when organizations must guarantee provisioning within a specific scope. All three options can be combined, yet they do not replace one another. When comparing AWS, Azure, and Google Cloud, normalize configurations, regions, terms, payments, eligibility, and capacity assurances—then factor in interruptions, unused commitments, idle reservations, networking, and operations. A sound strategy typically commits the predictable baseline, reserves capacity for workloads requiring certainty, and uses Spot for resilient work, while tracking cost per successful work unit to validate real savings.
