# Billing, Consolidated Billing, and Cost Allocation

## Learning Objectives

After this lesson, you will be able to:

- Explain how AWS meters usage, generates invoices, and delivers cost data.
- Distinguish between standalone AWS accounts, AWS Organizations, management accounts, member accounts, and payer accounts.
- Describe consolidated billing, usage aggregation, volume discounts, Reserved Instances, and Savings Plans.
- Configure a discount sharing model aligned with your organizational structure.
- Differentiate consolidated billing from Billing Transfer across multiple AWS Organizations.
- Build a cost allocation taxonomy using accounts, resource tags, account tags, and AWS Cost Categories.
- Design showback, chargeback, and shared cost allocation.
- Select AWS Bills, Cost Explorer, AWS Budgets, Cost Anomaly Detection, and Data Exports CUR 2.0 according to purpose.
- Explain the role of AWS Billing Conductor and pro forma data.
- Protect billing access, CUR data, and cloud financial governance workflows.
- Design a FinOps workflow spanning forecasting, tracking, allocation, reconciliation, and cost optimization.

## 1. Why Billing and Cost Allocation Matter

When an enterprise uses AWS across multiple products, environments, and teams, the question is no longer just how much this month's total bill is. The organization needs to know:

- Which account, product, application, or environment is consuming budget?
- Which costs belong directly to a team, and which are shared platform costs?
- Did a cost increase come from higher traffic, architectural changes, service pricing, or suboptimal configuration?
- Where are discounts from Reserved Instances (RI) and Savings Plans (SP) being applied?
- Which team is accountable for costs without an owner?
- How can the AWS invoice be reconciled against budgets, purchase orders, and internal general ledgers?

AWS Billing and Cost Management provides usage data, cost data, invoices, and analysis tools. AWS Organizations consolidated billing combines payments across multiple accounts into a single billing family. Cost allocation maps cost line items onto business structures. FinOps connects this data to accountability and operational decisions.

A solid billing system must answer two distinct questions:

1. **How much does AWS bill and collect?** This is a question about billable charges and the invoice.
2. **Who does the business want to allocate that amount to?** This is a question about showback, chargeback, and the internal cost model.

The two numbers can differ because an organization may distribute shared services, apply an internal markup, or use internal pricing. Always make clear which figures represent the AWS invoice and which represent internal allocation figures.

## 2. Basic Billing Terminology

| Term | Meaning |
|---|---|
| AWS account | Governance, security, resource, and billing boundary |
| Management account | The account that creates and owns an AWS Organization |
| Member account | A member account belonging to an Organization |
| Payer account | The account that generates, manages, and pays the consolidated bill; in standard Organizations, this is the management account |
| Linked account | Common term for a member account when analyzing billing |
| Billing family | A group of accounts whose usage is aggregated for billing purposes |
| Billing period | The billing cycle, typically monthly |
| Invoice | The document issued by AWS establishing the amount due |
| Usage | Amount of service consumed |
| Charge | Fee incurred from usage, subscriptions, or purchases |
| Credit | Credit applied to reduce the amount payable under applicable terms |
| Refund | Refund recorded in billing data |
| Discount | Price reduction from pricing tiers, RIs, SPs, or agreements |
| Showback | Reporting costs to consuming teams so they have visibility into consumption |
| Chargeback | Allocating internal costs to the responsible cost center or budget |
| Pro forma billing | Simulated billing data based on internal pricing rules, not an AWS invoice |

In AWS documentation, the management account and payer account usually coincide when using standard consolidated billing. With Billing Transfer, billing responsibility can be transferred to an external bill-transfer account outside the Organization. Use exact terminology matching your deployment model.

## 3. Designing Account Structure for Cost Governance

An AWS account is a strong cost allocation dimension because each account can represent an environment, product, team, or security boundary.

A reference structure:

~~~mermaid
flowchart TD
    P["Management / Payer account"] --> O["AWS Organizations"]
    O --> S["Security OU"]
    O --> I["Infrastructure OU"]
    O --> W["Workloads OU"]
    O --> D["Sandbox OU"]
    S --> SA["Security account"]
    I --> N["Network account"]
    I --> L["Logging account"]
    W --> A["Product A - Production"]
    W --> B["Product B - Production"]
    W --> T["Shared services"]
    D --> X["Developer sandbox accounts"]
~~~

Accounts can be segmented by:

- **Environment:** production, staging, development, sandbox.
- **Business unit:** finance, engineering, marketing, data.
- **Product/application:** storefront, analytics, identity platform.
- **Function:** security, networking, logging, shared platform.

There is no need to create a separate account for every tiny project. Account sprawl increases administrative overhead, whereas lumping every workload into a single account weakens isolation, tracking, and accountability. Choose boundaries that remain meaningful long term.

### 3.1 Billing Boundary and Security Boundary

Consolidated billing does not merge multiple AWS accounts into one account. Each account retains its own resources, credentials, IAM policies, and access controls. The management account is responsible for paying for member accounts, but that does not automatically grant administrative control over every member account's workloads.

If centralized governance is needed, the organization must configure AWS Organizations all features, IAM roles, IAM Identity Center, service control policies (SCPs), delegated administration, and appropriate access workflows. Consolidated billing addresses only billing aggregation.

### 3.2 Protecting the Management Account

The management account carries special privileges and responsibilities. You should:

- Not deploy application workloads into the management account.
- Enable strong MFA for the root user and protect recovery methods.
- Not create root access keys.
- Use IAM Identity Center or controlled IAM roles for day-to-day work.
- Separate permissions for viewing bills, managing payments, administering Organizations, and managing workloads.
- Monitor CloudTrail for changes to Organizations, billing preferences, cost categories, and billing access.

## 4. Consolidated Billing with AWS Organizations

Consolidated billing allows an AWS Organization to combine billing and payment across multiple accounts. The management account receives the consolidated bill and pays charges incurred by member accounts.

Key benefits:

1. **One consolidated bill:** accounts under the same Seller of Record (SOR) are combined into one bill. The SOR is the local AWS legal entity selling AWS services and contracting with the customer. If an Organization spans multiple SORs, AWS issues one bill per SOR.
2. **Centralized visibility:** the management account sees total costs and can break them down by member account.
3. **Usage aggregation:** AWS combines usage across accounts to calculate volume pricing tiers.
4. **Discount sharing:** RIs and Savings Plans can be shared across eligible accounts according to billing preferences.
5. **No extra fee for consolidated billing:** this feature has no separate charge.

A member account can still view its own usage and charges, though a member account's bill is informational only within the billing family. The management account is responsible for paying the consolidated bill. Member account owners cannot view billing data for the management account or other members unless explicitly granted appropriate permissions.

### 4.1 Volume Pricing Aggregation

Some services have tiered pricing that lowers unit rates as total usage rises. When consolidated billing is enabled, AWS sums usage across accounts in the Organization to determine the applicable tier.

Illustrative example:

- Product A uses 7 TB in the month.
- Product B uses 5 TB in the month.
- Total billing family usage is 12 TB.

If the service offers a lower price tier above 10 TB, combined usage can qualify the Organization for a better tier than the two accounts standing alone. AWS distributes the resulting discount according to the service's billing rules and usage data.

Not every service or dimension has volume discounts. Always check each service's pricing page.

### 4.2 Timing When an Account Joins an Organization

When a member account accepts an invitation to join, the management account becomes responsible for charges incurred from the moment the account joins. If an account joins mid-month, the previous owner remains responsible for charges incurred prior to joining.

When a member account leaves an Organization, it may lose access to Cost Explorer data generated while it was a member. The data is not deleted; the former management account retains access. If the account rejoins the Organization, access to prior data may be restored per AWS guidance.

### 4.3 Consolidated Billing Does Not Automatically Split Internal Costs

AWS aggregates the bill and applies discounts according to billing rules. Attributing costs to Product A, Product B, or departments still requires account dimensions, cost allocation tags, Cost Categories, or a dedicated chargeback system.

## 5. Sharing Reserved Instances and Savings Plans

RIs and Savings Plans are usage commitments in exchange for discounted pricing. Within an Organization, discount sharing allows usage in one account to benefit from a commitment purchased in another account if service, Region, scope, and billing preference conditions are met.

Example:

- Account A purchases a Savings Plan, but its workload uses less than the commitment.
- Account B has eligible compute usage.
- If discount sharing is enabled and usage meets conditions, the unused portion of the commitment can apply to Account B's usage.

This maximizes Organization-wide utilization, while complicating internal cost attribution. The account that purchased the commitment may not be the account receiving the full discount benefit.

### 5.1 Three Discount Sharing Modes

AWS Billing preferences currently support three options:

| Mode | Allocation Behavior | Suitable Use Case |
|---|---|---|
| Open sharing | Discounts can be shared with all accounts with sharing enabled in the Organization; this is the default | Maximize Organization-wide cost optimization |
| Prioritized group sharing | Prioritizes the purchasing account, then defined groups, then remaining eligible accounts | Balance control with optimization |
| Restricted group sharing | Discounts are shared only within defined groups | Isolate discounts by business unit or customer |

To use group sharing, create a Cost Category defining the account groups. Each account belongs to at most one sharing group; groups cannot overlap; the management account does not belong to any sharing group. The account owning the Savings Plan must have discount sharing enabled for the benefit to be applied.

Group sharing can reduce overall discount utilization if commitments are not fully consumed within their assigned group. Model the impact before switching from open sharing to restricted group sharing.

### 5.2 Credits Have Separate Preferences

Credit sharing differs from RI/SP discount sharing. The payer account can choose which accounts are allowed to share or receive credits within the billing family. Do not assume that enabling RI/SP sharing automatically shares credits as well.

### 5.3 Distinguishing Cost and Savings

When analyzing RIs/SPs, separate:

- Commitment purchase cost.
- Usage covered by the commitment.
- Unused commitment.
- Discount benefit applied to consuming accounts.
- Amortized cost for evaluating economic efficiency over time.

Use the cash bill to reconcile the amount AWS collects during the period. Use the amortized view to evaluate daily/monthly workload economics and avoid misinterpreting a large upfront payment as solely a cost of the purchase month.

## 6. Billing Transfer Across Multiple AWS Organizations

Consolidated billing groups accounts within a single Organization. If an enterprise operates multiple Organizations and wants an external account to manage and pay those consolidated bills, evaluate **Billing Transfer**.

In Billing Transfer:

- **Bill-source account:** the management account of the Organization generating the consolidated bill.
- **Bill-transfer account:** the designated external management account managing and paying the bill.
- Both parties are management accounts of separate Organizations.
- The bill-transfer account sends an invitation; the bill-source account accepts.
- The invitation must be accepted before the effective cutoff required by AWS.
- Transfers start and end on monthly boundaries at AWS-specified UTC times.

Billing Transfer centralizes payment and cost management data across multiple Organizations. It does not merge Organizations into a single billing computation boundary. Volume discounts, RIs, and Savings Plans are still calculated within each individual AWS Organization. Do not expect Organization A's RIs/SPs to cover Organization B's usage simply because both share a bill-transfer account.

### 6.1 Impacts to Evaluate Before Transferring

- Existing CUR configurations may become Unhealthy and need to be recreated.
- The bill-source account may lose access to historical cost data in Cost Anomaly Detection.
- Cost Anomaly Detection does not support creating alerts for bill-source account usage under the Billing Transfer model.
- Certain credits, Free Tier, support charges, taxes, or refunds may not appear in pro forma data under default settings.
- The bill-source account should download CUR and save AWS Budgets data prior to transfer.
- Cost Explorer pro forma data may lack hourly granularity; use CUR for hourly detail.
- Re-verify access permissions, cost categories, cost allocation tags, and reports after the transfer.

Billing Transfer is a significant change in financial responsibility. Plan reconciliation, historical data preservation, and Finance notifications before enabling it.

## 7. Different Billing Data Sources

Not every page in Billing and Cost Management displays the exact same numbers. Choose the right data source for the question at hand.

| Source | Purpose | How It Is Used |
|---|---|---|
| Bills | View charges and invoices by period | Reconcile amounts payable |
| Payments | View payment status and transactions | Track payments |
| Cost Explorer | Analyze cost/usage by account, service, Region, tag, category, and time | Identify cost drivers and trends |
| AWS Budgets | Track cost/usage against thresholds or plans | Alerting and actions |
| Cost Anomaly Detection | Detect unusual spending patterns | Investigate unexpected cost spikes |
| Cost Categories | Map line items to internal structures | Allocation and reporting |
| Cost allocation tags | Analyze costs by resource metadata | Tie costs to app/team/environment |
| Data Exports CUR 2.0 | Granular data for querying and integration | Athena, QuickSight, data warehouse |
| AWS Billing Conductor | Create billing views using internal pricing rules | Showback/chargeback and billing transfer |

### 7.1 Bills and Invoices Are the Financial Source of Truth

The Bills page displays charges by billing period, service, account, purchases, and applicable taxes. For an open period, figures represent estimated charges. When AWS issues the invoice, the billing period status changes to Issued, and the invoice amount is the basis for payment.

Do not use Cost Explorer as a substitute for an invoice. Cost Explorer is an analytical tool that groups data and displays discounts, credits, refunds, and taxes differently from the Bills page.

### 7.2 Cash Basis and Amortized Cost

Billing data is always presented on a cash basis. For example, an organization buys a one-year All Upfront Savings Plan in October. The October invoice records that upfront payment.

Cost Explorer can display amortized cost, spreading the upfront amount evenly across the commitment term to analyze workload efficiency. The two views answer different questions:

- Cash basis: how much is AWS collecting this month?
- Amortized basis: how much economic cost is the workload consuming over time?

### 7.3 Why Bills and Cost Explorer Can Differ

Several reasons:

- Different refresh timestamps for intra-month estimated data.
- Cost Explorer exposes granular dimensions such as Availability Zone or operating system.
- Cost Explorer may separate EC2 Instances and EC2 Other, whereas the invoice groups by service.
- Amortized cost spreads commitments over time.
- Refunds, credits, and taxes may be presented differently.
- Rounding and data processing granularity differ.

When determining how much to pay AWS, reconcile against the final invoice. When understanding which workloads consume resources and finding optimization opportunities, use Cost Explorer or CUR.

## 8. Building a Cost Allocation Model

Cost allocation is the process of mapping AWS costs onto the enterprise's accountability structure. A strong model combines multiple dimensions instead of relying on a single tag.

Common dimensions:

| Dimension | Example | Data Source |
|---|---|---|
| Account | Product A production | AWS account ID/name |
| Business unit | Engineering, Marketing | Account tag or Cost Category |
| Cost center | CC-ENG-001 | Resource tag, account tag |
| Application | storefront, analytics | Resource tag or awsApplication |
| Environment | prod, staging, dev | Resource tag |
| Owner | team-checkout | Resource tag or account metadata |
| Project | migration-2026 | Resource tag |
| Service | EC2, S3, RDS | Billing dimension |
| Region | ap-southeast-1 | Billing dimension |
| Usage type | BoxUsage, DataTransfer | CUR usage dimensions |

A single resource can belong to multiple dimensions simultaneously. For instance, an EC2 instance carries:

- CostCenter = CC-ENG-001
- Application = checkout
- Environment = prod
- Owner = team-commerce

Reports can aggregate costs by CostCenter for Finance reconciliation, by Application for Product Owner optimization, or by Environment to catch development resources left running off-hours.

### 8.1 Choose Account Boundaries Before Tags

If each product has its own production account, the account dimension already provides a clean boundary. Tags further subdivide costs inside that account.

Some charges cannot receive resource tags or do not belong to a single resource—for example, shared support, certain credits, taxes, or shared network/platform costs. Account tags and Cost Categories help bridge these gaps.

### 8.2 Showback and Chargeback

- **Showback:** delivers reports to consuming teams for cost visibility without internal fund transfers.
- **Chargeback:** allocates costs into the responsible team's cost center, budget, or general ledger.
- **Hybrid:** start with showback to improve accuracy, then move to chargeback once taxonomy and data stabilize.

Chargeback requires explicit rules for allocating discounts, shared services, taxes, credits, support, Marketplace charges, and unowned costs. Simply taking unblended costs and splitting them evenly may not reflect true economics.

## 9. Designing a Tag Taxonomy for Cost Allocation

A tag is a key/value pair attached to a resource. A resource can have only one value per key. Standardize key names and value conventions across the Organization.

A reference taxonomy:

| Key | Example Value | Purpose |
|---|---|---|
| CostCenter | CC-ENG-001 | Finance reconciliation |
| BusinessUnit | Engineering | Cost-bearing department |
| Application | checkout | Product/application |
| Environment | prod | Environment |
| Owner | team-commerce | Responsible team |
| Project | migration-2026 | Time-bound project |
| DataClass | internal | Operational classification, no sensitive info |

### 9.1 Design Principles

- Pick a consistent naming style, such as PascalCase for keys and lowercase for values.
- Standardize values using a managed catalog.
- Never put personal emails, customer names, credentials, or sensitive data in tags.
- Assign an owner for each key.
- Define mandatory tags per resource type.
- Use Infrastructure as Code to apply tags at resource creation time.
- Verify whether the service supports cost allocation tags for that resource type.
- Define a default or workflow for handling unallocated costs.
- Review tag coverage monthly.

Tag policies in AWS Organizations can enforce standardized tag keys/values and evaluate compliance across supported services. However, do not assume every resource automatically receives all tags. Verify service support and embed guardrails in IaC/CI pipelines.

### 9.2 AWS-Generated and User-Defined Tags

AWS supports two types of cost allocation tags:

- **AWS-generated tags:** created and applied by AWS or AWS Marketplace.
- **User-defined tags:** created and applied to resources by your organization.

AWS-generated tags typically use the `aws:` prefix. User-defined tags appear with the `user:` prefix in cost allocation reports. The `aws:` prefix is reserved for AWS; do not use it for custom tags.

Certain tags such as `awsApplication` can be automatically applied to resources associated with applications in AWS Service Catalog AppRegistry and automatically activated as cost allocation tags. Check the status of this tag if your organization uses AppRegistry.

## 10. Activating Cost Allocation Tags

Applying tags to resources is not enough for them to appear in billing reports. The tag key must be activated in Billing and Cost Management.

Process:

1. Apply tag keys/values to supported resources.
2. Wait for the tag key to appear on the Cost allocation tags page.
3. Sign in to the management account or a standalone account with billing permissions.
4. Open Billing and Cost Management.
5. Select Cost allocation tags.
6. Select the user-defined or AWS-generated tag keys to activate.
7. Choose Activate.
8. Verify that the tag appears in Cost Explorer or CUR.

It can take up to 24 hours for a tag key to appear after being created and applied to resources. After activation, it can take up to another 24 hours for the tag key to become active in billing data.

Activation operates at the tag key level, so activating/deactivating affects all tag values under that key. For example, activating the `Environment` key applies to `prod`, `staging`, and `dev` values.

### 10.1 Account Tags for Cost Allocation

Account tags are an allocation dimension at the AWS account level. Usage and costs within an account can inherit account-level tags in reports. This mechanism is helpful for items that cannot be tagged directly on resources, including credits, refunds, and certain service charges.

Account tags can be used with Cost Explorer, CUR 2.0, FOCUS, AWS Budgets, Cost Categories, and Cost Anomaly Detection once activated. They complement resource tags rather than replacing them when application- or resource-level granularity is needed.

### 10.2 Note When an Account Moves Between Organizations

When an account moves to a different Organization, the activated state of previously enabled cost allocation tags may be lost. The new management account must check and reactivate required tag keys so reports do not lose allocation dimensions.

## 11. AWS Cost Categories

Cost Categories allow mapping billing line items into business-meaningful groups. A Cost Category is a key/value applied to cost line items:

- Category name is the key.
- Category value is the value assigned by rules.

Example:

- Cost Category: Department
- Values: Engineering, Marketing, Finance, Shared Platform

Cost Categories are managed from the Organization's management account or a standalone account. Under Billing Transfer, bill-source and bill-transfer accounts manage categories within their respective Organization scopes according to AWS-supported roles.

### 11.1 Dimensions for Grouping Costs

Rules can be based on:

- Account or linked account.
- Cost allocation tags.
- Charge type, such as credits/refunds.
- AWS service.
- Region.
- Usage type.
- Billing entity, such as AWS or AWS Marketplace.
- Another Cost Category or inherited values by design.

Rules are evaluated top-down. If a line item matches multiple rules, the first matching rule wins. Place specific rules before general rules and include a default value for unmatched items.

### 11.2 Classification Example

Suppose a company has three product teams:

| Rule | Condition | Cost Category Value |
|---|---|---|
| 1 | Account belongs to Product A | Product A |
| 2 | Account belongs to Product B | Product B |
| 3 | Tag CostCenter = CC-ENG-001 | Engineering |
| 4 | Service = AWS Support | Shared Platform |
| Default | Matches no rule | Unallocated |

In practice, design rule ordering so account-level ownership and resource-level tags do not unintentionally override each other. You can create multiple categories such as BusinessUnit, Application, and Environment to support different reporting views.

### 11.3 Inherited Values and Hierarchical Categories

Inherited value rules let a Cost Category dynamically pull values from a dimension—for example, inheriting the value of the `Team` tag key. If team tag values change, the category reflects the new values without creating static rules for every team.

You can build hierarchical relationships between categories. For example:

- Cost Category `Team` has Engineering, Marketing, Data.
- Cost Category `BusinessUnit` groups Engineering and Data into Technology, and Marketing into Growth.

Cost Categories appear as a dimension in Cost Explorer and Budgets, as a column in CUR, and as a monitor type in Cost Anomaly Detection.

### 11.4 Effective Dates

Cost Categories typically take effect from the beginning of the current month. When creating a category, you can select an appropriate effective date and apply rules retroactively within supported windows. Verify the preview and data once the category reaches Applied status before using it as the basis for chargeback.

## 12. Split Charges and Allocating Shared Costs

Certain costs do not belong solely to one team:

- Shared networking and NAT Gateways.
- Logging, monitoring, and security platforms.
- Enterprise Support.
- Shared databases or data platforms.
- Shared CI/CD runners.
- Data transfer shared across applications.

Cost Categories support split charge rules to distribute one category value across target values.

Three allocation methods:

| Method | Calculation | Example |
|---|---|---|
| Proportional | Weighted by direct cost share of target groups | Split shared platform proportionally to direct costs |
| Fixed | By organization-defined percentages | Engineering 60%, Marketing 30%, Finance 10% |
| Even | Split equally across target values | Three teams each receive one-third |

For example, Shared Platform is $2,000 USD. The organization chooses a fixed split:

- Engineering: 60% = $1,200 USD.
- Marketing: 30% = $600 USD.
- Finance: 10% = $200 USD.

Split charge rules only display the split allocation on the Cost Categories details page. This split does not appear in and does not modify AWS CUR or Cost Explorer. If financial systems need granular chargeback data in a data warehouse, implement the corresponding allocation logic in your internal pipeline and keep the formula auditable.

A category value can be used as a source only once across all split charge rules in a category. A value used as a source cannot simultaneously serve as a target. AWS limits the number of split charge rules per Cost Category; check current quotas before designing multi-tier allocations.

## 13. Showback and Chargeback Workflow

A mature workflow typically follows these steps:

1. **Capture:** collect usage and charges from all accounts.
2. **Normalize:** standardize account names, tag values, service names, and billing dimensions.
3. **Categorize:** apply Cost Categories and internal mappings.
4. **Allocate:** distribute shared costs, discounts, credits, and support per policy.
5. **Validate:** reconcile total allocations against the invoice and identify unallocated costs.
6. **Publish:** deliver reports by business unit, product, and application.
7. **Review:** meet with owners to explain variances and optimization actions.
8. **Reconcile:** archive snapshots and perform period-end reconciliation with Finance.

### 13.1 Chargeback Example

Suppose the final AWS invoice is $10,000 USD:

| Group | Direct Cost | Shared Cost Allocation | Internal Total |
|---|---:|---:|---:|
| Engineering | 4,000 | 1,200 | 5,200 |
| Marketing | 2,000 | 600 | 2,600 |
| Finance | 2,000 | 200 | 2,200 |
| **Total** | **8,000** | **2,000** | **10,000** |

This table represents an internal model. If the business applies markups, platform fees, or internal credits, the chargeback total may differ from the AWS invoice. In that case, include explicit adjustment lines and never label internal figures as the AWS invoice.

### 13.2 Discount Allocation Rules

Organizations must decide where discounts are recognized:

- The account purchasing the RI/SP.
- The account receiving the benefit.
- A shared discount pool.
- Business units weighted by usage share.
- A central cost center.

Choose one policy and apply it consistently. If you change discount sharing or allocation rules mid-month, record the effective date to explain variances.

## 14. AWS Cost Explorer

Cost Explorer analyzes historical cost and usage, compares time periods, forecasts spend, and identifies cost drivers.

Common dimensions:

- Linked account.
- Service.
- Region.
- Usage type.
- Instance type.
- Availability Zone.
- Purchase option.
- Cost allocation tag.
- Cost Category.

Available metrics include Unblended Cost, Amortized Cost, Net Amortized Cost, Usage Quantity, and other options depending on the report.

### 14.1 Questions Cost Explorer Answers

- Which account had the largest cost increase?
- Is EC2 or NAT Gateway driving cost growth?
- Is Product A production costing more than last month?
- Are Savings Plans coverage and utilization improving?
- In which Region or usage type did data transfer increase?
- Are costs grouped by Owner or Application tags missing coverage?

### 14.2 AWS CLI Examples

Retrieve costs by linked account and service for October 2026:

~~~bash
aws ce get-cost-and-usage \
  --time-period Start=2026-10-01,End=2026-11-01 \
  --granularity MONTHLY \
  --metrics UnblendedCost \
  --group-by Type=DIMENSION,Key=LINKED_ACCOUNT Type=DIMENSION,Key=SERVICE
~~~

Cost Explorer's End date is exclusive. The example above queries data from the start of October 1 up to (excluding) November 1 in UTC.

Retrieve daily amortized costs:

~~~bash
aws ce get-cost-and-usage \
  --time-period Start=2026-10-01,End=2026-11-01 \
  --granularity DAILY \
  --metrics AmortizedCost NetAmortizedCost \
  --group-by Type=DIMENSION,Key=LINKED_ACCOUNT
~~~

API and metric support may depend on billing data types. Check the AWS Cost Explorer API Reference and IAM permissions before automating.

## 15. AWS Data Exports and Cost and Usage Report 2.0

Cost and Usage Report (CUR) provides the most granular data on AWS costs and usage. AWS Data Exports is the current mechanism for creating exports, with CUR 2.0 as AWS's recommended choice for new granular cost/usage exports.

CUR 2.0 improvements include:

- A more stable schema with a consistent set of columns.
- Nested key-value columns to reduce data sparsity.
- Additional fields identifying accounts, principals, and cost analytics.
- Ability to select specific columns, filter rows, and configure exports with SQL via Data Exports capabilities.

### 15.1 Data Flow

~~~mermaid
flowchart LR
    A["AWS Billing data"] --> B["Data Exports - CUR 2.0"]
    B --> C["Amazon S3"]
    C --> D["AWS Glue Data Catalog"]
    D --> E["Amazon Athena"]
    E --> F["QuickSight / FinOps dashboard"]
    E --> G["Finance data warehouse"]
~~~

Data Exports writes files to Amazon S3. You can use Glue Catalog and Athena for querying, QuickSight for visualization, or internal pipelines for ERP/finance warehouse integration.

After creating an export, AWS may take up to 24 hours to begin delivering data. Once started, billing exports refresh at least daily. Current-month data can continue updating until the billing period closes and may be adjusted afterward.

### 15.2 Choosing Which Data to Export

Depending on objectives, you can create:

- CUR 2.0 standard export.
- Cost and usage dashboard export.
- Cost optimization recommendations export.
- FOCUS exports with AWS columns per supported versions.
- Carbon emissions data export.
- Legacy CUR export for older pipelines needing migration.

For new builds, prefer CUR 2.0. If existing pipelines rely on the legacy CUR schema, review the migration guide and verify compatible settings before switching production.

### 15.3 Commonly Used Data Fields

| Group | Example Fields |
|---|---|
| Billing | Billing period, payer account |
| Identity | Usage account ID, principal |
| Line item | Line item type, usage type, operation |
| Product | Product code, service attributes |
| Pricing | Public on-demand rate, pricing unit |
| Cost | Unblended cost, net unblended cost |
| Reservation | RI ARN, effective cost, unused commitment |
| Savings Plan | SP ARN, covered usage, effective cost |
| Resource tags | Resource tag key/value |
| Cost category | Cost category name/value |
| Split line item | Split cost allocation details if available |

Exact column names depend on the CUR 2.0 table and schema. Consult the CUR 2.0 table dictionary to confirm names before writing queries.

### 15.4 Athena Query Examples

Total unblended cost by account and service for a period:

~~~sql
SELECT
    line_item_usage_account_id AS account_id,
    line_item_product_code AS service,
    SUM(line_item_unblended_cost) AS unblended_cost
FROM cur2_database.cur2_table
WHERE bill_billing_period_start_date >= TIMESTAMP '2026-10-01 00:00:00'
  AND bill_billing_period_start_date < TIMESTAMP '2026-11-01 00:00:00'
GROUP BY
    line_item_usage_account_id,
    line_item_product_code
ORDER BY unblended_cost DESC;
~~~

Total cost by cost center tag if the CUR export includes the corresponding tag column:

~~~sql
SELECT
    resource_tags_user_costcenter AS cost_center,
    SUM(line_item_unblended_cost) AS unblended_cost
FROM cur2_database.cur2_table
WHERE bill_billing_period_start_date >= TIMESTAMP '2026-10-01 00:00:00'
  AND bill_billing_period_start_date < TIMESTAMP '2026-11-01 00:00:00'
GROUP BY resource_tags_user_costcenter
ORDER BY unblended_cost DESC;
~~~

These are illustrative templates. Replace database/table names, nested tag column names, and data types according to the schema created in your account. For queries involving nested columns, Data Exports supports configuring nested keys to be extracted as separate columns.

### 15.5 Securing CUR Data

CUR can contain detailed information about usage, accounts, resource IDs, tags, and pricing. You should:

- Use a dedicated S3 bucket for billing exports.
- Enable encryption with SSE-S3 or SSE-KMS as required.
- Use bucket policies restricting access to AWS delivery and analytical roles.
- Enable versioning if file history protection is needed.
- Apply lifecycle rules to transition storage classes or expire data per retention policy.
- Restrict Athena/Glue permissions and object read access.
- Never place CUR in a public bucket or share it broadly.
- Audit changes to Data Exports and bucket policies.

## 16. AWS Budgets and Cost Anomaly Detection

Cost allocation tells you who is spending money. Budgets and Anomaly Detection alert you when spending deviates from plan.

### 16.1 AWS Budgets

AWS Budgets can track:

- Cost budgets.
- Usage budgets.
- Savings Plans utilization/coverage budgets.
- Reserved Instances utilization/coverage budgets.

For example, Product A has a monthly budget of $8,000 USD. Configure alerts at 80%, 100% actual, and 110% forecasted. Send notifications to an SNS topic or email so the owner investigates.

Budget actions can execute supported responses, such as applying an IAM policy or SCP, but carefully assess the impact before automatically blocking resources. Do not use budget actions as a blanket kill switch across production workloads.

### 16.2 Cost Anomaly Detection

Cost Anomaly Detection uses machine learning to detect unusual spending relative to historical patterns. You can create monitors by AWS services, linked accounts, cost allocation tags, or Cost Categories depending on supported monitor types.

An anomaly is not necessarily an error. It could be legitimate traffic growth, a new campaign, a data migration, or an intentionally scaled workload. Handling workflow:

1. Receive alert.
2. Identify the relevant service, account, Region, and cost category.
3. Open Cost Explorer or CUR to pinpoint the usage type/resource.
4. Correlate with deployment/change events.
5. Confirm with the owner.
6. Document root cause and action taken.
7. Monitor until spend returns to baseline or is approved.

### 16.3 Billing Alerts

Billing preferences allow configuring alerts such as Free Tier usage alerts and CloudWatch billing alerts. Billing alerts should complement Budgets and Anomaly Detection, not replace product/team-level monitors.

## 17. AWS Billing Conductor for Showback and Chargeback

AWS Billing Conductor generates pro forma billing data by applying pricing plans, pricing rules, and custom line items to billing groups.

Key concepts:

| Component | Role |
|---|---|
| Billing group | Collection of accounts sharing a customer or billing view |
| Pricing plan | Set of pricing rules applied to a billing group |
| Pricing rule | Configured markup, discount, or custom pricing |
| Custom line item | Additional fee or credit line in a pro forma bill |
| Pro forma bill | Billing data computed under internal pricing configuration |
| Standard bill | Billable charges serving as the basis for the AWS invoice |

### 17.1 Pro Forma Is Not an AWS Invoice

Pro forma billing data is an alternative billing view generated from Billing Conductor configuration. It supports showback/chargeback or delivering billing views to end customers.

Pro forma data does not alter the standard AWS bill and does not change the amount AWS collects from the payer account. Keep the two data domains separate:

- Standard bill: actual amount payable to AWS.
- Pro forma bill: value computed according to internal pricing plans.

### 17.2 Pricing Plans

AWS provides managed pricing plans such as:

- BasicPricingPlan: calculates pro forma costs at base rates, excluding certain non-public discounts, credits, taxes, and support charges.
- Passthrough: passes through billable data to reflect the AWS invoice; applies only to Billing Transfer billing groups.

Customer-managed pricing plans allow creating custom pricing rules. One pricing plan can be assigned to multiple billing groups. When modifying a plan, current billing period data may be updated; check the impact on reports and CUR configurations.

### 17.3 Billing Groups

When using Billing Conductor standalone, a billing group is a set of accounts within a consolidated billing family sharing the same end customer. In the pro forma domain, usage is calculated as a separate billing family for that group; RIs/SPs and volume tiers are evaluated at the group scope per service rules.

When using Billing Transfer, a billing group maps one-to-one with the bill-transferring Organization. It does not alter how RIs/SPs and volume discounts are computed for that Organization.

### 17.4 Items That May Not Appear in Pro Forma Data

Depending on configuration and billing group type, pro forma data may omit or only partially reflect:

- Credits.
- Free Tier credits.
- Support plan charges.
- Non-public discounts.
- Usage-based bundled discounts.
- Taxes.
- Refunds.

Consequently, internal margins computed from pro forma data can fluctuate or even appear negative. When reconciling against the invoice, explicitly identify excluded items and how to account for them.

### 17.5 When Should You Use Billing Conductor?

- Service providers wanting to generate billing views for multiple customers.
- Platform teams wanting to apply internal markups or platform fees.
- Enterprises needing pro forma showback per business unit.
- Billing Transfer setups needing custom cost views for bill-source organizations.

If you only need cost reporting by account, tag, and service, Cost Explorer, Cost Categories, and CUR may already suffice. Do not add Billing Conductor without specific pricing/showback requirements.

## 18. Comparing Consolidated Billing, Cost Categories, and Billing Conductor

| Tool | Problem Solved | Does It Change the AWS Invoice? |
|---|---|---|
| AWS Organizations consolidated billing | Combines payments and usage across member accounts | Yes, the management account receives the consolidated bill |
| RI/SP discount sharing | Distributes commitment benefits across eligible accounts | Yes, affects billable costs |
| Cost allocation tags | Attaches metadata to resource costs | No |
| Cost Categories | Groups cost line items by rules | No |
| Cost Category split charges | Displays shared cost allocation across category values | No; split view only appears in Cost Categories details |
| AWS Billing Conductor | Generates pro forma pricing and custom line items | No; the standard bill does not change |
| Billing Transfer | Transfers consolidated bill management/payment across Organizations | Changes the paying account; does not merge discount boundaries |

These are complementary layers that combine rather than replace each other. An Organization can use consolidated billing, tags, Cost Categories, CUR, and Budgets together. Billing Conductor is only needed when pro forma pricing or billing transfer integration is required.

## 19. Access Control and Security for Billing Data

Billing data is sensitive financial information. Grant access by role:

| Role | Appropriate Permissions |
|---|---|
| Finance approver | View invoices, payments, credits, and billing reports |
| FinOps analyst | Cost Explorer, Budgets, Cost Categories, CUR |
| Platform engineer | View costs for assigned accounts/workloads without payment permissions |
| Billing administrator | Manage billing preferences, exports, and billing settings |
| Auditor | Read-only access and change history |

Principles:

- Use IAM Identity Center and role-based access.
- Grant fine-grained Billing and Cost Management actions rather than overly broad permissions.
- Separate cost read permissions from permissions to modify payment methods.
- Restrict permissions to edit Cost Categories, Data Exports, billing groups, and pricing plans.
- Protect the management account and root user.
- Protect the CUR S3 bucket with encryption and least privilege.
- Use CloudTrail to audit changes to billing preferences, Organizations, and IAM.
- Review access periodically and upon role changes.

Member accounts can be granted access to view their own billing data. Access to Organization-wide billing data must be governed from the management account and corresponding Cost Explorer/Billing access controls.

## 20. Monthly Billing Governance Workflow

A FinOps cycle may include:

### During the Month

- Monitor Cost Explorer and Budgets.
- Act on Cost Anomaly Detection alerts.
- Check tag coverage and unallocated costs.
- Track RI/SP utilization and coverage.
- Confirm owners for cost spikes.
- Update forecasts for releases, campaigns, or migrations.

### Month-End

- Close the billing period and invoice.
- Reconcile Bills against Cost Explorer and CUR.
- Verify credits, refunds, taxes, and Marketplace charges.
- Run Cost Categories and shared cost allocation.
- Export reports by account, cost center, product, and application.
- Publish showback/chargeback.
- Document variances against budget.

### Post-Reconciliation

- Confirm increases/decreases with service owners.
- Create action items for resource optimization.
- Update budgets/forecasts if workloads have shifted.
- Archive report snapshots, queries, rule versions, and approvals.
- Track execution of action items in the next period.

## 21. Example FinOps Architecture for a Multi-Product Enterprise

An enterprise has three product accounts, one shared infrastructure account, and one management account.

- The management account pays the consolidated bill.
- Product accounts apply Application, Environment, CostCenter, and Owner tags.
- The shared infrastructure account hosts Transit Gateway, NAT, logging, and monitoring.
- A Cost Category groups Product A, Product B, Product C, and Shared Platform.
- Split charge rules allocate Shared Platform by traffic share or fixed percentages.
- CUR 2.0 exports into S3.
- Athena calculates direct costs by account/tag and joins internal split allocation tables.
- QuickSight displays dashboards by business unit.
- AWS Budgets and Cost Anomaly Detection send alerts to owners.

~~~mermaid
flowchart TD
    A["AWS Organizations"] --> B["Management account / consolidated bill"]
    A --> C["Product accounts"]
    A --> D["Shared infrastructure account"]
    C --> E["Resource tags"]
    D --> E
    B --> F["Cost Categories"]
    E --> F
    B --> G["CUR 2.0 Data Export"]
    F --> G
    G --> H["S3 + Athena"]
    H --> I["FinOps data model"]
    I --> J["Showback / Chargeback dashboard"]
    B --> K["Budgets / Anomaly Detection"]
    K --> L["Owner alerts"]
~~~

The key point is that shared cost allocation needs an explicit driver and owner. For example, NAT Gateways can be allocated by GB processed; logging platforms by ingest volume; security platforms by account or workload count. Choose drivers as close as possible to actual consumption.

## 22. Lab: Building a Cost Allocation Report for an Organization

Use a sandbox account or an AWS environment with appropriate billing permissions. Do not modify billing preferences in a production Organization without approval.

### Step 1: Identify Account Structure

Select a management account and at least two member accounts representing two products. Record account IDs and owners.

### Step 2: Standardize Tag Taxonomy

Apply the following keys:

- CostCenter
- Application
- Environment
- Owner

Example for a production resource:

~~~yaml
CostCenter: CC-ENG-001
Application: storefront
Environment: prod
Owner: team-commerce
~~~

Ensure tag values conform to the catalog approved by Finance and the Platform team.

### Step 3: Activate Cost Allocation Tags

In the management account:

1. Open Billing and Cost Management.
2. Select Cost allocation tags.
3. Select the user-defined tag keys.
4. Activate the required keys.
5. Wait for data to populate and verify in Cost Explorer.

If a tag key does not appear immediately, verify that the resource/service supports tagging and allow time for billing data updates.

### Step 4: Create a Cost Category

Create a Cost Category named `BusinessUnit` or `Product`. Use linked accounts to group Product A and Product B. Add a default value `Unallocated` for costs not matching any rule.

If you have a shared platform, create a `SharedPlatform` value to classify it before building split charge rules.

### Step 5: Create a CUR 2.0 Export

In Billing and Cost Management:

1. Select Data Exports.
2. Create a Standard data export.
3. Choose Cost and Usage Report 2.0.
4. Select the columns needed for analysis, including resource IDs if needed.
5. Choose the S3 destination.
6. Configure encryption and the bucket policy.
7. Create the export and wait for AWS to begin delivery.

### Step 6: Analyze in Cost Explorer

Build reports:

- Group by Linked account.
- Filter by service.
- Group by Cost allocation tag `Application`.
- Select Amortized Cost to evaluate commitments.
- Compare the current month against the same timeframe last month.

### Step 7: Create Budgets and Anomaly Monitors

Create budgets for each Product or Cost Category. Set actual/forecast thresholds. Create appropriate Cost Anomaly Detection monitors and subscriptions sending alerts to owners.

### Step 8: Produce a Showback Report

Aggregate direct costs, shared costs, discounts, and unallocated costs. If using split charge rules, verify figures on the Cost Categories details page. Reconcile total allocations against the consolidated bill.

### Step 9: Cleanup

Delete test budgets, anomaly subscriptions, Cost Categories, or Data Exports no longer needed. Do not delete production CUR buckets in use by Finance systems. Document configurations and report ownership.

## 23. Common Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Member account does not see consolidated bill | Viewing member account view instead of management account | Sign in to the management account and check billing permissions |
| Management account does not see new account | Invitation not accepted or account not yet in Organization | Check Organizations membership and join timestamp |
| Volume discount not as expected | Service has no matching tier or usage dimensions differ | Check pricing dimensions and consolidated usage |
| RIs/SPs not shared | Discount sharing disabled or usage incompatible | Check owner account, sharing preference, Region/scope, and instance family |
| Cost allocation tag missing | Not activated, resource unsupported, or insufficient propagation time | Check tag key, service support, and update delay |
| Tag on resource but missing in CUR | Tag not activated for billing or resource not metered/taggable | Activate key and verify in cost allocation report |
| Cost Category assigns wrong value | Rule ordering or overlapping conditions | Place specific rules first; check preview and Applied status |
| Shared cost not split | Source value not categorized or invalid rule | Check source/targets, method, and category status |
| Split charge missing in CUR | Split allocation only appears on Cost Categories details | Use the details page or replicate allocation in internal pipeline |
| No CUR 2.0 files yet | Newly created export or S3 delivery not yet started | Wait up to initialization window and check bucket policy |
| Athena query fails with column not found | Different nested key name or schema | Check CUR 2.0 table dictionary and Data Export configuration |
| Cost Explorer differs from invoice | Cash vs. amortized view, refresh timing, grouping, refunds, or rounding | Match exact cost metric and use final invoice for payment |
| Pro forma differs from standard bill | Pricing plan, excluded credits/tax/support, or custom line items | Compare billing domains and Billing Conductor rules |
| Billing Transfer makes CUR unhealthy | Old CUR configuration invalid after transfer | Recreate Data Exports/CUR under the new billing view |
| Bill-source account has no Cost Anomaly alerts | Cost Anomaly Detection does not support bill-source usage in Billing Transfer | Use appropriate monitors at bill-transfer scope and supplementary tools |
| Unallocated costs rising | Missing tags, account mapping, or default Cost Category | Report Unallocated items and have owners add metadata |

## 24. Best Practices for Billing and FinOps

### Accounts and Organizations

- Use the management account strictly for Organizations administration and billing.
- Separate workloads along meaningful product, environment, or security boundaries.
- Maintain clear account owners and cost owners.
- Use consolidated billing to centralize payment and aggregate usage within the Organization.
- Evaluate Billing Transfer when centralizing multiple Organizations.
- Do not assume Billing Transfer merges RI/SP discount boundaries across Organizations.

### Discounts and Commitments

- Monitor RI/SP utilization and coverage.
- Start with open sharing if the goal is maximizing Organization-wide discounts.
- Use group sharing when business-unit discount isolation is required.
- Simulate impact before changing sharing preferences.
- Manage credit sharing separately from RI/SP discount sharing.
- Allocate discounts under a consistent internal policy.

### Cost Allocation

- Standardize tags before scaling account counts.
- Combine account dimensions, resource tags, account tags, and Cost Categories.
- Activate required tag keys in the Billing console.
- Include a default `Unallocated` value and monitor coverage.
- Use Cost Categories for business mapping and shared cost grouping.
- Document split charge formulas and shared service owners.
- Do not rely on Cost Category split charges as a CUR replacement, since split views are not written to CUR/Cost Explorer.

### Data and Reporting

- Use Bills for invoice reconciliation.
- Use Cost Explorer for analysis and forecasting.
- Use CUR 2.0/Data Exports for granular data and data pipelines.
- Protect the CUR S3 bucket with encryption, IAM, and lifecycle policies.
- Keep queries and dashboards in version control.
- Label metric types explicitly: Unblended, Net Unblended, Amortized, or Net Amortized.
- Avoid comparing reports with different billing periods, granularities, or cost bases.

### Governance

- Separate cost read permissions from payment management permissions.
- Use Budgets, Cost Anomaly Detection, and owner alerts.
- Hold a monthly variance review workflow.
- Retain reconciliation evidence and approvals.
- Audit tag coverage, unallocated costs, and shared cost allocation monthly.
- Conduct periodic reviews across Engineering, Product, Finance, and Procurement.

## 25. Practice Exercises

1. What is consolidated billing in AWS Organizations?
2. How do a management account and a member account differ?
3. Does consolidated billing merge multiple AWS accounts into a single account?
4. Why can consolidated billing yield better volume discounts?
5. What conditions govern RI and Savings Plans sharing?
6. How do open sharing, prioritized group sharing, and restricted group sharing differ?
7. Why must credit sharing be evaluated separately?
8. If an account joins an Organization mid-month, how are charges before and after joining handled?
9. How does Billing Transfer differ from consolidated billing?
10. Does Billing Transfer pool RI/SP discounts across two Organizations?
11. How do showback and chargeback differ?
12. Why is applying resource tags alone insufficient for them to appear in cost reports?
13. Where must cost allocation tags be activated?
14. What value do account tags add beyond resource tags?
15. Which dimensions can Cost Categories use to group costs?
16. Why does Cost Category rule ordering matter?
17. How do proportional, fixed, and even splits differ?
18. Why do split charges not appear in CUR?
19. How do Bills and Cost Explorer differ regarding cash basis vs. amortized basis?
20. What is CUR 2.0 used for?
21. How long can Data Exports take to start delivering data?
22. Why does a CUR bucket require encryption and least privilege?
23. Does AWS Billing Conductor pro forma data change the AWS invoice?
24. When should Billing Conductor be used?
25. If Cost Explorer differs from the month-end invoice, which source governs payment?

### Suggested Answers

1. An AWS Organizations mechanism that consolidates billing and payment across multiple accounts into the management account.
2. The management account owns the Organization and pays the consolidated bill; a member account hosts workloads and has billing scoped to its account.
3. No. Each account remains a separate resource, IAM, and security boundary.
4. AWS combines usage across accounts when calculating volume pricing tiers.
5. The commitment-owning account must enable sharing; consuming usage must match scope, Region, and service eligibility.
6. Open sharing shares with all enabled accounts; prioritized prioritizes groups; restricted shares only within defined groups.
7. Because credit sharing has separate preferences from RI/SP discount sharing.
8. The management account is responsible for charges from the time the account accepts the invitation; the previous owner covers prior charges.
9. Consolidated billing groups accounts within one Organization; Billing Transfer transfers consolidated bill management/payment between management accounts of multiple Organizations.
10. No. Each Organization remains its own discount computation boundary.
11. Showback provides visibility; chargeback allocates costs into internal cost centers or ledgers.
12. Because the tag key must be activated in Billing and Cost Management and takes time to propagate.
13. Under Cost allocation tags in the Billing and Cost Management console or API.
14. Account tags help allocate costs that cannot receive resource tags, including certain credits, refunds, and service charges.
15. Accounts, tags, charge types, services, Regions, usage types, billing entities, and supported category dimensions.
16. Rules are evaluated top-down; the first matching rule determines the category value.
17. Proportional splits by target group cost share, fixed splits by defined percentages, and even splits equally.
18. Split charges appear only on the Cost Categories details page and do not modify CUR or Cost Explorer.
19. Bills are cash basis reflecting amounts due; Cost Explorer can amortize commitments over time.
20. CUR 2.0 provides granular cost/usage details for querying and analytical pipeline integration.
21. Up to 24 hours to begin delivery; afterward it refreshes at least daily.
22. Because CUR contains potentially sensitive cost, account, resource, and tag data.
23. No. Pro forma is a simulated billing view; the standard AWS bill remains unchanged.
24. When internal pricing, markups, custom line items, billing groups, or showback/chargeback via billing transfer are needed.
25. The final AWS invoice is the basis for payment.

## 26. Interview Questions

### Why use multiple AWS accounts instead of one large account?

Multiple accounts isolate security boundaries, quotas, environments, ownership, and billing dimensions. Consolidated billing still aggregates payment and usage across the Organization.

### Does consolidated billing automatically allocate discounts to the right product owner?

Not according to desired internal governance models. AWS applies discounts based on billing rules and sharing preferences. Enterprises still need internal discount allocation policies and reporting by account/tag/category.

### When should you use Cost Categories instead of resource tags?

Use tags when metadata needs to be attached directly to resources. Use Cost Categories when grouping line items by account, service, usage type, charge type, or combinations of dimensions, and when mapping onto business structures.

### Why do you need both Cost Categories and CUR 2.0?

Cost Categories provide business mapping within Cost Management tools. CUR 2.0 supplies granular cost/usage rows for querying, reconciliation, and data warehouse integration. They complement each other.

### Can split charges be used to record shared costs in CUR?

No. Cost Categories split charge allocations appear only on the category details page and do not alter CUR or Cost Explorer. To bring allocations into a general ledger, implement the logic internally and document the formula.

### How does Billing Conductor differ from Cost Categories?

Cost Categories classify line items without altering AWS pricing. Billing Conductor creates pro forma billing using pricing plans, pricing rules, and custom line items to support showback/chargeback. Pro forma is not an AWS invoice.

### Why separate cash basis and amortized cost?

Cash basis supports reconciling payments collected by AWS in the period. Amortized basis spreads commitment costs over time to assess workload economics. Mixing the two leads to wrong conclusions about cost trends.

### Is Billing Transfer a way to pool discounts across multiple Organizations?

No. Billing Transfer centralizes bill management and payment across multiple Organizations. RIs/SPs and volume discounts are still calculated separately within each Organization.

### How can you reduce unallocated costs?

Standardize account structure and tag taxonomy, activate cost allocation tags, use account tags, create Cost Categories with a default `Unallocated` value, and require owners to remediate untagged spend.

### What makes a chargeback dashboard trustworthy?

It must clearly show direct costs, shared cost allocations, discount/credit policies, billing period, cost basis, owners, unallocated costs, data sources, and reconciliation with the invoice.

## 27. Production Checklist for Billing and FinOps

### Organization and Billing

- [ ] Management account is protected with MFA and root security controls.
- [ ] Application workloads do not run in the management account.
- [ ] Member accounts have defined owners and cost owners.
- [ ] Consolidated billing is properly configured.
- [ ] SOR and invoice routing are confirmed.
- [ ] RI/SP discount sharing preferences are reviewed.
- [ ] Credit sharing preferences are reviewed separately.
- [ ] Billing Transfer is enabled only after evaluating historical data and discount boundaries.

### Cost Allocation

- [ ] Account structure reflects product/environment/business boundaries.
- [ ] Tag taxonomy has assigned owners and an approved value catalog.
- [ ] Tag keys are applied across supported resources.
- [ ] Cost allocation tags are activated.
- [ ] Account tags are used for items that cannot carry resource tags.
- [ ] Cost Categories define rule ordering and a default `Unallocated` value.
- [ ] Shared costs have documented drivers and allocation methodology.
- [ ] Discount allocation policy is documented.

### Reporting and Data

- [ ] Bills are used for invoice reconciliation.
- [ ] Cost Explorer is configured for owners.
- [ ] CUR 2.0/Data Exports deliver to S3.
- [ ] CUR bucket has encryption, IAM controls, and lifecycle policies.
- [ ] Athena/QuickSight queries are under version control.
- [ ] Cost basis and billing period are labeled on dashboards.
- [ ] Billing Conductor pro forma views are distinguished from standard bills.

### Governance and FinOps Operations

- [ ] AWS Budgets are configured per business unit/product.
- [ ] Cost Anomaly Detection monitors have assigned owners.
- [ ] Alerts have a defined escalation path.
- [ ] Finance and Engineering conduct monthly cost reviews.
- [ ] Unallocated costs are actively tracked.
- [ ] Chargeback totals reconcile with the invoice.
- [ ] Audit trails exist for billing preferences, cost categories, and pricing plans.
- [ ] Billing permissions are reviewed periodically.

## 28. Official References

- [Consolidating billing for AWS Organizations](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/consolidated-billing.html)
- [Finding the seller of record](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/finding-the-seller-of-record.html)
- [Consolidated billing process](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/useconsolidatedbilling-procedure.html)
- [Effective billing date, account activity, and volume discounts](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/useconsolidatedbilling-effective.html)
- [Understanding consolidated bills](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/con-bill-blended-rates.html)
- [Customizing your Billing preferences](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/billing-pref.html)
- [Applying AWS credits](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/useconsolidatedbilling-credits.html)
- [Transfer billing management to external accounts](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/orgs_transfer_billing.html)
- [Organizing and tracking costs using AWS cost allocation tags](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/cost-alloc-tags.html)
- [Using user-defined cost allocation tags](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/custom-tags.html)
- [Activating user-defined cost allocation tags](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/activating-tags.html)
- [Using account tags for cost allocation](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/account-tags-cost-allocation.html)
- [Organizing costs using AWS Cost Categories](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/manage-cost-categories.html)
- [Creating cost categories](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/create-cost-categories.html)
- [Splitting charges within cost categories](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/splitcharge-cost-categories.html)
- [Knowing the differences between Billing and Cost Explorer data](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/differences-billing-data-cost-explorer-data.html)
- [Understanding your bill](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/getting-viewing-bill.html)
- [AWS Data Exports](https://docs.aws.amazon.com/cur/latest/userguide/)
- [Creating data exports](https://docs.aws.amazon.com/cur/latest/userguide/dataexports-create.html)
- [Migrating from CUR to Data Exports CUR 2.0](https://docs.aws.amazon.com/cur/latest/userguide/dataexports-migrate.html)
- [Understanding the Cost and Usage Report](https://docs.aws.amazon.com/cur/latest/userguide/dataexports-cur-info.html)
- [Cost and Usage Report 2.0 table dictionary](https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-cur2.html)
- [Understanding export delivery](https://docs.aws.amazon.com/cur/latest/userguide/dataexports-export-delivery.html)
- [AWS Billing Conductor - Pro forma billing data](https://docs.aws.amazon.com/billingconductor/latest/userguide/understanding-proforma.html)
- [AWS Billing Conductor - Billing groups](https://docs.aws.amazon.com/billingconductor/latest/userguide/creating-abc.html)
- [AWS Billing Conductor - Pricing plans](https://docs.aws.amazon.com/billingconductor/latest/userguide/abc-pricingplan.html)
- [AWS Cost Explorer User Guide](https://docs.aws.amazon.com/cost-management/latest/userguide/what-is-costmanagement.html)
- [Creating a cost budget](https://docs.aws.amazon.com/cost-management/latest/userguide/create-cost-budget.html)
- [Getting started with AWS Cost Anomaly Detection](https://docs.aws.amazon.com/cost-management/latest/userguide/getting-started-ad.html)
