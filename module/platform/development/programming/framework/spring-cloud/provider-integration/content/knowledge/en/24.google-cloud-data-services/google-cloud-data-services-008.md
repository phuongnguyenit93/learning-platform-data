# Distinguishing Transactional Databases from the BigQuery Analytics Warehouse

## Learning Objectives

In the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, Spring Boot integrates managed services from AWS, Azure, and Google Cloud for data storage, messaging, analytics, and access protection. On Google Cloud, a key architectural decision is choosing where to record business transactions and where to analyze data generated from those transactions.

This lesson helps you distinguish **transactional databases (OLTP)** from **analytical data warehouses (OLAP/data warehouse)**, understand BigQuery's role, and design a combined architecture:

1. Distinguish the goals, access patterns, and characteristics of OLTP vs. OLAP.
2. Choose Cloud SQL, Spanner, or Firestore for operational data according to the business model.
3. Understand how BigQuery is optimized for scanning, aggregation, joins, and large-scale analytics.
4. Understand why BigQuery supports ACID transactions yet is still not the default choice for checkout or row-by-row CRUD.
5. Design data pipelines from transactional databases to BigQuery via batch, CDC, or event streaming.
6. Define the source of truth, data freshness, event ordering, idempotency, and handling of late-arriving data.
7. Organize raw, curated, and mart layers; select partitioning, clustering, and analytical schemas.
8. Integrate Spring Boot with operational databases and BigQuery along clear responsibility boundaries.
9. Control costs, access permissions, data quality, and reconciliation capabilities.
10. Choose architectures based on latency, consistency, scale, and cost requirements.

## 1. Two Workload Types, Two Design Goals

### 1.1. What Is OLTP?

OLTP (Online Transaction Processing) serves operational actions inside an application: creating orders, confirming payments, updating inventory, logging in, updating profiles, or making bookings.

A typical OLTP request:

- Reads a few records by primary key or index.
- Validates business rules.
- Writes a few related records.
- Commits or rolls back as a single transaction.
- Returns a result to the user quickly.

For example, when a customer books a rental asset, the system must check availability, hold the slot, create a reservation, and record payment status. If two customers book the same time window concurrently, the system needs concurrency control so two conflicting reservations are not confirmed.

OLTP databases are designed to handle many concurrent requests, key-based lookups, small updates, and transactions with crisp boundaries.

### 1.2. What Is OLAP?

OLAP (Online Analytical Processing) serves analytics and decision support. Users typically pose questions across large volumes of data:

- Revenue by month, region, or customer segment.
- Cancellation rate by marketing channel.
- Average time from booking to confirmation.
- Inventory and seasonal utilization.
- Cohort, funnel, and behavioral analysis over time.
- Detecting trends or anomalies over months or years of history.

An OLAP query may scan millions or billions of rows, join multiple datasets, group, aggregate, and use window functions. The output is typically a summary table much smaller than the input data.

BigQuery is designed for this query style: columnar storage, decoupled compute and storage, and distributed query execution across many workers. [BigQuery documentation describes its storage/compute architecture and parallel processing](https://docs.cloud.google.com/bigquery/docs/introduction).

### 1.3. Comparing OLTP and OLAP

| Criterion | OLTP | OLAP |
| --- | --- | --- |
| Goal | Execute business transactions | Analyze and aggregate |
| Unit of access | A few rows/documents by key | Many rows and many columns |
| Read/write | Small, frequent reads and writes | Broad reads, aggregations; batch or streaming ingestion |
| Transactions | Critical per business operation | Supports transactions for analytical data tasks, but not optimized for row-by-row CRUD |
| Schema | Typically normalized around business relationships | Typically denormalized around analytical questions |
| Index/partition | Indexes for lookups and updates | Partitioning, clustering, column pruning |
| Target latency | Fast response for user requests | Seconds to minutes depending on query and SLA |
| Concurrency | Many short transactions, contention on hot data | Many parallel analytical queries, potentially queued |
| Users | Backend services, business applications | Analysts, BI, data scientists, reporting |
| Examples | Creating a reservation, deducting inventory | Monthly revenue, occupancy rate |

There is no rule saying OLTP only touches a few rows or OLAP is strictly read-only. The difference lies in access patterns and optimization goals. A report reading relatively few rows can still be OLAP; a transaction writing several tables is still OLTP.

### 1.4. Example of the Same Business Domain Seen from Both Workloads

Suppose an application manages bookings:

**OLTP request:** a customer confirms reservation R-1001.

1. Read the reservation by ID.
2. Verify current status is PENDING.
3. Verify payment conditions.
4. Update reservation status to CONFIRMED.
5. Record payment reference and outbox event.
6. Commit the transaction and return the result.

**OLAP query:** a manager wants monthly confirmation rates over 24 months.

1. Read millions of historical reservations.
2. Group by month and booking channel.
3. Count total reservations and confirmed reservations.
4. Compute rates and compare trends.
5. Return the summary table to a dashboard.

If you run this analytical query on the operational database, it can compete for CPU, I/O, memory, and connections with checkout requests. If you use BigQuery to update individual reservation statuses per request, you are forcing an analytical warehouse into an access pattern it was not built for.

## 2. BigQuery Is an Analytics Warehouse, Not a Checkout Database

### 2.1. What Is BigQuery Optimized For?

BigQuery is a managed data warehouse using GoogleSQL to analyze large datasets. Key architectural traits:

- **Columnar storage:** queries needing only a subset of columns read just those columns rather than entire rows.
- **Separation of storage and compute:** storage capacity and query compute scale independently.
- **Distributed query execution:** scanning, joining, and aggregating work is spread across many workers.
- **Serverless operations:** users do not provision database machines or shard query clusters manually.
- **Analytics ecosystem:** integrates with BI, machine learning, geospatial analytics, external tables, and data pipelines.

These traits make BigQuery effective for large-scale analytics. [BigQuery storage uses a columnar format to support query analytics](https://docs.cloud.google.com/bigquery/docs/best-practices-storage).

### 2.2. Why Is BigQuery Not the Default Choice for OLTP?

A checkout application needs to read/write single records by ID and finish short transactions. BigQuery focuses on scanning and processing large datasets. Practical differences:

- Every query runs as a query job; you should not launch a query job for each individual row update on a strict-latency request path.
- DML such as UPDATE, DELETE, and MERGE is supported, but DML is designed for batch/set-based modifications rather than continuous single-row updates.
- Transactions can hold table-level locks when executing mutating DML; concurrent updates on the same table face specific limits.
- Query costs can depend on bytes read or allocated compute capacity.
- BigQuery does not replace the business constraint enforcement and transaction boundaries of operational databases.

Google recommends avoiding row-by-row DML updates or inserts because that treats BigQuery like an OLTP system; batch changes instead or use a database built for OLTP. [Query performance best practices](https://docs.cloud.google.com/bigquery/docs/best-practices-performance-compute).

### 2.3. BigQuery Still Has ACID Transactions

Avoid the misconception that BigQuery has no transactions at all. BigQuery supports:

- Implicit transactions on a single DML statement: changes commit when the statement succeeds.
- Multi-statement transactions with BEGIN TRANSACTION, COMMIT TRANSACTION, and ROLLBACK TRANSACTION.
- Atomic mutations across multiple tables within a transaction's scope.
- Snapshot isolation for supported operations.

Example updating a summary table and writing an audit record inside the same analytical transaction:

~~~sql
BEGIN TRANSACTION;

UPDATE analytics.mart.monthly_revenue
SET reviewed = TRUE
WHERE month_key = DATE '2026-10-01';

INSERT INTO analytics.audit.review_log
    (month_key, action, reviewed_at)
VALUES
    (DATE '2026-10-01', 'REVIEWED', CURRENT_TIMESTAMP());

COMMIT TRANSACTION;
~~~

This transaction fits a data-processing task or analytical data correction. It does not turn BigQuery into a runtime store for individual checkout requests.

Important limitations of multi-statement transactions:

- A transaction must be contained within a single query, unless using session mode.
- Transactions cannot be nested.
- DDL affecting permanent entities, such as creating or dropping tables, is not supported inside a transaction.
- When a transaction mutates (updates/deletes) a table, BigQuery acquires a table-level lock; other concurrent mutating transactions on the same table may abort.
- Multi-statement transactions have lower concurrency limits than standalone DML statements.
- Transactions have limits on the number of mutated tables and partition modifications.

Therefore, use BigQuery transactions for well-bounded analytical data processing tasks; do not substitute them for high-frequency, short application transactions. [Details on transactions and concurrency](https://docs.cloud.google.com/bigquery/docs/transactions).

### 2.4. Common Misconceptions

| Claim | Assessment |
| --- | --- |
| BigQuery does not support transactions | False: supports ACID transactions for specified operations |
| Since it has ACID, BigQuery can serve as the checkout database | False: ACID does not imply suitability for point updates and OLTP latency |
| DML can update rows so it can replace Cloud SQL | False: DML is optimized for set-based changes and has concurrency limits |
| BigQuery only stores stale batch data | False: supports the Storage Write API, CDC, and streaming analytics |
| Data written to BigQuery is always immediately in sync with the source database | False: freshness depends on load/CDC/streaming pipelines and configuration |
| BigQuery is only for dashboards | False: also used for ELT, ML, geospatial, data sharing, and ad hoc analysis |

## 3. Choosing an Operational Database on Google Cloud

BigQuery is the analytical destination; applications still need a system of record for operational state. Choosing an OLTP store depends on data model, consistency, transactions, scale, and access patterns.

### 3.1. Cloud SQL

Cloud SQL is a managed relational database service for PostgreSQL, MySQL, and SQL Server.

Good fit when:
- The application has a relational model, foreign keys, and familiar SQL.
- Business transactions require ACID guarantees.
- Workload scale is regional or zonal and fits Cloud SQL's scaling capacity.
- The system already uses PostgreSQL/MySQL/SQL Server and wants reduced operational overhead.

Examples: reservations, payments, customer profiles, invoices, and inventory with explicit relationships.

[Cloud SQL is a managed relational database service](https://docs.cloud.google.com/sql/docs/introduction).

### 3.2. Spanner

Spanner is a distributed relational database supporting strong transactions and horizontal scaling for workloads needing wide availability and consistency.

Good fit when:
- The application needs a relational model and ACID transactions.
- Transaction volume or distributed scale exceeds typical single-region database models.
- Strong/external consistency is required across distributed replicas.
- The system has global availability and scale requirements.

Spanner provides read-write and read-only transactions; strong consistency guarantees help applications build distributed business logic. In return, architecture, schemas, and key designs must be tailored to Spanner's characteristics. [Spanner transactions and external consistency](https://docs.cloud.google.com/spanner/docs/transactions).

### 3.3. Firestore

Firestore is a managed NoSQL document database. It fits:
- Flexible document data.
- Mobile/web apps needing realtime listeners and offline support.
- User profiles, application state, content, or nested structured data.
- Workloads whose query patterns match Firestore's document model and indexes.

Firestore supports ACID transactions across multiple documents. However, its collection/document model and querying differ from relational databases; do not choose it merely to avoid SQL schemas. [Firestore overview and transaction capabilities](https://docs.cloud.google.com/firestore/native/docs/overview).

### 3.4. Bigtable and Specialized Options

Cloud Bigtable fits key-based, high-throughput workloads, time-series data, or wide-column storage. It is not a direct replacement for a relational transactional database or the BigQuery warehouse.

Memorystore fits as a cache/in-memory data store for ultra-fast access, not as the sole source of truth for critical transactions.

### 3.5. Selection Table

| Service | Model | Primary workload | When to consider |
| --- | --- | --- | --- |
| Cloud SQL | Relational | OLTP | Traditional SQL apps, regional transactions |
| Spanner | Distributed relational | Large-scale OLTP | Needs strong consistency and distributed scale |
| Firestore | Document NoSQL | OLTP/document | Mobile/web backends, documents, and realtime |
| Bigtable | Wide-column | High-throughput operational data | Key lookups, time-series, very large datasets |
| BigQuery | Columnar warehouse | OLAP | Reporting, aggregations, BI, ML, and historical analytics |

This is not a ranking table. One system can use multiple services simultaneously as long as each plays its proper role.

## 4. Hybrid Architecture Combining OLTP and BigQuery

### 4.1. Overall Data Flow

The application writes transactions to the operational database. Data flows into BigQuery via CDC, event streaming, or batch ingestion. BigQuery holds data for analytics; dashboards and analysts query that data.

~~~mermaid
flowchart TD
    USER["Web / Mobile / Partner API"] --> API["Spring Boot services"]
    API --> OLTP["OLTP database<br/>Cloud SQL / Spanner / Firestore"]
    API --> OUTBOX["Outbox event in same OLTP transaction"]
    OUTBOX --> PUB["Pub/Sub"]
    PUB --> FLOW["Dataflow / streaming transform"]
    OLTP --> CDC["Datastream CDC"]
    CDC --> RAW["BigQuery raw / replicated tables"]
    FLOW --> RAW
    RAW --> CURATED["Curated analytical tables"]
    CURATED --> MART["Data marts / aggregate tables"]
    MART --> BI["Looker / dashboards / analyst"]
    CURATED --> APIQ["Analytics API / scheduled reports"]
~~~

Core principles:

1. The operational database is the canonical store for business state.
2. BigQuery is the place to analyze transformed and standardized data.
3. Data transfer pipelines must support retries, observability, and duplicate handling.
4. Dashboards accept freshness within an agreed SLA.
5. Never expect a single Spring transaction to commit atomically across both Cloud SQL and BigQuery.

### 4.2. Separating the Command Path and Analytics Path

**Command path** handles state-changing actions:
- Creating reservations.
- Confirming payments.
- Canceling orders.
- Deducting inventory.
- Validating invariants and committing transactions.

**Analytics path** handles analytical questions:
- Reservation success rate.
- Daily revenue.
- Regional utilization.
- Cohort analysis.
- Demand forecasting.

Do not let dashboard queries scanning billions of rows run on the operational database's connection pool. Do not make the checkout API wait for a BigQuery query job to finish.

### 4.3. Source of Truth and Analytical Replicas

For each business entity, define which system is the source of truth. Examples:

| Data | Source of truth | Analytical replica |
| --- | --- | --- |
| Reservation status | Cloud SQL or Spanner | BigQuery reservation fact |
| Payment status | Payment service/OLTP database | BigQuery payment events |
| Customer profile | Operational database | BigQuery customer dimension |
| Inventory availability | Operational database | BigQuery inventory snapshot/history |
| Clickstream | Event pipeline/Pub/Sub | BigQuery event fact |

If BigQuery has not yet received a change, checkout state must still be decided from the operational database. Do not read BigQuery replicas to verify inventory or confirm payments immediately after commit.

### 4.4. Avoid Direct Dual-Writes to Both Systems

An anti-pattern is:

1. Spring service commits a transaction to Cloud SQL.
2. Spring service also writes a row to BigQuery.
3. Return success only if both calls succeed.

If step 1 succeeds and step 2 fails, the system has a committed transaction missing from analytics. If step 2 succeeds and step 1 rolls back, BigQuery contains data absent from the source of truth. The two systems do not share a single default transaction manager.

Better solutions:
- Transactional outbox.
- CDC from transaction logs.
- Event-driven pipelines with idempotency.
- Batch extract/load with watermarks and reconciliation.

This turns analytical updates into an asynchronous pipeline that can be retried and audited.

## 5. Moving Data with Transactional Outbox and Pub/Sub

### 5.1. What Is a Transactional Outbox?

A transactional outbox writes business data and the event to be published inside the same database transaction. A separate publisher reads the outbox and sends events to Pub/Sub.

If the business transaction rolls back, the outbox event rolls back too. If the transaction commits, both business data and event record persist for the publisher to dispatch later.

### 5.2. Spring Boot Example with Spring Data JPA

Suppose the service uses Cloud SQL PostgreSQL and Spring Data JPA. Both repositories must share the same datasource and transaction manager:

~~~java
@Service
public class ReservationService {

    private final ReservationRepository reservations;
    private final OutboxEventRepository outbox;

    public ReservationService(
            ReservationRepository reservations,
            OutboxEventRepository outbox) {
        this.reservations = reservations;
        this.outbox = outbox;
    }

    @Transactional
    public Reservation confirm(UUID reservationId) {
        Reservation reservation = reservations.findById(reservationId)
                .orElseThrow(() ->
                        new IllegalArgumentException("Reservation not found"));

        reservation.confirm();

        OutboxEvent event = OutboxEvent.create(
                UUID.randomUUID(),
                "ReservationConfirmed",
                reservation.getId().toString(),
                reservation.toAnalyticsPayload());

        outbox.save(event);
        return reservations.save(reservation);
    }
}
~~~

Within the same transaction, the service updates the reservation and persists the outbox event. If an error occurs before commit, both changes roll back.

toAnalyticsPayload() should produce a stable event contract rather than serializing an entire JPA entity that may hold lazy relations, sensitive data, or internal fields.

### 5.3. Publishers and Duplicate Delivery

A scheduled publisher or dedicated worker:
1. Reads unpublished outbox events.
2. Publishes messages to Pub/Sub.
3. Waits for broker acknowledgment.
4. Marks events as published.
5. Retries on transient errors.

A failure window exists: the publisher sends the message successfully but crashes before marking the outbox row. The next run may re-send the same event. Therefore, outbox publishers typically produce **at-least-once delivery**; consumers must be idempotent.

Events should contain:
- A unique event_id.
- event_type and schema_version.
- aggregate_id such as reservation ID.
- occurred_at as the time the business event occurred.
- published_at or pipeline ingestion timestamp.
- A payload containing the fields needed for analytics.

Do not use the message arrival timestamp as a substitute for the business occurrence time. Having both timestamps lets you measure pipeline lag and handle late-arriving events.

### 5.4. Pub/Sub and Dataflow

Pub/Sub delivers events to subscribers. Dataflow can read messages, validate schemas, enrich or transform them, and write to BigQuery. Google provides a Pub/Sub to BigQuery template for JSON messages matching a table schema; when complex transformations are needed, use a custom Dataflow pipeline. [Dataflow Pub/Sub to BigQuery template](https://docs.cloud.google.com/dataflow/docs/guides/templates/provided/pubsub-to-bigquery).

A pipeline can:
- Validate event_id and schema version.
- Normalize timestamps and currencies.
- Filter or route malformed messages to a dead-letter path.
- Enrich with dimensions from caches/reference data.
- Write raw events to BigQuery.
- Emit metrics on throughput, lag, duplicates, and invalid records.

### 5.5. Idempotency and Deduplication

Pub/Sub and event pipelines can redeliver messages. Append-only BigQuery tables can receive duplicates if a consumer writes the same event twice.

Strategies include:
- Retaining event_id and deduplicating during queries/curation.
- Using staging tables followed by MERGE on event ID.
- Using appropriate sink/stream semantics and checkpoints.
- Ensuring transformations can re-run without distorting aggregations.
- Persisting processing state by batch/event ID in an appropriate store.

Example selecting the latest record per event_id:

~~~sql
CREATE OR REPLACE TABLE analytics.curated.reservation_events AS
SELECT * EXCEPT(row_number)
FROM (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY event_id
            ORDER BY ingested_at DESC
        ) AS row_number
    FROM analytics.raw.reservation_events
)
WHERE row_number = 1;
~~~

This is the curation step; the raw layer keeps original events for auditing and replay.

## 6. Moving Data with Change Data Capture (CDC)

### 6.1. How Does CDC Differ from Business Events?

CDC captures database-level changes, typically from transaction logs or replication logs. It records inserts, updates, and deletes on source tables.

Business events express domain meaning—for example, ReservationConfirmed. CDC expresses data mutations—for example, a reservation row whose status changed from PENDING to CONFIRMED.

| Criterion | Domain event / Outbox | CDC |
| --- | --- | --- |
| Meaning | States what happened in the business domain | States which row changed |
| Payload | Defined by the application | Follows source table schema and connector |
| Database schema coupling | Lower if event contracts stay stable | High; schema changes must be managed |
| Captures updates/deletes | Only for events emitted by the app | Captures directly from database logs |
| Use cases | Business analytics, event-driven integration | Table replication, data sync, change auditing |
| Tools | Outbox, Pub/Sub, Dataflow | Datastream or CDC platform |

It does not have to be either-or for every case. A system can use CDC to replicate tables and domain events to convey business semantics.

### 6.2. Datastream to BigQuery

Datastream supports capturing changes from sources like Cloud SQL for MySQL and PostgreSQL and streaming them into BigQuery. The BigQuery destination uses the Storage Write API and CDC functionality to apply changes. [Datastream BigQuery destination](https://docs.cloud.google.com/datastream/docs/destination-bigquery).

Common write modes:

- **Merge:** BigQuery mirrors the current state of source tables; requires primary keys to merge changes.
- **Append-only:** stores change events such as inserts, updates, and deletes to preserve change history.

Choose merge when you need an analytical mirror of current state. Choose append-only when you need change history and want to build custom temporal/audit models. Carefully review connector, source database, and schema limitations before deploying.

### 6.3. Full Backfill and Ongoing Replication

CDC typically has two phases:

1. **Backfill:** copies existing rows from source tables.
2. **Change replication:** continuously reads new changes from transaction logs.

Define checkpoints/watermarks and rules for handling changes occurring during backfill. Do not assume every table is fully synced just because a stream is running; monitor per-table status and replication lag.

### 6.4. Schema Evolution

When a source table changes schema:
- Determine whether new fields are nullable or required.
- Check data types and type conversions.
- Assess destination tables and consumer queries.
- Version event/schema contracts if emitting domain events.
- Roll out changes in backward-compatible order.
- Monitor CDC errors and rejected records.

Do not arbitrarily alter field types if dashboards, views, scheduled queries, or downstream consumers depend on the old schema.

## 7. Batch Ingestion and ELT

### 7.1. When to Choose Batch?

Batch fits when:
- Reports do not need second-by-second updates.
- Source systems can export scheduled snapshots.
- Historical data needs backfilling.
- Sources are CSV, Avro, or Parquet files.
- You want simpler pipelines and fewer tiny event writes.

Common batch flow:
1. Export source data by time window or watermark.
2. Write files to Cloud Storage.
3. Load files into a BigQuery staging table via load jobs.
4. Validate schema, row counts, and malformed records.
5. Transform into curated tables.
6. Advance the watermark after batch completion.

### 7.2. Incremental Loads Using Watermarks

Without CDC, you can use an updated_at column or monotonic sequence to extract changes since the previous run.

Logical flow:
- Store the last committed watermark.
- Query the source with updated_at > last_watermark and updated_at <= batch_upper_bound.
- Export that slice of data.
- Load into a staging table.
- MERGE staging into the curated table by primary key.
- Update the watermark only after the merge succeeds.

Use a small overlap window or a stable sequence to reduce the risk of missing records due to clock skew or late commits. MERGE must be idempotent; re-running a batch must not create duplicates or regress newer state.

### 7.3. Raw, Curated, and Mart Layers

Warehouses are commonly organized into layers:

| Layer | Purpose | Example |
| --- | --- | --- |
| Raw/landing | Keeps data close to source for easy replay and audit | raw.reservation_cdc |
| Curated | Standardizes types, names, keys, and deduplicates | curated.reservations |
| Mart | Optimized for business questions/dashboards | mart.monthly_revenue |

Do not turn raw tables directly into dashboard tables if data still needs deduplication, currency normalization, or business rules applied.

### 7.4. How Does ELT Differ from ETL?

- **ETL:** extract, transform, then load; transforms happen before writing to the warehouse.
- **ELT:** extract and load raw data first, then transform using SQL/compute inside the warehouse.

BigQuery typically pairs well with ELT: load raw data and run SQL to build curated/mart tables. However, if data needs PII scrubbing or validation before storage, upstream pipeline transformations may be necessary.

## 8. Designing Data Models for BigQuery

### 8.1. Normalized OLTP, Analytical OLAP Models

Operational databases are usually normalized to avoid update anomalies and maintain consistency. Warehouses often use dimensional modeling to simplify reporting queries.

OLTP example:
- customers
- reservations
- reservation_items
- payments
- assets

Analytical model example:
- fact_reservations
- fact_payments
- dim_customer
- dim_asset
- dim_date
- dim_channel

Fact tables contain events or measurements; dimension tables provide context for filtering and grouping. Define the grain of each fact table—for instance, one row per reservation, per payment attempt, or per reservation status event.

### 8.2. Star Schema

~~~mermaid
flowchart TD
    FACT["fact_reservations<br/>date_key, customer_key, asset_key<br/>reservation_count, amount, duration"]
    DATE["dim_date<br/>date_key, day, month, quarter, year"]
    CUSTOMER["dim_customer<br/>customer_key, segment, region"]
    ASSET["dim_asset<br/>asset_key, category, city"]
    CHANNEL["dim_channel<br/>channel_key, source, campaign"]
    DATE --> FACT
    CUSTOMER --> FACT
    ASSET --> FACT
    CHANNEL --> FACT
~~~

Star schemas help analysts write clear queries and reduce repeated join logic. BigQuery also supports nested/repeated fields and denormalized models; choose schemas based on query patterns, data governance, and maintainability.

### 8.3. Fact Tables Must Have an Explicit Grain

Suppose fact_reservations has a grain of one row per reservation. Then:
- reservation_count can be 1.
- gross_amount is the reservation's total amount.
- duration_days is the rental duration.
- created_date_key is the creation date.
- confirmed_date_key can be nullable if unconfirmed.

Do not mix one-row-per-reservation with one-row-per-payment-attempt inside the same fact table without an explicit grain. If one reservation has multiple payments, use a separate fact table or define a different grain.

### 8.4. Slowly Changing Dimensions (SCD)

Dimension attributes can change over time—for example, a customer changes region or an asset changes category.

- **SCD Type 1:** overwrites the old value; fits when history is unneeded.
- **SCD Type 2:** creates a new version with valid_from, valid_to, and is_current; preserves change history.
- **Snapshot:** records state at periodic points in time.

Choose based on analytical questions. If you want last month's revenue broken down by the customer's region at the time of the transaction, you need historical dimensions or snapshots; using current values can distort historical reports.

## 9. Data Freshness, Consistency, and Event Time

### 9.1. Freshness Is an SLA

BigQuery can receive data via:
- Scheduled batch load jobs.
- Storage Write API.
- Datastream CDC.
- Pub/Sub and Dataflow.
- Exports/imports from other systems.

Each path has different latency and traits. Define freshness SLAs—for instance, finance dashboards updated hourly, operational dashboards updated within minutes, or executive reports updated daily. These are architectural target examples, not default service guarantees.

### 9.2. Ingestion Time vs. Event Time

Two timestamps must be distinguished:

- event_time/occurred_at: when the event happened at the source.
- ingested_at: when the pipeline received or wrote the data into BigQuery.

An event occurring at 10:00 might reach BigQuery at 10:03 or later due to retries. If dashboards group by ingestion time, reports may place events on the wrong business date.

Store both timestamps to:
- Measure pipeline lag.
- Handle late-arriving data.
- Recompute partitions or aggregates.
- Reconcile source and warehouse data.

### 9.3. Strong Consistency at the Source Does Not Mean Instant BigQuery Replicas

Cloud SQL/Spanner/Firestore provide their own consistency guarantees for operational data. When data moves through CDC or event pipelines, BigQuery is an analytical replica with lag.

A request that just committed a reservation can read the new state from the operational database while the dashboard has not updated yet. This is normal behavior for asynchronous pipelines. Never use BigQuery to answer queries requiring immediate read-after-write consistency.

### 9.4. CDC Merge and Max Staleness

With Datastream destinations, BigQuery supports CDC merges and data staleness settings. `max_staleness` represents a trade-off between freshness and background merge processing cost. Choose it based on dashboard SLAs and measure actual lag; do not assume the smallest value is always best. [Datastream destination describes merge mode and staleness limits](https://docs.cloud.google.com/datastream/docs/configure-bigquery-destination).

### 9.5. Late Data and Corrections

Data can arrive late due to:
- Offline devices.
- Publisher retries.
- CDC backlogs.
- Slow-committing source transactions.
- Paused pipelines or backfills.

Pipelines must support updating affected partitions or aggregates. Do not assume yesterday's partition is immutable if events can arrive late. Define correction windows and reprocessing procedures.

## 10. Spring Boot: Boundary Between Transactions and Analytics

### 10.1. Operational Layer

Spring Boot uses JDBC/JPA or Spring Data appropriate for the operational database:
- Cloud SQL: JDBC driver, connection pool, and Spring Data JPA/JDBC.
- Spanner: Spring Cloud GCP Spanner integration.
- Firestore: Spring Data Cloud Firestore reactive repositories or client API.

Business transactions execute on the source database's transaction manager. Repositories participating in a transaction must share the same datasource/transaction manager for atomicity.

### 10.2. Analytics Layer

Spring Boot can use the BigQuery Java client or BigQueryTemplate to:
- Run reporting queries.
- Trigger scheduled or on-demand query jobs.
- Read pre-aggregated results.
- Ingest batches from files or streams.
- Check job status and record operational metadata.

You do not need BigQuery in every service. Separate an Analytics API or reporting worker to narrow permissions and isolate query load.

### 10.3. OLTP Transaction Service Example

~~~java
@Service
public class PaymentApplicationService {

    private final PaymentRepository payments;
    private final ReservationRepository reservations;

    public PaymentApplicationService(
            PaymentRepository payments,
            ReservationRepository reservations) {
        this.payments = payments;
        this.reservations = reservations;
    }

    @Transactional
    public Payment confirmPayment(
            UUID reservationId, String providerReference) {

        Reservation reservation = reservations.findById(reservationId)
                .orElseThrow();

        Payment payment = Payment.confirmed(
                reservationId, providerReference);

        reservation.markPaid();
        payments.save(payment);
        reservations.save(reservation);

        return payment;
    }
}
~~~

This is a business transaction on the operational database. In a system with an outbox, the service also writes an event record in the same transaction so the analytics pipeline picks up the change after commit.

### 10.4. BigQuery Query Example in an Analytics Service

This example assumes the mart schema has `reservation_date` of type DATE and `total_amount` of type NUMERIC; the DTO and accessors match that schema.

~~~java
import com.google.cloud.bigquery.BigQuery;
import com.google.cloud.bigquery.FieldValueList;
import com.google.cloud.bigquery.QueryJobConfiguration;
import com.google.cloud.bigquery.QueryParameterValue;
import com.google.cloud.bigquery.TableResult;

@Service
public class ReservationAnalyticsService {

    private final BigQuery bigQuery;

    public ReservationAnalyticsService(BigQuery bigQuery) {
        this.bigQuery = bigQuery;
    }

    public List<DailyRevenue> revenueByDay(LocalDate startDate)
            throws InterruptedException {

        String sql = """
            SELECT
              reservation_date,
              COUNT(*) AS reservation_count,
              SUM(total_amount) AS revenue
            FROM analytics.mart.fact_reservations
            WHERE reservation_date >= @startDate
            GROUP BY reservation_date
            ORDER BY reservation_date
            """;

        QueryJobConfiguration config =
                QueryJobConfiguration.newBuilder(sql)
                        .addNamedParameter(
                                "startDate",
                                QueryParameterValue.date(startDate.toString()))
                        .setUseLegacySql(false)
                        .setMaximumBytesBilled(5_000_000_000L)
                        .build();

        TableResult result = bigQuery.query(config);

        List<DailyRevenue> rows = new ArrayList<>();
        for (FieldValueList row : result.iterateAll()) {
            rows.add(new DailyRevenue(
                    LocalDate.parse(
                            row.get("reservation_date").getStringValue()),
                    row.get("reservation_count").getLongValue(),
                    row.get("revenue").getNumericValue().bigDecimalValue()));
        }

        return rows;
    }
}
~~~

This illustrates an analytics query; the DailyRevenue DTO and remaining imports are defined by the application. The API can return aggregated results for dashboards. If queries are large or long-running, submit jobs asynchronously, store job IDs, and let clients poll rather than keeping HTTP requests open.

### 10.5. Do Not Put Two Transaction Managers into One @Transactional

`@Transactional` only controls the transaction manager selected by Spring. A method touching both a JPA repository and the BigQuery client does not automatically become a distributed transaction.

Example unsafe with respect to atomicity:

~~~java
@Transactional
public void confirmAndWriteAnalytics(UUID reservationId) {
    reservationRepository.confirm(reservationId);
    bigQueryTemplate.writeJsonStream(...);
}
~~~

Cloud SQL's transaction manager cannot roll back a write already committed to BigQuery. If the BigQuery call fails, the database transaction may roll back; if BigQuery succeeds while the database rolls back, analytical data still lingers.

Use outbox/CDC or a workflow with retries and reconciliation instead of assuming cross-service atomicity.

### 10.6. Reporting APIs and Caching

If dashboards are queried frequently:
- Precompute aggregate tables or materialized views where appropriate.
- Cache results by time window and filters.
- Use query parameters.
- Bound date ranges and page sizes.
- Display when the data was last updated.

Do not run a fresh full-scan query on every user dashboard refresh when precomputed aggregates can be reused.

## 11. Optimizing BigQuery for OLAP

### 11.1. Partitioning

Partition tables by a date/timestamp column or ingestion time so queries skip irrelevant partitions.

Examples:
- fact_reservations partitioned by reservation_date.
- fact_payments partitioned by payment_date.
- event_log partitioned by ingestion date or event date depending on requirements.

Queries should filter on the partition column:

~~~sql
SELECT
    reservation_date,
    SUM(total_amount) AS revenue
FROM analytics.mart.fact_reservations
WHERE reservation_date >= DATE '2026-10-01'
  AND reservation_date < DATE '2026-11-01'
GROUP BY reservation_date;
~~~

Partition pruning reduces bytes read when filters match properly. [Querying partitioned tables documentation](https://docs.cloud.google.com/bigquery/docs/querying-partitioned-tables).

### 11.2. Clustering

Clustering sorts data by specific columns so BigQuery scans fewer blocks when queries filter on those columns. For example, cluster fact_reservations by customer_id, asset_id, or region if query patterns commonly filter by them.

Do not pick clustering solely by cardinality. Base it on query filters, data distribution, and partition sizes. [Clustered tables documentation](https://docs.cloud.google.com/bigquery/docs/clustered-tables).

### 11.3. Projection and Aggregation

Avoid SELECT * when only a few columns are needed. Because BigQuery is columnar, selected columns directly affect bytes read.

Push aggregations into SQL:
- COUNT, SUM, AVG.
- GROUP BY.
- Window functions.
- APPROX_COUNT_DISTINCT when approximate precision is acceptable.
- Pre-aggregations or materialized views for recurring dashboards.

LIMIT does not guarantee lower bytes scanned if the query still has to scan the whole table to compute results. [Best practices to reduce data processed](https://docs.cloud.google.com/bigquery/docs/best-practices-performance-compute).

### 11.4. Compute and Storage Costs

BigQuery has separate compute and storage billing models:
- On-demand: queries billed by bytes processed.
- Capacity-based: uses slots/reservations to allocate compute capacity.
- Storage: depends on data volume and storage billing model.

To control costs:
- Use dry runs and maximumBytesBilled.
- Filter partitions.
- Select only needed columns.
- Use materialized views/aggregate tables for suitable workloads.
- Set quotas or budget alerts.
- Monitor bytes processed, slot usage, and job history.

Cost must be evaluated alongside freshness and concurrency; a faster query is not necessarily cheaper if it scans excessive data. [Cost estimation and control guide](https://docs.cloud.google.com/bigquery/docs/best-practices-costs).

## 12. Security and Data Governance

### 12.1. Separating Operational Database and Warehouse Permissions

Spring Boot's runtime service account needs permissions on the source database tailored to its use case. CDC/Dataflow pipelines need permissions to read source logs, write to Pub/Sub/BigQuery, and manage checkpoints. Analysts should only have read access to needed datasets/marts.

Do not share one Owner service account across:
- Checkout API.
- CDC connector.
- Dataflow workers.
- BI dashboards.
- Migration pipelines.

Separating principals limits blast radius and simplifies auditing.

### 12.2. IAM in BigQuery

BigQuery supports access controls at project, dataset, table, row, and column levels. Examples:
- Job User to create query jobs in a project.
- Data Viewer to read datasets/tables.
- Data Editor to write data into datasets.
- Row-level access policies to restrict rows conditionally.
- Policy tags/column-level security for sensitive fields.

Grant permissions at the dataset or table level where appropriate instead of project-wide.

### 12.3. PII and Sensitive Data

Do not replicate every OLTP column into the warehouse just because you can. Before moving data to BigQuery:
- Classify PII and sensitive data.
- Exclude fields unnecessary for analytics.
- Tokenize or pseudonymize identifiers where feasible.
- Apply policy tags and row-level access.
- Define retention, deletion, and legal hold policies.
- Audit logs and event payloads for sensitive fields.

Analytical copies can outlive operational records; design deletion/anonymization policies aligned with legal and business requirements.

### 12.4. Auditing and Lineage

Track:
- Source database and source table.
- CDC stream or event topic.
- Schema version.
- Pipeline run/job ID.
- Watermark and ingestion timestamp.
- Transformation version.
- Rows read/written/rejected.
- Destination dataset/table.

Lineage traces dashboard metrics back to their source and explains numerical discrepancies.

## 13. Reconciliation and Data Quality

### 13.1. Why Is Reconciliation Necessary?

Pipelines can drop events, deliver duplicates, misconvert types, or lag behind. Reconcile OLTP with the warehouse by batch/window:

- Daily record counts.
- Total amounts by currency.
- Reservation counts by status.
- Min/max event timestamps.
- Duplicate event counts.
- Rejected event counts.
- Source and target watermarks.

Do not compare a live changing source table against a target table mid-backfill without pinning a common snapshot/window.

### 13.2. Quality Checks

Example query detecting duplicate event IDs:

~~~sql
SELECT
    event_id,
    COUNT(*) AS copies
FROM analytics.raw.reservation_events
GROUP BY event_id
HAVING COUNT(*) > 1
ORDER BY copies DESC;
~~~

Example checking reservations missing a customer key:

~~~sql
SELECT COUNT(*) AS invalid_rows
FROM analytics.curated.reservations
WHERE customer_id IS NULL;
~~~

You can automate checks using scheduled queries, Dataform assertions, pipeline validation, or dedicated jobs. When quality checks fail, do not publish new marts as if the data were valid.

### 13.3. Replay and Backfill

When a pipeline fails:
1. Identify the affected time window or event IDs.
2. Verify source log retention or outbox history still holds the data.
3. Reprocess into raw/staging.
4. Deduplicate by event ID or primary key.
5. Rebuild affected curated/mart partitions.
6. Re-reconcile counts and aggregates.
7. Document the incident and pipeline version.

Designing for replay upfront reduces the risk of painful manual recovery.

## 14. Choosing a Synchronization Strategy by Requirements

| Need | Approach | Key considerations |
| --- | --- | --- |
| Daily updated reports | Batch export/load | Simple, scheduled freshness |
| Dashboards updated within minutes | Datastream CDC or Pub/Sub/Dataflow | Monitor lag and schema evolution |
| Explicit business semantics needed | Outbox + domain events | Event contracts, duplicates, and ordering |
| Mirror close to current table state | Datastream merge mode | Requires primary keys and understanding max staleness |
| Preserve full history of all changes | Append-only CDC/event logs | Larger storage, curation/dedup required |
| Multi-year historical backfill | Batch load/Datastream backfill | Check location, schema, and quotas |
| Recurring dashboard queries | Curated/mart/materialized views | Precompute aggregates and cache |
| Checkout/availability needing read-after-write | OLTP database | Never read BigQuery as the decision source |

No single latency target fits every system. Pick pipelines based on SLAs, data volume, cost, and operational capacity.

## 15. Common Architectural Pitfalls

| Issue | Consequence | Fix |
| --- | --- | --- |
| Using BigQuery as checkout source of truth | Unsuitable latency and consistency | Write to Cloud SQL/Spanner/Firestore |
| Running large dashboard scans on OLTP | Competes with requests for CPU/I/O/connections | Offload analytics to BigQuery |
| Dual-writing database and BigQuery in one method | One side commits, the other fails | Outbox, CDC, or event pipeline |
| Missing event IDs | Difficult to deduplicate | Use a deterministic ID per event |
| Storing only ingestion timestamps | Reports misattribute dates when events arrive late | Store both event time and ingestion time |
| Unversioned schemas | Consumers break when fields change | Backward-compatible schema evolution |
| SELECT * queries without partition filters | Higher cost and latency | Projection and partition pruning |
| Continuous row-by-row DML | Too many jobs and contention | Batch DML or appropriate Storage Write API |
| Assuming BigQuery ACID means OLTP | Wrong database choice | Evaluate access patterns and transaction latency |
| No reconciliation | Missing data/duplicates go unnoticed | Reconcile counts, sums, watermarks, and quality |
| Granting Owner to every service | Elevated security risk | Least-privilege IAM per workload |
| No replay plan | Incident backfills are hard | Raw layer, checkpoints, and idempotent transforms |

## 16. Practical Exercises

### Exercise A — Classify Workloads

List 10 operations in a booking application. Classify each as OLTP or OLAP. Explain why creating a reservation and computing monthly revenue require two different access patterns.

### Exercise B — Choose Operational Databases

Compare Cloud SQL, Spanner, and Firestore for:
- Reservations and payments.
- Customer profiles.
- Mobile application state.
- Workloads needing global transactions.

State schema, consistency, latency, queries, and rationale for each choice.

### Exercise C — Design an Outbox

Create an `outbox_event` table in Cloud SQL. Write a `@Transactional` service that updates a reservation and inserts an event. Build a publisher sending events to Pub/Sub. Simulate a crash after publish but before marking processed; prove the consumer handles duplicates safely.

### Exercise D — CDC with Datastream

Create a Cloud SQL sandbox and configure Datastream to BigQuery. Compare merge mode with append-only mode. Determine how backfills work and how to monitor data staleness.

### Exercise E — Dataflow Streaming

Stream JSON events from Pub/Sub into Dataflow and write to BigQuery. Verify schema validation, dead-letter handling, event IDs, event time, and pipeline lag.

### Exercise F — Batch Ingestion

Export source data by watermark to Cloud Storage. Create a staging table, load the batch, and merge into a curated table. Re-run the same batch and verify no duplicates are created.

### Exercise G — Star Schema

Design fact_reservations, fact_payments, dim_customer, dim_asset, and dim_date. Define the grain of each fact and how to handle customer region changes using SCD Type 2.

### Exercise H — Data Freshness and Reconciliation

Define a freshness SLA for a dashboard. Write queries comparing daily counts and sums between a source snapshot and BigQuery. Set alerts when lag or discrepancies exceed thresholds.

### Exercise I — Query Costs

Create a table partitioned by date and clustered by customer ID. Compare bytes processed between a query with a partition filter and one without. Test maximumBytesBilled and dry runs.

### Exercise J — Security and Lineage

Separate service accounts for the API, Datastream/Dataflow, and analysts. Apply dataset/table permissions, policy tags for PII, and record source, pipeline run ID, and schema version.

### Self-Check Questions

1. In which primary access patterns do OLTP and OLAP differ?
2. Why do OLTP databases typically normalize schemas?
3. Why does BigQuery use columnar storage for analytics?
4. Does BigQuery support ACID transactions?
5. Why does ACID support not make BigQuery the default choice for checkout?
6. Which kinds of applications fit Cloud SQL?
7. When should you consider Spanner instead of Cloud SQL?
8. In what data model ways does Firestore differ from a relational database?
9. What does "source of truth" mean in a hybrid architecture?
10. Why shouldn't you dual-write directly to Cloud SQL and BigQuery?
11. What problem does a transactional outbox solve?
12. Why can an outbox publisher still send duplicate messages?
13. How does CDC differ from domain events?
14. How does Datastream merge mode differ from append-only mode?
15. How do batch loads differ from streaming ingestion in freshness and operations?
16. How does event time differ from ingestion time?
17. Why can a BigQuery replica be stale relative to the OLTP source?
18. What purposes do raw, curated, and mart layers serve?
19. What is the grain of a fact table?
20. How does SCD Type 2 support historical analysis?
21. Why is row-by-row BigQuery DML unsuitable for high-frequency transactional workloads?
22. Which notable concurrency limit applies to BigQuery multi-statement transactions?
23. How does partition pruning reduce costs?
24. Why does LIMIT not always reduce bytes scanned?
25. Which metrics should be reconciled to detect missing or duplicate data?

**Expected outcome:** learners can choose appropriate operational databases for OLTP workloads, use BigQuery for OLAP analytics, explain BigQuery's ACID transactions and their limitations, design outbox/CDC/batch pipelines, define sources of truth and freshness SLAs, build analytical data models, control IAM/costs, and reconcile data quality in Spring Boot architectures on Google Cloud.

## References

- [BigQuery overview and architecture](https://docs.cloud.google.com/bigquery/docs/introduction)
- [BigQuery storage optimization and columnar storage](https://docs.cloud.google.com/bigquery/docs/best-practices-storage)
- [BigQuery multi-statement transactions](https://docs.cloud.google.com/bigquery/docs/transactions)
- [BigQuery DML best practices and concurrency](https://docs.cloud.google.com/bigquery/docs/data-manipulation-language)
- [Avoid point-specific DML and optimize query computation](https://docs.cloud.google.com/bigquery/docs/best-practices-performance-compute)
- [Cloud SQL overview](https://docs.cloud.google.com/sql/docs/introduction)
- [Spanner transactions](https://docs.cloud.google.com/spanner/docs/transactions)
- [Firestore overview](https://docs.cloud.google.com/firestore/native/docs/overview)
- [Datastream BigQuery destination](https://docs.cloud.google.com/datastream/docs/destination-bigquery)
- [Datastream BigQuery merge and append-only modes](https://docs.cloud.google.com/datastream/docs/configure-bigquery-destination)
- [Dataflow Pub/Sub to BigQuery template](https://docs.cloud.google.com/dataflow/docs/guides/templates/provided/pubsub-to-bigquery)
- [BigQuery partitioned tables](https://docs.cloud.google.com/bigquery/docs/querying-partitioned-tables)
- [BigQuery clustered tables](https://docs.cloud.google.com/bigquery/docs/clustered-tables)
- [BigQuery cost control](https://docs.cloud.google.com/bigquery/docs/best-practices-costs)
