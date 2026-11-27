# Cost Explorer and Usage Variance Analysis

AWS Cost Explorer is the cost and usage analysis tool within AWS Billing and Cost Management. It helps engineering and finance teams answer questions such as: which service drove this month's cost increase, which account generated the growth, which Region or resource type is consuming more, whether the increase came from usage volume or unit price, and where current trends may take month-end spend.

In FinOps practice, Cost Explorer is the starting point for observing and asking questions. Analysts must combine billing data with deployment records, traffic, transaction counts, release schedules, and architectural changes to uncover root causes. A rising cost chart is only a signal; it is not an explanation.

This lesson places Cost Explorer in the context of AWS operations spanning Regions/AZs, accounts, compute, storage, database, networking, and integration services. The goal is to turn cost data into verifiable engineering decisions while maintaining security, observability, and cost control.

## 1. Learning Objectives

After this lesson, learners will be able to:

- Open Cost Explorer and select appropriate analysis periods, granularities, cost metrics, filters, and groupings.
- Distinguish UnblendedCost, AmortizedCost, BlendedCost, NetUnblendedCost, NetAmortizedCost, and UsageQuantity.
- Compare two periods, calculate absolute and percentage variances, and identify top-contributing services/accounts/Regions.
- Separate variances driven by volume, unit rate, and usage mix; normalize costs by business unit metrics.
- Read trends and forecasts while accounting for data latency, seasonality, and configuration changes.
- Analyze the impact of Reserved Instances and Savings Plans using appropriate metrics.
- Combine tags, Cost Categories, AWS Organizations, Cost and Usage Data Exports, and FinOps workflows to assign accountability.
- Propose optimization actions with owners, hypotheses, before/after metrics, and completion criteria.

## 2. Where Cost Explorer Fits in the Cost Management Ecosystem

Cost Explorer provides a query and visualization interface for cost data, usage data, and commitment-related metrics. Users can view data over time, filter by attributes, group by analytical dimensions, and save reports for reuse.

Distinguish the tools commonly used together:

| Tool | Primary Question | How It Is Used |
|---|---|---|
| AWS Cost Explorer | Where and along which dimensions did cost and usage change? | Interactive analysis, period comparisons, grouping, and forecasting |
| AWS Budgets | Have costs or usage exceeded defined thresholds? | Budgets, alert thresholds, and configured actions |
| AWS Cost Anomaly Detection | Is there an unusual spending pattern compared to normal behavior? | ML-based anomaly detection and alerting |
| AWS Data Exports / Cost and Usage Report (CUR) | Which granular line items make up the aggregated total? | Exporting detailed data for Athena, BI, or internal systems |
| Billing console / invoice | What amount is billed and payable? | Reconciling invoices, taxes, credits, adjustments, and billing periods |

Cost Explorer is suited for exploration and guiding investigations. When you need to trace down to specific usage rows, resource IDs, reservations, Savings Plans, or granular columns, use Data Exports/CUR if the report is configured with the required fields.

Cost Explorer does not replace budget controls, alerting, infrastructure change approvals, or invoice reconciliation. Organizations typically combine these tools: Cost Explorer explains trends, Budgets enforces thresholds, Cost Anomaly Detection catches notable deviations, and CUR/Data Exports supports deep querying.

## 3. Understanding Data Scope and Latency

Cost data is aggregated from AWS service usage and billing information. Visible scope depends on the signed-in account, Billing access permissions, AWS Organizations setup, and whether the user is viewing payer/management account or linked account data.

In a multi-account environment:

- The payer account or management account typically serves as the organization-wide vantage point.
- Linked accounts separate costs by application, environment, team, or business unit.
- Member accounts may only see the scope permitted by IAM permissions and Billing settings.
- Consolidating payment does not mean all users across all accounts automatically gain visibility into all costs.

Cost Explorer data is not a real-time telemetry stream. Usage and cost data may refresh multiple times per day, yet latency remains; certain adjustments, credits, refunds, or period-end fees may appear later. Therefore, when comparing an in-progress period against a closed period, record the extraction timestamp and data status.

Principles for choosing periods:

1. Use completed periods to evaluate more settled financial outcomes.
2. For the current month, compare the same elapsed day count or matching days of the week if usage exhibits seasonality.
3. Avoid comparing the first 10 days of this month against the entire previous month.
4. Document the timezone and start/end dates of reports. API queries use intervals with an exclusive end date.
5. When figures differ from the invoice, check metric, period, account scope, credits/refunds/taxes, adjustments, and latency before assuming an error.

A chart is only meaningful when the reader knows which accounts, timeframe, metric, and charge types it covers.

## 4. Cost Metrics to Distinguish

Cost Explorer supports multiple metrics. Picking the wrong metric can cause two reports for the same period to show different numbers while both remain accurate according to their respective definitions.

| Metric | Practical Meaning | When to Use |
|---|---|---|
| UnblendedCost | Cost calculated at unblended rates for each usage line/account | Tracking costs tied directly to usage and applied rates |
| AmortizedCost | Spreads upfront Reserved Instance/Savings Plan fees across the commitment term | Viewing economic run-rate over time without upfront spikes distorting a single day/month |
| BlendedCost | Cost at blended rates within eligible consolidated billing contexts | Analyzing from an organization-wide blended perspective when billing models use this concept |
| NetUnblendedCost | Unblended cost after eligible discounts reflected in net data | Evaluating post-discount costs on an unblended basis |
| NetAmortizedCost | Amortized cost after eligible discounts reflected in net data | Tracking post-discount economic costs and amortized commitments |
| UsageQuantity | Recorded usage volume across usage types | Analyzing volume when measurement units are homogeneous |
| NormalizedUsageAmount | Usage normalized by conversion factors for supported resource types | Comparing usage across convertible instance sizes, especially in size-flexible RI analysis |

### 4.1 UnblendedCost vs. AmortizedCost

Suppose an organization purchases a Reserved Instance with an upfront fee. UnblendedCost may record the upfront charge when incurred. Looking solely at the purchase month, the chart spikes sharply even though compute capacity is consumed steadily across the entire commitment term.

AmortizedCost spreads the upfront charge across the commitment term, enabling analysis of the economic cost of consuming that capacity per period. This is typically the preferred metric when FinOps teams compare monthly operating costs and evaluate long-term commitment efficiency.

The two metrics answer different questions:

- UnblendedCost: what unblended charges were recorded during the period?
- AmortizedCost: how much commitment cost is allocated to this period?

Do not add values from the two metrics together or compare an UnblendedCost report against an AmortizedCost report without explicitly stating the basis.

### 4.2 Net Cost and Blended Cost

Metrics prefixed with `Net` reflect eligible discounts included in net cost data. Their availability and meaning depend on pricing programs, account types, and billing data. Verify the selected metric rather than assuming `Net` always equals the final invoice.

BlendedCost is meaningful within consolidated billing contexts and rate averaging across accounts. When determining economic cost by consuming account, agree on an internal policy for using blended vs. unblended. Do not use blended merely because the numbers appear easier to distribute.

### 4.3 UsageQuantity Must Accompany Units

UsageQuantity can contain instance-hours, GB-months, requests, API calls, or other units. Summing 1,000 instance-hours plus 2,000 GB-months produces a meaningless figure.

When analyzing UsageQuantity:

- Group by Usage Type or resource type to ensure matching units.
- Verify the measurement unit before summing or averaging.
- If summing usage, sum only lines with identical units and business scope.
- When multiple instance sizes exist, consider NormalizedUsageAmount if the resource type and RI program support normalization.

### 4.4 Choosing a Metric by Question

| Question | Appropriate Metric/View |
|---|---|
| How much did recorded unblended cost increase? | UnblendedCost |
| How did monthly cost with amortized commitments change? | AmortizedCost |
| What is the cost after eligible discounts? | NetUnblendedCost or NetAmortizedCost, depending on goal |
| Did volume of a specific EC2 usage type rise or fall? | UsageQuantity, filtered to the exact Usage Type |
| How did normalized instance usage change in a size-flexible RI group? | NormalizedUsageAmount |
| Need to reconcile against the invoice? | Match the right metric and scope, then reconcile with Billing/invoice and CUR |

## 5. Dimensions, Filters, and Group By

Dimensions are data attributes used to filter or group costs. Common dimensions:

| Dimension | Meaning | Example Question |
|---|---|---|
| SERVICE | AWS service | Did EC2, S3, or RDS drive the increase? |
| LINKED_ACCOUNT | Member account | Which account bears the largest increase? |
| REGION | AWS Region | Did costs in ap-southeast-1 rise? |
| AZ | Availability Zone | Is usage concentrated in one AZ? |
| USAGE_TYPE | Specific usage type | Which instance-hour, storage, or transfer type increased? |
| USAGE_TYPE_GROUP | Usage type group | How did Compute, Data Transfer, or Storage costs change? |
| OPERATION | Operation/action type | Which operation type is generating charges? |
| INSTANCE_TYPE | Instance type | Is m7i.large or r7i.xlarge taking most of the spend? |
| INSTANCE_TYPE_FAMILY | Instance family | How did compute family spend shift? |
| PURCHASE_TYPE | Purchase option | How do On-Demand, Reserved Instances, or Savings Plans affect spend? |
| RECORD_TYPE | Cost line type | How do usage, fees, credits, refunds, or taxes contribute? |
| PLATFORM / OPERATING_SYSTEM | Platform or OS | Do licenses/platforms impact unit rates? |
| TENANCY | Tenancy model | Is there a difference between Dedicated and shared tenancy? |
| TAG | Activated cost allocation tag | Which prod environment, team, or application bears the cost? |

Dimensions appear depending on service, data type, and report context. Not every dimension has a populated value for every cost line item.

### 5.1 Filter vs. Group By

Filters narrow the dataset. For example, filtering `Region = ap-southeast-1` shows only costs in one Region.

Group by splits the dataset into buckets. For instance, after filtering `Region = ap-southeast-1`, grouping by `SERVICE` reveals EC2, S3, RDS, and Data Transfer separately.

A practical investigation sequence:

1. Start organization-wide, grouped by `SERVICE`.
2. Pick the service with the largest variance.
3. Filter to that service and group by `LINKED_ACCOUNT`.
4. Pick the account with the largest variance, then group by `REGION` or `USAGE_TYPE`.
5. If cost allocation tags are activated, group by `Environment`, `Application`, or `Owner`.
6. Correlate the rising usage group with deployment, traffic, or configuration changes.

Do not cram too many dimensions into a single chart upfront. Use one dimension to locate anomalies, then drill down intentionally.

### 5.2 Cost Allocation Tags

Tags such as `Application`, `Environment`, `Owner`, `CostCenter`, or `Product` allocate costs by internal context. Tags attached to resources do not immediately appear as cost analysis dimensions automatically.

To use tags in Cost Explorer:

- Standardize keys/values, casing, and naming conventions.
- Apply tags consistently across taggable resources.
- Activate cost allocation tags in Billing and Cost Management.
- Wait for tag data to propagate and verify in Cost Explorer.
- Build a process to detect untagged resources.
- Define who is responsible for fixing missing tags and the remediation SLA.

Tags cannot accurately allocate all shared costs. For example, a NAT Gateway, shared load balancer, log archive, or data transfer may serve multiple applications. Organizations need transparent allocation rules—such as request count, GB transferred, usage share, tenant count, or an approved fixed ratio.

### 5.3 Cost Categories

Cost Categories group costs using business rules—for example, Production, Non-production, Shared Platform, or Business Unit. Rules can reference accounts, tags, services, or supported attributes.

A strong design requires:

- An owner for each category and rule.
- Explicit rule ordering and handling when a line item matches multiple rules.
- An `Unallocated`/`Unclassified` bucket to surface uncategorized spend.
- Periodic reviews for new accounts, new tags, and organizational changes.
- Change logs for rule updates to explain allocation shifts across periods.

Cost Categories are a governance classification layer. They do not alter the underlying usage or charges metered by AWS.

## 6. Analysis Workflow in the Cost Explorer Console

Use the following workflow for a monthly analysis session.

### Step 1: Open Cost Explorer

Sign in to the AWS Management Console with a role authorized to view Billing and Cost Management. Open Billing and Cost Management, select Cost Explorer, and confirm the account scope being viewed.

If Cost Explorer is not yet enabled or data is not ready, follow the Billing console prompts and wait for data initialization. Enabling the tool or modifying billing visibility permissions must follow organizational account governance.

### Step 2: Select Time Period

Choose the current period, prior period, or a custom range. For monthly reviews, prefer comparing completed months. When analyzing an in-progress month, compare matching elapsed days or matching day-of-week windows against the prior month.

Record:
- Start date and end date.
- Whether the period is closed or in progress.
- Report extraction timestamp.
- Account or organization scope.

### Step 3: Select Granularity

- Monthly: suited for financial reporting, trends, and monthly reviews.
- Daily: suited for pinpointing spike dates, deployment days, or traffic campaign surges.

Finer granularity yields more data points. Start at Monthly to grasp the big picture, then switch to Daily when isolating timing.

### Step 4: Select Metric

Choose UnblendedCost, AmortizedCost, or the metric matching the question. Label the metric clearly on screenshots and reports. Never compare two charts with different metrics.

### Step 5: Apply Filters

Start with filters that narrow the scope:

- `LINKED_ACCOUNT` to isolate an application or environment.
- `SERVICE` to focus on the growing service.
- `REGION` to compare deployment locations.
- `TAG` or Cost Category to view spend by accountability.
- `RECORD_TYPE` to separate usage from credits, refunds, taxes, or fees when needed.

### Step 6: Group By

Group by `SERVICE` to find major buckets. Continue with `LINKED_ACCOUNT`, `REGION`, `USAGE_TYPE`, or tags to decompose the variance.

### Step 7: Read Charts and Tables

Charts reveal trends; tables give exact group values. Examine both:

- How much did total cost change?
- Which group contributed the most to the change?
- Which group shows a high percentage jump despite a small absolute dollar amount?
- Is a one-time fee or credit/refund skewing the chart?
- Do spike dates align with deployments, batch jobs, or business events?

### Step 8: Save the Report and Document Findings

Save recurring configurations as Cost Explorer reports so teams can reopen them. In your conclusions, record the metric, period, scope, filters, groupings, and root-cause hypothesis. A screenshot without query parameters is rarely reproducible.

## 7. Calculating Cost Variance

Variance analysis begins by comparing two periods on an apples-to-apples basis.

Let:

- C0 be the baseline period cost.
- C1 be the current period cost.
- ΔC be the absolute change.
- Δ% be the percentage change relative to the baseline period.

Formulas:

~~~text
ΔC = C1 - C0

Δ% = (C1 - C0) / C0 × 100%
~~~

Example: September cost is $12,000 USD, and October cost is $15,000 USD.

~~~text
ΔC = 15,000 - 12,000 = 3,000 USD

Δ% = 3,000 / 12,000 × 100% = 25%
~~~

Cost increased by $3,000 USD, or 25% compared to the baseline month.

If C0 = 0, a percentage increase cannot be computed with the formula above. Record this as a new cost or newly appearing group and report the absolute dollar figure. Never substitute an arbitrary denominator just to produce a percentage.

When costs decrease, ΔC and Δ% are negative. Keep the negative sign in calculations, then explain clearly in prose using "decreased" to avoid ambiguity.

### 7.1 Fair Comparisons

A trustworthy comparison ensures:

- Same metric.
- Same account and organization scope.
- Same currency.
- Same commitment allocation method.
- Same period status (both closed, or equal elapsed days).
- Same treatment of credits, refunds, taxes, and adjustments.
- Same shared cost allocation policy.

If a new account joined or a tag was activated mid-period, note the classification change. Historical data may not retroactively carry the categorization expected by the current report.

### 7.2 Distinguishing Absolute Dollars from Percentages

Suppose:

| Service | Baseline Period | Current Period | Change | % Change |
|---|---:|---:|---:|---:|
| EC2 | 6,000 | 8,100 | +2,100 | +35.0% |
| S3 | 2,400 | 2,700 | +300 | +12.5% |
| RDS | 1,800 | 1,900 | +100 | +5.6% |
| Data Transfer | 1,200 | 1,500 | +300 | +25.0% |
| Other | 600 | 800 | +200 | +33.3% |
| **Total** | **12,000** | **15,000** | **+3,000** | **+25.0%** |

EC2 accounts for $2,100 USD of the $3,000 USD total increase. It is the top investigation priority because it has the largest absolute impact.

The "Other" group grew 33.3%, nearly matching EC2 in percentage terms, yet rose by only $200 USD. A high percentage does not imply large financial impact. When prioritizing investigations, inspect both ΔC and Δ%.

## 8. Finding Root Causes: Volume, Rate, and Mix

Total cost typically shifts due to one or more factors:

- Volume: running hours, stored GB, requests, replica count, transferred volume, or resource counts rising/falling.
- Rate: unit rates shifting due to Region, instance type, tier, purchase model, discounts, or contracts.
- Mix: shifts in resource proportions—for example, moving from smaller to larger instances or from one Region to another.
- One-time items: upfront payments, one-time fees, credits, refunds, taxes, or adjustments.
- Allocation: changes to tags, Cost Categories, or allocation rules reassigning spend to different buckets.

A simple decomposition for a homogeneous usage type:

~~~text
Cost = Quantity × Unit Rate

Volume Effect = (Q1 - Q0) × P0

Rate Effect = Q1 × (P1 - P0)

Total Change = Volume Effect + Rate Effect
~~~

Here Q0/P0 are baseline quantity and unit rate; Q1/P1 are current quantity and unit rate. This decomposition evaluates volume impact at the baseline rate and rate impact at current volume. Organizations may choose another convention, provided it is documented consistently so reports never double-count.

For example, an EC2 group has 1,000 instance-hours in the baseline period at an illustrative analytical rate of $6 USD/hour. The current period has 1,350 instance-hours at an unchanged unit rate.

~~~text
Baseline = 1,000 × 6 = 6,000 USD
Current = 1,350 × 6 = 8,100 USD
Volume Effect = (1,350 - 1,000) × 6 = 2,100 USD
Rate Effect = 1,350 × (6 - 6) = 0 USD
~~~

In this example, the entire increase comes from volume. In real environments, effective unit rates can be affected by discounts, RIs, Savings Plans, free tier, credits, operating system, tenancy, and Region. Do not infer P simply by dividing total cost by total usage if usage lines have differing units or rates.

### 8.1 Mix Analysis

Suppose an application previously ran primarily on compute-optimized instances and after a configuration change shifted partly to memory-optimized instances. Total instance-hours might stay flat, yet total cost rises because the resource mix and unit rates changed.

To analyze mix:

1. Group by `INSTANCE_TYPE` or `INSTANCE_TYPE_FAMILY`.
2. Compare quantity and cost across each group.
3. Check Region, platform, tenancy, and purchase option.
4. Correlate with configuration change timestamps.
5. Verify whether switching resource types delivered corresponding performance or SLA improvements.

### 8.2 Separating Recurring vs. One-Time Costs

A spike may not reflect a new steady-state run rate. Check `RECORD_TYPE` and lines related to fees, upfront charges, credits, refunds, or taxes.

Examples:
- Purchasing an upfront commitment creates a large charge in the purchase period.
- A refund can make the current period dip without indicating workload optimization.
- Credits can mask rising underlying usage.
- Taxes or billing adjustments may be unrelated to architectural changes.

Management reports should show both gross cost on the selected basis and relevant adjustments according to organizational finance policy.

## 9. Normalizing Costs by Business Activity

Total spend alone cannot measure efficiency. If order volume doubles while cloud spend grows 30%, unit efficiency may actually have improved.

Common normalization units:

| Unit | Formula | Best Suited For |
|---|---|---|
| Cost per request | Total relevant cost / request count | APIs, backend services |
| Cost per order | Platform cost / order count | E-commerce |
| Cost per active user | Cost / active users | SaaS, consumer apps |
| Cost per tenant | Cost / tenant count | Multi-tenant platforms |
| Cost per GB processed | Processing cost / GB data | Data platforms, ETL |
| Cost per build | CI/CD cost / build count | Development pipelines |

Example:

~~~text
Month A:
Cloud cost = 10,000 USD
Orders = 100,000
Cost per order = 0.10 USD

Month B:
Cloud cost = 12,000 USD
Orders = 150,000
Cost per order = 0.08 USD
~~~

Total cost rose 20%, yet cost per order dropped 20%. This may indicate improved efficiency. Still, check service quality, latency, error rates, and utilization to ensure lower unit cost did not come at the expense of degraded quality.

Business activity metrics usually live outside Cost Explorer. Combine Cost Explorer with CloudWatch, analytics systems, order counts, or product telemetry. Align exact time windows and rules for filtering out test traffic so denominators remain consistent.

## 10. Analyzing Reserved Instances and Savings Plans

Reserved Instances (RIs) and Savings Plans are financial commitments that lower costs for steady-state usage. They also change how reports should be read.

Questions to answer:

- Are purchased commitments being fully utilized by workloads?
- Does utilization align with plan expectations?
- Is workload coverage rising or falling?
- Do commitments match the Region, instance family, operating system, and scope?
- Are upfront or recurring fees causing period-over-period swings?
- Are new workloads running On-Demand while unused commitment capacity exists in a compatible scope?

Cost Explorer provides reports for RIs and Savings Plans, including utilization and coverage. Distinguish:

- Utilization: how much of the purchased commitment is being used.
- Coverage: the share of eligible workload usage covered by commitments.
- Amortized cost: commitment cost distributed over time.
- On-Demand equivalent: reference cost if eligible usage were billed at On-Demand rates; this is a comparison benchmark, not an actual invoice.

For example, a team sees low RI utilization alongside low workload coverage. That may indicate commitments were purchased for the wrong scope or size. Conversely, high utilization alongside low coverage suggests substantial remaining On-Demand usage and potential room for additional commitments.

Do not purchase more RIs or Savings Plans simply because a chart shows high On-Demand spend for one week. Before committing:
1. Confirm the workload is stable over the expected term.
2. Verify Region, family, platform, and scope applicability.
3. Review usage history and scaling plans.
4. Weigh potential savings against over-commitment risk.
5. Check architectural impact and workload portability.
6. Obtain approval from the budget owner.

## 11. Reading Cost Forecasts

Cost Explorer generates forecasts using historical data and AWS statistical models. Forecasts help spot trends, though they are not guarantees of the final invoice.

When using forecasts:

- Select the metric matching your governance objective.
- Check the forecast horizon and account scope.
- Inspect confidence intervals if the interface provides an estimation band.
- Account for seasonality, holidays, business campaigns, and batch schedules.
- Factor in known changes such as launching a new Region, onboarding tenants, or migrations.
- Refresh forecasts when new operational information arrives.

History-based forecasts cannot anticipate upcoming releases, marketing events, pricing updates, commitment purchases, or brand-new workloads. If an application is about to triple traffic, historical forecasts will underestimate spend.

### 11.1 Combining Forecasts and Budgets

A governance workflow might pair:

1. Cost Explorer forecasts to project trend trajectories.
2. AWS Budgets to enforce cost or usage thresholds.
3. SNS or approved notification channels to deliver alerts.
4. Runbooks to verify root causes before taking action.
5. Weekly variance reports comparing forecast against actuals.

A threshold alert does not automatically prove waste; it is a prompt to investigate. Likewise, forecasting under budget does not mean an architecture is already optimized.

## 12. Combining Cost Explorer with AWS Organizations and FinOps Governance

In multi-account setups, account structure should reflect sound governance boundaries: production workloads, non-production, shared services, security, log archives, or individual products.

A FinOps workflow can assign responsibilities as follows:

| Role | Responsibility |
|---|---|
| Platform/Cloud team | Design account structure, tagging, networking, and observability tooling |
| Application owner | Explain workloads, traffic, configurations, and deployment changes |
| Finance/FinOps | Standardize metrics, budgets, allocations, and reporting |
| Security | Ensure proper Billing data access controls and change governance |
| Engineering manager | Prioritize optimization actions and approve cost/performance trade-offs |

Establish a clear operating cadence:

- Daily: review anomaly alerts and investigate severe spikes.
- Weekly: review top service/account variances and action-item progress.
- Monthly: close period reconciliation, review budgets/forecasts, allocate shared costs, and review commitments.
- Quarterly: review account structure, tag taxonomy, Cost Categories, and optimization effectiveness.

This cadence is an operational baseline; adjust actual frequency to match workload velocity and risk profile.

## 13. Querying Cost Explorer with AWS CLI

The Cost Explorer API lets you automate aggregate queries and feed data into reporting pipelines. The example below queries costs by service and linked account across two completed months.

~~~bash
aws ce get-cost-and-usage \
  --region us-east-1 \
  --time-period Start=2026-09-01,End=2026-11-01 \
  --granularity MONTHLY \
  --metrics UnblendedCost AmortizedCost \
  --group-by Type=DIMENSION,Key=SERVICE Type=DIMENSION,Key=LINKED_ACCOUNT
~~~

Explanation:

- `Start` is inclusive.
- `End` is exclusive. In the example above, data covers September and October.
- `MONTHLY` produces one result bucket per month.
- `UnblendedCost` and `AmortizedCost` are returned separately.
- Grouping by `SERVICE` and `LINKED_ACCOUNT` identifies services per account.

A tag filter can be passed via a JSON file for version control.

File `filter.json`:

~~~json
{
  "Tags": {
    "Key": "Environment",
    "Values": ["prod"]
  }
}
~~~

Query strictly for the production environment:

~~~bash
aws ce get-cost-and-usage \
  --region us-east-1 \
  --time-period Start=2026-10-01,End=2026-11-01 \
  --granularity DAILY \
  --metrics UnblendedCost \
  --filter file://filter.json \
  --group-by Type=DIMENSION,Key=SERVICE
~~~

API responses typically follow this structure:
- `ResultsByTime`: queried time intervals.
- `Groups`: buckets by selected dimensions.
- `Keys`: dimension values in each group.
- `Metrics`: `Amount` and `Unit` for each metric.

When parsing results, convert `Amount` from string to numeric carefully and preserve `Unit`. Never sum different metrics or units. For multi-group queries, store raw responses alongside query parameters for reproducibility.

### 13.1 Forecasting via CLI

Example query forecasting unblended cost for December:

~~~bash
aws ce get-cost-forecast \
  --region us-east-1 \
  --time-period Start=2026-12-01,End=2027-01-01 \
  --metric UNBLENDED_COST \
  --granularity MONTHLY
~~~

Forecasts depend on historical data and metric/time-range support. Inspect responses, prediction intervals, and permission or date-range errors before publishing to reports.

### 13.2 IAM Permissions

The role executing queries needs appropriate Cost Explorer API permissions, for example:

- `ce:GetCostAndUsage`
- `ce:GetCostForecast`
- `ce:GetDimensionValues`
- `ce:GetTags`
- `ce:GetCostCategories`

Exact action names must match the APIs called by your application. Apply least-privilege IAM policies, attach roles to appropriate workloads or operators, and log access per organizational policy. Billing read access may also require account-level configuration; an IAM policy alone does not guarantee console Billing access is enabled.

Never embed long-lived access keys in scripts, notebooks, or repositories. Prefer IAM roles and temporary credentials.

## 14. When You Need Cost and Usage Data Exports or CUR

Cost Explorer is suited for aggregated analysis and interactive exploration. When deeper granularity is required, consider AWS Data Exports with Cost and Usage Report (CUR), including CUR 2.0 format where appropriate.

Scenarios warranting granular data exports:

- Querying many line-item attributes.
- Analyzing resource IDs when supported and included in the export.
- Joining cost data with inventory, owners, or internal datasets.
- Retaining long-term history in a custom data model.
- Processing millions of rows with Athena, Glue, or BI tools.
- Reconciling specific RI/Savings Plan applications or granular usage.

A typical pipeline looks like:

~~~text
AWS billing data
       |
       v
Data Exports / CUR
       |
       v
Amazon S3
       |
       +----> AWS Glue Data Catalog
       |
       v
Amazon Athena
       |
       +----> BI dashboard
       |
       +----> FinOps reports
       |
       +----> Cost allocation / unit economics
~~~

Design the pipeline with S3 access controls, encryption, retention, Athena permissions, and sensitive-data governance. Cost reports can expose account topology, workload names, business scale, and service adoption; restrict visibility on a need-to-know basis.

Cost Explorer and CUR may differ if scope, refresh timing, metrics, or line-item processing differ. When reconciling, document the exact configuration on both sides.

## 15. Practical Scenario: A 25% Monthly Cost Increase

An e-commerce platform running across multiple AWS accounts notices October spend is higher than September. Finance asks engineering to explain the jump and propose actions.

### 15.1 Step 1: Confirm the Figures

The FinOps team opens Cost Explorer and selects:
- Baseline period: 09-01 to 10-01.
- Current period: 10-01 to 11-01.
- Granularity: Monthly.
- Metric: AmortizedCost to evaluate economic trends including amortized commitments.
- Scope: entire payer account.
- Group by: `SERVICE`.

Illustrative output shows total spend rising from $12,000 to $15,000 USD, or 25%.

### 15.2 Step 2: Identify Top Contributors

Service breakdown table:

| Service | September | October | Difference |
|---|---:|---:|---:|
| EC2 | 6,000 USD | 8,100 USD | +2,100 USD |
| S3 | 2,400 USD | 2,700 USD | +300 USD |
| RDS | 1,800 USD | 1,900 USD | +100 USD |
| Data Transfer | 1,200 USD | 1,500 USD | +300 USD |
| Other | 600 USD | 800 USD | +200 USD |
| **Total** | **12,000 USD** | **15,000 USD** | **+3,000 USD** |

EC2 represents 70% of the total increase. The team investigates EC2 first.

### 15.3 Step 3: Decompose EC2

Filter `SERVICE = EC2` and group by `LINKED_ACCOUNT`. One production account drives most of the increase. Further group by `REGION`, `INSTANCE_TYPE`, and `USAGE_TYPE`.

Initial hypotheses:
- A release scaled up task/instance counts.
- Autoscaling added capacity to absorb traffic.
- A batch job ran longer.
- Instance types or purchase options changed.

The team correlates with deployment logs, CPU/memory metrics, request counts, and batch schedules. Data shows instance-hours rose 35% while the effective unit rate stayed nearly flat. Growth came primarily from volume.

### 15.4 Step 4: Check Business Efficiency

During the same period, order volume grew 50%. EC2 cost grew 35%, slower than order growth. Compute cost per order improved.

The team still checks:
- CPU and memory utilization.
- Idle instances during off-peak hours.
- Scale-in responsiveness.
- Error rates and latency.
- Whether batch jobs can shift to more appropriate schedules.

The conclusion is not "cost increases are bad." The conclusion is "compute rose due to volume supporting business growth; cost per order improved, though off-peak idle windows remain to optimize."

### 15.5 Step 5: Inspect Remaining Groups

- S3 rose $300 USD: inspect storage classes, object versioning, lifecycle rules, and data retrievals.
- Data Transfer rose $300 USD: inspect inter-AZ, inter-Region, internet egress, and cache hit ratio.
- RDS rose $100 USD: inspect instance-hours, storage, backups, and read replicas.
- Other rose $200 USD: group by `SERVICE` and `RECORD_TYPE` to spot new charges.

Every finding needs an owner and a measurable action. For example, "reduce non-production idle EC2 hours by 10%" is far better than "optimize EC2."

## 16. Variance Investigation Runbook

Use this runbook when total spend breaches thresholds or a bucket shows abnormal variance.

### 16.1 Validate

1. Verify account and organization scope.
2. Verify period, metric, granularity, and currency.
3. Confirm comparison periods have comparable length.
4. Record the data extraction timestamp.
5. Determine whether the increase is usage, fee, credit, refund, tax, or adjustment.

### 16.2 Narrow Down

1. Group by `SERVICE`.
2. Sort by absolute dollar difference.
3. Select top contributors.
4. Group by `LINKED_ACCOUNT`.
5. Drill down by `REGION`, `USAGE_TYPE`, `OPERATION`, or tags.
6. Inspect resource-level exports if Cost Explorer lacks needed granularity.

### 16.3 Identify Root Cause

Cross-check against:
- Release/deployment timelines.
- Autoscaling events and batch schedules.
- Traffic, request counts, and user volume.
- Instance/storage/database/network modifications.
- Region, AZ, replication, or backup changes.
- New purchases or expirations of RIs/Savings Plans.
- Discount, credit, or contract changes.
- Tag, account structure, or Cost Category changes.

### 16.4 Decide on Actions

Each action requires:
- Description of the verified root cause.
- Accountable owner.
- Expected savings and calculation method.
- Impact on performance, availability, security, and resilience.
- Target completion date.
- Before/after metrics.
- Rollback plan if service quality degrades.

Never cut replicas, backups, logging, encryption, or availability tiers to hit a cost target without a formal risk review. Cost optimization must preserve approved operational and security requirements.

## 17. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Comparing UnblendedCost with AmortizedCost | Wrong conclusions on increases/decreases | Use the same metric and state the basis |
| Comparing an incomplete month to a full month | Creates false variances | Compare equal elapsed days or closed periods |
| Summing UsageQuantity across different units | Meaningless usage totals | Group by usage type/unit |
| Looking only at percentage growth | Misses absolute dollar impact | Inspect both ΔC and Δ% |
| Treating forecasts as final invoices | Faulty budgeting | Use forecasts as conditional projections |
| Assuming all tags immediately appear in Cost Explorer | Missing groups or unallocated spend | Activate cost allocation tags and verify data |
| Assuming tags automatically split shared costs | Incomplete or wrong allocation | Define verifiable allocation drivers |
| Buying commitments off one week of usage | Over-commitment risk | Analyze long-term trends and workload roadmaps |
| Treating any cost increase as waste | Cutting in the wrong places | Normalize against business activity |
| Using Cost Explorer instead of CUR for every query | Missing line-item columns | Switch to Data Exports/CUR when detail is needed |
| Ignoring credits/refunds/taxes | Misinterpreting variances | Inspect RECORD_TYPE and reconcile with Billing |
| Failing to record report parameters | Reports cannot be reproduced | Save period, metric, filters, group by, and extraction timestamp |

## 18. Access Control and Protecting Cost Data

Cost data can reveal product scale, account structure, Regions, active systems, and growth trajectories. Treat Billing data as controlled internal information.

Principles:

- Use IAM roles with least-privilege Cost Explorer read permissions for analysts or automation workloads.
- Govern Billing access under organizational account policies.
- Separate permissions to view costs from permissions to alter billing/payment settings where needed.
- Never embed access keys in dashboards, scripts, or report files.
- For CUR/Data Exports, protect S3 buckets with Block Public Access, principal-restricted policies, encryption, and logging.
- Share dashboards only with groups who have a business need.
- Review access when staff change roles or leave the organization.

Cost Explorer is primarily for reading and analysis. Modifying resources to cut costs must still pass through change management, security review, and service impact checks.

## 19. Monthly Variance Report Checklist

Before publishing a report, confirm:

- [ ] Account/organization scope is explicitly documented.
- [ ] Baseline and current periods have comparable durations.
- [ ] Metric and granularity match across comparisons.
- [ ] ΔC and Δ% are calculated accurately.
- [ ] Top contributors are ranked by absolute impact.
- [ ] Groups with sharp percentage jumps are explained.
- [ ] `RECORD_TYPE`, credits, refunds, taxes, and fees are checked.
- [ ] Volume, rate, mix, and one-time items are separated.
- [ ] RI/Savings Plans impacts are evaluated.
- [ ] Unit economics are included where workloads tie to business metrics.
- [ ] Root-cause hypotheses are corroborated with operational telemetry.
- [ ] Each action has an owner, deadline, and measurement plan.
- [ ] Impact on performance, security, availability, and recovery is assessed.
- [ ] Query parameters and extraction timestamp are saved for reproducibility.

## 20. Practice Exercises

### Exercise 1: Calculate Variance

A workload has an August AmortizedCost of $8,000 USD and a September AmortizedCost of $9,600 USD.

Tasks:
1. Calculate the absolute difference.
2. Calculate the percentage change.
3. Write a one-sentence conclusion explicitly naming the metric and periods.

Answer:
- ΔC = 9,600 - 8,000 = $1,600 USD.
- Δ% = 1,600 / 8,000 × 100% = 20%.
- September amortized cost increased by $1,600 USD, or 20%, compared to August.

### Exercise 2: Prioritize Investigation

Three services changed as follows:

| Service | Baseline Period | Current Period |
|---|---|---|
| Compute | 20,000 USD | 22,000 USD |
| Storage | 1,000 USD | 1,500 USD |
| Network | 500 USD | 700 USD |

Task: choose which service to investigate first if the goal is explaining total spend growth.

Answer: Compute rose $2,000 USD, making it the largest absolute contributor. Storage rose 50% and Network rose 40%; their percentages are higher, but their dollar increases are $500 and $200 USD respectively. Start with Compute, then inspect Storage and Network according to risk or optimization goals.

### Exercise 3: UsageQuantity

A report shows 500 instance-hours, 800 GB-months, and 2 million requests.

Task: can these three quantities be summed into a single total usage figure?

Answer: No. They have different units. Analyze them separately or convert them via a clearly defined business metric.

### Exercise 4: Volume or Rate?

Compute cost rose from $4,000 to $5,000 USD. Usage rose from 800 to 1,000 units of the same type. Effective unit rate remained unchanged.

Answer: the cost increase is driven by volume. At a unit rate of $5 USD/unit, the volume effect is (1,000 - 800) × 5 = $1,000 USD; the rate effect is 0.

### Exercise 5: Choose a Metric

An organization just purchased an upfront RI and wants to evaluate average monthly economic cost.

Answer: check `AmortizedCost`, or `NetAmortizedCost` if aligned with net-cost policy. Also view `UnblendedCost` to understand the unblended charge recorded in the purchase period. Never compare the two metrics as though they mean the same thing.

### Exercise 6: Investigate Data Transfer

Data Transfer costs rose 40%. Name three dimensions or data sources to inspect.

Suggested answer:
- Group by `REGION` and `AZ` to inspect inter-Region/inter-AZ flows.
- Group by `USAGE_TYPE` and `OPERATION` to pinpoint the transfer type.
- Cross-check network architecture, NAT Gateways, load balancers, cache hit ratio, and actual traffic.

### Exercise 7: Evaluate Cost per Order

Cloud costs rose 10%, while orders rose 25%.

Answer: assuming cost and order scopes align, cost per order decreased. The new relative index is 1.10 / 1.25 = 0.88, roughly a 12% reduction. Check service quality and other component costs before concluding overall efficiency improved.

### Exercise 8: Analyze Forecast

Month-end forecast is 15% above budget, but a major marketing campaign ends in three days.

Answer: verify the campaign schedule and actual consumption, build a post-campaign projection, update the forecast, and monitor actuals. Do not ignore the alert merely expecting the campaign to end; confirm whether workloads scale in and spend drops after the event.

## 21. Self-Check Questions

1. What is Cost Explorer primarily used for?
2. Why is Cost Explorer not a real-time telemetry tool?
3. How do UnblendedCost and AmortizedCost differ?
4. When should NetAmortizedCost be used?
5. Why should you avoid summing UsageQuantity across multiple Usage Types?
6. What question does the SERVICE dimension answer?
7. How does Filter differ from Group by?
8. Why must cost allocation tags be activated in Billing?
9. How do Cost Categories help FinOps?
10. What are the formulas for absolute and percentage variance?
11. What should you do when the baseline period cost is 0?
12. Why examine both ΔC and Δ%?
13. How do volume, rate, and mix differ?
14. What can cost per order explain when total cloud cost increases?
15. What two perspectives do RI utilization and coverage reflect?
16. Why is a forecast not the final invoice?
17. When should you use Data Exports/CUR instead of Cost Explorer alone?
18. What metadata must be saved to reproduce a report?
19. Why check RECORD_TYPE when costs fluctuate?
20. What governance elements should every cost optimization action include?

Suggested answers:

1. Interactive analysis of cost and usage over time and across dimensions.
2. Billing data is aggregated and updated with latency.
3. AmortizedCost spreads upfront charges across the commitment term; UnblendedCost reflects unblended charges when recorded.
4. When viewing amortized costs net of eligible discounts.
5. Different usage types have different measurement units.
6. Which AWS service is contributing costs.
7. Filter narrows the dataset; group by splits data into buckets.
8. So eligible tags appear as cost allocation dimensions.
9. They group costs by business rules such as BU, product, or environment.
10. ΔC = C1 - C0; Δ% = ΔC / C0 × 100%.
11. Report the absolute dollar amount and flag it as a new cost/group; never divide by 0.
12. To see both financial dollar impact and relative magnitude of change.
13. Volume is usage quantity; rate is unit price; mix is the composition of resource/usage types.
14. Whether cost per unit of business output improved or worsened.
15. Utilization measures commitment usage; coverage measures the share of eligible workload covered by commitments.
16. Forecasts rely on historical data and cannot know every upcoming change.
17. When line-item, resource-level detail, or custom analytics are required.
18. Period, metric, granularity, scope, filters, group by, and extraction timestamp.
19. To distinguish usage from fees, credits, refunds, taxes, and adjustments.
20. Verified root cause, owner, expected savings, deadline, measurement plan, and risk assessment.

## 22. Official References

The following AWS documentation provides a starting point to verify UI behavior, metrics, APIs, and feature updates:

- [What is AWS Cost Explorer?](https://docs.aws.amazon.com/cost-management/latest/userguide/ce-what-is.html)
- [Exploring your data using Cost Explorer](https://docs.aws.amazon.com/cost-management/latest/userguide/ce-exploring-data.html)
- [Cost Explorer metrics](https://docs.aws.amazon.com/cost-management/latest/userguide/ce-advanced.html)
- [Using the Cost Explorer API](https://docs.aws.amazon.com/cost-management/latest/userguide/ce-api.html)
- [GetCostAndUsage API reference](https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API_GetCostAndUsage.html)
- [GetCostForecast API reference](https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API_GetCostForecast.html)
- [Forecasting costs with Cost Explorer](https://docs.aws.amazon.com/cost-management/latest/userguide/ce-forecast.html)
- [Cost allocation tags](https://docs.aws.amazon.com/cost-management/latest/userguide/activating-tags.html)
- [Organizing costs using AWS Cost Categories](https://docs.aws.amazon.com/cost-management/latest/userguide/cost-categories.html)
- [Managing your costs with AWS Budgets](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html)
- [Detecting unusual spend with AWS Cost Anomaly Detection](https://docs.aws.amazon.com/cost-management/latest/userguide/manage-ad.html)
- [What is the AWS Cost and Usage Report?](https://docs.aws.amazon.com/cur/latest/userguide/what-is-cur.html)
- [AWS Data Exports](https://docs.aws.amazon.com/cur/latest/userguide/dataexports.html)
- [AWS Organizations consolidated billing](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/consolidated-billing.html)

AWS documentation evolves over time and varies by account type. When deploying in production, verify supported metrics, dimensions, IAM permissions, API scope, and features available in your organization's accounts and Regions.
