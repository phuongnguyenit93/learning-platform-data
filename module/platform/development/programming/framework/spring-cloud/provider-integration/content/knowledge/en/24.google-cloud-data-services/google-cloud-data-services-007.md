# Integrating BigQuery with Client, Template, and Batch Data Loading

## Learning Objectives

In the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, Spring Boot integrates managed services from AWS, Azure, and Google Cloud through their respective Spring Cloud libraries. On Google Cloud, **BigQuery** is a data warehouse for large-scale data analytics, SQL queries, reporting, and batch data processing.

This lesson focuses on integrating BigQuery in Spring Boot applications:

1. Configuring the Spring Framework on Google Cloud BigQuery starter and Application Default Credentials.
2. Using the BigQuery Java client to run GoogleSQL, pass parameters, and read results.
3. Understanding datasets, tables, schemas, locations, partitioning, and clustering at the application level.
4. Using BigQueryTemplate and BigQueryOperations to ingest data from InputStreams.
5. Distinguishing load jobs from the BigQuery Storage Write API.
6. Batch loading CSV, newline-delimited JSON, Avro, ORC, and Parquet from Cloud Storage.
7. Choosing write dispositions, schemas, and job IDs for safe retries.
8. Configuring least-privilege IAM, monitoring costs, quotas, and job status.
9. Testing with mocks and sandbox datasets in CI environments.

> **Scope:** Examples reference Spring Framework on Google Cloud 8.2.1 and the BigQuery Java client managed by the BOM. The Spring Framework on Google Cloud 8.x branch is compatible with Spring Boot 4.0/4.1. If your project uses Spring Boot 3.5 or 3.4, select the corresponding BOM branch rather than copying version 8.x verbatim.

## 1. BigQuery in Spring Boot Architecture

### 1.1. Which Workloads Fit BigQuery?

BigQuery is a fully managed columnar analytics data warehouse. Applications commonly use BigQuery to:

- Aggregate orders, revenue, visits, or usage behavior.
- Run scheduled reports and dashboards.
- Analyze event history from Pub/Sub, Cloud Storage, or transactional systems.
- Store standardized data for BI, machine learning, or data science.
- Run ELT/ETL and query data across multiple sources.

BigQuery is not a default replacement for an application's transactional database. Small CRUD operations, per-request order status updates, or business transactions usually belong in Cloud SQL, Spanner, or another transactional database. BigQuery fits when an application reads/writes analytical data in bulk sets.

### 1.2. Core Components

| Component | Role | Example |
| --- | --- | --- |
| Project | Resource, IAM, and billing boundary | rental-analytics |
| Dataset | Group of tables sharing location and policies | sales_reporting |
| Table | Stores data per schema | orders_daily |
| Schema | Defines field names, types, and modes | order_id STRING, amount NUMERIC |
| Query job | Executes GoogleSQL and stores result metadata | Revenue aggregation |
| Load job | Loads files into a table from Cloud Storage or supported sources | End-of-day CSV |
| Storage Write API | Writes records over gRPC streams | Continuous incoming events |

Datasets have a location. Query or load jobs must be compatible with the location of the involved data. For ingestion flows from Cloud Storage, align bucket and dataset locations per BigQuery requirements to avoid compatibility errors or cross-region transfer charges.

### 1.3. Integration Architecture

~~~mermaid
flowchart TD
    APP["Spring Boot application"] --> STARTER["spring-cloud-gcp-starter-bigquery"]
    STARTER --> CLIENT["BigQuery Java client"]
    STARTER --> TEMPLATE["BigQueryTemplate"]
    CLIENT --> QUERY["Query jobs / table metadata"]
    CLIENT --> LOAD["Load jobs"]
    TEMPLATE --> CSV["CSV / InputStream load"]
    TEMPLATE --> JSON["NDJSON / Storage Write API"]
    GCS["Cloud Storage files"] --> LOAD
    QUERY --> BQ["BigQuery dataset and tables"]
    LOAD --> BQ
    CSV --> BQ
    JSON --> BQ
    ADC["ADC + runtime service account"] --> CLIENT
~~~

There are three primary access paths:

- **BigQuery client:** controls query jobs, tables, datasets, schemas, load jobs, and metadata.
- **BigQueryTemplate:** dataset-scoped wrapper convenient for loading InputStreams and JSON streams.
- **Spring Integration handler:** feeds files into BigQuery from a message pipeline when the application already uses Spring Integration.

There is no JPA-style Spring Data repository for BigQuery. Applications typically use the client or template to run queries and ingestion.

## 2. Dependencies and Spring Boot Configuration

### 2.1. Importing the BOM

In Maven, import the Spring Framework on Google Cloud BOM in dependencyManagement:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.google.cloud</groupId>
            <artifactId>spring-cloud-gcp-dependencies</artifactId>
            <version>${spring-cloud-gcp.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Choose the spring-cloud-gcp.version value per the Spring Boot compatibility matrix. The BOM manages compatible client and Spring Cloud GCP module versions together; do not specify individual starter versions unless there is a special reason.

### 2.2. BigQuery Starter

Add the dependency:

~~~xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>spring-cloud-gcp-starter-bigquery</artifactId>
</dependency>
~~~

The starter provides auto-configuration for the BigQuery client and required credentials. When present, the application can inject BigQuery and BigQueryTemplate beans.

Even if you only need the Java client, the starter can still be a simple way to get a client pre-configured with project ID and credentials. You do not need to manually instantiate BigQueryOptions in every service.

### 2.3. Configuring application.yml

Example:

~~~yaml
spring:
  cloud:
    gcp:
      project-id: rental-analytics
      bigquery:
        enabled: true
        project-id: rental-analytics
        dataset-name: sales_reporting
        json-writer-batch-size: 1000
        thread-pool-size: 4
~~~

Key properties:

| Property | Meaning |
| --- | --- |
| spring.cloud.gcp.bigquery.dataset-name | Dataset used by BigQueryTemplate and BigQueryFileMessageHandler; required when using template/handler |
| spring.cloud.gcp.bigquery.enabled | Enables/disables BigQuery auto-configuration; defaults to true |
| spring.cloud.gcp.bigquery.project-id | Project dedicated to BigQuery if different from GCP core project ID |
| spring.cloud.gcp.bigquery.credentials.location | Custom credentials file if different from default ADC |
| spring.cloud.gcp.bigquery.json-writer-batch-size | Batch size for BigQueryJsonDataWriter; defaults to 1000 |
| spring.cloud.gcp.bigquery.thread-pool-size | ThreadPoolTaskScheduler used by BigQueryTemplate; defaults to 4 |

Property names in the reference may use camelCase like datasetName; Spring Boot relaxed binding permits kebab-case dataset-name in YAML.

Do not place service account private keys in Git, Docker images, or application.yml. Prefer Application Default Credentials and a service account attached to the workload. Use custom credentials only when specifically required and store them in a controlled secret management system.

### 2.4. Local Development and Production Identity

Local developers can configure ADC with the Google Cloud CLI and log in with an account having appropriate permissions. On Cloud Run, GKE, or Compute Engine, attach a service account/workload identity to the runtime.

The same code path can run locally and in production because the starter obtains credentials from CredentialsProvider. Code should not read key files from hardcoded paths or embed credentials in constructors.

## 3. BigQuery Client: Running GoogleSQL Queries

### 3.1. Injecting the BigQuery Bean

GcpBigQueryAutoConfiguration creates the BigQuery bean using the project ID and credentials resolved from the environment.

~~~java
import com.google.cloud.bigquery.BigQuery;
import org.springframework.stereotype.Service;

@Service
public class AnalyticsQueryService {

    private final BigQuery bigQuery;

    public AnalyticsQueryService(BigQuery bigQuery) {
        this.bigQuery = bigQuery;
    }
}
~~~

The client is a shared object for BigQuery operations. Do not instantiate a new client per query request; let Spring manage the bean and its lifecycle.

### 3.2. Querying with Named Parameters

Example querying orders for a customer:

~~~java
import com.google.cloud.bigquery.BigQuery;
import com.google.cloud.bigquery.FieldValueList;
import com.google.cloud.bigquery.JobId;
import com.google.cloud.bigquery.QueryJobConfiguration;
import com.google.cloud.bigquery.QueryParameterValue;
import com.google.cloud.bigquery.TableResult;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

public List<OrderMetric> findOrders(
        BigQuery bigQuery, String location,
        String customerId, long minimumAmount)
        throws InterruptedException {

    String sql = """
        SELECT order_id, status, total_amount
        FROM `rental-analytics.sales_reporting.orders`
        WHERE customer_id = @customerId
          AND total_amount >= @minimumAmount
        ORDER BY created_at DESC
        LIMIT 100
        """;

    QueryJobConfiguration queryConfig =
            QueryJobConfiguration.newBuilder(sql)
                    .addNamedParameter(
                            "customerId",
                            QueryParameterValue.string(customerId))
                    .addNamedParameter(
                            "minimumAmount",
                            QueryParameterValue.int64(minimumAmount))
                    .setUseLegacySql(false)
                    .setMaximumBytesBilled(2_000_000_000L)
                    .build();

    JobId queryJobId = JobId.newBuilder()
            .setJob("orders_query_" + UUID.randomUUID())
            .setLocation(location)
            .build();
    TableResult rows = bigQuery.query(queryConfig, queryJobId);

    List<OrderMetric> result = new ArrayList<>();
    for (FieldValueList row : rows.iterateAll()) {
        result.add(new OrderMetric(
                row.get("order_id").getStringValue(),
                row.get("status").getStringValue(),
                row.get("total_amount").getLongValue()));
    }

    return result;
}
~~~

QueryParameterValue provides typed factories such as string, int64, numeric, timestamp, bool, and corresponding array/struct factories. Pick the exact BigQuery type of the field.

Named parameters are referenced via `@parameterName`. Positional parameters `?` can also be used, though a single query cannot mix named and positional parameters.

### 3.3. Why Bind Parameters?

Do not concatenate user input directly into SQL:

~~~java
// Unsafe: input can alter the structure of the SQL statement.
String sql = "SELECT * FROM orders WHERE customer_id = '" + customerId + "'";
~~~

Use parameters instead:

~~~sql
SELECT order_id, status
FROM `rental-analytics.sales_reporting.orders`
WHERE customer_id = @customerId;
~~~

Parameters prevent input values from becoming SQL syntax and keep BigQuery from recording sensitive parameter values in query logs. Parameters replace **values** only, not project, dataset, table, or column names. If a table name is chosen dynamically, validate it against an allowlist or internal mapping.

### 3.4. Reading Results and Pagination

TableResult can be iterated via iterateAll() to read all rows. For large results, avoid materializing all rows into a List unnecessarily.

Approaches:

- Select exact columns instead of SELECT *.
- Use LIMIT when the UI only needs one page.
- Use pageSize or paging APIs when reading results page by page.
- Perform aggregations in SQL rather than pulling millions of rows into the JVM to compute.
- If large results must feed a processing pipeline, evaluate the BigQuery Storage Read API or export jobs.

Do not hold a TableResult and turn a huge dataset into an in-heap object graph. Set result bounds and design queries around API needs.

### 3.5. Dataset Location and Query Jobs

Jobs must run in a location compatible with the queried datasets. For single-region datasets or locations outside US/EU multi-regions, the BigQuery Java client requires specifying the location on JobId when calling the `query(QueryJobConfiguration, JobId, ...)` overload.

When designing services, store the location alongside dataset metadata or environment config. Do not assume jobs always run in US. If a query reads multiple datasets, the datasets must satisfy BigQuery's location compatibility rules.

### 3.6. Controlling Bytes and Query Costs

Before running production queries:

- Use setMaximumBytesBilled as a protective cap per use case.
- Use dry-run query jobs to estimate bytes processed before execution.
- Filter on partition columns to avoid scanning unnecessary partitions.
- Select only needed fields.
- Use partitioning and clustering tailored to query patterns.
- Monitor bytes processed, bytes billed, slot milliseconds, and job status.

A dry run is a query job configured with setDryRun(true); it returns no data. Use bigQuery.create(JobInfo.of(dryRunConfig)) to submit a dry-run job and inspect statistics. Do not call BigQuery.query(...) to retrieve results from a dry run.

## 4. Schemas and Java Data Mapping

### 4.1. BigQuery Schema as a Data Contract

A BigQuery table has a schema consisting of field names, data types, and modes (NULLABLE, REQUIRED, REPEATED). An explicit schema enforces a data contract when loading files or reading results.

Common types:

| BigQuery Type | Suggested Java Type | Notes |
| --- | --- | --- |
| STRING | String | UTF-8 text |
| INT64 | Long | 64-bit integer |
| NUMERIC | BigDecimal | Suits exact decimal numbers |
| FLOAT64 | Double | Floating-point number |
| BOOL | Boolean | Boolean |
| DATE | LocalDate or ISO string | Date without timezone |
| DATETIME | LocalDateTime | Date and time without timezone |
| TIMESTAMP | Instant or Timestamp | Absolute point in time |
| BYTES | byte[] | Binary data |
| ARRAY<T> | List<T> | Field mode REPEATED |
| STRUCT | POJO/Map or nested field mapping | Nested record |

When reading a FieldValue, choose the accessor matching the field type—such as getStringValue(), getLongValue(), getNumericValue(), or getBooleanValue(). Do not coerce every value to String and re-parse it when the client already provides a typed accessor.

### 4.2. Creating a Schema in Java

~~~java
import com.google.cloud.bigquery.Field;
import com.google.cloud.bigquery.Schema;
import com.google.cloud.bigquery.StandardSQLTypeName;

Schema orderSchema = Schema.of(
        Field.of("order_id", StandardSQLTypeName.STRING),
        Field.of("customer_id", StandardSQLTypeName.STRING),
        Field.of("status", StandardSQLTypeName.STRING),
        Field.of("total_amount", StandardSQLTypeName.INT64),
        Field.of("created_at", StandardSQLTypeName.TIMESTAMP));
~~~

This schema can be used when creating tables or passed to load APIs. For required fields, nested records, repeated fields, or special precision, use Field builders to declare modes and subfields explicitly.

### 4.3. No Spring Data Repository for BigQuery

BigQuery is not integrated like a JPA repository or Spring Data document repository. Applications use:

- BigQuery to run queries, create datasets/tables, and run load jobs.
- BigQueryTemplate for convenient data ingestion operations.
- BigQueryOperations if services should depend on the template abstraction.
- Java DTOs/records to map query results.

Do not design BigQuery like an OLTP repository calling save(entity) for individual CRUD operations. Think in terms of query jobs, load jobs, batch ingestion, and analytics results.

## 5. BigQueryTemplate and BigQueryOperations

### 5.1. Role of the Template

BigQueryTemplate is a wrapper over the BigQuery client that simplifies data loading operations. The auto-configured instance is scoped to a single dataset taken from spring.cloud.gcp.bigquery.dataset-name.

Therefore, when calling:

~~~java
bigQueryTemplate.writeDataToTable(
        "orders_stage",
        inputStream,
        FormatOptions.csv());
~~~

orders_stage is the table name inside the configured dataset. If you need to write to a different dataset, use a template/client explicitly configured for that dataset or use the BigQuery client directly with TableId.

### 5.2. Loading CSV from InputStream

~~~java
import com.google.cloud.bigquery.FormatOptions;
import com.google.cloud.bigquery.Job;
import com.google.cloud.spring.bigquery.core.BigQueryTemplate;
import org.springframework.stereotype.Service;

import java.io.InputStream;
import java.util.concurrent.CompletableFuture;

@Service
public class BigQueryTemplateImportService {

    private final BigQueryTemplate bigQueryTemplate;

    public BigQueryTemplateImportService(
            BigQueryTemplate bigQueryTemplate) {
        this.bigQueryTemplate = bigQueryTemplate;
    }

    public CompletableFuture<Job> loadCsv(
            String tableName, InputStream csvInputStream) {

        return bigQueryTemplate.writeDataToTable(
                tableName,
                csvInputStream,
                FormatOptions.csv());
    }
}
~~~

writeDataToTable returns a CompletableFuture<Job>. The future completes when the load job finishes. If called in a synchronous batch worker, wait on the future and check status. When processing asynchronously, keep the InputStream open until the future completes.

### 5.3. Loading CSV with an Explicit Schema

When the table does not yet exist or schema control is needed, also pass a Schema:

~~~java
CompletableFuture<Job> future =
        bigQueryTemplate.writeDataToTable(
                "orders_stage",
                csvInputStream,
                FormatOptions.csv(),
                orderSchema);

Job job = future.get();
if (job.getStatus() != null && job.getStatus().getError() != null) {
    throw new IllegalStateException(
            "BigQuery load failed: " + job.getStatus().getError());
}
~~~

This is a convenient overload when the application already defines a Java schema. For CSV files with headers, ensure the parser is configured to skip the header. If you need skipLeadingRows, delimiter, quote, or null markers, use CsvOptions in the load job client API.

### 5.4. Loading Newline-Delimited JSON via Storage Write API

BigQueryTemplate.writeJsonStream uses the BigQuery Storage Write API to write newline-delimited JSON (NDJSON). Each line is an independent JSON object:

~~~json
{"order_id":"ord-1001","customer_id":"cus-42","status":"PAID","total_amount":250000}
{"order_id":"ord-1002","customer_id":"cus-77","status":"PENDING","total_amount":180000}
~~~

Example:

~~~java
var future = bigQueryTemplate.writeJsonStream(
        "orders_events",
        jsonInputStream);

var response = future.get();

if (!response.isSuccessful()) {
    throw new IllegalStateException(
            "Storage Write API errors: " + response.getErrors());
}
~~~

If the table does not yet exist, you can use the overload accepting a schema:

~~~java
var future = bigQueryTemplate.writeJsonStream(
        "orders_events",
        jsonInputStream,
        orderSchema);

var response = future.get();
if (!response.isSuccessful()) {
    throw new IllegalStateException(
            "Storage Write API errors: " + response.getErrors());
}
~~~

When no schema is passed, the table must already exist because the Storage Write API does not auto-create tables in that overload. When passing a schema, the template can create the table with that schema.

WriteApiResponse differs from Job: it is the write result from the Storage Write API. Check isSuccessful() and errors; do not inspect the response as if it were a load job.

### 5.5. Template Batch Size and Scheduler

Two configuration properties affect the template:

- json-writer-batch-size: number of records per JSON write batch; defaults to 1000.
- thread-pool-size: size of the ThreadPoolTaskScheduler used for polling jobs; defaults to 4.

A batch size that is too small increases overhead; too large can increase memory usage or latency. Benchmark against record size, throughput, and workload limits rather than tuning arbitrarily.

### 5.6. BigQueryTemplate Write Disposition

The template supports configuring:
- WRITE_APPEND: appends data to the table.
- WRITE_TRUNCATE: overwrites existing data.
- WRITE_EMPTY: writes only if the table has no data yet.

By default, BigQueryTemplate uses append. The template exposes setWriteDisposition(...) and setCreateDisposition(...); these mutate the template instance configuration. If concurrent requests require different dispositions, do not mutate singleton bean state across concurrent requests. Use the BigQuery client with a dedicated LoadJobConfiguration per job for explicit disposition control.

## 6. Load Jobs: Batch Loading Data from Cloud Storage

### 6.1. When Should You Use a Load Job?

Load jobs fit when data is already staged into files and latency need not be sub-second:

- End-of-day CSV ingestion.
- Loading Parquet/Avro files standardized by ETL.
- Loading hundreds of files by prefix in Cloud Storage.
- Replacing periodic snapshot tables.
- Historical backfills or importing data from external systems.

BigQuery supports batch loads from Cloud Storage in CSV, newline-delimited JSON, Avro, ORC, and Parquet formats. You can load from local files via the client library, though for large files it is better to stage files in Cloud Storage first.

### 6.2. Load Jobs Are Atomic

A load job executes as a single job. The load outcome is atomic: if the job fails, partial data from the job is not exposed; if the job succeeds, data is loaded according to the chosen write disposition.

This fits batch ETL well because downstream queries can wait for job completion before reading the destination table.

Do not confuse load jobs with row-by-row streaming inserts. Load jobs do not issue one request per record; BigQuery processes files in batch.

### 6.3. Loading CSV from Cloud Storage with the BigQuery Java Client

The example below uses an explicit schema and skips the header line:

~~~java
import com.google.cloud.bigquery.BigQuery;
import com.google.cloud.bigquery.CsvOptions;
import com.google.cloud.bigquery.Field;
import com.google.cloud.bigquery.Job;
import com.google.cloud.bigquery.JobId;
import com.google.cloud.bigquery.JobInfo;
import com.google.cloud.bigquery.LoadJobConfiguration;
import com.google.cloud.bigquery.Schema;
import com.google.cloud.bigquery.StandardSQLTypeName;
import com.google.cloud.bigquery.TableId;

public Job loadOrdersCsv(
        BigQuery bigQuery,
        String projectId,
        String datasetId,
        String location,
        String tableName,
        String sourceUri,
        String batchId,
        int attempt) throws InterruptedException {

    Schema schema = Schema.of(
            Field.of("order_id", StandardSQLTypeName.STRING),
            Field.of("customer_id", StandardSQLTypeName.STRING),
            Field.of("status", StandardSQLTypeName.STRING),
            Field.of("total_amount", StandardSQLTypeName.INT64));

    CsvOptions csvOptions =
            CsvOptions.newBuilder()
                    .setSkipLeadingRows(1)
                    .build();

    TableId destination = TableId.of(
            projectId, datasetId, tableName);

    LoadJobConfiguration loadConfig =
            LoadJobConfiguration.newBuilder(
                    destination, sourceUri, csvOptions)
                    .setSchema(schema)
                    .setCreateDisposition(
                            JobInfo.CreateDisposition.CREATE_IF_NEEDED)
                    .setWriteDisposition(
                            JobInfo.WriteDisposition.WRITE_APPEND)
                    .build();

    if (!batchId.matches("[A-Za-z0-9_-]+") || attempt < 1) {
        throw new IllegalArgumentException(
                "batchId must use letters, digits, underscore or dash; attempt must be positive");
    }

    JobId jobId = JobId.newBuilder()
            .setJob("load_orders_" + batchId + "_a" + attempt)
            .setLocation(location)
            .build();

    Job job = bigQuery.create(
            JobInfo.newBuilder(loadConfig)
                    .setJobId(jobId)
                    .build());

    Job completed = job.waitFor();

    if (completed == null) {
        throw new IllegalStateException(
                "BigQuery load job no longer exists");
    }

    if (completed.getStatus().getError() != null) {
        throw new IllegalStateException(
                "BigQuery load failed: "
                        + completed.getStatus().getError());
    }

    return completed;
}
~~~

sourceUri takes the form `gs://bucket/path/file.csv`. When using wildcards, BigQuery supports a single `*` per URI; do not use wildcards in bucket names. Verify that the matched objects belong strictly to the batch being loaded.

### 6.4. Write Disposition

| Disposition | Behavior | Use case |
| --- | --- | --- |
| WRITE_APPEND | Appends rows to the table | Loading a new partition/batch |
| WRITE_TRUNCATE | Deletes existing data then writes new data | Replacing a snapshot or staging table |
| WRITE_EMPTY | Writes only if table is empty | Initial load, preventing overwrites |

Do not set WRITE_TRUNCATE on a production table if the goal is solely appending data. For snapshot pipelines, load into a staging table, validate data, and then replace or publish the table/view.

### 6.5. Create Disposition

| Disposition | Behavior |
| --- | --- |
| CREATE_IF_NEEDED | Creates the table if it does not exist |
| CREATE_NEVER | Job fails if the table does not exist |

Choose create disposition explicitly to avoid unexpectedly creating tables. When schema contracts are managed via migrations, use CREATE_NEVER so pipelines do not silently create malformed tables.

### 6.6. File Formats

| Format | When suitable | Notes |
| --- | --- | --- |
| CSV | Simple exchange, easily inspectable files | Must handle delimiter, quote, header, and encoding |
| NDJSON | Independent JSON records, nested objects | Each line is one JSON object |
| Avro | Batch data with schema, nested/repeated fields | Often fits schema-bound data ingestion |
| Parquet | Columnar analytics, efficient compression | Fits large-scale data pipelines |
| ORC | Columnar format in Hadoop ecosystems | Verify schema and codec compatibility |

For Avro, Parquet, and ORC, schemas can often be derived from the file format. For CSV and JSON, consider an explicit schema when a stable contract is required.

### 6.7. Safe Load Job Retries Using Job IDs

When the network drops after the client submits a job, the application may not know whether BigQuery accepted the job. Generating a brand-new job ID immediately can load the same batch twice.

Safe design:

1. Generate a deterministic batch ID and attempt number for the specific run.
2. Submit the load job with a job ID derived from the batch ID and attempt number.
3. If a timeout leaves job creation status ambiguous, look up the same job ID and location.
4. If the job is still running or already succeeded, continue polling/finish the batch instead of creating another job.
5. If the job definitively failed and must re-run, increment the attempt number; do not generate a new ID solely because the client timed out.

Resubmitting or checking with the same job ID prevents spawning duplicate independent jobs for the same attempt. The load snippet above takes a deterministic batchId, attempt, and dataset location. For jobs in locations outside US/EU, you must specify location when creating or looking up jobs; always pass location explicitly to avoid relying on defaults.

### 6.8. Dataset and Cloud Storage Bucket Locations

BigQuery datasets have a location. The Cloud Storage bucket holding source files must reside in a location compatible with the destination dataset. Co-locate buckets and datasets in the same region or a BigQuery-supported location pair.

If bucket and dataset locations differ, operations may fail or incur cross-region transfer fees. Do not choose locations solely based on where the application runs; weigh data residency, latency, cost, and which datasets will be joined in queries.

## 7. Storage Write API and Streaming Ingestion

### 7.1. When to Use the Storage Write API?

The Storage Write API uses bidirectional gRPC streams to write records into BigQuery. It fits when:
- Data is generated continuously.
- Lower latency than batch load jobs is needed.
- Multiple workers write data concurrently.
- Stream, offset, and batched commit management is required.
- Schema update detection or CDC upserts are needed per API capabilities.

Spring's BigQueryTemplate.writeJsonStream provides a convenient NDJSON ingestion path. For advanced workloads, use BigQueryWriteClient directly and manage write streams.

### 7.2. Comparing Load Jobs and Storage Write API

| Criterion | Load job | Storage Write API |
| --- | --- | --- |
| Data source | Files or URIs in Cloud Storage | Records sent over gRPC streams |
| Latency | Batch; waits for job completion | Lower; suits continuous ingestion |
| Processing unit | Job | Write stream and append requests |
| Atomicity | A single load job is atomic | Pending streams can commit multiple streams atomically |
| Retry | Uses deterministic job IDs | Uses stream offsets and matching retry semantics |
| Use case | Nightly loads, backfills, file imports | Event ingestion, near-real-time pipelines |

The Storage Write API has different stream types with different semantics. The default stream writes data with fast visibility and at-least-once semantics. Committed streams support offsets so clients can retry appends without duplicating within that stream. Pending streams buffer data until finalized and batch-committed; multiple pending streams can be committed atomically.

Spring Framework on Google Cloud provides BigQueryJsonDataWriter, documented as a helper for exactly-once delivery mode. BigQueryTemplate uses this helper in its JSON write path. When using BigQueryWriteClient directly, the application must choose stream types, track offsets, and retry with matching semantics; do not assume every Storage Write API call is automatically exactly-once.

Do not label every Storage Write API operation as exactly-once. Semantics depend on stream type, offsets, and client retry behavior. For BigQueryTemplate.writeJsonStream, refer to Spring Cloud GCP's BigQueryJsonDataWriter; when using the client API directly, design streams and offsets explicitly.

### 7.3. Pending Streams for Atomic Batches

A multi-worker batch can follow this sequence:

1. Create pending write streams.
2. Partition the batch and assign slices to workers.
3. Each worker appends rows to its own stream.
4. Finalize each stream after writing finishes.
5. Wait for all workers to succeed.
6. Call BatchCommitWriteStreams to publish the entire batch.

Pending data is not visible to queries before commit. If a worker fails, retry only that stream slice using saved checkpoints/offsets. Once finalized, no additional rows can be appended to that stream.

Pending streams have finalize/commit deadlines and buffer quotas; do not treat them as long-term storage. For very large batch jobs, consider a load job from Cloud Storage since it is simpler when data already exists as files.

### 7.4. When Do You Need the BigQuery Storage Write Client Directly?

Use BigQueryWriteClient when you need control over:
- Creating specific stream types.
- Appending rows and offsets.
- Finalizing streams.
- Batch commits.
- Checkpoint-based retries.
- Parallel writers and backpressure.

This is a lower-level API than BigQueryTemplate. Implement it only when throughput/consistency demands stream-level control; for straightforward NDJSON streams, the template is usually sufficient.

## 8. Spring Integration with BigQueryFileMessageHandler

Spring Framework on Google Cloud includes BigQueryFileMessageHandler to ingest data into BigQuery inside a Spring Integration pipeline.

The handler accepts payloads such as:
- java.io.File
- byte[]
- org.springframework.core.io.Resource
- java.io.InputStream

The handler reads message headers to determine table and format:

| Header | Meaning |
| --- | --- |
| BigQuerySpringMessageHeaders.TABLE_NAME | Table name in the configured dataset |
| BigQuerySpringMessageHeaders.FORMAT_OPTIONS | Payload format, e.g., CSV or JSON |

You can also configure table name and format options directly on the handler instead of via message headers.

Example ServiceActivator configuration:

~~~java
import com.google.cloud.bigquery.FormatOptions;
import com.google.cloud.spring.bigquery.core.BigQueryTemplate;
import com.google.cloud.spring.bigquery.integration.outbound.BigQueryFileMessageHandler;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageHandler;

@Bean
DirectChannel bigQueryWriteDataChannel() {
    return new DirectChannel();
}

@Bean
DirectChannel bigQueryJobReplyChannel() {
    return new DirectChannel();
}

@Bean
@ServiceActivator(inputChannel = "bigQueryWriteDataChannel")
MessageHandler bigQueryFileHandler(BigQueryTemplate template) {
    BigQueryFileMessageHandler handler =
            new BigQueryFileMessageHandler(template);
    handler.setFormatOptions(FormatOptions.csv());
    handler.setOutputChannel(bigQueryJobReplyChannel());
    return handler;
}
~~~

### 8.1. Handling Asynchronous Replies

By default, the handler runs asynchronously (`setSync(false)`) and sends a `CompletableFuture<Job>` to the reply channel. The future completes when the load job finishes.

If `setSync(true)` is enabled, the handler blocks the thread until the load job finishes. Use synchronous mode only when the pipeline permits blocking; for high-throughput message flows, keep async mode and handle reply/failure channels separately.

### 8.2. Typical Pipeline

~~~mermaid
flowchart LR
    SOURCE["GCS file / inbound message"] --> INPUT["Spring Integration input channel"]
    INPUT --> HANDLER["BigQueryFileMessageHandler"]
    HANDLER --> JOB["CompletableFuture<Job>"]
    JOB --> SUCCESS["Job completed successfully"]
    JOB --> FAILURE["Load job error / retry queue"]
~~~

When building pipelines, attach correlation IDs/batch IDs to trace source files to job IDs. Do not mark a file as processed merely because the message handler accepted the payload; update status only after the load job completes successfully.

## 9. IAM and Security

### 9.1. Permissions to Run Queries

To create BigQuery jobs, the runtime principal needs `bigquery.jobs.create`. Common roles:
- roles/bigquery.jobUser on the project running jobs.
- roles/bigquery.dataViewer on the dataset/table if read-only.
- roles/bigquery.dataEditor on the dataset if creating/updating tables or loading data.

Grant permissions scoped to the appropriate project/dataset. Do not grant roles/bigquery.admin to the runtime just because the application runs queries.

### 9.2. Permissions to Load from Cloud Storage

When loading files from a bucket, the runtime principal also needs read access to source objects. Typical permissions include storage.objects.get; when using wildcard URIs, storage.objects.list may also be required.

Grant roles/storage.objectViewer on the specific bucket rather than project-wide Storage Admin. Both the BigQuery service and the runtime principal must have permissions aligned with how the application triggers load jobs and accesses sources.

### 9.3. ADC and Workload Identity

- Local: developer ADC with limited permissions in a sandbox project.
- Cloud Run: dedicated service account for the service.
- GKE: Workload Identity Federation for GKE.
- Compute Engine: service account attached to the VM.

Separate runtime principals from deployment/migration principals. Runtime APIs generally only need to run queries or write into designated datasets; creating datasets, changing IAM policies, or deleting tables should be handled by a separate administrative pipeline.

### 9.4. Data Protection

BigQuery supports governance controls such as dataset/table IAM, row-level access policies, column-level security, and policy tags. Applications should:
- Return only the columns the API caller is authorized to view.
- Never write sensitive data or entire query results into logs.
- Use parameter binding for query values.
- Avoid returning PII unless required by the use case.
- Monitor audit logs and job history.
- Define retention and deletion policies for analytical data.

Query parameters do not replace authorization. A user may not be allowed to view a row/column even though the backend service account has table read permission; the backend must enforce business authorization before returning data.

## 10. Testing BigQuery in Spring Boot Applications

### 10.1. Unit Testing

BigQuery does not have a local emulator provided by the Spring BigQuery starter. Unit tests should mock BigQuery or BigQueryTemplate to verify:
- SQL text and parameter mappings.
- Rules converting FieldValue to DTOs.
- Empty result handling.
- Exception and interrupted query handling.
- Job error checks and retry policies.
- Write dispositions chosen per use case.

Do not mock the entire BigQuery client in an integration test and treat that as proof that real IAM or queries work.

### 10.2. Integration Testing on a Sandbox Dataset

Create a dedicated test dataset in a sandbox project:
1. Dataset with a fixed location.
2. Tables named with test run IDs or prefixes.
3. Schemas created via code or migration fixtures.
4. Test parameterized queries and assert results.
5. Test loading CSV from a test bucket or InputStream.
6. Test write dispositions on isolated tables.
7. Clean up test tables/datasets afterward if permitted.

Use a test service account with minimal roles. Never run write or truncate tests against production datasets.

### 10.3. Testing Job Completion

A job reaching state DONE does not guarantee it succeeded. Check status.errorResult; if present, the job failed. Individual row errors may also appear in status.errors without failing the entire job, depending on maxBadRecords and load configuration.

In tests, verify:
- Job ID.
- Job location.
- Job state.
- Fatal errors.
- Nonfatal row errors if the pipeline allows bad records.
- Loaded row count after job success.

### 10.4. Testing Retries

Simulate a client losing connectivity after submitting a job:
- Look up the job by its generated ID.
- If the job is still running, continue polling.
- If the job has finished, inspect its status.
- Only generate a different job ID when starting a new batch.

Tests must prove that retries do not duplicate the same batch by generating a fresh job ID after a timeout.

## 11. Operations, Costs, and Quotas

### 11.1. Tracking Query Jobs

Record at a minimum:
- Job ID and location.
- Related dataset/table.
- Query label or use case name.
- Bytes processed and bytes billed.
- Slot milliseconds.
- Execution duration.
- Error result and execution errors.

You can query INFORMATION_SCHEMA.JOBS_BY_PROJECT to analyze query, load, extract, and copy jobs over time. Avoid logging SQL containing sensitive data in application logs unnecessarily.

### 11.2. Managing Query Costs

- Prefer partition filters on partitioned tables.
- Select only needed columns instead of SELECT *.
- Use clustering on appropriate filter/sort columns.
- Set maximumBytesBilled on queries at risk of scanning large volumes.
- Use dry runs when developing new queries.
- Monitor query caching and job history.
- Decouple heavy dashboard queries from strict-latency API requests.

Queries are billed by bytes or slots depending on your pricing model and reservations. Do not execute heavy analytical queries inside synchronous HTTP requests if users expect fast responses; consider submitting async jobs and returning a job ID for clients to poll.

### 11.3. Reducing Load Job Counts

Load jobs have per-project/per-table quotas and ingestion rate limits. If a pipeline launches a separate load job for every tiny file, job counts can surge quickly.

Instead:
- Consolidate multiple files sharing a schema into one batch when feasible.
- Use valid wildcard URIs to load multiple objects.
- Use the Storage Write API when data arrives continuously.
- Monitor quotas and quotaExceeded errors.
- Design retries with exponential backoff.

Do not rapidly retry in a tight loop once quotas are exhausted; that only adds load without lifting the limit.

### 11.4. Observing the Storage Write API

For the Storage Write API, monitor:
- Batch sizes and append latency.
- Number of open streams.
- Retry counts and offsets.
- Schema mismatch errors.
- Pending streams not yet finalized/committed.
- Time from append to query visibility.

When using pending streams, monitor finalize/commit progress and stream expiration. When using the default stream, understand at-least-once semantics and implement application-side deduplication if events can be sent multiple times.

## 12. Common Errors and How to Handle Them

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| PERMISSION_DENIED when querying | Missing bigquery.jobs.create or table read permission | Check job project and dataset/table IAM |
| Access Denied when loading from GCS | Runtime principal cannot read object | Grant storage.objects.get and list when using wildcards |
| Dataset not found | Wrong project, dataset ID, or location | Check project-id and dataset-name configuration |
| Query location mismatch | Job running in different location from dataset | Specify exact location in JobId/job config |
| Unrecognized name | SQL references wrong field or schema differs from reality | Verify schema and field names |
| Parameter type mismatch | Wrong QueryParameterValue factory used | Match parameter type to BigQuery column type |
| Load job fails to parse CSV | Wrong header, delimiter, quote, or encoding | Configure CsvOptions and explicit schema |
| Header loaded as first row | Header not skipped | Use setSkipLeadingRows(1) |
| Schema mismatch | Source file does not match table schema | Standardize schema, check nullability and field order |
| quotaExceeded | Too many load jobs or table modifications | Consolidate batches, reduce job frequency, apply backoff |
| Job state DONE but data missing | Nonfatal row errors or maxBadRecords | Inspect status.errors and destination row count |
| Future not completing | Load job still running or slow polling | Track future/job ID, configure appropriate timeouts |
| Storage Write API response failed | Schema mismatch or stream error | Inspect WriteApiResponse.getErrors() |
| Duplicate data written after retry | New job ID created for same batch or non-idempotent stream semantics | Keep job ID/offset deterministic, deduplicate |
| Overly expensive query | Scanning many partitions/columns or missing limit | Dry run, partition filter, projection, maximumBytesBilled |
| App holds many threads waiting on jobs | Blocking on futures in request path | Run ingestion in async/batch workers, return job ID |

## 13. Practical Exercises

### Exercise A — Configure the Starter

Add spring-cloud-gcp-starter-bigquery, configure project ID and dataset name. Inject BigQuery and BigQueryTemplate; verify local ADC works against a sandbox dataset.

### Exercise B — Parameterized Queries

Write a service querying orders by customer ID, status, and time range. Use named parameters; never concatenate user input into SQL. Map TableResult into DTOs.

### Exercise C — Cost Control

Add maximumBytesBilled and perform a dry run for a dashboard query. Compare bytes processed between a query with a partition filter and one without.

### Exercise D — BigQueryTemplate CSV

Load a CSV file into a staging table using writeDataToTable. Pass an explicit schema, inspect job status, and compare row counts against the source file.

### Exercise E — NDJSON and Storage Write API

Load an NDJSON file using writeJsonStream. Test both the existing-table overload and the schema-passing overload. Verify WriteApiResponse.isSuccessful() and errors.

### Exercise F — Load Job from Cloud Storage

Upload a CSV batch to a bucket in the same location as the dataset. Create a LoadJobConfiguration with WRITE_APPEND, schema, and deterministic job ID. Simulate a timeout and look up the job by ID.

### Exercise G — Spring Integration

Create an input channel and BigQueryFileMessageHandler. Send a Resource or InputStream with table name/format headers. Handle `CompletableFuture<Job>` on the reply channel.

### Exercise H — IAM and Sandbox

Run the application with a dedicated service account. Grant roles/bigquery.jobUser, roles/bigquery.dataEditor on the test dataset, and read permission on the source bucket. Verify missing permissions produce clear errors.

### Exercise I — Pipeline Design

Choose between load jobs and the Storage Write API for three scenarios: nightly files, event streams, and historical backfills. Explain latency, atomicity, retry, and quota considerations for each choice.

### Self-Check Questions

1. Which workloads suit BigQuery and how does it differ from an OLTP database?
2. How do project, dataset, table, and schema relate to each other?
3. Which beans does spring-cloud-gcp-starter-bigquery auto-configure?
4. Which property scopes BigQueryTemplate?
5. Why can't query parameters replace table names?
6. How do named parameters differ from positional parameters?
7. Why should you use maximumBytesBilled and dry runs?
8. When should you use the BigQuery client instead of the template?
9. What return type does writeDataToTable produce?
10. How does writeJsonStream differ from a CSV load job?
11. When does the writeJsonStream overload require a schema?
12. How do WRITE_APPEND, WRITE_TRUNCATE, and WRITE_EMPTY differ?
13. Are load jobs atomic?
14. Why should you keep job IDs deterministic on retry?
15. Which file formats can be batch loaded from Cloud Storage?
16. How does dataset location affect load jobs?
17. How do pending streams differ from the default stream?
18. When is the Storage Write API needed instead of a load job?
19. How does BigQueryFileMessageHandler accept payloads and send replies?
20. Which IAM permissions does the runtime need to run queries and load from GCS?
21. Why doesn't DONE mean a job succeeded?
22. How do you inspect nonfatal row errors?
23. Why shouldn't you create a separate load job for every tiny file?
24. When do you need integration tests on a sandbox instead of mocking the client?

**Expected outcome:** learners can configure the BigQuery starter, run parameterized GoogleSQL queries with the Java client, ingest CSV/NDJSON via BigQueryTemplate, submit batch load jobs from Cloud Storage, choose the Storage Write API when appropriate, implement safe job checks/retries, grant least-privilege IAM, and monitor costs/quotas in Spring Boot applications.

## References

- [Spring Framework on Google Cloud 8.2.1 — BigQuery](https://googlecloudplatform.github.io/spring-cloud-gcp/8.2.1/reference/html/index.html#bigquery)
- [Spring Framework on Google Cloud — BigQueryTemplate Javadocs](https://googleapis.dev/java/spring-cloud-gcp/latest/com/google/cloud/spring/bigquery/core/BigQueryTemplate.html)
- [BigQueryJsonDataWriter Javadocs](https://googleapis.dev/java/spring-cloud-gcp/latest/com/google/cloud/spring/bigquery/core/BigQueryJsonDataWriter.html)
- [BigQuery Java client — QueryJobConfiguration](https://docs.cloud.google.com/java/docs/reference/google-cloud-bigquery/latest/com.google.cloud.bigquery.QueryJobConfiguration)
- [BigQuery Java client — JobId](https://docs.cloud.google.com/java/docs/reference/google-cloud-bigquery/latest/com.google.cloud.bigquery.JobId)
- [Run parameterized queries](https://docs.cloud.google.com/bigquery/docs/parameterized-queries)
- [Batch load data](https://docs.cloud.google.com/bigquery/docs/batch-loading-data)
- [Load CSV data from Cloud Storage](https://docs.cloud.google.com/bigquery/docs/loading-data-cloud-storage-csv)
- [BigQuery Storage Write API](https://docs.cloud.google.com/bigquery/docs/write-api-grpc)
- [Batch load with Storage Write API](https://docs.cloud.google.com/bigquery/docs/write-api-batch)
- [Optimize load jobs](https://docs.cloud.google.com/bigquery/docs/optimize-load-jobs)
- [BigQuery IAM roles and permissions](https://docs.cloud.google.com/bigquery/docs/access-control)
