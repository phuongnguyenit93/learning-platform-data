# JobExplorer: Reading Metadata in Spring Batch

## 1. Lesson Objectives

When running batch jobs in real-world environments, operators need to know **which jobs ran, which runs failed, how many records each step processed, whether a job is currently running, and how many times a job has been restarted**. That information does not live in the business `Job` configuration object; it lives in **execution metadata** stored and managed by Spring Batch.

`JobExplorer` is the API dedicated to **reading metadata** for `JobInstance`s, `JobExecution`s, and `StepExecution`s. Within the *Execution control* topic of *Spring Batch Core Processing*, understanding `JobExplorer` is the foundation for building batch run-history views, status-check APIs, troubleshooting tools, and monitoring logic.

After this lesson, you will be able to:

- Distinguish `Job`, `JobInstance`, `JobExecution`, `StepExecution`, and `ExecutionContext`.
- Query metadata using the commonly used methods on `JobExplorer`.
- Retrieve execution lists by job name, inspect an individual execution, and read per-step processing counters.
- Paginate history, inspect running status, spot stale metadata, and handle missing IDs.
- Use `JobExplorer` in Spring Boot, build read-only services/REST endpoints, and test against a real repository.
- Understand the boundary between **reading metadata** and **controlling jobs** so you pick the right API.

**Version baseline for code examples:** Java 17+, Spring Boot 3.x, and Spring Batch 5.2.x. In Spring Batch 6.x, several metadata packages and APIs changed; the final section notes what to check when upgrading.

---

## 2. Distinguishing Job, JobInstance, JobExecution, and StepExecution

Before calling `JobExplorer`, you need to understand the nature of each metadata object.

| Concept | Meaning | Example |
|---|---|---|
| `Job` | Batch process definition, consisting of steps and execution flow | `dailyInvoiceJob` |
| `JobParameters` | Parameters for a job launch request; parameters can be marked identifying or non-identifying | `businessDate=2026-11-16`, `inputFile=...` |
| `JobInstance` | A **logical identity** of a job, determined by job name and **identifying JobParameters** | `dailyInvoiceJob` for business date `2026-11-16` |
| `JobExecution` | A specific execution attempt of a `JobInstance` | First run fails; subsequent restart succeeds |
| `StepExecution` | Execution record for one step inside a `JobExecution` | `invoiceStep` read 1,000 items, wrote 998 items |
| `ExecutionContext` | State data saved at job/step scope, typically used for resuming or sharing state | Read line position, pagination key, processing flags |
| `BatchStatus` | Technical status of the job/step | `STARTED`, `COMPLETED`, `FAILED` |
| `ExitStatus` | Outcome code describing termination conditions and driving flow navigation | `COMPLETED`, `FAILED`, or a custom code |

### Example of One JobInstance Having Multiple JobExecutions

Suppose `dailyInvoiceJob` processes `businessDate=2026-11-16`, and `businessDate` is an identifying parameter:

```text
Job: dailyInvoiceJob
│
├── JobInstance #42
│   Identifying parameters: businessDate=2026-11-16
│   │
│   ├── JobExecution #7001  → FAILED
│   │   ├── StepExecution #8001: readInvoices   → COMPLETED
│   │   └── StepExecution #8002: exportInvoices → FAILED
│   │
│   └── JobExecution #7002  → COMPLETED   (restart)
│       └── StepExecution #8003: exportInvoices → COMPLETED
│
└── JobInstance #43
    Identifying parameters: businessDate=2026-11-17
    │
    └── JobExecution #7003  → COMPLETED
        ├── StepExecution #8004: readInvoices   → COMPLETED
        └── StepExecution #8005: exportInvoices → COMPLETED
```

Key points to remember:

1. **One JobInstance can have multiple JobExecutions.** When an execution fails and is validly restarted, the system creates another `JobExecution` for the **same** `JobInstance`.
2. **Not all `JobParameters` identify a JobInstance.** Only identifying parameters participate in instance identity. Non-identifying parameters can still be stored with the run without creating a new logical identity.
3. **One JobExecution has multiple StepExecutions.** Not every step appears in every restart because already-completed steps can be skipped depending on configuration.
4. **JobExecution ID differs from JobInstance ID.** Do not confuse them when fetching details or passing IDs to operations tools.
5. `JobExplorer` reloads persisted objects; it does not return the live Java object currently active inside the processing thread.

The example above has three `JobExecution`s but only two `JobInstance`s. That is why instance counts, execution counts, and restart counts must be understood separately.

---

## 3. Where Is Metadata Stored?

With a JDBC `JobRepository` in Spring Batch 5.x, metadata usually lives in tables with the default prefix `BATCH_`.

| Table | Primary Contents |
|---|---|
| `BATCH_JOB_INSTANCE` | Instance ID, job name, instance identifying key |
| `BATCH_JOB_EXECUTION` | Execution ID, associated instance, status, start/end times, exit code |
| `BATCH_JOB_EXECUTION_PARAMS` | JobParameters attached to the execution |
| `BATCH_STEP_EXECUTION` | Status, timestamps, and read/write/skip/commit/rollback counters per step |
| `BATCH_JOB_EXECUTION_CONTEXT` | Serialized job-level ExecutionContext |
| `BATCH_STEP_EXECUTION_CONTEXT` | Serialized step-level ExecutionContext |
| ID sequence tables | Primary key generation depending on database and Spring Batch schema |

Logical relationships:

```text
BATCH_JOB_INSTANCE
      │ 1
      │
      ▼ N
BATCH_JOB_EXECUTION ─────────────── BATCH_JOB_EXECUTION_PARAMS
      │                  1 ─── N
      │ 1
      ├──────────────────────────── BATCH_JOB_EXECUTION_CONTEXT
      │
      ▼ N
BATCH_STEP_EXECUTION
      │ 1
      ▼ 1
BATCH_STEP_EXECUTION_CONTEXT
```

`JobRepository` writes/updates metadata during the job and step lifecycle. `JobExplorer` uses these structures to query history, even when the original runtime Java objects are no longer in memory.

**Do not query SQL directly for every history screen** when `JobExplorer` already provides the right API. The API spares the application from manually joining tables, decoding execution contexts, and tracking framework schema changes. However, dashboards requiring heavy aggregate queries may still opt for a dedicated analytics/metrics store if query load exceeds `JobExplorer`'s design.

### Metadata Is Not Business Data

A `StepExecution` recording `writeCount=998` only states that the step wrote 998 items as counted by Spring Batch; it does not prove 998 invoices were reconciled, issued, dispatched, or hold the right state in the target system. To confirm business outcomes, cross-check output tables/files or dedicated business logs.

---

## 4. How Does JobExplorer Differ from JobRepository, JobLauncher, and JobOperator?

| Component | Primary Responsibility | Operation Type |
|---|---|---|
| `JobExplorer` | Look up running or historical job/step executions | Read metadata |
| `JobRepository` | Create, persist, and update Spring Batch metadata | Write/manage underlying state |
| `JobLauncher` | Request running a `Job` with `JobParameters` | Launch |
| `JobOperator` | High-level operational API such as find, start, stop, restart depending on version | Control and monitoring |
| `JobRegistry` | Manage `Job` definitions registered in the application context | Look up job definitions |

Usage examples:

```java
// Read metadata (does not launch a job)
JobExecution execution = jobExplorer.getJobExecution(7001L);

// Launch a job: different operation, different API
JobExecution launched = jobLauncher.run(dailyInvoiceJob, parameters);

// Stop a job: requires JobOperator, not JobExplorer
boolean stopRequested = jobOperator.stop(7002L);
```

The `stop` call illustrates the Spring Batch 5.x admin API. Do not use it merely to "mark finished" a hung execution: a normal stop request requires a live batch process to respond.

**Crucial boundary:** `JobExplorer` does not restart, stop, modify `BatchStatus`, or persist `ExecutionContext` to the repository. If an application has an admin UI, you can build the **history viewing** portion with `JobExplorer`, while state-changing actions go through a separately authorized flow via `JobOperator` or an access-controlled orchestration service.

---

## 5. JobExplorer Metadata Reading APIs

In Spring Batch 5.2.x, the interface is:

```java
import org.springframework.batch.core.explore.JobExplorer;
```

Essential methods:

| Method | Return Type | Use Case |
|---|---|---|
| `getJobNames()` | `List<String>` | List of job names that have instances in the repository |
| `getJobInstanceCount(jobName)` | `long` | Total instances of a job for pagination |
| `getJobInstances(jobName, start, count)` | `List<JobInstance>` | List of instances, newest first, by offset |
| `findJobInstancesByJobName(jobName, start, count)` | `List<JobInstance>` | Search job names with LIKE/wildcard pattern |
| `getLastJobInstance(jobName)` | `JobInstance` or `null` | Latest instance by ID |
| `getJobInstance(instanceId)` | `JobInstance` or `null` | Look up an instance by ID |
| `getJobInstance(jobName, jobParameters)` | `JobInstance` or `null` | Look up an instance by name and identifying parameters |
| `getJobExecutions(jobInstance)` | `List<JobExecution>` | History of execution attempts for the same instance |
| `getLastJobExecution(jobInstance)` | `JobExecution` or `null` | Latest execution of an instance |
| `getJobExecution(executionId)` | `JobExecution` or `null` | Details of one run by execution ID |
| `getStepExecution(jobExecutionId, stepExecutionId)` | `StepExecution` or `null` | Step details and corresponding context |
| `findRunningJobExecutions(jobName)` | `Set<JobExecution>` | Executions recorded as running for a job |

Points to note:

- `start` in `getJobInstances` is a **0-based offset** and `count` is the page size, not an ID or page number.
- `getJobInstances` returns results ordered newest-first based on creation/ID order; that is **not synonymous** with the timestamp of each instance's latest execution.
- `getJobInstanceCount(jobName)` can throw `NoSuchJobException` if the job name has no instances yet; do not assume every name returns `0`.
- Lookup-by-ID methods generally return `null` when the ID is absent from the repository.
- `findRunningJobExecutions` returns a `Set`: order is not guaranteed, so sort it yourself before display.
- `getJobExecutions` may return step executions that are not fully hydrated, especially `ExecutionContext`. When you actually need a step's context, call `getStepExecution(jobExecutionId, stepExecutionId)`.
- `getJobExecution(executionId)` typically reconstructs the run's object graph including steps and contexts per the API contract, though persisted data may lag behind live in-memory objects while a job is actively running.

### Short Example: Listing Jobs That Have Run

```java
for (String jobName : jobExplorer.getJobNames()) {
    long instanceCount = jobExplorer.getJobInstanceCount(jobName);
    System.out.printf("%s: %d instances%n", jobName, instanceCount);
}
```

The list of job names comes from **persisted metadata**, which does not necessarily match the currently deployed `Job` beans. A job may exist in code without ever having run; conversely, DB history may contain job names removed from the current application version.

---

## 6. Configuring JobExplorer in Spring Boot

### 6.1. Declaring Dependencies

With Spring Boot 3.x + Spring Batch 5.2.x, example Gradle dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter-web'

    runtimeOnly 'org.postgresql:postgresql' // Example production DB
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}
```

`spring-boot-starter-web` is only needed for the REST API illustrated later. A batch worker launched via CLI/scheduler that only emits metrics may not need Spring MVC.

When Spring Batch infrastructure is properly configured, you can inject `JobExplorer` into beans like any other dependency:

```java
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.stereotype.Service;

@Service
public class BatchStatusReader {
    private final JobExplorer jobExplorer;

    public BatchStatusReader(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public long countInstances(String jobName)
            throws org.springframework.batch.core.launch.NoSuchJobException {
        return jobExplorer.getJobInstanceCount(jobName);
    }
}
```

You need a JDBC `JobRepository` pointing to a metadata database containing Spring Batch tables. If the database was just initialized, run schema initialization/migrations before querying history. If using multiple datasources, make sure `JobExplorer` **reads the exact same metadata store** used by `JobRepository` when executing jobs.

### 6.2. Example Datasource Configuration

A Spring Boot application using PostgreSQL can configure:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/batchdb
    username: batch_app
    password: ${BATCH_DB_PASSWORD}
  batch:
    job:
      enabled: false
```

In this snippet, `spring.batch.job.enabled=false` fits monitoring applications or setups where jobs are launched explicitly by a scheduler/API. Adjust database settings for your environment and real secret management. The `BATCH_*` tables must be created using the version-matched schema.

### 6.3. When You Must Create JobExplorer Manually

In manual Spring Batch configurations, you can use `JobExplorerFactoryBean`. Add this configuration only if existing infrastructure does not already provide the bean:

```java
import javax.sql.DataSource;

import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.explore.support.JobExplorerFactoryBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class ExplorerConfiguration {

    @Bean
    JobExplorer jobExplorer(DataSource batchDataSource) throws Exception {
        JobExplorerFactoryBean factory = new JobExplorerFactoryBean();
        factory.setDataSource(batchDataSource);
        factory.setTablePrefix("BATCH_");
        factory.afterPropertiesSet();
        return factory.getObject();
    }
}
```

`BATCH_` is just the default prefix in the example. If the repository uses `SYSTEM.BATCH_` or another prefix, the explorer must use the **same prefix**. In a Spring Boot app where `JobExplorer` is already auto-configured, do not create a second bean of the same name, as that causes configuration conflicts or datasource mismatches.

Some systems use a custom serializer for `ExecutionContext`: the explorer must use a serializer compatible with the repository to decode persisted contents accurately. Never change the serializer on only one side without a migration plan.

---

## 7. Complete Example: Service to Read Job Run History

This section builds a read-only Java API for an operations dashboard. Returned data is mapped into DTOs/records instead of serializing Spring Batch domain objects directly to JSON. This avoids circular object references, prevents leaking `ExecutionContext`, and controls exactly which fields appear in responses.

### 7.1. Display DTOs

Example package `com.example.batch.monitoring`:

```java
package com.example.batch.monitoring;

import java.time.LocalDateTime;
import java.util.List;
import org.springframework.batch.core.BatchStatus;

public final class BatchViews {
    private BatchViews() {}

    public record Page<T>(int page, int size, long total, List<T> items) {}

    public record InstanceView(
            long instanceId,
            String jobName,
            Long lastExecutionId,
            BatchStatus lastStatus,
            LocalDateTime lastStartTime) {}

    public record StepView(
            Long stepExecutionId,
            String stepName,
            BatchStatus status,
            String exitCode,
            long readCount,
            long writeCount,
            long filterCount,
            long readSkipCount,
            long processSkipCount,
            long writeSkipCount,
            long commitCount,
            long rollbackCount) {}

    public record ExecutionView(
            Long executionId,
            long instanceId,
            String jobName,
            BatchStatus status,
            String exitCode,
            LocalDateTime startTime,
            LocalDateTime endTime,
            List<StepView> steps) {}
}
```

Spring Batch 5.2 uses `LocalDateTime` for execution timestamps. This type **carries no offset/timezone**; the dashboard must standardize the infrastructure timezone and how timestamps are interpreted. Do not blindly slap `UTC` onto values not confirmed to be UTC.

### 7.2. Query Service

```java
package com.example.batch.monitoring;

import java.util.Comparator;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.Optional;

import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobInstance;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.launch.NoSuchJobException;
import org.springframework.stereotype.Service;

import com.example.batch.monitoring.BatchViews.ExecutionView;
import com.example.batch.monitoring.BatchViews.InstanceView;
import com.example.batch.monitoring.BatchViews.Page;
import com.example.batch.monitoring.BatchViews.StepView;

@Service
public class BatchHistoryService {

    private final JobExplorer explorer;

    public BatchHistoryService(JobExplorer explorer) {
        this.explorer = explorer;
    }

    public List<String> jobNames() {
        return explorer.getJobNames();
    }

    public Page<InstanceView> instances(String jobName, int page, int size) {
        if (jobName == null || jobName.isBlank()) {
            throw new IllegalArgumentException("jobName is required");
        }
        if (page < 0 || size < 1 || size > 100) {
            throw new IllegalArgumentException(
                    "page must be >= 0 and size must be 1..100");
        }

        long offset = (long) page * size;
        if (offset > Integer.MAX_VALUE) {
            throw new IllegalArgumentException("page offset too large");
        }

        long total;
        try {
            total = explorer.getJobInstanceCount(jobName);
        } catch (NoSuchJobException notFound) {
            return new Page<>(page, size, 0L, List.of());
        }

        List<InstanceView> items = explorer
                .getJobInstances(jobName, (int) offset, size)
                .stream()
                .map(this::toInstanceView)
                .toList();

        return new Page<>(page, size, total, items);
    }

    public Optional<ExecutionView> execution(long executionId) {
        if (executionId <= 0) {
            throw new IllegalArgumentException("executionId must be positive");
        }
        JobExecution execution = explorer.getJobExecution(executionId);
        if (execution == null) {
            return Optional.empty();
        }
        return Optional.of(toExecutionView(execution));
    }

    public List<ExecutionView> executionsOf(long instanceId) {
        JobInstance instance = explorer.getJobInstance(instanceId);
        if (instance == null) {
            throw new NoSuchElementException(
                    "JobInstance does not exist: " + instanceId);
        }

        return explorer.getJobExecutions(instance).stream()
                .sorted(Comparator.comparing(
                        JobExecution::getId,
                        Comparator.nullsLast(Comparator.reverseOrder())))
                .map(this::toExecutionView)
                .toList();
    }

    private InstanceView toInstanceView(JobInstance instance) {
        JobExecution last = explorer.getLastJobExecution(instance);
        return new InstanceView(
                instance.getInstanceId(),
                instance.getJobName(),
                last == null ? null : last.getId(),
                last == null ? null : last.getStatus(),
                last == null ? null : last.getStartTime());
    }

    private ExecutionView toExecutionView(JobExecution execution) {
        List<StepView> steps = execution.getStepExecutions().stream()
                .sorted(Comparator.comparing(
                        StepExecution::getId,
                        Comparator.nullsLast(Comparator.naturalOrder())))
                .map(this::toStepView)
                .toList();

        return new ExecutionView(
                execution.getId(),
                execution.getJobInstance().getInstanceId(),
                execution.getJobInstance().getJobName(),
                execution.getStatus(),
                execution.getExitStatus().getExitCode(),
                execution.getStartTime(),
                execution.getEndTime(),
                steps);
    }

    private StepView toStepView(StepExecution step) {
        return new StepView(
                step.getId(),
                step.getStepName(),
                step.getStatus(),
                step.getExitStatus().getExitCode(),
                step.getReadCount(),
                step.getWriteCount(),
                step.getFilterCount(),
                step.getReadSkipCount(),
                step.getProcessSkipCount(),
                step.getWriteSkipCount(),
                step.getCommitCount(),
                step.getRollbackCount());
    }
}
```

Explanation of key design choices:

- `getJobNames()` retrieves job names that actually have metadata in the repository.
- `getJobInstanceCount()` counts **instances**, not the individual `JobExecution`s of each instance.
- Each page fetches at most 100 instances; the offset uses `long` arithmetic before casting to `int` after bounds checking.
- `NoSuchJobException` is mapped to an empty page as an interface choice in this example; another app might return HTTP 404.
- `getLastJobExecution(instance)` is called per instance, creating an N+1 query pattern at the list layer. For small pages this is acceptable; for high-traffic dashboards, consider caching, summary tables, or dedicated queries.
- `getJobExecutions(instance)` returns execution attempts for the **same instance**, useful for identifying restarts.
- `getJobExecution(executionId)` returns `null` when the ID does not exist. `Optional.empty()` cleanly represents a not-found result.
- This service reads counters from metadata; it does not open input resources, run processors, or update progress.
- `ExecutionContext` and raw exception traces are deliberately kept out of the DTO because they can contain internal paths, resource names, transaction info, or sensitive data.

**Consistency observation:** a page assembled from multiple queries (count, list, last execution) can observe different states if a job starts or finishes mid-read. That is normal behavior in concurrent systems; totals and item states can momentarily diverge.

### 7.3. Read-Only REST Endpoint

```java
package com.example.batch.monitoring;

import java.util.List;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import com.example.batch.monitoring.BatchViews.ExecutionView;
import com.example.batch.monitoring.BatchViews.InstanceView;
import com.example.batch.monitoring.BatchViews.Page;

@RestController
@RequestMapping("/internal/batch")
public class BatchHistoryController {

    private final BatchHistoryService service;

    public BatchHistoryController(BatchHistoryService service) {
        this.service = service;
    }

    @GetMapping("/jobs")
    public List<String> jobs() {
        return service.jobNames();
    }

    @GetMapping("/jobs/{jobName}/instances")
    public Page<InstanceView> instances(
            @PathVariable String jobName,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        return service.instances(jobName, page, size);
    }

    @GetMapping("/executions/{executionId}")
    public ResponseEntity<ExecutionView> execution(
            @PathVariable long executionId) {
        return service.execution(executionId)
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
```

Example requests:

```http
GET /internal/batch/jobs
GET /internal/batch/jobs/dailyInvoiceJob/instances?page=0&size=20
GET /internal/batch/executions/7002
```

Illustrative response from the execution endpoint:

```json
{
  "executionId": 7002,
  "instanceId": 42,
  "jobName": "dailyInvoiceJob",
  "status": "COMPLETED",
  "exitCode": "COMPLETED",
  "startTime": "2026-11-16T02:00:00",
  "endTime": "2026-11-16T02:01:12",
  "steps": [
    {
      "stepExecutionId": 8003,
      "stepName": "exportInvoices",
      "status": "COMPLETED",
      "exitCode": "COMPLETED",
      "readCount": 1000,
      "writeCount": 998,
      "filterCount": 2,
      "readSkipCount": 0,
      "processSkipCount": 0,
      "writeSkipCount": 0,
      "commitCount": 6,
      "rollbackCount": 0
    }
  ]
}
```

This is **example data**, not live output from a repository. Timestamps omit timezone info, so clients must apply the system convention before converting to local time.

The REST example omits authentication, authorization, exception handlers, and CORS configuration. In a real operations app, restrict this endpoint to authorized readers; never publicly expose paths, JobParameters, or `ExecutionContext`.

---

## 8. Querying Metadata Directly for Operational Scenarios

### 8.1. Finding Run History of a Job

```java
String name = "dailyInvoiceJob";
int offset = 0;
int pageSize = 10;

List<JobInstance> instances =
        jobExplorer.getJobInstances(name, offset, pageSize);

for (JobInstance instance : instances) {
    System.out.println("instance=" + instance.getInstanceId());

    for (JobExecution execution :
            jobExplorer.getJobExecutions(instance)) {
        System.out.println(
                "  execution=" + execution.getId()
                + " status=" + execution.getStatus());
    }
}
```

This traverses **instances first, then executions**. If an instance was restarted several times, multiple executions sit under that same instance.

Do not call `getJobInstances(name, 0, 1)` and assume the result holds the **latest JobExecution across the entire system** in every situation. An older instance may just have been restarted and hold a newer execution than a newly created instance. To find the "most recent by execution time" across the whole job, inspect executions across relevant instances or use an appropriate summary query.

### 8.2. Looking Up Execution Details by ID

```java
JobExecution execution = jobExplorer.getJobExecution(7002L);

if (execution == null) {
    System.out.println("No execution found");
} else {
    System.out.println("Status: " + execution.getStatus());
    System.out.println("Exit code: "
            + execution.getExitStatus().getExitCode());
    System.out.println("Start: " + execution.getStartTime());
    System.out.println("End: " + execution.getEndTime());

    for (StepExecution step : execution.getStepExecutions()) {
        System.out.printf(
                "%s: read=%d, write=%d, skip=%d%n",
                step.getStepName(),
                step.getReadCount(),
                step.getWriteCount(),
                step.getSkipCount());
    }
}
```

Note that `getStepCount` or `getReadCount` are not methods on `JobExecution`; item counters live on `StepExecution`. If a job has multiple steps, decide **how to aggregate** based on business semantics. For instance, if two steps sequentially read the same set of records, summing both `readCount` values would double-count every record.

### 8.3. Reading Details of a Specific StepExecution

```java
Long jobExecutionId = 7002L;
Long stepExecutionId = 8003L;

StepExecution step = jobExplorer.getStepExecution(
        jobExecutionId,
        stepExecutionId);

if (step != null) {
    System.out.println(step.getStepName());
    System.out.println(step.getStatus());
    System.out.println(step.getExecutionContext());
}
```

Pass **both jobExecutionId and stepExecutionId** to retrieve the right step. To display field names, item counts, and timestamps, call the corresponding getters. Avoid printing the entire `ExecutionContext` into production logs: it may leak secrets or sensitive operational data.

### 8.4. Finding Jobs Recorded as Running

```java
Set<JobExecution> running =
        jobExplorer.findRunningJobExecutions("dailyInvoiceJob");

List<JobExecution> ordered = running.stream()
        .sorted(Comparator.comparing(
                JobExecution::getId,
                Comparator.nullsLast(Comparator.reverseOrder())))
        .toList();

for (JobExecution execution : ordered) {
    System.out.printf("running execution=%d, status=%s%n",
            execution.getId(), execution.getStatus());
}
```

Additional imports:

```java
import java.util.Comparator;
import java.util.List;
import java.util.Set;
import org.springframework.batch.core.JobExecution;
```

**"Running" here is the metadata state recorded by the repository, not a guaranteed JVM heartbeat.** If a server shuts down abruptly, an execution can remain `STARTED` even though no processing thread exists. Combine this with process monitoring, `lastUpdated`, logs, or metrics to verify it is truly still running.

### 8.5. Distinguishing Technical Status from Flow Outcomes

```java
BatchStatus batchStatus = execution.getStatus();
String exitCode = execution.getExitStatus().getExitCode();
String exitDescription =
        execution.getExitStatus().getExitDescription();
```

`BatchStatus` serves the technical lifecycle; `ExitStatus` is the outcome a step/job can customize, often used by job flows to determine the next branch.

For example, a technically completed step can return a custom `ExitStatus` like `COMPLETED_WITH_WARNINGS`. Operations dashboards should display both rather than inferring that `BatchStatus.COMPLETED` always means "zero business warnings."

---

## 9. Reading ExecutionContext Properly

`ExecutionContext` is a map of key/value pairs persisted at job/step scope to support checkpoints, restarts, or sharing data between steps.

| Scope | Retrieved From | Typical Data |
|---|---|---|
| Job execution context | `jobExecution.getExecutionContext()` | Total processed record count, aggregate keys, data shared across steps |
| Step execution context | `stepExecution.getExecutionContext()` | Reader position, writer state, pagination offsets |

Controlled key lookup example:

```java
JobExecution execution = jobExplorer.getJobExecution(7002L);
if (execution != null) {
    ExecutionContext context = execution.getExecutionContext();

    if (context.containsKey("processedBusinessDate")) {
        String value = context.getString("processedBusinessDate");
        System.out.println(value);
    }
}
```

Import:

```java
import org.springframework.batch.item.ExecutionContext;
```

Do not assume every key exists, or that every value is a `String`. `ExecutionContext` can hold objects deserialized by the configured serializer, and reading with the wrong type can throw an exception.

### Why Might a Second getStepExecution Call Be Needed?

The `JobExplorer.getJobExecutions(JobInstance)` Javadoc notes that attached `StepExecution`s **may not be fully hydrated**. In particular, step execution contexts may be missing in nested objects depending on the implementation.

When you need the checkpoint for diagnostics:

```java
JobExecution jobExecution = jobExplorer.getJobExecution(7002L);
if (jobExecution != null) {
    for (StepExecution summary : jobExecution.getStepExecutions()) {
        StepExecution detailed = jobExplorer.getStepExecution(
                jobExecution.getId(), summary.getId());

        if (detailed != null) {
            ExecutionContext checkpoint = detailed.getExecutionContext();
            // Only read keys approved for display.
        }
    }
}
```

Querying a specific step by ID is clearer than trying to pull data from a partially hydrated object graph inside a list query. Do not mutate `checkpoint` expecting it to persist automatically: `JobExplorer` is for **reading** metadata, not committing new state.

### When Should ExecutionContext Not Be Exposed?

Never return the raw context in a public REST API. A context can contain bucket names, internal file paths, tokens accidentally stored by application code, business IDs, or Java class structures. If support staff need diagnostics, design an allowlisted DTO and mask sensitive values.

---

## 10. JobExecution Statuses to Understand When Inspecting Metadata

| BatchStatus | Common Operational Meaning |
|---|---|
| `STARTING` | Framework has begun launch procedures |
| `STARTED` | Execution is recorded as actively running |
| `STOPPING` | Stop requested, waiting for job/step response |
| `STOPPED` | Execution stopped via stop mechanism |
| `COMPLETED` | Execution completed from the batch framework's standpoint |
| `FAILED` | Execution failed |
| `ABANDONED` | Marked abandoned/not to be resumed under batch controls |
| `UNKNOWN` | Unable to determine reliable status in certain cases |

Do not turn the table above into a rule to blindly restart every job with `FAILED` or `STOPPED`. Restartability also depends on job configuration, step statuses, committed data, and the safety of business operations.

### Relationship Between Status and Timestamps

- `getCreateTime()`: when the execution record was created.
- `getStartTime()`: when the job actually started; may be absent initially.
- `getEndTime()`: when it ended; typically `null` if it has not terminated normally.
- `getLastUpdated()`: latest metadata update timestamp recorded by the repository.

`endTime == null` does not always prove the job is still running; the process may have crashed or metadata updates may have stopped mid-flight. In multi-host setups, also check the scheduler, container/VM health, and logs.

---

## 11. Practical Applications: Lookup, Alerting, and Restart

### 11.1. History Dashboard

A UI can use two tiers:

1. **Instance list**: `jobName`, `instanceId`, identifying business key, latest execution status.
2. **Instance/execution detail page**: list of execution attempts, steps, counters, errors, and timestamps.

This layout avoids presenting each `JobExecution` as a "brand-new job" and lets operators clearly see restarts.

### 11.2. Finding Failed Executions

`JobExplorer` in Spring Batch 5.2 does not provide a single global method to "fetch all FAILED executions across the entire repository by date." A simple application-level approach is paging through instances and filtering executions:

```java
List<JobInstance> instances =
        jobExplorer.getJobInstances("dailyInvoiceJob", 0, 100);

List<JobExecution> failed = instances.stream()
        .flatMap(instance ->
                jobExplorer.getJobExecutions(instance).stream())
        .filter(execution ->
                execution.getStatus() == BatchStatus.FAILED)
        .toList();
```

This searches only the **first 100 instances**, not the entire history. When global filtering by date/status is needed over large datasets, build a dedicated query/report read model against the metadata database with proper indexes or a metrics pipeline to avoid scanning the repository on every request.

### 11.3. Alerting on "Job Running Too Long"

An operational heuristic can inspect:

- `BatchStatus.STARTED`.
- `getStartTime()` older than that job's expected threshold.
- `getLastUpdated()` no longer advancing.
- Process/scheduler checks confirming whether work is still alive or gone.

Relying solely on `STARTED` can misclassify a job killed by the OS as "running for a very long time." Alert heuristics are **signals to investigate**, not grounds to automatically mutate status or restart without assessing data impact.

### 11.4. Using Control APIs When Stop or Restart Is Needed

`JobExplorer` can retrieve exact IDs, status, and execution details to inform decisions. Once an action is confirmed safe and authorized, the operations layer can invoke `JobOperator`.

Ideal flow:

```text
Operator selects execution
           │
           ▼
JobExplorer reloads latest metadata
           │
           ▼
Verify status, history, policy, and permissions
           │
           ▼
JobOperator performs stop/restart (if appropriate)
           │
           ▼
JobExplorer re-queries to display result
```

Reading and acting happen at **two separate moments**; the execution could change state in between. The control layer must still handle conflicts rather than blindly trusting data just viewed on screen.

---

## 12. Pagination, Performance, and Consistency

### 12.1. Pagination Is a Design Requirement

In a repository with millions of job executions, calling `getJobInstances(name, 0, Integer.MAX_VALUE)` causes heavy load. Use bounded page sizes and reject unreasonable request values.

```java
int page = 3;       // fourth page, zero-indexed
int size = 25;
int start = Math.multiplyExact(page, size);

List<JobInstance> items =
        jobExplorer.getJobInstances("dailyInvoiceJob", start, size);
```

Enforce `page >= 0`, `size > 0`, and an upper bound on `size`; `Math.multiplyExact` throws if integer overflow occurs. `getJobInstances` only orders by instance query semantics and **does not provide a consistent snapshot** across multiple paginated requests while new data is being inserted.

### 12.2. The N+1 Query Problem

To display `lastStatus` for 100 instances, calling `getLastJobExecution(instance)` in a loop issues many queries. For moderate volume this may be fine; for dashboards opened by many users:

- Return only the fields actually needed on the list view.
- Reduce page size and use short-lived caching where staleness tolerance allows.
- Build a read model aggregating latest statuses when high SLAs are required.
- Restrict deep diagnostic endpoints so they do not load every context at once.

### 12.3. Data Source Consistency

A batch system running on cluster A and a dashboard hosted on service B only see matching metadata if both read the same repository or a synchronized replica. If the dashboard reads a read replica, **replication lag** can appear: a job already finished on primary while the UI still shows `STARTED` for a short window.

### 12.4. Metadata Retention

Some systems periodically purge old metadata to keep the DB small. When that happens, `getJobInstance(...)` or `getJobExecution(...)` may not find historical records even though the batch ran in the past. If long-term auditing is required, establish an archive/reporting policy instead of relying indefinitely on operational tables.

---

## 13. Testing Metadata-Reading Code

There are two distinct testing layers.

### 13.1. Unit Testing Services with a Mocked JobExplorer

Unit tests are ideal for verifying how a service handles missing IDs, pagination, and validation errors. Example with Mockito (included in `spring-boot-starter-test`):

```java
package com.example.batch.monitoring;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.explore.JobExplorer;
import java.util.List;

class BatchHistoryServiceTest {

    private final JobExplorer explorer = mock(JobExplorer.class);
    private final BatchHistoryService service =
            new BatchHistoryService(explorer);

    @Test
    void missingExecutionReturnsEmpty() {
        when(explorer.getJobExecution(999L)).thenReturn(null);

        assertTrue(service.execution(999L).isEmpty());
        verify(explorer).getJobExecution(999L);
    }

    @Test
    void emptyInstancePageWhenNoJobWasExecuted() throws Exception {
        when(explorer.getJobInstanceCount("neverRunJob"))
                .thenThrow(new org.springframework.batch.core.launch
                        .NoSuchJobException("neverRunJob"));

        var result = service.instances("neverRunJob", 0, 20);

        assertEquals(0L, result.total());
        assertEquals(List.of(), result.items());
        verify(explorer, never())
                .getJobInstances(anyString(), anyInt(), anyInt());
    }

    @Test
    void rejectsOversizedPage() {
        assertThrows(IllegalArgumentException.class,
                () -> service.instances("dailyInvoiceJob", 0, 1000));
    }
}
```

This unit test verifies service-layer rules, **not** that database queries and instance–execution relationships actually work. That requires integration tests.

### 13.2. Integration Testing with a Real JobRepository

The idea is to run a test job with a simple step, then use `JobExplorer` to reload metadata by the generated ID. The following is an integration test skeleton; it requires `BatchTestApplication` and `sampleJob` configured in your project.

```java
@SpringBatchTest
@SpringBootTest(
    classes = BatchTestApplication.class,
    properties = {
        "spring.batch.job.enabled=false",
        "spring.batch.jdbc.initialize-schema=always"
    }
)
class JobExplorerIntegrationTest {

    @Autowired
    JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    JobExplorer jobExplorer;

    @Test
    void canReadMetadataOfCompletedExecution() throws Exception {
        JobParameters params = new JobParametersBuilder()
                .addString("testRunId", UUID.randomUUID().toString())
                .toJobParameters();

        JobExecution launched = jobLauncherTestUtils.launchJob(params);
        assertEquals(BatchStatus.COMPLETED, launched.getStatus());

        JobExecution stored =
                jobExplorer.getJobExecution(launched.getId());

        assertNotNull(stored);
        assertEquals(launched.getId(), stored.getId());
        assertEquals(BatchStatus.COMPLETED, stored.getStatus());
        assertNotNull(stored.getJobInstance());
        assertFalse(stored.getStepExecutions().isEmpty());

        for (StepExecution step : stored.getStepExecutions()) {
            StepExecution hydrated = jobExplorer.getStepExecution(
                    stored.getId(), step.getId());
            assertNotNull(hydrated);
            assertEquals(step.getStepName(), hydrated.getStepName());
        }
    }
}
```

Typical imports:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
```

If the application context has multiple `Job`s, configure `JobLauncherTestUtils` to select the target job; if tests use H2, include the H2 dependency and schema initialization. For multi-step jobs, assertions should reflect the steps actually expected to execute.

### 13.3. Recommended Test Cases

| Scenario | Assertion |
|---|---|
| Job has never run | `getJobNames()` does not include it; depending on API `getJobInstanceCount` may throw `NoSuchJobException` |
| Successful job run | Instance exists, execution exists, status and steps are accurate |
| Restart of a failed job | Same JobInstance ID, an additional distinct JobExecution ID |
| Two different identifying business dates | Two distinct JobInstances |
| Non-identifying parameter changes | Does not create a new instance solely from that parameter |
| Non-existent execution ID lookup | `getJobExecution(id) == null` |
| Reading step details | ID and step metadata match parent execution |
| Running job | `findRunningJobExecutions` reflects metadata at query time |
| Multiple executions for one instance | History returns all runs; failed and completed can be distinguished |
| Database missing schema / wrong datasource | Integration test fails loudly rather than silently returning empty |

**Important:** you do not need to simulate a real restart in every unit test. Scenarios depending on transactions and metadata are much more valuable in isolated integration tests.

---

## 14. Common Issues When Using JobExplorer

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `NoSuchJobException` when counting instances | Job name has never created an instance in the repository | Decide UI behavior: return 404 or an empty page |
| `getJobExecution(id)` returns `null` | Wrong ID, metadata was purged, or not in this datasource | Check execution ID, DB, and retention policy |
| Empty job list despite job beans in code | Job has never run, or explorer reads the wrong repository | Run a test job and verify datasource |
| Job finished yet UI shows `STARTED` | Stale metadata, replica lag, killed JVM, or cached page | Check primary DB, `lastUpdated`, processes, and logs |
| Step counters appear missing | Reading wrong step or insufficiently hydrated object | Call `getStepExecution(jobExecutionId, stepExecutionId)` |
| Error that `BATCH_JOB_INSTANCE` table does not exist | Schema not initialized or wrong table prefix | Verify schema and repository/explorer configuration |
| Cannot deserialize `ExecutionContext` | Serializer, configuration, or data type changed | Align serializer and metadata migration plan |
| Slow dashboard | Fetching too many instances, N+1 lookups, or scanning full history | Paginate, limit fields, optimize read model |
| Status `COMPLETED` but output is wrong | Metadata records technical completion, not business validation | Verify output files, business DB, checksums, and reconciliation |
| Two services report different statuses | Different datasources/schemas, replica lag, or caching | Standardize on one metadata source and freshness rules |
| Old job names still appear in list | Historical metadata persists, does not reflect deployed beans | Distinguish JobRegistry from JobExplorer |
| Cannot restart despite previous `FAILED` execution | Non-restartable job, unsafe data, or status already changed | Check restart policy and use appropriate control APIs |

### A Short Diagnostic Flow

```text
Cannot see expected job/execution
    │
    ├─ Verify job name and execution ID
    │
    ▼
Right datasource, schema, tablePrefix?
    │
    ├─ No → fix metadata store configuration
    │
    ▼
Metadata exists in BATCH_*?
    │
    ├─ No → check whether job ran / retention / migration
    │
    ▼
Querying at the right API level?
    │
    ├─ Wrong → JobInstance vs JobExecution vs StepExecution
    │
    ▼
Is status stale?
    │
    └─ Check lastUpdated, scheduler, process, logs, replica lag
```

---

## 15. Designing Permissions and Operational Data

Even though `JobExplorer` is a read-only API, metadata can expose internal details:

- `JobParameters` may reveal file paths, partner identifiers, bucket names, or operational parameters.
- `ExecutionContext` may contain checkpoints, business keys, or custom application data.
- `ExitDescription` and exceptions sometimes contain stack traces or failing record payloads.
- The list of job names may reveal sensitive organizational workflows.

Restrict APIs to required operational roles, return allowlisted DTOs, never expose raw `ExecutionContext`, and audit sensitive lookups if internal compliance requires it.

Reading metadata also consumes database resources. Aggressive dashboard polling can impact the database serving live batch jobs; set reasonable refresh intervals and monitor query load.

---

## 16. Practice Exercises

### Exercise 1 — Listing JobInstances

Write a service accepting `jobName`, `page`, and `size` that returns `instanceId`, job name, and `lastStatus`. Test `page=0`, `page=1`, a job that has never run, and sizes exceeding the limit.

### Exercise 2 — Restart History

Create a job that fails on its first run and succeeds on restart. Use `JobExplorer` to prove:

1. `getJobInstances(jobName, ...)` contains exactly one instance for that set of identifying parameters.
2. `getJobExecutions(instance)` contains at least two executions with distinct IDs.
3. The first execution's status is `FAILED` and the subsequent one's is `COMPLETED`.
4. Steps can execute differently according to restart policy.

### Exercise 3 — StepExecution Details

Given `jobExecutionId` and `stepExecutionId`, build an endpoint returning step name, `readCount`, `writeCount`, `skipCount`, `commitCount`, and status. Handle missing IDs with HTTP 404.

### Exercise 4 — Running Status Dashboard

Simulate a long-running job. Call `findRunningJobExecutions(jobName)` while running, after completion, and after an abrupt process stop. Explain why metadata query results alone do not prove the JVM is still alive.

### Exercise 5 — Performance Evaluation

Populate a test repository with tens of thousands of instances. Measure query counts of a list page calling `getLastJobExecution` per instance; experiment with bounding page size and caching aggregated results, then compare cost vs. data staleness.

### Exercise 6 — Avoiding Sensitive Data Leaks

Create an `ExecutionContext` with internal business keys. Write a DTO returning only allowlisted fields. Verify the REST API never directly serializes `ExecutionContext`, `JobParameters`, or exception stack traces.

---

## 17. Upgrade Notes for Spring Batch 6.x

The main examples here follow **Spring Batch 5.2.x**. In Spring Batch 6.x, package layouts and several repository/explorer APIs changed; for instance, Spring Batch 6 Javadoc places `JobExplorer` under `org.springframework.batch.core.repository.explore` and alters the relationship between `JobRepository` and `JobExplorer`.

Therefore, when upgrading:

1. Pick compatible Spring Boot/Spring Batch versions together; do not mix Spring Batch 6.x libraries into a Boot 3.x app built for Spring Batch 5.x.
2. Check version-specific Javadoc for `JobExplorer`, `JobRepository`, `JobExecution`, `StepExecution`, and types used in DTOs.
3. Review `@Deprecated` APIs, package imports, and metadata repository SQL migrations.
4. Verify `ExecutionContext` serializer compatibility and reading historical metadata post-upgrade.
5. Re-run integration tests that read persisted metadata and test restart scenarios.

The core principles remain unchanged: know whether you are querying an **instance**, an **execution**, or a **step execution**, and never turn metadata reading into uncontrolled job manipulation.

---

## 18. References

- [Spring Batch 5.2 — Advanced Metadata Usage](https://docs.spring.io/spring-batch/reference/5.2/job/advanced-meta-data.html): `JobExplorer`, `JobOperator`, and repository queries.
- [JobExplorer API — Spring Batch 5.2.2](https://docs.spring.io/spring-batch/docs/5.2.2/api/org/springframework/batch/core/explore/JobExplorer.html): method signatures, pagination, running executions, and `null` behavior.
- [Spring Batch 5.2 — Domain Language](https://docs.spring.io/spring-batch/reference/5.2/domain.html): relationships among `JobInstance`, `JobExecution`, and `StepExecution`.
- [Spring Batch 5.2 — Configuring a JobRepository](https://docs.spring.io/spring-batch/reference/5.2/job/configuring-repository.html): datasource, transaction, and table prefix configuration.
- [Spring Batch 5.2 — Metadata Schema](https://docs.spring.io/spring-batch/reference/5.2/schema-appendix.html): metadata table details.
- [JobExplorer API — Spring Batch 6.x](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/repository/explore/JobExplorer.html): check APIs when using the newer version.

`JobExplorer` turns Spring Batch metadata into actionable insight for humans and monitoring systems. A solid design accurately distinguishes identity levels, presents statuses and counters in proper context, paginates cleanly, and always remembers that repository history is a **record of execution state** that must be cross-checked with business data and operational signals when making decisions.
