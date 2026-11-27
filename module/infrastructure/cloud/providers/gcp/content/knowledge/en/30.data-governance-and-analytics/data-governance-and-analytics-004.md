# Catalog, Metadata, and Data Discovery in Dataplex

A retail enterprise has an orders API on **Cloud Run**, transactional systems on **Cloud SQL/Spanner**, events flowing through **Pub/Sub**, raw data in **Cloud Storage**, and analytical tables in **BigQuery**. An analyst asks: "Which revenue table is official, who owns it, when is it updated, how is `net_revenue` defined, does it contain PII, and where do I request access?" Knowing only a bucket or table name is not enough to answer those questions.

A **data catalog** solves the problem of *finding the right data assets and understanding how to use them* through metadata. On Google Cloud, the service formerly named **Dataplex Universal Catalog** is now called **Knowledge Catalog** in documentation. Existing configurations remain compatible, and many CLI/API/IAM names **still carry the `dataplex` prefix**. This lesson uses "Dataplex/Knowledge Catalog" so learners accurately recognize both older documentation and the current UI, without confusing it with the earlier **Data Catalog** product. See [transitioning product names](https://docs.cloud.google.com/knowledge-catalog/docs/transition-dataplex-universal-catalog).

This lesson belongs to the **Data Governance and Analytics** chapter of the **CLOUD_PROVIDERS_GCP** module. It focuses on organizing the catalog, understanding **entries, aspects, and business glossaries**, searching assets, and managing authorization; lineage, data quality, cost, and operations are covered sufficiently to deploy a useful catalog without turning it into a transactional data store.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish between a **data asset**, **metadata**, a **catalog**, and **source data access permissions**.
2. Explain **entry group, entry, entry type, aspect type, aspect, entry link**, and glossary term.
3. Understand **system entries** automatically harvested from Google Cloud sources versus **custom entries** for external sources.
4. Search data by name, column, system, location, labels, description, or business metadata; understand IAM scoping and search result limits.
5. Enrich entries with descriptions, owners, sensitivity levels, update cadences, and business term definitions.
6. Combine metadata with **data lineage**, **data quality**, IAM, BigQuery views, and practical access-granting workflows.
7. Run safe `gcloud dataplex` commands and design processes that keep metadata accurate after schema changes.

## 2. The Catalog Is a Data Map, Not a Data Warehouse

### 2.1. Data vs. Metadata

| Concept | Retail Example | Where Managed |
| --- | --- | --- |
| **Actual data** | Rows of `order_id`, `customer_email`, `amount_vnd`. | BigQuery, Cloud SQL, Cloud Storage... |
| **Technical metadata** | Table name, schema, region, data types, creation time. | Catalog synced with source system metadata. |
| **Business metadata** | "Net revenue", owner, data steward, trust level, update SLA. | Aspects, descriptions, glossaries, and governance workflows. |
| **Data lineage** | `raw.orders` → Dataflow/BigQuery transform → `mart.daily_revenue`. | Data Lineage API / supported integrations. |
| **Data read permissions** | Analyst can `SELECT` on a view, not on the raw PII table. | IAM, BigQuery dataset/table policies, row/column policies, and corresponding sources. |

**The catalog does not copy all rows into a second database** simply because an entry is created. It stores *descriptive context and search indexes* so users can find, evaluate, and request access to the right assets. Because metadata can reveal sensitive column names or internal notes, it also requires access controls and rules against putting secrets in notes.

### 2.2. Data Discovery Flow

~~~mermaid
flowchart LR
    SRC["BigQuery / Cloud Storage / other sources"] --> ING["Sync or ingest metadata"]
    ING --> CATALOG["Knowledge Catalog"]
    OWNER["Data steward"] --> ASPECT["Ownership / classification / descriptions"]
    ASPECT --> CATALOG
    GOV["Glossary / quality / lineage"] --> CATALOG
    USER["Analyst"] --> SEARCH["Catalog search"]
    SEARCH --> CATALOG
    CATALOG --> INFO["Inspect schema, owner, freshness, policies"]
    INFO --> ACCESS["Request access at the source system"]
    ACCESS --> QUERY["Query/view with appropriate IAM"]
~~~

The catalog helps users answer step by step: **where to find it → what it means → whether it is trustworthy → whether they may use it → whom to contact**. Do not start by granting `BigQuery Admin` just so everyone can "see" a table in search.

## 3. The Dataplex/Knowledge Catalog Metadata Model

### 3.1. Six Core Objects

| Object | Role | Example |
| --- | --- | --- |
| **Entry group** | Container and governance boundary for entries/entry links. | System group `@bigquery`; custom group `partner-data`. |
| **Entry** | A discoverable asset. | `orders` table, bucket, dashboard, or external source. |
| **Entry type** | Defines the category of entry and required aspects. | System type `bigquery-table`; custom type `external-report`. |
| **Aspect type** | Reusable template/schema for a category of metadata. | `data-steward`, `data-sensitivity`, `freshness-policy`. |
| **Aspect** | Metadata instance matching an aspect type, attached to an entry or column. | `owner_team=finance`, `classification=confidential`. |
| **Entry link** | Relationship between entries, columns, or concepts. | Term "Net Revenue" linked to column `net_revenue`. |

~~~mermaid
flowchart TB
    GROUP["Entry group: @bigquery"] --> ENTRY["Entry: mart.daily_revenue"]
    TYPE["Entry type: bigquery-table"] --> ENTRY
    ASPECTTYPE["Aspect type: governance"] --> ASPECT["Aspect: owner=finance, tier=gold"]
    ASPECT --> ENTRY
    GLOSS["Glossary term: Net Revenue"] --> LINK["Entry link: definition"]
    LINK --> ENTRY
~~~

Every entry has a resource identifier and may have a **fully qualified name (FQN)** linking it to the source. An aspect belongs to an **entry or column**; it is not a new BigQuery table. Depending on the source system, there are **required aspects** describing schemas and **optional aspects** carrying business metadata. Some service-managed aspects can be viewed but **cannot be edited directly**.

### 3.2. System Entries vs. Custom Entries

- **System entries:** Knowledge Catalog automatically ingests metadata for supported sources like **BigQuery** assets; they typically live in **system entry groups** prefixed with `@`, such as `@bigquery`. Do not manually create, edit, or delete system entry groups; deleting the underlying asset can cause its system entry to disappear.
- **Custom entries:** created by the platform team to describe sources not automatically integrated, such as partner databases, internal datasets outside Google Cloud, or custom-structured assets.
- **Custom entry type:** defines a custom asset kind and its required aspects so entries of the same kind share consistent metadata.
- **Custom aspect type:** specifies fields, types, and constraints; can be **regional** or **global**. Global enables reuse across regions, though avoid global if the aspect type definition itself contains sensitive information subject to data residency.

Do not assume the catalog automatically discovers *every table* across every system. Sync scope depends on **supported connectors/products, APIs, IAM, source configuration, location, and ingestion state**. For external sources, you must design a connector/import pipeline and update it periodically.

### 3.3. Example of a Useful Entry

| Metadata Field | Illustrative Value |
| --- | --- |
| Asset | `retail-analytics.mart.daily_revenue` (BigQuery table). |
| Business name | Daily Net Revenue. |
| Description | Total payments after refunds, by UTC date; excludes cancelled orders. |
| Grain | One row per `sale_date` and `channel`. |
| Owner | `finance-data` team; steward `data-governance` team. |
| Freshness | Updated before 07:00 Vietnam time daily. |
| Classification | `internal`; no public PII. |
| Quality | Non-negative; missing data below approved threshold. |
| Lineage | Sourced from `raw.payments` and `raw.refunds` via identified pipeline. |
| Certification | Verified by Finance per standard process. |

**These values are purely hypothetical examples for illustration**, not metadata from any real table. Never put personal emails, tokens, or passwords into aspects. Labels like "Gold", "certified", or "fresh" must have **verifiable criteria and an accountable owner**, rather than serving as decorative badges.

## 4. Business Metadata: Aspects, Descriptions, and Glossaries

### 4.1. Metadata Managed Like a Contract

A `business-governance` aspect type might contain:

| Field | Suggested Type | Rule |
| --- | --- | --- |
| `owner_team` | String | Responsible team name, never a single individual. |
| `data_class` | Enum | `public`, `internal`, `confidential`, `restricted`. |
| `sla_hours` | Integer | Expected maximum hours before data refreshes. |
| `purpose` | String | Approved intended usage. |
| `reviewed_at` | Date/time | Timestamp of steward review. |

**An aspect type is a template; an aspect is the value attached to an entry.** For instance, the same template can apply to `daily_revenue`, `customer_profiles`, and `product_metrics`, each with its own owner and classification. Do not enter the same team in three spellings like `Finance`, `finance-team`, and `fin_analytics` if you want reliable filtering.

Column-level metadata can store sensitivity labels, descriptions, or term definitions. In BigQuery, **table descriptions** and **column descriptions** remain useful for query tools and AI assistants; do not assume every **custom aspect** is automatically passed verbatim as context to Gemini SQL tasks.

### 4.2. Business Glossaries Prevent "Same Name, Different Meaning"

Suppose three teams define "revenue" differently:

- Finance: recognized amount after adjustments.
- Growth: total value of newly created carts.
- Operations: total successful payment volume.

A glossary creates **terms with approved definitions** such as `Net Revenue`, `Gross Merchandise Value`, and `Successful Payment Value`. Terms can be organized into **glossaries/categories** with synonyms, related terms, stewards, and **links to entries/columns**. Searching for "net revenue" then leads to the properly defined asset rather than a random table containing the word `revenue`.

**A glossary does not validate SQL formulas on its own** and does not replace data quality scans; owners must update definitions, mappings, and approvals whenever business logic changes.

## 5. Data Discovery: From Search to Usage Decisions

### 5.1. Self-Service Workflow for Analysts

1. Open **Knowledge Catalog Search** in the Google Cloud console and select an authorized project/context.
2. Search by **business intent** ("daily net revenue"), system/table name, or column name.
3. Filter by **system, type, project, location, labels**, and searchable metadata.
4. Open the entry and inspect schema, description, glossary links, owner/contacts, quality, and lineage if available.
5. Verify business grain, freshness, data classification, upstream sources, and usage policies.
6. If you lack query permissions, contact the owner or request access at the **source system**; never attempt to use another service account to bypass controls.
7. Run a small test query or preview using **granted permissions**, reconciling business definitions before building a dashboard.

Search results are **candidates**, not automatic certification that data is accurate or approved for your use case.

### 5.2. Metadata Search Syntax

Knowledge Catalog supports keyword search, **semantic search**, and **qualified predicates**. Examples in the UI or via `gcloud dataplex entries search`:

| Query | What It Finds |
| --- | --- |
| `daily_revenue` | Assets with matching names or descriptions. |
| `system=bigquery type=table` | BigQuery tables discoverable by the user. |
| `column:customer_id` | Entries containing a column matching `customer_id`. |
| `description:"revenue"` | Description metadata containing the token `revenue`. |
| `projectid:retail-analytics` | Assets matching the project ID. |
| `location=asia-southeast1` | Assets in the specified location. |
| `labels.env=prod` | Label `env` with exact value `prod`. |
| `system=bigquery (type=table OR type=view)` | BigQuery tables or views. |
| `system=bigquery -name:test` | Excludes entries whose names contain `test`. |

Rules to remember:

- `type=`, `system=`, and `location=` are **exact matches**; do not substitute `type:` or `system:`.
- `name:` and `column:` support substrings; `description:` typically performs token matching.
- Write `AND`, `OR`, `NOT` in **uppercase**; use parentheses when combining boolean logic.
- Do not use `*`/`?` wildcards like SQL `LIKE`; search follows its own syntax rules.
- `aspect`/metadata-field search supports filtering on **indexed aspect types/fields**; check the ID format and filterable field types.
- Semantic search improves intent-based discovery, yet **does not guarantee complete recall and never replaces IAM checks**.

For example, `name:revenue` may return several distinct tables; read descriptions and glossaries to identify the **approved** one.

### 5.3. Search vs. Listing and Full Inventory

**Search** is built for *discovery*; **list/get** is for *enumerating and reading explicitly addressed resources*. Search may omit matching entries due to **relevance, scope, IAM, or recall limits**, and results can vary across calls. Therefore:

- **Do not use** `COUNT(search results)` as a definitive report of "how many tables the company has."
- For a **complete inventory** at scale, use metadata export features and query the resulting dataset per product docs, or use properly scoped list APIs with pagination.
- When a table does not appear in search, verify source existence, user metadata IAM, **search scope**, VPC Service Controls, ingestion status, and indexing state; do not assume the data was deleted.

Search defaults typically to the **organization scope** of the querying project and only returns entries the user is authorized to view; VPC Service Controls can restrict results within a perimeter. **Catalog Viewer alone may not reveal BigQuery metadata** if the principal lacks metadata permissions at the source system.

## 6. Hands-On `gcloud`: Exploring and Inspecting Metadata

The following commands are **Bash** and read-only; project/entry/group IDs are **examples** and are not guaranteed to exist. You need an up-to-date `gcloud` installation, required APIs enabled, and an authorized identity. When running labs, use a project within your permitted scope.

### 6.1. Preflight: Identity and Project

~~~bash
PROJECT_ID="retail-lab"
LOCATION="asia-southeast1"

# READ-ONLY: check current identity and configured project.
gcloud auth list
gcloud config get-value project

# READ-ONLY: do not enable APIs or create projects without authorization.
gcloud services list --enabled \
  --project="$PROJECT_ID" \
  --filter="name:dataplex.googleapis.com"
~~~

**Naming note:** the refreshed product carries the **Knowledge Catalog** label, yet the API remains `dataplex.googleapis.com` and CLI commands still use `gcloud dataplex`. If services are governed by organization policy, ask an admin to enable the API rather than requesting the Owner role.

### 6.2. Searching Entries by Metadata

~~~bash
# READ-ONLY: find BigQuery tables within the lab project scope.
gcloud dataplex entries search \
  'system=bigquery type=table' \
  --project="$PROJECT_ID" \
  --scope="projects/$PROJECT_ID" \
  --limit=20 \
  --format="table(name,displayName)"

# READ-ONLY: search by column name.
gcloud dataplex entries search \
  'column:customer_id' \
  --project="$PROJECT_ID" \
  --scope="projects/$PROJECT_ID" \
  --limit=20

# READ-ONLY: try semantic search if CLI/version supports it.
gcloud dataplex entries search \
  'trusted daily revenue reports' \
  --project="$PROJECT_ID" \
  --scope="projects/$PROJECT_ID" \
  --semantic-search \
  --limit=20
~~~

`--project` specifies the **project executing the request**, whereas `--scope` restricts the **set of assets searched**; do not assume they are always identical. Organization scope requires the right org ID and IAM; scoping solely to one project will **miss** assets in another analytics project. Empty lists may simply reflect no matching sources or missing metadata permissions.

### 6.3. Viewing Entry Groups and Entries

~~~bash
# READ-ONLY: list entry groups in the selected location.
gcloud dataplex entry-groups list \
  --project="$PROJECT_ID" \
  --location="$LOCATION"

# READ-ONLY: for an existing custom group named "partner-data".
gcloud dataplex entries list \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --entry-group="partner-data"

# READ-ONLY: run only if the entry ID actually exists in the group.
gcloud dataplex entries describe "partner-orders" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --entry-group="partner-data"

# READ-ONLY: list custom aspect types in the location.
gcloud dataplex aspect-types list \
  --project="$PROJECT_ID" \
  --location="$LOCATION"
~~~

Do not try to describe a BigQuery table using `ENTRY_ID="dataset.table"` without first checking the **actual entry ID and entry group ID generated by the catalog**: display names, FQNs, and resource IDs are not necessarily identical. System groups like `@bigquery` appear at the source's location; for BigQuery multi-region datasets, that location may be `us` or `eu` rather than the developer's working region.

### 6.4. Cross-Checking BigQuery Metadata at the Source

~~~bash
# READ-ONLY: sample resource must exist and principal must have permissions.
bq show --schema --format=prettyjson \
  retail-analytics:mart.daily_revenue

# READ-ONLY: inspect basic metadata.
bq show --format=prettyjson \
  retail-analytics:mart.daily_revenue
~~~

Compare the schema, description, and last modification time at the source system with the catalog entry. If they conflict, **check ingestion/index latency and the source owner**—never overwrite system aspects to "fix" catalog metadata.

## 7. Enriching Metadata: Workflow and Configuration Examples

### 7.1. Start with Information Users Actually Need

Do not create hundreds of aspect fields before anyone uses them. A **minimum viable catalog** for a retail enterprise usually needs:

1. **Description and grain:** what does this data represent, and what does one row correspond to?
2. **Owner and steward:** who approves usage, and who handles incidents?
3. **Business term:** which definition of "net revenue" applies?
4. **Classification:** does it hold PII, payment data, or trade secrets?
5. **Freshness:** when is data refreshed, and how much lag is acceptable?
6. **Quality:** what tests prove the data is trustworthy, and what were the latest results?
7. **Lineage:** which sources feed it, and which dashboards break if upstream changes?

| Field | Direct Impact |
| --- | --- |
| Owner | Users know whom to contact for wrong numbers or access requests. |
| Grain and business definition | Prevents mistakenly summing item-grain and order-grain figures. |
| Freshness SLO | Prevents using a D-1 report for a real-time dashboard. |
| Classification | Guides selection of authorized views, masking, and approval workflows. |
| Lineage | Identifies impact ahead of schema or pipeline changes. |

### 7.2. Creating an Aspect Type via Console

In **Knowledge Catalog → Metadata types → Aspect types**, administrators can:

1. Select the project and **location**: `global` for cross-region reuse, or regional for location constraints.
2. Create aspect type `business-governance` with fields such as `owner_team`, `data_class`, and `sla_hours`.
3. Define data types and required/optional flags matching real needs.
4. Save the aspect type and grant the **steward team** permission to attach aspects.
5. Open an entry, attach the optional aspect at the **entry level** or supported column level, enter values, and verify via Search.

**Boundary to remember:** on system entries like BigQuery tables, Google-managed system aspects are usually **read-only**, whereas optional business aspects can be attached/edited with proper permissions. Running `CREATE OR REPLACE TABLE` in BigQuery can cause custom aspects attached to the original table to **not be preserved**; include metadata verification/restoration in migration runbooks instead of assuming metadata survives replacement forever.

### 7.3. Example Mapping an Aspect Once the Type Exists

Suppose the organization has **already created** aspect type `business-governance` in `asia-southeast1` with fields `owner_team STRING`, `data_class STRING`, and `sla_hours INT`. The JSON below is **illustrative CLI input**, not a file created in the lesson repository:

~~~json
{
  "retail-lab.asia-southeast1.business-governance": {
    "data": {
      "owner_team": "finance-data",
      "data_class": "internal",
      "sla_hours": 24
    }
  }
}
~~~

After saving this JSON to `governance-aspect.json` in a **dedicated lab environment** and verifying the **exact entry ID, entry group, and location**, the update command looks like:

~~~bash
# WRITE: run ONLY with approval and real existing resources/type.
gcloud dataplex entries update-aspects "partner-orders" \
  --project="retail-lab" \
  --location="asia-southeast1" \
  --entry-group="partner-data" \
  --aspects="governance-aspect.json"

# READ-ONLY: re-read entry to verify the new aspect.
gcloud dataplex entries describe "partner-orders" \
  --project="retail-lab" \
  --location="asia-southeast1" \
  --entry-group="partner-data"
~~~

Resource strings are **hypothetical**; the command succeeds only if the entry and aspect type already exist, schemas match, and the principal has sufficient permissions. `update-aspects` **does not replace the entry's entire aspect map**, yet for **each aspect listed in the file** it can **replace that aspect's entire content** rather than merging individual fields; read the current version before writing to avoid silently wiping someone else's fields. See [gcloud entries update-aspects](https://docs.cloud.google.com/sdk/gcloud/reference/dataplex/entries/update-aspects).

### 7.4. Automating Metadata Updates

In data pipeline CI/CD:

~~~mermaid
flowchart LR
    CHANGE["PR changes schema / pipeline"] --> TEST["Schema + contract tests"]
    TEST --> DEPLOY["Deploy BigQuery/Dataflow"]
    DEPLOY --> CHECK["Verify catalog sync"]
    CHECK --> META["Steward reviews aspects/glossary"]
    META --> SEARCH["Search + access tests"]
    SEARCH --> DONE["Hand off change"]
~~~

For custom sources, schedule a periodic job to read source metadata, perform **controlled upserts** of entries/aspects, emit audit logs, and flag metadata whose source no longer exists. For system sources, rely on the **source API** for source-owned attributes (schema, description); do not maintain manual metadata that contradicts the source.

## 8. Data Lineage, Data Profiling, and Data Quality

### 8.1. Lineage Answers "Where Did the Numbers Come From?"

~~~mermaid
flowchart LR
    APP["Cloud Run: payments"] --> RAW["BigQuery raw.payments"]
    APP2["Refund API"] --> REF["BigQuery raw.refunds"]
    RAW --> TRANS["BigQuery/Dataflow transform"]
    REF --> TRANS
    TRANS --> MART["mart.daily_revenue"]
    MART --> DASH["Finance dashboard"]
~~~

Lineage enables:

- **Upstream tracing:** which tables and jobs produced `mart.daily_revenue`?
- **Impact analysis:** if `raw.refunds` changes schema, which downstream tables/dashboards may be affected?
- **Incident investigation:** did an error originate in the source, the transform, or stale data?

In the Google Cloud ecosystem, the **Data Lineage API** automatically captures metadata from **supported integrations** once enabled, or from **OpenLineage/custom events**. Not every SQL statement, UDF, external API, or custom pipeline is automatically tracked in full: verify **coverage, project/region, and lineage viewing permissions**. Lineage can incur **processing and metadata storage charges**.

### 8.2. Data Profiling vs. Quality Scans

| Feature | Example | Limitation |
| --- | --- | --- |
| **Data profiling** | Value distributions, null rates, min/max, column cardinality. | Descriptive statistics do not prove business rules hold. |
| **Data quality scan** | `order_id` non-null, `amount_vnd >= 0`, uniqueness threshold, freshness rule. | Requires defining/maintaining rules and handling failures. |
| **Quality aspect/scorecard** | Latest scan status, quality score, run timestamp. | Does not replace query permissions; can be missing/stale if scans haven't run. |
| **Lineage** | Data flow across transforms. | Does not guarantee a transform implements the right business formula. |
| **Glossary/certification** | Term, owner, and trust sign-off. | Requires governance review; does not legally authorize usage on its own. |

A "certified" table whose data quality scan fails today must be flagged and investigated. Establish an **operational rule**: when freshness breaches its SLO or null rates exceed thresholds, alert the owner, review certification, and log an incident. Never delete old scan results to make scorecards look prettier.

## 9. IAM: Catalog Read Permissions Separate from Data Read Permissions

### 9.1. Who Needs What Permissions?

| Persona | Need | Roles to Consider |
| --- | --- | --- |
| **Data analyst** | Find assets, inspect metadata, request access. | `roles/dataplex.catalogViewer` plus source metadata roles (e.g., `roles/bigquery.metadataViewer`). |
| **Data consumer** | Run BigQuery queries on approved data. | BigQuery job permissions (`roles/bigquery.jobUser` on the execution project) and appropriate `dataViewer`/view access. |
| **Steward** | Maintain descriptions/aspects/glossaries, confirm owners. | Scoped Dataplex Entry/Aspect Type User/Editor roles depending on operations. |
| **Platform catalog admin** | Create entry groups/types, manage metadata permissions. | Catalog admin role or custom role with specific permissions. |
| **Data engineering pipeline** | Ingest custom metadata, update aspects. | Dedicated service account with create/update entry/aspect permissions scoped by group/type. |
| **Auditor** | Inspect policies, logs, lineage/quality. | Separate viewer roles for catalog/lineage/logs; no default access to underlying data. |

Exact role names vary by resource type and operation; check [Dataplex IAM roles](https://docs.cloud.google.com/iam/docs/roles-permissions/dataplex). **Never grant `roles/owner`, `roles/editor`, or BigQuery Admin to all analysts just to enable search.**

### 9.2. Metadata Visibility vs. Data Visibility

- **Permission to find an entry** does not implicitly grant `SELECT` on a BigQuery table, Cloud Storage object reads, or viewing sensitive values.
- For **system entries**, search results respect **metadata permissions at the source**. A user lacking BigQuery metadata permissions may not see the table even though the catalog entry exists.
- **Custom catalog entries** also have their own IAM on entry groups/types and metadata; those permissions grant no access on the external systems described in the entry.
- **Policy tags**, column-level security, masking, row access policies, and authorized views are **enforced at the data service**, not because an entry carries an aspect `confidential`.
- Search is bounded by **organization scope**, VPC Service Controls, and IAM; a broad catalog role cannot cross every perimeter.

**Example:** an analyst may see `mart.daily_revenue` and its schema in the catalog yet only be permitted to query a **view masking customer details**. Seeing a PII column name in the catalog does not mean you can read its values.

## 10. Case Study: Building a Catalog for Retail Data

### 10.1. Context

The system includes:

- `raw.payments`: payment data flowing from Cloud Run/Pub/Sub into BigQuery.
- `raw.refunds`: refunds from an internal service.
- `mart.daily_revenue`: aggregated table used for financial reporting.
- A Cloud Storage bucket containing legacy ingestion files and logs.
- Two teams currently reporting **two different "revenue" numbers**.

The data team needs to establish the set of **approved assets** before financial close, not just "spin up a catalog and call it done."

### 10.2. Implementation Plan

| Phase | Activities | Exit Criteria |
| --- | --- | --- |
| **1. Inventory** | Confirm BigQuery/Cloud Storage assets and metadata are ingested into the catalog. | Tables are searchable with accurate schemas/locations. |
| **2. Align terminology** | Finance defines net/gross revenue, refund cutoffs, and timezones. | Glossary has owners and approved formulas. |
| **3. Attach metadata** | Document grain, owner, classification, SLA, and contacts. | Every critical table has required metadata. |
| **4. Link** | Link glossary terms to tables/columns; verify lineage from sources. | Analysts distinguish raw, staging, and mart layers. |
| **5. Prove trust** | Configure profiling/quality checks and reconcile against sources. | Freshness and quality thresholds have recent results. |
| **6. Controlled access** | Grant authorized views or dataset/table permissions as needed. | Analysts query the right assets while PII stays protected. |
| **7. Operate** | Alert on schema changes, stale metadata, and departed owners. | Periodic steward reviews and audit/changelog in place. |

### 10.3. Analyst Experience

The analyst searches:

~~~text
system=bigquery type=table name:revenue
~~~

Then opens the `mart.daily_revenue` entry and checks:

1. **Definition:** `net_revenue = payments_successful - refunds_recorded`—is the day boundary UTC or Vietnam time?
2. **Grain:** `sale_date × channel` or `sale_date × SKU`?
3. **Freshness:** does an 07:00 ICT refresh meet a 06:00 reporting requirement?
4. **Quality:** did the latest scan PASS or FAIL, and what are the null/duplicate rates?
5. **Lineage:** where does `refund_amount` originate, and are late refunds handled?
6. **Access:** which view is certified by Finance, and who approves access if missing?

If two tables share the name `daily_revenue`, **never pick the top search result arbitrarily**. Compare owners, glossaries, lineage, and certification, and check with Finance before publishing numbers.

## 11. Operations, Metadata Quality, and Cost

### 11.1. Metadata Has a "Freshness SLO" Too

A healthy catalog must maintain **metadata accuracy**:

| Operational Metric | Suggested Measurement | Action When Missed |
| --- | --- | --- |
| **Coverage** | % of critical tables with an entry and owner. | Sync sources, assign ownership. |
| **Description completeness** | % of entries with reviewed descriptions/grain. | Assign steward to update. |
| **Metadata freshness** | Time from schema change to catalog entry update. | Check ingestion/indexing; raise alert. |
| **Glossary coverage** | % of business metrics with approved terms. | Hold review with Finance/Growth. |
| **Quality signal age** | Age of the most recent data quality scan. | Re-run scan, inspect jobs and sources. |
| **Broken ownership** | Entries whose owner team no longer exists. | Reassign owner per team roster. |
| **Discovery success** | % of requests finding the right asset and getting timely access. | Improve descriptions, synonyms, IAM workflow. |

**Illustrative SLO:** "100% of financial reporting tables have an owner, description, and business term; metadata changes are verified within 24 hours." This is a hypothetical internal target, **not a Knowledge Catalog SLA**.

### 11.2. Costs and Limits to Review

A catalog involves more than "search" costs:

- **Metadata storage** may be billed based on the volume of retained metadata.
- **Creating/managing metamodel resources** (entry types, aspect types, entry groups, entries, links) and **search calls** may fall under categories with no separate per-call charge per pricing docs, while still subject to quotas and IAM.
- **Data lineage** carries processing and metadata storage SKUs; enabling the API on high-activity projects can increase costs.
- **Profiling/quality scans** execute data processing jobs and must be budgeted separately by resource type and current pricing.
- **BigQuery** used for previews, quality validation, queries, or metadata exports still incurs query/compute/storage costs.
- **Connector/import jobs**, Cloud Run/GKE, Pub/Sub change feeds, and logs/Monitoring also carry real costs.

Measure **operational value**: hours saved finding data, access provisioning lead time, incidents prevented from metric misunderstandings, alongside metadata/quality/lineage costs. Never store sensitive data or entire raw rows inside custom aspects just to improve search matching.

### 11.3. Schema Change Workflow

Suppose engineering renames column `amount` to `gross_amount`:

1. Open a **change request** listing downstream consumers from lineage and inventories.
2. Maintain a **compatibility view** or versioned migration plan.
3. Apply the schema change in BigQuery and confirm the system entry metadata refreshes.
4. Update descriptions, aspect field references, and glossary mappings.
5. Re-run quality tests and re-verify owner/certification if results shift.
6. Test catalog search with both old and new intent terms, cross-checking the source system.
7. Record audit trail and rollback steps in case of missing data, lost aspects, or broken dashboards.

**Never rename a field solely in the catalog to mask an unchanged source schema.** The catalog reflects and annotates the source state; source changes must be driven through separate pipeline/schema governance.

## 12. Troubleshooting: Why Can't I Find the Data?

| Symptom | Possible Cause | Check First |
| --- | --- | --- |
| BigQuery table missing from Search | Missing metadata IAM on table/dataset, wrong scope/project/perimeter. | `bq show` as the current principal; scope, VPC SC, IAM. |
| Table appears in Search, query returns 403 | Has metadata permission, lacks data or job permission. | BigQuery IAM/Data Viewer/Job User and row/column policies. |
| Entry exists with outdated schema | Ingestion/indexing lag, or source not yet updated. | Metadata at source, modification timestamp, catalog status. |
| Two entries share the same name with different meanings | Missing owner/glossary/description or duplicate copy. | FQN, project, glossary mapping, and certified assets. |
| `system:bigquery` filter fails | Used `:` instead of exact `=`. | `system=bigquery type=table`. |
| `@bigquery` entry group cannot be edited | Service-managed system group. | Do not edit directly; manage source and optional aspects. |
| Attaching aspect fails | Aspect type missing, wrong location, field type mismatch, or missing role. | `aspect-types list`, schema template, IAM. |
| Writing aspect wipes an existing field | `update-aspects` replaces the specified aspect's full content. | Diff JSON before/after; supply all fields on update. |
| Glossary term finds no tables | Term not linked to entry/column or index lag. | Entry links, term details, user permissions. |
| Lineage missing | Data Lineage API disabled, missing permissions, or unsupported source. | Project settings, run logs, lineage coverage. |
| Stale data quality scorecard | Scan hasn't run, failed, or metadata publishing off. | Scan jobs, timestamps, scorecard aspects. |
| Metadata disappears after replacing table | `CREATE OR REPLACE TABLE` replaced asset and dropped old custom aspects. | Audit logs, metadata backups, re-attachment workflow. |
| Search returns fewer items than inventory | Search does not guarantee full recall and enforces IAM. | Use metadata export/list for inventory, not `COUNT(search)`. |

**Short runbook:** identify `project/region/FQN` → verify source still exists → verify principal and metadata permissions → check Search scope/VPC SC → inspect ingestion/entry/aspects → compare descriptions/owner/quality/lineage → propose approved fix. Never "fix" missing metadata by granting project Owner.

## 13. Exercises

### Exercise 1 — Data or Metadata?

Classify: (a) `order_id=O-1001`, (b) field `amount_vnd NUMERIC`, (c) `owner_team=finance`, (d) scan result "2% nulls", (e) IAM allowing SELECT. Which items are metadata, which are actual data, and which are access policies?

### Exercise 2 — Designing an Entry

For table `daily_revenue`, propose at least 6 metadata attributes so a newcomer can decide whether to use it for reporting. Include **grain**, owner, freshness, sensitivity, glossary term, and quality checks.

### Exercise 3 — Entry, Aspect Type, Aspect

An organization wants to standardize `owner_team`, `data_class`, and `sla_hours` across 300 tables. Which object serves as the **reusable template**, which holds **per-table values**, and when is a custom entry type needed?

### Exercise 4 — Search Syntax

Write three queries to find: (a) all BigQuery tables whose name relates to `revenue`; (b) entries having column `customer_id`; (c) BigQuery views in project `retail-analytics` in a supported region. Explain why `type:table` is invalid syntax.

### Exercise 5 — Table Not Found

Two analysts run the exact same search query, yet only one sees the table. Walk through checking **source metadata IAM, org/project scope, VPC Service Controls, and index/ingestion** before suspecting the table was deleted.

### Exercise 6 — View Permission vs. Query Permission

An analyst can see the description of `raw.customers`, but `SELECT` returns 403. Design access via **authorized views/masking** so PII cannot be read directly; explain why `roles/dataplex.catalogViewer` does not enable querying.

### Exercise 7 — Lineage and Glossary

Finance defines `Net Revenue = Successful Payments − Refunds`. Sketch the relationship between the glossary term and `mart.daily_revenue` table/columns; identify upstream sources and the impact of changing `raw.refunds` schema.

### Exercise 8 — Updating Aspects

A `business-governance` aspect currently has three fields, and a pipeline sends only one field in an update file. What can happen to the other fields? Write a read-before / write-after / verify checklist covering permissions and auditing.

### Exercise 9 — Quality and Certification

A table is labeled "certified", yet the latest quality scan ran 60 days ago and shows 8% null customer IDs. Should this report be used immediately? Who decides, and what evidence must be added?

### Exercise 10 — Measuring Catalog Success

A data governance team manages 500 tables; 320 have owners, 200 have descriptions, and 120 have glossary terms. Compute coverage percentages for each criterion, propose a 30-day priority target, and distinguish **tables lacking metadata** from **catalog entries hidden by IAM**.

**Hint:** owner **64%**, description **40%**, glossary **24%**. These coverage figures apply to the 500 tables inventoried from the source, **not a count reliably inferred from search results**.

## 14. Production Checklist and Official Documentation

| Item | Verification Criteria |
| --- | --- |
| **Product/API** | Recognizes Knowledge Catalog (formerly Dataplex Universal Catalog); CLI/IAM still `dataplex`. |
| **Inventory** | Defined scope, metadata ingestion sources, and reconciliation against source-system inventory. |
| **Metamodel** | Entry groups/types and aspects/links standardized by domain without redundancy. |
| **Business context** | Owner, steward, grain, description, glossary terms, and usage policies approved. |
| **Discovery** | Search filters use valid syntax; result trimming, metadata permissions, and recall limits understood. |
| **Lineage/quality** | Coverage, scan timestamps, alerts, and downstream impacts monitored. |
| **Security** | Catalog IAM separated from data IAM; PII/masking/authorized views enforced at source. |
| **Locations** | Global/regional aspect types, resource locations, and data residency reviewed. |
| **Automation** | Schema changes/`CREATE OR REPLACE TABLE` verify metadata and glossary links. |
| **Observability** | Coverage, freshness, search success, governance change logs, and metadata drift tracked. |
| **Cost** | Metadata storage, lineage, quality scans, data queries, and connector operations budgeted. |
| **Recovery** | Custom metadata recovery plan and rollback procedures for schema/permission changes. |

Official documentation for UI and API cross-reference:

- [Knowledge Catalog — overview](https://docs.cloud.google.com/knowledge-catalog/docs)
- [Transition from Dataplex Universal Catalog to Knowledge Catalog](https://docs.cloud.google.com/knowledge-catalog/docs/transition-dataplex-universal-catalog)
- [Metadata model: entry, entry type, aspect, and entry link](https://docs.cloud.google.com/knowledge-catalog/docs/metadata-overview)
- [Manage entries and ingest custom sources](https://docs.cloud.google.com/knowledge-catalog/docs/ingest-custom-sources)
- [Search assets](https://docs.cloud.google.com/knowledge-catalog/docs/search-assets)
- [Search syntax](https://docs.cloud.google.com/knowledge-catalog/docs/search-syntax)
- [Manage aspect types and aspects](https://docs.cloud.google.com/knowledge-catalog/docs/enrich-entries-metadata)
- [Manage business glossaries](https://docs.cloud.google.com/knowledge-catalog/docs/manage-glossaries)
- [About data lineage](https://docs.cloud.google.com/knowledge-catalog/docs/about-data-lineage)
- [Knowledge Catalog IAM](https://docs.cloud.google.com/knowledge-catalog/docs/iam-permissions)
- [gcloud dataplex entries search](https://docs.cloud.google.com/sdk/gcloud/reference/dataplex/entries/search)
- [gcloud dataplex entries update-aspects](https://docs.cloud.google.com/sdk/gcloud/reference/dataplex/entries/update-aspects)
- [Knowledge Catalog pricing](https://cloud.google.com/dataplex/pricing)

**Remember:** Dataplex/Knowledge Catalog does not replace BigQuery, Cloud Storage, or source systems: it helps **locate the right assets, understand metadata, link business definitions, and evaluate trust**. An **entry** represents an asset, an **aspect** adds context, a **glossary** aligns terminology, **lineage** traces provenance, and **source-system IAM** governs data reads. A catalog delivers value when metadata stays **accurate, fresh, owned, and verified**—not merely when the search box returns results.
