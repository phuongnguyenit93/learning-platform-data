# Choosing Dataflow, Dataproc, or BigQuery for Data Transformations

An e-commerce company receives **nightly order files**, **continuous payment events via Pub/Sub**, and terabytes of Parquet data from a legacy Spark system. You can use **BigQuery SQL**, **Dataflow/Apache Beam**, or **Managed Service for Apache Spark (formerly Dataproc)** to transform data; however, each tool is optimized for a different processing model, codebase, and operational footprint.

This lesson belongs to the **Data Pipelines and Processing** chapter of the **CLOUD_PROVIDERS_GCP** module, connecting Cloud Storage, Pub/Sub, IAM, VPC, BigQuery, Java/Cloud Run applications, release automation, and cost monitoring. The goal is to **choose a solution based on measurable requirements**, never assuming one service is universally faster or cheaper.

After this lesson, you will be able to:

- Choose among **BigQuery ELT**, **Dataflow batch/stream**, and **Spark batch/cluster** based on sources, latency, engine, state, and team skills.
- Distinguish *bounded/unbounded*, event time, windows, watermarks, late data, batch replay, and idempotency.
- Build a sample revenue table with **BigQuery GoogleSQL**, alongside equivalent transformations in **PySpark** and **Java Apache Beam**.
- Understand the difference between Dataflow intra-pipeline exactly-once and external side effects, and between serverless Spark and managed clusters.
- Design hybrid architectures separating raw/curated data, backfills, schema evolution, and quality checks.
- Measure correctness, latency, throughput, bytes/slot-ms, backlog, shuffle, CPU, cost, and SLOs to make informed decisions.

> **Lab scope:** project/bucket paths, service accounts, and datasets are illustrative examples. Running BigQuery jobs, Dataflow workers, or Spark batches incurs charges; **never run on production** or spin up clusters solely while reading the lesson. All code samples share the same **data contract** while writing outputs in different formats; only compare performance under identical datasets and measurement conditions.

## 1. Three Engines, Three Strengths

| Criterion | **BigQuery** | **Dataflow** | **Managed Service for Apache Spark (Dataproc)** |
|---|---|---|---|
| Core language | GoogleSQL, Dataform SQLX | Apache Beam Java/Python/Go; templates | Spark SQL, PySpark, Scala, Java |
| Strongest when | Data is already in BigQuery; relational/aggregate SQL transforms | Multi-source ETL/streaming, event time, and complex windows/state | Spark/lakehouse jobs, data lakes, OSS/legacy Spark libraries |
| Batch | Queries/DDL/DML/scheduled runs | Beam bounded pipelines | Spark batch (serverless or cluster) |
| Streaming | **Continuous queries** for supported SQL patterns, still bounded in scope | **Primary streaming design**, Beam unbounded/windowing | Structured Streaming within supported Spark/runtime models; requires checkpoint/capacity management |
| Statefulness and late events | Supported SQL and continuous-query operations; not full Beam | Watermarks, windows, triggers, allowed lateness, state/timers | Spark windows/watermarks/checkpoints depending on mode |
| Infrastructure | No SQL cluster management | Dataflow provisions workers, autoscaling/Streaming Engine | Serverless Spark per job; clusters for deeper self-management |
| Data sources | Native BigQuery; conditional external tables | Pub/Sub, GCS, BigQuery, JDBC, Kafka, and rich I/O connectors | GCS, Parquet/ORC, Iceberg/Hive, BigQuery connector, JDBC |
| Primary billing model | Query compute by on-demand bytes or editions/slots; storage | Worker CPU/RAM, Streaming Engine/shuffle, networking, and storage | Serverless by resources/job; clusters by VMs/disks + management |
| Common pitfalls | Large byte scans, missing partition pruning, costly `MERGE` DML | Late data, unbounded backlogs, duplicate side effects, worker scaling | Shuffle/skew, driver memory, idle cluster cost, dependency/version drift |

**Current product naming (2026):** Google Cloud consolidated **Dataproc** and **Serverless for Apache Spark** under the **Managed Service for Apache Spark** brand. Compatible commands such as `gcloud dataproc batches submit pyspark` and `gcloud dataproc clusters create` **remain in use**. In this lesson, "Dataproc/Spark" refers to this service family and does not imply every Spark batch must run on a VM cluster.

There is no 1:1 substitution: **BigQuery is a SQL warehouse**, **Dataflow is a Beam runner**, and **Spark is a distributed compute engine**. A single architecture can legitimately use all three when workloads truly differ.

## 2. Decision Tree Before Writing a Pipeline

~~~mermaid
flowchart TD
  A["Need to transform data"] --> B{"Is data already in BigQuery?"}
  B -- "Yes" --> C{"Do SQL + batch schedules suffice?"}
  C -- "Yes" --> Q["BigQuery SQL / scheduled query / Dataform"]
  C -- "No" --> D{"Does SQL continuous query support the transform?"}
  D -- "Yes" --> CQ["Consider BigQuery continuous query"]
  D -- "No" --> E{"Need event-time windows, late data, multi-source state/IO?"}
  B -- "No" --> E
  E -- "Yes" --> F["Dataflow / Apache Beam"]
  E -- "No" --> G{"Existing Spark code or lakehouse/OSS Spark needed?"}
  G -- "Yes" --> H["Managed Spark serverless or cluster"]
  G -- "No" --> I["Compare BigQuery load+SQL, Dataflow template, and Spark batch"]
~~~

**Five questions you must answer before choosing:**

1. **Frequency/latency:** once nightly, every 15 minutes, or continuously updated within seconds/minutes?
2. **Sources and sinks:** raw files in Cloud Storage, BigQuery tables, Pub/Sub, Kafka, database CDC, Iceberg lakehouse, or external systems?
3. **Transformations:** relational SQL and aggregations, per-record map/filter, large multi-source joins, ML libraries, or windows/state/event time?
4. **Semantics:** are lost/duplicate events tolerable; how is late data corrected; are replay and duplicate write prevention required?
5. **Operations:** team skills in Java/Beam, Spark, or SQL; quotas, runtime, logging, SLOs, compliance, and total cost?

### Quick Selection Rules

- **BigQuery SQL can do the job** → prefer *in-place* transforms with BigQuery/Dataform or scheduled queries; avoid exporting data to GCS just to read it back into Spark unnecessarily.
- **Pub/Sub/Kafka/CDC with event time and late data**, complex windows → start with Dataflow/Beam; verify source/sink I/O and streaming semantics.
- **Substantial existing Spark SQL/PySpark/Scala code**, Parquet/Iceberg/Hive, custom dependencies → consider Managed Spark, picking **serverless** for periodic jobs and **clusters** for deep OSS/ecosystem tuning or long-running workloads.
- **Simply forwarding JSON messages from Pub/Sub into BigQuery** → evaluate a **Pub/Sub BigQuery subscription** or a Dataflow template before writing custom Beam code.
- **Orchestrating multiple ordered jobs** → use Workflows / Managed Airflow / Cloud Scheduler depending on complexity; **an orchestrator never replaces a data-processing engine**.

## 3. Dataflow: Beam for Both Batch and Streaming

**Apache Beam** defines a pipeline of `PCollection`s and `PTransform`s; **`DataflowRunner`** executes that pipeline on Dataflow. A `PCollection` can be **bounded** (finite files, batch) or **unbounded** (Pub/Sub stream). Not all Beam pipelines behave identically: streaming requires windowing, state, watermark, and dead-letter strategies.

~~~text
Input Pub/Sub (unbounded)
  → parse + validate schema
  → dedup eventId / route invalid to DLQ
  → event-time window + watermark + allowed lateness
  → aggregate / enrich
  → BigQuery (Storage Write API) / GCS / Pub/Sub
                    ↑
       backlog, watermark lag, worker metrics
~~~

### Exactly-Once Does Not Mean "Side Effects Execute Only Once"

Dataflow streaming defaults to **exactly-once processing mode** inside the pipeline; **at-least-once mode** can be chosen to reduce cost/latency when downstream handles duplicates. However:

- Due to retries, a `DoFn` **can execute multiple times**, even concurrently in some scenarios. Outputs are deduplicated within Dataflow's guarantee scope, which **does not** mean an external payment REST API call inside a `DoFn` executes only once.
- For external **sinks** such as Pub/Sub, HTTP, or JDBC, semantics also depend on the connector/sink. The BigQuery Storage Write API supports exactly-once and at-least-once modes **depending on configuration**.
- Pub/Sub can redeliver the same message; do not rely on `messageId` to prevent **business event** duplicates if the producer publishes the same event as two separate messages. Use a stable producer `eventId` and an idempotent sink.
- Pipeline exactly-once **does not replace** unique business keys, upsert/deduplication, outboxes, or data-warehouse reconciliation.

### Event Time, Processing Time, and Watermarks

An order is created at 10:02 but reaches Pub/Sub/Dataflow at 10:17:

| Concept | Value in example | Why it matters |
|---|---|---|
| **Event time** | 10:02 | Order belongs to the 10:00–10:05 business window |
| **Processing time** | 10:17 | When the worker processes the event |
| **Watermark** | Estimated event-time progress | Indicates when most events for a window are expected to have arrived |
| **Allowed lateness** | E.g., 30 minutes | Accepts late events within the configured post-window/watermark interval |
| **Trigger/accumulation** | Early/on-time/late panes | Controls when aggregates emit and whether cumulative totals re-emit |

A 5-minute window may emit an **on-time** result and then **update** when a late event arrives. If the sink simply runs `INSERT` into BigQuery without key/merge semantics, dashboards can double-count across panes. Define the write contract explicitly: **upsert by `(storeId, windowStart, version)`**, append revisions and query the latest, or use a sink with matching mutation semantics.

**When is Dataflow unnecessary?** If the job is simply a nightly `SELECT ... GROUP BY` in BigQuery, Beam adds code and worker ops with no inherent advantage. If the flow only pushes schema-compatible JSON from Pub/Sub into BigQuery, a direct subscription may suffice without custom Dataflow code.

## 4. Managed Spark: Serverless or Cluster?

Managed Service for Apache Spark preserves **Spark DataFrames, Spark SQL, PySpark/Scala/Java**, and compatible JVM/Hive/Iceberg libraries. It is a natural choice when teams already run **Spark on Hadoop/on-prem or a data lake** and are migrating jobs to Google Cloud.

| Model | Choose when | Trade-offs |
|---|---|---|
| **Serverless Spark batches** (`gcloud dataproc batches submit ...`) | Scheduled/ad-hoc jobs; no desire to manage VMs; prefer pay-per-job | Less infrastructure customization than clusters; must standardize artifacts/roles/networking |
| **Managed clusters** (`gcloud dataproc clusters ...`) | Need custom Spark/Hadoop configs, persistent services, HBase/Hive, or custom runtimes | Must manage lifecycle, autoscaling, idle timeouts, and Compute Engine costs |
| **Spark Structured Streaming** | Existing Spark streaming code/checkpoints and matching runtime | Do not assume all modes or serverless batches suit always-on jobs; verify support, checkpoints, and restarts |

Spark parallelizes using **partitions and shuffles**. Two common warning signs:

- `groupBy`/`join` on a heavily skewed key (one store accounts for 90% of events) → **data skew**, a few tasks lag; apply partitioning/repartitioning/key salting as appropriate.
- Small dataset on a large cluster → startup and idle costs exceed the transformation itself. For batch jobs, try serverless, bound workers/executors, and measure total runtime.

**Do not equate Spark with Dataflow:** Spark has Structured Streaming, while Apache Beam on Dataflow provides a distinct windowing/trigger/late-data model. Switching engines requires comparing semantics, watermarks, output modes, checkpoints, and sinks—not just swapping service names.

## 5. BigQuery: ELT/SQL Before Spinning Up Another Engine

Once data is **loaded into BigQuery**, GoogleSQL is usually the shortest path to filter, join, normalize, deduplicate, aggregate, and populate curated tables.

| Task | BigQuery capabilities | Considerations |
|---|---|---|
| Transform staging into curated | `CREATE TABLE AS SELECT`, `INSERT`, `MERGE`, `UPDATE` | Partition filters, bytes scanned, and idempotency |
| Scheduled transformations | **Scheduled queries**, **Dataform**, BigQuery pipelines | Service accounts, dependencies, retries, backfills |
| Reusable aggregations | Materialized views / scheduled aggregate tables | Query rewrites, refresh frequency, freshness, storage |
| Near-real-time SQL | **BigQuery continuous queries** | Supported stateful JOIN/aggregate/window operations remain limited, with Preview features |
| External Parquet data lake | External/BigLake tables or load into native tables | SQL support, storage IAM, and connector performance |
| Complex compute with Spark libraries | Not a direct Spark runtime replacement | Evaluate Managed Spark or Dataflow |

**2026 update:** BigQuery **continuous queries** are no longer limited to simple record filtering; they support certain stateful JOIN, aggregation, and window operations **in Preview**, yet they still **do not** replace full Beam/Spark streaming. Continuous queries carry restrictions on SQL syntax, RLS/column-level security, sources, destinations, and job lifecycles. Neither dismiss BigQuery as "incapable of streaming" nor assume every `MERGE`/`SELECT DISTINCT` works unchanged inside a continuous query.

**SLOs and cost:** BigQuery query jobs consume compute billed via **on-demand bytes** or **editions/slots**, alongside storage, query-result caching, scan, and DML overhead. Apply partition pruning, clustering, column projection, maximum-bytes-billed caps, and inspect `INFORMATION_SCHEMA.JOBS` before buying more slots.

## 6. Shared Lab: One Order Contract Across Three Engines

We transform an **8-row** CSV file containing one duplicate event, one cancelled order, one refunded order, and one invalid `amount_minor < 0` row. The desired output is **valid PAID order revenue by date and store**.

**Input contract:**

| Field | Type | Rule |
|---|---|---|
| `event_id` | STRING | Stable producer ID; retries must keep identical ID and payload |
| `order_id` | STRING | Business order ID, distinct from message ID |
| `event_ts` | TIMESTAMP UTC | Event occurrence time, not file upload time |
| `store_id` | STRING | Store eligible to record revenue |
| `amount_minor` | INT64 | Integer in minor currency units; must be positive for `PAID` |
| `status` | STRING | `PAID` / `CANCELLED` / `REFUNDED` |

This is a **simplified event stream**. Real systems handle order state transitions, partial refunds, multiple currencies, and late adjustments. Currency rules and business logic must be defined explicitly; never sum all `PAID` rows as an official financial ledger.

### Step 1 — Create the Sample Data File

Save `orders.csv` in your lab directory:

~~~csv
event_id,order_id,event_ts,store_id,amount_minor,status
e-001,O-1001,2026-11-18T09:00:00Z,store-a,12500,PAID
e-002,O-1002,2026-11-18T09:01:00Z,store-a,5900,PAID
e-003,O-1003,2026-11-18T09:02:00Z,store-b,3000,CANCELLED
e-004,O-1004,2026-11-18T09:03:00Z,store-b,8900,PAID
e-004,O-1004,2026-11-18T09:03:00Z,store-b,8900,PAID
e-005,O-1005,2026-11-18T09:04:00Z,store-b,2500,PAID
e-006,O-1006,2026-11-18T09:05:00Z,store-a,1000,REFUNDED
e-007,O-1007,2026-11-18T09:06:00Z,store-a,-100,PAID
~~~

**Expected output** after removing duplicate `e-004`, dropping `CANCELLED`/`REFUNDED`, and rejecting invalid amounts:

| sale_date | store_id | paid_orders | revenue_minor |
|---|---|---:|---:|
| 2026-11-18 | store-a | 2 | 18,400 |
| 2026-11-18 | store-b | 2 | 11,400 |

**Validation invariants:** total valid `PAID` orders after deduplication is **4**, and total revenue is `29,800` minor units. There are **7 distinct `event_id`s** across 8 rows, including 1 invalid amount; a duplicate with **conflicting payloads** violates the producer contract and must be quarantined and alerted on rather than arbitrarily picked.

### Step 2 — Prepare GCS and BigQuery for Your Chosen Lab Track

~~~bash
PROJECT_ID="my-data-pipelines-lab"
REGION="asia-southeast1"
BUCKET="my-data-pipelines-lab-unique-bucket"
DATASET="pipeline_lab"

gcloud config set project "$PROJECT_ID"
gcloud services enable storage.googleapis.com bigquery.googleapis.com

# Create a new bucket/dataset only if absent and authorized.
gcloud storage buckets create "gs://$BUCKET" --location="$REGION"
bq --location="$REGION" mk --dataset "$PROJECT_ID:$DATASET"
gcloud storage cp orders.csv "gs://$BUCKET/raw/orders.csv"
~~~

Bucket names are **globally unique**; the name above is a placeholder. Keep **Cloud Storage, BigQuery dataset, and processing region** aligned with organizational residency/egress policies; a dataset cannot change location after creation. Each lab track below is an **alternative option**—you do not need to run all three and pay three times.

## 7. Option A — BigQuery SQL: Shortest Path When BigQuery Is the Destination

Once the file is in Cloud Storage, run a **load job** into a raw table and then a GoogleSQL transformation. This suits **hourly/daily** schedules or pipelines whose data already resides in BigQuery; you do not need a Spark cluster just to compute `GROUP BY`.

### Step A1 — Load CSV with an Explicit Schema

~~~bash
bq --location="$REGION" load \
  --source_format=CSV \
  --skip_leading_rows=1 \
  --replace \
  "$PROJECT_ID:$DATASET.raw_order_events" \
  "gs://$BUCKET/raw/orders.csv" \
  "event_id:STRING,order_id:STRING,event_ts:TIMESTAMP,store_id:STRING,amount_minor:INT64,status:STRING"
~~~

`--replace` is only for **reproducible labs**, as it overwrites the table if present. In production, keep raw data immutable, load by batch ID/date, and record source metadata and ingestion time. A completed load job **does not mean business data is valid**; run validation next.

### Step A2 — Verify Duplicates and Invalid Data

Run in BigQuery Studio in `asia-southeast1`, replacing `MY_PROJECT` with your lab project:

~~~sql
SELECT COUNT(*) AS raw_rows,
       COUNT(DISTINCT event_id) AS distinct_event_ids,
       COUNTIF(amount_minor <= 0) AS invalid_amount_rows
FROM `MY_PROJECT.pipeline_lab.raw_order_events`;

-- An event ID with CONFLICTING payloads requires quarantine.
SELECT event_id,
       COUNT(DISTINCT TO_JSON_STRING(STRUCT(
         order_id, event_ts, store_id, amount_minor, status
       ))) AS payload_variants
FROM `MY_PROJECT.pipeline_lab.raw_order_events`
GROUP BY event_id
HAVING payload_variants > 1;
~~~

Expect the first query to return `8, 7, 1`, and the conflict query to return **0 rows**. With real sources, build a **quarantine table** capturing error reason, source, file/offset, and ingest time rather than silently dropping bad rows without a trace.

### Step A3 — CTAS with Deduplication, Filtering, and Aggregation

~~~sql
CREATE OR REPLACE TABLE `MY_PROJECT.pipeline_lab.daily_store_sales`
PARTITION BY sale_date
CLUSTER BY store_id
AS
WITH ranked AS (
  SELECT
    event_id, order_id, event_ts, store_id, amount_minor, status,
    ROW_NUMBER() OVER (
      PARTITION BY event_id
      ORDER BY event_ts DESC, order_id DESC
    ) AS rn
  FROM `MY_PROJECT.pipeline_lab.raw_order_events`
  WHERE event_id IS NOT NULL
)
SELECT
  DATE(event_ts) AS sale_date,
  store_id,
  COUNT(*) AS paid_orders,
  SUM(amount_minor) AS revenue_minor
FROM ranked
WHERE rn = 1 AND status = 'PAID' AND amount_minor > 0
GROUP BY sale_date, store_id;

SELECT sale_date, store_id, paid_orders, revenue_minor
FROM `MY_PROJECT.pipeline_lab.daily_store_sales`
ORDER BY sale_date, store_id;
~~~

On the sample data, output matches the table in Section 6. `ROW_NUMBER()` suffices for **identical duplicates** in the lab; in production, if one `event_id` has **two differing payloads**, quarantine before running the query—arbitrary tie-breaking hides billing bugs. If the source emits CDC updates, use explicit version/sequence columns and `MERGE` by business key instead of treating an event ID as latest record state.

**Idempotency:** `CREATE OR REPLACE TABLE ... AS SELECT` recomputes from full raw data, so re-running over **unchanged** inputs yields identical output. For TB-scale tables and incremental loads, replace this with **partitioned staging + `MERGE` on batch/event keys**, pruning affected partitions and validating unique keys before `MERGE`; scanning full history hourly is expensive.

### Step A4 — Scheduling / Dataform

- **Scheduled query:** uses BigQuery Data Transfer Service to run SQL hourly/daily under an SA with query/write permissions, managing schedules and preventing overlapping runs/backfills.
- **Dataform:** declares a SQLX DAG from raw → validated → daily sales with assertions for unique keys, non-nulls, and valid ranges; ideal when multiple SQL transforms depend on each other.
- **BigQuery continuous query:** evaluate when data streams into BigQuery and transforms fall within supported capabilities; never assume CTAS, `ROW_NUMBER`, or `MERGE` above runs verbatim as a continuous query.

**Limitations:** BigQuery is an analytics engine; fresh OLTP data may require CDC/ingestion and propagation time. Never use the `daily_store_sales` dashboard to confirm payment immediately after commit when business logic requires strongly consistent OLTP reads.

## 8. Option B — Managed Spark: PySpark for Data Lakes and Batch Jobs

Spark fits well when CSV is just part of a **Parquet/ORC lakehouse**, when joining multiple datasets outside BigQuery, when existing PySpark/JVM libraries are used, or when standardizing on one engine across platforms.

Save **`orders_etl.py`** in your lab project, taking GCS URIs as input and output:

~~~python
import sys
from pyspark.sql import SparkSession, functions as F, types as T

if len(sys.argv) != 3:
    raise SystemExit("Usage: orders_etl.py INPUT_CSV OUTPUT_PARQUET")

input_uri, output_uri = sys.argv[1], sys.argv[2]
spark = SparkSession.builder.appName("orders-daily-sales").getOrCreate()

schema = T.StructType([
    T.StructField("event_id", T.StringType(), False),
    T.StructField("order_id", T.StringType(), False),
    T.StructField("event_ts", T.TimestampType(), False),
    T.StructField("store_id", T.StringType(), False),
    T.StructField("amount_minor", T.LongType(), False),
    T.StructField("status", T.StringType(), False),
])

raw = (
    spark.read.option("header", "true")
    .option("mode", "FAILFAST")
    .schema(schema)
    .csv(input_uri)
)

# Valid for lab only: rows sharing event_id have identical payloads.
# In production, detect conflicting events and quarantine before deduplicating.
deduped = raw.dropDuplicates(["event_id"])

daily = (
    deduped.filter(
        (F.col("status") == "PAID") & (F.col("amount_minor") > 0)
    )
    .withColumn("sale_date", F.to_date("event_ts"))
    .groupBy("sale_date", "store_id")
    .agg(
        F.count(F.lit(1)).alias("paid_orders"),
        F.sum("amount_minor").alias("revenue_minor"),
    )
)

daily.orderBy("sale_date", "store_id").show(truncate=False)
# Overwrite ONLY a dedicated LAB output path.
daily.write.mode("overwrite").parquet(output_uri)
spark.stop()
~~~

**Key points to remember:** `dropDuplicates(["event_id"])` requires shuffle/state; if rows sharing an ID differ in payload, Spark **does not guarantee which row wins** without an explicit business sequence. At TB scale, monitor **shuffle read/write, skew, partition count, and executor memory**. `FAILFAST` catches parse errors only; business validation such as negative amounts should still route to quarantine instead of being silently dropped.

### Submitting the Serverless Spark Batch

After the platform team provisions a **runtime service account** with proper roles (e.g., `roles/dataproc.worker` and bucket read/write permissions), upload the script to GCS:

~~~bash
gcloud services enable dataproc.googleapis.com \
  --project="$PROJECT_ID"

SPARK_SA="spark-batch@$PROJECT_ID.iam.gserviceaccount.com"
gcloud storage cp orders_etl.py "gs://$BUCKET/code/orders_etl.py"

gcloud dataproc batches submit pyspark \
  "gs://$BUCKET/code/orders_etl.py" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --service-account="$SPARK_SA" \
  --batch="orders-etl-lab-001" \
  -- \
  "gs://$BUCKET/raw/orders.csv" \
  "gs://$BUCKET/out/spark-daily-sales/"

# Inspect the batch after submission/run; do not confuse batch ID with cluster name.
gcloud dataproc batches describe orders-etl-lab-001 \
  --project="$PROJECT_ID" --region="$REGION"
~~~

Batch names must be **unique within scope**; if the ID already exists, pick a new ID after checking prior results. This is a **Managed Spark serverless batch** and creates no persistent VM cluster. For cluster execution, flags, startup/shutdown, autoscaling, and billing differ; never use `batches submit` as if managing a VM cluster.

**PySpark result:** two rows with `store-a = (2, 18400)` and `store-b = (2, 11400)`. The output path is a **Parquet directory** containing part files, not a single CSV file. To query it natively in BigQuery, use the **BigQuery connector** or a load job; writing Parquet to GCS **does not automatically create** a BigQuery table.

## 9. Option C — Dataflow / Java Apache Beam for Batch

Beam fits well when the same system must also process a **Pub/Sub stream** with event-time windows, or when the team has reusable Java/Beam transforms. First run a **bounded pipeline** over the same GCS CSV to compute store/date revenue totals for comparison with BigQuery/Spark.

The example below uses **Java 17** and a Dataflow-compatible Beam Java SDK. In a standard Beam Maven project, include `beam-sdks-java-core`, `beam-sdks-java-io-google-cloud-platform`, `beam-runners-google-cloud-dataflow-java`, and an execution plugin (such as Maven Exec Plugin) **all pinned to a Dataflow-supported Beam SDK version**. Never mix mismatched SDK and runner versions.

**`src/main/java/example/SalesBeam.java`**

~~~java
package example;

import org.apache.beam.runners.dataflow.options.DataflowPipelineOptions;
import org.apache.beam.sdk.Pipeline;
import org.apache.beam.sdk.io.TextIO;
import org.apache.beam.sdk.options.Description;
import org.apache.beam.sdk.options.PipelineOptionsFactory;
import org.apache.beam.sdk.options.Validation;
import org.apache.beam.sdk.transforms.Distinct;
import org.apache.beam.sdk.transforms.DoFn;
import org.apache.beam.sdk.transforms.Filter;
import org.apache.beam.sdk.transforms.MapElements;
import org.apache.beam.sdk.transforms.ParDo;
import org.apache.beam.sdk.transforms.Sum;
import org.apache.beam.sdk.values.KV;
import org.apache.beam.sdk.values.TypeDescriptors;

public final class SalesBeam {
    public interface Options extends DataflowPipelineOptions {
        @Description("CSV file input, including header")
        @Validation.Required
        String getInput();
        void setInput(String value);

        @Description("Cloud Storage output prefix")
        @Validation.Required
        String getOutputPrefix();
        void setOutputPrefix(String value);
    }

    public static void main(String[] args) {
        Options opts = PipelineOptionsFactory.fromArgs(args)
            .withValidation().as(Options.class);
        Pipeline p = Pipeline.create(opts);

        p.apply("ReadCSV", TextIO.read().from(opts.getInput()))
         .apply("SkipHeader", Filter.by(
             (String line) -> !line.startsWith("event_id,")))
         // Deduplicates IDENTICAL lines in the lab only.
         // Production requires deduplicating by event_id and flagging payload conflicts.
         .apply("DeduplicateExactRows", Distinct.create())
         .apply("ValidateAndMap", ParDo.of(
             new DoFn<String, KV<String, Long>>() {
                 @ProcessElement
                 public void process(
                         @Element String line,
                         OutputReceiver<KV<String, Long>> out) {
                     // Simple CSV: assumes no commas inside quoted fields.
                     // Production: use a proper parser/schema and a DLQ for malformed rows.
                     String[] c = line.split(",", -1);
                     if (c.length != 6) {
                         throw new IllegalArgumentException("Malformed CSV");
                     }
                     long amount = Long.parseLong(c[4]);
                     if (!"PAID".equals(c[5]) || amount <= 0) {
                         return;
                     }
                     String saleDate = c[2].substring(0, 10);
                     String key = saleDate + "," + c[3];
                     out.output(KV.of(key, amount));
                 }
             }))
         .apply("SumByDateStore", Sum.longsPerKey())
         .apply("AsCSV", MapElements
             .into(TypeDescriptors.strings())
             .via((KV<String, Long> kv) ->
                 kv.getKey() + "," + kv.getValue()))
         // Single output file for tiny lab ONLY; production should use sharding.
         .apply("WriteCSV", TextIO.write()
             .to(opts.getOutputPrefix())
             .withSuffix(".csv")
             .withoutSharding());

        p.run().waitUntilFinish();
    }
}
~~~

Unlike the first two labs, the Beam output here includes only **`sale_date,store_id,revenue_minor`** (omitting `paid_orders`). The aim is to demonstrate `PTransform`/`KV`/`Sum.longsPerKey` and verify **matching total revenue**; to include counts, combine `Count.perKey` or use a custom `CombineFn` with `(count, amount)` values. **Never compare an intentionally omitted column against another engine's count and conclude an engine is wrong**.

**Limitations of the minimal example:** `Distinct.create()` only removes **exact string duplicates** and triggers a shuffle; it cannot catch matching `event_id`s with differing amounts. `ParDo` throws on malformed CSV, causing retries/failures; production pipelines must route bad records to a **dead-letter output** with error reasons. `withoutSharding()` limits write parallelism; remove it for large datasets.

### Run Beam Locally First, Then Submit to Dataflow

In a Maven project configured with the SDK, I/O, Dataflow runner, and exec plugin:

~~~bash
# Local bounded run: creates no Dataflow workers.
mvn -q compile exec:java \
  -Dexec.mainClass=example.SalesBeam \
  -Dexec.args="--runner=DirectRunner --input=orders.csv --outputPrefix=out/sales"

# Remote Dataflow: requires worker SA, temp/staging bucket, and IAM first.
DF_SA="dataflow-worker@$PROJECT_ID.iam.gserviceaccount.com"
mvn -q -Pdataflow-runner compile exec:java \
  -Dexec.mainClass=example.SalesBeam \
  -Dexec.args="--runner=DataflowRunner --project=$PROJECT_ID --region=$REGION --gcpTempLocation=gs://$BUCKET/tmp --serviceAccount=$DF_SA --input=gs://$BUCKET/raw/orders.csv --outputPrefix=gs://$BUCKET/out/beam/sales"
~~~

**Prerequisites:** `DirectRunner` requires `beam-runners-direct-java` in the local profile; the Dataflow runner profile must exist in `pom.xml`. The commands above **do not create those Maven profiles automatically**. On Dataflow, the worker SA needs worker, input-read, and staging/output-write permissions, while the launcher needs job-creation permissions and `iam.serviceAccounts.actAs` on the worker SA. Dataflow workers usually run inside a project VPC; networking, subnets, firewalls, and private access to Google APIs must also be configured.

Expected output (row order may vary):

~~~csv
2026-11-18,store-a,18400
2026-11-18,store-b,11400
~~~

### If You Need Real Streaming: Choose Custom Beam or a Template

Turning a bounded pipeline into streaming **is not as simple as adding `--streaming=true`** and keeping an unbounded `Distinct.create()`: maintaining a set of seen IDs over an infinite stream grows state unboundedly without windows/TTLs. You must specify:

1. `PubsubIO.read...` source and event timestamp attribute / event-time parsing.
2. `Window.into(FixedWindows...)`, watermarks, allowed lateness, and early/late firings.
3. Deduplication by `event_id` with bounded state expiry/windows and a late-arrival contract; never rely on message ordering.
4. A sink with explicit semantics (such as BigQuery Storage Write API), business keys, and window revision upserts.
5. DLQ/quarantine, backlog monitoring, and replay from durable storage.

For flows **merely moving JSON from Pub/Sub into BigQuery**, evaluate Google-provided templates before writing custom code:

~~~bash
# Example only: requires pre-created subscription/tables/schema,
# and runs as STREAMING until drained or canceled.
gcloud dataflow jobs run "orders-pubsub-to-bq-lab" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --gcs-location="gs://dataflow-templates/latest/PubSub_Subscription_to_BigQuery" \
  --staging-location="gs://$BUCKET/staging" \
  --parameters="inputSubscription=projects/$PROJECT_ID/subscriptions/orders-events-sub,outputTableSpec=$PROJECT_ID:$DATASET.raw_order_events"
~~~

This template requires **Pub/Sub JSON payloads matching an existing BigQuery table schema**; it does not build `daily_store_sales` or apply the lab's deduplication/aggregation rules automatically. It can create a dead-letter table depending on flags. For light JSON filtering/transforms, evaluate template UDFs or a Pub/Sub **BigQuery subscription** before building custom Dataflow streaming.

**Stopping criteria:** a continuous streaming job **incurs charges even with zero messages**. For controlled shutdown, check status and choose **drain** (attempts to finish in-flight work where supported) or **cancel** (stops quickly, requiring reconciliation/replay):

~~~bash
gcloud dataflow jobs list --project="$PROJECT_ID" --region="$REGION"
# Never run drain/cancel before verifying the exact JOB_ID and owner.
~~~

## 10. Comparing Outputs and Traits Across the Three Labs

| Output or trait | BigQuery SQL | Spark PySpark | Dataflow Beam Java |
|---|---|---|---|
| Input | BigQuery raw table from CSV | CSV on GCS | CSV on GCS |
| Lab deduplication | `ROW_NUMBER` by `event_id` | `dropDuplicates(event_id)` | `Distinct` by **entire line** |
| Filter | `status=PAID`, positive amount | Equivalent | Equivalent |
| Output | Partitioned BigQuery table | GCS Parquet directory | GCS CSV file |
| `store-a` revenue | **18,400** | **18,400** | **18,400** |
| `store-b` revenue | **11,400** | **11,400** | **11,400** |
| Paid count | 2 + 2 | 2 + 2 | Omitted in example |
| Reruns | CTAS replaces output table | Overwrites output prefix | `TextIO` needs a new output path / cleanup |
| Streaming capability | Dedicated SQL continuous queries | Structured Streaming per runtime | Beam unbounded pipelines with windows/state |

**Never conclude which engine is fastest from an 8-row file.** Startup/worker overhead can dwarf processing CPU; valid benchmarks use realistic data volumes, matching business semantics, and controlled input locations, concurrency, and caching.

## 11. Designing Hybrid Architectures by Data Workload

An enterprise does not need to force a single engine onto every data source:

~~~mermaid
flowchart LR
  F["GCS: nightly sales files"] --> L["BigQuery load job"]
  L --> S["BigQuery SQL / Dataform"]
  P["Pub/Sub: real-time events"] --> D["Dataflow Beam streaming"]
  D --> R["BigQuery raw events"]
  R --> S
  K["Lake Parquet / legacy Spark jobs"] --> SP["Managed Spark batch"]
  SP --> O["GCS curated Parquet / BigQuery"]
  O --> S
  S --> V["BigQuery marts / BI dashboards"]
  M["Workflows / Scheduler / Airflow"] --> L
  M --> SP
  M --> S
~~~

**The raw → validated → curated principle:**

1. **Raw/landing:** preserve original records, `event_id`, source offset/file URI, ingest timestamp, and schema version so failed pipelines can always re-read source data.
2. **Validated/quarantine:** isolate bad schemas, currency errors, missing IDs, negative amounts, and conflicting `event_id`s; never silently "drop all errors" and report success.
3. **Curated:** deduplicated transforms with explicit business rules, written by batch ID/partition for easy verification and replay.
4. **Marts:** aggregated `daily_store_sales` tables with clearly published freshness for BI; never use them as authoritative OLTP payment confirmation.

**Orchestration vs. processing:** Cloud Scheduler triggers periodic runs; Workflows or Managed Airflow expresses dependencies `load → validate → aggregate → check → publish`. Dataflow, Spark, and BigQuery perform the actual distributed data processing. Eventarc/Pub/Sub triggers can deliver duplicate events, so orchestrators must pass a **run ID / batch ID** to prevent launching two concurrent jobs that overwrite each other.

### Handling Late Data and Backfills

- **BigQuery:** retain raw events, reprocess **affected partitions**, and use scoped `MERGE`/CTAS with business sequence keys. Never run hourly full-table scans to backfill 3 years of history.
- **Dataflow:** configure watermarks, allowed lateness, triggers, and state retention; route events arriving past allowed lateness to DLQ/backfill rather than expecting dashboards to self-heal implicitly.
- **Spark:** write **versioned or partitioned** batch outputs and retain checkpoints/job inputs for GCS replay. Structured Streaming requires a **durable checkpoint location** and sink upsert/deduplication semantics.
- **All engines:** prevent two writers from executing concurrent `overwrite`s on retries; use staging + validation + atomic publish/view swaps where supported.

## 12. IAM, Networking, and Sensitive Data

**Deployer/orchestrator identity differs from runtime identity.** An account permitted to submit jobs does not automatically grant workers GCS read or BigQuery write access; conversely, granting workers bucket read access does not let them alter pipeline code.

| Component | Runtime identity and typical required roles | Do NOT grant |
|---|---|---|
| **BigQuery scheduled query / Dataform execution** | SA with `bigquery.jobs.create` in the billing project, source read, target write | Project Owner to SQL analysts |
| **Dataflow workers** | Worker SA with worker role, Storage Object Viewer/Creator on exact paths/buckets, Pub/Sub Subscriber, BigQuery write if needed | Project-wide Editor just to read GCS |
| **Managed Spark serverless** | Batch workload SA with Dataproc Worker per product requirements, GCS permissions, BigQuery roles if using connector | Default Compute Admin for every Spark job |
| **CI/CD launcher** | Deploy/job-create roles and `iam.serviceAccounts.actAs` on approved workload SAs | Service Account Token Creator across all SAs |
| **Operations/SRE** | Job/metrics/log reader; stop/drain/delete permissions only when assigned | PII read access when only metrics are needed |

Network controls:

- Workers and managed Spark typically reach Cloud Storage, BigQuery, Pub/Sub, and service APIs; in a **private subnet**, verify **Private Google Access / Private Service Connect for Google APIs**, routes, firewalls, DNS, VPC Service Controls, and NAT if internet access is needed.
- For **cross-project GCS/BigQuery**, grant IAM to the **exact workload SA** on the resource project—not a developer's account or the Compute Engine default SA.
- Banking/PII data requires encryption, retention policies, CMEK where mandated, tenant partitioning / authorized views, audit logs, and **never printing raw payloads, secrets, or access tokens** to worker logs.
- JDBC/SQL connectors must use Secret Manager / short-lived credentials, TLS, and proper network paths; never embed DB passwords in command args or source code.

**Note on BigQuery row-level/column-level policies:** policies apply to queries based on the caller's identity. Never disable security policies just to make Spark or Dataflow run faster; use a properly scoped service account or design appropriate data products / authorized views.

## 13. Reliability, Performance, and Total Cost

### Measuring Against the Same Dataset

Hold input size, schema, partitioning, region, output format, deduplication rules, error record counts, and output freshness constant. Measure **from launch until output validation passes**, not just core transform duration:

| Dimension | BigQuery | Dataflow | Managed Spark |
|---|---|---|---|
| Latency | Job creation/elapsed time, query stages | Job startup, system lag/watermark lag (stream), end-to-end latency | Batch startup, driver/executor runtime |
| Throughput | Bytes processed, rows/s, slot-ms | Elements/s, input bytes, worker CPU, backlog | Records/s, shuffle bytes, stages/tasks |
| Correctness | Duplicates/quarantine, reconciliation SQL | Late/invalid counts, watermarks, DLQ, sink errors | Invalid records, dedup conflicts, stage retries |
| Scale bottleneck | Partition pruning, JOIN shuffle, slot contention | Hot keys, state size, slow transforms, Pub/Sub backlog | Skew, partition count, shuffle spill/OOM |
| Costs | On-demand bytes/slots, storage, DML | CPU/RAM, Streaming Engine/shuffle, VM/network, I/O | Serverless compute/DCUs/shuffle or cluster VM uptime |

**Qualitative end-to-end cost formula:**

~~~text
Total cost = ingest + source/storage + compute
           + shuffle/streaming state + network/egress
           + sink writes + logging/monitoring + operations
~~~

- Dataflow streaming runs **persistent workers**; never estimate cost from daily event count while ignoring idle hours, Streaming Engine, shuffle, and state.
- Managed Spark **serverless** optimizes intermittent jobs by billing per run; **clusters** also incur VM/disk and idle time if not torn down. Never assume serverless is always cheaper at 24/7 utilization.
- BigQuery SQL is simple and inexpensive when data already lives in the warehouse, but repeated TB scans or unpruned `MERGE`s grow expensive quickly; a misconfigured scheduled query can repeat that cost daily.
- Cross-region/cross-project movement can incur **network egress** and residency issues; co-locate pipelines and sinks in the same region whenever feasible.

### Sample SLOs for Three Workloads

| Workload | SLO to verify | Best tool to try first |
|---|---|---|
| CSV files arrive at 02:00; report due by 03:00 | Job finishes P95 under 1 hour, reconciliation passes | BigQuery load + SQL/Dataform |
| Pub/Sub orders require alerting within 30 seconds | End-to-end event lag P95 under 30 seconds, late-data contract | Dataflow streaming |
| Terabytes of Parquet + legacy Spark libraries on weekends | Batch completes within 3 hours with zero post-job cluster idle time | Managed Spark serverless or autoscaling cluster |

Every SLO requires **alert thresholds, an owner, and a remediation plan**. Never track `job SUCCEEDED` alone when business outputs are wrong or 0.1% of events are missing.

## 14. Error Runbook and Remediation

| Symptom | Common cause | Priority investigation steps |
|---|---|---|
| BigQuery `PERMISSION_DENIED` on load/query | Job SA lacks `jobUser`/`dataViewer`/`dataEditor` on target project/dataset | Check job principal and dataset IAM |
| BigQuery `Not found: Dataset ... location` | Dataset and query job regions differ | Dataset location, job location |
| BigQuery report shows duplicates | Re-run append, duplicate event IDs, wrong `MERGE` key | Raw duplicates, input batch ID, curated uniqueness |
| BigQuery bill / query time spikes | Full table scan, missing partition filter, large JOIN shuffle | `INFORMATION_SCHEMA.JOBS`, query plan, bytes/slot-ms |
| Dataflow `RUNNING` but output unchanged | No incoming events, watermark lag, sink errors, backlog | Worker logs, input subscriptions, system lag, dead letters |
| Dataflow duplicates after retry | Non-idempotent external side effect/sink, producer republish | Event ID, sink semantics, deduplication state |
| Dataflow windows emit late / wrong counts | Timestamp assignment, watermark, allowed lateness/triggers | Window config and pane/retraction strategy |
| Dataflow workers cannot reach storage | Worker SA missing IAM or VPC/DNS/Private Google Access | Service account, network path, API errors |
| Spark batch `FAILED` / Python dependency error | Runtime version, package/JAR, Python mismatch | Driver logs, batch runtime config, artifacts |
| Spark job slow / OOM | Skew, shuffle spill, partition count / driver memory | Spark UI stages, executors, shuffle/skew metrics |
| Spark output empty | Wrong GCS URI, filter dropped all rows, schema cast failure | Input row count/schema and transformation stages |
| All three outputs disagree | Differing dedup, timezone, currency, or late-data semantics | Compare by `event_id` + data contract, not totals alone |

### Read-Only Inspection Commands

~~~bash
# Dataflow:
gcloud dataflow jobs list --project="$PROJECT_ID" --region="$REGION"

# Managed Spark batches:
gcloud dataproc batches list --project="$PROJECT_ID" --region="$REGION"
gcloud dataproc batches describe orders-etl-lab-001 \
  --project="$PROJECT_ID" --region="$REGION"

# BigQuery:
bq --location="$REGION" ls "$PROJECT_ID:$DATASET"
bq --location="$REGION" show "$PROJECT_ID:$DATASET.daily_store_sales"
~~~

For BigQuery query jobs, inspect `INFORMATION_SCHEMA.JOBS_BY_PROJECT` in the matching region to analyze `total_bytes_processed`, `total_slot_ms`, and `error_result`. For Dataflow, monitor per-job/per-worker **backlog and system lag**—far more informative than `RUNNING` status alone. For Spark, inspect **driver logs and Spark UI**, not just job state.

## 15. Zero-Disruption Migration and Rollout

1. **Inventory:** sources, sinks, schemas, dependencies, partitions, watermarks/checkpoints, IAM/locations, and current spend.
2. **Golden dataset:** build test inputs with duplicate event IDs, late events, null fields, negative amounts, malformed schemas, timezone boundaries, and edge business cases.
3. **Parallel shadow run:** the new engine writes to a **separate dataset/output prefix**, never overwriting curated production. Reconcile event IDs, record counts, and revenue per partition.
4. **Canary:** route a slice of data or one store/partition; measure correctness, P95 latency, backlog/shuffle, cost, and downstream load.
5. **Cutover:** switch the scheduler/orchestrator or view/table alias once validation passes; confirm two writers never publish simultaneously.
6. **Rollback:** revert to the still-available old output/engine and replay from raw using event IDs/batch IDs; never delete checkpoints or Pub/Sub subscriptions before accounting for backlogged data.
7. **Cleanup:** stop old jobs/clusters/streaming pipelines **owned by your team**, delete authorized lab resources, and audit granted IAM roles.

**If migrating Spark → BigQuery**, verify SQL dialect differences, null handling, timezones, duplicate ordering, UDFs, decimal precision, and transaction semantics. **If migrating Spark Structured Streaming → Beam**, review windows/watermarks/output modes and state retention before switching; identical results on a batch test do not prove identical behavior on late events.

## 16. Pre-Production Checklist

- [ ] Sources/sinks, schemas, business keys, event time, and timezone are documented.
- [ ] Workload classified as batch, micro-batch, or streaming with an end-to-end SLO target.
- [ ] BigQuery SQL evaluated before building Dataflow/Spark for simple aggregations.
- [ ] Streaming pipelines define watermarks, late-event handling, deduplication, and sink idempotency.
- [ ] Raw retention, replay/backfill, DLQ/quarantine, and schema evolution plans exist.
- [ ] Unbounded streams never use unbounded `Distinct.create()`.
- [ ] Spark batches use versioned artifacts, proper networking/SA, and shuffle/skew/output controls.
- [ ] BigQuery tables are partitioned/clustered for query patterns, transforms tested, and scans capped.
- [ ] Runtime SA is separate from deployer, narrowly scoped on GCS/Pub/Sub/BigQuery, with no JSON keys.
- [ ] Data-quality assertions verify counts, uniqueness, and monetary totals—not just job health.
- [ ] Dashboards monitor latency, throughput, backlog, error rate, cost, and freshness.
- [ ] Benchmarked at realistic scale with matching semantics, including startup and validation time.
- [ ] Canary, rollback, IAM audit, and cloud resource cleanup ownership are defined.

## 17. Applied Exercises

**Exercise 1 — Choosing an engine.** Classify three cases: (a) nightly SQL aggregation on a BigQuery table, (b) Pub/Sub streaming requiring event-time windows and late data, (c) 4 TB of Parquet using legacy PySpark/UDFs/JARs. Explain not only the service choice, but also execution mode and cost drivers.

**Exercise 2 — BigQuery deduplication.** Using the eight rows in Section 6, run the `ROW_NUMBER` SQL and compute revenue per store. If event `e-004` is published a third time with a different amount, why is arbitrarily picking one payload invalid from a business standpoint?

**Exercise 3 — PySpark.** Extend `orders_etl.py` to also output `paid_orders`, partitioned by `sale_date`. Identify the shuffle costs of `dropDuplicates` and `groupBy` at large scale.

**Exercise 4 — Beam Java.** Add the count column to `SalesBeam` to output four columns matching BigQuery. Explain why line-level `Distinct.create()` only works for exact duplicates in the lab and why streaming needs bounded state/windows.

**Exercise 5 — Streaming semantics.** A `DoFn` makes an HTTP payment call, and the job retries due to a worker failure. Does Dataflow's exactly-once mode guarantee the payment API is called only once? Propose an event ID, idempotency key, and state transaction/lookup design.

**Exercise 6 — Late data.** An order occurs at 10:02 but arrives at a worker at 10:17. With 5-minute windows and 30 minutes of allowed lateness, explain how the event is classified, which window updates, and how the sink prevents double-counting across panes.

**Exercise 7 — Serverless vs. cluster Spark.** One Spark job runs 15 minutes daily; another requires custom Hive/JARs on a 24/7 cluster. Pick the two Managed Spark models and compare startup, idle cost, IAM/networking, and operations.

**Exercise 8 — BigQuery continuous queries.** Why might you consider a continuous query for certain streaming row transformations, yet not drop the CTAS with `ROW_NUMBER`/`MERGE` straight into a streaming query? List two key limitations to verify.

**Exercise 9 — IAM.** A Java app on Cloud Run triggers a Dataflow job writing to BigQuery in another data project. Diagram the three identities: launcher SA, Dataflow worker SA, and BigQuery resource owner; where should least-privilege roles be granted?

**Exercise 10 — Cost and measurement.** Build a benchmark matrix for 100 million rows across SQL, Beam, and Spark covering P95 latency, job startup, bytes/shuffle, workers/slots, error counts, cost, and the value of backlog reduction. Why do results on 8 rows lack predictive value?

**Exercise 11 — Migration.** A team wants to migrate Spark Structured Streaming to Dataflow while dealing with a 24-hour replay backlog and frequent late events. Write a runbook covering shadow testing, watermark/state/checkpoint migration, canary rollout, reconciliation, and rollback without losing or duplicating data.

## Official References

- [Dataflow overview](https://cloud.google.com/dataflow/docs/overview) — batch/stream processing with Apache Beam.
- [Dataflow streaming modes](https://cloud.google.com/dataflow/docs/guides/streaming-modes) — exactly-once/at-least-once modes.
- [Exactly-once in Dataflow](https://cloud.google.com/dataflow/docs/concepts/exactly-once) — guarantee scope and external side effects.
- [Pub/Sub streaming with Dataflow](https://cloud.google.com/dataflow/docs/concepts/streaming-with-cloud-pubsub) — duplicate deliveries and ordering.
- [Create Java Dataflow pipelines](https://cloud.google.com/dataflow/docs/guides/create-pipeline-java) — Beam Java SDK, Maven runners, and GCS.
- [Deploy Dataflow pipelines](https://cloud.google.com/dataflow/docs/guides/deploying-a-pipeline) — options, region, `tempLocation`, and IAM.
- [Dataflow Pub/Sub Subscription to BigQuery template](https://cloud.google.com/dataflow/docs/guides/templates/provided/pubsub-subscription-to-bigquery) — input JSON, target schema, and template usage.
- [Write from Dataflow to BigQuery](https://cloud.google.com/dataflow/docs/guides/write-to-bigquery) — `BigQueryIO` / Storage Write API semantics.
- [Managed Service for Apache Spark (formerly Dataproc)](https://cloud.google.com/products/managed-service-for-apache-spark) — serverless vs. clusters.
- [Submit a Spark batch workload](https://cloud.google.com/managed-spark/docs/quickstarts/spark-batch) — `gcloud dataproc batches submit`.
- [Managed Spark pricing](https://cloud.google.com/products/managed-service-for-apache-spark/pricing) — serverless/cluster costs.
- [BigQuery data transformation options](https://cloud.google.com/bigquery/docs/transform-intro) — SQL, Dataform, scheduled/continuous queries.
- [BigQuery scheduled queries](https://cloud.google.com/bigquery/docs/scheduling-queries) — schedules, IAM, and batch jobs.
- [BigQuery continuous queries introduction](https://cloud.google.com/bigquery/docs/continuous-queries-introduction) — SQL streaming support and limitations.
- [BigQuery query optimization](https://cloud.google.com/bigquery/docs/best-practices-performance-compute) — partition pruning/JOIN/aggregates.
- [BigQuery job information schema](https://cloud.google.com/bigquery/docs/information-schema-jobs) — query cost/slot-ms/metadata.
- [BigQuery pricing](https://cloud.google.com/bigquery/pricing) and [Dataflow pricing](https://cloud.google.com/dataflow/pricing) — estimating total cost.
