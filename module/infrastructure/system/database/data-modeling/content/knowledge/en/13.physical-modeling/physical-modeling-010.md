# Deletion Policies, Long-Term Archiving, and Storage Growth Over Time

## Learning Objectives

In the **DATABASE_DATA_MODELING** module, data design does not end once entities, relationships, keys, and indexes are defined. A sound physical schema must also answer: **how long is data retained, where does it move, how is it deleted, and how much storage will the system need after one or many years?**

This lesson in the **Physical Modeling** chapter helps you:

1. Design the **data lifecycle** from creation, active use, and long-term archiving through safe deletion.
2. Distinguish **soft deletion**, **hard deletion**, **cold archiving**, **anonymization**, and **policy-driven expiration**.
3. Build a **retention policy** tied to data category, business purpose, retention clock trigger, and legal exceptions.
4. Assess the impact of foreign keys, transactions, backups, CDC, caches, and derived data on deletion requirements.
5. Choose **partitioning, indexes, TTL, batch purges, and archiving** based on volume and access patterns, avoiding confusing logical hiding with freeing storage.
6. Estimate storage growth from record counts, actual row sizes, indexes, replicas, backups, and headroom.
7. Establish metrics, restore tests, and operational evidence so policies remain enforceable, verifiable, and evolvable.

## 1. Why Must Deletion and Archiving Be Designed from the Start?

Consider a sales system with these data groups:

~~~text
CUSTOMERS       -- Customer profiles
ORDERS          -- Orders
ORDER_ITEMS     -- Order lines, price at purchase time
PAYMENT_EVENTS  -- Payment events
AUDIT_EVENTS    -- Operation audit logs
SESSION_EVENTS  -- Login session events
PRODUCT_IMAGES  -- Image files stored in object storage
~~~

Suppose you design only keys and CRUD operations **without** defining lifecycles:

- `AUDIT_EVENTS` grows unbounded, bloating indexes, slowing backups, and consuming hot storage even though most events are only queried briefly.
- Support staff click "delete customer", yet the record lingers in order history, logs, search indexes, or reporting replicas.
- Hard-deleting `CUSTOMERS` fails due to the foreign key on `ORDERS.customer_id`; carelessly switching to `ON DELETE CASCADE` risks wiping out financial transaction evidence.
- Data moved to cold storage, yet restore procedures were never tested; when reconciliation is needed, **it cannot be read back**.
- Storage climbs steadily while operations watches only base-table size, forgetting indexes, replicas, WAL, dead tuples, backups, and external object files.

Therefore, **deletion and long-term archiving policies are part of the data model**, not an afterthought cleanup cron job.

## 2. Concepts That Must Not Be Equated

| Concept | Actual Action | Does Data Still Exist? | Typical Purpose |
|---|---|---|---|
| **Soft delete** | Marks `deleted_at`, `status`, or a tombstone | **Yes**, in primary storage | Hide from active workflows; recoverable |
| **Hard delete** | Removes record/object from a specific store | Replicas, unreclaimed pages, or backups may still hold copies | End lifecycle in primary store |
| **Archive** | Moves infrequently accessed data to a cost/retrieval-appropriate tier | **Yes**, in another location/lifecycle | Reconciliation, history, rare lookups |
| **Expiration** | Marks data as past its policy retention window | Not necessarily deleted immediately | Identify records eligible for disposition |
| **Anonymization** | Transforms data so individuals are no longer identifiable given context and auxiliary data | Aggregate non-identifying stats may remain | Analytics after identification purpose ends |
| **Pseudonymization** | Replaces identifiers with tokens/codes re-linkable via controlled mapping | **May still constitute personal data** | Reduce exposure; support access separation |
| **Cryptographic erasure** | Destroys ability to read encrypted data by destroying appropriate keys | Ciphertext may remain | Conditional deletion mechanism requiring separate assessment |

**Hiding a record from the UI does not mean data has been removed from the system.** Likewise, moving a table to an archive does not mean retention obligations have ended.

### Hard Deletion and Reclaiming Disk Space Are Two Different Things

In MVCC databases like PostgreSQL, `DELETE` makes rows invisible to new transactions without **immediately shrinking disk files**. Space reclamation (such as `VACUUM`) makes space **reusable internally**, whereas physically shrinking underlying files is a separate operation with specific tooling and locking trade-offs.

For object storage, deleting an object key also does not necessarily erase all **versions**, replicas, or copies locked under immutability policies. Therefore, deletion reports must distinguish **inaccessible in the application**, **purged from primary store**, **derived stores handled**, and **replica/backup lifecycle completed**.

## 3. Modeling the Data Lifecycle

A typical lifecycle model:

~~~mermaid
flowchart LR
    A["Data created"] --> B["Active / hot"]
    B --> C["Infrequent access / warm"]
    C --> D["Long-term archive / cold"]
    D --> E["Eligible for disposal"]
    E --> F{"Retention exception?"}
    F -->|Yes| G["Retain under control"]
    G --> F
    F -->|No| H["Purge and reconcile"]
~~~

This is a **reference model**; not every record passes through every tier. For example:

- Short-lived login sessions may move straight from **hot** to **purge**.
- Finalized invoices may transition from **hot** to **archive** before reaching retention end.
- Customer profiles may be hidden from the app first while a subset of data remains retained to satisfy valid obligations.
- Records under a **legal hold** or evidence preservation order pause purging even past normal expiration.

In physical design, identify the **trigger event** for each state transition, decision ownership, affected datasets, and completion proof.

### Storage Lifecycle Does Not Equal Business Status

A `CANCELLED` order does not automatically mean deletable. A `COMPLETED` order may require long retention for reconciliation. `status` describes **business state**, whereas `retention_until`, `archived_at`, and `purge_eligible_at` describe **storage lifecycle**. The two are related yet should not replace one another.

## 4. Writing Retention Policies from Purpose and Data Category

A **retention policy** must answer:

1. **Scope:** data category, grain, owner, and every replica/copy location.
2. **Purpose:** why keep it—daily operations, reconciliation, security, analytics, or other obligations.
3. **Start point** (*retention trigger*): creation time, transaction completion, contract end, account closure, or another event.
4. **Duration:** length and calendar/timezone calculation rules, including policy-version transitions.
5. **End-of-term action:** deletion, anonymization, tier migration, or manual review.
6. **Exceptions:** disputes, investigations, legal holds, immutable backups, sync errors, records serving multiple purposes.
7. **Evidence:** decision logs, processed counts, reconciliation outputs, approval trail, policy history.

### Example Policy Matrix

Durations below are **illustrative exercise assumptions only**, not legal mandates or recommended defaults:

| Data Category | Illustrative Trigger | Hot | Archive | End of Lifecycle | Notes |
|---|---|---|---|---|---|
| Session events | When event occurs | 30 days | Not needed | Delete after 90 days | Check incident investigation needs |
| Application logs | When log is emitted | 14 days | Next 60 days | Delete at expiration | Avoid logging sensitive personal payloads |
| Orders | When order finalizes | 12 months | Until approved retention milestone | Delete/anonymize on valid basis | Transaction obligations vary by jurisdiction |
| Payment audit | When payment event settles | 90 days | Stored in access-controlled vault | Per dedicated policy | Do not infer retention solely from orders table |
| Product media | When file version is superseded | Per serving needs | May keep prior versions | Delete obsolete versions and copies | Check object versioning and CDNs |
| Derived analytics | When batch/model runs | Per analytical needs | May keep aggregates | Delete or anonymize alongside source | Derived data also has a lifecycle |

Actual durations must be confirmed by data owners, legal/compliance, and security for the **applicable jurisdictions and purposes**. No universal rule like "keep all orders 7 years" or "delete all logs after 30 days" applies to every system.

### Avoiding the "Retention Clock" Trap

For example, "keep orders for 24 months" is ambiguous without specifying **24 months from when**. An order may be created on day 1, paid on day 3, delivered on day 10, and settled on day 15. When counting from completion, pick an immutable trigger, define rules for forever-open or reopened orders, and handle erroneous source timestamps.

A single record can be subject to **multiple retention obligations**. Never pick the shortest duration just to save space: permit purging only after **all retention obligations** have expired and no hold exceptions apply.

## 5. Encoding Policies into Logical Models and Physical Schemas

Commonly useful fields:

| Field / Attribute | Meaning | Notes |
|---|---|---|
| `created_at` | Record creation timestamp | Not necessarily the retention trigger |
| `business_finalized_at` | When business event settled | Useful trigger for orders/invoices |
| `deleted_at` | Marked no longer active | **Does not** mean purged |
| `archived_at` | Successfully moved to archive store | Set only after verified completion |
| `purge_eligible_at` | Earliest date eligible for purge review | May shift with policy updates or exceptions |
| `retention_policy_version` | Policy version applied to decision | Supports auditing policy changes |
| `legal_hold` or hold reference | Special preservation flag | Often warrants a dedicated hold table/approval flow |
| `tenant_id` | Ownership and isolation scope | Include in relevant queries and keys as needed |

You do not need **every field on every table**. For immutable event data, purge eligibility can be derived from `occurred_at` plus policy version. For data with frequent exceptions, a `retention_holds` table and separate workflow metadata are far easier to govern than a free-form `hold_reason` text column.

### Temporal Fields and Consistency

Use timezone-aware temporal types where supported, store consistent absolute instants, and convert to local timezones only when applying calendar business rules. Notice differences between "90 days", "3 calendar months", "end of local business day", and "until instant X"; these phrases are **not always equivalent**.

When policies change, decide how existing records behave: recompute `purge_eligible_at`, grandfather under approved policy versions, or review separately. Avoid tweaking one parameter and accidentally wiping historical data on the next job run.

## 6. Soft Delete: Useful, Yet Never a Complete Solution

Soft deletion fits when users need **recovery** for a grace window, workflows require review before hard deletion, or visibility must stop immediately while downstream systems process asynchronously.

Example using **PostgreSQL syntax**:

~~~sql
CREATE TABLE customer_profiles (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL,
    display_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,
    purge_eligible_at TIMESTAMPTZ
);

-- Illustrates uniqueness ONLY among active profiles.
-- Choose this policy only if emails may be reused
-- after an old profile is soft-deleted.
CREATE UNIQUE INDEX uq_customer_profiles_active_email
    ON customer_profiles (email)
    WHERE deleted_at IS NULL;

-- Soft-delete a profile per approved business decision.
UPDATE customer_profiles
SET deleted_at = now(),
    purge_eligible_at = now() + INTERVAL '30 days'
WHERE customer_id = 123
  AND deleted_at IS NULL;

-- Business queries must actively exclude soft-deleted rows.
SELECT customer_id, email, display_name
FROM customer_profiles
WHERE deleted_at IS NULL;
~~~

**Critical caveats:**

- `deleted_at` does not stop queries from reading deleted rows if a developer forgets the filter. Use **views, privileges, row-level security**, or a data-access layer for consistent defense; test all read paths.
- The partial `UNIQUE` index above allows the same email in a **soft-deleted profile** and an **active profile**. If business rules forbid reuse or require historical duplicate detection, design differently.
- Restoring an old profile can trigger an **email collision** with a newer profile. Build a conflict resolution workflow instead of blindly setting `deleted_at = NULL`.
- `purge_eligible_at` is only an **eligibility timestamp**, not automatic permission to purge while other holds exist.
- Soft-deleted rows still occupy storage and affect backups, indexes, access control, and query performance.

### When Not to Use Soft Delete?

For a fully rebuildable cache table, keeping tombstones for years adds no value. For sensitive data that must be erased after a valid deadline, setting `deleted_at` **without an actual purge workflow** fails retention end-of-life goals.

In distributed systems, tombstones sometimes must survive long enough to **prevent deleted records from syncing back**; tombstone TTLs must exceed replication/CDC windows rather than being purged arbitrarily before all peers receive the delete event.

## 7. Hard Deletion and Foreign Keys: Choose Behavior by Business Rules

A typical schema:

~~~text
CUSTOMERS(customer_id, ...)
ORDERS(order_id, customer_id, ...)
ORDER_ITEMS(order_id, line_no, ...)
PAYMENT_EVENTS(payment_event_id, order_id, ...)
~~~

Not every child table shares its parent's deletion policy:

- Deleting a draft shopping cart may validly delete attached draft items.
- Deleting a customer profile **does not automatically** authorize deleting settled orders or payment vouchers.
- Payment records may have a different lifecycle from profiles, while reporting needs anonymized revenue totals.

Foreign key behaviors:

| Behavior | When Appropriate | Risk If Misused |
|---|---|---|
| `ON DELETE RESTRICT` / `NO ACTION` | Block parent deletion while child rows require handling | Purge job must resolve dependencies first |
| `ON DELETE CASCADE` | Child records truly live/die with parent and may be purged together | Can wipe across many tables, destroying records that must stay |
| `ON DELETE SET NULL` | Relationship is optional and column allows `NULL` | Loses reference; breaks semantics if child requires an owner |
| Decoupling / tokenization | Must retain events while severing identity link | Must still assess re-identification risk from remaining fields |

**Never enable `CASCADE` just to make a `DELETE` statement succeed.** Before deleting, map dependencies, define grain, and uphold each dataset's retention obligations.

### Deleting Data with Complex Relationships

A purge workflow can follow these steps:

1. Block new writes for the target subject if required by the workflow.
2. Verify authorization, retention policy, legal holds, and open transaction states.
3. Map the **reference graph**: foreign keys, replicas, objects, search indexes, analytical warehouses, and queues.
4. Delete, anonymize, or retain each group per its policy inside resumable transactions or workflows.
5. Record **execution outcome and minimal necessary proof**, avoiding copying sensitive data into deletion logs.
6. Verify the subject is unreachable through required read paths; track lagging derived copies.

A deletion request may reach "removed from application, awaiting backup expiration" rather than falsely claiming "erased everywhere immediately" without basis.

## 8. Time Partitioning and High-Volume Purging

For high-volume event data with time-based retention, **range partitioning by time** usually beats row-by-row deletes across an entire table.

### PostgreSQL Example: Monthly Event Table

~~~sql
CREATE TABLE audit_events (
    tenant_id BIGINT NOT NULL,
    event_id BIGINT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    PRIMARY KEY (tenant_id, occurred_at, event_id)
) PARTITION BY RANGE (occurred_at);

CREATE TABLE audit_events_2027_01
    PARTITION OF audit_events
    FOR VALUES FROM ('2027-01-01 00:00:00+00')
               TO ('2027-02-01 00:00:00+00');

CREATE TABLE audit_events_2027_02
    PARTITION OF audit_events
    FOR VALUES FROM ('2027-02-01 00:00:00+00')
               TO ('2027-03-01 00:00:00+00');

CREATE INDEX idx_audit_tenant_time
    ON audit_events (tenant_id, occurred_at DESC);
~~~

**Design notes:**

- A partitioned table's primary key in PostgreSQL must include **the partition key column** here; hence `occurred_at` appears in `PRIMARY KEY`. It does **not** automatically guarantee global `event_id` uniqueness across differing `occurred_at` values; if global uniqueness is required, add a dedicated identity/uniqueness strategy.
- Pre-create partitions for upcoming periods, handle late arrivals, and standardize UTC/timezone boundaries.
- Queries filtering `occurred_at` cleanly benefit from **partition pruning**, scanning fewer partitions; actual gain depends on execution plans and workload.
- Too many tiny partitions bloat metadata, planning time, and index maintenance. Not every table belongs partitioned.

Example pruning-friendly query:

~~~sql
SELECT tenant_id, event_id, occurred_at, event_type
FROM audit_events
WHERE tenant_id = 42
  AND occurred_at >= TIMESTAMPTZ '2027-01-15 00:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2027-02-01 00:00:00+00';
~~~

### Archive-Then-Drop Partition Workflow

A safe workflow can include:

1. Identify partitions **wholly prior to the eligibility cutoff** containing zero legal-hold or extended-retention rows.
2. Export the partition to the chosen long-term format/tier.
3. Verify row counts, checksums/manifests, metadata, readability, and access permissions.
4. Approve removal from hot storage; detach or perform the DBMS equivalent.
5. Only **after** verifying the archive and retention gates, physically drop source storage objects per runbook.
6. Verify disk space, replicas, backups, and audit traceability.

In PostgreSQL, `ALTER TABLE ... DETACH PARTITION ...` **only detaches the partition from the parent tree** without deleting the detached table's data files. Dropping that table afterward is **destructive**: never put it in a cron job without guardrails, recovery verification, and explicit approval.

### Partitioning Does Not Replace Policy

You cannot drop a whole partition if even one record inside requires longer retention. When retention counts from **transaction settlement date** rather than event creation time, partitioning by `occurred_at` may not align cleanly with purge eligibility. In such cases adjust the partitioning strategy, extract held records, or purge selectively.

## 9. Batch Purging When Whole Partitions Cannot Be Dropped

For unpartitioned tables or tables with per-row holds, deleting in **small batches** lowers lock duration and transaction size compared to a single multi-million-row delete.

PostgreSQL example on a simple sessions table:

~~~sql
CREATE TABLE sessions (
    session_id BIGINT PRIMARY KEY,
    expires_at TIMESTAMPTZ NOT NULL,
    legal_hold BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_sessions_expiration
    ON sessions (expires_at, session_id);

-- One batch, run inside a rate-limited, policy-approved workflow.
-- :cutoff is supplied from a valid retention decision.
WITH batch AS (
    SELECT session_id
    FROM sessions
    WHERE expires_at < :cutoff
      AND legal_hold = FALSE
    ORDER BY expires_at, session_id
    LIMIT 500
    FOR UPDATE SKIP LOCKED
)
DELETE FROM sessions AS s
USING batch AS b
WHERE s.session_id = b.session_id
RETURNING s.session_id;
~~~

This is a **technical query pattern**, not a complete deletion policy:

- `:cutoff` is an **application bind parameter**, not standalone SQL literal syntax runnable directly in every SQL console.
- `legal_hold` is simplified for illustration. Real systems may track multiple hold types, retention reasons, and cross-table hold rules.
- Before executing, ensure concurrent transactions cannot invalidate eligibility mid-flight, handle foreign keys, and enforce approval controls.
- `SKIP LOCKED` lets parallel workers progress without replacing idempotency, reconciliation, and error handling.
- High-volume `DELETE`s under MVCC generate substantial dead tuples and WAL; monitor vacuum throughput and replication lag.

Throttle purge speed according to **write load, query latency, replica lag, WAL, I/O**, and post-delete cleanup capacity. The goal is steadily draining backlog without disrupting operations.

## 10. Long-Term Archiving: Must Remain Accurately Restorable

Archiving is not just "moving files somewhere cheap". A long-term archive package must cover:

- **Content:** data, schema version, encoding, time units, tenant identifiers, and scope boundaries.
- **Integrity:** manifest, record/object counts, checksums, and corruption/missing-chunk detection.
- **Readability:** decompression/decryption tools, mapping from legacy schemas to current schemas, and restore testing.
- **Access control:** authorized readers, approval gates, access auditing, and encryption key management.
- **Retention:** expiration date, legal holds, immutability locks where needed, and post-expiration disposition.
- **Cost:** storage, retrieval request fees, restore charges, retrieval latency, and egress transfer.

### Choosing the Right Storage Format

| Storage Format | Strengths | What to Verify |
|---|---|---|
| Hot/warm DB tables | Direct SQL queries, transactions, and joins | Storage/index cost, vacuum load, backup time |
| Compressed files in object storage | Cost-effective for infrequent access | Manifests, checksums, object versions, read permissions |
| Columnar format (e.g., Parquet) | Efficient for columnar analytics and batch scans | Schema evolution, partition metadata, point lookups by key |
| Immutable / WORM archive | Enforces no-edit/no-delete during retention term | Not built for ad-hoc early deletion; legal hold mechanics |
| Dedicated historical store | Optimized for time/reconciliation queries | Cost and consistency relative to primary source |

A dataset may require both **transaction-grain records for reconciliation** and **aggregated analytical tables**. These carry different purposes and retention terms; never mistake derived summaries for the source of truth.

### Restore Testing Cannot Be Skipped

For example, a January 2027 archive package must be tested: read files, verify checksums, reconstruct schema, query a specific order, reconcile total counts, and verify decryption using actively managed keys. **An untested backup** or unreadable archive is not proof of recoverability.

As schemas evolve, retain **data dictionaries, migration mappings, encodings, timezones**, and application version metadata long enough to interpret historical archives accurately.

## 11. Deleting Across Replicas and Derived Systems

One record may exist in many places:

~~~text
Application
   |
   +-- Primary database
   +-- Read replica
   +-- Backup / snapshot
   +-- CDC stream / message queue
   +-- Search index
   +-- Cache / CDN
   +-- Warehouse / data lake
   +-- Object storage / file version
   +-- Logs, monitoring, exports
~~~

When policy requires deleting a subject's data, maintain a **data inventory and lineage** to locate every derived copy. Deleting from the primary database alone does not prove derived stores were handled.

### Differences Among Primary, Replicas, and Backups

- **Replicas** receive changes asynchronously or synchronously from primary; watch **replication lag** and failed delete applications.
- **Backups/snapshots** capture a point in time before deletion. Immutable snapshots cannot surgically edit individual rows; establish **backup expiration windows**, access restrictions, and **replay of deletion logs upon restore** where appropriate.
- **CDC/queues** hold historical events and payloads. Define stream retention, replay policies, and guards against resurrecting deleted records.
- **Caches/search** need invalidation or reindexing. Update lag can leave deleted items searchable after primary purge.
- **Object versioning** keeps older versions under the same key; lifecycle rules must purge noncurrent versions if true deletion is required.

In systems subject to personal data protection rules, review backup retention windows, exceptions, and deletion workflows against applicable obligations. **Never promise "instant deletion from all backups"** if architecture cannot deliver it; conversely, never assume backups are exempt from every rule without basis.

### Deletion Proof Records

A deletion job record may store:

~~~text
deletion_job_id
subject_ref_or_token
policy_version
requested_at
validated_at
source_purged_at
derived_systems_status
backup_expiry_or_restore_controls
completed_at
error_code
~~~

Store **minimal reference tokens** instead of copying names, emails, addresses, or sensitive payloads into deletion audit logs. Deletion logs themselves must carry a **dedicated retention policy for deletion proof**.

## 12. Modeling Storage Growth Over Time

System footprint is never simply:

~~~text
row count × declared column size
~~~

A physical estimate must account for:

- **New events/records over time** and traffic growth.
- **Actual average size** per row including encoding, row overhead, alignment, compression, or out-of-line storage.
- **Indexes:** index count, key width, selectivity, bloat, and fill factor.
- **Dead tuples / free space** from MVCC, updates/deletes, autovacuum, or equivalent housekeeping.
- **Replicas:** replication factor, multi-region copies, lag, and read replicas.
- **Backups/snapshots**, WAL/binlogs, CDC, checkpoints, and object versioning.
- **Archives** and separate data warehouses with distinct retention schedules.
- **Operational headroom** for reindexing, restores, compaction, migrations, and traffic spikes.

### Simple Formula for Bounded-Lifecycle Data

For an event stream with steady write rate \(\lambda\) (records/day), hot retention duration \(T\) (days), and average physical cost \(s\) (bytes/record, including allocated index share):

\[
N_{\text{hot}}\approx\lambda T
\]

\[
S_{\text{hot}}\approx\lambda T s.
\]

If \(\lambda\) grows over time, sum daily rates instead:

\[
N_{\text{hot}}(d)
\approx\sum_{k=d-T+1}^{d}\lambda(k).
\]

For **never-deleted** data at steady daily volume, storage grows roughly linearly over time. With consistently enforced retention, hot storage approaches a steady plateau **only if write rate and record size stop growing**. If traffic continues rising, hot storage still grows even with fixed \(T\).

### Storage Calculation Example

Assume a system has:

- \(3,000,000\) events/day.
- Each event consumes an average of **800 bytes in the hot store**, including measured index and physical overhead.
- Hot retention policy of **90 days**.
- **3 full replicas** of hot data (including primary).
- Storage headroom of **30% on top of replica requirements**.

Then:

~~~text
New data/day:
3,000,000 × 800 bytes = 2,400,000,000 bytes ≈ 2.4 GB/day

Hot data over 90 days:
2.4 × 90 = 216 GB

Total across three replicas:
216 × 3 = 648 GB

Including 30% headroom:
648 × 1.30 = 842.4 GB
~~~

These are **decimal GB** (\(1\text{ GB}=10^9\) bytes) and an **estimate only**. The **842.4 GB** figure excludes standalone backups, WAL/CDC, archives, caches, object storage, filesystem overhead, or traffic growth over the 90 days. Never treat it as final provisioning without empirical benchmarks.

### Sensitivity Analysis of the Design

| Illustrative Scenario | Changed Assumption | Single-Replica Hot Footprint |
|---|---|---:|
| Baseline | 3M rows/day, 800 B, 90-day retention | 216 GB |
| Longer retention | 3M rows/day, 800 B, 180-day retention | 432 GB |
| Doubled traffic | 6M rows/day, 800 B, 90-day retention | 432 GB |
| Larger records | 3M rows/day, 1,200 B, 90-day retention | 324 GB |
| Combined stress | 6M rows/day, 1,200 B, 180-day retention | 1,296 GB |

This table covers **one hot replica only**, before multiplying replicas or adding backups. It demonstrates how **retention, traffic, and record size** multiply together strongly. In practice, measure hourly/daily to capture **seasonality, bursts, late arrivals, and update churn**.

## 13. Limits of Capacity Forecasting

### Average Row Size Shifts Over Time

A `JSONB` or `TEXT` record grows significantly as fields, Unicode, metadata, or attachments are added. `VARCHAR(255)` defines a logical limit, **not a fixed 255 bytes per row**. Physical size depends on DBMS, encoding, compression, page overhead, and TOAST/LOB storage.

For accurate forecasts, measure sizes on **representative data** and track size percentiles, not just an average over a tiny sample.

### Old Data Does Not Disappear Instantly

- `DELETE` changes logical visibility while leaving space awaiting reclamation.
- LSM-tree stores require **compaction** to purge old versions and tombstones.
- Expired partitions may remain pinned by **legal holds**, unverified archives, or incomplete detach/drop jobs.
- Replication lag and CDC backlogs create temporary growth.
- Object versioning or backups retain older content for an extra window.

Good capacity models include **headroom for disposal lag**, rather than assuming purges execute instantaneously on schedule.

### Hot Storage and Archives Must Be Forecasted Separately

When keeping 90 days hot and 2 years archived, model two stores separately:

~~~text
Hot:     traffic × 90 days × hot size
Archive: traffic × archive period × compressed size
~~~

Then calculate replicas/backups separately for **each tier**, since replication factor, compression, indexing, and retrieval costs differ. Never blindly apply one replica multiplier across all tiers.

## 14. Measure Reality Instead of Guessing from DDL

In PostgreSQL, example size inspection for an **unpartitioned table** including indexes and auxiliary storage:

~~~sql
SELECT
    pg_size_pretty(pg_relation_size('customer_profiles')) AS main_heap,
    pg_size_pretty(pg_table_size('customer_profiles')) AS table_storage,
    pg_size_pretty(pg_indexes_size('customer_profiles')) AS indexes,
    pg_size_pretty(pg_total_relation_size('customer_profiles')) AS total;
~~~

These functions inspect the **named relation**, yet a partitioned parent table's size does not automatically sum all child partitions in all cases. To measure **the entire partition tree**, sum leaf partitions or query catalog functions appropriate to your PostgreSQL version.

Track operational metrics as well:

~~~text
daily_inserted_rows
daily_updated_rows
daily_deleted_rows
live_rows_estimate
dead_tuples_estimate
retention_backlog_rows
oldest_unpurged_at
partition_count
hot_storage_bytes
archive_storage_bytes
index_bytes
replica_lag
backup_bytes_and_age
restore_test_passed_at
~~~

Not every counter is **exact real-time truth**: DBMS stats may be sampled estimates, lagged, or partial. Infrastructure billing storage also includes replicas, snapshots, WAL, buffers, and auxiliary services.

### Operational Alerts Should Trigger Concrete Actions

For example:

- `oldest_unpurged_at` breaches SLA: inspect purge jobs, legal holds, archive blockers, and data errors.
- `retention_backlog_rows` climbs over multiple days: tune purge throughput or revisit partitioning strategy.
- Index footprint outpaces table growth: check query patterns, bloat, and redundant indexes.
- Replica lag spikes during purges: reduce batch size/rate and inspect I/O.
- Archive package fails restore test: **halt source deletion** until archiving is fixed.

Set thresholds per system rather than applying one universal number to all workloads.

## 15. Safe Policy Rollout Procedure

A runbook should proceed in clear stages:

### Step 1 — Classify and Map Data

Identify all related tables, objects, logs, search indexes, caches, warehouses, CDC streams, and backups. Trace which derived datasets originate from which tables; if lineage is unknown, never assume deletion is complete.

### Step 2 — Finalize Rules and Exceptions

Confirm retention triggers, durations, end-of-term actions, legal/compliance rules, legal holds, approvers, and policy versions. Never let a scheduler infer legal retention from table names alone.

### Step 3 — Pick Execution Mechanics per Data Category

- High-volume time-expiring events: consider **partition + archive + drop** after verification.
- Data with row-level exceptions: **batch purge** with exact filters.
- Data needing instant hiding with grace recovery: **soft delete + purge workflow**.
- Rarely accessed data still under retention: **archive** with tested permissions and restores.
- Derived data: **rebuild, invalidate, remove, or transform** per corresponding rules.

### Step 4 — Dry-Run Safely

On representative test data, verify **records that must NOT be deleted**: active holds, open orders, disputed transactions, linked records, other tenants, late arrivals, and pending restore requests.

Before production execution, generate a **dry-run report**: eligible row counts, estimated freed bytes, dependent tables, and projected impact. Compare against normal baselines to catch bad parameters.

### Step 5 — Execute Under Guardrails

Enforce least-privilege permissions, bounded transactions, batch sizes, rate limits, idempotency, pause/resume controls, and live monitoring. For archives, **never destroy source data before sample restores and integrity checks pass**.

### Step 6 — Reconcile and Record Proof

Verify processed row counts, checksums where applicable, source–archive discrepancies, lagging derived stores, and replica/backup status. Keep auditable logs **without re-exposing sensitive payloads**.

### Step 7 — Drill Restores and Govern Changes

Run periodic restore drills, including **reapplying deletion logs** or equivalent controls after restoring older backups.

## 16. Common Mistakes

| Mistake | Why It Is Risky | Fix |
|---|---|---|
| "Setting `deleted_at` means deleted." | Data remains in tables, indexes, and backups | Build **real purge workflows** and reconciliation |
| Using `ON DELETE CASCADE` everywhere | Can wipe required financial vouchers and history | Choose FK behavior per **each entity's lifecycle** |
| Keeping everything forever "just in case" | Inflates costs, breach exposure, and compliance risk | Define purpose, durations, and exceptions |
| Dropping a whole partition 90 days after `occurred_at` | May contain held records or alternate triggers | Check policy **across the whole partition** |
| Moving files to object storage and dropping primary immediately | Archive might be unreadable or corrupt | Verify manifest, checksum, and **restore test** before dropping |
| Assuming `DELETE` shrinks disk usage immediately | MVCC/compaction reclaims space asynchronously | Monitor bloat, vacuum/compaction, and physical sizes |
| Deleting primary only; forgetting search, cache, CDC, replicas | Records stay searchable or resurrect | Maintain data lineage and cross-system deletion workflows |
| Claiming backups are deleted while immutable snapshots remain | Misstates actual deletion status | Separate primary status, backup status, and backup expiration |
| Forecasting solely via row count × `VARCHAR(n)` | Misses variable lengths, indexes, replicas, backups | Measure actual sizes and model every tier |
| Treating TTL as an instant deletion SLA | Some TTL engines run asynchronously or during compaction | Define **acceptable deletion lag** and monitor |
| Managing retention on tables while ignoring files/images | Objects and object versions persist indefinitely | Apply lifecycle policies to every storage layer |
| Logging full emails/addresses in deletion job logs | Deletion logs create new copies of deleted data | Store minimal proof tokens or job IDs |

## 17. Comparison Across Storage Models

| Model | Lifecycle Approach | Characteristic Risks |
|---|---|---|
| **Relational** | Per-table/row/partition retention; FKs, archives, and batch purges | Cascading wipes, long locks, MVCC bloat, broken links |
| **Document** | Document TTL where suitable, per-collection policies, object lifecycle | TTL lag; embedded subdocuments mixing lifecycles |
| **Graph** | Business-driven node/edge deletion or anonymization; orphan checks | Deleting a node touches many edges; leftover edges risk re-identification |
| **Analytical / data lake** | Date partitioning, file/object lifecycles, rebuilding derived tables | File snapshots/versions, time-travel queries vs. purged source records |

**Never assume one mechanism works identically across all engines.** Some document stores run TTL sweeps asynchronously; some object stores lock versions or retention; graph engines delete edges differently; data lakes keep snapshots needing separate vacuuming. Always verify exact features, limits, and deletion mechanics of the **actual deployed version**.

## 18. Practice Exercises with Solutions

### Exercise 1 — Does Soft Delete Satisfy Purge Requirements?

A system adds `deleted_at` to `CUSTOMERS` and always filters `WHERE deleted_at IS NULL`. Users are told "permanently deleted".

**Solution:** The statement is inaccurate. Data remains in the table and may persist in replicas, backups, or search. Separate **hidden in app** from **hard-purged across primary and copies**; implement a purge workflow per approved policy.

### Exercise 2 — Deleting a Customer with Order History

`ORDERS.customer_id` references `CUSTOMERS`. A customer requests profile deletion while orders must be retained under confirmed obligations. Should `ON DELETE CASCADE` be enabled?

**Solution:** No. Cascading would destroy orders that must be kept. Define how order vouchers are retained, restrict or decouple identity links where valid, handle personal fields inside orders, and configure FKs accordingly. A profile deletion request does not authorize destroying all transaction records.

### Exercise 3 — Estimating Hot Storage

A system logs 1 million events/day, each averaging 1,000 bytes (including allocated index overhead), kept hot for 60 days. Estimate **one hot replica** footprint before headroom.

**Solution:** \(1,000,000\times 1,000\times 60=60,000,000,000\) bytes, or **60 decimal GB**. This excludes backups, logs, replicas, and additional overhead.

### Exercise 4 — Effect of Doubling Traffic

Continuing Exercise 3, if traffic doubles to 2 million events/day with unchanged retention and record size, what happens to steady-state single-replica size?

**Solution:** It roughly **doubles** to **120 GB**. If traffic climbs gradually or bursts, sum daily volumes to estimate capacity at specific dates.

### Exercise 5 — Can an Old Partition Be Dropped?

A January partition holds millions of expired logs alongside 20 events under legal hold. Should the whole partition be dropped to save space?

**Solution:** No—not without a valid mechanism preserving all 20 held events and proving the rest may be deleted. Move/preserve held events to an appropriate store or purge selectively. Verify archive completeness before destroying the source.

### Exercise 6 — `DELETE` Ran, Yet DB Files Did Not Shrink

Ten million rows were deleted from PostgreSQL; file sizes barely changed. Does this prove the delete failed?

**Solution:** No. MVCC leaves internal space awaiting reclamation/reuse; standard `VACUUM` rarely returns files to the OS. Inspect visible row counts, dead-tuple stats, vacuum runs, and partition/index sizes before concluding.

### Exercise 7 — Archive Has a Checksum, Never Restored

The system wrote a compressed archive file, recorded its checksum, and plans to drop the source table. Is it safe enough?

**Solution:** Not yet. Verify **actual reading and restoration**, schema/encoding, decryption keys, queryability, and completeness across the intended range. Checksums verify only bit integrity.

### Exercise 8 — Deleting in a Replicated System

A profile is deleted from primary yet stays visible in search for minutes and inside backups for 30 days. Can the system announce "deleted from all systems immediately"?

**Solution:** No. Accurately state search/replica propagation lag, backup expiration windows, and restore/replay controls preventing unintentional resurrection. Policies must align with obligations and real architecture.

### Exercise 9 — Ambiguous Retention Trigger

Policy says "delete orders after 24 months", yet orders are created before payment and may be refunded months later. What should the design team do?

**Solution:** Finalize the exact clock trigger (creation, settlement, delivery, expiration, or refund completion), exceptions, and dispute states. Confirm the rule with data owners; never pick `created_at` merely because that column already exists.

## 19. Pre-Production Operational Checklist

- [ ] Classified data by **purpose, sensitivity, grain, and lifecycle**.
- [ ] Every dataset has an explicit **retention trigger**, duration, end-of-term action, and owner.
- [ ] Confirmed policies with business/legal/compliance where needed instead of inventing arbitrary numbers.
- [ ] Handled **legal holds**, disputed records, and records with multiple retention obligations.
- [ ] Distinguished **soft delete**, hard purge, archiving, and anonymization.
- [ ] Reviewed foreign keys, `CASCADE`, unique constraints, and read paths for deleted rows.
- [ ] Selected suitable purge mechanics: row-by-row, batched, partitioned, or monitored TTL.
- [ ] Archives include manifests, checksums, schemas, decryption access, and **restore tests**.
- [ ] Mapped primary, replicas, backups, CDC, caches, search, files, and warehouses.
- [ ] Established controls preventing purged data from **reappearing after restores or replays**.
- [ ] Forecasted capacity from record counts, real sizes, retention, replicas, backups, and headroom.
- [ ] Monitored **retention backlog, oldest unpurged record, index size, replica lag, and restore status**.
- [ ] Built dry runs, approvals, rate limiting, reconciliation, and error handling for purges.
- [ ] Tested edge cases: cross-tenant boundaries, late arrivals, child tables requiring retention, legal holds, and object versioning.

**Remember:** A sound physical model does not merely store today's data efficiently—it defines **when to stop keeping data and how to prove safe disposal**. Design retention around business rules and applicable obligations; pick partitioning, batch purges, archiving, and backups from actual workloads; forecast storage from real measurements. **Soft delete is not hard delete, purging primary is not purging every copy, and an archive that cannot be restored is not a trustworthy retention strategy.**
