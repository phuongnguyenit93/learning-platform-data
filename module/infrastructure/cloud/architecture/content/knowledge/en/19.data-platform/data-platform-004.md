# Tiering Raw, Standardized, and Serving Data

## Learning Objectives

A cloud data platform typically ingests data from many sources: transactional applications, payment systems, CRMs, devices, logs, SaaS platforms, and partners. Incoming data can differ in schema, format, timezone, units of measure, quality, and business meaning. Feeding data directly into dashboards or analytical models without managing provenance and transformation steps makes results hard to trust, reproduce, and investigate.

A common organizational pattern divides data into tiers:

- **Raw / Bronze:** original data ingested and retained with minimal transformation, alongside source metadata.
- **Standardized / Silver:** data that has been validated, cleaned, and standardized in schema, data types, keys, and semantics.
- **Serving / Gold:** data organized for specific consumption needs such as KPIs, reports, dashboards, analytics, ML features, or APIs.

Bronze/Silver/Gold are common names used in lakehouse architectures; not every platform strictly requires three physical layers. What matters is clearly defining **data contracts, quality bars, authoritative sources, access permissions, and operational ownership** at every boundary.

This lesson belongs to the **Data Platform** chapter and focuses on tiering raw, standardized, and serving data. It frames decisions within cloud architecture—from business requirements to storage, compute, networking, security, and deployment models—while evaluating trade-offs in reliability, security, scalability, cost, and operations per Well-Architected principles.

After this lesson, you will be able to:

- Explain the purpose, inputs, outputs, and completion criteria of each data tier.
- Design ingestion flows that support auditing, replay, and late-arriving data.
- Define data contracts, schema versions, business keys, event time, and ingestion time.
- Design workflows for validation, cleansing, deduplication, standardization, and enrichment.
- Distinguish source data, standardized data, and decision-serving business data.
- Choose batch, streaming, or hybrid pipelines based on freshness, throughput, and cost.
- Manage lineage, metadata, catalogs, quality rules, ownership, and data contracts.
- Protect data via classification, tenant isolation, retention, encryption, and least privilege.
- Design partitioning, file formats, compaction, incremental processing, and backfills.
- Build dashboards, SLAs/SLOs, reconciliation, and recovery plans.
- Evaluate costs and select a lake, warehouse, or lakehouse suited to the workload.

## 1. Why Tier Data?

Suppose a hotel/room booking platform receives data from three systems:

- Booking service records orders and booking statuses.
- Payment provider sends transactions, refunds, and chargebacks.
- CRM stores customer profiles and campaign details.

These three sources may use different conventions. Booking records timestamps in UTC while CRM uses local timezones; payment uses minor units like cents while booking uses decimals; one system represents status as `PAID` while another uses `SETTLED`; customer IDs in CRM differ from customer IDs in booking.

If revenue dashboards read directly from all three sources, each analytics team might write its own join logic, currency conversion, status filtering, and deduplication. Results quickly become inconsistent. Furthermore, an upstream schema change can break multiple dashboards without any central control point.

Tiering creates clear boundaries of responsibility:

1. Raw preserves evidence of received data and source metadata.
2. Standardized converts disparate records into structures with unified semantics.
3. Serving presents metrics or datasets ready for specific consumption purposes.

~~~mermaid
flowchart LR
    S1["Booking DB"] --> I["Ingestion"]
    S2["Payment API"] --> I
    S3["CRM"] --> I
    I --> B[("Raw / Bronze")]
    B --> T["Validate / Clean / Standardize"]
    T --> S[("Standardized / Silver")]
    S --> M["Model / Aggregate / Serve"]
    M --> G[("Serving / Gold")]
    G --> BI["BI / Dashboard"]
    G --> API["Data API"]
    G --> ML["Analytics / ML"]
~~~

Flows may be batch, streaming, or hybrid. Not all data has to pass through the exact same tool, but the tiers need contracts and lineage so you know where data originated and how it was transformed.

## 2. How Raw, Standardized, and Serving Differ

| Tier | Purpose | Level of Transformation | Primary Users | Examples |
| --- | --- | --- | --- | --- |
| Raw / Bronze | Preserve source data and ingestion evidence | Minimal; add technical metadata | Data engineers, auditors, pipelines | Original JSON events, CDC records, source CSV files |
| Standardized / Silver | Produce data with consistent schema and semantics | Parse, validate, deduplicate, normalize, and link | Data engineers, analysts, domain teams | Standardized bookings, cleaned payment transactions |
| Serving / Gold | Answer specific business questions or decisions | Business logic, aggregations, metrics, denormalization | Analysts, BI, product, APIs, ML | Daily revenue, occupancy KPIs |

### 2.1. Raw Does Not Mean Unmanaged

Raw data can be stored near its original form, yet still requires:

- An envelope or manifest recording source system, object/event ID, ingestion timestamp, and schema version.
- File integrity checks, checksums, sizes, and format verification.
- Encryption, access controls, and data classification.
- Partitioning by source, ingestion date, or tenant where appropriate.
- Handling duplicate files, retries, and late arrivals.
- Policy-driven retention, legal holds, archiving, and deletion.
- Tracking rejected or unparseable payloads.

Raw should never become an unbounded dumping ground with no owner. Raw data can contain PII, secrets, or malicious payloads; read permissions typically must be restricted more tightly than serving data.

### 2.2. Standardized Does Not Mean Erasing All Differences

Standardization must preserve meaning and source evidence. For example, convert timestamps from local timezones to UTC while keeping the source timezone or raw value when needed for auditing. Currency standardization must never collapse USD and VND into a single number without storing the currency and exchange rate applied.

The Standardized layer should clearly capture:

- Parsed fields with standardized data types.
- Rules for null, missing, invalid, and unknown values.
- Business keys, source keys, and identity mappings.
- Timestamps, timezones, currencies, units, and precision.
- Record quality status and quarantine reason codes.
- Source system, schema version, and lineage.

### 2.3. Serving Is Not an Arbitrary Copy of Silver

The Serving layer organizes data around specific business questions. For instance, a revenue dashboard needs explicit definitions for gross bookings, net revenue, refunds, taxes, commissions, and recognition dates. A customer 360 dataset may require snapshots, survivorship rules, and different access controls.

Serving data needs a semantic contract: metrics with names, formulas, grain, timezones, currencies, filters, freshness, owners, and restatement policies. Two dashboards using the same label "revenue" with different formulas is a governance problem, not merely a SQL problem.

## 3. Grain: The Unit of Each Row

Before standardizing or aggregating, define the dataset's **grain**: what does a single row represent?

Examples:

- Raw booking events: one row is one ingested event.
- Standardized bookings: one row is the standardized state of one booking at a point in time or a defined snapshot.
- Payment transactions: one row is one authorization/capture/refund/chargeback per contract.
- Serving daily revenue: one row is an aggregate by date, branch, currency, and revenue type.
- Customer activity: one row is one customer action or a customer-day summary.

Failing to define grain clearly causes double-counting. One booking can have multiple payment attempts, multiple status events, and multiple refunds. Directly joining bookings with payment events and summing `booking_amount` multiplies the booking total by the number of payment records.

### 3.1. Grain and Cardinality in Joins

Suppose the `bookings` table has one row per booking and the `payments` table has multiple rows per booking. When joining:

~~~sql
SELECT
    b.booking_id,
    b.total_amount,
    p.payment_id,
    p.amount
FROM bookings b
JOIN payments p
  ON p.booking_id = b.booking_id;
~~~

A booking with three payment events appears three times. Summing `b.total_amount` after the join triples that booking's revenue. Aggregate payments to the appropriate grain before joining, or explicitly model the one-to-many relationship.

### 3.2. Documenting Grain in Data Contracts

A strong contract answers:

- What entity, event, or snapshot does one row/event represent?
- Which key is unique at that grain?
- Can there be multiple versions/attempts for the same entity?
- Does the dataset represent current state or history?
- When the source sends an update, is the old row overwritten or retained?
- At which grain are aggregations computed?

## 4. Raw / Bronze: Ingesting and Preserving Source Data

### 4.1. Ingestion Workflow

An ingestion pipeline may include:

1. Authenticating the source and verifying permissions.
2. Receiving files, events, CDC records, or API responses.
3. Writing payloads to durable storage.
4. Recording manifests/metadata with source, timestamps, and version.
5. Verifying checksums, formats, and schema envelopes.
6. Updating ingestion status and offsets/watermarks.
7. Detecting duplicates or storing redeliveries per policy.
8. Supporting controlled replay.

The Raw layer should answer "what did the platform actually receive?". For API sources that do not support replay, retain responses or exported snapshots under appropriate permissions and retention to preserve reproducibility.

### 4.2. Ingestion Time vs. Event Time

These two timestamps often differ:

- **Event time:** when the event occurred at the source.
- **Ingestion time:** when the platform received the data.

For example, a payment occurs at 23:58 UTC, but the webhook arrives 4 minutes later. If partitioning and reporting rely solely on ingestion date, the payment gets attributed to the wrong business day.

Retain both timestamps whenever meaningful. Late-event handling requires watermarks or policies permitting updates to previously aggregated periods.

### 4.3. Append-Only Raw and Replay

Some pipelines keep Raw append-only: new data is appended without overwriting prior payloads. The benefit is auditability and replay; the cost is increased storage and needing downstream deduplication and late-data handling.

Object storage can use partitioned paths:

~~~text
raw/
  source=booking/
    ingest_date=2026-11-18/
      hour=10/
        part-00001.json
  source=payments/
    ingest_date=2026-11-18/
      hour=10/
        part-00001.json
~~~

Paths are illustrative. Partitioning should match read patterns and lifecycle needs; avoid creating excessive tiny partitions or small files. Avoid placing tenant IDs or unnecessary sensitive data in object keys when metadata/catalogs suffice.

### 4.4. File Formats

| Format | Characteristics | Use When |
| --- | --- | --- |
| JSON | Easy to exchange, flexible, larger size and higher parsing cost | APIs/events, raw ingestion |
| CSV | Simple, easy export/import, weak schema and error-prone quoting/nulls | Basic tabular exchanges |
| Avro | Explicit schema, suited for event/row-oriented serialization | Event streaming, schema evolution |
| Parquet | Columnar, high compression, efficient for analytical scans | Standardized/serving on data lakes |
| ORC | Columnar, optimized for certain engines/Hadoop ecosystems | Matching analytical workloads |
| Delta/Iceberg/Hudi table formats | Manages transactions/metadata/versions over data files | Lakehouse tables, incremental updates, and time travel per format capabilities |

No single format fits every tier. Raw can keep original payloads while optionally generating curated columnar copies; Standardized and Serving typically benefit from columnar formats for analytical queries.

## 5. Standardized / Silver: Cleansing and Normalization

Silver produces reusable datasets shared across teams. Processing typically includes parsing, type casting, validation, normalization, deduplication, identity resolution, enrichment, and quarantine.

### 5.1. Data Type Standardization

Suppose a source sends:

- `booking_id` as a string.
- `created_at` in inconsistent timestamp formats.
- `amount` as a comma-formatted string.
- `status` with inconsistent upper/lowercase.
- `currency` missing in some records.

Silver can cast `booking_id` to UUID, timestamps to UTC, `amount` to fixed-precision decimal, `status` to a domain enum, and `currency` to standardized codes.

Never silently coerce invalid data to `0` or an empty string. Distinguish clearly between:

- Null: value is explicitly absent.
- Missing: field is absent from the payload.
- Invalid: field exists but fails parsing or validation.
- Unknown: syntactically valid but unmapped semantically.
- Not applicable: field does not apply to that record type.

### 5.2. Unit and Semantic Standardization

An `amount` of `100` could mean 100 VND, 100 USD, or 100 cents. The number `100` is meaningless without currency and scale.

A standardized transaction might look like:

~~~json
{
  "transaction_id": "pay-981",
  "booking_id": "booking-123",
  "operation_type": "CAPTURE",
  "amount": 1250000.00,
  "currency": "VND",
  "occurred_at": "2026-11-18T09:15:00Z",
  "source_system": "payment-provider-a",
  "source_schema_version": 3,
  "quality_status": "VALID"
}
~~~

Illustrative example. When converting currencies, store original amount/currency, converted amount/currency, exchange rate, rate source, and effective timestamp. Never overwrite source values with converted figures without provenance.

### 5.3. Deduplication

Duplicates arise from source retries, resent files, webhook redeliveries, or CDC replays. Deduplication requires an appropriate key:

- Event ID if every event has a stable identifier.
- Source record ID + source version.
- Business key + effective version.
- Composite key per domain contract.

Do not deduplicate simply by keeping the latest row by ingestion timestamp if events can arrive out of order. Source version or event sequence numbers are often more reliable. For legitimately repeated events (e.g., two separate valid payments of the same amount), never merge them just because payloads look similar.

### 5.4. Quarantine and Invalid Data Handling

One bad record should not break an entire batch if errors can be isolated. Record:

- Raw reference or object URI.
- Source ID and schema version.
- Failed rule ID.
- Error reason, timestamp, and pipeline run ID.
- Resolution state: awaiting fix, retry, or approved exception.

Quarantine stores need appropriate access controls and retention; payloads with PII must still be protected. Establish workflows to fix upstream issues or mappings and replay safely. Never manually alter original raw data without leaving an audit trail.

## 6. Data Quality: Purpose-Driven Definitions

Quality is more than "no nulls." A dataset can have zero nulls yet still carry wrong currencies, duplicates, or SLA-breaching staleness.

Common quality dimensions:

| Dimension | Question | Example Rule |
| --- | --- | --- |
| Completeness | Are all required fields/records present? | `booking_id` is non-null |
| Validity | Are values within valid domains and formats? | `status` belongs to permitted enum |
| Accuracy | Do values match reality/authoritative sources? | `amount` reconciles with payment source |
| Uniqueness | Are there duplicates at the defined grain? | `event_id` unique within source |
| Consistency | Do related fields/systems agree? | Booking currency matches payment contract |
| Timeliness | Does data arrive on schedule? | 99% of events reach Silver within 5 minutes |
| Referential integrity | Do referenced keys exist? | `payment.booking_id` exists or is quarantined |
| Freshness | Was the dataset updated recently? | Serving snapshot newer than required watermark |

### 6.1. Data Quality Gates

A pipeline can enforce quality checks at multiple levels:

- **Hard gate:** severe error rendering records/dataset unusable; halt or quarantine.
- **Soft gate:** degraded quality that permits publishing with a warning and owner acknowledgment.
- **Aggregate threshold:** if invalid/duplicate/null ratios exceed a threshold, block publishing the serving dataset.
- **Contract violation:** schema or semantic contract broken; alert producer/owner.

Example quality report:

~~~text
Pipeline run: silver-bookings-2026-11-18-10
Input rows:              120,000
Valid rows:              119,760
Quarantined rows:            180
Duplicate rows:               60
Unknown status:               12
Null business key:             0
Quality pass threshold:    99.5%
Observed valid ratio:       99.8%
Result: PASS_WITH_WARNING
~~~

Numbers are illustrative. Explicitly define the denominator, excluded records, duplicate calculation, and thresholds based on risk severity. A 99.8% pass rate may be acceptable for clickstreams but unacceptable for a payment ledger.

## 7. Serving / Gold: Serving Data Models

Gold is organized around data products or business questions. Forms include star schemas, wide tables, aggregate tables, semantic layers, API datasets, or feature tables.

### 7.1. Star Schema for Analytics

Booking revenue example:

- `FactBooking`: one row at booking or booking-line grain.
- `DimDate`: dates and calendar attributes.
- `DimBranch`: branch locations.
- `DimCustomer`: customer attributes per privacy rules.
- `DimRoom`: room types.
- `DimChannel`: booking channels.
- `FactPayment`: payment, refund, and chargeback transactions at their own grain.

~~~mermaid
flowchart TB
    F[("Fact Booking")] --- D1[("Dim Date")]
    F --- D2[("Dim Branch")]
    F --- D3[("Dim Customer")]
    F --- D4[("Dim Room")]
    F --- D5[("Dim Channel")]
    P[("Fact Payment")] --- D1
    P --- D3
    P --- D2
~~~

Never join facts of different grains without proper pre-aggregation. Booking facts and payment facts can have a one-to-many relationship; joining directly requires careful cardinality control to avoid double-counting.

### 7.2. Metric Contracts

A business-serving metric should define:

- Name and description.
- Formula and grain.
- Numerator/denominator.
- Filters/exclusions.
- Timezone and business date.
- Currency and conversion policy.
- Handling of cancellations, refunds, taxes, fees, and chargebacks.
- Freshness/SLA.
- Owner and version.

Example:

~~~text
Net booking revenue
  = Captured booking amount
    - Successful refunds
    - Reversed/chargeback amount

Grain: business_date × branch_id × currency
Time basis: booking business timezone
Freshness target: 15 minutes
Owner: Finance Data Product
~~~

This is a sample definition; the business must confirm revenue recognition and accounting rules. Avoid having a single generic "revenue" metric if teams disagree on gross/net definitions or recognition timing.

### 7.3. Data Products

Serving datasets can be managed as data products:

- Explicit owner and identified consumers.
- Contracts, schemas, and documentation.
- Quality/freshness SLOs.
- Access permissions and data classification.
- Versioning, changelogs, and deprecation policies.
- Support channels and incident workflows.
- Storage/compute cost visibility and capacity ownership.

Not every Gold table requires heavyweight product management; apply governance proportional to sharing breadth and business impact.

## 8. Data Contracts and Schema Evolution

A data contract is an agreement between producers and consumers covering structure, semantics, quality, delivery, and schema changes. A syntactically valid schema can still break consumers if a field's meaning shifts.

A contract should specify:

- Dataset/topic name and owner.
- Grain, primary/business keys.
- Fields, types, nullability, semantics, and units.
- Event time, ingestion time, and timezone.
- Schema version and compatibility rules.
- Delivery mode, ordering, duplicates, and retention.
- Quality rules and freshness targets.
- PII classification, access policies, and deletion requirements.
- Notification process for breaking changes and deprecations.

### 8.1. Compatible Changes

Adding optional fields with explicit defaults is generally easier to keep compatible. High-risk changes include renaming fields, changing types, reducing precision, altering timezone interpretation, changing enum semantics, shifting grain, or modifying keys.

For instance, switching `amount` from integer minor units to decimal major units is a major semantic break even though the field name stays identical. Old consumers might misread monetary amounts silently without parse errors.

### 8.2. Schema Migration Workflow

1. Publish the new contract/schema.
2. Check consumer inventory and compatibility.
3. Deploy consumers capable of reading both old and new versions if needed.
4. Deploy producers emitting the new version.
5. Monitor record distribution and error rates by schema version.
6. Backfill or transform historical data if required.
7. Retire the old version after the deprecation window and once consumers have migrated.

Never mutate stored raw payloads in place. You can stand up `standardized v2` or `serving v2` in parallel and cut over consumers after reconciliation.

## 9. Batch, Streaming, and Hybrid Pipelines

| Model | Characteristics | When Suitable | Trade-offs |
| --- | --- | --- | --- |
| Batch | Collects and processes data on schedule | Hourly/daily reports, large backfills | Higher latency, bursty compute workloads |
| Streaming | Processes events continuously | Alerts, near-real-time state | Complex state, ordering, late events, and operations |
| Micro-batch | Processes short time windows | Balances near-real-time and efficiency | Latency bounded by batch interval |
| Hybrid | Streaming for freshness, batch for reconciliation/rebuilds | Critical data products | Two code paths requiring identical semantics and reconciliation |

### 9.1. Batch Pipelines

A batch job can read manifests/files from Raw, validate against schema versions, transform into standardized Parquet, run quality gates, and publish Gold partitions.

Requires idempotency per run ID/business date/source snapshot, checkpoints, atomic publishing, or staging paths. If a job fails mid-run, serving consumers must never see half-written partitions.

### 9.2. Streaming Pipelines

Streaming pipelines ingest events, parse schemas, verify keys/versions, manage state/windows, and write to Silver/Gold. Define event-time, watermarks, late arrivals, duplicate deliveries, state retention, checkpoints, and recovery.

Do not assume streaming is automatically real-time. Queue lag, checkpointing, backpressure, sink throughput, and windowing policies all impact end-to-end freshness.

### 9.3. Hybrid and Reconciliation

Streaming can update Gold in near real-time while nightly batch recomputes from historical sources for reconciliation. Both paths must share identical business definitions or document differences explicitly; otherwise, intraday dashboards and end-of-day reports will diverge without explanation.

## 10. Incremental Processing, Watermarks, and Late-Arriving Data

Re-reading all raw data every run wastes compute and network bandwidth. Incremental pipelines process only new/changed data using offsets, CDC positions, `updated_at`, event sequences, or watermarks.

A pipeline should record:

- Last committed source watermark/offset.
- Run ID and input snapshot.
- Processed data range.
- Counts of received, skipped, and quarantined records.
- Transformation code/logic version.
- Start/end timestamps and run status.

### 10.1. Watermarks

A watermark represents the point prior to which the pipeline assumes data has been sufficiently observed per policy. Watermarks do not guarantee zero late data; define allowed lateness and mechanisms to revise earlier partitions.

For example, day D reporting may provisionally close at 03:00 on day D+1, yet a payment provider might send chargebacks days later. Distinguish provisional metrics from finalized/restated metrics.

### 10.2. Late Events and Restatements

When a late event arrives:

- If the partition is still open, apply it to the open partition.
- If the partition is closed, emit a correction/restatement or delta record per policy.
- Maintain an audit trail showing which version changed a metric and why.
- Notify consumers when historical numbers can change.

Never silently overwrite previously published figures if the business requires auditability.

## 11. File Layout, Partitioning, and Compaction

Data lakes store numerous files organized by dataset/table, partition, and time. Layout affects scan cost, query latency, listing operations, and manageability.

### 11.1. Choosing Partition Keys

Common partitions include `event_date`, `ingestion_date`, `tenant`, or domain dimensions. Choose based on frequent filter predicates and cardinality.

- Too coarse: queries scan excessive data.
- Too fine/too many: metadata bloats, small files proliferate, query planning slows down.
- High-cardinality tenant partitioning can create excessive directories/partitions.
- Never partition by `customer_id` if most queries do not filter by it.
- Plan how late-arriving data writes into older partitions.

### 11.2. The Small Files Problem

Streaming or highly parallel workers can generate thousands of tiny files. Query engines must read bloated metadata and open many files, increasing request costs and planning latency.

Compaction merges small files into larger ones sized appropriately for the engine and storage. Avoid compaction colliding with concurrent writers, and avoid rewriting excessive data for negligible benefit.

### 11.3. Columnar Layout and Predicate Pushdown

Parquet/ORC allow reading only required columns while leveraging statistics, encoding, and compression. Partition pruning and predicate pushdown reduce bytes scanned when query filters align. However, query engines and table formats have distinct semantics; benchmark with realistic schemas, file sizes, and queries.

## 12. Lake, Warehouse, and Lakehouse

| Architecture | Strengths | Limitations / Considerations |
| --- | --- | --- |
| Data lake | Diverse data storage, object storage economics, raw & large-scale processing | Requires self-managing catalog, schemas, quality, transactions, and governance |
| Data warehouse | Well-managed SQL/BI, concurrency, and semantic analytics | Compute/storage costs, ingestion, and service-dependent portability |
| Lakehouse | Combines object storage with table formats/catalogs/transactions for analytics | Requires managing engine compatibility, metadata, compaction, and transaction semantics |

Lakehouses typically use table formats such as Delta Lake, Apache Iceberg, or Apache Hudi to add metadata, snapshots/versioning, schema evolution, and transaction semantics atop object storage. Exact capabilities vary by format, engine, catalog, and version; do not assume identical feature support across all tools.

You can store Raw on object storage, Silver/Gold as lakehouse tables, and use a warehouse/serving engine for BI. A platform can combine multiple storage engines instead of forcing everything into one service.

## 13. Governance, Catalog, and Lineage

### 13.1. Metadata Catalog

A catalog helps users find datasets and understand schemas, owners, quality, classification, and access permissions. Metadata should capture:

- Business name and technical name.
- Description, domain, and owner/steward.
- Grain, schema, field semantics, and examples.
- Source systems and upstream dependencies.
- Update frequency/freshness.
- Quality score and known limitations.
- Classification, retention, and access request process.
- Consuming dashboards/models/APIs.

Do not let the catalog become a bare list of table names. Metadata should be updated automatically by pipelines with accountable people curating business semantics.

### 13.2. Data Lineage

Lineage traces data from sources through ingestion, transformations, and intermediate datasets to dashboards/APIs/models. Levels include:

- **Table-level lineage:** which tables depend on which tables.
- **Column-level lineage:** which source columns/expressions produce each output column.
- **Run-level lineage:** which pipeline run produced which partition/file/version.
- **Business lineage:** which metrics inform which business decisions.

When a metric looks wrong, lineage isolates the upstream source or transformation at fault. Before changing a field, lineage identifies all impacted consumers.

### 13.3. Ownership and Stewardship

Every critical dataset needs an owner empowered to decide contracts, quality thresholds, access, and deprecation; a steward/domain expert who understands semantics; and a platform team operating storage/compute/governance. Never assign a generic "data team" as the sole owner for all business definitions.

## 14. Security and Privacy Across Tiers

Raw generally holds the most original data, including sensitive fields or unfiltered payloads. Standardized and Serving tiers strip unnecessary fields, yet still carry risks of re-identification or leakage through small aggregates.

Principles:

1. **Classification:** label public, internal, confidential, restricted, or equivalent tiers.
2. **Least privilege:** separate roles for raw ingestion, transformations, serving readers, analysts, and administrators.
3. **Encryption:** encrypt in transit and at rest; manage key lifecycles and rotation.
4. **Data minimization:** Silver/Gold retain only fields needed for approved use.
5. **Masking/tokenization:** obfuscate or tokenize identifiers for consumers who do not need raw values.
6. **Tenant isolation:** verify partitioning, filters, and authorization rather than relying solely on folder paths.
7. **Auditing:** log reads, exports, policy edits, and replays.
8. **Retention/deletion:** enforce lifecycles and propagate deletions across Raw, Silver, Gold, caches, indexes, and backups as required.
9. **Secrets:** never write tokens, passwords, or credentials into raw events or logs.
10. **Egress control:** restrict outbound data paths and govern dataset sharing.

Masking a field in a dashboard does not mean it has been deleted from Raw or archive files. Maintain deletion/anonymization workflows spanning all copies with verifiable completion evidence.

## 15. Data Reliability: Backfills, Replays, and Disaster Recovery

Pipelines can fail due to schema changes, networking, quotas, storage outages, code bugs, or unavailable downstreams. Recovery must avoid producing corrupt data or overwriting good results.

### 15.1. Idempotent Pipelines

An idempotent pipeline yields equivalent outputs without duplicating records when rerun on the same input/version. Techniques include:

- Unique business keys and source versions.
- Keyed `MERGE`/upsert operations.
- Controlled partition overwrites from deterministic input snapshots.
- Run IDs and manifests.
- Atomic publish/commit via the table format.
- Advancing checkpoints only after output commits.
- Deduplication using event identities and domain semantics.

Avoid blindly appending the same files/batches on retry without run-level deduplication or an atomic commit protocol.

### 15.2. Backfills

Backfills require defining time/key ranges, input snapshots, transformation versions, partition scopes, compute capacity, cost, production impact, and reconciliation methods. Use isolated compute or rate limits to protect live pipelines.

### 15.3. Disaster Recovery

Define RPO/RTO across Raw, Standardized, Serving, and metadata/catalogs. Raw may require cross-region replication/object versioning; table metadata and catalogs require backups; Serving can be rebuilt from Silver if time and sources allow.

Having Parquet files alone does not guarantee table recovery. You also need manifests, schemas, transaction metadata, catalogs, encryption keys, and matching code/config versions.

## 16. Observability: Freshness, Quality, and Pipeline Health

A green pipeline does not guarantee usable data. A job can exit 0 while reading the wrong partition, dropping 30% of records, or publishing stale datasets.

Monitor per tier:

| Tier | Metrics | Question |
| --- | --- | --- |
| Ingestion / Raw | Source lag, file counts/sizes, checksum failures, ingest delay, duplicates | Did source data arrive completely and intact? |
| Standardized / Silver | Input/output rows, valid/quarantined/duplicate counts, schema failures, transform duration | Is data clean and compliant with contracts? |
| Serving / Gold | Freshness, row counts, metric totals, publication version, query latency | Do consumers have fresh, accurate datasets? |
| Platform | CPU/memory, storage, I/O, queue lag, networking, quotas | Where are infrastructure bottlenecks? |
| Governance | Access denials, policy violations, PII scans, retention status | Is data properly protected? |
| Cost | Storage by tier, bytes scanned, compute hours, egress, cost per product | What is driving cost growth? |

### 16.1. Freshness and Completeness

Measure freshness from event time or source update time to serving dataset publication. Always specify which timestamp is measured.

Completeness requires reconciling against manifests/source counts, watermarks, sequence gaps, or control totals. If sources cannot supply expected totals, reconcile using domain rules and observation windows.

### 16.2. Data Reconciliation

Example reconciliations:

- Booking count per business date between source and Silver.
- Captured totals per currency between payment provider and standardized payments.
- Total refunds/chargebacks per period.
- Row counts per partition and maximum source version.
- Gold revenue totals compared against an independent calculation over Silver.

A discrepancy is not necessarily a bug if timing or business rules differ; classify discrepancies as expected lag, late events, adjustments, or defects.

### 16.3. Actionable Alerts

- Expected file or source events missing within window.
- Ingestion lag exceeding SLA.
- Schema contract break or spiking quarantine rate.
- Quality gate failure.
- Serving dataset older than freshness SLO.
- Reconciliation mismatch exceeding threshold.
- Backfill/rebuild consuming excessive capacity or budget.
- Abnormal growth in storage/metadata small files.
- Policy scans detecting unauthorized sensitive fields in Gold.

Every alert needs an owner, severity, dashboard, and runbook. Alerts without clear remediation create noise.

## 17. Cost and Storage/Compute Optimization

Data platform costs include:

- Object storage, versioning, replication, and API requests.
- Compute for ingestion, transformation, streaming, and querying.
- Warehouse/serverless SQL bytes scanned or provisioned capacity.
- Brokers, catalogs, metadata services, and orchestration.
- Network transfers, cross-region/cross-zone traffic, and egress.
- Logs, metrics, traces, and audit log retention.
- Backups, archives, restore drills, and disaster recovery.
- Data governance, scanning, and security tooling.
- Staffing for operations, quality incidents, and data product support.

### 17.1. Storage Lifecycle

Tier data across hot/warm/cold/archive:

- Keep recent Raw or frequently queried datasets on low-latency storage tiers.
- Move infrequently accessed historical data to cheaper storage classes when retrieval latency is acceptable.
- Retain Raw archives per retention/audit policy; do not retain all copies indefinitely.
- Store Serving aggregates only at required history depth and grain.
- Enforce TTLs and ownership on temporary/staging/quarantine data.

Lifecycle policies must account for table formats, snapshots, delete markers, legal holds, and retrieval fees. Never delete files directly via storage lifecycle rules if lakehouse table transaction metadata/snapshots still reference them.

### 17.2. Compute Optimization

- Use incremental processing instead of full scans when semantics allow.
- Choose partitioning and columnar formats to cut bytes scanned.
- Schedule and threshold-trigger small-file compaction.
- Isolate interactive BI compute from heavy backfills when needed.
- Autoscale on queue lag or query concurrency with strict quotas and cost guardrails.
- Shut down idle dev/test resources.
- Use spot/preemptible compute for checkpointed, retryable jobs.
- Cap query scan sizes and heavy workloads per tenant/team.

### 17.3. Cost per Data Product

~~~text
Cost per published data product
  = (Storage + ingestion + transformation + query
     + network + observability + governance cost)
    / Number of valid published data products or business uses
~~~

You can track cost per million records, cost per TB scanned, cost per dashboard/query, or spend by domain/team. Pick denominators reflecting real business value, avoiding optimizations that lower unit cost at the expense of freshness or accuracy.

## 18. Case Study: Multi-Source Booking Platform

### 18.1. Context

A booking platform ingests continuous booking events, payment transactions from providers, customer profiles from CRM, and daily reconciliation files. Leadership needs near-real-time occupancy/revenue dashboards; Finance needs reconciled end-of-day figures; Operations needs multi-criteria booking search.

Assumed requirements:

- Booking lists update within 2 minutes.
- Operations dashboards achieve p95 freshness under 5 minutes.
- End-of-day financial reports finalize after reconciliation.
- Zero double-counting of payment captures/refunds.
- Sensitive customer attributes visible only to authorized roles.
- Serving data can be rebuilt from governed sources when metric logic changes.

### 18.2. Three-Tier Design

**Raw / Bronze**

- Append-only booking events with source event ID, event time, ingestion time, and schema version.
- Payment webhooks/files preserving raw references, checksums, provider IDs, and ingestion batches.
- CRM snapshots carrying source export timestamps.
- Malformed records routed to a restricted quarantine zone with metadata.

**Standardized / Silver**

- Bookings mapped to unified `booking_id`, `tenant_id`, booking status, business timezone, and source version.
- Payments standardized with operation type, decimal amount, currency, provider transaction ID, and state.
- Refunds/chargebacks stored at their own grain, linked to bookings/payments via business keys.
- Customer identity mapping managed with explicit lineage and policy.
- Deduplicated by event/source ID and source version; late events update according to rules.

**Serving / Gold**

- Operational booking view powering search and lists.
- Daily occupancy aggregates by branch, date, and room type.
- Revenue model by business date, branch, and currency, separating captures, refunds, and chargebacks.
- Finance daily close dataset carrying reconciliation status and finalized version.

~~~mermaid
flowchart TB
    subgraph SOURCES["Sources"]
      B["Booking events"]
      P["Payment provider"]
      C["CRM exports"]
      F["Daily reconciliation files"]
    end
    B --> RAW[("Raw / Bronze")]
    P --> RAW
    C --> RAW
    F --> RAW
    RAW --> SILVER["Parse / validate / standardize / deduplicate"]
    SILVER --> STD[("Standardized / Silver")]
    STD --> OPS["Operational booking projection"]
    STD --> REV["Revenue / occupancy model"]
    STD --> FIN["Finance reconciliation model"]
    OPS --> GOLD[("Serving / Gold")]
    REV --> GOLD
    FIN --> GOLD
    GOLD --> DASH["Dashboard / BI"]
    GOLD --> API["Search and data APIs"]
~~~

### 18.3. Handling Late Payments

A capture webhook has event time 23:58 but arrives at 00:04. Raw records the new ingestion date while preserving the prior event time. Silver deduplicates by provider transaction ID and operation type. The Gold revenue model updates the corresponding business-date partition or records an adjustment/restatement per policy. The Finance close dataset logs version and reconciliation status; published figures are restated with an audit trail rather than silently overwritten.

### 18.4. Handling Metric Definition Changes

Finance updates the net revenue formula to separate confirmed chargebacks from disputed ones. Do not modify the existing metric without versioning. Create a v2 metric contract, build Serving v2 in parallel, compare outputs against samples and control totals, notify consumers, and migrate dashboards after sign-off. Retain v1 according to committed retention policies.

### 18.5. Security Controls

Only pipeline roles can access Raw payment/CRM data; Silver drops or tokenizes fields unnecessary for analytics; Gold exposes only required dimensions and metrics. Query APIs enforce tenant scope and RBAC. Exports, reads, and schema edits are audited. Deletion requests propagate to downstream copies and indexes per policy.

## 19. When to Keep Tiers Simple vs. Deeply Separated

| Signal | Potentially Suitable Approach |
| --- | --- |
| Single source, few dashboards, low volume | Simple curated pipeline; keep raw snapshots if audits require |
| Multiple sources/schemas and diverse consumers | Shared Raw + Standardized tiers; domain-specific Serving |
| BI queries impacting transactional systems | Separate data platform and serving store |
| Audit/replay needs and frequent logic changes | Immutable Raw with retention and lineage |
| Sub-minute/few-second freshness required | Streaming/micro-batch with serving projections |
| Finance requires reconciled closing numbers | Batch close, watermarks, reconciliation, and restatement versioning |
| Small ops team, limited data engineering capacity | Managed ingestion/warehouse; minimize tiers and tools |
| Unclear schemas and ownership | Clarify data contracts/owners before splitting across many stores |

Not every dataset requires three physically separate storage tiers. A tier might be a separate schema, table format, or logical view. Physical separation depends on risk, volume, access patterns, freshness, compliance, and team capacity.

## 20. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Querying Raw directly from dashboards | Duplicated query logic, inconsistent numbers | Standardize and define serving metrics |
| Treating Silver as merely renamed Raw | No contracts or quality guarantees | Define types, keys, semantics, and rules |
| Gold without grain or formulas | Double-counting and disputed numbers | Metric contracts and reconciliation |
| Overwriting raw payloads | Loss of auditability and replay | Immutable/append-only or versioned capture |
| Using ingestion date instead of event time | Misattributed business periods | Keep both event time and ingestion time |
| Deduplicating by identical payload | Merging two valid distinct transactions | Use business keys/source event identities |
| Ignoring late data | Incomplete or wrong historical reports | Watermarks, allowed lateness, and restatements |
| Appending blindly on job retries | Duplicate records | Idempotent writes, run IDs, and commit protocols |
| Generating excessive small files | Metadata/query overhead | Compaction and sensible partitioning |
| Copying PII into every serving store | Elevated risk and deletion cost | Data minimization, masking, and lineage |
| No owners or lineage | Incidents go unowned | Dataset owners, catalogs, and dependency maps |
| Unbounded rebuilds in production | Exhausts compute/storage/IO | Isolate, throttle, budget, and plan backfills |

## 21. Practice Exercise

A retail company has three sources: POS terminals sending near-real-time transactions, an ERP sending product/inventory updates hourly, and a CRM sending customer records daily. Executives want store-level revenue dashboards updated within 5 minutes; Finance needs reconciled end-of-day closing reports; Marketing needs campaign-level customer analytics. The data contains PII and multiple currencies.

Complete the following:

1. Define Raw, Standardized, and Serving datasets for each source, specifying grain and business keys.
2. Design a data contract for POS transactions including event time, ingestion time, currency, operation type, and schema version.
3. Specify Silver validation, normalization, deduplication, and quarantine rules.
4. Design Gold metrics for gross sales, net sales, refunds, and daily close, defining currency and timezone rules.
5. Choose batch/streaming/hybrid for the 5-minute dashboard and end-of-day reports.
6. Design watermarks and late-arrival/restatement handling for delayed POS transactions.
7. Choose partition keys and file formats; explain how to prevent small files.
8. Trace lineage from POS to Gold dashboards and identify owners at each boundary.
9. Design classification/access policies so Marketing cannot read unnecessary raw PII.
10. Propose quality gates, reconciliations, and at least six alerts with runbooks.
11. Build a TCO estimate covering raw retention, compute, storage, queries, networking, and observability.
12. Write an ADR selecting lake/warehouse/lakehouse along with review triggers.

**Self-assessment guidance:** A strong design specifies grain, sources of truth, business keys, metric semantics, freshness, late-data policies, access controls, and reconciliation evidence. Simply drawing three boxes labeled Bronze/Silver/Gold is not a complete data platform design.

## 22. Production Readiness Checklist

- [ ] Every tier has clear purpose, owners, contracts, grain, and consumers.
- [ ] Raw retains source metadata, event/ingestion times, schema versions, checksums, and retention.
- [ ] Raw payloads and quarantine stores are classified, encrypted, and access-restricted.
- [ ] Silver enforces types, timezones, units, identity mapping, deduplication, and quality rules.
- [ ] Invalid records carry reason codes, owners, and replay/remediation workflows.
- [ ] Gold defines metric contracts, grain, formulas, currencies, timezones, freshness, and versions.
- [ ] Fact tables state grain explicitly to avoid fan-out joins and double-counting.
- [ ] Schema evolution includes compatibility tests, deprecations, and migration plans.
- [ ] Batch/stream pipelines implement checkpoints, watermarks, backfills, and idempotency.
- [ ] Late events and restatements follow explicit policies and audit trails.
- [ ] Partitioning/file layouts are benchmarked; small files have a compaction plan.
- [ ] Catalogs, lineage, and dependency maps are kept current.
- [ ] Tenant isolation, masking, deletion propagation, and audits are tested.
- [ ] Source-to-standardized-to-serving reconciliation is in place.
- [ ] Dashboards track freshness, completeness, quality, lag, cost, and query latency.
- [ ] RPO/RTO, backup/restore, and rebuild drills cover both data and metadata.
- [ ] TCO includes storage, compute, queries, networking, observability, governance, and operations.

## 23. Well-Architected Review

| Pillar | Questions When Designing Data Tiers |
| --- | --- |
| **Operational Excellence** | Do datasets have owners, contracts, lineage, quality gates, runbooks, backfills, and release workflows? |
| **Security** | Do Raw/Silver/Gold enforce classification, least privilege, encryption, tenant isolation, retention, and deletion? |
| **Reliability** | Do ingestion, transformation, and serving implement idempotency, checkpoints, replay, reconciliation, and recovery? |
| **Performance Efficiency** | Do grain, file formats, partitioning, compaction, incremental processing, and query engines match access patterns? |
| **Cost Optimization** | Are retention, storage tiers, bytes scanned, compute, egress, and cost per data product monitored? |
| **Sustainability** | Are full refreshes, duplicate processing, unnecessary scans, and redundant copies avoided? |

**Conclusion:** Raw preserves evidence of received data; Standardized establishes unified semantics and quality; Serving turns data into decision-ready products. Three tiers are only effective when backed by clear grain, contracts, ownership, lineage, quality, freshness, and access controls. Choose physical separation and technologies based on workloads, operational capacity, and cost; design pipelines to reconcile, replay, and rebuild while protecting data from ingestion to consumer in line with Well-Architected principles.
