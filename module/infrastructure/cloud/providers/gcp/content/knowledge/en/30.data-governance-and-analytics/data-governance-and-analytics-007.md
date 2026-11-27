# Dataform and Managing SQL Transformations in BigQuery

## Learning Objectives

After this lesson, learners will be able to:

1. Distinguish **Dataform** (managing SQL code, dependencies, tests, and schedules) from **BigQuery** (storage and SQL execution), as well as from Dataflow/Beam.
2. Organize **repositories, development workspaces, `workflow_settings.yaml`, SQLX, release configurations, workflow configurations**, and dev/prod environments.
3. Write **declarations, tables/views, incremental tables, and assertions**; use `${ref(...)}` to build DAGs, catch data errors, and avoid hardcoded table references.
4. Compile, dry-run, test-execute, release with Git review, and schedule safely using a **custom service account** with least-privilege IAM.
5. Control **data correctness, lineage, location, BigQuery cost, access permissions, and rollbacks** in a Java/Cloud Run/BigQuery scenario.

## 1. Context: Data Transformation SQL Needs a Software Lifecycle Too

In the **CLOUD_PROVIDERS_GCP** track, Java/Spring Boot on Cloud Run creates orders; Cloud SQL stores transactions; Pub/Sub/Dataflow forwards events to BigQuery. The data team needs to build:

- **Staging** tables normalizing events from raw sources.
- **Mart** tables aggregating revenue by date and region.
- Checks for non-null IDs, uniqueness, and non-negative amounts.
- Production schedules, failure monitoring, and SQL change reviews.

If each analyst saves separate SQL snippets in the console and schedules them independently, you quickly run into **wrong table references, out-of-order execution, environment drift, and no visibility into who changed revenue logic**.

**Dataform** puts BigQuery transformations into **versioned code**, automatically builds a **dependency graph (DAG)**, generates/orchestrates SQL, and manages assertions. **BigQuery remains the SQL execution engine and table store**, so Dataform is neither a new database nor a compute layer like Dremel/Dataflow workers.

~~~mermaid
flowchart LR
  APP["Cloud Run Java"] --> SRC["Pub/Sub / Dataflow / GCS"]
  SRC --> RAW["BigQuery raw_orders"]
  RAW --> STG["Dataform: staging SQLX"]
  STG --> MART["Dataform: revenue mart SQLX"]
  MART --> BI["Looker / BI / reporting"]
  TEST["Dataform assertions"] -. "Quality checks" .-> STG
  TEST -. "Quality checks" .-> MART
  GIT["Git + code review"] --> DF["Dataform repository / compilation / workflow"]
  DF -. "Schedules and runs SQL in BigQuery" .-> STG
  DF -. "Schedules and runs SQL in BigQuery" .-> MART
~~~

| Tool | Primary Responsibility | Do Not Confuse With |
|---|---|---|
| **BigQuery** | Storage, SQL execution, query jobs, data IAM | A SQL code-review and DAG release system |
| **Dataform Core/SQLX** | Defines actions, references, assertions, SQL configs | A separate storage/compute engine |
| **Managed Dataform** | Repository/workspaces, compilation, runs, schedules, logs, Git integration | A streaming data source |
| **Dataflow/Apache Beam** | Batch/stream processing via distributed pipelines and SDKs | Dataform SQL mart definitions |
| **Cloud Composer/Workflows** | Orchestrates multiple services beyond BigQuery when needed | Mandatory for running Dataform schedules |

**When to choose Dataform:** SQL processing inside BigQuery needing dependency management, tests, Git, and scheduling. **When to choose Beam/Dataflow:** reading/transforming events or files in code, streaming/windowing/state, or connectors outside BigQuery. Many systems use **both**, though neither is mandatory together.

## 2. Architecture and Lifecycle of a Dataform Workflow

### 2.1. Core Objects

| Object | Purpose | Example |
|---|---|---|
| **Repository** | Holds Dataform code, Git connection, and runtime settings | `commerce-transform` |
| **Development workspace** | Developer working branch and compilation sandbox | `dev-analyst-a` |
| **`workflow_settings.yaml`** | Default project/dataset/location/assertions and Core version | Dataset `analytics_mart` |
| **`definitions/*.sqlx`** | Definitions for tables, views, sources, tests, and operations | `stg_orders.sqlx` |
| **Compilation result** | Graph and SQL compiled from a revision + overrides | Compiled code; writes no data |
| **Release configuration** | Selects Git commitish, overrides, and compile frequency | `production` |
| **Workflow configuration** | Selects release, actions/tags, schedule, and run identity | `daily-revenue` |
| **Workflow invocation** | A concrete execution run with per-action statuses | Job at 02:00 UTC |

### 2.2. Flow from Code to Data

~~~mermaid
flowchart TD
  CODE["SQLX + workflow_settings.yaml"] --> COMP["Compile: resolve refs and DAG"]
  COMP --> CHECK{"Valid compilation?"}
  CHECK -->|No| FIX["Fix SQLX / dependencies / config"]
  CHECK -->|Yes| DRY["BigQuery dry-run / verify permissions and schema"]
  DRY --> REVIEW["Git review + release configuration"]
  REVIEW --> RUN["Workflow configuration / manual invocation"]
  RUN --> JOBS["BigQuery SQL jobs following DAG"]
  JOBS --> ASSERT["Assertions / logs / quality status"]
  ASSERT --> MART["Tables/views for BI"]
~~~

**Compilation ≠ execution ≠ data acceptance.** Dataform compilation primarily validates SQLX/JavaScript syntax, refs, target names, and dependency cycles; it does not prove every BigQuery table, column, IAM permission, or GoogleSQL query is valid. After compiling, run a **BigQuery dry run and a staging workflow execution**. Assertions validate data after tables are built and do not replace business acceptance testing.

### 2.3. How the DAG Enforces Order

If you define `raw_orders → stg_orders → daily_revenue`:

- **Declaration** identifies an existing external source table without creating new data.
- **`stg_orders`** uses `${ref("raw_orders")}` both to reference the source and to declare the dependency.
- **`daily_revenue`** uses `${ref("stg_orders")}`; Dataform executes dependencies before running dependent actions.
- Actions with no dependencies between them can run **in parallel**; never rely on filename ordering.

`resolve()` only returns an identifier **without adding a dependency edge**. To enforce execution order, use `ref()` or explicit `dependencies`. Dependency cycles cause compilation errors.

## 3. SQLX: Tables, Views, Declarations, Assertions, and Operations

`.sqlx` is SQL paired with **Dataform config/templating**. After compilation, BigQuery receives standard **GoogleSQL**. Never run raw `config { ... }` or `${ref(...)}` verbatim in the BigQuery SQL editor.

| Action `type` | Purpose | Notes |
|---|---|---|
| `declaration` | Declares an external source table/view outside Dataform for `ref` | **Does not load or create** the source table |
| `view` | Creates a BigQuery view; optionally materialized per supported config | Standard views do not store a data copy |
| `table` | Materializes SELECT results as a BigQuery table | Re-runs rebuild/replace the table, incurring query/storage |
| `incremental` | Processes only new/changed data per custom logic | Requires watermark, key, and late-data plan |
| `assertion` | SQL returning **0 rows to pass**; any rows returned → fail | Does not automatically delete bad rows |
| `operations` | Runs manual GoogleSQL (DDL/DML/procedures) | Requires explicit dependencies and impact review |

Syntax-only example:

~~~sqlx
config {
  type: "view",
  name: "orders_recent",
  tags: ["daily"]
}
SELECT order_id, region
FROM ${ref("stg_orders")}
WHERE order_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
~~~

**`tags`** select subsets of actions when running workflows; they **do not** create IAM boundaries. `description`/`columns` document metadata; advanced governance can sync to **Knowledge Catalog** with appropriate IAM and configuration.

## 4. Repository and Environment Configuration

Dataform Core **3.0+** recommends `workflow_settings.yaml` at the root instead of legacy `dataform.json`. In real projects, **keep the Dataform Core version pinned by the repository** and test before upgrading.

**Example `workflow_settings.yaml` inside a hypothetical Dataform repository**:

~~~yaml
defaultProject: shop-dev-001
defaultDataset: analytics_mart
defaultAssertionDataset: dataform_assertions
defaultLocation: asia-southeast1
# dataformCoreVersion: use the stable version pinned by the repository.
~~~

Do not copy a versionless placeholder into a repository assuming Core does not need pinning. If an existing repo specifies **`dataformCoreVersion`**, keep its current version and verify compatibility when migrating from `dataform.json`. A repository can also set `projectSuffix`, `datasetSuffix`, `namePrefix`, and compilation variables to separate environments.

| Key | Meaning |
|---|---|
| `defaultProject` | Default BigQuery project; may differ from the Dataform repository project |
| `defaultDataset` | Default target dataset |
| `defaultAssertionDataset` | Dataset holding assertion result views |
| `defaultLocation` | **BigQuery SQL processing** location; must be compatible with source/target datasets |
| `dataformCoreVersion` | Pinned Dataform Core version |

**Location matters:** a Dataform repository can reside in a different region than **BigQuery datasets**. For example, the repo can live in `us-central1` while SQL processes tables in `asia-southeast1` if `defaultLocation` and resources align. Leaving location blank can cause dataset-less queries to default to **US**, and querying across incompatible regions will fail.

### 4.1. Separating Dev/Staging/Prod with Compilation Overrides

- Personal workspaces use a **schema suffix** derived from the workspace name, or run in a dedicated dev project.
- Production **release configurations** point to a reviewed branch/tag/commit SHA and apply environment overrides.
- **Workflow configurations** reference the corresponding release compilation and run only selected actions/tags.
- Real customer data and IAM should be isolated by **project/dataset**, not merely by appending `_dev` to table names.

**Never test-run `type: "table"` from a workspace into a production dataset before inspecting compiled targets:** executing it can overwrite a live table. Workspaces do not automatically isolate BigQuery data without configured overrides.

## 5. Lab: From Raw Order Events to a Revenue Table

The steps below are **lab examples**, not actions already executed. Assume a project `shop-dev-001`, permissions to create BigQuery tables/jobs, a Dataform repository, and an appropriate service account. Names are illustrative—never run against unauthorized production environments.

### 5.1. Step 0 — Prepare the Source Table in BigQuery

In **BigQuery Studio** with query location **asia-southeast1**, create dataset `raw_orders` first via console or `bq`:

~~~bash
bq --location=asia-southeast1 mk \
  --dataset shop-dev-001:raw_orders
~~~

Then run **GoogleSQL** (not SQLX) to create the test table:

~~~sql
CREATE TABLE IF NOT EXISTS `shop-dev-001.raw_orders.order_events` (
  event_id STRING,
  order_id STRING,
  event_ts TIMESTAMP,
  region STRING,
  amount NUMERIC,
  status STRING
)
PARTITION BY DATE(event_ts);
~~~

Insert sample data **once into the empty table**:

~~~sql
INSERT INTO `shop-dev-001.raw_orders.order_events`
  (event_id, order_id, event_ts, region, amount, status)
VALUES
  ('e1','o1', TIMESTAMP '2026-11-17 09:00:00+00','north',120,'PAID'),
  ('e2','o2', TIMESTAMP '2026-11-17 10:00:00+00','south',200,'PAID'),
  ('e3','o3', TIMESTAMP '2026-11-18 09:00:00+00','north', 50,'PENDING'),
  ('e4','o4', TIMESTAMP '2026-11-18 11:00:00+00','north', 80,'PAID');
~~~

**Caution:** re-running `INSERT` duplicates records because BigQuery does not enforce uniqueness like a traditional PostgreSQL primary key. With real sources, ingestion from Pub/Sub/Dataflow must maintain **event IDs, deduplication, and freshness SLAs**; Dataform does not automatically repair missing or duplicate upstream events.

### 5.2. Hypothetical Dataform Structure

~~~text
commerce-transform/
  workflow_settings.yaml
  definitions/
    order_events.sqlx
    stg_orders.sqlx
    daily_revenue.sqlx
    assert_positive_amount.sqlx
~~~

These are **example files inside a separate Dataform repository** for learners to create. This lesson does not ask you to edit those files inside the curriculum repository.

### 5.3. Step 1 — `definitions/order_events.sqlx`: Declare the Raw Table

~~~sqlx
config {
  type: "declaration",
  database: "shop-dev-001",
  schema: "raw_orders",
  name: "order_events"
}
~~~

Dataform treats `order_events` as a source managed **outside** the workflow. **Declarations neither create tables nor insert records.** The BigQuery table must already exist with the right location and IAM access; if the source is missing, compilation may still pass, while execution/dry runs will fail.

### 5.4. Step 2 — `definitions/stg_orders.sqlx`: Normalize and Test

~~~sqlx
config {
  type: "table",
  schema: "analytics_mart",
  description: "Normalized orders keeping the latest record per order",
  tags: ["daily"],
  assertions: {
    uniqueKey: ["order_id"],
    nonNull: ["order_id", "order_date", "amount"],
    rowConditions: ["amount >= 0"]
  },
  columns: {
    order_id: "Business order ID",
    order_date: "Event date in UTC",
    region: "Normalized sales region",
    amount: "Payment amount",
    event_ts: "Event timestamp"
  }
}

WITH latest AS (
  SELECT
    order_id,
    DATE(event_ts) AS order_date,
    LOWER(TRIM(region)) AS region,
    amount,
    event_ts,
    status
  FROM ${ref("order_events")}
  WHERE order_id IS NOT NULL
    AND event_ts IS NOT NULL
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY order_id ORDER BY event_ts DESC, event_id DESC
  ) = 1
)
SELECT order_id, order_date, region, amount, event_ts
FROM latest
WHERE status = 'PAID'
~~~

**Key points to understand:**

1. `${ref("order_events")}` creates a dependency on the declaration, avoiding hardcoded table paths in every SELECT.
2. `QUALIFY ROW_NUMBER()` picks the latest record by `event_ts, event_id` per `order_id`. This is a **lab convention**, not automatic business-version resolution when events arrive out of order or `event_ts` changes; production should use reliable versions or CDC sequences.
3. Filtering `status = 'PAID'` happens only after selecting the latest status, avoiding counting orders that later transitioned to CANCELLED.
4. `type: "table"` materializes results on each run; it is not an incremental table. Assertions generate separate checks after the table updates.
5. Dataform documents columns via `columns`, yet a `nonNull` assertion **does not turn BigQuery columns into REQUIRED/NOT NULL**. Enforced schema constraints in BigQuery DDL require supported mechanisms.

### 5.5. Step 3 — `definitions/daily_revenue.sqlx`: Aggregated Mart

~~~sqlx
config {
  type: "table",
  schema: "analytics_mart",
  description: "Daily revenue by region",
  tags: ["daily", "bi"],
  bigquery: {
    partitionBy: "order_date",
    clusterBy: ["region"]
  },
  assertions: {
    uniqueKeys: [["order_date", "region"]],
    nonNull: ["order_date", "region"],
    rowConditions: ["revenue >= 0", "order_count >= 0"]
  }
}

SELECT
  order_date,
  region,
  COUNT(*) AS order_count,
  SUM(amount) AS revenue
FROM ${ref("stg_orders")}
GROUP BY order_date, region
~~~

`bigquery.partitionBy` partitions by `order_date` and `clusterBy` clusters data by region. On large datasets, BI queries should filter with `WHERE order_date ...` to reduce bytes scanned. **Partitioning and clustering do not make queries free**; BigQuery still charges for table storage and query jobs.

**Expected lab results:**

| order_date | region | order_count | revenue |
|---|---|---:|---:|
| 2026-11-17 | north | 1 | 120 |
| 2026-11-17 | south | 1 | 200 |
| 2026-11-18 | north | 1 | 80 |

Total revenue is **400** across three PAID orders; the PENDING order `o3` is excluded. If you get 450, 520, or 600, check for duplicate source data, status filtering, or repeated lab `INSERT` runs.

### 5.6. Step 4 — `definitions/assert_positive_amount.sqlx`: Custom Assertion

~~~sqlx
config {
  type: "assertion",
  schema: "dataform_assertions",
  tags: ["quality", "daily"]
}

SELECT order_id, amount, region
FROM ${ref("stg_orders")}
WHERE amount < 0
   OR region IS NULL
   OR TRIM(region) = ''
~~~

**An assertion must return 0 rows to pass.** Returning any rows causes failure and records errors in workflow logs; bad rows are **not automatically deleted or fixed**. Dataform also creates assertion views in BigQuery for authorized inspectors. Pair with QA alerts and incident runbooks rather than only checking whether tables built.

### 5.7. Resulting Compiled DAG

~~~mermaid
flowchart TD
  R["order_events<br/>declaration"] --> S["stg_orders<br/>table + built-in assertions"]
  S --> M["daily_revenue<br/>partitioned table + assertions"]
  S --> A["assert_positive_amount<br/>manual assertion"]
~~~

Running the workflow via the DAG ensures **stg_orders** materializes before **daily_revenue** and its assertions. However, an assertion does not automatically **block** downstream actions unless dependencies or run selections are configured accordingly; if you need **fail-fast gating before publishing marts**, design explicit checks and dependencies supported by your orchestrator.

## 6. Incremental Tables: Processing New Data Without Corrupting Old Data

`type: "table"` typically recomputes the full SELECT on every run. With multi-TB history, `type: "incremental"` limits how much data is processed. However, **incremental logic is not automatically accurate** if sources send late events, mutate old records, or emit duplicates.

### 6.1. Example `definitions/fact_orders_incremental.sqlx` (Optional Alternative, Not Needed for Basic Lab)

~~~sqlx
config {
  type: "incremental",
  schema: "analytics_mart",
  uniqueKey: ["order_id"],
  bigquery: {
    partitionBy: "order_date",
    clusterBy: ["region"]
  },
  assertions: {
    nonNull: ["order_id", "order_date"],
    uniqueKey: ["order_id"]
  }
}

SELECT order_id, order_date, region, amount, event_ts
FROM ${ref("stg_orders")}
${when(incremental(), `
  WHERE event_ts >= TIMESTAMP_SUB(
    (SELECT IFNULL(MAX(event_ts), TIMESTAMP('1970-01-01'))
     FROM ${self()}),
    INTERVAL 3 DAY
  )
`)}
~~~

How it works:

- On the first run, `incremental()` is false: builds the table using all staging data.
- On subsequent runs, the filter considers only events near the target table's **max `event_ts`** within a **3-day lookback**.
- `uniqueKey: ["order_id"]` instructs Dataform to emit a keyed **MERGE/upsert** instead of pure append; this **differs** from `assertions.uniqueKey`, which only checks data.
- `${self()}` references the **target table itself** inside the workflow; BigQuery must have read access to it.

**Do not treat this snippet as a complete late-update solution:** events arriving later than the lookback, skewed `event_ts`, or edits to very old orders can be **missed**. An order updating its `order_date` may require reviewing **MERGE scan/partition pruning**. Production needs watermarks on **reliable ingestion/update times**, business keys, appropriate reprocessing windows, delete handling, and controlled **backfills/full refreshes**.

### 6.2. `updatePartitionFilter` and Write Bounds

For large tables, `bigquery.updatePartitionFilter` reduces how many **target table** partitions are scanned during MERGE. Yet if the filter scans only the last 7 days while an edit touches an older partition, MERGE can **miss the existing row and insert a duplicate**. Never set a filter purely to "save money" if it violates business update windows.

### 6.3. Full Refresh and Backfill

When SQL logic changes or older missing data is discovered:

1. List dependent tables, backfill volume, and scan costs.
2. Test full refresh/backfill in a staging dataset using snapshots/dataset copies when needed.
3. Run assertions and reconcile row counts and sums against source systems.
4. Pick a low-impact deployment window, handling downstream readers and rollbacks.
5. Modify production only upon approval; **full refreshes can recreate tables and drop grants/policy tags** unless governance controls are preserved and tested.

**Know when to stay simple:** daily aggregates that are small or fixed can use `type: "table"` more reliably than incremental models. Never pick incremental just because it sounds optimized; measure bytes processed, late-data rates, and remediation complexity.

## 7. Assertions, Testing, and Data Quality

| Tool | What It Checks | Limitations |
|---|---|---|
| **Compilation** | SQLX/JS syntax, refs, DAG, duplicate/cyclic targets | Does not prove BigQuery SQL is valid |
| **BigQuery dry run** | SQL syntax/types and tables/columns/permissions when sources exist | Does not prove data accuracy or fast execution |
| **Built-in assertions** | `nonNull`, `uniqueKey/uniqueKeys`, `rowConditions` | Check queries only; do not enforce schema |
| **Manual assertion** | SQL must return 0 rows, testing business invariants | Must author and maintain logic yourself |
| **Dataform unit tests** | Mock dependencies and expected outputs for an action | Does not simulate quotas, latency, or production data |
| **Staging execution** | Runs real DAG and assertions on near-real data | Incurs BigQuery cost and needs IAM/isolated targets |

**Good examples for CI:** a paid order with a negative amount must fail an assertion; duplicate `order_id` records must be caught; negative or out-of-bounds daily revenue must trigger alerts. Dataform logs failures in workflow logs; **blocking BI publication, rolling back, or backfilling is up to your operational system**.

### 7.1. Protecting Schema Changes and Metadata

In SQLX, `description` and `columns` document data, while BigQuery policy tags, row access policies, and masking remain the **real security controls**. When Dataform replaces/recreates tables, verify that **column policies/grants** are preserved as required. `preserveGovernanceControls` is an option with its own release status and limits; **never assume all governance metadata is preserved by default**.

**Data lineage** can be sent to **Knowledge Catalog** when configured with appropriate permissions. Lineage shows data relationships, **not proof that data has been anonymized or authorized for end users**.

## 8. Hands-On Lab: Running Dataform on Google Cloud

### 8.1. Preparation

In project **shop-dev-001** (hypothetical):

1. Enable the **Dataform API** and **BigQuery API**; check billing, organization policies, and quotas.
2. Create a **Dataform repository** in a supported region, e.g., `asia-southeast1` if listed in current supported locations.
3. Choose a **custom service account** for the repository and grant scoped Dataform/BigQuery roles per Section 10.
4. Create a development workspace and ensure `workflow_settings.yaml` sets `defaultProject`, `defaultDataset`, and `defaultLocation` accurately.
5. Create the four SQLX files from Section 5 under `definitions/`.
6. Inspect the **Compiled graph** before triggering the workflow; verify targets are not in production.

**Never use a repository serving live data to test** table creation, writes, or deletes. BigQuery jobs and storage still incur costs even though Dataform has no separate service fee.

### 8.2. Compile and Inspect Results

In **Dataform → Repository → Development Workspaces → workspace**:

- Open each SQLX file and inspect **Compiled queries** and error messages.
- Open the **Compiled graph** and confirm `order_events → stg_orders → daily_revenue`.
- Check the **Dataform Core version** used by the repo and the compiled project/dataset names.
- If BigQuery dry-run validation is available, verify permissions, schemas, and locations; compilation success does not guarantee dry-run success.

### 8.3. Run a Workflow in the Workspace

Click **Start execution** (button label may vary by UI), choose the actions to run, and select **Include dependencies** when needed. Observe:

1. `order_events` is a declaration, so no table-creation SQL runs.
2. `stg_orders` creates a table containing normalized data.
3. `daily_revenue` aggregates **400** on the sample dataset.
4. Assertions build and evaluate; zero rows = pass.
5. Workflow execution logs show per-action details and BigQuery query jobs (errors, bytes/slot-time when available).

If you run only `daily_revenue` without dependencies in a fresh project, it may fail with **missing upstream table**. Run upstream actions or select Include dependencies rather than hardcoding table paths to bypass the Dataform DAG.

### 8.4. Detecting an Intentional Defect

In the **lab raw table** (never production), insert a PAID order with a negative amount, e.g., `event_id=e_bad, order_id=o_bad, amount=-10`. Re-run the workflow:

- `stg_orders` may materialize the defective row, yet **rowConditions** fails.
- `assert_positive_amount` returns at least one row; status **FAILED**.
- Record the affected action and BigQuery job ID; do not edit production sources or let QA reports treat invalid numbers as published.

After completing the lab, delete test data and lab-created tables/datasets per approved procedures; never delete shared datasets, source tables, or outputs serving BI.

### 8.5. Optional: Compile Locally on a Developer Machine

Dataform has an **open-source CLI**. In a valid Dataform project with managed Node.js/npm:

~~~bash
# Inside a dedicated Dataform lab project, NOT the curriculum repository.
npm install --global @dataform/cli
dataform --version
dataform compile .
~~~

**`dataform compile` sends no SQL to BigQuery**, mainly validating the graph and building code; `dataform test`/`dataform run` are separate commands that can invoke BigQuery and incur charges. The CLI uses ADC when accessing Google Cloud. Pin Node/Core versions in CI rather than relying on untested global latest installs for releases.

## 9. Git, Releases, and Scheduling

**Never turn an active workspace into a production schedule.** A straightforward workflow:

~~~mermaid
flowchart TD
  DEV["Developer workspace / feature branch"] --> CI["Compile + BigQuery dry run + tests"]
  CI --> PR["Git pull request / review"]
  PR --> MAIN["Merged main / pinned release commit"]
  MAIN --> RC["Release configuration: compile result"]
  RC --> WC["Workflow configuration: schedule + actions"]
  WC --> RUN["Workflow invocation on BigQuery"]
  RUN --> OBS["Assertions + execution logs + cost alert"]
  OBS --> BI["Downstream analytics / BI"]
~~~

### 9.1. Release Configuration vs. Workflow Configuration

| Component | Main Settings | Output |
|---|---|---|
| **Release configuration** | Git branch/tag/commitish, compilation overrides, compilation schedule | Compiled graph/SQL snapshot |
| **Workflow configuration** | Release reference, actions/tags list, cron/timezone, execution identity | Scheduled runs of compiled results |
| **Workflow invocation** | One concrete execution | BigQuery jobs, action statuses, logs |

**Scheduling note:** to ensure workflows pick up the latest compilation result, docs recommend at least **one hour** between release compilation and scheduled workflow runs. If a prior scheduled run **has not finished** when the next trigger fires, the next run may be **skipped with an error**; schedule according to real runtimes and handle backlogs.

### 9.2. Orchestration Options

| Option | Best Suited For |
|---|---|
| **Dataform workflow configurations** | SQL DAG jobs and cron within Dataform with few external dependencies |
| **Cloud Workflows + Cloud Scheduler** | Orchestrating Dataform alongside other Google Cloud APIs |
| **Managed Service for Apache Airflow/Cloud Composer** | Complex pipelines with cross-system dependencies |
| **Cloud Build triggers** | Triggering compilation/execution on Git pushes |

**You do not need Composer just to run three SQLX tables nightly.** Choose orchestration based on cross-service dependencies, observability, failure handling, scheduling, and cost. For production, prefer **release configurations** over cloning a Git remote on every invocation: fetching Git on every run introduces network and SSH/credential failure points.

### 9.3. Deployment and Rollback

Recommended workflow:

1. **PR** modifies SQLX/metadata; review query plans, partitioning, columns/rules, and downstream impact.
2. **Compile + dry run** in dev; run assertions/integration tests in staging.
3. **Merge** approved revision; update release compilation for the pinned branch/tag/commit.
4. **Trigger a manual staging invocation** and verify row counts, revenue, and BI contracts.
5. **Enable the production workflow configuration** and monitor several cycles.
6. On failure, **revert to the previous Git revision/release configuration** to restore code; if bad data was written, you still need a separate **BigQuery restore/backfill**.

**Rolling back code does not automatically roll back data.** A `type: "table"` job may already have replaced the table; BigQuery time travel/snapshots/backups, schema compatibility, and data reconciliation form the real data recovery plan.

## 10. IAM: Developers, Execution Identity, and the Dataform Service Agent

**Dataform governs workflows; BigQuery governs data/queries.** Both IAM layers must be configured independently:

| Identity | Role / Task | Illustrative Permissions |
|---|---|---|
| **Dataform developer** | Edits SQLX, compiles/uses workspaces | `roles/dataform.editor` scoped to repository/workspace |
| **Release operator** | Manages releases, schedules, and workflows | Dataform Admin or appropriate role with environment approval |
| **Execution service account** | Executes BigQuery SQL jobs | `roles/bigquery.jobUser` on job project; Viewer on sources, Editor on targets per dataset |
| **Dataform service agent** | Dataform infrastructure impersonating execution identity | Service-agent role + `iam.serviceAccountUser` and `iam.serviceAccountTokenCreator` on effective SA |
| **Security/BI analyst** | Inspects lineage, policies, reports | Appropriate metadata/log/BigQuery reader roles |

### 10.1. Do Not Confuse the Service Agent with the Execution Service Account

The Dataform service agent typically looks like:

~~~text
service-PROJECT_NUMBER@gcp-sa-dataform.iam.gserviceaccount.com
~~~

**Strict act-as mode applies to repositories.** Workflows must run using a **custom service account** or supported Google Account credentials—**never rely on the default Dataform service agent as the execution identity**. When using a custom SA:

- The user creating/editing workflow executions needs **`iam.serviceAccounts.actAs`** on the chosen SA.
- The Dataform service agent needs **`roles/iam.serviceAccountTokenCreator`** to mint impersonation tokens for the service account, and **`roles/iam.serviceAccountUser`** to support automated scheduled runs.
- The execution SA needs **BigQuery Job User** on the job-execution project, **Data Viewer** on source datasets, and **Data Editor** on target datasets. Grant at the dataset level where supported; certain dataset management or policy operations require extra permissions.
- If the service account lives in a **different project**, check **cross-project service account attachment** constraints and organization policies.

**Never grant Owner to the service agent or execution SA** just to bypass a 403. Every principal must be auditable; narrow scope and check inherited permissions from project/folder/organization.

### 10.2. Example BigQuery Grants in a Lab Project/Dataset

~~~bash
# Check principal details before making changes:
gcloud projects describe shop-dev-001 \
  --format="value(projectNumber)"

# Grant query job creation to the execution SA on the lab project.
# Requires setIamPolicy; run per organizational approval.
gcloud projects add-iam-policy-binding shop-dev-001 \
  --member="serviceAccount:dataform-exec@shop-dev-001.iam.gserviceaccount.com" \
  --role="roles/bigquery.jobUser"
~~~

**These are not the complete grants:** reading `raw_orders` and writing `analytics_mart` still require **dataset-level IAM**. For the Dataform service agent, grant Token Creator/Service Account User **on the specific custom service account**, not project-wide unless necessary. Never put passwords or API keys in SQLX, workflow configs, or Git; use Secret Manager/ADC properly for the workload.

## 11. Data Governance, Security, and Lineage

Dataform governs **transformation code and metadata**, but **does not replace** data protection layers:

| Goal | Primary Mechanism |
|---|---|
| Reading/writing BigQuery data | BigQuery IAM, row-level policies, column policy tags/masking |
| Geographic data placement | BigQuery dataset locations, org policies, export restrictions |
| Data validation | Dataform assertions/unit tests, reconciliation with sources |
| Source & relationship definitions | Dataform declarations/ref/DAG; Knowledge Catalog lineage when configured |
| Git/secrets control | Repository roles, branch protection, Secret Manager, access reviews |
| Log security | Cloud Logging IAM/retention, masking query parameters/customer data |
| Recovery on schema/data errors | BigQuery time travel/snapshots/backups/backfills + release rollback |

**Passing assertions do not prove GDPR/PCI compliance or full business correctness.** For example, `order_count` and `revenue` may both be positive while revenue is double-counted due to ingestion duplicates; separate reconciliation, idempotency, and data contracts are required.

### 11.1. Metadata, Data Catalog, and Lineage

Dataform can publish **table/column descriptions**, BigQuery labels/tags, and lineage to **Knowledge Catalog** per current configuration. Metadata syncs can run **asynchronously after an action succeeds**; temporary sync failures do not necessarily fail the BigQuery SQL job. Grant **Dataplex Catalog Editor/Data Lineage Events Producer** only when those features are used.

### 11.2. Dataset Location and Sensitive Data

A Dataform repository does not force tables to reside in the repository's own region. `defaultLocation` must match the BigQuery SQL processing location; **do not directly query incompatible datasets across regions**. Review cross-region copies/exports, CMEK permissions, time travel, and retention per dataset rather than by repository name.

## 12. Monitoring Workflows and Costs

### 12.1. Does Dataform Have a Separate Charge?

Per official pricing, **Dataform itself is a free service**, though associated resources **still incur charges**:

| Component | Cost Source |
|---|---|
| **BigQuery query jobs** | Bytes billed on-demand or capacity/reservation slots |
| **BigQuery managed tables** | Storage, partitions/snapshots/retention per billing model |
| **Dataform assertions** | Quality check queries also consume BigQuery compute |
| **Cloud Logging** | Logging ingestion/retention based on pricing and volume |
| **Cloud Scheduler/Workflows/Airflow/Cloud Build** | Separate charges when using external orchestration |
| **Cross-region/network/data export** | Charges depending on sources, targets, and transfer paths |

If a mart rebuilds from 5 TB of raw data every hour, **Dataform having no service fee** does not make 120 BigQuery scans free. Optimize **partition filters, column projection, incremental windows, tag/action selection, run frequency**, and intermediate datasets.

### 12.2. Metrics to Monitor

| Observation | Question |
|---|---|
| **Compilation error rate** | Are there SQLX/ref/dependency/version errors? |
| **Workflow invocation status** | Did scheduled runs succeed, fail, or get skipped? |
| **Action runtime and BigQuery job ID** | Which table is slow, and which assertion failed? |
| **BigQuery `total_bytes_billed`, `total_slot_ms`** | Which SQL queries are expensive or slot-heavy? |
| **Data freshness / last successful run** | How far behind SLA is the mart? |
| **Assertion failure count** | Is data violating business rules or hitting schema drift? |
| **Storage bytes/partition growth** | Is incremental loading creating duplicates or growing uncontrollably? |
| **IAM/metadata changes** | Were broad permissions granted, policy tags altered, or datasets deleted? |

Example inspecting BigQuery jobs in a region (GoogleSQL):

~~~sql
SELECT
  job_id,
  creation_time,
  state,
  total_bytes_billed,
  total_slot_ms,
  error_result.message AS error_message
FROM `shop-dev-001.region-asia-southeast1.INFORMATION_SCHEMA.JOBS_BY_PROJECT`
WHERE creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)
  AND job_type = 'QUERY'
ORDER BY creation_time DESC
LIMIT 50;
~~~

**`JOBS_BY_PROJECT`** only lists jobs visible under your IAM permissions and region qualifier. Certain fields may be NULL while a job is still running. Under **capacity-based pricing**, job `total_bytes_billed` does not directly represent reservation baseline spend; **Cloud Billing** remains the source of truth for invoices.

### 12.3. Alerts and Cost Controls

- Alert on **no successful invocation** before BI needs the data, rather than alerting only when a job fails.
- Alert on **assertion failures** for critical tables and name the data owner.
- Cap runaway queries using **BigQuery quotas and `maximum_bytes_billed`/dry runs** in appropriate pipelines; measure before scaling out.
- Verify **query caching, partition pruning, and incremental scans** in practice; never assume any `WHERE` date filter automatically prunes partitions.
- **Budget alerts do not automatically stop workflows or cap spend.** Hard guardrails require controlled permissions, quotas, and automation.

## 13. Layered Troubleshooting

| Symptom | First Suspect | How to Check |
|---|---|---|
| **Compilation error: ref not found** | Misspelled action, missing declaration, mismatched override name | `definitions/` files, compiled graph, `ref` |
| **Circular dependency** | A refs B and B refs A, or wrong dependencies | Rebuild DAG, break cycle |
| **Compile passes, BigQuery syntax error** | Compile does not validate all GoogleSQL | Compiled SQL, BigQuery dry run, job logs |
| **Not found: table/dataset** | Declaration source missing or upstream hasn't run | Dataset resource, Include dependencies, IAM |
| **Not found in location US** | `defaultLocation` mismatches dataset | Dataset location, compile/runtime settings |
| **`PERMISSION_DENIED` at runtime** | Execution SA lacks Job User/Viewer/Editor | Effective IAM of execution identity, job project, dataset |
| **Cannot schedule with custom SA** | Missing strict act-as / Token Creator / SA User | Dataform service agent and bindings on effective SA |
| **Workspace overwrites production table** | Missing compilation overrides or wrong targets | Inspect compiled target project/schema before running |
| **Workflow runs but assertion fails** | Rows violate quality conditions | Assertion view, upstream source, event dedup |
| **Incremental table balloons** | Missing `uniqueKey`/merge, late-data logic, duplicate loads | MERGE SQL, business keys, row counts, updated partitions |
| **Incremental misses updates** | Lookback too short or flawed watermark | Event/update timestamps, reprocessing policy |
| **Workflow skipped** | Previous run still active at next cron trigger | Workflow logs, cron schedule, runtime duration |
| **Unstable production Git compile** | Remote Git credentials/network/compiling too frequently | Logs, release configs, Git provider connection |
| **Columns/policy tags lost after refresh** | Recreating table drops governance metadata | BigQuery policy metadata, Dataform code and options |
| **Unexpectedly expensive jobs** | Full rebuilds, `SELECT *`, missing partition pruning | `INFORMATION_SCHEMA`, bytes billed, partitions |
| **New lineage missing** | Async metadata sync or missing Catalog IAM | Workflow logs, Catalog permissions, sync status |

**5-step runbook:** identify **repo/workspace/release + compilation result** → inspect **compiled targets/DAG** → verify **effective execution identity/IAM/location** → check **BigQuery job and assertion logs** → fix in **staging** and run controlled replay/backfill. Never resolve errors by granting `roles/owner` or blindly full-refreshing production.

## 14. Case Study: Auditable Sales Data Management

Company **Hai Nam** has a 5-person data team and a Java backend on Cloud Run. Every night they need total revenue by region, yet data can arrive up to 48 hours late, and post-release audits must identify which SQL revision produced a report.

| Requirement | Solution |
|---|---|
| Source data managed by another team | BigQuery source table + Dataform `declaration` |
| Standardized, testable logic | `stg_orders`, `daily_revenue`, assertions |
| Edit SQL without immediately touching prod | Dev workspace, schema suffix or separate project, Git PR |
| Versioned releases | Release configuration from reviewed commit/tag |
| Automated run at 02:00 UTC | Workflow configuration with schedule and custom SA |
| Data arriving 48 hours late | Reprocessing window exceeding SLA, event version logic, and backfill |
| Least privilege | JobUser on job project, Viewer on sources, Editor on targets, strict act-as |
| Cost control | Date partitioning, bytes/slot monitoring, budgets, appropriate cadence |
| Revenue bug recovery | Revert SQL release **and** restore/recompute data |

### 14.1. Acceptance Tests

| Test | Expected |
|---|---|
| Run all four SQLX files on a lab with source populated | Graph compiles; mart reports total revenue **400** |
| One negative order | Assertion fails and workflow logs record it clearly |
| Duplicate order in raw | Staging picks right version; assertion catches if final output still has duplicates |
| Source table changes column | Dry run/execution flags mismatch; CI blocks release |
| Developer lacks prod permissions | Cannot execute prod workflow |
| Job runs in wrong location | Caught via dataset/job location mismatch error |
| Incremental receives 2-day-late update | Reprocesses/merges when within lookback and key is valid |
| Incremental receives 10-day-late update | Handled by explicit backfill/reconciliation; never claim "automatic" |
| Faulty SQL deployed | Roll back release and restore/recompute impacted tables |

### 14.2. Report Completion Criteria

Never ask only "Is the Dataform job green?". Check **last successful data timestamp**, assertion results, source/target row counts, revenue reconciliation, downstream report consumers, and the BigQuery bill. A workflow that succeeds while silently dropping 10% of events still produces a wrong report.

## 15. Exercises and Suggested Answers

### Exercise A — Dataform or Dataflow?

**Question:** A Java backend publishes events via Pub/Sub, and the team needs to filter streams by event time and compute 5-minute windows; which tool fits? Next, the team needs nightly BigQuery marts and Git-managed SQL.

**Answer:** **Beam/Dataflow** handles streaming and windowing; **Dataform** manages BigQuery SQL transforms, DAGs, and quality. Both can be used together.

### Exercise B — `ref` vs. `resolve`?

Table A references B, yet B is not guaranteed to run first.

**Answer:** `resolve("B")` only returns an identifier without creating a dependency. Use `ref("B")` or `dependencies` so Dataform enforces execution order.

### Exercise C — Does `declaration` Create a Table?

Dataform compiles cleanly, yet BigQuery reports `raw_orders.order_events` does not exist.

**Answer:** `declaration` only **declares an existing source**; it does not create tables. Create/populate the source first and check project/dataset/IAM/location.

### Exercise D — Calculate Lab Output

Four sample records exist: three PAID orders with amounts 120, 200, and 80, and one PENDING order with amount 50.

**Answer:** Reported revenue is **400**, PAID order count is **3**, grouped by date/region as shown in Section 5.

### Exercise E — Negative Assertion

A PAID order has `amount=-10`; built-in `rowConditions` checks `amount >= 0`.

**Answer:** The assertion fails, even though the table may have materialized. Fix the source defect rather than disabling the assertion to hide the failure.

### Exercise F — Incremental and the Two `uniqueKey` Settings

What is the difference between `uniqueKey: ["order_id"]` and `assertions: { uniqueKey: ["order_id"] }`?

**Answer:** The first controls **keyed incremental MERGE**; the second **tests for duplicates**. An assertion alone does not turn an append into an upsert.

### Exercise G — Late Update

An order updates 10 days later, while the incremental filter reads only the last 3 days.

**Answer:** It can be missed. You need reliable ingestion/update timestamps, a suitable lookback, or a backfill; avoid short filters when the SLA requires longer lookbacks.

### Exercise H — IAM Service Account

A Dataform developer can edit SQLX, yet scheduled runs fail on service account impersonation.

**Answer:** Check **strict act-as**: `actAs` permission for the configuring user, **Service Account User + Token Creator** for the Dataform service agent on the effective SA, and BigQuery job/data permissions on the execution SA.

### Exercise I — Does Passing Compilation Mean It Runs?

An SQLX file references a nonexistent column `amount_usd`, yet the compiled graph succeeds without error.

**Answer:** Expected, because compilation does not fully validate BigQuery schemas. Run BigQuery dry runs and staging executions before releasing.

### Exercise J — Rollback

After deploying buggy Dataform code, `daily_revenue` is rebuilt with missing revenue.

**Answer:** Reverting the commit/release does not restore the table; restore from snapshots/time travel or rerun fixed logic/backfill, then verify downstream dashboards and reconciliation.

### Exercise K — Finance

A team argues Dataform is free, so they schedule a full scan of a 5 TB table every 15 minutes.

**Answer:** The Dataform service is free, yet **BigQuery queries/storage and Cloud Logging/orchestration still cost money**. Size workloads, partitioning/incrementals, and schedules, and monitor Cloud Billing.

## 16. Summary and Official Documentation

**Six key takeaways:**

1. **Dataform manages SQL code/quality/dependencies**, while BigQuery executes and stores data; never treat Dataform as a streaming engine.
2. **`ref()` creates DAG edges**, declarations represent external sources, tables/views/incrementals materialize data, and assertions test outputs.
3. **Compilation does not guarantee valid BigQuery SQL**; validate with dry runs, staging executions, unit/data assertions, and output reviews.
4. **Version control + workspace/release/workflow configurations** establish controlled release paths rather than editing prod directly.
5. **Strict act-as/IAM, dataset locations, policy tags, and lineage** must be governed for exact identities and resources.
6. **Dataform is free, but BigQuery is not**; incrementals, partitioning, quality checks, backfills, query jobs, and budgets affect both correctness and cost.

**Official Google Cloud documentation:**

1. [Dataform overview](https://docs.cloud.google.com/dataform/docs/overview) — repository/compilation/workflow lifecycle.
2. [SQL workflows](https://docs.cloud.google.com/dataform/docs/sql-workflows) — graph and action types.
3. [Repository/workflow settings](https://docs.cloud.google.com/dataform/docs/manage-repository) — `workflow_settings.yaml`, location, Core versions.
4. [Declare data sources](https://docs.cloud.google.com/dataform/docs/declare-source) — `declaration`.
5. [Create tables and incremental tables](https://docs.cloud.google.com/dataform/docs/create-tables) — `type, uniqueKey, ref`.
6. [Set dependencies](https://docs.cloud.google.com/dataform/docs/dependencies) — `ref` and DAGs.
7. [Test data quality](https://docs.cloud.google.com/dataform/docs/test-data) — built-in/manual assertions and unit tests.
8. [Configure compilation and releases](https://docs.cloud.google.com/dataform/docs/configure-compilation) — compilation overrides.
9. [Schedule SQL workflows](https://docs.cloud.google.com/dataform/docs/schedule-runs) — workflow configs, Workflows/Scheduler/Airflow.
10. [Dataform IAM](https://docs.cloud.google.com/dataform/docs/access-control) — service agent, strict act-as, and BigQuery roles.
11. [Dataform troubleshooting](https://docs.cloud.google.com/dataform/docs/troubleshooting) — compile, execution, and Git errors.
12. [Dataform CLI](https://docs.cloud.google.com/dataform/docs/use-dataform-cli) — local compile/test/run.
13. [Dataform pricing](https://cloud.google.com/dataform/pricing) — Dataform free, associated services billed.
