# Controlling Query Costs, Quotas, and Connection Resources

## Lesson Objectives

The **SPRING_CLOUD_PROVIDER_INTEGRATION** module covers integrating Spring Boot with managed services from AWS, Azure, and Google Cloud via their corresponding Spring Cloud libraries. When applications use Google Cloud data services, cost and availability do not depend solely on SQL statements. They also depend on the pricing model, bytes scanned, API quotas, concurrent jobs, database connection counts, per-instance pools, and how autoscaling spawns additional clients.

This lesson focuses on three resource groups that are often confused:

- **Query costs:** data processing charges or compute slots, storage, and data transfer.
- **Quotas and system limits:** API limits, query usage, jobs, instances, or request rates.
- **Connection resources:** Cloud SQL connection pools, Spanner sessions/channels, and BigQuery client/job concurrency.

After this lesson, you will be able to:

1. Distinguish BigQuery on-demand pricing from capacity-based pricing.
2. Reduce bytes scanned using partition pruning, clustering, and selecting only needed columns.
3. Estimate queries with dry runs and set maximum bytes billed.
4. Configure custom query quotas, budget alerts, and query INFORMATION_SCHEMA.JOBS.
5. Distinguish adjustable quotas from fixed system limits.
6. Calculate total Cloud SQL connections as an application scales across multiple instances.
7. Configure HikariCP and Cloud SQL Java Connector in Spring Boot.
8. Understand multiplexed sessions and dynamic channel pooling in the Spanner Java client.
9. Monitor pools, quotas, and latency, and handle overload errors with backoff.
10. Design tests proving the system does not exceed query budgets or connection budgets.

## 1. Resource and Cost Models

### 1.1. Distinguishing Cost, Quota, Limit, and Pool

| Concept | Meaning | Example |
| --- | --- | --- |
| Cost | Consumed resources billed under the pricing model | BigQuery bytes billed, slot capacity, Cloud SQL instance and storage |
| Quota | Usage budget enforced per project, user, or API over a time period | Query usage per day, Cloud SQL Admin API requests |
| System limit | Fixed technical limit or one not adjustable via quota requests | Response size limits or structural limits of an API |
| Connection/session pool | Client resources held or borrowed to send requests to the database | HikariCP connections, Spanner multiplexed sessions, and gRPC channels |

A query can be cheap yet still rejected because quota is exhausted. Conversely, plenty of remaining quota does not mean the application has enough connections or slots to absorb more workload. When investigating incidents, identify which layer is exhausted before raising quotas or expanding pools.

### 1.2. Three Data Service Groups

| Service | Primary resources | Risks to control |
| --- | --- | --- |
| BigQuery | Bytes scanned, slots, query jobs, API requests, storage | Overly broad scans, job queues, quota exhaustion, or under-provisioned reservations |
| Cloud SQL | Database connections, CPU, memory, storage, Cloud SQL Admin API | Pools multiplying across instances, exhausting max_connections, excessive connector refreshes or login rates |
| Cloud Spanner | Transactions, multiplexed sessions, gRPC channels, compute capacity | Spawning many clients, channel congestion, transaction contention, or insufficient capacity |

Do not apply a single pool sizing rule across all three services. BigQuery is a job-oriented analytical service; Cloud SQL is a relational database with connection limits; Spanner uses a client library managing sessions and channels under its own model.

## 2. Controlling BigQuery Query Costs

### 2.1. Understanding the Pricing Model

BigQuery has two common compute pricing models:

- **On-demand:** billed by bytes processed/billed per query. Under this model, pay close attention to `total_bytes_billed`, dry runs, `maximumBytesBilled`, and custom query quotas.
- **Capacity-based:** pays for compute capacity (slots/reservations or corresponding editions). Under this model, `total_slot_ms`, reservation utilization, and concurrency matter more than bytes billed when evaluating compute usage.

Storage cost is a separate category. Query optimization does not automatically lower storage bills; manage retention, partition expiration, table expiration, and storage billing models separately.

Do not convert `total_slot_ms` into a fixed dollar figure for every workload. Slot milliseconds measure compute consumption; actual cost depends on pricing model, edition, reservations, and project capacity commitments.

### 2.2. Select Only Needed Columns

BigQuery stores data in columnar format. For on-demand queries, selecting more columns increases bytes read even if the application only displays a subset of results.

Avoid:

~~~sql
SELECT *
FROM `acme-analytics.sales.orders`
WHERE order_date >= DATE '2026-01-01';
~~~

Select explicit columns instead:

~~~sql
SELECT
  order_id,
  customer_id,
  order_date,
  total_amount
FROM `acme-analytics.sales.orders`
WHERE order_date >= DATE '2026-01-01';
~~~

If schemas change frequently, you can use `SELECT * EXCEPT (...)`, though it is still better to exclude unneeded columns explicitly. For APIs serving dashboards, avoid returning wider payloads than clients require.

### 2.3. Partition Pruning

Partitioning divides a table into segments along a partition column, typically a date/timestamp or ingestion time. When a query has an appropriate predicate on the partition column, BigQuery skips irrelevant partitions; bytes scanned and query costs drop.

Example `orders` table partitioned by `order_date`:

~~~sql
SELECT
  customer_id,
  SUM(total_amount) AS revenue
FROM `acme-analytics.sales.orders`
WHERE order_date >= DATE '2026-10-01'
  AND order_date < DATE '2026-11-01'
GROUP BY customer_id;
~~~

Predicates on partition columns should be direct and specify concrete ranges. Wrapping the partition column in complex expressions or using non-prunable predicates can cause the query to read more partitions than expected.

Enforce mandatory partition filters on large tables where appropriate. For ingestion-time partitioned tables, use `_PARTITIONDATE` or `_PARTITIONTIME` depending on the partition type created.

### 2.4. Clustering

Clustering sorts data by frequently filtered or joined columns. BigQuery can prune blocks based on clustering predicates to reduce actual bytes read.

Example table partitioned by day and clustered by `customer_id`, `region`:

~~~sql
SELECT order_id, total_amount
FROM `acme-analytics.sales.orders`
WHERE order_date BETWEEN DATE '2026-11-01' AND DATE '2026-11-07'
  AND customer_id = 'cust-1001';
~~~

Partition pruning eliminates dates outside the range; clustering reduces blocks read within the remaining partitions. Choose clustering columns based on real query patterns rather than adding many columns speculatively.

### 2.5. LIMIT Is Not a Cost-Control Guardrail

On unclustered tables, `LIMIT 100` only caps returned rows; it does not necessarily reduce bytes read. Do not rely on `LIMIT` as a cost guardrail for queries scanning large tables.

When inspecting sample data, use Preview, `bq head`, or partial data read APIs. To genuinely limit costs, use partition filters, dry runs, and maximum bytes billed.

### 2.6. Avoid Repeated Computation

If multiple queries perform the same heavy transformation:

- Materialize intermediate results into an appropriate table.
- Use scheduled queries or materialized views when workloads recur and semantics permit.
- Build aggregate tables for frequently accessed dashboards.
- Refresh only changed slices if pipelines support incremental processing.
- Evaluate query caching, though never rely on cache as a cost guarantee.

Materialization can increase storage costs, yet storage for summary tables is often cheaper than repeating heavy scans/transforms. Compare total compute + storage + refresh frequency.

### 2.7. Federated Queries and External Data

For external/federated queries, bytes may not be accurately estimated beforehand. Dry runs may report 0 or a lower bound even though the actual query reads data and incurs charges. Do not rely on dry run as the sole guard for queries reading Cloud SQL, Cloud Storage, or external sources.

Additional controls:

- Restrict date/partition ranges or object prefixes read.
- Co-locate BigQuery and data sources in compatible locations where feasible.
- Monitor data transfer and cross-region charges.
- Consider loading data into BigQuery before running repeated analytics.

## 3. Query Estimation and Per-Job Limits

### 3.1. Dry Runs

A dry run validates syntax and estimates bytes processed without executing the query. Dry runs consume no query slots and incur no query processing charges.

Java BigQuery client:

~~~java
import com.google.cloud.bigquery.BigQuery;
import com.google.cloud.bigquery.BigQueryOptions;
import com.google.cloud.bigquery.Job;
import com.google.cloud.bigquery.JobInfo;
import com.google.cloud.bigquery.JobStatistics;
import com.google.cloud.bigquery.QueryJobConfiguration;
import com.google.cloud.bigquery.QueryParameterValue;

public long estimateBytes(BigQuery bigQuery, String sql) {
    QueryJobConfiguration dryRunConfig =
            QueryJobConfiguration.newBuilder(sql)
                    .setUseLegacySql(false)
                    .setDryRun(true)
                    .setUseQueryCache(false)
                    .build();

    Job job = bigQuery.create(JobInfo.of(dryRunConfig));
    JobStatistics.QueryStatistics statistics = job.getStatistics();
    return statistics.getTotalBytesProcessed();
}

// The BigQuery client is created once and reused across the application.
BigQuery bigQuery = BigQueryOptions.getDefaultInstance().getService();
~~~

Set the location matching the dataset/job when running outside US/EU regions. Do not create a new BigQuery client per HTTP request; keep the client as a shared bean.

### 3.2. Capping Bytes Billed per Query

With on-demand pricing, `maximumBytesBilled` causes a query to be rejected before execution if estimated bytes billed exceed the threshold. When rejected, the query incurs no processing charges.

~~~java
long maxBytesBilled = 50L * 1024 * 1024 * 1024; // 50 GiB

QueryJobConfiguration guardedConfig =
        QueryJobConfiguration.newBuilder(sql)
                .setUseLegacySql(false)
                .setMaximumBytesBilled(maxBytesBilled)
                .build();

// Submit guardedConfig via the BigQuery client after the application checks
// policies and query parameters.
~~~

This is a per-job guard, not a project-wide quota. A service can submit many jobs, each below the cap, while total usage still grows very large.

Estimates for queries on clustered tables may represent an upper bound before block pruning finishes. Consequently, a query may be rejected even though actual bytes after execution would have been lower than the threshold. Set thresholds based on query patterns and handle `bytesBilledLimitExceeded` errors.

### 3.3. Combining Dry Runs and Maximum Bytes Billed

Recommended flow for endpoints accepting SQL/report requests:

1. Select an application-controlled SQL template.
2. Bind parameters; never concatenate strings from user input.
3. Run a dry run and obtain estimated bytes.
4. Compare the estimate against thresholds per endpoint/tenant/job type.
5. If exceeded, return a clear error or ask the user to narrow the scope.
6. If within bounds, submit the job with `maximumBytesBilled`.
7. Record job ID, caller, labels, duration, and usage after completion.

Dry runs may not provide reliable estimates for external/federated queries or tables with row-level security. In such cases, enforce other controls such as query allowlists, restricted data sources/scopes, and post-execution usage checks.

### 3.4. Query Parameters and Job Labels

Never concatenate filter values from HTTP requests directly into SQL. Use named parameters:

~~~java
import com.google.cloud.bigquery.BigQuery;
import com.google.cloud.bigquery.JobId;
import com.google.cloud.bigquery.BigQueryOptions;
import com.google.cloud.bigquery.QueryJobConfiguration;
import com.google.cloud.bigquery.QueryParameterValue;
import com.google.cloud.bigquery.TableResult;
import java.util.Map;
import java.util.UUID;

BigQuery bigQuery = BigQueryOptions.getDefaultInstance().getService();
QueryJobConfiguration config =
        QueryJobConfiguration.newBuilder("""
            SELECT order_id, total_amount
            FROM `acme-analytics.sales.orders`
            WHERE customer_id = @customerId
              AND order_date >= @fromDate
            """)
            .setUseLegacySql(false)
            .addNamedParameter(
                    "customerId",
                    QueryParameterValue.string(customerId))
            .addNamedParameter(
                    "fromDate",
                    QueryParameterValue.date(fromDate.toString()))
            .setMaximumBytesBilled(maxBytesBilled)
            .setLabels(Map.of(
                    "service", "order-reporting",
                    "environment", "production"))
            .build();

// For datasets in regions other than US/EU, supply location in JobId.
JobId jobId = JobId.newBuilder()
        .setLocation("asia-southeast1")
        .setJob("order-report-" + UUID.randomUUID())
        .build();
TableResult results = bigQuery.query(config, jobId);
~~~

Job labels help break down usage by service, environment, or workload. Labels can be set on `QueryJobConfiguration` or `JobInfo` depending on how jobs are submitted. Labels must comply with BigQuery naming/value rules and contain no personal data or secrets. Keep label cardinality moderate; do not generate a unique label value per request, as that complicates reporting.

## 4. BigQuery Quotas and API Limits

### 4.1. Custom Daily Query Quotas

Under on-demand pricing, BigQuery provides daily query usage quotas:

| Quota | Documented default | Scope |
| --- | --- | --- |
| QueryUsagePerDay | 200 TiB per project per day | Total usage across all users in the project |
| QueryUsagePerUserPerDay | Unlimited by default | Enforces a per-user/service-account quota within the project |

Custom quotas can be set lower or higher within supported limits. Daily quotas reset at midnight Pacific Time, not your application's timezone. These two quotas apply only to on-demand query pricing.

Custom quotas are approximate safeguards, not strict hard billing caps. BigQuery may occasionally allow queries to exceed the configured limit. When stricter per-job control is needed, combine with `maximumBytesBilled`.

You cannot set a custom quota for a single specific user or service account via an individual override; user-level custom quotas apply uniformly across users under the project's quota mechanism.

### 4.2. Configuring Custom Quotas

In Google Cloud Console:

1. Open **IAM & Admin → Quotas & System Limits**.
2. Filter the service to **BigQuery API**.
3. Locate **Query usage per day** and/or **Query usage per day per user**.
4. Select the quota, click Edit, and uncheck Unlimited if enabled.
5. Enter the new limit in TiB.
6. Submit the change and monitor quota status.

Principals modifying quotas need `serviceusage.quotas.update`, typically via the Quota Administrator role or equivalent permissions. Do not grant quota management roles to application runtime service accounts.

### 4.3. API Quotas and Job Concurrency

BigQuery also enforces quotas on API requests, query jobs, pending jobs, concurrent jobs, and certain data read methods. For instance, core BigQuery API docs specify per-user/method request rates and concurrent request limits; values vary by API type, region, project, and pricing model.

Do not hard-code quotas into business logic as immutable constants. Before release, inspect your project's Quotas & Limits page and current documentation. When receiving `quotaExceeded`, `rateLimitExceeded`, or HTTP 429:

- Throttle job submission rate and concurrent requests.
- Use exponential backoff with jitter for transient errors.
- Do not retry infinitely or retry syntax/permission errors.
- Keep job IDs deterministic when retrying submissions to avoid spawning duplicate jobs.
- Separate batch workloads from interactive workloads when queue isolation is needed.

### 4.4. Quotas vs. Slot Capacity

Quotas limit request rates or usage within a defined scope. Slot capacity is the compute resource BigQuery uses to execute queries. A workload may have remaining quota yet run slowly due to slot contention or insufficient reservations; conversely, reservations may have spare slots while API quotas are hit.

When using capacity-based pricing:

- Monitor slot utilization and reservation assignments.
- Distinguish pending jobs from running jobs.
- Evaluate workloads by duration, concurrency, and slot milliseconds.
- Do not use `maximumBytesBilled` as a monetary cap mechanism under reservation pricing.

## 5. Tracking BigQuery Usage with INFORMATION_SCHEMA

### 5.1. Reporting Bytes Billed by User

BigQuery records query job telemetry in `INFORMATION_SCHEMA.JOBS*`. The example below aggregates bytes billed by user over 7 days:

~~~sql
SELECT
  user_email,
  COUNT(*) AS query_count,
  SUM(total_bytes_billed) AS bytes_billed,
  SUM(total_slot_ms) AS total_slot_ms
FROM
  `region-asia-southeast1`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
WHERE
  creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
  AND job_type = 'QUERY'
  AND state = 'DONE'
  AND (statement_type IS NULL OR statement_type != 'SCRIPT')
GROUP BY user_email
ORDER BY bytes_billed DESC;
~~~

Replace `asia-southeast1` with the region hosting your jobs. The query execution location must match the location of the `INFORMATION_SCHEMA` view. Filtering on `creation_time` bounds the time range scanned.

### 5.2. Why Exclude SCRIPT?

Multi-statement queries create a parent job with `statement_type = SCRIPT` alongside child jobs. The parent job may aggregate total usage from its child jobs. Summing both parent and child jobs can double-count usage. When aggregating cost/slot usage, exclude `SCRIPT` or build explicit parent/child aggregation logic.

### 5.3. Fields to Monitor

| Field | Meaning | Used for |
| --- | --- | --- |
| total_bytes_processed | Bytes processed | Evaluating scan volume |
| total_bytes_billed | Bytes billed under on-demand model | Reporting billed usage |
| total_slot_ms | Slot milliseconds | Analyzing compute consumption |
| user_email | Identity submitting the job | Identifying consuming callers/service accounts |
| job_id | Job identifier | Tracing individual jobs |
| reservation_id | Reservation executing the job | Analyzing workloads by capacity |
| query_info.resource_warning | Query resource warnings | Finding queries experiencing resource pressure |
| error_result | Job error | Distinguishing quota, bytes cap, and SQL errors |

`total_bytes_billed` may be null for queries reading tables with row-level access policies. Under capacity pricing, this field is informational rather than a byte-based charge. `total_slot_ms` also does not map directly to currency without factoring in the pricing model.

### 5.4. Monitoring and Alerting

Build dashboards tracking:

- Bytes billed by project, service account, label, and hour/day.
- Query counts, failed jobs, and quota errors.
- Slot milliseconds and pending/running jobs.
- Query latency p50/p95/p99.
- Top queries by bytes billed or slot usage.
- Rate of jobs rejected due to `maximumBytesBilled`.

Combine `INFORMATION_SCHEMA` with Cloud Monitoring and Cloud Billing reports. `INFORMATION_SCHEMA` provides granular per-job telemetry; Cloud Billing reflects billing figures with its own reporting latency.

## 6. Budgets, Reservations, and Cost Policies

### 6.1. Budget Alerts Do Not Block Usage by Default

Cloud Billing budgets can track costs by billing account, project, service, or label and send alerts on actual/forecasted thresholds. However, **alerts-only budgets do not automatically stop services or enforce hard caps**. Billing data also lags; by the time an alert fires, additional usage may already have accrued without appearing yet.

For services supporting spend cap budgets, you can configure a spend limit for an eligible project and service. This mechanism uses estimated gross cost for enforcement, has latency, and does not terminate in-flight requests. Do not treat spend caps as a substitute for `maximumBytesBilled`, custom quotas, and application-level guardrails.

### 6.2. Combining Multiple Control Layers

| Layer | Mechanism | Scope |
| --- | --- | --- |
| Query design | Partitioning, clustering, column selection, materialization | Reduces data needing processing |
| Per-job | Dry run and maximum bytes billed | Blocks on-demand queries exceeding threshold |
| Project/user | Custom daily query quotas | Caps total daily query usage |
| Compute capacity | Reservation/slot assignment | Allocates compute and controls concurrency |
| Billing | Budget alerts or spend caps where eligible | Tracks overall costs and alerts |
| Application | Query allowlists, rate limits, queues, authorization | Blocks unsuitable requests before creating jobs |

No single layer completely replaces the others. For instance, a daily quota can block an entire analytics team if one user exhausts it; a per-job cap does not control the volume of small jobs; a budget alert does not necessarily halt queries.

### 6.3. Choosing On-Demand vs. Capacity

On-demand fits variable workloads, is easy to start with, and pairs easily with byte-based guardrails. Capacity-based fits steady workloads or those needing more predictable throughput/latency, but requires tracking slot utilization, reservation assignments, and concurrency.

Before switching pricing models:

1. Aggregate query usage and slot milliseconds over a representative period.
2. Separate interactive, scheduled, and batch workloads.
3. Evaluate peak concurrency and busy hours.
4. Estimate reservations/editions suited to the workload.
5. Check whether jobs queue or experience slot starvation.
6. Compare capacity costs against on-demand, factoring in storage and workload growth.

## 7. Cloud SQL: Connection Limits and Connection Budgets

### 7.1. Connections Are Resources on Both App and Database

Each database connection consumes resources on both client and server. Cloud SQL enforces overall connection limits based on engine, instance configuration, and memory. Adding connections does not automatically boost throughput; if the database lacks CPU/memory, more connections can increase contention and latency.

For Cloud SQL MySQL, check the current limit:

~~~sql
SHOW VARIABLES LIKE 'max_connections';
~~~

For Cloud SQL PostgreSQL:

~~~sql
SELECT name, setting
FROM pg_settings
WHERE name = 'max_connections';
~~~

Default values and headroom to raise limits depend on machine type and memory. On PostgreSQL, also account for backend processes such as autovacuum workers and worker processes when tuning `max_connections`. Do not copy a number from another environment straight into production.

### 7.2. Calculating Total Connections When Scaling Horizontally

HikariCP pools live inside each process. With multiple pods/containers, each process maintains its own pool. Potential total connections must be summed across the entire fleet:

~~~text
Total peak connections
  = max application instances x maximumPoolSize
  + background workers
  + scheduled jobs
  + migration/admin connections
  + old/new instances during rolling deployment
~~~

Example:

| Component | Count | Pool/connections per instance | Max total |
| --- | ---: | ---: | ---: |
| Cloud Run/GKE application | 12 | 5 | 60 |
| Background workers | 3 | 4 | 12 |
| Migration/admin job | 1 | 3 | 3 |
| Rolling deployment buffer | 2 | 5 | 10 |
| **Estimated total** | | | **85** |

If the database only allows 100 client connections, this setup already consumes most of the budget. Leave buffer for failover, maintenance, DBAs, monitoring, and other workloads. Never set `maximumPoolSize` equal to the database's `max_connections`.

Cloud Run enforces a limit of 100 connections per container instance for the **built-in Cloud SQL connection**. When using the Cloud SQL Auth Proxy sidecar, Cloud SQL Language Connectors, or direct IP connections, this built-in limit does not apply; however, the database's `max_connections` limit still applies.

### 7.3. HikariCP in Spring Boot

Spring Boot uses HikariCP as the default connection pool in many JDBC setups. The example below is a starting point for load testing, not an optimal configuration for every instance:

~~~yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 5
      minimum-idle: 1
      connection-timeout: 10000
      idle-timeout: 600000
~~~

Meanings:

| Property | Effect |
| --- | --- |
| maximum-pool-size | Maximum connections in one process's pool |
| minimum-idle | Target idle connections the pool tries to maintain |
| connection-timeout | Maximum wait time to borrow a connection before failing |
| idle-timeout | Time an idle connection may stay in the pool when idle count exceeds minimum-idle |

When running serverless or scale-to-zero workloads, a high `minimum-idle` opens connections immediately at instance startup. When scaling out many instances simultaneously, this causes a connection storm. You can set `minimum-idle` lower—even 0 if appropriate—and measure cold-start and connection latency.

### 7.4. Keep Connections Held Briefly

Always close connections, statements, and result sets with try-with-resources so connections return to the pool:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
             connection.prepareStatement(
                     "SELECT status FROM orders WHERE order_id = ?")) {
    statement.setString(1, orderId);
    try (ResultSet resultSet = statement.executeQuery()) {
        if (resultSet.next()) {
            return resultSet.getString("status");
        }
    }
}
~~~

Do not hold connections while calling external HTTP APIs, sending emails, or waiting on users. Acquire connections right before transactions/queries and return them immediately afterward. Connection leaks exhaust the pool even while the database still has capacity.

### 7.5. Limit Long Transactions

Long transactions hold connections and locks longer. You should:

- Keep transactions short; avoid network calls inside transactions.
- Split large batches into smaller transactions when business semantics permit.
- Set query and transaction timeouts.
- Retry transactions from the beginning only on retryable errors; never continue mid-way inside an aborted transaction.
- Design idempotent writes when the client cannot tell whether a commit completed before a disconnect.

## 8. Cloud SQL Java Connector and Connection Quotas

### 8.1. The Connector Does Not Replace the Connection Pool

Cloud SQL Java Connector/Auth Proxy creates an authenticated, encrypted path to Cloud SQL. The connector is not a connection pool replacing HikariCP. A typical stack looks like:

~~~text
Spring Boot DataSource
        |
      HikariCP
        |
 JDBC driver + Cloud SQL Java Connector
        |
 Cloud SQL instance
~~~

The application must still cap pools and total connections across the fleet. Do not instantiate a new connector or `DataSource` per HTTP request.

### 8.2. Spring Boot Configuration with PostgreSQL Socket Factory

Add the PostgreSQL Socket Factory dependency compatible with your project's Java Connector version. Example configuration for IAM database authentication:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql:///APP_DATABASE?cloudSqlInstance=PROJECT_ID:REGION:INSTANCE_NAME&socketFactory=com.google.cloud.sql.postgres.SocketFactory
    username: IAM_DATABASE_USER
    hikari:
      maximum-pool-size: 5
      minimum-idle: 1
      connection-timeout: 10000
      data-source-properties:
        enableIamAuth: true
        sslmode: disable
        cloudSqlRefreshStrategy: lazy
~~~

Replace `APP_DATABASE`, `PROJECT_ID`, `REGION`, `INSTANCE_NAME`, and `IAM_DATABASE_USER` with environment-specific configuration. For regular database user/password auth, retrieve passwords from Secret Manager or managed secret injection; never commit passwords to YAML.

Cloud SQL Java Connector handles TLS, so driver-level SSL is typically disabled per connector instructions. Verify exact properties for your engine and JDBC driver version.

### 8.3. Connector Refreshes and Cloud SQL Admin API Quotas

Cloud SQL Auth Proxy and Language Connectors consume Cloud SQL Admin API quota. Connectors refresh metadata/certificates roughly once per hour; each refresh typically makes two API calls per process per connected instance.

Simple estimate:

~~~text
Admin API calls per hour
  = connector processes
  x Cloud SQL instances per process
  x 2 calls per refresh
~~~

For example, 4 connector processes each connecting to 3 Cloud SQL instances make roughly 24 API calls per hour for refreshes. During rapid autoscaling, rising connector process counts can trigger bursts of API requests. Keep one stable `DataSource`/connector lifecycle per process, monitor Admin API quota, and avoid initializing connectors per request.

### 8.4. Lazy Refresh for Serverless

In serverless environments with CPU throttling while instances are idle, Cloud SQL Connector can be configured with a `lazy` refresh strategy so refreshes happen on demand rather than via scheduled background refreshes. This prevents background refreshes from being delayed or consuming CPU outside request handling.

Do not apply lazy refresh blindly to every workload. Measure connection establishment latency after idle periods and weigh the trade-off between cold connections and background refreshes.

### 8.5. IAM Database Authentication

IAM database authentication lets workloads use an IAM identity instead of static passwords, though it does not eliminate database connection limits. Cloud SQL for MySQL docs note an IAM login authorization quota of 12,000 logins per minute per instance; check documentation for your specific engine before relying on this figure. Even with high quotas, do not open a new login per query.

Use pooling to reuse authenticated connections. When tokens/credentials expire or connections close, the connector and pool establish new connections via the library's mechanism.

## 9. Cloud Spanner: Multiplexed Sessions and gRPC Channels

### 9.1. Spanner Does Not Use HikariCP Like Cloud SQL

The Spanner Java client is not a traditional JDBC database on the native access path. The client manages sessions and gRPC channels. Do not configure HikariCP `maximumPoolSize` assuming it governs Spanner concurrency.

With Java client library version 6.98.0 and later, multiplexed sessions are enabled by default. One multiplexed session can serve many concurrent transactions; the application does not need to create one session per request.

### 9.2. Reusing the Spanner Client

Create the `Spanner` client and `DatabaseClient` once in the Spring context and reuse them:

~~~java
import com.google.cloud.spanner.DatabaseClient;
import com.google.cloud.spanner.DatabaseId;
import com.google.cloud.spanner.Spanner;
import com.google.cloud.spanner.SpannerOptions;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SpannerConfiguration {

    @Bean(destroyMethod = "close")
    Spanner spannerClient(
            @Value("${spring.cloud.gcp.project-id}") String projectId) {
        SpannerOptions options = SpannerOptions.newBuilder()
                .setProjectId(projectId)
                .enableDynamicChannelPool()
                .build();
        return options.getService();
    }

    @Bean
    DatabaseClient databaseClient(
            Spanner spanner,
            @Value("${spring.cloud.gcp.project-id}") String projectId,
            @Value("${app.spanner.instance-id}") String instanceId,
            @Value("${app.spanner.database-id}") String databaseId) {
        return spanner.getDatabaseClient(
                DatabaseId.of(projectId, instanceId, databaseId));
    }
}
~~~

In real applications, supply `projectId`, `instanceId`, and `databaseId` via configuration properties or constructor-bound configuration classes. Never create a `Spanner` client inside each business method.

### 9.3. Dynamic Channel Pool

Dynamic channel pooling is not enabled by default in the Java client. When disabled, the client typically uses 4 gRPC channels (8 when using the gRPC-GCP extension). Enable the dynamic channel pool so the library scales channels to match workload:

~~~java
SpannerOptions options = SpannerOptions.newBuilder()
        .setProjectId(projectId)
        .enableDynamicChannelPool()
        .build();
~~~

Each gRPC channel uses a TCP connection. Each RPC requires a thread to execute; thus channel count, concurrency, and thread pools all affect client resources. Dynamic channel pooling helps avoid channel under- or over-provisioning as load shifts.

Do not set `setNumChannels` if you want dynamic channel pooling, because configuring a static channel count disables the dynamic mechanism.

### 9.4. Avoid Copying Legacy Session Pool Configs Mechanically

Older examples configure `SessionPoolOptions` with `minSessions`/`maxSessions`. In modern Java clients, multiplexed sessions are enabled by default and legacy session pool options are deprecated/non-functional under the current API. Check your client version before copying old configurations from blogs or samples.

For older clients lacking multiplexed session support, session pool sizing should be based on concurrent transactions of **one application instance**. Growing the pool beyond what the instance can process consumes extra resources and can destabilize the system.

### 9.5. Transaction Contention and Retries

Spanner can abort read-write transactions due to contention. Use the client library's transaction API to retry transactions per supported semantics; transaction callbacks must be safe to re-run.

Do not place external side effects outside Spanner (sending emails, calling payment APIs) inside a retryable transaction callback. Record intended side effects in an outbox inside the transaction and process them in a separate step.

Monitor transaction aborts, latency, CPU utilization, request rates, and channel saturation. When raising concurrency, evaluate both Spanner instance capacity and the client's capacity to dispatch RPCs.

## 10. Retries, Backoff, and Overload Handling

### 10.1. Classify Errors Before Retrying

| Error | Handling |
| --- | --- |
| HTTP 429 or RESOURCE_EXHAUSTED | Slow down, backoff with jitter, check quota/capacity |
| UNAVAILABLE or transient network error | Bounded retries if the operation is safe |
| SQL syntax/invalid query | Do not retry; fix the query |
| Permission denied/unauthenticated | Fix IAM/credentials; do not retry continuously |
| maximumBytesBilled exceeded | Narrow query or adjust threshold after review |
| Connection pool timeout | Check leaks, concurrency, pool sizing, and DB capacity |
| Transaction aborted | Retry the whole transaction if business logic and client library permit |

### 10.2. Exponential Backoff with Jitter

When a quota or database is temporarily overloaded, immediate retries from many instances trigger a retry storm. Use exponential backoff with jitter and cap the retry count:

~~~java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

Duration delay = Duration.ofMillis(200);
Duration maxDelay = Duration.ofSeconds(10);

for (int attempt = 1; attempt <= 5; attempt++) {
    try {
        return executeOperation();
    } catch (TransientDataException error) {
        if (attempt == 5) {
            throw error;
        }

        long jitterMillis = ThreadLocalRandom.current()
                .nextLong(Math.max(1, delay.toMillis() / 2),
                          Math.max(2, delay.toMillis() + 1));
        Thread.sleep(jitterMillis);
        delay = delay.multipliedBy(2).compareTo(maxDelay) > 0
                ? maxDelay
                : delay.multipliedBy(2);
    }
}
throw new IllegalStateException("Unreachable");
~~~

This illustrates the strategy; in production, use a retry library or the Google client library's built-in retry settings if suitably configured. Do not wrap an external retry layer around a client that already retries the same errors automatically, if doing so multiplies call attempts.

### 10.3. Retries Must Be Idempotent

For query/job submissions, persist the job ID or request ID to detect whether a prior submission was already created. For Cloud SQL/Spanner writes, use unique keys, transactions, or idempotency keys to avoid duplicate writes when clients do not know whether commit completed before disconnect.

If an error occurs mid-transaction, retry from the beginning of the transaction per database semantics. Never merely re-run the last statement of an aborted transaction.

## 11. Observability for Queries and Connection Pools

### 11.1. BigQuery

Monitor:

- Bytes billed/processed by job, user, and label.
- Query counts, job errors, and quota exceeded errors.
- Pending/running jobs and slot utilization.
- Query latency, resource warnings, and top expensive jobs.
- Reservation utilization when using the capacity model.

### 11.2. Cloud SQL and HikariCP

Monitor at a minimum:

| Metric | Meaning |
| --- | --- |
| Hikari active | Connections currently borrowed by the application |
| Hikari idle | Idle connections available in the pool |
| Hikari pending/waiting | Threads waiting for a connection |
| Hikari max | Process pool limit |
| Cloud SQL connections | Total connections to the instance |
| Database CPU/memory | Server resources |
| Query latency/lock waits | Database processing health |

If `active` approaches `maximumPoolSize` and `pending` grows, the pool may be the bottleneck. If connection counts rise while database CPU is already high, enlarging the pool can worsen the situation. Optimize queries and transactions before raising connection limits.

### 11.3. Spanner

Monitor instance CPU, request latency, transaction aborts, read/write throughput, gRPC channel utilization, and retry rates. When using dynamic channel pooling, watch tail latency and channel growth to determine whether clients are under-provisioned.

### 11.4. Correlation and Labels

Attach service name, environment, workload type, and correlation IDs to logs/job labels. Never log SQL parameters containing sensitive info or secrets. Use trace IDs to link Spring Boot requests to BigQuery job IDs or transaction/database logs.

## 12. Resource Control Runbook

Before releasing data workloads:

1. Identify the BigQuery pricing model and region.
2. Set `maximumBytesBilled` for critical on-demand queries.
3. Configure appropriate project/user daily query quotas.
4. Verify budget alerts and alert recipients.
5. Monitor `INFORMATION_SCHEMA.JOBS` by user, label, and workload.
6. Verify Cloud SQL `max_connections` on the real instance.
7. Calculate total Hikari `maximumPoolSize` multiplied by max replicas across the fleet.
8. Add worker, migration, monitoring, and rolling deployment headroom.
9. Set connection timeouts and monitor pool pending counts.
10. Manage Cloud SQL Connector/Proxy along proper lifecycles; never create connectors per request.
11. Reuse the Spanner client; verify multiplexed sessions and dynamic channel pooling.
12. Test quota exceeded, connection timeouts, transaction aborts, and scale-out.

When incidents occur:

- **BigQuery cost spike:** inspect top jobs by bytes billed/slot ms, caller, and query text; identify broad scans or repeated queries.
- **BigQuery quota exceeded:** check quota ID, project/user scope, and reset time; do not simply raise quotas without optimizing query patterns.
- **Cloud SQL connections exhausted:** inspect Hikari active/idle/pending, connection counts, max replicas, and leaks; do not raise `max_connections` without evaluating memory.
- **Spanner latency spike:** check transaction aborts, CPU, request concurrency, and channel pools; distinguish contention from insufficient client channels.

## 13. Comprehensive Practical Exercises

A Spring Boot application has two workloads:

- Service `order-reporting` runs BigQuery queries to generate daily revenue reports.
- Service `order-api` writes orders to Cloud SQL PostgreSQL.
- Another worker uses Cloud Spanner to update read projections.

### Requirement A — BigQuery Query Costs

1. Write a reporting query using a daily partition filter.
2. Compare byte estimates between `SELECT *` and selecting only required columns.
3. Run a dry run using the Java BigQuery client.
4. Reject queries if estimated bytes exceed the endpoint threshold.
5. Submit queries with `maximumBytesBilled`.
6. Attach job labels by service/environment.
7. Query `INFORMATION_SCHEMA.JOBS_BY_PROJECT` to aggregate bytes billed by user.

### Requirement B — Quotas and Budgets

1. Configure `QueryUsagePerDay` and `QueryUsagePerUserPerDay` on a sandbox project.
2. Check when quotas reset in Pacific Time.
3. Create budget alerts at 50%, 80%, and 100%.
4. Demonstrate that budget alerts do not automatically halt queries.
5. Write tests handling `quotaExceeded` and HTTP 429 using backoff with jitter.

### Requirement C — Cloud SQL Connection Budget

1. Read `max_connections` from Cloud SQL PostgreSQL.
2. Configure Hikari `maximumPoolSize = 5` and `minimumIdle = 1`.
3. Simulate 10 application replicas; compute total pool capacity.
4. Add worker and migration connections to the budget.
5. Load test to observe active, idle, and pending connections.
6. Test concurrent scale-out and identify connection storms.
7. Verify `DataSource`/Cloud SQL Connector is created only once per application instance.

### Requirement D — Spanner Client Resources

1. Create a shared `Spanner` bean in the Spring context.
2. Verify the Java client version enables multiplexed sessions by default.
3. Enable dynamic channel pooling and compare p95/p99 latency.
4. Induce transaction contention and observe aborts/retries.
5. Ensure transaction callbacks emit no external side effects.

### Evaluation Matrix

| Scenario | Expected outcome |
| --- | --- |
| Query scan exceeds maximum bytes | Job rejected prior to execution |
| Daily query quota exhausted | Application reports quota error and stops retrying aggressively |
| Budget alert reaches threshold | Notification sent; queries not automatically halted by alerts-only budget |
| Cloud SQL pool runs out of connections | Requests wait up to connectionTimeout then fail cleanly |
| Cloud Run scale-out | Total connections remain within the database budget |
| Cloud SQL connector refresh | Admin API usage monitored; connector not created per request |
| Spanner concurrency increases | Client reused, multiplexed sessions and channel pool behave properly |
| Transaction abort | Entire transaction retried without duplicating side effects |

### Completion Criteria

- Dry runs and maximum bytes billed configured for on-demand queries.
- Daily quotas and usage dashboards by job/user in place.
- Total Cloud SQL connections calculated across the entire fleet.
- Hikari pool config, connection timeouts, and leak monitoring configured.
- Cloud SQL connector/`DataSource` and Spanner client reused.
- Bounded retry/backoff and idempotency implemented for writes.
- Clear distinction made between quotas, system limits, and budget alerts.

## 14. Comparison with AWS and Azure

| Need | Google Cloud | AWS | Azure |
| --- | --- | --- | --- |
| Data warehouse scan cost control | BigQuery dry run, maximumBytesBilled, custom query quotas, reservations | Athena scan bytes, workgroup data usage controls, and service-specific capacity/reservations | Synapse/serverless SQL data processed limits, dedicated SQL pool capacity |
| Query telemetry | INFORMATION_SCHEMA.JOBS, slot milliseconds, Cloud Monitoring | CloudWatch, query history, and workgroup metrics | Azure Monitor, query insights, and workspace metrics |
| Database connection pooling | Cloud SQL + HikariCP/Cloud SQL Connector | RDS/Aurora + HikariCP, RDS Proxy when suitable | Azure SQL Database + HikariCP, connection pooling/managed identity |
| Connection limits | Cloud SQL max_connections per engine/instance; Cloud Run built-in connection cap | Engine max connections and RDS Proxy/client limits | SQL connection limits per tier/service objectives |
| Distributed database clients | Spanner multiplexed sessions and gRPC channels | DynamoDB SDK connection/HTTP client pools or Aurora/DAX per workload | Cosmos DB SDK client reuse, connection modes, and endpoint topology |
| Quota governance | Cloud Quotas, BigQuery custom query quotas, budgets | Service Quotas, Budgets, and workgroup controls | Azure quotas/limits, Cost Management budgets |

Do not map a BigQuery quota one-to-one onto an Athena/Synapse limit. Each service has different billing units, quota scopes, and compute-limiting mechanisms. When moving across clouds, preserve the principles: estimate before running, cap per job, enforce aggregate quotas, monitor usage, and size connection budgets across the entire fleet.

## Summary

Controlling data costs and resources requires multiple layers. For on-demand BigQuery, reduce bytes scanned via column selection, partition pruning, clustering, and materialization; use dry runs with `maximumBytesBilled` to guard individual jobs; use custom daily query quotas and `INFORMATION_SCHEMA` to manage usage by project/user. Budget alerts warn on spend, but alerts-only budgets do not automatically stop services.

For Cloud SQL, connection budgets must cover all replicas: max instances multiplied by `maximumPoolSize`, plus workers, migrations, and rolling deployment headroom. HikariCP needs sensible bounds, connections must be returned to the pool, transactions kept short, and connectors/`DataSource` instances reused. Cloud SQL Java Connector also consumes Cloud SQL Admin API quota for metadata/certificate refreshes.

For modern Spanner Java clients, multiplexed sessions are enabled by default; reuse a single `Spanner` client and consider dynamic channel pooling rather than copying deprecated legacy session pool configurations. Monitor query usage, connection pools, database capacity, and retry rates to distinguish quota exhaustion from real bottlenecks.

## References

- [BigQuery — Estimate and control costs](https://docs.cloud.google.com/bigquery/docs/best-practices-costs) — on-demand/capacity pricing, dry runs, maximum bytes billed, and ways to reduce bytes scanned.
- [BigQuery — Quotas and limits](https://docs.cloud.google.com/bigquery/quotas) — query jobs, API quotas, and system limits.
- [BigQuery — Create custom query quotas](https://docs.cloud.google.com/bigquery/docs/custom-quotas) — project/user daily query usage quotas, reset times, and custom quota limits.
- [BigQuery — INFORMATION_SCHEMA.JOBS](https://docs.cloud.google.com/bigquery/docs/information-schema-jobs) — bytes billed, slot milliseconds, query jobs, and usage reporting.
- [BigQuery Java — Dry run query sample](https://docs.cloud.google.com/bigquery/docs/samples/bigquery-query-dry-run) — Java BigQuery client and QueryJobConfiguration.setDryRun.
- [Cloud Billing — Budgets and budget alerts](https://docs.cloud.google.com/billing/docs/how-to/budgets) — budget thresholds, notifications, and limitations of alerts-only budgets.
- [Cloud SQL — Manage database connections](https://docs.cloud.google.com/sql/docs/postgres/manage-connections) — HikariCP, connection pools, connection counts, and exponential backoff.
- [Cloud SQL — Quotas and limits](https://docs.cloud.google.com/sql/docs/quotas) — max_connections, Cloud Run built-in connection limits, and Admin API quotas.
- [Cloud Spanner — Sessions](https://docs.cloud.google.com/spanner/docs/sessions) — multiplexed sessions, session usage, and dynamic channel pooling.
- [Cloud Spanner Java — SpannerOptions.Builder](https://docs.cloud.google.com/java/docs/reference/google-cloud-spanner/latest/com.google.cloud.spanner.SpannerOptions.Builder) — dynamic channel pool configuration.
