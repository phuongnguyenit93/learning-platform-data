# Glue Bookmarks, Workflows, and ETL Resource Optimization

## Lesson Objectives

In the CLOUD_PROVIDERS_AWS ecosystem, AWS Glue provides a managed ETL environment to discover data, catalog metadata, and run data processing pipelines across Amazon S3, JDBC databases, and many other sources/targets. When pipelines run on schedules or continuously receive new data, two operational challenges typically arise: how to process only the necessary data, and how to orchestrate multiple ETL steps with predictable cost and completion times.

AWS Glue job bookmarks persist read progress state to avoid reprocessing data that has already been read successfully. AWS Glue workflows connect jobs, crawlers, and triggers into an observable ETL graph. Mechanisms such as Auto Scaling, worker types, the FLEX execution class, partition pruning, file grouping, and Spark tuning help align resources with data characteristics.

After this lesson, you can:

- Explain job bookmarks and distinguish between Enable, Disable, Pause, rewind, and reset.
- Configure bookmarks for S3 and JDBC, and understand the role of bookmark keys and transformation contexts.
- Identify bookmark limitations with updates, deletes, and target outputs.
- Design workflows consisting of jobs, crawlers, and schedule/event/conditional triggers.
- Pass run properties between steps and limit concurrent workflow runs.
- Select appropriate worker types, worker counts, Auto Scaling, and execution classes.
- Reduce data scanned using partition pruning, pushdown, and column projection.
- Reduce overhead caused by small files, shuffles, skew, and joins.
- Monitor job metrics, Spark UI, workflow runs, and costs.
- Build incremental ETL pipelines with retries, backfills, idempotent outputs, and clear operational procedures.

## 1. Role of Bookmarks, Workflows, and ETL Resources

A data lake pipeline typically has multiple stages:

1. Receive files or data from source systems.
2. Discover schemas and update metadata in the AWS Glue Data Catalog.
3. Read new data or data requiring backfill.
4. Cleanse, standardize, and deduplicate.
5. Write data into Bronze, Silver, or Gold zones.
6. Validate data quality, update the catalog, and emit notifications.

Three capability groups address different dimensions:

| Capability | Question Answered | Example |
|---|---|---|
| Job bookmark | Which portion of input should the next run read? | Read only new S3 objects or JDBC rows with bookmark key greater than checkpoint |
| Workflow | Which step runs first, and what depends on what? | Crawler completes, then Bronze job runs; Silver runs only after Bronze succeeds |
| Resource optimization | How much compute is needed and how much data must be read/processed? | Auto Scaling, G.1X workers, partition pruning, file grouping, and shuffle tuning |

These mechanisms complement each other. Bookmarks do not orchestrate pipelines; workflows do not guarantee duplicate-free outputs; adding workers does not fix designs that unnecessarily scan entire datasets. A reliable pipeline must combine read progress tracking, execution ordering, safe reruns, and resource measurement.

## 2. How Do AWS Glue Job Bookmarks Work?

A job bookmark is persistent state maintained by AWS Glue for a job run. This state helps Glue determine which input data has already been processed so subsequent runs can focus on new data.

For S3 sources, Glue uses object metadata and `LastModified` timestamps to identify objects to process. For JDBC, Glue uses one or more bookmark keys to identify new rows based on saved key values. Bookmarks can maintain state per source and transformation context in the script.

High-level flow:

~~~mermaid
flowchart TD
    A[Start Glue job] --> B[job.init reads bookmark state]
    B --> C[Read supported source with transformation_ctx]
    C --> D[Filter input using saved bookmark]
    D --> E[Transform and write output]
    E --> F{All required work succeeded?}
    F -- No --> G[Job fails; bookmark is not committed]
    F -- Yes --> H[job.commit saves bookmark state]
    H --> I[Next run reads only eligible new input]
~~~

Bookmarks only track read progress. They are not distributed transactions spanning source and target. If a job writes partial output and fails before `job.commit()`, the next run may reread the same input. Therefore, targets require an idempotent write strategy or duplicate handling.

Bookmarks are supported for JDBC sources, the `Relationalize` transform, and certain S3 sources. For Glue 1.0+, documented S3 formats include JSON, CSV, Apache Avro, XML, Parquet, and ORC. Verify the specific source/format type and Glue version before relying on bookmarks.

## 3. Three Bookmark Modes: Enable, Disable, and Pause

Job bookmarks have three primary modes:

| Mode | Behavior | When to Use |
|---|---|---|
| Enable | Reads new data per bookmark and updates bookmark after a successful run | Recurring incremental ETL |
| Disable | Does not use bookmarks; every run processes the full input scope defined in the script | Full refreshes or jobs managing their own checkpoints |
| Pause | Reads an incremental range or specified run interval without advancing current bookmark state | Backfills or rechecking a range of data |

Disable is the default if bookmarks are not configured on the job. Enable is standard for incremental pipelines. Disable suits full reloads, provided targets are replaced or rewritten to avoid duplicates. Pause allows reading across a run range without advancing the active bookmark state.

Two parameters used with Pause:

- `job-bookmark-from`: run marker defining input already processed previously and excluded from this run.
- `job-bookmark-to`: run marker capping the maximum input allowed to be processed.

When using these parameters, both `from` and `to` must be supplied. Both values are job run IDs, not business dates. The job processes input after `from` up to `to` according to bookmark semantics; data after `to` is excluded. Check run history before backfilling and write results to an isolated target or safely replaceable partition.

Example Pause over a run range:

~~~bash
aws glue start-job-run \
  --job-name sales-incremental-etl \
  --arguments '{"--job-bookmark-option":"job-bookmark-pause","--job-bookmark-from":"jr_OLD_RUN_ID","--job-bookmark-to":"jr_NEW_RUN_ID"}' \
  --region ap-southeast-1
~~~

Example passing bookmark option when running a job:

~~~bash
aws glue start-job-run \
  --job-name sales-incremental-etl \
  --arguments '{"--job-bookmark-option":"job-bookmark-enable","--run-date":"2026-11-20"}' \
  --region ap-southeast-1
~~~

The `--run-date` value is an illustrative business argument read by the script itself; bookmark state does not infer business dates from that parameter name.

## 4. job.init, transformation_ctx, and job.commit

When writing Glue Spark scripts, initialize the job to read bookmark state and commit state once work finishes.

- `job.init(job_name, args)` retrieves current state and initializes the bookmark service.
- `transformation_ctx` is a stable identifier for a source or transformation context; Glue uses it to bind state to the right operator.
- `job.commit()` persists updated bookmark state after required operations succeed.

S3 source example:

~~~python
import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext

args = getResolvedOptions(sys.argv, ["JOB_NAME"])

sc = SparkContext.getOrCreate()
glue_context = GlueContext(sc)
spark = glue_context.spark_session

job = Job(glue_context)
job.init(args["JOB_NAME"], args)

source = glue_context.create_dynamic_frame.from_catalog(
    database="raw_catalog",
    table_name="sales_events",
    transformation_ctx="sales_events_source"
)

# Transform and write output here.
# Make the sink idempotent for retries and backfills.

job.commit()
~~~

If `job.init` or `job.commit` is missing, bookmarks will not operate properly. If `transformation_ctx` is omitted from an eligible source DynamicFrame, Glue cannot associate bookmark state with that operator.

Keep `transformation_ctx` stable while the logical source remains the same. Renaming the context or changing source properties while keeping the old context can cause Glue to apply prior state to a different source, skipping data or reading the wrong range. When changing sources, evaluate creating a new context/job or resetting state through a controlled process.

`job.commit()` should occur after the sink finishes. Never call commit prematurely before writes, validations, or required output publishing complete.

## 5. Bookmarks with Amazon S3

For S3 sources, Glue bookmarks track processed objects using `LastModified` timestamps. On the next run, Glue filters eligible objects newer than the bookmark state.

Example data layout:

~~~text
s3://company-data/raw/sales/
  year=2026/month=11/day=18/part-0001.json
  year=2026/month=11/day=19/part-0001.json
  year=2026/month=11/day=20/part-0001.json
~~~

A daily job can read new objects via bookmarks. However:

- S3 bookmarks are not content checksums; objects overwritten or modified get a new `LastModified` and may be reprocessed.
- Deleting an object at the source does not generate an automatic delete event at the target.
- Changing prefixes/source paths can alter the input set and interact unpredictably with old state.
- Bookmarks do not delete or replace objects at the target.
- A newly arrived file with an older timestamp than the checkpoint may not be detected as operators expect; design explicit ingestion timestamps and separate backfills.

When data is written by multiple producers, use date/hour or batch-ID prefixes and avoid overwriting already processed objects. If sources allow late-arriving files, define a backfill window or manifest verification mechanism instead of relying solely on bookmarks.

### 5.1. Bookmarks and Partition Pruning

Bookmarks answer which objects were already processed; partition pruning answers which partitions to read in the current run. Both can be combined.

Example reading only November data:

~~~python
source = glue_context.create_dynamic_frame.from_catalog(
    database="raw_catalog",
    table_name="sales_events",
    push_down_predicate="year='2026' and month='11'",
    transformation_ctx="sales_events_source"
)
~~~

`push_down_predicate` filters partitions based on Data Catalog metadata before Glue lists objects inside the selected partitions. For tables with huge partition counts, `catalogPartitionPredicate` combined with partition indexes enables server-side catalog partition filtering and reduces listing overhead.

For inputs with very large object counts, enable the AWS Glue S3 Lister via `additional_options` to reduce driver memory pressure when listing files. Example:

~~~python
source = glue_context.create_dynamic_frame.from_catalog(
    database="raw_catalog",
    table_name="sales_events",
    push_down_predicate="year='2026' and month='11'",
    additional_options={"useS3ListImplementation": True},
    transformation_ctx="sales_events_source"
)
~~~

The S3 Lister helps Glue iterate filtered file lists with lower memory overhead. It does not replace partition pruning and does not change bookmark semantics.

Do not confuse pushdown predicates with bookmarks: predicates restrict the read scope by query conditions; bookmarks persist progress across runs.

## 6. Bookmarks with JDBC Sources

For JDBC sources, Glue tracks one or more bookmark keys to identify new rows. By default, Glue can use the primary key if values increase or decrease sequentially under supported conditions. Users can specify custom bookmark keys and sort order in the script.

Example:

~~~python
source = glue_context.create_dynamic_frame.from_catalog(
    database="operational_db",
    table_name="orders",
    transformation_ctx="orders_jdbc_source",
    additional_options={
        "jobBookmarkKeys": ["updated_sequence"],
        "jobBookmarkKeysSortOrder": "asc"
    }
)
~~~

Custom bookmark keys must increase or decrease strictly monotonically. Gaps in key values are permitted, but never use columns whose values can be reused or move backward, such as status, order type, or non-monotonic revision numbers.

An important limitation: JDBC bookmarks do not automatically detect `UPDATE`s on rows whose key is less than or equal to the checkpoint. If an older row changes without its bookmark key increasing, the job may skip rereading that row. Nor are bookmarks transaction-log CDC capture. When insert/update/delete synchronization is required, consider AWS DMS CDC, properly managed change timestamps/sequences, or full reconciliation strategies.

If a source uses `updated_at` as a bookmark key, ensure the value increases monotonically with readable data and never moves backward. In practice, timestamps can collide or suffer clock skew; a compound key may need a unique sequence column. Validate key logic against real data and delayed-commit transaction edge cases.

## 7. Rewinding, Resetting, and Backfilling Bookmarks

Glue supports rewinding a Spark ETL job bookmark to a prior run or resetting the entire bookmark state.

| Operation | Effect | Warning |
|---|---|---|
| Rewind | Moves bookmark back to a prior run's state to reprocess input from that point | Already written outputs are not automatically deleted |
| Reset | Clears bookmark state so the job can reread all supported input | Can create duplicates unless targets are cleaned or replaced |
| Pause with from/to | Processes an input range without modifying current bookmark state | Backfill outputs must be managed explicitly |

Resetting a bookmark:

~~~bash
aws glue reset-job-bookmark \
  --job-name sales-incremental-etl \
  --region ap-southeast-1
~~~

Resetting does not clean up outputs in S3, databases, or other targets. Glue only tracks input progress via bookmarks; targets are not rolled back automatically. Therefore, before resetting or rewinding:

1. Identify the run ID and data scope needing reprocessing.
2. Identify affected output partitions or target rows.
3. Choose partition overwrite, staging prefixes, merge/upsert, or business-key deduplication.
4. Capture snapshots or output versions needed for rollback.
5. Execute the backfill and reconcile metrics.
6. Promote results to serving zones only after validation passes.

If replays are frequent, consider separating backfill jobs from production incremental jobs. This prevents resetting a production job's bookmark and disturbing its active checkpoint.

Bookmark state is scoped to the job. Deleting a Glue job also deletes its bookmark state; recreating a job with the same name does not restore old state. Retain run history and backfill plans before deleting or replacing production jobs.

## 8. Output Idempotency and Failure Windows

Bookmarks and sink writes are not part of a single distributed transaction. For example:

1. The job reads file A.
2. The job successfully writes part of the data to the target.
3. The job fails before `job.commit()`.
4. On the next run, the bookmark was not updated, so file A is read again.

If the sink appends every record, the target can accumulate duplicates. Pipelines must design idempotent outputs using one of these approaches:

- Overwrite partitions keyed by business date or batch ID.
- Write to a staging prefix, validate, and then publish/commit metadata.
- Use merge/upsert by business key and version.
- Record event IDs and deduplicate downstream.
- Maintain manifests of published batches to prevent duplicate processing.

Example writing daily outputs:

~~~python
from datetime import date

run_date = date.today().isoformat()
target_path = f"s3://company-data/curated/sales/run_date={run_date}/"

# The pipeline should replace or publish this partition idempotently.
# Do not blindly append duplicate rows on every retry.
~~~

Distinguish retrying the same job run from an intentional backfill. If two concurrent runs write to the same partition, they can overwrite each other or leave inconsistent states. Use workflow/job concurrency limits, business locks, or partition ownership to avoid conflicts.

## 9. AWS Glue Workflows: Orchestrating Pipelines

A workflow is a collection of interdependent jobs, crawlers, and triggers. It models the pipeline as a directed graph, tracks execution status, and provides end-to-end observability.

Example:

~~~mermaid
flowchart TD
    A[EventBridge S3 arrival or schedule] --> B[Workflow start trigger]
    B --> C[Raw catalog crawler]
    C --> D{Crawler succeeded}
    D --> E[Bronze ETL job]
    E --> F{Bronze succeeded}
    F --> G[Silver ETL job]
    G --> H{Silver succeeded}
    H --> I[Quality check job]
    I --> J[Publish curated data]
~~~

Components:

- Job: runs ETL scripts, Spark, Python shell, or supported Glue workload types.
- Crawler: discovers schemas and updates metadata in the Data Catalog.
- Trigger: starts jobs/crawlers on schedules, on demand, on events, or on completion conditions.
- Workflow run: a single execution of the entire graph.
- Workflow run properties: key/value pairs used to pass state or parameters between steps.

Workflows provide a static view describing the design and a dynamic view showing live run status, including completed, running, or failed components.

## 10. Trigger Types in Workflows

There are three main start trigger types:

| Trigger | How It Starts | Example |
|---|---|---|
| Schedule | On a schedule or cron expression | Run ETL daily at 01:00 UTC |
| On demand | Operator invokes via console, API, or CLI | Run an on-demand backfill |
| EventBridge event | Upon receiving an event or event batch | New object arrives in S3 |

Conditional triggers inside a workflow can start a job or crawler when one or more component state conditions are met. For example, the Silver job runs only after the Bronze job succeeds and the crawler finishes updating the catalog. Conditions can be combined using `AND`/`OR` logic depending on trigger settings.

EventBridge event triggers can batch multiple events before starting a workflow. You can configure batch size and batch window; the maximum batch window is 900 seconds (15 minutes). Whichever threshold is reached first triggers the workflow. If batch conditions are omitted, the default batch size is 1.

Operational limits to remember:

- A workflow should have at most 100 jobs, crawlers, and triggers combined.
- You can set `MaxConcurrentRuns` to prevent multiple workflow runs from updating the same data concurrently.
- If the concurrency limit is exceeded, the workflow run is not started even when event conditions match; AWS Glue does not automatically retry workflow runs rejected due to concurrency limits.
- If an event/batch triggers a workflow run and that run fails, that event/batch is not reused to automatically launch a new run; the workflow waits for the next event/batch.
- Maintain a controlled redrive or event replay mechanism if the pipeline needs to retry the same input.

Do not set concurrency to 1 for every workflow out of habit. Choose based on whether runs write to independent partitions or risk updating the same target.

## 11. Workflow Run Properties and Passing Parameters

Workflow run properties are a key/value map shared among jobs within the same workflow run. They are useful for passing source paths, batch IDs, partition dates, schema versions, or run modes.

Example workflow properties:

~~~json
{
  "source_prefix": "s3://company-data/raw/sales/batch=2026-11-20/",
  "business_date": "2026-11-20",
  "run_mode": "incremental",
  "schema_version": "3"
}
~~~

Jobs can read the workflow name and run ID from arguments, then call the Glue API `GetWorkflowRunProperties` to retrieve properties. A job can also call `PutWorkflowRunProperties` to update values for downstream steps.

Python example:

~~~python
import sys
import boto3

from awsglue.utils import getResolvedOptions

args = getResolvedOptions(
    sys.argv,
    ["JOB_NAME", "WORKFLOW_NAME", "WORKFLOW_RUN_ID"]
)

glue = boto3.client("glue")

response = glue.get_workflow_run_properties(
    Name=args["WORKFLOW_NAME"],
    RunId=args["WORKFLOW_RUN_ID"]
)

run_properties = response["RunProperties"]
source_prefix = run_properties["source_prefix"]
business_date = run_properties["business_date"]

print(f"Processing {source_prefix} for {business_date}")
~~~

Never store plaintext secrets in workflow run properties because properties can appear in logs or be readable by multiple components. Use Glue Connections, Secrets Manager, or appropriate secrets management mechanisms. Workflow properties are also not a durable database replacement; they suit orchestration parameters within a single run.

## 12. Designing Workflows for Multi-Tier Data Lakes

A Bronze/Silver/Gold pipeline can be structured as follows:

| Tier | Responsibility | Input/Output |
|---|---|---|
| Landing/Raw | Receive raw files, preserve source schemas and metadata | Producer -> S3 raw |
| Bronze | Standardize encoding, baseline schemas, add ingestion metadata | S3 raw -> S3 bronze |
| Silver | Cleanse, deduplicate, join, and normalize business entities | Bronze -> S3 silver |
| Gold | Build aggregates, fact/dimension tables, and BI-ready datasets | Silver -> S3 gold |
| Catalog/Quality | Update Data Catalog and verify data quality | Catalog, quality results |

Workflows should divide components along failure boundaries and data ownership lines. A monolithic job is hard to retry step-by-step; too many tiny jobs increase startup overhead and orchestration costs.

A solid design:

- Triggers receive events or schedules at the start of the pipeline.
- Crawlers run only when schema discovery is genuinely required; they do not need to run every batch if schemas are stable.
- Bronze jobs use bookmarks or manifests to read incremental inputs.
- Silver jobs run only after Bronze completes and publishes successfully.
- Quality jobs validate counts, nulls, uniqueness, and business invariants.
- Gold jobs read only validated partitions.
- Workflow properties pass batch IDs and business dates end-to-end.
- `MaxConcurrentRuns` on workflows and jobs protects targets from concurrent overwrites.
- EventBridge/SNS or ticketing systems receive alerts when workflows fail.

## 13. Worker Types and DPUs

AWS Glue Spark jobs run on predefined worker types. The worker type determines each worker's DPUs, vCPUs, memory, and disk.

Common workers:

| Worker Type | DPU/M-DPU | vCPU | Memory | Characteristics |
|---|---:|---:|---:|---|
| G.1X | 1 | 4 | 16 GB | Standard ETL workloads |
| G.2X | 2 | 8 | 32 GB | Larger datasets/joins |
| G.4X | 4 | 16 | 64 GB | Heavy transforms, aggregations, and joins |
| G.8X | 8 | 32 | 128 GB | Large workloads requiring high compute/memory |
| G.12X | 12 | 48 | 192 GB | Very large workloads, Region/Glue version dependent |
| G.16X | 16 | 64 | 256 GB | Very large workloads, Region/Glue version dependent |
| R.1X | 1 | 4 | 32 GB | Memory-optimized |
| R.2X | 2 | 8 | 64 GB | Memory-optimized |
| R.4X | 4 | 16 | 128 GB | Memory-optimized |
| R.8X | 8 | 32 | 256 GB | Memory-optimized |

R workers provide a higher memory-to-vCPU ratio than G workers, suited for workloads with caching, aggregations, joins, or shuffles that frequently hit OOM. Do not select R workers merely because a dataset is large; confirm actual memory pressure via executor metrics and the Spark UI.

G.025X offers 0.25 DPU, 2 vCPUs, and 4 GB memory, primarily intended for low-volume Glue streaming jobs; do not use it as a general choice for batch Spark ETL.

G.12X, G.16X, and R workers have specific Glue version and Region availability constraints. Verify availability before designing production workflows. Larger workers can incur higher startup latency; scaling worker size does not guarantee faster jobs if the bottleneck lies in S3 listing, shuffles, JDBC throughput, or a single skewed task.

## 14. AWS Glue Auto Scaling

Auto Scaling lets Glue automatically scale workers up or down based on stage or micro-batch parallelism. Operators specify the worker type and maximum worker limit; Glue allocates workers within that range.

Auto Scaling supports AWS Glue version 3.0+ for ETL, interactive sessions, and streaming jobs. Supported worker types include G.1X, G.2X, G.4X, G.8X, G.12X, G.16X, R.1X, R.2X, R.4X, and R.8X; G.025X is for streaming jobs only. Standard DPUs do not support Auto Scaling.

Enabling Auto Scaling in job arguments:

~~~json
{
  "JobName": "sales-silver-etl",
  "Arguments": {
    "--enable-auto-scaling": "true",
    "--enable-metrics": "true"
  },
  "WorkerType": "G.2X",
  "NumberOfWorkers": 20
}
~~~

In this example, `NumberOfWorkers` acts as the maximum worker cap when Auto Scaling is enabled. Verify specific job configurations for your Glue version and API.

Auto Scaling helps when workloads vary in parallelism across stages: reading many files may need more workers, whereas a downstream join or write stage may need fewer. However, Auto Scaling cannot fix a single skewed task or an oversized partition. If only one executor is busy while others sit idle, revisit partitioning, skew, and the query plan.

Track worker utilization, executor metrics, `DPUSeconds`, stage durations, and the Spark UI to verify Auto Scaling actually reduces runtime or cost. Never compare only maximum worker counts across runs.

## 15. Execution Class FLEX

AWS Glue supports `STANDARD` and `FLEX` execution classes for certain Glue Spark jobs.

- `STANDARD`: prioritizes predictable startup and completion for workloads requiring consistent runtimes.
- `FLEX`: optimizes cost for workloads that can wait for spare capacity and tolerate variable start/completion times.

FLEX is supported for Spark ETL jobs (command type `glueetl`) on Glue 3.0+ with G.1X or G.2X worker types. Newer worker types such as G.12X, G.16X, and R.1X–R.8X do not support FLEX per current job property documentation.

FLEX fits:

- Backfills that do not require immediate completion.
- Daily batches with relaxed SLAs.
- Opportunistic jobs run when capacity is available.
- Workloads that can be safely retried or rerun without data side effects.

Do not use FLEX for pipelines with strict cutoff times, tight SLAs, or downstream dependencies waiting immediately. In a multi-job sequential workflow, one slow-starting FLEX job can delay the entire pipeline.

FLEX alters billing based on worker count and actual per-worker runtime; use current AWS pricing and job run metrics to compare total cost rather than looking only at execution duration.

## 16. Reducing Data Read Volume

The highest-leverage optimization is usually avoiding unnecessary reads. Inspect input scans before adding workers.

### 16.1. Partition Pruning and Pushdown

If an S3 dataset is partitioned by `year`, `month`, and `day`, filter at the Data Catalog level instead of reading all files and filtering in Spark.

~~~python
source = glue_context.create_dynamic_frame.from_catalog(
    database="raw_catalog",
    table_name="clickstream",
    push_down_predicate="year='2026' and month='11' and day='20'",
    transformation_ctx="clickstream_source"
)
~~~

`push_down_predicate` lets Glue list and read only matching partitions. For tables with huge partition counts, `catalogPartitionPredicate` combined with partition indexes enables server-side filtering in the Data Catalog and reduces listing overhead.

### 16.2. Projection and Predicate Pushdown

Read only required columns. Parquet and ORC are columnar formats that reduce I/O through column projection and predicate pushdown.

~~~python
df = spark.read.parquet("s3://company-data/silver/sales/")
filtered = (
    df.select("order_id", "customer_id", "order_date", "total_amount")
      .where("order_date >= DATE '2026-11-01'")
)
~~~

Filtering early before joins and aggregations reduces shuffled data. Use Parquet/ORC with suitable compression for analytical workloads; choose schemas and partition layouts driven by actual query patterns.

## 17. Small Files, Grouping, and Output Compaction

Too many small files create overhead in listing S3 objects, creating Spark tasks, and planning execution. A 100 GB dataset composed of millions of few-KB files can run far slower than the same volume stored in well-sized files.

For certain S3 input formats, Glue supports file grouping:

- `groupFiles = "inPartition"` groups files within each partition.
- `groupSize` sets the target group size in bytes.
- Glue automatically enables grouping in certain scenarios with over 50,000 input files.
- Grouping supports CSV, Ion, GrokLog, JSON, and XML; it does not support Avro, Parquet, or ORC per current documentation.

Example:

~~~python
source = glue_context.create_dynamic_frame.from_options(
    connection_type="s3",
    connection_options={
        "paths": ["s3://company-data/raw/events/"],
        "recurse": True,
        "groupFiles": "inPartition",
        "groupSize": "134217728"
    },
    format="json",
    transformation_ctx="raw_events_source"
)
~~~

Here `groupSize` is 128 MiB. Tune based on data volume, executor count, and format; do not apply blindly to every pipeline.

On output, `repartition()` or `coalesce()` can control output file counts. `coalesce(1)` commonly creates a single-task bottleneck and an oversized file for distributed workloads. Pick partition counts based on volume, parallelism, and query patterns. Periodic compaction jobs can consolidate small files across the data lake.

## 18. Optimizing Shuffles, Joins, and Data Skew

Shuffles occur when Spark exchanges data across executors, typically triggered by `join`, `groupBy`, `distinct`, `repartition`, or `sort`. Shuffles consume network, disk, and memory.

Principles:

- Filter and project early before wide transformations.
- Broadcast small dimension tables if they fit comfortably in executor memory.
- Repartition by join key when distributing data and avoiding repeated shuffles.
- Avoid unnecessary sorts or distinct operations.
- Watch for skew when a few keys hold most records.
- Use the Spark UI to locate stages with straggler tasks, disk spill, or heavy shuffle read/write.
- Size partition counts based on worker count, data volume, and task duration.

Data skew arises when one key holds far more data than others. A few tasks can run for a long time while most executors sit idle. Adding workers rarely fixes skew; consider key salting, splitting hot keys, broadcast joins, or two-stage aggregations. Salting changes grouping keys, so verify final results remain exact.

For Glue Spark jobs, inspect the Spark UI and event logs to examine DAGs, stages, task distribution, executor memory, and shuffle spill. Measure before and after changing a single parameter to attribute improvements accurately.

## 19. Metric-Driven Measurement and Optimization

AWS recommends an iterative tuning cycle:

1. Define targets: SLA, cost, throughput, or stability.
2. Measure a baseline via Glue metrics, CloudWatch logs, and the Spark UI.
3. Identify the bottleneck: scan, planning, shuffle, CPU, memory, I/O, or downstream.
4. Apply one targeted change.
5. Rerun on representative data and compare.
6. Repeat until targets are met.

Metrics to observe:

| Category | Metrics/Signals | Interpretation |
|---|---|---|
| Job | Duration, `DPUSeconds`, retries, failed runs | Actual runtime and resource consumption |
| Worker | Worker utilization, executor count, memory | Identify over-provisioning or resource shortages |
| Spark | Stage duration, task skew, shuffle read/write, spill | Locate processing bottlenecks |
| Source | Bytes scanned, files listed, JDBC read throughput | Detect excessive reads or slow sources |
| Sink | Write throughput, small files, commit latency | Detect output bottlenecks |
| Bookmark | Input range, run state, commit success | Verify incremental progress |
| Workflow | Run duration, component states, concurrency rejections | Identify slow or blocked steps |

Enable Glue job metrics and observability metrics as needed. Enable Spark UI event logs to inspect detailed DAGs. Retain logs and metrics long enough for investigation while controlling storage cost and avoiding sensitive data logging.

## 20. Managing Concurrency, Retries, and Costs

A workflow can execute concurrently multiple times unless bounded. This can cause two jobs to write to the same partition, consume excessive workers, or create bookmark race conditions.

Control concurrency at two levels:

- Workflow `MaxConcurrentRuns` caps simultaneous workflow runs.
- Per-job `MaxConcurrentRuns` caps simultaneous job runs.

For bookmarked jobs sharing source and target state, usually limit concurrent runs or enforce partition ownership so two runs never update the same data region concurrently.

Glue jobs can configure retry counts. Retries help only for transient failures when outputs can be retried safely. For schema, permission, or bad-data errors, repeated retries simply waste money. Set sensible timeouts; Glue job timeout maxes out at 7 days (10,080 minutes), while the default depends on Glue version. Never let hung jobs run indefinitely without alerts.

Cost control measures:

- Use bookmarks to avoid rereading successfully processed data.
- Use partition pruning, projection, and predicate pushdown to cut scans.
- Use Auto Scaling with a sensible max worker cap.
- Use FLEX for batches with flexible SLAs and supported worker types.
- Avoid unnecessary crawler runs.
- Limit workflow/job concurrency when targets cannot handle concurrent writes.
- Clean up logs, temporary files, and staging data via lifecycle policies.
- Compact small files to reduce downstream query costs.
- Tune retries and timeouts so you do not pay for doomed runs.

Never cut worker counts before knowing whether a job is I/O-bound or compute-bound. A smaller job running many times longer can cost more overall.

## 21. Common Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Job rereads old files | Bookmarks disabled, missing `transformation_ctx`, changed source/context, or modified object `LastModified` | Check job args, context, and source paths |
| JDBC misses new rows | Bookmark key not monotonically increasing or late-committing transactions | Check key semantics, choose proper sequence/timestamp, and backfill |
| JDBC misses `UPDATE`s | Bookmarks do not track changes to existing rows | Use CDC or full reconciliation |
| Job succeeds yet target has duplicates | Append output; prior run wrote partial data before failing prior to `job.commit()` | Design idempotent sinks, overwrite partitions, or merge |
| Bookmark reset leaves old data in target | Bookmarks do not manage target cleanup | Clean or replace targets via separate runbook |
| Workflow fails to start | Bad trigger, concurrency limit, or non-matching event pattern | Inspect trigger state, batch conditions, and workflow run history |
| Failed workflow run does not auto-retry | Event/batch already consumed or concurrency rejection | Redrive/replay events via dedicated mechanism |
| Worker hits OOM | Large joins/shuffles, skew, or excessive caching | Check Spark UI; reduce scans, mitigate skew, or switch to R workers |
| Many workers sit idle | Too few partitions or a sequential stage | Increase parallelism appropriately, repartition, or split workloads |
| Job slowed by small files | Too many tiny objects/tasks | Group inputs if format supported, compact outputs |
| High Glue cost | Excessive workers, long runtimes, unnecessary retries/crawlers | Measure `DPUSeconds`, use Auto Scaling/FLEX, and reduce data scanned |
| Corrupt bookmark state after script edit | Changed `transformation_ctx` or source mapping | Review state, keep contexts stable, or run controlled backfill/reset |

## 22. Hands-On: Incremental Sales Pipeline on S3

An enterprise receives daily sales files in `s3://company-data/raw/sales/`. The pipeline must process new files, standardize schemas, write Silver by date, and build Gold aggregates. Runs must never duplicate data on retries.

### Design

| Component | Configuration |
|---|---|
| Source | S3 raw sales partitioned by `year/month/day` |
| Bronze job | Glue Spark job, bookmark Enable, stable transformation context |
| Silver job | Deduplicate by event/order ID, write partitioned by business date |
| Gold job | Aggregate revenue by day and region |
| Trigger | EventBridge on object arrival or daily schedule |
| Workflow | Bronze succeeds -> Silver -> Quality check -> Gold |
| Resources | Start with G.1X/G.2X; Auto Scaling if workload varies |
| Backfill | Dedicated job or Pause/rewind by run ID |
| Monitoring | Job metrics, workflow graph, `DPUSeconds`, output counts |

### Implementation Steps

1. Create Glue Data Catalog database and table for raw sales.
2. Create the Bronze job with bookmark Enable and `transformation_ctx="sales_raw_source"`.
3. Read only needed partitions using `push_down_predicate`.
4. Standardize schemas and add `ingestion_date`, `source_file`, and `event_id`.
5. Write Bronze/Silver keyed by batch ID or idempotently overwritable partitions.
6. Call `job.commit()` only after sink writes and validation succeed.
7. Build the workflow with start trigger, Bronze, Silver, quality job, and Gold.
8. Pass `business_date` and `batch_id` via workflow run properties.
9. Configure concurrency limits so two runs never write to the same partition.
10. Enable Auto Scaling with a benchmarked maximum worker count.
11. Enable CloudWatch metrics and Spark UI to identify bottlenecks.
12. Test rerunning the same input; verify bookmarks skip old files and outputs do not duplicate.
13. Test a late-arriving file and a modified object; confirm the backfill procedure handles them properly.
14. Test reset/rewind in a test environment; confirm targets are managed independently of bookmarks.
15. Drill workflow failures and event redrive; verify the pipeline recovers without losing batches.

### Success Criteria

- Job reads only input within the expected incremental scope.
- Bookmarks commit only after output completes.
- Retries create no duplicates in the target.
- Workflows run downstream components only after dependencies succeed.
- Workflow concurrency prevents two runs from writing the same partition.
- Auto Scaling stays within configured maximum workers.
- Spark UI and CloudWatch metrics confirm bottlenecks have been identified.
- Backfills do not unexpectedly alter production checkpoints.
- Gold outputs reconcile against total revenue, order counts, and record counts.

## Conclusion

AWS Glue job bookmarks persist read progress to support incremental ETL. S3 bookmarks rely on object `LastModified` timestamps; JDBC bookmarks rely on bookmark keys and do not automatically detect all `UPDATE`/`DELETE` operations. Proper `job.init`, stable `transformation_ctx`, and timely `job.commit` are critical. Resetting or rewinding modifies only bookmark state without cleaning already written outputs.

AWS Glue workflows orchestrate jobs, crawlers, and triggers on schedules, on demand, via EventBridge, or on completion conditions. Run properties pass parameters between steps; concurrency limits protect targets and control costs. However, events or workflow runs that are rejected or fail need an explicit redrive mechanism.

ETL optimization starts by reducing data read, small files, and shuffles before tuning worker capacity. Auto Scaling, G/R worker types, and FLEX each have specific support conditions. Measure with Glue metrics, CloudWatch, and the Spark UI before changing configurations. A production pipeline combines bookmarks, output idempotency, workflow orchestration, monitoring, and backfill/retry runbooks.

## References

- [Tracking processed data using job bookmarks](https://docs.aws.amazon.com/glue/latest/dg/monitor-continuations.html)
- [Using job bookmarks in AWS Glue scripts](https://docs.aws.amazon.com/glue/latest/dg/programming-etl-connect-bookmarks.html)
- [Troubleshooting Glue bookmark and transformation context errors](https://docs.aws.amazon.com/glue/latest/dg/glue-troubleshooting-errors.html)
- [Overview of workflows in AWS Glue](https://docs.aws.amazon.com/glue/latest/dg/workflows_overview.html)
- [Creating and building out workflows manually](https://docs.aws.amazon.com/glue/latest/dg/creating_running_workflows.html)
- [AWS Glue workflows API](https://docs.aws.amazon.com/glue/latest/dg/aws-glue-api-workflow.html)
- [Getting and setting workflow run properties](https://docs.aws.amazon.com/glue/latest/dg/workflow-run-properties-code.html)
- [Using Auto Scaling for AWS Glue](https://docs.aws.amazon.com/glue/latest/dg/auto-scaling.html)
- [AWS Glue worker types](https://docs.aws.amazon.com/glue/latest/dg/worker-types.html)
- [Configuring job properties for Spark jobs](https://docs.aws.amazon.com/glue/latest/dg/add-job.html)
- [AWS Glue job runs and execution class](https://docs.aws.amazon.com/glue/latest/dg/aws-glue-api-jobs-runs.html)
- [Managing partitions for ETL output](https://docs.aws.amazon.com/glue/latest/dg/aws-glue-programming-etl-partitions.html)
- [Optimizing reads with pushdown in AWS Glue ETL](https://docs.aws.amazon.com/glue/latest/dg/aws-glue-programming-pushdown.html)
- [Reading input files in larger groups](https://docs.aws.amazon.com/glue/latest/dg/grouping-input-files.html)
- [Connection options and the AWS Glue S3 Lister](https://docs.aws.amazon.com/glue/latest/dg/aws-glue-programming-etl-connect.html)
- [Improving performance for AWS Glue Spark jobs](https://docs.aws.amazon.com/glue/latest/dg/tuning-aws-glue-for-apache-spark.html)
- [Best practices for performance tuning AWS Glue for Apache Spark jobs](https://docs.aws.amazon.com/prescriptive-guidance/latest/tuning-aws-glue-for-apache-spark/introduction.html)
- [Strategies for tuning Spark job performance](https://docs.aws.amazon.com/prescriptive-guidance/latest/tuning-aws-glue-for-apache-spark/performance-tuning-strategies.html)
- [AWS Glue pricing](https://aws.amazon.com/glue/pricing/)
