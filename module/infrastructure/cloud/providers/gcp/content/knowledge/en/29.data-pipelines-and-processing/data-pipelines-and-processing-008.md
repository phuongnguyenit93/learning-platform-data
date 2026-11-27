# Serverless for Apache Spark and Running Spark On Demand

A training platform collects enrollment events through Pub/Sub, stores raw data in Cloud Storage, and aggregates learners per course nightly for analysis in BigQuery. The data team already has PySpark code but does not want to maintain a 24/7 cluster just to run a few hours each day. **Serverless for Apache Spark** solves infrastructure operations for on-demand Spark workloads: submit a job, the service provisions drivers and executors, autoscales with load, and terminates compute resources when the batch finishes.

In current Google Cloud documentation, this product is named **Managed Service for Apache Spark serverless** (formerly commonly called **Dataproc Serverless for Apache Spark**). The APIs and `gcloud dataproc batches ...` commands remain in use. This lesson belongs to the **Data Pipelines and Processing** chapter of the **CLOUD_PROVIDERS_GCP** module, connecting IAM, VPC, Cloud Storage, BigQuery, Cloud Run/GKE, and Cloud Monitoring to run on-demand data processing securely and with controlled costs.

**After this lesson, you will be able to:**

1. Distinguish serverless **batches**, **interactive sessions**, Spark clusters, and cases where Spark is unnecessary.
2. Read the driver/executor architecture, submit a PySpark batch via `gcloud`, and track its status.
3. Choose runtime versions, execution identities, networking, and data permissions under least privilege.
4. Tune dynamic allocation, memory, shuffle, partitioning, and batch concurrency using metrics.
5. Design idempotent pipelines, schedules, retries, data checks, and cost/reliability monitoring.
6. Complete a data-bounded lab and production design exercises.

## 1. Choosing the Right Way to Run Spark

Apache Spark is a distributed data-processing engine: an application has a **driver** orchestrating work into stages and tasks, while **executors** process data in parallel. Spark is not a database; inputs and outputs typically reside in Cloud Storage, BigQuery, or another system.

~~~mermaid
flowchart LR
    O["Cloud Scheduler / Airflow<br/>or operator"] --> API["Dataproc Batches API"]
    API --> DRIVER["Spark driver<br/>managed compute"]
    DRIVER --> E1["Executor 1"]
    DRIVER --> E2["Executor 2 ... N"]
    GCS["Cloud Storage<br/>raw input"] --> E1
    GCS --> E2
    E1 --> OUT["Cloud Storage Parquet<br/>or BigQuery"]
    E2 --> OUT
    DRIVER -. "Logs, Spark UI, metrics" .-> OBS["Cloud Logging / Monitoring"]
~~~

Serverless **requires no manual Dataproc cluster provisioning**; compute infrastructure for the batch is managed by Google Cloud. However, Spark code, schemas, dependencies, data permissions, networking, output quality, and scheduling **remain the application team's responsibility**.

### 1.1. Options

| Option | Best suited when | Considerations |
| --- | --- | --- |
| **Serverless batch** | Hourly/daily ETL, periodic backfills, PySpark/Spark SQL/Java-Scala/R runs that terminate | Startup latency, quota/concurrency, runtime cost |
| **Serverless interactive session** | Notebooks/Jupyter for data exploration, prototyping Spark code, and feature engineering | Live sessions consume resources; enforce idle timeouts and protect sensitive data |
| **Managed Spark cluster** | Need custom components/daemons, long-lived environments, or continuous workloads | Must operate clusters, autoscaling, patching, and supporting tools |
| **BigQuery SQL** | Relational aggregations/transforms expressible in pure SQL | Avoid using Spark for minor `GROUP BY` jobs when BigQuery is simpler |
| **Dataflow (Apache Beam)** | Batch/streaming pipelines requiring event-processing semantics, windows, and event time | Different programming model from Spark; evaluate true requirements |
| **Cloud Run Jobs** | Lightweight, independent batch tasks with minimal distributed shuffle | Does not provide a managed distributed Spark engine out of the box |

**Large data alone does not mandate Spark.** If the logic is just a few SQL queries and data already lives in BigQuery, benchmark BigQuery first. When you need existing Spark/PySpark code, large file joins, feature engineering, or Spark MLlib, serverless Spark is a natural fit.

### 1.2. Batch vs. Streaming

A **batch** has bounded inputs and finishes after processing completes. Managed Service for Apache Spark can also run **Spark Structured Streaming**, yet it **does not automatically manage streaming restarts and checkpoints** like a full managed streaming service. Running continuously requires designing checkpoint storage, recovery, retries, supervision, and incident handling; never assume a batch automatically restarts forever after a crash.

## 2. Batch Lifecycle and Key Concepts

~~~mermaid
flowchart LR
    A["SUBMIT"] --> B["PENDING / SETUP"]
    B --> C["RUNNING"]
    C --> D{"Outcome?"}
    D -->|Success| E["SUCCEEDED"]
    D -->|Error| F["FAILED"]
    C -->|Cancel/timeout| G["CANCELLED"]
    E --> H["Verify output<br/>and trigger next step"]
~~~

This is a **conceptual state diagram**; the API can return intermediate states such as `PENDING`, `SETUP_DONE`, `RUNNING`, `SUCCEEDED`, `FAILED`, `CANCELLING`, and `CANCELLED`. When building automation, rely on **API terminal states** rather than matching a single log text line.

| Component | Responsibility |
| --- | --- |
| **Submitter** | Submits the batch, selects runtime, resources, source, network, and receives the batch ID |
| **Control plane** | Provisions and schedules execution resources per batch and quota |
| **Driver** | Plans Spark jobs/stages, creates tasks, manages the DAG and results |
| **Executors** | Read/write data, run transformations and shuffles |
| **Object storage / warehouse** | Stores inputs/outputs, artifacts, dependencies, and checkpoints if needed |
| **Observability** | Exposes batch state, Spark UI, logs, metrics, errors, and costs |

Do not assume `gcloud ... submit` returning immediately means the pipeline finished. When `--async` is passed, the CLI **only submits the request and exits**; your next step must **poll/watch the batch until `SUCCEEDED`**, inspect outputs, and handle `FAILED`/`CANCELLED`.

### 2.1. Serverless Batch vs. Job on an Existing Cluster

| Submission model | Managed target | Command |
| --- | --- | --- |
| **Serverless batch** | Regional batch resource with auto-provisioned infrastructure | `gcloud dataproc batches submit pyspark ...` |
| **Cluster job** | Job executed on an existing Dataproc cluster | `gcloud dataproc jobs submit pyspark ... --cluster=...` |

The two commands **are not interchangeable**: `batches submit` takes no `--cluster`, whereas `jobs submit` requires a target cluster. Cluster management and serverless batches also follow distinct pricing and quota models.

## 3. Runtime, IAM, and VPC: Three Prerequisites Before Running

### 3.1. Runtime Version and Execution Identity

The runtime version determines Spark, Python/Java, connectors, features, and **how identity delegation works**. 2026 documentation distinguishes:

- **Runtimes prior to 3.0:** with service account credentials, workloads use the **Compute Engine default service account** or an attached custom service account. The submitter needs appropriate Dataproc permissions plus `iam.serviceAccounts.actAs` on the service account; the runtime identity needs `Dataproc Worker` and data permissions.
- **Runtime 3.0 and later:** defaults to the submitter's **end-user credentials (EUC)** unless service account credentials are specified. A **custom service account** can be configured per organizational policy, requiring dedicated serverless node and service agent roles/permissions per version docs.
- **Runtime 4.0 and later:** introduces changes to resource tiers and Spark versions; never copy all Spark properties or JARs from runtime 2.x to 4.x without testing.

**Never rely on the default runtime when production requires reproducibility.** Pin a supported `major.minor` version, test library compatibility, and track EOL dates; minor patch updates may be rolled out by the service within a runtime line.

### 3.2. Role-Based Permission Separation

| Principal | Required permissions | Avoid |
| --- | --- | --- |
| **User/CI submitting batches** | `dataproc.batches.create`, corresponding get/list/operations; **Dataproc Serverless Editor** on newer runtimes as appropriate | Project Owner just to submit batches |
| **Submitter selecting a custom SA** | `iam.serviceAccounts.actAs` on the **exact** attached SA | Broad Service Account Token Creator if unnecessary |
| **Execution identity (EUC or SA)** | Read input bucket, write output, write logs, and scoped BigQuery dataset access | Editor across all buckets and all BigQuery datasets |
| **Google-managed service agents** | Roles required per runtime/service activation | Removing system roles/SAs without understanding impact |
| **Read-only job viewer** | Viewer with scoped batch get/list and approved log access | Dataproc Admin/Editor |

For example, a job reading `gs://learning-lab-raw/events/` and writing `gs://learning-lab-curated/` needs **Storage Object Viewer** on the source and object-creation permissions on the destination, plus overwrite/delete permissions only if truly required. When writing to BigQuery, it needs **job creation** permission in the job project and **data write** permissions on the target dataset/table per connector—not just `roles/bigquery.dataViewer`.

**Do not confuse identities:** a CLI user having bucket read access does not prove a custom workload SA has it; conversely, with **runtime 3.x EUC**, data permissions are evaluated against the user identity. When debugging `403`, verify the **runtime version + actual execution identity** first.

### 3.3. VPC and Location

Serverless Spark uses compute with **internal IPs**, running in a subnet **in the batch's region**. If unspecified, the service may look for a regional default subnet; projects with custom VPCs typically must pass `--subnet`.

- **Internal connectivity between driver and executors**, firewall rules, and sufficient subnet IP addresses are required.
- **Private Google Access** is enabled on the associated subnet per product behavior to reach required Google APIs.
- If a job needs packages/models from the **public internet**, configure **Cloud NAT/egress** and proper DNS; Private Google Access **does not equal public internet access**.
- With VPC Service Controls, Shared VPC, or PSC, verify egress, service perimeters, service agent roles, and networking accordingly.
- Choose a region close to data and compliant with **residency**; cross-region data transfer increases latency and cost.

Modifying project firewalls/VPCs is **outside the scope of this lab**. If no pre-configured subnet/identity is available, complete the design exercise on paper or ask an admin to approve the configuration before submitting.

## 4. PySpark Example: Aggregating Enrollment Events by Course

Scenario: a `CSV` dataset contains `event_id`, `course_id`, `status`, and `event_time`. We want to count **ACTIVE events with unique `event_id`s** per course and write Parquet for downstream analytics.

### 4.1. Code: `aggregate_enrollments.py`

~~~python
import argparse
from pyspark.sql import SparkSession, functions as F, types as T


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    spark = SparkSession.builder.appName("enrollment-counts-lab").getOrCreate()

    schema = T.StructType([
        T.StructField("event_id", T.StringType(), True),
        T.StructField("course_id", T.StringType(), True),
        T.StructField("status", T.StringType(), True),
        T.StructField("event_time", T.StringType(), True),
    ])

    try:
        events = (
            spark.read.option("header", "true")
            .schema(schema)
            .csv(args.input)
        )
        valid = (
            events.filter(
                F.col("event_id").isNotNull()
                & F.col("course_id").isNotNull()
                & (F.col("status") == "ACTIVE")
            )
            .dropDuplicates(["event_id"])
        )
        counts = valid.groupBy("course_id").agg(
            F.count("*").alias("active_enrollments")
        )
        # Each run should use a unique output prefix.
        counts.write.mode("errorifexists").parquet(args.output)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
~~~

**Key characteristics:**

- The schema is declared explicitly rather than running `inferSchema` over entire files every run.
- `dropDuplicates(["event_id"])` assumes an `event_id` represents **one immutable event**, never multiple records sharing an ID with updated values. If source data includes updated versions for an event, you need explicit ordering/versioning and reconciliation; `dropDuplicates` does not deterministically pick the latest version.
- This is a **bounded batch**; streaming/time-based deduplication requires event-time, watermarks, and checkpointing.
- `mode("errorifexists")` prevents accidentally overwriting prior outputs; for production retries, use a batch-ID prefix and validate an output manifest, or rely on staging and atomic publishing.
- Spark writes a **directory containing multiple part files**, not a single Parquet file named by `--output`. Never pass a `.parquet` filename expecting a single file.

### 4.2. Minimal Synthetic Dataset

Create `enrollments.csv` **on your lab machine** with no PII:

~~~csv
event_id,course_id,status,event_time
e001,java-basic,ACTIVE,2026-11-18T10:00:00Z
e002,java-basic,ACTIVE,2026-11-18T10:03:00Z
e003,python-basic,ACTIVE,2026-11-18T10:04:00Z
e003,python-basic,ACTIVE,2026-11-18T10:04:00Z
e004,java-basic,CANCELLED,2026-11-18T10:05:00Z
e005,python-basic,ACTIVE,2026-11-18T10:06:00Z
~~~

Expected result: `java-basic = 2` and `python-basic = 2`, because `e003` is duplicated and `e004` was cancelled. In production, also check input row counts, parse errors, duplicate counts, late-arriving events, and reconciliation with the operational source.

### 4.3. Useful Output Rules

| Rule | Why |
| --- | --- |
| Use a dedicated `gs://.../output/run_id=.../` per run | Prevents overwriting earlier jobs; eases auditing and rollback |
| Allow downstream reads only after `SUCCEEDED` and file validation | Prevents downstream consumers from reading incomplete results |
| Use Parquet/columnar format for analytics pipelines | Cuts bytes scanned vs. CSV in most analytical queries |
| Partition/bucket based on real queries and dataset size | Avoids thousands of tiny files or one massive partition |
| Record metadata: `run_id`, input prefix, code version, row counts | Supports idempotency, lineage, and incident investigation |

**Warning:** if the sink is BigQuery, use a runtime-supported Spark BigQuery connector, grant dataset/job permissions, and pick a controlled write mode (`append`/`overwrite`); **never** assume Parquet written to Cloud Storage is automatically imported into BigQuery.

## 5. Submitting a Spark Batch via CLI

### 5.1. Controlled Environment Preparation

The commands below target an **owner-approved lab project**. You need billing, the Dataproc / Managed Service for Apache Spark API, Cloud Storage API, batch submit permissions, and input/output/staging buckets configured with **consistent location policies**. Learners should never enable APIs, create VPCs/firewalls, or grant IAM in production without assignment.

~~~bash
export PROJECT_ID="YOUR_APPROVED_LAB_PROJECT"
export REGION="asia-southeast1"
export STAGING_BUCKET="YOUR_EXISTING_LAB_STAGING_BUCKET"
export DATA_BUCKET="YOUR_EXISTING_LAB_DATA_BUCKET"
export SUBNET="projects/YOUR_APPROVED_LAB_PROJECT/regions/asia-southeast1/subnetworks/YOUR_LAB_SUBNET"
export RUN_ID="batch-lab-001"

gcloud config set project "$PROJECT_ID"
gcloud config get-value project

# Read-only: verify enabled APIs and provisioned resources
gcloud services list --enabled --filter="name:dataproc.googleapis.com"
gcloud storage buckets describe "gs://$STAGING_BUCKET"
gcloud storage buckets describe "gs://$DATA_BUCKET"
gcloud dataproc batches list --region="$REGION" --project="$PROJECT_ID"
~~~

If no managed subnet or buckets are available, **stop before live execution** and complete the paper exercises in Section 9. Never use the default VPC if your organization mandates a custom VPC, and never run `gcloud services enable` without approval.

### 5.2. Uploading Code and Synthetic Data to Cloud Storage

Copy only the **lab files**. Confirm `RUN_ID` is unused and the destination path holds no one else's data:

~~~bash
gcloud storage cp ./aggregate_enrollments.py \
  "gs://$STAGING_BUCKET/scripts/$RUN_ID/aggregate_enrollments.py"
gcloud storage cp ./enrollments.csv \
  "gs://$DATA_BUCKET/input/$RUN_ID/enrollments.csv"
~~~

**Never treat a Cloud Storage bucket as temporary public scratch space**: grant Storage Object Viewer/Creator to the workload identity, never `allUsers`. After uploading, verify URIs/byte counts and specify a fresh output prefix.

### 5.3. Running the Batch with a Supported Runtime

This example picks **runtime 3.0** (if available in your project/region) to illustrate default **end-user credentials**. The submitter needs matching data permissions, and the subnet and IAM must be ready:

~~~bash
# BILLABLE OPERATION: launches real Spark compute resources.
gcloud dataproc batches submit pyspark \
  "gs://$STAGING_BUCKET/scripts/$RUN_ID/aggregate_enrollments.py" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --batch="$RUN_ID" \
  --version="3.0" \
  --subnet="$SUBNET" \
  --properties="spark.dynamicAllocation.maxExecutors=5" \
  -- \
  --input="gs://$DATA_BUCKET/input/$RUN_ID/enrollments.csv" \
  --output="gs://$DATA_BUCKET/output/$RUN_ID"
~~~

This **creates a real batch**—never run it in production just while reading the lesson. Version `3.0` is chosen to explain the newer auth flow; if this runtime is unavailable when you practice, check [runtime versions](https://cloud.google.com/dataproc-serverless/docs/concepts/versions/dataproc-serverless-versions) and use a supported version with matching permissions. `--subnet` must specify a subnet in the exact region with required firewall rules and internal connectivity.

A production alternative uses a **custom workload service account** instead of EUC:

~~~bash
# REPLACEMENT FLAG, do not launch a duplicate batch with the same RUN_ID.
# Use only after an Admin grants SA, actAs, runtime node/service agent roles,
# least-privilege Cloud Storage/BigQuery access, and verifies runtime compatibility.
--service-account="spark-batch-runtime@YOUR_PROJECT.iam.gserviceaccount.com"
~~~

Do not blindly add the flag above to production commands without checking **runtime 3.x** IAM requirements. Runtimes prior to 3.0 differ substantially in Dataproc Worker / Compute Engine SA requirements; never assume one role set works across all versions.

### 5.4. Reading Results and Logs

~~~bash
# Read-only; these commands do not create additional batches.
gcloud dataproc batches describe "$RUN_ID" \
  --region="$REGION" --project="$PROJECT_ID"
gcloud dataproc batches list \
  --region="$REGION" --project="$PROJECT_ID"
gcloud storage ls "gs://$DATA_BUCKET/output/$RUN_ID/"
~~~

If the batch is not `SUCCEEDED`, block downstream reads. Open **Managed Service for Apache Spark → Batches → select batch** in the Console to view state, driver logs, Spark UI, and metrics. Verify input/output row counts (here expecting 2 and 2) using an approved Spark or BigQuery query rather than merely checking whether the output folder exists.

**Never delete a batch while its logs are still needed for investigation.** After the lab, delete only the outputs, inputs, and scripts for your `RUN_ID`, after confirming no pipeline references them. Batch metadata expires according to service retention; the absence of VMs does not mean buckets or outputs were cleaned up automatically.

## 6. Autoscaling, Shuffle, and Resource Selection

### 6.1. Dynamic Allocation Is Not Infinite Automatic Quota

Serverless Spark enables **dynamic resource allocation** per runtime support: executor counts scale up and down based on Spark workload demand. Key properties:

| Spark property | Meaning | Warning |
| --- | --- | --- |
| `spark.dynamicAllocation.enabled` | Enables/disables dynamic executor allocation | Do not disable just for "stability"; it can raise cost or starve capacity |
| `spark.dynamicAllocation.initialExecutors` | Initial executor count | Does not mean a fixed executor count |
| `spark.dynamicAllocation.minExecutors` | Minimum executor count | Keeping a high minimum makes small batches over-provision |
| `spark.dynamicAllocation.maxExecutors` | Upper bound on executors for the batch | Does not guarantee enough quota or IPs exist to reach this cap |
| `spark.dynamicAllocation.executorAllocationRatio` | Tunes scale-up aggressiveness relative to needed parallelism | Scaling too aggressively can waste resources |
| `spark.dataproc.scaling.version` | Selects autoscaling V1 or V2 where supported | V2 supports asynchronous downscaling and better shuffle management |
| `spark.dynamicAllocation.profile` | `cost` or `performance` profile where supported | Profiles can be overridden by explicitly set properties |

In current documentation, **min/initial executors** have product minimums (typically **2**). Avoid setting `minExecutors=0` thinking serverless means scale-to-zero **while a batch is still running**. Compute resources are released only when the batch finishes; never assume a `RUNNING` batch consumes zero compute.

Example properties tuned as needed:

~~~bash
--properties="spark.dataproc.scaling.version=2,spark.dynamicAllocation.initialExecutors=2,spark.dynamicAllocation.maxExecutors=20,spark.dynamicAllocation.executorAllocationRatio=0.5"
~~~

This is a **replacement flag** for the submit command's `--properties` option, not a standalone shell command. `maxExecutors=20` is an upper bound for an approved high-load lab; for our 6-row lab, 20 executors would be **wasteful**. Never tune many properties simultaneously when benchmarking.

### 6.2. Autoscaling V1 vs. V2

| Feature | V1 | V2 |
| --- | --- | --- |
| Scale-down | Mostly synchronous with shuffle migration | Supports **asynchronous downscaling** |
| Node selection for scale-down | Less optimized for shuffle state | Picks nodes accounting for shuffle/idle state |
| Graceful decommission / shuffle tuning | More limited | Exposes additional tuning properties |

To enable V2, set `spark.dataproc.scaling.version=2` if your chosen **runtime/tier** supports it. Never assume V2 is universally faster for every job: compare **total DCU-time**, shuffle read/write, retries, p99 stage duration, and total runtime. Very short jobs are often dominated by startup time, so changing the scaling algorithm makes little difference.

### 6.3. Memory, Partitions, and Skew

| Symptom | Likely root cause | What to try |
| --- | --- | --- |
| Executor OOM | Large join/shuffle, skew, object overhead, or oversized partitions | Profile, increase partitioning reasonably, fix skew before raising RAM |
| Very few tasks in a stage despite many executors | Few input files/partitions, or premature `coalesce(1)` | Inspect physical plan, input splits, and parallelism |
| Too many tiny tasks, high scheduler overhead | Too many small files or shuffle partitions | Compact files appropriately, size partitions to dataset volume |
| One task takes far longer than all others | Data skew on a very common key | Salting/hot-key splitting, adaptive query execution, broadcast join if appropriate |
| Heavy shuffle spill | Suboptimal memory/partitions/joins, disk pressure | Inspect Spark UI shuffle spill, partition sizes, memory, and skew |
| Driver OOM | Calling `collect()` or `toPandas()` on a large dataset | Keep data distributed, use `limit` for previews, never pull everything to the driver |

**Rule:** true Spark parallelism is bounded by useful partitions/tasks and source/sink I/O; having 100 executors with only 10 independent tasks will not make a read run 100x faster.

### 6.4. Partitioning and Storage Formats

- Converting CSV to **Parquet** with a consistent schema usually reduces bytes scanned for columnar analytics.
- Only **partition outputs by meaningful query predicates** (such as `event_date`); never partition arbitrarily on a very high-cardinality key like `event_id`.
- Avoid writing thousands of KB-sized files: file listing, metadata, and downstream scans incur heavy overhead.
- With `repartition(n)`, pick `n` based on data size—never set `1` just to "make files easier to view"; forcing `coalesce(1)` on large datasets creates a single-task bottleneck.
- When writing to BigQuery, consider connector type, partitioning/clustering, BigQuery job permissions, and commit semantics so retries never duplicate data.

**Data source note:** Cloud Storage streams data quickly, yet Spark still has to read bytes, decompress, and process them; cross-region networking, codecs, and connectors govern speed. Never mistake low CPU for "Spark failing to utilize compute" when I/O is the bottleneck.

## 7. Orchestration, Scheduling, and Correctness on Retry

### 7.1. Separating the Scheduler from the Batch

Serverless Spark **accepts and executes** workloads; scheduling, cross-step dependencies, and pipeline SLAs belong in a dedicated orchestrator.

~~~mermaid
flowchart TB
    SCH["Nightly schedule<br/>Managed Airflow / Workflows"] --> CHECK["Check input + assign run ID"]
    CHECK --> BATCH["Submit Spark batch"]
    BATCH --> WATCH{"Wait for terminal state"}
    WATCH -->|SUCCEEDED| VAL["Validate output + row counts"]
    WATCH -->|FAILED/CANCELLED| ERR["Alert, bounded retry"]
    VAL --> PUBLISH["Publish partition / BigQuery table"]
    PUBLISH --> DOWN["Dashboard / downstream API"]
    ERR --> CHECK
~~~

**Managed Service for Apache Airflow** (managed by Google Cloud) provides operators to launch and monitor Dataproc serverless batches. For simpler needs, Cloud Scheduler can trigger Workflows or Cloud Run to orchestrate the **Batches API**. Never let Cloud Scheduler blindly resubmit duplicate jobs without a deterministic job ID, lock/idempotency, and timeout handling.

### 7.2. Which Retries Are Safe?

| Situation | Action |
| --- | --- |
| Submit request timed out, yet batch may have been created | **Fetch the batch by ID** before resubmitting; use request ID/idempotency where supported |
| Batch `FAILED` after writing partial output | Never append again blindly; write to a run-specific staging prefix and clean up/reconcile before retry |
| BigQuery sink could receive duplicates | Use `MERGE` on a business key or staging tables + atomic publish transactions |
| Late-arriving inputs | Define watermarks / late-data acceptance windows and tagged backfills with dedicated IDs |
| Downstream reporting query failed | Do not rerun the entire Spark batch if its output was already validated |
| Code/schema changed between retries | Record code version and input snapshot; require review rather than treating it as an identical retry |

A **Batch ID** should uniquely identify an intentional run, such as `enrollment-20261118-r01`. Never reuse an existing batch ID without checking its state first. For historical **backfills**, record input/output manifests and define replacement semantics; when reprocessing a recent date, avoid double-counting old results via `append`.

### 7.3. Recording Minimal Lineage Metadata

A run metadata record should look like:

~~~json
{
  "run_id": "enrollment-20261118-r01",
  "source": "gs://lab-raw/events/date=2026-11-18/",
  "output": "gs://lab-curated/enrollment_counts/run_id=enrollment-20261118-r01/",
  "code_version": "git-commit-or-image-digest",
  "runtime_version": "3.0",
  "batch_state": "SUCCEEDED",
  "validation": "PASS",
  "published_at": "2026-11-19T03:00:00Z"
}
~~~

This is **illustrative metadata**; never store service account tokens, credentials, or PII in manifests. `SUCCEEDED` must come from the Batches API, while `validation=PASS` comes from **separate** pipeline checks (schema, row counts, uniqueness, output path). Publish data only after both pass.

## 8. Monitoring, Cost, and Environment Selection

### 8.1. Signals to Track

| Area | Metric / evidence | Question |
| --- | --- | --- |
| **Batch lifecycle** | `PENDING`/`SETUP`/`RUNNING` durations, `SUCCEEDED`/`FAILED`, retry counts | Will the batch finish before the reporting deadline? |
| **Spark UI** | DAG, stages, tasks, shuffle read/write/spill, executor utilization | Bottlenecked on driver, skew, or network? |
| **Logs** | Driver exceptions, executor lost, IAM errors, `OutOfMemory` | Configuration error or data error? |
| **Input/output** | Rows/bytes, late data, duplicates, null rate, file counts | Are results complete and schema-valid? |
| **Compute/cost** | DCU-time, driver/executor resources, shuffle storage, duration | Is cost per million events rising? |
| **Data services** | Cloud Storage requests/bytes, BigQuery query/storage costs | Is Spark compute the whole bill? |
| **Network** | Subnet IPs, egress, VPC/perimeter violations | Did the job fail because it couldn't reach sources/sinks? |

A batch's Spark UI can be viewed **directly in the Console** without a Persistent History Server for supported cases. Before relying on it for long-term auditing, check retention limits, access controls, and policies for Spark UI/logs—never assume UIs persist forever by default.

### 8.2. How Serverless Spark Billing Works

Managed serverless Spark bills in **Data Compute Units (DCUs)** based on allocated resources and runtime, distinguishing **standard/premium tiers**, shuffle storage, and supporting components. **You do not pay only per output row**, and "serverless" does not mean small batches are free.

A cost model:

\[
\text{Total} \approx
\text{driver/executor DCU-seconds} \times \text{unit price}
+ \text{shuffle storage}
+ \text{Cloud Storage / BigQuery / network / logging}
\]

Check the **pricing unit** (DCU-hour vs. DCU-second conversions) so you are not off by a factor of 3,600. Startup time and workload resource minimums also contribute to total cost. Long-lived interactive sessions consume resources while users sit idle; enforce TTL/auto-stop policies.

**A runtime change affecting pricing:** starting with 4.0+, resource-tier selection changes; batches may default to **premium** unless `dataproc.tier=standard` is chosen where supported. Never carry old `spark.dataproc.driver.compute.tier` settings from older runtimes straight into 4.0. Check current [pricing](https://cloud.google.com/products/managed-service-for-apache-spark/pricing) by region and tier before committing a budget.

### 8.3. Cost Optimization Trade-Offs

| Adjustment | Potential benefit | Risk |
| --- | --- | --- |
| Lower initial/min executors | Less compute during light phases | Longer batch runtime if scale-up lags |
| Raise max executors carefully | Shorter wall-clock time when many tasks exist | Higher peak DCUs, quota/IP pressure, potentially higher cost |
| Choose `cost` autoscaling profile | Reduces idle resources | Some stages run slower |
| Optimize file sizes / partition pruning | Less I/O and shuffle; faster jobs | Requires schema/layout changes and downstream testing |
| Move simple SQL jobs to BigQuery | Eliminates Spark ops and startup overhead | Must benchmark actual BigQuery query cost |
| Consolidate tiny batches with shared dependencies | Reduces startup/setup overhead | Increases coupling; one retry impacts multiple outputs |

**Compare total cost against deadlines**, not just runtime minutes. A 10-minute batch averaging 5 DCUs and a 4-minute batch averaging 30 DCUs consume different compute totals; decide using measured DCU-time and downstream service costs.

## 9. Diagnosing Failed Batches or Wrong Outputs

### 9.1. Layered Fault Table

| Symptom | Common root cause | Safe verification |
| --- | --- | --- |
| Submit fails, missing `dataproc.batches.create` | Submitter lacks matching Dataproc Serverless role | Check principal and role per runtime; never grant Owner |
| `iam.serviceAccounts.actAs` denied | Submitter lacks delegation rights on custom SA | Check permissions **on that exact SA**, not another account |
| Driver never initializes, times out waiting | Missing execution/service agent roles, subnet/firewall/DNS, insufficient IPs/quota | Inspect batch details, runtime version, IAM, and network logs |
| `403` reading Cloud Storage | Execution identity lacks object read access | Check EUC vs. custom SA, bucket policy, and object path |
| `403` writing BigQuery | Missing `jobs.create` or `tables.updateData` / data roles | Verify job project/dataset, connector, and execution SA |
| `ClassNotFound`/`ModuleNotFoundError` | Missing package/JAR or mismatched Spark/Python/Scala version | Pin and verify runtime, dependencies, image, and connectors |
| `OutOfMemoryError` on driver | `collect()`/`toPandas()` or oversized metadata/plan | Inspect Spark UI; stop pulling large data to the driver |
| Executor OOM, stage retries | Skew, oversized partitions, shuffle spill, insufficient resources | Check task skew, physical plan, partition sizes, and memory |
| Batch `SUCCEEDED` yet output is empty | Wrong path/filter, schema parse mismatch, missing input, wrote to wrong prefix | Compare input counts, schema, output manifest, and sample data |
| Retry duplicates rows in sink | Non-idempotent append, retry after partial write | Stage/merge by business key; control run IDs and commits |
| Job slow while CPU is low | I/O wait, remote bucket, network, hot partition, small files | Inspect Spark UI I/O/shuffle, region, and connector metrics |
| Batch misses morning deadline | Setup overhead, quota queuing, heavy joins/shuffles | Separate `PENDING` vs. `RUNNING`; add headroom and trigger earlier |

### 9.2. Runbook When a Batch Is `FAILED`

1. **Scope** the exact `project`, `region`, `batch_id`, start time, runtime, and submitter.
2. Read `gcloud dataproc batches describe`, driver logs, and Spark UI; separate **resource/provisioning errors** from **application code errors**.
3. Identify the execution identity: EUC (runtime 3.x) or service account; verify source/sink permissions.
4. If the driver never started, inspect VPC subnet, firewall, DNS, Private Google Access, egress, VPC Service Controls, and quotas.
5. If the driver started and failed, inspect the root exception, stage/task retries, OOMs, shuffle skew, and SQL schemas.
6. Check any partially written output prefix and follow the **cleanup/retry/merge** runbook; never blindly re-append.
7. After fixing, rerun with a **new batch ID** or per designed idempotency rules; verify row counts and SLOs.

**Response rule:** never increase executor memory, grant BigQuery Admin, and open all VPC firewalls simultaneously. Doing so widens the blast radius and obscures the true root cause.

### 9.3. How to Interpret `SUCCEEDED`

`SUCCEEDED` means the Spark workload terminated cleanly according to the service. It **does not prove**:

- The correct input partition or schema was read.
- All duplicate or late-arriving events were handled per business definitions.
- Results landed at the exact location downstream reads.
- A BigQuery table or dashboard has been refreshed.
- No PII leaked or source/sink authorization was violated.

Therefore, add a **data-quality gate**—for example: `input_events >= expected_min`, `duplicate_event_ids = 0` in output, course count checks, valid output manifests, and source reconciliation. If checks fail, mark the pipeline **validation failed** even when the batch state is `SUCCEEDED`.

## 10. Exercises and Real-World Scenarios

### Scenario A — Should You Use Serverless Spark for 3 SQL Queries?

A data team wants to run three daily `GROUP BY` queries over a 20 GiB BigQuery table. No special Spark libraries are needed, and no external files are read.

**Prompt:** choose BigQuery SQL, serverless Spark, or a self-managed Spark cluster.

**Solution:** BigQuery SQL is usually the simplest starting point. Compare query cost, latency, governance, and features. Serverless Spark wins only when valuable Spark transforms, ML, or dependencies exist; self-managing a cluster for three small SQL queries adds unnecessary operational overhead.

### Scenario B — Twice-Daily Job over 1 TiB of Parquet

Nightly jobs process 1 TiB of data, apply PySpark business rules, join a dimension table, and write curated Parquet. Jobs run many hours apart.

**Prompt:** propose execution mode, IAM, scheduling, output layout, and key metrics.

**Solution:** **serverless batch** is a strong candidate, with a pinned runtime, least-privilege bucket identities, matching subnet/region, and scheduling via Managed Airflow/Workflows. Write outputs by `run_id` or date partition and publish after validation; track wall-clock duration, DCU-time, shuffle spill, input/output bytes, failed retries, and data-quality checks.

### Scenario C — Submitter Has Permissions Yet Job Gets `403`

User `alice@example.com` holds `Dataproc Serverless Editor` and Storage Object Viewer on the input bucket. The batch runs on runtime 3.x with a **custom service account** `spark-runtime@...`; the driver fails to read `gs://input-bucket`.

**Prompt:** which principal lacks permissions? Should you grant Project Editor?

**Solution:** inspect the attached **execution service account** and grant Storage Object Viewer **on the input bucket** to that SA, along with required runtime node roles for the version. Alice's read permissions do not transfer automatically to a custom SA. Never grant Project Editor; also verify the submitter's `actAs` permission.

### Scenario D — Adding Executors Does Not Speed Up the Job

A job has 6 independent partitions and currently uses 8 executors. The team raises `maxExecutors` to 100, yet runtime barely improves.

**Prompt:** identify the cause and what changes are worth benchmarking.

**Solution:** the actual task count limits parallelism; 100 executors cannot conjure 100 useful tasks. Check partition counts and data skew in the Spark UI, and increase input/join partitioning reasonably if I/O and data volume warrant it—never add executors just to make aggregate CPU look higher.

### Scenario E — Retry After Timeout Doubles Totals

A job writes results using `append` into a BigQuery table. The orchestrator times out and submits a new batch even though the first batch already finished writing; the dashboard shows doubled enrollment totals.

**Prompt:** design three-layer duplicate protection.

**Solution:** (1) use deterministic `batch_id`/`request_id` on submission and check batch status before retrying; (2) write output to a `run_id`-scoped staging prefix/table and validate; (3) publish via `MERGE`/deduplication on business key or controlled partition replacement. The orchestrator marks success only when both API state and validation pass.

### Scenario F — Running 24/7 Streaming Inside a Batch and Getting Restarted

A team runs Structured Streaming from Pub/Sub without configuring durable checkpoints or a supervisor/restart policy, assuming serverless Spark keeps the stream running continuously on its own.

**Prompt:** explain the misconception and suggest an alternative.

**Solution:** serverless Spark infrastructure **does not automatically manage all streaming recovery requirements**. You need checkpoints, state/replay semantics, monitoring, restart orchestration, and cost guardrails; if continuous event-time streaming is a core requirement, evaluate **Dataflow/Beam** as a better fit.

### Quantitative Exercise — Choosing by DCU-Time

Two configurations process the same batch and meet output quality:

| Configuration | Average DCUs while running | Runtime | Estimated DCU-hours |
| --- | ---: | ---: | ---: |
| A — fewer executors | 12 DCUs | 30 minutes | 6 |
| B — more executors | 30 DCUs | 15 minutes | 7.5 |

**Questions:**

1. How are DCU-hours calculated? — `average DCUs × time (hours)`.
2. Assuming identical tier/unit price, which configuration has lower compute charges? — **A** (6 vs. 7.5 DCU-hours).
3. Which configuration finishes faster? — **B**, 15 minutes vs. 30 minutes.
4. Can you conclude A is cheaper in **total** cost by an exact dollar amount? — **Not yet**: you also need tier/region rates, shuffle storage, data I/O, and related service charges.
5. If the report must finish under 20 minutes, which option fits? — **B** is the deadline-meeting candidate, provided data quality, quotas, and cost are also verified.

### Self-Check Questions

1. **Does Serverless Spark require creating a cluster beforehand?** — No, not for serverless batches.
2. **What is the current CLI path for batches?** — `gcloud dataproc batches submit ...`.
3. **What is the difference between a batch and an interactive session?** — A batch terminates when processing finishes; a session supports interactive exploration with its own lifecycle.
4. **Under what identity does runtime 3.x run by default?** — Typically **end-user credentials**, unless service account credentials are specified.
5. **Are submitter permissions and execution SA permissions the same?** — No; submission permissions differ from runtime data access.
6. **Does autoscaling guarantee the lowest possible cost?** — No; `minExecutors`, partitions, skew, and runtime/tier also matter.
7. **Why is `collect()` risky on large datasets?** — It pulls all data into driver RAM, risking OOM.
8. **Does Batches API `SUCCEEDED` prove data correctness?** — No; separate validation is required.
9. **When `--async` returns on submit, is the batch finished?** — No; you must poll its status.
10. **Should you retry an append job after timeout without checking the first batch?** — No; it can duplicate data.

## 11. Production Deployment Checklist

| Item | Acceptance criteria |
| --- | --- |
| **Workload fit** | Clear justification for Spark over BigQuery SQL / Dataflow / Cloud Run Jobs, benchmarked on realistic data. |
| **Runtime** | Supported Spark/Python/connector line, `major.minor` pinned, upgrade/EOL plan in place. |
| **IAM** | Submitter has batch permissions; execution identity (EUC or custom SA) is explicit and scoped to exact buckets/datasets. |
| **Networking** | Matching region/subnet, internal firewall rules, Private Google Access, DNS, and NAT/PSC/perimeter if needed. |
| **Input** | Clear input snapshot/partition and schema; checks for row counts, corruption, duplicates, and late events. |
| **Output** | Run-specific staging prefix, deterministic publish, validation, no unintended duplicate appends. |
| **Resources** | Min/max executors, shuffle, memory, and partitions measured; reasonable quota/IP/cost headroom. |
| **Orchestration** | Schedule includes dependencies, timeouts, retry/backoff, idempotency, alerts, and an owner. |
| **Observability** | Batches API state, Spark UI, logs, data-quality signals, DCU-time, and cost dashboards. |
| **Security** | No JSON keys in code; data/credentials redacted from logs; VPC SC/CMEK verified where applicable. |
| **Resilience** | Tested against `FAILED` runs, duplicate submissions, partial outputs, driver crashes, and recovery/backfills. |
| **Cost/SLO** | Completion time, compute DCUs, shuffle, and destination service fees checked against approved budget. |

### Next Steps Beyond This Lesson

Once a single batch runs safely, raise pipeline maturity rather than chasing raw throughput alone: implement **CI/CD for code and config**, schema compatibility checks, **data contracts**, lineage, CI tests with synthetic data, freshness tracking, per-run audits, and failure/retry drills. For streaming, design dedicated checkpoint/state/late-data handling or choose Dataflow when it is a core requirement.

## 12. Official Google Cloud Documentation

- [Managed Service for Apache Spark serverless overview](https://docs.cloud.google.com/managed-spark/docs/serverless-overview): batch workloads, interactive sessions, operational model, and scheduling.
- [Submit an Apache Spark batch workload](https://docs.cloud.google.com/managed-spark/docs/quickstarts/spark-batch): Console/CLI walkthrough, SparkPi, and batch lifecycle.
- [gcloud dataproc batches submit pyspark](https://cloud.google.com/sdk/gcloud/reference/dataproc/batches/submit/pyspark): `--batch`, `--region`, `--version`, `--subnet`, `--service-account`, `--properties`, and `--async` syntax.
- [Serverless runtime versions](https://docs.cloud.google.com/managed-spark/docs/concepts/versions/serverless-versions): Spark/Java/Python/connector versions, support dates, and differences across runtimes.
- [Serverless IAM roles and permissions](https://docs.cloud.google.com/managed-spark/docs/concepts/iam-serverless): batch, session, Viewer/Editor, and execution roles.
- [Serverless service accounts](https://docs.cloud.google.com/managed-spark/docs/concepts/service-accounts-serverless): pre-3.0 vs. 3.0+ runtimes, end-user credentials, and custom SAs.
- [Serverless network configuration](https://docs.cloud.google.com/managed-spark/docs/concepts/network-serverless): subnets, internal IPs, Private Google Access, NAT, and VPCs.
- [Autoscale workload resources](https://docs.cloud.google.com/managed-spark/docs/concepts/autoscaling-serverless): dynamic allocation, V1/V2, profiles, and Spark properties.
- [Spark workload properties](https://docs.cloud.google.com/managed-spark/docs/concepts/spark-properties-serverless): CPU/RAM, tiers, executors, and shuffle controls by runtime.
- [Monitor and troubleshoot batch workloads](https://docs.cloud.google.com/managed-spark/docs/guides/monitor-troubleshoot-batches): Spark UI, logs, metrics, and batch debugging.
- [Troubleshoot batch creation failures](https://docs.cloud.google.com/managed-spark/docs/support/batch-session-creation-failures): IAM, subnets, quotas, and driver initialization.
- [Serverless Spark FAQ](https://docs.cloud.google.com/managed-spark/docs/faq-serverless): cluster vs. serverless comparison, streaming, and concurrency limits.
- [Managed Service for Apache Spark pricing](https://cloud.google.com/products/managed-service-for-apache-spark/pricing): DCUs, resource tiers, shuffle storage, and pricing components.

**Conclusion:** running Spark on demand on Google Cloud means **not managing persistent Spark clusters**, while still managing **runtimes, execution identities, networking, data, and workflows** properly. A sound pipeline does not stop at `SUCCEEDED`; it must deliver **data accuracy, duplicate-free retries, deadline adherence, least privilege, and measurable total cost**. Start with a small batch with isolated input/output, validate thoroughly, and only then scale throughput by tuning executors, partitions, and scheduling.
