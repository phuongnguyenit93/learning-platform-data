# Azure Databricks and Data Processing with Apache Spark

An enterprise receives data from transactional applications, CSV/JSON files, ERP systems, clickstream events, and sensors. Millions of records arrive daily that need standardization, quality checks, joins, and serving to reports. Once volume exceeds what a single process handles conveniently or data arrives continuously, engineering teams need a way to **distribute computation, enforce quality, and operate recoverable pipelines**.

**Apache Spark** is a distributed data processing engine supporting DataFrames, SQL, batch processing, machine learning, and Structured Streaming. **Azure Databricks** provides a managed Spark-based environment with notebooks, compute, Delta Lake, Jobs/Workflows, SQL analytics, and Unity Catalog to build data platforms on Azure.

This lesson belongs to the **Data Platforms and Analytics** chapter of the **CLOUD_PROVIDERS_AZURE** module. It connects Azure Databricks with subscriptions and resource groups, Microsoft Entra ID, virtual networks, Azure Data Lake Storage Gen2 (ADLS Gen2), Key Vault, Azure Monitor, and the deployment, security, monitoring, and cost control of Azure application architectures.

**Scope:** Spark fundamentals and practical Databricks design patterns. Features such as serverless, compute types, catalogs, deployment models, regions, and SKUs change across releases and tiers. Never assume every feature exists in every workspace; verify documentation and organizational policies before running workloads.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain driver, executor, task, partition, DAG, stage, lazy evaluation, and shuffle in Apache Spark.
2. Distinguish Spark DataFrame API, Spark SQL, RDD, and pandas; choose the right tool by scale and problem.
3. Understand the components of an Azure Databricks workspace: notebooks, compute, Databricks Runtime, Jobs/Workflows, SQL warehouses, Delta Lake, and Unity Catalog.
4. Describe a lakehouse architecture using ADLS Gen2, Bronze/Silver/Gold, and Delta tables.
5. Write PySpark to read, standardize, filter errors, deduplicate, and aggregate orders.
6. Read/write Delta data within an authorized schema; understand the transaction log, ACID, schema enforcement, and MERGE.
7. Compare batch ingestion, Auto Loader, and Structured Streaming with checkpointing, state, and event-time semantics.
8. Design data access controls with Unity Catalog, Microsoft Entra ID, managed identities, and private networking.
9. Choose job compute, interactive compute, or SQL warehouses by workload and budget.
10. Understand how to optimize partitions, joins, skew, small files, adaptive query execution, and query plans.
11. Deploy pipelines with orchestration, CI/CD, data quality checks, lineage, and safe retryability.
12. Monitor Spark UI, job runs, logs, Databricks Units (DBUs), and Azure infrastructure costs.
13. Identify scenarios where Databricks should—and should not—be chosen over other data services.

Examples here use **Python/PySpark**, SQL, and notebook structures. Never provision resources or execute workloads on a production subscription.

## 2. Problem Statement: From Raw Files to Trustworthy Reports

Suppose an e-commerce platform produces:

- Orders and OrderItems from an App Service backend.
- Website clickstream JSON events.
- Customer data from a relational database.
- Partner product CSV files.
- Payment events from Event Hubs or a messaging service.

Business goal: deliver daily revenue reports by tenant and date every morning, while catching corrupted data, duplicate records, and refunded orders.

~~~mermaid
flowchart LR
    A["App / ERP / Event sources"] --> L["ADLS Gen2 landing"]
    L --> B["Bronze: ingest raw"]
    B --> S["Silver: clean, validate, deduplicate"]
    S --> G["Gold: business aggregates"]
    G --> Q["Databricks SQL / BI / Analytics"]
    S --> M["ML features / downstream apps"]
    B --> E["Quarantine / data quality alerts"]
    S --> E
~~~

You must solve simultaneously:

1. **Scale:** data exceeds single-node RAM/CPU.
2. **Data quality:** wrong field types, nulls, duplicates, late arrivals.
3. **Repeatability:** rerunning a batch does not produce duplicate data.
4. **Governance:** which tenant may read which table?
5. **Recovery:** where does a job resume after failing midway?
6. **Cost:** avoid keeping expensive compute running while pipelines are idle.
7. **Lineage:** which source produced the numbers in a report?

Spark distributes computation; Databricks provides the operational and governance environment. They **do not invent business rules**, replace solid schema design, or guarantee every pipeline is exactly-once unless write logic is idempotent.

## 3. How Does Apache Spark Work?

### 3.1. Driver and Executors

~~~mermaid
flowchart TD
    D["Driver: SparkSession, planner, scheduler"] --> E1["Executor 1"]
    D --> E2["Executor 2"]
    D --> E3["Executor 3"]
    E1 --> T1["Tasks / data partitions"]
    E2 --> T2["Tasks / data partitions"]
    E3 --> T3["Tasks / data partitions"]
    E1 --> S["Read / Write distributed storage"]
    E2 --> S
    E3 --> S
~~~

- **Driver:** runs the Spark coordinator program, builds query plans, schedules work, and aggregates status.
- **Executors:** worker processes executing tasks using CPU/RAM and optionally caching partitions.
- **Task:** unit of computation running on one partition within a stage.
- **Partition:** logical slice of data processed in parallel by Spark; not synonymous with a storage directory or a Cosmos DB partition key.
- **Job:** typically triggered by an action such as `count`, `collect`, or `write`.
- **Stage:** group of tasks runnable in parallel between shuffle boundaries.

The driver **is not a place to collect huge datasets**. Calling `collect`/`toPandas` on tens of millions of rows can crash the driver with out-of-memory errors even if the Spark cluster has many executors.

### 3.2. DAG and Lazy Evaluation

Spark DataFrame operations such as `select`, `filter`, `withColumn`, and `join` are usually **transformations**: Spark builds an execution plan without running it immediately.

Operations such as `count`, `show`, `collect`, and `write` are **actions**, triggering job execution.

~~~python
from pyspark.sql import functions as F

filtered = df.filter(F.col("status") == "paid")  # transformation
grouped = filtered.groupBy("tenant_id").count()   # transformation

grouped.explain()  # inspect execution plan
grouped.show()     # action: triggers Spark computation
~~~

This means a notebook can step through dozens of transformation cells very quickly and only begin heavy compute consumption when an action is invoked.

### 3.3. Narrow and Wide Transformations

| Type | Examples | Impact |
|---|---|---|
| Narrow | `filter`, `select`, simple `withColumn` | Typically executes within existing partitions |
| Wide | `groupBy`, `orderBy`, `distinct`, many joins | May require shuffling data across executors |
| Action | `count`, `show`, `write` | Triggers DAG execution |
| Cache/persist | `cache` or `persist` | Retains data when materialized by an action, consuming RAM/disk |

**Shuffle** redistributes data across partitions by keys or ordering, incurring network and disk I/O. A `groupBy` over billions of records or an unoptimized join can be very expensive.

### 3.4. Shuffle and Data Skew

Suppose an events table has 80% of records belonging to one large tenant. Grouping by `tenant_id` forces one partition to process vastly more data than others.

~~~text
Partition 1: tenant-a 80 million events
Partition 2: tenant-b 2 million events
Partition 3: tenant-c 1 million events
...
~~~

As a result, one executor runs for a long time while all others sit idle. This is **data skew**, which cannot be cured merely by adding more workers while key distribution remains skewed.

Mitigation approaches include:

- Analyze skew upfront rather than picking partition keys blindly.
- Use adaptive query execution where supported.
- Split hot keys or apply salting when appropriate.
- Broadcast small tables if eligible.
- Partition data around actual access and query patterns.
- Measure shuffle read/write, spill, and task durations in Spark UI.

### 3.5. Spark DataFrame, SQL, RDD, and pandas

| Tool | Best Fit | Notes |
|---|---|---|
| DataFrame API (PySpark) | ETL, joins, cleansing, aggregations | Catalyst optimizer optimizes query plans |
| Spark SQL | Queries, views/tables, BI transformations | Still executes distributed via Spark |
| RDD | Specialized low-level algorithms | Less structural optimization than DataFrames |
| pandas | Data fitting in single-machine RAM, quick analysis | Does not distribute across Spark executors |
| pandas API on Spark | Distributed pandas-like API | Semantics/performance differ from local pandas |
| Databricks SQL | SQL analytics/warehousing and BI workflows | Requires SQL warehouse compute and data permissions |

For standard SQL/ETL pipelines, prefer **DataFrame API or Spark SQL**. Never write a Python `for` loop reading JSON rows one by one and calling APIs/DBs sequentially from the driver when Spark provides distributed columnar primitives.

## 4. What Does Azure Databricks Add?

### 4.1. Key Components

~~~mermaid
flowchart TD
    W["Azure Databricks Workspace"] --> N["Notebooks / Repos / Development"]
    W --> C["Compute: interactive / jobs / serverless if supported"]
    W --> J["Lakeflow Jobs / Workflows orchestration"]
    W --> Q["Databricks SQL Warehouses"]
    W --> U["Unity Catalog governance"]
    C --> S["Apache Spark engine"]
    S --> D["Delta Lake tables on cloud storage"]
    Q --> D
    U --> D
    J --> C
    J --> Q
~~~

- **Workspace:** interface and scope housing notebooks, compute settings, jobs, and assets.
- **Databricks Runtime:** managed environment bundling Spark with Databricks libraries, optimizations, and versioned features.
- **Notebooks:** write Python, SQL, and other supported languages for data exploration and processing.
- **Compute:** execution resources for workloads, either classic compute or serverless depending on workspace features.
- **Jobs/Workflows:** schedule and orchestrate notebooks, Python scripts, SQL, or supported task types.
- **Databricks SQL:** SQL warehouses, queries, dashboards, and BI tool connectivity.
- **Unity Catalog:** governs catalogs/schemas/tables/volumes, permissions, lineage, and data resource access.
- **Delta Lake:** table format providing transaction logs, ACID guarantees, and reliable DML operations atop object storage.

Feature names and availability evolve across releases and workspace SKUs. "Having a Databricks workspace" does not automatically unlock all compute types or permission to create catalogs.

### 4.2. Control Plane and Compute/Data Plane

Conceptually, Azure Databricks spans:

- **Control plane:** manages workspace services, job scheduling, UI, and service metadata.
- **Compute/data plane:** runs workloads and accesses data using the networking and identity model of the chosen compute/workspace type.
- **Cloud storage:** such as ADLS Gen2 storing landing data, Delta tables, files, and checkpoints.

With classic compute, VMs and resources typically deploy into the Azure environment per workspace setup. With serverless, compute infrastructure is managed by Databricks under a different model. **Do not assume the exact same VNet/Private Link/egress setup applies identically to every compute type.**

### 4.3. When Should You Use Databricks?

Well suited when:

- Processing many GB/TB+ of batch or near-real-time data.
- Using Spark SQL/PySpark and needing distributed compute.
- Building a lakehouse on Delta Lake across multiple pipelines.
- Running multi-tier ingestion and transformations from files and events.
- Unifying data engineering and BI/ML workloads under shared governance.
- Requiring enterprise-scale job orchestration, identity, and lineage.

May be suboptimal when:

- Processing only 200 CSV rows per day.
- Workloads are purely millisecond OLTP queries; Azure SQL Database or PostgreSQL fits better than Spark.
- Needing low-latency Kafka messaging or transactional APIs rather than analytics.
- A small SQL query already runs well in another warehouse or serverless SQL service.
- Lacking a team to operate pipelines, data quality, and compute costs.

**Spark is not an online transactional database replacing Azure SQL or Cosmos DB.** It is a distributed processing and analytics engine that can use Delta tables in a lakehouse architecture.

## 5. Choosing Compute Types and Runtimes

### 5.1. Compute Types by Purpose

| Type | Typical Use | Notes |
|---|---|---|
| Interactive/all-purpose compute | Data exploration, development, interactive notebooks | Easy to leave running; requires auto-termination |
| Jobs compute | Scheduled or triggered pipelines | Typically best for automated workloads with job-scoped lifecycles |
| SQL warehouse | SQL queries, dashboards, BI | Decoupled from PySpark clusters depending on design |
| Serverless compute | Supported workloads with minimal compute management | Verify availability, networking, governance, and pricing |
| Single-node compute when supported | Labs / small workloads | Does not prove distributed scaling |

UI terminology and support vary by release. Never leave interactive compute running 24/7 for a daily 10-minute job when jobs compute meets the need.

### 5.2. Databricks Runtime and Libraries

Before starting a notebook:

1. Identify supported Databricks Runtime, Spark, Python, and Delta versions.
2. Pick an organization-approved runtime, considering LTS for stability.
3. Verify extra libraries and connector/JDBC versions.
4. Never install unvetted packages ad-hoc onto production clusters.
5. Run regression tests before upgrading runtimes.
6. Record the runtime version in job and release metadata.

A notebook running on Runtime A can break on Runtime B due to Python/PySpark API changes, permission updates, or dependency shifts.

### 5.3. Autoscaling and Auto-Termination

- **Autoscaling** adjusts worker counts under service-supported rules.
- **Auto-termination** shuts down interactive compute after a configured idle window.
- **Jobs compute** lives for the duration of a job run, though startup and scaling overhead must be factored in.
- **Serverless** changes both infrastructure management and billing models.

Autoscaling **does not cure shuffle bottlenecks or data skew**, nor can it save a job that repeatedly calls `collect` on huge datasets into the driver.

### 5.4. Cluster Policies and Tags

Production governance should enforce guardrails:

- Restrict node types and maximum workers.
- Block deprecated or unsupported runtime versions.
- Enforce auto-termination on interactive compute.
- Require resource tags such as `env`, `team`, `costCenter`, and `workload`.
- Disallow unapproved instance, storage, or cluster configurations.
- Separate dev/test/prod workspaces and compute creation rights.

Cluster policies enforce governance guardrails, but they do not automatically guarantee optimal queries or proper data access.

## 6. ADLS Gen2 and the Lakehouse Architecture

### 6.1. Decoupling Storage from Compute

~~~mermaid
flowchart LR
    SRC["Sources"] --> LAND["ADLS Gen2 landing / raw"]
    LAND --> BR["Bronze Delta tables"]
    BR --> SI["Silver Delta tables"]
    SI --> GO["Gold Delta tables"]
    GO --> BI["Databricks SQL / BI"]
    GO --> ML["Analytics / ML"]
    UC["Unity Catalog"] -. "Access, metadata, lineage" .-> BR
    UC -. "Access, metadata, lineage" .-> SI
    UC -. "Access, metadata, lineage" .-> GO
~~~

ADLS Gen2 provides object storage with hierarchical namespaces and Azure Storage management features. Spark compute can spin up and shut down independently while Delta data persists durably on storage.

### 6.2. Bronze/Silver/Gold (Medallion)

| Layer | Contents | Requirements |
|---|---|---|
| Bronze | Near-source data with ingestion metadata | Preserves source fidelity, supports schema tracking/quarantine where needed |
| Silver | Cleansed, typed, deduplicated, standardized keys and rules | Reusable across multiple consumers, quality-tested |
| Gold | Business aggregates and data marts | Clear metric definitions, access permissions, and SLAs |

**Bronze does not mean "ignore all errors"**: retain enough provenance to reprocess and trace origins. **Gold is not automatically accurate**: teams must define metrics, timezones, data contracts, and late-event handling.

### 6.3. Unity Catalog Managed and External Storage

Unity Catalog can manage **managed tables/volumes** in managed storage or govern access to properly configured **external locations**. Do not build entire new pipelines around un-governed, hard-coded mounts or keys.

Key concepts:

- **Catalog:** top-level data namespace.
- **Schema:** grouping of tables, views, and volumes.
- **Table:** structured data governed by `SELECT`/`MODIFY` privileges.
- **Volume:** non-tabular file path managed in Unity Catalog.
- **Storage credential:** managed mechanism for authenticating to cloud storage.
- **External location:** cloud storage path bound to a credential and permissions.
- **Lineage:** source/target relationships captured across supported operations.

Configuring storage credentials, external locations, and access connectors normally requires appropriate Azure and Unity Catalog privileges; never assume notebook users can create them by default.

### 6.4. Handle Storage Paths Carefully

Example Unity Catalog volume path:

~~~text
/Volumes/<catalog>/<schema>/<volume>/landing/orders/
~~~

This is a placeholder, not a live resource. Production jobs should load paths and table names from controlled environment configs. Never embed access keys, SAS tokens, or client secrets inside path strings.

## 7. Spark DataFrames: Core APIs

### 7.1. Creating a SparkSession and Reading Data

In a Databricks notebook attached to Spark compute, the **`spark`** object is normally pre-initialized.

~~~python
from pyspark.sql import functions as F

# In a Databricks notebook, SparkSession `spark` is already available.
rows = [
    ("o-001", "tenant-a", 2, 125.50),
    ("o-002", "tenant-a", 1, 90.00),
    ("o-003", "tenant-b", 3, 49.90),
]

df = spark.createDataFrame(
    rows,
    ["order_id", "tenant_id", "quantity", "unit_price"]
)

df.printSchema()
df.show(truncate=False)
~~~

`spark.createDataFrame` is convenient for small lab datasets. When reading production data, read directly from distributed sources like ADLS Gen2 or Delta tables rather than passing millions of Python objects through the driver.

### 7.2. Select, Filter, and `withColumn`

~~~python
clean = (
    df.filter(F.col("quantity") > 0)
      .withColumn("line_total", F.col("quantity") * F.col("unit_price"))
      .select("order_id", "tenant_id", "line_total")
)

clean.show()
~~~

For financial data, use **`DecimalType`** instead of floats whenever exact currency precision is needed. The `125.50` float literal here merely illustrates the API, not production data-type design.

### 7.3. GroupBy and Aggregate

~~~python
summary = (
    clean.groupBy("tenant_id")
         .agg(
             F.count("*").alias("order_count"),
             F.sum("line_total").alias("gross_total")
         )
)

summary.show()
~~~

Executing a `groupBy` in Spark can trigger a shuffle by `tenant_id`. Watch partition counts and skew if one tenant dominates data volume.

### 7.4. Join

~~~python
tenants = spark.createDataFrame(
    [("tenant-a", "North"), ("tenant-b", "South")],
    ["tenant_id", "region"]
)

result = summary.join(tenants, on="tenant_id", how="left")
result.show()
~~~

When the tenant mapping table is genuinely small, the Spark optimizer can pick a broadcast join. Never broadcast a table just because it has few rows if each row carries a massive payload.

### 7.5. DataFrames Are Immutable Transformations

DataFrame operations return a **new DataFrame**; running:

~~~python
df.filter(F.col("quantity") > 0)
~~~

does not mutate `df` in place. To keep the filtered result, assign it:

~~~python
df = df.filter(F.col("quantity") > 0)
~~~

Clear pipelines use distinct variables like **`raw`, `validated`, `silver`, and `gold`** rather than reassigning `df` repeatedly, making lineage easy to review.


## 8. Self-Contained PySpark Practice: Cleansing Orders

### 8.1. Data and Rules

We create synthetic data inline in the notebook so no storage permissions are needed. The goal is processing six rows, including two invalid rows and one order with two versions. Business rules:

- `quantity` must be a positive integer.
- `unit_price` must be a non-negative `DECIMAL`.
- `event_time` must be a valid UTC timestamp.
- `status` must be in `paid`, `pending`, or `canceled`.
- Within the same tenant, keep the latest `source_version` per `order_id`.
- Gold computes total gross value for `paid` orders by tenant and date.

### 8.2. Generating Bronze Data

~~~python
from pyspark.sql import functions as F
from pyspark.sql import Window

spark.conf.set("spark.sql.session.timeZone", "UTC")

rows = [
    ("o-001", "tenant-a", "c-01", "2026-11-18T08:00:00Z",
     "2", "125.50", "paid", 1),
    ("o-002", "tenant-a", "c-02", "2026-11-18T08:05:00Z",
     "1", "90.00", "pending", 1),
    ("o-001", "tenant-a", "c-01", "2026-11-18T08:10:00Z",
     "2", "125.50", "paid", 2),
    ("o-003", "tenant-b", "c-03", "2026-11-19T11:30:00Z",
     "3", "49.90", "paid", 1),
    ("o-004", "tenant-b", "c-04", "2026-11-19T12:00:00Z",
     "-1", "24.50", "paid", 1),
    ("o-005", "tenant-b", "c-05", "2026-11-19T12:30:00Z",
     "1", "invalid", "paid", 1),
]

schema = """
order_id STRING,
tenant_id STRING,
customer_id STRING,
event_time_text STRING,
quantity_text STRING,
unit_price_text STRING,
status STRING,
source_version INT
"""

bronze = (
    spark.createDataFrame(rows, schema=schema)
         .withColumn("_ingested_at", F.current_timestamp())
)
bronze.show(truncate=False)
~~~

Production Bronze tables should also carry source file, source event ID, ingestion batch, and schema version. This DataFrame is merely an illustrative dataset, not a persisted Delta table.

### 8.3. Standardizing Data Types

~~~python
typed = (
    bronze
    .withColumn(
        "event_time",
        F.to_timestamp("event_time_text", "yyyy-MM-dd'T'HH:mm:ssX")
    )
    .withColumn(
        "quantity", F.expr("try_cast(quantity_text as int)")
    )
    .withColumn(
        "unit_price",
        F.expr("try_cast(unit_price_text as decimal(18,2))")
    )
)
typed.select(
    "order_id", "event_time", "quantity",
    "unit_price", "status"
).show(truncate=False)
~~~

`try_cast` in Databricks SQL returns `null` when casting fails, allowing malformed rows to be routed to quarantine. Functions and timestamp formats can vary across Runtime/Spark versions; this example intentionally uses valid ISO strings. For malformed source timestamps, add a controlled parsing branch.

**Monetary amounts require `DECIMAL` with explicit precision/scale, currency, and rounding rules**—never use arbitrary floats in financial reporting.

### 8.4. Routing Valid vs. Quarantine

~~~python
condition = (
    F.col("order_id").isNotNull()
    & F.col("tenant_id").isNotNull()
    & F.col("customer_id").isNotNull()
    & F.col("event_time").isNotNull()
    & (F.col("quantity") > 0)
    & (F.col("unit_price") >= 0)
    & F.col("status").isin("paid", "pending", "canceled")
)
is_valid = F.coalesce(condition, F.lit(False))

valid = typed.filter(is_valid)
quarantine = typed.filter(~is_valid)

print("Valid rows:", valid.count())
print("Rejected rows:", quarantine.count())
~~~

Expected result: **4 valid**, **2 rejected** (`o-004` has negative quantity, `o-005` has an unparseable `unit_price`). `coalesce` ensures any `null` condition evaluates to `False` instead of letting SQL three-valued logic with `NOT` silently drop null rows from quarantine.

In production, quarantine should record source metadata, error codes, timestamps, owners, and replay schedules; never drop malformed records and report pipeline success without alerting.

### 8.5. Deduplicating by `source_version`

~~~python
w = (
    Window.partitionBy("tenant_id", "order_id")
          .orderBy(
              F.col("source_version").desc(),
              F.col("event_time").desc()
          )
)

silver = (
    valid
    .withColumn("_row_num", F.row_number().over(w))
    .filter(F.col("_row_num") == 1)
    .select(
        "tenant_id", "order_id", "customer_id",
        "event_time", "quantity", "unit_price",
        "status", "source_version"
    )
)

silver.orderBy("tenant_id", "order_id").show(truncate=False)
~~~

Expected result: **3 Silver rows**: the latest `o-001`, plus `o-002` and `o-003`.

This is a lab rule. In production, if both `source_version` and `event_time` tie, add a deterministic tie-breaker such as a source event ID or sequence number. Using `dropDuplicates` that picks an arbitrary row is insufficient for semantically meaningful updates.

### 8.6. Gold Aggregation for Paid Orders

~~~python
paid = silver.filter(F.col("status") == "paid")

gold = (
    paid
    .withColumn("order_date", F.to_date("event_time"))
    .groupBy("tenant_id", "order_date")
    .agg(
        F.countDistinct("order_id").alias("paid_orders"),
        F.sum(
            F.col("quantity") * F.col("unit_price")
        ).alias("gross_value")
    )
)

gold.orderBy("tenant_id", "order_date").show(truncate=False)
~~~

Expected output:

| tenant_id | order_date (UTC) | paid_orders | gross_value |
|---|---|---:|---:|
| tenant-a | 2026-11-18 | 1 | 251.00 |
| tenant-b | 2026-11-19 | 1 | 149.70 |

This computes only **gross `quantity × unit_price`** for paid orders, before taxes, refunds, and discounts. If business requires daily reporting in Vietnam time or another region, convert timezones per requirements before grouping by date; this example uses UTC.

### 8.7. Row-Count Assertions

~~~python
assert bronze.count() == 6
assert quarantine.count() == 2
assert silver.count() == 3
assert gold.count() == 2

assert (
    silver.filter(
        (F.col("tenant_id") == "tenant-a")
        & (F.col("order_id") == "o-001")
        & (F.col("source_version") == 2)
    ).count()
) == 1
~~~

`count` calls are **actions** that re-trigger Spark jobs. In production, avoid calling full-table `count()` repeatedly just for debugging; prefer pipeline-integrated metrics, expectations, or sampling.

### 8.8. Lab Limitations

The dataset is tiny; it does not test concurrency, skew, storage permissions, checkpoints, late events, or MERGE. Production requires idempotent ingestion, schema validation, source metadata, permission tests, and orchestration.

## 9. Delta Lake: Transactions on Object Storage

### 9.1. Why Not Just Use a Parquet Folder?

Parquet is a valuable columnar format, yet a plain directory of Parquet files lacks multi-file `UPDATE`/`DELETE` transactions and consistent table versioning.

**Delta Lake** pairs data files (typically Parquet) with a transaction log to support:

- ACID transactions for supported operations.
- Schema enforcement on write.
- Controlled schema evolution.
- `UPDATE`/`DELETE`/`MERGE`.
- Time travel across retained snapshots.
- Batch and Structured Streaming on Delta tables.
- File optimization and layout features per Databricks Runtime capabilities.

~~~mermaid
flowchart TD
    T["Delta table"] --> D["Data files"]
    T --> L["_delta_log"]
    L --> V1["Version 1"]
    L --> V2["Version 2"]
    L --> V3["Version 3"]
    V3 --> Q["Consistent snapshot for readers"]
~~~

Delta table ACID guarantees do not automatically enforce a business-level unique constraint on `(tenant_id, order_id)`. If unchecked source duplicates slip through, wrong business data can still be written.

### 9.2. Writing a Table in an Authorized Lab

Assuming Unity Catalog has a **lab catalog and schema**, the caller holds create-table rights, and the target table does not yet exist:

~~~python
target_table = "training_catalog.sandbox.orders_silver_lab"

(
    silver.write
          .format("delta")
          .mode("errorifexists")
          .saveAsTable(target_table)
)
~~~

`errorifexists` intentionally refuses to write if the table already exists. Never run `overwrite` on production tables or execute writes against resources you do not own. `training_catalog.sandbox` is illustrative; replace it with an authorized catalog/schema.

### 9.3. Reading Back with PySpark and SQL

~~~python
saved = spark.table("training_catalog.sandbox.orders_silver_lab")
saved.printSchema()
saved.show(truncate=False)
~~~

~~~sql
SELECT tenant_id, COUNT(*) AS orders_count
FROM training_catalog.sandbox.orders_silver_lab
GROUP BY tenant_id
ORDER BY tenant_id;
~~~

### 9.4. `MERGE` for Incremental Upsert

Assuming the staging table is already **deduplicated by `(tenant_id, order_id)`**:

~~~sql
MERGE INTO training_catalog.sandbox.orders_silver_lab AS t
USING training_catalog.sandbox.orders_stage_lab AS s
ON t.tenant_id = s.tenant_id
   AND t.order_id = s.order_id
WHEN MATCHED AND s.source_version > t.source_version
THEN UPDATE SET
    t.customer_id = s.customer_id,
    t.event_time = s.event_time,
    t.quantity = s.quantity,
    t.unit_price = s.unit_price,
    t.status = s.status,
    t.source_version = s.source_version
WHEN NOT MATCHED THEN INSERT (
    tenant_id, order_id, customer_id, event_time,
    quantity, unit_price, status, source_version
)
VALUES (
    s.tenant_id, s.order_id, s.customer_id, s.event_time,
    s.quantity, s.unit_price, s.status, s.source_version
);
~~~

This example assumes the stage table already exists. Delete events, late data, source duplicates, or transaction conflicts require explicit handling. In production, re-running a batch must be idempotent; duplicate keys in the source can cause `MERGE` to fail or produce wrong semantics.

### 9.5. Time Travel, Retention, and `VACUUM`

~~~sql
DESCRIBE HISTORY training_catalog.sandbox.orders_silver_lab;

-- Run only when version 2 actually still exists on the table:
SELECT *
FROM training_catalog.sandbox.orders_silver_lab VERSION AS OF 2;
~~~

For time travel to work, logs and referenced data files must remain within retention. **`VACUUM`** deletes unreferenced files and renders older history unreadable. Never lower retention excessively just to save storage when streaming readers, rollbacks, long-running jobs, or compliance depend on it. Verify retention safety before cleanup.

### 9.6. Schema Evolution Is a Governance Decision

When a source adds fields or changes types:

1. Determine whether it is a breaking or non-breaking change.
2. Update source and target data contracts.
3. Evaluate whether backfills are needed.
4. Check downstream tables, views, and BI reports.
5. Maintain version logs, commits, and tests.
6. Enable schema auto-merge only under governed policies.

Never auto-accept every arbitrary column change into sensitive Gold tables and call it schema resilience.

## 10. Medallion Architecture: Bronze, Silver, Gold

### 10.1. Bronze: Preserving Source Data with Evidence

Bronze should keep raw payloads or near-source schemas alongside metadata:

- Event/file ID, source name, UTC ingestion timestamp.
- Schema version, source partition/offset if applicable.
- Tenant and data classification.
- Error fields or rescued data per supported features.
- Retention long enough to replay when Silver pipelines fail.

If a source emits bad types, you still need to trace which source caused the issue and remediate; never silently drop rows upfront.

### 10.2. Silver: Rule-Based Cleansing

Silver typically handles:

- Parsing and casting data types.
- Checking nulls, amounts, statuses, and domains.
- Timezone, currency, and code normalization.
- Deduplication by business key/source version.
- Upserts for late-arriving changes.
- Enrichment/joins across sources.
- Data quality metrics and quarantine.

Every rule needs an owner and tests; naming a layer "Silver" does not guarantee data accuracy.

### 10.3. Gold: Clear Metrics and Grain

A Gold aggregate should be documented:

~~~text
Metric: paid_gross_value
Grain: tenant_id + calendar_date (UTC)
Source: silver.orders
Filter: latest source_version, status = paid
Formula: sum(quantity * unit_price)
Excludes: tax, refund, discount in this lab
Business owner: Commerce Analytics
Freshness target: before 07:00 UTC daily (example)
~~~

If Business requires dates in Vietnam time or another region, do not blindly group by UTC dates across all tenants.

### 10.4. Table Governance

Every Delta table should have:
- Owner and steward.
- Catalog/schema and data permissions.
- Schema, contract version, and lineage.
- Freshness and quality bars.
- Retention and backup/recovery plans.
- Storage layout and performance policies.
- Cost budgets and incident responders.

Only then is a table a true data product serving users, rather than just a folder full of files.


## 11. Batch Reading from ADLS Gen2

### 11.1. Prefer Governed Storage Paths

In a workspace configured with **Unity Catalog volumes** and appropriate permissions:

~~~python
source_path = (
    "/Volumes/<catalog>/<schema>/<volume>/landing/orders/"
)

df_batch = (
    spark.read
         .format("json")
         .load(source_path)
)

df_batch.printSchema()
~~~

The path above is a placeholder, not a pre-existing lab file. Use catalogs/schemas/volumes authorized by your Data Platform team; never store SAS tokens or account keys in notebook code.

### 11.2. CSV with Explicit Schema

~~~python
from pyspark.sql.types import (
    StructType, StructField,
    StringType, IntegerType, DecimalType
)

product_schema = StructType([
    StructField("sku", StringType(), False),
    StructField("quantity", IntegerType(), True),
    StructField("unit_price", DecimalType(18, 2), True)
])

products = (
    spark.read
         .format("csv")
         .option("header", "true")
         .schema(product_schema)
         .load(
             "/Volumes/<catalog>/<schema>/<volume>/landing/products/"
         )
)
~~~

Never rely on **`inferSchema`** for important data contracts; inferred types, nullability, encoding, and headers can shift whenever upstream emits new files.

### 11.3. Why Re-Reading an Entire Folder Daily Causes Problems

Suppose a folder accumulates 100,000 files per day. If a batch job re-reads everything every time:

- Storage listing and network requests explode.
- Compute/RU costs rise on metering sources.
- Append targets risk duplicates.
- History gets reprocessed uncontrollably.
- Small-file overhead worsens.
- Pinpointing truly new records after an incident becomes hard.

Use ingestion manifests, source metadata, or **Auto Loader** to ingest incrementally and track progress.

## 12. Auto Loader: File-Based Incremental Ingestion

### 12.1. What Is Auto Loader?

Databricks **Auto Loader** uses the **`cloudFiles`** source to detect new files in cloud storage and feed them into a Structured Streaming pipeline. It maintains a schema location and checkpoint to track processed inputs.

~~~mermaid
flowchart LR
    F["ADLS Gen2 files"] --> A["Auto Loader cloudFiles"]
    A --> C["Checkpoint / Schema state"]
    A --> B["Bronze Delta table"]
    B --> S["Silver cleaning"]
~~~

Auto Loader supports file discovery modes such as directory listing or file-event/notification-based discovery per supported configuration. Verify feature prerequisites and Azure Storage permissions; never assume every workspace automatically provisions managed file events.

### 12.2. Example Reading New JSON Files

Assuming a Unity Catalog volume permits reading landing and writing schemas/checkpoints:

~~~python
landing = (
    "/Volumes/<catalog>/<schema>/<volume>/landing/orders/"
)
schema_location = (
    "/Volumes/<catalog>/<schema>/<volume>/schemas/orders/"
)
checkpoint = (
    "/Volumes/<catalog>/<schema>/<volume>/checkpoints/orders_bronze/"
)

bronze_stream = (
    spark.readStream
         .format("cloudFiles")
         .option("cloudFiles.format", "json")
         .option("cloudFiles.schemaLocation", schema_location)
         .load(landing)
)

query = (
    bronze_stream.writeStream
                 .format("delta")
                 .option("checkpointLocation", checkpoint)
                 .trigger(availableNow=True)
                 .toTable(
                     "<catalog>.<schema>.orders_bronze"
                 )
)

query.awaitTermination()
~~~

Prerequisites:
1. Compute/runtime supports Auto Loader and Structured Streaming.
2. Volume paths and read/write permissions are configured.
3. Checkpoint and `schemaLocation` paths are durable.
4. Target table permissions permit creation/writes.
5. Catalog/schema/volume placeholders are replaced with real names.
6. No other query shares an incompatible checkpoint.

**`availableNow=True`** processes all currently available files across one or more micro-batches and then stops cleanly per supported semantics; it is not an always-on 24/7 stream.

### 12.3. Checkpoints Are Not Logging

Checkpoints are used by Spark to recover offsets, state, and sink progress. Deleting a checkpoint and restarting can:

- Re-ingest already processed files.
- Duplicate records in append targets.
- Cause unexpected behavior if schemas or locations changed.
- Break idempotency assumptions and recovery guarantees.

Never share one checkpoint across two pipelines or delete checkpoints casually to "fix" streaming errors. When changing sources, schemas, query semantics, or targets, review compatibility and migration plans.

### 12.4. Schema Drift and Rescued Data

When new files add columns or alter types:

- The pipeline can evolve the schema per configuration.
- It can halt for manual intervention.
- It can capture mismatched data into a rescued data column per supported capabilities.
- It can fail if the target Delta schema rejects the change.

Never allow arbitrary schema changes to cascade unchecked through Bronze, Silver, and Gold when they impact revenue metrics, privacy, or backward compatibility.

## 13. Structured Streaming and Event-Time Processing

### 13.1. Batch vs. Streaming

**Batch** reads a bounded dataset and terminates. **Structured Streaming** processes arriving data incrementally via triggers, source offsets, checkpoints, and sink semantics.

~~~mermaid
sequenceDiagram
    participant S as Source
    participant Q as Streaming Query
    participant C as Checkpoint
    participant D as Delta table
    S->>Q: Micro-batch input
    Q->>C: Read progress and state
    Q->>D: Write output batch
    Q->>C: Advance checkpoint
    S->>Q: Next input
~~~

- **Micro-batch:** group of records executed in one logical batch.
- **Checkpoint:** stores stream progress and state.
- **Trigger:** determines when new data is processed.
- **Watermark:** bounds state retention for event-time computations.
- **Sink:** a Delta table or another supported destination.

Not all sinks share the same transaction semantics. Writing to Delta with a valid checkpoint differs fundamentally from issuing arbitrary HTTP/JDBC calls inside **`foreachBatch`**.

### 13.2. Event Time Differs from Processing Time

Example:

~~~text
Event A occurred 10:00, arrived 10:01
Event B occurred 09:55, arrived 10:20
~~~

Grouping solely by when Spark received the event places Event B into the wrong bucket. Define explicitly:

- Source-supplied event time.
- Lake ingestion time.
- Spark processing time.
- Late-event policy.
- Standardized timezone and calendar-date logic.

### 13.3. Watermarks and Windows

Suppose a streaming DataFrame **`events`** has `event_time TIMESTAMP` and `tenant_id STRING`:

~~~python
from pyspark.sql import functions as F

windowed = (
    events
    .withWatermark("event_time", "15 minutes")
    .groupBy(
        F.window("event_time", "5 minutes"),
        F.col("tenant_id")
    )
    .count()
)
~~~

This is only a streaming transformation without a sink or checkpoint. Watermarks bound state and govern late-data handling per output mode. Events arriving past the watermark may be dropped. Never pick 15 minutes if source events routinely arrive 3 days late.

### 13.4. Understanding the Scope of Exactly-Once

Structured Streaming and Delta provide recovery and transactional guarantees for supported sources and sinks. However:

- Sources can replay events.
- Business event IDs can repeat.
- Spark jobs can retry tasks.
- External HTTP APIs or JDBC sinks are not inherently idempotent.
- Pipelines can re-read inputs if checkpoints are deleted.
- `MERGE` requires proper keys and staged deduplication.

Inside **`foreachBatch`**, pair `batchId` with appropriate transactions/idempotency keys to avoid duplicate side effects. Never claim end-to-end exactly-once without verifying every stage.

### 13.5. Stateful Streaming Requires Watching State Size

Windowed aggregations and streaming joins hold state keyed by watermark/keys. If watermarks are too wide, key cardinality is huge, or late events grow unbounded, state balloons and micro-batches slow down.

Monitor:
- Input rows/second.
- Processed rows/second.
- Batch duration.
- State store memory/rows.
- Watermark progress.
- Backlog/source lag.
- Shuffle/spill/errors.
- Checkpoint health.

If the business only needs hourly file processing, triggered batch / `availableNow` can be simpler and cheaper than running a continuous stream.

## 14. Unity Catalog: Governance, Permissions, and Lineage

### 14.1. Object Hierarchy

~~~mermaid
flowchart TD
    M["Unity Catalog metastore / governance"] --> C["Catalog: analytics"]
    C --> S1["Schema: bronze"]
    C --> S2["Schema: silver"]
    C --> S3["Schema: gold"]
    S1 --> T1["Delta tables"]
    S2 --> T2["Delta tables"]
    S3 --> T3["Tables, views, BI"]
    C --> V["Volumes / external locations"]
~~~

Catalogs, schemas, tables, and volumes each have owners, privileges, and lifecycles. Workspaces are attached to governance scopes per organizational setup; never assume every workspace automatically accesses every catalog.

### 14.2. Unity Catalog and Azure Identity

With ADLS Gen2, an organization can use an **Azure Databricks access connector** and managed identity to configure storage credentials, external locations, or managed storage per Unity Catalog capabilities. Requirements:

1. Azure identity holds proper RBAC/ACLs on Storage.
2. External locations/volumes are registered in Unity Catalog.
3. Unity Catalog privileges are granted to users/service principals/workloads.
4. Network/DNS and private endpoint paths are valid.
5. Zero account keys or SAS tokens exposed in notebooks.
6. Data owners and stewards assigned.

**Azure Storage Blob Data Contributor** on storage does not automatically grant `SELECT` on a Unity Catalog table. Conversely, `GRANT SELECT` in UC fails if underlying storage credentials or networking are misconfigured.

### 14.3. Illustrative SQL Privileges

Databricks SQL example on existing objects (without creating new ones):

~~~sql
GRANT USE CATALOG
ON CATALOG analytics
TO data_analyst_group;

GRANT USE SCHEMA
ON SCHEMA analytics.gold
TO data_analyst_group;

GRANT SELECT
ON TABLE analytics.gold.daily_orders
TO data_analyst_group;
~~~

Principal and table names are illustrative. Granting requires appropriate privileges, and privileges may inherit per configuration. For sensitive data, use views, row filters, or column masks where supported to enforce PII and tenant boundaries.

### 14.4. Least Privilege

| Role | Recommended Permissions | Do Not Grant by Default |
|---|---|---|
| Bronze data engineer | Read sources, write assigned Bronze tables | All production catalogs |
| Silver transform job | `SELECT` Bronze, `MODIFY` Silver | Account admin, all storage keys |
| BI analyst | `SELECT` approved Gold/views | Read raw PII or write Bronze |
| Security auditor | Metadata/logs as required | Arbitrary data edits/deletions |
| CI/CD service principal | Deploy jobs/tables in scope | Subscription-wide Owner |
| Platform admin | Compute/network/governance administration | Using admin identity as pipeline runtime |

Never conflate workspace membership, compute access, SQL privileges, and Azure RBAC: they are **distinct permission planes**.

### 14.5. Lineage and Data Discovery

Lineage helps answer:
- Which Silver/Bronze tables feed a Gold report?
- Which notebook/job produced the data?
- Where did a revenue column originate and how was it transformed?
- Who owns downstream impacts when a schema changes?

Lineage completeness depends on supported activities, jobs, and queries being captured. Never treat lineage as proof that zero unmonitored external access exists if unmanaged tools or pipelines still touch storage.

## 15. Networking, Secrets, and Workspace Security

### 15.1. Connecting to Azure Securely

~~~mermaid
flowchart LR
    APP["Databricks workload"] --> DNS["DNS / VNet routing"]
    DNS --> ADLS["ADLS Gen2 private or approved endpoint"]
    APP --> UC["Unity Catalog authorization"]
    UC --> ID["Managed identity / storage credential"]
    ID --> ADLS
    APP --> LOG["Logs / Monitoring"]
~~~

A private-data architecture may require:

- Workspace/compute networking aligned with the deployment model.
- Private Endpoints to ADLS, Key Vault, and other services where appropriate.
- Operational Private DNS Zones and resolvers.
- Network Security Groups/routes/firewalls protecting traffic flows.
- Egress controls and approved package repositories.
- Connectivity to Microsoft Entra token endpoints when required by identity flows.

**Classic compute and serverless compute can have different networking requirements**; never apply a single subnet diagram blindly across all features.

### 15.2. Secrets and Sensitive Information

- Never hard-code client secrets, storage account keys, or SAS tokens in notebooks.
- Prefer Microsoft Entra authentication, service principal federation, or managed identities wherever possible.
- For unavoidable secrets, use organization-approved secret management (Key Vault integration / Databricks secrets).
- Never print tokens via `print`, `display`, or logs.
- Never place production PII into demo notebooks or shared tables.
- Govern `SELECT`/`READ VOLUME` permissions and data retention.
- Separate runtime identities from pipeline deployment identities.

**A secret scope is not a tenant-level data firewall.** An identity with overly broad storage permissions can still access unintended data if policies are misconfigured.

### 15.3. Encryption, Compliance, and Personal Data

Verify:
- Encryption at rest and in transit.
- Customer-managed keys when required by compliance and supported.
- Audit logs, access logs, and retention.
- Data residency across workspace, storage, replicas, and logs.
- Row/column access controls or views.
- Token/credential rotation and break-glass access.
- Backup/restore and deletion policies.

**Running `VACUUM` on a Delta table does not prove every copy of data was erased from cloud backups or downstream BI extracts.** Establish an end-to-end data lifecycle and legal-hold plan where applicable.


## 16. Spark Performance Tuning

### 16.1. Find the Root Cause Before Adding Workers

A job may run slowly because:

- Inputs consist of huge numbers of tiny files.
- Massive shuffles in `groupBy`/`join`/`orderBy`.
- Data skew: one key holds most records.
- Python UDFs inhibit expression optimization.
- Over-caching puts pressure on executor memory.
- Driver `collect` pulls too much data.
- Executor memory spill or out-of-memory errors.
- Queries scan too many columns or partitions.
- Missing data skipping or suboptimal file layout.
- A single huge task leaves extra workers idle.
- Multiple jobs contend on shared compute or warehouses.

Increasing cluster size is not an automatic cure; Spark UI and query plans usually reveal the real bottleneck.

### 16.2. Reading Execution Plans

~~~python
gold.explain("formatted")
~~~

Inspect:

- `Exchange`: where is data shuffled?
- `Scan`: which files and columns are read?
- Are filter pushdown and partition pruning active?
- Are broadcast joins used appropriately?
- `SortAggregate`/`HashAggregate` and partition counts.
- Adaptive query execution adjustments.
- Are specific operators consuming unexpected CPU/IO?

Correlate execution plans with Spark UI stages, tasks, shuffle read/write, skew, and spill metrics.

### 16.3. Number of Partitions

Too many tiny partitions inflate scheduler overhead; too few large partitions starve parallelism and trigger memory pressure or long tails. Common operations:

~~~python
# Repartition when there is a clear reason to redistribute data.
balanced = source_df.repartition(32)

# Coalesce typically reduces partition count without a full shuffle
# in scenarios supported by Spark.
smaller = balanced.coalesce(8)
~~~

The numbers 32 and 8 are purely illustrative. Never hard-code fixed counts across all data sizes, cluster sizes, and file layouts.

**`repartition(32, "tenant_id")` does not fix skew if 80% of records share one `tenant_id`**: identical keys hash to the exact same partition. You may need composite keys, salting, AQE, or two-stage aggregation.

### 16.4. Broadcast Joins

When a dimension table is small and safe to replicate to executors:

~~~python
from pyspark.sql import functions as F

joined = facts.join(
    F.broadcast(dimensions),
    on="product_id",
    how="left"
)
~~~

Broadcasting avoids shuffling the large fact table, but always verify memory footprint. Never broadcast a "few-row" table whose rows hold huge payloads; executors will OOM if it exceeds RAM.

### 16.5. Adaptive Query Execution (AQE)

**Adaptive Query Execution** lets Spark adjust certain query-plan decisions using runtime statistics, such as coalescing shuffle partitions or mitigating skew in supported operators.

Inspect actual runtime configuration and behavior:

~~~python
spark.conf.get("spark.sql.adaptive.enabled")
~~~

Do not copy-paste dozens of `spark.sql.*` settings from old blog posts without benchmarking on your Databricks Runtime; defaults and optimizations evolve.

### 16.6. Built-In Functions Usually Beat Python UDFs

For example, prefer:

~~~python
# Avoid Python UDFs whenever logic can be expressed with
# Spark SQL built-in functions.
normalized = df.withColumn(
    "normalized_email",
    F.lower(F.trim(F.col("email")))
)
~~~

If business logic demands complex Unicode or locale-specific case folding, verify semantics and test carefully; for performance, reach for Spark built-ins before Python UDFs due to serialization overhead and optimizer opacity.

### 16.7. Cache Only on Genuine Reuse

~~~python
reused = source_df.filter(F.col("status") == "paid").cache()

# Action materializes the cache.
reused.count()

# Two downstream operations share `reused`.
a = reused.groupBy("tenant_id").count()
b = reused.groupBy("customer_id").count()

# When finished:
reused.unpersist()
~~~

Caching is not a default speedup. It consumes memory/disk and can trigger evictions or spills if larger than capacity. Never cache a DataFrame used only once.

### 16.8. Small Files and Delta Optimization

Appending tens of thousands of micro-batches or high-task writes creates many tiny Delta data files:

- Listing and metadata overhead.
- High task startup counts.
- Elevated query latency.
- Higher storage transaction and compute costs.

Use compaction/`OPTIMIZE` and supported auto-optimization features:

~~~sql
-- Run only on authorized lab tables with an actual need.
OPTIMIZE training_catalog.sandbox.orders_silver_lab;
~~~

Do not run `OPTIMIZE` on every table after every micro-batch. Schedule frequency around file sizes, query patterns, and cost. Techniques like **Z-ORDER** or **liquid clustering** have specific prerequisites and trade-offs; never mix layout strategies without checking the feature matrix.

### 16.9. Delta Table Partitioning Differs from Spark Partitions

- **Spark partitions:** units of in-job parallel execution.
- **Delta table partitioning:** how table/data files are physically grouped on storage by chosen partition columns.
- **Unity Catalog schema:** metadata namespace.
- **Cosmos DB partition key:** data distribution mechanism of a separate database service.

Partitioning a Delta table by high-cardinality `customer_id` creates massive numbers of tiny folders and files. When partitioning by date, evaluate daily data volume, access patterns, and pruning. **Never `partitionBy` arbitrary columns.**

## 17. Costing Azure Databricks

### 17.1. Primary Cost Components

A total cost estimate must consider:

~~~text
Total data platform cost =
    Azure Databricks usage (DBUs / workload billing model)
  + Azure infrastructure compute where applicable
  + ADLS Gen2 data storage and transactions
  + Network egress / private connectivity
  + SQL warehouse usage
  + Job retry/reprocessing and orchestration overhead
  + Monitoring / Log Analytics ingestion and retention
  + Other dependent services (Event Hubs, Key Vault, etc.)
~~~

A **DBU (Databricks Unit)** is the billing unit in Databricks pricing models, though rates and billing mechanics vary by tier, workload, serverless vs. classic compute, and contract. Classic compute may also incur separate Azure VM/infrastructure charges. Never apply a single flat DBU price across every workload.

### 17.2. Matching Compute to Workload

| Need | Initial Option to Evaluate | Watch Out For |
|---|---|---|
| Single data engineer doing light exploration | Interactive compute with auto-termination | Leaving idle overnight |
| Nightly ETL | Jobs compute | Startup overhead and runtime |
| Always-on streaming | Compute suited to continuous streaming | SLAs/backpressure and 24/7 cost |
| SQL dashboards | SQL warehouse | Auto-stop, concurrency, and pricing |
| Hourly file ingestion | `availableNow` job | Easier cost control when data is sparse |
| Small-data POC | Smaller compute or lighter tool | Databricks may be overkill |

### 17.3. Illustrative Compute Cost Example

Suppose a pipeline runs 20 minutes every hour:

~~~text
Total processing time/day:
  24 × 20 minutes = 480 minutes = 8 hours.

If compute stays up 24 hours:
  you may pay for significant idle time depending on the model.

If jobs compute terminates after each run:
  you pay for active usage/capacity plus startup overhead.
~~~

This is not a real price sheet. Compare **DBUs + compute/infrastructure + storage/network/logging**, and evaluate serverless billing against classic compute. Spawning tiny jobs too frequently can cost more than longer-running jobs if startup overhead dominates.

### 17.4. Cost-Saving Levers

- Auto-termination on interactive compute.
- Jobs compute for scheduled pipelines.
- Right-size drivers and workers using Spark UI.
- Cut redundant historical scans via incremental ingestion.
- Apply Delta file optimization where beneficial.
- Avoid `collect`/`toPandas` on large datasets.
- Minimize unnecessary shuffles and Python UDFs.
- Cap infinite retries, excessive concurrency, and runaway job timeouts.
- Monitor network egress, log volume, and storage retention.
- Enforce tags and cost attribution by team, environment, and job.
- Leverage commitment/pricing tiers if eligible.

Never cut costs by disabling audits, slashing recovery retention, or weakening network security without approval.

### 17.5. Monitoring Cost per Workload

Every pipeline should log:
- Job ID and release version.
- Input file/row counts and bytes.
- Duration, compute type, and worker count.
- Output rows/bytes and partition/file counts.
- Retries, failures, and root causes.
- Cost attribution/usage tags.
- Resource budget and notification owner.

Comparing **cost per million rows processed** across pipeline releases spots regressions, provided data quality, accuracy, and SLAs remain constant.

## 18. Databricks Jobs/Workflows: Pipeline Orchestration

### 18.1. Dependency Graph

~~~mermaid
flowchart TD
    I["Ingest orders"] --> Q["Validate schema / quarantine"]
    Q --> S["Silver merge"]
    S --> G["Gold aggregate"]
    G --> T["Data quality / reconciliation"]
    T --> P["Publish / notify"]
    Q --> F["Alert data owner on failure"]
    S --> F
    G --> F
~~~

A workflow defines tasks, dependencies, compute settings, parameters, schedules/triggers, retries, and notifications. Databricks supports various task types by product release; never assume every task type exists in all workspaces.

### 18.2. Jobs Must Be Idempotent

If the Silver merge task succeeds and the Gold task fails, the workflow retries. Rerunning must not blindly re-append Silver and duplicate records.

Strategies:

- Merge by business keys and source versions.
- Track ingestion batch IDs and processed sources.
- Use Delta transactions and checkpoints properly.
- Define clean commit boundaries.
- Quarantine bad records and retry selectively.
- Log `runId` and send alerts with correlation IDs.
- Test rerunning identical inputs to confirm identical business outputs.

**Retries** only help recover from transient failures when side effects are safely idempotent.

### 18.3. Separating Development Notebooks from Production Jobs

During development, notebooks often:
- Sample small subsets for exploration.
- Call `display`, `show`, and `explain`.
- Run cells manually out of order.
- Hard-code temporary paths/parameters.

In production:
- Use controlled job/task parameters.
- Never depend on manual cell execution order.
- Extract reusable Python modules/functions where appropriate.
- Configure timeouts, retries, and notifications.
- Keep secrets completely out of notebooks.
- Enforce logging and data quality gates.
- Maintain CI/CD, tests, and release metadata.

Never copy an experimental notebook full of scratch cells straight into production on a schedule without verifying idempotency.

### 18.4. CI/CD and Source Control

Promoting a pipeline from dev to production should organize:

~~~text
Git repository
  ├─ src/              transformation code
  ├─ notebooks/        interactive workflows
  ├─ tests/            unit / contract tests
  ├─ sql/              table definitions / business views
  ├─ deployment/       bundle/IaC configuration
  └─ docs/             source contracts, runbooks, ADRs
~~~

This directory structure is an architectural example—**no file creation is required** for this assignment.

Use supported Databricks deployment tooling (bundles/CLI/APIs/IaC) with Azure DevOps or GitHub Actions under service identities; exact tooling depends on your ecosystem.

Separate stages:
1. CI runs linting and unit tests.
2. Integration tests run in a staging catalog/schema.
3. Data contract and security validation.
4. CD deploys workflow/compute configs under a scoped identity.
5. Production approval gate.
6. Monitoring/canary verification and rollback plan.

### 18.5. Parameters and Environments

A job parameter payload might look like:

~~~json
{
  "environment": "staging",
  "input_catalog": "commerce_staging",
  "output_catalog": "analytics_staging",
  "process_date": "2026-11-20",
  "run_mode": "incremental",
  "fail_on_quality_error": true
}
~~~

This is an illustrative team-designed schema, not a mandatory Databricks Job API schema. Never let arbitrary users pass a production catalog name via parameters to read or write outside their authority; enforce allowlists and UC permissions.

### 18.6. Orchestration Systems Outside Databricks

Databricks Jobs can integrate with Azure Data Factory, Microsoft Fabric pipelines, Azure Functions, or external orchestrators as needed. Avoid running two independent schedulers that trigger the same pipeline and overwrite data concurrently.

When ADF invokes a Databricks job, define clearly:
- Who owns the schedule?
- Where are retries and checkpoints stored?
- Where are SLAs and alerts centralized?
- Which system is the source of truth for job status?
- How are duplicate runs canceled or failed over?

## 19. Data Quality and Testing

### 19.1. Test Categories

| Category | Example | When It Runs |
|---|---|---|
| Schema | Non-null `order_id`, `unit_price` is `DECIMAL` | Ingest / PR |
| Domain | `quantity > 0`, valid `status` | Silver |
| Uniqueness | One latest row per `tenant_id + order_id` | Silver |
| Referential | `product_id` exists in dimension | Silver / Gold |
| Freshness | Data updated within SLA | Post-job |
| Volume | Row counts do not drop abnormally | Post-ingest |
| Reconciliation | Total order value matches source within tolerance | Gold / cutover |
| Permission | BI cannot read Bronze PII | Release / security |
| Idempotency | Running identical inputs twice does not double outputs | Integration test |
| Failure recovery | Checkpoints and retries behave safely | Staging chaos test |

### 19.2. Deciding Between Fail-Fast and Quarantine

Not every data error should halt the entire pipeline:

- **Invalid quantity:** quarantine the row and notify the data owner if policy allows partial success.
- **Missing critical schema:** fail the pipeline before publishing Gold.
- **Single tenant corrupted:** isolate the tenant if business rules permit.
- **PII appearing in an unauthorized column:** block release and alert security.
- **Duplicate file:** handle via source keys and idempotency.
- **Late event:** apply business watermark/backfill policy.

Define "partial success" explicitly and never mark an SLA as met if 20% of a tenant's data sits in quarantine.

### 19.3. Constraints Where Appropriate

On supported Delta tables, `NOT NULL` or `CHECK` constraints can be enforced. Illustrative example on an existing lab table, only after confirming existing data conforms:

~~~sql
ALTER TABLE training_catalog.sandbox.orders_silver_lab
ADD CONSTRAINT positive_quantity CHECK (quantity > 0);
~~~

Never add strict constraints to a raw Bronze table holding malformed rows and cause unplanned ingestion outages. `CHECK` constraints also do not replace business uniqueness or unsupported foreign-key semantics.

### 19.4. Testing Incremental and Late Data

A thorough test suite covers:

1. New source events.
2. Events with duplicate source IDs.
3. Older event arriving after a newer version.
4. Events missing mandatory fields.
5. Source adding new columns.
6. Malformed price or unexpected null types.
7. Job crash between Bronze and Silver.
8. Rerun with the same batch ID.
9. Stream restart from checkpoint.
10. Historical backfill after code changes.

Verify results against **actual output tables and metrics**, not merely "job status Success."

## 20. Observability and Troubleshooting

### 20.1. How Does Spark UI Help?

Spark UI reveals:
- Jobs and stages.
- Per-stage and per-task durations.
- Shuffle read/write volumes.
- Memory and disk spill.
- Executor memory and CPU utilization.
- Failed and retried tasks.
- SQL query plans and physical operators.
- Skew: a few tasks running vastly longer than peers.

If a job stalls because one task processes 90% of the data, adding more workers will not help. If every executor spills to disk, fix the query plan, partition sizing, or capacity.

### 20.2. Databricks Job and Pipeline Telemetry

Operational signals:

| Signal | Why It Matters |
|---|---|
| Job run status/duration | Pipeline SLA |
| Task retries/failures | Transient vs. permanent faults |
| Rows/bytes ingested | Data volume and freshness |
| Quarantine counts | Source quality |
| Input/output schema versions | Drift detection |
| Streaming lag | Delayed data, checkpoint backlogs |
| Shuffle/spill/skew | Spark bottlenecks |
| Cluster/SQL warehouse utilization | Capacity and cost |
| Delta table history | Schema/data evolution |
| Unity Catalog audit/lineage | Governance |
| Azure Storage errors | Networking, storage, quotas |
| Cost by job/team | Budgeting |

Persist run metadata with UTC timestamps, commit SHAs, job IDs, environments, table versions, and source identifiers. Keep PII and credentials out of logs.

### 20.3. Common Failure Matrix

| Symptom | Likely Cause | How to Investigate |
|---|---|---|
| Job stuck on final stage | Data skew or one huge task | Spark UI task durations, key distribution |
| Executor OutOfMemory | Oversized partitions, excessive cache, bad join | Memory/spill metrics, partition sizes |
| Driver OutOfMemory | `collect`/`toPandas` on large dataset | Remove `collect`, use distributed writes |
| Huge shuffle | `groupBy`/`join`/`orderBy` | Explain plan, partitioning, AQE |
| Many small files | Frequent micro-batch writes | File metrics, optimize policies |
| `FileNotFound` | Wrong source path, permission, or retention purge | UC volumes, ADLS paths, file lifecycle |
| 403 reading ADLS | Storage RBAC/ACL, credential, or UC privileges | Inspect each permission layer |
| Job SQL permission denied | Missing `USE CATALOG`/`SCHEMA`/`SELECT`/`MODIFY` | UC grants and executing principal |
| Stream reprocesses inputs | Checkpoint reset or source altered | Checkpoint/state audit |
| Late events dropped | Watermark too short | Event-time arrival distributions |
| Schema mismatch | Upstream drift, Delta enforcement | Source contract, rescued data |
| `MERGE` fails | Duplicate source keys or concurrent conflicts | Deduplicate stage, concurrent writers |
| Streaming state grows huge | Wide watermark or high key cardinality | State metrics and aggregation logic |
| Stale dashboard | Failed job, Gold not updated | Job lineage and freshness |
| Idle compute burning budget | Missing auto-termination | Billing and cluster policies |
| Network timeout | VNet/DNS/firewall/private path | Test from exact compute environment |
| Slow Python UDF | Serialization/optimizer overhead | Switch to built-in functions or vectorized UDFs |

### 20.4. Ordered Troubleshooting Runbook

1. Identify **job ID, run ID, environment, and UTC timestamps**.
2. Isolate whether the failure stems from source, compute, transformation, sink, or permissions.
3. Read Databricks run/task logs—not just the "Failed" banner.
4. Inspect Spark UI plans, shuffles, spills, and skew for performance issues.
5. Check checkpoints and source offsets for streams.
6. Verify Unity Catalog grants, storage credentials, and networking.
7. Diff schemas, data contracts, and deployment commits against the last good run.
8. Determine whether the job can retry **safely**.
9. Quarantine/reconcile bad records rather than deleting outputs blindly.
10. Execute a controlled rerun, validate outputs/metrics, and document a postmortem.

**Never delete checkpoints, run `VACUUM` across an entire table, or open a public Storage firewall as a quick test before identifying the root cause.**

## 21. End-to-End Reference Architecture: Revenue and Clickstream

### 21.1. Requirements

A commerce platform has:

- Millions of order records from Azure SQL Database.
- Web clickstream via Event Hubs.
- Daily product CSVs stored in ADLS Gen2.
- Revenue dashboards by tenant and date.
- Fraud analytics needing near-real-time data.
- Customer PII that must be protected.
- Tenant-specific reports.

### 21.2. Reference Design

~~~mermaid
flowchart TD
    SQL["Azure SQL Database"] --> ING["Ingestion / CDC pipeline"]
    EH["Event Hubs clickstream"] --> ST["Streaming ingestion"]
    FILES["Product CSV ADLS"] --> AL["Auto Loader"]
    ING --> BR["Bronze Delta"]
    ST --> BR
    AL --> BR
    BR --> SI["Silver clean + dedupe + joins"]
    SI --> GO["Gold revenue + funnel"]
    GO --> WH["Databricks SQL Warehouse"]
    WH --> DASH["BI dashboards"]
    SI --> ML["Fraud analytics"]
    UC["Unity Catalog"] -. "Access / lineage" .-> BR
    UC -. "Access / lineage" .-> SI
    UC -. "Access / lineage" .-> GO
    JOB["Jobs + monitoring"] --> BR
    JOB --> SI
    JOB --> GO
~~~

The CDC path from Azure SQL or Event Hubs is a logical architecture; choose supported connectors/ingestion services and verify source read permissions. Never assume Databricks natively offers automatic CDC for every Azure SQL database configuration.

### 21.3. Why Separate Bronze/Silver/Gold?

- Bronze preserves order and clickstream events close to source fidelity.
- Silver standardizes event IDs, statuses, currencies, timezones, and deduplicates.
- Gold defines revenue and conversion funnels per business contracts.
- Unity Catalog enforces permissions: BI reads Gold, fraud reads filtered Silver, general users never see raw PII.
- Jobs/Workflows orchestrates batch tiers and tracks failures.
- Structured Streaming handles near-real-time events with checkpoints and watermarks.
- ADLS Gen2 stores Delta tables long-term under retention policies.

### 21.4. Acceptance Tests

- Zero duplicate orders after retries or backfills.
- Late order updates never double-count revenue.
- Invalid currencies and negative quantities route to quarantine.
- Gold computes metrics strictly per approved business definitions.
- Tenant isolation verified across views and permissions.
- Streaming restarts from checkpoints without duplicating business outputs.
- Jobs alert when freshness SLAs slip.
- Reports carry traceable lineage and source IDs.
- Cost stress tests evaluate sudden workload spikes.
- Recovery/rollback tested when breaking source schemas disrupt pipelines.


## 22. Comparing Databricks with Other Data Services

### 22.1. No Single Service Fits Every Workload

| Tool / Service | Strengths | Do Not Use Instead Of |
|---|---|---|
| **Azure Databricks** | Spark ETL, lakehouse, Delta, streaming/analytics, governed pipelines | An OLTP database for per-request HTTP transactions |
| **Azure Data Factory** | Orchestration/integration, Copy activities, and connectors | An engine executing complex Spark transforms natively |
| **Azure SQL Database** | Relational OLTP transactions, constraints, application queries | Spark ETL over multi-TB raw files |
| **Azure Cosmos DB** | Partitioned low-latency NoSQL application operations | Ad-hoc aggregations scanning a massive data lake |
| **Azure Event Hubs** | Event ingestion and buffering | Long-term lakehouse storage or SQL analytics |
| **ADLS Gen2** | Cloud object storage for raw files and Delta data | Running SQL/Spark compute itself |
| **Microsoft Fabric** | Integrated analytics platform with lakehouse/warehouse/BI per capabilities | Assume 1:1 feature parity with every Databricks feature |
| **Azure Synapse Analytics** | SQL/Spark/integration workloads per workspace capabilities | Must evaluate maturity, support, and system contracts |
| **Azure Functions** | Event-driven logic and short-lived compute | Multi-TB distributed ETL suited to Spark |

An enterprise architecture frequently combines multiple services: Azure Data Factory triggers Databricks jobs, ADLS stores Delta tables, Event Hubs ingests events, and BI reads Gold.

### 22.2. Selection Questions

1. Is data large enough to require distributed compute?
2. Do you need Spark DataFrames/SQL, ML, or streaming?
3. Do you want to govern Delta tables through Unity Catalog?
4. Does data already live in ADLS/Delta or in an OLTP database?
5. Is the latency SLA in milliseconds, minutes, or hours?
6. Do you need lineage, data contracts, and multi-team governance?
7. Does the team have Spark/SQL skills and job/cost operational readiness?
8. How must total cost balance networking, storage, VMs/DBUs, and monitoring?
9. Has the organization standardized on another analytics platform?
10. Can you run a POC comparing two candidates before locking in the architecture?

**If a SQL query over 200,000 rows already runs fast in an existing database, do not build a Spark pipeline just to "modernize to the cloud."**

## 23. Architectural Anti-Patterns to Avoid

### 23.1. Collecting Full Datasets to the Driver

Wrong on large tables:

~~~python
# Do not use on very large production tables.
all_rows = huge_df.collect()
~~~

Right architectural direction:

~~~python
# Spark processes distributedly; write to a governed output.
aggregated = huge_df.groupBy("tenant_id").count()
# With proper permissions and purpose, use a distributed write.
~~~

`collect` is fine for inspecting a few bounded rows; it cannot serve as a multi-TB export mechanism.

### 23.2. Using UDFs for Every Transformation

Python UDFs incur serialization overhead and blind the optimizer. Prefer Spark SQL built-in functions wherever possible; use UDFs only for custom algorithms after benchmarking.

### 23.3. Putting Secrets Directly in Notebooks

Avoid:

~~~python
# UNSAFE EXAMPLE — never use real credentials.
storage_key = "PLACEHOLDER_SECRET"
~~~

Use managed identities, Unity Catalog storage credentials, and organization-approved secret managers. Keep secrets out of commit history and logs.

### 23.4. Sharing One Cluster Across Every Team

Sharing a single interactive cluster across production ETL, BI dashboards, and exploratory notebooks causes resource contention, inflates costs, and muddles authorization. Isolate compute/workloads by SLA, security boundary, and budget.

### 23.5. Using `overwrite` for Production Retries

Example:

~~~python
# Use only on verified targets with intentional full replacement.
df.write.mode("overwrite")
~~~

Never blindly run `overwrite` against production Gold tables during retries without considering concurrent downstream readers and rollback. Prefer transactional upserts, idempotent patterns, staging tables, and controlled promotion.

### 23.6. Ignoring Late Data

A click event arriving 20 minutes late can shift business metrics. A 5-minute watermark risks dropping it. Analyze **late-arrival distributions**, business reporting cutoffs, and backfill policies.

### 23.7. Treating Delta Time Travel as Permanent Backup

Time travel depends on retained logs and data files. Manage `VACUUM`, retention, and restore plans explicitly; never treat time travel as your sole DR strategy.

### 23.8. Auto-Accepting Every Schema Drift

Unchecked automatic column additions or type shifts from upstream sources can corrupt Gold metrics, privacy boundaries, and BI reports. Keep Bronze flexible if needed, while enforcing contracts and reviews on Silver and Gold.

### 23.9. Ignoring Partition Skew and File Sizes

A single hot key can stall a stage; millions of tiny files bog down metadata scans. Neither is solved simply by throwing unlimited workers at the cluster.

### 23.10. Monitoring Only "Success" Status

A job can report Success yet:
- Ingest only 10% of expected data.
- Route every row to quarantine.
- Compute wrong timezones or revenue.
- Serve stale Gold versions.
- Fail to refresh downstream consumers.

Production demands **data freshness, quality, reconciliation, and business metrics**—not just green job statuses.

## 24. Azure Databricks Rollout Plan

### 24.1. Phase 1: Requirements and Architecture

Define:

- Data sources plus volume, velocity, and variety.
- Batch/streaming workloads and latency SLAs.
- Data classification/PII and retention rules.
- Storage account/container/ADLS Gen2 regions.
- Workspace isolation across dev/staging/prod.
- Compute models, budgets, and networking.
- Identity, Unity Catalog structure, owners, and lineage.
- Backup/DR and replay requirements.
- Error/retry scenarios and alerting.

### 24.2. Phase 2: Security Foundation

1. Provision or onboard to an organization-approved workspace.
2. Configure Microsoft Entra ID and workspace identities.
3. Set up Unity Catalog catalogs, schemas, tables, and volumes.
4. Configure Storage credentials/external locations via managed identities where supported.
5. Verify ADLS RBAC/ACLs alongside UC permissions.
6. Validate private networking, DNS, and egress per compute model.
7. Configure secrets, audit logs, and retention.
8. Enforce cluster policies, auto-termination, and cost tags.

### 24.3. Phase 3: Pipelines and Testing

1. Author source data contracts.
2. Build Bronze ingestion preserving source metadata.
3. Build Silver transformations with quarantine.
4. Build Gold metrics with accountable owners.
5. Configure Jobs/dependencies, checkpoints, and retries.
6. Test duplicate data, late data, and schema drift.
7. Test permissions and PII controls.
8. Benchmark with anonymized production-scale data/traffic.
9. Test failure recovery and rollbacks.
10. Document operational runbooks.

### 24.4. Phase 4: Release and Optimization

- Deploy via a least-privilege CI/CD identity.
- Enable monitoring, alerts, and tracing.
- Run canary checks or parallel output comparisons before cutover.
- Track freshness, quality, completion times, and costs.
- Tune partitioning, joins, and file sizes based on real measurements.
- Drill backfills, rollbacks, and data recovery.
- Record Architecture Decision Records (ADRs) and release metadata.

## 25. Production Checklist

### Data Design

- [ ] Source owners, schemas, and partition/access patterns confirmed.
- [ ] Bronze/Silver/Gold data contracts and metric definitions documented.
- [ ] Explicit timezone policy applied to timestamps.
- [ ] Stable source event IDs and business keys established.
- [ ] Late, duplicate, and invalid data policies tested.
- [ ] Raw PII prevented from leaking outside authorized scopes.
- [ ] Lineage and data retention configured.
- [ ] Storage layout and Delta table optimization evaluated.

### Spark and Pipelines

- [ ] Driver never collects large datasets.
- [ ] `groupBy`/joins reviewed for shuffle/skew and via `explain` plans.
- [ ] Compute sized against real data volumes.
- [ ] Durable, job-specific checkpoint paths configured.
- [ ] Checkpoints never shared across incompatible queries.
- [ ] Ingestion implements idempotency and safe reruns.
- [ ] Staged `MERGE` inputs deduplicated prior to merge.
- [ ] Schema evolution policy enforced.
- [ ] Quarantine and data quality alerts active.
- [ ] Streaming restarts and late events tested.
- [ ] UDFs, caches, and repartitions justified and benchmarked.

### Security and Governance

- [ ] Correct subscription, resource group, region, and workspace.
- [ ] Catalog/schema/table/volume privileges follow least privilege.
- [ ] Managed identities and storage credentials properly scoped.
- [ ] Private networking, DNS, TLS, and egress verified.
- [ ] Zero hard-coded secrets or PII in notebooks/logs.
- [ ] Audit logs, ownership, and change approvals active.
- [ ] Data residency, retention, and backup policies clear.
- [ ] CI/CD identities lack unnecessary organization-wide admin privileges.

### Operations and Cost

- [ ] Jobs configured with dependencies, timeouts, retries, and notifications.
- [ ] Interactive compute enforces auto-termination.
- [ ] Compute policies, max workers, and approved runtimes enforced.
- [ ] DBUs, infrastructure, ADLS, logging, and budgets tracked.
- [ ] Spark UI / SQL execution diagnostics available for incident response.
- [ ] Freshness SLAs, data quality, volume, and output verification monitored.
- [ ] Runbooks cover source, compute, network, auth, sink, schema, and streaming issues.
- [ ] Backfills, rollbacks, and recovery tested.
- [ ] Tables have owners and aligned `VACUUM`/retention schedules.
- [ ] Post-growth reviews scheduled when workloads or data exceed forecasts.

## 26. Knowledge Self-Check

1. **What problem does Apache Spark solve?** Distributed data processing across DataFrames, SQL, batch, and streaming.
2. **What does the driver do?** Builds query plans, coordinates jobs/stages/tasks, and tracks execution.
3. **What do executors do?** Run tasks, perform computations, and process partitions.
4. **Are Spark partitions the same as Delta table partitioning?** No.
5. **What is lazy evaluation?** Transformations construct an execution plan; actions trigger execution.
6. **Examples of actions?** `count`, `show`, `collect`, `write`.
7. **When does a shuffle occur?** When data must be redistributed across partitions, such as `groupBy`, `join`, or `orderBy`.
8. **What problem does data skew cause?** A few tasks process vastly more data than all others.
9. **Why can `collect` crash the driver?** It pulls huge volumes of distributed data into driver RAM.
10. **How do Spark DataFrames differ from pandas?** Spark DataFrames process distributedly; pandas runs on a single machine.
11. **What does Azure Databricks add to Spark?** Workspaces, runtimes, managed compute, jobs, Delta/SQL, and governance.
12. **What does Unity Catalog manage?** Data objects, privileges, metadata, and lineage per supported capabilities.
13. **What is ADLS Gen2 used for?** Storing files, object data, and Delta tables on Azure.
14. **What should Bronze store?** Source data and enough ingestion metadata for replay.
15. **What should Silver do?** Parse, validate, normalize, deduplicate, enrich, and quarantine.
16. **What is Gold for?** Metrics and data marts governed by business contracts.
17. **How does Delta Lake differ from a plain Parquet folder?** Adds transaction logs, ACID guarantees, schema enforcement, DML, and time travel where supported.
18. **Is time travel permanent?** No; it depends on log and file retention.
19. **What can `VACUUM` affect?** Deletes unreferenced files, removing the ability to read older history.
20. **Does `MERGE` automatically prevent duplicate business keys?** No; pre-merge deduplication and idempotency are still needed.
21. **Which format does Auto Loader use?** `cloudFiles`.
22. **What is `schemaLocation` used for?** Tracking and managing Auto Loader schemas.
23. **Where should checkpoints be stored?** Durable, authorized paths dedicated to a single query.
24. **What risk comes with deleting a checkpoint?** Reprocessing data, duplicating outputs, or corrupting state.
25. **How does `availableNow` differ from a continuous stream?** Processes available source inputs and terminates cleanly per trigger semantics.
26. **How does event time differ from processing time?** When an event occurred vs. when the pipeline processed it.
27. **What do watermarks do?** Bound late-data acceptance and state per streaming operator semantics.
28. **Does exactly-once apply automatically to a custom HTTP sink?** No.
29. **When is a broadcast join beneficial?** Small dimension table, fits in RAM, avoids shuffling large fact tables.
30. **What is AQE?** Spark adjusting query plans dynamically using runtime statistics.
31. **Is caching always faster?** No; it can cause memory pressure and spill overhead.
32. **What impact do small files have?** Inflate metadata/task overhead and slow down queries.
33. **What is a DBU?** Databricks consumption unit used in supported pricing models.
34. **Jobs compute or interactive compute for nightly ETL?** Typically evaluate jobs compute.
35. **Is Unity Catalog `SELECT` enough if Storage permissions/networking fail?** No.
36. **Does Azure RBAC replace table-level Unity Catalog grants?** No.
37. **Why separate BI Gold from Bronze PII?** Least privilege and governance.
38. **Does Job Success prove data accuracy?** No; quality, freshness, and reconciliation tests are still required.
39. **When is Databricks unnecessary?** Small data or simple OLTP APIs already served well by dedicated engines.
40. **What makes a pipeline trustworthy?** Data contracts, idempotency, checkpoints, governance, quality tests, monitoring, recovery, and cost control.

## 27. References

Official links to verify features, Runtime support, and implementation guidance:

- [Azure Databricks documentation](https://learn.microsoft.com/azure/databricks/) — workspaces, compute, notebooks, Jobs, SQL, and governance.
- [What is Azure Databricks?](https://learn.microsoft.com/azure/databricks/introduction/) — core concepts and workloads.
- [Apache Spark programming guide](https://spark.apache.org/docs/latest/) — Spark SQL/DataFrames, Structured Streaming, tuning.
- [PySpark API reference](https://spark.apache.org/docs/latest/api/python/) — DataFrame functions, Window, and SparkSession syntax.
- [Databricks compute documentation](https://learn.microsoft.com/azure/databricks/compute/) — compute types, runtimes, policies, and lifecycle.
- [Databricks Workflows/Jobs](https://learn.microsoft.com/azure/databricks/jobs/) — orchestration and job monitoring.
- [Databricks SQL](https://learn.microsoft.com/azure/databricks/sql/) — warehouses and SQL analytics.
- [Databricks Delta Lake](https://learn.microsoft.com/azure/databricks/delta/) — transactions, DML, history, VACUUM, and optimization.
- [Medallion lakehouse architecture](https://learn.microsoft.com/azure/databricks/lakehouse/medallion) — Bronze/Silver/Gold.
- [Auto Loader](https://learn.microsoft.com/azure/databricks/ingestion/cloud-object-storage/auto-loader/) — `cloudFiles`, `schemaLocation`, and incremental ingestion.
- [Structured Streaming](https://learn.microsoft.com/azure/databricks/structured-streaming/) — watermarks, triggers, checkpoints, performance.
- [Unity Catalog](https://learn.microsoft.com/azure/databricks/data-governance/unity-catalog/) — data governance, privileges, external locations.
- [Unity Catalog volumes](https://learn.microsoft.com/azure/databricks/volumes/) — managing file resources and Volume paths.
- [Azure Data Lake Storage Gen2 overview](https://learn.microsoft.com/azure/storage/blobs/data-lake-storage-introduction) — storage, hierarchical namespace, data lake design.
- [Azure Databricks networking](https://learn.microsoft.com/azure/databricks/security/network/) — networking and connection security.
- [Azure Databricks monitoring](https://learn.microsoft.com/azure/databricks/admin/account-settings/usage/) — usage and account administration; also see job/Spark UI diagnostics.
- [Azure Databricks pricing](https://azure.microsoft.com/pricing/details/databricks/) — pricing models and cost planning.
- [Azure Cost Management](https://learn.microsoft.com/azure/cost-management-billing/costs/) — budgets, tags, and cost analysis.

**Conclusion:** Apache Spark provides the distributed compute engine through drivers, executors, DAGs, and DataFrames. Azure Databricks builds a lakehouse development, processing, and operational environment atop Spark, Delta Lake, ADLS Gen2, Unity Catalog, and Jobs/Workflows. Implementing it properly requires designing **clear Bronze/Silver/Gold boundaries, source keys and data quality rules, incremental ingestion/checkpoints, data authorization, shuffle and storage layout optimization, alongside monitoring/costing and recovery runbooks**. A trustworthy pipeline does more than finish with a Success status—it produces reconcilable figures with lineage, enforces proper security, and recovers safely on failure.
