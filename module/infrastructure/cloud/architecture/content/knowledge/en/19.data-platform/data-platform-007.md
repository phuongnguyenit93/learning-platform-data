# Serving Analytics, Reporting, and Cross-Domain Queries

An application typically comprises multiple business services, each owning its own data and optimizing its database for transactional operations. The Booking Service needs fast, consistent scheduling; the Payment Service records payment state; the Customer Service manages profiles; the Inventory Service tracks quantities. When leadership needs revenue reports broken down by region, product, customer, and time, querying each operational database directly to stitch data together creates unpredictable load, leaks internal schemas, and yields inconsistent numbers.

An **analytical data platform** provides a dedicated path to collect, standardize, join, and serve multi-domain data for reporting, dashboards, trend analysis, and cross-domain queries. It typically combines batch ingestion, change data capture (CDC), streaming/events, a data lake or warehouse, analytical data models, a catalog, a semantic layer, and BI/query APIs.

The goal is delivering reliable analytics without turning transactional databases into shared reporting stores. However, replicating data into an analytical platform introduces latency, cost, sensitive data copies, and governance obligations. The architecture must define which data is ingested, who owns metric definitions, target freshness, how invalid data is handled, and who is permitted to query.

This lesson belongs to the **Data Platform** section of the cloud architecture track. It focuses on serving analytics, reporting, and cross-domain queries by balancing reliability, security, scalability, cost, and operability in line with Well-Architected principles.

After this lesson, you will be able to:

- Distinguish OLTP and OLAP workloads and explain why cross-domain reporting needs a data platform.
- Choose a data warehouse, data lake, or lakehouse based on requirements.
- Design ingestion via batch, CDC, and streaming with checkpoints, schemas, and replay.
- Organize data by domain, analytical data models, and a semantic layer.
- Manage freshness, quality, lineage, catalogs, and ownership.
- Protect cross-domain data with classification, least privilege, masking, and auditing.
- Optimize queries, concurrency, partitioning, storage tiers, and costs.
- Propose an architecture and validation plan for a production analytical platform.

## 1. Why Do We Need an Analytical Data Platform?

Transactional databases are built to power live business operations. Actions like creating a booking, updating payment status, or checking inventory typically read/write a small set of well-structured records with low latency. Analytical reporting exhibits a very different access pattern: scanning massive record sets, joining many tables, aggregating over time, grouping by dimensions, and computing across large volumes.

When BI tools run heavy queries directly against production databases:

- Reporting queries contend with live transactions for CPU, memory, I/O, and connections.
- Cross-domain joins couple reports tightly to internal service schemas.
- Reports can blend data from mismatched timestamps without clear consistency guarantees.
- Services must grant broad read permissions to BI tools, expanding the security blast radius.
- A schema change in one service breaks dashboards and reports across multiple teams.
- Different teams define revenue, active customers, or completed orders inconsistently.

A data platform establishes a governed analytical serving path, isolating heavy read workloads from OLTP and delivering purpose-built standardized datasets.

### How OLTP and OLAP Differ

| Characteristic | OLTP (Transactional) | OLAP (Analytical) |
| --- | --- | --- |
| Goal | Execute current business operations | Understand trends and aggregate data |
| Access pattern | Many small key-based reads/writes | Large scans, aggregations, joins, and groupings |
| Latency | Typically low and predictable | Seconds/minutes acceptable depending on use case |
| Data | Current state, granular transactions | History, snapshots, aggregates, cross-domain datasets |
| Modeling | Normalized for transactions and ownership | Dimensions/facts, wide tables, or query-tuned models |
| Concurrency | High volume of concurrent business requests | Fewer queries, each potentially resource-intensive |
| Consistency | Usually requires strong transactional consistency | Eventual/freshness-bound per SLA |

These workload differences guide system selection and guardrails. OLTP can still serve tiny operational lookups; OLAP can also ingest near-real-time data when supported by the platform.

## 2. Data Boundaries Across Domains

In domain-oriented or microservices architectures, each service owns its data and business rules. The data platform must read from multiple domains without becoming a central shared database that every service writes into directly.

~~~mermaid
flowchart LR
    subgraph DOMAINS["Business sources / OLTP"]
        B["Booking Service<br/>Booking DB"]
        P["Payment Service<br/>Payment DB"]
        C["Customer Service<br/>Customer DB"]
        I["Inventory Service<br/>Inventory DB"]
    end
    B --> ING["Ingestion<br/>Batch / CDC / Events"]
    P --> ING
    C --> ING
    I --> ING
    ING --> LAKE[("Landing / Raw zone")]
    LAKE --> TRANSFORM["Validate, standardize,<br/>join and transform"]
    TRANSFORM --> CURATED[("Curated / Warehouse / Lakehouse")]
    CURATED --> SEM["Semantic models / Metrics"]
    SEM --> BI["BI / Dashboard / Analytics API"]
    SEM --> DS["Data science / ML"]
~~~

Source services remain the authoritative owners of operational data. The data platform receives copies or events for analytics and must track sources, timestamps, schema versions, and lineage.

### Ownership Rules

- Domain owners are responsible for the meaning and quality of emitted data.
- Data engineering owns ingestion, technical standardization, and pipelines.
- Data product owners own datasets serving specific user groups.
- BI/analytics owners own metrics, semantic definitions, and report documentation.
- Security/data governance defines classification, retention, access controls, and auditing.

Never leave the BI team guessing what `status`, `amount`, or `created_at` mean by inspecting application schemas. Require explicit contracts with clear definitions.

## 3. Choosing a Data Warehouse, Data Lake, or Lakehouse

No single storage architecture fits every need. Your choice depends on structured vs. semi-structured data, query patterns, concurrency, retention, governance, and sharing needs.

| Architecture | Characteristics | Best Suited For | Trade-offs |
| --- | --- | --- | --- |
| **Data warehouse** | Structured analytical store tuned for SQL queries, schemas, and BI performance | Executive reporting, KPIs, dashboards, structured ad-hoc SQL | Compute/concurrency costs; ingestion and modeling design effort |
| **Data lake** | Stores diverse data on object storage, often preserving raw and multi-format files | Diverse datasets, data science, history, batch/stream processing | Risks becoming a data swamp without catalog/schema/governance |
| **Lakehouse** | Combines object storage with metadata/table formats and table/transaction management | Lake flexibility paired with table/SQL/BI ergonomics | Extra management of formats, catalogs, engine compatibility, and compaction |
| **Operational data store (ODS)** | Integrates near-current operational data for bounded cross-domain lookups | Operational lookups or status views with tight freshness SLAs | Introduces another critical operational store requiring HA and consistency |

### Data Warehouse

Warehouses serve BI via SQL, dimensional/fact models, materialized views, or aggregate tables. Compute often decouples from storage, scaling with queries and workloads. Manage concurrency, workload queues, partitioning/clustering, and cost per query.

### Data Lake

Lakes store raw and processed data on object storage—spanning CSV, JSON, Parquet, logs, images, or streaming files. Catalogs, schemas, partitioning, and access policies determine discoverability and governance.

### Lakehouse

Lakehouses add a metadata/table layer onto data lakes to enable schema evolution, snapshots/versioning, transaction semantics, and multi-engine querying depending on table format capabilities. Not every lakehouse delivers identical ACID guarantees, concurrency, or interoperability; verify exact engine and format support.

### How to Choose

- Executive dashboards with well-defined KPIs and heavy SQL usage: a warehouse is often the natural fit.
- Storing logs, files, raw events, and diverse datasets: a data lake fits well.
- Sharing large-scale datasets across BI, batch, and ML: evaluate a lakehouse.
- Near-real-time cross-domain operational lookups: consider an ODS or dedicated read model, defining clear SLAs and never confusing it with the source of truth.

## 4. Ingestion: Bringing Domain Data into the Platform

Ingestion moves data from sources into the data platform. Three common patterns—batch, CDC, and streaming—can be combined to satisfy varying requirements.

### 4.1. Batch Ingestion

Batch pulls data on a schedule or interval, such as every 15 minutes or nightly. Sources may provide file exports, table snapshots, or paginated APIs.

**Advantages:** straightforward to operate, easy to verify record counts, well suited for reports without instant freshness needs.

**Trade-offs:** data is always stale relative to schedule intervals; incremental extraction requires checkpoints to avoid gaps or duplicates; full reloads can be heavy.

Design principles:

- Prefer incremental loads via watermarks/versions when supported by sources.
- Do not rely solely on `updated_at` if timestamps are unreliable or updates arrive late; consider overlap windows and reconciliation.
- Advance checkpoints only after the batch commits successfully to the target.
- Use idempotent merges/upserts so retries never create duplicates.
- Define explicit late-arriving data and backfill policies.

### 4.2. Change Data Capture (CDC)

CDC captures mutations from source databases, typically via transaction logs or native engine hooks. It propagates inserts, updates, and deletes downstream without repeatedly scanning entire tables.

~~~mermaid
flowchart LR
    DB[("Source database")] --> LOG["Transaction log / CDC connector"]
    LOG --> BROKER[("Change stream / broker")]
    BROKER --> SINK["CDC consumer"]
    SINK --> RAW[("Raw change records")]
    RAW --> MERGE["Apply changes / build current state"]
    MERGE --> CURATED[("Analytics tables")]
~~~

Key CDC considerations:

- Initial snapshot and starting log position.
- Checkpoints/offsets and recovery after consumer restarts.
- Ordering of mutations per key/partition.
- Deletes/tombstones and rapid successive updates.
- Schema evolution and DDL compatibility.
- Database log retention; prolonged connector outages can lose required logs.
- Replication slots/binlog retention inflating storage or pressuring the database if consumers lag.

CDC reflects physical database mutations, not automatic business semantics. A row update may represent an intermediate state, a data fix, or a technical migration; transform it according to domain contracts.

### 4.3. Streaming and Domain Events

Streaming consumes events emitted by domain services when business events occur, such as `BookingConfirmed` or `PaymentCaptured`. This communicates domain semantics more clearly than CDC when producers design strong event contracts.

Streaming fits near-real-time dashboards, alerting, and event-driven reactions. However, producers and consumers must manage schemas, ordering, duplicates, retries, partition keys, offsets, retention, and DLQs.

### Comparing Batch, CDC, and Streaming

| Criterion | Batch | CDC | Domain Event Streaming |
| --- | --- | --- | --- |
| Freshness | Schedule-driven | Near real-time depending on logs/connectors | Near real-time depending on publish/consume |
| Semantics | Snapshots or record sets | Physical/row-level mutations | Business events |
| Source impact | Can trigger scan queries | Reads transaction logs with some overhead/retention impact | Producer emits events; requires outbox/broker |
| Deletes/updates | Needs watermark/upsert logic | Typically emits change/delete records | Producer defines event contracts |
| Replay/backfill | Rerun batch or snapshot | Limited by log retention and offsets | Limited by broker retention/archives |
| Complexity | Generally lower | Connectors, offsets, schema evolution | Event design, delivery guarantees, ordering, ownership |

Choose based on required freshness. Never force streaming onto every dataset just for "real-time"; when batch meets requirements, it is simpler and cheaper.

## 5. Data Contracts and Schema Evolution

Cross-domain pipelines break easily when producers change schemas without informing consumers. A data contract specifies:

- Field names and meanings.
- Data types, units, timezones, and nullability.
- Primary/business keys and event semantics.
- Versioning, compatibility rules, and deprecation timelines.
- Privacy classifications and usage permissions.
- Freshness expectations, owners, and change notification channels.

For example, an `amount` field must specify minor units vs. decimals, currency, gross vs. net, and FX conversion timing if applicable. A `status` field must define its enum values and transition meanings.

### Schema Evolution

Common changes:

- Adding optional fields with explicit defaults or clear null semantics.
- Renaming fields, usually requiring dual-read/dual-write phases or mapping layers.
- Changing types or semantics, requiring new versions and migrations.
- Dropping fields only after all legacy consumers have migrated.
- Changing event meanings should not be disguised with superficial version bumps alone.

With Avro, Protobuf, JSON Schema, or table schemas, configure appropriate compatibility modes and validate contracts in CI. Structural backward compatibility does not guarantee business semantic compatibility.

### Source Schemas Are Not Analytical Models

Do not blindly mirror every OLTP table and call it a warehouse model. Source schemas optimize transactional writes; analytical models must answer business questions with history, dimensions, facts, metric definitions, and late-data handling.

## 6. Structuring Cross-Domain Data Models

After ingestion, data typically flows through structured layers. A common layout:

~~~mermaid
flowchart TD
    SRC["Domain sources"] --> RAW["Raw / Bronze<br/>Retain source records and metadata"]
    RAW --> CLEAN["Validated / Silver<br/>Standardize, dedup, quality checks"]
    CLEAN --> MART["Curated / Gold<br/>Business models, facts, dimensions"]
    MART --> SEM["Semantic layer / certified metrics"]
    SEM --> CONSUME["Dashboards, reports, APIs, ML"]
~~~

Bronze/Silver/Gold is a popular naming convention, not a mandate. You can use raw/clean/curated or landing/conformed/mart as long as boundaries and promotion criteria are explicit.

### Raw Layer

Raw preserves data close to source formats along with metadata: source, ingestion timestamp, event ID, schema version, and partition. It supports auditing, replay, and rebuilding downstream layers. Enforce tight retention, encryption, and access controls since Raw often holds sensitive data.

### Clean/Conformed Layer

This layer standardizes timestamps/timezones, currencies/units, and reference codes, deduplicates records, handles nulls, validates schemas, and enforces quality rules. Cross-domain datasets require ID mappings and governed master/reference data.

### Curated/Mart Layer

Organized around analytical questions: revenue by date/region, cancellation rates, booking completion times, payment provider performance. Build facts/dimensions, aggregates, or materialized views to serve queries efficiently.

### Facts and Dimensions

In dimensional modeling:

- **Facts** store measurable events at an explicit grain, such as one booking, one payment attempt, or one revenue line.
- **Dimensions** provide descriptive context such as customer, service, provider, region, or date.

Defining grain is critical. If a booking fact has one row per booking and you join it directly to payment attempts (multiple rows per booking), revenue totals multiply artificially. Pre-aggregate payments to the matching grain or keep a separate fact table for payment events.

### Slowly Changing Dimensions

If a region name or customer segment changes over time, historical reports may need:

- Current values applied across all history (Type 1).
- Versioned records with effective timestamps (Type 2).
- Limited prior-value attributes per specific rules.

Choose based on the business question. Revenue attributed to the region at transaction time requires historical dimension versions; reporting under today's organizational structure uses the latest mapping.

## 7. Cross-Domain Queries and the Semantic Layer

Cross-domain reports frequently combine Booking, Payment, Customer, Inventory, or Support. The challenge is not only joining tables, but **shared business definitions**:

- When is a booking considered completed?
- Is revenue recognized at authorization, capture, or settlement?
- Is an active customer defined by login, booking, or payment?
- Do cancelled bookings count toward total new bookings?
- Are refunds attributed to the refund date or the original transaction date?

If every dashboard writes its own SQL, the same metric produces conflicting numbers.

### Semantic Layer

A semantic layer defines shared entities, relationships, measures, dimensions, and business metrics. BI tools, APIs, and analysts consume a single definition instead of reimplementing business logic.

Example:

~~~text
Metric: Net Revenue
Grain: currency + business_date + market
Definition:
  captured_amount
  - refunded_amount
Filters:
  exclude test transactions
Currency:
  report in transaction currency or converted currency
Owner:
  Finance data product
Freshness:
  updated hourly
~~~

This definition is illustrative. The organization must standardize handling of partial refunds, chargebacks, taxes, fees, FX rates, and timezones.

### Cross-Domain Joins

Joining across domains requires explicit key mappings and cardinality rules. Never assume two services share the same customer ID or that IDs are immutable. Use conformed dimensions, an identity mapping service, or governed crosswalk tables.

### Direct Federated Queries vs. Data Products

Federated queries query multiple live sources on demand without prior ingestion. They are convenient for exploratory analysis or rarely accessed sources, but depend on source availability, network latency, and source performance—risking extra load on transactional systems.

Data products and curated datasets suit recurring reports, certified KPIs, and workloads needing predictable performance. Federated querying and materialization can coexist based on data class and freshness requirements.

## 8. Freshness, Consistency, and Late-Arriving Data

Data platforms rarely update instantaneously. Elapsed time from source commit through ingestion, transformation, and semantic modeling defines data latency/freshness.

### Defining Freshness SLAs

| Dataset | Assumed Target Freshness | Rationale |
| --- | --- | --- |
| Booking operations dashboard | Under 2 minutes | Near-current backlog and error monitoring |
| Revenue report | Hourly | Intraday business management |
| End-of-day financial close | Ready before 08:00 next business day | Requires full reconciliation and verification |
| Trend analytics dataset | Daily | Real-time unnecessary |

These targets are illustrative examples, not universal SLAs. Measure freshness using source commit time, ingestion time, and publish time—never job schedule times alone.

### Eventual Consistency and Dashboards

When Payment Service commits a capture before the analytics pipeline consumes the event, revenue dashboards temporarily lag behind reality. UIs should display a "data updated as of..." timestamp or freshness indicator whenever users might mistake delayed figures for live state.

Never query the analytics warehouse for instant transactional decisions, such as checking whether a booking slot is free or an account balance is sufficient. Those decisions belong strictly to transactional services and sources of truth.

### Late-Arriving Data and Event Corrections

Events can arrive late, out of order, or be corrected retroactively. Pipelines should:

- Store event/record time and ingestion time separately.
- Support updating closed partitions/windows when required by business rules.
- Apply appropriate watermarks and late-arrival windows.
- Support backfills/reprocessing by date range or event ID.
- Use upserts/merges and business keys to prevent duplicates.
- Maintain audit trails whenever historical metrics are restated.

### Reconciliation

Compare counts, sums, and statuses between sources and curated datasets across matching time windows/partitions. Categorize discrepancies into expected lag, late events, filtering rules, deletes, duplicates, transformation bugs, or upstream corrections.

## 9. Data Quality and Pipeline Controls

Validate data quality continuously rather than only at project launch.

| Category | Example |
| --- | --- |
| Schema | Fields, types, and versions match contract |
| Completeness | No missing required customer IDs or booking dates |
| Uniqueness | Event IDs or business keys do not duplicate outside policy |
| Validity | Amounts non-negative unless allowed; statuses within enums |
| Referential integrity | Payments reference valid bookings |
| Consistency | Currencies, timezones, and units standardized |
| Freshness | Partitions/datasets updated within SLA |
| Reconciliation | Source counts/sums match reconciliation rules |

### Data Quality Gates

Mark a dataset certified/published only after mandatory checks pass. On failure:

- Halt promotion of bad data into the curated layer.
- Route invalid records to quarantine.
- Log error counts, source, schema version, and reason codes.
- Alert owners and consumers.
- Enable fixing data or code followed by controlled replay.

Never silently drop bad records without metrics and audit trails, or reports will undercount silently.

## 10. Metadata, Catalog, Lineage, and Ownership

As datasets proliferate, users need to know what exists, who owns it, when it updated, how metrics are calculated, whether it contains sensitive data, which sources and transforms created it, and who has access.

### Data Catalog

The catalog stores technical and business metadata: dataset names, descriptions, schemas, owners, tags, classifications, freshness, quality status, access policies, and sample queries.

### Lineage

Lineage traces paths from source fields/tables/events through pipelines and transformations to curated datasets, metrics, and dashboards. When a source schema changes or numbers look wrong, lineage quickly pinpoints impacted consumers.

### Data Products

A data product should specify:

- Accountable owner.
- Versioned contracts/schemas.
- Intended purpose and target consumer groups.
- Quality/freshness SLOs.
- Access and retention policies.
- Documentation, lineage, and support channels.
- Deprecation workflows and change notifications.

Not every intermediate staging table needs full product governance. Publish formal data products for datasets with explicit consumers and contracts.

## 11. Security and Governance for Cross-Domain Data

Because a data platform centralizes copies from many domains, a single permission mistake can expose far more data than any individual source service.

### Classification and Least Privilege

Classify data at minimum as public, internal, confidential, and restricted per organizational policy. PII, financial data, health data, and sensitive identifiers require strict protection and purpose limitation.

Access policies should evaluate:

- User/service identity and functional groups.
- Dataset, table, column, and row scopes.
- Tenant, region, and approved purpose.
- Production vs. non-production environments.
- Export, download, sharing, and copy permissions.
- Access expiration and revocation workflows.

### Masking and Pseudonymization

Not every analyst needs emails, phone numbers, or real names. Tokenize, hash cleanly, mask, or strip identifying columns in curated datasets. Hashing does not automatically anonymize data if re-identification or lookup joins remain possible.

### Row-Level and Column-Level Security

When users may view only a single region or tenant, enforce row/column policies directly in the query engine or semantic layer—and verify export paths too. Never rely solely on dashboard-level UI filters.

### Encryption and Secrets

- Encrypt at rest and in transit.
- Manage keys, rotation, decrypt permissions, and key backups.
- Store ingestion connector secrets in a secrets manager.
- Never write sensitive payloads into unprotected logs or dead-letter stores.
- Audit queries, exports, and access policy modifications.

### Data Lifecycle and Deletion

Deleting a record at the source may require propagating deletions to raw, curated, materialized views, search indexes, exports, backups, and downstream consumers. Define deletion propagation, legal holds, retention, and completion proof. Never assume deleting an OLTP row automatically removes downstream analytical copies.

## 12. Query Performance and Scalability

Warehouses and lakehouses handle huge volumes, yet queries turn slow and expensive if data and workloads are poorly organized.

### Partitioning

Partitioning by date, region, or appropriate filter keys lets engines skip irrelevant data. Overly small partitions bloat files and metadata; overly large partitions cause broad scans. Choose keys matching real query predicates.

### Columnar Formats

Columnar formats like Parquet suit analytical queries because engines read only needed columns and leverage compression/encoding. Excessive small files add overhead; run compaction and tune target file sizes per engine.

### Clustering/Sorting

Clustering or sorting on frequently filtered/joined keys reduces bytes scanned. Effectiveness depends on engine behavior and data distribution; benchmark with real queries.

### Materialized Views and Aggregates

Repeated dashboard queries benefit from pre-aggregations or materialized views. Define refresh cadences, dependencies, freshness expectations, and storage costs. Preserve exact grain in aggregates to avoid double-counting.

### Workload Management

Segment workloads:

- Interactive dashboards/BI needing consistent low latency.
- Ad-hoc analyst queries that can consume heavy resources and need quotas.
- Scheduled batch transformations.
- ML/feature extraction with distinct access patterns.

Use resource groups, queues, concurrency caps, query timeouts, and workload isolation when supported. Prevent one runaway ad-hoc query from starving production dashboards.

### Caching and Result Reuse

Caching query results or semantic metrics lowers compute cost, but requires freshness invalidation and permission checks. Never share cache keys across tenants or roles when row/column entitlements differ.

## 13. Reliability, Backup, and Recovery for Data Platforms

Pipelines can fail across schedulers, connectors, brokers, object storage, catalogs, compute engines, or semantic models. Make every layer recoverable:

- Durable checkpoints and offsets.
- Bounded retries with backoff.
- Dead-letter/quarantine stores for invalid records.
- Idempotent loads/merges and event deduplication.
- Immutable/archived raw data to enable backfills when transforms have bugs.
- Versioned code, schemas, and data models.
- Backups for catalogs, metadata, configs, and critical state.
- Restore tests covering warehouses/lakehouses and access controls.
- Throttled reprocessing to avoid spiking load on sources.

### Replay and Backfill

Replays can create duplicates if pipelines are not idempotent. Before rerunning:

1. Identify source partitions, time ranges, or event IDs.
2. Lock in the transformation logic and version to apply.
3. Use staging tables or separate target versions for major changes.
4. Deduplicate using event IDs or business keys.
5. Validate row counts, sums, and quality gates.
6. Promote outputs and log audit records.

### Disaster Recovery

Data platforms need DR across raw data, curated data, catalogs, encryption keys, pipeline code, and orchestration state. Backing up object files while forgetting the catalog or KMS keys leaves data unusable. Set RPO/RTO per data product based on the business impact of reporting outages.

## 14. Cross-Domain Governance and Change Management

When multiple domains emit data, changes must roll out without breaking downstream consumers unexpectedly.

### Schema Registry and Contract Checks

Producers publishing new schemas must run compatibility checks. Consumers can register contract tests. Breaking changes require new versions, dual publishing/reading during transition periods, and explicit deprecation windows.

### Data Owners and Stewardship

Every certified metric needs a business owner accountable for its definition. Data stewards manage glossaries, mappings, and quality rules. Data engineering should not unilaterally decide the business meaning of financial metrics.

### Certified Datasets and Self-Service

Empower analysts to explore data self-service via catalogs, sandboxes, and query quotas. Official reporting, however, should rely on certified datasets/metrics with owners, tests, and versions. Enforce retention and cleanup on sandboxes.

### Data Access Requests

Access workflows should capture purpose, scope, expiration, owner approval, and access audit logs. Never grant permanent broad access merely because a user requested one dashboard.

## 15. Choosing Batch, Near-Real-Time, or Federated Queries

| Approach | When Suitable | Risks / Costs |
| --- | --- | --- |
| Batch warehouse | Periodic reports, KPIs, historical analysis | Freshness tied to schedule, batch windows |
| CDC/streaming lakehouse | Near-real-time monitoring, multi-consumer data products | Connectors/brokers, offsets, schemas, ordering, operational load |
| Operational data store / read model | Operational cross-domain lookups | Operating another read store and managing consistency |
| Federated queries | Exploration, infrequently queried or unmaterialized sources | Source availability/network dependence, direct source load, variable latency |
| Hybrid | Combining curated datasets with controlled live lookups | Must define freshness expectations and authoritative sources clearly |

### Decision Questions

1. How fresh do users actually need the data?
2. Are queries repetitive enough to optimize via models or aggregates?
3. Can sources handle direct query load, or must workloads be isolated?
4. Does the use case require historical snapshots or audit trails?
5. Do consumers need ad-hoc SQL or task-specific APIs?
6. Can the team operate CDC/streaming and schema evolution reliably?
7. Do compute, storage, networking, and freshness costs align with value?

## 16. Architecture Example: Booking Platform Performance Reporting

**Assumed context:** A booking platform runs Booking, Payment, Customer, and Provider Services. Leadership wants dashboards showing daily/regional revenue, cancellation rates, payment success rates, and provider performance. Dashboards must refresh within 15 minutes; financial reports reconcile at end of day. Production databases must not handle heavy BI queries.

~~~mermaid
flowchart TD
    subgraph SOURCE["Operational domains"]
        B[("Booking DB")]
        P[("Payment DB")]
        C[("Customer DB")]
        V[("Provider DB")]
    end
    B --> ING["CDC + Domain events"]
    P --> ING
    C --> ING
    V --> ING
    ING --> RAW[("Raw data lake<br/>append-only with source metadata")]
    RAW --> CLEAN["Schema validation<br/>dedup + standardize"]
    CLEAN --> MODEL["Curated warehouse model<br/>FactBooking / FactPayment<br/>Customer / Provider / Date dimensions"]
    MODEL --> METRIC["Semantic layer<br/>Revenue, cancellation rate,<br/>payment success"]
    METRIC --> DASH["Executive dashboards"]
    MODEL --> FIN["Daily finance reconciliation"]
    ING --> MON["Pipeline monitoring / DLQ"]
~~~

### Data Decisions

- Booking Service emits booking created/confirmed/cancelled events or suitable CDC.
- Payment Service provides authorization/capture/refund events with operation references, currencies, and timestamps.
- Customer/Provider dimensions use snapshots or CDC with effective timestamps when historical reporting requires point-in-time accuracy.
- The Raw layer retains events/change records with source, event ID, schema version, and ingestion time.
- The Curated layer separates `FactBooking` and `FactPayment` to prevent double-counting across one-to-many joins.
- The Semantic layer defines revenue as captures minus refunds, alongside cancellation rates and payment success rates.
- Dashboards display freshness timestamps; financial reporting reconciles against authoritative payment sources.

### Freshness and Consistency

Operational dashboards target 15-minute freshness, whereas daily financial closing reports are finalized only after reconciliation. When a late payment or provider correction arrives, reporting records an audited adjustment rather than silently altering published figures.

### Security

Analysts reviewing regional revenue do not need customer phone numbers or emails. Curated marts strip or mask PII; row-level policies scope visibility by market; queries and exports are audited.

### Verification Criteria

- Daily booking counts match business rules and source records.
- Total captured/refunded amounts reconcile by currency.
- Duplicate events never double-count revenue.
- Late events and corrections appear with full audit trails.
- Pipelines achieve 15-minute freshness under normal load and alert on SLA breaches.
- Dashboard queries impose negligible impact on OLTP databases.

## 17. Practice Exercise: Building a Cross-Domain Reporting Platform

**Scenario:** An enterprise operates Order Service, Payment Service, Customer Service, and Fulfillment Service, each with its own database. Management needs daily/regional revenue reports, completed order counts, refund rates, and payment-to-delivery lead times. Dashboards require under 10-minute freshness; financial reports close daily. Customer data includes emails and phone numbers, and only Customer Support may see raw PII. These facts are simulated for the exercise.

### Tasks

1. **Choose the platform:** compare warehouse, lake, and lakehouse by query patterns, data types, storage, concurrency, governance, and cost; decide whether an ODS or federated queries are warranted.
2. **Design ingestion:** choose batch, CDC, or domain events per source; define initial snapshots, offsets/checkpoints, schema evolution, delete handling, replay, and backfills.
3. **Design the data model:** define grain for `FactOrder`, `FactPayment`, and `FactFulfillment`; design `Customer`, `Product`, `Region`, and `Date` dimensions; handle one-to-many joins, refunds, late events, and SCDs.
4. **Define semantic metrics:** specify definitions for revenue, refund rate, completed orders, and fulfillment time—including units, currencies, timezones, filters, owners, and freshness.
5. **Design security/governance:** classification, PII masking, row/column access, team roles, catalog, lineage, retention, and deletion propagation; prove analysts cannot read raw emails/phones.
6. **Design reliability/performance/cost:** retries/DLQs/reconciliation, query workload groups, partitioning, compaction, concurrency, budgets, and DR; propose freshness and pipeline lag alerts.

### Testing Matrix

| Test | Scenario | Required Evidence |
| --- | --- | --- |
| Duplicate event | Same payment event delivered twice | Curated revenue does not double |
| Late event | Refund arrives after daily close | Metrics adjust accurately with audit trail |
| Schema change | Source adds a field or alters a type | Contract check blocks breaking change or version migrates cleanly |
| Connector outage | CDC stops and offset lags | Alerts fire; recovery and replay lose or duplicate zero records |
| Bad record | Invalid amount or currency | Record enters quarantine; owner receives alert |
| Freshness breach | Pipeline lags past 10 minutes | Dashboard displays stale indicator and alert triggers |
| Access violation | Analyst attempts to query PII | Query denied/masked and logged in audit trail |
| Query overload | Ad-hoc query scans entire dataset | Workload isolation/timeouts keep dashboards within SLO |
| Data deletion | Customer requests deletion per policy | Curated and downstream copies processed per lifecycle |
| Recovery | Reprocess a failed partition | Numbers match source, idempotent, reconciled |

### Deliverables

- Architecture diagram and warehouse/lake/lakehouse decision.
- Data source inventory and ingestion matrix.
- Data contracts and schema versioning policy.
- Data model detailing grain, facts, dimensions, and semantic metrics.
- Freshness/quality SLOs and operational dashboards.
- Security/access matrix, lineage, and retention policies.
- Load, failure, replay, DR, and cost validation plan.
- ADR documenting decisions, assumptions, risks, and review triggers.

## 18. Well-Architected Review

| Pillar | Data Platform Questions |
| --- | --- |
| **Operational Excellence** | Do pipelines have owners, SLAs, catalogs, lineage, quality checks, runbooks, and replay/backfills? |
| **Security** | Are classification, least privilege, masking, encryption, keys, auditing, retention, and deletion propagation clear? |
| **Reliability** | Have checkpoints, retries, DLQs, idempotent merges, backups, restores, and reconciliations been tested? |
| **Performance Efficiency** | Is OLTP isolated from analytical workloads? Do partitioning, columnar formats, materialization, and concurrency match queries? |
| **Cost Optimization** | Are ingestion cadences, storage tiers, compute scaling/pausing, bytes scanned, egress, retention, and idle capacity controlled? |
| **Sustainability** | Are redundant copies, wasteful pipeline reruns, full-table scans, and infinite retention avoided? |

## 19. Common Mistakes

**Running BI directly on OLTP databases.** Heavy scans and joins contend for resources and couple reports to service schemas.

**Building a central data store without owners.** Nobody takes responsibility for metric definitions, quality, or dataset freshness.

**Copying source schemas verbatim as analytical models.** Source schemas optimize transactional writes, not facts, dimensions, and business metrics.

**Treating CDC as business events.** Row-level changes do not always convey business event intent.

**Choosing streaming when batch meets requirements.** Adds unnecessary broker, connector, schema, monitoring, and operational cost.

**Omitting grain definitions before joining.** One-to-many joins silently multiply monetary totals or order counts.

**Defining KPIs separately inside each dashboard.** Teams report conflicting numbers for identical business terms.

**Ignoring duplicates and late-arriving data.** Aggregates become inaccurate or historical figures shift without audit trails.

**Omitting freshness indicators.** Users mistake stale dashboards for real-time state.

**Granting analysts raw PII out of convenience.** Centralizing copies expands breach blast radius.

**Neglecting schema evolution.** Upstream changes silently break pipelines or alter metric semantics.

**Never testing replay or restore.** When a transform bug surfaces, teams lack a reliable way to regenerate data.

## 20. Data Platform Production Readiness Checklist

- [ ] OLTP and OLAP workloads are separated; heavy reports never degrade transactional databases.
- [ ] Warehouse/lake/lakehouse/ODS choices are justified by access patterns and freshness needs.
- [ ] Source domains, owners, data contracts, and emission permissions are defined.
- [ ] Batch/CDC/streaming pipelines implement checkpoints, schema handling, retries, replay, and delete semantics.
- [ ] Raw/clean/curated layers have clear boundaries, retention, and promotion criteria.
- [ ] Fact grain, dimensions, key mappings, SCDs, and metric definitions are documented.
- [ ] Semantic layers/certified datasets have owners and a business glossary.
- [ ] Freshness, completeness, validity, uniqueness, and reconciliation have SLOs and tests.
- [ ] Late events, duplicates, corrections, and backfills have explicit workflows.
- [ ] Catalog, lineage, classification, and ownership are discoverable.
- [ ] IAM, tenant/row/column policies, masking, encryption, auditing, and deletion propagation are enforced.
- [ ] Query workload isolation, partitioning, compaction, concurrency, and cost guardrails are configured.
- [ ] Pipelines have dashboards, alerts, DLQs/quarantine, and runbooks.
- [ ] Raw, curated, metadata/catalogs, keys, and pipeline state have tested backup/recovery.
- [ ] Connector outages, schema changes, duplicates, bad data, access violations, and replays have been tested.
- [ ] TCO accounts for ingestion, storage, compute, query scans, networking, logs, retention, and staffing.
- [ ] An ADR documents assumptions, trade-offs, owners, and review triggers.

An analytical data platform empowers an organization to answer cross-domain questions while keeping transactional workloads safely bounded. Great design starts from **business questions and target freshness**, then selects the warehouse/lake/lakehouse, ingestion methods, data models, and semantic definitions. Platform quality rests on source contracts, clear ownership, schema governance, secured data copies, replayability, and reconciliation. When these elements operate together, reporting and analytics scale with clear provenance, high trust, and predictable cost.
