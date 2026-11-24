# Adding Listeners and Metrics to a Spring Batch Project

## 1. Practice Project Objectives

A Spring Batch Job completing successfully does not mean operators know what it actually did. In production, you must be able to answer:

- Which Jobs are running, and which completed or failed?
- How many items did the Step read, write, filter, or skip?
- Are chunks typically succeeding or failing?
- Is Job/Step execution duration spiking abnormally?
- Is the output data accurate, or did the Job report `COMPLETED` while processing incorrectly?
- Can metrics be exported to Prometheus/Grafana for monitoring without leaking sensitive data?

The lesson **"Adding Listeners and Metrics"** belongs to **Practice Projects** in *Spring Batch Core Processing*. You will upgrade a CSV-to-database import Job with three listener groups and Micrometer:

1. `JobExecutionListener` tracking the outcome of the whole Job.
2. `StepExecutionListener` recording read/write/filter/skip item counts.
3. `ChunkListener` tracking chunk successes and errors.
4. `MeterRegistry` storing and exporting custom counters; Spring Batch/Micrometer also provides built-in duration metrics.
5. `@SpringBatchTest` verifying status, data output, and custom metrics.

The primary example targets **Java 17+, Spring Boot 3.x, and Spring Batch 5.2.x** with H2 for local runs. The final section explains differences when moving to Spring Batch 6.x. APIs between the two version lines differ, so do not copy imports mechanically.

### Expected Results

With a 6-row input file where 2 rows with amount 0 are filtered:

| Result | Value |
| --- | ---: |
| Items read | 6 |
| Items filtered | 2 |
| Items written to database | 4 |
| Valid amount total | 850 |
| Final `BatchStatus` | `COMPLETED` |
| Job completion metric | Incremented by 1 |
| Step read/write/filter metrics | Incremented by 6/4/2 respectively |

These are **illustrative fixture values**, not universal thresholds for every Job.

## 2. What Are Listeners and Where Do They Sit?

A listener is a callback invoked at a point in the Job/Step lifecycle or around item/chunk processing. It separates **observability, auditing, and statistics** from reading, processing, and writing logic.

~~~text
         Spring Batch Job
                |
     JobExecutionListener.beforeJob
                |
                v
         importOrdersStep
                |
     StepExecutionListener.beforeStep
                |
                v
     +--------------------------+
     | Chunk: read -> process   |
     |        -> write -> commit|
     +--------------------------+
              |         |
         success       error
              |         |
              v         v
      afterChunk   afterChunkError
                |
     StepExecutionListener.afterStep
                |
                v
     JobExecutionListener.afterJob
                |
                v
           MeterRegistry
                |
                v
      Actuator / Prometheus
                |
                v
          Grafana / Alert
~~~

In Spring Batch 5.2, key callbacks include:

| Listener | Callback | Observed Information |
| --- | --- | --- |
| `JobExecutionListener` | `beforeJob`, `afterJob` | Job name, execution ID, `BatchStatus`, `ExitStatus`, final errors. |
| `StepExecutionListener` | `beforeStep`, `afterStep` | Step name, read/write/filter/skip, commit/rollback, status. |
| `ChunkListener` | `beforeChunk`, `afterChunk`, `afterChunkError` | Chunk cycle, chunk completion or error. |
| `ItemReadListener` | `beforeRead`, `afterRead`, `onReadError` | Reader errors and activity. |
| `ItemProcessListener` | `beforeProcess`, `afterProcess`, `onProcessError` | Processor, filtering, and processing errors. |
| `ItemWriteListener` | `beforeWrite`, `afterWrite`, `onWriteError` | Writer and write errors. |
| `SkipListener` | `onSkip...` callbacks | Items skipped under policy. |

**Avoid attaching heavy per-item callbacks in very large Jobs** just to log INFO on every read: one million items can produce one million log lines. For dashboards, prefer aggregated metrics or sampling.

### Listeners Do Not Replace Business Logic

- `ItemProcessor` remains responsible for transformation/filtering.
- `ItemWriter` remains responsible for persisting data.
- `JobRepository` remains responsible for storing metadata and checkpoints.
- Listeners only observe, emit metrics/logs, or perform controlled auxiliary actions.

If an error inside a listener prevents the Job from continuing, you can break a data batch simply because the metrics system had a temporary glitch. For non-business-critical telemetry, listeners should **never throw exceptions outward** if observation errors can be handled safely.

## 3. Distinguishing Built-In Metrics from Custom Metrics

Spring Batch 5.2 integrates Micrometer and exposes several metrics prefixed with `spring.batch`:

| Built-in Micrometer Metric | Type | Purpose |
| --- | --- | --- |
| `spring.batch.job` | Timer | Job duration. |
| `spring.batch.job.active` | LongTaskTimer | Currently active Jobs. |
| `spring.batch.step` | Timer | Step duration. |
| `spring.batch.step.active` | LongTaskTimer | Currently active Steps. |
| `spring.batch.item.read` | Timer | Item read time. |
| `spring.batch.item.process` | Timer | Item processing time. |
| `spring.batch.chunk.write` | Timer | Chunk write time. |

In Spring Batch **5.2.x**, these built-in metrics are registered via Micrometer's **global registry**. When using Spring Boot Actuator and Micrometer, ensure the registry is wired to the observability backend. Exported Prometheus metric names follow naming conventions (e.g., timers may carry a `_seconds` suffix).

We will add custom metrics:

| Application Metric | Type | Meaning |
| --- | --- | --- |
| `app.batch.job.executions` | Counter | Number of `JobExecution`s reaching `afterJob`, by Job and `BatchStatus`. |
| `app.batch.step.items` | Counter | Item counts by `read`, `write`, `filter`, `skip` operation, added at end of `StepExecution`. |
| `app.batch.chunk.events` | Counter | Number of chunk `success` or `error` callbacks observed by the listener. |

**These are project-defined custom metrics**, not built-in Spring Batch metrics. When exported to Prometheus, these names typically become `app_batch_job_executions_total`, `app_batch_step_items_total`, and `app_batch_chunk_events_total`.

Do not define a custom timer identical to a built-in timer without a specific purpose; doing so creates duplicate dashboard content and complicates comparisons.

## 4. Sample Project Structure

~~~text
batch-observability-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/batch/
    │   │   ├── BatchObservabilityApplication.java
    │   │   ├── OrderRow.java
    │   │   ├── ImportJobConfiguration.java
    │   │   ├── JobMetricsListener.java
    │   │   ├── StepMetricsListener.java
    │   │   └── ChunkMetricsListener.java
    │   └── resources/
    │       ├── application.yml
    │       ├── schema.sql
    │       └── orders.csv
    └── test/
        ├── java/com/example/batch/ImportJobIT.java
        └── resources/application-test.yml
~~~

The example uses one Job `importOrdersJob`, one Step `importOrdersStep`, one CSV reader, and one JDBC writer. We filter records with `amount <= 0` in `ItemProcessor` and measure results through listeners.

### 4.1. Dependencies

In a Spring Boot 3.x project compatible with Spring Batch 5.2.x, add dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-web'

    runtimeOnly 'com.h2database:h2'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Dependency versions above are coordinated by **Spring Boot dependency management**. If a project must pin Spring Batch 5.2, pick a Spring Boot 3.x release managing that line or configure dependency management explicitly; never randomly mix Batch 5.x libraries with 6.x APIs.

`spring-boot-starter-actuator` provides monitoring infrastructure, `micrometer-registry-prometheus` provides the exporter, and `spring-boot-starter-web` keeps the demo app running to serve Actuator HTTP endpoints.

## 5. Preparing Input and Database

### 5.1. Input CSV

File `src/main/resources/orders.csv`:

~~~csv
id,amount
1,100
2,0
3,200
4,150
5,0
6,400
~~~

Two rows with amount 0 are filtered by `ItemProcessor`. Four valid rows have IDs `1,3,4,6`, totaling `100 + 200 + 150 + 400 = 850`.

### 5.2. Business Schema

File `src/main/resources/schema.sql`:

~~~sql
CREATE TABLE imported_orders (
    id BIGINT PRIMARY KEY,
    amount BIGINT NOT NULL
);
~~~

`PRIMARY KEY (id)` helps the practice project detect accidental duplicate writes by the writer. In production, this key must be based on a business key and proper idempotency policy; a primary key alone does not handle all off-transaction side effects.

### 5.3. Application Configuration

File `src/main/resources/application.yml`:

~~~yaml
spring:
  datasource:
    url: jdbc:h2:mem:batch_observability;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
  sql:
    init:
      mode: always
  batch:
    jdbc:
      initialize-schema: always
    job:
      enabled: true

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    prometheus:
      access: unrestricted
~~~

This is a **local demo** configuration. In production environments:

- Never publicly expose `/actuator/prometheus` or sensitive administrative endpoints.
- Enforce authentication, network policies, and proper read permissions.
- In-memory H2 does not support cross-JVM restarts; use a persistent database for `JobRepository` when crash recovery is required.
- `BATCH_*` table schemas must be managed by appropriate initialization/migration mechanisms.
- The Job is auto-launched by Boot at startup because `spring.batch.job.enabled=true`; the demo has only one Job. Production should explicitly use a scheduler/launcher with stable identifying `JobParameters`.

Note that Actuator properties changed partially across Spring Boot 3.x releases. If a Boot version does not support `management.endpoint.prometheus.access`, use the matching endpoint configuration for that Boot release. HTTP endpoint security rules remain the same.

## 6. Application and Model

File `BatchObservabilityApplication.java`:

~~~java
package com.example.batch;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BatchObservabilityApplication {
    public static void main(String[] args) {
        SpringApplication.run(
            BatchObservabilityApplication.class, args);
    }
}
~~~

File `OrderRow.java`:

~~~java
package com.example.batch;

public class OrderRow {

    private final Long id;
    private final Long amount;

    public OrderRow(Long id, Long amount) {
        this.id = id;
        this.amount = amount;
    }

    public Long getId() {
        return id;
    }

    public Long getAmount() {
        return amount;
    }
}
~~~

We choose a JavaBean with getters so `JdbcBatchItemWriterBuilder.beanMapped()` can read `id` and `amount` properties.

## 7. Job-Level Listener

File `JobMetricsListener.java`:

~~~java
package com.example.batch;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;
import org.springframework.stereotype.Component;

@Component
public class JobMetricsListener implements JobExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(JobMetricsListener.class);

    private final MeterRegistry registry;

    public JobMetricsListener(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public void beforeJob(JobExecution execution) {
        log.info(
            "batch_job_started job={} executionId={}",
            execution.getJobInstance().getJobName(),
            execution.getId());
    }

    @Override
    public void afterJob(JobExecution execution) {
        String jobName = execution.getJobInstance().getJobName();
        String status = execution.getStatus().name();

        log.info(
            "batch_job_finished job={} executionId={} " +
            "batchStatus={} exitCode={}",
            jobName,
            execution.getId(),
            status,
            execution.getExitStatus().getExitCode());

        try {
            Counter.builder("app.batch.job.executions")
                    .description(
                        "Finished JobExecution callbacks observed")
                    .tag("job", jobName)
                    .tag("status", status)
                    .register(registry)
                    .increment();
        } catch (RuntimeException metricsError) {
            // Telemetry should not fail the Job.
            log.warn(
                "Could not record job metric for job={}",
                jobName);
        }
    }
}
~~~

Key points:

- `afterJob` counts **`JobExecution`s observed by the listener**, not `JobInstance`s. One `JobInstance` may have multiple `JobExecution`s after restarts.
- `status` has a bounded set of values such as `COMPLETED`, `FAILED`, `STOPPED`, suitable as a metric tag.
- `executionId` appears only in logs for investigation, **never** as a Prometheus label because cardinality grows with every run.
- Listeners are registered when building the Job; merely annotating `@Component` does not guarantee every Job invokes the listener.
- Never log full `JobParameters`, access tokens, or exception messages that might contain secrets.

`try/catch` illustrates preventing metric errors from overriding business outcomes. In systems with strict policies, you can monitor exporter/registry failures separately without corrupting Job status semantics.

## 8. Step-Level Listener

File `StepMetricsListener.java`:

~~~java
package com.example.batch;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;
import org.springframework.stereotype.Component;

@Component
public class StepMetricsListener implements StepExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(StepMetricsListener.class);

    private final MeterRegistry registry;

    public StepMetricsListener(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public void beforeStep(StepExecution stepExecution) {
        log.info(
            "batch_step_started step={} stepExecutionId={}",
            stepExecution.getStepName(),
            stepExecution.getId());
    }

    @Override
    public ExitStatus afterStep(StepExecution execution) {
        String job = execution.getJobExecution()
                .getJobInstance().getJobName();
        String step = execution.getStepName();

        log.info(
            "batch_step_finished job={} step={} status={} " +
            "read={} write={} filter={} skip={} " +
            "commit={} rollback={}",
            job, step, execution.getStatus(),
            execution.getReadCount(),
            execution.getWriteCount(),
            execution.getFilterCount(),
            execution.getSkipCount(),
            execution.getCommitCount(),
            execution.getRollbackCount());

        try {
            count(job, step, "read", execution.getReadCount());
            count(job, step, "write", execution.getWriteCount());
            count(job, step, "filter", execution.getFilterCount());
            count(job, step, "skip", execution.getSkipCount());
        } catch (RuntimeException metricsError) {
            log.warn(
                "Could not record step metrics job={} step={}",
                job, step);
        }

        // null means do not modify the Step's ExitStatus.
        return null;
    }

    private void count(
            String job, String step, String operation, long amount) {
        Counter.builder("app.batch.step.items")
                .description("Item counts from completed StepExecutions")
                .tag("job", job)
                .tag("step", step)
                .tag("operation", operation)
                .register(registry)
                .increment(amount);
    }
}
~~~

In Spring Batch 5.2, `StepExecutionListener.afterStep` has return type `ExitStatus`. Returning `null` preserves the existing `ExitStatus`; if intentionally overriding the exit code, do so explicitly per the Job/flow contract—never use a metric listener to accidentally alter business outcomes.

### Reading `StepExecution` Metrics with Accurate Semantics

| Value | Meaning |
| --- | --- |
| `getReadCount()` | Number of items read by the reader per Step semantics. |
| `getWriteCount()` | Number of items written by the writer per Step semantics. |
| `getFilterCount()` | Number of items filtered by the processor returning `null`. |
| `getSkipCount()` | Total items skipped across read/process/write per policy. |
| `getCommitCount()` | Number of commits recorded by `StepExecution`. |
| `getRollbackCount()` | Number of rollbacks recorded by `StepExecution`. |

**Do not equate `rollbackCount` with retry count**, and do not treat `readCount` as the physical number of `ItemReader.read()` calls. Under rollbacks/retries, an item may be read or processed again.

The counter in the example records each `StepExecution`'s counts in the `afterStep` callback. This is an **observed** aggregate figure, not a durable exactly-once audit across JVM crashes. If the process dies before `afterStep`, metrics may not be emitted even though the database committed partial data.

## 9. Chunk-Level Listener

File `ChunkMetricsListener.java`:

~~~java
package com.example.batch;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ChunkListener;
import org.springframework.batch.core.scope.context.ChunkContext;
import org.springframework.stereotype.Component;

@Component
public class ChunkMetricsListener implements ChunkListener {

    private static final Logger log =
            LoggerFactory.getLogger(ChunkMetricsListener.class);

    private final MeterRegistry registry;

    public ChunkMetricsListener(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public void afterChunk(ChunkContext context) {
        record(context, "success");
    }

    @Override
    public void afterChunkError(ChunkContext context) {
        record(context, "error");
    }

    private void record(ChunkContext context, String event) {
        String job = context.getStepContext()
                .getStepExecution()
                .getJobExecution()
                .getJobInstance()
                .getJobName();
        String step = context.getStepContext().getStepName();

        try {
            Counter.builder("app.batch.chunk.events")
                    .description("Chunk listener events")
                    .tag("job", job)
                    .tag("step", step)
                    .tag("event", event)
                    .register(registry)
                    .increment();
        } catch (RuntimeException metricsError) {
            log.warn(
                "Could not record chunk metric job={} step={}",
                job, step);
        }
    }
}
~~~

In Spring Batch 5.2, `afterChunk(ChunkContext)` is called after a successful chunk, outside the transaction, while `afterChunkError(ChunkContext)` signals a chunk failure/rollback. A single `afterChunkError` **does not necessarily make the entire Job `FAILED`**: the framework may retry or skip and continue.

With a fault-tolerant Step, chunk callbacks can fire during item scanning/re-execution after a writer error. Thus this metric should be defined as **observed callback events**, not exact committed rows or business transactions.

Chunk listeners must not throw exceptions. Logging on every chunk can also be very noisy when chunk size is small; the example only records metrics without logging success on each chunk.

## 10. Configuring Job, Step, Reader, Processor, and Writer

File `ImportJobConfiguration.java`:

~~~java
package com.example.batch;

import javax.sql.DataSource;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration(proxyBeanMethods = false)
public class ImportJobConfiguration {

    @Bean
    @StepScope
    FlatFileItemReader<OrderRow> ordersReader() {
        return new FlatFileItemReaderBuilder<OrderRow>()
                .name("ordersReader")
                .resource(new ClassPathResource("orders.csv"))
                .linesToSkip(1)
                .delimited()
                .names("id", "amount")
                .fieldSetMapper(fields -> new OrderRow(
                        fields.readLong("id"),
                        fields.readLong("amount")))
                .build();
    }

    @Bean
    ItemProcessor<OrderRow, OrderRow> ordersProcessor() {
        return row -> row.getAmount() > 0 ? row : null;
    }

    @Bean
    JdbcBatchItemWriter<OrderRow> ordersWriter(DataSource dataSource) {
        return new JdbcBatchItemWriterBuilder<OrderRow>()
                .dataSource(dataSource)
                .sql(
                    "INSERT INTO imported_orders(id, amount) " +
                    "VALUES (:id, :amount)")
                .beanMapped()
                .build();
    }

    @Bean
    Step importOrdersStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            FlatFileItemReader<OrderRow> ordersReader,
            ItemProcessor<OrderRow, OrderRow> ordersProcessor,
            JdbcBatchItemWriter<OrderRow> ordersWriter,
            StepMetricsListener stepMetricsListener,
            ChunkMetricsListener chunkMetricsListener) {

        return new StepBuilder("importOrdersStep", jobRepository)
                .<OrderRow, OrderRow>chunk(2, transactionManager)
                .reader(ordersReader)
                .processor(ordersProcessor)
                .writer(ordersWriter)
                .listener(stepMetricsListener)
                .listener(chunkMetricsListener)
                .build();
    }

    @Bean
    Job importOrdersJob(
            JobRepository jobRepository,
            Step importOrdersStep,
            JobMetricsListener jobMetricsListener) {

        return new JobBuilder("importOrdersJob", jobRepository)
                .listener(jobMetricsListener)
                .start(importOrdersStep)
                .build();
    }
}
~~~

### Explanation of Choices

- `@StepScope` gives a dedicated reader per `StepExecution` and enables proper restart state on the reader.
- `FlatFileItemReaderBuilder` reads CSV by column name; `linesToSkip(1)` skips the header.
- The processor returns `null` for amount 0; this is a **filter**, not an exception-based skip.
- `JdbcBatchItemWriter` receives `OrderRow` with getters and writes valid rows.
- `chunk(2, transactionManager)` defines processing/transaction boundaries of two input items; the final chunk may be smaller.
- `.listener(stepMetricsListener)` and `.listener(chunkMetricsListener)` attach callbacks to the Step.
- `.listener(jobMetricsListener)` attaches the callback to the Job.
- Do not store metric state in `ExecutionContext`; Micrometer manages metrics, whereas the repository stores metadata and restart state.

For real systems, pass file name, `businessDate`, and output resources via valid `JobParameters` or controlled configuration. Never pass raw secrets in `JobParameters`, and ensure the input snapshot does not change between restarts.

## 11. Running the Application and Viewing Metrics

For the demo app with one Job and `spring.batch.job.enabled=true`, start with:

~~~bash
./gradlew bootRun
~~~

On Windows, use the corresponding Gradle wrapper (`gradlew.bat bootRun`). The example assumes the Gradle plugin and Java toolchain are properly configured for the project.

When Boot auto-launches the Job, the CSV has six input items, the Step completes, and the writer saves four rows to H2. The logger will typically record Job and Step start/end events; specific ID values depend on the database/sequences.

Because the demo includes the web starter and Actuator, you can open:

~~~text
http://localhost:8080/actuator/health
http://localhost:8080/actuator/metrics
http://localhost:8080/actuator/prometheus
~~~

In production, never expose admin or Prometheus endpoints publicly to the Internet. Specific endpoints require enabling exposure and configuring proper authentication, reverse proxies, and network policies.

### Expected Prometheus Output

Micrometer name `app.batch.job.executions` is typically exported as:

~~~text
app_batch_job_executions_total{
    job="importOrdersJob",
    status="COMPLETED"
} 1
~~~

Event/item counts:

~~~text
app_batch_step_items_total{
    job="importOrdersJob",
    step="importOrdersStep",
    operation="read"
} 6

app_batch_step_items_total{
    job="importOrdersJob",
    step="importOrdersStep",
    operation="write"
} 4

app_batch_step_items_total{
    job="importOrdersJob",
    step="importOrdersStep",
    operation="filter"
} 2
~~~

The snippets above describe **expected series**, not stdout captured from an actual run of the project. Metric names and exporting also depend on Micrometer and backend version/configuration.

### Do You Need a Separate Duration Timer?

Not necessarily. Spring Batch 5.2 already provides `spring.batch.job` and `spring.batch.step` Timers. Use them for general latency; custom listeners are more useful for business/operational counts not already covered by built-in metrics.

If you need to measure a specific business operation inside `ItemProcessor`/`Tasklet`, use `Timer.Sample` or `Timer.record` with a **different** metric name and low-cardinality tags.

## 12. Prometheus Queries and Grafana Dashboards

Assuming an application runs multiple times, counter metrics accumulate over the registry lifecycle. You can query:

**JobExecutions completed in the last hour:**

~~~promql
sum by (job) (
  increase(
    app_batch_job_executions_total{status="COMPLETED"}[1h]
  )
)
~~~

**JobExecutions failed in one hour:**

~~~promql
sum by (job) (
  increase(
    app_batch_job_executions_total{status="FAILED"}[1h]
  )
)
~~~

**Items written in 15 minutes:**

~~~promql
sum by (job, step) (
  increase(
    app_batch_step_items_total{operation="write"}[15m]
  )
)
~~~

**Chunk error rate:**

~~~promql
sum by (job, step) (
  rate(
    app_batch_chunk_events_total{event="error"}[5m]
  )
)
~~~

**Share of items filtered in a window:**

~~~promql
sum by (job, step) (
  increase(
    app_batch_step_items_total{operation="filter"}[1h]
  )
)
/
clamp_min(
  sum by (job, step) (
    increase(
      app_batch_step_items_total{operation="read"}[1h]
    )
  ),
  1
)
~~~

This is the share **based on counts aggregated by `StepExecution` in the observation window**, not a real-time percentage of direct processor filter callbacks. For a Job running only nightly, pick a wide enough window and avoid interpreting a zero series when the Job is idle.

Suggested dashboard:

| Panel | Source | Question |
| --- | --- | --- |
| Job completions/failures | Custom `app.batch.job.executions` | Is the batch schedule failing? |
| Job/Step duration | Built-in timers | Is it slower than usual? |
| Read/write/filter | Custom `app.batch.step.items` | Did throughput drop or filtering rise? |
| Chunk error rate | Custom `app.batch.chunk.events` | Is chunk failure spiking? |
| Latest Job status | `JobRepository` | What state is a specific run in? |
| Step read/write/skip counts per execution | JDBC metadata | What did a single execution process? |
| Business totals | Business database | Is the final data truly accurate? |

Micrometer counters **do not replace `JobRepository`**. When the JVM restarts, in-process counters can reset; Prometheus handles counter resets in `rate`/`increase`. If exact auditing of a `JobInstance` across crashes is needed, use appropriate persistent metadata/audit tables.

## 13. Integration Test: Checking Both Metrics and Data

If tests only confirm the Job is `COMPLETED` or that `job.executions` incremented by one, data read/write bugs can still slip through. Therefore, tests must verify all of:

1. `JobExecution` `COMPLETED`.
2. `StepExecution` read = 6, write = 4, filter = 2, skip = 0.
3. The `imported_orders` table contains exact IDs `1,3,4,6` and total amount = 850.
4. Custom metrics incremented accordingly.

File `src/test/resources/application-test.yml`:

~~~yaml
spring:
  batch:
    job:
      enabled: false
~~~

The test disables Boot auto-launch so it can launch the Job explicitly with `JobLauncherTestUtils`. The example has only one Job, yet we still set the Job explicitly.

File `ImportJobIT.java`:

~~~java
package com.example.batch;

import java.util.List;

import io.micrometer.core.instrument.MeterRegistry;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.JobRepositoryTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.*;

@SpringBatchTest
@SpringBootTest
@ActiveProfiles("test")
class ImportJobIT {

    @Autowired JobLauncherTestUtils launcher;
    @Autowired JobRepositoryTestUtils repositoryUtils;
    @Autowired JdbcTemplate jdbc;
    @Autowired MeterRegistry metrics;

    @Autowired
    @Qualifier("importOrdersJob")
    Job job;

    @BeforeEach
    void prepare() {
        launcher.setJob(job);

        // Run only on an isolated H2/test DB.
        repositoryUtils.removeJobExecutions();
        jdbc.update("DELETE FROM imported_orders");
    }

    @Test
    void recordsMetricsAndCorrectBusinessData() throws Exception {
        JobParameters params = new JobParametersBuilder()
                .addString("caseId", "case-725", true)
                .toJobParameters();

        JobExecution execution = launcher.launchJob(params);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());

        StepExecution step = execution.getStepExecutions().stream()
                .filter(se -> "importOrdersStep".equals(
                        se.getStepName()))
                .findFirst()
                .orElseThrow();

        assertEquals(BatchStatus.COMPLETED, step.getStatus());
        assertEquals(6, step.getReadCount());
        assertEquals(4, step.getWriteCount());
        assertEquals(2, step.getFilterCount());
        assertEquals(0, step.getSkipCount());

        List<Long> ids = jdbc.queryForList(
                "SELECT id FROM imported_orders ORDER BY id",
                Long.class);
        assertEquals(List.of(1L, 3L, 4L, 6L), ids);

        Long amount = jdbc.queryForObject(
                "SELECT SUM(amount) FROM imported_orders",
                Long.class);
        assertEquals(850L, amount);

        assertEquals(1.0,
            metrics.get("app.batch.job.executions")
                .tags("job", "importOrdersJob",
                      "status", "COMPLETED")
                .counter().count(),
            0.001);

        assertEquals(6.0,
            metrics.get("app.batch.step.items")
                .tags("job", "importOrdersJob",
                      "step", "importOrdersStep",
                      "operation", "read")
                .counter().count(),
            0.001);

        assertEquals(4.0,
            metrics.get("app.batch.step.items")
                .tags("job", "importOrdersJob",
                      "step", "importOrdersStep",
                      "operation", "write")
                .counter().count(),
            0.001);

        assertEquals(2.0,
            metrics.get("app.batch.step.items")
                .tags("job", "importOrdersJob",
                      "step", "importOrdersStep",
                      "operation", "filter")
                .counter().count(),
            0.001);
    }
}
~~~

### Why Is This Test Valuable?

- If the processor mistakenly filters a valid row, ID/amount results or read/write/filter counts change and the test fails.
- If the writer maps values incorrectly, counts may stay right while `SUM(amount)` fails.
- If listeners are not attached to the Step or Job, expected metrics are not emitted and the test fails.
- If the Job does not run, target data cannot satisfy the assertions.
- If the Job hits an exception, `BatchStatus` will differ from `COMPLETED`.

**Metric isolation in tests:** The example above has a single standalone test with Boot auto-launch disabled. In a test suite where multiple tests share an `ApplicationContext`/`MeterRegistry`, counters accumulate. In that case, measure **before/after deltas**, use separate registries/test contexts, or design each test to be order-independent. Never assume counters always start at 0.

Never delete `BATCH_*` tables in production; `JobRepositoryTestUtils.removeJobExecutions()` is strictly for isolated test databases. When testing restarts, **do not** delete metadata between the failed execution and the recovery execution.

## 14. When Listeners and Metrics Differ from Metadata Counts

A common question: "Why do callback counts differ from `COMMIT_COUNT` in the database?"

The reason is that they measure **different things**:

- `app.batch.chunk.events{event="success"}` counts `afterChunk` callbacks observed by the listener.
- `StepExecution.getCommitCount()` is a transaction counter stored by the framework in metadata, which may include internal commit points depending on the execution path.
- `StepExecution.getWriteCount()` is the number of items recorded as written per Step semantics, not necessarily the number of JDBC statements sent over the network.
- `ItemWriteListener` may be re-invoked after retries/rollbacks, even though ultimately only one chunk commits.
- A `JobExecution` can fail after committing earlier chunks; the Job-end listener may not run if the JVM is force-killed.

Therefore, when designing metrics:

| What You Want to Measure | Instrumentation Point |
| --- | --- |
| Job completion/failure per framework | `JobExecutionListener` after Job or querying repository. |
| Read/write/filter/skip per `StepExecution` | `StepExecutionListener` after Step. |
| Chunk callback events | `ChunkListener`. |
| Retry callback failures | Retry subsystem's `RetryListener`, with a metric name clearly stating the unit. |
| Physical HTTP requests | HTTP client instrumentation. |
| Committed business data | Database/output audits and business queries. |
| Restarts of a `JobInstance` | `JobRepository` and `JobExecution` history. |

Do not lump everything into one variable named `retryCount` or `processedCount` if they have different units.

## 15. Failure Cases: Which Listener Emits Signals?

Suppose the processor throws an exception not configured for retry/skip:

~~~text
Input item #3
    |
    v
ItemProcessor throws
    |
    v
Chunk error / rollback
    |
    v
StepExecution FAILED
    |
    v
JobExecution FAILED
~~~

In this scenario, you can observe:

- `ChunkListener.afterChunkError` is invoked when the chunk rolls back and the listener is active.
- `StepExecutionListener.afterStep` sees `FAILED` status and per-Step read/write/filter/skip counts.
- `JobExecutionListener.afterJob` counts a `FAILED` `JobExecution` if the framework is able to execute the callback.
- Built-in timers record elapsed time if the observability system is active.

However, **not every callback is guaranteed to run when the JVM dies abruptly**. In-memory metrics can also be lost before the next Prometheus scrape. For incident recovery, `JobRepository` and business data are more important sources of reconciliation than runtime counters.

### Should Alerts Be Sent Directly from Listeners?

You can send an event/notification from `afterJob` on `FAILED`, yet you should not call a synchronous alerting API and let an alerting API error fail the Job further. Prefer having listeners emit logs/metrics, while Alertmanager/Grafana/Prometheus trigger alerts based on rules.

If the business requires **accurate, durable auditing**, write an audit/outbox table with separate transaction/retry verification; never turn a Micrometer `Counter` into the sole proof that a transaction occurred.

## 16. Tags, Cardinality, and Sensitive Data

Metric tags should have a bounded set of values:

~~~text
job=importOrdersJob
step=importOrdersStep
status=COMPLETED|FAILED|STOPPED
operation=read|write|filter|skip
event=success|error
environment=test|staging|production
~~~

Values that **should not** become Prometheus labels:

~~~text
jobExecutionId=123456789
orderId=100012399
customerEmail=sample@example.org
fileName=/private/tenant/acme/2026-11-16/orders.csv
exceptionMessage=token=...
accessToken=...
~~~

A new label per item/execution creates excessively high cardinality, consumes RAM, and can leak sensitive information. Place execution IDs in **structured logs** with proper access controls and retention; use only stable Job/Step/status names in metrics.

To group exceptions, use an allowlist such as `transient_db`, `timeout`, `invalid_input`, `other` instead of using full exception messages or specific file paths as tags.

### Logs Also Need Controls

Example listener logging only:

~~~text
job=importOrdersJob
executionId=42
status=FAILED
exitCode=FAILED
```

Never log raw `JobParameters` if they could contain secrets; better yet, design `JobParameters` **never to contain raw credentials in the first place**.

## 17. Monitoring Multi-Threading, Partitioning, and Remote Processing

When scaling batch processing:

- Multiple `StepExecution`s may emit metrics for the same Step name; Micrometer counters are aggregates, not per-execution detail tables.
- Partitioning creates distinct worker-level executions; for Job totals, aggregate partitions semantically and avoid double-counting manager and workers.
- Remote chunking runs separate worker processes; each process has its own `MeterRegistry`, requiring collection and aggregation in the metrics backend.
- Listeners on worker threads may lack some `ThreadLocal` contexts that manager-thread listeners rely on.
- Runtime Timers/Counters can reset when Pods restart; use `rate`/`increase` on counters for observation.
- Never use unsynchronized `static int retryCount`/`processedCount` variables as overview metrics in multi-threaded systems.

A dashboard should distinguish **system-wide throughput** from individual `JobInstance`s. To inspect a specific instance, use `JobRepository` and logs/traces carrying the execution ID, rather than creating per-ID metric labels.

## 18. Adding Metrics for Business Errors

Some data **cannot be inferred solely from read/write counts**. For example, when the processor excludes a record for an invalid amount:

~~~java
@Bean
ItemProcessor<OrderRow, OrderRow> ordersProcessor(
        MeterRegistry metrics) {

    return row -> {
        if (row.getAmount() <= 0) {
            Counter.builder("app.batch.orders.rejected")
                    .description("Orders rejected by validation rule")
                    .tag("reason", "non_positive_amount")
                    .register(metrics)
                    .increment();
            return null;
        }

        return row;
    };
}
~~~

This example **replaces** the processor bean in Section 10; do not add a duplicate bean with the same name in the same configuration. It records business filter reasons, with important caveats:

- The processor callback may be re-invoked during chunk rollbacks or Step restarts.
- A counter incremented directly inside the processor **does not roll back** with the JDBC transaction.
- Thus this counter counts **processor calls detecting invalid records**, not guaranteed one-per-business-item events.
- To count each uniquely excluded item, persist results to a quarantine/audit table with a business key and proper transaction/idempotency.

Name metrics after the actual unit counted and document semantics on the dashboard.

## 19. How Does Spring Batch 6.x Differ?

The concepts of `JobExecutionListener`, `StepExecutionListener`, `ChunkListener`, and Micrometer still exist, yet the APIs are reorganized:

| Topic | Spring Batch 5.2.x | Spring Batch 6.x |
| --- | --- | --- |
| Packages | Many types live in `org.springframework.batch.core` | Types organized into job/step subpackages; some listener signatures changed. |
| Step chunk builder | `chunk(size, transactionManager)` | `chunk(size).transactionManager(transactionManager)` per 6.x builder. |
| Testing utility | `JobLauncherTestUtils` | `JobOperatorTestUtils` |
| Built-in metrics | Typically works via Micrometer global registry | Requires configuring `ObservationRegistry` to enable built-in observations per 6.x docs. |
| Custom metrics | `MeterRegistry`/Micrometer | Can still use `MeterRegistry`; check exact 6.x listener APIs. |

In Spring Batch 6.x, an integrated observation configuration may use `ObservationRegistry` and a handler writing to `MeterRegistry`:

~~~java
@Bean
ObservationRegistry observationRegistry(MeterRegistry meterRegistry) {
    ObservationRegistry registry = ObservationRegistry.create();
    registry.observationConfig().observationHandler(
            new DefaultMeterObservationHandler(meterRegistry));
    return registry;
}
~~~

Corresponding imports belong to Micrometer Observation and Meter handlers; verify your project's dependencies/versions. Do not confuse custom counters (invoked directly on `MeterRegistry` by listeners) with enabling built-in Spring Batch observations.

**Note:** `ChunkListener` and builder signatures in 6.x are not necessarily identical to Spring Batch 5.2; migrate code per 6.x Javadoc rather than just bumping the dependency version.

## 20. Common Mistakes

**Adding `@Component` yet forgetting `.listener(...)`.** The listener is not attached to the Job/Step being monitored.

**Reading only `BatchStatus.COMPLETED`.** Skipping output data and read/write/filter counts can miss business errors.

**Assuming `rollbackCount` is retry count.** Rollbacks, retries, and skips are separate concepts.

**Recording per-item metrics with an `orderId` label.** Causes uncontrolled cardinality.

**Counting metrics inside the processor and treating them as unique committed items.** Rollbacks/retries/restarts can re-run the processor.

**Throwing exceptions because the metrics backend is unreachable.** Observability systems must not corrupt business outcomes.

**Printing full `JobParameters` in logs.** Risks exposing credentials or sensitive info.

**Counting `JobExecution`s as `JobInstance`s.** One instance can restart multiple times.

**Asserting a custom counter always equals 1 in a shared test suite.** Registries persist across tests; isolate or measure deltas.

**Checking metrics only without checking data.** Recorded metrics may show `writeCount=4` while amounts are still wrong.

**Reading runtime metrics instead of `JobRepository` during crash recovery.** Listeners do not always run if the JVM dies abruptly.

**Using Spring Batch 6 APIs with 5.2 imports.** Builder/listener signatures and observability infrastructure change across versions.

## 21. Extension Exercises

### Exercise 1 — Detecting Data Errors in a Step

Change the processor to also filter item `id=3`, then re-run the integration test. Confirm the test fails on `writeCount` or output IDs, even though the Job is still `COMPLETED`.

### Exercise 2 — Error-Classification Metrics

Trigger a non-retryable exception in the processor. Add an `ItemProcessListener` to count errors by allowlisted category. Verify error counters and `JobStatus FAILED`, avoiding per-item ID labels.

### Exercise 3 — Retry and Skip

Configure a fault-tolerant Step with appropriate `retryLimit` and `skipLimit`, then measure error callbacks. Explain why a single item can emit multiple error events yet be skipped only once.

### Exercise 4 — Duration Timer

Use built-in `spring.batch.step` to compare runtime when increasing item counts or reducing chunk size. If creating a custom timer, name it clearly and check whether it duplicates the built-in timer.

### Exercise 5 — Prometheus and Grafana

Build a dashboard with Job completions/failures, Step duration, read/write/filter throughput, chunk error rate, and latest `JobStatus`. Pick time windows matching the batch schedule.

### Exercise 6 — Restart

Intentionally fail the first `JobExecution` after one chunk commit, then restart the same `JobInstance`. Verify final data has no duplicates and the `JobExecution` metric increments twice by outcome; do not conclude there are two `JobInstance`s.

### Exercise 7 — Multi-Threading and Cardinality

Scale the Step to partitions or parallel workers. Ensure metrics aggregate at the right scope, never use per-item IDs as labels, and never store per-execution state in a mutable singleton variable.

### Exercise 8 — Observability Failure

Simulate an error when the custom metrics listener records a metric. Verify the application preserves the Job outcome and logs the telemetry failure appropriately without causing new business side effects.

## 22. Official References

- [Spring Batch 5.2 — Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/5.2/monitoring-and-metrics.html)
- [Spring Batch 5.2 — Intercepting Step Execution](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/intercepting-execution.html)
- [Spring Batch 5.2 — Configuring a Step](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing.html)
- [Spring Batch 5.2 — Unit Testing](https://docs.spring.io/spring-batch/reference/5.2/testing.html)
- [Spring Batch 5.2 — JobExecutionListener API](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/JobExecutionListener.html)
- [Spring Batch 5.2 — StepExecutionListener API](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/StepExecutionListener.html)
- [Spring Batch 5.2 — ChunkListener API](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/ChunkListener.html)
- [Spring Batch 6 — Micrometer Support](https://docs.spring.io/spring-batch/reference/spring-batch-observability/micrometer.html)
- [Spring Batch 6 — Unit Testing](https://docs.spring.io/spring-batch/reference/testing.html)
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Micrometer — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html)
- [Prometheus — Querying Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/)

