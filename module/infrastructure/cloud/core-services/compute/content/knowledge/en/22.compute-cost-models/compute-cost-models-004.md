# Distinguishing Pricing Discounts from Capacity Reservations

When purchasing cloud compute capacity, two questions are often confused: "How do I pay less for a VM?" and "How do I guarantee enough VMs can launch when needed?" A long-term usage commitment or savings plan can lower unit prices, but it does not necessarily hold CPU/RAM ready in a zone. Conversely, a capacity reservation can reserve resource slots for a workload, yet it does not automatically provide a discount.

A **pricing discount** reduces the amount paid for eligible usage. A **capacity reservation/commitment** reserves a quantity of resources or launch capability within a specific scope. Some provider products combine both features, while many address only one goal.

In **CLOUD_CORE_SERVICES_COMPUTE**, it is essential to clearly separate these two benefits when choosing among On-Demand, Reserved Instances, Savings Plans, Committed Use Discounts, Spot/Preemptible, and Capacity Reservations. Sound decisions must simultaneously evaluate expected usage, workload stability, resource placement, interruption tolerance, commitment term, and the risk of paying for unused capacity.

## 1. Two Distinct Goals: Lowering Price and Securing Capacity

### 1.1. What Is a Pricing Discount?

A pricing discount lowers the unit price or cost of usage that meets specified conditions. Conditions may include:

- Committing to spend or usage over a period of time.
- Using the designated service family, instance type, operating system, or region.
- Maintaining an hourly or monthly compute consumption level.
- Paying part or all of the committed value upfront.
- Using an eligible resource type under contract.

Discounts may apply to actual usage incurred. If the workload does not run, savings may not materialize; with some commitments, the buyer must still pay the committed amount even when usage is lower.

### 1.2. What Is a Capacity Reservation?

A capacity reservation reserves the ability to consume a given quantity of compute resources within a specified scope. Scope can be tied to:

- Region and availability zone.
- Instance family/type or VM size.
- CPU architecture, accelerators, or hardware attributes.
- Platform, tenancy, or operating system.
- Number of instances, vCPUs, GPUs, or capacity units.
- Reservation active window and usage terms.

Capacity reservations solve the risk of capacity shortages when creating or starting machines. They do not make applications faster on their own, do not guarantee capacity for database or network dependencies, and do not necessarily reduce unit prices.

### 1.3. Quick Comparison Table

| Criterion | Pricing Discount | Capacity Reservation |
|---|---|---|
| Goal | Reduce cost for eligible usage | Reserve launchable resource slots |
| Core question | "What is the compute unit price?" | "When needed, are enough machines available in the right place?" |
| Scope | Can be flexible across family, region, or spend | Usually more specific to zone, machine type, and count |
| Value when unused | May forfeit savings or still owe commitment | Reservation may still be billed even if unused |
| Availability impact | Does not inherently guarantee launchability | Reduces capacity shortage risk within reservation scope |
| Examples | Savings Plan, Committed Use Discount, many Reserved Instances | On-Demand Capacity Reservation, Azure Capacity Reservation, Compute Engine Reservation |

A single contract or product may offer both features. Always read the exact reservation type and provider terms rather than inferring from the name.

## 2. Common Compute Purchasing Model Groups

Common models can be grouped by primary objective:

| Model | Billing / Operation | Primary Priority |
|---|---|---|
| On-Demand/pay-as-you-go | Pay for actual usage, no long-term commitment | Flexibility |
| Reserved Instances/VM reservations | Commit under terms and duration for discounted pricing; some types add capacity benefits | Discounts, sometimes paired with capacity |
| Savings Plans | Commit to hourly/periodic compute spend for discounted rates on eligible usage | Flexible discounts |
| Committed Use Discounts (CUD) | Commit to usage or spend over a term for discounts | Discounts |
| Spot/Preemptible | Use spare capacity at lower prices, subject to reclamation | Cost reduction for interruptible workloads |
| Capacity Reservation | Pre-allocate specific capacity within service scope | Guaranteed launchability |

Do not treat Spot as a form of capacity guarantee. Spot uses spare capacity and can be reclaimed; lower prices come with interruption risk and no guarantee that capacity will remain available.

## 3. On-Demand: Flexible and Easy to Start

On-Demand lets you launch VMs and pay per usage without signing a one- or three-year commitment. It is usually the right choice when:

- Workloads are new without long-term usage history.
- Load fluctuates or is hard to predict.
- Dev/test environments only run by the hour.
- Short-term capacity is needed for campaigns or events.
- Multiple instance types must be tested before standardizing.
- Workloads require frequent changes to region, family, or size.

Advantages:

- No long-term forecasting required upfront.
- Can scale up/down or delete resources as needed.
- No commitment charges when not in use.
- Serves well as a baseline to measure usage and compare purchasing options.

Limitations:

- Unit prices are generally higher than committed options.
- On-Demand does not mean capacity is always available in every zone or instance type.
- During capacity shortages, VM creation can still fail or require switching zones/types.

On-Demand is a flexible purchasing model, not a reservation. If a critical workload must be guaranteed enough machines at a specific time, evaluate capacity separately.

## 4. Reserved Instances and Pricing Commitments

The name "Reserved Instance" may refer to a pricing discount product, a product with capacity benefits, or a reservation mechanism depending on the cloud provider. Distinguish by provider and specific type.

### 4.1. Term-Based Pricing Commitments

Some programs let you commit to a compute type or spend level for 1 year, 3 years, or another term. In exchange, matching usage is billed at a lower rate.

Binding conditions may include:

- Instance family or machine type.
- Region or zone.
- Platform/OS and tenancy.
- Size or vCPU/RAM units.
- Upfront amount and payment schedule.
- Ability to modify, exchange, or cancel the commitment.

More specific commitments may yield steeper discounts, yet mismatch risk increases if workloads change machine type, region, or architecture.

### 4.2. AWS Reserved Instances

In AWS EC2, Reserved Instances are primarily a pricing mechanism for eligible usage. Distinguish between:

- **Regional Reserved Instance:** generally provides discounts for matching usage across the region per applicable terms; it is not a zonal capacity reservation.
- **Zonal Reserved Instance:** tied to a specific Availability Zone and can provide a capacity reservation for matching instance attributes in addition to pricing benefits.

AWS also offers **On-Demand Capacity Reservations**, a separate product for reserving EC2 capacity in an Availability Zone. A Capacity Reservation is billed at On-Demand rates for the reserved capacity, even if unused; eligible Reserved Instance or Savings Plans discounts can apply to matching usage per billing rules.

Therefore, never generalize that "buying a Reserved Instance always secures capacity" or "all RIs are only discounts." Check Regional/Zonal type, instance attributes, and current terms.

### 4.3. Azure Reservations

Azure Reservations for many compute services generally reduce prices when committing to usage for a term. An Azure reservation for VMs does not automatically mean capacity is pre-reserved in a zone.

Azure offers **On-demand Capacity Reservation** for supported VM configurations/regions/zones. This reservation holds capacity for selected attributes and can be billed at the corresponding rate even when underutilized. Azure Reservation discounts can apply to matching usage per service rules.

During design, separate VM reservations used for price optimization from capacity reservations used to hold slots. Check availability separately by region, zone, VM size, subscription, and quota.

### 4.4. Google Cloud Committed Use and Reservations

Google Cloud offers **Committed Use Discounts (CUD)** for eligible compute usage. CUDs reduce costs when committing over a term; the commitment itself does not guarantee resources can be allocated in a specific zone.

Google Cloud **Reservations** for Compute Engine can reserve capacity for VMs with matching attributes. Reservations are created under supported scopes and configurations; reserved capacity may incur charges even when unused. CUDs can apply to eligible usage according to product billing rules.

Distinguish resource-based/flexible CUDs, reservations, and Spot VMs. They solve different pricing and capacity problems.

## 5. Savings Plans and Committed Use Discounts

Savings Plans and CUDs often fit organizations that have a relatively steady baseline compute spend but want more flexibility than locking into one very specific instance type.

### 5.1. AWS Savings Plans

AWS Savings Plans are hourly compute spend commitments over a term in exchange for lower rates on eligible usage. Types exist with different flexibility scopes, such as Compute Savings Plans and EC2 Instance Savings Plans.

Key points:

- They are spend-commitment-based discount mechanisms.
- Compute Savings Plans offer broader flexibility across eligible compute types.
- EC2 Instance Savings Plans are generally tied more closely to a specific family/region.
- Savings Plans do not reserve EC2 capacity in an Availability Zone.
- If eligible usage falls below the commitment, unused commitment may still be billed.

If a workload requires guaranteed capacity, pair Savings Plans with Capacity Reservations or another capacity strategy.

### 5.2. Google Cloud Committed Use Discounts

CUDs allow committing to eligible spend or resources over a term for discounted pricing. Scope and application depend on commitment type, service, region, and resources.

CUDs should be purchased against a predictable usage baseline, not transient load peaks. A CUD is not a guarantee that a specific VM will have capacity in a desired zone.

### 5.3. Azure Savings Plan for Compute

Azure Savings Plan for Compute applies discounts to eligible compute spend within supported products and regions. It provides greater flexibility across compute types than highly specific reservations, without reserving zonal capacity on its own.

When guaranteed VM launch in a specific zone is required, evaluate Azure Capacity Reservation separately.

### 5.4. Flexible Commitments vs. Resource-Locked Commitments

| Characteristic | Flexible Commitment | Resource-Locked Commitment |
|---|---|---|
| Goal | Discounts across a broader usage set | Deeper discounts for a specific configuration |
| Flexibility | Can switch families/services within allowed scope | Often restricted by family, region, size, or platform |
| Mismatch risk | Lower, though not zero | Higher if workloads change |
| Capacity assurance | Not included by default | Only if the specific product explicitly states a capacity benefit |
| Best suited for | Fleets with steady compute baseline but shifting configurations | Stable workloads with rarely changing configurations |

## 6. Capacity Reservation: Reserving Compute Slots

Capacity Reservations answer the question: "Can we launch the exact machine type in the exact place at the moment we need it?"

### 6.1. Why Reserve Capacity?

In the cloud, quotas and physical capacity are two distinct limits:

- **Quota** is the resource ceiling permitted within an account/project/subscription.
- **Capacity** is the provider's physical infrastructure availability to allocate a resource type at a specific location.

An account with ample remaining quota can still fail to launch a VM type in a zone due to temporary capacity shortages. Conversely, holding a reservation without sufficient quota or policy permissions can also cause usage to fail.

Capacity Reservations are useful when:

- Events or traffic surges require launching many VMs simultaneously.
- DR recovery requires guaranteed launch in a specific zone/region.
- Workloads require scarce instance families or GPUs.
- Batch windows are tight and cannot wait for capacity to free up.
- Critical systems require maintaining standby reserve capacity.

### 6.2. Reservations Have Specific Scopes

Before placing a reservation, check:

- Region and zone.
- Machine type/family, vCPU, memory, and accelerators.
- CPU architecture and platform/OS if constrained.
- Number of instances or total capacity.
- Network/subnet and attachment conditions.
- Reservation duration and modification options.
- Whether the reservation can be shared across other accounts/projects.
- Billing when capacity is unused and how discounts apply.

A reservation only guarantees attributes within the product's scope. Reserving a VM type does not automatically guarantee GPUs, public IPs, disk IOPS, database connections, or bandwidth across every dependency.

### 6.3. Unused Reservations Can Still Cost Money

Reserved capacity may be billed even when no VM is consuming it. This is the cost of holding access to scarce resources.

Illustrative example:

- Reserve 10 VM slots in a zone.
- Average usage is only 6 VMs.
- The remaining 4 VM capacity slots stay reserved and may incur charges.

If steady demand only needs 6 VMs, reserving 10 VMs may be wasteful. If 10 VMs are mandatory during critical events, the spare capacity may be a reasonable cost to reduce launch-failure risk.

### 6.4. Reservations Are Not Autoscaling

Autoscaling adjusts VM counts based on metrics or schedules. Capacity reservations pre-hold launch capability. Both mechanisms can complement each other:

- The autoscaler decides how many VMs are needed.
- The Capacity Reservation provides slots for part or all of those VMs.
- The group/scale set provisions VMs from a template.
- Health checks confirm machines are ready.

An autoscaler cannot manufacture physical capacity if the provider lacks stock and no matching reservation exists. Likewise, a reservation does not launch VMs by itself without a scaling group or automation controller.

## 7. Spot and Preemptible: Lower Price in Exchange for Reclamation Risk

Spot/Preemptible VMs use spare provider capacity at lower prices than On-Demand. The provider can reclaim the resources when capacity is needed or under product terms.

Characteristics:

- Typically priced significantly lower than On-Demand.
- No guarantee that instances will keep running for the desired duration.
- May receive an interruption notice in some cases, though notices should not be relied upon as an absolute guarantee.
- Capacity fluctuates by region, zone, instance type, and demand.
- Workloads must tolerate restarts, retries, or losing partial progress.

Well-suited for:

- Checkpointed batch processing.
- Retryable CI builds/tests.
- Distributed rendering.
- Certain ETL or analytics workloads.
- Training jobs with checkpoints and externalized data.
- Queue workers using leases, idempotency, and retries.

Unsuitable if the instance holds the sole copy of critical data, the workload cannot restart, or continuous capacity is mandatory with no fallback.

Spot lowers prices but is not a capacity assurance tool. To guarantee capacity for non-interruptible workloads, use On-Demand or appropriate capacity reservations/commitments.

## 8. Benefit Classification Matrix

| Product / Model | Pricing Discount | Capacity Guarantee | Interruptible by Product Mechanism |
|---|---|---|---|
| On-Demand | No commitment discount | Not by default | Not reclaimed via Spot mechanics, though still subject to outages/provider events |
| Savings Plans | Yes | No | No (not Spot mechanics) |
| CUD | Yes | Not by default | No (not Spot mechanics) |
| Regional RI (AWS) | Yes | Not zonal | No (not Spot mechanics) |
| Zonal RI (AWS) | Yes | Conditional capacity benefit | No (not Spot mechanics) |
| Capacity Reservation | No automatic discount; can combine with eligible discounts | Yes within reservation scope | No (not Spot mechanics) |
| Azure VM Reservation | Yes | Not by default | No (not Spot mechanics) |
| Azure Capacity Reservation | No automatic discount; can combine with eligible discounts | Yes within reservation scope | No (not Spot mechanics) |
| Google Cloud CUD | Yes | Not by default | No (not Spot mechanics) |
| Google Cloud Reservation | No automatic discount; can combine with eligible CUDs | Yes within reservation scope | No (not Spot mechanics) |
| Spot/Preemptible | Lower pricing | No | Yes, subject to reclamation |

This table is a conceptual model. How discounts, reservations, and billing combine depends on the specific product, resource attributes, and current terms. For AWS Zonal Reserved Instances, capacity benefits are conditional and must not be generalized to Regional RIs or Savings Plans.

## 9. Calculating Commitment Benefits and Risks

Do not select a commitment solely from advertised discount percentages. Calculate total costs across realistic usage scenarios.

### 9.1. Basic Comparison Formulas

Using a simple model:

\[
\text{On-Demand cost} = \text{Eligible usage} \times \text{On-Demand rate}
\]

\[
\text{Commitment cost} =
\text{Committed amount} + \text{Usage exceeding commitment}
\]

Actual commitment cost depends on how the product calculates hourly, resource-based, upfront, or monthly obligations. Use the provider's exact billing model for formal calculations.

### 9.2. Pricing Commitment Example

Suppose a workload has a hypothetical On-Demand rate of 0.10 USD per equivalent VM-hour. An eligible commitment discounts the rate by 30% to 0.07 USD per committed hour. For simplicity, suppose a commitment covers 1,000 equivalent VM-hours in the period:

| Actual Usage | On-Demand | 1,000-Hour Commitment at 0.07 USD | Outcome |
|---:|---:|---:|---|
| 1,200 hours | 120 USD | 70 + 20 = 90 USD | Saves 30 USD |
| 1,000 hours | 100 USD | 70 USD | Saves 30 USD |
| 800 hours | 80 USD | 70 USD | Saves 10 USD |
| 500 hours | 50 USD | 70 USD | Costs 20 USD more |

This example only illustrates underutilization risk. In real products, commitments may be measured by hourly spend and applied via specific billing priority order rather than a simple bundle of "VM-hours".

### 9.3. Commitment Utilization Ratio

\[
\text{Commitment utilization} =
\frac{\text{Eligible usage covered}}{\text{Committed amount}}
\times 100\%
\]

Track utilization alongside coverage:

- **Utilization:** portion of the commitment actually consumed.
- **Coverage:** portion of total eligible spend covered by commitments.

Low utilization means paying for unused commitments. Low coverage means substantial usage remains on On-Demand where commitments might be evaluated.

Do not maximize coverage at all costs. Buying commitments to cover brief peaks can lock in long-term costs exceeding actual savings.

### 9.4. Capacity Reservation Example

Suppose reserving 8 VM slots at a hypothetical rate of 0.10 USD/slot/hour for 30 days:

\[
8 \times 0.10 \times 24 \times 30 = 576\ \text{USD}
\]

If average usage is only 5 slots, the cost of unused reserved capacity is equivalent to:

\[
(8-5) \times 0.10 \times 24 \times 30 = 216\ \text{USD}
\]

This is a simplified model showing idle capacity cost. Actual billing, applied discounts, and reservation types may differ. The value of the 3 spare slots is the ability to launch during sudden surges or recovery events.

## 10. Choosing Tools by Workload Type

| Workload | Appropriate Pricing Discount | Capacity Strategy |
|---|---|---|
| 24/7 production baseline | Savings Plan/CUD/RI sized to steady usage | Reservations for critical configs/zones if guarantees are needed |
| Variable-load APIs | Commitment for baseline, On-Demand for fluctuations | Autoscaling, capacity buffers, and reservations for known events |
| Retryable batch jobs | Spot/Preemptible combined with commitments for baseline if suitable | Pool diversification, checkpointing, and On-Demand fallback |
| Hourly dev/test | On-Demand, auto-shutdown schedules, Spot for interruptible runs | No long-term reservations unless specifically required |
| GPU inference/training | Commitment if GPU usage is steady; Spot for interruptible jobs | Reservations by GPU type/zone when scarce |
| Disaster recovery | Commitment for standby baseline if usage is steady | Capacity reservation in recovery zone/region when RTO requires it |
| Scheduled high-load events | Commitment for baseline if used long-term | Temporary or planned capacity reservations |

A single fleet can combine multiple models. For example, cover production baseline with commitments, use On-Demand for scale-out, Spot for retryable batch, and capacity reservations for a group of VMs requiring guaranteed launch during DR.

## 11. Decision Workflow

~~~mermaid
flowchart TD
    A["Identify compute requirements"] --> B{"Need guaranteed machines in a specific location?"}
    B -- "Yes" --> C["Define zone, type, quantity, and duration"]
    C --> D["Evaluate Capacity Reservation"]
    D --> E{"Is usage stable long-term?"}
    B -- "No" --> E
    E -- "Yes" --> F["Analyze Savings Plan / CUD / RI"]
    E -- "No" --> G{"Can workload tolerate interruption?"}
    G -- "Yes" --> H["Evaluate Spot/Preemptible"]
    G -- "No" --> I["Use On-Demand and autoscaling"]
    F --> J["Model utilization, coverage, and total cost"]
    H --> J
    I --> J
    J --> K["Verify quotas, capacity, scope, and terms"]
    K --> L["Pilot, monitor, and adjust"]
~~~

Detailed steps:

1. **Classify the workload:** baseline, burst, batch, dev/test, DR, or GPU.
2. **Measure usage:** by hour, day, week, season, and region.
3. **Define availability requirements:** is capacity needed in a specific zone/instance type?
4. **Separate baseline and variability:** commitments should only cover predictable portions.
5. **Assess interruption tolerance:** does the workload have checkpoints, retries, idempotency, and externalized state?
6. **Select products:** pricing discounts, capacity reservations, or a combination.
7. **Check terms:** term, scope, exchange/cancellation, payment, sharing, and billing.
8. **Simulate scenarios:** low usage, normal usage, growth, and peaks.
9. **Purchase in phases:** avoid committing the entire fleet upfront.
10. **Review periodically:** utilization, coverage, unused capacity, and actual effectiveness.

## 12. Questions to Verify Before Purchasing

### 12.1. On Pricing Discounts

- Which services, families, regions, and platforms does the commitment apply to?
- Does it apply across different instance sizes?
- Can family, region, or account be changed?
- Can it be resold, exchanged, or canceled?
- What are the upfront level and payment schedule?
- Which usage is ineligible?
- Can discounts combine with reservations or license benefits?
- How is unused commitment handled?

### 12.2. On Capacity

- Does the reservation hold the exact zone and machine type needed?
- Is quantity counted in instances, vCPUs, GPUs, or capacity units?
- Is there an expiration or start/end schedule?
- Must the reservation be toggled or bound to specific VMs?
- Can it be shared with other accounts/projects/subscriptions?
- Are quotas sufficient to consume the reservation?
- Does the reservation cover disks, networking, public IPs, or accelerators?
- How is billing handled when unused or partially used?

### 12.3. On Resilience

- If a zone fails, does a reservation in that zone retain usable value?
- Is there a reservation or capacity strategy in a backup zone?
- If an instance type is deprecated, are replacements available?
- Can the autoscaler launch the exact reserved configuration?
- Does startup time meet RTO?
- Is spare capacity sufficient to serve load while failed VMs are replaced?

## 13. Common Risks

### 13.1. Buying Commitments Above Baseline

If workloads shrink after optimization or migrate to containers/serverless, old commitments may lack eligible usage. Unused portions still generate cost.

Mitigations:

- Use multi-cycle usage data.
- Subtract seasonal loads or workloads nearing retirement.
- Leave growth margin without treating peaks as baseline.
- Buy in tranches and review utilization.

### 13.2. Confusing Discounts with Capacity Guarantees

A Savings Plan or CUD can lower the bill without holding slots in a specific zone. During regional capacity shortages, VM launches can still fail.

Mitigations:

- Document pricing commitments and capacity requirements separately.
- Verify the exact reservation product type.
- Test launching VMs in the target zone/type.
- Include capacity checks in DR exercises and game days.

### 13.3. Over-Sizing Capacity Reservations

Surplus reservations generate charges even when idle. Reserve quantities should be grounded in failover, burst, and capacity replacement timing needs.

Mitigations:

- Calculate minimum capacity needed when losing a zone.
- Use autoscaling for variable demand whenever feasible.
- Choose reservations with appropriate duration/scope.
- Track reservation utilization.

### 13.4. Wrong Zone or Mismatched Instance Attributes

A reservation cannot substitute for any machine type. If instance type, platform, tenancy, or zone mismatches, VMs may fail to consume the reservation.

Mitigations:

- Verify attributes against actual inventory.
- Check reservation matching rules.
- Test-launch using exact templates.
- Monitor unused reservations alongside On-Demand usage simultaneously.

### 13.5. Relying on Spot for Non-Interruptible Workloads

Low prices are tempting, yet interruptions drop requests, lose progress, or cause data errors.

Mitigations:

- Use only for retryable/checkpointed workloads.
- Externalize state and enforce idempotency.
- Diversify across pools/families/zones.
- Maintain On-Demand fallbacks or reserve capacity for critical parts.

## 14. Post-Purchase Monitoring and Optimization

A compute purchasing decision does not end when signing a commitment. Usage and architectures evolve over time.

Track:

- Commitment utilization and coverage.
- Remaining On-Demand spend.
- Unused reservation capacity.
- Launch failures caused by capacity shortages.
- Usage by family, zone, and region.
- Running instances delivering no business value.
- Architectural changes, retirement schedules, or migrations.
- Cost per request, job, or completed transaction.

Periodic reviews:

1. Reconcile bills against forecasts and actual usage.
2. Identify commitments with low utilization.
3. Identify steady On-Demand usage suitable for coverage.
4. Verify reservations still hold the right capacity types.
5. Assess workload changes before renewing.
6. Adjust per exchange/cancellation rules and product terms.

Do not optimize solely for discount percentage. The goal is lowering total cost while meeting capacity, availability, and resilience requirements.

## 15. Design Example Combining Pricing and Capacity

An API service has baseline demand equivalent to 20 VMs most of the time, rises to 35 VMs at peak hours, and needs 10 extra VMs in a DR scenario.

One approach:

| Demand Segment | Purchasing / Operating Approach | Rationale |
|---|---|---|
| 20 baseline VMs | Flexible pricing commitment or matching RI | Stable, predictable usage |
| 15 peak VMs | On-Demand via autoscaling | Needed only during specific hours |
| 10 DR capacity VMs | Capacity Reservation at standby site if RTO demands it | Reduces capacity shortage risk during failover |
| Auxiliary batch | Spot if jobs have checkpoints | Lowers cost for interruptible workloads |

Before deploying, verify whether the 20-VM baseline truly holds across the entire commitment term, whether peaks might shrink after optimization, whether DR reservations match the exact zone/type, and whether quotas suffice.

If a 10-VM capacity reservation is held solely for DR, idle capacity may still incur costs. Compare that cost against the business impact of failing to launch enough machines within RTO. If the organization tolerates longer provisioning times, pilot light or On-Demand capacity can be cheaper, though drills are needed to verify.

## 16. Pre-Decision Checklist

**Objectives**

- [ ] Clearly separated pricing discount goals from capacity assurance goals.
- [ ] Identified baseline, peak, batch, and DR workloads.
- [ ] Aligned on availability and RTO requirements.

**Pricing Commitment**

- [ ] Have sufficient usage history with retiring workloads excluded.
- [ ] Defined scope, term, payment, and eligible usage.
- [ ] Modeled low, normal, and growth utilization scenarios.
- [ ] Understood exchange, modification, or cancellation rules.

**Capacity Reservation**

- [ ] Identified zone, instance attributes, and quantity to reserve.
- [ ] Verified quotas and reservation matching rules.
- [ ] Understood billing for unused capacity.
- [ ] Verified capacity for related dependencies and networking.
- [ ] Planned fallbacks if a zone or instance type is unavailable.

**Operations**

- [ ] Autoscalers and instance templates can consume reservations properly.
- [ ] Alerts configured for unused capacity and launch failures.
- [ ] Tested scale-out and DR failover.
- [ ] Scheduled periodic utilization/coverage reviews.
- [ ] Planned adjustments to commitments as workloads change.

## 17. Operational Principles

1. **Separate the two problems:** discounts lower unit price; capacity reservations hold resource slots.
2. **Never infer from product names:** Reserved Instance, Reservation, and Commitment carry different semantics across providers.
3. **Commit only predictable baselines:** avoid locking in short-term peaks or workloads about to change.
4. **Use capacity reservations for guaranteed launch needs:** specify the exact zone, type, and count.
5. **Account for idle capacity cost:** reservations may still charge when unused.
6. **Use Spot for interruptible workloads:** require checkpoints, retries, idempotency, and fallbacks.
7. **Track quotas separately from capacity:** having quota does not mean the provider has physical capacity.
8. **Combine tools intentionally:** commitments for baseline, On-Demand for variability, reservations for guaranteed capacity, and Spot for suitable batch jobs.
9. **Validate through testing:** test launches, autoscaling, failover, and billing matching.
10. **Review periodically:** changes in usage, architecture, and terms can erode initial purchasing decisions.

Pricing discounts and capacity reservations address two distinct risks. Commitments cut costs when workload usage is steady enough; capacity reservations reduce the risk of failing to launch resources where needed. By separating both objectives, modeling usage and idle costs, and combining them per workload segment, organizations can optimize budgets while maintaining sufficient compute power for production and incident recovery.
