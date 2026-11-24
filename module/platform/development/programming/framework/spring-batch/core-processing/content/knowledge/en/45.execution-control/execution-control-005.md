# Operator Restarting a Failed Job in Spring Batch

## 1. The Problem: A Job Is `FAILED`, How Do You Resume the Exact Previous Run?

In a batch system, a run can fail due to a lost database connection, an unready input file, an overloaded external API, a temporary authentication error, or data failing validation. After fixing the root cause, operators must decide whether to **resume the exact failed unit of work** or **start a brand-new processing batch**.

Spring Batch provides the **`JobOperator`** interface to observe and control jobs from an entry point usable inside the application, admin commands, or operations systems. In Spring Batch 5.x, the central operation for this lesson is:

```java
Long newExecutionId = jobOperator.restart(failedExecutionId);
```

This method asks the framework to **restart a `JobExecution` that is in a failed or stopped state**. Spring Batch looks up persisted metadata, identifies the associated `JobInstance`, checks restart preconditions, and creates a new `JobExecution` for the **same `JobInstance`**. Previously completed steps are normally skipped; incomplete steps can use the saved `ExecutionContext` to resume according to the step's policy.

> **Core distinction:** `restart` is not "re-running everything from scratch." It is resuming a `JobInstance` based on existing execution history and metadata. To start an independent batch run, you need a new `JobInstance` with different identifying `JobParameters`.

After this lesson, you will be able to:

- Explain the relationships among `JobInstance`, `JobExecution`, `StepExecution`, and parameters during a restart.
- Use `JobOperator.restart(long executionId)` in Spring Batch 5.x with proper preconditions and error handling.
- Identify which statuses can be restarted and which must be resolved first.
- Verify skipping `COMPLETED` steps, restoring checkpoints for failed steps, and preserving business data integrity.
- Write integration tests for restarts via `JobOperator` with a real metadata repository.
- Design observable operational workflows that avoid duplicate launches and limit impact when a job did partial work.
- Recognize API differences in Spring Batch 6.x.

The Java examples use **Java 17+, Spring Boot 3.x, and Spring Batch 5.x**. When using Spring Batch 6.x, update the restart API as noted at the end of the lesson.

---

## 2. How the Metadata Model Governs Restart Behavior

### 2.1. `JobInstance` Is a Logical Processing Batch

A `JobInstance` is identified by the **job name** combined with the set of **identifying job parameters**.

Example:

```text
Job name:       invoiceImportJob
businessDate:   2026-11-16  (identifying)
tenantId:       company-A   (identifying)
traceId:        trace-7391 (non-identifying)

=> JobInstance #41
```

If the run for `JobInstance #41` fails, we can create another `JobExecution` to continue processing that exact business date and tenant. A run with different identifying parameters normally corresponds to a new `JobInstance`.

**`JobExecution` is not `JobInstance`.** Each execution/restart attempt is recorded as its own execution:

```text
JobInstance #41: invoiceImportJob + businessDate + tenantId
    |
    +-- JobExecution #810 (FAILED)
    |      |
    |      +-- StepExecution prepareStep  (COMPLETED)
    |      +-- StepExecution importStep   (FAILED)
    |
    +-- JobExecution #811 (COMPLETED, after restart)
           |
           +-- prepareStep: normally skipped
           +-- StepExecution importStep   (COMPLETED)
```

Here, the **`JobInstance` remains the same**, a **new `JobExecution` is created**, and Spring Batch relies on step statuses stored in the repository to decide what runs next.

### 2.2. Participating Components

| Component | Role in Restart |
| --- | --- |
| `JobOperator` | Operational entry point: `restart`, `stop`, `getSummary`, `getRunningExecutions`, and other control actions |
| `JobRepository` | Persists job/step statuses, links instances and executions, manages persistence/checkpoints |
| `JobExplorer` | Reads metadata to inspect current executions and run history |
| `JobRegistry` / `JobLocator` | Helps the operator locate the `Job` definition by the name stored in metadata |
| `JobLauncher` | Used by infrastructure to launch the matching job |
| `ExecutionContext` | Stores restart state such as reader offsets, data pages, checkpoints, and step state |
| `ItemStream` | Restores state in `open()`, writes checkpoints in `update()` when registered with the step |

A restart requires that **the job definition is still available** and **metadata from the previous run is intact and compatible**. If every application restart uses a fresh in-memory repository, the job loses the history needed to resume after the old process dies.

### 2.3. Restart vs. Starting Fresh

| Operation | Input | `JobInstance` | `JobExecution` | Meaning |
| --- | --- | --- | --- | --- |
| `jobOperator.restart(failedExecutionId)` | Failed/stopped execution ID | Keeps the old instance | Creates a new execution | Resumes prior work from metadata |
| `jobLauncher.run(job, sameParameters)` | `Job` + old parameters | Can use same instance if restart is valid | Creates a new execution | Framework can restart, but caller must supply matching `Job`/parameters |
| `jobOperator.startNextInstance(jobName)` | Job name with incrementer | Creates a new instance | Creates a new execution | Runs the next batch with new parameters |
| `jobLauncher.run(job, newParameters)` | `Job` + different identifying parameters | Creates a new instance | Creates a new execution | Runs an independent unit of work |
| `jobOperator.stop(executionId)` | Running execution ID | Unchanged | Affects current execution | Sends a graceful stop request, not a restart |

For example, incrementing `run.id` or adding a new identifying timestamp and running the job is not a restart, because the new `JobInstance` will not automatically use the old instance's checkpoint.

---

## 3. Which Statuses Allow Restart?

Spring Batch manages execution state via the `BatchStatus` enum. Operators must inspect the actual status in the **metadata repository**, because metadata can differ from a lagging dashboard or log view.

| `BatchStatus` | Operational Meaning | Action |
| --- | --- | --- |
| `FAILED` | Execution failed | Restartable if the job allows it, metadata is valid, and no newer execution is running or already completed |
| `STOPPED` | Execution stopped cleanly | Restartable per flow/step policy |
| `COMPLETED` | Instance processed successfully | Do not restart; if a new batch is needed, create a new instance |
| `STARTING` / `STARTED` | Execution is starting/running | Do not restart; verify real process, wait for completion, or request stop |
| `STOPPING` | Stop requested, not finished yet | Wait for `STOPPED`; stop signal does not mean already stopped |
| `ABANDONED` | Execution marked abandoned/do not continue | Framework will not restart this execution |
| `UNKNOWN` | Unknown status or anomalous metadata | Investigate metadata and safety; do not auto-restart |

Important condition: if an older execution is `FAILED` but **the same instance has a later execution that is `COMPLETED`**, that instance cannot be restarted either. You must check the **history of the entire `JobInstance`**, not just one old row.

### 3.1. `BatchStatus` and `ExitStatus` Are Not the Same

`BatchStatus` represents the execution lifecycle; `ExitStatus` drives flow transitions and describes step/job exit outcomes. For instance, a flow with an `.end()` transition can finish the entire job as `COMPLETED` even if an earlier step took an error branch. Once the job is `COMPLETED`, operators must not treat it as a failed job eligible for restart.

In flows, distinguish:

- `.end()`: terminates the flow as completed; **cannot restart a completed instance**.
- `.fail()`: terminates the job as `FAILED`, allowing restart if the job is restartable.
- `.stopAndRestart(...)`: stops the flow and designates which step runs next upon restart per configuration.

Thus, a request like "the job logged a business error, please restart it" must be verified against **actual metadata** and flow semantics, not inferred from an "ERROR" log line.

### 3.2. Job Restartability

A job can be configured to disallow restarts:

```java
@Bean
Job singleRunJob(JobRepository jobRepository, Step exportStep) {
    return new JobBuilder("singleRunJob", jobRepository)
        .start(exportStep)
        .preventRestart()
        .build();
}
```

When a job is configured with `preventRestart()`, attempting to restart a prior instance is rejected, typically with `JobRestartException`. This may fit jobs with irreversible side effects, but if business requirements call for resuming after failure, design checkpoints and idempotency so restarts are safe.

### 3.3. Step-Level `startLimit` and `allowStartIfComplete`

A step can limit how many times it may run:

```java
Step importStep = new StepBuilder("importStep", jobRepository)
    .tasklet(importTasklet, transactionManager)
    .startLimit(3)
    .build();
```

If `startLimit` is reached, a restart can fail when that step needs to run again.

By default, a step that already reached `COMPLETED` in the same instance is skipped on restart. For a step that must re-run even after completing, configure:

```java
Step checkInputStep = new StepBuilder("checkInputStep", jobRepository)
    .tasklet(checkInputTasklet, transactionManager)
    .allowStartIfComplete(true)
    .build();
```

Do not enable this option out of habit; re-running a completed step can duplicate side effects such as sending emails, writing files, emitting events, or transferring funds.

---

## 4. The `JobOperator.restart` API in Spring Batch 5.x

### 4.1. Core Method

```java
import org.springframework.batch.core.launch.JobOperator;

Long restartedExecutionId =
    jobOperator.restart(failedExecutionId);
```

**Parameter:** the ID of the **old `JobExecution`**, not `JobInstance ID`, not step ID, and not job name. For example, if the metadata table has `JOB_EXECUTION_ID = 810`, pass `810L`.

**Return value:** the ID of the **newly launched `JobExecution`**; for example `811L`. Not the retry count, `COMPLETED` status, or instance ID.

The method uses the old execution's metadata to look up the job, parameters, and execution history. The caller does not need to manually reassemble identifying parameters for a normal restart.

### 4.2. Why Not Assume the Job Already Finished?

`restart` returns the ID once the launch request has been processed. Depending on `JobLauncher` and `TaskExecutor`, the job may execute synchronously or asynchronously. In an async setup, when the operator returns the ID, the execution may still be `STARTING` or `STARTED`.

Therefore, control workflows should separate launch from completion:

```text
Send restart
    |
    v
Receive new JobExecution ID
    |
    v
Query JobExplorer/JobRepository
    |
    +-- STARTING/STARTED/STOPPING --> continue monitoring
    |
    +-- COMPLETED ---------------> confirm success
    |
    +-- FAILED ------------------> collect new failure cause
    |
    +-- STOPPED -----------------> review stop request
```

Do not return a "job succeeded" message immediately upon receiving a valid ID.

### 4.3. Example Restart Control Service

The snippet below assumes Spring has configured a `JobOperator` and `JobExplorer` connected to the application's metadata repository:

```java
package example.batch.ops;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.launch.JobOperator;
import org.springframework.stereotype.Service;

@Service
public class BatchRestartService {

    private final JobOperator jobOperator;
    private final JobExplorer jobExplorer;

    public BatchRestartService(
            JobOperator jobOperator,
            JobExplorer jobExplorer) {
        this.jobOperator = jobOperator;
        this.jobExplorer = jobExplorer;
    }

    public long restartFailedOrStopped(long oldExecutionId)
            throws Exception {

        JobExecution previous =
            jobExplorer.getJobExecution(oldExecutionId);

        if (previous == null) {
            throw new IllegalArgumentException(
                "No JobExecution: " + oldExecutionId
            );
        }

        BatchStatus status = previous.getStatus();
        if (status != BatchStatus.FAILED &&
            status != BatchStatus.STOPPED) {
            throw new IllegalStateException(
                "JobExecution " + oldExecutionId
                    + " has status " + status
                    + " and cannot be restarted"
            );
        }

        // JobOperator/JobRepository further validate conditions
        // across the entire JobInstance, restartability, and concurrency.
        Long newExecutionId = jobOperator.restart(oldExecutionId);
        return newExecutionId;
    }

    public JobExecution getExecution(long executionId) {
        return jobExplorer.getJobExecution(executionId);
    }
}
```

Checking status before calling produces clearer error messages, **not a lock against race conditions**. Between reading `FAILED` and issuing restart, another node might already have restarted the same instance. `JobOperator` and the repository remain responsible for enforcing validity; the admin application must handle exceptions and duplicate requests at the service/API layer.

### 4.4. Invoking from a Scheduler, CLI, or Admin API

Example internal REST endpoint calling the service:

```java
package example.batch.ops;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/internal/batch")
public class BatchOperationsController {

    private final BatchRestartService restartService;

    public BatchOperationsController(BatchRestartService restartService) {
        this.restartService = restartService;
    }

    @PostMapping("/executions/{executionId}/restart")
    public Map<String, Long> restart(@PathVariable long executionId)
            throws Exception {

        if (executionId <= 0) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "executionId must be positive"
            );
        }

        long newExecutionId =
            restartService.restartFailedOrStopped(executionId);

        return Map.of("newExecutionId", newExecutionId);
    }
}
```

This is a **minimal control path** illustrating the invocation. In a real system, the endpoint needs authentication/authorization for batch operator roles, action confirmation, audit logging, proper exception mapping, and duplicate-request protection. Never expose an unauthenticated restart endpoint or accept arbitrary IDs across tenants without access checks.

---

## 5. Preparing Infrastructure for Operator Restarts to Succeed

### 5.1. Required Beans and Data

When using `JobOperator` under the Spring Batch 5.x model with JDBC metadata:

- `JobRepository` backed by a **persistent metadata database** with the version-matched schema.
- `JobExplorer` able to read persisted `JobInstance` and `JobExecution` records.
- `JobLauncher` capable of launching the corresponding job definition.
- `JobRegistry` holding the registered `Job` name so the operator can resolve the job from metadata.
- `JobOperator` configured to use the components above.
- Restartable readers/writers persisting checkpoints properly via `ExecutionContext` and `ItemStream`.

`@EnableBatchProcessing` in Spring Batch 5.x provides many infrastructure beans, including `JobOperator`. With Spring Boot 3.x, standard Batch auto-configuration can also provide infrastructure; pick **one consistent configuration approach**. Adding `@EnableBatchProcessing` or extending `DefaultBatchConfiguration` causes part of Boot's auto-configuration to back off, including metadata schema initialization options depending on configuration.

### 5.2. Gradle Dependencies for Application and Tests

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'

    testRuntimeOnly 'com.h2database:h2'
}
```

These dependencies assume the project uses the Spring Boot BOM or dependency management to align Spring Batch versions. In-memory H2 is only a test database: if the goal is restarting after a production application restarts, metadata must live in a **database that survives JVM termination**.

### 5.3. Simple H2 Test Configuration

Example `src/test/resources/application-operator-test.yml`:

```yaml
spring:
  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: always

  datasource:
    generate-unique-name: true
```

With H2 on the test classpath and no other datasource configured, Spring Boot can auto-configure an embedded datasource. `spring.batch.job.enabled=false` disables auto-running jobs when the application context starts; in integration tests, we invoke the launcher explicitly.

For restart tests within the same context, both the failed run and the restart run must share the **same live H2 database**. Do not swap datasources between the two runs.

### 5.4. Metadata Must Remain Intact

Example of a restart across two processes:

```text
Process A                          Metadata DB
  JobExecution #810 FAILED   ----> BATCH_JOB_EXECUTION
  Step checkpoint = 80       ----> BATCH_STEP_EXECUTION_CONTEXT
  Process A exits                       |
                                        |
Process B starts                        |
  JobOperator.restart(810) <------------+
  JobExecution #811 STARTED
  ItemStream.open(checkpoint=80)
```

If Process B points to a different database, the metadata does not exist and the operator cannot restart execution 810. If an H2 `jdbc:h2:mem:...` database vanishes when the JVM exits, you cannot rely on it to restart in a new JVM either.

---

## 6. Execution Flow of a Failed Job

### 6.1. Hypothetical Scenario

An invoice import job has two steps:

```text
invoiceImportJob
  |
  +-- validateInputStep
  |     status: COMPLETED
  |
  +-- importInvoicesStep
        reads 1000 records, commits every 100
        checkpoint saved at offset=600
        database connection error on next read
        status: FAILED

JobExecution #2100: FAILED
```

After the database recovers, the operator is asked to restart execution `2100`:

```java
long newId = jobOperator.restart(2100L);
```

Expected outcome:

- `JobInstance` remains the same.
- The framework creates a new `JobExecution`.
- `validateInputStep` is skipped under default policy because it is already `COMPLETED`.
- `importInvoicesStep` re-runs with the saved `ExecutionContext`/checkpoint, provided the reader/writer are properly designed for restart.
- The job finishes `COMPLETED` if the remaining processing succeeds.
- Final record count has no lost or duplicated records, backed by transactions and writer idempotency.

### 6.2. Checkpoint Is Not "The Last Line Read"

`ExecutionContext` is normally updated and persisted at chunk/transaction boundaries. When an error occurs mid-chunk:

```text
read 1..100   -> commit -> checkpoint 100
read 101..200 -> commit -> checkpoint 200
read 201..250 -> exception + rollback

ExecutionContext persisted for restart: offset=200
In-memory offset inside reader at failure: may already be 250
```

If restart were based on 250 while chunk 201–250 never committed, data would be lost. If the writer performed non-transactional side effects before failing, data could be duplicated when re-running 201–250.

Therefore, tests and operational procedures must care about the **persisted checkpoint**, not merely in-memory object state right before an exception.

### 6.3. ItemStream Supports Saving and Restoring Progress

Simplified example of a reader's checkpoint contract:

```java
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.ItemStream;

public class OffsetStream implements ItemStream {

    private static final String KEY = "invoice.reader.offset";

    private long offset;

    @Override
    public void open(ExecutionContext context) {
        offset = context.getLong(KEY, 0L);
    }

    public void onOneItemCommittedToProgress() {
        offset++;
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong(KEY, offset);
    }

    @Override
    public void close() {
        // Release resources if any.
    }
}
```

This illustrates the `ItemStream` API contract. In a real reader, the offset is adjusted according to the component's read/chunk and rollback semantics, not by externally calling a "committed" method without proper transactional coordination. The framework calls `open/update/close` when the stream is properly registered and managed; values written in `update` are persisted at checkpoints.

For restart to work:

1. The step must register/recognize the stream. With a delegate hidden inside a wrapper, you may need `.stream(delegate)` when building the step.
2. Storage keys must remain stable across runs, avoiding key collisions between two readers.
3. The context must hold types serializable by the repository.
4. The writer must avoid incorrect side effects when a chunk is reprocessed.
5. The set of identifying parameters must not change between the failed execution and the restart execution.

---

## 7. Integration Test: Calling `JobOperator.restart` and Verifying Results

Test goal: build a real job, make one step fail on the first run and succeed on restart, and verify metadata is accurately persisted in `JobRepository`.

### 7.1. Scenario

```text
retryableImportJob
    |
    +-- prepareStep       : increments prepareCounter, always COMPLETED
    |
    +-- deliverStep       : first run throws exception -> FAILED
                            next run -> COMPLETED

Test:
  launchJob(uniqueParameters) -> FAILED, JobExecution A
  jobOperator.restart(A.id)   -> JobExecution B, COMPLETED
  A.instanceId == B.instanceId
  A.id != B.id
  prepareCounter == 1 (COMPLETED step is skipped)
  deliverCounter == 2 (FAILED step runs again)
```

### 7.2. Java Integration Test

Using JUnit 5, Spring Batch 5.x, Spring Boot 3.x, and H2:

```java
import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.launch.JobOperator;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.PlatformTransactionManager;

import static org.junit.jupiter.api.Assertions.*;

@SpringBatchTest
@SpringBootTest(
    classes = OperatorRestartFailedTest.TestApplication.class
)
@ActiveProfiles("operator-test")
class OperatorRestartFailedTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    private JobOperator jobOperator;

    @Autowired
    private JobExplorer jobExplorer;

    @Autowired
    private AtomicInteger prepareCounter;

    @Autowired
    private AtomicInteger deliverCounter;

    @Test
    void operatorRestartsFailedExecutionWithinSameInstance()
            throws Exception {

        JobParameters parameters = new JobParametersBuilder()
            .addString("test.requestId", UUID.randomUUID().toString())
            .toJobParameters();

        JobExecution first =
            jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.FAILED, first.getStatus());
        assertEquals(1, prepareCounter.get());
        assertEquals(1, deliverCounter.get());

        // JobOperator takes the JobExecution ID and returns the new execution ID.
        Long restartedId = jobOperator.restart(first.getId());

        // Test launcher runs synchronously by default. If configured
        // asynchronously, wait for execution to finish before asserting
        // terminal status.
        JobExecution restarted =
            jobExplorer.getJobExecution(restartedId);

        assertNotNull(restarted);
        assertEquals(BatchStatus.COMPLETED, restarted.getStatus());

        assertEquals(
            first.getJobInstance().getId(),
            restarted.getJobInstance().getId()
        );
        assertNotEquals(first.getId(), restarted.getId());

        // Step that was COMPLETED on the first run is not re-executed.
        assertEquals(1, prepareCounter.get());

        // FAILED step runs one more time.
        assertEquals(2, deliverCounter.get());

        assertTrue(restarted.getStepExecutions().stream()
            .map(StepExecution::getStepName)
            .anyMatch("deliverStep"::equals));
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import(TestJobs.class)
    static class TestApplication {
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class TestJobs {

        @Bean
        AtomicBoolean failFirstDelivery() {
            return new AtomicBoolean(true);
        }

        @Bean
        AtomicInteger prepareCounter() {
            return new AtomicInteger();
        }

        @Bean
        AtomicInteger deliverCounter() {
            return new AtomicInteger();
        }

        @Bean
        Step prepareStep(
                JobRepository repository,
                PlatformTransactionManager transactionManager,
                AtomicInteger prepareCounter) {

            return new StepBuilder("prepareStep", repository)
                .tasklet((contribution, chunkContext) -> {
                    prepareCounter.incrementAndGet();
                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .build();
        }

        @Bean
        Step deliverStep(
                JobRepository repository,
                PlatformTransactionManager transactionManager,
                AtomicInteger deliverCounter,
                AtomicBoolean failFirstDelivery) {

            return new StepBuilder("deliverStep", repository)
                .tasklet((contribution, chunkContext) -> {
                    deliverCounter.incrementAndGet();

                    if (failFirstDelivery.getAndSet(false)) {
                        throw new IllegalStateException(
                            "Simulated delivery failure"
                        );
                    }

                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .build();
        }

        @Bean
        Job retryableImportJob(
                JobRepository repository,
                Step prepareStep,
                Step deliverStep) {

            return new JobBuilder("retryableImportJob", repository)
                .start(prepareStep)
                .next(deliverStep)
                .build();
        }
    }
}
```

File `src/test/resources/application-operator-test.yml` uses the content from section 5.3.

**Explanation:**

- `AtomicBoolean` is a test fixture that produces a single failure; it is not a business-state persistence solution. Because this state lives in a test bean, the fixture must be reset/isolated if expanded to multiple test methods or parallel runs.
- `JobLauncherTestUtils` sees only one `Job` in the context so it resolves the default job automatically. If an application has multiple jobs, call `setJob(jobUnderTest)` or configure explicit job selection.
- `prepareStep` completed in the first execution; on restart, the framework skips it by default.
- `deliverStep` throws an exception on the first run, then succeeds on the second execution.
- `jobOperator.restart(first.getId())` is the operation under test, distinct from launching a second time with new parameters.
- `JobExplorer` reads back the execution from the metadata repository, verifying actual instance/execution relationships.
- If `JobLauncher` is configured asynchronously, wait for a terminal status with a timeout before asserting `COMPLETED`; do not treat a single immediate read after restart as proof the job finished.

In real projects, tests should also assert **business data** after restart—for example, only one invoice per external ID, no duplicate events, and no missing records.

### 7.3. Verifying Results via Metadata

In addition to test assertions, we can inspect data using `JobExplorer`:

```java
JobExecution oldExecution =
    jobExplorer.getJobExecution(first.getId());

JobExecution newExecution =
    jobExplorer.getJobExecution(restartedId);

assertNotNull(oldExecution);
assertNotNull(newExecution);

assertEquals(BatchStatus.FAILED, oldExecution.getStatus());
assertEquals(BatchStatus.COMPLETED, newExecution.getStatus());

assertEquals(
    oldExecution.getJobInstance().getId(),
    newExecution.getJobInstance().getId()
);
```

If a test needs to verify **checkpoint recovery**, read `StepExecution.getExecutionContext()` of the failed execution from the repository, record what the reader receives in `ItemStream.open()` during the restart, and compare them. Seeing `COMPLETED` alone does not prove the reader resumed at the right offset.

### 7.4. Running Tests Against a Persistent Metadata Database

In CI, in-memory H2 works well for single-process tests. To verify restarts across **actual JVM or container restarts**, use a JDBC metadata repository on storage that survives restarts: PostgreSQL, Oracle, SQL Server, file-mode H2, or a dedicated test database service.

---

## 8. Handling Exceptions When Calling Restart

`JobOperator.restart(long)` in Spring Batch 5.x declares several checked exceptions. They carry distinct meanings and should not be caught indiscriminately and retried in an infinite loop.

| Exception | Typical Cause | Response |
| --- | --- | --- |
| `NoSuchJobExecutionException` | Execution ID does not exist in the active repository | Verify ID, datasource, environment, and metadata access |
| `NoSuchJobException` | Metadata has the execution, but the job definition is missing in the current registry | Ensure the job name is registered and present in the deployed version |
| `JobInstanceAlreadyCompleteException` | The instance already has a successful execution | Do not restart this instance; a new run requires new parameters |
| `JobRestartException` | Job sets `preventRestart`, metadata is inconsistent, instance is not in a valid restartable state, or other framework rules | Investigate cause, restart policy, consistency, and step history |
| `JobParametersInvalidException` | Current validator rejects stored parameters | Check validator/contract changes introduced in a new deployment |

Errors related to running executions, datasources, transactions, or infrastructure can also surface as runtime/wrapped exceptions. Consult the official exception list for your exact Spring Batch version.

### 8.1. Example Error Classification in the Service Layer

```java
import org.springframework.batch.core.launch.NoSuchJobException;
import org.springframework.batch.core.launch.NoSuchJobExecutionException;
import org.springframework.batch.core.launch.JobRestartException;
import org.springframework.batch.core.repository.JobInstanceAlreadyCompleteException;
import org.springframework.batch.core.JobParametersInvalidException;

public long restartWithErrorClassification(long failedId)
        throws Exception {

    try {
        return jobOperator.restart(failedId);

    } catch (NoSuchJobExecutionException e) {
        // Wrong ID or metadata repository does not contain the execution.
        throw new IllegalArgumentException(
            "Unknown execution ID: " + failedId, e
        );

    } catch (NoSuchJobException e) {
        // Current application version lacks the old job definition.
        throw new IllegalStateException(
            "Job definition is unavailable for execution " + failedId, e
        );

    } catch (JobInstanceAlreadyCompleteException e) {
        // Logical work for this instance is already complete.
        throw new IllegalStateException(
            "Job instance has already completed", e
        );

    } catch (JobParametersInvalidException e) {
        throw new IllegalStateException(
            "Stored parameters fail current validation", e
        );

    } catch (JobRestartException e) {
        throw new IllegalStateException(
            "Restart rejected by Spring Batch", e
        );
    }
}
```

This snippet illustrates an extension for a service using `jobOperator`. In production, use domain/API-specific exceptions mapped to stable error codes—for example "execution not found", "already completed", "job not registered", "restart rejected", or "temporary infrastructure error".

A transient SQL error can be retried at the appropriate layer, but **retrying a restart command** must check whether the prior call already created a new `JobExecution`. If the response timed out after launching the job, immediately resending can conflict with the now-running execution.

---

## 9. Operational Checklist Before and After Restart

### 9.1. Before Restart

An operator can follow this procedure:

1. **Identify the exact execution:** record `jobName`, `jobExecutionId`, `jobInstanceId`, identifying parameters, environment, and tenant.
2. **Inspect current metadata:** review `BatchStatus`, `ExitStatus`, failure exceptions, step history, checkpoints, and any newer executions.
3. **Confirm nothing is still running:** check the scheduler, worker nodes, processes/containers, queues, and repository state. Pay special attention to executions stuck in `STARTED` after a JVM crash.
4. **Find and fix the root cause:** database, input data, API credentials, data mapping, quotas, or timeouts.
5. **Assess side effects:** committed records, written files, sent notifications, external system state; verify whether re-running is safe.
6. **Confirm job restartability and definition compatibility:** job is still in the registry, parameters are valid, and step names and checkpoint contracts have not changed incompatibly.
7. **Invoke restart with the exact execution ID:** record the operator, reason, and new execution ID.

Example using inspection APIs:

```java
String summary = jobOperator.getSummary(failedExecutionId);

var steps =
    jobOperator.getStepExecutionSummaries(failedExecutionId);

var runningIds =
    jobOperator.getRunningExecutions("invoiceImportJob");
```

These APIs assist verification, but they do not replace external process checks when `STARTED` metadata is stuck after a host crash.

### 9.2. After Restart

1. Record the **new `JobExecution ID`** returned by the operator.
2. Monitor status until terminal: `COMPLETED`, `FAILED`, or `STOPPED`.
3. Verify `readCount`, `writeCount`, `skipCount`, `rollbackCount`, and checkpoints in relevant steps.
4. Reconcile business data: counts, unique keys, checksums, or side-effect traces.
5. Record the outcome and, if it fails again, address the new cause; avoid endless restart loops.

With an asynchronous launcher, use bounded monitoring or system schedulers/observability to check status. Avoid writing loops that repeatedly call `restart` just because status is not `COMPLETED` yet.

### 9.3. Suggested Operational Audit Log

```text
action            = RESTART_JOB_EXECUTION
requestedBy       = batch-operator
jobName           = invoiceImportJob
jobInstanceId     = 41
sourceExecutionId = 810
newExecutionId    = 811
reason            = external database recovered
requestedAt       = 2026-11-16T08:30:00+07:00
initialResult     = LAUNCHED
finalResult       = COMPLETED
```

These fields are an audit example; in real systems, avoid logging secrets, raw credentials, and sensitive personal data from job parameters or execution contexts.

---

## 10. Special Case: Process Died While Repository Still Shows `STARTED`

During an abrupt shutdown such as a killed process, power loss, or node eviction, the application may not get a chance to update the final execution status in the database. Metadata stays `STARTED` even though the job is no longer running.

```text
Spring Batch JVM #1:   process crashed
Metadata repository:  JobExecution #910 = STARTED
Spring Batch JVM #2:   sees STARTED, restart rejected
```

This is an **operational state recovery** issue before restart can happen. Never assume every `STARTED` row is stale: another node might genuinely still be processing it.

In Spring Batch 5.x:

- Confirm with certainty that no process/worker is still executing that run.
- Investigate which transactions committed and which checkpoints were persisted.
- Transition metadata to an appropriate state via a controlled administrative procedure if allowed, maintaining consistency. Never edit status columns directly by guesswork, because versions, counters, contexts, and related rows also matter.
- Only after the state is valid and safe should you call `JobOperator.restart(executionId)`.

In **Spring Batch 6.x**, `JobOperator.recover(JobExecution)` was added for executions stuck in `STARTED` after an abrupt shutdown. Use it only after confirming the execution is genuinely no longer running; check the exact API documentation for your version.

### 10.1. Differences Among Stop, Fail, and Abandon

- **Stop:** requests a running job to terminate cleanly; it may take time to reach `STOPPED`. A `STOPPED` execution can be restarted if the job allows it.
- **Fail:** execution ended `FAILED` due to an error, usually still restartable after fixing the root cause.
- **Abandon:** marks the execution `ABANDONED` to close tracking in a way that blocks restarting that execution. It is not a way to "make a job runnable again."

`jobOperator.abandon(id)` is a lifecycle-impacting admin action and must be used intentionally. Do not use it to clear a `FAILED` error hoping restart will magically work.

---

## 11. Business Risks During Restart

### 11.1. Restart Does Not Automatically Guarantee Exactly-Once for All Side Effects

Example job steps:

```text
1. Call email-sending API
2. Write SENT status to database
3. Commit metadata checkpoint
```

If the process dies after step 1 but before step 2 or 3, a restart can send the email a second time. Spring Batch coordinates transactions and checkpoints for participating resources, but it cannot automatically make a non-transactional API exactly-once.

Risk mitigation:

- Use an **idempotency key** derived from a business ID when calling external systems.
- Enforce unique constraints / UPSERTs for business outputs.
- Use the outbox pattern for transactional events.
- Split steps along clear transaction boundaries.
- Reconcile committed data before resuming when required by business contracts.

### 11.2. Do Not Change Identifying Parameters on Restart

If a job processes `2026-11-16` and tenant `A`, operator restart uses the old instance's parameters. To process a different date, create a new instance with new identifying parameters. "Editing parameters so restart runs" breaks checkpoint semantics and skews output scope.

### 11.3. Job Definition Changes Across Versions

Restarts often happen after deploying a new release. If code changes:

- `Job` or `Step` names.
- Flow transitions, `startLimit`, or `allowStartIfComplete`.
- Keys/data types in `ExecutionContext`.
- Serializers or metadata schema.
- Input file formats or data filtering rules.

then the old execution may no longer be compatible with the new code.

For example, an old checkpoint storing `reader.offset=500L` while a new reader expects `source.page.index` can cause the job to read from the beginning or fail. Have a cross-version checkpoint compatibility policy or a clear operational decision for metadata transitions.

### 11.4. Partitioning and Remote Processing

A job with partitioned steps or remote workers requires checking per-partition state, commit ordering, and task ownership. Restarting at the job level does not mean all partitions re-run; the framework can use metadata to determine which partitions still need work.

Inspect partition `StepExecution`s, external worker state, and ensure no old worker keeps writing data once the new execution starts.

### 11.5. Concurrent Restart Requests

Two operators or two nodes might issue restarts for the same execution simultaneously:

```text
operator A -> restart(810)
operator B -> restart(810) right after
```

The metadata repository enforces controls on execution creation and state, yet the admin application should still implement request idempotency, check for active executions, and apply locking/authorization per instance as needed. One of the two requests may be rejected; the caller should clearly report "an execution is already running" rather than retrying with new parameters.

---

## 12. Common Issues When Operating `JobOperator.restart`

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| `NoSuchJobExecutionException` | Passed JobInstance ID by mistake or queried wrong database/environment | Check ID in `BATCH_JOB_EXECUTION` and repository config |
| `NoSuchJobException` | Job renamed, bean removed, or job not registered in `JobRegistry` | Compare job name in metadata against current registry |
| `JobInstanceAlreadyCompleteException` | Instance already has a completed execution; operator passed an older execution | Inspect all executions for the instance |
| `JobRestartException` due to non-restartable | `.preventRestart()` or job/step policy | Inspect Job definition, `startLimit`, step statuses |
| Status remains `STARTED` after crash | JVM died before updating metadata | Confirm process is dead, follow recovery procedure |
| Restart re-runs a completed step | `allowStartIfComplete(true)` or flow changed | Inspect step config and execution history |
| Restart reads data from the start | Stream did not save/restore checkpoint, key changed, wrong repository | Read `ExecutionContext` from repository and verify `open/update` |
| Restart succeeds but output is duplicated | Non-transactional side effect, non-idempotent writer | Check unique keys, transaction boundaries, outbox |
| Restart cannot see metadata after switching nodes | In-memory H2 or different datasource, missing schema | Use a shared persistent metadata database |
| Method returns ID but dashboard still shows `STARTED` | Async JobLauncher | Poll `JobExplorer` with a timeout; do not assume completion |
| Retrying restart command throws "already running" | First command launched the job before response timed out | Query recent/running executions before retrying |
| Restart fails after deploy | Job/step names or context serialization changed | Check version compatibility, migration, checkpoint contract |

### 12.1. Checking with `JobExplorer` Before Acting

```java
JobExecution failed = jobExplorer.getJobExecution(810L);

if (failed == null) {
    throw new IllegalArgumentException("Unknown execution ID");
}

System.out.println("Job: "
    + failed.getJobInstance().getJobName());

System.out.println("Instance: "
    + failed.getJobInstance().getId());

System.out.println("Execution status: " + failed.getStatus());
```

Do not use `System.out` as the official audit log in an admin application. It only shows which details to collect; in practice use structured logging with correlation IDs, protect sensitive job parameter values, and record operator actions.

### 12.2. Do Not "Fix" a Restart Error by Immediately Creating a New `JobInstance`

If an import job of 1,000 invoices wrote 600 and failed, changing `run.id` and running from scratch can create 600 duplicate records. Creating a new instance is only appropriate when business operations intentionally request **a fresh processing run from the beginning** and deduplication or cleanup is already in place.

If the goal is to finish the incomplete work, find and fix why restart was rejected instead of bypassing historical metadata.

---

## 13. Testing Rejection Scenarios

Beyond the happy path in section 7, write dedicated tests for these scenarios:

### 13.1. Restarting a `COMPLETED` Execution

```java
JobExecution completed =
    jobLauncherTestUtils.launchJob(uniqueParameters);

// With a fixture ensuring the job succeeded:
assertEquals(BatchStatus.COMPLETED, completed.getStatus());

assertThrows(
    JobInstanceAlreadyCompleteException.class,
    () -> jobOperator.restart(completed.getId())
);
```

This assertion pattern applies to a succeeding fixture, unlike the fail-once fixture in section 7. This test must use a job/job parameters set up to succeed on the first run.

### 13.2. Non-Existent Execution ID

```java
assertThrows(
    NoSuchJobExecutionException.class,
    () -> jobOperator.restart(nonExistingExecutionId)
);
```

Do not pick a random number and assume it does not exist in a shared database. Use an isolated test repository fixture or verify the ID does not exist before asserting.

### 13.3. Disallowing Restart

```java
Job noRestartJob = new JobBuilder("noRestartJob", repository)
    .start(stepThatWillFail)
    .preventRestart()
    .build();
```

Let this job fail once, then assert the operator rejects restart. In such tests, ensure the job actually has a `FAILED` execution: calling restart on a job that never ran does not test `preventRestart()`.

### 13.4. Job No Longer Registered

Persist metadata for a job, then start another application context using the same persistent metadata **without the corresponding job definition**. Call restart and verify `NoSuchJobException`. This tests wiring/deployment rather than job processing.

### 13.5. Async Launcher

Use an asynchronous `TaskExecutor` and a step that runs long enough to observe. Assert `restart` returns an execution ID, then wait for `JobExplorer` to report a terminal status using bounded polling. Avoid asserting `COMPLETED` immediately after receiving the ID.

---

## 14. API Differences Between Spring Batch 5 and Spring Batch 6

Starting in Spring Batch 6.x, the operator API provides more ergonomic object-based overloads, while several primitive-ID methods are marked deprecated.

| Task | Spring Batch 5.x | Spring Batch 6.x |
| --- | --- | --- |
| Restart from failed execution | `Long newId = jobOperator.restart(oldId);` | `JobExecution newRun = jobOperator.restart(failedExecution);` |
| Access execution before restart | `jobExplorer.getJobExecution(id)` | Can fetch execution from `JobRepository` via new APIs |
| Recover execution stuck `STARTED` after crash | Requires version-appropriate controlled metadata procedure | `jobOperator.recover(jobExecution)` |
| ID-based APIs | Common API | Many ID-based overloads deprecated and scheduled for removal |
| Metadata infrastructure | Typically JDBC `JobRepository` | Supports multiple repository types; persistent repository still required across processes |

Conceptual Spring Batch 6 example:

```java
JobExecution failedExecution = /* read from metadata repository */;

JobExecution restartedExecution =
    jobOperator.restart(failedExecution);

long newExecutionId = restartedExecution.getId();
```

If an execution is stuck in `STARTED` after an abrupt shutdown and you verify it is no longer running, Spring Batch 6 offers `jobOperator.recover(failedExecution)` to move the state into a proper restart workflow. Do not copy Spring Batch 6 code into a Spring Batch 5 project without upgrading the API.

Because packages, exceptions, and infrastructure differ across versions, examples in this lesson use **Spring Batch 5.x as the baseline** and highlight what changes when upgrading.

---

## 15. Practice Exercises

### Exercise 1 — Restart a Failed Job via the Operator

Create an `orderImportJob` job with two steps:

1. `loadConfigStep` always ends `COMPLETED`.
2. `importOrdersStep` throws `IllegalStateException` on the first run and succeeds on the second.

Create unique identifying parameters. Use `JobLauncherTestUtils` for the first run and `JobOperator.restart(failedExecutionId)` for the second. Assert the two executions have different IDs under the same instance, `loadConfigStep` ran only once, and the final job status is `COMPLETED`.

### Exercise 2 — Test Status-Based Refusals

Create a `COMPLETED` execution, attempt a restart, and verify `JobInstanceAlreadyCompleteException`. Use a non-existent execution ID and verify `NoSuchJobExecutionException`.

Explain why you should not manually flip status from `COMPLETED` to `FAILED` to force a restart.

### Exercise 3 — Checkpoint Recovery

Create a chunk job reading 100 rows with commit interval 20. Intentionally fail after several chunks commit. Inspect the failed step's persisted `ExecutionContext`; restart the same instance via the operator. Assert the reader receives the saved checkpoint in `open()`, the final output contains all 100 rows without duplicates, and the final execution is `COMPLETED`.

### Exercise 4 — Monitoring Async Restart

Configure an asynchronous launcher, call `restart`, and store the new ID. Write a status endpoint/query using `JobExplorer`; determine when it transitions `STARTED → COMPLETED` or `FAILED`. Do not treat a successful restart call as the whole job succeeding.

### Exercise 5 — Designing an Operational Procedure

Suppose an execution fails after sending 400 out of 1,000 emails. Design a safe restart plan covering idempotency keys, where sent status is persisted, how to inspect execution metadata, handling non-transactional sends, and audit logging after restart.

---

## 16. Implementation Takeaways

**`JobOperator.restart(failedExecutionId)` resumes an existing `JobInstance` using persisted metadata.** It creates a new `JobExecution`, enforces job/step restart policies, and can restore checkpoints for incomplete steps. To guarantee correct results, you need a persistent metadata repository, a registered job definition, stable identifying parameters, stateful reader/writer management, and controlled side effects.

Every restart must be evaluated across three independent outcomes:

- **Control:** the operator accepted the command and returned a new execution ID.
- **Framework:** the new execution reached the expected terminal status with accurate step history/checkpoints.
- **Business:** final data is complete, free of duplicates, and free of erroneous side effects.

Only when all three layers agree should an operator mark the recovery task successful.

## 17. References

- [Spring Batch 5.2 — JobOperator API](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/launch/JobOperator.html).
- [Spring Batch 5.2 — Advanced Metadata Usage / JobOperator](https://docs.spring.io/spring-batch/reference/5.2/job/advanced-meta-data.html).
- [Spring Batch 5.2 — Configuring and Running a Job](https://docs.spring.io/spring-batch/reference/5.2/job/configuring.html).
- [Spring Batch 5.2 — Restarting a Job](https://docs.spring.io/spring-batch/reference/5.2/job/advanced-meta-data.html).
- [Spring Batch 5.2 — `JobRepository` and `JobExplorer`](https://docs.spring.io/spring-batch/reference/5.2/job/advanced-meta-data.html).
- [Spring Batch 5.2 — Testing](https://docs.spring.io/spring-batch/reference/5.2/testing.html).
- [Spring Batch 6 — JobOperator API](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/launch/JobOperator.html).
- [Spring Batch 6 — Advanced Metadata Usage / Recovering a job](https://docs.spring.io/spring-batch/reference/job/advanced-meta-data.html).
