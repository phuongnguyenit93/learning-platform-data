# Separating Transaction Processing from Data Analytics

A cloud application typically has to serve two different data workloads. Online business operations need to create orders, update payments, reserve inventory, or look up status with low latency and high correctness. Meanwhile, the analytics team needs to aggregate millions of transactions, calculate monthly trends, build dashboards, forecast demand, and combine data across multiple systems. If both workloads share the same database and resources without clear boundaries, heavy analytical queries can slow down transactions, while optimizations made for transactions can make analytics difficult.

**Separating transaction processing from data analytics** is an architectural decision aimed at isolating workloads, storing data in formats suited to each purpose, and synchronizing data between systems under explicit contracts. The pattern typically combines transactional databases (OLTP), change data capture (CDC) mechanisms, ETL/ELT pipelines, a data lake or data warehouse, a modeling layer, and an analytics serving platform.

This lesson belongs to the **Data Platform** chapter in the **Cloud Architecture** track: learning how to architect cloud applications from business requirements to networking, compute, data, and deployment models while balancing reliability, security, scalability, cost, and operations. Separating workloads does not mean data synchronizes instantaneously or that analytical copies are always accurate; the architecture must explicitly define freshness, lineage, quality, access control, and recovery.

After this lesson, you will be able to:

- Distinguish OLTP and OLAP by workload, data model, latency, and transaction semantics.
- Explain why analytical queries can impact transactional databases.
- Design data flows from OLTP sources through CDC/ETL/ELT to a lake, warehouse, and serving layer.
- Choose between batch, micro-batch, or streaming based on freshness and cost.
- Define schema, partitioning, data quality, lineage, and data governance.
- Protect sensitive data when replicating and exposing it for analytics.
- Set SLOs for pipelines, freshness, completeness, and data recovery.
- Evaluate trade-offs between isolation, complexity, cost, and operability.

## 1. Two Workload Categories: OLTP and OLAP

**OLTP (Online Transaction Processing)** serves ongoing business transactions. Each operation typically reads or updates a selective set of records, requires fast response times, and must preserve data invariants.

Examples: creating a booking and checking asset availability; recording a payment or refund; updating delivery status; verifying account permissions and details; decrementing inventory within a single transaction.

**OLAP (Online Analytical Processing)** serves analytics over large datasets, typically reading many records, joining, grouping, aggregating, and computing metrics over time. Examples: total revenue by region/month/equipment type; cancellation rate; customer lifecycle analysis; seasonal demand comparison; building datasets for forecasting and machine learning.

| Criterion | OLTP | OLAP |
| --- | --- | --- |
| Goal | Online business processing | Analytics and decision support |
| Access pattern | Many small requests, point lookups and updates | Large scans, joins, and aggregations |
| Unit of work | Short transactions | Long-running queries/jobs |
| Latency | Typically milliseconds to a few hundred milliseconds depending on use case | Seconds to minutes or longer |
| Data writes | Many small, continuous operations | Batch, stream, or micro-batch loads |
| Data model | Usually normalized to protect integrity | Dimensions, facts, denormalized, or query-optimized |
| Concurrency | Many transactions competing for rows/locks/connections | Fewer queries, each potentially consuming significant CPU/I/O |
| Consistency | Transactions and business invariants | Can be eventually consistent per freshness SLO |
| Users | Applications, customers, operations staff | Analysts, BI tools, data scientists, leadership |
| Optimization | Transaction latency, throughput, availability | Scan throughput, query latency, and cost |

Timeframes above are illustrative guidelines, not hard rules. A dashboard may require sub-second or few-second responses, while a training job may run for hours. OLTP also does not have a single latency target for every transaction.

### 1.1. Why Shouldn't You Default to One Database for Everything?

An analytical query can scan hundreds of millions of rows, hold resources for a long time, create large sorts/hashes, or consume significant I/O. Meanwhile, OLTP transactions still need stable connections, cache pages, CPU, and disk latency.

If reports run during peak hours, database CPU spikes, transactions wait longer, buffer/cache pages get evicted by table scans, connection pools are tied up by long-running queries, and lock contention increases. A buggy dashboard or unbounded query can cause a cascading impact across the entire application.

Separating workloads lets transactional databases focus on guaranteeing business operations while the analytics system uses storage and compute suited for scans and aggregations.

## 2. Data Architecture Boundaries

A data platform is not necessarily a single product. It consists of zones with distinct responsibilities: source systems, ingestion, storage, transformation, governance, and serving.

~~~mermaid
flowchart LR
    subgraph SOURCES["Business data sources"]
        OLTP[("OLTP databases")]
        APP["Application events"]
        EXT["External systems / files"]
    end
    SOURCES --> ING["Ingestion: CDC / batch / stream"]
    ING --> RAW[("Raw data lake / landing zone")]
    RAW --> TRANS["Transform / quality / governance"]
    TRANS --> WH[("Warehouse / curated lakehouse")]
    WH --> BI["BI / dashboards"]
    WH --> DS["Data science / ML"]
    WH --> API["Analytical APIs / extracts"]
~~~

| Component | Responsibility | Examples |
| --- | --- | --- |
| OLTP source | Authoritative source for transactional state | Booking DB, Payment DB |
| Ingestion | Capture snapshots or changes | CDC connector, event consumer, file ingestion |
| Landing/raw zone | Retain near-source data and load metadata | Object storage raw bucket |
| Processing | Parse, validate, deduplicate, transform | Stream processor, SQL ELT, Spark job |
| Curated layer | Standardized and validated data | Warehouse tables, lakehouse tables |
| Semantic/serving | Define metrics and serve queries | BI semantic model, analytical API |
| Governance | Permissions, lineage, catalog, retention, and quality | Data catalog, policy engine |

Do not let BI tools query production databases directly with unrestricted ad-hoc access. If a special lookup case requires it, strictly limit query scope, permissions, concurrency, and load impact.

## 3. Data Contracts Between OLTP and the Analytics Platform

Separating workloads does not automatically guarantee that data is accurate, complete, and understandable. Before building pipelines, teams must agree on a data contract.

A data contract should specify:

- **Owner:** the team or domain responsible for the data's meaning.
- **Schema:** field names, types, nullability, enums, and structure.
- **Semantics:** whether fields represent an event or current state; currency units, timezone, and business definitions.
- **Primary/business key:** how a record or entity is uniquely identified.
- **Change behavior:** inserts, updates, deletes, tombstones, corrections, and late arrivals.
- **Versioning:** how fields are added/removed and compatibility rules.
- **Freshness:** how quickly data must reach the analytics layer.
- **Quality rules:** uniqueness, completeness, referential integrity, and valid ranges.
- **Security classification:** PII, confidential, public, or restricted data.
- **Retention:** how long raw, curated, and derived data are retained.

For example, an `amount` field is ambiguous without currency, sign convention, transaction status, and gross/net rules. Analysts can produce wrong revenue metrics even when the pipeline runs without technical errors.

### 3.1. Current State vs. Event History

There are two common ways to bring OLTP data into analytics:

1. **Snapshot/current-state:** each extraction pulls the current state of the table. Suitable when only the latest state is needed and periodic updates are acceptable.
2. **Change/event history:** streams changes over time. Suitable when historical records, incremental processing, or point-in-time reconstruction are required.

A current-state snapshot does not capture every transition that occurred. If you need to analyze order lifecycles or state history, you need granular CDC, business events, or a dedicated history source.

## 4. Ingestion: Batch, Micro-Batch, Streaming, and CDC

### 4.1. Batch Ingestion

Batch extracts data on a schedule: hourly, daily, or by business window. Its advantages are simpler implementation, optimized scans and bulk loads, easy scheduling, and straightforward partition reprocessing. Trade-offs include stale data until the next batch; large snapshots putting load on sources; failed batches delaying the entire window; and incremental extraction requiring reliable watermarks.

### 4.2. Micro-Batch

Micro-batch processes small groups of data at shorter intervals, such as every 1–5 minutes. This can be a middle ground between freshness and operational complexity. You must define how batches close, retry, prevent duplicate loads, and handle missed batch intervals. A scheduler finishing successfully does not prove every record from that window has arrived.

### 4.3. Streaming Ingestion

Streaming processes data continuously or in very short windows, suited for cases where events must appear quickly in dashboards or alerts. In return, you must manage partitions, offsets/checkpoints, late events, ordering, backpressure, replay, and consumer operations.

### 4.4. Change Data Capture (CDC)

CDC captures changes from a data source, usually by reading the transaction log or an equivalent mechanism. Instead of repeatedly scanning entire tables, a connector reads inserts, updates, and deletes to forward downstream.

~~~mermaid
sequenceDiagram
    participant A as OLTP application
    participant DB as Transactional database
    participant C as CDC connector
    participant B as Broker
    participant L as Data lake / warehouse
    A->>DB: Commit transaction
    DB->>DB: Append database log
    C->>DB: Read log position
    DB-->>C: Change records
    C->>B: Publish changes
    B-->>L: Consume and apply
    L->>L: Update curated tables
~~~

CDC can reduce query overhead compared to table polling, but it is not free. The connector requires log-reading privileges, appropriate replication slots or log retention, lag monitoring, and schema change handling. If a connector stops for too long, required logs may be purged or log storage may grow rapidly depending on the database engine.

### 4.5. Ingestion Comparison

| Method | Typical Freshness | Complexity | Best Suited For |
| --- | --- | --- | --- |
| Batch | Minutes to days | Low to medium | Periodic reporting, slowly changing data |
| Micro-batch | A few minutes | Medium | Frequent dashboards without instant-event needs |
| Streaming | Seconds or near real-time | High | Alerting, telemetry, event analytics |
| CDC | Can be near real-time depending on connector/downstream | Medium to high | Synchronizing database changes |
| Full snapshot | Per extraction schedule | Low initially, can tax sources | Small datasets or initial bootstrap loads |

These are illustrative ranges, not vendor guarantees. Choose based on freshness SLOs, source capabilities, cost, and operational capacity.

## 5. CDC Does Not Equal Business Events

CDC typically reflects changes at the database record level: which table changed, which columns changed, before/after images, and log position depending on the system. Business events describe business meaning: `BookingConfirmed`, `RefundCompleted`, `AssetReturned`.

For instance, confirming a booking might update three tables and emit three CDC change records. A single business event encapsulates the fact that the booking was confirmed after all relevant invariants completed.

| Characteristic | CDC record | Business event |
| --- | --- | --- |
| Source | Database log/table mutation | Domain/application logic |
| Semantics | Technical, reflecting storage mutations | Business-level, reflecting what happened |
| Schema coupling | Coupled to database schema | Coupled to business contract |
| Best suited for | Replication, ingestion, downstream sync | Integration, workflows, business analytics |
| Risk | Internal schema changes impact consumers | Producer must define events accurately |

CDC can be used for analytical ingestion, but if you need to understand why a business decision happened, business events carry richer semantics. Do not infer business transitions from a single row update without reliable correlation logic.

## 6. ETL and ELT

- **ETL (Extract, Transform, Load):** extracts data, transforms it in a processing engine, and loads the result into the destination.
- **ELT (Extract, Load, Transform):** loads data into the destination platform first, then uses the warehouse/lakehouse compute to transform it.

| Criterion | ETL | ELT |
| --- | --- | --- |
| Transformation | Before loading | After loading into raw/landing |
| Compute platform | Separate ETL engine or managed service | Warehouse/lakehouse compute |
| Raw data | May only be partially kept depending on pipeline | Usually keeps raw data for re-transformation |
| Flexibility | Coupled to pre-load logic | Easy to build new models from raw if data is retained |
| Cost | Processing compute and data movement | Raw storage plus destination compute |
| Best suited for | Masking/tokenizing before landing, multi-source integration | SQL analytics, in-warehouse/lakehouse ELT |

Both approaches can be combined. For example, you might strip or tokenize PII before landing data in a shared analytics zone, then execute business transformations after loading.

## 7. Data Lake, Warehouse, and Lakehouse

### 7.1. Data Lake

A data lake typically stores data in object storage across multiple formats and processing stages: raw, cleaned, curated, logs, events, semi-structured, and unstructured.

Advantages include storing diverse formats at massive scale, retaining raw data for reprocessing, decoupling storage from compute, and flexibility for data science/ML. Trade-offs include the risk of turning into a data swamp without catalog/schema/ownership/quality; query performance depending heavily on format, partitioning, file sizing, and metadata; and needing explicit object-level/column-level access controls.

### 7.2. Data Warehouse

A data warehouse is optimized for structured analytical queries, usually offering an integrated SQL engine with managed compute and concurrency. Advantages include easy BI integration, joins, and aggregations, clear schemas/semantic models, and multi-user workload management. Trade-offs include compute costs scaling with query volume/concurrency; unstructured data requiring conversion; and pricing models or lock-in varying by provider.

### 7.3. Lakehouse

A lakehouse combines object storage/lake with a transactional table format, catalog, and query engine to bring warehouse-like table management to the lake. Some ecosystems support schema evolution, table transactions, time travel, or metadata management, though exact capabilities depend on the table format and engine.

Do not assume a lakehouse automatically solves every issue of lakes and warehouses. You must verify compatibility across writer/reader engines, transaction isolation, concurrency, compaction, and catalog management.

| Criterion | Data lake | Data warehouse | Lakehouse |
| --- | --- | --- | --- |
| Data | Structured, semi/unstructured | Mostly structured/curated | Structured and diverse formats via table/lake |
| Storage | Object storage | Managed storage | Object storage + table metadata |
| Query | Multiple engines | Integrated SQL analytics | Compatible SQL/compute engines |
| Schema | Can be schema-on-read | Strictly managed schema | Schema/table metadata |
| Use cases | Raw archive, data science, files | BI, metrics, analytics | Unified analytics when ecosystem supports it |
| Operations | Catalog, format, partitioning, lifecycle | Warehouse workload/cost management | Compatibility, catalog, compaction, concurrency |

## 8. Data Layers: Raw, Cleaned, and Curated

A layered structure distinguishes near-source data, standardized data, and decision-ready data.

- **Raw/landing:** stores data as close to the source format as possible, along with source name, ingestion time, batch ID, schema version, and checksum. Raw must have clear protection, permissions, and retention; it does not necessarily have to store full unmasked PII.
- **Cleaned/standardized:** standardizes data types, timezones, units of measure, country codes, currencies, and schemas; handles duplicates, invalid records, and late arrivals; maintains lineage back to raw for investigation.
- **Curated/serving:** modeled for specific use cases: fact/dimension tables, aggregates, data marts, or dashboard tables. Metrics must have shared definitions such as gross revenue, net revenue, cancelled bookings, and active customers.

~~~mermaid
flowchart TB
    S["Source systems"] --> R["Raw / landing"]
    R --> C["Cleaned / standardized"]
    C --> D["Curated / data marts"]
    D --> M["Semantic metrics"]
    M --> B["BI / analytics / ML"]
    R -. "Lineage and replay" .-> C
~~~

Layer names may vary across organizations. What matters is knowing what state the data is in, who owns it, which rules it has passed, and what purposes it is approved for.

## 9. Analytical Data Modeling

OLTP is typically normalized to reduce duplication and protect updates. OLAP can use dimensional modeling to make queries simpler and more efficient.

### 9.1. Star Schema

A star schema typically consists of a central fact table surrounded by dimension tables. Example for an equipment rental platform:

- **FactRental:** one row per rental transaction or line item.
- **DimCustomer:** customer attributes keyed by dimension key.
- **DimAsset:** asset type, brand, and category.
- **DimDate:** day, week, month, quarter, fiscal year.
- **DimRegion:** business region or pickup/drop-off location.

~~~mermaid
flowchart TB
    F[("FactRental")]
    C[("DimCustomer")] --> F
    A[("DimAsset")] --> F
    D[("DimDate")] --> F
    R[("DimRegion")] --> F
~~~

### 9.2. Fact Table Grain

**Grain** defines what a single row in a fact table represents. A row might represent a booking, a booking line item, a payment transaction, or an asset's active day.

Without a well-defined grain, joins can multiply rows and double-count monetary totals. Before creating a fact table, answer: does each row represent an entity or an event; what is the business key; do dimensions change over time; are there cancellations/adjustments; and at what grain are metrics calculated?

### 9.3. Slowly Changing Dimensions

A dimension such as regional address or customer segment can change over time. You must decide whether historical reports use the value at the time of the transaction or the current value.

- **Type 1:** overwrites old values; suited for corrections or attributes that do not need history.
- **Type 2:** creates a new version with effective start/end timestamps; preserves history.
- **Type 3:** stores a limited number of previous/current values; suited for specific requirements.

If historical revenue must stay tied to the region at the time the transaction occurred, Type 2 is usually more appropriate than a Type 1 overwrite.

## 10. Partitioning and File Formats

Data platforms can store vast numbers of files and partitions. Poor data organization causes queries to scan too many small files or suffer from data skew.

- Partition by fields commonly used in filters with reasonable cardinality, such as date/month.
- Avoid partitioning by nearly unique IDs, which explodes partition and file counts.
- Do not over-partition when each partition contains very little data.
- Use columnar formats like Parquet/ORC for tabular analytical workloads when supported by the engine.
- Compress using a codec and compression level that balance CPU and query speed.
- Run compaction to avoid the small-file problem.
- Leverage metadata/catalogs so query engines can prune partitions and files.
- Verify schema evolution and compatibility across writers and readers.

Example object layout:

~~~text
object-storage://analytics-data/curated/rentals/
    event_date=2026-11-18/
        region=south/
            part-0001.parquet
~~~

The path is illustrative. Partitioning by `region` only makes sense if the number of regions is bounded and queries frequently filter by region; with high cardinality or small data volumes, it can create excessive directories.

## 11. Data Quality and Pipeline Validation

A pipeline succeeding technically does not mean the data is business-correct. A job can exit with code 0 while missing payment events because a connector lost its checkpoint.

| Category | Example Rule |
| --- | --- |
| Completeness | Received record count compared against source count or expected window |
| Uniqueness | `event_id`/business key is unique per defined semantics |
| Validity | `amount` is non-negative except for permitted refunds/adjustments |
| Referential integrity | Fact keys reference valid dimensions |
| Freshness | Latest event reaches the curated layer within the deadline |
| Consistency | Monetary/record totals reconcile with source under the same definition |
| Schema | Required fields, types, nullability, and enums are valid |
| Distribution | Values do not fluctuate abnormally compared to baseline |

### 11.1. Reconciliation

Source-to-target reconciliation requires an explicit scope and point in time. For example, count committed bookings within a window based on source watermark, then compare against bookings present in the curated table after the pipeline catches up.

Do not compare two systems at mismatched timestamps and conclude data is missing. For streaming, use watermarks/window closure to determine whether enough data for a time range has arrived.

### 11.2. Handling Invalid Records

Invalid records can be routed to a quarantine/dead-letter dataset with a reason code, source ID, and metadata. Define an owner to fix root causes, a replay policy, and retention rules. Never silently drop invalid data without incrementing counters or triggering alerts.

## 12. Freshness, Watermarks, and Late-Arriving Data

Event time and processing time can differ. An offline device might upload events today that actually happened yesterday. If the pipeline relies solely on ingestion time, daily business reports will be inaccurate.

- **Event time:** when the event actually occurred at the source.
- **Ingestion time:** when the platform received the data.
- **Processing time:** when the pipeline processed it.
- **Watermark:** a threshold used by the engine to estimate that older data has arrived to an acceptable degree.

Define a late-arrival policy: how late data is accepted, whether historical partitions are updated, whether dashboards show provisional data, and when a reporting period closes.

Measure freshness end-to-end from source commit/event time to curated/serving availability; measuring job runtime alone is insufficient.

## 13. Data Governance, Catalog, and Lineage

As datasets grow, users need to know what data exists, who owns it, how metrics are defined, and whether it is approved for a given purpose.

A catalog should document dataset/table/field names and business definitions, owners/stewards, schemas/formats/partitions/locations, freshness/quality/SLAs, classification/sensitivity/retention, upstream/downstream lineage, and approved use cases.

Lineage connects sources through transformation steps to target datasets. When a revenue metric shifts, analysts can trace back source tables/event types, pipeline/job versions, transformation logic/code commits, quality checks, and the semantic models feeding the dashboard. Lineage is essential for impact analysis, auditing, and discrepancy investigations.

## 14. Securing Data When Separating OLTP and Analytics

Replicating data into a lake/warehouse expands the access surface. Users without access to the production database might gain permission to download exports or query raw tables, leading to data leaks.

Key principles:

- **Least privilege:** enforce permissions at the dataset, table, column, row, and use-case levels where supported.
- **Data minimization:** replicate only the fields needed for analytics.
- **Masking/tokenization:** obfuscate or replace identifying attributes before broad sharing.
- **Encryption:** encrypt in transit and at rest, and manage key lifecycles.
- **Network isolation:** separate the data plane, use private endpoints, and enforce egress policies as needed.
- **Audit:** log sensitive queries, exports, policy changes, and catalog access.
- **Retention/deletion:** enforce across raw, curated, caches, backups, and derived datasets.
- **Environment separation:** test/sandbox environments must not automatically receive full production data.
- **Purpose limitation:** data is used strictly for approved purposes.

### 14.1. Pseudonymization Is Not Anonymization

Replacing a customer ID with a token reduces direct identification, but if a mapping table exists or attributes can be combined to re-identify individuals, the data remains sensitive. Classify data based on realistic linkability.

### 14.2. Data Deletion and Analytical Copies

Deletion/update requests may need to propagate across sources, CDC, raw, curated, data marts, caches, exports, and backups according to deadlines and policies. Design proper deletion propagation and tombstones. Never assume deleting a row in OLTP automatically removes all downstream copies.

## 15. Isolating Workloads and Protecting Transactional Databases

The goal is to prevent analytical queries from competing for resources with live transactions. Applicable techniques include:

1. Use a dedicated read replica for read-only queries if staleness tolerance and load allow.
2. Stream via CDC to a lake/warehouse to eliminate direct production queries.
3. Use a separate replica/export for initial ingestion and batch extraction.
4. Enforce query, connection, concurrency, and execution time limits on any shared read source.
5. Schedule exports during low-traffic windows or extract incrementally via watermarks.
6. Use query monitoring to detect heavy reports.
7. Separate backups, maintenance, and batch jobs from peak transaction windows when possible.

A read replica still shares replication overhead and can lag under heavy reporting. For large analytics workloads, an independent warehouse/lakehouse generally provides stronger isolation.

## 16. Batch Loads, Incremental Loads, and Backfills

**Full load** extracts the entire dataset, suited for initial bootstrap or small tables. For large tables, frequent full scans tax sources and increase transfer/storage costs.

**Incremental load** extracts only changes since the last watermark/checkpoint. You must define watermarks based on updated time, transaction log position, or sequence; handle late updates or duplicate timestamps; represent deletes/tombstones; ensure idempotency on re-runs; and advance checkpoints only after the destination commits.

Relying solely on `updated_at` timestamps can miss updates due to low timestamp resolution, clock skew, or delayed transaction commits. Log-based CDC solves some of these issues, though you still need to understand connector semantics.

**Backfill** reloads a historical range or older dataset. It can compete for resources with live pipelines. Set quotas, lower priority, partition by time, track progress, and ensure backfills do not overwrite newer data.

## 17. Orchestration and Pipeline Dependencies

A pipeline may encompass ingestion, validation, transformation, enrichment, aggregation, and publishing. An orchestrator tracks dependencies, retries, timeouts, states, and schedules.

~~~mermaid
flowchart TD
    A["Ingest source changes"] --> B["Validate schema and completeness"]
    B --> C{"Quality passed?"}
    C -- "No" --> Q["Quarantine + alert"]
    C -- "Yes" --> D["Transform / normalize"]
    D --> E["Build curated tables"]
    E --> F["Reconcile source and target"]
    F --> G{"Reconciliation passed?"}
    G -- "No" --> Q
    G -- "Yes" --> H["Publish semantic dataset"]
~~~

A pipeline must distinguish transient errors that can be retried; schema errors requiring producer/data owner intervention; quality errors requiring quarantine or blocking publication; and downstream failures requiring preserved state and safe re-runs. Partial completion must be tracked with metadata to avoid publishing incomplete datasets.

Never mark a dataset as fresh merely because the scheduler job succeeded if CDC is lagging or quality gates have not passed.

## 18. Data Products and Ownership

A data platform should not be a collection of unowned tables. Under a domain-oriented or data mesh approach, domains can own data products while relying on a shared platform and cross-domain standards.

A data product should define an owner, target consumers, business definitions, schema contracts, freshness/completeness/availability SLOs, quality checks, lineage, classification, permissions, retention, versioning/deprecation policies, and supported access patterns.

Not every organization needs to implement a full data mesh. Domain ownership principles can be adopted without building a distributed platform that exceeds operational capacity.

## 19. Performance and Cost Optimization

Separating OLTP from analytics introduces additional systems, storage, pipelines, and data copies. Isolation benefits must be weighed against total cost of ownership.

Cost drivers include OLTP databases/replicas/log retention; CDC connectors/brokers/partitions/data transfer; object storage tiers and requests; warehouse/lakehouse compute; ETL/ELT/stream processing; catalog/governance/quality/lineage tooling; BI concurrency; logging/metrics/auditing; and on-call operations.

Optimization strategies:

- Replicate only required fields and tables.
- Use incremental loads/CDC instead of repeated full scans.
- Partition according to query access patterns while avoiding excessive cardinality.
- Compact small files and choose appropriate columnar formats.
- Auto-scale or auto-suspend compute that does not need to run continuously when supported.
- Apply workload management and concurrency limits for expensive queries.
- Select retention and storage tiers based on access frequency.
- Track cost per query, cost per dataset, and cost per successful pipeline run.
- Identify owners to decommission unused datasets.

Do not delete raw data too early if it is needed for replay, auditing, or fixing transformations. Conversely, keeping all data indefinitely creates privacy risks and uncontrolled costs.

## 20. Data Platform Reliability and Recovery

An analytics platform may tolerate delayed data within a bounded window, but it must never silently lose data.

Design durable checkpoints/offsets for CDC and stream consumers; retries with backoff, idempotent sinks, and quarantines; source/target reconciliation; replay/backfill from logs/archives; backups for metadata, catalogs, and configurations; rebuilding curated layers from raw where possible; cross-region replication/backups aligned with RPO/RTO; and runbooks for connector lag, full brokers, schema changes, or warehouse outages.

### 20.1. RPO/RTO vs. Freshness SLO

- **Freshness SLO:** how soon new data must appear in the analytics layer.
- **RPO:** how much data can be lost when recovering from an outage.
- **RTO:** how long it takes to restore the pipeline or dataset.
- **Completeness SLO:** the percentage or count of records that must be fully processed.

A dashboard delayed by 10 minutes violates freshness without losing data. A pipeline that loses its checkpoint can permanently drop records even while the dashboard still looks fresh up to a few minutes ago. Track each dimension separately.

## 21. Architecture Example: Equipment Rental Platform

Suppose a system has a Booking DB, Payment DB, Asset DB, and transactional applications. Teams need reports on revenue, asset utilization, and customer behavior.

| Source | OLTP Responsibility | Analytical Data |
| --- | --- | --- |
| Booking DB | Authoritative booking status and rental schedule | Booking facts, rental duration, cancellations |
| Payment DB | Transactions, authorization, capture, refunds | Payment facts, net/gross revenue |
| Asset DB | Asset condition and availability | Utilization, maintenance history |
| Customer service | Profiles and PII access | Tokenized/segmented dimensions per policy |

~~~mermaid
flowchart TB
    subgraph OLTP["Operational systems"]
        B[("Booking DB")]
        P[("Payment DB")]
        A[("Asset DB")]
        C[("Customer service")]
    end
    B --> CDC["CDC / event ingestion"]
    P --> CDC
    A --> CDC
    C --> MASK["PII filter / tokenization"]
    CDC --> RAW[("Raw object storage")]
    MASK --> RAW
    RAW --> TRANS["ELT + quality + reconciliation"]
    TRANS --> CUR[("Curated lakehouse / warehouse")]
    CUR --> MART["Rental / Revenue data marts"]
    MART --> BI["BI dashboards"]
    MART --> ML["Forecasting / ML"]
~~~

The BFF or transactional API never queries the warehouse to confirm a booking. The warehouse answers analytical questions; OLTP retains decision authority and commits transactions.

### 21.1. Choosing Freshness

| Use case | Assumed Target Freshness | Approach |
| --- | --- | --- |
| Rapid fraud detection | Seconds to under a minute | Dedicated event/stream pipeline |
| Operations dashboard | 1–5 minutes | CDC + micro-batch/stream processing |
| Daily revenue reporting | Hourly or end-of-day | Batch/ELT with reconciliation |
| Forecast model training | Daily/weekly | Curated historical dataset |
| Accounting reconciliation | Per closing window | Batch with completeness gate and audit |

These are illustrative targets that must be validated against business requirements. Fraud detection may require an online feature store and dedicated serving rather than a streaming dashboard.

### 21.2. Incident Controls

- CDC connector stops reading: alert on log lag and protect transaction logs from unbounded growth.
- Payment schema changes: detect contract incompatibility, quarantine records, and notify the owner.
- Warehouse overloaded: keep ingestion/raw durable, throttle publishing and query concurrency.
- PII leaks into raw: block via quality/security gates and handle under incident policy.
- Reconciliation mismatch: keep the dataset in an unverified state and avoid publishing metrics as complete data.

## 22. Testing the Data Platform

Testing goes beyond confirming that a job exits cleanly.

- **Contract tests:** schema, field semantics, versions, and compatibility.
- **Data quality tests:** uniqueness, nulls, ranges, relationships, and domain rules.
- **Volume tests:** peak ingestion rate, batch size, file count, and query concurrency.
- **Freshness tests:** source event reaching curated/serving within SLO.
- **Failure tests:** connector restarts, broker outages, job crashes, partial writes, and retries.
- **Replay/backfill tests:** re-running windows without producing duplicates or overwriting newer data.
- **Security tests:** dataset/table/column permissions, masking, exports, and auditing.
- **Reconciliation tests:** comparing source and target at corresponding watermarks.
- **Recovery tests:** restoring metadata, checkpoints, raw/curated layers, and rebuilding.
- **Cost tests:** measuring ingestion, transformation, storage, query, and idle compute costs.

Pipelines should include test fixtures covering duplicates, late events, deletes, timezones, currency conversions, empty batches, and schema evolution.

## 23. Common Design Mistakes

| Mistake | Consequence | Prevention |
| --- | --- | --- |
| Allowing BI to query production OLTP directly | Analytical queries slow down transactions | Separate warehouse/lake or strictly capped read replica |
| Using a read replica as the entire analytics platform | Replication lag, heavy scans, resource contention | Stream via CDC to a dedicated analytics platform at scale |
| Repeatedly full-extracting every table | High source load and transfer costs | Incremental/CDC loads, watermarks, and partitioning |
| Lacking business definitions | Metrics share names but yield different numbers | Semantic layer, owners, and data contracts |
| Treating CDC records as business events | Misinterpreting business transitions | Distinguish row mutations from domain events |
| Ignoring delete/update semantics | Stale or incorrect downstream records | Tombstones, merges, and retention policies |
| Not handling late-arriving data | Inaccurate daily reports | Event time, watermarks, and correction windows |
| No quality gates | Dashboards publish missing/wrong data | Completeness checks, reconciliation, and quarantine |
| Keeping only curated data, dropping raw too early | Cannot replay when transforms have bugs | Retain raw data per replay needs and policy |
| Retaining raw data indefinitely | Escalating costs and privacy risks | Lifecycle rules, minimization, and deletion propagation |
| Uncontrolled partitioning/small files | Slow queries and heavy metadata overhead | Partition design, compaction, and columnar formats |
| Copying unfiltered PII to analytics | Expanded data exposure surface | Masking, tokenization, and least privilege |
| Unversioned pipelines/schemas | Cannot reproduce historical metrics | Version code, schemas, configs, and lineage |
| Unbounded backfills | Impacts live ingestion | Priority, quotas, time windows, and resource isolation |
| Measuring only job success | Undetected data loss or staleness | Freshness/completeness/quality SLOs |

## 24. Design and Implementation Process

1. **Identify use cases:** who analyzes what, at what granularity, and with what freshness?
2. **Classify workloads:** transactional, operational reporting, analytics, ML, or archival.
3. **Select source of truth:** which domain/database owns each field and business transition?
4. **Define data contracts:** schemas, keys, semantics, event time, deletes, versioning, and owners.
5. **Choose ingestion:** initial full snapshot, batch, micro-batch, streaming, or CDC.
6. **Choose storage:** raw landing, data lake, warehouse, lakehouse, or hybrid.
7. **Design transformations:** ETL/ELT, standardization, models, grain, quality, and reconciliation.
8. **Set freshness/completeness SLOs:** end-to-end and per dataset.
9. **Design security/governance:** classification, masking, IAM, catalog, lineage, retention, and deletion.
10. **Isolate workloads:** OLTP sources, ingestion, transformation, and query compute.
11. **Set up CI/CD/orchestration:** versioning, testing, retries, backfills, and promotions.
12. **Measure and optimize:** cost, query performance, freshness, lag, quality, and recovery.
13. **Run failure drills:** connector lag, schema breaks, full brokers, restores, and replays.

## 25. Well-Architected Review

| Pillar | Design Questions |
| --- | --- |
| **Reliability** | Are CDC/checkpoints recoverable? Are backfills/replays idempotent? Are reconciliation and backup/restore in place? |
| **Security** | Is PII minimized/masked? Are permissions separated across raw/curated/serving? Do deletions and retention propagate across all copies? |
| **Performance Efficiency** | Is OLTP protected? Do ingestion lag, query latency, and concurrency meet targets? Are partitioning and file formats appropriate? |
| **Cost Optimization** | Are there repeated full scans, small files, unbounded storage, idle compute, or uncapped queries? What is the cost per dataset/use case? |
| **Operational Excellence** | Are catalog, lineage, owners, quality gates, freshness alerts, replay/backfill runbooks, and pipeline versioning in place? |

### Acceptance Checklist

- [ ] OLTP and OLAP have clear workload boundaries, owners, and SLOs.
- [ ] Analytical queries do not have unrestricted access to production databases.
- [ ] Every dataset has a source of truth, contract, and business definition.
- [ ] Batch/CDC/streaming is selected based on freshness, capacity, and operational readiness.
- [ ] CDC monitors log positions/lag and handles schema changes.
- [ ] Raw, cleaned, and curated layers have distinct purposes, permissions, and retention.
- [ ] Analytical models define explicit grain, keys, and metric definitions.
- [ ] Partitioning, file formats, and compaction are tested against realistic queries.
- [ ] Quality, completeness, freshness, and reconciliation have explicit rules and owners.
- [ ] PII is minimized, masked, encrypted, and access-controlled.
- [ ] Deletes, corrections, and late-arriving data propagate properly.
- [ ] Pipelines implement checkpoints, retries, idempotency, quarantine, and replay.
- [ ] Backfills do not degrade live ingestion or OLTP.
- [ ] Catalog, lineage, cost dashboards, and data product owners are established.
- [ ] Restore/rebuild procedures and incident runbooks have been rehearsed.

## 26. Practice Exercise

An e-commerce platform operates a transactional database managing customers, orders, payments, and inventory. During peak hours, revenue dashboards and product analytics significantly slow down the database. Executives want dashboards updated within 2 minutes; the finance team requires an end-of-day closing report that can be reconciled; and the data science team needs historical data to forecast demand.

Design the following:

1. Which workloads are OLTP, operational analytics, OLAP, and ML?
2. Should you use read replicas, CDC, batch, or streaming for each use case?
3. Design the data flow from the source database to raw, cleaned, curated, and serving layers.
4. How would you define freshness, completeness, and reconciliation for the 2-minute dashboard?
5. Which fields should be tokenized/masked before analysts access them?
6. How would you handle updates, deletes, late events, and schema evolution?
7. Define the grain for the sales fact table and the product/customer/date dimensions.
8. How would you backfill historical data without pressuring production or creating duplicates?
9. Which metrics help detect pipeline lag, data quality issues, and rising costs?
10. How would you verify that dashboard queries no longer affect the transactional database?

A sound solution might use CDC for transactional changes, raw object storage as the landing zone, ELT to build curated tables/warehouse models, micro-batch or streaming for the 2-minute dashboard, and batch with reconciliation for financial closing. Data science consumes governed historical datasets with dedicated permissions and purpose limits. Freshness and completeness must be proven with metrics rather than relying solely on pipeline schedules.

**Key takeaway:** OLTP optimizes for correct, fast-response transactions; OLAP optimizes for large scans, aggregations, and analysis. Separating these workloads with appropriate ingestion, storage, and compute protects transactional systems, but introduces requirements around synchronization, freshness, quality, governance, security, and cost. A well-architected data platform tracks where data comes from, how it is transformed, who can use it, how fresh it is, and how it can be recovered.
