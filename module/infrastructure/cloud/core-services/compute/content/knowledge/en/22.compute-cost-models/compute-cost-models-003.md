# Usage Commitments and Provider-Specific Discount Models

Cloud providers typically reduce compute unit prices when customers commit to using resources or spending a set amount over a fixed term. These programs can significantly cut costs for eligible VMs, containers, serverless, or GPUs, but in exchange, the organization must maintain the committed usage or spend level. If you over-purchase, unused commitment may still be billed; if you under-purchase, usage exceeding the commitment continues at on-demand rates.

In the **CLOUD_CORE_SERVICES_COMPUTE** module, commitment purchasing decisions should be based on actual workloads: continuously running VMs, baseline node pools, fluctuating workers, request-based functions, campaign-based GPUs, and capacity held for availability. This lesson explains common commitment models, distinguishes discount entitlements from capacity guarantees, shows how to estimate commitment levels, track utilization/coverage, and select programs across AWS, Microsoft Azure, and Google Cloud.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish pay-as-you-go, reservation, reserved instance, savings plan, and committed use discount.
- Explain the difference between resource-based and spend-based commitments.
- Distinguish billing discounts from capacity reservations.
- Read commitment attributes: term, scope, resource type, region, spend level, and payment option.
- Calculate utilization, coverage, unused commitment, and effective savings.
- Choose a stable baseline to commit without locking in full peaks or variable workloads.
- Compare AWS, Azure, and Google Cloud models at a principle level.
- Build a workflow for purchasing, allocating, tracking, adjusting, and renewing commitments.
- Identify risks when changing instance families, regions, architectures, licenses, or usage levels.

## 1. Compute Pricing Models

Cloud compute can be billed by runtime, provisioned resources, request count, execution duration, or actual usage. Common options include:

| Model | Basic Billing Mechanism | Best Suited For |
|---|---|---|
| On-demand / pay-as-you-go | Pay for actual usage, no long-term commitment | New, fluctuating, short-term, or hard-to-forecast workloads |
| Reserved capacity / reservation | Reserve a capacity type or configuration under provider terms | Workloads requiring guaranteed resource availability in a specific zone/machine type |
| Reserved Instance / resource commitment | Commit to using an eligible configuration or resource group for a term | Stable workloads with infrequently changing configurations |
| Savings plan / spend commitment | Commit to an hourly or periodic compute spend level for lower unit prices | Workloads with stable budgets that may change machine types/services |
| Committed use discount (CUD) | Commit to resource levels or spend by product/scope | Workloads with a predictable baseline |
| Spot / interruptible | Use spare capacity at lower prices, subject to reclamation | Batch, CI, background processing with retries/checkpointing |
| Serverless per-request | Pay per request, execution duration, and configured resources | Uneven traffic, low baseline load, or event-driven workloads |

Specific names and conditions vary across providers. Do not assume "reservation", "commitment", or "savings plan" shares the same scope or benefits across clouds.

### 1.1. Why Do Providers Offer Discounts for Commitments?

Commitments help providers forecast demand, plan capacity, and smooth usage volatility. In return, customers accept a payment obligation over a term, typically one to several years depending on the program.

Discount levels depend on:

- Commitment term.
- Upfront payment level or payment schedule.
- Eligible resource types and products.
- Scope of application: project, subscription, account, region, or instance family.
- Flexibility when changing configurations.
- Specific program and terms at the time of purchase.

List prices, discount rates, and exchange/cancellation terms can change. Always use current pricing pages and terms in the organization's billing account when drafting a purchase proposal.

### 1.2. Discounts and Capacity Reservations Are Two Separate Benefits

A commitment can discount eligible usage without guaranteeing that a specific VM/GPU will always be available in a zone. Conversely, a capacity reservation can preserve the ability to launch resources without necessarily generating a discount on its own.

| Question | Billing discount | Capacity reservation |
|---|---|---|
| Goal | Lower unit price for eligible usage | Guarantee resource availability within reservation scope |
| Payment obligation? | Usually yes with commitment plans | Depends on reservation type and service |
| Guarantees instance launch? | Not by default | Potentially, per reservation terms/type |
| Applies across configurations? | Depends on program flexibility | Usually tied more tightly to region/zone/family/capacity |
| Example | Savings Plan or CUD | Zonal capacity reservation or reserved capacity |

If a workload needs both low cost and guaranteed capacity, you may need to combine both mechanisms. Verify how benefits apply concurrently and avoid double-counting the same usage in savings models.

## 2. Resource-Based vs. Spend-Based Commitments

Two common commitment categories differ in the unit the customer promises to consume.

### 2.1. Resource-Based Commitment

A resource-based commitment commits to a specific quantity of resources, such as vCPUs, RAM, GPUs, or an instance configuration within a given region/product group.

Common characteristics:

- Fits workloads with stable configurations and deployment regions.
- May offer steeper discounts in exchange for lower flexibility.
- Easy to quantify covered resources.
- Carries unused commitment risk if workloads shrink or shift to ineligible configurations.
- Must check rules for changing size, family, OS, tenancy, region, and sharing scope.

Example: an organization commits to 32 vCPUs and 128 GiB RAM of Compute Engine in a region for a set term. If actual usage moves to another region or an out-of-scope resource type, the commitment may go underutilized.

### 2.2. Spend-Based Commitment

A spend-based commitment commits to a spending level for eligible usage, usually measured per hour or billing period. The discount benefit applies to eligible usage within the program's scope.

Common characteristics:

- More flexible when instance families, sizes, or eligible services change.
- Does not necessarily reserve a specific machine type.
- Can apply across multiple projects/subscriptions/regions depending on the program.
- Commitment not absorbed by eligible usage can still result in unutilized spend.
- Requires understanding discount application order and benefit allocation rules.

Example: an organization commits to 20 USD per hour for an eligible compute group. If eligible usage falls below this level, the remaining commitment does not automatically convert into generic credit usable for any service.

### 2.3. Comparing the Two Commitment Approaches

| Criterion | Resource-Based | Spend-Based |
|---|---|---|
| Commitment unit | vCPU, RAM, GPU, instance/configuration, or resource unit | USD/hour or periodic spend level |
| Flexibility | Generally lower | Generally higher within eligible usage scope |
| Primary risk | Workload changes config/region leaving committed resources unused | Eligible spend drops leaving commitment unabsorbed |
| Best suited for | Stable compute baseline, clear configuration | Workloads that may switch compute types with relatively stable spend |
| What to track | Usage of each resource type and region | Hourly/periodic benefit utilization and eligible scope |

## 3. Attributes to Read Before Purchasing

Do not compare two programs solely by discount percentage. Standardize the following attributes:

### 3.1. Term

Terms may be one year, three years, or another structure depending on the program. Longer terms generally offer lower unit rates but increase risk when workloads evolve.

Check:

- Start date and expiration date.
- Whether auto-renewal is enabled and its renewal terms.
- Whether the commitment can be modified, exchanged, canceled, or refunded.
- Whether terms differ between reservations and savings plans.
- What happens when an account/subscription/project is moved or closed.

Do not buy a long term solely for a high discount percentage if the compute, region, or license roadmap is unstable.

### 3.2. Scope

Scope defines which usage receives the benefit. It can be:

- A resource or instance family.
- A region or set of regions.
- A project, subscription, account, or billing account.
- A group of eligible services.
- Usage across an organization or linked account group.

A broad scope increases benefit absorption when workloads shift across projects/teams, though it can make cost allocation harder. A narrow scope simplifies ownership tracking but raises underutilization risk when resources change.

### 3.3. Commitment Unit and Amount

Units may be:

- vCPUs/RAM/GPUs per hour.
- Number of instances in a family/region.
- USD/hour rate.
- Monthly or entitlement-period spend level.

Distinguish commitment amount from On-Demand spend. For instance, a 10 USD/hour commitment does not necessarily mean 10 USD/hour of list-price usage; it may represent the committed benefit or spend value as defined by that specific program.

### 3.4. Payment Option

Some programs allow all-upfront, partial-upfront, or periodic payments. Compare the total obligation across the entire term, not just first-month cash flow.

Consider:

- Total nominal cost over the term.
- Cash flow and CAPEX/OPEX budgets.
- Exchange rate, tax, and billing currency impacts.
- Billing when usage exceeds the commitment.
- Billing when usage falls below the commitment.
- Whether license/OS/network/storage costs are covered by the benefit.

## 4. Calculating Savings and Commitment Utilization

The goal is to measure actual net savings after accounting for unused commitment and out-of-scope usage. Do not treat advertised discount percentages as guaranteed savings across the entire bill.

### 4.1. Core Metrics

**Commitment utilization** measures how much of the purchased benefit is absorbed by eligible usage:

\[
Utilization = \frac{Used\ commitment\ benefit}{Purchased\ commitment\ benefit} \times 100\%
\]

**Coverage** measures the share of eligible usage covered by the benefit:

\[
Coverage = \frac{Eligible\ usage\ covered}{Total\ eligible\ usage} \times 100\%
\]

**Effective savings** compares actual cost with the commitment against the hypothetical On-Demand cost for the same usage:

\[
Effective\ savings = \frac{OnDemand\ baseline - Actual\ cost}{OnDemand\ baseline} \times 100\%
\]

Calculation definitions must align with the invoice: credits, taxes, support, licenses, networking, and storage may fall outside the same scope.

### 4.2. Resource-Based Commitment Example

Suppose a compute group has steady On-Demand demand of 100 resource units per hour. The On-Demand rate is 0.10 USD/unit/hour. A commitment lowers the rate to 0.07 USD/unit/hour, and the organization commits to 80 units per hour.

| Scenario | Actual Usage | Cost if On-Demand | Cost with Commitment | Observation |
|---|---:|---:|---:|---|
| Exact 80 used | 80 | 8.00 USD | 5.60 USD | Full commitment utilized; 30% savings |
| 100 used | 100 | 10.00 USD | 5.60 + 2.00 = 7.60 USD | 80 units discounted, 20 units billed On-Demand |
| Only 60 used | 60 | 6.00 USD | 5.60 USD | 20 units unused; effective savings only ~6.7% |
| Only 20 used | 20 | 2.00 USD | 5.60 USD | Commitment costs ~3.60 USD more than On-Demand |

This is an illustrative arithmetic model for a resource-based commitment carrying a full payment obligation for the committed quantity. Actual application and pricing vary by provider.

### 4.3. Spend-Based Commitment Example

Suppose a program requires committing to 10 USD/hour for eligible usage. In one hour, eligible usage only reaches a benefit equivalent of 7 USD; the remaining commitment goes unused. In another hour, eligible usage equals 14 USD; the benefit applies up to the commitment cap, and the excess is billed under program rules.

Items to verify in billing reports:

- Is the commitment measured in On-Demand equivalent or post-discount spend?
- Do unused benefits carry forward?
- Is the benefit applied hourly, monthly, or per entitlement window?
- Which usage counts as eligible?
- In what order is the benefit distributed across projects/teams?

Do not assume unused commitment from one hour offsets overage in another hour. Some programs meter hourly while others use different windows; follow the exact product semantics.

### 4.4. Discount Rate Is Not Effective Savings

If a program advertises 40% off eligible usage, yet only 50% of the baseline is covered by the commitment and 80% of the commitment is utilized, the effective savings across all eligible spend are far lower than 40%.

When presenting a business case, always include:

- On-Demand baseline.
- Eligible usage.
- Commitment amount.
- Expected utilization and coverage.
- Overage usage beyond the commitment.
- Unused commitment.
- Total cost and effective savings.

## 5. Selecting a Baseline to Commit

Commitments should be sized to the stable portion of the workload, not peaks or an anomalous month.

### 5.1. Analyzing Usage History

Collect data over a long enough window to capture weekdays, weekends, peak seasons, releases, batch windows, and traffic spikes. Analyze:

- Hourly/daily/monthly compute usage.
- Instance family, size, region, and OS/license.
- CPU/memory utilization and idle time.
- Minimum capacity for HA and failure scenarios.
- Autoscaling baseline, peaks, and troughs.
- Existing commitments and expiration dates.
- Services eligible under the program.

### 5.2. Use a Stable Baseline Instead of Peak

Example workload hourly compute usage:

```text
Overnight baseline:     40 units
Workday:                65 units
Peak hours:            100 units
Seasonal events:       140 units
```

If you commit to 100 units because it is a common peak, overnight usage can create unused commitment. A more conservative strategy is committing the stable baseline while handling bursts with On-Demand, autoscaling, or Spot if the workload tolerates interruptions.

### 5.3. Classifying Workloads

| Workload Type | Stability | Approach |
|---|---|---|
| Continuously running production databases | High | May suit appropriate resource-based or reservation plans |
| Baseline APIs always needing minimum replicas | Medium to high | Commit baseline; handle scale-out flexibly |
| Queue-driven workers | Fluctuating | Commit small floor; burst on demand |
| Campaign-based GPU training | Low to medium | Commit only when history and roadmap are sufficiently stable |
| Ephemeral CI/test | Low | Prefer pay-as-you-go or Spot/interruptible |
| Request-based serverless | Depends on traffic and program | Verify eligibility, baseline, and spend window |
| Disaster recovery standby | Potentially stable but rarely active | Separate capacity-holding cost from usage-based benefit |

### 5.4. Eliminate Waste Before Buying Discounts

Discounts lower unit prices but do not fix overprovisioning. Before committing:

- Rightsize VMs/Pods and remove unused instances.
- Shut down dev/test environments outside working hours where appropriate.
- Tune autoscaling min/max bounds and schedules.
- Clean up orphaned disks, snapshots, images, and resources.
- Optimize CPU/RAM, storage IOPS, and networking.
- Measure cost per request/job rather than total usage alone.

Only commit to the baseline after reducing waste. If you buy commitments first and rightsize afterward, utilization can drop and discount gains evaporate.

## 6. Cloud Provider Programs

Program names, scopes, discount rates, terms, and exchange rights vary by product, region, account type, and purchase date. The examples below explain how models are categorized; verify current documentation and your billing console before purchasing.

### 6.1. AWS

Common compute programs include:

- **Compute Savings Plans:** commit to an hourly compute spend level. Per AWS documentation, this offers broad flexibility across EC2 and can apply to eligible Fargate/Lambda usage, with wider scope across instance families/sizes/regions than family/region-locked options.
- **EC2 Instance Savings Plans:** commit to hourly spend within a single instance family and region; flexible across sizes within program scope, though narrower than Compute Savings Plans.
- **EC2 Reserved Instances:** pricing benefits based on RI attributes and term. Standard/Convertible and Regional/Zonal have different modification and capacity rules.
- **On-Demand Capacity Reservations:** mechanism to reserve EC2 capacity in an Availability Zone; this is a capacity entitlement, distinct from a Savings Plans discount.

Key points to remember:

- Savings Plans are generally financial commitments and do not inherently guarantee capacity.
- Compute Savings Plans offer broader flexibility but do not necessarily match every RI discount rate.
- EC2 RIs and Capacity Reservations interact differently depending on RI type and configuration.
- Savings Plans do not apply to Spot usage per AWS documentation.
- Check term, payment option, and eligible services by plan type.

### 6.2. Microsoft Azure

Common options:

- **Azure Reservations:** commit to a resource/configuration type for a term to receive a billing discount. For VMs, attributes like region and instance family/size can govern application scope.
- **Azure Savings Plan for Compute:** commit to an hourly compute spend level; the benefit applies to eligible compute usage within the plan's scope.
- **Pay-as-you-go:** suited for fluctuating usage or workloads not yet stable enough for commitment.

Key points to remember:

- A reservation is a billing benefit and does not alter the runtime state of resources.
- VM reservations do not automatically cover all software, network, and storage charges; inspect covered charge scopes.
- Savings Plans offer greater flexibility when workloads shift across eligible compute types.
- Exchange/refund/cancellation terms differ between reservations and savings plans; do not assume every commitment can be canceled.
- Scope affects how benefits are shared across subscriptions/billing scopes.

### 6.3. Google Cloud

Google Cloud offers Committed Use Discounts (CUDs):

- **Resource-based CUDs:** commit to Compute Engine resource levels such as vCPUs, memory, GPUs, or certain other resources, typically tied to a region and project/scope per program rules.
- **Spend-based CUDs:** commit to a spend level for an eligible product/service; measured in USD/hour or an entitlement model depending on the program.
- **On-demand usage:** usage not covered by benefits continues at standard applicable rates.

Key points to remember:

- Resource-based CUDs fit predictable resource demand.
- Spend-based CUDs provide flexibility across eligible spend yet remain bounded by product, billing account, and scope.
- Some CUDs are region-specific; others have broader scope depending on the service.
- Commitments typically carry payment obligations over the term; do not buy before understanding exactly how benefits are calculated and allocated.

### 6.4. Directional Comparison Table

| Provider | Resource-Based Commitment | Spend-Based Commitment | Key Considerations |
|---|---|---|---|
| AWS | EC2 Reserved Instances; EC2 Instance Savings Plans tied to family/region | Compute Savings Plans by USD/hour level | Distinguish discounts from On-Demand Capacity Reservations; check EC2/Fargate/Lambda eligibility |
| Azure | Reservations for eligible resources/configurations | Savings Plan for Compute by hourly spend | Covered charges, scope, exchange/refund policies, and eligible services |
| Google Cloud | Resource-based CUDs for Compute Engine | Spend-based CUDs by product/eligible usage | Region/project/billing scope, resource categories, and term |

This table only describes model categories. Do not substitute it for specific product terms, as eligibility and benefits vary by series, OS, region, account, and purchase date.

## 7. Commitments Do Not Replace Capacity Planning

Discounts do not mean resources will be available in a zone or region when needed. Workloads requiring HA, specific GPUs, or DR capacity must have a separate capacity plan.

### 7.1. Capacity Reservations

Capacity reservations aim to preserve the ability to launch a resource type within a defined scope. Verify:

- Zone/region and instance family/size.
- Reserved capacity quantity.
- Start/end times and reservation state.
- Which discount programs can combine with it.
- Cost when reserved capacity goes unused.

### 7.2. Commitment Discounts

Discount commitments lower prices for eligible usage but may not guarantee:

- Enough GPUs or instance types in a capacity-constrained zone.
- Sufficient IPs/subnets, network interfaces, or quotas.
- Matching capacity in databases, storage, or NAT.
- Workloads meeting RTO/RPO when a zone/region fails.

In production planning, separate cost goals from availability goals. One system might combine commitment discounts for the baseline, capacity reservations for critical workloads, and On-Demand headroom for bursts/failover.

## 8. Strategies for Combining Pricing Models

You do not need to put every workload into the same program. Layer them by stability and operational requirements.

### 8.1. Baseline + Burst

A common pattern:

- Commitments cover the stable baseline.
- On-Demand handles load above baseline.
- Spot/interruptible runs retryable or checkpointed jobs.
- Serverless handles uneven events/traffic if the cost profile fits.
- Capacity reservations protect critical resources when availability demands it.

### 8.2. Splitting by Environment

| Environment | Approach |
|---|---|
| Production core | Commit proven baseline; separate capacity plan for HA |
| Staging | Start/stop schedules, rightsizing, commit only if usage is stable and eligible |
| Development | Pay-as-you-go, shared pools, or off-hours shutdown |
| Batch/ETL | Spot/interruptible or On-Demand by deadline; commit only steady baseline |
| DR standby | Weigh capacity-holding cost, storage replication, and required readiness |

### 8.3. Avoiding Overcommitment

Overcommitment occurs when total committed obligations exceed stable eligible usage. To reduce this risk:

- Leave room for volatility and seasonality.
- Exclude Spot usage or ineligible resources from the committed baseline.
- Exclude workloads scheduled for decommissioning or platform migration.
- Account for existing commitments before adding new ones.
- Use conservative forecasts and downside stress scenarios.
- Purchase in tranches, evaluate utilization, then scale up.

## 9. Commitment Purchasing Workflow

### Step 1: Clean the Baseline

Gather bills and usage by service, region, family, OS, environment, account, and team. Rightsize before choosing commitment levels.

### Step 2: Identify Eligible Usage

Read program rules to identify which usage receives benefits. Strip ineligible items like storage, networking, licenses, or Spot if excluded by the program.

### Step 3: Separate Stable from Variable

Classify usage into:

- Continuous baseline.
- Seasonal/predictable bursts.
- Unpredictable bursts.
- Ephemeral/test.
- DR/failover capacity.

### Step 4: Choose Commitment Type

Choose resource-based when configurations are stable; choose spend-based when eligible spend is more stable than specific configurations. Compare flexibility, scope, term, and payment obligations.

### Step 5: Simulate Scenarios

Model costs when usage is below, equal to, and above baseline, and under region/family shifts. Inspect unused commitment and On-Demand overage.

### Step 6: Approval

The business case should include:

- Total commitment and term.
- On-Demand baseline.
- Expected utilization/coverage.
- Effective savings.
- Underutilization and workload-change risks.
- Owner and cost center.
- Review, renewal, and exit conditions.

### Step 7: Purchase in Tranches

Buy a moderate portion of the verified baseline, monitor for 1–3 billing cycles or a representative period, then increase if utilization remains steady. The exact cycle depends on term and workload churn rate.

## 10. Tracking Utilization, Coverage, and Cost Allocation

Once purchased, commitments must be managed like financial assets with clear owners.

### 10.1. Commitment Dashboard

Track:

- Purchased commitment and remaining term.
- Hourly/daily/monthly utilization.
- Coverage of eligible usage.
- Unused commitment and usage exceeding the benefit.
- Cost avoidance compared to the On-Demand baseline.
- Benefit allocation across projects/subscriptions/teams.
- Workload shifts making commitments misaligned.
- Upcoming expirations and renewal recommendations.

### 10.2. Showback and Chargeback

- **Showback:** inform teams how commitment benefits and costs are allocated.
- **Chargeback:** bill commitment costs to cost centers per organizational rules.

If a billing account shares benefits across multiple projects, establish transparent allocation rules. Avoid scenarios where one team buys a commitment while another consumes the benefit without clear ownership or cost-sharing rules.

### 10.3. Alerts

Set alerts when:

- Utilization drops below threshold for consecutive periods.
- Coverage drops because workloads changed family/region or service.
- Eligible usage persistently exceeds commitments.
- New resources appear uncovered.
- Commitments approach expiration or auto-renewal.
- A project/team stops consuming its allocated benefit.

Thresholds should match baselines and financial targets; no single utilization ratio fits every program.

## 11. Example: Selecting Commitments for an API Platform

An API platform has three compute groups:

- Production API always requires a minimum of 40 vCPUs.
- Autoscaling can add 20–60 vCPUs during peak hours.
- Batch workers require 0–30 vCPUs and can tolerate delays.

### 11.1. Classifying Usage

| Group | Baseline | Peak | Stability | Option to Consider |
|---|---:|---:|---|---|
| API core | 40 vCPU | 60 vCPU | High | Appropriate resource commitment or spend plan |
| API burst | 0 | 20 vCPU | Variable | On-Demand or autoscaling |
| Batch worker | 0 | 30 vCPU | Intermittent | Spot/interruptible or On-Demand by deadline |

### 11.2. Initial Commitment Level

The organization should not commit to 90 vCPUs simply because that equals peak plus workers. A prudent option is analyzing the 40-vCPU baseline over several months, checking the roadmap and region stability, then committing part or all of the eligible baseline while keeping bursts flexible.

### 11.3. Post-Purchase Monitoring

After purchase, if API core drops from 40 to 25 vCPUs due to code optimization or moving to a container platform, utilization may fall. Evaluate changing scope/exchanging if the program permits, or routing other eligible usage into scope if policy allows. If no adjustment is possible, factor the unused commitment into forecasts until the term expires.

## 12. Factors That Reduce Commitment Effectiveness

### 12.1. Architectural Changes

Migrating VMs to serverless, switching instance families, changing regions, or adopting managed services can render usage ineligible. Before migrating, map existing commitments and expiration dates.

### 12.2. Post-Purchase Rightsizing

Rightsizing lowers usage and can leave surplus commitment. That does not mean avoiding optimization; evaluate total cost after rightsizing instead of keeping wasteful resources just to consume a discount.

### 12.3. Seasonality and Business Downturns

Committing based on peak season leaves commitments unused when demand falls. Rely on multi-cycle baselines, forecasts, and downside scenarios.

### 12.4. Scope and Account Changes

Moving subscriptions/projects/accounts or restructuring the organization can alter how benefits apply. Verify billing scopes, sharing settings, and administrative permissions.

### 12.5. Currency, Taxes, and Billing Differences

List prices, currency fluctuations, taxes, support plans, licenses, and credit allocation can cause actual bills to diverge from models. Reconcile against actual invoice data.

## 13. Common Mistakes

| Mistake | Consequence | Remedy |
|---|---|---|
| Choosing solely by highest discount rate | Can lock in unstable usage | Compare effective savings and unused risk |
| Committing to peak | Surplus commitment during off-peak hours | Commit baseline; handle bursts flexibly |
| Confusing discounts with capacity reservations | Discount active, but unable to launch needed resources | Set up separate capacity reservations if needed |
| Skipping rightsizing before purchase | Discounting wasteful capacity | Remove waste before calculating baseline |
| Assuming all compute services are eligible | Benefit fails to apply to some usage | Verify product/region/family/OS eligibility |
| Ignoring scope | Benefit sits in a different account/project from usage | Define clear scope and sharing rules |
| Not tracking utilization | Unused commitments persist until term end | Dashboards, alerts, and owners |
| Including Spot in committed baseline | Usage may be ineligible or unstable | Exclude Spot from commitment baselines |
| Buying long terms with unclear roadmap | Hard to adapt during migrations/rightsizing | Match term to certainty and flexibility needs |
| Ignoring overage beyond commitments | Total cost exceeds forecast | Simulate baseline, burst, and peak |
| Auto-renewing without review | Locks old commitment levels despite changed demand | Review prior to renewal and re-approve |

## 14. Pre-Purchase and Operational Checklist

**Before Purchasing**

- [ ] Rightsized and removed unused resources.
- [ ] Analyzed usage by hour/region/family/service over a representative period.
- [ ] Identified eligible usage and excluded items.
- [ ] Separated baseline, burst, seasonal, batch, and DR capacity.
- [ ] Compared resource-based vs. spend-based commitments.
- [ ] Reviewed term, scope, payment, exchange/cancel/refund, and renewal rules.
- [ ] Calculated unused commitment, overage, and effective savings.
- [ ] Assigned owner, cost center, and budget approval.

**In Operations**

- [ ] Track utilization and coverage periodically.
- [ ] Track unused commitment and usage exceeding benefits.
- [ ] Allocate benefits transparently across teams/projects.
- [ ] Review whenever changing instance family, region, architecture, or licenses.
- [ ] Alert before commitments expire.
- [ ] Re-evaluate forecasts prior to renewal.
- [ ] Separate billing discounts from capacity reservations and HA requirements.

## 15. Conclusion

Commitments lower compute unit prices in exchange for an obligation to consume resources or spend over a term. Resource-based commitments fit stable configurations; spend-based commitments offer flexibility when eligible spend is steady even as compute types evolve. Both carry underutilization risk if the baseline shrinks or usage becomes ineligible.

Rightsize first, analyze usage history, establish the baseline, verify scope/term/eligibility, and simulate low-base-high scenarios before buying. Monitor utilization, coverage, unused benefits, and effective savings throughout the term. Most importantly, separate discount entitlements from capacity guarantees: workloads needing HA or scarce resources still require dedicated capacity reservations and quota planning.

## Provider Reference Documentation

- [AWS – What are Savings Plans?](https://docs.aws.amazon.com/savingsplans/latest/userguide/what-is-savings-plans.html)
- [AWS – Compute Savings Plans and Reserved Instances](https://docs.aws.amazon.com/savingsplans/latest/userguide/sp-ris.html)
- [Microsoft Azure – Decide between a savings plan and a reservation](https://learn.microsoft.com/en-us/azure/cost-management-billing/savings-plan/decide-between-savings-plan-reservation)
- [Microsoft Azure – What are Azure Reservations?](https://learn.microsoft.com/en-us/azure/cost-management-billing/reservations/save-compute-costs-reservations)
- [Google Cloud – Committed use discounts](https://docs.cloud.google.com/docs/cuds)

## Key Glossary

| Term | Meaning |
|---|---|
| Pay-as-you-go | Paying for actual usage with no long-term commitment. |
| Commitment | Obligation to use resources or spend a set amount over a chosen term. |
| Resource-based commitment | Commitment to a specific quantity of resources or configuration. |
| Spend-based commitment | Commitment to a spending level for eligible usage. |
| Reserved Instance | Discounted pricing program tied to resource attributes per provider rules. |
| Savings Plan | Discount program in exchange for committed compute spend. |
| Committed Use Discount (CUD) | Discount entitlement for committing resources or spend on Google Cloud. |
| Capacity reservation | Mechanism preserving the ability to launch resources within a defined scope. |
| Utilization | Percentage of commitment benefit consumed by eligible usage. |
| Coverage | Percentage of eligible usage covered by commitment benefits. |
| Unused commitment | Portion of commitment not absorbed by eligible usage. |
| Effective savings | Actual savings relative to the equivalent On-Demand baseline. |
| Scope | Resource/project/subscription/account boundary where benefits apply. |
| Term | Commitment duration. |
| Eligible usage | Usage meeting the discount program's qualification rules. |
