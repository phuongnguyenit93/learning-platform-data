# Microsoft Fabric in the Azure Data Ecosystem

A retail enterprise uses Azure SQL Database to store orders, Azure Blob Storage for files, Azure Event Hubs to collect traffic events, and Power BI for reporting. The data team wants to unify these sources, cleanse, analyze, and present metrics without stitching together too many services via bespoke integration glue code. **Microsoft Fabric** is a major approach for this problem: providing data engineering, data integration, data warehousing, real-time analytics, data science, and business intelligence experiences on a **Software as a Service (SaaS)** analytics platform backed by a unified storage layer, **OneLake**.

Within the Microsoft Azure ecosystem, Fabric **is not a new name for Azure Storage, Azure SQL Database, or Azure Databricks**, nor does it automatically replace all of those components. Fabric can **read, connect to, copy, sync, or analyze** data across many Azure services depending on features, permissions, and connectivity models. Architects must know **where source data lives, where transformations run, where queries/reports are served, and where costs and security are governed**.

This lesson belongs to the **Data Platforms and Analytics** chapter in the **CLOUD_PROVIDERS_AZURE** module. The module explores Azure from subscriptions, resource groups, and Microsoft Entra ID to virtual networks, compute, storage, and data—then deploying, monitoring, securing, and controlling costs of an application architecture. This lesson connects those building blocks into a data pipeline capable of leveraging Microsoft Fabric.

> **Scope and Caveats:** Microsoft Fabric evolves rapidly; workload names, item types, OneLake integration features, security, network integration, billing, and licensing can vary by tenant, region, capacity, and time. Examples are illustrative architectures/labs; no commands in this document provision live resources. Always check official documentation for your exact tenant and SKU before applying to production.

## Learning Objectives

After this lesson, you will be able to:

1. Explain Fabric as a **SaaS data analytics platform** and identify its relationship with Azure services.
2. Distinguish **tenant, Fabric capacity, workspace, and Fabric item**.
3. Describe **OneLake**, **Lakehouse**, the **Delta Lake** format, **Warehouse**, **SQL analytics endpoint**, **semantic model**, and **Power BI report**.
4. Distinguish **Data Factory pipeline**, **Dataflow Gen2**, **Notebook/Spark**, **Mirroring**, **OneLake shortcut**, and **Eventstream/Eventhouse**.
5. Design a **Bronze → Silver → Gold** pipeline connecting Azure SQL, ADLS/Blob, and Event Hubs.
6. Evaluate when to choose Fabric instead of—or alongside—**Azure Data Factory, Azure Synapse Analytics, Azure Databricks, and Azure Data Explorer**.
7. Understand identity layers, workspace/item permissions, sensitive data controls, and network connectivity.
8. Evaluate **Fabric capacity, Compute Units (CU), OneLake storage, throttling, and Power BI licensing** before operating.
9. Write PySpark, SQL, and KQL examples illustrating the analytical flow.
10. Build an operational, monitoring, testing, and cost-optimization checklist for production.

## 1. Context: Why Do Enterprises Need a Unified Analytics Platform?

A traditional data architecture often spans many separate tools:

~~~text
                         Data Sources

Azure SQL       Cosmos DB       ADLS/Blob      Event Hubs
   |                |               |              |
   +----------------+---------------+--------------+
                            |
                            v
                   Ingestion / ETL / ELT
                            |
                            v
                      Data lake / DWH
                            |
                            v
                     Data engineering
                            |
                            v
                   Semantic model / BI
                            |
                            v
                        Consumers
~~~

When each step runs inside a distinct product, operations teams must manage:

- Connections, service principals, and secrets across many tools.
- Repeated data copies across lake, warehouse, and BI tiers.
- Schema standards, data quality, and lineage.
- Batch schedules, real-time streams, retries, and failure recovery.
- Fragmented compute, storage, egress, and licensing costs.
- Read permissions for analysts, data engineers, and report viewers.

Fabric aims to reduce this fragmentation through a **shared governance and collaboration experience**, **OneLake**, and integrated workloads. Yet "unified" **does not mean you can skip data architecture, authorization, or data standardization**.

## 2. What Is Microsoft Fabric?

Microsoft Fabric is a **SaaS data analytics platform** providing integrated experiences for:

- **Data ingestion/orchestration:** Pipelines, Dataflow Gen2, connectors.
- **Data engineering:** Lakehouse, Notebooks, Spark.
- **Data warehousing:** Fabric Warehouse and SQL.
- **Real-time intelligence:** Eventstream, Eventhouse, and KQL per feature support.
- **Data science:** workspace for notebooks and ML experiments/models per supported capabilities.
- **Business intelligence:** Power BI semantic models, reports, and dashboards.
- **Data governance/discovery:** catalog, lineage, sensitivity labeling, and governance capabilities aligned with Microsoft Purview and tenant policies.

### How Does Fabric Differ from an Azure Server?

Users primarily work with **workspaces** and **items** rather than provisioning VMs to install SQL, Spark, Airflow, or Redis. Compute for many experiences is supplied through **Fabric capacity** or a matching licensing/trial model.

~~~text
Microsoft Entra tenant
        |
        v
Microsoft Fabric tenant configuration
        |
        +--> Fabric capacity (compute budget)
        |         |
        |         +--> Workspace: Analytics
        |         |       +--> Lakehouse
        |         |       +--> Notebook
        |         |       +--> Warehouse
        |         |       +--> Semantic model/Report
        |         |
        |         +--> Workspace: Realtime
        |                 +--> Eventstream
        |                 +--> Eventhouse
        |
        +--> OneLake (logical unified data lake)
~~~

This diagram shows conceptual governance relationships. **OneLake is not a VM or disk sitting inside a capacity**, and storage and capacity have separate management and billing mechanics.

## 3. How Does Fabric Fit into the Azure Ecosystem?

| Need | Common Azure Service | How Fabric Complements It |
|---|---|---|
| Transactional database | Azure SQL Database, Azure Cosmos DB | Reads, copies, or syncs data for analytics without turning the lakehouse into an OLTP store |
| Object/data lake storage | Azure Blob Storage, ADLS Gen2 | Ingests or accesses via **OneLake shortcuts** where supported by source/capabilities |
| Event streaming | Azure Event Hubs, IoT Hub | Consumes and analyzes streams via real-time ingestion features |
| Data integration | Azure Data Factory | Fabric Data Factory pipelines / Dataflow Gen2, depending on orchestration needs |
| Big data processing | Azure Databricks, Azure Synapse Spark | Fabric Spark/Notebooks and Delta processing |
| SQL analytics | Azure Synapse dedicated/serverless SQL, Azure SQL | Fabric Warehouse and Lakehouse SQL analytics endpoint |
| Real-time analytics | Azure Data Explorer, Azure Stream Analytics | Fabric Eventhouse / KQL / Eventstreams |
| Reporting | Power BI | Power BI is a core experience inside Fabric |
| Governance | Microsoft Purview, Entra ID | Integrates discovery, lineage, labels, and identity per policy |

**Not every row above represents 1:1 feature parity.** For instance, Fabric Warehouse has different T-SQL/transaction semantics and limits than Azure SQL Database; Eventhouse does not replace Event Hubs for retention and consumer offsets; Fabric Spark does not expose every administrative option of Azure Databricks.

### Is Fabric an Azure Resource Group?

Fabric **is a SaaS service** organized around tenants, workspaces, and items under the Fabric model. A **Fabric capacity F SKU** can be purchased and managed under an Azure subscription and resource group per supported mechanisms, whereas **workspaces and items** are not managed like individual Azure VMs or VNets inside a resource group. This is an important governance distinction.

## 4. Governance Concepts: Tenant, Capacity, Workspace, Item

| Component | Meaning |
|---|---|
| **Microsoft Entra tenant** | Identity boundary for users, groups, and organizational policies |
| **Fabric tenant settings** | Rules enabling/disabling features, sharing, item creation, data movement, etc. |
| **Fabric capacity** | Compute budget allocated to assigned workloads under the licensing model |
| **Workspace** | Collaborative container managing ownership, items, and permissions |
| **Item** | Unit such as Lakehouse, Warehouse, Pipeline, Notebook, Eventhouse, or Report |
| **OneLake** | Unified logical data lake layer for Fabric data and supported external access |
| **Connection/credential** | Configuration defining how Fabric authenticates to external sources |
| **Deployment pipeline/Git** | Mechanisms promoting Fabric items across environments per supported features |

### One Workspace Does Not Automatically Mean One Customer Tenant

A Fabric **workspace** is a collaboration and governance boundary for teams; it does not automatically enforce application-tier SaaS multi-tenant isolation. If multiple customers query a shared semantic model or warehouse, design row/column/object-level security and test authorization end-to-end.

### Capacity Permissions vs. Workspace Permissions

A capacity administrator is not automatically the owner of every data source; someone with edit rights in a workspace does not automatically gain access to every Azure SQL source. **Source data-plane permissions** and **Fabric item permissions** must be granted separately at their proper scopes.

## 5. OneLake: A Unified Logical Data Lake Layer

**OneLake** is the shared logical data lake for Fabric, built on Azure Data Lake Storage-compatible storage technology and open formats. It enables multiple Fabric workloads to access governed, organized datasets in a unified environment.

~~~text
                        OneLake
                 +---------------------+
                 | Workspace A         |
                 |  Lakehouse Sales    |
                 |   Files             |
                 |   Tables (Delta)    |
                 |                     |
                 | Workspace B         |
                 |  Lakehouse Metrics  |
                 |   Tables (Delta)    |
                 +---------------------+
                          |
          +---------------+----------------+
          |               |                |
          v               v                v
       Spark          SQL analytics      Power BI
       notebooks      endpoint           semantic model
~~~

### OneLake Does Not Mean Dumping Everything into One Folder

Each workspace and lakehouse maintains its own resource structure and paths. OneLake shortcuts can **reference** data in other locations without always copying bytes physically, though access, permissions, and performance depend on shortcut type and source.

### What Formats Does OneLake Store?

**Lakehouse tables** typically use **Delta Lake** (Parquet data files paired with transaction logs). Raw source files like CSV, JSON, and Parquet can land in **Files**, then Spark or other tools cleanse and materialize them into **Tables**.

**OneLake does not automatically turn every file into a typed SQL table.** Raw files must be governed, standardized, and registered properly before serving SQL/BI.

## 6. Files, Tables, and Delta Lake

A Lakehouse conceptually looks like:

~~~text
Lakehouse: sales_lh
    |
    +-- Files/
    |    +-- landing/orders_2026_11_20.csv
    |    +-- raw/events/
    |
    +-- Tables/
         +-- bronze_orders/
         +-- silver_orders/
         +-- gold_daily_sales/
~~~

### Why Choose Delta Lake?

- Provides a table format with metadata and a transaction log.
- Suits Spark ETL workflows while remaining consumable by SQL/BI per supported capabilities.
- Organizes tabular data for ongoing read/write optimizations.
- Reduces reliance on raw CSV files in analytical layers.

Still, Delta does not mean every engine supports identical mutation or transaction semantics. Check limitations across **Fabric Spark, Warehouse, and the Lakehouse SQL analytics endpoint** before writing pipelines.

### What Role Do Raw Files Play?

Preserving raw sources helps you:

1. Reconcile when downstream processing produces errors.
2. Re-run transformations with updated logic.
3. Separate ingestion failures from transformation bugs.
4. Retain audit evidence when retention and permissions are designed properly.

The raw layer must govern PII, retention, encryption, and access; never grant analysts blanket read access to uncleaned raw data.

## 7. How Do Lakehouse and Warehouse Differ?

| Question | Fabric Lakehouse | Fabric Warehouse |
|---|---|---|
| Focus | Combines data lake and analytics over files and Delta tables | Relational analytics with a SQL warehouse experience |
| Primary users | Data engineers, Spark developers, analysts | SQL developers, BI/analytics teams |
| Creating/transforming data | Spark/Notebooks, pipelines, and ingestion tools | T-SQL and supported ingestion/ETL mechanisms |
| SQL querying | Via **Lakehouse SQL analytics endpoint** (primarily read-oriented) | **Warehouse SQL endpoint** supporting full write/transform operations |
| Raw files | Includes a `Files` area | Not the primary tool for managing raw lake files |
| Power BI | Can build semantic models on lakehouse data | Can build semantic models on Warehouse |
| When to use | Medallion, ML/Spark, diverse file formats | Star schemas, SQL analytics, governed relational tables |

### Crucial Distinction: Lakehouse SQL Analytics Endpoint

The **Lakehouse SQL analytics endpoint** primarily serves SQL queries over exposed Delta tables; **do not confuse** it with a Warehouse for arbitrary DDL/DML. To write or modify Lakehouse tables, use **Spark or supported write mechanisms**—never assume Warehouse `UPDATE` statements execute through the Lakehouse SQL endpoint.

### Is Fabric Warehouse the Same as Azure SQL Database?

**No.** Fabric Warehouse is an analytical warehousing service, whereas Azure SQL Database targets transactional OLTP workloads across its service tiers. Although both expose T-SQL surfaces, concurrency, data modeling, supported features, and operational guarantees differ.

## 8. SQL Analytics Endpoint and Sample Queries

An analyst can query a standardized table:

~~~sql
-- Read-only T-SQL example assuming the table already exists.
SELECT TOP (20)
    order_date,
    customer_segment,
    SUM(net_amount) AS total_net_sales
FROM dbo.gold_order_sales
GROUP BY order_date, customer_segment
ORDER BY order_date DESC, total_net_sales DESC;
~~~

**Note:** table and column names are entirely illustrative. In a Lakehouse, the endpoint exposes tables and schemas per the service's metadata sync rules; schemas are not guaranteed to be `dbo` in every lakehouse. In a Warehouse, verify exact schema names.

### The SQL Endpoint Alone Does Not Solve Security

Users need appropriate Fabric item, SQL, or OneLake data permissions depending on the access path. **Seeing a table in the SQL explorer does not guarantee permission to read every row.** Verify effective permissions and enforce supported row/column/object-level controls on the right engine where needed.

## 9. Data Factory in Fabric

**Data Factory** is Fabric's data integration experience. Two common components are:

- **Data pipeline:** orchestrates activities, dependencies, schedules, data movement, and external calls.
- **Dataflow Gen2:** low-code data transformations powered by Power Query and supported connectors.

~~~text
Azure SQL / ADLS / SaaS API
           |
           v
      Fabric Pipeline
         |        |
         |        +--> Copy data
         |
         +--> Dataflow Gen2 transform
         |
         +--> Notebook Spark
         |
         v
     Lakehouse / Warehouse
~~~

### Pipelines Do Not Automatically Transform Data

**Orchestration** controls execution order, dependencies, and retries; **transformation** defines how data is cleansed and computed. Inside a pipeline, Copy moves data while Notebooks and Dataflows transform it—each activity carries distinct limits and cost meters.

### Does Fabric Data Factory Differ from Azure Data Factory?

Both share similar pipeline and connector concepts, yet **do not assume 1:1 feature parity**. Integration runtimes, network gateways, managed identities, activity types, CI/CD, and billing must be evaluated separately before migrating from Azure Data Factory.

## 10. Notebooks and Spark in Fabric

**Fabric Data Engineering** provides Notebooks/Spark for big-data processing, converting files into Delta tables, computing aggregates, and standardizing data.

Example flow:

~~~text
Raw CSV in OneLake Files
       |
       v
Fabric Notebook (PySpark)
  - parse fields
  - validate schema
  - drop/mark invalid records
  - deduplicate by business key
       |
       v
Delta tables in Lakehouse
       |
       v
Warehouse / Power BI semantic model
~~~

### When Does Spark Fit?

- Processing large or semi-structured file datasets.
- Multi-step batch transformations.
- Standardizing schemas and running quality checks.
- Using Python/Scala and supported processing libraries.

### Do Not Use Spark for Everything

A 200-row lookup table updated once a day may be processed more efficiently with SQL or Dataflow Gen2 rather than spinning up a Spark session. Weigh compute cost, startup latency, cadence, and team skills.

## 11. PySpark Example: CSV to Delta Table

The snippet below **illustrates a notebook attached to a Lakehouse**. Executing it reads an existing file and creates/writes a table; **run only in a lab Fabric workspace/lakehouse**. Never run without verifying the target table and write permissions.

Suppose the file is:

~~~text
Files/landing/orders.csv

order_id,customer_id,amount
ORD-001,C-001,125000
ORD-002,C-002,75000
ORD-003,C-001,99000
~~~

Notebook:

~~~python
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField, StringType, DecimalType
)

schema = StructType([
    StructField("order_id", StringType(), False),
    StructField("customer_id", StringType(), True),
    StructField("amount", DecimalType(18, 2), True),
])

df = (
    spark.read
    .option("header", "true")
    .schema(schema)
    .csv("Files/landing/orders.csv")
)

clean = (
    df.filter(F.col("order_id").isNotNull())
      .filter(F.col("amount") >= 0)
      .withColumn("ingested_at", F.current_timestamp())
)

# Use a lab table name only; append creates duplicate rows if rerun
# without idempotency/deduplication.
clean.write.format("delta").mode("append").saveAsTable(
    "bronze_orders_lab"
)
~~~

### Points to Explain

1. **Schema is declared explicitly** rather than inferring types from the first few rows.
2. **`DecimalType`** beats floats for monetary values, though real financial workloads still need currency, scale, and validation rules.
3. **`filter`** drops invalid rows here without writing them to quarantine yet.
4. **`append`** is not idempotent if the notebook reruns; production needs `MERGE`/deduplication by key and batch/run ID.
5. The table lands in the Lakehouse attached to the notebook; adjust names/namespaces for your environment.
6. **Spark sessions/compute consume capacity**, even on small files.

### Additions Required for Production

- Validation for mandatory fields and event timestamps.
- Quarantine/error-record tables.
- Per-source ingestion watermarks/checkpoints.
- Audit logging of row counts and run IDs.
- Partitioning/compaction or workload-specific table optimization.
- Bounded retries and duplicate-write prevention.
- Approved schema evolution handling.

## 12. Medallion Architecture: Bronze, Silver, Gold

**Medallion** organizes data by progressive levels of standardization:

~~~text
Sources: Azure SQL / Event Hubs / ADLS
                 |
                 v
         Bronze (raw/landing)
         - preserves source structure
         - ingestion metadata
         - replayability
                 |
                 v
         Silver (clean/validated)
         - standardized schema
         - deduplicated, controlled error handling
         - normalized timezone, currency, business keys
                 |
                 v
         Gold (business-ready)
         - facts/dimensions
         - aggregated KPI tables
         - semantic models / reports
~~~

### Bronze

Stores source data or faithful copies sufficient for reprocessing. Retains source timestamps, ingestion timestamps, batch identifiers, and source files/versions. Define retention and protect PII—never grant wide permissions just because it is "only raw."

### Silver

Standardizes formats and business logic, handles nulls/duplicates/out-of-order events, and applies data quality tests. **Never silently drop bad records**; quarantine enables diagnosing upstream source bugs.

### Gold

Organizes business-ready data: facts/dimensions, metric definitions, and aggregates. Every Gold table or semantic model needs a clear **owner and metric calculation rule** so dashboards do not define revenue inconsistently.

### Must You Create Three Separate Lakehouses?

No. Medallion is an **architectural pattern** that can be implemented across multiple schemas, tables, lakehouses/workspaces, or partially inside a Warehouse within platform limits. Physical separation depends on scale, data ownership, and security boundaries.

## 13. Shortcuts in OneLake: Referencing Without Copying

**OneLake shortcuts** expose data from supported locations into the OneLake namespace—either from another workspace/item or external sources like ADLS Gen2 per connector/feature support.

~~~text
Azure Data Lake Storage Gen2
   container / curated/orders
              |
              | OneLake shortcut
              v
Fabric Lakehouse
   Files/linked_orders  -- references source data
              |
              v
Spark / supported engines
~~~

### Benefits

- Avoids unnecessary physical copies.
- Reduces ingestion effort when data already lives in another lake.
- Reuses existing Azure datasets.
- Allows multiple teams to share one source under supported access models.

### Risks and Limitations

- Shortcuts do not standardize schemas, deduplicate, or cleanse data automatically.
- If source data changes, queries reflect those changes per source/cache/engine semantics.
- **Credentials and access controls** across the shortcut, connection creator, and querying user must be designed carefully.
- Network access to external sources and supported features vary by connector.
- Do not assume every external shortcut supports writes or appears identically as a Delta table to every engine.
- Check whether intermediate engine caches/copies occur if strict data residency rules apply.

**A shortcut is not an immutable backup.** If the underlying source is deleted or access is revoked, referenced data becomes unavailable.

## 14. How Does Mirroring Differ from Shortcuts?

**Mirroring** in Fabric is a set of features that replicates and keeps data synced from **supported sources** into Fabric/OneLake for analytics using source/connector mechanisms. It differs from shortcuts:

| Question | OneLake Shortcut | Fabric Mirroring |
|---|---|---|
| Goal | Reference existing data in another location | Bring and maintain a synced replica of a compatible source for analytics |
| Copies data? | Generally avoids initial data copying | Replicates and maintains mirrored data in Fabric per connector |
| Freshness | Depends on source and access path | Depends on replication/sync lag |
| Sources | OneLake/ADLS and supported shortcut targets | Databases/sources with supported mirror connectors |
| Transformation | No built-in ETL | Mirroring does not replace cleansing/semantic transforms |
| Governance | Credentials, permissions, shortcut/source lifecycle | Connections, replication health, lag, source impact |

### Azure SQL Example

Suppose an enterprise runs Azure SQL Database for OLTP. If Fabric Mirroring supports their configuration and tier, mirroring can feed analytics without writing frequent custom batch copies.

However:

- Not every Azure SQL deployment, table, or feature is eligible.
- Mirrors experience **replication lag**; never rely on them for strict transactional read-after-write.
- Assess source overhead, permissions, firewalls/private connectivity, and initial sync impact.
- Mirroring does not eliminate backups, PITR, and DR for the primary database.

### When Use Copy/Pipelines Instead of Mirroring?

When the source is unsupported, custom incremental rules are needed, complex transformations are required, or business validation gates must run before landing in Gold, choose Data Factory pipelines, Dataflows, or Notebooks.

## 15. Power BI and Semantic Models in Fabric

Power BI is a core part of the Fabric experience: building **semantic models** and reports for business users.

~~~text
Gold tables (Lakehouse/Warehouse)
               |
               v
        Power BI Semantic Model
        - relationships
        - business measures
        - row-level security when designed
               |
               v
        Power BI Report / Dashboard
               |
               v
          Business users
~~~

### What Is a Semantic Model?

It defines tables, relationships, measures, and business logic centrally so report authors do not reinvent definitions of "revenue," "canceled orders," or "active customers" in every dashboard.

Example:

~~~text
Revenue = SUM(net_sales_amount)
OrderCount = DISTINCTCOUNT(order_id)
AverageOrderValue = Revenue / OrderCount
~~~

**These are conceptual formulas**, not complete production DAX for every model. Metrics must specify taxes, refunds, cancellations, and recognition timestamps.

### Data Access Modes

Power BI supports modes including **Import**, **DirectQuery**, and **Direct Lake** in supported configurations. Understand the differences:

- **Import:** loads data into the semantic model, requiring scheduled or event-driven refreshes.
- **DirectQuery:** queries the underlying source interactively, bounded by source latency and limits.
- **Direct Lake:** designed to query OneLake/Delta data directly with performance approaching in-memory models under supported conditions.

**Direct Lake is not an unconditional real-time guarantee**, does not bypass RLS rules, and has fallback/tier limitations. When fresh data is required, design table/model updates explicitly and measure end-to-end freshness.

## 16. Real-Time Intelligence: Eventstream, Eventhouse, and KQL

Fabric provides **Real-Time Intelligence** to ingest, analyze, and visualize near-real-time events and telemetry through supported components.

~~~text
Applications / devices
          |
          v
Azure Event Hubs / supported source
          |
          v
Fabric Eventstream
  - ingest/route/transform per capabilities
          |
          v
Eventhouse / KQL database
          |
          v
KQL queries, dashboards, alerts/Activator
          |
          v
Operators / incident workflows
~~~

### Eventstream

Handles continuous event streams, connecting sources/destinations and applying supported stream transformations. **Eventstream is not synonymous with Event Hubs**: Event Hubs is Azure's broker/ingestion service with its own partitions, consumer groups, and retention; Fabric Eventstream is an analytics-platform ingestion component.

### Eventhouse and KQL Databases

Targeted at high-volume event, log, and time-series queries using **Kusto Query Language (KQL)** with optimized storage and ingestion.

### Read-Only KQL Example

Suppose a KQL database has table **`AppEvents`** with columns **`EventTime`** and **`EventType`**:

~~~kusto
AppEvents
| where EventTime >= ago(1h)
| summarize EventCount = count()
    by bin(EventTime, 5m), EventType
| order by EventTime asc
~~~

This query counts events per 5-minute bin and event type. Table and column names are illustrative. Evaluate timezones, event time vs. ingestion time, late events, and filtering/retention when building alerts.

## 17. Data Science in Fabric

Fabric includes data science experiences enabling practitioners to read OneLake/Lakehouse datasets, run notebooks, and train/track models.

A typical workflow:

~~~text
Silver data (cleaned, consented)
          |
          v
Feature engineering (Notebook/Spark)
          |
          v
Training / evaluation
          |
          v
Model/experiments per supported capabilities
          |
          v
Batch scoring / reports / downstream APIs
~~~

### Not Synonymous with Azure Machine Learning

Azure Machine Learning provides a dedicated ecosystem for training, registries, managed online endpoints, and MLOps capabilities. Fabric Data Science does not automatically replace every Azure ML feature. Choose based on production workflows, model governance, online inference latency, networking/security, and cost.

### Permissions on Training Data

Data scientists may read analytical tables, yet **never assume they are authorized to view raw PII**. Use classified datasets, consent tracking, masking, lineage, and controls over exported model artifacts.

## 18. Connecting Fabric to Azure Data Sources

| Source | Integration Options to Evaluate | Key Watchouts |
|---|---|---|
| **Azure SQL Database** | Pipelines, connectors, Mirroring if supported | Networking, source load, replication lag, credentials |
| **Azure Cosmos DB** | Connectors/Mirroring where supported | API compatibility, partitioning, RU/s, and change propagation |
| **ADLS Gen2 / Blob** | Copy/Pipeline or OneLake shortcuts | ACL/RBAC, shortcut type, path/format, cost |
| **Azure Event Hubs** | Eventstream / supported connectors | Consumer positions, streaming lag, throughput |
| **Azure Databricks** | Delta data exchange / OneLake connectors per support | Compatibility, Unity Catalog/governance, copy vs. reference |
| **Azure Functions / Logic Apps** | Pipeline orchestration / API / service integration | Authentication, rate limits, retries/idempotency |
| **Power BI** | Semantic models / reports | Licensing, Direct Lake constraints, RLS |
| **On-premises SQL** | Data gateways / supported connectors | Private connectivity, gateway capacity, security |

### Connecting Does Not Equal Copying Data

**Shortcuts** create references; **Copy activity** writes destination data; **Mirroring** maintains a synced replica; **DirectQuery** queries on demand; **Import** loads into semantic memory. Each carries distinct cost, freshness, and access-control implications.

## 19. Fabric vs. Azure Data Factory: Choosing an Orchestration Tool

**Azure Data Factory (ADF)** is a standalone Azure PaaS integration/orchestration service with pipelines, activities, and integration runtimes. **Fabric Data Factory** brings orchestration and dataflow experiences directly into Fabric.

| Scenario | Direction to Evaluate |
|---|---|
| Analytics centered inside Fabric/OneLake | Fabric pipelines / Dataflow Gen2 |
| Existing ADF running complex integrations reliably | Keep ADF or evaluate migration carefully—no forced rewrite |
| On-prem/private system connectivity | Compare gateway and network support across platforms |
| Orchestration spanning multiple Azure subscriptions | ADF or Fabric depending on connectors, identities, and requirements |
| Streamlining dataset prep for Power BI | Fabric Dataflow Gen2 often fits well |
| Reusing existing IaC/CI/CD | Compare deployment APIs, Git integration, and feature parity |

**Never import an ADF pipeline JSON expecting identical behavior in Fabric.** Activity names, runtimes, parameters, triggers, billing, and connector support can differ.

## 20. Fabric, Azure Synapse, and Azure Databricks

| Criterion | Microsoft Fabric | Azure Synapse Analytics | Azure Databricks |
|---|---|---|---|
| Focus | Unified SaaS analytics integrating Power BI and OneLake | Azure analytics suite combining Spark/SQL/pipelines per config | Databricks lakehouse/data engineering/ML platform on Azure |
| Governance plane | Fabric tenant/capacity/workspaces/items | Azure resources/workspaces/pools | Azure workspaces/compute and platform governance |
| Spark | Fabric Spark notebooks/experiences | Synapse Spark pools | Databricks clusters, SQL, and ML features |
| SQL | Fabric Warehouse / Lakehouse SQL endpoint | Dedicated and serverless SQL pools | Databricks SQL / lakehouse tables |
| BI | Deeply integrated Power BI | External BI connections | Connects to Power BI and other BI tools |
| Data lake | OneLake / shortcuts | ADLS Gen2 and integrated data lake | Delta Lake in cloud storage per architecture |
| Pricing | Fabric capacity + storage/licensing | Per-service / per-compute-pool billing | DBUs + compute/cloud storage per model |
| When to choose | Consolidating workloads and BI collaboration | Existing Synapse workloads / aligned requirements | Deep Spark/ML platform and Databricks-specific features |

### Avoid the Wrong Question: "Which Tool Is Always Best?"

For example, a company already running Databricks cleanly with governed Delta tables on ADLS can keep Databricks for data engineering and use **Fabric/Power BI** for reporting via supported integrations. There is no requirement to rewrite every Spark job into Fabric just to benefit from OneLake or semantic models.

### Do Not Mistake Fabric for Simply Rebranded Power BI

Power BI is a cornerstone workload, yet Fabric also spans ingestion, Spark, Lakehouse, Warehouse, and Real-Time Intelligence. Conversely, not every Power BI user needs to adopt every Fabric workload.

## 21. End-to-End Architecture: Retail Application on Azure and Fabric

Suppose an enterprise has three sources:

- **Azure SQL Database:** orders, order lines, and customers.
- **ADLS Gen2:** product files and historical transactions in Parquet/CSV.
- **Azure Event Hubs:** continuous clickstream and telemetry.

A proposed architecture:

~~~text
        Azure SQL Database          ADLS Gen2             Event Hubs
                 |                     |                      |
                 | Mirroring/Copy      | Shortcut/Copy        | Eventstream
                 v                     v                      v
         +-----------------------------------------------------------+
         |                     Microsoft Fabric                      |
         |                                                           |
         |  OneLake / Lakehouse               Eventhouse             |
         |    Bronze raw data                     |                   |
         |         |                              | KQL/aggregation   |
         |         v                              v                   |
         |    Notebook Spark / Dataflow Gen2   Realtime insights     |
         |         |                              |                   |
         |         v                              |                   |
         |    Silver validated                    |                   |
         |         |                              |                   |
         |         v                              |                   |
         |    Gold facts/dimensions <--------------+                   |
         |         |                                                  |
         |         v                                                  |
         |    Warehouse / Lakehouse SQL endpoint                     |
         |         |                                                  |
         |         v                                                  |
         |    Semantic model -> Power BI report                       |
         +-----------------------------------------------------------+
                                |
                                v
                   Data consumers / business users
~~~

### Architectural Boundaries

1. **Azure SQL** stays the OLTP system of record; never force the website to write orders straight into an analytical Warehouse.
2. **Event Hubs** handles event ingestion; Fabric Eventstream/Eventhouse handles consumption and analytics via supported integrations.
3. **ADLS/OneLake** stores files and Delta tables, choosing shortcuts vs. copies around permissions and needs.
4. **Silver/Gold** establish trustworthy business semantics rather than merely renaming tables.
5. **Semantic models** standardize metrics, relationships, and viewer permissions.
6. **Monitoring and governance** span every tier rather than stopping at "pipeline succeeded."

## 22. Why Distinguish OLTP from OLAP?

**OLTP (Online Transaction Processing)** serves high-concurrency short transactions like placing orders, decrementing inventory, and updating statuses. **OLAP (Online Analytical Processing)** serves multi-dimensional scans and historical aggregations.

| Criterion | Azure SQL Database for OLTP | Fabric Lakehouse/Warehouse for OLAP |
|---|---|---|
| Goal | Low-latency operational transactions | Large-scale dataset analytics and aggregations |
| Query pattern | Point lookups, transactional writes/updates | Multi-table scans, aggregations, and joins |
| Load | Many concurrent short transactions | Batch, analytical, and BI concurrency |
| Consistency | Database transactional semantics | Governed by engine/table format and pipeline freshness |
| System of record | Typically the transactional system | Analytical copy for reporting |
| Usage | REST APIs, checkout, inventory | Dashboards, behavioral analytics, reporting |

**Fabric Warehouse is not a direct replacement for a payment backend requiring fast transactions.** When reporting queries slow down Azure SQL, offload analytical workloads into Fabric instead of letting hundreds of BI queries scan transactional tables.

### Data Freshness Expectations

A revenue report fed by mirroring or batch ingestion can **lag** behind newly committed orders. Stakeholders must know:

- Acceptable delay (freshness SLO).
- When source records were committed vs. when analytics updated.
- Which tables update real-time, near-real-time, or batch.
- Whether dashboards surface "stale data" warnings when pipelines fail.

## 23. Full Load, Incremental Load, and CDC Ingestion

Initial loads differ from daily incremental updates:

| Ingestion Pattern | Goal | Risks |
|---|---|---|
| **Full load** | Extract the entire source dataset | Slow, costly, risks overloading source |
| **Incremental timestamp/watermark** | Read only new/updated rows via timestamp column | Misses late arrivals or suffers from untrusted timestamps |
| **Change Data Capture (CDC)** | Track log-based changes per supported connector | Permission issues, log retention, ordering, schema shifts |
| **Mirroring** | Maintain a near-source replica via connector | Sync lag, source compatibility, initial sync load, permissions |
| **Eventstream** | Consume continuous event streams | Duplicate events, late events, streaming backpressure |

### Watermarks Are Not Always Enough

~~~text
Last watermark = 10:00
Record A written to source at 10:01 -> ingested cleanly
Record B arrives late at 10:05 with business timestamp 09:59

If filtering strictly timestamp > 10:00:
  Record B may be skipped.
~~~

Mitigations include overlap windows, business-key deduplication, change tracking/CDC, or supported log-based ingestion.

### Full Load and CDC Must Hand Off Cleanly

Running an initial full copy alongside a change stream without a precise cutover watermark risks duplicate or missing events. That is a **data correctness problem**—never something a larger Fabric capacity fixes automatically.

## 24. Designing Re-Runnable Ingestion Pipelines

A sound pipeline must be **idempotent and restartable**:

~~~text
Run ID: orders-2026-11-20-08
      |
      v
Read source data for window
      |
      v
Validate source schema/row counts
      |
      v
Write staging or Bronze partition
      |
      v
Transform/Deduplicate into Silver
      |
      v
Publish Gold data
      |
      v
Update run watermark/status after commit
~~~

### If a Mid-Pipeline Step Fails

Suppose Copy wrote 100,000 rows to Bronze, and the Silver Notebook fails. Retrying from scratch with an **uncontrolled `append`** risks doubling Bronze. Prefer:

- Keying processing by **`run_id`**.
- Deduplicating by source operation ID.
- Upserting/`MERGE`-ing into Delta tables where cleanly supported.
- Writing to staging and promoting only after verification.
- Advancing watermarks only after outputs commit durably.

### Do You Need Exactly-Once?

Never promise end-to-end exactly-once merely because an activity has retries. Moving from Azure SQL through Copy/Mirror, Spark, and semantic models crosses multiple commit boundaries. **At-least-once ingestion + idempotent transforms** is usually the practical pattern, verified by tests.

## 25. Data Quality Is Part of the Pipeline

Critical questions:

- Are any `order_id`s null or duplicated?
- Is an amount negative due to a valid refund or corrupted data?
- Are currencies and timezones normalized?
- Are customers erased under privacy requests still lingering in raw files?
- Did late records arrive after Gold aggregation ran?
- Do processed order counts reconcile with source totals?

### Example Validation Rules

| Rule | Dimension | Action |
|---|---|---|
| `order_id` is not null | Completeness | Quarantine records missing keys |
| `amount` valid in business context | Validity | Log errors; do not blindly drop negative refunds |
| `order_id + source_event_version` unique | Uniqueness | Deduplicate per contract |
| `currency` is a supported code | Validity | Check against reference lookup |
| `order_date` not unreasonably in the future | Timeliness | Quarantine or flag for review |
| Gold totals reconcile with source | Accuracy | Block publishing if variance exceeds threshold |

**Dataflow Gen2/Spark does not make data clean merely because a pipeline finished.** Every transform stage needs explicit quality assertions and metrics.

## 26. Timezones, Currencies, and Event Time

In global apps, order timestamps are typically stored in UTC and displayed per user locale. Grouping Gold tables by local dates without timezone awareness skews daily revenue.

~~~text
Source event:
  2026-11-20T23:45:00Z

Business timezone UTC+7:
  2026-11-21 06:45

UTC date = 20/11
Local business date = 21/11
~~~

### Definitions to Standardize

- **Event time:** when the business event occurred at the source.
- **Ingestion time:** when the pipeline received the data.
- **Processing time:** when transformations executed.
- **Business date:** calendar date in the organization's accounting timezone.

Select the right time field in fact tables, semantic measures, and dashboards. For streaming, handle late events explicitly rather than treating arrival order as business order.

## 27. Security: Microsoft Entra ID and Fabric Access Control

A Fabric architecture spans multiple authorization layers:

~~~text
Microsoft Entra ID
       |
       v
Fabric tenant / workspace roles
       |
       +-- Item permissions
       |
       +-- OneLake data permissions / roles per capability
       |
       +-- Warehouse / SQL security
       |
       +-- Power BI semantic model permissions/RLS
       |
       v
External Azure sources
       |
       +-- Azure SQL identity/SQL permissions
       +-- ADLS Gen2 RBAC/ACL
       +-- Event Hubs consumer rights
~~~

### Each Layer Answers a Different Question

| Layer | Example Question |
|---|---|
| **Tenant administration** | Who can create/share items or use external sharing? |
| **Workspace role** | Who can create, edit, or view items inside a workspace? |
| **Item permissions** | Who can read, execute, or modify a specific Lakehouse, Warehouse, or Pipeline? |
| **OneLake data access** | Who can read data within a scoped OneLake path? |
| **SQL security** | Who can `SELECT`/`UPDATE` tables, columns, or rows in the SQL endpoint? |
| **Semantic model RLS/OLS** | Which data subset can a report viewer see? |
| **Azure source authorization** | Which databases or containers can the Fabric connection read? |

### Do Not Treat All Fabric Roles Alike

Workspace roles—**Admin, Member, Contributor, Viewer**—grant distinct capabilities. Effective data access also hinges on item grants, SQL/OneLake security, and sharing/build permissions. **A Viewer of a report does not inherently gain access to raw PII**; verify and restrict this explicitly by design.

### Principles

1. Use Entra groups instead of individual assignments wherever possible.
2. Isolate dev/test/prod permissions.
3. Classify PII before permitting shortcuts or exports.
4. Restrict who can modify connection credentials.
5. Never grant broad workspace Admin just to fix a permission error.
6. Test access using **genuinely low-privilege test accounts**.

## 28. OneLake and Shortcut Trust Boundaries

A shortcut to ADLS does not automatically make source data public. Evaluate:

- Who is permitted to create shortcuts?
- Which identity or credential does the connection use?
- Who holds permissions on the shortcut as a Fabric item?
- What ACLs/RBAC govern the external source?
- Does the connection use a service principal, workspace identity, or user credentials?
- If the shortcut creator leaves the company, does the connection break?
- Could another OneLake path expose data while bypassing SQL or Power BI controls?

### Risk Example

~~~text
Power BI Report enforces strict RLS
       |
       v
User sees only tenant-A data

Yet the same user holds direct read access to Lakehouse raw Files
       |
       v
User can view multiple tenants unless raw access is restricted
~~~

**Semantic-model RLS does not replace permissions on OneLake, Files, or SQL endpoints.** For sensitive data, evaluate every access path independently.

## 29. Microsoft Purview, Lineage, and Data Governance

Governance answers:

- Which sources produced this Gold table?
- Who owns the revenue definition?
- Which reports break if a column is renamed?
- Which datasets contain PII?
- Who accessed, shared, or exported data?
- Is data retained according to policy?

**Fabric** offers built-in lineage/discovery features and integrates with **Microsoft Purview**, subject to licensing, configuration, and feature scope. Never assume every table, shortcut, pipeline, or external source gets **complete automatic lineage** out of the box. Verify captured metadata and document gaps manually.

### Minimum Metadata Set

| Field | Example |
|---|---|
| Dataset owner | Data Platform Team |
| Business owner | Finance |
| Source | Azure SQL orders |
| Update cadence | Every 15 minutes |
| Freshness SLO | Data age under 30 minutes |
| Sensitivity | Confidential / contains PII? |
| Retention | Per corporate policy |
| Quality checks | Row count, duplicate rate, reconciliation |
| Downstream | Revenue semantic model/report |

Data governance is an **ongoing discipline**, not merely slapping "Gold" onto a table name.

## 30. Private Networking and Enterprise Data

Because Fabric is SaaS, how it reaches resources inside your VNet differs from a VM or AKS pod running inside a subnet you manage directly.

### Connectivity Paths to Evaluate

- Public endpoints restricted by firewall/IP policies.
- **On-premises data gateway** when sources sit on internal networks.
- **VNet data gateway** or Fabric-supported private network integrations.
- **Managed private endpoints / Private Link** or workload-specific network integrations per tier.
- Workspace identity or service principals where supported by connectors.

**Never assume all Fabric workspaces run inside your VNet**, or that creating a single Azure Private Endpoint lets every Notebook, Dataflow, Mirroring job, Eventstream, and SQL connector traverse that exact path.

### Verification Workflow

1. Identify the exact **Fabric workload/connector** accessing the source.
2. Check which network options that workload supports.
3. Verify authentication identities, source firewalls, and private DNS.
4. Test from the actual Fabric activity/notebook, not just a personal laptop.
5. Inspect which regions and network paths traffic traverses.
6. Document compliance constraints and whether data may cross regions.

### Dangerous Workarounds to Avoid

If a pipeline hits connection failures, never open Azure SQL or Storage public network access to **all of the Internet** or grant unrestricted admin privileges. Separate **DNS/network/TLS** failures from **authentication/RBAC/SQL permission** errors first.

## 31. Data Residency, Regions, and Compliance

A Fabric capacity is pinned to a **region/geography** upon selection, while external sources like Azure SQL and ADLS reside in their own regions. Cross-region access impacts:

- Network latency and bandwidth.
- Data transfer and egress costs.
- Data residency and sovereignty.
- Corporate PII/export policies.
- Availability and recovery during regional outages.

### Example to Check

Suppose ADLS sits in one Azure region and Fabric capacity sits in another. A OneLake shortcut avoids copying data upfront, **yet does not stop queries from reading across regions or incurring egress**. When mirroring or copying data, verify where physical replicas live.

Never declare an architecture "locally compliant" merely because the service carries the Azure name. Verify the **regions of compute, storage, caches, logs, backups, and network paths** under current terms.

## 32. Fabric Capacity and Compute Units (CU)

Fabric uses capacities to pool compute budgets across workloads. Capacities using **F SKUs** are managed under Azure in supported configurations, with throughput measured in **Compute Units (CU)**. Workspaces attach to capacities per tenant licensing models.

~~~text
                     Fabric Capacity (F SKU)
                              |
                 Shared compute capacity budget
                              |
           +------------------+------------------+
           |                  |                  |
           v                  v                  v
       Spark notebook      Warehouse SQL    Power BI queries
           |                  |                  |
           +---------+--------+------------------+
                     |
                     v
              Capacity utilization
                     |
              Throttling if overloaded
              per service policy
~~~

### A CU Is Not One CPU Core

**CU** is an internal capacity/billing unit for Fabric operations under service rules. You cannot map **1 CU = 1 Azure VM vCore** or a fixed queries-per-second number. Spark, Warehouse, Power BI, and pipelines each have distinct consumption profiles.

### What to Monitor

- Overall capacity utilization and usage by workload/item.
- Background operations vs. interactive queries.
- Throttling, delays, or rejections under capacity policies.
- Overlapping peaks among Spark batches, Warehouse ETL, and Power BI refreshes.
- Impact of splitting capacities or staggering schedules.

**A workspace running smoothly when no notebooks are active does not prove capacity will handle peak concurrent report refreshes.**

## 33. Throttling and Capacity Planning

Capacities can experience load pressure when demand exceeds budgets, governed by Fabric's smoothing and throttling mechanics. Never assume a single heavy query halts everything instantly, nor assume the system scales upward infinitely for free.

### Conflicting Load Example

~~~text
08:00  Warehouse loads Gold tables
08:05  40 Power BI reports refresh/query interactively
08:10  Spark notebook runs a two-month backfill
08:15  Eventhouse ingests continuous streams

If capacity is undersized:
  Interactive report latency can climb,
  background jobs may be delayed,
  and requests may be throttled.
~~~

### How to Handle It

1. Measure daily utilization, separating interactive vs. background load.
2. Stagger batch and refresh schedules to reduce overlap.
3. Optimize Spark jobs, SQL queries, and semantic model footprints.
4. Cut unnecessary copies/scans and use partitioning.
5. Isolate critical workloads onto dedicated capacities where justified and permitted.
6. Scale F SKUs only after benchmarking and cost modeling.
7. Maintain alerts, budgets, and runbooks for capacity overload.

**Never upgrade an F SKU to mask a pipeline duplicating data on retries.** Fix correctness first.

## 34. OneLake Storage and Total Cost

A Fabric platform involves distinct cost components to evaluate separately:

| Component | What to Account For |
|---|---|
| **Fabric capacity** | Provisioned or billed F SKU/compute per purchasing model |
| **OneLake storage** | Stored data, copies, files, tables, retention, and storage tier pricing |
| **External Azure storage** | Source ADLS/Blob storage, transactions, and egress if applicable |
| **External Azure compute** | Azure SQL, Databricks, Event Hubs, and Functions bill separately |
| **Data movement** | Pipeline copies, mirroring, gateways, and network operations per features |
| **Power BI licensing** | Rights to author, share, and view reports per current Fabric capacity and license rules |
| **Monitoring/governance** | Logs, retention, Purview, and integrated services |
| **Operations** | Support, engineering, quality checks, and DevOps |

### Never Confuse Capacity with Storage

Holding a Fabric capacity does not make OneLake storage unlimited or free. Conversely, pausing a capacity per supported options does not delete data or stop storage billing.

### Estimation Process

1. Estimate source TB volume and growth rate.
2. Determine physical copies, mirroring, shortcuts, and retention.
3. Estimate batch/streaming schedules, Spark, Warehouse, and Power BI query volumes.
4. Pick candidate F SKUs from benchmarks.
5. Add external Azure charges, networking/egress, and user licensing.
6. Use the **Azure Pricing Calculator** and **Fabric Capacity Metrics** during trials.
7. Audit actual bills, tuning workloads and capacity continuously.

**Never quote a fixed USD/CU unit price** since regions, SKUs, purchasing programs, and price sheets vary. Calculate costs under real deployment conditions.

## 35. Power BI Licensing and Report Viewers

A common deployment trap: the team buys a Fabric capacity and assumes **everyone can view every Power BI report without licenses or permissions**.

Rights to author, share, and view Power BI content can depend on:

- Power BI Pro, Premium Per User, or other licenses.
- Supported Fabric capacity size/tier.
- Workspace, item, and semantic model permissions.
- How reports are shared, embedded, or shared externally.
- Tenant-level settings.

### Questions Before Publishing

1. Who authors reports, and who views them?
2. Which licenses do viewers hold?
3. Is the workspace hosted on a capacity supporting the required sharing/viewing model?
4. Do tenant policies permit external B2B viewers?
5. Are RLS/OLS or export/download restrictions required?
6. Do gateways, Direct Lake, or DirectQuery cause viewers to touch external sources?

**Do not apply a single rigid licensing assumption across all F SKUs**, as entitlements depend on product policy and capacity tier. Check Microsoft Learn and your enterprise agreements prior to rollout.

## 36. Monitoring Pipelines and Data via Metrics

| Layer | What to Monitor | Risk If Ignored |
|---|---|---|
| Source | Data freshness, source errors, schema changes | Unnoticed stalled upstream feeds |
| Ingestion | Rows/files/events ingested, retries, duration | Missing or duplicated data |
| OneLake | Storage growth, file sizes, schema evolution | Degraded performance and runaway costs |
| Spark | Job durations, failures, skew, shuffles | Overloaded compute |
| Warehouse | Query latency, concurrency, failed ops | Sluggish BI and throttling |
| Eventhouse | Ingestion lag, query latency, retention | Stale real-time dashboards |
| Semantic model | Refresh status, relationships, RLS | Broken metrics or wrong reports |
| Capacity | CU utilization, throttling, per-item consumption | Noisy-neighbor workload starvation |
| Security | Permission changes, unexpected sharing | Data leakage |
| Cost | Fabric + external Azure bills | Uncontrolled TCO |

### A Freshness SLO

~~~text
Order committed in Azure SQL at 10:00.
Report must reflect it before 10:15.

Freshness SLO:
  95% of valid orders appear in Gold/semantic view
  within 15 minutes of source commit.
~~~

This is an **illustrative SLO**, not a Fabric guarantee. Measuring it requires logging source commit timestamps, ingestion timestamps, transformation completion, and report visibility times.

### Technical Success Differs from Business Success

A pipeline showing **Succeeded** does not prove:

- Revenue totals are right.
- Zero records were dropped.
- Zero PII leaked.
- Reports refreshed cleanly.
- Semantic measures match finance definitions.

Verify with **row-count reconciliations**, data quality rules, spot audits, and business-level metrics.

## 37. CI/CD, Git Integration, and Multi-Environment Deployments

Fabric provides **Git integration, deployment pipelines, and REST APIs** for supported artifacts and workloads.

~~~text
Developer changes
       |
       v
Git repository (supported metadata/code)
       |
       v
DEV Fabric workspace
  - notebooks
  - pipeline definitions
  - semantic models/reports
       |
       v
Test/validation
       |
       v
TEST workspace
       |
       v
Approval + release
       |
       v
PROD workspace
~~~

### What to Separate

- **Code/metadata** for pipelines, notebooks, and reports.
- **Data** inside OneLake and warehouses.
- **Connections, credentials, and identities** per environment.
- **Capacities** and workspace assignments.
- **Permissions** and tenant policies.

Never assume clicking Deploy Pipeline automatically migrates data, copies secrets, or grants user permissions. Verify supported item types and workload-specific **deployment rules**.

### Production Rules

1. Never use raw production data arbitrarily as dev fixtures.
2. Use distinct identities and external sources per environment wherever possible.
3. Test notebook/pipeline outputs and reconciliation numbers.
4. Keep artifact rollbacks and data recovery plans for schema changes.
5. Version schemas, queries, semantic measures, and dashboard definitions.
6. Re-verify permissions and connections after every deployment.

## 38. Backup, Recovery, and Data Retention

OneLake, Warehouse, Lakehouse, shortcuts, and mirrored data **do not automatically share one uniform backup/restore model**. Define recovery capabilities per item type and source.

### RPO/RTO Questions

- If a notebook writes bad Silver data, which version can you roll back to?
- If a Lakehouse table is deleted accidentally, can it be restored and how fast?
- If an external ADLS source is deleted, does the shortcut still hold data?
- If a mirrored table lags or corrupts, how do you resync or backfill?
- If a semantic model is deployed wrongly, can you roll back versions?
- If a region or capacity suffers an outage, what recovery workflow is supported?

### Separate Three Recovery Layers

1. **Origin sources:** Azure SQL, Cosmos DB, and ADLS have their own backup, PITR, and DR.
2. **Fabric data:** retention, versioning/time travel, and restore mechanics per item/table.
3. **Artifacts/code:** Git/deployment history and configuration documentation.

**A Lakehouse raw table is an analytical copy, never a substitute for tested Azure SQL backups**, and a shortcut creates no snapshot preserving source data.

## 39. Performance: Avoiding Scanning Too Much Data

Common drivers of excessive capacity burn:

- Spark scanning entire huge tables every run instead of incremental loads.
- Producing millions of tiny files that stall metadata scans.
- Joining massive tables without aligned partitioning.
- Warehouse/BI queries scanning raw records instead of Gold aggregates.
- Duplicate schedules triggering Dataflows/Notebooks concurrently.
- Reports refreshing continuously when source data updates only once a day.
- Missing partition pruning or early predicate pushdown.

### Best Practices

- Use incremental ingestion and idempotent `MERGE` where appropriate.
- Partition/cluster tables around real access patterns.
- Reduce file fragmentation using Fabric-supported table optimizations.
- Project only needed columns and rows.
- Separate raw/clean/Gold layers to avoid repeating heavy logic.
- Measure Spark/Warehouse/BI queries and per-item CU consumption.
- Verify accuracy before and after every performance tweak.

Never run **`OPTIMIZE`/`VACUUM`/`DELETE`** on production data merely from generic advice; check engine support, transactions, retention, and backups first.

## 40. Lab A: Creating a Sample Lakehouse and Gold Table

**Goal:** understand the Files → Delta table → SQL → report flow in Fabric. This lab uses synthetic data and runs only in an **authorized test Fabric workspace/capacity**.

### Prerequisites

1. Assigned a lab workspace or permission to create one.
2. Workspace attached to an appropriate capacity/trial for needed features.
3. Permissions to create a Lakehouse, Notebook, and inspect the SQL analytics endpoint.
4. Zero customer data or files containing PII.
5. Approved budget and cleanup instructions.

### Steps

1. In Fabric, select the lab workspace.
2. Create a **Lakehouse**, e.g., **`sales_lab`**.
3. Upload a synthetic CSV into **`Files/landing/orders.csv`**.
4. Create a Notebook and attach the lab lakehouse.
5. Use the PySpark snippet in Section 11 to populate **`bronze_orders_lab`**.
6. Build Silver/Gold transformations:
   - Validate `amount` and `order_id`.
   - Sum totals by date or customer segment.
   - Deduplicate by unique business key.
7. Confirm the Delta tables appear in the Lakehouse.
8. Query via the SQL analytics endpoint using **`SELECT`**—do not attempt arbitrary DML.
9. If licensed/permitted, build a semantic model and report from the Gold table.
10. Record notebook runtime, source/target row counts, and capacity consumption.

### Read-Only SQL Example on an Assumed Gold Table

~~~sql
SELECT
    order_date,
    COUNT(*) AS order_count,
    SUM(amount) AS gross_amount
FROM dbo.gold_orders_lab
GROUP BY order_date
ORDER BY order_date DESC;
~~~

If actual schema/table names are not under **`dbo`**, adjust to match the endpoint. Do not assume the Notebook in Step 5 created the Gold table—Step 6 creates Gold after standardization.

### Acceptance Criteria

| Check | PASS When |
|---|---|
| Workspace | Correct lab workspace and capacity |
| Files | Synthetic CSV is readable |
| Notebook | Succeeds, logging run ID and row counts |
| Delta | Table exists in the right Lakehouse |
| Schema | `order_id`/`amount` match expected types |
| Quality | Zero unintended duplicates |
| SQL | `SELECT` reads supported tables cleanly |
| Report | Metrics match SQL; viewer permissions scoped properly |
| Cost | Compute/capacity usage observed |
| Cleanup | Lab items removed per authorization/approval |

## 41. Lab B: Using Shortcuts Instead of Copying

**Goal:** distinguish OneLake shortcut referencing permissions from physical copying.

### Preparation

- An approved lab ADLS Gen2 container holding sample tables/files.
- Supported external source connection.
- Identity/connection holding read permissions on the target scope.
- A lab workspace Lakehouse.

### Steps

1. In the Lakehouse, create a shortcut to the lab ADLS folder per supported UI/features.
2. Confirm the shortcut appears under `Files` or `Tables` depending on source type.
3. Read a file/table from a Notebook via the Fabric-provided path.
4. Compare against Copy activity: Copy materializes bytes at destination; shortcuts reference the source path via the connector.
5. Revoke read permission **in the lab environment** and observe behavior/errors if permitted.
6. Evaluate latency, data egress, access logs, and ownership.

### What Must Not Be Inferred

- Creating a shortcut does not automatically grant read rights to every Fabric viewer.
- Shortcuts are not backups.
- Not every external file automatically appears as a Delta table.
- Shortcuts do not prove data residency compliance without checking actual read/copy paths.

### Question

Why must an organization requiring data never to leave its ADLS region still evaluate **network paths and external processing** before enabling shortcuts?

## 42. Lab C: Event Hubs to Real-Time Intelligence

**Goal:** recognize boundaries between Azure ingestion and Fabric analytics.

~~~text
Telemetry producer (lab)
       |
       v
Azure Event Hubs
       |
       v
Fabric Eventstream (supported connector)
       |
       v
Eventhouse / KQL Database
       |
       v
Read-only KQL / dashboard
~~~

### Workflow

1. Prepare an authorized lab Event Hubs namespace and event hub.
2. Verify RBAC/credentials for the connector reading events.
3. Create a Fabric Eventstream with a supported Event Hubs source.
4. Select an authorized Eventhouse/KQL destination.
5. Emit a few synthetic events with timestamps and event types from a lab producer.
6. Inspect ingestion status and lag; query via KQL as in Section 16.
7. Test a schema change with a malformed lab event, observing errors/quarantine.
8. Stop ingestion cleanly and check cleanup/costs.

### Questions to Answer

- Does producer send success prove Eventhouse received the event?
- Does Fabric Eventstream retain event history identically to Event Hubs consumer group retention?
- Where can delays occur between emitted events and KQL visibility?
- If Eventhouse is paused, what retention and connection mechanics govern replay/recovery?

Never run high-rate producers against unbudgeted Event Hubs or Fabric capacities; a handful of synthetic records suffices to validate the pipeline path.

## 43. Architecture Scenario: E-Commerce Enterprise

An enterprise operates:

- Azure SQL Database as OLTP for orders.
- Azure Cosmos DB storing behavioral/cart events.
- ADLS Gen2 storing historical files.
- Azure Event Hubs ingesting 20 million click events/day.
- Analytics team wanting revenue reports every 15 minutes.
- Operations team wanting clickstream anomaly alerts within minutes.
- ML team wanting weekly demand forecasts.
- Security requiring PII readable only by approved teams.
- Existing Power BI, Azure Databricks, and several ADF pipelines.

### Tasks

1. Classify data sources across OLTP, lake files, and streaming.
2. Select Fabric components suited to each analytical need.
3. Design Azure SQL → Fabric via Copy or Mirroring depending on source support.
4. Explain when OneLake shortcuts fit ADLS vs. when copies/transforms are required.
5. Design Bronze/Silver/Gold covering watermarks, deduplication, timezones, and currencies.
6. Explain how to meet the 15-minute freshness SLO and measure errors.
7. Use Eventstream/Eventhouse/KQL for near-real-time alerts.
8. Design the revenue semantic model and report access controls.
9. Recommend which workloads should stay in Azure Databricks rather than migrating immediately.
10. Design workspaces and capacities across dev/test/prod.
11. Specify how to reach Azure SQL/ADLS over approved network policies.
12. Evaluate CU/capacity, OneLake storage, Azure sources, and Power BI licensing.
13. Design a recovery workflow if a Silver pipeline introduces duplicate rows.
14. List metrics for ingestion, Gold freshness, report availability, and cost.
15. Propose tests using low-privilege accounts confirming zero PII leakage.

### Suggested Solution Direction

~~~text
Azure SQL + ADLS + Cosmos DB --> Fabric pipeline/mirror/shortcut
                                          |
                                          v
                                 Bronze Lakehouse
                                          |
                                          v
                             Silver validated Delta tables
                                          |
                                          v
                              Gold Warehouse / Lakehouse
                                          |
                                          v
                             Power BI semantic model/report

Event Hubs --> Fabric Eventstream --> Eventhouse --> KQL / alerts

Gold/Silver data --> Fabric Notebook or Databricks/ML workflow
~~~

This is a **candidate direction for evaluation**, not the single universal architecture. Final choices hinge on quotas, IAM, connectors, latency, regions, features, team skills, and TCO.

## 44. Production Readiness Checklist for Fabric

| Area | What to Verify |
|---|---|
| Purpose | Clear data problems Fabric solves—not adopted merely because it is new |
| System of record | OLTP sources keep their role; pipelines never disrupt live transactions |
| Tenant/capacity | Tenant settings, F SKUs, and capacity assignments aligned |
| Workspaces | Dev/test/prod separated with clear owners and roles |
| OneLake | Sources, storage growth, Files/Tables layout, and permissions governed |
| Shortcuts | Right connectors, identities, data residency, and never treated as backups |
| Mirroring | Source support, lag, initial sync, and source load verified |
| Data Factory | Pipeline dependencies, retries, watermarks, and idempotency |
| Spark/Notebooks | Runtime versions, schemas, quality gates, and compute usage |
| Warehouse | SQL feature support, data model, and query latency |
| Real-time | Eventstream/Eventhouse ingestion lag and retention |
| Semantic models | Standardized metrics, Direct Lake compatibility, RLS/OLS |
| Identity | Entra groups, managed/workspace identities, and least privilege |
| External sources | Azure SQL/ADLS/Event Hubs permissions, networking, and DNS |
| Data governance | Catalog, lineage, classification, owners, and retention |
| Data privacy | PII masking/access controls, sharing/export restrictions |
| Regions | Data residency, network egress, and regional recovery |
| CI/CD | Git/deployment support, parameterization, secrets, and rollbacks |
| Monitoring | Quality/freshness, capacity throttling, query/refresh failures |
| Cost | Capacity + OneLake + external Azure resources + licensing |
| DR | Data restoration, replay/backfills, and tested runbooks |
| Training | Operations team understands Fabric SaaS vs. Azure PaaS differences |

## 45. Self-Check Questions

1. Is Microsoft Fabric SaaS or an Azure VM?
2. Why isn't Fabric synonymous with just Power BI?
3. What is OneLake—is it a single Azure subscription holding all blobs?
4. Distinguish Fabric capacity, workspace, and item.
5. How does a CU differ from an Azure VM vCore?
6. What needs do Files and Tables in a Lakehouse address?
7. What benefits does Delta Lake provide over raw CSV?
8. How does a Lakehouse SQL analytics endpoint differ from a Warehouse SQL endpoint in write capabilities?
9. Should a checkout API execute all OLTP transactions directly against Fabric Warehouse?
10. How do Data Factory pipelines differ from Dataflow Gen2?
11. Should Spark notebooks run on every tiny table of a few dozen rows?
12. What are the responsibilities of Bronze, Silver, and Gold?
13. When can OneLake shortcuts replace copying?
14. Do shortcuts guarantee an immutable backup?
15. How does Mirroring differ from shortcuts and Copy activity?
16. Does Mirroring guarantee reports always reflect the very latest committed transaction?
17. Which sessions/users can read external shortcuts, and where must permissions be checked?
18. How does Fabric Eventstream differ from Azure Event Hubs?
19. Which data suits Eventhouse / KQL Databases?
20. What problem does KQL `summarize by bin` solve?
21. What advantages do semantic models provide over reporting directly on raw tables?
22. How do Direct Lake, DirectQuery, and Import differ?
23. Does Power BI RLS automatically protect raw OneLake Files?
24. Why doesn't a pipeline reporting Succeeded guarantee Gold data is accurate?
25. How can a simple timestamp watermark miss late-arriving events?
26. Why can retrying an append into Bronze duplicate data?
27. What differences must be evaluated when moving from ADF to Fabric Data Factory?
28. Must Fabric replace a smoothly operating Azure Databricks platform?
29. Do Fabric capacity and OneLake storage share the exact same billing model?
30. Why doesn't holding an F SKU automatically make Power BI viewing free for all users?
31. What factors trigger Fabric capacity throttling?
32. Should heavy Spark backfills run during peak reporting hours?
33. Which authorization questions do Entra ID tenants vs. workspace roles answer?
34. Can you assume Fabric reaches every private Azure SQL/ADLS resource inside a VNet automatically?
35. Why do shortcuts still require evaluating data residency and network egress?
36. Why can't a Lakehouse mirror replace Azure SQL backups?
37. How do you design a backfill pipeline after duplicate data occurs?
38. Which timestamps must be measured for a 15-minute report freshness SLO?
39. Which metrics distinguish a slow Spark query from capacity throttling?
40. In the retail architecture, would you keep transactional data in Azure SQL or move everything into Warehouse, and why?

## References

- Microsoft Learn — *What is Microsoft Fabric?*: https://learn.microsoft.com/fabric/fundamentals/microsoft-fabric-overview
- Microsoft Learn — *Fabric terminology*: https://learn.microsoft.com/fabric/fundamentals/fabric-terminology
- Microsoft Learn — *OneLake overview*: https://learn.microsoft.com/fabric/onelake/onelake-overview
- Microsoft Learn — *OneLake shortcuts*: https://learn.microsoft.com/fabric/onelake/onelake-shortcuts
- Microsoft Learn — *Lakehouse overview*: https://learn.microsoft.com/fabric/data-engineering/lakehouse-overview
- Microsoft Learn — *SQL analytics endpoint*: https://learn.microsoft.com/fabric/data-engineering/lakehouse-sql-analytics-endpoint
- Microsoft Learn — *Fabric Data Warehouse overview*: https://learn.microsoft.com/fabric/data-warehouse/data-warehousing
- Microsoft Learn — *Data Factory in Fabric*: https://learn.microsoft.com/fabric/data-factory/data-factory-overview
- Microsoft Learn — *Dataflow Gen2*: https://learn.microsoft.com/fabric/data-factory/dataflows-gen2-overview
- Microsoft Learn — *Fabric notebooks*: https://learn.microsoft.com/fabric/data-engineering/how-to-use-notebook
- Microsoft Learn — *Medallion architecture in Fabric*: https://learn.microsoft.com/fabric/onelake/onelake-medallion-lakehouse-architecture
- Microsoft Learn — *Mirroring in Fabric*: https://learn.microsoft.com/fabric/database/mirrored-database/overview
- Microsoft Learn — *Real-Time Intelligence overview*: https://learn.microsoft.com/fabric/real-time-intelligence/overview
- Microsoft Learn — *Eventstream overview*: https://learn.microsoft.com/fabric/real-time-intelligence/event-streams/overview
- Microsoft Learn — *Eventhouse overview*: https://learn.microsoft.com/fabric/real-time-intelligence/eventhouse
- Microsoft Learn — *Power BI Direct Lake*: https://learn.microsoft.com/fabric/fundamentals/direct-lake-overview
- Microsoft Learn — *Fabric capacity overview*: https://learn.microsoft.com/fabric/enterprise/licenses
- Microsoft Learn — *Fabric Capacity Metrics*: https://learn.microsoft.com/fabric/enterprise/metrics-app
- Microsoft Learn — *Fabric security overview*: https://learn.microsoft.com/fabric/security/security-overview
- Microsoft Learn — *Git integration*: https://learn.microsoft.com/fabric/cicd/git-integration/intro-to-git-integration
- Microsoft Learn — *Deployment pipelines*: https://learn.microsoft.com/fabric/cicd/deployment-pipelines/intro-to-deployment-pipelines
- Microsoft Learn — *Microsoft Purview and Fabric*: https://learn.microsoft.com/fabric/governance/microsoft-purview-fabric
- Azure Pricing Calculator: https://azure.microsoft.com/pricing/calculator/
