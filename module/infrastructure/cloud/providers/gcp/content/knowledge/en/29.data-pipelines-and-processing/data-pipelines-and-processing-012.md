# Datastream and Change Data Capture from Databases on Google Cloud

> **Chapter:** Data Pipelines and Processing  
> **Module:** **CLOUD_PROVIDERS_GCP** — Explore Google Cloud from project organization, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage services, and databases. Through real deployment scenarios, learners select services, protect resources, automate releases, and monitor reliability alongside cost.

A Java system on Cloud Run writes orders to PostgreSQL while the analytics team wants near-real-time metrics in BigQuery. Running a **full-table `SELECT` every minute** increases database load, repeatedly transfers unchanged data, and struggles to detect updated or deleted rows. **Change Data Capture (CDC)** replaces that approach by reading the **stream of changes from the database transaction log** and delivering those changes to analytics or downstream processing pipelines.

**Datastream** is Google Cloud's serverless CDC and replication service. Datastream can capture historical data (**backfill**), continue reading subsequent `INSERT`/`UPDATE`/`DELETE` operations, and replicate them to **BigQuery**, **Cloud Storage**, or supported Apache Iceberg destinations. This lesson focuses on **Cloud SQL for PostgreSQL → Datastream → BigQuery**, then extends to CDC files in Cloud Storage and Dataflow.

**Safety boundary:** creating a stream, enabling logical replication, opening connections, or backfilling a real database can increase I/O, retain WAL, and incur charges. Practice only on a lab database/table you own with owner and change approval; never alter flags, publications, slots, or delete production resources just to follow this lesson.

## Learning Objectives

1. Distinguish **transaction-log CDC**, batch snapshots, streaming events, and event sourcing.
2. Explain **connection profile, stream, stream object, event, initial backfill, continuous CDC**, checkpoints, and replication lag.
3. Prepare a PostgreSQL source: logical decoding, publication, replication slot, user, and least-privilege read access.
4. Design source connectivity via public allowlist or private connectivity, and manage the Datastream identity.
5. Configure a stream to BigQuery with **Merge/Append-only**, schema mapping, and data staleness.
6. Verify `INSERT`/`UPDATE`/`DELETE`, metadata, and the difference between current state and change history.
7. Analyze risks around **at-least-once delivery, out-of-order delivery, schema evolution, primary keys, WAL retention**, and recovery.
8. Monitor data freshness, system/total latency, errors, source pressure, quotas, and cost; complete exercises with answers.

## 1. Why Does CDC Differ from Batch ETL?

~~~mermaid
flowchart LR
    APP["Cloud Run Java app"] --> SQL[("Cloud SQL PostgreSQL\norders")]
    SQL --> WAL["Transaction log: WAL"]
    WAL --> DS["Datastream\nsource profile + stream"]
    DS --> BQ["BigQuery\nMerge / Append-only"]
    DS -. "Another stream if needed" .-> GCS["Cloud Storage\nAvro / JSON"]
    GCS --> DF["Dataflow / Spark\ncustom transforms"]
    DF --> DW["Destination / curated tables"]
    BQ --> BI["BI / BigQuery ML / analytics"]
~~~

| Approach | Data source | Best suited for | Typical risks |
|---|---|---|---|
| **Batch full extract** | Periodic full-table `SELECT` | Small tables, hourly/daily latency | High scan cost, misses `DELETE`s, repeated reads |
| **Batch incremental** | `WHERE updated_at > watermark` | Tables with reliable watermarks | Clock skew, late commits, misses hard deletes |
| **Log-based CDC** | WAL/binlog/redo log | Near real time; captures `INSERT`/`UPDATE`/`DELETE` | Log retention, replication privileges, schema drift |
| **Application events** | Events emitted by the service | Business events with clear semantics | Without an outbox, DB and events can diverge |
| **Event sourcing** | Event store as source of truth | Domain-event auditing/replay | Not automatically gained by reading CDC |

**CDC does not equal event sourcing.** A table change `status=PAID` shows the database changed state, without necessarily carrying full business context, user identity, or payment reason. When reliable business events are needed, use a **transactional outbox** in the same transaction as business data and CDC the outbox table, or use a dedicated event architecture.

### 1.1. What Steps Does a Record Flow Through?

~~~mermaid
sequenceDiagram
    participant A as Orders API
    participant P as PostgreSQL
    participant W as WAL / replication slot
    participant D as Datastream
    participant B as BigQuery
    A->>P: BEGIN; UPDATE orders; COMMIT
    P->>W: Write WAL on commit
    D->>W: Read logical changes
    W-->>D: Row change + source metadata
    D->>B: Send CDC event
    B-->>D: Ingest/apply change
    Note over D,B: At-least-once with no guaranteed event order
    Note over P,B: Near real time, not a 0 ms SLA
~~~

Datastream **does not modify PostgreSQL transactions** and does not wrap BigQuery in a distributed transaction with the source. **Replication lag** can exist at any point; a BigQuery query may not yet reflect the latest commit.

## 2. Five Datastream Objects to Distinguish

| Object | Meaning | Example |
|---|---|---|
| **Private connectivity configuration** | Private network path from Datastream to the source, configured when needed | `ds-private-vpc` |
| **Connection profile** | Credentials, host, port, and source/destination type | `orders-pg-source`, `analytics-bq-dest` |
| **Stream** | Links source + destination profiles, object filters, backfill, and write settings | `orders-cdc-lab` |
| **Stream object** | A single replicated table/collection in a stream | `public.orders_cdc_lab` |
| **Event** | A single row change or backfill record | `UPDATE order 1001` |

**Backfill** reads existing historical table state; **CDC** reads ongoing changes. Datastream can run backfill and CDC concurrently depending on configuration, yet **event arrival order at the destination is not guaranteed** and **duplicates can occur**. Metadata supports reordering or deduplication where needed; **never use Cloud Storage file arrival time as business event order**.

### 2.1. Key States and Definitions

- **`RUNNING`:** Datastream is actively replicating the stream.
- **`PAUSED`:** stream is paused; it passes through **`DRAINING`** beforehand to flush in-flight work.
- **`FAILED`/`ERROR`:** inspect stream details, connectivity errors, source logs, and destination permissions.
- **Backfill completed:** historical snapshot copy finished; **does not** prove current CDC lag is zero.
- **Source position:** for PostgreSQL, the WAL read position/progress—not simply an application timestamp.
- **Destination write/merge lag:** the destination may have ingested events without yet applying them to final queryable state.

A **PostgreSQL logical replication slot** is bound to **one database and one consumer stream**, so each CDC stream needs its own slot; never share one slot across two streams.

## 3. Supported Sources and Destinations: Choose by Workload

| Typical source | Core CDC mechanism | Key considerations |
|---|---|---|
| **PostgreSQL / Cloud SQL / AlloyDB** | Logical decoding of **WAL** via publication + slot | Check version, privileges, replica identity, WAL retention |
| **MySQL / Cloud SQL MySQL** | Binary log or GTID per supported method | Binlog retention, `ROW` events, InnoDB, failovers |
| **Oracle** | Redo logs / LogMiner with supplemental logging | Log read privileges, LOB/DDL limits, licensing/cost |
| **SQL Server** | CDC change tables or transaction log method | CDC jobs, log truncation safeguards, version limits |
| **MongoDB** | Change streams and snapshots per support | Sharding, change stream permissions, type mapping |
| **Spanner** | Change stream mechanism per supported source | Features and setup differ from traditional RDBMS |

Datastream also supports several SaaS sources; Preview status, versions, and regional availability can change. Check **[Sources](https://docs.cloud.google.com/datastream/docs/sources)** before designing a solution rather than assuming every engine, edition, or column type is supported.

| Destination | Output | When to choose? |
|---|---|---|
| **BigQuery** | Tables with current state or change history | Near-real-time dashboards and analytics |
| **Cloud Storage** | Avro/JSON event files and metadata | Auditing, data lakes, custom downstream pipelines |
| **Apache Iceberg tables** | Managed Iceberg target per support conditions | Lakehouses and compatible query engines |
| **Cloud SQL / Spanner via Dataflow** | **Datastream → Cloud Storage → Dataflow** integration path | Custom replication/transforms; **not a default direct native destination** |

### 3.1. BigQuery Merge vs. Append-Only

| Mode | Result | Example: `INSERT → UPDATE → DELETE` |
|---|---|---|
| **Merge** | Table reflects current source row state; requires a **primary key** | After applying `DELETE`, the row is gone |
| **Append-only** | Stores a sequence of change events without automatically collapsing to current state | Retains `INSERT`, `UPDATE-INSERT`, `DELETE` events |
| **No primary key** | Datastream writes append-only even when the stream selects Merge | Cannot assume destination count equals source count |

With **Merge**, BigQuery uses CDC ingestion via the **Storage Write API** to consolidate changes. With **Append-only**, metadata includes fields like **`CHANGE_TYPE`** and **`CHANGE_SEQUENCE_NUMBER`**. Never interpret an append-only table as a one-row-per-entity snapshot. On PostgreSQL sources, **large LOB/TOAST values** may require supplemental lookups, and rapid `UPDATE`/`DELETE` bursts may not capture every intermediate state. Verify replay/audit requirements before promising "every intermediate state".

### 3.2. Event Size Limits

Per Datastream behavior documentation, individual event size is capped at **20 MB for BigQuery** and **100 MB for Cloud Storage**. This is **not** a promise that every LOB replicates cleanly; each source and data type has specific limits. Payloads exceeding limits require an alternate pattern—such as storing large objects in object storage and replicating metadata via CDC.

## 4. Lab A — Preparing a PostgreSQL Source for Synthetic Data Only

**Context:** a Java Orders API writes to **Cloud SQL for PostgreSQL**; we replicate only **`public.orders_cdc_lab`** in database **`orders_lab`** to BigQuery. If you lack permissions to create databases/tables or enable logical decoding, complete the SQL analysis and design sections **without** touching a live database.

### 4.1. Read-Only Preflight on the Lab Project

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
REGION="asia-southeast1"
PG_INSTANCE="YOUR_CLOUD_SQL_POSTGRES_INSTANCE"
STREAM_ID="orders-cdc-lab"
BQ_DATASET="cdc_orders_lab"

gcloud auth list
gcloud config list project
gcloud sql instances describe "$PG_INSTANCE" \
  --project="$PROJECT_ID" \
  --format="yaml(name,state,region,databaseVersion,connectionName,ipAddresses,settings.databaseFlags)"
gcloud datastream streams list \
  --project="$PROJECT_ID" --location="$REGION"
gcloud datastream connection-profiles list \
  --project="$PROJECT_ID" --location="$REGION"
~~~

**Read-only** commands first confirm the exact project and instance. Database **`orders_lab`** must exist with an owner-authorized PostgreSQL user able to create tables and define publications/slots within lab scope. Never enable public networking or change production flags outside an approved change window.

### 4.2. Creating a Test Table with a Primary Key

Run inside **`orders_lab`** using an authorized schema/table-owner role. The SQL below **creates and modifies real data**; never run it on a shared database without permission.

~~~sql
-- MUTATES LAB DATABASE.
CREATE TABLE public.orders_cdc_lab (
    order_id BIGINT PRIMARY KEY,
    status VARCHAR(20) NOT NULL
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    total_vnd NUMERIC(12, 2) NOT NULL
        CHECK (total_vnd >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO public.orders_cdc_lab
    (order_id, status, total_vnd)
VALUES
    (1001, 'NEW', 150000.00),
    (1002, 'NEW', 250000.00),
    (1003, 'PAID', 79000.00);
~~~

**Note:** if the table already exists, **do not blindly run `CREATE TABLE`/`INSERT`**; pick another table or stop to avoid conflicts. **`PRIMARY KEY(order_id)`** lets Datastream use BigQuery **Merge** with "one current row per key" semantics once events apply. If the PK is dropped or altered while a stream runs, evaluate re-backfilling the table and data-corruption risks.

### 4.3. Enabling Logical Decoding on Cloud SQL

Cloud SQL for PostgreSQL uses the database flag **`cloudsql.logical_decoding=on`**. Changing this flag **requires an instance restart**, which can interrupt active connections.

**Steps in Google Cloud Console (only with owner approval):**

1. **Cloud SQL → Instances → select lab instance → Edit**.
2. Under **Flags**, set **`cloudsql.logical_decoding = on`**.
3. Review impact on connections, replication slots, WAL, and restart downtime.
4. Save and restart within a maintenance window.
5. Verify the database actually runs in logical mode rather than trusting the config screen alone.

~~~sql
-- READ-ONLY in PostgreSQL.
SHOW wal_level;
SHOW max_replication_slots;
SHOW max_wal_senders;

-- Inspect existing slots and their status.
SELECT
    slot_name,
    plugin,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_name;
~~~

**For self-managed PostgreSQL**, logical replication is enabled via **`wal_level=logical`**, adjusting **`max_replication_slots`/`max_wal_senders`** and restarting per server setup; never apply Cloud SQL flags to self-managed PostgreSQL. Other engines like AlloyDB or RDS have their own procedures.

### 4.4. Publication and Replication Slot

In database **`orders_lab`**, an authorized admin creates a **publication scoped strictly to the lab table** and a **logical replication slot** using the **`pgoutput`** plugin:

~~~sql
-- MUTATES DATABASE / WAL — lab DBA only.
CREATE PUBLICATION ds_orders_lab_pub
FOR TABLE public.orders_cdc_lab;

SELECT pg_create_logical_replication_slot(
    'ds_orders_lab_slot', 'pgoutput'
);
~~~

**Remember:**

- **Publication** defines which tables and changes are exposed; publish only required tables and avoid uncontrolled **`FOR ALL TABLES`**.
- **Slot** tracks consumed WAL progress. When a slot exists without an active consumer reading it, PostgreSQL can **retain WAL indefinitely until disk or quota fills**, endangering production. Never create a real slot and abandon it.
- **One slot** serves **one stream**; slot names must be unique and match the name entered in the Datastream source configuration.
- If multiple streams read the same database, create separate publications/slots as appropriate and measure added source load. Never point two consumers at the same slot.
- For tables receiving `UPDATE`/`DELETE`, **replica identity / primary key** determines key columns emitted; our demo table has a PK, so it is ready.

### 4.5. Dedicated Datastream Account and Least Privilege

Run as an authorized database admin role:

~~~sql
-- MUTATES USER: never put literal passwords in source or SQL history.
CREATE ROLE ds_orders_reader LOGIN REPLICATION;
GRANT CONNECT ON DATABASE orders_lab TO ds_orders_reader;
GRANT USAGE ON SCHEMA public TO ds_orders_reader;
GRANT SELECT ON TABLE public.orders_cdc_lab TO ds_orders_reader;
~~~

Then **inside `psql`**, run the interactive command below to set a strong password and store it in an approved secret manager:

~~~text
\password ds_orders_reader
~~~

For future tables, the table owner can configure **`ALTER DEFAULT PRIVILEGES ... GRANT SELECT`**; PostgreSQL default privileges apply per **object-creating role**, not automatically across every owner in the database. Never grant `SELECT` across all sensitive tables just to stream one test table.

### 4.6. Checking the WAL Slot Whenever the Stream Is Idle

~~~sql
-- READ-ONLY; run with an account permitted to read replication stats.
SELECT
    slot_name,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    pg_size_pretty(
      pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)
    ) AS approx_wal_retained
FROM pg_replication_slots
WHERE slot_name = 'ds_orders_lab_slot';
~~~

**Do not treat this number as the exact physical bytes eligible for immediate deletion.** It flags WAL retention risk when a stream stalls. Before pausing for long periods, establish storage monitoring and an approved slot-handling plan; **never drop a replication slot actively used by a stream**.

## 5. Designing Connectivity, Accounts, and Data Locations

### 5.1. Two Ways to Connect to a Source Database

| Connectivity | Best for | Requirements |
|---|---|---|
| **Public network + IP allowlisting** | Labs where policy permits | Reachable DB address, firewall/allowlist for Datastream IPs, TLS/credentials |
| **Private connectivity** | Production with VPC / private IPs | Private connectivity config (VPC peering/PSC per supported options), valid routes/IP ranges/DNS/firewall |
| **SSH tunnel** | Self-managed sources or private networks with an approved bastion | Hardened host/keys, network path, and access reviews |

**Private connectivity does not work automatically just by selecting a private IP.** The network path from Datastream to the database must actually route; BigQuery is not a source network client in Datastream's direct-destination model. Cloud SQL has specific private connection options; see [private connectivity options](https://docs.cloud.google.com/datastream/docs/network-connectivity).

### 5.2. Connection Profiles and Secrets

- **PostgreSQL source profile:** host/IP, port (typically 5432), username/password, database, TLS/SSL, and network connectivity method.
- **BigQuery destination profile:** BigQuery destination project; no database password needed.
- **Stream:** connects source + destination profiles, publication/slot, table include/exclude filters, backfill, and write mode.
- **Datastream service agent:** Google Cloud–managed identity used on destinations; when the destination resides in **another project**, grant appropriate roles in that target project.
- **Operator IAM:** only authorized operators can create/update streams, connection profiles, and network configs. Deployment permission does not imply permission to read all source tables.

Never commit database passwords or connection secrets to Markdown, Git, or shell history. When rotating passwords, update the connection profile, verify the stream reconnects, and ensure the WAL/log retention window is not exceeded.

### 5.3. Data Residency, Reliability, and Compliance

- Place the **Datastream stream region** close to both the database and destination when possible to minimize latency and egress.
- BigQuery datasets have their own **location**; verify supported locations and residency policies.
- Separate **dev/staging/prod** cleanly via IAM and distinct projects/datasets.
- Classify sensitive data before replicating; CDC will copy PII columns automatically if filters are overly broad.
- Apply **data minimization** in source table/object filters; Datastream does not anonymize replicated data.

## 6. Lab B — Creating a PostgreSQL → BigQuery Stream in the Console

### 6.1. Preparing the Destination

Create a **dedicated BigQuery dataset** in the lab project, e.g., **`cdc_orders_lab`**. Choose a valid BigQuery location, owner, and retention policy. Ensure **Datastream API / BigQuery API** are enabled and the Datastream service agent holds required roles. The destination dataset must not hold an existing table with the same name you don't want overwritten.

~~~bash
# READ-ONLY check for enabled APIs and existing datasets.
gcloud services list --enabled --project="$PROJECT_ID" \
  --filter="NAME:(datastream.googleapis.com OR bigquery.googleapis.com)"

bq --project_id="$PROJECT_ID" ls

# MUTATING — create LAB dataset only if it does not already exist.
bq --project_id="$PROJECT_ID" --location="$REGION" mk \
  --dataset "$PROJECT_ID:$BQ_DATASET"
~~~

**Note:** `bq --location` must be a supported BigQuery dataset location; this example matches the stream region for convenience, though organizations must verify per-service support beforehand. Never store data bound to regional residency inside the `US` multi-region.

### 6.2. Setup Steps in the Datastream Console

1. **Datastream → Connection profiles → Create profile** for source **PostgreSQL**. Select the Datastream region, host/database/user/SSL, and prepared network connectivity; run **Test connection**.
2. Create a **BigQuery** destination profile in the target project and supported region.
3. **Datastream → Streams → Create stream**; enter stream name, stream ID, region, and source/destination profiles.
4. Select **Source objects**: **only database `orders_lab` → schema `public` → table `orders_cdc_lab`**. Review exclude filters and DDL limitations.
5. Enter publication **`ds_orders_lab_pub`** and replication slot **`ds_orders_lab_slot`** for the PostgreSQL source.
6. Choose **Backfill all objects** for the lab table to capture the three initial orders; without backfill, only CDC from the configured position is captured.
7. Set **BigQuery destination dataset = `cdc_orders_lab`** and **Single dataset for all schemas**. Datastream creates table **`public_orders_cdc_lab`** following the **`schema_table`** naming convention.
8. Select **Merge** (the table has a primary key) and set the **data staleness limit** per freshness/cost goals.
9. **Validate stream**: verify source, permissions, publication/slot, connectivity, and destination. Only once validation PASSES and is approved, click **Create & Start**.
10. Open **Streams → `orders-cdc-lab` → Monitoring / Objects** to track backfill and CDC status.

**Important:** UI control names and prerequisites can vary by source and edition; if the Console offers an automated Cloud SQL stream setup flow, still verify all permissions and source impacts. **Never assume backfill is complete immediately after clicking Create & Start.**

### 6.3. BigQuery Merge and Data Staleness

In **Merge** mode, BigQuery uses CDC ingestion and applies mutations per configuration. During backlogs or before background merges catch up, query results are affected by **`max_staleness`** and apply lag. **BigQuery staleness is distinct from Datastream data freshness**: one governs applying changes inside BigQuery, while the other measures Datastream's lag reading from the source.

In **Append-only** mode, data represents an event log rather than a self-updating current-state table. Choose the mode before downstream consumers depend on the schema; **never switch modes arbitrarily once downstream jobs rely on it**.

## 7. Lab C — Verifying `INSERT`, `UPDATE`, and `DELETE` in BigQuery

### 7.1. Wait for Initial Backfill to Finish

Open **Datastream → Streams → `orders-cdc-lab`** and confirm the stream is running and object **`public.orders_cdc_lab`** has completed initial backfill with no pending backfill remaining. Then open BigQuery Studio in the target project/dataset.

~~~sql
-- READ-ONLY BigQuery MERGE mode. Replace PROJECT_ID with your real lab project.
SELECT
  order_id,
  status,
  total_vnd,
  updated_at,
  datastream_metadata
FROM `PROJECT_ID.cdc_orders_lab.public_orders_cdc_lab`
ORDER BY order_id;
~~~

**Expected after backfill and CDC catch-up:** 3 rows with `order_id`s **1001, 1002, 1003**. If the target table is empty or missing rows, inspect stream objects, backfill status, and permissions first; never re-run `INSERT`s on the source to "force" Datastream to catch up.

### 7.2. Generating Changes on Source PostgreSQL

Only after confirming the BigQuery baseline, run inside **`orders_lab`**:

~~~sql
-- MUTATES LAB DATA.
BEGIN;
UPDATE public.orders_cdc_lab
SET status = 'PAID', updated_at = CURRENT_TIMESTAMP
WHERE order_id = 1001;

INSERT INTO public.orders_cdc_lab
    (order_id, status, total_vnd)
VALUES
    (1004, 'NEW', 329000.00);

DELETE FROM public.orders_cdc_lab
WHERE order_id = 1002;
COMMIT;
~~~

After committing, do not expect BigQuery to reflect changes **within the same instant**. Wait per monitoring freshness/total latency, then query **both PostgreSQL and BigQuery** and compare:

| `order_id` | Before | After CDC and Merge complete |
|---|---|---|
| **1001** | `NEW` | `PAID` |
| **1002** | `NEW` | **Deleted (absent)** |
| **1003** | `PAID` | `PAID` |
| **1004** | Absent | `NEW` |

The total row count remains **3** (1 inserted, 1 deleted). Never treat matching `COUNT(*)` alone as proof of accuracy: one missing row and one duplicate row can yield the exact same count.

### 7.3. Output Verification SQL

~~~sql
-- READ-ONLY BigQuery check after replication catch-up.
SELECT
  order_id,
  status,
  total_vnd,
  datastream_metadata.UUID AS event_uuid,
  datastream_metadata.SOURCE_TIMESTAMP AS source_ts_raw
FROM `PROJECT_ID.cdc_orders_lab.public_orders_cdc_lab`
ORDER BY order_id;

-- Verify exact expected state, not just row count.
WITH state AS (
  SELECT order_id, status
  FROM `PROJECT_ID.cdc_orders_lab.public_orders_cdc_lab`
)
SELECT
  (SELECT COUNT(*) FROM state) AS actual_rows,
  (SELECT COUNT(*) FROM state
   WHERE order_id = 1001 AND status = 'PAID') AS updated_ok,
  (SELECT COUNT(*) FROM state
   WHERE order_id = 1002) AS deleted_remaining,
  (SELECT COUNT(*) FROM state
   WHERE order_id = 1004 AND status = 'NEW') AS inserted_ok;
~~~

**Expected after catch-up:** **`actual_rows=3`**, **`updated_ok=1`**, **`deleted_remaining=0`**, **`inserted_ok=1`**. With Merge and a PK table, Datastream metadata typically includes **`UUID`** and **`SOURCE_TIMESTAMP`**; do not treat these as full historical audit logs, because Merge consolidates events.

### 7.4. If Using Append-Only Instead of Merge

**Do not run Section 7.3 SQL expecting Append-only output to look identical.** In Append-only mode, each event is stored as a row, including `UPDATE`/`DELETE` actions and metadata:

~~~sql
-- READ-ONLY; applies when the table comes from an Append-only stream.
SELECT
  order_id,
  datastream_metadata.CHANGE_TYPE AS change_type,
  datastream_metadata.CHANGE_SEQUENCE_NUMBER AS change_sequence_number,
  datastream_metadata.UUID AS uuid
FROM `PROJECT_ID.cdc_orders_lab.public_orders_cdc_lab`
WHERE order_id IN (1001, 1002, 1004)
ORDER BY order_id, change_sequence_number;
~~~

**Remember:**

- Change types like **`INSERT`**, **`UPDATE-INSERT`**, **`UPDATE-DELETE`**, and **`DELETE`** represent event semantics—**not** always single-row snapshots.
- **`CHANGE_SEQUENCE_NUMBER`/`SORT_KEYS`** work with metadata to reconstruct ordering per Datastream semantics; never infer order from filenames or ingest timestamps alone.
- At-least-once delivery can emit duplicate events. To build a current-state table from Append-only, downstream pipelines must implement tested **deduplication, ordering, delete handling, and replay**.
- Metadata columns differ between **Merge** and **Append-only**; avoid running queries written for one mode against the other.
- For source tables lacking a PK, append-only behavior can also apply even if the stream selects Merge.

## 8. Datastream → Cloud Storage → Dataflow When Transformations Are Needed

Not every pipeline should write straight to BigQuery. When you need to **retain raw events**, run complex transforms, or push to targets not supported as direct Datastream destinations, write to **Cloud Storage** and process downstream.

~~~mermaid
flowchart LR
    PG[("PostgreSQL WAL")] --> DS["Datastream"]
    DS --> GCS["Cloud Storage\nAvro / JSON CDC files"]
    GCS --> DFR["Dataflow template / custom Beam"]
    DFR --> CUR["BigQuery curated / Cloud SQL / Spanner"]
    GCS --> ARCH["Archive / replay"]
    MET["Event metadata"] -. "ordering + dedup" .-> DFR
~~~

### 8.1. Configuring a Cloud Storage Destination

When creating a **separate stream** in the lab project (never alter a running BigQuery stream if consumers depend on it):

1. Prepare a Cloud Storage bucket in an appropriate location and retention policy, with logging and IAM enabled.
2. Grant the **Datastream service agent** least-privilege bucket read/write permissions per destination docs; never use `allUsers`.
3. Create a **Cloud Storage** destination connection profile pointing to a dedicated bucket and prefix.
4. Pick **Avro** for self-describing schemas or **JSON** if downstream expects text; JSON offers an option to emit a **Unified Types schema file**.
5. Check **gzip compression, file size / flush frequency**, and their impact on latency and small-file costs.
6. Validate the stream, select source objects and backfill, and start with owner approval.

Output paths typically follow **`prefix/object-name/yyyy/mm/dd/hh/mm/file`**, where the date/time folders derive from source metadata per Datastream formatting. **Never** treat filename ordering or folder timestamps as strict commit order.

### 8.2. Illustrative Event (Pseudocode, Not Exact Payload)

~~~json
{
  "row": {
    "order_id": 1001,
    "status": "PAID"
  },
  "metadata": {
    "source": "PostgreSQL",
    "operation": "UPDATE",
    "source_position": "<WAL-position>",
    "event_id": "<unique-change-id>"
  }
}
~~~

The JSON schema **above is strictly conceptual**, not Datastream's actual JSON contract. Real events include **source-specific metadata**, **Datastream metadata**, and payloads whose field names and encodings vary by version and format; parse according to official schema docs. **Avro** embeds schema/types to avoid guessing from filenames. See [Events and streams](https://docs.cloud.google.com/datastream/docs/events-and-streams).

### 8.3. When Using Dataflow

- Use the **Datastream to BigQuery** template compatible with your version, or a custom **Apache Beam** pipeline for other sinks.
- Read both data and metadata, normalize schemas, and handle **at-least-once** delivery and business keys.
- Decide explicitly between **current-state** and **event history**—never mix both semantics in the same table.
- Use checkpoints, dedicated dead-letter/quarantine storage for unparseable events, alerts, and job-ID-scoped replays.
- Configure **windowing/triggers** by event time and acceptable latency; never assume data is complete just because a single file was created.
- Secure raw data in Cloud Storage with bucket IAM, encryption, lifecycle rules, and retention.

**Datastream does not emit a separate Pub/Sub message per change event by default.** You can use Cloud Storage notifications / Eventarc to trigger consumers when files land, though a "file finalized" notification does not mean "one database transaction finished". Consumers must parse and process multiple events per file.

## 9. Schema Evolution and Primary Keys: Where Data Breaks Most Easily

### 9.1. Supported Schema Changes Do Not Make Every DDL Safe

PostgreSQL sources impose several DDL restrictions while a stream runs. Test per engine/version:

| Change | Risk | Recommended policy |
|---|---|---|
| Add nullable column at the end | Usually smoother, yet still verify | Migration + stream/destination schema check |
| Change type `INT → TEXT` | Can break event decoding/mapping | Pause and review compatibility before DDL |
| Rename/drop column | Can cause data loss or downstream drift | Use expand/contract; never break schemas abruptly |
| Change primary key | Can break BigQuery Merge | Planned cutover, reconciliation, and re-backfill per docs |
| Drop PK from table | Table can revert to append-only | Forbid changes without review |
| Missing replica identity on `UPDATE`/`DELETE` | Datastream may fail to capture key values | Require a primary key or valid `REPLICA IDENTITY` |
| Table with large TOAST/LOB columns | May need extra lookups and lose intermediate states | Test and bound sizes/churn |
| New table outside publication | Not replicated automatically | Update publication and stream object filters |

Depending on schema, user, and engine, Datastream **does not detect every DDL change**. Never treat a production BigQuery table as an `ALTER TABLE` testbed; maintain dedicated migrations, a schema compatibility checklist, and recovery/backfill plans.

### 9.2. Choosing `REPLICA IDENTITY`

For PostgreSQL tables with a PK like **`orders_cdc_lab`**, the preferred setting is **`REPLICA IDENTITY DEFAULT`**. Without a PK, a **`UNIQUE NOT NULL` index** with **`USING INDEX`** or another Datastream-supported option may work, subject to BigQuery column type and count limits. **`REPLICA IDENTITY FULL`** adds heavy overhead and can exceed BigQuery Merge's 16-column key limit; never use it as a blanket fix.

~~~sql
-- READ-ONLY inspection of keys and replica identity.
SELECT
  c.relname AS table_name,
  c.relreplident AS replica_identity,
  pg_get_indexdef(i.indexrelid) AS index_definition
FROM pg_class c
LEFT JOIN pg_index i ON i.indrelid = c.oid AND i.indisprimary
WHERE c.oid = 'public.orders_cdc_lab'::regclass;
~~~

**Never modify PKs or `REPLICA IDENTITY` in production** without knowing how active streams rely on them as logical keys.

## 10. Replication Accuracy: Checkpoints, Deduplication, and Reconciliation

### 10.1. Datastream Does Not Promise Exactly-Once Delivery

Datastream provides **at-least-once event delivery** with no ordering guarantee across arrival. An event can be redelivered after retries or recovery, and event A committed earlier is not guaranteed to arrive before event B. **Destinations or consumers must use metadata and idempotent logic** to achieve accurate current state or duplicate-free history.

~~~mermaid
sequenceDiagram
    participant PG as PostgreSQL
    participant DS as Datastream
    participant Q as Consumer / BigQuery
    PG->>DS: INSERT id=1001 seq=10
    PG->>DS: UPDATE id=1001 seq=11
    DS->>Q: UPDATE seq=11
    DS->>Q: INSERT seq=10 (arrives later)
    Note over Q: Do not take 'last arrived event' as row state
    DS->>Q: UPDATE seq=11 (redelivered)
    Note over Q: Apply metadata/sequence/dedup before updating state
~~~

**BigQuery Merge** consolidates keyed rows via Datastream/BigQuery CDC mechanics. When consuming raw events from Cloud Storage or custom Dataflow, **you** must implement deduplication, ordering, and delete handling. Never promise an event is processed exactly once merely because the stream is `RUNNING`.

### 10.2. Reconciliation Metrics to Use

| Check | Goal | Warning |
|---|---|---|
| Source vs. destination **`COUNT`** | Catch large discrepancies | Insufficient on its own to prove accuracy |
| Count of **distinct primary keys** | Catch duplicate keys in current-state tables | Does not apply directly to Append-only |
| Sample checksums by key range | Catch payload mismatches | Normalize types and timezones first |
| Compare over closed time windows | Avoid racing against continuous writes | Compare only when CDC lag is low |
| High-watermark / source position | See how far the stream has read | Does not prove the table has finished merging |
| `DELETE` correctness | Ensure deleted rows vanish in Merge | Avoid treating tombstones as active rows |
| Unsupported event rate | Spot unhandled data types or DDL | Changes can be lost even while the stream runs |
| Per-object backfill status | Confirm full historical snapshot | Stream `RUNNING` alone is not enough |

### 10.3. Reconciling a Lab Table in a Quiet State

1. Pause **lab app writes** using lab controls—never pause a production stream.
2. Record the timestamp/source checkpoint and confirm **no transactions are pending**.
3. Wait for Datastream **total latency** and BigQuery apply to catch up; check stream monitoring rather than guessing with a fixed sleep.
4. Compare **`order_id, status, total_vnd, updated_at`** between PostgreSQL and BigQuery, normalizing timestamps and decimals.
5. Classify any mismatch: catch-up lag, incomplete backfill, wrong PK, type mismatch, incompatible DDL, or dedup/merge bug.
6. Log results in the change ticket: tested keys, SQL checksums, measurement timestamp, and sign-off.

Never use **`MAX(updated_at)`** as a universal CDC checkpoint: databases can run `UPDATE` without touching timestamps, delete rows, backfill snapshots, or commit out of application clock order.

## 11. Monitoring CDC: Freshness, Latency, and WAL Disk Exhaustion Risk

### 11.1. Three Latency Signals Not to Conflate

| Datastream signal | What does it measure? | Where to look when elevated |
|---|---|---|
| **Data freshness** | Delay from source commit until Datastream reads the change | Source overload, WAL backlog, replication privileges, source network |
| **System latency** | Delay inside Datastream from reading source to writing destination | Destination quotas/permissions, pipeline processing |
| **Total latency** | End-to-end from source commit to Datastream writing destination | Both layers above plus queuing |
| **Backfill progress** | Objects pending, in progress, or failed | Large-table scans, source I/O, per-table errors |
| **Unsupported events** | Events that could not be processed | Incompatible DDL, schemas, or data types |
| **PostgreSQL WAL retention** | WAL held by the replication slot | Slow source reads, inactive slot, growing disk usage |

**A data freshness value of 0 can simply mean no new events occurred**, not proof that all downstream tables have applied every change. Inspect **system/total latency**, stream errors, BigQuery query freshness, and end-to-end reconciliation.

### 11.2. Read-Only Commands and Inspection Checklist

~~~bash
# Datastream status/config; modifies no resources.
gcloud datastream streams list \
  --project="$PROJECT_ID" --location="$REGION"

gcloud datastream streams describe "$STREAM_ID" \
  --project="$PROJECT_ID" --location="$REGION" \
  --format="yaml(name,state,errors,sourceConfig,destinationConfig,backfillAll)"

# Inspect connection profiles only; avoid printing secrets into tickets.
gcloud datastream connection-profiles list \
  --project="$PROJECT_ID" --location="$REGION"
~~~

In **Datastream → Streams → stream → Monitoring**, review graphs for throughput, data freshness, system/total latency, unsupported events, and backfill object states. In **Cloud Monitoring**, configure alerts on **`datastream.googleapis.com`** metrics such as **`stream/freshness`**, **`stream/system_latencies`**, and **`stream/total_latencies`**—verifying exact metric names and labels in Metrics Explorer for your project.

### 11.3. Monitoring Source PostgreSQL

~~~sql
-- READ-ONLY; requires replication stats privileges.
SELECT
  slot_name,
  active,
  restart_lsn,
  confirmed_flush_lsn,
  pg_size_pretty(
    pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)
  ) AS approx_wal_retained
FROM pg_replication_slots
WHERE slot_name = 'ds_orders_lab_slot';

-- READ-ONLY total row count of the lab table.
SELECT
  COUNT(*) AS current_rows,
  MAX(updated_at) AS latest_source_update
FROM public.orders_cdc_lab;
~~~

**Two separate facts:** a logical slot can retain WAL even with **zero business traffic**, and conversely heavy business updates do not directly tell you how many WAL bytes remain pinned. Monitor **Cloud SQL disk usage/free space**, logs, and the replication slot together. If disk fills up due to an inactive slot, engage the DBA/on-call to execute a recovery plan; **never unilaterally drop the slot** to free space, as that destroys CDC continuity from the prior position.

### 11.4. Sample Alerts (Lab SLOs Only)

| Condition | Illustrative threshold | Response |
|---|---|---|
| Stream not `RUNNING` | > 5 minutes outside maintenance | Check errors and owner |
| Total latency | > 5 minutes over 10 minutes | Isolate source vs. destination |
| Backfill object `FAILED` | Any lab object | Inspect permissions, types, and PK |
| Unsupported events | > 0 on critical sources | Pause DDL, investigate schema |
| WAL retained bytes | Rising steadily under load, past DBA threshold | Diagnose slot, backlog, and disk |
| Cloud SQL available disk | Below approved headroom | Escalate early to prevent outage |
| BigQuery query failures | Spike after schema change | Check mapping and destination permissions |

**Never treat 5 minutes as Datastream's default SLA.** SLOs are defined by the business: risk reporting may require 30 seconds, while financial analytics may allow 15 minutes with strict post-reconciliation accuracy.

## 12. IAM, Data Security, and Cost Governance

### 12.1. Multi-Layer Access Control

| Component | Principal / permissions | Warning |
|---|---|---|
| **Database source** | PostgreSQL user with `LOGIN REPLICATION` + scoped `SELECT`/`USAGE` | Never use the `postgres` superuser for routine connections |
| **Datastream control plane** | Operators with scoped create/update/validate permissions on streams/profiles | Never grant project-wide Editor unnecessarily |
| **Datastream service agent** | Scoped BigQuery Storage Write / GCS destination permissions | Platform identity; never assign `serviceAgent` roles to developers |
| **BigQuery dataset** | Authorized BI consumers/analysts with read access | Analytics access does not mean raw PII access |
| **Cloud Storage** | Bucket IAM, encryption, and lifecycle rules | Never grant `allUsers` or create public buckets |
| **KMS / networking** | CMEK, peering/PSC, TLS, and firewalls per policy | Involve network/KMS admins when required |
| **Auditing** | Cloud Audit Logs and stream change records | Never print secrets or passwords into logs |

**CDC will replicate a PII column the moment it appears.** This creates a data copy requiring the same protection as the source—not "anonymized" analytics data. Use object/column include/exclude filters where supported, restricted datasets, encryption, and strict retention. For sensitive fields, apply masking or tokenization in the pipeline before exposing data to BI.

### 12.2. Multi-Project or Private Networking Topologies

If the stream lives in **project A**, the source in **project B**, and the BigQuery destination in **project C**, three approvals are needed:

1. Source DB user and network path from Datastream to the source, including Cloud SQL/VPC/Firewall/SSL.
2. The stream project's Datastream service agent granted destination permissions on project/dataset/bucket in C.
3. Operators creating, running, and monitoring the stream granted permissions on **project A** plus required log/metric read access.

**Never assume that having Project Owner in A grants the service agent write access to BigQuery in C.** Verify the actual service agent identity and cross-project IAM.

### 12.3. Cost Components to Estimate

| Cost item | What drives it? | Mitigation |
|---|---|---|
| **Datastream** | Data volume processed/transferred to destination, covering backfill and CDC per SKU | Select only needed tables/columns; avoid needless restarts/backfills |
| **Cloud SQL / source** | Backfill I/O, WAL storage, CPU/replication overhead | Throttle load, monitor disk headroom |
| **BigQuery CDC** | Storage Write API and background merges per pricing/reservations | Pick Merge vs. Append intentionally; tune `max_staleness` and reservations |
| **BigQuery queries/storage** | Data retention, queries, BI/ML jobs | Partition/cluster tables; track quotas and cost dashboards |
| **Cloud Storage** | File sizes, object counts, storage, operations | Tune format, flush intervals, and lifecycle rules |
| **Dataflow** | Worker compute, streaming uptime, shuffle/storage | Configure autoscaling and pipeline limits |
| **Network/KMS/Monitoring** | Egress, encryption, logs, and metrics | Align regions, topology, and retention |

**Datastream and BigQuery bill separately.** With **BigQuery Merge**, background CDC applies also consume compute; **`max_staleness`** trades freshness against query cost/latency, not a toggle for "free merges". Never try to save money by retaining WAL indefinitely or turning off backups and observability.

### 12.4. Throughput Estimation Exercise

Suppose **200,000 rows** are backfilled at an average of **1 KiB** of replicated data per row:

\[
200,000 \times 1\ \mathrm{KiB}
\approx 195.3\ \mathrm{MiB}
\]

If ongoing CDC writes **50,000 changes/day × 0.5 KiB/change**, that is roughly **24.4 MiB/day**, excluding event metadata, framing overhead, retries, backfill read amplification, and BigQuery merge/query charges. **Never multiply PostgreSQL on-disk table size by a Datastream unit rate** expecting an exact invoice: Datastream bills on processed data volume per SKU, which differs from compressed on-disk storage.

## 13. Incident Response and Recovery Runbook

### 13.1. Layered Diagnosis

~~~mermaid
flowchart TD
    A["Dashboard: freshness or errors spiking"] --> B{"Is the stream still RUNNING?"}
    B -->|"No"| C["Inspect errors / connection profiles"]
    B -->|"Yes"| D{"Is data freshness high?"}
    D -->|"Yes"| E["Check source WAL/slot, network, and load"]
    D -->|"No"| F{"Is system latency high?"}
    F -->|"Yes"| G["Check BigQuery/GCS destination, quotas/IAM"]
    F -->|"No"| H["Check BigQuery merge staleness and data correctness"]
    E --> R["Fix root cause, verify catch-up"]
    G --> R
    C --> R
    H --> R
    R --> I["Reconcile source-destination, sign off"]
~~~

### 13.2. Common Failure Matrix

| Error / symptom | Likely cause | Controlled remediation |
|---|---|---|
| Validate source connection failed | Wrong host/port/password, firewall/PSC/peering | Check connection profile, routes, TLS |
| PostgreSQL permission denied | User lacks `REPLICATION`/`SELECT`/`USAGE` | Grant scoped DB/slot/table privileges |
| Publication or slot not found | Typo or created in the wrong database | Check PostgreSQL database and `pg_replication_slots` |
| WAL growing without bound | Inactive slot, paused/errored Datastream, long transactions | Check slot, source disk, recovery plan with DBA |
| Backfill very slow | Huge table, I/O-starved source, throttling | Adjust concurrency/window, monitor object status |
| High source data freshness lag | WAL generated faster than read rate, slow network | Split high-volume tables into separate streams if appropriate |
| High system latency | Destination quotas/permissions, write lag | Check BigQuery/GCS logs, IAM, service health |
| BigQuery count > source | Table lacks PK or uses Append-only | Distinguish event history from current state |
| Merge fails to apply `DELETE` | Wrong PK / replica identity / CDC lag | Inspect source setup, stream metadata, apply lag |
| Schema changed, events fail | Incompatible drop/rename/type change | Halt DDL, follow migration plan, approved re-backfill |
| Unsupported events rising | Unsupported data type or decode error | Isolate affected table/column per source docs |
| Quota exceeded / `429` | BigQuery API capacity / write-stream limits | Rate limits, reservations, quota increase, backoff |
| Replication resumes but misses rows | WAL purged; source position lost | Recover/recreate stream and backfill per runbook; reconcile |
| Same-region source + destination still lags | Multi-layer lag and load | Inspect the full pipeline, not just network RTT |

### 13.3. When a Stream Is Stopped Too Long

1. **Do not rush to delete the stream or slot.** Record outage timestamp, slot state, and WAL position.
2. Have the DBA inspect **disk headroom** and **log retention** on the source, prioritizing database uptime.
3. Determine whether the stream can **resume/recover from retained WAL** or requires a new slot/stream and **re-backfill**.
4. If replacing the slot, calculate the **coverage gap** and data needing reconciliation; never declare recovery complete just because the stream shows `RUNNING`.
5. In BigQuery/GCS, handle duplicate events and verify final state by PK.
6. Audit `DELETE`d rows and any tables with DDL changes during the outage.
7. Close the incident and update the change record only once data correctness is verified.

**Never manually drop a PostgreSQL replication slot actively used by a stream** just to clear a full-disk alert; doing so breaks CDC continuity. If dropping it is unavoidable to save the database, require DBA/on-call sign-off and a **reseed/re-backfill** plan afterward.

### 13.4. Pausing, Resuming, and Configuration Changes

- **Pausing** transitions the stream through draining to paused; **the source continues generating WAL/binlogs** while paused.
- **Resuming** can pick up from a valid position if logs remain; there is no guarantee once retention expires.
- Changing object filters, connection profiles, write modes, schemas, or destinations may require re-verifying backfills, IAM, and downstream contracts.
- Before major DB upgrades or PK changes, plan per engine-specific docs; PostgreSQL major upgrades may require a new slot or recovery workflow.
- When changing production configs, test in canary/staging or via a parallel stream with planned reconciliation and cutover.

## 14. Case Study: Syncing Order Analytics from a Java App

### 14.1. Context

An e-commerce company uses **Cloud Run Java/Spring Boot → Cloud SQL PostgreSQL** for transactions. Analytics wants order status tracking in BigQuery while the transactional API maintains low latency and strict consistency.

**Goal:** analytics updated at **p95 total latency under 3 minutes** under normal load, without starving the source DB of WAL/disk, while accurately handling refunds, cancellations, and price adjustments.

~~~mermaid
flowchart LR
    APP["Java Orders API"] --> PG[("Cloud SQL PostgreSQL\nOLTP")]
    PG --> WAL["Logical WAL + publication"]
    WAL --> DS["Datastream\norders-main stream"]
    DS --> BQ["BigQuery Merge\ncurrent orders"]
    BQ --> DASH["Near-real-time dashboards"]
    PG --> OUTBOX["Order events / outbox"]
    OUTBOX --> OTHER["Business events for services"]
    MON["SRE alerts\nfreshness, WAL, merge"] -. "Monitors" .-> DS
    MON -. "Disk / slot" .-> PG
~~~

**Design:**

- **Source:** publication includes only **`public.orders`** and genuinely required analytics tables; dedicated replication user.
- **BigQuery:** Merge for PK tables; separate append-only table only when event history is explicitly needed.
- **Networking:** private connectivity and cross-project IAM reviewed.
- **Backfill:** executed during off-peak hours while watching I/O; CDC picks up ongoing commits.
- **Consumers:** BI reads curated tables/views with separated permissions rather than raw PII.
- **Observability:** alerts on latency, unsupported events, PostgreSQL disk/WAL, and BigQuery CDC apply failures.
- **Governance:** schema changes follow expand/contract with migration contracts and rollbacks.

### 14.2. Hypothetical Incident

A reconciliation job updates millions of orders inside **one massive transaction**. Datastream PostgreSQL uses one replication slot per stream, so other tables in the same stream fall behind too. Dashboards show rising data freshness lag, and Cloud SQL WAL disk usage climbs.

**What NOT to do:** drop the slot to "start fresh", raise Cloud Run max instances, or skip destination checks just because the stream still reads `RUNNING`.

**Remediation:**

1. Inspect the active/recently committed transaction, PostgreSQL WAL disk usage, and Datastream metrics.
2. Confirm the bottleneck stems from a single high-write transaction/table.
3. Plan to isolate **high-churn tables** into a **separate stream** with its own publication/slot if sustained volume stays high, assessing source impact before multiplying slots.
4. If CDC stalled too long, execute reconciled recovery/backfill rather than assuming all WAL remains intact.
5. Close the incident only once BigQuery matches across **primary keys, `UPDATE`/`DELETE`, and time windows**—not just `COUNT(*)`.

### 14.3. Acceptance Criteria

| Condition | Evidence |
|---|---|
| Complete backfill | All in-scope objects verified |
| Working CDC | `UPDATE`/`DELETE` reflected accurately in BigQuery |
| Freshness meets SLO | Dashboard p95 and alerts verified operational |
| Zero source outage | WAL/storage/CPU/connection headroom within limits |
| Least-privilege IAM | Source reader, service agent, and BI consumers separated |
| Governed DDL | Migration reviews and compatibility tests passed |
| Recoverable | Re-backfill/reconciliation runbook tested in staging |
| Tracked costs | Datastream + BigQuery CDC + Cloud SQL + Logging/Billing |

## 15. Applied Exercises and Answers

### 15.1. Exercise A — Batch vs. CDC

An application transitions orders **`NEW → PAID → CANCELLED`** and later runs a **`DELETE`** per retention policy.

**Question:** why can `SELECT WHERE updated_at > last_run` miss changes?

**Guided answer:** physical `DELETE`s vanish from queries; transactions can commit late with older `updated_at` timestamps; application clocks can skew; or status updates might omit updating `updated_at`. WAL-based CDC reads committed engine changes, provided publication, replica identity, and log retention are properly configured.

### 15.2. Exercise B — Preparing PostgreSQL

Given table **`public.orders_cdc_lab`** with a PK and user **`ds_orders_reader`**.

**Prompt:** list 5 prerequisites for Datastream to read CDC.

**Answer:** (1) logical decoding enabled; (2) publication covering the target table; (3) unique replication slot using **`pgoutput`**; (4) `LOGIN`/`REPLICATION`/`SELECT`/`USAGE` privileges on the database role; (5) network route/TLS/credentials and stream config pointing to the exact database. Add **WAL disk monitoring** before going to production.

### 15.3. Exercise C — Merge vs. Append-Only

A source starts with 3 rows; during one interval it performs **1 `INSERT`**, **1 `UPDATE`**, and **1 `DELETE`** across distinct keys.

**Question:** do both destination modes end up with the same final row count?

**Answer:** no. **Merge** reflects current state once caught up: still 3 rows (`+1 -1`). **Append-only** stores individual events and backfill records, yielding more than 3 rows; reconstructing state requires decoding **`CHANGE_TYPE`**, metadata, deduplication, and ordering.

### 15.4. Exercise D — Out-of-Order Events

A consumer receives `UPDATE` with sequence **12**, then `INSERT` with sequence **11**, and then a redelivered `UPDATE` **12**.

**Question:** is a "last event arrived wins" algorithm safe?

**Answer:** no. Use the ordering key in **Datastream metadata** for the source, deduplicate by event ID/`UUID` or composite key, handle tombstones/`DELETE`s properly, and verify replays. With BigQuery Merge, rely on platform CDC consolidation; with Cloud Storage files, consumers must implement this logic.

### 15.5. Exercise E — Computing Latency

A change commits at **10:00:00**, Datastream reads it at **10:00:40**, and writes to the destination at **10:01:10**. Ignore BigQuery apply/query time.

\[
\text{Data freshness} \approx 40\ \mathrm{s}
\]

\[
\text{System latency} \approx 30\ \mathrm{s}
\]

\[
\text{Total latency} \approx 70\ \mathrm{s}
\]

**Question:** if system latency stays at 30 seconds while data freshness climbs to 8 minutes, which layer should you inspect first?

**Answer:** the source, WAL, replication slot, source network, or rapid log generation rate. Do not blame BigQuery prematurely when Datastream hasn't even read the source changes yet.

### 15.6. Exercise F — Why Did WAL Fill the Disk?

PostgreSQL has logical replication slot **`ds_orders_lab_slot`**, the stream has been paused for 2 days, and the database continues processing heavy writes.

**Answer:** the slot retains WAL needed by its consumer and cannot reclaim segments not yet confirmed flushed. Inspect disk space, stream state, slot active status, `restart_lsn`, and production logs; only a DBA with change approval should decide between resume, recover, or drop/reseed. Never drop a needed slot just to reclaim disk space.

### 15.7. Exercise G — Reviewing Schema Evolution

A proposal bundles **renaming `order_id`**, **dropping the primary key**, and **changing `total_vnd`'s type** in one live migration while the stream runs.

**Answer:** very high risk: BigQuery Merge relies on the PK, and DDL renames/type changes can corrupt data or drop events. Split migrations into backward-compatible steps, test in staging, define downstream contracts, back up, and prepare a backfill/recovery plan—proceeding only with data-owner sign-off.

### 15.8. Exercise H — Estimating and Optimizing Cost

A source backfills **5 GiB** and then generates **500 MiB/day** of changes processed by Datastream. Over the first 30 days, illustrative source volume before overhead is:

\[
5\ \mathrm{GiB} + 30 \times 500\ \mathrm{MiB}
= 5\ \mathrm{GiB} + 14.65\ \mathrm{GiB}
\approx 19.65\ \mathrm{GiB}.
\]

**Question:** can you use this number to predict the entire pipeline invoice?

**Answer:** no. Datastream bills by source SKU and processed volume; BigQuery CDC merges, queries, tables, Cloud SQL storage/compute, networking, backups, Logging, and Dataflow (if used) bill separately. Inspect Cloud Billing reports instead of multiplying by one flat rate.

### 15.9. Exercise I — Lab Report Template

~~~text
PROJECT_ID / STREAM_REGION / OWNER:
SOURCE_DB / ENGINE_VERSION / PRIMARY_KEY:
PUBLICATION / REPLICATION_SLOT / REPLICA_IDENTITY:
REPLICATION_USER / PERMISSIONS:
PRIVATE_CONNECTIVITY_OR_ALLOWLIST:
SOURCE_PROFILE / DESTINATION_PROFILE:
STREAM_ID / OBJECT_FILTER / BACKFILL_STATUS:
DESTINATION_BIGQUERY_DATASET / WRITE_MODE / MAX_STALENESS:
INSERT_CHECK / UPDATE_CHECK / DELETE_CHECK:
SOURCE_ROW_COUNT / DEST_ROW_COUNT / KEY_RECONCILIATION:
DATA_FRESHNESS / SYSTEM_LATENCY / TOTAL_LATENCY:
WAL_RETAINED / DISK_HEADROOM / UNSUPPORTED_EVENTS:
IAM / ENCRYPTION / RESIDENCY / RETENTION:
COST_BREAKDOWN / CHANGE_TICKET / CLEANUP:
OPEN_ISSUES:
~~~

Mark **PASS** only with evidence from the database, Datastream, and BigQuery. Without an authorized lab project, mark **NOT_EXECUTED** and document the exact steps rather than claiming replication succeeded.

## 16. Resource Cleanup and Data Preservation

### 16.1. Pre-Cleanup Checklist

1. Confirm **source, destination, and stream** belong exclusively to the lab with no other consumers.
2. Stop all producer writes to **`orders_cdc_lab`** and finalize reconciliation records.
3. Check whether stream objects finished and whether any data needs archiving.
4. With owner approval, **pause/drain/delete only the lab stream** in the Datastream Console.
5. Only after the stream no longer uses the slot should the DBA clean up the **replication slot and publication**.
6. Only afterward delete the lab PostgreSQL table, BigQuery table/dataset, and lab credentials.
7. Retain audit records, logs, and backups per retention policy; never delete shared assets.

### 16.2. Verification Before Deletion

~~~bash
# READ-ONLY; creates or deletes no cloud resources.
gcloud datastream streams describe "$STREAM_ID" \
  --location="$REGION" --project="$PROJECT_ID"

gcloud datastream streams list \
  --location="$REGION" --project="$PROJECT_ID"

bq --project_id="$PROJECT_ID" ls "$PROJECT_ID:$BQ_DATASET"
~~~

~~~sql
-- READ-ONLY PostgreSQL check before the DBA cleans up the slot:
SELECT slot_name, active, restart_lsn
FROM pg_replication_slots
WHERE slot_name = 'ds_orders_lab_slot';

SELECT pubname
FROM pg_publication
WHERE pubname = 'ds_orders_lab_pub';
~~~

**Never run `pg_drop_replication_slot` on production on your own.** Dropping an active slot breaks continuity; deleting a stream while forgetting the slot keeps pinning WAL. Cleanup must follow the exact order and be verified by a DBA.

### 16.3. Approved Lab Deletion Commands (If Needed)

Once the **stream is fully deleted, consumers are stopped, and the slot is confirmed inactive**, the DBA can run the following **inside the lab database** after double-checking names:

~~~sql
-- DESTRUCTIVE: DBA only, lab database only, requires owner approval.
SELECT pg_drop_replication_slot('ds_orders_lab_slot');
DROP PUBLICATION IF EXISTS ds_orders_lab_pub;

-- Only if the table belongs to the lab with no data worth keeping:
DROP TABLE IF EXISTS public.orders_cdc_lab;
~~~

**Never delete shared database instances, IAM/service agents, or shared BigQuery datasets.** Before cleaning up a BigQuery table, confirm the stream is stopped/deleted so it isn't recreated automatically. Cloud Storage buckets, Dataflow jobs, and KMS keys (if any) have separate lifecycles and cleanup steps.

## 17. Official References and Summary

**Datastream:**

- [Datastream overview](https://docs.cloud.google.com/datastream/docs/overview)
- [Key concepts and behavior](https://docs.cloud.google.com/datastream/docs/behavior-overview)
- [Events and streams](https://docs.cloud.google.com/datastream/docs/events-and-streams)
- [Sources](https://docs.cloud.google.com/datastream/docs/sources)
- [Destinations](https://docs.cloud.google.com/datastream/docs/destinations)
- [Configure Cloud SQL for PostgreSQL for CDC](https://docs.cloud.google.com/datastream/docs/configure-cloudsql-psql)
- [PostgreSQL source behavior and limitations](https://docs.cloud.google.com/datastream/docs/sources-postgresql)
- [Configure a BigQuery destination](https://docs.cloud.google.com/datastream/docs/configure-bigquery-destination)
- [BigQuery destination behavior and metadata](https://docs.cloud.google.com/datastream/docs/destination-bigquery)
- [Configure a Cloud Storage destination](https://docs.cloud.google.com/datastream/docs/destination-gcs)
- [Create a stream](https://docs.cloud.google.com/datastream/docs/create-a-stream)
- [Manage streams](https://docs.cloud.google.com/datastream/docs/manage-streams)
- [Monitor a stream](https://docs.cloud.google.com/datastream/docs/monitor-a-stream)
- [Diagnose issues](https://docs.cloud.google.com/datastream/docs/diagnose-issues)
- [General best practices](https://docs.cloud.google.com/datastream/docs/best-practices-general)
- [Datastream pricing](https://cloud.google.com/datastream/pricing)

**Related:**

- [BigQuery change data capture](https://docs.cloud.google.com/bigquery/docs/change-data-capture)
- [Cloud SQL for PostgreSQL](https://docs.cloud.google.com/sql/docs/postgres)
- [Dataflow overview](https://docs.cloud.google.com/dataflow/docs/overview)
- [Cloud Monitoring metrics for Datastream](https://docs.cloud.google.com/monitoring/api/metrics_gcp_d_h)

**Key takeaway:** CDC is a **change stream**, not automatically a stream of **business events**. Datastream reduces pipeline operational toil, yet **it does not guarantee single delivery or strict ordering to destinations**, and **it cannot recover expired WAL by resuming alone**. Designing with **primary keys / replica identities**, metadata, observability, reconciliation, source log retention, and runbooks is essential for trustworthy analytics.

**Connecting to the `CLOUD_PROVIDERS_GCP` learning path:** this lesson ties together **Cloud SQL/AlloyDB, IAM, VPC/private connectivity, BigQuery, Cloud Storage, Dataflow, Cloud Monitoring, and Cloud Billing**. A strong production pipeline doesn't just stream continuously—it stays **accurate across `INSERT`/`UPDATE`/`DELETE`, safe for the source database, recoverable, and cost-controlled**.
