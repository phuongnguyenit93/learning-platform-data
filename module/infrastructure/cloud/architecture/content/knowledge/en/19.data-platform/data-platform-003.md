# Data Lake, Data Warehouse, and Lakehouse

> **Chapter:** Data Platform  
> **Module:** CLOUD_ARCHITECTURE  
> **Scope:** Architecting cloud applications from business requirements to networking, compute, data, and deployment models. This lesson evaluates reliability, security, scalability, cost, and operations from a Well-Architected perspective.

## Learning Objectives

After this lesson, you will be able to:

1. Explain the roles of a data lake, data warehouse, and lakehouse, as well as the problems each model solves.
2. Select storage and processing models based on data type, access pattern, latency, consistency, team skills, and cost.
3. Outline a cloud data platform from ingestion, storage zones, catalog, processing, and serving to governance and observability.
4. Distinguish batch, micro-batch, and streaming; determine required data latency and delivery/recovery guarantees.
5. Understand the roles of columnar file formats, table formats, metadata/catalogs, and transactions in modern data lakes.
6. Design partitioning, storage lifecycles, data quality, access controls, and cost management.
7. Evaluate lake/warehouse/lakehouse choices against business requirements and the Well-Architected pillars.

## 1. The Data Platform Problem in Cloud Architecture

A transactional application typically needs a database serving requests with low latency and strict update constraints. However, when the business wants to analyze customer behavior, monitor operations, train models, or combine data from multiple systems, running all analytical queries on the transactional database creates contention over CPU, I/O, and connections with user-facing workloads.

A **data platform** organizes how data is ingested, stored, processed, governed, and delivered for those needs. A platform typically supports multiple data types:

- Structured data from relational databases, ERPs, CRMs, and transactional systems.
- Semi-structured data such as JSON, logs, events, clickstreams, and documents.
- Unstructured data such as images, video, audio, and arbitrary files.
- Time-varying change data, including CDC (change data capture), events, and telemetry.
- Reference data, metadata, data catalogs, and governance information.

User groups also differ: applications need transactional reads/writes; analysts need SQL and standardized data; data engineers need ingestion/transformation; data scientists need exploration and experimentation; reporting systems need stable models; governance teams need lineage, access controls, and audit evidence.

### 1.1. Design Questions Before Selecting Technology

| Question | Example | Architectural Impact |
|---|---|---|
| Where does the data come from? | Transactional DBs, SaaS, files, sensors, events | Batch ingestion, CDC, streaming, or file transfer |
| Format and growth rate? | 200 GB/day, growing 30%/year; many small files vs. fewer large files | Object storage, compaction, partitioning, and lifecycle |
| Acceptable latency? | Next-day reports vs. dashboards updated in seconds | Batch, micro-batch, or streaming |
| Who uses it? | SQL analysts, BI, applications, ML pipelines | Warehouse, query engine, APIs, or feature pipelines |
| What consistency level is needed? | Consistent snapshots vs. eventual consistency | Transactions, watermarks, CDC offsets, and table formats |
| How sensitive is the data? | PII, payment, public data | Encryption, IAM, masking, retention, and auditing |
| Must original records be preserved? | Investigation, replay, auditing | Immutable raw zone, versioning, and retention |
| Budget and operational capacity? | Small team, spiky workloads, limited budget | Managed services, autoscaling, serverless, or hybrid models |

Not every workload needs a massive platform. A team with a few reports can start with a database replica or a small warehouse; as data sources, history, and analytical needs grow, a lake/warehouse/lakehouse becomes valuable. Choose an architecture for current needs with a controllable evolution path.

## 2. Data Lake: Flexible Storage at Scale

### 2.1. Concept and Goals

A **data lake** is a centralized repository, usually built on scalable object storage, for storing data across many formats and processing stages. Data can be preserved close to its original source format before being cleaned, standardized, or transformed for specific use cases.

A lake typically exhibits these characteristics:

- **Schema-on-read:** structure/data types are applied or interpreted at read time, depending on format and engine.
- **Flexible formats:** CSV, JSON, Parquet, Avro, images, logs, binaries, and more.
- **Tiered storage economics:** leverages object storage and lifecycle policies to move infrequently accessed data to cheaper tiers.
- **Decoupled compute and storage:** multiple engines can read the same storage zone without relying on a single database cluster.
- **Raw data retention:** facilitates reprocessing when business logic changes or root-cause investigations are needed.

Schema-on-read does not mean data needs no schema or validation. Without contracts, catalogs, and quality checks, a lake can degenerate into a **data swamp**: hard-to-find files, unclear schemas, corrupt/duplicate data, uncontrolled permissions, and no clarity on whether data still has value.

### 2.2. Common Data Zones

| Zone | Purpose | Characteristics |
|---|---|---|
| **Landing / ingest** | Receive data from sources | Retains receipt trail, checksums, manifests, ingestion timestamps |
| **Raw / bronze** | Store near-original data | Append/versioned, minimal transformation, keeps source metadata and timestamps |
| **Cleaned / silver** | Clean, standardize, deduplicate | Explicit schema, validated data quality |
| **Curated / gold** | Serve business analytics/BI | Consumption-friendly models, unified metrics, specific access policies |
| **Archive** | Store cold historical data | Lower-cost storage classes, slower retrieval, explicit retention |

Bronze/silver/gold naming is a common organizational convention, not a mandatory standard. You can use raw/standardized/serving or another structure. What matters is that each zone has a defined meaning, owner, permissions, and output quality bar.

### 2.3. Data Lake Diagram

~~~mermaid
flowchart LR
    DB[(Operational DB)] --> CDC[CDC / Batch Ingestion]
    SaaS[SaaS / APIs] --> ING[Ingestion]
    Files[Files / Logs / Events] --> ING
    CDC --> RAW[(Object Storage: Raw)]
    ING --> RAW
    RAW --> PROC[Batch / Spark / SQL Processing]
    PROC --> CLEAN[(Cleaned / Silver)]
    CLEAN --> CURATED[(Curated / Gold)]
    CURATED --> BI[BI / Analytics]
    RAW --> DS[Data Science / ML]
    CAT[Catalog + Governance] -.-> RAW
    CAT -.-> CLEAN
    CAT -.-> CURATED
~~~

The diagram shows logical flow only. Actual implementation requires network boundaries, workload identities, encryption keys, storage regions, catalogs, logging, checkpoints, and engine-specific access controls.

### 2.4. When Is a Data Lake Suitable?

- Data is diverse and growing rapidly; you want to preserve raw copies for future analytics.
- You have exploratory, data science, machine learning, or reprocessing workloads.
- You need to decouple storage costs from compute and pick engines per task.
- Multiple teams share data while having different processing needs.
- You want long-term historical retention governed by clear lifecycle policies.

The trade-off is having to manage schemas, metadata, transactions, access controls, quality, compaction, and lifecycles. Querying many small files, unoptimized CSV/JSON, or poorly partitioned data can be slow and expensive. Object storage alone does not constitute a reliable data platform.

## 3. Data Warehouse: Structured Data Organized for Analytics

### 3.1. Concept and Goals

A **data warehouse** is an analytical storage and query system that typically integrates data from multiple sources, cleans it, and models it into structures suited for SQL, BI, and reporting.

Common characteristics:

- **Schema-on-write:** data is validated/transformed against a schema before loading into serving models.
- **Analytical modeling:** fact tables, dimensions, star schemas, snowflakes, or custom models.
- **Analytical query optimization:** columnar storage, compression, parallel execution, caching, and query optimizers.
- **Centralized governance:** permissions at schema/table/column/row levels, auditing, and controlled data sharing.
- **Workload isolation:** BI queries do not execute directly against transactional databases.

Many modern cloud warehouses are managed/serverless or decouple storage from compute. Each provider has different pricing, concurrency, caching, limits, and semantics; study the actual service model rather than assuming all warehouses behave identically.

### 3.2. Facts and Dimensions

Example for booking and revenue analytics:

- **FactBooking:** one row per booking or business event at a well-defined grain.
- **DimCustomer:** customer attributes used for slicing and grouping.
- **DimResource:** resource/service attributes.
- **DimDate:** day, month, quarter, day of week.
- **DimLocation:** region/location where applicable.

~~~mermaid
flowchart TB
    FC[(FactBooking)] --> DC[DimCustomer]
    FC --> DR[DimResource]
    FC --> DD[DimDate]
    FC --> DL[DimLocation]
~~~

Fact grain must be stated explicitly: does one row represent a booking, a status transition, or a payment line item? If grain is ambiguous, summing revenue or counting bookings can break due to fan-out joins or double-counting state transitions.

### 3.3. Star Schema Example

| Table | Key | Illustrative Fields | Role |
|---|---|---|---|
| FactBooking | `booking_key` (surrogate) | `date_key`, `customer_key`, `resource_key`, `status_key`, `amount`, `count` | Quantitative measurements |
| DimCustomer | `customer_key` | `customer_id`, `segment`, `created_date`, `valid_from/to` | Slice by customer |
| DimResource | `resource_key` | `resource_id`, `category`, `location_key` | Slice by resource |
| DimDate | `date_key` | `date`, `month`, `quarter`, `year`, `weekday` | Slice by time |
| DimStatus | `status_key` | `status_code`, `status_group` | Status grouping |

To track changes in dimension attributes over time, use **Slowly Changing Dimensions (SCD)**. Type 1 overwrites current info; Type 2 creates a new versioned row with `valid_from`/`valid_to` and a current flag. Your choice determines whether you can answer "which segment was the customer in when the transaction occurred?" versus only "which segment is the customer in today?".

### 3.4. When Is a Warehouse Suitable?

- SQL-based BI/reporting with standardized metric definitions.
- Aggregate queries spanning multiple sources and large data volumes.
- Concurrency support for analysts, dashboards, and analytical workloads.
- Controlled data models, curated datasets, and fine-grained access control.
- Strong integration with existing BI/semantic layer tools.

Trade-offs include compute costs under heavy querying, ingestion/storage costs, coupling to service features and pricing, plus data movement and model management overhead. Warehouses may support extended data types, but they do not automatically replace object lakes for arbitrary file types.

## 4. Lakehouse: Combining Data Lakes with Table Management

### 4.1. Motivation

Data lakes are flexible and often offer strong economics via object storage, yet raw files lack transactions, concurrent updates, and standardized table metadata. Warehouses deliver great SQL/transaction/management ergonomics, but can tightly couple storage/compute or create extra copies when raw data already resides in a lake.

A **lakehouse** is an architecture built on open storage or object storage while adding a table management and metadata layer to support capabilities traditionally associated with warehouses: schema enforcement/evolution, transactions, snapshots, updates/deletes, time travel, and multi-engine access.

A lakehouse typically relies on:

- Object storage as the durable storage foundation.
- Columnar file formats such as Parquet.
- A table format providing metadata, snapshots, and transaction semantics.
- A catalog/metadata service to register tables, schemas, locations, and permissions.
- Batch/streaming/SQL/ML processing engines to read and write.
- Cross-engine governance, lineage, quality, and access controls.

A lakehouse is not a single file format or single service. Supported features depend on the table format, catalog, engine, connector, and version; a feature available in one engine may not behave identically when multiple engines write concurrently.

### 4.2. Lakehouse Diagram

~~~mermaid
flowchart TB
    SRC[DB / SaaS / Events / Files] --> ING[Batch / CDC / Streaming Ingestion]
    ING --> OBJ[(Object Storage)]
    subgraph Lakehouse[Lakehouse Table Layer]
        OBJ --> PARQ[Parquet / Columnar Files]
        META[Table Format Metadata / Snapshots]
        CAT[Catalog / Namespace / Schema]
        PARQ <--> META
        CAT --> META
    end
    ENG1[Spark / Batch Engine] <--> Lakehouse
    ENG2[SQL Query Engine] <--> Lakehouse
    ENG3[Streaming Engine] <--> Lakehouse
    ENG4[ML / Data Science] <--> Lakehouse
    GOV[Governance / IAM / Lineage / Quality] -.-> CAT
    BI[BI / Data Products] --> ENG2
~~~

This is a conceptual view; how engines connect to object storage/catalogs and commit snapshots depends on the chosen ecosystem. Not every engine supports all operations equally on the same table format.

### 4.3. Comparing the Three Models

| Criterion | Data Lake | Data Warehouse | Lakehouse |
|---|---|---|---|
| Primary goal | Store diverse data at scale with flexible processing | SQL/BI analytics on modeled data | Combine open storage with table/transaction management |
| Storage | Typically object storage | Managed storage or service-integrated storage | Typically object storage |
| Schema | Often schema-on-read across many zones | Often schema-on-write before serving | Schema enforcement/evolution via table layer |
| Table transactions | None by default for raw files; requires extra mechanisms | Typically a managed warehouse feature | Provided via coordinated table format/engines |
| Unstructured data | Very well suited | Varies by service; often stored separately | Co-located in storage; metadata managed per use case |
| SQL/BI | Requires appropriate query engine/catalog | SQL is typically central | Multiple SQL engines depending on compatibility |
| Batch/stream/ML | Flexible, governance must be built | Supported per service/tooling | Geared toward multiple engines sharing data |
| Governance | Easily fragmented without catalog/policy | Often centralized and integrated | Requires coordinating catalog, table format, and engines |
| Trade-offs | Data swamp, small files, schema drift | Compute costs, proprietary/service coupling | Integration/compatibility and operational complexity |

These models are not mutually exclusive. An organization can use a lake for raw storage, a warehouse for mission-critical KPIs, and a lakehouse for datasets shared across batch, SQL, and ML. Having multiple layers must be justified: avoid pointless duplication and define clear sources of truth.

### 4.4. When Is a Lakehouse Worth Considering?

- Multiple engines need to access shared tables while minimizing data duplication.
- You need updates/deletes/merges, snapshots, and schema evolution directly on object storage.
- Workloads span batch, streaming, SQL analytics, and data science.
- You want open formats/tables and greater engine flexibility.
- Your team can manage catalogs, transaction semantics, compaction, file layouts, and engine compatibility.

A lakehouse can reduce reliance on a proprietary warehouse, but it **does not automatically eliminate vendor lock-in**. Catalogs, cloud object storage, engines, IAM, and governance tools still introduce dependencies. Operational overhead can be high if the organization must integrate and maintain many components itself.

## 5. File Formats vs. Table Formats: Two Distinct Layers

### 5.1. Row Formats and Columnar Formats

CSV/JSON are easy to exchange and inspect manually, but can consume high storage and CPU for columnar analytics. **Parquet** and **ORC** are columnar storage formats supporting compression and selective column/row-group reads, making them well suited for analytical workloads.

| Format | Characteristics | Best Suited For |
|---|---|---|
| CSV | Simple row-column text, minimal type metadata | Simple exchanges, source ingestion, small datasets |
| JSON | Flexible, nested/semi-structured | Events/APIs, raw landing |
| Avro | Row-oriented, schema embedded or alongside data | Event/record serialization, streaming |
| Parquet | Columnar, compression, predicate/column pruning per engine | Analytics, lakes/lakehouses |
| ORC | Columnar, optimized for certain SQL/big data ecosystems | Analytics where engine support is strong |

Choose formats based on producers/consumers, schema evolution, compression, scan patterns, latency, and interoperability. A Parquet file by itself does not provide transactions, catalogs, or table-level permissions.

### 5.2. A File Format Is Not a Table Format

A **file format** defines how bytes are organized inside a single file. A **table format** manages a collection of files as a logical table, including metadata, snapshots/transactions, schemas, partition specs, and update/delete semantics according to its specification.

A lakehouse table might consist of hundreds of Parquet files plus a metadata log/snapshot tree. When committing a new transaction, the table format determines which table version is committed and which files belong to that snapshot. Query engines read the table via metadata instead of listing every file under a storage prefix.

### 5.3. Common Table Formats

| Table Format | High-Level Concept / Characteristics | Evaluation Considerations |
|---|---|---|
| **Apache Iceberg** | Open table format, metadata trees and snapshots; schema/partition evolution per spec and engine | Catalog choice, engine compatibility, commit protocol, connector versions/features |
| **Delta Lake** | Transaction log managing versions and table operations; broad processing ecosystem | Engine compatibility, protocol versions, and specific feature extensions |
| **Apache Hudi** | Lake data management with upsert/incremental processing and multiple storage modes | Query modes, compaction/cleaning, timeline, and engine support |

Do not assume these three formats are identical or that every engine reads/writes all features uniformly. Before choosing, build a compatibility matrix covering engines, catalogs, cloud storage, reader/writer versions, concurrency models, schema evolution, deletes, streaming, and governance. Test realistic workloads and check version limits.

### 5.4. Snapshots, Time Travel, and Compaction

Table formats can retain snapshot history to query prior table versions, compare changes across commits, support rollback/recovery within retained metadata and files, or enable incremental processing where supported by the format/engine.

Time travel **does not replace independent backups**. Once old files are vacuumed/expired/deleted by lifecycle rules, older snapshots become unreadable. Retention must balance recoverability, compliance retention, privacy deletion, and storage cost.

Many small files inflate listing, query planning, metadata, and storage request overhead. **Compaction** merges small files into better-sized files, but it is itself a write workload requiring conflict control, compute resources, and snapshot management. Choose target file sizes based on engine, storage, and query behavior rather than applying a single universal number.

## 6. Ingestion and Processing: Batch, Micro-Batch, and Streaming

### 6.1. Batch Ingestion

Batch collects data over a time interval or job scope and loads/processes it together. Examples include syncing orders hourly or generating nightly reports.

Advantages: simpler orchestration and testing; suitable when instant updates are unnecessary; cost-effective via scheduled runs and ephemeral compute; easy to rerun a time window when inputs are retained and tasks are idempotent.

Trade-offs: latency includes batch wait plus processing time; large batches create compute/IO spikes; jobs failing near completion may require expensive reruns without checkpointing and resume capabilities.

### 6.2. Micro-Batch

Micro-batch collects data over small windows, such as 30 seconds or 5 minutes, and processes each window as a batch. It sits between traditional batch and event-by-event streaming.

Useful when dashboards need near-real-time updates without millisecond latency. Requires defining windows, watermarks, late-arriving data handling, and how outputs update when older events arrive late.

### 6.3. Streaming

Streaming processes events continuously from a broker or stream source. Architecture must define:

- Producers, topics/partitions, schemas, and event timestamps.
- Consumer groups, offsets/checkpoints, and processing progress.
- Ordering scope, partition keys, and duplicate event handling.
- Event-time vs. processing-time; watermarks and late events.
- Windowing, state stores, and worker restart recovery.
- Backpressure, lag, retention, DLQs, and scaling.

**Exactly-once** depends on system boundaries and engine/sink semantics; end-to-end exactly-once is not automatic across brokers, databases, and external APIs. You typically combine idempotent sinks, transactions, or deduplication to achieve correct business outcomes.

### 6.4. Matching Latency to Business Needs

| Business Need | Candidate Processing Pattern | What to Measure |
|---|---|---|
| Daily financial reporting | Daily batch | Completion time, completeness, rerun safety |
| Operations dashboard updated in minutes | Micro-batch | Data freshness, window lag, job cost |
| Near-real-time fraud alerting | Streaming | Event-to-alert latency, false positives, recovery |
| Marketing KPIs from clickstreams | Streaming or micro-batch | Late events, deduplication, session/window semantics |
| Weekly ML model training | Batch data preparation | Dataset versioning, lineage, reproducibility |

Never choose streaming just because "real-time sounds modern." Always-on infrastructure, state management, operations, retries, and debugging may not be justified if the business tolerates a 15-minute delay.

## 7. Cloud Data Platform Reference Architecture

### 7.1. Flow from Sources to Data Products

~~~mermaid
flowchart TB
    subgraph Sources[Data sources]
        OLTP[(Operational databases)]
        SAAS[SaaS / APIs]
        EVENTS[Events / Logs]
        FILES[Files / Partner feeds]
    end
    subgraph Ingestion[Ingestion layer]
        CDC[CDC connectors]
        BATCH[Batch loaders]
        STREAM[Stream broker]
    end
    OLTP --> CDC
    SAAS --> BATCH
    FILES --> BATCH
    EVENTS --> STREAM
    CDC --> RAW[(Raw object storage)]
    BATCH --> RAW
    STREAM --> RAW
    RAW --> TRANSFORM[Transform / Validate / Deduplicate]
    TRANSFORM --> SILVER[(Standardized tables)]
    SILVER --> CURATE[Business modeling]
    CURATE --> GOLD[(Curated data products)]
    GOLD --> WH[Warehouse / SQL serving]
    GOLD --> BI[BI / Semantic layer]
    SILVER --> ML[ML / Feature pipelines]
    CAT[Catalog + Lineage + Policy] -.-> RAW
    CAT -.-> SILVER
    CAT -.-> GOLD
    OBS[Logs / Metrics / Alerts] -.-> TRANSFORM
    OBS -.-> WH
~~~

This logical blueprint can be implemented with various cloud services. Not every box is mandatory; a warehouse may serve BI directly, or a lakehouse engine may query curated tables without loading into a separate warehouse. Every zone must have an owner, SLA, schema, permissions, and retention/deletion rules.

### 7.2. Separation of Responsibilities

| Layer | Responsibility | Operational Questions |
|---|---|---|
| Source systems | Provide data and schema/change contracts | Who owns fixes when a source schema changes? |
| Ingestion | Connectivity, checkpoints, retries, receipt tracking | How are data loss and duplication prevented? |
| Storage | Durability, versioning, encryption, lifecycle | How long is each dataset kept, and in which region? |
| Processing | Validation, transformation, deduplication, business logic | Are jobs idempotent, replayable, and testable? |
| Catalog/governance | Discovery, schemas, classification, lineage, policies | Who is allowed to see and use the data? |
| Serving | SQL, BI, APIs, feature stores, or exports | What are the SLOs, concurrency, and freshness targets? |
| Observability | Job status, data freshness, quality, cost | Who receives alerts, and where are the runbooks? |

### 7.3. Decoupling Storage from Compute

Object storage and compute engines scale independently: data persists durably while compute spins up per job or workload. This flexibility is not free:

- Each query may incur scan charges, storage API requests, and compute time.
- Multiple engines reading shared data require coordinated concurrency, catalogs, and unified permissions.
- Cross-region, cross-account, or cross-service network egress can become substantial.
- File formats and partitioning dictate bytes read; columnar storage does not optimize itself if queries scan everything.
- Ephemeral engines need bootstrap, caching, and warm-up; very short jobs can be dominated by startup overhead.

Serving architectures can isolate BI, ML, and data engineering workloads to limit blast radius. Prevent an unbounded analytical query from starving compute needed for critical executive dashboards.

## 8. Data Schemas, Partitioning, and Quality

### 8.1. Partitioning by Query Pattern

Partitioning lets engines skip irrelevant data (**partition pruning**) when query predicates match the partition key. Example daily event layout:

~~~text
s3://data-lake/events/
  event_date=2026-11-16/
  event_date=2026-11-17/
  event_date=2026-11-18/
~~~

Or by date and source type:

~~~text
.../event_date=2026-11-18/source=web/
.../event_date=2026-11-18/source=mobile/
~~~

Overly granular partitioning creates excessive directories, small files, and metadata; overly coarse partitioning forces queries to scan unnecessary data. Never partition by high-cardinality keys like `user_id` if it spawns millions of partitions. Choose partition keys from access patterns, volume per period, pruning effectiveness, and catalog limits.

### 8.2. File Size and the Small Files Problem

Excessive small files force queries to list/read bloated metadata, open thousands of files, and rack up storage request fees. Compaction lowers overhead but consumes compute and requires writer/reader coordination.

Mitigations:

- Buffer or micro-batch data reasonably before writing.
- Trigger compaction by partition or file-count threshold, avoiding peak business hours.
- Monitor file counts, average/p95 file sizes, small-file ratios, and query planning time.
- Avoid jobs writing one file per record or tiny files per partition.
- Use a table format/catalog to manage snapshots and metadata instead of relying solely on storage prefixes.

### 8.3. Data Quality and Schema Contracts

| Quality Dimension | Question | Example Check |
|---|---|---|
| Completeness | Are all expected records/fields present? | Record count per source/time window |
| Validity | Are values within valid domains? | `status` in enum, valid parseable timestamps |
| Uniqueness | Are logical keys unique? | Deduplicate by `event_id`/`booking_id` |
| Consistency | Do related sources/fields agree? | `amount = quantity * price` per business rules |
| Timeliness | Did data arrive on schedule? | Freshness lag, watermarks |
| Accuracy | Does it match authoritative sources or reconciliations? | Count/sum reconciliation |

Never silently fix corrupt data. Log reject/quarantine counts, root causes, sources, timestamps, and owners. Invalid records can be quarantined to avoid blocking an entire batch, but never silently dropped without metrics and remediation workflows.

### 8.4. Schema Evolution

Sources may add columns, change types, alter enums, or drop fields. Maintain a schema registry/catalog or equivalent governance workflow:

1. Attach schema versions and owners to sources.
2. Analyze whether consumers depend on changing fields or semantics.
3. Prefer backward-compatible changes like adding optional fields with clear meanings.
4. For breaking changes, run dual versions/fields in parallel, backfill, and migrate consumers on a schedule.
5. Test against old data, new data, nulls, and late-arriving events.
6. Remove deprecated fields only after all consumers migrate and rollback windows expire.

Schema evolution is more than syntax parsing. Changing currency units, timezones, status meanings, or fact grain can break reports even when jobs exit cleanly.

## 9. Catalog, Governance, and Data Security

### 9.1. Data Catalog and Metadata

A catalog helps users discover and understand datasets. Useful metadata includes:

- Dataset/table name, business description, and owner.
- Schema, data types, partitions, and storage locations.
- Source system, ingestion time, update schedule, freshness, and SLA.
- Classification such as public/internal/confidential/regulated.
- Upstream/downstream lineage, producing jobs, and consumers.
- Access permissions, retention, quality scores, and deprecation status.

A catalog does not replace enforcement. Tagging a column as "PII" in documentation does not block an analyst from querying `email`; you need IAM/ACLs, masking, row/column-level controls, or equivalent platform-enforced policies.

### 9.2. Identity- and Purpose-Based Access Control

- Ingestion workloads can only write to their designated landing/raw zones, with no read access across all curated data.
- Transformation pipelines read only required inputs and write only to assigned output datasets.
- BI/analysts access only role-appropriate data products; PII requires separate authorization or masking.
- Service accounts/workload identities are isolated per job and environment; avoid long-lived shared credentials.
- Catalog, storage, and query engines must enforce consistent policies; do not let direct object storage access bypass warehouse permissions.
- Audit log permission grants, sensitive queries, exports, and deletions.

### 9.3. Encryption, Networking, and Data Residency

Cloud designs must specify:

- TLS in transit across source → ingestion → storage → engine.
- Encryption at rest, KMS key lifecycles, and decrypt permissions.
- Private endpoints/VPC endpoints, egress restrictions, and cross-account connectivity.
- Permitted storage regions, compute execution regions, and backup/replica locations.
- Data deletion workflows upon request across raw, curated, caches, extracts, backups, and derived copies.

A Parquet file or snapshot can contain PII even if its filename does not reveal it. Lineage and classification must follow the full lifecycle so access, retention, and deletion stay consistent.

### 9.4. Governance and Ownership

| Role | Responsibility |
|---|---|
| Data owner | Defines purpose, quality bar, access permissions, and retention |
| Data steward | Maintains metadata, glossary, classification, and quality rules |
| Producer owner | Guarantees source schemas and upstream reliability |
| Pipeline owner | Operates ingestion/transforms, freshness, retries, and recovery |
| Consumer owner | Uses data according to semantics, permissions, and dataset limits |
| Platform/security | Provides foundational services, IAM, networking, encryption, logging, and policies |

Do not let a data catalog accumulate thousands of tables with no owners or descriptions. When an owner leaves or a product sunsets, transfer ownership or mark datasets deprecated/retired with a corresponding data lifecycle workflow.

## 10. Reliability, Recovery, and Reprocessing

### 10.1. Ingestion Must Be Resumable

A pipeline can lose connectivity between reading from a source and writing to a destination. Determine:

- Where are watermarks/offsets/checkpoints stored?
- When a job retries, could it write duplicates?
- How are late-arriving or out-of-order records handled?
- If a source schema changes mid-job, does the job fail or quarantine?
- If a job crashes after writing data but before marking completion, how are duplicate writes prevented?

Solutions typically combine idempotent writes, staging + atomic commits or table format transactions, event ID/dedup keys, durable checkpoints, and source reconciliation. For database CDC, understand offset/log positions and transaction log retention; if consumer lag exceeds retention, a full snapshot re-bootstrap may be required.

### 10.2. Data Freshness and Completeness

Freshness measures the elapsed time from when an event/record originates at the source until it becomes queryable in the serving layer:

~~~text
event_time        = when the business event occurred
ingestion_time    = when the platform received the data
processed_time    = when the pipeline completed processing
available_time    = when consumers can query the result

end-to-end freshness = available_time - event_time
~~~

Measuring only job execution duration misses time data spent waiting in sources or queues. Track watermarks, late events, delayed partitions, quarantined records, and window completeness as well.

### 10.3. Backup and Disaster Recovery

Object storage versioning, replication, table snapshots, and warehouse backups carry different semantics:

- Versioning restores individual objects per service capabilities, but does not automatically guarantee multi-file consistency across a table.
- Replication can propagate accidental deletes or logically corrupted data.
- Snapshots/time travel rely on metadata and retention; vacuum/expire jobs can remove older data.
- Warehouse backups follow service-specific restore, cloning, and retention mechanics.

Define RTO/RPO for raw, curated, catalogs, pipeline state, and serving layers. Test restoring **a complete dataset along with the metadata needed to read it**, not just a single file. Data recovery requires compatible catalogs, schemas, encryption keys, permissions, and pipeline code/versions.

### 10.4. Replay and Reproducibility

An immutable raw zone or source archive enables rerunning transformations when logic changes. To reproduce outputs, retain:

- Source snapshots/versions or offsets and time windows.
- Pipeline code, parameters, dependencies, and engine versions.
- Schemas, business rules, and reference data versions.
- Run timestamps, checkpoints, output table snapshots, and quality check outcomes.

Not all raw data should be kept forever. Replays must respect retention rules and deletion rights; deleting sensitive data upon user request may legally preclude full historical replay.

## 11. Performance and Cost in Cloud Data Platforms

### 11.1. Optimize by Actual Bytes Read

Query costs may depend on bytes scanned, compute duration, concurrency, storage API calls, or provisioned capacity. Key techniques:

- Columnar formats and projection pruning: read only needed columns.
- Predicate pushdown: filter close to storage when supported by the engine.
- Partition pruning: read only relevant partitions.
- Compression: reduce I/O volume while weighing decompression CPU.
- Statistics/catalogs: help query planners estimate cardinality and choose plans.
- Materialized views/aggregate tables: avoid recomputing popular dashboards repeatedly.
- Caching: speeds up repeated queries while requiring freshness/invalidation strategies.
- Workload isolation/resource groups: stop massive queries from monopolizing shared compute.

Example: a dashboard needs only 5 columns out of an 80-column table and filters 2 days out of 1 year of data. Parquet + daily partitioning + projection/filter pushdown can drastically cut bytes scanned compared to a full scan. Verify actual impact via bytes scanned, execution plans, and billing metrics.

### 11.2. Cost Estimation

~~~text
Data TCO ≈
    storage (raw + curated + snapshots + versions)
  + ingestion (connectors, brokers, API calls, egress)
  + compute (batch, streaming, SQL, ML)
  + catalog/governance/observability
  + backup/replication/DR
  + operations, security, and staffing
~~~

Hypothetical example: a lake stores 10 TB raw, plus 4 TB cleaned/curated, plus 3 TB snapshots/versions—roughly 17 TB of logical storage before accounting for compression, deduplication, and cloud provider billing rules. With multiple retained snapshots, temporary compaction artifacts, and regional replicas, billed storage can be significantly higher. Never budget using raw ingestion size alone.

### 11.3. Commonly Overlooked Cost Drivers

| Source | How It Accrues | Control |
|---|---|---|
| Small files/listing | Numerous small objects, planning and API request overhead | Compaction, batching, file count monitoring |
| Query scans | Scanning unneeded partitions/columns | Parquet/ORC, pruning, query guardrails |
| Streaming compute | Always-on workers, idle capacity | Autoscaling/scale-to-zero where suitable, micro-batching |
| Data egress | Cross-region, cross-account, or Internet transfers | Co-locate compute with storage, review network topology |
| Snapshots/versions | Historical data, delete files, retention bloat | Policy-driven lifecycle and snapshot expiration |
| Logs/traces | High-volume job/query logs | Sampling, retention caps, sensitive data redaction |
| Failed jobs/retries | Repeated scans/compute from failures | Idempotency, checkpoints, bounded retries |
| Replication/DR | Multi-zone and cross-region copies | Align with RPO/RTO and audit costs |

### 11.4. Chargeback/Showback and FinOps

Tag metadata and billing resources with owner, domain, environment, data product, cost center, and pipeline ID where supported. Attribute costs by dataset/table/storage prefix, job/pipeline/compute pool, query/workload/warehouse, region/network egress, and retention/snapshot/version/lifecycle tiers.

Precise per-user chargeback is not always necessary to start; domain- or product-level showback is usually enough. What matters is having an accountable owner who responds when storage or query spend spikes unexpectedly.

## 12. Data Products and the Serving Layer

Curated data should be treated as a **data product** with explicit consumers and contracts:

- Name and business description; grain and metric semantics.
- Owner, steward, source lineage, and authorized consumers.
- Schema/version, update schedule, freshness/SLO, and quality score.
- Access permissions, classification, retention, and access request workflow.
- Consumption interfaces: BI semantic layer, SQL endpoint, API, or export.

For example, a `booking_daily_metrics` data product defines one row per day, region, and service category; `booking_count` counts confirmed bookings as of the snapshot time; `gross_amount` specifies currency, refund handling, and timezone. Without shared semantics, two dashboards can display the same KPI name with conflicting numbers.

A semantic layer centralizes metric definitions and permissions, preventing each dashboard from duplicating business logic. However, it does not replace upstream data validation, lineage, and quality gates.

## 13. Well-Architected Review

| Pillar | Lake / Warehouse / Lakehouse Questions | Evidence |
|---|---|---|
| **Operational Excellence** | Do pipelines have owners, retries, replay, lineage, runbooks, and versioned deployments? | Job SLOs, runbooks, lineage, CI/CD, replay drills |
| **Security** | Are identity, encryption, PII, networking, and query permissions enforced consistently across engines? | IAM/ACL tests, audits, masking, access reviews |
| **Reliability** | Can ingestion resume, do outputs have transactions/atomicity, and do backups/restores meet RTO/RPO? | CDC checkpoints, failure tests, restore drills |
| **Performance Efficiency** | Are partitioning, file layouts, formats, query engines, and workload isolation appropriate? | Bytes scanned, p95 query latency, streaming lag, file metrics |
| **Cost Optimization** | Do storage, queries, compute, egress, snapshots, and retries have owners and budgets? | Cost dashboards, showback, lifecycle rules, query cost |
| **Sustainability** | Are redundant scans/storage avoided, idle compute shut down, and expired data deleted? | Utilization, scan efficiency, retention compliance |

Do not choose a lakehouse simply for its feature checklist, or a warehouse solely for SQL convenience. Balance total cost of ownership, operability, portability, data requirements, and team capability.

## 14. Process for Selecting the Right Model

1. **Define objectives:** BI, ad-hoc analytics, ML, near-real-time dashboards, auditing, or data sharing.
2. **Inventory sources:** formats, volume, velocity, schemas, permissions, locations, and owners.
3. **Define data SLOs:** freshness, completeness, query latency, concurrency, RTO/RPO, and retention.
4. **Catalog access patterns:** SQL, scans, joins, upserts, streaming, replay, file access, and sharing.
5. **Compare lake/warehouse/lakehouse:** storage, transactions, engines, governance, and cost.
6. **Benchmark representative workloads:** real ingestion, real queries, skewed data, concurrency, late events, and failures.
7. **Design security/governance:** catalog, IAM, data classification, lineage, and data deletion.
8. **Estimate TCO:** storage, compute, egress, snapshots, logging, backups, and operational effort.
9. **Record ADR and roadmap:** initial choice, constraints, review triggers, and migration path.

### 14.1. Quick Selection Matrix

| Dominant Need | First Model Worth Evaluating | Key Caveats |
|---|---|---|
| Diverse raw data, long-term retention, ML/exploration | Data lake | Requires investment in catalog, schema, quality, and policies |
| BI/SQL with stable models and standardized metrics | Data warehouse | Evaluate compute/concurrency costs and portability |
| Multiple engines sharing tables on object storage with transactions/updates | Lakehouse | Verify table format/catalog/engine compatibility |
| Just a few reports from a small database | Small replica/warehouse or simple query service | May not need a lake or lakehouse yet |
| Real-time events with stateful processing | Streaming platform paired with lake/warehouse/lakehouse | Evaluate brokers, checkpoints, and sink semantics |

### 14.2. Example Architecture Selection ADR

~~~text
ADR-DP-003: Building Curated Analytics on a Lakehouse

Context:
- Sources include relational DBs, events, and partner files.
- Data engineering, BI, and ML need to share several core datasets.
- Raw data must be retained for replay; curated data needs SQL and controlled updates.

Options:
A. Data lake + query engine only.
B. Load all data into a warehouse.
C. Object storage + open table format + catalog + multi-engine compute.

Illustrative Decision: Option C for shared curated datasets;
keep raw in a dedicated storage zone; retain a warehouse option
for BI workloads with specialized SLOs or high concurrency.

Rationale:
- Supports multiple engines while keeping underlying data in object storage.
- Table metadata/transactions manage updates and snapshots cleanly.

Trade-offs:
- Requires testing compatibility, catalogs, commit concurrency,
  compaction, governance, and operations.
- Does not automatically eliminate cloud/provider coupling.

Verification:
- Benchmark queries/ingestion on representative workloads.
- Test writer concurrency, schema evolution, and replay.
- Verify access controls across every engine.
- Measure bytes scanned, freshness, storage, compute, egress, and TCO.

Review When:
- SLOs, engine ecosystems, team skills, or costs change significantly.
~~~

## 15. Common Mistakes

| Mistake | Consequence | Improvement |
|---|---|---|
| Treating a data lake as just a file bucket | Data swamp, hard to discover and govern | Catalog, owners, zones, schemas, lineage, quality |
| Running all reports on the OLTP database | Resource contention with user-facing requests | Replicas, warehouse, or isolated workloads |
| Picking a warehouse/lakehouse before understanding access patterns | Unnecessary cost and complexity | Clarify users, queries, freshness, and volume first |
| Assuming Parquet alone provides transactions | Concurrent writes or inconsistent snapshot reads | Table format/catalog/commit semantics |
| Assuming a lakehouse removes all vendor lock-in | Connector, IAM, catalog, and engine coupling remain | Compatibility matrix and portability tests |
| Streaming data that does not need real-time | High cost and operational burden | Batch/micro-batch when SLOs permit |
| Partitioning by ultra-high-cardinality keys | Partition and small-file explosion | Choose grain from volume and query predicates |
| Ignoring late or duplicate events | Wrong KPIs and duplicate records | Watermarks, event IDs, dedup/reconciliation |
| Keeping snapshots indefinitely | Storage bloat, compliance/privacy risks | Snapshot expiration and lifecycle policies |
| Backing up files without catalogs/code/keys | Restored data is unusable | Back up metadata, pipelines, IAM, and encryption keys |
| Inconsistent permissions across engines/storage | Governance bypass and data leaks | Unified policy across catalog, object storage, and query engines |
| Tracking only job success, ignoring freshness/quality | Green jobs with missing or stale data | Data SLOs, reconciliation, freshness, and quality checks |

## 16. Practice Exercise: Designing a Data Platform for a Booking Service

**Scenario:** A booking platform has a relational database serving APIs, booking events, web/mobile logs, and partner files. Product wants operations dashboards refreshed within 5 minutes; Finance needs accurate daily reports; Data Science needs historical data for demand forecasting models. The data contains PII and requires strict access controls. Actual volumes, target budgets, and specific engines have not yet been finalized.

Develop a proposal covering:

1. **Workload classification:** specify how the 5-minute dashboard, daily reporting, and historical ML differ in freshness and consistency needs.
2. **Source inventory:** document sources, schemas, volume/velocity, owners, classification, retention, and ingestion method.
3. **Comparing the three models:** propose roles for a lake, warehouse, and lakehouse; explain what should be shared versus what does not need to be forced into one model.
4. **Architecture diagram:** depict batch/CDC/stream ingestion, raw/clean/curated zones, catalog, governance, SQL/BI/ML, and observability.
5. **Formats/partitioning:** choose CSV/JSON/Avro/Parquet or a table format for each zone; define partitioning and compaction strategy.
6. **Data quality/schema:** define deduplication, late events, schema evolution, quarantine, and reconciliation.
7. **Security:** specify permissions for ingestion/analysts/ML, PII masking, encryption, private networking, auditing, and retention.
8. **Reliability:** design checkpoints, replay, idempotency, backup/restore, and RTO/RPO per data tier.
9. **Cost model:** account for raw/curated/snapshot storage, job/query compute, egress, logging, and backups; outline showback.
10. **ADR and validation:** choose an architecture, list alternatives, test queries/ingestion/failures, and define review triggers.

| Data Product | Consumer | Target Freshness | Storage/Model | Access | Verification |
|---|---|---|---|---|---|
| `booking_ops_5min` | Operations | ≤ 5 minutes (assumed) | Curated table + SQL/BI | Operations role, minimal PII | Event lag, completeness |
| `booking_finance_daily` | Finance | Ready before daily reporting cutoff | Curated warehouse/lakehouse | Finance role, audited | Count/sum reconciliation |
| `booking_history_ml` | Data Science | Daily/weekly batch | Historical lake/lakehouse | ML role, masked | Dataset version, lineage |

**Completion criteria:** A reviewer clearly understands how data flows from each source to each consumer, what each zone stores, how duplicate/late events are handled, who has access, how recovery works, and where major costs arise. Unverified numerical targets must be explicitly flagged as assumptions requiring validation.

## 17. Key Takeaways

- **Data lakes** prioritize storing diverse data at massive scale, retaining near-original copies and enabling varied processing engines.
- **Data warehouses** prioritize modeled data, SQL/BI queries, and governed metrics.
- **Lakehouses** add table management, metadata, and transactions atop open storage so multiple engines can share datasets; exact capabilities depend on the ecosystem.
- **File formats differ from table formats:** Parquet organizes bytes inside files; Iceberg/Delta/Hudi manage tables, snapshots, and transaction semantics.
- **Batch, micro-batch, and streaming** are selected based on business latency, complexity, and operational cost.
- **Governance travels with the data:** catalogs, owners, classification, IAM, lineage, quality, retention, and auditing must span all engines.
- **Measure end-to-end:** freshness, completeness, query performance, bytes scanned, storage, compute, egress, and replay/restore readiness.

A great cloud data platform is not the one storing the most files or running the most engines. It is the architecture that delivers accurate, complete, secure, and timely data to the people who need it—at a cost and operational complexity that can be explained, measured, and continuously improved.
