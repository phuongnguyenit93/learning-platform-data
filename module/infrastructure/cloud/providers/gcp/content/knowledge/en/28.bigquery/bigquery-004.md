# BigQuery Storage Write API and Streaming Data

> **Chapter:** BigQuery  
> **Module:** CLOUD_PROVIDERS_GCP

An IoT platform continuously sends temperature events, device states, and measurement timestamps. The analytics team wants to query fresh data in **BigQuery** shortly after writing, while the event sender may retry due to network drops. Uncontrolled retries will cause reports to double-count; writing row-by-row without batching wastes bandwidth and quota. The **BigQuery Storage Write API** solves online data ingestion using *write streams*, asynchronous writes, and distinct options for **visibility timing** and **duplicate prevention guarantees**.

This lesson belongs to the **CLOUD_PROVIDERS_GCP** module, connecting project/IAM, VPC, Cloud Run, Pub/Sub, Dataflow, and BigQuery concepts to reliable pipeline design, operations, security, and cost control. The content emphasizes the **Storage Write API over gRPC** and the Java client; REST and other ingestion options are compared so you know when to use each.

**Learning objectives:** After this lesson, learners will be able to:

1. Distinguish the Storage Write API from batch load jobs and legacy streaming inserts.
2. Choose **default**, **application-created committed**, or **pending** streams per business requirements; understand that the buffered type is mainly for advanced use cases.
3. Understand the exact scope of **at-least-once**, **exactly-once via offsets**, and **atomic batch commit**.
4. Configure BigQuery table schemas, partitioning, and least-privilege IAM for producers.
5. Use Java `JsonStreamWriter` to send a JSON batch to the default stream, wait for acknowledgment, and handle errors.
6. Design checkpoint/retry/idempotency, schema evolution, and dead-letter queues (DLQ).
7. Observe throughput, quotas, latency, duplicate events, and costs using BigQuery/Cloud Monitoring.
8. Complete a lab testing the event ingestion path and comparing stream types.

## 1. Reference Architecture for Streaming Analytics

~~~mermaid
flowchart LR
  DEVICE["IoT devices / apps"] --> PUB["Pub/Sub topic\nevents-raw"]
  PUB --> WORKER["Dataflow or Cloud Run worker\nvalidate, transform, batch"]
  WORKER -->|"Storage Write API gRPC\nAppendRows"| BQ["BigQuery\nstream_lab.events"]
  WORKER -->|"Non-retryable errors"| DLQ["DLQ / Cloud Storage\nquarantine"]
  BQ --> SQL["BigQuery SQL\npartition + cluster"]
  WORKER --> OBS["Cloud Logging / Monitoring"]
  BQ --> OBS
~~~

**Why use Pub/Sub?** Pub/Sub acts as a buffer and event distribution layer so producers do not have to wait on BigQuery. When BigQuery slows down or hits quota, consumers can throttle and reprocess. However, **Pub/Sub does not guarantee a duplicate-free BigQuery table**: you must select appropriate stream semantics or include event keys for deduplication.

BigQuery is suited for analytics and SQL over large volumes; it is **not an OLTP database** for per-request order updates. If application transactions are needed, typically write to Cloud SQL/Firestore first, then forward analytical events to BigQuery.

### 1.1. Components and Responsibilities

| Component | Role | Risks to Handle |
| --- | --- | --- |
| Producer | Generates `event_id`, sends schema-compliant data | Duplicate sends, skewed device clocks |
| Pub/Sub | Buffers and delivers events to consumers | Redelivery, backlog, retention |
| Worker | Validates, enriches, batches, retries/acks | Crashes before/after acknowledgment |
| Storage Write API | Ingests data into BigQuery | Quotas, stream state, offset/schema errors |
| BigQuery table | Stores data for SQL/reporting | Partition/cluster design, schema, duplicate rows |
| Monitoring/DLQ | Observes pipeline and holds failed records | Exposing sensitive data, silently dropping bad data |

**Key rule:** An acknowledgment from `AppendRows` confirms BigQuery's ingestion call under the stream's semantics; it does **not** confirm that every downstream business workflow has finished. Pub/Sub acknowledgment is a separate event.

## 2. Choosing the Right BigQuery Ingestion Method

| Method | When to Use | Latency / Semantics | Notes |
| --- | --- | --- | --- |
| **Storage Write API gRPC** | Continuous streaming, high throughput, offset/batch control | Near real-time; stream-dependent at-least-once or in-stream exactly-once | **Preferred for new streaming designs** |
| **Storage Write API REST** | Stateless clients / difficult to maintain gRPC connections | Depends on REST method and semantics | Lacks full gRPC capabilities; check pricing separately |
| **BigQuery load job** | Files in Cloud Storage; batch processing | Data available after load job completes | Suited for large batches; separate quota/cost model |
| **Legacy `tabledata.insertAll`** | Legacy systems already using streaming inserts | Legacy streaming mechanism with best-effort `insertId` dedup | Not equivalent to write streams with offsets |
| **Dataflow BigQueryIO** | Want a streaming framework with checkpoints/scaling/retries | Depends on `STORAGE_WRITE_API` / `STORAGE_API_AT_LEAST_ONCE` | Configure the Beam connector properly |

**Do not confuse:** The `bq insert` command and some legacy streaming SDKs often use **`tabledata.insertAll`**, not the Storage Write API gRPC covered here. The **Storage Read** API is also completely different from the **Storage Write** API.

Per the [overview documentation](https://docs.cloud.google.com/bigquery/docs/write-api-intro), gRPC offers long-lived connections, binary serialization (Protocol Buffers/Arrow), async writes, stream-level transactions, and generally lower ingestion costs than REST. Always verify pricing/quotas at deployment time.

## 3. Four Write Stream Types and When Data Becomes Queryable

A **stream** is a write channel targeting **a single BigQuery table**. Multiple streams can write to the same table in parallel; each type has different visibility and commit behavior.

| Stream | Requires `CreateWriteStream`? | When Are Rows Visible? | Characteristic Guarantee | Purpose |
| --- | --- | --- | --- | --- |
| **Default stream** (name ends in `_default`) | **No** | Once write is acknowledged by server | **At-least-once**, retries can duplicate | General streaming |
| **Application-created COMMITTED** | Yes | After `AppendRows` acknowledgment | **Exactly-once within the stream when using offsets** | Streaming requiring duplicate control |
| **PENDING** | Yes | **Only after `BatchCommitWriteStreams`** | Atomic commit across multiple streams | Batch/parallel imports |
| **BUFFERED** | Yes | After `FlushRows` up to a specified offset | Fine-grained partial visibility control | Advanced scenarios, typically via Beam |

**Note:** The default stream uses committed behavior but **lacks the exactly-once offset tracking of an application-created committed stream**. Therefore, the accurate description is "default at-least-once," not "all committed streams are exactly-once."

### 3.1. Default Stream: Lowest-Complexity Ingestion

~~~mermaid
sequenceDiagram
  participant P as Worker
  participant D as Default stream
  participant Q as BigQuery SQL
  P->>D: AppendRows(batch A)
  D-->>P: ACK
  Q->>D: SELECT...
  D-->>Q: Batch A is queryable
  Note over P,D: Lost ACK → retry may create duplicates
~~~

With the default stream, producers **do not need to create or close separate streams**, can share multiple connections, and achieve high throughput. This is the default choice when data already carries an `event_id` for downstream deduplication or when occasional duplicate records are acceptable.

### 3.2. Committed Stream: Using Offsets to Prevent Duplicate Retries

An application-created COMMITTED stream maintains a **current write position (next offset)**, counted by **number of rows appended**, starting at 0. `AppendRows(rows, offset)` succeeds only if the offset matches the expected position.

~~~text
New stream, next_offset = 0
AppendRows([A,B], offset=0)  → OK; next_offset = 2
AppendRows([C], offset=2)    → OK; next_offset = 3
Retry [C] with offset=2      → ALREADY_EXISTS (already written)
AppendRows([D], offset=5)    → OUT_OF_RANGE (gap detected)
~~~

If it is unclear whether a previous request **was executed by the server**, retry the **same batch at the same offset** after reconnecting. `ALREADY_EXISTS` indicates that offset was already written, which is safe only if you guarantee the offset maps to the **exact same payload**; mismanaging offsets can drop data. `OUT_OF_RANGE` typically requires reconciling against the checkpoint / last-acknowledged offset.

**Scope of guarantee:** Exactly-once holds only **within a single stream with accurate offsets**. If the same event is sent over **two different streams**, or upstream emits two different `event_id` values for the same business action, BigQuery **does not automatically know they represent the same event**. End-to-end business exactly-once requires designing upstream generation, event-to-stream routing, checkpointing, and deduplication/reconciliation together.

### 3.3. Pending Stream: Atomic Commit Across Multiple Workers

~~~mermaid
sequenceDiagram
  participant C as Coordinator
  participant W1 as Worker A
  participant W2 as Worker B
  participant B as BigQuery
  C->>B: CreateWriteStream(PENDING) x2
  C->>W1: Stream 1
  C->>W2: Stream 2
  W1->>B: AppendRows + Finalize
  W2->>B: AppendRows + Finalize
  C->>B: BatchCommitWriteStreams(1,2)
  B-->>C: Commit ACK
  Note over B: Rows from both streams become visible together
~~~

In a PENDING stream, data is **not visible to queries** before commit. After `FinalizeWriteStream`, no further appends are allowed; once all workers succeed, the coordinator calls `BatchCommitWriteStreams` to **atomically** commit multiple streams. If the commit returns errors, inspect `stream_errors`, check stream state/timeouts, and retry per guidance.

**Do not call a pending stream "real-time streaming"** prior to commit. It is designed for **atomic batch loading** when coordinating multiple parallel workers.

### 3.4. Buffered Stream: Only for Specific Needs

A BUFFERED stream allows appending and then calling `FlushRows` to decide which rows become visible. Google recommends **not using it directly for common use cases**, outside supported integrations like Apache Beam. For near-real-time streaming, choose default or committed; for multi-worker atomic batch commits, choose pending. <https://docs.cloud.google.com/bigquery/docs/write-api-grpc>

## 4. Schema, Format, and Table Layout Before Writing

The lab receives events shaped like:

~~~json
{
  "event_id": "evt-20261119-0001",
  "device_id": "device-0042",
  "event_ts": "2026-11-19T02:00:00Z",
  "temperature_c": 27.5,
  "source": "iot"
}
~~~

Table schema:

| Field | BigQuery Type | Nullability | Meaning |
| --- | --- | --- | --- |
| `event_id` | STRING | REQUIRED | Producer-side unique key for reconciliation/dedup |
| `device_id` | STRING | REQUIRED | Analysis by device |
| `event_ts` | TIMESTAMP | REQUIRED | Timestamp when the event occurred |
| `temperature_c` | FLOAT64 | NULLABLE | Measured value |
| `source` | STRING | NULLABLE | Event source |

**BigQuery tables do not automatically enforce a UNIQUE constraint on `event_id`.** Even declared PRIMARY KEY fields in related features are **not enforced** like in an OLTP database; do not rely on the schema to prevent duplicate writes. Validate `event_id` at the producer and apply query/ETL deduplication when needed.

### 4.1. Partitioning + Clustering Suited for Ingestion

- Partitioning by **day of `event_ts`** lets time-range queries scan fewer partitions.
- Clustering by `device_id` makes queries filtering on specific devices more efficient.
- Late-arriving data must fall within valid partition bounds; if rejected by partition expiration or write restrictions, the pipeline needs a DLQ/rehydration path.
- Consider adding `ingest_ts` (when the system received the event) to measure **ingestion lag**, distinct from the device measurement time `event_ts`.
- With late/out-of-order events, **do not** use arrival order as the default business event ordering.

### 4.2. Java Supports JSON, While the gRPC Wire Format Is Binary

The BigQuery Storage Write API gRPC uses **serialized Protocol Buffers** or **Apache Arrow**. Java `JsonStreamWriter` accepts JSON objects and **converts them to protobuf before sending**; Java `StreamWriter` accepts protobuf schemas/rows directly. Do not think passing a `JSONArray` to `JsonStreamWriter` means the API sends REST JSON.

If a payload contains unexpected fields, wrong types, or invalid values, it can trigger `SCHEMA_MISMATCH_EXTRA_FIELD` or serialization errors. **Do not enable ignore unknown fields to hide pipeline bugs**, because new fields can be silently dropped.

## 5. Permissions and Lab Scope Boundaries

This example only interacts with:

| Resource | Illustrative Value |
| --- | --- |
| Project | `LAB_PROJECT_ID` |
| BigQuery dataset | `stream_lab` |
| Region | `asia-southeast1` |
| Table | `events` |
| Producer runtime SA | `bq-stream-writer@LAB_PROJECT_ID.iam.gserviceaccount.com` |
| gRPC API | `bigquerystorage.googleapis.com` |
| Java library | `com.google.cloud:google-cloud-bigquerystorage` |
| Event identity | `event_id` |
| Java ingest method | `JsonStreamWriter` + default stream |

### 5.1. IAM by Role

| Principal | Permissions | Purpose |
| --- | --- | --- |
| Dataset/table creator | BigQuery Data Owner on the dataset or appropriate admin permissions | Provision/create schema |
| Producer runtime SA | **`bigquery.tables.updateData`** on the table/dataset plus appropriate metadata read access | Storage Write API append |
| Query runner / CI | `bigquery.jobs.create` on the job project + read permissions on dataset/table | Data verification, SQL, and monitoring |
| Cloud Run/GKE caller | Uses runtime SA via ADC | Avoids storing JSON keys in source |
| Monitoring/SRE | Metrics, logs, and corresponding `INFORMATION_SCHEMA` permissions | Observability/investigation |

The predefined role `roles/bigquery.dataEditor` includes `bigquery.tables.updateData` but also grants broader permissions than appending rows. In production, consider a **custom role** or narrowest dataset-level assignment per IAM guidance. Never grant Project Owner to a writer to fix a permission error.

With Storage Write API gRPC, IAM permissions and OAuth scopes are **two separate requirements** in scope-restricted environments. Use **Application Default Credentials** on the workload; the BigQuery Storage Write API does not require a hard-coded service account private key.

### 5.2. Read-Only Preflight

~~~bash
# On a machine with gcloud and bq, verify the project before making changes
gcloud config get-value project
gcloud services list --enabled --project=LAB_PROJECT_ID

bq show --format=prettyjson LAB_PROJECT_ID:stream_lab
bq show --format=prettyjson LAB_PROJECT_ID:stream_lab.events

# Check application identity (if already created)
gcloud iam service-accounts describe \
  bq-stream-writer@LAB_PROJECT_ID.iam.gserviceaccount.com \
  --project=LAB_PROJECT_ID
~~~

If the dataset or table does not exist yet, `bq show` returning not found is expected; **do not run commands creating production resources** to resolve this. Verify billing/quotas, data location, retention, and cost before creating resources.

## 6. Create the Dataset and Partitioned/Clustered Table in the Lab Project

**The following commands mutate resources and may incur charges.** Run them only after project, dataset name, data residency, IAM, and budget are approved. Skip if your sandbox already provides an equivalent table.

~~~bash
# Create the dataset in the same region as the chosen pipeline
bq --location=asia-southeast1 mk \
  --dataset LAB_PROJECT_ID:stream_lab
~~~

Create the **target `events` table** using BigQuery SQL (in the Console or via `bq query --use_legacy_sql=false`), so key fields are declared `NOT NULL` matching the contract in Section 4:

~~~sql
-- Run via BigQuery SQL in the lab project; creates resources and may incur charges
CREATE TABLE IF NOT EXISTS `LAB_PROJECT_ID.stream_lab.events` (
  event_id STRING NOT NULL,
  device_id STRING NOT NULL,
  event_ts TIMESTAMP NOT NULL,
  temperature_c FLOAT64,
  source STRING
)
PARTITION BY DATE(event_ts)
CLUSTER BY device_id
OPTIONS(description="Lab Storage Write API");
~~~

If `events` already exists, `IF NOT EXISTS` **does not alter the existing schema**. Use a clean lab table or inspect the actual schema before ingesting. The producer must still validate `event_id/device_id/event_ts`, because column constraints do not guarantee uniqueness of `event_id`.

### 6.1. Producer Permissions on the Table (Sample)

~~~bash
# Only an authorized IAM administrator should run this in the lab project
bq add-iam-policy-binding \
  --member=serviceAccount:bq-stream-writer@LAB_PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/bigquery.dataEditor \
  --table LAB_PROJECT_ID:stream_lab.events
~~~

The `bq add-iam-policy-binding` command supports **tables/views, not datasets**. If you need to grant permissions across an entire dataset (multiple tables), configure it under **Console → BigQuery → Dataset → Sharing → Permissions** or via the IAM API/IaC. Start with the narrowest table scope and verify permissions using the real workload identity.

## 7. Java: Writing a Small Batch to the Default Stream

This is a Java example using the **BigQuery Storage Write API gRPC** directly, rather than legacy `insertAll`. It requires `google-cloud-bigquerystorage`, `org.json`, the BigQuery Storage API enabled, ADC, and an existing table. Pick library versions via a BOM tested with your JDK/framework rather than pinning an arbitrary version in learning materials.

### 7.1. Complete, Minimal Java Program

~~~java
import com.google.cloud.bigquery.storage.v1.AppendRowsResponse;
import com.google.cloud.bigquery.storage.v1.BigQueryWriteClient;
import com.google.cloud.bigquery.storage.v1.JsonStreamWriter;
import com.google.cloud.bigquery.storage.v1.TableName;
import com.google.api.core.ApiFuture;
import org.json.JSONArray;
import org.json.JSONObject;

public final class WriteEvents {
    public static void main(String[] args) throws Exception {
        String project = "LAB_PROJECT_ID";
        String dataset = "stream_lab";
        String table = "events";
        String parent = TableName.of(project, dataset, table).toString();

        try (BigQueryWriteClient client = BigQueryWriteClient.create()) {
            JsonStreamWriter writer = JsonStreamWriter
                .newBuilder(parent, client)
                .build();
            try {
                JSONArray rows = new JSONArray();
                rows.put(new JSONObject()
                    .put("event_id", "evt-20261119-0001")
                    .put("device_id", "device-0042")
                    .put("event_ts", "2026-11-19T02:00:00Z")
                    .put("temperature_c", 27.5)
                    .put("source", "iot"));

                rows.put(new JSONObject()
                    .put("event_id", "evt-20261119-0002")
                    .put("device_id", "device-0101")
                    .put("event_ts", "2026-11-19T02:00:01Z")
                    .put("temperature_c", 29.1)
                    .put("source", "iot"));

                ApiFuture<AppendRowsResponse> pending = writer.append(rows);
                AppendRowsResponse ack = pending.get(); // Wait for server ACK
                System.out.println("Batch appended: " + ack.hasAppendResult());
            } finally {
                writer.close();
            }
        }
    }
}
~~~

**Why use `JsonStreamWriter.newBuilder(parent, client)`?** When passing a table name instead of a stream name, the Java client writes to the **default stream**; it manages gRPC transport, protobuf mapping, regional headers, and reconnection. Passing an offset to the default stream **does not turn** it into an exactly-once stream.

- `ApiFuture` represents the result of an asynchronous append; this demo calls `get()` to wait for **one** batch to finish.
- Production implementations should send **multiple async batches**, bound inflight bytes/requests, and await all acknowledgments before acking Pub/Sub or shutting down.
- If `get()` throws, do not log payloads or credentials; classify the error, retry with backoff, and handle duplicates as covered below.
- The records use fixed timestamps so tests work independently of the wall clock; **do not reuse `event_id` in real pipelines** unless intentionally testing duplicate handling.
- Do not create/close a writer **per HTTP request** or per message; reuse the writer/channel across long-lived workers.

### 7.2. Verifying Data with SQL

~~~sql
-- Read-only; incurs query charges if exceeding free tier limits
SELECT
  event_id,
  device_id,
  event_ts,
  temperature_c,
  source
FROM `LAB_PROJECT_ID.stream_lab.events`
WHERE event_ts >= TIMESTAMP("2026-11-19T00:00:00Z")
  AND event_ts < TIMESTAMP("2026-11-20T00:00:00Z")
ORDER BY event_ts
LIMIT 20;
~~~

Data from **default/COMMITTED streams** is queryable right after acknowledgment. With PENDING streams, queries **will not see** rows prior to commit. Never poll with `SELECT COUNT(*)` every second as a substitute for monitoring: SQL queries incur costs; use metrics and bounded spot checks instead.

### 7.3. Distinguishing Stream ACK from Uniqueness

Running the program again with the same `event_id` values will append two more rows because the default stream is **at-least-once**. BigQuery does not enforce a unique key automatically. To keep reports from double-counting, for example:

~~~sql
-- Example deduplication query based on event_id, picking the latest record.
-- Without ingest_ts, the tie-breaker may be non-deterministic.
SELECT * EXCEPT(row_num)
FROM (
  SELECT
    *,
    ROW_NUMBER() OVER (
      PARTITION BY event_id
      ORDER BY event_ts DESC
    ) AS row_num
  FROM `LAB_PROJECT_ID.stream_lab.events`
)
WHERE row_num = 1;
~~~

**Note:** If two rows with the same `event_id` share the same `event_ts` but differ in payload, the result can be non-deterministic due to missing a tie-breaker. Production schemas should include **`ingest_ts`/source sequence** and an explicit conflict-resolution rule; use views, projections, or scheduled `MERGE` batches as needed.

## 8. Java Committed Stream: Using Offsets to Prevent Duplicate Retries

The default stream satisfies most pipelines. Switch to an **application-created COMMITTED stream** only when you need exactly-once ingestion at the **stream scope** and are ready to operate checkpointing and stream ownership.

### 8.1. Creating a Stream and Sending an Offset Batch

The Java snippet below reuses `BigQueryWriteClient`, `JsonStreamWriter`, and `TableName` from Section 7, plus imports for `CreateWriteStreamRequest`, `WriteStream`, and `JSONArray`. This is a **logic excerpt** meant to sit inside a worker that already has retry/checkpoint infrastructure, not a standalone Java file:

~~~java
String parent = TableName
    .of("LAB_PROJECT_ID", "stream_lab", "events").toString();

WriteStream spec = WriteStream.newBuilder()
    .setType(WriteStream.Type.COMMITTED)
    .build();

try (BigQueryWriteClient client = BigQueryWriteClient.create()) {
    WriteStream stream = client.createWriteStream(
        CreateWriteStreamRequest.newBuilder()
            .setParent(parent)
            .setWriteStream(spec)
            .build());

    JsonStreamWriter writer = JsonStreamWriter
        .newBuilder(stream.getName(), stream.getTableSchema(), client)
        .build();
    try {
        // JSONArray rows has already been constructed and validated.
        long nextOffset = 0L;
        AppendRowsResponse ack = writer.append(rows, nextOffset).get();

        // Only checkpoint the next row offset after receiving ACK.
        if (!ack.hasAppendResult()) {
            throw new IllegalStateException("No append result");
        }
        nextOffset += rows.length();
        // Persist (stream.getName(), nextOffset) to the checkpoint store.
    } finally {
        writer.close();
    }

    // Optional finalize for COMMITTED once the producer stops writing.
    client.finalizeWriteStream(stream.getName());
}
~~~

**What this snippet leaves to your worker:** checkpoints must be **durable**, stream ownership must be coordinated across workers, unacknowledged batches must be retained to retry with the **exact same payload and offset**, and crashes between ACK and checkpoint write must be handled. Keeping `long nextOffset` in RAM is purely illustrative and **insufficient for end-to-end exactly-once**. Never finalize a stream still in use by another worker.

### 8.2. Concrete Checkpoint Rules

| Scenario | What the Worker Must Do |
| --- | --- |
| Append at offset 0 succeeds for 2 rows | Persist checkpoint next offset = 2 |
| Send 3 rows at offset 2, connection drops before ACK | Keep the same batch, retry at **offset 2** |
| Retry returns `OFFSET_ALREADY_EXISTS` | Verify previously ACKed batch/offset, resume from offset 5 |
| Sent offset exceeds next expected position, `OFFSET_OUT_OF_RANGE` | Reconcile against last ACK, resend missing slice; never skip offsets |
| Worker restarts | Reload stream ID, checkpointed offset, and unacknowledged batch |
| An event enters a **different stream** | Offsets cannot prevent cross-stream duplicates; use `event_id`/dedup |
| Multiple writers exist | Enforce one active connection per application-created stream; clear ownership |

When upstream Pub/Sub redelivers messages, map a stable **logical partition** to a stream + checkpoint rather than creating a new stream per request. If a worker loses a stream or pending records, follow a reconciliation runbook instead of blindly re-writing every event to a brand-new stream.

### 8.3. Do Not Equate Exactly-Once Row Delivery with Business Semantics

In-stream exactly-once guarantees that the same offset **is not written twice to that stream**, but it **does not** guarantee the source produced only one event per transaction, or that downstream jobs will not reprocess an event. General rules:

- Every event carries a stable **`event_id`** / source sequence.
- Writers enforce consistent partitioning and checkpointing rules.
- If data enters multiple streams, reports/transformations perform deduplication or `MERGE` by business key.
- `AppendRows` results and Pub/Sub acks are persisted/reconciled for crash recovery.

When cross-system exactly-once adds unnecessary complexity, **default stream + idempotent downstream** is often more practical.

## 9. Pending Streams: Atomic Commit of a Multi-Worker Batch

For end-of-day batches or historical backfills, data often must become visible only when **all** parts have finished loading and validating. Pending streams let a coordinator create multiple streams for workers and **commit them together**.

### 9.1. Required Flow

~~~text
Coordinator:
  CreateWriteStream(type=PENDING) -> stream-A, stream-B
  Assign each stream to a worker.

Worker A:
  AppendRows(stream-A, rows, offset if managed)
  Wait for all ACKs
  FinalizeWriteStream(stream-A) -> row_count_A

Worker B:
  AppendRows(stream-B, rows)
  Wait for all ACKs
  FinalizeWriteStream(stream-B) -> row_count_B

Coordinator:
  Verify row counts, checksums/manifest if applicable
  BatchCommitWriteStreams(parent table, [stream-A, stream-B])
  Confirm no stream_errors
  Publish batch as succeeded
~~~

This is **API flow pseudocode** (not Bash). The corresponding methods in Java `BigQueryWriteClient` are `createWriteStream`, `finalizeWriteStream`, and `batchCommitWriteStreams`. `FinalizeWriteStream` is **mandatory** for pending streams; `BatchCommitWriteStreams` is the step that makes rows queryable.

### 9.2. Data States and Failures

| State | Queryable? | Action |
| --- | --- | --- |
| Appended, not finalized | No | Continue sending / checking ACKs |
| Finalized, not committed | No | Coordinator decides whether to commit or investigate |
| Committed successfully | Yes | Mark batch manifest complete |
| One worker failed | Whole batch not committed yet | Retry failed worker/stream per runbook |
| Timeout / unknown commit status | Do not immediately treat as failed | Check stream state/response and perform idempotent commit retry |

Pending streams have **retention time limits** prior to commit; do not use them as an unbounded queue. Documentation notes that after finalizing, buffered data is retained for up to roughly 4 hours and pending streams must be committed within 24 hours. <https://docs.cloud.google.com/bigquery/docs/write-api-batch-load>

**Comparison with load jobs:** If data is already in Cloud Storage and only needs a batch load, BigQuery load jobs are usually simpler. Use pending streams when coordinating direct multi-worker ingestion requiring an explicit atomic commit.

## 10. Retries, Backpressure, and Dead-Letter Queues

### 10.1. Classify Before Retrying

| Error / Group | Common Causes | How to Handle |
| --- | --- | --- |
| `UNAVAILABLE`, `INTERNAL`, `DEADLINE_EXCEEDED` | Transient / network issues | Exponential backoff + jitter, reconnect, replay per stream semantics |
| `RESOURCE_EXHAUSTED` / 429 | Throughput, connection, or request quotas | Reduce inflight/rate, increase batching, inspect quotas before requesting increases |
| `OFFSET_ALREADY_EXISTS` | Batch already written or offset tracking bug | Verify checkpoint/payload, **never blindly append a new offset** |
| `OFFSET_OUT_OF_RANGE` | Offset gap or prior write failed | Recover from last ACK, backfill missing batch |
| `SCHEMA_MISMATCH_EXTRA_FIELD` | Payload contains a field not yet in schema | Evolve schema first, sync writer, or route to DLQ |
| `INVALID_ARGUMENT` / type mismatch | Data violates schema/format | Do not retry infinitely; quarantine record |
| `PERMISSION_DENIED` | Runtime SA lacks IAM or wrong resource | Fix scoped identity/permissions; never grant broad Editor |
| `NOT_FOUND` | Wrong table/dataset/stream or TTL expired | Verify names, region, stream lifecycle |
| `STREAM_FINALIZED` | Append attempted after finalize | Do not reuse stream; check workflow state |

**Not every timeout means the server failed to write.** On the default stream, retrying can produce duplicates; on a committed stream, retrying the batch at the **same offset** preserves in-stream idempotency.

### 10.2. Backpressure Rules for Pub/Sub Consumers

~~~mermaid
flowchart TD
  MSG["Pull Pub/Sub message"] --> VAL{"Validate schema + event_id?"}
  VAL -- "No" --> DLQ["Quarantine/DLQ\nreason + safe payload reference"]
  VAL -- "Yes" --> BATCH["Assemble batch with byte/row/time limits"]
  BATCH --> APP["AppendRows async"]
  APP --> ACK{"Server ACK?"}
  ACK -- "Yes" --> SAVE["Persist checkpoint/ack Pub/Sub\nper delivery policy"]
  ACK -- "Retryable" --> WAIT["Bounded backoff + jitter\nflow control"] --> APP
  ACK -- "Nonretryable" --> DLQ
  SAVE --> NEXT["Pull next batch"]
~~~

Enforce bounds on **pending batches, in-memory bytes, request deadlines, and concurrency**. When downstream hits quotas, throttle message pulling; if the Pub/Sub backlog grows, ensure capacity/retention is sufficient to avoid data loss. On extended outages, spill batches to durable storage for recovery rather than buffering solely in RAM.

### 10.3. Never Silently Drop Poison Records

Records with invalid schemas, timestamps, or nested fields should go to a DLQ **with error code, event_id, source, and object reference**. Never dump full PII or secrets into Cloud Logging. Maintain an audited repair-and-replay procedure that prevents DLQ replays from introducing duplicates.

## 11. Schema Evolution in Continuously Running Streams

A BigQuery schema can evolve while workers are actively streaming data. For example, adding `firmware_version STRING`:

1. **Expand schema first**: add the new nullable/defaulted field to the BigQuery table.
2. **Wait for schema propagation**: the Storage Write API does not reflect schema changes instantaneously; documentation notes it can take a few minutes.
3. **Update producers**: begin sending the new field only after writers recognize the updated schema.
4. **Monitor errors**: watch for `SCHEMA_MISMATCH_EXTRA_FIELD`, bad types, and serialization failures.
5. **Safe rollback**: stop sending the new field if consumers are not ready; never drop a column actively used by running jobs.

In Java, `JsonStreamWriter` supports **automatic reconnection with the updated schema**, though you still must manage retries/ACKs and producer rollouts. With low-level gRPC, you may need to close and reopen connections when schemas change.

**Do not enable `setIgnoreUnknownFields(true)` by default.** It can silently strip new payload fields, leaving missing data while writes report success. Protect the full pipeline with schema tests and a DLQ.

### 11.1. Critical Data Types

| Field | Payload Sent | Common Errors |
| --- | --- | --- |
| TIMESTAMP | Valid timestamp string / supported format | Wrong timezone, unparseable timestamp |
| FLOAT64 | Valid JSON floating-point number | `NaN`/Infinity or string literal |
| STRING | UTF-8 string | Unauthorized PII, exceeding row/request limits |
| RECORD/REPEATED | Nested/repeated fields matching schema | Missing or mismatched map/list structures |
| NUMERIC/DECIMAL | Exact representation per library | Precision loss from using floats |
| REQUIRED | Non-null value | Missing/null causes failure |

Do not ingest sensitive data without verifying data classification, policy tags, table permissions, and retention policies.

## 12. Throughput, Multiplexing, Quotas, and Costs

### 12.1. Batch and Async Instead of Per-Row Appends

Every `AppendRows` call carries overhead. Grouping **multiple rows into each batch** improves throughput, provided you stay below **request size limits** and pipeline memory/latency budgets. Google recommends larger requests—over 1 MB where appropriate—rather than opening/closing connections per row. <https://docs.cloud.google.com/bigquery/docs/write-api-best-practices>

**Balance:** Overly large batches increase wait time before data becomes visible and complicate failure retries; overly small batches waste overhead. Tune thresholds by **bytes, row count, and max wait time**, measuring p95 ingestion lag and throughput in load tests.

### 12.2. Multiplexing on the Default Stream

- The default stream can use **multiple gRPC connections**.
- Java/Go/Rust clients support **multiplexing/connection pooling** for the default stream, sharing connections across compatible tables/streams.
- Java provides `JsonStreamWriter.newBuilder(...).setEnableConnectionPool(true)`.
- For application-created streams, keep **one active connection per stream**.
- Never create a stream **per message**: `CreateWriteStream` has quotas/rate limits and adds latency.

### 12.3. Quotas to Monitor

| Quota | Risk |
| --- | --- |
| Ingest throughput per project/location | `RESOURCE_EXHAUSTED`, growing backlog |
| Concurrent connections | `AppendRows` rejected when exceeded |
| Application-created stream creation rate | Creating too many streams causes throttling or delays |
| Active stream count | Resource exhaustion if streams are not finalized / TTL-expired |
| Request size, inflight bytes/requests | Serialization errors, timeouts, or flow-control stalls |
| Pending buffer and commit window | Batches unable to commit in time |

Actual quotas depend on location, project, and API mode (gRPC/REST) and may change. Verify [BigQuery quotas](https://docs.cloud.google.com/bigquery/quotas#write-api-limits) in your project before hardcoding numbers into a capacity plan.

### 12.4. End-to-End Pipeline Costs

Costs are not limited to bytes sent through the Storage Write API:

- **Ingestion**: gRPC/REST have different pricing models and free-tier rules per current terms.
- **BigQuery storage**: raw events, partitions, copies, retention, and time travel/backups.
- **Query compute**: bytes scanned or slots; apply partition filters, clustering, and meaningful `LIMIT`s.
- **Pub/Sub/Dataflow/Cloud Run**: buffering, processing, scaling, and retries.
- **Logging/Monitoring/DLQ**: log volume, storage, and operations.
- **Network egress**: data location / cross-region transfers in the architecture.

Estimate ingestion based on **processed data size** and current SKU pricing rather than fixed numbers from old examples. Configure a **Billing Budget** and alerts during testing.

## 13. Observing the Storage Write API via BigQuery and Monitoring

### 13.1. The `WRITE_API_TIMELINE` View

BigQuery provides `INFORMATION_SCHEMA.WRITE_API_TIMELINE[_BY_PROJECT]` showing request/row/byte counts, stream types, and error codes in **one-minute intervals**. Queries must include a **region qualifier** matching the dataset/query region.

~~~sql
-- Read-only; run job in asia-southeast1 (may incur charges)
SELECT
  start_timestamp,
  table_id,
  stream_type,
  error_code,
  SUM(total_requests) AS request_count,
  SUM(total_rows) AS rows_count,
  SUM(total_input_bytes) AS input_bytes
FROM `region-asia-southeast1`.INFORMATION_SCHEMA.WRITE_API_TIMELINE_BY_PROJECT
WHERE start_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 MINUTE)
  AND dataset_id = 'stream_lab'
  AND table_id = 'events'
GROUP BY start_timestamp, table_id, stream_type, error_code
ORDER BY start_timestamp DESC;
~~~

**Note:** This view covers the **gRPC Storage Write API**; it does not replace Cloud Logging or legacy REST metrics. Appropriate IAM metadata and query job permissions are required, and the query must run in the matching region. If no rows appear for the last 30 minutes, widen the time window rather than assuming the API is inactive.

### 13.2. Key Metrics

| Layer | Metric / Observation | Question Answered |
| --- | --- | --- |
| Producer | Events created/s and event size | True incoming volume |
| Pub/Sub | Oldest unacked message age, backlog, redelivery | Is the buffer backing up? |
| Worker | Batch bytes, inflight, retries, ACK latency | Any backpressure or network drops? |
| Storage Write API | Requests/errors by code, rows/s, bytes/s | Quota, schema, or offset errors? |
| BigQuery table | Rows/min by event_ts/ingest_ts, duplicate event_id | Is ingestion complete, accurate, duplicate-free? |
| Business | Active devices, p95 ingestion lag | Are reports meeting SLOs? |
| Cost | Ingest bytes, query bytes, worker hours | Are we within budget? |

**Do not measure request latency by the duration of a long-lived gRPC connection.** For bidirectional streams, the Console may display connection duration; rely on **per-append ACKs, client metrics, and WRITE_API_TIMELINE** to measure request-level latency.

### 13.3. Quick Diagnostics

| Symptom | Verify |
| --- | --- |
| Java `PERMISSION_DENIED` | ADC/runtime SA, BigQuery table `bigquery.tables.updateData` permission, API enabled |
| `INVALID_ARGUMENT` / serialization | JSON fields/types, schema, required fields |
| `SCHEMA_MISMATCH_EXTRA_FIELD` | Was schema expanded? Has writer refreshed? |
| `RESOURCE_EXHAUSTED` | Bytes/s, connections, stream creation rate, flow control |
| `ALREADY_EXISTS` / `OUT_OF_RANGE` | Stream ID, offset checkpoint, batch equality |
| Missing data in reports | Pending not committed, query partition filter, late events |
| Duplicates | Default stream retry, upstream redelivery, multiple streams, source duplicates |
| Pending commit failure | Are streams finalized? `stream_errors`? TTL/buffer limits? |
| Persistent backlog | Producer > ingest capacity, retries, DLQ issues, insufficient workers |
| High query bills | Overly wide partition scans, missing cluster filters, frequent polling SQL |

**Investigation order:** right table/region → IAM → writer/stream type → schema → ACK/error code → checkpoint/retry → Pub/Sub backlog → query/filters → business reconciliation.

## 14. Case Study: IoT System with Late-Arriving Events

**Requirements:** 100,000 devices send one sample per minute, data must appear in reports within a few minutes, and sensors may lose connectivity and replay many older samples.

- **Design A:** Pub/Sub → Dataflow → BigQuery default stream, with a stable `event_id` on every event and downstream deduplication.
- **Design B:** Custom Java workers using committed streams/offsets per logical partition with checkpoints in a durable store.
- **Design C:** Import historical files using load jobs or pending streams when atomic batch visibility is required.

**Trade-offs:** A is easier to scale and operate under at-least-once; B adds complexity for in-stream exactly-once; C fits batches requiring all-at-once visibility on a schedule. For reports that cannot double-count, both A and B still require validating **business event identity** and checking whether the source emits duplicates.

**IoT-specific risk:** A device offline for 12 hours replays events whose `event_ts` is far behind ingest time. If the table partitions by event time, reports querying only "today" will miss late events; define watermark/late-data windows rather than increasing retries.

## 15. Lab: Demonstrating Stream Types

**Prerequisites:** Use a lab project with billing/quotas and appropriate permissions. If no sandbox is available, complete an **offset/batch simulation** without creating billable resources.

### 15.1. Part A — Default Stream Can Produce Duplicates

1. Verify table schema, partitioning, SA, and required APIs.
2. Write two events using the Java code in Section 7.
3. Run a query to inspect the two `event_id` values.
4. Run the program a second time **with the same event IDs** to simulate a replay.
5. Group by `event_id` in SQL to spot duplicates:

~~~sql
SELECT event_id, COUNT(*) AS copies
FROM `LAB_PROJECT_ID.stream_lab.events`
WHERE event_ts >= TIMESTAMP("2026-11-19T00:00:00Z")
  AND event_ts < TIMESTAMP("2026-11-20T00:00:00Z")
GROUP BY event_id
HAVING COUNT(*) > 1
ORDER BY copies DESC;
~~~

Explain why **both appends received ACKs** yet the table still contains duplicates by `event_id`.

### 15.2. Part B — Committed Offsets (Safe Simulation)

Assume a stream with `next_offset = 0`:

| Attempt | Rows | Sent Offset | Expected Result |
| --- | --- | ---: | --- |
| 1 | A, B | 0 | ACK, next = 2 |
| 2 | C | 2 | ACK, next = 3 |
| 3 | C (retry) | 2 | OFFSET_ALREADY_EXISTS |
| 4 | D | 5 | OFFSET_OUT_OF_RANGE |
| 5 | D | 3 | ACK, next = 4 |

Write the checkpoint/ACK logic and describe the case where a worker crashes **after the server writes the batch but before saving the checkpoint**. Explain why retrying with the same offset helps and why `event_id` is still needed across multiple streams.

### 15.3. Part C — Pending Commit

Diagram the flow where a coordinator creates two pending streams, workers append/finalize, and the coordinator commits. Answer: *Can SELECT see rows before commit? If one worker fails, what should the coordinator do? Can a commit be retried after a timeout?* Do not attempt to delete tables or intentionally break production jobs to demonstrate errors.

### 15.4. Part D — Observability and Deliverables

| Evidence | Criteria |
| --- | --- |
| Pipeline architecture | Includes buffer, worker, DLQ, BigQuery |
| Stream choice | Explains at-least-once / exactly-once / pending |
| JSON/schema | Valid types and required fields |
| IAM | Writer SA scoped to table, not Owner |
| ACK/retry | Distinguishes timeouts from permanent errors |
| Batching | Defines byte/row/inflight limits |
| Metrics | Uses WRITE_API_TIMELINE in the right region |
| Duplicates | Explains `event_id` and deduplication query |
| Cost | Accounts for ingestion, storage, queries, workers/logs |
| Cleanup | Leaves shared lab data untouched |

## 16. Review Questions

1. **How does the Storage Write API differ from the Storage Read API?** One ingests rows; the other reads data at high throughput.
2. **Does the default stream require `CreateWriteStream`?** No.
3. **Does the default stream guarantee exactly-once?** No; it is at-least-once, so retries can duplicate rows.
4. **When can queries see rows in a committed stream?** Once the append is acknowledged.
5. **Why do committed offsets enable exactly-once?** The server only accepts appends at the stream's valid next offset.
6. **Does in-stream exactly-once prevent two different streams from writing the same event?** No.
7. **What is the next offset after appending a 7-row batch at offset 12?** 19.
8. **What should you do on `ALREADY_EXISTS`?** Verify the previously written batch/checkpoint before advancing.
9. **What should you do on `OUT_OF_RANGE`?** Reconcile against the last ACK and backfill missing offsets.
10. **When is a pending stream queryable?** After `BatchCommitWriteStreams` succeeds.
11. **Can you keep appending after finalizing a pending stream?** No.
12. **Should buffered streams be used by default for real-time APIs?** No; they are an advanced mechanism.
13. **Does `JsonStreamWriter` send raw JSON directly over the gRPC wire?** No; it converts JSON to protobuf.
14. **Should you create a new stream per HTTP message?** No; that adds overhead and hits stream creation quotas.
15. **Why is a DLQ needed?** To isolate schema-invalid or retry-exhausted records for controlled handling.
16. **Does BigQuery automatically enforce UNIQUE on `event_id`?** No.
17. **Should you run a SQL query every second to measure throughput?** No; use API metrics and monitoring instead.
18. **If an ACK is lost on the default stream, is retrying the same data guaranteed duplicate-free?** No; it can create duplicates.
19. **When a field is added to the schema, can every producer immediately send it?** No; you must wait for schema propagation and writer refresh.
20. **How does partitioning by `event_ts` affect late-arriving data?** Late events land in past partitions, so queries must cover the appropriate window.

## 17. Production Checklist and References

- [ ] Distinguish batch load vs. near-real-time ingest; choose gRPC vs. REST per client capabilities.
- [ ] Define event schema/versioning, `event_id`, UTC timestamps, and late-arrival rules.
- [ ] Select **default** for at-least-once or **COMMITTED + offsets** when in-stream exactly-once is required.
- [ ] For pending streams, coordinator finalizes and atomically commits; monitor stream buffer TTLs.
- [ ] Reuse Java writers/clients, append asynchronously with flow control, and await ACKs before shutdown.
- [ ] Persist stream ID, offset, and batch content durably when using committed streams.
- [ ] Implement bounded retries, exponential backoff/jitter, DLQ, and duplicate-safe replay.
- [ ] Manage schema evolution safely; never enable ignore unknown fields by default.
- [ ] Enforce least-privilege IAM at table/dataset scope with ADC and zero stored JSON keys.
- [ ] Review dataset/table location, partitioning/clustering, and retention policies.
- [ ] Monitor throughput/quotas, p95 ACK latency, Pub/Sub backlog, and write errors.
- [ ] Implement query/ETL deduplication when business events may be duplicated.
- [ ] Configure Billing Budgets and optimize batching, query scans, and logging.
- [ ] Maintain rollout/canary procedures, change audits, and incident runbooks for BigQuery or Pub/Sub.

**Official Google Cloud Documentation:**

- [Storage Write API overview](https://docs.cloud.google.com/bigquery/docs/write-api-intro) — gRPC/REST and selection criteria.
- [Introduction to Storage Write API gRPC](https://docs.cloud.google.com/bigquery/docs/write-api-grpc) — stream types, permissions, protocol.
- [Streaming with Storage Write API](https://docs.cloud.google.com/bigquery/docs/write-api-streaming) — default and committed Java examples.
- [Batch load with pending streams](https://docs.cloud.google.com/bigquery/docs/write-api-batch-load) — finalize, atomic commit, buffer duration.
- [Storage Write API best practices](https://docs.cloud.google.com/bigquery/docs/write-api-best-practices) — throughput, offsets, connection pooling, schema evolution.
- [Storage Write API quotas](https://docs.cloud.google.com/bigquery/quotas#write-api-limits) — request/throughput/connection/stream limits.
- [WRITE_API_TIMELINE information schema](https://docs.cloud.google.com/bigquery/docs/information-schema-write-api) — per-minute stream metrics and error codes.
- [Troubleshooting Storage API](https://docs.cloud.google.com/bigquery/docs/troubleshoot-storage-api) — errors, quotas, and regional issues.
- [BigQuery Java client libraries](https://cloud.google.com/java/docs/reference/google-cloud-bigquerystorage/latest/overview) — Java BigQueryWriteClient/JsonStreamWriter.
- [Control access to BigQuery](https://docs.cloud.google.com/bigquery/docs/control-access-to-resources-iam) — BigQuery IAM roles.
- [Partitioned tables](https://docs.cloud.google.com/bigquery/docs/partitioned-tables) and [Clustered tables](https://docs.cloud.google.com/bigquery/docs/clustered-tables) — query pruning.
- [BigQuery pricing](https://cloud.google.com/bigquery/pricing) — ingestion, storage, and queries.

**Conclusion:** The Storage Write API is a **data ingestion channel**, not an automatic business-level exactly-once engine. The **default stream** suits general streaming where at-least-once is acceptable; **committed streams with offsets** prevent duplicates **within a single stream**; **pending streams** support atomic batch commits. A production pipeline also requires explicit schemas, least-privilege IAM, checkpointing/retries/DLQs, ingestion lag observability, and cost controls.
