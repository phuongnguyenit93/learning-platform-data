# Unit Economics, Cost Anomaly Detection, and Resource Cleanup

FinOps does not stop at reading invoices or trying to cut total AWS spend. Organizations need to know how much infrastructure each product, customer, transaction, or unit of work consumes; detect when spending deviates from normal behavior; and remove capacity that no longer delivers value. These three capabilities connect directly: **unit economics** measures workload economic efficiency, **cost anomaly detection** spots unusual shifts, and **resource cleanup** turns data into operational action.

A rising bill is not necessarily a problem. If orders grow faster than spend, cost per order may actually be dropping. Conversely, a flat bill can mask one service surging while another drops. Therefore, evaluate spend alongside output volume, service quality, utilization, and ownership.

This lesson establishes how to measure costs per business unit, allocate shared costs, configure AWS Cost Anomaly Detection, investigate root causes, and clean up resources safely. Services such as AWS Cost Explorer, Cost and Usage Reports, Cost Categories, AWS Budgets, AWS Compute Optimizer, and Cost Optimization Hub are brought together into one unified FinOps workflow.

## 1. Learning Objectives

After this lesson, learners will be able to:

- Explain unit economics and pick suitable denominators such as orders, successful transactions, active users, tenants, or requests.
- Build a consistent cost numerator from direct costs, shared costs, and allocated components.
- Use cost allocation tags, Cost Categories, Cost Explorer, and Cost and Usage Reports to analyze costs by accountability.
- Distinguish unblended, net unblended, amortized, and net amortized costs when measuring efficiency.
- Configure monitors and alert subscriptions for AWS Cost Anomaly Detection.
- Distinguish anomaly detection from AWS Budgets and handle limits around latency, history, and monitoring scope.
- Investigate anomalies by service, account, Region, and usage type, correlating billing data with engineering changes.
- Use Compute Optimizer and Cost Optimization Hub to uncover idle or rightsizeable resources.
- Design a workflow for inventory, owner confirmation, data protection, stop/quarantine, and resource deletion.
- Measure realized savings and feed results back into the FinOps loop.

## 2. Unit Economics in AWS Environments

### 2.1 Concept

Unit economics describes the cost and economic value tied to one unit of output for a product or workload. Rather than asking only "how much did AWS cost this month?", product and engineering teams need to answer:

- How much infrastructure cost goes into one completed order?
- How much monthly cost does one active user generate?
- How much more than average does a heavy tenant consume?
- How much does one successful request or data processing job cost?
- As customer count grows, does cost per customer fall or rise?

A simple metric:

\[
\text{Unit cost} = \frac{\text{Costs allocated to the workload}}{\text{Number of output units}}
\]

For example, an application spends $18,000 USD in a month and completes 120,000 orders:

\[
\frac{18,000}{120,000} = 0.15\text{ USD/order}
\]

The following month, spend rises to $21,000 USD while completed orders rise to 150,000:

\[
\frac{21,000}{150,000} = 0.14\text{ USD/order}
\]

Total cost grew 16.7%, yet output grew 25% and unit cost fell roughly 6.7%. Looking solely at the total bill might have led operators to mistakenly conclude efficiency worsened.

### 2.2 Choosing the Right Output Unit

The denominator must reflect real value delivered by the product, be reliably measurable, and resist distortion by implementation artifacts.

| Workload Type | Appropriate Unit Economics | Denominators to Avoid |
|---|---|---|
| E-commerce | Cost per completed order, per successful payment transaction | Total page views when orders are the business goal |
| Multi-tenant SaaS | Cost per active tenant, per active user, per successful request | Total registered tenants including inactive ones |
| API platform | Cost per 1,000 successful requests or per API product | Total requests including non-value internal retries |
| Data platform | Cost per TB processed, successful pipeline, or served table | Count of launched jobs even when jobs fail |
| Machine learning | Cost per 1,000 inferences, tokens, or completed training runs | Raw invocations without distinguishing useful outputs |
| Media processing | Cost per video minute, GB of media, or completed asset | Raw uploaded bytes never processed |
| Internal developer platform | Cost per served workload/team/project | Count of IAM accounts or provisioned user logins |

A single product may track multiple metrics in parallel. For example, an API platform tracks cost/request, cost/1,000 successful requests, and cost/tenant to separate engineering efficiency from customer consumption.

### 2.3 Defining Cost Scope

The numerator must remain consistent across periods. A complete model may include:

    Workload cost
      = direct infrastructure cost
      + allocated shared platform cost
      + allocated network and security cost
      + allocated observability and backup cost
      + applicable software/license cost

Direct costs attach directly to a workload—such as a dedicated EC2 instance, dedicated database, or clearly owned S3 bucket. Shared costs serve multiple workloads—such as NAT Gateways, transit networking, logging platforms, shared Kubernetes clusters, support plans, or platform engineering teams.

Not every unit economics report must include full corporate overhead in the numerator. State boundaries explicitly:

- **Infrastructure unit cost:** includes only AWS services and direct infrastructure spend.
- **Platform unit cost:** adds allocated shared platform spend.
- **Fully loaded unit cost:** adds software licenses, support, operational labor, and overhead per finance policy.

If this month's dashboard uses net amortized cost while last month's used unblended cost, trends can shift due to commitment accounting rather than workload behavior. Label the cost basis clearly in metric names or metadata.

### 2.4 Choosing the Right Cost Basis

Cost Explorer offers multiple cost metrics:

| Cost Basis | Meaning | When to Use |
|---|---|---|
| Unblended cost | Usage cost at unblended values; reservation fees/discounts may appear on separate line items | Line-item analysis and reconciling usage/charges |
| Net unblended cost | Cost after applicable discounts | Tracking post-discount spend; Cost Anomaly Detection analyzes net unblended data |
| Amortized cost | Spreads upfront and recurring reservation fees across commitment usage periods | Comparing workload costs across periods with RIs/Savings Plans |
| Net amortized cost | Amortized commitment costs reflecting applicable discounts | Unit economics and post-discount efficiency benchmarking |

No single cost basis fits every report. Accounting may reconcile invoice/cash timing; FinOps amortizes commitments to measure effective cost; anomaly monitors analyze net unblended per AWS's model. When comparing periods, match cost basis, time range, filters, currency, and treatment of credits/refunds/taxes.

### 2.5 Distinguishing Fixed Costs from Variable Costs

- **Fixed costs** remain relatively steady over an interval, such as baseline EC2, provisioned databases, cluster control planes, or fixed endpoints.
- **Variable costs** scale with usage, such as requests, data transfer, GB processed, log ingestion, I/O, or storage growth.
- **Step costs** jump at capacity thresholds—for example, adding a node, shard, replica, or NAT Gateway when load exceeds capacity.

Separating these three helps predict behavior as volume scales. When fixed costs are high and variable costs are low, unit cost typically drops with scale. If variable costs climb faster than output, unit economics can degrade due to data transfer, retries, log volume, or query patterns.

## 3. Collecting and Allocating Cost Data

### 3.1 Cost Allocation Tags

Tags are key/value pairs attached to AWS resources. A structured tag set attributes spend by product, environment, owner, and cost center:

| Tag Key | Example Values | Purpose |
|---|---|---|
| Application | commerce-api | Product or workload |
| Environment | production, staging, dev | Distinguish environments |
| Owner | team-payments | Accountable team |
| CostCenter | CC-1042 | Financial reconciliation |
| BusinessUnit | retail | Business-unit allocation |
| DataClass | critical, internal | Guides retention and controls |
| Lifecycle | ephemeral, persistent | Supports cleanup workflows |

AWS provides both AWS-generated and user-defined cost allocation tags. Both must be activated individually in Billing and Cost Management before appearing in Cost Explorer or cost allocation reports. After attaching/activating, tags can take up to 24 hours to appear in the Billing console.

Cost allocation reports include both tagged and untagged spend; at billing cycle close, report totals must reconcile against the Bills page and period billing reports. Untagged resources do not vanish from totals; they land in the unallocated bucket. Never store sensitive data, PII, or secrets in tags.

A frequent mistake is attaching tags while forgetting to activate them as cost allocation tags. The tag appears on the resource yet remains missing as an allocation dimension in Cost Explorer. Govern both tagging policies and the Billing activation step.

### 3.2 Cost Categories

Cost Categories map cost line items into business buckets via rules. Available classification dimensions include:

- AWS account.
- Cost allocation tag.
- Charge type such as credit, refund, or reservation fee.
- Service.
- Region.
- Usage type.
- Billing entity such as AWS or AWS Marketplace.

Rules evaluate sequentially. When a line item matches multiple rules, the first matching rule determines the category value. Place specific rules ahead of general rules and configure a default value so unmatched items never go unnoticed.

For instance, an organization has Engineering, Marketing, and Operations teams. Costs tagged `Application=commerce-api` or `Application=payments` map to Engineering; `Application=campaign-site` maps to Marketing; everything else maps to Operations. Categories can form hierarchies by business unit, application, or cost center.

### 3.3 Allocating Shared Costs

Not every charge maps directly to a single team. Shared networking, logging, security tooling, or platform clusters require an explainable allocation driver:

| Shared Cost | Suggested Allocation Driver |
|---|---|
| Shared NAT/data transfer | GB processed or bytes per workload |
| Shared Kubernetes cluster | vCPU-hours, memory GB-hours, or namespace requests |
| Central logging | GB of logs ingested or retained GB-months |
| Shared database | Query units, connection time, or consumed storage |
| Internal platform team | Served workload count or capacity share |
| Support plan | Share of AWS spend per finance policy |

Do not default to even splits when consumption varies widely. If one team generates 70% of log volume, allocating 70% of logging costs by ingested GB reflects causality far better than splitting equally across five teams.

Cost Categories support split charge rules for shared costs using:

- **Proportional:** weighted by each target's own cost share.
- **Fixed:** by organization-defined percentages.
- **Even split:** divided equally across targets.

Important note: split charges appear on the Cost Categories details page. These split allocations do not appear in and do not modify data in Cost Explorer, Cost and Usage Reports, or other AWS Cost Management tools. Use them as a governance allocation layer; if line-item unit economics require split numbers, implement the allocation in your own data pipeline/reporting layer.

### 3.4 Cost Explorer and Cost and Usage Reports

Cost Explorer excels at trend visualization and interactive slicing by service, account, Region, usage type, tag, and cost category. It is the starting point for investigating an unexpected spike.

AWS Cost and Usage Reports (CUR) supply deeper cost/usage granularity delivered to S3. Reports support hourly, daily, or monthly granularity segmented by product/resource and tags. AWS updates reports at least daily; a new export can take up to 24 hours for initial delivery. Intra-month files update cumulatively and adjust until charges are finalized.

For unit economics, Athena or BI tools can join CUR with product datasets:

    AWS CUR / Data Exports
          |
          +---- cost, usage type, account, Region, tag
          |
    Product analytics / order ledger / tenant usage
          |
          +---- order_id, tenant_id, request_count, success_count
          |
    Allocation model
          |
    Unit cost by product / tenant / business unit

Do not join cost data with product data solely by date when workloads span multiple Regions, accounts, or environments. Join on keys such as account, Region, resource tag, usage type, and time window to prevent misattribution.

### 3.5 Normalizing Data Before Calculating

Before computing unit cost:

1. Select a consistent cost basis.
2. Align time windows to identical timezones and period boundaries.
3. Define treatment for credits, refunds, taxes, support, and Marketplace.
4. Define shared cost allocation rules.
5. Check tag coverage and unallocated spend.
6. Pull denominators from reconciled business systems.
7. Clearly label figures as estimated, provisional, or finalized.

Some usage/cost lines update retroactively after occurrence. Never lock monthly unit economics off unfinalized intra-month figures. Maintain consistent data finality when comparing periods.

## 4. Building Unit Economics Metrics

### 4.1 Cost per Transaction

Example monthly cost breakdown for a payments system:

| Component | Cost |
|---|---:|
| EC2/ECS application | 4,000 USD |
| RDS/Aurora | 3,500 USD |
| Network/NAT/ALB | 1,200 USD |
| S3/backups | 500 USD |
| Logs/metrics/security | 800 USD |
| Shared platform allocation | 1,000 USD |
| **Total** | **11,000 USD** |

With 2,000,000 successful transactions:

\[
\text{Cost per transaction} = \frac{11,000}{2,000,000} = 0.0055\text{ USD}
\]

If the denominator includes all requests—including retries and failures—the metric can appear artificially low because the denominator grows without adding business value. Measure separately:

- Cost per attempted transaction.
- Cost per successful transaction.
- Cost per failed transaction when analyzing waste.

### 4.2 Cost per Tenant

Multi-tenant SaaS often relies on shared platforms. Total monthly cost can follow:

    Total cost = direct tenant cost + shared platform cost

Example:

- Direct tenant-specific costs: $6,000 USD.
- Shared platform costs: $9,000 USD.
- 300 active tenants.

If splitting shared costs evenly:

    Shared cost per tenant = 9,000 / 300 = 30 USD

A tenant with $12 USD of direct workload spend carries a fully allocated cost of $42 USD. However, even splits make sense only when tenants consume roughly similar capacity. When consumption diverges, allocate by requests, storage, vCPU-hours, or data egress.

Avoid forcing one driver onto every shared cost. Allocating logging by GB ingested, networking by GB transferred, and control planes by workload count often makes more sense than one flat ratio for everything.

### 4.3 Cost per Active User

    Cost per active user = total allocated workload cost / monthly active users

Define "active user" unambiguously: someone who logged in, completed at least one meaningful action, or generated a transaction? Changing definitions across months breaks trend comparability.

For freemium products, track both cost per active user and cost per paying user. If free users consume heavy compute without converting, cost per paying user climbs even if cost per active user looks flat.

### 4.4 Contribution Margin and Pricing

Unit economics can pair infrastructure spend with revenue:

\[
\text{Contribution margin per unit} =
\text{Revenue per unit} - \text{Variable cost per unit}
\]

AWS spend is typically only part of variable cost. For a fully loaded margin, include payment processing, support, licenses, customer success, and other costs per finance policy. Never label AWS cost per order as gross margin if the numerator covers only infrastructure.

### 4.5 Evaluating Trends

Track simultaneously:

- Total spend.
- Output volume.
- Unit cost.
- Service availability/latency/error rates.
- Capacity headroom.
- Cost allocation coverage.

Lower unit cost accompanied by rising error rates or SLO-breaching latency is not a successful optimization. Downsizing instances in a way that triggers retries can make effective cost per request higher.

### 4.6 Dashboard Model

A product-level FinOps dashboard can include:

| Group | KPIs |
|---|---|
| Spend | Net amortized cost, actual month-to-date, month-end forecast |
| Unit economics | Cost/order, cost/active tenant, cost/1,000 requests |
| Efficiency | CPU/memory utilization, cache hit ratio, requests per vCPU-hour |
| Reliability | Availability, p95/p99 latency, error rate, restore readiness |
| Allocation | % tagged cost, unallocated cost, shared cost by driver |
| Optimization | Estimated savings, realized savings, pending recommendations |
| Anomalies | Anomaly count, USD impact, time-to-detect, time-to-triage |

Assign an owner to each KPI. If unit cost rises, the product owner verifies output volume; the platform owner inspects capacity/networking; FinOps verifies cost basis and allocation.

## 5. AWS Cost Anomaly Detection

### 5.1 Capabilities

AWS Cost Anomaly Detection uses machine learning models to spot unusual spend relative to historical patterns. Models account for weekly/monthly seasonality and organic growth trends to reduce false positives.

An anomaly does not automatically mean a bug or breach occurred. A marketing campaign, new release, migration, traffic surge, or new Region rollout can produce a valid spend increase. Detection simply flags spend diverging from expected patterns; operators must diagnose the cause and choose the response.

Cost Anomaly Detection analyzes net unblended cost data. Once billing data is processed, detection runs roughly three times per day. Because Cost Explorer data can lag up to 24 hours, an anomaly may be detected up to ~24 hours after usage occurs. A new monitor can take up to 24 hours to begin detecting; a newly active service requires 10 days of historical service usage data before anomaly detection begins for that service.

This is not a spending blocker, rate limiter, or per-API-call real-time alert.

### 5.2 Prerequisites and Scope

Cost Anomaly Detection is part of Cost Explorer, so Cost Explorer must be enabled with appropriate IAM permissions. Cost monitors and alert subscriptions live in the account that creates them. Monitors for linked accounts, cost allocation tags, and cost categories can only be created from the management account under AWS Organizations.

Cost Anomaly Detection does not monitor standard third-party AWS Marketplace products/services, except third-party foundation models on Amazon Bedrock. To track Marketplace charges, use AWS Budgets with the Billing Entity filter or analyze billing exports directly.

### 5.3 AWS-Managed Monitors vs. Customer-Managed Monitors

AWS supports two monitor types:

| Monitor | How It Works | Best Suited When |
|---|---|---|
| AWS-managed | Automatically tracks all values in the chosen dimension and includes new accounts/tags/categories | Broad coverage with minimal maintenance is desired |
| Customer-managed | Selects specific values—up to 10 accounts or tag values per monitor | Monitoring a small subset or configuring distinct thresholds/groups |

Primary dimensions:

- AWS services.
- Linked accounts.
- Cost allocation tags.
- Cost Categories.

An AWS-managed monitor tracks up to 5,000 values in a dimension; if more exist, it monitors the top 5,000 by total spend. Customer-managed monitors allow up to 10 selected values within supported dimensions. Customer-managed AWS services monitors are not supported.

AWS-managed monitors fit organization-wide coverage. Customer-managed monitors fit project teams, critical production accounts, or teams requiring custom thresholds. Avoid overlapping monitors on the same dimension if they create duplicate alerts.

Alert subscriptions attached to an AWS-managed monitor apply a single threshold across all monitored values. If you need custom notification routing per account/tag value, pair with AWS User Notifications using JSON filtering patterns.

### 5.4 Alert Subscriptions and Thresholds

After creating a monitor, attach at least one alert subscription specifying recipients and delivery channels.

Frequency options:

- **Individual alerts:** sent as anomalies are detected; requires an Amazon SNS topic.
- **Daily summaries:** email summarizing the previous day's top 10 anomalies ranked by cost impact.
- **Weekly summaries:** email summarizing anomalies across the week.

Thresholds control alert delivery, not whether the model detects an anomaly. Two threshold types exist:

- **Absolute threshold:** alerts when total cost impact meets or exceeds a USD amount.
- **Percentage threshold:** alerts when total impact percentage meets or exceeds a set percentage.

You can combine both thresholds with `AND` or `OR`. Anomalies below thresholds still appear under Detected anomalies; only notification delivery is filtered by thresholds.

For example, a FinOps team wants alerts whenever impact exceeds $500 USD or exceeds 100%. Combining both thresholds with `OR` prevents missing large absolute-dollar anomalies or sharp relative spikes on smaller baseline workloads.

### 5.5 Root Cause Analysis

Anomaly details rank root causes by USD contribution across four dimensions:

- AWS service.
- AWS account.
- Region.
- Usage type.

Details typically show expected spend, actual spend, total impact, impact percentage, duration, monitor, and an anomaly details link. Severity reflects statistical deviation from historical patterns, not solely raw dollar amounts.

Example:

| Dimension | Value |
|---|---|
| Service | Amazon EC2 |
| Account | production |
| Region | ap-southeast-1 |
| Usage type | BoxUsage:m7i.large |
| Expected spend | 300 USD |
| Actual spend | 1,300 USD |
| Total impact | 1,000 USD |
| Impact percentage | 333.3% |

This illustrates how to read an anomaly. Root cause identifies only the top-contributing dimensions; you still need resource IDs, deployments, CloudTrail, and metrics to pinpoint the exact cause.

### 5.6 EventBridge Integration

Cost Anomaly Detection integrates with EventBridge. Rules can match Anomaly Detected events from source `aws.ce` and route them to SNS, Lambda, incident workflows, or internal chatops. Events can include anomaly ID, monitor ARN, impact, root cause, account, Region, service, usage type, and anomaly details link.

A sound processing flow:

    Cost Anomaly Detection
             |
         EventBridge
             |
      Filter by impact/severity
             |
        SNS / Lambda
             |
       FinOps incident
             |
    Triage + owner + action

EventBridge orchestrates notifications and workflows. Never configure a rule to automatically terminate resources solely because an anomaly fired; enforce owner verification, resource state checks, data protection, and approvals.

## 6. Distinguishing Anomaly Detection, Budgets, and Cost Monitoring

| Tool | Primary Question | Mechanism |
|---|---|---|
| Cost Anomaly Detection | Did spend deviate from historical patterns? | Machine learning, seasonality, and root cause |
| AWS Budgets | Did spend/usage breach set limits or forecasts? | Actual or forecasted thresholds |
| Cost Explorer | Where did spend originate and how did it shift? | Historical slicing by dimension/filter |
| CUR/Data Exports | Which line items generated cost/usage? | Granular data for querying and reconciliation |
| CloudWatch | Are application/resource metrics behaving abnormally? | Metrics, logs, alarms |
| Compute Optimizer | Are resources over-provisioned or idle? | Utilization analysis and recommendations |

AWS Budgets alerts on actual or forecasted spend exceeding a USD amount or budget percentage. Budgets suit fixed financial caps, whereas Cost Anomaly Detection catches unexpected deviations relative to baselines. Use both:

- Budgets enforce monthly/quarterly/annual limits.
- Anomaly Detection catches unexpected spikes.
- Cost Explorer/CUR isolates services, usage types, and line items.
- CloudWatch/CloudTrail identifies runtime changes and actors.

Never treat a budget alert as root-cause detection. An account can breach budget due to approved growth; an anomaly can occur while total spend still sits under overall budget.

## 7. Cost Anomaly Investigation Workflow

### 7.1 Step 1: Confirm the Signal

Upon receiving an alert:

1. Open the anomaly details link.
2. Check start time, end time, and ongoing/resolved status.
3. Review expected spend, actual spend, total impact, and impact percentage.
4. Check monitor type, account, service, Region, and usage type.
5. Check whether the shift aligns with an approved release, migration, campaign, or capacity plan.

If recent cost data is still settling, do not draw final conclusions from provisional charts. Compare periods on identical cost bases and recheck once billing data updates.

### 7.2 Step 2: Analyze Root Cause

Use Cost Explorer to filter by:

- Service and usage type.
- Linked account.
- Region and Availability Zone if relevant.
- Cost allocation tag or Cost Category.
- Operation, charge type, and resource where supported.

Compare the anomaly date against prior days, matching days of the week, and comparable cycles. Determine whether spend rose due to quantity, unit rate, resource count, data transfer, requests, storage, commitments, or credits/refunds.

### 7.3 Step 3: Correlate with Engineering Changes

Combine:

- CloudTrail to find create/modify/scale/launch API calls.
- Deployment logs, release pipelines, and change requests.
- CloudWatch metrics for CPU, requests, concurrency, bytes, queue depth, and errors.
- Application logs for retry loops, bot traffic, or query surges.
- Tags/owners to identify the accountable team.
- CUR/Data Exports for usage types, operations, and resource-level costs.

An EC2 anomaly can stem from autoscaling, a new instance family, an abandoned test environment, or cryptomining. A NAT anomaly can stem from data transfer, retries, or misrouted traffic. A CloudWatch anomaly can stem from log spikes, unbounded retention, or custom metric cardinality growth.

### 7.4 Step 4: Classify the Cause

| Cause Category | Signals | Response |
|---|---|---|
| Legitimate growth | Requests/orders/users rose alongside campaigns | Update forecasts and unit economics |
| Architectural change | Added Region, replicas, Multi-AZ, or migration | Validate business case and updated estimate |
| Misconfiguration | Oversized instances, extra NATs, wrong log retention | Fix configuration and check for regressions |
| Application bug | Retry loops, cache misses, heavy query scans, runaway jobs | Roll back/fix code and bound workload |
| Abuse or compromise | Unfamiliar resources, new Regions, sudden GPU/compute spikes | Trigger security incident, preserve evidence, isolate per runbook |
| Billing/data issue | Cost report spikes while usage telemetry stays flat | Check AWS Health/Support and await data confirmation |

### 7.5 Step 5: Mitigate Impact and Monitor

Select actions matching the cause:

- Stop broken batch jobs or cap concurrency.
- Scale down temporary capacity per capacity plans.
- Remove confirmed unused resources.
- Block abusive traffic or fix retry/backoff logic.
- Update routes/caches to cut data processing.
- Escalate to security incident response if compromise is suspected.

Never shut down a database, NAT Gateway, endpoint, or instance solely because spend is high. Check dependencies, RTO, DR, data durability, and owner before making changes. Afterward, monitor spend and application metrics to confirm the anomaly ends.

### 7.6 Step 6: Document and Improve

Log a record for every anomaly:

| Field | Contents |
|---|---|
| Anomaly ID | ID from Cost Anomaly Detection |
| Owner | Responding team |
| Root cause | Service/account/Region/usage type and verified cause |
| Business context | Release, campaign, migration, or incident |
| Cost impact | USD and percentage |
| Action | Remediation performed |
| Realized savings | Actual spend reduction post-action, if applicable |
| Prevention | Additional budgets, alarms, quotas, tags, guardrails, or tests |

Submit appropriate feedback assessments on anomaly details once confirmed whether an anomaly was a true issue or benign. Feedback improves detection accuracy over time.

## 8. Finding Optimization Opportunities with Compute Optimizer and Cost Optimization Hub

### 8.1 AWS Compute Optimizer

Compute Optimizer analyzes configurations and utilization metrics to produce rightsizing or idle-resource recommendations. Recommendations rely on historical telemetry; they do not inherently know upcoming business plans, seasonality, or future workloads.

Idle recommendations currently cover multiple resource types:

- EC2 instances and EC2 Auto Scaling groups.
- EBS volumes.
- ECS services on Fargate.
- Aurora and RDS databases.
- NAT Gateways.
- DynamoDB provisioned tables.
- ElastiCache, MemoryDB, and DocumentDB.
- WorkSpaces.
- SageMaker endpoints.

Recommendations refresh daily. Default lookback is commonly 14 days, with exceptions such as 32 days for EBS/NAT attachment status and 63 days for WorkSpaces connection activity. For some resources like ElastiCache, recommendations may take longer to appear after opting in.

Idle criteria vary by resource type. Examples:

- EC2 idle evaluation inspects peak CPU and network I/O over the lookback window.
- Unattached EBS is identified by attachment status, while idle volumes evaluate read/write activity.
- Fargate services inspect CPU and memory.
- RDS/Aurora inspect database connections, CPU, and IOPS.
- NAT Gateways inspect state, route table associations, and packet/connection activity.

Never rely on a single CPU threshold to declare every resource valueless.

### 8.2 Rightsizing Recommendations

Compute Optimizer recommends resizing instance types/sizes, EBS volumes, ECS services, or RDS DB instances. For EC2, recommendations evaluate CPU, memory (when metrics exist), networking, disk, and workload patterns. Memory metrics must be supplied via CloudWatch Agent or supported sources.

Lookback periods can be 14, 32, or 93 days. 14 and 32 days carry no extra fee; 93 days requires paid Enhanced Infrastructure Metrics. For workloads with month-end cycles, 32 days captures patterns better than 14 days.

Never look only at average CPU. Check peaks/p95/p99, memory, networking, EBS throughput, queue depth, latency, burstable CPU credits, and batch schedules. An instance with low average CPU that needs high bursts during billing runs may not safely tolerate aggressive downsizing.

### 8.3 AWS Cost Optimization Hub

Cost Optimization Hub aggregates and prioritizes recommendations across accounts and Regions, spanning rightsizing, idle resource deletion, Savings Plans, and Reserved Instances. The Hub calculates estimated savings under your commercial terms such as RIs/Savings Plans and deduplicates overlapping recommendations so savings are never double-counted.

For example, an EC2 instance might qualify for both an idle stop recommendation and a rightsizing recommendation. You cannot both stop an instance and save additional money by rightsizing it over the same hours. Cost Optimization Hub selects the higher-savings action in its aggregate math instead of summing both.

The Hub refreshes recommendations daily and can take up to 24 hours to import all recommendations after opt-in. With Organizations, the management account can enable coverage across member accounts.

Notable new capability: starting November 17, 2026, Cost Optimization Hub allows stopping idle EC2 instances directly from the Savings opportunities page. The stop action executes using the operator's permissions and displays a confirmation dialog showing potential data loss and ongoing costs. Both Cost Optimization Hub and Compute Optimizer must be enabled for idle recommendations.

### 8.4 Reading Savings Estimates Accurately

Estimated monthly savings represent projected potential, not realized cash savings. Values may reflect On-Demand or after-discount pricing depending on savings estimation preferences and resource type. Cost Optimization Hub factors in existing RIs/Savings Plans and deduplicates overlapping recommendations, yet actual savings still depend on post-change usage.

Measure realized savings by comparing pre/post spend normalized for output volume, time, Region, discounts, and architectural changes. If traffic dropped 40% the month after rightsizing, do not credit the entire bill drop to rightsizing.

## 9. Safe Resource Cleanup Workflow

### 9.1 Principles

Cleanup must rely on inventory, ownership, dependencies, and data policies. A resource with zero traffic for 14 days is not automatically useless: it could be a DR standby, month-end batch system, quarterly test environment, or forensic/compliance hold.

Follow this workflow:

    Discover
       |
    Identify owner and purpose
       |
    Check metrics, dependencies and schedule
       |
    Confirm backup / retention / recovery
       |
    Notify owner and obtain approval
       |
    Stop or quarantine first when possible
       |
    Observe impact and billing
       |
    Delete explicitly after confirmation
       |
    Verify resource and cost removal

### 9.2 Inventory and Ownership

Combine data sources:

- AWS Resource Explorer or AWS Config for resource inventory.
- Resource Groups Tagging API to query resources by tags.
- AWS Organizations and account inventories to identify accounts/owners.
- Cost Explorer/CUR to catch cost-bearing untagged resources.
- Compute Optimizer/Cost Optimization Hub for idle and rightsizing candidates.
- CloudTrail to trace principals that created or modified resources.

Require `Owner`, `Application`, `Environment`, `CostCenter`, and `Lifecycle` tags at resource creation. For legacy untagged resources, determine owners via CloudTrail, IaC state, deployment pipelines, and service dependencies before cleaning up.

### 9.3 Classifying Cleanup Candidates

| Category | Candidates to Review | Risks to Check |
|---|---|---|
| Compute | Long-stopped EC2, idle instances, zero-traffic ASGs, idle ECS services/tasks | DR, scheduled jobs, capacity reservations, instance store, Auto Scaling ownership |
| Block storage | Available/unattached EBS volumes, idle volumes, stale snapshots | Temporarily detached volumes, forensics, backups, AMIs still referencing snapshots |
| Network | Unassociated Elastic IPs, idle NAT Gateways, targetless load balancers | DR routes, failover, partner static IP allowlists, DNS, rare traffic |
| Database | Idle RDS/Aurora, unused read replicas, test clusters | Backup retention, replica lag, PITR, batch/quarter-end jobs |
| Object storage | Old S3 versions, incomplete multipart uploads, mismatched storage classes | Legal holds, Object Lock, restore needs, lifecycle rules |
| Observability | Unused log groups, infinite retention, high metric cardinality | Audit retention, incident investigations, compliance |
| Data processing | Idle SageMaker endpoints, running Glue/EMR clusters, spare batch workers | Scheduled workloads, model warm-up, data pipelines |
| Security/platform | Unused endpoints, ENIs, keys, certificates, or secrets | AWS service-managed resources, dependencies, rotation, recovery |

### 9.4 Stop, Scale Down, or Delete?

Favor reversible actions when evidence is incomplete:

1. Scale down or reduce desired capacity for Auto Scaling/ECS/EKS-managed resources.
2. Stop EC2/RDS or disable schedulers if workloads support it and owners confirm.
3. Quarantine/disable routes or endpoints per runbook when observation is needed.
4. Take snapshots/backups before deleting.
5. Delete explicitly by resource ID after the observation window and formal approval.

Stopping EC2 stops compute billing but does not eliminate all costs:

- EBS volumes continue accruing charges.
- Elastic IPs may continue accruing charges.
- Savings Plans/Reserved Instances commitments continue billing.
- Instance store data and RAM contents are lost.
- Auto-assigned public IPv4 addresses can change on restart.

EC2 instances inside Auto Scaling groups or managed by another service often cannot simply be stopped directly. Adjust desired capacity or controller configuration instead.

### 9.5 EBS Volumes and Snapshots

An EBS volume in `available` state is simply unattached at query time. Treat it as a candidate only; it may be awaiting restore, migration, or DR. Before deleting:

- Confirm owner and detach date.
- Inspect CloudTrail, attachment history, and IaC state.
- Verify it is not a recovery root volume.
- Take a snapshot if policy requires.
- Confirm the snapshot obeys retention and is restorable.
- Confirm the volume is unreferenced by workflows or AMIs.

Snapshots may back AMIs or recovery plans. Never delete snapshots purely due to age; inspect AMIs, AWS Backup recovery points, sharing, Recycle Bin, and retention policies. Recovery points managed by AWS Backup must be managed via AWS Backup APIs/console and are subject to Vault Lock/lifecycles; never assume EC2 `DeleteSnapshot` can delete them.

### 9.6 Elastic IPs, NAT Gateways, and Load Balancers

Unassociated Elastic IPs can still incur charges. Yet they may be held for failover, partner allowlists, or disaster recovery. Verify DNS, firewalls, and runbooks before releasing.

For idle NAT Gateways, inspect route tables, active connections, packet metrics, and AZ layout. If replacing NAT with VPC endpoints or another architecture, verify routes and security policies before deleting. Cost Optimizer flags NAT Gateways as idle when unassociated with route tables and showing zero traffic/connections over the lookback per current criteria.

Load balancers with zero targets or traffic may be standby failover endpoints, blue/green slots, or undergoing maintenance. Inspect listeners, target groups, DNS, WAF, certificates, security groups, and service ownership before deleting.

### 9.7 RDS/Aurora and Data

Databases showing zero connections during a lookback window may be standby nodes, DR instances, or periodic batch workloads. Before stopping/deleting:

- Inspect connections, CPU, IOPS, replicas, and Global Database topology.
- Verify backup retention, PITR, and snapshot restores.
- Confirm application owners and scheduled runtimes.
- Check endpoints, secrets, DNS, and downstream dependencies.
- Test snapshot restores in an isolated environment for critical data.

Some RDS engines support temporary stops followed by automatic restarts; limits and behavior vary by engine/deployment. Never treat stopping as a permanent solution while storage and backups remain billed.

### 9.8 S3 and CloudWatch Logs

For S3, review storage classes, versioning, noncurrent versions, incomplete multipart uploads, replication, and lifecycle rules. Use lifecycle rules to tier down or expire eligible objects per policy. With Object Lock/legal holds, do not attempt deletion before retention expires.

For CloudWatch Logs, log groups without retention keep data indefinitely. Set retention matching audit, incident response, and compliance needs. Never delete logs solely to cut costs without verifying retention obligations; reduce log verbosity, sampling, or retention only after owner sign-off.

## 10. AWS CLI Examples for Finding Cleanup Candidates

The commands below are read-only inventory queries. Run per account and Region, as AWS resources are Regional or account-scoped depending on service. Never pipe inventory output straight into automated deletion.

Example commands use Bash syntax with backslashes for line continuation. In PowerShell, enter commands on a single line or use PowerShell's line continuation character.

### 10.1 Unattached EBS Volumes

    aws ec2 describe-volumes \
      --filters Name=status,Values=available \
      --query 'Volumes[].{VolumeId:VolumeId,SizeGiB:Size,Type:VolumeType,CreateTime:CreateTime,Encrypted:Encrypted,Tags:Tags}' \
      --output table \
      --region ap-southeast-1

### 10.2 Unassociated Elastic IPs

    aws ec2 describe-addresses \
      --query 'Addresses[?AssociationId==null].{PublicIp:PublicIp,AllocationId:AllocationId,Domain:Domain,Tags:Tags}' \
      --output table \
      --region ap-southeast-1

### 10.3 NAT Gateways

    aws ec2 describe-nat-gateways \
      --filter Name=state,Values=available \
      --query 'NatGateways[].{NatGatewayId:NatGatewayId,SubnetId:SubnetId,VpcId:VpcId,State:State,CreateTime:CreateTime}' \
      --output table \
      --region ap-southeast-1

Output lists only available NAT Gateways. To confirm whether one is idle, inspect route table associations, CloudWatch metrics, flow logs, and DR design.

### 10.4 RDS Database Inventory

    aws rds describe-db-instances \
      --query 'DBInstances[].{Id:DBInstanceIdentifier,Engine:Engine,Class:DBInstanceClass,Status:DBInstanceStatus,MultiAZ:MultiAZ,StorageGiB:AllocatedStorage,BackupRetention:BackupRetentionPeriod}' \
      --output table \
      --region ap-southeast-1

This command does not prove a DB is idle. Correlate connections, CPU, IOPS, queries, replicas, and business schedules.

### 10.5 CloudWatch Log Groups

    aws logs describe-log-groups \
      --query 'logGroups[].{Name:logGroupName,StoredBytes:storedBytes,RetentionDays:retentionInDays,Created:creationTime}' \
      --output table \
      --region ap-southeast-1

Log groups lacking `retentionInDays` may retain logs indefinitely. Set retention aligned with data classification and audit requirements.

### 10.6 Snapshot Inventory

    aws ec2 describe-snapshots \
      --owner-ids self \
      --query 'Snapshots[].{SnapshotId:SnapshotId,VolumeId:VolumeId,StartTime:StartTime,State:State,SizeGiB:VolumeSize,Description:Description}' \
      --output table \
      --region ap-southeast-1

Cross-reference snapshots against AMIs, AWS Backup, retention, sharing, and recovery plans before deleting.

### 10.7 Controlled Deletion Actions

Execute deletion commands by explicit ID only after owner confirmation, backup/retention verification, and change approval. Example syntax:

    # Destructive action example: use only explicitly approved IDs
    aws ec2 delete-volume --volume-id vol-0123456789abcdef0 --region ap-southeast-1

    # Release a specific Elastic IP after confirming no failover/allowlist dependency
    aws ec2 release-address --allocation-id eipalloc-0123456789abcdef0 --region ap-southeast-1

    # Delete a specific snapshot after confirming no AMI/backup policy references it
    aws ec2 delete-snapshot --snapshot-id snap-0123456789abcdef0 --region ap-southeast-1

Never replace explicit IDs with wildcards or account-wide loops. For resources managed by CloudFormation, Terraform, EKS, RDS, AWS Backup, or other controllers, apply changes through the managing controller to avoid recreation or IaC state drift.

## 11. Guardrailed Cleanup Automation

### 11.1 Tags and Lifecycle Policies

A resource cleanup policy can leverage tags:

| Tag | Meaning |
|---|---|
| Owner | Person/team required to confirm |
| Environment | Production, staging, dev, sandbox |
| Lifecycle | Persistent, ephemeral, temporary |
| CleanupAfter | Earliest date eligible for cleanup review |
| DataClass | Data classification and retention |
| DoNotDelete | Opt-out flag excluding from automation per policy |

Tags alone do not authorize deletion. Automation must validate tags, owners, account/Region allowlists, resource states, dependencies, retention, and approvals.

### 11.2 Dry-Run Workflow

Before automating stops/deletions:

1. Run read-only discovery.
2. Build a candidate list with evidence and estimated savings.
3. Skip resources missing owners or mandatory tags.
4. Check dependencies, backups, and service ownership.
5. Send reports for owner review.
6. Apply only allowlisted, approved actions.
7. Archive CloudTrail events, action outcomes, and rollback steps.

Scheduled EventBridge jobs can invoke Lambda/Step Functions/Systems Manager Automation. Prioritize automation for discovery, reporting, and owner reminders. Automate deletion only for resources with clear policies, stateless data, and tested rollbacks.

### 11.3 Approvals and Separation of Duties

The person discovering candidates should not unilaterally approve deletion. Separate permissions:

- Read-only inventory/recommendations.
- Stopping/scaling resources.
- Taking snapshots/backups.
- Deleting/releasing resources.
- Administering policies/allowlists.

IAM policies should scope actions by resource tags, accounts, Regions, and resource types where supported. SCPs/permission boundaries can block dangerous actions at the Organization level. CloudTrail must log principals and requests for auditing.

### 11.4 Idempotency and Rollback

Automation must be safe to rerun:

- Re-check current state before every action.
- Skip resources already deleted or no longer matching criteria.
- Abort deletion if owner/tag/backup state changed after discovery.
- Record operation ID, resource ID, timestamp, and approval reference.
- Enforce timeouts, bounded retries, and dead-letter/error workflows.
- Monitor health/alarms after stopping before proceeding to delete.
- Rollbacks must specify how to restart/recreate and which data cannot be recovered.

Stopping EC2 cannot recover lost instance store data or memory. Deleting EBS without a snapshot is irreversible. Releasing an Elastic IP may make the address unrecoverable. Every automation must state these limits explicitly.

## 12. Prioritizing Actions by Savings, Effort, and Risk

Not every highest-savings recommendation belongs at the top of the queue. One prioritization approach:

\[
\text{Priority score} =
\frac{\text{Expected monthly savings} \times \text{Confidence}}
{\text{Implementation effort} \times \text{Business risk factor}}
\]

This is an internal governance model, not an AWS formula. Teams can score confidence, effort, and risk on a 1–5 scale to rank backlogs.

| Action | Savings Potential | Effort | Risk |
|---|---|---|---|
| Delete confirmed unused unattached EBS volume | Medium | Low | Low to medium if snapshot/owner confirmed |
| Configure log retention | Medium | Low | Medium if audit impact exists |
| Rightsize non-production EC2 | Medium | Low to medium | Low if rollback exists |
| Rightsize production database | High | Medium/high | High without benchmarking |
| Remove NAT Gateway | Potentially high | Medium | High if routing/DR unclear |
| Modify Savings Plans commitment | High | Medium | High if usage forecast is wrong |
| Clean up old snapshots/backups | Potentially high | Medium | Very high if retention/legal hold applies |

Set backlog SLAs by category:

- Quick wins: low effort, low risk, fast owner confirmation.
- Engineering changes: require benchmarks, testing, and deployments.
- Financial commitments: require forecasts, term review, and finance sign-off.
- Data retention/security: require compliance, legal, and security sign-off.

## 13. Real-World Example: Multi-Tenant SaaS

### 13.1 Context

A SaaS platform serves 300 active tenants. During the month:

- Total AWS spend on a net amortized basis: $21,000 USD.
- 150,000 orders processed.
- 300 active tenants.
- Shared logging/network/platform spend already allocated by usage drivers.

Unit economics:

    Cost per order = 21,000 / 150,000 = 0.14 USD
    Cost per tenant = 21,000 / 300 = 70 USD

Last month's cost per order was $0.15 USD. Despite total spend rising, per-order efficiency improved. However, cost per tenant can vary sharply between small and large tenants; add p50/p90 cost distributions to spot heavy-consuming tenants.

### 13.2 Detecting an Anomaly

Cost Anomaly Detection raises an anomaly on Amazon EC2:

- Expected spend: $300 USD.
- Actual spend: $1,300 USD.
- Impact: $1,000 USD.
- Root cause: one production account, Region `ap-southeast-1`, usage type EC2 instance-hour.

FinOps checks deployment history and finds a test autoscaling group had minimum capacity set to 20 instead of 2. CloudTrail pinpoints the update timestamp; CloudWatch shows low CPU and near-zero requests.

The platform team confirms the capacity is not for DR, lowers minimum capacity back to 2 instances per approved baseline, and updates IaC so future deploys do not reintroduce the mistake. Once spend returns to baseline, the anomaly is closed and logged.

### 13.3 Cleanup and Realized Savings

Compute Optimizer flags idle EC2 and unattached EBS volumes. Owners confirm:

- One test EC2 instance can be stopped.
- One EBS volume is temporary migration leftover with a verified snapshot.
- One NAT Gateway backs a DR route and must stay.
- One unused log group can move to 90-day retention after audit owner sign-off.

Do not delete all candidates at once. Execute batch by batch, monitor application health and billing for 7–30 days, then measure savings normalized by order volume.

### 13.4 Results to Track

| Metric | Before | After |
|---|---|---|
| AWS spend | 21,000 USD | Measure next period actuals |
| Cost/order | 0.14 USD | Compare after normalizing volume |
| Idle EC2 | 1 candidate | Stopped and verified |
| Unattached EBS | 1 candidate | Snapshotted + deleted after approval |
| NAT Gateway | 1 idle-looking | Retained for DR |
| Anomaly impact | 1,000 USD | Confirmed resolved |

Never book projected savings as realized savings. Recognize realized savings only after billing data reflects the change and traffic/price/discount variances are isolated.

## 14. Lab: Building a Unit Economics and Cleanup Loop

### Objective

Create a cost-per-unit report, configure anomaly alerts, identify cleanup candidates, and demonstrate measurable impact from an optimization action.

### Step 1: Prepare Cost Allocation

1. Pick a workload with a clear owner.
2. Apply `Application`, `Environment`, `Owner`, and `CostCenter`.
3. Activate cost allocation tags in Billing.
4. Wait for tag data to populate; inspect tagged vs. untagged spend.
5. Create Cost Categories if grouping or shared cost allocation is needed.

### Step 2: Build a Unit Economics Report

1. Pick net amortized cost or your organization's agreed cost basis.
2. Pull costs by account, Region, service, usage type, and tag.
3. Pull denominators from product telemetry: orders, requests, tenants, or active users.
4. Compute monthly cost/unit by workload.
5. Separate direct and shared costs.
6. Document coverage, assumptions, and unallocated spend.

### Step 3: Configure Cost Anomaly Detection

1. Enable Cost Explorer.
2. Create an AWS-managed service monitor.
3. Create linked-account or cost-allocation-tag monitors if needed.
4. Create an alert subscription.
5. Choose individual alerts via SNS for fast response or daily/weekly email summaries.
6. Set absolute/percentage thresholds suited to workload scale.
7. Test EventBridge integration if wiring into incident workflows.

### Step 4: Identify Cleanup Candidates

1. Enable Compute Optimizer and Cost Optimization Hub per permissions.
2. Inspect idle EC2, EBS, RDS, NAT, and supported resource types.
3. Run the CLI discovery commands in Section 10 to cross-check inventory.
4. Record owner, usage evidence, retention, and estimated savings.
5. Classify actions: stop, scale down, snapshot, delete, or retain.

### Step 5: Execute a Reversible Action

Pick an owner-confirmed non-production resource. Stop or scale it down per runbook. Monitor applications, CloudWatch, and billing data. Proceed to deletion only after approval and backup/rollback verification.

### Step 6: Report Outcomes

Document:

- Before/after unit cost.
- Before/after total spend.
- Output volume and workload mix.
- Modified resources.
- Resolved anomalies.
- Estimated vs. realized savings.
- Remaining risks/limitations.

## 15. Self-Check Questions

**Q1.** What question does unit economics answer?

**Answer:** The cost and economic value per unit of output such as an order, tenant, active user, or successful request.

**Q2.** Why doesn't a rising AWS bill automatically mean lower efficiency?

**Answer:** If output grows faster than spend, unit cost can actually fall. Always evaluate total spend alongside the denominator.

**Q3.** How does cost per successful transaction differ from cost per attempted transaction?

**Answer:** Successful transactions count only value-generating completions; attempted transactions include retries/failures. Both denominators answer different questions.

**Q4.** Why must you state the cost basis explicitly?

**Answer:** Unblended, net unblended, amortized, and net amortized costs handle discounts/commitments differently; switching bases shifts trends even when usage is unchanged.

**Q5.** What must happen before cost allocation tags appear in Cost Explorer?

**Answer:** Tags must be applied to resources and activated in Billing. AWS-generated and user-defined tags are activated separately, and data can take up to 24 hours to propagate.

**Q6.** Do Cost Categories split charges alter CUR and Cost Explorer?

**Answer:** No. Split charges appear on the Cost Categories details page and do not modify CUR, Cost Explorer, or other Cost Management tools.

**Q7.** Which cost basis does AWS Cost Anomaly Detection analyze?

**Answer:** Net unblended cost data.

**Q8.** Why is Cost Anomaly Detection not a real-time alert?

**Answer:** It runs roughly three times daily after billing data is processed, and Cost Explorer data can lag up to 24 hours.

**Q9.** How much historical data does a newly active service need before anomaly detection starts?

**Answer:** 10 days of historical service usage data per current documentation.

**Q10.** Do thresholds on anomaly subscriptions prevent the model from detecting small anomalies?

**Answer:** No. Thresholds filter notification delivery only; anomalies below thresholds still appear in Detected anomalies.

**Q11.** How do AWS-managed monitors differ from customer-managed monitors?

**Answer:** AWS-managed monitors automatically track all values in a dimension and scale automatically; customer-managed monitors target up to 10 explicit accounts/tag values per supported dimension.

**Q12.** Does Cost Anomaly Detection monitor all AWS Marketplace spend?

**Answer:** No. Third-party Marketplace products/services are generally excluded, except third-party foundation models on Amazon Bedrock. Use AWS Budgets to track Marketplace charges.

**Q13.** How do AWS Budgets and Cost Anomaly Detection complement each other?

**Answer:** Budgets alert when actuals/forecasts cross defined thresholds; anomaly detection catches unusual spend patterns relative to history.

**Q14.** What lookback windows can Compute Optimizer idle recommendations use?

**Answer:** Commonly 14 days by default, with exceptions such as 32 days for EBS/NAT attachments and 63 days for WorkSpaces.

**Q15.** Why shouldn't you delete an EBS volume solely because its status is `available`?

**Answer:** It may be staged for migration, restore, DR, or forensics; confirm owner, dependencies, backups, and retention first.

**Q16.** Does stopping EC2 stop all charges?

**Answer:** No. EBS, Elastic IPs, and RI/Savings Plans commitments continue accruing charges.

**Q17.** Why must you check ASGs before stopping EC2 instances?

**Answer:** An ASG or service controller may relaunch replacements or block direct stops; update desired capacity/configuration on the controller instead.

**Q18.** Why check seasonality before cleaning up idle resources?

**Answer:** Workloads may run monthly, quarterly, seasonally, or for DR; short lookbacks can miss active cycles.

**Q19.** Are estimated savings in Cost Optimization Hub equal to realized savings?

**Answer:** No. They are projected potential; measure actual billing post-change and normalize for usage before claiming realized savings.

**Q20.** Why does cleanup automation need dry-run, approvals, and idempotency?

**Answer:** To prevent accidental resource/data deletion, enforce access controls, handle safe reruns, and preserve audit evidence/rollbacks.

## 16. FinOps Operations Checklist

- [ ] Unit metrics have clear definitions, owners, and stable denominators.
- [ ] Numerators use a consistent cost basis with documented boundaries.
- [ ] Direct/shared costs are allocated via explainable drivers.
- [ ] Cost allocation tags are activated and coverage is measured.
- [ ] Cost Categories have sound rule ordering and default values.
- [ ] Split charges are understood as a governance layer rather than replacing CUR/Cost Explorer.
- [ ] CUR/Data Exports have configured S3 destinations, granularity, and owners.
- [ ] Unit cost is reviewed alongside availability, latency, errors, and capacity.
- [ ] Cost Anomaly Detection has appropriate monitors and recipient subscriptions.
- [ ] Absolute/percentage thresholds match workload scale.
- [ ] Billing latency and Marketplace boundaries of anomaly detection are understood.
- [ ] AWS Budgets track actuals/forecasts against limits.
- [ ] Anomalies have owners, triage workflows, incident links, and feedback.
- [ ] Compute Optimizer/Cost Optimization Hub are enabled across target accounts/Regions.
- [ ] Idle recommendations are validated against seasonality and business calendars.
- [ ] Resource cleanup enforces inventory, owners, backups, dependencies, and approvals.
- [ ] Reversible stops/scale-downs precede permanent deletion.
- [ ] Deletions target explicit resource IDs through owning controllers.
- [ ] Automation enforces dry-run, allowlists, idempotency, auditing, and rollback.
- [ ] Realized savings are measured using volume-normalized actual costs.

## 17. Official References

1. [AWS Cost Anomaly Detection – overview](https://docs.aws.amazon.com/cost-management/latest/userguide/manage-ad.html) — detection models, latency, and limits.
2. [Getting started with Cost Anomaly Detection](https://docs.aws.amazon.com/cost-management/latest/userguide/getting-started-ad.html) — monitor types, alert subscriptions, and thresholds.
3. [Using EventBridge with Cost Anomaly Detection](https://docs.aws.amazon.com/cost-management/latest/userguide/cad-eventbridge.html) — event schema and workflows.
4. [AWS Cost Allocation Tags](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/cost-alloc-tags.html) — activating and classifying costs with tags.
5. [Creating Cost Categories](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/create-cost-categories.html) — grouping rules and split charges.
6. [Splitting charges within Cost Categories](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/splitcharge-cost-categories.html) — proportional, fixed, and even splits.
7. [Exploring data using Cost Explorer](https://docs.aws.amazon.com/cost-management/latest/userguide/ce-exploring-data.html) — unblended, amortized, and net costs.
8. [AWS Cost and Usage Reports](https://docs.aws.amazon.com/cur/latest/userguide/what-is-cur.html) — granular cost/usage data.
9. [Creating a cost budget](https://docs.aws.amazon.com/cost-management/latest/userguide/create-cost-budget.html) — actual/forecast thresholds.
10. [Cost Optimization Hub](https://docs.aws.amazon.com/cost-management/latest/userguide/cost-optimization-hub.html) — aggregating and prioritizing savings recommendations.
11. [Viewing idle resource recommendations](https://docs.aws.amazon.com/compute-optimizer/latest/ug/view-idle-recommendations.html) — idle criteria and per-resource lookbacks.
12. [Rightsizing recommendation preferences](https://docs.aws.amazon.com/compute-optimizer/latest/ug/rightsizing-preferences.html) — lookback, CPU/memory headroom, and performance risk.
13. [Stopping idle resources](https://docs.aws.amazon.com/cost-management/latest/userguide/coh-stop-idle-resources.html) — stopping idle EC2 from Cost Optimization Hub.
14. [AWS Cost Optimization Hub now supports stopping idle EC2 instances](https://aws.amazon.com/about-aws/whats-new/2026/11/cost-hub-stop-idle-ec2/) — announcement published November 17, 2026.
15. [AWS Resource Groups Tagging API](https://docs.aws.amazon.com/resourcegroupstagging/latest/APIReference/Welcome.html) — inventory and querying resource tags.
16. [AWS CloudTrail](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-user-guide.html) — auditing API activity and resource changes.

---

**Conclusion:** Unit economics shows the cost of producing one unit of value; anomaly detection alerts when spend drifts from expected behavior; cleanup turns evidence into controlled action. A mature FinOps program combines all three with trustworthy allocation data, clear owners, data-protection guardrails, and savings measured via output-normalized actual costs.
