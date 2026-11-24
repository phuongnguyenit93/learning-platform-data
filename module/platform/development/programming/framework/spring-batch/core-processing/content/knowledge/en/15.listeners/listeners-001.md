# JobExecutionListener Before and After a Job

In Spring Batch, `JobExecutionListener` provides two callbacks to perform work tied to the lifecycle of a Job run: `beforeJob()` is invoked before the Job executes its Steps, and `afterJob()` is invoked after the Job finishes. Listeners are commonly used to record start/end timestamps, persist audit records, aggregate outcomes, or send notifications based on execution status.

The listener receives a `JobExecution` object, so it can read `JobParameters`, `BatchStatus`, `ExitStatus`, execution time, `StepExecution` instances, and exceptions. Remember that a listener is bound to **a single Job execution**. If a `JobInstance` is restarted, Spring Batch creates a new `JobExecution`, and the callbacks are invoked again for the new execution.

## 1. What is JobExecutionListener?

`JobExecutionListener` is an interface in Spring Batch with two methods:

```java
public interface JobExecutionListener {

    void beforeJob(JobExecution jobExecution);

    void afterJob(JobExecution jobExecution);
}
```

- `beforeJob(JobExecution)`: runs before the Job's Steps start executing.
- `afterJob(JobExecution)`: runs after the Job has finished, regardless of whether the Job completed successfully or failed.

Listeners are suited for Job-level actions. For example, logging the start of a data import run, saving the completion time and outcome, or sending an alert when a Job fails.

General flow:

```text
JobLauncher
    |
    v
Create JobExecution
    |
    v
beforeJob(jobExecution)
    |
    v
Execute Steps
    |
    +----> Job completes
    |         or
    +----> Job fails / is stopped
    |
    v
afterJob(jobExecution)
    |
    v
JobExecution ends
```

`beforeJob` and `afterJob` do not replace Step data-processing logic. They are lifecycle hooks for performing cross-cutting work for the entire Job.

## 2. Purpose of beforeJob()

`beforeJob()` is called before the Job starts executing its Steps. This is the right place to record that a run has started or read input metadata needed for auditing.

Common tasks placed in `beforeJob()`:

- Log the Job name, `JobExecution` ID, and identifying `JobParameters`.
- Record the start timestamp or create an audit record for the execution.
- Put a small shared value into the Job `ExecutionContext` if Steps need to read it.
- Attach a correlation ID or tracing metadata to the execution.

Example listener that logs when a Job starts:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;

public class ImportJobListener implements JobExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(ImportJobListener.class);

    @Override
    public void beforeJob(JobExecution jobExecution) {
        log.info("Job {} is starting. executionId={}, parameters={}",
                jobExecution.getJobInstance().getJobName(),
                jobExecution.getId(),
                jobExecution.getJobParameters());
    }

    @Override
    public void afterJob(JobExecution jobExecution) {
        // Handle the outcome in the next callback.
    }
}
```

`beforeJob()` is not the right place to process batches of records or run a long task. Put business processing inside a Step so it has its own transaction boundary, state, and restartability.

If `beforeJob()` needs to write an audit record to the database, call a service with an appropriate transaction. Do not open a transaction spanning the entire Job just to hold an audit record.

## 3. Purpose of afterJob()

`afterJob()` is called after the Job finishes, whether the outcome is success or failure. The listener should inspect the status in `JobExecution` to decide the appropriate action.

Common tasks placed in `afterJob()`:

- Record the end timestamp and execution duration.
- Persist the final status and `ExitStatus` code to an audit log.
- Aggregate metrics from `StepExecution` instances.
- Record exceptions when the Job fails.
- Send notifications or emit signals to a monitoring system.

Example:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;

public class ImportJobListener implements JobExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(ImportJobListener.class);

    @Override
    public void beforeJob(JobExecution jobExecution) {
        log.info("Starting job execution {}", jobExecution.getId());
    }

    @Override
    public void afterJob(JobExecution jobExecution) {
        if (jobExecution.getStatus() == BatchStatus.COMPLETED) {
            log.info("Job execution {} completed with exit status {}",
                    jobExecution.getId(), jobExecution.getExitStatus());
        } else if (jobExecution.getStatus() == BatchStatus.FAILED) {
            log.error("Job execution {} failed. Exceptions: {}",
                    jobExecution.getId(),
                    jobExecution.getAllFailureExceptions());
        } else {
            log.warn("Job execution {} ended with status {}",
                    jobExecution.getId(), jobExecution.getStatus());
        }
    }
}
```

Do not check only `COMPLETED` and `FAILED` and assume every other status means success. A Job can end with a status such as `STOPPED`, `ABANDONED`, or another status that requires separate operational handling.

## 4. Distinguishing BatchStatus and ExitStatus in a Listener

`JobExecution` provides both `BatchStatus` and `ExitStatus`. These two values are related but serve different purposes:

| Property | Meaning | Examples |
|---|---|---|
| `BatchStatus` | Execution lifecycle status managed by Spring Batch | `STARTED`, `COMPLETED`, `FAILED`, `STOPPED` |
| `ExitStatus` | Job exit result code, which can carry a custom code | `COMPLETED`, `FAILED`, `NO_DATA`, `INVALID_INPUT` |

In `afterJob()`, `BatchStatus` is typically used to determine whether the Job succeeded or failed operationally. `ExitStatus` is useful when distinguishing business outcomes. For example, a Job may finish with code `NO_DATA` to indicate there was no data for the day, while the execution status still completed normally.

If you need to route between Steps, configure the flow based on Step `ExitStatus`. `JobExecutionListener` primarily observes the Job lifecycle; do not use a listener to replace the control flow declared in the Job.

## 5. Reading Information from JobExecution

The callback receives a `JobExecution`, which contains plenty of useful information:

| API | Information |
|---|---|
| `getId()` | ID of the Job execution. |
| `getJobInstance()` | `JobInstance` to which the execution belongs. |
| `getJobParameters()` | Input parameters for the run. |
| `getStatus()` | Current/final `BatchStatus`. |
| `getExitStatus()` | `ExitStatus` of the Job. |
| `getStartTime()` | Start timestamp. |
| `getEndTime()` | End timestamp. |
| `getStepExecutions()` | `StepExecution` instances belonging to this run. |
| `getAllFailureExceptions()` | Recorded failure exceptions. |
| `getExecutionContext()` | Job `ExecutionContext` for the execution. |

You can aggregate metrics from `StepExecution` instances in `afterJob()`:

```java
@Override
public void afterJob(JobExecution jobExecution) {
    for (StepExecution stepExecution : jobExecution.getStepExecutions()) {
        log.info(
                "Step {} status={}, read={}, write={}, filter={}, skip={}",
                stepExecution.getStepName(),
                stepExecution.getStatus(),
                stepExecution.getReadCount(),
                stepExecution.getWriteCount(),
                stepExecution.getFilterCount(),
                stepExecution.getSkipCount());
    }
}
```

These metrics help build a summary report for a run. If a Job has multiple Steps or flow branches, iterate through all `StepExecution` instances rather than assuming the Job always has a single Step.

## 6. Registering a JobExecutionListener on a Job

In Spring Batch 5 and later, you can register a listener using the `.listener(...)` method on `JobBuilder`:

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ImportJobConfig {

    @Bean
    public ImportJobListener importJobListener() {
        return new ImportJobListener();
    }

    @Bean
    public Job importOrdersJob(
            JobRepository jobRepository,
            Step importOrdersStep,
            ImportJobListener importJobListener) {

        return new JobBuilder("importOrdersJob", jobRepository)
                .listener(importJobListener)
                .start(importOrdersStep)
                .build();
    }
}
```

Once registered, Spring Batch invokes the listener during the lifecycle of each `JobExecution`. If the Job has multiple Steps, the listener is still invoked at the Job level once before the Steps and once after the Job finishes.

A single listener can be registered for multiple Jobs if the same logic applies. In that case, use `jobExecution.getJobInstance().getJobName()` to distinguish Jobs and avoid storing per-run state in shared mutable fields.

## 7. Using @BeforeJob and @AfterJob Annotations

In addition to implementing the interface, Spring Batch supports `@BeforeJob` and `@AfterJob` annotations on listener methods. This approach can help separate callbacks into clearly named methods:

```java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.annotation.AfterJob;
import org.springframework.batch.core.annotation.BeforeJob;

public class AnnotatedImportListener {

    @BeforeJob
    public void before(JobExecution jobExecution) {
        System.out.println("Starting: "
                + jobExecution.getJobInstance().getJobName());
    }

    @AfterJob
    public void after(JobExecution jobExecution) {
        System.out.println("Finished with status: "
                + jobExecution.getStatus());
    }
}
```

The annotated listener bean must also be registered on the Job:

```java
return new JobBuilder("importOrdersJob", jobRepository)
        .listener(annotatedImportListener)
        .start(importOrdersStep)
        .build();
```

Callback methods must accept the exact parameter types supported by the annotations. If you want an explicit implementation that is easy to locate with an IDE and easy to structure around shared logic, the `JobExecutionListener` interface is the direct choice.

## 8. Listener Is Called Again on Restart

`JobExecutionListener` is bound to `JobExecution`, not invoked once per `JobInstance`. When a `JobInstance` fails and is restarted, Spring Batch creates a new `JobExecution`. Consequently, both `beforeJob()` and `afterJob()` are called for the new execution.

Example:

```text
JobInstance: importOrders / fileId=orders-2026-11-15
  |
  +--> JobExecution #101: FAILED
  |       beforeJob()
  |       Steps run and fail
  |       afterJob()
  |
  +--> JobExecution #108: COMPLETED
          beforeJob()
          Steps restart and complete
          afterJob()
```

Because callbacks are invoked again, actions inside a listener must be designed for multiple executions. For example, if `afterJob()` sends an email, a successful restart may send another email. If the requirement is to send a notification only once per business unit of work, use a deduplication key based on the `JobInstance` or an appropriate business identifier.

Do not use a field like `startedAt` in a singleton listener to hold the start time between `beforeJob()` and `afterJob()`. If two `JobExecution` instances run concurrently, the field value can be overwritten. Read the timestamp directly from `JobExecution` or store needed state in `ExecutionContext`.

## 9. Writing Audit Records and Sending Notifications Safely

A listener can call a service to save an audit record after the Job finishes:

```java
@Service
public class JobAuditService {

    @Transactional
    public void recordOutcome(
            long executionId,
            String jobName,
            String status,
            String exitCode) {
        // Save an audit record in a short transaction.
    }
}
```

The listener calls this service from `afterJob()`:

```java
@Component
public class AuditingJobListener implements JobExecutionListener {

    private final JobAuditService auditService;

    public AuditingJobListener(JobAuditService auditService) {
        this.auditService = auditService;
    }

    @Override
    public void beforeJob(JobExecution jobExecution) {
        // Log or create a start audit record if needed.
    }

    @Override
    public void afterJob(JobExecution jobExecution) {
        String jobName = jobExecution.getJobInstance().getJobName();
        auditService.recordOutcome(
                jobExecution.getId(),
                jobName,
                jobExecution.getStatus().name(),
                jobExecution.getExitStatus().getExitCode());
    }
}
```

`JobAuditService`'s transaction is a short transaction for the audit operation. There is no need to keep a transaction open for the entire duration of the Job just to record the outcome.

For email, HTTP, or message brokers, keep in mind that the callback can be invoked again and side effects outside the database cannot roll back with the Job. You can write a completion event to an outbox, and then have a separate process send the notification with an idempotency key. This reduces the risk of duplicate sends when the callback or an external system fails.

A listener is part of the Job execution flow. Therefore, callbacks should be short and handle errors carefully. If sending a notification must not alter the batch processing outcome, isolate notification errors, record them for separate retry, or use an outbox. Do not let transient network failures compromise the ability to track Job outcomes.

## 10. How JobExecutionListener and StepExecutionListener Differ

Spring Batch provides listeners at multiple levels. Choose the right listener for the scope of events you want to observe:

| Listener | Scope | Common Callbacks |
|---|---|---|
| `JobExecutionListener` | Entire `JobExecution` | Before and after Job |
| `StepExecutionListener` | Single `StepExecution` | Before and after Step |
| `ChunkListener` | Single chunk | Before and after chunk, and when a chunk fails |
| `ItemReadListener` | Single item read | Before/after read and on read error |
| `ItemProcessListener` | Single item process | Before/after process and on processor error |
| `ItemWriteListener` | Single chunk write | Before/after write and on writer error |

Examples:

- Record total duration of importing orders: use `JobExecutionListener`.
- Record duration of just the file-reading Step: use `StepExecutionListener`.
- Record how many times a chunk rolls back: use `ChunkListener` or corresponding metadata.
- Investigate a specific record causing a processor failure: use `ItemProcessListener`.

Do not put per-item audit logic in `afterJob()` because this callback runs only at the Job level and does not provide item-level events.

## 11. Threading Notes and Asynchronous JobLauncher

In Spring Boot or Spring applications, listeners are typically declared as singleton beans. Multiple `JobExecution` instances can share the same listener instance, especially when Jobs run concurrently. Therefore:

- Avoid storing per-`JobExecution` state in mutable fields of the listener.
- Use data on `JobExecution` or `ExecutionContext` instead of shared variables.
- Dependencies invoked from the listener must support the application's concurrency model.
- Do not assume callbacks always run on the thread that called `JobLauncher`.

When using an asynchronous `JobLauncher`, `run()` may return as soon as the Job is submitted to the executor. `afterJob()` is called on the thread executing the Job when the Job completes. Callers should not wait for the result by keeping a transaction open; instead, track `JobExecution` via the repository, explorer, or an appropriate notification mechanism.

## 12. Common Pitfalls

| Mistake | Cause | How to Handle |
|---|---|---|
| Handling only `COMPLETED` in `afterJob` | Ignores cases where the Job failed or was stopped. | Handle all relevant `BatchStatus` values explicitly. |
| Assuming listener runs once per `JobInstance` | Listener actually runs per `JobExecution`. | Design auditing and notifications to account for restarts. |
| Storing start time in a singleton listener field | Concurrent executions can overwrite the field. | Use `JobExecution` or `ExecutionContext`. |
| Putting full business logic in `beforeJob`/`afterJob` | Hard to manage transactions, retries, and restarts for business work. | Move core processing into Steps; keep listeners to lifecycle work. |
| Sending emails directly without error control | Notifications may be duplicated or callback errors may affect execution flow. | Use an outbox, idempotency keys, and separate retries. |
| Confusing `JobExecutionListener` with `StepExecutionListener` | Capturing the wrong scope or missing granular data. | Choose the listener matching Job, Step, chunk, or item level. |
| Assuming `afterJob` runs on the launch caller thread | Asynchronous launcher executes the Job on another thread. | Track execution via metadata and monitoring mechanisms. |

## Conclusion

`JobExecutionListener` provides `beforeJob()` and `afterJob()` to handle work tied to the lifecycle of a Job run. `beforeJob()` is suited for recording the start and input metadata; `afterJob()` is suited for reading the final status, aggregating `StepExecution` metrics, saving audit records, or signaling the outcome. A listener should distinguish `BatchStatus` from `ExitStatus`, be registered on the Job with `.listener(...)`, and account for being invoked again on every `JobExecution`, including restarts. Keeping callbacks short, avoiding shared mutable state, and using outbox/idempotency for notifications enables reliable Job monitoring without complicating Step transactions.
