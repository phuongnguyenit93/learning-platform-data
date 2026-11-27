# Cost Analysis, Cost Reports, and Cost Allocation with Tags

## 1. From Tenancy Total Cost to Team Accountability

In the **Cost and Capacity Management** chapter of the **CLOUD_PROVIDERS_ORACLE** module, this lesson focuses on three sequential tasks: locating where costs originate with Cost Analysis, extracting detailed data with cost reports, and allocating costs to applications or business units using tags.

An OCI system may consist of Compute running Java applications, boot volumes and block volumes, Object Storage holding backups, and Oracle database services. Looking at Compute cost alone does not reveal the full cost of operating an application. Conversely, total tenancy cost does not answer which team is responsible for the increase.

Suppose an enterprise has two applications, `payments` and `analytics`, sharing a central log ingestion platform. The owner needs to answer:

- Which service, region, or application drove the cost increase?
- Which items can be attributed directly to a cost center?
- By what criteria is the shared platform split?
- How much spend lacks sufficient metadata for allocation?
- Does the allocation output preserve the exact source cost total?

After this lesson, learners can build a report that explains these numbers, identify the data source for each figure, and know which items require coordination with finance before closing the period.

## 2. Distinguish Three Layers of Information

| Layer | Tool or data | Intended use |
| --- | --- | --- |
| Discovery | Cost Analysis | Narrow down trends and areas needing investigation |
| Granular detail | Cost reports | Trace consumption line items and build analytical datasets |
| Internal allocation | Business rules combining tags, owner catalogs, and usage metrics | Determine the amount each unit bears |

**Showback** presents each team's costs so teams understand and take ownership. **Chargeback** goes a step further: using approved results to record or recover internal charges. An initial showback report may tolerate unallocated items, whereas chargeback requires rules for handling them and a clear adjustment workflow.

Also distinguish a **saved report** from a **cost report**. A saved report stores an analysis configuration to reopen later; it does not replace the collected granular dataset. When needing to reproduce a closed result, store both the input dataset and the allocation ruleset version.

An overarching principle is:

~~~text
Observed costs
    → define scope and data source
    → classify direct / shared / unallocated
    → apply allocation rules
    → reconcile and publish
~~~

Tags provide identification labels. Deciding the ratio used to split a shared cost remains an organizational decision.

## 3. Prepare Scope and Access Permissions

### 3.1. State Scope Explicitly Before Comparing

Every report should contain at least the following information:

| Attribute | Example for an illustrative period |
| --- | --- |
| Tenancy and subscription | Record OCID or agreed identifier |
| Analysis period | October 2026 |
| Standard timezone | UTC |
| Currency | USD |
| Metric | Consumption cost per selected source |
| Scope | All relevant regions |
| Data extraction timestamp | Record actual extraction timestamp |
| Status | Provisional or finalized per internal process |

Do not sum multiple currencies directly. If management reporting requires VND, preserve original currency amounts, exchange rate, rate date, and rounding rules.

For Vietnam, `2026-10-01 00:00:00 UTC` is `07:00:00` on the same day in local time. If an organization closes periods in Vietnam time, shift period boundaries consistently; do not take a UTC month from one source and compare it against a local-time month from another.

### 3.2. Separate Cost Viewing Permissions from Report Administration

Sample policy for a team viewing Cost Analysis:

~~~text
Allow group FinOpsReaders to read usage-report in tenancy
~~~

To manage saved reports, OCI documentation uses the `manage usage-report` permission. Grant this only to groups that truly need to manage report configurations. Group reference syntax must match the tenancy's identity domain. See [IAM permissions for Cost Analysis](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/costanalysisoverview.htm#RequiredIAMPolicy).

The `usage-report` permission does not equal permission to read every cost report object. Downloading Oracle-hosted files requires corresponding access policies to the report storage location. [Downloading a Cost Report](https://docs.oracle.com/en-us/iaas/Content/Billing/Tasks/download-cost-usage-report.htm) provides sample `define tenancy` and `endorse group` policies; the tenancy OCID in that sample is Oracle's tenancy, not a customer tenancy OCID to swap arbitrarily.

Do not use compartment or tag filters on a screen as proof that a user can only view one team's costs. Filters serve analysis; access boundaries must be enforced at the IAM layer and where datasets are shared. For per-team reporting, export scope-filtered datasets into an organization-controlled reporting store with read permissions.

## 4. Design Tags to Identify Costs

### 4.1. Start from Dimensions Tied to Business Decisions

An illustrative set of defined tags:

| Namespace and key | Example value | Meaning |
| --- | --- | --- |
| `Finance.CostCenter` | `CC100` | Cost-bearing unit |
| `Finance.Application` | `payments` | Application or product |
| `Finance.Environment` | `prod` | Operating environment |
| `Finance.OwnerTeam` | `payments-platform` | Team contacted for verification |
| `Finance.AllocationMode` | `direct` or `shared` | Routing to allocation rules |

This is an example convention, not a prebuilt OCI tag set. Before applying, create the namespace and corresponding keys.

Choose dimensions that have active maintainers. For instance, employee names change frequently and can introduce personal data into reporting datasets; team codes are usually better suited for `OwnerTeam`.

**Defined tags** have organization-managed namespaces and definitions. **Free-form tags** are convenient for ad-hoc labels but harder to standardize. Oracle recommends defined tags for governance data; marking a tag as cost-tracking is not required for it to appear in Cost Analysis or Cost and Usage Reports. See [Overview of Tagging](https://docs.oracle.com/en-us/iaas/Content/Tagging/Concepts/taggingoverview.htm).

If you encounter older guides requiring "enable cost-tracking before analyzing costs," verify against current documentation before making that step mandatory.

### 4.2. Define Valid Values

The organization should standardize:

- `prod`, `test`, and `dev` are the environment values used in the examples.
- `CC100` and `CC200` are valid codes from the internal cost center catalog.
- `SHARED` is an owner-approved bucket awaiting allocation.
- Blank values, unlisted codes, or conflicting application–cost center pairs must all be routed to an exception list.

Having a tag present is not enough to prove the tag is accurate. A resource tagged `CostCenter=CC100` that actually serves `analytics` may still require verification.

OCI supports predefined value lists and can combine them with tag defaults requiring resource creators to enter a value. This helps reduce manual typos. See [Using Predefined Values](https://docs.oracle.com/en-us/iaas/Content/Tagging/Tasks/usingpredefinedvalues.htm).

### 4.3. Apply Tags to the Exact Cost-Generating Resources

Example `definedTags` payload snippet when creating a resource that supports defined tags:

~~~json
{
  "definedTags": {
    "Finance": {
      "CostCenter": "CC100",
      "Application": "payments",
      "Environment": "prod",
      "OwnerTeam": "payments-platform",
      "AllocationMode": "direct"
    }
  }
}
~~~

This is only the metadata snippet, not a complete payload to create a Compute instance or database. When using Terraform or other tools, field representation may differ.

List all components serving the application: instances, volumes, buckets, databases, and related items. Verify tags on each resource type and in actual cost data. Do not assume tagging an instance automatically applies the same tag to all attached volumes, backups, or service-created components.

Likewise, a tag on a bucket only describes the bucket. If multiple applications store data inside it, a single label does not tell you how much storage each application occupies or how many requests it makes. When that granularity is needed, the organization must supplement usage metrics and split rules.

### 4.4. Tag Defaults and Timing Factors

Tag defaults apply to new resources created within a compartment, including inheritance down to child compartments. They do not retroactively tag existing resources; changing a default value does not modify previously applied tags either. See [Managing Tag Defaults](https://docs.oracle.com/en-us/iaas/Content/Tagging/Tasks/managingtagdefaults.htm).

Therefore, a practical rollout plan consists of two tracks:

1. Set rules for new resources via tag defaults or infrastructure provisioning pipelines.
2. Audit existing resources and backfill tags after confirming owners.

Cost Analysis records costs according to when a tag is associated with a resource, rather than retroactively reclassifying all prior spend. See [notes on tag application timing](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/costanalysisoverview.htm).

For example, a volume accrues cost starting day 1 but is tagged `CC100` only on day 15. Do not expect a tag query to immediately attribute the entire first half of the month to `CC100`.

If historical reallocation is required, build an effective-dated mapping table in the internal reporting system:

| Resource | Cost center | Effective from | Effective to | Basis |
| --- | --- | --- | --- | --- |
| `volume-A` | `CC100` | `2026-10-01T00:00:00Z` | `2026-10-15T00:00:00Z` | Owner confirmation and deployment records |

This mapping layer adds a business view. Preserve source data unchanged so you can explain why internal reports classify items differently from OCI tag queries.

## 5. Use Cost Analysis to Narrow Down Spend

In the Console, open **Billing & Cost Management → Cost Management → Cost Analysis**. Choose a UTC date range, display Cost, apply filters and appropriate grouping dimensions, then inspect the results table. Frequently used views can be saved as a saved report. See [Cost Analysis](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/costanalysisoverview.htm).

Instead of adding all filters up front, run a purposeful investigation sequence:

| Analysis pass | Suggested setup | What to learn |
| --- | --- | --- |
| Period overview | Broad scope, grouped by service | Which services make up most of the total |
| Spike investigation | Same scope, daily granularity | When the increase started |
| Infrastructure isolation | Filter relevant region or compartment | Where the change is concentrated |
| Accountability check | Group by `Finance.CostCenter` tag | Which teams receive direct charges |
| Missing spend trace | Reconcile against granular data | Which items remain unidentified |

For each pass, record filters and totals. If the total drops after adding a tag filter, the difference may be spend not matching the filter; do not assume those costs disappeared.

A common mistake is entering multiple conditions and interpreting them as an intersection without checking tool logic. Inspect representative result rows before treating a query as an official report, especially when combining multiple tag conditions.

When comparing two periods, control for day count and data completeness. Twenty days of cost is not equivalent to a full month. You can compute average daily cost for preliminary observation, then factor in weekends, batch processing, and business events.

Also separate **cost** from **usage**. Two services can both rise in cost while using different units. Do not sum OCPU-hours, GB-months, and requests into one meaningful usage total. To explain a spend increase, review usage quantity, billing unit, and the corresponding price component together.

## 6. Use Cost Reports as Granular Data

### 6.1. Choose the Input Format

OCI provides cost reports in its native format and in FOCUS format. Legacy usage reports were deprecated from recommended use as of January 31, 2025; new pipelines should rely on cost reports. The **Cost Report Types** section describes roughly six-hour generation cycles, latency up to 24 hours, and one-year retention. See [Cost Reports](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/costusagereportsoverview.htm).

Pick one format as the primary source for a given scope. If ingesting both native and FOCUS formats for verification, keep them in separate datasets; do not union both sets and sum costs, as that double-counts the same consumption.

| Choice | When appropriate |
| --- | --- |
| OCI native format | Need analysis using native OCI fields |
| FOCUS | Need standardized input for multi-cloud analytics |

Commonly used fields in the native format:

| Field | Role |
| --- | --- |
| `lineItem/intervalUsageStart` | UTC usage start timestamp |
| `product/resourceId` | Resource identifier |
| `product/compartmentId` | Compartment identifier |
| `cost/productSku` | SKU |
| `cost/myCost` | Line cost |
| `cost/currencyCode` | Currency |
| `tags/…` | Classification labels |

Full field names and semantics are in the [OCI cost reports schema](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/costusagereportsoverview.htm#CostReportTypes). When building a CSV parser, read column names from the actual header and verify against the schema; do not guess tag column names from how they display in the Console.

### 6.2. Distinguish Usage Time from Data Receipt Time

The reporting system should store at least two timestamps:

- **Usage time** to assign each charge to the right period.
- **Ingestion time** to know which data snapshot produced a result.

A file received today may contain usage data from prior days. Reading only files whose creation date matches the target reporting date can miss late-arriving data.

You can apply a re-reconciliation window, such as re-reading recent days and widening the read window at period close. This is an organizational design choice tuned to observed data; do not treat a single daily run as proof that data is complete.

### 6.3. Download Reports from the Console

Switch to the tenancy's **home region** and open **Cost and Usage Reports**. Select the report and download action; FOCUS reports are organized by usage date in the interface. See [Listing Cost Reports](https://docs.oracle.com/en-us/iaas/Content/Billing/Tasks/list-cost-usage-report.htm).

When pulling data for a period, maintain a manifest of downloaded objects and preserve source naming structure. Do not just grab the first file seen. Use the manifest to track which run processed which objects and explain differences between two aggregations.

## 7. Automate Retrieval with OCI CLI

The commands below target **Bash**, such as in OCI Cloud Shell. They illustrate read operations; learners must substitute placeholder values and have proper authentication and IAM policies configured. Do not store API keys or private keys in exercise source code.

### 7.1. Query Summaries by Service and Region

~~~bash
TENANCY_OCID='<your-tenancy-ocid>'
HOME_REGION='<your-home-region>'

oci usage-api usage-summary request-summarized-usages \
  --tenant-id "$TENANCY_OCID" \
  --time-usage-started '2026-10-01T00:00:00Z' \
  --time-usage-ended '2026-11-01T00:00:00Z' \
  --granularity DAILY \
  --query-type COST \
  --group-by '["service","region"]' \
  --region "$HOME_REGION"
~~~

The command selects cost data instead of usage metrics and groups across two dimensions. You can use `--group-by-tag` with the JSON structure specified in CLI documentation to analyze a specific key. When automating, handle pagination if responses include a next page; do not pass a small `--limit` and treat the output as complete data. See [request-summarized-usages](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/usage-api/usage-summary/request-summarized-usages.html).

Usage API uses an inclusive start timestamp and an exclusive end timestamp. The range above is `[10/01, 11/01)` in UTC. See [Usage API guide in Cost Analysis](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/costanalysisoverview.htm#UsingtheAPI).

When scheduling runs, generate both boundaries from the same calendar rule. Do not combine `[day 1, day 2]` and `[day 2, day 3]` in a way that accidentally counts day 2 twice.

### 7.2. List and Download Cost Report Objects

Oracle uses the `bling` namespace and a bucket named after the customer's tenancy OCID to deliver these reports. Sample listing command:

~~~bash
oci os object list \
  --namespace-name bling \
  --bucket-name "$TENANCY_OCID" \
  --prefix 'reports/cost-csv' \
  --region "$HOME_REGION" \
  --all
~~~

Take the **exact object name** from the list output and download it:

~~~bash
REPORT_OBJECT_NAME='<exact-object-name-from-list>'

oci os object get \
  --namespace-name bling \
  --bucket-name "$TENANCY_OCID" \
  --name "$REPORT_OBJECT_NAME" \
  --file './cost-report.csv.gz' \
  --region "$HOME_REGION"
~~~

Do not create a `bling` bucket inside your own tenancy and do not guess filenames from dates. See [listing cost reports via CLI](https://docs.oracle.com/en-us/iaas/Content/Billing/Tasks/list-cost-usage-report.htm) and [downloading a cost report via CLI](https://docs.oracle.com/en-us/iaas/Content/Billing/Tasks/download-cost-usage-report.htm).

The fixed local filename in the example is only for downloading one object. When downloading multiple objects, map each source name to a unique local path so prior files are not overwritten. Check the download command's exit code before decompressing and ingesting data.

## 8. Build Traceable Allocation Data

A recommended processing pipeline:

~~~mermaid
flowchart LR
    A[Cost reports] --> B[Store raw data and manifest]
    B --> C[Normalize and reconcile]
    D[Cost center catalog] --> E[Classify costs]
    F[Effective-dated historical mapping] --> E
    C --> E
    E --> G[Direct costs]
    E --> H[Shared costs]
    E --> I[Unallocated]
    J[Metrics and split rules] --> K[Allocate shared pool]
    H --> K
    G --> L[Report and reconcile totals]
    K --> L
    I --> L
~~~

### 8.1. Preserve Raw Data, Normalize in a Separate Layer

For each file, store object identifier, ingestion timestamp, size or checksum, and parser version. Every normalized row should trace back to the source object and its row position or identifier in raw data.

Name normalized fields clearly such as `usage_start_utc`, `currency`, `cost_amount`, `cost_center`, and `allocation_mode`. This is an organization-designed internal schema, not mandatory OCI field names.

An ingestion pipeline must be idempotent: re-ingesting the same object must not double costs. Use manifests and ingestion transactions so a given object version is recorded once.

Do not use `resourceId + date` alone as a unique key. The same resource can appear across multiple time intervals and multiple billing components. Collapsing too early destroys explainability.

### 8.2. Preserve Adjustment Lines

Cost reports may add correction rows referencing earlier lines via `lineItem/isCorrection` and `lineItem/backReferenceNo`. See [schema and correction mechanics](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/costusagereportsoverview.htm).

Distinguish **duplicate ingestion** from **a valid adjustment**. Both may reference the same resource yet require different handling.

Preserve source links and value signs. Do not delete all correction rows, do not blindly take absolute values, and do not assume "the newest row always completely replaces the prior row." Rules for incorporating adjustments must follow data semantics and be reconciled before use in chargeback.

The SQL examples below assume a dataset layer has already completed deduplication, adjustment handling, and period selection. They are not raw cost report parsers.

### 8.3. Include Exceptions in Reporting

Each line can be classified into one of three groups:

| Group | Illustrative business condition | Handling |
| --- | --- | --- |
| `direct` | Valid cost center code, application matches catalog | Attribute directly |
| `shared` | Belongs to a registered shared pool | Await split rule application |
| `unallocated` | Missing or conflicting metadata | Track separately and assign verification |

Do not replace every blank value with the infrastructure team's cost center. Doing so hides tag governance issues and forces the infrastructure team to absorb other applications' costs.

If compartment-based fallback is needed, use an approved mapping table and mark the classification source as `compartment_mapping`. For tag-based mapping, mark `resource_tag`. That lets you report clearly how much spend is directly identified versus derived through fallback inference.

## 9. Example Allocation of 1,000 USD

The following numbers are **purely hypothetical**, not an OCI price sheet. Assume one period's data is complete for this example, all in USD, with no pending adjustments.

| Item | Cost center | Mode | Cost USD |
| --- | --- | --- | ---: |
| Compute for `payments` | `CC100` | `direct` | 420 |
| Volumes for `payments` | `CC100` | `direct` | 200 |
| Database for `analytics` | `CC200` | `direct` | 240 |
| Shared log storage | `SHARED` | `shared` | 60 |
| Shared log processing Compute | `SHARED` | `shared` | 40 |
| Volume with unidentified owner | Blank | `unallocated` | 40 |
| **Total** | | | **1,000** |

### 9.1. First Step: Keep the Three Groups Separate

~~~text
Direct CC100       = 420 + 200 = 620 USD
Direct CC200       = 240 USD
Shared log pool    = 60 + 40   = 100 USD
Unallocated        = 40 USD

620 + 240 + 100 + 40 = 1,000 USD
~~~

`SHARED` is a routing label into a pool. In the post-allocation report, do not leave an extra 100 USD as a final charge on the platform team while also adding the split 100 USD to the two applications.

### 9.2. Select Split Criteria and Freeze Period Figures

In the example, the organization agrees to split the log processing and storage pool by log volume ingested during the period:

- `payments`: 3 agreed measurement units.
- `analytics`: 2 units of the same measure.
- Total: 5 units.

This is a simple illustrative rule. When reality shows processing and storage have different cost drivers, split them into separate pools with distinct criteria.

For pool `S` and weights `w_i`:

~~~text
SharedAllocation_i = S × w_i / Σw

payments:  100 × 3/5 = 60 USD
analytics: 100 × 2/5 = 40 USD
~~~

If the sum of weights equals 0, do not divide. Keep the amount in an unallocated pool or apply a pre-approved fallback rule. Do not silently switch to an equal split just because metrics are missing.

### 9.3. Report Results and Verify Total Conservation

| Unit or bucket | Original cost | Received from pool | Total USD |
| --- | ---: | ---: | ---: |
| `CC100` | 620 | 60 | 680 |
| `CC200` | 240 | 40 | 280 |
| Unallocated | 40 | 0 | 40 |
| **Total** | **900** | **100** | **1,000** |

The "Original cost" column comprises 860 USD direct and 40 USD unidentified. In the data model, the 40 USD item remains in its separate `unallocated` group.

Identities to preserve:

~~~text
Source cost
  = Valid direct costs
  + Shared costs
  + Initially unallocated costs

Source cost
  = Sum of final unit costs
  + Remaining unallocated costs

1,000 = 680 + 280 + 40
~~~

If the 40 USD volume is later verified as belonging to `CC200`, `CC200` becomes 320 USD and unallocated drops to 0. That is a documented reclassification; the source total remains 1,000 USD.

When ratios produce fractional cents, compute with sufficient decimal precision and round at report output. Any residual penny difference must be allocated using a fixed, explainable, and reproducible rule.

## 10. Aggregation SQL on the Internal Schema

Suppose view `cost_lines_ready` has the following columns:

~~~text
usage_start_utc, currency, cost_amount,
cost_center, application, allocation_mode
~~~

This view has already selected a single cost source, removed duplicate ingestions, handled adjustments, and standardized classification per section 8. `cost_amount` uses a decimal numeric type, not floating-point numbers, for financial calculations.

The example below uses PostgreSQL syntax and parameters `:period_start_utc`, `:period_end_utc` supplied by the application. Parameters must be UTC timestamps compatible with the column type.

~~~sql
SELECT
    currency,
    allocation_mode,
    CASE
        WHEN allocation_mode = 'direct' THEN cost_center
        WHEN allocation_mode = 'shared' THEN 'SHARED'
        ELSE 'UNALLOCATED'
    END AS allocation_bucket,
    SUM(cost_amount) AS source_cost
FROM cost_lines_ready
WHERE usage_start_utc >= :period_start_utc
  AND usage_start_utc <  :period_end_utc
GROUP BY
    currency,
    allocation_mode,
    CASE
        WHEN allocation_mode = 'direct' THEN cost_center
        WHEN allocation_mode = 'shared' THEN 'SHARED'
        ELSE 'UNALLOCATED'
    END
ORDER BY currency, allocation_mode, allocation_bucket;
~~~

Grouping by `currency` from the start prevents producing a meaningless mixed total. Filtering the period by start timestamp matches the assumption that lines have already been aligned to period boundaries. If a line spans a boundary, the normalization layer must handle it per preselected rules.

A minimal reconciliation query compares source total and post-allocation total per currency:

~~~sql
WITH source_total AS (
    SELECT currency, SUM(cost_amount) AS amount
    FROM source_cost_for_period
    GROUP BY currency
),
allocated_total AS (
    SELECT currency, SUM(allocated_amount) AS amount
    FROM final_allocations_for_period
    GROUP BY currency
)
SELECT
    COALESCE(s.currency, a.currency) AS currency,
    COALESCE(s.amount, 0) AS source_amount,
    COALESCE(a.amount, 0) AS allocated_amount,
    COALESCE(a.amount, 0) - COALESCE(s.amount, 0) AS difference
FROM source_total s
FULL OUTER JOIN allocated_total a
    ON a.currency = s.currency;
~~~

`source_cost_for_period` and `final_allocations_for_period` are two internal views restricted to the same period. The output view must include unallocated buckets as well. `FULL OUTER JOIN` ensures a currency appearing on only one side is not dropped. Expected difference is 0, or within the published rounding tolerance when reconciling rounded reports.

You do not run this SQL directly in the OCI Console. It illustrates how to structure data inside an enterprise analytics warehouse.

## 11. Reconcile Against Financial Statements

Reconciliation should follow an ordered sequence to avoid altering allocation rules to hide a scope error.

1. **Scope:** matching tenancy, subscription, period, and relevant regions.
2. **Currency and metric:** matching cost type and accounting basis.
3. **Completeness:** all objects collected and failed runs resolved.
4. **Adjustments:** late-arriving data and related corrections incorporated into the run.
5. **Classification:** sum of direct, shared, and unallocated matches source.
6. **Allocation:** total after splitting matches total before splitting.
7. **Accounting:** explain variances against financial documents being reconciled.

Consumption cost used for operational analysis and payable amounts on an invoice may have different recognition scopes. Reconcile taxes, credits, commitments, and related adjustments separately against actual billing documents and subscription terms. Do not force two numbers to match by plugging an unfounded amount into an arbitrary cost center.

A reconciliation table can record:

| Item | Amount | Evidence source | Handling |
| --- | ---: | --- | --- |
| Period consumption cost | Per closed dataset | Manifest and source data | Allocate per rules |
| Confirmed variance item | Per financial document | Document reference | State clearly whether in or out of scope |
| Unexplained difference | Per reconciliation check | Active investigation record | Hold separately, do not finalize chargeback |

A report may be published as "provisional" while awaiting verification. Close dates and approvers must be clear; amending a closed period must create a revised version so readers understand the change.

## 12. Measure Allocation Quality and Handle Discrepancies

### 12.1. Track Quality by Monetary Value

Counting tagged resources is useful for governance, yet it does not reflect dollar coverage. One large untagged database can matter more than hundreds of fully tagged small resources.

With non-negative cost data in the example:

~~~text
Identified cost ratio
  = (Valid direct costs + Valid shared pool)
    / Total source cost

  = (860 + 100) / 1,000
  = 96%
~~~

"Identified" includes the 100 USD properly routed to a pool; it does not mean the money has been split to final business units yet. After splitting the pool, the ratio attributed to final units is `(680 + 280) / 1,000 = 96%`; both ratios happen to match here, though that is not always true.

If credits or negative costs exist, net totals can make ratios hard to interpret. In that case, publish separate calculations for positive charges, credits, and adjustments rather than applying the formula above mechanically.

Also track unallocated dollar amount, age of exceptions, money in pools lacking weights, and number of periods restated after close. Every exception needs an owning team and a resolution deadline.

### 12.2. Common Scenarios

| Symptom | Investigation direction |
| --- | --- |
| Newly added tag does not appear in costs | Check tag application time and data freshness |
| Filtering by tag shows lower total than tenancy total | Look for non-matching tags, missing tags, or items outside selected scope |
| Report download denied while Cost Analysis works | Check object download permissions and report storage location separately |
| Expected report not visible | Check home region, access permissions, and object listing |
| Total doubles after a re-run | Check for duplicate ingestion or loading both formats into one sum |
| Large unexplained usage total | Separate SKUs and measurement units before summing |
| Team receives costs without owning the resource | Check historical mappings, pool rules, and source metadata |
| Post-allocation total exceeds source | Check whether the pool was still added after splitting or a join duplicated rows |

For join bugs, watch closely for mapping tables matching one resource to multiple records with overlapping effective windows. A cost line joined to two cost centers can be counted twice even though source data was ingested only once.

## 13. Practice Workflow and Required Deliverables

You can practice on resources you already have permission to view without provisioning extra paid infrastructure:

1. Choose a period with existing data and record full scope details.
2. Use Cost Analysis to identify two or three major cost groups.
3. Select a primary allocation tag and inspect several representative resources.
4. Download matching cost reports, record a manifest, and archive raw files.
5. Normalize data, separating direct costs, pools, and exceptions.
6. Apply a split rule stating exact weights and measurement sources.
7. Reconcile by currency, keeping unexplained items separate.
8. Export a showback table with data status and calculation date.

Practice output should include a source summary table, an allocation table, an exception list, and rule documentation clear enough for someone else to recalculate. Do not modify tags on production resources just to make a practice report look cleaner.

In operations, this data supports cost and capacity decisions. For example, when volume cost for `payments` rises, combine it with used capacity metrics and retention requirements to evaluate options. When database cost rises, review both business workload and availability requirements before changing configurations.

Cost reports show where to investigate. Optimization decisions still require operational evidence, accountable owners, and a plan to maintain service quality.

## 14. References

The sources below provide OCI behavior and syntax references; amounts, application names, data models, and split rules in this lesson are learning examples.

- [OCI Cost Analysis](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/costanalysisoverview.htm).
- [OCI Cost Reports and schema](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/costusagereportsoverview.htm).
- [Listing Cost Reports](https://docs.oracle.com/en-us/iaas/Content/Billing/Tasks/list-cost-usage-report.htm).
- [Downloading a Cost Report](https://docs.oracle.com/en-us/iaas/Content/Billing/Tasks/download-cost-usage-report.htm).
- [Overview of Tagging](https://docs.oracle.com/en-us/iaas/Content/Tagging/Concepts/taggingoverview.htm).
- [Managing Tag Defaults](https://docs.oracle.com/en-us/iaas/Content/Tagging/Tasks/managingtagdefaults.htm).
- [Using Predefined Values](https://docs.oracle.com/en-us/iaas/Content/Tagging/Tasks/usingpredefinedvalues.htm).
- [OCI CLI: request-summarized-usages](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/usage-api/usage-summary/request-summarized-usages.html).
