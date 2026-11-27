# Managing Oracle License Costs and Choosing BYOL

In the **Cost and Capacity Management** chapter, choosing a licensing model is part of designing Oracle Cloud Infrastructure (OCI) infrastructure. For the exact same application, total cost can shift substantially when changing the database service, edition, CPU count, redundancy topology, or how previously purchased licenses are applied.

This lesson focuses on Oracle Database on OCI, where the **License Included** vs. **Bring Your Own License (BYOL)** choice ties directly to compute capacity and high-availability architecture. For other Oracle software such as WebLogic, maintain separate entitlement records and calculations for that exact product; do not carry Oracle Database rules directly over to it.

After this lesson, learners can:

- Distinguish OCI service costs, software entitlements, and support fees.
- Build a license ledger and reconcile it against production, standby, testing, and migration resources.
- Compare both models using Total Cost of Ownership (TCO), runtime hours, and scaling needs.
- Design license controls tied to compartments, IAM, cost monitoring, and deployment automation.

## 1. Two Decisions That Must Be Solved Together

When deploying a database, the infrastructure team must answer two questions:

1. **Which resources satisfy the workload?** Consider latency, throughput, storage capacity, RTO, RPO, and operability.
2. **Which entitlements cover that configuration?** Consider product, edition, metric, quantity, features, and contract scope.

A configuration with enough CPUs can still lack licenses. A valid set of licenses can still fail to match the service or edition the application requires. Financial decisions must therefore rest on a configuration that meets technical requirements and has verified entitlement backing.

### License Included and BYOL

| Dimension | License Included | BYOL |
|---|---|---|
| Source of software entitlement | Bundled with the chosen service, within offering scope | From eligible organization-owned licenses |
| Items to model | Service rate with license included plus ancillary charges | BYOL service rate, support on carried licenses, plus ancillary charges |
| Data to manage | Service, edition, features, usage | Items on the left plus license records and allocations |
| Decision question | Does the offering cover the requirements? | Do existing licenses truly cover the target configuration? |

Oracle describes BYOL to PaaS as applying existing software entitlements with software support maintained under the corresponding support contract; annual support payment obligations continue. BYOL therefore does not mean zero software cost. See [Oracle BYOL FAQ](https://www.oracle.com/cloud/bring-your-own-license/faq/).

In practice, keep three figures separate: the OCI bill, off-OCI license/support costs, and operational staffing costs. Looking solely at the cloud invoice can make BYOL appear cheaper than its true total cost.

## 2. Identify Exactly Where Oracle Database Runs

Before calculating costs, specify the target service. "Running Oracle on OCI" is not specific enough to pick one licensing rule.

| Deployment option | Details to specify before comparing |
|---|---|
| Oracle Base Database Service | Edition, CPU model, shape, capacity, license model, HA setup |
| Autonomous Database | Workload type, ECPU/OCPU model, edition used for BYOL, autoscaling, redundancy |
| Exadata Database Service | Deployment type, infrastructure and database billed separately, enabled CPUs, enabled features |
| Self-managed Oracle Database on OCI Compute | Host/CPU scope requiring licensing, operational duties, and corresponding software entitlements |

Distinguishing managed databases from self-managed installations on Compute is especially important. Do not use Compute VM unit rates to represent the full cost of a managed database; nor should you extend an add-on entitlement of one database service to every VM in the tenancy.

For licensing documentation, check the exact Oracle Database version, offering, and features. Oracle provides entitlement tables by offering and a **Special License Rights** section in [Database Licensing Information](https://docs.oracle.com/en/database/oracle/oracle-database/26/dblic/Licensing-Information.html).

A minimal configuration description should look like:

```text
Workload: order system
Target service: Oracle Base Database Service
Edition: Enterprise Edition
CPU model: specify exact ECPU or OCPU for chosen config
Production: baseline capacity, peak capacity, usage schedule
HA/DR: local resources and DR region resources
Features: list separately any options/management packs actually needed
Planned license model: License Included or BYOL
Entitlement record: internal reference ID and accountable owner
```

VCNs and subnets define network connectivity; compartments and IAM help organize and restrict resource access. These components aid governance, yet they do not replace software entitlement records.

## 3. Build a License Ledger Before Choosing BYOL

A license ledger maps what entitlements the organization owns to where those entitlements are currently consumed. Do not start with "the company already bought Oracle"; establish exactly what was bought and where it is allocated.

### 3.1. Records to Collect

| Information group | Details to record | Purpose |
|---|---|---|
| Product and edition | Program name, edition, version in use | Avoid applying entitlements from another product/edition |
| Metric and quantity | Processor, Named User Plus, or contract-defined metric | Choose the exact calculation |
| License type | Full Use, application-specific, or other restricted rights | Identify permitted workloads |
| Contract scope | Legal entities, territories, and related restrictions | Check whether the target environment is in scope |
| Support | Status, term, cost, and associated license pool | Verify BYOL eligibility and cash outlay |
| Options/management packs | Separate entitlements, counts, and usage locations | Avoid checking only base database licenses |
| Current allocation | On-premises, OCI, standby, and test environments | Detect overlapping allocations |
| Evidence | Contracts, ordering documents, addenda, and applicability confirmations | Substantiate the basis for decisions |

**Processor** and **Named User Plus (NUP)** are distinct metrics. NUP is not merely concurrent logged-in users; check definitions of authorized users/devices, multiplexing rules, and minimums. Full Use, Application Specific, and Embedded rights also differ in scope. See concepts in [Oracle Software Licensing Basics](https://www.oracle.com/a/ocom/docs/corporate/oracle-software-licensing-basics.pdf).

Do not infer BYOL eligibility merely from having a My Oracle Support account or software media. Specific licenses must trace to applicable terms and active support status.

### 3.2. Unused Entitlements vs. Portable Entitlements

For example, an asset register listing six licenses does not mean all six are free for OCI. Some may actively serve on-premises production; others may carry application restrictions or lack verification records.

One way to structure an internal allocation ledger:

```text
Total verified entitlements
- entitlements allocated to existing systems
- entitlements reserved for parallel migration environments
- entitlements committed to other projects
= entitlements remaining eligible for allocation review
```

This is a portfolio governance formula, not an Oracle license conversion rule. Every deduction must name a target, start/end dates, and an owner. Release an allocation only after verifying the legacy system meets corresponding decommissioning criteria.

For ULAs, application-restricted rights, or special agreements, record conclusions strictly per the governing contract text. Do not turn a contract category name into an assumption of "unlimited use everywhere."

## 4. Translate OCI Capacity into License Demand

### 4.1. Do Not Equate ECPU, OCPU, vCPU, and Processor Licenses

These names belong to different measurement contexts. When building calculations, specify:

- Service resource unit: ECPU, OCPU, or another unit.
- Available license metric.
- Conversion factor for the exact service/SKU and edition.
- Rounding rules, caps, and minimum requirements.
- Options/packs or redundancy entitlements requiring separate verification.

Do not take a ratio from a legacy service, another hyperscaler, or a self-managed host and apply it to an OCI managed database.

Specifically scoped example: the BYOL section for **Oracle Base Database Service – BYOL – x86 – ECPU, B112728**, in the Service Descriptions effective November 5, 2026, specifies that one supported Enterprise Edition Processor license corresponds to up to 8 ECPUs. This ratio is not a universal rule across all products. See [Universal Credits Service Descriptions](https://www.oracle.com/contracts/docs/paas_iaas_universal_credits_3940775.pdf), section BYOL Non-Autonomous Database Cloud Services.

### 4.2. Allocation Example Using a Verified Ratio

Suppose a project uses that exact service and EE terms above, holds four eligible Processor licenses, and has zero allocations on other systems. Consider only base database licenses in this calculation:

| Item | Capacity to cover | Processor licenses at 8 ECPU ratio |
|---|---|---:|
| Production at baseline | 16 ECPU | 2 |
| Identified DR needing coverage | 8 ECPU | 1 |
| Increment for production peak | 8 ECPU | 1 |
| Total at production peak | 32 ECPU | 4 |

At peak state, production uses 24 ECPUs and DR uses 8 ECPUs. The "increment" row in the table is the capacity needing coverage during scaling, not a separate third running resource.

For an individual configuration under those exact conversion terms:

```text
Processor licenses to evaluate = ceil(ECPUs to cover / 8)
```

With multiple resources, apply the allocation/rounding rules of the applicable terms; do not pool fractional remainders across multiple databases into one shared bucket on your own. The example above uses divisible numbers to focus on allocation.

If developers spin up an additional 8-ECPU clone while production sits at peak, demand reaches 40 ECPUs and exceeds the four-license allocation. A pre-deployment check must catch this scenario even if last month's bill was still low.

### 4.3. Migration Windows Easily Cause Double Allocation

Suppose those same four licenses are still required by the legacy system during parallel operation. You cannot simply re-label the allocation to OCI and pretend the legacy system vanished.

A migration plan must state clearly:

1. The overlap window when both environments coexist.
2. Entitlements or billing models covering each environment during that window.
3. Cutover, rollback, and parallel-run end timestamps.
4. Evidence of legacy resource retirement and ledger updates.

Without sufficient entitlements for concurrent runs, the team must adjust timelines, acquire interim rights, or pick an appropriate service model for the transition phase. Do not assume a universal grace period applies to every migration.

## 5. Verify Edition, Options, and Management Packs

Two systems both labeled "Enterprise Edition" may still require different entitlement sets. Needs such as partitioning, compression, security, clustering, diagnostics, or active standby queries must be checked against the exact offering and version.

Oracle grants certain additional rights for BYOL on designated database services. For instance, EE BYOL on Base Database Service is listed with rights to use Diagnostics Pack and Tuning Pack. This is not a blanket grant for every option or for self-managed databases on Compute. Check the **Special License Rights** section in [Database Licensing Information](https://docs.oracle.com/en/database/oracle/oracle-database/26/dblic/Licensing-Information.html).

A feature checklist is far more useful than a checkbox reading "has Oracle license":

| Feature needed | Technical rationale | Entitlement basis | Applicable scope | Conclusion |
|---|---|---|---|---|
| Feature A | Satisfies application queries | Purchased right or offering entitlement | Exact service, edition, version | Sufficient / insufficient evidence |
| Feature B | Satisfies ops or HA | Corresponding terms | Production, standby, or other environment | Sufficient / needs add-on |

For existing databases, combine configuration inventories, feature usage history, and entitlement records. A feature appearing in installed binaries or toggleable via parameter does not prove the organization holds rights to use it.

If cutting cost by downgrading editions or dropping options, verify the application still functions properly and meets SLAs. Saving license spend while breaking recovery or performance targets does not produce an equivalent deployment option.

## 6. Tie Licensing to Autoscaling, HA, and DR

### 6.1. Cost Demand and Entitlement Demand Use Different Lenses

To estimate bills, you typically integrate resource capacity over time:

```text
Resource-hours = sum(billable capacity in interval × hours in interval)
```

To verify BYOL, determine which capacity requires license coverage under service rules. Monthly average CPU does not prove sufficient licenses exist for scaled-out peaks.

Therefore, capacity profiles should capture baseline, allowed peak, and expected duration at each level. Whenever autoscaling rules change, update both the cost model and the license allocation check together.

### 6.2. Autonomous Has a Specific BYOL ECPU Limit Mechanism

Autonomous ECPU documentation describes an option to cap the number of ECPUs covered by BYOL for EE. The API also specifies that usage exceeding `byolComputeCountLimit` is treated as License Included and billed accordingly. Apply this mechanism only on offerings that support it; do not assume every DB system handles license overages that way. See [Autonomous ECPU guide](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/autonomous-update-license.html) and [BYOL limit field description in the API model](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/database/models/oci.database.models.UpdateAutonomousDatabaseDetails.html).

When using a BYOL limit, manage two boundaries: ECPU count backed by entitlements and the cost of usage above the cap. If the limit only governs billing mode, do not treat it as proof that resources stop scaling at that level. Also check autoscaling behavior, edition, standby, and resource-specific settings.

### 6.3. Do Not Overlook Replicas and Standby Environments

A capacity review checklist should include:

- Primary and HA nodes.
- Same-region or cross-region standbys.
- DR environments opened for drills or reporting.
- Clones for UAT, performance testing, and troubleshooting.
- Legacy environments still running during migration or rollback windows.

Oracle distinguishes shared-storage cluster failover from copying/synchronizing/mirroring setups. The ten-day 24-hour failover rule carries strict conditions; it cannot be treated as a blanket free pass for every cloud standby or DR setup. See [Licensing Data Recovery Environments](https://www.oracle.com/a/ocom/docs/data-recovery-licensing-070587.pdf).

Downsizing DR to save money must be paired with recovery verification. Know to what level standby resources must scale during an incident, which entitlements cover that level, and how incident operating costs are budgeted.

## 7. Compare Using TCO and Break-Even Points

### 7.1. Normalize Both Options Before Calculating

Two quotes are comparable only when meeting the same requirements. State service, edition, features, performance, runtime hours, storage, backups, HA/DR, deployment region, and analysis horizon explicitly.

If two offerings deliver different performance, benchmark the workload to find configurations meeting the same SLA. Do not force identical CPU counts and then conclude the lower per-CPU rate is cheaper.

A straightforward financial model:

```text
Period TCO = OCI service costs
           + off-OCI support/license costs
           + amortized additional license purchases in period
           + operational costs
           + amortized migration costs in period
```

Items inside OCI costs may include compute/database meters, storage, backups, transfer, and dedicated infra. Separate anything already included in a unit rate so you do not double-count.

For contracts with spend commitments or credits, add a cash-flow and commitment-burn view. Credits alter payment mechanics or internal cost allocation; they do not prove sufficient BYOL entitlements.

### 7.2. Example Using Purely Hypothetical Prices

Suppose two configurations meet identical requirements, both using 8 billable resource units denoted `U`. `U` is purely a problem unit; do not infer from this example that ECPU equals OCPU or Processor licenses. The unit prices below are **not an Oracle price list**.

| Variable | Hypothetical value |
|---|---:|
| License Included unit rate | 1.20 USD/U-hour |
| BYOL unit rate | 0.45 USD/U-hour |
| Monthly usage hours | 730 hours |
| Shared OCI storage, backups, and other items | 500 USD/month |
| Incremental support for BYOL option | 3,500 USD/month |
| License Included operations | 150 USD/month |
| BYOL operations | 220 USD/month |
| Additional license purchase and migration | 0 USD in this example |

Key assumption in this comparison: 3,500 USD support is a true incremental cost difference between the two options. Use this assumption only if the License Included path lets you retire that support spend after checking contract terms. If the organization must continue paying support under both options, include it in both columns or exclude it from the delta calculation.

Results at 730 hours:

| Cost item | License Included | BYOL |
|---|---|---:|
| Service resources | 8 × 730 × 1.20 = 7,008 | 8 × 730 × 0.45 = 2,628 |
| Shared OCI costs | 500 | 500 |
| Off-OCI support in comparison scope | 0 | 3,500 |
| Operations | 150 | 220 |
| **Total USD/month** | **7,658** | **6,848** |

BYOL saves 810 USD/month under these hypothetical assumptions. Looking solely at the 4,380 USD service-bill difference would miss support and added operational overhead.

### 7.3. Break-Even Point Depends on Runtime Hours

With fixed capacity and identical shared OCI costs:

```text
Break-even occurs when:
n × H × (p_LI - p_BYOL)
= (support_BYOL - support_LI)
  + (ops_BYOL - ops_LI)
  + other period cost differences
```

Applying the hypothetical figures:

```text
H = (3,500 + 220 - 150) / (8 × (1.20 - 0.45))
  = 3,570 / 6
  = 595 hours/month
```

| Usage duration | License Included TCO | BYOL TCO | Lower option under assumptions |
|---|---:|---:|---|
| 160 hours/month | 2,186 USD | 4,796 USD | License Included, lower by 2,610 USD |
| 595 hours/month | 6,362 USD | 6,362 USD | Break-even |
| 730 hours/month | 7,658 USD | 6,848 USD | BYOL, lower by 810 USD |

This explains why a 24/7 environment and an environment running a few hours daily can lead to opposite choices even for the same workload and unit rates.

With autoscaling, replace `n × H` with the sum of resource-hours across intervals. If an offering bills over-cap BYOL usage as License Included, separate the usage and unit prices of those two segments.

### 7.4. Distinguish Sunk Costs from Future Costs

Purchase prices paid for licenses years ago may be sunk costs. When making new deployment choices, examine future cash flows that actually change between options. When reporting full costs to a business unit, the organization may still amortize license value per internal accounting policy.

Do not add the full upfront purchase price into every single month. For multi-year TCO models, specify amortization periods, annual support, add-on purchases, scaling changes, and price escalation assumptions. Also weigh opportunity cost: allocating licenses to this project might force another project to buy more.

Stopping resources may reduce service charges per offering rules, yet it does not automatically cancel support fees on owned licenses. Savings from shutdown schedules must be calculated strictly on costs that actually vary.

## 8. Choose a Model Based on Evidence

The table below is a decision framework, not a conclusion applicable to every contract:

| Situation | Path to evaluate first | Required evidence |
|---|---|---|
| No matching licenses available, short-term project | License Included | Offering satisfies requirements and runtime-based estimate |
| Eligible unallocated licenses exist, steady workload | BYOL | Entitlement records, support, conversion math, and TCO |
| Licenses exist but remain needed on-premises | Parallel-run plan or phased cutover | Point-in-time allocation and entitlements for overlap |
| Sudden workload spikes beyond covered capacity | Scaling caps or BYOL-overage billing if supported | Service behavior, entitlement caps, and bill forecast |
| Licenses carry app/entity restrictions or unclear records | Complete entitlement verification before choosing BYOL | Documented conclusion grounded in governing agreements |

A portfolio decision may use License Included on one resource and BYOL on another. Each resource still requires its own license-model setting and record; splitting across a catalog does not prove two models can be mixed arbitrarily inside a single resource.

Record the decision as a short decision note capturing target configuration, chosen model, TCO, license allocation, approver, and re-evaluation triggers. For example, raising maximum CPUs, enabling new features, or adding a standby are events that can invalidate an earlier decision.

## 9. Embed License Controls into OCI Operations

### 9.1. Assign Roles and Archive Evidence

| Role | Primary responsibility in workflow |
|---|---|
| Application owner / DBA | Define workload, edition, features, HA, and DR |
| OCI platform team | Inventory resources, control configurations, compartments, and IAM |
| Software asset management / procurement | Verify entitlements, support, and license allocations |
| FinOps / finance | Track TCO, forecasts, invoices, and cost allocation |

Internal tags can link resources to cost center, environment, owner, and license ledger reference ID. For example, an org-defined namespace `Governance` with key `LicenseAllocationRef` pointing to a managed record. A tag is only a governance link; a value saying `"BYOL-approved"` does not create software rights.

Never store full contracts or sensitive details inside tags. Store evidence in an access-controlled repository and put only needed reference IDs on resources.

### 9.2. Pre-Change Controls

In infrastructure pipelines or change processes, require checks whenever:

- Creating or cloning a database.
- Switching to BYOL or changing edition.
- Increasing CPUs, raising autoscaling ceilings, or changing shapes.
- Adding nodes, standbys, DR regions, or test environments.
- Enabling features that can alter entitlement requirements.

An internal validation logic can be expressed as:

```text
Read planned configuration and allocation ledger.
Identify service, edition, metric, and applicable rules.
Compute post-change demand across all relevant environments.
Verify base licenses, options/packs, and support.
Compare against remaining allocatable entitlements.
If data is missing or entitlements are exceeded: block change and escalate to owner.
If substantiated: record result, timestamp, and change request ID.
```

This is an organizational process design. Do not assume a tag, IAM policy, or IaC tool understands Oracle contract clauses natively. IAM governs who may execute actions; the license ledger and reconciliation workflow determine whether that action is backed by software entitlements.

### 9.3. Post-Deployment Monitoring

Establish periodic reconciliation across three sources:

1. **Actual resources:** license model, CPUs, autoscaling, replicas, and enabled features.
2. **Costs:** which resources incur which charges and how much variance exists against estimates.
3. **Entitlement ledger:** which licenses are allocated and through what date support remains valid.

Cost alerts catch invoice shifts, yet they do not prove license compliance. Conversely, a properly licensed resource can still breach budget. Every alert needs an owner and concrete follow-up, such as reviewing a new clone or verifying a recent scale-out.

In the operational calendar, review resources regularly, reconcile costs each billing cycle, and check support renewal milestones against contract dates. Cadence should match how fast the environment changes.

## 10. Practice Configuration Inventory and Proposal Drafting

This section uses existing resources with appropriate read permissions. There is no need to create new databases or switch license models to complete the exercise. Without an OCI environment, use the hypothetical setup from section 4 and hypothetical prices from section 7 to practice the calculations.

### Step 1: Read Resource Configuration

With OCI CLI configured for profile, region, and permissions, read a Base Database DB system in PowerShell:

```powershell
$dbSystemId = 'ocid1.dbsystem.REPLACE_WITH_YOUR_RESOURCE_OCID'
oci db system get --db-system-id $dbSystemId --output json
```

Verify identifier, compartment, shape, edition, CPU settings, and `license-model`. This command targets eligible DB system resources and does not represent every Exadata resource. Refer to [OCI CLI: db system get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/db/system/get.html).

For Autonomous Database:

```powershell
$autonomousDatabaseId = 'ocid1.autonomousdatabase.REPLACE_WITH_YOUR_RESOURCE_OCID'
oci db autonomous-database get --autonomous-database-id $autonomousDatabaseId --output json
```

Read license model, CPU model/capacity, and scaling, BYOL limit, or standby fields returned for that offering. Any missing or `null` field must be checked against corresponding documentation. Refer to [OCI CLI: autonomous-database get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/db/autonomous-database/get.html).

Configuration JSON reports resource state; it does not confirm your organization's contract covers that state. Combine the output with the license ledger and cost data.

### Step 2: Build a Scenario Capacity Table

Record baseline and peak levels for production, DR, and test environments. Create at least three time columns: normal operations, peak load, and parallel migration.

For each column, recalculate license demand using verified rules. Flag items lacking data rather than filling in a generic multiplier. State clearly which portion is covered by BYOL and which follows another billing model if supported by the offering.

### Step 3: Calculate TCO for Both Options

Use unit prices and terms valid at the time of evaluation; in a learning setting, use the lesson's hypothetical prices. Separate service charges, support, operations, additional purchases, and migration. Include actual runtime hours and sensitivity to demand growth.

Results must show which option is lower at baseline, which wins at peak, and which delta could flip the conclusion. If unsure whether support can be reduced, present both scenarios rather than picking an assumption favorable to BYOL.

### Step 4: Prepare for Change if Selecting Another Model

For supported Base Database DB systems, Oracle guides opening resource details, selecting **Actions → Update license type**, choosing the model, and saving/confirming. This change affects billing metering. See [Manage Licenses on a DB System](https://docs.oracle.com/en/cloud/paas/base-database/guide/dbs-licenses.html).

Before executing in practice, complete entitlement verification, allocation updates, cost forecasts, and organizational change approval. Afterward, verify returned state, period cost data, and the allocation ledger. The Console accepting a selection does not substitute for an entitlement determination.

The practice deliverable is a proposal containing the resource table, entitlement allocation table, two TCO options, and prerequisites before changing. No write actions on OCI are needed merely to demonstrate understanding of the decision process.

## 11. Mistakes That Corrupt Cost Decisions

| Mistake | Consequence | Fix |
|---|---|---|
| Comparing only compute unit rates | Misses support, storage, DR, and operations | Normalize configurations then calculate TCO |
| Treating all Oracle licenses as interchangeable | Wrong product, edition, or usage scope | Match each entitlement line to the target service |
| Using average CPU to prove BYOL sufficiency | Misses peak configurations or autoscaling | Verify coverage across every scenario |
| Assigning the same license to on-premises and OCI without basis | Double allocation during migration | Schedule parallel runs and matching entitlement records |
| Assuming DR or non-production is always license-free | Uncovered replicas and drills | Inventory every environment and check applicable terms |
| Assuming every option requires separate purchase or is included | Over-purchasing or under-licensing | Check exact offering, version, and add-on rights |
| Treating `license-model` field as proof of compliance | Configuration diverges from entitlement records | Reconcile resources against license ledger and evidence |
| Stopping machines and removing all support from estimates | Overstates net savings | Separate usage-variable charges from contract obligations |
| Cutting license spend by dropping HA without checking SLA | Fails recovery requirements | Verify RTO/RPO and capacity during outages |

Decisions must be revisited whenever workload, configuration, entitlements, or prices change. A record that clearly explains **which resources are covered by which entitlements, at what times, and at what total cost** is the foundation for operating BYOL under control on OCI.
