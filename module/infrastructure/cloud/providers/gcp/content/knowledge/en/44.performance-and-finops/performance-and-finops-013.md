# Carbon Footprint and Evaluating Workload Environmental Impact

Optimizing performance and cost alone does not capture the full picture of cloud resource efficiency. Two applications with identical bills can produce different estimated greenhouse gas emissions due to resource types, deployment regions, electricity grid timing, and actual utilization. Conversely, moving a workload to a region with higher carbon-free energy while driving up latency, cross-region traffic, and replica counts may fail to deliver a net overall benefit.

In the **Performance and FinOps** chapter of the **CLOUD_PROVIDERS_GCP** module, this lesson guides measuring, analyzing, and improving the environmental impact of workloads on Google Cloud. It connects project organization, IAM, VPC, Compute Engine, GKE, Cloud Run, storage, and databases with cost, performance, reliability, and GreenOps/FinOps practices. The focus is **Google Cloud Carbon Footprint**, its methodology and BigQuery export, and designing data-backed changes rather than claiming emissions cuts from guesswork.

After this lesson, learners will be able to:

- Explain CO₂e, emission scopes, and location-based vs. market-based accounting.
- Understand what Carbon Footprint measures, its coverage boundaries, aggregation level, and publication latency.
- Access the dashboard using proper IAM permissions on a Cloud Billing account.
- Set up Carbon Footprint exports to BigQuery and query by month, project, service, and region.
- Distinguish provider-allocated estimated emissions from direct energy metering of individual VMs, Pods, or requests.
- Build carbon intensity KPIs per business unit and evaluate variances fairly.
- Analyze optimization levers across regions, compute, serverless, Kubernetes, storage, networking, and batch jobs.
- Balance carbon, cost, latency, data residency, safety, and SLOs.
- Design dashboards, impact-verification workflows, and data governance for sustainability reporting.

## 1. What Is Carbon Footprint in FinOps?

A **carbon footprint** expresses greenhouse gas emissions converted into CO₂ equivalent (CO₂e) tied to the activity under evaluation. CO₂e does not measure carbon dioxide alone; it normalizes the warming impact of multiple greenhouse gases into a single common unit.

In Google Cloud:

- **Cloud Billing** reports charges by product, project, SKU, and usage unit.
- **Cloud Monitoring** measures CPU, memory, networking, request counts, latency, errors, and operational signals.
- **Carbon Footprint** provides **estimated emissions** allocated by Google to usage of in-scope services by billing account, month, project, product, and location.

Never infer emissions directly from spend using a fixed kgCO₂e/USD ratio. Pricing reflects discounts, contracts, SKU structures, and regions, whereas emissions depend on energy consumption, electricity grid mix, and allocation methodology. Cost and emissions often drop together when deleting idle resources, yet the relationship is not always linear.

### 1.1. Units to Distinguish

| Unit | Meaning | Example Use |
|---|---|---|
| kWh | Electrical energy | Analyzing consumption and grid carbon intensity |
| gCO₂e/kWh | Electricity emissions intensity | Comparing grid characteristics across regions |
| kgCO₂e | Mass of CO₂-equivalent emissions | Monthly totals in BigQuery export |
| tCO₂e | Metric tons of CO₂e emissions | Overview totals in the Carbon Footprint dashboard |
| % CFE | Carbon-free energy percentage per published methodology | One signal when selecting regions |
| kgCO₂e/1,000 requests | Emissions intensity per business unit | Evaluating API efficiency at equal service quality |

Unit conversion: **1 tCO₂e = 1,000 kgCO₂e**. This is strictly a unit conversion—never treat one metric ton in a cloud provider's report as one metric ton of a customer's direct Scope 1 emissions.

## 2. Understanding Scope 1, Scope 2, and Scope 3

Google Cloud Carbon Footprint categorizes emissions sources according to the **Greenhouse Gas Protocol (GHG Protocol)**:

| Scope in Google's Report | Source Type | Data Center Operations Examples |
|---|---|---|
| Scope 1 | Direct emissions from operations in reporting scope | Backup generator fuel, refrigerant leakage |
| Scope 2 | Emissions from purchased/consumed electricity | Electricity for servers, networking, cooling, lighting |
| Scope 3 | Indirect value-chain emissions included in the model boundary | Equipment manufacturing, data center construction, select upstream activities |

**Crucial distinction:** these scopes classify Google's own emissions components inside the Carbon Footprint model. When an enterprise purchases cloud services, the associated emissions typically map to the **purchasing enterprise's Scope 3**, depending on the organization's GHG accounting policy. Never copy Google's Scope 1 figure and report it as the customer company's direct Scope 1.

Carbon Footprint does not cover every activity in a user's value chain. Client devices, office electricity, end-user terminals, and services outside covered products must be accounted for separately if within your organizational inventory boundary.

### 2.1. Location-Based Accounting

**Location-based** accounting uses the physical grid characteristics where consumption occurs via location- and time-specific emission factors. It helps evaluate the relative impact of region choices, compute timing, and workload distribution, even though final Carbon Footprint reports aggregate at the **monthly** level.

Location-based figures do not separately credit Google's clean-energy purchases or renewable contracts in Scope 2; they reflect underlying grid mix.

### 2.2. Market-Based Accounting

**Market-based** accounting computes Scope 2 reflecting Google's clean-energy procurement based on contracts and published emission factors. This lens is helpful for emissions reporting that incorporates a provider's renewable energy purchasing.

Location-based and market-based totals **must never be summed together**; they are two parallel accounting methods for the Scope 2 component of the same activity boundary.

### 2.3. Total Emissions Formulas

For the same billing account/project/service/location/month:

\[
E_{\text{location}} = E_1 + E_{2,\text{location}} + E_3
\]

\[
E_{\text{market}} = E_1 + E_{2,\text{market}} + E_3
\]

Reported sums may differ slightly due to rounding or display precision. Never take the difference between those two totals and label it "carbon eliminated" by a specific engineering change.

### 2.4. Carbon Offsets Are No Longer a Target Total Field

In the current Carbon Footprint schema, `carbon_offsets_kgCO2e` and `carbon_footprint_total_kgCO2e.after_offsets` are **deprecated** and return NULL. Use `carbon_footprint_total_kgCO2e.location_based` and `carbon_footprint_total_kgCO2e.market_based`. Never build new dashboards on `after_offsets` or interpret NULL as "zero emissions."

## 3. How Carbon Footprint Measures and Allocates Emissions

Google Cloud uses an estimation allocation model driven by machine/service activity data, data center energy usage, grid characteristics, clean-energy procurement, and included indirect sources.

~~~mermaid
flowchart LR
    Use[Google Cloud SKU usage] --> Allocation[Energy / activity allocation]
    DC[Data center energy + overhead] --> Allocation
    Grid[Grid emission factors] --> Loc[Location-based Scope 2]
    CFE[Clean energy contracts per Google methodology] --> Market[Market-based Scope 2]
    Allocation --> Loc
    Allocation --> Market
    Other[Allocated Scope 1 + Scope 3] --> Report[Monthly Carbon Footprint]
    Loc --> Report
    Market --> Report
    Report --> BQ[BigQuery export]
~~~

The model accounts for active compute energy and idle energy, plus supporting overhead such as cooling and power distribution. Cloud infrastructure is multi-tenant, so allocation rules attribute shared energy down to specific SKUs, services, and customers.

**Practical implications:**

- Figures are **modeled estimates**, not dedicated physical meter readings per workload.
- Not every Google Cloud SKU/product falls inside the allocatable boundary.
- Emissions reflect service usage within Google's reporting boundary, not every physical impact outside it.
- Exports contain no direct per-request, per-pod, or per-container metering.
- Models and input factors can change across methodology updates, skewing historical comparisons if model versions are not tracked.

### 3.1. Granularity and Latency

The Carbon Footprint dashboard computes data per billing account automatically—**no separate Carbon Footprint API enablement is needed** just to view the dashboard. Prior-month data can take **up to 21 days** to appear. The dashboard displays tCO₂e, whereas the BigQuery export reports kgCO₂e.

Exports use **BigQuery Data Transfer Service**, creating monthly partitioned tables on Google's published schedule—typically around the 15th of the following month. Track transfer completion dates so internal reports know which months are finalized.

Never use Carbon Footprint reports to alert on "CO₂e over the last 5 minutes" or claim direct per-request emissions measurements. Minute/hour performance metrics diagnose operational drivers; monthly Carbon Footprint tracks trends and verified outcomes.

### 3.2. Limits on Interpreting Zeroes

A project or service showing 0 or missing rows may reflect tiny/zero estimated emissions, missing telemetry, coverage boundaries, allocation shifts, or an incomplete export cycle. **Missing rows do not mean a workload has zero emissions.**

When `project.id` is NULL, emissions could not be attributed to a specific project or the project was deleted. Never silently drop these rows when reconciling billing-account totals; display them as `UNATTRIBUTED` or equivalent.

## 4. Accessing the Carbon Footprint Dashboard

### 4.1. IAM at the Billing Account Level

Viewing Carbon Footprint data requires permissions on the **Cloud Billing account**, not merely Project Viewer roles.

| Role | Scope | Notes |
|---|---|---|
| `roles/billing.carbonViewer` | Billing account | View Carbon Footprint without viewing granular cost details |
| `roles/billing.viewer` | Billing account | View billing and carbon data per role permissions |
| `roles/billing.admin` | Billing account | Broad billing admin rights; never grant merely to view carbon |

The core permission is `billing.accounts.getCarbonInformation`, alongside billing-account list/view rights to navigate the dashboard. Billing administrators must grant access on the billing account IAM page; `roles/viewer` on a project alone is typically insufficient.

### 4.2. Navigating in the Console

1. Open **Google Cloud Console → Carbon Footprint** (under Tools).
2. Select the Cloud Billing account to analyze.
3. Inspect both **Location-based emissions** and **Market-based emissions** tabs.
4. Review the trailing 12-month total and the most recent completed month.
5. Inspect trends by month and region; on the location-based tab, inspect project and product breakdowns where provided by the UI.
6. Note the date range and accounting method used before making comparisons.

A billing-account-level emissions figure does not automatically answer "how much did microservice A emit?" You must map projects/services/regions to workloads and document allocation confidence.

### 4.3. Viewing Emissions Without Viewing Costs

`roles/billing.carbonViewer` is ideal when Sustainability or SRE teams need emissions visibility without invoice access. When combining carbon and cost in BigQuery dashboards, enforce matching dataset permissions and data separation under least privilege.

## 5. Exporting Carbon Footprint Data to BigQuery

Carbon Footprint has no dedicated public API for querying emissions directly. Google's supported integration path is **BigQuery Data Transfer Service** to export data, followed by **BigQuery SQL/API** analysis. Do not confuse this with Cloud Billing cost export: the two sources have distinct schemas, granularity, and purposes.

### 5.1. Data Architecture

~~~mermaid
flowchart LR
    BA[Cloud Billing account] --> Carbon[Carbon Footprint monthly report]
    Carbon --> DTS[BigQuery Data Transfer Service]
    DTS --> Raw[(BigQuery carbon_footprint)]
    Billing[Cloud Billing cost/usage export] --> Cost[(BigQuery billing tables)]
    Raw --> Model[Clean views / metric definitions]
    Cost --> Model
    Model --> Dash[Looker Studio / BI / FinOps dashboard]
    Model --> Review[Quarterly GreenOps review]
~~~

This pattern separates the **raw source** from **derived metrics**. Leave raw export tables untouched, build clean views/tables for dashboards, and document NULL handling, chosen accounting method, missing cycles, and billing account scope.

### 5.2. Permissions and Setup Steps

Setting up the export requires appropriate permissions on the target project (such as `resourcemanager.projects.update`, `serviceusage.services.enable`, and `bigquery.transfers.update`), plus `billing.accounts.getCarbonInformation` on the billing account. Google documents broader roles for convenience, though organizations can craft custom roles to narrow deployment privileges.

Console workflow:

1. Select the billing account in Carbon Footprint.
2. Click **Data export**.
3. Choose the target project for the export; open BigQuery Data Transfer Service.
4. Select **Google Cloud Carbon Footprint Exports** as the data source.
5. Choose or create the target BigQuery dataset and specify the billing account ID.
6. Save the transfer and grant required consent/permissions.
7. Verify the transfer run succeeds and the `carbon_footprint` table appears.
8. Schedule historical backfills if needed.

BigQuery storage and queries incur costs and require explicit dataset location, retention policies, and IAM. If projects sit inside VPC Service Controls, verify ingress rules for BigQuery / BigQuery Data Transfer and export service identities per Google documentation.

### 5.3. Example Creating a Transfer via `bq`

~~~bash
bq mk \
  --transfer_config \
  --target_dataset=carbon_reporting \
  --display_name="Monthly Google Cloud Carbon Footprint" \
  --params='{"billing_accounts":"XXXXXX-XXXXXX-XXXXXX"}' \
  --data_source='61cede5a-0000-2440-ad42-883d24f8f7b8'
~~~

This is a structural example; substitute real billing account IDs/datasets and configure permissions, project, location, and required data-source enrollment. Per Google documentation, creating transfers outside the Console may require **enrolling the data source** before running. A new transfer does not guarantee full historical backfill automatically; request backfills separately.

### 5.4. Export Data Granularity

Each record represents estimated emissions for a **billing account + project + service + location + usage month** combination under the published schema. The table is typically named `carbon_footprint`.

| Field | Type | Meaning |
|---|---|---|
| `usage_month` | DATE | First day of the usage month |
| `billing_account_id` | STRING | Billing account |
| `project.id` | STRING | Project ID, may be NULL |
| `project.number` | STRING | Project number |
| `service.id`, `service.description` | STRING | GCP service |
| `location.region`, `location.location` | STRING | Region/location |
| `carbon_model_version` | INTEGER | Calculation model version |
| `carbon_footprint_total_kgCO2e.location_based` | FLOAT | Total location-based emissions |
| `carbon_footprint_total_kgCO2e.market_based` | FLOAT | Total market-based emissions |
| `carbon_footprint_kgCO2e.scope1` | FLOAT | Scope 1 component |
| `carbon_footprint_kgCO2e.scope2.location_based` | FLOAT | Location-based Scope 2 |
| `carbon_footprint_kgCO2e.scope2.market_based` | FLOAT | Market-based Scope 2 |
| `carbon_footprint_kgCO2e.scope3` | FLOAT | Scope 3 component |

Field names are case-sensitive with nested RECORD/STRUCT types; query against the actual exported schema rather than guessing from dashboard labels.

## 6. SQL Examples: Analyzing by Month, Project, and Region

These SQL queries use **GoogleSQL** (BigQuery Standard SQL), assuming `PROJECT_ID.carbon_reporting.carbon_footprint` was created by the transfer. They are read-only templates and do not create resources or mutate production.

### 6.1. Monthly Total Emissions by Billing Account

~~~sql
SELECT
  billing_account_id,
  usage_month,
  ROUND(SUM(carbon_footprint_total_kgCO2e.location_based), 3)
      AS location_based_kgco2e,
  ROUND(SUM(carbon_footprint_total_kgCO2e.market_based), 3)
      AS market_based_kgco2e
FROM `PROJECT_ID.carbon_reporting.carbon_footprint`
WHERE usage_month >= DATE '2026-01-01'
  AND usage_month < DATE '2027-01-01'
GROUP BY billing_account_id, usage_month
ORDER BY usage_month, billing_account_id;
~~~

Backticks wrap the fully-qualified table name. Date predicates reduce bytes scanned and keep incomplete months out of finalized periods. **Never add location-based and market-based columns into a single sum.**

### 6.2. Top Projects by Location-Based Carbon

~~~sql
SELECT
  billing_account_id,
  COALESCE(project.id, 'UNATTRIBUTED') AS project_id,
  ROUND(SUM(carbon_footprint_total_kgCO2e.location_based), 3)
      AS kgco2e_location_based
FROM `PROJECT_ID.carbon_reporting.carbon_footprint`
WHERE usage_month = DATE '2026-09-01'
GROUP BY billing_account_id, project_id
ORDER BY kgco2e_location_based DESC;
~~~

Never jump to the conclusion that the top project is the "most wasteful": larger projects naturally have higher absolute emissions. Compare alongside completed business output and SLOs to find true inefficiencies.

### 6.3. Project × Service × Region Matrix

~~~sql
SELECT
  usage_month,
  COALESCE(project.id, 'UNATTRIBUTED') AS project_id,
  service.description AS service_name,
  COALESCE(location.region, 'UNKNOWN_REGION') AS region,
  ROUND(SUM(carbon_footprint_total_kgCO2e.location_based), 3)
      AS kgco2e_location_based,
  ROUND(SUM(carbon_footprint_total_kgCO2e.market_based), 3)
      AS kgco2e_market_based
FROM `PROJECT_ID.carbon_reporting.carbon_footprint`
WHERE usage_month BETWEEN DATE '2026-07-01' AND DATE '2026-09-01'
GROUP BY usage_month, project_id, service_name, region
ORDER BY usage_month, kgco2e_location_based DESC;
~~~

This breakdown answers "which month, project, service, and region are the hotspots?" When analyzing a single billing account, filter by `billing_account_id`; when exporting multiple accounts, keep `billing_account_id` in the grouping to avoid merging distinct owners.

### 6.4. Reconciling Scopes Without Mixing Totals

~~~sql
SELECT
  usage_month,
  ROUND(SUM(carbon_footprint_kgCO2e.scope1), 3) AS scope1_kg,
  ROUND(SUM(carbon_footprint_kgCO2e.scope2.location_based), 3)
      AS scope2_location_kg,
  ROUND(SUM(carbon_footprint_kgCO2e.scope2.market_based), 3)
      AS scope2_market_kg,
  ROUND(SUM(carbon_footprint_kgCO2e.scope3), 3) AS scope3_kg,
  ROUND(SUM(carbon_footprint_total_kgCO2e.location_based), 3)
      AS total_location_kg,
  ROUND(SUM(carbon_footprint_total_kgCO2e.market_based), 3)
      AS total_market_kg
FROM `PROJECT_ID.carbon_reporting.carbon_footprint`
WHERE usage_month = DATE '2026-09-01'
GROUP BY usage_month;
~~~

Location-based totals reconcile with Scope 1 + Scope 2 location-based + Scope 3; market-based totals reconcile with Scope 1 + Scope 2 market-based + Scope 3. Check NULLs, rounding, and `model_version` before concluding data mismatches.

### 6.5. Tracking Model Versions and Data Completeness

~~~sql
SELECT
  usage_month,
  carbon_model_version,
  COUNT(*) AS row_count,
  COUNTIF(project.id IS NULL) AS unattributed_rows,
  COUNTIF(carbon_footprint_total_kgCO2e.location_based IS NULL)
      AS missing_location_values
FROM `PROJECT_ID.carbon_reporting.carbon_footprint`
WHERE usage_month >= DATE '2026-01-01'
GROUP BY usage_month, carbon_model_version
ORDER BY usage_month, carbon_model_version;
~~~

A change in `carbon_model_version` signals a methodology update; never assume two periods use identical coefficients. Months showing multiple model versions should be inspected at the proper grain alongside release notes.

## 7. Building Workload Carbon Intensity KPIs

Absolute emissions alone are insufficient for evaluating efficiency. A workload serving twice as many requests may see emissions rise 20% while **kgCO₂e per 1,000 requests** drops. Track both **absolute footprint** and **workload-normalized intensity**.

### 7.1. Formula

\[
\text{Carbon intensity} =
\frac{E_{\text{workload (kgCO₂e)}}}
{\text{Business output}} .
\]

Output units can be:

- 1,000 valid HTTP requests (comparable type, size, and complexity).
- 1,000 completed orders.
- One million records processed in batch ETL.
- One hour of video transcoded or one GB of data processed.
- One ML model trained to a defined quality threshold.

Anchor KPIs to meaningful business outcomes. Never game request counts by splitting requests artificially or degrading quality without accounting for true output.

### 7.2. Illustrative Example

Suppose an application has these internal metrics:

| Period | Total Location-Based (kgCO₂e) | Completed Orders | kgCO₂e / 1,000 Orders |
|---|---:|---:|---:|
| Month A | 420 | 140,000 | 3.00 |
| Month B | 480 | 240,000 | 2.00 |

Even though absolute emissions grew by 60 kgCO₂e, intensity fell from 3.00 to 2.00 kgCO₂e per 1,000 orders. These are **hypothetical figures**, not measurements of a live Google Cloud system.

If the organization's goal is cutting absolute emissions, lower intensity **is not enough** to declare goal completion. Monitor total emissions, intensity, workload growth, SLOs, and cost together.

### 7.3. Attribution by Team/Service

If each workload owns a dedicated project or clear ownership boundary, Carbon Footprint aggregates cleanly by project. When multiple services share one project, native exports lack per-pod or per-VM attribution.

Google publishes a finer-grained **estimation** approach by joining Carbon Footprint exports with Cloud Billing detailed cost/usage exports, then splitting emissions within the same billing account, project, product, region, and month proportionally by **cost at list** per resource/label. This is an **allocation estimate**, not per-resource power metering.

In particular, you must:

- Aggregate billing data to the exact matching grain before joining.
- Never join row-by-row, which multiplies Carbon Footprint totals across multiple billing line items.
- Include only valid resources within the same group in the denominator.
- Reconcile allocated totals back to original totals to avoid double-counting or lost remainders.
- Preserve `unattributed/unallocated` buckets rather than forcing everything onto arbitrary teams when data is missing.
- Document methodology and confidence levels directly on dashboards.

### 7.4. An Approximate Attribution Formula

For group `g = (billing_account, project, service, region, month)`:

\[
\widehat{E}_{i} =
E_g \times \frac{\text{ListCost}_{i}}{\sum_{j \in g}\text{ListCost}_{j}} .
\]

Apply only when the denominator is positive and Carbon Footprint and billing scopes match. This is a cost-weighted resource-level estimate, **not a physical emission factor for VM `i`**.

When discounts vary widely across resources, use `cost_at_list` per Google's guidance rather than net cost to avoid skewing allocations. If reliable `cost_at_list` data is unavailable, leave that share unallocated and disclose the limitation.

## 8. Selecting Regions with Carbon-Aware Architecture

Google publishes **Carbon-Free Energy percentage (CFE%)** and **grid carbon intensity (gCO₂e/kWh)** by region, along with a **Low CO₂** filter/badge for eligible locations. These metrics mean different things:

- CFE% reflects carbon-free energy share under Google's methodology in that region.
- Grid carbon intensity reflects electricity grid emissions across its generation mix.
- The Carbon Footprint monthly report reflects emissions allocated to **actual usage** at aggregate level.

A high-CFE% region does not automatically offer low latency, low pricing, sufficient quotas, or data residency compliance. Region selection is a multi-objective trade-off.

### 8.1. Region Decision Matrix

| Factor | Questions to Answer |
|---|---|
| Data residency | Where is data legally permitted to be stored and processed? |
| Latency | Do p95/p99 latencies to users and dependencies meet SLOs? |
| Reliability | Do HA, DR, region pairs, and RTO/RPO meet requirements? |
| Cost | How do compute, database, egress, and cross-region traffic change? |
| Capacity | Are needed SKUs, accelerators, quotas, and managed services available? |
| Sustainability | What are CFE%, grid carbon intensity, and historical Carbon Footprint? |
| Operational risk | Are migrations, consistency, backups, security, and compliance impacted? |

For users in Vietnam, compare nearby Asian regions matching network latency and data residency needs. Moving all data to a distant region solely for high CFE% is not recommended if it raises latency, cross-region traffic, and operational risk.

### 8.2. Carbon-Aware Batch Scheduling

Batch workloads like ETL, training, reindexing, or report generation often have flexible execution windows. You can:

1. Identify business deadlines for when outputs must be ready.
2. Check compliant regions and workload portability across regions.
3. Compare grid mix/carbon intensity using appropriate data sources—never treat monthly Carbon Footprint exports as a real-time signal.
4. Choose lower-carbon windows/regions when cost, latency, and SLOs remain satisfied.
5. Log baselines, job counts, resources, outputs, runtimes, estimated CO₂e, and cost.

For systems scheduling by **hourly carbon intensity**, use authorized/verified hourly grid signal feeds and evaluate reliability rather than inferring hourly patterns from monthly Carbon Footprint tables.

## 9. Improving Compute Engine and GKE Efficiency

### 9.1. Compute Engine: Eliminate Waste First

Common opportunities:

- Delete truly forgotten VMs, disks, images, IPs, and load balancers.
- Rightsize VMs using measured CPU, memory, throughput, and latency.
- Auto-stop/start dev/test environments that do not need 24/7 uptime.
- Use Managed Instance Groups / autoscaling for variable workloads.
- Evaluate newer-generation machine families/CPUs via profiling and work per unit energy.
- Trim redundant disks while preserving backups, retention, and RPO.

Rightsizing must account for peaks, memory working sets, networking, IOPS, GC, and tail latency. A low-average-CPU VM may still need headroom for batch spikes, failovers, or transaction bursts. Cutting a machine in half based purely on average CPU can break SLOs and cause costly retry storms.

### 9.2. GKE: Pod- and Node-Level Optimization

For Kubernetes:

- Audit requests/limits, actual utilization, and Pending/OOMKilled Pods.
- Tune HPA/VPA from real metrics and understand impacts on the cluster autoscaler.
- Improve bin-packing for fewer idle nodes while preserving HA.
- Choose GKE Autopilot or Standard based on control vs. operational capacity.
- Clean up unused namespaces, jobs, clusters, and preview environments.
- Match node types, accelerators, and CPU architectures to workloads.
- Monitor cluster capacity, zonal spread, rollout surges, and disruption budgets.

**Never equate "fewer nodes" with "adequate reliability."** Maintain zone/node fault tolerance per SLOs, and avoid overly strict PodDisruptionBudgets that block routine maintenance.

### 9.3. JVMs in Containers

Java/Spring apps can waste resources via oversized heaps, thread pools outsizing vCPUs, or high minimum replica counts. Useful measurements include process RSS, heap/GC, CPU throttling, connection pools, startup times, and request latency.

Tune concurrency and heap sizes via load tests rather than inflating container memory blindly to avoid OOMs without root-cause analysis. Shrinking memory lets more Pods pack onto fewer nodes, provided you verify GC pauses and p99 latency stay healthy.

## 10. Cloud Run, Functions, and Demand-Driven Architectures

Cloud Run scales with incoming requests and shrinks instances during low load. Still, **scale-to-zero does not guarantee a zero footprint**: downstream dependencies, storage, networking, and baseline platform overhead remain, and Carbon Footprint continues allocating per methodology.

### 10.1. Tuning Levers

- **Minimum instances:** set above 0 only when cold-start/SLO benefits are proven.
- **Maximum instances:** prevent runaway scaling and protect downstream databases.
- **Concurrency:** raise carefully to utilize CPU/memory while watching queueing and tail latency.
- **CPU/memory:** size to real traffic and startup profiles.
- **Request/Job architecture:** offload bounded batch jobs to Cloud Run Jobs.
- **Retry policies:** prevent retry storms that multiply processing and resource draw.
- **Caching:** eliminate redundant work and DB/API calls while accounting for cache memory and invalidation.

Trimming max instances can curb waste in some cases, yet never turn autoscaling caps into self-inflicted outages.

### 10.2. Example Change Verification

A Cloud Run API wants to reduce minimum instances from 4 to 1. Steps:

1. Capture a 2–4 week baseline covering peak and off-peak hours.
2. Record throughput, p95/p99 latency, error rate, cold starts, CPU/memory, and cost.
3. Pilot `min=1` in staging or a representative canary.
4. Test behavior under sudden traffic spikes and database connection pool demand.
5. Observe one complete Carbon Footprint month while checking confounding variables.
6. Report **estimated** emissions reductions only using identical methodology, identical boundaries, and explicit attribution caveats.

If multiple services in the same project changed concurrently, you cannot credit the project's entire Carbon Footprint delta solely to lowering one service's min instances.

## 11. Storage, Databases, and Networking

### 11.1. Cloud Storage

- Apply lifecycle policies to temporary files, exports, and obsolete logs/artifacts.
- Choose storage classes by access frequency and restore terms, not list storage rate alone.
- Eliminate duplicate datasets and unowned backups lacking retention rules.
- Cut unnecessary reads/writes; batch processing and cache where appropriate.
- Evaluate **replication** cost and impact against DR requirements.

Changing storage classes can raise retrieval/operation fees and latency; deleting backups to "look greener" while breaking RPO is the wrong trade-off.

### 11.2. Cloud SQL, Spanner, and BigQuery

- Cloud SQL: rightsize instances, connection pools, truly needed replicas, backups, and disks.
- Spanner: size compute capacity and storage configs to real traffic, avoiding excessive overprovisioning.
- BigQuery: partition, cluster, filter, and process incrementally; eliminate full-table scans and redundant pipeline runs.
- Dataflow/Pub/Sub: eliminate duplicate processing, tune batch/streaming, and curb retention/backlogs.
- Co-locate data and compute to avoid unnecessary cross-region transfers.

Lower BigQuery scan costs do not automatically prove an identical percentage drop in emissions; track Carbon Footprint figures alongside workload output.

### 11.3. Networking and Content Delivery

- Co-locate chatty apps and databases when data residency and SLOs allow.
- Use caching/CDN for suitable content to cut origin processing and repeated transfers.
- Avoid cross-region replication without clear business requirements.
- Monitor egress and topology, especially when evaluating region moves.

CDNs, load balancers, or multi-region replication can raise emissions in one layer while lowering them elsewhere. Evaluate the **end-to-end system boundary** and reliability rather than focusing only on shut-down resources.

## 12. When Cost and Carbon Do Not Move Together

| Decision | Likely Cost Impact | Likely Emissions Impact | What to Verify |
|---|---|---|---|
| Delete forgotten VMs | Usually drops | Usually drops | No hidden dependencies or DR roles |
| Downsize to smaller VMs | May drop | May drop | SLOs and retry rates |
| Move to a high-CFE% region | May rise or drop | May drop | Networking, data residency, redundancy |
| Add caching | Costs cache RAM/spend | May cut backend compute | Hit rate, invalidation, net effect |
| Add read replicas | Usually rises | Usually rises | Truly needed for availability/read SLOs? |
| Scale-to-zero | Usually drops at low load | May drop | Cold starts, downstream baseline |
| Shift batch execution hours | May vary | Depends on hourly grid intensity | Deadlines, data movement, hourly signals |
| Increase compression | Adds CPU | Cuts network/storage if effective | Net CPU vs. transferred data |

Never optimize a single metric in isolation. Enforce hard constraints—**safety, security, compliance, SLOs, RTO/RPO**—and then compare cost and estimated CO₂e within the remaining feasible design space.

## 13. Designing a GreenOps + FinOps Dashboard

A useful dashboard separates three data feeds:

~~~mermaid
flowchart TB
    Carbon[Carbon Footprint monthly export] --> Metric[Metric layer]
    Cost[Billing export / cost-at-list] --> Metric
    Usage[Monitoring + app business metrics] --> Metric
    Metric --> Exec[Executive overview: absolute + intensity]
    Metric --> Eng[Engineering: project / region / service hotspots]
    Metric --> Gov[Governance: coverage, lag, ownership, controls]
~~~

### 13.1. Recommended KPI Set

| KPI | Source | Cadence | Interpretation Caveat |
|---|---|---|---|
| Total location-based kgCO₂e | Carbon Footprint | Monthly | Same billing account and boundary |
| Total market-based kgCO₂e | Carbon Footprint | Monthly | Never sum with location-based |
| kgCO₂e by project/service/region | Carbon Footprint | Monthly | Affected by product mix and model versions |
| kgCO₂e / 1,000 transactions | Carbon + business output | Monthly | Output must match exact period and scope |
| Cost per transaction | Billing + business output | Daily/monthly | Discounts, credits, list vs. net |
| Idle resource inventory | Monitoring/Recommender | Weekly | Verify before deleting |
| Project ownership coverage | Resource inventory | Monthly | Categorize unowned items |
| Reporting completeness/lag | DTS metadata | Monthly | Never report incomplete periods |

Emissions data may require restricted access by billing account. Create BigQuery authorized views, row-level filters, or separate datasets when teams should only view owned resources. Never expose unnecessary billing account IDs, private pricing, or sensitive event metadata on public dashboards.

### 13.2. Data Quality Gates

Before publishing monthly reports:

1. Confirm the transfer run succeeded cleanly.
2. Confirm the target `usage_month` is populated and complete.
3. Reconcile billing-account carbon totals between dashboards and SQL queries.
4. Check NULL projects/locations, missing values, and scope definitions.
5. Check for changes in `carbon_model_version` or methodology.
6. Correlate project/service swings against billing usage and infrastructure events.
7. Stamp export date, data cutoff date, and dashboard version.
8. Record reconciliation notes and report approvers.

## 14. Verifying the Impact of an Optimization Measure

Manage a GreenOps initiative like an engineering experiment, not a collection of anecdotes like "we turned off 10 VMs and saved X tons of carbon" without measurement.

### 14.1. Formulate a Hypothesis

Example: "Rightsizing a GKE node pool will cut allocated idle CPU/memory; at equal transaction counts and p99 latency, estimated emissions per transaction will drop."

### 14.2. Record Baselines and Confounders

| Data | Before Change | After Change |
|---|---|---|
| Time window | Complete data month | Complete data month |
| Total transactions | Same definition | Same definition |
| Average and peak load | Recorded | Recorded |
| p95/p99, error rate, SLOs | Recorded | Recorded |
| Service/region architecture | Inventory | Inventory |
| Cost | Explicit list/net basis | Same method |
| Carbon Footprint | Location-based + market-based | Same boundary |
| Carbon model version | Recorded | Recorded |

Confounding variables: seasonal traffic, feature launches, marketing campaigns, Google allocation model updates, region shifts, outages, DR drills, traffic mix shifts, collection windows, and baseline overhead.

### 14.3. Compute the Delta

Suppose a project has comparable before/after baselines:

| Metric | Before (Hypothetical) | After (Hypothetical) |
|---|---:|---:|
| Orders/month | 200,000 | 200,000 |
| Location-based carbon | 560 kgCO₂e | 490 kgCO₂e |
| Carbon per 1,000 orders | 2.80 kg | 2.45 kg |
| p99 latency | 420 ms | 425 ms |
| Error rate | 0.10% | 0.10% |

Absolute delta = -70 kgCO₂e/month; intensity fell by 0.35 kgCO₂e/1,000 orders. These are **illustrative figures only**. When reporting real impacts, disclose that project-level attribution may span multiple workloads and external changes.

For intra-month A/B traffic tests or canaries, native Carbon Footprint lacks container-level resolution to separate two deployments. Use resource-level estimates derived from billing and Monitoring for engineering decisions, explicitly labeled "internal estimate" rather than official Carbon Footprint measurements.

### 14.4. Communicating Results Responsibly

Good phrasing: "Post-optimization, the project's estimated total location-based emissions fell 12.5% period-over-period at comparable output; concurrent changes and carbon model version are noted."

Poor phrasing: "Service A saved exactly 70 kgCO₂e from changing one JVM flag" when only project-wide totals exist without attribution evidence.

## 15. Practice: Carbon Assessment of an E-Commerce API

**Context:** an enterprise operates a Cloud Run API, Cloud SQL database, Pub/Sub event pipeline, Cloud Storage artifacts, and BigQuery analytics. The goal is finding top estimated emission sources and building a verified optimization backlog while protecting SLOs.

### Step 1: Define Scope

- Select the right billing account and workload projects.
- Inventory services, regions, and owners.
- Use location-based for operational decisions while keeping market-based alongside for reporting.
- Select 3–6 completed months, excluding the current in-progress month.

### Step 2: Verify Permissions and Export

- Billing admin grants Carbon Footprint Viewer.
- Data/platform team sets up BigQuery export via Data Transfer Service.
- Verify table names, dataset location, transfer status, and backfills.
- Create read-only views for engineers if project-scoped isolation is needed.

### Step 3: Identify Hotspots

- Run queries by month and project/service/region.
- Flag fast-growing services and projects, including NULL-project rows.
- Cross-check spend, quotas, instance counts, and usage metrics.
- Never downsize resources based solely on a carbon chart.

### Step 4: Build an Action Shortlist

Examples:

1. Close preview environments with zero traffic for 7 days.
2. Rightsize staging VMs with low CPU/memory not serving test runs.
3. Lower min instances on Cloud Run services whose p99 cold start stays within budget.
4. Add lifecycle policies for expired intermediate objects.
5. Partition BigQuery tables and fix full-scan queries in analytics pipelines.

Each action requires an owner, risk tier, rollback criteria, resource scope, cost forecast, and carbon impact to verify.

### Step 5: Controlled Rollout

- Measure load and SLOs before and after.
- Canary or stage before touching production.
- Roll back immediately if error rate, latency, or RTO/RPO crosses guardrails.
- Update resource inventories, spend trackers, and architecture docs.

### Step 6: Verify on Finalized Carbon Cycles

Once Carbon Footprint exports complete for full post-change months, compare absolute and intensity figures across matching boundaries; record `carbon_model_version`, business output, and confounders. State findings directionally if multiple workloads share a project.

## 16. Troubleshooting Carbon Footprint

**Cannot find Carbon Footprint in Console.** Check selected billing account, billing-account IAM permissions, data availability, and Tools menu—do not just ask for Project Viewer.

**Missing last month's data.** Publication can lag up to 21 days; verify transfer schedule and run status. Never interpret an unpublished month as a zero footprint.

**BigQuery table has not appeared.** Check dataset, BigQuery Data Transfer Service, transfer config, permissions, and data-source enrollment if configured outside Console. Inspect transfer run logs.

**Permission denied during export.** Check `billing.accounts.getCarbonInformation` on the billing account and `bigquery.transfers.update`/target project permissions rather than granting Owner broadly.

**Dashboard numbers differ from SQL.** Check tCO₂e vs. kgCO₂e units, location-based vs. market-based selection, billing account, month filters, NULL projects, query predicates, and backfills.

**The two methods yield different totals.** That reflects Scope 2 location-based vs. market-based accounting, not an addition bug; verify schema and methodology.

**Deleted projects show no name.** `project.id` can be NULL; retain the unattributed group when reconciling totals rather than dropping rows.

**`after_offsets` column is all NULL.** That field is deprecated; switch to current `location_based` or `market_based` totals.

**A single microservice has no isolated emission figure.** Native export stops at project/service/region/month; if resource-level estimates are needed, join billing usage and allocate per published methods, explicitly labeling it an approximation.

**CO₂e rose despite shrinking VMs.** Check traffic growth, service mix, region moves, other workloads, `carbon_model_version`, and non-comparable months.

**Moving regions cut carbon yet raised latency.** Re-evaluate SLOs, data locality, downstream egress, and capacity; never trade away user-facing requirements to lower footprint.

## 17. Common Analytical Pitfalls

1. **Adding location-based and market-based into one total:** two parallel views that must not be summed.
2. **Treating Carbon Footprint as a per-VM meter:** it is a modeled allocation across shared cloud infrastructure.
3. **Comparing an incomplete month with a complete month:** data is out of sync.
4. **Ignoring NULL `project.id` rows:** breaks billing-account total reconciliation.
5. **Booking the provider's Scope 1/2/3 as the customer's Scope 1/2/3:** confuses GHG inventory ownership.
6. **Claiming model-version shifts as optimization wins:** inspect methodology updates first.
7. **Multiplying Carbon Footprint totals when joining billing rows:** aggregate to matching grain first.
8. **Optimizing cost and claiming identical percentage carbon cuts:** cost and CO₂e do not scale linearly.
9. **Picking regions solely by CFE%:** ignores residency, cost, latency, networking, and HA.
10. **Deleting backups or dropping HA to "go green":** breaks SLO/RPO/RTO.
11. **Ignoring sensitive data in dashboards:** billing and resource usage require restricted access.
12. **Claiming "net zero" solely from low market-based figures:** does not imply zero lifecycle emissions.

## 18. Operational Checklist

### Measurement

- [ ] Billing accounts, projects, services, and workload boundaries defined.
- [ ] Provider Scope 1/2/3 understood without conflating with customer enterprise scopes.
- [ ] Location-based and market-based tracked separately.
- [ ] Consistent units used: kgCO₂e in exports and tCO₂e in dashboards.
- [ ] Only finalized months compared, with `carbon_model_version` recorded.
- [ ] Carbon Footprint BigQuery export configured and transfer completion verified.
- [ ] NULL projects and unattributed rows retained during total reconciliations.

### Analysis and Optimization

- [ ] Both absolute emissions and workload-normalized carbon intensity tracked.
- [ ] Business output KPIs match timeframe, scope, and definitions.
- [ ] Hotspots identified by project/service/region.
- [ ] Cost-at-list/resource allocation clearly labeled as an approximation when used.
- [ ] Regions evaluated across CFE%, carbon intensity, residency, latency, and price.
- [ ] Idle cleanup, rightsizing, autoscaling, storage lifecycles, and networking evaluated.
- [ ] Every change carries SLO, security, HA, and cost guardrails.

### Governance

- [ ] Data owner, FinOps/GreenOps lead, and reviewers assigned.
- [ ] IAM Carbon Footprint Viewer granted on billing account; least privilege on BigQuery datasets.
- [ ] Raw data, derived views, versioned metrics, and reports managed separately.
- [ ] Runbooks exist for missing data, transfer failures, and methodology updates.
- [ ] Baselines, comparison methods, and rollback plans documented.
- [ ] Unapproved resource-level estimates are not presented as formal inventory audits.

## 19. Official References

- [Google Cloud Carbon Footprint](https://cloud.google.com/carbon-footprint)
- [View Carbon Footprint data](https://cloud.google.com/carbon-footprint/docs/view-carbon-data)
- [Carbon Footprint methodology](https://cloud.google.com/carbon-footprint/docs/methodology)
- [Carbon Footprint export to BigQuery](https://cloud.google.com/carbon-footprint/docs/export)
- [Carbon Footprint export data schema](https://cloud.google.com/carbon-footprint/docs/data-schema)
- [Carbon Footprint IAM roles](https://cloud.google.com/carbon-footprint/docs/iam)
- [Carbon Footprint API / BigQuery Data Transfer](https://cloud.google.com/carbon-footprint/docs/api)
- [Custom Carbon Footprint dashboard and resource attribution](https://cloud.google.com/carbon-footprint/docs/custom-dashboard)
- [Carbon Footprint release notes](https://cloud.google.com/carbon-footprint/docs/release-notes)
- [Carbon-free energy for Google Cloud regions](https://cloud.google.com/sustainability/region-carbon)
- [Sustainability: continuously measure and improve](https://cloud.google.com/architecture/framework/sustainability/continuously-measure-improve)
- [Sustainability: low-carbon regions](https://cloud.google.com/architecture/framework/sustainability/low-carbon-regions)
- [Cloud Billing export to BigQuery](https://cloud.google.com/billing/docs/how-to/export-data-bigquery)
- [Google Cloud Active Assist recommendations](https://cloud.google.com/recommender/docs/overview)

**Conclusion:** Carbon Footprint supplies a quantitative foundation for viewing the estimated environmental impact of Google Cloud usage, provided its **boundaries and methodology** are interpreted accurately. Analyze location-based and market-based metrics separately, slice data by billing account/project/service/region/month, pair with performance and business output KPIs, and prioritize eliminating unused resources, rightsizing, workload placement, and architectural efficiency. Sound GreenOps decisions deliver evidence-backed emissions reductions while preserving security, service quality, reliability, and cost control.
