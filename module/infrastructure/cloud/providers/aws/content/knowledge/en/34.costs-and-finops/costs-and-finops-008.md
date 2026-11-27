# Savings Plans, Reserved Instances, and Commitment Selection

## Learning Objectives

AWS offers multiple pricing models to lower costs for workloads with steady usage. In return, organizations commit to a spend level or usage configuration over a fixed term. When chosen well, commitments reduce spend relative to On-Demand. When over-purchased, when workloads shift, or when the wrong scope is selected, the organization still pays for unused commitments.

In the AWS ecosystem, Savings Plans and Reserved Instances (RIs) are the two primary mechanisms for optimizing compute and database spend. They differ in commitment units, scope of applicability, flexibility, capacity rights, and financial risk. This lesson helps you evaluate these options using usage telemetry, architectural design, and planned workload changes.

After this lesson, learners will be able to:

- Distinguish On-Demand, Spot, Savings Plans, Reserved Instances, and On-Demand Capacity Reservations.
- Explain the four types of Savings Plans: Compute, EC2 Instance, Database, and SageMaker AI.
- Distinguish Standard/Convertible EC2 Reserved Instances and Regional/Zonal scope.
- Understand RDS Reserved DB Instances and size flexibility limitations.
- Size commitments based on steady usage, coverage, utilization, and opportunity cost.
- Use Cost Explorer Recommendations, Purchase Analyzer, and reservation reports to evaluate options.
- Select term, payment option, account scope, and commitment levels aligned with risk tolerance.
- Establish governance, track expirations, and adjust commitment portfolios as architectures evolve.

## 1. Why Commitment Pricing Models Are Needed

On-Demand fits when flexibility is paramount, workloads are still volatile, or usage levels are unknown. For steady, long-running workloads, paying 100% On-Demand can cost significantly more than discounted commitment rates.

AWS uses multiple pricing models:

| Model | Payment Structure | Best Suited When |
|---|---|---|
| On-Demand | Pay for actual resource consumption with no long-term commitment | New, spiky, or short-lived workloads |
| Spot | Use spare AWS capacity at lower rates; can be interrupted | Batch, CI, background processing capable of retry/checkpoint |
| Savings Plans | Commit to eligible hourly spend in USD/hour over a term | Steady baseline usage needing service or configuration flexibility |
| Reserved Instances | Commit to configuration attributes and term for a billing discount | Steady EC2/RDS or reservation-eligible service usage |
| On-Demand Capacity Reservation | Reserves EC2 capacity in an AZ without an inherent discount | Guaranteed capacity is needed in a specific AZ |

Savings Plans and RIs do not run resources for you, do not replace Auto Scaling, and do not guarantee application correctness. They are pricing constructs and billing discounts; architectures must still be engineered for load, availability, and recovery.

### 1.1. Commitments Are Financial Obligations

When buying a Savings Plan, an organization commits to an hourly spend level for the entire term. When buying an RI, an organization commits to paying per the selected term and offering, even if no matching instance is running. No Upfront simply means no large initial lump sum; it does not eliminate the payment obligation over the term.

Before purchasing, answer:

- Which workloads generate steady usage?
- How much usage will remain after rightsizing or migrations?
- When might workloads shrink, change Regions, switch engines, or change instance families?
- Can budgets absorb upfront or recurring charges across the full term?
- Who is accountable for monitoring utilization and making renewal decisions?

## 2. On-Demand, Spot, and Commitments: Choosing the Right Layer

Do not try to cover every dollar of usage with commitments. Different workloads carry different stability profiles and requirements.

| Workload Profile | Typically Suitable Option |
|---|---|
| 24/7 steady production baseline with minimal change | Savings Plans or RIs |
| API with steady base load plus seasonal scaling | Commit the baseline; leave peaks on On-Demand |
| Batch workloads tolerant of interruption | Spot combined with On-Demand as needed |
| Dev/test environments running business hours only | Scheduling and On-Demand; commit only if baseline is truly steady |
| Experimental, POC, or temporary migration workloads | On-Demand |
| Guaranteed EC2 capacity needed in a specific AZ | Zonal RI or On-Demand Capacity Reservation, depending on discount needs |
| Steady database usage with stable engine | RDS Reserved DB Instance or Database Savings Plan |
| Database with plans to change engine/service or Region | Database Savings Plan can be more flexible than traditional RIs |

A sound strategy combines multiple models: cover the steady baseline with commitments, handle variable bursts with On-Demand, run interruptible batch jobs on Spot, and address critical capacity separately.

## 3. How Do Savings Plans Work?

Savings Plans are a discounted pricing model in exchange for committing to consume a specified amount of eligible services measured in USD per hour. AWS automatically applies Savings Plans rates to matching usage. Operators do not manually bind individual instances to a reservation.

General characteristics:

- Common terms are 1 year or 3 years; 1 year equals 365 days and 3 years equals 1,095 days by Savings Plans definition.
- Commitments are measured in USD/hour at the Savings Plans rate, not the equivalent On-Demand spend.
- Each hour has its own commitment bucket. Unused commitment in one hour cannot roll over to the next hour.
- Eligible usage above the commitment is billed at On-Demand rates.
- Plan commitment and Savings Plans rates cannot be modified or canceled mid-term.
- Additional plans can be purchased if steady usage grows, though the full commitment portfolio must be analyzed.
- Savings Plans do not reserve capacity.

### 3.1. Hourly Commitment Is Not an On-Demand Budget

Suppose eligible EC2 usage has an On-Demand equivalent of $100 USD/hour. If the Savings Plans rate for that configuration is $60 USD/hour, the commitment to evaluate is roughly $60 USD/hour at the Savings Plans rate.

Never take $60 USD/hour of On-Demand spend and blindly enter $60 USD/hour as the commitment without checking applied rates. AWS expresses commitments in Savings Plans rates, so the same On-Demand usage requires a lower commitment figure.

### 3.2. Unused Commitment Still Costs Money

If a commitment is $60 USD/hour but eligible usage in a given hour consumes only $45 USD at Savings Plans rates, utilization for that hour is 75%. The remaining $15 USD is neither refunded nor carried over to the next hour.

If eligible usage exceeds what the commitment covers, the excess is billed at On-Demand rates. This is why usage must be evaluated hourly rather than buying commitments off monthly averages alone.

## 4. Four Types of Savings Plans

Per current AWS documentation, there are four Savings Plans types, each covering a different scope of usage.

| Type | Eligible Scope | AWS-Published Max Savings and Flexibility |
|---|---|---|
| Compute Savings Plans | EC2, AWS Fargate, AWS Lambda | Up to 66%; not locked to EC2 instance family, size, Region, OS, or tenancy |
| EC2 Instance Savings Plans | Amazon EC2 | Up to 72%; locked to instance family and Region; flexible across size, OS, and tenancy within that scope |
| Database Savings Plans | Eligible database services | Up to 35%; flexible across engine, family, size, AZ, Region, and provisioned/serverless types within supported scope |
| SageMaker AI Savings Plans | Amazon SageMaker AI | Up to 64%; flexible across eligible family, size, Region, and components |

AWS's published "up to" savings figures represent maximum discounts relative to On-Demand under specific configurations and conditions. Never use those maximums as default savings assumptions across every Region, engine, or workload.

### 4.1. Compute Savings Plans

Compute Savings Plans carry the broadest scope within compute:

- Applies to EC2 regardless of instance family, size, Region, OS, or tenancy.
- Applies to AWS Fargate, including Fargate on ECS and EKS.
- Applies to eligible AWS Lambda usage.
- Best suited when workloads may switch instance families, Regions, or compute platforms.

For example, a workload migrating from EC2 `m7i` to `c8g`, moving Regions, or shifting containers to Fargate continues receiving Compute Savings Plans discounts as long as the new usage stays within eligible scope.

Compute Savings Plans do not cover every fee associated with ECS/EKS. For clusters running on EC2, EC2 instances can be covered, while control plane fees, orchestration, load balancers, storage, data transfer, and other components follow their own pricing rules. For EKS on Fargate, separate Fargate compute fees from EKS control plane fees.

### 4.2. EC2 Instance Savings Plans

EC2 Instance Savings Plans require choosing:

- One AWS Region.
- One EC2 instance family, such as `m7i` or `c8g`.
- An hourly commitment in USD/hour.
- Term and payment option.

Within the selected family and Region, the plan applies across sizes, OSes, and tenancies under supported rules. It fits when an organization is confident it will keep a specific family in a specific Region while retaining size flexibility.

For example, `m7i.large` can resize to `m7i.2xlarge` and remain covered by an `m7i` EC2 Instance Savings Plan in that Region. Switching to `c8g` or another Region moves usage outside this plan's scope.

### 4.3. Database Savings Plans

Database Savings Plans were introduced by AWS for data services. They can apply to eligible usage across:

- Amazon Aurora and Amazon RDS.
- Amazon DynamoDB.
- Amazon ElastiCache.
- Amazon DocumentDB.
- Amazon Timestream.
- Amazon Neptune.
- Amazon Keyspaces for Apache Cassandra.
- AWS Database Migration Service (DMS).
- Amazon OpenSearch Service.

Database Savings Plans can cover both provisioned and serverless usage within supported service scopes. For latest-generation provisioned instances, discounts apply automatically across engine, instance family, size, Availability Zone, and Region. This is valuable when organizations modernize databases or evolve deployment models.

Examples:

- Upgrading Aurora from `db.r7g` to `db.r8g`.
- Moving a workload from Ireland to London.
- Modernizing RDS for Oracle to Aurora PostgreSQL-Compatible Edition.
- Shifting a suitable access pattern from RDS to DynamoDB.
- Moving a workload from provisioned to serverless within supported scope.

Database Savings Plans currently offer a 1-year term and No Upfront option. AWS Billing provides a separate Advance Pay feature if an organization wishes to prepay. Published discounts reach up to 35%, though actual savings vary by service and usage type.

Do not assume every database feature, storage, backup, I/O, or data transfer charge is covered. Check exact eligible usage types in the Database Savings Plans pricing table.

### 4.4. SageMaker AI Savings Plans

SageMaker AI Savings Plans apply to eligible Amazon SageMaker AI instance usage. Scope is flexible across eligible instance families, sizes, Regions, and components such as Notebook, Training, or Inference per current pricing documentation.

This plan suits organizations with steady SageMaker usage that may switch instance families or shift workloads across components. Do not use it to cover standard EC2 or other AI services outside the documented list.

## 5. Savings Plans Terms and Payment Options

For Compute, EC2 Instance, and SageMaker AI Savings Plans, buyers typically choose a 1-year or 3-year term and one of three payment options:

| Payment Option | Payment Structure | Cash Flow Impact |
|---|---|---|
| No Upfront | Nothing paid upfront; commitment billed periodically | Minimal initial cash outlay; full term obligation remains |
| Partial Upfront | Portion paid upfront and remainder billed periodically | Balances upfront outlay and recurring payments |
| All Upfront | Entire commitment paid upfront | Large initial cash outlay; no recurring plan payments |

The payment option alters cash timing, not the plan's usage scope. Any unused commitment remains a payment obligation.

Database Savings Plans carry their own term/payment rules as noted above; do not mechanically apply Compute Savings Plans options to Database Savings Plans.

## 6. What Are Reserved Instances?

A Reserved Instance is a billing discount tied to a specific configuration or usage type over a term. For EC2, RI attributes may include instance type/family, platform, scope, and tenancy. For RDS, discounts bind to database engine, Region, class, edition, and license type.

An RI is not a physical server set aside exclusively by AWS. You still launch and run instances normally. When usage matches RI attributes, the billing engine applies the discounted rate.

General characteristics:

- EC2 RIs offer 1-year or 3-year terms.
- RDS Reserved DB Instances offer 1-year or 3-year terms depending on the offering.
- No Upfront, Partial Upfront, and All Upfront options exist for most RIs; availability depends on service and instance type.
- Billing commitments continue accruing over the term even if instances are stopped or idle, per service rules.
- At term end, usage reverts to On-Demand rates unless another commitment applies.

Never purchase RIs solely from a snapshot of currently running instances in the console. Evaluate attributes alongside hourly usage, accounts, Regions, and change roadmaps.

## 7. EC2 Reserved Instances: Standard vs. Convertible

EC2 offers two primary offering classes:

| Characteristic | Standard RI | Convertible RI |
|---|---|---|
| Discount level | Typically higher | Typically lower than Standard |
| Exchange to another RI configuration | No | Yes, subject to exchange rules |
| Modify selected attributes | Yes, within allowed limits | Yes |
| Sell on Reserved Instance Marketplace | Possible, if eligible | No |
| Best suited when | Configuration is steady with minimal change | Configuration flexibility is needed within the same Region |

Standard RIs cannot be exchanged for different RI types. Convertible RIs can be exchanged for other Convertible RIs with different attributes such as instance family, type, platform, or tenancy under AWS conditions. Exchanges may require a true-up payment if the new reservation value exceeds the remaining value of the old reservation.

A Convertible RI is not a blank check to swap freely across any service or Region. The Region of a Convertible RI remains fixed for the entire term. Before exchanging, inspect remaining value, remaining term, resulting instance counts, and any incremental cost.

### 7.1. Modify vs. Exchange

- **Modify:** changes allowed attributes of an existing reservation—such as scope or Availability Zone—or splits/merges reservations where supported.
- **Exchange:** converts a Convertible RI into another Convertible RI with different configuration attributes, potentially including family or platform.

Do not confuse modifying a Standard RI with exchange rights. Standard RIs allow modifying certain attributes but cannot be exchanged.

### 7.2. Reserved Instance Marketplace

Eligible EC2 Standard Regional or Zonal RIs can be sold on the Reserved Instance Marketplace. Convertible RIs cannot be sold on the Marketplace. Eligibility depends on remaining term, reservation history, payment option, and AWS Marketplace conditions.

The Marketplace is not a guaranteed exit strategy for over-purchasing. Sale prices are market-driven, may fall below expected value, and listings may find no buyer.

## 8. EC2 RI Scope: Regional vs. Zonal

EC2 RIs support two scopes:

| Attribute | Regional RI | Zonal RI |
|---|---|---|
| Scope | One Region | One Availability Zone |
| Billing discount | Applies across any AZ in the Region for matching usage | Only usage in the selected AZ |
| Capacity reservation | No | Yes, in the specified AZ |
| Instance size flexibility | Conditional | No |
| Best suited when | Flexible discount across AZs is desired | Discount plus capacity in a specific AZ is needed |

Regional and Zonal RIs do not differ in purchase price due to scope alone. The core difference is capacity reservation versus flexibility.

### 8.1. Instance Size Flexibility

Regional RIs can provide size flexibility within the same instance family when conditions are met—commonly Linux/Unix with default tenancy. The billing engine uses normalized units to distribute discounts across sizes.

Illustrative example: if one larger size equals two smaller sizes by normalization factor, one larger-size RI can cover the equivalent combined usage of two smaller instances in the same family and Region. Verify platform, tenancy, family, and current normalization factor tables.

Zonal RIs have neither AZ flexibility nor instance size flexibility. They bind to a specific AZ and instance configuration while providing a capacity reservation in that AZ.

### 8.2. RIs Do Not Cover Every Capacity Need

Regional RIs provide only a billing discount, not reserved capacity. If an organization needs guaranteed EC2 capacity in a specific AZ, evaluate Zonal RIs or On-Demand Capacity Reservations (ODCRs).

An ODCR reserves capacity for a specific configuration and AZ without creating a discount on its own. When instances run inside reserved capacity, eligible RIs or Savings Plans can still apply discounts. If reserved capacity goes unused, ODCR still incurs charges at On-Demand rates.

## 9. Amazon RDS Reserved DB Instances

An RDS Reserved DB Instance is a billing discount for eligible DB instance usage, not a pre-provisioned physical DB instance.

When purchasing an RDS RI, match:

- AWS Region.
- Database engine.
- DB instance type/class.
- DB instance size if the engine lacks size flexibility.
- Edition and license type for engines with multiple licensing options.
- Single-AZ or Multi-AZ offering.
- Term and payment option.

Exact engine version numbers generally do not need to match, though engine, Region, and required attributes must align.

### 9.1. RDS RI Size Flexibility

Certain RDS Reserved DB Instances can cover other sizes within the same instance class type and Region via normalized units. Engines listed by AWS for size flexibility include:

- RDS for Db2.
- RDS for MariaDB.
- RDS for MySQL.
- RDS for Oracle Bring Your Own License.
- RDS for PostgreSQL.

Size flexibility does not apply to RDS for SQL Server or RDS for Oracle License Included under documented rules. Aurora has its own reservation guidelines; verify specific engines and offerings before purchasing.

Size flexibility does not allow switching from `db.r6i` to `db.r7g` or `db.r6id`. You must remain within the exact instance class type supported by the RI.

### 9.2. Multi-AZ and Normalized Units

RDS RIs can apply to Single-AZ or Multi-AZ configurations. When shifting between deployment options within size flexibility scope, normalized units across primary/standby instances must be calculated accurately.

For a three-instance Multi-AZ DB cluster, never assume one Single-AZ RI covers the whole cluster. Check exact reservation quantities and normalized unit equivalents in RDS documentation.

### 9.3. Costs RDS RIs Do Not Cover

RDS RIs primarily discount eligible hourly DB instance usage. They do not automatically reduce charges such as:

- Provisioned database storage.
- Backup storage beyond free allowances.
- Separately billed I/O or IOPS.
- Data transfer.
- Features or components outside the covered usage types.

Therefore, when comparing total costs, never take the instance-hour discount percentage and apply it to the entire database bill.

### 9.4. RDS RI Payment Options

RDS offers No Upfront, Partial Upfront, and All Upfront depending on the offering. No Upfront is available only for 1-year terms per current RDS documentation; not every DB instance class offers every payment option.

Before purchasing, check actual offerings in the target Region and engine via the console or `describe-reserved-db-instances-offerings`.

## 10. Reservations for Other AWS Services

Across AWS, reservation terminology varies by service:

- ElastiCache offers Reserved Nodes.
- Redshift offers Reserved Nodes.
- OpenSearch Service offers Reserved Instances.
- MemoryDB offers reserved node offerings.
- DynamoDB offers reserved capacity for certain provisioned capacity models.

These offerings have distinct attributes, terms, discounts, payment options, and scopes. Do not apply EC2 Standard/Convertible or Regional/Zonal rules to them unless explicitly defined in that service's documentation.

Database Savings Plans include ElastiCache and OpenSearch Service on the current eligible service list. Redshift Reserved Nodes follow their own reservation model and are not listed among Database Savings Plans in plan-type documentation. Never infer that every service with its own reservations is covered; check eligible usage types before committing.

## 11. Comparing Savings Plans, RIs, and Capacity Reservations

| Criterion | Savings Plans | EC2 Regional RI | EC2 Zonal RI | On-Demand Capacity Reservation |
|---|---|---|---|---|
| Commitment unit | USD/hour | EC2 config in Region | EC2 config in AZ | Capacity in AZ |
| Term | 1 or 3 years; Database SP 1 year | 1 or 3 years | 1 or 3 years | Flexible by reservation type |
| Discount | Yes | Yes | Yes | None inherently |
| Reserves capacity | No | No | Yes | Yes |
| Flexibility | Depends on SP type | Region; conditional size flexibility | Lower | Tied to capacity attributes |
| Applies to | Eligible services per plan type | Matching EC2 usage | Matching EC2 usage | Matching EC2 instances |
| Best suited when | Steady baseline usage with possible config changes | Steady EC2 family/config | Both capacity and discount needed in AZ | Capacity needed while keeping On-Demand pricing |

A workload can combine Savings Plans with ODCRs. If you need guaranteed capacity in an AZ alongside discounts, pair an ODCR with eligible Savings Plans or Regional RIs. A Zonal RI both provides a discount and reserves capacity within its scope.

## 12. How Savings Plans and RIs Apply to Bills

The billing engine applies discounts automatically according to precedence rules. Operators must understand the order to avoid double-buying commitments for the same usage.

For EC2:

1. EC2 Reserved Instance discounts apply first.
2. Savings Plans apply after RIs.
3. Within Savings Plans, EC2 Instance Savings Plans apply before Compute Savings Plans due to narrower scope.
4. AWS evaluates savings percentages across eligible usage combinations and applies Savings Plans to usage yielding the highest savings percentage first. On ties, usage with the lower Savings Plans rate takes precedence.
5. Remaining usage after exhausting commitments is billed at On-Demand rates.

In a consolidated billing family, Savings Plans apply first to the owning account's usage. Remaining commitment can share across other accounts if discount sharing is enabled and sharing preferences allow it.

### 12.1. Savings Plans Do Not Cover Spot

Savings Plans do not apply to Spot usage or usage already covered by RIs. Therefore, when modeling commitments, separate eligible On-Demand usage from Spot and already-discounted usage.

### 12.2. Avoiding Double-Counting Savings

Never add potential savings from RI recommendations and Savings Plans recommendations together as independent gains if both target the same underlying usage. AWS recommendations account for current commitment inventory and already-covered usage. Run Purchase Analyzer or compare against one unified baseline after accounting for owned plans.

### 12.3. Discount Sharing in AWS Organizations

With Savings Plans, the management account can analyze usage at the payer scope when discount sharing is enabled. Plans apply to the owning account's usage first, then to other accounts per sharing preferences.

Sharing can be structured by group or account level depending on Billing settings. This maximizes steady-usage utilization across accounts, though governance is needed to avoid one account buying commitments while another account alters workloads and lowers utilization.

## 13. Coverage, Utilization, and Savings

Three metrics must be evaluated together:

- **Coverage:** share of eligible usage covered by commitments.
- **Utilization:** share of purchased commitment actually consumed.
- **Net savings:** actual net savings after accounting for commitment charges and remaining On-Demand usage.

Coverage and utilization are not the same thing.

Examples:

- Large commitment, low usage: low utilization; coverage of remaining usage may be high.
- Small commitment, high usage: utilization near 100%; coverage remains low because most usage stays On-Demand.
- A right-sized baseline commitment aims for high utilization while leaving variable peaks on On-Demand.

### 13.1. Intuitive Formulas

Savings Plans utilization:

\[
Utilization = \frac{Commitment\ used}{Total\ commitment} \times 100\%
\]

Savings Plans coverage:

\[
Coverage = \frac{Eligible\ On\text{-}Demand\ equivalent\ usage\ covered}{Total\ eligible\ On\text{-}Demand\ equivalent\ usage} \times 100\%
\]

AWS reports compute exact figures using On-Demand equivalent rates, eligible usage, and commitment levels. Use Cost Explorer or CUR metrics for official reporting; the formulas above clarify the concepts.

### 13.2. RI Utilization and Coverage

RI utilization measures how much of the purchased reservation was consumed. RI coverage measures how much eligible usage was covered by RIs.

For EC2 size-flexible RIs, inspect normalized units rather than raw instance-hour counts alone. One `2xlarge` instance consumes twice the normalized units of an `xlarge` in the same family.

## 14. Identifying the Baseline Before Committing

Commitments should rest on steady usage *after* resource optimization. Never buy Savings Plans or RIs to subsidize idle or over-provisioned resources.

Workflow:

1. Collect hourly usage over at least 30–60 days; inspect longer windows if seasonality exists.
2. Eliminate idle resources, unnecessary test environments, and misconfigurations.
3. Rightsize compute/databases based on CPU, memory, network, I/O, and latency.
4. Classify workloads into steady-state, seasonal, burst, ephemeral, and interruptible.
5. Exclude usage already covered by RIs, Savings Plans, or Spot.
6. Identify the recurring minimum hourly baseline, not merely the monthly average.
7. Flag workloads likely to shift Region, family, engine, or platform.
8. Pick a commitment level at or below the high-confidence baseline based on risk tolerance.

### 14.1. Why Not Use Monthly Averages?

Suppose a workload runs 24/7 but drops to 30% overnight and doubles during the day. A monthly average hides low-usage nighttime hours. Savings Plans commitments are metered hourly—unused dollars from low hours cannot carry forward to peak hours.

Hourly usage analysis reveals:

- Minimum hourly baseline.
- Median and percentile hourly usage.
- Peak usage.
- Low-utilization hours.
- Weekends or seasonal troughs.
- Effects of deployments, maintenance, and autoscaling.

### 14.2. Forecasts and Architectural Changes

A lookback window is not a forecast. If you plan to migrate EC2 to Graviton, change Regions, switch database engines, retire a workload, or adopt serverless, historical data may no longer represent future usage.

Model approved changes and exclude disappearing usage before buying long-term commitments.

## 15. Choosing Commitment Type by Stability

| Scenario | Option to Consider | Rationale |
|---|---|---|
| EC2 may change family, Region, or move to Fargate/Lambda | Compute Savings Plans | Broad compute coverage |
| EC2 steady in one family and Region, but changing size/OS/tenancy | EC2 Instance Savings Plans | Discount within family/Region |
| EC2 steady configuration needing capacity in an AZ | Zonal Standard RI | Discount plus capacity reservation |
| EC2 steady at Region level without capacity guarantee | Regional Standard RI or EC2 Instance Savings Plans | Pick based on discount, flexibility, and management |
| EC2 needing family/OS/tenancy changes mid-term | Compute Savings Plans or Convertible RI | Avoid configuration lock-in; Convertible RIs require manual exchanges |
| RDS with steady engine, Region, and class | RDS Reserved DB Instance | Billing discount tied to database attributes |
| Multiple database services with possible engine/Region/serverless shifts | Database Savings Plans | Broader flexible scope |
| SageMaker AI with steady instance usage | SageMaker AI Savings Plans | Dedicated scope for SageMaker AI |
| Uncertain usage or potential early shutdown | On-Demand | No long-term financial lock-in |

No single commitment type fits an entire account. Choose per usage group and manage the overall commitment portfolio.

## 16. Choosing a 1-Year vs. 3-Year Term

Longer terms generally offer deeper discounts while locking the organization in longer. Shorter terms reduce architectural and demand-shift risk at slightly lower discount rates.

| Factor | 1 Year | 3 Years |
|---|---|---|
| Flexibility | Higher | Lower |
| Workload change risk | Lower | Higher |
| Discount depth | Typically lower | Typically higher |
| Cash commitment | Shorter obligation | Longer obligation |
| Best suited for | Evolving platforms, uncertain forecasts | Steady workloads with long-term roadmaps |

Never pick a 3-year term solely for a higher discount percentage. Weigh NPV, underutilization risk, opportunity cost, and migration plans over the term.

## 17. Choosing Payment Options and Cash Flow Analysis

No Upfront, Partial Upfront, and All Upfront alter payment timing and effective rates.

When comparing options:

- Normalize upfront and recurring payments across the same analysis period.
- Factor in the enterprise's cost of capital or discount rate.
- Check liquidity and quarterly/annual budget constraints.
- Model potential underutilized commitment exposure.
- Align expense recognition timing with internal accounting policies.

### 17.1. Effective Hourly Cost

For an RI with an upfront payment, convert the upfront fee into an hourly amortized figure over the term for fair comparison:

\[
Effective\ hourly\ cost =
\frac{Upfront\ payment}{Term\ hours}
+ Recurring\ hourly\ charge
\]

This is a straightforward economic view. Accounting reports and Cost Explorer/CUR amortization may follow different allocation rules depending on configuration and reporting period.

### 17.2. Break-Even

Break-even is the point at which cumulative savings offset the upfront payment or beat the On-Demand alternative. If a workload might shut down before break-even, committing can increase total spend.

Cost Explorer reservation recommendations can display break-even months for certain reservations. Treat that as an estimate from historical usage and verify against forecasts.

## 18. Using AWS Cost Explorer and Purchase Analyzer

AWS Cost Explorer provides recommendations and reports to analyze commitments.

### 18.1. Savings Plans Recommendations

In Billing and Cost Management:

1. Open Cost Management.
2. Select Savings Plans → Recommendations.
3. Refresh recommendations to pull current usage and inventory.
4. Choose the Savings Plans type.
5. Choose term and payment option.
6. Choose a 7-, 30-, or 60-day lookback period.
7. Choose payer scope or linked account scope if authorized.
8. Review recommended commitment, estimated savings, coverage, and utilization.

Recommendations derive from historical usage and current commitment inventory. AWS does not forecast future usage and does not automatically treat queued/scheduled purchases as a forecast. If workloads recently changed, choose a post-change lookback window or use Purchase Analyzer with custom scenarios.

### 18.2. Purchase Analyzer

Purchase Analyzer lets you test multiple assumptions:

- Savings Plans type.
- Payer or linked account.
- 1- or 3-year term (Database Savings Plans per supported term).
- Payment option.
- Lookback period within tool-supported bounds.
- Excluding expiring plans.
- Commitment at recommended level, target coverage, or custom hourly amount.

After running, compare three dimensions:

1. Estimated monthly savings.
2. Average hourly coverage increase.
3. Average hourly utilization.

Never accept a recommendation based solely on estimated monthly savings. If projected utilization looks low, lower the commitment or re-verify the workload baseline.

### 18.3. RI Recommendations

In Cost Explorer, select Reservations → Recommendations. Filter by service, term, offering class, payment option, and lookback period. Recommendations can cover EC2, RDS, ElastiCache, OpenSearch, Redshift, MemoryDB, and DynamoDB depending on reservation type.

RI recommendations likewise rely on historical usage and do not predict future changes. Verify Region, engine, class, platform, tenancy, scope, and size flexibility before buying.

## 19. Monitoring Utilization and Coverage

After purchasing, review periodically:

- Savings Plans utilization report.
- Savings Plans coverage report.
- RI utilization report.
- RI coverage report.
- Cost and Usage Report (CUR) or Data Exports.
- Actual costs by linked account, service, Region, and usage type.

### 19.1. Signs of Under-Commitment

- Sustained low coverage.
- High, steady On-Demand eligible spend.
- Utilization near 100%.
- Baseline workload growth persisting for weeks.
- Recommendations showing additional commitments with high projected utilization.

### 19.2. Signs of Over-Commitment

- Sustained low utilization.
- Workloads scaled down, migrated, or terminated.
- RI-matching usage dropping after family, engine, or Region changes.
- Rising unused commitment costs.
- Portions of commitment only used during seasonal peaks.

Do not buy more simply because coverage dips during a single peak day. Equally, do not leave unused commitments unaddressed without a remediation plan.

### 19.3. Budgets and Alerts

Create Savings Plans budgets based on utilization or coverage thresholds. Set alerts when utilization drops below target or when plans near expiration. For RIs, track expirations, coverage, and unused hours.

Metrics and reports carry update latency. Never adjust commitments off a single alert; corroborate against usage, deployments, and event schedules.

## 20. Governance for Commitment Portfolios

Multi-account organizations need explicit governance:

- **Owner:** who is accountable for commitments per workload or account?
- **Approver:** who is authorized to approve 1–3 year financial obligations?
- **Budget:** where are upfront and recurring charges recorded?
- **Scope:** do commitments sit at the payer account or linked account?
- **Sharing:** is Organizations sharing enabled, and which accounts receive benefits?
- **Renewal:** who evaluates expiring plans?
- **Risk:** what are the minimum utilization thresholds and acceptable exposure?
- **Evidence:** where are recommendations, analyzer outputs, and purchase approvals archived?

### 20.1. Approval Policy

A purchase request should document:

1. Workload and owner.
2. Savings Plans/RI type.
3. Hourly commitment or reservation attributes.
4. Term and payment option.
5. Baseline usage and lookback period.
6. Expected utilization/coverage.
7. Estimated savings and break-even.
8. Contraction or workload-change scenarios.
9. Approver and next review date.

Do not allow individual teams to purchase long-term commitments without payer-level visibility. Uncoordinated buying leads to overlapping plans where one account over-commits while another continues paying On-Demand.

### 20.2. Expiration Calendar

Maintain an expiration calendar for every plan and RI. Before expiration:

- Verify whether the workload still exists.
- Check whether family, Region, engine, or architecture changed.
- Compare renewing, switching commitment types, or reverting to On-Demand.
- Refresh recommendations and Purchase Analyzer.
- Queue a new purchase if continuity is desired.

Never auto-renew simply because an expiring reservation previously had high utilization. Demand may have changed.

## 21. Example: Sizing a Commitment for an EC2 Workload

A continuously running EC2 workload shows the following hourly On-Demand equivalent (illustrative figures):

| Time Window | On-Demand Equivalent |
|---|---:|
| Off-peak hours | 80 USD/hour |
| Normal hours | 100 USD/hour |
| Peak hours | 150 USD/hour |

The operations team analyzes 60 days and identifies a steady baseline of $80 USD/hour. After selecting Compute Savings Plans, the Savings Plans rate for the current configuration equals $60 USD/hour.

The architecture team evaluates:

- Committing $60 USD/hour to cover the baseline.
- Keeping the surge from $80 to $150 USD/hour on On-Demand.
- Avoiding committing to the peak since peak hours occur only briefly.

If usage drops to a level costing $45 USD/hour at Savings Plans rates, utilization of the $60 USD/hour commitment is 75%. If usage rises, the commitment is fully consumed and excess usage bills at On-Demand rates.

Key takeaways:

- $60 USD/hour is the Savings Plans rate commitment, not the On-Demand equivalent.
- The baseline must be verified hour by hour.
- If workloads migrate off EC2 to services outside Compute Savings Plans, re-evaluate eligible usage.
- Once purchased, commitments cannot be canceled or reduced mid-term.

## 22. Example: Choosing EC2 RIs vs. EC2 Instance Savings Plans

A workload runs 20 `m7i.large` Linux instances in `ap-southeast-1` steadily year-round.

Two options:

**Option A – Regional Standard RI**

- Fits if family/platform/tenancy configuration is stable.
- Applies across AZs in the Region.
- With supported size flexibility, can cover other sizes in the same family.
- Does not reserve capacity because scope is Regional.

**Option B – EC2 Instance Savings Plans**

- Commits only to the `m7i` family in the selected Region.
- Allows changing size, OS, or tenancy within supported scope.
- Does not reserve capacity.
- Eliminates managing individual RIs or exchanges.

The decision depends on:

- How stable is the configuration?
- Is capacity reservation required?
- Might the workload switch instance families?
- What is the actual net discount after comparing offerings?
- Do existing governance processes depend on RIs?

If capacity in a specific AZ is needed, evaluate Zonal RIs or ODCRs. If instance family changes are possible, Compute Savings Plans offer more flexibility than EC2 Instance Savings Plans.

## 23. Example: Database Commitments — RDS RIs vs. Database Savings Plans

An organization runs PostgreSQL on RDS across two Regions. Over the next 12 months, the data team may:

- Upgrade instance classes.
- Migrate one workload to Aurora PostgreSQL.
- Move one analytics workload to DynamoDB or OpenSearch.
- Adopt serverless for uneven-traffic environments.

RDS Reserved DB Instances can yield strong discounts for steady usage, but bind to Region, engine, and reservation attributes. Size flexibility applies only to supported engines/classes.

Database Savings Plans offer broader flexibility across multiple eligible database services, engines, Regions, and serverless/provisioned usage. However, current terms and payment options differ from Compute Savings Plans.

The team should:

1. Separate database usage by usage type and service.
2. Identify eligible provisioned/serverless portions.
3. Compare RDS RI recommendations against Database Savings Plans recommendations.
4. Model scheduled migrations.
5. Size commitments to the post-migration baseline or stable unchanged portion.
6. Monitor coverage and utilization after purchase.

Never buy an RDS RI for a workload scheduled to migrate soon simply because the current discount percentage looks higher.

## 24. Common Mistakes

1. **Committing based on monthly total spend:** ignores hourly fluctuations.
2. **Buying before rightsizing:** locks in the cost of over-provisioned resources.
3. **Treating recommendations as forecasts:** AWS recommendations are backward-looking.
4. **Confusing commitments with On-Demand spend:** Savings Plans commitments use Savings Plans rates.
5. **Committing too close to peak:** off-peak hours drag utilization down.
6. **Confusing Savings Plans with capacity reservations:** Savings Plans do not reserve capacity.
7. **Confusing Regional RIs with Zonal RIs:** only Zonal RIs reserve capacity in an AZ.
8. **Confusing Standard and Convertible RIs:** Standard cannot be exchanged; Convertible has conditional exchanges.
9. **Assuming all RDS RIs are size-flexible:** SQL Server and Oracle License Included lack size flexibility under the rules above.
10. **Assuming RDS RIs discount the entire database bill:** storage, backups, I/O, and data transfer can be billed separately.
11. **Treating No Upfront as zero commitment:** payment obligations remain across the term.
12. **Adding RI and Savings Plans recommendations together:** can double-count the same usage.
13. **Ignoring Organizations sharing:** commitments can spill over to other accounts per sharing preferences.
14. **Ignoring migration roadmaps:** eligible usage may disappear or shift scope.
15. **Failing to track expirations:** usage reverts to On-Demand at expiry without a new commitment.
16. **Relying on the Marketplace to exit RIs:** neither sale nor full recovery is guaranteed.
17. **Looking only at discount percentage:** ignores upfront outlay, cash flow, utilization, and risk.

## 25. Hands-On Practice: Planning Commitments in Cost Explorer

### 25.1. Gather the Baseline

1. Open Billing and Cost Management.
2. Open Cost Explorer.
3. Select at least 30–60 days; inspect longer windows if seasonality exists.
4. Group by service, Region, linked account, and usage type.
5. Inspect off-peak hours, peaks, weekends, and post-deployment shifts.
6. Exclude usage already covered by RIs, Savings Plans, or Spot when sizing remaining eligible demand.

### 25.2. Open Savings Plans Recommendations

1. Select Savings Plans → Recommendations.
2. Refresh data.
3. Select the Savings Plans type.
4. Select term and payment option.
5. Compare 7-, 30-, and 60-day lookbacks.
6. Compare recommended commitment, coverage, and utilization.
7. Note a more conservative commitment option if usage fluctuates widely.

### 25.3. Use Purchase Analyzer

1. Select Savings Plans → Purchase Analyzer.
2. Select payer or linked account scope.
3. Select plan type, term, and payment option.
4. Pick a lookback window and exclude expiring plans if appropriate.
5. Run Recommended, Target coverage, and Custom commitment scenarios.
6. Compare hourly cost, coverage, and utilization.
7. Save the analysis results into the purchase request.

### 25.4. Evaluate RIs

1. Select Reservations → Recommendations.
2. Choose service, Region, term, and offering class.
3. Verify instance type, engine, platform, tenancy, and scope.
4. Check expected utilization, break-even months, upfront cost, and recurring cost.
5. Check size flexibility and normalized units.
6. Compare against Savings Plans for the same usage.

Do not execute real purchases just to complete a lab. Use simulated figures or inspect recommendations in a test account only.

## 26. Inspecting via AWS CLI

The following commands inspect inventory and reports. They are read-only and do not purchase or alter commitments.

List active EC2 Reserved Instances:

~~~bash
aws ec2 describe-reserved-instances --filters Name=state,Values=active
~~~

List RDS Reserved DB Instances:

~~~bash
aws rds describe-reserved-db-instances
~~~

Retrieve monthly Savings Plans utilization report:

~~~bash
aws ce get-savings-plans-utilization --time-period Start=2026-10-01,End=2026-11-01 --granularity MONTHLY
~~~

Retrieve Savings Plans coverage report:

~~~bash
aws ce get-savings-plans-coverage --time-period Start=2026-10-01,End=2026-11-01 --granularity MONTHLY
~~~

Retrieve RI utilization report:

~~~bash
aws ce get-reservation-utilization --time-period Start=2026-10-01,End=2026-11-01 --granularity MONTHLY
~~~

Retrieve RI coverage report:

~~~bash
aws ce get-reservation-coverage --time-period Start=2026-10-01,End=2026-11-01 --granularity MONTHLY
~~~

Example dates use UTC and exclusive `End` dates per Cost Explorer API semantics. Results vary depending on permissions, Billing data, and account configuration. Use a current AWS CLI version and inspect command help before automating.

## 27. Scenarios Requiring Commitment Re-Evaluation

### 27.1. Workload Scale-Down

If workloads shrink substantially, inspect hourly utilization and unused commitment costs. Active Savings Plans commitments cannot be reduced; adjust future commitment purchases and avoid adding more. For RIs, evaluate modify/exchange options or the Marketplace if eligible.

### 27.2. Changing Regions

Compute Savings Plans continue applying to eligible EC2 usage in the new Region. EC2 Instance Savings Plans bind to the selected Region. Regional EC2 RIs bind to the Region; Convertible RIs cannot be exchanged into a different Region. RDS RIs bind to the Region. Database Savings Plans allow Regional flexibility across supported usage.

### 27.3. Migrating EC2 to Fargate or Lambda

Compute Savings Plans continue covering eligible EC2, Fargate, and Lambda usage. EC2 Instance Savings Plans apply solely to EC2 in the chosen family/Region. If platform modernization is planned, evaluate Compute Savings Plans before locking into a single EC2 family.

### 27.4. Switching Database Engines

RDS RIs bind to engine and Region. Database Savings Plans can preserve discounts when migrating across eligible database services/engines. Verify migration dates, projected usage, and remaining commitment before purchasing.

## 28. Pre-Purchase Checklist

- [ ] Compute/databases have been rightsized.
- [ ] Workloads are classified into steady-state, peak, seasonal, and interruptible.
- [ ] Hourly usage has been analyzed, not just monthly averages.
- [ ] Usage already covered by RIs/SPs or Spot has been excluded.
- [ ] Appropriate Savings Plans or RI type has been identified.
- [ ] Region, family, engine, platform, tenancy, scope, and size flexibility are verified.
- [ ] Whether capacity reservation is truly needed has been evaluated.
- [ ] Term matches workload stability.
- [ ] No/Partial/All Upfront options and cash flow are compared.
- [ ] Commitment is sized in Savings Plans rates, not confused with On-Demand spend.
- [ ] Utilization, coverage, break-even, and unused commitment exposure are reviewed.
- [ ] Migration/modernization roadmap during the term is accounted for.
- [ ] Payer/linked account scope and discount sharing are evaluated.
- [ ] Owner and budget-holder approvals are obtained.
- [ ] Calendar is set to track utilization, coverage, and expirations.

## 29. Self-Check Exercises

### Question 1

In what unit are Savings Plans commitments expressed?

**Answer:** An eligible spend rate measured in USD per hour at Savings Plans rates over the chosen term.

### Question 2

Which compute services can Compute Savings Plans apply to?

**Answer:** Eligible EC2, AWS Fargate, and AWS Lambda usage.

### Question 3

Can EC2 Instance Savings Plans apply to a different instance family in the same Region?

**Answer:** No. The plan is locked to the chosen family and Region, with flexibility across size, OS, and tenancy within supported scope.

### Question 4

What advantage do Database Savings Plans offer when an organization switches engines or database services?

**Answer:** They provide flexible coverage across multiple eligible database services and provisioned/serverless usage, rather than locking tightly to one engine like traditional RDS RIs.

### Question 5

If a Savings Plans commitment is $60 USD/hour but usage consumes only $45 USD at Savings Plans rates, what happens?

**Answer:** Utilization is 75%. The unused commitment is still billed and does not carry over to the next hour.

### Question 6

Can a Standard EC2 RI be exchanged for a Convertible RI?

**Answer:** No. Standard RIs allow modifying certain attributes but cannot be exchanged.

### Question 7

Does an EC2 Regional RI reserve capacity in an AZ?

**Answer:** No. Regional RIs provide only a billing discount across the Region. Only Zonal RIs reserve capacity in a specific AZ.

### Question 8

When do EC2 Regional RIs have size flexibility?

**Answer:** When conditions such as matching instance family, Linux/Unix, and default tenancy are met per AWS rules. Zonal RIs lack size flexibility.

### Question 9

Do RDS RIs reduce storage and backup fees?

**Answer:** Not by default. RDS RIs primarily discount eligible hourly DB instance usage; storage, backups, I/O, and data transfer can be billed separately.

### Question 10

Does No Upfront mean there is no payment commitment over the term?

**Answer:** No. No Upfront only omits the initial lump sum; the term payment obligation still applies.

### Question 11

Does AWS apply EC2 RIs or Savings Plans first?

**Answer:** EC2 RIs apply before Savings Plans. Within Savings Plans, EC2 Instance Savings Plans apply before Compute Savings Plans.

### Question 12

Do Savings Plans apply to Spot usage?

**Answer:** No. Savings Plans do not apply to Spot usage or usage already covered by RIs.

### Question 13

Why shouldn't Savings Plans recommendations be used as forecasts?

**Answer:** Recommendations rely on historical usage and current inventory rather than predicting future workloads or queued purchases. Adjust for migrations and business plans.

### Question 14

If guaranteed EC2 capacity in an AZ is needed alongside discounts, what options exist?

**Answer:** Consider a Zonal RI, or an ODCR paired with eligible Savings Plans/Regional RIs. Separate capacity assurance from billing discounts.

### Question 15

A database workload is scheduled to migrate from RDS to Aurora in 4 months. What should you do before buying a 3-year RDS RI?

**Answer:** Model the migration and remaining usage; compare Database Savings Plans, shorter terms, or On-Demand. Never lock a long-term commitment onto usage expected to disappear.

## 30. Official References

- [AWS Savings Plans – What are Savings Plans?](https://docs.aws.amazon.com/savingsplans/latest/userguide/what-is-savings-plans.html)
- [AWS Savings Plans – Types of Savings Plans](https://docs.aws.amazon.com/savingsplans/latest/userguide/plan-types.html)
- [AWS Savings Plans – Compute Savings Plans and Reserved Instances](https://docs.aws.amazon.com/savingsplans/latest/userguide/sp-ris.html)
- [AWS Savings Plans – How Savings Plans apply to usage](https://docs.aws.amazon.com/savingsplans/latest/userguide/sp-applying.html)
- [AWS Savings Plans – Services eligible for Savings Plans benefits](https://docs.aws.amazon.com/savingsplans/latest/userguide/sp-services.html)
- [AWS Savings Plans – Recommendations calculations](https://docs.aws.amazon.com/savingsplans/latest/userguide/sp-rec-calculations.html)
- [AWS Savings Plans – Purchase Analyzer](https://docs.aws.amazon.com/savingsplans/latest/userguide/sp-purchase-analysis.html)
- [AWS Savings Plans – Purchasing a custom commitment](https://docs.aws.amazon.com/savingsplans/latest/userguide/purchase-sp-direct.html)
- [AWS Savings Plans – Savings Plans FAQ](https://aws.amazon.com/savingsplans/faqs/)
- [Amazon EC2 – Reserved Instances overview](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-reserved-instances.html)
- [Amazon EC2 – Standard and Convertible Reserved Instances](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/reserved-instances-types.html)
- [Amazon EC2 – Regional and Zonal Reserved Instances](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/reserved-instances-scope.html)
- [Amazon EC2 – How RI billing works](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/concepts-reserved-instances-application.html)
- [Amazon EC2 – Capacity Reservation pricing and billing](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/capacity-reservations-pricing-billing.html)
- [Amazon RDS – Reserved DB instances](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_WorkingWithReservedDBInstances.html)
- [AWS Cost Management – Reservation recommendations](https://docs.aws.amazon.com/cost-management/latest/userguide/ri-recommendations.html)
- [AWS Cost Management – Cost Explorer default reports](https://docs.aws.amazon.com/cost-management/latest/userguide/ce-default-reports.html)

Discount rates, offerings, usage types, terms, and quotas vary by service, Region, and date. Before purchasing, verify current pricing pages and offerings in your specific account and Region.
