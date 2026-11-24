# A Tasklet throwing an exception

In Spring Batch, a Tasklet performs an operation or one pass of work inside a TaskletStep. When the operation cannot be completed, the Tasklet can throw an exception to report the failure to the framework. The TaskletStep receives the exception, handles the transaction of that execution pass, and marks the Step as failed.

An exception is the key mechanism for distinguishing a successful execution from one that did not complete. If a Tasklet catches an exception and ignores it, or returns RepeatStatus.FINISHED even though the operation failed, Spring Batch may record the Step as successful while the business data has not been processed correctly.

This lesson explains how an exception passes through a TaskletStep, how it affects the transaction and the Job status, how to classify errors, and how to design retry, restart, and side effects safely.

## 1. How does a Tasklet report an error?

A Tasklet declares an execute method that takes a StepContribution and a ChunkContext, and it can throw an Exception:

~~~java
RepeatStatus execute(
        StepContribution contribution,
        ChunkContext chunkContext) throws Exception;
~~~

The method returns a RepeatStatus when the pass ends normally:

- **RepeatStatus.FINISHED**: the Tasklet has completed; the Tasklet execution loop ends.
- **RepeatStatus.CONTINUABLE**: the Tasklet still has work; the TaskletStep calls the Tasklet again in the next pass.

If the Tasklet cannot complete because of an error, it can throw an exception:

~~~java
@Bean
public Step processBatchStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        BatchService batchService) {

    Tasklet tasklet = (contribution, chunkContext) -> {
        if (!batchService.inputIsReady()) {
            throw new IllegalStateException(
                    "Input batch is not ready");
        }

        batchService.processBatch();
        return RepeatStatus.FINISHED;
    };

    return new StepBuilder("processBatchStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .build();
}
~~~

If the input is not ready, the Tasklet throws an IllegalStateException. The return FINISHED statement is not executed, so the Step does not end as a successful run.

The point to remember: RepeatStatus controls the Tasklet loop. It is not the success/failure status of the Job. An exception reports an execution error and is handled by the TaskletStep at the Step level.

## 2. How does an exception pass through a TaskletStep?

The TaskletStep controls the loop that calls the Tasklet and the transaction for each call. When the Tasklet throws an exception, the exception exits the execute call and is handled in the Step's execution mechanism.

General flow:

~~~text
TaskletStep starts
       |
       v
Open a transaction for the Tasklet pass
       |
       v
Call Tasklet.execute(...)
       |
       +---- returns FINISHED ------> commit the pass
       |                              |
       |                              v
       |                         End the Step
       |
       +---- returns CONTINUABLE ---> commit the current pass
       |                              |
       |                              v
       |                         Call the next pass
       |
       +---- throws an exception ---> rollback per the transaction policy
                                       |
                                       v
                                  Step fails
~~~

With the default TaskletStep configuration, an exception from the Tasklet is the rollback signal for the execution pass's transaction. The StepExecution is updated with a failed status and the exception is kept in the metadata/logs for investigation. If the application customizes the transaction attributes or rollback rules, you need to check the Step's actual policy.

A Tasklet can throw a checked exception because the execute signature declares throws Exception. A RuntimeException can also be thrown directly. Whichever you use, choose an exception that accurately reflects the cause and do not turn an error that needs a rollback into a successful result.

### A Tasklet throwing an exception differs from returning FINISHED

The following two approaches have completely different meanings:

~~~java
// The work completed normally.
return RepeatStatus.FINISHED;
~~~

~~~java
// The work cannot be completed.
throw new IllegalStateException("Cannot process batch");
~~~

Do not use FINISHED to indicate that the Tasklet stopped because of an error. If a condition is a normal business outcome, represent it with a meaningful status or data, instead of pretending to complete or throwing a generic exception.

## 3. Impact on the transaction and rollback

The TaskletStep executes the Tasklet in a transaction managed by the transaction manager. When the Tasklet throws an exception, the current transaction is rolled back according to the Step's rollback policy. The database operations participating in that same transaction are undone.

For example:

~~~java
Tasklet tasklet = (contribution, chunkContext) -> {
    orderRepository.markBatchAsProcessing(batchId);
    reconciliationService.reconcile(batchId);

    if (reconciliationService.hasCriticalErrors(batchId)) {
        throw new IllegalStateException(
                "Reconciliation contains critical errors");
    }

    orderRepository.markBatchAsCompleted(batchId);
    return RepeatStatus.FINISHED;
};
~~~

If the repository operations participate in one transaction and the exception causes the transaction to roll back, the database changes in that pass are undone. However, you need to understand the limits of the transaction:

- Rollback only applies to resources participating in the corresponding transaction.
- Writing files, calling an HTTP API, or sending messages to an external system is usually not automatically undone along with the database transaction.
- If the Tasklet uses multiple DataSources with independent transaction managers, rolling back one transaction does not automatically roll back the other.
- Operations that were committed in earlier Tasklet passes are not rolled back just because a later pass fails.

Because a Tasklet can return CONTINUABLE, a multi-pass Tasklet may have committed some portions of work before a later pass throws an exception. A restart must know which portions have completed and which need to be redone.

### The transaction boundary of a multi-pass Tasklet

~~~text
Pass 1: Tasklet.execute -> process page 1 -> COMMIT
Pass 2: Tasklet.execute -> process page 2 -> COMMIT
Pass 3: Tasklet.execute -> error -> ROLLBACK

State after the failure:
  Page 1: committed
  Page 2: committed
  Pass 3: transaction rolled back
~~~

This differs from a Tasklet that performs only one operation in a single pass. When work is split into multiple passes, you need a checkpoint or durable state to determine progress precisely.

## 4. Classifying exceptions by cause

Not every exception needs to be handled the same way. They can be divided into several groups:

| Error group | Example | Usually suitable handling |
| --- | --- | --- |
| Invalid data or business condition | Missing input, a batch state that does not allow processing | Fail the Step or record a rejection result per the business process |
| Transient error | The database temporarily loses its connection, a remote service times out | Bounded retry if the operation is safe |
| Configuration error | Missing configuration file, wrong endpoint, wrong credentials | Fail early and fix the configuration |
| Programming error | NullPointerException, a violated invariant | Fail and fix the code; do not skip arbitrarily |
| Resource error | Out of disk space, connection pool exhausted | Fail, or retry once suitable recovery conditions exist |

Classification helps choose the exception type and the operational policy. For example, invalid input usually does not become valid by itself after a few attempts; continuous retrying only repeats the same error. Conversely, a transient connection error can recover after a backoff.

### Creating exceptions with business semantics

Instead of throwing a generic RuntimeException, you can define a specific exception:

~~~java
public class InvalidBatchStateException extends RuntimeException {

    public InvalidBatchStateException(String message) {
        super(message);
    }
}
~~~

Usage:

~~~java
if (batch.getStatus() != BatchStatus.READY) {
    throw new InvalidBatchStateException(
            "Batch " + batch.getId() + " is not READY");
}
~~~

A dedicated exception helps logs and monitoring systems distinguish business errors from technical errors. Do not put secret information or unnecessary personal data into the message.

## 5. Catching an exception in a Tasklet: when should and shouldn't you?

If there is no reason to handle it locally, let the exception exit the Tasklet. The TaskletStep needs to know the execution failed in order to roll back, update the status, and let the Job flow apply the corresponding policy.

Do not write:

~~~java
Tasklet tasklet = (contribution, chunkContext) -> {
    try {
        batchService.processBatch();
    } catch (Exception ex) {
        log.error("Batch processing failed", ex);
    }

    return RepeatStatus.FINISHED;
};
~~~

This code swallows the exception. Spring Batch sees the Tasklet return FINISHED and may record the Step as successful even though batchService failed.

If you need to add logging or context, you can log and then rethrow the exception:

~~~java
Tasklet tasklet = (contribution, chunkContext) -> {
    try {
        batchService.processBatch();
        return RepeatStatus.FINISHED;
    } catch (BatchProcessingException ex) {
        log.error("Cannot process batchId={}", batchId, ex);
        throw ex;
    }
};
~~~

If you need to change the exception type, keep the original cause:

~~~java
try {
    batchService.processBatch();
} catch (IOException ex) {
    throw new BatchProcessingException(
            "Unable to read batch input", ex);
}
~~~

Only wrap an exception when the new exception provides useful semantics. Keeping the cause helps investigate the stack trace and the root cause.

### When can you handle an exception locally?

You can catch an exception if the Tasklet truly has a valid way to handle it, such as:

- Converting an expected kind of error into a recorded business result.
- Performing necessary cleanup and then rethrowing the original error.
- Converting a technical exception into a specific domain exception while keeping the cause.
- Performing a fallback that the business allows and that can be verified.

After handling, if the work is still considered successful, you must ensure the result and the status reflect the truth. Do not catch just to prevent the Job from being FAILED.

## 6. The Job and Step receive a failed status

When an exception exits the Tasklet, the TaskletStep ends in a failed state. Spring Batch stores the BatchStatus and ExitStatus in the metadata.

The two concepts are related but different:

- **BatchStatus** is the standard lifecycle status of a JobExecution or StepExecution, such as COMPLETED, FAILED, STOPPED, or STARTED.
- **ExitStatus** is the result code used in the flow and can carry additional information for routing.

Normally, an unhandled exception leaves the Step with BatchStatus FAILED and an ExitStatus reflecting the error. The Job can also end FAILED if no flow transition handles the failure branch.

### Routing the Job when a Step fails

A Job can declare flow transitions to move to a Step that handles the error:

~~~java
@Bean
public Job dailyBatchJob(
        JobRepository jobRepository,
        Step processBatchStep,
        Step recordFailureStep,
        Step publishResultStep) {

    return new JobBuilder("dailyBatchJob", jobRepository)
            .start(processBatchStep)
                .on("FAILED").to(recordFailureStep)
            .from(processBatchStep)
                .on("*").to(publishResultStep)
            .end()
            .build();
}
~~~

An illustrative flow example: if processBatchStep has an ExitStatus of FAILED, the Job moves to recordFailureStep. For other exit codes, the flow goes to publishResultStep. Design the error-handling Step so it does not hide the original error and does not accidentally mark the entire Job as successful if the business still requires the Job to be FAILED.

If you want to distinguish multiple kinds of errors, you can use a custom ExitStatus or an error-classification step. Clearly determine which BatchStatus and ExitStatus will finally be returned, because they can differ when the Job has an error-handling flow.

## 7. Retrying transient errors in a Tasklet

A Tasklet does not have an item-level retry/skip pipeline like a chunk-oriented Step. If a Tasklet calls a service that has transient errors, the application can implement an explicit retry with Spring Retry or the service's own retry mechanism.

A retry policy should specify:

- Which exception types are retried.
- The maximum number of attempts.
- The interval and backoff between attempts.
- The overall timeout.
- The stop condition when the error is no longer transient.
- How to ensure the operation can be performed again safely.

Do not retry every exception. Data errors, configuration errors, or programming errors are usually not resolved by trying again.

An illustrative example using RetryTemplate for a recoverable service call:

~~~java
public class RemoteBatchService {

    private final RetryTemplate retryTemplate;
    private final RemoteClient remoteClient;

    public RemoteBatchService(
            RetryTemplate retryTemplate,
            RemoteClient remoteClient) {
        this.retryTemplate = retryTemplate;
        this.remoteClient = remoteClient;
    }

    public void submitBatch(String batchId) {
        retryTemplate.execute(context -> {
            remoteClient.submit(batchId);
            return null;
        });
    }
}
~~~

RetryTemplate needs to be configured with an appropriate retry policy, backoff policy, and exception classifier. If the attempts are exhausted, the final exception exits the service and the TaskletStep handles it as a Tasklet error.

### Be careful with transactions when retrying

If a RetryTemplate is called inside a Tasklet transaction, multiple attempts can take place within the same outer transaction. A failed attempt does not necessarily automatically roll back the transaction before the next attempt begins. This is especially important if the first attempt already performed part of a database operation.

For operations that need a separate transaction for each attempt, design an appropriate transaction boundary, for example by splitting out a service with suitable propagation or letting an orchestrator perform each attempt in its own transaction. Do not add new propagation out of habit; you must clearly determine which data is committed, rolled back, and how to recover after a crash.

If the remote API has received the request but the response times out, the client does not know for sure whether the server performed the operation. A retry may send the request a second time. Use a stable idempotency key, for example batchId plus the operation type, so the server can recognize the repeated request.

## 8. Restarting after a Tasklet throws an exception

If a JobExecution ends FAILED and the Job allows restart, you can restart the same JobInstance using the same Job name and identifying JobParameters. Spring Batch creates a new JobExecution for that instance.

With a TaskletStep, when the Step fails, the Step is usually executed again from the beginning in the restart. A custom Tasklet does not automatically have fine-grained checkpoints like an ItemStream reader. If the Tasklet had completed part of the work before failing, the application must know how to continue or redo it safely.

An example of a Tasklet that processes multiple pages:

~~~java
Tasklet tasklet = (contribution, chunkContext) -> {
    ExecutionContext context =
            contribution.getStepExecution().getExecutionContext();

    int nextPage = context.getInt("nextPage", 0);

    pageService.processPage(nextPage);

    context.putInt("nextPage", nextPage + 1);
    return pageService.hasMorePages(nextPage + 1)
            ? RepeatStatus.CONTINUABLE
            : RepeatStatus.FINISHED;
};
~~~

This illustrates a checkpoint. In a real application, you need to ensure that updating the page data and the checkpoint is consistent. If the page data has committed but the checkpoint has not been saved, a restart may reprocess the page. If the checkpoint is saved before the page data commits, a restart may skip data that has not completed.

Another option is to design the Tasklet to be idempotent: reprocessing the same batchId or pageId does not create duplicate data and does not corrupt the state. For operations with side effects outside the transaction, idempotency is especially important.

### When restart is not appropriate

If the error is wrong input data or an invalid configuration, restarting with the same parameters usually just repeats the error. Fix the cause before running again. If the business data has changed and an independent run is needed, determine new identifying parameters based on the business revision instead of adding a random timestamp.

## 9. Side effects outside the transaction

A Tasklet can perform many kinds of operations:

- Updating the database.
- Writing or moving files.
- Calling a REST API.
- Sending a message.
- Sending an email or notification.

Not all of these operations participate in the same transaction. For example:

~~~text
Tasklet
   |
   +--> UPDATE database
   |
   +--> POST remote API
   |
   +--> write file
   |
   +--> throw an exception
          |
          v
       DB rollback

The completed remote API call or file may still remain
~~~

A database rollback does not automatically delete a file or revoke a request that an external system has already processed. On restart, the Tasklet may call the API again or rewrite the file and create duplicate side effects.

Ways to reduce risk:

- **Idempotency key:** use a stable key so the target system can recognize repeated requests.
- **Outbox pattern:** write the message-sending request in the same database transaction, then a separate publisher sends the message and marks the status.
- **Staging and processing state:** record completed operations so a restart knows which step to continue.
- **Compensation:** perform a compensating operation if the business system allows it and a direct rollback is not possible.
- **Atomic file replacement:** write a temporary file and rename it after completion, if the filesystem and the deployment requirements support it.

Choose a mechanism suited to each side effect. Do not assume a database transaction can span every external system.

## 10. Recording and observing errors

When a Tasklet fails, the operator needs to know which Job, which Step, which batch, and what cause. You can combine logging, listeners, and JobExplorer.

### Logging with context

~~~java
try {
    batchService.process(batchId);
} catch (BatchProcessingException ex) {
    log.error(
            "Tasklet failed for batchId={}, step=processBatch",
            batchId,
            ex);
    throw ex;
}
~~~

Logs should include the Job name, the JobExecutionId or StepExecutionId when accessible, the business key, and the error category. Do not log credentials or sensitive payloads.

### StepExecutionListener

A listener can be used to record the result after the Step ends:

~~~java
public class BatchStepListener implements StepExecutionListener {

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        if (stepExecution.getStatus() == BatchStatus.FAILED) {
            log.error(
                    "Step {} failed with exit status {}",
                    stepExecution.getStepName(),
                    stepExecution.getExitStatus());
        }

        return null;
    }
}
~~~

Returning null keeps the current ExitStatus unchanged. A listener is suitable for observing and adding information. Do not use a listener to erase errors or change a FAILED Step to COMPLETED just to make the Job green on a dashboard.

### JobExplorer

JobExplorer lets you look up JobExecution and StepExecution from the metadata repository:

~~~java
JobExecution execution =
        jobExplorer.getJobExecution(jobExecutionId);

if (execution != null) {
    for (StepExecution stepExecution : execution.getStepExecutions()) {
        log.info(
                "step={}, status={}, exitStatus={}",
                stepExecution.getStepName(),
                stepExecution.getStatus(),
                stepExecution.getExitStatus());
    }
}
~~~

You can combine the metadata with a log correlation ID to identify the root exception. Avoid directly editing the metadata tables to change a Job's status; use the operations API and an appropriate restart process.

## 11. Distinguishing an exception, a skip, and a normal business result

A Tasklet does not have item-level skip semantics like a chunk-oriented Step. If a record is excluded from processing, the Tasklet must decide for itself how to record it and continue. Throwing an exception usually means the Tasklet pass failed; returning FINISHED means the work ended normally.

For example, if a batch contains some rejected records but can still complete under the business rules, the Tasklet can:

1. Write the rejected records to a rejected area.
2. Record the accepted and rejected counts.
3. Determine whether there is a serious error.
4. Complete with an appropriate business status, or throw an exception if the failure condition is met.

If the business needs to continue after each item error, a chunk-oriented Step with a skip policy and a SkipListener usually provides a more suitable structure. Do not build a complex skip mechanism inside a Tasklet if ItemReader/ItemProcessor/ItemWriter can already model the work.

## 12. Common mistakes

### Catching an exception and returning FINISHED

The TaskletStep may consider the Step complete even though the business operation failed. Rethrow the exception if the error should make the Step fail.

### Using CONTINUABLE to represent an error

CONTINUABLE only asks the Tasklet to run the next pass. It is not an error signal. If it cannot continue, throw an exception or represent a normal business result according to the designed flow.

### Retrying every exception

Retrying data errors or configuration errors only makes the Job fail later. Only retry exceptions that can recover and limit the number of attempts.

### Assuming a database rollback undoes HTTP or file operations

Side effects outside the transaction may still exist. Use an idempotency key, an outbox, staging, or compensation.

### Not saving a checkpoint for a multi-pass Tasklet

After some passes have committed, an exception in a later pass may cause the Tasklet to run again from the beginning on restart. Store durable progress and ensure the checkpoint is consistent with the data.

### Using generic exceptions

Exceptions without semantics make error classification, retry, and alerting harder. Create specific domain exceptions and keep the original cause.

### Changing JobParameters on restart

If the identifying parameters change, Spring Batch may create a new JobInstance. Keep the original identifiers when the goal is to restart the same instance.

### Converting a FAILED Step to COMPLETED in a listener

This can hide errors and cause the operations flow to misread the result. A listener should observe or add information; only change the ExitStatus when there is a clear business rule.

## 13. Process for handling Tasklet exceptions

When designing a Tasklet that can fail, determine:

1. Which conditions are business errors and which are technical errors?
2. Which exceptions should cause the transaction to roll back and the Step to be FAILED?
3. Are there transient errors that may be retried? What are the limit and backoff?
4. Which side effects lie outside the database transaction?
5. If the Tasklet fails after part of the work has committed, where will the restart continue from?
6. Is a checkpoint, idempotency key, outbox, or compensation needed?
7. Does the Job need to stop immediately or move to a Step that records the error?
8. Do the logs and metadata contain enough information for the operator to identify the cause?

A good Tasklet does not try to hide every exception. It clearly distinguishes errors that must stop, errors that can be retried, and normal business results; and it ensures the transaction, restart, and side effects behave predictably.

## Conclusion

When a Tasklet throws an exception, the TaskletStep handles the error within the execution pass's transaction, rolls back per the transaction policy, and marks the Step as failed. Let the exception exit the Tasklet when the work is not completed; only catch an error when there is a truly valid way to handle it, and keep the cause if you wrap the exception. Retry needs to be bounded and error classification is needed, while restart needs stable identifying parameters, checkpoints, and idempotency. In particular, a database rollback does not automatically undo side effects such as HTTP requests or files, so you must design the corresponding recovery mechanisms.
